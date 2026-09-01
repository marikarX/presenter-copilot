from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.storage.database import (
    APP_SCHEMA_VERSION,
    PROJECT_SCHEMA_VERSION,
    connect_app_database,
    connect_project_database,
    current_schema_version,
)


def call(core: CoreService, request_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    return core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": request_id,
            "method": method,
            "params": params,
        }
    )


def test_new_latest_older_and_future_databases_are_handled_transactionally(tmp_path: Path) -> None:
    app_path = tmp_path / "app.db"
    connection = connect_app_database(app_path)
    assert current_schema_version(connection) == APP_SCHEMA_VERSION
    assert {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    } >= {
        "app_metadata",
        "projects",
    }
    connection.close()

    latest = connect_app_database(app_path)
    assert current_schema_version(latest) == APP_SCHEMA_VERSION
    latest.close()

    older_path = tmp_path / "older.db"
    with sqlite3.connect(older_path) as older:
        older.execute("PRAGMA user_version = 0")
    migrated = connect_app_database(older_path)
    assert current_schema_version(migrated) == APP_SCHEMA_VERSION
    migrated.close()

    future_path = tmp_path / "future.db"
    with sqlite3.connect(future_path) as future:
        future.execute("PRAGMA user_version = 99")
    with pytest.raises(CoreDomainError) as error:
        connect_app_database(future_path)
    assert error.value.code == "DATABASE_VERSION_UNSUPPORTED"
    with sqlite3.connect(future_path) as unchanged:
        assert unchanged.execute("PRAGMA user_version").fetchone()[0] == 99

    project_path = tmp_path / "project.db"
    project = connect_project_database(project_path)
    assert current_schema_version(project) == PROJECT_SCHEMA_VERSION
    project.close()
    project_again = connect_project_database(project_path)
    assert current_schema_version(project_again) == PROJECT_SCHEMA_VERSION
    project_again.close()

    future_project_path = tmp_path / "future-project.db"
    with sqlite3.connect(future_project_path) as future_project:
        future_project.execute("PRAGMA user_version = 99")
    with pytest.raises(CoreDomainError) as project_error:
        connect_project_database(future_project_path)
    assert project_error.value.code == "DATABASE_VERSION_UNSUPPORTED"
    with sqlite3.connect(future_project_path) as unchanged_project:
        assert unchanged_project.execute("PRAGMA user_version").fetchone()[0] == 99


