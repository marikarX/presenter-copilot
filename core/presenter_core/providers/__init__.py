"""Provider-neutral reasoning contracts and M3 adapters."""

from .fake import DeterministicFakeReasoningProvider
from .models import (
    CandidateOutput,
    ProviderCapabilities,
    ProviderError,
    ProviderHealth,
    QuestionOutput,
    ReasoningProvider,
    ReasoningRequest,
    ReasoningResult,
    validate_provider_output,
)
from .openai import DEFAULT_OPENAI_MODEL, OpenAIReasoningProvider
from .router import ReasoningRoute, ReasoningRouter

__all__ = [
    "CandidateOutput",
    "DEFAULT_OPENAI_MODEL",
    "DeterministicFakeReasoningProvider",
    "OpenAIReasoningProvider",
    "ProviderCapabilities",
    "ProviderError",
    "ProviderHealth",
    "ReasoningProvider",
    "ReasoningRequest",
    "ReasoningResult",
    "ReasoningRoute",
    "ReasoningRouter",
    "QuestionOutput",
    "validate_provider_output",
]
