"""Set an object's alt text (cNvPr@descr) and PowerPoint's "Mark as decorative" flag."""

from __future__ import annotations

import copy
import dataclasses
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    DECORATIVE_EXT_URI,
    DECORATIVE_NS,
    DRAWING_NS,
    PRESENTATION_NS,
    _parse_xml_part,
    inspect_pptx_snapshot,
    object_alt_text,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

A = f"{{{DRAWING_NS}}}"
MAX_ALT_TEXT = 2000


def _text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > MAX_ALT_TEXT
        or any(ord(c) < 32 and c not in "\n\t" for c in value)
    ):
        raise invalid_request(
            f"{field} must be text of at most {MAX_ALT_TEXT} characters.", field=field
        )
    return value


def _flag(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise invalid_request(f"{field} must be true or false.", field=field)
    return value


def _apply(nonvisual: etree._Element, alt_text: str, decorative: bool) -> None:
    if alt_text:
        nonvisual.set("descr", alt_text)
    elif "descr" in nonvisual.attrib:
        del nonvisual.attrib["descr"]
    extensions = nonvisual.find(f"{A}extLst")
    if extensions is not None:
        for extension in extensions.findall(f"{A}ext"):
            if extension.get("uri") == DECORATIVE_EXT_URI:
                extensions.remove(extension)
    if decorative:
        if extensions is None:
            extensions = etree.SubElement(nonvisual, f"{A}extLst")
        extension = etree.SubElement(extensions, f"{A}ext", uri=DECORATIVE_EXT_URI)
        etree.SubElement(
            extension, f"{{{DECORATIVE_NS}}}decorative", nsmap={"adec": DECORATIVE_NS}, val="1"
        )
    if extensions is not None and not len(extensions):
        nonvisual.remove(extensions)


def set_alt_text(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "object_id",
            "expected_alt_text",
            "expected_decorative",
            "alt_text",
            "decorative",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    object_id = editor._uuid_field(params.get("object_id"), "object_id")
    expected_text = _text(params.get("expected_alt_text"), "expected_alt_text")
    expected_flag = _flag(params.get("expected_decorative"), "expected_decorative")
    alt_text = _text(params.get("alt_text"), "alt_text").strip()
    decorative = _flag(params.get("decorative"), "decorative")
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
    slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
    obj = (
        next((item for item in slide.objects if item.object_id == object_id), None)
        if slide is not None
        else None
    )
    if slide is None or obj is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected object is unavailable."
        )
    if obj.alt_text is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED", "This object's alt text stays read-only."
        )
    if (obj.alt_text, obj.decorative) != (expected_text, expected_flag):
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The alt text changed. Refresh and try again.",
            retryable=True,
        )
    if (alt_text, decorative) == (obj.alt_text, obj.decorative):
        return {
            "changed": False,
            "revision_id": source["revision_id"],
            "revision_number": int(source["revision_number"]),
            "sha256": source["sha256"],
            "byte_size": int(source["byte_size"]),
        }

    def write(original: Path, target: Path) -> bool:
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            matches = root.xpath(
                ".//p:cSld/p:spTree//*[self::p:nvSpPr or self::p:nvPicPr or "
                "self::p:nvGraphicFramePr or self::p:nvCxnSpPr or self::p:nvGrpSpPr]"
                "/p:cNvPr[@id=$id]",
                namespaces={"p": PRESENTATION_NS},
                id=obj.ooxml_id,
            )
            if len(matches) != 1 or object_alt_text(matches[0]) != (
                expected_text,
                expected_flag,
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET",
                    "The alt text changed. Refresh and try again.",
                    retryable=True,
                )
            _apply(matches[0], alt_text, decorative)
            rewritten = etree.tostring(
                root, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            with zipfile.ZipFile(target, "w", allowZip64=True) as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    if info.filename == slide.part_name:
                        output.writestr(copy.copy(info), rewritten)
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
        before = {o.object_id: o for page in fidelity.slides for o in page.objects}
        after = {o.object_id: o for page in updated.slides for o in page.objects}
        revised = after.get(object_id)
        if (
            revised is None
            or (revised.alt_text, revised.decorative) != (alt_text, decorative)
            or dataclasses.replace(revised, alt_text=obj.alt_text, decorative=obj.decorative) != obj
            or {k: v for k, v in after.items() if k != object_id}
            != {k: v for k, v in before.items() if k != object_id}
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The alt text edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {
        **result,
        "slide_id": slide_id,
        "object_id": object_id,
        "alt_text": alt_text,
        "decorative": decorative,
    }
