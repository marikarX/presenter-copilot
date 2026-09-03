from __future__ import annotations

import threading
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import presenter_core.presentation.adapters as presentation_adapters
from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import (
    ASR_FRAME_SAMPLES,
    DeterministicFakeAudioInput,
    SoundDeviceAudioInput,
)
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.adapters import (
    FakePowerPointFacade,
    PowerPointComFacade,
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


def test_sounddevice_input_pair_marks_real_default_device() -> None:
    class InputOutputPair:
        def __getitem__(self, index: int) -> int:
            return (1, 4)[index]

    fake_sounddevice = SimpleNamespace(
        query_devices=lambda: [
            {
                "name": "first input",
                "hostapi": 0,
                "max_input_channels": 1,
                "default_samplerate": 44_100,
            },
            {
                "name": "actual default input",
                "hostapi": 0,
                "max_input_channels": 1,
                "default_samplerate": 44_100,
            },
        ],
        query_hostapis=lambda: [{"name": "fixture host"}],
        default=SimpleNamespace(device=InputOutputPair()),
    )

    devices = SoundDeviceAudioInput(sounddevice_module=fake_sounddevice).list_devices()
    assert [device.is_default for device in devices] == [False, True]


def test_sounddevice_stream_lifecycle_matches_pinned_backend_api() -> None:
    class FakeStream:
        def __init__(self, **kwargs: Any) -> None:
            assert "start" not in kwargs
            self.started = False
            self.stopped = False
            self.closed = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

        def close(self) -> None:
            self.closed = True

    fake_sounddevice = SimpleNamespace(
        query_devices=lambda: [
            {
                "name": "fixture input",
                "hostapi": 0,
                "max_input_channels": 1,
                "default_samplerate": 16_000,
            }
        ],
        query_hostapis=lambda: [{"name": "fixture host"}],
        default=SimpleNamespace(device=(0, 0)),
        InputStream=FakeStream,
    )
    audio = SoundDeviceAudioInput(sounddevice_module=fake_sounddevice)

    audio.open("0", lambda _frame: None)
    stream = audio._stream
    assert isinstance(stream, FakeStream)
    audio.start()
    audio.stop()
    audio.close()
    assert stream.started and stream.stopped and stream.closed


def test_sounddevice_normalizes_native_stereo_blocks_to_bounded_asr_frames() -> None:
    class FakeStream:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def close(self) -> None:
            return None

    fake_sounddevice = SimpleNamespace(
        query_devices=lambda: [
            {
                "name": "native stereo input",
                "hostapi": 0,
                "max_input_channels": 2,
                "default_samplerate": 44_100,
            }
        ],
        query_hostapis=lambda: [{"name": "fixture host"}],
        default=SimpleNamespace(device=(0, 0)),
        InputStream=FakeStream,
    )
    received: list[np.ndarray[Any, Any]] = []
    audio = SoundDeviceAudioInput(sounddevice_module=fake_sounddevice)

    audio.open("0", lambda frame: received.append(frame))
    stream = audio._stream
    assert isinstance(stream, FakeStream)
    assert stream.kwargs["samplerate"] == 44_100.0
    assert stream.kwargs["blocksize"] == 882
    assert stream.kwargs["channels"] == 2

    left = np.full(882, 0.01, dtype=np.float32)
    right = np.full(882, 0.2, dtype=np.float32)
    stream.kwargs["callback"](np.column_stack((left, right)), 882, None, None)

    assert len(received) == 1
    assert received[0].dtype == np.float32
    assert received[0].shape == (ASR_FRAME_SAMPLES,)
    assert float(np.mean(received[0])) == pytest.approx(0.2, abs=1e-5)


def test_asr_status_surfaces_silent_capture_without_exposing_pcm(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter()
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=audio,
        asr_adapters={adapter.id: adapter},
    )
    try:
        project_id = str(call(core, "project.create", {"name": "Signal status"})["project"]["id"])
        session_id = str(
            call(core, "session.start", {"project_id": project_id, "mode": "run"})["session"]["id"]
        )
        call(core, "asr.start", {"project_id": project_id, "session_id": session_id})
        before = call(core, "asr.status", {})
        assert before["input_signal_state"] == "unknown"
        assert before["input_frames_received"] == 0

        with core._asr._lock:
            active = core._asr._active
            assert active is not None
            ingestion_progress = active.ingestion_progress
        audio.feed(np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32))
        assert ingestion_progress.wait(2.0)

        after = call(core, "asr.status", {})
        assert after["input_signal_state"] == "silent"
        assert after["input_frames_received"] >= 1
        assert "pcm" not in after
        assert "audio" not in after
    finally:
        core.close()


