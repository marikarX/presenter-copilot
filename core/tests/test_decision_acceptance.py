from __future__ import annotations

import json

import pytest

from presenter_core.decisions.models import ChoiceAnswer, ChoiceDecisionResult
from presenter_core.tools import decision_acceptance


def test_acceptance_cli_can_select_ollama_without_an_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: dict[str, object] = {}

    class FakeOllamaProvider:
        id = "ollama_systemone"
        locality = "local"
        leaves_machine = False

        def __init__(self, *, model_id: str, timeout_seconds: float) -> None:
            observed["model_id"] = model_id
            observed["timeout_seconds"] = timeout_seconds
            self.model_id = model_id

        def decide(self, _request) -> ChoiceDecisionResult:
            return ChoiceDecisionResult(
                provider_id=self.id,
                model_id=f"{self.model_id}@sha256:{'a' * 64}",
                latency_ms=17,
                answers={"purpose": ChoiceAnswer(name="purpose", choice="opening")},
            )

        def close(self) -> None:
            observed["closed"] = True

    monkeypatch.setattr(
        decision_acceptance,
        "OllamaSystemOneDecisionProvider",
        FakeOllamaProvider,
    )

    assert decision_acceptance.main(["--provider-id", "ollama_systemone"]) == 0
    output = capsys.readouterr().out
    report = json.loads(output)

    assert observed == {
        "model_id": "tev1:4b",
        "timeout_seconds": 10.0,
        "closed": True,
    }
    assert report["provider_id"] == "ollama_systemone"
    assert report["configured_model_id"] == "tev1:4b"
    assert report["resolved_model_ids"] == [f"tev1:4b@sha256:{'a' * 64}"]
    assert report["valid_structured_responses"] == 10
    assert report["presentation_content_used"] is False
    assert "Revenue grew" not in output


def test_ollama_acceptance_rejects_custom_endpoints(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        decision_acceptance.main(
            [
                "--provider-id",
                "ollama_systemone",
                "--model-id",
                "tev1:0.8b",
                "--endpoint",
                "http://127.0.0.1:1234/v1",
            ]
        )

    assert error.value.code == 2
    assert "--endpoint is not configurable" in capsys.readouterr().err
