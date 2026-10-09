"""Creation citation receipts are source-bound suggestions, never approved claim links."""

import copy
import json
from pathlib import Path

import pytest
from test_presentation_planning import CitationProvider, call, context

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter


def setup(tmp_path: Path):
    core = CoreService(
        data_root=tmp_path / "data",
        reasoning_provider=CitationProvider(locality="local"),
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=2),
    )
    project, params = context(core)
    source = tmp_path / "Pilot.md"
    source.write_text("# Pilot rationale\nThe pilot measures decision quality after thirty days.")
    call(core, "source.import", {"project_id": project, "kind": "supporting", "path": str(source)})
    proposal = call(core, "presentation.workspace.propose_outline", params)
    payload = {
        "project_id": project,
        "title": proposal["title"],
        "provider_run_id": proposal["provider_run_id"],
        "slides": [
            {k: slide[k] for k in ("title", "bullets", "notes", "evidence_ids")}
            for slide in proposal["slides"]
        ],
    }
    return core, proposal, payload


@pytest.mark.parametrize("layout", ["points", "columns", "cards", "statement"])
def test_receipt_follows_reviewed_points_and_reindex_without_saving_claims(
    tmp_path: Path, layout: str
):
    core, proposal, payload = setup(tmp_path)
    try:
        for slide in payload["slides"]:
            slide["layout"] = layout
            if layout == "statement":
                slide["bullets"] = slide["bullets"][:1]
        payload["slides"][0]["bullets"][0] = "Manually reviewed pilot point"
        created = call(core, "presentation.workspace.create_from_outline", payload)
        document = created["document"]["id"]
        project = payload["project_id"]
        with core._storage.project_database(project) as connection:
            metadata = json.loads(
                connection.execute(
                    "SELECT metadata_json FROM documents WHERE id=?", (document,)
                ).fetchone()[0]
            )
            original = connection.execute(
                "SELECT id,sha256 FROM presentation_revisions WHERE presentation_id=?", (document,)
            ).fetchone()
            assert connection.execute("SELECT COUNT(*) FROM presentation_claims").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 1
        receipt = metadata["outline_evidence_receipt"]
        assert receipt["original_revision_id"] == original["id"]
        assert receipt["original_sha256"] == original["sha256"]
        assert receipt["provider_run_id"] == proposal["provider_run_id"]
        assert receipt["slides"][0]["points"][0] == "Manually reviewed pilot point"
        assert receipt["slides"][0]["evidence_ids"] == proposal["slides"][0]["evidence_ids"]
        call(core, "source.reindex", {"project_id": project, "document_id": document})
        with core._storage.project_database(project) as connection:
            after = json.loads(
                connection.execute(
                    "SELECT metadata_json FROM documents WHERE id=?", (document,)
                ).fetchone()[0]
            )
        assert after["outline_evidence_receipt"] == receipt
    finally:
        core.close()


@pytest.mark.parametrize(
    "bad", ["no_run", "unknown", "duplicate", "too_many", "wrong_type", "other_project"]
)
def test_invalid_citation_authority_rejected_before_creation(tmp_path: Path, bad: str):
    core, _, payload = setup(tmp_path)
    try:
        references = payload["slides"][0]["evidence_ids"]
        if bad == "no_run":
            payload.pop("provider_run_id")
        elif bad == "unknown":
            references[:] = ["not-supplied"]
        elif bad == "duplicate":
            references.append(references[0])
        elif bad == "too_many":
            references[:] = [str(i) for i in range(9)]
        elif bad == "wrong_type":
            references[:] = [True]
        else:
            payload["project_id"] = call(core, "project.create", {"name": "Other project"})[
                "project"
            ]["id"]
        assert (
            call(core, "presentation.workspace.create_from_outline", payload, ok=False)["code"]
            == "INVALID_REQUEST"
        )
        assert not [
            d
            for d in call(core, "source.list", {"project_id": payload["project_id"]})["sources"]
            if d["kind"] == "presentation"
        ]
    finally:
        core.close()


def test_receipt_initialization_failure_rolls_back_native_registration_and_snapshot(
    tmp_path: Path, monkeypatch
):
    core, _, payload = setup(tmp_path)
    try:
        directory = core._storage.paths.safe_sources_directory(payload["project_id"])
        before = {p.name for p in directory.iterdir()}
        original = core._presentation_creation._record_evidence_receipt

        def fail(*args):
            original(*args)
            raise CoreDomainError("TEST_RECEIPT_FAILED", "Injected receipt failure")

        monkeypatch.setattr(core._presentation_creation, "_record_evidence_receipt", fail)
        assert (
            call(core, "presentation.workspace.create_from_outline", payload, ok=False)["code"]
            == "TEST_RECEIPT_FAILED"
        )
        assert {p.name for p in directory.iterdir()} == before
        with core._storage.project_database(payload["project_id"]) as connection:
            assert connection.execute("SELECT COUNT(*) FROM presentations").fetchone()[0] == 0
            assert (
                connection.execute("SELECT COUNT(*) FROM presentation_revisions").fetchone()[0] == 0
            )
        monkeypatch.setattr(core._presentation_creation, "_record_evidence_receipt", original)
        assert (
            call(core, "presentation.workspace.create_from_outline", copy.deepcopy(payload))[
                "status"
            ]
            == "ready"
        )
    finally:
        core.close()
