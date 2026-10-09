"""Explicit range borders synchronize shared edges without touching cell content."""

from __future__ import annotations

import copy
import math
import re
from typing import Any, cast

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request
from presenter_core.presentation.fidelity import _NS, DRAWING_NS
from presenter_core.presentation.table_format import bounds, rgb

SIDES = {"left": "lnL", "right": "lnR", "top": "lnT", "bottom": "lnB"}
PRESETS = {"all", "outline", "inside", "horizontal", "vertical", "top", "bottom", "left", "right"}
STYLES = {"solid": "solid", "dash": "dash", "dot": "sysDot"}
FIELDS = {"border_scope", "line_style", "width_pt", "color"}


def validate_border(params: dict[str, Any]) -> dict[str, Any]:
    result = {k: params.get(k) for k in FIELDS}
    scope, style = result["border_scope"], result["line_style"]
    if (
        not isinstance(scope, str)
        or scope not in PRESETS
        or not isinstance(style, str)
        or style not in {*STYLES, "none"}
    ):
        raise invalid_request("Choose border edges and solid, dash, dot or none.")
    width, color = result["width_pt"], result["color"]
    if style == "none":
        if width is not None or color is not None:
            raise invalid_request("Removed borders use null width and color.")
    elif (
        type(width) not in (int, float)
        or not math.isfinite(cast(float, width))
        or not 0.25 <= cast(float, width) <= 12
        or not isinstance(color, str)
        or not re.fullmatch("#[0-9a-fA-F]{6}", color)
    ):
        raise invalid_request("Choose a 0.25–12 point border and opaque RGB color.")
    return result


def selected_edges(params: dict[str, Any], cells: list[list[Any]]) -> list[tuple[int, int, str]]:
    a, b, c, d = bounds(params, cells)
    scope = validate_border(params)["border_scope"]
    edges: set[tuple[int, int, str]] = set()

    def add(row: int, column: int, side: str) -> None:
        if 0 <= row < len(cells) and 0 <= column < len(cells[0]):
            edges.add((row, column, side))
            rr, cc, other = {
                "left": (row, column - 1, "right"),
                "right": (row, column + 1, "left"),
                "top": (row - 1, column, "bottom"),
                "bottom": (row + 1, column, "top"),
            }[side]
            if 0 <= rr < len(cells) and 0 <= cc < len(cells[0]):
                edges.add((rr, cc, other))

    for row in range(a, b + 1):
        for column in range(c, d + 1):
            for side in SIDES:
                exterior = {
                    "top": row == a,
                    "bottom": row == b,
                    "left": column == c,
                    "right": column == d,
                }[side]
                wanted = (
                    scope == "all"
                    or scope == "outline"
                    and exterior
                    or scope == "inside"
                    and not exterior
                    or scope == side
                    and exterior
                    or scope == "horizontal"
                    and side in {"top", "bottom"}
                    and not exterior
                    or scope == "vertical"
                    and side in {"left", "right"}
                    and not exterior
                )
                if wanted:
                    add(row, column, side)
    if not edges:
        raise invalid_request("This range has no requested interior borders.")
    return sorted(edges)


def describe_line(cell: Any, side: str) -> dict[str, Any]:
    line = cell.find("a:tcPr/a:" + SIDES[side], _NS)
    if line is None:
        return {
            "source": "inherited",
            "visible": None,
            "width_pt": None,
            "color": None,
            "line_style": None,
        }
    width = line.get("w", "")
    dash = line.find("a:prstDash", _NS)
    hidden = line.find("a:noFill", _NS) is not None
    return {
        "source": "native",
        "visible": not hidden,
        "width_pt": int(width) / 12700 if re.fullmatch("[0-9]{1,10}", width) else None,
        "color": rgb(line),
        "line_style": "none"
        if hidden
        else next(
            (k for k, v in STYLES.items() if dash is not None and dash.get("val") == v),
            "solid" if dash is None and line.find("a:custDash", _NS) is None else "other",
        ),
    }


def inspect_borders(frame: Any) -> dict[str, Any]:
    from presenter_core.presentation.table_merge import layout

    rows = frame.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS)
    if any(
        len(cell.findall("a:tcPr/a:" + tag, _NS)) > 1
        for row in rows
        for cell in row.findall("a:tc", _NS)
        for tag in SIDES.values()
    ):
        return {"editable": False, "reason": "Ambiguous native border properties stay read-only."}
    return {
        "editable": True,
        "reason": None,
        "spans": layout(frame),
        "cell_borders": [
            [
                {side: describe_line(cell, side) for side in SIDES}
                for cell in row.findall("a:tc", _NS)
            ]
            for row in rows
        ],
    }


