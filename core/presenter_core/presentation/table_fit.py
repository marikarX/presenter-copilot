"""Measure installed explicit fonts and store reviewed native table row heights."""

from __future__ import annotations

import copy
import math
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from lxml import etree  # type: ignore[import-untyped]
from PIL import ImageFont

from presenter_core.errors import CoreDomainError, invalid_request
from presenter_core.presentation.fidelity import _NS
from presenter_core.presentation.table_merge import grid, layout

PT = 12700


def unsupported(message: str) -> CoreDomainError:
    return CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", message)


def positive(value: str | None) -> int:
    if not value or not re.fullmatch("[0-9]{1,10}", value) or not 0 < int(value) <= 2**31 - 1:
        raise unsupported("Unsupported table dimensions stay read-only for automatic fitting.")
    return int(value)


def inspect_fit(frame: Any) -> dict[str, Any]:
    try:
        rows = [
            positive(r.get("h")) for r in frame.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS)
        ]
        columns = [
            positive(c.get("w"))
            for c in frame.findall("a:graphic/a:graphicData/a:tbl/a:tblGrid/a:gridCol", _NS)
        ]
        transform = frame.find("p:xfrm", _NS)
        off, ext = transform.find("a:off", _NS), transform.find("a:ext", _NS)
        if (
            set(transform.attrib)
            or len(transform) != 2
            or set(off.attrib) != {"x", "y"}
            or set(ext.attrib) != {"cx", "cy"}
        ):
            raise unsupported("Transformed tables stay read-only for automatic fitting.")
        if positive(ext.get("cy")) != sum(rows) or positive(ext.get("cx")) != sum(columns):
            raise unsupported("The stored table frame and grid dimensions disagree.")
        if not all(re.fullmatch("[0-9]{1,10}", off.get(k, "")) for k in ["x", "y"]):
            raise unsupported("Unsupported table positions stay read-only for automatic fitting.")
        return {
            "editable": True,
            "reason": None,
            "row_heights_pt": [v / PT for v in rows],
            "column_widths_pt": [v / PT for v in columns],
            "height_pt": sum(rows) / PT,
        }
    except (CoreDomainError, AttributeError) as error:
        return {"editable": False, "reason": str(error)}


@lru_cache(maxsize=1)
def font_files() -> dict[tuple[str, bool, bool], Path]:
    if sys.platform == "win32":
        directories = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
    elif sys.platform == "darwin":
        directories = [Path("/Library/Fonts"), Path("/System/Library/Fonts")]
    else:
        directories = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts")]
    files = {}
    styles = {
        "regular": (False, False),
        "normal": (False, False),
        "roman": (False, False),
        "book": (False, False),
        "bold": (True, False),
        "italic": (False, True),
        "oblique": (False, True),
        "bold italic": (True, True),
        "bold oblique": (True, True),
    }
    for directory in directories:
        if not directory.is_dir():
            continue
        for file in sorted(directory.rglob("*")):
            if file.suffix.lower() not in {".ttf", ".otf"}:
                continue
            try:
                face = ImageFont.truetype(str(file), size=16)
                family, style = face.getname()
                if isinstance(family, str) and isinstance(style, str) and style.lower() in styles:
                    bold, italic = styles[style.lower()]
                    files[(family.casefold(), bold, italic)] = file
            except (OSError, ValueError, UnicodeError):
                continue
    return files


@lru_cache(maxsize=128)
def installed_font(family: str, bold: bool, italic: bool, size: int) -> Any:
    try:
        file = font_files()[(family.casefold(), bold, italic)]
        return ImageFont.truetype(str(file), size=size)
    except (KeyError, OSError, ValueError):
        raise unsupported(
            "An exact installed font is unavailable for automatic fitting. "
            "Use explicit installed fonts before fitting."
        ) from None


