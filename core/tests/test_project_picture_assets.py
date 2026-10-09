from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_presentation_edit_planning import call

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter
from presenter_core.storage.database import connect_project_database

IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGMU"
    "VDJmYGBgYgADAATQAGoNqSJLAAAAAElFTkSuQmCC"
)


def test_library_persists_without_a_deck_and_isolates_projects(tmp_path: Path) -> None:
    root = tmp_path / "data"
    core = CoreService(data_root=root, embedding_adapter=DeterministicEmbeddingAdapter(dimension=2))
    project = call(core, "project.create", {"name": "Images"})["project"]["id"]
    other = call(core, "project.create", {"name": "Other"})["project"]["id"]
    try:
        imported = call(
            core,
            "presentation.workspace.import_project_picture",
            {"project_id": project, "name": "Logo.png", "image_base64": IMAGE},
        )
        duplicate = call(
            core,
            "presentation.workspace.import_project_picture",
            {"project_id": project, "name": "Different name.png", "image_base64": IMAGE},
        )
        assert imported["created"] and not duplicate["created"]
        assert duplicate["asset"] == imported["asset"]
        call(
            core,
            "presentation.workspace.read_project_picture",
            {"project_id": other, "asset_id": imported["asset"]["asset_id"]},
            ok=False,
        )
        assert not call(
            core, "presentation.workspace.list_project_pictures", {"project_id": other}
        )["assets"]
        with core._storage.project_database(project) as connection:
            assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
            assert (
                connection.execute("SELECT COUNT(*) FROM project_picture_assets").fetchone()[0] == 1
            )
    finally:
        core.close()
    core = CoreService(data_root=root, embedding_adapter=DeterministicEmbeddingAdapter(dimension=2))
    try:
        listing = call(
            core, "presentation.workspace.list_project_pictures", {"project_id": project}
        )
        assert listing["assets"] == [imported["asset"]]
        read = call(
            core,
            "presentation.workspace.read_project_picture",
            {"project_id": project, "asset_id": imported["asset"]["asset_id"]},
        )
        assert read["image_base64"] == IMAGE
        scope = {
            "project_id": project,
            "asset_id": imported["asset"]["asset_id"],
            "expected_sha256": imported["asset"]["sha256"],
        }
        call(core, "presentation.workspace.delete_project_picture", scope, ok=False)
        call(
            core,
            "presentation.workspace.delete_project_picture",
            {**scope, "confirm": True, "expected_sha256": "0" * 64},
            ok=False,
        )
        call(core, "presentation.workspace.delete_project_picture", {**scope, "confirm": True})
        assert not call(
            core, "presentation.workspace.list_project_pictures", {"project_id": project}
        )["assets"]
    finally:
        core.close()


