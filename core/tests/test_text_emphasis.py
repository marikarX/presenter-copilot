"""Reviewed underline/strikethrough edits on direct text runs."""

from pathlib import Path

import pytest
from lxml import etree
from test_bullet_marker import NS, A, _Deck


def _runs(deck: _Deck) -> list[etree._Element]:
    return [
        run.find(f"{A}rPr")
        for properties in deck.properties()
        for run in properties.getparent().findall("a:r", NS)
    ]


def _keep(_properties: etree._Element) -> None:
    pass


def _run_attribute(name: str, value: str):
    def mutate(properties: etree._Element) -> None:
        for run in properties.getparent().findall("a:r", NS):
            properties_node = run.find(f"{A}rPr")
            if properties_node is None:
                properties_node = etree.Element(f"{A}rPr")
                run.insert(0, properties_node)
            properties_node.set(name, value)

    return mutate


def test_underline_and_strikethrough_apply_read_back_and_clear(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _keep)
    try:
        style = deck.target()[0]["text_style"]
        assert style["underline"] is None and style["strikethrough"] is None
        reply = deck.format({"underline": True, "strikethrough": True})
        assert reply["ok"], reply
        assert {(run.get("u"), run.get("strike")) for run in _runs(deck)} == {("sng", "sngStrike")}
        style = deck.target()[0]["text_style"]
        assert style["underline"] is True and style["strikethrough"] is True
        assert deck.format({"underline": False, "strikethrough": False})["ok"]
        assert {(run.get("u"), run.get("strike")) for run in _runs(deck)} == {("none", "noStrike")}
        style = deck.target()[0]["text_style"]
        assert style["underline"] is False and style["strikethrough"] is False
    finally:
        deck.core.close()


def test_existing_double_underline_counts_as_underlined_and_is_kept(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _run_attribute("u", "dbl"))
    try:
        assert deck.target()[0]["text_style"]["underline"] is True
        assert deck.format({"underline": True, "bold": True})["ok"]
        assert {run.get("u") for run in _runs(deck)} == {"dbl"}
    finally:
        deck.core.close()


@pytest.mark.parametrize(("name", "value"), [("u", "squiggle"), ("strike", "triple")])
def test_unknown_emphasis_values_stay_read_only(tmp_path: Path, name: str, value: str) -> None:
    deck = _Deck(tmp_path, _run_attribute(name, value))
    try:
        target = deck.target()[0]
        assert target["text_style"] is None or not target["text_style"]["editable"]
    finally:
        deck.core.close()


def test_non_boolean_emphasis_is_rejected(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _keep)
    try:
        reply = deck.format({"underline": "yes"})
        assert not reply["ok"] and reply["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()


def test_font_family_replaces_latin_typeface_and_drops_stale_metadata(tmp_path: Path) -> None:
    def latin(properties: etree._Element) -> None:
        for run in properties.getparent().findall("a:r", NS):
            node = run.find(f"{A}rPr")
            if node is None:
                node = etree.Element(f"{A}rPr")
                run.insert(0, node)
            for old in node.findall(f"{A}latin") + node.findall(f"{A}ea"):
                node.remove(old)
            etree.SubElement(node, f"{A}latin", typeface="Calibri", panose="020F0502020204030204")
            etree.SubElement(node, f"{A}ea", typeface="+mn-ea")

    deck = _Deck(tmp_path, latin)
    try:
        assert deck.target()[0]["text_style"]["font_family"] == "Calibri"
        assert deck.format({"font_family": "Georgia"})["ok"]
        for run in _runs(deck):
            assert dict(run.find(f"{A}latin").attrib) == {"typeface": "Georgia"}
            assert [child.tag.removeprefix(A) for child in run][-2:] == ["latin", "ea"]
        assert deck.target()[0]["text_style"]["font_family"] == "Georgia"
        assert deck.format({"font_family": "+mj-lt"})["ok"]
        assert deck.target()[0]["text_style"]["font_family"] == "+mj-lt"
    finally:
        deck.core.close()


def _without_latin(properties: etree._Element) -> None:
    for node in properties.getparent().findall("a:r/a:rPr", NS):
        for old in node.findall(f"{A}latin"):
            node.remove(old)


def test_font_family_is_inserted_when_absent(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _without_latin)
    try:
        assert deck.target()[0]["text_style"]["font_family"] is None
        assert deck.format({"font_family": "Segoe UI"})["ok"]
        assert {run.find(f"{A}latin").get("typeface") for run in _runs(deck)} == {"Segoe UI"}
    finally:
        deck.core.close()


@pytest.mark.parametrize("family", ["", " Arial", "+custom", "A" * 32, "Bad<Font>", "Tab\tFont"])
def test_invalid_font_family_is_rejected(tmp_path: Path, family: str) -> None:
    deck = _Deck(tmp_path, _keep)
    try:
        reply = deck.format({"font_family": family})
        assert not reply["ok"] and reply["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()


def test_highlight_applies_in_schema_order_and_removes(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _keep)
    try:
        assert deck.target()[0]["text_style"]["highlight_color"] is None
        assert deck.format({"highlight_color": "#ffff00", "font_family": "Georgia"})["ok"]
        for run in _runs(deck):
            names = [child.tag.removeprefix(A) for child in run]
            assert names.index("highlight") < names.index("latin")
            assert run.find(f"{A}highlight/{A}srgbClr").get("val") == "FFFF00"
        assert deck.target()[0]["text_style"]["highlight_color"] == "#FFFF00"
        assert deck.format({"highlight_color": "none"})["ok"]
        assert all(run.find(f"{A}highlight") is None for run in _runs(deck))
        assert deck.target()[0]["text_style"]["highlight_color"] is None
        bad = deck.format({"highlight_color": "yellow"})
        assert not bad["ok"] and bad["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()
