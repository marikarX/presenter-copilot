from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter, FastEmbedAdapter
from presenter_core.storage.database import PROJECT_SCHEMA_VERSION, connect_project_database

FIXTURE_ROOT = Path(__file__).parents[2] / "samples" / "synthetic-deck"


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


def create_project(core: CoreService) -> str:
    response = call(core, "create", "project.create", {"name": "Synthetic M2"})
    assert response["ok"] is True
    return response["result"]["project"]["id"]


def import_fixture(core: CoreService, project_id: str) -> dict[str, str]:
    paths = {
        "presentation.pptx": (FIXTURE_ROOT / "deck" / "presentation.pptx", "presentation"),
        "cost-model.pdf": (FIXTURE_ROOT / "supporting" / "cost-model.pdf", "supporting"),
        "architecture-notes.md": (
            FIXTURE_ROOT / "supporting" / "architecture-notes.md",
            "supporting",
        ),
    }
    document_ids: dict[str, str] = {}
    for index, (name, (path, kind)) in enumerate(paths.items()):
        response = call(
            core,
            f"import-{index}",
            "source.import",
            {"project_id": project_id, "path": str(path.resolve()), "kind": kind},
        )
        assert response["ok"] is True, response
        document_ids[name] = response["result"]["document"]["id"]
    return document_ids


def seed_semantic_relationships(core: CoreService, adapter: DeterministicEmbeddingAdapter) -> None:
    with core._storage.project_database(next(iter(_project_ids(core)))) as connection:  # type: ignore[attr-defined]
        rows = connection.execute("SELECT id, text FROM chunks ORDER BY id").fetchall()
    for row in rows:
        text = str(row["text"])
        if "Target recovery time objective" in text:
            vector = [1.0, 0.0, 0.0, 0.0]
        elif "Rejected option: rebuild" in text:
            vector = [0.0, 1.0, 0.0, 0.0]
        elif "cobalt lighthouse 731" in text:
            vector = [0.0, 0.0, 0.0, 1.0]
        elif "Proposed solution 3-year cost" in text:
            vector = [0.0, 0.0, 1.0, 0.0]
        else:
            vector = [0.0, 0.0, 1.0, 0.0]
        adapter.set_vector(text, vector)


def _project_ids(core: CoreService) -> list[str]:
    return [row["id"] for row in core._storage.list_app_rows()]  # type: ignore[attr-defined]


def build_fixture(
    tmp_path: Path,
) -> tuple[CoreService, DeterministicEmbeddingAdapter, str, dict[str, str]]:
    adapter = DeterministicEmbeddingAdapter(dimension=4)
    core = CoreService(data_root=tmp_path / "data", embedding_adapter=adapter)
    project_id = create_project(core)
    document_ids = import_fixture(core, project_id)
    seed_semantic_relationships(core, adapter)
    return core, adapter, project_id, document_ids


