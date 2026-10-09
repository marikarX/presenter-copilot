from __future__ import annotations

import copy
import io
import zipfile

import pytest
from lxml import etree
from test_graphic_geometry import fixture
from test_presentation_chart_editing import imported
from test_presentation_edit_planning import call
from test_presentation_native_layouts import path, scope

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import _NS
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


@pytest.mark.parametrize("kind", ["chart", "table"])
@pytest.mark.parametrize("reviewed", [False, True])
def test_native_slide_duplicate_preserves_content_notes_and_undo(tmp_path, kind, reviewed):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, inventory, obj = fixture(core, tmp_path, kind)
        original = path(core, params).read_bytes()
        if reviewed:
            plan = call(
                core,
                "presentation.workspace.prepare_edit_plan",
                {
                    **params,
                    "summary": "Copy native chart/table slide",
                    "operations": [
                        {"type": "duplicate_slide", "params": {"slide_id": inventory["slide_id"]}}
                    ],
                },
            )
            assert path(core, params).read_bytes() == original
            call(
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
        else:
            saved = call(
                core,
                "presentation.workspace.duplicate_slide",
                {**params, "slide_id": inventory["slide_id"]},
            )
        params["expected_revision_id"] = saved["revision_id"]
        fresh = call(
            core, "presentation.workspace.list_text_targets", {**scope(params), "slide_number": 2}
        )
        assert fresh["slide_id"] != inventory["slide_id"]
        assert len(fresh["objects"]) == len(inventory["objects"])
        for source, copied in zip(inventory["objects"], fresh["objects"], strict=True):
            assert source["name"] == copied["name"] and source["geometry"] == copied["geometry"]
            assert source["object_id"] != copied["object_id"]
        with (
            zipfile.ZipFile(io.BytesIO(original)) as before,
            zipfile.ZipFile(path(core, params)) as after,
        ):
            assert set(n for n in before.namelist() if before.read(n) != after.read(n)) == {
                "[Content_Types].xml",
                "ppt/presentation.xml",
                "ppt/_rels/presentation.xml.rels",
            }
            duplicate_slide = next(
                n
                for n in set(after.namelist()) - set(before.namelist())
                if n.startswith("ppt/slides/") and n.endswith(".xml") and "/_rels/" not in n
            )
            assert after.read(duplicate_slide) == before.read("ppt/slides/slide1.xml")
            original_notes = before.read("ppt/notesSlides/notesSlide1.xml")
            assert any(
                after.read(n) == original_notes
                for n in set(after.namelist()) - set(before.namelist())
                if n.startswith("ppt/notesSlides/") and n.endswith(".xml")
            )
        if kind == "chart":
            first = call(
                core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
            )["items"][0]
            copied = call(
                core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 2}
            )["items"][0]
            assert first["data"] == copied["data"]
            edited = call(
                core,
                "presentation.workspace.replace_chart_data",
                {
                    **params,
                    "slide_id": fresh["slide_id"],
                    "object_id": copied["object_id"],
                    "expected_fingerprint": copied["fingerprint"],
                    **copied["data"],
                    "title": "Copied slide chart",
                },
            )
            params["expected_revision_id"] = edited["revision_id"]
            assert (
                call(
                    core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 1}
                )["items"][0]["data"]["title"]
                == "Imported pilot"
            )
            undone = call(
                core, "presentation.workspace.step_revision", {**params, "direction": "undo"}
            )
            params["expected_revision_id"] = undone["revision_id"]
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


@pytest.mark.parametrize("mutation", ["linked", "extension"])
def test_slide_chart_clone_rejects_unsupported_dependencies_without_revision(tmp_path, mutation):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, inventory = imported(core, tmp_path, mutation=mutation)
        original = path(core, params).read_bytes()
        result = call(
            core,
            "presentation.workspace.duplicate_slide",
            {**params, "slide_id": inventory["slide_id"]},
            ok=False,
        )
        assert result["code"] == "PRESENTATION_EDIT_UNSUPPORTED"
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


