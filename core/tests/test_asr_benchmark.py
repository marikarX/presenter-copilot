from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from presenter_core.asr.audio import ASR_FRAME_SAMPLES
from presenter_core.tools import asr_benchmark


@pytest.mark.parametrize(("prefix_frames", "expected_onset_ms"), [(0, 0), (5, 100)])
def test_asr_benchmark_preserves_vad_onset_at_zero_or_after_prefix_silence(
    prefix_frames: int,
    expected_onset_ms: int,
) -> None:
    prefix = np.zeros(prefix_frames * ASR_FRAME_SAMPLES, dtype=np.float32)
    speech = np.full(25 * ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
    trailing_silence = np.zeros(31 * ASR_FRAME_SAMPLES, dtype=np.float32)
    samples = np.concatenate((prefix, speech, trailing_silence))

    onset_ms, speech_end_ms, segment_end_ms = asr_benchmark._fixture_first_speech_timing(samples)

    assert onset_ms == expected_onset_ms
    assert speech_end_ms == expected_onset_ms + 500
    assert segment_end_ms == expected_onset_ms + 1_100


@pytest.mark.parametrize(
    (
        "partial_latency_ms",
        "final_event_latency_ms",
        "expected_status",
        "expected_code",
        "expected_exit",
    ),
    [
        (426.0, 826.0, "passed", None, 0),
        (626.0, 826.0, "failed", "ASR_BENCHMARK_TARGET_NOT_MET", 1),
        (426.0, 926.0, "failed", "ASR_BENCHMARK_TARGET_NOT_MET", 1),
        (None, 826.0, "failed", "ASR_BENCHMARK_TARGET_NOT_MET", 1),
        (426.0, None, "failed", "ASR_BENCHMARK_TARGET_NOT_MET", 1),
    ],
)
def test_asr_benchmark_exit_matches_latency_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    partial_latency_ms: float | None,
    final_event_latency_ms: float | None,
    expected_status: str,
    expected_code: str | None,
    expected_exit: int,
) -> None:
    class FakeAdapter:
        id = "faster-whisper"
        model_id = "fixture-model"
        execution = {"device": "cpu", "compute_type": "int8"}

        def __init__(self, *, cache_dir: Path) -> None:
            self.cache_dir = cache_dir

        def model_status(self) -> str:
            return "installed"

        def load_local_model(self) -> None:
            return None

        def transcribe_partial(self, _audio: np.ndarray, *, language: str) -> None:
            return None

        def transcribe_final(self, _audio: np.ndarray, *, language: str) -> None:
            return None

        def close(self) -> None:
            return None

    clock_values = [0.0, 0.01]
    for index in range(3):
        final_start = 1.0 + index * 2
        clock_values.extend([final_start, final_start + 0.3])
    clock = iter(clock_values)
    segment = SimpleNamespace(start_ms=0, end_ms=3_100, audio=np.zeros(1, dtype=np.float32))

    monkeypatch.setattr(asr_benchmark, "FasterWhisperASRAdapter", FakeAdapter)
    monkeypatch.setattr(asr_benchmark, "_read_fixture", lambda _path: (np.zeros(1), 7.135))
    monkeypatch.setattr(
        asr_benchmark,
        "_fixture_windows",
        lambda _samples: (np.zeros(1), segment, 0.0),
    )
    monkeypatch.setattr(
        asr_benchmark,
        "_fixture_first_speech_timing",
        lambda _samples: (0, 1_000, 3_100),
    )
    monkeypatch.setattr(
        asr_benchmark,
        "_measure_service_events",
        lambda _adapter, _samples, **_kwargs: asr_benchmark.ASRServiceTiming(
            partial_latency_ms,
            final_event_latency_ms,
            final_event_latency_ms,
        ),
    )
    monkeypatch.setattr(asr_benchmark, "_git_sha", lambda _root: None)
    monkeypatch.setattr(asr_benchmark, "perf_counter", lambda: next(clock))
    output = tmp_path / "asr-benchmark.json"

    result = asr_benchmark.main(["--output", str(output)])
    report = json.loads(capsys.readouterr().out)

    assert result == expected_exit
    assert report["status"] == expected_status
    assert report["target_pass"] is (expected_exit == 0)
    assert "ASRService" in report["first_partial_measurement"]
    assert report["first_partial_missing_samples"] == (3 if partial_latency_ms is None else 0)
    assert report["final_event_missing_samples"] == (3 if final_event_latency_ms is None else 0)
    if partial_latency_ms is None:
        assert report["first_partial_after_onset_ms"] is None
    else:
        assert report["first_partial_after_onset_ms"]["p50_ms"] == partial_latency_ms
    if expected_code is None:
        assert "code" not in report
    else:
        assert report["code"] == expected_code
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_asr_benchmark_times_the_first_core_partial_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAudioInput:
        def __init__(self) -> None:
            self.callback = None
            self.started = False
            self.frames = 0

        def open(self, _device_id: str | None, callback: object) -> None:
            self.callback = callback

        def start(self) -> None:
            self.started = True

        def feed(self, frame: np.ndarray) -> None:
            if self.started and callable(self.callback):
                self.frames += 1
                self.callback(frame)

        def stop(self) -> None:
            self.started = False

        def close(self) -> None:
            return None

    services = []

    class FakeService:
        def __init__(self, *, audio_input: FakeAudioInput, event_sink: object, **_kwargs: object):
            self.audio_input = audio_input
            self.event_sink = event_sink
            self.cancelled = False
            self.closed = False
            services.append(self)

        def start(self, _params: dict[str, str]) -> None:
            self.audio_input.open(None, self.on_frame)
            self.audio_input.start()

        def on_frame(self, _frame: np.ndarray) -> None:
            if self.audio_input.frames == 4 and callable(self.event_sink):
                self.event_sink(
                    "asr.partial",
                    {"text": "synthetic", "start_ms": 20, "end_ms": 80},
                )
            if self.audio_input.frames == 6 and callable(self.event_sink):
                self.event_sink(
                    "asr.final",
                    {"text": "synthetic final", "start_ms": 20, "end_ms": 1_000},
                )

        def cancel(self, _params: dict[str, str]) -> None:
            self.cancelled = True
            self.audio_input.stop()

        def close(self) -> None:
            self.closed = True

    clock = iter((10.0, 10.426, 10.9))
    monkeypatch.setattr(asr_benchmark, "DeterministicFakeAudioInput", FakeAudioInput)
    monkeypatch.setattr(asr_benchmark, "ASRService", FakeService)
    monkeypatch.setattr(asr_benchmark, "perf_counter", lambda: next(clock))
    monkeypatch.setattr(
        asr_benchmark,
        "_wait_for_frame_deadline",
        lambda final_ready, **_kwargs: final_ready.is_set(),
    )
    adapter = SimpleNamespace(id="faster-whisper")

    timing = asr_benchmark._measure_service_events(
        adapter,  # type: ignore[arg-type]
        np.zeros(6 * ASR_FRAME_SAMPLES, dtype=np.float32),
        onset_ms=20,
        speech_end_ms=400,
        segment_end_ms=1_000,
    )

    assert timing.first_partial_after_onset_ms == pytest.approx(406.0)
    assert timing.first_final_after_speech_end_ms == pytest.approx(500.0)
    assert timing.first_final_after_vad_completion_ms == 0.0
    assert len(services) == 1
    assert services[0].cancelled
    assert services[0].closed


def test_asr_benchmark_frame_pacing_uses_absolute_deadlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEvent:
        def __init__(self) -> None:
            self.timeouts: list[float] = []

        def is_set(self) -> bool:
            return False

        def wait(self, timeout: float | None = None) -> bool:
            assert timeout is not None
            self.timeouts.append(timeout)
            return False

    clock = iter((10.015, 10.033))
    monkeypatch.setattr(asr_benchmark, "perf_counter", lambda: next(clock))
    event = FakeEvent()

    assert not asr_benchmark._wait_for_frame_deadline(event, capture_started=10.0, frame_end_ms=20)
    assert not asr_benchmark._wait_for_frame_deadline(event, capture_started=10.0, frame_end_ms=40)

    assert event.timeouts == pytest.approx([0.005, 0.007])
