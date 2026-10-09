from __future__ import annotations

from pathlib import Path

import pytest
from test_presentation_edit_planning import PlanProvider, call, context
from test_presentation_native_layouts import path
from test_selection_actions import save

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


@pytest.mark.parametrize(
    "mode",
    [
        "group",
        "ungroup",
        "duplicate",
        "forward",
        "cross_slide",
        "unselected",
        "precondition",
        "wrong_kind",
    ],
)
def test_copilot_groups_bind_native_targets_and_preserve_review(tmp_path: Path, mode: str):
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        params = context(core)
        scope = {k: params[k] for k in ("project_id", "document_id", "expected_revision_id")}
        baseline = path(core, scope).read_bytes()
        original = core._presentation_edit_planning._read(
            core._presentation_edits,
            scope["project_id"],
            scope["document_id"],
            scope["expected_revision_id"],
        )

        def modify(output, invocation):
            slide = original.slides[0].slide_id
            entries = [
                ("create_text_box", {"slide_id": slide, "text": "First grouping child"}),
                ("create_text_box", {"slide_id": slide, "text": "Second grouping child"}),
                (
                    "group_objects",
                    {
                        "slide_id": slide,
                        "objects": [
                            {"object_id": {"created_by": 1}},
                            {"object_id": {"created_by": 2}},
                        ],
                    },
                ),
            ]
            if mode in {"ungroup", "wrong_kind"}:
                entries.append(
                    (
                        "ungroup_object",
                        {
                            "slide_id": slide,
                            "object_id": {"created_by": 3 if mode == "ungroup" else 1},
                        },
                    )
                )
            if mode == "duplicate":
                entries[2][1]["objects"][1] = {"object_id": {"created_by": 1}}
            if mode == "forward":
                entries[2][1]["objects"][1] = {"object_id": {"created_by": 4}}
            if mode == "cross_slide":
                entries[1][1]["slide_id"] = original.slides[1].slide_id
            if mode == "unselected":
                entries[2][1]["slide_id"] = original.slides[1].slide_id
            if mode == "precondition":
                entries[2][1]["objects"][0]["expected_geometry"] = {}
            output["operations"] = [
                {
                    "type": kind,
                    "params": value,
                    "rationale": "Review grouping without altering child content",
                    "evidence_ids": [],
                }
                for kind, value in entries
            ]

        provider.modifier = modify
        valid = mode in {"group", "ungroup"}
        proposed = call(core, "presentation.workspace.propose_edit_plan", params, ok=valid)
        assert path(core, scope).read_bytes() == baseline
        if not valid:
            assert not core._presentation_edit_plans._plans
            assert not list(
                core._storage.paths.safe_sources_directory(scope["project_id"]).glob(".edit-*.pptx")
            )
            return
        grouped = proposed["operations"][2]["params"]["objects"]
        assert [
            item["text"]
            for item in proposed["review_operations"][2]["previous_data"]["group_members"]
        ] == ["First grouping child", "Second grouping child"]
        assert len({item["object_id"] for item in grouped}) == 2
        assert all(item["expected_geometry"]["width_emu"] > 0 for item in grouped)
        result = save(core, scope, proposed)
        assert result["revision_number"] == 2
        current = core._presentation_edit_planning._read(
            core._presentation_edits,
            scope["project_id"],
            scope["document_id"],
            result["revision_id"],
        )
        assert current.slides[1] == original.slides[1]
        assert any(obj.text == "First grouping child" for obj in current.slides[0].objects)
        groups = [obj for obj in current.slides[0].objects if obj.kind == "grpSp"]
        assert len(groups) == (1 if mode == "group" else 0)
        if mode == "group":
            assert result["operations"][2]["created_object_id"] == groups[0].object_id
        call(core, "presentation.workspace.step_revision", {**scope, "direction": "undo"})
        assert path(core, scope).read_bytes() == baseline
    finally:
        core.close()
