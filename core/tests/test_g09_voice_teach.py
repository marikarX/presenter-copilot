from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import ASR_FRAME_SAMPLES, DeterministicFakeAudioInput
from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


class FailingFinalASRAdapter(DeterministicFakeASRAdapter):
    """Fixture adapter that fails only at final decode."""

    def transcribe_final(self, _audio: Any, *, language: str) -> Any:
        del language
        raise CoreDomainError(
            "ASR_TRANSCRIBE_FAILED", "The fixture final decode failed.", retryable=True
        )


def call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is True, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def error_code(core: CoreService, method: str, params: dict[str, Any]) -> str:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is False, response
    error = response["error"]
    assert isinstance(error, dict)
    return str(error["code"])


def wait_until(predicate: Any, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def make_core(
    data_root: Path,
    *,
    audio: DeterministicFakeAudioInput,
    adapter: DeterministicFakeASRAdapter,
    provider: DeterministicFakeReasoningProvider | None = None,
    events: list[dict[str, Any]] | None = None,
) -> CoreService:
    return CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=audio,
        asr_adapters={adapter.id: adapter},
        reasoning_provider=provider,
        event_sink=(events.append if events is not None else None),
    )


def start_prompt(core: CoreService, project_id: str) -> str:
    session = call(core, "session.start", {"project_id": project_id, "mode": "teach"})["session"]
    session_id = str(session["id"])
    prompt = call(
        core,
        "teach.next_prompt",
        {"project_id": project_id, "session_id": session_id},
    )
    assert prompt["state"] == "awaiting_user"
    return session_id


def feed_answer(audio: DeterministicFakeAudioInput) -> None:
    loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
    quiet = np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)
    audio.feed_frames([loud] * 12 + [quiet] * 35)


def finalize_voice_answer(
    core: CoreService,
    audio: DeterministicFakeAudioInput,
    project_name: str,
) -> tuple[str, str]:
    project_id = str(call(core, "project.create", {"name": project_name})["project"]["id"])
    session_id = start_prompt(core, project_id)
    call(core, "teach.voice_start", {"project_id": project_id, "session_id": session_id})
    feed_answer(audio)
    stopped = call(
        core,
        "teach.voice_stop",
        {"project_id": project_id, "session_id": session_id},
    )
    assert isinstance(stopped.get("submission"), dict)
    return project_id, session_id


def assert_compact_voice_submission_cache(core: CoreService) -> None:
    teach = core._teach  # type: ignore[attr-defined]
    with teach._voice_submission_guard:
        assert teach._voice_submissions
        assert all(not isinstance(value, dict) for value in teach._voice_submissions.values())
        assert teach._last_voice_submission
        assert all(not isinstance(value, dict) for value in teach._last_voice_submission.values())


def assert_voice_submission_cache_empty(core: CoreService) -> None:
    teach = core._teach  # type: ignore[attr-defined]
    with teach._voice_submission_guard:
        assert teach._voice_submissions == {}
        assert teach._last_voice_submission == {}


def user_utterances(core: CoreService, project_id: str, session_id: str) -> list[sqlite3.Row]:
    with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
        return connection.execute(
            "SELECT * FROM utterances WHERE session_id = ? AND actor = 'user' "
            "ORDER BY created_at, id",
            (session_id,),
        ).fetchall()


