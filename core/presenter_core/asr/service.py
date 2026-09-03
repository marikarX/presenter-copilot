"""Thread-safe local ASR orchestration for Run sessions."""

from __future__ import annotations

import queue
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

import numpy as np

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import (
    ASR_WORKER_JOIN_TIMEOUT_SECONDS,
    MAX_ASR_AUDIO_QUEUE_FRAMES,
    MAX_FINAL_UTTERANCE_CHARS,
    MAX_PARTIAL_EVENT_CHARS,
)

from .audio import SoundDeviceAudioInput
from .interfaces import ASRAdapter, AudioDevice, AudioFrame, AudioInputAdapter
from .segmenter import UtteranceSegment, UtteranceSegmenter, VADConfig

EventSink = Callable[[str, dict[str, Any]], None]
SessionValidator = Callable[[str, str], dict[str, Any]]
FinalPersistence = Callable[[str, str, str, str, int, int, float | None, int | None], int | None]
SlideSnapshot = Callable[[str, str], int | None]


@dataclass(frozen=True)
class ASRConfiguration:
    adapter_id: str
    model_id: str
    language: str = "en"
    device_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "model_id": self.model_id,
            "language": self.language,
            "device_id": self.device_id,
        }


@dataclass
class _UtteranceState:
    utterance_id: str
    start_ms: int
    slide_ordinal: int | None
    last_partial_end_ms: int = -500
    generation: int = 0
    finalizing: bool = False


@dataclass
class _ActiveCapture:
    project_id: str
    session_id: str
    adapter: ASRAdapter
    device: AudioDevice
    config: ASRConfiguration
    frames: queue.Queue[AudioFrame] = field(
        default_factory=lambda: queue.Queue(maxsize=MAX_ASR_AUDIO_QUEUE_FRAMES)
    )
    stop_requested: threading.Event = field(default_factory=threading.Event)
    accepting: bool = True
    backpressure: bool = False
    fatal_error_code: str | None = None
    utterance: _UtteranceState | None = None
    frame_clock_ms: int = 0
    worker: threading.Thread | None = None
    started_monotonic: float = field(default_factory=monotonic)


