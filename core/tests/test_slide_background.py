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
        assert before["background"] == {
            "state": "inherited",
            "color": None,
            "end_color": None,
            "angle": None,
            "editable": True,
        }
        reply = deck.set("#1f3a5f")
        assert reply["ok"] and reply["result"]["changed"], reply
        assert reply["result"]["background"] == {
            "state": "solid",
            "color": "#1F3A5F",
            "end_color": None,
            "angle": None,
        }
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
        # A picture without stretch, a theme-colored fill and an empty gradient are
        # replaceable but not edited in place.
        (
            '<p:bg><p:bgPr><a:blipFill><a:blip r:embed="rId9"/></a:blipFill></p:bgPr></p:bg>',
            ("custom", None),
        ),
        (
            '<p:bg><p:bgPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill></p:bgPr></p:bg>',
            ("custom", None),
        ),
        ("<p:bg><p:bgPr><a:gradFill/></p:bgPr></p:bg>", ("custom", None)),
        (
            '<p:bg><p:bgPr><a:gradFill><a:gsLst><a:gs pos="0"><a:srgbClr val="000000"/></a:gs>'
            '<a:gs pos="100000"><a:srgbClr val="FFFFFF"/></a:gs></a:gsLst><a:lin ang="2700000"/>'
            "</a:gradFill></p:bgPr></p:bg>",
            ("gradient", "#000000"),
        ),
        # Two fills, or a background with extra children, are not well formed.
        (
            "<p:bg><p:bgPr><a:noFill/><a:noFill/></p:bgPr></p:bg>",
            None,
        ),
    ],
)
def test_background_states(xml: str, expected: tuple | None) -> None:
    result = slide_background(_root(xml))
    assert (None if result is None else (result.state, result.color)) == expected


def test_gradient_and_picture_backgrounds(tmp_path: Path) -> None:
    import base64
    import io

    from PIL import Image

    deck = _Deck(tmp_path)
    try:
        image = io.BytesIO()
        Image.new("RGB", (64, 36), (20, 90, 160)).save(image, "PNG")
        asset = _call(
            deck.core,
            "import",
            "presentation.workspace.import_project_picture",
            {
                "project_id": deck.project,
                "name": "Hero",
                "image_base64": base64.b64encode(image.getvalue()).decode(),
            },
        )["result"]["asset"]["asset_id"]

        def change(**replacement: object) -> dict:
            inventory = deck.inventory()
            current = inventory["background"]
            reply = _call(
                deck.core,
                "background",
                "presentation.workspace.set_slide_background",
                {
                    "project_id": deck.project,
                    "document_id": deck.document,
                    "expected_revision_id": deck.revision,
                    "slide_id": inventory["slide_id"],
                    "expected_background": {
                        k: current[k] for k in ("state", "color", "end_color", "angle")
                    },
                    **replacement,
                },
            )
            if reply["ok"]:
                deck.revision = reply["result"]["revision_id"]
            return reply

        def rels() -> str:
            with deck.core._storage.project_database(deck.project) as connection:
                row = connection.execute(
                    "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
                    (deck.revision,),
                ).fetchone()
            path = deck.core._storage.paths.snapshot_path(deck.project, row["local_snapshot_path"])
            with zipfile.ZipFile(path) as archive:
                return archive.read("ppt/slides/_rels/slide1.xml.rels").decode()

        picture = change(replacement_picture_asset_id=asset)
        assert picture["ok"], picture.get("error")
        assert deck.inventory()["background"]["state"] == "picture"
        assert "copilot-background-" in rels()
        assert slide_background(deck.slide()).state == "picture"

        gradient = change(replacement_gradient={"start": "#0B1F33", "end": "#3A7BD5", "angle": 90})
        assert gradient["ok"], gradient.get("error")
        background = deck.inventory()["background"]
        assert (background["state"], background["color"], background["end_color"]) == (
            "gradient",
            "#0B1F33",
            "#3A7BD5",
        )
        assert background["angle"] == 90
        # The replaced picture's relationship is removed with it.
        assert "copilot-background-" not in rels()
        assert deck.slide().find(f".//{A}lin").get("ang") == "5400000"

        unchanged = change(replacement_gradient={"start": "#0B1F33", "end": "#3A7BD5", "angle": 90})
        assert unchanged["ok"] and unchanged["result"]["changed"] is False
        both = change(
            replacement_color="#FFFFFF",
            replacement_gradient=None,
            replacement_picture_asset_id=asset,
        )
        assert both["error"]["code"] == "INVALID_REQUEST"
        bad = change(replacement_gradient={"start": "#0B1F33", "end": "blue", "angle": 90})
        assert bad["error"]["code"] == "INVALID_REQUEST"
        assert change()["ok"]
        assert deck.inventory()["background"]["state"] == "inherited"
    finally:
        deck.core.close()
