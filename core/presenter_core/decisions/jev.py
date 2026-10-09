"""OpenRouter System One API adapter for Jev's typed choice output."""

from __future__ import annotations

import http.client
import json
import math
import time
from collections.abc import Mapping
from urllib.parse import urlsplit

from .models import (
    ChoiceAnswer,
    ChoiceDecisionRequest,
    ChoiceDecisionResult,
    CredentialResolver,
    DecisionError,
    JsonPoster,
    _resolved_model_id,
)

OPENROUTER_SYSTEMONE_URL = "https://openrouter.ai/api/v1/systemone"
DEFAULT_JEV_MODEL = "typesafe/jev-1.13"
MAX_RESPONSE_BYTES = 65_536
DEFAULT_TIMEOUT_SECONDS = 4.0


class JevDecisionProvider:
    """Use Jev for finite choices; never turn its output into free-form text."""

    id = "openrouter_jev"
    locality = "remote"

    def __init__(
        self,
        *,
        credential_resolver: CredentialResolver,
        model_id: str = DEFAULT_JEV_MODEL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        poster: JsonPoster | None = None,
    ) -> None:
        if not callable(credential_resolver):
            raise ValueError("credential_resolver must be callable")
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 120:
            raise ValueError("model_id must be a bounded non-empty string")
        if any(ord(character) < 33 or ord(character) > 126 for character in model_id):
            raise ValueError("model_id contains unsupported characters")
        self.model_id = model_id.strip()
        self._credential_resolver = credential_resolver
        self._timeout_seconds = max(0.5, min(float(timeout_seconds), 30.0))
        self._poster = poster or _post_json

    @property
    def leaves_machine(self) -> bool:
        return True

    def decide(self, request: ChoiceDecisionRequest) -> ChoiceDecisionResult:
        try:
            credential = self._credential_resolver()
        except Exception as error:
            raise DecisionError(
                "DECISION_CREDENTIAL_UNAVAILABLE",
                "The decision provider credential could not be read.",
                retryable=True,
            ) from error
        if (
            not isinstance(credential, str)
            or not credential
            or len(credential) > 8_192
            or any(ord(character) < 33 or ord(character) > 126 for character in credential)
        ):
            raise DecisionError(
                "DECISION_PROVIDER_UNCONFIGURED",
                "Configure a credential for the Jev decision provider.",
            )

        body = json.dumps(
            request.to_jev_payload(self.model_id),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        started = time.monotonic()
        try:
            status, payload = self._poster(
                OPENROUTER_SYSTEMONE_URL,
                {
                    "Authorization": f"Bearer {credential}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                body,
                self._timeout_seconds,
            )
        except DecisionError:
            raise
        except TimeoutError as error:
            raise DecisionError(
                "DECISION_PROVIDER_TIMEOUT",
                "The decision provider timed out.",
                retryable=True,
            ) from error
        except Exception as error:
            raise DecisionError(
                "DECISION_PROVIDER_UNAVAILABLE",
                "The decision provider could not be reached.",
                retryable=True,
            ) from error

        if isinstance(status, bool) or not isinstance(status, int):
            raise _malformed()
        if status != 200:
            code, message, retryable = _map_status(status)
            raise DecisionError(code, message, retryable=retryable)
        if not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE_BYTES:
            raise DecisionError(
                "DECISION_PROVIDER_MALFORMED_OUTPUT",
                "The decision provider returned an oversized response.",
            )
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DecisionError(
                "DECISION_PROVIDER_MALFORMED_OUTPUT",
                "The decision provider returned malformed structured output.",
            ) from error
        answers = parse_jev_response(decoded, request)
        model_id = _resolved_model_id(decoded.get("model"), self.model_id)
        return ChoiceDecisionResult(
            provider_id=self.id,
            model_id=model_id,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            answers=answers,
        )

    def close(self) -> None:
        """This adapter owns no persistent transport resources."""


def parse_jev_response(
    payload: object,
    request: ChoiceDecisionRequest,
) -> dict[str, ChoiceAnswer]:
    """Validate Jev's selected labels and optional score distributions."""
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
        raise DecisionError(
            "DECISION_PROVIDER_MALFORMED_OUTPUT",
            "The decision provider returned malformed structured output.",
        )
    raw_answers = payload["answers"]
    expected = {question.name: question for question in request.questions}
    if set(raw_answers) != set(expected):
        raise DecisionError(
            "DECISION_PROVIDER_MALFORMED_OUTPUT",
            "The decision provider returned an incomplete or unexpected answer set.",
        )

    answers: dict[str, ChoiceAnswer] = {}
    for name, question in expected.items():
        raw = raw_answers.get(name)
        if (
            not isinstance(raw, dict)
            or set(raw).difference({"type", "choice", "confidence", "probabilities"})
            or raw.get("type") != "choice"
        ):
            raise _malformed()
        choice = raw.get("choice")
        confidence = raw.get("confidence")
        if (
            not isinstance(choice, str)
            or choice not in question.criteria
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            raise _malformed()
        probabilities = _probabilities(raw.get("probabilities"), question.criteria)
        answers[name] = ChoiceAnswer(
            name=name,
            choice=choice,
            confidence=float(confidence),
            probabilities=probabilities,
        )
    return answers


def _probabilities(
    raw: object,
    criteria: Mapping[str, str],
) -> dict[str, float] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw).difference(criteria):
        raise _malformed()
    result: dict[str, float] = {}
    for choice_id, value in raw.items():
        if (
            not isinstance(choice_id, str)
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
        ):
            raise _malformed()
        result[choice_id] = float(value)
    return result


def _malformed() -> DecisionError:
    return DecisionError(
        "DECISION_PROVIDER_MALFORMED_OUTPUT",
        "The decision provider returned malformed structured output.",
    )


def _map_status(status: int) -> tuple[str, str, bool]:
    if status == 401:
        return (
            "DECISION_PROVIDER_AUTH_FAILED",
            "The decision provider credential was rejected.",
            False,
        )
    if status == 402:
        return (
            "DECISION_PROVIDER_QUOTA_EXCEEDED",
            "The decision provider account has no available quota.",
            False,
        )
    if status == 403:
        return (
            "DECISION_PROVIDER_PERMISSION_DENIED",
            "OpenRouter denied access to its System One endpoint. "
            "Check the credential's endpoint permissions.",
            False,
        )
    if status == 429:
        return (
            "DECISION_PROVIDER_RATE_LIMITED",
            "The decision provider is rate limiting requests.",
            True,
        )
    if status >= 500:
        return (
            "DECISION_PROVIDER_UNAVAILABLE",
            "The decision provider is temporarily unavailable.",
            True,
        )
    return (
        "DECISION_PROVIDER_REQUEST_FAILED",
        "The decision provider could not process the request.",
        False,
    )


def _post_json(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> tuple[int, bytes]:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "openrouter.ai"
        or parsed.path != "/api/v1/systemone"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("The Jev endpoint is fixed to OpenRouter's official System One API.")
    connection = http.client.HTTPSConnection(parsed.hostname, timeout=timeout)
    try:
        connection.request("POST", parsed.path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        return response.status, payload
    finally:
        connection.close()
