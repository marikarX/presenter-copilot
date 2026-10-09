from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_m5_challenge import configure, create_profile, start_challenge
from test_presentation_claims import setup
from test_presentation_edit_planning import PlanProvider, call

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def save(core, scope, target, evidence):
    return call(
        core,
        "presentation.workspace.save_claim",
        {
            **scope,
            "object_id": target["object_id"],
            "quote": target["decision_text"],
            "confirm": True,
            "evidence": [
                {
                    "chunk_id": evidence["chunk_id"],
                    "sha256": evidence["sha256"],
                    "relation": "supports",
                }
            ],
        },
    )


def proposal(core, scope):
    return call(
        core,
        "presentation.workspace.propose_edit_plan",
        {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "expected_revision_id": scope["revision_id"],
            "slide_numbers": [1],
            "instruction": "Clarify the pilot decision and add a speaking reminder.",
        },
    )


def test_edit_plan_grounding_is_reviewed_hashed_and_audited(tmp_path: Path) -> None:
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        save(core, scope, target, evidence)
        prepared = proposal(core, scope)
        request = provider.request_objects[-1]
        semantics = json.loads(request.current_slide_summary)["reviewed_claim_context"]
        assert semantics == prepared["reviewed_claim_context"]
        claim = semantics["claims"][0]
        assert claim["coverage"] == "supported" and claim["reviewed_for_revision"]
        assert claim["links"][0]["grounding_included"] is True
        linked = next(
            item for item in request.evidence if item["evidence_id"] == evidence["chunk_id"]
        )
        assert linked["text"] == evidence["text"] and linked["sha256"] == evidence["sha256"]
        with core._storage.project_database(scope["project_id"]) as connection:
            manifest = json.loads(
                connection.execute(
                    "SELECT context_manifest_json FROM provider_runs WHERE id = ?",
                    (prepared["provider_run_id"],),
                ).fetchone()[0]
            )
            assert linked["source_id"] in manifest["source_ids"]
            assert evidence["text"] not in json.dumps(manifest)
            connection.execute(
                "UPDATE chunks SET text = 'Changed source finding' WHERE id = ?",
                (evidence["chunk_id"],),
            )
            connection.commit()
        prepared = proposal(core, scope)
        stale = prepared["reviewed_claim_context"]["claims"][0]
        assert stale["coverage"] == "needs_review"
        assert (
            stale["links"][0]["grounding_included"] is False
            and "evidence_id" not in stale["links"][0]
        )
        assert evidence["text"] not in provider.request_objects[-1].serialized_input()
    finally:
        core.close()


def test_challenge_uses_its_frozen_revision_after_workspace_edits(tmp_path: Path) -> None:
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        save(core, scope, target, evidence)
        audience = create_profile(core, scope["project_id"], "Reviewer", "CTO")
        session = start_challenge(core, scope["project_id"])
        configure(core, scope["project_id"], session, [audience])
        changed = call(
            core,
            "presentation.workspace.replace_text_shape",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "expected_revision_id": scope["revision_id"],
                "slide_id": scope["slide_id"],
                "object_id": target["object_id"],
                "expected_text": target["current_text"],
                "replacement_text": "Reject the pilot",
                "operation_type": "replace_text_shape",
            },
        )
        call(core, "presentation.workspace.list_claims", scope, ok=False)
        question = call(
            core,
            "challenge.next_question",
            {"project_id": scope["project_id"], "session_id": session},
        )
        assert question["question"]["text"]
        request = provider.request_objects[-1]
        semantics = json.loads(request.current_slide_summary)["reviewed_claim_context"]
        assert semantics["revision_id"] == scope["revision_id"]
        assert request.presentation_revision_ids == (scope["revision_id"],)
        assert semantics["claims"][0]["coverage"] == "supported"
        assert semantics["claims"][0]["quote_excerpt"] == target["decision_text"]
        scope["revision_id"] = changed["revision_id"]
        prepared = proposal(core, scope)
        claim = prepared["reviewed_claim_context"]["claims"][0]
        assert claim["span_status"] == "changed" and claim["coverage"] == "needs_review"
        assert claim["quote_excerpt"] is None and not claim["reviewed_for_revision"]
        assert not claim["links"][0]["grounding_included"]
    finally:
        core.close()


def test_claim_context_is_bounded_and_links_only_supplied_grounding(tmp_path: Path) -> None:
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        for _ in range(20):
            save(core, scope, target, evidence)
        result = proposal(core, scope)
        context = result["reviewed_claim_context"]
        assert context["incomplete"] is True and 1 <= len(context["claims"]) <= 8
        assert len(json.dumps(context["claims"], ensure_ascii=False)) <= 6000
        request = provider.request_objects[-1]
        included = {item["evidence_id"] for item in request.evidence}
        for claim in context["claims"]:
            for link in claim["links"]:
                if link["grounding_included"]:
                    assert link["evidence_id"] in included
                else:
                    assert "evidence_id" not in link
    finally:
        core.close()


def test_remote_claim_context_cannot_bypass_local_only(tmp_path: Path) -> None:
    provider = PlanProvider(locality="remote")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        save(core, scope, target, evidence)
        error = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "expected_revision_id": scope["revision_id"],
                "slide_numbers": [1],
                "instruction": "Clarify the decision.",
            },
            ok=False,
        )
        assert error["code"] == "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED"
        assert provider.request_objects == []
    finally:
        core.close()


def test_pruned_link_does_not_expose_an_unsupplied_citation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        save(core, scope, target, evidence)
        monkeypatch.setattr("presenter_core.providers.context.MAX_DOCUMENT_EVIDENCE", 1)
        request, manifest = core._context_builder.build(
            project_id=scope["project_id"],
            task_type="challenge_evaluation",
            question="Review the pilot.",
            user_input="The pilot tests a bounded decision.",
            privacy_mode="local_only",
            style_policy="preserve_voice",
            current_slide=1,
            presentation_revision_id=scope["revision_id"],
            additional_grounding_evidence=[
                {
                    "evidence_id": "canonical-question",
                    "text": "Canonical question grounding.",
                    "source_type": "document",
                }
            ],
        )
        context = json.loads(request.current_slide_summary)["reviewed_claim_context"]
        link = context["claims"][0]["links"][0]
        assert link["grounding_included"] is False and "evidence_id" not in link
        assert [item["evidence_id"] for item in request.evidence] == ["canonical-question"]
        assert manifest["presentation_revision_ids"] == [scope["revision_id"]]
    finally:
        core.close()
