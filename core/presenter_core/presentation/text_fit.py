"""Measure resolved native text without substituting fonts or flattening runs."""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field, replace
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request
from presenter_core.presentation.fidelity import _NS, _paragraph_property_insert_index
from presenter_core.presentation.table_fit import PT, installed_font, unsupported
from presenter_core.presentation.text_inheritance import ResolvedText


@dataclass(frozen=True)
class FontMetrics:
    font: Any
    disable_kerning: bool

    _glyphs: dict[str, float] = field(default_factory=dict, compare=False, repr=False)

    def unkerned_glyph(self, character: str) -> float:
        if character not in self._glyphs:
            self._glyphs[character] = float(self.font.getlength(character))
        return self._glyphs[character]

    def getlength(self, text: str) -> float:
        try:
            if self.disable_kerning:
                # BASIC Pillow builds lack feature flags. Single Latin glyph advances
                # disable pair kerning without requiring an optional shaping library.
                return sum(self.unkerned_glyph(character) for character in text)
            return float(self.font.getlength(text))
        except (ValueError, KeyError, TypeError):
            raise unsupported(
                "The installed font engine cannot apply the native kerning threshold."
            ) from None


def number(value: str, label: str, *, negative: bool = False) -> int:
    if not re.fullmatch("-?[0-9]{1,10}" if negative else "[0-9]{1,10}", value):
        raise unsupported(f"Unsupported {label} cannot be measured for text fitting.")
    parsed = int(value)
    if abs(parsed) > 2**31 - 1:
        raise unsupported(f"Unsupported {label} cannot be measured for text fitting.")
    return parsed


def point_size(props: Any, factor: float) -> float:
    raw = number(props.get("sz", ""), "font size")
    if not 600 <= raw <= 9600:
        raise unsupported("Text fitting requires resolved font sizes between 6 and 96 points.")
    return max(1, math.floor(raw * factor + 1e-7)) / 100


def face(props: Any, factor: float) -> tuple[Any, float, float]:
    size = point_size(props, factor)
    family = props.find("a:latin", _NS)
    if family is None or not family.get("typeface"):
        raise unsupported("The native font family is unavailable for text fitting.")
    if any(props.get(k, "0") not in {"0", "1", "true", "false"} for k in ["b", "i"]):
        raise unsupported("Unsupported native text emphasis cannot be measured.")
    if props.get("baseline", "0") != "0":
        raise unsupported("Baseline shifts require manual text fitting.")
    threshold = number(props.get("kern", "0"), "kerning threshold") / 100
    font = installed_font(
        str(family.get("typeface")),
        props.get("b", "0") in {"1", "true"},
        props.get("i", "0") in {"1", "true"},
        max(1, round(size * 4)),
    )
    spacing = number(props.get("spc", "0"), "character spacing", negative=True) / 1000
    return FontMetrics(font, size < threshold), size, spacing


def distance(pp: Any, name: str, default: float, size: float) -> float:
    node = pp.find("a:" + name, _NS) if pp is not None else None
    if node is None:
        return default
    if len(node) != 1:
        raise unsupported("Unsupported paragraph spacing cannot be measured for fitting.")
    value = number(node[0].get("val", ""), "paragraph spacing")
    if node[0].tag == f"{{{_NS['a']}}}spcPts":
        return value / 100
    if node[0].tag == f"{{{_NS['a']}}}spcPct":
        return size * 1.2 * value / 100000
    raise unsupported("Unsupported paragraph spacing cannot be measured for fitting.")


def validate_body(resolved: ResolvedText) -> tuple[int, int, int, int, float, float]:
    transform = resolved.transform
    off, ext = transform.find("a:off", _NS), transform.find("a:ext", _NS)
    if (
        off is None
        or ext is None
        or len(transform) != 2
        or any(transform.get(k, "0") not in {"0", "false"} for k in ["rot", "flipH", "flipV"])
    ):
        raise unsupported("Rotated or flipped text boxes require manual fitting.")
    x, y = (number(off.get(k, ""), "text-box position") for k in ["x", "y"])
    width, height = (number(ext.get(k, ""), "text-box size") for k in ["cx", "cy"])
    if not width or not height:
        raise unsupported("Empty native text-box geometry cannot be fitted.")
    bp = resolved.body.find("a:bodyPr", _NS)
    if (
        bp is None
        or bp.get("vert", "horz") != "horz"
        or bp.get("rot", "0") != "0"
        or bp.get("numCol", "1") != "1"
        or bp.get("rtlCol", "0") not in {"0", "false"}
        or bp.get("fromWordArt", "0") not in {"0", "false"}
        or any(
            bp.find("a:" + n, _NS) is not None for n in ["prstTxWarp", "scene3d", "sp3d", "extLst"]
        )
    ):
        raise unsupported("Vertical, columned or warped text requires manual fitting.")
    cached = bp.find("a:normAutofit", _NS)
    if cached is not None and (
        not 1 <= number(cached.get("fontScale", "100000"), "cached font scale") <= 100000
        or number(cached.get("lnSpcReduction", "0"), "cached line spacing") > 100000
    ):
        raise unsupported("Unsupported cached text scaling requires manual fitting.")
    margins = [
        number(bp.get(k, str(v)), "text inset") / PT
        for k, v in [("lIns", 91440), ("rIns", 91440), ("tIns", 45720), ("bIns", 45720)]
    ]
    available = width / PT - sum(margins[:2])
    if available <= 0 or height / PT <= sum(margins[2:]):
        raise invalid_request("The text-box insets leave no space for fitting.")
    return x, y, width, height, available, sum(margins[2:])


