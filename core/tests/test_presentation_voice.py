"""Transient local voice editing and source ownership boundaries."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import ASR_FRAME_SAMPLES, DeterministicFakeAudioInput
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter

FIXTURE_ROOT = Path(__file__).parents[2] / "samples" / "synthetic-deck"
VOICE_START = "presentation.workspace.voice_start"
VOICE_STOP = "presentation.workspace.voice_stop"
VOICE_CANCEL = "presentation.workspace.voice_cancel"


def _request(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "type": "request",
        "request_id": str(uuid.uuid4()),
        "method": method,
        "params": params,
    }


def _call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(_request(method, params))
    assert response["ok"] is True, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def _error_code(core: CoreService, method: str, params: dict[str, Any]) -> str:
    response = core.handle_message(_request(method, params))
    assert response["ok"] is False, response
    error = response["error"]
    assert isinstance(error, dict)
    return str(error["code"])


def _wait_until(predicate: Any, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def _core(
    data_root: Path,
    *,
    audio: DeterministicFakeAudioInput,
    adapter: DeterministicFakeASRAdapter,
    events: list[dict[str, Any]],
) -> CoreService:
    return CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=audio,
        asr_adapters={adapter.id: adapter},
        event_sink=events.append,
    )


def _workspace_context(
    core: CoreService, project_name: str = "Voice edit fixture"
) -> dict[str, str]:
    project = _call(core, "project.create", {"name": project_name})["project"]
    document = _call(
        core,
        "source.import",
        {
            "project_id": project["id"],
            "kind": "presentation",
            "path": str((FIXTURE_ROOT / "deck" / "presentation.pptx").resolve()),
        },
    )["document"]
    opened = _call(
        core,
        "presentation.workspace.open_source",
        {"project_id": project["id"], "document_id": document["id"]},
    )
    targets = _call(
        core,
        "presentation.workspace.list_text_targets",
        {
            "project_id": project["id"],
            "document_id": document["id"],
            "revision_id": opened["revision_id"],
            "slide_number": 1,
        },
    )
    target = next(
        item
        for item in targets["targets"]
        if (item["single_run_editable"] or item["uniform_run_editable"])
        and isinstance(item["current_text"], str)
        and item["current_text"].strip()
    )
    return {
        "project_id": str(project["id"]),
        "document_id": str(document["id"]),
        "revision_id": str(opened["revision_id"]),
        "slide_id": str(targets["slide_id"]),
        "slide_number": "1",
        "object_id": str(target["object_id"]),
        "current_text": str(target["current_text"]),
    }


def _start_params(context: dict[str, str], intent: str = "rewrite") -> dict[str, Any]:
    params: dict[str, Any] = {
        "project_id": context["project_id"],
        "document_id": context["document_id"],
        "revision_id": context["revision_id"],
        "slide_number": int(context["slide_number"]),
        "object_id": context["object_id"],
    }
    if intent != "rewrite":
        params.pop("object_id")
        params.update(intent="edit_plan", scope="deck" if intent == "edit_plan_deck" else "slide")
    return params


def _feed_instruction(audio: DeterministicFakeAudioInput) -> None:
    loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
    quiet = np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)
    audio.feed_frames([loud] * 30 + [quiet] * 35)


def test_outline_voice_before_deck_creation_is_ephemeral_and_project_owned(tmp_path: Path) -> None:
    events: list[dict[str, Any]] = []
    audio = DeterministicFakeAudioInput()
    core = _core(
        tmp_path / "data",
        audio=audio,
        adapter=DeterministicFakeASRAdapter(final_text="Approve a measured pilot."),
        events=events,
    )
    try:
        project = _call(core, "project.create", {"name": "Spoken outline"})["project"]["id"]
        other = _call(core, "project.create", {"name": "Other"})["project"]["id"]
        params = {"project_id": project, "intent": "outline", "scope": "deck"}
        for invalid in (
            {"document_id": str(uuid.uuid4())},
            {"object_id": str(uuid.uuid4())},
            {"revision_id": str(uuid.uuid4())},
            {"slide_number": 1},
            {"scope": "slide"},
        ):
            assert _error_code(core, VOICE_START, {**params, **invalid}) == "INVALID_REQUEST"
            assert not audio.started
        capture = _call(core, VOICE_START, params)["capture_id"]
        assert (
            _error_code(core, VOICE_STOP, {"project_id": other, "capture_id": capture})
            == "ASR_SESSION_INVALID"
        )
        _feed_instruction(audio)
        stopped = _call(core, VOICE_STOP, {"project_id": project, "capture_id": capture})
        assert stopped["transcript"] == "Approve a measured pilot."
        assert stopped["intent"] == "outline" and stopped["scope"] == "deck"
        assert all(
            stopped[field] is None
            for field in ("document_id", "revision_id", "slide_number", "object_id")
        )
        assert not audio.started
        with core._storage.project_database(project) as connection:
            for table in ("sessions", "utterances", "provider_runs", "documents"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        capture = _call(core, VOICE_START, params)["capture_id"]
        assert _call(core, "project.delete", {"project_id": project})["deleted"] is True
        assert not audio.started
        assert core._presentation_workspace_voice._captures == {}
        assert core._asr.active_owner_details() is None
    finally:
        assert core.close() is True


@pytest.mark.parametrize("intent", ["rewrite", "edit_plan_slide", "edit_plan_deck"])
def test_workspace_voice_returns_review_text_without_durable_capture_rows(
    tmp_path: Path,
    intent: str,
) -> None:
    events: list[dict[str, Any]] = []
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(
        partial_texts=("shorten the opening",),
        final_text="Shorten the selected title and keep the recommendation.",
    )
    core = _core(tmp_path / "data", audio=audio, adapter=adapter, events=events)
    try:
        context = _workspace_context(core)
        started = _call(core, VOICE_START, _start_params(context, intent))
        capture_id = str(started["capture_id"])
        owner = core._asr.active_owner_details()  # type: ignore[attr-defined]
        assert owner is not None
        assert owner[:3] == (context["project_id"], capture_id, "presentation_workspace")
        assert audio.started

        assert (
            _error_code(
                core,
                "asr.stop",
                {"project_id": context["project_id"], "session_id": capture_id},
            )
            == "ASR_SESSION_INVALID"
        )
        # Observe a partial while speech is active. Feeding silence in the same
        # burst can legitimately coalesce the optional partial into a final.
        audio.feed_frames([np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)] * 30)
        assert _wait_until(
            lambda: any(
                item.get("event") == "asr.partial"
                and item["payload"].get("session_id") == capture_id
                for item in events
            )
        )
        audio.feed_frames([np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)] * 35)

        stopped = _call(
            core,
            VOICE_STOP,
            {"project_id": context["project_id"], "capture_id": capture_id},
        )
        assert stopped["transcript"] == "Shorten the selected title and keep the recommendation."
        assert stopped["revision_id"] == context["revision_id"]
        assert stopped["object_id"] == (context["object_id"] if intent == "rewrite" else None)
        if intent != "rewrite":
            assert stopped["intent"] == "edit_plan"
            assert stopped["scope"] == ("deck" if intent == "edit_plan_deck" else "slide")
        assert not audio.started
        assert core._asr.active_owner_details() is None  # type: ignore[attr-defined]
        assert not any(
            item.get("event") == "asr.final" and item["payload"].get("session_id") == capture_id
            for item in events
        )
        with core._storage.project_database(context["project_id"]) as connection:  # type: ignore[attr-defined]
            assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM utterances").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM provider_runs").fetchone()[0] == 0
        assert core._presentation_workspace_voice._captures == {}  # type: ignore[attr-defined]
    finally:
        assert core.close() is True


@pytest.mark.parametrize("intent", ["rewrite", "edit_plan_slide", "edit_plan_deck"])
def test_workspace_voice_stale_revision_cancels_and_discards_transcript(
    tmp_path: Path,
    intent: str,
) -> None:
    events: list[dict[str, Any]] = []
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(final_text="This stale instruction is discarded.")
    core = _core(tmp_path / "data", audio=audio, adapter=adapter, events=events)
    try:
        context = _workspace_context(core)
        started = _call(core, VOICE_START, _start_params(context, intent))
        capture_id = str(started["capture_id"])
        _feed_instruction(audio)
        changed = _call(
            core,
            "presentation.workspace.replace_text_shape",
            {
                "project_id": context["project_id"],
                "document_id": context["document_id"],
                "expected_revision_id": context["revision_id"],
                "operation_type": "replace_text_shape",
                "slide_id": context["slide_id"],
                "object_id": context["object_id"],
                "expected_text": context["current_text"],
                "replacement_text": "A newer reviewed slide title.",
            },
        )
        assert changed["revision_number"] == 2

        assert (
            _error_code(
                core,
                VOICE_STOP,
                {"project_id": context["project_id"], "capture_id": capture_id},
            )
            == "PRESENTATION_REVISION_CONFLICT"
        )
        assert not audio.started
        assert core._asr.active_owner_details() is None  # type: ignore[attr-defined]
        assert core._presentation_workspace_voice._captures == {}  # type: ignore[attr-defined]
        assert not any(item.get("event") == "asr.final" for item in events)
        with core._storage.project_database(context["project_id"]) as connection:  # type: ignore[attr-defined]
            assert connection.execute("SELECT COUNT(*) FROM utterances").fetchone()[0] == 0
    finally:
        assert core.close() is True


def test_general_voice_can_target_a_blank_slide_without_a_text_object(tmp_path: Path) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter()
    core = _core(tmp_path / "data", audio=audio, adapter=adapter, events=[])
    try:
        context = _workspace_context(core)
        created = _call(
            core,
            "presentation.workspace.create_slide",
            {
                "project_id": context["project_id"],
                "document_id": context["document_id"],
                "expected_revision_id": context["revision_id"],
                "slide_id": context["slide_id"],
            },
        )
        params = _start_params(context, "edit_plan_slide")
        params.update(revision_id=created["revision_id"], slide_number=2)
        started = _call(core, VOICE_START, params)
        stopped = _call(
            core,
            VOICE_STOP,
            {"project_id": context["project_id"], "capture_id": started["capture_id"]},
        )
        assert stopped["object_id"] is None
        assert stopped["slide_number"] == 2
        assert stopped["transcript"] == ""
        assert not audio.started
    finally:
        assert core.close() is True


def test_workspace_source_and_project_deletion_cancel_owned_voice_capture(
    tmp_path: Path,
) -> None:
    events: list[dict[str, Any]] = []
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter()
    core = _core(tmp_path / "data", audio=audio, adapter=adapter, events=events)
    try:
        source_context = _workspace_context(core, "Delete source during voice")
        source_capture = _call(core, VOICE_START, _start_params(source_context))
        deleted_source = _call(
            core,
            "source.delete",
            {
                "project_id": source_context["project_id"],
                "document_id": source_context["document_id"],
            },
        )
        assert deleted_source["deleted"] is True
        assert not audio.started
        assert core._asr.active_owner_details() is None  # type: ignore[attr-defined]
        assert core._presentation_workspace_voice._captures == {}  # type: ignore[attr-defined]
        assert (
            _error_code(
                core,
                VOICE_STOP,
                {
                    "project_id": source_context["project_id"],
                    "capture_id": str(source_capture["capture_id"]),
                },
            )
            == "ASR_SESSION_INVALID"
        )

        project_context = _workspace_context(core, "Delete project during voice")
        _call(core, VOICE_START, _start_params(project_context))
        deleted_project = _call(
            core,
            "project.delete",
            {"project_id": project_context["project_id"]},
        )
        assert deleted_project["deleted"] is True
        assert not audio.started
        assert core._asr.active_owner_details() is None  # type: ignore[attr-defined]
        assert core._presentation_workspace_voice._captures == {}  # type: ignore[attr-defined]
    finally:
        assert core.close() is True


def test_workspace_voice_cancel_is_discard_only_and_idempotent_after_cleanup(
    tmp_path: Path,
) -> None:
    events: list[dict[str, Any]] = []
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(final_text="Do not retain this canceled phrase.")
    core = _core(tmp_path / "data", audio=audio, adapter=adapter, events=events)
    try:
        context = _workspace_context(core)
        started = _call(core, VOICE_START, _start_params(context))
        capture_id = str(started["capture_id"])
        _feed_instruction(audio)
        cancelled = _call(
            core,
            VOICE_CANCEL,
            {"project_id": context["project_id"], "capture_id": capture_id},
        )
        assert cancelled == {
            "project_id": context["project_id"],
            "capture_id": capture_id,
            "stopped": True,
            "cancelled": True,
        }
        assert not audio.started
        assert core._asr.active_owner_details() is None  # type: ignore[attr-defined]
        assert (
            _call(
                core,
                VOICE_CANCEL,
                {"project_id": context["project_id"], "capture_id": capture_id},
            )["cancelled"]
            is False
        )
        assert not any(
            item.get("event") == "asr.final" and item["payload"].get("session_id") == capture_id
            for item in events
        )
    finally:
        assert core.close() is True
