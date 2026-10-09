from __future__ import annotations

import copy
import io
import zipfile

import pytest
from lxml import etree
from test_presentation_chart_editing import draft, imported
from test_presentation_edit_planning import call
from test_presentation_native_layouts import path, scope

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.chart_structure import (
    replace_cache,
    reshape_chart,
    sources,
    structure_reason,
)
from presenter_core.presentation.charts import CNS, NS
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def structure_draft(params, inventory):
    op = draft(params, inventory)
    op["categories"] = ["Baseline", "Forecast", "Target", "Later"]
    op["category_sources"] = [0, None, 2, None]
    op["series_sources"] = [0] if op["chart_type"] == "pie" else [0, None]
    op["series"] = [{"name": "Revenue", "values": [10, 11, 15, 20]}]
    if op["chart_type"] != "pie":
        op["series"].append({"name": "Margin", "values": [2, 3, 4, 5]})
    return op


@pytest.mark.parametrize("kind", ["column", "bar", "line", "pie"])
@pytest.mark.parametrize("shared", [False, True])
def test_reviewed_chart_structure_preserves_native_parts_styles_and_undo(tmp_path, kind, shared):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, inventory = imported(core, tmp_path, kind, shared=shared)
        assert inventory["items"][0]["structure_editable"]
        op = structure_draft(params, inventory)
        original = path(core, params).read_bytes()
        plan = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {
                **params,
                "summary": "Restructure native chart",
                "operations": [
                    {
                        "type": "reshape_chart",
                        "params": {k: v for k, v in op.items() if k not in params},
                    }
                ],
            },
        )
        assert path(core, params).read_bytes() == original
        identity = {
            "project_id": params["project_id"],
            "document_id": params["document_id"],
            "plan_id": plan["plan_id"],
        }
        call(core, "presentation.workspace.open_edit_plan_preview", identity)
        saved = call(
            core,
            "presentation.workspace.apply_edit_plan",
            {**identity, "reviewed_sha256": plan["sha256"], "confirm": True},
        )
        params["expected_revision_id"] = saved["revision_id"]
        fresh = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
        )["items"][0]
        assert fresh["data"] == {k: op[k] for k in ["title", "chart_type", "categories", "series"]}
        assert (
            fresh["object_id"] == inventory["items"][0]["object_id"] and fresh["structure_editable"]
        )
        second = call(
            core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 2}
        )["items"][0]
        assert second["data"]["categories"] == ["Baseline", "Pilot", "Target"]
        with (
            zipfile.ZipFile(io.BytesIO(original)) as before,
            zipfile.ZipFile(path(core, params)) as after,
        ):
            changes = [n for n in before.namelist() if before.read(n) != after.read(n)]
            assert set(changes) == {
                "[Content_Types].xml",
                "ppt/slides/slide1.xml",
                "ppt/slides/_rels/slide1.xml.rels",
            }
            newparts = [n for n in after.namelist() if n not in before.namelist()]
            newchart = next(n for n in newparts if n.endswith(".xml") and "/charts/" in n)
            a = etree.fromstring(before.read("ppt/charts/chart1.xml"))
            b = etree.fromstring(after.read(newchart))
            assert etree.tostring(a.find(".//c:ser/c:spPr", NS)) == etree.tostring(
                b.find(".//c:ser/c:spPr", NS)
            )
            assert b.find(".//c:ser/c:idx", NS).get("val") == a.find(".//c:ser/c:idx", NS).get(
                "val"
            )
            workbook = next(n for n in newparts if n.endswith(".xlsx"))
            with zipfile.ZipFile(io.BytesIO(after.read(workbook))) as book:
                xml = book.read("xl/worksheets/sheet1.xml")
                assert b"<f>" not in xml
                assert b"Forecast" in book.read("xl/sharedStrings.xml")
        call(
            core,
            "source.reindex",
            {"project_id": params["project_id"], "document_id": params["document_id"]},
        )
        with core._storage.project_database(params["project_id"]) as conn:
            assert any(
                "Forecast" in row[0] for row in conn.execute("SELECT text FROM source_units")
            )
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize(
    "case",
    ["missing_mapping", "duplicate", "reorder", "stale", "type", "empty", "bad_value", "foreign"],
)
def test_invalid_chart_structure_never_publishes(tmp_path, case):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, inventory = imported(core, tmp_path)
        op = structure_draft(params, inventory)
        original = path(core, params).read_bytes()
        if case == "missing_mapping":
            op.pop("category_sources")
        elif case == "duplicate":
            op["category_sources"] = [0, 0, 2, None]
        elif case == "reorder":
            op["category_sources"] = [2, None, 0, None]
        elif case == "stale":
            op["expected_fingerprint"] = "0" * 64
        elif case == "type":
            op["chart_type"] = "line"
        elif case == "empty":
            op["series"] = []
        elif case == "bad_value":
            op["series"][0]["values"][0] = True
        else:
            op["object_id"] = "00000000-0000-4000-8000-000000000001"
        error = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {
                **params,
                "summary": "Invalid structure",
                "operations": [
                    {
                        "type": "reshape_chart",
                        "params": {k: v for k, v in op.items() if k not in params},
                    }
                ],
            },
            ok=False,
        )
        assert error["code"] == (
            "PRESENTATION_EDIT_STALE_TARGET"
            if case == "stale"
            else "PRESENTATION_EDIT_TARGET_NOT_FOUND"
            if case == "foreign"
            else "INVALID_REQUEST"
        )
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize("kind", ["column", "pie"])
def test_native_point_label_legend_and_cache_indexes_follow_retained_categories(tmp_path, kind):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, inventory = imported(core, tmp_path, kind)
        with zipfile.ZipFile(path(core, params)) as archive:
            chart = etree.fromstring(archive.read("ppt/charts/chart1.xml"))
        ser = chart.find(".//c:ser", NS)
        for tag in ["dPt", "dLbl"]:
            container = ser if tag == "dPt" else etree.SubElement(ser, f"{{{CNS}}}dLbls")
            for index in [1, 2]:
                node = etree.SubElement(container, f"{{{CNS}}}{tag}")
                etree.SubElement(node, f"{{{CNS}}}idx", val=str(index))
                etree.SubElement(node, f"{{{CNS}}}delete", val="0")
        legend = chart.find("c:chart/c:legend", NS)
        if legend is None:
            legend = etree.SubElement(chart.find("c:chart", NS), f"{{{CNS}}}legend")
        entry = etree.SubElement(legend, f"{{{CNS}}}legendEntry")
        etree.SubElement(entry, f"{{{CNS}}}idx", val="2" if kind == "pie" else "0")
        etree.SubElement(entry, f"{{{CNS}}}delete", val="1")
        op = structure_draft(params, inventory)
        reshape_chart(chart, inventory["items"][0]["data"], op, op)
        assert len(chart.findall(".//c:ser/c:dPt", NS)) == 1
        assert chart.find(".//c:ser/c:dPt/c:idx", NS).get("val") == "2"
        assert chart.find(".//c:dLbl/c:idx", NS).get("val") == "2"
        assert chart.find(".//c:legendEntry/c:idx", NS).get("val") == (
            "2" if kind == "pie" else "0"
        )
        ref = chart.find(".//c:ser/c:val/c:numRef", NS)
        ref.find('c:numCache/c:pt[@idx="2"]', NS).set("formatCode", "0.00")
        replace_cache(ref, [10, 11, 15, 20], structural=True, mapping=[0, None, 2, None])
        assert ref.find('c:numCache/c:pt[@idx="2"]', NS).get("formatCode") == "0.00"
        assert ref.find('c:numCache/c:pt[@idx="1"]', NS).get("formatCode") is None
        malformed = copy.deepcopy(chart)
        malformed.find(".//c:ser/c:order", NS).set("val", "9")
        assert structure_reason(malformed, op)
        with pytest.raises(CoreDomainError):
            sources([True], 1, 3, "category_sources")
    finally:
        core.close()
