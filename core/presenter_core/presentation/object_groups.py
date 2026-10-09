"""Reviewed native grouping and ungrouping preserve child identities and relationships."""

from __future__ import annotations

import copy
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    _NS,
    DRAWING_NS,
    OBJECT_LIMIT,
    PRESENTATION_NS,
    _parse_xml_part,
    inspect_pptx_snapshot,
)
from presenter_core.presentation.group_geometry import (
    native_children,
    promoted_geometry,
    read_geometry,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService


def edit_group(
    editor: PresentationEditService, params: dict[str, Any], *, ungroup: bool
) -> dict[str, Any]:
    from presenter_core.presentation.editing import _next_ooxml_shape_id, _verified_source_archive

    reject_unknown_fields(
        params,
        {"project_id", "document_id", "expected_revision_id", "slide_id"}
        | ({"object_id", "expected_geometry"} if ungroup else {"objects"}),
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    expected = (
        params.get("objects")
        if not ungroup
        else [
            {
                "object_id": params.get("object_id"),
                "expected_geometry": params.get("expected_geometry"),
            }
        ]
    )
    if not isinstance(expected, list) or not (1 if ungroup else 2) <= len(expected) <= 20:
        raise invalid_request("Select between 2 and 20 objects to group, or one group to ungroup.")
    identities = []
    geometries = {}
    for item in expected:
        if not isinstance(item, dict):
            raise invalid_request("Provide each object's identity and current geometry.")
        reject_unknown_fields(item, {"object_id", "expected_geometry"})
        identity = editor._uuid_field(item.get("object_id"), "object_id")
        identities.append(identity)
        geometries[identity] = editor._geometry_field(
            item.get("expected_geometry"), "expected_geometry"
        )
    if len(set(identities)) != len(identities):
        raise invalid_request("Selected objects must have distinct identities.")
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
    slide = next((page for page in fidelity.slides if page.slide_id == slide_id), None)
    if slide is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
        )
    objects = [obj for obj in slide.objects if obj.object_id in identities]
    if len(objects) != len(identities):
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "A selected object is unavailable."
        )
    for obj in objects:
        if not obj.group_editable or (ungroup and obj.kind != "grpSp"):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                obj.group_reason or "Select a supported native group.",
            )
        if obj.geometry != geometries[obj.object_id]:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The selected geometry changed. Refresh the slide.",
            )
    if not ungroup and fidelity.object_count >= OBJECT_LIMIT:
        raise CoreDomainError(
            "PRESENTATION_EDIT_RESOURCE_LIMIT", "The presentation has reached its object limit."
        )
    selected: list[str] = []

    def write(original: Path, target: Path) -> None:
        expected_geometries = {}
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            tree = root.find("p:cSld/p:spTree", _NS)
            nodes = [
                editor._find_object_node(root, ooxml_id=obj.ooxml_id, kind=obj.kind)
                for obj in objects
            ]
            assert tree is not None
            if any(node.getparent() is not tree for node in nodes):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED",
                    "Select slide-level objects or their containing group.",
                )
            if ungroup:
                group = nodes[0]
                insertion = tree.index(group)
                children = native_children(group)
                child_native_ids = []
                for child in children:
                    geometry = promoted_geometry(group, child)
                    if geometry.width_emu <= 0 or geometry.height_emu <= 0:
                        raise invalid_request("Ungrouping would create an empty object.")
                    _, transform = read_geometry(child)
                    offset, extent = transform.find("a:off", _NS), transform.find("a:ext", _NS)
                    offset.set("x", str(geometry.x_emu))
                    offset.set("y", str(geometry.y_emu))
                    extent.set("cx", str(geometry.width_emu))
                    extent.set("cy", str(geometry.height_emu))
                    native_id = child.xpath("./*/p:cNvPr/@id", namespaces=_NS)[0]
                    child_native_ids.append(native_id)
                    expected_geometries[native_id] = geometry
                tree.remove(group)
                for index, child in enumerate(children):
                    tree.insert(insertion + index, child)
                selected.extend(
                    obj.object_id for obj in slide.objects if obj.ooxml_id in child_native_ids
                )
            else:
                nodes.sort(key=tree.index)
                anchor = nodes[-1]
                group = etree.Element(f"{{{PRESENTATION_NS}}}grpSp")
                nonvisual = etree.SubElement(group, f"{{{PRESENTATION_NS}}}nvGrpSpPr")
                native_id = _next_ooxml_shape_id(root)
                etree.SubElement(
                    nonvisual,
                    f"{{{PRESENTATION_NS}}}cNvPr",
                    id=native_id,
                    name=f"Group {native_id}",
                )
                etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvGrpSpPr")
                etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}nvPr")
                properties = etree.SubElement(group, f"{{{PRESENTATION_NS}}}grpSpPr")
                transform = etree.SubElement(properties, f"{{{DRAWING_NS}}}xfrm")
                left = min(geometries[obj.object_id].x_emu for obj in objects)
                top = min(geometries[obj.object_id].y_emu for obj in objects)
                width = (
                    max(
                        geometries[obj.object_id].x_emu + geometries[obj.object_id].width_emu
                        for obj in objects
                    )
                    - left
                )
                height = (
                    max(
                        geometries[obj.object_id].y_emu + geometries[obj.object_id].height_emu
                        for obj in objects
                    )
                    - top
                )
                for tag, attrs in [
                    ("off", {"x": left, "y": top}),
                    ("ext", {"cx": width, "cy": height}),
                    ("chOff", {"x": left, "y": top}),
                    ("chExt", {"cx": width, "cy": height}),
                ]:
                    etree.SubElement(
                        transform,
                        f"{{{DRAWING_NS}}}{tag}",
                        **{key: str(value) for key, value in attrs.items()},
                    )
                tree.insert(tree.index(anchor), group)
                for node in nodes:
                    group.append(node)
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
        fresh = next(page for page in updated.slides if page.slide_id == slide_id)
        original_ids = {obj.object_id for obj in slide.objects}
        if ungroup:
            expected_ids = original_ids - {objects[0].object_id}
            if {obj.object_id for obj in fresh.objects} != expected_ids or any(
                obj.geometry != expected_geometries[obj.ooxml_id] or not obj.geometry_editable
                for obj in fresh.objects
                if obj.ooxml_id in expected_geometries
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED",
                    "Ungrouping could not preserve native geometry and identities.",
                )
        else:
            groups = [obj for obj in fresh.objects if obj.object_id not in original_ids]
            if (
                len(groups) != 1
                or groups[0].kind != "grpSp"
                or not groups[0].group_editable
                or {obj.object_id for obj in fresh.objects} != original_ids | {groups[0].object_id}
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED",
                    "Grouping could not preserve native objects.",
                )
            selected.append(groups[0].object_id)
        if [page.slide_id for page in updated.slides] != [
            page.slide_id for page in fidelity.slides
        ] or any(
            page != original_page
            for page, original_page in zip(updated.slides, fidelity.slides, strict=True)
            if page.slide_id != slide_id
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED", "Other slides changed during grouping."
            )

    result = editor._commit_revision(project, document, revision, source, write)
    return {
        **result,
        "slide_id": slide_id,
        "selected_object_ids": selected,
        **({"created_object_id": selected[-1]} if not ungroup else {}),
    }
