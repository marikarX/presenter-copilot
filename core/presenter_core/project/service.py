"""Project creation, settings, listing, opening, and deletion."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.storage.database import PROJECT_SCHEMA_VERSION, connect_project_database
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

PRIVACY_MODES = frozenset({"local_only", "selected_context_cloud", "full_context_cloud"})
STYLE_POLICIES = frozenset({"preserve_voice", "light_polish", "executive_concise", "custom"})
MAX_PROJECT_NAME_LENGTH = 120
MAX_STYLE_GUIDANCE_LENGTH = 4_000


def utc_now() -> str:
    """Return a sortable UTC timestamp without local timezone ambiguity."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _required_string(params: dict[str, Any], field: str, *, max_length: int) -> str:
    value = params.get(field)
    if not isinstance(value, str) or not value.strip():
        raise invalid_request(f"{field} must be a non-empty string.", field=field)
    normalized = value.strip()
    if len(normalized) > max_length or any(ord(character) < 32 for character in normalized):
        raise CoreDomainError(
            "PROJECT_NAME_INVALID", "Project name is invalid.", details={"field": field}
        )
    return normalized


def _optional_string(
    params: dict[str, Any],
    field: str,
    *,
    max_length: int,
    allow_null: bool = True,
) -> str | None:
    if field not in params:
        return None
    value = params[field]
    if value is None and allow_null:
        return None
    if not isinstance(value, str) or len(value) > max_length:
        raise invalid_request(
            f"{field} must be a string of at most {max_length} characters.", field=field
        )
    if any(ord(character) < 32 and character not in "\r\n\t" for character in value):
        raise invalid_request(f"{field} contains unsupported control characters.", field=field)
    return value


