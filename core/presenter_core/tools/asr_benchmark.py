"""Metadata-only end-to-end timing benchmark for the pinned local ASR path."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import threading
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from presenter_core.asr.adapters import FasterWhisperASRAdapter
from presenter_core.asr.audio import (
    ASR_FRAME_DURATION_MS,
    ASR_FRAME_SAMPLES,
    DeterministicFakeAudioInput,
)
from presenter_core.asr.segmenter import UtteranceSegment, UtteranceSegmenter
from presenter_core.asr.service import ASRService
from presenter_core.errors import CoreDomainError
from presenter_core.storage.paths import AppPaths

FIXTURE_ROOT = Path(__file__).parents[3] / "samples" / "synthetic-deck"
FIXTURE_PATH = FIXTURE_ROOT / "audio" / "speech-fixture.wav"


@dataclass(frozen=True)
class ASRServiceTiming:
    """User-visible Core event times from one deterministic audio capture."""

    first_partial_after_onset_ms: float | None
    first_final_after_speech_end_ms: float | None
    first_final_after_vad_completion_ms: float | None


def _model_cache(data_root: Path | None) -> Path:
    paths = AppPaths(data_root)
    candidate = paths.root / "models" / "asr"
    if candidate.exists():
        return paths.asr_model_cache_directory(create=False)
    return candidate


def _read_fixture(path: Path) -> tuple[np.ndarray[Any, Any], float]:
    with wave.open(str(path), "rb") as source:
        if (
            source.getnchannels() != 1
            or source.getsampwidth() != 2
            or source.getframerate() != 16_000
        ):
            raise ValueError("fixture must be 16 kHz mono signed 16-bit PCM")
        frame_count = source.getnframes()
        if frame_count < 1 or frame_count > 16_000 * 60:
            raise ValueError("fixture duration is outside the benchmark bound")
        samples = np.frombuffer(source.readframes(frame_count), dtype="<i2").astype(np.float32)
    return samples / 32_768.0, frame_count / 16_000


def _fixture_windows(
    samples: np.ndarray[Any, Any],
) -> tuple[np.ndarray[Any, Any], UtteranceSegment, float]:
    """Find one deterministic speech window for onset/finalization timing."""
    segmenter = UtteranceSegmenter()
    partial_audio: np.ndarray[Any, Any] | None = None
    onset_ms: int | None = None
    partial_buffer_ms = 0.0
    final_segment: UtteranceSegment | None = None
    frame_clock_ms = 0
    for offset in range(0, len(samples), ASR_FRAME_SAMPLES):
        frame = samples[offset : offset + ASR_FRAME_SAMPLES]
        if len(frame) < ASR_FRAME_SAMPLES:
            frame = np.pad(frame, (0, ASR_FRAME_SAMPLES - len(frame)))
        was_active = segmenter.speech_active
        completed = segmenter.process(frame, frame_clock_ms)
        if not was_active and segmenter.speech_active and partial_audio is None:
            segment_start_ms = segmenter.current_start_ms
            onset_ms = frame_clock_ms if segment_start_ms is None else segment_start_ms
            partial_audio = segmenter.current_audio()
            partial_buffer_ms = max(0.0, float(frame_clock_ms + 20 - onset_ms))
        frame_clock_ms += 20
        if completed is not None:
            final_segment = completed
            break
    if final_segment is None:
        final_segment = segmenter.flush(frame_clock_ms)
    if partial_audio is None or final_segment is None or onset_ms is None:
        raise ValueError("the ASR fixture did not contain a detectable speech window")
    return partial_audio, final_segment, partial_buffer_ms


def _fixture_first_speech_timing(samples: np.ndarray[Any, Any]) -> tuple[int, int, int]:
    """Return speech onset, last active frame, and completed VAD segment times."""
    segmenter = UtteranceSegmenter()
    frame_clock_ms = 0
    onset_ms: int | None = None
    speech_end_ms: int | None = None
    for offset in range(0, len(samples), ASR_FRAME_SAMPLES):
        frame = samples[offset : offset + ASR_FRAME_SAMPLES]
        if len(frame) < ASR_FRAME_SAMPLES:
            frame = np.pad(frame, (0, ASR_FRAME_SAMPLES - len(frame)))
        was_active = segmenter.speech_active
        rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
        completed = segmenter.process(frame, frame_clock_ms)
        if not was_active and segmenter.speech_active:
            segment_start_ms = segmenter.current_start_ms
            onset_ms = max(
                0,
                frame_clock_ms if segment_start_ms is None else segment_start_ms,
            )
        if segmenter.speech_active and rms > segmenter.config.speech_end_rms:
            speech_end_ms = frame_clock_ms + ASR_FRAME_DURATION_MS
        frame_clock_ms += ASR_FRAME_DURATION_MS
        if completed is not None:
            if onset_ms is None or speech_end_ms is None:
                raise ValueError("the first ASR fixture segment has invalid speech boundaries")
            return onset_ms, speech_end_ms, completed.end_ms
    raise ValueError("the ASR fixture did not contain a complete detectable speech window")


def _wait_for_frame_deadline(
    final_ready: threading.Event,
    *,
    capture_started: float,
    frame_end_ms: int,
) -> bool:
    """Pace fixture frames against capture time without accumulating timer drift."""
    if final_ready.is_set():
        return True
    deadline = capture_started + frame_end_ms / 1_000
    return final_ready.wait(timeout=max(0.0, deadline - perf_counter()))


def _measure_service_events(
    adapter: FasterWhisperASRAdapter,
    samples: np.ndarray[Any, Any],
    *,
    onset_ms: int,
    speech_end_ms: int,
    segment_end_ms: int,
) -> ASRServiceTiming:
    """Measure partial and final events through Core's capture/decoder lifecycle."""
    audio_input = DeterministicFakeAudioInput()
    event_times: dict[str, float] = {}
    partial_ready = threading.Event()
    final_ready = threading.Event()
    capture_started: float | None = None

    def on_event(event: str, _payload: dict[str, Any]) -> None:
        nonlocal capture_started
        if capture_started is None:
            return
        if (
            event == "asr.partial"
            and not partial_ready.is_set()
            and _payload.get("start_ms") == onset_ms
        ):
            event_times["partial"] = perf_counter()
            partial_ready.set()
        elif (
            event == "asr.final"
            and not final_ready.is_set()
            and _payload.get("start_ms") == onset_ms
            and _payload.get("end_ms") == segment_end_ms
        ):
            event_times["final"] = perf_counter()
            final_ready.set()

    service = ASRService(
        audio_input=audio_input,
        adapters={adapter.id: adapter},
        session_validator=lambda _project_id, _session_id, _mode: {"mode": "run"},
        persist_final=lambda *_args: None,
        slide_snapshot=lambda *_args: None,
        event_sink=on_event,
    )
    project_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    params = {"project_id": project_id, "session_id": session_id}
    try:
        service.start(params)
        capture_started = perf_counter()
        # Continue through the first VAD-completed segment so the final metric
        # includes the service queue and emitted event, not only model decode.
        max_feed_ms = segment_end_ms + 2_000
        for offset in range(0, len(samples), ASR_FRAME_SAMPLES):
            frame_start_ms = offset // ASR_FRAME_SAMPLES * ASR_FRAME_DURATION_MS
            if frame_start_ms >= max_feed_ms:
                break
            frame = samples[offset : offset + ASR_FRAME_SAMPLES]
            if len(frame) < ASR_FRAME_SAMPLES:
                frame = np.pad(frame, (0, ASR_FRAME_SAMPLES - len(frame)))
            audio_input.feed(frame)
            frame_end_ms = frame_start_ms + ASR_FRAME_DURATION_MS
            if _wait_for_frame_deadline(
                final_ready,
                capture_started=capture_started,
                frame_end_ms=frame_end_ms,
            ):
                break
        if not final_ready.is_set():
            final_ready.wait(timeout=2.0)
        partial_event_time = event_times.get("partial")
        final_event_time = event_times.get("final")
        partial_latency = (
            max(0.0, (partial_event_time - capture_started) * 1_000 - onset_ms)
            if partial_event_time is not None and capture_started is not None
            else None
        )
        final_after_speech_end = (
            max(0.0, (final_event_time - capture_started) * 1_000 - speech_end_ms)
            if final_event_time is not None and capture_started is not None
            else None
        )
        final_after_vad_completion = (
            max(0.0, (final_event_time - capture_started) * 1_000 - segment_end_ms)
            if final_event_time is not None and capture_started is not None
            else None
        )
        return ASRServiceTiming(
            partial_latency,
            final_after_speech_end,
            final_after_vad_completion,
        )
    finally:
        try:
            service.cancel(params)
        finally:
            service.close()


