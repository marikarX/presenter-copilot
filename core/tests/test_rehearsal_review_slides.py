"""Original Run slide paging stays independent of debriefs and editable objects."""

import uuid

import pytest
import test_rehearsal_coverage as coverage_tests
from test_presentation_planning import call

rehearsal = coverage_tests.rehearsal
METHOD = "presentation.workspace.list_rehearsal_review_slides"


def test_original_slide_selection_needs_no_debrief_and_preserves_stable_identity(rehearsal):
    core, scope = rehearsal
    with core._storage.project_database(scope["project_id"]) as db:
        db.execute("DELETE FROM run_debriefs WHERE session_id=?", (scope["session_id"],))
        db.commit()
    first = call(core, METHOD, scope | {"limit": 1})
    assert first["total"] == 3 and first["has_more"]
    assert first["slides"][0]["source_slide_number"] == 1
    assert "object_id" not in first["slides"][0]
    identities = [
        call(core, METHOD, scope | {"offset": index, "limit": 1})["slides"][0]["slide_id"]
        for index in range(3)
    ]
    reordered = call(
        core,
        "presentation.workspace.reorder_slides",
        {
            **{k: scope[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "ordered_slide_ids": identities[::-1],
        },
    )
    current = scope | {"expected_revision_id": reordered["revision_id"]}
    after = call(core, METHOD, current)
    assert [slide["slide_id"] for slide in after["slides"]] == identities
    assert [slide["current_slide_number"] for slide in after["slides"]] == [3, 2, 1]
    assert after["source_revision_id"] == scope["expected_revision_id"]
    deleted = call(
        core,
        "presentation.workspace.delete_slide",
        {
            **{k: current[k] for k in ("project_id", "document_id", "expected_revision_id")},
            "slide_id": identities[0],
        },
    )
    remaining = call(core, METHOD, scope | {"expected_revision_id": deleted["revision_id"]})
    assert remaining["total"] == 3 and remaining["slides"][0]["current_slide_number"] is None
    assert (
        call(core, METHOD, scope | {"expected_revision_id": deleted["revision_id"], "offset": 20})[
            "slides"
        ]
        == []
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"limit": 21},
        {"limit": 0},
        {"offset": -1},
        {"offset": True},
        {"session_id": str(uuid.uuid4())},
        {"document_id": str(uuid.uuid4())},
        {"expected_revision_id": str(uuid.uuid4())},
        {"quote": "caller text"},
    ],
)
def test_slide_selector_rejects_foreign_scope_or_invalid_paging(rehearsal, extra):
    core, scope = rehearsal
    call(core, METHOD, scope | extra, ok=False)
