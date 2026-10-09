"""Immutable rehearsal hints survive Core restart without becoming approved knowledge."""

import json
import sqlite3
import uuid

import pytest
import test_rehearsal_coverage as coverage_tests
from test_presentation_planning import call
from test_rehearsal_semantic_analysis import CoverageProvider, analysis, params
from test_rehearsal_semantic_context import selection

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.claims import digest
from presenter_core.presentation.rehearsal_analysis_store import (
    RehearsalAnalysisStore,
    validate_snapshot,
)
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter
from presenter_core.storage.database import connect_project_database

rehearsal = coverage_tests.rehearsal


def saved(core, scope):
    return analysis(core, CoverageProvider()).analyze(params(core, scope))


def read(core, scope, result):
    return RehearsalAnalysisStore(core._presentation_semantics).read(
        {
            **{key: scope[key] for key in ("project_id", "document_id", "expected_revision_id")},
            "finding_id": result["finding_id"],
        }
    )


def test_immutable_result_restart_and_distinct_retry(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    item = read(core, scope, result)
    assert item["can_adopt"] and item["context_current"] and item["requires_user_review"]
    assert item["snapshot"]["hint"] == result["hint"] and item["disposition"] == "unreviewed"
    other = saved(core, scope)
    assert other["finding_id"] != result["finding_id"]
    restarted = CoreService(
        data_root=core._storage.paths.root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        assert read(restarted, scope, result) == item
    finally:
        restarted.close()
    with core._storage.project_database(scope["project_id"]) as db:
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_analyses").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM presentation_claims").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_reviews").fetchone()[0] == 0


def test_changed_recording_preserves_historical_quotes_but_blocks_adoption(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    original = read(core, scope, result)["snapshot"]
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute(
            "UPDATE utterances SET text='Later edited transcription' WHERE session_id=?",
            (scope["session_id"],),
        )
        db.commit()
    item = read(core, scope, result)
    assert not item["context_current"] and not item["can_adopt"]
    assert item["snapshot"] == original


def test_absent_recording_preserves_history_without_omission_inference(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute("DELETE FROM utterances WHERE session_id=?", (scope["session_id"],))
        db.commit()
    item = read(core, scope, result)
    assert not item["context_current"] and item["snapshot"]["hint"] == result["hint"]


def test_native_reorder_retains_original_context(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    coverage = call(core, "presentation.workspace.rehearsal_coverage", scope)
    revision = call(
        core,
        "presentation.workspace.reorder_slides",
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "ordered_slide_ids": [item["slide_id"] for item in coverage["slides"]][::-1],
        },
    )["revision_id"]
    item = read(core, scope | {"expected_revision_id": revision}, result)
    assert item["current_slide_number"] == 3 and item["context_current"]
    assert item["snapshot"]["source_slide_number"] == 1
    assert item["snapshot"]["revision_id"] == scope["expected_revision_id"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("hint", {"status": "addressed", "reason": "fabricated", "quotes": []}),
        ("recording_completeness", "complete"),
        ("speaker_identity_verified", True),
        ("window_index", True),
        ("context_sha256", "x" * 64),
        ("point", {}),
        ("total_windows", 0),
        ("windows", []),
        ("requires_user_review", False),
    ],
)
def test_strict_snapshot_refuses_new_authority(rehearsal, field, value):
    core, scope = rehearsal
    result = saved(core, scope)
    snapshot = read(core, scope, result)["snapshot"]
    with pytest.raises(CoreDomainError) as error:
        validate_snapshot(snapshot | {field: value})
    assert error.value.code == "REHEARSAL_ANALYSIS_CORRUPT"


@pytest.mark.parametrize("rehash", [False, True])
def test_tampered_stored_window_cannot_be_read(rehearsal, rehash):
    core, scope = rehearsal
    result = saved(core, scope)
    with core._storage.project_database(scope["project_id"]) as db:
        raw = db.execute("SELECT snapshot_json FROM presentation_rehearsal_analyses").fetchone()[0]
        data = json.loads(raw)
        data["windows"][0]["utterances"][0]["text"] = "fabricated"
        data["windows"][0]["utterances"][0]["sha256"] = digest("fabricated")
        data["hint"]["quotes"][0]["quote"] = "fabricated"
        replacement = json.dumps(data)
        db.execute("UPDATE presentation_rehearsal_analyses SET snapshot_json=?", (replacement,))
        if rehash:
            db.execute(
                "UPDATE presentation_rehearsal_analyses SET snapshot_sha256=?",
                (digest(replacement),),
            )
        db.commit()
    with pytest.raises(CoreDomainError) as error:
        read(core, scope, result)
    assert error.value.code == "REHEARSAL_ANALYSIS_CORRUPT"


def test_failed_store_rolls_back_and_audit_remains_separate(rehearsal, monkeypatch):
    core, scope = rehearsal
    real_save = RehearsalAnalysisStore.save

    def fail(self, project, result, *, transaction_guard):
        def failed_guard(db):
            transaction_guard(db)
            db.execute(
                "INSERT INTO presentation_rehearsal_reviews VALUES (?,?,?,?,?,?,?,?)",
                (
                    "a" * 64,
                    result["session_id"],
                    result["document_id"],
                    result["source_revision_id"],
                    result["revision_id"],
                    None,
                    "rejected",
                    "now",
                ),
            )
            raise CoreDomainError("TEST_STORE_ABORT", "Injected transaction failure")

        return real_save(self, project, result, transaction_guard=failed_guard)

    monkeypatch.setattr(RehearsalAnalysisStore, "save", fail)
    with pytest.raises(CoreDomainError, match="Injected transaction failure"):
        saved(core, scope)
    with core._storage.project_database(scope["project_id"]) as db:
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_analyses").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_reviews").fetchone()[0] == 0
        assert db.execute("SELECT status FROM provider_runs").fetchone()[0] == "success"


def test_foreign_run_or_session_is_not_a_storable_hint(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    snapshot = read(core, scope, result)["snapshot"]
    store = RehearsalAnalysisStore(core._presentation_semantics)
    for field in ("provider_run_id", "session_id", "document_id"):
        with pytest.raises(CoreDomainError):
            store.save(
                scope["project_id"],
                snapshot | {field: str(uuid.uuid4())},
                transaction_guard=lambda _: None,
            )
    with core._storage.project_database(scope["project_id"]) as db:
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_analyses").fetchone()[0] == 1


def test_real_schema20_upgrade_preserves_run_native_and_app_metadata(rehearsal):
    core, scope = rehearsal
    chosen = selection(core, scope)
    call(
        core,
        "presentation.workspace.save_claim",
        {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "revision_id": scope["expected_revision_id"],
            "slide_number": 1,
            "slide_id": chosen["slide_id"],
            "object_id": chosen["object_id"],
            "quote": "First point",
            "evidence": [],
            "confirm": True,
        },
    )
    path = core._storage.project_paths(scope["project_id"]).database
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE presentation_rehearsal_objection_comparison_candidates")
        db.execute("DROP TABLE presentation_rehearsal_objection_comparisons")
        db.execute("DROP TABLE presentation_rehearsal_objection_findings")
        db.execute("DROP TABLE presentation_rehearsal_objection_analyses")
        db.execute("DROP TABLE presentation_rehearsal_analyses")
        db.execute("PRAGMA user_version=20")
        db.execute("UPDATE project SET schema_version=20")
        rows = {
            table: db.execute(f"SELECT * FROM {table}").fetchall()
            for table in (
                "sessions",
                "utterances",
                "presentation_revisions",
                "documents",
                "run_debriefs",
                "presentation_claims",
            )
        }
    app_before = core._storage.paths.app_database.read_bytes()
    upgraded = connect_project_database(path)
    try:
        assert upgraded.execute("PRAGMA user_version").fetchone()[0] == 23
        assert upgraded.execute("SELECT schema_version FROM project").fetchone()[0] == 23
        for table, expected in rows.items():
            assert [tuple(row) for row in upgraded.execute(f"SELECT * FROM {table}")] == expected
        assert not upgraded.execute("SELECT * FROM presentation_rehearsal_analyses").fetchall()
    finally:
        upgraded.close()
    assert core._storage.paths.app_database.read_bytes() == app_before


def test_schema21_collision_rolls_back_version_and_project_rows(rehearsal):
    core, scope = rehearsal
    path = core._storage.project_paths(scope["project_id"]).database
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=20")
        db.execute("UPDATE project SET schema_version=20")
    with pytest.raises(CoreDomainError) as error:
        connect_project_database(path)
    assert error.value.code == "DATABASE_MIGRATION_FAILED"
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 20
        assert db.execute("SELECT schema_version FROM project").fetchone()[0] == 20
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        # Restore only this disposable fixture so normal Core teardown can reopen it.
        db.execute("PRAGMA user_version=22")
        db.execute("UPDATE project SET schema_version=22")


@pytest.mark.parametrize(
    "change,code",
    [
        ("speech", "REHEARSAL_CONTEXT_CHANGED"),
        ("privacy", "PRIVACY_POLICY_CHANGED"),
        ("cancel", "PROVIDER_CANCELLED"),
    ],
)
def test_last_transaction_guard_refuses_late_changes(rehearsal, monkeypatch, change, code):
    core, scope = rehearsal
    real_save = RehearsalAnalysisStore.save
    cancelled = False

    def changed(self, project, result, *, transaction_guard):
        nonlocal cancelled
        if change == "cancel":
            cancelled = True
        else:
            with core._storage.project_database(project) as db:
                if change == "speech":
                    db.execute(
                        "UPDATE utterances SET text='last-moment edit' WHERE session_id=?",
                        (scope["session_id"],),
                    )
                else:
                    db.execute(
                        "UPDATE project SET privacy_mode='selected_context_cloud' WHERE id=?",
                        (scope["project_id"],),
                    )
                db.commit()
        return real_save(self, project, result, transaction_guard=transaction_guard)

    monkeypatch.setattr(RehearsalAnalysisStore, "save", changed)
    with pytest.raises(CoreDomainError) as error:
        analysis(core, CoverageProvider()).analyze(
            params(core, scope), cancellation_check=lambda: cancelled
        )
    assert error.value.code == code
    with core._storage.project_database(scope["project_id"]) as db:
        assert db.execute("SELECT COUNT(*) FROM presentation_rehearsal_analyses").fetchone()[0] == 0
        assert db.execute("SELECT status FROM provider_runs").fetchone()[0] == "success"


def test_native_text_edit_keeps_original_message_and_source_tamper_fails(rehearsal):
    core, scope = rehearsal
    result = saved(core, scope)
    point = result["point"]
    revision = call(
        core,
        "presentation.workspace.replace_text_shape",
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "slide_id": result["slide_id"],
            "object_id": point["object_id"],
            "expected_text": point["quote"],
            "replacement_text": "Updated after the recording",
            "operation_type": "replace_text_shape",
        },
    )["revision_id"]
    current = scope | {"expected_revision_id": revision}
    item = read(core, current, result)
    assert item["context_current"] and item["current_span_status"] == "changed"
    assert item["snapshot"]["point"]["quote"] == "First point"
    with core._storage.project_database(scope["project_id"]) as db:
        path = db.execute(
            "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
            (scope["expected_revision_id"],),
        ).fetchone()[0]
    original = core._storage.paths.snapshot_path(scope["project_id"], path, require_exists=True)
    original.write_bytes(original.read_bytes() + b"tamper")
    with pytest.raises(CoreDomainError) as error:
        read(core, current, result)
    assert error.value.code == "SOURCE_SNAPSHOT_CHANGED"
