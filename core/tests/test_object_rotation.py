"""Reviewed rotation/flip edits; rotated shapes and pictures stay movable."""

import zipfile
from pathlib import Path

import pytest
from lxml import etree
from test_presentation_workspace_source import _call, _import_presentation, _open, _project_id

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import DRAWING_NS, PRESENTATION_NS

A = f"{{{DRAWING_NS}}}"
P = f"{{{PRESENTATION_NS}}}"
NAME = "Workspace duplicate test picture"
UPRIGHT = {"rotation_degrees": 0, "flip_horizontal": False, "flip_vertical": False}


class _Deck:
    def __init__(self, tmp_path: Path) -> None:
        self.core = CoreService(data_root=tmp_path / "data")
        self.project = _project_id(self.core)
        self.document = _import_presentation(self.core, self.project)["id"]
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
                "slide_number": 1,
            },
        )
        assert inventory["ok"], inventory
        target = next(o for o in inventory["result"]["objects"] if o["name"] == NAME)
        return target, inventory["result"]["slide_id"]

    def send(self, method: str, extra: dict) -> dict:
        target, slide_id = self.target()
        reply = _call(
            self.core,
            "edit",
            f"presentation.workspace.{method}",
            {
                "project_id": self.project,
                "document_id": self.document,
                "expected_revision_id": self.revision,
                "slide_id": slide_id,
                "object_id": target["object_id"],
                "expected_geometry": target["geometry"],
                **extra,
            },
        )
        if reply["ok"]:
            self.revision = reply["result"]["revision_id"]
        return reply

    def rotate(self, replacement: dict, expected: dict | None = None) -> dict:
        return self.send(
            "rotate_object",
            {
                "expected_rotation": expected or self.target()[0]["rotation"],
                "replacement_rotation": replacement,
            },
        )

    def transform(self) -> etree._Element:
        with self.core._storage.project_database(self.project) as connection:
            row = connection.execute(
                "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
                (self.revision,),
            ).fetchone()
        path = self.core._storage.paths.snapshot_path(
            self.project, row["local_snapshot_path"], require_exists=True
        )
        with zipfile.ZipFile(path) as archive:
            root = etree.fromstring(archive.read("ppt/slides/slide1.xml"))
        picture = next(
            pic
            for pic in root.iter(f"{P}pic")
            if pic.find(f"{P}nvPicPr/{P}cNvPr").get("name") == NAME
        )
        return picture.find(f"{P}spPr/{A}xfrm")


def test_rotation_applies_survives_moves_and_resets(tmp_path: Path) -> None:
    deck = _Deck(tmp_path)
    try:
        before = deck.target()[0]
        assert before["rotation"] == UPRIGHT
        wanted = {"rotation_degrees": 90, "flip_horizontal": True, "flip_vertical": False}
        reply = deck.rotate(wanted)
        assert reply["ok"] and reply["result"]["changed"], reply
        assert dict(deck.transform().attrib) == {"rot": "5400000", "flipH": "1"}
        rotated = deck.target()[0]
        assert rotated["rotation"] == wanted
        assert rotated["geometry"] == before["geometry"]
        assert rotated["geometry_editable"] and rotated["delete_editable"]

        moved_geometry = {**before["geometry"], "x_emu": before["geometry"]["x_emu"] + 12700}
        moved = deck.send("transform_object", {"replacement_geometry": moved_geometry})
        assert moved["ok"], moved
        after_move = deck.target()[0]
        assert after_move["geometry"] == moved_geometry and after_move["rotation"] == wanted

        fine = {"rotation_degrees": 12.5, "flip_horizontal": False, "flip_vertical": True}
        assert deck.rotate(fine)["ok"]
        assert dict(deck.transform().attrib) == {"rot": "750000", "flipV": "1"}
        assert deck.rotate(UPRIGHT)["ok"]
        assert dict(deck.transform().attrib) == {}
        same = deck.rotate(UPRIGHT)
        assert same["ok"] and same["result"]["changed"] is False
    finally:
        deck.core.close()


def test_stale_expected_rotation_is_rejected(tmp_path: Path) -> None:
    deck = _Deck(tmp_path)
    try:
        reply = deck.rotate(
            {**UPRIGHT, "rotation_degrees": 45},
            expected={**UPRIGHT, "rotation_degrees": 30},
        )
        assert not reply["ok"] and reply["error"]["code"] == "PRESENTATION_EDIT_STALE_TARGET"
    finally:
        deck.core.close()


@pytest.mark.parametrize(
    "replacement",
    [
        {**UPRIGHT, "rotation_degrees": 360},
        {**UPRIGHT, "rotation_degrees": -1},
        {**UPRIGHT, "rotation_degrees": "90"},
        {**UPRIGHT, "rotation_degrees": 0.000001},
        {**UPRIGHT, "flip_horizontal": 1},
        {"rotation_degrees": 90},
    ],
)
def test_invalid_rotation_is_rejected(tmp_path: Path, replacement: dict) -> None:
    deck = _Deck(tmp_path)
    try:
        reply = deck.rotate(replacement)
        assert not reply["ok"] and reply["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()
