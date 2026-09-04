"""App-owned, fail-safe quarantine operations for destructive deletion.

The filesystem and SQLite app registry cannot share one atomic transaction.  A
small journal under the application data root bridges that boundary:

* a project vault is first moved into a generated tombstone directory;
* the app transaction records its committed operation id;
* only a committed tombstone may be physically removed.

Uncommitted tombstones are restored.  Committed tombstones are never restored
to ``projects/`` and are retried until cleanup completes.  All paths are
constructed from generated UUIDs and canonical project ids; manifest values
never become filesystem paths.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from presenter_core.errors import CoreDomainError

from .paths import AppPaths, normalize_project_id

TOMBSTONE_VERSION = 1
MAX_TOMBSTONE_PROJECTS = 10_000
TOMBSTONE_DIRECTORY_NAME = "tombstones"
MANIFEST_NAME = "manifest.json"
MANIFEST_TEMP_NAME = "manifest.tmp"
VAULT_NAME = "vault"
RESET_PROJECTS_NAME = "projects"

DeletionKind = Literal["project", "reset"]


@dataclass(frozen=True)
class DeletionOperation:
    """A validated app-owned deletion operation."""

    operation_id: str
    kind: DeletionKind
    project_ids: tuple[str, ...]
    root: Path
    manifest: Path
    state: Literal["staging", "committed"]
    credential_present: bool = False
    credential_removed: bool = False
    remove_model_cache: bool = False


class TombstoneManager:
    """Create, stage, recover, and clean generated deletion tombstones."""

    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    def create(
        self,
        kind: DeletionKind,
        project_ids: list[str] | tuple[str, ...],
        *,
        credential_present: bool = False,
        remove_model_cache: bool = False,
    ) -> DeletionOperation:
        if kind not in {"project", "reset"}:
            raise CoreDomainError(
                "DELETION_OPERATION_INVALID", "The deletion operation is invalid."
            )
        normalized_ids = self._normalize_project_ids(project_ids, allow_empty=kind == "reset")
        if kind == "project" and len(normalized_ids) != 1:
            raise CoreDomainError(
                "DELETION_OPERATION_INVALID",
                "A project deletion must name exactly one project.",
            )
        if not isinstance(credential_present, bool) or not isinstance(remove_model_cache, bool):
            raise CoreDomainError(
                "DELETION_OPERATION_INVALID", "The deletion operation is invalid."
            )

        tombstones_root = self._safe_tombstones_root(create=True)
        # Inspect existing operations before creating a new one so a malformed
        # app-owned journal entry fails closed instead of being bypassed.
        self.list_operations()
        operation_id = str(uuid.uuid4())
        operation_root = tombstones_root / operation_id
        operation_root.mkdir()
        if kind == "reset":
            (operation_root / RESET_PROJECTS_NAME).mkdir()
        operation = DeletionOperation(
            operation_id=operation_id,
            kind=kind,
            project_ids=normalized_ids,
            root=operation_root,
            manifest=operation_root / MANIFEST_NAME,
            state="staging",
            credential_present=credential_present if kind == "reset" else False,
            credential_removed=not credential_present if kind == "reset" else False,
            remove_model_cache=remove_model_cache if kind == "reset" else False,
        )
        self._write_manifest(operation, state="staging")
        return operation

    def list_operations(self) -> list[DeletionOperation]:
        """Return every valid tombstone, failing closed on unknown entries."""
        root = self._safe_tombstones_root(create=True)
        try:
            entries = sorted(root.iterdir(), key=lambda path: path.name)
        except OSError as error:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "The deletion journal could not be inspected.",
                retryable=True,
            ) from error
        operations: list[DeletionOperation] = []
        for entry in entries:
            if entry.is_symlink() or not entry.is_dir():
                raise CoreDomainError(
                    "DELETION_TOMBSTONE_UNSAFE",
                    "The deletion journal contains an unsafe entry.",
                )
            self._assert_safe_directory(entry, root)
            operation_id = self._canonical_uuid(entry.name)
            operations.append(self._read_operation(operation_id))
        return operations

    def stage_project(self, operation: DeletionOperation, project_id: str) -> bool:
        """Move one validated project vault into its operation tombstone."""
        operation = self._reload(operation)
        if operation.kind not in {"project", "reset"} or project_id not in operation.project_ids:
            raise CoreDomainError(
                "DELETION_OPERATION_INVALID", "The project is not in this operation."
            )
        if operation.kind == "project":
            target = operation.root / VAULT_NAME
        else:
            target = operation.root / RESET_PROJECTS_NAME / project_id / VAULT_NAME
            parent = target.parent
            if parent.exists():
                self._assert_safe_directory(parent, operation.root / RESET_PROJECTS_NAME)
            else:
                try:
                    parent.mkdir()
                except OSError as error:
                    raise CoreDomainError(
                        "PROJECT_DELETE_STAGE_FAILED",
                        "The project vault could not be staged; no project data was deleted.",
                        retryable=True,
                    ) from error
        source = self._paths.project(project_id, require_exists=False).root
        if source.is_symlink():
            raise CoreDomainError(
                "PROJECT_DELETE_FAILED",
                "The project vault is not a safe local directory.",
            )
        if not source.exists():
            return False
        self._assert_safe_directory(source, self._paths.projects)
        self._assert_absent_target(target)
        try:
            os.replace(source, target)
        except OSError as error:
            raise CoreDomainError(
                "PROJECT_DELETE_STAGE_FAILED",
                "The project vault could not be staged; no project data was deleted.",
                retryable=True,
            ) from error
        return True

    def rollback(self, operation: DeletionOperation) -> None:
        """Restore every staged vault for an uncommitted operation."""
        operation = self._reload(operation)
        if operation.state == "committed":
            raise CoreDomainError(
                "DELETION_ROLLBACK_UNSAFE",
                "A committed deletion cannot be rolled back.",
            )
        for project_id in operation.project_ids:
            source = self._paths.project(project_id, require_exists=False).root
            target = self._target_for(operation, project_id)
            source_exists = source.exists() or source.is_symlink()
            target_exists = target.exists() or target.is_symlink()
            if source_exists and target_exists:
                raise CoreDomainError(
                    "DELETION_ROLLBACK_UNSAFE",
                    "The project vault has two competing locations.",
                )
            if source.is_symlink() or (source.exists() and not source.is_dir()):
                raise CoreDomainError(
                    "DELETION_ROLLBACK_UNSAFE",
                    "The project restore destination is unsafe.",
                )
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise CoreDomainError(
                    "DELETION_ROLLBACK_UNSAFE",
                    "The staged project vault is unsafe.",
                )
            if target_exists:
                self._assert_safe_directory(target, target.parent)
                try:
                    os.replace(target, source)
                except OSError as error:
                    raise CoreDomainError(
                        "DELETION_ROLLBACK_FAILED",
                        "The staged project vault could not be restored.",
                        retryable=True,
                    ) from error
        self._remove_operation(operation)

    def mark_committed(self, operation: DeletionOperation) -> DeletionOperation:
        """Record the post-transaction committed state in the tombstone."""
        operation = self._reload(operation)
        if operation.state == "committed":
            return operation
        self._write_manifest(operation, state="committed")
        return self._reload(operation)

    def mark_credential_removed(self, operation: DeletionOperation) -> DeletionOperation:
        """Persist successful reset credential cleanup without storing a secret."""
        operation = self._reload(operation)
        if operation.kind != "reset" or not operation.credential_present:
            return operation
        if operation.credential_removed:
            return operation
        self._write_manifest(
            operation,
            state="committed",
            credential_removed=True,
        )
        return self._reload(operation)

    def cleanup(self, operation: DeletionOperation) -> None:
        """Physically remove a committed operation and finalize its journal."""
        self.cleanup_vaults(operation)
        self.finalize(operation)

    def cleanup_vaults(self, operation: DeletionOperation) -> None:
        """Remove staged vault contents while retaining the operation journal."""
        operation = self._reload(operation)
        if operation.state != "committed":
            raise CoreDomainError(
                "DELETION_CLEANUP_UNSAFE",
                "Only a committed deletion can be physically removed.",
            )
        for project_id in operation.project_ids:
            original = self._paths.project(project_id, require_exists=False).root
            if original.exists() or original.is_symlink():
                raise CoreDomainError(
                    "DELETION_TOMBSTONE_UNSAFE",
                    "A committed deletion has an unexpected project path.",
                )
            target = self._target_for(operation, project_id)
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise CoreDomainError(
                    "DELETION_TOMBSTONE_UNSAFE",
                    "A staged project vault is not a safe directory.",
                )
            if not target.exists():
                continue
            self._assert_safe_directory(target, target.parent)
            try:
                shutil.rmtree(target)
            except OSError as error:
                raise CoreDomainError(
                    "DELETION_CLEANUP_FAILED",
                    "Committed deletion cleanup is pending and can be retried.",
                    retryable=True,
                ) from error

    def finalize(self, operation: DeletionOperation) -> None:
        """Remove an already-empty committed operation journal."""
        operation = self._reload(operation)
        if operation.state != "committed":
            raise CoreDomainError(
                "DELETION_CLEANUP_UNSAFE",
                "Only a committed deletion can be finalized.",
            )
        self._remove_operation(operation)

    def _read_operation(self, operation_id: str) -> DeletionOperation:
        tombstones_root = self._safe_tombstones_root()
        operation_root = tombstones_root / operation_id
        self._assert_safe_directory(operation_root, tombstones_root)
        manifest = operation_root / MANIFEST_NAME
        if manifest.is_symlink() or not manifest.is_file() or manifest.name != MANIFEST_NAME:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A deletion tombstone manifest is missing or unsafe.",
            )
        try:
            manifest_resolved = manifest.resolve()
            operation_resolved = operation_root.resolve()
        except OSError as error:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A deletion tombstone manifest could not be resolved.",
                retryable=True,
            ) from error
        if manifest_resolved.parent != operation_resolved:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A deletion tombstone manifest is outside its operation directory.",
            )
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A deletion tombstone manifest is invalid.",
            ) from error
        if not isinstance(raw, dict):
            raise CoreDomainError("DELETION_TOMBSTONE_UNSAFE", "A deletion tombstone is invalid.")
        kind = raw.get("kind")
        if kind not in {"project", "reset"}:
            raise CoreDomainError("DELETION_TOMBSTONE_UNSAFE", "A deletion tombstone is invalid.")
        required = {"version", "operation_id", "kind", "project_ids", "state"}
        reset_fields = {"credential_present", "credential_removed", "remove_model_cache"}
        allowed = required | (reset_fields if kind == "reset" else set())
        if set(raw) != allowed:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A deletion tombstone contains unsupported metadata.",
            )
        if raw.get("version") != TOMBSTONE_VERSION or raw.get("operation_id") != operation_id:
            raise CoreDomainError("DELETION_TOMBSTONE_UNSAFE", "A deletion tombstone is invalid.")
        project_ids_value = raw.get("project_ids")
        if (
            not isinstance(project_ids_value, list)
            or len(project_ids_value) > MAX_TOMBSTONE_PROJECTS
        ):
            raise CoreDomainError("DELETION_TOMBSTONE_UNSAFE", "A deletion tombstone is invalid.")
        project_ids = self._normalize_project_ids(project_ids_value, allow_empty=kind == "reset")
        if project_ids != tuple(project_ids_value):
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE", "A deletion tombstone is not canonical."
            )
        state = raw.get("state")
        if state not in {"staging", "committed"}:
            raise CoreDomainError("DELETION_TOMBSTONE_UNSAFE", "A deletion tombstone is invalid.")
        if kind == "reset":
            if not all(isinstance(raw.get(field), bool) for field in reset_fields):
                raise CoreDomainError(
                    "DELETION_TOMBSTONE_UNSAFE", "A deletion tombstone is invalid."
                )
        operation = DeletionOperation(
            operation_id=operation_id,
            kind=kind,
            project_ids=project_ids,
            root=operation_root,
            manifest=manifest,
            state=state,
            credential_present=bool(raw.get("credential_present", False)),
            credential_removed=bool(raw.get("credential_removed", False)),
            remove_model_cache=bool(raw.get("remove_model_cache", False)),
        )
        self._validate_shape(operation)
        return operation

    def _reload(self, operation: DeletionOperation) -> DeletionOperation:
        if not isinstance(operation, DeletionOperation):
            raise CoreDomainError(
                "DELETION_OPERATION_INVALID", "The deletion operation is invalid."
            )
        return self._read_operation(operation.operation_id)

    def _write_manifest(
        self,
        operation: DeletionOperation,
        *,
        state: Literal["staging", "committed"],
        credential_removed: bool | None = None,
    ) -> None:
        temp = operation.root / MANIFEST_TEMP_NAME
        if temp.is_symlink() or (temp.exists() and not temp.is_file()):
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A deletion tombstone temporary manifest is unsafe.",
            )
        payload: dict[str, Any] = {
            "version": TOMBSTONE_VERSION,
            "operation_id": operation.operation_id,
            "kind": operation.kind,
            "project_ids": list(operation.project_ids),
            "state": state,
        }
        if operation.kind == "reset":
            payload.update(
                {
                    "credential_present": operation.credential_present,
                    "credential_removed": (
                        operation.credential_removed
                        if credential_removed is None
                        else credential_removed
                    ),
                    "remove_model_cache": operation.remove_model_cache,
                }
            )
        try:
            temp.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(temp, operation.manifest)
        except OSError as error:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_WRITE_FAILED",
                "The deletion journal could not be updated.",
                retryable=True,
            ) from error

    def _validate_shape(self, operation: DeletionOperation) -> None:
        direct_allowed = {
            MANIFEST_NAME,
            MANIFEST_TEMP_NAME,
            VAULT_NAME if operation.kind == "project" else RESET_PROJECTS_NAME,
        }
        try:
            entries = list(operation.root.iterdir())
        except OSError as error:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A deletion tombstone could not be inspected.",
                retryable=True,
            ) from error
        for entry in entries:
            if entry.name not in direct_allowed or entry.is_symlink():
                raise CoreDomainError(
                    "DELETION_TOMBSTONE_UNSAFE",
                    "A deletion tombstone contains an unsafe entry.",
                )
            try:
                if entry.resolve().parent != operation.root.resolve():
                    raise CoreDomainError(
                        "DELETION_TOMBSTONE_UNSAFE",
                        "A deletion tombstone contains an entry outside its operation directory.",
                    )
            except OSError as error:
                raise CoreDomainError(
                    "DELETION_TOMBSTONE_UNSAFE",
                    "A deletion tombstone entry could not be resolved.",
                    retryable=True,
                ) from error
        if operation.kind == "project":
            vault = operation.root / VAULT_NAME
            if vault.exists():
                self._assert_safe_directory(vault, operation.root)
            return
        projects_root = operation.root / RESET_PROJECTS_NAME
        if projects_root.is_symlink() or not projects_root.is_dir():
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A reset tombstone project directory is unsafe.",
            )
        self._assert_safe_directory(projects_root, operation.root)
        try:
            project_entries = list(projects_root.iterdir())
        except OSError as error:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A reset tombstone could not be inspected.",
                retryable=True,
            ) from error
        allowed_ids = set(operation.project_ids)
        for project_entry in project_entries:
            if (
                project_entry.name not in allowed_ids
                or project_entry.is_symlink()
                or not project_entry.is_dir()
            ):
                raise CoreDomainError(
                    "DELETION_TOMBSTONE_UNSAFE",
                    "A reset tombstone contains an unsafe project entry.",
                )
            self._assert_safe_directory(project_entry, projects_root)
            children = list(project_entry.iterdir())
            for child in children:
                if child.name != VAULT_NAME or child.is_symlink():
                    raise CoreDomainError(
                        "DELETION_TOMBSTONE_UNSAFE",
                        "A reset tombstone contains an unsafe staged entry.",
                    )
                self._assert_safe_directory(child, project_entry)

    def _remove_operation(self, operation: DeletionOperation) -> None:
        operation = self._reload(operation)
        if operation.kind == "project":
            vault = operation.root / VAULT_NAME
            if vault.exists() or vault.is_symlink():
                raise CoreDomainError(
                    "DELETION_CLEANUP_FAILED",
                    "The committed deletion tombstone is not empty.",
                    retryable=True,
                )
        else:
            projects_root = operation.root / RESET_PROJECTS_NAME
            try:
                for project_entry in list(projects_root.iterdir()):
                    if project_entry.exists() or project_entry.is_symlink():
                        project_entry.rmdir()
                projects_root.rmdir()
            except OSError as error:
                raise CoreDomainError(
                    "DELETION_CLEANUP_FAILED",
                    "The committed deletion tombstone could not be finalized.",
                    retryable=True,
                ) from error
        try:
            temp = operation.root / MANIFEST_TEMP_NAME
            if temp.exists() and not temp.is_symlink():
                temp.unlink()
            operation.manifest.unlink()
            operation.root.rmdir()
        except OSError as error:
            raise CoreDomainError(
                "DELETION_CLEANUP_FAILED",
                "The committed deletion tombstone could not be finalized.",
                retryable=True,
            ) from error

    def _target_for(self, operation: DeletionOperation, project_id: str) -> Path:
        normalized = normalize_project_id(project_id)
        if normalized not in operation.project_ids:
            raise CoreDomainError(
                "DELETION_OPERATION_INVALID", "The project is not in this operation."
            )
        if operation.kind == "project":
            return operation.root / VAULT_NAME
        return operation.root / RESET_PROJECTS_NAME / normalized / VAULT_NAME

    @staticmethod
    def _normalize_project_ids(
        project_ids: list[str] | tuple[str, ...], *, allow_empty: bool
    ) -> tuple[str, ...]:
        if not isinstance(project_ids, (list, tuple)):
            raise CoreDomainError("DELETION_OPERATION_INVALID", "The project list is invalid.")
        if len(project_ids) > MAX_TOMBSTONE_PROJECTS:
            raise CoreDomainError("DELETION_OPERATION_INVALID", "The project list is too large.")
        normalized: list[str] = []
        for project_id in project_ids:
            try:
                value = normalize_project_id(project_id)
            except CoreDomainError as error:
                raise CoreDomainError(
                    "DELETION_OPERATION_INVALID",
                    "The project list contains an invalid project id.",
                ) from error
            if value in normalized:
                raise CoreDomainError(
                    "DELETION_OPERATION_INVALID", "The project list is not unique."
                )
            normalized.append(value)
        if not allow_empty and not normalized:
            raise CoreDomainError("DELETION_OPERATION_INVALID", "The project list cannot be empty.")
        return tuple(sorted(normalized))

    @staticmethod
    def _canonical_uuid(value: str) -> str:
        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError, TypeError) as error:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE", "A deletion tombstone id is invalid."
            ) from error
        canonical = str(parsed)
        if parsed.version != 4 or canonical != value.lower() or canonical != value:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE", "A deletion tombstone id is invalid."
            )
        return canonical

    @staticmethod
    def _assert_absent_target(target: Path) -> None:
        if target.is_symlink() or target.exists():
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "The deletion staging target is already occupied.",
            )

    @staticmethod
    def _assert_safe_directory(path: Path, parent: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A deletion directory is not safe.",
            )
        try:
            resolved_parent = parent.resolve()
            resolved_path = path.resolve()
        except OSError as error:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A deletion directory could not be resolved.",
                retryable=True,
            ) from error
        if resolved_path.parent != resolved_parent:
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "A deletion directory escapes its app-owned parent.",
            )

    def _safe_tombstones_root(self, *, create: bool = False) -> Path:
        root = self._paths.root / TOMBSTONE_DIRECTORY_NAME
        if root.is_symlink() or (root.exists() and not root.is_dir()):
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "The deletion journal root is not safe.",
            )
        if create:
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise CoreDomainError(
                    "DELETION_TOMBSTONE_UNSAFE",
                    "The deletion journal root could not be created.",
                    retryable=True,
                ) from error
        if not root.is_dir() or root.resolve().parent != self._paths.root.resolve():
            raise CoreDomainError(
                "DELETION_TOMBSTONE_UNSAFE",
                "The deletion journal root is not safe.",
            )
        return root
