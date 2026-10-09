"""Merge/split acceptance includes native spans and subsequent edit dependencies."""

from __future__ import annotations

import copy
import zipfile

import pytest
from lxml import etree
from test_chart_legend import core_at
from test_copilot_data import DataProvider
from test_copilot_diagrams import operations
from test_presentation_edit_planning import call
from test_presentation_native_layouts import path
from test_selection_actions import save
from test_table_borders import DEFAULT, catalog, frame
from test_table_structure import fixture

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.fidelity import _NS
from presenter_core.presentation.table_borders import inspect_borders, logical_edges, set_borders
from presenter_core.presentation.table_merge import ATTRS, grid, merge_cells
from presenter_core.presentation.tables import inspect_table

RANGE = {"row_start": 0, "row_end": 1, "column_start": 0, "column_end": 1}


def prepare(core, params, info, kind="merge_table_cells", **options):
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Review merged table cells",
            "operations": [
                {
                    "type": kind,
                    "params": {
                        "slide_id": info["slide_id"],
                        "object_id": info["items"][0]["object_id"],
                        "expected_fingerprint": info["items"][0]["fingerprint"],
                        **RANGE,
                        **options,
                    },
                }
            ],
        },
    )


@pytest.mark.parametrize("rows,cols", [(1, 2), (1, 3), (2, 1), (3, 1), (2, 2), (3, 3)])
def test_merge_split_preserve_styles_parts_grid_text_and_exact_undo(tmp_path, rows, cols):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        info = catalog(core, params)
        original = path(core, params).read_bytes()
        before = frame(core, params)
        cells = info["items"][0]["cells"]
        expected = "\n".join(v for row in cells[:rows] for v in row[:cols] if v)
        options = {"row_end": rows - 1, "column_end": cols - 1}
        save(core, params, prepare(core, params, info, **options))
        fresh = catalog(core, params)
        item = fresh["items"][0]
        assert item["editable"] and not item["structure_editable"]
        assert item["cells"][0][0] == expected
        assert item["spans"]["regions"] == [
            {"row": 0, "column": 0, "row_span": rows, "column_span": cols}
        ]
        merged = path(core, params).read_bytes()
        with zipfile.ZipFile(path(core, params)) as new:
            import io

            with zipfile.ZipFile(io.BytesIO(original)) as old:
                assert [n for n in old.namelist() if old.read(n) != new.read(n)] == [
                    "ppt/slides/slide1.xml"
                ]
        for tree in [before, frame(core, params)]:
            for r, row in enumerate(grid(tree)):
                for c, cell in enumerate(row):
                    if r < rows and c < cols:
                        for key in ATTRS:
                            cell.attrib.pop(key, None)
                        cell.remove(cell.find("a:txBody", _NS))
        assert etree.tostring(before, method="c14n", exclusive=True) == etree.tostring(
            frame_stripped(core, params, rows, cols), method="c14n", exclusive=True
        )
        assert not prepare(core, params, fresh, **options)["changed"]
        save(core, params, prepare(core, params, fresh, "split_table_cells", **options))
        split = catalog(core, params)["items"][0]
        assert split["editable"] and split["structure_editable"] and not split["spans"]["regions"]
        assert split["cells"] == item["cells"]
        undo = call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        params["expected_revision_id"] = undo["revision_id"]
        assert path(core, params).read_bytes() == merged
        undo = call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        params["expected_revision_id"] = undo["revision_id"]
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


def frame_stripped(core, params, rows, cols):
    tree = frame(core, params)
    for r, row in enumerate(grid(tree)):
        for c, cell in enumerate(row):
            if r < rows and c < cols:
                for k in ATTRS:
                    cell.attrib.pop(k, None)
                cell.remove(cell.find("a:txBody", _NS))
    return tree


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("rowSpan", "99"),
        ("gridSpan", "0"),
        ("hMerge", "true"),
        ("vMerge", "1"),
        ("hMerge", "2"),
        ("gridSpan", "nan"),
        ("id", "x"),
    ],
)
def test_malformed_spans_remain_read_only(tmp_path, attribute, value):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        tree = frame(core, params)
        grid(tree)[0][0].set(attribute, value)
        assert not inspect_table(tree)["editable"]
    finally:
        core.close()


