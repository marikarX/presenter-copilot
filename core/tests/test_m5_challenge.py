from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from presenter_core.__main__ import _explicit_developer_provider
from presenter_core.ipc.core import CoreService
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.providers.models import ReasoningResult, validate_provider_output
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter
from presenter_core.storage.database import (
    _migrate_project_v1,
    _migrate_project_v2,
    _migrate_project_v3,
    _migrate_project_v4,
    connect_project_database,
)

FIXTURE_ROOT = Path(__file__).parents[2] / "samples" / "synthetic-deck"


def test_deterministic_fake_provider_requires_explicit_developer_flags(monkeypatch: Any) -> None:
    monkeypatch.delenv("PRESENTER_COPILOT_DEV_MODE", raising=False)
    monkeypatch.delenv("PRESENTER_COPILOT_TEST_PROVIDER", raising=False)
    assert _explicit_developer_provider() is None

    monkeypatch.setenv("PRESENTER_COPILOT_DEV_MODE", "1")
    assert _explicit_developer_provider() is None

    monkeypatch.setenv("PRESENTER_COPILOT_TEST_PROVIDER", "deterministic_fake")
    provider = _explicit_developer_provider()
    assert provider is not None
    assert provider.id == "fake-test"
    assert provider.locality == "local"


def call(core: CoreService, request_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": request_id,
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is True, response
    assert isinstance(response["result"], dict)
    return response["result"]


def error_call(
    core: CoreService, request_id: str, method: str, params: dict[str, Any]
) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": request_id,
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is False, response
    return response["error"]


def create_project(core: CoreService, *, privacy_mode: str = "selected_context_cloud") -> str:
    result = call(
        core,
        "create-project",
        "project.create",
        {"name": "M5 Challenge", "privacy_mode": privacy_mode},
    )
    return str(result["project"]["id"])


def seed_project_evidence(core: CoreService, project_id: str) -> dict[str, str]:
    document_id = str(uuid.uuid4())
    unit_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    presentation_id = str(uuid.uuid4())
    now = "2026-09-02T00:00:00Z"
    with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
        connection.execute(
            """
            INSERT INTO documents (
                id, project_id, kind, original_name, local_snapshot_path, source_uri,
                sha256, mime_type, parser_id, imported_at, parse_status,
                parse_error_code, parse_error_message, byte_size, metadata_json
            ) VALUES (?, ?, 'supporting', 'decision-notes.md', NULL, NULL, ?, 'text/markdown',
                      'test.fixture', ?, 'ready', NULL, NULL, 20, '{}')
            """,
            (document_id, project_id, "a" * 64, now),
        )
        connection.execute(
            """
            INSERT INTO source_units (
                id, document_id, unit_type, ordinal, title, start_ms, end_ms,
                speaker_label, text, metadata_json
            ) VALUES (?, ?, 'section', 1, 'Decision', NULL, NULL, NULL, ?, '{}')
            """,
            (
                unit_id,
                document_id,
                "The finance case compares annual cost and downside against the current platform. "
                "The technical plan targets RTO recovery, availability, migration, and rollback.",
            ),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                id, source_unit_id, chunk_index, text, token_count, embedding_key,
                lexical_text, created_at
            ) VALUES (?, ?, 0, ?, NULL, NULL, ?, ?)
            """,
            (
                chunk_id,
                unit_id,
                "The finance case compares annual cost and downside against the current platform. "
                "The technical plan targets RTO recovery, availability, migration, and rollback.",
                "the finance case compares annual cost and downside against the current platform "
                "the technical plan targets rto recovery availability migration and rollback",
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, project_id, kind, original_name, local_snapshot_path, source_uri,
                sha256, mime_type, parser_id, imported_at, parse_status,
                parse_error_code, parse_error_message, byte_size, metadata_json
            ) VALUES (?, ?, 'presentation', 'proposal.pptx', NULL, NULL, ?,
                      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                      'test.fixture', ?, 'ready', NULL, NULL, 20, '{}')
            """,
            (presentation_id, project_id, "b" * 64, now),
        )
        for ordinal, text in enumerate(
            (
                "Slide 1: executive decision and annual cost.",
                "Slide 2: migration and RTO recovery plan.",
                "Slide 3: availability and rollback controls.",
            ),
            start=1,
        ):
            slide_unit_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO source_units (
                    id, document_id, unit_type, ordinal, title, start_ms, end_ms,
                    speaker_label, text, metadata_json
                ) VALUES (?, ?, 'slide', ?, ?, NULL, NULL, NULL, ?, '{}')
                """,
                (slide_unit_id, presentation_id, ordinal, f"Slide {ordinal}", text),
            )
            connection.execute(
                """
                INSERT INTO chunks (
                    id, source_unit_id, chunk_index, text, token_count, embedding_key,
                    lexical_text, created_at
                ) VALUES (?, ?, 0, ?, NULL, NULL, ?, ?)
                """,
                (str(uuid.uuid4()), slide_unit_id, text, text.casefold(), now),
            )
        connection.execute(
            "UPDATE project SET current_presentation_id = ? WHERE id = ?",
            (presentation_id, project_id),
        )
        connection.commit()
    return {"document_id": document_id, "unit_id": unit_id, "chunk_id": chunk_id}


def create_profile(core: CoreService, project_id: str, name: str, role: str) -> str:
    result = call(
        core,
        f"profile-{name}",
        "audience.create",
        {
            "project_id": project_id,
            "display_name": name,
            "role": role,
            "organization": "ExampleCo",
            "user_notes": "User supplied role context only.",
        },
    )
    return str(result["profile"]["id"])


def create_observation(core: CoreService, project_id: str, profile_id: str, text: str) -> str:
    result = call(
        core,
        f"observation-{profile_id}",
        "audience.create_observation",
        {
            "project_id": project_id,
            "audience_profile_id": profile_id,
            "observation_type": "decision_criterion",
            "text": text,
        },
    )
    return str(result["observation"]["id"])


def start_challenge(core: CoreService, project_id: str) -> str:
    result = call(
        core,
        "start-challenge",
        "session.start",
        {"project_id": project_id, "mode": "challenge"},
    )
    return str(result["session"]["id"])


def configure(
    core: CoreService,
    project_id: str,
    session_id: str,
    profile_ids: list[str],
    **overrides: Any,
) -> dict[str, Any]:
    return call(
        core,
        "configure-challenge",
        "challenge.configure",
        {
            "project_id": project_id,
            "session_id": session_id,
            "audience_profile_ids": profile_ids,
            "intensity": "skeptical",
            "allow_follow_ups": True,
            "scope": "full_deck",
            **overrides,
        },
    )


def test_challenge_vertical_slice_retry_preferred_and_restart(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    provider = DeterministicFakeReasoningProvider()
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    project_id = create_project(core)
    evidence_ids = seed_project_evidence(core, project_id)
    jane_id = create_profile(core, project_id, "Jane Smith", "CFO")
    robert_id = create_profile(core, project_id, "Robert Chen", "CTO")
    jane_observation = create_observation(
        core, project_id, jane_id, "Prioritizes cost comparison and downside risk."
    )
    robert_observation = create_observation(
        core, project_id, robert_id, "Prioritizes RTO, availability, and rollback safety."
    )
    call(core, "ack", "project.acknowledge_remote_reasoning", {"project_id": project_id})
    session_id = start_challenge(core, project_id)
    configured = configure(core, project_id, session_id, [jane_id, robert_id])
    assert configured["state"] == "ready_for_question"
    assert [item["id"] for item in configured["audiences"]] == [jane_id, robert_id]

    first = call(
        core,
        "question-a",
        "challenge.next_question",
        {"project_id": project_id, "session_id": session_id},
    )
    question_a = first["question"]
    assert question_a["audience_profile_id"] == jane_id
    assert "cost" in question_a["text"].casefold()
    assert question_a["rationale"]
    assert question_a["evidence"]
    assert {item["evidence_id"] for item in question_a["evidence"]} <= {
        evidence_ids["chunk_id"]
    } | {item.get("evidence_id") for item in first["question"]["evidence"]}
    assert any(
        item["observation_id"] == jane_observation for item in question_a["audience_observations"]
    )
    manifest = first["context_manifest"]
    assert jane_id in manifest["audience_profile_ids"]
    assert jane_observation in manifest["audience_observation_ids"]
    assert manifest["full_corpus_sent"] is False

    weak = call(
        core,
        "answer-weak",
        "challenge.submit_answer",
        {
            "project_id": project_id,
            "session_id": session_id,
            "question_id": question_a["id"],
            "text": "It is a good proposal.",
        },
    )
    weak_answer = weak["answer_version"]
    assert weak_answer["origin"] == "user_typed"
    assert weak["evaluation"]["style_match"]["score"] is None
    assert "Not enough style evidence" in weak["evaluation"]["style_match"]["feedback"]

    retried = call(
        core,
        "retry-a",
        "challenge.retry_question",
        {
            "project_id": project_id,
            "session_id": session_id,
            "question_id": question_a["id"],
        },
    )
    assert retried["current_question"]["id"] == question_a["id"]
    strong = call(
        core,
        "answer-strong",
        "challenge.submit_answer",
        {
            "project_id": project_id,
            "session_id": session_id,
            "question_id": question_a["id"],
            "text": (
                "We compare annual cost and downside against the current platform, while the "
                "migration plan protects RTO recovery, availability, and rollback safety."
            ),
        },
    )
    strong_answer = strong["answer_version"]
    assert strong_answer["id"] != weak_answer["id"]
    assert strong["evaluation"]["correctness"]["score"] > weak["evaluation"]["correctness"]["score"]

    saved = call(
        core,
        "save-preferred",
        "challenge.save_preferred_answer",
        {
            "project_id": project_id,
            "session_id": session_id,
            "question_id": question_a["id"],
            "answer_version_id": strong_answer["id"],
        },
    )
    assert saved["knowledge_item"]["kind"] == "answer"
    assert saved["knowledge_item"]["created_by"] == "user"
    assert saved["knowledge_item"]["preferred"] is True
    assert (
        call(
            core,
            "save-preferred-again",
            "challenge.save_preferred_answer",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question_a["id"],
                "answer_version_id": strong_answer["id"],
            },
        )["semantic_sync"]["status"]
        == "not_needed"
    )

    follow_up = call(
        core,
        "follow-up-a",
        "challenge.next_question",
        {
            "project_id": project_id,
            "session_id": session_id,
            "follow_up_to_question_id": question_a["id"],
        },
    )
    assert follow_up["question"]["parent_question_id"] == question_a["id"]
    assert follow_up["question"]["audience_profile_id"] == jane_id

    # Retry the follow-up only through a disposable answer cycle so the normal
    # round-robin root question can exercise the second selected profile.
    call(
        core,
        "answer-follow-up",
        "challenge.submit_answer",
        {
            "project_id": project_id,
            "session_id": session_id,
            "question_id": follow_up["question"]["id"],
            "text": "The evidence and next step should make the cost trade-off explicit.",
        },
    )
    second = call(
        core,
        "question-b",
        "challenge.next_question",
        {"project_id": project_id, "session_id": session_id},
    )
    assert second["question"]["audience_profile_id"] == robert_id
    assert "migration" in second["question"]["text"].casefold()
    assert any(
        item["observation_id"] == robert_observation
        for item in second["question"]["audience_observations"]
    )

    history = call(
        core,
        "history",
        "challenge.list_history",
        {"project_id": project_id, "session_id": session_id, "limit": 10},
    )
    assert history["total"] == 3
    assert len(history["items"][0]["answer_versions"]) == 2
    assert any(answer["preferred"] for answer in history["items"][0]["answer_versions"])

    retrieval = call(
        core,
        "retrieve-practice",
        "retrieval.query",
        {
            "project_id": project_id,
            "query": "annual cost downside current platform",
            "usage": "rehearsal",
            "limit": 10,
        },
    )
    practiced = [
        hit["evidence"]
        for hit in retrieval["hits"]
        if hit["evidence"].get("knowledge_item_id") == saved["knowledge_item"]["id"]
    ]
    assert practiced
    assert practiced[0]["label"] == "Your practiced answer"

    core.close()
    restarted_provider = DeterministicFakeReasoningProvider()
    restarted = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=restarted_provider,
    )
    try:
        recovered = call(
            restarted,
            "recovered-state",
            "challenge.get_state",
            {"project_id": project_id, "session_id": session_id},
        )
        assert recovered["state"] == "awaiting_answer"
        assert recovered["current_question"]["id"] == second["question"]["id"]
        assert (
            call(
                restarted,
                "recovered-history",
                "challenge.list_history",
                {"project_id": project_id, "session_id": session_id, "limit": 10},
            )["total"]
            == 3
        )
        assert restarted_provider.call_count == 0
        call(
            restarted,
            "delete-challenge-session",
            "session.delete",
            {"project_id": project_id, "session_id": session_id},
        )
        with restarted._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            durable = connection.execute(
                "SELECT origin_session_id FROM knowledge_items WHERE id = ?",
                (saved["knowledge_item"]["id"],),
            ).fetchone()
            assert durable is not None and durable["origin_session_id"] is None
            assert connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM answer_versions").fetchone()[0] == 0
            assert (
                connection.execute("SELECT COUNT(*) FROM challenge_answer_promotions").fetchone()[0]
                == 0
            )
        durable_retrieval = call(
            restarted,
            "durable-practice",
            "retrieval.query",
            {
                "project_id": project_id,
                "query": "annual cost downside current platform",
                "usage": "rehearsal",
                "limit": 10,
            },
        )
        assert any(
            hit["evidence"].get("knowledge_item_id") == saved["knowledge_item"]["id"]
            for hit in durable_retrieval["hits"]
        )
        call(
            restarted,
            "delete-practice",
            "knowledge.delete",
            {"project_id": project_id, "knowledge_item_id": saved["knowledge_item"]["id"]},
        )
        with restarted._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM embedding_vectors "
                    "WHERE entity_type = 'knowledge_item' AND entity_id = ?",
                    (saved["knowledge_item"]["id"],),
                ).fetchone()[0]
                == 0
            )
    finally:
        restarted.close()


def test_challenge_validation_privacy_and_lifecycle_boundaries(tmp_path: Path) -> None:
    provider = DeterministicFakeReasoningProvider()
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        reasoning_provider=provider,
    )
    project_a = create_project(core, privacy_mode="local_only")
    project_b = create_project(core, privacy_mode="selected_context_cloud")
    seed_project_evidence(core, project_a)
    profile_a = create_profile(core, project_a, "A", "CFO")
    profile_b = create_profile(core, project_b, "B", "CTO")
    session_a = start_challenge(core, project_a)
    for index, selected in enumerate(([], [profile_a, profile_a, profile_b, profile_a])):
        error = error_call(
            core,
            f"invalid-{index}",
            "challenge.configure",
            {
                "project_id": project_a,
                "session_id": session_a,
                "audience_profile_ids": selected,
            },
        )
        assert error["code"] == "CHALLENGE_AUDIENCE_INVALID"
    cross_session = start_challenge(core, project_a)
    cross_profile_error = error_call(
        core,
        "cross-profile",
        "challenge.configure",
        {
            "project_id": project_a,
            "session_id": cross_session,
            "audience_profile_ids": [profile_b],
        },
    )
    assert cross_profile_error["code"] == "CHALLENGE_AUDIENCE_INVALID"
    range_error = error_call(
        core,
        "bad-range",
        "challenge.configure",
        {
            "project_id": project_a,
            "session_id": cross_session,
            "audience_profile_ids": [profile_a],
            "scope": "slide_range",
            "slide_start": 2,
            "slide_end": 1,
        },
    )
    assert range_error["code"] == "CHALLENGE_CONFIG_INVALID"
    configure(core, project_a, cross_session, [profile_a])
    unavailable = error_call(
        core,
        "local-only-provider",
        "challenge.next_question",
        {"project_id": project_a, "session_id": cross_session},
    )
    assert unavailable["code"] == "CHALLENGE_REASONING_UNAVAILABLE"
    assert provider.call_count == 0

    core.close()


def test_challenge_source_and_profile_deletion_preserve_history_without_excerpts(
    tmp_path: Path,
) -> None:
    provider = DeterministicFakeReasoningProvider()
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        reasoning_provider=provider,
    )
    project_id = create_project(core)
    source = seed_project_evidence(core, project_id)
    profile_id = create_profile(core, project_id, "Historical", "CFO")
    create_observation(core, project_id, profile_id, "Cares about cost evidence.")
    call(core, "ack", "project.acknowledge_remote_reasoning", {"project_id": project_id})
    session_id = start_challenge(core, project_id)
    configure(core, project_id, session_id, [profile_id])
    question = call(
        core,
        "question",
        "challenge.next_question",
        {"project_id": project_id, "session_id": session_id},
    )["question"]
    call(
        core,
        "answer",
        "challenge.submit_answer",
        {
            "project_id": project_id,
            "session_id": session_id,
            "question_id": question["id"],
            "text": "The annual cost and downside are supported by the decision notes.",
        },
    )
    call(
        core,
        "delete-profile",
        "audience.delete",
        {"project_id": project_id, "audience_profile_id": profile_id},
    )
    history = call(
        core,
        "history-after-profile-delete",
        "challenge.list_history",
        {"project_id": project_id, "session_id": session_id},
    )
    assert history["items"][0]["text"] == question["text"]
    assert history["items"][0]["audience"]["historical"] is True
    assert history["items"][0]["audience"]["display_name"] == "Historical"
    call(
        core,
        "delete-source",
        "source.delete",
        {"project_id": project_id, "document_id": source["document_id"]},
    )
    after_source_delete = call(
        core,
        "history-after-source-delete",
        "challenge.list_history",
        {"project_id": project_id, "session_id": session_id},
    )
    assert after_source_delete["items"][0]["evidence"][0]["available"] is False
    with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
        question_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(questions)").fetchall()
        }
        assert "text" in question_columns
        assert "text" not in {
            row[1] for row in connection.execute("PRAGMA table_info(question_evidence)").fetchall()
        }
    core.close()


def test_v4_to_v5_migration_retains_m4_state_and_is_forward_only(tmp_path: Path) -> None:
    project_path = tmp_path / "v4-project.db"
    project_id = str(uuid.uuid4())
    profile_id = str(uuid.uuid4())
    second_profile_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    presentation_id = str(uuid.uuid4())
    transcript_document_id = str(uuid.uuid4())
    source_unit_id = str(uuid.uuid4())
    transcript_unit_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    generation_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    utterance_id = str(uuid.uuid4())
    provider_run_id = str(uuid.uuid4())
    statement_id = str(uuid.uuid4())
    knowledge_id = str(uuid.uuid4())
    candidate_id = str(uuid.uuid4())
    stale_candidate_id = str(uuid.uuid4())
    observation_id = str(uuid.uuid4())
    stale_observation_id = str(uuid.uuid4())
    speaker_map_id = str(uuid.uuid4())
    with sqlite3.connect(project_path) as connection:
        _migrate_project_v1(connection)
        _migrate_project_v2(connection)
        _migrate_project_v3(connection)
        _migrate_project_v4(connection)
        connection.execute(
            """
            INSERT INTO project (
                id, name, created_at, updated_at, privacy_mode, default_style_policy,
                custom_style_guidance, current_presentation_id, schema_version
            ) VALUES (?, 'v4', 'created', 'updated', 'local_only', 'preserve_voice', NULL, NULL, 4)
            """,
            (project_id,),
        )
        connection.execute(
            """
            INSERT INTO audience_profiles (
                id, project_id, display_name, role, organization, user_notes,
                active, created_at, updated_at
            ) VALUES (?, ?, 'M4 Profile', 'CFO', 'ExampleCo', NULL, 1, 'created', 'updated')
            """,
            (profile_id, project_id),
        )
        connection.execute(
            """
            INSERT INTO audience_observations (
                id, audience_profile_id, observation_type, text, derivation,
                confidence, sensitive_trait, review_status, created_at, updated_at
            ) VALUES (
                ?, ?, 'decision_criterion', 'Cost', 'user_entered', NULL, 0,
                'active', 'created', 'updated'
            )
            """,
            (observation_id, profile_id),
        )
        connection.execute(
            """
            INSERT INTO audience_profiles (
                id, project_id, display_name, role, organization, user_notes,
                active, created_at, updated_at
            ) VALUES (?, ?, 'M4 Technical Profile', 'CTO', 'ExampleCo', NULL, 1,
                      'created', 'updated')
            """,
            (second_profile_id, project_id),
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, project_id, kind, original_name, local_snapshot_path, source_uri,
                sha256, mime_type, parser_id, imported_at, parse_status,
                parse_error_code, parse_error_message, byte_size, metadata_json
            ) VALUES (?, ?, 'presentation', 'm4-deck.pptx', NULL, NULL, ?,
                      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                      'test', 'created', 'ready', NULL, NULL, 0, '{}')
            """,
            (presentation_id, project_id, "d" * 64),
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, project_id, kind, original_name, local_snapshot_path, source_uri,
                sha256, mime_type, parser_id, imported_at, parse_status,
                parse_error_code, parse_error_message, byte_size, metadata_json
            ) VALUES (?, ?, 'transcript', 'm4-meeting.vtt', NULL, NULL, ?, 'text/vtt',
                      'test', 'created', 'ready', NULL, NULL, 0, '{}')
            """,
            (transcript_document_id, project_id, "e" * 64),
        )
        connection.execute(
            """
            INSERT INTO source_units (
                id, document_id, unit_type, ordinal, title, start_ms, end_ms,
                speaker_label, text, metadata_json
            ) VALUES (?, ?, 'slide', 1, 'Decision', NULL, NULL, NULL,
                      'The decision compares cost and recovery risk.', '{}')
            """,
            (source_unit_id, presentation_id),
        )
        connection.execute(
            """
            INSERT INTO source_units (
                id, document_id, unit_type, ordinal, title, start_ms, end_ms,
                speaker_label, text, metadata_json
            ) VALUES (?, ?, 'transcript_segment', NULL, NULL, 1000, 3000,
                      'M4 Profile', 'We need the cost case and recovery plan.', '{}')
            """,
            (transcript_unit_id, transcript_document_id),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                id, source_unit_id, chunk_index, text, token_count, embedding_key,
                lexical_text, created_at
            ) VALUES (?, ?, 0, 'The decision compares cost and recovery risk.', 7,
                      'generation:chunk', 'the decision compares cost and recovery risk', 'created')
            """,
            (chunk_id, source_unit_id),
        )
        connection.execute("UPDATE project SET current_presentation_id = ?", (presentation_id,))
        connection.execute(
            """
            INSERT INTO transcript_speaker_maps (
                id, document_id, native_speaker_label, audience_profile_id,
                mapped_by, created_at
            ) VALUES (?, ?, 'M4 Profile', ?, 'user', 'created')
            """,
            (speaker_map_id, transcript_document_id, profile_id),
        )
        connection.execute(
            """
            INSERT INTO audience_observations (
                id, audience_profile_id, observation_type, text, derivation,
                confidence, sensitive_trait, review_status, created_at, updated_at
            ) VALUES (?, ?, 'decision_criterion', 'Prioritizes recovery evidence.',
                      'source_derived', 0.8, 0, 'stale', 'created', 'updated')
            """,
            (stale_observation_id, second_profile_id),
        )
        connection.execute(
            """
            INSERT INTO audience_observation_evidence (
                observation_id, provenance_type, provenance_id
            ) VALUES (?, 'transcript', ?)
            """,
            (observation_id, transcript_unit_id),
        )
        connection.execute(
            """
            INSERT INTO audience_observation_evidence (
                observation_id, provenance_type, provenance_id
            ) VALUES (?, 'transcript', ?)
            """,
            (stale_observation_id, transcript_unit_id),
        )
        connection.execute(
            """
            INSERT INTO audience_observation_candidates (
                id, audience_profile_id, observation_type, proposed_text, confidence,
                fingerprint, status, observation_id, created_at, updated_at
            ) VALUES (?, ?, 'decision_criterion', 'Accepted recovery criterion.', 0.8,
                      ?, 'accepted', ?, 'created', 'updated')
            """,
            (candidate_id, profile_id, "f" * 64, observation_id),
        )
        connection.execute(
            """
            INSERT INTO audience_observation_candidates (
                id, audience_profile_id, observation_type, proposed_text, confidence,
                fingerprint, status, observation_id, created_at, updated_at
            ) VALUES (?, ?, 'decision_criterion', 'Stale recovery criterion.', 0.7,
                      ?, 'stale', ?, 'created', 'updated')
            """,
            (stale_candidate_id, second_profile_id, "1" * 64, stale_observation_id),
        )
        connection.execute(
            """
            INSERT INTO audience_observation_candidate_evidence (
                candidate_id, provenance_type, provenance_id
            ) VALUES (?, 'transcript', ?)
            """,
            (candidate_id, transcript_unit_id),
        )
        connection.execute(
            """
            INSERT INTO audience_observation_candidate_evidence (
                candidate_id, provenance_type, provenance_id
            ) VALUES (?, 'transcript', ?)
            """,
            (stale_candidate_id, transcript_unit_id),
        )
        connection.execute(
            """
            INSERT INTO sessions (
                id, project_id, mode, started_at, ended_at, style_policy,
                privacy_mode, provider_id, current_slide_start, status, teach_state
            ) VALUES (?, ?, 'teach', 'created', NULL, 'preserve_voice',
                      'local_only', 'fake-test', 1, 'active', 'prompted')
            """,
            (session_id, project_id),
        )
        connection.execute(
            """
            INSERT INTO utterances (
                id, session_id, actor, text, created_at, start_ms, end_ms,
                asr_confidence, slide_ordinal, is_final
            ) VALUES (?, ?, 'user', 'The recovery plan protects the decision.',
                      'created', 1000, 3000, 0.99, 1, 1)
            """,
            (utterance_id, session_id),
        )
        connection.execute(
            """
            INSERT INTO user_statements (
                id, project_id, origin_session_id, source_utterance_id, text, created_at
            ) VALUES (?, ?, ?, ?, 'The recovery plan protects the decision.', 'created')
            """,
            (statement_id, project_id, session_id, utterance_id),
        )
        connection.execute(
            """
            INSERT INTO knowledge_items (
                id, project_id, kind, text, use_live, use_rehearsal, preferred, private,
                created_by, origin_session_id, created_at, updated_at
            ) VALUES (?, ?, 'answer', 'The recovery plan protects the decision.', 1, 1, 1, 0,
                      'user', ?, 'created', 'updated')
            """,
            (knowledge_id, project_id, session_id),
        )
        connection.execute(
            """
            INSERT INTO knowledge_evidence (knowledge_item_id, provenance_type, provenance_id)
            VALUES (?, 'user_statement', ?)
            """,
            (knowledge_id, statement_id),
        )
        connection.execute(
            """
            INSERT INTO provider_runs (
                id, session_id, task_type, provider_id, privacy_mode, started_at,
                ended_at, status, input_token_count, output_token_count, latency_ms,
                context_manifest_json, error_code
            ) VALUES (?, ?, 'teach_question', 'fake-test', 'local_only', 'created',
                      'updated', 'success', 10, 5, 12, '{}', NULL)
            """,
            (provider_run_id, session_id),
        )
        connection.execute(
            """
            INSERT INTO teach_candidates (
                id, session_id, source_utterance_id, proposed_kind, proposed_text,
                provider_run_id, status, knowledge_item_id, created_at
            ) VALUES (?, ?, ?, 'answer', 'The recovery plan protects the decision.',
                      ?, 'confirmed', ?, 'created')
            """,
            (str(uuid.uuid4()), session_id, utterance_id, provider_run_id, knowledge_id),
        )
        connection.execute(
            """
            INSERT INTO embedding_generations (
                id, adapter_id, model_id, model_fingerprint, dimension,
                matrix_relative_path, matrix_row_count, is_active, created_at
            ) VALUES (?, 'deterministic', 'm4-model', ?, 2, 'embeddings/m4.npy', 2, 1, 'created')
            """,
            (generation_id, "2" * 16),
        )
        connection.execute(
            """
            INSERT INTO embedding_vectors (
                generation_id, vector_id, entity_type, entity_id, project_id,
                source_class, row_index, content_sha256
            ) VALUES (?, 'vector-chunk', 'chunk', ?, ?, 'document', 0, ?)
            """,
            (generation_id, chunk_id, project_id, "3" * 64),
        )
        connection.execute(
            """
            INSERT INTO embedding_vectors (
                generation_id, vector_id, entity_type, entity_id, project_id,
                source_class, row_index, content_sha256
            ) VALUES (?, 'vector-knowledge', 'knowledge_item', ?, ?, 'user_knowledge', 1, ?)
            """,
            (generation_id, knowledge_id, project_id, "4" * 64),
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, project_id, kind, original_name, local_snapshot_path, source_uri,
                sha256, mime_type, parser_id, imported_at, parse_status,
                parse_error_code, parse_error_message, byte_size, metadata_json
            ) VALUES (?, ?, 'supporting', 'm4.md', NULL, NULL, ?, 'text/markdown',
                      'test', 'created', 'ready', NULL, NULL, 0, '{}')
            """,
            (document_id, project_id, "c" * 64),
        )
        connection.execute("PRAGMA user_version = 4")
        connection.commit()
    migrated = connect_project_database(project_path)
    try:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 5
        assert migrated.execute("SELECT schema_version FROM project").fetchone()[0] == 5
        assert (
            migrated.execute(
                "SELECT id FROM audience_profiles WHERE id = ?", (profile_id,)
            ).fetchone()[0]
            == profile_id
        )
        assert (
            migrated.execute(
                "SELECT id FROM audience_observations WHERE id = ?", (observation_id,)
            ).fetchone()[0]
            == observation_id
        )
        assert (
            migrated.execute("SELECT id FROM documents WHERE id = ?", (document_id,)).fetchone()[0]
            == document_id
        )
        assert (
            migrated.execute(
                "SELECT id FROM source_units WHERE id = ?", (source_unit_id,)
            ).fetchone()[0]
            == source_unit_id
        )
        assert (
            migrated.execute("SELECT id FROM chunks WHERE id = ?", (chunk_id,)).fetchone()[0]
            == chunk_id
        )
        assert (
            migrated.execute(
                "SELECT id FROM embedding_generations WHERE id = ?", (generation_id,)
            ).fetchone()[0]
            == generation_id
        )
        assert migrated.execute("SELECT COUNT(*) FROM embedding_vectors").fetchone()[0] == 2
        assert (
            migrated.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()[0]
            == session_id
        )
        assert (
            migrated.execute(
                "SELECT id FROM provider_runs WHERE id = ?", (provider_run_id,)
            ).fetchone()[0]
            == provider_run_id
        )
        assert (
            migrated.execute("SELECT id FROM transcript_speaker_maps").fetchone()[0]
            == speaker_map_id
        )
        assert (
            migrated.execute(
                "SELECT id FROM knowledge_items WHERE id = ?", (knowledge_id,)
            ).fetchone()[0]
            == knowledge_id
        )
        assert (
            migrated.execute(
                "SELECT id FROM audience_observation_candidates WHERE id = ?", (candidate_id,)
            ).fetchone()[0]
            == candidate_id
        )
        assert (
            migrated.execute(
                "SELECT id FROM audience_observation_candidates WHERE id = ?",
                (stale_candidate_id,),
            ).fetchone()[0]
            == stale_candidate_id
        )
        assert (
            migrated.execute(
                "SELECT id FROM audience_observations WHERE id = ?", (stale_observation_id,)
            ).fetchone()[0]
            == stale_observation_id
        )
        first_tables = migrated.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'questions'"
        ).fetchone()[0]
        assert first_tables == 1
    finally:
        migrated.close()
    no_op = connect_project_database(project_path)
    no_op.close()
    with sqlite3.connect(project_path) as future:
        future.execute("PRAGMA user_version = 6")
        future.commit()
    try:
        connect_project_database(project_path)
    except Exception as error:
        assert getattr(error, "code", None) == "DATABASE_VERSION_UNSUPPORTED"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("future project schema was accepted")
    with sqlite3.connect(project_path) as unchanged:
        assert unchanged.execute("PRAGMA user_version").fetchone()[0] == 6


class InventedEvidenceProvider(DeterministicFakeReasoningProvider):
    def generate(self, request: Any) -> ReasoningResult:
        result = super().generate(request)
        if request.task_type in {"challenge_question", "challenge_follow_up"}:
            invalid = dict(result.output)
            invalid["evidence_ids"] = [str(uuid.uuid4())]
            return ReasoningResult(
                output=validate_provider_output(request.task_type, invalid),
                latency_ms=result.latency_ms,
            )
        return result


class InvalidEvaluationProvider(DeterministicFakeReasoningProvider):
    def generate(self, request: Any) -> ReasoningResult:
        result = super().generate(request)
        if request.task_type == "challenge_evaluation":
            invalid = dict(result.output)
            invalid["correctness"] = {"score": 1.5, "feedback": "invalid"}
            return ReasoningResult(output=invalid, latency_ms=result.latency_ms)
        return result


def test_challenge_rejects_provider_invented_evidence(tmp_path: Path) -> None:
    provider = InventedEvidenceProvider()
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        reasoning_provider=provider,
    )
    project_id = create_project(core)
    seed_project_evidence(core, project_id)
    profile_id = create_profile(core, project_id, "CFO", "CFO")
    call(core, "ack", "project.acknowledge_remote_reasoning", {"project_id": project_id})
    session_id = start_challenge(core, project_id)
    configure(core, project_id, session_id, [profile_id])
    response = error_call(
        core,
        "invented",
        "challenge.next_question",
        {"project_id": project_id, "session_id": session_id},
    )
    assert response["code"] == "CHALLENGE_OUTPUT_INVALID"
    with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
        assert connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0
    core.close()


def test_challenge_rejects_invalid_evaluation_without_persisting_answer(tmp_path: Path) -> None:
    provider = InvalidEvaluationProvider()
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        reasoning_provider=provider,
    )
    try:
        project_id = create_project(core)
        seed_project_evidence(core, project_id)
        profile_id = create_profile(core, project_id, "CFO", "CFO")
        create_observation(core, project_id, profile_id, "Cares about cost evidence.")
        call(core, "ack", "project.acknowledge_remote_reasoning", {"project_id": project_id})
        session_id = start_challenge(core, project_id)
        configure(core, project_id, session_id, [profile_id])
        question = call(
            core,
            "question",
            "challenge.next_question",
            {"project_id": project_id, "session_id": session_id},
        )["question"]
        error = error_call(
            core,
            "invalid-evaluation",
            "challenge.submit_answer",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question["id"],
                "text": "A bounded typed answer.",
            },
        )
        assert error["code"] == "CHALLENGE_OUTPUT_INVALID"
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            assert connection.execute("SELECT COUNT(*) FROM answer_versions").fetchone()[0] == 0
            run = connection.execute(
                "SELECT status, error_code FROM provider_runs "
                "WHERE task_type = 'challenge_evaluation'"
            ).fetchone()
            assert run is not None and run["status"] == "error"
            assert run["error_code"] == "CHALLENGE_OUTPUT_INVALID"
    finally:
        core.close()


def test_challenge_remote_context_excludes_private_knowledge(tmp_path: Path) -> None:
    provider = DeterministicFakeReasoningProvider(locality="remote")
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        reasoning_provider=provider,
    )
    try:
        project_id = create_project(core)
        seed_project_evidence(core, project_id)
        profile_id = create_profile(core, project_id, "CFO", "CFO")
        create_observation(core, project_id, profile_id, "Cares about cost evidence.")
        statement_id = str(uuid.uuid4())
        knowledge_id = str(uuid.uuid4())
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            connection.execute(
                "INSERT INTO user_statements "
                "(id, project_id, origin_session_id, source_utterance_id, text, created_at) "
                "VALUES (?, ?, NULL, NULL, ?, 'created')",
                (statement_id, project_id, "PRIVATE SECRET: do not send this knowledge."),
            )
            connection.execute(
                "INSERT INTO knowledge_items "
                "(id, project_id, kind, text, use_live, use_rehearsal, preferred, private, "
                "created_by, origin_session_id, created_at, updated_at) "
                "VALUES (?, ?, 'private_note', ?, 1, 1, 0, 1, 'user', NULL, 'created', 'updated')",
                (knowledge_id, project_id, "PRIVATE SECRET: do not send this knowledge."),
            )
            connection.execute(
                "INSERT INTO knowledge_evidence "
                "(knowledge_item_id, provenance_type, provenance_id) "
                "VALUES (?, 'user_statement', ?)",
                (knowledge_id, statement_id),
            )
            connection.commit()
        call(core, "ack", "project.acknowledge_remote_reasoning", {"project_id": project_id})
        session_id = start_challenge(core, project_id)
        configure(core, project_id, session_id, [profile_id])
        result = call(
            core,
            "remote-question",
            "challenge.next_question",
            {"project_id": project_id, "session_id": session_id},
        )
        payload = provider.requests[-1]
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "PRIVATE SECRET" not in serialized
        assert knowledge_id not in serialized
        assert result["context_manifest"]["private_items_sent"] is False
        assert knowledge_id not in result["context_manifest"]["knowledge_item_ids"]
        assert result["context_manifest"]["full_corpus_sent"] is False
    finally:
        core.close()


def test_e2e04_canonical_fixture_challenge_acceptance(tmp_path: Path) -> None:
    """Run the M5 exit flow against the repository's named synthetic fixture."""
    data_root = tmp_path / "data"
    provider = DeterministicFakeReasoningProvider()
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
    )
    restarted: CoreService | None = None
    try:
        project_id = create_project(core)
        for path, kind in (
            (FIXTURE_ROOT / "deck" / "presentation.pptx", "presentation"),
            (FIXTURE_ROOT / "supporting" / "cost-model.pdf", "supporting"),
            (FIXTURE_ROOT / "supporting" / "architecture-notes.md", "supporting"),
            (FIXTURE_ROOT / "transcript" / "PriorMeeting.vtt", "transcript"),
        ):
            imported = call(
                core,
                f"import-{path.name}",
                "source.import",
                {"project_id": project_id, "path": str(path.resolve()), "kind": kind},
            )
            assert imported["status"] == "ready"
        call(core, "build-index", "retrieval.rebuild", {"project_id": project_id})

        jane_id = create_profile(core, project_id, "Jane Smith", "CFO")
        robert_id = create_profile(core, project_id, "Robert Chen", "CTO")
        speakers = call(
            core,
            "list-canonical-speakers",
            "transcript.list_speakers",
            {"project_id": project_id},
        )["speakers"]
        transcript = next(item for item in speakers if item["native_speaker_label"] == "Jane Smith")
        transcript_document_id = transcript["document_id"]
        call(
            core,
            "map-jane",
            "transcript.map_speaker",
            {
                "project_id": project_id,
                "document_id": transcript_document_id,
                "native_speaker_label": "Jane Smith",
                "audience_profile_id": jane_id,
            },
        )
        call(
            core,
            "map-robert",
            "transcript.map_speaker",
            {
                "project_id": project_id,
                "document_id": transcript_document_id,
                "native_speaker_label": "Robert Chen",
                "audience_profile_id": robert_id,
            },
        )
        jane_observation = create_observation(
            core, project_id, jane_id, "Prioritizes cost comparison and downside risk."
        )
        robert_observation = create_observation(
            core, project_id, robert_id, "Prioritizes RTO, availability, and rollback safety."
        )
        assert jane_observation and robert_observation
        assert any(
            item["native_speaker_label"] == "Conference Room" and item["audience_profile"] is None
            for item in speakers
        )

        call(
            core,
            "ack-canonical",
            "project.acknowledge_remote_reasoning",
            {"project_id": project_id},
        )
        session_id = start_challenge(core, project_id)
        configure(core, project_id, session_id, [jane_id, robert_id])
        first = call(
            core,
            "canonical-question-jane",
            "challenge.next_question",
            {"project_id": project_id, "session_id": session_id},
        )
        question_a = first["question"]
        assert question_a["audience_profile_id"] == jane_id
        assert "cost" in question_a["text"].casefold()
        assert question_a["evidence"]
        assert jane_observation in {
            item["observation_id"] for item in question_a["audience_observations"]
        }
        assert first["context_manifest"]["full_corpus_sent"] is False
        captured = provider.requests[0]
        assert captured["challenge_intensity"] == "skeptical"
        assert "upload all project files" not in captured["application_policy"].casefold()
        assert all(
            key in captured
            for key in (
                "untrusted_retrieved_evidence",
                "approved_audience_context",
                "application_policy",
            )
        )

        weak = call(
            core,
            "canonical-weak",
            "challenge.submit_answer",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question_a["id"],
                "text": "It is a good proposal.",
            },
        )
        call(
            core,
            "canonical-retry",
            "challenge.retry_question",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question_a["id"],
            },
        )
        strong = call(
            core,
            "canonical-strong",
            "challenge.submit_answer",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question_a["id"],
                "text": (
                    "We compare annual cost and downside against the current platform, "
                    "while the proposal protects the recovery target and rollback plan."
                ),
            },
        )
        assert (
            strong["evaluation"]["correctness"]["score"]
            > weak["evaluation"]["correctness"]["score"]
        )
        saved = call(
            core,
            "canonical-save",
            "challenge.save_preferred_answer",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question_a["id"],
                "answer_version_id": strong["answer_version"]["id"],
            },
        )
        assert saved["knowledge_item"]["kind"] == "answer"

        second = call(
            core,
            "canonical-question-robert",
            "challenge.next_question",
            {"project_id": project_id, "session_id": session_id},
        )
        assert second["question"]["audience_profile_id"] == robert_id
        assert "migration" in second["question"]["text"].casefold()
        assert robert_observation in {
            item["observation_id"] for item in second["question"]["audience_observations"]
        }
        history = call(
            core,
            "canonical-history",
            "challenge.list_history",
            {"project_id": project_id, "session_id": session_id, "limit": 10},
        )
        assert history["total"] == 2
        assert len(history["items"][0]["answer_versions"]) == 2

        retrieval = call(
            core,
            "canonical-practice-retrieval",
            "retrieval.query",
            {
                "project_id": project_id,
                "query": "annual cost downside current platform",
                "usage": "rehearsal",
                "limit": 10,
            },
        )
        practice_hits = [
            hit
            for hit in retrieval["hits"]
            if hit["evidence"].get("knowledge_item_id") == saved["knowledge_item"]["id"]
        ]
        assert practice_hits
        assert practice_hits[0]["evidence"]["label"] == "Your practiced answer"

        core.close()
        restarted = CoreService(
            data_root=data_root,
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
            reasoning_provider=DeterministicFakeReasoningProvider(),
        )
        recovered = call(
            restarted,
            "canonical-recovered-state",
            "challenge.get_state",
            {"project_id": project_id, "session_id": session_id},
        )
        assert recovered["current_question"]["id"] == second["question"]["id"]
        recovered_history = call(
            restarted,
            "canonical-recovered-history",
            "challenge.list_history",
            {"project_id": project_id, "session_id": session_id, "limit": 10},
        )
        assert recovered_history["total"] == 2
        assert len(recovered_history["items"][0]["answer_versions"]) == 2
        assert restarted._providers.current_provider().call_count == 0  # type: ignore[attr-defined]
    finally:
        if restarted is not None:
            restarted.close()
        else:
            core.close()
