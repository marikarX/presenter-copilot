"""Constrained, revisioned text edits for Presentation Workspace."""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import io
import math
import os
import posixpath
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from lxml import etree  # type: ignore[import-untyped]
from PIL import Image

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.ingestion.security import (
    MAX_ARCHIVE_ENTRIES,
    MAX_ARCHIVE_EXPANDED_BYTES,
    MAX_SOURCE_BYTES,
    preflight_source,
)
from presenter_core.presentation.fidelity import (
    _PARAGRAPH_BULLET_TYPE_NAMES,
    DRAWING_NS,
    EMU_PER_POINT,
    MAX_BULLET_SIZE_PERCENT,
    MAX_NUMBERING_START,
    MAX_SHAPE_LINE_WIDTH_PT,
    MAX_SLIDE_DIMENSION_EMU,
    MAX_SPEAKER_NOTES_CHARS,
    MAX_SPEAKER_NOTES_PARAGRAPHS,
    MAX_TEXT_FIRST_LINE_INDENT_PT,
    MAX_TEXT_LEFT_INDENT_PT,
    MAX_TEXT_LINE_SPACING_PT,
    MAX_TEXT_PARAGRAPH_SPACING_PT,
    MIN_BULLET_SIZE_PERCENT,
    NOTES_SLIDE_REL_TYPE,
    OBJECT_LIMIT,
    PARAGRAPH_AUTONUM_TYPE_BY_MODE,
    PARAGRAPH_BULLET_CHAR_BY_MODE,
    PARAGRAPH_BULLET_MODES,
    PRESENTATION_NS,
    REL_NS,
    SHAPE_LINE_DASHES,
    SLIDE_LIMIT,
    FidelityGeometry,
    FidelityPictureAdjustment,
    FidelityPictureCrop,
    FidelityRotation,
    _formatable_text_runs,
    _is_uniform_run_text_shape,
    _notes_body_is_plain_editable,
    _paragraph_bullet_decoration_for_shape,
    _paragraph_bullet_mode_for_shape,
    _paragraph_property_insert_index,
    _paragraph_text,
    _parse_xml_part,
    _picture_adjustment,
    _picture_crop,
    _relationships,
    _resolve_internal_part,
    _shape_style,
    _styled_paragraphs,
    _text_style_for_shape,
    inspect_pptx_snapshot,
    object_rotation,
    plain_bullet_font,
)
from presenter_core.presentation.revisions import MAX_REVISION_NUMBER
from presenter_core.storage.paths import normalize_project_id
from presenter_core.storage.service import StorageManager

_NS = {
    "p": PRESENTATION_NS,
    "a": DRAWING_NS,
    "r": REL_NS,
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}
_PRESENTATION_SLIDE_REL_TYPE = f"{REL_NS}/slide"
_NOTES_MASTER_REL_TYPE = f"{REL_NS}/notesMaster"
_SLIDE_LAYOUT_REL_TYPE = f"{REL_NS}/slideLayout"
_IMAGE_REL_TYPE = f"{REL_NS}/image"
_HYPERLINK_REL_TYPE = f"{REL_NS}/hyperlink"
_SLIDE_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
_NOTES_SLIDE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT_CHARS = 2_000
_MAX_REPLACEMENT_IMAGE_BYTES = 4 * 1024 * 1024
_MAX_REPLACEMENT_IMAGE_DIMENSION = 8_192
_MAX_REPLACEMENT_IMAGE_PIXELS = 20_000_000
_MAX_XML_PART_BYTES = 8 * 1024 * 1024
_COPY_CHUNK_BYTES = 1024 * 1024
_DUPLICATE_OFFSET_EMU = 228_600
_MAX_OOXML_SHAPE_ID = 2_147_483_647
_MAX_OOXML_SLIDE_ID = 2_147_483_647


def _next_ooxml_shape_id(shape_tree: etree._Element) -> str:
    """Allocate above every source ID, including preserved compatibility branches.

    Duplicate raw IDs are expected in mutually exclusive mc:AlternateContent
    branches and opaque fallback payloads. The fidelity inventory validates
    uniqueness among effective drawing objects before any writer reaches here.
    """
    raw_shape_ids = shape_tree.xpath(".//p:cNvPr/@id", namespaces=_NS)
    try:
        shape_ids = [int(value) for value in raw_shape_ids]
    except ValueError as error:
        raise CoreDomainError(
            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
            "The slide contains an unsupported shape identifier.",
        ) from error
    if any(value < 0 or value > _MAX_OOXML_SHAPE_ID for value in shape_ids):
        raise CoreDomainError(
            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
            "The slide contains an unsupported shape identifier.",
        )
    maximum_shape_id = max(shape_ids, default=0)
    if maximum_shape_id >= _MAX_OOXML_SHAPE_ID:
        raise CoreDomainError(
            "PRESENTATION_EDIT_RESOURCE_LIMIT",
            "This slide cannot allocate another safe shape identifier.",
        )
    return str(maximum_shape_id + 1)


@contextmanager
def _verified_source_archive(
    path: Path,
    *,
    expected_sha256: str,
    expected_byte_size: int,
) -> Iterator[zipfile.ZipFile]:
    """Open the exact verified revision bytes used by a package rewrite."""
    with path.open("rb") as source_handle:
        if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_CHANGED",
                "The stored presentation no longer matches its revision record.",
            )
        digest = hashlib.sha256()
        while chunk := source_handle.read(_COPY_CHUNK_BYTES):
            digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_CHANGED",
                "The stored presentation no longer matches its revision record.",
            )
        source_handle.seek(0)
        with zipfile.ZipFile(source_handle, "r") as archive:
            yield archive


