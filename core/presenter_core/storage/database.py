"""Small transactional SQLite migration layer for app and project scopes."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path

from presenter_core.errors import CoreDomainError

APP_SCHEMA_VERSION = 1
PROJECT_SCHEMA_VERSION = 1

Migration = tuple[int, Callable[[sqlite3.Connection], None]]


def current_schema_version(connection: sqlite3.Connection) -> int:
    """Read SQLite's integer schema version."""
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def _set_schema_version(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(f"PRAGMA user_version = {version}")


def _migrate_database(
    path: Path,
    *,
    scope: str,
    migrations: Iterable[Migration],
    latest_version: int,
) -> None:
    """Apply all supported migrations in one transaction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        version = current_schema_version(connection)
        if version > latest_version:
            raise CoreDomainError(
                "DATABASE_VERSION_UNSUPPORTED",
                "The database was created by a newer application version.",
                details={
                    "scope": scope,
                    "current_version": version,
                    "supported_version": latest_version,
                },
            )

        migration_list = tuple(migrations)
        connection.execute("BEGIN IMMEDIATE")
        for migration_version, migration in migration_list:
            if migration_version <= version:
                continue
            migration(connection)
            _set_schema_version(connection, migration_version)
        connection.commit()
    except CoreDomainError:
        if connection.in_transaction:
            connection.rollback()
        raise
    except (OSError, sqlite3.Error, ValueError) as exc:
        if connection.in_transaction:
            connection.rollback()
        raise CoreDomainError(
            "DATABASE_MIGRATION_FAILED",
            "The database migration failed without replacing the database.",
            retryable=False,
            details={"scope": scope},
        ) from exc
    finally:
        connection.close()


def _migrate_app_v1(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE app_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            project_relative_path TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_opened_at TEXT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX projects_last_opened_idx ON projects(last_opened_at DESC, updated_at DESC)"
    )


def _migrate_project_v1(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE project (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            privacy_mode TEXT NOT NULL CHECK (
                privacy_mode IN ('local_only', 'selected_context_cloud', 'full_context_cloud')
            ),
            default_style_policy TEXT NOT NULL CHECK (
                default_style_policy IN (
                    'preserve_voice', 'light_polish', 'executive_concise', 'custom'
                )
            ),
            custom_style_guidance TEXT NULL,
            current_presentation_id TEXT NULL,
            schema_version INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('presentation', 'supporting', 'transcript', 'note')),
            original_name TEXT NOT NULL,
            local_snapshot_path TEXT NULL,
            source_uri TEXT NULL,
            sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
            mime_type TEXT NOT NULL,
            parser_id TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            parse_status TEXT NOT NULL CHECK (parse_status IN ('pending', 'ready', 'error')),
            parse_error_code TEXT NULL,
            parse_error_message TEXT NULL,
            byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
            metadata_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX documents_project_hash_idx ON documents(project_id, sha256)"
    )
    connection.execute(
        """
        CREATE TABLE source_units (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            unit_type TEXT NOT NULL CHECK (
                unit_type IN ('slide', 'page', 'section', 'transcript_segment', 'user_note')
            ),
            ordinal INTEGER NULL,
            title TEXT NULL,
            start_ms INTEGER NULL,
            end_ms INTEGER NULL,
            speaker_label TEXT NULL,
            text TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE chunks (
            id TEXT PRIMARY KEY,
            source_unit_id TEXT NOT NULL REFERENCES source_units(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
            text TEXT NOT NULL,
            token_count INTEGER NULL,
            embedding_key TEXT NULL,
            lexical_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(source_unit_id, chunk_index)
        )
        """
    )
    connection.execute(
        "CREATE INDEX source_units_document_idx ON source_units(document_id, ordinal, id)"
    )
    connection.execute(
        "CREATE INDEX chunks_source_unit_idx ON chunks(source_unit_id, chunk_index, id)"
    )


def connect_app_database(path: str | Path) -> sqlite3.Connection:
    """Migrate and open an app database with foreign keys enabled."""
    database_path = Path(path)
    _migrate_database(
        database_path,
        scope="app",
        migrations=((1, _migrate_app_v1),),
        latest_version=APP_SCHEMA_VERSION,
    )
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def connect_project_database(path: str | Path) -> sqlite3.Connection:
    """Migrate and open a project database with foreign keys enabled."""
    database_path = Path(path)
    _migrate_database(
        database_path,
        scope="project",
        migrations=((1, _migrate_project_v1),),
        latest_version=PROJECT_SCHEMA_VERSION,
    )
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
