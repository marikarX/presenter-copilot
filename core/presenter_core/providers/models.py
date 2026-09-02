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
MAX_PROVIDER_RATIONALE_CHARS = 1_000
MAX_PROVIDER_FEEDBACK_CHARS = 600
MAX_PROVIDER_MISSING_POINTS = 6
MAX_PROVIDER_EVIDENCE_IDS = 8
MAX_PROVIDER_OBSERVATION_IDS = 8
CHALLENGE_INTENSITIES = frozenset({"normal", "skeptical", "adversarial"})
SOURCE_SUPPORT_STATUSES = frozenset(
    {"supported", "partially_supported", "unsupported", "conflicted"}
)


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
    audience_context: tuple[dict[str, Any], ...] = ()
    challenge_intensity: str | None = None
    prior_question_context: tuple[dict[str, Any], ...] = ()
    grounding_evidence: tuple[dict[str, Any], ...] = ()

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-serializable packet with separated trust classes."""
        evidence_payload = list(self.evidence)
        user_knowledge_payload = list(self.preferred_user_explanations)
        seen_evidence_ids = {
            str(item.get("evidence_id"))
            for item in [*evidence_payload, *user_knowledge_payload]
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
        }
        for item in self.grounding_evidence:
            evidence_id = item.get("evidence_id")
            if not isinstance(evidence_id, str) or evidence_id in seen_evidence_ids:
                continue
            if item.get("source_type") == "user_statement":
                user_knowledge_payload.append(item)
            else:
                evidence_payload.append(item)
            seen_evidence_ids.add(evidence_id)
        return {
            "task_type": self.task_type,
            "question": self.question,
            "user_input": self.user_input,
            "current_slide_summary": self.current_slide_summary,
            "application_policy": self.application_policy,
            "untrusted_retrieved_evidence": evidence_payload,
            "approved_user_knowledge": user_knowledge_payload,
            "approved_speaker_style_evidence": list(self.speaker_evidence),
            "style_context": self.style_context,
            "conflict_metadata": list(self.conflict_metadata),
            "approved_audience_context": list(self.audience_context),
            "challenge_intensity": self.challenge_intensity,
            "prior_question_context": list(self.prior_question_context),
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


def challenge_question_output_schema() -> dict[str, Any]:
    """Strict bounded schema for a project- and audience-grounded question."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "question": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_PROVIDER_QUESTION_CHARS,
            },
            "rationale": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_PROVIDER_RATIONALE_CHARS,
            },
            "evidence_ids": {
                "type": "array",
                "maxItems": MAX_PROVIDER_EVIDENCE_IDS,
                "items": {"type": "string", "minLength": 1, "maxLength": 120},
            },
            "audience_observation_ids": {
                "type": "array",
                "maxItems": MAX_PROVIDER_OBSERVATION_IDS,
                "items": {"type": "string", "minLength": 1, "maxLength": 120},
            },
        },
        "required": ["question", "rationale", "evidence_ids", "audience_observation_ids"],
    }


def challenge_evaluation_output_schema() -> dict[str, Any]:
    """Strict bounded advisory evaluation schema."""
    score = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "feedback": {
                "type": "string",
                "maxLength": MAX_PROVIDER_FEEDBACK_CHARS,
            },
        },
        "required": ["score", "feedback"],
    }
    style_score = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "score": {
                "anyOf": [
                    {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    {"type": "null"},
                ]
            },
            "feedback": {
                "type": "string",
                "maxLength": MAX_PROVIDER_FEEDBACK_CHARS,
            },
        },
        "required": ["score", "feedback"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "correctness": score,
            "directness": score,
            "completeness": score,
            "concision": score,
            "style_match": style_score,
            "source_support": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": sorted(SOURCE_SUPPORT_STATUSES),
                    },
                    "feedback": {
                        "type": "string",
                        "maxLength": MAX_PROVIDER_FEEDBACK_CHARS,
                    },
                },
                "required": ["status", "feedback"],
            },
            "missing_points": {
                "type": "array",
                "maxItems": MAX_PROVIDER_MISSING_POINTS,
                "items": {"type": "string", "minLength": 1, "maxLength": 300},
            },
            "supported_evidence_ids": {
                "type": "array",
                "maxItems": MAX_PROVIDER_EVIDENCE_IDS,
                "items": {"type": "string", "minLength": 1, "maxLength": 120},
            },
        },
        "required": [
            "correctness",
            "directness",
            "completeness",
            "concision",
            "style_match",
            "source_support",
            "missing_points",
            "supported_evidence_ids",
        ],
    }


def output_schema_for(task_type: str) -> dict[str, Any]:
    if task_type == "teach_question":
        return question_output_schema()
    if task_type == "teach_candidate":
        return candidate_output_schema()
    if task_type in {"challenge_question", "challenge_follow_up"}:
        return challenge_question_output_schema()
    if task_type == "challenge_evaluation":
        return challenge_evaluation_output_schema()
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
    if task_type in {"challenge_question", "challenge_follow_up"}:
        return _validate_challenge_question_output(value)
    if task_type == "challenge_evaluation":
        return _validate_challenge_evaluation_output(value)
    raise ProviderError(
        "PROVIDER_REQUEST_FAILED",
        "The reasoning task is not supported.",
    )


