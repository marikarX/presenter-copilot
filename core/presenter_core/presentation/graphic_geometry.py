"""Keep table grid sizes synchronized with reviewed native frame transforms."""

from __future__ import annotations

from typing import Any

from presenter_core.errors import invalid_request
from presenter_core.presentation.fidelity import _NS, FidelityGeometry


def resize_table_grid(frame: Any, old: FidelityGeometry, new: FidelityGeometry) -> None:
    table = frame.find("a:graphic/a:graphicData/a:tbl", _NS)
    if table is None:
        return
    for nodes, field, original, replacement in [
        (table.findall("a:tblGrid/a:gridCol", _NS), "w", old.width_emu, new.width_emu),
        (table.findall("a:tr", _NS), "h", old.height_emu, new.height_emu),
    ]:
        if original == replacement:
            continue
        values = [int(node.get(field)) for node in nodes]
        if not values or sum(values) != original or any(value <= 0 for value in values):
            raise invalid_request("The table grid does not match its frame size.")
        scaled = []
        total = previous = 0
        for value in values:
            total += value
            boundary = total * replacement // original
            scaled.append(boundary - previous)
            previous = boundary
        if any(value <= 0 for value in scaled):
            raise invalid_request("The resized table would have an empty row or column.")
        for node, value in zip(nodes, scaled, strict=True):
            node.set(field, str(value))
