"""Durable outline drafts preserve branch snapshots, provenance and write ownership."""

from __future__ import annotations

import copy
import uuid
from pathlib import Path
from typing import Any

import pytest

from presenter_core.ipc.core import CoreService
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def call(core: CoreService, action: str, params: dict[str, Any], *, ok: bool = True) -> Any:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": action,
            "params": params,
        }
    )
    assert response["ok"] is ok, response
    return response["result" if ok else "error"]


def service(root: Path) -> CoreService:
    return CoreService(
        data_root=root,
        reasoning_provider=DeterministicFakeReasoningProvider(locality="local"),
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )


def setup(core: CoreService) -> tuple[str, dict[str, Any]]:
    project = call(
        core, "project.create", {"name": "Saved planning", "privacy_mode": "local_only"}
    )["project"]["id"]
    fields = {
        "objective": "Approve a pilot",
        "audience": "Decision owners",
        "briefing": "Review rationale and evidence.",
        "slide_count": 3,
        "instruction": "Plan a clear narrative for this presentation.",
    }
    response = call(
        core, "presentation.workspace.propose_outline", {"project_id": project, **fields}
    )
    turn = {
        "ordinal": 1,
        "request": copy.deepcopy(fields),
        "parentRunId": None,
        "baseline": None,
        "original": response,
        "draft": copy.deepcopy(response),
    }
    return project, {
        "fields": fields,
        "conversation": {"turns": [turn], "activeRunId": response["provider_run_id"]},
    }


def save(
    core: CoreService,
    project: str,
    payload: dict[str, Any],
    token: str | None = None,
    *,
    ok: bool = True,
) -> Any:
    return call(
        core,
        "presentation.workspace.save_outline_session",
        {"project_id": project, "expected_record_token": token, "payload": payload},
        ok=ok,
    )


def test_restart_restores_exact_manual_draft_without_provider_or_deck(tmp_path: Path) -> None:
    root = tmp_path / "data"
    core = service(root)
    project, payload = setup(core)
    payload["conversation"]["turns"][0]["draft"]["title"] = "  My exact local title  "
    payload["fields"]["instruction"] = "Unsent refinement"
    saved = save(core, project, payload)
    core.close()
    core = service(root)
    try:
        restored = call(core, "presentation.workspace.get_outline_session", {"project_id": project})
        assert restored == saved
        assert call(core, "source.list", {"project_id": project})["sources"] == []
        with core._storage.project_database(project) as connection:
            assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 1
    finally:
        core.close()


def test_branch_baseline_survives_later_ancestor_edits(tmp_path: Path) -> None:
    core = service(tmp_path / "data")
    try:
        project, payload = setup(core)
        turns = payload["conversation"]["turns"]
        parent = turns[0]
        parent["draft"]["title"] = "Edited before refinement"
        baseline = copy.deepcopy(parent["draft"])
        fields = {**payload["fields"], "instruction": "Put the decision first."}
        response = call(
            core,
            "presentation.workspace.propose_outline",
            {
                "project_id": project,
                **fields,
                "prior_outline": {key: baseline[key] for key in ("title", "rationale", "slides")},
            },
        )
        turns.append(
            {
                "ordinal": 2,
                "request": fields,
                "parentRunId": parent["original"]["provider_run_id"],
                "baseline": baseline,
                "original": response,
                "draft": copy.deepcopy(response),
            }
        )
        parent["draft"]["title"] = "Edited after refinement"
        payload["conversation"]["activeRunId"] = response["provider_run_id"]
        assert save(core, project, payload)["payload"] == payload
        turns[1]["baseline"]["title"] = "Invented request baseline"
        assert (
            save(core, project, payload, ok=False)["code"]
            == "PRESENTATION_OUTLINE_SESSION_CONFLICT"
        )
        token = call(core, "presentation.workspace.get_outline_session", {"project_id": project})[
            "record_token"
        ]
        assert save(core, project, payload, token, ok=False)["code"] == "INVALID_REQUEST"
    finally:
        core.close()


@pytest.mark.parametrize(
    "change", ["original", "request", "evidence", "branch", "ordinal", "active", "foreign"]
)
def test_rejects_fabricated_provenance_without_saving(tmp_path: Path, change: str) -> None:
    core = service(tmp_path / "data")
    try:
        project, payload = setup(core)
        turn = payload["conversation"]["turns"][0]
        if change == "original":
            turn["original"]["title"] = "Fake original"
        if change == "request":
            turn["request"]["objective"] = "Another objective"
        if change == "evidence":
            turn["draft"]["slides"][0]["evidence_ids"] = ["invented"]
        if change == "branch":
            turn["parentRunId"] = str(uuid.uuid4())
        if change == "ordinal":
            turn["ordinal"] = True
        if change == "active":
            payload["conversation"]["activeRunId"] = []
        if change == "foreign":
            project = setup(core)[0]
        assert save(core, project, payload, ok=False)["code"] == "INVALID_REQUEST"
        assert (
            call(core, "presentation.workspace.get_outline_session", {"project_id": project})[
                "payload"
            ]
            is None
        )
    finally:
        core.close()


def test_conflicts_and_clear_keep_token_to_prevent_aba(tmp_path: Path) -> None:
    core = service(tmp_path / "data")
    try:
        project, payload = setup(core)
        saved = save(core, project, payload)
        assert (
            save(core, project, payload, ok=False)["code"]
            == "PRESENTATION_OUTLINE_SESSION_CONFLICT"
        )
        cleared = call(
            core,
            "presentation.workspace.clear_outline_session",
            {"project_id": project, "expected_record_token": saved["record_token"]},
        )
        assert cleared["payload"] is None
        assert cleared["record_token"] != saved["record_token"]
        assert (
            save(core, project, payload, saved["record_token"], ok=False)["code"]
            == "PRESENTATION_OUTLINE_SESSION_CONFLICT"
        )
        assert (
            save(core, project, payload, ok=False)["code"]
            == "PRESENTATION_OUTLINE_SESSION_CONFLICT"
        )
        assert save(core, project, payload, cleared["record_token"])["payload"] == payload
    finally:
        core.close()
