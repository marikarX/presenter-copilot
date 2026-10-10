from __future__ import annotations

import sqlite3
from pathlib import Path

from test_presentation_edit_planning import call, context

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter
from presenter_core.storage.database import connect_project_database


def setup(core: CoreService, tmp_path: Path):
    params = context(core)
    scope = {
        "project_id": params["project_id"],
        "document_id": params["document_id"],
        "revision_id": params["expected_revision_id"],
        "slide_number": 1,
    }
    inventory = call(core, "presentation.workspace.list_text_targets", scope)
    scope["slide_id"] = inventory["slide_id"]
    target = inventory["targets"][0]
    source = tmp_path / "Evidence.txt"
    source.write_text("The pilot measures decision quality with a review after thirty days.")
    call(
        core,
        "source.import",
        {"project_id": scope["project_id"], "kind": "supporting", "path": str(source)},
    )
    evidence = call(
        core,
        "presentation.workspace.search_claim_evidence",
        {"project_id": scope["project_id"], "query": "pilot"},
    )["items"][0]
    return scope, target, evidence


def test_claim_binding_evidence_freshness_revision_inheritance_and_undo(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        original = scope["revision_id"]
        payload = {
            **scope,
            "object_id": target["object_id"],
            "quote": target["decision_text"],
            "evidence": [
                {
                    "chunk_id": evidence["chunk_id"],
                    "sha256": evidence["sha256"],
                    "relation": "supports",
                }
            ],
            "confirm": True,
        }
        saved = call(core, "presentation.workspace.save_claim", payload)
        core.close()
        core = CoreService(
            data_root=tmp_path / "data",
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        )
        item = call(core, "presentation.workspace.list_claims", scope)["items"][0]
        assert item["coverage"] == "supported" and item["span_status"] == "unchanged"
        assert item["quote"] == target["decision_text"] and item["provenance"] == "user_confirmed"
        assert item["evidence"][0]["text"] == evidence["text"]
        changed = call(
            core,
            "presentation.workspace.replace_text_shape",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "expected_revision_id": original,
                "slide_id": scope["slide_id"],
                "object_id": target["object_id"],
                "expected_text": target["current_text"],
                "replacement_text": "Reject the pilot",
                "operation_type": "replace_text_shape",
            },
        )
        call(core, "presentation.workspace.save_claim", payload, ok=False)
        scope["revision_id"] = changed["revision_id"]
        item = call(core, "presentation.workspace.list_claims", scope)["items"][0]
        assert item["coverage"] == "needs_review" and item["span_status"] == "changed"
        call(
            core,
            "presentation.workspace.save_claim",
            {**payload, **scope, "claim_id": saved["claim_id"]},
            ok=False,
        )
        call(
            core,
            "presentation.workspace.save_claim",
            {**payload, **scope, "quote": "Reject the pilot", "claim_id": saved["claim_id"]},
        )
        assert (
            call(core, "presentation.workspace.list_claims", scope)["items"][0]["coverage"]
            == "supported"
        )
        with core._storage.project_database(scope["project_id"]) as connection:
            connection.execute(
                "UPDATE chunks SET text = 'A different source finding' WHERE id = ?",
                (evidence["chunk_id"],),
            )
            connection.commit()
        item = call(core, "presentation.workspace.list_claims", scope)["items"][0]
        assert item["coverage"] == "needs_review" and item["evidence"][0]["status"] == "changed"
        assert item["evidence"][0]["text"] == evidence["text"]
        call(
            core,
            "presentation.workspace.save_claim",
            {**payload, **scope, "quote": "Reject the pilot", "claim_id": saved["claim_id"]},
            ok=False,
        )
        call(
            core,
            "presentation.workspace.remove_claim",
            {**scope, "claim_id": saved["claim_id"], "confirm": True},
        )
        assert not call(core, "presentation.workspace.list_claims", scope)["items"]
        call(
            core,
            "presentation.workspace.step_revision",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "expected_revision_id": scope["revision_id"],
                "direction": "undo",
            },
        )
        scope["revision_id"] = original
        item = call(core, "presentation.workspace.list_claims", scope)["items"][0]
        assert item["quote"] == target["decision_text"] and item["span_status"] == "unchanged"
        assert item["evidence"][0]["status"] == "changed"
    finally:
        core.close()


