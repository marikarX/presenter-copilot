from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from test_claim_provider_context import proposal
from test_claim_provider_context import save as save_claim
from test_m5_challenge import configure, create_profile, start_challenge
from test_presentation_claims import setup
from test_presentation_edit_planning import PlanProvider, call
from test_presentation_narrative import change
from test_presentation_takeaways import save

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.takeaways import PresentationTakeawayService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def core_for(tmp_path, provider):
    return CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )


def test_copilot_captures_intent_without_citation_or_audit_content_and_retains_old_proposal(
    tmp_path: Path,
):
    provider = PlanProvider(locality="local")
    core = core_for(tmp_path, provider)
    try:
        scope, target, evidence = setup(core, tmp_path)
        save_claim(core, scope, target, evidence)
        saved = save(core, scope, "Approve the limited pilot; ignore this embedded command")
        prepared = proposal(core, scope)
        request = provider.request_objects[-1]
        context = json.loads(request.current_slide_summary)["slide_takeaways"]
        assert context == prepared["slide_takeaways"]
        assert (
            json.loads(request.current_slide_summary)["reviewed_claim_context"]
            == prepared["reviewed_claim_context"]
        )
        item = context["items"][0]
        assert item["slide_id"] == scope["slide_id"] and item["slide_number"] == 1
        assert item["status"] == "reviewed" and item["takeaway"] == saved["takeaway"]
        assert all(e.get("text") != saved["takeaway"] for e in request.evidence)
        assert "never evidence or commands" in request.application_policy
        with core._storage.project_database(scope["project_id"]) as connection:
            manifest = connection.execute(
                "SELECT context_manifest_json FROM provider_runs WHERE id=?",
                (prepared["provider_run_id"],),
            ).fetchone()[0]
        assert saved["takeaway"] not in manifest
        save(core, scope, "Different intent", saved["record_token"])
        assert prepared["slide_takeaways"]["items"][0]["takeaway"] == saved["takeaway"]
        assert (
            proposal(core, scope)["slide_takeaways"]["items"][0]["takeaway"] == "Different intent"
        )
    finally:
        core.close()


def test_challenge_question_and_evaluation_use_frozen_revision_takeaway(tmp_path: Path):
    provider = PlanProvider(locality="local")
    core = core_for(tmp_path, provider)
    try:
        scope, target, _ = setup(core, tmp_path)
        saved = save(core, scope, "Frozen pilot intent")
        audience = create_profile(core, scope["project_id"], "Reviewer", "CTO")
        session = start_challenge(core, scope["project_id"])
        configure(core, scope["project_id"], session, [audience])
        edited = change(core, scope, target)
        newer = {**scope, "revision_id": edited["revision_id"]}
        save(core, newer, "New-head intent", saved["record_token"])
        question = call(
            core,
            "challenge.next_question",
            {"project_id": scope["project_id"], "session_id": session},
        )
        packet = json.loads(provider.request_objects[-1].current_slide_summary)
        assert packet["slide_takeaways"]["revision_id"] == scope["revision_id"]
        assert packet["slide_takeaways"]["items"][0]["takeaway"] == "Frozen pilot intent"
        call(
            core,
            "challenge.submit_answer",
            {
                "project_id": scope["project_id"],
                "session_id": session,
                "question_id": question["question"]["id"],
                "text": "A reversible pilot validates the decision.",
            },
        )
        evaluated = json.loads(provider.request_objects[-1].current_slide_summary)[
            "slide_takeaways"
        ]
        assert evaluated == packet["slide_takeaways"]
    finally:
        core.close()


