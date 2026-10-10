"""Native group eligibility and unrotated parent/child coordinate transforms."""

from __future__ import annotations

import copy
import posixpath
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import invalid_request
from presenter_core.presentation.fidelity import (
    _NS,
    DRAWING_NS,
    PRESENTATION_NS,
    REL_NS,
    FidelityGeometry,
    _delete_geometry_candidate,
    _graphic_frame_geometry_supported,
    _parse_xml_part,
    _relationships,
    _resolve_internal_part,
    has_unsafe_extensions,
)


def transform_path(kind: str) -> str:
    return {"grpSp": "./p:grpSpPr/a:xfrm", "graphicFrame": "./p:xfrm"}.get(kind, "./p:spPr/a:xfrm")


def read_geometry(node: Any) -> tuple[FidelityGeometry | None, Any]:
    kind = etree.QName(node).localname
    transforms = node.xpath(transform_path(kind), namespaces=_NS)
    if len(transforms) != 1:
        return None, None
    transform = transforms[0]
    try:
        offset, extent = transform.find("a:off", _NS), transform.find("a:ext", _NS)
        geometry = FidelityGeometry(
            int(offset.get("x")),
            int(offset.get("y")),
            int(extent.get("cx")),
            int(extent.get("cy")),
        )
    except (AttributeError, TypeError, ValueError):
        return None, transform
    return geometry, transform


def box_transform(node: Any) -> bool:
    """A shape/picture transform whose off/ext box can move; rotation and flips are kept."""
    geometry, transform = read_geometry(node)
    if geometry is None or geometry.width_emu <= 0 or geometry.height_emu <= 0:
        return False
    if [child.tag for child in transform] != [f"{{{DRAWING_NS}}}off", f"{{{DRAWING_NS}}}ext"]:
        return False
    if any(key not in {"rot", "flipH", "flipV"} for key in transform.attrib):
        return False
    rotation = transform.get("rot", "0")
    return rotation.lstrip("-").isdigit() and all(
        transform.get(key) in {None, "0", "1", "false", "true"} for key in ("flipH", "flipV")
    )


def simple_transform(node: Any) -> bool:
    geometry, transform = read_geometry(node)
    if geometry is None or geometry.width_emu <= 0 or geometry.height_emu <= 0:
        return False
    kind = etree.QName(node).localname
    names = ["off", "ext", "chOff", "chExt"] if kind == "grpSp" else ["off", "ext"]
    if [child.tag for child in transform] != [f"{{{DRAWING_NS}}}{name}" for name in names]:
        return False
    if any(key not in {"rot", "flipH", "flipV"} for key in transform.attrib):
        return False
    try:
        if int(transform.get("rot", "0")) != 0:
            return False
        if any(transform.get(key) not in {None, "0", "false"} for key in ["flipH", "flipV"]):
            return False
        if kind == "grpSp":
            child_extent = transform.find("a:chExt", _NS)
            child_offset = transform.find("a:chOff", _NS)
            return (
                int(child_extent.get("cx")) > 0
                and int(child_extent.get("cy")) > 0
                and all(abs(int(child_offset.get(axis))) <= 2**31 - 1 for axis in ["x", "y"])
            )
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def native_children(node: Any) -> list[Any]:
    return [
        child
        for child in node
        if etree.QName(child).namespace == PRESENTATION_NS
        and etree.QName(child).localname in {"sp", "pic", "graphicFrame", "grpSp", "cxnSp"}
    ]


