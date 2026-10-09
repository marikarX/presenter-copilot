"""Explicit RGB solid/linear-gradient fills with per-stop native opacity."""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.chart_colors import FILLS, _solid, inspect_colors, nodes
from presenter_core.presentation.charts import CNS, NS
from presenter_core.presentation.fidelity import DRAWING_NS

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService


def validate_fill(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise invalid_request("Provide a solid or linear-gradient native fill.")
    kind = value.get("kind")
    stops: Any
    if kind == "solid":
        reject_unknown_fields(value, {"kind", "color", "opacity_percent"})
        stops = [value]
    elif kind == "linear_gradient":
        reject_unknown_fields(value, {"kind", "angle_degrees", "stops"})
        angle, stops = value.get("angle_degrees"), value.get("stops")
        if (
            type(angle) is not int
            or not 0 <= angle <= 359
            or not isinstance(stops, list)
            or not 2 <= len(stops) <= 8
        ):
            raise invalid_request(
                "Use an integer angle from 0 to 359 and two to eight gradient stops."
            )
        positions = []
        for stop in stops:
            if not isinstance(stop, dict):
                raise invalid_request("Each gradient stop must provide position, RGB and opacity.")
            reject_unknown_fields(stop, {"position_percent", "color", "opacity_percent"})
            position = stop.get("position_percent")
            if type(position) is not int or not 0 <= position <= 100:
                raise invalid_request(
                    "Gradient stop positions must be whole percentages from 0 to 100."
                )
            positions.append(position)
        if positions != sorted(set(positions)) or positions[0] != 0 or positions[-1] != 100:
            raise invalid_request("Gradient stops must increase strictly from 0 to 100 percent.")
    else:
        raise invalid_request("Choose a solid or linear-gradient fill.")
    for stop in stops:
        color, opacity = stop.get("color"), stop.get("opacity_percent")
        if (
            not isinstance(color, str)
            or not re.fullmatch("#[0-9A-Fa-f]{6}", color)
            or type(opacity) is not int
            or not 0 <= opacity <= 100
        ):
            raise invalid_request("Use #RRGGBB and a whole opacity percentage from 0 to 100.")
    result = copy.deepcopy(value)
    for stop in [result] if kind == "solid" else result["stops"]:
        stop["color"] = stop["color"].upper()
    return result


def _fills(parent: Any) -> list[Any]:
    return (
        [node for node in parent if node.tag in {f"{{{DRAWING_NS}}}{tag}" for tag in FILLS}]
        if parent is not None
        else []
    )


def _integer(value: str, limit: int) -> int | None:
    return (
        int(value)
        if 1 <= len(value) <= len(str(limit))
        and value.isascii()
        and value.isdigit()
        and int(value) <= limit
        else None
    )


def _rgb(parent: Any) -> dict[str, Any] | None:
    if parent is None or len(parent) != 1 or parent[0].tag != f"{{{DRAWING_NS}}}srgbClr":
        return None
    color = parent[0]
    if not re.fullmatch("[0-9A-Fa-f]{6}", color.get("val", "")):
        return None
    if not len(color):
        opacity = 100
    elif len(color) == 1 and color[0].tag == f"{{{DRAWING_NS}}}alpha":
        alpha = _integer(color[0].get("val", ""), 100000)
        if alpha is None or alpha % 1000:
            return None
        opacity = alpha // 1000
    else:
        return None
    return {"color": "#" + color.get("val").upper(), "opacity_percent": opacity}


def describe_fill(parent: Any) -> dict[str, Any]:
    fills = _fills(parent)
    if not fills:
        return {"kind": "native_default"}
    if len(fills) == 1:
        fill = fills[0]
        if fill.tag == f"{{{DRAWING_NS}}}solidFill":
            rgb = _rgb(fill)
            if rgb is not None:
                return {"kind": "solid", **rgb}
        if (
            fill.tag == f"{{{DRAWING_NS}}}gradFill"
            and fill.get("rotWithShape") == "1"
            and set(fill.attrib) == {"rotWithShape"}
            and [etree.QName(n).localname for n in fill] == ["gsLst", "lin"]
        ):
            angle = _integer(fill[1].get("ang", ""), 21599999)
            stops = []
            if (
                angle is not None
                and angle % 60000 == 0
                and fill[1].get("scaled", "1") == "1"
                and 2 <= len(fill[0]) <= 8
            ):
                for stop in fill[0]:
                    position = _integer(stop.get("pos", ""), 100000)
                    rgb = _rgb(stop)
                    if (
                        stop.tag != f"{{{DRAWING_NS}}}gs"
                        or position is None
                        or position % 1000
                        or rgb is None
                    ):
                        break
                    stops.append({"position_percent": position // 1000, **rgb})
                if len(stops) == len(fill[0]):
                    try:
                        return validate_fill(
                            {
                                "kind": "linear_gradient",
                                "angle_degrees": angle // 60000,
                                "stops": stops,
                            }
                        )
                    except CoreDomainError:
                        pass
    return {"kind": "native_custom"}


def _parent(target: Any, line: bool) -> Any:
    return target.find("c:spPr/a:ln" if line else "c:spPr", NS) if target is not None else None


def inspect_fills(chart: Any, data: dict[str, Any]) -> dict[str, Any]:
    colors = inspect_colors(chart, data)
    result = {k: colors[k] for k in ("editable", "reason", "series_editable", "points_editable")}
    line = data["chart_type"] == "line"
    series = []
    for index, node in enumerate(nodes(chart)):
        points = (
            {int(point.find("c:idx", NS).get("val")): point for point in node.findall("c:dPt", NS)}
            if colors["editable"]
            else {}
        )
        for target in [node, *points.values()]:
            props = target.findall("c:spPr", NS)
            if (
                len(props) > 1
                or (props and line and len(props[0].findall("a:ln", NS)) > 1)
                or len(_fills(_parent(target, line))) > 1
            ):
                result.update(
                    editable=False,
                    series_editable=False,
                    points_editable=False,
                    reason="Multiple native fill/style nodes stay read-only.",
                )
        series.append(
            {
                "name": data["series"][index]["name"],
                "fill": describe_fill(_parent(node, line)),
                "points": [
                    {"category": name, "fill": describe_fill(_parent(points.get(i), line))}
                    for i, name in enumerate(data["categories"])
                ],
            }
        )
    return {**result, "property": "stroke_fill" if line else "fill_only", "series": series}


def previous_fill(info: dict[str, Any], series: int, point: int | None) -> dict[str, Any]:
    if (
        not info["editable"]
        or not info["series_editable" if point is None else "points_editable"]
        or type(series) is not int
        or not 0 <= series < len(info["series"])
        or (
            point is not None
            and (type(point) is not int or not 0 <= point < len(info["series"][series]["points"]))
        )
    ):
        raise invalid_request("The proposed native chart fill target is unavailable or read-only.")
    item = info["series"][series]
    return {
        "series_index": series,
        "point_index": point,
        "fill": copy.deepcopy(item["fill"] if point is None else item["points"][point]["fill"]),
    }


def _target(chart: Any, series: int, point: int | None) -> Any:
    node = nodes(chart)[series]
    return (
        node
        if point is None
        else next(
            (p for p in node.findall("c:dPt", NS) if p.find("c:idx", NS).get("val") == str(point)),
            None,
        )
    )


def _native_fill(value: dict[str, Any]) -> Any:
    def rgb(parent: Any, stop: dict[str, Any]) -> None:
        color = etree.SubElement(parent, f"{{{DRAWING_NS}}}srgbClr", val=stop["color"][1:])
        etree.SubElement(color, f"{{{DRAWING_NS}}}alpha", val=str(stop["opacity_percent"] * 1000))

    if value["kind"] == "solid":
        fill = etree.Element(f"{{{DRAWING_NS}}}solidFill")
        rgb(fill, value)
    else:
        fill = etree.Element(f"{{{DRAWING_NS}}}gradFill", rotWithShape="1")
        stops = etree.SubElement(fill, f"{{{DRAWING_NS}}}gsLst")
        for stop in value["stops"]:
            rgb(
                etree.SubElement(
                    stops, f"{{{DRAWING_NS}}}gs", pos=str(stop["position_percent"] * 1000)
                ),
                stop,
            )
        etree.SubElement(
            fill, f"{{{DRAWING_NS}}}lin", ang=str(value["angle_degrees"] * 60000), scaled="1"
        )
    return fill


def apply_fill(
    chart: Any, data: dict[str, Any], series: int, point: int | None, value: Any
) -> bool:
    value = validate_fill(value)
    previous_fill(inspect_fills(chart, data), series, point)
    before = copy.deepcopy(chart)
    target = _target(chart, series, point)
    created = target is None
    if created:
        target = etree.Element(f"{{{CNS}}}dPt")
        etree.SubElement(target, f"{{{CNS}}}idx", val=str(point))
        owner = nodes(chart)[series]
        position = next(
            (
                i
                for i, child in enumerate(owner)
                if etree.QName(child).localname
                in {"dLbls", "trendline", "errBars", "cat", "val", "smooth", "extLst"}
            ),
            len(owner),
        )
        owner.insert(position, target)
    props = target.find("c:spPr", NS)
    added_props = props is None
    if added_props:
        props = etree.Element(f"{{{CNS}}}spPr")
        position = next(
            (
                i
                for i, child in enumerate(target)
                if (
                    etree.QName(child).localname not in {"idx", "order", "tx"}
                    if point is None
                    else etree.QName(child).localname in {"pictureOptions", "extLst"}
                )
            ),
            len(target),
        )
        target.insert(position, props)
    parent = props
    line = data["chart_type"] == "line"
    added_line = False
    if line:
        parent = props.find("a:ln", NS)
        added_line = parent is None
        if added_line:
            parent = etree.Element(f"{{{DRAWING_NS}}}ln")
            position = next(
                (
                    i
                    for i, child in enumerate(props)
                    if etree.QName(child).localname
                    in {"effectLst", "effectDag", "scene3d", "sp3d", "extLst"}
                ),
                len(props),
            )
            props.insert(position, parent)
    _solid(parent, "000000")
    parent.replace(parent.find("a:solidFill", NS), _native_fill(value))
    stripped = copy.deepcopy(chart)
    changed = _target(stripped, series, point)
    if created:
        changed.getparent().remove(changed)
    elif added_props:
        changed.remove(changed.find("c:spPr", NS))
    elif added_line:
        changed.find("c:spPr", NS).remove(_parent(changed, True))
    else:
        original_parent = _parent(_target(before, series, point), line)
        changed_parent = _parent(changed, line)
        for fill in _fills(changed_parent):
            changed_parent.remove(fill)
        for fill in _fills(original_parent):
            changed_parent.insert(original_parent.index(fill), copy.deepcopy(fill))
    if etree.tostring(before, method="c14n") != etree.tostring(stripped, method="c14n"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_VALIDATION_FAILED", "Fill editing changed other chart content."
        )
    return bool(etree.tostring(before, method="c14n") != etree.tostring(chart, method="c14n"))


def set_chart_fill(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "object_id",
            "expected_fingerprint",
            "series_index",
            "point_index",
            "fill",
        },
    )
    series, point = params.get("series_index"), params.get("point_index")
    if (
        type(series) is not int
        or not 0 <= series < 6
        or (point is not None and (type(point) is not int or not 0 <= point < 24))
    ):
        raise invalid_request("Choose valid native chart series/data-point indexes.")
    value = validate_fill(params.get("fill"))
    from presenter_core.presentation.chart_appearance import edit_chart_appearance
    from presenter_core.presentation.charts import read_chart

    def mutate(chart: Any) -> bool:
        data = read_chart(chart)
        assert data is not None
        return apply_fill(chart, data, series, point, value)

    return edit_chart_appearance(editor, params, mutate)
