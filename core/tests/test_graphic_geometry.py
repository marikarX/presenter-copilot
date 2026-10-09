from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from test_presentation_chart_editing import imported
from test_presentation_edit_planning import call
from test_presentation_native_layouts import path, scope
from test_presentation_tables import table_request
from test_presentation_transactions import context

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import (
    _NS,
    FidelityGeometry,
    _graphic_frame_geometry_supported,
)
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def fixture(core, tmp_path, kind):
    if kind == "chart":
        params, _ = imported(core, tmp_path)
    else:
        params, ops = context(core)
        saved = call(core, "presentation.workspace.create_table", table_request(params, ops))
        params["expected_revision_id"] = saved["revision_id"]
    inventory = call(
        core, "presentation.workspace.list_text_targets", {**scope(params), "slide_number": 1}
    )
    obj = next(v for v in inventory["objects"] if v["kind"] == "graphicFrame")
    return params, inventory, obj


@pytest.mark.parametrize("kind", ["chart", "table"])
def test_reviewed_graphic_move_resize_preserves_native_parts_and_undo(tmp_path: Path, kind: str):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, inventory, obj = fixture(core, tmp_path, kind)
        assert obj["geometry_editable"] and obj["delete_editable"]
        original = path(core, params).read_bytes()
        new = {"x_emu": 914400, "y_emu": 1371600, "width_emu": 5943601, "height_emu": 3200401}
        operation = {
            "type": "transform_object",
            "params": {
                "slide_id": inventory["slide_id"],
                "object_id": obj["object_id"],
                "expected_geometry": obj["geometry"],
                "replacement_geometry": new,
            },
        }
        plan = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {**params, "summary": "Review chart/table layout", "operations": [operation]},
        )
        assert path(core, params).read_bytes() == original
        call(
            core,
            "presentation.workspace.open_edit_plan_preview",
            {
                "project_id": params["project_id"],
                "document_id": params["document_id"],
                "plan_id": plan["plan_id"],
            },
        )
        saved = call(
            core,
            "presentation.workspace.apply_edit_plan",
            {
                "project_id": params["project_id"],
                "document_id": params["document_id"],
                "plan_id": plan["plan_id"],
                "reviewed_sha256": plan["sha256"],
                "confirm": True,
            },
        )
        params["expected_revision_id"] = saved["revision_id"]
        with (
            zipfile.ZipFile(io.BytesIO(original)) as before,
            zipfile.ZipFile(path(core, params)) as after,
        ):
            assert [
                name for name in before.namelist() if before.read(name) != after.read(name)
            ] == ["ppt/slides/slide1.xml"]
            old = etree.fromstring(before.read("ppt/slides/slide1.xml"))
            changed = etree.fromstring(after.read("ppt/slides/slide1.xml"))
            if kind == "table":
                widths = [
                    int(node.get("w")) for node in changed.findall(".//a:tblGrid/a:gridCol", _NS)
                ]
                heights = [int(node.get("h")) for node in changed.findall(".//a:tbl/a:tr", _NS)]
                assert sum(widths) == new["width_emu"] and sum(heights) == new["height_emu"]
                assert all(v > 0 for v in widths + heights)
            for root in [old, changed]:
                for node in root.findall(".//p:graphicFrame/p:xfrm/a:off", _NS) + root.findall(
                    ".//p:graphicFrame/p:xfrm/a:ext", _NS
                ):
                    node.attrib.clear()
                if kind == "table":
                    for node in root.findall(".//a:tblGrid/a:gridCol", _NS):
                        node.set("w", "1")
                    for node in root.findall(".//a:tbl/a:tr", _NS):
                        node.set("h", "1")
            assert etree.tostring(old, method="c14n") == etree.tostring(changed, method="c14n")
        fresh = call(
            core, "presentation.workspace.list_text_targets", {**scope(params), "slide_number": 1}
        )
        updated = next(v for v in fresh["objects"] if v["object_id"] == obj["object_id"])
        assert updated["geometry"] == new and updated["name"] == obj["name"]
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize("kind", ["chart", "table"])
@pytest.mark.parametrize("case", ["stale", "bounds", "noop"])
def test_graphic_geometry_rejects_stale_bounds_and_handles_noop(
    tmp_path: Path, kind: str, case: str
):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, inventory, obj = fixture(core, tmp_path, kind)
        original = path(core, params).read_bytes()
        expected = dict(obj["geometry"])
        replacement = dict(expected)
        if case == "stale":
            expected["x_emu"] += 1
        if case == "bounds":
            replacement["width_emu"] = 100000000
        result = call(
            core,
            "presentation.workspace.transform_object",
            {
                **params,
                "slide_id": inventory["slide_id"],
                "object_id": obj["object_id"],
                "expected_geometry": expected,
                "replacement_geometry": replacement,
            },
            ok=case == "noop",
        )
        if case == "noop":
            assert not result["changed"]
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


