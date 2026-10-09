"""Atomic multi-operation edits reuse the existing native package invariants."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pytest

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.edit_plans import PresentationEditPlanService
from presenter_core.presentation.transactions import PresentationTransactionService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def call(core: CoreService, method: str, params: dict[str, Any]) -> Any:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    assert response["ok"], response
    return response["result"]


def context(core: CoreService) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    project_id = call(core, "project.create", {"name": "Atomic edits"})["project"]["id"]
    document_id = call(
        core,
        "presentation.workspace.create_from_outline",
        {
            "project_id": project_id,
            "title": "Decision",
            "slides": [
                {
                    "title": "Our recommendation",
                    "bullets": ["Approve the pilot", "Review outcomes after thirty days"],
                    "notes": "Explain the rationale",
                },
                {
                    "title": "Evidence",
                    "bullets": ["Review the supporting evidence"],
                    "notes": "Unchanged notes",
                },
            ],
        },
    )["document"]["id"]
    source = core._presentation_edits._current_revision_source(project_id, document_id)
    inventory = call(
        core,
        "presentation.workspace.list_text_targets",
        {
            "project_id": project_id,
            "document_id": document_id,
            "revision_id": source["revision_id"],
            "slide_number": 1,
        },
    )
    target = next(
        item for item in inventory["targets"] if item["current_text"] == "Our recommendation"
    )
    scope = {
        "project_id": project_id,
        "document_id": document_id,
        "expected_revision_id": source["revision_id"],
    }
    operations = [
        {
            "type": "replace_text_shape",
            "params": {
                "operation_type": "replace_text_shape",
                "slide_id": inventory["slide_id"],
                "object_id": target["object_id"],
                "expected_text": target["current_text"],
                "replacement_text": "Decision requested",
            },
        },
        {
            "type": "replace_speaker_notes",
            "params": {
                "slide_id": inventory["slide_id"],
                "expected_text": inventory["speaker_notes"]["current_text"],
                "replacement_text": "Explain the rationale and review the detailed alternatives.",
            },
        },
    ]
    return scope, operations


def test_multiple_edits_stage_without_mutation_and_commit_one_revision(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, operations = context(core)
        editor = core._presentation_edits
        transactions = PresentationTransactionService(core._storage, editor)
        original = editor._current_revision_source(scope["project_id"], scope["document_id"])
        original_path = core._storage.paths.snapshot_path(
            scope["project_id"], original["local_snapshot_path"], require_exists=True
        )
        original_digest = hashlib.sha256(original_path.read_bytes()).hexdigest()
        with transactions.stage(**scope, operations=operations) as staged:
            assert staged.changed
            assert staged.path != original_path
            assert (
                editor._current_revision_source(scope["project_id"], scope["document_id"])[
                    "revision_id"
                ]
                == original["revision_id"]
            )
            with (
                zipfile.ZipFile(original_path) as baseline,
                zipfile.ZipFile(staged.path) as preview,
            ):
                assert set(baseline.namelist()) == set(preview.namelist())
                changed = [
                    name
                    for name in baseline.namelist()
                    if baseline.read(name) != preview.read(name)
                ]
                assert set(changed) == {"ppt/slides/slide1.xml", "ppt/notesSlides/notesSlide1.xml"}
        assert not staged.path.exists()
        result = transactions.apply(**scope, operations=operations)
        assert result["revision_number"] == 2
        assert result["parent_revision_id"] == original["revision_id"]
        assert len(result["operations"]) == 2
        assert all("revision_id" not in item for item in result["operations"])
        assert hashlib.sha256(original_path.read_bytes()).hexdigest() == original_digest
        with core._storage.project_database(scope["project_id"]) as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM presentation_revisions WHERE presentation_id = ?",
                    (scope["document_id"],),
                ).fetchone()[0]
                == 2
            )
        current = call(
            core,
            "presentation.workspace.list_text_targets",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "revision_id": result["revision_id"],
                "slide_number": 1,
            },
        )
        assert (
            current["speaker_notes"]["current_text"] == operations[1]["params"]["replacement_text"]
        )
        assert any(item["current_text"] == "Decision requested" for item in current["targets"])
        assert list(original_path.parent.glob(".edit-stage-*.pptx")) == []
    finally:
        core.close()


@pytest.mark.parametrize(
    "failure", ["stale_second_operation", "scope_override", "unsupported", "audit_commit"]
)
def test_failed_plan_preserves_head_and_cleans_private_stages(tmp_path: Path, failure: str) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, operations = context(core)
        editor = core._presentation_edits
        before = dict(editor._current_revision_source(scope["project_id"], scope["document_id"]))
        if failure == "stale_second_operation":
            operations[1]["params"]["expected_text"] = "Stale notes"
        elif failure == "scope_override":
            operations[1]["params"]["document_id"] = str(uuid.uuid4())
        elif failure == "unsupported":
            operations[1]["type"] = "restore_revision"

        def fail_audit(_connection: Any, _revision: str) -> None:
            raise CoreDomainError("AUDIT_FAILED", "Audit failure fixture")

        with pytest.raises(CoreDomainError):
            PresentationTransactionService(core._storage, editor).apply(
                **scope,
                operations=operations,
                on_commit=fail_audit if failure == "audit_commit" else None,
            )
        assert (
            dict(editor._current_revision_source(scope["project_id"], scope["document_id"]))
            == before
        )
        directory = core._storage.paths.safe_sources_directory(scope["project_id"])
        assert list(directory.glob(".edit-stage-*.pptx")) == []
        assert list(directory.glob(".revision-*.tmp")) == []
        assert list(directory.glob("revision-*.pptx")) == []
        with core._storage.project_database(scope["project_id"]) as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM presentation_revisions WHERE presentation_id = ?",
                    (scope["document_id"],),
                ).fetchone()[0]
                == 1
            )
    finally:
        core.close()


def test_review_preview_publishes_exact_bytes_and_content_free_audit(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, operations = context(core)
        plan = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {
                **scope,
                "summary": "Clarify the decision and its speaking notes",
                "operations": operations,
            },
        )
        plan_scope = {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "plan_id": plan["plan_id"],
        }
        reader = call(core, "presentation.workspace.open_edit_plan_preview", plan_scope)
        assert reader["is_edit_plan_preview"] is True
        assert reader["revision_kind"] == "edit_plan_preview"
        assert reader["revision_id"] == scope["expected_revision_id"]
        chunks: list[bytes] = []
        offset = 0
        while True:
            chunk = call(
                core,
                "presentation.workspace.read_source",
                {
                    "project_id": scope["project_id"],
                    "document_id": scope["document_id"],
                    "session_id": reader["session_id"],
                    "offset": offset,
                    "max_bytes": reader["chunk_bytes"],
                },
            )
            data = base64.b64decode(chunk["bytes_b64"])
            chunks.append(data)
            offset += len(data)
            if chunk["complete"]:
                break
        preview = b"".join(chunks)
        assert hashlib.sha256(preview).hexdigest() == plan["sha256"]
        assert (
            core._presentation_edits._current_revision_source(
                scope["project_id"], scope["document_id"]
            )["revision_id"]
            == scope["expected_revision_id"]
        )
        result = call(
            core,
            "presentation.workspace.apply_edit_plan",
            {
                **plan_scope,
                "confirm": True,
                "reviewed_sha256": plan["sha256"],
            },
        )
        assert result["revision_number"] == 2
        source = core._presentation_edits._current_revision_source(
            scope["project_id"], scope["document_id"]
        )
        path = core._storage.paths.snapshot_path(
            scope["project_id"], source["local_snapshot_path"], require_exists=True
        )
        assert path.read_bytes() == preview
        assert source["sha256"] == plan["sha256"]
        with core._storage.project_database(scope["project_id"]) as connection:
            row = connection.execute("SELECT * FROM presentation_edit_transactions").fetchone()
            assert row["revision_id"] == result["revision_id"]
            assert row["baseline_revision_id"] == scope["expected_revision_id"]
            metadata = json.loads(row["operation_metadata_json"])
            assert [item["type"] for item in metadata] == [item["type"] for item in operations]
            assert all(
                set(item) <= {"type", "changed", "slide_id", "object_id"} for item in metadata
            )
            assert "Decision requested" not in row["operation_metadata_json"]
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert list(path.parent.glob(".edit-plan-*.pptx")) == []
        assert core._presentation_edit_plans._plans == {}
        history = call(
            core,
            "presentation.workspace.list_revisions",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
            },
        )
        assert history["revisions"][0]["edit_transaction"]["operations"] == metadata
        assert "edit_transaction" not in history["revisions"][1]
        call(
            core,
            "source.delete",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
            },
        )
        assert not path.exists()
        with core._storage.project_database(scope["project_id"]) as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM presentation_edit_transactions"
                ).fetchone()[0]
                == 0
            )
    finally:
        core.close()


@pytest.mark.parametrize(
    "failure",
    ["no_preview", "wrong_digest", "unconfirmed", "stale", "tampered", "wrong_scope", "audit"],
)
def test_review_failures_never_publish(
    tmp_path: Path, failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, operations = context(core)
        service = core._presentation_edit_plans
        plan = service.prepare({**scope, "summary": "Reviewed plan", "operations": operations})
        plan_scope = {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "plan_id": plan["plan_id"],
        }
        if failure != "no_preview":
            service.open_preview(plan_scope)
        apply_params = {**plan_scope, "confirm": True, "reviewed_sha256": plan["sha256"]}
        if failure == "wrong_digest":
            apply_params["reviewed_sha256"] = "0" * 64
        elif failure == "unconfirmed":
            apply_params["confirm"] = False
        elif failure == "stale":
            core._presentation_edits.replace_speaker_notes({**scope, **operations[1]["params"]})
        elif failure == "tampered":
            # Close the Windows preview reader before changing its owned file.
            core._presentation_workspace_sources.close_source_readers(
                scope["project_id"], scope["document_id"]
            )
            service._plans[plan["plan_id"]].package.path.write_bytes(b"changed preview")
        elif failure == "wrong_scope":
            apply_params["document_id"] = str(uuid.uuid4())
        elif failure == "audit":
            # A missing audit table forces the final commit callback to fail.
            with core._storage.project_database(scope["project_id"]) as connection:
                connection.execute("DROP TABLE presentation_edit_transactions")
                connection.commit()
        before = dict(
            core._presentation_edits._current_revision_source(
                scope["project_id"], scope["document_id"]
            )
        )
        with pytest.raises(CoreDomainError):
            service.apply(apply_params)
        assert (
            dict(
                core._presentation_edits._current_revision_source(
                    scope["project_id"], scope["document_id"]
                )
            )
            == before
        )
        service.reject(plan_scope)
        directory = core._storage.paths.safe_sources_directory(scope["project_id"])
        assert list(directory.glob(".edit-plan-*.pptx")) == []
        assert list(directory.glob(".revision-*.tmp")) == []
        assert service._plans == {}
    finally:
        core.close()


@pytest.mark.parametrize(
    "cleanup", ["expire", "reject", "close", "source_delete", "project_delete"]
)
def test_review_lifetime_cleanup_releases_reader_and_private_package(
    tmp_path: Path, cleanup: str
) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, operations = context(core)
        now = [0.0]
        service = PresentationEditPlanService(
            core._storage,
            core._presentation_edits,
            core._presentation_workspace_sources,
            clock=lambda: now[0],
        )
        core._presentation_edit_plans = service
        plan = service.prepare({**scope, "summary": "Reviewed plan", "operations": operations})
        plan_scope = {
            "project_id": scope["project_id"],
            "document_id": scope["document_id"],
            "plan_id": plan["plan_id"],
        }
        reader = service.open_preview(plan_scope)
        package = service._plans[plan["plan_id"]].package.path
        if cleanup == "expire":
            now[0] = 901
            with pytest.raises(CoreDomainError, match="expired"):
                service.open_preview(plan_scope)
        elif cleanup == "reject":
            service.reject(plan_scope)
        elif cleanup == "close":
            service.close()
        elif cleanup == "source_delete":
            call(
                core,
                "source.delete",
                {"project_id": scope["project_id"], "document_id": scope["document_id"]},
            )
        else:
            call(core, "project.delete", {"project_id": scope["project_id"]})
        assert not package.exists()
        assert service._plans == {}
        assert reader["session_id"] not in core._presentation_workspace_sources._readers
    finally:
        core.close()


def test_abandoned_preview_reconciliation_preserves_live_and_registered_snapshots(
    tmp_path: Path,
) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, operations = context(core)
        service = core._presentation_edit_plans
        plan = service.prepare({**scope, "summary": "Reviewed plan", "operations": operations})
        live = service._plans[plan["plan_id"]].package.path
        directory = live.parent
        abandoned = directory / f".edit-plan-{uuid.uuid4()}.pptx"
        abandoned.write_bytes(b"abandoned package")
        stage = directory / f".edit-stage-{uuid.uuid4().hex}-1.pptx"
        stage.write_bytes(b"abandoned stage")
        unrelated = directory / ".edit-plan-user-deck.pptx"
        unrelated.write_bytes(b"user data")
        registered = directory / f".edit-plan-{uuid.uuid4()}.pptx"
        source = core._presentation_edits._current_revision_source(
            scope["project_id"], scope["document_id"]
        )
        original = core._storage.paths.snapshot_path(
            scope["project_id"], source["local_snapshot_path"], require_exists=True
        )
        registered.write_bytes(original.read_bytes())
        with core._storage.project_database(scope["project_id"]) as connection:
            connection.execute(
                "UPDATE documents SET local_snapshot_path = ? WHERE id = ?",
                (f"sources/{registered.name}", scope["document_id"]),
            )
            connection.commit()
        service.reconcile_project(scope["project_id"])
        assert not abandoned.exists()
        assert not stage.exists()
        assert live.exists()
        assert unrelated.read_bytes() == b"user data"
        assert registered.exists()
        assert original.exists()
    finally:
        core.close()


def test_reviewed_multi_object_geometry_is_atomic_and_undoable(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, _ = context(core)
        inventory = call(
            core,
            "presentation.workspace.list_text_targets",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "revision_id": scope["expected_revision_id"],
                "slide_number": 1,
            },
        )
        objects = [obj for obj in inventory["objects"] if obj["geometry_editable"]]
        assert len(objects) >= 2
        objects = objects[:2]
        operations = [
            {
                "type": "transform_object",
                "params": {
                    "slide_id": inventory["slide_id"],
                    "object_id": obj["object_id"],
                    "expected_geometry": obj["geometry"],
                    "replacement_geometry": {
                        **obj["geometry"],
                        "x_emu": obj["geometry"]["x_emu"] + 10000,
                    },
                },
            }
            for obj in objects
        ]
        invalid = json.loads(json.dumps(operations))
        invalid[1]["params"]["expected_geometry"]["y_emu"] += 1
        with pytest.raises(CoreDomainError):
            core._presentation_edit_plans.prepare(
                {**scope, "summary": "Move both objects", "operations": invalid}
            )
        assert (
            core._presentation_edits._current_revision_source(
                scope["project_id"], scope["document_id"]
            )["revision_id"]
            == scope["expected_revision_id"]
        )
        plan = call(
            core,
            "presentation.workspace.prepare_edit_plan",
            {**scope, "summary": "Move both objects", "operations": operations},
        )
        assert (
            core._presentation_edits._current_revision_source(
                scope["project_id"], scope["document_id"]
            )["revision_id"]
            == scope["expected_revision_id"]
        )
        reader = call(
            core,
            "presentation.workspace.open_edit_plan_preview",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "plan_id": plan["plan_id"],
            },
        )
        offset = 0
        preview = bytearray()
        while True:
            chunk = call(
                core,
                "presentation.workspace.read_source",
                {
                    "project_id": scope["project_id"],
                    "document_id": scope["document_id"],
                    "session_id": reader["session_id"],
                    "offset": offset,
                    "max_bytes": reader["chunk_bytes"],
                },
            )
            data = base64.b64decode(chunk["bytes_b64"])
            preview.extend(data)
            offset += len(data)
            if chunk["complete"]:
                break
        assert hashlib.sha256(preview).hexdigest() == plan["sha256"]
        result = call(
            core,
            "presentation.workspace.apply_edit_plan",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "plan_id": plan["plan_id"],
                "reviewed_sha256": plan["sha256"],
                "confirm": True,
            },
        )
        assert result["revision_number"] == 2
        assert result["sha256"] == plan["sha256"]
        updated = call(
            core,
            "presentation.workspace.list_text_targets",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "revision_id": result["revision_id"],
                "slide_number": 1,
            },
        )
        assert [o["object_id"] for o in updated["objects"]] == [
            o["object_id"] for o in inventory["objects"]
        ]
        by_id = {o["object_id"]: o for o in updated["objects"]}
        for operation in operations:
            assert (
                by_id[operation["params"]["object_id"]]["geometry"]
                == operation["params"]["replacement_geometry"]
            )
        restored = call(
            core,
            "presentation.workspace.step_revision",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "expected_revision_id": result["revision_id"],
                "direction": "undo",
            },
        )
        assert restored["revision_id"] == scope["expected_revision_id"]
    finally:
        core.close()
