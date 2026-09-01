from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

import pytest

from presenter_core.errors import CoreDomainError
from presenter_core.ingestion import security as ingestion_security
from presenter_core.ingestion import service as ingestion_service_module
from presenter_core.ingestion.chunking import MAX_CHUNK_CHARACTERS, chunk_text
from presenter_core.ingestion.models import Evidence, ParsedSourceUnit
from presenter_core.ingestion.parsers.pdf import PdfParser
from presenter_core.ingestion.parsers.pptx import PptxParser
from presenter_core.ingestion.parsers.text import TextParser
from presenter_core.ingestion.service import IngestionService, provenance_label
from presenter_core.ipc.core import CoreService
from presenter_core.storage.paths import AppPaths

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
    response = call(core, "create", "project.create", {"name": "Synthetic M1"})
    assert response["ok"] is True
    return response["result"]["project"]["id"]


def import_source(
    core: CoreService, project_id: str, path: Path, kind: str = "supporting"
) -> dict[str, Any]:
    response = call(
        core,
        path.name,
        "source.import",
        {"project_id": project_id, "path": str(path.resolve()), "kind": kind},
    )
    assert response["ok"] is True, response
    return response["result"]


def test_parser_adapters_preserve_boundaries_titles_and_notes() -> None:
    slides = PptxParser().parse(FIXTURE_ROOT / "deck" / "presentation.pptx")
    pages = PdfParser().parse(FIXTURE_ROOT / "supporting" / "cost-model.pdf")
    sections = TextParser().parse(FIXTURE_ROOT / "supporting" / "architecture-notes.md")

    assert len(slides) == 22
    assert [slide.ordinal for slide in slides] == list(range(1, 23))
    assert slides[7].title == "Proposed solution cost"
    assert "$980,000" in slides[7].text
    assert "Briefing note for slide 8" in slides[7].metadata["notes"]
    assert "Briefing note for slide 8" in slides[7].search_text
    assert "cobalt lighthouse 731" in slides[11].search_text
    assert len(pages) == 4
    assert [page.ordinal for page in pages] == [1, 2, 3, 4]
    assert "Current solution 3-year cost: $1,200,000" in pages[1].text
    assert [section.title for section in sections] == [
        "Architecture notes",
        "Ownership",
        "Untrusted source text",
    ]
    assert '<script>alert("do not execute")</script>' in sections[2].text


