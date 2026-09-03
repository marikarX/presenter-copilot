from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import ASR_FRAME_SAMPLES, DeterministicFakeAudioInput
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.adapters import (
    FakePowerPointFacade,
    PowerPointPresentationAdapter,
    PresentationInfo,
    PresentationSnapshot,
)
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter

FIXTURE_ROOT = Path(__file__).parents[2] / "samples" / "synthetic-deck"


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


def make_core(
    data_root: Path,
    *,
    presentation_adapter: PowerPointPresentationAdapter | None = None,
) -> CoreService:
    fake_audio = DeterministicFakeAudioInput()
    fake_asr = DeterministicFakeASRAdapter()
    return CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=fake_audio,
        asr_adapters={fake_asr.id: fake_asr},
        presentation_adapter=presentation_adapter,
    )


def import_presentation(core: CoreService, project_id: str) -> None:
    call(
        core,
        "source.import",
        {
            "project_id": project_id,
            "kind": "presentation",
            "path": str(FIXTURE_ROOT / "deck" / "presentation.pptx"),
        },
    )


def test_asr_requires_active_run_and_invalid_device_never_owns_capture(tmp_path: Path) -> None:
    core = make_core(tmp_path / "data")
    try:
        project_id = str(call(core, "project.create", {"name": "ASR boundaries"})["project"]["id"])
        teach_id = str(
            call(core, "session.start", {"project_id": project_id, "mode": "teach"})["session"][
                "id"
            ]
        )
        assert (
            error_code(
                core,
                "asr.start",
                {"project_id": project_id, "session_id": teach_id},
            )
            == "ASR_SESSION_INVALID"
        )
        assert (
            error_code(
                core,
                "session.start",
                {"project_id": project_id, "mode": "live_assist"},
            )
            == "MODE_NOT_IMPLEMENTED"
        )
        run_id = str(
            call(core, "session.start", {"project_id": project_id, "mode": "run"})["session"]["id"]
        )
        call(core, "asr.configure", {"device_id": "device-that-disappeared"})
        assert (
            error_code(
                core,
                "asr.start",
                {"project_id": project_id, "session_id": run_id},
            )
            == "ASR_DEVICE_UNAVAILABLE"
        )
        status = call(core, "asr.status", {})
        assert status["capture_state"] == "stopped"
        assert status["session_id"] is None
    finally:
        core.close()


def test_asr_final_is_committed_before_event_and_partial_stays_ephemeral(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    final_seen = threading.Event()
    committed_at_final: list[bool] = []
    core: CoreService | None = None
    project_id: str | None = None

    def on_event(envelope: dict[str, Any]) -> None:
        event = str(envelope["event"])
        payload = dict(envelope["payload"])
        if event == "asr.final":
            assert core is not None and project_id is not None
            with core._storage.project_database(project_id) as connection:
                committed_at_final.append(
                    connection.execute(
                        "SELECT 1 FROM utterances WHERE id = ? AND is_final = 1",
                        (payload["utterance_id"],),
                    ).fetchone()
                    is not None
                )
            final_seen.set()
        events.append((event, payload))

    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(
        partial_texts=("the three year", "the three year cost drops"),
        final_text="The three year cost drops by eighteen percent.",
    )
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=audio,
        asr_adapters={adapter.id: adapter},
        presentation_adapter=None,
        event_sink=on_event,
    )
    try:
        project_id = str(call(core, "project.create", {"name": "ASR lifecycle"})["project"]["id"])
        first_session = str(
            call(core, "session.start", {"project_id": project_id, "mode": "run"})["session"]["id"]
        )
        second_session = str(
            call(core, "session.start", {"project_id": project_id, "mode": "run"})["session"]["id"]
        )
        call(core, "asr.configure", {"device_id": "fake-microphone"})
        call(core, "asr.start", {"project_id": project_id, "session_id": first_session})
        assert (
            error_code(
                core,
                "asr.start",
                {"project_id": project_id, "session_id": second_session},
            )
            == "ASR_ALREADY_RUNNING"
        )
        assert error_code(core, "asr.configure", {"device_id": "fake-microphone"}) == "ASR_BUSY"

        loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
        quiet = np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)
        audio.feed_frames([loud] * 30 + [quiet] * 35)
        assert final_seen.wait(5.0)
        assert committed_at_final == [True]
        partials = [payload for event, payload in events if event == "asr.partial"]
        finals = [payload for event, payload in events if event == "asr.final"]
        assert partials and finals
        assert {payload["utterance_id"] for payload in partials + finals} == {
            finals[0]["utterance_id"]
        }
        with core._storage.project_database(project_id) as connection:
            rows = connection.execute(
                "SELECT text, is_final FROM utterances WHERE session_id = ?",
                (first_session,),
            ).fetchall()
        assert [(row["text"], row["is_final"]) for row in rows] == [
            ("The three year cost drops by eighteen percent.", 1)
        ]
        assert (
            error_code(
                core,
                "asr.stop",
                {"project_id": project_id, "session_id": second_session},
            )
            == "ASR_SESSION_INVALID"
        )
        call(core, "session.stop", {"project_id": project_id, "session_id": first_session})
        call(
            core,
            "session.stop",
            {"project_id": project_id, "session_id": second_session, "status": "aborted"},
        )
    finally:
        core.close()