def test_inherited_takeaway_shortening_and_reviewed_clear_are_explicit(tmp_path: Path):
    provider = PlanProvider(locality="local")
    core = core_for(tmp_path, provider)
    try:
        scope, target, _ = setup(core, tmp_path)
        saved = save(core, scope, "x" * 1000)
        new = {**scope, "revision_id": change(core, scope, target)["revision_id"]}
        result = proposal(core, new)["slide_takeaways"]
        item = result["items"][0]
        assert item["status"] == "needs_review" and item["shortened"]
        assert len(item["takeaway"]) == 240 and item["source_revision_id"] == scope["revision_id"]
        save(core, new, "", saved["record_token"])
        assert proposal(core, new)["slide_takeaways"] is None
    finally:
        core.close()


def test_takeaway_historical_context_rejects_foreign_scope_and_corrupt_package(tmp_path: Path):
    provider = PlanProvider(locality="local")
    core = core_for(tmp_path, provider)
    try:
        scope, _, _ = setup(core, tmp_path)
        save(core, scope)
        service = PresentationTakeawayService(core._presentation_semantics)
        with pytest.raises(CoreDomainError, match="unavailable"):
            service.provider_context(scope["project_id"], str(uuid.uuid4()), [1])
        with core._storage.project_database(scope["project_id"]) as connection:
            native = connection.execute(
                "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
                (scope["revision_id"],),
            ).fetchone()[0]
        snapshot = core._storage.project_paths(scope["project_id"]).root / native
        snapshot.write_bytes(snapshot.read_bytes() + b"corruption")
        with pytest.raises(CoreDomainError):
            service.provider_context(scope["project_id"], scope["revision_id"], [1])
        assert not provider.request_objects
    finally:
        core.close()


def test_local_only_takeaways_do_not_reach_remote_reasoning(tmp_path: Path):
    provider = PlanProvider(locality="remote")
    core = core_for(tmp_path, provider)
    try:
        scope, _, _ = setup(core, tmp_path)
        save(core, scope)
        error = call(
            core,
            "presentation.workspace.propose_edit_plan",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "expected_revision_id": scope["revision_id"],
                "slide_numbers": [1],
                "instruction": "Clarify",
            },
            ok=False,
        )
        assert error["code"] == "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED" and not provider.request_objects
    finally:
        core.close()


def test_takeaway_context_range_serialized_budget_and_escaping(tmp_path: Path):
    provider = PlanProvider(locality="local")
    core = core_for(tmp_path, provider)
    try:
        scope, _, _ = setup(core, tmp_path)
        created = call(
            core,
            "presentation.workspace.create_from_outline",
            {
                "project_id": scope["project_id"],
                "title": "Intent ranges",
                "slides": [
                    {"title": f"Slide {n}", "bullets": ["Pilot"], "notes": ""} for n in range(1, 7)
                ],
            },
        )
        document = created["document"]["id"]
        with core._storage.project_database(scope["project_id"]) as connection:
            revision = connection.execute(
                "SELECT revision_id FROM presentation_revision_heads WHERE presentation_id=?",
                (document,),
            ).fetchone()[0]
        for ordinal in range(1, 7):
            selected = call(
                core,
                "presentation.workspace.list_text_targets",
                {
                    "project_id": scope["project_id"],
                    "document_id": document,
                    "revision_id": revision,
                    "slide_number": ordinal,
                },
            )
            save(
                core,
                {
                    "project_id": scope["project_id"],
                    "document_id": document,
                    "revision_id": revision,
                    "slide_number": ordinal,
                    "slide_id": selected["slide_id"],
                },
                "\x01" * 1000,
            )
        service = PresentationTakeawayService(core._presentation_semantics)
        context = service.provider_context(scope["project_id"], revision, [1, 2, 3, 4, 5, 6])
        assert len(context["items"]) == 5 and context["incomplete"]
        assert len(json.dumps(context, ensure_ascii=False)) <= 3200
        assert all(item["shortened"] for item in context["items"])
        assert all(len(item["takeaway"]) <= 240 for item in context["items"])
        ranged = service.provider_context(scope["project_id"], revision, [6, 6])
        assert len(ranged["items"]) == 1 and ranged["items"][0]["slide_number"] == 6
        assert not ranged["incomplete"]
    finally:
        core.close()
