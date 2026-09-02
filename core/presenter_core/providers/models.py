"""Small provider-neutral request, result, health, and schema types."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from presenter_core.errors import CoreDomainError

QUESTION_FOCUSES = frozenset(
    {
        "decision_rationale",
        "rejected_alternative",
        "assumption",
        "evidence_gap",
        "tradeoff",
        "likely_objection",
        "why_now",
        "risk",
        "exact_fact_conflict",
    }
)
KNOWLEDGE_KINDS = frozenset(
    {
        "fact",
        "decision",
        "rationale",
        "preferred_explanation",
        "analogy",
        "private_note",
        "constraint",
        "objection",
        "answer",
    }
)
MAX_PROVIDER_QUESTION_CHARS = 500
MAX_PROVIDER_CANDIDATE_CHARS = 1_500
MAX_PROVIDER_FOLLOW_UP_CHARS = 500


@dataclass(frozen=True)
class ProviderCapabilities:
    """Renderer-safe capabilities exposed by one provider."""

    structured_outputs: bool
    streaming: bool
    cancellation: bool
    task_types: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "structured_outputs": self.structured_outputs,
            "streaming": self.streaming,
            "cancellation": self.cancellation,
            "task_types": list(self.task_types),
        }


@dataclass(frozen=True)
class ProviderHealth:
    """Safe provider status; it never contains a credential or response body."""

    provider_id: str
    locality: str
    model_id: str
    status: str
    configured: bool
    error_code: str | None = None
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "locality": self.locality,
            "model_id": self.model_id,
            "status": self.status,
            "configured": self.configured,
            "error_code": self.error_code,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class ReasoningRequest:
    """Fully assembled structured context passed to a provider adapter."""

    task_type: str
    question: str | None
    user_input: str | None
    current_slide_summary: str | None
    evidence: tuple[dict[str, Any], ...]
    preferred_user_explanations: tuple[dict[str, Any], ...]
    speaker_evidence: tuple[dict[str, Any], ...]
    style_context: dict[str, Any]
    conflict_metadata: tuple[dict[str, Any], ...]
    style_policy: str
    privacy_mode: str
    output_schema: dict[str, Any]
    latency_budget_ms: int
    application_policy: str
    context_manifest: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-serializable packet with separated trust classes."""
        return {
            "task_type": self.task_type,
            "question": self.question,
            "user_input": self.user_input,
            "current_slide_summary": self.current_slide_summary,
            "application_policy": self.application_policy,
            "untrusted_retrieved_evidence": list(self.evidence),
            "approved_user_knowledge": list(self.preferred_user_explanations),
            "approved_speaker_style_evidence": list(self.speaker_evidence),
            "style_context": self.style_context,
            "conflict_metadata": list(self.conflict_metadata),
            "style_policy": self.style_policy,
            "privacy_mode": self.privacy_mode,
            "latency_budget_ms": self.latency_budget_ms,
        }

    def serialized_input(self) -> str:
        """Serialize the bounded packet for the official provider request."""
        return json.dumps(self.to_payload(), ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class ReasoningResult:
    """Final structured provider output and optional usage metadata."""

    output: dict[str, Any]
    input_token_count: int | None = None
    output_token_count: int | None = None
    latency_ms: int | None = None


@dataclass(frozen=True)
class QuestionOutput:
    question: str
    focus: str


@dataclass(frozen=True)
class CandidateOutput:
    kind: str
    text: str
    follow_up_question: str | None


class ProviderError(CoreDomainError):
    """Structured, renderer-safe provider failure."""


class ReasoningProvider(ABC):
    """Provider boundary: adapters receive context, never storage authority."""

    id: str
    locality: str
    model_id: str

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderHealth:
        raise NotImplementedError

    @abstractmethod
    def generate(self, request: ReasoningRequest) -> ReasoningResult:
        raise NotImplementedError

    def close(self) -> None:
        """Release optional SDK resources."""
        return None


def question_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "question": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_PROVIDER_QUESTION_CHARS,
            },
            "focus": {"type": "string", "enum": sorted(QUESTION_FOCUSES)},
        },
        "required": ["question", "focus"],
    }


def candidate_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": sorted(KNOWLEDGE_KINDS)},
            "text": {"type": "string", "minLength": 1, "maxLength": MAX_PROVIDER_CANDIDATE_CHARS},
            "follow_up_question": {
                "anyOf": [
                    {"type": "string", "maxLength": MAX_PROVIDER_FOLLOW_UP_CHARS},
                    {"type": "null"},
                ]
            },
        },
        "required": ["kind", "text", "follow_up_question"],
    }


def output_schema_for(task_type: str) -> dict[str, Any]:
    if task_type == "teach_question":
        return question_output_schema()
    if task_type == "teach_candidate":
        return candidate_output_schema()
    raise CoreDomainError(
        "PROVIDER_REQUEST_FAILED",
        "The reasoning task is not supported.",
        details={"task_type": task_type},
    )


def validate_provider_output(task_type: str, value: Any) -> dict[str, Any]:
    """Validate provider output again inside the domain boundary."""
    if not isinstance(value, dict):
        raise ProviderError(
            "PROVIDER_MALFORMED_OUTPUT",
            "The reasoning provider returned an invalid structured result.",
        )
    if task_type == "teach_question":
        if set(value) != {"question", "focus"}:
            raise ProviderError(
                "PROVIDER_MALFORMED_OUTPUT",
                "The reasoning provider returned an unsupported question shape.",
            )
        question = value.get("question")
        focus = value.get("focus")
        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question.strip()) > MAX_PROVIDER_QUESTION_CHARS
            or not isinstance(focus, str)
            or focus not in QUESTION_FOCUSES
        ):
            raise ProviderError(
                "PROVIDER_MALFORMED_OUTPUT",
                "The reasoning provider returned an invalid Teach question.",
            )
        return {"question": question.strip(), "focus": focus}
    if task_type == "teach_candidate":
        if set(value) != {"kind", "text", "follow_up_question"}:
            raise ProviderError(
                "PROVIDER_MALFORMED_OUTPUT",
                "The reasoning provider returned an unsupported candidate shape.",
            )
        kind = value.get("kind")
        candidate_text = value.get("text")
        follow_up = value.get("follow_up_question")
        if (
            not isinstance(kind, str)
            or kind not in KNOWLEDGE_KINDS
            or not isinstance(candidate_text, str)
            or not candidate_text.strip()
            or len(candidate_text.strip()) > MAX_PROVIDER_CANDIDATE_CHARS
            or (follow_up is not None and not isinstance(follow_up, str))
            or (
                isinstance(follow_up, str) and len(follow_up.strip()) > MAX_PROVIDER_FOLLOW_UP_CHARS
            )
        ):
            raise ProviderError(
                "PROVIDER_MALFORMED_OUTPUT",
                "The reasoning provider returned an invalid Teach candidate.",
            )
        return {
            "kind": kind,
            "text": candidate_text.strip(),
            "follow_up_question": follow_up.strip() if isinstance(follow_up, str) else None,
        }
    raise ProviderError(
        "PROVIDER_REQUEST_FAILED",
        "The reasoning task is not supported.",
    )
