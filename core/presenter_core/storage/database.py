"""Small transactional SQLite migration layer for app and project scopes."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path

from presenter_core.errors import CoreDomainError

APP_SCHEMA_VERSION = 1
PROJECT_SCHEMA_VERSION = 2

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


def _migrate_project_v2(connection: sqlite3.Connection) -> None:
    """Add generation-based, project-local semantic index metadata."""
    connection.execute(
        """
        CREATE TABLE embedding_generations (
            id TEXT PRIMARY KEY,
            adapter_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            model_fingerprint TEXT NOT NULL CHECK (length(model_fingerprint) >= 16),
            dimension INTEGER NOT NULL CHECK (dimension > 0),
            matrix_relative_path TEXT NOT NULL UNIQUE,
            matrix_row_count INTEGER NOT NULL CHECK (matrix_row_count >= 0),
            is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX embedding_generations_one_active_idx
        ON embedding_generations(is_active)
        WHERE is_active = 1
        """
    )
    connection.execute(
        """
        CREATE TABLE embedding_vectors (
            generation_id TEXT NOT NULL REFERENCES embedding_generations(id) ON DELETE CASCADE,
            vector_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
            source_class TEXT NOT NULL,
            row_index INTEGER NOT NULL CHECK (row_index >= 0),
            content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
            PRIMARY KEY (generation_id, vector_id),
            UNIQUE (generation_id, entity_type, entity_id),
            UNIQUE (generation_id, row_index)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX embedding_vectors_entity_idx
        ON embedding_vectors(entity_type, entity_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX embedding_vectors_generation_row_idx
        ON embedding_vectors(generation_id, row_index)
        """
    )
    connection.execute(
        """
        CREATE INDEX documents_project_status_idx
        ON documents(project_id, parse_status, id)
        """
    )
    connection.execute(
        """
        CREATE INDEX embedding_vectors_generation_entity_project_idx
        ON embedding_vectors(generation_id, entity_type, project_id, row_index)
        """
    )
    connection.execute(
        """
        CREATE TRIGGER chunks_delete_embedding_vectors
        AFTER DELETE ON chunks
        BEGIN
            DELETE FROM embedding_vectors
            WHERE entity_type = 'chunk' AND entity_id = OLD.id;
        END
        """
    )
    connection.execute(
        "UPDATE project SET schema_version = ?",
        (PROJECT_SCHEMA_VERSION,),
    )


def connect_app_database(path: str | Path) -> sqlite3.Connection:
    """Migrate and open an app database with foreign keys enabled."""
    database_path = Path(path)
    _migrate_database(
        database_path,
        scope="app",
        migrations=((APP_SCHEMA_VERSION, _migrate_app_v1),),
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
        migrations=(
            (1, _migrate_project_v1),
            (PROJECT_SCHEMA_VERSION, _migrate_project_v2),
        ),
        latest_version=PROJECT_SCHEMA_VERSION,
    )
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
