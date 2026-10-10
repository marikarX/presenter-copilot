"""Deck-wide theme fonts: the heading (major) and body (minor) Latin typefaces.

Text that uses the theme fonts (+mj-lt / +mn-lt) follows the change; text with
an explicit typeface keeps it. Every slide master's theme is updated together.
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
    _parse_xml_part,
    _relationships,
    _resolve_internal_part,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

A = f"{{{DRAWING_NS}}}"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
FONT_NAME = re.compile(r'[^\x00-\x1f\x7f<>"&+\s][^\x00-\x1f\x7f<>"&]{0,30}')


def _theme_parts(archive: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo]) -> list[str]:
    """Theme parts referenced by the presentation's slide masters."""
    rels = members.get("ppt/_rels/presentation.xml.rels")
    if rels is None:
        return []
    themes: list[str] = []
    for kind, target, mode in _relationships(_parse_xml_part(archive, rels)).values():
        if kind != f"{REL}/slideMaster" or mode != "Internal":
            continue
        master = _resolve_internal_part("ppt", target)
        directory, name = posixpath.split(master)
        master_rels = members.get(f"{directory}/_rels/{name}.rels")
        if master_rels is None:
            continue
        for theme_kind, theme_target, theme_mode in _relationships(
            _parse_xml_part(archive, master_rels)
        ).values():
            if theme_kind == f"{REL}/theme" and theme_mode == "Internal":
                part = _resolve_internal_part(directory, theme_target)
                if part in members and part not in themes:
                    themes.append(part)
    return themes


def _fonts(theme: etree._Element) -> tuple[etree._Element | None, etree._Element | None]:
    scheme = theme.find(f"{A}themeElements/{A}fontScheme")
    if scheme is None:
        return None, None
    return scheme.find(f"{A}majorFont/{A}latin"), scheme.find(f"{A}minorFont/{A}latin")


def _state(archive: zipfile.ZipFile) -> dict[str, Any]:
    members = {info.filename: info for info in archive.infolist()}
    parts = _theme_parts(archive, members)
    pairs = []
    for part in parts:
        major, minor = _fonts(_parse_xml_part(archive, members[part]))
        pairs.append(
            (
                major.get("typeface") if major is not None else None,
                minor.get("typeface") if minor is not None else None,
            )
        )
    uniform = len(set(pairs)) == 1
    return {
        "theme_count": len(parts),
        "heading_font": pairs[0][0] if pairs and uniform else None,
        "body_font": pairs[0][1] if pairs and uniform else None,
        "uniform": uniform,
        "editable": bool(parts) and all(major and minor for major, minor in pairs),
    }


def _load(editor: PresentationEditService, params: dict[str, Any]) -> tuple[Any, ...]:
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    path = editor._storage.paths.snapshot_path(
        project, source["local_snapshot_path"], require_exists=True
    )
    return project, document, revision, source, path


def get_theme_fonts(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(params, {"project_id", "document_id", "expected_revision_id"})
    _project, _document, revision, source, path = _load(editor, params)
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        return {"revision_id": revision, **_state(archive)}


def _font_field(value: Any, field: str) -> str:
    if not isinstance(value, str) or not FONT_NAME.fullmatch(value) or value != value.strip():
        raise invalid_request(f"{field} must be a font name of up to 31 characters.", field=field)
    return value


def set_theme_fonts(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "expected_heading_font",
            "expected_body_font",
            "heading_font",
            "body_font",
        },
    )
    heading = _font_field(params.get("heading_font"), "heading_font")
    body = _font_field(params.get("body_font"), "body_font")
    project, document, revision, source, path = _load(editor, params)
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        before = _state(archive)
    if not before["editable"]:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED", "This presentation's theme fonts cannot be edited."
        )
    if (before["heading_font"], before["body_font"]) != (
        params.get("expected_heading_font"),
        params.get("expected_body_font"),
    ):
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The theme fonts changed. Refresh and try again.",
            retryable=True,
        )
    if (heading, body) == (before["heading_font"], before["body_font"]):
        return {
            "changed": False,
            "revision_id": source["revision_id"],
            "revision_number": int(source["revision_number"]),
            "sha256": source["sha256"],
            "byte_size": int(source["byte_size"]),
        }
    with path.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=document,
            expected_sha256=source["sha256"],
            byte_size=source["byte_size"],
        )

    def write(original: Path, target: Path) -> bool:
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            members = {info.filename: info for info in archive.infolist()}
            rewritten: dict[str, bytes] = {}
            for part in _theme_parts(archive, members):
                root = _parse_xml_part(archive, members[part])
                major, minor = _fonts(root)
                if major is None or minor is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED", "A theme has no font scheme."
                    )
                for element, value in ((major, heading), (minor, body)):
                    for attribute in list(element.attrib):
                        del element.attrib[attribute]
                    element.set("typeface", value)
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
        with zipfile.ZipFile(target) as archive:
            after = _state(archive)
        if (after["heading_font"], after["body_font"]) != (heading, body) or (
            [s.slide_id for s in updated.slides] != [s.slide_id for s in fidelity.slides]
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The theme font edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "heading_font": heading, "body_font": body}
