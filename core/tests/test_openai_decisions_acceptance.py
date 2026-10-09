from __future__ import annotations

import json

import pytest

from presenter_core.decisions.openai_decisions import OpenAIDecisionsProvider
from presenter_core.tools import openai_decisions_acceptance as acceptance


def test_live_acceptance_requires_opt_in_and_credential(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        acceptance.main([])
    assert acceptance.main(["--live"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "not_executed"


def test_native_acceptance_stops_at_access_rejection_without_disclosing_body() -> None:
    calls = []

    def poster(url, headers, body, timeout):
        calls.append(url)
        return 403, b'{"error":"SECRET_RESPONSE_CANARY"}'

    provider = OpenAIDecisionsProvider(credential_resolver=lambda: "SECRET_KEY", poster=poster)
    report = acceptance.evaluate(provider)
    assert len(calls) == 1
    assert report["status"] == "failed"
    assert report["valid_structured_responses"] == 0
    assert report["rows"][0]["error_code"] == "DECISION_PROVIDER_PERMISSION_DENIED"
    assert "SECRET" not in json.dumps(report)


def test_native_acceptance_collects_probabilities_and_separate_review_abstentions() -> None:
    def poster(url, headers, body, timeout):
        question = json.loads(body)["questions"][0]
        values = [choice["value"] for choice in question["choices"]]
        answer = {
            "type": "choice",
            "name": question["name"],
            "choice": values[0],
            "confidence": 0.5,
            "probabilities": [{"value": value, "probability": 1 / len(values)} for value in values],
        }
        return 200, json.dumps({"model": "gpt-6-luna", "answers": [answer]}).encode()

    provider = OpenAIDecisionsProvider(credential_resolver=lambda: "fixture", poster=poster)
    report = acceptance.evaluate(provider)
    assert report["status"] == "completed"
    assert report["valid_structured_responses"] == 30
    assert report["confidence_calibrated"] is False
    relations = [row for row in report["rows"] if row["task"] == "relation"]
    assert len(relations) == 20
    assert all(row["review"]["abstained"] is True for row in relations)
    assert all(row["confidence"] == 0.5 for row in report["rows"])
    assert "pilot included" not in json.dumps(report)