def test_merged_paragraph_styles_survive_text_format_border_and_split(tmp_path):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        info = catalog(core, params)
        save(core, params, prepare(core, params, info))
        fresh = catalog(core, params)
        table = fresh["items"][0]
        tree = frame(core, params)
        original_paragraphs = [
            etree.tostring(p.find("a:r/a:rPr", _NS), method="c14n", exclusive=True)
            for p in grid(tree)[0][0].findall("a:txBody/a:p", _NS)
        ]
        cells = copy.deepcopy(table["cells"])
        cells[0][0] = "Header\nCurrent\nRevenue\n$11M"
        save(
            core,
            params,
            call(
                core,
                "presentation.workspace.prepare_edit_plan",
                {
                    **params,
                    "summary": "Edit merged text",
                    "operations": [
                        {
                            "type": "replace_table_cells",
                            "params": {
                                "slide_id": fresh["slide_id"],
                                "object_id": table["object_id"],
                                "expected_fingerprint": table["fingerprint"],
                                "cells": cells,
                            },
                        }
                    ],
                },
            ),
        )
        assert [
            etree.tostring(p.find("a:r/a:rPr", _NS), method="c14n", exclusive=True)
            for p in grid(frame(core, params))[0][0].findall("a:txBody/a:p", _NS)
        ] == original_paragraphs
        fresh = catalog(core, params)
        with pytest.raises(CoreDomainError):
            prepare(core, params, fresh, row_end=0)
        before = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError):
            prepare(core, params, fresh, "format_table_cells", row_end=0, style={"bold": True})
        assert path(core, params).read_bytes() == before
        save(
            core,
            params,
            prepare(
                core,
                params,
                fresh,
                "format_table_cells",
                style={"bold": True, "fill_color": "#FFEE99"},
            ),
        )
        fresh = catalog(core, params)
        save(
            core,
            params,
            prepare(
                core,
                params,
                fresh,
                "set_table_borders",
                **{k: v for k, v in DEFAULT.items() if k not in RANGE},
            ),
        )
        tree = frame(core, params)
        assert logical_edges(DEFAULT, inspect_borders(tree)) == [
            (0, 0, "bottom"),
            (0, 0, "left"),
            (0, 0, "right"),
            (0, 0, "top"),
            (0, 2, "left"),
            (1, 2, "left"),
            (2, 0, "top"),
            (2, 1, "top"),
        ]
        assert not set_borders(tree, DEFAULT)
        fresh = catalog(core, params)
        save(core, params, prepare(core, params, fresh, "split_table_cells"))
        assert catalog(core, params)["items"][0]["cells"] == cells
    finally:
        core.close()


def test_copilot_merge_then_split_uses_actual_staged_regions(tmp_path):
    provider = DataProvider(locality="local")
    core = core_at(tmp_path, provider)
    try:
        params, _, _ = fixture(core)

        def build(snapshot):
            slide = snapshot["slides"][0]
            table = slide["tables"][0]
            return {
                "summary": "Review merge then split",
                "operations": operations(
                    [
                        (
                            kind,
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": table["object_id"],
                                **RANGE,
                            },
                        )
                        for kind in ["merge_table_cells", "split_table_cells"]
                    ]
                ),
            }

        provider.builder = build
        plan = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {**params, "instruction": "Merge then split", "slide_numbers": [1]},
        )
        reviews = plan["review_operations"]
        assert not reviews[0]["previous_data"]["merge_regions"]
        assert len(reviews[1]["previous_data"]["merge_regions"]) == 1
        assert (
            reviews[0]["params"]["expected_fingerprint"]
            != reviews[1]["params"]["expected_fingerprint"]
        )
        save(core, params, plan)
        assert not catalog(core, params)["items"][0]["spans"]["regions"]
    finally:
        core.close()


def test_covered_text_cannot_be_written_and_failed_plan_preserves_head(tmp_path):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        save(core, params, prepare(core, params, catalog(core, params)))
        fresh = catalog(core, params)
        table = fresh["items"][0]
        cells = copy.deepcopy(table["cells"])
        cells[0][1] = "Hidden change"
        original = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError, match="top-left"):
            core._presentation_edit_plans.prepare(
                {
                    **params,
                    "summary": "Invalid covered edit",
                    "operations": [
                        {
                            "type": "replace_table_cells",
                            "params": {
                                "slide_id": fresh["slide_id"],
                                "object_id": table["object_id"],
                                "expected_fingerprint": table["fingerprint"],
                                "cells": cells,
                            },
                        }
                    ],
                }
            )
        assert path(core, params).read_bytes() == original
        assert catalog(core, params)["items"][0]["fingerprint"] == table["fingerprint"]
    finally:
        core.close()


def test_large_merge_text_and_latent_covered_text_are_rejected(tmp_path):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        tree = frame(core, params)
        grid(tree)[0][0].find("a:txBody/a:p/a:r/a:t", _NS).text = "x" * 300
        grid(tree)[0][1].find("a:txBody/a:p/a:r/a:t", _NS).text = "y" * 300
        with pytest.raises(CoreDomainError, match="Combined text"):
            merge_cells(core._presentation_edits, tree, RANGE, split=False)
        tree = frame(core, params)
        merge_cells(core._presentation_edits, tree, RANGE, split=False)
        grid(tree)[0][1].find("a:txBody/a:p/a:r/a:t", _NS).text = "invisible native content"
        assert not inspect_table(tree)["editable"]
        assert "Hidden content" in inspect_table(tree)["reason"]
    finally:
        core.close()


def test_partially_intersected_neighbor_border_is_rejected_before_mutation(tmp_path):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        tree = frame(core, params)
        merge_cells(
            core._presentation_edits,
            tree,
            {**RANGE, "row_end": 2, "column_start": 2, "column_end": 2},
            split=False,
        )
        before = etree.tostring(tree)
        with pytest.raises(CoreDomainError, match="neighboring merged cell"):
            set_borders(
                tree, {**DEFAULT, "row_start": 1, "row_end": 1, "column_start": 1, "column_end": 1}
            )
        assert etree.tostring(tree) == before
    finally:
        core.close()
