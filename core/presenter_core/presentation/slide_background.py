"""Set a slide's own solid background color, or return it to the layout background."""

from __future__ import annotations

import copy
import re
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    DRAWING_NS,
    PRESENTATION_NS,
    FidelityBackground,
    _parse_xml_part,
    inspect_pptx_snapshot,
    slide_background,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

P = f"{{{PRESENTATION_NS}}}"
A = f"{{{DRAWING_NS}}}"


def background_payload(background: FidelityBackground) -> dict[str, Any]:
    return {"state": background.state, "color": background.color}


def _expected(value: Any) -> FidelityBackground:
    if not isinstance(value, dict) or set(value) != {"state", "color"}:
        raise invalid_request(
            "expected_background must contain state and color.", field="expected_background"
        )
    state, color = value["state"], value["color"]
    valid = (
        state in {"inherited", "theme_reference"}
        and color is None
        or state == "solid"
        and isinstance(color, str)
        and re.fullmatch(r"#[0-9A-F]{6}", color)
    )
    if not valid:
        raise invalid_request(
            "expected_background is not a supported background.", field="expected_background"
        )
    return FidelityBackground(state=state, color=color)


def set_slide_background(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "expected_background",
            "replacement_color",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    expected = _expected(params.get("expected_background"))
    color = params.get("replacement_color")
    if color is not None and (
        not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color)
    ):
        raise invalid_request(
            "replacement_color must be a #RRGGBB color or null to use the layout background.",
            field="replacement_color",
        )
    replacement = (
        FidelityBackground(state="inherited", color=None)
        if color is None
        else FidelityBackground(state="solid", color=color.upper())
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
    if slide.background is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "This slide uses a picture, gradient or pattern background that stays read-only.",
        )
    if slide.background != expected:
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The slide background changed. Refresh the preview and try again.",
            retryable=True,
        )
    if replacement == expected:
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
            if slide_background(root) != expected:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET",
                    "The slide background changed. Refresh the preview and try again.",
                    retryable=True,
                )
            common = root.find(f"{P}cSld")
            if common is None:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "This slide has no common slide data."
                )
            for existing in common.findall(f"{P}bg"):
                common.remove(existing)
            if replacement.color is not None:
                background = etree.Element(f"{P}bg")
                properties = etree.SubElement(background, f"{P}bgPr")
                fill = etree.SubElement(properties, f"{A}solidFill")
                etree.SubElement(fill, f"{A}srgbClr", val=replacement.color[1:])
                etree.SubElement(properties, f"{A}effectLst")
                common.insert(0, background)
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
            or revised.background != replacement
            or [item.slide_id for item in updated.slides]
            != [item.slide_id for item in fidelity.slides]
            or {item.object_id: item for page in updated.slides for item in page.objects}
            != {item.object_id: item for page in fidelity.slides for item in page.objects}
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The slide background edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "slide_id": slide_id, "background": background_payload(replacement)}
