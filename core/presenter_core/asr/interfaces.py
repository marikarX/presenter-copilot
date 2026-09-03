"""Typed seams between audio capture, segmentation, and local ASR."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

AudioFrame = np.ndarray[Any, Any]
AudioCallback = Callable[[AudioFrame], None]


@dataclass(frozen=True)
class AudioDevice:
    """Safe, renderer-facing metadata for one input device."""

    device_id: str
    display_name: str
    host_api: str
    max_input_channels: int
    default_sample_rate: float
    is_default: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "display_name": self.display_name,
            "host_api": self.host_api,
            "max_input_channels": self.max_input_channels,
            "default_sample_rate": self.default_sample_rate,
            "is_default": self.is_default,
        }


@dataclass(frozen=True)
class ASRTranscription:
    """Text returned by an adapter; confidence is optional by design."""

    text: str
    confidence: float | None = None


class AudioInputAdapter(Protocol):
    """Capture PCM frames without knowing anything about recognition/storage."""

    def list_devices(self) -> list[AudioDevice]: ...

    def open(self, device_id: str | None, callback: AudioCallback) -> None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class ASRAdapter(Protocol):
    """Local speech-recognition adapter with no storage or IPC authority."""

    @property
    def id(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    def capabilities(self) -> dict[str, Any]: ...

    def model_status(self) -> str: ...

    def prepare_model(self, progress: Callable[[float | None], None] | None = None) -> None: ...

    def load_local_model(self) -> None: ...

    def transcribe_partial(self, audio: AudioFrame, *, language: str) -> ASRTranscription: ...

    def transcribe_final(self, audio: AudioFrame, *, language: str) -> ASRTranscription: ...

    def close(self) -> None: ...
