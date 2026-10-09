"""Reviewed line-series marker symbol/size edits preserve other chart content."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.chart_colors import nodes
from presenter_core.presentation.chart_structure import structure_reason
from presenter_core.presentation.charts import CNS, NS

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

SYMBOLS = ("none", "circle", "square", "diamond", "triangle", "x", "plus", "star", "dot", "dash")


def inspect_markers(chart: Any, data: dict[str, Any]) -> dict[str, Any]:
    reason = structure_reason(chart, data)
    if data["chart_type"] != "line":
        reason = "Marker editing is available for ordinary native line charts."
    series = []
    for index, node in enumerate(nodes(chart)):
        markers = node.findall("c:marker", NS)
        marker = markers[0] if len(markers) == 1 else None
        symbols = marker.findall("c:symbol", NS) if marker is not None else []
        sizes = marker.findall("c:size", NS) if marker is not None else []
        symbol = symbols[0].get("val") if len(symbols) == 1 else None
        size = sizes[0].get("val", "") if len(sizes) == 1 else ""
        parsed_size = (
            int(size) if 1 <= len(size) <= 2 and size.isascii() and size.isdigit() else None
        )
        valid_size = parsed_size is not None and 2 <= parsed_size <= 72
        if (
            len(markers) > 1
            or len(symbols) > 1
            or len(sizes) > 1
            or (symbol is not None and symbol not in (*SYMBOLS, "picture", "auto"))
            or (sizes and not valid_size)
        ):
            reason = "Malformed native marker settings stay read-only."
        series.append(
            {
                "series_index": index,
                "name": data["series"][index]["name"],
                "marker_symbol": symbol,
                "marker_size": parsed_size if valid_size else None,
                "point_overrides": len(node.findall("c:dPt/c:marker", NS)),
            }
        )
    return {
        "editable": reason is None,
        "reason": reason,
        "symbols": list(SYMBOLS),
        "series": series,
    }


def previous_marker(info: dict[str, Any], index: int) -> dict[str, Any]:
    if not info["editable"] or type(index) is not int or not 0 <= index < len(info["series"]):
        raise invalid_request("The proposed line-chart marker series is read-only or unavailable.")
    return copy.deepcopy(info["series"][index])


def apply_marker(chart: Any, data: dict[str, Any], index: int, symbol: str, size: int) -> bool:
    if symbol not in SYMBOLS or type(size) is not int or not 2 <= size <= 72:
        raise invalid_request("Choose a native marker symbol and a size from 2 to 72 points.")
    previous_marker(inspect_markers(chart, data), index)
    before = copy.deepcopy(chart)
    series = nodes(chart)[index]
    marker = series.find("c:marker", NS)
    if marker is None:
        marker = etree.Element(f"{{{CNS}}}marker")
        position = next(
            (
                i
                for i, node in enumerate(series)
                if etree.QName(node).localname
                in {"dPt", "dLbls", "trendline", "errBars", "cat", "val", "smooth", "extLst"}
            ),
            len(series),
        )
        series.insert(position, marker)
    for tag, value in (("symbol", symbol), ("size", str(size))):
        child = marker.find(f"c:{tag}", NS)
        if child is None:
            child = etree.Element(f"{{{CNS}}}{tag}")
            marker.insert(0 if tag == "symbol" else len(marker.findall("c:symbol", NS)), child)
        child.set("val", value)
    # Prove all content outside the selected symbol/size is unchanged, including spPr.
    stripped = copy.deepcopy(chart)
    original_marker = nodes(before)[index].find("c:marker", NS)
    changed_marker = nodes(stripped)[index].find("c:marker", NS)
    if original_marker is None:
        changed_marker.getparent().remove(changed_marker)
    else:
        for tag in ("symbol", "size"):
            original_child = original_marker.find(f"c:{tag}", NS)
            changed_child = changed_marker.find(f"c:{tag}", NS)
            if original_child is None:
                changed_marker.remove(changed_child)
            else:
                changed_marker.replace(changed_child, copy.deepcopy(original_child))
    if etree.tostring(before, method="c14n") != etree.tostring(stripped, method="c14n"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_VALIDATION_FAILED", "Marker editing changed other settings."
        )
    return bool(etree.tostring(before, method="c14n") != etree.tostring(chart, method="c14n"))


def set_chart_marker(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
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
            "marker_symbol",
            "marker_size",
        },
    )
    index, symbol, size = (
        params.get("series_index"),
        params.get("marker_symbol"),
        params.get("marker_size"),
    )
    if (
        type(index) is not int
        or not 0 <= index < 6
        or not isinstance(symbol, str)
        or symbol not in SYMBOLS
        or type(size) is not int
        or not 2 <= size <= 72
    ):
        raise invalid_request(
            "Choose a valid line series, marker symbol and size from 2 to 72 points."
        )
    from presenter_core.presentation.chart_appearance import edit_chart_appearance
    from presenter_core.presentation.charts import read_chart

    def mutate(chart: Any) -> bool:
        data = read_chart(chart)
        assert data is not None
        return apply_marker(chart, data, index, symbol, size)

    return edit_chart_appearance(editor, params, mutate)
