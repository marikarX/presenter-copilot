"""Reviewed native axes isolate chart appearance from workbook/data dependencies."""

from __future__ import annotations

import copy
import math
import re
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.charts import CNS, NS
from presenter_core.presentation.creation import PresentationCreationService
from presenter_core.presentation.fidelity import DRAWING_NS

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

TICKS = {"next_to": "nextTo", "low": "low", "high": "high", "none": "none"}
NUMBERS = {"minimum": "min", "maximum": "max", "major_unit": "majorUnit", "minor_unit": "minorUnit"}
ORDER = [
    "axId",
    "scaling",
    "delete",
    "axPos",
    "majorGridlines",
    "minorGridlines",
    "title",
    "numFmt",
    "majorTickMark",
    "minorTickMark",
    "tickLblPos",
    "spPr",
    "txPr",
    "crossAx",
    "crosses",
    "crossesAt",
    "auto",
    "lblAlgn",
    "lblOffset",
    "tickLblSkip",
    "tickMarkSkip",
    "noMultiLvlLbl",
    "crossBetween",
    "majorUnit",
    "minorUnit",
    "dispUnits",
    "extLst",
]
MANAGED = {
    "delete",
    "majorGridlines",
    "minorGridlines",
    "title",
    "numFmt",
    "tickLblPos",
    "majorUnit",
    "minorUnit",
}
FIELDS = {
    "axis_kind",
    "visible",
    "tick_labels",
    "major_gridlines",
    "minor_gridlines",
    "title",
    "number_format",
    *NUMBERS,
}


def _number(node: Any) -> float | None:
    if node is None:
        return None
    try:
        value = float(node.get("val"))
        return value if math.isfinite(value) and abs(value) <= 1e12 else None
    except (ValueError, TypeError):
        return None


def _title_editable(node: Any) -> bool:
    if node is None:
        return True
    # One native rich paragraph/run keeps its existing character/paragraph formatting.
    body = node.find("c:tx/c:rich", NS)
    return bool(
        body is not None
        and len(body.findall("a:p", NS)) == 1
        and len(body.findall("a:p/a:r", NS)) == 1
        and len(body.findall("a:p/a:r/a:t", NS)) == 1
        and not body.findall(".//a:fld", NS)
        and not body.findall(".//a:br", NS)
        and not node.findall("c:layout/c:manualLayout", NS)
        and not node.findall(".//c:extLst", NS)
    )


