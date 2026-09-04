"""Authoritative application and project-vault path resolution."""

from __future__ import annotations

import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from presenter_core.errors import CoreDomainError

DATA_ROOT_ENV = "PRESENTER_COPILOT_DATA_ROOT"
APP_DIRECTORY_NAME = "PresenterCopilot"
_PROJECT_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def resolve_app_data_root(data_root: str | Path | None = None) -> Path:
    """Resolve the one application data root used by the core.

    Tests and controlled integrations can pass a root directly or set
    ``PRESENTER_COPILOT_DATA_ROOT``.  The normal Windows location is under
    ``LOCALAPPDATA``; non-Windows fallbacks keep the core testable elsewhere.
    """
    configured_root = data_root or os.environ.get(DATA_ROOT_ENV)
    if configured_root:
        return Path(configured_root).expanduser().resolve()

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return (base / APP_DIRECTORY_NAME).resolve()


def normalize_project_id(value: str) -> str:
    """Return a canonical UUID4 string or reject it."""
    if not isinstance(value, str) or not _PROJECT_ID_PATTERN.fullmatch(value.lower()):
        raise CoreDomainError(
            "PROJECT_ID_INVALID",
            "Project id must be a UUID4.",
            details={},
        )
    try:
        project_id = str(uuid.UUID(value))
    except ValueError as exc:
        raise CoreDomainError("PROJECT_ID_INVALID", "Project id must be a UUID4.") from exc
    if project_id != value.lower() or not _PROJECT_ID_PATTERN.fullmatch(project_id):
        raise CoreDomainError("PROJECT_ID_INVALID", "Project id must be a UUID4.")
    return project_id


@dataclass(frozen=True)
class ProjectPaths:
    """Known paths for one UUID-keyed project vault."""

    project_id: str
    root: Path
    database: Path
    sources: Path
    extracted: Path
    embeddings: Path
    sessions: Path
    diagnostics: Path


