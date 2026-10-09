"""Typed choice adapters are bounded and unit-tested without provider traffic."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any

import pytest

from presenter_core.decisions import (
    ChoiceDecisionRequest,
    ChoiceQuestion,
    DecisionError,
    JevDecisionProvider,
    LocalChoiceDecisionProvider,
    OllamaSystemOneDecisionProvider,
    OpenAIFastDecisionProvider,
    OpenAIUltrafastDecisionProvider,
)
from presenter_core.decisions.ollama import _post_json, _read_installed_model_digest
from presenter_core.errors import CoreDomainError
from presenter_core.providers.service import ProviderService
from presenter_core.storage.service import StorageManager


def _request(state: dict[str, Any] | None = None) -> ChoiceDecisionRequest:
    return ChoiceDecisionRequest(
        state=state if state is not None else {"slide_text": "Revenue grew 12 percent."},
        questions=(
            ChoiceQuestion(
                name="slide_purpose",
                instructions="Choose the best supported purpose for this slide.",
                criteria={
                    "decision": "The slide asks the audience to approve a decision.",
                    "evidence": "The slide primarily provides supporting evidence.",
                },
            ),
        ),
    )


def _choice_payload(choice: str = "evidence") -> dict[str, Any]:
    return {"slide_purpose": {"choice": choice}}


def _local_response(choice: str = "evidence") -> bytes:
    return json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(_choice_payload(choice))},
                }
            ]
        }
    ).encode()


def _systemone_response(choice: str = "evidence", model: str = "tev1:4b") -> bytes:
    return json.dumps(
        {
            "model": model,
            "answers": {
                "slide_purpose": {
                    "type": "choice",
                    "choice": choice,
                    "probabilities": {"decision": 0.1, "evidence": 0.9},
                    "confidence": 0.8,
                }
            },
            "usage": {"input_tokens": 42, "output_tokens": 3},
        }
    ).encode()


def test_request_snapshots_untrusted_mutable_input_and_builds_strict_schema() -> None:
    state = {"nested": {"labels": ["initial"]}}
    criteria = {"decision": "Ask for approval.", "evidence": "Support a claim."}
    question = ChoiceQuestion("slide_purpose", "Classify the slide.", criteria)
    request = ChoiceDecisionRequest(state=state, questions=(question,))
    original_serialized = request.serialized_request()

    state["nested"]["labels"].append("changed")
    criteria["decision"] = "Altered after validation."

    assert request.serialized_request() == original_serialized
    assert "changed" not in request.serialized_request()
    schema = request.output_schema()
    assert schema["additionalProperties"] is False
    question_schema = schema["properties"]["slide_purpose"]
    assert question_schema["additionalProperties"] is False
    assert question_schema["properties"]["choice"]["enum"] == ["decision", "evidence"]


@pytest.mark.parametrize(
    "state",
    [
        {"value": float("nan")},
        {"value": {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": 1}}}}}}}}}},
        {"value": "x" * (32 * 1024)},
    ],
)
def test_request_rejects_nonfinite_too_deep_and_oversized_state(state: dict[str, Any]) -> None:
    with pytest.raises(DecisionError) as error:
        _request(state)
    assert error.value.code == "DECISION_REQUEST_INVALID"


def test_request_rejects_duplicate_question_names_and_untrusted_answer_fields() -> None:
    question = ChoiceQuestion("slide_purpose", "Classify the slide.", {"a": "A", "b": "B"})
    with pytest.raises(DecisionError, match="unique"):
        ChoiceDecisionRequest(
            state={"source": "bounded"},
            questions=(question, question),
        )

    with pytest.raises(DecisionError) as error:
        _request().parse_structured_answers(
            {"slide_purpose": {"choice": "evidence", "action": "export"}}
        )
    assert error.value.code == "DECISION_PROVIDER_MALFORMED_OUTPUT"


def test_jev_uses_documented_typed_shape_and_validates_calibrated_output() -> None:
    observed: dict[str, Any] = {}

    def poster(url: str, headers: dict[str, str], body: bytes, timeout: float):
        observed.update(url=url, headers=headers, body=json.loads(body), timeout=timeout)
        return (
            200,
            json.dumps(
                {
                    "model": "typesafe/jev-1.13-20260917",
                    "answers": {
                        "slide_purpose": {
                            "choice": "evidence",
                            "confidence": 0.84,
                            "probabilities": {"decision": 0.16, "evidence": 0.84},
                            "type": "choice",
                        }
                    },
                }
            ).encode(),
        )

    provider = JevDecisionProvider(credential_resolver=lambda: "test-secret", poster=poster)
    result = provider.decide(_request())
    answer = result.answers["slide_purpose"]

    assert observed["url"] == "https://openrouter.ai/api/v1/systemone"
    assert observed["headers"]["Authorization"] == "Bearer test-secret"
    assert observed["body"]["model"] == "typesafe/jev-1.13"
    assert observed["body"]["questions"]["slide_purpose"]["type"] == "choice"
    assert observed["body"]["state"] == {"slide_text": "Revenue grew 12 percent."}
    assert result.model_id == "typesafe/jev-1.13-20260917"
    assert answer.choice == "evidence"
    assert answer.confidence == pytest.approx(0.84)
    assert dict(answer.probabilities or {}) == {"decision": 0.16, "evidence": 0.84}


def test_jev_fails_closed_without_credential_or_for_an_invalid_choice() -> None:
    calls = 0

    def unused_poster(*_args):
        nonlocal calls
        calls += 1
        return 200, b"{}"

    missing = JevDecisionProvider(credential_resolver=lambda: None, poster=unused_poster)
    with pytest.raises(DecisionError) as error:
        missing.decide(_request())
    assert error.value.code == "DECISION_PROVIDER_UNCONFIGURED"
    assert calls == 0

    invalid_output = JevDecisionProvider(
        credential_resolver=lambda: "test-secret",
        poster=lambda *_args: (
            200,
            json.dumps(
                {
                    "answers": {
                        "slide_purpose": {
                            "type": "choice",
                            "choice": "mutate_document",
                            "confidence": 0.99,
                        }
                    }
                }
            ).encode(),
        ),
    )
    with pytest.raises(DecisionError) as malformed:
        invalid_output.decide(_request())
    assert malformed.value.code == "DECISION_PROVIDER_MALFORMED_OUTPUT"


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (401, "DECISION_PROVIDER_AUTH_FAILED"),
        (402, "DECISION_PROVIDER_QUOTA_EXCEEDED"),
        (403, "DECISION_PROVIDER_PERMISSION_DENIED"),
        (429, "DECISION_PROVIDER_RATE_LIMITED"),
        (503, "DECISION_PROVIDER_UNAVAILABLE"),
    ],
)
def test_jev_maps_status_without_exposing_response_body(status: int, expected_code: str) -> None:
    provider = JevDecisionProvider(
        credential_resolver=lambda: "test-secret",
        poster=lambda *_args: (status, b"provider secret body"),
    )
    with pytest.raises(DecisionError) as error:
        provider.decide(_request())
    assert "provider secret body" not in str(error.value)
    assert error.value.code == expected_code


def test_openai_fast_uses_strict_schema_fast_tier_and_no_server_storage() -> None:
    observed: dict[str, Any] = {}

    class Responses:
        def create(self, **kwargs: Any):
            observed.update(kwargs)
            return SimpleNamespace(
                status="completed",
                service_tier="fast",
                output_text=json.dumps(_choice_payload()),
            )

    class Client:
        responses = Responses()

    provider = OpenAIFastDecisionProvider(
        credential_resolver=lambda: "test-secret",
        client_factory=lambda **_kwargs: Client(),
    )
    result = provider.decide(_request())

    assert result.answers["slide_purpose"].choice == "evidence"
    assert result.answers["slide_purpose"].confidence is None
    assert observed["service_tier"] == "fast"
    assert observed["store"] is False
    assert observed["tools"] == []
    assert observed["text"]["format"]["strict"] is True
    assert observed["text"]["format"]["schema"]["additionalProperties"] is False


def test_openai_fast_rejects_incomplete_and_nonchoice_response() -> None:
    class Responses:
        def __init__(self, response: Any) -> None:
            self.response = response

        def create(self, **_kwargs: Any):
            return self.response

    class ClientFactory:
        def __init__(self, response: Any) -> None:
            self.response = response

        def __call__(self, **_kwargs: Any):
            return SimpleNamespace(responses=Responses(self.response))

    for response in (
        SimpleNamespace(status="incomplete", output_text=json.dumps(_choice_payload())),
        SimpleNamespace(
            status="completed",
            service_tier="fast",
            output_text=json.dumps(_choice_payload("do_anything")),
        ),
    ):

        def client_factory(*, response_value: Any, **_kwargs: Any):
            return SimpleNamespace(responses=Responses(response_value))

        provider = OpenAIFastDecisionProvider(
            credential_resolver=lambda: "test-secret",
            client_factory=ClientFactory(response),
        )
        with pytest.raises(DecisionError) as error:
            provider.decide(_request())
        assert error.value.code in {
            "DECISION_PROVIDER_INCOMPLETE",
            "DECISION_PROVIDER_MALFORMED_OUTPUT",
        }


def test_openai_fast_rejects_reported_standard_tier_instead_of_silent_downgrade() -> None:
    provider = OpenAIFastDecisionProvider(
        credential_resolver=lambda: "test-secret",
        client_factory=lambda **_kwargs: SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **_params: SimpleNamespace(
                    status="completed",
                    service_tier="default",
                    output_text=json.dumps(_choice_payload()),
                )
            )
        ),
    )
    with pytest.raises(DecisionError) as error:
        provider.decide(_request())
    assert error.value.code == "DECISION_PROVIDER_FAST_TIER_NOT_USED"


def test_openai_fast_reports_unsupported_tier_without_falling_back() -> None:
    class UnsupportedTierError(Exception):
        status_code = 400
        param = "service_tier"

    def create(**_params: Any):
        raise UnsupportedTierError

    provider = OpenAIFastDecisionProvider(
        credential_resolver=lambda: "test-secret",
        client_factory=lambda **_kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    with pytest.raises(DecisionError) as error:
        provider.decide(_request())
    assert error.value.code == "DECISION_PROVIDER_FAST_TIER_UNAVAILABLE"


def test_openai_ultrafast_uses_gpt6_astra_and_strict_schema() -> None:
    observed: dict[str, Any] = {}

    class Responses:
        def create(self, **kwargs: Any):
            observed.update(kwargs)
            return SimpleNamespace(
                status="completed",
                service_tier="ultrafast",
                output_text=json.dumps(_choice_payload()),
            )

    provider = OpenAIUltrafastDecisionProvider(
        credential_resolver=lambda: "test-secret",
        client_factory=lambda **_kwargs: SimpleNamespace(responses=Responses()),
    )
    result = provider.decide(_request())

    assert result.provider_id == "openai_ultrafast"
    assert result.model_id == "gpt-6-astra"
    assert result.answers["slide_purpose"].choice == "evidence"
    assert observed["model"] == "gpt-6-astra"
    assert observed["service_tier"] == "ultrafast"
    assert observed["store"] is False
    assert observed["tools"] == []
    assert observed["text"]["format"]["strict"] is True


def test_openai_ultrafast_rejects_other_models_and_tier_downgrade() -> None:
    with pytest.raises(ValueError, match="GPT-6 Astra"):
        OpenAIUltrafastDecisionProvider(
            credential_resolver=lambda: "test-secret",
            model_id="gpt-5.6-sol",
        )

    provider = OpenAIUltrafastDecisionProvider(
        credential_resolver=lambda: "test-secret",
        client_factory=lambda **_kwargs: SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **_params: SimpleNamespace(
                    status="completed",
                    service_tier="default",
                    output_text=json.dumps(_choice_payload()),
                )
            )
        ),
    )
    with pytest.raises(DecisionError) as error:
        provider.decide(_request())
    assert error.value.code == "DECISION_PROVIDER_ULTRAFAST_TIER_NOT_USED"


def test_openai_ultrafast_reports_unavailable_tier_without_fallback() -> None:
    class UnsupportedTierError(Exception):
        status_code = 400
        param = "service_tier"

    def create(**_params: Any) -> Any:
        raise UnsupportedTierError

    provider = OpenAIUltrafastDecisionProvider(
        credential_resolver=lambda: "test-secret",
        client_factory=lambda **_kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    with pytest.raises(DecisionError) as error:
        provider.decide(_request())
    assert error.value.code == "DECISION_PROVIDER_ULTRAFAST_TIER_UNAVAILABLE"


def test_local_choice_adapter_is_loopback_only_unless_private_lan_is_explicit() -> None:
    loopback = LocalChoiceDecisionProvider(
        endpoint="http://127.0.0.1:1234/v1",
        model_id="local-fixture",
        poster=lambda *_args: (200, _local_response()),
    )
    lan = LocalChoiceDecisionProvider(
        endpoint="http://192.168.1.3:1234/v1",
        model_id="lan-fixture",
        poster=lambda *_args: (200, _local_response()),
    )

    assert loopback.leaves_machine is False
    assert lan.leaves_machine is True
    result = loopback.decide(_request())
    assert result.provider_id == "local_choice"
    assert result.answers["slide_purpose"].choice == "evidence"


def test_local_choice_adapter_sends_strict_schema_and_fails_without_fallback() -> None:
    observed: dict[str, Any] = {}

    def poster(url: str, headers: dict[str, str], body: bytes, timeout: float):
        observed.update(url=url, headers=headers, body=json.loads(body), timeout=timeout)
        return 200, _local_response()

    provider = LocalChoiceDecisionProvider(
        endpoint="http://localhost:1234/v1",
        model_id="fixture",
        credential_resolver=lambda: None,
        poster=poster,
    )
    provider.decide(_request())
    assert observed["url"] == "http://127.0.0.1:1234/v1/chat/completions"
    assert observed["body"]["response_format"]["json_schema"]["strict"] is True
    assert "Authorization" not in observed["headers"]

    unsupported = LocalChoiceDecisionProvider(
        endpoint="http://localhost:1234/v1",
        model_id="fixture",
        poster=lambda *_args: (
            200,
            json.dumps(
                {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
            ).encode(),
        ),
    )
    with pytest.raises(DecisionError) as error:
        unsupported.decide(_request())
    assert error.value.code == "DECISION_PROVIDER_MALFORMED_OUTPUT"


def test_local_choice_adapter_rejects_public_endpoint_and_secret_bearing_errors() -> None:
    with pytest.raises(DecisionError) as invalid_endpoint:
        LocalChoiceDecisionProvider(endpoint="https://example.com/v1", model_id="fixture")
    assert invalid_endpoint.value.code == "DECISION_ENDPOINT_INVALID"

    provider = LocalChoiceDecisionProvider(
        endpoint="http://127.0.0.1:1234/v1",
        model_id="fixture",
        poster=lambda *_args: (401, b"private server body"),
    )
    with pytest.raises(DecisionError) as auth_error:
        provider.decide(_request())
    assert auth_error.value.code == "DECISION_PROVIDER_AUTH_FAILED"
    assert "private server body" not in str(auth_error.value)


def test_local_choice_http_transport_posts_directly_and_does_not_follow_redirects() -> None:
    observed: dict[str, Any] = {"status": 200, "calls": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            observed["calls"].append((self.path, dict(self.headers), json.loads(body)))
            response_body = _local_response() if observed["status"] == 200 else b"redirect body"
            self.send_response(observed["status"])
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Location", "http://203.0.113.44/should-not-follow")
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, *_args: Any) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    provider = LocalChoiceDecisionProvider(
        endpoint=f"http://127.0.0.1:{server.server_port}/v1",
        model_id="loopback-fixture",
        credential_resolver=lambda: "local-secret",
    )
    try:
        assert provider.decide(_request()).answers["slide_purpose"].choice == "evidence"
        observed["status"] = 302
        with pytest.raises(DecisionError) as redirect:
            provider.decide(_request())
        assert redirect.value.code == "DECISION_PROVIDER_REQUEST_FAILED"
        assert len(observed["calls"]) == 2
        path, headers, body = observed["calls"][0]
        assert path == "/v1/chat/completions"
        assert headers["Authorization"] == "Bearer local-secret"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert observed["calls"][1][0] == path
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_ollama_systemone_sends_typed_choices_only_to_fixed_loopback() -> None:
    observed: dict[str, Any] = {}

    def poster(url: str, headers: dict[str, str], body: bytes, timeout: float):
        observed.update(url=url, headers=headers, body=json.loads(body), timeout=timeout)
        return 200, _systemone_response()

    digest = "a" * 64
    provider = OllamaSystemOneDecisionProvider(
        model_id="tev1:4b",
        poster=poster,
        model_digest_resolver=lambda *_args: digest,
    )
    result = provider.decide(_request())

    assert provider.locality == "local"
    assert provider.leaves_machine is False
    assert result.provider_id == "ollama_systemone"
    assert result.model_id == f"tev1:4b@sha256:{digest}"
    assert result.answers["slide_purpose"].choice == "evidence"
    assert result.answers["slide_purpose"].confidence == 0.8
    assert observed["url"] == "http://127.0.0.1:11434/v1/systemone"
    assert observed["headers"] == {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    assert observed["body"] == {
        "model": "tev1:4b",
        "state": {"slide_text": "Revenue grew 12 percent."},
        "questions": {
            "slide_purpose": {
                "type": "choice",
                "instructions": "Choose the best supported purpose for this slide.",
                "criteria": {
                    "decision": "The slide asks the audience to approve a decision.",
                    "evidence": "The slide primarily provides supporting evidence.",
                },
            }
        },
    }
    assert 0.5 <= observed["timeout"] <= 60


def test_ollama_systemone_allows_only_published_models_and_valid_responses() -> None:
    for model_id in (
        "nimble:9b",
        "nimble:9b-q4_K_M",
        "nimble:latest",
        "tev1:4b",
        "tev1:4b-q4_K_M",
        "tev1:latest",
        "tev1:0.8b",
    ):
        provider = OllamaSystemOneDecisionProvider(
            model_id=model_id,
            poster=lambda _url, _headers, _body, _timeout, model_id=model_id: (
                200,
                _systemone_response(model=model_id),
            ),
            model_digest_resolver=lambda *_args: "b" * 64,
        )
        assert provider.decide(_request()).model_id == f"{model_id}@sha256:{'b' * 64}"

    with pytest.raises(ValueError, match="supported Ollama decision model"):
        OllamaSystemOneDecisionProvider(model_id="qwen3.5")

    malformed = OllamaSystemOneDecisionProvider(
        poster=lambda *_args: (200, _systemone_response(choice="export")),
        model_digest_resolver=lambda *_args: "c" * 64,
    )
    with pytest.raises(DecisionError) as error:
        malformed.decide(_request())
    assert error.value.code == "DECISION_PROVIDER_MALFORMED_OUTPUT"


@pytest.mark.parametrize("model_id", ("nimble:9b", "nimble:9b-q4_K_M", "nimble:latest"))
def test_nimble_accepts_the_documented_26_choice_limit(model_id: str) -> None:
    observed: dict[str, Any] = {}

    def poster(_url: str, _headers: dict[str, str], body: bytes, _timeout: float):
        request_body = json.loads(body)
        observed.update(request_body)
        choice = next(iter(request_body["questions"]["purpose"]["criteria"]))
        response = {"answers": {"purpose": {"type": "choice", "choice": choice, "confidence": 1.0}}}
        return 200, json.dumps(response).encode()

    request = ChoiceDecisionRequest(
        state={"slide_text": "short"},
        questions=(
            ChoiceQuestion(
                name="purpose",
                instructions="Choose one.",
                criteria={f"choice_{index}": "A supported choice." for index in range(26)},
            ),
        ),
    )
    provider = OllamaSystemOneDecisionProvider(
        model_id=model_id,
        poster=poster,
        model_digest_resolver=lambda *_args: "a" * 64,
    )

    result = provider.decide(request)

    assert result.answers["purpose"].choice == "choice_0"
    assert len(observed["questions"]["purpose"]["criteria"]) == 26

    too_many_choices = ChoiceDecisionRequest(
        state={"slide_text": "short"},
        questions=(
            ChoiceQuestion(
                name="purpose",
                instructions="Choose one.",
                criteria={f"choice_{index}": "A supported choice." for index in range(27)},
            ),
        ),
    )
    with pytest.raises(DecisionError) as error:
        provider.decide(too_many_choices)
    assert error.value.code == "DECISION_PROVIDER_UNSUPPORTED_REQUEST"


@pytest.mark.parametrize("tev1_model_id", ("tev1:4b", "tev1:4b-q4_K_M", "tev1:latest", "tev1:0.8b"))
def test_ollama_systemone_enforces_context_and_api_request_limits_before_calling(
    tev1_model_id: str,
) -> None:
    calls = 0

    def poster(*_args: Any):
        nonlocal calls
        calls += 1
        return 200, _systemone_response()

    tev1 = OllamaSystemOneDecisionProvider(
        model_id=tev1_model_id,
        poster=poster,
        model_digest_resolver=lambda *_args: "d" * 64,
    )
    tev1_many_choices = ChoiceDecisionRequest(
        state={"slide_text": "short"},
        questions=(
            ChoiceQuestion(
                name="purpose",
                instructions="Choose one.",
                criteria={f"choice_{index}": "A supported choice." for index in range(25)},
            ),
        ),
    )
    with pytest.raises(DecisionError) as tev1_choice_limit:
        tev1.decide(tev1_many_choices)
    assert tev1_choice_limit.value.code == "DECISION_PROVIDER_UNSUPPORTED_REQUEST"

    with pytest.raises(DecisionError) as long_slide:
        tev1.decide(_request({"slide_text": "x" * (6 * 1024 + 1)}))
    assert long_slide.value.code == "DECISION_CONTEXT_TOO_LARGE"

    questions = tuple(
        ChoiceQuestion(
            name=f"question_{index}",
            instructions="Choose one.",
            criteria={f"choice_{choice}": "d" * 500 for choice in range(26)},
        )
        for index in range(8)
    )
    oversized = ChoiceDecisionRequest(state={"slide_text": "short"}, questions=questions)
    nimble = OllamaSystemOneDecisionProvider(
        model_id="nimble:9b-q4_K_M",
        poster=poster,
        model_digest_resolver=lambda *_args: "e" * 64,
    )
    with pytest.raises(DecisionError) as too_large:
        nimble.decide(oversized)
    assert too_large.value.code == "DECISION_CONTEXT_TOO_LARGE"
    assert calls == 0


def test_ollama_systemone_uses_model_context_safety_limits_before_model_lookup() -> None:
    calls = 0
    lookups = 0

    def poster(*_args: Any):
        nonlocal calls
        calls += 1
        return 200, _systemone_response()

    def resolve(*_args: Any) -> str:
        nonlocal lookups
        lookups += 1
        return "d" * 64

    tev1 = OllamaSystemOneDecisionProvider(
        model_id="tev1:0.8b", poster=poster, model_digest_resolver=resolve
    )
    nimble = OllamaSystemOneDecisionProvider(
        model_id="nimble:9b", poster=poster, model_digest_resolver=resolve
    )

    for provider, request in (
        (tev1, _request({"slide_text": "x" * 1_025})),
        (nimble, _request({"slide_text": "x" * (5 * 1024 + 1)})),
    ):
        with pytest.raises(DecisionError) as error:
            provider.decide(request)
        assert error.value.code == "DECISION_CONTEXT_TOO_LARGE"

    tev1_oversized_payload = ChoiceDecisionRequest(
        state={"slide_text": "short"},
        questions=tuple(
            ChoiceQuestion(
                name=f"question_{index}",
                instructions="i" * 300,
                criteria={"first": "a" * 350, "second": "b" * 350},
            )
            for index in range(2)
        ),
    )
    nimble_oversized_payload = ChoiceDecisionRequest(
        state={"slide_text": "short"},
        questions=tuple(
            ChoiceQuestion(
                name=f"question_{index}",
                instructions="i" * 900,
                criteria={"first": "a" * 450, "second": "b" * 450},
            )
            for index in range(6)
        ),
    )

    for provider, request in (
        (tev1, tev1_oversized_payload),
        (nimble, nimble_oversized_payload),
    ):
        with pytest.raises(DecisionError) as error:
            provider.decide(request)
        assert error.value.code == "DECISION_CONTEXT_TOO_LARGE"

    assert calls == 0
    assert lookups == 0


def test_ollama_systemone_redacts_provider_errors_and_rejects_non_loopback_urls() -> None:
    provider = OllamaSystemOneDecisionProvider(
        poster=lambda *_args: (404, b"internal path and prompt leaked here"),
        model_digest_resolver=lambda *_args: "f" * 64,
    )
    with pytest.raises(DecisionError) as missing_model:
        provider.decide(_request())
    assert missing_model.value.code == "DECISION_PROVIDER_MODEL_NOT_AVAILABLE"
    assert "internal path and prompt" not in str(missing_model.value)

    with pytest.raises(ValueError, match="fixed to its loopback endpoint"):
        _post_json(
            "http://203.0.113.4:11434/v1/systemone",
            {"Content-Type": "application/json"},
            b"{}",
            0.5,
        )


@pytest.mark.parametrize("model_id", ("tev1:4b", "nimble:latest"))
def test_ollama_model_resolution_reads_loopback_tags_and_pins_digest(
    monkeypatch, model_id: str
) -> None:
    observed: dict[str, Any] = {}

    class Response:
        status = 200

        def read(self, _limit: int) -> bytes:
            return json.dumps({"models": [{"name": model_id, "digest": "1" * 64}]}).encode()

    class Connection:
        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            observed.update(host=host, port=port, timeout=timeout)

        def request(self, method: str, path: str, **_kwargs: Any) -> None:
            observed.update(method=method, path=path)

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            observed["closed"] = True

    monkeypatch.setattr("presenter_core.decisions.ollama.http.client.HTTPConnection", Connection)
    assert _read_installed_model_digest(model_id, 1.5) == "1" * 64
    assert observed == {
        "host": "127.0.0.1",
        "port": 11434,
        "timeout": 1.5,
        "method": "GET",
        "path": "/api/tags",
        "closed": True,
    }


def test_ollama_model_change_during_decision_fails_closed() -> None:
    digests = iter(("a" * 64, "b" * 64))
    provider = OllamaSystemOneDecisionProvider(
        poster=lambda *_args: (200, _systemone_response()),
        model_digest_resolver=lambda *_args: next(digests),
    )
    with pytest.raises(DecisionError) as changed:
        provider.decide(_request())
    assert changed.value.code == "DECISION_PROVIDER_MODEL_CHANGED"


def test_provider_service_rejects_invalid_ollama_model_ids_without_fallback(tmp_path) -> None:
    storage = StorageManager(tmp_path)
    service = ProviderService(storage)
    try:
        for model_id in ("", [], {}):
            with pytest.raises(CoreDomainError):
                service.decision_provider("ollama_systemone", model_id=model_id)  # type: ignore[arg-type]
        provider = service.decision_provider("ollama_systemone")
        assert provider.model_id == "tev1:4b"
    finally:
        service.close()
        storage.close()
