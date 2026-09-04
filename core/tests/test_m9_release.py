"""Milestone 9 release-hardening regressions."""

from __future__ import annotations

import json
import sqlite3
import stat
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pytest

from presenter_core.credentials import InMemoryCredentialStore
from presenter_core.errors import CoreDomainError
from presenter_core.ingestion import security as ingestion_security
from presenter_core.ingestion.security import preflight_pptx_archive
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter
from presenter_core.storage.database import connect_project_database


def _request(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is True, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def _error(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is False, response
    error = response["error"]
    assert isinstance(error, dict)
    return error


def _project(core: CoreService, name: str) -> str:
    result = _request(core, "project.create", {"name": name})
    return str(result["project"]["id"])


def _all_bytes(root: Path) -> bytes:
    chunks: list[bytes] = []
    if not root.exists():
        return b""
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            chunks.append(path.read_bytes())
    return b"\n".join(chunks)


def test_credentials_logs_and_diagnostics_never_contain_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = "sk-m9-secret-sentinel-7f3c"
    monkeypatch.setenv("OPENAI_API_KEY", sentinel)
    store = InMemoryCredentialStore()
    data_root = tmp_path / "data"
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=store,
    )
    try:
        _request(core, "provider.configure", {"enabled": True, "model_id": "m9-test"})
        saved = _request(core, "provider.credentials.save_detected", {})
        assert saved == {
            "provider_id": "openai",
            "saved": True,
            "detected": True,
            "credential_source": "test_credential_store",
        }
        status = _request(core, "provider.credentials.status", {})
        assert status["configured"] is True
        assert sentinel not in json.dumps(status)

        # These calls exercise both the central logger allowlist and the
        # diagnostics projection against values that must never be serialized.
        core._logger.event("m9-sentinel-secret", {"status": sentinel})  # type: ignore[attr-defined]
        core._logger.event(
            "m9-safe-event",
            {"operation": "diagnostic_test", "error_code": "M9_SECRET_REDACTION"},
        )
        preview = _request(core, "diagnostics.preview", {})
        assert sentinel not in json.dumps(preview)

        output = tmp_path / "diagnostics" / "m9.zip"
        exported = _request(
            core,
            "diagnostics.export",
            {"output_path": str(output), "sections": ["core", "provider", "logs"]},
        )
        assert exported["exported"] is True
        with zipfile.ZipFile(output) as archive:
            archive_bytes = b"".join(archive.read(name) for name in archive.namelist())
        assert sentinel.encode() not in archive_bytes
        assert sentinel.encode() not in _all_bytes(data_root)
        with core._storage.app_database() as connection:  # type: ignore[attr-defined]
            database_dump = "\n".join(connection.iterdump())
        assert sentinel not in database_dump

        removed = _request(core, "provider.credentials.remove", {})
        assert removed["removed"] is True
        assert store.read() is None
    finally:
        core.close()


def test_project_delete_purges_warm_retrieval_state_and_retains_shared_models(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    adapter = DeterministicEmbeddingAdapter(dimension=2)
    core = CoreService(data_root=data_root, embedding_adapter=adapter)
    source_a = tmp_path / "a.md"
    source_b = tmp_path / "b.md"
    source_a.write_text("Project A private deletion sentinel.", encoding="utf-8")
    source_b.write_text("Project B must survive deletion.", encoding="utf-8")
    try:
        project_a = _project(core, "M9 project A")
        project_b = _project(core, "M9 project B")
        imported_a = _request(
            core,
            "source.import",
            {"project_id": project_a, "path": str(source_a), "kind": "supporting"},
        )
        imported_b = _request(
            core,
            "source.import",
            {"project_id": project_b, "path": str(source_b), "kind": "supporting"},
        )
        document_a = str(imported_a["document"]["id"])
        document_b = str(imported_b["document"]["id"])
        _request(core, "retrieval.rebuild", {"project_id": project_a})
        _request(core, "retrieval.rebuild", {"project_id": project_b})
        _request(core, "retrieval.query", {"project_id": project_a, "query": "private deletion"})
        _request(core, "retrieval.query", {"project_id": project_b, "query": "survive deletion"})

        matrix_cache = core._hybrid_retrieval._matrix_cache  # type: ignore[attr-defined]
        mapping_cache = core._hybrid_retrieval._mapping_count_cache  # type: ignore[attr-defined]
        assert project_a in matrix_cache
        assert project_b in matrix_cache
        assert any(key[0] == project_a for key in mapping_cache)
        model_marker = data_root / "models" / "embeddings" / "shared-model.marker"
        model_marker.parent.mkdir(parents=True)
        model_marker.write_text("shared", encoding="utf-8")
        project_a_root = data_root / "projects" / project_a

        deleted = _request(core, "project.delete", {"project_id": project_a})
        assert deleted == {"project_id": project_a, "deleted": True}
        assert not project_a_root.exists()
        assert project_a not in matrix_cache
        assert all(key[0] != project_a for key in mapping_cache)
        with pytest.raises(CoreDomainError) as stale_db:
            with core._storage.project_database(project_a):  # type: ignore[attr-defined]
                pass
        assert stale_db.value.code == "PROJECT_NOT_FOUND"
        assert _error(core, "project.open", {"project_id": project_a})["code"] == (
            "PROJECT_NOT_FOUND"
        )
        assert (
            _error(core, "retrieval.query", {"project_id": project_a, "query": "private deletion"})[
                "code"
            ]
            == "PROJECT_NOT_FOUND"
        )

        surviving = _request(
            core, "retrieval.query", {"project_id": project_b, "query": "survive deletion"}
        )
        assert surviving["project_id"] == project_b
        assert document_b
        assert not document_a == document_b
        assert model_marker.read_text(encoding="utf-8") == "shared"
    finally:
        core.close()


def test_reset_local_data_requires_confirmation_and_has_explicit_model_retention(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    store = InMemoryCredentialStore("m9-reset-secret")
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=store,
    )
    try:
        project_id = _project(core, "M9 reset project")
        _request(core, "speaker_profile.get", {})
        _request(core, "speaker_profile.update_settings", {"display_name": "M9"})
        _request(core, "provider.configure", {"enabled": True})
        core._storage.set_app_metadata("m9", {"value": "user state"})  # type: ignore[attr-defined]
        core._logger.event("m9-reset-event", {"operation": "reset_test"})  # type: ignore[attr-defined]
        diagnostic_file = data_root / "diagnostics" / "before-reset.json"
        diagnostic_file.parent.mkdir(parents=True)
        diagnostic_file.write_text("metadata", encoding="utf-8")
        retained_model = data_root / "models" / "asr" / "retained.marker"
        retained_model.parent.mkdir(parents=True, exist_ok=True)
        retained_model.write_text("retain", encoding="utf-8")
        orphan_project = str(uuid.uuid4())
        orphan_marker = data_root / "projects" / orphan_project / "orphan.marker"
        orphan_marker.parent.mkdir(parents=True)
        orphan_marker.write_text("orphaned app-owned state", encoding="utf-8")

        assert _error(core, "app.reset_local_data", {})["code"] == (
            "LOCAL_DATA_RESET_CONFIRMATION_REQUIRED"
        )
        reset = _request(core, "app.reset_local_data", {"confirm": True})
        assert reset["model_cache_retained"] is True
        assert reset["credentials_removed"] is True
        assert reset["project_directories_removed"] == 2
        assert not (data_root / "projects" / project_id).exists()
        assert not orphan_marker.exists()
        assert not diagnostic_file.exists()
        assert retained_model.read_text(encoding="utf-8") == "retain"
        assert store.read() is None
        with core._storage.app_database() as connection:  # type: ignore[attr-defined]
            for table in (
                "projects",
                "speaker_profiles",
                "provider_configurations",
                "app_metadata",
            ):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

        removable_model = data_root / "models" / "embeddings" / "remove.marker"
        removable_model.parent.mkdir(parents=True)
        removable_model.write_text("remove", encoding="utf-8")
        second_reset = _request(
            core,
            "app.reset_local_data",
            {"confirm": True, "remove_model_cache": True},
        )
        assert second_reset["model_cache_retained"] is False
        assert not (data_root / "models" / "asr").exists()
        assert not (data_root / "models" / "embeddings").exists()
    finally:
        core.close()


def test_reset_local_data_fails_closed_on_unknown_project_entry(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=InMemoryCredentialStore(),
    )
    try:
        project_id = _project(core, "M9 unsafe reset project")
        unknown_entry = data_root / "projects" / "not-a-project"
        unknown_entry.mkdir()
        error = _error(core, "app.reset_local_data", {"confirm": True})
        assert error["code"] == "PROJECT_PATH_UNSAFE"
        assert (data_root / "projects" / project_id).is_dir()
        assert unknown_entry.is_dir()
    finally:
        core.close()


def test_project_delete_stage_and_registry_failures_restore_the_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        project_id = _project(core, "M9 injected project failure")
        project_root = tmp_path / "data" / "projects" / project_id
        marker = project_root / "preserve.txt"
        marker.write_text("preserve", encoding="utf-8")
        storage = core._storage  # type: ignore[attr-defined]

        def fail_stage(_operation: Any, _project_id: str) -> bool:
            raise CoreDomainError(
                "PROJECT_DELETE_STAGE_FAILED",
                "injected stage failure",
                retryable=True,
            )

        original_stage = storage._tombstones.stage_project
        monkeypatch.setattr(storage._tombstones, "stage_project", fail_stage)
        stage_error = _error(core, "project.delete", {"project_id": project_id})
        assert stage_error["code"] == "PROJECT_DELETE_STAGE_FAILED"
        assert marker.read_text(encoding="utf-8") == "preserve"
        assert storage.app_row(project_id)["id"] == project_id
        monkeypatch.setattr(storage._tombstones, "stage_project", original_stage)

        def fail_registry_marker(_connection: Any, _operation_id: str) -> None:
            raise sqlite3.OperationalError("injected registry failure")

        original_journal = storage._append_deletion_journal_id
        monkeypatch.setattr(storage, "_append_deletion_journal_id", fail_registry_marker)
        registry_error = _error(core, "project.delete", {"project_id": project_id})
        assert registry_error["code"] == "PROJECT_DELETE_FAILED"
        assert registry_error["retryable"] is True
        assert marker.read_text(encoding="utf-8") == "preserve"
        assert storage.app_row(project_id)["id"] == project_id
        monkeypatch.setattr(storage, "_append_deletion_journal_id", original_journal)

        deleted = _request(core, "project.delete", {"project_id": project_id})
        assert deleted == {"project_id": project_id, "deleted": True}
        assert not project_root.exists()
        assert not list((tmp_path / "data" / "tombstones").iterdir())
    finally:
        core.close()


def test_reset_stage_and_app_transaction_failures_leave_all_data_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    store = InMemoryCredentialStore("m9-reset-injected-secret")
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=store,
    )
    try:
        project_a = _project(core, "M9 reset failure A")
        project_b = _project(core, "M9 reset failure B")
        storage = core._storage  # type: ignore[attr-defined]
        storage.set_app_metadata("m9-reset-state", {"preserve": True})
        original_stage = storage._tombstones.stage_project
        stage_calls = 0

        def fail_second_stage(operation: Any, project_id: str) -> bool:
            nonlocal stage_calls
            stage_calls += 1
            if stage_calls == 2:
                raise CoreDomainError(
                    "LOCAL_DATA_RESET_FAILED",
                    "injected reset stage failure",
                    retryable=True,
                )
            return original_stage(operation, project_id)

        monkeypatch.setattr(storage._tombstones, "stage_project", fail_second_stage)
        stage_error = _error(core, "app.reset_local_data", {"confirm": True})
        assert stage_error["code"] == "LOCAL_DATA_RESET_FAILED"
        assert (data_root / "projects" / project_a).is_dir()
        assert (data_root / "projects" / project_b).is_dir()
        assert {str(row["id"]) for row in storage.list_app_rows()} == {project_a, project_b}
        monkeypatch.setattr(storage._tombstones, "stage_project", original_stage)

        def fail_reset_registry_marker(_connection: Any, _operation_id: str) -> None:
            raise sqlite3.OperationalError("injected reset transaction failure")

        original_journal = storage._append_deletion_journal_id
        monkeypatch.setattr(storage, "_append_deletion_journal_id", fail_reset_registry_marker)
        transaction_error = _error(core, "app.reset_local_data", {"confirm": True})
        assert transaction_error["code"] == "LOCAL_DATA_RESET_FAILED"
        assert (data_root / "projects" / project_a).is_dir()
        assert (data_root / "projects" / project_b).is_dir()
        assert {str(row["id"]) for row in storage.list_app_rows()} == {project_a, project_b}
        assert storage.get_app_metadata("m9-reset-state") == {"preserve": True}
        assert store.read() == "m9-reset-injected-secret"
        monkeypatch.setattr(storage, "_append_deletion_journal_id", original_journal)

        reset = _request(core, "app.reset_local_data", {"confirm": True})
        assert reset["reset"] is True
        assert reset["credentials_removed"] is True
        assert not (data_root / "projects" / project_a).exists()
        assert not (data_root / "projects" / project_b).exists()
    finally:
        core.close()


def test_committed_project_cleanup_failure_is_non_retrievable_and_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    source = tmp_path / "warm-cache.md"
    source.write_text("warm cache deletion sentinel", encoding="utf-8")
    try:
        project_id = _project(core, "M9 cleanup retry")
        imported = _request(
            core,
            "source.import",
            {"project_id": project_id, "path": str(source), "kind": "supporting"},
        )
        _request(core, "retrieval.rebuild", {"project_id": project_id})
        _request(core, "retrieval.query", {"project_id": project_id, "query": "warm cache"})
        matrix_cache = core._hybrid_retrieval._matrix_cache  # type: ignore[attr-defined]
        mapping_cache = core._hybrid_retrieval._mapping_count_cache  # type: ignore[attr-defined]
        assert project_id in matrix_cache
        assert any(key[0] == project_id for key in mapping_cache)

        storage = core._storage  # type: ignore[attr-defined]
        original_cleanup = storage._tombstones.cleanup_vaults
        failed = False

        def fail_once(operation: Any) -> None:
            nonlocal failed
            if not failed:
                failed = True
                raise CoreDomainError(
                    "DELETION_CLEANUP_FAILED",
                    "injected postcommit cleanup failure",
                    retryable=True,
                )
            original_cleanup(operation)

        monkeypatch.setattr(storage._tombstones, "cleanup_vaults", fail_once)
        first_error = _error(core, "project.delete", {"project_id": project_id})
        assert first_error["code"] == "PROJECT_DELETE_CLEANUP_PENDING"
        assert first_error["retryable"] is True
        assert not (data_root / "projects" / project_id).exists()
        assert project_id not in matrix_cache
        assert all(key[0] != project_id for key in mapping_cache)
        with pytest.raises(CoreDomainError) as missing:
            storage.app_row(project_id)
        assert missing.value.code == "PROJECT_NOT_FOUND"
        assert list((data_root / "tombstones").iterdir())
        with storage.app_database() as connection:
            journal = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?",
                ("__presenter_copilot_deletion_journal_v1",),
            ).fetchone()
        assert journal is not None
        assert imported["document"]["project_id"] == project_id

        monkeypatch.setattr(storage._tombstones, "cleanup_vaults", original_cleanup)
        retry = _request(core, "project.delete", {"project_id": project_id})
        assert retry == {"project_id": project_id, "deleted": True}
        assert not list((data_root / "tombstones").iterdir())
        assert (
            _error(core, "retrieval.query", {"project_id": project_id, "query": "warm cache"})[
                "code"
            ]
            == "PROJECT_NOT_FOUND"
        )
    finally:
        core.close()