class ProjectService:
    """Own project lifecycle state while delegating paths to StorageManager."""

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage

    def create(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"name", "privacy_mode", "default_style_policy", "custom_style_guidance"},
        )
        name = _required_string(params, "name", max_length=MAX_PROJECT_NAME_LENGTH)
        privacy_mode = params.get("privacy_mode", "local_only")
        style_policy = params.get("default_style_policy", "preserve_voice")
        self._validate_enum(privacy_mode, PRIVACY_MODES, "privacy_mode")
        self._validate_enum(style_policy, STYLE_POLICIES, "default_style_policy")
        custom_guidance = _optional_string(
            params,
            "custom_style_guidance",
            max_length=MAX_STYLE_GUIDANCE_LENGTH,
        )

        project_id = str(uuid.uuid4())
        created_at = utc_now()
        paths = self._storage.paths.create_project_directories(project_id)
        try:
            connection = connect_project_database(paths.database)
            try:
                connection.execute(
                    """
                    INSERT INTO project (
                        id, name, created_at, updated_at, privacy_mode,
                        default_style_policy, custom_style_guidance,
                        current_presentation_id, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        project_id,
                        name,
                        created_at,
                        created_at,
                        privacy_mode,
                        style_policy,
                        custom_guidance,
                        PROJECT_SCHEMA_VERSION,
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            self._storage.insert_app_project(
                {
                    "id": project_id,
                    "name": name,
                    "project_relative_path": f"projects/{project_id}",
                    "created_at": created_at,
                    "updated_at": created_at,
                    "last_opened_at": None,
                }
            )
        except Exception:
            self._storage.paths.delete_project_directory(project_id)
            raise

        return {"project": self._project_dict_from_database(project_id)}

    def open(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id"})
        project_id = self._project_id(params)
        project = self._read_project(project_id)
        self._storage.mark_project_opened(project_id, utc_now())
        return {"project": project}

    def list(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        projects: list[dict[str, Any]] = []
        for row in self._storage.list_app_rows():
            project_id = str(row["id"])
            try:
                project = self._read_project(project_id)
            except CoreDomainError as error:
                project = {
                    "id": project_id,
                    "name": row["name"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "last_opened_at": row["last_opened_at"],
                    "storage_status": "unavailable",
                    "storage_error_code": error.code,
                }
            else:
                project["last_opened_at"] = row["last_opened_at"]
                project["storage_status"] = "ready"
            projects.append(project)
        return {"projects": projects}

    def update_settings(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "name",
                "privacy_mode",
                "default_style_policy",
                "custom_style_guidance",
            },
        )
        project_id = self._project_id(params)
        if not any(
            field in params
            for field in ("name", "privacy_mode", "default_style_policy", "custom_style_guidance")
        ):
            raise invalid_request("At least one project setting must be supplied.")

        current = self._read_project(project_id)
        name = (
            _required_string(params, "name", max_length=MAX_PROJECT_NAME_LENGTH)
            if "name" in params
            else str(current["name"])
        )
        privacy_mode = params.get("privacy_mode", current["privacy_mode"])
        style_policy = params.get("default_style_policy", current["default_style_policy"])
        self._validate_enum(privacy_mode, PRIVACY_MODES, "privacy_mode")
        self._validate_enum(style_policy, STYLE_POLICIES, "default_style_policy")
        custom_guidance = (
            _optional_string(
                params,
                "custom_style_guidance",
                max_length=MAX_STYLE_GUIDANCE_LENGTH,
            )
            if "custom_style_guidance" in params
            else current["custom_style_guidance"]
        )
        updated_at = utc_now()

        with self._storage.project_database(project_id) as connection:
            connection.execute(
                """
                UPDATE project
                SET name = ?, updated_at = ?, privacy_mode = ?,
                    default_style_policy = ?, custom_style_guidance = ?
                WHERE id = ?
                """,
                (name, updated_at, privacy_mode, style_policy, custom_guidance, project_id),
            )
            connection.commit()
        self._storage.update_app_project(project_id, name=name, updated_at=updated_at)
        return {"project": self._read_project(project_id)}

    def delete(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id"})
        project_id = self._project_id(params)
        try:
            self._storage.app_row(project_id)
        except CoreDomainError as error:
            if error.code == "PROJECT_NOT_FOUND":
                return {"project_id": project_id, "deleted": False}
            raise

        # Validate the registry-to-vault mapping before the one authoritative
        # filesystem delete path is allowed to run.
        self._storage.project_paths(project_id, require_exists=False)
        self._storage.paths.delete_project_directory(project_id)
        try:
            self._storage.remove_app_project(project_id)
        except CoreDomainError as exc:
            raise CoreDomainError(
                "PROJECT_DELETE_FAILED",
                "The project directory was removed but its registry entry could not be cleared.",
                retryable=True,
                details={},
            ) from exc
        return {"project_id": project_id, "deleted": True}

    def close(self) -> None:
        """Reserved for symmetry; project DB connections are operation-scoped."""

    def _read_project(self, project_id: str) -> dict[str, Any]:
        self._storage.project_paths(project_id, require_exists=True)
        return self._project_dict_from_database(project_id)

    def _project_dict_from_database(self, project_id: str) -> dict[str, Any]:
        # Existing-project reads must use the guarded storage path.  In
        # particular, StorageManager.project_database refuses to bootstrap a
        # missing project.db, so corruption is reported without recreating it.
        with self._storage.project_database(project_id) as connection:
            row = connection.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
            if row is None:
                raise CoreDomainError("PROJECT_CORRUPT", "The project record is missing.")
            return {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "privacy_mode": row["privacy_mode"],
                "default_style_policy": row["default_style_policy"],
                "custom_style_guidance": row["custom_style_guidance"],
                "source_count": self._count(connection, "documents"),
                "storage_status": "ready",
            }

    def _project_id(self, params: dict[str, Any]) -> str:
        value = params.get("project_id")
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _validate_enum(value: Any, allowed: frozenset[str], field: str) -> None:
        if not isinstance(value, str) or value not in allowed:
            raise invalid_request(f"{field} is not supported.", field=field)

    @staticmethod
    def _count(connection: sqlite3.Connection, table: str) -> int:
        if table != "documents":
            raise ValueError("unexpected table")
        row = connection.execute("SELECT COUNT(*) FROM documents").fetchone()
        return int(row[0]) if row else 0
