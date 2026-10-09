"""Paged, read-only deck semantics derived from a verified native revision."""

from __future__ import annotations

from typing import Any

from presenter_core.errors import invalid_request, reject_unknown_fields
from presenter_core.presentation.claims import PresentationClaimService
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.presentation.takeaways import PresentationTakeawayService

COVERAGE = ("supported", "conflicting", "needs_review", "unlinked")


class PresentationDeckReviewService:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics
        self._claims = PresentationClaimService(semantics)

    def review_deck_semantics(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "document_id", "revision_id", "offset", "limit"}
        )
        offset, limit = params.get("offset", 0), params.get("limit", 20)
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 5000:
            raise invalid_request("offset must be an integer from 0 to 5000.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 25:
            raise invalid_request("limit must be an integer from 1 to 25.")
        scope = {key: params.get(key) for key in ("project_id", "document_id", "revision_id")}
        project, document, revision, fidelity = (
            self._semantics._workspace_sources.read_revision_inventory(scope)
        )
        selected_slides = fidelity.slides[offset : offset + limit]
        purposes = {}
        with self._semantics._storage.project_database(project) as connection:
            self._semantics._require_current_presentation(connection, project, document, revision)
            # Ranked ancestry is filtered to this page; no unbounded deck/parent scan.
            if selected_slides:
                placeholders = ",".join("?" for _ in selected_slides)
                rows = connection.execute(
                    """
                    WITH RECURSIVE lineage(id, depth) AS (
                        SELECT ?, 0 UNION ALL
                        SELECT r.parent_revision_id, l.depth + 1 FROM presentation_revisions r
                        JOIN lineage l ON r.id = l.id WHERE r.presentation_id = ?
                        AND r.parent_revision_id IS NOT NULL AND l.depth < 100
                    ), ranked AS (
                        SELECT p.slide_id, p.purpose, p.revision_id,
                               ROW_NUMBER() OVER (PARTITION BY p.slide_id ORDER BY l.depth) AS rank
                        FROM lineage l JOIN presentation_slide_purposes p ON p.revision_id = l.id
                        WHERE p.presentation_id = ? AND p.slide_id IN (
                    """
                    + placeholders
                    + ") ) SELECT * FROM ranked WHERE rank = 1",
                    (revision, document, document, *(slide.slide_id for slide in selected_slides)),
                ).fetchall()
                purposes = {row["slide_id"]: row for row in rows}
        items = []
        totals = dict.fromkeys(COVERAGE, 0)
        incomplete = False
        for slide in selected_slides:
            native: dict[str, Any] = fidelity.text_targets(slide.ordinal)
            claims = self._claims._list_claims(
                {**scope, "slide_id": slide.slide_id, "slide_number": slide.ordinal},
                historical=False,
                selected=(project, document, revision, {"revision_id": revision, **native}),
            )
            with self._semantics._storage.project_database(project) as connection:
                takeaway = PresentationTakeawayService._read(
                    connection, document, revision, slide.slide_id
                )
            purpose = purposes.get(slide.slide_id)
            purpose_status = (
                "missing"
                if purpose is None
                else "reviewed"
                if purpose["revision_id"] == revision
                else "needs_review"
            )
            counts = {key: sum(c["coverage"] == key for c in claims["items"]) for key in COVERAGE}
            for key, count in counts.items():
                totals[key] += count
            reasons = []
            if purpose_status == "missing":
                reasons.append("purpose_missing")
            elif purpose_status == "needs_review":
                reasons.append("purpose_inherited")
            elif purpose is not None and purpose["purpose"] == "unclear":
                reasons.append("purpose_unclear")
            if counts["needs_review"]:
                reasons.append("claim_needs_review")
            if counts["conflicting"]:
                reasons.append("conflicting_evidence")
            if counts["unlinked"]:
                reasons.append("claim_unlinked")
            if takeaway["status"] == "needs_review" and takeaway["takeaway"]:
                reasons.append("takeaway_inherited")
            truncated = (
                claims["inventory_truncated"]
                or claims["lineage_truncated"]
                or takeaway["lineage_truncated"]
            )
            if truncated:
                reasons.append("incomplete_coverage")
            incomplete = incomplete or truncated
            title = next(
                (
                    t["current_text"][:160]
                    for t in native["targets"]
                    if isinstance(t.get("current_text"), str) and t["current_text"].strip()
                ),
                f"Slide {slide.ordinal}",
            )
            items.append(
                {
                    "slide_id": slide.slide_id,
                    "slide_number": slide.ordinal,
                    "title": title,
                    "purpose": purpose["purpose"] if purpose else None,
                    "purpose_status": purpose_status,
                    "purpose_source_revision_id": purpose["revision_id"] if purpose else None,
                    "takeaway": takeaway["takeaway"],
                    "takeaway_status": takeaway["status"],
                    "takeaway_source_revision_id": takeaway["source_revision_id"],
                    "claim_count": len(claims["items"]),
                    "claim_counts": counts,
                    "attention_reasons": reasons,
                    "incomplete": bool(truncated),
                }
            )
        # A deck change during native inspection or per-slide review invalidates the page.
        with self._semantics._storage.project_database(project) as connection:
            self._semantics._require_current_presentation(connection, project, document, revision)
        return {
            "revision_id": revision,
            "total_slides": len(fidelity.slides),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(items) < len(fidelity.slides),
            "items": items,
            "page_claim_counts": totals,
            "page_slides_needing_attention": sum(bool(i["attention_reasons"]) for i in items),
            "incomplete": bool(incomplete),
            "coverage_scope": "user_reviewed_claims_on_displayed_page",
        }
