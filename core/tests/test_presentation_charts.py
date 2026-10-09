from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from lxml import etree
from test_presentation_edit_planning import call
from test_presentation_native_layouts import path, scope
from test_presentation_transactions import context

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.charts import (
    CNS,
    NS,
    generated_chart,
    read_chart,
    summary,
    validate_data,
)
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def request(params, operations, kind="column"):
    return {
        **params,
        "slide_id": operations[0]["params"]["slide_id"],
        "geometry": {
            "x_emu": 457200,
            "y_emu": 1828800,
            "width_emu": 7315200,
            "height_emu": 3657600,
        },
        "title": "Pilot outcomes",
        "chart_type": kind,
        "categories": ["Baseline", "Pilot", "Target"],
        "series": [{"name": "Revenue", "values": [10, 12.25, 15]}],
    }


@pytest.mark.parametrize("kind", ["column", "bar", "line", "pie"])
def test_chart_native_review_preserves_deck_embeds_literal_workbook_and_reindexes(
    tmp_path: Path, kind: str
):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, ops = context(core)
        draft = request(params, ops, kind)
        draft["categories"][0] = "=2+3"
        draft["series"][0]["name"] = "https://example.test/Revenue"
        original = path(core, params).read_bytes()
        plan = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {
                **params,
                "summary": "Insert reviewed chart",
                "operations": [
                    {
                        "type": "create_chart",
                        "params": {k: v for k, v in draft.items() if k not in params},
                    }
                ],
            },
        )
        assert path(core, params).read_bytes() == original
        preview = call(
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
        with (
            zipfile.ZipFile(io.BytesIO(original)) as before,
            zipfile.ZipFile(path(core, params)) as after,
        ):
            changed = [name for name in before.namelist() if before.read(name) != after.read(name)]
            assert set(changed) == {
                "ppt/slides/slide1.xml",
                "ppt/slides/_rels/slide1.xml.rels",
                "[Content_Types].xml",
            }
            chartpart = next(
                name
                for name in after.namelist()
                if name.startswith("ppt/charts/copilot-") and name.endswith(".xml")
            )
            data = read_chart(etree.fromstring(after.read(chartpart)))
            assert data == validate_data(draft)
            bookpart = next(
                name
                for name in after.namelist()
                if name.startswith("ppt/embeddings/copilot-") and name.endswith(".xlsx")
            )
            with zipfile.ZipFile(io.BytesIO(after.read(bookpart))) as book:
                ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for member in book.namelist():
                    if member.endswith(".xml"):
                        root = etree.fromstring(book.read(member))
                        assert not root.findall(".//a:f", ns)
                    if member.endswith(".rels"):
                        assert b'TargetMode="External"' not in book.read(member)
                assert b"=2+3" in book.read("xl/sharedStrings.xml")
                assert b"https://example.test/Revenue" in book.read("xl/sharedStrings.xml")
        params["expected_revision_id"] = saved["revision_id"]
        call(
            core,
            "source.reindex",
            {"project_id": params["project_id"], "document_id": params["document_id"]},
        )
        with core._storage.project_database(params["project_id"]) as conn:
            assert any(
                "Pilot outcomes" in row[0] and "Pilot: 12.25" in row[0]
                for row in conn.execute("SELECT text FROM source_units")
            )
        native = core._presentation_workspace_sources.read_revision_inventory(scope(params))[3]
        assert native.slides[0].objects[-1].text == summary(data)
        assert preview["fidelity_report"]["slides"][0]["slide_id"] == native.slides[0].slide_id
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize(
    "case",
    [
        "bool",
        "nan",
        "infinity",
        "large",
        "ragged",
        "zero_pie",
        "negative_pie",
        "multi_pie",
        "too_many_categories",
        "too_many_series",
        "unknown",
        "bad_title",
    ],
)
def test_bad_chart_data_never_creates_revision(tmp_path: Path, case: str):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, ops = context(core)
        draft = request(params, ops)
        if case == "bool":
            draft["series"][0]["values"][0] = True
        if case == "nan":
            draft["series"][0]["values"][0] = float("nan")
        if case == "infinity":
            draft["series"][0]["values"][0] = float("inf")
        if case == "large":
            draft["series"][0]["values"][0] = 1e13
        if case == "ragged":
            draft["series"][0]["values"].pop()
        if case in {"zero_pie", "negative_pie", "multi_pie"}:
            draft["chart_type"] = "pie"
        if case == "zero_pie":
            draft["series"][0]["values"] = [0, 0, 0]
        if case == "negative_pie":
            draft["series"][0]["values"][0] = -1
        if case == "multi_pie":
            draft["series"].append(draft["series"][0])
        if case == "too_many_categories":
            draft["categories"] = ["a"] * 25
        if case == "too_many_series":
            draft["series"] *= 7
        if case == "unknown":
            draft["chart_type"] = "3d"
        if case == "bad_title":
            draft["title"] = "x" * 121
        original = path(core, params).read_bytes()
        call(core, "presentation.workspace.create_chart", draft, ok=False)
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


def test_chart_validation_keeps_fractional_summary_precision():
    data = validate_data(
        {
            "title": "Precision",
            "chart_type": "line",
            "categories": ["A"],
            "series": [{"name": "Measured", "values": [0.123456789123]}],
        }
    )
    assert "0.123456789123" in summary(data)
    with pytest.raises(CoreDomainError):
        validate_data({**data, "categories": ["\uffff"]})


@pytest.mark.parametrize("mutation", ["stacked", "combo", "cache_gap", "external", "negative"])
def test_cached_chart_reader_rejects_unsupported_and_keeps_negative_values(mutation):
    data = validate_data(
        {
            "title": "Bounded data",
            "chart_type": "line",
            "categories": ["A", "B"],
            "series": [{"name": "Measured", "values": [-2, 3]}],
        }
    )
    _, payload, _ = generated_chart(
        data, SimpleNamespace(x_emu=0, y_emu=0, width_emu=7315200, height_emu=3657600)
    )
    root = etree.fromstring(payload)
    if mutation == "stacked":
        root.find("c:chart/c:plotArea/c:lineChart/c:grouping", NS).set("val", "stacked")
    elif mutation == "combo":
        etree.SubElement(root.find("c:chart/c:plotArea", NS), f"{{{CNS}}}scatterChart")
    elif mutation == "cache_gap":
        root.find(".//c:numCache/c:pt", NS).set("idx", "3")
    elif mutation == "external":
        cache = root.find(".//c:numCache", NS)
        cache.getparent().remove(cache)
    if mutation == "negative":
        assert read_chart(root) == data
    else:
        assert read_chart(root) is None


def test_extreme_integer_chart_data_is_domain_error():
    with pytest.raises(CoreDomainError):
        validate_data(
            {
                "title": "Bounded",
                "chart_type": "bar",
                "categories": ["A"],
                "series": [{"name": "Value", "values": [10**1000]}],
            }
        )
