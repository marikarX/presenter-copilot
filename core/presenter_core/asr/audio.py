"""Windows microphone adapters and deterministic test capture."""

from __future__ import annotations

import math
import threading
from collections.abc import Iterable
from typing import Any, cast

import numpy as np

from presenter_core.errors import CoreDomainError

from .interfaces import AudioCallback, AudioDevice, AudioFrame

ASR_SAMPLE_RATE = 16_000
ASR_CHANNELS = 1
ASR_FRAME_DURATION_MS = 20
ASR_FRAME_SAMPLES = ASR_SAMPLE_RATE * ASR_FRAME_DURATION_MS // 1_000
MAX_AUDIO_FRAME_SAMPLES = ASR_FRAME_SAMPLES * 2
MAX_AUDIO_DEVICES = 32
MAX_DEVICE_NAME_LENGTH = 120


def _safe_text(value: Any, *, fallback: str) -> str:
    text = str(value) if value is not None else fallback
    text = "".join(character for character in text if ord(character) >= 32)
    return text[:MAX_DEVICE_NAME_LENGTH] or fallback


class SoundDeviceAudioInput:
    """Reference microphone input using sounddevice's callback stream."""

    def __init__(
        self,
        *,
        sample_rate: int = ASR_SAMPLE_RATE,
        frame_samples: int = ASR_FRAME_SAMPLES,
        sounddevice_module: Any | None = None,
    ) -> None:
        self._sample_rate = sample_rate
        self._frame_samples = frame_samples
        self._sounddevice = sounddevice_module
        self._stream: Any | None = None
        self._callback: AudioCallback | None = None
        self._lock = threading.RLock()

    def list_devices(self) -> list[AudioDevice]:
        sounddevice = self._module()
        try:
            raw_devices = sounddevice.query_devices()
            host_apis = sounddevice.query_hostapis()
            default_device = sounddevice.default.device
            try:
                # sounddevice exposes this as an _InputOutputPair rather than
                # a built-in tuple on the real backend.
                default_input = int(default_device[0])
            except (IndexError, TypeError, ValueError, AttributeError):
                try:
                    default_input = int(default_device)
                except (TypeError, ValueError):
                    default_input = None
        except Exception as exc:
            raise CoreDomainError(
                "ASR_DEVICE_UNAVAILABLE",
                "Input devices could not be enumerated.",
                retryable=True,
            ) from exc

        devices: list[AudioDevice] = []
        for index, raw in enumerate(raw_devices):
            try:
                input_channels = max(0, int(raw.get("max_input_channels", 0)))
                if input_channels < ASR_CHANNELS:
                    continue
                host_api_index = int(raw.get("hostapi", -1))
                host_name = (
                    host_apis[host_api_index].get("name", "unknown")
                    if 0 <= host_api_index < len(host_apis)
                    else "unknown"
                )
                sample_rate = float(raw.get("default_samplerate", self._sample_rate))
                if not math.isfinite(sample_rate) or sample_rate <= 0:
                    sample_rate = float(self._sample_rate)
                devices.append(
                    AudioDevice(
                        device_id=str(index),
                        display_name=_safe_text(raw.get("name"), fallback=f"Input device {index}"),
                        host_api=_safe_text(host_name, fallback="unknown"),
                        max_input_channels=min(input_channels, 64),
                        default_sample_rate=round(sample_rate, 3),
                        is_default=index == default_input,
                    )
                )
            except (TypeError, ValueError, AttributeError):
                continue
            if len(devices) >= MAX_AUDIO_DEVICES:
                break
        return devices

    def open(self, device_id: str | None, callback: AudioCallback) -> None:
        if not callable(callback):
            raise CoreDomainError("ASR_CAPTURE_FAILED", "The audio callback is invalid.")
        with self._lock:
            if self._stream is not None:
                raise CoreDomainError("ASR_ALREADY_RUNNING", "Audio capture is already open.")
            devices = self.list_devices()
            selected = self._select_device(devices, device_id)
            sounddevice = self._module()
            try:
                self._stream = sounddevice.InputStream(
                    samplerate=self._sample_rate,
                    blocksize=self._frame_samples,
                    device=int(selected.device_id),
                    channels=ASR_CHANNELS,
                    dtype="float32",
                    callback=self._on_stream_callback,
                    start=False,
                )
                self._callback = callback
            except CoreDomainError:
                raise
            except Exception as exc:
                self._stream = None
                self._callback = None
                raise CoreDomainError(
                    "ASR_DEVICE_UNAVAILABLE",
                    "The selected input device could not be opened.",
                    retryable=True,
                    details={"device": selected.to_dict()},
                ) from exc

    def start(self) -> None:
        with self._lock:
            if self._stream is None:
                raise CoreDomainError("ASR_CAPTURE_FAILED", "Audio capture is not open.")
            try:
                self._stream.start()
            except Exception as exc:
                raise CoreDomainError(
                    "ASR_CAPTURE_FAILED",
                    "The selected input device could not start.",
                    retryable=True,
                ) from exc

    def stop(self) -> None:
        with self._lock:
            stream = self._stream
            if stream is None:
                return
            try:
                stream.stop()
            except Exception as exc:
                raise CoreDomainError(
                    "ASR_CAPTURE_FAILED",
                    "The input device could not stop cleanly.",
                    retryable=True,
                ) from exc

    def close(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
            self._callback = None
            if stream is None:
                return
            try:
                stream.close()
            except Exception as exc:
                raise CoreDomainError(
                    "ASR_CAPTURE_FAILED",
                    "The input device could not be released cleanly.",
                    retryable=True,
                ) from exc

    def _on_stream_callback(self, indata: Any, _frames: int, _time_info: Any, _status: Any) -> None:
        # Keep this callback deliberately boring: bounded copy, enqueue, return.
        callback = self._callback
        if callback is None:
            return
        try:
            frame = np.asarray(indata, dtype=np.float32).reshape(-1)
            if frame.size == 0:
                return
            callback(frame[:MAX_AUDIO_FRAME_SAMPLES].copy())
        except Exception:
            # The worker owns error reporting.  Never let a callback exception
            # destabilize PortAudio's real-time thread.
            return

    def _module(self) -> Any:
        if self._sounddevice is not None:
            return self._sounddevice
        try:
            import sounddevice  # type: ignore[import-untyped]
        except ImportError as exc:
            raise CoreDomainError(
                "ASR_DEVICE_UNAVAILABLE",
                "The local microphone backend is not installed.",
                retryable=False,
            ) from exc
        self._sounddevice = sounddevice
        return sounddevice

    @staticmethod
    def _select_device(devices: list[AudioDevice], device_id: str | None) -> AudioDevice:
        if not devices:
            raise CoreDomainError(
                "ASR_DEVICE_UNAVAILABLE",
                "No usable input device is available.",
                retryable=True,
            )
        if device_id is not None:
            selected = next((device for device in devices if device.device_id == device_id), None)
            if selected is None:
                raise CoreDomainError(
                    "ASR_DEVICE_UNAVAILABLE",
                    "The selected input device is unavailable.",
                    retryable=True,
                )
            return selected
        return next((device for device in devices if device.is_default), devices[0])


class DeterministicFakeAudioInput:
    """Fixture input; it never opens hardware and emits only caller-fed frames."""

    def __init__(self, devices: Iterable[AudioDevice] | None = None) -> None:
        self._devices = list(
            devices
            or [
                AudioDevice(
                    device_id="fake-microphone",
                    display_name="Deterministic test microphone",
                    host_api="fixture",
                    max_input_channels=1,
                    default_sample_rate=float(ASR_SAMPLE_RATE),
                    is_default=True,
                )
            ]
        )[:MAX_AUDIO_DEVICES]
        self._callback: AudioCallback | None = None
        self._opened_device: str | None = None
        self._started = False
        self._lock = threading.RLock()
        self.start_count = 0
        self.stop_count = 0
        self.close_count = 0

    @property
    def started(self) -> bool:
        with self._lock:
            return self._started

    def list_devices(self) -> list[AudioDevice]:
        return list(self._devices)

    def open(self, device_id: str | None, callback: AudioCallback) -> None:
        with self._lock:
            selected = (
                next((device for device in self._devices if device.device_id == device_id), None)
                if device_id is not None
                else next((device for device in self._devices if device.is_default), None)
            )
            if selected is None:
                raise CoreDomainError(
                    "ASR_DEVICE_UNAVAILABLE", "The selected input device is unavailable."
                )
            if self._callback is not None:
                raise CoreDomainError("ASR_ALREADY_RUNNING", "Audio capture is already open.")
            self._opened_device = selected.device_id
            self._callback = callback

    def start(self) -> None:
        with self._lock:
            if self._callback is None:
                raise CoreDomainError("ASR_CAPTURE_FAILED", "Audio capture is not open.")
            self._started = True
            self.start_count += 1

    def stop(self) -> None:
        with self._lock:
            self._started = False
            self.stop_count += 1

    def close(self) -> None:
        with self._lock:
            self._started = False
            self._opened_device = None
            self._callback = None
            self.close_count += 1

    def feed(self, frame: AudioFrame) -> None:
        with self._lock:
            callback = self._callback if self._started else None
        if callback is None:
            return
        bounded = np.asarray(frame, dtype=np.float32).reshape(-1)[:MAX_AUDIO_FRAME_SAMPLES].copy()
        if bounded.size:
            callback(cast(AudioFrame, bounded))

    def feed_frames(self, frames: Iterable[AudioFrame]) -> None:
        for frame in frames:
            self.feed(frame)
