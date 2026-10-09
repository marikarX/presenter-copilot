"""Reviewed slide background color and reset-to-layout edits."""

import zipfile
from pathlib import Path

import pytest
from lxml import etree
from test_presentation_workspace_source import _call, _import_presentation, _open, _project_id

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import DRAWING_NS, PRESENTATION_NS, slide_background

P = f"{{{PRESENTATION_NS}}}"
A = f"{{{DRAWING_NS}}}"


class _Deck:
    def __init__(self, tmp_path: Path) -> None:
        self.core = CoreService(data_root=tmp_path / "data")
        self.project = _project_id(self.core)
        self.document = _import_presentation(self.core, self.project)["id"]
        self.revision = _open(self.core, self.project, self.document)["revision_id"]

    def inventory(self) -> dict:
        reply = _call(
            self.core,
            "targets",
            "presentation.workspace.list_text_targets",
            {
                "project_id": self.project,
                "document_id": self.document,
                "revision_id": self.revision,
                "slide_number": 1,
            },
        )
        assert reply["ok"], reply
        return reply["result"]

    def set(self, color: str | None, expected: dict | None = None) -> dict:
        inventory = self.inventory()
        background = inventory["background"]
        reply = _call(
            self.core,
            "background",
            "presentation.workspace.set_slide_background",
            {
                "project_id": self.project,
                "document_id": self.document,
                "expected_revision_id": self.revision,
                "slide_id": inventory["slide_id"],
                "expected_background": expected
                or {"state": background["state"], "color": background["color"]},
                "replacement_color": color,
            },
        )
        if reply["ok"]:
            self.revision = reply["result"]["revision_id"]
        return reply

    def slide(self) -> etree._Element:
        with self.core._storage.project_database(self.project) as connection:
            row = connection.execute(
                "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
                (self.revision,),
            ).fetchone()
        path = self.core._storage.paths.snapshot_path(
            self.project, row["local_snapshot_path"], require_exists=True
        )
        with zipfile.ZipFile(path) as archive:
            return etree.fromstring(archive.read("ppt/slides/slide1.xml"))


def test_background_color_applies_and_resets_to_layout(tmp_path: Path) -> None:
    deck = _Deck(tmp_path)
    try:
        before = deck.inventory()
        assert before["background"] == {"state": "inherited", "color": None, "editable": True}
        reply = deck.set("#1f3a5f")
        assert reply["ok"] and reply["result"]["changed"], reply
        assert reply["result"]["background"] == {"state": "solid", "color": "#1F3A5F"}
        root = deck.slide()
        common = root.find(f"{P}cSld")
        assert common[0].tag == f"{P}bg"
        assert common[0].find(f"{P}bgPr/{A}solidFill/{A}srgbClr").get("val") == "1F3A5F"
        after = deck.inventory()
        assert after["background"]["color"] == "#1F3A5F"
        assert [o["object_id"] for o in after["objects"]] == [
            o["object_id"] for o in before["objects"]
        ]
        assert deck.set(None)["ok"]
        assert deck.slide().find(f"{P}cSld/{P}bg") is None
        same = deck.set(None)
        assert same["ok"] and same["result"]["changed"] is False
    finally:
        deck.core.close()


def test_stale_and_invalid_background_requests_are_rejected(tmp_path: Path) -> None:
    deck = _Deck(tmp_path)
    try:
        stale = deck.set("#FFFFFF", expected={"state": "solid", "color": "#000000"})
        assert not stale["ok"] and stale["error"]["code"] == "PRESENTATION_EDIT_STALE_TARGET"
        for color in ("red", "#12345", 7):
            reply = deck.set(color)  # type: ignore[arg-type]
            assert not reply["ok"] and reply["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()


def _root(background: str) -> etree._Element:
    return etree.fromstring(
        f'<p:sld xmlns:p="{PRESENTATION_NS}" xmlns:a="{DRAWING_NS}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<p:cSld>{background}<p:spTree/></p:cSld></p:sld>"
    )


@pytest.mark.parametrize(
    ("xml", "expected"),
    [
        ("", ("inherited", None)),
        (
            '<p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>',
            ("theme_reference", None),
        ),
        (
            '<p:bg><p:bgPr><a:solidFill><a:srgbClr val="abcdef"/></a:solidFill>'
            "<a:effectLst/></p:bgPr></p:bg>",
            ("solid", "#ABCDEF"),
        ),
        ('<p:bg><p:bgPr><a:blipFill><a:blip r:embed="rId9"/></a:blipFill></p:bgPr></p:bg>', None),
        (
            '<p:bg><p:bgPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill></p:bgPr></p:bg>',
            None,
        ),
        ("<p:bg><p:bgPr><a:gradFill/></p:bgPr></p:bg>", None),
    ],
)
def test_background_states(xml: str, expected: tuple | None) -> None:
    result = slide_background(_root(xml))
    assert (None if result is None else (result.state, result.color)) == expected