def previous_borders(info: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    if not info["editable"]:
        raise invalid_request(info["reason"])
    cells = info["cell_borders"]
    return {
        "border_edges": [
            {"row": r, "column": c, "side": side, **cells[r][c][side]}
            for r, c, side in logical_edges(params, info)
        ]
    }


def logical_edges(params: dict[str, Any], info: dict[str, Any]) -> list[tuple[int, int, str]]:
    from presenter_core.presentation.table_merge import complete_range

    if not info["spans"]["regions"]:
        return selected_edges(params, info["cell_borders"])
    owners = info["spans"]["owners"]
    a, b, c, d = complete_range(params, owners, info["spans"])
    scope = validate_border(params)["border_scope"]
    edges = set()
    for r in range(a, b + 1):
        for col in range(c, d + 1):
            rr, cc, h, w = owners[r][col]
            if (r, col) != (rr, cc):
                continue
            for side in SIDES:
                exterior = {
                    "top": r == a,
                    "bottom": r + h - 1 == b,
                    "left": col == c,
                    "right": col + w - 1 == d,
                }[side]
                wanted = (
                    scope == "all"
                    or scope == "outline"
                    and exterior
                    or scope == "inside"
                    and not exterior
                    or scope == side
                    and exterior
                    or scope == "horizontal"
                    and side in {"top", "bottom"}
                    and not exterior
                    or scope == "vertical"
                    and side in {"left", "right"}
                    and not exterior
                )
                if not wanted:
                    continue
                edges.add((r, col, side))
                neighbors = (
                    {
                        "left": [(v, col - 1) for v in range(r, r + h)],
                        "right": [(v, col + w) for v in range(r, r + h)],
                        "top": [(r - 1, v) for v in range(col, col + w)],
                        "bottom": [(r + h, v) for v in range(col, col + w)],
                    }
                )[side]
                for nr, nc in neighbors:
                    if not 0 <= nr < len(owners) or not 0 <= nc < len(owners[0]):
                        continue
                    ar, ac, ah, aw = owners[nr][nc]
                    if (
                        side in {"left", "right"}
                        and not r <= ar <= ar + ah - 1 < r + h
                        or side in {"top", "bottom"}
                        and not col <= ac <= ac + aw - 1 < col + w
                    ):
                        raise invalid_request(
                            "This edge covers part of a neighboring merged cell. "
                            "Split that cell before changing this border."
                        )
                    edges.add(
                        (
                            ar,
                            ac,
                            {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}[
                                side
                            ],
                        )
                    )
    if not edges:
        raise invalid_request("This range has no requested visible interior borders.")
    return sorted(edges)


def set_borders(frame: Any, params: dict[str, Any]) -> bool:
    info = inspect_borders(frame)
    if not info["editable"]:
        raise CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", info["reason"])
    value = validate_border(params)
    edges = logical_edges(params, info)
    original_xml = bytes(etree.tostring(frame, method="c14n"))
    before = copy.deepcopy(frame)
    rows = frame.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS)
    order = [
        "lnL",
        "lnR",
        "lnT",
        "lnB",
        "lnTlToBr",
        "lnBlToTr",
        "cell3D",
        "noFill",
        "solidFill",
        "gradFill",
        "blipFill",
        "pattFill",
        "grpFill",
        "headers",
        "extLst",
    ]
    for r, c, side in edges:
        tc = rows[r].findall("a:tc", _NS)[c].find("a:tcPr", _NS)
        tag = SIDES[side]
        old = tc.find("a:" + tag, _NS)
        if old is not None:
            tc.remove(old)
        line = etree.Element(f"{{{DRAWING_NS}}}{tag}")
        if value["line_style"] == "none":
            etree.SubElement(line, f"{{{DRAWING_NS}}}noFill")
        else:
            line.set("w", str(round(value["width_pt"] * 12700)))
            fill = etree.SubElement(line, f"{{{DRAWING_NS}}}solidFill")
            etree.SubElement(fill, f"{{{DRAWING_NS}}}srgbClr", val=value["color"][1:].upper())
            etree.SubElement(line, f"{{{DRAWING_NS}}}prstDash", val=STYLES[value["line_style"]])
        later = set(order[order.index(tag) + 1 :])
        tc.insert(
            next((i for i, v in enumerate(tc) if etree.QName(v).localname in later), len(tc)), line
        )
    # Strip only managed side nodes, including the reciprocal neighbor edges, to
    # prove every cell's text/fill/other edges, geometry and table style unchanged.
    compared = copy.deepcopy(frame)
    for tree in [before, compared]:
        rr = tree.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS)
        for r, c, side in edges:
            tc = rr[r].findall("a:tc", _NS)[c].find("a:tcPr", _NS)
            for n in tc.findall("a:" + SIDES[side], _NS):
                tc.remove(n)
    if etree.tostring(before, method="c14n") != etree.tostring(compared, method="c14n"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_VALIDATION_FAILED",
            "Borders changed other cell properties or geometry.",
        )
    # Compare unstripped source to result for semantic no-op detection.
    return bool(etree.tostring(frame, method="c14n") != original_xml)
