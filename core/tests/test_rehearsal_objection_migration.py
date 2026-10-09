"""Schema22 preserves populated coverage history and bounds objection candidate slots."""

import hashlib
import sqlite3

import pytest
import test_rehearsal_coverage as coverage_tests
from test_presentation_planning import call
from test_rehearsal_analysis_store import saved
from test_rehearsal_semantic_adoption import selection

from presenter_core.errors import CoreDomainError
from presenter_core.storage.database import connect_project_database

rehearsal = coverage_tests.rehearsal


def test_populated_schema21_upgrade_preserves_reviews_audits_recording_and_native_files(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    call(core, "presentation.workspace.reject_rehearsal_finding", selection(scope, result))
    paths = core._storage.project_paths(scope["project_id"])
    native = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.root.rglob("*.pptx")
    }
    app = core._storage.paths.app_database.read_bytes()
    tables = (
        "sessions",
        "utterances",
        "documents",
        "presentation_revisions",
        "run_debriefs",
        "provider_runs",
        "presentation_rehearsal_analyses",
        "presentation_rehearsal_reviews",
    )
    with sqlite3.connect(paths.database) as db:
        db.execute("DROP TABLE presentation_rehearsal_objection_comparison_candidates")
        db.execute("DROP TABLE presentation_rehearsal_objection_comparisons")
        db.execute("DROP TABLE presentation_rehearsal_objection_findings")
        db.execute("DROP TABLE presentation_rehearsal_objection_analyses")
        db.execute("PRAGMA user_version=21")
        db.execute("UPDATE project SET schema_version=21")
        before = {
            table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in tables
        }
    migrated = connect_project_database(paths.database)
    try:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 23
        assert migrated.execute("SELECT schema_version FROM project").fetchone()[0] == 23
        for table in tables:
            assert [
                tuple(r) for r in migrated.execute(f"SELECT * FROM {table} ORDER BY rowid")
            ] == before[table]
        assert not migrated.execute(
            "SELECT * FROM presentation_rehearsal_objection_analyses"
        ).fetchall()
        assert not migrated.execute(
            "SELECT * FROM presentation_rehearsal_objection_findings"
        ).fetchall()
    finally:
        migrated.close()
    assert core._storage.paths.app_database.read_bytes() == app
    assert {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.root.rglob("*.pptx")
    } == native


def test_schema22_collision_rolls_back_both_versions_and_preserves_previous_history(rehearsal):
    core, scope = rehearsal
    saved(core, scope)
    path = core._storage.project_paths(scope["project_id"]).database
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=21")
        db.execute("UPDATE project SET schema_version=21")
    with pytest.raises(CoreDomainError) as error:
        connect_project_database(path)
    assert error.value.code == "DATABASE_MIGRATION_FAILED"
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 21
        assert db.execute("SELECT schema_version FROM project").fetchone()[0] == 21
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_analyses").fetchone()[0] == 1
        db.execute("PRAGMA user_version=23")
        db.execute("UPDATE project SET schema_version=23")


def test_candidate_slots_are_unique_bounded_and_cascade_with_their_analysis(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    # Exercise SQL constraints only. Domain storage must separately reject a
    # coverage audit used as an objection audit; this is not a valid saved hint.
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute(
            "INSERT INTO presentation_rehearsal_objection_analyses "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                result["provider_run_id"],
                scope["document_id"],
                scope["session_id"],
                scope["expected_revision_id"],
                scope["expected_revision_id"],
                "a" * 64,
                "b" * 64,
                0,
                "local_only",
                '{"observations":[]}',
                "c" * 64,
                "now",
            ),
        )
        db.execute(
            "INSERT INTO presentation_rehearsal_objection_findings VALUES (?,?,0)",
            ("a" * 64, result["provider_run_id"]),
        )
        for identity, run, index in (
            ("b" * 64, result["provider_run_id"], 0),
            ("c" * 64, result["provider_run_id"], 4),
            ("d" * 64, "unknown-analysis", 1),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO presentation_rehearsal_objection_findings VALUES (?,?,?)",
                    (identity, run, index),
                )
        db.execute(
            "DELETE FROM presentation_rehearsal_objection_analyses WHERE provider_run_id=?",
            (result["provider_run_id"],),
        )
        assert not db.execute("SELECT * FROM presentation_rehearsal_objection_findings").fetchall()
        db.commit()
