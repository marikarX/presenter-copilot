from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from presenter_core.tools.release_benchmark import _report_reference


def test_release_benchmark_preserves_bounded_asr_event_metrics(tmp_path: Path) -> None:
    report = {
        "status": "failed",
        "benchmark": "m6-local-asr-v2",
        "git_sha": "candidate-sha",
        "target_pass": False,
        "targets": {
            "first_partial_p50_ms": 500.0,
            "first_final_after_speech_end_p50_ms": 900.0,
        },
        "execution": {"device": "cpu", "compute_type": "int8"},
        "iterations": 3,
        "sample_count": 3,
        "first_partial_after_onset_ms": {"p50_ms": 949.093},
        "first_partial_missing_samples": 0,
        "first_partial_measurement": "ASRService event",
        "finalization_ms": {"p50_ms": 365.622},
        "final_event_after_speech_end_ms": {"p50_ms": 2_903.225},
        "final_event_after_vad_completion_ms": {"p50_ms": 2_303.225},
        "final_event_missing_samples": 0,
        "final_event_measurement": "ASRService final event",
        "model_id": "Systran/faster-whisper-base.en",
        "transcription": "private source content must not be copied",
    }
    path = tmp_path / "asr.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    result = _report_reference(path, "candidate-sha")

    assert result["status"] == "failed"
    assert result["first_partial_after_onset_ms"] == {"p50_ms": 949.093}
    assert result["final_event_after_speech_end_ms"] == {"p50_ms": 2_903.225}
    assert result["final_event_after_vad_completion_ms"] == {"p50_ms": 2_303.225}
    assert result["execution"] == {"device": "cpu", "compute_type": "int8"}
    assert "transcription" not in result


def test_release_benchmark_marks_asr_report_from_another_sha_stale(tmp_path: Path) -> None:
    report: dict[str, Any] = {
        "status": "failed",
        "git_sha": "older-sha",
        "first_partial_after_onset_ms": {"p50_ms": 949.093},
    }
    path = tmp_path / "asr.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    result = _report_reference(path, "candidate-sha")

    assert result == {"status": "stale", "report_git_sha": "older-sha"}
