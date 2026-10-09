"""Loopback-only Ollama System One adapter for Jev-compatible decision models."""

from __future__ import annotations

import http.client
import json
import re
import time
from collections.abc import Callable
from urllib.parse import urlsplit

from .jev import MAX_RESPONSE_BYTES, parse_jev_response
from .models import (
    ChoiceDecisionRequest,
    ChoiceDecisionResult,
    DecisionError,
    JsonPoster,
)

OLLAMA_SYSTEMONE_URL = "http://127.0.0.1:11434/v1/systemone"
DEFAULT_OLLAMA_MODEL = "tev1:4b"
OLLAMA_MODEL_OPTIONS = (
    ("nimble:9b", "Nimble 9B · about 9.5 GB"),
    ("nimble:9b-q4_K_M", "Nimble 9B Q4_K_M · about 5.6 GB"),
    ("nimble:latest", "Nimble 9B · Ollama latest tag · about 9.5 GB"),
    ("tev1:4b", "Tev1 4B · about 4.5 GB"),
    ("tev1:4b-q4_K_M", "Tev1 4B Q4_K_M · about 2.7 GB"),
    ("tev1:latest", "Tev1 4B · Ollama latest tag · about 4.5 GB"),
    ("tev1:0.8b", "Tev1 0.8B · about 812 MB"),
)
OLLAMA_MODEL_IDS = frozenset(model_id for model_id, _label in OLLAMA_MODEL_OPTIONS)
NIMBLE_MODEL_IDS = frozenset(
    model_id for model_id in OLLAMA_MODEL_IDS if model_id.startswith("nimble:")
)
MAX_REQUEST_BYTES = 65_536
# Ollama does not expose a tokenizer-based preflight. Bound the complete UTF-8
# request below each model's published context size, reserving room for its
# generated prompt template and scoring positions. These are safety limits, not
# token-count guarantees.
MAX_TEV1_STATE_BYTES = 1 * 1024
MAX_TEV1_REQUEST_BYTES = 1_536
MAX_NIMBLE_STATE_BYTES = 5 * 1024
MAX_NIMBLE_REQUEST_BYTES = 6 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TAGS_RESPONSE_BYTES = 1_048_576
_MODEL_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
ModelDigestResolver = Callable[[str, float], str]


