"""Native labels preserve chart dependencies and review exact staged settings."""

from __future__ import annotations

import copy
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from test_chart_legend import call, core_at, imported, path, save, scope
from test_copilot_data import DataProvider
from test_copilot_diagrams import operations

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.chart_labels import (
    ALLOWED,
    apply_labels,
    inspect_labels,
    series_nodes,
)
from presenter_core.presentation.charts import CNS, NS, read_chart

DEFAULT = {
    "series_index": None,
    "position": "default",
    "show_value": True,
    "show_category": False,
    "show_series": False,
    "show_percent": False,
    "number_format": None,
}


def prepare(core, params, catalog, **change):
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Review native data labels",
            "operations": [
                {
                    "type": "set_chart_labels",
                    "params": {
                        "slide_id": catalog["slide_id"],
                        "object_id": catalog["items"][0]["object_id"],
                        "expected_fingerprint": catalog["items"][0]["fingerprint"],
                        **DEFAULT,
                        **change,
                    },
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "kind,position",
    [(kind, position) for kind, positions in ALLOWED.items() for position in positions],
)
def test_labels_preserve_shared_workbook_data_and_undo(tmp_path: Path, kind, position):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path, kind, shared=True)
        before = path(core, params).read_bytes()
        with zipfile.ZipFile(path(core, params)) as z:
            parts = {n: z.read(n) for n in z.namelist()}
        proposal = prepare(
            core,
            params,
            catalog,
            position=position,
            show_percent=kind == "pie",
            number_format="0.0%" if kind == "pie" else "$0.00",
        )
        assert path(core, params).read_bytes() == before
        save(core, params, proposal)
        after = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
        )
        labels = after["items"][0]["labels"]["series"][0]
        assert (
            labels["position"] == position
            and labels["show_value"]
            and labels["show_percent"] == (kind == "pie")
        )
        assert labels["number_format"] == ("0.0%" if kind == "pie" else "$0.00")
        assert after["items"][0]["data"] == catalog["items"][0]["data"]
        assert (
            after["items"][0]["legend"] == catalog["items"][0]["legend"]
            and after["items"][0]["colors"] == catalog["items"][0]["colors"]
        )
        untouched = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 2}
        )
        assert untouched["items"][0]["labels"] == catalog["items"][0]["labels"]
        with zipfile.ZipFile(path(core, params)) as z:
            assert {n for n, value in parts.items() if z.read(n) != value} == {
                "[Content_Types].xml",
                "ppt/slides/slide1.xml",
                "ppt/slides/_rels/slide1.xml.rels",
            }
        assert not prepare(
            core,
            params,
            after,
            position=position,
            show_percent=kind == "pie",
            number_format="0.0%" if kind == "pie" else "$0.00",
        )["changed"]
        undo = call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        params["expected_revision_id"] = undo["revision_id"]
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


@pytest.mark.parametrize(
    "change",
    [
        {"series_index": True},
        {"series_index": 6},
        {"series_index": -1},
        {"show_value": 1},
        {"show_category": "true"},
        {"show_percent": True},
        {"position": "best_fit"},
        {"position": []},
        {"number_format": ""},
        {"number_format": "x" * 65},
        {"number_format": "a\nb"},
        {"position": "center", "show_value": False},
    ],
)
def test_invalid_labels_do_not_publish(tmp_path, change):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path)
        before = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError):
            prepare(core, params, catalog, **change)
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


@pytest.mark.parametrize("global_override", [False, True])
def test_label_decoration_custom_text_number_formats_and_hide_are_retained(
    tmp_path, global_override
):
    core = core_at(tmp_path)
    try:
        params, _ = imported(core, tmp_path)
        with zipfile.ZipFile(path(core, params)) as z:
            chart = etree.fromstring(z.read("ppt/charts/chart1.xml"))
        node = series_nodes(chart)[0]
        parent = node.getparent() if global_override else node
        labels = etree.SubElement(parent, f"{{{CNS}}}dLbls")
        point = etree.SubElement(labels, f"{{{CNS}}}dLbl")
        etree.SubElement(point, f"{{{CNS}}}idx", val="1")
        tx = etree.SubElement(point, f"{{{CNS}}}tx")
        rich = etree.SubElement(tx, f"{{{CNS}}}rich")
        rich.text = "retained custom text"
        etree.SubElement(point, f"{{{CNS}}}numFmt", formatCode="0.000", sourceLinked="0")
        sp = etree.SubElement(point, f"{{{CNS}}}spPr")
        sp.text = "retained decoration"
        original_tx = etree.tostring(tx, method="c14n", exclusive=True)
        original_sp = etree.tostring(sp, method="c14n", exclusive=True)
        data = read_chart(chart)
        assert inspect_labels(chart, data)["editable"]
        assert apply_labels(
            chart, {**DEFAULT, "series_index": 0, "position": "outside_end", "show_category": True}
        )
        fresh = series_nodes(chart)[0].find("c:dLbls/c:dLbl", NS)
        assert etree.tostring(fresh.find("c:tx", NS), method="c14n", exclusive=True) == original_tx
        assert (
            etree.tostring(fresh.find("c:spPr", NS), method="c14n", exclusive=True) == original_sp
        )
        assert fresh.find("c:numFmt", NS).get("formatCode") == "0.000"
        before_hide = copy.deepcopy(chart)
        assert apply_labels(chart, {**DEFAULT, "series_index": 0, "position": "hidden"})
        for tree in [before_hide, chart]:
            for delete in tree.findall(".//c:delete", NS):
                delete.getparent().remove(delete)
        assert etree.tostring(before_hide, method="c14n") == etree.tostring(chart, method="c14n")
    finally:
        core.close()