def inspect_axes(chart: Any) -> dict[str, Any]:
    plot = chart.find("c:chart/c:plotArea", NS)
    axes = (
        plot.xpath("c:catAx | c:valAx | c:dateAx | c:serAx", namespaces=NS)
        if plot is not None
        else []
    )
    reason = None
    if len(axes) != 2 or {etree.QName(a).localname for a in axes} != {"catAx", "valAx"}:
        reason = (
            "Only one category/value axis pair is editable; "
            "pie, date and secondary axes stay read-only."
        )
    ids = [a.find("c:axId", NS) for a in axes]
    values = [n.get("val", "") if n is not None else "" for n in ids]
    if len(set(values)) != len(values) or any(
        not re.fullmatch(r"-?[0-9]{1,10}", v) or not -(2**31) <= int(v) <= 2**32 - 1 for v in values
    ):
        reason = "Ambiguous native axis identities stay read-only."
    for a in axes:
        if a.attrib or any(len(a.findall("c:" + tag, NS)) > 1 for tag in ORDER):
            reason = "Ambiguous native axis properties stay read-only."
        if a.findall("c:extLst", NS) or any(
            v.tag not in {f"{{{CNS}}}{tag}" for tag in ORDER} for v in a
        ):
            reason = "Unsupported native axis extensions stay read-only."
        cross = a.find("c:crossAx", NS)
        own = a.find("c:axId", NS)
        if (
            cross is None
            or own is None
            or cross.get("val") not in values
            or cross.get("val") == own.get("val")
        ):
            reason = "The native axes are not an unambiguous connected pair."
        scaling = a.find("c:scaling", NS)
        if (
            scaling is None
            or scaling.attrib
            or scaling.findall("c:logBase", NS)
            or a.findall("c:dispUnits", NS)
        ):
            reason = "Logarithmic or display-unit axes need a separate scale editor."
        if scaling is not None:
            if any(
                v.tag not in {f"{{{CNS}}}{tag}" for tag in ["min", "max", "orientation"]}
                for v in scaling
            ) or any(
                len(scaling.findall("c:" + tag, NS)) > 1 for tag in ["min", "max", "orientation"]
            ):
                reason = "Unsupported native axis scaling stays read-only."
            for tag in ["min", "max"]:
                n = scaling.find("c:" + tag, NS)
                if n is not None and (_number(n) is None or set(n.attrib) != {"val"} or len(n)):
                    reason = "Unsupported native scale bounds stay read-only."
            minimum, maximum = (
                _number(scaling.find("c:min", NS)),
                _number(scaling.find("c:max", NS)),
            )
            if minimum is not None and maximum is not None and minimum >= maximum:
                reason = "Invalid native scale bounds stay read-only."
        for tag in ["majorUnit", "minorUnit"]:
            n = a.find("c:" + tag, NS)
            number = _number(n)
            if n is not None and (
                number is None or number <= 0 or set(n.attrib) != {"val"} or len(n)
            ):
                reason = "Unsupported native axis units stay read-only."
        for tag, allowed in [
            ("delete", {"0", "1", "true", "false"}),
            ("tickLblPos", set(TICKS.values())),
        ]:
            n = a.find("c:" + tag, NS)
            if n is not None and (
                set(n.attrib) != {"val"} or len(n) or n.get("val") not in allowed
            ):
                reason = "Unsupported native axis flags stay read-only."
        fmt = a.find("c:numFmt", NS)
        if fmt is not None and (
            set(fmt.attrib) - {"formatCode", "sourceLinked"}
            or len(fmt)
            or fmt.get("sourceLinked", "0") not in {"0", "1", "true", "false"}
        ):
            reason = "Unsupported native axis number formats stay read-only."
    refs = (
        [
            v
            for child in plot
            if etree.QName(child).localname.endswith("Chart")
            for v in child.xpath("c:axId/@val", namespaces=NS)
        ]
        if plot is not None
        else []
    )
    if sorted(refs) != sorted(values):
        reason = "The chart does not use exactly this axis pair."
    items = []
    for a in axes:
        kind = "category" if etree.QName(a).localname == "catAx" else "value"
        scaling = a.find("c:scaling", NS)
        fmt = a.find("c:numFmt", NS)
        title = a.find("c:title", NS)
        hidden = a.find("c:delete", NS)
        ticks = a.find("c:tickLblPos", NS)
        items.append(
            {
                "axis_kind": kind,
                "visible": hidden is None or hidden.get("val") not in {"1", "true"},
                "tick_labels": next(
                    (k for k, v in TICKS.items() if ticks is not None and ticks.get("val") == v),
                    "next_to",
                ),
                "major_gridlines": a.find("c:majorGridlines", NS) is not None,
                "minor_gridlines": a.find("c:minorGridlines", NS) is not None,
                "title": "".join(title.xpath(".//a:t/text()", namespaces=NS))
                if title is not None
                else "",
                "title_editable": _title_editable(title),
                "number_format": fmt.get("formatCode") if fmt is not None else None,
                **{
                    field: _number(
                        (scaling if field in {"minimum", "maximum"} else a).find("c:" + tag, NS)
                    )
                    if (scaling is not None or field not in {"minimum", "maximum"})
                    else None
                    for field, tag in NUMBERS.items()
                },
            }
        )
    return {"editable": reason is None, "reason": reason, "axes": items}


def validate_settings(params: dict[str, Any]) -> dict[str, Any]:
    result = {k: params.get(k) for k in FIELDS}
    if (
        not isinstance(result["axis_kind"], str)
        or result["axis_kind"] not in {"category", "value"}
        or not isinstance(result["tick_labels"], str)
        or result["tick_labels"] not in TICKS
        or any(
            type(result[k]) is not bool for k in ["visible", "major_gridlines", "minor_gridlines"]
        )
    ):
        raise invalid_request("Choose an axis, visibility, tick labels and gridlines.")
    for field in NUMBERS:
        n = result[field]
        if n is not None and (
            type(n) not in (int, float)
            or not math.isfinite(n)
            or abs(n) > 1e12
            or (field.endswith("unit") and n < 1e-9)
        ):
            raise invalid_request(
                "Use finite bounds within ±1 trillion and units from 0.000000001 to 1 trillion.",
                field=field,
            )
    lo, hi = result["minimum"], result["maximum"]
    if lo is not None and hi is not None and lo >= hi:
        raise invalid_request("Axis minimum must be less than maximum.")
    major, minor = result["major_unit"], result["minor_unit"]
    if major is not None and minor is not None and minor > major:
        raise invalid_request("Minor unit must not exceed major unit.")
    if result["axis_kind"] == "category" and (
        any(result[k] is not None for k in NUMBERS) or result["number_format"] is not None
    ):
        raise invalid_request("Numeric scaling and formatting apply to the value axis only.")
    for field, limit in [("title", 120), ("number_format", 64)]:
        if result[field] is not None:
            text = result[field]
            if isinstance(text, str) and any(c in text for c in "\n\r\t"):
                raise invalid_request(
                    "Use single-line axis titles and number formats.", field=field
                )
            result[field] = PresentationCreationService._text(
                result[field], field, limit, allow_empty=field == "title"
            )
    return result