def test_m1_project_database_migrates_to_m2_and_preserves_content(tmp_path: Path) -> None:
    database_path = tmp_path / "project.db"
    with sqlite3.connect(database_path) as connection:
        from presenter_core.storage.database import _migrate_project_v1

        _migrate_project_v1(connection)
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            """
            INSERT INTO project (
                id, name, created_at, updated_at, privacy_mode,
                default_style_policy, custom_style_guidance,
                current_presentation_id, schema_version
            ) VALUES (?, 'old', 'now', 'now', 'local_only', 'preserve_voice', NULL, NULL, 1)
            """,
            ("project-row",),
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, project_id, kind, original_name, local_snapshot_path,
                source_uri, sha256, mime_type, parser_id, imported_at,
                parse_status, parse_error_code, parse_error_message,
                byte_size, metadata_json
            ) VALUES (?, ?, 'supporting', 'old.txt', NULL, NULL, ?, 'text/plain',
                      'text.stdlib', 'now', 'ready', NULL, NULL, 3, '{}')
            """,
            ("document-row", "project-row", "a" * 64),
        )
        connection.execute(
            """
            INSERT INTO source_units (
                id, document_id, unit_type, ordinal, title, start_ms,
                end_ms, speaker_label, text, metadata_json
            ) VALUES ('unit-row', 'document-row', 'section', 1, NULL, NULL, NULL, NULL,
                      'preserved', '{}')
            """
        )
        connection.execute(
            """
            INSERT INTO chunks (
                id, source_unit_id, chunk_index, text, token_count,
                embedding_key, lexical_text, created_at
            ) VALUES ('chunk-row', 'unit-row', 0, 'preserved', NULL, NULL, 'preserved', 'now')
            """
        )
        connection.commit()

    migrated = connect_project_database(database_path)
    try:
        assert PROJECT_SCHEMA_VERSION == 2
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 2
        assert migrated.execute("SELECT schema_version FROM project").fetchone()[0] == 2
        assert migrated.execute("SELECT text FROM chunks").fetchone()[0] == "preserved"
        assert migrated.execute("SELECT COUNT(*) FROM embedding_generations").fetchone()[0] == 0
        assert migrated.execute("SELECT COUNT(*) FROM embedding_vectors").fetchone()[0] == 0
    finally:
        migrated.close()


def test_deterministic_hybrid_ranking_notes_filters_and_conflicts(tmp_path: Path) -> None:
    core, adapter, project_id, document_ids = build_fixture(tmp_path)
    try:
        adapter.set_query_vector(
            "How quickly can we recover after losing a region?", [1.0, 0.0, 0.0, 0.0]
        )
        adapter.set_query_vector(
            "Which alternative was rejected because it increased migration risk?",
            [0.0, 1.0, 0.0, 0.0],
        )
        adapter.set_query_vector("Find the note-only phrase", [0.0, 0.0, 0.0, 1.0])
        adapter.set_query_vector("What is the RTO?", [1.0, 0.0, 0.0, 0.0])
        rebuilt = call(core, "rebuild", "retrieval.rebuild", {"project_id": project_id})
        assert rebuilt["ok"] is True, rebuilt
        assert rebuilt["result"]["embedded_count"] > 0

        health = call(core, "health", "retrieval.health", {"project_id": project_id})
        assert health["result"]["status"] == "ready"
        assert health["result"]["semantic_coverage"] == 1.0
        assert (
            health["result"]["current_indexed_mappings"]
            == health["result"]["current_project_chunk_count"]
        )

        recovery = call(
            core,
            "recovery",
            "retrieval.query",
            {
                "project_id": project_id,
                "query": "How quickly can we recover after losing a region?",
                "limit": 3,
            },
        )["result"]
        assert recovery["mode"] == "hybrid"
        assert recovery["hits"][0]["evidence"]["label"] == "presentation.pptx slide 10"
        assert "semantic" in recovery["hits"][0]["reasons"]

        rejected = call(
            core,
            "rejected",
            "retrieval.query",
            {
                "project_id": project_id,
                "query": "Which alternative was rejected because it increased migration risk?",
                "limit": 3,
            },
        )["result"]
        assert rejected["hits"][0]["evidence"]["label"] == "presentation.pptx slide 18"

        notes = call(
            core,
            "notes",
            "retrieval.query",
            {"project_id": project_id, "query": "Find the note-only phrase", "limit": 3},
        )["result"]
        assert notes["hits"][0]["evidence"]["label"] == "presentation.pptx slide 12"
        assert "cobalt lighthouse 731" in notes["hits"][0]["evidence"]["text"]

        filtered = call(
            core,
            "filtered",
            "retrieval.query",
            {
                "project_id": project_id,
                "query": "How quickly can we recover after losing a region?",
                "source_types": ["pdf"],
                "document_ids": [document_ids["cost-model.pdf"]],
                "limit": 3,
            },
        )["result"]
        assert filtered["hits"]
        assert all("cost-model.pdf" in hit["evidence"]["label"] for hit in filtered["hits"])

        conflict = call(
            core,
            "conflict",
            "retrieval.query",
            {"project_id": project_id, "query": "What is the RTO?", "limit": 3},
        )["result"]
        assert conflict["conflicts"]
        values = {value["normalized_value"] for value in conflict["conflicts"][0]["values"]}
        assert {"15 minutes", "30 minutes"} <= values
        assert conflict["conflicts"][0]["subject"] == "RTO"
    finally:
        core.close()


def test_exact_number_slide_boost_reuse_and_embedding_keys(tmp_path: Path) -> None:
    core, adapter, project_id, _ = build_fixture(tmp_path)
    try:
        adapter.set_query_vector("$980,000", [0.0, 0.0, 1.0, 0.0])
        first = call(core, "first", "retrieval.rebuild", {"project_id": project_id})["result"]
        first_calls = adapter.document_call_count
        assert first_calls == first["embedded_count"]

        exact = call(
            core,
            "exact",
            "retrieval.query",
            {"project_id": project_id, "query": "$980,000", "limit": 1},
        )["result"]
        assert exact["hits"][0]["evidence"]["label"] == "presentation.pptx slide 8"
        assert "exact_number" in exact["hits"][0]["reasons"]

        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            keys = connection.execute(
                "SELECT embedding_key FROM chunks WHERE embedding_key IS NOT NULL"
            ).fetchall()
        assert keys and all(str(row[0]).count(":") == 1 for row in keys)

        second = call(core, "second", "retrieval.rebuild", {"project_id": project_id})["result"]
        assert second["reused_count"] == first["matrix_row_count"]
        assert second["embedded_count"] == 0
        assert adapter.document_call_count == first_calls
    finally:
        core.close()


def test_repeated_rebuild_retires_generations_and_converges_filesystem_state(
    tmp_path: Path,
) -> None:
    core, adapter, project_id, _ = build_fixture(tmp_path)
    try:
        adapter.set_query_vector("rebuild lifecycle query", [1.0, 0.0, 0.0, 0.0])
        rebuilds = [
            call(core, "rebuild-1", "retrieval.rebuild", {"project_id": project_id})["result"],
            call(core, "rebuild-2", "retrieval.rebuild", {"project_id": project_id})["result"],
            call(core, "rebuild-3", "retrieval.rebuild", {"project_id": project_id})["result"],
        ]
        chunk_count = rebuilds[0]["matrix_row_count"]
        assert chunk_count > 0
        assert rebuilds[1]["reused_count"] == chunk_count
        assert rebuilds[1]["embedded_count"] == 0
        assert rebuilds[2]["reused_count"] == chunk_count
        assert rebuilds[2]["embedded_count"] == 0
        assert len({item["generation_id"] for item in rebuilds}) == 3

        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            assert (
                connection.execute("SELECT COUNT(*) FROM embedding_generations").fetchone()[0] == 1
            )
            active_id = connection.execute(
                "SELECT id FROM embedding_generations WHERE is_active = 1"
            ).fetchone()[0]
            assert (
                connection.execute("SELECT COUNT(*) FROM embedding_vectors").fetchone()[0]
                == chunk_count
            )
            keys = connection.execute(
                "SELECT embedding_key FROM chunks WHERE embedding_key IS NOT NULL"
            ).fetchall()
        assert keys and all(str(row[0]).startswith(f"{active_id}:") for row in keys)

        embedding_directory = core._storage.paths.safe_embeddings_directory(project_id)  # type: ignore[attr-defined]
        matrix_files = sorted(embedding_directory.glob("vectors-*.npy"))
        assert len(matrix_files) == 1
        assert not list(embedding_directory.glob(".staging-*.npy"))

        # Health is also allowed to repair derived files left by an interrupted
        # cleanup without changing the active DB generation.
        orphan_matrix = embedding_directory / "vectors-orphan.npy"
        orphan_staging = embedding_directory / ".staging-orphan.npy"
        orphan_matrix.write_bytes(b"orphan")
        orphan_staging.write_bytes(b"staging")
        health = call(core, "health", "retrieval.health", {"project_id": project_id})
        assert health["result"]["status"] == "ready"
        assert not orphan_matrix.exists()
        assert not orphan_staging.exists()

        queried = call(
            core,
            "query-after-rebuilds",
            "retrieval.query",
            {"project_id": project_id, "query": "rebuild lifecycle query", "limit": 3},
        )["result"]
        assert queried["hits"]
    finally:
        core.close()


def test_failed_generation_activation_rolls_back_and_cleans_orphan_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core, adapter, project_id, _ = build_fixture(tmp_path)
    try:
        adapter.set_query_vector("rollback lifecycle query", [1.0, 0.0, 0.0, 0.0])
        first = call(core, "initial-build", "retrieval.rebuild", {"project_id": project_id})[
            "result"
        ]
        data_root = tmp_path / "data"
        project_database = data_root / "projects" / project_id / "project.db"
        with sqlite3.connect(project_database) as connection:
            active_before = connection.execute(
                "SELECT id, matrix_relative_path FROM embedding_generations WHERE is_active = 1"
            ).fetchone()
            mapping_count_before = connection.execute(
                "SELECT COUNT(*) FROM embedding_vectors"
            ).fetchone()[0]
        assert active_before is not None
        active_id, active_relative = active_before
        active_matrix = data_root / "projects" / project_id / active_relative
        assert active_matrix.is_file()

        def fail_commit(connection: sqlite3.Connection) -> None:
            del connection
            raise sqlite3.OperationalError("injected generation activation failure")

        monkeypatch.setattr(
            core._hybrid_retrieval,  # type: ignore[attr-defined]
            "_commit_generation_transaction",
            fail_commit,
        )
        failed = call(core, "failed-build", "retrieval.rebuild", {"project_id": project_id})
        assert failed["ok"] is False
        assert failed["error"]["code"] == "RETRIEVAL_REBUILD_FAILED"

        with sqlite3.connect(project_database) as connection:
            generations = connection.execute(
                "SELECT id, is_active FROM embedding_generations"
            ).fetchall()
            assert generations == [(active_id, 1)]
            assert (
                connection.execute("SELECT COUNT(*) FROM embedding_vectors").fetchone()[0]
                == mapping_count_before
            )
        assert active_matrix.is_file()
        embedding_directory = data_root / "projects" / project_id / "embeddings"
        assert len(list(embedding_directory.glob("vectors-*.npy"))) == 1
        assert not list(embedding_directory.glob(".staging-*.npy"))

        queried = call(
            core,
            "query-after-failed-build",
            "retrieval.query",
            {"project_id": project_id, "query": "rollback lifecycle query", "limit": 3},
        )["result"]
        assert queried["hits"]
        assert queried["semantic"]["generation_id"] == active_id
        assert first["generation_id"] == active_id
    finally:
        core.close()


def test_unchanged_source_reindex_restores_reusable_active_vectors(tmp_path: Path) -> None:
    core, adapter, project_id, document_ids = build_fixture(tmp_path)
    try:
        call(core, "build", "retrieval.rebuild", {"project_id": project_id})
        initial_calls = adapter.document_call_count
        reindexed = call(
            core,
            "reindex",
            "source.reindex",
            {"project_id": project_id, "document_id": document_ids["presentation.pptx"]},
        )
        assert reindexed["ok"] is True, reindexed
        health = call(core, "health", "retrieval.health", {"project_id": project_id})
        assert health["result"]["status"] == "ready"

        rebuilt = call(core, "rebuild-again", "retrieval.rebuild", {"project_id": project_id})
        assert rebuilt["result"]["reused_count"] == rebuilt["result"]["matrix_row_count"]
        assert rebuilt["result"]["embedded_count"] == 0
        assert adapter.document_call_count == initial_calls
    finally:
        core.close()


def test_current_and_adjacent_slide_boosts_only_apply_to_pptx(tmp_path: Path) -> None:
    core, adapter, project_id, _ = build_fixture(tmp_path)
    try:
        ambiguous = "ambiguous retrieval prompt"
        adapter.set_query_vector(ambiguous, [0.0, 0.0, 1.0, 0.0])
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            rows = connection.execute(
                """
                SELECT c.text FROM chunks AS c
                JOIN source_units AS su ON su.id = c.source_unit_id
                JOIN documents AS d ON d.id = su.document_id
                WHERE d.original_name = 'presentation.pptx' AND su.ordinal IN (8, 9)
                """
            ).fetchall()
        for row in rows:
            adapter.set_vector(str(row[0]), [0.0, 0.0, 1.0, 0.0])
        call(core, "rebuild", "retrieval.rebuild", {"project_id": project_id})

        current = call(
            core,
            "current",
            "retrieval.query",
            {
                "project_id": project_id,
                "query": ambiguous,
                "current_slide": 8,
                "slide_window": 1,
                "limit": 3,
            },
        )["result"]
        assert current["hits"][0]["evidence"]["label"] == "presentation.pptx slide 8"
        assert (
            current["hits"][0]["scores"]["slide_boost"]
            > current["hits"][1]["scores"]["slide_boost"]
        )
        assert current["hits"][1]["scores"]["slide_boost"] == 0.07

        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            pdf_chunk = connection.execute(
                """
                SELECT c.text FROM chunks AS c
                JOIN source_units AS su ON su.id = c.source_unit_id
                JOIN documents AS d ON d.id = su.document_id
                WHERE d.original_name = 'cost-model.pdf' AND su.ordinal = 2
                """
            ).fetchone()[0]
        adapter.set_vector(str(pdf_chunk), [0.0, 0.0, 1.0, 0.0])
        call(core, "rebuild-again", "retrieval.rebuild", {"project_id": project_id})
        no_pdf_boost = call(
            core,
            "pdf-no-boost",
            "retrieval.query",
            {
                "project_id": project_id,
                "query": ambiguous,
                "current_slide": 8,
                "source_types": ["pdf"],
                "limit": 1,
            },
        )["result"]
        assert no_pdf_boost["hits"][0]["scores"]["slide_boost"] == 0
    finally:
        core.close()


def test_deletion_restart_corruption_and_model_mismatch_degrade_safely(tmp_path: Path) -> None:
    core, adapter, project_id, document_ids = build_fixture(tmp_path)
    data_root = tmp_path / "data"
    try:
        adapter.set_query_vector("recovery", [1.0, 0.0, 0.0, 0.0])
        call(core, "build", "retrieval.rebuild", {"project_id": project_id})
        before = call(
            core,
            "before",
            "retrieval.query",
            {"project_id": project_id, "query": "recovery", "limit": 2},
        )["result"]
        assert before["hits"]
        with sqlite3.connect(data_root / "projects" / project_id / "project.db") as connection:
            relative_path = connection.execute(
                "SELECT matrix_relative_path FROM embedding_generations WHERE is_active = 1"
            ).fetchone()[0]
        matrix_path = data_root / "projects" / project_id / relative_path
        core.close()
        matrix_path.write_bytes(matrix_path.read_bytes()[:32])

        corrupt_adapter = DeterministicEmbeddingAdapter(dimension=4)
        corrupt_core = CoreService(data_root=data_root, embedding_adapter=corrupt_adapter)
        try:
            fallback = call(
                corrupt_core,
                "corrupt-query",
                "retrieval.query",
                {"project_id": project_id, "query": "recovery", "limit": 2},
            )["result"]
            assert fallback["mode"] == "lexical_fallback"
            assert fallback["semantic"]["status"] == "corrupt"
            repaired = call(
                corrupt_core,
                "repair",
                "retrieval.rebuild",
                {"project_id": project_id},
            )
            assert repaired["ok"] is True
        finally:
            corrupt_core.close()

        mismatched = CoreService(
            data_root=data_root,
            embedding_adapter=DeterministicEmbeddingAdapter(
                dimension=4, model_fingerprint="different-fingerprint"
            ),
        )
        try:
            stale = call(
                mismatched,
                "stale",
                "retrieval.query",
                {"project_id": project_id, "query": "recovery", "limit": 2},
            )["result"]
            assert stale["mode"] == "lexical_fallback"
            assert stale["semantic"]["status"] == "stale"
        finally:
            mismatched.close()

        restarted_adapter = DeterministicEmbeddingAdapter(dimension=4)
        restarted = CoreService(data_root=data_root, embedding_adapter=restarted_adapter)
        try:
            restarted_health = call(
                restarted,
                "restart-health",
                "retrieval.health",
                {"project_id": project_id},
            )["result"]
            assert restarted_health["status"] == "ready"
            with restarted._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
                target_chunk_ids = [
                    str(row["id"])
                    for row in connection.execute(
                        """
                        SELECT c.id
                        FROM chunks AS c
                        JOIN source_units AS su ON su.id = c.source_unit_id
                        WHERE su.document_id = ?
                        ORDER BY c.id
                        """,
                        (document_ids["presentation.pptx"],),
                    ).fetchall()
                ]
            assert target_chunk_ids
            deleted = call(
                restarted,
                "delete",
                "source.delete",
                {"project_id": project_id, "document_id": document_ids["presentation.pptx"]},
            )
            assert deleted["result"]["deleted"] is True
            with restarted._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
                placeholders = ", ".join("?" for _ in target_chunk_ids)
                assert (
                    connection.execute(
                        "SELECT COUNT(*) FROM embedding_vectors "
                        "WHERE entity_type = 'chunk' AND entity_id IN (" + placeholders + ")",
                        target_chunk_ids,
                    ).fetchone()[0]
                    == 0
                )
            after_delete = call(
                restarted,
                "after-delete",
                "retrieval.query",
                {"project_id": project_id, "query": "$980,000", "limit": 5},
            )["result"]
            assert all(
                hit["evidence"]["evidence_id"] not in target_chunk_ids
                and hit["evidence"]["source_id"] != document_ids["presentation.pptx"]
                and "presentation.pptx" not in hit["evidence"]["label"]
                for hit in after_delete["hits"]
            )
        finally:
            restarted.close()
    finally:
        if core._storage._app:  # type: ignore[attr-defined]
            try:
                core.close()
            except sqlite3.ProgrammingError:
                pass


def test_project_delete_removes_embedding_files_and_preserves_shared_model_cache(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    core, adapter, project_id, _ = build_fixture(tmp_path)
    model_cache = data_root / "models" / "embeddings"
    model_cache.mkdir(parents=True, exist_ok=True)
    marker = model_cache / "prepared-model.marker"
    marker.write_text("keep", encoding="utf-8")
    try:
        adapter.set_query_vector("project deletion query", [1.0, 0.0, 0.0, 0.0])
        built = call(core, "build", "retrieval.rebuild", {"project_id": project_id})
        assert built["ok"] is True
        queried = call(
            core,
            "populate-cache",
            "retrieval.query",
            {"project_id": project_id, "query": "project deletion query", "limit": 2},
        )
        assert queried["result"]["hits"]
        project_root = data_root / "projects" / project_id
        embedding_directory = project_root / "embeddings"
        assert list(embedding_directory.glob("vectors-*.npy"))
        assert core._hybrid_retrieval._matrix_cache  # type: ignore[attr-defined]

        deleted = call(core, "delete-project", "project.delete", {"project_id": project_id})
        assert deleted["ok"] is True
        assert deleted["result"]["deleted"] is True
        assert not project_root.exists()
        assert not list(core._storage.list_app_rows())  # type: ignore[attr-defined]
        assert marker.read_text(encoding="utf-8") == "keep"
        assert core._hybrid_retrieval._matrix_cache == {}  # type: ignore[attr-defined]
    finally:
        core.close()


def test_retrieval_ipc_methods_are_bounded_and_lexical_fallback_survives_missing_model(
    tmp_path: Path,
) -> None:
    adapter = DeterministicEmbeddingAdapter(dimension=2)
    core = CoreService(data_root=tmp_path / "data", embedding_adapter=adapter)
    try:
        project_id = create_project(core)
        imported = call(
            core,
            "import",
            "source.import",
            {
                "project_id": project_id,
                "path": str((FIXTURE_ROOT / "supporting" / "architecture-notes.md").resolve()),
            },
        )
        assert imported["ok"] is True
        health = call(core, "health", "retrieval.health", {"project_id": project_id})
        assert health["result"]["status"] == "not_built"
        query = call(
            core,
            "query",
            "retrieval.query",
            {"project_id": project_id, "query": "Architecture notes", "limit": 2},
        )
        assert query["ok"] is True
        assert query["result"]["mode"] == "lexical_fallback"
        invalid = call(
            core,
            "invalid",
            "retrieval.query",
            {"project_id": project_id, "query": "x", "limit": 51},
        )
        assert invalid["error"]["code"] == "INVALID_REQUEST"
    finally:
        core.close()


def test_fastembed_missing_cache_is_checked_local_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The normal adapter path must not turn a local cache miss into a download."""
    from fastembed.text.onnx_embedding import OnnxTextEmbedding

    observed: dict[str, Any] = {}

    def fail_download(cls: Any, model: Any, cache_dir: str, **kwargs: Any) -> Path:
        del cls, model, cache_dir
        observed.update(kwargs)
        raise ValueError("test cache miss")

    monkeypatch.setattr(OnnxTextEmbedding, "download_model", classmethod(fail_download))
    adapter = FastEmbedAdapter(cache_dir=tmp_path / "missing-model", local_files_only=True)

    health = adapter.health()

    assert observed["local_files_only"] is True
    assert health.status == "unavailable"
    assert health.error_code == "EMBEDDING_MODEL_UNAVAILABLE"


def test_embedding_matrix_paths_stay_inside_project_vault(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter()
    )
    try:
        project_id = create_project(core)
        paths = core._storage.paths  # type: ignore[attr-defined]
        with pytest.raises(CoreDomainError) as error:
            paths.embedding_matrix_path(project_id, "embeddings/../sources/escape.npy")
        assert error.value.code == "EMBEDDING_PATH_UNSAFE"
    finally:
        core.close()
