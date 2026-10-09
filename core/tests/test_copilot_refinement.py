"""Refinement keeps draft intent ephemeral and rebuilds from the authoritative baseline."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from test_copilot_diagrams import edit_scope
from test_presentation_edit_planning import PlanProvider, call, context
from test_presentation_native_layouts import path
from test_selection_actions import save

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "scope",
        "assets",
        "missing",
        "foreign",
        "expired",
        "stale",
        "manual",
        "evidence",
        "late_target",
        "expired_during_provider",
    ],
)
def test_refine_owned_proposal_preserves_baseline_and_failed_draft(tmp_path: Path, failure):
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        params = context(core)
        scope = edit_scope(params)
        baseline = path(core, scope).read_bytes()
        first = call(core, "presentation.workspace.propose_edit_plan", params)
        retained = core._presentation_edit_plans._plans[first["plan_id"]]
        draft = copy.deepcopy(retained.planner_draft)
        package = retained.package.path.read_bytes()
        request = {
            **params,
            "previous_plan_id": first["plan_id"],
            "instruction": "Keep the title change and make the notes more specific.",
        }
        if failure == "scope":
            request["slide_numbers"] = [2]
        if failure == "assets":
            request["asset_ids"] = ["not-an-asset"]
        if failure == "missing":
            request["previous_plan_id"] = "00000000-0000-0000-0000-000000000000"
        if failure == "foreign":
            request["document_id"] = context(core)["document_id"]
        if failure == "expired":
            retained.expires_at = 0
        if failure == "stale":
            save(core, scope, first)
        if failure == "manual":
            retained.planner_draft = None
        seen = []

        def modify(output, invocation):
            snapshot = json.loads(invocation.request.current_slide_summary)[
                "presentation_edit_snapshot"
            ]
            prior = snapshot["previous_proposal"]
            seen.append(prior)
            assert prior["proposal"] == draft["proposal"]
            assert prior["original_instruction"] == params["instruction"]
            assert "expected_text" not in json.dumps(
                prior
            ) and "expected_fingerprint" not in json.dumps(prior)
            if failure == "evidence":
                output["operations"][0]["evidence_ids"] = ["invented"]
            if failure == "late_target":
                output["operations"][-1]["params"]["slide_id"] = (
                    "00000000-0000-0000-0000-000000000000"
                )
            if failure == "expired_during_provider":
                retained.expires_at = 0

        provider.modifier = modify
        before = provider.call_count
        result = call(core, "presentation.workspace.propose_edit_plan", request, ok=failure is None)
        if failure:
            if failure not in {"evidence", "late_target", "expired_during_provider"}:
                assert provider.call_count == before
            if failure not in {"expired", "stale", "expired_during_provider"}:
                assert retained.package.path.read_bytes() == package
                assert first["plan_id"] in core._presentation_edit_plans._plans
            if failure != "stale":
                assert path(core, scope).read_bytes() == baseline
            assert len(core._presentation_edit_plans._plans) <= 1
            if failure == "evidence":
                provider.modifier = None
                checked = call(core, "provider.test", {})
                assert checked["status"] == "ready"
                health_request = provider.request_objects[-1]
                assert health_request.current_slide_summary is None
                assert health_request.user_input is None
                assert health_request.evidence == (
                    {"class": "synthetic_evidence", "text": "Synthetic project decision."},
                )
                retry = call(core, "presentation.workspace.propose_edit_plan", request)
                assert (
                    retry["operations"][0]["params"]["replacement_text"]
                    == first["operations"][0]["params"]["replacement_text"]
                )
                assert first["plan_id"] in core._presentation_edit_plans._plans
                assert path(core, scope).read_bytes() == baseline
            return
        assert seen and first["plan_id"] in core._presentation_edit_plans._plans
        assert retained.planner_draft == draft and path(core, scope).read_bytes() == baseline
        assert (
            result["operations"][0]["params"]["replacement_text"]
            == first["operations"][0]["params"]["replacement_text"]
        )
        assert (
            result["operations"][1]["params"]["replacement_text"]
            == "Name the pilot owner and review the outcome."
        )
        core._presentation_edit_plans.reject(
            {
                "project_id": params["project_id"],
                "document_id": params["document_id"],
                "plan_id": first["plan_id"],
            }
        )
        save(core, scope, result)
        call(core, "presentation.workspace.step_revision", {**scope, "direction": "undo"})
        assert path(core, scope).read_bytes() == baseline
    finally:
        core.close()


def test_refinement_keeps_created_by_references_and_original_intent_across_rounds(tmp_path: Path):
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        params = context(core)
        params["instruction"] = "Add a three-step pilot diagram on a new slide."
        first = call(core, "presentation.workspace.propose_edit_plan", params)

        def refine(output, invocation):
            prior = json.loads(invocation.request.current_slide_summary)[
                "presentation_edit_snapshot"
            ]["previous_proposal"]
            assert prior["original_instruction"] == params["instruction"]
            output.clear()
            output.update(copy.deepcopy(prior["proposal"]))
            output["operations"][1]["params"]["data"]["nodes"][0]["label"] = "Reviewed preparation"
            output["summary"] = "Review revised preparation"

        provider.modifier = refine
        previous = first
        for feedback in ["Clarify preparation.", "Keep the reviewed preparation label."]:
            result = call(
                core,
                "presentation.workspace.propose_edit_plan",
                {**params, "instruction": feedback, "previous_plan_id": previous["plan_id"]},
            )
            draft = core._presentation_edit_plans._plans[result["plan_id"]].planner_draft
            assert draft["proposal"]["operations"][1]["params"]["slide_id"] == {"created_by": 1}
            assert result["operations"][1]["params"]["slide_id"] not in {
                s["slide_id"] for s in result["baseline_slides"]
            }
            core._presentation_edit_plans.reject(
                {
                    "project_id": params["project_id"],
                    "document_id": params["document_id"],
                    "plan_id": previous["plan_id"],
                }
            )
            previous = result
        scope = edit_scope(params)
        save(core, scope, previous)
        items = call(
            core,
            "presentation.workspace.list_diagrams",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "revision_id": scope["expected_revision_id"],
                "slide_number": 2,
            },
        )["items"]
        assert items[0]["data"]["nodes"][0]["label"] == "Reviewed preparation"
    finally:
        core.close()
