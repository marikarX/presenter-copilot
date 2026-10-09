"""Insert/remove native categories and series with explicit formatting identities."""

from __future__ import annotations

import copy
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request
from presenter_core.presentation.charts import CNS, COLORS, NS
from presenter_core.presentation.fidelity import DRAWING_NS


def _index(node: Any) -> int | None:
    values = node.findall("c:idx", NS)
    value = values[0].get("val", "") if len(values) == 1 else ""
    return int(value) if len(value) <= 10 and value.isascii() and value.isdigit() else None


def structure_reason(chart: Any, data: dict[str, Any]) -> str | None:
    nodes = chart.findall("c:chart/c:plotArea/*/c:ser", NS)
    identities = [_index(node) for node in nodes]
    if any(v is None or v > 2**32 - 7 for v in identities) or len(set(identities)) != len(nodes):
        return "The native series identities are unsupported."
    for position, node in enumerate(nodes):
        order = node.findall("c:order", NS)
        if len(order) != 1 or order[0].get("val") != str(position):
            return "Charts with reordered native series need a separate structure editor."
    for container in chart.iter():
        for tag, limit in [
            ("dPt", len(data["categories"])),
            ("dLbl", len(data["categories"])),
            ("legendEntry", len(data["categories"]) if data["chart_type"] == "pie" else len(nodes)),
        ]:
            children = container.findall(f"c:{tag}", NS)
            ids = [_index(child) for child in children]
            if any(value is None or value >= limit for value in ids) or len(set(ids)) != len(ids):
                return "The native point, data-label or legend indexes are unsupported."
    if chart.findall(".//c:legendEntry", NS) and chart.findall(".//c:trendline", NS):
        return (
            "Charts combining custom legend entries and trendlines need separate structure review."
        )
    return None


def sources(value: Any, size: int, old_size: int, field: str) -> list[int | None]:
    if not isinstance(value, list) or len(value) != size:
        raise invalid_request(
            "Provide one original index or null per draft category/series.", field=field
        )
    retained = []
    for index in value:
        if index is not None:
            if type(index) is not int or not 0 <= index < old_size:
                raise invalid_request("An original chart index is out of bounds.", field=field)
            retained.append(index)
    if retained != sorted(set(retained)):
        raise invalid_request("Retained chart items must keep their original order.", field=field)
    return value


def _remap(container: Any, tag: str, mapping: list[int | None]) -> None:
    indexes = {old: new for new, old in enumerate(mapping) if old is not None}
    for node in list(container.findall(f"c:{tag}", NS)):
        old = _index(node)
        if old not in indexes:
            container.remove(node)
        else:
            node.find("c:idx", NS).set("val", str(indexes[old]))


def reshape_chart(
    chart: Any, old: dict[str, Any], data: dict[str, Any], params: dict[str, Any]
) -> None:
    reason = structure_reason(chart, old)
    if reason:
        raise CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", reason)
    categories = sources(
        params.get("category_sources"),
        len(data["categories"]),
        len(old["categories"]),
        "category_sources",
    )
    series_sources = sources(
        params.get("series_sources"), len(data["series"]), len(old["series"]), "series_sources"
    )
    nodes = chart.findall("c:chart/c:plotArea/*/c:ser", NS)
    plot = nodes[0].getparent()
    position = plot.index(nodes[0])
    next_id = max(_index(node) or 0 for node in nodes) + 1
    for node in nodes:
        plot.remove(node)
    for order, source in enumerate(series_sources):
        node = copy.deepcopy(nodes[source if source is not None else 0])
        node.find("c:order", NS).set("val", str(order))
        if source is None:
            node.find("c:idx", NS).set("val", str(next_id))
            next_id += 1
            # New series inherit plot defaults, never another series's per-point overrides.
            for tag in ["spPr", "dPt", "dLbls", "trendline", "errBars"]:
                for child in node.findall(f"c:{tag}", NS):
                    node.remove(child)
            marker = node.find("c:marker", NS)
            if marker is not None:
                for properties in marker.findall("c:spPr", NS):
                    marker.remove(properties)
            properties = etree.Element(f"{{{CNS}}}spPr")
            fill = etree.SubElement(properties, f"{{{DRAWING_NS}}}solidFill")
            etree.SubElement(fill, f"{{{DRAWING_NS}}}srgbClr", val=COLORS[order % len(COLORS)])
            line = etree.SubElement(properties, f"{{{DRAWING_NS}}}ln")
            fill = etree.SubElement(line, f"{{{DRAWING_NS}}}solidFill")
            etree.SubElement(fill, f"{{{DRAWING_NS}}}srgbClr", val=COLORS[order % len(COLORS)])
            tx = node.find("c:tx", NS)
            node.insert(node.index(tx) + 1, properties)
        else:
            _remap(node, "dPt", categories)
            for labels in node.findall("c:dLbls", NS):
                _remap(labels, "dLbl", categories)
        plot.insert(position + order, node)
    # Plot-level labels and legend entries follow category/series positions, not workbook columns.
    for labels in plot.findall("c:dLbls", NS):
        _remap(labels, "dLbl", categories)
    legend = chart.find("c:chart/c:legend", NS)
    if legend is not None:
        _remap(legend, "legendEntry", categories if old["chart_type"] == "pie" else series_sources)


def replace_cache(
    ref: Any, values: list[Any], *, structural: bool, mapping: list[int | None] | None = None
) -> None:
    cache = ref[-1]
    if not structural:
        for point, value in zip(cache.findall("c:pt", NS), values, strict=True):
            point.find("c:v", NS).text = str(value)
        return
    count = cache.find("c:ptCount", NS)
    count.set("val", str(len(values)))
    points = cache.findall("c:pt", NS)
    originals = {int(point.get("idx")): point for point in points}
    insert = cache.index(points[0]) if points else cache.index(count) + 1
    for point in points:
        cache.remove(point)
    for index, value in enumerate(values):
        source = mapping[index] if mapping is not None else None
        original = originals.get(source) if source is not None else None
        point = copy.deepcopy(original) if original is not None else etree.Element(f"{{{CNS}}}pt")
        point.set("idx", str(index))
        text = point.find("c:v", NS)
        if text is None:
            text = etree.SubElement(point, f"{{{CNS}}}v")
        text.text = str(value)
        cache.insert(insert + index, point)