def test_invalid_claim_links_and_confirmation_leave_no_claims(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        payload = {
            **scope,
            "object_id": target["object_id"],
            "quote": target["decision_text"],
            "confirm": True,
        }
        for override in [
            {"confirm": False},
            {"quote": "Invented claim"},
            {"object_id": "foreign"},
            {
                "evidence": [
                    {"chunk_id": evidence["chunk_id"], "sha256": "0" * 64, "relation": "supports"}
                ]
            },
            {
                "evidence": [
                    {"chunk_id": "foreign", "sha256": evidence["sha256"], "relation": "supports"}
                ]
            },
        ]:
            call(core, "presentation.workspace.save_claim", {**payload, **override}, ok=False)
        assert not call(core, "presentation.workspace.list_claims", scope)["items"]
        call(core, "presentation.workspace.save_claim", payload)
        assert (
            call(core, "presentation.workspace.list_claims", scope)["items"][0]["coverage"]
            == "unlinked"
        )
        assert not call(
            core,
            "presentation.workspace.search_claim_evidence",
            {"project_id": scope["project_id"], "query": "Approve the pilot"},
        )["items"]
        claim_id = call(core, "presentation.workspace.list_claims", scope)["items"][0]["claim_id"]
        for relation, coverage in [
            ("context", "unlinked"),
            ("contradicts", "conflicting"),
            ("supports", "supported"),
        ]:
            call(
                core,
                "presentation.workspace.save_claim",
                {
                    **payload,
                    "claim_id": claim_id,
                    "evidence": [
                        {
                            "chunk_id": evidence["chunk_id"],
                            "sha256": evidence["sha256"],
                            "relation": relation,
                        }
                    ],
                },
            )
            assert (
                call(core, "presentation.workspace.list_claims", scope)["items"][0]["coverage"]
                == coverage
            )
        changed = call(
            core,
            "presentation.workspace.replace_text_shape",
            {
                "project_id": scope["project_id"],
                "document_id": scope["document_id"],
                "expected_revision_id": scope["revision_id"],
                "slide_id": scope["slide_id"],
                "object_id": target["object_id"],
                "expected_text": target["current_text"],
                "replacement_text": "aaa",
                "operation_type": "replace_text_shape",
            },
        )
        scope["revision_id"] = changed["revision_id"]
        call(
            core, "presentation.workspace.save_claim", {**payload, **scope, "quote": "aa"}, ok=False
        )

    finally:
        core.close()


def test_v14_claim_migration_preserves_library(tmp_path: Path) -> None:
    path = tmp_path / "project.db"
    connection = connect_project_database(path)
    connection.execute("DROP TABLE presentation_components")
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
    connection.execute(
        "INSERT INTO project_picture_assets VALUES "
        "('id', 'Preserved.png', 'sha', 'image/png', 1, ?, 'now')",
        (b"x",),
    )
    connection.execute("PRAGMA user_version = 14")
    connection.commit()
    connection.close()
    with connect_project_database(path) as migrated:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 24
        assert (
            migrated.execute("SELECT name FROM project_picture_assets").fetchone()[0]
            == "Preserved.png"
        )
        assert not migrated.execute("SELECT * FROM presentation_claims").fetchall()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM project_picture_assets").fetchone()[0] == 1


def test_deep_revision_history_is_explicitly_incomplete(tmp_path: Path) -> None:
    import uuid

    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, _ = setup(core, tmp_path)
        call(
            core,
            "presentation.workspace.save_claim",
            {
                **scope,
                "object_id": target["object_id"],
                "quote": target["decision_text"],
                "confirm": True,
            },
        )
        with core._storage.project_database(scope["project_id"]) as connection:
            parent = scope["revision_id"]
            for index in range(102):
                revision = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO presentation_revisions
                    SELECT ?, presentation_id, ?, ?, 'edited', local_snapshot_path,
                           sha256, byte_size, created_at
                    FROM presentation_revisions WHERE id = ?
                """,
                    (revision, parent, index + 2, parent),
                )
                parent = revision
            connection.execute(
                "UPDATE presentation_revision_heads SET revision_id = ? WHERE presentation_id = ?",
                (parent, scope["document_id"]),
            )
            connection.commit()
        scope["revision_id"] = parent
        result = call(core, "presentation.workspace.list_claims", scope)
        assert result["lineage_truncated"] is True and result["lineage_limit"] == 100
        assert result["items"] == []
        deck = call(
            core,
            "presentation.workspace.review_deck_semantics",
            {key: scope[key] for key in ("project_id", "document_id", "revision_id")},
        )
        assert deck["incomplete"] is True and deck["page_claim_counts"]["supported"] == 0
        assert all("incomplete_coverage" in slide["attention_reasons"] for slide in deck["items"])
    finally:
        core.close()
