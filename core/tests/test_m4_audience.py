from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from presenter_core.audience.context import (
    MAX_AUDIENCE_CONTEXT_CHARS,
    MAX_CONTEXT_EVIDENCE_PER_OBSERVATION,
    MAX_CONTEXT_OBSERVATIONS_PER_PROFILE,
    MAX_CONTEXT_PROFILES,
)
from presenter_core.audience.extraction import extract_observable_patterns
from presenter_core.audience.models import (
    MAX_CANDIDATES_PER_PROFILE,
    MAX_EVIDENCE_PER_ITEM,
    MAX_EXTRACTION_SEGMENTS,
    MAX_OBSERVATIONS_PER_PROFILE,
    MAX_PROFILE_COUNT,
)
from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.project.service import utc_now
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter
from presenter_core.transcript.parsers import (
    NamedTextTranscriptParser,
    SrtParser,
    StructuredJsonTranscriptParser,
    WebVttParser,
)

FIXTURE_ROOT = Path(__file__).parents[2] / "samples" / "synthetic-deck"
VTT_FIXTURE = FIXTURE_ROOT / "transcript" / "PriorMeeting.vtt"


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


def create_project(core: CoreService, name: str = "M4 test") -> str:
    response = call(core, "create-project", "project.create", {"name": name})
    assert response["ok"] is True, response
    return str(response["result"]["project"]["id"])


def import_vtt(core: CoreService, project_id: str) -> dict[str, Any]:
    response = import_source(
        core,
        project_id,
        VTT_FIXTURE,
        kind="transcript",
        request_id="import-vtt",
    )
    assert response["ok"] is True, response
    return response["result"]


def import_source(
    core: CoreService,
    project_id: str,
    path: Path,
    *,
    kind: str | None,
    request_id: str,
) -> dict[str, Any]:
    params: dict[str, Any] = {"project_id": project_id, "path": str(path.resolve())}
    if kind is not None:
        params["kind"] = kind
    return call(core, request_id, "source.import", params)


def create_profile(core: CoreService, project_id: str, display_name: str) -> dict[str, Any]:
    response = call(
        core,
        f"profile-{display_name}",
        "audience.create",
        {
            "project_id": project_id,
            "display_name": display_name,
            "role": "CFO" if display_name == "Jane Smith" else "CTO",
            "organization": "ExampleCo",
            "user_notes": "User-supplied context only.",
        },
    )
    assert response["ok"] is True, response
    return response["result"]["profile"]


def list_speakers(core: CoreService, project_id: str) -> list[dict[str, Any]]:
    response = call(core, "list-speakers", "transcript.list_speakers", {"project_id": project_id})
    assert response["ok"] is True, response
    return response["result"]["speakers"]


def map_speaker(
    core: CoreService, project_id: str, document_id: str, label: str, profile_id: str
) -> None:
    response = call(
        core,
        f"map-{label}-{profile_id}",
        "transcript.map_speaker",
        {
            "project_id": project_id,
            "document_id": document_id,
            "native_speaker_label": label,
            "audience_profile_id": profile_id,
        },
    )
    assert response["ok"] is True, response


def extract(
    core: CoreService, project_id: str, profile_id: str, request_id: str = "extract"
) -> dict[str, Any]:
    response = call(
        core,
        request_id,
        "audience.extract_observations",
        {"project_id": project_id, "audience_profile_id": profile_id},
    )
    assert response["ok"] is True, response
    return response["result"]


def list_observations(core: CoreService, project_id: str) -> dict[str, Any]:
    response = call(
        core,
        "list-observations",
        "audience.list_observations",
        {"project_id": project_id},
    )
    assert response["ok"] is True, response
    return response["result"]


