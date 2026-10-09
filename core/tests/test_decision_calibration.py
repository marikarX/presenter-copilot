"""Calibration evidence only from human labels; thresholds are never auto-applied."""

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from presenter_core.decisions.models import DecisionError
from presenter_core.tools.decision_calibration import (
    MIN_LABELS_FOR_RECOMMENDATION,
    evaluate,
    export_sheet,
    labeled_rows,
    threshold_table,
)

FIXTURE_DECK = Path(__file__).resolve().parents[2] / "samples" / "synthetic-deck"


class FakeProvider:
    leaves_machine = False

    def __init__(self, answers):
        self.answers = list(answers)

    def decide(self, _request):
        item = self.answers.pop(0)
        if isinstance(item, DecisionError):
            raise item
        choice, confidence = item
        return SimpleNamespace(
            answers={"purpose": SimpleNamespace(choice=choice, confidence=confidence)},
            latency_ms=12,
        )


def _sheet(path: Path, rows) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["deck", "slide", "slide_text", "label"])
        writer.writeheader()
        for index, (text, label) in enumerate(rows, start=1):
            writer.writerow({"deck": "d", "slide": index, "slide_text": text, "label": label})
    return path


def test_only_human_labeled_supported_rows_are_used(tmp_path):
    sheet = _sheet(tmp_path / "s.csv", [("Agenda", "Opening"), ("Budget", ""), ("", "plan")])
    assert [row["label"] for row in labeled_rows(sheet)] == ["opening"]
    bad = _sheet(tmp_path / "bad.csv", [("Agenda", "intro")])
    with pytest.raises(ValueError):
        labeled_rows(bad)


def test_threshold_table_reports_coverage_precision_and_waits_for_enough_labels():
    few = [("plan", "plan", 0.9), ("risk", "plan", 0.6)]
    report = threshold_table(few, target_precision=0.9)
    row = next(item for item in report["table"] if item["threshold"] == 0.7)
    assert (row["covered"], row["precision"]) == (1, 1.0)
    assert report["recommendation_status"] == "insufficient_labels"
    assert report["recommended_minimum_confidence"] is None

    many = [("plan", "plan", 0.95)] * 40 + [("risk", "plan", 0.6)] * 20
    assert len(many) >= MIN_LABELS_FOR_RECOMMENDATION
    report = threshold_table(many, target_precision=0.9)
    assert report["recommendation_status"] == "candidate_for_human_review"
    assert report["recommended_minimum_confidence"] == 0.65

    no_confidence = [("plan", "plan", None)] * MIN_LABELS_FOR_RECOMMENDATION
    assert (
        threshold_table(no_confidence, target_precision=0.9)["recommendation_status"]
        == "no_confidence_returned"
    )


def test_evaluate_counts_abstentions_failures_and_never_emits_slide_text():
    rows = [
        {"slide_text": "Secret agenda text", "label": "opening"},
        {"slide_text": "Plan", "label": "plan"},
        {"slide_text": "Risk", "label": "risk"},
    ]
    report = evaluate(
        rows,
        FakeProvider(
            [("opening", 0.8), ("unclear", None), DecisionError("DECISION_PROVIDER_TIMEOUT", "x")]
        ),
    )
    assert report["answered"] == 2 and report["abstentions"] == 1
    assert report["failures"] == {"DECISION_PROVIDER_TIMEOUT": 1}
    assert report["precision_when_decided"] == 1.0
    assert report["confidence_calibrated"] is False
    assert "Secret agenda text" not in str(report)


def test_remote_providers_are_refused():
    provider = FakeProvider([])
    provider.leaves_machine = True
    with pytest.raises(DecisionError) as error:
        evaluate([{"slide_text": "x", "label": "plan"}], provider)
    assert error.value.code == "DECISION_CALIBRATION_LOOPBACK_REQUIRED"


def test_export_writes_unlabeled_rows(tmp_path):
    deck = next(FIXTURE_DECK.rglob("*.pptx"))
    out = tmp_path / "sheet.csv"
    assert export_sheet([deck], out) > 0
    with out.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and all(row["label"] == "" for row in rows)
    assert labeled_rows(out) == []
