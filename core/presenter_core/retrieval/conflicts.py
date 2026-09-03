"""Conservative, deterministic exact-fact conflict detection."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from presenter_core.ingestion.parsers.utils import lexical_normalize

_CURRENCY = re.compile(r"(?P<symbol>[$€£])\s*(?P<number>\d[\d,]*(?:\.\d+)?)")
_PERCENT = re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*%")
_DURATION = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>milliseconds?|seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "be",
        "for",
        "how",
        "is",
        "of",
        "the",
        "to",
        "was",
        "what",
        "which",
        "with",
    }
)


@dataclass(frozen=True)
class ExtractedFactValue:
    normalized_value: str
    value_type: str
    start: int
    end: int


def detect_conflicts(
    query: str,
    evidence_items: Iterable[Mapping[str, Any]],
    *,
    require_query_number_match: bool = True,
) -> list[dict[str, Any]]:
    """Return only high-signal incompatible values sharing query context.

    The default preserves the M2/M5 retrieval contract.  Run debrief can opt
    into context-only conflict detection because its claim text is the
    authoritative query and may not contain every value found in evidence.
    """
    query_tokens = set(lexical_normalize(query).split())
    query_number_tokens = {token for token in query_tokens if any(c.isdigit() for c in token)}
    context_tokens = query_tokens.difference(_STOP_WORDS).difference(query_number_tokens)
    if not context_tokens:
        return []

    values_by_value: dict[str, set[str]] = defaultdict(set)
    labels_by_evidence: dict[str, str] = {}
    types_by_value: dict[str, str] = {}
    for item in evidence_items:
        evidence = item.get("evidence")
        if not isinstance(evidence, Mapping):
            continue
        evidence_id = evidence.get("evidence_id")
        label = evidence.get("label")
        text = evidence.get("text")
        if (
            not isinstance(evidence_id, str)
            or not isinstance(label, str)
            or not isinstance(text, str)
        ):
            continue
        body_tokens = set(lexical_normalize(text).split())
        if not context_tokens.intersection(body_tokens):
            continue
        extracted = extract_fact_values(text)
        if (
            require_query_number_match
            and query_number_tokens
            and not _contains_query_number(text, query_number_tokens)
        ):
            continue
        labels_by_evidence[evidence_id] = label
        for value in extracted:
            values_by_value[value.normalized_value].add(evidence_id)
            types_by_value[value.normalized_value] = value.value_type

    if len(values_by_value) < 2:
        return []
    ordered_values = sorted(values_by_value)
    conflicting_values = [
        {
            "normalized_value": value,
            "value_type": types_by_value[value],
            "evidence_ids": sorted(values_by_value[value]),
        }
        for value in ordered_values
    ]
    evidence_refs = [
        {"evidence_id": evidence_id, "label": labels_by_evidence[evidence_id]}
        for evidence_id in sorted(labels_by_evidence)
        if any(evidence_id in value["evidence_ids"] for value in conflicting_values)
    ]
    query_lower = query.casefold()
    subject = "RTO" if re.search(r"\brto\b", query_lower) else " ".join(sorted(context_tokens)[:4])
    value_types = {value["value_type"] for value in conflicting_values}
    return [
        {
            "kind": "numeric",
            "subject": subject or "numeric fact",
            "value_type": next(iter(value_types)) if len(value_types) == 1 else "mixed",
            "values": conflicting_values,
            "evidence": evidence_refs,
        }
    ]


def extract_fact_values(text: str) -> list[ExtractedFactValue]:
    """Extract currency, percentages, durations, and standalone numbers once."""
    matches: list[ExtractedFactValue] = []
    occupied: list[tuple[int, int]] = []
    for match in _CURRENCY.finditer(text):
        matches.append(
            ExtractedFactValue(
                normalized_value=f"{match.group('symbol')}{_normalize_number(match.group('number'))}",
                value_type="currency",
                start=match.start(),
                end=match.end(),
            )
        )
        occupied.append((match.start(), match.end()))
    for match in _PERCENT.finditer(text):
        if _overlaps(match.start(), match.end(), occupied):
            continue
        matches.append(
            ExtractedFactValue(
                normalized_value=f"{_normalize_number(match.group('number'))}%",
                value_type="percentage",
                start=match.start(),
                end=match.end(),
            )
        )
        occupied.append((match.start(), match.end()))
    for match in _DURATION.finditer(text):
        if _overlaps(match.start(), match.end(), occupied):
            continue
        unit = match.group("unit").casefold()
        if unit.endswith("s"):
            unit = unit[:-1]
        matches.append(
            ExtractedFactValue(
                normalized_value=f"{_normalize_number(match.group('number'))} {unit}s",
                value_type="duration",
                start=match.start(),
                end=match.end(),
            )
        )
        occupied.append((match.start(), match.end()))
    for match in _NUMBER.finditer(text):
        if _overlaps(match.start(), match.end(), occupied):
            continue
        matches.append(
            ExtractedFactValue(
                normalized_value=_normalize_number(match.group(0)),
                value_type="number",
                start=match.start(),
                end=match.end(),
            )
        )
    return sorted(matches, key=lambda value: (value.start, value.end, value.normalized_value))


def _contains_query_number(text: str, query_number_tokens: set[str]) -> bool:
    normalized = lexical_normalize(text)
    return any(token in normalized.split() for token in query_number_tokens)


def _normalize_number(value: str) -> str:
    number = value.replace(",", "")
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return number or "0"


def _overlaps(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(
        start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied
    )