class OllamaSystemOneDecisionProvider:
    """Call the documented Ollama decision endpoint without leaving loopback."""

    id = "ollama_systemone"
    locality = "local"

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_OLLAMA_MODEL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        poster: JsonPoster | None = None,
        model_digest_resolver: ModelDigestResolver | None = None,
    ) -> None:
        if not isinstance(model_id, str) or model_id not in OLLAMA_MODEL_IDS:
            raise ValueError("model_id must identify a supported Ollama decision model")
        self.model_id = model_id
        self._timeout_seconds = max(0.5, min(float(timeout_seconds), 60.0))
        self._poster = poster or _post_json
        self._model_digest_resolver = model_digest_resolver or _read_installed_model_digest

    @property
    def leaves_machine(self) -> bool:
        return False

    def decide(self, request: ChoiceDecisionRequest) -> ChoiceDecisionResult:
        maximum_choices = 26 if self.model_id in NIMBLE_MODEL_IDS else 24
        if any(len(question.criteria) > maximum_choices for question in request.questions):
            raise DecisionError(
                "DECISION_PROVIDER_UNSUPPORTED_REQUEST",
                f"The selected Ollama model supports at most {maximum_choices} choices "
                "per question.",
            )

        state_limit = (
            MAX_NIMBLE_STATE_BYTES if self.model_id in NIMBLE_MODEL_IDS else MAX_TEV1_STATE_BYTES
        )
        if len(request.serialized_state().encode("utf-8")) > state_limit:
            raise DecisionError(
                "DECISION_CONTEXT_TOO_LARGE",
                "This slide is too long for the selected Ollama model's bounded context.",
            )

        body = json.dumps(
            request.to_jev_payload(self.model_id),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise DecisionError(
                "DECISION_CONTEXT_TOO_LARGE",
                "The typed decision request exceeds Ollama System One's 64 KiB limit.",
            )
        model_request_limit = (
            MAX_NIMBLE_REQUEST_BYTES
            if self.model_id in NIMBLE_MODEL_IDS
            else MAX_TEV1_REQUEST_BYTES
        )
        if len(body) > model_request_limit:
            raise DecisionError(
                "DECISION_CONTEXT_TOO_LARGE",
                "The typed decision request exceeds the selected Ollama model's "
                "context safety limit.",
            )

        started = time.monotonic()
        digest_before = self._resolve_model_digest()
        try:
            status, payload = self._poster(
                OLLAMA_SYSTEMONE_URL,
                {"Content-Type": "application/json", "Accept": "application/json"},
                body,
                self._timeout_seconds,
            )
        except DecisionError:
            raise
        except TimeoutError as error:
            raise DecisionError(
                "DECISION_PROVIDER_TIMEOUT",
                "The local Ollama decision model timed out.",
                retryable=True,
            ) from error
        except Exception as error:
            raise DecisionError(
                "DECISION_PROVIDER_UNAVAILABLE",
                "The local Ollama decision service could not be reached.",
                retryable=True,
            ) from error

        if isinstance(status, bool) or not isinstance(status, int):
            raise _malformed()
        if status != 200:
            code, message, retryable = _map_status(status)
            raise DecisionError(code, message, retryable=retryable)
        if not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE_BYTES:
            raise _malformed()
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise _malformed() from error

        answers = parse_jev_response(decoded, request)
        if not isinstance(decoded, dict):
            raise _malformed()
        digest_after = self._resolve_model_digest()
        if digest_after != digest_before:
            raise DecisionError(
                "DECISION_PROVIDER_MODEL_CHANGED",
                "The installed Ollama model changed during this decision. Retry the request.",
                retryable=True,
            )
        return ChoiceDecisionResult(
            provider_id=self.id,
            model_id=f"{self.model_id}@sha256:{digest_before.removeprefix('sha256:')}",
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            answers=answers,
        )

    def close(self) -> None:
        """This adapter owns no persistent transport resources."""

    def _resolve_model_digest(self) -> str:
        try:
            digest = self._model_digest_resolver(self.model_id, self._timeout_seconds)
        except DecisionError:
            raise
        except TimeoutError as error:
            raise DecisionError(
                "DECISION_PROVIDER_TIMEOUT",
                "The local Ollama model check timed out.",
                retryable=True,
            ) from error
        except Exception as error:
            raise DecisionError(
                "DECISION_PROVIDER_UNAVAILABLE",
                "The local Ollama model could not be verified.",
                retryable=True,
            ) from error
        if not isinstance(digest, str) or not _MODEL_DIGEST.fullmatch(digest):
            raise _malformed()
        return digest


def _malformed() -> DecisionError:
    return DecisionError(
        "DECISION_PROVIDER_MALFORMED_OUTPUT",
        "Ollama returned malformed typed decision output.",
    )


def _map_status(status: int) -> tuple[str, str, bool]:
    if status == 401:
        return (
            "DECISION_PROVIDER_AUTH_FAILED",
            "The local Ollama decision endpoint rejected the request.",
            False,
        )
    if status == 404:
        return (
            "DECISION_PROVIDER_MODEL_NOT_AVAILABLE",
            "Ollama did not find the selected model or System One endpoint. "
            "Check that Ollama 0.35 or later is running and the model is already installed.",
            False,
        )
    if status == 413:
        return (
            "DECISION_CONTEXT_TOO_LARGE",
            "Ollama rejected the decision because its request limit was exceeded.",
            False,
        )
    if status == 429:
        return (
            "DECISION_PROVIDER_RATE_LIMITED",
            "The local Ollama decision service is busy.",
            True,
        )
    if status >= 500:
        return (
            "DECISION_PROVIDER_UNAVAILABLE",
            "The local Ollama decision service is temporarily unavailable.",
            True,
        )
    return (
        "DECISION_PROVIDER_REQUEST_FAILED",
        "Ollama could not process this typed decision request.",
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
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 11434
        or parsed.path != "/v1/systemone"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Ollama System One is fixed to its loopback endpoint.")
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout)
    try:
        connection.request("POST", parsed.path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read(MAX_RESPONSE_BYTES + 1)
        return response.status, payload
    finally:
        connection.close()


def _read_installed_model_digest(model_id: str, timeout: float) -> str:
    """Resolve an already-installed exact Ollama tag without loading/downloading it."""
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=timeout)
    try:
        connection.request("GET", "/api/tags", headers={"Accept": "application/json"})
        response = connection.getresponse()
        payload = response.read(MAX_TAGS_RESPONSE_BYTES + 1)
        if response.status != 200:
            code, message, retryable = _map_status(response.status)
            raise DecisionError(code, message, retryable=retryable)
    finally:
        connection.close()
    if len(payload) > MAX_TAGS_RESPONSE_BYTES:
        raise _malformed()
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _malformed() from error
    if not isinstance(decoded, dict) or not isinstance(decoded.get("models"), list):
        raise _malformed()
    matches = [
        item
        for item in decoded["models"]
        if isinstance(item, dict) and item.get("name") == model_id
    ]
    if len(matches) != 1:
        raise DecisionError(
            "DECISION_PROVIDER_MODEL_NOT_AVAILABLE",
            "The selected Ollama model is not installed. Install it in Ollama before use.",
        )
    digest = matches[0].get("digest")
    if not isinstance(digest, str) or not _MODEL_DIGEST.fullmatch(digest):
        raise _malformed()
    return digest
