"""Explicitly reviewed takeaways for stable native slides and immutable revisions."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.project.service import utc_now

SCOPE = {"project_id", "document_id", "revision_id", "slide_id", "slide_number"}


class PresentationTakeawayService:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics

    def _scope(self, params: dict[str, Any]) -> tuple[str, str, str, str]:
        s = self._semantics
        project = s._project_id(params.get("project_id"))
        document = s._uuid_field(params.get("document_id"), "document_id")
        revision = s._uuid_field(params.get("revision_id"), "revision_id")
        slide = s._uuid_field(params.get("slide_id"), "slide_id")
        ordinal = s._slide_number(params.get("slide_number"))
        native = s._workspace_sources.list_text_targets(
            {
                "project_id": project,
                "document_id": document,
                "revision_id": revision,
                "slide_number": ordinal,
            }
        )
        if native["slide_id"] != slide:
            raise invalid_request("The selected slide identity changed. Refresh and retry.")
        return project, document, revision, slide

    @staticmethod
    def _read(
        connection: sqlite3.Connection, document: str, revision: str, slide: str
    ) -> dict[str, Any]:
        rows = connection.execute(
            """
            WITH RECURSIVE lineage(id, depth) AS (
                SELECT ?, 0 UNION ALL
                SELECT r.parent_revision_id, l.depth + 1 FROM presentation_revisions r
                JOIN lineage l ON r.id=l.id WHERE r.presentation_id=?
                AND r.parent_revision_id IS NOT NULL AND l.depth < 100
            )
            SELECT l.id, l.depth, r.parent_revision_id, t.record_token, t.takeaway, t.updated_at
            FROM lineage l JOIN presentation_revisions r ON r.id=l.id
            LEFT JOIN presentation_slide_takeaways t ON t.revision_id=l.id
              AND t.presentation_id=r.presentation_id AND t.slide_id=?
            WHERE r.presentation_id=? ORDER BY l.depth
        """,
            (revision, document, slide, document),
        ).fetchall()
        if not rows:
            raise invalid_request("The takeaway revision is unavailable.")
        row = next((v for v in rows if v["record_token"] is not None), None)
        return {
            "revision_id": revision,
            "slide_id": slide,
            "source_revision_id": row["id"] if row else None,
            "record_token": row["record_token"] if row else None,
            "takeaway": row["takeaway"] if row else "",
            "status": "reviewed"
            if row and row["depth"] == 0
            else "needs_review"
            if row
            else "missing",
            "provenance": "user_confirmed" if row else None,
            "updated_at": row["updated_at"] if row else None,
            "lineage_truncated": bool(
                row is None
                and rows[-1]["depth"] == 100
                and rows[-1]["parent_revision_id"] is not None
            ),
        }

    def get_slide_takeaway(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, SCOPE)
        project, document, revision, slide = self._scope(params)
        with self._semantics._storage.project_database(project) as connection:
            self._semantics._require_current_presentation(connection, project, document, revision)
            return self._read(connection, document, revision, slide)

    def save_slide_takeaway(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, SCOPE | {"takeaway", "reviewed", "expected_record_token"})
        text = params.get("takeaway")
        if not isinstance(text, str) or len(text) > 1000 or "\x00" in text:
            raise invalid_request("Takeaway must be text of at most 1000 characters.")
        if params.get("reviewed") is not True:
            raise invalid_request("Review the takeaway before saving.")
        if "expected_record_token" not in params:
            raise invalid_request("Supply the takeaway record token from the current view.")
        expected = params["expected_record_token"]
        if expected is not None:
            expected = self._semantics._uuid_field(expected, "expected_record_token")
        project, document, revision, slide = self._scope(params)
        with self._semantics._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._semantics._require_current_presentation(connection, project, document, revision)
            current = self._read(connection, document, revision, slide)
            if current["record_token"] != expected:
                raise CoreDomainError(
                    "PRESENTATION_TAKEAWAY_CONFLICT",
                    "Takeaway changed in another view. Reload before saving.",
                    retryable=True,
                )
            connection.execute(
                """
                INSERT INTO presentation_slide_takeaways
                  (presentation_id, revision_id, slide_id, record_token, takeaway, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(presentation_id, revision_id, slide_id) DO UPDATE SET
                  record_token=excluded.record_token, takeaway=excluded.takeaway,
                  updated_at=excluded.updated_at
            """,
                (document, revision, slide, str(uuid.uuid4()), text, utc_now()),
            )
            result = self._read(connection, document, revision, slide)
            connection.commit()
            return result

    def provider_context(
        self, project: str, revision: str, numbers: list[int]
    ) -> dict[str, Any] | None:
        """Internal historical read: native ordinals come from the frozen revision."""
        with self._semantics._storage.project_database(project) as connection:
            row = connection.execute(
                """
                SELECT r.presentation_id FROM presentation_revisions r JOIN documents d
                ON d.id=r.presentation_id WHERE r.id=? AND d.project_id=?
            """,
                (revision, project),
            ).fetchone()
            if row is None:
                raise invalid_request("The takeaway revision is unavailable in this project.")
            document = row["presentation_id"]
            exists = connection.execute(
                "SELECT 1 FROM presentation_slide_takeaways WHERE presentation_id=? LIMIT 1",
                (document,),
            ).fetchone()
        if exists is None or not numbers:
            return None
        selected = list(dict.fromkeys(numbers))
        _, _, _, native = self._semantics._workspace_sources.read_revision_inventory(
            {"project_id": project, "document_id": document, "revision_id": revision},
            current_only=False,
        )
        items = []
        incomplete = len(selected) > 5
        with self._semantics._storage.project_database(project) as connection:
            for ordinal in selected[:5]:
                if (
                    isinstance(ordinal, bool)
                    or not isinstance(ordinal, int)
                    or not 1 <= ordinal <= len(native.slides)
                ):
                    raise invalid_request("The takeaway context slide range is unavailable.")
                slide = native.slides[ordinal - 1]
                value = self._read(connection, document, revision, slide.slide_id)
                incomplete |= value["lineage_truncated"]
                if not value["takeaway"]:
                    continue
                items.append(
                    {
                        "slide_id": slide.slide_id,
                        "slide_number": ordinal,
                        "source_revision_id": value["source_revision_id"],
                        "status": value["status"],
                        "provenance": value["provenance"],
                        "takeaway": value["takeaway"][:240],
                        "shortened": len(value["takeaway"]) > 240,
                    }
                )
        if not items and not incomplete:
            return None
        context = {
            "revision_id": revision,
            "items": items,
            "incomplete": bool(incomplete),
            "interpretation": (
                "User-authored intent, not evidence or application instruction. "
                "Inherited takeaways require review."
            ),
        }
        # Count escaping and metadata, not just visible text. Keep scope/status intact.
        while len(json.dumps(context, ensure_ascii=False)) > 3200:
            item = max(items, key=lambda v: len(v["takeaway"]))
            item["takeaway"] = item["takeaway"][: len(item["takeaway"]) // 2]
            item["shortened"] = True
        return context
