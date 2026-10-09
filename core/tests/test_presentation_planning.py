"""Conversation outlines retain review, evidence, privacy, and creation boundaries."""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pptx import Presentation

from presenter_core.ipc.core import CoreService
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def call(core: CoreService, method: str, params: dict[str, Any], *, ok: bool = True) -> Any:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is ok, response
    return response["result" if ok else "error"]


class CitationProvider(DeterministicFakeReasoningProvider):
    fabricated = False

    def generate(self, invocation: Any) -> Any:
        result = super().generate(invocation)
        output = dict(result.output)
        evidence = invocation.request.evidence
        output["slides"][0]["evidence_ids"] = (
            ["invented-evidence-id"] if self.fabricated else [evidence[0]["evidence_id"]]
        )
        return replace(result, output=output)


def context(core: CoreService) -> tuple[str, dict[str, Any]]:
    project_id = call(
        core, "project.create", {"name": "Narrative plan", "privacy_mode": "local_only"}
    )["project"]["id"]
    params = {
        "project_id": project_id,
        "objective": "Approve a pilot",
        "audience": "Decision owners",
        "briefing": "Review the pilot rationale and supporting evidence.",
        "slide_count": 3,
    }
    return project_id, params


def test_outline_is_review_only_refinable_and_materializes_with_lineage(tmp_path: Path) -> None:
    provider = DeterministicFakeReasoningProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        project_id, params = context(core)
        first = call(core, "presentation.workspace.propose_outline", params)
        assert first["requires_user_review"] is True
        assert call(core, "source.list", {"project_id": project_id})["sources"] == []
        prior = {key: first[key] for key in ("title", "rationale", "slides")}
        refined = call(
            core,
            "presentation.workspace.propose_outline",
            {
                **params,
                "prior_outline": prior,
                "instruction": "Put the decision first.",
            },
        )
        request = provider.request_objects[-1]
        assert json.loads(request.current_slide_summary or "{}")["prior_outline"] == prior
        assert request.question == "Put the decision first."
        assert "prior_outline" not in request.question
        with core._storage.project_database(project_id) as connection:
            manifest = json.loads(
                connection.execute(
                    "SELECT context_manifest_json FROM provider_runs WHERE id = ?",
                    (refined["provider_run_id"],),
                ).fetchone()[0]
            )
        assert "current_slide_summary" in manifest["classes_sent"]
        assert params["briefing"] not in json.dumps(manifest)
        document = call(
            core,
            "presentation.workspace.create_from_outline",
            {
                "project_id": project_id,
                "title": refined["title"],
                "provider_run_id": refined["provider_run_id"],
                "slides": [
                    {key: slide[key] for key in ("title", "bullets", "notes")}
                    for slide in refined["slides"]
                ],
            },
        )["document"]
        with core._storage.project_database(project_id) as connection:
            snapshot = connection.execute(
                "SELECT local_snapshot_path FROM documents WHERE id = ?", (document["id"],)
            ).fetchone()[0]
        presentation = Presentation(
            str(core._storage.paths.snapshot_path(project_id, snapshot, require_exists=True))
        )
        assert len(presentation.slides) == 3
        assert refined["provider_run_id"] in presentation.core_properties.comments
        other_id = call(core, "project.create", {"name": "Other project"})["project"]["id"]
        error = call(
            core,
            "presentation.workspace.create_from_outline",
            {
                "project_id": other_id,
                "title": refined["title"],
                "provider_run_id": refined["provider_run_id"],
                "slides": [{"title": "Decision", "bullets": [], "notes": ""}],
            },
            ok=False,
        )
        assert error["code"] == "INVALID_REQUEST"
    finally:
        core.close()


def test_outline_citations_are_supplied_project_evidence(tmp_path: Path) -> None:
    provider = CitationProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        project_id, params = context(core)
        source = tmp_path / "Pilot.md"
        source.write_text(
            "# Pilot rationale\n"
            "The pilot measures decision quality with a review after thirty days.",
            encoding="utf-8",
        )
        document = call(
            core,
            "source.import",
            {"project_id": project_id, "kind": "supporting", "path": str(source)},
        )["document"]
        result = call(core, "presentation.workspace.propose_outline", params)
        cited = result["slides"][0]["evidence_ids"][0]
        assert any(item["evidence_id"] == cited for item in result["evidence"])
        with core._storage.project_database(project_id) as connection:
            manifest = json.loads(
                connection.execute(
                    "SELECT context_manifest_json FROM provider_runs WHERE id = ?",
                    (result["provider_run_id"],),
                ).fetchone()[0]
            )
        assert document["id"] in manifest["source_ids"]
        provider.fabricated = True
        assert (
            call(core, "presentation.workspace.propose_outline", params, ok=False)["code"]
            == "PROVIDER_MALFORMED_OUTPUT"
        )
        with core._storage.project_database(project_id) as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM provider_runs WHERE status = 'error'"
                ).fetchone()[0]
                == 1
            )
    finally:
        core.close()


@pytest.mark.parametrize("count", [True, 0, 41])
def test_outline_invalid_count_never_calls_provider(tmp_path: Path, count: Any) -> None:
    provider = DeterministicFakeReasoningProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        _project_id, params = context(core)
        assert (
            call(
                core,
                "presentation.workspace.propose_outline",
                {**params, "slide_count": count},
                ok=False,
            )["code"]
            == "INVALID_REQUEST"
        )
        assert provider.call_count == 0
    finally:
        core.close()


def test_outline_local_only_blocks_remote_before_retrieval_and_generation(tmp_path: Path) -> None:
    provider = DeterministicFakeReasoningProvider(locality="remote")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        _project_id, params = context(core)
        assert (
            call(core, "presentation.workspace.propose_outline", params, ok=False)["code"]
            == "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED"
        )
        assert provider.call_count == 0
    finally:
        core.close()


def test_outline_preserves_long_brief_and_complete_large_draft(tmp_path: Path) -> None:
    provider = DeterministicFakeReasoningProvider(locality="local")
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=provider,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    try:
        _project_id, params = context(core)
        briefing = "The audience needs to understand the decision and assumptions. " * 25
        first = call(
            core,
            "presentation.workspace.propose_outline",
            {
                **params,
                "briefing": briefing,
                "slide_count": 40,
            },
        )
        assert (
            json.loads(provider.request_objects[-1].user_input or "{}")["briefing"]
            == briefing.strip()
        )
        prior = {key: first[key] for key in ("title", "rationale", "slides")}
        for slide in prior["slides"]:
            slide["notes"] = ("Preserve the explanation and uncertainty. " * 10).strip()
        refined = call(
            core,
            "presentation.workspace.propose_outline",
            {
                **params,
                "briefing": briefing,
                "slide_count": 40,
                "prior_outline": prior,
                "instruction": "Keep every slide while improving the narrative.",
            },
        )
        assert len(refined["slides"]) == 40
        request = provider.request_objects[-1]
        assert len(request.serialized_input()) > 12_000
        assert json.loads(request.current_slide_summary or "{}")["prior_outline"] == prior
        for slide in prior["slides"]:
            slide["notes"] = "Too large to fit the full prior draft. " * 100
        error = call(
            core,
            "presentation.workspace.propose_outline",
            {
                **params,
                "slide_count": 40,
                "prior_outline": prior,
            },
            ok=False,
        )
        assert error["code"] == "PRESENTATION_PLAN_CONTEXT_TOO_LARGE"
        assert provider.call_count == 2
    finally:
        core.close()
