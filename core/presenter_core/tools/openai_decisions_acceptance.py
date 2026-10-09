"""Opt-in native Decisions diagnostic using synthetic content only.

No project, credential store, OAuth session, endpoint override or fallback is used.
Run with --live and OPENAI_API_KEY set in the process environment.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
from typing import Any

from presenter_core.decisions.models import ChoiceDecisionRequest, ChoiceQuestion, DecisionProvider
from presenter_core.decisions.openai_decisions import OpenAIDecisionsProvider
from presenter_core.decisions.purpose import (
    SLIDE_PURPOSE_CHOICES,
    SLIDE_PURPOSE_QUESTION_INSTRUCTIONS,
)
from presenter_core.decisions.triage import reviewed_suggestion, triage_request
from presenter_core.tools.claim_triage_acceptance import CASES
from presenter_core.tools.decision_acceptance import _EXAMPLES, _error_code


def evaluate(provider: DecisionProvider) -> dict[str, Any]:
    """Observe the actual adapter; a completed diagnostic is not production acceptance."""
    if provider.id != "openai_decisions" or not provider.leaves_machine:
        raise ValueError("This diagnostic requires the native OpenAI Decisions adapter.")
    requests = [
        (
            "purpose",
            str(index),
            expected,
            ChoiceDecisionRequest(
                state={"slide_text": text},
                questions=(
                    ChoiceQuestion(
                        "purpose", SLIDE_PURPOSE_QUESTION_INSTRUCTIONS, SLIDE_PURPOSE_CHOICES
                    ),
                ),
            ),
        )
        for index, (expected, text) in enumerate(_EXAMPLES, start=1)
    ] + [
        ("relation", name, expected, triage_request(quote, excerpt))
        for name, expected, quote, excerpt in CASES
    ]
    rows: list[dict[str, Any]] = []
    latencies: list[int] = []
    try:
        for task, case, expected, request in requests:
            try:
                result = provider.decide(request)
                answer = result.answers[task]
                row: dict[str, Any] = {
                    "task": task,
                    "case": case,
                    "expected": expected,
                    "actual": answer.choice,
                    "correct": answer.choice == expected,
                    "confidence": answer.confidence,
                    "probabilities": dict(answer.probabilities or {}),
                    "latency_ms": result.latency_ms,
                }
                if task == "relation":
                    row["review"] = reviewed_suggestion(answer)
                rows.append(row)
                latencies.append(result.latency_ms)
            except Exception as error:
                rows.append({"task": task, "case": case, "error_code": _error_code(error)})
                # One attempt per case; never retry or hammer a rejected credential/access gate.
                break
    finally:
        provider.close()
    ordered = sorted(latencies)
    completed = len(latencies) == len(requests)
    return {
        "status": "completed" if completed else "failed",
        "benchmark": "native-decisions-synthetic-v1",
        "provider_id": provider.id,
        "model_id": provider.model_id,
        "cases": len(requests),
        "cases_attempted": len(rows),
        "valid_structured_responses": len(latencies),
        "correct": sum(row.get("correct") is True for row in rows),
        "median_latency_ms": statistics.median(latencies) if latencies else None,
        "p95_latency_ms": ordered[math.ceil(len(ordered) * 0.95) - 1] if ordered else None,
        "confidence_calibrated": False,
        "evaluation_scope": "authored synthetic diagnostic; no production quality threshold",
        "presentation_content_used": False,
        "raw_prompt_or_response_emitted": False,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send up to 30 synthetic API requests.")
    args = parser.parse_args(argv)
    if not args.live:
        parser.error("--live is required to authorize synthetic API requests")
    if not os.environ.get("OPENAI_API_KEY"):
        print(json.dumps({"status": "not_executed", "reason": "OPENAI_API_KEY unavailable"}))
        return 2
    provider = OpenAIDecisionsProvider(credential_resolver=lambda: os.environ.get("OPENAI_API_KEY"))
    report = evaluate(provider)
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
