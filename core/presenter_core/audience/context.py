"""Bounded provider-neutral Audience Model context assembly."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from presenter_core.errors import CoreDomainError
from presenter_core.ingestion.service import provenance_label
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

from .models import (
    MAX_EVIDENCE_PER_ITEM,
    MAX_OBSERVATION_TEXT_LENGTH,
    MAX_OBSERVATIONS_PER_PROFILE,
    MAX_PROFILE_COUNT,
)

MAX_CONTEXT_EVIDENCE_TEXT_LENGTH = 800


class AudienceContextBuilder:
    """Build only active profiles and active, accepted observations."""

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage

    def build(
        self,
        *,
        project_id: str,
        audience_profile_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        normalized_project_id = normalize_project_id(project_id)
        requested_ids = None
        if audience_profile_ids is not None:
            requested_ids_list: list[str] = []
            if len(audience_profile_ids) > MAX_PROFILE_COUNT:
                raise CoreDomainError(
                    "INVALID_REQUEST",
                    "audience_profile_ids contains too many profiles.",
                    details={"field": "audience_profile_ids"},
                )
            for profile_id in audience_profile_ids:
                try:
                    normalized_profile_id = str(uuid.UUID(profile_id))
                except (ValueError, TypeError, AttributeError) as exc:
                    raise CoreDomainError(
                        "INVALID_REQUEST",
                        "audience_profile_ids must contain UUIDs.",
                        details={"field": "audience_profile_ids"},
                    ) from exc
                if normalized_profile_id not in requested_ids_list:
                    requested_ids_list.append(normalized_profile_id)
            requested_ids = tuple(requested_ids_list)

        with self._storage.project_database(normalized_project_id) as connection:
            clauses = ["ap.project_id = ?", "ap.active = 1"]
            parameters: list[Any] = [normalized_project_id]
            if requested_ids is not None and requested_ids:
                placeholders = ", ".join("?" for _ in requested_ids)
                clauses.append(f"ap.id IN ({placeholders})")
                parameters.extend(requested_ids)
            elif requested_ids is not None:
                clauses.append("1 = 0")
            profiles = connection.execute(
                "SELECT * FROM audience_profiles AS ap WHERE "
                + " AND ".join(clauses)
                + " ORDER BY ap.display_name COLLATE NOCASE, ap.id LIMIT ?",
                [*parameters, MAX_PROFILE_COUNT],
            ).fetchall()
            if requested_ids is not None:
                found = {str(row["id"]) for row in profiles}
                missing = [profile_id for profile_id in requested_ids if profile_id not in found]
                if missing:
                    raise CoreDomainError(
                        "AUDIENCE_PROFILE_NOT_FOUND",
                        "One or more audience profiles were not found or are inactive.",
                    )
            result_profiles = [self._profile_context(connection, profile) for profile in profiles]
        return {"project_id": normalized_project_id, "profiles": result_profiles}

    @staticmethod
    def _profile_context(connection: sqlite3.Connection, profile: sqlite3.Row) -> dict[str, Any]:
        observations = connection.execute(
            """
            SELECT * FROM audience_observations
            WHERE audience_profile_id = ? AND review_status = 'active'
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (profile["id"], MAX_OBSERVATIONS_PER_PROFILE),
        ).fetchall()
        result_observations: list[dict[str, Any]] = []
        for observation in observations:
            evidence = _valid_evidence(connection, str(observation["id"]))
            if observation["derivation"] == "source_derived" and not evidence:
                continue
            result_observations.append(
                {
                    "id": observation["id"],
                    "type": observation["observation_type"],
                    "text": str(observation["text"])[:MAX_OBSERVATION_TEXT_LENGTH],
                    "derivation": observation["derivation"],
                    "confidence": observation["confidence"],
                    "evidence": evidence,
                }
            )
        return {
            "id": profile["id"],
            "display_name": profile["display_name"],
            "role": profile["role"],
            "organization": profile["organization"],
            "user_supplied_notes": profile["user_notes"],
            "observations": result_observations,
        }


def _valid_evidence(connection: sqlite3.Connection, observation_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT aoe.provenance_type, aoe.provenance_id,
               d.id AS source_id, d.original_name,
               su.unit_type, su.ordinal, su.start_ms, su.end_ms,
               su.speaker_label, su.text
        FROM audience_observation_evidence AS aoe
        JOIN source_units AS su ON su.id = aoe.provenance_id
        JOIN documents AS d ON d.id = su.document_id
        WHERE aoe.observation_id = ? AND aoe.provenance_type = 'transcript'
          AND d.kind = 'transcript' AND su.unit_type = 'transcript_segment'
        ORDER BY d.original_name COLLATE NOCASE, su.ordinal, su.id
        LIMIT ?
        """,
        (observation_id, MAX_EVIDENCE_PER_ITEM),
    ).fetchall()
    return [
        {
            "provenance_type": row["provenance_type"],
            "provenance_id": row["provenance_id"],
            "source_type": "transcript",
            "source_id": row["source_id"],
            "source_unit_id": row["provenance_id"],
            "label": provenance_label(
                row["original_name"],
                row["unit_type"],
                row["ordinal"],
                start_ms=row["start_ms"],
                end_ms=row["end_ms"],
                speaker_label=row["speaker_label"],
                transcript=True,
            ),
            "text": str(row["text"])[:MAX_CONTEXT_EVIDENCE_TEXT_LENGTH],
        }
        for row in rows
    ]
