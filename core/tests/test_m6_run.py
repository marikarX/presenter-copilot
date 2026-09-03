from __future__ import annotations

import io
import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from presenter_core.asr.adapters import DeterministicFakeASRAdapter
from presenter_core.asr.audio import ASR_FRAME_SAMPLES, DeterministicFakeAudioInput
from presenter_core.asr.segmenter import UtteranceSegmenter, VADConfig
from presenter_core.ipc.core import CoreService
from presenter_core.ipc.server import SidecarServer
from presenter_core.presentation.adapters import ManualPresentationAdapter
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter
from presenter_core.storage.database import PROJECT_SCHEMA_VERSION, connect_project_database

FIXTURE_ROOT = Path(__file__).parents[2] / "samples" / "synthetic-deck"


def call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is True, response
    result = response["result"]
    assert isinstance(result, dict)
    return result


def error_call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
    )
    assert response["ok"] is False, response
    error = response["error"]
    assert isinstance(error, dict)
    return error


def make_core(
    data_root: Path,
    audio: DeterministicFakeAudioInput,
    adapter: DeterministicFakeASRAdapter,
    events: list[tuple[str, dict[str, Any]]],
) -> CoreService:
    return CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=audio,
        asr_adapters={adapter.id: adapter},
        presentation_adapter=ManualPresentationAdapter(),
        event_sink=lambda envelope: events.append(
            (str(envelope["event"]), dict(envelope["payload"]))
        ),
    )


def import_fixture(core: CoreService, project_id: str) -> None:
    call(
        core,
        "source.import",
        {
            "project_id": project_id,
            "kind": "presentation",
            "path": str(FIXTURE_ROOT / "deck" / "presentation.pptx"),
        },
    )
    call(
        core,
        "source.import",
        {
            "project_id": project_id,
            "kind": "supporting",
            "path": str(FIXTURE_ROOT / "supporting" / "architecture-notes.md"),
        },
    )


def test_vad_confirmation_silence_and_forced_finalization() -> None:
    loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
    quiet = np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)
    segmenter = UtteranceSegmenter()
    for index in range(5):
        assert segmenter.process(loud, index * 20) is None
    assert segmenter.speech_active is False
    assert segmenter.process(loud, 100) is None
    assert segmenter.speech_active is True
    for index in range(29):
        completed = segmenter.process(quiet, 120 + index * 20)
    assert completed is None
    completed = segmenter.process(quiet, 700)
    assert completed is not None
    assert completed.start_ms == 0
    assert completed.end_ms == 720

    forced = UtteranceSegmenter(VADConfig(max_continuous_utterance_ms=100))
    forced_result = None
    for index in range(8):
        forced_result = forced.process(loud, index * 20)
        if forced_result is not None:
            break
    assert forced_result is not None
    assert forced_result.forced is True


