"""Provider-neutral reasoning contracts and M3 adapters."""

from .execution import ProviderExecutionError, ProviderExecutionResult, ProviderExecutionService
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
    derive_context_manifest,
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
    "ProviderExecutionError",
    "ProviderExecutionResult",
    "ProviderExecutionService",
    "ReasoningProvider",
    "ReasoningRequest",
    "ReasoningResult",
    "derive_context_manifest",
    "ReasoningRoute",
    "ReasoningRouter",
    "QuestionOutput",
    "validate_provider_output",
]
