"""Accessibility check: visual objects without alt text and slides without a title.

Mirrors the two most common PowerPoint Accessibility Checker errors. Read-only; fixes
go through the alt text editor and slide editing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from presenter_core.errors import reject_unknown_fields
from presenter_core.presentation.fidelity import (
    PRESENTATION_NS,
    _parse_xml_part,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

P = f"{{{PRESENTATION_NS}}}"
TABLE_URI = "http://schemas.openxmlformats.org/drawingml/2006/table"
MAX_ISSUES = 500


def _visual_kinds(root: Any) -> dict[str, str]:
    """Native ids of objects that need alt text, mapped to a readable type."""
    result: dict[str, str] = {}
    tree = root.find(f"{P}cSld/{P}spTree")
    if tree is None:
        return result
    for node in tree.iter(f"{P}pic", f"{P}graphicFrame", f"{P}grpSp"):
        if node is tree:
            continue
        nonvisual = node.find(f"./*/{P}cNvPr")
        if nonvisual is None or not nonvisual.get("id"):
            continue
        local = node.tag.rsplit("}", 1)[-1]
        if local == "graphicFrame":
            uri = node.xpath("./*[local-name()='graphic']/*[local-name()='graphicData']/@uri")
            if not uri or uri[0] == TABLE_URI:
                continue  # Tables are read as text.
            kind = "chart" if uri[0].endswith("/chart") else "graphic"
        elif local == "grpSp":
            if node.getparent() is not tree:
                continue  # Only the outermost group needs a description.
            kind = "group"
        else:
            kind = "picture"
        result[nonvisual.get("id")] = kind
    return result


def _has_title(root: Any) -> bool:
    for shape in root.iter(f"{P}sp"):
        placeholder = shape.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
        if placeholder is not None and placeholder.get("type") in {"title", "ctrTitle"}:
            text = "".join(shape.itertext()).strip()
            if text:
                return True
    return False


def check_accessibility(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(params, {"project_id", "document_id", "revision_id"})
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("revision_id"), "revision_id")
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    path = editor._storage.paths.snapshot_path(
        project, source["local_snapshot_path"], require_exists=True
    )
    with path.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=document,
            expected_sha256=source["sha256"],
            byte_size=source["byte_size"],
        )
    issues: list[dict[str, Any]] = []
    truncated = False
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        for slide in fidelity.slides:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            found: list[dict[str, Any]] = []
            if not _has_title(root):
                found.append(
                    {
                        "issue": "missing_slide_title",
                        "slide_id": slide.slide_id,
                        "slide_number": slide.ordinal,
                        "object_id": None,
                        "name": None,
                        "object_type": None,
                    }
                )
            kinds = _visual_kinds(root)
            for obj in slide.objects:
                kind = kinds.get(obj.ooxml_id)
                if kind is None or obj.decorative or (obj.alt_text or "").strip():
                    continue
                found.append(
                    {
                        "issue": "missing_alt_text",
                        "slide_id": slide.slide_id,
                        "slide_number": slide.ordinal,
                        "object_id": obj.object_id,
                        "name": obj.name,
                        "object_type": kind,
                        "alt_text_editable": obj.alt_text is not None,
                    }
                )
            for item in found:
                if len(issues) >= MAX_ISSUES:
                    truncated = True
                    break
                issues.append(item)
    return {
        "revision_id": revision,
        "issues": issues,
        "truncated": truncated,
        "slide_count": len(fidelity.slides),
    }
