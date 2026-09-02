"""Deterministic test-only provider with bounded payload capture."""

from __future__ import annotations

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


class DeterministicFakeReasoningProvider(ReasoningProvider):
    """Offline provider used by CI and explicit developer acceptance flows."""

    id = "fake-test"

    def __init__(
        self,
        *,
        locality: str = "remote",
        failure_code: str | None = None,
        model_id: str = "fake-teach-v1",
    ) -> None:
        self.locality = locality
        self.model_id = model_id
        self.failure_code = failure_code
        self.requests: list[dict[str, Any]] = []
        self.call_count = 0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            structured_outputs=True,
            streaming=False,
            cancellation=False,
            task_types=("teach_question", "teach_candidate"),
        )

    def health(self) -> ProviderHealth:
        if self.failure_code == "PROVIDER_UNCONFIGURED":
            return ProviderHealth(
                provider_id=self.id,
                locality=self.locality,
                model_id=self.model_id,
                status="unconfigured",
                configured=False,
                error_code=self.failure_code,
            )
        return ProviderHealth(
            provider_id=self.id,
            locality=self.locality,
            model_id=self.model_id,
            status="ready",
            configured=True,
        )

    def generate(self, request: ReasoningRequest) -> ReasoningResult:
        self.call_count += 1
        self.requests.append(request.to_payload())
        if self.failure_code is not None:
            raise ProviderError(
                self.failure_code,
                "The deterministic reasoning provider was configured to fail.",
                retryable=self.failure_code
                in {"PROVIDER_TIMEOUT", "PROVIDER_RATE_LIMITED", "PROVIDER_UNAVAILABLE"},
            )
        started = monotonic()
        if request.task_type == "teach_question":
            evidence = request.evidence[0] if request.evidence else None
            if isinstance(evidence, dict) and isinstance(evidence.get("label"), str):
                question = (
                    f"What made the option described in {evidence['label']} a poor fit "
                    "for this project?"
                )
            else:
                question = "What decision or tradeoff behind this project should I remember?"
            output = validate_provider_output(
                request.task_type,
                {"question": question, "focus": "decision_rationale"},
            )
        elif request.task_type == "teach_candidate":
            answer = (request.user_input or "").strip()
            if not answer:
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT",
                    "The deterministic provider needs a user explanation.",
                )
            lowered = answer.casefold()
            if "reject" in lowered or "rollback" in lowered or "cutover" in lowered:
                candidate_text = (
                    "We rejected it because it doubled the cutover surface and made rollback "
                    "harder."
                    if "doubled the cutover surface" in lowered
                    else answer
                )
            else:
                candidate_text = answer
            output = validate_provider_output(
                request.task_type,
                {
                    "kind": "rationale",
                    "text": candidate_text,
                    "follow_up_question": None,
                },
            )
        else:
            raise ProviderError("PROVIDER_REQUEST_FAILED", "Unsupported fake provider task.")
        return ReasoningResult(
            output=output,
            input_token_count=None,
            output_token_count=None,
            latency_ms=max(0, int((monotonic() - started) * 1000)),
        )
