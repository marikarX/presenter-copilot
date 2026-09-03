"""Real local ASR acceptance over the checked-in synthetic speech fixture."""

from __future__ import annotations

import argparse
import json
import re
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np

from presenter_core.asr.adapters import FasterWhisperASRAdapter
from presenter_core.errors import CoreDomainError
from presenter_core.storage.paths import AppPaths

FIXTURE_ROOT = Path(__file__).parents[3] / "samples" / "synthetic-deck"
FIXTURE_PATH = FIXTURE_ROOT / "audio" / "speech-fixture.wav"
EXPECTED_TERMS = (
    "three year",
    "eighteen percent",
    "recovery time objective",
    "thirty minutes",
)
EXPECTED_ALTERNATIVES = {
    "three year": ("three year",),
    "eighteen percent": ("eighteen percent", "18 percent"),
    "recovery time objective": ("recovery time objective",),
    "thirty minutes": ("thirty minutes", "30 minutes"),
}


def _model_cache(data_root: Path | None) -> Path:
    paths = AppPaths(data_root)
    candidate = paths.root / "models" / "asr"
    if candidate.exists():
        return paths.asr_model_cache_directory(create=False)
    return candidate


def _read_fixture(path: Path) -> tuple[np.ndarray[Any, Any], float]:
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        frame_count = source.getnframes()
        if channels != 1 or sample_width != 2 or sample_rate != 16_000:
            raise ValueError("fixture must be 16 kHz mono signed 16-bit PCM")
        if frame_count < 1 or frame_count > 16_000 * 60:
            raise ValueError("fixture duration is outside the acceptance bound")
        samples = np.frombuffer(source.readframes(frame_count), dtype="<i2").astype(np.float32)
    return samples / 32_768.0, frame_count / sample_rate


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9% ]+", " ", text.lower()).replace("  ", " ").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run real local ASR acceptance.")
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Optional application data root containing the prepared ASR cache.",
    )
    args = parser.parse_args(argv)
    adapter: FasterWhisperASRAdapter | None = None
    try:
        audio, duration_seconds = _read_fixture(FIXTURE_PATH)
        adapter = FasterWhisperASRAdapter(cache_dir=_model_cache(args.data_root))
        if adapter.model_status() == "not_installed":
            raise CoreDomainError(
                "ASR_MODEL_UNAVAILABLE",
                "Prepare the pinned local ASR model before running acceptance.",
                retryable=True,
            )
        adapter.load_local_model()
        transcription = adapter.transcribe_final(audio, language="en")
        normalized = _normalize(transcription.text)
        matched = [
            term
            for term in EXPECTED_TERMS
            if any(alternative in normalized for alternative in EXPECTED_ALTERNATIVES[term])
        ]
        missing = [term for term in EXPECTED_TERMS if term not in matched]
        report = {
            "status": "passed" if not missing else "failed",
            "fixture_id": "synthetic-asr-speech-v1",
            "fixture_duration_seconds": round(duration_seconds, 3),
            "adapter_id": adapter.id,
            "model_id": adapter.model_id,
            "execution": adapter.execution,
            "transcription": transcription.text,
            "matched_terms": matched,
            "missing_terms": missing,
            "confidence_reported": transcription.confidence is not None,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not missing else 1
    except CoreDomainError as error:
        print(
            json.dumps(
                {
                    "status": "unavailable",
                    "fixture_id": "synthetic-asr-speech-v1",
                    "code": error.code,
                    "message": error.message,
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "error",
                    "fixture_id": "synthetic-asr-speech-v1",
                    "code": "ASR_FIXTURE_INVALID",
                    "message": str(error),
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "status": "error",
                    "fixture_id": "synthetic-asr-speech-v1",
                    "code": "ASR_ACCEPTANCE_FAILED",
                    "message": "The local ASR acceptance run failed.",
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        if adapter is not None:
            adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())
