"""Native Decisions contract and failure boundaries; no API traffic."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from presenter_core.decisions import ChoiceDecisionRequest, ChoiceQuestion, DecisionError
from presenter_core.decisions.openai_decisions import (
    OPENAI_DECISIONS_URL,
    OpenAIDecisionsProvider,
    parse_openai_decisions_response,
)


def _request() -> ChoiceDecisionRequest:
    return ChoiceDecisionRequest(
        state={"slide_text": "Approve the proposed launch."},
        questions=(
            ChoiceQuestion(
                "purpose",
                "Choose the purpose.",
                {"decision": "Approval", "unclear": "Insufficient evidence"},
            ),
        ),
    )


def _response() -> dict[str, Any]:
    return {
        "model": "gpt-6-luna",
        "answers": [
            {
                "type": "choice",
                "name": "purpose",
                "choice": "decision",
                "confidence": 0.77,
                "probabilities": [
                    {"value": "unclear", "probability": 0.1},
                    {"value": "decision", "probability": 0.9},
                ],
            }
        ],
    }


def test_native_payload_and_rotating_api_credential() -> None:
    calls: list[tuple[str, dict[str, str], dict[str, Any]]] = []
    credentials = iter(["test-one", "test-two"])

    def poster(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
        assert timeout == 4
        calls.append((url, headers, json.loads(body)))
        return 200, json.dumps(_response()).encode()

    provider = OpenAIDecisionsProvider(credential_resolver=lambda: next(credentials), poster=poster)
    for _ in range(2):
        result = provider.decide(_request())
        assert result.provider_id == "openai_decisions"
        assert result.model_id == "gpt-6-luna"
        assert result.answers["purpose"].confidence == 0.77
        assert result.answers["purpose"].probabilities == {"unclear": 0.1, "decision": 0.9}
    assert calls[0][0] == OPENAI_DECISIONS_URL
    assert calls[0][1]["Authorization"] == "Bearer test-one"
    assert calls[1][1]["Authorization"] == "Bearer test-two"
    assert calls[0][2] == {
        "model": "gpt-6-luna",
        "input": _request().serialized_state(),
        "questions": [
            {
                "type": "choice",
                "name": "purpose",
                "instructions": "Choose the purpose.",
                "choices": [
                    {"value": "decision", "description": "Approval"},
                    {"value": "unclear", "description": "Insufficient evidence"},
                ],
            }
        ],
    }
    assert provider.leaves_machine


@pytest.mark.parametrize(
    "mutation",
    [
        "model",
        "missing",
        "duplicate",
        "unknown",
        "bool",
        "nan",
        "sum",
        "choice",
        "type",
        "confidence",
        "probability_extra",
        "answer_extra",
    ],
)
def test_rejects_invalid_answer_sets(mutation: str) -> None:
    response = _response()
    answer = response["answers"][0]
    if mutation == "model":
        response["model"] = "another-model"
    elif mutation == "missing":
        answer["probabilities"].pop()
    elif mutation == "duplicate":
        answer["probabilities"][1] = copy.deepcopy(answer["probabilities"][0])
    elif mutation == "unknown":
        answer["probabilities"][0]["value"] = "unknown"
    elif mutation == "bool":
        answer["choice"] = True
    elif mutation == "nan":
        answer["probabilities"][0]["probability"] = float("nan")
    elif mutation == "sum":
        answer["probabilities"][0]["probability"] = 0.6
    elif mutation == "choice":
        answer["choice"] = "unknown"
    elif mutation == "type":
        answer["type"] = "score"
    elif mutation == "confidence":
        answer["confidence"] = True
    elif mutation == "probability_extra":
        answer["probabilities"][0]["label"] = "unexpected"
    else:
        answer["explanation"] = "unexpected"
    with pytest.raises(DecisionError) as caught:
        parse_openai_decisions_response(response, _request())
    assert caught.value.code == "DECISION_PROVIDER_MALFORMED_OUTPUT"


def test_refusal_and_duplicate_question_names_are_atomic() -> None:
    request = ChoiceDecisionRequest(
        state={"text": "Example"},
        questions=(
            _request().questions[0],
            ChoiceQuestion("other", "Choose.", {"yes": "Yes", "no": "No"}),
        ),
    )
    response = _response()
    response["answers"].append({"type": "refusal", "name": "other"})
    with pytest.raises(DecisionError, match="declined"):
        parse_openai_decisions_response(response, request)
    response["answers"][1] = copy.deepcopy(response["answers"][0])
    with pytest.raises(DecisionError) as caught:
        parse_openai_decisions_response(response, request)
    assert caught.value.code == "DECISION_PROVIDER_MALFORMED_OUTPUT"


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (302, "DECISION_PROVIDER_REQUEST_FAILED", False),
        (401, "DECISION_PROVIDER_AUTH_FAILED", False),
        (403, "DECISION_PROVIDER_PERMISSION_DENIED", False),
        (429, "DECISION_PROVIDER_RATE_LIMITED", True),
        (503, "DECISION_PROVIDER_UNAVAILABLE", True),
    ],
)
def test_safe_http_errors(status: int, code: str, retryable: bool) -> None:
    provider = OpenAIDecisionsProvider(
        credential_resolver=lambda: "secret",
        poster=lambda *args: (status, b"sensitive server body"),
    )
    with pytest.raises(DecisionError) as caught:
        provider.decide(_request())
    assert caught.value.code == code
    assert caught.value.retryable is retryable
    assert "sensitive" not in str(caught.value)
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [b"{}", b"{", b"x" * 65_537, b'{"model":"gpt-6-luna","model":"gpt-6-luna"}'],
    ids=["empty", "invalid-json", "oversized", "duplicate-key"],
)
def test_rejects_bad_wire_payload(payload: bytes) -> None:
    provider = OpenAIDecisionsProvider(
        credential_resolver=lambda: "test", poster=lambda *args: (200, payload)
    )
    with pytest.raises(DecisionError) as caught:
        provider.decide(_request())
    assert caught.value.code == "DECISION_PROVIDER_MALFORMED_OUTPUT"


def test_unconfigured_key_never_posts() -> None:
    def unexpected(*args: Any) -> tuple[int, bytes]:
        pytest.fail("Unconfigured provider made an HTTP request")

    provider = OpenAIDecisionsProvider(credential_resolver=lambda: None, poster=unexpected)
    with pytest.raises(DecisionError) as caught:
        provider.decide(_request())
    assert caught.value.code == "DECISION_PROVIDER_UNCONFIGURED"


@pytest.mark.parametrize(
    "error,code",
    [
        (TimeoutError("sensitive timeout"), "DECISION_PROVIDER_TIMEOUT"),
        (OSError("sensitive transport detail"), "DECISION_PROVIDER_UNAVAILABLE"),
    ],
)
def test_transport_failures_are_safe(error: Exception, code: str) -> None:
    calls = 0

    def poster(*args: Any) -> tuple[int, bytes]:
        nonlocal calls
        calls += 1
        raise error

    provider = OpenAIDecisionsProvider(credential_resolver=lambda: "test", poster=poster)
    with pytest.raises(DecisionError) as caught:
        provider.decide(_request())
    assert caught.value.code == code
    assert caught.value.retryable is True
    assert "sensitive" not in str(caught.value)
    assert calls == 1


def test_fixed_transport_bounds_and_closes_without_following_redirects(monkeypatch: Any) -> None:
    from presenter_core.decisions.openai_decisions import _post_json

    calls: list[object] = []

    class Response:
        status = 302

        def read(self, size: int) -> bytes:
            calls.append(size)
            return b"redirect"

    class Connection:
        def __init__(self, host: str, *, timeout: float) -> None:
            calls.append((host, timeout))

        def request(self, method: str, path: str, *, body: bytes, headers: dict[str, str]) -> None:
            calls.append((method, path))

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            calls.append("closed")

    monkeypatch.setattr(
        "presenter_core.decisions.openai_decisions.http.client.HTTPSConnection", Connection
    )
    with pytest.raises(ValueError):
        _post_json("https://example.invalid/", {}, b"{}", 4)
    assert calls == []
    assert _post_json(OPENAI_DECISIONS_URL, {}, b"{}", 4) == (302, b"redirect")
    assert calls == [("api.openai.com", 4), ("POST", "/v1/decisions"), 65_537, "closed"]
