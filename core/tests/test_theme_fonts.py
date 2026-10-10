"""Deck-wide theme heading/body fonts."""

from pathlib import Path

from test_presentation_workspace_source import _call
from test_slide_footers import _Footers


def _get(deck: _Footers) -> dict:
    reply = _call(deck.core, "get", "presentation.workspace.get_theme_fonts", deck.scope())
    assert reply["ok"], reply
    return reply["result"]


def _set(deck: _Footers, heading: str, body: str, expected: tuple | None = None) -> dict:
    state = _get(deck)
    old = expected or (state["heading_font"], state["body_font"])
    reply = _call(
        deck.core,
        "set",
        "presentation.workspace.set_theme_fonts",
        {
            **deck.scope(),
            "expected_heading_font": old[0],
            "expected_body_font": old[1],
            "heading_font": heading,
            "body_font": body,
        },
    )
    if reply["ok"]:
        deck.revision = reply["result"]["revision_id"]
    return reply


def test_theme_fonts_read_set_and_guard(tmp_path: Path) -> None:
    deck = _Footers(tmp_path)
    try:
        state = _get(deck)
        assert state["editable"] and state["theme_count"] >= 1 and state["heading_font"]
        assert _set(deck, "Georgia", "Segoe UI")["ok"]
        after = _get(deck)
        assert (after["heading_font"], after["body_font"]) == ("Georgia", "Segoe UI")
        stale = _set(deck, "Arial", "Arial", expected=("Calibri", "Calibri"))
        assert not stale["ok"] and stale["error"]["code"] == "PRESENTATION_EDIT_STALE_TARGET"
        bad = _set(deck, "+mj-lt", "Arial")
        assert not bad["ok"] and bad["error"]["code"] == "INVALID_REQUEST"
        same = _set(deck, "Georgia", "Segoe UI")
        assert same["ok"] and same["result"]["changed"] is False
    finally:
        deck.core.close()
