from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import ASR_FRAME_SAMPLES, DeterministicFakeAudioInput
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.adapters import ManualPresentationAdapter
from presenter_core.project.service import utc_now
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.providers.models import (
    ReasoningRequest,
    ReasoningResult,
    validate_provider_output,
)
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter

FIXTURE_ROOT = Path(__file__).parents[2] / "samples" / "synthetic-deck"


def request_message(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "type": "request",
        "request_id": str(uuid.uuid4()),
        "method": method,
        "params": params,
    }


def call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(request_message(method, params))
    assert response["ok"] is True, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def error_code(core: CoreService, method: str, params: dict[str, Any]) -> str:
    response = core.handle_message(request_message(method, params))
    assert response["ok"] is False, response
    error = response["error"]
    assert isinstance(error, dict)
    return str(error["code"])


def make_core(
    data_root: Path,
    events: list[tuple[str, dict[str, Any]]],
    *,
    provider: DeterministicFakeReasoningProvider | None = None,
    adapter: DeterministicFakeASRAdapter | None = None,
) -> tuple[CoreService, DeterministicFakeAudioInput, DeterministicFakeASRAdapter, threading.Event]:
    audio = DeterministicFakeAudioInput()
    asr_adapter = adapter or DeterministicFakeASRAdapter()
    final_seen = threading.Event()
    event_lock = threading.Lock()

    def on_event(envelope: dict[str, Any]) -> None:
        event = str(envelope["event"])
        payload = dict(envelope["payload"])
        with event_lock:
            events.append((event, payload))
        if event == "asr.final":
            final_seen.set()

    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=provider,
        audio_input=audio,
        asr_adapters={asr_adapter.id: asr_adapter},
        presentation_adapter=ManualPresentationAdapter(),
        event_sink=on_event,
    )
    return core, audio, asr_adapter, final_seen


def import_fixture(core: CoreService, project_id: str) -> None:
    for kind, path in (
        ("presentation", FIXTURE_ROOT / "deck" / "presentation.pptx"),
        ("supporting", FIXTURE_ROOT / "supporting" / "architecture-notes.md"),
        ("supporting", FIXTURE_ROOT / "supporting" / "cost-model.pdf"),
    ):
        call(core, "source.import", {"project_id": project_id, "kind": kind, "path": str(path)})
    call(core, "retrieval.rebuild", {"project_id": project_id})


def start_live(
    core: CoreService,
    *,
    privacy_mode: str = "local_only",
    seed_fixture: bool = False,
) -> tuple[str, str]:
    project_id = str(
        call(core, "project.create", {"name": "M7 Live fixture", "privacy_mode": privacy_mode})[
            "project"
        ]["id"]
    )
    if seed_fixture:
        import_fixture(core, project_id)
    session_id = str(
        call(
            core,
            "session.start",
            {"project_id": project_id, "mode": "live_assist", "current_slide_start": 8},
        )["session"]["id"]
    )
    return project_id, session_id


def feed_one_utterance(audio: DeterministicFakeAudioInput) -> None:
    loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
    quiet = np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)
    audio.feed_frames([loud] * 8 + [quiet] * 31)


def payloads(
    events: list[tuple[str, dict[str, Any]]], event_name: str, assist_id: str | None = None
) -> list[dict[str, Any]]:
    return [
        payload
        for event, payload in events
        if event == event_name and (assist_id is None or payload.get("assist_id") == assist_id)
    ]


