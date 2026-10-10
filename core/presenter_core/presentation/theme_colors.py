"""Deck-wide theme colors (accents, secondary dark/light, hyperlink colors).

Shapes and text that use scheme colors follow the change; direct RGB colors stay.
Every slide master's theme is updated together.
"""

from __future__ import annotations

import copy
import re
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import _parse_xml_part, inspect_pptx_snapshot
from presenter_core.presentation.theme_fonts import A, _load, _theme_parts

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

THEME_COLOR_SLOTS = (
    "dk2",
    "lt2",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
    "hlink",
    "folHlink",
)


def _slot_color(scheme: etree._Element, slot: str) -> str | None:
    node = scheme.find(f"{A}{slot}")
    if node is None or len(node) != 1:
        return None
    color = node[0]
    value = color.get("val") if color.tag == f"{A}srgbClr" else color.get("lastClr")
    if value is None or not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        return None
    return f"#{value.upper()}"


def _schemes(archive: zipfile.ZipFile) -> list[tuple[str, etree._Element, etree._Element]]:
    members = {info.filename: info for info in archive.infolist()}
    result = []
    for part in _theme_parts(archive, members):
        root = _parse_xml_part(archive, members[part])
        scheme = root.find(f"{A}themeElements/{A}clrScheme")
        if scheme is not None:
            result.append((part, root, scheme))
    return result


def _state(archive: zipfile.ZipFile) -> dict[str, Any]:
    schemes = _schemes(archive)
    palettes = [
        {slot: _slot_color(scheme, slot) for slot in THEME_COLOR_SLOTS}
        for _part, _root, scheme in schemes
    ]
    uniform = bool(palettes) and all(palette == palettes[0] for palette in palettes)
    return {
        "theme_count": len(palettes),
        "colors": palettes[0] if uniform else None,
        "editable": uniform and all(value is not None for value in palettes[0].values()),
    }


def get_theme_colors(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(params, {"project_id", "document_id", "expected_revision_id"})
    _project, _document, revision, source, path = _load(editor, params)
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        return {"revision_id": revision, **_state(archive)}


def set_theme_colors(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {"project_id", "document_id", "expected_revision_id", "expected_colors", "colors"},
    )
    colors = params.get("colors")
    if (
        not isinstance(colors, dict)
        or not colors
        or not set(colors) <= set(THEME_COLOR_SLOTS)
        or any(
            not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value)
            for value in colors.values()
        )
    ):
        raise invalid_request(
            "colors must map theme slots (" + ", ".join(THEME_COLOR_SLOTS) + ") to #RRGGBB.",
            field="colors",
        )
    colors = {slot: value.upper() for slot, value in colors.items()}
    project, document, revision, source, path = _load(editor, params)
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        before = _state(archive)
    if not before["editable"]:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED", "This presentation's theme colors cannot be edited."
        )
    if params.get("expected_colors") != before["colors"]:
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The theme colors changed. Refresh and try again.",
            retryable=True,
        )
    wanted = {**before["colors"], **colors}
    if wanted == before["colors"]:
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
            rewritten: dict[str, bytes] = {}
            for part, root, scheme in _schemes(archive):
                for slot, value in colors.items():
                    node = scheme.find(f"{A}{slot}")
                    if node is None:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED", "A theme color slot is missing."
                        )
                    for child in list(node):
                        node.remove(child)
                    etree.SubElement(node, f"{A}srgbClr", val=value[1:])
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
        if after["colors"] != wanted or [s.slide_id for s in updated.slides] != [
            s.slide_id for s in fidelity.slides
        ]:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The theme color edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "colors": wanted}