def seed_transcript_segments(
    core: CoreService, project_id: str, profile_id: str, counts: list[int]
) -> list[str]:
    document_ids: list[str] = []
    with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
        for document_index, segment_count in enumerate(counts):
            document_id = str(uuid.uuid4())
            document_ids.append(document_id)
            connection.execute(
                """
                INSERT INTO documents (
                    id, project_id, kind, original_name, local_snapshot_path, source_uri,
                    sha256, mime_type, parser_id, imported_at, parse_status, parse_error_code,
                    parse_error_message, byte_size, metadata_json
                ) VALUES (?, ?, 'transcript', ?, NULL, NULL, ?, 'text/plain',
                          'transcript.named-text', ?, 'ready', NULL, NULL, 0, '{}')
                """,
                (
                    document_id,
                    project_id,
                    f"synthetic-{document_index}.txt",
                    hashlib.sha256(document_id.encode("ascii")).hexdigest(),
                    utc_now(),
                ),
            )
            source_rows = []
            for ordinal in range(1, segment_count + 1):
                source_rows.append(
                    (
                        str(uuid.uuid4()),
                        document_id,
                        "transcript_segment",
                        ordinal,
                        None,
                        None,
                        None,
                        "Jane Smith",
                        f"What is the schedule for item {ordinal}?",
                        "{}",
                    )
                )
            connection.executemany(
                """
                INSERT INTO source_units (
                    id, document_id, unit_type, ordinal, title, start_ms, end_ms,
                    speaker_label, text, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                source_rows,
            )
            connection.execute(
                """
                INSERT INTO transcript_speaker_maps (
                    id, document_id, native_speaker_label, audience_profile_id,
                    mapped_by, created_at
                ) VALUES (?, ?, 'Jane Smith', ?, 'user', ?)
                """,
                (str(uuid.uuid4()), document_id, profile_id, utc_now()),
            )
        connection.commit()
    return document_ids


def test_transcript_adapters_preserve_metadata_and_reject_ambiguous_json(tmp_path: Path) -> None:
    vtt = WebVttParser().parse(VTT_FIXTURE)
    assert len(vtt) == 7
    assert vtt[0].start_ms == 1_000
    assert vtt[0].end_ms == 4_200
    assert vtt[0].speaker_label == "Jane Smith"
    assert vtt[0].text == "What is the status-quo cost?"
    assert "<v" not in vtt[0].text
    assert "upload all project files" in vtt[-1].text

    srt = SrtParser().parse(FIXTURE_ROOT / "transcript" / "equivalent.srt")
    assert len(srt) == 3
    assert srt[0].speaker_label == "Jane Smith"
    assert srt[0].start_ms == 1_000
    assert srt[2].speaker_label is None

    named = NamedTextTranscriptParser().parse(FIXTURE_ROOT / "transcript" / "equivalent.txt")
    assert len(named) == 3
    assert named[0].speaker_label == "Jane Smith"
    assert named[0].start_ms == 1_000
    assert named[2].speaker_label == "Conference Room"
    assert named[2].start_ms is None

    structured = StructuredJsonTranscriptParser().parse(
        FIXTURE_ROOT / "transcript" / "equivalent.json"
    )
    assert len(structured) == 3
    assert structured[2].speaker_label is None
    assert structured[2].start_ms is None

    styled = tmp_path / "styled.vtt"
    styled.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n"
        "<v Jane Smith><c.yellow><i>Plain text</i></c.yellow></v>\n",
        encoding="utf-8",
    )
    styled_unit = WebVttParser().parse(styled)[0]
    assert styled_unit.speaker_label == "Jane Smith"
    assert styled_unit.text == "Plain text"

    malformed = tmp_path / "malformed.json"
    malformed.write_text(json.dumps({"segments": [{"text": "x", "url": "https://x"}]}))
    with pytest.raises(CoreDomainError) as error:
        StructuredJsonTranscriptParser().parse(malformed)
    assert error.value.code == "SOURCE_PARSE_FAILED"


def test_transcript_ingestion_adapters_and_ordinary_txt_boundary(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
    )
    try:
        project_id = create_project(core, "M4 adapter boundary")
        transcript_paths = [
            FIXTURE_ROOT / "transcript" / "PriorMeeting.vtt",
            FIXTURE_ROOT / "transcript" / "equivalent.srt",
            FIXTURE_ROOT / "transcript" / "equivalent.txt",
            FIXTURE_ROOT / "transcript" / "equivalent.json",
        ]
        for index, path in enumerate(transcript_paths):
            result = import_source(
                core,
                project_id,
                path,
                kind="transcript",
                request_id=f"import-adapter-{index}",
            )
            assert result["ok"] is True, result
            document = result["result"]["document"]
            assert document["kind"] == "transcript"
            assert document["source_type"] == "transcript"
            assert document["parser_id"].startswith("transcript.")
            assert result["result"]["chunks_count"] >= 1

        supporting = import_source(
            core,
            project_id,
            FIXTURE_ROOT / "supporting" / "architecture-notes.md",
            kind=None,
            request_id="import-supporting",
        )
        assert supporting["ok"] is True, supporting
        supporting_document = supporting["result"]["document"]
        assert supporting_document["kind"] == "supporting"
        assert supporting_document["source_type"] == "markdown"

        ordinary_txt = tmp_path / "ordinary.txt"
        ordinary_txt.write_text("Jane Smith: ordinary supporting text", encoding="utf-8")
        ordinary = import_source(
            core,
            project_id,
            ordinary_txt,
            kind=None,
            request_id="import-ordinary-txt",
        )
        assert ordinary["ok"] is True, ordinary
        ordinary_document = ordinary["result"]["document"]
        assert ordinary_document["kind"] == "supporting"
        assert ordinary_document["source_type"] == "txt"
        preview = call(
            core,
            "ordinary-preview",
            "source.preview",
            {
                "project_id": project_id,
                "document_id": ordinary_document["id"],
                "limit": 5,
            },
        )
        assert preview["ok"] is True, preview
        assert preview["result"]["units"][0]["speaker_label"] is None
        assert preview["result"]["units"][0]["start_ms"] is None
    finally:
        core.close()


def test_transcript_vertical_slice_maps_extracts_reviews_restarts_and_retrieves(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    adapter = DeterministicEmbeddingAdapter(dimension=4)
    core = CoreService(data_root=data_root, embedding_adapter=adapter)
    project_id = create_project(core)
    imported = import_vtt(core, project_id)
    document = imported["document"]
    document_id = str(document["id"])
    assert document["kind"] == "transcript"
    assert document["source_type"] == "transcript"
    assert document["parser_id"] == "transcript.vtt"
    assert imported["source_units_count"] == 7

    preview = call(
        core,
        "preview-vtt",
        "source.preview",
        {"project_id": project_id, "document_id": document_id, "offset": 0, "limit": 7},
    )
    assert preview["ok"] is True, preview
    units = preview["result"]["units"]
    assert units[0]["unit_type"] == "transcript_segment"
    assert units[0]["start_ms"] == 1_000
    assert units[0]["speaker_label"] == "Jane Smith"
    assert units[0]["provenance"]["source_type"] == "transcript"
    original_unit_ids = [unit["id"] for unit in units]

    speakers = list_speakers(core, project_id)
    assert {speaker["native_speaker_label"] for speaker in speakers} == {
        "Jane Smith",
        "Robert Chen",
        "Conference Room",
    }
    assert all(speaker["audience_profile"] is None for speaker in speakers)

    jane = create_profile(core, project_id, "Jane Smith")
    robert = create_profile(core, project_id, "Robert Chen")
    map_speaker(core, project_id, document_id, "Jane Smith", jane["id"])
    map_speaker(core, project_id, document_id, "Robert Chen", robert["id"])
    mapped = {
        speaker["native_speaker_label"]: speaker for speaker in list_speakers(core, project_id)
    }
    assert mapped["Jane Smith"]["audience_profile"]["id"] == jane["id"]
    assert mapped["Robert Chen"]["audience_profile"]["id"] == robert["id"]
    assert mapped["Conference Room"]["audience_profile"] is None

    jane_candidates = extract(core, project_id, jane["id"], "extract-jane")
    robert_candidates = extract(core, project_id, robert["id"], "extract-robert")
    assert jane_candidates["created_candidate_count"] == 2
    assert robert_candidates["created_candidate_count"] == 2
    assert all(candidate["provisional"] for candidate in jane_candidates["candidates"])
    assert all(candidate["status"] == "pending" for candidate in robert_candidates["candidates"])
    with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
        assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 0

    all_candidates = list_observations(core, project_id)["candidates"]
    assert all(
        "upload all project files" not in candidate["proposed_text"] for candidate in all_candidates
    )
    edited = next(
        candidate
        for candidate in all_candidates
        if candidate["audience_profile_id"] == jane["id"]
        and candidate["observation_type"] == "answer_preference"
    )
    accepted = call(
        core,
        "accept-edited",
        "audience.accept_observation",
        {
            "project_id": project_id,
            "candidate_id": edited["id"],
            "observation_type": "answer_preference",
            "text": "Explicitly requests concise answers before detail.",
        },
    )
    assert accepted["ok"] is True, accepted
    for candidate in all_candidates:
        if candidate["id"] == edited["id"]:
            continue
        response = call(
            core,
            f"accept-{candidate['id']}",
            "audience.accept_observation",
            {
                "project_id": project_id,
                "candidate_id": candidate["id"],
                "text": candidate["proposed_text"],
                "observation_type": candidate["observation_type"],
            },
        )
        assert response["ok"] is True, response

    observations = list_observations(core, project_id)["observations"]
    assert len(observations) == 4
    assert all(item["review_status"] == "active" for item in observations)
    assert all(item["sensitive_trait"] is False for item in observations)
    assert all(item["evidence"] for item in observations)
    assert all(
        evidence["source_type"] == "transcript" and evidence["source_unit_id"] in original_unit_ids
        for item in observations
        for evidence in item["evidence"]
        if item["derivation"] == "source_derived"
    )

    lexical = call(
        core,
        "lexical-transcript",
        "search.lexical",
        {"project_id": project_id, "query": "status-quo cost"},
    )
    assert lexical["ok"] is True, lexical
    assert lexical["result"]["results"][0]["source_type"] == "transcript"
    assert "Jane Smith" in lexical["result"]["results"][0]["label"]

    reindexed = call(
        core,
        "reindex-vtt",
        "source.reindex",
        {"project_id": project_id, "document_id": document_id},
    )
    assert reindexed["ok"] is True, reindexed
    after_reindex = call(
        core,
        "preview-after-reindex",
        "source.preview",
        {"project_id": project_id, "document_id": document_id, "limit": 7},
    )
    assert [unit["id"] for unit in after_reindex["result"]["units"]] == original_unit_ids

    core.close()
    restarted = CoreService(
        data_root=data_root, embedding_adapter=DeterministicEmbeddingAdapter(dimension=4)
    )
    try:
        persisted = list_observations(restarted, project_id)
        assert len(persisted["observations"]) == 4
        context_response = call(
            restarted,
            "audience-context",
            "audience.build_context",
            {"project_id": project_id},
        )
        assert context_response["ok"] is True, context_response
        context = context_response["result"]
        assert {profile["display_name"] for profile in context["profiles"]} == {
            "Jane Smith",
            "Robert Chen",
        }
        assert all(profile["observations"] for profile in context["profiles"])
        assert all(
            evidence["source_type"] == "transcript"
            for profile in context["profiles"]
            for observation in profile["observations"]
            for evidence in observation["evidence"]
            if observation["derivation"] == "source_derived"
        )
    finally:
        restarted.close()


def test_remap_unmap_stales_without_transferring_derived_observations(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
    )
    try:
        project_id = create_project(core, "M4 remap")
        document_id = import_vtt(core, project_id)["document"]["id"]
        profile_a = create_profile(core, project_id, "Profile A")
        profile_b = create_profile(core, project_id, "Profile B")
        map_speaker(core, project_id, document_id, "Jane Smith", profile_a["id"])
        candidates = extract(core, project_id, profile_a["id"], "extract-a")["candidates"]
        accepted = call(
            core,
            "accept-a",
            "audience.accept_observation",
            {
                "project_id": project_id,
                "candidate_id": candidates[0]["id"],
                "text": candidates[0]["proposed_text"],
                "observation_type": candidates[0]["observation_type"],
            },
        )
        assert accepted["ok"] is True, accepted

        map_speaker(core, project_id, document_id, "Jane Smith", profile_b["id"])
        stale = list_observations(core, project_id)
        old_observation = next(
            item for item in stale["observations"] if item["audience_profile_id"] == profile_a["id"]
        )
        assert old_observation["review_status"] == "stale"
        old_candidates = [
            item for item in stale["candidates"] if item["audience_profile_id"] == profile_a["id"]
        ]
        assert old_candidates
        assert {item["status"] for item in old_candidates} == {"accepted", "stale"}
        stale_candidate = next(item for item in old_candidates if item["status"] == "stale")
        stale_accept = call(
            core,
            "accept-stale-candidate",
            "audience.accept_observation",
            {"project_id": project_id, "candidate_id": stale_candidate["id"]},
        )
        assert stale_accept["ok"] is False
        assert stale_accept["error"]["code"] == "AUDIENCE_CANDIDATE_STALE"
        context = call(
            core,
            "context-after-remap",
            "audience.build_context",
            {"project_id": project_id},
        )
        assert context["ok"] is True, context
        assert all(
            observation["id"] != old_observation["id"]
            for profile in context["result"]["profiles"]
            for observation in profile["observations"]
        )
        assert (
            extract(core, project_id, profile_b["id"], "extract-b")["created_candidate_count"] >= 1
        )

        unmapped = call(
            core,
            "unmap-jane",
            "transcript.unmap_speaker",
            {
                "project_id": project_id,
                "document_id": document_id,
                "native_speaker_label": "Jane Smith",
            },
        )
        assert unmapped["ok"] is True, unmapped
        speakers = {
            speaker["native_speaker_label"]: speaker for speaker in list_speakers(core, project_id)
        }
        assert speakers["Jane Smith"]["audience_profile"] is None
        assert (
            next(
                item
                for item in list_observations(core, project_id)["observations"]
                if item["id"] == old_observation["id"]
            )["review_status"]
            == "stale"
        )
    finally:
        core.close()


def test_rejected_candidate_is_deduped_and_profile_delete_unresolves_speaker(
    tmp_path: Path,
) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
    )
    try:
        project_id = create_project(core, "M4 delete")
        document_id = import_vtt(core, project_id)["document"]["id"]
        profile = create_profile(core, project_id, "Delete Me")
        map_speaker(core, project_id, document_id, "Jane Smith", profile["id"])
        first = extract(core, project_id, profile["id"], "extract-before-reject")
        candidate = first["candidates"][0]
        rejected = call(
            core,
            "reject-candidate",
            "audience.reject_observation",
            {"project_id": project_id, "candidate_id": candidate["id"]},
        )
        assert rejected["ok"] is True, rejected
        second = extract(core, project_id, profile["id"], "extract-after-reject")
        assert second["created_candidate_count"] == 0
        assert second["skipped_duplicate_count"] >= 1

        deleted = call(
            core,
            "delete-profile",
            "audience.delete",
            {"project_id": project_id, "audience_profile_id": profile["id"]},
        )
        assert deleted["ok"] is True, deleted
        speakers = {
            speaker["native_speaker_label"]: speaker for speaker in list_speakers(core, project_id)
        }
        assert speakers["Jane Smith"]["audience_profile"] is None
        assert (
            call(core, "profiles-after-delete", "audience.list", {"project_id": project_id})[
                "result"
            ]["profiles"]
            == []
        )
        assert (
            call(
                core,
                "sources-after-profile-delete",
                "source.list",
                {"project_id": project_id},
            )["result"]["sources"][0]["source_units_count"]
            == 7
        )
    finally:
        core.close()


@pytest.mark.parametrize(
    "text",
    [
        "Jane seems depressed.",
        "Robert is probably Republican.",
        "Jane may have a medical condition.",
        "Robert sounds deceptive.",
        "Jane has low intelligence.",
        "Robert appears emotionally unstable.",
        "Jane has ADHD.",
        "Robert was arrested.",
        "Jane is a union member.",
        "Robert's sexual orientation is relevant.",
        "Jane is Christian.",
        "Robert's ethnicity is obvious.",
        "Jane is unemployable.",
        "Jane has a health issue.",
        "Robert seems happy.",
        "Jane may lie about the budget.",
        "Robert has union membership.",
        "Jane is pregnant.",
        "Jane mentioned pregnancy.",
        "Robert has diabetes.",
        "Robert is diabetic.",
        "Jane has cancer.",
        "Jane has political beliefs that affect this.",
        "Jane is politically active.",
        "Robert seems nervous.",
        "Jane appears worried.",
        "Robert is scared.",
    ],
)
def test_observation_policy_rejects_prohibited_categories(tmp_path: Path, text: str) -> None:
    core = CoreService(data_root=tmp_path / "data")
    try:
        project_id = create_project(core, "M4 policy")
        profile = create_profile(core, project_id, "Policy Profile")
        response = call(
            core,
            "unsafe-observation",
            "audience.create_observation",
            {
                "project_id": project_id,
                "audience_profile_id": profile["id"],
                "observation_type": "interaction_pattern",
                "text": text,
            },
        )
        assert response["ok"] is False
        assert response["error"]["code"] == "AUDIENCE_OBSERVATION_PROHIBITED"
    finally:
        core.close()


def test_source_delete_stales_derived_rows_but_preserves_user_observation(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
    )
    try:
        project_id = create_project(core, "M4 source delete")
        imported = import_vtt(core, project_id)
        document_id = imported["document"]["id"]
        profile = create_profile(core, project_id, "Source Delete Profile")
        map_speaker(core, project_id, document_id, "Jane Smith", profile["id"])
        candidate = extract(core, project_id, profile["id"], "extract-delete")["candidates"][0]
        accepted = call(
            core,
            "accept-delete-candidate",
            "audience.accept_observation",
            {
                "project_id": project_id,
                "candidate_id": candidate["id"],
                "text": candidate["proposed_text"],
                "observation_type": candidate["observation_type"],
            },
        )
        assert accepted["ok"] is True, accepted
        user_observation = call(
            core,
            "user-observation",
            "audience.create_observation",
            {
                "project_id": project_id,
                "audience_profile_id": profile["id"],
                "observation_type": "topic_interest",
                "text": "User supplied project context.",
            },
        )
        assert user_observation["ok"] is True, user_observation

        deleted = call(
            core,
            "delete-transcript",
            "source.delete",
            {"project_id": project_id, "document_id": document_id},
        )
        assert deleted["ok"] is True, deleted
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM source_units").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
            assert (
                connection.execute("SELECT COUNT(*) FROM transcript_speaker_maps").fetchone()[0]
                == 0
            )
            assert (
                connection.execute("SELECT COUNT(*) FROM audience_observation_evidence").fetchone()[
                    0
                ]
                == 0
            )
        observations = list_observations(core, project_id)["observations"]
        assert any(item["derivation"] == "user_entered" for item in observations)
        assert any(
            item["derivation"] == "source_derived" and item["review_status"] == "stale"
            for item in observations
        )
    finally:
        core.close()


def test_m4_unknown_fields_and_cross_project_profile_isolation(tmp_path: Path) -> None:
    core = CoreService(data_root=tmp_path / "data")
    try:
        project_a = create_project(core, "M4 A")
        project_b = create_project(core, "M4 B")
        profile_a = create_profile(core, project_a, "Same Name")
        unknown = call(
            core,
            "unknown-profile-field",
            "audience.create",
            {"project_id": project_a, "display_name": "x", "sensitive_trait": True},
        )
        assert unknown["ok"] is False
        assert unknown["error"]["code"] == "INVALID_REQUEST"
        wrong_project = call(
            core,
            "wrong-project-profile",
            "audience.update",
            {
                "project_id": project_b,
                "audience_profile_id": profile_a["id"],
                "display_name": "Should fail",
            },
        )
        assert wrong_project["ok"] is False
        assert wrong_project["error"]["code"] == "AUDIENCE_PROFILE_NOT_FOUND"
        assert (
            call(core, "list-b", "audience.list", {"project_id": project_b})["result"]["profiles"]
            == []
        )
    finally:
        core.close()


def test_profile_crud_disable_context_user_observation_and_project_delete(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    core = CoreService(data_root=data_root)
    try:
        project_id = create_project(core, "M4 project delete")
        profile = create_profile(core, project_id, "CRUD Profile")
        updated = call(
            core,
            "update-profile",
            "audience.update",
            {
                "project_id": project_id,
                "audience_profile_id": profile["id"],
                "display_name": "CRUD Profile Updated",
                "role": "VP",
                "active": False,
            },
        )
        assert updated["ok"] is True, updated
        assert updated["result"]["profile"]["active"] is False
        inactive_context = call(
            core,
            "inactive-context",
            "audience.build_context",
            {"project_id": project_id},
        )
        assert inactive_context["ok"] is True, inactive_context
        assert inactive_context["result"]["profiles"] == []

        enabled = call(
            core,
            "enable-profile",
            "audience.update",
            {
                "project_id": project_id,
                "audience_profile_id": profile["id"],
                "active": True,
            },
        )
        assert enabled["ok"] is True, enabled
        user_observation = call(
            core,
            "crud-user-observation",
            "audience.create_observation",
            {
                "project_id": project_id,
                "audience_profile_id": profile["id"],
                "observation_type": "topic_interest",
                "text": "User supplied topic note.",
            },
        )
        assert user_observation["ok"] is True, user_observation
        observation_id = user_observation["result"]["observation"]["id"]
        context = call(
            core,
            "crud-context",
            "audience.build_context",
            {"project_id": project_id},
        )
        assert context["ok"] is True, context
        assert context["result"]["profiles"][0]["observations"][0]["derivation"] == "user_entered"
        empty_context = call(
            core,
            "empty-context",
            "audience.build_context",
            {"project_id": project_id, "audience_profile_ids": []},
        )
        assert empty_context["ok"] is True, empty_context
        assert empty_context["result"]["profiles"] == []
        edited = call(
            core,
            "edit-user-observation",
            "audience.update_observation",
            {
                "project_id": project_id,
                "observation_id": observation_id,
                "text": "Edited user supplied topic note.",
            },
        )
        assert edited["ok"] is True, edited
        assert edited["result"]["observation"]["text"] == "Edited user supplied topic note."
        removed = call(
            core,
            "delete-user-observation",
            "audience.delete_observation",
            {"project_id": project_id, "observation_id": observation_id},
        )
        assert removed["ok"] is True, removed

        project_root = data_root / "projects" / project_id
        deleted = call(core, "delete-m4-project", "project.delete", {"project_id": project_id})
        assert deleted["ok"] is True, deleted
        assert not project_root.exists()
        assert call(core, "list-after-m4-delete", "project.list", {})["result"]["projects"] == []
    finally:
        core.close()


def test_extraction_requires_question_like_evidence_and_uses_calibrated_wording() -> None:
    declarative_units = [
        {"id": "1", "text": "Cost is approved."},
        {"id": "2", "text": "Budget is fixed."},
        {"id": "3", "text": "This test fails on Windows."},
        {"id": "4", "text": "The backup job fails sometimes."},
        {"id": "5", "text": "Ownership is assigned."},
        {"id": "6", "text": "The owner for migration is documented."},
    ]
    assert extract_observable_patterns(declarative_units) == []

    generic_cost = extract_observable_patterns(
        [
            {"id": "1", "text": "What is the cost?"},
            {"id": "2", "text": "Can you explain the budget?"},
        ]
    )
    cost_proposal = next(
        item for item in generic_cost if item.observation_type == "question_pattern"
    )
    assert cost_proposal.proposed_text == "Repeatedly asks about cost or budget."
    assert cost_proposal.matched_segment_count == 2
    assert cost_proposal.evidence_ids == ("1", "2")

    explicit_cost = extract_observable_patterns(
        [
            {"id": "1", "text": "What is the status-quo cost?"},
            {"id": "2", "text": "How does this cost compare with the baseline?"},
        ]
    )
    assert next(
        item for item in explicit_cost if item.observation_type == "question_pattern"
    ).proposed_text == ("Repeatedly asks for status-quo cost comparisons.")

    rollback_only = extract_observable_patterns(
        [
            {"id": "1", "text": "Can we roll back safely?"},
            {"id": "2", "text": "What happens during rollback?"},
        ]
    )
    assert next(
        item for item in rollback_only if item.observation_type == "question_pattern"
    ).proposed_text == ("Repeatedly asks about rollback.")

    rollback_and_failure = extract_observable_patterns(
        [
            {"id": "1", "text": "What happens if rollback fails?"},
            {"id": "2", "text": "Which failure modes remain?"},
        ]
    )
    assert (
        next(
            item for item in rollback_and_failure if item.observation_type == "question_pattern"
        ).proposed_text
        == "Repeatedly asks about rollback or failure modes."
    )

    schedule_generic = extract_observable_patterns(
        [
            {"id": "1", "text": "What is the schedule?"},
            {"id": "2", "text": "When is the timeline?"},
        ]
    )
    assert next(
        item for item in schedule_generic if item.observation_type == "question_pattern"
    ).proposed_text == ("Repeatedly asks about schedule or timeline.")

    schedule_challenge = extract_observable_patterns(
        [
            {"id": "1", "text": "Why is the schedule assumption unrealistic?"},
            {"id": "2", "text": "Could the timeline assumption be too aggressive?"},
        ]
    )
    assert next(
        item for item in schedule_challenge if item.observation_type == "question_pattern"
    ).proposed_text == ("Repeatedly challenges schedule assumptions.")


def test_unicode_speaker_labels_and_mixed_vtt_fail_closed(tmp_path: Path) -> None:
    srt = tmp_path / "unicode.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nJosé Álvarez: What is the cost?\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nМария Иванова: Who owns the rollout?\n\n"
        "3\n00:00:05,000 --> 00:00:06,000\n张伟: What is the timeline?\n",
        encoding="utf-8",
    )
    srt_units = SrtParser().parse(srt)
    assert [unit.speaker_label for unit in srt_units] == [
        "José Álvarez",
        "Мария Иванова",
        "张伟",
    ]

    named = tmp_path / "unicode.txt"
    named.write_text(
        "[00:00:01.000 --> 00:00:02.000] Mārtiņš Bērziņš: Show me the data.\n",
        encoding="utf-8",
    )
    named_unit = NamedTextTranscriptParser().parse(named)[0]
    assert named_unit.speaker_label == "Mārtiņš Bērziņš"

    mixed = tmp_path / "mixed.vtt"
    mixed.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n"
        "<v José Álvarez>First speaker.</v> <v Мария Иванова>Second speaker.</v>\n",
        encoding="utf-8",
    )
    with pytest.raises(CoreDomainError, match="multiple speaker labels") as error:
        WebVttParser().parse(mixed)
    assert error.value.code == "SOURCE_PARSE_FAILED"

    repeated = tmp_path / "repeated.vtt"
    repeated.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n"
        "<v 张伟>First part.</v> <v 张伟>Second part.</v>\n",
        encoding="utf-8",
    )
    repeated_unit = WebVttParser().parse(repeated)[0]
    assert repeated_unit.speaker_label == "张伟"
    assert repeated_unit.text == "First part. Second part."


def test_profile_notes_and_legacy_observations_are_policy_checked_in_context(
    tmp_path: Path,
) -> None:
    core = CoreService(data_root=tmp_path / "data")
    try:
        project_id = create_project(core, "M4 context policy")
        unsafe_notes = [
            "Jane is probably Republican.",
            "Robert seems depressed.",
            "Jane has diabetes.",
        ]
        for index, notes in enumerate(unsafe_notes):
            response = call(
                core,
                f"unsafe-profile-notes-{index}",
                "audience.create",
                {
                    "project_id": project_id,
                    "display_name": f"Unsafe Notes {index}",
                    "user_notes": notes,
                },
            )
            assert response["ok"] is False
            assert response["error"]["code"] == "AUDIENCE_OBSERVATION_PROHIBITED"

        created = call(
            core,
            "safe-profile-notes",
            "audience.create",
            {
                "project_id": project_id,
                "display_name": "Safe Notes",
                "user_notes": "Owns final budget approval.",
            },
        )
        assert created["ok"] is True, created
        profile = created["result"]["profile"]
        profile_id = profile["id"]

        safe_context = call(
            core,
            "safe-notes-context",
            "audience.build_context",
            {"project_id": project_id},
        )
        assert safe_context["ok"] is True, safe_context
        assert safe_context["result"]["profiles"][0]["user_supplied_notes"] == (
            "Owns final budget approval."
        )

        update = call(
            core,
            "unsafe-profile-update",
            "audience.update",
            {
                "project_id": project_id,
                "audience_profile_id": profile_id,
                "user_notes": "Robert seems nervous.",
            },
        )
        assert update["ok"] is False
        assert update["error"]["code"] == "AUDIENCE_OBSERVATION_PROHIBITED"

        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            connection.execute(
                "UPDATE audience_profiles SET user_notes = ? WHERE id = ?",
                ("Robert seems nervous.", profile_id),
            )
            connection.commit()
        legacy_notes = call(
            core,
            "legacy-unsafe-notes-context",
            "audience.build_context",
            {"project_id": project_id},
        )
        assert legacy_notes["ok"] is False
        assert legacy_notes["error"]["code"] == "AUDIENCE_OBSERVATION_PROHIBITED"

        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            connection.execute(
                "UPDATE audience_profiles SET user_notes = ? WHERE id = ?",
                ("Owns final budget approval.", profile_id),
            )
            connection.commit()
        observation = call(
            core,
            "safe-observation",
            "audience.create_observation",
            {
                "project_id": project_id,
                "audience_profile_id": profile_id,
                "observation_type": "topic_interest",
                "text": "Asks about project risks.",
            },
        )
        assert observation["ok"] is True, observation
        observation_id = observation["result"]["observation"]["id"]

        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            connection.execute(
                "UPDATE audience_observations SET text = ? WHERE id = ?",
                ("Robert seems nervous.", observation_id),
            )
            connection.commit()
        legacy_observation = call(
            core,
            "legacy-unsafe-observation-context",
            "audience.build_context",
            {"project_id": project_id},
        )
        assert legacy_observation["ok"] is False
        assert legacy_observation["error"]["code"] == "AUDIENCE_OBSERVATION_PROHIBITED"

        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            connection.execute(
                "UPDATE audience_observations SET text = ?, sensitive_trait = 1 WHERE id = ?",
                ("Asks about project risks.", observation_id),
            )
            connection.commit()
        sensitive_context = call(
            core,
            "sensitive-observation-context",
            "audience.build_context",
            {"project_id": project_id},
        )
        assert sensitive_context["ok"] is True, sensitive_context
        assert sensitive_context["result"]["profiles"][0]["observations"] == []
    finally:
        core.close()


def test_safe_observable_audience_statements_remain_allowed(tmp_path: Path) -> None:
    core = CoreService(data_root=tmp_path / "data")
    try:
        project_id = create_project(core, "M4 safe statements")
        profile = create_profile(core, project_id, "Safe Statements")
        for index, text in enumerate(
            [
                "Jane asks about project risk.",
                "Robert asks what happens if rollback fails.",
                "Jane requests concise answers.",
            ]
        ):
            response = call(
                core,
                f"safe-observation-{index}",
                "audience.create_observation",
                {
                    "project_id": project_id,
                    "audience_profile_id": profile["id"],
                    "observation_type": "interaction_pattern",
                    "text": text,
                },
            )
            assert response["ok"] is True, response
    finally:
        core.close()


def test_extraction_and_evidence_limits_are_reported_and_bounded(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
    )
    try:
        project_id = create_project(core, "M4 extraction bounds")
        profile = create_profile(core, project_id, "Extraction Bounds")
        document_ids = seed_transcript_segments(
            core, project_id, profile["id"], [MAX_EXTRACTION_SEGMENTS // 2 + 1] * 2
        )

        too_large = call(
            core,
            "too-large-extraction",
            "audience.extract_observations",
            {"project_id": project_id, "audience_profile_id": profile["id"]},
        )
        assert too_large["ok"] is False
        assert too_large["error"]["code"] == "AUDIENCE_EXTRACTION_TOO_LARGE"
        assert too_large["error"]["details"]["max_segments"] == MAX_EXTRACTION_SEGMENTS

        filtered = call(
            core,
            "bounded-extraction",
            "audience.extract_observations",
            {
                "project_id": project_id,
                "audience_profile_id": profile["id"],
                "document_ids": [document_ids[0]],
            },
        )
        assert filtered["ok"] is True, filtered
        result = filtered["result"]
        assert result["matched_segment_count"] == MAX_EXTRACTION_SEGMENTS // 2 + 1
        assert result["evidence_segment_count"] == MAX_EVIDENCE_PER_ITEM
        assert len(result["candidates"]) == 1
        assert len(result["candidates"][0]["evidence"]) == MAX_EVIDENCE_PER_ITEM
        assert result["candidates"][0]["evidence_segment_count"] == MAX_EVIDENCE_PER_ITEM
    finally:
        core.close()


def test_context_profile_observation_and_evidence_bounds(tmp_path: Path) -> None:
    core = CoreService(data_root=tmp_path / "data")
    try:
        project_id = create_project(core, "M4 context bounds")
        profile_ids: list[str] = []
        for index in range(MAX_CONTEXT_PROFILES + 1):
            response = call(
                core,
                f"bounded-profile-{index}",
                "audience.create",
                {
                    "project_id": project_id,
                    "display_name": f"Bounded Profile {index}",
                    "user_notes": "Owns final budget approval. " * 30,
                },
            )
            assert response["ok"] is True, response
            profile_ids.append(response["result"]["profile"]["id"])

        too_many = call(
            core,
            "too-many-context-profiles",
            "audience.build_context",
            {"project_id": project_id, "audience_profile_ids": profile_ids},
        )
        assert too_many["ok"] is False
        assert too_many["error"]["code"] == "INVALID_REQUEST"

        long_observation = "Discusses roadmap priorities with the team. " * 30
        for profile_id in profile_ids[:MAX_CONTEXT_PROFILES]:
            for index in range(MAX_CONTEXT_OBSERVATIONS_PER_PROFILE + 2):
                response = call(
                    core,
                    f"bounded-observation-{profile_id}-{index}",
                    "audience.create_observation",
                    {
                        "project_id": project_id,
                        "audience_profile_id": profile_id,
                        "observation_type": "topic_interest",
                        "text": long_observation,
                    },
                )
                assert response["ok"] is True, response

        bounded = call(
            core,
            "bounded-context",
            "audience.build_context",
            {"project_id": project_id},
        )
        assert bounded["ok"] is True, bounded
        context = bounded["result"]
        assert len(context["profiles"]) == MAX_CONTEXT_PROFILES
        assert all(
            len(profile["observations"]) <= MAX_CONTEXT_OBSERVATIONS_PER_PROFILE
            for profile in context["profiles"]
        )
        assert len(json.dumps(context, ensure_ascii=True)) <= MAX_AUDIENCE_CONTEXT_CHARS
    finally:
        core.close()


def test_context_evidence_is_currently_attributed_and_source_bounded(tmp_path: Path) -> None:
    core = CoreService(data_root=tmp_path / "data")
    try:
        project_id = create_project(core, "M4 evidence context")
        profile = create_profile(core, project_id, "Evidence Context")
        document_id = seed_transcript_segments(core, project_id, profile["id"], [5])[0]
        observation_id = str(uuid.uuid4())
        now = utc_now()
        with core._storage.project_database(project_id) as connection:  # type: ignore[attr-defined]
            connection.execute(
                """
                INSERT INTO audience_observations (
                    id, audience_profile_id, observation_type, text, derivation,
                    confidence, sensitive_trait, review_status, created_at, updated_at
                ) VALUES (?, ?, 'question_pattern', ?, 'source_derived', 0.9, 0, 'active', ?, ?)
                """,
                (
                    observation_id,
                    profile["id"],
                    "Repeatedly asks about schedule or timeline.",
                    now,
                    now,
                ),
            )
            unit_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM source_units WHERE document_id = ? ORDER BY ordinal",
                    (document_id,),
                ).fetchall()
            ]
            connection.executemany(
                """
                INSERT INTO audience_observation_evidence (
                    observation_id, provenance_type, provenance_id
                ) VALUES (?, 'transcript', ?)
                """,
                [(observation_id, unit_id) for unit_id in unit_ids],
            )
            connection.commit()

        context_response = call(
            core,
            "bounded-evidence-context",
            "audience.build_context",
            {"project_id": project_id},
        )
        assert context_response["ok"] is True, context_response
        observations = context_response["result"]["profiles"][0]["observations"]
        assert len(observations) == 1
        assert len(observations[0]["evidence"]) == MAX_CONTEXT_EVIDENCE_PER_OBSERVATION
    finally:
        core.close()


def test_audience_entity_capacity_limits_fail_closed(tmp_path: Path) -> None:
    core = CoreService(
        data_root=tmp_path / "data",
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
    )
    try:
        profile_project = create_project(core, "M4 profile capacity")
        now = utc_now()
        with core._storage.project_database(profile_project) as connection:  # type: ignore[attr-defined]
            connection.executemany(
                """
                INSERT INTO audience_profiles (
                    id, project_id, display_name, role, organization, user_notes,
                    active, created_at, updated_at
                ) VALUES (?, ?, ?, NULL, NULL, NULL, 1, ?, ?)
                """,
                [
                    (str(uuid.uuid4()), profile_project, f"Seeded {index}", now, now)
                    for index in range(MAX_PROFILE_COUNT)
                ],
            )
            connection.commit()
        profile_limit = call(
            core,
            "profile-capacity",
            "audience.create",
            {"project_id": profile_project, "display_name": "Over capacity"},
        )
        assert profile_limit["ok"] is False
        assert profile_limit["error"]["code"] == "AUDIENCE_PROFILE_LIMIT_REACHED"

        observation_project = create_project(core, "M4 observation capacity")
        observation_profile = create_profile(core, observation_project, "Observation Capacity")
        with core._storage.project_database(observation_project) as connection:  # type: ignore[attr-defined]
            connection.executemany(
                """
                INSERT INTO audience_observations (
                    id, audience_profile_id, observation_type, text, derivation,
                    confidence, sensitive_trait, review_status, created_at, updated_at
                ) VALUES (?, ?, 'topic_interest', ?, 'user_entered', NULL, 0, 'active', ?, ?)
                """,
                [
                    (
                        str(uuid.uuid4()),
                        observation_profile["id"],
                        f"Seeded safe observation {index}.",
                        now,
                        now,
                    )
                    for index in range(MAX_OBSERVATIONS_PER_PROFILE)
                ],
            )
            connection.commit()
        observation_limit = call(
            core,
            "observation-capacity",
            "audience.create_observation",
            {
                "project_id": observation_project,
                "audience_profile_id": observation_profile["id"],
                "observation_type": "topic_interest",
                "text": "A safe additional observation.",
            },
        )
        assert observation_limit["ok"] is False
        assert observation_limit["error"]["code"] == "AUDIENCE_OBSERVATION_LIMIT_REACHED"

        candidate_project = create_project(core, "M4 candidate capacity")
        imported = import_vtt(core, candidate_project)
        document_id = imported["document"]["id"]
        candidate_profile = create_profile(core, candidate_project, "Candidate Capacity")
        map_speaker(core, candidate_project, document_id, "Jane Smith", candidate_profile["id"])
        with core._storage.project_database(candidate_project) as connection:  # type: ignore[attr-defined]
            connection.executemany(
                """
                INSERT INTO audience_observation_candidates (
                    id, audience_profile_id, observation_type, proposed_text, confidence,
                    fingerprint, status, observation_id, created_at, updated_at
                ) VALUES (?, ?, 'topic_interest', ?, 0.5, ?, 'rejected', NULL, ?, ?)
                """,
                [
                    (
                        str(uuid.uuid4()),
                        candidate_profile["id"],
                        f"Seeded candidate {index}.",
                        hashlib.sha256(f"candidate-{index}".encode("ascii")).hexdigest(),
                        now,
                        now,
                    )
                    for index in range(MAX_CANDIDATES_PER_PROFILE)
                ],
            )
            connection.commit()
        candidate_limit = call(
            core,
            "candidate-capacity",
            "audience.extract_observations",
            {"project_id": candidate_project, "audience_profile_id": candidate_profile["id"]},
        )
        assert candidate_limit["ok"] is False
        assert candidate_limit["error"]["code"] == "AUDIENCE_CANDIDATE_LIMIT_REACHED"

        accept_project = create_project(core, "M4 accept capacity")
        accepted_document = import_vtt(core, accept_project)["document"]["id"]
        accept_profile = create_profile(core, accept_project, "Accept Capacity")
        map_speaker(core, accept_project, accepted_document, "Jane Smith", accept_profile["id"])
        candidate = extract(core, accept_project, accept_profile["id"], "accept-capacity-extract")[
            "candidates"
        ][0]
        with core._storage.project_database(accept_project) as connection:  # type: ignore[attr-defined]
            connection.executemany(
                """
                INSERT INTO audience_observations (
                    id, audience_profile_id, observation_type, text, derivation,
                    confidence, sensitive_trait, review_status, created_at, updated_at
                ) VALUES (?, ?, 'topic_interest', ?, 'user_entered', NULL, 0, 'active', ?, ?)
                """,
                [
                    (
                        str(uuid.uuid4()),
                        accept_profile["id"],
                        f"Seeded accept observation {index}.",
                        now,
                        now,
                    )
                    for index in range(MAX_OBSERVATIONS_PER_PROFILE)
                ],
            )
            connection.commit()
        accept_limit = call(
            core,
            "accept-observation-capacity",
            "audience.accept_observation",
            {
                "project_id": accept_project,
                "candidate_id": candidate["id"],
                "observation_type": candidate["observation_type"],
                "text": candidate["proposed_text"],
            },
        )
        assert accept_limit["ok"] is False
        assert accept_limit["error"]["code"] == "AUDIENCE_OBSERVATION_LIMIT_REACHED"
    finally:
        core.close()