def test_copilot_binds_exact_staged_label_values(tmp_path):
    provider = DataProvider(locality="local")
    core = core_at(tmp_path, provider)
    try:
        params, _ = imported(core, tmp_path)

        def build(snapshot):
            slide = snapshot["slides"][0]
            chart = slide["charts"][0]
            return {
                "summary": "Review labels",
                "operations": operations(
                    [
                        (
                            "set_chart_labels",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": chart["object_id"],
                                **DEFAULT,
                                "position": position,
                                "number_format": fmt,
                            },
                        )
                        for position, fmt in [("outside_end", "0.0"), ("center", None)]
                    ]
                ),
            }

        provider.builder = build
        proposal = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {**params, "instruction": "Add value labels.", "slide_numbers": [1]},
        )
        reviews = proposal["review_operations"]
        assert reviews[0]["previous_data"]["label_series"][0]["position"] == "hidden"
        assert reviews[1]["previous_data"]["label_series"][0]["position"] == "outside_end"
        assert reviews[1]["previous_data"]["label_series"][0]["number_format"] == "0.0"
        assert (
            reviews[0]["params"]["expected_fingerprint"]
            != reviews[1]["params"]["expected_fingerprint"]
        )
        save(core, params, proposal)
    finally:
        core.close()


@pytest.mark.parametrize("tag,attrs", [("layout", {}), ("showVal", {"val": "unknown"})])
def test_unsupported_native_label_properties_stay_read_only(tmp_path, tag, attrs):
    core = core_at(tmp_path)
    try:
        params, _ = imported(core, tmp_path)
        with zipfile.ZipFile(path(core, params)) as z:
            chart = etree.fromstring(z.read("ppt/charts/chart1.xml"))
        labels = etree.SubElement(series_nodes(chart)[0], f"{{{CNS}}}dLbls")
        node = etree.SubElement(labels, f"{{{CNS}}}{tag}", **attrs)
        if tag == "layout":
            etree.SubElement(node, f"{{{CNS}}}manualLayout")
        assert not inspect_labels(chart, read_chart(chart))["editable"]
        before = etree.tostring(chart)
        with pytest.raises(CoreDomainError):
            apply_labels(chart, DEFAULT)
        assert etree.tostring(chart) == before
    finally:
        core.close()


def test_single_series_override_retains_plot_defaults_and_other_series(tmp_path):
    core = core_at(tmp_path)
    try:
        params, _ = imported(core, tmp_path)
        with zipfile.ZipFile(path(core, params)) as z:
            chart = etree.fromstring(z.read("ppt/charts/chart1.xml"))
        first = series_nodes(chart)[0]
        global_labels = etree.SubElement(first.getparent(), f"{{{CNS}}}dLbls")
        etree.SubElement(global_labels, f"{{{CNS}}}showVal", val="1")
        before = etree.tostring(first)
        plot_before = etree.tostring(global_labels)
        assert apply_labels(chart, {**DEFAULT, "series_index": 1, "position": "center"})
        assert etree.tostring(first) == before and etree.tostring(global_labels) == plot_before
        info = inspect_labels(chart, read_chart(chart))
        assert (
            info["series"][0]["position"] == "default" and info["series"][1]["position"] == "center"
        )
    finally:
        core.close()


def test_stale_chart_label_fingerprint_does_not_publish(tmp_path):
    core = core_at(tmp_path)
    try:
        params, catalog = imported(core, tmp_path)
        before = path(core, params).read_bytes()
        catalog["items"][0]["fingerprint"] = "0" * 64
        with pytest.raises(CoreDomainError):
            prepare(core, params, catalog)
        assert path(core, params).read_bytes() == before
    finally:
        core.close()
