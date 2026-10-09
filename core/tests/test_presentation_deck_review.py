from __future__ import annotations

from pathlib import Path

import pytest
from test_claim_provider_context import save as save_claim
from test_presentation_claims import setup
from test_presentation_edit_planning import call
from test_presentation_narrative import change

from presenter_core.ipc.core import CoreService
from presenter_core.presentation import workspace_source
from presenter_core.presentation.claims import PresentationClaimService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def scope_only(scope):
    return {key: scope[key] for key in ("project_id", "document_id", "revision_id")}


def review(core, scope, **params):
    return call(
        core, "presentation.workspace.review_deck_semantics", {**scope_only(scope), **params}
    )


def test_deck_pages_reuse_one_verified_inspection_and_show_reviewed_coverage(
    tmp_path: Path, monkeypatch
):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        save_claim(core, scope, target, evidence)
        call(
            core,
            "presentation.workspace.save_slide_purpose",
            {**scope, "purpose": "recommendation"},
        )
        inspect = workspace_source.inspect_pptx_snapshot
        calls = []

        def track(*args, **kwargs):
            calls.append(1)
            return inspect(*args, **kwargs)

        monkeypatch.setattr(workspace_source, "inspect_pptx_snapshot", track)
        result = review(core, scope)
        assert len(calls) == 1
        assert result["total_slides"] == 2 and not result["has_more"]
        assert result["page_claim_counts"] == {
            "supported": 1,
            "conflicting": 0,
            "needs_review": 0,
            "unlinked": 0,
        }
        first, second = result["items"]
        assert first["slide_id"] == scope["slide_id"] and first["title"] == target["current_text"]
        assert first["purpose"] == "recommendation" and first["purpose_status"] == "reviewed"
        assert first["attention_reasons"] == [] and second["claim_count"] == 0
        assert second["attention_reasons"] == ["purpose_missing"]
        assert result["page_slides_needing_attention"] == 1
        assert evidence["text"] not in str(result)
        first_page = review(core, scope, limit=1)
        second_page = review(core, scope, offset=1, limit=1)
        assert first_page["has_more"] and not second_page["has_more"]
        assert first_page["page_claim_counts"]["supported"] == 1
        assert second_page["page_claim_counts"]["supported"] == 0
        empty = review(core, scope, offset=2)
        assert empty["items"] == [] and not empty["has_more"]
        with core._storage.project_database(scope["project_id"]) as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM presentation_revisions").fetchone()[0] == 1
            )
    finally:
        core.close()


def test_deck_review_tracks_inherited_purposes_stale_links_conflicts_and_undo(tmp_path: Path):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, evidence = setup(core, tmp_path)
        saved = save_claim(core, scope, target, evidence)
        call(
            core,
            "presentation.workspace.save_slide_purpose",
            {**scope, "purpose": "recommendation"},
        )
        original = scope["revision_id"]
        scope["revision_id"] = change(core, scope, target)["revision_id"]
        item = review(core, scope)["items"][0]
        assert item["purpose"] == "recommendation" and item["purpose_status"] == "needs_review"
        assert item["purpose_source_revision_id"] == original
        assert set(item["attention_reasons"]) == {"purpose_inherited", "claim_needs_review"}
        call(
            core,
            "presentation.workspace.save_slide_purpose",
            {**scope, "purpose": "recommendation"},
        )
        targets = call(
            core,
            "presentation.workspace.list_text_targets",
            {**scope_only(scope), "slide_number": 1},
        )
        updated = targets["targets"][0]
        call(
            core,
            "presentation.workspace.save_claim",
            {
                **scope,
                "claim_id": saved["claim_id"],
                "object_id": updated["object_id"],
                "quote": updated["decision_text"],
                "confirm": True,
                "evidence": [
                    {
                        "chunk_id": evidence["chunk_id"],
                        "sha256": evidence["sha256"],
                        "relation": "contradicts",
                    }
                ],
            },
        )
        item = review(core, scope)["items"][0]
        assert item["claim_counts"]["conflicting"] == 1
        assert item["attention_reasons"] == ["conflicting_evidence"]
        with core._storage.project_database(scope["project_id"]) as connection:
            connection.execute(
                "UPDATE chunks SET text='Changed excerpt' WHERE id=?", (evidence["chunk_id"],)
            )
            connection.commit()
        assert review(core, scope)["items"][0]["claim_counts"]["needs_review"] == 1
        call(
            core,
            "presentation.workspace.remove_claim",
            {**scope, "claim_id": saved["claim_id"], "confirm": True},
        )
        assert review(core, scope)["items"][0]["claim_count"] == 0
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
        item = review(core, scope)["items"][0]
        assert item["purpose_status"] == "reviewed" and item["claim_count"] == 1
        assert item["claim_counts"]["needs_review"] == 1
    finally:
        core.close()


@pytest.mark.parametrize(
    "failure", ["foreign", "stale", "changed_snapshot", "invalid_offset", "bool_limit", "unknown"]
)
def test_invalid_deck_review_fails_before_any_result(tmp_path: Path, failure):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, _ = setup(core, tmp_path)
        payload = scope_only(scope)
        if failure == "foreign":
            payload["project_id"] = call(core, "project.create", {"name": "Other"})["project"]["id"]
        if failure == "stale":
            change(core, scope, target)
        if failure == "changed_snapshot":
            record = core._presentation_edits._current_revision_source(
                scope["project_id"], scope["document_id"]
            )
            path = core._storage.paths.snapshot_path(
                scope["project_id"], record["local_snapshot_path"], require_exists=True
            )
            path.write_bytes(path.read_bytes() + b"changed")
        if failure == "invalid_offset":
            payload["offset"] = -1
        if failure == "bool_limit":
            payload["limit"] = True
        if failure == "unknown":
            payload["path"] = "arbitrary.pptx"
        error = call(core, "presentation.workspace.review_deck_semantics", payload, ok=False)
        assert error["code"] in {
            "SOURCE_NOT_FOUND",
            "PRESENTATION_REVISION_CONFLICT",
            "SOURCE_SNAPSHOT_CHANGED",
            "INVALID_REQUEST",
        }
    finally:
        core.close()


def test_deck_change_during_page_review_invalidates_the_page(tmp_path: Path, monkeypatch):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        scope, target, _ = setup(core, tmp_path)
        read = PresentationClaimService._list_claims
        changed = False

        def mutate(self, *args, **kwargs):
            nonlocal changed
            value = read(self, *args, **kwargs)
            if not changed:
                changed = True
                change(core, scope, target)
            return value

        monkeypatch.setattr(PresentationClaimService, "_list_claims", mutate)
        error = call(
            core, "presentation.workspace.review_deck_semantics", scope_only(scope), ok=False
        )
        assert error["code"] == "PRESENTATION_REVISION_CONFLICT"
    finally:
        core.close()