def test_committed_project_cleanup_is_retried_during_next_core_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        project_id = _project(core, "M9 startup cleanup retry")
        storage = core._storage  # type: ignore[attr-defined]

        def fail_cleanup(_operation: Any) -> None:
            raise CoreDomainError(
                "DELETION_CLEANUP_FAILED",
                "injected startup cleanup failure",
                retryable=True,
            )

        original_cleanup = storage._tombstones.cleanup_vaults
        monkeypatch.setattr(storage._tombstones, "cleanup_vaults", fail_cleanup)
        error = _error(core, "project.delete", {"project_id": project_id})
        assert error["code"] == "PROJECT_DELETE_CLEANUP_PENDING"
        assert list((data_root / "tombstones").iterdir())
        monkeypatch.setattr(storage._tombstones, "cleanup_vaults", original_cleanup)
        core.close()

        restarted = CoreService(
            data_root=data_root,
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        )
        try:
            assert not list((data_root / "tombstones").iterdir())
            assert (
                _error(
                    restarted,
                    "retrieval.query",
                    {"project_id": project_id, "query": "deleted"},
                )["code"]
                == "PROJECT_NOT_FOUND"
            )
            assert _request(restarted, "project.delete", {"project_id": project_id}) == {
                "project_id": project_id,
                "deleted": False,
            }
        finally:
            restarted.close()
    finally:
        core.close()


