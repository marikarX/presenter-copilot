"""Deterministic M9 release acceptance runner for E2E-01 through E2E-08."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import ASR_FRAME_SAMPLES, DeterministicFakeAudioInput
from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.adapters import ManualPresentationAdapter
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter

REPOSITORY_ROOT = Path(__file__).parents[3]
FIXTURE_ROOT = REPOSITORY_ROOT / "samples" / "synthetic-deck"
SAFE_CODE = re.compile(r"^[A-Z0-9_]{1,96}$")


class ReleaseAcceptanceFailure(Exception):
    """A safe, reportable acceptance failure without source or user content."""

    def __init__(self, code: str) -> None:
        self.code = code if SAFE_CODE.fullmatch(code) else "ACCEPTANCE_FAILED"
        super().__init__(self.code)


def _request_message(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "type": "request",
        "request_id": f"m9-{uuid.uuid4()}",
        "method": method,
        "params": params,
    }


def _call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(_request_message(method, params))
    if response.get("ok") is not True:
        error = response.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        raise ReleaseAcceptanceFailure(str(code or "REQUEST_FAILED"))
    result = response.get("result")
    if not isinstance(result, dict):
        raise ReleaseAcceptanceFailure("INVALID_RESULT")
    return result


def _expect_error(core: CoreService, method: str, params: dict[str, Any]) -> str:
    response = core.handle_message(_request_message(method, params))
    if response.get("ok") is not False:
        raise ReleaseAcceptanceFailure("EXPECTED_ERROR_MISSING")
    error = response.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    if not isinstance(code, str):
        raise ReleaseAcceptanceFailure("INVALID_ERROR")
    return code


def _project(core: CoreService, name: str, *, privacy_mode: str = "local_only") -> str:
    result = _call(core, "project.create", {"name": name, "privacy_mode": privacy_mode})
    project = result.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("id"), str):
        raise ReleaseAcceptanceFailure("PROJECT_CREATE_FAILED")
    return str(project["id"])


def _import(core: CoreService, project_id: str, path: Path, kind: str) -> dict[str, Any]:
    return _call(
        core,
        "source.import",
        {"project_id": project_id, "path": str(path.resolve()), "kind": kind},
    )


def _import_corpus(core: CoreService, project_id: str) -> None:
    _import(core, project_id, FIXTURE_ROOT / "deck" / "presentation.pptx", "presentation")
    _import(
        core,
        project_id,
        FIXTURE_ROOT / "supporting" / "architecture-notes.md",
        "supporting",
    )
    _import(core, project_id, FIXTURE_ROOT / "supporting" / "cost-model.pdf", "supporting")
    _call(core, "retrieval.rebuild", {"project_id": project_id})


def _new_core(
    data_root: Path,
    *,
    with_audio: bool = False,
    provider_locality: str = "remote",
) -> tuple[
    CoreService,
    DeterministicFakeAudioInput | None,
    DeterministicFakeASRAdapter,
    list[dict[str, Any]],
    threading.Event,
]:
    events: list[dict[str, Any]] = []
    final_seen = threading.Event()
    audio = DeterministicFakeAudioInput() if with_audio else None
    asr_adapter = DeterministicFakeASRAdapter(
        partial_texts=("what is the proposed", "what is the proposed cost"),
        final_text="What is the proposed cost reduction?",
    )

    def on_event(event: dict[str, Any]) -> None:
        events.append(event)
        if event.get("event") == "asr.final":
            final_seen.set()

    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        reasoning_provider=DeterministicFakeReasoningProvider(locality=provider_locality),
        audio_input=audio,
        asr_adapters={asr_adapter.id: asr_adapter},
        presentation_adapter=ManualPresentationAdapter(),
        event_sink=on_event,
    )
    return core, audio, asr_adapter, events, final_seen


def _close(core: CoreService) -> None:
    try:
        if not core.close():
            raise ReleaseAcceptanceFailure("CORE_CLOSE_FAILED")
    except CoreDomainError as error:
        raise ReleaseAcceptanceFailure(error.code) from error


def _e2e01(root: Path) -> None:
    core, _, _, _, _ = _new_core(root / "data")
    try:
        project_id = _project(core, "M9 E2E project")
        _import_corpus(core, project_id)
        sources = _call(core, "source.list", {"project_id": project_id}).get("sources")
        if not isinstance(sources, list) or len(sources) < 3:
            raise ReleaseAcceptanceFailure("IMPORT_INCOMPLETE")
        presentation = next(
            (
                item
                for item in sources
                if isinstance(item, dict) and item.get("kind") == "presentation"
            ),
            None,
        )
        if not isinstance(presentation, dict) or not isinstance(presentation.get("id"), str):
            raise ReleaseAcceptanceFailure("PRESENTATION_MISSING")
        preview = _call(
            core,
            "source.preview",
            {"project_id": project_id, "document_id": presentation["id"], "limit": 5},
        )
        if not preview.get("units"):
            raise ReleaseAcceptanceFailure("PROVENANCE_PREVIEW_EMPTY")
    finally:
        _close(core)


def _e2e02(root: Path) -> None:
    core, _, _, _, _ = _new_core(root / "data")
    try:
        project_id = _project(core, "M9 audience project")
        imported = _import(
            core,
            project_id,
            FIXTURE_ROOT / "transcript" / "PriorMeeting.vtt",
            "transcript",
        )
        document = imported.get("document")
        if not isinstance(document, dict) or not isinstance(document.get("id"), str):
            raise ReleaseAcceptanceFailure("TRANSCRIPT_IMPORT_FAILED")
        profile_ids: list[str] = []
        for name, role in (("Jane Smith", "CFO"), ("Robert Chen", "CTO")):
            profile = _call(
                core,
                "audience.create",
                {
                    "project_id": project_id,
                    "display_name": name,
                    "role": role,
                    "organization": "ExampleCo",
                },
            ).get("profile")
            if not isinstance(profile, dict) or not isinstance(profile.get("id"), str):
                raise ReleaseAcceptanceFailure("AUDIENCE_PROFILE_CREATE_FAILED")
            profile_ids.append(str(profile["id"]))
        speakers = _call(core, "transcript.list_speakers", {"project_id": project_id}).get(
            "speakers"
        )
        if not isinstance(speakers, list):
            raise ReleaseAcceptanceFailure("TRANSCRIPT_SPEAKER_LIST_FAILED")
        by_label = {
            str(item.get("native_speaker_label")): item
            for item in speakers
            if isinstance(item, dict) and item.get("native_speaker_label")
        }
        if not {"Jane Smith", "Robert Chen", "Conference Room"}.issubset(by_label):
            raise ReleaseAcceptanceFailure("TRANSCRIPT_LABELS_INCOMPLETE")
        for label, profile_id in zip(("Jane Smith", "Robert Chen"), profile_ids, strict=True):
            _call(
                core,
                "transcript.map_speaker",
                {
                    "project_id": project_id,
                    "document_id": document["id"],
                    "native_speaker_label": label,
                    "audience_profile_id": profile_id,
                },
            )
        for profile_id in profile_ids:
            extracted = _call(
                core,
                "audience.extract_observations",
                {"project_id": project_id, "audience_profile_id": profile_id},
            )
            candidates = extracted.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                raise ReleaseAcceptanceFailure("AUDIENCE_EXTRACTION_EMPTY")
            candidate = candidates[0]
            if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str):
                raise ReleaseAcceptanceFailure("AUDIENCE_CANDIDATE_INVALID")
            _call(
                core,
                "audience.accept_observation",
                {"project_id": project_id, "candidate_id": candidate["id"]},
            )
    finally:
        _close(core)


def _e2e03(root: Path) -> None:
    core, _, _, _, _ = _new_core(root / "data", provider_locality="remote")
    try:
        project_id = _project(core, "M9 teach project", privacy_mode="selected_context_cloud")
        _import_corpus(core, project_id)
        _call(core, "project.acknowledge_remote_reasoning", {"project_id": project_id})
        session = _call(core, "session.start", {"project_id": project_id, "mode": "teach"})[
            "session"
        ]
        session_id = str(session["id"])
        prompt = _call(
            core,
            "teach.next_prompt",
            {"project_id": project_id, "session_id": session_id},
        )
        if not prompt.get("question"):
            raise ReleaseAcceptanceFailure("TEACH_PROMPT_EMPTY")
        submitted = _call(
            core,
            "teach.submit_text",
            {
                "project_id": project_id,
                "session_id": session_id,
                "text": "We rejected the larger cutover because rollback would be harder.",
            },
        )
        candidate = submitted.get("candidate")
        if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str):
            raise ReleaseAcceptanceFailure("TEACH_CANDIDATE_MISSING")
        _call(
            core,
            "teach.confirm_knowledge_item",
            {
                "project_id": project_id,
                "session_id": session_id,
                "candidate_id": candidate["id"],
                "source_utterance_id": candidate["source_utterance_id"],
                "text": "We rejected the larger cutover because rollback would be harder.",
                "kind": "rationale",
                "preferred": True,
            },
        )
        retrieval = _call(
            core,
            "retrieval.query",
            {"project_id": project_id, "query": "rollback harder", "usage": "rehearsal"},
        )
        if not retrieval.get("hits"):
            raise ReleaseAcceptanceFailure("TEACH_KNOWLEDGE_NOT_RETRIEVABLE")
        _call(
            core,
            "session.stop",
            {"project_id": project_id, "session_id": session_id, "status": "completed"},
        )
    finally:
        _close(core)


def _e2e04(root: Path) -> None:
    core, _, _, _, _ = _new_core(root / "data", provider_locality="remote")
    try:
        project_id = _project(core, "M9 challenge project", privacy_mode="selected_context_cloud")
        _import_corpus(core, project_id)
        profiles: list[str] = []
        for name, role, observation in (
            ("Jane Smith", "CFO", "Prioritizes cost comparison and downside risk."),
            ("Robert Chen", "CTO", "Prioritizes RTO, availability, and rollback safety."),
        ):
            profile = _call(
                core,
                "audience.create",
                {"project_id": project_id, "display_name": name, "role": role},
            )["profile"]
            profile_id = str(profile["id"])
            profiles.append(profile_id)
            _call(
                core,
                "audience.create_observation",
                {
                    "project_id": project_id,
                    "audience_profile_id": profile_id,
                    "observation_type": "decision_criterion",
                    "text": observation,
                },
            )
        _call(core, "project.acknowledge_remote_reasoning", {"project_id": project_id})
        session_id = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "challenge"})[
                "session"
            ]["id"]
        )
        _call(
            core,
            "challenge.configure",
            {
                "project_id": project_id,
                "session_id": session_id,
                "audience_profile_ids": profiles,
                "intensity": "skeptical",
                "allow_follow_ups": True,
                "scope": "full_deck",
            },
        )
        question = _call(
            core,
            "challenge.next_question",
            {"project_id": project_id, "session_id": session_id},
        ).get("question")
        if not isinstance(question, dict) or not isinstance(question.get("id"), str):
            raise ReleaseAcceptanceFailure("CHALLENGE_QUESTION_MISSING")
        weak = _call(
            core,
            "challenge.submit_answer",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question["id"],
                "text": "It is a good proposal.",
            },
        )
        weak_answer = weak.get("answer_version")
        if not isinstance(weak_answer, dict) or not isinstance(weak_answer.get("id"), str):
            raise ReleaseAcceptanceFailure("CHALLENGE_WEAK_ANSWER_MISSING")
        _call(
            core,
            "challenge.retry_question",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question["id"],
            },
        )
        strong = _call(
            core,
            "challenge.submit_answer",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question["id"],
                "text": (
                    "We compare annual cost and downside with the current platform while "
                    "protecting RTO, availability, and rollback safety."
                ),
            },
        )
        strong_answer = strong.get("answer_version")
        if not isinstance(strong_answer, dict) or not isinstance(strong_answer.get("id"), str):
            raise ReleaseAcceptanceFailure("CHALLENGE_STRONG_ANSWER_MISSING")
        _call(
            core,
            "challenge.save_preferred_answer",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question_id": question["id"],
                "answer_version_id": strong_answer["id"],
            },
        )
        _call(
            core,
            "session.stop",
            {"project_id": project_id, "session_id": session_id, "status": "completed"},
        )
    finally:
        _close(core)


def _e2e05(root: Path) -> None:
    core, audio, asr_adapter, _, final_seen = _new_core(root / "data", with_audio=True)
    if audio is None:
        raise ReleaseAcceptanceFailure("AUDIO_FIXTURE_UNAVAILABLE")
    project_id: str | None = None
    session_id: str | None = None
    try:
        project_id = _project(core, "M9 run project")
        _import_corpus(core, project_id)
        session_id = str(
            _call(
                core,
                "session.start",
                {"project_id": project_id, "mode": "run", "current_slide_start": 1},
            )["session"]["id"]
        )
        _call(
            core,
            "asr.configure",
            {"adapter_id": asr_adapter.id, "model_id": asr_adapter.model_id, "language": "en"},
        )
        _call(core, "asr.start", {"project_id": project_id, "session_id": session_id})
        loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
        quiet = np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)
        audio.feed_frames([loud] * 8 + [quiet] * 31)
        if not final_seen.wait(5.0):
            raise ReleaseAcceptanceFailure("ASR_FINAL_NOT_OBSERVED")
        _call(core, "presentation.next_slide", {"project_id": project_id, "session_id": session_id})
        _call(core, "presentation.next_slide", {"project_id": project_id, "session_id": session_id})
        _call(
            core,
            "run.mark_event",
            {
                "project_id": project_id,
                "session_id": session_id,
                "marker_type": "weak_point",
                "timestamp_ms": 1000,
                "note": "Review the cost explanation.",
            },
        )
        _call(
            core,
            "run.mark_event",
            {
                "project_id": project_id,
                "session_id": session_id,
                "marker_type": "question",
                "timestamp_ms": 1500,
            },
        )
        stopped = _call(
            core,
            "session.stop",
            {"project_id": project_id, "session_id": session_id, "status": "completed"},
        )
        if not stopped.get("debrief"):
            raise ReleaseAcceptanceFailure("RUN_DEBRIEF_MISSING")
        transcript = _call(
            core,
            "run.list_transcript",
            {"project_id": project_id, "session_id": session_id, "limit": 10},
        )
        timeline = _call(
            core,
            "run.list_timeline",
            {"project_id": project_id, "session_id": session_id, "limit": 10},
        )
        if not transcript.get("total") or not timeline.get("total"):
            raise ReleaseAcceptanceFailure("RUN_PERSISTENCE_INCOMPLETE")
        _close(core)
        core = CoreService(
            data_root=root / "data",
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
            reasoning_provider=DeterministicFakeReasoningProvider(locality="remote"),
            audio_input=DeterministicFakeAudioInput(),
            asr_adapters={asr_adapter.id: DeterministicFakeASRAdapter()},
            presentation_adapter=ManualPresentationAdapter(),
        )
        recovered = _call(
            core,
            "run.get_state",
            {"project_id": project_id, "session_id": session_id},
        )
        if recovered.get("status") != "completed":
            raise ReleaseAcceptanceFailure("RUN_RECOVERY_FAILED")
        _call(core, "session.delete", {"project_id": project_id, "session_id": session_id})
        _call(core, "project.delete", {"project_id": project_id})
    finally:
        _close(core)


def _e2e06(root: Path) -> None:
    core, _, _, _, _ = _new_core(root / "data")
    try:
        project_id = _project(core, "M9 live project")
        _import_corpus(core, project_id)
        session_id = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "live_assist"})[
                "session"
            ]["id"]
        )
        started = _call(
            core,
            "assist.request",
            {
                "project_id": project_id,
                "session_id": session_id,
                "question": "What is the RTO?",
                "trigger": "typed",
            },
        )
        if not isinstance(started.get("assist_id"), str) or not core._assist.wait_for_idle(5.0):
            raise ReleaseAcceptanceFailure("LIVE_ASSIST_NOT_IDLE")
        cues = _call(
            core,
            "cue.list",
            {"project_id": project_id, "session_id": session_id, "limit": 10},
        )
        items = cues.get("cues")
        if not isinstance(items, list) or not items:
            raise ReleaseAcceptanceFailure("LIVE_CUE_MISSING")
        cue_id = items[0].get("id") if isinstance(items[0], dict) else None
        if not isinstance(cue_id, str):
            raise ReleaseAcceptanceFailure("LIVE_CUE_INVALID")
        expanded = _call(
            core,
            "cue.expand_sources",
            {"project_id": project_id, "session_id": session_id, "cue_id": cue_id},
        )
        if not expanded.get("sources"):
            raise ReleaseAcceptanceFailure("LIVE_PROVENANCE_MISSING")
        _call(
            core,
            "session.stop",
            {"project_id": project_id, "session_id": session_id, "status": "completed"},
        )
    finally:
        _close(core)


def _e2e07(root: Path) -> None:
    core, _, _, _, _ = _new_core(root / "data")
    project_id: str | None = None
    session_id: str | None = None
    try:
        project_id = _project(core, "M9 recovery project")
        session_id = str(
            _call(core, "session.start", {"project_id": project_id, "mode": "teach"})["session"][
                "id"
            ]
        )
        _call(
            core,
            "session.stop",
            {"project_id": project_id, "session_id": session_id, "status": "completed"},
        )
        _close(core)
        core = CoreService(
            data_root=root / "data",
            embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
            reasoning_provider=DeterministicFakeReasoningProvider(locality="remote"),
            asr_adapters={"deterministic-fake": DeterministicFakeASRAdapter()},
            presentation_adapter=ManualPresentationAdapter(),
        )
        _call(core, "project.open", {"project_id": project_id})
        recovered = _call(
            core,
            "session.get",
            {"project_id": project_id, "session_id": session_id},
        )
        if recovered.get("session", {}).get("status") != "completed":
            raise ReleaseAcceptanceFailure("SESSION_RECOVERY_FAILED")
    finally:
        _close(core)


def _e2e08(root: Path) -> None:
    core, _, _, _, _ = _new_core(root / "data")
    try:
        project_a = _project(core, "M9 delete A")
        project_b = _project(core, "M9 delete B")
        source_a = _import(
            core,
            project_a,
            FIXTURE_ROOT / "supporting" / "architecture-notes.md",
            "supporting",
        )
        _import(
            core,
            project_b,
            FIXTURE_ROOT / "supporting" / "cost-model.pdf",
            "supporting",
        )
        _call(core, "retrieval.rebuild", {"project_id": project_a})
        _call(core, "retrieval.rebuild", {"project_id": project_b})
        _call(core, "retrieval.query", {"project_id": project_a, "query": "rollback"})
        _call(core, "retrieval.query", {"project_id": project_b, "query": "cost"})
        _call(core, "project.delete", {"project_id": project_a})
        project_ids = {
            str(item.get("id"))
            for item in _call(core, "project.list", {}).get("projects", [])
            if isinstance(item, dict)
        }
        if project_a in project_ids or project_b not in project_ids:
            raise ReleaseAcceptanceFailure("PROJECT_REGISTRY_DELETE_FAILED")
        _expect_error(core, "retrieval.query", {"project_id": project_a, "query": "rollback"})
        surviving = _call(core, "retrieval.query", {"project_id": project_b, "query": "cost"})
        if surviving.get("project_id") != project_b or not source_a.get("document"):
            raise ReleaseAcceptanceFailure("PROJECT_CACHE_DELETE_FAILED")
    finally:
        _close(core)


SCENARIOS: tuple[tuple[str, Callable[[Path], None]], ...] = (
    ("E2E-01", _e2e01),
    ("E2E-02", _e2e02),
    ("E2E-03", _e2e03),
    ("E2E-04", _e2e04),
    ("E2E-05", _e2e05),
    ("E2E-06", _e2e06),
    ("E2E-07", _e2e07),
    ("E2E-08", _e2e08),
)


def _git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic M9 E2E acceptance scenarios.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / "m9-release-e2e.json",
        help="Metadata-only acceptance report path.",
    )
    args = parser.parse_args(argv)
    output = args.output if args.output.is_absolute() else REPOSITORY_ROOT / args.output
    results: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="presenter-copilot-m9-e2e-") as temporary:
        root = Path(temporary)
        for scenario_id, scenario in SCENARIOS:
            try:
                scenario(root / scenario_id)
            except ReleaseAcceptanceFailure as error:
                results.append({"id": scenario_id, "status": "failed", "code": error.code})
            except Exception:
                results.append(
                    {"id": scenario_id, "status": "failed", "code": "UNEXPECTED_FAILURE"}
                )
            else:
                results.append({"id": scenario_id, "status": "verified"})
    report = {
        "runner": "m9-release-e2e-v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "content_output": False,
        "scenarios": results,
        "all_passed": all(item["status"] == "verified" for item in results),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
