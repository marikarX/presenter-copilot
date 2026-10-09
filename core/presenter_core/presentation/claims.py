"""User-reviewed claim spans and evidence snapshots, with explicit revision freshness."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from presenter_core.errors import invalid_request, reject_unknown_fields
from presenter_core.presentation.semantics import PresentationSemanticService


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PresentationClaimService:
    def __init__(self, semantics: PresentationSemanticService) -> None:
        self._semantics = semantics

    def _selection(
        self, params: dict[str, Any], *, historical: bool = False
    ) -> tuple[str, str, str, dict[str, Any]]:
        service = self._semantics
        project = service._project_id(params.get("project_id"))
        document = service._uuid_field(params.get("document_id"), "document_id")
        revision = service._uuid_field(params.get("revision_id"), "revision_id")
        read = (
            service._workspace_sources.revision_text_targets
            if historical
            else service._workspace_sources.list_text_targets
        )
        selection = read(
            {
                "project_id": project,
                "document_id": document,
                "revision_id": revision,
                "slide_number": service._slide_number(params.get("slide_number")),
            }
        )
        if selection["slide_id"] != params.get("slide_id"):
            raise invalid_request("The claim slide changed. Refresh and try again.")
        return project, document, revision, selection

    @staticmethod
    def _rows(
        connection: sqlite3.Connection, document: str, revision: str, slide: str
    ) -> list[Any]:
        return connection.execute(
            """
            WITH RECURSIVE lineage(id, depth) AS (
                SELECT ?, 0 UNION ALL
                SELECT r.parent_revision_id, l.depth + 1 FROM presentation_revisions r
                JOIN lineage l ON r.id = l.id WHERE r.presentation_id = ?
                AND r.parent_revision_id IS NOT NULL AND l.depth < 100
            )
            SELECT c.*, l.depth FROM lineage l JOIN presentation_claims c ON c.revision_id = l.id
            WHERE c.presentation_id = ? AND c.slide_id = ? ORDER BY l.depth, c.claim_id
        """,
            (revision, document, document, slide),
        ).fetchall()

    @staticmethod
    def _evidence(connection: Any, project: str, chunk_id: str) -> Any:
        return connection.execute(
            """
            SELECT c.id, c.text, d.id AS document_id, d.original_name, u.ordinal,
                   d.kind AS document_kind, u.id AS source_unit_id
            FROM chunks c JOIN source_units u ON u.id = c.source_unit_id
            JOIN documents d ON d.id = u.document_id
            WHERE c.id = ? AND d.project_id = ? AND d.parse_status = 'ready'
              AND d.kind != 'presentation'
        """,
            (chunk_id, project),
        ).fetchone()

    def list_claims(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._list_claims(params, historical=False)

    def revision_claims(self, params: dict[str, Any]) -> dict[str, Any]:
        """Internal context read; historical records never authorize editing an old revision."""
        return self._list_claims(params, historical=True)

    def _list_claims(
        self,
        params: dict[str, Any],
        *,
        historical: bool,
        selected: tuple[str, str, str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        reject_unknown_fields(
            params, {"project_id", "document_id", "revision_id", "slide_id", "slide_number"}
        )
        project, document, revision, selection = selected or self._selection(
            params, historical=historical
        )
        targets = {t["object_id"]: t for t in selection["semantic_targets"]}
        items, seen = [], set()
        with self._semantics._storage.project_database(project) as connection:
            if not historical:
                self._semantics._require_current_presentation(
                    connection, project, document, revision
                )
            lineage_truncated = (
                connection.execute(
                    """
                WITH RECURSIVE lineage(id, depth) AS (
                    SELECT ?, 0 UNION ALL
                    SELECT r.parent_revision_id, l.depth + 1 FROM presentation_revisions r
                    JOIN lineage l ON r.id = l.id WHERE r.presentation_id = ?
                    AND r.parent_revision_id IS NOT NULL AND l.depth < 100
                )
                SELECT r.parent_revision_id FROM lineage l
                JOIN presentation_revisions r ON r.id = l.id
                WHERE l.depth = 100 AND r.parent_revision_id IS NOT NULL
            """,
                    (revision, document),
                ).fetchone()
                is not None
            )
            for row in self._rows(connection, document, revision, selection["slide_id"]):
                if row["claim_id"] in seen:
                    continue
                seen.add(row["claim_id"])
                if row["deleted"]:
                    continue
                item = json.loads(row["record_json"])
                item.setdefault("source_kind", "native_text")
                target = targets.get(item["object_id"])
                text = target.get("decision_text") if target else None
                span_status = (
                    "missing"
                    if text is None
                    else "unchanged"
                    if digest(text) == item["object_sha256"]
                    and target is not None
                    and target["source_kind"] == item["source_kind"]
                    else "changed"
                )
                evidence = []
                for saved in item["evidence"]:
                    current = self._evidence(connection, project, saved["chunk_id"])
                    status = (
                        "missing"
                        if current is None
                        else (
                            "current" if digest(current["text"]) == saved["sha256"] else "changed"
                        )
                    )
                    evidence.append({**saved, "status": status})
                fresh = row["revision_id"] == revision and span_status == "unchanged"
                support = any(
                    e["relation"] == "supports" and e["status"] == "current" for e in evidence
                )
                conflict = any(
                    e["relation"] == "contradicts" and e["status"] == "current" for e in evidence
                )
                coverage = (
                    "needs_review"
                    if not fresh or any(e["status"] != "current" for e in evidence)
                    else "conflicting"
                    if conflict
                    else "supported"
                    if support
                    else "unlinked"
                )
                items.append(
                    {
                        **item,
                        "source_revision_id": row["revision_id"],
                        "span_status": span_status,
                        "coverage": coverage,
                        "evidence": evidence,
                    }
                )
        return {
            "revision_id": revision,
            "slide_id": selection["slide_id"],
            "items": items,
            "lineage_limit": 100,
            "lineage_truncated": lineage_truncated,
            "inventory_truncated": selection["semantic_has_more"],
        }

    def revision_slide_numbers(self, project: str, revision: str) -> list[int]:
        with self._semantics._storage.project_database(project) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT u.ordinal FROM source_units u
                JOIN documents d ON d.id = u.document_id
                WHERE d.project_id = ? AND u.presentation_revision_id = ? AND u.unit_type = 'slide'
                    AND u.ordinal IS NOT NULL ORDER BY u.ordinal LIMIT 6
            """,
                (project, revision),
            ).fetchall()
        return [int(row[0]) for row in rows]

    def provider_context(
        self, project: str, revision: str, numbers: list[int]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with self._semantics._storage.project_database(project) as connection:
            row = connection.execute(
                """
                SELECT r.presentation_id FROM presentation_revisions r
                JOIN documents d ON d.id = r.presentation_id
                WHERE r.id = ? AND d.project_id = ?
            """,
                (revision, project),
            ).fetchone()
        if row is None:
            raise invalid_request("The claim context revision is unavailable in this project.")
        document = row["presentation_id"]
        with self._semantics._storage.project_database(project) as connection:
            exists = connection.execute(
                "SELECT 1 FROM presentation_claims WHERE presentation_id = ? LIMIT 1", (document,)
            ).fetchone()
        if exists is None:
            return {"revision_id": revision, "claims": [], "incomplete": False}, []

        candidates, documents = [], []
        truncated = len(numbers) > 5
        for number in numbers[:5]:
            selection = self._semantics._workspace_sources.revision_text_targets(
                {
                    "project_id": project,
                    "document_id": document,
                    "revision_id": revision,
                    "slide_number": number,
                }
            )
            result = self._list_claims(
                {
                    "project_id": project,
                    "document_id": document,
                    "revision_id": revision,
                    "slide_number": number,
                    "slide_id": selection["slide_id"],
                },
                historical=True,
                selected=(project, document, revision, selection),
            )
            truncated |= result["lineage_truncated"] or result["inventory_truncated"]
            for claim in result["items"]:
                links, excerpts = [], []
                fresh = (
                    claim["source_revision_id"] == revision and claim["span_status"] == "unchanged"
                )
                for link in claim["evidence"]:
                    supplied = fresh and link["status"] == "current"
                    links.append(
                        {
                            "relation": link["relation"],
                            "status": link["status"],
                            "grounding_included": False,
                            **({"evidence_id": link["chunk_id"]} if supplied else {}),
                        }
                    )
                    if supplied:
                        with self._semantics._storage.project_database(project) as connection:
                            source = self._evidence(connection, project, link["chunk_id"])
                        if source is None or digest(source["text"]) != link["sha256"]:
                            links[-1].pop("evidence_id", None)
                            links[-1]["status"] = "changed"
                            continue
                        excerpts.append(
                            {
                                "evidence_id": link["chunk_id"],
                                "text": source["text"][:800],
                                "source_id": source["document_id"],
                                "source_type": "transcript"
                                if source["document_kind"] == "transcript"
                                else "document",
                                "source_unit_id": source["source_unit_id"],
                                "label": source["original_name"],
                                "sha256": link["sha256"],
                            }
                        )
                candidates.append(
                    (
                        {
                            "claim_id": claim["claim_id"],
                            "slide_id": selection["slide_id"],
                            "slide_number": number,
                            "object_id": claim["object_id"],
                            "source_kind": claim["source_kind"],
                            "quote_excerpt": claim["quote"][:500]
                            if claim["span_status"] == "unchanged"
                            else None,
                            "quote_truncated": len(claim["quote"]) > 500,
                            "span": {"start": claim["start"], "end": claim["end"]},
                            "coverage": "needs_review"
                            if any(link["status"] != "current" for link in links)
                            else claim["coverage"],
                            "span_status": claim["span_status"],
                            "reviewed_for_revision": fresh,
                            "links": links,
                        },
                        excerpts,
                    )
                )
        candidates.sort(
            key=lambda pair: {"conflicting": 0, "needs_review": 1, "unlinked": 2, "supported": 3}[
                pair[0]["coverage"]
            ]
        )
        claims: list[dict[str, Any]] = []
        for item, excerpts in candidates:
            if len(claims) >= 8 or len(json.dumps([*claims, item], ensure_ascii=False)) > 6000:
                truncated = True
                continue
            claims.append(item)
            documents.extend(excerpts)
        return {
            "revision_id": revision,
            "claims": claims,
            "incomplete": truncated,
            "coverage_definition": "user_relation_judgment",
        }, documents

    def search_evidence(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"project_id", "query"})
        project = self._semantics._project_id(params.get("project_id"))
        query = params.get("query")
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 120:
            raise invalid_request("Search evidence with 2-120 characters.")
        # Literal substring matching; SQL wildcard characters have no special meaning.
        with self._semantics._storage.project_database(project) as connection:
            rows = connection.execute(
                """
                SELECT c.id AS chunk_id, c.text, d.original_name, u.ordinal
                FROM chunks c JOIN source_units u ON u.id = c.source_unit_id
                JOIN documents d ON d.id = u.document_id
                WHERE d.project_id = ? AND d.parse_status = 'ready' AND d.kind != 'presentation'
                  AND length(c.text) <= 8000 AND instr(lower(c.text), lower(?)) > 0
                ORDER BY d.imported_at DESC, u.ordinal, c.chunk_index LIMIT 21
            """,
                (project, query.strip()),
            ).fetchall()
        return {
            "items": [
                {
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "name": row["original_name"],
                    "ordinal": row["ordinal"],
                    "sha256": digest(row["text"]),
                }
                for row in rows[:20]
            ],
            "has_more": len(rows) > 20,
        }

    def save_claim(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "revision_id",
                "slide_id",
                "slide_number",
                "object_id",
                "quote",
                "evidence",
                "claim_id",
                "confirm",
            },
        )
        if params.get("confirm") is not True:
            raise invalid_request("Confirm reviewing this claim and its evidence links.")
        project, document, revision, selection = self._selection(params)
        object_id, quote = params.get("object_id"), params.get("quote")
        target = next(
            (t for t in selection["semantic_targets"] if t["object_id"] == object_id), None
        )
        text = target.get("decision_text") if target else None
        if (
            not isinstance(quote, str)
            or not 1 <= len(quote) <= 2000
            or not quote.strip()
            or not isinstance(text, str)
            or text.find(quote) < 0
            or text.find(quote, text.find(quote) + 1) >= 0
        ):
            raise invalid_request(
                "Choose a unique exact quote from a current native representation."
            )
        links = params.get("evidence", [])
        if not isinstance(links, list) or len(links) > 4:
            raise invalid_request("Link up to four evidence excerpts.")
        claim_id = (
            self._semantics._uuid_field(params["claim_id"], "claim_id")
            if params.get("claim_id")
            else str(uuid.uuid4())
        )
        with self._semantics._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._semantics._require_current_presentation(connection, project, document, revision)
            active: dict[str, bool] = {}
            for row in self._rows(connection, document, revision, selection["slide_id"]):
                active.setdefault(row["claim_id"], not row["deleted"])
            if params.get("claim_id") and claim_id not in active:
                raise invalid_request("Choose a claim from this slide's revision history.")
            if not active.get(claim_id, False) and sum(active.values()) >= 20:
                raise invalid_request("Each slide allows up to 20 reviewed claims.")
            evidence, seen = [], set()
            for link in links:
                if not isinstance(link, dict):
                    raise invalid_request("Choose a valid evidence link.")
                reject_unknown_fields(link, {"chunk_id", "sha256", "relation"})
                chunk = link.get("chunk_id")
                if not isinstance(chunk, str) or chunk in seen:
                    raise invalid_request("Evidence links must be unique.")
                seen.add(chunk)
                row = self._evidence(connection, project, chunk)
                relation = link.get("relation")
                if (
                    row is None
                    or len(row["text"]) > 8000
                    or digest(row["text"]) != link.get("sha256")
                    or relation not in {"supports", "contradicts", "context"}
                ):
                    raise invalid_request(
                        "The chosen evidence changed or is unavailable. Search again."
                    )
                evidence.append(
                    {
                        "chunk_id": chunk,
                        "sha256": digest(row["text"]),
                        "text": row["text"],
                        "name": row["original_name"],
                        "ordinal": row["ordinal"],
                        "relation": relation,
                    }
                )
            start = text.index(quote)
            record = {
                "claim_id": claim_id,
                "object_id": object_id,
                "source_kind": target["source_kind"] if target is not None else "native_text",
                "quote": quote,
                "start": start,
                "end": start + len(quote),
                "object_sha256": digest(text),
                "provenance": "user_confirmed",
                "evidence": evidence,
            }
            connection.execute(
                """
                INSERT INTO presentation_claims VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(revision_id, claim_id) DO UPDATE SET
                    record_json=excluded.record_json, deleted=0
            """,
                (revision, document, selection["slide_id"], claim_id, json.dumps(record)),
            )
            connection.commit()
        return {"revision_id": revision, "claim_id": claim_id}

    def remove_claim(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "revision_id",
                "slide_id",
                "slide_number",
                "claim_id",
                "confirm",
            },
        )
        if params.get("confirm") is not True:
            raise invalid_request("Confirm removing the reviewed claim.")
        project, document, revision, selection = self._selection(params)
        claim_id = self._semantics._uuid_field(params.get("claim_id"), "claim_id")
        with self._semantics._storage.project_database(project) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._semantics._require_current_presentation(connection, project, document, revision)
            row = next(
                (
                    r
                    for r in self._rows(connection, document, revision, selection["slide_id"])
                    if r["claim_id"] == claim_id
                ),
                None,
            )
            if row is None or row["deleted"]:
                raise invalid_request("The claim is unavailable.")
            connection.execute(
                """
                INSERT INTO presentation_claims VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(revision_id, claim_id) DO UPDATE SET deleted=1
            """,
                (revision, document, selection["slide_id"], claim_id, row["record_json"]),
            )
            connection.commit()
        return {"revision_id": revision, "claim_id": claim_id, "removed": True}
