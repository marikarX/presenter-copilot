"""Reviewed bullet color/size edits and plain text-font bullet tolerance."""

import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from lxml import etree
from test_presentation_workspace_source import (
    FIXTURE_ROOT,
    _call,
    _import_presentation,
    _open,
    _project_id,
    _write_multirun_text_fixture,
)

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import DRAWING_NS, PRESENTATION_NS
from presenter_core.providers.edit_plan_schema import _STYLE_PROPERTIES

NS = {"p": PRESENTATION_NS, "a": DRAWING_NS}
A = f"{{{DRAWING_NS}}}"


def _fixture(tmp_path: Path, mutate: Callable[[etree._Element], None]) -> tuple[Path, int, str]:
    base = tmp_path / "base.pptx"
    slide_number, shape_id = _write_multirun_text_fixture(
        FIXTURE_ROOT / "deck" / "presentation.pptx", base
    )
    target = tmp_path / "bullets.pptx"
    with zipfile.ZipFile(base) as source, zipfile.ZipFile(target, "w") as output:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == f"ppt/slides/slide{slide_number}.xml":
                root = etree.fromstring(content)
                for properties in root.xpath(
                    ".//p:sp[p:nvSpPr/p:cNvPr[@id=$id]]/p:txBody/a:p/a:pPr",
                    namespaces=NS,
                    id=shape_id,
                ):
                    mutate(properties)
                content = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
            output.writestr(info, content)
    return target, slide_number, shape_id


def _with_font(typeface: str) -> Callable[[etree._Element], None]:
    def mutate(properties: etree._Element) -> None:
        bullet = properties.find(f"{A}buChar")
        assert bullet is not None
        bullet.addprevious(etree.Element(f"{A}buFont", typeface=typeface))

    return mutate


class _Deck:
    def __init__(self, tmp_path: Path, mutate: Callable[[etree._Element], None]) -> None:
        path, self.slide_number, self.shape_id = _fixture(tmp_path, mutate)
        self.core = CoreService(data_root=tmp_path / "data")
        self.project = _project_id(self.core)
        self.document = _import_presentation(self.core, self.project, path)["id"]
        self.revision = _open(self.core, self.project, self.document)["revision_id"]

    def target(self) -> tuple[dict, str]:
        inventory = _call(
            self.core,
            "targets",
            "presentation.workspace.list_text_targets",
            {
                "project_id": self.project,
                "document_id": self.document,
                "revision_id": self.revision,
                "slide_number": self.slide_number,
            },
        )
        assert inventory["ok"], inventory
        target = next(
            item
            for item in inventory["result"]["targets"]
            if item["ooxml_shape_id"] == self.shape_id
        )
        return target, inventory["result"]["slide_id"]

    def format(self, style: dict) -> dict:
        target, slide_id = self.target()
        reply = _call(
            self.core,
            "format",
            "presentation.workspace.format_text_shape",
            {
                "project_id": self.project,
                "document_id": self.document,
                "expected_revision_id": self.revision,
                "slide_id": slide_id,
                "object_id": target["object_id"],
                "expected_text": target["current_text"],
                "expected_style_fingerprint": target["text_style"]["fingerprint"],
                "replacement_style": style,
            },
        )
        if reply["ok"]:
            self.revision = reply["result"]["revision_id"]
        return reply

    def properties(self) -> list[etree._Element]:
        with self.core._storage.project_database(self.project) as connection:
            row = connection.execute(
                "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
                (self.revision,),
            ).fetchone()
        path = self.core._storage.paths.snapshot_path(
            self.project, row["local_snapshot_path"], require_exists=True
        )
        with zipfile.ZipFile(path) as archive:
            root = etree.fromstring(archive.read(f"ppt/slides/slide{self.slide_number}.xml"))
        return root.xpath(
            ".//p:sp[p:nvSpPr/p:cNvPr[@id=$id]]/p:txBody/a:p/a:pPr",
            namespaces=NS,
            id=self.shape_id,
        )


def _names(properties: etree._Element) -> list[str]:
    return [child.tag.removeprefix(A) for child in properties]


