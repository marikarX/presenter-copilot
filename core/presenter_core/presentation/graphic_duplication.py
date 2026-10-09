"""Clone a native chart's internal package graph without opening its workbook."""

from __future__ import annotations

import posixpath
import re
import uuid
import zipfile
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.fidelity import (
    _NS,
    PACKAGE_REL_NS,
    REL_NS,
    _parse_xml_part,
    _relationships,
    _resolve_internal_part,
)

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
CNS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
ALLOWED = {
    f"{REL_NS}/package",
    f"{REL_NS}/image",
    f"{REL_NS}/themeOverride",
    "http://schemas.microsoft.com/office/2011/relationships/chartStyle",
    "http://schemas.microsoft.com/office/2011/relationships/chartColorStyle",
}


def clone_chart_graph(
    archive: zipfile.ZipFile,
    slide_part: str,
    frame: Any,
    *,
    slide_relationships: Any = None,
    content_types_root: Any = None,
    preserve_relationship_id: bool = False,
    cloned_parts: dict[str, str] | None = None,
    source_slide_part: str | None = None,
) -> dict[str, bytes]:
    refs = frame.findall("a:graphic/a:graphicData/c:chart", {**_NS, "c": CNS})
    if not refs:
        return {}

    def reject() -> CoreDomainError:
        return CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "This chart's package dependencies cannot be duplicated safely.",
        )

    def rels_name(part: str) -> str:
        return posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")

    members = {m.filename: m for m in archive.infolist()}
    slide_rels_part = rels_name(slide_part)
    if (
        len(refs) != 1
        or (source_slide_part or slide_part) not in members
        or rels_name(source_slide_part or slide_part) not in members
        or (slide_relationships is None and slide_rels_part not in members)
    ):
        raise reject()
    slide_rels = (
        slide_relationships
        if slide_relationships is not None
        else _parse_xml_part(archive, members[slide_rels_part])
    )
    source_part = source_slide_part or slide_part
    source_rels_part = rels_name(source_part)
    if source_rels_part not in members:
        raise reject()
    source_rels = (
        _parse_xml_part(archive, members[source_rels_part])
        if source_slide_part is not None
        else slide_rels
    )
    relations = _relationships(source_rels)
    relation = relations.get(refs[0].get(f"{{{REL_NS}}}id", ""))
    if not relation or relation[0] != f"{REL_NS}/chart" or relation[2].casefold() != "internal":
        raise reject()
    chart_part = _resolve_internal_part(posixpath.dirname(source_part), relation[1])
    if chart_part not in members:
        raise reject()
    chart = _parse_xml_part(archive, members[chart_part])
    if chart.tag != f"{{{CNS}}}chartSpace" or chart.findall(f".//{{{CNS}}}extLst"):
        raise reject()
    content_types = (
        content_types_root
        if content_types_root is not None
        else _parse_xml_part(archive, members["[Content_Types].xml"])
    )
    source_types = (
        _parse_xml_part(archive, members["[Content_Types].xml"])
        if source_slide_part is not None
        else content_types
    )
    overrides = {
        n.get("PartName", "").lstrip("/"): n.get("ContentType")
        for n in source_types.findall(f"{{{CT}}}Override")
    }
    defaults = {
        n.get("Extension"): n.get("ContentType") for n in source_types.findall(f"{{{CT}}}Default")
    }
    additions: dict[str, bytes] = {}
    mapped: dict[str, str] = cloned_parts if cloned_parts is not None else {}
    initial_part_count = len(mapped)
    token = uuid.uuid4().hex
    # Keep imported charts outside the preview adapter's authored-chart naming convention.
    prefix = (
        "copilot"
        if re.fullmatch(r"copilot-[0-9a-f]{32}\.xml", posixpath.basename(chart_part))
        else "copilot-copy"
    )

    def clone(part: str) -> str:
        if part in mapped:
            return mapped[part]
        if part not in members or len(mapped) - initial_part_count >= 64:
            raise reject()
        new = posixpath.join(
            posixpath.dirname(part),
            (f"{prefix}-{token}" if part == chart_part else f"copilot-{token}-{len(mapped)}")
            + posixpath.splitext(part)[1],
        )
        if new in members or new in additions:
            raise reject()
        mapped[part] = new
        content_type = overrides.get(part) or defaults.get(posixpath.splitext(part)[1].lstrip("."))
        if not content_type:
            raise reject()
        additions[new] = archive.read(members[part])
        if part in overrides or source_slide_part is not None:
            etree.SubElement(
                content_types, f"{{{CT}}}Override", PartName="/" + new, ContentType=content_type
            )
        old_rels = rels_name(part)
        if old_rels in members:
            rels = _parse_xml_part(archive, members[old_rels])
            _relationships(rels)
            for node in rels:
                if (
                    node.get("Type") not in ALLOWED
                    or node.get("TargetMode", "Internal").casefold() != "internal"
                ):
                    raise reject()
                destination = _resolve_internal_part(
                    posixpath.dirname(part), node.get("Target", "")
                )
                node.set("Target", posixpath.relpath(clone(destination), posixpath.dirname(new)))
            additions[rels_name(new)] = etree.tostring(
                rels, encoding="UTF-8", xml_declaration=True, standalone=True
            )
        return new

    copied_chart = clone(chart_part)
    if preserve_relationship_id:
        rid = refs[0].get(f"{{{REL_NS}}}id", "")
        node = next(n for n in slide_rels if n.get("Id") == rid)
        node.set("Target", posixpath.relpath(copied_chart, posixpath.dirname(slide_part)))
    else:
        new_rid = "rIdCopilot" + token
        if new_rid in relations or new_rid in _relationships(slide_rels):
            raise reject()
        etree.SubElement(
            slide_rels,
            f"{{{PACKAGE_REL_NS}}}Relationship",
            Id=new_rid,
            Type=f"{REL_NS}/chart",
            Target=posixpath.relpath(copied_chart, posixpath.dirname(slide_part)),
        )
        refs[0].set(f"{{{REL_NS}}}id", new_rid)
    additions[slide_rels_part] = etree.tostring(
        slide_rels, encoding="UTF-8", xml_declaration=True, standalone=True
    )
    additions["[Content_Types].xml"] = etree.tostring(
        content_types, encoding="UTF-8", xml_declaration=True, standalone=True
    )
    return additions
