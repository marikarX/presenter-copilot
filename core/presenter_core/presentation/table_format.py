"""Explicit range formatting preserves native table text, dimensions and style references."""

from __future__ import annotations

import copy
import re
from typing import Any, cast

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import _NS, DRAWING_NS

FIELDS = {
    "bold",
    "italic",
    "underline",
    "font_size_pt",
    "font_color",
    "fill_color",
    "alignment",
    "vertical_alignment",
}
FILLS = {"noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"}
ALIGN = {"left": "l", "center": "ctr", "right": "r", "justify": "just"}
ANCHOR = {"top": "t", "center": "ctr", "bottom": "b"}


def validate_style(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise invalid_request("Provide table cell style settings.")
    reject_unknown_fields(value, FIELDS)
    style = {name: value.get(name) for name in sorted(FIELDS)}
    if not any(v is not None for v in style.values()):
        raise invalid_request("Choose at least one formatting change.")
    for name, v in style.items():
        if v is None:
            continue
        if name in {"bold", "italic", "underline"} and type(v) is not bool:
            raise invalid_request("Text emphasis must be a boolean or null.")
        if name == "font_size_pt" and (type(v) is not int or not 6 <= v <= 96):
            raise invalid_request("Choose a font size between 6 and 96 points.")
        if name in {"font_color", "fill_color"} and (
            not isinstance(v, str) or not re.fullmatch("#[0-9a-fA-F]{6}", v)
        ):
            raise invalid_request("Choose an opaque RGB color.")
        if name in {"alignment", "vertical_alignment"} and (
            not isinstance(v, str) or v not in (ALIGN if name == "alignment" else ANCHOR)
        ):
            raise invalid_request("Choose a supported cell alignment.")
    return style


def bounds(params: dict[str, Any], cells: list[list[Any]]) -> tuple[int, int, int, int]:
    values = tuple(
        params.get(name) for name in ["row_start", "row_end", "column_start", "column_end"]
    )
    if any(type(v) is not int for v in values):
        raise invalid_request("Cell range indexes must be integers.")
    a, b, c, d = cast(tuple[int, int, int, int], values)
    if not 0 <= a <= b < len(cells) or not 0 <= c <= d < len(cells[0]):
        raise invalid_request("The selected cell range is unavailable.")
    return a, b, c, d


def rgb(parent: Any) -> str | None:
    node = parent.find("a:solidFill/a:srgbClr", _NS) if parent is not None else None
    return (
        "#" + str(node.get("val")).upper()
        if node is not None
        and not len(node)
        and re.fullmatch("[0-9a-fA-F]{6}", node.get("val", ""))
        else None
    )


def describe(cell: Any) -> dict[str, Any]:
    paragraph = cell.find("a:txBody/a:p", _NS)
    ppr = paragraph.find("a:pPr", _NS)
    run = paragraph.find("a:r/a:rPr", _NS)
    default = ppr.find("a:defRPr", _NS) if ppr is not None else None
    props = run if run is not None else default

    def attr(name: str) -> Any:
        return (
            props.get(name, default.get(name) if default is not None else None)
            if props is not None
            else None
        )

    def boolean(name: str) -> bool | None:
        value = attr(name)
        return True if value in {"1", "true"} else False if value in {"0", "false"} else None

    size = attr("sz")
    tc = cell.find("a:tcPr", _NS)
    color = (
        rgb(run)
        if run is not None and any(etree.QName(v).localname in FILLS for v in run)
        else rgb(default)
    )
    return {
        "bold": boolean("b"),
        "italic": boolean("i"),
        "underline": None if attr("u") is None else attr("u") != "none",
        "font_size_pt": int(size) / 100
        if isinstance(size, str) and len(size) <= 10 and size.isascii() and size.isdigit()
        else None,
        "font_color": color,
        "fill_color": rgb(tc),
        "alignment": next(
            (k for k, v in ALIGN.items() if ppr is not None and ppr.get("algn") == v), None
        ),
        "vertical_alignment": next((k for k, v in ANCHOR.items() if tc.get("anchor") == v), None),
    }


def inspect_formatting(frame: Any) -> dict[str, Any]:
    rows = frame.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS)
    for row in rows:
        for cell in row.findall("a:tc", _NS):
            for paragraph in cell.findall("a:txBody/a:p", _NS):
                if any(
                    len(paragraph.findall(tag, _NS)) > 1
                    for tag in ["a:pPr", "a:endParaRPr", "a:pPr/a:defRPr"]
                ):
                    return {
                        "editable": False,
                        "reason": "Ambiguous native cell text properties stay read-only.",
                    }
    return {
        "editable": True,
        "reason": None,
        "cell_styles": [[describe(cell) for cell in row.findall("a:tc", _NS)] for row in rows],
    }


