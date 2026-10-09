"""Reviewed selection operations publish atomically and expose new native identities."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from test_graphic_geometry import fixture
from test_object_paste import inventory
from test_presentation_native_layouts import path
from test_presentation_transactions import call, context

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def plan(core, params, action, slide_id, objects):
    return core._presentation_edit_plans.prepare(
        {
            **params,
            "summary": f"{action} selection",
            "operations": [
                {
                    "type": f"{action}_object",
                    "params": {
                        "slide_id": slide_id,
                        "object_id": o["object_id"],
                        "expected_geometry": o["geometry"],
                    },
                }
                for o in objects
            ],
        },
    )


def save(core, params, proposed):
    scope = {
        "project_id": params["project_id"],
        "document_id": params["document_id"],
        "plan_id": proposed["plan_id"],
    }
    call(core, "presentation.workspace.open_edit_plan_preview", scope)
    result = call(
        core,
        "presentation.workspace.apply_edit_plan",
        {
            **scope,
            "reviewed_sha256": proposed["sha256"],
            "confirm": True,
        },
    )
    params["expected_revision_id"] = result["revision_id"]
    assert hashlib.sha256(path(core, params).read_bytes()).hexdigest() == proposed["sha256"]
    return result


@pytest.mark.parametrize("kind", ["shapes", "chart", "table"])
def test_reviewed_duplicate_delete_selection_identity_and_history(tmp_path: Path, kind):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        if kind == "shapes":
            params, _ = context(core)
            first = inventory(core, params, 1)
            objects = [
                o for o in first["objects"] if o["delete_editable"] and o["geometry_editable"]
            ][:2]
            assert len(objects) == 2
        else:
            params, first, obj = fixture(core, tmp_path, kind)
            objects = [obj, obj]
        original = path(core, params).read_bytes()
        original_revision = params["expected_revision_id"]
        proposed = plan(core, params, "duplicate", first["slide_id"], objects)
        assert path(core, params).read_bytes() == original
        duplicated = save(core, params, proposed)
        ids = [o["created_object_id"] for o in duplicated["operations"]]
        assert len(set(ids)) == 2 and not set(ids).intersection(o["object_id"] for o in objects)
        fresh = inventory(core, params, 1)
        copies = [
            next(o for o in fresh["objects"] if o["object_id"] == identifier) for identifier in ids
        ]
        assert len(fresh["objects"]) == len(first["objects"]) + 2
        copied_bytes = path(core, params).read_bytes()
        duplicate_revision = params["expected_revision_id"]
        removed = save(core, params, plan(core, params, "delete", fresh["slide_id"], copies))
        assert len(removed["operations"]) == 2
        assert [o["object_id"] for o in inventory(core, params, 1)["objects"]] == [
            o["object_id"] for o in first["objects"]
        ]
        deletion_revision = params["expected_revision_id"]
        for direction, expected_revision, expected_bytes in [
            ("undo", duplicate_revision, copied_bytes),
            ("undo", original_revision, original),
            ("redo", duplicate_revision, copied_bytes),
        ]:
            stepped = call(
                core, "presentation.workspace.step_revision", {**params, "direction": direction}
            )
            assert stepped["revision_id"] == expected_revision
            params["expected_revision_id"] = stepped["revision_id"]
            assert path(core, params).read_bytes() == expected_bytes
        stepped = call(
            core, "presentation.workspace.step_revision", {**params, "direction": "redo"}
        )
        assert stepped["revision_id"] == deletion_revision
    finally:
        core.close()


@pytest.mark.parametrize("action", ["duplicate", "delete"])
@pytest.mark.parametrize("failure", ["cancel", "bad_second"])
def test_selection_cancel_and_late_failure_preserve_head(tmp_path: Path, action, failure):
    core = CoreService(
        data_root=tmp_path / "data", embedding_adapter=DeterministicEmbeddingAdapter(dimension=2)
    )
    try:
        params, _ = context(core)
        first = inventory(core, params, 1)
        objects = [o for o in first["objects"] if o["delete_editable"] and o["geometry_editable"]][
            :2
        ]
        assert len(objects) == 2
        original = path(core, params).read_bytes()
        if failure == "bad_second":
            objects[1] = {**objects[1], "geometry": {**objects[1]["geometry"], "x_emu": -1}}
            with pytest.raises(CoreDomainError):
                plan(core, params, action, first["slide_id"], objects)
        else:
            proposed = plan(core, params, action, first["slide_id"], objects)
            call(
                core,
                "presentation.workspace.reject_edit_plan",
                {
                    "project_id": params["project_id"],
                    "document_id": params["document_id"],
                    "plan_id": proposed["plan_id"],
                },
            )
        assert (
            core._presentation_edits._current_revision_source(
                params["project_id"], params["document_id"]
            )["revision_id"]
            == params["expected_revision_id"]
        )
        assert path(core, params).read_bytes() == original
        history = call(
            core,
            "presentation.workspace.list_revisions",
            {
                "project_id": params["project_id"],
                "document_id": params["document_id"],
            },
        )
        assert len(history["revisions"]) == 1
        assert not list(path(core, params).parent.glob(".edit-stage-*.pptx"))
        assert not list(path(core, params).parent.glob(".edit-plan-*.pptx"))
    finally:
        core.close()