def paragraph_height(
    paragraph: Any, width: float, factor: float, wrap: bool, ordinal: int = 1
) -> float:
    pp = paragraph.find("a:pPr", _NS)
    if pp is not None and (
        pp.get("rtl", "0") not in {"0", "false"}
        or any(pp.find("a:" + n, _NS) is not None for n in ["tabLst", "buBlip", "extLst"])
    ):
        raise unsupported("RTL text, tab stops and image bullets require manual fitting.")
    left = number(pp.get("marL", "0"), "paragraph indent") / PT if pp is not None else 0
    right = number(pp.get("marR", "0"), "paragraph indent") / PT if pp is not None else 0
    indent = (
        number(pp.get("indent", "0"), "first-line indent", negative=True) / PT
        if pp is not None
        else 0
    )
    if left + indent < 0 or width - left - right - max(0, indent) <= 0:
        raise invalid_request("Paragraph indents leave no space for fitted text.")
    # Each glyph carries its actual run font. Run seams do not turn into word breaks.
    glyphs: list[tuple[str, float, float]] = []
    for node in paragraph:
        if node.tag == f"{{{_NS['a']}}}r":
            props = node.find("a:rPr", _NS)
            font, size, spacing = face(props, factor)
            text = node.find("a:t", _NS)
            value = text.text or "" if text is not None else ""
            if "\t" in value or "\n" in value or "\r" in value:
                raise unsupported("Native tab/control text requires manual fitting.")
            previous = 0.0
            for index, character in enumerate(value):
                # Complex shaping needs script-aware metrics, not a Latin fallback.
                if ord(character) > 0x024F and character not in "–—‘’“”…•€£¥©®™":
                    raise unsupported("Complex-script glyph metrics require manual fitting.")
                advance = float(font.getlength(value[: index + 1])) / 4
                glyphs.append((character, max(0, advance - previous + spacing), size))
                previous = advance
        elif node.tag == f"{{{_NS['a']}}}br":
            glyphs.append(("\n", 0, 0))
        elif node.tag not in {f"{{{_NS['a']}}}pPr", f"{{{_NS['a']}}}endParaRPr"}:
            raise unsupported("Fields and unsupported runs require manual fitting.")
    end = paragraph.find("a:endParaRPr", _NS)
    _, end_size, _ = face(end, factor)
    max_size = max([end_size, *(g[2] for g in glyphs)])
    bullet = pp.find("a:buChar", _NS) if pp is not None else None
    numbered = pp.find("a:buAutoNum", _NS) if pp is not None else None
    has_bullet = bullet is not None or numbered is not None
    # Hanging bullet markers occupy the area before the text margin. Reject a
    # marker that would share/overrun text instead of silently ignoring its width.
    if has_bullet and indent >= 0:
        raise unsupported("Bullets without a hanging indent require manual fitting.")
    if has_bullet:
        marker_props = paragraph.find("a:r/a:rPr", _NS)
        if marker_props is None:
            marker_props = end
        _, marker_size, _ = face(marker_props, factor)
        family = marker_props.find("a:latin", _NS).get("typeface")
        marker_font = pp.find("a:buFont", _NS)
        if marker_font is not None:
            family = marker_font.get("typeface", "")
        pct, points = pp.find("a:buSzPct", _NS), pp.find("a:buSzPts", _NS)
        if pct is not None:
            marker_size *= number(pct.get("val", ""), "bullet size") / 100000
        if points is not None:
            marker_size = number(points.get("val", ""), "bullet size") / 100
        if not 1 <= marker_size <= 96:
            raise unsupported("Unsupported bullet sizes require manual fitting.")
        font = installed_font(str(family), False, False, max(1, round(marker_size * 4)))
        if numbered is not None:
            marker_number = number(numbered.get("startAt", "1"), "bullet numbering") + ordinal - 1
            suffixes = {"arabicPeriod": ".", "arabicParenR": ")", "arabicPlain": ""}
            kind = numbered.get("type", "")
            if kind not in suffixes or not 1 <= marker_number <= 32767:
                raise unsupported("Unsupported native numbering requires manual fitting.")
            marker = str(marker_number) + suffixes[kind]
        else:
            assert bullet is not None
            marker = bullet.get("char", "")
            if len(marker) != 1:
                raise unsupported("Unsupported native bullet markers require manual fitting.")
        if float(font.getlength(marker)) / 4 > -indent:
            raise invalid_request(
                "The bullet marker exceeds its hanging indent. Increase the indent."
            )
    first_width = width - left - right - (0 if has_bullet else indent)
    continuation_width = width - left - right
    tokens: list[list[tuple[str, float, float]]] = []
    for glyph in glyphs:
        if (
            not tokens
            or glyph[0] == "\n"
            or tokens[-1][-1][0] == "\n"
            or (glyph[0].isspace() != tokens[-1][-1][0].isspace())
        ):
            tokens.append([])
        tokens[-1].append(glyph)
    line_width, line_size, heights = 0.0, max(end_size, marker_size if has_bullet else 0), []
    available = first_width
    for token in tokens:
        if token[0][0] == "\n":
            heights.append(line_size)
            line_width, line_size, available = 0, end_size, continuation_width
            continue
        token_width = sum(g[1] for g in token)
        if not wrap and line_width + token_width > available:
            raise invalid_request(
                "Non-wrapping text is too wide. Enable wrapping or widen the box."
            )
        if wrap and line_width and line_width + token_width > available:
            if token[0][0].isspace():
                continue
            heights.append(line_size)
            line_width, line_size, available = 0, end_size, continuation_width
        for _, advance, size in token:
            if advance > available:
                raise invalid_request("A glyph is wider than the text box at the selected size.")
            if wrap and line_width + advance > available:
                heights.append(line_size)
                line_width, line_size, available = 0, end_size, continuation_width
            line_width += advance
            line_size = max(line_size, size)
    heights.append(line_size)
    return (
        sum(distance(pp, "lnSpc", s * 1.2, s) for s in heights)
        + distance(pp, "spcBef", 0, max_size)
        + distance(pp, "spcAft", 0, max_size)
    )