def test_g09_voice_final_uses_typed_teach_pipeline_and_acceptance_flow(tmp_path: Path) -> None:
    events: list[dict[str, Any]] = []
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(
        partial_texts=("unstable partial", "unstable partial revised"),
        final_text="The rollout stays local because customer data cannot leave the device.",
    )
    provider = DeterministicFakeReasoningProvider(locality="local")
    core = make_core(
        tmp_path / "data",
        audio=audio,
        adapter=adapter,
        provider=provider,
        events=events,
    )
    try:
        project_id = str(call(core, "project.create", {"name": "G09 acceptance"})["project"]["id"])
        session_id = start_prompt(core, project_id)

        assert (
            error_code(
                core,
                "teach.voice_start",
                {"project_id": project_id, "session_id": str(uuid.uuid4())},
            )
            == "SESSION_NOT_FOUND"
        )
        started = call(
            core,
            "teach.voice_start",
            {"project_id": project_id, "session_id": session_id},
        )
        assert started["state"] == "awaiting_user"
        assert started["capture_state"] == "running"
        assert started["asr_status"]["session_mode"] == "teach"
        assert audio.started is True
        assert core._asr.active_owner() == (project_id, session_id)  # type: ignore[attr-defined]

        assert (
            error_code(
                core,
                "teach.submit_text",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "text": "typed race",
                },
            )
            == "TEACH_VOICE_CAPTURE_ACTIVE"
        )

        loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
        quiet = np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)
        audio.feed_frames([loud] * 30)
        assert wait_until(lambda: any(item.get("event") == "asr.partial" for item in events))
        audio.feed_frames([quiet] * 35)
        stopped = call(
            core,
            "teach.voice_stop",
            {"project_id": project_id, "session_id": session_id},
        )
        submission = stopped["submission"]
        assert isinstance(submission, dict)
        assert submission["candidate"] is not None
        assert submission["state"] == "candidate_ready"
        assert audio.started is False
        assert adapter.close_count >= 1

        partials = [item["payload"] for item in events if item.get("event") == "asr.partial"]
        assert partials
        assert all(payload["is_final"] is False for payload in partials)
        assert not any(item.get("event") == "asr.final" for item in events)
        finalized_events = [item for item in events if item.get("event") == "teach.voice_finalized"]
        assert len(finalized_events) == 1
        assert "text" not in finalized_events[0]["payload"]
        assert len(user_utterances(core, project_id, session_id)) == 1
        source_id = str(submission["source_utterance_id"])
        assert str(user_utterances(core, project_id, session_id)[0]["id"]) == source_id
        candidate = submission["candidate"]
        assert candidate["source_utterance_id"] == source_id

        duplicate = call(
            core,
            "teach.voice_stop",
            {"project_id": project_id, "session_id": session_id},
        )
        assert duplicate["idempotent"] is True
        assert duplicate["submission"]["source_utterance_id"] == source_id
        assert len(user_utterances(core, project_id, session_id)) == 1
        assert (
            error_code(
                core,
                "teach.voice_cancel",
                {"project_id": project_id, "session_id": session_id},
            )
            == "TEACH_VOICE_SUBMISSION_ALREADY_FINALIZED"
        )
        assert provider.call_count == 2  # prompt + candidate; partials added no call
        assert "unstable partial" not in str(provider.requests[-1])
        assert "The rollout stays local" in str(provider.requests[-1])

        call(
            core,
            "teach.confirm_knowledge_item",
            {
                "project_id": project_id,
                "session_id": session_id,
                "candidate_id": candidate["id"],
                "source_utterance_id": source_id,
                "text": candidate["proposed_text"],
                "kind": candidate["proposed_kind"],
                "use_live": True,
                "use_rehearsal": True,
                "preferred": True,
                "private": False,
            },
        )
        knowledge = call(core, "knowledge.list", {"project_id": project_id})["knowledge_items"]
        assert any("rollout stays local" in str(item["text"]) for item in knowledge)
        retrieved = call(
            core,
            "retrieval.query",
            {
                "project_id": project_id,
                "query": "rollout local customer data device",
                "limit": 5,
                "usage": "rehearsal",
            },
        )
        assert any(
            "rollout stays local" in str(hit["evidence"]["text"]) for hit in retrieved["hits"]
        )
        next_question = call(
            core,
            "teach.next_prompt",
            {"project_id": project_id, "session_id": session_id},
        )
        assert next_question["state"] == "awaiting_user"
    finally:
        core.close()