def test_m7_e2e06_live_assist_persists_one_cue_and_bounded_provenance(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    adapter = DeterministicFakeASRAdapter(
        partial_texts=("what is the proposed", "what is the proposed three-year cost"),
        final_text="What is the proposed three-year cost reduction?",
    )
    core, audio, _, final_seen = make_core(tmp_path / "data", events, adapter=adapter)
    try:
        project_id, session_id = start_live(core, seed_fixture=True)
        call(core, "asr.start", {"project_id": project_id, "session_id": session_id})
        feed_one_utterance(audio)
        assert final_seen.wait(5.0)

        with core._storage.project_database(project_id) as connection:
            transcript_row = connection.execute(
                "SELECT actor, text FROM utterances WHERE session_id = ? AND is_final = 1",
                (session_id,),
            ).fetchone()
        assert transcript_row is not None
        assert transcript_row["actor"] == "unknown_audience"
        assert transcript_row["text"] == "What is the proposed three-year cost reduction?"
        assert core._asr.latest_partial(project_id, session_id) is None

        started = call(
            core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question": "$980,000",
                "trigger": "hotkey",
            },
        )
        assist_id = str(started["assist_id"])
        assert started["question_origin"] == "typed"
        assert core._assist.wait_for_idle(5.0)

        started_events = payloads(events, "assist.started", assist_id)
        retrieval_events = payloads(events, "assist.retrieval_ready", assist_id)
        partial_events = payloads(events, "cue.partial", assist_id)
        ready_events = payloads(events, "cue.ready", assist_id)
        assert len(started_events) == 1
        assert len(retrieval_events) == 1
        assert len(partial_events) == 1
        assert len(ready_events) == 1
        ready = ready_events[0]
        assert ready["state"] == "final"
        assert ready["route"] == "retrieval_only"
        assert len(ready["lines"]) <= 3
        assert "$980,000" in ready["text"]
        assert ready["evidence_ids"]
        assert ready["latency_ms"] >= 0

        partial = partial_events[0]
        assert partial["cue_id"] == ready["cue_id"]
        assert partial["state"] == "partial"

        cues = call(
            core,
            "cue.list",
            {"project_id": project_id, "session_id": session_id, "limit": 10},
        )
        assert cues["limit"] == 10
        assert cues["offset"] == 0
        assert cues["total"] == 1
        assert cues["has_more"] is False
        assert len(cues["cues"]) == 1
        assert cues["cues"]
        assert cues["cues"][0]["id"] == ready["cue_id"]
        assert cues["cues"][0]["assist_id"] == assist_id
        empty_page = call(
            core,
            "cue.list",
            {"project_id": project_id, "session_id": session_id, "limit": 10, "offset": 1},
        )
        assert empty_page["cues"] == []
        assert empty_page["total"] == 1
        assert empty_page["has_more"] is False

        expanded = call(
            core,
            "cue.expand_sources",
            {"project_id": project_id, "session_id": session_id, "cue_id": ready["cue_id"]},
        )
        assert 1 <= len(expanded["sources"]) <= 8
        assert expanded["sources"][0]["pointer"]["source_id"]
        assert expanded["sources"][0]["source_name"]

        source_id = expanded["sources"][0]["pointer"]["source_id"]
        if expanded["sources"][0]["pointer"]["source_type"] == "document":
            call(
                core,
                "source.delete",
                {"project_id": project_id, "document_id": source_id},
            )
            after_delete = call(
                core,
                "cue.expand_sources",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "cue_id": ready["cue_id"],
                },
            )
            assert any(source["available"] is False for source in after_delete["sources"])

        call(
            core,
            "cue.dismiss",
            {"project_id": project_id, "session_id": session_id, "cue_id": ready["cue_id"]},
        )
        assert (
            call(
                core,
                "cue.list",
                {"project_id": project_id, "session_id": session_id, "limit": 10},
            )["cues"]
            == []
        )
        assert (
            call(
                core,
                "cue.list",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "limit": 10,
                    "include_dismissed": True,
                },
            )["total"]
            == 1
        )

        stopped = call(
            core,
            "session.stop",
            {"project_id": project_id, "session_id": session_id, "status": "completed"},
        )
        assert stopped["session"]["status"] == "completed"
        assert core.close() is True

        restarted, _, _, _ = make_core(tmp_path / "data", [], adapter=DeterministicFakeASRAdapter())
        try:
            persisted = call(
                restarted,
                "cue.list",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "limit": 10,
                    "include_dismissed": True,
                },
            )
            assert persisted["total"] == 1
            assert len(persisted["cues"]) == 1
            assert persisted["cues"][0]["dismissed_at"] is not None
            call(restarted, "session.delete", {"project_id": project_id, "session_id": session_id})
            assert (
                error_code(
                    restarted,
                    "cue.list",
                    {"project_id": project_id, "session_id": session_id, "limit": 10},
                )
                == "CUE_SESSION_INVALID"
            )
            assert call(restarted, "project.delete", {"project_id": project_id})["deleted"] is True
        finally:
            restarted.close()
    finally:
        core.close()


