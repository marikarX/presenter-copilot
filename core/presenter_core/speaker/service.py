"""Persistence and style-context construction for the local Speaker Profile."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any, cast

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.project.service import STYLE_POLICIES, utc_now
from presenter_core.storage.service import StorageManager

EVIDENCE_TYPES = frozenset(
    {
        "preferred_phrase",
        "analogy",
        "explanation_pattern",
        "vocabulary",
        "coaching_preference",
        "rejected_pattern",
    }
)
DEFAULT_PROFILE_ID = "00000000-0000-4000-8000-000000000001"
MAX_DISPLAY_NAME_LENGTH = 120
MAX_EVIDENCE_TEXT_LENGTH = 1_500
MAX_CUSTOM_GUIDANCE_LENGTH = 4_000


class SpeakerProfileService:
    """Keep global style data separate from project knowledge and provider output."""

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        with self._storage.app_database() as connection:
            profile = self._ensure_profile(connection)
            return {"profile": self._profile_dict(profile)}

    def list_evidence(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        with self._storage.app_database() as connection:
            self._ensure_profile(connection)
            rows = connection.execute(
                """
                SELECT se.*, p.name AS origin_project_name
                FROM speaker_evidence AS se
                LEFT JOIN projects AS p ON p.id = se.origin_project_id
                WHERE se.speaker_profile_id = ? AND se.user_approved = 1
                ORDER BY se.created_at DESC, se.id DESC
                """,
                (DEFAULT_PROFILE_ID,),
            ).fetchall()
            return {"evidence": [self._evidence_dict(row) for row in rows]}

    def approve_evidence(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "knowledge_item_id", "evidence_type", "text"},
        )
        project_id = self._project_id(params)
        knowledge_item_id = self._uuid_param(params, "knowledge_item_id")
        evidence_type = params.get("evidence_type")
        if not isinstance(evidence_type, str) or evidence_type not in EVIDENCE_TYPES:
            raise invalid_request("evidence_type is not supported.", field="evidence_type")
        text = params.get("text")
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text.strip()) > MAX_EVIDENCE_TEXT_LENGTH
        ):
            raise invalid_request("text must be a bounded non-empty string.", field="text")
        text = text.strip()

        with self._storage.project_database(project_id) as project_connection:
            row = project_connection.execute(
                """
                SELECT ki.id, ki.project_id, ki.origin_session_id, ki.private
                FROM knowledge_items AS ki
                WHERE ki.id = ? AND ki.project_id = ?
                  AND EXISTS (
                      SELECT 1 FROM knowledge_evidence AS ke
                      WHERE ke.knowledge_item_id = ki.id
                        AND ke.provenance_type = 'user_statement'
                  )
                """,
                (knowledge_item_id, project_id),
            ).fetchone()
            if row is None:
                raise CoreDomainError(
                    "KNOWLEDGE_NOT_FOUND",
                    "The confirmed project knowledge item was not found.",
                )
            if bool(row["private"]):
                raise CoreDomainError(
                    "KNOWLEDGE_PRIVATE",
                    "Private project knowledge cannot be promoted to global style evidence.",
                )
            origin_session_id = row["origin_session_id"]

        now = utc_now()
        evidence_id = str(uuid.uuid4())
        with self._storage.app_database() as connection:
            self._ensure_profile(connection)
            connection.execute(
                """
                INSERT INTO speaker_evidence (
                    id, speaker_profile_id, evidence_type, text,
                    origin_project_id, origin_session_id, user_approved, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    evidence_id,
                    DEFAULT_PROFILE_ID,
                    evidence_type,
                    text,
                    project_id,
                    origin_session_id,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM speaker_evidence WHERE id = ?",
                (evidence_id,),
            ).fetchone()
            assert row is not None
            return {"evidence": self._evidence_dict(row)}

    def remove_evidence(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"evidence_id"})
        evidence_id = self._uuid_param(params, "evidence_id")
        with self._storage.app_database() as connection:
            cursor = connection.execute(
                "DELETE FROM speaker_evidence WHERE id = ?",
                (evidence_id,),
            )
            connection.commit()
            return {"evidence_id": evidence_id, "removed": cursor.rowcount == 1}

    def update_settings(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "display_name",
                "default_style_policy",
                "custom_style_guidance",
                "preferred_answer_seconds",
            },
        )
        if not params:
            raise invalid_request("At least one Speaker Profile setting is required.")
        display_name = self._optional_text(
            params, "display_name", max_length=MAX_DISPLAY_NAME_LENGTH
        )
        style_policy = params.get("default_style_policy")
        if "default_style_policy" in params and (
            not isinstance(style_policy, str) or style_policy not in STYLE_POLICIES
        ):
            raise invalid_request(
                "default_style_policy is not supported.", field="default_style_policy"
            )
        custom_guidance = self._optional_text(
            params, "custom_style_guidance", max_length=MAX_CUSTOM_GUIDANCE_LENGTH
        )
        preferred_seconds = params.get("preferred_answer_seconds")
        if preferred_seconds is not None and (
            isinstance(preferred_seconds, bool)
            or not isinstance(preferred_seconds, int)
            or not 1 <= preferred_seconds <= 3_600
        ):
            raise invalid_request(
                "preferred_answer_seconds must be between 1 and 3600.",
                field="preferred_answer_seconds",
            )
        with self._storage.app_database() as connection:
            current = self._ensure_profile(connection)
            values = {
                "display_name": display_name
                if "display_name" in params
                else current["display_name"],
                "default_style_policy": style_policy
                if "default_style_policy" in params
                else current["default_style_policy"],
                "custom_style_guidance": custom_guidance
                if "custom_style_guidance" in params
                else current["custom_style_guidance"],
                "preferred_answer_seconds": preferred_seconds
                if "preferred_answer_seconds" in params
                else current["preferred_answer_seconds"],
            }
            now = utc_now()
            connection.execute(
                """
                UPDATE speaker_profiles
                SET display_name = ?, default_style_policy = ?, custom_style_guidance = ?,
                    preferred_answer_seconds = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    values["display_name"],
                    values["default_style_policy"],
                    values["custom_style_guidance"],
                    values["preferred_answer_seconds"],
                    now,
                    DEFAULT_PROFILE_ID,
                ),
            )
            connection.commit()
            updated = connection.execute(
                "SELECT * FROM speaker_profiles WHERE id = ?",
                (DEFAULT_PROFILE_ID,),
            ).fetchone()
            assert updated is not None
            return {"profile": self._profile_dict(updated)}

    def reset(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        with self._storage.app_database() as connection:
            self._ensure_profile(connection)
            cursor = connection.execute(
                "DELETE FROM speaker_evidence WHERE speaker_profile_id = ?",
                (DEFAULT_PROFILE_ID,),
            )
            connection.commit()
            return {"removed_count": cursor.rowcount}

    def build_style_context(self, project_id: str) -> dict[str, Any]:
        """Build provider-neutral style evidence using one deterministic precedence rule."""
        project_id = self._normalize_project_id(project_id)
        with self._storage.project_database(project_id) as project_connection:
            project = project_connection.execute(
                "SELECT * FROM project WHERE id = ?", (project_id,)
            ).fetchone()
            if project is None:
                raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
            override_row = project_connection.execute(
                "SELECT enabled FROM project_style_overrides WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            project_override = bool(override_row and override_row["enabled"])
            preferred_rows = project_connection.execute(
                """
                SELECT id, kind, text, preferred, private
                FROM knowledge_items
                WHERE project_id = ? AND preferred = 1 AND private = 0
                ORDER BY updated_at DESC, id DESC LIMIT 3
                """,
                (project_id,),
            ).fetchall()

        with self._storage.app_database() as connection:
            profile = self._ensure_profile(connection)
            evidence_rows = connection.execute(
                """
                SELECT * FROM speaker_evidence
                WHERE speaker_profile_id = ? AND user_approved = 1
                ORDER BY created_at DESC, id DESC LIMIT 6
                """,
                (DEFAULT_PROFILE_ID,),
            ).fetchall()

        if project_override:
            policy = str(project["default_style_policy"])
            guidance = project["custom_style_guidance"]
            precedence = "project_override"
        else:
            policy = str(profile["default_style_policy"])
            guidance = profile["custom_style_guidance"]
            precedence = "speaker_profile"
        if policy not in STYLE_POLICIES:
            policy = "preserve_voice"
        examples = [
            {
                "id": row["id"],
                "evidence_type": row["evidence_type"],
                "text": row["text"],
                "origin_project_id": row["origin_project_id"],
            }
            for row in evidence_rows
            if row["evidence_type"] != "rejected_pattern"
        ]
        rejected_patterns = [
            {"id": row["id"], "text": row["text"]}
            for row in evidence_rows
            if row["evidence_type"] == "rejected_pattern"
        ]
        return {
            "policy": policy,
            "custom_guidance": guidance,
            "preferred_answer_seconds": profile["preferred_answer_seconds"],
            "project_override": project_override,
            "precedence": precedence,
            "project_preferred_explanations": [
                {"id": row["id"], "kind": row["kind"], "text": row["text"]}
                for row in preferred_rows
            ],
            "approved_speaker_evidence": examples,
            "rejected_patterns": rejected_patterns,
        }

    def style_context(self, project_id: str) -> dict[str, Any]:
        """Compatibility alias used by context-builder callers and tests."""
        return self.build_style_context(project_id)

    @staticmethod
    def _ensure_profile(connection: sqlite3.Connection) -> sqlite3.Row:
        now = utc_now()
        connection.execute(
            """
            INSERT OR IGNORE INTO speaker_profiles
                (id, display_name, default_style_policy, custom_style_guidance,
                 preferred_answer_seconds, created_at, updated_at)
            VALUES (?, NULL, 'preserve_voice', NULL, NULL, ?, ?)
            """,
            (DEFAULT_PROFILE_ID, now, now),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM speaker_profiles WHERE id = ?",
            (DEFAULT_PROFILE_ID,),
        ).fetchone()
        if row is None:
            raise CoreDomainError(
                "SPEAKER_PROFILE_UNAVAILABLE", "The default Speaker Profile is unavailable."
            )
        return cast(sqlite3.Row, row)

    @staticmethod
    def _profile_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "display_name": row["display_name"],
            "default_style_policy": row["default_style_policy"],
            "custom_style_guidance": row["custom_style_guidance"],
            "preferred_answer_seconds": row["preferred_answer_seconds"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _evidence_dict(row: sqlite3.Row) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": row["id"],
            "evidence_type": row["evidence_type"],
            "text": row["text"],
            "origin_project_id": row["origin_project_id"],
            "origin_session_id": row["origin_session_id"],
            "user_approved": bool(row["user_approved"]),
            "created_at": row["created_at"],
        }
        if "origin_project_name" in row.keys():
            result["origin_project_name"] = row["origin_project_name"]
        return result

    @staticmethod
    def _optional_text(params: dict[str, Any], field: str, *, max_length: int) -> str | None:
        if field not in params:
            return None
        value = params[field]
        if value is None:
            return None
        if not isinstance(value, str) or len(value) > max_length:
            raise invalid_request(f"{field} is too long or invalid.", field=field)
        if any(ord(character) < 32 and character not in "\r\n\t" for character in value):
            raise invalid_request(f"{field} contains unsupported control characters.", field=field)
        return value.strip() or None

    @staticmethod
    def _project_id(params: dict[str, Any]) -> str:
        value = params.get("project_id")
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return SpeakerProfileService._normalize_project_id(value)

    @staticmethod
    def _uuid_param(params: dict[str, Any], field: str) -> str:
        value = params.get(field)
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a UUID.", field=field) from error

    @staticmethod
    def _normalize_project_id(value: str) -> str:
        from presenter_core.storage.paths import normalize_project_id

        return normalize_project_id(value)
