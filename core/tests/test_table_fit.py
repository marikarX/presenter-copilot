"""Row fitting preserves native content and rejects unmeasurable or unsafe layouts."""

from __future__ import annotations

import io
import zipfile

import pytest
from lxml import etree
from test_chart_legend import core_at
from test_copilot_data import DataProvider
from test_copilot_diagrams import operations
from test_presentation_edit_planning import call
from test_presentation_native_layouts import path
from test_selection_actions import save
from test_table_borders import catalog, frame
from test_table_merge import prepare as merge_plan
from test_table_structure import fixture

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.fidelity import _NS, DRAWING_NS
from presenter_core.presentation.table_fit import fit_rows, grid, inspect_fit


@pytest.fixture(autouse=True)
def deterministic_font_metrics(monkeypatch):
    class Font:
        def __init__(self, size):
            self.size = size

        def getlength(self, text):
            return len(text) * self.size / 2

    # Core invariants run without depending on a CI host's font installation.
    # Actual installed Arial metrics and native line wrapping are checked in Office acceptance.
    monkeypatch.setattr(
        "presenter_core.presentation.table_fit.installed_font",
        lambda family, bold, italic, size: Font(size),
    )


def prepare(core, params, info, strategy="compact"):
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Fit native table rows",
            "operations": [
                {
                    "type": "fit_table_rows",
                    "params": {
                        "slide_id": info["slide_id"],
                        "object_id": info["items"][0]["object_id"],
                        "expected_fingerprint": info["items"][0]["fingerprint"],
                        "strategy": strategy,
                    },
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "merged,split,strategy",
    [
        (False, False, "compact"),
        (False, False, "grow"),
        (True, False, "compact"),
        (True, True, "grow"),
        (True, True, "compact"),
    ],
)
def test_fitting_changes_only_stored_heights_and_retains_exact_undo(
    tmp_path, merged, split, strategy
):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        if merged:
            save(core, params, merge_plan(core, params, catalog(core, params)))
        if split:
            save(core, params, merge_plan(core, params, catalog(core, params), "split_table_cells"))
        info = catalog(core, params)
        old = path(core, params).read_bytes()
        before = frame(core, params)
        plan = prepare(core, params, info, strategy)
        if not merged and strategy == "grow":
            assert not plan["changed"] and path(core, params).read_bytes() == old
            return
        save(core, params, plan)
        fresh = catalog(core, params)["items"][0]
        assert fresh["cells"] == info["items"][0]["cells"]
        assert fresh["spans"] == info["items"][0]["spans"]
        assert fresh["fit"]["column_widths_pt"] == [192] * 3
        if split:
            assert fresh["fit"]["row_heights_pt"][0] == pytest.approx(93.6)
        with (
            zipfile.ZipFile(io.BytesIO(old)) as previous,
            zipfile.ZipFile(path(core, params)) as updated,
        ):
            assert [n for n in previous.namelist() if previous.read(n) != updated.read(n)] == [
                "ppt/slides/slide1.xml"
            ]
        after = frame(core, params)
        for tree in [before, after]:
            tree.find("p:xfrm/a:ext", _NS).attrib.pop("cy")
            for row in tree.findall("a:graphic/a:graphicData/a:tbl/a:tr", _NS):
                row.attrib.pop("h")
        assert etree.tostring(before, method="c14n", exclusive=True) == etree.tostring(
            after, method="c14n", exclusive=True
        )
        assert not prepare(core, params, catalog(core, params), strategy)["changed"]
        undo = call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        params["expected_revision_id"] = undo["revision_id"]
        assert path(core, params).read_bytes() == old
    finally:
        core.close()


@pytest.mark.parametrize(
    "case",
    [
        "font",
        "size",
        "rotated",
        "vertical",
        "bullet",
        "indent",
        "tabs",
        "scale",
        "margins",
        "frame",
        "strategy",
        "overflow",
    ],
)
def test_unsupported_fit_never_mutates_the_native_table(tmp_path, case):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        tree = frame(core, params)
        cell = grid(tree)[0][0]
        body = cell.find("a:txBody/a:bodyPr", _NS)
        rp = cell.find("a:txBody/a:p/a:r/a:rPr", _NS)
        paragraph = cell.find("a:txBody/a:p", _NS)
        if case == "font":
            rp.find("a:latin", _NS).set("typeface", "+mj-lt")
        if case == "size":
            rp.attrib.pop("sz")
        if case == "rotated":
            body.set("rot", "60000")
        if case == "vertical":
            body.set("vert", "vert")
        if case == "scale":
            etree.SubElement(body, f"{{{DRAWING_NS}}}normAutofit", fontScale="50000")
        if case in {"bullet", "indent"}:
            ppr = etree.Element(f"{{{DRAWING_NS}}}pPr")
            paragraph.insert(0, ppr)
            if case == "bullet":
                etree.SubElement(ppr, f"{{{DRAWING_NS}}}buChar", char="•")
            else:
                ppr.set("marL", "invalid")
        if case == "tabs":
            cell.find("a:txBody/a:p/a:r/a:t", _NS).text = "A\tB"
        if case == "margins":
            cell.find("a:tcPr", _NS).set("marL", "99999999")
        if case == "frame":
            tree.find("p:xfrm/a:ext", _NS).set("cy", "2")
        before = etree.tostring(tree)
        with pytest.raises(CoreDomainError):
            fit_rows(
                tree, [] if case == "strategy" else "compact", 1 if case == "overflow" else 6858000
            )
        assert etree.tostring(tree) == before
    finally:
        core.close()


def test_measured_wrapping_spacing_and_merged_constraints(tmp_path):
    core = core_at(tmp_path)
    try:
        params, _, _ = fixture(core)
        tree = frame(core, params)
        cell = grid(tree)[0][0]
        cell.find("a:txBody/a:p/a:r/a:t", _NS).text = "word " * 30
        assert fit_rows(tree, "grow", 10000000)
        assert inspect_fit(tree)["row_heights_pt"][0] > 72
        paragraph = cell.find("a:txBody/a:p", _NS)
        ppr = etree.Element(f"{{{DRAWING_NS}}}pPr")
        paragraph.insert(0, ppr)
        for name, value in [("lnSpc", 3000), ("spcBef", 1200), ("spcAft", 1200)]:
            n = etree.SubElement(ppr, f"{{{DRAWING_NS}}}{name}")
            etree.SubElement(n, f"{{{DRAWING_NS}}}spcPts", val=str(value))
        assert fit_rows(tree, "grow", 10000000)
        assert inspect_fit(tree)["row_heights_pt"][0] > 200
    finally:
        core.close()


def test_copilot_second_fit_reviews_actual_staged_heights(tmp_path):
    provider = DataProvider(locality="local")
    core = core_at(tmp_path, provider)
    try:
        params, _, _ = fixture(core)

        def build(snapshot):
            slide = snapshot["slides"][0]
            table = slide["tables"][0]
            return {
                "summary": "Review compact then grow",
                "operations": operations(
                    [
                        (
                            "fit_table_rows",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": table["object_id"],
                                "strategy": strategy,
                            },
                        )
                        for strategy in ["compact", "grow"]
                    ]
                ),
            }

        provider.builder = build
        plan = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {**params, "instruction": "Fit rows", "slide_numbers": [1]},
        )
        reviews = plan["review_operations"]
        assert reviews[0]["previous_data"]["row_heights_pt"] == [72] * 3
        assert reviews[1]["previous_data"]["row_heights_pt"] == pytest.approx([28.8] * 3)
        assert (
            reviews[0]["params"]["expected_fingerprint"]
            != reviews[1]["params"]["expected_fingerprint"]
        )
        save(core, params, plan)
        assert catalog(core, params)["items"][0]["fit"]["row_heights_pt"] == pytest.approx(
            [28.8] * 3
        )
    finally:
        core.close()