def test_m7_live_context_bounds_and_empty_push_does_not_segment_automatically(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    core, _, _, _ = make_core(tmp_path / "data", events)
    try:
        project_id, session_id = start_live(core)
        assert (
            error_code(
                core,
                "assist.request",
                {"project_id": project_id, "session_id": session_id, "trigger": "hotkey"},
            )
            == "ASSIST_CONTEXT_INSUFFICIENT"
        )

        with core._storage.project_database(project_id) as connection:
            for index in range(7):
                utterance_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO utterances (
                        id, session_id, actor, text, created_at, start_ms, end_ms,
                        asr_confidence, slide_ordinal, is_final
                    ) VALUES (?, ?, 'unknown_audience', ?, ?, ?, ?, NULL, 8, 1)
                    """,
                    (
                        utterance_id,
                        session_id,
                        f"bounded audience question {index}",
                        utc_now(),
                        20_000 + index * 500,
                        20_400 + index * 500,
                    ),
                )
            connection.execute(
                """
                INSERT INTO utterances (
                    id, session_id, actor, text, created_at, start_ms, end_ms,
                    asr_confidence, slide_ordinal, is_final
                ) VALUES (
                    ?, ?, 'unknown_audience', 'old context must be excluded', ?,
                    0, 100, NULL, 8, 1
                )
                """,
                (str(uuid.uuid4()), session_id, utc_now()),
            )
            connection.commit()

        recent = core._assist._recent_utterances(project_id, session_id)
        assert len(recent) == 6
        assert all("old context" not in str(item["text"]) for item in recent)
        question, origin = core._assist._assemble_live_question(project_id, session_id)
        assert origin == "live_final"
        assert question is not None
        assert len(question) <= 1_200
        assert "bounded audience question 6" in question
    finally:
        core.close()


def test_m7_provider_failure_and_unsupported_fact_are_degraded_without_fabrication(
    tmp_path: Path,
) -> None:
    for suffix, provider in (
        (
            "failure",
            DeterministicFakeReasoningProvider(locality="local", failure_code="PROVIDER_TIMEOUT"),
        ),
        ("unsupported", UnsupportedFactProvider(locality="local")),
        ("invented-evidence", InventedEvidenceProvider(locality="local")),
        ("malformed", MalformedProvider(locality="local")),
    ):
        events: list[tuple[str, dict[str, Any]]] = []
        core, _, _, _ = make_core(tmp_path / suffix, events, provider=provider)
        try:
            project_id, session_id = start_live(core)
            call(
                core,
                "source.import",
                {
                    "project_id": project_id,
                    "kind": "supporting",
                    "path": str(FIXTURE_ROOT / "supporting" / "architecture-notes.md"),
                },
            )
            call(core, "retrieval.rebuild", {"project_id": project_id})
            started = call(
                core,
                "assist.request",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "question": "Explain the warm standby ownership boundary.",
                    "trigger": "button",
                },
            )
            assist_id = str(started["assist_id"])
            assert core._assist.wait_for_idle(5.0)
            errors = payloads(events, "cue.error", assist_id)
            ready = payloads(events, "cue.ready", assist_id)
            assert errors
            assert ready
            assert ready[-1]["route"] == "retrieval_only"
            assert ready[-1]["degraded"] is True
            assert len(ready[-1]["lines"]) <= 3
            if suffix == "unsupported":
                assert "987,654,321" not in ready[-1]["text"]
                assert errors[-1]["code"] == "ASSIST_PROVIDER_FAILED"
            else:
                assert provider.call_count == 1
                assert errors[-1]["code"] == "ASSIST_PROVIDER_FAILED"
        finally:
            core.close()


def test_m7_preferred_live_wording_uses_retrieval_fast_path(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    provider = DeterministicFakeReasoningProvider(locality="local")
    core, _, _, _ = make_core(tmp_path / "data", events, provider=provider)
    try:
        project_id, session_id = start_live(core, privacy_mode="selected_context_cloud")
        statement_id = str(uuid.uuid4())
        knowledge_id = str(uuid.uuid4())
        wording = "We keep the warm standby because it gives the team a tested recovery path."
        with core._storage.project_database(project_id) as connection:
            connection.execute(
                "INSERT INTO user_statements "
                "(id, project_id, origin_session_id, source_utterance_id, text, created_at) "
                "VALUES (?, ?, NULL, NULL, ?, ?)",
                (statement_id, project_id, wording, utc_now()),
            )
            connection.execute(
                "INSERT INTO knowledge_items "
                "(id, project_id, kind, text, use_live, use_rehearsal, preferred, private, "
                "created_by, origin_session_id, created_at, updated_at) "
                "VALUES (?, ?, 'preferred_explanation', ?, 1, 1, 1, 0, 'user', NULL, ?, ?)",
                (knowledge_id, project_id, wording, utc_now(), utc_now()),
            )
            connection.execute(
                "INSERT INTO knowledge_evidence "
                "(knowledge_item_id, provenance_type, provenance_id) "
                "VALUES (?, 'user_statement', ?)",
                (knowledge_id, statement_id),
            )
            connection.commit()
        call(core, "retrieval.rebuild", {"project_id": project_id})
        started = call(
            core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question": "Explain the tested recovery path.",
                "trigger": "button",
            },
        )
        assert core._assist.wait_for_idle(5.0)
        ready = payloads(events, "cue.ready", str(started["assist_id"]))
        assert ready
        assert ready[-1]["route"] == "retrieval_only"
        assert wording in ready[-1]["text"]
        assert ready[-1]["text"].endswith("Source: Your Teach explanation")
        assert provider.call_count == 0
    finally:
        core.close()


def test_m7_reindex_does_not_transfer_historical_cue_evidence(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    core, _, _, _ = make_core(tmp_path / "data", events)
    try:
        project_id, session_id = start_live(core, seed_fixture=True)
        started = call(
            core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question": "$980,000",
                "trigger": "button",
            },
        )
        assert core._assist.wait_for_idle(5.0)
        ready = payloads(events, "cue.ready", str(started["assist_id"]))[-1]
        expanded = call(
            core,
            "cue.expand_sources",
            {
                "project_id": project_id,
                "session_id": session_id,
                "cue_id": ready["cue_id"],
            },
        )
        source = next(
            source
            for source in expanded["sources"]
            if source["pointer"]["source_type"] == "document"
            and source["pointer"]["source_unit_id"]
        )
        call(
            core,
            "source.reindex",
            {"project_id": project_id, "document_id": source["pointer"]["source_id"]},
        )
        after_reindex = call(
            core,
            "cue.expand_sources",
            {
                "project_id": project_id,
                "session_id": session_id,
                "cue_id": ready["cue_id"],
            },
        )
        historical = next(
            item
            for item in after_reindex["sources"]
            if item["evidence_id"] == source["evidence_id"]
        )
        assert historical["available"] is False
        assert historical["excerpt"] is None
    finally:
        core.close()


def test_m7_assist_supersession_suppresses_stale_cue_ready(
    tmp_path: Path,
) -> None:
    provider = BlockingProvider(locality="local")
    events: list[tuple[str, dict[str, Any]]] = []
    core, _, _, _ = make_core(tmp_path / "data", events, provider=provider)
    try:
        project_id, session_id = start_live(core)
        call(
            core,
            "source.import",
            {
                "project_id": project_id,
                "kind": "supporting",
                "path": str(FIXTURE_ROOT / "supporting" / "architecture-notes.md"),
            },
        )
        call(core, "retrieval.rebuild", {"project_id": project_id})
        first = call(
            core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question": "Explain the warm standby ownership boundary.",
            },
        )
        assert provider.first_call.wait(5.0)
        second = call(
            core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question": "Explain the tested recovery workflow.",
            },
        )
        assert provider.second_call.wait(5.0)
        provider.release.set()
        assert core._assist.wait_for_idle(5.0)
        ready = payloads(events, "cue.ready")
        assert ready
        assert all(item["assist_id"] == second["assist_id"] for item in ready)
        assert all(item["assist_id"] != first["assist_id"] for item in ready)
    finally:
        provider.release.set()
        core.close()


def test_m7_local_only_skips_remote_provider_and_remote_context_excludes_private_knowledge(
    tmp_path: Path,
) -> None:
    local_events: list[tuple[str, dict[str, Any]]] = []
    local_provider = DeterministicFakeReasoningProvider(locality="remote")
    local_core, _, _, _ = make_core(tmp_path / "local", local_events, provider=local_provider)
    try:
        project_id, session_id = start_live(local_core, seed_fixture=True)
        started = call(
            local_core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question": "Explain the warm standby ownership boundary.",
            },
        )
        assert local_core._assist.wait_for_idle(5.0)
        assert local_provider.call_count == 0
        assert payloads(local_events, "cue.ready", str(started["assist_id"]))[-1]["route"] == (
            "retrieval_only"
        )
    finally:
        local_core.close()

    remote_events: list[tuple[str, dict[str, Any]]] = []
    remote_provider = DeterministicFakeReasoningProvider(locality="remote")
    remote_core, _, _, _ = make_core(tmp_path / "remote", remote_events, provider=remote_provider)
    try:
        project_id, session_id = start_live(remote_core, privacy_mode="selected_context_cloud")
        seed_private_knowledge(remote_core, project_id)
        call(remote_core, "retrieval.rebuild", {"project_id": project_id})
        call(remote_core, "project.acknowledge_remote_reasoning", {"project_id": project_id})
        started = call(
            remote_core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question": "What is the private launch phrase?",
            },
        )
        assert remote_core._assist.wait_for_idle(5.0)
        assert remote_provider.call_count == 1
        assert remote_provider.requests
        request_payload = remote_provider.requests[0]
        assert request_payload["approved_user_knowledge"] == []
        assert all(
            item.get("private") is not True
            for item in request_payload["untrusted_retrieved_evidence"]
        )
        assert payloads(remote_events, "cue.ready", str(started["assist_id"]))
    finally:
        remote_core.close()


class UnsupportedFactProvider(DeterministicFakeReasoningProvider):
    def generate(self, request: ReasoningRequest) -> ReasoningResult:
        self.call_count += 1
        self.requests.append(request.to_payload())
        self.request_objects.append(request)
        grounding = request.grounding_evidence or request.evidence
        evidence_ids = [
            str(grounding[0]["evidence_id"])
            if grounding and isinstance(grounding[0].get("evidence_id"), str)
            else ""
        ]
        output = validate_provider_output(
            "live_cue",
            {
                "cue_type": "fact",
                "lines": ["The answer is $987,654,321."],
                "evidence_ids": [item for item in evidence_ids if item],
            },
        )
        return ReasoningResult(output=output)


class InventedEvidenceProvider(DeterministicFakeReasoningProvider):
    def generate(self, request: ReasoningRequest) -> ReasoningResult:
        self.call_count += 1
        self.requests.append(request.to_payload())
        self.request_objects.append(request)
        return ReasoningResult(
            output={
                "cue_type": "fact",
                "lines": ["This cited item was not supplied by retrieval."],
                "evidence_ids": ["invented-evidence-id"],
            }
        )


class MalformedProvider(DeterministicFakeReasoningProvider):
    def generate(self, request: ReasoningRequest) -> ReasoningResult:
        self.call_count += 1
        self.requests.append(request.to_payload())
        self.request_objects.append(request)
        return ReasoningResult(
            output={
                "cue_type": "fact",
                "lines": ["The provider omitted its evidence binding."],
            }
        )


class BlockingProvider(DeterministicFakeReasoningProvider):
    def __init__(self, *, locality: str) -> None:
        super().__init__(locality=locality)
        self.first_call = threading.Event()
        self.second_call = threading.Event()
        self.release = threading.Event()
        self._calls_lock = threading.Lock()

    def generate(self, request: ReasoningRequest) -> ReasoningResult:
        with self._calls_lock:
            self.call_count += 1
            call_number = self.call_count
        self.requests.append(request.to_payload())
        self.request_objects.append(request)
        if call_number == 1:
            self.first_call.set()
        else:
            self.second_call.set()
        self.release.wait(5.0)
        grounding = request.grounding_evidence or request.evidence
        evidence_ids = [
            str(item["evidence_id"])
            for item in grounding[:1]
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
        ]
        return ReasoningResult(
            output=validate_provider_output(
                "live_cue",
                {
                    "cue_type": "reminder",
                    "lines": ["Explain the ownership boundary."],
                    "evidence_ids": evidence_ids,
                },
            )
        )


def seed_private_knowledge(core: CoreService, project_id: str) -> None:
    statement_id = str(uuid.uuid4())
    knowledge_id = str(uuid.uuid4())
    text = "The private launch phrase is blue lantern."
    with core._storage.project_database(project_id) as connection:
        connection.execute(
            """
            INSERT INTO user_statements (
                id, project_id, origin_session_id, source_utterance_id, text, created_at
            ) VALUES (?, ?, NULL, NULL, ?, ?)
            """,
            (statement_id, project_id, text, utc_now()),
        )
        connection.execute(
            """
            INSERT INTO knowledge_items (
                id, project_id, kind, text, use_live, use_rehearsal, preferred,
                private, created_by, origin_session_id, created_at, updated_at
            ) VALUES (?, ?, 'private_note', ?, 1, 1, 1, 1, 'user', NULL, ?, ?)
            """,
            (knowledge_id, project_id, text, utc_now(), utc_now()),
        )
        connection.execute(
            """
            INSERT INTO knowledge_evidence (knowledge_item_id, provenance_type, provenance_id)
            VALUES (?, 'user_statement', ?)
            """,
            (knowledge_id, statement_id),
        )
        connection.commit()


def test_m7_malformed_hud_metadata_uses_safe_defaults(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    core, _, _, _ = make_core(tmp_path / "data", events)
    try:
        with core._storage.app_database() as connection:
            connection.execute(
                "INSERT INTO app_metadata(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("hud.settings.v1", "not-json"),
            )
            connection.commit()
        settings = call(core, "hud.settings.get", {})["settings"]
        assert settings["display_id"] is None
        assert settings["width"] == 560
        assert settings["font_size"] == 24
        assert settings["top_offset"] == 32
        assert settings["shortcuts"]["push_to_assist"] == "Ctrl+Alt+Space"
    finally:
        core.close()
