from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
import test_local_provider
from test_claim_provider_context import save as save_claim
from test_local_provider import configure as configure_local
from test_presentation_claims import setup
from test_presentation_edit_planning import PlanProvider, call
from test_presentation_narrative import change, save, scope_only

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.narrative import FIELD_LIMITS
from presenter_core.providers.models import (
    ProviderError,
    output_schema_for,
    validate_provider_output,
)
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def payload(scope, token=None):
    return {
        **scope_only(scope),
        "fields": {**dict.fromkeys(FIELD_LIMITS, ""), "objective": "Clarify the pilot decision"},
        "expected_record_token": token,
        "instruction": "Analyze the decision narrative.",
    }


def test_narrative_suggestion_preserves_draft_saved_semantics_and_native_revision(tmp_path: Path):
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        saved = save(core, scope)
        save_claim(core, scope, target, evidence)
        params = payload(scope, saved["record_token"])
        result = call(core, "presentation.workspace.propose_narrative", params)
        assert result["requires_user_review"] and result["revision_id"] == scope["revision_id"]
        assert result["analysis_scope"]["covered_slide_count"] == 2
        assert result["analysis_scope"]["omitted_slide_count"] == 0
        assert result["analysis_scope"]["visual_content_not_analyzed"]
        assert result["fields"]["thesis"] and params["fields"]["thesis"] == ""
        assert call(core, "presentation.workspace.get_narrative", scope_only(scope)) == saved
        assert not call(core, "presentation.workspace.list_slide_purposes", scope_only(scope))[
            "items"
        ]
        request = provider.request_objects[-1]
        packet = json.loads(request.current_slide_summary)
        assert packet["presentation_narrative_snapshot"]["draft_fields"] == params["fields"]
        assert packet["presentation_narrative_snapshot"]["slides"][0]["text_excerpt"].startswith(
            target["current_text"]
        )
        assert packet["reviewed_claim_context"]["claims"][0]["links"][0]["grounding_included"]
        assert request.presentation_revision_ids == (scope["revision_id"],)
        with core._storage.project_database(scope["project_id"]) as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM presentation_revisions").fetchone()[0] == 1
            )
            row = connection.execute(
                "SELECT status,context_manifest_json FROM provider_runs WHERE id=?",
                (result["provider_run_id"],),
            ).fetchone()
        assert (
            row["status"] == "success"
            and "presentation_narrative_review" in row["context_manifest_json"]
        )
        assert "Clarify the pilot decision" not in row["context_manifest_json"]
        assert target["current_text"] not in row["context_manifest_json"]
    finally:
        core.close()


@pytest.mark.parametrize(
    "failure",
    [
        "foreign_slide",
        "duplicate_slide",
        "fabricated_evidence",
        "bad_fields",
        "bad_role",
        "changed_head",
        "changed_intent",
        "changed_snapshot",
        "stale_token",
        "bad_range",
    ],
)
def test_invalid_or_stale_narrative_suggestions_are_rejected_and_audited(tmp_path: Path, failure):
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, target, _ = setup(core, tmp_path)
        params = payload(scope)
        if failure == "stale_token":
            params["expected_record_token"] = str(uuid.uuid4())
        if failure == "bad_range":
            params["start_slide"] = 0

        def modify(output, _request):
            if failure == "foreign_slide":
                output["findings"][0]["slide_id"] = str(uuid.uuid4())
            if failure == "duplicate_slide":
                output["findings"].append(output["findings"][0])
            if failure == "fabricated_evidence":
                output["findings"][0]["evidence_ids"] = ["invented"]
            if failure == "bad_fields":
                del output["fields"]["thesis"]
            if failure == "bad_role":
                output["findings"][0]["role"] = ["instruction"]
            if failure == "changed_head":
                change(core, scope, target)
            if failure == "changed_intent":
                save(core, scope, text="Changed by another view")
            if failure == "changed_snapshot":
                row = core._presentation_edits._current_revision_source(
                    scope["project_id"], scope["document_id"]
                )
                path = core._storage.paths.snapshot_path(
                    scope["project_id"], row["local_snapshot_path"], require_exists=True
                )
                path.write_bytes(path.read_bytes() + b"changed")

        provider.modifier = modify
        error = call(core, "presentation.workspace.propose_narrative", params, ok=False)
        assert error["code"] in {
            "PROVIDER_MALFORMED_OUTPUT",
            "PRESENTATION_REVISION_CONFLICT",
            "PRESENTATION_NARRATIVE_CONFLICT",
            "SOURCE_SNAPSHOT_CHANGED",
            "INVALID_REQUEST",
        }
        if failure in {"stale_token", "bad_range"}:
            assert not provider.request_objects
        else:
            with core._storage.project_database(scope["project_id"]) as connection:
                assert (
                    connection.execute(
                        "SELECT status FROM provider_runs "
                        "WHERE task_type='presentation_narrative_review'"
                    ).fetchone()[0]
                    == "error"
                )
    finally:
        core.close()


