"""Explicit native series/point RGB colors preserve other chart and workbook content."""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.chart_structure import structure_reason
from presenter_core.presentation.charts import CNS, NS
from presenter_core.presentation.fidelity import DRAWING_NS

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

FILLS = {"noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"}


def nodes(chart: Any) -> list[Any]:
    return list(chart.findall("c:chart/c:plotArea/*/c:ser", NS))


def color_of(target: Any, *, outline: bool = False) -> str | None:
    location = "c:spPr/a:ln/a:solidFill/a:srgbClr" if outline else "c:spPr/a:solidFill/a:srgbClr"
    value = target.find(location, NS) if target is not None else None
    if (
        value is not None
        and not len(value)
        and re.fullmatch("[0-9A-Fa-f]{6}", value.get("val", ""))
    ):
        return "#" + str(value.get("val")).upper()
    return None


def inspect_colors(chart: Any, data: dict[str, Any]) -> dict[str, Any]:
    reason = structure_reason(chart, data)
    editable = reason is None
    series = []
    for i, node in enumerate(nodes(chart)):
        points = (
            {int(v.find("c:idx", NS).get("val")): v for v in node.findall("c:dPt", NS)}
            if editable
            else {}
        )
        series.append(
            {
                "name": data["series"][i]["name"],
                "color": color_of(node, outline=data["chart_type"] == "line"),
                "points": [
                    {"category": name, "color": color_of(points.get(j))}
                    for j, name in enumerate(data["categories"])
                ],
            }
        )
    return {
        "series_color_property": "outline" if data["chart_type"] == "line" else "fill_and_outline",
        "editable": editable,
        "reason": reason,
        "series": series,
        "series_editable": editable and data["chart_type"] not in {"pie", "doughnut"},
        "points_editable": editable and data["chart_type"] != "line",
    }


def _solid(parent: Any, color: str) -> None:
    fills = [v for v in parent if v.tag in {f"{{{DRAWING_NS}}}{tag}" for tag in FILLS}]
    if len(fills) > 1:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED", "Multiple native fills stay read-only."
        )
    index = (
        parent.index(fills[0])
        if fills
        else next(
            (
                i
                for i, v in enumerate(parent)
                if v.tag
                not in {f"{{{DRAWING_NS}}}{tag}" for tag in ["xfrm", "prstGeom", "custGeom"]}
            ),
            len(parent),
        )
    )
    for node in fills:
        parent.remove(node)
    fill = etree.Element(f"{{{DRAWING_NS}}}solidFill")
    etree.SubElement(fill, f"{{{DRAWING_NS}}}srgbClr", val=color)
    parent.insert(index, fill)


def apply_color(
    chart: Any, data: dict[str, Any], series_index: int, point_index: int | None, color: str
) -> bool:
    info = inspect_colors(chart, data)
    if (
        not info["editable"]
        or not info["series_editable" if point_index is None else "points_editable"]
    ):
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            info["reason"] or "Pie charts use point colors; line charts use series colors.",
        )
    if series_index >= len(data["series"]) or (
        point_index is not None and point_index >= len(data["categories"])
    ):
        raise invalid_request("The selected series or data point is unavailable.")
    series = nodes(chart)[series_index]
    before = copy.deepcopy(chart)
    target = series
    created = False
    if point_index is not None:
        target = next(
            (
                v
                for v in series.findall("c:dPt", NS)
                if v.find("c:idx", NS).get("val") == str(point_index)
            ),
            None,
        )
        if target is None:
            target = etree.Element(f"{{{CNS}}}dPt")
            etree.SubElement(target, f"{{{CNS}}}idx", val=str(point_index))
            index = next(
                (
                    i
                    for i, v in enumerate(series)
                    if etree.QName(v).localname
                    in {"dLbls", "trendline", "errBars", "cat", "val", "smooth", "extLst"}
                ),
                len(series),
            )
            series.insert(index, target)
            created = True
    props = target.findall("c:spPr", NS)
    if len(props) > 1:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED", "Multiple native shape styles stay read-only."
        )
    properties = props[0] if props else etree.Element(f"{{{CNS}}}spPr")
    if not props:
        if point_index is None:
            index = next(
                (
                    i
                    for i, v in enumerate(target)
                    if etree.QName(v).localname not in {"idx", "order", "tx"}
                ),
                len(target),
            )
        else:
            index = next(
                (
                    i
                    for i, v in enumerate(target)
                    if etree.QName(v).localname in {"pictureOptions", "extLst"}
                ),
                len(target),
            )
        target.insert(index, properties)
    if data["chart_type"] != "line":
        _solid(properties, color)
    lines = properties.findall("a:ln", NS)
    if len(lines) > 1:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED", "Multiple native outlines stay read-only."
        )
    line = lines[0] if lines else etree.Element(f"{{{DRAWING_NS}}}ln")
    if not lines:
        index = next(
            (
                i
                for i, v in enumerate(properties)
                if etree.QName(v).localname
                in {"effectLst", "effectDag", "scene3d", "sp3d", "extLst"}
            ),
            len(properties),
        )
        properties.insert(index, line)
    _solid(line, color)
    # Only the selected shape properties may differ; newly created dPt has only idx/spPr.
    stripped = copy.deepcopy(chart)
    original = nodes(before)[series_index]
    changed = nodes(stripped)[series_index]
    if point_index is not None:
        changed = next(
            v
            for v in changed.findall("c:dPt", NS)
            if v.find("c:idx", NS).get("val") == str(point_index)
        )
        if created:
            changed.getparent().remove(changed)
        else:
            original = next(
                v
                for v in original.findall("c:dPt", NS)
                if v.find("c:idx", NS).get("val") == str(point_index)
            )
    if not created:
        for node in [original, changed]:
            for prop in node.findall("c:spPr", NS):
                node.remove(prop)
    if etree.tostring(before, method="c14n") != etree.tostring(stripped, method="c14n"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_VALIDATION_FAILED", "Color editing changed other chart settings."
        )
    # Compare real original versus actual edited chart, before any stripping.
    return True


def set_chart_color(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
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
            "color",
        },
    )
    series = params.get("series_index")
    point = params.get("point_index")
    color = params.get("color")
    if (
        type(series) is not int
        or not 0 <= series < 6
        or (point is not None and (type(point) is not int or not 0 <= point < 24))
        or not isinstance(color, str)
        or not re.fullmatch("#[0-9A-Fa-f]{6}", color)
    ):
        raise invalid_request("Choose a valid series/data-point index and opaque RGB color.")
    from presenter_core.presentation.chart_appearance import edit_chart_appearance
    from presenter_core.presentation.charts import read_chart

    def mutate(chart: Any) -> bool:
        original = bytes(etree.tostring(chart, method="c14n"))
        data = read_chart(chart)
        assert data is not None
        apply_color(chart, data, series, point, color[1:].upper())
        return original != bytes(etree.tostring(chart, method="c14n"))

    return edit_chart_appearance(editor, params, mutate)


def previous_color(info: dict[str, Any], series: int, point: int | None) -> dict[str, Any]:
    if not info["editable"] or not info["series_editable" if point is None else "points_editable"]:
        raise invalid_request("The proposed chart color target is read-only.")
    if series >= len(info["series"]) or (
        point is not None and point >= len(info["series"][series]["points"])
    ):
        raise invalid_request("The proposed series or data point is unavailable.")
    item = info["series"][series]
    return {
        "series_index": series,
        "point_index": point,
        "color": item["color"] if point is None else item["points"][point]["color"],
    }
