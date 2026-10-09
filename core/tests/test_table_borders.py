"""Range borders preserve native content and synchronize reciprocal shared sides."""

from __future__ import annotations

import copy
import zipfile

import pytest
from lxml import etree
from test_chart_legend import core_at
from test_copilot_data import DataProvider
from test_copilot_diagrams import operations
from test_presentation_edit_planning import call
from test_presentation_native_layouts import path, scope
from test_selection_actions import save
from test_table_structure import fixture

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.fidelity import _NS, DRAWING_NS
from presenter_core.presentation.table_borders import (
    PRESETS,
    SIDES,
    inspect_borders,
    selected_edges,
    set_borders,
)

DEFAULT = {
    "row_start": 0,
    "row_end": 1,
    "column_start": 0,
    "column_end": 1,
    "border_scope": "outline",
    "line_style": "solid",
    "width_pt": 2.5,
    "color": "#A12266",
}


def catalog(core, params):
    return call(core, "presentation.workspace.list_tables", {**scope(params), "slide_number": 1})


def prepare(core, params, info, **change):
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Review range borders",
            "operations": [
                {
                    "type": "set_table_borders",
                    "params": {
                        "slide_id": info["slide_id"],
                        "object_id": info["items"][0]["object_id"],
                        "expected_fingerprint": info["items"][0]["fingerprint"],
                        **DEFAULT,
                        **change,
                    },
                }
            ],
        }
    )


def frame(core, params):
    with zipfile.ZipFile(path(core, params)) as z:
        return etree.fromstring(z.read("ppt/slides/slide1.xml")).find(
            "p:cSld/p:spTree/p:graphicFrame", _NS
        )


@pytest.mark.parametrize("border_scope", sorted(PRESETS))
@pytest.mark.parametrize("line_style", ["solid", "dash", "dot", "none"])
def test_preserve_native_content_parts_shared_edges_and_exact_undo(
    tmp_path, border_scope, line_style
):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        info = catalog(core, params)
        before = path(core, params).read_bytes()
        with zipfile.ZipFile(path(core, params)) as z:
            parts = {n: z.read(n) for n in z.namelist()}
        options = {
            "border_scope": border_scope,
            "line_style": line_style,
            **({"width_pt": None, "color": None} if line_style == "none" else {}),
        }
        proposed = prepare(core, params, info, **options)
        assert path(core, params).read_bytes() == before
        save(core, params, proposed)
        after = catalog(core, params)
        assert (
            after["items"][0]["cells"] == info["items"][0]["cells"]
            and after["items"][0]["formatting"] == info["items"][0]["formatting"]
        )
        cells = after["items"][0]["borders"]["cell_borders"]
        edges = selected_edges({**DEFAULT, **options}, cells)
        for r, c, side in edges:
            value = cells[r][c][side]
            assert value["line_style"] == line_style and value["visible"] == (line_style != "none")
            if line_style != "none":
                assert value["width_pt"] == 2.5 and value["color"] == "#A12266"
        with zipfile.ZipFile(path(core, params)) as z:
            assert {n for n, v in parts.items() if z.read(n) != v} == {"ppt/slides/slide1.xml"}
        assert not prepare(core, params, after, **options)["changed"]
        undo = call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        params["expected_revision_id"] = undo["revision_id"]
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


@pytest.mark.parametrize(
    "change",
    [
        {"width_pt": True},
        {"width_pt": 0},
        {"width_pt": float("nan")},
        {"width_pt": 13},
        {"color": "#1234"},
        {"border_scope": []},
        {"line_style": []},
        {"line_style": "none"},
        {"row_end": 12},
        {"column_start": -1},
        {"row_start": 2, "row_end": 1},
        {"border_scope": "inside", "row_end": 0, "column_end": 0},
    ],
)
def test_invalid_borders_never_publish(tmp_path, change):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        info = catalog(core, params)
        before = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError):
            prepare(core, params, info, **change)
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


def test_only_selected_edges_and_reciprocal_neighbors_change(tmp_path):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        table = frame(core, params)
        rows = table.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS)
        cell = rows[0].findall("a:tc", _NS)[0]
        tc = cell.find("a:tcPr", _NS)
        etree.SubElement(tc, f"{{{DRAWING_NS}}}lnTlToBr", w="12700")
        before = copy.deepcopy(table)
        settings = {
            **DEFAULT,
            "row_start": 1,
            "row_end": 1,
            "column_start": 1,
            "column_end": 1,
            "border_scope": "outline",
        }
        edges = selected_edges(settings, [[None] * 3 for _ in range(3)])
        assert (
            len(edges) == 8
            and (0, 1, "bottom") in edges
            and (1, 0, "right") in edges
            and (2, 1, "top") in edges
            and (1, 2, "left") in edges
        )
        assert set_borders(table, settings)
        for tree in [before, table]:
            rr = tree.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS)
            for r, c, side in edges:
                pr = rr[r].findall("a:tc", _NS)[c].find("a:tcPr", _NS)
                for n in pr.findall("a:" + SIDES[side], _NS):
                    pr.remove(n)
        assert etree.tostring(before, method="c14n", exclusive=True) == etree.tostring(
            table, method="c14n", exclusive=True
        )
    finally:
        core.close()


def test_ambiguous_edges_stay_read_only(tmp_path):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        table = frame(core, params)
        pr = table.find("a:graphic/a:graphicData/a:tbl/a:tr/a:tc/a:tcPr", _NS)
        for _ in range(2):
            etree.SubElement(pr, f"{{{DRAWING_NS}}}lnL")
        assert not inspect_borders(table)["editable"]
        with pytest.raises(CoreDomainError):
            set_borders(table, DEFAULT)
    finally:
        core.close()


def test_copilot_reviews_exact_staged_neighbor_edges(tmp_path):
    provider = DataProvider(locality="local")
    core = core_at(tmp_path, provider)
    try:
        params, _, _ = fixture(core)

        def build(snapshot):
            slide = snapshot["slides"][0]
            table = slide["tables"][0]
            return {
                "summary": "Review border removal",
                "operations": operations(
                    [
                        (
                            "set_table_borders",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": table["object_id"],
                                **DEFAULT,
                                **change,
                            },
                        )
                        for change in [{}, {"line_style": "none", "width_pt": None, "color": None}]
                    ]
                ),
            }

        provider.builder = build
        proposed = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {**params, "instruction": "Outline then remove borders", "slide_numbers": [1]},
        )
        reviews = proposed["review_operations"]
        assert (
            reviews[0]["params"]["expected_fingerprint"]
            != reviews[1]["params"]["expected_fingerprint"]
        )
        assert all(
            v["width_pt"] == 2.5 and v["color"] == "#A12266" and v["line_style"] == "solid"
            for v in reviews[1]["previous_data"]["border_edges"]
        )
        save(core, params, proposed)
    finally:
        core.close()
