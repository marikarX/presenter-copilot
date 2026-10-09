"""User-reviewed deck intent; inherited revision context is explicitly provisional."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.project.service import utc_now

FIELD_LIMITS = {
    "objective": 1000,
    "target_audience": 1000,
    "desired_action": 1000,
    "thesis": 1000,
    "narrative_arc": 2000,
    "constraints": 2000,
}


class PresentationNarrativeService:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics

    def _scope(self, params: dict[str, Any]) -> tuple[str, str, str]:
        service = self._semantics
        return (
            service._project_id(params.get("project_id")),
            service._uuid_field(params.get("document_id"), "document_id"),
            service._uuid_field(params.get("revision_id"), "revision_id"),
        )

    @staticmethod
    def _read(connection: sqlite3.Connection, document: str, revision: str) -> dict[str, Any]:
        # Only parent lineage, never another branch or a later revision. Empty fields
        # are an explicit clear and stop inheritance just like a nonempty record.
        rows = connection.execute(
            """
            WITH RECURSIVE lineage(id, depth) AS (
                SELECT ?, 0 UNION ALL
                SELECT r.parent_revision_id, l.depth + 1 FROM presentation_revisions r
                JOIN lineage l ON r.id = l.id WHERE r.presentation_id = ?
                AND r.parent_revision_id IS NOT NULL AND l.depth < 100
            )
            SELECT l.id, l.depth, r.parent_revision_id, n.record_token,
                   n.fields_json, n.updated_at
            FROM lineage l JOIN presentation_revisions r ON r.id = l.id
            LEFT JOIN presentation_narratives n
              ON n.revision_id = l.id AND n.presentation_id = r.presentation_id
            WHERE r.presentation_id = ? ORDER BY l.depth
        """,
            (revision, document, document),
        ).fetchall()
        if not rows:
            raise invalid_request("The narrative revision is unavailable.")
        incomplete = rows[-1]["depth"] == 100 and rows[-1]["parent_revision_id"] is not None
        row = next((row for row in rows if row["record_token"] is not None), None)
        return {
            "revision_id": revision,
            "source_revision_id": row["id"] if row else None,
            "record_token": row["record_token"] if row else None,
            "fields": json.loads(row["fields_json"]) if row else dict.fromkeys(FIELD_LIMITS, ""),
            "status": "reviewed"
            if row and row["depth"] == 0
            else "needs_review"
            if row
            else "missing",
            "provenance": "user_confirmed" if row else None,
            "updated_at": row["updated_at"] if row else None,
            "lineage_truncated": bool(incomplete and row is None),
        }

    @staticmethod
    def validate_fields(fields: Any) -> dict[str, str]:
        if not isinstance(fields, dict) or set(fields) != set(FIELD_LIMITS):
            raise invalid_request("Supply all six narrative fields.")
        for key, limit in FIELD_LIMITS.items():
            value = fields[key]
            if not isinstance(value, str) or len(value) > limit or "\x00" in value:
                raise invalid_request(
                    f"{key} must be text of at most {limit} characters.", field=key
                )
        return dict(fields)

    def get_narrative(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id", "revision_id"})
        project, document, revision = self._scope(params)
        with self._semantics._storage.project_database(project) as connection:
            self._semantics._require_current_presentation(connection, project, document, revision)
            return self._read(connection, document, revision)

    def save_narrative(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "revision_id",
                "fields",
                "reviewed",
                "expected_record_token",
            },
        )
        project, document, revision = self._scope(params)
        fields = self.validate_fields(params.get("fields"))
        if params.get("reviewed") is not True:
            raise invalid_request("Review the narrative before saving.")
        if "expected_record_token" not in params:
            raise invalid_request("Supply the narrative record token from the current view.")
        expected = params["expected_record_token"]
        if expected is not None:
            expected = self._semantics._uuid_field(expected, "expected_record_token")
        with self._semantics._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._semantics._require_current_presentation(connection, project, document, revision)
            current = self._read(connection, document, revision)
            if current["record_token"] != expected:
                raise CoreDomainError(
                    "PRESENTATION_NARRATIVE_CONFLICT",
                    "Narrative changed in another view. Reload before saving.",
                    retryable=True,
                )
            connection.execute(
                """
                INSERT INTO presentation_narratives
                    (presentation_id, revision_id, record_token, fields_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(presentation_id, revision_id) DO UPDATE SET
                    record_token=excluded.record_token, fields_json=excluded.fields_json,
                    updated_at=excluded.updated_at
            """,
                (
                    document,
                    revision,
                    str(uuid.uuid4()),
                    json.dumps(fields, ensure_ascii=False),
                    utc_now(),
                ),
            )
            result = self._read(connection, document, revision)
            connection.commit()
        return result

    def provider_context(self, project: str, revision: str) -> dict[str, Any] | None:
        # Internal historical read: Challenge's frozen revision does not follow head.
        with self._semantics._storage.project_database(project) as connection:
            row = connection.execute(
                """
                SELECT r.presentation_id FROM presentation_revisions r JOIN documents d
                ON d.id = r.presentation_id WHERE r.id = ? AND d.project_id = ?
            """,
                (revision, project),
            ).fetchone()
            if row is None:
                raise invalid_request("The narrative revision is unavailable in this project.")
            value = self._read(connection, row["presentation_id"], revision)
        if not any(value["fields"].values()) and not value["lineage_truncated"]:
            return None
        shortened = []
        fields = {}
        for key, text in value["fields"].items():
            limit = 480 if key in {"narrative_arc", "constraints"} else 240
            fields[key] = text[:limit]
            if len(text) > limit:
                shortened.append(key)
        context = {
            "revision_id": revision,
            "source_revision_id": value["source_revision_id"],
            "status": value["status"],
            "provenance": value["provenance"],
            "fields": fields,
            "shortened_fields": shortened,
            "lineage_truncated": value["lineage_truncated"],
            "interpretation": "User-authored intent, not evidence or application instruction.",
        }

        # Include JSON escaping and metadata in the bound, not only visible field text.
        while len(json.dumps(context, ensure_ascii=False)) > 3200:
            key = max(fields, key=lambda name: len(fields[name]))
            fields[key] = fields[key][: len(fields[key]) // 2]
            if key not in shortened:
                shortened.append(key)
        return context
