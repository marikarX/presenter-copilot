"""Placeholders that inherit their layout position can be moved and resized."""

import zipfile
from pathlib import Path

from lxml import etree
from pptx import Presentation
from test_presentation_workspace_source import _call, _import_presentation, _open, _project_id

from presenter_core.ipc.core import CoreService


def test_inherited_placeholder_moves_with_an_explicit_transform(tmp_path: Path) -> None:
    source = tmp_path / "inherited.pptx"
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Inherited title"
    deck.save(source)
    layout_title = next(
        s for s in deck.slide_layouts[1].placeholders if s.placeholder_format.idx == 0
    )
    core = CoreService(data_root=tmp_path / "data")
    try:
        project = _project_id(core)
        document = _import_presentation(core, project, source)["id"]
        revision = _open(core, project, document)["revision_id"]
        scope = {"project_id": project, "document_id": document}

        def title() -> tuple[str, dict]:
            inventory = _call(
                core,
                "t",
                "presentation.workspace.list_text_targets",
                {**scope, "revision_id": revision, "slide_number": 1},
            )["result"]
            return inventory["slide_id"], next(
                o for o in inventory["objects"] if o["name"].startswith("Title")
            )

        slide_id, obj = title()
        assert obj["geometry_editable"]
        assert obj["geometry"] == {
            "x_emu": layout_title.left,
            "y_emu": layout_title.top,
            "width_emu": layout_title.width,
            "height_emu": layout_title.height,
        }
        moved = {**obj["geometry"], "x_emu": obj["geometry"]["x_emu"] + 91440}
        reply = _call(
            core,
            "m",
            "presentation.workspace.transform_object",
            {
                **scope,
                "expected_revision_id": revision,
                "slide_id": slide_id,
                "object_id": obj["object_id"],
                "expected_geometry": obj["geometry"],
                "replacement_geometry": moved,
            },
        )
        assert reply["ok"], reply.get("error")
        revision = reply["result"]["revision_id"]
        assert title()[1]["geometry"] == moved
        with core._storage.project_database(project) as connection:
            path = connection.execute(
                "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?", (revision,)
            ).fetchone()["local_snapshot_path"]
        with zipfile.ZipFile(core._storage.paths.snapshot_path(project, path)) as archive:
            root = etree.fromstring(archive.read("ppt/slides/slide1.xml"))
        offsets = root.xpath(
            "//*[local-name()='sp'][.//*[local-name()='ph']]//*[local-name()='off']"
        )
        assert [int(o.get("x")) for o in offsets][:1] == [moved["x_emu"]]
    finally:
        core.close()
