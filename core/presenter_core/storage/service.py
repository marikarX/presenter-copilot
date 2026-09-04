"""Storage manager and app/project repository boundaries."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from presenter_core.errors import CoreDomainError

from .database import connect_app_database, connect_project_database
from .paths import AppPaths, ProjectPaths, normalize_project_id


class StorageManager:
    """Own app.db and resolve project databases through AppPaths."""

    def __init__(self, data_root: str | Path | None = None) -> None:
        self.paths = AppPaths(data_root)
        self.paths.ensure_layout()
        self._app = connect_app_database(self.paths.app_database)
        self._app_lock = threading.RLock()

    @property
    def app_schema_version(self) -> int:
        with self._app_lock:
            row = self._app.execute("PRAGMA user_version").fetchone()
            return int(row[0]) if row else 0

    @contextmanager
    def app_database(self) -> Iterator[sqlite3.Connection]:
        """Expose the already-open app database for bounded app-scope services."""
        with self._app_lock:
            yield self._app

    def close(self) -> None:
        with self._app_lock:
            self._app.close()

    def project_paths(self, project_id: str, *, require_exists: bool = True) -> ProjectPaths:
        normalized_id = normalize_project_id(project_id)
        registry_row = self.app_row(normalized_id)
        expected_relative_path = f"projects/{normalized_id}"
        if registry_row["project_relative_path"] != expected_relative_path:
            raise CoreDomainError("PROJECT_PATH_UNSAFE", "The project vault path is not trusted.")
        return self.paths.project(normalized_id, require_exists=require_exists)

    @contextmanager
    def project_database(self, project_id: str) -> Iterator[sqlite3.Connection]:
        """Open a trusted project DB for one bounded operation."""
        normalized_id = normalize_project_id(project_id)
        paths = self.project_paths(normalized_id, require_exists=True)
        if (
            paths.database.is_symlink()
            or not paths.database.is_file()
            or paths.database.resolve().parent != paths.root.resolve()
        ):
            if paths.database.is_symlink() or paths.database.exists():
                raise CoreDomainError(
                    "PROJECT_PATH_UNSAFE",
                    "The project database path is not trusted.",
                )
            raise CoreDomainError("PROJECT_CORRUPT", "The project database is missing.")

        connection = connect_project_database(paths.database)
        try:
            yield connection
        finally:
            connection.close()

    def app_row(self, project_id: str) -> sqlite3.Row:
        normalized_id = normalize_project_id(project_id)
        with self._app_lock:
            row = self._app.execute(
                "SELECT * FROM projects WHERE id = ?",
                (normalized_id,),
            ).fetchone()
        if row is None:
            raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
        return cast(sqlite3.Row, row)

    def list_app_rows(self) -> list[sqlite3.Row]:
        with self._app_lock:
            return list(
                self._app.execute(
                    "SELECT * FROM projects "
                    "ORDER BY COALESCE(last_opened_at, updated_at) DESC, created_at DESC"
                ).fetchall()
            )

    def insert_app_project(self, values: dict[str, Any]) -> None:
        with self._app_lock:
            self._app.execute(
                """
                INSERT INTO projects (
                    id, name, project_relative_path, created_at, updated_at, last_opened_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    values["id"],
                    values["name"],
                    values["project_relative_path"],
                    values["created_at"],
                    values["updated_at"],
                    values.get("last_opened_at"),
                ),
            )
            self._app.commit()

    def update_app_project(self, project_id: str, *, name: str, updated_at: str) -> None:
        normalized_id = normalize_project_id(project_id)
        with self._app_lock:
            cursor = self._app.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                (name, updated_at, normalized_id),
            )
            if cursor.rowcount != 1:
                self._app.rollback()
                raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
            self._app.commit()

    def mark_project_opened(self, project_id: str, opened_at: str) -> None:
        normalized_id = normalize_project_id(project_id)
        with self._app_lock:
            cursor = self._app.execute(
                "UPDATE projects SET last_opened_at = ? WHERE id = ?",
                (opened_at, normalized_id),
            )
            if cursor.rowcount != 1:
                self._app.rollback()
                raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
            self._app.commit()

    def remove_app_project(self, project_id: str) -> bool:
        normalized_id = normalize_project_id(project_id)
        with self._app_lock:
            cursor = self._app.execute("DELETE FROM projects WHERE id = ?", (normalized_id,))
            self._app.commit()
            return cursor.rowcount == 1

    def get_app_metadata(self, key: str) -> Any | None:
        """Read one bounded JSON value from the existing app metadata table."""
        if not isinstance(key, str) or not key or len(key) > 120:
            raise CoreDomainError("APP_METADATA_INVALID", "The app metadata key is invalid.")
        with self._app_lock:
            row = self._app.execute(
                "SELECT value FROM app_metadata WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(str(row[0]))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise CoreDomainError(
                "APP_METADATA_INVALID",
                "The app metadata value is malformed.",
                details={"key": key},
            ) from error

    def set_app_metadata(self, key: str, value: Any) -> None:
        """Atomically replace one bounded JSON value in app scope."""
        if not isinstance(key, str) or not key or len(key) > 120:
            raise CoreDomainError("APP_METADATA_INVALID", "The app metadata key is invalid.")
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise CoreDomainError(
                "APP_METADATA_INVALID", "The app metadata value is not JSON serializable."
            ) from error
        if len(encoded) > 32_000:
            raise CoreDomainError(
                "APP_METADATA_INVALID", "The app metadata value exceeds the safe bound."
            )
        with self._app_lock:
            self._app.execute(
                "INSERT INTO app_metadata(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, encoded),
            )
            self._app.commit()
