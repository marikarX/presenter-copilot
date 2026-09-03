"""Local faster-whisper and deterministic ASR implementations."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import numpy as np

from presenter_core.errors import CoreDomainError

from .interfaces import ASRTranscription, AudioFrame

DEFAULT_ASR_MODEL_ID = "Systran/faster-whisper-base.en"
DEFAULT_ASR_ADAPTER_ID = "faster-whisper"
DEFAULT_ASR_DEVICE = "cpu"
DEFAULT_ASR_COMPUTE_TYPE = "int8"
FAKE_ASR_ADAPTER_ID = "deterministic-fake"
MAX_ASR_SEGMENTS = 64
MAX_ADAPTER_TEXT_CHARS = 12_000


class FasterWhisperASRAdapter:
    """Reference local ASR adapter with an explicit, app-owned model cache."""

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        model_id: str = DEFAULT_ASR_MODEL_ID,
        device: str = DEFAULT_ASR_DEVICE,
        compute_type: str = DEFAULT_ASR_COMPUTE_TYPE,
    ) -> None:
        if model_id != DEFAULT_ASR_MODEL_ID:
            raise ValueError("Only the approved M6 reference model is supported.")
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("ASR device must be auto, cpu, or cuda.")
        if compute_type not in {"default", "int8", "float16"}:
            raise ValueError("ASR compute type is not supported.")
        self._cache_dir = Path(cache_dir)
        self._model_dir = self._cache_dir / "base.en"
        self._marker_path = self._model_dir / ".presenter-copilot-model.json"
        self._model_id = model_id
        self._device = device
        self._compute_type = compute_type
        self._model: Any | None = None
        self._load_lock = threading.RLock()

    @property
    def id(self) -> str:
        return DEFAULT_ASR_ADAPTER_ID

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def execution(self) -> dict[str, str]:
        return {"device": self._device, "compute_type": self._compute_type}

    def capabilities(self) -> dict[str, Any]:
        return {
            "local_only": True,
            "languages": ["en"],
            "partial": True,
            "final": True,
            "confidence": False,
        }

    def model_status(self) -> str:
        if self._model is not None:
            return "ready"
        if not self._paths_are_safe(create=False):
            return "unavailable"
        if not self._marker_matches() or not (self._model_dir / "config.json").is_file():
            return "not_installed"
        return "installed"

    def prepare_model(self, progress: Callable[[float | None], None] | None = None) -> None:
        """Explicitly download only the approved model into the shared cache."""
        with self._load_lock:
            try:
                self._paths_are_safe(create=True, raise_on_error=True)
                if self.model_status() in {"installed", "ready"}:
                    progress and progress(1.0)
                    return
                progress and progress(0.0)
                from faster_whisper.utils import download_model  # type: ignore[import-untyped]

                download_model(
                    self._model_id,
                    output_dir=str(self._model_dir),
                    local_files_only=False,
                )
                if not (self._model_dir / "config.json").is_file():
                    raise RuntimeError("the downloaded model did not contain config.json")
                marker = {
                    "model_id": self._model_id,
                    "adapter_id": self.id,
                    "format_version": 1,
                }
                temporary = self._marker_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(marker, separators=(",", ":")), encoding="utf-8")
                os.replace(temporary, self._marker_path)
                progress and progress(1.0)
            except Exception as exc:
                try:
                    if self._marker_path.exists():
                        self._marker_path.unlink()
                except OSError:
                    pass
                raise CoreDomainError(
                    "ASR_MODEL_PREPARE_FAILED",
                    "The approved local ASR model could not be prepared.",
                    retryable=True,
                ) from exc

    def load_local_model(self) -> None:
        with self._load_lock:
            if self._model is not None:
                return
            if not self._paths_are_safe(create=False):
                raise CoreDomainError(
                    "ASR_MODEL_UNAVAILABLE",
                    "The local ASR model cache is not a safe application directory.",
                    retryable=False,
                )
            if self.model_status() == "not_installed":
                raise CoreDomainError(
                    "ASR_MODEL_UNAVAILABLE",
                    "The approved local ASR model is not installed.",
                    retryable=True,
                )
            try:
                from faster_whisper import WhisperModel  # type: ignore[import-untyped]

                self._model = WhisperModel(
                    str(self._model_dir),
                    device=self._device,
                    compute_type=self._compute_type,
                    local_files_only=True,
                )
            except Exception as exc:
                self._model = None
                raise CoreDomainError(
                    "ASR_MODEL_UNAVAILABLE",
                    "The installed local ASR model could not be loaded.",
                    retryable=True,
                ) from exc

    def transcribe_partial(self, audio: AudioFrame, *, language: str) -> ASRTranscription:
        return self._transcribe(audio, language=language, partial=True)

    def transcribe_final(self, audio: AudioFrame, *, language: str) -> ASRTranscription:
        return self._transcribe(audio, language=language, partial=False)

    def close(self) -> None:
        with self._load_lock:
            self._model = None

    def _transcribe(
        self,
        audio: AudioFrame,
        *,
        language: str,
        partial: bool,
    ) -> ASRTranscription:
        if self._model is None:
            raise CoreDomainError("ASR_TRANSCRIBE_FAILED", "The local ASR model is not loaded.")
        try:
            segments, _info = self._model.transcribe(
                np.asarray(audio, dtype=np.float32),
                language=language,
                beam_size=1 if partial else 5,
                best_of=1 if partial else 5,
                condition_on_previous_text=False,
                vad_filter=False,
                without_timestamps=False,
            )
            text_parts: list[str] = []
            for index, segment in enumerate(segments):
                if index >= MAX_ASR_SEGMENTS:
                    break
                text = str(getattr(segment, "text", "")).strip()
                if text:
                    text_parts.append(text)
                if len(" ".join(text_parts)) >= MAX_ADAPTER_TEXT_CHARS:
                    break
            text = " ".join(text_parts).strip()[:MAX_ADAPTER_TEXT_CHARS]
            # faster-whisper's segment scores are not calibrated confidence;
            # leave this optional field empty rather than inventing certainty.
            return ASRTranscription(text=text, confidence=None)
        except CoreDomainError:
            raise
        except Exception as exc:
            raise CoreDomainError(
                "ASR_TRANSCRIBE_FAILED",
                "The local ASR adapter could not transcribe the utterance.",
                retryable=True,
            ) from exc

    def _marker_matches(self) -> bool:
        try:
            marker = json.loads(self._marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return False
        return (
            isinstance(marker, dict)
            and marker.get("model_id") == self._model_id
            and marker.get("adapter_id") == self.id
            and marker.get("format_version") == 1
        )

    def _paths_are_safe(self, *, create: bool, raise_on_error: bool = False) -> bool:
        def invalid() -> bool:
            if raise_on_error:
                raise CoreDomainError(
                    "ASR_MODEL_CACHE_UNSAFE",
                    "The local ASR model cache is not a safe application directory.",
                )
            return False

        if self._cache_dir.is_symlink() or (
            self._cache_dir.exists() and not self._cache_dir.is_dir()
        ):
            return invalid()
        if not self._cache_dir.exists() and not create:
            return True
        if create:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        if not self._cache_dir.is_dir():
            return invalid()
        cache_root = self._cache_dir.resolve()
        if self._model_dir.is_symlink() or (
            self._model_dir.exists() and not self._model_dir.is_dir()
        ):
            return invalid()
        if create:
            self._model_dir.mkdir(exist_ok=True)
        if not self._model_dir.exists():
            return True
        model_root = self._model_dir.resolve()
        if model_root.parent != cache_root:
            return invalid()
        return True


class DeterministicFakeASRAdapter:
    """A local fixture adapter that makes partial/final lifecycle deterministic."""

    def __init__(
        self,
        *,
        partial_texts: Iterable[str] = (),
        final_text: str = "The three year cost drops by eighteen percent.",
        model_installed: bool = True,
        load_error: bool = False,
        confidence: float | None = None,
    ) -> None:
        self._partial_texts = list(partial_texts)
        self._final_text = final_text
        self._model_installed = model_installed
        self._load_error = load_error
        self._confidence = confidence
        self._loaded = False
        self._partial_index = 0
        self.load_count = 0
        self.close_count = 0

    @property
    def id(self) -> str:
        return FAKE_ASR_ADAPTER_ID

    @property
    def model_id(self) -> str:
        return "fixture-asr-v1"

    def capabilities(self) -> dict[str, Any]:
        return {
            "local_only": True,
            "languages": ["en"],
            "partial": True,
            "final": True,
            "confidence": self._confidence is not None,
        }

    def model_status(self) -> str:
        if self._loaded:
            return "ready"
        return "installed" if self._model_installed else "not_installed"

    def prepare_model(self, progress: Callable[[float | None], None] | None = None) -> None:
        if not self._model_installed:
            self._model_installed = True
        progress and progress(1.0)

    def load_local_model(self) -> None:
        self.load_count += 1
        if not self._model_installed or self._load_error:
            raise CoreDomainError(
                "ASR_MODEL_UNAVAILABLE", "The fixture ASR model could not be loaded."
            )
        self._loaded = True

    def transcribe_partial(self, _audio: AudioFrame, *, language: str) -> ASRTranscription:
        if language != "en":
            raise CoreDomainError("ASR_TRANSCRIBE_FAILED", "The fixture supports English only.")
        if not self._loaded:
            raise CoreDomainError("ASR_TRANSCRIBE_FAILED", "The fixture ASR model is not loaded.")
        if not self._partial_texts:
            return ASRTranscription(text="", confidence=None)
        index = min(self._partial_index, len(self._partial_texts) - 1)
        self._partial_index += 1
        return ASRTranscription(text=self._partial_texts[index], confidence=None)

    def transcribe_final(self, _audio: AudioFrame, *, language: str) -> ASRTranscription:
        if language != "en" or not self._loaded:
            raise CoreDomainError("ASR_TRANSCRIBE_FAILED", "The fixture ASR model is not ready.")
        return ASRTranscription(text=self._final_text, confidence=self._confidence)

    def close(self) -> None:
        self._loaded = False
        self.close_count += 1