def test_native_sounddevice_callback_reaches_vad_and_durable_final(tmp_path: Path) -> None:
    class FakeStream:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.started = False

        def start(self) -> None:
            self.started = True
            loud = np.full(882, 0.1, dtype=np.float32)
            quiet = np.zeros(882, dtype=np.float32)
            for frame in [loud] * 8 + [quiet] * 31:
                stereo = np.column_stack((frame * 0.5, frame))
                self.kwargs["callback"](stereo, 882, None, None)

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            return None

    fake_sounddevice = SimpleNamespace(
        query_devices=lambda: [
            {
                "name": "native stereo input",
                "hostapi": 0,
                "max_input_channels": 2,
                "default_samplerate": 44_100,
            }
        ],
        query_hostapis=lambda: [{"name": "fixture host"}],
        default=SimpleNamespace(device=(0, 0)),
        InputStream=FakeStream,
    )
    events: list[tuple[str, dict[str, Any]]] = []
    final_seen = threading.Event()
    adapter = DeterministicFakeASRAdapter(
        partial_texts=("native partial",),
        final_text="Native microphone final.",
    )
    audio = SoundDeviceAudioInput(sounddevice_module=fake_sounddevice)

    def on_event(envelope: dict[str, Any]) -> None:
        event = str(envelope["event"])
        events.append((event, dict(envelope["payload"])))
        if event == "asr.final":
            final_seen.set()

    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=audio,
        asr_adapters={adapter.id: adapter},
        event_sink=on_event,
    )
    try:
        project_id = str(call(core, "project.create", {"name": "Native callback"})["project"]["id"])
        session_id = str(
            call(core, "session.start", {"project_id": project_id, "mode": "run"})["session"]["id"]
        )
        call(core, "asr.start", {"project_id": project_id, "session_id": session_id})

        assert final_seen.wait(5.0)
        assert [event for event, _payload in events].count("asr.final") == 1
        assert any(event == "asr.partial" for event, _payload in events)
        transcript = call(
            core,
            "run.list_transcript",
            {"project_id": project_id, "session_id": session_id, "limit": 10},
        )
        assert transcript["utterances"][0]["text"] == "Native microphone final."
        call(
            core,
            "session.stop",
            {"project_id": project_id, "session_id": session_id, "status": "completed"},
        )
    finally:
        core.close()


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
    partial_seen = threading.Event()
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
        if event == "asr.partial":
            partial_seen.set()
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
        audio.feed_frames([loud] * 30)
        assert partial_seen.wait(2.0)
        audio.feed_frames([quiet] * 35)
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


def test_powerpoint_com_facade_reads_current_slide_from_view_slide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePythonCom:
        initialized = False
        uninitialized = False

        def CoInitialize(self) -> None:
            self.initialized = True

        def CoUninitialize(self) -> None:
            self.uninitialized = True

    pythoncom = FakePythonCom()
    window = SimpleNamespace(
        View=SimpleNamespace(
            # This must not be confused with the current slide index.
            CurrentShowPosition=2,
            Slide=SimpleNamespace(SlideIndex=7),
        ),
        Presentation=SimpleNamespace(
            FullName=r"C:\Decks\reordered.pptx",
            Slides=SimpleNamespace(Count=22),
        ),
    )
    application = SimpleNamespace(
        SlideShowWindows=SimpleNamespace(Count=1, Item=lambda index: window),
    )
    win32com_client = SimpleNamespace(
        GetActiveObject=lambda name: application,
    )
    modules = {
        "pythoncom": pythoncom,
        "win32com.client": win32com_client,
    }

    monkeypatch.setattr(presentation_adapters.os, "name", "nt")
    monkeypatch.setattr(presentation_adapters, "import_module", modules.__getitem__)

    snapshot = PowerPointComFacade().snapshot()

    assert snapshot == PresentationSnapshot("reordered.pptx", 22, 7)
    assert pythoncom.initialized is True
    assert pythoncom.uninitialized is True


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
