"""Safe, previewable diagnostic metadata and ZIP export."""

from __future__ import annotations

import json
import os
import platform
import shutil
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from presenter_core import CORE_VERSION
from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.safe_logging import SafeLogger
from presenter_core.storage.database import APP_SCHEMA_VERSION, PROJECT_SCHEMA_VERSION
from presenter_core.storage.service import StorageManager

SafeProjection = Callable[[], dict[str, Any]]
_SECTIONS = frozenset({"core", "storage", "models", "provider", "logs", "benchmarks"})


class DiagnosticService:
    """Keep export content metadata-only and output authority outside the renderer."""

    def __init__(
        self,
        storage: StorageManager,
        logger: SafeLogger,
        *,
        core_status: SafeProjection,
        models: SafeProjection,
        provider: SafeProjection,
    ) -> None:
        self._storage = storage
        self._logger = logger
        self._core_status = core_status
        self._models = models
        self._provider = provider

    def preview(self, params: dict[str, Any]) -> dict[str, Any]:
        sections = _requested_sections(params)
        projection = self._projection()
        if sections is None:
            return projection
        return {
            "schema_version": projection["schema_version"],
            "timestamp": projection["timestamp"],
            **{section: projection[section] for section in sections if section in projection},
        }

    def export(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"output_path", "sections"})
        output_value = params.get("output_path")
        if not isinstance(output_value, str) or not output_value or "\x00" in output_value:
            raise invalid_request(
                "output_path must be a selected output file.", field="output_path"
            )
        destination = Path(output_value).expanduser()
        if not destination.is_absolute() or destination.is_symlink():
            raise CoreDomainError(
                "DIAGNOSTIC_EXPORT_PATH_UNSAFE",
                "The diagnostic destination is not a safe selected file.",
            )
        if destination.exists() and destination.is_dir():
            raise CoreDomainError(
                "DIAGNOSTIC_EXPORT_PATH_UNSAFE",
                "The diagnostic destination must be a file.",
            )
        if destination.suffix.casefold() != ".zip":
            destination = destination.with_suffix(".zip")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise CoreDomainError(
                "DIAGNOSTIC_EXPORT_FAILED",
                "The diagnostic export destination is unavailable.",
                retryable=True,
            ) from error

        preview_params: dict[str, Any] = {}
        if "sections" in params:
            preview_params["sections"] = params["sections"]
        projection = self.preview(preview_params)
        staging = self._storage.paths.root / f".diagnostic-staging-{uuid.uuid4()}"
        temporary_output = destination.with_name(f".{destination.name}.{uuid.uuid4()}.tmp")
        try:
            if staging.exists() or staging.is_symlink():
                raise CoreDomainError(
                    "DIAGNOSTIC_EXPORT_FAILED",
                    "The diagnostic staging directory is not safe.",
                    retryable=True,
                )
            staging.mkdir(parents=True)
            (staging / "diagnostics.json").write_text(
                json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            safe_logs = projection.get("logs", [])
            (staging / "logs.jsonl").write_text(
                "".join(
                    json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                    + "\n"
                    for item in safe_logs
                    if isinstance(item, dict)
                ),
                encoding="utf-8",
            )
            with zipfile.ZipFile(
                temporary_output,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                archive.write(staging / "diagnostics.json", "diagnostics.json")
                archive.write(staging / "logs.jsonl", "logs.jsonl")
            os.replace(temporary_output, destination)
            size_bytes = destination.stat().st_size
        except CoreDomainError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            raise CoreDomainError(
                "DIAGNOSTIC_EXPORT_FAILED",
                "The diagnostic export could not be created; no project data was changed.",
                retryable=True,
            ) from error
        finally:
            _remove_tree(staging)
            try:
                if temporary_output.exists() and not temporary_output.is_symlink():
                    temporary_output.unlink()
            except OSError:
                pass
        self._logger.event(
            "diagnostics.exported",
            {"operation": "diagnostic_export", "size_bytes": size_bytes},
        )
        return {
            "exported": True,
            "format": "zip",
            "file_name": destination.name[:160],
            "size_bytes": size_bytes,
            "included_sections": [
                key for key in projection if key not in {"schema_version", "timestamp"}
            ],
        }

    def _projection(self) -> dict[str, Any]:
        project_count = 0
        unavailable_count = 0
        session_count = 0
        for row in self._storage.list_app_rows():
            project_count += 1
            try:
                with self._storage.project_database(str(row["id"])) as connection:
                    count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()
                    session_count += int(count[0]) if count else 0
            except Exception:
                unavailable_count += 1
        return {
            "schema_version": 1,
            "timestamp": self._timestamp(),
            "core": self._core_status(),
            "storage": {
                "app_schema_version": APP_SCHEMA_VERSION,
                "project_schema_version": PROJECT_SCHEMA_VERSION,
                "project_count": project_count,
                "unavailable_project_count": unavailable_count,
                "session_count": session_count,
            },
            "models": self._models(),
            "provider": self._provider(),
            "logs": self._logger.recent(50),
            "benchmarks": {
                "status": "metadata_only",
                "automatic_question_segmentation": "not_applicable",
            },
            "runtime": {
                "os": platform.system(),
                "os_release": platform.release(),
                "architecture": platform.machine(),
                "python": platform.python_version(),
                "core_version": CORE_VERSION,
                "pid_present": True,
            },
        }

    @staticmethod
    def _timestamp() -> str:
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _requested_sections(params: dict[str, Any]) -> tuple[str, ...] | None:
    reject_unknown_fields(params, {"sections"})
    if "sections" not in params:
        return None
    sections = params["sections"]
    if not isinstance(sections, list) or len(sections) > len(_SECTIONS):
        raise invalid_request(
            "sections must be a bounded list of safe diagnostic sections.", field="sections"
        )
    result: list[str] = []
    for section in sections:
        if not isinstance(section, str) or section not in _SECTIONS or section in result:
            raise invalid_request(
                "sections contains an unsupported diagnostic section.", field="sections"
            )
        result.append(section)
    return tuple(result)


def _remove_tree(path: Path) -> None:
    if not path.exists() or path.is_symlink():
        return
    try:
        shutil.rmtree(path)
    except OSError:
        pass