def wrapped_lines(text: str, width: float, font: Any, spacing: float) -> int:
    def measure(value: str) -> float:
        return float(font.getlength(value)) / 4 + max(0, len(value) - 1) * spacing

    lines, current = 1, ""
    for token in re.findall(r"\s+|\S+", text):
        if measure(current + token) <= width:
            current += token
            continue
        if token.isspace():
            continue
        if current:
            lines += 1
            current = ""
        for character in token:
            if measure(current + character) > width:
                if not current:
                    raise invalid_request(
                        "A glyph exceeds the available cell width. Widen the column before fitting."
                    )
                lines += 1
                current = ""
            current += character
    return lines


def cell_height(cell: Any, width: float) -> float:
    tc, body = cell.find("a:tcPr", _NS), cell.find("a:txBody", _NS)
    bp = body.find("a:bodyPr", _NS)
    if (
        bp is None
        or bp.get("vert", "horz") != "horz"
        or bp.get("rot", "0") != "0"
        or bp.get("numCol", "1") != "1"
        or body.find("a:lstStyle", _NS) is not None
        and len(body.find("a:lstStyle", _NS))
    ):
        raise unsupported("Vertical, rotated, columned or inherited-list text cannot be measured.")
    if any(bp.find("a:" + k, _NS) is not None for k in ["normAutofit", "spAutoFit"]):
        raise unsupported(
            "Existing automatic text scaling must be resolved before fitting table rows."
        )

    def margin(name: str, default: int) -> float:
        v = tc.get(name, str(default))
        if not re.fullmatch("[0-9]{1,10}", v) or int(v) > 2**31 - 1:
            raise unsupported("Unsupported cell margins stay read-only for automatic fitting.")
        return int(v) / PT

    available = width - margin("marL", 91440) - margin("marR", 91440)
    if available <= 0:
        raise invalid_request("The table cell margins leave no text width.")
    height = margin("marT", 45720) + margin("marB", 45720)
    for p in body.findall("a:p", _NS):
        ppr, run = p.find("a:pPr", _NS), p.find("a:r", _NS)
        default = p.find("a:pPr/a:defRPr", _NS)
        rp = run.find("a:rPr", _NS) if run is not None else p.find("a:endParaRPr", _NS)

        def attr(name: str, fallback: str = "", rp: Any = rp, default: Any = default) -> str:
            return str(
                rp.get(name, default.get(name, fallback) if default is not None else fallback)
                if rp is not None
                else default.get(name, fallback)
                if default is not None
                else fallback
            )

        latin = rp.find("a:latin", _NS) if rp is not None else None
        if latin is None and default is not None:
            latin = default.find("a:latin", _NS)
        family = latin.get("typeface", "") if latin is not None else ""
        size = attr("sz")
        if (
            not family
            or family.startswith("+")
            or len(family) > 120
            or not re.fullmatch("[0-9]{1,6}", size)
            or not 600 <= int(size) <= 9600
        ):
            raise unsupported(
                "Automatic fitting requires explicit installed font families and 6-96 point sizes."
            )
        if attr("b", "0") not in {"0", "1", "false", "true"} or attr("i", "0") not in {
            "0",
            "1",
            "false",
            "true",
        }:
            raise unsupported("Unsupported text emphasis cannot be measured.")
        font_size = int(size) / 100
        font = installed_font(
            family,
            attr("b", "0") in {"1", "true"},
            attr("i", "0") in {"1", "true"},
            round(font_size * 4),
        )
        spacing = attr("spc", "0")
        if not re.fullmatch("-?[0-9]{1,6}", spacing):
            raise unsupported("Unsupported character spacing cannot be measured.")
        if ppr is not None and any(
            not re.fullmatch("-?[0-9]{1,10}", ppr.get(k, "0")) for k in ["marL", "indent"]
        ):
            raise unsupported("Unsupported native indents cannot be measured.")
        indent = float(ppr.get("marL", "0")) / PT if ppr is not None else 0
        first = float(ppr.get("indent", "0")) / PT if ppr is not None else 0
        if (
            not math.isfinite(indent + first)
            or indent < 0
            or first != 0
            or ppr is not None
            and any(
                ppr.find("a:" + k, _NS) is not None
                for k in ["buChar", "buAutoNum", "buBlip", "tabLst"]
            )
        ):
            raise unsupported("Bullets, tabs or hanging indents require manual table layout.")
        text = "".join(n.text or "" for n in p.findall("a:r/a:t", _NS))
        if "\t" in text:
            raise unsupported("Tab stops require manual table layout.")
        if (
            bp.get("wrap", "square") == "none"
            and float(font.getlength(text)) / 4 + max(0, len(text) - 1) * int(spacing) / 1000
            > available - indent
        ):
            raise invalid_request(
                "Non-wrapping text exceeds the cell width. Enable wrapping before fitting."
            )
        lines = (
            wrapped_lines(text, available - indent, font, int(spacing) / 1000)
            if bp.get("wrap", "square") != "none"
            else 1
        )

        def distance(
            name: str, default_value: float, ppr: Any = ppr, font_size: float = font_size
        ) -> float:
            n = ppr.find("a:" + name, _NS) if ppr is not None else None
            if n is None:
                return default_value
            if len(n) != 1 or not re.fullmatch("[0-9]{1,8}", n[0].get("val", "")):
                raise unsupported("Unsupported paragraph spacing cannot be measured.")
            v = int(n[0].get("val"))
            if etree.QName(n[0]).localname == "spcPts":
                return v / 100
            if etree.QName(n[0]).localname == "spcPct":
                return font_size * 1.2 * v / 100000
            raise unsupported("Unsupported paragraph spacing cannot be measured.")

        height += (
            lines * distance("lnSpc", font_size * 1.2)
            + distance("spcBef", 0)
            + distance("spcAft", 0)
        )
    return height


