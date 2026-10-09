from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from test_presentation_edit_planning import call, context
from test_presentation_native_layouts import path

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter
from presenter_core.storage.database import connect_project_database


def core_at(root):
    return CoreService(data_root=root, embedding_adapter=DeterministicEmbeddingAdapter(dimension=2))


def scope(params):
    return {k: params[k] for k in ("project_id", "document_id")}


def saved(
    core, params, token=None, name="Ready for rehearsal", note="Keep exact notes\n  second line"
):
    return call(
        core,
        "presentation.workspace.save_checkpoint",
        {
            **scope(params),
            "expected_revision_id": params["expected_revision_id"],
            "expected_token": token,
            "name": name,
            "note": note,
        },
    )


def test_checkpoints_restart_without_package_head_provider_or_revision_changes(tmp_path: Path):
    root = tmp_path / "data"
    core = core_at(root)
    try:
        params = context(core)
        baseline = path(core, params).read_bytes()
        before = call(core, "presentation.workspace.list_revisions", scope(params))
        result = saved(core, params)
        assert result["items"][0]["name"] == "Ready for rehearsal"
        assert result["items"][0]["note"] == "Keep exact notes\n  second line"
        assert result["items"][0]["sha256"] == before["revisions"][0]["sha256"]
        assert call(core, "presentation.workspace.list_revisions", scope(params)) == before
        assert path(core, params).read_bytes() == baseline
        with core._storage.project_database(params["project_id"]) as db:
            assert db.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 0
    finally:
        core.close()
    core = core_at(root)
    try:
        assert call(core, "presentation.workspace.list_checkpoints", scope(params)) == result
        assert path(core, params).read_bytes() == baseline
        call(core, "source.delete", scope(params))
        with core._storage.project_database(params["project_id"]) as db:
            assert (
                db.execute("SELECT COUNT(*) FROM presentation_revision_checkpoints").fetchone()[0]
                == 0
            )
    finally:
        core.close()


def test_checkpoint_rename_clear_and_aba_tokens(tmp_path: Path):
    core = core_at(tmp_path / "data")
    try:
        params = context(core)
        first = saved(core, params)
        token = first["current_record_token"]
        second = saved(core, params, token, "Approved wording")
        call(
            core,
            "presentation.workspace.save_checkpoint",
            {
                **scope(params),
                "expected_revision_id": params["expected_revision_id"],
                "expected_token": token,
                "name": "Stale label",
                "note": "",
            },
            ok=False,
        )
        removed = call(
            core,
            "presentation.workspace.clear_checkpoint",
            {
                **scope(params),
                "revision_id": params["expected_revision_id"],
                "expected_token": second["current_record_token"],
            },
        )
        assert not removed["items"]
        assert removed["current_record_token"] not in (None, token, second["current_record_token"])
        call(
            core,
            "presentation.workspace.save_checkpoint",
            {
                **scope(params),
                "expected_revision_id": params["expected_revision_id"],
                "expected_token": None,
                "name": "Stale empty writer",
                "note": "",
            },
            ok=False,
        )
        assert saved(core, params, removed["current_record_token"])["items"]
        foreign = context(core)
        error = call(
            core,
            "presentation.workspace.clear_checkpoint",
            {
                **scope(foreign),
                "revision_id": params["expected_revision_id"],
                "expected_token": token,
            },
            ok=False,
        )
        assert error["code"] == "PRESENTATION_CHECKPOINT_CONFLICT"
    finally:
        core.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "a" * 81),
        ("name", "Two\nlines"),
        ("note", "a" * 501),
        ("expected_token", "bad"),
        ("expected_revision_id", "bad"),
        ("extra", True),
    ],
)
def test_checkpoint_validation_does_not_change_records(tmp_path: Path, field, value):
    core = core_at(tmp_path / "data")
    try:
        params = context(core)
        request = {
            **scope(params),
            "expected_revision_id": params["expected_revision_id"],
            "expected_token": None,
            "name": "Checkpoint",
            "note": "",
        }
        request[field] = value
        call(core, "presentation.workspace.save_checkpoint", request, ok=False)
        assert not call(core, "presentation.workspace.list_checkpoints", scope(params))["items"]
    finally:
        core.close()


