"""Explicit native text-placeholder assignments; preserve content and identities."""

from __future__ import annotations

import copy
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request
from presenter_core.presentation.fidelity import _NS, _geometry_for_object

TEXT_TYPES = {"title", "ctrTitle", "subTitle", "body", "obj"}


def candidates(root: Any, slide: Any) -> list[dict[str, Any]]:
    dependent = set(root.xpath("./p:timing//@spid", namespaces=_NS)) | set(
        root.xpath(
            "./p:cSld/p:spTree//a:stCxn/@id | ./p:cSld/p:spTree//a:endCxn/@id",
            namespaces=_NS,
        )
    )
    objects = {obj.ooxml_id: obj for obj in slide.objects}
    result = []
    for shape in root.findall("p:cSld/p:spTree/p:sp", _NS):
        props = shape.find("p:nvSpPr/p:cNvPr", _NS)
        ph = shape.find("p:nvSpPr/p:nvPr/p:ph", _NS)
        obj = objects.get(props.get("id")) if props is not None else None
        if (
            obj is None
            or ph is None
            or ph.get("type", "obj") not in TEXT_TYPES
            or obj.ooxml_id in dependent
            or shape.find("p:txBody", _NS) is None
            or len(ph)
            or set(ph.attrib) - {"type", "idx", "sz", "orient"}
            or shape.xpath("./p:spPr/a:scene3d | ./p:spPr/a:sp3d", namespaces=_NS)
        ):
            continue
        result.append(
            {
                "object_id": obj.object_id,
                "name": obj.name,
                "type": ph.get("type", "obj"),
                "text": obj.text[:500],
            }
        )
    return result


def remap(
    root: Any, slide: Any, layout: dict[str, Any], mapping: Any, width: int, height: int
) -> dict[str, tuple[bytes, Any]]:
    if not isinstance(mapping, list) or not 1 <= len(mapping) <= 20:
        raise invalid_request("Map between one and twenty existing text placeholders.")
    if not layout["creation_supported"]:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED", "This layout has unsupported placeholder geometry."
        )
    eligible = {item["object_id"] for item in candidates(root, slide)}
    slots = {slot["placeholder_id"]: slot for slot in layout["_slots"]}
    objects = {obj.object_id: obj for obj in slide.objects}
    assignments = {}
    destinations = set()
    for item in mapping:
        if not isinstance(item, dict) or set(item) != {"object_id", "placeholder_id"}:
            raise invalid_request(
                "Each mapping needs an existing object and a native placeholder identity."
            )
        obj, slot = item["object_id"], item["placeholder_id"]
        if (
            not isinstance(obj, str)
            or not isinstance(slot, str)
            or obj not in eligible
            or slot not in slots
        ):
            raise invalid_request(
                "Choose an eligible existing placeholder and a slot in this layout."
            )
        if obj in assignments or slot in destinations:
            raise invalid_request("Each object and destination placeholder must be assigned once.")
        assignments[obj] = slots[slot]
        destinations.add(slot)
    tree = root.find("p:cSld/p:spTree", _NS)
    expected = {}
    for shape in tree.findall("p:sp", _NS):
        props = shape.find("p:nvSpPr/p:cNvPr", _NS)
        obj = next(
            (
                obj
                for obj in objects.values()
                if props is not None and obj.ooxml_id == props.get("id")
            ),
            None,
        )
        if obj is None or obj.object_id not in assignments:
            continue
        slot = assignments[obj.object_id]
        nv = shape.find("p:nvSpPr/p:nvPr", _NS)
        old = nv.find("p:ph", _NS)
        nv.replace(old, copy.deepcopy(slot["_placeholder"]))
        sp = shape.find("p:spPr", _NS)
        if sp is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED", "The existing placeholder has no shape properties."
            )
        previous = sp.find("a:xfrm", _NS)
        if previous is not None:
            sp.replace(previous, copy.deepcopy(slot["_transform"]))
        else:
            sp.insert(0, copy.deepcopy(slot["_transform"]))
        geometry, valid = _geometry_for_object(
            shape, kind="sp", shape_tree=tree, slide_width_emu=width, slide_height_emu=height
        )
        if not valid:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED", "The mapped placeholder geometry is unsupported."
            )
        expected[obj.object_id] = (etree.tostring(shape, method="c14n", exclusive=True), geometry)
    indices = [
        ph.get("idx", "0")
        for ph in tree.findall("p:sp/p:nvSpPr/p:nvPr/p:ph", _NS)
        if ph.get("type", "obj") in TEXT_TYPES
    ]
    if len(set(indices)) != len(indices):
        raise invalid_request(
            "The mapping would share a placeholder index with an unmapped object. "
            "Assign distinct slots."
        )
    return expected
