from __future__ import annotations

import threading
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import ASR_FRAME_SAMPLES, DeterministicFakeAudioInput
from presenter_core.asr.interfaces import ASRTranscription
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.adapters import ManualPresentationAdapter
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def request(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "type": "request",
        "request_id": str(uuid.uuid4()),
        "method": method,
        "params": params,
    }


def call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(request(method, params))
    assert response["ok"] is True, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def error_code(core: CoreService, method: str, params: dict[str, Any]) -> str:
    response = core.handle_message(request(method, params))
    assert response["ok"] is False, response
    error = response["error"]
    assert isinstance(error, dict)
    return str(error["code"])


class BlockingFinalAdapter(DeterministicFakeASRAdapter):
    def __init__(self) -> None:
        super().__init__(final_text="The recovery time objective is 30 minutes.")
        self.final_entered = threading.Event()
        self.release_final = threading.Event()

    def transcribe_final(self, audio: Any, *, language: str) -> ASRTranscription:
        self.final_entered.set()
        self.release_final.wait(5.0)
        return super().transcribe_final(audio, language=language)


class SlowPartialAdapter(DeterministicFakeASRAdapter):
    def __init__(self) -> None:
        super().__init__(partial_texts=("a coalesced partial",))
        self.partial_entered = threading.Event()
        self.release_partial = threading.Event()
        self.partial_calls = 0
        self.partial_lock = threading.Lock()

    def transcribe_partial(self, audio: Any, *, language: str) -> ASRTranscription:
        with self.partial_lock:
            self.partial_calls += 1
        self.partial_entered.set()
        self.release_partial.wait(5.0)
        return super().transcribe_partial(audio, language=language)


class FailingStopAudioInput(DeterministicFakeAudioInput):
    def __init__(self) -> None:
        super().__init__()
        self.fail_stop = True

    def stop(self) -> None:
        if self.fail_stop:
            self.fail_stop = False
            raise RuntimeError("fixture stop failure")
        super().stop()


def make_core(
    data_root: Path,
    audio: DeterministicFakeAudioInput,
    adapter: DeterministicFakeASRAdapter,
    events: list[tuple[str, dict[str, Any]]],
    *,
    join_timeout: float = 0.05,
) -> CoreService:
    return CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=audio,
        asr_adapters={adapter.id: adapter},
        presentation_adapter=ManualPresentationAdapter(),
        event_sink=lambda envelope: events.append(
            (str(envelope["event"]), dict(envelope["payload"]))
        ),
        asr_worker_join_timeout_seconds=join_timeout,
    )


def start_run(core: CoreService) -> tuple[str, str]:
    project_id = str(
        call(core, "project.create", {"name": "M6 lifecycle fixture"})["project"]["id"]
    )
    session_id = str(
        call(
            core,
            "session.start",
            {"project_id": project_id, "mode": "run", "current_slide_start": 1},
        )["session"]["id"]
    )
    call(core, "asr.start", {"project_id": project_id, "session_id": session_id})
    return project_id, session_id


def feed_one_utterance(audio: DeterministicFakeAudioInput) -> None:
    loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
    quiet = np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)
    audio.feed_frames([loud] * 8 + [quiet] * 31)