def fit_rows(frame: Any, strategy: Any, slide_height: int) -> bool:
    if not isinstance(strategy, str) or strategy not in {"grow", "compact"}:
        raise invalid_request("Choose grow or compact table fitting.")
    info = inspect_fit(frame)
    if not info["editable"]:
        raise unsupported(info["reason"])
    before = copy.deepcopy(frame)
    table = frame.find("a:graphic/a:graphicData/a:tbl", _NS)
    rows = table.findall("a:tr", _NS)
    widths = [positive(v.get("w")) / PT for v in table.findall("a:tblGrid/a:gridCol", _NS)]
    original = [positive(v.get("h")) for v in rows]
    heights = original.copy() if strategy == "grow" else [1] * len(rows)
    spans = layout(frame)
    constraints = []
    for r, row in enumerate(grid(frame)):
        for c, cell in enumerate(row):
            rr, cc, h, w = spans["owners"][r][c]
            if (rr, cc) == (r, c):
                required = math.ceil(cell_height(cell, sum(widths[c : c + w])) * PT - 1e-7)
                constraints.append((h, r, required))
    # Establish single-row minima first, then satisfy taller merged cells by
    # distributing any deficit across their rows without violating prior minima.
    for h, r, required in sorted(constraints):
        deficit = max(0, required - sum(heights[r : r + h]))
        for offset in range(h):
            heights[r + offset] += deficit // h + int(offset < deficit % h)
    off = frame.find("p:xfrm/a:off", _NS)
    if int(off.get("y")) + sum(heights) > slide_height:
        raise invalid_request(
            "The fitted table would extend beyond the slide. "
            "Reduce text size or move the table before fitting."
        )
    if heights == original:
        return False
    for row, value in zip(rows, heights, strict=True):
        row.set("h", str(value))
    frame.find("p:xfrm/a:ext", _NS).set("cy", str(sum(heights)))
    compared = copy.deepcopy(frame)
    for tree in [before, compared]:
        tree.find("p:xfrm/a:ext", _NS).attrib.pop("cy")
        for row in tree.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS):
            row.attrib.pop("h")
    if etree.tostring(before, method="c14n") != etree.tostring(compared, method="c14n"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_VALIDATION_FAILED", "Fitting changed table content or styling."
        )
    return True
