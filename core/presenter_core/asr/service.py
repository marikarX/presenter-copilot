"""Thread-safe local ASR orchestration for Run sessions."""

from __future__ import annotations

import queue
import threading
import uuid
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

import numpy as np

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.limits import (
    ASR_WORKER_JOIN_TIMEOUT_SECONDS,
    MAX_ASR_AUDIO_QUEUE_FRAMES,
    MAX_ASR_FINAL_QUEUE_SEGMENTS,
    MAX_FINAL_UTTERANCE_CHARS,
    MAX_PARTIAL_EVENT_CHARS,
)

from .audio import ASR_SIGNAL_RMS_THRESHOLD, SoundDeviceAudioInput
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


@dataclass(frozen=True)
class _DecodeRequest:
    kind: str
    utterance: _UtteranceState
    audio: AudioFrame
    start_ms: int
    end_ms: int
    generation: int


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
    decoder_worker: threading.Thread | None = None
    decode_condition: threading.Condition | None = None
    final_requests: deque[_DecodeRequest] = field(default_factory=deque)
    partial_request: _DecodeRequest | None = None
    pending_final_retry: _DecodeRequest | None = None
    ingestion_done: threading.Event = field(default_factory=threading.Event)
    decoder_done: threading.Event = field(default_factory=threading.Event)
    decoder_error_code: str | None = None
    partial_error_code: str | None = None
    async_error_reported: bool = False
    stop_attempts: int = 0
    frames_processed: int = 0
    input_signal_detected: bool = False
    ingestion_progress: threading.Event = field(default_factory=threading.Event)
    final_enqueued: threading.Event = field(default_factory=threading.Event)
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
        worker_join_timeout_seconds: float = ASR_WORKER_JOIN_TIMEOUT_SECONDS,
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
        self._closing = False
        if worker_join_timeout_seconds <= 0:
            raise ValueError("worker_join_timeout_seconds must be positive.")
        self._worker_join_timeout_seconds = float(worker_join_timeout_seconds)

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
            if self._active is not None or self._preparing or self._closing:
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
            if self._active is not None or self._preparing or self._closing:
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
            if self._closed or self._closing:
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
            active.decode_condition = threading.Condition(self._lock)
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
            with self._lock:
                self._start_decoder_locked(active)
                worker = threading.Thread(
                    target=self._ingestion_loop,
                    args=(active,),
                    name="presenter-copilot-asr-ingestion",
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
            active.stop_attempts += 1
            active.partial_request = None
            condition = active.decode_condition
            if condition is not None:
                condition.notify_all()
            # A failed final is retained for an explicit retry.  Do not retry
            # it from the same stop call: the first failure must leave the
            # ownership boundary observably unresolved.
            if (
                active.stop_attempts > 1
                and active.pending_final_retry is not None
                and not self._thread_alive(active.decoder_worker)
                and active.fatal_error_code != "ASR_BACKPRESSURE"
            ):
                self._restart_decoder_locked(active)
            worker = active.worker
            decoder_worker = active.decoder_worker

        cleanup_error: CoreDomainError | None = None
        deadline = monotonic() + self._worker_join_timeout_seconds
        try:
            self._audio.stop()
        except CoreDomainError as error:
            cleanup_error = error
        except Exception:
            cleanup_error = CoreDomainError(
                "ASR_CAPTURE_FAILED",
                "The input device could not stop cleanly; retry cleanup is safe.",
                retryable=True,
            )
        for thread in (worker, decoder_worker):
            if thread is None or thread is threading.current_thread():
                continue
            remaining = max(0.0, deadline - monotonic())
            if remaining <= 0:
                break
            thread.join(timeout=remaining)

        with self._lock:
            alive = [
                thread
                for thread in (active.worker, active.decoder_worker)
                if self._thread_alive(thread)
            ]
            unresolved_final = (
                active.pending_final_retry is not None
                or bool(active.final_requests)
                or active.utterance is not None
            )
            fatal_code = active.fatal_error_code
            if alive:
                cleanup_error = cleanup_error or CoreDomainError(
                    "ASR_CAPTURE_FAILED",
                    "The ASR capture or decode worker did not stop within the bounded "
                    "shutdown window.",
                    retryable=True,
                    details={"capture_state": "stopping"},
                )
            elif unresolved_final:
                cleanup_error = cleanup_error or CoreDomainError(
                    "ASR_CAPTURE_FAILED",
                    "The active ASR final has not been durably resolved; retry cleanup "
                    "after the worker is available.",
                    retryable=True,
                )

        # A live worker or unresolved final owns the model and audio handles.
        # In particular, never close an adapter underneath a blocked decode.
        if cleanup_error is not None and (alive or unresolved_final):
            with self._lock:
                self._last_error_code = cleanup_error.code
            raise cleanup_error

        release_error: CoreDomainError | None = cleanup_error
        try:
            self._audio.close()
        except CoreDomainError as error:
            release_error = release_error or error
        except Exception:
            release_error = release_error or CoreDomainError(
                "ASR_CAPTURE_FAILED",
                "The input device could not be released cleanly.",
                retryable=True,
            )
        try:
            active.adapter.close()
        except Exception:
            release_error = release_error or CoreDomainError(
                "ASR_CAPTURE_FAILED",
                "The local ASR model could not be released cleanly.",
                retryable=True,
            )
        with self._lock:
            if release_error is None and self._active is active:
                self._active = None
            if release_error is not None:
                self._last_error_code = release_error.code
        if release_error is not None:
            raise release_error
        if fatal_code is not None:
            raise CoreDomainError(
                fatal_code,
                "Microphone capture ended with an error; the capture resources were "
                "released, so retry the Run stop.",
                retryable=True,
            )
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

    def active_owner(self) -> tuple[str, str] | None:
        """Return the Run that still owns capture or model cleanup, if any."""
        with self._lock:
            if self._active is None:
                return None
            return self._active.project_id, self._active.session_id

    def close(self) -> bool:
        """Stop capture and release model/device resources before core shutdown."""
        with self._lock:
            if self._closed:
                return True
            self._closing = True
            active = self._active
        if active is not None:
            try:
                self.stop({"project_id": active.project_id, "session_id": active.session_id})
            except CoreDomainError as error:
                with self._lock:
                    self._last_error_code = error.code
                    self._closing = False
                return False
        with self._lock:
            adapters = list(self._adapters.values())
        release_error: CoreDomainError | None = None
        for adapter in adapters:
            try:
                adapter.close()
            except Exception:
                release_error = release_error or CoreDomainError(
                    "ASR_CAPTURE_FAILED",
                    "A local ASR model could not be released cleanly.",
                    retryable=True,
                )
        try:
            self._audio.close()
        except CoreDomainError as error:
            release_error = release_error or error
        except Exception:
            release_error = release_error or CoreDomainError(
                "ASR_CAPTURE_FAILED",
                "The input device could not be released cleanly.",
                retryable=True,
            )
        with self._lock:
            if release_error is None:
                self._closed = True
            self._closing = False
            if release_error is not None:
                self._last_error_code = release_error.code
        return release_error is None

    def _audio_callback(self, frame: AudioFrame, status: Any = None) -> None:
        # The real-time callback only copies bounded PCM and performs a
        # non-blocking queue operation.  VAD, recognition, storage, and IPC
        # remain outside the capture thread.
        with self._lock:
            active = self._active
            if active is None or not active.accepting:
                return
            if self._capture_status_has_input_loss(status):
                active.backpressure = True
                active.fatal_error_code = "ASR_BACKPRESSURE"
                active.accepting = False
                active.stop_requested.set()
                if active.decode_condition is not None:
                    active.decode_condition.notify_all()
                return
            bounded = np.asarray(frame, dtype=np.float32).reshape(-1)
            if bounded.size == 0:
                return
            bounded = bounded[: self._vad_config.frame_samples * 2].copy()
            try:
                active.frames.put_nowait(bounded)
            except queue.Full:
                active.backpressure = True
                active.fatal_error_code = "ASR_BACKPRESSURE"
                active.accepting = False
                active.stop_requested.set()
                if active.decode_condition is not None:
                    active.decode_condition.notify_all()

    def _ingestion_loop(self, active: _ActiveCapture) -> None:
        """Drain bounded PCM and schedule work without running ASR in VAD."""
        segmenter = UtteranceSegmenter(self._vad_config)
        fatal_code: str | None = None
        try:
            while True:
                with self._lock:
                    if active.fatal_error_code is not None:
                        raise CoreDomainError(
                            active.fatal_error_code,
                            "Audio capture ended with an input or recognition error.",
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
                with self._lock:
                    active.frames_processed += 1
                    active.input_signal_detected = active.input_signal_detected or (
                        self._frame_rms(frame) >= ASR_SIGNAL_RMS_THRESHOLD
                    )
                    active.ingestion_progress.set()
                was_active = segmenter.speech_active
                completed = segmenter.process(frame, frame_start_ms)
                if not was_active and segmenter.speech_active:
                    start_ms = segmenter.current_start_ms or frame_start_ms
                    with self._lock:
                        if self._active is not active:
                            return
                        active.utterance = _UtteranceState(
                            utterance_id=str(uuid.uuid4()),
                            start_ms=max(0, start_ms),
                            slide_ordinal=self._slide_snapshot(
                                active.project_id, active.session_id
                            ),
                        )
                if completed is not None:
                    self._enqueue_final(active, completed)
                elif (
                    segmenter.speech_active
                    and active.utterance is not None
                    and not active.stop_requested.is_set()
                ):
                    self._maybe_emit_partial(active, segmenter, active.frame_clock_ms)

            with self._lock:
                capture_error_code = active.fatal_error_code
                should_report_capture_error = (
                    capture_error_code is not None and not active.async_error_reported
                )
                if should_report_capture_error:
                    active.async_error_reported = True
            if should_report_capture_error:
                self._record_async_error(active, str(capture_error_code), True)
            elif capture_error_code is None:
                completed = segmenter.flush(active.frame_clock_ms)
                if completed is not None and active.utterance is not None:
                    self._enqueue_final(active, completed)
        except CoreDomainError as error:
            fatal_code = error.code
            with self._lock:
                if active.fatal_error_code is None:
                    active.fatal_error_code = error.code
                active.accepting = False
                active.stop_requested.set()
                if active.decode_condition is not None:
                    active.decode_condition.notify_all()
            self._record_async_error(active, error.code, error.retryable)
        except Exception:
            fatal_code = "ASR_CAPTURE_FAILED"
            with self._lock:
                if active.fatal_error_code is None:
                    active.fatal_error_code = fatal_code
                active.accepting = False
                active.stop_requested.set()
                if active.decode_condition is not None:
                    active.decode_condition.notify_all()
            self._record_async_error(active, fatal_code, True)
        finally:
            with self._lock:
                active.ingestion_done.set()
                if active.decode_condition is not None:
                    active.decode_condition.notify_all()

    def _decoder_loop(self, active: _ActiveCapture) -> None:
        """Serialize optional partials and durable finals, with finals first."""
        try:
            while True:
                request = self._next_decode_request(active)
                if request is None:
                    return
                if request.kind == "partial":
                    try:
                        self._decode_partial(active, request)
                    except CoreDomainError as error:
                        self._record_optional_partial_error(active, error.code, error.retryable)
                    except Exception:
                        self._record_optional_partial_error(active, "ASR_TRANSCRIBE_FAILED", True)
                    continue
                try:
                    self._decode_final(active, request)
                except CoreDomainError as error:
                    self._retain_final_for_retry(active, request, error.code, error.retryable)
                    return
                except Exception:
                    self._retain_final_for_retry(active, request, "ASR_TRANSCRIBE_FAILED", True)
                    return
        finally:
            with self._lock:
                active.decoder_done.set()
                if active.decode_condition is not None:
                    active.decode_condition.notify_all()

    def _maybe_emit_partial(
        self,
        active: _ActiveCapture,
        segmenter: UtteranceSegmenter,
        end_ms: int,
    ) -> None:
        utterance = active.utterance
        if utterance is None or not active.accepting or active.stop_requested.is_set():
            return
        if utterance.finalizing or end_ms - utterance.last_partial_end_ms < 500:
            return
        # Copying the current bounded utterance is the only work here.  The
        # adapter call is owned by the serialized decoder worker.
        audio = segmenter.current_audio()
        with self._lock:
            if (
                self._active is not active
                or not active.accepting
                or active.stop_requested.is_set()
                or active.utterance is not utterance
                or utterance.finalizing
            ):
                return
            utterance.generation += 1
            generation = utterance.generation
            utterance.last_partial_end_ms = max(end_ms, utterance.last_partial_end_ms)
            active.partial_request = _DecodeRequest(
                kind="partial",
                utterance=utterance,
                audio=audio,
                start_ms=max(0, utterance.start_ms),
                end_ms=max(end_ms, utterance.start_ms),
                generation=generation,
            )
            if active.decode_condition is not None:
                active.decode_condition.notify_all()

    def _enqueue_final(self, active: _ActiveCapture, segment: UtteranceSegment) -> None:
        utterance = active.utterance
        if utterance is None:
            return
        with self._lock:
            if self._active is not active or active.utterance is not utterance:
                return
            utterance.finalizing = True
            utterance.generation += 1
            request = _DecodeRequest(
                kind="final",
                utterance=utterance,
                audio=segment.audio,
                start_ms=max(0, utterance.start_ms),
                end_ms=max(segment.end_ms, utterance.start_ms),
                generation=utterance.generation,
            )
            # A pending partial is optional and stale as soon as final audio
            # exists.  It can never occupy the bounded final queue.
            active.partial_request = None
            condition = active.decode_condition
            if condition is None:
                raise CoreDomainError(
                    "ASR_CAPTURE_FAILED", "The ASR decode synchronization primitive is missing."
                )
            while len(active.final_requests) >= MAX_ASR_FINAL_QUEUE_SEGMENTS:
                if not self._thread_alive(active.decoder_worker):
                    active.pending_final_retry = request
                    active.fatal_error_code = "ASR_CAPTURE_FAILED"
                    active.accepting = False
                    active.stop_requested.set()
                    condition.notify_all()
                    raise CoreDomainError(
                        "ASR_CAPTURE_FAILED",
                        "The ASR final queue cannot be drained because its decoder stopped.",
                        retryable=True,
                    )
                condition.wait(timeout=0.1)
            active.final_requests.append(request)
            active.final_enqueued.set()
            # The queued request, rather than this mutable pointer, now owns
            # the utterance until it is persisted or retained for retry.
            active.utterance = None
            condition.notify_all()

    def _next_decode_request(self, active: _ActiveCapture) -> _DecodeRequest | None:
        condition = active.decode_condition
        if condition is None:
            return None
        with condition:
            while True:
                if active.final_requests:
                    request = active.final_requests.popleft()
                    condition.notify_all()
                    return request
                if active.stop_requested.is_set():
                    # Partial recognition is disposable once shutdown starts.
                    active.partial_request = None
                    if active.ingestion_done.is_set():
                        return None
                    condition.wait(timeout=0.1)
                    continue
                if active.partial_request is not None:
                    request = active.partial_request
                    active.partial_request = None
                    return request
                condition.wait(timeout=0.1)

    def _decode_partial(self, active: _ActiveCapture, request: _DecodeRequest) -> None:
        result = active.adapter.transcribe_partial(request.audio, language=active.config.language)
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
                or active.utterance is not request.utterance
                or request.generation != request.utterance.generation
                or not active.accepting
                or active.stop_requested.is_set()
                or request.utterance.finalizing
            ):
                return
        self._emit(
            "asr.partial",
            {
                "session_id": active.session_id,
                "utterance_id": request.utterance.utterance_id,
                "text": text,
                "start_ms": request.start_ms,
                "end_ms": request.end_ms,
                "is_final": False,
            },
        )

    def _decode_final(self, active: _ActiveCapture, request: _DecodeRequest) -> None:
        result = active.adapter.transcribe_final(request.audio, language=active.config.language)
        text = result.text.strip()
        if not text:
            with self._lock:
                if active.pending_final_retry is request:
                    active.pending_final_retry = None
                if active.decoder_error_code is not None:
                    active.decoder_error_code = None
                if (
                    active.fatal_error_code is not None
                    and active.fatal_error_code != "ASR_BACKPRESSURE"
                ):
                    active.fatal_error_code = None
                if active.decode_condition is not None:
                    active.decode_condition.notify_all()
            return
        if len(text) > MAX_FINAL_UTTERANCE_CHARS:
            raise CoreDomainError(
                "ASR_TRANSCRIBE_FAILED",
                "The local ASR final exceeded the safe transcript bound.",
            )
        slide_ordinal = self._persist_final(
            active.project_id,
            active.session_id,
            request.utterance.utterance_id,
            text,
            request.start_ms,
            request.end_ms,
            result.confidence,
            request.utterance.slide_ordinal,
        )
        payload: dict[str, Any] = {
            "session_id": active.session_id,
            "utterance_id": request.utterance.utterance_id,
            "text": text,
            "start_ms": request.start_ms,
            "end_ms": request.end_ms,
            "is_final": True,
        }
        if result.confidence is not None:
            payload["confidence"] = result.confidence
        if slide_ordinal is not None:
            payload["slide_ordinal"] = slide_ordinal
        # _persist_final commits before this event is emitted.
        self._emit("asr.final", payload)
        with self._lock:
            if active.pending_final_retry is request:
                active.pending_final_retry = None
            active.decoder_error_code = None
            if (
                active.fatal_error_code is not None
                and active.fatal_error_code != "ASR_BACKPRESSURE"
            ):
                active.fatal_error_code = None
            if active.decode_condition is not None:
                active.decode_condition.notify_all()

    def _retain_final_for_retry(
        self, active: _ActiveCapture, request: _DecodeRequest, code: str, retryable: bool
    ) -> None:
        with self._lock:
            active.pending_final_retry = request
            active.decoder_error_code = code
            active.fatal_error_code = code
            active.accepting = False
            active.stop_requested.set()
            active.partial_request = None
            if active.decode_condition is not None:
                active.decode_condition.notify_all()
        self._record_async_error(active, code, retryable)

    def _record_optional_partial_error(
        self, active: _ActiveCapture, code: str, retryable: bool
    ) -> None:
        with self._lock:
            active.partial_error_code = code
            self._last_error_code = code
        self._emit_device_error(active, code, retryable)

    def _start_decoder_locked(self, active: _ActiveCapture) -> None:
        decoder = threading.Thread(
            target=self._decoder_loop,
            args=(active,),
            name="presenter-copilot-asr-decoder",
            daemon=True,
        )
        active.decoder_worker = decoder
        active.decoder_done.clear()
        decoder.start()

    def _restart_decoder_locked(self, active: _ActiveCapture) -> None:
        if self._thread_alive(active.decoder_worker):
            return
        if active.pending_final_retry is not None:
            active.final_requests.appendleft(active.pending_final_retry)
            active.pending_final_retry = None
        if not active.final_requests:
            return
        active.decoder_error_code = None
        if active.fatal_error_code != "ASR_BACKPRESSURE":
            active.fatal_error_code = None
        self._start_decoder_locked(active)

    @staticmethod
    def _thread_alive(thread: threading.Thread | None) -> bool:
        return thread is not None and thread.is_alive()

    @staticmethod
    def _capture_status_has_input_loss(status: Any) -> bool:
        if status is None:
            return False
        for name in (
            "input_overflow",
            "input_overflowed",
            "input_underflow",
            "input_underflowed",
        ):
            try:
                if bool(getattr(status, name, False)):
                    return True
            except Exception:
                continue
        rendered = str(status).casefold()
        return "input" in rendered and any(
            marker in rendered for marker in ("overflow", "underflow", "dropped", "loss")
        )

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
        input_frames_received = active.frames_processed if active is not None else 0
        if active is None or input_frames_received == 0:
            input_signal_state = "unknown"
        else:
            input_signal_state = "detected" if active.input_signal_detected else "silent"
        capture_state = "running" if active is not None and active.accepting else "stopped"
        if active is not None and (
            self._thread_alive(active.worker)
            or self._thread_alive(active.decoder_worker)
            or active.pending_final_retry is not None
            or bool(active.final_requests)
            or active.utterance is not None
        ):
            capture_state = "running" if active.accepting else "stopping"
        return {
            "adapter_id": adapter.id,
            "model_id": adapter.model_id,
            "model_status": model_status,
            "device": device,
            "capture_state": capture_state,
            "session_id": active.session_id if active is not None else None,
            "language": self._configuration.language,
            "input_signal_state": input_signal_state,
            "input_frames_received": input_frames_received,
            "last_error_code": self._last_error_code,
            "config": self._configuration.to_dict(),
            "capabilities": adapter.capabilities(),
        }

    def _abort_start(self, active: _ActiveCapture) -> None:
        with self._lock:
            active.accepting = False
            active.stop_requested.set()
            if active.decode_condition is not None:
                active.decode_condition.notify_all()
        try:
            self._audio.stop()
        except Exception:
            pass
        deadline = monotonic() + self._worker_join_timeout_seconds
        for worker in (active.worker, active.decoder_worker):
            if worker is None or worker is threading.current_thread():
                continue
            remaining = max(0.0, deadline - monotonic())
            if remaining <= 0:
                break
            worker.join(timeout=remaining)
        if self._thread_alive(active.worker) or self._thread_alive(active.decoder_worker):
            with self._lock:
                self._last_error_code = "ASR_CAPTURE_FAILED"
            return
        try:
            self._audio.close()
        except Exception:
            with self._lock:
                self._last_error_code = "ASR_CAPTURE_FAILED"
            return
        try:
            active.adapter.close()
        except Exception:
            with self._lock:
                self._last_error_code = "ASR_CAPTURE_FAILED"
            return
        with self._lock:
            if self._active is active:
                self._active = None

    def _record_async_error(self, active: _ActiveCapture, code: str, retryable: bool) -> None:
        with self._lock:
            self._last_error_code = code
            active.async_error_reported = True
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
    def _frame_rms(frame: AudioFrame) -> float:
        if frame.size == 0:
            return 0.0
        value = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
        return value if np.isfinite(value) else 0.0

    @staticmethod
    def _required_id(params: dict[str, Any], field: str) -> str:
        value = params.get(field)
        if not isinstance(value, str) or not value:
            raise invalid_request(f"{field} must be a UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise invalid_request(f"{field} must be a UUID.", field=field) from exc