def measure(resolved: ResolvedText, factor: float = 1) -> float:
    _, _, _, _, width, vertical = validate_body(resolved)
    bp = resolved.body.find("a:bodyPr", _NS)
    return vertical + sum(
        paragraph_height(p, width, factor, bp.get("wrap", "square") != "none", i)
        for i, p in enumerate(resolved.body.findall("a:p", _NS), 1)
    )


@dataclass(frozen=True)
class TextFitResult:
    height_emu: int
    font_scale: float
    measured_height_pt: float


def calculate(
    resolved: ResolvedText, strategy: Any, minimum_size: Any, slide_height: int
) -> TextFitResult:
    if not isinstance(strategy, str) or strategy not in {"grow", "shrink"}:
        raise invalid_request("Choose grow or shrink text fitting.")
    if type(minimum_size) is not int or not 6 <= minimum_size <= 96:
        raise invalid_request("The minimum font size must be 6-96 points.")
    # Fitting explicitly enables wrapping, like the native Fit-to-shape workflow.
    # Resolve it on a detached copy so preview planning cannot mutate its source.
    resolved = replace(resolved, body=copy.deepcopy(resolved.body))
    resolved.body.find("a:bodyPr", _NS).set("wrap", "square")
    _, y, _, height, _, _ = validate_body(resolved)
    if strategy == "grow":
        measured = measure(resolved)
        fitted = max(height, math.ceil(measured * PT))
        if y + fitted > slide_height:
            raise invalid_request("The fitted text box would extend beyond the slide.")
        return TextFitResult(fitted, 1, measured)
    sizes = [point_size(p, 1) for p in resolved.body.findall(".//a:rPr", _NS)]
    sizes += [point_size(p, 1) for p in resolved.body.findall(".//a:endParaRPr", _NS)]
    if not sizes:
        raise unsupported("No measurable font sizes are available for fitting.")
    floor = minimum_size / min(sizes)
    if floor > 1:
        raise invalid_request("The minimum font size exceeds an existing text size.")
    bp = resolved.body.find("a:bodyPr", _NS)
    cached = bp.find("a:normAutofit", _NS)
    ceiling = 1.0
    if cached is not None:
        scale = number(cached.get("fontScale", "100000"), "cached font scale")
        reduction = number(cached.get("lnSpcReduction", "0"), "cached line spacing")
        if not 1 <= scale <= 100000 or reduction > 100000:
            raise unsupported("Unsupported cached text scaling requires manual fitting.")
        ceiling = scale / 100000
    if floor > ceiling:
        raise invalid_request("Cached text scaling is below the selected minimum size.")

    def fits(factor: float) -> bool:
        try:
            return measure(resolved, factor) * PT <= height
        except CoreDomainError as error:
            # Width failures may become feasible at a smaller font; structural
            # and exact-font failures must propagate rather than masquerade as fit.
            if error.code == "INVALID_REQUEST":
                return False
            raise

    if not fits(floor):
        raise invalid_request("Text cannot fit without going below the selected minimum font size.")
    low, high = floor, ceiling
    if fits(high):
        low = high
    else:
        for _ in range(18):
            middle = (low + high) / 2
            if fits(middle):
                low = middle
            else:
                high = middle
    return TextFitResult(height, low, measure(resolved, low))


