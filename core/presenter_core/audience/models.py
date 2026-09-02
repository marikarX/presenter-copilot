"""Audience Model enums and bounded limits."""

from __future__ import annotations

from typing import Final

OBSERVATION_TYPES: Final[frozenset[str]] = frozenset(
    {
        "topic_interest",
        "question_pattern",
        "answer_preference",
        "recurring_objection",
        "interaction_pattern",
        "decision_criterion",
    }
)
DERIVATIONS: Final[frozenset[str]] = frozenset({"user_entered", "source_derived", "ai_inferred"})
REVIEW_STATUSES: Final[frozenset[str]] = frozenset({"active", "stale"})
CANDIDATE_STATUSES: Final[frozenset[str]] = frozenset({"pending", "accepted", "rejected", "stale"})

MAX_PROFILE_DISPLAY_NAME_LENGTH: Final = 120
MAX_PROFILE_ROLE_LENGTH: Final = 200
MAX_PROFILE_ORGANIZATION_LENGTH: Final = 200
MAX_PROFILE_NOTES_LENGTH: Final = 4_000
MAX_OBSERVATION_TEXT_LENGTH: Final = 1_500
MAX_PROFILE_COUNT: Final = 100
MAX_OBSERVATIONS_PER_PROFILE: Final = 100
MAX_CANDIDATES_PER_PROFILE: Final = 100
MAX_EVIDENCE_PER_ITEM: Final = 20
MAX_DOCUMENT_FILTER_COUNT: Final = 100
MAX_EXTRACTION_SEGMENTS: Final = 5_000
