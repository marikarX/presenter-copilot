"""Native transcript-label enumeration and explicit project-local mapping."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable, Iterable
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.project.service import utc_now
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

from .parsers import MAX_TRANSCRIPT_SPEAKER_LABEL_LENGTH

MappingRevalidator = Callable[[sqlite3.Connection], None]


class TranscriptService:
    """Own transcript attribution metadata without attempting identity inference."""

    def __init__(
        self,
        storage: StorageManager,
        mapping_revalidator: MappingRevalidator | None = None,
    ) -> None:
        self._storage = storage
        self._mapping_revalidator = mapping_revalidator

    def list_speakers(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id"})
        project_id = self._project_id(params)
        document_id = self._optional_uuid(params, "document_id")
        with self._storage.project_database(project_id) as connection:
            if document_id is not None:
                self._document_row(connection, project_id, document_id)
            clauses = [
                "d.project_id = ?",
                "d.kind = 'transcript'",
                "su.unit_type = 'transcript_segment'",
                "su.speaker_label IS NOT NULL",
            ]
            parameters: list[Any] = [project_id]
            if document_id is not None:
                clauses.append("d.id = ?")
                parameters.append(document_id)
            rows = connection.execute(
                """
                SELECT d.id AS document_id, d.original_name AS document_name,
                       su.speaker_label AS native_speaker_label,
                       COUNT(*) AS segment_count,
                       MIN(su.start_ms) AS first_start_ms,
                       MAX(su.end_ms) AS last_end_ms,
                       tsm.audience_profile_id AS audience_profile_id,
                       ap.display_name AS profile_display_name,
                       ap.role AS profile_role,
                       ap.organization AS profile_organization,
                       ap.active AS profile_active
                FROM source_units AS su
                JOIN documents AS d ON d.id = su.document_id
                LEFT JOIN transcript_speaker_maps AS tsm
                    ON tsm.document_id = d.id
                   AND tsm.native_speaker_label = su.speaker_label
                LEFT JOIN audience_profiles AS ap ON ap.id = tsm.audience_profile_id
                WHERE """
                + " AND ".join(clauses)
                + """
                GROUP BY d.id, d.original_name, su.speaker_label,
                         tsm.audience_profile_id, ap.display_name, ap.role,
                         ap.organization, ap.active
                ORDER BY d.original_name COLLATE NOCASE, su.speaker_label COLLATE NOCASE,
                         d.id
                """,
                parameters,
            ).fetchall()
            speakers: list[dict[str, Any]] = []
            for row in rows:
                profile = None
                if row["audience_profile_id"] is not None:
                    profile = {
                        "id": row["audience_profile_id"],
                        "display_name": row["profile_display_name"],
                        "role": row["profile_role"],
                        "organization": row["profile_organization"],
                        "active": bool(row["profile_active"]),
                    }
                speakers.append(
                    {
                        "document_id": row["document_id"],
                        "document_name": row["document_name"],
                        "native_speaker_label": row["native_speaker_label"],
                        "segment_count": int(row["segment_count"]),
                        "first_start_ms": (
                            int(row["first_start_ms"])
                            if row["first_start_ms"] is not None
                            else None
                        ),
                        "last_end_ms": (
                            int(row["last_end_ms"]) if row["last_end_ms"] is not None else None
                        ),
                        "audience_profile": profile,
                    }
                )
            return {"speakers": speakers}

    def map_speaker(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "native_speaker_label", "audience_profile_id"},
        )
        project_id = self._project_id(params)
        document_id = self._uuid_param(params, "document_id")
        native_label = self._label_param(params)
        profile_id = self._uuid_param(params, "audience_profile_id")
        with self._storage.project_database(project_id) as connection:
            self._document_row(connection, project_id, document_id)
            profile = connection.execute(
                "SELECT * FROM audience_profiles WHERE id = ? AND project_id = ?",
                (profile_id, project_id),
            ).fetchone()
            if profile is None:
                raise CoreDomainError(
                    "AUDIENCE_PROFILE_NOT_FOUND",
                    "The audience profile was not found in this project.",
                )
            row = self._map_row(connection, document_id, native_label)
            connection.execute(
                """
                UPDATE transcript_speaker_maps
                SET audience_profile_id = ?, mapped_by = 'user'
                WHERE id = ?
                """,
                (profile_id, row["id"]),
            )
            self._revalidate(connection)
            connection.commit()
            updated = self._map_row(connection, document_id, native_label)
            return {
                "project_id": project_id,
                "speaker_map": self._map_dict(updated, profile),
            }

    def unmap_speaker(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id", "native_speaker_label"})
        project_id = self._project_id(params)
        document_id = self._uuid_param(params, "document_id")
        native_label = self._label_param(params)
        with self._storage.project_database(project_id) as connection:
            self._document_row(connection, project_id, document_id)
            row = self._map_row(connection, document_id, native_label)
            connection.execute(
                """
                UPDATE transcript_speaker_maps
                SET audience_profile_id = NULL, mapped_by = 'user'
                WHERE id = ?
                """,
                (row["id"],),
            )
            self._revalidate(connection)
            connection.commit()
            updated = self._map_row(connection, document_id, native_label)
            return {
                "project_id": project_id,
                "speaker_map": self._map_dict(updated, None),
            }

    def reconcile_speaker_maps(
        self,
        connection: sqlite3.Connection,
        document_id: str,
        native_labels: Iterable[str],
    ) -> None:
        """Preserve mappings for labels that survive a transcript re-index."""
        document = connection.execute(
            "SELECT id, kind FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if document is None or document["kind"] != "transcript":
            return
        labels = {label for label in native_labels if isinstance(label, str) and label.strip()}
        existing = connection.execute(
            "SELECT native_speaker_label FROM transcript_speaker_maps WHERE document_id = ?",
            (document_id,),
        ).fetchall()
        existing_labels = {str(row["native_speaker_label"]) for row in existing}
        now = utc_now()
        for label in sorted(labels):
            if label in existing_labels:
                continue
            connection.execute(
                """
                INSERT INTO transcript_speaker_maps (
                    id, document_id, native_speaker_label, audience_profile_id,
                    mapped_by, created_at
                ) VALUES (?, ?, ?, NULL, 'import_metadata', ?)
                """,
                (self._map_id(document_id, label), document_id, label, now),
            )
        for label in sorted(existing_labels - labels):
            connection.execute(
                """
                DELETE FROM transcript_speaker_maps
                WHERE document_id = ? AND native_speaker_label = ?
                """,
                (document_id, label),
            )
        self._revalidate(connection)

    def _revalidate(self, connection: sqlite3.Connection) -> None:
        # The callback is attached by CoreService and deliberately runs in the
        # same transaction as the mapping mutation or re-index.
        if self._mapping_revalidator is not None:
            self._mapping_revalidator(connection)

    @staticmethod
    def _project_id(params: dict[str, Any]) -> str:
        value = params.get("project_id")
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

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
    def _label_param(params: dict[str, Any]) -> str:
        value = params.get("native_speaker_label")
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value.strip()) > MAX_TRANSCRIPT_SPEAKER_LABEL_LENGTH
            or any(ord(character) < 32 for character in value)
        ):
            raise invalid_request(
                "native_speaker_label must be a bounded non-empty string.",
                field="native_speaker_label",
            )
        return " ".join(value.strip().split())

    @staticmethod
    def _document_row(
        connection: sqlite3.Connection, project_id: str, document_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM documents WHERE id = ? AND project_id = ?",
            (document_id, project_id),
        ).fetchone()
        if row is None:
            raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found in this project.")
        if row["kind"] != "transcript":
            raise CoreDomainError(
                "SOURCE_NOT_TRANSCRIPT",
                "Speaker mapping is available only for transcript sources.",
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _map_row(
        connection: sqlite3.Connection, document_id: str, native_label: str
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT * FROM transcript_speaker_maps
            WHERE document_id = ? AND native_speaker_label = ?
            """,
            (document_id, native_label),
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "TRANSCRIPT_SPEAKER_NOT_FOUND",
                "The native speaker label was not found in this transcript.",
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _map_dict(row: sqlite3.Row, profile: sqlite3.Row | None) -> dict[str, Any]:
        return {
            "id": row["id"],
            "document_id": row["document_id"],
            "native_speaker_label": row["native_speaker_label"],
            "audience_profile_id": row["audience_profile_id"],
            "mapped_by": row["mapped_by"],
            "created_at": row["created_at"],
            "audience_profile": (
                {
                    "id": profile["id"],
                    "display_name": profile["display_name"],
                    "role": profile["role"],
                    "organization": profile["organization"],
                    "active": bool(profile["active"]),
                }
                if profile is not None
                else None
            ),
        }

    @staticmethod
    def _map_id(document_id: str, native_label: str) -> str:
        return str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"presenter-copilot:transcript-speaker-map:{document_id}:{native_label}",
            )
        )