def test_plain_text_font_bullets_are_editable_and_font_is_preserved(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _with_font("Arial"))
    try:
        style = deck.target()[0]["text_style"]
        assert style["bullet_state"] == "bullet" and style["bullet_editable"]
        assert style["bullet_color_editable"] and style["bullet_size_editable"]
        assert style["bullet_color"] is None and style["bullet_size_percent"] is None
        reply = deck.format({"bullet_mode": "numbered_alpha_lower"})
        assert reply["ok"], reply
        for properties in deck.properties():
            assert properties.find(f"{A}buFont").get("typeface") == "Arial"
            assert properties.find(f"{A}buAutoNum").get("type") == "alphaLcPeriod"
            assert properties.find(f"{A}buChar") is None
    finally:
        deck.core.close()


def test_bullet_color_and_size_apply_in_schema_order_and_read_back(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _with_font("Calibri"))
    try:
        reply = deck.format({"bullet_color": "#c00000", "bullet_size_percent": 150})
        assert reply["ok"], reply
        assert reply["result"]["changed"] is True
        for properties in deck.properties():
            names = [n for n in _names(properties) if n.startswith("bu")]
            assert names == ["buClr", "buSzPct", "buFont", "buChar"]
            assert properties.find(f"{A}buClr/{A}srgbClr").get("val") == "C00000"
            assert properties.find(f"{A}buSzPct").get("val") == "150000"
        style = deck.target()[0]["text_style"]
        assert style["bullet_color"] == "#C00000"
        assert style["bullet_size_percent"] == 150
        assert style["bullet_state"] == "bullet"
        # Changing the marker type keeps the reviewed color and size.
        assert deck.format({"bullet_mode": "bullet_square"})["ok"]
        style = deck.target()[0]["text_style"]
        assert (style["bullet_state"], style["bullet_color"], style["bullet_size_percent"]) == (
            "bullet_square",
            "#C00000",
            150,
        )
        # Re-applying the same values is a no-op without a new revision.
        same = deck.format({"bullet_color": "#C00000", "bullet_size_percent": 150})
        assert same["ok"] and same["result"]["changed"] is False
    finally:
        deck.core.close()


def _theme_color(properties: etree._Element) -> None:
    color = etree.Element(f"{A}buClr")
    etree.SubElement(color, f"{A}schemeClr", val="accent1")
    properties.find(f"{A}buChar").addprevious(color)


def _symbol_glyph(properties: etree._Element) -> None:
    bullet = properties.find(f"{A}buChar")
    bullet.set("char", "\u00a7")  # Wingdings square
    bullet.addprevious(etree.Element(f"{A}buFont", typeface="Wingdings"))


def _follow_text(properties: etree._Element) -> None:
    bullet = properties.find(f"{A}buChar")
    for name in ("buClrTx", "buSzTx", "buFontTx"):
        bullet.addprevious(etree.Element(f"{A}{name}"))


def _point_size(properties: etree._Element) -> None:
    properties.find(f"{A}buChar").addprevious(etree.Element(f"{A}buSzPts", val="1800"))


@pytest.mark.parametrize(
    ("mutate", "state"),
    [
        (_theme_color, "bullet"),
        (_follow_text, "bullet"),
        (_point_size, "bullet"),
        (_symbol_glyph, None),
    ],
    ids=["theme-color", "follow-text", "point-size", "symbol-glyph"],
)
def test_common_real_deck_decoration_is_editable(tmp_path: Path, mutate, state) -> None:
    deck = _Deck(tmp_path, mutate)
    try:
        style = deck.target()[0]["text_style"]
        assert style["bullet_editable"] and style["bullet_state"] == state
        assert style["bullet_color_editable"] and style["bullet_size_editable"]
        assert style["bullet_color"] is None and style["bullet_size_percent"] is None
        assert deck.format({"bullet_color": "#336699", "bullet_size_percent": 90})["ok"]
        for properties in deck.properties():
            names = [n for n in _names(properties) if n.startswith("bu")]
            assert "buClrTx" not in names and "buSzTx" not in names
            assert "buSzPts" not in names
            assert names.count("buClr") == 1 and names.count("buSzPct") == 1
        assert deck.format({"bullet_mode": "numbered"})["ok"]
        for properties in deck.properties():
            fonts = [f.get("typeface") for f in properties.findall(f"{A}buFont")]
            assert "Wingdings" not in fonts
        style = deck.target()[0]["text_style"]
        assert (style["bullet_state"], style["bullet_color"], style["bullet_size_percent"]) == (
            "numbered",
            "#336699",
            90,
        )
    finally:
        deck.core.close()


