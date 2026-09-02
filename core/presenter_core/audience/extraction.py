"""Deterministic, evidence-first observable interaction-pattern extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ObservationProposal:
    observation_type: str
    proposed_text: str
    confidence: float
    evidence_ids: tuple[str, ...]


def extract_observable_patterns(units: list[dict[str, Any]]) -> list[ObservationProposal]:
    """Extract only explicit questions/requests using bounded local rules.

    Repeated wording requires two distinct SourceUnits.  One explicit request
    can support a preference or decision criterion, but utterance length alone
    is never treated as a preference signal.
    """
    normalized = [
        (str(unit["id"]), str(unit["text"]).casefold())
        for unit in units
        if isinstance(unit.get("id"), str) and isinstance(unit.get("text"), str)
    ]
    proposals: list[ObservationProposal] = []

    cost_units = _matching(
        normalized,
        lambda text: (
            "cost" in text
            or "price" in text
            or "budget" in text
            or "status quo" in text
            or "status-quo" in text
            or "financial downside" in text
        ),
    )
    if len(cost_units) >= 2:
        proposals.append(
            ObservationProposal(
                "question_pattern",
                "Repeatedly asks for status-quo cost comparisons.",
                0.9,
                tuple(item[0] for item in cost_units),
            )
        )

    rollback_units = _matching(
        normalized,
        lambda text: any(
            phrase in text
            for phrase in (
                "rollback",
                "roll back",
                "failure mode",
                "failure modes",
                "fails",
                "technical migration risk",
                "migration risk",
            )
        ),
    )
    if len(rollback_units) >= 2:
        proposals.append(
            ObservationProposal(
                "question_pattern",
                "Repeatedly asks about rollback and failure modes.",
                0.9,
                tuple(item[0] for item in rollback_units),
            )
        )

    schedule_units = _matching(
        normalized,
        lambda text: any(
            phrase in text for phrase in ("schedule", "timeline", "deadline", "delivery date")
        ),
    )
    if len(schedule_units) >= 2:
        proposals.append(
            ObservationProposal(
                "question_pattern",
                "Repeatedly challenges schedule assumptions.",
                0.88,
                tuple(item[0] for item in schedule_units),
            )
        )

    concise_units = _matching(
        normalized,
        lambda text: any(
            phrase in text
            for phrase in (
                "short version",
                "short answer",
                "brief answer",
                "be concise",
                "concise answer",
                "direct answer",
                "bottom line",
                "tl;dr",
            )
        ),
    )
    if concise_units:
        proposals.append(
            ObservationProposal(
                "answer_preference",
                "Explicitly requests concise answers.",
                0.95,
                (concise_units[0][0],),
            )
        )

    ownership_units = _matching(
        normalized,
        lambda text: any(
            phrase in text for phrase in ("who owns", "ownership", "owner for", "responsible for")
        ),
    )
    if ownership_units:
        proposals.append(
            ObservationProposal(
                "interaction_pattern",
                "Requests ownership clarification.",
                0.86,
                (ownership_units[0][0],),
            )
        )

    evidence_units = _matching(
        normalized,
        lambda text: (
            ("evidence" in text or "proof" in text or "show me" in text)
            and any(term in text for term in ("number", "numeric", "claim", "data", "cost"))
        ),
    )
    if evidence_units:
        proposals.append(
            ObservationProposal(
                "decision_criterion",
                "Requests evidence for numeric claims.",
                0.9,
                (evidence_units[0][0],),
            )
        )
    return proposals


def _matching(units: list[tuple[str, str]], predicate: Any) -> list[tuple[str, str]]:
    return [unit for unit in units if predicate(unit[1])]