class PresentationEditService:
    """Apply narrow domain edits and persist immutable PPTX revisions."""

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage

    def replace_single_run_text(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._replace_text_shape(
            params,
            operation_type="replace_single_run_text",
            allow_uniform_runs=False,
        )

    def replace_text_shape(
        self,
        params: dict[str, Any],
        *,
        on_commit: Callable[[sqlite3.Connection, str], None] | None = None,
    ) -> dict[str, Any]:
        """Replace text in one run or in multiple runs with identical formatting."""
        return self._replace_text_shape(
            params,
            operation_type="replace_text_shape",
            allow_uniform_runs=True,
            on_commit=on_commit,
        )

    def _replace_text_shape(
        self,
        params: dict[str, Any],
        *,
        operation_type: str,
        allow_uniform_runs: bool,
        on_commit: Callable[[sqlite3.Connection, str], None] | None = None,
    ) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "operation_type",
                "slide_id",
                "object_id",
                "expected_text",
                "replacement_text",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        if params.get("operation_type") != operation_type:
            raise invalid_request(
                f"operation_type must be {operation_type}.", field="operation_type"
            )
        expected_text = self._text_field(params.get("expected_text"), "expected_text")
        replacement_text = self._text_field(params.get("replacement_text"), "replacement_text")

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        if replacement_text == expected_text:
            return {
                "changed": False,
                "revision_id": source["revision_id"],
                "revision_number": int(source["revision_number"]),
                "sha256": source["sha256"],
                "byte_size": int(source["byte_size"]),
            }

        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                object_id=object_id,
                expected_text=expected_text,
                replacement_text=replacement_text,
                allow_uniform_runs=allow_uniform_runs,
            ),
            on_commit=on_commit,
        )

    def format_single_run_text(self, params: dict[str, Any]) -> dict[str, Any]:
        """Compatibility route for formatting a verified single text run."""
        return self._format_text_shape(params, require_single_run=True)

    def fit_text_shape(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.text_fit_editing import fit_text

        return fit_text(self, params)

    def format_text_shape(self, params: dict[str, Any]) -> dict[str, Any]:
        """Apply bounded run formatting and paragraph formatting to a simple text shape."""
        return self._format_text_shape(params, require_single_run=False)

    def _format_text_shape(
        self, params: dict[str, Any], *, require_single_run: bool
    ) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "object_id",
                "expected_text",
                "expected_style_fingerprint",
                "replacement_style",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        expected_text = self._text_field(
            params.get("expected_text"), "expected_text", allow_newlines=True
        )
        fingerprint = params.get("expected_style_fingerprint")
        if not isinstance(fingerprint, str) or not _SHA256.fullmatch(fingerprint):
            raise invalid_request(
                "expected_style_fingerprint must be a SHA-256 fingerprint.",
                field="expected_style_fingerprint",
            )
        replacement_style = self._text_style_field(params.get("replacement_style"))

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        obj = (
            next((item for item in slide.objects if item.object_id == object_id), None)
            if slide is not None
            else None
        )
        if slide is None or obj is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected text shape is unavailable."
            )
        style = obj.text_style
        if (
            not obj.text_format_edit_candidate
            or (require_single_run and not obj.single_run_text_edit_candidate)
            or style is None
            or not style.editable
            or style.fingerprint is None
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text shape does not use a supported plain-paragraph formatting structure.",
            )
        if obj.text != expected_text or style.fingerprint != fingerprint:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The selected text or formatting changed. Refresh the preview and try again.",
            )
        if "font_color" in replacement_style and not style.color_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text run has incompatible direct color fills.",
            )
        if "alignment" in replacement_style and not style.alignment_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph does not support direct alignment formatting.",
            )
        if "bullet_mode" in replacement_style and not style.bullet_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's bullet style cannot be safely edited.",
            )
        if "bullet_color" in replacement_style and not style.bullet_color_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's bullet color cannot be safely edited.",
            )
        if "bullet_size_percent" in replacement_style and not style.bullet_size_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's bullet size cannot be safely edited.",
            )
        if "numbering_start" in replacement_style and not style.numbering_start_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's list numbering cannot be safely edited.",
            )
        if "left_indent_pt" in replacement_style and not style.left_indent_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's left indentation cannot be safely edited.",
            )
        if "first_line_indent_pt" in replacement_style and not style.first_line_indent_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's first-line indentation cannot be safely edited.",
            )
        if "line_spacing_pt" in replacement_style and not style.line_spacing_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's line spacing cannot be safely edited.",
            )
        if "space_before_pt" in replacement_style and not style.space_before_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's before spacing cannot be safely edited.",
            )
        if "space_after_pt" in replacement_style and not style.space_after_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's after spacing cannot be safely edited.",
            )
        if all(
            getattr(style, "bullet_state" if name == "bullet_mode" else name) == value
            for name, value in replacement_style.items()
        ):
            return {
                "changed": False,
                "revision_id": source["revision_id"],
                "revision_number": int(source["revision_number"]),
                "sha256": source["sha256"],
                "byte_size": int(source["byte_size"]),
            }

        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_text_style_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                object_id=object_id,
                expected_text=expected_text,
                expected_style_fingerprint=fingerprint,
                replacement_style=replacement_style,
                require_single_run=require_single_run,
            ),
        )

    def format_shape_style(self, params: dict[str, Any]) -> dict[str, Any]:
        """Set direct solid RGB fill or outline color on one simple shape."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "object_id",
                "expected_style_fingerprint",
                "replacement_style",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        fingerprint = params.get("expected_style_fingerprint")
        if not isinstance(fingerprint, str) or not _SHA256.fullmatch(fingerprint):
            raise invalid_request(
                "expected_style_fingerprint must be a SHA-256 fingerprint.",
                field="expected_style_fingerprint",
            )
        replacement_style = self._shape_style_field(params.get("replacement_style"))

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        obj = (
            next((item for item in slide.objects if item.object_id == object_id), None)
            if slide is not None
            else None
        )
        if slide is None or obj is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected shape is unavailable."
            )
        style = obj.shape_style
        if style is None or not style.editable or style.fingerprint is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This shape does not use a supported direct fill or outline color.",
            )
        if obj.kind != "sp" or style.fingerprint != fingerprint:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The selected shape styling changed. Refresh the preview and try again.",
            )
        if "fill_color" in replacement_style and not style.fill_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This shape fill uses a style the color editor cannot safely retain.",
            )
        if "line_color" in replacement_style and not style.line_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This shape outline uses a style the color editor cannot safely retain.",
            )
        if (
            replacement_style.keys() & {"line_width_pt", "line_dash"}
            and not style.line_format_editable
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This shape outline uses a width or dash the editor cannot safely retain.",
            )
        if all(
            getattr(style, "bullet_state" if name == "bullet_mode" else name) == value
            for name, value in replacement_style.items()
        ):
            return {
                "changed": False,
                "revision_id": source["revision_id"],
                "revision_number": int(source["revision_number"]),
                "sha256": source["sha256"],
                "byte_size": int(source["byte_size"]),
            }

        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_shape_style_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                object_id=object_id,
                expected_style_fingerprint=fingerprint,
                replacement_style=replacement_style,
            ),
        )

    def replace_speaker_notes(
        self,
        params: dict[str, Any],
        *,
        on_commit: Callable[[sqlite3.Connection, str], None] | None = None,
    ) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "expected_text",
                "replacement_text",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        expected_text = self._speaker_notes_field(params.get("expected_text"), "expected_text")
        replacement_text = self._speaker_notes_field(
            params.get("replacement_text"), "replacement_text"
        )

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        if replacement_text == expected_text:
            return {
                "changed": False,
                "revision_id": source["revision_id"],
                "revision_number": int(source["revision_number"]),
                "sha256": source["sha256"],
                "byte_size": int(source["byte_size"]),
            }
        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_notes_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                expected_text=expected_text,
                replacement_text=replacement_text,
            ),
            on_commit=on_commit,
        )

    def transform_object(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "object_id",
                "expected_geometry",
                "replacement_geometry",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        expected_geometry = self._geometry_field(
            params.get("expected_geometry"), "expected_geometry"
        )
        replacement_geometry = self._geometry_field(
            params.get("replacement_geometry"), "replacement_geometry"
        )

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
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
        if not obj.geometry_editable or obj.geometry is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This object does not use a supported slide-level transform.",
            )
        if obj.geometry != expected_geometry:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The object position or size changed. Refresh the preview and try again.",
            )
        self._validate_geometry_bounds(
            replacement_geometry,
            slide_width_emu=fidelity.slide_width_emu,
            slide_height_emu=fidelity.slide_height_emu,
            field="replacement_geometry",
        )
        if replacement_geometry == expected_geometry:
            return {
                "changed": False,
                "revision_id": source["revision_id"],
                "revision_number": int(source["revision_number"]),
                "sha256": source["sha256"],
                "byte_size": int(source["byte_size"]),
            }

        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_geometry_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                object_id=object_id,
                expected_geometry=expected_geometry,
                replacement_geometry=replacement_geometry,
            ),
        )

    def replace_picture_image(self, params: dict[str, Any]) -> dict[str, Any]:
        """Replace one supported picture without changing its frame or shared media."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "object_id",
                "expected_geometry",
                "expected_crop",
                "image_base64",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        expected_geometry = self._geometry_field(
            params.get("expected_geometry"), "expected_geometry"
        )
        expected_crop = self._picture_crop_field(params.get("expected_crop"), "expected_crop")
        image_bytes, image_format = self._replacement_image_field(params.get("image_base64"))

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        obj = (
            next((item for item in slide.objects if item.object_id == object_id), None)
            if slide is not None
            else None
        )
        if slide is None or obj is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected picture is unavailable."
            )
        if (
            obj.kind != "pic"
            or not obj.geometry_editable
            or obj.geometry is None
            or obj.picture_crop is None
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This picture does not use a supported embedded-image structure.",
            )
        if obj.geometry != expected_geometry or obj.picture_crop != expected_crop:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The picture changed. Refresh the preview and try again.",
                retryable=True,
            )

        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_picture_image_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                object_id=object_id,
                expected_geometry=expected_geometry,
                expected_crop=expected_crop,
                image_bytes=image_bytes,
                image_format=image_format,
            ),
        )

    def rotate_object(self, params: dict[str, Any]) -> dict[str, Any]:
        """Set rotation and flips on a verified slide-level shape or picture."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "object_id",
                "expected_geometry",
                "expected_rotation",
                "replacement_rotation",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        expected_geometry = self._geometry_field(
            params.get("expected_geometry"), "expected_geometry"
        )
        expected_rotation = self._rotation_field(
            params.get("expected_rotation"), "expected_rotation"
        )
        replacement_rotation = self._rotation_field(
            params.get("replacement_rotation"), "replacement_rotation"
        )
        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
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
        if not obj.geometry_editable or obj.geometry is None or obj.rotation is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "Only slide-level shapes and pictures can be rotated.",
            )
        if obj.geometry != expected_geometry or obj.rotation != expected_rotation:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The object changed. Refresh the preview and try again.",
                retryable=True,
            )
        if replacement_rotation == expected_rotation:
            return {
                "changed": False,
                "revision_id": source["revision_id"],
                "revision_number": int(source["revision_number"]),
                "sha256": source["sha256"],
                "byte_size": int(source["byte_size"]),
            }
        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_geometry_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                object_id=object_id,
                expected_geometry=expected_geometry,
                replacement_geometry=expected_geometry,
                expected_rotation=expected_rotation,
                replacement_rotation=replacement_rotation,
            ),
        )

    @staticmethod
    def _rotation_field(value: Any, field: str) -> FidelityRotation:
        names = {"rotation_degrees", "flip_horizontal", "flip_vertical"}
        if not isinstance(value, dict) or set(value) != names:
            raise invalid_request(
                f"{field} must contain rotation_degrees, flip_horizontal and flip_vertical.",
                field=field,
            )
        degrees = value["rotation_degrees"]
        if (
            type(degrees) not in {int, float}
            or not math.isfinite(degrees)
            or not 0 <= degrees < 360
            or abs(degrees * 60_000 - round(degrees * 60_000)) > 1e-4
        ):
            raise invalid_request(
                f"{field}.rotation_degrees must be at least 0 and below 360.",
                field=f"{field}.rotation_degrees",
            )
        if any(type(value[name]) is not bool for name in ("flip_horizontal", "flip_vertical")):
            raise invalid_request(f"{field} flips must be booleans.", field=field)
        return FidelityRotation(
            rotation=round(degrees * 60_000) % 21_600_000,
            flip_horizontal=value["flip_horizontal"],
            flip_vertical=value["flip_vertical"],
        )

    def adjust_picture(self, params: dict[str, Any]) -> dict[str, Any]:
        """Set brightness, contrast and grayscale on a verified embedded picture."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "object_id",
                "expected_geometry",
                "expected_adjustment",
                "replacement_adjustment",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        expected_geometry = self._geometry_field(
            params.get("expected_geometry"), "expected_geometry"
        )
        expected_adjustment = self._picture_adjustment_field(
            params.get("expected_adjustment"), "expected_adjustment"
        )
        replacement_adjustment = self._picture_adjustment_field(
            params.get("replacement_adjustment"), "replacement_adjustment"
        )
        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        obj = (
            next((item for item in slide.objects if item.object_id == object_id), None)
            if slide is not None
            else None
        )
        if slide is None or obj is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected picture is unavailable."
            )
        if (
            obj.kind != "pic"
            or obj.geometry is None
            or obj.picture_crop is None
            or obj.picture_adjustment is None
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This picture uses image effects that cannot be adjusted safely.",
            )
        if obj.geometry != expected_geometry or obj.picture_adjustment != expected_adjustment:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The picture changed. Refresh the preview and try again.",
                retryable=True,
            )
        if replacement_adjustment == expected_adjustment:
            return {
                "changed": False,
                "revision_id": source["revision_id"],
                "revision_number": int(source["revision_number"]),
                "sha256": source["sha256"],
                "byte_size": int(source["byte_size"]),
            }
        crop = obj.picture_crop
        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_picture_crop_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                object_id=object_id,
                expected_geometry=expected_geometry,
                expected_crop=crop,
                replacement_crop=crop,
                expected_adjustment=expected_adjustment,
                replacement_adjustment=replacement_adjustment,
            ),
        )

    @staticmethod
    def _picture_adjustment_field(value: Any, field: str) -> FidelityPictureAdjustment:
        if not isinstance(value, dict):
            raise invalid_request(f"{field} must be an object.", field=field)
        reject_unknown_fields(value, {"brightness_percent", "contrast_percent", "grayscale"})
        result: dict[str, Any] = {}
        for name, key in (("brightness_percent", "brightness"), ("contrast_percent", "contrast")):
            item = value.get(name, 0)
            if type(item) is not int or not -100 <= item <= 100:
                raise invalid_request(
                    f"{field}.{name} must be an integer from -100 to 100.", field=f"{field}.{name}"
                )
            result[key] = item
        grayscale = value.get("grayscale", False)
        if type(grayscale) is not bool:
            raise invalid_request(
                f"{field}.grayscale must be a boolean.", field=f"{field}.grayscale"
            )
        return FidelityPictureAdjustment(grayscale=grayscale, **result)

    def crop_picture(self, params: dict[str, Any]) -> dict[str, Any]:
        """Apply a bounded source crop to a verified embedded picture."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "object_id",
                "expected_geometry",
                "expected_crop",
                "replacement_crop",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        expected_geometry = self._geometry_field(
            params.get("expected_geometry"), "expected_geometry"
        )
        expected_crop = self._picture_crop_field(params.get("expected_crop"), "expected_crop")
        replacement_crop = self._picture_crop_field(
            params.get("replacement_crop"), "replacement_crop"
        )

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        obj = (
            next((item for item in slide.objects if item.object_id == object_id), None)
            if slide is not None
            else None
        )
        if slide is None or obj is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected picture is unavailable."
            )
        if obj.kind != "pic" or not obj.geometry_editable or obj.geometry is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This object does not use a supported picture layout.",
            )
        if obj.picture_crop is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This picture uses a fill or relationship structure that cannot be cropped safely.",
            )
        if obj.geometry != expected_geometry or obj.picture_crop != expected_crop:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The picture changed. Refresh the preview and try again.",
                retryable=True,
            )
        if replacement_crop == expected_crop:
            return {
                "changed": False,
                "revision_id": source["revision_id"],
                "revision_number": int(source["revision_number"]),
                "sha256": source["sha256"],
                "byte_size": int(source["byte_size"]),
            }

        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_picture_crop_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                object_id=object_id,
                expected_geometry=expected_geometry,
                expected_crop=expected_crop,
                replacement_crop=replacement_crop,
            ),
        )

    def reorder_slides(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "expected_revision_id", "ordered_slide_ids"},
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        supplied_order = params.get("ordered_slide_ids")
        if (
            not isinstance(supplied_order, list)
            or not supplied_order
            or len(supplied_order) > SLIDE_LIMIT
        ):
            raise invalid_request(
                f"ordered_slide_ids must contain between 1 and {SLIDE_LIMIT} slide IDs.",
                field="ordered_slide_ids",
            )
        ordered_slide_ids = [
            self._uuid_field(slide_id, f"ordered_slide_ids[{index}]")
            for index, slide_id in enumerate(supplied_order)
        ]
        if len(set(ordered_slide_ids)) != len(ordered_slide_ids):
            raise invalid_request(
                "ordered_slide_ids must not contain duplicates.", field="ordered_slide_ids"
            )

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        current_order = [slide.slide_id for slide in fidelity.slides]
        if len(ordered_slide_ids) != len(current_order) or set(ordered_slide_ids) != set(
            current_order
        ):
            raise invalid_request(
                "ordered_slide_ids must be an exact permutation of the current slides.",
                field="ordered_slide_ids",
            )
        if ordered_slide_ids == current_order:
            return {
                "changed": False,
                "revision_id": source["revision_id"],
                "revision_number": int(source["revision_number"]),
                "sha256": source["sha256"],
                "byte_size": int(source["byte_size"]),
            }

        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_slide_order_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                expected_slide_ids=current_order,
                ordered_slide_ids=ordered_slide_ids,
            ),
        )

    def apply_slide_layout(self, params: dict[str, Any]) -> dict[str, Any]:
        """Apply a layout already used by a slide in this presentation revision."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "layout_source_slide_id",
                "layout_id",
                "placeholder_mapping",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        if ("layout_source_slide_id" in params) == ("layout_id" in params):
            raise invalid_request("Choose either a source slide layout or a native layout.")
        layout_source_slide_id = (
            self._uuid_field(params["layout_source_slide_id"], "layout_source_slide_id")
            if "layout_source_slide_id" in params
            else None
        )
        layout_id = (
            self._uuid_field(params["layout_id"], "layout_id") if "layout_id" in params else None
        )
        mapping = params.get("placeholder_mapping")
        if "placeholder_mapping" in params and (
            layout_id is None or not isinstance(mapping, list) or not mapping
        ):
            raise invalid_request(
                "Explicit placeholder mapping requires a native layout and nonempty assignments."
            )

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        if not any(item.slide_id == slide_id for item in fidelity.slides):
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        if layout_source_slide_id is not None and not any(
            item.slide_id == layout_source_slide_id for item in fidelity.slides
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_LAYOUT_NOT_FOUND",
                "Choose a layout used by a slide in the current presentation revision.",
            )
        expected_slide_ids = [item.slide_id for item in fidelity.slides]

        result = self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_slide_layout_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                expected_slide_ids=expected_slide_ids,
                layout_source_slide_id=layout_source_slide_id,
                layout_id=layout_id,
                placeholder_mapping=mapping,
            ),
        )
        return {
            **result,
            **(
                {"layout_source_slide_id": layout_source_slide_id}
                if layout_source_slide_id
                else {"layout_id": layout_id}
            ),
        }

    def create_authored_slide(self, params: dict[str, Any]) -> dict[str, Any]:
        """Insert native content/notes as one operation, including in a review plan."""
        from presenter_core.presentation.creation import PresentationCreationService
        from presenter_core.presentation.templates import LAYOUTS, TEMPLATES

        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "layout_source_slide_id",
                "title",
                "bullets",
                "notes",
                "template",
                "layout",
            },
        )
        title = PresentationCreationService._text(params.get("title"), "title", 120)
        points = params.get("bullets", [])
        if not isinstance(points, list) or len(points) > 8:
            raise invalid_request("Provide up to 8 points.", field="bullets")
        points = [PresentationCreationService._text(point, "bullets", 200) for point in points]
        notes = PresentationCreationService._text(
            params.get("notes", ""), "notes", 4000, allow_empty=True
        )
        # Match the normal native notes editor's paragraph bounds.
        self._speaker_notes_field(notes, "notes")
        template, layout = params.get("template", "classic"), params.get("layout", "points")
        if not isinstance(template, str) or template not in TEMPLATES:
            raise invalid_request("Choose a supported template.", field="template")
        if (
            not isinstance(layout, str)
            or layout not in LAYOUTS
            or (layout == "statement" and len(points) > 1)
        ):
            raise invalid_request(
                "Choose a supported layout; Statement accepts one point.", field="layout"
            )
        scope = {
            key: value
            for key, value in params.items()
            if key
            in {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "layout_source_slide_id",
            }
        }
        result = self._create_slide(
            scope,
            content={
                "heading": title,
                "points": points,
                "notes": notes,
                "template": template,
                "layout": layout,
            },
        )
        return {**result, "slide_id": params["slide_id"]}

    def create_slide(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._create_slide(params)

    def _create_slide(
        self, params: dict[str, Any], *, content: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Insert a blank slide after the selected slide using its layout."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "layout_source_slide_id",
                "layout_id",
                "placeholder_text",
                "notes",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        if "layout_id" in params and ("layout_source_slide_id" in params or content is not None):
            raise invalid_request("Choose one native layout source.", field="layout_id")
        layout_id = (
            self._uuid_field(params["layout_id"], "layout_id") if "layout_id" in params else None
        )
        notes = None
        if "notes" in params:
            if layout_id is None or content is not None:
                raise invalid_request("Native notes need a native layout.")
            notes = self._speaker_notes_field(params["notes"], "notes")
        placeholder_text = params.get("placeholder_text")
        if placeholder_text is not None:
            if (
                layout_id is None
                or not isinstance(placeholder_text, list)
                or len(placeholder_text) > 20
            ):
                raise invalid_request("Native placeholder text needs a layout and up to 20 slots.")
            from presenter_core.presentation.creation import PresentationCreationService

            values = {}
            for item in placeholder_text:
                if not isinstance(item, dict) or set(item) != {"placeholder_id", "text"}:
                    raise invalid_request("Each placeholder needs an identity and text.")
                identity = self._uuid_field(item["placeholder_id"], "placeholder_id")
                if identity in values:
                    raise invalid_request("Placeholder identities must be unique.")
                text = PresentationCreationService._text(
                    item["text"], "text", 2000, allow_empty=True
                )
                if len(text.split("\n")) > 20:
                    raise invalid_request("A placeholder accepts up to 20 paragraphs.")
                values[identity] = text
            placeholder_text = values
        layout_source_slide_id = (
            self._uuid_field(params.get("layout_source_slide_id"), "layout_source_slide_id")
            if "layout_source_slide_id" in params
            else slide_id
        )

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        if slide is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        layout_source_slide = next(
            (item for item in fidelity.slides if item.slide_id == layout_source_slide_id), None
        )
        if layout_id is None and layout_source_slide is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_LAYOUT_NOT_FOUND",
                "Choose a layout used by a slide in the current presentation revision.",
            )
        if len(fidelity.slides) >= SLIDE_LIMIT:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "This presentation cannot contain another slide safely.",
            )

        created_slide_ids: list[str] = []

        def write_blank_slide(original_path: Path, staged_path: Path) -> None:
            def blank(destination: Path) -> str:
                return self._write_revised_blank_slide_package(
                    original_path,
                    destination,
                    document_id=document_id,
                    expected_sha256=str(source["sha256"]),
                    expected_byte_size=int(source["byte_size"]),
                    slide_id=slide_id,
                    layout_source_slide_id=layout_source_slide_id,
                    layout_id=layout_id,
                    placeholder_text=placeholder_text,
                )

            if content is None and notes is None:
                created_slide_ids.append(blank(staged_path))
            elif content is None:
                from presenter_core.presentation.authored import fill_native_notes

                with tempfile.TemporaryDirectory(prefix="presenter-native-") as directory:
                    blank_path = Path(directory) / "blank.pptx"
                    created_id = blank(blank_path)
                    fill_native_notes(
                        blank_path,
                        staged_path,
                        document_id=document_id,
                        slide_id=created_id,
                        notes=notes or "",
                    )
                    created_slide_ids.append(created_id)
            else:
                from presenter_core.presentation.authored import fill_authored_slide

                with tempfile.TemporaryDirectory(prefix="presenter-authored-") as directory:
                    blank_path = Path(directory) / "blank.pptx"
                    created_id = blank(blank_path)
                    fill_authored_slide(
                        blank_path,
                        staged_path,
                        document_id=document_id,
                        slide_id=created_id,
                        **content,
                    )
                    created_slide_ids.append(created_id)

        result = self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            write_blank_slide,
        )
        if len(created_slide_ids) != 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The blank slide did not pass validation.",
            )
        return {
            **result,
            "created_slide_id": created_slide_ids[0],
            **(
                {"layout_id": layout_id}
                if layout_id
                else {"layout_source_slide_id": layout_source_slide_id}
            ),
        }

    def duplicate_slide(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "expected_revision_id", "slide_id"},
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        if slide is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        if len(fidelity.slides) >= SLIDE_LIMIT:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "This presentation cannot contain another slide safely.",
            )
        if fidelity.object_count + len(slide.objects) > OBJECT_LIMIT:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "Duplicating this slide would exceed the workspace object limit.",
            )

        created_slide_ids: list[str] = []

        def write_duplicate(original_path: Path, staged_path: Path) -> None:
            created_slide_ids.append(
                self._write_revised_slide_duplicate_package(
                    original_path,
                    staged_path,
                    document_id=document_id,
                    expected_sha256=str(source["sha256"]),
                    expected_byte_size=int(source["byte_size"]),
                    slide_id=slide_id,
                )
            )

        result = self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            write_duplicate,
        )
        if len(created_slide_ids) != 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The duplicated slide did not pass validation.",
            )
        return {**result, "created_slide_id": created_slide_ids[0]}

    def create_text_box(self, params: dict[str, Any]) -> dict[str, Any]:
        """Insert one plain, centered text box into a verified slide revision."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "text",
                "geometry",
                "text_style",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        text = self._text_field(params.get("text"), "text")
        if not text.strip():
            raise invalid_request("text must not be empty.", field="text")
        text_style = self._text_style_field(params["text_style"]) if "text_style" in params else {}
        if set(text_style) - {"font_size_pt", "font_color", "bold", "italic", "alignment"}:
            raise invalid_request(
                "New text boxes support font size, color, emphasis and alignment."
            )

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        if slide is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        if fidelity.object_count >= OBJECT_LIMIT:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "This presentation cannot contain another object safely.",
            )
        width_emu = max(1, min(fidelity.slide_width_emu // 2, 4 * 914_400))
        height_emu = max(1, min(fidelity.slide_height_emu // 6, 914_400))
        geometry = FidelityGeometry(
            x_emu=(fidelity.slide_width_emu - width_emu) // 2,
            y_emu=(fidelity.slide_height_emu - height_emu) // 2,
            width_emu=width_emu,
            height_emu=height_emu,
        )
        if "geometry" in params:
            geometry = self._geometry_field(params["geometry"], "geometry")
            self._validate_geometry_bounds(
                geometry,
                slide_width_emu=fidelity.slide_width_emu,
                slide_height_emu=fidelity.slide_height_emu,
                field="geometry",
            )
        created_object_ids: list[str] = []

        def write_text_box(original_path: Path, staged_path: Path) -> None:
            created_object_ids.append(
                self._write_revised_text_box_package(
                    original_path,
                    staged_path,
                    document_id=document_id,
                    expected_sha256=str(source["sha256"]),
                    expected_byte_size=int(source["byte_size"]),
                    slide_id=slide_id,
                    expected_slide_ids=[item.slide_id for item in fidelity.slides],
                    expected_geometry=geometry,
                    text=text,
                    text_style=text_style,
                )
            )

        result = self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            write_text_box,
        )
        if len(created_object_ids) != 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The new text box did not pass validation.",
            )
        return {**result, "created_object_id": created_object_ids[0]}

    def list_picture_assets(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.assets import picture_assets

        return picture_assets(self, params, read=False)

    def read_picture_asset(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.assets import picture_assets

        return picture_assets(self, params, read=True)

    def create_picture(self, params: dict[str, Any]) -> dict[str, Any]:
        """Insert one embedded PNG or JPEG at an explicit in-bounds position."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "geometry",
                "alt_text",
                "image_base64",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        geometry = self._geometry_field(params.get("geometry"), "geometry")
        alt_text = self._text_field(params.get("alt_text", ""), "alt_text")
        image_bytes, image_format = self._replacement_image_field(params.get("image_base64"))

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        if slide is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        if fidelity.object_count >= OBJECT_LIMIT:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "This presentation cannot contain another object safely.",
            )
        self._validate_geometry_bounds(
            geometry,
            slide_width_emu=fidelity.slide_width_emu,
            slide_height_emu=fidelity.slide_height_emu,
            field="geometry",
        )

        created_object_ids: list[str] = []

        def write_picture(original_path: Path, staged_path: Path) -> None:
            created_object_ids.append(
                self._write_revised_picture_creation_package(
                    original_path,
                    staged_path,
                    document_id=document_id,
                    expected_sha256=str(source["sha256"]),
                    expected_byte_size=int(source["byte_size"]),
                    slide_id=slide_id,
                    expected_slide_ids=[item.slide_id for item in fidelity.slides],
                    geometry=geometry,
                    alt_text=alt_text,
                    image_bytes=image_bytes,
                    image_format=image_format,
                )
            )

        result = self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            write_picture,
        )
        if len(created_object_ids) != 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The new picture did not pass validation.",
            )
        return {**result, "created_object_id": created_object_ids[0]}

    def create_chart(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.charts import create_chart

        return create_chart(self, params)

    def replace_chart_data(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.chart_editing import replace_chart_data

        return replace_chart_data(self, params)

    def reshape_chart(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.chart_editing import replace_chart_data

        return replace_chart_data(self, params, structural=True)

    def fit_table_rows(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.tables import edit_table

        return edit_table(self, params, create=False, fitting=True)

    def merge_table_cells(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.tables import edit_table

        return edit_table(self, params, create=False, merging=True)

    def split_table_cells(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.tables import edit_table

        return edit_table(self, params, create=False, splitting=True)

    def set_table_borders(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.tables import edit_table

        return edit_table(self, params, create=False, borders=True)

    def format_table_cells(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.tables import edit_table

        return edit_table(self, params, create=False, formatting=True)

    def set_chart_marker(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.chart_markers import set_chart_marker

        return set_chart_marker(self, params)

    def set_chart_fill(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.chart_fills import set_chart_fill

        return set_chart_fill(self, params)

    def set_shape_fill(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.shape_fills import set_shape_fill

        return set_shape_fill(self, params)

    def set_chart_color(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.chart_colors import set_chart_color

        return set_chart_color(self, params)

    def set_chart_axis(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.chart_axes import set_chart_axis

        return set_chart_axis(self, params)

    def set_chart_labels(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.chart_labels import set_chart_labels

        return set_chart_labels(self, params)

    def set_chart_legend(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.chart_legend import set_chart_legend

        return set_chart_legend(self, params)

    def create_diagram(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.diagrams import edit_diagram

        return edit_diagram(self, params, create=True)

    def delete_diagram(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.diagrams import edit_diagram

        return edit_diagram(self, params, create=False, delete=True)

    def replace_diagram(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.diagrams import edit_diagram

        return edit_diagram(self, params, create=False)

    def create_table(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.tables import edit_table

        return edit_table(self, params, create=True)

    def replace_table_cells(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.tables import edit_table

        return edit_table(self, params, create=False)

    def reshape_table(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.tables import edit_table

        return edit_table(self, params, create=False, structural=True)

    def create_shape(self, params: dict[str, Any]) -> dict[str, Any]:
        """Insert one solid rectangle or ellipse at an explicit bounded position."""
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "shape_type",
                "geometry",
                "fill_color",
                "line_color",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        shape_type = params.get("shape_type")
        if not isinstance(shape_type, str) or shape_type not in {"rect", "ellipse"}:
            raise invalid_request("shape_type must be rect or ellipse.", field="shape_type")
        geometry = self._geometry_field(params.get("geometry"), "geometry")
        style = self._shape_style_field(
            {
                "fill_color": params.get("fill_color"),
                "line_color": params.get("line_color"),
            }
        )

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        if not any(item.slide_id == slide_id for item in fidelity.slides):
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        if fidelity.object_count >= OBJECT_LIMIT:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "This presentation cannot contain another object safely.",
            )
        self._validate_geometry_bounds(
            geometry,
            slide_width_emu=fidelity.slide_width_emu,
            slide_height_emu=fidelity.slide_height_emu,
            field="geometry",
        )

        created_object_ids: list[str] = []

        def write_shape(original_path: Path, staged_path: Path) -> None:
            created_object_ids.append(
                self._write_revised_shape_creation_package(
                    original_path,
                    staged_path,
                    document_id=document_id,
                    expected_sha256=str(source["sha256"]),
                    expected_byte_size=int(source["byte_size"]),
                    slide_id=slide_id,
                    expected_slide_ids=[item.slide_id for item in fidelity.slides],
                    shape_type=shape_type,
                    geometry=geometry,
                    replacement_style=style,
                )
            )

        result = self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            write_shape,
        )
        if len(created_object_ids) != 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The new shape did not pass validation.",
            )
        return {**result, "created_object_id": created_object_ids[0]}

    def delete_slide(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "expected_revision_id", "slide_id"},
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
            )
        if len(fidelity.slides) <= 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "A presentation must keep at least one slide.",
            )
        if not any(slide.slide_id == slide_id for slide in fidelity.slides):
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )

        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_slide_delete_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
            ),
        )

    def set_text_hyperlink(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.text_hyperlinks import set_text_hyperlink

        return set_text_hyperlink(self, params)

    def set_slide_background(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.slide_background import set_slide_background

        return set_slide_background(self, params)

    def change_object_layer(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.layering import change_object_layer

        return change_object_layer(self, params)

    def delete_object(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "object_id",
                "expected_geometry",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        expected_geometry = self._geometry_field(
            params.get("expected_geometry"), "expected_geometry"
        )

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
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
        if not obj.delete_editable or not obj.geometry_editable or obj.geometry is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This object cannot be removed safely in this version.",
            )
        if obj.geometry != expected_geometry:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The object changed. Refresh the preview and try again.",
            )

        return self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            lambda original_path, staged_path: self._write_revised_object_delete_package(
                original_path,
                staged_path,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                expected_byte_size=int(source["byte_size"]),
                slide_id=slide_id,
                object_id=object_id,
                expected_geometry=expected_geometry,
            ),
        )

    def duplicate_object(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {
                "project_id",
                "document_id",
                "expected_revision_id",
                "slide_id",
                "object_id",
                "expected_geometry",
            },
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        slide_id = self._uuid_field(params.get("slide_id"), "slide_id")
        object_id = self._uuid_field(params.get("object_id"), "object_id")
        expected_geometry = self._geometry_field(
            params.get("expected_geometry"), "expected_geometry"
        )

        source = self._current_revision_source(project_id, document_id)
        if source["revision_id"] != expected_revision_id:
            raise self._revision_conflict()
        source_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != int(source["byte_size"]):
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=str(source["sha256"]),
                byte_size=int(source["byte_size"]),
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
        if (
            obj.kind not in {"sp", "pic", "graphicFrame", "grpSp"}
            or not obj.delete_editable
            or not obj.geometry_editable
            or obj.geometry is None
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This object cannot be duplicated safely in this version.",
            )
        if obj.geometry != expected_geometry:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The object changed. Refresh the preview and try again.",
            )
        if obj.kind == "grpSp":
            # The paste writer allocates every descendant ID and clones chart graphs.
            result = self.paste_objects(
                {
                    "project_id": project_id,
                    "document_id": document_id,
                    "expected_revision_id": expected_revision_id,
                    "source_document_id": document_id,
                    "source_revision_id": expected_revision_id,
                    "source_slide_id": slide_id,
                    "slide_id": slide_id,
                    "object_ids": [object_id],
                }
            )
            return {**result, "created_object_id": result["created_object_ids"][0]}
        if fidelity.object_count >= OBJECT_LIMIT:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The presentation already contains the maximum number of supported objects.",
            )

        created_object_ids: list[str] = []

        def write_duplicate(original_path: Path, staged_path: Path) -> None:
            created_object_ids.append(
                self._write_revised_object_duplicate_package(
                    original_path,
                    staged_path,
                    document_id=document_id,
                    expected_sha256=str(source["sha256"]),
                    expected_byte_size=int(source["byte_size"]),
                    slide_id=slide_id,
                    object_id=object_id,
                    expected_geometry=expected_geometry,
                )
            )

        result = self._commit_revision(
            project_id,
            document_id,
            expected_revision_id,
            source,
            write_duplicate,
        )
        return {**result, "created_object_id": created_object_ids[0]}

    def group_objects(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.object_groups import edit_group

        return edit_group(self, params, ungroup=False)

    def ungroup_object(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.object_groups import edit_group

        return edit_group(self, params, ungroup=True)

    def paste_objects(self, params: dict[str, Any]) -> dict[str, Any]:
        from presenter_core.presentation.object_paste import paste_objects

        return paste_objects(self, params)

    def restore_revision(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "expected_revision_id", "revision_id"},
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        revision_id = self._uuid_field(params.get("revision_id"), "revision_id")
        target = self._verified_revision(project_id, document_id, revision_id)
        with self._storage.project_database(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._head_row(connection, document_id)
            if current is None:
                raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found.")
            if current["revision_id"] != expected_revision_id:
                raise self._revision_conflict()
            current_target = connection.execute(
                """
                SELECT id, revision_number, sha256, byte_size, local_snapshot_path
                FROM presentation_revisions
                WHERE id = ? AND presentation_id = ?
                """,
                (revision_id, document_id),
            ).fetchone()
            if current_target is None:
                raise CoreDomainError(
                    "PRESENTATION_REVISION_NOT_FOUND", "That presentation revision was not found."
                )
            if (
                current_target["sha256"] != target["sha256"]
                or current_target["byte_size"] != target["byte_size"]
                or current_target["local_snapshot_path"] != target["local_snapshot_path"]
            ):
                raise CoreDomainError(
                    "PRESENTATION_REVISION_STATE_INVALID",
                    "The selected presentation revision changed during restore.",
                    retryable=True,
                )
            if revision_id == expected_revision_id:
                connection.rollback()
                return {
                    "changed": False,
                    "revision_id": revision_id,
                    "revision_number": int(target["revision_number"]),
                    "sha256": target["sha256"],
                    "byte_size": int(target["byte_size"]),
                }
            updated = connection.execute(
                """
                UPDATE presentation_revision_heads
                SET revision_id = ?
                WHERE presentation_id = ? AND revision_id = ?
                """,
                (revision_id, document_id, expected_revision_id),
            )
            if updated.rowcount != 1:
                raise self._revision_conflict()
            connection.commit()
        return {
            "changed": True,
            "revision_id": revision_id,
            "revision_number": int(target["revision_number"]),
            "sha256": target["sha256"],
            "byte_size": int(target["byte_size"]),
        }

    def step_revision(self, params: dict[str, Any]) -> dict[str, Any]:
        """Move one parent/child step without guessing across revision branches."""
        reject_unknown_fields(
            params,
            {"project_id", "document_id", "expected_revision_id", "direction"},
        )
        project_id = self._project_id(params.get("project_id"))
        document_id = self._document_id(params.get("document_id"))
        expected_revision_id = self._uuid_field(
            params.get("expected_revision_id"), "expected_revision_id"
        )
        direction = params.get("direction")
        if not isinstance(direction, str) or direction not in {"undo", "redo"}:
            raise invalid_request("direction must be undo or redo.", field="direction")

        with self._storage.project_database(project_id) as connection:
            current = self._head_row(connection, document_id)
            if current is None:
                raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found.")
            if current["revision_id"] != expected_revision_id:
                raise self._revision_conflict()
            current_revision = connection.execute(
                """
                SELECT id, parent_revision_id
                FROM presentation_revisions
                WHERE id = ? AND presentation_id = ?
                """,
                (expected_revision_id, document_id),
            ).fetchone()
            if current_revision is None:
                raise CoreDomainError(
                    "PRESENTATION_REVISION_STATE_INVALID",
                    "The current presentation revision is unavailable.",
                )

            if direction == "undo":
                target_revision_id = current_revision["parent_revision_id"]
            else:
                children = connection.execute(
                    """
                    SELECT id
                    FROM presentation_revisions
                    WHERE presentation_id = ? AND parent_revision_id = ?
                    ORDER BY revision_number DESC, id
                    LIMIT 2
                    """,
                    (document_id, expected_revision_id),
                ).fetchall()
                if len(children) > 1:
                    raise CoreDomainError(
                        "PRESENTATION_REVISION_BRANCH_AMBIGUOUS",
                        "This revision has multiple redo branches. Choose a revision from history.",
                    )
                target_revision_id = children[0]["id"] if children else None

        # Reuse the full package/hash verification and compare-and-swap head
        # update in restore_revision. A concurrent edit makes that restore fail
        # with the normal stale-revision conflict instead of overwriting it.
        return self.restore_revision(
            {
                "project_id": project_id,
                "document_id": document_id,
                "expected_revision_id": expected_revision_id,
                "revision_id": target_revision_id or expected_revision_id,
            }
        )

    def _commit_revision(
        self,
        project_id: str,
        document_id: str,
        expected_revision_id: str,
        source: sqlite3.Row | dict[str, Any],
        write_package: Callable[[Path, Path], bool | None],
        *,
        on_commit: Callable[[sqlite3.Connection, str], None] | None = None,
    ) -> dict[str, Any]:
        original_path = self._storage.paths.snapshot_path(
            project_id, source["local_snapshot_path"], require_exists=True
        )
        staged_id = uuid.uuid4()
        staged_relative_path = f"sources/.revision-{staged_id}.tmp"
        staged_path = self._storage.paths.snapshot_path(project_id, staged_relative_path)
        final_relative_path = f"sources/revision-{staged_id}.pptx"
        final_path = self._storage.paths.snapshot_path(project_id, final_relative_path)
        created_revision_id = str(staged_id)
        staged_created = False
        final_created = False
        try:
            package_changed = write_package(original_path, staged_path)
            if package_changed is False:
                return {
                    "changed": False,
                    "revision_id": source["revision_id"],
                    "revision_number": int(source["revision_number"]),
                    "sha256": source["sha256"],
                    "byte_size": int(source["byte_size"]),
                }
            staged_created = True
            revised_byte_size = staged_path.stat().st_size
            revised_sha256 = self._sha256_path(staged_path)
            created_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")

            with self._storage.project_database(project_id) as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = self._head_row(connection, document_id)
                if current is None or current["revision_id"] != expected_revision_id:
                    raise self._revision_conflict()
                latest_revision = connection.execute(
                    """
                    SELECT max(revision_number) FROM presentation_revisions
                    WHERE presentation_id = ?
                    """,
                    (document_id,),
                ).fetchone()
                latest_number = (
                    int(latest_revision[0]) if latest_revision and latest_revision[0] else 0
                )
                if latest_number >= MAX_REVISION_NUMBER:
                    raise CoreDomainError(
                        "PRESENTATION_REVISION_LIMIT",
                        "This presentation has reached its revision limit.",
                    )
                revision_number = latest_number + 1
                if final_path.exists() or final_path.is_symlink():
                    raise CoreDomainError(
                        "PRESENTATION_REVISION_PATH_INVALID",
                        "A generated revision path is already in use.",
                    )
                os.replace(staged_path, final_path)
                staged_created = False
                final_created = True
                connection.execute(
                    """
                    INSERT INTO presentation_revisions (
                        id, presentation_id, parent_revision_id, revision_number,
                        revision_kind, local_snapshot_path, sha256, byte_size, created_at
                    ) VALUES (?, ?, ?, ?, 'edited', ?, ?, ?, ?)
                    """,
                    (
                        created_revision_id,
                        document_id,
                        expected_revision_id,
                        revision_number,
                        final_relative_path,
                        revised_sha256,
                        revised_byte_size,
                        created_at,
                    ),
                )
                updated = connection.execute(
                    """
                    UPDATE presentation_revision_heads
                    SET revision_id = ?
                    WHERE presentation_id = ? AND revision_id = ?
                    """,
                    (created_revision_id, document_id, expected_revision_id),
                )
                if updated.rowcount != 1:
                    raise self._revision_conflict()
                if on_commit is not None:
                    on_commit(connection, created_revision_id)
                connection.commit()
            return {
                "changed": True,
                "revision_id": created_revision_id,
                "parent_revision_id": expected_revision_id,
                "revision_number": revision_number,
                "sha256": revised_sha256,
                "byte_size": revised_byte_size,
                "created_at": created_at,
            }
        except CoreDomainError:
            if final_created:
                self._unlink_managed(final_path)
            raise
        except (
            OSError,
            sqlite3.Error,
            ValueError,
            RuntimeError,
            etree.XMLSyntaxError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
        ) as error:
            if final_created:
                self._unlink_managed(final_path)
            raise CoreDomainError(
                "PRESENTATION_EDIT_FAILED",
                "The presentation change could not be saved as a revision.",
                retryable=True,
            ) from error
        finally:
            if staged_created or staged_path.exists():
                self._unlink_managed(staged_path)

    def _verified_revision(
        self, project_id: str, document_id: str, revision_id: str
    ) -> sqlite3.Row:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                """
                SELECT d.kind, d.mime_type, r.id, r.revision_number,
                       r.local_snapshot_path, r.sha256, r.byte_size
                FROM documents d
                JOIN presentation_revisions r ON r.presentation_id = d.id
                WHERE d.id = ? AND d.project_id = ? AND r.id = ?
                """,
                (document_id, project_id, revision_id),
            ).fetchone()
        if row is None:
            raise CoreDomainError(
                "PRESENTATION_REVISION_NOT_FOUND", "That presentation revision was not found."
            )
        if row["kind"] != "presentation" or row["mime_type"] != (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ):
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_INVALID",
                "Revision restore requires an imported PPTX presentation.",
            )
        relative_path = row["local_snapshot_path"]
        digest = row["sha256"]
        byte_size = row["byte_size"]
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
            or isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or not 0 < byte_size <= MAX_SOURCE_BYTES
        ):
            raise CoreDomainError(
                "PRESENTATION_REVISION_STATE_INVALID",
                "The selected presentation revision metadata is invalid.",
            )
        snapshot = self._storage.paths.snapshot_path(project_id, relative_path, require_exists=True)
        try:
            preflight_source(snapshot, "pptx")
            with snapshot.open("rb") as handle:
                if os.fstat(handle.fileno()).st_size != byte_size:
                    raise CoreDomainError(
                        "SOURCE_SNAPSHOT_CHANGED",
                        "The stored presentation no longer matches its revision record.",
                    )
                inspect_pptx_snapshot(
                    handle,
                    document_id=document_id,
                    expected_sha256=digest,
                    byte_size=byte_size,
                )
        except CoreDomainError:
            raise
        except OSError as error:
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_FAILED", "The selected presentation cannot be read."
            ) from error
        return cast(sqlite3.Row, row)

    def _current_revision_source(
        self, project_id: str, document_id: str
    ) -> sqlite3.Row | dict[str, Any]:
        with self._storage.project_database(project_id) as connection:
            row = connection.execute(
                """
                SELECT d.kind, d.mime_type, d.parse_status,
                       r.id AS revision_id, r.revision_number, r.local_snapshot_path,
                       r.sha256, r.byte_size
                FROM documents d
                JOIN presentation_revision_heads h ON h.presentation_id = d.id
                JOIN presentation_revisions r
                    ON r.id = h.revision_id AND r.presentation_id = h.presentation_id
                WHERE d.id = ? AND d.project_id = ?
                """,
                (document_id, project_id),
            ).fetchone()
        if row is None:
            raise CoreDomainError("SOURCE_NOT_FOUND", "Source was not found.")
        if row["kind"] != "presentation" or row["mime_type"] != (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ):
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_INVALID",
                "Text editing requires an imported PPTX presentation.",
            )
        if row["parse_status"] != "ready":
            raise CoreDomainError(
                "PRESENTATION_WORKSPACE_SOURCE_NOT_READY",
                "The presentation is not ready to edit.",
                retryable=True,
            )
        if (
            not isinstance(row["local_snapshot_path"], str)
            or not row["local_snapshot_path"]
            or not isinstance(row["sha256"], str)
            or not _SHA256.fullmatch(row["sha256"])
            or isinstance(row["byte_size"], bool)
            or not isinstance(row["byte_size"], int)
            or not 0 < row["byte_size"] <= MAX_SOURCE_BYTES
        ):
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_CHANGED",
                "The stored presentation no longer matches its revision record.",
            )
        return cast(sqlite3.Row, row)

    def _head_row(self, connection: sqlite3.Connection, document_id: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
                """
                SELECT h.revision_id
                FROM presentation_revision_heads h
                JOIN documents d ON d.id = h.presentation_id
                WHERE h.presentation_id = ?
                """,
                (document_id,),
            ).fetchone(),
        )

    @staticmethod
    def _write_revised_notes_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        expected_text: str,
        replacement_text: str,
    ) -> None:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )

        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        if slide is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        if (
            slide.speaker_notes is None
            or not slide.speaker_notes_editable
            or len(slide.speaker_notes) > MAX_SPEAKER_NOTES_CHARS
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "These speaker notes do not use a supported plain-text format.",
            )
        if slide.speaker_notes != expected_text:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The speaker notes changed. Refresh the preview and try again.",
            )

        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                if len(infos) > 2_048 or len({info.filename for info in infos}) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                members = {info.filename: info for info in infos}
                notes_part = PresentationEditService._notes_part_for_slide(
                    slide.part_name, source_archive, members
                )
                notes_info = members.get(notes_part)
                if notes_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide does not have an editable speaker-notes part.",
                    )
                notes_root = _parse_xml_part(source_archive, notes_info)
                placeholders = notes_root.xpath(
                    "./p:cSld/p:spTree/p:sp[p:nvSpPr/p:nvPr/p:ph[@type='body']]",
                    namespaces=_NS,
                )
                if len(placeholders) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide does not have a supported speaker-notes placeholder.",
                    )
                text_bodies = placeholders[0].xpath("./p:txBody", namespaces=_NS)
                if len(text_bodies) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide does not have a supported speaker-notes text body.",
                    )
                text_body = text_bodies[0]
                paragraphs = text_body.xpath("./a:p", namespaces=_NS)
                if (
                    not paragraphs
                    or not _notes_body_is_plain_editable(paragraphs)
                    or "\n".join(_paragraph_text(item) for item in paragraphs) != expected_text
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The speaker notes changed or use an unsupported format. "
                        "Refresh and try again.",
                    )
                PresentationEditService._replace_notes_paragraphs(
                    text_body,
                    paragraphs,
                    replacement_text,
                )
                rewritten_notes = etree.tostring(
                    notes_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_notes) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "The edited speaker notes are larger than the safe editing limit.",
                    )

                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == notes_part:
                            output_archive.writestr(copied_info, rewritten_notes)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        revised_slide = next(
            (item for item in revised_fidelity.slides if item.slide_id == slide_id), None
        )
        if (
            revised_slide is None
            or revised_slide.speaker_notes != replacement_text
            or not revised_slide.speaker_notes_editable
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The edited speaker notes did not pass validation.",
            )

    @staticmethod
    def _notes_part_for_slide(
        slide_part_name: str,
        source_archive: zipfile.ZipFile,
        members: dict[str, zipfile.ZipInfo],
    ) -> str:
        slide_directory = slide_part_name.rsplit("/", 1)[0]
        slide_filename = slide_part_name.rsplit("/", 1)[-1]
        rels_part = f"{slide_directory}/_rels/{slide_filename}.rels"
        rels_info = members.get(rels_part)
        if rels_info is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This slide does not have an editable speaker-notes relationship.",
            )
        relationships = _relationships(_parse_xml_part(source_archive, rels_info))
        notes = [
            relation for relation in relationships.values() if relation[0] == NOTES_SLIDE_REL_TYPE
        ]
        if len(notes) != 1 or notes[0][2].casefold() != "internal":
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This slide does not have an editable speaker-notes relationship.",
            )
        return _resolve_internal_part(slide_directory, notes[0][1])

    @staticmethod
    def _replace_notes_paragraphs(
        text_body: etree._Element,
        paragraphs: list[etree._Element],
        replacement_text: str,
    ) -> None:
        lines = replacement_text.split("\n")
        if len(lines) > MAX_SPEAKER_NOTES_PARAGRAPHS:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "Speaker notes contain too many paragraphs for this editor.",
            )
        template = paragraphs[0]
        paragraph_properties = template.find(f"{{{DRAWING_NS}}}pPr")
        end_properties = template.find(f"{{{DRAWING_NS}}}endParaRPr")
        template_runs = template.xpath("./a:r", namespaces=_NS)
        run_properties = template_runs[0].find(f"{{{DRAWING_NS}}}rPr") if template_runs else None
        first_paragraph_index = text_body.index(paragraphs[0])
        for paragraph in paragraphs:
            text_body.remove(paragraph)
        xml_space = "{http://www.w3.org/XML/1998/namespace}space"
        for offset, line in enumerate(lines):
            paragraph = etree.Element(f"{{{DRAWING_NS}}}p")
            if paragraph_properties is not None:
                paragraph.append(copy.deepcopy(paragraph_properties))
            run = etree.SubElement(paragraph, f"{{{DRAWING_NS}}}r")
            if run_properties is not None:
                run.append(copy.deepcopy(run_properties))
            text_node = etree.SubElement(run, f"{{{DRAWING_NS}}}t")
            text_node.text = line
            if line and (line[0].isspace() or line[-1].isspace()):
                text_node.set(xml_space, "preserve")
            if end_properties is not None:
                paragraph.append(copy.deepcopy(end_properties))
            text_body.insert(first_paragraph_index + offset, paragraph)

    @staticmethod
    def _write_revised_geometry_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        object_id: str,
        expected_geometry: FidelityGeometry,
        replacement_geometry: FidelityGeometry,
        expected_rotation: FidelityRotation | None = None,
        replacement_rotation: FidelityRotation | None = None,
    ) -> None:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
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
        if not obj.geometry_editable or obj.geometry is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This object does not use a supported slide-level transform.",
            )
        if obj.geometry != expected_geometry:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The object position or size changed. Refresh the preview and try again.",
            )

        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                if len(infos) > 2_048 or len({info.filename for info in infos}) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                slide_info = source_archive.getinfo(slide.part_name)
                slide_root = _parse_xml_part(source_archive, slide_info)
                offset, extent = PresentationEditService._find_transform(
                    slide_root,
                    ooxml_id=obj.ooxml_id,
                    kind=obj.kind,
                )
                current_geometry = FidelityGeometry(
                    x_emu=int(offset.get("x", "")),
                    y_emu=int(offset.get("y", "")),
                    width_emu=int(extent.get("cx", "")),
                    height_emu=int(extent.get("cy", "")),
                )
                if current_geometry != expected_geometry:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The object position or size changed. Refresh the preview and try again.",
                    )
                if obj.kind == "graphicFrame":
                    from presenter_core.presentation.graphic_geometry import resize_table_grid

                    resize_table_grid(
                        PresentationEditService._find_object_node(
                            slide_root, ooxml_id=obj.ooxml_id, kind=obj.kind
                        ),
                        expected_geometry,
                        replacement_geometry,
                    )
                if replacement_rotation is not None:
                    node = PresentationEditService._find_object_node(
                        slide_root, ooxml_id=obj.ooxml_id, kind=obj.kind
                    )
                    if object_rotation(node, obj.kind, None) != expected_rotation:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_STALE_TARGET",
                            "The object rotation changed. Refresh the preview and try again.",
                            retryable=True,
                        )
                    transform = offset.getparent()
                    for name, value in (
                        ("rot", str(replacement_rotation.rotation)),
                        ("flipH", "1" if replacement_rotation.flip_horizontal else None),
                        ("flipV", "1" if replacement_rotation.flip_vertical else None),
                    ):
                        if value is None or value == "0":
                            transform.attrib.pop(name, None)
                        else:
                            transform.set(name, value)
                offset.set("x", str(replacement_geometry.x_emu))
                offset.set("y", str(replacement_geometry.y_emu))
                extent.set("cx", str(replacement_geometry.width_emu))
                extent.set("cy", str(replacement_geometry.height_emu))
                rewritten_slide = etree.tostring(
                    slide_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_slide) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "The edited slide is larger than the safe editing limit.",
                    )

                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == slide.part_name:
                            output_archive.writestr(copied_info, rewritten_slide)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        revised_slide = next(
            (item for item in revised_fidelity.slides if item.slide_id == slide_id), None
        )
        revised_object = (
            next((item for item in revised_slide.objects if item.object_id == object_id), None)
            if revised_slide is not None
            else None
        )
        if (
            revised_object is None
            or not revised_object.geometry_editable
            or revised_object.geometry != replacement_geometry
            or (
                replacement_rotation is not None and revised_object.rotation != replacement_rotation
            )
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The edited object geometry did not pass validation.",
            )

    @staticmethod
    def _write_revised_picture_crop_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        object_id: str,
        expected_geometry: FidelityGeometry,
        expected_crop: FidelityPictureCrop,
        replacement_crop: FidelityPictureCrop,
        expected_adjustment: FidelityPictureAdjustment | None = None,
        replacement_adjustment: FidelityPictureAdjustment | None = None,
    ) -> None:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        source_object = (
            next((item for item in slide.objects if item.object_id == object_id), None)
            if slide is not None
            else None
        )
        if slide is None or source_object is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected picture is unavailable."
            )
        if (
            source_object.kind != "pic"
            or not source_object.geometry_editable
            or source_object.geometry is None
            or source_object.picture_crop is None
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This picture does not use a supported crop structure.",
            )
        if (
            source_object.geometry != expected_geometry
            or source_object.picture_crop != expected_crop
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The picture changed. Refresh the preview and try again.",
                retryable=True,
            )

        original_slide_ids = [item.slide_id for item in fidelity.slides]
        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                members = {info.filename: info for info in infos}
                if len(infos) > 2_048 or len(members) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                slide_info = members.get(slide.part_name)
                if slide_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The selected slide is missing from the presentation package.",
                    )
                slide_root = _parse_xml_part(source_archive, slide_info)
                object_node = PresentationEditService._find_object_node(
                    slide_root,
                    ooxml_id=source_object.ooxml_id,
                    kind="pic",
                )
                fill_nodes = object_node.xpath("./p:blipFill", namespaces=_NS)
                blips = (
                    fill_nodes[0].xpath("./a:blip", namespaces=_NS) if len(fill_nodes) == 1 else []
                )
                if len(blips) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This picture does not have one verifiable embedded image.",
                    )
                relationship_id = blips[0].get(f"{{{REL_NS}}}embed")
                slide_directory = posixpath.dirname(slide.part_name)
                slide_filename = posixpath.basename(slide.part_name)
                relationships_part = posixpath.join(
                    slide_directory, "_rels", f"{slide_filename}.rels"
                )
                relationships_info = members.get(relationships_part)
                if not relationship_id or relationships_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This picture’s embedded image relationship cannot be verified.",
                    )
                relationships_root = _parse_xml_part(source_archive, relationships_info)
                relationships = _relationships(relationships_root)
                relationship = relationships.get(relationship_id)
                if relationship is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This picture’s embedded image relationship cannot be verified.",
                    )
                relationship_type, relationship_target, target_mode = relationship
                if relationship_type != _IMAGE_REL_TYPE or target_mode != "Internal":
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This picture does not use a local image relationship.",
                    )
                image_part = _resolve_internal_part(slide_directory, relationship_target)
                if image_part not in members:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This picture’s embedded image is missing from the package.",
                    )

                current_crop = _picture_crop(object_node, "pic")
                if current_crop != expected_crop:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The picture crop changed. Refresh the preview and try again.",
                        retryable=True,
                    )
                if replacement_adjustment is not None:
                    if _picture_adjustment(object_node, "pic") != expected_adjustment:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_STALE_TARGET",
                            "The picture adjustments changed. Refresh and try again.",
                            retryable=True,
                        )
                    blip = blips[0]
                    for child in list(blip):
                        blip.remove(child)
                    if replacement_adjustment.grayscale:
                        etree.SubElement(blip, f"{{{DRAWING_NS}}}grayscl")
                    if replacement_adjustment.brightness or replacement_adjustment.contrast:
                        luminance = etree.SubElement(blip, f"{{{DRAWING_NS}}}lum")
                        if replacement_adjustment.brightness:
                            luminance.set("bright", str(replacement_adjustment.brightness * 1000))
                        if replacement_adjustment.contrast:
                            luminance.set("contrast", str(replacement_adjustment.contrast * 1000))
                fill = fill_nodes[0]
                source_rectangles = fill.xpath("./a:srcRect", namespaces=_NS)
                if len(source_rectangles) > 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This picture has an unsupported crop structure.",
                    )
                crop_values = {
                    "l": replacement_crop.left,
                    "r": replacement_crop.right,
                    "t": replacement_crop.top,
                    "b": replacement_crop.bottom,
                }
                if not any(crop_values.values()):
                    if source_rectangles:
                        fill.remove(source_rectangles[0])
                else:
                    rectangle = (
                        source_rectangles[0]
                        if source_rectangles
                        else etree.Element(f"{{{DRAWING_NS}}}srcRect")
                    )
                    if not source_rectangles:
                        fill.insert(1, rectangle)
                    for name, value in crop_values.items():
                        if value:
                            rectangle.set(name, str(value))
                        else:
                            rectangle.attrib.pop(name, None)

                rewritten_slide = etree.tostring(
                    slide_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_slide) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The edited slide is larger than the safe editing limit.",
                    )

                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == slide.part_name:
                            output_archive.writestr(copied_info, rewritten_slide)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        if [item.slide_id for item in revised_fidelity.slides] != original_slide_ids:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Cropping the picture changed slide identity or order.",
            )
        expected_slides = tuple(
            replace(
                current_slide,
                objects=tuple(
                    replace(
                        current_object,
                        picture_crop=replacement_crop,
                        picture_adjustment=(
                            replacement_adjustment
                            if replacement_adjustment is not None
                            else current_object.picture_adjustment
                        ),
                    )
                    if current_slide.slide_id == slide_id and current_object.object_id == object_id
                    else current_object
                    for current_object in current_slide.objects
                ),
            )
            for current_slide in fidelity.slides
        )
        if revised_fidelity.slides != expected_slides:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Cropping the picture changed unrelated slide content or metadata.",
            )
        revised_slide = next(
            (item for item in revised_fidelity.slides if item.slide_id == slide_id), None
        )
        revised_object = (
            next((item for item in revised_slide.objects if item.object_id == object_id), None)
            if revised_slide is not None
            else None
        )
        if (
            revised_object is None
            or revised_object.kind != "pic"
            or revised_object.geometry != expected_geometry
            or revised_object.picture_crop != replacement_crop
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The picture crop did not pass package validation.",
            )

    @staticmethod
    def _write_revised_picture_image_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        object_id: str,
        expected_geometry: FidelityGeometry,
        expected_crop: FidelityPictureCrop,
        image_bytes: bytes,
        image_format: str,
    ) -> bool | None:
        """Point one selected picture at a new, private media part."""
        try:
            extension, media_type = {
                "PNG": ("png", "image/png"),
                "JPEG": ("jpg", "image/jpeg"),
            }[image_format]
        except KeyError as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_INVALID_IMAGE",
                "The replacement image format is not supported.",
            ) from error

        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        source_object = (
            next((item for item in slide.objects if item.object_id == object_id), None)
            if slide is not None
            else None
        )
        if slide is None or source_object is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected picture is unavailable."
            )
        if (
            source_object.kind != "pic"
            or not source_object.geometry_editable
            or source_object.geometry is None
            or source_object.picture_crop is None
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This picture does not use a supported embedded-image structure.",
            )
        if (
            source_object.geometry != expected_geometry
            or source_object.picture_crop != expected_crop
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The picture changed. Refresh the preview and try again.",
                retryable=True,
            )

        original_slide_ids = [item.slide_id for item in fidelity.slides]
        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                if len(infos) >= MAX_ARCHIVE_ENTRIES or len(
                    {info.filename.casefold() for info in infos}
                ) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "This presentation has no room for another media file.",
                    )
                if sum(info.file_size for info in infos) + len(image_bytes) > (
                    MAX_ARCHIVE_EXPANDED_BYTES
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The replacement would exceed the expanded presentation size limit.",
                    )
                members = {info.filename: info for info in infos}
                slide_info = members.get(slide.part_name)
                content_types_info = members.get("[Content_Types].xml")
                if slide_info is None or content_types_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "A required presentation package part is missing.",
                    )
                slide_root = _parse_xml_part(source_archive, slide_info)
                object_node = PresentationEditService._find_object_node(
                    slide_root,
                    ooxml_id=source_object.ooxml_id,
                    kind="pic",
                )
                fills = object_node.xpath("./p:blipFill", namespaces=_NS)
                blips = fills[0].xpath("./a:blip", namespaces=_NS) if len(fills) == 1 else []
                if len(blips) != 1 or _picture_crop(object_node, "pic") != expected_crop:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The picture changed. Refresh the preview and try again.",
                        retryable=True,
                    )
                blip = blips[0]
                original_relationship_id = blip.get(f"{{{REL_NS}}}embed")
                slide_directory = posixpath.dirname(slide.part_name)
                slide_filename = posixpath.basename(slide.part_name)
                relationships_part = posixpath.join(
                    slide_directory, "_rels", f"{slide_filename}.rels"
                )
                relationships_info = members.get(relationships_part)
                if not original_relationship_id or relationships_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This picture does not have one verifiable embedded image.",
                    )
                relationships_root = _parse_xml_part(source_archive, relationships_info)
                relationships = _relationships(relationships_root)
                original_relationship = relationships.get(original_relationship_id)
                if original_relationship is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This picture’s embedded image relationship cannot be verified.",
                    )
                original_type, original_target, original_mode = original_relationship
                if original_type != _IMAGE_REL_TYPE or original_mode != "Internal":
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This picture does not use a local image relationship.",
                    )
                original_image_part = _resolve_internal_part(slide_directory, original_target)
                original_image_info = members.get(original_image_part)
                if original_image_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This picture’s embedded image is missing from the package.",
                    )
                if (
                    original_image_info.file_size == len(image_bytes)
                    and source_archive.read(original_image_info) == image_bytes
                ):
                    return False

                relationship_number = 1
                used_relationship_ids = set(relationships)
                while f"rId{relationship_number}" in used_relationship_ids:
                    relationship_number += 1
                replacement_relationship_id = f"rId{relationship_number}"

                media_part = f"ppt/media/presenter-copilot-{uuid.uuid4().hex}.{extension}"
                existing_member_names = {name.casefold() for name in members}
                while media_part.casefold() in existing_member_names:
                    media_part = f"ppt/media/presenter-copilot-{uuid.uuid4().hex}.{extension}"
                replacement_target = posixpath.relpath(media_part, start=slide_directory)

                etree.SubElement(
                    relationships_root,
                    f"{{{_NS['rel']}}}Relationship",
                    Id=replacement_relationship_id,
                    Type=_IMAGE_REL_TYPE,
                    Target=replacement_target,
                )
                blip.set(f"{{{REL_NS}}}embed", replacement_relationship_id)

                content_types_root = _parse_xml_part(source_archive, content_types_info)
                matching_defaults = [
                    item
                    for item in content_types_root.findall(f"{{{_NS['ct']}}}Default")
                    if item.get("Extension", "").casefold() == extension
                ]
                if len(matching_defaults) > 1 or (
                    matching_defaults and matching_defaults[0].get("ContentType") != media_type
                ):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The image file type declaration conflicts with this presentation.",
                    )
                add_content_type_default = not matching_defaults
                if add_content_type_default:
                    default_node = etree.Element(
                        f"{{{_NS['ct']}}}Default",
                        Extension=extension,
                        ContentType=media_type,
                    )
                    first_override = next(
                        (
                            index
                            for index, child in enumerate(content_types_root)
                            if child.tag == f"{{{_NS['ct']}}}Override"
                        ),
                        len(content_types_root),
                    )
                    content_types_root.insert(first_override, default_node)

                rewritten_parts = {
                    slide.part_name: etree.tostring(
                        slide_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    ),
                    relationships_part: etree.tostring(
                        relationships_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    ),
                }
                if add_content_type_default:
                    rewritten_parts["[Content_Types].xml"] = etree.tostring(
                        content_types_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    )
                if any(len(payload) > _MAX_XML_PART_BYTES for payload in rewritten_parts.values()):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The edited presentation metadata is larger than the safe editing limit.",
                    )

                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        rewritten_part = rewritten_parts.get(info.filename)
                        if rewritten_part is not None:
                            output_archive.writestr(copied_info, rewritten_part)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
                    output_archive.writestr(
                        media_part,
                        image_bytes,
                        compress_type=zipfile.ZIP_DEFLATED,
                    )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            KeyError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        if (
            revised_fidelity.slides != fidelity.slides
            or [item.slide_id for item in revised_fidelity.slides] != original_slide_ids
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Replacing the image changed slide identity or unrelated slide content.",
            )

        changed_parts = {slide.part_name, relationships_part}
        if add_content_type_default:
            changed_parts.add("[Content_Types].xml")
        with (
            _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive,
            zipfile.ZipFile(destination_path, "r") as output_archive,
        ):
            output_names = {info.filename for info in output_archive.infolist()}
            expected_names = set(members) | {media_part}
            if output_names != expected_names:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED",
                    "Replacing the image changed the package member list unexpectedly.",
                )
            for member_name in set(members) - changed_parts:
                if source_archive.read(member_name) != output_archive.read(member_name):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_VALIDATION_FAILED",
                        "Replacing the image changed an unrelated presentation part.",
                    )
            revised_slide_root = etree.fromstring(output_archive.read(slide.part_name))
            revised_object = PresentationEditService._find_object_node(
                revised_slide_root,
                ooxml_id=source_object.ooxml_id,
                kind="pic",
            )
            revised_blips = revised_object.xpath("./p:blipFill/a:blip", namespaces=_NS)
            revised_embed = (
                revised_blips[0].get(f"{{{REL_NS}}}embed") if len(revised_blips) == 1 else None
            )
            revised_relationships = _parse_xml_part(
                output_archive, output_archive.getinfo(relationships_part)
            )
            revised_relationship = _relationships(revised_relationships).get(revised_embed or "")
            if revised_relationship is None:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED",
                    "The replacement image relationship did not pass validation.",
                )
            revised_type, revised_target, revised_mode = revised_relationship
            revised_image_part = _resolve_internal_part(slide_directory, revised_target)
            revised_content_types = _parse_xml_part(
                output_archive, output_archive.getinfo("[Content_Types].xml")
            )
            revised_defaults = [
                item
                for item in revised_content_types.findall(f"{{{_NS['ct']}}}Default")
                if item.get("Extension", "").casefold() == extension
            ]
            if (
                revised_embed != replacement_relationship_id
                or revised_type != _IMAGE_REL_TYPE
                or revised_mode != "Internal"
                or revised_image_part != media_part
                or output_archive.read(revised_image_part) != image_bytes
                or len(revised_defaults) != 1
                or revised_defaults[0].get("ContentType") != media_type
                or _picture_crop(revised_object, "pic") != expected_crop
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED",
                    "The replacement image did not pass package validation.",
                )
        return True

    @staticmethod
    def _write_revised_object_duplicate_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        object_id: str,
        expected_geometry: FidelityGeometry,
    ) -> str:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        source_object = (
            next((item for item in slide.objects if item.object_id == object_id), None)
            if slide is not None
            else None
        )
        if slide is None or source_object is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected object is unavailable."
            )
        if (
            source_object.kind not in {"sp", "pic", "graphicFrame"}
            or not source_object.delete_editable
            or not source_object.geometry_editable
            or source_object.geometry is None
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This object cannot be duplicated safely in this version.",
            )
        if source_object.geometry != expected_geometry:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The object changed. Refresh the preview and try again.",
            )
        duplicate_geometry = PresentationEditService._duplicate_geometry(
            expected_geometry,
            slide_width_emu=fidelity.slide_width_emu,
            slide_height_emu=fidelity.slide_height_emu,
        )

        original_slide_ids = [item.slide_id for item in fidelity.slides]
        original_object_ids = {
            item.slide_id: [target.object_id for target in item.objects] for item in fidelity.slides
        }
        source_object_index = next(
            index for index, item in enumerate(slide.objects) if item.object_id == object_id
        )
        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                if len(infos) > 2_048 or len({info.filename for info in infos}) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                slide_info = source_archive.getinfo(slide.part_name)
                slide_root = _parse_xml_part(source_archive, slide_info)
                object_node = PresentationEditService._find_object_node(
                    slide_root,
                    ooxml_id=source_object.ooxml_id,
                    kind=source_object.kind,
                )
                offset, extent = PresentationEditService._find_transform(
                    slide_root,
                    ooxml_id=source_object.ooxml_id,
                    kind=source_object.kind,
                )
                current_geometry = FidelityGeometry(
                    x_emu=int(offset.get("x", "")),
                    y_emu=int(offset.get("y", "")),
                    width_emu=int(extent.get("cx", "")),
                    height_emu=int(extent.get("cy", "")),
                )
                if current_geometry != expected_geometry:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The object changed. Refresh the preview and try again.",
                    )
                shape_tree = object_node.getparent()
                if shape_tree is None or shape_tree.tag != f"{{{PRESENTATION_NS}}}spTree":
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This object is not a direct slide-level object.",
                    )
                nonvisual_selector = {
                    "sp": "./p:nvSpPr/p:cNvPr",
                    "pic": "./p:nvPicPr/p:cNvPr",
                    "graphicFrame": "./p:nvGraphicFramePr/p:cNvPr",
                }[source_object.kind]
                nonvisual = object_node.xpath(nonvisual_selector, namespaces=_NS)
                if len(nonvisual) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The selected object has invalid identity metadata.",
                    )
                duplicate_ooxml_id = _next_ooxml_shape_id(shape_tree)
                duplicate_name = PresentationEditService._duplicate_object_name(
                    slide_root, source_object.name
                )
                duplicate_node = copy.deepcopy(object_node)
                duplicate_nonvisual = duplicate_node.xpath(nonvisual_selector, namespaces=_NS)
                if len(duplicate_nonvisual) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The selected object has invalid identity metadata.",
                    )
                duplicate_nonvisual[0].set("id", duplicate_ooxml_id)
                duplicate_nonvisual[0].set("name", duplicate_name)
                duplicate_offset = duplicate_node.xpath(
                    "./p:xfrm/a:off"
                    if source_object.kind == "graphicFrame"
                    else "./p:spPr/a:xfrm/a:off",
                    namespaces=_NS,
                )
                if len(duplicate_offset) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "The selected object does not have a supported transform.",
                    )
                duplicate_offset[0].set("x", str(duplicate_geometry.x_emu))
                duplicate_offset[0].set("y", str(duplicate_geometry.y_emu))
                from presenter_core.presentation.graphic_duplication import clone_chart_graph

                replacements = (
                    clone_chart_graph(source_archive, slide.part_name, duplicate_node)
                    if source_object.kind == "graphicFrame"
                    else {}
                )
                shape_tree.insert(shape_tree.index(object_node) + 1, duplicate_node)
                rewritten_slide = etree.tostring(
                    slide_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_slide) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The duplicated slide is larger than the safe editing limit.",
                    )

                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == slide.part_name:
                            output_archive.writestr(copied_info, rewritten_slide)
                            continue
                        if info.filename in replacements:
                            output_archive.writestr(copied_info, replacements.pop(info.filename))
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
                    for name, payload in replacements.items():
                        output_archive.writestr(name, payload)
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        if [item.slide_id for item in revised_fidelity.slides] != original_slide_ids:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The object duplication changed slide identity or order.",
            )
        revised_slide = next(
            (item for item in revised_fidelity.slides if item.slide_id == slide_id), None
        )
        revised_source = (
            next((item for item in revised_slide.objects if item.object_id == object_id), None)
            if revised_slide is not None
            else None
        )
        created_object = (
            next(
                (item for item in revised_slide.objects if item.ooxml_id == duplicate_ooxml_id),
                None,
            )
            if revised_slide is not None
            else None
        )
        if (
            revised_slide is None
            or revised_source is None
            or revised_source.geometry != expected_geometry
            or created_object is None
            or created_object.kind != source_object.kind
            or created_object.name != duplicate_name
            or created_object.text != source_object.text
            or not created_object.geometry_editable
            or not created_object.delete_editable
            or created_object.geometry != duplicate_geometry
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The duplicated object did not pass validation.",
            )
        expected_ids = {
            current_slide_id: list(source_ids)
            for current_slide_id, source_ids in original_object_ids.items()
        }
        expected_ids[slide_id].insert(source_object_index + 1, created_object.object_id)
        if any(
            [obj.object_id for obj in actual_slide.objects] != expected_ids[actual_slide.slide_id]
            for actual_slide in revised_fidelity.slides
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The duplicated object changed other slide objects or their order.",
            )
        return created_object.object_id

    @staticmethod
    def _write_revised_object_delete_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        object_id: str,
        expected_geometry: FidelityGeometry,
    ) -> None:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
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
        if not obj.delete_editable or not obj.geometry_editable or obj.geometry is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This object cannot be removed safely in this version.",
            )
        if obj.geometry != expected_geometry:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The object changed. Refresh the preview and try again.",
            )

        original_order = [item.slide_id for item in fidelity.slides]
        removed_ids = {object_id}
        if obj.kind == "grpSp":
            # Inventory is depth-first; discover the complete subtree from verified XML.
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as archive:
                root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
                node = PresentationEditService._find_object_node(
                    root, ooxml_id=obj.ooxml_id, kind=obj.kind
                )
                native_ids = set(node.xpath(".//p:cNvPr/@id", namespaces=_NS))
                removed_ids.update(
                    target.object_id for target in slide.objects if target.ooxml_id in native_ids
                )
        expected_object_ids = {
            item.slide_id: [
                target.object_id
                for target in item.objects
                if not (item.slide_id == slide_id and target.object_id in removed_ids)
            ]
            for item in fidelity.slides
        }
        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                if len(infos) > 2_048 or len({info.filename for info in infos}) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                slide_info = source_archive.getinfo(slide.part_name)
                slide_root = _parse_xml_part(source_archive, slide_info)
                object_node = PresentationEditService._find_object_node(
                    slide_root,
                    ooxml_id=obj.ooxml_id,
                    kind=obj.kind,
                )
                offset, extent = PresentationEditService._find_transform(
                    slide_root,
                    ooxml_id=obj.ooxml_id,
                    kind=obj.kind,
                )
                current_geometry = FidelityGeometry(
                    x_emu=int(offset.get("x", "")),
                    y_emu=int(offset.get("y", "")),
                    width_emu=int(extent.get("cx", "")),
                    height_emu=int(extent.get("cy", "")),
                )
                if current_geometry != expected_geometry:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The object changed. Refresh the preview and try again.",
                    )
                shape_tree = object_node.getparent()
                if shape_tree is None or shape_tree.tag != f"{{{PRESENTATION_NS}}}spTree":
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This object is not a direct slide-level object.",
                    )
                shape_tree.remove(object_node)
                rewritten_slide = etree.tostring(
                    slide_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_slide) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The edited slide is larger than the safe editing limit.",
                    )

                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == slide.part_name:
                            output_archive.writestr(copied_info, rewritten_slide)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        revised_order = [item.slide_id for item in revised_fidelity.slides]
        revised_object_ids = {
            item.slide_id: [target.object_id for target in item.objects]
            for item in revised_fidelity.slides
        }
        if revised_order != original_order or revised_object_ids != expected_object_ids:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The object deletion did not pass validation.",
            )

    @staticmethod
    def _write_revised_slide_delete_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
    ) -> None:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        source_slide_index = next(
            (index for index, item in enumerate(fidelity.slides) if item.slide_id == slide_id),
            -1,
        )
        if source_slide_index < 0:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        if len(fidelity.slides) <= 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "A presentation must keep at least one slide.",
            )
        source_slide = fidelity.slides[source_slide_index]
        original_slide_ids = [item.slide_id for item in fidelity.slides]
        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                members = {info.filename: info for info in infos}
                if len(infos) > 2_048 or len(members) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                slide_rels_part = PresentationEditService._relationship_part_name(
                    source_slide.part_name
                )
                slide_rels_info = members.get(slide_rels_part)
                if source_slide.part_name not in members or slide_rels_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide is missing package relationships required for safe deletion.",
                    )
                slide_rels_root = _parse_xml_part(source_archive, slide_rels_info)
                slide_relationships = _relationships(slide_rels_root)
                notes_relationships: list[tuple[str, str, str]] = []
                layout_count = 0
                for relationship_id, relation in slide_relationships.items():
                    relationship_type, target, target_mode = relation
                    if relationship_type == _SLIDE_LAYOUT_REL_TYPE:
                        layout_count += 1
                        if target_mode.casefold() != "internal":
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "This slide uses an unsupported layout relationship.",
                            )
                        related_part = _resolve_internal_part("ppt/slides", target)
                        if related_part not in members:
                            raise CoreDomainError(
                                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                "The slide layout relationship is invalid.",
                            )
                    elif relationship_type == _IMAGE_REL_TYPE:
                        if (
                            target_mode.casefold() != "internal"
                            or _resolve_internal_part("ppt/slides", target) not in members
                        ):
                            raise CoreDomainError(
                                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                "The slide image relationship is invalid.",
                            )
                    elif relationship_type == _HYPERLINK_REL_TYPE:
                        if target_mode.casefold() == "internal":
                            related_part = _resolve_internal_part("ppt/slides", target)
                            if related_part not in members:
                                raise CoreDomainError(
                                    "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                    "The slide hyperlink relationship is invalid.",
                                )
                        elif target_mode.casefold() != "external":
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "This slide uses an unsupported hyperlink relationship.",
                            )
                    elif relationship_type == NOTES_SLIDE_REL_TYPE:
                        if target_mode.casefold() != "internal":
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "This slide uses an unsupported speaker-notes relationship.",
                            )
                        notes_relationships.append((relationship_id, target, target_mode))
                    else:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED",
                            "This slide contains a package relationship that cannot be "
                            "deleted safely.",
                        )
                if layout_count != 1 or len(notes_relationships) > 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide does not use a supported layout and notes structure.",
                    )

                presentation_info = members.get("ppt/presentation.xml")
                presentation_rels_info = members.get("ppt/_rels/presentation.xml.rels")
                content_types_info = members.get("[Content_Types].xml")
                if (
                    presentation_info is None
                    or presentation_rels_info is None
                    or content_types_info is None
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not contain the package parts required "
                        "for slide deletion.",
                    )
                presentation_root = _parse_xml_part(source_archive, presentation_info)
                presentation_rels_root = _parse_xml_part(source_archive, presentation_rels_info)
                content_types_root = _parse_xml_part(source_archive, content_types_info)
                slide_lists = presentation_root.xpath("./p:sldIdLst", namespaces=_NS)
                if (
                    len(slide_lists) != 1
                    or content_types_root.tag
                    != "{http://schemas.openxmlformats.org/package/2006/content-types}Types"
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not use a supported slide-list structure.",
                    )
                slide_list = slide_lists[0]
                references = list(slide_list)
                if len(references) != len(fidelity.slides) or any(
                    reference.tag != f"{{{PRESENTATION_NS}}}sldId" for reference in references
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not use a supported slide-list structure.",
                    )
                presentation_relationships = _relationships(presentation_rels_root)
                selected_reference = references[source_slide_index]
                selected_ooxml_id = selected_reference.get("id")
                selected_relationship_id = selected_reference.get(f"{{{REL_NS}}}id")
                selected_relationship = presentation_relationships.get(
                    selected_relationship_id or ""
                )
                if (
                    not selected_ooxml_id
                    or selected_relationship is None
                    or selected_relationship[0] != _PRESENTATION_SLIDE_REL_TYPE
                    or selected_relationship[2].casefold() != "internal"
                    or _resolve_internal_part("ppt", selected_relationship[1])
                    != source_slide.part_name
                ):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The selected slide relationship is invalid.",
                    )
                presentation_relation_references = presentation_root.xpath(
                    ".//@r:id", namespaces=_NS
                )
                if presentation_relation_references.count(selected_relationship_id) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide is referenced by another presentation feature and cannot "
                        "be deleted safely.",
                    )
                if any(
                    item.get("id") == selected_ooxml_id
                    and not (
                        item.tag == f"{{{PRESENTATION_NS}}}sldId" and item.getparent() is slide_list
                    )
                    for item in presentation_root.xpath(".//*[@id]")
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide is referenced by section metadata and cannot be deleted "
                        "safely.",
                    )

                notes_part: str | None = None
                notes_rels_part: str | None = None
                if notes_relationships:
                    _, notes_target, _ = notes_relationships[0]
                    notes_part = _resolve_internal_part("ppt/slides", notes_target)
                    notes_rels_part = PresentationEditService._relationship_part_name(notes_part)
                    notes_info = members.get(notes_part)
                    notes_rels_info = members.get(notes_rels_part)
                    if notes_info is None or notes_rels_info is None:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED",
                            "This slide's speaker notes are missing package parts required "
                            "for deletion.",
                        )
                    notes_rels_root = _parse_xml_part(source_archive, notes_rels_info)
                    notes_relationships_map = _relationships(notes_rels_root)
                    note_slide_relations = [
                        relation
                        for relation in notes_relationships_map.values()
                        if relation[0] == _PRESENTATION_SLIDE_REL_TYPE
                        and relation[2].casefold() == "internal"
                        and _resolve_internal_part("ppt/notesSlides", relation[1])
                        == source_slide.part_name
                    ]
                    note_master_relations = [
                        relation
                        for relation in notes_relationships_map.values()
                        if relation[0] == _NOTES_MASTER_REL_TYPE
                        and relation[2].casefold() == "internal"
                        and _resolve_internal_part("ppt/notesSlides", relation[1]) in members
                    ]
                    if (
                        len(notes_relationships_map) != 2
                        or len(note_slide_relations) != 1
                        or len(note_master_relations) != 1
                    ):
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED",
                            "This slide does not use a supported speaker-notes structure.",
                        )

                removed_parts = {source_slide.part_name, slide_rels_part}
                if notes_part and notes_rels_part:
                    removed_parts.update({notes_part, notes_rels_part})
                for relationship_part in (name for name in members if name.endswith(".rels")):
                    relationship_source_part = PresentationEditService._relationship_source_part(
                        relationship_part
                    )
                    if (
                        relationship_source_part in removed_parts
                        or relationship_source_part == "ppt/presentation.xml"
                    ):
                        continue
                    relationships_root = _parse_xml_part(source_archive, members[relationship_part])
                    for relation in _relationships(relationships_root).values():
                        relationship_type, target, target_mode = relation
                        if target_mode.casefold() != "internal" or relationship_type not in {
                            _PRESENTATION_SLIDE_REL_TYPE,
                            _HYPERLINK_REL_TYPE,
                        }:
                            continue
                        related_part = _resolve_internal_part(
                            posixpath.dirname(relationship_source_part), target
                        )
                        if related_part == source_slide.part_name:
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "Another package part links to this slide and prevents safe "
                                "deletion.",
                            )

                slide_list.remove(selected_reference)
                relationship_node = next(
                    (
                        item
                        for item in presentation_rels_root.xpath(
                            "./rel:Relationship", namespaces=_NS
                        )
                        if item.get("Id") == selected_relationship_id
                    ),
                    None,
                )
                if relationship_node is None:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The selected slide relationship is invalid.",
                    )
                presentation_rels_root.remove(relationship_node)

                content_type_overrides = content_types_root.xpath("./ct:Override", namespaces=_NS)
                content_type_map = {
                    item.get("PartName"): item.get("ContentType") for item in content_type_overrides
                }
                if (
                    len(content_type_map) != len(content_type_overrides)
                    or content_type_map.get(f"/{source_slide.part_name}") != _SLIDE_CONTENT_TYPE
                    or (
                        notes_part is not None
                        and content_type_map.get(f"/{notes_part}") != _NOTES_SLIDE_CONTENT_TYPE
                    )
                ):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The presentation content-type declarations are invalid.",
                    )
                content_parts_to_remove = {source_slide.part_name}
                if notes_part is not None:
                    content_parts_to_remove.add(notes_part)
                for part_name in content_parts_to_remove:
                    content_type_name = f"/{part_name}"
                    matches = [
                        item
                        for item in content_type_overrides
                        if item.get("PartName") == content_type_name
                    ]
                    if len(matches) != 1:
                        raise CoreDomainError(
                            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                            "The slide content-type declarations are invalid.",
                        )
                    content_types_root.remove(matches[0])

                replacements = {
                    "ppt/presentation.xml": etree.tostring(
                        presentation_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    ),
                    "ppt/_rels/presentation.xml.rels": etree.tostring(
                        presentation_rels_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    ),
                    "[Content_Types].xml": etree.tostring(
                        content_types_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    ),
                }
                if any(len(payload) > _MAX_XML_PART_BYTES for payload in replacements.values()):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The presentation metadata is larger than the safe editing limit.",
                    )
                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        if info.filename in removed_parts:
                            continue
                        copied_info = copy.copy(info)
                        replacement = replacements.get(info.filename)
                        if replacement is not None:
                            output_archive.writestr(copied_info, replacement)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        expected_slide_ids = original_slide_ids.copy()
        expected_slide_ids.pop(source_slide_index)
        if [item.slide_id for item in revised_fidelity.slides] != expected_slide_ids:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The slide deletion changed the remaining slide order or identity.",
            )
        for original in fidelity.slides:
            if original.slide_id == slide_id:
                continue
            revised = next(
                (item for item in revised_fidelity.slides if item.slide_id == original.slide_id),
                None,
            )
            if (
                revised is None
                or revised.part_name != original.part_name
                or revised.objects != original.objects
                or revised.speaker_notes != original.speaker_notes
                or revised.speaker_notes_editable != original.speaker_notes_editable
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED",
                    "Deleting the slide changed existing slide content or relationships.",
                )

    @staticmethod
    def _write_revised_slide_duplicate_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
    ) -> str:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        source_slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        if source_slide is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        if (
            len(fidelity.slides) >= SLIDE_LIMIT
            or fidelity.object_count + len(source_slide.objects) > OBJECT_LIMIT
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "Duplicating this slide would exceed the workspace limit.",
            )

        original_slide_ids = [item.slide_id for item in fidelity.slides]
        source_slide_index = next(
            index for index, item in enumerate(fidelity.slides) if item.slide_id == slide_id
        )
        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                members = {info.filename: info for info in infos}
                if len(infos) > 2_048 or len(members) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                source_slide_info = members.get(source_slide.part_name)
                source_slide_rels_part = PresentationEditService._relationship_part_name(
                    source_slide.part_name
                )
                source_slide_rels_info = members.get(source_slide_rels_part)
                if source_slide_info is None or source_slide_rels_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide is missing package relationships required for safe "
                        "duplication.",
                    )
                source_slide_xml = source_archive.read(source_slide_info)
                slide_root = _parse_xml_part(source_archive, source_slide_info)
                slide_rels_root = _parse_xml_part(source_archive, source_slide_rels_info)
                slide_relationships = _relationships(slide_rels_root)
                referenced_relationship_ids = set(
                    slide_root.xpath(".//@r:id | .//@r:embed | .//@r:link", namespaces=_NS)
                )
                if not referenced_relationship_ids.issubset(slide_relationships):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The slide contains a relationship reference that cannot be resolved.",
                    )

                layout_relationships: list[tuple[str, str, str]] = []
                notes_relationships: list[tuple[str, str, str, str]] = []
                for relationship_id, relation in slide_relationships.items():
                    relationship_type, target, target_mode = relation
                    if relationship_type == _SLIDE_LAYOUT_REL_TYPE:
                        layout_relationships.append(relation)
                        if target_mode.casefold() != "internal":
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "This slide uses an unsupported layout relationship.",
                            )
                        related_part = _resolve_internal_part("ppt/slides", target)
                        if related_part not in members:
                            raise CoreDomainError(
                                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                "The slide layout relationship is invalid.",
                            )
                    elif relationship_type == _IMAGE_REL_TYPE:
                        if target_mode.casefold() != "internal":
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "This slide uses an unsupported external image relationship.",
                            )
                        related_part = _resolve_internal_part("ppt/slides", target)
                        if related_part not in members:
                            raise CoreDomainError(
                                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                "The slide image relationship is invalid.",
                            )
                    elif relationship_type == f"{REL_NS}/chart":
                        if (
                            target_mode.casefold() != "internal"
                            or _resolve_internal_part("ppt/slides", target) not in members
                        ):
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "This slide contains an invalid or external chart relationship.",
                            )
                    elif relationship_type == _HYPERLINK_REL_TYPE:
                        if target_mode.casefold() == "internal":
                            related_part = _resolve_internal_part("ppt/slides", target)
                            if related_part not in members:
                                raise CoreDomainError(
                                    "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                    "The slide hyperlink relationship is invalid.",
                                )
                        elif target_mode.casefold() != "external":
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "This slide uses an unsupported hyperlink relationship.",
                            )
                    elif relationship_type == NOTES_SLIDE_REL_TYPE:
                        notes_relationships.append((relationship_id, *relation))
                        if target_mode.casefold() != "internal":
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "This slide uses an unsupported speaker-notes relationship.",
                            )
                    else:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED",
                            "This slide contains a package relationship that cannot be "
                            "duplicated safely.",
                        )
                if len(layout_relationships) != 1 or len(notes_relationships) > 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide does not use a supported layout and notes structure.",
                    )

                presentation_info = members.get("ppt/presentation.xml")
                presentation_rels_info = members.get("ppt/_rels/presentation.xml.rels")
                content_types_info = members.get("[Content_Types].xml")
                if (
                    presentation_info is None
                    or presentation_rels_info is None
                    or content_types_info is None
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not contain the package parts required "
                        "for slide duplication.",
                    )
                presentation_root = _parse_xml_part(source_archive, presentation_info)
                presentation_rels_root = _parse_xml_part(source_archive, presentation_rels_info)
                content_types_root = _parse_xml_part(source_archive, content_types_info)
                slide_lists = presentation_root.xpath("./p:sldIdLst", namespaces=_NS)
                if (
                    len(slide_lists) != 1
                    or presentation_rels_root.tag
                    != "{http://schemas.openxmlformats.org/package/2006/relationships}Relationships"
                    or content_types_root.tag
                    != "{http://schemas.openxmlformats.org/package/2006/content-types}Types"
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not use a supported slide-list structure.",
                    )
                slide_list = slide_lists[0]
                references = list(slide_list)
                if len(references) != len(fidelity.slides) or any(
                    reference.tag != f"{{{PRESENTATION_NS}}}sldId" for reference in references
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not use a supported slide-list structure.",
                    )
                presentation_relationships = _relationships(presentation_rels_root)
                source_reference_index = -1
                slide_id_values: list[int] = []
                for index, reference in enumerate(references):
                    ooxml_id = reference.get("id")
                    relation_id = reference.get(f"{{{REL_NS}}}id")
                    presentation_relation = presentation_relationships.get(relation_id or "")
                    try:
                        slide_id_values.append(int(ooxml_id or ""))
                    except ValueError as error:
                        raise CoreDomainError(
                            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                            "The presentation contains an invalid slide identifier.",
                        ) from error
                    if (
                        presentation_relation is None
                        or presentation_relation[0] != _PRESENTATION_SLIDE_REL_TYPE
                        or presentation_relation[2].casefold() != "internal"
                    ):
                        raise CoreDomainError(
                            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                            "The presentation slide relationship is invalid.",
                        )
                    resolved_part = _resolve_internal_part("ppt", presentation_relation[1])
                    if resolved_part == source_slide.part_name:
                        if source_reference_index >= 0:
                            raise CoreDomainError(
                                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                "The selected slide appears more than once in the slide list.",
                            )
                        source_reference_index = index
                if (
                    source_reference_index < 0
                    or source_reference_index != source_slide_index
                    or len(slide_id_values) != len(set(slide_id_values))
                    or any(value <= 0 or value > _MAX_OOXML_SLIDE_ID for value in slide_id_values)
                    or not slide_id_values
                    or max(slide_id_values) >= _MAX_OOXML_SLIDE_ID
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "This presentation cannot allocate another safe slide identifier.",
                    )

                slide_part = PresentationEditService._unique_package_part(
                    members, "ppt/slides", "slide"
                )
                slide_rels_part = PresentationEditService._relationship_part_name(slide_part)
                new_ooxml_slide_id = str(max(slide_id_values) + 1)
                used_presentation_relation_ids = set(presentation_relationships)
                new_presentation_relation_id = PresentationEditService._new_relationship_id(
                    used_presentation_relation_ids, "SlideDuplicate"
                )
                new_slide_reference = copy.deepcopy(references[source_reference_index])
                new_slide_reference.set("id", new_ooxml_slide_id)
                new_slide_reference.set(f"{{{REL_NS}}}id", new_presentation_relation_id)
                slide_list.insert(source_reference_index + 1, new_slide_reference)
                presentation_relationship = etree.SubElement(
                    presentation_rels_root,
                    "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
                )
                presentation_relationship.set("Id", new_presentation_relation_id)
                presentation_relationship.set("Type", _PRESENTATION_SLIDE_REL_TYPE)
                presentation_relationship.set(
                    "Target", PresentationEditService._relative_part_target("ppt", slide_part)
                )

                note_parts_to_add: list[tuple[str, bytes]] = []
                slide_rels_to_write = copy.deepcopy(slide_rels_root)
                if notes_relationships:
                    notes_relation_id, _, notes_target, _ = notes_relationships[0]
                    source_notes_part = _resolve_internal_part("ppt/slides", notes_target)
                    source_notes_rels_part = PresentationEditService._relationship_part_name(
                        source_notes_part
                    )
                    source_notes_info = members.get(source_notes_part)
                    source_notes_rels_info = members.get(source_notes_rels_part)
                    if source_notes_info is None or source_notes_rels_info is None:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED",
                            "This slide's speaker notes are missing package parts required "
                            "for duplication.",
                        )
                    notes_root = _parse_xml_part(source_archive, source_notes_info)
                    notes_rels_root = _parse_xml_part(source_archive, source_notes_rels_info)
                    notes_relationships_map = _relationships(notes_rels_root)
                    notes_slide_relationships: list[tuple[etree._Element, str]] = []
                    notes_master_relationships: list[str] = []
                    notes_refs = set(
                        notes_root.xpath(".//@r:id | .//@r:embed | .//@r:link", namespaces=_NS)
                    )
                    if not notes_refs.issubset(notes_relationships_map):
                        raise CoreDomainError(
                            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                            "The speaker notes contain a relationship reference that cannot "
                            "be resolved.",
                        )
                    for relationship_node in notes_rels_root.xpath(
                        "./rel:Relationship", namespaces=_NS
                    ):
                        relation_id = relationship_node.get("Id")
                        relationship_type = relationship_node.get("Type")
                        target = relationship_node.get("Target")
                        target_mode = relationship_node.get("TargetMode", "Internal")
                        if not relation_id or not relationship_type or not target:
                            raise CoreDomainError(
                                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                "The speaker-notes relationships are invalid.",
                            )
                        if relationship_type == _PRESENTATION_SLIDE_REL_TYPE:
                            if target_mode.casefold() != "internal":
                                raise CoreDomainError(
                                    "PRESENTATION_EDIT_UNSUPPORTED",
                                    "This speaker-notes part uses an unsupported slide "
                                    "relationship.",
                                )
                            resolved = _resolve_internal_part("ppt/notesSlides", target)
                            if resolved != source_slide.part_name:
                                raise CoreDomainError(
                                    "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                    "The speaker notes do not refer to the selected slide.",
                                )
                            notes_slide_relationships.append((relationship_node, relation_id))
                        elif relationship_type == _NOTES_MASTER_REL_TYPE:
                            if target_mode.casefold() != "internal":
                                raise CoreDomainError(
                                    "PRESENTATION_EDIT_UNSUPPORTED",
                                    "This speaker-notes part uses an unsupported notes-master "
                                    "relationship.",
                                )
                            resolved = _resolve_internal_part("ppt/notesSlides", target)
                            if resolved not in members:
                                raise CoreDomainError(
                                    "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                    "The notes-master relationship is invalid.",
                                )
                            notes_master_relationships.append(relation_id)
                        else:
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "This speaker-notes part contains a relationship that cannot "
                                "be duplicated safely.",
                            )
                    if len(notes_slide_relationships) != 1 or len(notes_master_relationships) != 1:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED",
                            "This slide does not use a supported speaker-notes structure.",
                        )
                    notes_part = PresentationEditService._unique_package_part(
                        members, "ppt/notesSlides", "notesSlide"
                    )
                    notes_rels_part = PresentationEditService._relationship_part_name(notes_part)
                    notes_slide_relationships[0][0].set(
                        "Target",
                        PresentationEditService._relative_part_target(
                            "ppt/notesSlides", slide_part
                        ),
                    )
                    duplicate_notes_xml = source_archive.read(source_notes_info)
                    duplicate_notes_rels_xml = etree.tostring(
                        notes_rels_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    )
                    slide_note_relation = next(
                        (
                            relation
                            for relation in slide_rels_to_write.xpath(
                                "./rel:Relationship", namespaces=_NS
                            )
                            if relation.get("Id") == notes_relation_id
                        ),
                        None,
                    )
                    if slide_note_relation is None:
                        raise CoreDomainError(
                            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                            "The slide's speaker-notes relationship is invalid.",
                        )
                    slide_note_relation.set(
                        "Target",
                        PresentationEditService._relative_part_target("ppt/slides", notes_part),
                    )
                    note_parts_to_add.extend(
                        [
                            (notes_part, duplicate_notes_xml),
                            (notes_rels_part, duplicate_notes_rels_xml),
                        ]
                    )

                content_type_overrides = {
                    item.get("PartName"): item.get("ContentType")
                    for item in content_types_root.xpath("./ct:Override", namespaces=_NS)
                }
                if (
                    len(content_type_overrides)
                    != len(content_types_root.xpath("./ct:Override", namespaces=_NS))
                    or content_type_overrides.get(f"/{source_slide.part_name}")
                    != _SLIDE_CONTENT_TYPE
                    or f"/{slide_part}" in content_type_overrides
                ):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The slide content-type declarations are invalid.",
                    )
                slide_override = etree.SubElement(
                    content_types_root,
                    "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
                )
                slide_override.set("PartName", f"/{slide_part}")
                slide_override.set("ContentType", _SLIDE_CONTENT_TYPE)
                if note_parts_to_add:
                    original_notes_part = _resolve_internal_part(
                        "ppt/slides", notes_relationships[0][2]
                    )
                    if (
                        content_type_overrides.get(f"/{original_notes_part}")
                        != _NOTES_SLIDE_CONTENT_TYPE
                        or f"/{note_parts_to_add[0][0]}" in content_type_overrides
                    ):
                        raise CoreDomainError(
                            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                            "The speaker-notes content-type declarations are invalid.",
                        )
                    notes_override = etree.SubElement(
                        content_types_root,
                        "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
                    )
                    notes_override.set("PartName", f"/{note_parts_to_add[0][0]}")
                    notes_override.set("ContentType", _NOTES_SLIDE_CONTENT_TYPE)

                from presenter_core.presentation.graphic_duplication import clone_chart_graph

                chart_parts_to_add: dict[str, bytes] = {}
                cloned_chart_parts: dict[str, str] = {}
                processed_chart_rids: set[str] = set()
                for frame in slide_root.xpath(".//p:graphicFrame", namespaces=_NS):
                    chart_refs = frame.xpath(
                        "./a:graphic/a:graphicData/c:chart",
                        namespaces={
                            **_NS,
                            "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
                        },
                    )
                    if not chart_refs:
                        continue
                    if len(chart_refs) != 1:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED",
                            "This slide contains an unsupported chart reference structure.",
                        )
                    rid = chart_refs[0].get(f"{{{REL_NS}}}id", "")
                    if rid in processed_chart_rids:
                        continue
                    copied_parts = clone_chart_graph(
                        source_archive,
                        source_slide.part_name,
                        frame,
                        slide_relationships=slide_rels_to_write,
                        content_types_root=content_types_root,
                        preserve_relationship_id=True,
                        cloned_parts=cloned_chart_parts,
                    )
                    processed_chart_rids.add(rid)
                    copied_parts.pop("[Content_Types].xml", None)
                    copied_parts.pop(source_slide_rels_part, None)
                    chart_parts_to_add.update(copied_parts)

                referenced_chart_rids = {
                    rid
                    for rid, relation in slide_relationships.items()
                    if relation[0] == f"{REL_NS}/chart" and rid in referenced_relationship_ids
                }
                if referenced_chart_rids != processed_chart_rids:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide contains chart references outside supported native frames.",
                    )

                rewritten_presentation = etree.tostring(
                    presentation_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                rewritten_presentation_rels = etree.tostring(
                    presentation_rels_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                rewritten_content_types = etree.tostring(
                    content_types_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                rewritten_slide_rels = etree.tostring(
                    slide_rels_to_write,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if any(
                    len(payload) > _MAX_XML_PART_BYTES
                    for payload in (
                        rewritten_presentation,
                        rewritten_presentation_rels,
                        rewritten_content_types,
                        rewritten_slide_rels,
                        *(payload for _, payload in note_parts_to_add),
                    )
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The duplicated slide package metadata exceeds the safe editing limit.",
                    )

                replacements = {
                    "ppt/presentation.xml": rewritten_presentation,
                    "ppt/_rels/presentation.xml.rels": rewritten_presentation_rels,
                    "[Content_Types].xml": rewritten_content_types,
                }
                additions = [
                    (slide_part, source_slide_xml),
                    (slide_rels_part, rewritten_slide_rels),
                ]
                additions.extend(note_parts_to_add)
                additions.extend(chart_parts_to_add.items())
                if any(part_name in members for part_name, _ in additions):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The duplicated slide would overwrite an existing package part.",
                    )
                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        replacement = replacements.get(info.filename)
                        if replacement is not None:
                            output_archive.writestr(copied_info, replacement)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
                    for part_name, payload in additions:
                        output_archive.writestr(part_name, payload)
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        expected_slide_order = original_slide_ids.copy()
        expected_slide_order.insert(source_slide_index + 1, "")
        revised_ids = [item.slide_id for item in revised_fidelity.slides]
        if len(revised_ids) != len(expected_slide_order):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The duplicated slide changed the presentation slide count unexpectedly.",
            )
        duplicate_slide = revised_fidelity.slides[source_slide_index + 1]
        expected_slide_order[source_slide_index + 1] = duplicate_slide.slide_id
        if (
            revised_ids != expected_slide_order
            or duplicate_slide.slide_id in original_slide_ids
            or duplicate_slide.part_name != slide_part
            or len(duplicate_slide.objects) != len(source_slide.objects)
            or duplicate_slide.speaker_notes != source_slide.speaker_notes
            or duplicate_slide.speaker_notes_editable != source_slide.speaker_notes_editable
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The duplicated slide did not preserve slide order and speaker notes.",
            )
        if any(
            (
                copied.kind != original.kind
                or copied.name != original.name
                or copied.text != original.text
                or copied.geometry != original.geometry
                or copied.geometry_editable != original.geometry_editable
                or copied.delete_editable != original.delete_editable
                or copied.object_id == original.object_id
            )
            for original, copied in zip(source_slide.objects, duplicate_slide.objects, strict=True)
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The duplicated slide did not preserve its editable object inventory.",
            )
        if any(
            original.objects != revised.objects
            or original.part_name != revised.part_name
            or original.speaker_notes != revised.speaker_notes
            or original.speaker_notes_editable != revised.speaker_notes_editable
            for original, revised in zip(
                fidelity.slides,
                [item for item in revised_fidelity.slides if item.slide_id in original_slide_ids],
                strict=True,
            )
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Duplicating the slide changed existing slide content or relationships.",
            )
        return duplicate_slide.slide_id

    @staticmethod
    def _slide_layout_part(
        source_archive: zipfile.ZipFile,
        members: dict[str, zipfile.ZipInfo],
        slide_part_name: str,
    ) -> tuple[str, str]:
        relationships_part = PresentationEditService._relationship_part_name(slide_part_name)
        relationships_info = members.get(relationships_part)
        if relationships_info is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "The selected slide has no supported layout relationship part.",
            )
        relationships_root = _parse_xml_part(source_archive, relationships_info)
        relationships = _relationships(relationships_root)
        layout_relationships = [
            (relationship_id, relationship)
            for relationship_id, relationship in relationships.items()
            if relationship[0] == _SLIDE_LAYOUT_REL_TYPE
        ]
        if len(layout_relationships) != 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "The selected slide does not use exactly one supported layout.",
            )
        relationship_id, (relationship_type, target, target_mode) = layout_relationships[0]
        if relationship_type != _SLIDE_LAYOUT_REL_TYPE or target_mode.casefold() != "internal":
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "The selected slide uses an unsupported layout relationship.",
            )
        layout_part = _resolve_internal_part(posixpath.dirname(slide_part_name), target)
        if layout_part not in members:
            raise CoreDomainError(
                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                "The selected slide layout relationship points to a missing package part.",
            )
        return relationship_id, layout_part

    @staticmethod
    def _write_revised_slide_layout_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        expected_slide_ids: list[str],
        layout_source_slide_id: str | None,
        layout_id: str | None = None,
        placeholder_mapping: list[dict[str, Any]] | None = None,
    ) -> bool | None:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        source_slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        layout_source_slide = next(
            (item for item in fidelity.slides if item.slide_id == layout_source_slide_id), None
        )
        if (
            source_slide is None
            or [item.slide_id for item in fidelity.slides] != expected_slide_ids
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The selected slide changed. Refresh the preview and try again.",
            )
        if layout_source_slide is None and layout_id is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_LAYOUT_NOT_FOUND",
                "Choose a layout used by a slide in the current presentation revision.",
            )

        expected_remapped: dict[str, tuple[bytes, Any]] = {}
        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                members = {info.filename: info for info in infos}
                if (
                    len(infos) > MAX_ARCHIVE_ENTRIES
                    or len(members) != len(infos)
                    or len({name.casefold() for name in members}) != len(members)
                ):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                target_slide_info = members.get(source_slide.part_name)
                layout_source_info = (
                    members.get(layout_source_slide.part_name)
                    if layout_source_slide is not None
                    else None
                )
                if target_slide_info is None or (
                    layout_source_slide is not None and layout_source_info is None
                ):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The selected slide package part is missing.",
                    )
                target_relationship_id, current_layout_part = (
                    PresentationEditService._slide_layout_part(
                        source_archive, members, source_slide.part_name
                    )
                )
                if layout_id is not None:
                    from presenter_core.presentation.layouts import catalog

                    selected = next(
                        (
                            v
                            for v in catalog(source_archive, document_id)
                            if v["layout_id"] == layout_id
                        ),
                        None,
                    )
                    if selected is None:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_LAYOUT_NOT_FOUND",
                            "Choose a native layout from this revision's catalog.",
                        )
                    replacement_layout_part = str(selected["_part"])
                else:
                    assert layout_source_slide is not None
                    _, replacement_layout_part = PresentationEditService._slide_layout_part(
                        source_archive, members, layout_source_slide.part_name
                    )
                rewritten_slide = None
                if placeholder_mapping is not None:
                    from presenter_core.presentation.placeholder_remapping import remap

                    assert selected is not None
                    root = _parse_xml_part(source_archive, target_slide_info)
                    original_shapes = {
                        obj.object_id: etree.tostring(
                            PresentationEditService._find_shape(root, obj.ooxml_id),
                            method="c14n",
                            exclusive=True,
                        )
                        for obj in source_slide.objects
                        if obj.kind == "sp"
                    }
                    expected_remapped = remap(
                        root,
                        source_slide,
                        selected,
                        placeholder_mapping,
                        fidelity.slide_width_emu,
                        fidelity.slide_height_emu,
                    )
                    if any(
                        original_shapes.get(identity) != expected[0]
                        for identity, expected in expected_remapped.items()
                    ):
                        rewritten_slide = etree.tostring(
                            root, encoding="UTF-8", xml_declaration=True, standalone=True
                        )
                        if len(rewritten_slide) > _MAX_XML_PART_BYTES:
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                                "The remapped slide is too large.",
                            )
                if current_layout_part == replacement_layout_part and rewritten_slide is None:
                    return False

                relationships_part = PresentationEditService._relationship_part_name(
                    source_slide.part_name
                )
                relationships_info = members[relationships_part]
                relationships_root = _parse_xml_part(source_archive, relationships_info)
                relationship_nodes = relationships_root.findall(f"{{{_NS['rel']}}}Relationship")
                target_relationship = next(
                    (
                        relationship
                        for relationship in relationship_nodes
                        if relationship.get("Id") == target_relationship_id
                    ),
                    None,
                )
                if target_relationship is None:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The selected slide layout relationship is inconsistent.",
                    )
                target_relationship.set(
                    "Target",
                    PresentationEditService._relative_part_target(
                        posixpath.dirname(source_slide.part_name), replacement_layout_part
                    ),
                )
                rewritten_relationships = etree.tostring(
                    relationships_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_relationships) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The slide relationships are larger than the safe editing limit.",
                    )

                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == source_slide.part_name and rewritten_slide is not None:
                            output_archive.writestr(copied_info, rewritten_slide)
                            continue
                        if (
                            info.filename == relationships_part
                            and current_layout_part != replacement_layout_part
                        ):
                            output_archive.writestr(copied_info, rewritten_relationships)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        if [item.slide_id for item in revised_fidelity.slides] != expected_slide_ids or any(
            original.slide_id != revised.slide_id
            or len(original.objects) != len(revised.objects)
            or any(
                old != new
                if old.object_id not in expected_remapped
                else (
                    old.object_id,
                    old.ooxml_id,
                    old.name,
                    old.kind,
                    old.text,
                    old.text_style,
                    old.shape_style,
                )
                != (
                    new.object_id,
                    new.ooxml_id,
                    new.name,
                    new.kind,
                    new.text,
                    new.text_style,
                    new.shape_style,
                )
                or new.geometry != expected_remapped[old.object_id][1]
                for old, new in zip(original.objects, revised.objects, strict=True)
            )
            or original.part_name != revised.part_name
            or original.speaker_notes != revised.speaker_notes
            or original.speaker_notes_editable != revised.speaker_notes_editable
            for original, revised in zip(fidelity.slides, revised_fidelity.slides, strict=True)
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Applying a slide layout changed slide content or presentation order.",
            )
        try:
            with zipfile.ZipFile(destination_path, "r") as revised_archive:
                revised_members = {info.filename: info for info in revised_archive.infolist()}
                _, applied_layout_part = PresentationEditService._slide_layout_part(
                    revised_archive, revised_members, source_slide.part_name
                )
                if applied_layout_part != replacement_layout_part:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_VALIDATION_FAILED",
                        "The selected slide does not use the requested layout.",
                    )
                if expected_remapped:
                    root = _parse_xml_part(revised_archive, revised_members[source_slide.part_name])
                    for obj in source_slide.objects:
                        if (
                            obj.object_id in expected_remapped
                            and etree.tostring(
                                PresentationEditService._find_shape(root, obj.ooxml_id),
                                method="c14n",
                                exclusive=True,
                            )
                            != expected_remapped[obj.object_id][0]
                        ):
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_VALIDATION_FAILED",
                                "The remapped placeholder content changed.",
                            )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The applied slide layout could not be verified.",
            ) from error
        return None

    @staticmethod
    def _write_revised_blank_slide_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        layout_source_slide_id: str,
        layout_id: str | None = None,
        placeholder_text: dict[str, str] | None = None,
    ) -> str:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        source_slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        if source_slide is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        layout_source_slide = next(
            (item for item in fidelity.slides if item.slide_id == layout_source_slide_id), None
        )
        if layout_id is None and layout_source_slide is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_LAYOUT_NOT_FOUND",
                "The selected slide layout is unavailable in the current revision.",
            )
        if len(fidelity.slides) >= SLIDE_LIMIT:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "This presentation cannot contain another slide safely.",
            )

        original_slide_ids = [item.slide_id for item in fidelity.slides]
        source_slide_index = next(
            index for index, item in enumerate(fidelity.slides) if item.slide_id == slide_id
        )
        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                members = {info.filename: info for info in infos}
                if len(infos) + 2 > MAX_ARCHIVE_ENTRIES or len(members) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "This presentation cannot safely contain another slide.",
                    )
                source_slide_info = members.get(source_slide.part_name)
                slots: list[dict[str, Any]] = []
                if source_slide_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED", "The slide part is missing."
                    )
                if layout_id:
                    from presenter_core.presentation.layouts import catalog

                    selected = next(
                        (
                            v
                            for v in catalog(source_archive, document_id)
                            if v["layout_id"] == layout_id
                        ),
                        None,
                    )
                    if selected is None:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_LAYOUT_NOT_FOUND",
                            "The native layout is unavailable.",
                        )
                    layout_part = selected["_part"]
                    if placeholder_text is not None:
                        if not selected["creation_supported"]:
                            raise CoreDomainError(
                                "PRESENTATION_EDIT_UNSUPPORTED",
                                "This layout has unsupported text placeholders.",
                            )
                        slots = selected["_slots"]
                        if set(placeholder_text) - {slot["placeholder_id"] for slot in slots}:
                            raise invalid_request(
                                "A placeholder does not belong to this native layout."
                            )
                else:
                    assert layout_source_slide is not None
                    _, layout_part = PresentationEditService._slide_layout_part(
                        source_archive, members, layout_source_slide.part_name
                    )

                presentation_info = members.get("ppt/presentation.xml")
                presentation_rels_info = members.get("ppt/_rels/presentation.xml.rels")
                content_types_info = members.get("[Content_Types].xml")
                if (
                    presentation_info is None
                    or presentation_rels_info is None
                    or content_types_info is None
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not contain the package parts required for "
                        "slide creation.",
                    )
                presentation_root = _parse_xml_part(source_archive, presentation_info)
                presentation_rels_root = _parse_xml_part(source_archive, presentation_rels_info)
                content_types_root = _parse_xml_part(source_archive, content_types_info)
                slide_lists = presentation_root.xpath("./p:sldIdLst", namespaces=_NS)
                if (
                    len(slide_lists) != 1
                    or presentation_rels_root.tag
                    != "{http://schemas.openxmlformats.org/package/2006/relationships}Relationships"
                    or content_types_root.tag
                    != "{http://schemas.openxmlformats.org/package/2006/content-types}Types"
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not use a supported slide-list structure.",
                    )
                slide_list = slide_lists[0]
                references = list(slide_list)
                if len(references) != len(fidelity.slides) or any(
                    reference.tag != f"{{{PRESENTATION_NS}}}sldId" for reference in references
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not use a supported slide-list structure.",
                    )
                presentation_relationships = _relationships(presentation_rels_root)
                source_reference_index = -1
                slide_id_values: list[int] = []
                for index, reference in enumerate(references):
                    ooxml_id = reference.get("id")
                    relation_id = reference.get(f"{{{REL_NS}}}id")
                    presentation_relation = presentation_relationships.get(relation_id or "")
                    try:
                        slide_id_values.append(int(ooxml_id or ""))
                    except ValueError as error:
                        raise CoreDomainError(
                            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                            "The presentation contains an invalid slide identifier.",
                        ) from error
                    if (
                        presentation_relation is None
                        or presentation_relation[0] != _PRESENTATION_SLIDE_REL_TYPE
                        or presentation_relation[2].casefold() != "internal"
                    ):
                        raise CoreDomainError(
                            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                            "The presentation slide relationship is invalid.",
                        )
                    resolved_part = _resolve_internal_part("ppt", presentation_relation[1])
                    if resolved_part != fidelity.slides[index].part_name:
                        raise CoreDomainError(
                            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                            "The presentation slide order does not match its slide relationships.",
                        )
                    if resolved_part == source_slide.part_name:
                        if source_reference_index >= 0:
                            raise CoreDomainError(
                                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                                "The selected slide appears more than once in the slide list.",
                            )
                        source_reference_index = index
                if (
                    source_reference_index != source_slide_index
                    or len(slide_id_values) != len(set(slide_id_values))
                    or any(value <= 0 or value > _MAX_OOXML_SLIDE_ID for value in slide_id_values)
                    or not slide_id_values
                    or max(slide_id_values) >= _MAX_OOXML_SLIDE_ID
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "This presentation cannot allocate another safe slide identifier.",
                    )

                slide_part = PresentationEditService._unique_package_part(
                    members, "ppt/slides", "slide"
                )
                slide_rels_part = PresentationEditService._relationship_part_name(slide_part)
                new_ooxml_slide_id = str(max(slide_id_values) + 1)
                new_presentation_relation_id = PresentationEditService._new_relationship_id(
                    set(presentation_relationships), "SlideCreate"
                )
                new_slide_reference = etree.Element(f"{{{PRESENTATION_NS}}}sldId")
                new_slide_reference.set("id", new_ooxml_slide_id)
                new_slide_reference.set(f"{{{REL_NS}}}id", new_presentation_relation_id)
                slide_list.insert(source_reference_index + 1, new_slide_reference)
                presentation_relationship = etree.SubElement(
                    presentation_rels_root,
                    "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
                )
                presentation_relationship.set("Id", new_presentation_relation_id)
                presentation_relationship.set("Type", _PRESENTATION_SLIDE_REL_TYPE)
                presentation_relationship.set(
                    "Target", PresentationEditService._relative_part_target("ppt", slide_part)
                )

                slide_root = etree.Element(
                    f"{{{PRESENTATION_NS}}}sld",
                    nsmap={"a": DRAWING_NS, "r": REL_NS, "p": PRESENTATION_NS},
                )
                common_slide_data = etree.SubElement(slide_root, f"{{{PRESENTATION_NS}}}cSld")
                shape_tree = etree.SubElement(common_slide_data, f"{{{PRESENTATION_NS}}}spTree")
                group_properties = etree.SubElement(shape_tree, f"{{{PRESENTATION_NS}}}nvGrpSpPr")
                group_non_visual = etree.SubElement(group_properties, f"{{{PRESENTATION_NS}}}cNvPr")
                group_non_visual.set("id", "1")
                group_non_visual.set("name", "")
                etree.SubElement(group_properties, f"{{{PRESENTATION_NS}}}cNvGrpSpPr")
                etree.SubElement(group_properties, f"{{{PRESENTATION_NS}}}nvPr")
                group_shape_properties = etree.SubElement(
                    shape_tree, f"{{{PRESENTATION_NS}}}grpSpPr"
                )
                transform = etree.SubElement(group_shape_properties, f"{{{DRAWING_NS}}}xfrm")
                etree.SubElement(
                    transform,
                    f"{{{DRAWING_NS}}}off",
                    x="0",
                    y="0",
                )
                etree.SubElement(
                    transform,
                    f"{{{DRAWING_NS}}}ext",
                    cx="0",
                    cy="0",
                )
                etree.SubElement(
                    transform,
                    f"{{{DRAWING_NS}}}chOff",
                    x="0",
                    y="0",
                )
                etree.SubElement(
                    transform,
                    f"{{{DRAWING_NS}}}chExt",
                    cx="0",
                    cy="0",
                )
                if slots:
                    from presenter_core.presentation.layouts import populate_slots

                    populate_slots(shape_tree, slots, placeholder_text or {})
                color_map = etree.SubElement(slide_root, f"{{{PRESENTATION_NS}}}clrMapOvr")
                etree.SubElement(color_map, f"{{{DRAWING_NS}}}masterClrMapping")

                slide_rels_root = etree.Element(
                    "{http://schemas.openxmlformats.org/package/2006/relationships}Relationships",
                    nsmap={None: "http://schemas.openxmlformats.org/package/2006/relationships"},
                )
                layout_relation = etree.SubElement(
                    slide_rels_root,
                    "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
                )
                layout_relation.set(
                    "Id", PresentationEditService._new_relationship_id(set(), "Layout")
                )
                layout_relation.set("Type", _SLIDE_LAYOUT_REL_TYPE)
                layout_relation.set(
                    "Target",
                    PresentationEditService._relative_part_target(
                        posixpath.dirname(slide_part), layout_part
                    ),
                )

                content_type_overrides = {
                    item.get("PartName"): item.get("ContentType")
                    for item in content_types_root.xpath("./ct:Override", namespaces=_NS)
                }
                if (
                    len(content_type_overrides)
                    != len(content_types_root.xpath("./ct:Override", namespaces=_NS))
                    or content_type_overrides.get(f"/{source_slide.part_name}")
                    != _SLIDE_CONTENT_TYPE
                    or f"/{slide_part}" in content_type_overrides
                ):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The slide content-type declarations are invalid.",
                    )
                slide_override = etree.SubElement(
                    content_types_root,
                    "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
                )
                slide_override.set("PartName", f"/{slide_part}")
                slide_override.set("ContentType", _SLIDE_CONTENT_TYPE)

                replacements = {
                    "ppt/presentation.xml": etree.tostring(
                        presentation_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    ),
                    "ppt/_rels/presentation.xml.rels": etree.tostring(
                        presentation_rels_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    ),
                    "[Content_Types].xml": etree.tostring(
                        content_types_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    ),
                }
                additions = [
                    (
                        slide_part,
                        etree.tostring(
                            slide_root,
                            encoding="UTF-8",
                            xml_declaration=True,
                            standalone=True,
                        ),
                    ),
                    (
                        slide_rels_part,
                        etree.tostring(
                            slide_rels_root,
                            encoding="UTF-8",
                            xml_declaration=True,
                            standalone=True,
                        ),
                    ),
                ]
                if any(
                    len(payload) > _MAX_XML_PART_BYTES
                    for payload in [*replacements.values(), *(part for _, part in additions)]
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The new slide metadata exceeds the safe editing limit.",
                    )
                if any(part_name in members for part_name, _ in additions):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The new slide would overwrite an existing package part.",
                    )
                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        replacement = replacements.get(info.filename)
                        if replacement is not None:
                            output_archive.writestr(copied_info, replacement)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
                    for part_name, payload in additions:
                        output_archive.writestr(part_name, payload)
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        expected_slide_order = original_slide_ids.copy()
        expected_slide_order.insert(source_slide_index + 1, "")
        revised_ids = [item.slide_id for item in revised_fidelity.slides]
        if len(revised_ids) != len(expected_slide_order):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Creating the slide changed the presentation slide count unexpectedly.",
            )
        blank_slide = revised_fidelity.slides[source_slide_index + 1]
        expected_slide_order[source_slide_index + 1] = blank_slide.slide_id
        if (
            revised_ids != expected_slide_order
            or blank_slide.slide_id in original_slide_ids
            or blank_slide.part_name != slide_part
            or len(blank_slide.objects) != len(slots)
            or any(not obj.geometry_editable for obj in blank_slide.objects)
            or [obj.text or "" for obj in blank_slide.objects]
            != [(placeholder_text or {}).get(slot["placeholder_id"], "") for slot in slots]
            or blank_slide.speaker_notes is not None
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The new slide is not blank or did not retain its requested position.",
            )
        if any(
            original.slide_id != revised.slide_id
            or original.objects != revised.objects
            or original.part_name != revised.part_name
            or original.speaker_notes != revised.speaker_notes
            or original.speaker_notes_editable != revised.speaker_notes_editable
            for original, revised in zip(
                fidelity.slides,
                [item for item in revised_fidelity.slides if item.slide_id in original_slide_ids],
                strict=True,
            )
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Creating a slide changed an existing slide or its relationships.",
            )

        try:
            with zipfile.ZipFile(destination_path, "r") as revised_archive:
                revised_members = {info.filename: info for info in revised_archive.infolist()}
                if len(revised_members) != len(revised_archive.infolist()):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The revised presentation contains duplicate package parts.",
                    )
                blank_info = revised_members.get(slide_part)
                blank_rels_info = revised_members.get(slide_rels_part)
                if blank_info is None or blank_rels_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_VALIDATION_FAILED",
                        "The new slide package parts are missing.",
                    )
                blank_root = _parse_xml_part(revised_archive, blank_info)
                blank_rels_root = _parse_xml_part(revised_archive, blank_rels_info)
                shape_trees = blank_root.xpath("./p:cSld/p:spTree", namespaces=_NS)
                if len(shape_trees) != 1 or [child.tag for child in shape_trees[0]] != [
                    f"{{{PRESENTATION_NS}}}nvGrpSpPr",
                    f"{{{PRESENTATION_NS}}}grpSpPr",
                    *[f"{{{PRESENTATION_NS}}}sp" for _ in slots],
                ]:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_VALIDATION_FAILED",
                        "The new slide contains unexpected drawing objects.",
                    )
                blank_relationships = _relationships(blank_rels_root)
                if len(blank_relationships) != 1 or next(iter(blank_relationships.values())) != (
                    _SLIDE_LAYOUT_REL_TYPE,
                    PresentationEditService._relative_part_target(
                        posixpath.dirname(slide_part), layout_part
                    ),
                    "Internal",
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_VALIDATION_FAILED",
                        "The new slide does not use only the selected slide layout.",
                    )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The new slide package parts could not be verified.",
            ) from error
        return blank_slide.slide_id

    @staticmethod
    def _relationship_part_name(part_name: str) -> str:
        return f"{posixpath.dirname(part_name)}/_rels/{posixpath.basename(part_name)}.rels"

    @staticmethod
    def _relationship_source_part(relationship_part_name: str) -> str:
        directory = posixpath.dirname(posixpath.dirname(relationship_part_name))
        filename = posixpath.basename(relationship_part_name)
        path_components = relationship_part_name.split("/")
        if (
            not filename.endswith(".rels")
            or len(path_components) < 2
            or path_components[-2] != "_rels"
        ):
            raise CoreDomainError(
                "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                "A package relationship part has an invalid name.",
            )
        return f"{directory}/{filename[:-5]}"

    @staticmethod
    def _unique_package_part(
        members: dict[str, zipfile.ZipInfo], directory: str, prefix: str
    ) -> str:
        for index in range(1, 10_001):
            candidate = f"{directory}/{prefix}{index}.xml"
            candidate_relationships = PresentationEditService._relationship_part_name(candidate)
            if candidate not in members and candidate_relationships not in members:
                return candidate
        raise CoreDomainError(
            "PRESENTATION_EDIT_RESOURCE_LIMIT",
            "This package cannot allocate another safe slide part.",
        )

    @staticmethod
    def _new_relationship_id(existing: set[str], purpose: str) -> str:
        for index in range(1, 10_001):
            candidate = f"rId{purpose}{index}"
            if candidate not in existing:
                return candidate
        raise CoreDomainError(
            "PRESENTATION_EDIT_RESOURCE_LIMIT",
            "This package cannot allocate another safe relationship identifier.",
        )

    @staticmethod
    def _relative_part_target(source_directory: str, destination_part: str) -> str:
        return posixpath.relpath(destination_part, source_directory)

    @staticmethod
    def _write_revised_slide_order_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        expected_slide_ids: list[str],
        ordered_slide_ids: list[str],
    ) -> None:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        current_slide_ids = [slide.slide_id for slide in fidelity.slides]
        if current_slide_ids != expected_slide_ids:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The slide order changed. Refresh the preview and try again.",
            )
        slides_by_ooxml_id = {slide.ooxml_slide_id: slide for slide in fidelity.slides}

        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                if len(infos) > 2_048 or len({info.filename for info in infos}) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                presentation_info = source_archive.getinfo("ppt/presentation.xml")
                presentation_root = _parse_xml_part(source_archive, presentation_info)
                slide_lists = presentation_root.xpath("./p:sldIdLst", namespaces=_NS)
                if len(slide_lists) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not use a supported slide list.",
                    )
                slide_list = slide_lists[0]
                references = list(slide_list)
                if (
                    not references
                    or len(references) != len(current_slide_ids)
                    or any(
                        reference.tag != f"{{{PRESENTATION_NS}}}sldId" for reference in references
                    )
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This presentation does not use a supported slide list.",
                    )
                references_by_slide_id: dict[str, etree._Element] = {}
                actual_slide_ids: list[str] = []
                for reference in references:
                    ooxml_slide_id = reference.get("id")
                    slide = slides_by_ooxml_id.get(ooxml_slide_id or "")
                    if slide is None or slide.slide_id in references_by_slide_id:
                        raise CoreDomainError(
                            "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                            "The presentation slide list is invalid.",
                        )
                    references_by_slide_id[slide.slide_id] = reference
                    actual_slide_ids.append(slide.slide_id)
                if actual_slide_ids != expected_slide_ids:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The slide order changed. Refresh the preview and try again.",
                    )

                for reference in references:
                    slide_list.remove(reference)
                for slide_id in ordered_slide_ids:
                    slide_list.append(references_by_slide_id[slide_id])
                rewritten_presentation = etree.tostring(
                    presentation_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_presentation) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The presentation slide list is larger than the safe editing limit.",
                    )

                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == "ppt/presentation.xml":
                            output_archive.writestr(copied_info, rewritten_presentation)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        if [slide.slide_id for slide in revised_fidelity.slides] != ordered_slide_ids:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The reordered slide list did not pass validation.",
            )

    @staticmethod
    def _write_revised_picture_creation_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        expected_slide_ids: list[str],
        geometry: FidelityGeometry,
        alt_text: str,
        image_bytes: bytes,
        image_format: str,
    ) -> str:
        """Add a private embedded image and one explicitly placed picture."""
        try:
            extension, media_type = {
                "PNG": ("png", "image/png"),
                "JPEG": ("jpg", "image/jpeg"),
            }[image_format]
        except KeyError as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_INVALID_IMAGE",
                "The image format is not supported.",
            ) from error

        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        source_slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        if (
            source_slide is None
            or [item.slide_id for item in fidelity.slides] != expected_slide_ids
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        PresentationEditService._validate_geometry_bounds(
            geometry,
            slide_width_emu=fidelity.slide_width_emu,
            slide_height_emu=fidelity.slide_height_emu,
            field="geometry",
        )

        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                if len(infos) >= MAX_ARCHIVE_ENTRIES or len(
                    {info.filename.casefold() for info in infos}
                ) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "This presentation has no room for another media file.",
                    )
                if sum(info.file_size for info in infos) + len(image_bytes) > (
                    MAX_ARCHIVE_EXPANDED_BYTES
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The picture would exceed the expanded presentation size limit.",
                    )
                members = {info.filename: info for info in infos}
                slide_info = members.get(source_slide.part_name)
                content_types_info = members.get("[Content_Types].xml")
                relationships_part = PresentationEditService._relationship_part_name(
                    source_slide.part_name
                )
                relationships_info = members.get(relationships_part)
                if slide_info is None or content_types_info is None or relationships_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "A required presentation package part is missing.",
                    )
                slide_root = _parse_xml_part(source_archive, slide_info)
                shape_trees = slide_root.xpath("./p:cSld/p:spTree", namespaces=_NS)
                if len(shape_trees) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide does not use a supported shape-tree structure.",
                    )
                shape_tree = shape_trees[0]
                new_shape_id = _next_ooxml_shape_id(shape_tree)
                existing_names = {
                    value.casefold()
                    for value in shape_tree.xpath(".//p:cNvPr/@name", namespaces=_NS)
                    if value
                }
                shape_name = ""
                for suffix in range(1, len(existing_names) + 2):
                    candidate_name = "Picture" if suffix == 1 else f"Picture {suffix}"
                    if candidate_name.casefold() not in existing_names:
                        shape_name = candidate_name
                        break
                if not shape_name:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "This slide cannot allocate another safe object name.",
                    )

                relationships_root = _parse_xml_part(source_archive, relationships_info)
                relationships = _relationships(relationships_root)
                relationship_id = PresentationEditService._new_relationship_id(
                    set(relationships), "Image"
                )
                slide_directory = posixpath.dirname(source_slide.part_name)
                media_part = f"ppt/media/presenter-copilot-{uuid.uuid4().hex}.{extension}"
                existing_member_names = {name.casefold() for name in members}
                while media_part.casefold() in existing_member_names:
                    media_part = f"ppt/media/presenter-copilot-{uuid.uuid4().hex}.{extension}"
                media_target = posixpath.relpath(media_part, start=slide_directory)
                etree.SubElement(
                    relationships_root,
                    f"{{{_NS['rel']}}}Relationship",
                    Id=relationship_id,
                    Type=_IMAGE_REL_TYPE,
                    Target=media_target,
                )

                picture = etree.Element(f"{{{PRESENTATION_NS}}}pic")
                nonvisual = etree.SubElement(picture, f"{{{PRESENTATION_NS}}}nvPicPr")
                properties = etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvPr")
                properties.set("id", new_shape_id)
                properties.set("name", shape_name)
                if alt_text:
                    properties.set("descr", alt_text)
                picture_properties = etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvPicPr")
                locks = etree.SubElement(picture_properties, f"{{{PRESENTATION_NS}}}picLocks")
                locks.set("noChangeAspect", "1")
                etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}nvPr")

                blip_fill = etree.SubElement(picture, f"{{{PRESENTATION_NS}}}blipFill")
                blip = etree.SubElement(blip_fill, f"{{{DRAWING_NS}}}blip")
                blip.set(f"{{{REL_NS}}}embed", relationship_id)
                stretch = etree.SubElement(blip_fill, f"{{{DRAWING_NS}}}stretch")
                etree.SubElement(stretch, f"{{{DRAWING_NS}}}fillRect")
                shape_properties = etree.SubElement(picture, f"{{{PRESENTATION_NS}}}spPr")
                transform = etree.SubElement(shape_properties, f"{{{DRAWING_NS}}}xfrm")
                offset = etree.SubElement(transform, f"{{{DRAWING_NS}}}off")
                offset.set("x", str(geometry.x_emu))
                offset.set("y", str(geometry.y_emu))
                extent = etree.SubElement(transform, f"{{{DRAWING_NS}}}ext")
                extent.set("cx", str(geometry.width_emu))
                extent.set("cy", str(geometry.height_emu))
                preset = etree.SubElement(shape_properties, f"{{{DRAWING_NS}}}prstGeom")
                preset.set("prst", "rect")
                etree.SubElement(preset, f"{{{DRAWING_NS}}}avLst")

                extension_lists = shape_tree.xpath("./p:extLst", namespaces=_NS)
                element_children = [child for child in shape_tree if isinstance(child.tag, str)]
                if len(extension_lists) > 1 or (
                    extension_lists and element_children[-1] is not extension_lists[0]
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide has an unsupported shape-tree extension structure.",
                    )
                insertion_index = (
                    shape_tree.index(extension_lists[0]) if extension_lists else len(shape_tree)
                )
                shape_tree.insert(insertion_index, picture)

                content_types_root = _parse_xml_part(source_archive, content_types_info)
                matching_defaults = [
                    item
                    for item in content_types_root.findall(f"{{{_NS['ct']}}}Default")
                    if item.get("Extension", "").casefold() == extension
                ]
                if len(matching_defaults) > 1 or (
                    matching_defaults and matching_defaults[0].get("ContentType") != media_type
                ):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The image file type declaration conflicts with this presentation.",
                    )
                add_content_type_default = not matching_defaults
                if add_content_type_default:
                    default_node = etree.Element(
                        f"{{{_NS['ct']}}}Default",
                        Extension=extension,
                        ContentType=media_type,
                    )
                    first_override = next(
                        (
                            index
                            for index, child in enumerate(content_types_root)
                            if child.tag == f"{{{_NS['ct']}}}Override"
                        ),
                        len(content_types_root),
                    )
                    content_types_root.insert(first_override, default_node)

                rewritten_parts = {
                    source_slide.part_name: etree.tostring(
                        slide_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    ),
                    relationships_part: etree.tostring(
                        relationships_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    ),
                }
                if add_content_type_default:
                    rewritten_parts["[Content_Types].xml"] = etree.tostring(
                        content_types_root,
                        encoding="UTF-8",
                        xml_declaration=True,
                        standalone=True,
                    )
                if any(len(payload) > _MAX_XML_PART_BYTES for payload in rewritten_parts.values()):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The edited presentation metadata is larger than the safe editing limit.",
                    )

                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        rewritten_part = rewritten_parts.get(info.filename)
                        if rewritten_part is not None:
                            output_archive.writestr(copied_info, rewritten_part)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
                    output_archive.writestr(
                        media_part,
                        image_bytes,
                        compress_type=zipfile.ZIP_DEFLATED,
                    )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            KeyError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        revised_slide = next(
            (item for item in revised_fidelity.slides if item.slide_id == slide_id), None
        )
        new_object = (
            revised_slide.objects[-1]
            if revised_slide is not None
            and len(revised_slide.objects) == len(source_slide.objects) + 1
            else None
        )
        if (
            [item.slide_id for item in revised_fidelity.slides] != expected_slide_ids
            or revised_slide is None
            or new_object is None
            or new_object.ooxml_id != new_shape_id
            or new_object.name != shape_name
            or new_object.kind != "pic"
            or new_object.geometry != geometry
            or new_object.picture_crop is None
            or not new_object.geometry_editable
            or not new_object.delete_editable
            or new_object.object_id in {item.object_id for item in source_slide.objects}
            or revised_slide.objects[:-1] != source_slide.objects
            or revised_slide.part_name != source_slide.part_name
            or revised_slide.speaker_notes != source_slide.speaker_notes
            or revised_slide.speaker_notes_editable != source_slide.speaker_notes_editable
            or any(
                original.objects != revised.objects
                or original.part_name != revised.part_name
                or original.speaker_notes != revised.speaker_notes
                or original.speaker_notes_editable != revised.speaker_notes_editable
                for original, revised in zip(fidelity.slides, revised_fidelity.slides, strict=True)
                if original.slide_id != slide_id
            )
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The new picture did not pass validation.",
            )

        changed_parts = {source_slide.part_name, relationships_part}
        if add_content_type_default:
            changed_parts.add("[Content_Types].xml")
        try:
            with (
                _verified_source_archive(
                    source_path,
                    expected_sha256=expected_sha256,
                    expected_byte_size=expected_byte_size,
                ) as source_archive,
                zipfile.ZipFile(destination_path, "r") as output_archive,
            ):
                output_names = {info.filename for info in output_archive.infolist()}
                expected_names = set(members) | {media_part}
                if output_names != expected_names:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_VALIDATION_FAILED",
                        "Adding the picture changed the package member list unexpectedly.",
                    )
                for member_name in set(members) - changed_parts:
                    if source_archive.read(member_name) != output_archive.read(member_name):
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_VALIDATION_FAILED",
                            "Adding the picture changed an unrelated presentation part.",
                        )
                revised_slide_root = etree.fromstring(output_archive.read(source_slide.part_name))
                revised_picture = PresentationEditService._find_object_node(
                    revised_slide_root,
                    ooxml_id=new_object.ooxml_id,
                    kind="pic",
                )
                revised_blips = revised_picture.xpath("./p:blipFill/a:blip", namespaces=_NS)
                revised_embed = (
                    revised_blips[0].get(f"{{{REL_NS}}}embed") if len(revised_blips) == 1 else None
                )
                revised_relationships = _parse_xml_part(
                    output_archive, output_archive.getinfo(relationships_part)
                )
                revised_relationship = _relationships(revised_relationships).get(
                    revised_embed or ""
                )
                revised_content_types = _parse_xml_part(
                    output_archive, output_archive.getinfo("[Content_Types].xml")
                )
                revised_defaults = [
                    item
                    for item in revised_content_types.findall(f"{{{_NS['ct']}}}Default")
                    if item.get("Extension", "").casefold() == extension
                ]
                if (
                    revised_embed != relationship_id
                    or revised_relationship is None
                    or revised_relationship[0] != _IMAGE_REL_TYPE
                    or revised_relationship[2].casefold() != "internal"
                    or _resolve_internal_part(slide_directory, revised_relationship[1])
                    != media_part
                    or output_archive.read(media_part) != image_bytes
                    or len(revised_defaults) != 1
                    or revised_defaults[0].get("ContentType") != media_type
                    or revised_picture.find(
                        f"{{{PRESENTATION_NS}}}nvPicPr/{{{PRESENTATION_NS}}}cNvPr"
                    ).get("descr", "")
                    != alt_text
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_VALIDATION_FAILED",
                        "The new picture relationship or media did not pass validation.",
                    )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            KeyError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The new picture package could not be verified.",
            ) from error
        return new_object.object_id

    @staticmethod
    def _write_revised_text_box_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        expected_slide_ids: list[str],
        expected_geometry: FidelityGeometry,
        text: str,
        text_style: dict[str, Any],
    ) -> str:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        source_slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        if (
            source_slide is None
            or [item.slide_id for item in fidelity.slides] != expected_slide_ids
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                members = {info.filename: info for info in infos}
                if len(infos) > 2_048 or len(members) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                slide_info = members.get(source_slide.part_name)
                if slide_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The selected slide package part is missing.",
                    )
                slide_root = _parse_xml_part(source_archive, slide_info)
                shape_trees = slide_root.xpath("./p:cSld/p:spTree", namespaces=_NS)
                if len(shape_trees) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide does not use a supported shape-tree structure.",
                    )
                shape_tree = shape_trees[0]
                new_shape_id = _next_ooxml_shape_id(shape_tree)
                existing_names = {
                    value.casefold()
                    for value in shape_tree.xpath(".//p:cNvPr/@name", namespaces=_NS)
                    if value
                }
                shape_name = ""
                for suffix in range(1, len(existing_names) + 2):
                    candidate_name = "Text Box" if suffix == 1 else f"Text Box {suffix}"
                    if candidate_name.casefold() not in existing_names:
                        shape_name = candidate_name
                        break
                if not shape_name:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "This slide cannot allocate another safe object name.",
                    )
                shape = etree.Element(f"{{{PRESENTATION_NS}}}sp")
                nonvisual = etree.SubElement(shape, f"{{{PRESENTATION_NS}}}nvSpPr")
                properties = etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvPr")
                properties.set("id", new_shape_id)
                properties.set("name", shape_name)
                shape_properties = etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvSpPr")
                shape_properties.set("txBox", "1")
                etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}nvPr")

                drawing_properties = etree.SubElement(shape, f"{{{PRESENTATION_NS}}}spPr")
                transform = etree.SubElement(drawing_properties, f"{{{DRAWING_NS}}}xfrm")
                offset = etree.SubElement(transform, f"{{{DRAWING_NS}}}off")
                offset.set("x", str(expected_geometry.x_emu))
                offset.set("y", str(expected_geometry.y_emu))
                extent = etree.SubElement(transform, f"{{{DRAWING_NS}}}ext")
                extent.set("cx", str(expected_geometry.width_emu))
                extent.set("cy", str(expected_geometry.height_emu))
                preset = etree.SubElement(drawing_properties, f"{{{DRAWING_NS}}}prstGeom")
                preset.set("prst", "rect")
                etree.SubElement(preset, f"{{{DRAWING_NS}}}avLst")
                etree.SubElement(drawing_properties, f"{{{DRAWING_NS}}}noFill")
                line = etree.SubElement(drawing_properties, f"{{{DRAWING_NS}}}ln")
                etree.SubElement(line, f"{{{DRAWING_NS}}}noFill")

                text_body = etree.SubElement(shape, f"{{{PRESENTATION_NS}}}txBody")
                body_properties = etree.SubElement(text_body, f"{{{DRAWING_NS}}}bodyPr")
                body_properties.set("wrap", "square")
                body_properties.set("lIns", "91440")
                body_properties.set("rIns", "91440")
                body_properties.set("tIns", "45720")
                body_properties.set("bIns", "45720")
                etree.SubElement(text_body, f"{{{DRAWING_NS}}}lstStyle")
                paragraph = etree.SubElement(text_body, f"{{{DRAWING_NS}}}p")
                run = etree.SubElement(paragraph, f"{{{DRAWING_NS}}}r")
                run_properties = etree.SubElement(run, f"{{{DRAWING_NS}}}rPr")
                run_properties.set("lang", "en-US")
                run_properties.set("sz", "1800")
                PresentationEditService._apply_text_style_to_run(run, text_style)
                if "alignment" in text_style:
                    PresentationEditService._apply_paragraph_alignment(
                        paragraph, text_style["alignment"]
                    )
                text_node = etree.SubElement(run, f"{{{DRAWING_NS}}}t")
                text_node.text = text
                if text and (text[0].isspace() or text[-1].isspace()):
                    text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                end_properties = etree.SubElement(paragraph, f"{{{DRAWING_NS}}}endParaRPr")
                end_properties.set("lang", "en-US")
                end_properties.set("sz", run_properties.get("sz", "1800"))

                extension_lists = shape_tree.xpath("./p:extLst", namespaces=_NS)
                element_children = [child for child in shape_tree if isinstance(child.tag, str)]
                if len(extension_lists) > 1 or (
                    extension_lists and element_children[-1] is not extension_lists[0]
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide has an unsupported shape-tree extension structure.",
                    )
                insertion_index = (
                    shape_tree.index(extension_lists[0]) if extension_lists else len(shape_tree)
                )
                shape_tree.insert(insertion_index, shape)
                rewritten_slide = etree.tostring(
                    slide_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_slide) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The edited slide is larger than the safe editing limit.",
                    )
                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == source_slide.part_name:
                            output_archive.writestr(copied_info, rewritten_slide)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        revised_ids = [item.slide_id for item in revised_fidelity.slides]
        revised_slide = next(
            (item for item in revised_fidelity.slides if item.slide_id == slide_id), None
        )
        new_object = (
            revised_slide.objects[-1]
            if revised_slide is not None
            and len(revised_slide.objects) == len(source_slide.objects) + 1
            else None
        )
        if (
            revised_ids != expected_slide_ids
            or revised_slide is None
            or new_object is None
            or new_object.ooxml_id != new_shape_id
            or new_object.name != shape_name
            or new_object.kind != "sp"
            or new_object.text != text
            or new_object.geometry != expected_geometry
            or new_object.text_style is None
            or any(
                getattr(new_object.text_style, key) != value for key, value in text_style.items()
            )
            or not new_object.single_run_text_edit_candidate
            or not new_object.geometry_editable
            or not new_object.delete_editable
            or new_object.object_id in {item.object_id for item in source_slide.objects}
            or revised_slide.objects[:-1] != source_slide.objects
            or revised_slide.part_name != source_slide.part_name
            or revised_slide.speaker_notes != source_slide.speaker_notes
            or revised_slide.speaker_notes_editable != source_slide.speaker_notes_editable
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The new text box did not pass validation.",
            )
        other_revised_slides = [
            item for item in revised_fidelity.slides if item.slide_id != slide_id
        ]
        if any(
            original.objects != revised.objects
            or original.part_name != revised.part_name
            or original.speaker_notes != revised.speaker_notes
            or original.speaker_notes_editable != revised.speaker_notes_editable
            for original, revised in zip(
                [item for item in fidelity.slides if item.slide_id != slide_id],
                other_revised_slides,
                strict=True,
            )
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Creating a text box changed another slide.",
            )
        return new_object.object_id

    @staticmethod
    def _write_revised_text_style_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        object_id: str,
        expected_text: str,
        expected_style_fingerprint: str,
        replacement_style: dict[str, Any],
        require_single_run: bool,
    ) -> None:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        obj = (
            next((item for item in slide.objects if item.object_id == object_id), None)
            if slide is not None
            else None
        )
        if slide is None or obj is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected text shape is unavailable."
            )
        if (
            not obj.text_format_edit_candidate
            or (require_single_run and not obj.single_run_text_edit_candidate)
            or obj.text_style is None
            or not obj.text_style.editable
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text shape does not use a supported plain-paragraph formatting structure.",
            )
        if obj.text != expected_text or obj.text_style.fingerprint != expected_style_fingerprint:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The selected text or formatting changed. Refresh the preview and try again.",
            )
        if "font_color" in replacement_style and not obj.text_style.color_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text run has incompatible direct color fills.",
            )
        if "alignment" in replacement_style and not obj.text_style.alignment_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph does not support direct alignment formatting.",
            )
        if "bullet_mode" in replacement_style and not obj.text_style.bullet_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's bullet style cannot be safely edited.",
            )
        if "bullet_color" in replacement_style and not obj.text_style.bullet_color_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's bullet color cannot be safely edited.",
            )
        if "bullet_size_percent" in replacement_style and not obj.text_style.bullet_size_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's bullet size cannot be safely edited.",
            )
        if "numbering_start" in replacement_style and not obj.text_style.numbering_start_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's list numbering cannot be safely edited.",
            )
        if "left_indent_pt" in replacement_style and not obj.text_style.left_indent_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's left indentation cannot be safely edited.",
            )
        if (
            "first_line_indent_pt" in replacement_style
            and not obj.text_style.first_line_indent_editable
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's first-line indentation cannot be safely edited.",
            )
        if "line_spacing_pt" in replacement_style and not obj.text_style.line_spacing_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's line spacing cannot be safely edited.",
            )
        if "space_before_pt" in replacement_style and not obj.text_style.space_before_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's before spacing cannot be safely edited.",
            )
        if "space_after_pt" in replacement_style and not obj.text_style.space_after_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text paragraph's after spacing cannot be safely edited.",
            )

        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                if len(infos) > 2_048 or len({info.filename for info in infos}) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                slide_info = source_archive.getinfo(slide.part_name)
                slide_root = _parse_xml_part(source_archive, slide_info)
                shape = PresentationEditService._find_shape(slide_root, obj.ooxml_id)
                paragraphs = shape.xpath("./p:txBody/a:p", namespaces=_NS)
                runs = _formatable_text_runs(shape, "sp")
                current_text = (
                    "\n".join(
                        "".join(
                            text_node.text or ""
                            for run in paragraph.xpath("./a:r | ./a:fld", namespaces=_NS)
                            for text_node in run.xpath("./a:t", namespaces=_NS)
                        )
                        for paragraph in paragraphs
                    )
                    if runs is not None
                    else None
                )
                if current_text != expected_text:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The selected text changed. Refresh the preview and try again.",
                    )
                current_style = _text_style_for_shape(shape, "sp")
                if (
                    not current_style.editable
                    or current_style.fingerprint != expected_style_fingerprint
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The selected formatting changed. Refresh the preview and try again.",
                    )

                if runs is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This text shape no longer uses a supported paragraph structure.",
                    )
                for run in runs:
                    PresentationEditService._apply_text_style_to_run(run, replacement_style)
                # Breaks keep their own run properties; style them too so line
                # height follows the new text size.
                if replacement_style.keys() & {
                    "bold",
                    "italic",
                    "font_family",
                    "font_size_pt",
                    "font_color",
                }:
                    for line_break in shape.xpath("./p:txBody/a:p/a:br", namespaces=_NS):
                        PresentationEditService._apply_text_style_to_run(
                            line_break, replacement_style
                        )
                paragraph_style_keys = {
                    "alignment",
                    "bullet_mode",
                    "bullet_color",
                    "bullet_size_percent",
                    "numbering_start",
                    "left_indent_pt",
                    "first_line_indent_pt",
                    "line_spacing_pt",
                    "space_before_pt",
                    "space_after_pt",
                } & replacement_style.keys()
                if paragraph_style_keys:
                    if not paragraphs:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED",
                            "This text shape no longer has supported paragraphs.",
                        )
                    for paragraph in _styled_paragraphs(paragraphs):
                        if "alignment" in replacement_style:
                            PresentationEditService._apply_paragraph_alignment(
                                paragraph,
                                replacement_style["alignment"],
                            )
                        if "bullet_mode" in replacement_style:
                            PresentationEditService._apply_paragraph_bullet(
                                paragraph,
                                replacement_style["bullet_mode"],
                            )
                        for decoration in ("bullet_color", "bullet_size_percent"):
                            if decoration in replacement_style:
                                PresentationEditService._apply_paragraph_bullet_decoration(
                                    paragraph, decoration, replacement_style[decoration]
                                )
                        if "numbering_start" in replacement_style:
                            PresentationEditService._apply_paragraph_numbering_start(
                                paragraph, replacement_style["numbering_start"]
                            )
                        if "left_indent_pt" in replacement_style:
                            PresentationEditService._apply_paragraph_left_indent(
                                paragraph,
                                replacement_style["left_indent_pt"],
                            )
                        if "first_line_indent_pt" in replacement_style:
                            PresentationEditService._apply_paragraph_first_line_indent(
                                paragraph,
                                replacement_style["first_line_indent_pt"],
                            )
                        if "line_spacing_pt" in replacement_style:
                            PresentationEditService._apply_paragraph_spacing(
                                paragraph,
                                "lnSpc",
                                replacement_style["line_spacing_pt"],
                            )
                        if "space_before_pt" in replacement_style:
                            PresentationEditService._apply_paragraph_spacing(
                                paragraph,
                                "spcBef",
                                replacement_style["space_before_pt"],
                            )
                        if "space_after_pt" in replacement_style:
                            PresentationEditService._apply_paragraph_spacing(
                                paragraph,
                                "spcAft",
                                replacement_style["space_after_pt"],
                            )

                rewritten_slide = etree.tostring(
                    slide_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_slide) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "The edited slide is larger than the safe editing limit.",
                    )
                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == slide.part_name:
                            output_archive.writestr(copied_info, rewritten_slide)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        revised_slide = next(
            (item for item in revised_fidelity.slides if item.slide_id == slide_id), None
        )
        revised_object = (
            next((item for item in revised_slide.objects if item.object_id == object_id), None)
            if revised_slide is not None
            else None
        )
        if (
            revised_object is None
            or revised_object.text != expected_text
            or not revised_object.text_format_edit_candidate
            or (require_single_run and not revised_object.single_run_text_edit_candidate)
            or revised_object.text_style is None
            or not revised_object.text_style.editable
            or any(
                getattr(
                    revised_object.text_style,
                    "bullet_state" if name == "bullet_mode" else name,
                )
                != value
                for name, value in replacement_style.items()
            )
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The edited presentation did not pass validation.",
            )

    @staticmethod
    def _apply_text_style_to_run(run: etree._Element, replacement_style: dict[str, Any]) -> None:
        run_properties = run.find(f"{{{DRAWING_NS}}}rPr")
        if run_properties is None:
            run_properties = etree.Element(f"{{{DRAWING_NS}}}rPr")
            run.insert(0, run_properties)
        for name in ("bold", "italic"):
            if name in replacement_style:
                run_properties.set(
                    "b" if name == "bold" else "i",
                    "1" if replacement_style[name] else "0",
                )
        if "font_family" in replacement_style:
            latin = run_properties.find(f"{{{DRAWING_NS}}}latin")
            if latin is None:
                following = {
                    f"{{{DRAWING_NS}}}{name}"
                    for name in ("ea", "cs", "sym", "hlinkClick", "hlinkMouseOver", "rtl", "extLst")
                }
                latin = etree.Element(f"{{{DRAWING_NS}}}latin")
                run_properties.insert(
                    next(
                        (
                            index
                            for index, child in enumerate(run_properties)
                            if child.tag in following
                        ),
                        len(run_properties),
                    ),
                    latin,
                )
            # Panose/charset metadata described the previous font.
            for attribute in list(latin.attrib):
                del latin.attrib[attribute]
            latin.set("typeface", replacement_style["font_family"])
        # Turning emphasis on keeps an existing underline/strike style (double, wavy...).
        for name, attribute, off, on in (
            ("underline", "u", "none", "sng"),
            ("strikethrough", "strike", "noStrike", "sngStrike"),
        ):
            if name in replacement_style:
                current = run_properties.get(attribute)
                if not replacement_style[name]:
                    run_properties.set(attribute, off)
                elif current is None or current == off:
                    run_properties.set(attribute, on)
        if "font_size_pt" in replacement_style:
            run_properties.set("sz", str(replacement_style["font_size_pt"] * 100))
        if "font_color" in replacement_style:
            fill_tags = {
                f"{{{DRAWING_NS}}}noFill",
                f"{{{DRAWING_NS}}}solidFill",
                f"{{{DRAWING_NS}}}gradFill",
                f"{{{DRAWING_NS}}}blipFill",
                f"{{{DRAWING_NS}}}pattFill",
                f"{{{DRAWING_NS}}}grpFill",
            }
            fills = [child for child in run_properties if child.tag in fill_tags]
            if len(fills) > 1:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED",
                    "This text run has incompatible direct color fills.",
                )
            for fill in fills:
                run_properties.remove(fill)
            new_fill = etree.Element(f"{{{DRAWING_NS}}}solidFill")
            color = etree.SubElement(new_fill, f"{{{DRAWING_NS}}}srgbClr")
            color.set("val", replacement_style["font_color"][1:])
            following_properties = {
                f"{{{DRAWING_NS}}}effectLst",
                f"{{{DRAWING_NS}}}effectDag",
                f"{{{DRAWING_NS}}}highlight",
                f"{{{DRAWING_NS}}}uFill",
                f"{{{DRAWING_NS}}}uLn",
                f"{{{DRAWING_NS}}}latin",
                f"{{{DRAWING_NS}}}ea",
                f"{{{DRAWING_NS}}}cs",
                f"{{{DRAWING_NS}}}sym",
                f"{{{DRAWING_NS}}}hlinkClick",
                f"{{{DRAWING_NS}}}hlinkMouseOver",
                f"{{{DRAWING_NS}}}rtl",
                f"{{{DRAWING_NS}}}extLst",
            }
            insertion_index = next(
                (
                    index
                    for index, child in enumerate(run_properties)
                    if child.tag in following_properties
                ),
                len(run_properties),
            )
            run_properties.insert(insertion_index, new_fill)

    @staticmethod
    def _apply_paragraph_alignment(paragraph: etree._Element, alignment: str) -> None:
        paragraph_properties = paragraph.find(f"{{{DRAWING_NS}}}pPr")
        if paragraph_properties is None:
            paragraph_properties = etree.Element(f"{{{DRAWING_NS}}}pPr")
            paragraph.insert(0, paragraph_properties)
        alignment_codes = {"left": "l", "center": "ctr", "right": "r", "justify": "just"}
        code = alignment_codes.get(alignment)
        if code is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This paragraph alignment is not supported.",
            )
        paragraph_properties.set("algn", code)

    @staticmethod
    def _apply_paragraph_left_indent(paragraph: etree._Element, left_indent_pt: int) -> None:
        if type(left_indent_pt) is not int or not 0 <= left_indent_pt <= MAX_TEXT_LEFT_INDENT_PT:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "The requested paragraph indentation is outside the supported range.",
            )
        paragraph_properties = paragraph.find(f"{{{DRAWING_NS}}}pPr")
        if paragraph_properties is None:
            paragraph_properties = etree.Element(f"{{{DRAWING_NS}}}pPr")
            paragraph.insert(0, paragraph_properties)
        paragraph_properties.set("marL", str(left_indent_pt * EMU_PER_POINT))

    @staticmethod
    def _apply_paragraph_first_line_indent(
        paragraph: etree._Element, first_line_indent_pt: int
    ) -> None:
        if (
            type(first_line_indent_pt) is not int
            or not -MAX_TEXT_FIRST_LINE_INDENT_PT
            <= first_line_indent_pt
            <= MAX_TEXT_FIRST_LINE_INDENT_PT
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "The requested first-line indentation is outside the supported range.",
            )
        paragraph_properties = paragraph.find(f"{{{DRAWING_NS}}}pPr")
        if paragraph_properties is None:
            paragraph_properties = etree.Element(f"{{{DRAWING_NS}}}pPr")
            paragraph.insert(0, paragraph_properties)
        paragraph_properties.set("indent", str(first_line_indent_pt * EMU_PER_POINT))

    @staticmethod
    def _apply_paragraph_bullet(paragraph: etree._Element, bullet_mode: str) -> None:
        if bullet_mode not in PARAGRAPH_BULLET_MODES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This paragraph list style is not supported.",
            )

        paragraph_properties = paragraph.find(f"{{{DRAWING_NS}}}pPr")
        if paragraph_properties is None:
            paragraph_properties = etree.Element(f"{{{DRAWING_NS}}}pPr")
            paragraph.insert(0, paragraph_properties)
        _, bullet_editable = _paragraph_bullet_mode_for_shape(paragraph_properties)
        if not bullet_editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This paragraph's existing bullet style cannot be safely edited.",
            )

        # Only the marker type is replaced; supported color/size/font decoration stays,
        # and a numbering start carries over between numbered schemes.
        previous_number = paragraph_properties.find(f"{{{DRAWING_NS}}}buAutoNum")
        previous_start = previous_number.get("startAt") if previous_number is not None else None
        for child in list(paragraph_properties):
            if (
                isinstance(child.tag, str)
                and child.tag.startswith(f"{{{DRAWING_NS}}}")
                and child.tag.removeprefix(f"{{{DRAWING_NS}}}") in _PARAGRAPH_BULLET_TYPE_NAMES
            ):
                paragraph_properties.remove(child)

        # New glyphs and numbers need a text font; a symbol bullet font would
        # render them as unrelated symbols.
        for font in paragraph_properties.findall(f"{{{DRAWING_NS}}}buFont"):
            if not plain_bullet_font(font.get("typeface")):
                paragraph_properties.remove(font)

        bullet_tag_name = (
            "buChar"
            if bullet_mode in PARAGRAPH_BULLET_CHAR_BY_MODE
            else "buAutoNum"
            if bullet_mode in PARAGRAPH_AUTONUM_TYPE_BY_MODE
            else "buNone"
        )
        insert_index = _paragraph_property_insert_index(paragraph_properties, bullet_tag_name)
        if insert_index is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This paragraph's properties cannot safely accept a list style.",
            )
        bullet_node = etree.Element(f"{{{DRAWING_NS}}}{bullet_tag_name}")
        if bullet_mode in PARAGRAPH_BULLET_CHAR_BY_MODE:
            bullet_node.set("char", PARAGRAPH_BULLET_CHAR_BY_MODE[bullet_mode])
        elif bullet_mode in PARAGRAPH_AUTONUM_TYPE_BY_MODE:
            bullet_node.set("type", PARAGRAPH_AUTONUM_TYPE_BY_MODE[bullet_mode])
            if previous_start is not None:
                bullet_node.set("startAt", previous_start)
        paragraph_properties.insert(insert_index, bullet_node)
        if bullet_mode == "none" or any(
            paragraph_properties.find(f"{{{DRAWING_NS}}}{name}") is not None
            for name in ("buFont", "buFontTx")
        ):
            return
        # Without a direct text font the marker would inherit the list style's bullet
        # font, which may be a symbol font (for example Wingdings in lstStyle or the
        # master). Follow the text font so the chosen glyph or number renders as shown.
        font_index = _paragraph_property_insert_index(paragraph_properties, "buFontTx")
        if font_index is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This paragraph's properties cannot safely accept a list style.",
            )
        paragraph_properties.insert(font_index, etree.Element(f"{{{DRAWING_NS}}}buFontTx"))

    @staticmethod
    def _apply_paragraph_numbering_start(paragraph: etree._Element, start: int) -> None:
        paragraph_properties = paragraph.find(f"{{{DRAWING_NS}}}pPr")
        node = (
            paragraph_properties.find(f"{{{DRAWING_NS}}}buAutoNum")
            if paragraph_properties is not None
            else None
        )
        if node is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "Choose a numbered list style before setting where numbering starts.",
            )
        if start == 1:
            node.attrib.pop("startAt", None)
        else:
            node.set("startAt", str(start))

    @staticmethod
    def _apply_paragraph_bullet_decoration(
        paragraph: etree._Element, name: str, value: str | int
    ) -> None:
        """Replace one direct bullet color (buClr) or size (buSzPct) decoration."""
        paragraph_properties = paragraph.find(f"{{{DRAWING_NS}}}pPr")
        if paragraph_properties is None:
            paragraph_properties = etree.Element(f"{{{DRAWING_NS}}}pPr")
            paragraph.insert(0, paragraph_properties)
        _, _, editable = _paragraph_bullet_decoration_for_shape(paragraph_properties)
        if not editable:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This paragraph's existing bullet decoration cannot be safely edited.",
            )
        replaced, tag = (
            ({"buClrTx", "buClr"}, "buClr")
            if name == "bullet_color"
            else ({"buSzTx", "buSzPct", "buSzPts"}, "buSzPct")
        )
        for child in list(paragraph_properties):
            if (
                isinstance(child.tag, str)
                and child.tag.removeprefix(f"{{{DRAWING_NS}}}") in replaced
            ):
                paragraph_properties.remove(child)
        insert_index = _paragraph_property_insert_index(paragraph_properties, tag)
        if insert_index is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This paragraph's properties cannot safely accept bullet decoration.",
            )
        node = etree.Element(f"{{{DRAWING_NS}}}{tag}")
        if name == "bullet_color":
            assert isinstance(value, str)
            etree.SubElement(node, f"{{{DRAWING_NS}}}srgbClr", val=value.removeprefix("#"))
        else:
            assert isinstance(value, int)
            node.set("val", str(value * 1000))
        paragraph_properties.insert(insert_index, node)

    @staticmethod
    def _apply_paragraph_spacing(
        paragraph: etree._Element, property_name: str, spacing_pt: int
    ) -> None:
        minimum_spacing_pt = 1 if property_name == "lnSpc" else 0
        maximum_spacing_pt = (
            MAX_TEXT_LINE_SPACING_PT if property_name == "lnSpc" else MAX_TEXT_PARAGRAPH_SPACING_PT
        )
        if (
            property_name not in {"lnSpc", "spcBef", "spcAft"}
            or type(spacing_pt) is not int
            or not minimum_spacing_pt <= spacing_pt <= maximum_spacing_pt
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "The requested paragraph spacing is outside the supported range.",
            )

        paragraph_properties = paragraph.find(f"{{{DRAWING_NS}}}pPr")
        if paragraph_properties is None:
            paragraph_properties = etree.Element(f"{{{DRAWING_NS}}}pPr")
            paragraph.insert(0, paragraph_properties)

        spacing_tag = f"{{{DRAWING_NS}}}{property_name}"
        spacing_nodes = paragraph_properties.findall(spacing_tag)
        if len(spacing_nodes) > 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This paragraph contains duplicate spacing properties.",
            )
        if spacing_nodes:
            spacing_node = spacing_nodes[0]
            points_nodes = list(spacing_node)
            if (
                spacing_node.attrib
                or len(points_nodes) != 1
                or points_nodes[0].tag != f"{{{DRAWING_NS}}}spcPts"
                or set(points_nodes[0].attrib) != {"val"}
                or len(points_nodes[0])
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED",
                    "This paragraph's existing spacing cannot be safely edited.",
                )
            points_nodes[0].set("val", str(spacing_pt * 100))
            return

        insert_index = _paragraph_property_insert_index(paragraph_properties, property_name)
        if insert_index is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This paragraph's properties cannot safely accept a spacing value.",
            )
        spacing_node = etree.Element(spacing_tag)
        points_node = etree.SubElement(spacing_node, f"{{{DRAWING_NS}}}spcPts")
        points_node.set("val", str(spacing_pt * 100))
        paragraph_properties.insert(insert_index, spacing_node)

    @staticmethod
    def _write_revised_shape_style_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        object_id: str,
        expected_style_fingerprint: str,
        replacement_style: dict[str, Any],
    ) -> None:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        obj = (
            next((item for item in slide.objects if item.object_id == object_id), None)
            if slide is not None
            else None
        )
        if slide is None or obj is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected shape is unavailable."
            )
        if (
            obj.kind != "sp"
            or obj.shape_style is None
            or not obj.shape_style.editable
            or obj.shape_style.fingerprint != expected_style_fingerprint
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The selected shape styling changed. Refresh the preview and try again.",
            )
        for property_name in replacement_style:
            editable_field = (
                "line_format_editable"
                if property_name in {"line_width_pt", "line_dash"}
                else f"{property_name.removesuffix('_color')}_editable"
            )
            if not getattr(obj.shape_style, editable_field):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED",
                    "This shape uses a fill or outline style the editor cannot safely retain.",
                )

        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                if len(infos) > 2_048 or len({info.filename for info in infos}) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                slide_info = source_archive.getinfo(slide.part_name)
                slide_root = _parse_xml_part(source_archive, slide_info)
                shape = PresentationEditService._find_object_node(
                    slide_root, ooxml_id=obj.ooxml_id, kind="sp"
                )
                shape_trees = slide_root.xpath("./p:cSld/p:spTree", namespaces=_NS)
                if len(shape_trees) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                shape_tree = shape_trees[0]
                current_style = _shape_style(shape, "sp", shape_tree=shape_tree)
                if (
                    not current_style.editable
                    or current_style.fingerprint != expected_style_fingerprint
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The selected shape styling changed. Refresh the preview and try again.",
                    )
                for property_name, value in replacement_style.items():
                    if property_name in {"fill_color", "line_color"}:
                        PresentationEditService._replace_shape_solid_color(
                            shape, property_name=property_name, color=value
                        )
                PresentationEditService._replace_shape_line_format(
                    shape,
                    width_pt=replacement_style.get("line_width_pt"),
                    dash=replacement_style.get("line_dash"),
                )

                rewritten_slide = etree.tostring(
                    slide_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_slide) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The edited slide is larger than the safe editing limit.",
                    )
                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == slide.part_name:
                            output_archive.writestr(copied_info, rewritten_slide)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        revised_slide = next(
            (item for item in revised_fidelity.slides if item.slide_id == slide_id), None
        )
        revised_object = (
            next((item for item in revised_slide.objects if item.object_id == object_id), None)
            if revised_slide is not None
            else None
        )
        revised_style = revised_object.shape_style if revised_object is not None else None
        expected_style = replace(
            obj.shape_style,
            fingerprint=revised_style.fingerprint if revised_style is not None else None,
            **replacement_style,
        )
        expected_object = replace(obj, shape_style=expected_style)
        if revised_object != expected_object:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The edited shape style did not pass validation.",
            )
        revised_slides = {item.slide_id: item for item in revised_fidelity.slides}
        for original_slide in fidelity.slides:
            revised = revised_slides.get(original_slide.slide_id)
            if revised is None or revised.part_name != original_slide.part_name:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED",
                    "The shape formatting changed the slide structure.",
                )
            if original_slide.slide_id != slide_id:
                if revised != original_slide:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_VALIDATION_FAILED",
                        "The shape formatting changed another slide.",
                    )
            elif (
                len(revised.objects) != len(original_slide.objects)
                or any(
                    revised_item != expected_object
                    if original_item.object_id == object_id
                    else revised_item != original_item
                    for original_item, revised_item in zip(
                        original_slide.objects, revised.objects, strict=True
                    )
                )
                or revised.speaker_notes != original_slide.speaker_notes
                or revised.speaker_notes_editable != original_slide.speaker_notes_editable
            ):
                raise CoreDomainError(
                    "PRESENTATION_EDIT_VALIDATION_FAILED",
                    "The shape formatting changed unrelated slide content.",
                )

    @staticmethod
    def _replace_shape_solid_color(
        shape: etree._Element, *, property_name: str, color: str
    ) -> None:
        shape_properties = shape.find(f"{{{PRESENTATION_NS}}}spPr")
        if shape_properties is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This shape does not have a supported property container.",
            )
        if property_name == "fill_color":
            container = shape_properties
            fill_tags = {
                f"{{{DRAWING_NS}}}noFill",
                f"{{{DRAWING_NS}}}solidFill",
                f"{{{DRAWING_NS}}}gradFill",
                f"{{{DRAWING_NS}}}blipFill",
                f"{{{DRAWING_NS}}}pattFill",
                f"{{{DRAWING_NS}}}grpFill",
            }
            insertion_rank = 2
        elif property_name == "line_color":
            lines = shape_properties.findall(f"{{{DRAWING_NS}}}ln")
            if len(lines) > 1:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_UNSUPPORTED",
                    "This shape has multiple outline property blocks.",
                )
            if lines:
                container = lines[0]
            else:
                container = etree.Element(f"{{{DRAWING_NS}}}ln")
                PresentationEditService._insert_ordered_shape_property(
                    shape_properties, container, insertion_rank=3
                )
            fill_tags = {
                f"{{{DRAWING_NS}}}noFill",
                f"{{{DRAWING_NS}}}solidFill",
                f"{{{DRAWING_NS}}}gradFill",
                f"{{{DRAWING_NS}}}blipFill",
                f"{{{DRAWING_NS}}}pattFill",
                f"{{{DRAWING_NS}}}grpFill",
            }
            insertion_rank = 0
        else:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED", "The selected shape property is unsupported."
            )

        for child in list(container):
            if child.tag in fill_tags:
                container.remove(child)
        solid_fill = etree.Element(f"{{{DRAWING_NS}}}solidFill")
        rgb = etree.SubElement(solid_fill, f"{{{DRAWING_NS}}}srgbClr")
        rgb.set("val", color[1:])
        PresentationEditService._insert_ordered_shape_property(
            container, solid_fill, insertion_rank=insertion_rank
        )

    @staticmethod
    def _replace_shape_line_format(
        shape: etree._Element, *, width_pt: float | None, dash: str | None
    ) -> None:
        """Set outline width (ln@w) and preset dash, keeping the outline color."""
        if width_pt is None and dash is None:
            return
        shape_properties = shape.find(f"{{{PRESENTATION_NS}}}spPr")
        if shape_properties is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This shape does not have a supported property container.",
            )
        lines = shape_properties.findall(f"{{{DRAWING_NS}}}ln")
        if len(lines) > 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This shape has multiple outline property blocks.",
            )
        if lines:
            line = lines[0]
        else:
            line = etree.Element(f"{{{DRAWING_NS}}}ln")
            PresentationEditService._insert_ordered_shape_property(
                shape_properties, line, insertion_rank=3
            )
        if width_pt is not None:
            line.set("w", str(round(width_pt * EMU_PER_POINT)))
        if dash is not None:
            for child in list(line):
                if child.tag in {f"{{{DRAWING_NS}}}prstDash", f"{{{DRAWING_NS}}}custDash"}:
                    line.remove(child)
            preset = etree.Element(f"{{{DRAWING_NS}}}prstDash")
            preset.set("val", dash)
            fills = {
                f"{{{DRAWING_NS}}}{name}"
                for name in ("noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill")
            }
            position = 0
            for index, child in enumerate(line):
                if child.tag in fills:
                    position = index + 1
            line.insert(position, preset)

    @staticmethod
    def _insert_ordered_shape_property(
        parent: etree._Element, child: etree._Element, *, insertion_rank: int
    ) -> None:
        """Insert a shape property at its OOXML sequence position."""
        local_order = {
            "xfrm": 0,
            "prstGeom": 1,
            "custGeom": 1,
            "noFill": 2,
            "solidFill": 2,
            "gradFill": 2,
            "blipFill": 2,
            "pattFill": 2,
            "grpFill": 2,
            "ln": 3,
            "effectLst": 4,
            "scene3d": 5,
            "sp3d": 6,
            "extLst": 7,
        }
        index = next(
            (
                item_index
                for item_index, current in enumerate(parent)
                if local_order.get(etree.QName(current).localname, 100) > insertion_rank
            ),
            len(parent),
        )
        parent.insert(index, child)

    @staticmethod
    def _write_revised_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        object_id: str,
        expected_text: str,
        replacement_text: str,
        allow_uniform_runs: bool = False,
    ) -> None:
        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )

        slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        obj = next(
            (
                item
                for candidate_slide in fidelity.slides
                if candidate_slide.slide_id == slide_id
                for item in candidate_slide.objects
                if item.object_id == object_id
            ),
            None,
        )
        if slide is None or obj is None:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected text shape is unavailable."
            )
        if not obj.single_run_text_edit_candidate and not (
            allow_uniform_runs and obj.uniform_run_text_edit_candidate
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This text shape cannot be edited safely in this version.",
            )
        if obj.text != expected_text:
            raise CoreDomainError(
                "PRESENTATION_EDIT_STALE_TARGET",
                "The selected text changed. Refresh the preview and try again.",
            )

        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                if len(infos) > 2_048 or len({info.filename for info in infos}) != len(infos):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                slide_info = source_archive.getinfo(slide.part_name)
                slide_root = _parse_xml_part(source_archive, slide_info)
                shape = PresentationEditService._find_shape(slide_root, obj.ooxml_id)
                paragraphs = shape.xpath("./p:txBody/a:p", namespaces=_NS)
                runs = _formatable_text_runs(shape, "sp")
                if (
                    len(paragraphs) != 1
                    or runs is None
                    or shape.xpath("./p:txBody/a:p/a:br | ./p:txBody/a:p/a:fld", namespaces=_NS)
                    or (not allow_uniform_runs and len(runs) != 1)
                    or (len(runs) > 1 and not _is_uniform_run_text_shape(shape, "sp"))
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This text shape no longer uses a supported replacement structure.",
                    )
                text_node = runs[0].find(f"{{{DRAWING_NS}}}t")
                if text_node is None:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This text shape no longer uses a supported replacement structure.",
                    )
                current_text = "".join(
                    run.find(f"{{{DRAWING_NS}}}t").text or ""
                    for run in runs
                    if run.find(f"{{{DRAWING_NS}}}t") is not None
                )
                if current_text != expected_text:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_STALE_TARGET",
                        "The selected text changed. Refresh the preview and try again.",
                    )
                for run in runs[1:]:
                    parent = run.getparent()
                    if parent is None:
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_UNSUPPORTED",
                            "This text shape no longer uses a supported replacement structure.",
                        )
                    parent.remove(run)
                text_node.text = replacement_text
                xml_space = "{http://www.w3.org/XML/1998/namespace}space"
                if replacement_text and (
                    replacement_text[0].isspace() or replacement_text[-1].isspace()
                ):
                    text_node.set(xml_space, "preserve")
                else:
                    text_node.attrib.pop(xml_space, None)
                rewritten_slide = etree.tostring(
                    slide_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_slide) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "The edited slide is larger than the safe editing limit.",
                    )

                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == slide.part_name:
                            output_archive.writestr(copied_info, rewritten_slide)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        revised_slide = next(
            (item for item in revised_fidelity.slides if item.slide_id == slide_id), None
        )
        revised_object = (
            next((item for item in revised_slide.objects if item.object_id == object_id), None)
            if revised_slide is not None
            else None
        )
        if (
            revised_object is None
            or revised_object.text != replacement_text
            or not revised_object.single_run_text_edit_candidate
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The edited presentation did not pass validation.",
            )

    @staticmethod
    def _find_transform(
        root: etree._Element,
        *,
        ooxml_id: str,
        kind: str,
    ) -> tuple[etree._Element, etree._Element]:
        candidate = PresentationEditService._find_object_node(
            root,
            ooxml_id=ooxml_id,
            kind=kind,
        )
        transforms = candidate.xpath(
            "./p:grpSpPr/a:xfrm"
            if kind == "grpSp"
            else "./p:xfrm"
            if kind == "graphicFrame"
            else "./p:spPr/a:xfrm",
            namespaces=_NS,
        )
        if len(transforms) != 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This object does not use a supported slide-level transform.",
            )
        offset = transforms[0].xpath("./a:off", namespaces=_NS)
        extent = transforms[0].xpath("./a:ext", namespaces=_NS)
        if (
            len(offset) != 1
            or len(extent) != 1
            or [child.tag for child in transforms[0]]
            != [
                f"{{{DRAWING_NS}}}{name}"
                for name in (
                    ["off", "ext", "chOff", "chExt"] if kind == "grpSp" else ["off", "ext"]
                )
            ]
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This object does not use a supported slide-level transform.",
            )
        return offset[0], extent[0]

    @staticmethod
    def _duplicate_geometry(
        geometry: FidelityGeometry,
        *,
        slide_width_emu: int,
        slide_height_emu: int,
    ) -> FidelityGeometry:
        offsets = (
            (_DUPLICATE_OFFSET_EMU, _DUPLICATE_OFFSET_EMU),
            (_DUPLICATE_OFFSET_EMU, -_DUPLICATE_OFFSET_EMU),
            (-_DUPLICATE_OFFSET_EMU, _DUPLICATE_OFFSET_EMU),
            (-_DUPLICATE_OFFSET_EMU, -_DUPLICATE_OFFSET_EMU),
            (0, _DUPLICATE_OFFSET_EMU),
            (_DUPLICATE_OFFSET_EMU, 0),
            (0, -_DUPLICATE_OFFSET_EMU),
            (-_DUPLICATE_OFFSET_EMU, 0),
        )
        for x_offset, y_offset in offsets:
            x_emu = geometry.x_emu + x_offset
            y_emu = geometry.y_emu + y_offset
            if (
                0 <= x_emu
                and 0 <= y_emu
                and x_emu + geometry.width_emu <= slide_width_emu
                and y_emu + geometry.height_emu <= slide_height_emu
            ):
                return FidelityGeometry(
                    x_emu=x_emu,
                    y_emu=y_emu,
                    width_emu=geometry.width_emu,
                    height_emu=geometry.height_emu,
                )
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "There is not enough room to place a visible in-bounds duplicate.",
        )

    @staticmethod
    def _duplicate_object_name(root: etree._Element, source_name: str) -> str:
        existing_names = {
            name.casefold()
            for name in root.xpath(".//p:cNvPr/@name", namespaces=_NS)
            if isinstance(name, str)
        }
        for suffix_number in range(1, len(existing_names) + 2):
            suffix = " copy" if suffix_number == 1 else f" copy {suffix_number}"
            base_name = source_name[: 256 - len(suffix)].rstrip()
            candidate = f"{base_name}{suffix}"
            if candidate.casefold() not in existing_names:
                return candidate
        raise CoreDomainError(
            "PRESENTATION_EDIT_RESOURCE_LIMIT",
            "The slide cannot allocate a unique object name.",
        )

    @staticmethod
    def _write_revised_shape_creation_package(
        source_path: Path,
        destination_path: Path,
        *,
        document_id: str,
        expected_sha256: str,
        expected_byte_size: int,
        slide_id: str,
        expected_slide_ids: list[str],
        shape_type: str,
        geometry: FidelityGeometry,
        replacement_style: dict[str, Any],
    ) -> str:
        """Add one simple direct-color shape without changing other package parts."""
        if shape_type not in {"rect", "ellipse"}:
            raise invalid_request("shape_type must be rect or ellipse.", field="shape_type")
        expected_name = {"rect": "Rectangle", "ellipse": "Ellipse"}[shape_type]
        fill_color = replacement_style["fill_color"].removeprefix("#")
        line_color = replacement_style["line_color"].removeprefix("#")

        with source_path.open("rb") as source_handle:
            if os.fstat(source_handle.fileno()).st_size != expected_byte_size:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its revision record.",
                )
            fidelity = inspect_pptx_snapshot(
                source_handle,
                document_id=document_id,
                expected_sha256=expected_sha256,
                byte_size=expected_byte_size,
            )
        source_slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
        if (
            source_slide is None
            or [item.slide_id for item in fidelity.slides] != expected_slide_ids
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
            )
        PresentationEditService._validate_geometry_bounds(
            geometry,
            slide_width_emu=fidelity.slide_width_emu,
            slide_height_emu=fidelity.slide_height_emu,
            field="geometry",
        )
        if fidelity.object_count >= OBJECT_LIMIT:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "This presentation cannot contain another object safely.",
            )

        try:
            with _verified_source_archive(
                source_path,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            ) as source_archive:
                infos = source_archive.infolist()
                members = {info.filename: info for info in infos}
                if (
                    len(infos) > 2_048
                    or len(members) != len(infos)
                    or len({name.casefold() for name in members}) != len(members)
                ):
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "This presentation contains an unsupported or invalid package structure.",
                    )
                slide_info = members.get(source_slide.part_name)
                if slide_info is None:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
                        "The selected slide package part is missing.",
                    )
                slide_root = _parse_xml_part(source_archive, slide_info)
                shape_trees = slide_root.xpath("./p:cSld/p:spTree", namespaces=_NS)
                if len(shape_trees) != 1:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide does not use a supported shape-tree structure.",
                    )
                shape_tree = shape_trees[0]
                new_shape_id = _next_ooxml_shape_id(shape_tree)
                existing_names = {
                    value.casefold()
                    for value in shape_tree.xpath(".//p:cNvPr/@name", namespaces=_NS)
                    if value
                }
                shape_name = ""
                for suffix in range(1, len(existing_names) + 2):
                    candidate_name = expected_name if suffix == 1 else f"{expected_name} {suffix}"
                    if candidate_name.casefold() not in existing_names:
                        shape_name = candidate_name
                        break
                if not shape_name:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "This slide cannot allocate another safe object name.",
                    )

                shape = etree.Element(f"{{{PRESENTATION_NS}}}sp")
                nonvisual = etree.SubElement(shape, f"{{{PRESENTATION_NS}}}nvSpPr")
                properties = etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvPr")
                properties.set("id", new_shape_id)
                properties.set("name", shape_name)
                etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvSpPr")
                etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}nvPr")

                shape_properties = etree.SubElement(shape, f"{{{PRESENTATION_NS}}}spPr")
                transform = etree.SubElement(shape_properties, f"{{{DRAWING_NS}}}xfrm")
                offset = etree.SubElement(transform, f"{{{DRAWING_NS}}}off")
                offset.set("x", str(geometry.x_emu))
                offset.set("y", str(geometry.y_emu))
                extent = etree.SubElement(transform, f"{{{DRAWING_NS}}}ext")
                extent.set("cx", str(geometry.width_emu))
                extent.set("cy", str(geometry.height_emu))
                preset = etree.SubElement(shape_properties, f"{{{DRAWING_NS}}}prstGeom")
                preset.set("prst", shape_type)
                etree.SubElement(preset, f"{{{DRAWING_NS}}}avLst")
                fill = etree.SubElement(shape_properties, f"{{{DRAWING_NS}}}solidFill")
                etree.SubElement(fill, f"{{{DRAWING_NS}}}srgbClr", val=fill_color)
                line = etree.SubElement(shape_properties, f"{{{DRAWING_NS}}}ln")
                line.set("w", "12700")
                line_fill = etree.SubElement(line, f"{{{DRAWING_NS}}}solidFill")
                etree.SubElement(line_fill, f"{{{DRAWING_NS}}}srgbClr", val=line_color)

                extension_lists = shape_tree.xpath("./p:extLst", namespaces=_NS)
                element_children = [child for child in shape_tree if isinstance(child.tag, str)]
                if len(extension_lists) > 1 or (
                    extension_lists and element_children[-1] is not extension_lists[0]
                ):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "This slide has an unsupported shape-tree extension structure.",
                    )
                insertion_index = (
                    shape_tree.index(extension_lists[0]) if extension_lists else len(shape_tree)
                )
                shape_tree.insert(insertion_index, shape)
                rewritten_slide = etree.tostring(
                    slide_root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                if len(rewritten_slide) > _MAX_XML_PART_BYTES:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_RESOURCE_LIMIT",
                        "The edited slide is larger than the safe editing limit.",
                    )
                with zipfile.ZipFile(destination_path, "w", allowZip64=True) as output_archive:
                    output_archive.comment = source_archive.comment
                    for info in infos:
                        copied_info = copy.copy(info)
                        if info.filename == source_slide.part_name:
                            output_archive.writestr(copied_info, rewritten_slide)
                            continue
                        with source_archive.open(info, "r") as input_member:
                            with output_archive.open(
                                copied_info, "w", force_zip64=False
                            ) as output_member:
                                shutil.copyfileobj(
                                    input_member,
                                    output_member,
                                    length=_COPY_CHUNK_BYTES,
                                )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_PACKAGE_INVALID",
                "The presentation could not be safely rewritten.",
            ) from error

        if destination_path.stat().st_size > MAX_SOURCE_BYTES:
            raise CoreDomainError(
                "PRESENTATION_EDIT_RESOURCE_LIMIT",
                "The edited presentation exceeds the safe size limit.",
            )
        preflight_source(destination_path, "pptx")
        digest = PresentationEditService._sha256_path(destination_path)
        with destination_path.open("rb") as output_handle:
            revised_fidelity = inspect_pptx_snapshot(
                output_handle,
                document_id=document_id,
                expected_sha256=digest,
                byte_size=destination_path.stat().st_size,
            )
        revised_slide = next(
            (item for item in revised_fidelity.slides if item.slide_id == slide_id), None
        )
        new_object = (
            revised_slide.objects[-1]
            if revised_slide is not None
            and len(revised_slide.objects) == len(source_slide.objects) + 1
            else None
        )
        new_style = new_object.shape_style if new_object is not None else None
        if (
            [item.slide_id for item in revised_fidelity.slides] != expected_slide_ids
            or revised_slide is None
            or new_object is None
            or new_object.ooxml_id != new_shape_id
            or new_object.name != shape_name
            or new_object.kind != "sp"
            or new_object.geometry != geometry
            or not new_object.geometry_editable
            or not new_object.delete_editable
            or new_style is None
            or not new_style.editable
            or new_style.fill_color != f"#{fill_color}"
            or new_style.line_color != f"#{line_color}"
            or new_object.object_id in {item.object_id for item in source_slide.objects}
            or revised_slide.objects[:-1] != source_slide.objects
            or revised_slide.part_name != source_slide.part_name
            or revised_slide.speaker_notes != source_slide.speaker_notes
            or revised_slide.speaker_notes_editable != source_slide.speaker_notes_editable
            or any(
                original != revised
                for original, revised in zip(fidelity.slides, revised_fidelity.slides, strict=True)
                if original.slide_id != slide_id
            )
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The new shape did not pass validation.",
            )

        try:
            with (
                _verified_source_archive(
                    source_path,
                    expected_sha256=expected_sha256,
                    expected_byte_size=expected_byte_size,
                ) as source_archive,
                zipfile.ZipFile(destination_path, "r") as output_archive,
            ):
                output_names = {info.filename for info in output_archive.infolist()}
                if output_names != set(members):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_VALIDATION_FAILED",
                        "Adding the shape changed the package member list unexpectedly.",
                    )
                revised_slide_root = etree.fromstring(output_archive.read(source_slide.part_name))
                revised_shape = PresentationEditService._find_object_node(
                    revised_slide_root,
                    ooxml_id=new_object.ooxml_id,
                    kind="sp",
                )
                revised_presets = revised_shape.xpath("./p:spPr/a:prstGeom/@prst", namespaces=_NS)
                if revised_presets != [shape_type]:
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_VALIDATION_FAILED",
                        "The created shape type did not pass package validation.",
                    )
                for member_name in set(members) - {source_slide.part_name}:
                    if source_archive.read(member_name) != output_archive.read(member_name):
                        raise CoreDomainError(
                            "PRESENTATION_EDIT_VALIDATION_FAILED",
                            "Adding the shape changed an unrelated presentation part.",
                        )
        except CoreDomainError:
            raise
        except (
            OSError,
            EOFError,
            KeyError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            etree.XMLSyntaxError,
        ) as error:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The new shape package could not be verified.",
            ) from error
        return new_object.object_id

    @staticmethod
    def _find_object_node(root: etree._Element, *, ooxml_id: str, kind: str) -> etree._Element:
        if kind == "sp":
            selector = "./p:cSld/p:spTree/p:sp"
            nonvisual_selector = "./p:nvSpPr/p:cNvPr"
        elif kind == "pic":
            selector = "./p:cSld/p:spTree/p:pic"
            nonvisual_selector = "./p:nvPicPr/p:cNvPr"
        elif kind == "grpSp":
            selector = "./p:cSld/p:spTree/p:grpSp"
            nonvisual_selector = "./p:nvGrpSpPr/p:cNvPr"
        elif kind == "graphicFrame":
            selector = "./p:cSld/p:spTree/p:graphicFrame"
            nonvisual_selector = "./p:nvGraphicFramePr/p:cNvPr"
        else:
            raise CoreDomainError(
                "PRESENTATION_EDIT_UNSUPPORTED",
                "This object does not use a supported slide-level shape or picture.",
            )
        matches = []
        for candidate in root.xpath(selector, namespaces=_NS):
            nonvisual = candidate.xpath(nonvisual_selector, namespaces=_NS)
            if len(nonvisual) == 1 and nonvisual[0].get("id") == ooxml_id:
                matches.append(candidate)
        if len(matches) != 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected object is unavailable."
            )
        return matches[0]

    @staticmethod
    def _find_shape(root: etree._Element, ooxml_id: str) -> etree._Element:
        matches = []
        for shape in root.xpath(".//p:sp", namespaces=_NS):
            nonvisual = shape.xpath("./p:nvSpPr/p:cNvPr", namespaces=_NS)
            if len(nonvisual) == 1 and nonvisual[0].get("id") == ooxml_id:
                matches.append(shape)
        if len(matches) != 1:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected text shape is unavailable."
            )
        return matches[0]

    @staticmethod
    def _sha256_path(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(_COPY_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _unlink_managed(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _revision_conflict() -> CoreDomainError:
        return CoreDomainError(
            "PRESENTATION_REVISION_CONFLICT",
            "The current presentation revision changed. Refresh the preview and try again.",
            retryable=True,
        )

    @staticmethod
    def _project_id(value: Any) -> str:
        if not isinstance(value, str):
            raise invalid_request("project_id must be a UUID4.", field="project_id")
        return normalize_project_id(value)

    @staticmethod
    def _document_id(value: Any) -> str:
        if not isinstance(value, str):
            raise invalid_request("document_id must be a UUID.", field="document_id")
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request("document_id must be a UUID.", field="document_id") from error

    @staticmethod
    def _uuid_field(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be a UUID.", field=field)
        try:
            return str(uuid.UUID(value))
        except ValueError as error:
            raise invalid_request(f"{field} must be a UUID.", field=field) from error

    @staticmethod
    def _text_field(value: Any, field: str, *, allow_newlines: bool = False) -> str:
        if not isinstance(value, str) or len(value) > _MAX_TEXT_CHARS:
            raise invalid_request(
                f"{field} must be text no longer than {_MAX_TEXT_CHARS} characters.",
                field=field,
            )
        if any(
            (
                ord(character) < 32
                and character != "\t"
                and not (allow_newlines and character == "\n")
            )
            or 0xD800 <= ord(character) <= 0xDFFF
            for character in value
        ):
            raise invalid_request(f"{field} contains unsupported characters.", field=field)
        return value

    @staticmethod
    def _text_style_field(value: Any) -> dict[str, Any]:
        names = {
            "bold",
            "italic",
            "underline",
            "strikethrough",
            "font_family",
            "font_size_pt",
            "font_color",
            "alignment",
            "bullet_mode",
            "bullet_color",
            "bullet_size_percent",
            "numbering_start",
            "left_indent_pt",
            "first_line_indent_pt",
            "line_spacing_pt",
            "space_before_pt",
            "space_after_pt",
        }
        if not isinstance(value, dict):
            raise invalid_request("replacement_style must be an object.", field="replacement_style")
        reject_unknown_fields(value, names)
        if not value:
            raise invalid_request(
                "replacement_style must change at least one supported property.",
                field="replacement_style",
            )
        result: dict[str, Any] = {}
        for name, item in value.items():
            if name in {"bold", "italic", "underline", "strikethrough"}:
                if type(item) is not bool:
                    raise invalid_request(
                        f"replacement_style.{name} must be a boolean.",
                        field=f"replacement_style.{name}",
                    )
                result[name] = item
            elif name == "font_family":
                if not isinstance(item, str) or not (
                    item in {"+mn-lt", "+mj-lt"}
                    or re.fullmatch(r"[^\x00-\x1f\x7f<>\"&+\s][^\x00-\x1f\x7f<>\"&]{0,30}", item)
                    and item == item.strip()
                ):
                    raise invalid_request(
                        "replacement_style.font_family must be a font name of up to 31 "
                        "characters, +mn-lt or +mj-lt.",
                        field="replacement_style.font_family",
                    )
                result[name] = item
            elif name == "font_size_pt":
                if type(item) is not int or not 6 <= item <= 96:
                    raise invalid_request(
                        "replacement_style.font_size_pt must be an integer from 6 to 96.",
                        field="replacement_style.font_size_pt",
                    )
                result[name] = item
            elif name == "alignment":
                if not isinstance(item, str) or item not in {
                    "left",
                    "center",
                    "right",
                    "justify",
                }:
                    raise invalid_request(
                        "replacement_style.alignment must be left, center, right, or justify.",
                        field="replacement_style.alignment",
                    )
                result[name] = item
            elif name == "bullet_mode":
                if not isinstance(item, str) or item not in PARAGRAPH_BULLET_MODES:
                    raise invalid_request(
                        "replacement_style.bullet_mode must be a supported paragraph bullet mode.",
                        field="replacement_style.bullet_mode",
                    )
                result[name] = item
            elif name == "bullet_color":
                if not isinstance(item, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", item):
                    raise invalid_request(
                        "replacement_style.bullet_color must be a #RRGGBB color.",
                        field="replacement_style.bullet_color",
                    )
                result[name] = item.upper()
            elif name == "numbering_start":
                if type(item) is not int or not 1 <= item <= MAX_NUMBERING_START:
                    raise invalid_request(
                        "replacement_style.numbering_start must be an integer from 1 to 9999.",
                        field="replacement_style.numbering_start",
                    )
                result[name] = item
            elif name == "bullet_size_percent":
                if (
                    type(item) is not int
                    or not MIN_BULLET_SIZE_PERCENT <= item <= MAX_BULLET_SIZE_PERCENT
                ):
                    raise invalid_request(
                        "replacement_style.bullet_size_percent must be an integer from 25 to 400.",
                        field="replacement_style.bullet_size_percent",
                    )
                result[name] = item
            elif name == "left_indent_pt":
                if type(item) is not int or not 0 <= item <= MAX_TEXT_LEFT_INDENT_PT:
                    raise invalid_request(
                        "replacement_style.left_indent_pt must be an integer from 0 to 144.",
                        field="replacement_style.left_indent_pt",
                    )
                result[name] = item
            elif name == "first_line_indent_pt":
                if (
                    type(item) is not int
                    or not -MAX_TEXT_FIRST_LINE_INDENT_PT <= item <= MAX_TEXT_FIRST_LINE_INDENT_PT
                ):
                    raise invalid_request(
                        "replacement_style.first_line_indent_pt must be an integer "
                        "from -144 to 144.",
                        field="replacement_style.first_line_indent_pt",
                    )
                result[name] = item
            elif name == "line_spacing_pt":
                if type(item) is not int or not 1 <= item <= MAX_TEXT_LINE_SPACING_PT:
                    raise invalid_request(
                        "replacement_style.line_spacing_pt must be an integer from 1 to 144.",
                        field="replacement_style.line_spacing_pt",
                    )
                result[name] = item
            elif name in {"space_before_pt", "space_after_pt"}:
                if type(item) is not int or not 0 <= item <= MAX_TEXT_PARAGRAPH_SPACING_PT:
                    raise invalid_request(
                        f"replacement_style.{name} must be an integer from 0 to 144.",
                        field=f"replacement_style.{name}",
                    )
                result[name] = item
            else:
                if not isinstance(item, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", item):
                    raise invalid_request(
                        "replacement_style.font_color must use #RRGGBB format.",
                        field="replacement_style.font_color",
                    )
                result[name] = item.upper()
        return result

    @staticmethod
    def _shape_style_field(value: Any) -> dict[str, Any]:
        names = {"fill_color", "line_color", "line_width_pt", "line_dash"}
        if not isinstance(value, dict):
            raise invalid_request("replacement_style must be an object.", field="replacement_style")
        reject_unknown_fields(value, names)
        if not value:
            raise invalid_request(
                "replacement_style must change at least one supported property.",
                field="replacement_style",
            )
        result: dict[str, Any] = {}
        for name, color in value.items():
            if name == "line_width_pt":
                if (
                    isinstance(color, bool)
                    or not isinstance(color, (int, float))
                    or not 0.25 <= color <= MAX_SHAPE_LINE_WIDTH_PT
                    or round(color * 4) != color * 4
                ):
                    raise invalid_request(
                        "replacement_style.line_width_pt must be 0.25 to 20 in 0.25 steps.",
                        field="replacement_style.line_width_pt",
                    )
                result[name] = float(color)
                continue
            if name == "line_dash":
                if not isinstance(color, str) or color not in SHAPE_LINE_DASHES:
                    raise invalid_request(
                        "replacement_style.line_dash must be a supported dash style.",
                        field="replacement_style.line_dash",
                    )
                result[name] = color
                continue
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
                raise invalid_request(
                    f"replacement_style.{name} must use #RRGGBB format.",
                    field=f"replacement_style.{name}",
                )
            result[name] = color.upper()
        return result

    @staticmethod
    def _replacement_image_field(value: Any) -> tuple[bytes, str]:
        max_encoded_bytes = ((_MAX_REPLACEMENT_IMAGE_BYTES + 2) // 3) * 4
        if not isinstance(value, str) or not value or len(value) > max_encoded_bytes:
            raise invalid_request(
                "image_base64 must encode a PNG or JPEG no larger than 4 MiB.",
                field="image_base64",
            )
        try:
            image_bytes = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise invalid_request(
                "image_base64 must contain valid base64 image data.", field="image_base64"
            ) from error
        if (
            not image_bytes
            or len(image_bytes) > _MAX_REPLACEMENT_IMAGE_BYTES
            or base64.b64encode(image_bytes).decode("ascii") != value
        ):
            raise invalid_request(
                "image_base64 must encode a PNG or JPEG no larger than 4 MiB.",
                field="image_base64",
            )

        image_format: str | None = None
        width = 0
        height = 0
        frame_count = 0
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image_format = image.format
                width, height = image.size
                frame_count = getattr(image, "n_frames", 1)
        except Exception as error:
            raise invalid_request(
                "image_base64 must contain a complete, decodable PNG or JPEG.",
                field="image_base64",
            ) from error

        if (
            image_format not in {"PNG", "JPEG"}
            or frame_count != 1
            or not 1 <= width <= _MAX_REPLACEMENT_IMAGE_DIMENSION
            or not 1 <= height <= _MAX_REPLACEMENT_IMAGE_DIMENSION
            or width * height > _MAX_REPLACEMENT_IMAGE_PIXELS
        ):
            raise invalid_request(
                "The image must be a single-frame PNG or JPEG with dimensions "
                "no larger than 8192 × 8192 pixels or 20 megapixels.",
                field="image_base64",
            )

        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.verify()
            with Image.open(io.BytesIO(image_bytes)) as decoded_image:
                decoded_image.load()
        except Exception as error:
            raise invalid_request(
                "image_base64 must contain a complete, decodable PNG or JPEG.",
                field="image_base64",
            ) from error
        return image_bytes, image_format

    @staticmethod
    def _speaker_notes_field(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise invalid_request(f"{field} must be text.", field=field)
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        if len(normalized) > MAX_SPEAKER_NOTES_CHARS:
            raise invalid_request(
                f"{field} must be no longer than {MAX_SPEAKER_NOTES_CHARS} characters.",
                field=field,
            )
        if any(
            (ord(character) < 32 and character not in {"\t", "\n"})
            or 0xD800 <= ord(character) <= 0xDFFF
            for character in normalized
        ):
            raise invalid_request(f"{field} contains unsupported characters.", field=field)
        return normalized

    @staticmethod
    def _geometry_field(value: Any, field: str) -> FidelityGeometry:
        names = {"x_emu", "y_emu", "width_emu", "height_emu"}
        if not isinstance(value, dict) or set(value) != names:
            raise invalid_request(
                f"{field} must contain x_emu, y_emu, width_emu, and height_emu.",
                field=field,
            )
        coordinates = [value[name] for name in ("x_emu", "y_emu", "width_emu", "height_emu")]
        if any(type(number) is not int for number in coordinates):
            raise invalid_request(f"{field} coordinates must be integers.", field=field)
        x_emu, y_emu, width_emu, height_emu = coordinates
        if (
            x_emu < 0
            or y_emu < 0
            or width_emu <= 0
            or height_emu <= 0
            or any(number > MAX_SLIDE_DIMENSION_EMU for number in coordinates)
        ):
            raise invalid_request(
                f"{field} must use positive dimensions within the safe slide-size limit.",
                field=field,
            )
        return FidelityGeometry(x_emu, y_emu, width_emu, height_emu)

    @staticmethod
    def _picture_crop_field(value: Any, field: str) -> FidelityPictureCrop:
        names = (
            "left_percent",
            "right_percent",
            "top_percent",
            "bottom_percent",
        )
        if not isinstance(value, dict) or set(value) != set(names):
            raise invalid_request(
                f"{field} must contain all four edge percentages: "
                "left_percent, right_percent, top_percent, and bottom_percent.",
                field=field,
            )
        normalized: dict[str, int] = {}
        for name in names:
            supplied = value[name]
            if isinstance(supplied, bool) or not isinstance(supplied, (int, float)):
                raise invalid_request(
                    f"{field}.{name} must be a finite percentage.",
                    field=f"{field}.{name}",
                )
            try:
                percentage = float(supplied)
            except (OverflowError, ValueError) as error:
                raise invalid_request(
                    f"{field}.{name} must be a finite percentage.",
                    field=f"{field}.{name}",
                ) from error
            if not math.isfinite(percentage):
                raise invalid_request(
                    f"{field}.{name} must be a finite percentage.",
                    field=f"{field}.{name}",
                )
            scaled = percentage * 1_000
            units = round(scaled)
            if not 0 <= units < 100_000 or abs(scaled - units) > 1e-6:
                raise invalid_request(
                    f"{field}.{name} must use 0 through 99.999 percent in increments of 0.001.",
                    field=f"{field}.{name}",
                )
            normalized[name] = units
        if (
            normalized["left_percent"] + normalized["right_percent"] >= 100_000
            or normalized["top_percent"] + normalized["bottom_percent"] >= 100_000
        ):
            raise invalid_request(
                f"{field} must leave a visible image area in both directions.",
                field=field,
            )
        return FidelityPictureCrop(
            left=normalized["left_percent"],
            right=normalized["right_percent"],
            top=normalized["top_percent"],
            bottom=normalized["bottom_percent"],
        )

    @staticmethod
    def _validate_geometry_bounds(
        geometry: FidelityGeometry,
        *,
        slide_width_emu: int,
        slide_height_emu: int,
        field: str,
    ) -> None:
        if (
            geometry.x_emu + geometry.width_emu > slide_width_emu
            or geometry.y_emu + geometry.height_emu > slide_height_emu
        ):
            raise invalid_request(
                f"{field} must stay within the current slide bounds.",
                field=field,
            )
