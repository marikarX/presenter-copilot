"""Bounded access to imported PPTX snapshots for the local workspace preview."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import sqlite3
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, BinaryIO

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.ingestion.security import MAX_SOURCE_BYTES, preflight_source
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

from .fidelity import FidelityDocument, inspect_pptx_snapshot

MAX_READ_CHUNK_BYTES = 512 * 1024
MAX_OPEN_READERS = 4
READER_TTL_SECONDS = 60.0
PPTX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class _Reader:
    project_id: str
    document_id: str
    revision_id: str
    expected_sha256: str
    byte_size: int
    handle: BinaryIO
    digest: Any
    offset: int
    expires_at: float


class PresentationWorkspaceSourceService:
    """Stream only verified project-owned PPTX snapshots to the renderer."""

    def __init__(self, storage: StorageManager, *, clock: Callable[[], float] = monotonic) -> None:
        self._storage = storage
        self._clock = clock
        self._readers: dict[str, _Reader] = {}

    def open_source(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id"})
        project_id = self._project_id(params)
        document_id = self._document_id(params)
        self._expire_readers()

        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                """
                SELECT d.kind, d.mime_type, d.parse_status,
                       r.id AS revision_id, r.revision_kind, r.revision_number,
                       r.local_snapshot_path, r.sha256, r.byte_size
                FROM documents d
                LEFT JOIN presentation_revision_heads h ON h.presentation_id = d.id
                LEFT JOIN presentation_revisions r
                    ON r.id = h.revision_id AND r.presentation_id = h.presentation_id
                WHERE d.id = ? AND d.project_id = ?
                """,
                (document_id, project_id),
            ).fetchone()
        if row is None:
            raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found.")
        if row["kind"] != "presentation" or row["mime_type"] != PPTX_MIME_TYPE:
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_INVALID",
                "The workspace preview requires an imported PPTX presentation.",
            )
        if row["parse_status"] != "ready":
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_NOT_READY",
                "The presentation is not ready to preview.",
                retryable=True,
            )
        if not isinstance(row["revision_id"], str) or not row["revision_id"]:
            raise CoreDomainError(
                "PRESENTATION_REVISION_STATE_INVALID",
                "The current presentation revision is unavailable.",
            )
        return self.open_verified_snapshot(project_id, document_id, dict(row))

    def open_verified_snapshot(
        self, project_id: str, document_id: str, row: dict[str, Any] | sqlite3.Row
    ) -> dict[str, Any]:
        """Internal entry point for Core-owned revisions and reviewed plan snapshots.

        This is not a protocol method: callers supply authoritative managed-path
        metadata, never a renderer-supplied path. It shares the ordinary reader's
        package, size, digest, scope, resource-limit and lifetime checks.
        """
        self._expire_readers()
        if len(self._readers) >= MAX_OPEN_READERS:
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_READER_LIMIT",
                "Too many presentation previews are open.",
                retryable=True,
            )

        relative_path = row["local_snapshot_path"]
        if not isinstance(relative_path, str) or not relative_path:
            raise CoreDomainError("SOURCE_SNAPSHOT_MISSING", "The source snapshot is missing.")
        snapshot = self._storage.paths.snapshot_path(project_id, relative_path, require_exists=True)
        expected_sha256 = row["sha256"]
        byte_size = row["byte_size"]
        if (
            not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or not 0 < byte_size <= MAX_SOURCE_BYTES
        ):
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_CHANGED",
                "The stored presentation no longer matches its imported record.",
            )

        handle: BinaryIO | None = None
        try:
            preflight_source(snapshot, "pptx")
            handle = snapshot.open("rb")
            if os.fstat(handle.fileno()).st_size != byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its imported record.",
                )
            fidelity = inspect_pptx_snapshot(
                handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=byte_size,
            )
            handle.seek(0)
        except CoreDomainError:
            if handle is not None:
                handle.close()
            raise
        except OSError as error:
            if handle is not None:
                handle.close()
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_FAILED", "The selected presentation cannot be read."
            ) from error

        session_id = uuid.uuid4().hex
        self._readers[session_id] = _Reader(
            project_id=project_id,
            document_id=document_id,
            revision_id=row["revision_id"],
            expected_sha256=expected_sha256,
            byte_size=byte_size,
            handle=handle,
            digest=hashlib.sha256(),
            offset=0,
            expires_at=self._clock() + READER_TTL_SECONDS,
        )
        return {
            "session_id": session_id,
            "revision_id": row["revision_id"],
            "revision_kind": row["revision_kind"],
            "revision_number": int(row["revision_number"]),
            "byte_size": byte_size,
            "sha256": expected_sha256,
            "chunk_bytes": MAX_READ_CHUNK_BYTES,
            "fidelity_report": fidelity.summary(),
        }

    def list_text_targets(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._list_text_targets(params, current_only=True)

    def revision_text_targets(self, params: dict[str, Any]) -> dict[str, Any]:
        """Internal verified read for a frozen provider/session revision; no GUI write bypass."""
        return self._list_text_targets(params, current_only=False)

    def _list_text_targets(self, params: dict[str, Any], *, current_only: bool) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id", "revision_id", "slide_number"})
        slide_number = self._bounded_integer(params, "slide_number", minimum=1, maximum=5_000)
        scope = {key: params.get(key) for key in ("project_id", "document_id", "revision_id")}
        _, _, revision_id, fidelity = self.read_revision_inventory(scope, current_only=current_only)
        try:
            targets = fidelity.text_targets(slide_number)
        except ValueError as error:
            raise invalid_request(
                "slide_number is outside the presentation.", field="slide_number"
            ) from error
        return {"revision_id": revision_id, **targets}

    def read_revision_inventory(
        self, params: dict[str, Any], *, current_only: bool = True
    ) -> tuple[str, str, str, FidelityDocument]:
        """Internal verified native inventory; no path or historical read is exposed by IPC.

        Page readers reuse this one inspection for all selected slides. Text targets
        share the same ownership, revision, preflight, size and hash checks.
        """
        reject_unknown_fields(params, {"project_id", "document_id", "revision_id"})
        project_id = self._project_id(params)
        document_id = self._document_id(params)
        revision_id = params.get("revision_id")
        if not isinstance(revision_id, str) or not revision_id or len(revision_id) > 64:
            raise invalid_request("revision_id must be a valid UUID.", field="revision_id")
        try:
            revision_id = str(uuid.UUID(revision_id))
        except ValueError as error:
            raise invalid_request(
                "revision_id must be a valid UUID.", field="revision_id"
            ) from error
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                """
                SELECT d.kind, d.mime_type, d.parse_status,
                       r.id AS revision_id, r.local_snapshot_path, r.sha256, r.byte_size
                FROM documents d
                LEFT JOIN presentation_revision_heads h ON h.presentation_id = d.id
                LEFT JOIN presentation_revisions r
                    ON r.id = h.revision_id AND r.presentation_id = h.presentation_id
                WHERE d.id = ? AND d.project_id = ?
                """,
                (document_id, project_id),
            ).fetchone()
        if not current_only:
            with self._storage.project_database(project_id) as connection:
                row = connection.execute(
                    """
                    SELECT d.kind, d.mime_type, d.parse_status, r.id AS revision_id,
                           r.local_snapshot_path, r.sha256, r.byte_size
                    FROM documents d JOIN presentation_revisions r ON r.presentation_id = d.id
                    WHERE d.id = ? AND d.project_id = ? AND r.id = ?
                """,
                    (document_id, project_id, revision_id),
                ).fetchone()
        if row is None:
            raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found.")
        if row["kind"] != "presentation" or row["mime_type"] != PPTX_MIME_TYPE:
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_INVALID",
                "Text targets are available for imported PPTX presentations only.",
            )
        if row["parse_status"] != "ready":
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_NOT_READY",
                "The presentation is not ready to preview.",
                retryable=True,
            )
        if row["revision_id"] != revision_id:
            raise CoreDomainError(
                "PRESENTATION_REVISION_CONFLICT",
                "The current presentation revision changed. Refresh the preview and try again.",
                retryable=True,
            )
        relative_path = row["local_snapshot_path"]
        expected_sha256 = row["sha256"]
        byte_size = row["byte_size"]
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or not isinstance(expected_sha256, str)
            or not _SHA256.fullmatch(expected_sha256)
            or isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or not 0 < byte_size <= MAX_SOURCE_BYTES
        ):
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_CHANGED",
                "The stored presentation no longer matches its revision record.",
            )
        snapshot = self._storage.paths.snapshot_path(project_id, relative_path, require_exists=True)
        try:
            preflight_source(snapshot, "pptx")
            with snapshot.open("rb") as handle:
                if os.fstat(handle.fileno()).st_size != byte_size:
                    raise CoreDomainError(
                        "SOURCE_SNAPSHOT_CHANGED",
                        "The stored presentation no longer matches its revision record.",
                    )
                fidelity = inspect_pptx_snapshot(
                    handle,
                    document_id=document_id,
                    expected_sha256=expected_sha256,
                    byte_size=byte_size,
                )
        except CoreDomainError:
            raise
        except OSError as error:
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_FAILED", "The selected presentation cannot be read."
            ) from error
        return project_id, document_id, revision_id, fidelity

    def export_original_copy(self, params: dict[str, Any]) -> dict[str, Any]:
        """Atomically save the verified imported bytes without rewriting OOXML."""
        return self._export_copy(params, original=True)

    def export_current_copy(self, params: dict[str, Any]) -> dict[str, Any]:
        """Atomically save the verified current immutable revision."""
        return self._export_copy(params, original=False)

    def _export_copy(self, params: dict[str, Any], *, original: bool) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "destination_path"}
            | (set() if original else {"expected_revision_id"}),
        )
        expected_revision_id = params.get("expected_revision_id")
        if "expected_revision_id" in params:
            if not isinstance(expected_revision_id, str):
                raise invalid_request("expected_revision_id must be a revision UUID.")
            try:
                expected_revision_id = str(uuid.UUID(expected_revision_id))
            except ValueError as error:
                raise invalid_request("expected_revision_id must be a revision UUID.") from error
        project_id = self._project_id(params)
        document_id = self._document_id(params)
        destination_value = params.get("destination_path")
        if (
            not isinstance(destination_value, str)
            or not destination_value
            or len(destination_value) > 32_768
            or "\x00" in destination_value
        ):
            raise invalid_request(
                "destination_path must be an absolute file path.", field="destination_path"
            )

        with self._storage.project_database(project_id) as connection:
            if original:
                row = connection.execute(
                    """
                    SELECT d.kind, d.mime_type, d.parse_status,
                           d.local_snapshot_path, d.sha256, d.byte_size
                    FROM documents d WHERE d.id = ? AND d.project_id = ?
                    """,
                    (document_id, project_id),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT d.kind, d.mime_type, d.parse_status,
                           r.id AS revision_id, r.local_snapshot_path, r.sha256, r.byte_size
                    FROM documents d
                    JOIN presentation_revision_heads h ON h.presentation_id = d.id
                    JOIN presentation_revisions r
                        ON r.id = h.revision_id AND r.presentation_id = h.presentation_id
                    WHERE d.id = ? AND d.project_id = ?
                    """,
                    (document_id, project_id),
                ).fetchone()
        if row is None:
            raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found.")
        if row["kind"] != "presentation" or row["mime_type"] != PPTX_MIME_TYPE:
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_INVALID",
                "Saving a presentation copy requires an imported PPTX presentation.",
            )
        if row["parse_status"] != "ready":
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_NOT_READY",
                "The presentation is not ready to save.",
                retryable=True,
            )

        if not original and expected_revision_id is not None:
            if row["revision_id"] != expected_revision_id:
                raise CoreDomainError(
                    "PRESENTATION_REVISION_CONFLICT",
                    "The current presentation changed. Refresh and export again.",
                    retryable=True,
                )

        relative_path = row["local_snapshot_path"]
        expected_sha256 = row["sha256"]
        byte_size = row["byte_size"]
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or not 0 < byte_size <= MAX_SOURCE_BYTES
        ):
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_CHANGED",
                "The stored presentation no longer matches its imported record.",
            )

        snapshot = self._storage.paths.snapshot_path(project_id, relative_path, require_exists=True)
        destination = self._validated_export_destination(destination_value, snapshot)
        temporary_path: Path | None = None
        try:
            with snapshot.open("rb") as source:
                if os.fstat(source.fileno()).st_size != byte_size:
                    raise CoreDomainError(
                        "SOURCE_SNAPSHOT_CHANGED",
                        "The stored presentation no longer matches its imported record.",
                    )
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=".presenter-copilot-",
                    suffix=".tmp",
                    dir=destination.parent,
                )
                temporary_path = Path(temporary_name)
                digest = hashlib.sha256()
                copied = 0
                try:
                    output = os.fdopen(descriptor, "wb")
                except OSError:
                    os.close(descriptor)
                    raise
                with output:
                    while chunk := source.read(1024 * 1024):
                        copied += len(chunk)
                        if copied > byte_size or copied > MAX_SOURCE_BYTES:
                            raise CoreDomainError(
                                "SOURCE_SNAPSHOT_CHANGED",
                                "The stored presentation no longer matches its imported record.",
                            )
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if copied != byte_size or digest.hexdigest() != expected_sha256:
                    raise CoreDomainError(
                        "SOURCE_SNAPSHOT_CHANGED",
                        "The stored presentation no longer matches its imported record.",
                    )
            os.replace(temporary_path, destination)
            temporary_path = None
        except CoreDomainError:
            raise
        except OSError as error:
            raise CoreDomainError(
                "PRESENTATION_EXPORT_FAILED",
                "The presentation copy could not be saved.",
                retryable=True,
            ) from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

        return {
            "saved": True,
            "file_name": destination.name,
            "byte_size": byte_size,
            "sha256": expected_sha256,
            "copy_kind": "original" if original else "current_revision",
            **({"revision_id": row["revision_id"]} if not original else {}),
        }

    def _validated_export_destination(self, value: str, snapshot: Path) -> Path:
        destination = Path(value)
        if not destination.is_absolute() or destination.suffix.casefold() != ".pptx":
            raise CoreDomainError(
                "PRESENTATION_EXPORT_DESTINATION_INVALID",
                "Choose an absolute destination ending in .pptx.",
            )
        try:
            parent = destination.parent.resolve(strict=True)
            if not parent.is_dir():
                raise ValueError("destination parent is not a directory")
            validated = parent / destination.name
            if (
                not destination.name
                or destination.name in {".", ".."}
                or validated.is_symlink()
                or (validated.exists() and not validated.is_file())
            ):
                raise ValueError("destination is not a regular file path")
            resolved = validated.resolve(strict=False)
            storage_root = self._storage.paths.root.resolve()
            if resolved == snapshot.resolve(strict=True) or resolved.is_relative_to(storage_root):
                raise ValueError("destination is inside application storage")
            return validated
        except CoreDomainError:
            raise
        except (OSError, RuntimeError, ValueError) as error:
            raise CoreDomainError(
                "PRESENTATION_EXPORT_DESTINATION_INVALID",
                "Choose a writable .pptx file outside Presenter Copilot storage.",
            ) from error

    def read_source(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "session_id", "offset", "max_bytes"},
        )
        project_id = self._project_id(params)
        document_id = self._document_id(params)
        session_id = params.get("session_id")
        if not isinstance(session_id, str) or not session_id or len(session_id) > 64:
            raise invalid_request("session_id must be a valid reader session.", field="session_id")
        offset = self._bounded_integer(params, "offset", minimum=0, maximum=MAX_SOURCE_BYTES)
        max_bytes = self._bounded_integer(
            params, "max_bytes", minimum=1, maximum=MAX_READ_CHUNK_BYTES
        )
        self._expire_readers()
        reader = self._readers.get(session_id)
        if reader is None or (reader.project_id, reader.document_id) != (
            project_id,
            document_id,
        ):
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_READER_EXPIRED",
                "The presentation preview reader has expired. Open the preview again.",
                retryable=True,
            )
        if offset != reader.offset:
            raise invalid_request("offset must match the next unread byte.", field="offset")

        requested = min(max_bytes, reader.byte_size - reader.offset)
        try:
            chunk = reader.handle.read(requested)
            if len(chunk) != requested:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation changed while it was being previewed.",
                )
            reader.digest.update(chunk)
            reader.offset += len(chunk)
            complete = reader.offset == reader.byte_size
            if complete and (
                reader.handle.read(1) != b"" or reader.digest.hexdigest() != reader.expected_sha256
            ):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation changed while it was being previewed.",
                )
        except CoreDomainError:
            self._close_reader(session_id)
            raise
        except OSError as error:
            self._close_reader(session_id)
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_FAILED", "The selected presentation cannot be read."
            ) from error

        if complete:
            self._close_reader(session_id)
        else:
            reader.expires_at = self._clock() + READER_TTL_SECONDS
        return {
            "offset": offset,
            "bytes_b64": base64.b64encode(chunk).decode("ascii"),
            "complete": complete,
        }

    def close_source(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "document_id", "session_id"})
        project_id = self._project_id(params)
        document_id = self._document_id(params)
        session_id = params.get("session_id")
        if not isinstance(session_id, str) or not session_id or len(session_id) > 64:
            raise invalid_request("session_id must be a valid reader session.", field="session_id")
        reader = self._readers.get(session_id)
        closed = bool(
            reader is not None
            and (reader.project_id, reader.document_id) == (project_id, document_id)
        )
        if closed:
            self._close_reader(session_id)
        return {"closed": closed}

    def close_source_readers(self, project_id: str, document_id: str) -> None:
        for session_id, reader in tuple(self._readers.items()):
            if (reader.project_id, reader.document_id) == (project_id, document_id):
                self._close_reader(session_id)

    def close_project(self, project_id: str) -> None:
        for session_id, reader in tuple(self._readers.items()):
            if reader.project_id == project_id:
                self._close_reader(session_id)

    def close(self) -> None:
        for session_id in tuple(self._readers):
            self._close_reader(session_id)

    def _expire_readers(self) -> None:
        now = self._clock()
        for session_id, reader in tuple(self._readers.items()):
            if reader.expires_at <= now:
                self._close_reader(session_id)

    def _close_reader(self, session_id: str) -> None:
        reader = self._readers.pop(session_id, None)
        if reader is not None:
            reader.handle.close()

    @staticmethod
    def _project_id(params: dict[str, Any]) -> str:
        value = params.get("project_id")
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _document_id(params: dict[str, Any]) -> str:
        value = params.get("document_id")
        if not isinstance(value, str):
            raise invalid_request("document_id must be a UUID.", field="document_id")
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request("document_id must be a UUID.", field="document_id") from error

    @staticmethod
    def _bounded_integer(params: dict[str, Any], field: str, *, minimum: int, maximum: int) -> int:
        value = params.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise invalid_request(f"{field} must be between {minimum} and {maximum}.", field=field)
        return value
