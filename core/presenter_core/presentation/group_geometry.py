"""Native group eligibility and unrotated parent/child coordinate transforms."""

from __future__ import annotations

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


def _swaps_axes(transform: Any) -> bool:
    """PowerPoint scales a child rotated 45-135 or 225-315 degrees with swapped axes."""
    try:
        degrees = (int(transform.get("rot", "0")) // 60_000) % 360
    except ValueError:
        return False
    return 45 <= degrees < 135 or 225 <= degrees < 315


def _box_in_parent(group: Any, box: FidelityGeometry, swaps: bool) -> FidelityGeometry:
    """Map a box from a group's child space into the space the group itself lives in."""
    outer, transform = read_geometry(group)
    assert outer is not None
    offset, extent = transform.find("a:chOff", _NS), transform.find("a:chExt", _NS)

    def coordinate(value: int, axis: str, origin: int, size: int) -> int:
        denominator = int(extent.get("c" + axis))
        numerator = (value - int(offset.get(axis))) * size
        return origin + (numerator + denominator // 2) // denominator

    if swaps:
        # The centre maps normally; the box takes the other axis' scale.
        center_x = coordinate(box.x_emu + box.width_emu // 2, "x", outer.x_emu, outer.width_emu)
        center_y = coordinate(box.y_emu + box.height_emu // 2, "y", outer.y_emu, outer.height_emu)
        cx, cy = int(extent.get("cx")), int(extent.get("cy"))
        width = (box.width_emu * outer.height_emu + cy // 2) // cy
        height = (box.height_emu * outer.width_emu + cx // 2) // cx
        return FidelityGeometry(center_x - width // 2, center_y - height // 2, width, height)
    left = coordinate(box.x_emu, "x", outer.x_emu, outer.width_emu)
    top = coordinate(box.y_emu, "y", outer.y_emu, outer.height_emu)
    right = coordinate(box.x_emu + box.width_emu, "x", outer.x_emu, outer.width_emu)
    bottom = coordinate(box.y_emu + box.height_emu, "y", outer.y_emu, outer.height_emu)
    return FidelityGeometry(left, top, right - left, bottom - top)


def promoted_geometry(group: Any, child: Any) -> FidelityGeometry:
    """A direct child's box in the space its group lives in (slide space for top level)."""
    geometry, transform = read_geometry(child)
    assert geometry is not None
    return _box_in_parent(group, geometry, transform is not None and _swaps_axes(transform))


def group_chain(child: Any) -> list[Any]:
    """The child's ancestor groups, innermost first, up to (not including) spTree."""
    chain = []
    parent = child.getparent()
    while parent is not None and etree.QName(parent).localname == "grpSp":
        chain.append(parent)
        parent = parent.getparent()
    return chain


def slide_geometry(node: Any) -> FidelityGeometry:
    """A shape, picture or group's box on the slide through every enclosing group."""
    geometry, transform = read_geometry(node)
    assert geometry is not None
    swaps = (
        etree.QName(node).localname != "grpSp" and transform is not None and _swaps_axes(transform)
    )
    for group in group_chain(node):
        geometry = _box_in_parent(group, geometry, swaps)
        swaps = False  # groups in a movable chain are unrotated
    return geometry


def child_geometry(
    child: Any, target: FidelityGeometry
) -> tuple[FidelityGeometry, FidelityGeometry]:
    """Child-space coordinates for a slide-space target, and where they actually land.

    The target must lie inside the immediate group's frame, so no group changes. A scaled
    group may not reach every EMU; the nearest position within one unit step is used.
    """
    chain = group_chain(child)
    frame = slide_geometry(chain[0])
    if (
        target.x_emu < frame.x_emu
        or target.y_emu < frame.y_emu
        or target.x_emu + target.width_emu > frame.x_emu + frame.width_emu
        or target.y_emu + target.height_emu > frame.y_emu + frame.height_emu
    ):
        raise invalid_request("Keep an object inside its group's frame, or ungroup it first.")

    def inverse_point(x: int, y: int) -> tuple[int, int]:
        # Slide space to the child's own space, outermost group first.
        for group in reversed(chain):
            outer, transform = read_geometry(group)
            assert outer is not None
            offset, extent = transform.find("a:chOff", _NS), transform.find("a:chExt", _NS)
            x = (
                int(offset.get("x"))
                + ((x - outer.x_emu) * int(extent.get("cx")) + outer.width_emu // 2)
                // outer.width_emu
            )
            y = (
                int(offset.get("y"))
                + ((y - outer.y_emu) * int(extent.get("cy")) + outer.height_emu // 2)
                // outer.height_emu
            )
        return x, y

    def scale(axis: str) -> tuple[int, int]:
        # Child units per slide unit along an axis, as (numerator, denominator).
        numerator = denominator = 1
        for group in chain:
            outer, transform = read_geometry(group)
            assert outer is not None
            extent = transform.find("a:chExt", _NS)
            numerator *= int(extent.get("c" + axis))
            denominator *= outer.width_emu if axis == "x" else outer.height_emu
        return numerator, denominator

    _, transform = read_geometry(child)
    if transform is not None and _swaps_axes(transform):
        center = inverse_point(
            target.x_emu + target.width_emu // 2, target.y_emu + target.height_emu // 2
        )
        ny, dy = scale("y")
        nx, dx = scale("x")
        width, height = target.width_emu * ny // dy, target.height_emu * nx // dx
        seed_left, seed_top = center[0] - width // 2, center[1] - height // 2
        seed_right, seed_bottom = seed_left + width, seed_top + height
    else:
        seed_left, seed_top = inverse_point(target.x_emu, target.y_emu)
        seed_right, seed_bottom = inverse_point(
            target.x_emu + target.width_emu, target.y_emu + target.height_emu
        )
    tolerance = 1
    for axis in ("x", "y"):
        numerator, denominator = scale(axis)
        tolerance = max(tolerance, 1 + -(-denominator // numerator))
    offset, extent = transform.find("a:off", _NS), transform.find("a:ext", _NS)
    original = (offset.get("x"), offset.get("y"), extent.get("cx"), extent.get("cy"))
    steps = (0, -1, 1, -2, 2)
    best: tuple[int, FidelityGeometry, FidelityGeometry] | None = None
    try:
        for left in (seed_left + step for step in steps):
            for right in (seed_right + step for step in steps):
                for top in (seed_top + step for step in steps):
                    for bottom in (seed_bottom + step for step in steps):
                        if right <= left or bottom <= top:
                            continue
                        offset.set("x", str(left))
                        offset.set("y", str(top))
                        extent.set("cx", str(right - left))
                        extent.set("cy", str(bottom - top))
                        landed = slide_geometry(child)
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
    finally:
        # The search probes the real node (its ancestors matter); restore it.
        offset.set("x", original[0])
        offset.set("y", original[1])
        extent.set("cx", original[2])
        extent.set("cy", original[3])
    if best is None or best[0] > tolerance:
        raise invalid_request("This scaled group cannot place the object at that position.")
    return best[1], best[2]
