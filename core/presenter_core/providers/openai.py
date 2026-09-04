"""Official OpenAI Responses API adapter for bounded reasoning tasks."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from threading import Lock
from time import monotonic
from typing import Any

from .models import (
    ProviderCapabilities,
    ProviderError,
    ProviderHealth,
    ProviderInvocation,
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
        self._client_lock = Lock()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            structured_outputs=True,
            streaming=False,
            cancellation=False,
            task_types=(
                "teach_question",
                "teach_candidate",
                "challenge_question",
                "challenge_follow_up",
                "challenge_evaluation",
                "live_cue",
            ),
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

    def generate(self, invocation: ProviderInvocation) -> ReasoningResult:
        request = invocation.request
        effective_timeout = self._effective_timeout_seconds(request)
        # Keep the SDK client and its connection pool stable.  The operation
        # budget belongs on this request, not in cached-client identity.
        client = self._load_client()
        schema_name = {
            "teach_question": "teach_question",
            "teach_candidate": "teach_candidate",
            "challenge_question": "challenge_question",
            "challenge_follow_up": "challenge_follow_up",
            "challenge_evaluation": "challenge_evaluation",
            "live_cue": "live_cue",
        }.get(request.task_type)
        if schema_name is None:
            raise ProviderError(
                "PROVIDER_REQUEST_FAILED",
                "The reasoning task is not supported.",
            )
        started = monotonic()
        system_content = [
            {"type": "input_text", "text": request.application_policy},
        ]
        if request.task_instruction:
            system_content.append({"type": "input_text", "text": request.task_instruction})
        try:
            response = client.responses.create(
                model=self.model_id,
                input=[
                    {
                        "role": "system",
                        "content": system_content,
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": invocation.serialized_input()},
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
                timeout=effective_timeout,
            )
        except Exception as error:
            raise self._map_error(error) from error

        try:
            output_text = getattr(response, "output_text", None)
            if not isinstance(output_text, str) or not output_text.strip():
                output_text = self._extract_output_text(response)
            output = validate_provider_output(
                request.task_type,
                json.loads(output_text),
                conflict_metadata=request.conflict_metadata,
            )
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
        with self._client_lock:
            client = self._client
            self._client = None
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    # Provider shutdown must not turn into a user-visible
                    # failure or leak SDK exception details.
                    pass

    def _load_client(self) -> Any:
        if not self._api_key:
            raise ProviderError("PROVIDER_UNCONFIGURED", "OpenAI credentials are not configured.")
        with self._client_lock:
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

    def _effective_timeout_seconds(self, request: ReasoningRequest) -> float:
        """Keep the adapter timeout inside the core-owned request budget."""
        if not isinstance(request.latency_budget_ms, int) or request.latency_budget_ms <= 0:
            raise ProviderError(
                "PROVIDER_TIMEOUT",
                "The reasoning request has no positive latency budget.",
                retryable=True,
            )
        return min(self._timeout_seconds, request.latency_budget_ms / 1000.0)

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
        provider_code = _provider_error_code(error)
        if (
            provider_code
            in {
                "insufficient_quota",
                "quota_exceeded",
                "billing_hard_limit_reached",
            }
            or "quota" in provider_code
        ):
            return ProviderError(
                "PROVIDER_QUOTA_EXCEEDED", "The OpenAI provider quota was exceeded."
            )
        if (
            status == 401
            or provider_code in {"invalid_api_key", "authentication_error", "unauthorized"}
            or "authentication" in name
            or "permission" in name
        ):
            return ProviderError("PROVIDER_AUTH_FAILED", "The OpenAI credential was rejected.")
        if status == 429 or "rate" in name or "rate_limit" in provider_code:
            return ProviderError(
                "PROVIDER_RATE_LIMITED",
                "The OpenAI provider rate limit was reached.",
                retryable=True,
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


def _provider_error_code(error: Exception) -> str:
    """Read only a safe provider code; never serialize or return the raw body."""
    direct = getattr(error, "code", None)
    if isinstance(direct, str):
        return direct.casefold()
    body = getattr(error, "body", None)
    if isinstance(body, Mapping):
        nested = body.get("error")
        if isinstance(nested, Mapping):
            nested_code = nested.get("code")
            if isinstance(nested_code, str):
                return nested_code.casefold()
        body_code = body.get("code")
        if isinstance(body_code, str):
            return body_code.casefold()
    return ""


def _usage_int(usage: Any, field: str) -> int | None:
    value = getattr(usage, field, None)
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(usage, dict):
        candidate = usage.get(field)
        if isinstance(candidate, int) and candidate >= 0:
            return candidate
    return None
