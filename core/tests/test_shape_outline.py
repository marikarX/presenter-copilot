"""Reviewed shape outline width and dash edits keep color and other content."""

import zipfile
from pathlib import Path

import pytest
from lxml import etree
from test_presentation_workspace_source import _call, _import_presentation, _open, _project_id

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import DRAWING_NS, PRESENTATION_NS
from presenter_core.providers.edit_plan_schema import _SHAPE_STYLE

A = f"{{{DRAWING_NS}}}"
NAME = "Workspace transform test shape"


class _Shape:
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

    def format(self, style: dict) -> dict:
        target, slide_id = self.target()
        reply = _call(
            self.core,
            "format",
            "presentation.workspace.format_shape_style",
            {
                "project_id": self.project,
                "document_id": self.document,
                "expected_revision_id": self.revision,
                "slide_id": slide_id,
                "object_id": target["object_id"],
                "expected_style_fingerprint": target["shape_style"]["fingerprint"],
                "replacement_style": style,
            },
        )
        if reply["ok"]:
            self.revision = reply["result"]["revision_id"]
        return reply

    def line(self) -> etree._Element:
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
        shape = next(
            sp
            for sp in root.iter(f"{{{PRESENTATION_NS}}}sp")
            if sp.find(f"{{{PRESENTATION_NS}}}nvSpPr/{{{PRESENTATION_NS}}}cNvPr").get("name")
            == NAME
        )
        return shape.find(f"{{{PRESENTATION_NS}}}spPr/{A}ln")


def test_outline_width_and_dash_apply_keep_color_and_read_back(tmp_path: Path) -> None:
    shape = _Shape(tmp_path)
    try:
        style = shape.target()[0]["shape_style"]
        assert style["line_format_editable"]
        assert style["line_color"] == "#396EA7"
        reply = shape.format({"line_width_pt": 4.5, "line_dash": "dash"})
        assert reply["ok"], reply
        line = shape.line()
        assert line.get("w") == str(round(4.5 * 12700))
        children = [child.tag.removeprefix(A) for child in line]
        assert children.index("prstDash") > children.index("solidFill")
        assert line.find(f"{A}prstDash").get("val") == "dash"
        style = shape.target()[0]["shape_style"]
        assert (style["line_width_pt"], style["line_dash"], style["line_color"]) == (
            4.5,
            "dash",
            "#396EA7",
        )
        assert shape.format({"line_dash": "sysDot"})["ok"]
        assert len(shape.line().findall(f"{A}prstDash")) == 1
        same = shape.format({"line_width_pt": 4.5})
        assert same["ok"] and same["result"]["changed"] is False
    finally:
        shape.core.close()


@pytest.mark.parametrize(
    "style",
    [
        {"line_width_pt": 0.1},
        {"line_width_pt": 21},
        {"line_width_pt": 1.3},
        {"line_width_pt": True},
        {"line_dash": "zigzag"},
    ],
)
def test_invalid_outline_values_are_rejected(tmp_path: Path, style: dict) -> None:
    shape = _Shape(tmp_path)
    try:
        reply = shape.format(style)
        assert not reply["ok"] and reply["error"]["code"] == "INVALID_REQUEST"
    finally:
        shape.core.close()


def test_copilot_schema_offers_outline_format() -> None:
    properties = _SHAPE_STYLE["properties"]
    assert {"line_width_pt", "line_dash"} <= set(properties)