def test_invalid_upload_and_tampering_do_not_publish_image_data(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        project = call(core, "project.create", {"name": "Integrity"})["project"]["id"]
        for values in ({"image_base64": "bad"}, {"name": ""}, {"path": "C:/private.png"}):
            call(
                core,
                "presentation.workspace.import_project_picture",
                {"project_id": project, "name": "Logo.png", "image_base64": IMAGE, **values},
                ok=False,
            )
        assert not call(
            core, "presentation.workspace.list_project_pictures", {"project_id": project}
        )["assets"]
        imported = call(
            core,
            "presentation.workspace.import_project_picture",
            {"project_id": project, "name": "Logo.png", "image_base64": IMAGE},
        )["asset"]
        with core._storage.project_database(project) as connection:
            connection.execute("UPDATE project_picture_assets SET image_bytes = ?", (b"tampered",))
            connection.commit()
        error = call(
            core,
            "presentation.workspace.read_project_picture",
            {"project_id": project, "asset_id": imported["asset_id"]},
            ok=False,
        )
        assert error["code"] == "PROJECT_ASSET_CHANGED"
    finally:
        core.close()


def test_v13_to_v14_preserves_existing_project_rows(tmp_path: Path) -> None:
    path = tmp_path / "project.db"
    connection = connect_project_database(path)
    connection.execute(
        "INSERT INTO project (id, name, created_at, updated_at, privacy_mode, "
        "default_style_policy, schema_version) "
        "VALUES ('old', 'Preserved', 'now', 'now', 'local_only', 'preserve_voice', 13)"
    )
    connection.execute("DROP TABLE presentation_rehearsal_objection_comparison_candidates")
    connection.execute("DROP TABLE presentation_rehearsal_objection_comparisons")
    connection.execute("DROP TABLE presentation_rehearsal_objection_findings")
    connection.execute("DROP TABLE presentation_rehearsal_objection_analyses")
    connection.execute("DROP TABLE presentation_rehearsal_analyses")
    connection.execute("DROP TABLE presentation_revision_checkpoints")
    connection.execute("DROP TABLE presentation_outline_sessions")
    connection.execute("DROP TABLE presentation_outline_proposals")
    connection.execute("DROP TABLE presentation_slide_takeaways")
    connection.execute("DROP TABLE presentation_narratives")
    connection.execute("DROP TABLE presentation_claims")
    connection.execute("DROP TABLE project_picture_assets")
    connection.execute("PRAGMA user_version = 13")
    connection.commit()
    connection.close()
    migrated = connect_project_database(path)
    try:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 23
        assert migrated.execute("SELECT name FROM project").fetchone()[0] == "Preserved"
        assert not migrated.execute("SELECT * FROM project_picture_assets").fetchall()
    finally:
        migrated.close()
    with sqlite3.connect(path) as collision:
        collision.execute("PRAGMA user_version = 13")
    with pytest.raises(CoreDomainError):
        connect_project_database(path)
    with sqlite3.connect(path) as unchanged:
        assert unchanged.execute("PRAGMA user_version").fetchone()[0] == 13
        assert unchanged.execute("SELECT name FROM project").fetchone()[0] == "Preserved"


def test_library_pagination_and_count_limit(tmp_path: Path) -> None:
    import base64
    import io

    from PIL import Image

    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        project = call(core, "project.create", {"name": "Capacity"})["project"]["id"]
        first = None
        for index in range(200):
            output = io.BytesIO()
            Image.new("RGB", (2, 2), (index, 12, 34)).save(output, format="PNG")
            encoded = base64.b64encode(output.getvalue()).decode("ascii")
            item = call(
                core,
                "presentation.workspace.import_project_picture",
                {"project_id": project, "name": f"Image {index}.png", "image_base64": encoded},
            )
            if first is None:
                first = encoded, item["asset"]
        ids = []
        cursor = 0
        while True:
            page = call(
                core,
                "presentation.workspace.list_project_pictures",
                {"project_id": project, "cursor": cursor},
            )
            assert len(page["assets"]) == 20
            ids.extend(asset["asset_id"] for asset in page["assets"])
            if not page["has_more"]:
                assert page["next_cursor"] is None
                break
            assert page["next_cursor"] > cursor
            cursor = page["next_cursor"]
        assert len(set(ids)) == 200
        error = call(
            core,
            "presentation.workspace.import_project_picture",
            {"project_id": project, "name": "Overflow.png", "image_base64": IMAGE},
            ok=False,
        )
        assert error["code"] == "PROJECT_ASSET_LIMIT"
        assert first is not None
        duplicate = call(
            core,
            "presentation.workspace.import_project_picture",
            {"project_id": project, "name": "Duplicate.png", "image_base64": first[0]},
        )
        assert not duplicate["created"] and duplicate["asset"] == first[1]
        call(
            core,
            "presentation.workspace.list_project_pictures",
            {"project_id": project, "cursor": True},
            ok=False,
        )
        call(
            core,
            "presentation.workspace.list_project_pictures",
            {"project_id": project, "cursor": 201},
            ok=False,
        )
    finally:
        core.close()