def apply_fit(shape: Any, resolved: ResolvedText, result: TextFitResult) -> bool:
    """Apply only explicit height/size/autofit overrides after all measurements succeed."""
    before = etree.tostring(shape, method="c14n")
    body = shape.find("p:txBody", _NS)
    if result.font_scale < 1:
        for paragraph in body.findall("a:p", _NS):
            if _paragraph_property_insert_index(paragraph.find("a:pPr", _NS), "defRPr") is None:
                raise unsupported("Unsupported paragraph property order requires manual fitting.")
    bp = body.find("a:bodyPr", _NS)
    if bp is None:
        bp = etree.Element(f"{{{_NS['a']}}}bodyPr")
        body.insert(0, bp)
    bp.set("wrap", "square")
    for name in ["noAutofit", "normAutofit", "spAutoFit"]:
        for node in bp.findall("a:" + name, _NS):
            bp.remove(node)
    etree.SubElement(bp, f"{{{_NS['a']}}}noAutofit")
    props = shape.find("p:spPr", _NS)
    transform = props.find("a:xfrm", _NS)
    if (
        transform is None
        or transform.find("a:off", _NS) is None
        or transform.find("a:ext", _NS) is None
    ):
        if transform is not None:
            props.remove(transform)
        transform = copy.deepcopy(resolved.transform)
        props.insert(0, transform)
    transform.find("a:ext", _NS).set("cy", str(result.height_emu))
    if result.font_scale < 1:
        for original, effective in zip(
            body.findall("a:p", _NS), resolved.body.findall("a:p", _NS), strict=True
        ):
            pp = original.find("a:pPr", _NS)
            if pp is None:
                pp = etree.Element(f"{{{_NS['a']}}}pPr")
                original.insert(0, pp)
            default = pp.find("a:defRPr", _NS)
            if default is None:
                default = etree.Element(f"{{{_NS['a']}}}defRPr")
                position = _paragraph_property_insert_index(pp, "defRPr")
                assert position is not None
                pp.insert(position, default)
            donor_default = effective.find("a:pPr/a:defRPr", _NS)
            if donor_default is None or donor_default.get("sz") is None:
                donor_default = effective.find("a:endParaRPr", _NS)
            default.set(
                "sz", str(math.floor(int(donor_default.get("sz")) * result.font_scale + 1e-7))
            )
            for run, donor in zip(
                original.findall("a:r", _NS), effective.findall("a:r", _NS), strict=True
            ):
                rp = run.find("a:rPr", _NS)
                if rp is None:
                    rp = etree.Element(f"{{{_NS['a']}}}rPr")
                    run.insert(0, rp)
                rp.set(
                    "sz",
                    str(
                        math.floor(
                            int(donor.find("a:rPr", _NS).get("sz")) * result.font_scale + 1e-7
                        )
                    ),
                )
            end = original.find("a:endParaRPr", _NS)
            if end is None:
                end = etree.SubElement(original, f"{{{_NS['a']}}}endParaRPr")
            end.set(
                "sz",
                str(
                    math.floor(
                        int(effective.find("a:endParaRPr", _NS).get("sz")) * result.font_scale
                        + 1e-7
                    )
                ),
            )
    return bool(etree.tostring(shape, method="c14n") != before)
