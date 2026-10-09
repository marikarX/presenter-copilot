"""Turn human slide-purpose labels into calibration evidence for Fast Decisions.

``export`` writes an unlabeled sheet from local PPTX files for a person to label.
``evaluate`` runs a loopback decision model over the labeled rows and reports
accuracy, confusion and a confidence-threshold table. It never edits thresholds;
a recommendation is emitted only when enough human labels exist.

Labels must come from people. Sheets and reports stay under ``.local``; do not
commit or redistribute slide text from third-party decks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from presenter_core.decisions.local import LocalChoiceDecisionProvider
from presenter_core.decisions.models import (
    ChoiceDecisionRequest,
    ChoiceQuestion,
    DecisionError,
    DecisionProvider,
)
from presenter_core.decisions.purpose import (
    SLIDE_PURPOSE_CHOICES,
    SLIDE_PURPOSE_QUESTION_INSTRUCTIONS,
)
from presenter_core.presentation.fidelity import inspect_pptx_snapshot

FIELDS = ("deck", "slide", "slide_text", "label", "labeler")
MAX_SLIDE_TEXT_CHARS = 4000
MIN_LABELS_FOR_RECOMMENDATION = 50
MIN_COVERED_FOR_RECOMMENDATION = 20
THRESHOLDS = tuple(round(0.5 + 0.05 * step, 2) for step in range(10))


def slide_texts(path: Path) -> list[tuple[int, str]]:
    data = path.read_bytes()
    with path.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=str(uuid.uuid4()),
            expected_sha256=hashlib.sha256(data).hexdigest(),
            byte_size=len(data),
        )
    rows = []
    for slide in fidelity.slides:
        parts = [obj.text.strip() for obj in slide.objects if obj.text and obj.text.strip()]
        text = "\n".join(parts)[:MAX_SLIDE_TEXT_CHARS]
        if text:
            rows.append((slide.ordinal, text))
    return rows


def export_sheet(decks: Iterable[Path], out: Path) -> int:
    count = 0
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for deck in sorted(decks):
            for ordinal, text in slide_texts(deck):
                writer.writerow(
                    {"deck": deck.name, "slide": ordinal, "slide_text": text, "label": ""}
                )
                count += 1
    return count


def labeled_rows(sheet: Path) -> list[dict[str, str]]:
    """Rows a person labeled with a supported purpose; blanks are skipped."""
    with sheet.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not {"slide_text", "label"} <= set(reader.fieldnames):
            raise ValueError("The sheet needs slide_text and label columns.")
        rows = []
        for row in reader:
            label = (row.get("label") or "").strip().lower()
            if not label:
                continue
            if label not in SLIDE_PURPOSE_CHOICES:
                raise ValueError(f"Unsupported label {label!r} on slide {row.get('slide')}.")
            text = (row.get("slide_text") or "").strip()
            if text:
                rows.append({**row, "label": label, "slide_text": text})
        return rows


def threshold_table(
    observations: Sequence[tuple[str, str, float | None]],
    *,
    target_precision: float,
) -> dict[str, Any]:
    """Coverage/precision if suggestions below each confidence threshold abstain.

    ``observations`` are (human label, model choice, model confidence). A model
    "unclear" is an abstention. Rows without confidence cannot be thresholded.
    """
    scored = [(label, choice, conf) for label, choice, conf in observations if conf is not None]
    table = []
    recommendation = None
    for threshold in THRESHOLDS:
        covered = [
            (label, choice)
            for label, choice, conf in scored
            if choice != "unclear" and conf >= threshold
        ]
        correct = sum(label == choice for label, choice in covered)
        precision = correct / len(covered) if covered else None
        table.append(
            {
                "threshold": threshold,
                "covered": len(covered),
                "coverage": round(len(covered) / len(scored), 3) if scored else None,
                "precision": round(precision, 3) if precision is not None else None,
            }
        )
        if (
            recommendation is None
            and precision is not None
            and precision >= target_precision
            and len(covered) >= MIN_COVERED_FOR_RECOMMENDATION
        ):
            recommendation = threshold
    enough = len(observations) >= MIN_LABELS_FOR_RECOMMENDATION
    return {
        "rows_with_confidence": len(scored),
        "target_precision": target_precision,
        "table": table,
        "recommended_minimum_confidence": recommendation if enough else None,
        "recommendation_status": (
            "insufficient_labels"
            if not enough
            else "no_confidence_returned"
            if not scored
            else "target_not_reached"
            if recommendation is None
            else "candidate_for_human_review"
        ),
    }


def evaluate(
    rows: Sequence[dict[str, str]],
    provider: DecisionProvider,
    *,
    target_precision: float = 0.9,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    if provider.leaves_machine:
        raise DecisionError(
            "DECISION_CALIBRATION_LOOPBACK_REQUIRED",
            "Calibration sends slide text to the model; use a loopback endpoint.",
        )
    observations: list[tuple[str, str, float | None]] = []
    failures: Counter[str] = Counter()
    latencies: list[int] = []
    for index, row in enumerate(rows, start=1):
        request = ChoiceDecisionRequest(
            state={"slide_text": [row["slide_text"]]},
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
            answer = result.answers["purpose"]
            observations.append((row["label"], answer.choice, answer.confidence))
            latencies.append(result.latency_ms)
        except DecisionError as error:
            failures[error.code] += 1
        if progress is not None:
            progress(index, len(rows))
    confusion: Counter[tuple[str, str]] = Counter(
        (label, choice) for label, choice, _ in observations
    )
    decided = [(label, choice) for label, choice, _ in observations if choice != "unclear"]
    ordered = sorted(latencies)
    return {
        "labeled_rows": len(rows),
        "answered": len(observations),
        "failures": dict(failures),
        "abstentions": sum(choice == "unclear" for _, choice, _ in observations),
        "accuracy_all": round(
            sum(label == choice for label, choice, _ in observations) / len(observations), 3
        )
        if observations
        else None,
        "precision_when_decided": round(
            sum(label == choice for label, choice in decided) / len(decided), 3
        )
        if decided
        else None,
        "label_distribution": dict(Counter(row["label"] for row in rows)),
        "confusion": [
            {"label": label, "choice": choice, "count": count}
            for (label, choice), count in sorted(confusion.items())
        ],
        "median_latency_ms": round(statistics.median(latencies)) if latencies else None,
        "p95_latency_ms": ordered[math.ceil(0.95 * len(ordered)) - 1] if ordered else None,
        "thresholds": threshold_table(observations, target_precision=target_precision),
        "confidence_calibrated": False,
        "requires_human_review_before_adoption": True,
        "raw_slide_text_emitted": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Write an unlabeled sheet from PPTX files.")
    export.add_argument("--corpus", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("evaluate", help="Evaluate a loopback model on human labels.")
    run.add_argument("--sheet", type=Path, required=True)
    run.add_argument("--model-id", required=True)
    run.add_argument("--endpoint", default="http://127.0.0.1:1234/v1")
    run.add_argument("--timeout-seconds", type=float, default=30.0)
    run.add_argument("--target-precision", type=float, default=0.9)
    run.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "export":
        decks = [p for p in args.corpus.glob("*.pptx") if "edited" not in p.name]
        print(json.dumps({"decks": len(decks), "rows": export_sheet(decks, args.out)}))
        return 0
    rows = labeled_rows(args.sheet)
    provider = LocalChoiceDecisionProvider(
        endpoint=args.endpoint, model_id=args.model_id, timeout_seconds=args.timeout_seconds
    )
    try:
        report = evaluate(rows, provider, target_precision=args.target_precision)
    finally:
        provider.close()
    report["model_id"] = args.model_id
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("labeled_rows", "answered", "accuracy_all")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
