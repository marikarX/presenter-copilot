"""Deck-wide find and run-preserving replace in native slide text and speaker notes.

Replacement happens inside each text run, so every run keeps its own formatting.
A match that crosses a run boundary, or sits in a field (slide number, date), is
reported as skipped and never rewritten.
"""

from __future__ import annotations

import copy
import posixpath
import re
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    DRAWING_NS,
    NOTES_SLIDE_REL_TYPE,
    PRESENTATION_NS,
    FidelityDocument,
    _parse_xml_part,
    _relationships,
    _resolve_internal_part,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

_NS = {"p": PRESENTATION_NS, "a": DRAWING_NS}
MAX_QUERY_CHARS = 200
MAX_REPLACEMENT_CHARS = 2000
MAX_RESULT_OBJECTS = 200
MAX_REPLACEMENTS = 2000
SLIDE_TARGET = "slide"
NOTES_TARGET = "speaker_notes"
_MATCH_KEYS = ("target", "slide_id", "object_id", "replaceable_count")


def _pattern(query: str, match_case: bool) -> re.Pattern[str]:
    return re.compile(re.escape(query), 0 if match_case else re.IGNORECASE)


def _query(editor: PresentationEditService, params: dict[str, Any]) -> tuple[str, bool]:
    query = editor._text_field(params.get("query"), "query")
    if not 1 <= len(query) <= MAX_QUERY_CHARS or not query.strip():
        raise invalid_request(
            f"query must contain visible text and at most {MAX_QUERY_CHARS} characters.",
            field="query",
        )
    match_case = params.get("match_case", False)
    if type(match_case) is not bool:
        raise invalid_request("match_case must be a boolean.", field="match_case")
    return query, match_case


def _scan_object(node: etree._Element, pattern: re.Pattern[str]) -> tuple[int, int]:
    """(replaceable, skipped) matches in one shape's own text body."""
    replaceable = total = 0
    for paragraph in node.xpath("./p:txBody/a:p", namespaces=_NS):
        total += len(
            pattern.findall(
                "".join(item.text or "" for item in paragraph.xpath(".//a:t", namespaces=_NS))
            )
        )
        replaceable += sum(
            len(pattern.findall(item.text or ""))
            for item in paragraph.xpath("./a:r/a:t", namespaces=_NS)
        )
    return replaceable, max(total - replaceable, 0)


def _notes_body(
    archive: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], slide_part: str
) -> tuple[str, etree._Element, etree._Element] | None:
    """(notes part, notes root, body placeholder) for a slide, when unambiguous."""
    directory, name = posixpath.split(slide_part)
    rels_info = members.get(f"{directory}/_rels/{name}.rels")
    if rels_info is None:
        return None
    notes = [
        (target, mode)
        for kind, target, mode in _relationships(_parse_xml_part(archive, rels_info)).values()
        if kind == NOTES_SLIDE_REL_TYPE
    ]
    if len(notes) != 1 or notes[0][1].casefold() != "internal":
        return None
    part = _resolve_internal_part(directory, notes[0][0])
    if part not in members:
        return None
    root = _parse_xml_part(archive, members[part])
    bodies = root.xpath(
        "./p:cSld/p:spTree/p:sp[p:nvSpPr/p:nvPr/p:ph[@type='body']]", namespaces=_NS
    )
    return (part, root, bodies[0]) if len(bodies) == 1 else None


def _excerpt(text: str, pattern: re.Pattern[str]) -> str:
    index = pattern.search(text)
    start = max((index.start() if index else 0) - 40, 0)
    return text[start : start + 120]


