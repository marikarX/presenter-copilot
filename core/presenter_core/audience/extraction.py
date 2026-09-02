"""Deterministic, evidence-first observable interaction-pattern extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import MAX_EVIDENCE_PER_ITEM


@dataclass(frozen=True)
class ObservationProposal:
    observation_type: str
    proposed_text: str
    confidence: float
    evidence_ids: tuple[str, ...]
    matched_segment_count: int


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
        lambda text: _is_question_like(text) and _contains_cost_topic(text),
    )
    if len(cost_units) >= 2:
        comparison_units = [item for item in cost_units if _contains_cost_comparison(item[1])]
        matched_cost_units = comparison_units if len(comparison_units) >= 2 else cost_units
        proposals.append(
            ObservationProposal(
                "question_pattern",
                (
                    "Repeatedly asks for status-quo cost comparisons."
                    if len(comparison_units) >= 2
                    else "Repeatedly asks about cost or budget."
                ),
                0.9,
                _bounded_evidence_ids(matched_cost_units),
                len(cost_units),
            )
        )

    rollback_units = _matching(
        normalized,
        lambda text: _is_question_like(text) and _contains_rollback_or_failure_topic(text),
    )
    if len(rollback_units) >= 2:
        has_rollback = any(_contains_rollback_topic(item[1]) for item in rollback_units)
        has_failure_mode = any(_contains_failure_mode_topic(item[1]) for item in rollback_units)
        if has_rollback and has_failure_mode:
            rollback_text = "Repeatedly asks about rollback or failure modes."
        elif has_rollback:
            rollback_text = "Repeatedly asks about rollback."
        else:
            rollback_text = "Repeatedly asks about failure modes."
        proposals.append(
            ObservationProposal(
                "question_pattern",
                rollback_text,
                0.9,
                _bounded_evidence_ids(rollback_units),
                len(rollback_units),
            )
        )

    schedule_units = _matching(
        normalized,
        lambda text: _is_question_like(text) and _contains_schedule_topic(text),
    )
    if len(schedule_units) >= 2:
        challenge_units = [item for item in schedule_units if _contains_schedule_challenge(item[1])]
        if len(challenge_units) >= 2:
            schedule_text = "Repeatedly challenges schedule assumptions."
            matched_schedule_units = challenge_units
        else:
            schedule_text = "Repeatedly asks about schedule or timeline."
            matched_schedule_units = schedule_units
        proposals.append(
            ObservationProposal(
                "question_pattern",
                schedule_text,
                0.88,
                _bounded_evidence_ids(matched_schedule_units),
                len(schedule_units),
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
                _bounded_evidence_ids(concise_units[:1]),
                1,
            )
        )

    ownership_units = _matching(
        normalized,
        lambda text: _is_question_like(text)
        and any(
            phrase in text for phrase in ("who owns", "ownership", "owner for", "responsible for")
        ),
    )
    if ownership_units:
        proposals.append(
            ObservationProposal(
                "interaction_pattern",
                "Requests ownership clarification.",
                0.86,
                _bounded_evidence_ids(ownership_units[:1]),
                1,
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
                _bounded_evidence_ids(evidence_units[:1]),
                1,
            )
        )
    return proposals


def _matching(units: list[tuple[str, str]], predicate: Any) -> list[tuple[str, str]]:
    return [unit for unit in units if predicate(unit[1])]


def _bounded_evidence_ids(units: list[tuple[str, str]]) -> tuple[str, ...]:
    """Retain chronological/source-ordered evidence without unbounded fan-out."""
    return tuple(item[0] for item in units[:MAX_EVIDENCE_PER_ITEM])


def _is_question_like(text: str) -> bool:
    if "?" in text:
        return True
    return bool(_QUESTION_INDICATOR_RE.search(text))


def _contains_cost_topic(text: str) -> bool:
    return any(phrase in text for phrase in ("cost", "price", "budget", "financial downside"))


def _contains_cost_comparison(text: str) -> bool:
    return _contains_cost_topic(text) and any(
        phrase in text
        for phrase in (
            "status quo",
            "status-quo",
            "compar",
            "versus",
            " vs ",
            "baseline",
        )
    )


def _contains_rollback_topic(text: str) -> bool:
    return "rollback" in text or "roll back" in text


def _contains_failure_mode_topic(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "failure mode",
            "failure modes",
            "fails",
            "fail",
            "technical migration risk",
            "migration risk",
        )
    )


def _contains_rollback_or_failure_topic(text: str) -> bool:
    return _contains_rollback_topic(text) or _contains_failure_mode_topic(text)


def _contains_schedule_topic(text: str) -> bool:
    return any(phrase in text for phrase in ("schedule", "timeline", "deadline", "delivery date"))


def _contains_schedule_challenge(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "unrealistic",
            "not realistic",
            "i disagree",
            "push back",
            "doesn't make sense",
            "does not make sense",
            "too aggressive",
            "too slow",
            "can't meet",
            "cannot meet",
            "won't meet",
            "will not meet",
            "challenge",
        )
    )


_QUESTION_INDICATOR_RE = re.compile(
    r"\b(?:who|what|why|when|where|how|which|can|could|should|would|please|"
    r"show me|give me|tell me|i need|i want|ask|asks|asked|request|requests|requested)\b",
    re.IGNORECASE,
)
