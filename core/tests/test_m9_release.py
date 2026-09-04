"""Milestone 9 release-hardening regressions."""

from __future__ import annotations

import json
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