def _insert(parent: Any, tag: str, order: list[str] = ORDER) -> Any:
    node = parent.find("c:" + tag, NS)
    if node is None:
        node = etree.Element(f"{{{CNS}}}{tag}")
        later = set(order[order.index(tag) + 1 :])
        parent.insert(
            next(
                (i for i, v in enumerate(parent) if etree.QName(v).localname in later), len(parent)
            ),
            node,
        )
    return node


def apply_axis(chart: Any, params: dict[str, Any]) -> bool:
    value = validate_settings(params)
    info = inspect_axes(chart)
    if not info["editable"]:
        raise CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", info["reason"])
    state = next(v for v in info["axes"] if v["axis_kind"] == value["axis_kind"])
    if value["title"] is not None and not state["title_editable"]:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "Complex axis titles stay intact; keep their title setting.",
        )
    desired = {
        **state,
        **{k: v for k, v in value.items() if k not in {"title", "number_format"} or v is not None},
    }
    # An explicit native number format also turns off source linking.
    axis = chart.find(
        "c:chart/c:plotArea/c:" + ("catAx" if value["axis_kind"] == "category" else "valAx"), NS
    )
    before = etree.tostring(chart, method="c14n")
    fmt = axis.find("c:numFmt", NS)
    if all(state[k] == desired[k] for k in value) and (
        value["number_format"] is None
        or fmt is not None
        and fmt.get("sourceLinked", "0") in {"0", "false"}
    ):
        return False
    _insert(axis, "delete").set("val", "0" if value["visible"] else "1")
    _insert(axis, "tickLblPos").set("val", TICKS[value["tick_labels"]])
    for field, tag in [
        ("major_gridlines", "majorGridlines"),
        ("minor_gridlines", "minorGridlines"),
    ]:
        n = axis.find("c:" + tag, NS)
        if value[field]:
            _insert(axis, tag)
        elif n is not None:
            axis.remove(n)
    if value["axis_kind"] == "value":
        for field, tag in NUMBERS.items():
            parent = axis.find("c:scaling", NS) if field in {"minimum", "maximum"} else axis
            n = parent.find("c:" + tag, NS)
            if value[field] is None:
                if n is not None:
                    parent.remove(n)
            else:
                _insert(
                    parent,
                    tag,
                    ["logBase", "orientation", "max", "min", "extLst"]
                    if parent is not axis
                    else ORDER,
                ).set("val", str(value[field]))
        if value["number_format"] is not None:
            fmt = _insert(axis, "numFmt")
            fmt.set("formatCode", value["number_format"])
            fmt.set("sourceLinked", "0")
    if value["title"] is not None and value["title"] != state["title"]:
        title = axis.find("c:title", NS)
        if not value["title"]:
            if title is not None:
                axis.remove(title)
        else:
            if title is None:
                title = _insert(axis, "title")
                tx = etree.SubElement(title, f"{{{CNS}}}tx")
                rich = etree.SubElement(tx, f"{{{CNS}}}rich")
                etree.SubElement(rich, f"{{{DRAWING_NS}}}bodyPr")
                etree.SubElement(rich, f"{{{DRAWING_NS}}}lstStyle")
                paragraph = etree.SubElement(rich, f"{{{DRAWING_NS}}}p")
                run = etree.SubElement(paragraph, f"{{{DRAWING_NS}}}r")
                etree.SubElement(run, f"{{{DRAWING_NS}}}t")
                etree.SubElement(title, f"{{{CNS}}}overlay", val="0")
            title.find("c:tx/c:rich/a:p/a:r/a:t", NS).text = value["title"]
    return bool(etree.tostring(chart, method="c14n") != before)


def set_chart_axis(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "object_id",
            "expected_fingerprint",
            *FIELDS,
        },
    )
    validate_settings(params)

    def mutate(chart: Any) -> bool:
        original = copy.deepcopy(chart)
        if not apply_axis(chart, params):
            return False
        compared = copy.deepcopy(chart)
        tag = "catAx" if params["axis_kind"] == "category" else "valAx"
        for tree in [original, compared]:
            axis = tree.find("c:chart/c:plotArea/c:" + tag, NS)
            for n in list(axis):
                if etree.QName(n).localname in MANAGED:
                    axis.remove(n)
            scaling = axis.find("c:scaling", NS)
            for n in list(scaling):
                if etree.QName(n).localname in {"min", "max"}:
                    scaling.remove(n)
        if etree.tostring(original, method="c14n") != etree.tostring(compared, method="c14n"):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Axis editing changed unrelated chart content.",
            )
        return True

    from presenter_core.presentation.chart_appearance import edit_chart_appearance

    return edit_chart_appearance(editor, params, mutate)
