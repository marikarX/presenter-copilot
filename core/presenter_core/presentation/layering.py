"""Change stacking order without changing object contents or package relationships."""

from __future__ import annotations

import copy
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    OBJECT_LIMIT,
    PRESENTATION_NS,
    _parse_xml_part,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService


def change_object_layer(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "object_id",
            "expected_object_ids",
            "direction",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    object_id = editor._uuid_field(params.get("object_id"), "object_id")
    direction = params.get("direction")
    if direction not in ("forward", "backward", "front", "back"):
        raise invalid_request("Choose a supported layer direction.")
    expected = params.get("expected_object_ids")
    if not isinstance(expected, list) or not 1 <= len(expected) <= OBJECT_LIMIT:
        raise invalid_request("Provide the current slide's object order.")
    expected = [editor._uuid_field(value, "expected_object_ids") for value in expected]
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
    obj = (
        next((item for item in slide.objects if item.object_id == object_id), None)
        if slide
        else None
    )
    if slide is None or obj is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected object is unavailable."
        )
    if [item.object_id for item in slide.objects] != expected:
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET", "The object order changed. Refresh the slide."
        )
    if not obj.delete_editable or obj.kind not in ("sp", "pic", "graphicFrame", "grpSp"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "Choose a supported slide-level shape, picture, chart, table or group.",
        )

    def write(original: Path, target: Path) -> bool:
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            node = editor._find_object_node(root, ooxml_id=obj.ooxml_id, kind=obj.kind)
            parent = node.getparent()
            if parent is None or parent.tag != f"{{{PRESENTATION_NS}}}spTree":
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "This object is not slide-level."
                )
            reserved = {
                f"{{{PRESENTATION_NS}}}{name}" for name in ("nvGrpSpPr", "grpSpPr", "extLst")
            }
            layers = [child for child in parent if child.tag not in reserved]
            index = layers.index(node)
            destination = {
                "front": len(layers) - 1,
                "back": 0,
                "forward": min(index + 1, len(layers) - 1),
                "backward": max(index - 1, 0),
            }[direction]
            if destination == index:
                return False
            anchor = layers[destination]
            parent.remove(node)
            parent.insert(parent.index(anchor) + (1 if destination > index else 0), node)
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
        if [item.slide_id for item in updated.slides] != [
            item.slide_id for item in fidelity.slides
        ] or {item.object_id: item for page in updated.slides for item in page.objects} != {
            item.object_id: item for page in fidelity.slides for item in page.objects
        }:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED", "Object contents changed during layering."
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "slide_id": slide_id, "object_id": object_id, "direction": direction}
