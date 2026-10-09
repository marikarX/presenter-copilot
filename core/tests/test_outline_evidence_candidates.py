"""Outline citations remain read-only, native-bound review suggestions."""

import json
from pathlib import Path

import pytest
from test_outline_evidence_receipt import setup
from test_presentation_planning import call

METHOD = "presentation.workspace.list_outline_evidence_candidates"


def create(core, payload):
    document = call(core, "presentation.workspace.create_from_outline", payload)["document"]["id"]
    source = core._presentation_edits._current_revision_source(payload["project_id"], document)
    return {
        "project_id": payload["project_id"],
        "document_id": document,
        "revision_id": source["revision_id"],
    }


@pytest.mark.parametrize("layout", ["points", "columns", "cards", "statement"])
def test_native_points_current_sources_paging_and_no_writes(tmp_path: Path, layout):
    core, proposal, payload = setup(tmp_path)
    try:
        for slide in payload["slides"]:
            slide["layout"] = layout
            slide["bullets"] = ["Same exact reviewed point"] * (1 if layout == "statement" else 2)
            slide["evidence_ids"] = list(payload["slides"][0]["evidence_ids"])
        scope = create(core, payload)
        result = call(core, METHOD, {**scope, "limit": 1})
        assert result["has_receipt"] and result["has_more"]
        assert result["provider_run_id"] == proposal["provider_run_id"]
        assert result["total_points"] == (3 if layout == "statement" else 6)
        first = result["items"][0]
        assert first["span_status"] == "unchanged" and first["reviewable"]
        reference = first["references"][0]
        assert reference["source_status"] == "available"
        assert reference["excerpt_comparison"] == "excerpt_matches"
        assert reference["current_evidence"]["relation"] == "context"
        second = call(core, METHOD, {**scope, "offset": 1, "limit": 1})["items"][0]
        assert second["object_id"] != first["object_id"]
        with core._storage.project_database(scope["project_id"]) as connection:
            assert connection.execute("SELECT COUNT(*) FROM presentation_claims").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 1
        call(core, "source.reindex", {k: scope[k] for k in ("project_id", "document_id")})
        assert call(core, METHOD, {**scope, "limit": 1}) == result
    finally:
        core.close()


def test_native_reorder_edit_delete_undo_and_stale_head(tmp_path: Path):
    from test_selection_actions import save

    core, _, payload = setup(tmp_path)
    try:
        scope = create(core, payload)
        original_revision = scope["revision_id"]
        original = call(core, METHOD, scope)["items"][0]
        _, _, _, inventory = core._presentation_workspace_sources.read_revision_inventory(scope)
        slide_ids = [s.slide_id for s in inventory.slides]
        edits = {
            **{k: scope[k] for k in ("project_id", "document_id")},
            "expected_revision_id": scope["revision_id"],
        }

        def apply(operations):
            prepared = core._presentation_edit_plans.prepare(
                {**edits, "summary": "Review outline provenance", "operations": operations}
            )
            save(core, edits, prepared)
            scope["revision_id"] = edits["expected_revision_id"]

        apply(
            [{"type": "reorder_slides", "params": {"ordered_slide_ids": list(reversed(slide_ids))}}]
        )
        reordered = call(core, METHOD, scope)["items"][0]
        assert reordered["object_id"] == original["object_id"]
        assert reordered["slide_id"] == original["slide_id"]
        assert reordered["slide_number"] == 3 and reordered["reviewable"]
        assert not call(core, METHOD, {**scope, "revision_id": original_revision}, ok=False).get(
            "items"
        )
        apply(
            [
                {
                    "type": "replace_text_shape",
                    "params": {
                        "operation_type": "replace_text_shape",
                        "slide_id": reordered["slide_id"],
                        "object_id": reordered["object_id"],
                        "expected_text": reordered["quote"],
                        "replacement_text": "The author changed this point",
                    },
                }
            ]
        )
        changed = call(core, METHOD, scope)["items"][0]
        assert changed["span_status"] == "changed" and not changed["reviewable"]
        target_inventory = call(
            core,
            "presentation.workspace.list_text_targets",
            {
                **scope,
                "slide_number": 3,
            },
        )
        target = next(
            o for o in target_inventory["objects"] if o["object_id"] == original["object_id"]
        )
        apply(
            [
                {
                    "type": "delete_object",
                    "params": {
                        "slide_id": original["slide_id"],
                        "object_id": original["object_id"],
                        "expected_geometry": target["geometry"],
                    },
                }
            ]
        )
        missing = call(core, METHOD, scope)["items"][0]
        assert missing["span_status"] == "missing" and not missing["reviewable"]
        for expected in ("changed", "unchanged"):
            stepped = call(
                core, "presentation.workspace.step_revision", {**edits, "direction": "undo"}
            )
            edits["expected_revision_id"] = scope["revision_id"] = stepped["revision_id"]
            assert call(core, METHOD, scope)["items"][0]["span_status"] == expected
    finally:
        core.close()