def test_table_grid_geometry_requires_matching_positive_sizes():
    ns = _NS["a"]
    pns = _NS["p"]
    frame = etree.fromstring(
        f'<p:graphicFrame xmlns:p="{pns}" xmlns:a="{ns}"><a:graphic>'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">'
        '<a:tbl><a:tblGrid><a:gridCol w="60"/><a:gridCol w="40"/></a:tblGrid>'
        '<a:tr h="50"/><a:tr h="50"/></a:tbl></a:graphicData></a:graphic></p:graphicFrame>'
    )
    geometry = FidelityGeometry(x_emu=0, y_emu=0, width_emu=100, height_emu=100)
    assert _graphic_frame_geometry_supported(frame, geometry)
    frame.find(".//a:gridCol", _NS).set("w", "0")
    assert not _graphic_frame_geometry_supported(frame, geometry)


def test_table_resize_preserves_unequal_proportions_and_exact_integer_totals():
    from presenter_core.presentation.graphic_geometry import resize_table_grid

    frame = etree.fromstring(
        '<p:graphicFrame xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphic>'
        '<a:graphicData><a:tbl><a:tblGrid><a:gridCol w="60"/><a:gridCol w="40"/>'
        '</a:tblGrid><a:tr h="30"/><a:tr h="70"/></a:tbl></a:graphicData>'
        "</a:graphic></p:graphicFrame>"
    )
    old = FidelityGeometry(x_emu=0, y_emu=0, width_emu=100, height_emu=100)
    new = FidelityGeometry(x_emu=0, y_emu=0, width_emu=125, height_emu=81)
    resize_table_grid(frame, old, new)
    assert [int(n.get("w")) for n in frame.findall(".//a:gridCol", _NS)] == [75, 50]
    assert [int(n.get("h")) for n in frame.findall(".//a:tr", _NS)] == [24, 57]
    from presenter_core.errors import CoreDomainError

    with pytest.raises(CoreDomainError):
        resize_table_grid(
            frame, new, FidelityGeometry(x_emu=0, y_emu=0, width_emu=1, height_emu=81)
        )


