from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from test_object_groups import mixed_fixture
from test_object_paste import inventory
from test_presentation_native_layouts import path
from test_presentation_transactions import call
from test_selection_actions import save

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import inspect_pptx_snapshot
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def slides(core, params):
    source = core._presentation_edits._current_revision_source(
        params["project_id"], params["document_id"]
    )
    with path(core, params).open("rb") as handle:
        return inspect_pptx_snapshot(
            handle,
            document_id=params["document_id"],
            expected_sha256=source["sha256"],
            byte_size=source["byte_size"],
        ).slides


def fixture(core, directory):
    params, _ = mixed_fixture(core, directory)
    second = inventory(core, params, 2)
    proposed = call(
        core,
        "presentation.workspace.prepare_edit_plan",
        {
            **params,
            "summary": "Fixture third slide",
            "operations": [
                {
                    "type": "create_authored_slide",
                    "params": {
                        "slide_id": second["slide_id"],
                        "layout_source_slide_id": second["slide_id"],
                        "title": "Detailed alternatives",
                        "bullets": ["Native detail"],
                        "notes": "Third slide notes",
                        "template": "paper",
                        "layout": "points",
                    },
                }
            ],
        },
    )
    created = save(core, params, proposed)
    params["expected_revision_id"] = created["revision_id"]
    return params, slides(core, params)


def appendix_operations(original, copy, template="classic"):
    ids = [s.slide_id for s in original]
    selected = [ids[0], ids[2]]
    ops = [
        {
            "type": "create_authored_slide",
            "params": {
                "slide_id": ids[-1],
                "layout_source_slide_id": ids[-1],
                "title": "Appendix",
                "bullets": [],
                "notes": "Appendix divider notes",
                "template": template,
                "layout": "statement",
            },
        }
    ]
    if copy:
        ops.extend({"type": "duplicate_slide", "params": {"slide_id": id}} for id in selected)
    ops.append(
        {
            "type": "reorder_slides",
            "params": {
                "ordered_slide_ids": (ids if copy else [ids[1]])
                + [{"created_by": 1}]
                + ([{"created_by": 2}, {"created_by": 3}] if copy else selected)
            },
        }
    )
    return ops


@pytest.mark.parametrize("copy", [False, True])
@pytest.mark.parametrize("template", ["classic", "midnight", "paper"])
def test_appendix_atomic_native_order_parts_notes_and_history(tmp_path: Path, copy, template):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, original_slides = fixture(core, tmp_path)
        original = path(core, params).read_bytes()
        old_ids = [s.slide_id for s in original_slides]
        proposed = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {
                **params,
                "summary": "Review appendix",
                "operations": appendix_operations(original_slides, copy, template),
            },
        )
        assert path(core, params).read_bytes() == original
        saved = save(core, params, proposed)
        fresh = slides(core, params)
        divider = saved["operations"][0]["created_slide_id"]
        assert [s.slide_id for s in fresh] == (old_ids if copy else [old_ids[1]]) + [divider] + (
            [s["created_slide_id"] for s in saved["operations"][1:-1]]
            if copy
            else [old_ids[0], old_ids[2]]
        )
        assert len(fresh) == (6 if copy else 4)
        by_id = {s.slide_id: s for s in fresh}
        assert all(by_id[s.slide_id].objects == s.objects for s in original_slides)
        divider_number = 4 if copy else 2
        assert (
            inventory(core, params, divider_number)["speaker_notes"]["current_text"]
            == "Appendix divider notes"
        )
        with (
            zipfile.ZipFile(io.BytesIO(original)) as before,
            zipfile.ZipFile(path(core, params)) as after,
        ):
            assert all(
                before.read(name) == after.read(name)
                for name in before.namelist()
                if name
                not in {
                    "[Content_Types].xml",
                    "ppt/presentation.xml",
                    "ppt/_rels/presentation.xml.rels",
                }
            )
            charts = [
                n
                for n in after.namelist()
                if n.startswith("ppt/charts/") and n.endswith(".xml") and "/_rels/" not in n
            ]
            assert len(charts) == (2 if copy else 1)
        appendix_bytes = path(core, params).read_bytes()
        stepped = call(
            core, "presentation.workspace.step_revision", {**params, "direction": "undo"}
        )
        params["expected_revision_id"] = stepped["revision_id"]
        assert path(core, params).read_bytes() == original
        stepped = call(
            core, "presentation.workspace.step_revision", {**params, "direction": "redo"}
        )
        params["expected_revision_id"] = stepped["revision_id"]
        assert path(core, params).read_bytes() == appendix_bytes
    finally:
        core.close()


@pytest.mark.parametrize("failure", ["discard", "missing_detail", "late_failure", "stale"])
def test_appendix_failures_never_publish_partial_divider_or_copies(tmp_path: Path, failure):
    import uuid

    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, original_slides = fixture(core, tmp_path)
        original = path(core, params).read_bytes()
        ops = appendix_operations(original_slides, True)
        if failure == "missing_detail":
            ops[1]["params"]["slide_id"] = str(uuid.uuid4())
        if failure == "late_failure":
            ops[-1]["params"]["ordered_slide_ids"][-1] = {"created_by": 20}
        request = {**params, "summary": "Appendix review", "operations": ops}
        if failure == "stale":
            request["expected_revision_id"] = str(uuid.uuid4())
        if failure == "discard":
            proposed = call(core, "presentation.workspace.prepare_edit_plan", request)
            call(
                core,
                "presentation.workspace.reject_edit_plan",
                {
                    "project_id": params["project_id"],
                    "document_id": params["document_id"],
                    "plan_id": proposed["plan_id"],
                },
            )
        else:
            with pytest.raises(CoreDomainError):
                core._presentation_edit_plans.prepare(request)
        assert path(core, params).read_bytes() == original
        assert (
            core._presentation_edits._current_revision_source(
                params["project_id"], params["document_id"]
            )["revision_id"]
            == params["expected_revision_id"]
        )
    finally:
        core.close()