def test_slide_duplication_after_chart_delete_retains_unused_parts(tmp_path):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, inventory, obj = fixture(core, tmp_path, "chart")
        deleted = call(
            core,
            "presentation.workspace.delete_object",
            {
                **params,
                "slide_id": inventory["slide_id"],
                "object_id": obj["object_id"],
                "expected_geometry": obj["geometry"],
            },
        )
        params["expected_revision_id"] = deleted["revision_id"]
        saved = call(
            core,
            "presentation.workspace.duplicate_slide",
            {**params, "slide_id": inventory["slide_id"]},
        )
        params["expected_revision_id"] = saved["revision_id"]
        assert (
            call(
                core,
                "presentation.workspace.list_text_targets",
                {**scope(params), "slide_number": 2},
            )["objects"]
            == []
        )
        assert (
            call(core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 3})[
                "items"
            ][0]["data"]["title"]
            == "Imported pilot"
        )
    finally:
        core.close()


@pytest.mark.parametrize("sharing", ["same_rid", "distinct_rids", "shared_workbook"])
def test_shared_chart_frames_preserve_sharing_inside_copy_but_isolate_source(tmp_path, sharing):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, _ = imported(core, tmp_path)
        with zipfile.ZipFile(path(core, params)) as source:
            parts = {n: source.read(n) for n in source.namelist()}
        slide = etree.fromstring(parts["ppt/slides/slide1.xml"])
        frame = copy.deepcopy(slide.find(".//p:graphicFrame", _NS))
        frame.find("p:nvGraphicFramePr/p:cNvPr", _NS).set("id", "42")
        frame.find("p:nvGraphicFramePr/p:cNvPr", _NS).set("name", "Shared chart view")
        if sharing != "same_rid":
            rels = etree.fromstring(parts["ppt/slides/_rels/slide1.xml.rels"])
            relation = copy.deepcopy(next(n for n in rels if n.get("Type", "").endswith("/chart")))
            relation.set("Id", "rIdShared")
            if sharing == "shared_workbook":
                relation.set("Target", "../charts/chart2.xml")
                chart1_rels = etree.fromstring(parts["ppt/charts/_rels/chart1.xml.rels"])
                chart2_rels = etree.fromstring(parts["ppt/charts/_rels/chart2.xml.rels"])
                chart2_rels[0].set("Target", chart1_rels[0].get("Target"))
                parts["ppt/charts/_rels/chart2.xml.rels"] = etree.tostring(chart2_rels)
            rels.append(relation)
            parts["ppt/slides/_rels/slide1.xml.rels"] = etree.tostring(rels)
            frame.find(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}chart").set(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id",
                "rIdShared",
            )
        slide.find("p:cSld/p:spTree", _NS).append(frame)
        parts["ppt/slides/slide1.xml"] = etree.tostring(slide)
        source_path = tmp_path / "shared-slide.pptx"
        with zipfile.ZipFile(source_path, "w") as archive:
            for n, payload in parts.items():
                archive.writestr(n, payload)
        document = call(
            core,
            "source.import",
            {"project_id": params["project_id"], "path": str(source_path), "kind": "presentation"},
        )["document"]["id"]
        source = core._presentation_edits._current_revision_source(params["project_id"], document)
        params.update(document_id=document, expected_revision_id=source["revision_id"])
        inventory = call(
            core, "presentation.workspace.list_text_targets", {**scope(params), "slide_number": 1}
        )
        saved = call(
            core,
            "presentation.workspace.duplicate_slide",
            {**params, "slide_id": inventory["slide_id"]},
        )
        params["expected_revision_id"] = saved["revision_id"]
        with zipfile.ZipFile(path(core, params)) as archive:
            added_charts = [
                n
                for n in archive.namelist()
                if n.startswith("ppt/charts/copilot-copy-") and n.endswith(".xml")
            ]
            assert len(added_charts) == (2 if sharing == "shared_workbook" else 1)
            assert (
                len(
                    [
                        n
                        for n in archive.namelist()
                        if n.startswith("ppt/embeddings/copilot-") and n.endswith(".xlsx")
                    ]
                )
                == 1
            )
            copied = call(
                core, "presentation.workspace.list_charts", {**scope(params), "slide_number": 2}
            )["items"]
            assert len(copied) == 2 and copied[0]["data"] == copied[1]["data"]
    finally:
        core.close()