def _git_sha(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark local ASR load and decode timings.")
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Optional application data root containing the prepared ASR cache.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / "m6-asr-benchmark.json",
        help="Metadata-only JSON output path.",
    )
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args(argv)
    root = Path(__file__).parents[3]
    output = args.output if args.output.is_absolute() else root / args.output
    base_report: dict[str, Any] = {
        "status": "unavailable",
        "benchmark": "m6-local-asr-v2",
        "git_sha": _git_sha(root),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor() or None,
        "fixture_id": "synthetic-asr-speech-v1",
        "iterations": max(1, min(args.iterations, 10)),
        "targets": {
            "first_partial_p50_ms": 500.0,
            "first_final_after_speech_end_p50_ms": 900.0,
        },
        "local_files_only": True,
        "network_allowed_by_this_command": False,
        "provider_called": False,
    }
    adapter: FasterWhisperASRAdapter | None = None
    try:
        audio, duration_seconds = _read_fixture(FIXTURE_PATH)
        base_report["fixture_duration_seconds"] = round(duration_seconds, 3)
        adapter = FasterWhisperASRAdapter(cache_dir=_model_cache(args.data_root))
        base_report["adapter_id"] = adapter.id
        base_report["model_id"] = adapter.model_id
        base_report["execution"] = adapter.execution
        if adapter.model_status() == "not_installed":
            base_report.update(
                {
                    "code": "ASR_MODEL_UNAVAILABLE",
                    "message": "Prepare the pinned local ASR model before benchmarking.",
                }
            )
            _write_report(output, base_report)
            print(json.dumps(base_report, indent=2, sort_keys=True))
            return 2

        load_started = perf_counter()
        adapter.load_local_model()
        load_ms = (perf_counter() - load_started) * 1_000
        partial_times: list[float] = []
        missing_partial_samples = 0
        final_event_times: list[float] = []
        final_after_vad_times: list[float] = []
        missing_final_samples = 0
        final_times: list[float] = []
        _partial_audio, final_segment, _partial_buffer_ms = _fixture_windows(audio)
        onset_ms, speech_end_ms, segment_end_ms = _fixture_first_speech_timing(audio)
        utterance_duration_seconds = max(
            (final_segment.end_ms - final_segment.start_ms) / 1_000,
            0.001,
        )
        for _ in range(base_report["iterations"]):
            service_timing = _measure_service_events(
                adapter,
                audio,
                onset_ms=onset_ms,
                speech_end_ms=speech_end_ms,
                segment_end_ms=segment_end_ms,
            )
            if service_timing.first_partial_after_onset_ms is None:
                missing_partial_samples += 1
            else:
                partial_times.append(service_timing.first_partial_after_onset_ms)
            if service_timing.first_final_after_speech_end_ms is None:
                missing_final_samples += 1
            else:
                final_event_times.append(service_timing.first_final_after_speech_end_ms)
            if service_timing.first_final_after_vad_completion_ms is not None:
                final_after_vad_times.append(service_timing.first_final_after_vad_completion_ms)
            if adapter.model_status() != "ready":
                adapter.load_local_model()
            started = perf_counter()
            adapter.transcribe_final(final_segment.audio, language="en")
            final_times.append((perf_counter() - started) * 1_000)

        def summary(values: list[float]) -> dict[str, float]:
            return {
                "first_ms": round(values[0], 3),
                "p50_ms": round(float(np.percentile(values, 50)), 3),
                "p95_ms": round(float(np.percentile(values, 95)), 3),
                "max_ms": round(max(values), 3),
            }

        partial_summary = summary(partial_times) if partial_times else None
        final_summary = summary(final_times)
        final_event_summary = summary(final_event_times) if final_event_times else None
        final_after_vad_summary = summary(final_after_vad_times) if final_after_vad_times else None
        target_pass = (
            partial_summary is not None
            and missing_partial_samples == 0
            and partial_summary["p50_ms"] <= 500.0
            and final_event_summary is not None
            and missing_final_samples == 0
            and final_event_summary["p50_ms"] <= 900.0
            and final_summary["p50_ms"] <= 900.0
        )
        base_report.update(
            {
                "status": "passed" if target_pass else "failed",
                "model_load_ms": round(load_ms, 3),
                "sample_count": base_report["iterations"],
                "first_partial_after_onset_ms": partial_summary,
                "first_partial_missing_samples": missing_partial_samples,
                "first_partial_measurement": (
                    "First ASRService event after synthetic 20 ms capture frames"
                ),
                "finalization_ms": final_summary,
                "final_event_after_speech_end_ms": final_event_summary,
                "final_event_after_vad_completion_ms": final_after_vad_summary,
                "final_event_missing_samples": missing_final_samples,
                "final_event_measurement": (
                    "First ASRService final event after the last speech-active VAD frame"
                ),
                "utterance_duration_seconds": round(utterance_duration_seconds, 3),
                "final_real_time_factor": round(
                    (final_times[0] / 1_000) / utterance_duration_seconds, 4
                ),
                "confidence_reported": False,
                "target_pass": target_pass,
            }
        )
        if not target_pass:
            base_report.update(
                {
                    "code": "ASR_BENCHMARK_TARGET_NOT_MET",
                    "message": "Local ASR latency exceeded one or more configured p50 targets.",
                }
            )
        _write_report(output, base_report)
        print(json.dumps(base_report, indent=2, sort_keys=True))
        return 0 if target_pass else 1
    except CoreDomainError as error:
        base_report.update({"code": error.code, "message": error.message})
    except (OSError, ValueError) as error:
        base_report.update({"code": "ASR_FIXTURE_INVALID", "message": str(error)})
    except Exception:
        base_report.update(
            {
                "code": "ASR_BENCHMARK_FAILED",
                "message": "The local ASR benchmark failed.",
            }
        )
    finally:
        if adapter is not None:
            adapter.close()
    _write_report(output, base_report)
    print(json.dumps(base_report, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
