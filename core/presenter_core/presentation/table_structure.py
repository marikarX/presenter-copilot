"""Retain native cells and styles while inserting/removing table rows and columns."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from presenter_core.errors import CoreDomainError, invalid_request
from presenter_core.presentation.fidelity import _NS, DRAWING_NS

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService


def structure_supported(frame: Any) -> bool:
    table = frame.find("a:graphic/a:graphicData/a:tbl", _NS)
    if table is None or [n.tag for n in table] != [
        f"{{{DRAWING_NS}}}tblPr",
        f"{{{DRAWING_NS}}}tblGrid",
        *[f"{{{DRAWING_NS}}}tr"] * len(table.findall("a:tr", _NS)),
    ]:
        return False
    grid = table.find("a:tblGrid", _NS)
    if grid.attrib or any(n.tag != f"{{{DRAWING_NS}}}gridCol" for n in grid):
        return False
    if any(cell.attrib for row in table.findall("a:tr", _NS) for cell in row.findall("a:tc", _NS)):
        return False
    return all(
        set(n.attrib) == {attribute}
        and len(n.get(attribute) or "") <= 10
        and (n.get(attribute) or "").isascii()
        and (n.get(attribute) or "").isdigit()
        and 0 < int(n.get(attribute)) <= 2**31 - 1
        for nodes, attribute in [(list(grid), "w"), (table.findall("a:tr", _NS), "h")]
        for n in nodes
    ) and all(len(n) == 0 for n in grid)


def axis_sources(value: Any, size: int, original_size: int, field: str) -> list[int | None]:
    if not isinstance(value, list) or len(value) != size:
        raise invalid_request(
            "Provide one source index or null for each draft row/column.", field=field
        )
    retained = []
    for index in value:
        if index is not None:
            if type(index) is not int or not 0 <= index < original_size:
                raise invalid_request(
                    "A table source index is outside the original table.", field=field
                )
            retained.append(index)
    if retained != sorted(set(retained)):
        raise invalid_request("Retained rows/columns must keep their original order.", field=field)
    return value


def _donors(sources: list[int | None], fallback: int) -> list[int]:
    # Prefer the next retained row/column, so a row after a header inherits body styling.
    return [
        source
        if source is not None
        else next(
            (v for v in sources[index + 1 :] if v is not None),
            next((v for v in reversed(sources[:index]) if v is not None), fallback),
        )
        for index, source in enumerate(sources)
    ]


def _dimensions(original: list[int], donors: list[int]) -> list[int]:
    total = sum(original)
    if total < len(donors):
        raise invalid_request("The table is too small for this many rows or columns.")
    weights = [original[index] for index in donors]
    weight_sum = sum(weights)
    # Allocate at least one EMU per item; distribute rounding remainders deterministically.
    available = total - len(weights)
    values = [1 + available * weight // weight_sum for weight in weights]
    remainder = total - sum(values)
    order = sorted(range(len(weights)), key=lambda i: -(available * weights[i] % weight_sum))
    for index in order[:remainder]:
        values[index] += 1
    if any(value > 2**31 - 1 for value in values):
        raise invalid_request("The resulting table row/column dimensions exceed the native limit.")
    return values


def reshape_table(
    editor: PresentationEditService,
    frame: Any,
    cells: list[list[str]],
    row_sources: Any,
    column_sources: Any,
) -> bool:
    if not structure_supported(frame):
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "The table's row/column structure cannot be safely edited.",
        )
    table = frame.find("a:graphic/a:graphicData/a:tbl", _NS)
    original_rows = table.findall("a:tr", _NS)
    grid = table.find("a:tblGrid", _NS)
    original_columns = list(grid)
    rows = axis_sources(row_sources, len(cells), len(original_rows), "row_sources")
    columns = axis_sources(column_sources, len(cells[0]), len(grid), "column_sources")
    row_donors = _donors(rows, min(1, len(original_rows) - 1))
    column_donors = _donors(columns, 0)
    heights = _dimensions([int(n.get("h")) for n in original_rows], row_donors)
    widths = _dimensions([int(n.get("w")) for n in original_columns], column_donors)
    # Identity mappings must not normalize rounding or imported dimensions during text-only edits.
    if rows == list(range(len(original_rows))):
        heights = [int(n.get("h")) for n in original_rows]
    if columns == list(range(len(original_columns))):
        widths = [int(n.get("w")) for n in original_columns]
    from lxml import etree  # type: ignore[import-untyped]

    before = etree.tostring(frame, method="c14n")
    for child in list(grid):
        grid.remove(child)
    for donor, width in zip(column_donors, widths, strict=True):
        column = copy.deepcopy(original_columns[donor])
        column.set("w", str(width))
        grid.append(column)
    for row in original_rows:
        table.remove(row)
    for donor, height, values in zip(row_donors, heights, cells, strict=True):
        source_cells = original_rows[donor].findall("a:tc", _NS)
        row = copy.deepcopy(original_rows[donor])
        row.set("h", str(height))
        for child in list(row):
            row.remove(child)
        for column_donor, text in zip(column_donors, values, strict=True):
            cell = copy.deepcopy(source_cells[column_donor])
            body = cell.find("a:txBody", _NS)
            paragraphs = body.findall("a:p", _NS)
            original_text = "\n".join(
                "".join(node.text or "" for node in paragraph.findall("a:r/a:t", _NS))
                for paragraph in paragraphs
            )
            if text != original_text:
                editor._replace_notes_paragraphs(body, paragraphs, text)
            row.append(cell)
        table.append(row)
    return bool(etree.tostring(frame, method="c14n") != before)
