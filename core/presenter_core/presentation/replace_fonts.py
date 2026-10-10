"""Deck-wide font replacement, like PowerPoint's Replace Fonts.

Every typeface named in slides, layouts, masters, notes, charts, diagrams and the
themes' heading/body fonts is listed with how often it is used; replacing one renames
it everywhere in one revision. Theme references (+mj-lt, +mn-ea, ...) are not fonts
and are left alone, so text that follows the theme changes only when a theme font is
itself replaced. Every theme part counts, including the notes master's.

Runs inside equations (Office Math) are listed and replaced like PowerPoint does,
and each font reports how many of its uses are in equations: an equation needs a
typeface with math tables, so replacing Cambria Math there changes how it renders.
"""

from __future__ import annotations

import copy
import dataclasses
import re
import shutil
import zipfile
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import DRAWING_NS, _parse_xml_part, inspect_pptx_snapshot
from presenter_core.presentation.theme_fonts import _font_field, _load

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

A = f"{{{DRAWING_NS}}}"
FONT_TAGS = {f"{A}latin", f"{A}ea", f"{A}cs", f"{A}sym", f"{A}buFont"}
# PANOSE, pitch and charset describe the old typeface, so they go with it.
FONT_HINTS = ("panose", "pitchFamily", "charset")
PARTS = re.compile(
    r"ppt/(slides|slideLayouts|slideMasters|notesSlides|notesMasters|handoutMasters"
    r"|charts|diagrams)/[^/]+\.xml"
)
FONT_LIMIT = 200
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
THEMES = re.compile(r"ppt/theme/[^/]+\.xml")


def _font_elements(part: str, root: Any, themes: set[str]) -> list[Any]:
    if part in themes:
        return [
            element
            for element in root.xpath(
                "./a:themeElements/a:fontScheme/*/*[self::a:latin or self::a:ea or self::a:cs]",
                namespaces={"a": DRAWING_NS},
            )
            if element.get("typeface") and not element.get("typeface").startswith("+")
        ]
    return [
        element
        for element in root.iter(*FONT_TAGS)
        if element.get("typeface") and not element.get("typeface").startswith("+")
    ]


def _math_elements(root: Any) -> list[Any]:
    return [
        element
        for zone in root.iter(f"{{{MATH_NS}}}oMathPara", f"{{{MATH_NS}}}oMath")
        if zone.getparent() is None or etree.QName(zone.getparent()).namespace != MATH_NS
        for element in zone.iter(*FONT_TAGS)
        if element.get("typeface") and not element.get("typeface").startswith("+")
    ]


def _scan(
    archive: zipfile.ZipFile, math: Counter[str] | None = None
) -> tuple[Counter[str], set[str], list[str]]:
    members = {info.filename: info for info in archive.infolist()}
    themes = {name for name in members if THEMES.fullmatch(name)}
    parts = sorted(name for name in members if PARTS.fullmatch(name)) + sorted(themes)
    counts: Counter[str] = Counter()
    theme_fonts: set[str] = set()
    for part in parts:
        root = _parse_xml_part(archive, members[part])
        if math is not None and part not in themes:
            math.update(element.get("typeface") for element in _math_elements(root))
        for element in _font_elements(part, root, themes):
            counts[element.get("typeface")] += 1
            if part in themes:
                theme_fonts.add(element.get("typeface"))
    return counts, theme_fonts, parts


def _listing(
    counts: Counter[str], theme_fonts: set[str], math: Counter[str]
) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "uses": uses,
            "theme": name in theme_fonts,
            "equation_uses": math.get(name, 0),
        }
        for name, uses in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    ][:FONT_LIMIT]


def list_fonts(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(params, {"project_id", "document_id", "expected_revision_id"})
    _project, _document, revision, source, path = _load(editor, params)
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        math: Counter[str] = Counter()
        counts, theme_fonts, _parts = _scan(archive, math)
    return {
        "revision_id": revision,
        "fonts": _listing(counts, theme_fonts, math),
        "truncated": len(counts) > FONT_LIMIT,
    }


def replace_fonts(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "font",
            "expected_uses",
            "replacement_font",
        },
    )
    old = params.get("font")
    if not isinstance(old, str) or not old or len(old) > 256:
        raise invalid_request("Choose a font used in this presentation.", field="font")
    new = _font_field(params.get("replacement_font"), "replacement_font")
    expected_uses = params.get("expected_uses")
    if type(expected_uses) is not int or expected_uses < 1:
        raise invalid_request("expected_uses must be a positive count.", field="expected_uses")
    project, document, revision, source, path = _load(editor, params)
    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        before, _theme_fonts, _parts = _scan(archive)
    if before.get(old, 0) != expected_uses:
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The fonts in this presentation changed. Refresh and try again.",
            retryable=True,
        )
    if new == old:
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
    touched: list[str] = []

    def write(original: Path, target: Path) -> bool:
        touched.clear()
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            members = {info.filename: info for info in archive.infolist()}
            themes = {name for name in members if THEMES.fullmatch(name)}
            _counts, _fonts, parts = _scan(archive)
            rewritten: dict[str, bytes] = {}
            for part in parts:
                root = _parse_xml_part(archive, members[part])
                matches = [
                    element
                    for element in _font_elements(part, root, themes)
                    if element.get("typeface") == old
                ]
                if not matches:
                    continue
                for element in matches:
                    element.set("typeface", new)
                    for hint in FONT_HINTS:
                        element.attrib.pop(hint, None)
                rewritten[part] = etree.tostring(
                    root, encoding="UTF-8", xml_declaration=True, standalone=True
                )
                touched.append(part)
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
        with zipfile.ZipFile(target) as archive:
            after, _theme_fonts, _parts = _scan(archive)
        expected = before.copy()
        expected[new] += expected.pop(old)
        with target.open("rb") as handle:
            updated = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(target),
                byte_size=target.stat().st_size,
            )

        def neutral(obj: Any) -> Any:
            # Only the named font family may change, and its style fingerprint with it.
            style = obj.text_style
            if style is not None:
                family = new if style.font_family == old else style.font_family
                style = dataclasses.replace(style, font_family=family, fingerprint=None)
            return dataclasses.replace(obj, text_style=style)

        def adjusted(obj: Any) -> Any:
            style = obj.text_style
            if style is not None:
                style = dataclasses.replace(style, fingerprint=None)
            return dataclasses.replace(obj, text_style=style)

        old_objects = [neutral(o) for page in fidelity.slides for o in page.objects]
        new_objects = [adjusted(o) for page in updated.slides for o in page.objects]
        if (
            after != expected
            or [s.slide_id for s in updated.slides] != [s.slide_id for s in fidelity.slides]
            or old_objects != new_objects
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The font replacement did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {
        **result,
        "font": old,
        "replacement_font": new,
        "replaced_uses": expected_uses,
        "parts": len(touched),
    }