def _validate_challenge_question_output(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "question",
        "rationale",
        "evidence_ids",
        "audience_observation_ids",
    }:
        raise ProviderError(
            "CHALLENGE_OUTPUT_INVALID",
            "The reasoning provider returned an unsupported Challenge question shape.",
        )
    question = value.get("question")
    rationale = value.get("rationale")
    evidence_ids = value.get("evidence_ids")
    observation_ids = value.get("audience_observation_ids")
    if (
        not isinstance(question, str)
        or not question.strip()
        or len(question.strip()) > MAX_PROVIDER_QUESTION_CHARS
        or not isinstance(rationale, str)
        or not rationale.strip()
        or len(rationale.strip()) > MAX_PROVIDER_RATIONALE_CHARS
        or not _bounded_string_list(evidence_ids, MAX_PROVIDER_EVIDENCE_IDS, 120)
        or not _bounded_string_list(observation_ids, MAX_PROVIDER_OBSERVATION_IDS, 120)
    ):
        raise ProviderError(
            "CHALLENGE_OUTPUT_INVALID",
            "The reasoning provider returned an invalid Challenge question.",
        )
    if not isinstance(evidence_ids, list) or not isinstance(observation_ids, list):
        raise ProviderError(
            "CHALLENGE_OUTPUT_INVALID",
            "The reasoning provider returned an invalid Challenge question.",
        )
    if len(set(evidence_ids)) != len(evidence_ids) or len(set(observation_ids)) != len(
        observation_ids
    ):
        raise ProviderError(
            "CHALLENGE_OUTPUT_INVALID",
            "The reasoning provider returned duplicate Challenge provenance IDs.",
        )
    return {
        "question": question.strip(),
        "rationale": rationale.strip(),
        "evidence_ids": list(evidence_ids),
        "audience_observation_ids": list(observation_ids),
    }


def _validate_challenge_evaluation_output(value: Any) -> dict[str, Any]:
    required = {
        "correctness",
        "directness",
        "completeness",
        "concision",
        "style_match",
        "source_support",
        "missing_points",
        "supported_evidence_ids",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ProviderError(
            "CHALLENGE_OUTPUT_INVALID",
            "The reasoning provider returned an unsupported Challenge evaluation shape.",
        )
    dimensions: dict[str, dict[str, Any]] = {}
    for name in ("correctness", "directness", "completeness", "concision"):
        dimensions[name] = _validate_score_dimension(value.get(name), name, allow_null=False)
    dimensions["style_match"] = _validate_score_dimension(
        value.get("style_match"), "style_match", allow_null=True
    )
    source_support = value.get("source_support")
    if (
        not isinstance(source_support, dict)
        or set(source_support) != {"status", "feedback"}
        or source_support.get("status") not in SOURCE_SUPPORT_STATUSES
        or not isinstance(source_support.get("feedback"), str)
        or len(source_support["feedback"]) > MAX_PROVIDER_FEEDBACK_CHARS
    ):
        raise ProviderError(
            "CHALLENGE_OUTPUT_INVALID",
            "The reasoning provider returned invalid source-support evaluation data.",
        )
    missing_points = value.get("missing_points")
    supported_ids = value.get("supported_evidence_ids")
    if not _bounded_string_list(missing_points, MAX_PROVIDER_MISSING_POINTS, 300) or not (
        _bounded_string_list(supported_ids, MAX_PROVIDER_EVIDENCE_IDS, 120)
    ):
        raise ProviderError(
            "CHALLENGE_OUTPUT_INVALID",
            "The reasoning provider returned invalid bounded evaluation lists.",
        )
    if not isinstance(missing_points, list) or not isinstance(supported_ids, list):
        raise ProviderError(
            "CHALLENGE_OUTPUT_INVALID",
            "The reasoning provider returned invalid bounded evaluation lists.",
        )
    if len(set(missing_points)) != len(missing_points) or len(set(supported_ids)) != len(
        supported_ids
    ):
        raise ProviderError(
            "CHALLENGE_OUTPUT_INVALID",
            "The reasoning provider returned duplicate evaluation IDs or points.",
        )
    return {
        **dimensions,
        "source_support": {
            "status": source_support["status"],
            "feedback": source_support["feedback"].strip(),
        },
        "missing_points": [item.strip() for item in missing_points],
        "supported_evidence_ids": list(supported_ids),
    }


def _validate_score_dimension(
    value: Any,
    name: str,
    *,
    allow_null: bool,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"score", "feedback"}:
        raise ProviderError("CHALLENGE_OUTPUT_INVALID", f"Invalid {name} evaluation data.")
    score = value.get("score")
    if score is None and allow_null:
        normalized_score = None
    elif isinstance(score, bool) or not isinstance(score, (int, float)) or not 0.0 <= score <= 1.0:
        raise ProviderError("CHALLENGE_OUTPUT_INVALID", f"Invalid {name} score.")
    else:
        normalized_score = float(score)
    feedback = value.get("feedback")
    if not isinstance(feedback, str) or len(feedback.strip()) > MAX_PROVIDER_FEEDBACK_CHARS:
        raise ProviderError("CHALLENGE_OUTPUT_INVALID", f"Invalid {name} feedback.")
    return {"score": normalized_score, "feedback": feedback.strip()}


def _bounded_string_list(value: Any, maximum: int, item_length: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= maximum
        and all(
            isinstance(item, str) and bool(item.strip()) and len(item.strip()) <= item_length
            for item in value
        )
    )