def group_reason(node: Any, root: Any, picture_ids: set[str], depth: int = 0) -> str | None:
    kind = etree.QName(node).localname
    if depth > 8 or kind not in {"sp", "pic", "graphicFrame", "grpSp"}:
        return "This group contains unsupported objects or nesting."
    if not simple_transform(node):
        return "Rotated, flipped or malformed group transforms are read-only."
    if kind == "graphicFrame" and node.find("a:graphic/a:graphicData/a:tbl", _NS) is not None:
        return "PowerPoint tables cannot join a native group."
    if node.xpath(".//*[@noGrp='1' or @noGrp='true' or @noUngrp='1' or @noUngrp='true']"):
        return "Native grouping locks prevent changing this membership."
    if kind == "grpSp" and node.xpath(
        "./p:nvGrpSpPr/p:cNvPr[@hidden='1' or @hidden='true'] | "
        "./p:nvGrpSpPr/p:cNvPr/a:hlinkClick | ./p:nvGrpSpPr/p:cNvPr/a:hlinkMouseOver",
        namespaces=_NS,
    ):
        return "Groups with inherited visibility or click actions are read-only."
    if has_unsafe_extensions(node):
        return "Placeholders and extended objects cannot join a native group."
    identity = node.xpath("./*/p:cNvPr/@id", namespaces=_NS)
    targets = root.xpath("./p:timing//@spid | .//a:stCxn/@id | .//a:endCxn/@id", namespaces=_NS)
    if len(identity) != 1 or identity[0] in targets:
        return "Connector or animation dependencies prevent native grouping."
    if kind == "grpSp":
        properties = node.find("p:grpSpPr", _NS)
        if properties is None or len(properties) != 1 or properties.attrib:
            return "Groups with inherited fills or effects are read-only."
        children = native_children(node)
        if any(
            child.tag
            not in {
                f"{{{PRESENTATION_NS}}}{name}"
                for name in ("nvGrpSpPr", "grpSpPr", "sp", "pic", "graphicFrame", "grpSp")
            }
            for child in node
        ):
            return "Groups containing unsupported or alternate-content children are read-only."
        if not 1 <= len(children) <= 20:
            return "A supported group contains between 1 and 20 direct objects."
        _, transform = read_geometry(node)
        child_offset, child_extent = transform.find("a:chOff", _NS), transform.find("a:chExt", _NS)
        left, top = int(child_offset.get("x")), int(child_offset.get("y"))
        right, bottom = left + int(child_extent.get("cx")), top + int(child_extent.get("cy"))
        for child in children:
            geometry, _ = read_geometry(child)
            if geometry is not None and (
                geometry.x_emu < left
                or geometry.y_emu < top
                or geometry.x_emu + geometry.width_emu > right
                or geometry.y_emu + geometry.height_emu > bottom
            ):
                return "Group child positions exceed its coordinate bounds."
        return next(
            (
                reason
                for child in children
                if (reason := group_reason(child, root, picture_ids, depth + 1))
            ),
            None,
        )
    if kind == "pic" and identity[0] not in picture_ids:
        return "Only embedded PNG and JPEG pictures can join this native group."
    if kind == "graphicFrame":
        geometry, _ = read_geometry(node)
        if geometry is None or not _graphic_frame_geometry_supported(node, geometry):
            return "Only supported native charts can join this group."
    if not _delete_geometry_candidate(
        root, node, kind=kind, ooxml_id=identity[0], geometry_editable=True
    ):
        return "This object has a grouping dependency."
    return None


def grouping_picture_ids(archive: Any, members: Any, root: Any, slide_part: str) -> set[str]:
    directory, filename = posixpath.split(slide_part)
    relationship_part = f"{directory}/_rels/{filename}.rels"
    if relationship_part not in members:
        return set()
    relationships = _relationships(_parse_xml_part(archive, members[relationship_part]))
    result = set()
    for picture in root.xpath(".//p:pic", namespaces=_NS):
        identities = picture.xpath("./p:nvPicPr/p:cNvPr/@id", namespaces=_NS)
        refs = picture.xpath("./p:blipFill/a:blip/@r:embed", namespaces=_NS)
        if len(identities) != 1 or len(refs) != 1:
            continue
        relationship = relationships.get(refs[0])
        if (
            not relationship
            or relationship[0] != f"{REL_NS}/image"
            or relationship[2].lower() != "internal"
        ):
            continue
        target = _resolve_internal_part(directory, relationship[1])
        if target not in members:
            continue
        with archive.open(target) as handle:
            header = handle.read(8)
        if header == b"\x89PNG\r\n\x1a\n" or header.startswith(b"\xff\xd8\xff"):
            result.add(identities[0])
    return result


