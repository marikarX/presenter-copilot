from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
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
