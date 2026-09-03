"""Local audio capture and automatic speech recognition boundaries."""

from .adapters import (
    DEFAULT_ASR_ADAPTER_ID,
    DEFAULT_ASR_MODEL_ID,
    DeterministicFakeASRAdapter,
    FasterWhisperASRAdapter,
)
from .audio import (
    ASR_CHANNELS,
    ASR_FRAME_DURATION_MS,
    ASR_FRAME_SAMPLES,
    ASR_SAMPLE_RATE,
    DeterministicFakeAudioInput,
    SoundDeviceAudioInput,
)
from .interfaces import ASRAdapter, ASRTranscription, AudioDevice, AudioInputAdapter
from .segmenter import UtteranceSegment, UtteranceSegmenter, VADConfig
from .service import ASRService

__all__ = [
    "ASRAdapter",
    "DEFAULT_ASR_ADAPTER_ID",
    "DEFAULT_ASR_MODEL_ID",
    "ASR_CHANNELS",
    "ASR_FRAME_DURATION_MS",
    "ASR_FRAME_SAMPLES",
    "ASR_SAMPLE_RATE",
    "ASRService",
    "ASRTranscription",
    "AudioDevice",
    "AudioInputAdapter",
    "DeterministicFakeAudioInput",
    "DeterministicFakeASRAdapter",
    "FasterWhisperASRAdapter",
    "SoundDeviceAudioInput",
    "UtteranceSegment",
    "UtteranceSegmenter",
    "VADConfig",
]