def test_powerpoint_match_mismatch_and_midrun_fallback_preserve_manual_run(
    tmp_path: Path,
) -> None:
    facade = FakePowerPointFacade(PresentationSnapshot("presentation.pptx", 22, 4))
    adapter = PowerPointPresentationAdapter(facade)
    info = PresentationInfo("document", "presentation.pptx", 22)
    assert adapter.detect(info)["mode"] == "powerpoint"
    facade.current = PresentationSnapshot("other.pptx", 22, 4)
    assert adapter.detect(info)["reason"] == "POWERPOINT_DECK_MISMATCH"
    facade.current = PresentationSnapshot("presentation.pptx", 21, 4)
    assert adapter.detect(info)["reason"] == "POWERPOINT_SLIDE_COUNT_MISMATCH"

    facade.current = PresentationSnapshot("presentation.pptx", 22, 4)
    events: list[tuple[str, dict[str, Any]]] = []
    durable_slide_events: list[bool] = []

    def on_event(envelope: dict[str, Any]) -> None:
        event = str(envelope["event"])
        payload = dict(envelope["payload"])
        if event == "presentation.slide_changed":
            with core._storage.project_database(project_id) as connection:
                durable_slide_events.append(
                    connection.execute(
                        "SELECT 1 FROM slide_state_events WHERE session_id = ? "
                        "AND slide_ordinal = ? LIMIT 1",
                        (payload["session_id"], payload["slide_ordinal"]),
                    ).fetchone()
                    is not None
                )
        events.append((event, payload))

    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=DeterministicFakeAudioInput(),
        asr_adapters={"deterministic-fake": DeterministicFakeASRAdapter()},
        presentation_adapter=adapter,
        event_sink=on_event,
    )
    try:
        project_id = str(
            call(core, "project.create", {"name": "PowerPoint boundaries"})["project"]["id"]
        )
        import_presentation(core, project_id)
        session_id = str(
            call(core, "session.start", {"project_id": project_id, "mode": "run"})["session"]["id"]
        )
        assert (
            call(
                core,
                "presentation.status",
                {"project_id": project_id, "session_id": session_id},
            )["mode"]
            == "powerpoint"
        )

        facade.current = PresentationSnapshot("presentation.pptx", 22, 5)
        assert (
            call(
                core,
                "presentation.detect",
                {"project_id": project_id, "session_id": session_id},
            )["current_slide"]
            == 5
        )
        facade.fail = True
        fallback = call(
            core,
            "presentation.detect",
            {"project_id": project_id, "session_id": session_id},
        )
        assert fallback["mode"] == "manual"
        assert fallback["current_slide"] == 5
        assert (
            call(
                core,
                "presentation.next_slide",
                {"project_id": project_id, "session_id": session_id},
            )["current_slide"]
            == 6
        )
        assert (
            call(
                core,
                "session.get",
                {"project_id": project_id, "session_id": session_id},
            )["session"]["status"]
            == "active"
        )

        with core._storage.project_database(project_id) as connection:
            rows = connection.execute(
                "SELECT slide_ordinal, source FROM slide_state_events "
                "WHERE session_id = ? ORDER BY timestamp_ms, id",
                (session_id,),
            ).fetchall()
        assert [(row[0], row[1]) for row in rows] == [
            (4, "powerpoint"),
            (5, "powerpoint"),
            (6, "manual"),
        ]
        slide_event_index = next(
            index
            for index, (event, payload) in enumerate(events)
            if event == "presentation.slide_changed" and payload["slide_ordinal"] == 5
        )
        assert rows[1][0] == 5
        assert slide_event_index >= 0
        assert durable_slide_events == [True, True, True]
    finally:
        core.close()


def test_run_schema_has_no_audio_table_or_audio_event_payload(tmp_path: Path) -> None:
    core = make_core(tmp_path / "data")
    try:
        project_id = str(
            call(core, "project.create", {"name": "No audio persistence"})["project"]["id"]
        )
        with core._storage.project_database(project_id) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        assert not any("audio" in table.casefold() for table in tables)
    finally:
        core.close()


@pytest.mark.parametrize(
    "snapshot,reason",
    [
        (None, "POWERPOINT_NO_ACTIVE_SLIDESHOW"),
        (PresentationSnapshot("presentation.pptx", 22, 0), "POWERPOINT_INVALID_SLIDE"),
    ],
)
def test_powerpoint_unusable_state_falls_back_without_exception(
    snapshot: PresentationSnapshot | None,
    reason: str,
) -> None:
    adapter = PowerPointPresentationAdapter(FakePowerPointFacade(snapshot))
    result = adapter.detect(PresentationInfo("document", "presentation.pptx", 22))
    assert result["mode"] == "manual"
    assert result["reason"] == reason
