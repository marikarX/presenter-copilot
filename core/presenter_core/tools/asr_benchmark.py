"""Metadata-only timing benchmark for the pinned local ASR adapter."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import wave
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from presenter_core.asr.adapters import FasterWhisperASRAdapter
from presenter_core.asr.audio import ASR_FRAME_SAMPLES
from presenter_core.asr.segmenter import UtteranceSegment, UtteranceSegmenter
from presenter_core.errors import CoreDomainError
from presenter_core.storage.paths import AppPaths

FIXTURE_ROOT = Path(__file__).parents[3] / "samples" / "synthetic-deck"
FIXTURE_PATH = FIXTURE_ROOT / "audio" / "speech-fixture.wav"


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
            onset_ms = segmenter.current_start_ms or frame_clock_ms
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
        "benchmark": "m6-local-asr-v1",
        "git_sha": _git_sha(root),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor() or None,
        "fixture_id": "synthetic-asr-speech-v1",
        "iterations": max(1, min(args.iterations, 10)),
        "targets": {
            "first_partial_p50_ms": 500.0,
            "final_p50_ms": 900.0,
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
        final_times: list[float] = []
        partial_audio, final_segment, partial_buffer_ms = _fixture_windows(audio)
        utterance_duration_seconds = max(
            (final_segment.end_ms - final_segment.start_ms) / 1_000,
            0.001,
        )
        for _ in range(base_report["iterations"]):
            started = perf_counter()
            adapter.transcribe_partial(partial_audio, language="en")
            partial_times.append(partial_buffer_ms + (perf_counter() - started) * 1_000)
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

        base_report.update(
            {
                "status": "passed",
                "model_load_ms": round(load_ms, 3),
                "sample_count": base_report["iterations"],
                "first_partial_after_onset_ms": summary(partial_times),
                "finalization_ms": summary(final_times),
                "utterance_duration_seconds": round(utterance_duration_seconds, 3),
                "final_real_time_factor": round(
                    (final_times[0] / 1_000) / utterance_duration_seconds, 4
                ),
                "confidence_reported": False,
            }
        )
        base_report["target_pass"] = (
            base_report["first_partial_after_onset_ms"]["p50_ms"] <= 500.0
            and base_report["finalization_ms"]["p50_ms"] <= 900.0
        )
        _write_report(output, base_report)
        print(json.dumps(base_report, indent=2, sort_keys=True))
        return 0
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
