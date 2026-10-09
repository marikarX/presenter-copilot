"""Local deck-wide text scan preflight; no inference or claim persistence."""

from typing import Any

from presenter_core.errors import invalid_request, reject_unknown_fields
from presenter_core.presentation.claim_extraction import claim_context_size, claim_request
from presenter_core.presentation.claims import digest
from presenter_core.presentation.semantics import PresentationSemanticService
from presenter_core.providers.context import MAX_TOTAL_CONTEXT_CHARS


class PresentationClaimScanService:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics

    def prepare_claim_scan(self, params: dict[str, Any]) -> dict[str, Any]:
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

        def fits(texts: dict[str, str], kinds: dict[str, str]) -> bool:
            # Reserve for policy-mode length changes between local preflight and execution.
            return (
                len(texts) <= 8
                and sum(map(len, texts.values())) <= 6000
                and claim_context_size(
                    claim_request(texts, "selected_context_cloud", document, revision, kinds)
                )
                <= MAX_TOTAL_CONTEXT_CHARS - 100
            )

        items: list[dict[str, Any]] = []
        for slide in fidelity.slides[offset : offset + limit]:
            native: dict[str, Any] = fidelity.text_targets(slide.ordinal)
            batches: list[dict[str, Any]] = []
            spans: list[dict[str, Any]] = []
            texts: dict[str, str] = {}
            kinds = {t["object_id"]: t["source_kind"] for t in native["semantic_targets"]}
            excluded = native["semantic_excluded_objects"]
            eligible = 0

            def flush(
                batch_rows: list[dict[str, Any]],
                batch_spans: list[dict[str, Any]],
                batch_texts: dict[str, str],
                source_kinds: dict[str, str],
            ) -> None:
                if batch_spans:
                    batch_rows.append(
                        {
                            "object_ids": list(batch_texts),
                            "spans": batch_spans.copy(),
                            "characters": sum(map(len, batch_texts.values())),
                            "source_kinds": {key: source_kinds[key] for key in batch_texts},
                        }
                    )
                    batch_spans.clear()
                    batch_texts.clear()

            for target in native["semantic_targets"]:
                text = target.get("decision_text")
                if not isinstance(text, str) or not text.strip():
                    excluded += 1
                    continue
                eligible += 1
                object_id = target["object_id"]
                start = 0
                while start < len(text):
                    low, high = start + 1, min(len(text), start + 6000)
                    end = start
                    while low <= high:
                        middle = (low + high) // 2
                        if fits({object_id: text[start:middle]}, kinds):
                            end, low = middle, middle + 1
                        else:
                            high = middle - 1
                    if end <= start:
                        raise invalid_request(
                            "The native text cannot fit the claim context budget."
                        )
                    window = text[start:end]
                    if window.strip():
                        if object_id in texts or not fits({**texts, object_id: window}, kinds):
                            flush(batches, spans, texts, kinds)
                        texts[object_id] = window
                        spans.append(
                            {
                                "object_id": object_id,
                                "start": start,
                                "end": end,
                                "sha256": digest(text),
                            }
                        )
                    if end == len(text):
                        break
                    # Preserve candidate spans up to the existing 2000-character quote limit.
                    start = max(start + 1, end - 2000)
            flush(batches, spans, texts, kinds)
            items.append(
                {
                    "slide_id": slide.slide_id,
                    "slide_number": slide.ordinal,
                    "title": next(
                        (
                            t["decision_text"][:100]
                            for t in native["targets"]
                            if isinstance(t.get("decision_text"), str)
                            and t["decision_text"].strip()
                        ),
                        f"Slide {slide.ordinal}",
                    ),
                    "batches": batches,
                    "eligible_objects": eligible,
                    "excluded_objects": excluded,
                    "inventory_truncated": bool(native["semantic_has_more"]),
                }
            )
        with self._semantics._storage.project_database(project) as connection:
            self._semantics._require_current_presentation(connection, project, document, revision)
        return {
            "document_id": document,
            "revision_id": revision,
            "total_slides": len(fidelity.slides),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(items) < len(fidelity.slides),
            "items": items,
            "provider_calls": sum(len(item["batches"]) for item in items),
            "coverage_scope": "available_native_representations_only",
        }
