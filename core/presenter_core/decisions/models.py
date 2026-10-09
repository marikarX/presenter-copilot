"""Shared schemas and validation for bounded choice decisions."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from presenter_core.errors import CoreDomainError

MAX_QUESTIONS = 8
MAX_CHOICES = 32
MAX_STATE_BYTES = 32 * 1024
MAX_DECISION_INPUT_BYTES = 256 * 1024
MAX_INSTRUCTIONS_CHARS = 1_000
MAX_CRITERIA_CHARS = 500
MAX_JSON_DEPTH = 8
MAX_COLLECTION_ITEMS = 1_000
_QUESTION_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CHOICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")


@dataclass(frozen=True)
class ChoiceQuestion:
    """One finite set of user-defined outcomes for an application decision."""

    name: str
    instructions: str
    criteria: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _QUESTION_NAME.fullmatch(self.name):
            raise _invalid("The decision question name is invalid.")
        if (
            not isinstance(self.instructions, str)
            or not self.instructions.strip()
            or len(self.instructions) > MAX_INSTRUCTIONS_CHARS
        ):
            raise _invalid("The decision question instructions are invalid.")
        if not isinstance(self.criteria, Mapping):
            raise _invalid("The decision question must define between 2 and 32 choices.")
        criteria = dict(self.criteria)
        if not 2 <= len(criteria) <= MAX_CHOICES:
            raise _invalid("The decision question must define between 2 and 32 choices.")
        for choice_id, description in criteria.items():
            if not isinstance(choice_id, str) or not _CHOICE_ID.fullmatch(choice_id):
                raise _invalid("The decision choice identifier is invalid.")
            if (
                not isinstance(description, str)
                or not description.strip()
                or len(description) > MAX_CRITERIA_CHARS
            ):
                raise _invalid("The decision choice description is invalid.")
        object.__setattr__(self, "criteria", MappingProxyType(criteria))


@dataclass(frozen=True)
class ChoiceDecisionRequest:
    """A bounded JSON state and one to eight trusted finite-choice questions."""

    state: Mapping[str, Any]
    questions: tuple[ChoiceQuestion, ...]
    _state_json: str = field(init=False, repr=False)
    _serialized_request_json: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.state, Mapping) or not self.state:
            raise _invalid("Decision state must be a non-empty JSON object.")
        if not isinstance(self.questions, tuple) or not 1 <= len(self.questions) <= MAX_QUESTIONS:
            raise _invalid("A decision request must contain between 1 and 8 questions.")
        if any(not isinstance(item, ChoiceQuestion) for item in self.questions):
            raise _invalid("Decision questions must use the typed choice schema.")
        names = [item.name for item in self.questions]
        if len(names) != len(set(names)):
            raise _invalid("Decision question names must be unique.")
        _validate_json_value(self.state)
        try:
            state_json = json.dumps(
                self.state,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as error:
            raise _invalid("Decision state must contain only finite JSON values.") from error
        if len(state_json.encode("utf-8")) > MAX_STATE_BYTES:
            raise _invalid("Decision state exceeds the 32 KiB request limit.")
        object.__setattr__(self, "_state_json", state_json)
        object.__setattr__(self, "state", _freeze_json_value(json.loads(state_json)))
        try:
            serialized = json.dumps(
                self.to_choice_payload(),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as error:
            raise _invalid("Decision input must contain only finite JSON values.") from error
        if len(serialized.encode("utf-8")) > MAX_DECISION_INPUT_BYTES:
            raise _invalid("Decision input exceeds the 256 KiB request limit.")
        object.__setattr__(self, "_serialized_request_json", serialized)

    def serialized_state(self) -> str:
        return self._state_json

    def to_jev_payload(self, model_id: str) -> dict[str, object]:
        """Serialize the shared contract into the Jev-compatible System One shape."""
        if not isinstance(model_id, str) or not model_id or len(model_id) > 120:
            raise _invalid("The decision model identifier is invalid.")
        return {
            "model": model_id,
            "questions": self._questions_payload(),
            "state": json.loads(self._state_json),
        }

    def to_choice_payload(self) -> dict[str, object]:
        """Return the common serialized input shared by structured providers."""
        return {
            "questions": self._questions_payload(),
            "state": json.loads(self._state_json),
        }

    def serialized_request(self) -> str:
        """Return an immutable bounded snapshot for local and Responses adapters."""
        return self._serialized_request_json

    def output_schema(self) -> dict[str, object]:
        """Build a strict output schema whose enum values match the request."""
        properties: dict[str, object] = {}
        for question in self.questions:
            properties[question.name] = {
                "type": "object",
                "properties": {
                    "choice": {
                        "type": "string",
                        "enum": list(question.criteria),
                    }
                },
                "required": ["choice"],
                "additionalProperties": False,
            }
        return {
            "type": "object",
            "properties": properties,
            "required": [question.name for question in self.questions],
            "additionalProperties": False,
        }

    def parse_structured_answers(self, payload: object) -> dict[str, ChoiceAnswer]:
        """Validate a Structured Outputs result against this exact request."""
        if not isinstance(payload, dict):
            raise DecisionError(
                "DECISION_PROVIDER_MALFORMED_OUTPUT",
                "The decision provider returned malformed structured output.",
            )
        expected = {question.name: question for question in self.questions}
        if set(payload) != set(expected):
            raise DecisionError(
                "DECISION_PROVIDER_MALFORMED_OUTPUT",
                "The decision provider returned an incomplete or unexpected answer set.",
            )
        answers: dict[str, ChoiceAnswer] = {}
        for name, question in expected.items():
            raw_answer = payload.get(name)
            if (
                not isinstance(raw_answer, dict)
                or set(raw_answer) != {"choice"}
                or not isinstance(raw_answer.get("choice"), str)
                or raw_answer["choice"] not in question.criteria
            ):
                raise DecisionError(
                    "DECISION_PROVIDER_MALFORMED_OUTPUT",
                    "The decision provider returned an unsupported choice.",
                )
            answers[name] = ChoiceAnswer(name=name, choice=raw_answer["choice"])
        return answers

    def _questions_payload(self) -> dict[str, object]:
        return {
            item.name: {
                "criteria": dict(item.criteria),
                "instructions": item.instructions,
                "type": "choice",
            }
            for item in self.questions
        }


@dataclass(frozen=True)
class ChoiceAnswer:
    """Validated output for one decision question."""

    name: str
    choice: str
    confidence: float | None = None
    probabilities: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _QUESTION_NAME.fullmatch(self.name):
            raise _invalid("The decision answer name is invalid.")
        if not isinstance(self.choice, str) or not _CHOICE_ID.fullmatch(self.choice):
            raise _invalid("The decision answer choice is invalid.")
        if self.confidence is not None and (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(float(self.confidence))
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise _invalid("Decision confidence must be between 0 and 1.")
        if self.probabilities is not None:
            if not isinstance(self.probabilities, Mapping):
                raise _invalid("Decision probabilities must be an object.")
            probabilities = dict(self.probabilities)
            for choice_id, value in probabilities.items():
                if (
                    not isinstance(choice_id, str)
                    or not _CHOICE_ID.fullmatch(choice_id)
                    or isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                ):
                    raise _invalid("Decision probabilities must be between 0 and 1.")
            object.__setattr__(self, "probabilities", MappingProxyType(probabilities))


@dataclass(frozen=True)
class ChoiceDecisionResult:
    """Answers only; providers do not return or execute free-form actions."""

    provider_id: str
    model_id: str
    latency_ms: int
    answers: Mapping[str, ChoiceAnswer]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider_id, str)
            or not self.provider_id
            or len(self.provider_id) > 80
            or not isinstance(self.model_id, str)
            or not self.model_id
            or len(self.model_id) > 120
            or isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, int)
            or self.latency_ms < 0
            or not isinstance(self.answers, Mapping)
            or not self.answers
        ):
            raise _invalid("The decision result metadata is invalid.")
        answers = dict(self.answers)
        if any(
            not isinstance(name, str) or not isinstance(answer, ChoiceAnswer) or name != answer.name
            for name, answer in answers.items()
        ):
            raise _invalid("The decision result contains invalid answers.")
        object.__setattr__(self, "answers", MappingProxyType(answers))


class DecisionProvider(Protocol):
    """Adapter contract separate from text-generating ReasoningProvider."""

    id: str
    model_id: str
    locality: str

    @property
    def leaves_machine(self) -> bool: ...

    def decide(self, request: ChoiceDecisionRequest) -> ChoiceDecisionResult: ...

    def close(self) -> None: ...


class DecisionError(CoreDomainError):
    """Safe decision provider failure with no provider response body."""


CredentialResolver = Callable[[], str | None]
JsonPoster = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]


def _validate_json_value(value: object, *, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise _invalid("Decision state nesting exceeds the allowed depth.")
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and len(value) > MAX_STATE_BYTES:
            raise _invalid("A decision state string exceeds the request limit.")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _invalid("Decision state numbers must be finite.")
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise _invalid("Decision state contains too many object fields.")
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 256:
                raise _invalid("Decision state object keys are invalid.")
            _validate_json_value(child, depth=depth + 1)
        return
    if isinstance(value, (tuple, list)):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise _invalid("Decision state contains too many array items.")
        for child in value:
            _validate_json_value(child, depth=depth + 1)
        return
    raise _invalid("Decision state must contain only finite JSON values.")


def _freeze_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json_value(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json_value(child) for child in value)
    return value


def _invalid(message: str) -> DecisionError:
    return DecisionError("DECISION_REQUEST_INVALID", message)


def _resolved_model_id(value: object, requested: str) -> str:
    """Use provider-reported deployment identity only when safely bounded."""
    if (
        isinstance(value, str)
        and value.strip()
        and len(value) <= 120
        and all(33 <= ord(character) <= 126 for character in value)
    ):
        return value.strip()
    return requested