def test_committed_reset_cleanup_failure_keeps_journal_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    store = InMemoryCredentialStore("m9-reset-cleanup-secret")
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=store,
    )
    try:
        project_id = _project(core, "M9 reset cleanup retry")
        storage = core._storage  # type: ignore[attr-defined]
        original_cleanup = storage._tombstones.cleanup_vaults
        failed = False

        def fail_once(operation: Any) -> None:
            nonlocal failed
            if not failed:
                failed = True
                raise CoreDomainError(
                    "DELETION_CLEANUP_FAILED",
                    "injected reset cleanup failure",
                    retryable=True,
                )
            original_cleanup(operation)

        monkeypatch.setattr(storage._tombstones, "cleanup_vaults", fail_once)
        error = _error(core, "app.reset_local_data", {"confirm": True})
        assert error["code"] == "LOCAL_DATA_RESET_CLEANUP_PENDING"
        assert store.read() is None
        assert not (data_root / "projects" / project_id).exists()
        assert list((data_root / "tombstones").iterdir())
        with storage.app_database() as connection:
            assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
            assert connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?",
                ("__presenter_copilot_deletion_journal_v1",),
            ).fetchone()

        monkeypatch.setattr(storage._tombstones, "cleanup_vaults", original_cleanup)
        retry = _request(core, "app.reset_local_data", {"confirm": True})
        assert retry["reset"] is True
        assert retry["stored_credential_present"] is False
        assert not list((data_root / "tombstones").iterdir())
    finally:
        core.close()


