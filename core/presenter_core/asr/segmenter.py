"""Deterministic RMS VAD and bounded utterance segmentation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .audio import ASR_FRAME_DURATION_MS, ASR_FRAME_SAMPLES, ASR_SAMPLE_RATE
from .interfaces import AudioFrame


@dataclass(frozen=True)
class VADConfig:
    """Centralized acoustic and growth limits for the local M6 segmenter."""

    sample_rate: int = ASR_SAMPLE_RATE
    frame_duration_ms: int = ASR_FRAME_DURATION_MS
    speech_start_rms: float = 0.025
    speech_end_rms: float = 0.015
    speech_start_confirmation_ms: int = 120
    end_silence_ms: int = 600
    max_continuous_utterance_ms: int = 35_000

    @property
    def frame_samples(self) -> int:
        return self.sample_rate * self.frame_duration_ms // 1_000

    @property
    def start_confirmation_frames(self) -> int:
        return max(
            1,
            (self.speech_start_confirmation_ms + self.frame_duration_ms - 1)
            // self.frame_duration_ms,
        )

    @property
    def end_silence_frames(self) -> int:
        return max(1, (self.end_silence_ms + self.frame_duration_ms - 1) // self.frame_duration_ms)

    @property
    def max_utterance_frames(self) -> int:
        return max(1, self.max_continuous_utterance_ms // self.frame_duration_ms)


@dataclass(frozen=True)
class UtteranceSegment:
    """One bounded segment of in-memory PCM, never a persisted audio object."""

    audio: AudioFrame
    start_ms: int
    end_ms: int
    forced: bool = False


class UtteranceSegmenter:
    """Use hysteresis and confirmation so short noise does not become speech."""

    def __init__(self, config: VADConfig | None = None) -> None:
        self.config = config or VADConfig()
        self._pending: list[AudioFrame] = []
        self._frames: list[AudioFrame] = []
        self._start_ms: int | None = None
        self._silence_frames = 0
        self._speech_active = False

    @property
    def speech_active(self) -> bool:
        return self._speech_active

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def current_start_ms(self) -> int | None:
        return self._start_ms

    def current_audio(self) -> AudioFrame:
        """Return a bounded copy for a worker decode, never for IPC/storage."""
        if not self._frames:
            return np.asarray([], dtype=np.float32)
        return np.concatenate(self._frames).astype(np.float32, copy=True)

    def process(self, frame: AudioFrame, frame_start_ms: int) -> UtteranceSegment | None:
        bounded = self._bounded_frame(frame)
        if bounded.size == 0:
            return None
        rms = self._rms(bounded)
        frame_end_ms = frame_start_ms + self.config.frame_duration_ms

        if not self._speech_active:
            if rms >= self.config.speech_start_rms:
                self._pending.append(bounded)
                if len(self._pending) >= self.config.start_confirmation_frames:
                    confirmation_start = (
                        frame_start_ms - (len(self._pending) - 1) * self.config.frame_duration_ms
                    )
                    self._speech_active = True
                    self._start_ms = max(0, confirmation_start)
                    self._frames = list(self._pending)
                    self._pending.clear()
                    self._silence_frames = 0
            else:
                self._pending.clear()
            return None

        self._frames.append(bounded)
        if rms <= self.config.speech_end_rms:
            self._silence_frames += 1
        else:
            self._silence_frames = 0

        if len(self._frames) >= self.config.max_utterance_frames:
            return self._take_segment(frame_end_ms, forced=True)
        if self._silence_frames >= self.config.end_silence_frames:
            return self._take_segment(frame_end_ms, forced=False)
        return None

    def flush(self, end_ms: int) -> UtteranceSegment | None:
        if not self._speech_active or not self._frames:
            self._pending.clear()
            return None
        return self._take_segment(
            max(end_ms, (self._start_ms or 0) + self.config.frame_duration_ms)
        )

    def reset(self) -> None:
        self._pending.clear()
        self._frames.clear()
        self._start_ms = None
        self._silence_frames = 0
        self._speech_active = False

    def _take_segment(self, end_ms: int, *, forced: bool = False) -> UtteranceSegment:
        assert self._start_ms is not None
        audio = np.concatenate(self._frames).astype(np.float32, copy=False)
        segment = UtteranceSegment(
            audio=audio,
            start_ms=max(0, self._start_ms),
            end_ms=max(end_ms, self._start_ms),
            forced=forced,
        )
        self.reset()
        return segment

    def _bounded_frame(self, frame: AudioFrame) -> AudioFrame:
        flattened = np.asarray(frame, dtype=np.float32).reshape(-1)
        if flattened.size > max(ASR_FRAME_SAMPLES * 2, self.config.frame_samples * 2):
            flattened = flattened[: max(ASR_FRAME_SAMPLES * 2, self.config.frame_samples * 2)]
        return flattened.copy()

    @staticmethod
    def _rms(frame: AudioFrame) -> float:
        if frame.size == 0:
            return 0.0
        value = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
        return value if np.isfinite(value) else 0.0
