"""Native color edits preserve package dependencies and selected-target scope."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from test_chart_legend import call, core_at, imported, path, save, scope
from test_copilot_data import DataProvider
from test_copilot_diagrams import operations

from presenter_core.errors import CoreDomainError


def prepare_color(core, params, catalog, series=0, point=None, color="#13579B", fingerprint=None):
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Review native chart color",
            "operations": [
                {
                    "type": "set_chart_color",
                    "params": {
                        "slide_id": catalog["slide_id"],
                        "object_id": catalog["items"][0]["object_id"],
                        "expected_fingerprint": fingerprint or catalog["items"][0]["fingerprint"],
                        "series_index": series,
                        "point_index": point,
                        "color": color,
                    },
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "kind,point",
    [("column", None), ("bar", None), ("line", None), ("pie", 1), ("column", 1), ("bar", 1)],
)
def test_color_save_retains_shared_chart_workbooks_data_and_undo(tmp_path: Path, kind, point):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path, kind, shared=True)
        before = path(core, params).read_bytes()
        original_colors = catalog["items"][0]["colors"]
        with zipfile.ZipFile(path(core, params)) as archive:
            parts = {n: archive.read(n) for n in archive.namelist()}
        plan = prepare_color(core, params, catalog, point=point)
        assert path(core, params).read_bytes() == before
        save(core, params, plan)
        item = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
        )["items"][0]
        color = item["colors"]["series"][0]
        assert (color["color"] if point is None else color["points"][point]["color"]) == "#13579B"
        assert (
            item["data"] == catalog["items"][0]["data"]
            and item["legend"] == catalog["items"][0]["legend"]
        )
        assert item["object_id"] == catalog["items"][0]["object_id"]
        assert (
            call(core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 2})[
                "items"
            ][0]["colors"]
            == original_colors
        )
        with zipfile.ZipFile(path(core, params)) as archive:
            changed = {n for n, payload in parts.items() if archive.read(n) != payload}
            assert changed == {
                "[Content_Types].xml",
                "ppt/slides/slide1.xml",
                "ppt/slides/_rels/slide1.xml.rels",
            }
        after = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
        )
        assert not prepare_color(core, params, after, point=point)["changed"]
        result = call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        params["expected_revision_id"] = result["revision_id"]
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


@pytest.mark.parametrize(
    "series,point,color",
    [
        (-1, None, "#13579B"),
        (6, None, "#13579B"),
        (True, None, "#13579B"),
        (0, True, "#13579B"),
        (0, 24, "#13579B"),
        (0, -1, "#13579B"),
        (0, None, "red"),
        (0, None, "#12345Z"),
        (5, None, "#13579B"),
        (0, 23, "#13579B"),
    ],
)
def test_invalid_color_drafts_never_publish(tmp_path: Path, series, point, color):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path)
        before = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError):
            prepare_color(core, params, catalog, series, point, color)
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


@pytest.mark.parametrize("kind,point", [("pie", None), ("line", 1)])
def test_incompatible_native_target_has_explicit_read_only_boundary(tmp_path: Path, kind, point):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path, kind)
        assert not catalog["items"][0]["colors"][
            "series_editable" if point is None else "points_editable"
        ]
        with pytest.raises(CoreDomainError):
            prepare_color(core, params, catalog, point=point)
    finally:
        core.close()


def test_copilot_reviews_staged_colors_and_binds_current_fingerprints(tmp_path: Path):
    provider = DataProvider(locality="local")
    core = core_at(tmp_path, provider)
    try:
        params, catalog = imported(core, tmp_path)
        seen = []

        def build(snapshot):
            slide = snapshot["slides"][0]
            item = slide["charts"][0]
            seen.append(item)
            return {
                "summary": "Review native series and point colors",
                "operations": operations(
                    [
                        (
                            "set_chart_color",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": item["object_id"],
                                "series_index": 0,
                                "point_index": None,
                                "color": "#13579B",
                            },
                        ),
                        (
                            "set_chart_color",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": item["object_id"],
                                "series_index": 0,
                                "point_index": None,
                                "color": "#8642AB",
                            },
                        ),
                        (
                            "set_chart_color",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": item["object_id"],
                                "series_index": 1,
                                "point_index": 1,
                                "color": "#DE4321",
                            },
                        ),
                    ]
                ),
            }

        provider.builder = build
        plan = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {**params, "instruction": "Recolor pilot data.", "slide_numbers": [1]},
        )
        assert "fingerprint" not in seen[0] and seen[0]["colors"]["series"][0]["color"] == "#6E1EA0"
        previous = [v["previous_data"] for v in plan["review_operations"]]
        assert previous[0] == {"series_index": 0, "point_index": None, "color": "#6E1EA0"}
        assert previous[1] == {"series_index": 0, "point_index": None, "color": "#13579B"}
        assert previous[2] == {"series_index": 1, "point_index": 1, "color": None}
        assert len({v["params"]["expected_fingerprint"] for v in plan["review_operations"]}) == 3
        save(core, params, plan)
    finally:
        core.close()


@pytest.mark.parametrize("kind,point", [("column", None), ("line", None), ("pie", 1)])
def test_color_preserves_widths_dashes_effects_markers_and_other_point_overrides(
    tmp_path: Path, kind, point
):
    from lxml import etree

    from presenter_core.presentation.chart_colors import apply_color
    from presenter_core.presentation.charts import CNS, NS, read_chart
    from presenter_core.presentation.fidelity import DRAWING_NS

    core = core_at(tmp_path)
    try:
        params, _ = imported(core, tmp_path, kind)
        with zipfile.ZipFile(path(core, params)) as archive:
            chart = etree.fromstring(archive.read("ppt/charts/chart1.xml"))
        series = chart.find("c:chart/c:plotArea/*/c:ser", NS)
        for index in [0, 1]:
            node = etree.SubElement(series, f"{{{CNS}}}dPt")
            etree.SubElement(node, f"{{{CNS}}}idx", val=str(index))
            props = etree.SubElement(node, f"{{{CNS}}}spPr")
            etree.SubElement(
                etree.SubElement(props, f"{{{DRAWING_NS}}}solidFill"),
                f"{{{DRAWING_NS}}}srgbClr",
                val="224466",
            )
        target = series if point is None else series.findall("c:dPt", NS)[point]
        props = target.find("c:spPr", NS)
        line = etree.SubElement(props, f"{{{DRAWING_NS}}}ln", w="31750", cap="rnd")
        dash = etree.SubElement(line, f"{{{DRAWING_NS}}}prstDash", val="dash")
        effects = etree.SubElement(props, f"{{{DRAWING_NS}}}effectLst")
        etree.SubElement(effects, f"{{{DRAWING_NS}}}glow", rad="12700")
        before_effect = etree.tostring(effects)
        before_dash = etree.tostring(dash)
        other = series.findall("c:dPt", NS)[0]
        before_other = etree.tostring(other)
        before_fill = etree.tostring(props.find("a:solidFill", NS))
        apply_color(chart, read_chart(chart), 0, point, "13579B")
        assert line.attrib == {"w": "31750", "cap": "rnd"}
        assert etree.tostring(effects) == before_effect and etree.tostring(dash) == before_dash
        assert etree.tostring(other) == before_other
        if kind == "line":
            assert etree.tostring(props.find("a:solidFill", NS)) == before_fill
    finally:
        core.close()


def test_stale_color_target_never_stages_or_publishes(tmp_path: Path):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path)
        before = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError) as error:
            prepare_color(core, params, catalog, fingerprint="0" * 64)
        assert error.value.code == "PRESENTATION_EDIT_STALE_TARGET"
        assert (
            path(core, params).read_bytes() == before and not core._presentation_edit_plans._plans
        )
    finally:
        core.close()