def previous_styles(info: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    if not info["editable"]:
        raise invalid_request(info["reason"])
    cells = info["cell_styles"]
    a, b, c, d = bounds(params, cells)
    fields = [
        name for name, value in validate_style(params.get("style")).items() if value is not None
    ]
    return {
        "cell_styles": [
            {"row": r, "column": col, "style": {name: cells[r][col][name] for name in fields}}
            for r in range(a, b + 1)
            for col in range(c, d + 1)
        ]
    }


def _color(parent: Any, color: str, *, cell: bool = False) -> None:
    fills = [
        v
        for v in parent
        if etree.QName(v).localname in FILLS and etree.QName(v).namespace == DRAWING_NS
    ]
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
                if (
                    etree.QName(v).localname in {"headers", "extLst"}
                    if cell
                    else etree.QName(v).localname != "ln"
                )
            ),
            len(parent),
        )
    )
    for node in fills:
        parent.remove(node)
    fill = etree.Element(f"{{{DRAWING_NS}}}solidFill")
    etree.SubElement(fill, f"{{{DRAWING_NS}}}srgbClr", val=color[1:].upper())
    parent.insert(index, fill)


def _font(parent: Any, style: dict[str, Any]) -> None:
    for name, attribute in [("bold", "b"), ("italic", "i"), ("font_size_pt", "sz")]:
        if style[name] is not None:
            parent.set(
                attribute, str(int(style[name]) if name != "font_size_pt" else style[name] * 100)
            )
    if style["underline"] is not None:
        current = parent.get("u")
        if not style["underline"]:
            parent.set("u", "none")
        elif current is None or current == "none":
            parent.set("u", "sng")
    if style["font_color"] is not None:
        _color(parent, style["font_color"])


def format_cells(frame: Any, params: dict[str, Any]) -> bool:
    info = inspect_formatting(frame)
    if not info["editable"]:
        raise CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", info["reason"])
    style = validate_style(params.get("style"))
    from presenter_core.presentation.table_merge import complete_range, layout

    a, b, c, d = complete_range(params, info["cell_styles"], layout(frame))
    original = bytes(etree.tostring(frame, method="c14n"))
    before = copy.deepcopy(frame)
    rows = frame.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS)
    text_change = any(
        style[n] is not None for n in ["bold", "italic", "underline", "font_size_pt", "font_color"]
    )
    for r in range(a, b + 1):
        for col in range(c, d + 1):
            cell = rows[r].findall("a:tc", _NS)[col]
            tc = cell.find("a:tcPr", _NS)
            if style["fill_color"] is not None:
                _color(tc, style["fill_color"], cell=True)
            if style["vertical_alignment"] is not None:
                tc.set("anchor", ANCHOR[style["vertical_alignment"]])
            for paragraph in cell.findall("a:txBody/a:p", _NS):
                ppr = paragraph.find("a:pPr", _NS)
                if text_change or style["alignment"] is not None:
                    if ppr is None:
                        ppr = etree.Element(f"{{{DRAWING_NS}}}pPr")
                        paragraph.insert(0, ppr)
                    if style["alignment"] is not None:
                        ppr.set("algn", ALIGN[style["alignment"]])
                if text_change:
                    default = ppr.find("a:defRPr", _NS)
                    if default is None:
                        default = etree.Element(f"{{{DRAWING_NS}}}defRPr")
                        ext = ppr.find("a:extLst", _NS)
                        ppr.insert(ppr.index(ext) if ext is not None else len(ppr), default)
                    _font(default, style)
                    for run in paragraph.findall("a:r", _NS):
                        props = run.find("a:rPr", _NS)
                        if props is None:
                            props = etree.Element(f"{{{DRAWING_NS}}}rPr")
                            run.insert(0, props)
                        _font(props, style)
                    end = paragraph.find("a:endParaRPr", _NS)
                    if end is None:
                        end = etree.SubElement(paragraph, f"{{{DRAWING_NS}}}endParaRPr")
                    _font(end, style)
    # Remove only the selected cells from both copies to prove other cells/geometry unchanged.
    compared = copy.deepcopy(frame)
    for tree in [before, compared]:
        rr = tree.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS)
        for r in range(a, b + 1):
            for cell in rr[r].findall("a:tc", _NS)[c : d + 1]:
                rr[r].remove(cell)
    if etree.tostring(before, method="c14n") != etree.tostring(compared, method="c14n"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_VALIDATION_FAILED", "Formatting changed other cells or geometry."
        )
    return original != bytes(etree.tostring(frame, method="c14n"))