@pytest.mark.parametrize("state", ["changed", "missing", "too_long"])
def test_current_source_changes_are_disclosed_without_upgrading_relation(tmp_path: Path, state):
    core, _, payload = setup(tmp_path)
    try:
        scope = create(core, payload)
        reference = call(core, METHOD, scope)["items"][0]["references"][0]
        key = reference["evidence_id"]
        with core._storage.project_database(scope["project_id"]) as connection:
            if state == "missing":
                connection.execute("DELETE FROM chunks WHERE id=?", (key,))
            else:
                connection.execute(
                    "UPDATE chunks SET text=? WHERE id=?",
                    ("Different current source" if state == "changed" else "x" * 8001, key),
                )
            connection.commit()
        changed = call(core, METHOD, scope)["items"][0]["references"][0]
        assert changed["original_excerpt"] == reference["original_excerpt"]
        assert changed["source_status"] == ("available" if state == "changed" else state)
        assert changed["excerpt_comparison"] == (
            "not_comparable" if state == "missing" else "excerpt_changed"
        )
        assert changed["can_link"] == (state == "changed")
        if changed["can_link"]:
            assert changed["current_evidence"]["relation"] == "context"
            assert changed["current_evidence"]["sha256"] != reference["current_evidence"]["sha256"]
    finally:
        core.close()


@pytest.mark.parametrize("bad", ["sha", "unknown_id", "slide_number", "version", "metadata"])
def test_corrupt_receipt_cannot_supply_authority(tmp_path: Path, bad):
    core, _, payload = setup(tmp_path)
    try:
        scope = create(core, payload)
        with core._storage.project_database(scope["project_id"]) as connection:
            metadata = json.loads(
                connection.execute(
                    "SELECT metadata_json FROM documents WHERE id=?", (scope["document_id"],)
                ).fetchone()[0]
            )
            receipt = metadata["outline_evidence_receipt"]
            if bad == "sha":
                receipt["original_sha256"] = "0" * 64
            elif bad == "unknown_id":
                receipt["slides"][0]["evidence_ids"] = ["forged"]
            elif bad == "slide_number":
                receipt["slides"][0]["slide_number"] = 1.0
            elif bad == "version":
                receipt["version"] = True
            connection.execute(
                "UPDATE documents SET metadata_json=? WHERE id=?",
                ("[]" if bad == "metadata" else json.dumps(metadata), scope["document_id"]),
            )
            connection.commit()
        assert call(core, METHOD, scope, ok=False)["code"] == "INVALID_REQUEST"
    finally:
        core.close()


def test_missing_planning_record_discloses_provenance_without_links(tmp_path: Path):
    core, proposal, payload = setup(tmp_path)
    try:
        scope = create(core, payload)
        with core._storage.project_database(scope["project_id"]) as connection:
            connection.execute(
                "DELETE FROM presentation_outline_proposals WHERE provider_run_id=?",
                (proposal["provider_run_id"],),
            )
            connection.commit()
        result = call(core, METHOD, scope)
        assert not result["planning_record_available"]
        reference = result["items"][0]["references"][0]
        assert reference["source_status"] == "planning_record_missing"
        assert not reference["can_link"] and reference["current_evidence"] is None
    finally:
        core.close()


@pytest.mark.parametrize(
    "bad", [{"limit": True}, {"limit": 21}, {"offset": -1}, {"offset": 321}, {"confirm": True}]
)
def test_reader_bounds_and_unknown_fields(tmp_path: Path, bad):
    core, _, payload = setup(tmp_path)
    try:
        scope = create(core, payload)
        assert call(core, METHOD, {**scope, **bad}, ok=False)["code"] == "INVALID_REQUEST"
    finally:
        core.close()


def test_speaker_memory_is_not_a_chunk_link_and_other_project_is_rejected(tmp_path: Path):
    core, proposal, payload = setup(tmp_path)
    try:
        scope = create(core, payload)
        with core._storage.project_database(scope["project_id"]) as connection:
            captured = json.loads(
                connection.execute(
                    "SELECT proposal_json FROM presentation_outline_proposals "
                    "WHERE provider_run_id=?",
                    (proposal["provider_run_id"],),
                ).fetchone()[0]
            )
            for item in captured["evidence"]:
                item["source_type"] = "user_statement"
            connection.execute(
                "UPDATE presentation_outline_proposals SET proposal_json=? WHERE provider_run_id=?",
                (json.dumps(captured), proposal["provider_run_id"]),
            )
            connection.commit()
        reference = call(core, METHOD, scope)["items"][0]["references"][0]
        assert reference["source_status"] == "not_linkable" and not reference["can_link"]
        assert reference["current_evidence"] is None
        other = call(core, "project.create", {"name": "Another project"})["project"]["id"]
        error = call(core, METHOD, {**scope, "project_id": other}, ok=False)
        assert "items" not in error
    finally:
        core.close()


def test_no_receipt_is_empty_but_still_checks_head(tmp_path: Path, monkeypatch):
    from presenter_core.errors import invalid_request

    core, _, payload = setup(tmp_path)
    try:
        for slide in payload["slides"]:
            slide.pop("evidence_ids")
        scope = create(core, payload)
        result = call(core, METHOD, scope)
        assert not result["has_receipt"] and not result["items"]
        original = core._presentation_semantics._require_current_presentation
        checked = []

        def guard(*args):
            checked.append(True)
            raise invalid_request("Injected head change after native read")

        monkeypatch.setattr(core._presentation_semantics, "_require_current_presentation", guard)
        assert call(core, METHOD, scope, ok=False)["code"] == "INVALID_REQUEST"
        assert checked
        monkeypatch.setattr(core._presentation_semantics, "_require_current_presentation", original)
    finally:
        core.close()
