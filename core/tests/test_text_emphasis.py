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
