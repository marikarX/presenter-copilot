"""Official OpenAI Responses API adapter for bounded M3 Teach tasks."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from time import monotonic
from typing import Any

from .models import (
    ProviderCapabilities,
    ProviderError,
    ProviderHealth,
    ReasoningProvider,
    ReasoningRequest,
    ReasoningResult,
    validate_provider_output,
)

DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_TIMEOUT_SECONDS = 20.0


class OpenAIReasoningProvider(ReasoningProvider):
    """Use only OPENAI_API_KEY and the official SDK; never browser credentials."""

    id = "openai"
    locality = "remote"

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_OPENAI_MODEL,
        api_key: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.model_id = model_id
        self._api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        self._timeout_seconds = max(1.0, min(float(timeout_seconds), 120.0))
        self._client_factory = client_factory
        self._client: Any | None = None

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            structured_outputs=True,
            streaming=False,
            cancellation=False,
            task_types=("teach_question", "teach_candidate"),
        )

    def health(self) -> ProviderHealth:
        if not self._api_key:
            return ProviderHealth(
                provider_id=self.id,
                locality=self.locality,
                model_id=self.model_id,
                status="unconfigured",
                configured=False,
                error_code="PROVIDER_UNCONFIGURED",
            )
        try:
            self._load_client()
        except ProviderError as error:
            return ProviderHealth(
                provider_id=self.id,
                locality=self.locality,
                model_id=self.model_id,
                status="unavailable",
                configured=True,
                error_code=error.code,
                retryable=error.retryable,
            )
        return ProviderHealth(
            provider_id=self.id,
            locality=self.locality,
            model_id=self.model_id,
            status="ready",
            configured=True,
        )

    def generate(self, request: ReasoningRequest) -> ReasoningResult:
        client = self._load_client()
        schema_name = (
            "teach_question" if request.task_type == "teach_question" else "teach_candidate"
        )
        started = monotonic()
        try:
            response = client.responses.create(
                model=self.model_id,
                input=[
                    {
                        "role": "system",
                        "content": [
                            {"type": "input_text", "text": request.application_policy},
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": request.serialized_input()},
                        ],
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": request.output_schema,
                    }
                },
                tools=[],
                store=False,
                timeout=self._timeout_seconds,
            )
        except Exception as error:
            raise self._map_error(error) from error

        try:
            output_text = getattr(response, "output_text", None)
            if not isinstance(output_text, str) or not output_text.strip():
                output_text = self._extract_output_text(response)
            output = validate_provider_output(request.task_type, json.loads(output_text))
        except ProviderError:
            raise
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProviderError(
                "PROVIDER_MALFORMED_OUTPUT",
                "The reasoning provider returned malformed structured output.",
            ) from error

        usage = getattr(response, "usage", None)
        input_tokens = _usage_int(usage, "input_tokens")
        output_tokens = _usage_int(usage, "output_tokens")
        return ReasoningResult(
            output=output,
            input_token_count=input_tokens,
            output_token_count=output_tokens,
            latency_ms=max(0, int((monotonic() - started) * 1000)),
        )

    def close(self) -> None:
        self._client = None

    def _load_client(self) -> Any:
        if not self._api_key:
            raise ProviderError("PROVIDER_UNCONFIGURED", "OpenAI credentials are not configured.")
        if self._client is not None:
            return self._client
        try:
            if self._client_factory is not None:
                self._client = self._client_factory(
                    api_key=self._api_key,
                    timeout=self._timeout_seconds,
                    max_retries=0,
                )
            else:
                from openai import OpenAI

                self._client = OpenAI(
                    api_key=self._api_key,
                    timeout=self._timeout_seconds,
                    max_retries=0,
                )
        except Exception as error:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                "The OpenAI SDK is unavailable.",
                retryable=True,
            ) from error
        return self._client

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        output = getattr(response, "output", None)
        if not isinstance(output, list):
            raise ProviderError(
                "PROVIDER_MALFORMED_OUTPUT",
                "The reasoning provider returned no structured output.",
            )
        for item in output:
            content = getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for part in content:
                text = getattr(part, "text", None)
                if isinstance(text, str) and text.strip():
                    return text
        raise ProviderError(
            "PROVIDER_MALFORMED_OUTPUT",
            "The reasoning provider returned no structured output.",
        )

    @staticmethod
    def _map_error(error: Exception) -> ProviderError:
        name = type(error).__name__.casefold()
        status = getattr(error, "status_code", None)
        if isinstance(status, str) and status.isdecimal():
            status = int(status)
        if status == 401 or "authentication" in name or "permission" in name:
            return ProviderError("PROVIDER_AUTH_FAILED", "The OpenAI credential was rejected.")
        if status == 429 or "rate" in name:
            return ProviderError(
                "PROVIDER_RATE_LIMITED",
                "The OpenAI provider rate limit was reached.",
                retryable=True,
            )
        if "quota" in name or "quota" in str(getattr(error, "code", "")).casefold():
            return ProviderError(
                "PROVIDER_QUOTA_EXCEEDED", "The OpenAI provider quota was exceeded."
            )
        if "timeout" in name or isinstance(error, TimeoutError):
            return ProviderError(
                "PROVIDER_TIMEOUT",
                "The OpenAI provider timed out within the bounded request budget.",
                retryable=True,
            )
        if "connection" in name or "connect" in name:
            return ProviderError(
                "PROVIDER_UNAVAILABLE",
                "The OpenAI provider could not be reached.",
                retryable=True,
            )
        return ProviderError(
            "PROVIDER_REQUEST_FAILED",
            "The OpenAI reasoning request failed.",
            retryable=True,
        )


def _usage_int(usage: Any, field: str) -> int | None:
    value = getattr(usage, field, None)
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(usage, dict):
        candidate = usage.get(field)
        if isinstance(candidate, int) and candidate >= 0:
            return candidate
    return None
