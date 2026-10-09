"""Native axes preserve other chart parts and bind staged Copilot settings."""

from __future__ import annotations

import copy
import zipfile

import pytest
from lxml import etree
from test_chart_legend import call, core_at, imported, path, save, scope
from test_copilot_data import DataProvider
from test_copilot_diagrams import operations

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.chart_axes import apply_axis, inspect_axes, validate_settings
from presenter_core.presentation.charts import CNS, NS

DEFAULT = {
    "axis_kind": "value",
    "visible": True,
    "tick_labels": "next_to",
    "major_gridlines": True,
    "minor_gridlines": False,
    "title": None,
    "number_format": None,
    "minimum": None,
    "maximum": None,
    "major_unit": None,
    "minor_unit": None,
}
CHANGE = {
    "title": "Revenue ($)",
    "minimum": -5,
    "maximum": 30,
    "major_unit": 5,
    "minor_unit": 1,
    "number_format": "$0.0",
    "tick_labels": "low",
    "minor_gridlines": True,
}


def prepare(core, params, catalog, **change):
    item = catalog["items"][0]
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Review native axes",
            "operations": [
                {
                    "type": "set_chart_axis",
                    "params": {
                        "slide_id": catalog["slide_id"],
                        "object_id": item["object_id"],
                        "expected_fingerprint": item["fingerprint"],
                        **DEFAULT,
                        **change,
                    },
                }
            ],
        }
    )


def native(core, params):
    with zipfile.ZipFile(path(core, params)) as z:
        # Latest appearance chart is referenced by the slide; old chart parts stay intact.
        candidates = [
            n
            for n in z.namelist()
            if n.startswith("ppt/charts/") and n.endswith(".xml") and "/_rels/" not in n
        ]
        return etree.fromstring(z.read(candidates[-1]))


@pytest.mark.parametrize("kind", ["column", "bar", "line"])
@pytest.mark.parametrize("axis_kind", ["category", "value"])
def test_axes_shared_parts_data_settings_and_exact_undo(tmp_path, kind, axis_kind):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path, kind, shared=True)
        before = path(core, params).read_bytes()
        with zipfile.ZipFile(path(core, params)) as z:
            originals = {n: z.read(n) for n in z.namelist()}
        assert catalog["items"][0]["axes"]["editable"]
        settings = (
            {**CHANGE}
            if axis_kind == "value"
            else {"title": "Period", "tick_labels": "high", "visible": False}
        )
        proposal = prepare(core, params, catalog, axis_kind=axis_kind, **settings)
        assert path(core, params).read_bytes() == before
        save(core, params, proposal)
        after = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
        )
        axis = next(v for v in after["items"][0]["axes"]["axes"] if v["axis_kind"] == axis_kind)
        assert all(
            axis[k] == v
            for k, v in {**DEFAULT, **settings, "axis_kind": axis_kind}.items()
            if v is not None
        )
        for field in ["data", "legend", "labels", "colors"]:
            assert after["items"][0][field] == catalog["items"][0][field]
        untouched = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 2}
        )
        assert untouched["items"][0]["axes"] == catalog["items"][0]["axes"]
        with zipfile.ZipFile(path(core, params)) as z:
            assert {n for n, v in originals.items() if z.read(n) != v} == {
                "[Content_Types].xml",
                "ppt/slides/slide1.xml",
                "ppt/slides/_rels/slide1.xml.rels",
            }
        assert not prepare(core, params, after, axis_kind=axis_kind, **settings)["changed"]
        call(
            core,
            "presentation.workspace.step_revision",
            {
                "project_id": params["project_id"],
                "document_id": params["document_id"],
                "expected_revision_id": params["expected_revision_id"],
                "direction": "undo",
            },
        )
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


@pytest.mark.parametrize(
    "change",
    [
        {"minimum": 5, "maximum": 5},
        {"minimum": float("nan")},
        {"maximum": 1e13},
        {"major_unit": 0},
        {"minor_unit": 2, "major_unit": 1},
        {"axis_kind": "category", "minimum": 0},
        {"axis_kind": "category", "number_format": "0"},
        {"tick_labels": []},
        {"visible": 1},
        {"number_format": ""},
        {"title": "x" * 121},
    ],
)
def test_invalid_axis_inputs(change):
    with pytest.raises(CoreDomainError):
        validate_settings({**DEFAULT, **change})


