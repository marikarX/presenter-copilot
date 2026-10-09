"""Read native text inheritance without flattening or modifying package styles."""

from __future__ import annotations

import copy
import hashlib
import posixpath
import re
import zipfile
from dataclasses import dataclass
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.presentation.fidelity import (
    _NS,
    REL_NS,
    _parse_xml_part,
    _relationships,
    _resolve_internal_part,
)
from presenter_core.presentation.table_fit import unsupported

_BODY_TYPES = {"body", "obj", "subTitle", "chart", "clipArt", "dgm", "media", "pic", "tbl"}


def overlay(base: Any, override: Any) -> Any:
    """Combine a property node on a detached copy, including exclusive choices."""
    result = copy.deepcopy(base)
    if override is None:
        return result
    result.attrib.update(override.attrib)
    choices = [
        {"buNone", "buChar", "buAutoNum", "buBlip"},
        {"noAutofit", "normAutofit", "spAutoFit"},
        {"solidFill", "noFill", "gradFill", "pattFill", "blipFill", "grpFill"},
    ]
    for node in override:
        if not isinstance(node.tag, str):
            raise unsupported("Unsupported text property nodes cannot be resolved for fitting.")
        name = etree.QName(node).localname
        group = next((g for g in choices if name in g), {name})
        replacement = copy.deepcopy(node)
        if name == "defRPr":
            prior = result.find("a:defRPr", _NS)
            if prior is not None:
                replacement = overlay(prior, node)
        for old in list(result):
            if etree.QName(old).localname in group:
                result.remove(old)
        result.append(replacement)
    return result


def empty(name: str) -> Any:
    return etree.Element(f"{{{_NS['a']}}}{name}")


def level_properties(style: Any, level: int) -> Any:
    result = empty("pPr")
    if style is not None:
        result = overlay(result, style.find("a:defPPr", _NS))
        result = overlay(result, style.find(f"a:lvl{level + 1}pPr", _NS))
    return result


@dataclass(frozen=True)
class ResolvedText:
    body: Any
    transform: Any
    paragraphs: tuple[dict[str, Any], ...]
    fingerprint: str


