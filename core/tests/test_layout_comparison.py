from __future__ import annotations

import base64
from pathlib import Path

import pytest
from test_presentation_native_layouts import path, scope
from test_presentation_transactions import call, context
from test_selection_actions import save

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def prepare(core, params, slide, layout):
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": "Compare native layout",
            "operations": [
                {
                    "type": "apply_slide_layout",
                    "params": {"slide_id": slide, "layout_id": layout},
                }
            ],
        }
    )


def read_preview(core, params, plan):
    reader_scope = {
        "project_id": params["project_id"],
        "document_id": params["document_id"],
        "plan_id": plan["plan_id"],
    }
    reader = call(core, "presentation.workspace.open_edit_plan_preview", reader_scope)
    result = bytearray()
    while len(result) < reader["byte_size"]:
        chunk = call(
            core,
            "presentation.workspace.read_source",
            {
                "project_id": params["project_id"],
                "document_id": params["document_id"],
                "session_id": reader["session_id"],
                "offset": len(result),
                "max_bytes": reader["chunk_bytes"],
            },
        )
        result.extend(base64.b64decode(chunk["bytes_b64"]))
    return bytes(result)


def test_baseline_and_all_comparison_candidates_publish_only_final_review(tmp_path: Path):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, targets = context(core)
        original = path(core, params).read_bytes()
        layouts = call(core, "presentation.workspace.list_native_layouts", scope(params))["items"]
        current = next(item for item in layouts if 1 in item["used_by_slides"])
        slide = targets[0]["params"]["slide_id"]
        baseline = prepare(core, params, slide, current["layout_id"])
        assert not baseline["changed"]
        assert read_preview(core, params, baseline) == original
        call(
            core,
            "presentation.workspace.reject_edit_plan",
            {
                "project_id": params["project_id"],
                "document_id": params["document_id"],
                "plan_id": baseline["plan_id"],
            },
        )
        alternatives = [item for item in layouts if item["layout_id"] != current["layout_id"]]
        for item in alternatives:
            proposed = prepare(core, params, slide, item["layout_id"])
            assert proposed["changed"] and read_preview(core, params, proposed) != original
            assert path(core, params).read_bytes() == original
            call(
                core,
                "presentation.workspace.reject_edit_plan",
                {
                    "project_id": params["project_id"],
                    "document_id": params["document_id"],
                    "plan_id": proposed["plan_id"],
                },
            )
        final = prepare(core, params, slide, alternatives[-1]["layout_id"])
        reviewed = read_preview(core, params, final)
        applied = save(core, params, final)
        assert applied["revision_number"] == 2 and path(core, params).read_bytes() == reviewed
        call(core, "presentation.workspace.step_revision", {**params, "direction": "undo"})
        assert path(core, params).read_bytes() == original
    finally:
        core.close()


def test_stale_comparison_cannot_authorize_save(tmp_path: Path):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, targets = context(core)
        original = path(core, params).read_bytes()
        items = call(core, "presentation.workspace.list_native_layouts", scope(params))["items"]
        choices = [item for item in items if 1 not in item["used_by_slides"]]
        slide = targets[0]["params"]["slide_id"]
        old = prepare(core, params, slide, choices[0]["layout_id"])
        read_preview(core, params, old)
        new = prepare(core, params, slide, choices[1]["layout_id"])
        read_preview(core, params, new)
        save(core, params, new)
        with pytest.raises(CoreDomainError):
            core._presentation_edit_plans.apply(
                {
                    "project_id": params["project_id"],
                    "document_id": params["document_id"],
                    "plan_id": old["plan_id"],
                    "reviewed_sha256": old["sha256"],
                    "confirm": True,
                }
            )
        assert path(core, params).read_bytes() != original
    finally:
        core.close()
