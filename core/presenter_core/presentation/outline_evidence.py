"""Trace reviewed creation citations to native points without approving evidence."""

import json
import re
from typing import Any, cast

from presenter_core.errors import invalid_request, reject_unknown_fields
from presenter_core.presentation.claims import PresentationClaimService, digest
from presenter_core.presentation.creation import PresentationCreationService
from presenter_core.presentation.semantics import PresentationSemanticService


class OutlineEvidenceService:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics
        self._claims = PresentationClaimService(semantics)

    def list_candidates(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "document_id", "revision_id", "offset", "limit"}
        )
        offset, limit = params.get("offset", 0), params.get("limit", 20)
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 320:
            raise invalid_request("offset must be an integer from 0 to 320.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise invalid_request("limit must be an integer from 1 to 20.")
        scope = {key: params.get(key) for key in ("project_id", "document_id", "revision_id")}
        service = self._semantics
        project, document, revision, current = service._workspace_sources.read_revision_inventory(
            scope
        )
        result: dict[str, Any] = {
            "document_id": document,
            "revision_id": revision,
            "offset": offset,
            "limit": limit,
            "has_receipt": False,
            "has_more": False,
            "total_points": 0,
            "items": [],
            "citation_only_slides": [],
            "requires_user_review": True,
        }
        with service._storage.project_database(project) as connection:
            row = connection.execute(
                "SELECT metadata_json FROM documents WHERE id=? AND project_id=?",
                (document, project),
            ).fetchone()
            try:
                metadata = json.loads(row[0]) if row else {}
                if not isinstance(metadata, dict):
                    raise ValueError("Invalid metadata")
                receipt = metadata.get("outline_evidence_receipt")
            except (ValueError, TypeError) as exc:
                raise invalid_request("The outline evidence metadata is invalid.") from exc
            if receipt is None:
                service._require_current_presentation(connection, project, document, revision)
                return result
            self._validate_receipt(receipt)
            captured = connection.execute(
                "SELECT p.proposal_json FROM presentation_outline_proposals p "
                "JOIN provider_runs r ON r.id=p.provider_run_id "
                "WHERE p.provider_run_id=? AND r.task_type='presentation_outline' "
                "AND r.status='success'",
                (receipt["provider_run_id"],),
            ).fetchone()
            supplied = self._supplied(captured[0]) if captured else {}
            if captured and any(
                key not in supplied for slide in receipt["slides"] for key in slide["evidence_ids"]
            ):
                raise invalid_request("The outline receipt cites evidence that was not supplied.")
        original_id = receipt["original_revision_id"]
        original = (
            current
            if original_id == revision
            else service._workspace_sources.read_revision_inventory(
                {**scope, "revision_id": original_id}, current_only=False
            )[-1]
        )
        if original.source_sha256 != receipt["original_sha256"]:
            raise invalid_request(
                "The outline receipt does not match its original native snapshot."
            )
        rows: list[dict[str, Any]] = []
        current_slides = {slide.slide_id: slide for slide in current.slides}
        citations: dict[str, dict[str, Any]] = {}
        with service._storage.project_database(project) as connection:
            for slide in receipt["slides"]:
                for evidence_id in slide["evidence_ids"]:
                    if evidence_id not in citations:
                        captured_excerpt = supplied.get(evidence_id)
                        source = self._claims._evidence(connection, project, evidence_id)
                        citations[evidence_id] = self._reference(
                            evidence_id, captured_excerpt, source
                        )
        missing_points: list[dict[str, Any]] = []
        for slide in receipt["slides"]:
            if not slide["evidence_ids"]:
                continue
            if not slide["points"]:
                missing_points.append(
                    {"original_slide_number": slide["slide_number"], "reason": "no_native_points"}
                )
            original_slide = next(
                (s for s in original.slides if s.ordinal == slide["slide_number"]), None
            )
            source_targets = cast(
                list[dict[str, Any]],
                (
                    original.text_targets(
                        original_slide.ordinal, limit=len(original_slide.objects)
                    )["semantic_targets"]
                    if original_slide
                    else []
                ),
            )
            current_slide = current_slides.get(original_slide.slide_id) if original_slide else None
            native = cast(
                list[dict[str, Any]],
                (
                    current.text_targets(current_slide.ordinal, limit=len(current_slide.objects))[
                        "semantic_targets"
                    ]
                    if current_slide
                    else []
                ),
            )
            for index, quote in enumerate(slide["points"], 1):
                matches = [
                    t
                    for t in source_targets
                    if t["name"] == f"Point {index}"
                    and t["decision_text"] == quote
                    and t["source_kind"] == "native_text"
                ]
                target = matches[0] if len(matches) == 1 else None
                current_target = next(
                    (t for t in native if target and t["object_id"] == target["object_id"]), None
                )
                status = (
                    "ambiguous_original"
                    if len(matches) > 1
                    else "missing_original"
                    if target is None
                    else "missing"
                    if current_target is None
                    else "unchanged"
                    if current_target["source_kind"] == "native_text"
                    and current_target["decision_text"] == quote
                    else "changed"
                )
                rows.append(
                    {
                        "original_slide_number": slide["slide_number"],
                        "point_number": index,
                        "slide_id": original_slide.slide_id if original_slide else None,
                        "slide_number": current_slide.ordinal if current_slide else None,
                        "object_id": target["object_id"] if target else None,
                        "quote": quote,
                        "object_sha256": digest(quote),
                        "source_kind": "native_text",
                        "span_status": status,
                        "reviewable": status == "unchanged",
                        "references": [citations[key] for key in slide["evidence_ids"]],
                    }
                )
        with service._storage.project_database(project) as connection:
            service._require_current_presentation(connection, project, document, revision)
        return {
            **result,
            "has_receipt": True,
            "provider_run_id": receipt["provider_run_id"],
            "original_revision_id": original_id,
            "original_sha256": receipt["original_sha256"],
            "planning_record_available": captured is not None,
            "total_points": len(rows),
            "items": rows[offset : offset + limit],
            "has_more": offset + limit < len(rows),
            "citation_only_slides": missing_points,
        }

    @staticmethod
    def _supplied(raw: str) -> dict[str, dict[str, Any]]:
        try:
            proposal = json.loads(raw)
            evidence = proposal["evidence"]
            if not isinstance(evidence, list):
                raise ValueError("Invalid evidence")
            supplied: dict[str, dict[str, Any]] = {}
            for item in evidence:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("evidence_id"), str)
                    or not isinstance(item.get("text"), str)
                    or item["evidence_id"] in supplied
                ):
                    raise ValueError("Invalid evidence entry")
                supplied[item["evidence_id"]] = item
            return supplied
        except (ValueError, TypeError, KeyError) as exc:
            raise invalid_request("The original outline evidence record is invalid.") from exc

    @staticmethod
    def _reference(
        evidence_id: str, captured: dict[str, Any] | None, source: Any
    ) -> dict[str, Any]:
        excerpt = captured.get("text", "") if captured else ""
        comparable = isinstance(excerpt, str) and bool(excerpt.strip())
        text: str = str(source["text"]) if source is not None else ""
        non_chunk = captured is not None and captured.get("source_type") == "user_statement"
        linkable = (
            captured is not None
            and not non_chunk
            and source is not None
            and isinstance(text, str)
            and 0 < len(text) <= 8000
        )
        return {
            "evidence_id": evidence_id,
            "original_excerpt": excerpt[:800] if isinstance(excerpt, str) else "",
            "original_excerpt_truncated": isinstance(excerpt, str) and len(excerpt) > 800,
            "original_source_type": captured.get("source_type") if captured else None,
            "excerpt_comparison": "not_comparable"
            if not comparable or source is None
            else "excerpt_matches"
            if excerpt in text
            else "excerpt_changed",
            "source_status": "planning_record_missing"
            if captured is None
            else "not_linkable"
            if non_chunk
            else "missing"
            if source is None
            else "too_long"
            if len(text) > 8000
            else "available",
            "can_link": linkable,
            "current_evidence": {
                "chunk_id": source["id"],
                "sha256": digest(text),
                "name": source["original_name"],
                "ordinal": source["ordinal"],
                "text": text,
                "relation": "context",
            }
            if linkable
            else None,
        }

    def _validate_receipt(self, receipt: Any) -> None:
        if (
            not isinstance(receipt, dict)
            or set(receipt)
            != {"version", "provider_run_id", "original_revision_id", "original_sha256", "slides"}
            or isinstance(receipt["version"], bool)
            or not isinstance(receipt["version"], int)
            or receipt["version"] != 1
        ):
            raise invalid_request("The outline evidence receipt is invalid.")
        for key in ("provider_run_id", "original_revision_id"):
            self._semantics._uuid_field(receipt[key], key)
        if not isinstance(receipt["original_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", receipt["original_sha256"]
        ):
            raise invalid_request("The outline evidence receipt SHA is invalid.")
        if not isinstance(receipt["slides"], list) or not 1 <= len(receipt["slides"]) <= 40:
            raise invalid_request("The outline evidence receipt slides are invalid.")
        for index, slide in enumerate(receipt["slides"], 1):
            if (
                not isinstance(slide, dict)
                or set(slide) != {"slide_number", "points", "evidence_ids"}
                or isinstance(slide["slide_number"], bool)
                or not isinstance(slide["slide_number"], int)
                or slide["slide_number"] != index
            ):
                raise invalid_request("The outline evidence receipt slide identity is invalid.")
            for key, maximum in (("points", 200), ("evidence_ids", 120)):
                values = slide[key]
                if not isinstance(values, list) or len(values) > 8:
                    raise invalid_request("The outline evidence receipt exceeds its bounds.")
                for value in values:
                    if PresentationCreationService._text(value, key, maximum) != value:
                        raise invalid_request("The outline evidence receipt text is invalid.")
            if len(set(slide["evidence_ids"])) != len(slide["evidence_ids"]):
                raise invalid_request("The outline evidence receipt repeats references.")
