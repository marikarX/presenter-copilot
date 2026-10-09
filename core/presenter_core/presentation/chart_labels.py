"""Native data-label edits preserve workbook, custom text and label decoration."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.chart_structure import structure_reason
from presenter_core.presentation.charts import CNS, NS, read_chart

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

FLAGS = {
    "show_value": "showVal",
    "show_category": "showCatName",
    "show_series": "showSerName",
    "show_percent": "showPercent",
}
POSITIONS = {
    "center": "ctr",
    "inside_end": "inEnd",
    "inside_base": "inBase",
    "outside_end": "outEnd",
    "best_fit": "bestFit",
    "above": "t",
    "below": "b",
    "left": "l",
    "right": "r",
}
ALLOWED = {
    "column": ["default", "center", "inside_end", "inside_base", "outside_end"],
    "bar": ["default", "center", "inside_end", "inside_base", "outside_end"],
    "line": ["default", "center", "above", "below", "left", "right"],
    "pie": ["default", "center", "inside_end", "outside_end", "best_fit"],
}
ORDER = [
    "idx",
    "dLbl",
    "delete",
    "layout",
    "tx",
    "numFmt",
    "spPr",
    "txPr",
    "dLblPos",
    "showLegendKey",
    "showVal",
    "showCatName",
    "showSerName",
    "showPercent",
    "showBubbleSize",
    "separator",
    "showLeaderLines",
    "leaderLines",
    "extLst",
]
MANAGED = {"delete", "dLblPos", "numFmt", *FLAGS.values()}


def series_nodes(chart: Any) -> list[Any]:
    return list(chart.findall("c:chart/c:plotArea/*/c:ser", NS))


def _bool(parent: Any, tag: str, default: bool) -> bool:
    node = parent.find("c:" + tag, NS) if parent is not None else None
    return node.get("val", "1") in {"1", "true"} if node is not None else default


def _state(parent: Any, inherited: dict[str, Any] | None = None) -> dict[str, Any]:
    base = inherited or {
        "position": "hidden",
        **{field: False for field in FLAGS},
        "number_format": None,
    }
    state: dict[str, Any] = {field: _bool(parent, tag, base[field]) for field, tag in FLAGS.items()}
    pos = parent.find("c:dLblPos", NS) if parent is not None else None
    fmt = parent.find("c:numFmt", NS) if parent is not None else None
    state["number_format"] = fmt.get("formatCode") if fmt is not None else base["number_format"]
    hidden = _bool(
        parent,
        "delete",
        base["position"] == "hidden"
        and not any(state[field] for field in FLAGS)
        and (parent is None or parent.find("c:tx", NS) is None),
    )
    state["position"] = (
        "hidden"
        if hidden
        else next(
            (
                key
                for key, value in POSITIONS.items()
                if pos is not None and pos.get("val") == value
            ),
            "default" if base["position"] == "hidden" else base["position"],
        )
    )
    return state


def _point_nodes(container: Any) -> dict[int, Any]:
    return (
        {
            int(point.find("c:idx", NS).get("val")): point
            for point in container.findall("c:dLbl", NS)
        }
        if container is not None
        else {}
    )


def _ensure_labels(series: Any, *, create: bool = False) -> Any:
    inherited = _point_nodes(series.getparent().find("c:dLbls", NS))
    labels = series.find("c:dLbls", NS)
    if labels is None and (create or inherited):
        labels = etree.Element(f"{{{CNS}}}dLbls")
        later = {"trendline", "errBars", "cat", "val", "smooth", "extLst"}
        series.insert(
            next(
                (i for i, v in enumerate(series) if etree.QName(v).localname in later), len(series)
            ),
            labels,
        )
    if labels is not None:
        existing = _point_nodes(labels)
        for index, point in inherited.items():
            if index not in existing:
                labels.insert(len(labels.findall("c:dLbl", NS)), copy.deepcopy(point))
    return labels


def inspect_labels(chart: Any, data: dict[str, Any]) -> dict[str, Any]:
    reason = structure_reason(chart, data)
    containers = chart.findall(".//c:dLbls", NS)
    for node in containers:
        if node.attrib or any(
            child.tag not in {f"{{{CNS}}}{tag}" for tag in ORDER} for child in node
        ):
            reason = "Unsupported native label settings stay read-only."
        if any(len(node.findall("c:" + tag, NS)) > 1 for tag in ORDER if tag != "dLbl"):
            reason = "Ambiguous native label properties stay read-only."
        for target in [node, *node.findall("c:dLbl", NS)]:
            if any(len(target.findall("c:" + tag, NS)) > 1 for tag in MANAGED):
                reason = "Ambiguous native label properties stay read-only."
            layout = target.find("c:layout", NS)
            if layout is not None and (layout.attrib or len(layout)):
                reason = "Labels with manual layouts need a separate layout editor."
            for tag in {"delete", *FLAGS.values()}:
                value = target.find("c:" + tag, NS)
                if value is not None and (
                    set(value.attrib) - {"val"}
                    or len(value)
                    or value.get("val", "1") not in {"0", "1", "false", "true"}
                ):
                    reason = "Unsupported native label flags stay read-only."
            pos = target.find("c:dLblPos", NS)
            if pos is not None and (
                set(pos.attrib) != {"val"} or len(pos) or pos.get("val") not in POSITIONS.values()
            ):
                reason = "Unsupported native label placement stays read-only."
    nodes = series_nodes(chart)
    if any(len(node.findall("c:dLbls", NS)) > 1 for node in [nodes[0].getparent(), *nodes]):
        reason = "Ambiguous native label containers stay read-only."
    # Invalid native indexes are never interpreted even for display metadata.
    if reason:
        return {
            "editable": False,
            "reason": reason,
            "positions": ALLOWED[data["chart_type"]],
            "series": [],
        }
    global_labels = nodes[0].getparent().find("c:dLbls", NS)
    inherited = _state(global_labels)
    series = []
    for index, node in enumerate(nodes):
        labels = node.find("c:dLbls", NS)
        state = _state(labels, inherited)
        points = {**_point_nodes(global_labels), **_point_nodes(labels)}
        series.append(
            {
                "name": data["series"][index]["name"],
                **state,
                "points": [
                    {
                        "index": int(point.find("c:idx", NS).get("val")),
                        **_state(point, state),
                        "custom_text": point.find("c:tx", NS) is not None,
                    }
                    for point in points.values()
                ],
            }
        )
    return {
        "editable": True,
        "reason": None,
        "positions": ALLOWED[data["chart_type"]],
        "series": series,
    }


def targets(info: dict[str, Any], index: Any) -> list[int]:
    if not info["editable"]:
        raise CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", info["reason"])
    if index is None:
        return list(range(len(info["series"])))
    if type(index) is not int or not 0 <= index < len(info["series"]):
        raise invalid_request("Choose an available chart series.")
    return [index]


def previous_labels(info: dict[str, Any], index: Any) -> dict[str, Any]:
    return {
        "label_series": [
            {"series_index": i, **copy.deepcopy(info["series"][i])} for i in targets(info, index)
        ]
    }


def validate(params: dict[str, Any], kind: str) -> None:
    if params.get("position") not in ["hidden", *ALLOWED[kind]]:
        raise invalid_request("Choose a supported label placement for this chart.")
    if any(type(params.get(field)) is not bool for field in FLAGS):
        raise invalid_request("Choose explicit label content flags.")
    if params["position"] != "hidden" and not any(params[field] for field in FLAGS):
        raise invalid_request("Choose at least one label content field.")
    if params["show_percent"] and kind != "pie":
        raise invalid_request("Percentage labels are supported on pie charts.")
    fmt = params.get("number_format")
    if fmt is not None and (
        not isinstance(fmt, str)
        or not 1 <= len(fmt) <= 64
        or any(ord(v) < 32 or 0xD800 <= ord(v) <= 0xDFFF for v in fmt)
    ):
        raise invalid_request(
            "Provide a native number format of 1-64 characters, or null to retain it."
        )


def _set(parent: Any, tag: str, attributes: dict[str, str] | None) -> None:
    node = parent.find("c:" + tag, NS)
    if attributes is None:
        if node is not None:
            parent.remove(node)
        return
    if node is None:
        node = etree.Element(f"{{{CNS}}}{tag}")
        rank = ORDER.index(tag)
        parent.insert(
            next(
                (
                    i
                    for i, v in enumerate(parent)
                    if etree.QName(v).localname in ORDER
                    and ORDER.index(etree.QName(v).localname) > rank
                ),
                len(parent),
            ),
            node,
        )
    for key, value in attributes.items():
        node.set(key, value)


def apply_labels(chart: Any, params: dict[str, Any]) -> bool:
    data = read_chart(chart)
    assert data is not None
    info = inspect_labels(chart, data)
    indexes = targets(info, params.get("series_index"))
    validate(params, data["chart_type"])
    before = copy.deepcopy(chart)
    original = bytes(etree.tostring(chart, method="c14n"))
    nodes = series_nodes(chart)
    for index in indexes:
        if (
            params["position"] == "hidden"
            and info["series"][index]["position"] == "hidden"
            and all(p["position"] == "hidden" for p in info["series"][index]["points"])
        ):
            continue
        series = nodes[index]
        labels = _ensure_labels(series, create=True)
        for target in [labels, *labels.findall("c:dLbl", NS)]:
            _set(target, "delete", {"val": "1" if params["position"] == "hidden" else "0"})
            if params["position"] == "hidden":
                continue
            _set(
                target,
                "dLblPos",
                None if params["position"] == "default" else {"val": POSITIONS[params["position"]]},
            )
            for field, tag in FLAGS.items():
                _set(target, tag, {"val": "1" if params[field] else "0"})
            if params.get("number_format") is not None:
                _set(target, "numFmt", {"formatCode": params["number_format"], "sourceLinked": "0"})
    # Strip selected managed settings on both copies; new empty label containers disappear.
    compared = copy.deepcopy(chart)
    for tree in [before, compared]:
        for index in indexes:
            series = series_nodes(tree)[index]
            _ensure_labels(series)
            for labels in series.findall("c:dLbls", NS):
                for target in [labels, *labels.findall("c:dLbl", NS)]:
                    for tag in MANAGED:
                        for node in target.findall("c:" + tag, NS):
                            target.remove(node)
                if not len(labels) and not labels.attrib:
                    series.remove(labels)
    if etree.tostring(before, method="c14n") != etree.tostring(compared, method="c14n"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_VALIDATION_FAILED", "Label editing changed other chart settings."
        )
    return original != bytes(etree.tostring(chart, method="c14n"))


def set_chart_labels(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
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
            "position",
            "number_format",
            *FLAGS,
        },
    )
    from presenter_core.presentation.chart_appearance import edit_chart_appearance

    return edit_chart_appearance(editor, params, lambda chart: apply_labels(chart, params))
