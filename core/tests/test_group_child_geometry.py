"""Shapes inside a top-level group move within the group's frame."""

from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches
from test_presentation_workspace_source import _call, _import_presentation, _open, _project_id

from presenter_core.ipc.core import CoreService


def test_group_child_moves_inside_the_frame_only(tmp_path: Path) -> None:
    source = tmp_path / "group.pptx"
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    group = slide.shapes.add_group_shape()
    first = group.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(2), Inches(1))
    first.name = "Inner A"
    group.shapes.add_shape(MSO_SHAPE.OVAL, Inches(4), Inches(3), Inches(2), Inches(2)).name = "B"
    deck.save(source)
    core = CoreService(data_root=tmp_path / "data")
    try:
        project = _project_id(core)
        document = _import_presentation(core, project, source)["id"]
        revision = _open(core, project, document)["revision_id"]
        scope = {"project_id": project, "document_id": document}

        def objects() -> tuple[str, dict]:
            inventory = _call(
                core,
                "t",
                "presentation.workspace.list_text_targets",
                {**scope, "revision_id": revision, "slide_number": 1},
            )["result"]
            return inventory["slide_id"], {o["name"]: o for o in inventory["objects"]}

        slide_id, found = objects()
        inner = found["Inner A"]
        frame = next(o for o in found.values() if o["kind"] == "grpSp")["geometry"]
        assert inner["group_child"] and inner["geometry_editable"]
        assert not inner["delete_editable"] and not inner["group_editable"]
        assert inner["geometry"] == {
            "x_emu": Inches(1),
            "y_emu": Inches(1),
            "width_emu": Inches(2),
            "height_emu": Inches(1),
        }

        def move(geometry: dict) -> dict:
            return _call(
                core,
                "m",
                "presentation.workspace.transform_object",
                {
                    **scope,
                    "expected_revision_id": revision,
                    "slide_id": slide_id,
                    "object_id": inner["object_id"],
                    "expected_geometry": inner["geometry"],
                    "replacement_geometry": geometry,
                },
            )

        outside = move({**inner["geometry"], "x_emu": int(Inches(5))})
        assert not outside["ok"] and "group" in outside["error"]["message"]
        inside = {**inner["geometry"], "x_emu": int(Inches(2)), "width_emu": int(Inches(1))}
        reply = move(inside)
        assert reply["ok"], reply.get("error")
        revision = reply["result"]["revision_id"]
        _, after = objects()
        assert after["Inner A"]["geometry"] == inside
        assert next(o for o in after.values() if o["kind"] == "grpSp")["geometry"] == frame
    finally:
        core.close()


def test_rotated_child_in_a_scaled_group_uses_swapped_axis_scaling() -> None:
    from lxml import etree

    from presenter_core.presentation.fidelity import FidelityGeometry
    from presenter_core.presentation.group_geometry import child_geometry, promoted_geometry

    group = etree.fromstring(
        '<p:grpSp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:grpSpPr><a:xfrm>'
        '<a:off x="1000" y="1000"/><a:ext cx="2000" cy="1000"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="1000" cy="1000"/></a:xfrm></p:grpSpPr>'
        '<p:sp><p:spPr><a:xfrm rot="5400000"><a:off x="400" y="300"/><a:ext cx="200" cy="400"/>'
        "</a:xfrm></p:spPr></p:sp></p:grpSp>"
    )
    child = group[1]
    # Centre (500, 500) maps to (2000, 1500); a 90-degree child takes y-scale on its width
    # (200 * 1) and x-scale on its height (400 * 2).
    assert promoted_geometry(group, child) == FidelityGeometry(1900, 1100, 200, 800)
    target = FidelityGeometry(1700, 1100, 200, 800)
    internal, landed = child_geometry(child, target)
    assert landed == target and internal.x_emu == 300