def test_g09_cancel_keeps_awaiting_user_and_typed_fallback_works(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(final_text="discarded voice")
    provider = DeterministicFakeReasoningProvider(locality="local")
    core = make_core(
        tmp_path / "data",
        audio=audio,
        adapter=adapter,
        provider=provider,
    )
    try:
        project_id = str(call(core, "project.create", {"name": "G09 cancel"})["project"]["id"])
        session_id = start_prompt(core, project_id)
        call(core, "teach.voice_start", {"project_id": project_id, "session_id": session_id})
        feed_answer(audio)
        cancelled = call(
            core,
            "teach.voice_cancel",
            {"project_id": project_id, "session_id": session_id},
        )
        assert cancelled["cancelled"] is True
        assert cancelled["state"] == "awaiting_user"
        assert audio.started is False
        assert user_utterances(core, project_id, session_id) == []
        assert provider.call_count == 1  # only the Teach prompt

        typed = call(
            core,
            "teach.submit_text",
            {
                "project_id": project_id,
                "session_id": session_id,
                "text": "The typed fallback remains available.",
            },
        )
        assert typed["state"] == "candidate_ready"
        assert len(user_utterances(core, project_id, session_id)) == 1
        assert (
            user_utterances(core, project_id, session_id)[0]["text"]
            == typed["candidate"]["proposed_text"]
        )
    finally:
        core.close()


def test_g09_model_and_device_failures_leave_typed_teach_available(tmp_path: Path) -> None:
    model_audio = DeterministicFakeAudioInput()
    model_adapter = DeterministicFakeASRAdapter(model_installed=False)
    model_core = make_core(
        tmp_path / "model-data",
        audio=model_audio,
        adapter=model_adapter,
    )
    try:
        model_project_id = str(
            call(model_core, "project.create", {"name": "G09 missing model"})["project"]["id"]
        )
        model_session_id = start_prompt(model_core, model_project_id)
        assert (
            error_code(
                model_core,
                "teach.voice_start",
                {"project_id": model_project_id, "session_id": model_session_id},
            )
            == "ASR_MODEL_UNAVAILABLE"
        )
        assert model_adapter.load_count == 0
        assert model_audio.started is False
        assert (
            call(
                model_core,
                "teach.get_state",
                {"project_id": model_project_id, "session_id": model_session_id},
            )["state"]
            == "awaiting_user"
        )
    finally:
        model_core.close()

    device_audio = DeterministicFakeAudioInput()
    device_adapter = DeterministicFakeASRAdapter()
    device_core = make_core(
        tmp_path / "device-data",
        audio=device_audio,
        adapter=device_adapter,
    )
    try:
        device_project_id = str(
            call(device_core, "project.create", {"name": "G09 missing device"})["project"]["id"]
        )
        device_session_id = start_prompt(device_core, device_project_id)
        call(device_core, "asr.configure", {"device_id": "missing-device"})
        assert (
            error_code(
                device_core,
                "teach.voice_start",
                {"project_id": device_project_id, "session_id": device_session_id},
            )
            == "ASR_DEVICE_UNAVAILABLE"
        )
        assert device_adapter.load_count == 0
        assert device_audio.started is False
    finally:
        device_core.close()


def test_g09_final_decode_failure_does_not_advance_teach(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = FailingFinalASRAdapter()
    core = make_core(tmp_path / "data", audio=audio, adapter=adapter)
    try:
        project_id = str(
            call(core, "project.create", {"name": "G09 decode failure"})["project"]["id"]
        )
        session_id = start_prompt(core, project_id)
        call(core, "teach.voice_start", {"project_id": project_id, "session_id": session_id})
        feed_answer(audio)
        assert (
            error_code(
                core,
                "teach.voice_stop",
                {"project_id": project_id, "session_id": session_id},
            )
            == "ASR_TRANSCRIBE_FAILED"
        )
        assert (
            call(
                core,
                "teach.get_state",
                {"project_id": project_id, "session_id": session_id},
            )["state"]
            == "awaiting_user"
        )
        assert user_utterances(core, project_id, session_id) == []
        assert adapter.close_count >= 1
        assert audio.started is False
    finally:
        core.close()


def test_g09_state_change_releases_capture_without_voice_submission(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(final_text="must be discarded after state change")
    core = make_core(tmp_path / "data", audio=audio, adapter=adapter)
    try:
        project_id = str(call(core, "project.create", {"name": "G09 state race"})["project"]["id"])
        session_id = start_prompt(core, project_id)
        call(core, "teach.voice_start", {"project_id": project_id, "session_id": session_id})
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            connection.execute(
                "UPDATE sessions SET teach_state = 'ready_for_prompt' WHERE id = ?",
                (session_id,),
            )
            connection.commit()
        assert (
            error_code(
                core,
                "teach.voice_stop",
                {"project_id": project_id, "session_id": session_id},
            )
            == "TEACH_STATE_CHANGED_DURING_CAPTURE"
        )
        assert core._asr.active_owner() is None  # type: ignore[attr-defined]
        assert user_utterances(core, project_id, session_id) == []
    finally:
        core.close()


def test_g09_empty_final_is_retryable_and_creates_no_answer(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(final_text="   \t")
    core = make_core(tmp_path / "data", audio=audio, adapter=adapter)
    try:
        project_id = str(call(core, "project.create", {"name": "G09 empty"})["project"]["id"])
        session_id = start_prompt(core, project_id)
        call(core, "teach.voice_start", {"project_id": project_id, "session_id": session_id})
        feed_answer(audio)
        assert (
            error_code(
                core,
                "teach.voice_stop",
                {"project_id": project_id, "session_id": session_id},
            )
            == "TEACH_VOICE_EMPTY_TRANSCRIPT"
        )
        assert (
            call(
                core,
                "teach.get_state",
                {"project_id": project_id, "session_id": session_id},
            )["state"]
            == "awaiting_user"
        )
        assert user_utterances(core, project_id, session_id) == []
    finally:
        core.close()


def test_g09_local_only_voice_never_calls_provider_and_model_is_explicit(tmp_path: Path) -> None:
    events: list[dict[str, Any]] = []
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(final_text="keep this answer local")
    provider = DeterministicFakeReasoningProvider(locality="local")
    core = make_core(
        tmp_path / "data",
        audio=audio,
        adapter=adapter,
        provider=provider,
        events=events,
    )
    try:
        project_id = str(
            call(
                core,
                "project.create",
                {"name": "G09 local", "privacy_mode": "selected_context_cloud"},
            )["project"]["id"]
        )
        session_id = start_prompt(core, project_id)
        prompt_calls = provider.call_count
        call(
            core,
            "teach.voice_start",
            {"project_id": project_id, "session_id": session_id, "local_only": True},
        )
        feed_answer(audio)
        stopped = call(
            core,
            "teach.voice_stop",
            {"project_id": project_id, "session_id": session_id},
        )
        assert stopped["submission"]["local_only"] is True
        assert stopped["submission"]["route"] == "retrieval_only"
        assert stopped["submission"]["candidate"] is None
        assert provider.call_count == prompt_calls
        assert all("audio" not in str(item) for item in provider.requests)
        assert all("partial" not in str(item) for item in provider.requests)
        assert any(item.get("event") == "teach.voice_finalized" for item in events)
    finally:
        core.close()


def test_g09_session_delete_purges_successful_voice_submission_state(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(final_text="session deletion answer")
    provider = DeterministicFakeReasoningProvider(locality="local")
    core = make_core(tmp_path / "data", audio=audio, adapter=adapter, provider=provider)
    try:
        project_id, session_id = finalize_voice_answer(core, audio, "G09 session purge")
        assert_compact_voice_submission_cache(core)

        deleted = call(
            core,
            "session.delete",
            {"project_id": project_id, "session_id": session_id},
        )
        assert deleted["deleted"] is True
        assert_voice_submission_cache_empty(core)
    finally:
        core.close()


def test_g09_project_delete_purges_successful_voice_submission_state(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(final_text="project deletion answer")
    provider = DeterministicFakeReasoningProvider(locality="local")
    core = make_core(tmp_path / "data", audio=audio, adapter=adapter, provider=provider)
    try:
        project_id, _session_id = finalize_voice_answer(core, audio, "G09 project purge")
        assert_compact_voice_submission_cache(core)

        deleted = call(core, "project.delete", {"project_id": project_id})
        assert deleted["deleted"] is True
        assert_voice_submission_cache_empty(core)
    finally:
        core.close()


def test_g09_reset_local_data_purges_successful_voice_submission_state(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(final_text="reset deletion answer")
    provider = DeterministicFakeReasoningProvider(locality="local")
    core = make_core(tmp_path / "data", audio=audio, adapter=adapter, provider=provider)
    try:
        finalize_voice_answer(core, audio, "G09 reset purge")
        assert_compact_voice_submission_cache(core)

        reset = call(core, "app.reset_local_data", {"confirm": True})
        assert reset["reset"] is True
        assert_voice_submission_cache_empty(core)
    finally:
        core.close()


def test_g09_wrong_state_and_asr_owner_conflicts_fail_closed(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter()
    core = make_core(tmp_path / "data", audio=audio, adapter=adapter)
    try:
        project_id = str(call(core, "project.create", {"name": "G09 states"})["project"]["id"])
        session = call(core, "session.start", {"project_id": project_id, "mode": "teach"})[
            "session"
        ]
        session_id = str(session["id"])
        assert (
            error_code(
                core,
                "teach.voice_start",
                {"project_id": project_id, "session_id": session_id},
            )
            == "TEACH_STATE_INVALID"
        )
        call(
            core,
            "teach.next_prompt",
            {"project_id": project_id, "session_id": session_id},
        )
        run_session = call(core, "session.start", {"project_id": project_id, "mode": "run"})[
            "session"
        ]
        call(core, "asr.start", {"project_id": project_id, "session_id": run_session["id"]})
        assert (
            error_code(
                core,
                "teach.voice_start",
                {"project_id": project_id, "session_id": session_id},
            )
            == "ASR_ALREADY_RUNNING"
        )
        call(core, "asr.stop", {"project_id": project_id, "session_id": run_session["id"]})
        assert (
            error_code(
                core,
                "asr.start",
                {"project_id": project_id, "session_id": session_id},
            )
            == "ASR_SESSION_INVALID"
        )
    finally:
        core.close()


def test_g09_shutdown_cancels_transient_teach_capture_without_durability(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(final_text="must not survive shutdown")
    core = make_core(tmp_path / "data", audio=audio, adapter=adapter)
    project_id = str(call(core, "project.create", {"name": "G09 shutdown"})["project"]["id"])
    session_id = start_prompt(core, project_id)
    call(core, "teach.voice_start", {"project_id": project_id, "session_id": session_id})
    feed_answer(audio)
    assert core.close() is True
    assert audio.started is False
    restarted = make_core(
        tmp_path / "data",
        audio=DeterministicFakeAudioInput(),
        adapter=DeterministicFakeASRAdapter(),
    )
    try:
        assert user_utterances(restarted, project_id, session_id) == []
    finally:
        restarted.close()