@pytest.mark.parametrize(
    "variant", ["pie", "secondary", "log", "duplicate", "cross", "extensions", "sparse"]
)
def test_unsupported_axes_are_read_only(tmp_path, variant):
    core = core_at(tmp_path)
    try:
        params, _ = imported(core, tmp_path, "pie" if variant == "pie" else "column")
        chart = native(core, params)
        if variant != "pie":
            plot = chart.find("c:chart/c:plotArea", NS)
            axis = plot.find("c:valAx", NS)
            if variant == "secondary":
                plot.append(copy.deepcopy(axis))
            if variant == "log":
                etree.SubElement(axis.find("c:scaling", NS), f"{{{CNS}}}logBase", val="10")
            if variant == "duplicate":
                etree.SubElement(axis, f"{{{CNS}}}delete", val="1")
            if variant == "cross":
                axis.find("c:crossAx", NS).set("val", axis.find("c:axId", NS).get("val"))
            if variant == "extensions":
                etree.SubElement(axis, f"{{{CNS}}}extLst")
            if variant == "sparse":
                axis.remove(axis.find("c:scaling", NS))
        assert not inspect_axes(chart)["editable"]
        with pytest.raises(CoreDomainError):
            apply_axis(chart, DEFAULT)
    finally:
        core.close()


def test_preserve_axis_style_custom_title_and_auto_reset(tmp_path):
    core = core_at(tmp_path)
    try:
        params, _ = imported(core, tmp_path)
        chart = native(core, params)
        apply_axis(chart, {**DEFAULT, **CHANGE})
        axis = chart.find("c:chart/c:plotArea/c:valAx", NS)
        etree.SubElement(axis, f"{{{CNS}}}spPr", custom="keep")
        title = axis.find("c:title", NS)
        run = title.find("c:tx/c:rich/a:p/a:r", NS)
        run.insert(
            0, etree.Element("{http://schemas.openxmlformats.org/drawingml/2006/main}rPr", b="1")
        )
        styled = copy.deepcopy(axis.find("c:spPr", NS))
        assert apply_axis(chart, {**DEFAULT, "title": "Profit"})
        state = next(v for v in inspect_axes(chart)["axes"] if v["axis_kind"] == "value")
        assert (
            state["minimum"] is None
            and state["maximum"] is None
            and state["major_unit"] is None
            and state["number_format"] == "$0.0"
            and state["title"] == "Profit"
        )
        assert title.find("c:tx/c:rich/a:p/a:r/a:rPr", NS).get("b") == "1"
        assert etree.tostring(
            axis.find("c:spPr", NS), method="c14n", exclusive=True
        ) == etree.tostring(styled, method="c14n", exclusive=True)
        paragraph = title.find("c:tx/c:rich/a:p", NS)
        paragraph.append(copy.deepcopy(run))
        assert (
            inspect_axes(chart)["editable"]
            and not next(v for v in inspect_axes(chart)["axes"] if v["axis_kind"] == "value")[
                "title_editable"
            ]
        )
        with pytest.raises(CoreDomainError):
            apply_axis(chart, {**DEFAULT, "title": "Replace complex"})
        assert apply_axis(chart, {**DEFAULT, "visible": False})
    finally:
        core.close()


def test_copilot_binds_staged_previous_axis_settings(tmp_path):
    provider = DataProvider(locality="local")
    core = core_at(tmp_path, provider)
    try:
        params, _ = imported(core, tmp_path)

        def build(snapshot):
            slide = snapshot["slides"][0]
            item = slide["charts"][0]
            return {
                "summary": "Review axes",
                "operations": operations(
                    [
                        (
                            "set_chart_axis",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": item["object_id"],
                                **DEFAULT,
                                **settings,
                            },
                        )
                        for settings in [
                            CHANGE,
                            {"visible": False, "title": None, "number_format": None},
                        ]
                    ]
                ),
            }

        provider.builder = build
        proposal = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {**params, "instruction": "Set range and hide axis", "slide_numbers": [1]},
        )
        reviews = proposal["review_operations"]
        assert reviews[0]["previous_data"]["minimum"] is None
        assert (
            reviews[1]["previous_data"]["minimum"] == -5
            and reviews[1]["previous_data"]["title"] == "Revenue ($)"
            and reviews[1]["previous_data"]["number_format"] == "$0.0"
        )
        assert (
            reviews[0]["params"]["expected_fingerprint"]
            != reviews[1]["params"]["expected_fingerprint"]
        )
        save(core, params, proposal)
    finally:
        core.close()