def _scan(
    editor: PresentationEditService,
    archive: zipfile.ZipFile,
    fidelity: FidelityDocument,
    pattern: re.Pattern[str],
) -> list[dict[str, Any]]:
    members = {info.filename: info for info in archive.infolist()}
    results: list[dict[str, Any]] = []
    for slide in fidelity.slides:
        root: etree._Element | None = None
        for obj in slide.objects:
            if obj.kind != "sp" or not pattern.search(obj.text):
                continue
            if root is None:
                root = _parse_xml_part(archive, members[slide.part_name])
            try:
                node = editor._find_shape(root, obj.ooxml_id)
            except CoreDomainError:
                # Ambiguous copies (alternate content) are listed, never rewritten.
                replaceable, skipped = 0, len(pattern.findall(obj.text))
            else:
                replaceable, skipped = _scan_object(node, pattern)
            if replaceable or skipped:
                results.append(
                    {
                        "target": SLIDE_TARGET,
                        "slide_id": slide.slide_id,
                        "slide_number": slide.ordinal,
                        "object_id": obj.object_id,
                        "name": obj.name,
                        "excerpt": _excerpt(obj.text, pattern),
                        "replaceable_count": replaceable,
                        "skipped_count": skipped,
                    }
                )
        if slide.speaker_notes and pattern.search(slide.speaker_notes):
            notes = _notes_body(archive, members, slide.part_name)
            replaceable, skipped = (
                _scan_object(notes[2], pattern)
                if notes
                else (0, len(pattern.findall(slide.speaker_notes)))
            )
            if replaceable or skipped:
                results.append(
                    {
                        "target": NOTES_TARGET,
                        "slide_id": slide.slide_id,
                        "slide_number": slide.ordinal,
                        "object_id": None,
                        "name": "Speaker notes",
                        "excerpt": _excerpt(slide.speaker_notes, pattern),
                        "replaceable_count": replaceable,
                        "skipped_count": skipped,
                    }
                )
    return results


def _source(editor: PresentationEditService, params: dict[str, Any]) -> tuple[Any, ...]:
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    path = editor._storage.paths.snapshot_path(
        project, source["local_snapshot_path"], require_exists=True
    )
    with path.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=document,
            expected_sha256=source["sha256"],
            byte_size=source["byte_size"],
        )
    return project, document, revision, source, path, fidelity


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "replaceable_matches": sum(item["replaceable_count"] for item in results),
        "skipped_matches": sum(item["skipped_count"] for item in results),
        "objects": results[:MAX_RESULT_OBJECTS],
        "objects_truncated": len(results) > MAX_RESULT_OBJECTS,
    }


def find_text(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params, {"project_id", "document_id", "expected_revision_id", "query", "match_case"}
    )
    query, match_case = _query(editor, params)
    _project, _document, revision, source, path, fidelity = _source(editor, params)
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        results = _scan(editor, archive, fidelity, _pattern(query, match_case))
    return {"revision_id": revision, "query": query, "match_case": match_case, **_summary(results)}


def _runs(node: etree._Element) -> list[etree._Element]:
    return list(node.xpath("./p:txBody/a:p/a:r/a:t", namespaces=_NS))


