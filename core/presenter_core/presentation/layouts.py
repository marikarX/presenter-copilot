"""Native master/layout catalog; package paths never cross the IPC boundary."""

from __future__ import annotations

import copy
import posixpath
import uuid
import zipfile
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    _NS,
    REL_NS,
    _geometry_for_object,
    _parse_xml_part,
    _relationships,
    _resolve_internal_part,
)
from presenter_core.presentation.workspace_source import PresentationWorkspaceSourceService

_TEXT_TYPES = {"title", "ctrTitle", "subTitle", "body", "obj"}


def creation_slots(layout: Any, master: Any, layout_id: str) -> tuple[list[dict[str, Any]], bool]:
    """Resolve only direct text placeholders; no foreign relationship data is copied."""
    slots: list[dict[str, Any]] = []
    supported = True
    seen: set[str] = set()
    for shape in layout.findall("p:cSld/p:spTree/p:sp", _NS):
        ph = shape.find("p:nvSpPr/p:nvPr/p:ph", _NS)
        if ph is None or ph.get("type", "obj") not in _TEXT_TYPES:
            continue
        if len(slots) >= 20:
            supported = False
            break
        idx, kind = ph.get("idx", "0"), ph.get("type", "obj")
        if (
            idx in seen
            or not idx.isascii()
            or not idx.isdigit()
            or len(idx) > 10
            or int(idx) > 4_294_967_295
            or set(ph.attrib) - {"idx", "type", "sz", "orient"}
            or len(ph)
            or ph.get("sz", "full") not in {"full", "half", "quarter"}
            or ph.get("orient", "horz") not in {"horz", "vert"}
        ):
            supported = False
        seen.add(idx)
        transform = shape.find("p:spPr/a:xfrm", _NS)
        if transform is None:
            matches = []
            for parent in master.findall("p:cSld/p:spTree/p:sp", _NS):
                parent_ph = parent.find("p:nvSpPr/p:nvPr/p:ph", _NS)
                if parent_ph is not None and parent_ph.get("type", "obj") == (
                    "title" if kind == "ctrTitle" else "body" if kind == "obj" else kind
                ):
                    matches.append(parent)
            if len(matches) == 1:
                transform = matches[0].find("p:spPr/a:xfrm", _NS)
        if transform is None:
            supported = False
        elif set(transform.attrib) - {"rot", "flipH", "flipV"} or any(
            len(child)
            or set(child.attrib)
            - ({"x", "y"} if child.tag == f"{{{_NS['a']}}}off" else {"cx", "cy"})
            for child in transform
        ):
            supported = False
        name = shape.find("p:nvSpPr/p:cNvPr", _NS)
        slots.append(
            {
                "placeholder_id": str(uuid.uuid5(uuid.UUID(layout_id), "placeholder:" + idx)),
                "name": ((name.get("name") if name is not None else None) or kind)[:160],
                "type": kind,
                "_placeholder": copy.deepcopy(ph),
                "_transform": copy.deepcopy(transform),
            }
        )
    # Grouped/alternate placeholders cannot be recreated safely by this text workflow.
    text_count = sum(ph.get("type", "obj") in _TEXT_TYPES for ph in layout.findall(".//p:ph", _NS))
    return slots, supported and text_count == len(slots) and len(slots) <= 20


def populate_slots(tree: Any, slots: list[dict[str, Any]], texts: dict[str, str]) -> None:
    for number, slot in enumerate(slots, 2):
        shape = etree.SubElement(tree, f"{{{_NS['p']}}}sp")
        nv = etree.SubElement(shape, f"{{{_NS['p']}}}nvSpPr")
        etree.SubElement(nv, f"{{{_NS['p']}}}cNvPr", id=str(number), name=slot["name"])
        etree.SubElement(nv, f"{{{_NS['p']}}}cNvSpPr")
        props = etree.SubElement(nv, f"{{{_NS['p']}}}nvPr")
        props.append(copy.deepcopy(slot["_placeholder"]))
        sp = etree.SubElement(shape, f"{{{_NS['p']}}}spPr")
        sp.append(copy.deepcopy(slot["_transform"]))
        body = etree.SubElement(shape, f"{{{_NS['p']}}}txBody")
        etree.SubElement(body, f"{{{_NS['a']}}}bodyPr")
        etree.SubElement(body, f"{{{_NS['a']}}}lstStyle")
        for line in texts.get(slot["placeholder_id"], "").split("\n"):
            paragraph = etree.SubElement(body, f"{{{_NS['a']}}}p")
            if line:
                run = etree.SubElement(paragraph, f"{{{_NS['a']}}}r")
                etree.SubElement(run, f"{{{_NS['a']}}}t").text = line