def test_v18_checkpoint_migration_preserves_existing_rows(tmp_path: Path):
    target = tmp_path / "migration.db"
    latest = connect_project_database(target)
    latest.execute("CREATE TABLE sentinel(value TEXT)")
    latest.execute("INSERT INTO sentinel VALUES ('preserved')")
    latest.commit()
    latest.close()
    with sqlite3.connect(target) as old:
        old.execute("DROP TABLE presentation_rehearsal_objection_comparison_candidates")
        old.execute("DROP TABLE presentation_rehearsal_objection_comparisons")
        old.execute("DROP TABLE presentation_rehearsal_objection_findings")
        old.execute("DROP TABLE presentation_rehearsal_objection_analyses")
        old.execute("DROP TABLE presentation_rehearsal_analyses")
        old.execute("DROP TABLE presentation_revision_checkpoints")
        old.execute("PRAGMA user_version = 18")
    migrated = connect_project_database(target)
    try:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 23
        assert migrated.execute("SELECT value FROM sentinel").fetchone()[0] == "preserved"
        assert (
            migrated.execute("SELECT COUNT(*) FROM presentation_revision_checkpoints").fetchone()[0]
            == 0
        )
    finally:
        migrated.close()


def test_checkpoint_write_rejects_a_changed_presentation_head(tmp_path: Path):
    core = core_at(tmp_path / "data")
    try:
        params = context(core)
        original = saved(core, params)
        fidelity = core._presentation_edit_planning._read(
            core._presentation_edits,
            params["project_id"],
            params["document_id"],
            params["expected_revision_id"],
        )
        edited = call(
            core,
            "presentation.workspace.replace_speaker_notes",
            {
                **scope(params),
                "expected_revision_id": params["expected_revision_id"],
                "slide_id": fidelity.slides[0].slide_id,
                "expected_text": fidelity.slides[0].speaker_notes,
                "replacement_text": "Revised rehearsal notes",
            },
        )
        error = call(
            core,
            "presentation.workspace.save_checkpoint",
            {
                **scope(params),
                "expected_revision_id": params["expected_revision_id"],
                "expected_token": original["current_record_token"],
                "name": "Stale head",
                "note": "",
            },
            ok=False,
        )
        assert error["code"] == "PRESENTATION_REVISION_CONFLICT"
        catalog = call(core, "presentation.workspace.list_checkpoints", scope(params))
        assert catalog["current_revision_id"] == edited["revision_id"]
        assert catalog["current_record_token"] is None
        assert catalog["items"] == original["items"]
    finally:
        core.close()


def test_checkpoint_active_limit_does_not_block_renaming_or_removal(tmp_path: Path):
    core = core_at(tmp_path / "data")
    try:
        params = context(core)
        with core._storage.project_database(params["project_id"]) as db:
            original = dict(
                db.execute(
                    "SELECT * FROM presentation_revisions WHERE id = ?",
                    (params["expected_revision_id"],),
                ).fetchone()
            )
            for index in range(100):
                identity = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO presentation_revisions "
                    "(id,presentation_id,parent_revision_id,revision_number,revision_kind,"
                    "local_snapshot_path,sha256,byte_size,created_at) "
                    "VALUES (?,?,NULL,?,'edited',?,?,?,?)",
                    (
                        identity,
                        params["document_id"],
                        index + 2,
                        original["local_snapshot_path"],
                        original["sha256"],
                        original["byte_size"],
                        original["created_at"],
                    ),
                )
                db.execute(
                    "INSERT INTO presentation_revision_checkpoints VALUES (?,?,?,?,?,?)",
                    (
                        identity,
                        params["document_id"],
                        str(uuid.uuid4()),
                        f"Checkpoint {index}",
                        "",
                        original["created_at"],
                    ),
                )
            db.commit()
        error = call(
            core,
            "presentation.workspace.save_checkpoint",
            {
                **scope(params),
                "expected_revision_id": params["expected_revision_id"],
                "expected_token": None,
                "name": "Beyond limit",
                "note": "",
            },
            ok=False,
        )
        assert error["code"] == "INVALID_REQUEST"
        catalog = call(core, "presentation.workspace.list_checkpoints", scope(params))
        assert len(catalog["items"]) == 100
        item = catalog["items"][0]
        call(
            core,
            "presentation.workspace.clear_checkpoint",
            {
                **scope(params),
                "revision_id": item["revision_id"],
                "expected_token": item["record_token"],
            },
        )
        assert len(saved(core, params)["items"]) == 100
        token = call(core, "presentation.workspace.list_checkpoints", scope(params))[
            "current_record_token"
        ]
        assert len(saved(core, params, token, "Renamed at limit")["items"]) == 100
    finally:
        core.close()
