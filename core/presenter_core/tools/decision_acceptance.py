"""Metadata-only acceptance smoke for a loopback structured-decision model."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from typing import Any

from presenter_core.decisions.local import LocalChoiceDecisionProvider
from presenter_core.decisions.models import (
    ChoiceDecisionRequest,
    ChoiceQuestion,
    DecisionError,
    DecisionProvider,
)
from presenter_core.decisions.ollama import (
    DEFAULT_OLLAMA_MODEL,
    OLLAMA_MODEL_IDS,
    OllamaSystemOneDecisionProvider,
)
from presenter_core.decisions.purpose import (
    SLIDE_PURPOSE_CHOICES,
    SLIDE_PURPOSE_QUESTION_INSTRUCTIONS,
)

_EXAMPLES = (
    (
        "opening",
        "Quarterly strategy review\n"
        "Align on the customer-retention objective and decide which initiatives to fund.",
    ),
    (
        "problem",
        "Support queue is growing\n"
        "Median first response rose from 3 hours to 11 hours after the February launch.",
    ),
    (
        "recommendation",
        "Recommendation\n"
        "Approve a six-week pilot in two regions before expanding the new onboarding flow.",
    ),
    (
        "evidence",
        "Pilot results\n"
        "Completion increased from 62% to 78% across 1,240 eligible accounts; "
        "the control group stayed at 63%.",
    ),
    (
        "plan",
        "Rollout plan\n"
        "Week 1: train two teams. Weeks 2–4: run the pilot. Week 5: review incidents. "
        "Week 6: decide whether to expand.",
    ),
    (
        "risk",
        "Key risks and controls\n"
        "A private endpoint may expose customer text on the LAN. Restrict it to loopback "
        "and record the selected provider.",
    ),
    (
        "transition",
        "From diagnosis to response\n"
        "Now that we have established the causes of churn, we will look at the "
        "proposed retention changes.",
    ),
    (
        "summary",
        "Decision and next steps\n"
        "Fund the pilot, assign an operations owner, and return with results "
        "at the November review.",
    ),
    (
        "appendix",
        "Appendix A — Terms\n"
        "Activation: first completed workflow. Retained account: active at 30 days. "
        "Eligible cohort: accounts with consent.",
    ),
    ("unclear", "Overview\nDraft v3\nBlue 16 px"),
)

_LOCAL_DEFAULT_ENDPOINT = "http://127.0.0.1:1234/v1"


def _error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    return (
        code
        if isinstance(code, str)
        and code
        and len(code) <= 80
        and all(
            character.isascii() and (character.isupper() or character.isdigit() or character == "_")
            for character in code
        )
        else "DECISION_ACCEPTANCE_FAILED"
    )


def _make_provider(
    provider_id: str,
    endpoint: str | None,
    model_id: str,
    timeout_seconds: float,
) -> DecisionProvider:
    if provider_id == "ollama_systemone":
        if endpoint is not None:
            raise ValueError("Ollama System One uses its fixed loopback endpoint.")
        return OllamaSystemOneDecisionProvider(
            model_id=model_id,
            timeout_seconds=timeout_seconds,
        )
    if provider_id != "local_choice":
        raise ValueError("The selected decision acceptance provider is unsupported.")
    return LocalChoiceDecisionProvider(
        endpoint=endpoint or _LOCAL_DEFAULT_ENDPOINT,
        model_id=model_id,
        timeout_seconds=timeout_seconds,
    )


def _run(
    endpoint: str | None,
    model_id: str,
    timeout_seconds: float,
    provider_id: str = "local_choice",
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    latency_values: list[int] = []
    resolved_model_ids: set[str] = set()
    provider: DecisionProvider | None = None
    error_code: str | None = None
    try:
        provider = _make_provider(provider_id, endpoint, model_id, timeout_seconds)
        if provider.leaves_machine:
            raise DecisionError(
                "DECISION_ACCEPTANCE_LOOPBACK_REQUIRED",
                "The local decision smoke accepts loopback endpoints only.",
            )
        for index, (expected, slide_text) in enumerate(_EXAMPLES, start=1):
            request = ChoiceDecisionRequest(
                state={"slide_text": slide_text},
                questions=(
                    ChoiceQuestion(
                        name="purpose",
                        instructions=SLIDE_PURPOSE_QUESTION_INSTRUCTIONS,
                        criteria=SLIDE_PURPOSE_CHOICES,
                    ),
                ),
            )
            try:
                result = provider.decide(request)
                answer = result.answers["purpose"].choice
                resolved_model_ids.add(result.model_id)
                latency_values.append(result.latency_ms)
                rows.append(
                    {
                        "case": index,
                        "expected": expected,
                        "actual": answer,
                        "correct": answer == expected,
                        "latency_ms": result.latency_ms,
                    }
                )
            except Exception as error:
                rows.append(
                    {
                        "case": index,
                        "expected": expected,
                        "actual": None,
                        "correct": False,
                        "error_code": _error_code(error),
                    }
                )
        if len(latency_values) != len(_EXAMPLES):
            error_code = "DECISION_ACCEPTANCE_INCOMPLETE"
    except Exception as error:
        error_code = _error_code(error)
    finally:
        if provider is not None:
            provider.close()

    ordered = sorted(latency_values)
    correct = sum(bool(row.get("correct")) for row in rows)
    accuracy = round(100 * correct / len(_EXAMPLES), 1) if latency_values else None
    report: dict[str, Any] = {
        "status": "completed" if error_code is None else "failed",
        "benchmark": "presentation-purpose-local-smoke-v1",
        "provider_id": provider_id,
        "configured_model_id": model_id,
        "resolved_model_ids": sorted(resolved_model_ids),
        "endpoint_scope": "loopback_only_required",
        "cases": len(_EXAMPLES),
        "cases_attempted": len(rows),
        "valid_structured_responses": len(latency_values),
        "correct": correct,
        "accuracy_percent": accuracy,
        "median_latency_ms": round(statistics.median(latency_values)) if latency_values else None,
        "p95_latency_ms": ordered[math.ceil(0.95 * len(ordered)) - 1] if ordered else None,
        "evaluation_scope": "self-authored synthetic smoke; no quality threshold",
        "presentation_content_used": False,
        "raw_prompt_or_response_emitted": False,
        "rows": rows,
    }
    if error_code is not None:
        report["error_code"] = error_code
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider-id",
        choices=("local_choice", "ollama_systemone"),
        default="local_choice",
        help="Decision provider to exercise; defaults to the local JSON Schema adapter.",
    )
    parser.add_argument(
        "--endpoint",
        help=(
            "Already-running loopback OpenAI-compatible API base URL; only applies to local_choice."
        ),
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Model identifier. Ollama defaults to its Tev1 4B model.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="Per-request timeout from 0.5 to 30 seconds.",
    )
    args = parser.parse_args(argv)
    if not 0.5 <= args.timeout_seconds <= 30:
        parser.error("--timeout-seconds must be between 0.5 and 30")
    model_id = args.model_id
    if args.provider_id == "ollama_systemone":
        if args.endpoint is not None:
            parser.error("--endpoint is not configurable for Ollama System One")
        model_id = model_id or DEFAULT_OLLAMA_MODEL
        if model_id not in OLLAMA_MODEL_IDS:
            parser.error(
                "--model-id must be one of the supported installed Ollama decision tags: "
                + ", ".join(sorted(OLLAMA_MODEL_IDS))
            )
    elif not model_id:
        parser.error("--model-id is required for local_choice")
    report = _run(args.endpoint, model_id, args.timeout_seconds, args.provider_id)
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