def replace_text_all(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "query",
            "match_case",
            "replacement",
            "expected_matches",
        },
    )
    query, match_case = _query(editor, params)
    replacement = editor._text_field(params.get("replacement"), "replacement")
    if len(replacement) > MAX_REPLACEMENT_CHARS:
        raise invalid_request("replacement is too long.", field="replacement")
    expected = params.get("expected_matches")
    if (
        not isinstance(expected, list)
        or not 1 <= len(expected) <= MAX_RESULT_OBJECTS
        or any(
            not isinstance(item, dict)
            or set(item) != set(_MATCH_KEYS)
            or type(item["replaceable_count"]) is not int
            for item in expected
        )
    ):
        raise invalid_request(
            "expected_matches must list the reviewed target, slide_id, object_id and "
            "replaceable_count of each match.",
            field="expected_matches",
        )
    project, document, revision, source, path, fidelity = _source(editor, params)
    pattern = _pattern(query, match_case)
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        current = [
            item for item in _scan(editor, archive, fidelity, pattern) if item["replaceable_count"]
        ]
    if [{key: item[key] for key in _MATCH_KEYS} for item in current] != expected:
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The matches changed. Search again and review the new results.",
            retryable=True,
        )
    total = sum(item["replaceable_count"] for item in current)
    if total > MAX_REPLACEMENTS:
        raise CoreDomainError(
            "PRESENTATION_EDIT_RESOURCE_LIMIT",
            f"Replace at most {MAX_REPLACEMENTS} matches at once.",
        )
    objects = {item["object_id"] for item in current if item["target"] == SLIDE_TARGET}
    notes_slides = {item["slide_id"] for item in current if item["target"] == NOTES_TARGET}
    slide_parts = {
        slide.part_name
        for slide in fidelity.slides
        if any(obj.object_id in objects for obj in slide.objects)
    }
    # Expected run texts by (part, object or "notes") for post-write verification.
    expected_runs: dict[tuple[str, str], list[str]] = {}

    def substitute(node: etree._Element) -> list[str]:
        texts = []
        for item in _runs(node):
            item.text = pattern.sub(lambda _match: replacement, item.text or "")
            texts.append(item.text)
        return texts

    def write(original: Path, target: Path) -> bool:
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            members = {info.filename: info for info in archive.infolist()}
            rewritten: dict[str, bytes] = {}
            for slide in fidelity.slides:
                if slide.part_name in slide_parts:
                    root = _parse_xml_part(archive, members[slide.part_name])
                    for obj in slide.objects:
                        if obj.object_id in objects:
                            expected_runs[(slide.part_name, obj.ooxml_id)] = substitute(
                                editor._find_shape(root, obj.ooxml_id)
                            )
                    rewritten[slide.part_name] = etree.tostring(
                        root, encoding="UTF-8", xml_declaration=True, standalone=True
                    )
                if slide.slide_id in notes_slides:
                    notes = _notes_body(archive, members, slide.part_name)
                    if notes is None:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_STALE_TARGET",
                            "The speaker notes changed. Search again.",
                            retryable=True,
                        )
                    part, root, body = notes
                    expected_runs[(part, "notes")] = substitute(body)
                    rewritten[part] = etree.tostring(
                        root, encoding="UTF-8", xml_declaration=True, standalone=True
                    )
            with zipfile.ZipFile(target, "w", allowZip64=True) as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    if info.filename in rewritten:
                        output.writestr(copy.copy(info), rewritten[info.filename])
                    else:
                        with (
                            archive.open(info) as reader,
                            output.open(copy.copy(info), "w") as writer,
                        ):
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
        with target.open("rb") as handle:
            updated = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(target),
                byte_size=target.stat().st_size,
            )
        before = {obj.object_id: obj for slide in fidelity.slides for obj in slide.objects}
        after = {obj.object_id: obj for slide in updated.slides for obj in slide.objects}
        notes_before = {slide.slide_id: slide.speaker_notes for slide in fidelity.slides}
        notes_after = {slide.slide_id: slide.speaker_notes for slide in updated.slides}
        if (
            set(before) != set(after)
            or any(before[key] != after[key] for key in before if key not in objects)
            or set(notes_before) != set(notes_after)
            or any(
                notes_before[key] != notes_after[key]
                for key in notes_before
                if key not in notes_slides
            )
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Text outside the reviewed matches changed.",
            )
        with zipfile.ZipFile(target) as archive:
            members = {info.filename: info for info in archive.infolist()}
            for slide in updated.slides:
                if slide.part_name in slide_parts:
                    root = _parse_xml_part(archive, members[slide.part_name])
                    for obj in slide.objects:
                        key = (slide.part_name, obj.ooxml_id)
                        if (
                            obj.object_id in objects
                            and [
                                item.text or ""
                                for item in _runs(editor._find_shape(root, obj.ooxml_id))
                            ]
                            != expected_runs[key]
                        ):
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_VALIDATION_FAILED",
                                "The replaced text did not pass validation.",
                            )
                if slide.slide_id in notes_slides:
                    notes = _notes_body(archive, members, slide.part_name)
                    if (
                        notes is None
                        or [item.text or "" for item in _runs(notes[2])]
                        != (expected_runs[(notes[0], "notes")])
                    ):
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_VALIDATION_FAILED",
                            "The replaced speaker notes did not pass validation.",
                        )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "replaced_matches": total, "objects_changed": len(current)}
