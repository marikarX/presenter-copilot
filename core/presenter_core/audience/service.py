"""Project-local AudienceProfile and reviewed observation lifecycle."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterable
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.ingestion.service import provenance_label
from presenter_core.project.service import utc_now
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

from .context import MAX_CONTEXT_PROFILES, AudienceContextBuilder
from .extraction import extract_observable_patterns
from .models import (
    MAX_CANDIDATES_PER_PROFILE,
    MAX_DOCUMENT_FILTER_COUNT,
    MAX_EVIDENCE_PER_ITEM,
    MAX_EXTRACTION_SEGMENTS,
    MAX_OBSERVATION_TEXT_LENGTH,
    MAX_OBSERVATIONS_PER_PROFILE,
    MAX_PROFILE_COUNT,
    MAX_PROFILE_DISPLAY_NAME_LENGTH,
    MAX_PROFILE_NOTES_LENGTH,
    MAX_PROFILE_ORGANIZATION_LENGTH,
    MAX_PROFILE_ROLE_LENGTH,
    OBSERVATION_TYPES,
)
from .policy import ObservationPolicy


class AudienceModelService:
    """Keep profile ownership, attribution, evidence, and review state explicit."""

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage
        self._context_builder = AudienceContextBuilder(storage)

    def create(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "display_name", "role", "organization", "user_notes", "active"},
        )
        project_id = self._project_id(params)
        display_name = self._required_text(
            params, "display_name", max_length=MAX_PROFILE_DISPLAY_NAME_LENGTH
        )
        role = self._optional_text(params, "role", max_length=MAX_PROFILE_ROLE_LENGTH)
        organization = self._optional_text(
            params, "organization", max_length=MAX_PROFILE_ORGANIZATION_LENGTH
        )
        user_notes = self._profile_notes(params)
        active = self._bool_param(params, "active", default=True)
        profile_id = str(uuid.uuid4())
        now = utc_now()
        with self._storage.project_database(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_capacity(
                connection,
                "SELECT COUNT(*) AS count FROM audience_profiles WHERE project_id = ?",
                (project_id,),
                limit=MAX_PROFILE_COUNT,
                code="AUDIENCE_PROFILE_LIMIT_REACHED",
                message="This project already has the maximum number of audience profiles.",
                details={"max_profiles": MAX_PROFILE_COUNT},
            )
            connection.execute(
                """
                INSERT INTO audience_profiles (
                    id, project_id, display_name, role, organization, user_notes,
                    active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    project_id,
                    display_name,
                    role,
                    organization,
                    user_notes,
                    int(active),
                    now,
                    now,
                ),
            )
            connection.commit()
            row = self._profile_row(connection, project_id, profile_id)
            return {"profile": self._profile_dict(row)}

    def update(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "audience_profile_id",
                "display_name",
                "role",
                "organization",
                "user_notes",
                "active",
            },
        )
        project_id = self._project_id(params)
        profile_id = self._uuid_param(params, "audience_profile_id")
        editable = {"display_name", "role", "organization", "user_notes", "active"}
        if not editable.intersection(params):
            raise invalid_request("At least one audience profile field is required.")
        with self._storage.project_database(project_id) as connection:
            current = self._profile_row(connection, project_id, profile_id)
            values: dict[str, Any] = {
                "display_name": current["display_name"],
                "role": current["role"],
                "organization": current["organization"],
                "user_notes": current["user_notes"],
                "active": bool(current["active"]),
            }
            if "display_name" in params:
                values["display_name"] = self._required_text(
                    params, "display_name", max_length=MAX_PROFILE_DISPLAY_NAME_LENGTH
                )
            if "role" in params:
                values["role"] = self._optional_text(
                    params, "role", max_length=MAX_PROFILE_ROLE_LENGTH
                )
            if "organization" in params:
                values["organization"] = self._optional_text(
                    params, "organization", max_length=MAX_PROFILE_ORGANIZATION_LENGTH
                )
            if "user_notes" in params:
                values["user_notes"] = self._profile_notes(params)
            if "active" in params:
                values["active"] = self._bool_param(params, "active", default=True)
            if values["user_notes"] is not None:
                ObservationPolicy.validate_text(str(values["user_notes"]))
            now = utc_now()
            connection.execute(
                """
                UPDATE audience_profiles
                SET display_name = ?, role = ?, organization = ?, user_notes = ?,
                    active = ?, updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    values["display_name"],
                    values["role"],
                    values["organization"],
                    values["user_notes"],
                    int(values["active"]),
                    now,
                    profile_id,
                    project_id,
                ),
            )
            connection.commit()
            row = self._profile_row(connection, project_id, profile_id)
            return {"profile": self._profile_dict(row)}

    def list_profiles(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id"})
        project_id = self._project_id(params)
        with self._storage.project_database(project_id) as connection:
            rows = connection.execute(
                """
                SELECT * FROM audience_profiles
                WHERE project_id = ?
                ORDER BY active DESC, display_name COLLATE NOCASE, id
                LIMIT ?
                """,
                (project_id, MAX_PROFILE_COUNT),
            ).fetchall()
            return {"profiles": [self._profile_dict(row) for row in rows]}

    def delete(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "audience_profile_id"})
        project_id = self._project_id(params)
        profile_id = self._uuid_param(params, "audience_profile_id")
        with self._storage.project_database(project_id) as connection:
            self._profile_row(connection, project_id, profile_id)
            connection.execute(
                """
                UPDATE transcript_speaker_maps
                SET audience_profile_id = NULL
                WHERE audience_profile_id = ?
                """,
                (profile_id,),
            )
            cursor = connection.execute(
                "DELETE FROM audience_profiles WHERE id = ? AND project_id = ?",
                (profile_id, project_id),
            )
            connection.commit()
            return {
                "project_id": project_id,
                "audience_profile_id": profile_id,
                "deleted": cursor.rowcount == 1,
            }

    def extract_observations(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "audience_profile_id", "document_ids"},
        )
        project_id = self._project_id(params)
        profile_id = self._uuid_param(params, "audience_profile_id")
        document_ids = self._document_ids(params)
        with self._storage.project_database(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._profile_row(connection, project_id, profile_id)
            self._validate_document_filters(connection, project_id, document_ids)
            clauses = [
                "d.project_id = ?",
                "d.kind = 'transcript'",
                "d.parse_status = 'ready'",
                "su.unit_type = 'transcript_segment'",
                "su.speaker_label IS NOT NULL",
                "tsm.audience_profile_id = ?",
                "tsm.native_speaker_label = su.speaker_label",
            ]
            query_parameters: list[Any] = [project_id, profile_id]
            if document_ids:
                placeholders = ", ".join("?" for _ in document_ids)
                clauses.append(f"d.id IN ({placeholders})")
                query_parameters.extend(document_ids)
            unit_rows = connection.execute(
                """
                SELECT su.id, su.text
                FROM source_units AS su
                JOIN documents AS d ON d.id = su.document_id
                JOIN transcript_speaker_maps AS tsm ON tsm.document_id = d.id
                WHERE """
                + " AND ".join(clauses)
                + " ORDER BY d.original_name COLLATE NOCASE, su.ordinal, su.id LIMIT ?",
                [*query_parameters, MAX_EXTRACTION_SEGMENTS + 1],
            ).fetchall()
            if len(unit_rows) > MAX_EXTRACTION_SEGMENTS:
                raise CoreDomainError(
                    "AUDIENCE_EXTRACTION_TOO_LARGE",
                    "Audience extraction matched too many transcript segments; select or filter "
                    "transcript document IDs.",
                    details={
                        "max_segments": MAX_EXTRACTION_SEGMENTS,
                        "document_filter_required": True,
                    },
                )
            units = [{"id": row["id"], "text": row["text"]} for row in unit_rows]
            proposals = extract_observable_patterns(units)
            created: list[dict[str, Any]] = []
            skipped_duplicates = 0
            matched_segment_count = sum(proposal.matched_segment_count for proposal in proposals)
            evidence_segment_count = 0
            now = utc_now()
            for proposal in proposals:
                evidence_ids = tuple(proposal.evidence_ids[:MAX_EVIDENCE_PER_ITEM])
                fingerprint = self._fingerprint(
                    profile_id,
                    proposal.observation_type,
                    proposal.proposed_text,
                    evidence_ids,
                )
                existing = connection.execute(
                    """
                    SELECT id FROM audience_observation_candidates
                    WHERE audience_profile_id = ? AND fingerprint = ?
                      AND status IN ('pending', 'accepted', 'rejected')
                    """,
                    (profile_id, fingerprint),
                ).fetchone()
                if existing is not None:
                    skipped_duplicates += 1
                    continue
                self._ensure_capacity(
                    connection,
                    "SELECT COUNT(*) AS count FROM audience_observation_candidates "
                    "WHERE audience_profile_id = ?",
                    (profile_id,),
                    limit=MAX_CANDIDATES_PER_PROFILE,
                    code="AUDIENCE_CANDIDATE_LIMIT_REACHED",
                    message="This audience profile already has the maximum number of candidates.",
                    details={"max_candidates_per_profile": MAX_CANDIDATES_PER_PROFILE},
                )
                ObservationPolicy.validate_text(proposal.proposed_text)
                candidate_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO audience_observation_candidates (
                        id, audience_profile_id, observation_type, proposed_text,
                        confidence, fingerprint, status, observation_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
                    """,
                    (
                        candidate_id,
                        profile_id,
                        proposal.observation_type,
                        proposal.proposed_text,
                        proposal.confidence,
                        fingerprint,
                        now,
                        now,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO audience_observation_candidate_evidence
                        (candidate_id, provenance_type, provenance_id)
                    VALUES (?, 'transcript', ?)
                    """,
                    [(candidate_id, evidence_id) for evidence_id in evidence_ids],
                )
                evidence_segment_count += len(evidence_ids)
                created.append(
                    {
                        **self._candidate_dict(
                            connection,
                            self._candidate_row(connection, project_id, candidate_id),
                        ),
                        "matched_segment_count": proposal.matched_segment_count,
                        "evidence_segment_count": len(evidence_ids),
                    }
                )
            connection.commit()
            return {
                "project_id": project_id,
                "audience_profile_id": profile_id,
                "created_candidate_count": len(created),
                "skipped_duplicate_count": skipped_duplicates,
                "matched_segment_count": matched_segment_count,
                "evidence_segment_count": evidence_segment_count,
                "candidates": created,
            }

    def list_observations(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "audience_profile_id"})
        project_id = self._project_id(params)
        profile_id = self._optional_uuid(params, "audience_profile_id")
        with self._storage.project_database(project_id) as connection:
            if profile_id is not None:
                self._profile_row(connection, project_id, profile_id)
            clauses = ["ao.audience_profile_id = ?"]
            parameters: list[Any] = [profile_id] if profile_id else []
            if profile_id is None:
                clauses = ["ap.project_id = ?"]
                parameters = [project_id]
            else:
                clauses = ["ao.audience_profile_id = ?"]
            observations = connection.execute(
                """
                SELECT ao.*
                FROM audience_observations AS ao
                JOIN audience_profiles AS ap ON ap.id = ao.audience_profile_id
                WHERE """
                + " AND ".join(clauses)
                + " ORDER BY ao.updated_at DESC, ao.id DESC LIMIT ?",
                [*parameters, MAX_PROFILE_COUNT * MAX_OBSERVATIONS_PER_PROFILE],
            ).fetchall()
            candidate_clauses = ["ac.audience_profile_id = ?"]
            candidate_parameters: list[Any] = [profile_id] if profile_id else []
            if profile_id is None:
                candidate_clauses = ["ap.project_id = ?"]
                candidate_parameters = [project_id]
            candidates = connection.execute(
                """
                SELECT ac.*
                FROM audience_observation_candidates AS ac
                JOIN audience_profiles AS ap ON ap.id = ac.audience_profile_id
                WHERE """
                + " AND ".join(candidate_clauses)
                + " ORDER BY ac.updated_at DESC, ac.id DESC LIMIT ?",
                [*candidate_parameters, MAX_PROFILE_COUNT * MAX_CANDIDATES_PER_PROFILE],
            ).fetchall()
            return {
                "observations": [self._observation_dict(connection, row) for row in observations],
                "candidates": [self._candidate_dict(connection, row) for row in candidates],
            }

    def accept_observation(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "candidate_id", "text", "observation_type"},
        )
        project_id = self._project_id(params)
        candidate_id = self._uuid_param(params, "candidate_id")
        with self._storage.project_database(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            candidate = self._candidate_row(connection, project_id, candidate_id)
            if candidate["status"] == "stale":
                raise CoreDomainError(
                    "AUDIENCE_CANDIDATE_STALE",
                    "This suggestion is stale because speaker attribution changed.",
                )
            if candidate["status"] != "pending":
                raise CoreDomainError(
                    "AUDIENCE_CANDIDATE_NOT_PENDING",
                    "Only pending audience suggestions can be accepted.",
                )
            profile_id = str(candidate["audience_profile_id"])
            self._profile_row(connection, project_id, profile_id)
            evidence_ids = self._candidate_evidence_ids(connection, candidate_id)
            if len(evidence_ids) > MAX_EVIDENCE_PER_ITEM:
                raise CoreDomainError(
                    "AUDIENCE_EVIDENCE_LIMIT_REACHED",
                    "This suggestion contains more evidence segments than supported.",
                    details={"max_evidence_per_item": MAX_EVIDENCE_PER_ITEM},
                )
            if not self._evidence_attributed_to_profile(
                connection, project_id, evidence_ids, profile_id
            ):
                connection.execute(
                    "UPDATE audience_observation_candidates "
                    "SET status = 'stale', updated_at = ? WHERE id = ?",
                    (utc_now(), candidate_id),
                )
                connection.commit()
                raise CoreDomainError(
                    "AUDIENCE_CANDIDATE_STALE",
                    "This suggestion is stale because speaker attribution changed.",
                )
            observation_type = params.get("observation_type", candidate["observation_type"])
            self._validate_observation_type(observation_type)
            text = params.get("text", candidate["proposed_text"])
            bounded_text = self._observation_text(text)
            ObservationPolicy.validate_text(bounded_text)
            self._ensure_capacity(
                connection,
                "SELECT COUNT(*) AS count FROM audience_observations WHERE audience_profile_id = ?",
                (profile_id,),
                limit=MAX_OBSERVATIONS_PER_PROFILE,
                code="AUDIENCE_OBSERVATION_LIMIT_REACHED",
                message="This audience profile already has the maximum number of observations.",
                details={"max_observations_per_profile": MAX_OBSERVATIONS_PER_PROFILE},
            )
            observation_id = str(uuid.uuid4())
            now = utc_now()
            connection.execute(
                """
                INSERT INTO audience_observations (
                    id, audience_profile_id, observation_type, text, derivation,
                    confidence, sensitive_trait, review_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'source_derived', ?, 0, 'active', ?, ?)
                """,
                (
                    observation_id,
                    profile_id,
                    observation_type,
                    bounded_text,
                    candidate["confidence"],
                    now,
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO audience_observation_evidence
                    (observation_id, provenance_type, provenance_id)
                VALUES (?, 'transcript', ?)
                """,
                [(observation_id, evidence_id) for evidence_id in evidence_ids],
            )
            connection.execute(
                """
                UPDATE audience_observation_candidates
                SET observation_type = ?, proposed_text = ?, status = 'accepted',
                    observation_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (observation_type, bounded_text, observation_id, now, candidate_id),
            )
            connection.commit()
            observation = self._observation_row(connection, project_id, observation_id)
            return {
                "observation": self._observation_dict(connection, observation),
                "candidate": self._candidate_dict(
                    connection, self._candidate_row(connection, project_id, candidate_id)
                ),
            }

    def reject_observation(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "candidate_id"})
        project_id = self._project_id(params)
        candidate_id = self._uuid_param(params, "candidate_id")
        with self._storage.project_database(project_id) as connection:
            candidate = self._candidate_row(connection, project_id, candidate_id)
            if candidate["status"] == "stale":
                raise CoreDomainError(
                    "AUDIENCE_CANDIDATE_STALE",
                    "This suggestion is stale because speaker attribution changed.",
                )
            if candidate["status"] != "pending":
                raise CoreDomainError(
                    "AUDIENCE_CANDIDATE_NOT_PENDING",
                    "Only pending audience suggestions can be rejected.",
                )
            connection.execute(
                "UPDATE audience_observation_candidates "
                "SET status = 'rejected', updated_at = ? WHERE id = ?",
                (utc_now(), candidate_id),
            )
            connection.commit()
            return {
                "project_id": project_id,
                "candidate_id": candidate_id,
                "status": "rejected",
            }

    def create_observation(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "audience_profile_id", "observation_type", "text"}
        )
        project_id = self._project_id(params)
        profile_id = self._uuid_param(params, "audience_profile_id")
        observation_type = params.get("observation_type")
        self._validate_observation_type(observation_type)
        text = self._observation_text(params.get("text"))
        ObservationPolicy.validate_text(text)
        observation_id = str(uuid.uuid4())
        now = utc_now()
        with self._storage.project_database(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._profile_row(connection, project_id, profile_id)
            self._ensure_capacity(
                connection,
                "SELECT COUNT(*) AS count FROM audience_observations WHERE audience_profile_id = ?",
                (profile_id,),
                limit=MAX_OBSERVATIONS_PER_PROFILE,
                code="AUDIENCE_OBSERVATION_LIMIT_REACHED",
                message="This audience profile already has the maximum number of observations.",
                details={"max_observations_per_profile": MAX_OBSERVATIONS_PER_PROFILE},
            )
            connection.execute(
                """
                INSERT INTO audience_observations (
                    id, audience_profile_id, observation_type, text, derivation,
                    confidence, sensitive_trait, review_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'user_entered', NULL, 0, 'active', ?, ?)
                """,
                (observation_id, profile_id, observation_type, text, now, now),
            )
            connection.commit()
            row = self._observation_row(connection, project_id, observation_id)
            return {"observation": self._observation_dict(connection, row)}

    def update_observation(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "observation_id", "observation_type", "text"},
        )
        project_id = self._project_id(params)
        observation_id = self._uuid_param(params, "observation_id")
        if "observation_type" not in params and "text" not in params:
            raise invalid_request("At least one observation field is required.")
        with self._storage.project_database(project_id) as connection:
            current = self._observation_row(connection, project_id, observation_id)
            observation_type = current["observation_type"]
            text = current["text"]
            if "observation_type" in params:
                observation_type = params["observation_type"]
                self._validate_observation_type(observation_type)
            if "text" in params:
                text = self._observation_text(params["text"])
            ObservationPolicy.validate_text(text)
            now = utc_now()
            connection.execute(
                """
                UPDATE audience_observations
                SET observation_type = ?, text = ?, updated_at = ?
                WHERE id = ? AND audience_profile_id = ?
                """,
                (observation_type, text, now, observation_id, current["audience_profile_id"]),
            )
            connection.commit()
            updated = self._observation_row(connection, project_id, observation_id)
            return {"observation": self._observation_dict(connection, updated)}

    def delete_observation(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "observation_id"})
        project_id = self._project_id(params)
        observation_id = self._uuid_param(params, "observation_id")
        with self._storage.project_database(project_id) as connection:
            self._observation_row(connection, project_id, observation_id)
            cursor = connection.execute(
                "DELETE FROM audience_observations WHERE id = ?", (observation_id,)
            )
            connection.commit()
            return {
                "project_id": project_id,
                "observation_id": observation_id,
                "deleted": cursor.rowcount == 1,
            }

    def build_context(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "audience_profile_ids"})
        project_id = self._project_id(params)
        profile_ids = params.get("audience_profile_ids")
        if profile_ids is not None and (
            not isinstance(profile_ids, list) or len(profile_ids) > MAX_CONTEXT_PROFILES
        ):
            raise invalid_request(
                "audience_profile_ids must be a bounded list of UUIDs.",
                field="audience_profile_ids",
            )
        normalized_ids = None
        if profile_ids is not None:
            normalized_ids = [self._uuid_param({"value": value}, "value") for value in profile_ids]
        return self._context_builder.build(
            project_id=project_id,
            audience_profile_ids=normalized_ids,
        )

    def build_context_for_connection(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        audience_profile_ids: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        """Reuse M4 context policy inside a caller-owned project transaction."""
        return self._context_builder.build_with_connection(
            connection,
            project_id=project_id,
            audience_profile_ids=audience_profile_ids,
        )

    def before_source_delete(self, connection: sqlite3.Connection, document_id: str) -> None:
        """Remove source evidence before document cascade while retaining stale rows."""
        unit_ids = self._source_unit_ids(connection, document_id)
        self._invalidate_source_evidence(connection, unit_ids)

    def after_source_reindex(
        self,
        connection: sqlite3.Connection,
        document_id: str,
        previous_unit_ids: set[str],
    ) -> None:
        """Remove provenance for SourceUnits that disappeared during re-index."""
        current_unit_ids = self._source_unit_ids(connection, document_id)
        self._invalidate_source_evidence(connection, previous_unit_ids - current_unit_ids)

    @staticmethod
    def _source_unit_ids(connection: sqlite3.Connection, document_id: str) -> set[str]:
        rows = connection.execute(
            "SELECT id FROM source_units WHERE document_id = ?", (document_id,)
        ).fetchall()
        return {str(row["id"]) for row in rows}

    @staticmethod
    def _invalidate_source_evidence(connection: sqlite3.Connection, unit_ids: set[str]) -> None:
        if not unit_ids:
            return
        ordered_unit_ids = sorted(unit_ids)
        placeholders = ", ".join("?" for _ in ordered_unit_ids)
        now = utc_now()
        connection.execute(
            f"""
            UPDATE audience_observations
            SET review_status = 'stale', updated_at = ?
            WHERE derivation = 'source_derived'
              AND id IN (
                  SELECT observation_id
                  FROM audience_observation_evidence
                  WHERE provenance_type = 'transcript'
                    AND provenance_id IN ({placeholders})
              )""",
            [now, *ordered_unit_ids],
        )
        connection.execute(
            f"""
            UPDATE audience_observation_candidates
            SET status = 'stale', updated_at = ?
            WHERE status IN ('pending', 'stale')
              AND id IN (
                  SELECT candidate_id
                  FROM audience_observation_candidate_evidence
                  WHERE provenance_type = 'transcript'
                    AND provenance_id IN ({placeholders})
              )""",
            [now, *ordered_unit_ids],
        )
        connection.execute(
            "DELETE FROM audience_observation_evidence "
            "WHERE provenance_type = 'transcript' AND provenance_id IN (" + placeholders + ")",
            ordered_unit_ids,
        )
        connection.execute(
            "DELETE FROM audience_observation_candidate_evidence "
            "WHERE provenance_type = 'transcript' AND provenance_id IN (" + placeholders + ")",
            ordered_unit_ids,
        )

    def revalidate_attribution(self, connection: sqlite3.Connection) -> None:
        """Mark derived rows stale when exact evidence is not currently attributed."""
        observation_rows = connection.execute(
            """
            SELECT id, audience_profile_id
            FROM audience_observations
            WHERE derivation = 'source_derived'
            """
        ).fetchall()
        for row in observation_rows:
            evidence_ids = self._observation_evidence_ids(connection, str(row["id"]))
            valid = self._evidence_attributed_to_profile(
                connection, None, evidence_ids, str(row["audience_profile_id"])
            )
            connection.execute(
                "UPDATE audience_observations SET review_status = ? WHERE id = ?",
                ("active" if evidence_ids and valid else "stale", row["id"]),
            )

        candidate_rows = connection.execute(
            """
            SELECT id, audience_profile_id, status
            FROM audience_observation_candidates
            WHERE status IN ('pending', 'stale')
            """
        ).fetchall()
        for row in candidate_rows:
            evidence_ids = self._candidate_evidence_ids(connection, str(row["id"]))
            valid = self._evidence_attributed_to_profile(
                connection, None, evidence_ids, str(row["audience_profile_id"])
            )
            connection.execute(
                "UPDATE audience_observation_candidates "
                "SET status = ?, updated_at = ? WHERE id = ?",
                ("pending" if evidence_ids and valid else "stale", utc_now(), row["id"]),
            )

    @staticmethod
    def _evidence_attributed_to_profile(
        connection: sqlite3.Connection,
        project_id: str | None,
        evidence_ids: list[str],
        profile_id: str,
    ) -> bool:
        if not evidence_ids:
            return False
        placeholders = ", ".join("?" for _ in evidence_ids)
        clauses = [
            f"su.id IN ({placeholders})",
            "d.kind = 'transcript'",
            "d.parse_status = 'ready'",
            "su.unit_type = 'transcript_segment'",
            "tsm.audience_profile_id = ?",
            "tsm.native_speaker_label = su.speaker_label",
        ]
        parameters: list[Any] = [*evidence_ids, profile_id]
        if project_id is not None:
            clauses.append("d.project_id = ?")
            parameters.append(project_id)
        row = connection.execute(
            """
            SELECT COUNT(DISTINCT su.id) AS count
            FROM source_units AS su
            JOIN documents AS d ON d.id = su.document_id
            JOIN transcript_speaker_maps AS tsm ON tsm.document_id = d.id
            WHERE """
            + " AND ".join(clauses),
            parameters,
        ).fetchone()
        return bool(row and int(row["count"]) == len(set(evidence_ids)))

    @staticmethod
    def _profile_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "display_name": row["display_name"],
            "role": row["role"],
            "organization": row["organization"],
            "user_notes": row["user_notes"],
            "active": bool(row["active"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _observation_dict(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "audience_profile_id": row["audience_profile_id"],
            "observation_type": row["observation_type"],
            "text": row["text"],
            "derivation": row["derivation"],
            "confidence": row["confidence"],
            "sensitive_trait": bool(row["sensitive_trait"]),
            "review_status": row["review_status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "evidence": self._evidence_dicts(
                connection, self._observation_evidence_ids(connection, str(row["id"]))
            ),
        }

    def _candidate_dict(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "audience_profile_id": row["audience_profile_id"],
            "observation_type": row["observation_type"],
            "proposed_text": row["proposed_text"],
            "confidence": row["confidence"],
            "fingerprint": row["fingerprint"],
            "status": row["status"],
            "observation_id": row["observation_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "evidence": self._evidence_dicts(
                connection, self._candidate_evidence_ids(connection, str(row["id"]))
            ),
            "provisional": row["status"] in {"pending", "stale"},
        }

    @staticmethod
    def _evidence_dicts(
        connection: sqlite3.Connection, provenance_ids: list[str]
    ) -> list[dict[str, Any]]:
        if not provenance_ids:
            return []
        placeholders = ", ".join("?" for _ in provenance_ids)
        rows = connection.execute(
            f"""
            SELECT su.id AS source_unit_id, su.ordinal, su.start_ms, su.end_ms,
                   su.speaker_label, su.unit_type, su.text,
                   d.id AS source_id, d.original_name
            FROM source_units AS su
            JOIN documents AS d ON d.id = su.document_id
            WHERE su.id IN ({placeholders})
              AND d.kind = 'transcript'
              AND su.unit_type = 'transcript_segment'
            ORDER BY d.original_name COLLATE NOCASE, su.ordinal, su.id
            LIMIT ?""",
            [*provenance_ids, MAX_EVIDENCE_PER_ITEM],
        ).fetchall()
        return [
            {
                "provenance_type": "transcript",
                "provenance_id": row["source_unit_id"],
                "source_type": "transcript",
                "source_id": row["source_id"],
                "source_unit_id": row["source_unit_id"],
                "label": provenance_label(
                    row["original_name"],
                    row["unit_type"],
                    row["ordinal"],
                    start_ms=row["start_ms"],
                    end_ms=row["end_ms"],
                    speaker_label=row["speaker_label"],
                    transcript=True,
                ),
                "text": str(row["text"])[:MAX_OBSERVATION_TEXT_LENGTH],
            }
            for row in rows
        ]

    @staticmethod
    def _profile_row(
        connection: sqlite3.Connection, project_id: str, profile_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM audience_profiles WHERE id = ? AND project_id = ?",
            (profile_id, project_id),
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "AUDIENCE_PROFILE_NOT_FOUND",
                "The audience profile was not found in this project.",
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _observation_row(
        connection: sqlite3.Connection, project_id: str, observation_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT ao.*
            FROM audience_observations AS ao
            JOIN audience_profiles AS ap ON ap.id = ao.audience_profile_id
            WHERE ao.id = ? AND ap.project_id = ?
            """,
            (observation_id, project_id),
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "AUDIENCE_OBSERVATION_NOT_FOUND",
                "The audience observation was not found in this project.",
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _candidate_row(
        connection: sqlite3.Connection, project_id: str, candidate_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT ac.*
            FROM audience_observation_candidates AS ac
            JOIN audience_profiles AS ap ON ap.id = ac.audience_profile_id
            WHERE ac.id = ? AND ap.project_id = ?
            """,
            (candidate_id, project_id),
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "AUDIENCE_CANDIDATE_NOT_FOUND",
                "The audience observation suggestion was not found in this project.",
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _observation_evidence_ids(connection: sqlite3.Connection, observation_id: str) -> list[str]:
        rows = connection.execute(
            """
            SELECT provenance_id FROM audience_observation_evidence
            WHERE observation_id = ? AND provenance_type = 'transcript'
            ORDER BY provenance_id
            """,
            (observation_id,),
        ).fetchall()
        return [str(row["provenance_id"]) for row in rows]

    @staticmethod
    def _candidate_evidence_ids(connection: sqlite3.Connection, candidate_id: str) -> list[str]:
        rows = connection.execute(
            """
            SELECT provenance_id FROM audience_observation_candidate_evidence
            WHERE candidate_id = ? AND provenance_type = 'transcript'
            ORDER BY provenance_id
            """,
            (candidate_id,),
        ).fetchall()
        return [str(row["provenance_id"]) for row in rows]

    @staticmethod
    def _fingerprint(
        profile_id: str,
        observation_type: str,
        text: str,
        evidence_ids: Iterable[str],
    ) -> str:
        payload = {
            "profile_id": profile_id,
            "observation_type": observation_type,
            "text": " ".join(text.casefold().split()),
            "evidence_ids": sorted(set(evidence_ids)),
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()

    @staticmethod
    def _validate_document_filters(
        connection: sqlite3.Connection, project_id: str, document_ids: list[str]
    ) -> None:
        for document_id in document_ids:
            row = connection.execute(
                "SELECT kind FROM documents WHERE id = ? AND project_id = ?",
                (document_id, project_id),
            ).fetchone()
            if row is None:
                raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found in this project.")
            if row["kind"] != "transcript":
                raise CoreDomainError(
                    "SOURCE_NOT_TRANSCRIPT",
                    "Audience extraction filters accept transcript sources only.",
                )

    @staticmethod
    def _project_id(params: dict[str, Any]) -> str:
        value = params.get("project_id")
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @classmethod
    def _profile_notes(cls, params: dict[str, Any]) -> str | None:
        notes = cls._optional_text(params, "user_notes", max_length=MAX_PROFILE_NOTES_LENGTH)
        if notes is not None:
            ObservationPolicy.validate_text(notes)
        return notes

    @staticmethod
    def _ensure_capacity(
        connection: sqlite3.Connection,
        query: str,
        parameters: tuple[Any, ...],
        *,
        limit: int,
        code: str,
        message: str,
        details: dict[str, Any],
    ) -> None:
        row = connection.execute(query, parameters).fetchone()
        if row is not None and int(row["count"]) >= limit:
            raise CoreDomainError(code, message, details=details)

    @staticmethod
    def _uuid_param(params: dict[str, Any], field: str) -> str:
        value = params.get(field)
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise invalid_request(f"{field} must be a UUID.", field=field) from exc

    @classmethod
    def _optional_uuid(cls, params: dict[str, Any], field: str) -> str | None:
        if field not in params or params[field] is None:
            return None
        return cls._uuid_param(params, field)

    @staticmethod
    def _required_text(params: dict[str, Any], field: str, *, max_length: int) -> str:
        value = params.get(field)
        if not isinstance(value, str) or not value.strip():
            raise invalid_request(f"{field} must be a non-empty string.", field=field)
        normalized = value.strip()
        if len(normalized) > max_length or any(
            ord(character) < 32 and character not in "\r\n\t" for character in normalized
        ):
            raise invalid_request(f"{field} is invalid or too long.", field=field)
        return normalized

    @staticmethod
    def _optional_text(params: dict[str, Any], field: str, *, max_length: int) -> str | None:
        if field not in params or params[field] is None:
            return None
        value = params[field]
        if not isinstance(value, str) or len(value) > max_length:
            raise invalid_request(f"{field} is invalid or too long.", field=field)
        if any(ord(character) < 32 and character not in "\r\n\t" for character in value):
            raise invalid_request(f"{field} contains unsupported control characters.", field=field)
        return value.strip() or None

    @staticmethod
    def _bool_param(params: dict[str, Any], field: str, *, default: bool) -> bool:
        value = params.get(field, default)
        if not isinstance(value, bool):
            raise invalid_request(f"{field} must be a boolean.", field=field)
        return value

    @staticmethod
    def _validate_observation_type(value: Any) -> None:
        if not isinstance(value, str) or value not in OBSERVATION_TYPES:
            raise invalid_request("observation_type is not supported.", field="observation_type")

    @staticmethod
    def _observation_text(value: Any) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value.strip()) > MAX_OBSERVATION_TEXT_LENGTH
        ):
            raise invalid_request(
                "text must be a bounded non-empty string.",
                field="text",
            )
        normalized = value.strip()
        if any(ord(character) < 32 and character not in "\r\n\t" for character in normalized):
            raise invalid_request("text contains unsupported control characters.", field="text")
        return normalized

    @classmethod
    def _document_ids(cls, params: dict[str, Any]) -> list[str]:
        value = params.get("document_ids", [])
        if not isinstance(value, list) or len(value) > MAX_DOCUMENT_FILTER_COUNT:
            raise invalid_request(
                "document_ids must be a bounded list of UUIDs.", field="document_ids"
            )
        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise invalid_request("document_ids must contain UUIDs.", field="document_ids")
            try:
                normalized = str(uuid.UUID(item))
            except ValueError as exc:
                raise invalid_request(
                    "document_ids must contain UUIDs.", field="document_ids"
                ) from exc
            if normalized not in result:
                result.append(normalized)
        return result
