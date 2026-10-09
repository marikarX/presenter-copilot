from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree
from test_chart_legend import call, core_at, imported, path, save, scope
from test_copilot_data import DataProvider
from test_copilot_diagrams import operations

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.chart_markers import SYMBOLS, apply_marker, inspect_markers
from presenter_core.presentation.charts import CNS, NS, read_chart


def prepare(core, params, catalog, symbol="diamond", size=12, index=0):
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Review native line markers",
            "operations": [
                {
                    "type": "set_chart_marker",
                    "params": {
                        "slide_id": catalog["slide_id"],
                        "object_id": catalog["items"][0]["object_id"],
                        "expected_fingerprint": catalog["items"][0]["fingerprint"],
                        "series_index": index,
                        "marker_symbol": symbol,
                        "marker_size": size,
                    },
                }
            ],
        }
    )


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_marker_save_shared_chart_isolation_and_exact_undo(tmp_path: Path, symbol):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path, "line", shared=True)
        original = path(core, params).read_bytes()
        with zipfile.ZipFile(path(core, params)) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        plan = prepare(core, params, catalog, symbol)
        assert path(core, params).read_bytes() == original
        save(core, params, plan)
        after = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
        )["items"][0]
        assert after["markers"]["series"][0]["marker_symbol"] == symbol
        assert after["markers"]["series"][0]["marker_size"] == 12
        assert after["data"] == catalog["items"][0]["data"]
        assert after["colors"] == catalog["items"][0]["colors"]
        assert (
            call(core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 2})[
                "items"
            ][0]["markers"]
            == catalog["items"][0]["markers"]
        )
        with zipfile.ZipFile(path(core, params)) as archive:
            assert {name for name, body in parts.items() if archive.read(name) != body} == {
                "[Content_Types].xml",
                "ppt/slides/slide1.xml",
                "ppt/slides/_rels/slide1.xml.rels",
            }
        updated = {**catalog, "items": [after]}
        assert prepare(core, params, updated, symbol)["changed"] is False
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize(
    "kind,size,symbol",
    [
        ("column", 12, "circle"),
        ("line", True, "circle"),
        ("line", 1, "circle"),
        ("line", 73, "circle"),
        ("line", 7, "picture"),
    ],
)
def test_marker_unsupported_or_invalid_request_does_not_mutate(tmp_path: Path, kind, size, symbol):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path, kind)
        original = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError):
            prepare(core, params, catalog, symbol, size)
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


def test_marker_preserves_custom_properties_and_point_overrides(tmp_path: Path):
    core = core_at(tmp_path)
    try:
        params, _ = imported(core, tmp_path, "line")
        with zipfile.ZipFile(path(core, params)) as archive:
            chart = etree.fromstring(archive.read("ppt/charts/chart1.xml"))
        series = chart.find("c:chart/c:plotArea/c:lineChart/c:ser", NS)
        marker = series.find("c:marker", NS)
        if marker is None:
            marker = etree.SubElement(series, f"{{{CNS}}}marker")
        props = etree.SubElement(marker, f"{{{CNS}}}spPr")
        etree.SubElement(props, "{http://schemas.openxmlformats.org/drawingml/2006/main}solidFill")
        point = etree.SubElement(series, f"{{{CNS}}}dPt")
        etree.SubElement(point, f"{{{CNS}}}idx", val="0")
        override = etree.SubElement(point, f"{{{CNS}}}marker")
        etree.SubElement(override, f"{{{CNS}}}symbol", val="square")
        original_props, original_point = etree.tostring(props), etree.tostring(point)
        data = read_chart(chart)
        assert data is not None
        assert apply_marker(chart, data, 0, "none", 72)
        assert etree.tostring(props) == original_props
        assert etree.tostring(point) == original_point
        assert inspect_markers(chart, data)["series"][0]["point_overrides"] >= 1
        etree.SubElement(marker, f"{{{CNS}}}size", val="7")
        assert not inspect_markers(chart, data)["editable"]
    finally:
        core.close()


def test_copilot_marker_review_uses_staged_previous_values(tmp_path: Path):
    provider = DataProvider(locality="local")
    core = core_at(tmp_path, provider)
    try:
        params, _ = imported(core, tmp_path, "line")

        def build(snapshot):
            slide = snapshot["slides"][0]
            chart = slide["charts"][0]
            assert chart["markers"]["editable"]
            return {
                "summary": "Review line markers",
                "operations": operations(
                    [
                        (
                            "set_chart_marker",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": chart["object_id"],
                                "series_index": 0,
                                "marker_symbol": symbol,
                                "marker_size": size,
                            },
                        )
                        for symbol, size in [("diamond", 12), ("circle", 18)]
                    ]
                ),
            }

        provider.builder = build
        plan = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {**params, "instruction": "Style markers", "slide_numbers": [1]},
        )
        previous = plan["review_operations"][1]["previous_data"]
        assert previous["marker_symbol"] == "diamond" and previous["marker_size"] == 12
        save(core, params, plan)
    finally:
        core.close()


@pytest.mark.parametrize("bad_size", ["1", "73", "x", "9" * 5000])
def test_malformed_native_marker_size_is_read_only_without_unbounded_integer_conversion(
    tmp_path: Path, bad_size
):
    core = core_at(tmp_path)
    try:
        params, _ = imported(core, tmp_path, "line")
        with zipfile.ZipFile(path(core, params)) as archive:
            chart = etree.fromstring(archive.read("ppt/charts/chart1.xml"))
        series = chart.find("c:chart/c:plotArea/c:lineChart/c:ser", NS)
        marker = series.find("c:marker", NS)
        if marker is None:
            marker = etree.SubElement(series, f"{{{CNS}}}marker")
        for existing in marker.findall("c:size", NS):
            marker.remove(existing)
        etree.SubElement(marker, f"{{{CNS}}}size", val=bad_size)
        data = read_chart(chart)
        assert data is not None
        info = inspect_markers(chart, data)
        assert info["editable"] is False
        assert info["series"][0]["marker_size"] is None
    finally:
        core.close()
