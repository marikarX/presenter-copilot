"""Native OpenAI Decisions beta, restricted to the application's finite choices."""

from __future__ import annotations

import http.client
import json
import math
import time

from .models import (
    MAX_DECISION_INPUT_BYTES,
    ChoiceAnswer,
    ChoiceDecisionRequest,
    ChoiceDecisionResult,
    CredentialResolver,
    DecisionError,
    JsonPoster,
)

OPENAI_DECISIONS_URL = "https://api.openai.com/v1/decisions"
DEFAULT_OPENAI_DECISIONS_MODEL = "gpt-6-luna"
MAX_RESPONSE_BYTES = 65_536


class OpenAIDecisionsProvider:
    """No endpoint/model override, retries, redirect following, or fallback."""

    id = "openai_decisions"
    locality = "remote"
    model_id = DEFAULT_OPENAI_DECISIONS_MODEL

    def __init__(
        self,
        *,
        credential_resolver: CredentialResolver,
        poster: JsonPoster | None = None,
        timeout_seconds: float = 4.0,
    ) -> None:
        if not callable(credential_resolver):
            raise ValueError("credential_resolver must be callable")
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        self._credential_resolver = credential_resolver
        self._poster = poster or _post_json
        self._timeout = max(0.5, min(float(timeout_seconds), 30.0))

    @property
    def leaves_machine(self) -> bool:
        return True

    def decide(self, request: ChoiceDecisionRequest) -> ChoiceDecisionResult:
        try:
            credential = self._credential_resolver()
        except Exception as error:
            raise DecisionError(
                "DECISION_CREDENTIAL_UNAVAILABLE",
                "The OpenAI API credential could not be read.",
                retryable=True,
            ) from error
        if (
            not isinstance(credential, str)
            or not credential
            or len(credential) > 8_192
            or any(ord(character) < 33 or ord(character) > 126 for character in credential)
        ):
            raise DecisionError(
                "DECISION_PROVIDER_UNCONFIGURED", "Configure an OpenAI API credential."
            )
        body = json.dumps(
            {
                "model": self.model_id,
                "input": request.serialized_state(),
                "questions": [
                    {
                        "type": "choice",
                        "name": question.name,
                        "instructions": question.instructions,
                        "choices": [
                            {"value": value, "description": description}
                            for value, description in question.criteria.items()
                        ],
                    }
                    for question in request.questions
                ],
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(body) > MAX_DECISION_INPUT_BYTES:
            raise DecisionError(
                "DECISION_INPUT_TOO_LARGE", "The native Decisions request exceeds its byte limit."
            )
        started = time.monotonic()
        try:
            status, payload = self._poster(
                OPENAI_DECISIONS_URL,
                {
                    "Authorization": f"Bearer {credential}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                body,
                self._timeout,
            )
        except TimeoutError as error:
            raise DecisionError(
                "DECISION_PROVIDER_TIMEOUT", "OpenAI Decisions timed out.", retryable=True
            ) from error
        except Exception as error:
            raise DecisionError(
                "DECISION_PROVIDER_UNAVAILABLE",
                "OpenAI Decisions could not be reached.",
                retryable=True,
            ) from error
        if isinstance(status, bool) or not isinstance(status, int):
            raise _malformed()
        if status != 200:
            code = {
                401: "DECISION_PROVIDER_AUTH_FAILED",
                402: "DECISION_PROVIDER_QUOTA_EXCEEDED",
                403: "DECISION_PROVIDER_PERMISSION_DENIED",
                429: "DECISION_PROVIDER_RATE_LIMITED",
            }.get(
                status,
                "DECISION_PROVIDER_UNAVAILABLE"
                if status >= 500
                else "DECISION_PROVIDER_REQUEST_FAILED",
            )
            raise DecisionError(
                code,
                "OpenAI Decisions rejected the request. Check API access, credentials and limits.",
                retryable=status == 429 or status >= 500,
            )
        if not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE_BYTES:
            raise _malformed()
        try:
            decoded = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, ValueError, RecursionError) as error:
            raise _malformed() from error
        answers = parse_openai_decisions_response(decoded, request)
        return ChoiceDecisionResult(
            provider_id=self.id,
            model_id=self.model_id,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            answers=answers,
        )

    def close(self) -> None:
        """Each request closes its own transport; no credential is cached."""


def parse_openai_decisions_response(
    payload: object, request: ChoiceDecisionRequest
) -> dict[str, ChoiceAnswer]:
    if (
        not isinstance(payload, dict)
        or payload.get("model") != DEFAULT_OPENAI_DECISIONS_MODEL
        or not isinstance(payload.get("answers"), list)
        or len(payload["answers"]) != len(request.questions)
    ):
        raise _malformed()
    expected = {question.name: question for question in request.questions}
    answers: dict[str, ChoiceAnswer] = {}
    refused = False
    seen: set[str] = set()
    for raw in payload["answers"]:
        if not isinstance(raw, dict):
            raise _malformed()
        name = raw.get("name")
        if not isinstance(name, str) or name not in expected or name in seen:
            raise _malformed()
        seen.add(name)
        if raw.get("type") == "refusal" and set(raw) == {"type", "name"}:
            refused = True
            continue
        if set(raw) != {"type", "name", "choice", "confidence", "probabilities"}:
            raise _malformed()
        question = expected[name]
        choice = raw["choice"]
        if (
            raw["type"] != "choice"
            or not isinstance(choice, str)
            or choice not in question.criteria
        ):
            raise _malformed()
        confidence = _probability(raw["confidence"])
        distribution = raw["probabilities"]
        if not isinstance(distribution, list) or len(distribution) != len(question.criteria):
            raise _malformed()
        probabilities: dict[str, float] = {}
        for item in distribution:
            if not isinstance(item, dict) or set(item) != {"value", "probability"}:
                raise _malformed()
            value = item["value"]
            if (
                not isinstance(value, str)
                or value not in question.criteria
                or value in probabilities
            ):
                raise _malformed()
            probabilities[value] = _probability(item["probability"])
        if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-5):
            raise _malformed()
        # Confidence is separate from the distribution; do not substitute one for the other.
        answers[name] = ChoiceAnswer(name, choice, confidence, probabilities)
    if refused:
        raise DecisionError(
            "DECISION_PROVIDER_REFUSED",
            "OpenAI Decisions declined a question; no decision was saved.",
        )
    return answers


def _probability(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
        or not math.isfinite(value)
    ):
        raise _malformed()
    return float(value)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _malformed() -> DecisionError:
    return DecisionError(
        "DECISION_PROVIDER_MALFORMED_OUTPUT", "OpenAI Decisions returned invalid structured output."
    )


def _post_json(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
    if url != OPENAI_DECISIONS_URL:
        raise ValueError("The OpenAI Decisions endpoint is fixed.")
    connection = http.client.HTTPSConnection("api.openai.com", timeout=timeout)
    try:
        connection.request("POST", "/v1/decisions", body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read(MAX_RESPONSE_BYTES + 1)
    finally:
        connection.close()
