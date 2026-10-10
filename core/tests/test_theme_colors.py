"""Deck-wide theme colors."""

from pathlib import Path

from test_presentation_workspace_source import _call
from test_slide_footers import _Footers


def _get(deck: _Footers) -> dict:
    reply = _call(deck.core, "get", "presentation.workspace.get_theme_colors", deck.scope())
    assert reply["ok"], reply
    return reply["result"]


def _set(deck: _Footers, colors: dict, expected: dict | None = None) -> dict:
    reply = _call(
        deck.core,
        "set",
        "presentation.workspace.set_theme_colors",
        {
            **deck.scope(),
            "expected_colors": expected or _get(deck)["colors"],
            "colors": colors,
        },
    )
    if reply["ok"]:
        deck.revision = reply["result"]["revision_id"]
    return reply


def test_theme_colors_read_set_and_guard(tmp_path: Path) -> None:
    deck = _Footers(tmp_path)
    try:
        state = _get(deck)
        assert state["editable"] and state["colors"]["accent1"].startswith("#")
        assert _set(deck, {"accent1": "#1f3a5f", "accent2": "#E07A1F"})["ok"]
        after = _get(deck)["colors"]
        assert (after["accent1"], after["accent2"]) == ("#1F3A5F", "#E07A1F")
        assert after["accent3"] == state["colors"]["accent3"]
        stale = _set(deck, {"accent1": "#000000"}, expected=state["colors"])
        assert not stale["ok"] and stale["error"]["code"] == "PRESENTATION_EDIT_STALE_TARGET"
        for bad in ({"dk1": "#000000"}, {"accent1": "red"}, {}):
            reply = _set(deck, bad)
            assert not reply["ok"] and reply["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()