def test_reset_fails_closed_without_changing_data_when_secure_store_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class UnavailableStore:
        source = "test_unavailable_store"

        def __init__(self) -> None:
            self.value = "m9-unavailable-secret"
            self.delete_called = False

        def is_available(self) -> bool:
            return False

        def read(self) -> str | None:
            return self.value

        def write(self, value: str) -> None:
            self.value = value

        def delete(self) -> bool:
            self.delete_called = True
            self.value = None
            return True

    monkeypatch.setenv("OPENAI_API_KEY", "m9-environment-secret")
    data_root = tmp_path / "data"
    store = UnavailableStore()
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=store,
    )
    try:
        project_id = _project(core, "M9 unavailable credential reset")
        core._storage.set_app_metadata("m9", {"value": "preserve"})  # type: ignore[attr-defined]
        before = _all_bytes(data_root)
        error = _error(core, "app.reset_local_data", {"confirm": True})
        assert error["code"] == "CREDENTIAL_STORE_UNAVAILABLE"
        assert not store.delete_called
        assert store.value == "m9-unavailable-secret"
        assert _all_bytes(data_root) == before
        assert (data_root / "projects" / project_id).is_dir()
        assert core._storage.app_row(project_id)["id"] == project_id  # type: ignore[attr-defined]
    finally:
        core.close()