def test_migration_failure_rolls_back_without_replacing_existing_database(tmp_path: Path) -> None:
    app_path = tmp_path / "partially-created.db"
    with sqlite3.connect(app_path) as connection:
        connection.execute("CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("PRAGMA user_version = 0")

    with pytest.raises(CoreDomainError) as error:
        connect_app_database(app_path)
    assert error.value.code == "DATABASE_MIGRATION_FAILED"
    with sqlite3.connect(app_path) as unchanged:
        assert unchanged.execute("PRAGMA user_version").fetchone()[0] == 0
        assert (
            unchanged.execute("SELECT name FROM sqlite_master WHERE name = 'projects'").fetchone()
            is None
        )


def test_project_settings_restart_and_delete_are_vault_scoped(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    core = CoreService(data_root=data_root)
    created = call(core, "create", "project.create", {"name": "Quarterly review"})
    assert created["ok"] is True
    project = created["result"]["project"]
    project_id = project["id"]
    project_root = data_root / "projects" / project_id
    assert (data_root / "app.db").is_file()
    assert (project_root / "project.db").is_file()
    assert (project_root / "sources").is_dir()
    assert not (project_root / "extracted").exists()
    project_database = sqlite3.connect(project_root / "project.db")
    try:
        assert (
            project_database.execute("PRAGMA user_version").fetchone()[0] == PROJECT_SCHEMA_VERSION
        )
        assert (
            project_database.execute(
                "SELECT schema_version FROM project WHERE id = ?", (project_id,)
            ).fetchone()[0]
            == PROJECT_SCHEMA_VERSION
        )
    finally:
        project_database.close()

    updated = call(
        core,
        "update",
        "project.update_settings",
        {
            "project_id": project_id,
            "name": "Quarterly review updated",
            "privacy_mode": "local_only",
            "default_style_policy": "light_polish",
            "custom_style_guidance": "Use evidence first.",
        },
    )
    assert updated["ok"] is True
    core.close()

    restarted = CoreService(data_root=data_root)
    listed = call(restarted, "list", "project.list", {})["result"]["projects"]
    assert len(listed) == 1
    assert listed[0]["id"] == project_id
    assert listed[0]["name"] == "Quarterly review updated"
    opened = call(restarted, "open", "project.open", {"project_id": project_id})
    assert opened["result"]["project"]["default_style_policy"] == "light_polish"

    sibling = data_root / "projects" / "unrelated-sibling"
    sibling.mkdir()
    keep = sibling / "keep.txt"
    keep.write_text("untouched", encoding="utf-8")
    deleted = call(restarted, "delete", "project.delete", {"project_id": project_id})
    assert deleted["result"] == {"project_id": project_id, "deleted": True}
    assert not project_root.exists()
    assert keep.read_text(encoding="utf-8") == "untouched"
    assert call(restarted, "list-after-delete", "project.list", {})["result"]["projects"] == []
    with sqlite3.connect(data_root / "app.db") as app_database:
        assert (
            app_database.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
            is None
        )

    idempotent = call(restarted, "delete-again", "project.delete", {"project_id": project_id})
    assert idempotent["result"] == {"project_id": project_id, "deleted": False}
    restarted.close()


def test_missing_project_database_is_reported_without_recreation_and_does_not_hide_healthy_projects(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    first = CoreService(data_root=data_root)
    corrupt_id = call(first, "create-corrupt", "project.create", {"name": "Corrupt vault"})[
        "result"
    ]["project"]["id"]
    healthy_id = call(first, "create-healthy", "project.create", {"name": "Healthy vault"})[
        "result"
    ]["project"]["id"]
    corrupt_database = data_root / "projects" / corrupt_id / "project.db"
    assert corrupt_database.is_file()
    first.close()
    corrupt_database.unlink()

    second = CoreService(data_root=data_root)
    try:
        listed = call(second, "list", "project.list", {})["result"]["projects"]
        by_id = {project["id"]: project for project in listed}
        assert by_id[corrupt_id]["storage_status"] == "unavailable"
        assert by_id[corrupt_id]["storage_error_code"] == "PROJECT_CORRUPT"
        assert by_id[healthy_id]["storage_status"] == "ready"
        assert not corrupt_database.exists()

        healthy_open = call(second, "healthy-open", "project.open", {"project_id": healthy_id})
        assert healthy_open["ok"] is True
        corrupt_open = call(second, "corrupt-open", "project.open", {"project_id": corrupt_id})
        assert corrupt_open["error"]["code"] == "PROJECT_CORRUPT"
        assert not corrupt_database.exists()
    finally:
        second.close()


def test_project_open_and_delete_reject_a_tampered_registry_path(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    core = CoreService(data_root=data_root)
    created = call(core, "create", "project.create", {"name": "Registry safety"})
    project_id = created["result"]["project"]["id"]
    app_database = sqlite3.connect(data_root / "app.db")
    try:
        app_database.execute(
            "UPDATE projects SET project_relative_path = ? WHERE id = ?",
            ("projects/../outside", project_id),
        )
        app_database.commit()
    finally:
        app_database.close()

    opened = call(core, "open", "project.open", {"project_id": project_id})
    assert opened["error"]["code"] == "PROJECT_PATH_UNSAFE"
    deleted = call(core, "delete", "project.delete", {"project_id": project_id})
    assert deleted["error"]["code"] == "PROJECT_PATH_UNSAFE"
    assert (data_root / "projects" / project_id).is_dir()

    core.close()