@pytest.mark.parametrize("mode", ["local_only", "changed_policy"])
def test_narrative_suggestion_privacy_is_enforced_before_and_after_inference(tmp_path: Path, mode):
    provider = PlanProvider(locality="remote")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        scope, _, _ = setup(core, tmp_path)
        if mode == "changed_policy":
            call(
                core,
                "project.update_settings",
                {"project_id": scope["project_id"], "privacy_mode": "selected_context_cloud"},
            )
            call(core, "project.acknowledge_remote_reasoning", {"project_id": scope["project_id"]})

            def mutate(_output, _request):
                call(
                    core,
                    "project.update_settings",
                    {"project_id": scope["project_id"], "privacy_mode": "local_only"},
                )

            provider.modifier = mutate
        error = call(core, "presentation.workspace.propose_narrative", payload(scope), ok=False)
        assert error["code"] in {"PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED", "PRIVACY_POLICY_CHANGED"}
        assert len(provider.request_objects) == (0 if mode == "local_only" else 1)
        assert (
            call(core, "presentation.workspace.get_narrative", scope_only(scope))["status"]
            == "missing"
        )
    finally:
        core.close()


def test_narrative_range_and_shortened_scope_are_explicit(tmp_path: Path):
    provider = PlanProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        project = call(core, "project.create", {"name": "Long narrative"})["project"]["id"]
        document = call(
            core,
            "presentation.workspace.create_from_outline",
            {
                "project_id": project,
                "title": "Long deck",
                "slides": [
                    {
                        "title": f"Slide {i}",
                        "bullets": ["point" * 35] * 4,
                        "notes": "Speaking note. " * 100,
                    }
                    for i in range(3)
                ],
            },
        )["document"]["id"]
        scope = {
            "project_id": project,
            "document_id": document,
            "revision_id": core._presentation_edits._current_revision_source(project, document)[
                "revision_id"
            ],
        }
        result = call(
            core,
            "presentation.workspace.propose_narrative",
            {**payload(scope), "start_slide": 2, "slide_count": 1},
        )
        assert result["analysis_scope"]["start_slide"] == result["analysis_scope"]["end_slide"] == 2
        assert result["analysis_scope"]["omitted_slide_count"] == 2
        assert result["analysis_scope"]["shortened_slide_numbers"] == [2]
        assert result["findings"][0]["slide_number"] == 2
        slide = json.loads(provider.request_objects[-1].current_slide_summary)[
            "presentation_narrative_snapshot"
        ]["slides"][0]
        assert len(slide["text_excerpt"]) == 600 and len(slide["notes_excerpt"]) == 120
    finally:
        core.close()


def test_narrative_schema_strictly_rejects_edit_commands_and_unsafe_text():
    schema = output_schema_for("presentation_narrative_review")
    assert schema["additionalProperties"] is False
    valid = {"summary": "Review", "fields": dict.fromkeys(FIELD_LIMITS, ""), "findings": []}
    assert validate_provider_output("presentation_narrative_review", valid) == valid
    for value in [{**valid, "operations": []}, {**valid, "summary": "bad\x00text"}]:
        with pytest.raises(ProviderError):
            validate_provider_output("presentation_narrative_review", value)


@pytest.fixture
def narrative_server():
    yield from test_local_provider.server.__wrapped__()


def test_narrative_task_uses_strict_local_transport_with_larger_output_budget(
    tmp_path: Path, narrative_server
):
    server = narrative_server
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, _, _ = setup(core, tmp_path)
        configure_local(core, server["endpoint"])
        call(core, "provider.test", {"provider_id": "local_openai"})
        server["body"] = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Review the supplied deck",
                                    "fields": dict.fromkeys(FIELD_LIMITS, ""),
                                    "findings": [],
                                }
                            )
                        },
                    }
                ]
            }
        ).encode()
        result = call(core, "presentation.workspace.propose_narrative", payload(scope))
        assert result["provider_id"] == "local_openai" and result["requires_user_review"]
        _, _, body = server["calls"][-1]
        assert body["max_tokens"] == 4096 and "tools" not in body
        assert body["response_format"]["json_schema"]["name"] == "presentation_narrative_review"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert (
            call(core, "presentation.workspace.get_narrative", scope_only(scope))["status"]
            == "missing"
        )
    finally:
        core.close()
