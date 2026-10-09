"""Native rectangular spans retain the grid, cell styling and paragraph runs."""

from __future__ import annotations

import copy
import re
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request
from presenter_core.presentation.fidelity import _NS, DRAWING_NS
from presenter_core.presentation.table_format import bounds

ATTRS = {"rowSpan", "gridSpan", "hMerge", "vMerge"}


def grid(frame: Any) -> list[list[Any]]:
    return [
        r.findall("a:tc", _NS) for r in frame.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS)
    ]


def layout(frame: Any) -> dict[str, Any]:
    cells = grid(frame)
    owners: list[list[Any]] = [[None for _ in row] for row in cells]
    regions = []
    for r, row in enumerate(cells):
        for c, cell in enumerate(row):
            if set(cell.attrib) - ATTRS:
                raise invalid_request("Unsupported native cell attributes stay read-only.")
            for name in ["rowSpan", "gridSpan"]:
                if not re.fullmatch("[1-9][0-9]?", cell.get(name, "1")):
                    raise invalid_request("Invalid native table spans stay read-only.")
            for name in ["hMerge", "vMerge"]:
                if cell.get(name, "0") not in {"0", "1", "false", "true"}:
                    raise invalid_request("Invalid native merge flags stay read-only.")
            h, w = int(cell.get("rowSpan", "1")), int(cell.get("gridSpan", "1"))
            hm, vm = [cell.get(k, "0") in {"1", "true"} for k in ["hMerge", "vMerge"]]
            if owners[r][c] is not None:
                a, b, hh, ww = owners[r][c]
                if (hm, vm, h, w) != (c > b, r > a, hh if r == a else 1, ww if c == b else 1):
                    raise invalid_request("Inconsistent native span coverage stays read-only.")
                continue
            if hm or vm or r + h > len(cells) or c + w > len(row):
                raise invalid_request("Orphaned or out-of-grid spans stay read-only.")
            for rr in range(r, r + h):
                for cc in range(c, c + w):
                    if owners[rr][cc] is not None:
                        raise invalid_request("Overlapping native spans stay read-only.")
                    owners[rr][cc] = [r, c, h, w]
            if h > 1 or w > 1:
                regions.append({"row": r, "column": c, "row_span": h, "column_span": w})
    return {"regions": regions, "owners": owners}


def complete_range(
    params: dict[str, Any], cells: list[list[Any]], info: dict[str, Any]
) -> tuple[int, int, int, int]:
    a, b, c, d = bounds(params, cells)
    for r in range(a, b + 1):
        for col in range(c, d + 1):
            rr, cc, h, w = info["owners"][r][col]
            if not (a <= rr and rr + h - 1 <= b and c <= cc and cc + w - 1 <= d):
                raise invalid_request("Include the whole merged cell in the selected range.")
    return a, b, c, d


def replace_text(editor: Any, cell: Any, text: str) -> None:
    """Retain each existing paragraph's style, using the last donor for added lines."""
    body = cell.find("a:txBody", _NS)
    previous = body.findall("a:p", _NS)
    at = body.index(previous[0])
    replacements = []
    for i, line in enumerate(text.split("\n")):
        donor = copy.deepcopy(previous[min(i, len(previous) - 1)])
        holder = etree.Element(f"{{{DRAWING_NS}}}txBody")
        holder.append(donor)
        editor._replace_notes_paragraphs(holder, [donor], line)
        replacements.append(holder[0])
    for p in previous:
        body.remove(p)
    for i, p in enumerate(replacements):
        body.insert(at + i, p)


def merge_cells(editor: Any, frame: Any, params: dict[str, Any], *, split: bool) -> bool:
    from presenter_core.presentation.tables import inspect_table, validate_cells

    info = inspect_table(frame)
    if not info or not info["editable"]:
        raise invalid_request("This native table is read-only.")
    cells = grid(frame)
    spans = layout(frame)
    a, b, c, d = complete_range(params, cells, spans)
    if split:
        selected = [v for v in spans["regions"] if a <= v["row"] <= b and c <= v["column"] <= d]
        if not selected:
            return False
    elif a == b and c == d:
        raise invalid_request("Select at least two cells to merge.")
    elif any(
        v["row"] == a
        and v["column"] == c
        and v["row_span"] == b - a + 1
        and v["column_span"] == d - c + 1
        for v in spans["regions"]
    ):
        return False
    before = copy.deepcopy(frame)
    if not split:
        paragraphs = [
            copy.deepcopy(p)
            for row in cells[a : b + 1]
            for cell in row[c : d + 1]
            for p in cell.findall("a:txBody/a:p", _NS)
            if any((n.text or "") for n in p.findall("a:r/a:t", _NS))
        ]
        if not paragraphs:
            paragraphs = [copy.deepcopy(cells[a][c].find("a:txBody/a:p", _NS))]
        origin = cells[a][c].find("a:txBody", _NS)
        for p in origin.findall("a:p", _NS):
            origin.remove(p)
        for p in paragraphs:
            origin.append(p)
    for r in range(a, b + 1):
        for col in range(c, d + 1):
            cell = cells[r][col]
            if split and not any(
                v["row"] <= r < v["row"] + v["row_span"]
                and v["column"] <= col < v["column"] + v["column_span"]
                for v in selected
            ):
                continue
            for k in ATTRS:
                cell.attrib.pop(k, None)
            if not split:
                if r == a and b > a:
                    cell.set("rowSpan", str(b - a + 1))
                if col == c and d > c:
                    cell.set("gridSpan", str(d - c + 1))
                if r > a:
                    cell.set("vMerge", "1")
                if col > c:
                    cell.set("hMerge", "1")
                if (r, col) != (a, c):
                    replace_text(editor, cell, "")
    fresh = inspect_table(frame)
    if not fresh or not fresh["editable"]:
        raise invalid_request(
            "Combined text exceeds the editable cell limits; shorten it before merging."
        )
    validate_cells(fresh["cells"])
    compared = copy.deepcopy(frame)
    for tree in [before, compared]:
        for r, row in enumerate(grid(tree)):
            for col, cell in enumerate(row):
                if a <= r <= b and c <= col <= d:
                    for k in ATTRS:
                        cell.attrib.pop(k, None)
                    if not split:
                        cell.remove(cell.find("a:txBody", _NS))
    if etree.tostring(before, method="c14n") != etree.tostring(compared, method="c14n"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_VALIDATION_FAILED", "Merge changed cell styling or other content."
        )
    return True