def test_m6_run_e2e_persists_final_only_timeline_debrief_and_restarts(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    events: list[tuple[str, dict[str, Any]]] = []
    final_seen = threading.Event()

    def on_event(event: str, payload: dict[str, Any]) -> None:
        events.append((event, payload))
        if event == "asr.final":
            final_seen.set()

    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(
        partial_texts=("the three year", "the three year cost drops"),
        final_text="The three year cost drops by eighteen percent.",
    )
    core = CoreService(
        data_root=data_root,
        embedding_adapter=DeterministicEmbeddingAdapter(dimension=4),
        audio_input=audio,
        asr_adapters={adapter.id: adapter},
        presentation_adapter=ManualPresentationAdapter(),
        event_sink=lambda envelope: on_event(str(envelope["event"]), dict(envelope["payload"])),
    )
    project_id = str(call(core, "project.create", {"name": "M6 disposable"})["project"]["id"])
    import_fixture(core, project_id)
    call(core, "retrieval.rebuild", {"project_id": project_id})

    session_id = str(
        call(
            core,
            "session.start",
            {"project_id": project_id, "mode": "run", "current_slide_start": 1},
        )["session"]["id"]
    )
    assert call(core, "asr.list_devices", {})["devices"][0]["display_name"]
    call(core, "asr.configure", {"device_id": "fake-microphone"})
    call(core, "asr.start", {"project_id": project_id, "session_id": session_id})
    assert (
        error_call(core, "asr.start", {"project_id": project_id, "session_id": session_id})["code"]
        == "ASR_ALREADY_RUNNING"
    )
    assert (
        error_call(
            core,
            "asr.configure",
            {"device_id": "fake-microphone", "language": "en"},
        )["code"]
        == "ASR_BUSY"
    )
    assert (
        error_call(
            core,
            "run.generate_debrief",
            {"project_id": project_id, "session_id": session_id},
        )["code"]
        == "RUN_SESSION_ACTIVE"
    )

    loud = np.full(ASR_FRAME_SAMPLES, 0.1, dtype=np.float32)
    quiet = np.zeros(ASR_FRAME_SAMPLES, dtype=np.float32)
    audio.feed_frames([loud] * 12 + [quiet] * 35)
    assert final_seen.wait(5.0)
    final_events = [payload for event, payload in events if event == "asr.final"]
    assert len(final_events) == 1
    assert final_events[0]["utterance_id"]
    assert all(event != "asr.partial" or payload["is_final"] is False for event, payload in events)

    call(core, "presentation.next_slide", {"project_id": project_id, "session_id": session_id})
    call(core, "presentation.next_slide", {"project_id": project_id, "session_id": session_id})
    call(core, "presentation.previous_slide", {"project_id": project_id, "session_id": session_id})
    call(
        core,
        "run.mark_event",
        {
            "project_id": project_id,
            "session_id": session_id,
            "marker_type": "weak_point",
            "note": "Clarify the cost assumption.",
        },
    )
    call(
        core,
        "run.mark_event",
        {"project_id": project_id, "session_id": session_id, "marker_type": "question"},
    )
    stopped = call(
        core,
        "session.stop",
        {"project_id": project_id, "session_id": session_id, "status": "completed"},
    )
    assert stopped["session"]["status"] == "completed"
    assert stopped["debrief"]["algorithm_version"] == "m6-deterministic-v1"
    assert adapter.close_count >= 1
    assert audio.started is False

    transcript = call(
        core,
        "run.list_transcript",
        {"project_id": project_id, "session_id": session_id, "limit": 10},
    )
    assert len(transcript["utterances"]) == 1
    assert transcript["utterances"][0]["text"] == final_events[0]["text"]
    assert transcript["utterances"][0]["slide_ordinal"] == 1
    timeline = call(
        core,
        "run.list_timeline",
        {"project_id": project_id, "session_id": session_id, "limit": 2},
    )
    assert timeline["total"] >= 4
    assert len(timeline["timeline"]) == 2
    assert {marker["marker_type"] for marker in timeline["markers"]} <= {"question", "weak_point"}
    debrief = call(core, "run.get_debrief", {"project_id": project_id, "session_id": session_id})
    reused = call(
        core,
        "run.generate_debrief",
        {"project_id": project_id, "session_id": session_id},
    )
    assert reused["reused"] is True
    assert reused["debrief"] == debrief["debrief"]
    core.close()

    restarted = make_core(
        data_root, DeterministicFakeAudioInput(), DeterministicFakeASRAdapter(), []
    )
    try:
        state = call(
            restarted, "run.get_state", {"project_id": project_id, "session_id": session_id}
        )
        assert state["status"] == "completed"
        assert (
            call(
                restarted,
                "run.list_transcript",
                {"project_id": project_id, "session_id": session_id, "limit": 10},
            )["utterances"]
            == transcript["utterances"]
        )
        assert (
            call(
                restarted,
                "run.get_debrief",
                {"project_id": project_id, "session_id": session_id},
            )["debrief"]
            == debrief["debrief"]
        )
        cache_path = data_root / "models" / "asr"
        cache_path.mkdir(parents=True, exist_ok=True)
        assert (
            call(
                restarted,
                "session.delete",
                {"project_id": project_id, "session_id": session_id},
            )["deleted"]
            is True
        )
        assert call(restarted, "project.delete", {"project_id": project_id})["deleted"] is True
        assert cache_path.is_dir()
    finally:
        restarted.close()


def test_missing_model_is_not_prepared_implicitly_and_shutdown_releases_capture(
    tmp_path: Path,
) -> None:
    audio = DeterministicFakeAudioInput()
    adapter = DeterministicFakeASRAdapter(model_installed=False)
    core = make_core(tmp_path / "data", audio, adapter, [])
    try:
        project_id = str(call(core, "project.create", {"name": "missing model"})["project"]["id"])
        session_id = str(
            call(core, "session.start", {"project_id": project_id, "mode": "run"})["session"]["id"]
        )
        missing = error_call(
            core, "asr.start", {"project_id": project_id, "session_id": session_id}
        )
        assert missing["code"] == "ASR_MODEL_UNAVAILABLE"
        assert adapter.load_count == 0
        call(core, "asr.prepare_model", {})
        call(core, "asr.start", {"project_id": project_id, "session_id": session_id})
        core.close()
        assert audio.started is False
        assert audio.close_count >= 1
    finally:
        core.close()


def test_project_v6_migration_and_future_rejection_preserve_existing_rows(tmp_path: Path) -> None:
    path = tmp_path / "project.db"
    project_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    source_unit_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    statement_id = str(uuid.uuid4())
    knowledge_item_id = str(uuid.uuid4())
    provider_run_id = str(uuid.uuid4())
    audience_id = str(uuid.uuid4())
    observation_id = str(uuid.uuid4())
    challenge_audience_id = str(uuid.uuid4())
    question_id = str(uuid.uuid4())
    answer_id = str(uuid.uuid4())
    generation_id = str(uuid.uuid4())
    now = "2026-09-03T00:00:00.000Z"
    with sqlite3.connect(path) as connection:
        from presenter_core.storage.database import (
            _migrate_project_v1,
            _migrate_project_v2,
            _migrate_project_v3,
            _migrate_project_v4,
            _migrate_project_v5,
        )

        connection.execute("PRAGMA foreign_keys = ON")
        _migrate_project_v1(connection)
        connection.execute(
            "INSERT INTO project (id, name, created_at, updated_at, privacy_mode, "
            "default_style_policy, custom_style_guidance, current_presentation_id, schema_version) "
            "VALUES (?, 'populated v5', ?, ?, 'local_only', 'preserve_voice', ?, ?, 1)",
            (project_id, now, now, "Keep the direct voice.", document_id),
        )
        connection.execute(
            "INSERT INTO documents "
            "(id, project_id, kind, original_name, local_snapshot_path, source_uri, sha256, "
            "mime_type, parser_id, imported_at, parse_status, parse_error_code, "
            "parse_error_message, byte_size, metadata_json) "
            "VALUES (?, ?, 'presentation', 'legacy.pptx', 'sources/legacy.pptx', NULL, ?, "
            "'application/vnd.openxmlformats-officedocument.presentationml.presentation', "
            "'pptx.python-pptx', ?, 'ready', NULL, NULL, 1234, ?)",
            (document_id, project_id, "a" * 64, now, '{"fixture":true}'),
        )
        connection.execute(
            "INSERT INTO source_units "
            "(id, document_id, unit_type, ordinal, title, start_ms, end_ms, speaker_label, "
            "text, metadata_json) VALUES (?, ?, 'slide', 7, 'Recovery', NULL, NULL, NULL, ?, ?)",
            (source_unit_id, document_id, "The recovery time objective is 30 minutes.", "{}"),
        )
        connection.execute(
            "INSERT INTO chunks "
            "(id, source_unit_id, chunk_index, text, token_count, embedding_key, "
            "lexical_text, created_at) "
            "VALUES (?, ?, 0, ?, 8, ?, ?, ?)",
            (
                chunk_id,
                source_unit_id,
                "The recovery time objective is 30 minutes.",
                f"{generation_id}:{chunk_id}",
                "the recovery time objective is 30 minutes",
                now,
            ),
        )
        _migrate_project_v2(connection)
        connection.execute(
            "INSERT INTO embedding_generations "
            "(id, adapter_id, model_id, model_fingerprint, dimension, matrix_relative_path, "
            "matrix_row_count, is_active, created_at) VALUES (?, 'fixture', 'fixture-v2', ?, 4, "
            "'embeddings/vectors.npy', 1, 1, ?)",
            (generation_id, "b" * 32, now),
        )
        connection.execute(
            "INSERT INTO embedding_vectors "
            "(generation_id, vector_id, entity_type, entity_id, project_id, source_class, "
            "row_index, content_sha256) VALUES (?, ?, 'chunk', ?, ?, 'document', 0, ?)",
            (generation_id, chunk_id, chunk_id, project_id, "c" * 64),
        )
        _migrate_project_v3(connection)
        connection.execute(
            "INSERT INTO sessions "
            "(id, project_id, mode, started_at, ended_at, style_policy, privacy_mode, provider_id, "
            "current_slide_start, status, teach_state) VALUES (?, ?, 'challenge', ?, ?, "
            "'preserve_voice', 'local_only', 'fixture-provider', 7, 'completed', 'completed')",
            (session_id, project_id, now, now),
        )
        connection.execute(
            "INSERT INTO utterances "
            "(id, session_id, actor, text, created_at, start_ms, end_ms, asr_confidence, "
            "slide_ordinal, is_final) VALUES (?, ?, 'user', ?, ?, 0, 500, NULL, 7, 1)",
            (str(uuid.uuid4()), session_id, "The recovery time objective is 30 minutes.", now),
        )
        connection.execute(
            "INSERT INTO user_statements "
            "(id, project_id, origin_session_id, source_utterance_id, text, created_at) "
            "VALUES (?, ?, ?, NULL, ?, ?)",
            (
                statement_id,
                project_id,
                session_id,
                "The recovery time objective is 30 minutes.",
                now,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge_items "
            "(id, project_id, kind, text, use_live, use_rehearsal, preferred, private, "
            "created_by, origin_session_id, created_at, updated_at) VALUES (?, ?, 'answer', ?, "
            "1, 1, 1, 0, 'user', ?, ?, ?)",
            (
                knowledge_item_id,
                project_id,
                "The recovery time objective is 30 minutes.",
                session_id,
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge_evidence "
            "(knowledge_item_id, provenance_type, provenance_id) VALUES (?, 'document', ?)",
            (knowledge_item_id, document_id),
        )
        connection.execute(
            "INSERT INTO provider_runs "
            "(id, session_id, task_type, provider_id, privacy_mode, started_at, ended_at, status, "
            "input_token_count, output_token_count, latency_ms, context_manifest_json, error_code) "
            "VALUES (?, ?, 'challenge_question', 'fixture-provider', 'local_only', ?, ?, "
            "'success', "
            "11, 17, 42, ?, NULL)",
            (provider_run_id, session_id, now, now, '{"evidence":["' + chunk_id + '"]}'),
        )
        _migrate_project_v4(connection)
        connection.execute(
            "INSERT INTO audience_profiles "
            "(id, project_id, display_name, role, organization, user_notes, active, created_at, "
            "updated_at) "
            "VALUES (?, ?, 'CFO', 'Finance', 'Example Co', 'Wants exact costs', 1, ?, ?)",
            (audience_id, project_id, now, now),
        )
        connection.execute(
            "INSERT INTO audience_observations "
            "(id, audience_profile_id, observation_type, text, derivation, confidence, "
            "sensitive_trait, review_status, created_at, updated_at) VALUES (?, ?, "
            "'decision_criterion', "
            "'Needs a quantified recovery plan', 'user_entered', 1.0, 0, 'active', ?, ?)",
            (observation_id, audience_id, now, now),
        )
        connection.execute(
            "INSERT INTO audience_observation_evidence "
            "(observation_id, provenance_type, provenance_id) VALUES (?, 'transcript', ?)",
            (observation_id, statement_id),
        )
        _migrate_project_v5(connection)
        connection.execute(
            "INSERT INTO challenge_configurations "
            "(session_id, intensity, allow_follow_ups, scope, slide_start, slide_end, state, "
            "created_at, updated_at) VALUES (?, 'skeptical', 1, 'slide_range', 7, 9, "
            "'evaluated', ?, ?)",
            (session_id, now, now),
        )
        connection.execute(
            "INSERT INTO challenge_audiences "
            "(id, session_id, audience_profile_id, selection_order, display_name_snapshot, "
            "role_snapshot, organization_snapshot, selected_at) VALUES (?, ?, ?, 0, 'CFO', "
            "'Finance', "
            "'Example Co', ?)",
            (challenge_audience_id, session_id, audience_id, now),
        )
        connection.execute(
            "INSERT INTO questions "
            "(id, session_id, asked_by_audience_profile_id, parent_question_id, provider_run_id, "
            "audience_display_name_snapshot, audience_role_snapshot, text, origin, rationale, "
            "created_at) "
            "VALUES (?, ?, ?, NULL, ?, 'CFO', 'Finance', 'Why 30 minutes?', 'simulated', "
            "'Exact RTO support', ?)",
            (question_id, session_id, audience_id, provider_run_id, now),
        )
        connection.execute(
            "INSERT INTO question_evidence "
            "(question_id, evidence_id, source_type, source_id, source_unit_id, label, available) "
            "VALUES (?, ?, 'document', ?, ?, 'legacy.pptx slide 7', 1)",
            (question_id, chunk_id, document_id, source_unit_id),
        )
        connection.execute(
            "INSERT INTO question_audience_observations "
            "(question_id, observation_id, available) VALUES (?, ?, 1)",
            (question_id, observation_id),
        )
        connection.execute(
            "INSERT INTO answer_versions "
            "(id, question_id, session_id, provider_run_id, text, origin, preferred, "
            "correctness_score, "
            "directness_score, completeness_score, concision_score, style_match_score, "
            "source_support_status, "
            "source_support_feedback, evaluation_json, created_at) VALUES (?, ?, ?, ?, ?, "
            "'user_typed', 1, "
            "0.9, 0.8, 0.95, 0.8, 0.9, 'supported', 'Matches source', ?, ?)",
            (
                answer_id,
                question_id,
                session_id,
                provider_run_id,
                "The recovery time objective is 30 minutes.",
                '{"score":0.87}',
                now,
            ),
        )
        connection.execute(
            "INSERT INTO answer_evidence "
            "(answer_version_id, evidence_id, source_type, source_id, source_unit_id, "
            "label, available) "
            "VALUES (?, ?, 'document', ?, ?, 'legacy.pptx slide 7', 1)",
            (answer_id, chunk_id, document_id, source_unit_id),
        )
        connection.execute(
            "INSERT INTO challenge_answer_promotions "
            "(question_id, answer_version_id, knowledge_item_id, promoted_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (question_id, answer_id, knowledge_item_id, now, now),
        )
        connection.execute("PRAGMA user_version = 5")
        connection.commit()

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        before_tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        }
        before_rows: dict[str, list[tuple[Any, ...]]] = {}
        for table in sorted(before_tables):
            before_rows[table] = [
                tuple(row) for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            ]
    assert connection is not None
    migrated = connect_project_database(path)
    assert migrated.execute("PRAGMA user_version").fetchone()[0] == PROJECT_SCHEMA_VERSION == 6
    assert migrated.execute("SELECT schema_version FROM project").fetchone()[0] == 6
    tables = {
        row[0]
        for row in migrated.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {"slide_state_events", "run_markers", "run_debriefs"} <= tables
    assert tables.difference(before_tables) == {"slide_state_events", "run_markers", "run_debriefs"}
    for table, rows in before_rows.items():
        after_rows = [
            tuple(row) for row in migrated.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
        ]
        if table == "project":
            columns = [row[1] for row in migrated.execute(f'PRAGMA table_info("{table}")')]
            schema_index = columns.index("schema_version")
            normalized = [row[:schema_index] + (5,) + row[schema_index + 1 :] for row in after_rows]
            assert normalized == rows
        else:
            assert after_rows == rows
    migrated.close()
    with sqlite3.connect(path) as connection:
        before_future = {
            table: [
                tuple(row) for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            ]
            for table in sorted(tables)
        }
        connection.execute("PRAGMA user_version = 7")
        connection.commit()
    try:
        connect_project_database(path)
    except Exception as error:
        assert getattr(error, "code", None) == "DATABASE_VERSION_UNSUPPORTED"
    else:  # pragma: no cover
        raise AssertionError("future schema was accepted")
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        for table, rows in before_future.items():
            assert [
                tuple(row) for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            ] == rows


def test_sidecar_write_serializes_complete_ndjson_lines() -> None:
    class BlockingWriter(io.StringIO):
        first_entered = threading.Event()
        release_first = threading.Event()
        second_entered = threading.Event()
        calls = 0

        def write(self, value: str) -> int:
            type(self).calls += 1
            if type(self).calls == 1:
                type(self).first_entered.set()
                assert type(self).release_first.wait(2.0)
            else:
                type(self).second_entered.set()
            return super().write(value)

    class StubCore:
        def set_event_sink(self, _sink: Any) -> None:
            return

    output = BlockingWriter()
    server = SidecarServer(io.StringIO(), output, core=StubCore())  # type: ignore[arg-type]
    first = threading.Thread(target=server._write, args=({"event": "asr.partial", "n": 1},))
    second = threading.Thread(target=server._write, args=({"ok": True, "n": 2},))
    first.start()
    assert output.first_entered.wait(2.0)
    second.start()
    assert output.second_entered.wait(0.05) is False
    output.release_first.set()
    first.join(2.0)
    second.join(2.0)
    assert first.is_alive() is False
    assert second.is_alive() is False
    lines = output.getvalue().splitlines()
    assert [json.loads(line) for line in lines] == [
        {"event": "asr.partial", "n": 1},
        {"ok": True, "n": 2},
    ]
