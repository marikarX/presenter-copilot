"""Range table styles keep original text, native cells and revision authority intact."""

from __future__ import annotations

import zipfile
from pathlib import Path

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
from presenter_core.presentation.fidelity import _NS
from presenter_core.presentation.table_format import FIELDS

STYLE = {
    "bold": False,
    "italic": True,
    "underline": True,
    "font_size_pt": 20,
    "font_color": "#224466",
    "fill_color": "#EAF1FA",
    "alignment": "right",
    "vertical_alignment": "bottom",
}


def catalog(core, params):
    return call(core, "presentation.workspace.list_tables", {**scope(params), "slide_number": 1})


def prepare(core, params, info, style=None, **range_values):
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Review cell styles",
            "operations": [
                {
                    "type": "format_table_cells",
                    "params": {
                        "slide_id": info["slide_id"],
                        "object_id": info["items"][0]["object_id"],
                        "expected_fingerprint": info["items"][0]["fingerprint"],
                        "row_start": 0,
                        "row_end": 0,
                        "column_start": 0,
                        "column_end": 2,
                        "style": STYLE if style is None else style,
                        **range_values,
                    },
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "row_start,row_end,column_start,column_end", [(0, 0, 0, 2), (0, 2, 0, 2), (1, 2, 1, 1)]
)
def test_style_range_preserves_cells_dimensions_borders_other_parts_and_undo(
    tmp_path: Path, row_start, row_end, column_start, column_end
):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        info = catalog(core, params)
        before = path(core, params).read_bytes()
        with zipfile.ZipFile(path(core, params)) as z:
            original = {n: z.read(n) for n in z.namelist()}
            root = etree.fromstring(original["ppt/slides/slide1.xml"])
            oldcells = root.findall(".//a:tbl/a:tr/a:tc", _NS)
            borders = [
                [
                    etree.tostring(v)
                    for v in cell.findall("a:tcPr/*", _NS)
                    if etree.QName(v).localname.startswith("ln")
                ]
                for cell in oldcells
            ]
            margins = [
                {k: v for k, v in cell.find("a:tcPr", _NS).attrib.items() if k.startswith("mar")}
                for cell in oldcells
            ]
        bounds = dict(
            row_start=row_start, row_end=row_end, column_start=column_start, column_end=column_end
        )
        proposal = prepare(core, params, info, **bounds)
        assert path(core, params).read_bytes() == before
        save(core, params, proposal)
        after = catalog(core, params)
        assert after["items"][0]["cells"] == info["items"][0]["cells"]
        assert after["items"][0]["object_id"] == info["items"][0]["object_id"]
        styles = after["items"][0]["formatting"]["cell_styles"]
        for r, row in enumerate(styles):
            for c, style in enumerate(row):
                assert style == (
                    STYLE
                    if row_start <= r <= row_end and column_start <= c <= column_end
                    else info["items"][0]["formatting"]["cell_styles"][r][c]
                )
        with zipfile.ZipFile(path(core, params)) as z:
            assert {n for n, payload in original.items() if z.read(n) != payload} == {
                "ppt/slides/slide1.xml"
            }
            cells = etree.fromstring(z.read("ppt/slides/slide1.xml")).findall(
                ".//a:tbl/a:tr/a:tc", _NS
            )
            assert margins == [
                {k: v for k, v in cell.find("a:tcPr", _NS).attrib.items() if k.startswith("mar")}
                for cell in cells
            ]
            assert borders == [
                [
                    etree.tostring(v)
                    for v in cell.findall("a:tcPr/*", _NS)
                    if etree.QName(v).localname.startswith("ln")
                ]
                for cell in cells
            ]
        assert not prepare(core, params, after, **bounds)["changed"]
        result = call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        params["expected_revision_id"] = result["revision_id"]
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"bold": 1},
        {"italic": "on"},
        {"font_size_pt": True},
        {"font_size_pt": 5},
        {"font_size_pt": 97},
        {"fill_color": "red"},
        {"font_color": "#12345Z"},
        {"alignment": "diagonal"},
        {"vertical_alignment": "middle"},
        {"unknown": True},
    ],
)
def test_invalid_styles_do_not_publish(tmp_path: Path, change):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        info = catalog(core, params)
        before = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError):
            prepare(core, params, info, style=change)
        assert (
            path(core, params).read_bytes() == before and not core._presentation_edit_plans._plans
        )
    finally:
        core.close()


@pytest.mark.parametrize(
    "bad_range",
    [
        {"row_start": True},
        {"row_start": -1},
        {"row_end": 3},
        {"column_end": 8},
        {"row_start": 2, "row_end": 0},
        {"column_start": 2, "column_end": 0},
    ],
)
def test_invalid_or_reversed_ranges_do_not_publish(tmp_path: Path, bad_range):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        info = catalog(core, params)
        before = path(core, params).read_bytes()
        with pytest.raises(CoreDomainError):
            prepare(core, params, info, **bad_range)
        assert path(core, params).read_bytes() == before
    finally:
        core.close()