def test_reset_fails_closed_when_secure_store_read_fails(tmp_path: Path) -> None:
    class ReadFailureStore:
        source = "test_read_failure_store"

        def __init__(self) -> None:
            self.delete_called = False

        def is_available(self) -> bool:
            return True

        def read(self) -> str | None:
            raise RuntimeError("injected secure-store read failure")

        def write(self, value: str) -> None:
            del value

        def delete(self) -> bool:
            self.delete_called = True
            return False

    data_root = tmp_path / "data"
    store = ReadFailureStore()
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=store,
    )
    try:
        project_id = _project(core, "M9 credential read failure")
        before = _all_bytes(data_root)
        error = _error(core, "app.reset_local_data", {"confirm": True})
        assert error["code"] == "CREDENTIAL_STORE_UNAVAILABLE"
        assert not store.delete_called
        assert _all_bytes(data_root) == before
        assert (data_root / "projects" / project_id).is_dir()
    finally:
        core.close()


def test_reset_reports_no_stored_credential_and_retains_environment_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "m9-environment-only-secret")
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=InMemoryCredentialStore(),
    )
    try:
        reset = _request(core, "app.reset_local_data", {"confirm": True})
        assert reset["credentials_removed"] is False
        assert reset["stored_credential_present"] is False
        assert reset["credential_cleanup_established"] is True
        assert reset["environment_credential_detected"] is True
        assert reset["environment_credential_retained"] is True
        assert "m9-environment-only-secret" not in json.dumps(reset)
    finally:
        core.close()