def test_blocked_final_keeps_run_and_deletions_nonterminal_until_retry(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    audio = DeterministicFakeAudioInput()
    adapter = BlockingFinalAdapter()
    final_seen = threading.Event()
    core = make_core(tmp_path / "data", audio, adapter, events)

    def capture_event(envelope: dict[str, Any]) -> None:
        events.append((str(envelope["event"]), dict(envelope["payload"])))
        if envelope["event"] == "asr.final":
            final_seen.set()

    core.set_event_sink(capture_event)
    try:
        project_id, session_id = start_run(core)
        second_session = str(
            call(core, "session.start", {"project_id": project_id, "mode": "run"})["session"]["id"]
        )
        feed_one_utterance(audio)
        assert adapter.final_entered.wait(2.0)

        assert (
            error_code(
                core,
                "session.stop",
                {"project_id": project_id, "session_id": session_id},
            )
            == "ASR_CAPTURE_FAILED"
        )
        assert (
            call(
                core,
                "session.get",
                {"project_id": project_id, "session_id": session_id},
            )["session"]["status"]
            == "active"
        )
        assert call(core, "asr.status", {})["capture_state"] == "stopping"
        assert adapter.close_count == 0
        assert (
            error_code(
                core,
                "asr.start",
                {"project_id": project_id, "session_id": second_session},
            )
            == "ASR_ALREADY_RUNNING"
        )
        assert (
            error_code(
                core,
                "session.delete",
                {"project_id": project_id, "session_id": session_id},
            )
            == "ASR_CAPTURE_FAILED"
        )
        assert (
            error_code(core, "project.delete", {"project_id": project_id}) == "ASR_CAPTURE_FAILED"
        )

        adapter.release_final.set()
        assert final_seen.wait(2.0)
        stopped = call(
            core,
            "session.stop",
            {"project_id": project_id, "session_id": session_id, "status": "completed"},
        )
        assert stopped["session"]["status"] == "completed"
        assert adapter.close_count == 1
        assert call(core, "project.delete", {"project_id": project_id})["deleted"] is True
    finally:
        adapter.release_final.set()
        core.close()


def test_core_shutdown_reuses_safe_run_cleanup_and_preserves_active_state_on_timeout(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    audio = DeterministicFakeAudioInput()
    adapter = BlockingFinalAdapter()
    core = make_core(tmp_path / "data", audio, adapter, events)
    final_seen = threading.Event()

    def capture_event(envelope: dict[str, Any]) -> None:
        events.append((str(envelope["event"]), dict(envelope["payload"])))
        if envelope["event"] == "asr.final":
            final_seen.set()

    core.set_event_sink(capture_event)
    try:
        project_id, session_id = start_run(core)
        feed_one_utterance(audio)
        assert adapter.final_entered.wait(2.0)

        shutdown = core.handle_message(request("core.shutdown", {}))
        assert shutdown["ok"] is True
        assert shutdown["result"]["cleanup_pending"] is True
        assert (
            call(
                core,
                "session.get",
                {"project_id": project_id, "session_id": session_id},
            )["session"]["status"]
            == "active"
        )

        adapter.release_final.set()
        assert final_seen.wait(2.0)
        assert core.close() is True
        restarted = CoreService(
            data_root=tmp_path / "data",
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
            audio_input=DeterministicFakeAudioInput(),
            asr_adapters={"deterministic-fake": DeterministicFakeASRAdapter()},
            presentation_adapter=ManualPresentationAdapter(),
        )
        try:
            state = call(
                restarted,
                "session.get",
                {"project_id": project_id, "session_id": session_id},
            )
            assert state["session"]["status"] == "aborted"
            assert (
                call(
                    restarted,
                    "run.get_debrief",
                    {"project_id": project_id, "session_id": session_id},
                )["debrief"]
                is None
            )
        finally:
            restarted.close()
    finally:
        adapter.release_final.set()
        core.close()


def test_slow_partial_cannot_block_ingestion_or_displace_final(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    audio = DeterministicFakeAudioInput()
    adapter = SlowPartialAdapter()
    core = make_core(tmp_path / "data", audio, adapter, events, join_timeout=1.0)
    final_seen = threading.Event()

    def capture_event(envelope: dict[str, Any]) -> None:
        events.append((str(envelope["event"]), dict(envelope["payload"])))
        if envelope["event"] == "asr.final":
            final_seen.set()

    core.set_event_sink(capture_event)
    try:
        project_id, session_id = start_run(core)
        loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
        quiet = np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)
        audio.feed_frames([loud] * 8)
        assert adapter.partial_entered.wait(2.0)

        with core._asr._lock:
            active = core._asr._active
            assert active is not None
            active.ingestion_progress.clear()
            initial_processed = active.frames_processed
        target_processed = initial_processed
        for _ in range(7):
            audio.feed_frames([loud] * 50)
            target_processed += 50
            while True:
                with core._asr._lock:
                    active = core._asr._active
                    assert active is not None
                    if active.frames_processed >= target_processed:
                        break
                    active.ingestion_progress.clear()
                assert active.ingestion_progress.wait(2.0)
        with core._asr._lock:
            active = core._asr._active
            assert active is not None
            assert active.backpressure is False
            assert active.frames.qsize() < 256
            assert active.partial_request is not None
            assert adapter.partial_calls == 1

        with core._asr._lock:
            active = core._asr._active
            assert active is not None
            active.ingestion_progress.clear()
            quiet_target = active.frames_processed + 31
        audio.feed_frames([quiet] * 31)
        while True:
            with core._asr._lock:
                active = core._asr._active
                assert active is not None
                if active.frames_processed >= quiet_target:
                    break
                active.ingestion_progress.clear()
            assert active.ingestion_progress.wait(2.0)
        assert active.final_enqueued.wait(2.0)
        adapter.release_partial.set()
        assert final_seen.wait(2.0)
        assert (
            call(
                core,
                "session.stop",
                {"project_id": project_id, "session_id": session_id},
            )["session"]["status"]
            == "completed"
        )
    finally:
        adapter.release_partial.set()
        core.close()


def test_audio_input_loss_is_reported_as_backpressure(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter()
    core = make_core(tmp_path / "data", audio, adapter, events)
    error_seen = threading.Event()

    def capture_event(envelope: dict[str, Any]) -> None:
        events.append((str(envelope["event"]), dict(envelope["payload"])))
        if (
            envelope["event"] == "asr.device_error"
            and envelope["payload"].get("error_code") == "ASR_BACKPRESSURE"
        ):
            error_seen.set()

    core.set_event_sink(capture_event)
    try:
        project_id, session_id = start_run(core)
        loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
        audio.feed(loud, status=SimpleNamespace(input_overflow=True))
        assert error_seen.wait(2.0)
        assert (
            error_code(
                core,
                "session.stop",
                {"project_id": project_id, "session_id": session_id},
            )
            == "ASR_BACKPRESSURE"
        )
    finally:
        core.close()


def test_audio_stop_failure_keeps_run_active_until_retry(tmp_path: Path) -> None:
    audio = FailingStopAudioInput()
    core = make_core(
        tmp_path / "data",
        audio,
        DeterministicFakeASRAdapter(),
        [],
    )
    try:
        project_id, session_id = start_run(core)
        assert (
            error_code(
                core,
                "session.stop",
                {"project_id": project_id, "session_id": session_id},
            )
            == "ASR_CAPTURE_FAILED"
        )
        assert (
            call(
                core,
                "session.get",
                {"project_id": project_id, "session_id": session_id},
            )["session"]["status"]
            == "active"
        )
        with core._asr._lock:
            active = core._asr._active
            assert active is not None
        assert active.ingestion_done.wait(1.0)
        assert active.decoder_done.wait(1.0)
        assert audio.close_count == 0
        assert (
            call(
                core,
                "session.stop",
                {"project_id": project_id, "session_id": session_id},
            )["session"]["status"]
            == "completed"
        )
        assert audio.close_count == 1
    finally:
        core.close()


class RecordingRetrieval:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def query(self, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(params))
        return self.response


def _numeric_hit(evidence_id: str, text: str, *, fact_safe: bool) -> dict[str, Any]:
    return {
        "evidence": {
            "evidence_id": evidence_id,
            "label": evidence_id,
            "source_type": "document",
            "source_id": "document-1",
            "source_unit_id": "unit-1",
            "text": text,
            "fact_safe": fact_safe,
        }
    }


def _run_numeric_debrief(
    tmp_path: Path,
    response: dict[str, Any],
) -> tuple[dict[str, Any], RecordingRetrieval, CoreService]:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=DeterministicFakeAudioInput(),
        asr_adapters={"deterministic-fake": DeterministicFakeASRAdapter()},
        presentation_adapter=ManualPresentationAdapter(),
    )
    project_id = str(call(core, "project.create", {"name": "numeric debrief"})["project"]["id"])
    session_id = str(
        call(
            core,
            "session.start",
            {"project_id": project_id, "mode": "run", "current_slide_start": 1},
        )["session"]["id"]
    )
    core._run.persist_final_utterance(
        project_id,
        session_id,
        str(uuid.uuid4()),
        "The recovery time objective is exactly 30 minutes today.",
        0,
        1_000,
        None,
        1,
    )
    retrieval = RecordingRetrieval(response)
    core._run._retrieval = retrieval  # type: ignore[assignment]
    result = call(
        core,
        "session.stop",
        {"project_id": project_id, "session_id": session_id, "status": "completed"},
    )
    return result["debrief"], retrieval, core


def test_numeric_debrief_requires_fact_safe_exact_support(tmp_path: Path) -> None:
    cases = [
        (
            {
                "hits": [
                    _numeric_hit(
                        "matching",
                        "The recovery time objective is 30 minutes.",
                        fact_safe=True,
                    )
                ],
                "conflicts": [],
            },
            "supported",
            0,
        ),
        (
            {
                "hits": [
                    _numeric_hit(
                        "wrong-number",
                        "The recovery time objective is 45 minutes.",
                        fact_safe=True,
                    )
                ],
                "conflicts": [],
            },
            "needs_evidence_review",
            1,
        ),
        (
            {
                "hits": [
                    _numeric_hit(
                        "thirty",
                        "The recovery time objective is 30 minutes.",
                        fact_safe=True,
                    ),
                    _numeric_hit(
                        "forty-five",
                        "The recovery time objective is 45 minutes.",
                        fact_safe=True,
                    ),
                ],
                "conflicts": [],
            },
            "conflict_review",
            1,
        ),
        (
            {
                "hits": [
                    _numeric_hit(
                        "inference",
                        "The recovery time objective is 30 minutes.",
                        fact_safe=False,
                    )
                ],
                "conflicts": [],
            },
            "needs_evidence_review",
            1,
        ),
    ]
    for index, (response, expected_status, expected_reviews) in enumerate(cases):
        debrief, retrieval, core = _run_numeric_debrief(tmp_path / str(index), response)
        try:
            reviews = debrief["evidence_review_candidates"]
            assert len(reviews) == expected_reviews
            explanations = debrief["best_explanation_candidates"]
            assert explanations
            support = explanations[0]["fact_support"]
            assert support["status"] == expected_status
            if expected_status == "supported":
                assert [item["evidence_id"] for item in explanations[0]["evidence"]] == ["matching"]
            else:
                assert explanations[0]["evidence"] == []
            assert retrieval.calls[0]["usage"] == "rehearsal"
            assert retrieval.calls[0]["allow_private"] is True
        finally:
            core.close()


def test_run_debrief_rehearsal_filter_excludes_disabled_knowledge_item(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=DeterministicFakeAudioInput(),
        asr_adapters={"deterministic-fake": DeterministicFakeASRAdapter()},
        presentation_adapter=ManualPresentationAdapter(),
    )
    try:
        project_id = str(
            call(core, "project.create", {"name": "rehearsal filter"})["project"]["id"]
        )
        now = "2026-09-03T00:00:00.000Z"
        disabled_id = str(uuid.uuid4())
        enabled_id = str(uuid.uuid4())
        statement_disabled = str(uuid.uuid4())
        statement_enabled = str(uuid.uuid4())
        with core._storage.project_database(project_id) as connection:
            for statement_id in (statement_disabled, statement_enabled):
                connection.execute(
                    "INSERT INTO user_statements "
                    "(id, project_id, origin_session_id, source_utterance_id, text, created_at) "
                    "VALUES (?, ?, NULL, NULL, ?, ?)",
                    (
                        statement_id,
                        project_id,
                        "Explain the recovery strategy for the executive review.",
                        now,
                    ),
                )
            for item_id, statement_id, use_rehearsal in (
                (disabled_id, statement_disabled, 0),
                (enabled_id, statement_enabled, 1),
            ):
                connection.execute(
                    "INSERT INTO knowledge_items "
                    "(id, project_id, kind, text, use_live, use_rehearsal, preferred, private, "
                    "created_by, origin_session_id, created_at, updated_at) "
                    "VALUES (?, ?, 'fact', ?, 1, ?, 0, 0, 'user', NULL, ?, ?)",
                    (
                        item_id,
                        project_id,
                        "Explain the recovery strategy for the executive review.",
                        use_rehearsal,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO knowledge_evidence "
                    "(knowledge_item_id, provenance_type, provenance_id) VALUES "
                    "(?, 'user_statement', ?)",
                    (item_id, statement_id),
                )
            connection.commit()
        session_id = str(
            call(
                core,
                "session.start",
                {"project_id": project_id, "mode": "run", "current_slide_start": 1},
            )["session"]["id"]
        )
        core._run.persist_final_utterance(
            project_id,
            session_id,
            str(uuid.uuid4()),
            "Explain the recovery strategy for the executive review today.",
            0,
            1_000,
            None,
            1,
        )
        stopped = call(
            core,
            "session.stop",
            {"project_id": project_id, "session_id": session_id, "status": "completed"},
        )
        debrief = stopped["debrief"]
        evidence = [
            item
            for candidate in debrief["best_explanation_candidates"]
            for item in candidate["evidence"]
        ]
        assert disabled_id not in {item.get("knowledge_item_id") for item in evidence}
        assert enabled_id in {item.get("knowledge_item_id") for item in evidence}
    finally:
        core.close()