def test_copilot_styles_bind_staged_fingerprints_and_previous_native_values(tmp_path: Path):
    provider = DataProvider(locality="local")
    core = core_at(tmp_path, provider)
    try:
        params, _, _ = fixture(core)
        seen = []

        def build(snapshot):
            slide = snapshot["slides"][0]
            table = slide["tables"][0]
            seen.append(table)
            return {
                "summary": "Review header styles",
                "operations": operations(
                    [
                        (
                            "format_table_cells",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": table["object_id"],
                                "row_start": 0,
                                "row_end": 0,
                                "column_start": 0,
                                "column_end": 2,
                                "style": {
                                    **{key: None for key in FIELDS},
                                    "bold": False,
                                    "alignment": "center",
                                },
                            },
                        ),
                        (
                            "format_table_cells",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": table["object_id"],
                                "row_start": 0,
                                "row_end": 0,
                                "column_start": 0,
                                "column_end": 2,
                                "style": {
                                    **{key: None for key in FIELDS},
                                    "bold": True,
                                    "fill_color": "#224466",
                                },
                            },
                        ),
                    ]
                ),
            }

        provider.builder = build
        proposed = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {**params, "instruction": "Style the header.", "slide_numbers": [1]},
        )
        assert (
            "fingerprint" not in seen[0]
            and seen[0]["formatting"]["cell_styles"][0][0]["bold"] is True
        )
        previous = [v["previous_data"]["cell_styles"] for v in proposed["review_operations"]]
        assert previous[0][0] == {"row": 0, "column": 0, "style": {"bold": True, "alignment": None}}
        assert previous[1][0] == {
            "row": 0,
            "column": 0,
            "style": {"bold": False, "fill_color": "#26364D"},
        }
        assert (
            proposed["review_operations"][0]["params"]["expected_fingerprint"]
            != proposed["review_operations"][1]["params"]["expected_fingerprint"]
        )
        save(core, params, proposed)
        assert catalog(core, params)["items"][0]["cells"] == seen[0]["cells"]
    finally:
        core.close()


@pytest.mark.parametrize("empty,multiline", [(True, False), (False, True), (False, False)])
def test_partial_styles_keep_native_theme_font_and_cell_properties(tmp_path, empty, multiline):
    from copy import deepcopy

    from presenter_core.presentation.table_format import format_cells

    def canonical(node):
        return etree.tostring(node, method="c14n", exclusive=True)

    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        with zipfile.ZipFile(path(core, params)) as z:
            frame = etree.fromstring(z.read("ppt/slides/slide1.xml")).find(
                "p:cSld/p:spTree/p:graphicFrame", _NS
            )
        table = frame.find("a:graphic/a:graphicData/a:tbl", _NS)
        etree.SubElement(
            table.find("a:tblPr", _NS), f"{{{_NS['a']}}}tableStyleId"
        ).text = "native-style-reference"
        cell = table.find("a:tr/a:tc", _NS)
        paragraph = cell.find("a:txBody/a:p", _NS)
        if empty:
            for run in paragraph.findall("a:r", _NS):
                paragraph.remove(run)
        if multiline:
            cell.find("a:txBody", _NS).append(deepcopy(paragraph))
        before = deepcopy(frame)
        assert format_cells(
            frame,
            {
                "row_start": 0,
                "row_end": 0,
                "column_start": 0,
                "column_end": 0,
                "style": {"italic": True},
            },
        )
        assert canonical(table.find("a:tblPr", _NS)) == canonical(
            before.find("a:graphic/a:graphicData/a:tbl/a:tblPr", _NS)
        )
        assert canonical(cell.find("a:tcPr", _NS)) == canonical(before.find(".//a:tc/a:tcPr", _NS))
        for paragraph in cell.findall("a:txBody/a:p", _NS):
            assert paragraph.find("a:pPr/a:defRPr", _NS).get("i") == "1"
            assert paragraph.find("a:endParaRPr", _NS).get("i") == "1"
        # Only the requested italic attribute may change on original runs.
        for old, new in zip(
            before.findall(".//a:tc/a:txBody/a:p/a:r", _NS),
            frame.findall(".//a:tc/a:txBody/a:p/a:r", _NS),
            strict=True,
        ):
            if new.find("a:rPr", _NS).get("i") == "1":
                new.find("a:rPr", _NS).attrib.pop("i")
            assert canonical(old) == canonical(new)
    finally:
        core.close()


def test_stale_table_format_target_does_not_publish(tmp_path):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        info = catalog(core, params)
        before = path(core, params).read_bytes()
        info["items"][0]["fingerprint"] = "0" * 64
        with pytest.raises(CoreDomainError):
            prepare(core, params, info)
        assert path(core, params).read_bytes() == before
    finally:
        core.close()