def catalog(archive: zipfile.ZipFile, document: str) -> list[dict[str, Any]]:
    members = {info.filename: info for info in archive.infolist()}

    def read(part: str) -> etree._Element:
        if part not in members:
            raise CoreDomainError(
                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                "A native layout catalog part is missing.",
            )
        return _parse_xml_part(archive, members[part])

    def target(
        owner: str, relationships: dict[str, tuple[str, str, str]], rid: str | None, kind: str
    ) -> str:
        relation = relationships.get(rid) if rid is not None else None
        if (
            relation is None
            or relation[0] != f"{REL_NS}/{kind}"
            or relation[2].casefold() != "internal"
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "Native layout references must be internal and unambiguous.",
            )
        return _resolve_internal_part(posixpath.dirname(owner), relation[1])

    def rels(part: str) -> dict[str, tuple[str, str, str]]:
        return _relationships(
            read(
                posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
            )
        )

    root = read("ppt/presentation.xml")
    presentation_rels = rels("ppt/presentation.xml")
    result = []
    seen = set()
    masters = root.findall("p:sldMasterIdLst/p:sldMasterId", _NS)
    for number, node in enumerate(masters, 1):
        master_part = target(
            "ppt/presentation.xml", presentation_rels, node.get(f"{{{REL_NS}}}id"), "slideMaster"
        )
        master = read(master_part)
        if master.tag != f"{{{_NS['p']}}}sldMaster":
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED", "The native master type is unsupported."
            )
        relationships = rels(master_part)
        master_name = master.find("p:cSld", _NS)
        label = (master_name.get("name") if master_name is not None else None) or f"Theme {number}"
        for item in master.findall("p:sldLayoutIdLst/p:sldLayoutId", _NS):
            part = target(master_part, relationships, item.get(f"{{{REL_NS}}}id"), "slideLayout")
            if part in seen:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "Native layout references are duplicated."
                )
            seen.add(part)
            layout = read(part)
            if layout.tag != f"{{{_NS['p']}}}sldLayout":
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "The native layout type is unsupported."
                )
            parents = [v for v in rels(part).values() if v[0] == f"{REL_NS}/slideMaster"]
            if (
                len(parents) != 1
                or parents[0][2].casefold() != "internal"
                or _resolve_internal_part(posixpath.dirname(part), parents[0][1]) != master_part
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED", "The native layout does not match its master."
                )
            common = layout.find("p:cSld", _NS)
            name = (
                (common.get("name") if common is not None else None)
                or layout.get("type")
                or "Unnamed layout"
            )
            layout_id = str(uuid.uuid5(uuid.UUID(document), "native-layout:" + part))
            slots, supported = creation_slots(layout, master, layout_id)
            size = root.find("p:sldSz", _NS)
            if supported:
                tree = etree.Element(f"{{{_NS['p']}}}spTree")
                populate_slots(tree, slots, {})
                try:
                    supported = size is not None and all(
                        _geometry_for_object(
                            shape,
                            kind="sp",
                            shape_tree=tree,
                            slide_width_emu=int(size.get("cx", "")),
                            slide_height_emu=int(size.get("cy", "")),
                        )[1]
                        for shape in tree
                    )
                except ValueError:
                    supported = False
            result.append(
                {
                    "layout_id": layout_id,
                    "creation_supported": supported,
                    "creation_placeholders": [
                        {k: v for k, v in slot.items() if not k.startswith("_")} for slot in slots
                    ],
                    "_slots": slots,
                    "name": name[:160],
                    "master_name": label[:160],
                    "placeholder_count": len(layout.findall(".//p:ph", _NS)),
                    "_part": part,
                }
            )
            if len(result) > 500:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_RESOURCE_LIMIT",
                    "The native layout catalog exceeds 500 layouts.",
                )
    return result


class PresentationLayoutService:
    def __init__(self, sources: PresentationWorkspaceSourceService) -> None:
        self._sources = sources

    def list_native_layouts(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.editing import (
            PresentationEditService,
            _verified_source_archive,
        )

        reject_unknown_fields(params, {"project_id", "document_id", "revision_id", "slide_id"})
        project, document, revision, native = self._sources.read_revision_inventory(
            {key: value for key, value in params.items() if key != "slide_id"}
        )
        remap_candidates = None
        with self._sources._storage.project_database(project) as connection:
            row = connection.execute(
                "SELECT local_snapshot_path, sha256, byte_size "
                "FROM presentation_revisions WHERE id=?",
                (revision,),
            ).fetchone()
        path = self._sources._storage.paths.snapshot_path(
            project, row["local_snapshot_path"], require_exists=True
        )
        with _verified_source_archive(
            path, expected_sha256=row["sha256"], expected_byte_size=row["byte_size"]
        ) as archive:
            items = catalog(archive, document)
            members = {info.filename: info for info in archive.infolist()}
            used = [
                PresentationEditService._slide_layout_part(archive, members, slide.part_name)[1]
                for slide in native.slides
            ]
            result = [
                {
                    **{k: v for k, v in item.items() if not k.startswith("_")},
                    "used_by_slides": [
                        slide.ordinal
                        for slide, part in zip(native.slides, used, strict=True)
                        if part == item["_part"]
                    ],
                }
                for item in items
            ]
            if "slide_id" in params:
                from presenter_core.presentation.placeholder_remapping import candidates

                slide = next(
                    (item for item in native.slides if item.slide_id == params["slide_id"]), None
                )
                if slide is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
                    )
                remap_candidates = candidates(
                    _parse_xml_part(archive, members[slide.part_name]), slide
                )
        # A concurrent head update cannot publish a catalog for an obsolete view.
        with self._sources._storage.project_database(project) as connection:
            from presenter_core.presentation.semantics import PresentationSemanticService

            PresentationSemanticService._require_current_presentation(
                connection, project, document, revision
            )
        return {
            "revision_id": revision,
            "items": result,
            **({"remap_candidates": remap_candidates} if remap_candidates is not None else {}),
        }