def child_geometry(
    group: Any, child: Any, target: FidelityGeometry
) -> tuple[FidelityGeometry, FidelityGeometry]:
    """Group-internal coordinates for a slide-space target, and where they actually land.

    The target must lie inside the group's frame, so the group itself is unchanged. A
    scaled group may not reach every EMU; the nearest position within one child-unit
    step is used.
    """
    outer, transform = read_geometry(group)
    assert outer is not None
    if (
        target.x_emu < outer.x_emu
        or target.y_emu < outer.y_emu
        or target.x_emu + target.width_emu > outer.x_emu + outer.width_emu
        or target.y_emu + target.height_emu > outer.y_emu + outer.height_emu
    ):
        raise invalid_request("Keep an object inside its group's frame, or ungroup it first.")
    offset, extent = transform.find("a:chOff", _NS), transform.find("a:chExt", _NS)

    def inverse(value: int, axis: str, origin: int, size: int) -> int:
        child_size = int(extent.get("c" + axis))
        return int(offset.get(axis)) + ((value - origin) * child_size + size // 2) // size

    def around(base: int) -> list[int]:
        return [base + step for step in (0, -1, 1, -2, 2)]

    def candidates(value: int, axis: str, origin: int, size: int) -> list[int]:
        return around(inverse(value, axis, origin, size))

    _, child_transform = read_geometry(child)
    if child_transform is not None and _swaps_axes(child_transform):
        # Seed from the centre and swapped-axis sizes, then search the same neighbourhood.
        center_x = inverse(target.x_emu + target.width_emu // 2, "x", outer.x_emu, outer.width_emu)
        center_y = inverse(
            target.y_emu + target.height_emu // 2, "y", outer.y_emu, outer.height_emu
        )
        child_width = target.width_emu * int(extent.get("cy")) // outer.height_emu
        child_height = target.height_emu * int(extent.get("cx")) // outer.width_emu
        seeds = {
            "left": center_x - child_width // 2,
            "right": center_x - child_width // 2 + child_width,
            "top": center_y - child_height // 2,
            "bottom": center_y - child_height // 2 + child_height,
        }

        def candidates(value: int, axis: str, origin: int, size: int) -> list[int]:  # noqa: F811
            key = {
                ("x", target.x_emu): "left",
                ("x", target.x_emu + target.width_emu): "right",
                ("y", target.y_emu): "top",
                ("y", target.y_emu + target.height_emu): "bottom",
            }[(axis, value)]
            return around(seeds[key])

    tolerance = 1 + max(
        -(-outer.width_emu // int(extent.get("cx"))),
        -(-outer.height_emu // int(extent.get("cy"))),
    )
    probe = copy.deepcopy(child)
    _, probe_transform = read_geometry(probe)
    probe_offset = probe_transform.find("a:off", _NS)
    probe_extent = probe_transform.find("a:ext", _NS)
    best: tuple[int, FidelityGeometry, FidelityGeometry] | None = None
    for left in candidates(target.x_emu, "x", outer.x_emu, outer.width_emu):
        for right in candidates(target.x_emu + target.width_emu, "x", outer.x_emu, outer.width_emu):
            for top in candidates(target.y_emu, "y", outer.y_emu, outer.height_emu):
                for bottom in candidates(
                    target.y_emu + target.height_emu, "y", outer.y_emu, outer.height_emu
                ):
                    if right <= left or bottom <= top:
                        continue
                    probe_offset.set("x", str(left))
                    probe_offset.set("y", str(top))
                    probe_extent.set("cx", str(right - left))
                    probe_extent.set("cy", str(bottom - top))
                    landed = promoted_geometry(group, probe)
                    error = max(
                        abs(landed.x_emu - target.x_emu),
                        abs(landed.y_emu - target.y_emu),
                        abs(landed.width_emu - target.width_emu),
                        abs(landed.height_emu - target.height_emu),
                    )
                    if best is None or error < best[0]:
                        best = (
                            error,
                            FidelityGeometry(left, top, right - left, bottom - top),
                            landed,
                        )
                    if error == 0:
                        return best[1], best[2]
    if best is None or best[0] > tolerance:
        raise invalid_request("This scaled group cannot place the object at that position.")
    return best[1], best[2]


def _swaps_axes(transform: Any) -> bool:
    """PowerPoint scales a child rotated 45-135 or 225-315 degrees with swapped axes."""
    try:
        degrees = (int(transform.get("rot", "0")) // 60_000) % 360
    except ValueError:
        return False
    return 45 <= degrees < 135 or 225 <= degrees < 315


def promoted_geometry(group: Any, child: Any) -> FidelityGeometry:
    outer, transform = read_geometry(group)
    geometry, child_transform = read_geometry(child)
    assert outer is not None and geometry is not None
    offset, extent = transform.find("a:chOff", _NS), transform.find("a:chExt", _NS)

    def coordinate(value: int, axis: str, origin: int, size: int) -> int:
        denominator = int(extent.get("c" + axis))
        numerator = (value - int(offset.get(axis))) * size
        return origin + (numerator + denominator // 2) // denominator

    if child_transform is not None and _swaps_axes(child_transform):
        # The centre maps normally; the box takes the other axis' scale.
        center_x = coordinate(
            geometry.x_emu + geometry.width_emu // 2, "x", outer.x_emu, outer.width_emu
        )
        center_y = coordinate(
            geometry.y_emu + geometry.height_emu // 2, "y", outer.y_emu, outer.height_emu
        )
        width = (geometry.width_emu * outer.height_emu + int(extent.get("cy")) // 2) // int(
            extent.get("cy")
        )
        height = (geometry.height_emu * outer.width_emu + int(extent.get("cx")) // 2) // int(
            extent.get("cx")
        )
        return FidelityGeometry(center_x - width // 2, center_y - height // 2, width, height)
    left = coordinate(geometry.x_emu, "x", outer.x_emu, outer.width_emu)
    top = coordinate(geometry.y_emu, "y", outer.y_emu, outer.height_emu)
    right = coordinate(geometry.x_emu + geometry.width_emu, "x", outer.x_emu, outer.width_emu)
    bottom = coordinate(geometry.y_emu + geometry.height_emu, "y", outer.y_emu, outer.height_emu)
    return FidelityGeometry(left, top, right - left, bottom - top)
