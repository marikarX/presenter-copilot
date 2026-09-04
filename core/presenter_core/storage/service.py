"""Storage manager and app/project repository boundaries."""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, cast

from presenter_core.errors import CoreDomainError

from .database import connect_app_database, connect_project_database
from .paths import AppPaths, ProjectPaths, normalize_project_id
from .tombstones import DeletionOperation, TombstoneManager

DELETION_JOURNAL_KEY = "__presenter_copilot_deletion_journal_v1"
MAX_DELETION_JOURNAL_OPERATIONS = 10_000
CredentialCleanup = Callable[[dict[str, Any]], dict[str, Any]]


class StorageManager:
    """Own app.db and resolve project databases through AppPaths."""

    def __init__(self, data_root: str | Path | None = None) -> None:
        self.paths = AppPaths(data_root)
        self.paths.ensure_layout()
        self._app = connect_app_database(self.paths.app_database)
        self._app_lock = threading.RLock()
        self._tombstones = TombstoneManager(self.paths)

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
        if key == DELETION_JOURNAL_KEY:
            raise CoreDomainError("APP_METADATA_INVALID", "The app metadata key is reserved.")
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
        if key == DELETION_JOURNAL_KEY:
            raise CoreDomainError("APP_METADATA_INVALID", "The app metadata key is reserved.")
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

    def reconcile_project_runtime(self, project_id: str) -> dict[str, int]:
        """Fail-closed process-owned state left by an interrupted core run."""
        normalized_id = normalize_project_id(project_id)
        now = _utc_now()
        with self.project_database(normalized_id) as connection:
            provider_runs = connection.execute(
                """
                UPDATE provider_runs
                SET ended_at = ?, status = 'error', error_code = 'CORE_RESTART_INTERRUPTED'
                WHERE status = 'started'
                """,
                (now,),
            ).rowcount
            sessions = connection.execute(
                """
                UPDATE sessions
                SET ended_at = COALESCE(ended_at, ?), status = 'aborted'
                WHERE status = 'active' AND mode IN ('run', 'live_assist')
                """,
                (now,),
            ).rowcount
            connection.commit()
        return {
            "provider_runs": max(0, int(provider_runs)),
            "sessions": max(0, int(sessions)),
        }

    def reconcile_runtime(self) -> dict[str, int]:
        """Reconcile every registered project without changing completed state."""
        result = {"provider_runs": 0, "sessions": 0, "projects": 0}
        for row in self.list_app_rows():
            project_id = str(row["id"])
            try:
                counts = self.reconcile_project_runtime(project_id)
            except CoreDomainError:
                # A corrupt vault remains unavailable and is never rewritten
                # during recovery.  Its safe error is reported by project.list.
                continue
            result["provider_runs"] += counts["provider_runs"]
            result["sessions"] += counts["sessions"]
            result["projects"] += 1
        return result

    def delete_project_authoritative(self, project_id: str) -> bool:
        """Quarantine a project, commit its registry removal, then clean it."""
        normalized_id = normalize_project_id(project_id)
        recovery = self.reconcile_deletions()
        if recovery["pending_operation_ids"]:
            raise CoreDomainError(
                "DELETION_RECOVERY_PENDING",
                "A previous deletion is still being recovered; retry is safe.",
                retryable=True,
            )
        self.project_paths(normalized_id, require_exists=False)
        operation = self._tombstones.create("project", [normalized_id])
        try:
            self._tombstones.stage_project(operation, normalized_id)
        except Exception as error:
            self._raise_after_rollback(
                operation,
                error,
                code="PROJECT_DELETE_FAILED",
                message="The project vault could not be staged; no project data was deleted.",
            )

        try:
            self._commit_project_registry_deletion(operation)
        except Exception as error:
            self._raise_after_rollback(
                operation,
                error,
                code="PROJECT_DELETE_FAILED",
                message="The project deletion could not be committed; project data was preserved.",
            )

        try:
            operation = self._tombstones.mark_committed(operation)
        except CoreDomainError as error:
            raise CoreDomainError(
                "PROJECT_DELETE_CLEANUP_PENDING",
                "The project deletion was committed and cleanup is pending; retry is safe.",
                retryable=True,
                details={"phase": "commit_journal"},
            ) from error
        self._complete_committed_operation(operation)
        return True

    def reset_local_data(
        self,
        *,
        remove_model_cache: bool = False,
        credential_present: bool = False,
        credential_cleanup: CredentialCleanup | None = None,
    ) -> dict[str, Any]:
        """Stage and commit a recoverable app-wide reset."""
        if not isinstance(remove_model_cache, bool) or not isinstance(credential_present, bool):
            raise CoreDomainError(
                "LOCAL_DATA_RESET_FAILED",
                "The local reset options are invalid.",
                retryable=False,
            )
        if credential_present and credential_cleanup is None:
            raise CoreDomainError(
                "CREDENTIAL_CLEANUP_PENDING",
                "The secure credential cleanup could not be established; retry is safe.",
                retryable=True,
            )
        recovery = self.reconcile_deletions(credential_cleanup=credential_cleanup)
        if recovery["pending_operation_ids"]:
            raise CoreDomainError(
                "DELETION_RECOVERY_PENDING",
                "A previous deletion is still being recovered; retry is safe.",
                retryable=True,
            )

        rows = self.list_app_rows()
        registered_ids: list[str] = []
        for row in rows:
            project_id = normalize_project_id(str(row["id"]))
            # Validate every registry mapping before moving any vault.  A
            # tampered mapping must never widen the deletion target.
            self.project_paths(project_id, require_exists=False)
            registered_ids.append(project_id)

        project_ids = self.paths.project_directory_ids()
        self._validate_named_directory("logs")
        self._validate_named_directory("diagnostics")
        if remove_model_cache:
            self.paths.model_cache_directories("all")

        operation = self._tombstones.create(
            "reset",
            project_ids,
            credential_present=credential_present,
            remove_model_cache=remove_model_cache,
        )
        try:
            for project_id in project_ids:
                self._tombstones.stage_project(operation, project_id)
        except Exception as error:
            self._raise_after_rollback(
                operation,
                error,
                code="LOCAL_DATA_RESET_FAILED",
                message=(
                    "The local reset could not stage all project data; no project data was deleted."
                ),
            )

        try:
            self._commit_reset_transaction(operation)
        except Exception as error:
            self._raise_after_rollback(
                operation,
                error,
                code="LOCAL_DATA_RESET_FAILED",
                message="The local reset could not be committed; project data was preserved.",
            )

        try:
            operation = self._tombstones.mark_committed(operation)
        except CoreDomainError as error:
            raise CoreDomainError(
                "LOCAL_DATA_RESET_CLEANUP_PENDING",
                "The local reset was committed and cleanup is pending; retry is safe.",
                retryable=True,
                details={"phase": "commit_journal"},
            ) from error

        credential_result: dict[str, Any] = {}
        if operation.credential_present and not operation.credential_removed:
            if credential_cleanup is None:
                raise CoreDomainError(
                    "CREDENTIAL_CLEANUP_PENDING",
                    "The secure credential cleanup could not be established; "
                    "local data was preserved for retry.",
                    retryable=True,
                )
            credential_result = self._apply_credential_cleanup(operation, credential_cleanup)
            operation = self._tombstones.mark_credential_removed(operation)

        self._complete_committed_operation(operation)
        return {
            "reset": True,
            "projects_removed": len(registered_ids),
            "project_directories_removed": len(project_ids),
            "model_cache_retained": not remove_model_cache,
            **credential_result,
        }

    def reconcile_deletions(
        self,
        *,
        credential_cleanup: CredentialCleanup | None = None,
    ) -> dict[str, Any]:
        """Recover interrupted staged operations and retry committed cleanup."""
        operations = self._tombstones.list_operations()
        journal_ids = set(self._deletion_journal_ids())
        operation_ids = {operation.operation_id for operation in operations}
        unknown_journal_ids = journal_ids.difference(operation_ids)
        if unknown_journal_ids:
            raise CoreDomainError(
                "DELETION_JOURNAL_UNSAFE",
                "The deletion journal references a missing tombstone.",
            )

        result: dict[str, Any] = {
            "recovered_operations": 0,
            "cleaned_operations": 0,
            "pending_operation_ids": [],
            "pending_project_ids": [],
            "completed_project_ids": [],
        }
        for operation in operations:
            marked = operation.operation_id in journal_ids
            if operation.state == "staging" and not marked:
                try:
                    self._tombstones.rollback(operation)
                    result["recovered_operations"] += 1
                except CoreDomainError as error:
                    self._record_pending_recovery(result, operation, error)
                continue

            try:
                if operation.state == "staging":
                    operation = self._tombstones.mark_committed(operation)
                if operation.kind == "reset" and operation.credential_present:
                    if not operation.credential_removed:
                        if credential_cleanup is None:
                            raise CoreDomainError(
                                "CREDENTIAL_CLEANUP_PENDING",
                                "The secure credential cleanup is not available; retry is safe.",
                                retryable=True,
                            )
                        self._apply_credential_cleanup(operation, credential_cleanup)
                        operation = self._tombstones.mark_credential_removed(operation)
                self._complete_committed_operation(operation)
                result["cleaned_operations"] += 1
                if operation.kind == "project":
                    result["completed_project_ids"].extend(operation.project_ids)
            except CoreDomainError as error:
                self._record_pending_recovery(result, operation, error)
        return result

    def _commit_project_registry_deletion(self, operation: DeletionOperation) -> None:
        """Commit the project row removal and its tombstone marker together."""
        project_id = operation.project_ids[0]
        with self._app_lock:
            try:
                self._app.execute("BEGIN IMMEDIATE")
                cursor = self._app.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                if cursor.rowcount != 1:
                    raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")
                self._append_deletion_journal_id(self._app, operation.operation_id)
                self._app.commit()
            except CoreDomainError:
                if self._app.in_transaction:
                    self._app.rollback()
                raise
            except Exception as error:
                if self._app.in_transaction:
                    self._app.rollback()
                raise CoreDomainError(
                    "PROJECT_DELETE_FAILED",
                    "The project deletion could not update its registry; retry is safe.",
                    retryable=True,
                ) from error

    def _commit_reset_transaction(self, operation: DeletionOperation) -> None:
        """Commit reset metadata removal and its tombstone marker together."""
        with self._app_lock:
            try:
                self._app.execute("BEGIN IMMEDIATE")
                self._app.execute("DELETE FROM speaker_profiles")
                self._app.execute("DELETE FROM provider_configurations")
                self._app.execute("DELETE FROM projects")
                self._app.execute("DELETE FROM app_metadata")
                self._append_deletion_journal_id(self._app, operation.operation_id)
                self._app.commit()
            except Exception as error:
                if self._app.in_transaction:
                    self._app.rollback()
                if isinstance(error, CoreDomainError):
                    raise
                raise CoreDomainError(
                    "LOCAL_DATA_RESET_FAILED",
                    "The local reset could not update application metadata; retry is safe.",
                    retryable=True,
                ) from error

    def _complete_committed_operation(self, operation: DeletionOperation) -> None:
        """Finish physical cleanup only after the app transaction is durable."""
        try:
            if operation.kind == "reset":
                for name in ("logs", "diagnostics"):
                    _delete_named_directory(self.paths.root, name)
                if operation.remove_model_cache:
                    self.paths.delete_model_cache("all")
            self._tombstones.cleanup_vaults(operation)
        except CoreDomainError as error:
            if operation.kind == "reset":
                code = "LOCAL_DATA_RESET_CLEANUP_PENDING"
                message = "The local reset was committed and cleanup is pending; retry is safe."
            else:
                code = "PROJECT_DELETE_CLEANUP_PENDING"
                message = (
                    "The project deletion was committed and cleanup is pending; retry is safe."
                )
            raise CoreDomainError(
                code,
                message,
                retryable=True,
                details={"phase": "postcommit_cleanup", "cleanup_error_code": error.code},
            ) from error
        except Exception as error:
            code = (
                "LOCAL_DATA_RESET_CLEANUP_PENDING"
                if operation.kind == "reset"
                else "PROJECT_DELETE_CLEANUP_PENDING"
            )
            raise CoreDomainError(
                code,
                "Committed deletion cleanup is pending and can be retried.",
                retryable=True,
                details={"phase": "postcommit_cleanup", "cleanup_error_code": "INTERNAL_ERROR"},
            ) from error

        try:
            self._remove_deletion_journal_id(operation.operation_id)
            self._tombstones.finalize(operation)
        except CoreDomainError as error:
            code = (
                "LOCAL_DATA_RESET_CLEANUP_PENDING"
                if operation.kind == "reset"
                else "PROJECT_DELETE_CLEANUP_PENDING"
            )
            raise CoreDomainError(
                code,
                "Committed deletion cleanup is pending and can be retried.",
                retryable=True,
                details={"phase": "postcommit_finalize", "cleanup_error_code": error.code},
            ) from error

    def _apply_credential_cleanup(
        self,
        operation: DeletionOperation,
        credential_cleanup: CredentialCleanup,
    ) -> dict[str, Any]:
        try:
            result = credential_cleanup(
                {
                    "operation_id": operation.operation_id,
                    "credential_present": operation.credential_present,
                    "credential_removed": operation.credential_removed,
                }
            )
        except CoreDomainError:
            raise
        except Exception as error:
            raise CoreDomainError(
                "CREDENTIAL_CLEANUP_INCOMPLETE",
                "The secure credential cleanup could not be verified; retry is safe.",
                retryable=True,
            ) from error
        if (
            not isinstance(result, dict)
            or result.get("credential_cleanup_established") is not True
            or (operation.credential_present and result.get("credentials_removed") is not True)
        ):
            raise CoreDomainError(
                "CREDENTIAL_CLEANUP_INCOMPLETE",
                "The secure credential cleanup could not be verified; retry is safe.",
                retryable=True,
            )
        allowed_fields = {
            "stored_credential_present",
            "credential_cleanup_established",
            "environment_credential_detected",
            "environment_credential_retained",
            "credentials_removed",
        }
        return {key: result[key] for key in allowed_fields if key in result}

    def _raise_after_rollback(
        self,
        operation: DeletionOperation,
        error: Exception,
        *,
        code: str,
        message: str,
    ) -> NoReturn:
        try:
            self._tombstones.rollback(operation)
        except CoreDomainError as rollback_error:
            raise CoreDomainError(
                code,
                "The deletion was not committed and recovery is pending; retry is safe.",
                retryable=True,
                details={"phase": "rollback"},
            ) from rollback_error
        if isinstance(error, CoreDomainError):
            raise error
        raise CoreDomainError(code, message, retryable=True) from error

    def _record_pending_recovery(
        self,
        result: dict[str, Any],
        operation: DeletionOperation,
        error: CoreDomainError,
    ) -> None:
        result["pending_operation_ids"].append(operation.operation_id)
        result["pending_project_ids"].extend(operation.project_ids)
        result.setdefault("pending_errors", []).append(
            {"operation_id": operation.operation_id, "error_code": error.code}
        )

    def _deletion_journal_ids(self) -> list[str]:
        with self._app_lock:
            return self._read_deletion_journal(self._app)

    def _append_deletion_journal_id(
        self, connection: sqlite3.Connection, operation_id: str
    ) -> None:
        ids = self._read_deletion_journal(connection)
        if operation_id not in ids:
            ids.append(operation_id)
        if len(ids) > MAX_DELETION_JOURNAL_OPERATIONS:
            raise CoreDomainError(
                "DELETION_JOURNAL_UNSAFE",
                "The deletion journal exceeds its safe bound.",
            )
        encoded = json.dumps(
            {"committed_operation_ids": ids}, ensure_ascii=False, separators=(",", ":")
        )
        connection.execute(
            "INSERT INTO app_metadata(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (DELETION_JOURNAL_KEY, encoded),
        )

    def _remove_deletion_journal_id(self, operation_id: str) -> None:
        with self._app_lock:
            try:
                self._app.execute("BEGIN IMMEDIATE")
                ids = self._read_deletion_journal(self._app)
                if operation_id not in ids:
                    self._app.rollback()
                    return
                ids.remove(operation_id)
                if ids:
                    encoded = json.dumps(
                        {"committed_operation_ids": ids},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    self._app.execute(
                        "INSERT INTO app_metadata(key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (DELETION_JOURNAL_KEY, encoded),
                    )
                else:
                    self._app.execute(
                        "DELETE FROM app_metadata WHERE key = ?", (DELETION_JOURNAL_KEY,)
                    )
                self._app.commit()
            except CoreDomainError:
                if self._app.in_transaction:
                    self._app.rollback()
                raise
            except Exception as error:
                if self._app.in_transaction:
                    self._app.rollback()
                raise CoreDomainError(
                    "DELETION_JOURNAL_UPDATE_FAILED",
                    "The deletion journal could not be finalized; retry is safe.",
                    retryable=True,
                ) from error

    @staticmethod
    def _read_deletion_journal(connection: sqlite3.Connection) -> list[str]:
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?", (DELETION_JOURNAL_KEY,)
        ).fetchone()
        if row is None:
            return []
        try:
            raw = json.loads(str(row[0]))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise CoreDomainError(
                "DELETION_JOURNAL_UNSAFE",
                "The deletion journal metadata is malformed.",
            ) from error
        if (
            not isinstance(raw, dict)
            or set(raw) != {"committed_operation_ids"}
            or not isinstance(raw["committed_operation_ids"], list)
            or len(raw["committed_operation_ids"]) > MAX_DELETION_JOURNAL_OPERATIONS
        ):
            raise CoreDomainError(
                "DELETION_JOURNAL_UNSAFE",
                "The deletion journal metadata is invalid.",
            )
        ids: list[str] = []
        for value in raw["committed_operation_ids"]:
            if not isinstance(value, str) or value in ids:
                raise CoreDomainError(
                    "DELETION_JOURNAL_UNSAFE",
                    "The deletion journal metadata is invalid.",
                )
            try:
                parsed = uuid.UUID(value)
            except (ValueError, AttributeError, TypeError) as error:
                raise CoreDomainError(
                    "DELETION_JOURNAL_UNSAFE",
                    "The deletion journal metadata is invalid.",
                ) from error
            if parsed.version != 4 or str(parsed) != value:
                raise CoreDomainError(
                    "DELETION_JOURNAL_UNSAFE",
                    "The deletion journal metadata is invalid.",
                )
            ids.append(value)
        return ids

    def _validate_named_directory(self, name: str) -> None:
        target = self.paths.root / name
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise CoreDomainError(
                "LOCAL_DATA_RESET_FAILED",
                "Application data contains an unsafe directory entry.",
                retryable=True,
            )
        if target.exists() and (
            target.resolve().parent != self.paths.root.resolve() or target.name != name
        ):
            raise CoreDomainError(
                "LOCAL_DATA_RESET_FAILED",
                "Application data contains an unsafe directory entry.",
                retryable=True,
            )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _delete_named_directory(root: Path, name: str) -> None:
    """Delete one fixed app-owned child directory after validating its boundary."""
    target = root / name
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise CoreDomainError(
            "LOCAL_DATA_RESET_FAILED",
            "Application data contains an unsafe directory entry.",
            retryable=True,
        )
    if not target.exists():
        return
    if target.resolve().parent != root.resolve() or target.name != name:
        raise CoreDomainError(
            "LOCAL_DATA_RESET_FAILED",
            "Application data contains an unsafe directory entry.",
            retryable=True,
        )
    try:
        shutil.rmtree(target)
    except OSError as error:
        raise CoreDomainError(
            "LOCAL_DATA_RESET_FAILED",
            "Application diagnostics could not be removed; retry is safe.",
            retryable=True,
        ) from error