def test_diagnostic_preview_and_export_have_exact_selected_sections(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        credential_store=InMemoryCredentialStore(),
    )
    try:
        core._logger.event("m9-diagnostic-parity", {"operation": "parity"})  # type: ignore[attr-defined]
        selected = ["core", "logs"]
        preview = _request(core, "diagnostics.preview", {"sections": selected})
        assert set(preview) == {"schema_version", "timestamp", *selected}
        assert "runtime" not in preview

        output = tmp_path / "diagnostics" / "selected.zip"
        exported = _request(
            core,
            "diagnostics.export",
            {"output_path": str(output), "sections": selected},
        )
        assert exported["included_sections"] == selected
        with zipfile.ZipFile(output) as archive:
            assert set(archive.namelist()) == {"diagnostics.json", "logs.jsonl"}
            exported_projection = json.loads(archive.read("diagnostics.json"))
            assert b"m9-diagnostic-parity" in archive.read("logs.jsonl")
        assert set(exported_projection) == set(preview)
        assert "provider" not in exported_projection

        empty_output = tmp_path / "diagnostics" / "empty.zip"
        empty = _request(
            core,
            "diagnostics.export",
            {"output_path": str(empty_output), "sections": []},
        )
        assert empty["included_sections"] == []
        with zipfile.ZipFile(empty_output) as archive:
            assert archive.namelist() == ["diagnostics.json"]
            assert set(json.loads(archive.read("diagnostics.json"))) == {
                "schema_version",
                "timestamp",
            }
    finally:
        core.close()


def test_startup_recovery_marks_process_owned_state_interrupted(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    first = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    project_id = _project(first, "M9 recovery project")
    first.close()
    project_db = data_root / "projects" / project_id / "project.db"
    run_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    live_session_id = str(uuid.uuid4())
    with connect_project_database(project_db) as connection:
        for current_session_id, mode in ((session_id, "run"), (live_session_id, "live_assist")):
            connection.execute(
                """
                INSERT INTO sessions (
                    id, project_id, mode, started_at, ended_at, style_policy,
                    privacy_mode, provider_id, current_slide_start, status, teach_state
                ) VALUES (?, ?, ?, '2026-09-04T00:00:00Z', NULL, 'preserve_voice',
                          'local_only', NULL, NULL, 'active', 'ready_for_prompt')
                """,
                (current_session_id, project_id, mode),
            )
        connection.execute(
            """
            INSERT INTO provider_runs (
                id, session_id, task_type, provider_id, privacy_mode, started_at,
                ended_at, status, input_token_count, output_token_count, latency_ms,
                context_manifest_json, error_code
            ) VALUES (?, ?, 'teach_question', 'fake', 'local_only',
                      '2026-09-04T00:00:00Z', NULL, 'started', NULL, NULL, NULL, '{}', NULL)
            """,
            (run_id, session_id),
        )
        connection.commit()

    recovered = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        with recovered._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            provider_run = connection.execute(
                "SELECT status, error_code, ended_at FROM provider_runs WHERE id = ?", (run_id,)
            ).fetchone()
            sessions = connection.execute(
                "SELECT id, mode, status, ended_at FROM sessions ORDER BY id"
            ).fetchall()
        assert provider_run["status"] == "error"
        assert provider_run["error_code"] == "CORE_RESTART_INTERRUPTED"
        assert provider_run["ended_at"]
        assert {row["status"] for row in sessions} == {"aborted"}
        assert {row["mode"] for row in sessions} == {"run", "live_assist"}
    finally:
        recovered.close()


def test_malicious_archive_names_and_links_are_rejected_without_extraction(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.pptx"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml", "<presentation/>")
        archive.writestr("../outside.xml", "no")
    with pytest.raises(CoreDomainError) as traversal_error:
        preflight_pptx_archive(traversal)
    assert traversal_error.value.code == "SOURCE_ARCHIVE_UNSAFE"

    linked = tmp_path / "linked.pptx"
    with zipfile.ZipFile(linked, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml", "<presentation/>")
        link = zipfile.ZipInfo("ppt/external-link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "C:/outside")
    with pytest.raises(CoreDomainError) as link_error:
        preflight_pptx_archive(linked)
    assert link_error.value.code == "SOURCE_ARCHIVE_UNSAFE"

    duplicate = tmp_path / "duplicate.pptx"
    with zipfile.ZipFile(duplicate, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml", "<presentation/>")
        archive.writestr("PPT/PRESENTATION.XML", "<duplicate/>")
    with pytest.raises(CoreDomainError) as duplicate_error:
        preflight_pptx_archive(duplicate)
    assert duplicate_error.value.code == "SOURCE_ARCHIVE_UNSAFE"

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(ingestion_security, "MAX_ARCHIVE_MEMBER_NAME_LENGTH", 12)
        with pytest.raises(CoreDomainError) as name_error:
            preflight_pptx_archive(traversal)
        assert name_error.value.code == "SOURCE_ARCHIVE_UNSAFE"
    finally:
        monkeypatch.undo()
