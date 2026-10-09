"""Project-local, explicitly saved outline conversations with immutable provenance."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.creation import PresentationCreationService
from presenter_core.project.service import utc_now
from presenter_core.providers.models import ProviderError, validate_provider_output
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager


class OutlineDraftService:
    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage

    def capture(self, project: str, proposal: dict[str, Any], request: dict[str, Any]) -> None:
        with self._storage.project_database(project) as connection:
            connection.execute(
                "INSERT INTO presentation_outline_proposals VALUES (?, ?, ?)",
                (proposal["provider_run_id"], json.dumps(proposal), json.dumps(request)),
            )
            connection.commit()

    @staticmethod
    def _project(params: dict[str, Any]) -> str:
        if not isinstance(params.get("project_id"), str):
            raise invalid_request("project_id must be a UUID.")
        return normalize_project_id(params["project_id"])

    @staticmethod
    def _fields(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict) or set(raw) != {
            "objective",
            "audience",
            "briefing",
            "slide_count",
            "instruction",
        }:
            raise invalid_request("The saved planning fields are invalid.")
        for key, limit in (
            ("objective", 500),
            ("audience", 300),
            ("briefing", 2000),
            ("instruction", 500),
        ):
            PresentationCreationService._text(raw[key], key, limit, allow_empty=True)
        count = raw["slide_count"]
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 40:
            raise invalid_request("Choose between 1 and 40 slides.")
        return raw

    @staticmethod
    def _content(proposal: Any) -> dict[str, Any]:
        if not isinstance(proposal, dict):
            raise invalid_request("The saved outline is invalid.")
        try:
            return validate_provider_output(
                "presentation_outline",
                {key: proposal.get(key) for key in ("title", "rationale", "slides")},
            )
        except ProviderError as error:
            raise invalid_request("The saved outline content is invalid.") from error

    def _validate(self, connection: sqlite3.Connection, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict) or set(payload) != {"conversation", "fields"}:
            raise invalid_request("The saved drafting session is invalid.")
        self._fields(payload["fields"])
        conversation = payload["conversation"]
        if not isinstance(conversation, dict) or set(conversation) != {"turns", "activeRunId"}:
            raise invalid_request("The saved conversation is invalid.")
        turns = conversation["turns"]
        if not isinstance(turns, list) or not 1 <= len(turns) <= 10:
            raise invalid_request("Save between 1 and 10 outline drafts.")
        seen: dict[str, dict[str, Any]] = {}
        for index, turn in enumerate(turns):
            if (
                not isinstance(turn, dict)
                or set(turn)
                != {"ordinal", "request", "parentRunId", "baseline", "original", "draft"}
                or type(turn["ordinal"]) is not int
                or turn["ordinal"] != index + 1
            ):
                raise invalid_request("The saved draft order is invalid.")
            original = turn["original"]
            if not isinstance(original, dict) or not isinstance(
                original.get("provider_run_id"), str
            ):
                raise invalid_request("The saved draft provenance is invalid.")
            run = original["provider_run_id"]
            row = connection.execute(
                "SELECT p.proposal_json, p.request_json FROM presentation_outline_proposals p "
                "JOIN provider_runs r ON r.id = p.provider_run_id "
                "WHERE p.provider_run_id = ? AND r.task_type = 'presentation_outline' "
                "AND r.status = 'success'",
                (run,),
            ).fetchone()
            if row is None or run in seen or original != json.loads(row["proposal_json"]):
                raise invalid_request(
                    "The saved draft does not match its original project proposal."
                )
            request = self._fields(turn["request"])
            captured = json.loads(row["request_json"])
            normalized = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in request.items()
            }
            if normalized != {key: captured[key] for key in request}:
                raise invalid_request("The saved draft request changed.")
            draft = turn["draft"]
            checked = self._content(draft)
            if (
                not isinstance(draft, dict)
                or set(draft) != set(original)
                or any(
                    draft[key] != original[key]
                    for key in original
                    if key not in {"title", "slides"}
                )
            ):
                raise invalid_request("The edited draft changed its provenance.")
            supplied = {item["evidence_id"] for item in original["evidence"]}
            if any(
                evidence not in supplied
                for slide in checked["slides"]
                for evidence in slide["evidence_ids"]
            ):
                raise invalid_request("The edited draft cites unknown evidence.")
            parent = turn["parentRunId"]
            baseline = turn["baseline"]
            if parent is None:
                if baseline is not None or captured["prior_outline"] is not None:
                    raise invalid_request("The initial draft has an invalid baseline.")
            else:
                if (
                    not isinstance(parent, str)
                    or parent not in seen
                    or not isinstance(baseline, dict)
                ):
                    raise invalid_request("The saved draft branch is invalid.")
                ancestor = seen[parent]
                if (
                    set(baseline) != set(ancestor)
                    or any(
                        baseline[key] != ancestor[key]
                        for key in ancestor
                        if key not in {"title", "slides"}
                    )
                    or self._content(baseline) != captured["prior_outline"]
                ):
                    raise invalid_request("The saved request baseline changed.")
            seen[run] = original
        if (
            not isinstance(conversation["activeRunId"], str)
            or conversation["activeRunId"] not in seen
        ):
            raise invalid_request("Select an existing saved draft.")
        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 8 * 1024 * 1024:
            raise invalid_request("The drafting session is too large to save.")
        return payload

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id"})
        project = self._project(params)
        with self._storage.project_database(project) as connection:
            return self._read(connection, project)

    def _read(self, connection: sqlite3.Connection, project: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM presentation_outline_sessions WHERE project_id = ?", (project,)
        ).fetchone()
        payload = json.loads(row["payload_json"]) if row and row["payload_json"] else None
        if payload is not None:
            self._validate(connection, payload)
        return {
            "record_token": row["record_token"] if row else None,
            "updated_at": row["updated_at"] if row else None,
            "payload": payload,
        }

    def save(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._write(params, clear=False)

    def clear(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._write(params, clear=True)

    def _write(self, params: dict[str, Any], *, clear: bool) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "expected_record_token"} | (set() if clear else {"payload"})
        )
        project = self._project(params)
        if "expected_record_token" not in params:
            raise invalid_request("Supply the saved session record token.")
        expected = params["expected_record_token"]
        if expected is not None:
            try:
                expected = str(uuid.UUID(expected))
            except (ValueError, TypeError, AttributeError) as error:
                raise invalid_request("The saved session record token is invalid.") from error
        with self._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._read(connection, project)
            if current["record_token"] != expected:
                raise CoreDomainError(
                    "PRESENTATION_OUTLINE_SESSION_CONFLICT",
                    "The saved drafting session changed in another view. Reload before saving.",
                    retryable=True,
                )
            payload = None if clear else self._validate(connection, params.get("payload"))
            connection.execute(
                "INSERT INTO presentation_outline_sessions VALUES (?, ?, ?, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET record_token=excluded.record_token, "
                "payload_json=excluded.payload_json, updated_at=excluded.updated_at",
                (project, str(uuid.uuid4()), json.dumps(payload) if payload else None, utc_now()),
            )
            result = self._read(connection, project)
            connection.commit()
            return result