@pytest.mark.parametrize("kind", ["chart", "table"])
@pytest.mark.parametrize("action", ["delete", "layer"])
def test_graphic_delete_layer_preserves_parts_and_undo(tmp_path, kind, action):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, inventory, obj = fixture(core, tmp_path, kind)
        if kind == "chart" and action == "layer":
            created = call(
                core,
                "presentation.workspace.create_shape",
                {
                    **params,
                    "slide_id": inventory["slide_id"],
                    "shape_type": "rect",
                    "geometry": {
                        "x_emu": 914400,
                        "y_emu": 914400,
                        "width_emu": 914400,
                        "height_emu": 914400,
                    },
                    "fill_color": "#FF0000",
                    "line_color": "#000000",
                },
            )
            params["expected_revision_id"] = created["revision_id"]
            inventory = call(
                core,
                "presentation.workspace.list_text_targets",
                {**scope(params), "slide_number": 1},
            )
        original = path(core, params).read_bytes()
        target = {**params, "slide_id": inventory["slide_id"], "object_id": obj["object_id"]}
        if action == "delete":
            target["expected_geometry"] = obj["geometry"]
            method = "presentation.workspace.delete_object"
        else:
            target.update(
                expected_object_ids=[o["object_id"] for o in inventory["objects"]],
                direction="front" if kind == "chart" else "back",
            )
            method = "presentation.workspace.change_object_layer"
        saved = call(core, method, target)
        assert saved["changed"]
        params["expected_revision_id"] = saved["revision_id"]
        fresh = call(
            core, "presentation.workspace.list_text_targets", {**scope(params), "slide_number": 1}
        )
        ids = [o["object_id"] for o in fresh["objects"]]
        if action == "delete":
            assert ids == [
                o["object_id"] for o in inventory["objects"] if o["object_id"] != obj["object_id"]
            ]
        else:
            assert ids[-1 if kind == "chart" else 0] == obj["object_id"]
            assert {o["object_id"]: o for o in fresh["objects"]} == {
                o["object_id"]: o for o in inventory["objects"]
            }
        with (
            zipfile.ZipFile(io.BytesIO(original)) as before,
            zipfile.ZipFile(path(core, params)) as after,
        ):
            assert before.namelist() == after.namelist()
            assert [n for n in before.namelist() if before.read(n) != after.read(n)] == [
                "ppt/slides/slide1.xml"
            ]
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize(
    "reference", ["connector", "nested_connector", "animation", "chart_build", "placeholder"]
)
def test_graphic_delete_dependency_guard(reference):
    from presenter_core.presentation.fidelity import _delete_geometry_candidate

    pns, ans = _NS["p"], _NS["a"]
    frame = (
        "<p:graphicFrame><p:nvGraphicFramePr><p:nvPr>"
        + ("<p:ph/>" if reference == "placeholder" else "")
        + "</p:nvPr></p:nvGraphicFramePr></p:graphicFrame>"
    )
    connector = (
        '<p:cxnSp><p:nvCxnSpPr><p:cNvCxnSpPr><a:stCxn id="7"/>'
        "</p:cNvCxnSpPr></p:nvCxnSpPr></p:cxnSp>"
    )
    extra = (
        connector
        if reference == "connector"
        else "<p:grpSp>" + connector + "</p:grpSp>"
        if reference == "nested_connector"
        else ""
    )
    timing = '<p:timing><p:spTgt spid="7"/></p:timing>' if reference == "animation" else ""
    if reference == "chart_build":
        timing = '<p:timing><p:bldLst><p:bldGraphic spid="7"/></p:bldLst></p:timing>'
    root = etree.fromstring(
        f'<p:sld xmlns:p="{pns}" xmlns:a="{ans}"><p:cSld><p:spTree>{frame}{extra}'
        f"</p:spTree></p:cSld>{timing}</p:sld>"
    )
    candidate = root.find(".//p:graphicFrame", _NS)
    assert not _delete_geometry_candidate(
        root, candidate, kind="graphicFrame", ooxml_id="7", geometry_editable=True
    )


def test_deleting_chart_preserves_shared_chart_relationship_and_data(tmp_path):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, _ = imported(core, tmp_path, shared=True)
        inventory = call(
            core, "presentation.workspace.list_text_targets", {**scope(params), "slide_number": 1}
        )
        obj = next(o for o in inventory["objects"] if o["kind"] == "graphicFrame")
        original = path(core, params).read_bytes()
        saved = call(
            core,
            "presentation.workspace.delete_object",
            {
                **params,
                "slide_id": inventory["slide_id"],
                "object_id": obj["object_id"],
                "expected_geometry": obj["geometry"],
            },
        )
        params["expected_revision_id"] = saved["revision_id"]
        with (
            zipfile.ZipFile(io.BytesIO(original)) as before,
            zipfile.ZipFile(path(core, params)) as after,
        ):
            assert [n for n in before.namelist() if before.read(n) != after.read(n)] == [
                "ppt/slides/slide1.xml"
            ]
        second = call(
            core, "presentation.workspace.list_text_targets", {**scope(params), "slide_number": 2}
        )
        assert len(second["objects"]) == 1
        charts = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 2}
        )
        assert charts["items"][0]["data"]["title"] == "Imported pilot"
        assert charts["items"][0]["data"]["series"][0]["values"] == [10, 12.25, 15]
    finally:
        core.close()
