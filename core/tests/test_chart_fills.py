from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree
from test_chart_legend import call, core_at, imported, path, save, scope
from test_copilot_data import DataProvider
from test_copilot_diagrams import operations

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.chart_fills import (
    apply_fill,
    describe_fill,
    inspect_fills,
    validate_fill,
)
from presenter_core.presentation.charts import NS, read_chart

SOLID = {"kind": "solid", "color": "#13579B", "opacity_percent": 35}
GRADIENT = {
    "kind": "linear_gradient",
    "angle_degrees": 45,
    "stops": [
        {"position_percent": 0, "color": "#13579B", "opacity_percent": 100},
        {"position_percent": 50, "color": "#8642AB", "opacity_percent": 65},
        {"position_percent": 100, "color": "#DE4321", "opacity_percent": 20},
    ],
}


def prepare(core, params, catalog, fill, point=None, series=0):
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Review native fill",
            "operations": [
                {
                    "type": "set_chart_fill",
                    "params": {
                        "slide_id": catalog["slide_id"],
                        "object_id": catalog["items"][0]["object_id"],
                        "expected_fingerprint": catalog["items"][0]["fingerprint"],
                        "series_index": series,
                        "point_index": point,
                        "fill": fill,
                    },
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "kind,point",
    [("column", None), ("bar", None), ("line", None), ("pie", 1), ("column", 1), ("bar", 1)],
)
@pytest.mark.parametrize("fill", [SOLID, GRADIENT])
def test_native_fill_roundtrip_shared_isolation_and_exact_undo(tmp_path: Path, kind, point, fill):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path, kind, shared=True)
        original = path(core, params).read_bytes()
        with zipfile.ZipFile(path(core, params)) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        plan = prepare(core, params, catalog, fill, point)
        assert path(core, params).read_bytes() == original
        save(core, params, plan)
        after = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
        )["items"][0]
        state = after["fills"]["series"][0]
        assert (state["fill"] if point is None else state["points"][point]["fill"]) == fill
        for field in ("data", "legend", "labels", "axes", "markers"):
            assert after[field] == catalog["items"][0][field]
        assert (
            call(core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 2})[
                "items"
            ][0]["fills"]
            == catalog["items"][0]["fills"]
        )
        with zipfile.ZipFile(path(core, params)) as archive:
            assert {name for name, body in parts.items() if archive.read(name) != body} == {
                "[Content_Types].xml",
                "ppt/slides/slide1.xml",
                "ppt/slides/_rels/slide1.xml.rels",
            }
        assert not prepare(core, params, {**catalog, "items": [after]}, fill, point)["changed"]
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        {**SOLID, "opacity_percent": True},
        {**SOLID, "opacity_percent": 101},
        {**SOLID, "color": "not rgb"},
        {**SOLID, "unknown": True},
        {**GRADIENT, "angle_degrees": 360},
        {**GRADIENT, "stops": []},
        {**GRADIENT, "stops": [GRADIENT["stops"][1], GRADIENT["stops"][0]]},
        {**GRADIENT, "stops": [GRADIENT["stops"][0], GRADIENT["stops"][0], GRADIENT["stops"][2]]},
        {
            **GRADIENT,
            "stops": [{**GRADIENT["stops"][0], "opacity_percent": -1}, GRADIENT["stops"][2]],
        },
    ],
)
def test_fill_invalid_data_rejected(bad):
    with pytest.raises(CoreDomainError):
        validate_fill(bad)


@pytest.mark.parametrize("kind,point", [("line", 0), ("pie", None)])
def test_fill_incompatible_target_keeps_source_exact(tmp_path: Path, kind, point):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path, kind)
        original = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError):
            prepare(core, params, catalog, SOLID, point)
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize("kind", ["column", "line"])
def test_fill_changes_only_selected_fill_and_preserves_other_style_content(tmp_path: Path, kind):
    core = core_at(tmp_path)
    try:
        params, _ = imported(core, tmp_path, kind)
        with zipfile.ZipFile(path(core, params)) as archive:
            chart = etree.fromstring(archive.read("ppt/charts/chart1.xml"))
        node = chart.find("c:chart/c:plotArea/*/c:ser", NS)
        props = node.find("c:spPr", NS)
        line = props.find("a:ln", NS)
        if line is None:
            line = etree.SubElement(
                props, "{http://schemas.openxmlformats.org/drawingml/2006/main}ln"
            )
        line.set("w", "38100")
        dash = etree.SubElement(
            line, "{http://schemas.openxmlformats.org/drawingml/2006/main}prstDash", val="dash"
        )
        before_line = etree.tostring(line)
        before_dash = etree.tostring(dash)
        data = read_chart(chart)
        assert data is not None
        assert apply_fill(chart, data, 0, None, GRADIENT)
        if kind == "column":
            assert etree.tostring(line) == before_line
        else:
            assert line.get("w") == "38100" and etree.tostring(dash) == before_dash
        assert inspect_fills(chart, data)["series"][0]["fill"] == GRADIENT
        gradient = props.find("a:ln/a:gradFill" if kind == "line" else "a:gradFill", NS)
        gradient.set("rotWithShape", "0")
        assert describe_fill(line if kind == "line" else props)["kind"] == "native_custom"
    finally:
        core.close()


def test_copilot_fill_uses_exact_staged_previous_data(tmp_path: Path):
    provider = DataProvider(locality="local")
    core = core_at(tmp_path, provider)
    try:
        params, _ = imported(core, tmp_path)

        def build(snapshot):
            slide = snapshot["slides"][0]
            chart = slide["charts"][0]
            assert chart["fills"]["editable"]
            return {
                "summary": "Review chart fills",
                "operations": operations(
                    [
                        (
                            "set_chart_fill",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": chart["object_id"],
                                "series_index": 0,
                                "point_index": None,
                                "fill": value,
                            },
                        )
                        for value in (SOLID, GRADIENT)
                    ]
                ),
            }

        provider.builder = build
        plan = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {**params, "instruction": "Style fills", "slide_numbers": [1]},
        )
        assert plan["review_operations"][1]["previous_data"]["fill"] == SOLID
        save(core, params, plan)
    finally:
        core.close()
