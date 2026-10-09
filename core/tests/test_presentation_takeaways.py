from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from test_presentation_claims import setup
from test_presentation_edit_planning import call
from test_presentation_narrative import change

from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def save(core, scope, text="Approve a limited reversible pilot", token=None, **extras):
    return call(
        core,
        "presentation.workspace.save_slide_takeaway",
        {**scope, "takeaway": text, "reviewed": True, "expected_record_token": token, **extras},
    )


def test_takeaway_persistence_conflict_clear_inheritance_undo_branch_and_deck_review(
    tmp_path: Path,
):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, _ = setup(core, tmp_path)
        original = dict(scope)
        initial = call(core, "presentation.workspace.get_slide_takeaway", scope)
        assert initial["status"] == "missing" and initial["record_token"] is None
        saved = save(core, scope)
        assert saved["status"] == "reviewed"
        with core._storage.project_database(scope["project_id"]) as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM presentation_revisions").fetchone()[0] == 1
            )
        core.close()
        core = CoreService(
            data_root=tmp_path / "data",
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
        )
        assert call(core, "presentation.workspace.get_slide_takeaway", scope) == saved
        error = call(
            core,
            "presentation.workspace.save_slide_takeaway",
            {**scope, "takeaway": "Concurrent", "reviewed": True, "expected_record_token": None},
            ok=False,
        )
        assert error["code"] == "PRESENTATION_TAKEAWAY_CONFLICT"
        edited = change(core, scope, target)
        scope["revision_id"] = edited["revision_id"]
        inherited = call(core, "presentation.workspace.get_slide_takeaway", scope)
        assert inherited["status"] == "needs_review" and inherited["takeaway"] == saved["takeaway"]
        review = call(
            core,
            "presentation.workspace.review_deck_semantics",
            {k: v for k, v in scope.items() if k in {"project_id", "document_id", "revision_id"}},
        )
        assert review["items"][0]["takeaway"] == saved["takeaway"]
        assert "takeaway_inherited" in review["items"][0]["attention_reasons"]
        cleared = save(core, scope, "", inherited["record_token"])
        assert cleared["takeaway"] == "" and cleared["status"] == "reviewed"
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
        assert call(core, "presentation.workspace.get_slide_takeaway", original) == saved
        branch = change(core, original, target)
        scope["revision_id"] = branch["revision_id"]
        branch_text = call(core, "presentation.workspace.get_slide_takeaway", scope)
        assert (
            branch_text["takeaway"] == saved["takeaway"]
            and branch_text["source_revision_id"] == original["revision_id"]
        )
    finally:
        core.close()


@pytest.mark.parametrize(
    "mutation",
    [
        "unreviewed",
        "oversized",
        "nul",
        "no_token",
        "bad_token",
        "wrong_slide",
        "wrong_number",
        "wrong_revision",
        "unknown",
    ],
)
def test_takeaway_rejects_invalid_scope_and_inputs_without_writes(tmp_path: Path, mutation: str):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, _, _ = setup(core, tmp_path)
        params = {
            **scope,
            "takeaway": "Review this",
            "reviewed": True,
            "expected_record_token": None,
        }
        if mutation == "unreviewed":
            params["reviewed"] = False
        if mutation == "oversized":
            params["takeaway"] = "x" * 1001
        if mutation == "nul":
            params["takeaway"] = "x\x00y"
        if mutation == "no_token":
            params.pop("expected_record_token")
        if mutation == "bad_token":
            params["expected_record_token"] = "bad"
        if mutation == "wrong_slide":
            params["slide_id"] = str(uuid.uuid4())
        if mutation == "wrong_number":
            params["slide_number"] = 2
        if mutation == "wrong_revision":
            params["revision_id"] = str(uuid.uuid4())
        if mutation == "unknown":
            params["unexpected"] = True
        call(core, "presentation.workspace.save_slide_takeaway", params, ok=False)
        with core._storage.project_database(scope["project_id"]) as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM presentation_slide_takeaways").fetchone()[
                    0
                ]
                == 0
            )
    finally:
        core.close()


def test_v16_migration_keeps_intent_claims_and_new_takeaway_empty(tmp_path: Path):
    from test_presentation_narrative import save as save_narrative

    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, _, _ = setup(core, tmp_path)
        intent = save_narrative(core, scope)
        with core._storage.project_database(scope["project_id"]) as connection:
            connection.execute("DROP TABLE presentation_rehearsal_objection_comparison_candidates")
            connection.execute("DROP TABLE presentation_rehearsal_objection_comparisons")
            connection.execute("DROP TABLE presentation_rehearsal_objection_findings")
            connection.execute("DROP TABLE presentation_rehearsal_objection_analyses")
            connection.execute("DROP TABLE presentation_rehearsal_analyses")
            connection.execute("DROP TABLE presentation_revision_checkpoints")
            connection.execute("DROP TABLE presentation_outline_sessions")
            connection.execute("DROP TABLE presentation_outline_proposals")
            connection.execute("DROP TABLE presentation_slide_takeaways")
            connection.execute("PRAGMA user_version=16")
            connection.execute("UPDATE project SET schema_version=16")
            connection.commit()
        with core._storage.project_database(scope["project_id"]) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 23
            assert (
                connection.execute("SELECT COUNT(*) FROM presentation_slide_takeaways").fetchone()[
                    0
                ]
                == 0
            )
        assert (
            call(
                core,
                "presentation.workspace.get_narrative",
                {
                    k: v
                    for k, v in scope.items()
                    if k in {"project_id", "document_id", "revision_id"}
                },
            )
            == intent
        )
    finally:
        core.close()
