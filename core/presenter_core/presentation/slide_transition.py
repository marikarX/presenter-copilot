"""Set a slide's basic transition (p:transition) or remove it."""

from __future__ import annotations

import copy
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    PRESENTATION_NS,
    SLIDE_TRANSITIONS,
    _parse_xml_part,
    inspect_pptx_snapshot,
    slide_transition,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

P = f"{{{PRESENTATION_NS}}}"
_FOLLOWING = {f"{P}timing", f"{P}extLst"}


def set_slide_transition(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "expected_transition",
            "transition",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    expected, transition = params.get("expected_transition"), params.get("transition")
    if expected not in SLIDE_TRANSITIONS or transition not in SLIDE_TRANSITIONS:
        raise invalid_request(
            "transition must be one of " + ", ".join(sorted(SLIDE_TRANSITIONS)) + ".",
            field="transition",
        )
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    source_path = editor._storage.paths.snapshot_path(
        project, source["local_snapshot_path"], require_exists=True
    )
    with source_path.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=document,
            expected_sha256=source["sha256"],
            byte_size=source["byte_size"],
        )
    slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
    if slide is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
        )
    if slide.transition is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "This slide uses a transition effect that stays read-only.",
        )
    if slide.transition != expected:
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The slide transition changed. Refresh and try again.",
            retryable=True,
        )
    if transition == expected:
        return {
            "changed": False,
            "revision_id": source["revision_id"],
            "revision_number": int(source["revision_number"]),
            "sha256": source["sha256"],
            "byte_size": int(source["byte_size"]),
        }

    def write(original: Path, target: Path) -> bool:
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            if slide_transition(root) != expected:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET",
                    "The slide transition changed. Refresh and try again.",
                    retryable=True,
                )
            for existing in root.findall(f"{P}transition"):
                root.remove(existing)
            if transition != "none":
                element = etree.Element(f"{P}transition", spd="med")
                etree.SubElement(element, f"{P}{transition}")
                anchor = next((child for child in root if child.tag in _FOLLOWING), None)
                if anchor is None:
                    root.append(element)
                else:
                    anchor.addprevious(element)
            rewritten = etree.tostring(
                root, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            with zipfile.ZipFile(target, "w", allowZip64=True) as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    if info.filename == slide.part_name:
                        output.writestr(copy.copy(info), rewritten)
                    else:
                        with (
                            archive.open(info) as reader,
                            output.open(copy.copy(info), "w") as writer,
                        ):
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
        with target.open("rb") as handle:
            updated = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(target),
                byte_size=target.stat().st_size,
            )
        revised = next((item for item in updated.slides if item.slide_id == slide_id), None)
        if (
            revised is None
            or revised.transition != transition
            or {o.object_id: o for page in updated.slides for o in page.objects}
            != {o.object_id: o for page in fidelity.slides for o in page.objects}
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The slide transition edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "slide_id": slide_id, "transition": transition}