def test_import_snapshot_preview_provenance_deduplication_and_lexical_search(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    core = CoreService(
        data_root=tmp_path / "data",
        event_sink=lambda event: events.append((event["event"], event["payload"])),
    )
    try:
        project_id = create_project(core)
        deck = import_source(
            core, project_id, FIXTURE_ROOT / "deck" / "presentation.pptx", "presentation"
        )
        pdf = import_source(core, project_id, FIXTURE_ROOT / "supporting" / "cost-model.pdf")
        markdown = import_source(
            core, project_id, FIXTURE_ROOT / "supporting" / "architecture-notes.md"
        )
        assert deck["source_units_count"] == 22
        assert pdf["source_units_count"] == 4
        assert markdown["source_units_count"] == 3

        source_list = call(core, "list", "source.list", {"project_id": project_id})
        sources = source_list["result"]["sources"]
        assert {source["original_name"] for source in sources} == {
            "presentation.pptx",
            "cost-model.pdf",
            "architecture-notes.md",
        }
        data_root_text = str((tmp_path / "data").resolve())
        assert data_root_text not in json.dumps(source_list)
        for source in sources:
            snapshot = source["snapshot_name"]
            assert snapshot.startswith(source["id"] + "-")
            assert "/" not in snapshot and "\\" not in snapshot
            assert (tmp_path / "data" / "projects" / project_id / "sources" / snapshot).is_file()

        deck_id = next(
            source["id"] for source in sources if source["original_name"] == "presentation.pptx"
        )
        deck_preview = call(
            core,
            "deck-preview",
            "source.preview",
            {"project_id": project_id, "document_id": deck_id, "offset": 7, "limit": 1},
        )["result"]
        assert deck_preview["total"] == 22
        assert deck_preview["units"][0]["ordinal"] == 8
        assert deck_preview["units"][0]["provenance"]["label"] == "presentation.pptx slide 8"
        assert "$980,000" in deck_preview["units"][0]["text"]
        assert "notes" in deck_preview["units"][0]["metadata"]

        pdf_id = next(
            source["id"] for source in sources if source["original_name"] == "cost-model.pdf"
        )
        pdf_preview = call(
            core,
            "pdf-preview",
            "source.preview",
            {"project_id": project_id, "document_id": pdf_id, "offset": 1, "limit": 1},
        )["result"]
        assert pdf_preview["units"][0]["provenance"]["label"] == "cost-model.pdf p.2"
        assert "Current solution 3-year cost" in pdf_preview["units"][0]["text"]

        md_id = next(
            source["id"] for source in sources if source["original_name"] == "architecture-notes.md"
        )
        markdown_preview = call(
            core,
            "markdown-preview",
            "source.preview",
            {"project_id": project_id, "document_id": md_id},
        )["result"]
        assert '<script>alert("do not execute")</script>' in markdown_preview["units"][2]["text"]
        assert (
            markdown_preview["units"][2]["provenance"]["label"] == "architecture-notes.md section 3"
        )

        duplicate = call(
            core,
            "duplicate",
            "source.import",
            {
                "project_id": project_id,
                "path": str((FIXTURE_ROOT / "deck" / "presentation.pptx").resolve()),
                "kind": "presentation",
            },
        )
        assert duplicate["error"]["code"] == "SOURCE_DUPLICATE"
        assert duplicate["error"]["details"]["duplicate"] is True
        assert duplicate["error"]["details"]["existing_document_id"] == deck_id

        exact = call(
            core,
            "search",
            "search.lexical",
            {"project_id": project_id, "query": "Target recovery time objective (RTO): 15 minutes"},
        )["result"]
        assert exact["results"][0]["label"] == "presentation.pptx slide 10"
        assert exact["results"][0]["fact_safe"] is True
        assert exact["latency_ms"] >= 0
        note_only = call(
            core,
            "note-search",
            "search.lexical",
            {"project_id": project_id, "query": "cobalt lighthouse 731"},
        )["result"]
        assert note_only["results"][0]["label"] == "presentation.pptx slide 12"
        assert "cobalt lighthouse 731" in note_only["results"][0]["text"]
        assert {name for name, _ in events} >= {
            "source.import_progress",
            "project.index_progress",
            "project.index_ready",
        }
        for name, payload in events:
            if name == "source.import_progress":
                assert set(payload) >= {
                    "project_id",
                    "document_id",
                    "stage",
                    "completed",
                    "total",
                    "status",
                }
                assert data_root_text not in json.dumps(payload)
                assert "text" not in payload
    finally:
        core.close()


def test_security_limits_malformed_sources_and_safe_text_handling(tmp_path: Path) -> None:
    core = CoreService(data_root=tmp_path / "data")
    try:
        project_id = create_project(core)
        unsafe = call(
            core,
            "unsafe",
            "source.import",
            {
                "project_id": project_id,
                "path": str((FIXTURE_ROOT / "security" / "unsafe-member.pptx").resolve()),
            },
        )
        assert unsafe["error"]["code"] == "SOURCE_ARCHIVE_UNSAFE"
        assert (
            call(core, "empty", "source.list", {"project_id": project_id})["result"]["sources"]
            == []
        )

        bad_pdf = tmp_path / "malformed.pdf"
        bad_pdf.write_bytes(b"%PDF-1.7\nnot a valid PDF")
        malformed = call(
            core,
            "malformed",
            "source.import",
            {"project_id": project_id, "path": str(bad_pdf.resolve())},
        )
        assert malformed["error"]["code"] == "SOURCE_PARSE_FAILED"
        failed_source = call(core, "failed-list", "source.list", {"project_id": project_id})[
            "result"
        ]["sources"]
        assert len(failed_source) == 1
        assert failed_source[0]["parse_status"] == "error"
        assert failed_source[0]["source_units_count"] == 0

        unsupported = tmp_path / "unsupported.docx"
        unsupported.write_bytes(b"not imported")
        rejected = call(
            core,
            "unsupported",
            "source.import",
            {"project_id": project_id, "path": str(unsupported.resolve())},
        )
        assert rejected["error"]["code"] == "SOURCE_TYPE_UNSUPPORTED"

        malicious_name = tmp_path / ".._.._unsafe-name.md"
        malicious_name.write_text("# Safe\n\n<script>alert('x')</script>", encoding="utf-8")
        imported = import_source(core, project_id, malicious_name)
        assert ".." not in imported["document"]["snapshot_name"]
        preview = call(
            core,
            "safe-preview",
            "source.preview",
            {"project_id": project_id, "document_id": imported["document"]["id"]},
        )["result"]
        assert "<script>alert('x')</script>" in preview["units"][0]["text"]
    finally:
        core.close()


def test_stored_snapshot_paths_cannot_traverse_the_vault(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    core = CoreService(data_root=data_root)
    try:
        project_id = create_project(core)
        paths = AppPaths(data_root)
        for unsafe in (
            "../outside.txt",
            "sources/../outside.txt",
            "sources/foo/../bar.txt",
            "C:/outside.txt",
            r"sources\..\outside.txt",
        ):
            with pytest.raises(CoreDomainError) as error:
                paths.snapshot_path(project_id, unsafe)
            assert error.value.code == "SOURCE_PATH_UNSAFE"
    finally:
        core.close()


def test_reindex_uses_snapshot_and_source_delete_cascades_then_survives_restart(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    external = tmp_path / "external.txt"
    external.write_text("Original snapshot text with recovery target 15 minutes.", encoding="utf-8")
    core = CoreService(data_root=data_root)
    project_id = create_project(core)
    imported = import_source(core, project_id, external)
    document_id = imported["document"]["id"]
    snapshot = (
        data_root / "projects" / project_id / "sources" / imported["document"]["snapshot_name"]
    )
    assert (
        snapshot.read_text(encoding="utf-8")
        == "Original snapshot text with recovery target 15 minutes."
    )
    external.write_text("Changed external file must not become authoritative.", encoding="utf-8")

    snapshot.unlink()
    missing_snapshot = call(
        core,
        "missing-snapshot",
        "source.reindex",
        {"project_id": project_id, "document_id": document_id},
    )
    assert missing_snapshot["error"]["code"] == "SOURCE_REINDEX_FAILED"
    snapshot.write_text("Original snapshot text with recovery target 15 minutes.", encoding="utf-8")

    reindexed = call(
        core,
        "reindex",
        "source.reindex",
        {"project_id": project_id, "document_id": document_id},
    )
    assert reindexed["ok"] is True
    preview = call(
        core,
        "after-reindex",
        "source.preview",
        {"project_id": project_id, "document_id": document_id},
    )["result"]
    assert "Original snapshot text" in preview["units"][0]["text"]
    assert "Changed external" not in preview["units"][0]["text"]
    deleted = call(
        core,
        "delete-source",
        "source.delete",
        {"project_id": project_id, "document_id": document_id},
    )
    assert deleted["result"]["deleted"] is True
    assert not snapshot.exists()
    project_database = sqlite3.connect(data_root / "projects" / project_id / "project.db")
    try:
        assert project_database.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        assert project_database.execute("SELECT COUNT(*) FROM source_units").fetchone()[0] == 0
        assert project_database.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
    finally:
        project_database.close()
    core.close()

    restarted = CoreService(data_root=data_root)
    try:
        assert (
            call(restarted, "sources", "source.list", {"project_id": project_id})["result"][
                "sources"
            ]
            == []
        )
        assert call(restarted, "project", "project.open", {"project_id": project_id})["ok"] is True
        assert (
            call(restarted, "delete-project", "project.delete", {"project_id": project_id})[
                "result"
            ]["deleted"]
            is True
        )
    finally:
        restarted.close()


def test_reindex_rejects_changed_snapshot_and_retains_previous_content(tmp_path: Path) -> None:
    external = tmp_path / "authoritative.txt"
    external.write_text("Original evidence phrase 482.", encoding="utf-8")
    data_root = tmp_path / "data"
    core = CoreService(data_root=data_root)
    try:
        project_id = create_project(core)
        imported = import_source(core, project_id, external)
        document_id = imported["document"]["id"]
        snapshot = (
            data_root / "projects" / project_id / "sources" / imported["document"]["snapshot_name"]
        )
        before_preview = call(
            core,
            "before-preview",
            "source.preview",
            {"project_id": project_id, "document_id": document_id},
        )["result"]
        with sqlite3.connect(data_root / "projects" / project_id / "project.db") as database:
            before_chunks = database.execute(
                "SELECT id, text FROM chunks ORDER BY chunk_index"
            ).fetchall()

        snapshot.write_text("Tampered evidence phrase 913.", encoding="utf-8")
        failed = call(
            core,
            "changed-snapshot",
            "source.reindex",
            {"project_id": project_id, "document_id": document_id},
        )
        assert failed["error"]["code"] == "SOURCE_REINDEX_FAILED"
        assert failed["error"]["details"]["cause_code"] == "SOURCE_SNAPSHOT_CHANGED"

        after_preview = call(
            core,
            "after-preview",
            "source.preview",
            {"project_id": project_id, "document_id": document_id},
        )["result"]
        assert after_preview["units"] == before_preview["units"]
        with sqlite3.connect(data_root / "projects" / project_id / "project.db") as database:
            after_chunks = database.execute(
                "SELECT id, text FROM chunks ORDER BY chunk_index"
            ).fetchall()
            stored_sha = database.execute(
                "SELECT sha256 FROM documents WHERE id = ?", (document_id,)
            ).fetchone()[0]
        assert after_chunks == before_chunks
        assert stored_sha == imported["document"]["sha256"]
    finally:
        core.close()


def test_unchanged_reindex_preserves_derived_ids_and_parser_metadata(tmp_path: Path) -> None:
    external = tmp_path / "stable.txt"
    external.write_text("Stable retrieval phrase 2718.", encoding="utf-8")
    data_root = tmp_path / "data"
    core = CoreService(data_root=data_root)
    try:
        project_id = create_project(core)
        imported = import_source(core, project_id, external)
        document_id = imported["document"]["id"]
        before_preview = call(
            core,
            "before-preview",
            "source.preview",
            {"project_id": project_id, "document_id": document_id},
        )["result"]
        before_search = call(
            core,
            "before-search",
            "search.lexical",
            {"project_id": project_id, "query": "Stable retrieval phrase 2718"},
        )["result"]["results"]
        with sqlite3.connect(data_root / "projects" / project_id / "project.db") as database:
            before_chunks = database.execute(
                "SELECT id, source_unit_id, chunk_index, text FROM chunks ORDER BY chunk_index"
            ).fetchall()
        reindexed = call(
            core,
            "stable-reindex",
            "source.reindex",
            {"project_id": project_id, "document_id": document_id},
        )
        assert reindexed["ok"] is True
        after_preview = call(
            core,
            "after-preview",
            "source.preview",
            {"project_id": project_id, "document_id": document_id},
        )["result"]
        after_search = call(
            core,
            "after-search",
            "search.lexical",
            {"project_id": project_id, "query": "Stable retrieval phrase 2718"},
        )["result"]["results"]
        with sqlite3.connect(data_root / "projects" / project_id / "project.db") as database:
            after_chunks = database.execute(
                "SELECT id, source_unit_id, chunk_index, text FROM chunks ORDER BY chunk_index"
            ).fetchall()
        assert [unit["id"] for unit in after_preview["units"]] == [
            unit["id"] for unit in before_preview["units"]
        ]
        assert [result["evidence_id"] for result in after_search] == [
            result["evidence_id"] for result in before_search
        ]
        assert [result["source_unit_id"] for result in after_search] == [
            result["source_unit_id"] for result in before_search
        ]
        assert after_chunks == before_chunks
        source = call(core, "source-list", "source.list", {"project_id": project_id})["result"][
            "sources"
        ][0]
        assert source["parser_id"] == "text.stdlib"
        assert source["metadata"]["parser"] == "text.stdlib"
    finally:
        core.close()


def test_reindex_records_the_parser_identity_actually_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "parser-version.txt"
    external.write_text("Parser version evidence.", encoding="utf-8")

    class ReplacementParser:
        parser_id = "text.stdlib.v2"

        def parse(self, _path: Path) -> list[ParsedSourceUnit]:
            return [
                ParsedSourceUnit(
                    unit_type="section",
                    ordinal=1,
                    title=None,
                    text="Parser version evidence.",
                    metadata={"parser": self.parser_id},
                )
            ]

    replacement = ReplacementParser()
    core = CoreService(data_root=tmp_path / "data")
    try:
        project_id = create_project(core)
        imported = import_source(core, project_id, external)
        document_id = imported["document"]["id"]
        assert imported["document"]["parser_id"] == "text.stdlib"
        monkeypatch.setattr(
            ingestion_service_module, "parser_for", lambda _source_type: replacement
        )
        reindexed = call(
            core,
            "parser-version-reindex",
            "source.reindex",
            {"project_id": project_id, "document_id": document_id},
        )
        assert reindexed["ok"] is True
        source = call(core, "parser-version-list", "source.list", {"project_id": project_id})[
            "result"
        ]["sources"][0]
        assert source["parser_id"] == replacement.parser_id
        assert source["metadata"]["parser"] == replacement.parser_id
    finally:
        core.close()


def test_import_preflights_the_copied_snapshot_before_parser_consumption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "preflight.txt"
    external.write_text("Copied snapshot is the parser subject.", encoding="utf-8")
    observed: list[Path] = []
    original_preflight = ingestion_service_module.preflight_source

    def recording_preflight(path: Path, source_type: str) -> int:
        observed.append(path)
        return original_preflight(path, source_type)

    monkeypatch.setattr(ingestion_service_module, "preflight_source", recording_preflight)
    core = CoreService(data_root=tmp_path / "data")
    try:
        project_id = create_project(core)
        imported = import_source(core, project_id, external)
        snapshot = (
            tmp_path
            / "data"
            / "projects"
            / project_id
            / "sources"
            / imported["document"]["snapshot_name"]
        ).resolve()
        assert snapshot in observed
    finally:
        core.close()


def test_parser_consumption_is_immediately_preflighted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = tmp_path / "authoritative.txt"
    snapshot.write_text("Parser subject.", encoding="utf-8")
    order: list[tuple[str, Path]] = []
    original_preflight = ingestion_service_module.preflight_source

    def recording_preflight(path: Path, source_type: str) -> int:
        order.append(("preflight", path))
        return original_preflight(path, source_type)

    class RecordingParser:
        parser_id = "test.parser"

        def parse(self, path: Path) -> list[Any]:
            order.append(("parse", path))
            return []

    monkeypatch.setattr(ingestion_service_module, "preflight_source", recording_preflight)
    core = CoreService(data_root=tmp_path / "data")
    try:
        core._ingestion._parse_snapshot(  # type: ignore[attr-defined]
            snapshot, "txt", parser=RecordingParser()
        )
        assert order == [("preflight", snapshot), ("parse", snapshot)]
    finally:
        core.close()


def test_speaker_notes_count_toward_extracted_text_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slide = PptxParser().parse(FIXTURE_ROOT / "deck" / "presentation.pptx")[11]
    assert slide.search_text is not None
    assert len(slide.search_text) > len(slide.text)
    core = CoreService(data_root=tmp_path / "data")
    try:
        monkeypatch.setattr(
            ingestion_service_module,
            "MAX_EXTRACTED_TEXT_CHARS",
            len(slide.text) + 1,
        )
        with pytest.raises(CoreDomainError) as error:
            core._ingestion._validate_parsed_units([slide])  # type: ignore[attr-defined]
        assert error.value.code == "SOURCE_PARSE_FAILED"
    finally:
        core.close()


def test_source_delete_failures_are_structured_retryable_and_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "delete.txt"
    external.write_text("Delete failure recovery.", encoding="utf-8")
    data_root = tmp_path / "data"
    core = CoreService(data_root=data_root)
    try:
        project_id = create_project(core)
        imported = import_source(core, project_id, external)
        document_id = imported["document"]["id"]
        snapshot = (
            data_root / "projects" / project_id / "sources" / imported["document"]["snapshot_name"]
        )

        def fail_database_delete(
            _service: IngestionService, _project_id: str, _document_id: str
        ) -> None:
            raise sqlite3.OperationalError("injected commit failure")

        with monkeypatch.context() as patch_context:
            patch_context.setattr(IngestionService, "_delete_document_record", fail_database_delete)
            failed = call(
                core,
                "delete-db-failure",
                "source.delete",
                {"project_id": project_id, "document_id": document_id},
            )
        assert failed["error"]["code"] == "SOURCE_DELETE_FAILED"
        assert failed["error"]["retryable"] is True
        assert not snapshot.exists()
        assert call(core, "after-db-failure", "source.list", {"project_id": project_id})["result"][
            "sources"
        ]
        assert (
            call(
                core,
                "delete-db-retry",
                "source.delete",
                {"project_id": project_id, "document_id": document_id},
            )["result"]["deleted"]
            is True
        )
    finally:
        core.close()


def test_source_delete_filesystem_failure_is_structured_and_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "delete-filesystem.txt"
    external.write_text("Filesystem failure recovery.", encoding="utf-8")
    core = CoreService(data_root=tmp_path / "data")
    try:
        project_id = create_project(core)
        imported = import_source(core, project_id, external)
        document_id = imported["document"]["id"]

        def fail_snapshot_remove(_path: Path) -> None:
            raise CoreDomainError("SOURCE_SNAPSHOT_FAILED", "injected snapshot failure")

        with monkeypatch.context() as patch_context:
            patch_context.setattr(
                ingestion_service_module, "_remove_snapshot", fail_snapshot_remove
            )
            failed = call(
                core,
                "delete-fs-failure",
                "source.delete",
                {"project_id": project_id, "document_id": document_id},
            )
        assert failed["error"]["code"] == "SOURCE_DELETE_FAILED"
        assert failed["error"]["retryable"] is True
        assert call(core, "after-fs-failure", "source.list", {"project_id": project_id})["result"][
            "sources"
        ]
        assert (
            call(
                core,
                "delete-fs-retry",
                "source.delete",
                {"project_id": project_id, "document_id": document_id},
            )["result"]["deleted"]
            is True
        )
    finally:
        core.close()


def test_pptx_archive_entry_and_expanded_size_limits_are_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    too_many = tmp_path / "too-many.pptx"
    with zipfile.ZipFile(too_many, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml", "<presentation/>")
    monkeypatch.setattr(ingestion_security, "MAX_ARCHIVE_ENTRIES", 1)
    with pytest.raises(CoreDomainError) as entry_error:
        ingestion_security.preflight_pptx_archive(too_many)
    assert entry_error.value.code == "SOURCE_ARCHIVE_UNSAFE"

    expanded = tmp_path / "too-large-expanded.pptx"
    with zipfile.ZipFile(expanded, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml", "<presentation/>")
        archive.writestr("ppt/large.xml", "0123456789")
    monkeypatch.setattr(ingestion_security, "MAX_ARCHIVE_ENTRIES", 2_048)
    monkeypatch.setattr(ingestion_security, "MAX_ARCHIVE_EXPANDED_BYTES", 5)
    with pytest.raises(CoreDomainError) as expanded_error:
        ingestion_security.preflight_pptx_archive(expanded)
    assert expanded_error.value.code == "SOURCE_ARCHIVE_UNSAFE"


def test_chunking_never_crosses_units_and_provenance_is_canonical() -> None:
    first = chunk_text("First paragraph. " + "alpha " * 500)
    second = chunk_text("Second paragraph. " + "beta " * 500)
    assert first and second
    assert all(len(chunk.text) <= MAX_CHUNK_CHARACTERS for chunk in first + second)
    assert [chunk.chunk_index for chunk in first] == list(range(len(first)))
    assert [chunk.chunk_index for chunk in second] == list(range(len(second)))
    assert provenance_label("Proposal.pptx", "slide", 7) == "Proposal.pptx slide 7"
    assert provenance_label("CostModel.pdf", "page", 4) == "CostModel.pdf p.4"
    evidence = Evidence("e", "document", "d", "u", "Architecture.md section 3", "fact")
    assert evidence.to_dict()["fact_safe"] is True
    assert evidence.provenance_ref().label == "Architecture.md section 3"


def test_same_filename_different_content_is_not_deduplicated(tmp_path: Path) -> None:
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first_directory.mkdir()
    second_directory.mkdir()
    first = first_directory / "brief.txt"
    second = second_directory / "brief.txt"
    first.write_text("First distinct content.", encoding="utf-8")
    second.write_text("Second distinct content.", encoding="utf-8")

    core = CoreService(data_root=tmp_path / "data")
    try:
        project_id = create_project(core)
        imported_first = import_source(core, project_id, first)
        imported_second = import_source(core, project_id, second)
        assert imported_first["document"]["id"] != imported_second["document"]["id"]
        assert {
            source["sha256"]
            for source in call(core, "list", "source.list", {"project_id": project_id})["result"][
                "sources"
            ]
        } == {imported_first["document"]["sha256"], imported_second["document"]["sha256"]}
    finally:
        core.close()