def _picture_bullet(properties: etree._Element) -> None:
    bullet = properties.find(f"{A}buChar")
    blip = etree.Element(f"{A}buBlip")
    etree.SubElement(blip, f"{A}blip")
    properties.replace(bullet, blip)


def _unknown_color_model(properties: etree._Element) -> None:
    color = etree.Element(f"{A}buClr")
    etree.SubElement(color, f"{A}prstClr", val="red")
    properties.find(f"{A}buChar").addprevious(color)


@pytest.mark.parametrize(
    "mutate",
    [_picture_bullet, _unknown_color_model],
    ids=["picture-bullet", "preset-color"],
)
def test_unsupported_bullet_decoration_stays_read_only(tmp_path: Path, mutate) -> None:
    deck = _Deck(tmp_path, mutate)
    try:
        style = deck.target()[0]["text_style"]
        assert not style["bullet_editable"]
        assert not style["bullet_color_editable"] and not style["bullet_size_editable"]
        for change in ({"bullet_color": "#000000"}, {"bullet_mode": "numbered"}):
            reply = deck.format(change)
            assert not reply["ok"]
            assert reply["error"]["code"] == "PRESENTATION_EDIT_UNSUPPORTED"
    finally:
        deck.core.close()


@pytest.mark.parametrize(
    "style",
    [
        {"bullet_color": "red"},
        {"bullet_color": "#12345"},
        {"bullet_size_percent": 24},
        {"bullet_size_percent": 401},
        {"bullet_size_percent": 100.5},
    ],
)
def test_invalid_bullet_decoration_values_are_rejected(tmp_path: Path, style) -> None:
    deck = _Deck(tmp_path, _with_font("Arial"))
    try:
        reply = deck.format(style)
        assert not reply["ok"] and reply["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()


def test_copilot_schema_exposes_bullet_decoration() -> None:
    assert _STYLE_PROPERTIES["bullet_color"]["minLength"] == 7
    assert _STYLE_PROPERTIES["bullet_size_percent"]["minimum"] == 25
    assert _STYLE_PROPERTIES["bullet_size_percent"]["maximum"] == 400


def _numbered_from(start: str | None) -> Callable[[etree._Element], None]:
    def mutate(properties: etree._Element) -> None:
        bullet = properties.find(f"{A}buChar")
        number = etree.Element(f"{A}buAutoNum", type="arabicPeriod")
        if start is not None:
            number.set("startAt", start)
        properties.replace(bullet, number)

    return mutate


def test_numbering_start_applies_carries_across_schemes_and_resets(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _with_font("Arial"))
    try:
        assert deck.target()[0]["text_style"]["numbering_start"] is None
        rejected = deck.format({"numbering_start": 3})
        assert not rejected["ok"]
        assert rejected["error"]["code"] == "PRESENTATION_EDIT_UNSUPPORTED"
        assert deck.format({"bullet_mode": "numbered", "numbering_start": 3})["ok"]
        assert [p.find(f"{A}buAutoNum").get("startAt") for p in deck.properties()] == ["3"] * len(
            deck.properties()
        )
        assert deck.target()[0]["text_style"]["numbering_start"] == 3
        assert deck.format({"bullet_mode": "numbered_roman_upper"})["ok"]
        style = deck.target()[0]["text_style"]
        assert (style["bullet_state"], style["numbering_start"]) == ("numbered_roman_upper", 3)
        assert deck.format({"numbering_start": 1})["ok"]
        assert all(p.find(f"{A}buAutoNum").get("startAt") is None for p in deck.properties())
        assert deck.target()[0]["text_style"]["numbering_start"] == 1
    finally:
        deck.core.close()


def test_imported_custom_start_is_now_editable(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _numbered_from("5"))
    try:
        style = deck.target()[0]["text_style"]
        assert style["bullet_state"] == "numbered" and style["bullet_editable"]
        assert style["numbering_start"] == 5
        for value in (0, 10000, "2"):
            reply = deck.format({"numbering_start": value})
            assert not reply["ok"] and reply["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()


@pytest.mark.parametrize("start", ["0", "07", "12345", "x"])
def test_malformed_start_values_stay_read_only(tmp_path: Path, start: str) -> None:
    deck = _Deck(tmp_path, _numbered_from(start))
    try:
        style = deck.target()[0]["text_style"]
        assert not style["bullet_editable"] and style["numbering_start"] is None
    finally:
        deck.core.close()


def _inherited_symbol_font(properties: etree._Element) -> None:
    # The paragraph has no direct marker; the shape list style supplies Wingdings.
    properties.remove(properties.find(f"{A}buChar"))
    body = properties.getparent().getparent()
    style = body.find(f"{A}lstStyle")
    if style is None:
        style = etree.Element(f"{A}lstStyle")
        body.find(f"{A}bodyPr").addnext(style)
    if style.find(f"{A}lvl1pPr") is None:
        level = etree.SubElement(style, f"{A}lvl1pPr")
        etree.SubElement(level, f"{A}buFont", typeface="Wingdings", charset="2")
        etree.SubElement(level, f"{A}buChar", char="§")


@pytest.mark.parametrize("mode", ["bullet", "numbered_roman_lower"])
def test_new_marker_follows_text_font_instead_of_inherited_symbol_font(
    tmp_path: Path, mode: str
) -> None:
    deck = _Deck(tmp_path, _inherited_symbol_font)
    try:
        assert deck.target()[0]["text_style"]["bullet_editable"]
        assert deck.format({"bullet_mode": mode})["ok"]
        for properties in deck.properties():
            names = _names(properties)
            assert "buFontTx" in names and "buFont" not in names
            assert names.index("buFontTx") < names.index(
                "buChar" if mode == "bullet" else "buAutoNum"
            )
        assert deck.target()[0]["text_style"]["bullet_state"] == mode
        # Removing the marker does not add a font.
        assert deck.format({"bullet_mode": "none"})["ok"]
    finally:
        deck.core.close()


def _with_blank_lines(properties: etree._Element) -> None:
    paragraph = properties.getparent()
    body = paragraph.getparent()
    if body.get("blank-lines-added"):
        return
    body.set("blank-lines-added", "1")
    for index in (1, len(body)):  # one blank line inside the list and one trailing
        blank = etree.Element(f"{A}p")
        etree.SubElement(blank, f"{A}endParaRPr", lang="en-US")
        body.insert(index, blank)
    del body.attrib["blank-lines-added"]


def test_blank_lines_keep_lists_formattable_without_receiving_properties(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _with_blank_lines)
    try:
        target = deck.target()[0]
        assert target["text_format_editable"]
        style = target["text_style"]
        assert style["bullet_state"] == "bullet" and style["bullet_editable"]
        before_text = target["current_text"]
        assert "\n\n" in before_text
        assert deck.format({"bullet_mode": "numbered", "alignment": "center"})["ok"]
        after = deck.target()[0]
        assert after["current_text"] == before_text
        assert (after["text_style"]["bullet_state"], after["text_style"]["alignment"]) == (
            "numbered",
            "center",
        )
        with zipfile.ZipFile(_snapshot(deck)) as archive:
            root = etree.fromstring(archive.read(f"ppt/slides/slide{deck.slide_number}.xml"))
        paragraphs = root.xpath(
            ".//p:sp[p:nvSpPr/p:cNvPr[@id=$id]]/p:txBody/a:p", namespaces=NS, id=deck.shape_id
        )
        blanks = [p for p in paragraphs if p.find(f"{A}r") is None]
        assert len(blanks) == 2 and all(p.find(f"{A}pPr") is None for p in blanks)
    finally:
        deck.core.close()


def _snapshot(deck: "_Deck") -> Path:
    with deck.core._storage.project_database(deck.project) as connection:
        row = connection.execute(
            "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
            (deck.revision,),
        ).fetchone()
    return deck.core._storage.paths.snapshot_path(
        deck.project, row["local_snapshot_path"], require_exists=True
    )


def _with_line_break(properties: etree._Element) -> None:
    paragraph = properties.getparent()
    if paragraph.getparent().find(f"{A}p") is not paragraph:
        return
    run = paragraph.find(f"{A}r")
    line_break = etree.Element(f"{A}br")
    etree.SubElement(line_break, f"{A}rPr", lang="en-US")
    second = etree.Element(f"{A}r")
    etree.SubElement(second, f"{A}t").text = "second line"
    run.addnext(line_break)
    line_break.addnext(second)


def test_line_breaks_are_formattable_but_never_replacement_targets(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _with_line_break)
    try:
        target = deck.target()[0]
        assert target["text_format_editable"]
        assert not target["single_run_editable"] and not target["uniform_run_editable"]
        before = target["current_text"]
        assert deck.format({"font_size_pt": 30, "bullet_mode": "numbered"})["ok"]
        after = deck.target()[0]
        assert after["current_text"] == before
        assert after["text_style"]["font_size_pt"] == 30
        for properties in deck.properties():
            for line_break in properties.getparent().findall(f"{A}br"):
                assert line_break.find(f"{A}rPr").get("sz") == "3000"
        assert len(deck.properties()[0].getparent().findall(f"{A}br")) == 1
    finally:
        deck.core.close()


def test_unsupported_line_break_markup_stays_read_only(tmp_path: Path) -> None:
    def mutate(properties: etree._Element) -> None:
        _with_line_break(properties)
        for line_break in properties.getparent().findall(f"{A}br"):
            line_break.set("unexpected", "1")

    deck = _Deck(tmp_path, mutate)
    try:
        assert not deck.target()[0]["text_format_editable"]
    finally:
        deck.core.close()


def _with_slide_number_field(properties: etree._Element) -> None:
    paragraph = properties.getparent()
    if paragraph.getparent().find(f"{A}p") is not paragraph:
        return
    field = etree.Element(f"{A}fld", id="{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}", type="slidenum")
    etree.SubElement(field, f"{A}rPr", lang="en-US")
    etree.SubElement(field, f"{A}t").text = "7"
    paragraph.find(f"{A}r").addnext(field)


def test_fields_are_formattable_preserved_and_never_replacement_targets(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _with_slide_number_field)
    try:
        target = deck.target()[0]
        assert target["text_format_editable"]
        assert not target["single_run_editable"] and not target["uniform_run_editable"]
        before = target["current_text"]
        assert "7" in before
        assert deck.format({"font_size_pt": 28})["ok"]
        assert deck.target()[0]["current_text"] == before
        field = deck.properties()[0].getparent().find(f"{A}fld")
        assert field.get("type") == "slidenum" and field.find(f"{A}t").text == "7"
        assert field.find(f"{A}rPr").get("sz") == "2800"
    finally:
        deck.core.close()


def test_fields_with_unexpected_markup_stay_read_only(tmp_path: Path) -> None:
    def mutate(properties: etree._Element) -> None:
        _with_slide_number_field(properties)
        field = properties.getparent().find(f"{A}fld")
        if field is not None:
            field.set("unexpected", "1")

    deck = _Deck(tmp_path, mutate)
    try:
        assert not deck.target()[0]["text_format_editable"]
    finally:
        deck.core.close()


def _embedded_picture_bullet(properties: etree._Element) -> None:
    bullet = properties.find(f"{A}buChar")
    picture = etree.Element(f"{A}buBlip")
    etree.SubElement(
        picture,
        f"{A}blip",
        {"{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed": "rId2"},
    )
    properties.replace(bullet, picture)


def test_embedded_picture_bullets_can_be_replaced_by_a_text_marker(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _embedded_picture_bullet)
    try:
        style = deck.target()[0]["text_style"]
        assert style["bullet_editable"] and style["bullet_state"] is None
        assert deck.format({"bullet_mode": "bullet_square"})["ok"]
        for properties in deck.properties():
            assert properties.find(f"{A}buBlip") is None
            assert properties.find(f"{A}buChar").get("char") == "▪"
        assert deck.target()[0]["text_style"]["bullet_state"] == "bullet_square"
    finally:
        deck.core.close()
