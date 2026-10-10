"""Reviewed basic slide transitions."""

from pathlib import Path

import pytest
from lxml import etree
from test_presentation_workspace_source import _call
from test_slide_background import P, _Deck

from presenter_core.presentation.fidelity import PRESENTATION_NS, slide_transition


def _set(deck: _Deck, expected: str, transition: str) -> dict:
    inventory = deck.inventory()
    reply = _call(
        deck.core,
        "transition",
        "presentation.workspace.set_slide_transition",
        {
            "project_id": deck.project,
            "document_id": deck.document,
            "expected_revision_id": deck.revision,
            "slide_id": inventory["slide_id"],
            "expected_transition": expected,
            "transition": transition,
        },
    )
    if reply["ok"]:
        deck.revision = reply["result"]["revision_id"]
    return reply


def test_transition_sets_in_schema_order_and_removes(tmp_path: Path) -> None:
    deck = _Deck(tmp_path)
    try:
        assert deck.inventory()["transition"] == "none"
        assert _set(deck, "none", "fade")["ok"]
        root = deck.slide()
        names = [etree.QName(child).localname for child in root]
        assert names.index("transition") > names.index("cSld")
        assert root.find(f"{P}transition/{P}fade") is not None
        assert deck.inventory()["transition"] == "fade"
        assert _set(deck, "fade", "push")["ok"]
        assert deck.slide().find(f"{P}transition/{P}push") is not None
        assert _set(deck, "push", "none")["ok"]
        assert deck.slide().find(f"{P}transition") is None
        stale = _set(deck, "fade", "wipe")
        assert not stale["ok"] and stale["error"]["code"] == "PRESENTATION_EDIT_STALE_TARGET"
        bad = _set(deck, "none", "spin")
        assert not bad["ok"] and bad["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("", "none"),
        ('<p:transition spd="slow"><p:wipe dir="r"/></p:transition>', "wipe"),
        ("<p:transition><p:zoom/></p:transition>", None),
        (
            '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/'
            'markup-compatibility/2006"><mc:Fallback><p:transition><p:fade/>'
            "</p:transition></mc:Fallback></mc:AlternateContent>",
            None,
        ),
    ],
)
def test_transition_states(body: str, expected: str | None) -> None:
    root = etree.fromstring(f'<p:sld xmlns:p="{PRESENTATION_NS}"><p:cSld/>{body}</p:sld>')
    assert slide_transition(root) == expected
