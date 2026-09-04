"""Bounded, non-executing import preflight for untrusted source files."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final

from presenter_core.errors import CoreDomainError

MAX_SOURCE_BYTES: Final = 50 * 1024 * 1024
MAX_ARCHIVE_ENTRIES: Final = 2_048
MAX_ARCHIVE_EXPANDED_BYTES: Final = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBER_NAME_LENGTH: Final = 512
MAX_SOURCE_UNITS: Final = 5_000
MAX_EXTRACTED_TEXT_CHARS: Final = 20_000_000

SOURCE_TYPE_BY_SUFFIX: Final = {
    ".pdf": "pdf",
    ".pptx": "pptx",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".vtt": "vtt",
    ".srt": "srt",
    ".json": "json",
}


def source_type_for_path(path: Path) -> str:
    source_type = SOURCE_TYPE_BY_SUFFIX.get(path.suffix.casefold())
    if source_type is None:
        raise CoreDomainError(
            "SOURCE_TYPE_UNSUPPORTED",
            "This source type is not supported.",
            details={},
        )
    return source_type


def preflight_source(path: Path, source_type: str) -> int:
    """Validate size/signature/archive bounds before parser consumption."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise CoreDomainError(
            "SOURCE_SNAPSHOT_FAILED", "The selected source cannot be read."
        ) from exc
    if size > MAX_SOURCE_BYTES:
        raise CoreDomainError(
            "SOURCE_TOO_LARGE",
            "The source exceeds the import size limit.",
            details={"max_bytes": MAX_SOURCE_BYTES},
        )

    if source_type == "pdf":
        try:
            with path.open("rb") as handle:
                signature = handle.read(5)
        except OSError as exc:
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_FAILED", "The selected source cannot be read."
            ) from exc
        if signature != b"%PDF-":
            raise CoreDomainError(
                "SOURCE_PARSE_FAILED",
                "The file extension does not match a readable PDF source.",
                details={"source_type": source_type},
            )
    elif source_type == "pptx":
        preflight_pptx_archive(path)
    return size


def preflight_pptx_archive(path: Path) -> None:
    """Inspect a PPTX ZIP central directory without extracting or executing it."""
    try:
        with zipfile.ZipFile(path, "r") as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise CoreDomainError(
                    "SOURCE_ARCHIVE_UNSAFE",
                    "The presentation archive contains too many entries.",
                    details={"max_entries": MAX_ARCHIVE_ENTRIES},
                )

            expanded_bytes = 0
            names: set[str] = set()
            for entry in entries:
                normalized_name = _validate_archive_member(entry.filename)
                if normalized_name.casefold() in names:
                    raise CoreDomainError(
                        "SOURCE_ARCHIVE_UNSAFE",
                        "The presentation archive contains duplicate member names.",
                        details={},
                    )
                names.add(normalized_name.casefold())
                if entry.flag_bits & 0x1:
                    raise CoreDomainError(
                        "SOURCE_ARCHIVE_UNSAFE",
                        "Encrypted presentation archives are not supported.",
                        details={},
                    )
                expanded_bytes += max(0, entry.file_size)
                if expanded_bytes > MAX_ARCHIVE_EXPANDED_BYTES:
                    raise CoreDomainError(
                        "SOURCE_ARCHIVE_UNSAFE",
                        "The presentation archive expands beyond the import limit.",
                        details={"max_expanded_bytes": MAX_ARCHIVE_EXPANDED_BYTES},
                    )
                mode = (entry.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise CoreDomainError(
                        "SOURCE_ARCHIVE_UNSAFE",
                        "The presentation archive contains a symbolic link.",
                        details={},
                    )

            if "[content_types].xml" not in names or "ppt/presentation.xml" not in names:
                raise CoreDomainError(
                    "SOURCE_PARSE_FAILED",
                    "The PPTX archive is missing required presentation parts.",
                    details={"source_type": "pptx"},
                )
    except CoreDomainError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise CoreDomainError(
            "SOURCE_PARSE_FAILED",
            "The PPTX archive is malformed.",
            details={"source_type": "pptx"},
        ) from exc


def _validate_archive_member(name: str) -> str:
    normalized = name.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(normalized)
    if (
        not normalized
        or len(normalized) > MAX_ARCHIVE_MEMBER_NAME_LENGTH
        or "\x00" in name
        or any(ord(character) < 32 for character in name)
        or posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in posix_path.parts
    ):
        raise CoreDomainError(
            "SOURCE_ARCHIVE_UNSAFE",
            "The presentation archive contains an unsafe path.",
            details={},
        )
    return normalized
