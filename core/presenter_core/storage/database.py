"""Small transactional SQLite migration layer for app and project scopes."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path

from presenter_core.errors import CoreDomainError

APP_SCHEMA_VERSION = 2
PROJECT_SCHEMA_VERSION = 3

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
        (2,),
    )


def _migrate_app_v2(connection: sqlite3.Connection) -> None:
    """Add non-secret provider metadata and the global Speaker Profile."""
    connection.execute(
        """
        CREATE TABLE provider_configurations (
            provider_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
            model_id TEXT NOT NULL,
            credential_source TEXT NOT NULL,
            safe_config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE speaker_profiles (
            id TEXT PRIMARY KEY,
            display_name TEXT NULL,
            default_style_policy TEXT NOT NULL CHECK (
                default_style_policy IN (
                    'preserve_voice', 'light_polish', 'executive_concise', 'custom'
                )
            ),
            custom_style_guidance TEXT NULL,
            preferred_answer_seconds INTEGER NULL CHECK (
                preferred_answer_seconds IS NULL OR preferred_answer_seconds BETWEEN 1 AND 3_600
            ),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE speaker_evidence (
            id TEXT PRIMARY KEY,
            speaker_profile_id TEXT NOT NULL
                REFERENCES speaker_profiles(id) ON DELETE CASCADE,
            evidence_type TEXT NOT NULL CHECK (
                evidence_type IN (
                    'preferred_phrase', 'analogy', 'explanation_pattern',
                    'vocabulary', 'coaching_preference', 'rejected_pattern'
                )
            ),
            text TEXT NOT NULL,
            origin_project_id TEXT NULL REFERENCES projects(id) ON DELETE CASCADE,
            origin_session_id TEXT NULL,
            user_approved INTEGER NOT NULL CHECK (user_approved IN (0, 1)),
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX speaker_evidence_profile_idx "
        "ON speaker_evidence(speaker_profile_id, created_at)"
    )
    connection.execute(
        "CREATE INDEX speaker_evidence_origin_project_idx ON speaker_evidence(origin_project_id)"
    )


def _migrate_project_v3(connection: sqlite3.Connection) -> None:
    """Add durable Teach, knowledge, provider-run, and style metadata."""
    connection.execute("ALTER TABLE project ADD COLUMN remote_reasoning_acknowledged_at TEXT NULL")
    connection.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
            mode TEXT NOT NULL CHECK (mode IN ('teach', 'challenge', 'run', 'live_assist')),
            started_at TEXT NOT NULL,
            ended_at TEXT NULL,
            style_policy TEXT NOT NULL CHECK (
                style_policy IN (
                    'preserve_voice', 'light_polish', 'executive_concise', 'custom'
                )
            ),
            privacy_mode TEXT NOT NULL CHECK (
                privacy_mode IN ('local_only', 'selected_context_cloud', 'full_context_cloud')
            ),
            provider_id TEXT NULL,
            current_slide_start INTEGER NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'aborted', 'error')),
            teach_state TEXT NOT NULL DEFAULT 'ready_for_prompt' CHECK (
                teach_state IN (
                    'ready_for_prompt', 'prompted', 'awaiting_user',
                    'candidate_ready', 'completed'
                )
            )
        )
        """
    )
    connection.execute("CREATE INDEX sessions_project_idx ON sessions(project_id, started_at DESC)")
    connection.execute(
        """
        CREATE TABLE utterances (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            actor TEXT NOT NULL CHECK (
                actor IN ('user', 'audience_profile', 'ai_coach', 'unknown_audience')
            ),
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            start_ms INTEGER NULL,
            end_ms INTEGER NULL,
            asr_confidence REAL NULL,
            slide_ordinal INTEGER NULL,
            is_final INTEGER NOT NULL DEFAULT 1 CHECK (is_final IN (0, 1))
        )
        """
    )
    connection.execute(
        "CREATE INDEX utterances_session_idx ON utterances(session_id, created_at, id)"
    )
    connection.execute(
        """
        CREATE TABLE user_statements (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
            origin_session_id TEXT NULL,
            source_utterance_id TEXT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX user_statements_project_idx ON user_statements(project_id, created_at)"
    )
    connection.execute(
        """
        CREATE TABLE knowledge_items (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (
                kind IN (
                    'fact', 'decision', 'rationale', 'preferred_explanation',
                    'analogy', 'private_note', 'constraint', 'objection', 'answer'
                )
            ),
            text TEXT NOT NULL,
            use_live INTEGER NOT NULL CHECK (use_live IN (0, 1)),
            use_rehearsal INTEGER NOT NULL CHECK (use_rehearsal IN (0, 1)),
            preferred INTEGER NOT NULL CHECK (preferred IN (0, 1)),
            private INTEGER NOT NULL CHECK (private IN (0, 1)),
            created_by TEXT NOT NULL CHECK (created_by IN ('user', 'ai_suggested_user_confirmed')),
            origin_session_id TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX knowledge_items_project_idx ON knowledge_items(project_id, updated_at DESC)"
    )
    connection.execute(
        """
        CREATE TABLE knowledge_evidence (
            knowledge_item_id TEXT NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
            provenance_type TEXT NOT NULL CHECK (
                provenance_type IN ('document', 'user_statement', 'transcript', 'practiced_answer')
            ),
            provenance_id TEXT NOT NULL,
            PRIMARY KEY (knowledge_item_id, provenance_type, provenance_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE provider_runs (
            id TEXT PRIMARY KEY,
            session_id TEXT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            task_type TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            privacy_mode TEXT NOT NULL CHECK (
                privacy_mode IN ('local_only', 'selected_context_cloud', 'full_context_cloud')
            ),
            started_at TEXT NOT NULL,
            ended_at TEXT NULL,
            status TEXT NOT NULL CHECK (status IN ('started', 'success', 'error', 'cancelled')),
            input_token_count INTEGER NULL,
            output_token_count INTEGER NULL,
            latency_ms INTEGER NULL,
            context_manifest_json TEXT NOT NULL,
            error_code TEXT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX provider_runs_session_idx ON provider_runs(session_id, started_at)"
    )
    connection.execute(
        """
        CREATE TABLE teach_candidates (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            source_utterance_id TEXT NOT NULL REFERENCES utterances(id) ON DELETE CASCADE,
            proposed_kind TEXT NOT NULL CHECK (
                proposed_kind IN (
                    'fact', 'decision', 'rationale', 'preferred_explanation',
                    'analogy', 'private_note', 'constraint', 'objection', 'answer'
                )
            ),
            proposed_text TEXT NOT NULL,
            provider_run_id TEXT NULL REFERENCES provider_runs(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'confirmed', 'rejected')
            ),
            knowledge_item_id TEXT NULL REFERENCES knowledge_items(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX teach_candidates_session_idx "
        "ON teach_candidates(session_id, status, created_at)"
    )
    connection.execute(
        """
        CREATE TABLE project_style_overrides (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL UNIQUE REFERENCES project(id) ON DELETE CASCADE,
            enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    now = "1970-01-01T00:00:00.000Z"
    project_rows = connection.execute("SELECT id, created_at FROM project").fetchall()
    for row in project_rows:
        connection.execute(
            """
            INSERT INTO project_style_overrides (id, project_id, enabled, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?)
            """,
            (str(uuid.uuid4()), str(row[0]), str(row[1] or now), str(row[1] or now)),
        )
    connection.execute("UPDATE project SET schema_version = ?", (3,))


def connect_app_database(path: str | Path) -> sqlite3.Connection:
    """Migrate and open an app database with foreign keys enabled."""
    database_path = Path(path)
    _migrate_database(
        database_path,
        scope="app",
        migrations=(
            (1, _migrate_app_v1),
            (2, _migrate_app_v2),
        ),
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
            (2, _migrate_project_v2),
            (3, _migrate_project_v3),
        ),
        latest_version=PROJECT_SCHEMA_VERSION,
    )
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