class AppPaths:
    """Own all application/project path construction and safety checks."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = resolve_app_data_root(root)
        self.app_database = self.root / "app.db"
        self.projects = self.root / "projects"

    def ensure_layout(self) -> None:
        """Create only the application directories needed by M1."""
        self.root.mkdir(parents=True, exist_ok=True)
        if self.projects.exists() and self.projects.is_symlink():
            raise CoreDomainError(
                "PROJECT_PATH_UNSAFE",
                "The application project root is not a safe local directory.",
            )
        self.projects.mkdir(parents=True, exist_ok=True)

    def project(self, project_id: str, *, require_exists: bool = False) -> ProjectPaths:
        """Resolve a project only from its canonical UUID, never from a path."""
        normalized_id = normalize_project_id(project_id)
        project_root = self.projects / normalized_id
        projects_root = self._safe_projects_root()

        if project_root.is_symlink():
            raise CoreDomainError(
                "PROJECT_PATH_UNSAFE",
                "The project vault path is not a safe local directory.",
            )
        resolved_root = project_root.resolve()
        if resolved_root.parent != projects_root or resolved_root.name != normalized_id:
            raise CoreDomainError(
                "PROJECT_PATH_UNSAFE",
                "The project vault path is not a safe local directory.",
            )
        if require_exists and not project_root.is_dir():
            raise CoreDomainError("PROJECT_NOT_FOUND", "Project was not found.")

        return ProjectPaths(
            project_id=normalized_id,
            root=project_root,
            database=project_root / "project.db",
            sources=project_root / "sources",
            extracted=project_root / "extracted",
            embeddings=project_root / "embeddings",
            sessions=project_root / "sessions",
            diagnostics=project_root / "diagnostics",
        )

    def create_project_directories(self, project_id: str) -> ProjectPaths:
        """Create a new vault with project-owned derived-data directories."""
        paths = self.project(project_id)
        if paths.root.exists():
            raise CoreDomainError("PROJECT_ALREADY_EXISTS", "Project already exists.")
        paths.root.mkdir()
        paths.sources.mkdir()
        paths.embeddings.mkdir()
        return paths

    def snapshot_path(
        self,
        project_id: str,
        relative_path: str,
        *,
        require_exists: bool = False,
    ) -> Path:
        """Resolve a stored project-relative snapshot within ``sources``."""
        paths = self.project(project_id, require_exists=True)
        sources_root = self.safe_sources_directory(project_id)
        if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
            raise CoreDomainError("SOURCE_PATH_UNSAFE", "Stored source path is invalid.")

        normalized = relative_path.replace("\\", "/")
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(normalized)
        if (
            posix_path.is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or ".." in posix_path.parts
            or not posix_path.parts
            or posix_path.parts[0] != "sources"
            or len(posix_path.parts) != 2
        ):
            raise CoreDomainError("SOURCE_PATH_UNSAFE", "Stored source path is invalid.")

        candidate = paths.root / Path(*posix_path.parts)
        resolved_candidate = candidate.resolve()
        if candidate.is_symlink() or not resolved_candidate.is_relative_to(sources_root.resolve()):
            raise CoreDomainError("SOURCE_PATH_UNSAFE", "Stored source path is invalid.")
        if require_exists and not candidate.is_file():
            raise CoreDomainError("SOURCE_SNAPSHOT_MISSING", "The source snapshot is missing.")
        return candidate

    def safe_sources_directory(self, project_id: str, *, create: bool = False) -> Path:
        """Return the project source directory only when it cannot escape the vault."""
        paths = self.project(project_id, require_exists=True)
        if create:
            paths.sources.mkdir(exist_ok=True)
        if paths.sources.is_symlink() or not paths.sources.is_dir():
            raise CoreDomainError("SOURCE_PATH_UNSAFE", "The project source directory is not safe.")
        resolved_sources = paths.sources.resolve()
        if resolved_sources.parent != paths.root.resolve() or resolved_sources.name != "sources":
            raise CoreDomainError("SOURCE_PATH_UNSAFE", "The project source directory is not safe.")
        return paths.sources

    def safe_embeddings_directory(self, project_id: str, *, create: bool = False) -> Path:
        """Return the project embedding directory only when it is vault-local."""
        paths = self.project(project_id, require_exists=True)
        if create:
            paths.embeddings.mkdir(exist_ok=True)
        if paths.embeddings.is_symlink() or not paths.embeddings.is_dir():
            raise CoreDomainError(
                "EMBEDDING_PATH_UNSAFE",
                "The project embedding directory is not safe.",
            )
        resolved_embeddings = paths.embeddings.resolve()
        if (
            resolved_embeddings.parent != paths.root.resolve()
            or resolved_embeddings.name != "embeddings"
        ):
            raise CoreDomainError(
                "EMBEDDING_PATH_UNSAFE",
                "The project embedding directory is not safe.",
            )
        return paths.embeddings

    def asr_model_cache_directory(self, *, create: bool = False) -> Path:
        """Return the shared app-level ASR model cache, never a project path."""
        models_root = self.root / "models"
        asr_root = models_root / "asr"
        # Validate existing path components before creating anything. In
        # particular, never follow a user-controlled models symlink while the
        # explicit model bootstrap command is creating its cache.
        if models_root.is_symlink() or (models_root.exists() and not models_root.is_dir()):
            raise CoreDomainError(
                "ASR_MODEL_CACHE_UNSAFE",
                "The local ASR model cache is not a safe application directory.",
            )
        if asr_root.is_symlink() or (asr_root.exists() and not asr_root.is_dir()):
            raise CoreDomainError(
                "ASR_MODEL_CACHE_UNSAFE",
                "The local ASR model cache is not a safe application directory.",
            )
        if create:
            models_root.mkdir(parents=True, exist_ok=True)
            asr_root.mkdir(exist_ok=True)
        if models_root.is_symlink() or asr_root.is_symlink() or not asr_root.is_dir():
            raise CoreDomainError(
                "ASR_MODEL_CACHE_UNSAFE",
                "The local ASR model cache is not a safe application directory.",
            )
        resolved_root = self.root.resolve()
        resolved_asr = asr_root.resolve()
        if resolved_asr.parent != resolved_root / "models" or not resolved_asr.is_relative_to(
            resolved_root
        ):
            raise CoreDomainError(
                "ASR_MODEL_CACHE_UNSAFE",
                "The local ASR model cache is not a safe application directory.",
            )
        return asr_root

    def embedding_matrix_path(
        self,
        project_id: str,
        relative_path: str,
        *,
        require_exists: bool = False,
    ) -> Path:
        """Resolve one stored matrix path inside the project embedding directory."""
        paths = self.project(project_id, require_exists=True)
        embeddings_root = self.safe_embeddings_directory(project_id)
        if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
            raise CoreDomainError("EMBEDDING_PATH_UNSAFE", "Stored embedding path is invalid.")

        normalized = relative_path.replace("\\", "/")
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(normalized)
        if (
            posix_path.is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or ".." in posix_path.parts
            or len(posix_path.parts) != 2
            or posix_path.parts[0] != "embeddings"
            or not posix_path.parts[1].endswith(".npy")
        ):
            raise CoreDomainError("EMBEDDING_PATH_UNSAFE", "Stored embedding path is invalid.")

        candidate = paths.root / Path(*posix_path.parts)
        resolved_candidate = candidate.resolve()
        if candidate.is_symlink() or not resolved_candidate.is_relative_to(
            embeddings_root.resolve()
        ):
            raise CoreDomainError("EMBEDDING_PATH_UNSAFE", "Stored embedding path is invalid.")
        if require_exists and not candidate.is_file():
            raise CoreDomainError(
                "RETRIEVAL_INDEX_CORRUPT",
                "The active embedding matrix is missing.",
            )
        return candidate

    def _safe_projects_root(self) -> Path:
        if self.projects.is_symlink() or not self.projects.is_dir():
            raise CoreDomainError(
                "PROJECT_PATH_UNSAFE",
                "The application project root is not a safe local directory.",
            )
        resolved_projects = self.projects.resolve()
        expected_projects = self.root.resolve() / "projects"
        if resolved_projects != expected_projects:
            raise CoreDomainError(
                "PROJECT_PATH_UNSAFE",
                "The application project root is not a safe local directory.",
            )
        return resolved_projects

    def project_directory_ids(self) -> list[str]:
        """List every safe, UUID-keyed project directory under the app root."""
        projects_root = self._safe_projects_root()
        try:
            entries = sorted(projects_root.iterdir(), key=lambda path: path.name)
        except OSError as error:
            raise CoreDomainError(
                "PROJECT_PATH_UNSAFE",
                "The application project root could not be inspected.",
                retryable=True,
            ) from error

        project_ids: list[str] = []
        for entry in entries:
            if entry.is_symlink() or not entry.is_dir():
                raise CoreDomainError(
                    "PROJECT_PATH_UNSAFE",
                    "The application project root contains an unsafe entry.",
                )
            try:
                project_id = normalize_project_id(entry.name)
            except CoreDomainError as error:
                raise CoreDomainError(
                    "PROJECT_PATH_UNSAFE",
                    "The application project root contains an unknown entry.",
                ) from error
            resolved_entry = entry.resolve()
            if resolved_entry.parent != projects_root or resolved_entry.name != project_id:
                raise CoreDomainError(
                    "PROJECT_PATH_UNSAFE",
                    "The application project root contains an unsafe entry.",
                )
            project_ids.append(project_id)
        return project_ids

    def delete_all_project_directories(self) -> int:
        """Delete all safe app-owned project directories, including orphans."""
        project_ids = self.project_directory_ids()
        for project_id in project_ids:
            self.delete_project_directory(project_id)
        return len(project_ids)

    def delete_project_directory(self, project_id: str) -> bool:
        """Delete one already-resolved project directory, safely and idempotently."""
        paths = self.project(project_id)
        if not paths.root.exists():
            return False
        if not paths.root.is_dir() or paths.root.is_symlink():
            raise CoreDomainError(
                "PROJECT_DELETE_FAILED",
                "The project vault is not a safe directory.",
            )
        resolved_root = paths.root.resolve()
        if (
            resolved_root.parent != self._safe_projects_root()
            or resolved_root.name != paths.project_id
        ):
            raise CoreDomainError(
                "PROJECT_DELETE_FAILED",
                "The project vault is outside the application project root.",
            )
        try:
            # Windows can briefly retain a SQLite or antivirus handle after a
            # request completes. Retrying the same already-validated target
            # keeps deletion idempotent without broadening its scope.
            for attempt in range(3):
                try:
                    shutil.rmtree(paths.root)
                    break
                except OSError:
                    if attempt == 2:
                        raise
                    time.sleep(0.1 * (attempt + 1))
        except OSError as exc:
            raise CoreDomainError(
                "PROJECT_DELETE_FAILED",
                "The project vault could not be deleted.",
                retryable=True,
                details={},
            ) from exc
        return True

    def delete_model_cache(self, kind: str) -> bool:
        """Delete one approved shared model cache, never a project directory."""
        targets = self.model_cache_directories(kind)
        removed = False
        for target in targets:
            if not target.exists():
                continue
            try:
                shutil.rmtree(target)
            except OSError as exc:
                raise CoreDomainError(
                    "MODEL_CACHE_DELETE_FAILED",
                    "The shared model cache could not be removed.",
                    retryable=True,
                ) from exc
            removed = True
        return removed

    def model_cache_directories(self, kind: str) -> tuple[Path, ...]:
        """Validate and return only the fixed shared model-cache directories."""
        if kind not in {"asr", "embeddings", "all"}:
            raise CoreDomainError("MODEL_KIND_INVALID", "The requested model cache is unsupported.")
        models_root = self.root / "models"
        if models_root.is_symlink() or (models_root.exists() and not models_root.is_dir()):
            raise CoreDomainError(
                "MODEL_CACHE_UNSAFE",
                "The shared model cache is not a safe application directory.",
            )
        try:
            resolved_models_root = models_root.resolve()
            expected_models_root = self.root.resolve() / "models"
        except OSError as error:
            raise CoreDomainError(
                "MODEL_CACHE_UNSAFE",
                "The shared model cache could not be resolved.",
                retryable=True,
            ) from error
        if resolved_models_root != expected_models_root:
            raise CoreDomainError(
                "MODEL_CACHE_UNSAFE",
                "The shared model cache is outside the application data root.",
            )
        names = ("asr", "embeddings") if kind == "all" else (kind,)
        targets = tuple(models_root / name for name in names)
        for target in targets:
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise CoreDomainError(
                    "MODEL_CACHE_UNSAFE",
                    "The shared model cache is not a safe application directory.",
                )
            if target.exists():
                try:
                    resolved = target.resolve()
                except OSError as error:
                    raise CoreDomainError(
                        "MODEL_CACHE_UNSAFE",
                        "The shared model cache could not be resolved.",
                        retryable=True,
                    ) from error
                if resolved.parent != resolved_models_root or resolved.name != target.name:
                    raise CoreDomainError(
                        "MODEL_CACHE_UNSAFE",
                        "The shared model cache is outside the application data root.",
                    )
        return targets