class TextInheritance:
    """Resolve one slide's internal layout/master/theme and presentation defaults."""

    def __init__(self, archive: zipfile.ZipFile, slide_part: str) -> None:
        self.archive = archive
        self.dependencies: dict[str, bytes] = {}
        self.slide = self.read(slide_part)
        layout_part = self.target(slide_part, "slideLayout", required=True)
        assert layout_part is not None
        self.layout = self.read(layout_part)
        master_part = self.target(layout_part, "slideMaster", required=True)
        assert master_part is not None
        self.master = self.read(master_part)
        theme_part = self.target(master_part, "theme", required=True)
        assert theme_part is not None
        self.theme = self.read(theme_part)
        self.presentation = self.read("ppt/presentation.xml")
        self.font_scheme = self.theme.find("a:themeElements/a:fontScheme", _NS)
        # The nearest override takes precedence; external overrides never get fetched.
        for owner in [master_part, layout_part, slide_part]:
            part = self.target(owner, "themeOverride")
            if part is not None:
                root = self.read(part)
                scheme = root.find("a:fontScheme", _NS)
                if scheme is not None:
                    self.font_scheme = scheme
        expected = [(self.slide, "sld"), (self.layout, "sldLayout"), (self.master, "sldMaster")]
        if any(node.tag != f"{{{_NS['p']}}}{name}" for node, name in expected):
            raise unsupported("Unexpected native slide/style parts cannot be resolved for fitting.")

    def read(self, part: str) -> Any:
        try:
            info = self.archive.getinfo(part)
        except KeyError:
            raise unsupported("A native text inheritance part is missing.") from None
        root = _parse_xml_part(self.archive, info)
        self.dependencies[part] = self.archive.read(info)
        return root

    def target(self, owner: str, kind: str, *, required: bool = False) -> str | None:
        part = posixpath.join(
            posixpath.dirname(owner), "_rels", posixpath.basename(owner) + ".rels"
        )
        if part not in self.archive.namelist():
            if required:
                raise unsupported("A native text inheritance relationship is missing.")
            return None
        relations = _relationships(self.read(part))
        matches = [v for v in relations.values() if v[0] == f"{REL_NS}/{kind}"]
        if not matches and not required:
            return None
        if len(matches) != 1 or matches[0][2].casefold() != "internal":
            raise unsupported("Text inheritance references must be internal and unambiguous.")
        return _resolve_internal_part(posixpath.dirname(owner), matches[0][1])

    def chain(self, shape: Any) -> list[Any]:
        ph = shape.find("p:nvSpPr/p:nvPr/p:ph", _NS)
        if ph is None:
            return [shape]
        idx = ph.get("idx", "0")
        if not re.fullmatch("[0-9]{1,10}", idx):
            raise unsupported("Unsupported placeholder identity cannot be resolved for fitting.")
        layouts = [
            s
            for s in self.layout.findall("p:cSld/p:spTree/p:sp", _NS)
            if (p := s.find("p:nvSpPr/p:nvPr/p:ph", _NS)) is not None and p.get("idx", "0") == idx
        ]
        if len(layouts) != 1:
            raise unsupported("The placeholder layout is missing or ambiguous.")
        parent = layouts[0]
        parent_ph = parent.find("p:nvSpPr/p:nvPr/p:ph", _NS)
        kind = parent_ph.get("type", "obj")
        master_kind = "body" if kind in _BODY_TYPES else "title" if kind == "ctrTitle" else kind
        masters = [
            s
            for s in self.master.findall("p:cSld/p:spTree/p:sp", _NS)
            if (p := s.find("p:nvSpPr/p:nvPr/p:ph", _NS)) is not None
            and p.get("type", "obj") == master_kind
        ]
        if len(masters) > 1:
            raise unsupported("The placeholder master is ambiguous.")
        return masters + [parent, shape]

    def family(self, raw: str) -> str:
        if not raw or len(raw) > 120:
            raise unsupported("The text font family cannot be resolved for fitting.")
        if not raw.startswith("+"):
            return raw
        if raw not in {"+mj-lt", "+mn-lt"} or self.font_scheme is None:
            raise unsupported("Unsupported theme/script fonts require manual text fitting.")
        path = "a:majorFont/a:latin" if raw == "+mj-lt" else "a:minorFont/a:latin"
        font = self.font_scheme.find(path, _NS)
        if font is None or not font.get("typeface"):
            raise unsupported("The theme Latin font is unavailable for fitting.")
        return str(font.get("typeface"))

    def resolve(self, shape: Any) -> ResolvedText:
        if shape.tag != f"{{{_NS['p']}}}sp":
            raise unsupported("Only native text shapes can use text-box fitting.")
        body = shape.find("p:txBody", _NS)
        if body is None:
            raise unsupported("The native shape has no text body.")
        chain = self.chain(shape)
        transform = empty("xfrm")
        for ancestor in chain:
            transform = overlay(transform, ancestor.find("p:spPr/a:xfrm", _NS))
        if not len(transform):
            raise unsupported("The inherited text-box geometry is unavailable.")
        bp = empty("bodyPr")
        for ancestor in chain:
            bp = overlay(bp, ancestor.find("p:txBody/a:bodyPr", _NS))
        detached = copy.deepcopy(body)
        old = detached.find("a:bodyPr", _NS)
        if old is not None:
            detached.remove(old)
        detached.insert(0, bp)
        paragraphs = []
        ph = chain[-2].find("p:nvSpPr/p:nvPr/p:ph", _NS) if len(chain) > 1 else None
        kind = ph.get("type", "obj") if ph is not None else "other"
        style_name = (
            "titleStyle"
            if kind in {"title", "ctrTitle"}
            else ("bodyStyle" if kind in _BODY_TYPES else "otherStyle")
        )
        for original, paragraph in zip(
            body.findall("a:p", _NS), detached.findall("a:p", _NS), strict=False
        ):
            own = original.find("a:pPr", _NS)
            level = own.get("lvl", "0") if own is not None else "0"
            if not re.fullmatch("[0-8]", level):
                raise unsupported("Unsupported text outline levels cannot be resolved for fitting.")
            document_defaults = level_properties(
                self.presentation.find("p:defaultTextStyle", _NS), int(level)
            )
            master_defaults = level_properties(
                self.master.find(f"p:txStyles/p:{style_name}", _NS), int(level)
            )
            # Native placeholders use their master text category. Ordinary text
            # boxes take presentation defaults ahead of the master's otherStyle.
            pp = (
                overlay(master_defaults, document_defaults)
                if ph is None
                else overlay(document_defaults, master_defaults)
            )
            rp = overlay(empty("rPr"), pp.find("a:defRPr", _NS))
            for ancestor in chain:
                ref = ancestor.find("p:style/a:fontRef", _NS)
                if ref is not None and ref.get("idx") in {"major", "minor"}:
                    font = empty("rPr")
                    etree.SubElement(
                        font,
                        f"{{{_NS['a']}}}latin",
                        typeface=("+mj-lt" if ref.get("idx") == "major" else "+mn-lt"),
                    )
                    rp = overlay(rp, font)
                defaults = level_properties(ancestor.find("p:txBody/a:lstStyle", _NS), int(level))
                pp = overlay(pp, defaults)
                rp = overlay(rp, defaults.find("a:defRPr", _NS))
            pp = overlay(pp, own)
            rp = overlay(rp, own.find("a:defRPr", _NS) if own is not None else None)
            prior = paragraph.find("a:pPr", _NS)
            if prior is not None:
                paragraph.remove(prior)
            paragraph.insert(0, pp)
            runs = []
            for run in paragraph.findall("a:r", _NS):
                direct = run.find("a:rPr", _NS)
                effective, metadata = self.run_properties(rp, direct)
                if direct is not None:
                    run.remove(direct)
                run.insert(0, effective)
                runs.append(metadata)
            end = paragraph.find("a:endParaRPr", _NS)
            effective_end, end_metadata = self.run_properties(rp, end)
            effective_end.tag = f"{{{_NS['a']}}}endParaRPr"
            if end is not None:
                paragraph.remove(end)
            paragraph.append(effective_end)
            paragraphs.append({"level": int(level), "runs": runs, "end": end_metadata})
        digest = hashlib.sha256()
        for part, data in sorted(self.dependencies.items()):
            key = part.encode("utf-8")
            digest.update(len(key).to_bytes(8, "big") + key + len(data).to_bytes(8, "big") + data)
        digest.update(etree.tostring(shape, method="c14n"))
        return ResolvedText(
            detached, copy.deepcopy(transform), tuple(paragraphs), digest.hexdigest()
        )

    def run_properties(self, inherited: Any, direct: Any) -> tuple[Any, dict[str, Any]]:
        effective = overlay(inherited, direct)
        latin = effective.find("a:latin", _NS)
        raw = latin.get("typeface", "") if latin is not None else "+mn-lt"
        family = self.family(raw)
        if latin is None:
            latin = etree.SubElement(effective, f"{{{_NS['a']}}}latin")
        latin.set("typeface", family)
        return effective, {
            "family": family,
            "size_hundredths": effective.get("sz"),
            "bold": effective.get("b", "0"),
            "italic": effective.get("i", "0"),
        }