class ASRService:
    """Own one local microphone stream and one recognition worker at a time."""

    def __init__(
        self,
        *,
        audio_input: AudioInputAdapter | None = None,
        adapters: Mapping[str, ASRAdapter],
        session_validator: SessionValidator,
        persist_final: FinalPersistence,
        slide_snapshot: SlideSnapshot,
        event_sink: EventSink | None = None,
        vad_config: VADConfig | None = None,
    ) -> None:
        if not adapters:
            raise ValueError("At least one ASR adapter is required.")
        self._audio = audio_input or SoundDeviceAudioInput()
        # The adapter's own id is canonical; callers cannot alias a model to a
        # different renderer-facing id by choosing an arbitrary mapping key.
        self._adapters = {adapter.id: adapter for adapter in adapters.values()}
        self._session_validator = session_validator
        self._persist_final = persist_final
        self._slide_snapshot = slide_snapshot
        self._event_sink = event_sink
        self._vad_config = vad_config or VADConfig()
        first_adapter = next(iter(self._adapters.values()))
        self._configuration = ASRConfiguration(
            adapter_id=first_adapter.id,
            model_id=first_adapter.model_id,
        )
        self._lock = threading.RLock()
        self._active: _ActiveCapture | None = None
        self._preparing = False
        self._last_error_code: str | None = None
        self._closed = False

    @property
    def audio_input(self) -> AudioInputAdapter:
        """Expose the injected capture seam to deterministic integration tests."""
        return self._audio

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        self._event_sink = event_sink

    def list_devices(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        try:
            devices = self._audio.list_devices()
        except CoreDomainError:
            raise
        except Exception as exc:
            raise CoreDomainError(
                "ASR_DEVICE_UNAVAILABLE",
                "Input devices could not be enumerated.",
                retryable=True,
            ) from exc
        return {"devices": [device.to_dict() for device in devices[:32]]}

    def configure(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"device_id", "adapter_id", "model_id", "language"})
        with self._lock:
            if self._active is not None or self._preparing:
                raise CoreDomainError(
                    "ASR_BUSY",
                    "Audio, model, and device configuration cannot change while Run is listening.",
                    retryable=True,
                )
            adapter_id = params.get("adapter_id", self._configuration.adapter_id)
            if not isinstance(adapter_id, str) or adapter_id not in self._adapters:
                raise invalid_request("adapter_id is not supported.", field="adapter_id")
            adapter = self._adapters[adapter_id]
            model_id = params.get("model_id", adapter.model_id)
            if not isinstance(model_id, str) or model_id != adapter.model_id:
                raise invalid_request(
                    "model_id must name the core-approved model for adapter_id.",
                    field="model_id",
                )
            language = params.get("language", self._configuration.language)
            if language != "en":
                raise invalid_request("Only English ASR is supported in M6.", field="language")
            device_id = params.get("device_id", self._configuration.device_id)
            if device_id is not None and (
                not isinstance(device_id, str) or not device_id or len(device_id) > 120
            ):
                raise invalid_request(
                    "device_id must be a bounded safe device id.", field="device_id"
                )
            self._configuration = ASRConfiguration(
                adapter_id=adapter_id,
                model_id=model_id,
                language=language,
                device_id=device_id,
            )
            self._last_error_code = None
            return {"config": self._configuration.to_dict(), "status": self._status_locked()}

    def prepare_model(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"adapter_id", "model_id"})
        with self._lock:
            if self._active is not None or self._preparing:
                raise CoreDomainError(
                    "ASR_BUSY",
                    "The ASR model cannot change while Run is listening.",
                    retryable=True,
                )
            adapter_id = params.get("adapter_id", self._configuration.adapter_id)
            model_id = params.get("model_id", self._configuration.model_id)
            if (
                adapter_id != self._configuration.adapter_id
                or model_id != self._configuration.model_id
            ):
                raise CoreDomainError(
                    "ASR_BUSY",
                    "Prepare the currently configured ASR adapter and model only.",
                )
            adapter = self._adapters.get(self._configuration.adapter_id)
            if adapter is None:
                raise CoreDomainError("ASR_MODEL_PREPARE_FAILED", "The ASR adapter is unavailable.")
            self._preparing = True

        self._emit(
            "asr.model_loading",
            {"phase": "prepare", "model_id": adapter.model_id, "progress": None},
        )
        try:
            adapter.prepare_model(
                lambda progress: self._emit(
                    "asr.model_loading",
                    {
                        "phase": "prepare",
                        "model_id": adapter.model_id,
                        "progress": progress,
                    },
                )
            )
        except CoreDomainError as error:
            with self._lock:
                self._last_error_code = error.code
            raise
        except Exception as exc:
            with self._lock:
                self._last_error_code = "ASR_MODEL_PREPARE_FAILED"
            raise CoreDomainError(
                "ASR_MODEL_PREPARE_FAILED",
                "The approved local ASR model could not be prepared.",
                retryable=True,
            ) from exc
        finally:
            with self._lock:
                self._preparing = False
        result = self.status({})
        self._emit(
            "asr.ready",
            {
                "adapter_id": adapter.id,
                "model_id": adapter.model_id,
                "session_id": None,
                "capture_state": "stopped",
                "model_status": result["model_status"],
            },
        )
        return result

    def start(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._required_id(params, "project_id")
        session_id = self._required_id(params, "session_id")
        with self._lock:
            if self._closed:
                raise CoreDomainError("ASR_CAPTURE_FAILED", "The local ASR service is shut down.")
            if self._active is not None:
                raise CoreDomainError(
                    "ASR_ALREADY_RUNNING",
                    "Only one Run microphone capture may be active at a time.",
                    retryable=True,
                )
        try:
            self._session_validator(project_id, session_id)
        except CoreDomainError as error:
            raise CoreDomainError(
                "ASR_SESSION_INVALID",
                "ASR requires an active Run session in the selected project.",
                details={"reason": error.code},
            ) from error

        with self._lock:
            adapter = self._adapters[self._configuration.adapter_id]
            device = self._select_device(self._configuration.device_id)
            active = _ActiveCapture(
                project_id=project_id,
                session_id=session_id,
                adapter=adapter,
                device=device,
                config=self._configuration,
            )
            self._active = active

        try:
            if adapter.model_status() == "not_installed":
                raise CoreDomainError(
                    "ASR_MODEL_UNAVAILABLE",
                    "The approved local ASR model is not installed. Prepare it explicitly first.",
                    retryable=True,
                )
            self._emit(
                "asr.model_loading",
                {"phase": "load", "model_id": adapter.model_id, "progress": None},
            )
            adapter.load_local_model()
            self._audio.open(device.device_id, self._audio_callback)
            worker = threading.Thread(
                target=self._worker_loop,
                args=(active,),
                name="presenter-copilot-asr",
                daemon=True,
            )
            active.worker = worker
            worker.start()
            self._audio.start()
        except CoreDomainError as error:
            self._abort_start(active)
            with self._lock:
                self._last_error_code = error.code
            if error.code in {"ASR_DEVICE_UNAVAILABLE", "ASR_CAPTURE_FAILED"}:
                self._emit_device_error(active, error.code, error.retryable)
            raise
        except Exception as exc:
            self._abort_start(active)
            with self._lock:
                self._last_error_code = "ASR_CAPTURE_FAILED"
            self._emit_device_error(active, "ASR_CAPTURE_FAILED", True)
            raise CoreDomainError(
                "ASR_CAPTURE_FAILED",
                "The local microphone capture could not start.",
                retryable=True,
            ) from exc

        result = self.status({})
        self._emit(
            "asr.ready",
            {
                "adapter_id": adapter.id,
                "model_id": adapter.model_id,
                "session_id": session_id,
                "device": device.to_dict(),
                "language": self._configuration.language,
                "capture_state": "running",
            },
        )
        return result

    def stop(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "session_id"})
        project_id = self._required_id(params, "project_id")
        session_id = self._required_id(params, "session_id")
        with self._lock:
            active = self._active
            if active is None:
                return {
                    "project_id": project_id,
                    "session_id": session_id,
                    "stopped": True,
                    "capture_state": "stopped",
                }
            if active.project_id != project_id or active.session_id != session_id:
                raise CoreDomainError(
                    "ASR_SESSION_INVALID",
                    "The requested session does not own the active microphone capture.",
                )
            active.accepting = False
            active.stop_requested.set()
            worker = active.worker

        cleanup_error: CoreDomainError | None = None
        try:
            self._audio.stop()
        except CoreDomainError as error:
            cleanup_error = error
        if worker is not None:
            worker.join(timeout=ASR_WORKER_JOIN_TIMEOUT_SECONDS)
            if worker.is_alive() and cleanup_error is None:
                cleanup_error = CoreDomainError(
                    "ASR_CAPTURE_FAILED",
                    "The ASR worker did not stop within the bounded shutdown window.",
                    retryable=True,
                )
        try:
            self._audio.close()
        except CoreDomainError as error:
            cleanup_error = cleanup_error or error
        try:
            active.adapter.close()
        except Exception:
            cleanup_error = cleanup_error or CoreDomainError(
                "ASR_CAPTURE_FAILED",
                "The local ASR model could not be released cleanly.",
                retryable=True,
            )
        with self._lock:
            if self._active is active:
                self._active = None
            if cleanup_error is not None:
                self._last_error_code = cleanup_error.code
        if cleanup_error is not None:
            raise cleanup_error
        return {
            "project_id": project_id,
            "session_id": session_id,
            "stopped": True,
            "capture_state": "stopped",
        }

    def status(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        with self._lock:
            return self._status_locked()

    def close(self) -> None:
        """Stop capture and release model/device resources before core shutdown."""
        with self._lock:
            self._closed = True
            active = self._active
        if active is not None:
            try:
                self.stop({"project_id": active.project_id, "session_id": active.session_id})
            except CoreDomainError:
                # Shutdown must continue after attempting every release path.
                pass
        with self._lock:
            adapters = list(self._adapters.values())
        for adapter in adapters:
            try:
                adapter.close()
            except Exception:
                continue
        try:
            self._audio.close()
        except Exception:
            pass

    def _audio_callback(self, frame: AudioFrame) -> None:
        # This is the only work allowed in the sounddevice callback: make a
        # bounded copy and enqueue it. Recognition, storage, and IPC stay out.
        with self._lock:
            active = self._active
            if active is None or not active.accepting:
                return
            bounded = np.asarray(frame, dtype=np.float32).reshape(-1)
            if bounded.size == 0:
                return
            bounded = bounded[: self._vad_config.frame_samples * 2].copy()
            try:
                active.frames.put_nowait(bounded)
            except queue.Full:
                active.backpressure = True
                active.accepting = False
                active.stop_requested.set()

    def _worker_loop(self, active: _ActiveCapture) -> None:
        segmenter = UtteranceSegmenter(self._vad_config)
        fatal_code: str | None = None
        try:
            while True:
                if active.backpressure:
                    raise CoreDomainError(
                        "ASR_BACKPRESSURE",
                        "Audio recognition could not keep up with the microphone.",
                        retryable=True,
                    )
                try:
                    frame = active.frames.get(timeout=0.1)
                except queue.Empty:
                    if active.stop_requested.is_set():
                        break
                    continue
                frame_start_ms = active.frame_clock_ms
                active.frame_clock_ms += self._vad_config.frame_duration_ms
                was_active = segmenter.speech_active
                completed = segmenter.process(frame, frame_start_ms)
                if not was_active and segmenter.speech_active:
                    start_ms = segmenter.current_start_ms or frame_start_ms
                    active.utterance = _UtteranceState(
                        utterance_id=str(uuid.uuid4()),
                        start_ms=max(0, start_ms),
                        slide_ordinal=self._slide_snapshot(active.project_id, active.session_id),
                    )
                if completed is not None:
                    self._finalize_segment(active, completed)
                elif segmenter.speech_active and active.utterance is not None:
                    self._maybe_emit_partial(active, segmenter, active.frame_clock_ms)

            completed = segmenter.flush(active.frame_clock_ms)
            if completed is not None and active.utterance is not None:
                self._finalize_segment(active, completed)
        except CoreDomainError as error:
            fatal_code = error.code
            active.fatal_error_code = error.code
            active.accepting = False
            self._record_async_error(active, error.code, error.retryable)
        except Exception:
            fatal_code = "ASR_TRANSCRIBE_FAILED"
            active.fatal_error_code = fatal_code
            active.accepting = False
            self._record_async_error(active, fatal_code, True)
        finally:
            if fatal_code is not None:
                self._cleanup_after_worker_failure(active)

    def _maybe_emit_partial(
        self,
        active: _ActiveCapture,
        segmenter: UtteranceSegmenter,
        end_ms: int,
    ) -> None:
        utterance = active.utterance
        if utterance is None or not active.accepting or utterance.finalizing:
            return
        if end_ms - utterance.last_partial_end_ms < 500:
            return
        with self._lock:
            if self._active is not active or not active.accepting:
                return
            utterance.generation += 1
            generation = utterance.generation
            audio = segmenter.current_audio()
        result = active.adapter.transcribe_partial(audio, language=active.config.language)
        text = result.text.strip()
        if not text:
            return
        if len(text) > MAX_PARTIAL_EVENT_CHARS:
            raise CoreDomainError(
                "ASR_TRANSCRIBE_FAILED",
                "The local ASR partial exceeded the safe event bound.",
            )
        with self._lock:
            if (
                self._active is not active
                or active.utterance is not utterance
                or generation != utterance.generation
                or not active.accepting
            ):
                return
            utterance.last_partial_end_ms = max(end_ms, utterance.last_partial_end_ms)
        self._emit(
            "asr.partial",
            {
                "session_id": active.session_id,
                "utterance_id": utterance.utterance_id,
                "text": text,
                "start_ms": utterance.start_ms,
                "end_ms": max(end_ms, utterance.start_ms),
                "is_final": False,
            },
        )

    def _finalize_segment(self, active: _ActiveCapture, segment: UtteranceSegment) -> None:
        utterance = active.utterance
        if utterance is None:
            return
        with self._lock:
            if self._active is not active:
                return
            utterance.finalizing = True
            utterance.generation += 1
            generation = utterance.generation
        result = active.adapter.transcribe_final(segment.audio, language=active.config.language)
        text = result.text.strip()
        if not text:
            with self._lock:
                if active.utterance is utterance:
                    active.utterance = None
            return
        if len(text) > MAX_FINAL_UTTERANCE_CHARS:
            raise CoreDomainError(
                "ASR_TRANSCRIBE_FAILED",
                "The local ASR final exceeded the safe transcript bound.",
            )
        with self._lock:
            if self._active is not active or active.utterance is not utterance:
                return
            if generation != utterance.generation:
                return
        slide_ordinal = self._persist_final(
            active.project_id,
            active.session_id,
            utterance.utterance_id,
            text,
            max(0, utterance.start_ms),
            max(segment.end_ms, utterance.start_ms),
            result.confidence,
            utterance.slide_ordinal,
        )
        payload: dict[str, Any] = {
            "session_id": active.session_id,
            "utterance_id": utterance.utterance_id,
            "text": text,
            "start_ms": max(0, utterance.start_ms),
            "end_ms": max(segment.end_ms, utterance.start_ms),
            "is_final": True,
        }
        if result.confidence is not None:
            payload["confidence"] = result.confidence
        if slide_ordinal is not None:
            payload["slide_ordinal"] = slide_ordinal
        # _persist_final commits before this event is emitted. The generation
        # check above prevents a stale partial from following a final.
        self._emit("asr.final", payload)
        with self._lock:
            if self._active is active and active.utterance is utterance:
                active.utterance = None

    def _select_device(self, requested_id: str | None) -> AudioDevice:
        try:
            devices = self._audio.list_devices()
        except CoreDomainError:
            raise
        except Exception as exc:
            raise CoreDomainError(
                "ASR_DEVICE_UNAVAILABLE",
                "Input devices could not be enumerated.",
                retryable=True,
            ) from exc
        if requested_id is not None:
            for device in devices:
                if device.device_id == requested_id:
                    return device
            raise CoreDomainError(
                "ASR_DEVICE_UNAVAILABLE",
                "The selected input device is unavailable.",
                retryable=True,
            )
        if not devices:
            return self._no_device()
        return next((device for device in devices if device.is_default), devices[0])

    @staticmethod
    def _no_device() -> AudioDevice:
        raise CoreDomainError(
            "ASR_DEVICE_UNAVAILABLE",
            "No usable input device is available.",
            retryable=True,
        )

    def _status_locked(self) -> dict[str, Any]:
        adapter = self._adapters[self._configuration.adapter_id]
        try:
            model_status = adapter.model_status()
        except Exception:
            model_status = "unavailable"
        active = self._active
        device = active.device.to_dict() if active is not None else None
        capture_state = "running" if active is not None and active.accepting else "stopped"
        if active is not None and active.worker is not None and active.worker.is_alive():
            capture_state = "running" if active.accepting else "stopping"
        return {
            "adapter_id": adapter.id,
            "model_id": adapter.model_id,
            "model_status": model_status,
            "device": device,
            "capture_state": capture_state,
            "session_id": active.session_id if active is not None else None,
            "language": self._configuration.language,
            "last_error_code": self._last_error_code,
            "config": self._configuration.to_dict(),
            "capabilities": adapter.capabilities(),
        }

    def _abort_start(self, active: _ActiveCapture) -> None:
        active.accepting = False
        active.stop_requested.set()
        try:
            self._audio.stop()
        except Exception:
            pass
        worker = active.worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=ASR_WORKER_JOIN_TIMEOUT_SECONDS)
        try:
            self._audio.close()
        except Exception:
            pass
        try:
            active.adapter.close()
        except Exception:
            pass
        with self._lock:
            if self._active is active:
                self._active = None

    def _cleanup_after_worker_failure(self, active: _ActiveCapture) -> None:
        try:
            self._audio.stop()
        except Exception:
            pass
        try:
            self._audio.close()
        except Exception:
            pass
        try:
            active.adapter.close()
        except Exception:
            pass
        with self._lock:
            if self._active is active:
                self._active = None
            self._last_error_code = active.fatal_error_code

    def _record_async_error(self, active: _ActiveCapture, code: str, retryable: bool) -> None:
        with self._lock:
            self._last_error_code = code
        self._emit_device_error(active, code, retryable)

    def _emit_device_error(self, active: _ActiveCapture, code: str, retryable: bool) -> None:
        self._emit(
            "asr.device_error",
            {
                "session_id": active.session_id,
                "error_code": code,
                "retryable": retryable,
                "device": active.device.to_dict(),
            },
        )

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)

    @staticmethod
    def _required_id(params: dict[str, Any], field: str) -> str:
        value = params.get(field)
        if not isinstance(value, str) or not value:
            raise invalid_request(f"{field} must be a UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise invalid_request(f"{field} must be a UUID.", field=field) from exc
