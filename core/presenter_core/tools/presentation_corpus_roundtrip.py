"""Exercise one reversible text edit and export per supported local corpus deck."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageChops

from presenter_core.errors import CoreDomainError
from presenter_core.ingestion.parsers.utils import lexical_normalize
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import FidelityDocument, inspect_pptx_snapshot
from presenter_core.presentation.native_pdf import validate_native_source

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPOSITORY_ROOT / "docs" / "PRESENTATION_WORKSPACE" / "corpus-manifest.json"
CORPUS_ROOT = REPOSITORY_ROOT / ".local" / "presentation-workspace-corpus"
POWERPOINT_RENDER_WIDTH = 1280
POWERPOINT_RENDER_HEIGHT = 720
MAX_POWERPOINT_RENDER_DIMENSION = 2048
_LEXICAL_WORD_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_LEXICAL_JOINERS = frozenset("._/%+-")


class AcceptanceFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _initialize_com_apartment() -> Any:
    # Pywin32 skips repeated initialization on its main thread. Use the native
    # reference count so releasing this validator never tears down caller COM.
    apartment = ctypes.WinDLL("ole32")
    apartment.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    apartment.CoInitializeEx.restype = ctypes.c_long
    apartment.CoUninitialize.argtypes = []
    apartment.CoUninitialize.restype = None
    result = apartment.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
    if result < 0:
        raise OSError("Cannot initialize the Office acceptance COM apartment")
    return apartment


class PowerPointOpenValidator:
    """Use private read-only copies without changing a shared PowerPoint application."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise AcceptanceFailure("POWERPOINT_AUTOMATION_UNAVAILABLE")
        self._com_apartment: Any | None = None
        self._application: Any | None = None
        try:
            from win32com.client import DispatchEx  # type: ignore[import-untyped]

            self._com_apartment = _initialize_com_apartment()
            self._application = DispatchEx("PowerPoint.Application")
        except Exception as error:
            self._application = None
            if self._com_apartment is not None:
                self._com_apartment.CoUninitialize()
                self._com_apartment = None
            raise AcceptanceFailure("POWERPOINT_AUTOMATION_UNAVAILABLE") from error

    def open_read_only(self, path: Path, expected_slide_count: int) -> int:
        application = self._application
        if application is None:
            raise AcceptanceFailure("POWERPOINT_AUTOMATION_UNAVAILABLE")
        with _opened_powerpoint_copy(application, path, expected_slide_count) as presentation:
            return int(presentation.Slides.Count)

    def compare_rendered_exports(
        self,
        original_path: Path,
        edited_path: Path,
        expected_slide_count: int,
        edited_slide_number: int,
        target_geometry: dict[str, Any] | None,
        slide_width_emu: int,
        slide_height_emu: int,
    ) -> dict[str, Any]:
        """Compare Office-rendered pixels without displaying or retaining slide images."""
        original_hash = _sha256(original_path)
        edited_hash = _sha256(edited_path)
        if _external_non_hyperlink_relationship_count(original_path) or (
            _external_non_hyperlink_relationship_count(edited_path)
        ):
            raise AcceptanceFailure("POWERPOINT_EXTERNAL_CONTENT_BLOCKED")
        application = self._application
        if application is None:
            raise AcceptanceFailure("POWERPOINT_AUTOMATION_UNAVAILABLE")

        with tempfile.TemporaryDirectory(prefix="presenter-copilot-office-visual-") as value:
            root = Path(value)
            original_images = self._render_slides(
                application,
                original_path,
                root / "original",
                expected_slide_count,
            )
            edited_images = self._render_slides(
                application,
                edited_path,
                root / "edited",
                expected_slide_count,
            )
            repeated_original_images = self._render_slides(
                application,
                original_path,
                root / "original-repeat",
                expected_slide_count,
            )
            repeated_edited_images = self._render_slides(
                application,
                edited_path,
                root / "edited-repeat",
                expected_slide_count,
            )
            target_changed_pixels = 0
            target_diff_bounds: tuple[int, int, int, int] | None = None
            nondeterministic_slides: list[int] = []
            unstable_pixel_counts: list[dict[str, int]] = []
            changed_untouched_slides: list[dict[str, Any]] = []
            target_geometry_check = "unavailable"
            target_allowed_diff_bounds: tuple[int, int, int, int] | None = None
            for slide_number, (
                original_image,
                repeated_original_image,
                edited_image,
                repeated_edited_image,
            ) in enumerate(
                zip(
                    original_images,
                    repeated_original_images,
                    edited_images,
                    repeated_edited_images,
                    strict=True,
                ),
                start=1,
            ):
                try:
                    with Image.open(original_image) as original:
                        original_pixels = original.convert("RGB")
                    with Image.open(repeated_original_image) as repeated_original:
                        repeated_original_pixels = repeated_original.convert("RGB")
                    with Image.open(edited_image) as edited:
                        edited_pixels = edited.convert("RGB")
                    with Image.open(repeated_edited_image) as repeated_edited:
                        repeated_edited_pixels = repeated_edited.convert("RGB")
                except OSError as error:
                    raise AcceptanceFailure("POWERPOINT_RENDER_INVALID") from error
                (
                    stable_diff_mask,
                    source_unstable_pixels,
                    edited_unstable_pixels,
                    unstable_pixels,
                ) = _stable_rendered_difference_mask(
                    original_pixels,
                    repeated_original_pixels,
                    edited_pixels,
                    repeated_edited_pixels,
                )
                if unstable_pixels:
                    nondeterministic_slides.append(slide_number)
                    unstable_pixel_counts.append(
                        {
                            "slide_number": slide_number,
                            "unstable_pixels": unstable_pixels,
                            "source_unstable_pixels": source_unstable_pixels,
                            "edited_unstable_pixels": edited_unstable_pixels,
                        }
                    )
                changed_pixels, bounds = _pixel_mask_summary(stable_diff_mask)
                if slide_number == edited_slide_number:
                    target_changed_pixels = changed_pixels
                    target_diff_bounds = bounds
                    if target_geometry is not None:
                        target_allowed_diff_bounds = self._target_diff_allowed_bounds(
                            target_geometry,
                            slide_width_emu,
                            slide_height_emu,
                        )
                        try:
                            self._validate_target_diff_bounds(
                                bounds,
                                target_allowed_diff_bounds,
                            )
                            target_geometry_check = "inside"
                        except AcceptanceFailure as error:
                            if error.code != "POWERPOINT_EDIT_VISUAL_ESCAPED_TARGET":
                                raise
                            target_geometry_check = "outside"
                elif changed_pixels:
                    changed_untouched_slides.append(
                        {
                            "slide_number": slide_number,
                            "changed_pixels": changed_pixels,
                            "diff_bounds": list(bounds) if bounds is not None else None,
                        }
                    )

        if _sha256(original_path) != original_hash or _sha256(edited_path) != edited_hash:
            raise AcceptanceFailure("POWERPOINT_CHANGED_READ_ONLY_EXPORT")

        return {
            "status": (
                "needs_review"
                if changed_untouched_slides
                or target_changed_pixels == 0
                or target_geometry_check != "inside"
                else "passed_with_dynamic_regions_masked"
                if nondeterministic_slides
                else "passed"
            ),
            "rendered_slide_count": expected_slide_count,
            "renderer_nondeterministic_slides": nondeterministic_slides,
            "renderer_unstable_pixel_counts": unstable_pixel_counts,
            "untouched_slides_with_pixel_diff": changed_untouched_slides,
            "edited_slide_changed_pixels": target_changed_pixels,
            "edited_slide_change_visible": bool(target_changed_pixels),
            "edited_target_geometry_check": target_geometry_check,
            "edited_slide_diff_bounds": list(target_diff_bounds)
            if target_diff_bounds is not None
            else None,
            "edited_target_allowed_diff_bounds_px": list(target_allowed_diff_bounds)
            if target_allowed_diff_bounds is not None
            else None,
        }

    @staticmethod
    def _render_slides(
        application: Any,
        path: Path,
        output_directory: Path,
        expected_slide_count: int,
        slide_dimensions: list[tuple[int, int]] | None = None,
    ) -> list[Path]:
        if _external_non_hyperlink_relationship_count(path):
            raise AcceptanceFailure("POWERPOINT_EXTERNAL_CONTENT_BLOCKED")
        if slide_dimensions is not None and len(slide_dimensions) != expected_slide_count:
            raise AcceptanceFailure("POWERPOINT_RENDER_DIMENSIONS_INVALID")
        output_directory.mkdir(parents=True, exist_ok=True)
        try:
            with _opened_powerpoint_copy(application, path, expected_slide_count) as presentation:
                rendered: list[Path] = []
                for slide_number in range(1, expected_slide_count + 1):
                    width, height = (
                        slide_dimensions[slide_number - 1]
                        if slide_dimensions is not None
                        else (POWERPOINT_RENDER_WIDTH, POWERPOINT_RENDER_HEIGHT)
                    )
                    if (
                        isinstance(width, bool)
                        or not isinstance(width, int)
                        or isinstance(height, bool)
                        or not isinstance(height, int)
                        or width < 1
                        or height < 1
                        or width > MAX_POWERPOINT_RENDER_DIMENSION
                        or height > MAX_POWERPOINT_RENDER_DIMENSION
                    ):
                        raise AcceptanceFailure("POWERPOINT_RENDER_DIMENSIONS_INVALID")
                    image_path = output_directory / f"slide-{slide_number:04}.png"
                    presentation.Slides.Item(slide_number).Export(
                        str(image_path),
                        "PNG",
                        width,
                        height,
                    )
                    if not image_path.is_file():
                        raise AcceptanceFailure("POWERPOINT_RENDER_MISSING")
                    rendered.append(image_path)
                return rendered
        except AcceptanceFailure:
            raise
        except Exception as error:
            raise AcceptanceFailure("POWERPOINT_RENDER_FAILED") from error

    @staticmethod
    def _target_diff_allowed_bounds(
        geometry: dict[str, Any] | None,
        slide_width_emu: int,
        slide_height_emu: int,
    ) -> tuple[int, int, int, int] | None:
        if geometry is None:
            return None
        values = (
            geometry.get("x_emu"),
            geometry.get("y_emu"),
            geometry.get("width_emu"),
            geometry.get("height_emu"),
        )
        if (
            any(isinstance(value, bool) or not isinstance(value, int) for value in values)
            or slide_width_emu <= 0
            or slide_height_emu <= 0
        ):
            raise AcceptanceFailure("POWERPOINT_TARGET_GEOMETRY_INVALID")
        x_emu, y_emu, width_emu, height_emu = cast(
            tuple[int, int, int, int],
            values,
        )
        left = math.floor(x_emu * POWERPOINT_RENDER_WIDTH / slide_width_emu) - 6
        top = math.floor(y_emu * POWERPOINT_RENDER_HEIGHT / slide_height_emu) - 6
        right = math.ceil((x_emu + width_emu) * POWERPOINT_RENDER_WIDTH / slide_width_emu) + 6
        bottom = math.ceil((y_emu + height_emu) * POWERPOINT_RENDER_HEIGHT / slide_height_emu) + 6
        return (left, top, right, bottom)

    @staticmethod
    def _validate_target_diff_bounds(
        bounds: tuple[int, int, int, int] | None,
        allowed_bounds: tuple[int, int, int, int] | None,
    ) -> None:
        if bounds is None or allowed_bounds is None:
            return
        left, top, right, bottom = allowed_bounds
        diff_left, diff_top, diff_right, diff_bottom = bounds
        if diff_left < left or diff_top < top or diff_right > right or diff_bottom > bottom:
            raise AcceptanceFailure("POWERPOINT_EDIT_VISUAL_ESCAPED_TARGET")

    def close(self) -> None:
        # DispatchEx can attach to an existing application. Never Quit or save
        # its presentations; only _opened_powerpoint_copy closes owned decks.
        self._application = None
        if self._com_apartment is not None:
            apartment, self._com_apartment = self._com_apartment, None
            try:
                apartment.CoUninitialize()
            except Exception as error:
                raise AcceptanceFailure("POWERPOINT_RELEASE_FAILED") from error


@contextmanager
def _opened_powerpoint_copy(
    application: Any,
    path: Path,
    expected_slide_count: int,
) -> Iterator[Any]:
    if path.is_symlink() or path.suffix.casefold() != ".pptx":
        raise AcceptanceFailure("POWERPOINT_SOURCE_INVALID")
    original_hash = _sha256(path)
    if _external_non_hyperlink_relationship_count(path):
        raise AcceptanceFailure("POWERPOINT_EXTERNAL_CONTENT_BLOCKED")
    try:
        count, _, _ = validate_native_source(path, original_hash)
    except CoreDomainError as error:
        code = {
            "PRESENTATION_PDF_ACTIVE_CONTENT": "POWERPOINT_ACTIVE_CONTENT_BLOCKED",
            "PRESENTATION_PDF_EXTERNAL_CONTENT": "POWERPOINT_EXTERNAL_CONTENT_BLOCKED",
            "SOURCE_SNAPSHOT_CHANGED": "POWERPOINT_CHANGED_READ_ONLY_EXPORT",
        }.get(error.code, "POWERPOINT_SOURCE_INVALID")
        raise AcceptanceFailure(code) from error
    if count != expected_slide_count:
        raise AcceptanceFailure("POWERPOINT_SLIDE_COUNT_MISMATCH")
    # A unique path prevents Office returning a user-open original presentation.
    with tempfile.TemporaryDirectory(
        prefix="presenter-copilot-office-copy-",
        ignore_cleanup_errors=True,
    ) as value:
        snapshot = Path(value) / "presentation.pptx"
        shutil.copyfile(path, snapshot)
        if _sha256(snapshot) != original_hash:
            raise AcceptanceFailure("POWERPOINT_CHANGED_READ_ONLY_EXPORT")
        presentation = None
        try:
            try:
                presentation = application.Presentations.Open(
                    str(snapshot),
                    ReadOnly=True,
                    Untitled=False,
                    WithWindow=False,
                )
                if int(presentation.Slides.Count) != expected_slide_count:
                    raise AcceptanceFailure("POWERPOINT_SLIDE_COUNT_MISMATCH")
            except AcceptanceFailure:
                raise
            except Exception as error:
                raise AcceptanceFailure("POWERPOINT_OPEN_FAILED") from error
            yield presentation
        finally:
            try:
                if presentation is not None:
                    presentation.Close()
            except Exception as error:
                raise AcceptanceFailure("POWERPOINT_PRESENTATION_CLOSE_FAILED") from error
            finally:
                if _sha256(snapshot) != original_hash or _sha256(path) != original_hash:
                    raise AcceptanceFailure("POWERPOINT_CHANGED_READ_ONLY_EXPORT")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _call(core: CoreService, method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = core.handle_message(
        {
            "protocol_version": 1,
            "type": "request",
            "request_id": f"corpus-{uuid.uuid4().hex}",
            "method": method,
            "params": params,
        }
    )
    if response.get("ok") is not True:
        error = response.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        raise AcceptanceFailure(code if isinstance(code, str) else "CORE_REQUEST_FAILED")
    result = response.get("result")
    if not isinstance(result, dict):
        raise AcceptanceFailure("CORE_RESULT_INVALID")
    return result


def _checked_snapshot(path: Path, document_id: str) -> Any:
    byte_size = path.stat().st_size
    digest = _sha256(path)
    with path.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=document_id,
            expected_sha256=digest,
            byte_size=byte_size,
        )
    return fidelity


def _package_part_hashes(path: Path) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    with zipfile.ZipFile(path, "r") as archive:
        for info in archive.infolist():
            digest = hashlib.sha256()
            with archive.open(info, "r") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            parts.append((info.filename, digest.hexdigest()))
    return parts


def _external_non_hyperlink_relationship_count(path: Path) -> int:
    """Count external package links Office could resolve while opening a deck."""
    count = 0
    try:
        with zipfile.ZipFile(path, "r") as archive:
            for info in archive.infolist():
                if not info.filename.endswith(".rels"):
                    continue
                try:
                    with archive.open(info, "r") as handle:
                        relationships = ET.parse(handle).getroot()
                except ET.ParseError as error:
                    raise AcceptanceFailure("POWERPOINT_RELATIONSHIPS_INVALID") from error
                for relationship in relationships:
                    if (
                        relationship.attrib.get("TargetMode", "").casefold() == "external"
                        and relationship.attrib.get("Type", "").rsplit("/", 1)[-1] != "hyperlink"
                    ):
                        count += 1
    except AcceptanceFailure:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile) as error:
        raise AcceptanceFailure("POWERPOINT_RELATIONSHIPS_UNREADABLE") from error
    return count


def _binary_pixel_difference(first: Image.Image, second: Image.Image) -> Image.Image:
    if first.size != second.size:
        raise AcceptanceFailure("POWERPOINT_RENDER_DIMENSIONS_CHANGED")
    difference = ImageChops.difference(first.convert("RGB"), second.convert("RGB"))
    red, green, blue = difference.split()
    mask = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    return mask.point(lambda value: 255 if value else 0)


def _pixel_mask_summary(mask: Image.Image) -> tuple[int, tuple[int, int, int, int] | None]:
    return mask.width * mask.height - mask.histogram()[0], mask.getbbox()


def _stable_rendered_difference_mask(
    original_first: Image.Image,
    original_second: Image.Image,
    edited_first: Image.Image,
    edited_second: Image.Image,
) -> tuple[Image.Image, int, int, int]:
    """Compare stable pixels and exclude variation in either rendered state."""
    source_unstable = _binary_pixel_difference(original_first, original_second)
    edited_unstable = _binary_pixel_difference(edited_first, edited_second)
    unstable = ImageChops.lighter(source_unstable, edited_unstable)
    edited_changes = _binary_pixel_difference(original_first, edited_first)
    stable_changes = ImageChops.subtract(edited_changes, unstable)
    source_count, _ = _pixel_mask_summary(source_unstable)
    edited_count, _ = _pixel_mask_summary(edited_unstable)
    unstable_count, _ = _pixel_mask_summary(unstable)
    return stable_changes, source_count, edited_count, unstable_count


def _source_lexical_tokens(fidelity: FidelityDocument) -> set[str]:
    texts = (
        text
        for slide in fidelity.slides
        for text in (
            *(obj.text for obj in slide.objects),
            slide.speaker_notes or "",
        )
    )
    return {token for text in texts for token in lexical_normalize(text).split()}


def _single_character_text_mutation(text: str, existing_tokens: set[str]) -> tuple[str, str] | None:
    """Change one letter to a novel lexical token without changing text length."""
    for match in _LEXICAL_WORD_PATTERN.finditer(text):
        word = match.group()
        if len(word) < 4 or not word.isalpha():
            continue
        if match.start() > 0 and text[match.start() - 1] in _LEXICAL_JOINERS:
            continue
        if match.end() < len(text) and text[match.end()] in _LEXICAL_JOINERS:
            continue
        for position in range(len(word) - 1, -1, -1):
            alphabet = (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                if word[position].isupper()
                else "abcdefghijklmnopqrstuvwxyz"
            )
            for replacement_character in alphabet:
                if replacement_character.casefold() == word[position].casefold():
                    continue
                replacement_word = word[:position] + replacement_character + word[position + 1 :]
                normalized = lexical_normalize(replacement_word).split()
                if len(normalized) == 1 and normalized[0] not in existing_tokens:
                    return (
                        text[: match.start()] + replacement_word + text[match.end() :],
                        normalized[0],
                    )
    return None


def _exercise(
    item: dict[str, Any],
    source: Path,
    powerpoint: PowerPointOpenValidator | None = None,
    office_visual_requested: bool = False,
) -> dict[str, Any]:
    source_hash = _sha256(source)
    office_validation_started = False
    try:
        _checked_snapshot(source, f"preflight-{item['record_id']}")
    except CoreDomainError as error:
        if error.code == "PRESENTATION_FIDELITY_STRUCTURE_INVALID":
            return {
                "record_id": item["record_id"],
                "status": "unsupported",
                "code": error.code,
            }
        return {
            "record_id": item["record_id"],
            "status": "failed",
            "code": error.code,
        }

    with tempfile.TemporaryDirectory(prefix="presenter-copilot-corpus-roundtrip-") as value:
        root = Path(value)
        core = CoreService(data_root=root / "profile")
        opened: dict[str, Any] | None = None
        project_id = ""
        document_id = ""
        try:
            project = _call(core, "project.create", {"name": "Corpus round-trip"})
            project_record = project.get("project")
            if not isinstance(project_record, dict) or not isinstance(
                project_record.get("id"), str
            ):
                raise AcceptanceFailure("PROJECT_CREATE_RESULT_INVALID")
            project_id = project_record["id"]

            imported = _call(
                core,
                "source.import",
                {
                    "project_id": project_id,
                    "path": str(source.resolve()),
                    "kind": "presentation",
                },
            )
            document = imported.get("document")
            if not isinstance(document, dict) or not isinstance(document.get("id"), str):
                raise AcceptanceFailure("PRESENTATION_IMPORT_RESULT_INVALID")
            document_id = document["id"]

            opened = _call(
                core,
                "presentation.workspace.open_source",
                {"project_id": project_id, "document_id": document_id},
            )
            original_revision_id = opened.get("revision_id")
            slide_count = opened.get("fidelity_report", {}).get("slide_count")
            if not isinstance(original_revision_id, str) or not isinstance(slide_count, int):
                raise AcceptanceFailure("PRESENTATION_OPEN_RESULT_INVALID")
            original_fidelity = _checked_snapshot(source, document_id)

            existing_tokens = _source_lexical_tokens(original_fidelity)
            selected: tuple[int, dict[str, Any], str, str, str, str, str, dict[str, int]] | None = (
                None
            )
            for slide_number in range(1, slide_count + 1):
                selection = _call(
                    core,
                    "presentation.workspace.list_text_targets",
                    {
                        "project_id": project_id,
                        "document_id": document_id,
                        "revision_id": original_revision_id,
                        "slide_number": slide_number,
                    },
                )
                targets = selection.get("targets")
                slide_id = selection.get("slide_id")
                if not isinstance(targets, list) or not isinstance(slide_id, str):
                    continue
                source_slide = original_fidelity.slides[slide_number - 1]
                source_objects = {obj.object_id: obj for obj in source_slide.objects}
                for target in targets:
                    current_text = target.get("current_text") if isinstance(target, dict) else None
                    if not isinstance(target, dict):
                        continue
                    if target.get("single_run_editable") is True:
                        edit_method = "presentation.workspace.replace_single_run_text"
                        operation_type = "replace_single_run_text"
                    elif target.get("uniform_run_editable") is True:
                        edit_method = "presentation.workspace.replace_text_shape"
                        operation_type = "replace_text_shape"
                    else:
                        continue
                    if (
                        isinstance(current_text, str)
                        and current_text
                        and isinstance(target.get("object_id"), str)
                    ):
                        source_object = source_objects.get(target["object_id"])
                        if (
                            source_object is None
                            or source_object.text != current_text
                            or source_object.geometry is None
                        ):
                            continue
                        replacement = _single_character_text_mutation(current_text, existing_tokens)
                        if replacement is None:
                            continue
                        replacement_text, replacement_token = replacement
                        geometry = source_object.geometry
                        selected = (
                            slide_number,
                            target,
                            slide_id,
                            edit_method,
                            operation_type,
                            replacement_text,
                            replacement_token,
                            {
                                "x_emu": geometry.x_emu,
                                "y_emu": geometry.y_emu,
                                "width_emu": geometry.width_emu,
                                "height_emu": geometry.height_emu,
                            },
                        )
                        break
                if selected:
                    break
            if selected is None:
                return {
                    "record_id": item["record_id"],
                    "status": "text_edit_unsupported",
                    "code": "NO_SUPPORTED_TEXT_EDIT_TARGET",
                }

            (
                slide_number,
                target,
                slide_id,
                edit_method,
                operation_type,
                replacement_text,
                replacement_token,
                target_geometry,
            ) = selected
            slide_width_emu = selection.get("slide_width_emu")
            slide_height_emu = selection.get("slide_height_emu")
            expected_text = target["current_text"]
            before_edit = _call(
                core,
                "search.lexical",
                {
                    "project_id": project_id,
                    "query": replacement_token,
                    "presentation_revision_id": original_revision_id,
                },
            )
            if before_edit.get("results"):
                raise AcceptanceFailure("EDITED_TEXT_MATCHED_BEFORE_MUTATION")
            edited = _call(
                core,
                edit_method,
                {
                    "project_id": project_id,
                    "document_id": document_id,
                    "expected_revision_id": original_revision_id,
                    "operation_type": operation_type,
                    "slide_id": slide_id,
                    "object_id": target["object_id"],
                    "expected_text": expected_text,
                    "replacement_text": replacement_text,
                },
            )
            edited_revision_id = edited.get("revision_id")
            edited_sha256 = edited.get("sha256")
            if edited.get("changed") is not True or not isinstance(edited_revision_id, str):
                raise AcceptanceFailure("TEXT_EDIT_NOT_COMMITTED")
            if not isinstance(edited_sha256, str):
                raise AcceptanceFailure("EDITED_REVISION_HASH_MISSING")

            edited_export = root / "edited-export.pptx"
            export_result = _call(
                core,
                "presentation.workspace.export_current_copy",
                {
                    "project_id": project_id,
                    "document_id": document_id,
                    "destination_path": str(edited_export),
                },
            )
            if (
                not edited_export.is_file()
                or _sha256(edited_export) != edited_sha256
                or export_result.get("sha256") != edited_sha256
            ):
                raise AcceptanceFailure("EDITED_EXPORT_HASH_MISMATCH")
            edited_fidelity = _checked_snapshot(edited_export, document_id)
            revised_slide = edited_fidelity.slides[slide_number - 1]
            revised_target = next(
                (obj for obj in revised_slide.objects if obj.object_id == target["object_id"]),
                None,
            )
            if revised_target is None or revised_target.text != replacement_text:
                raise AcceptanceFailure("EDITED_TEXT_NOT_REOPENABLE")
            if len(original_fidelity.slides) != len(edited_fidelity.slides):
                raise AcceptanceFailure("EDITED_EXPORT_SLIDE_COUNT_CHANGED")
            for original_slide, edited_slide in zip(
                original_fidelity.slides,
                edited_fidelity.slides,
                strict=True,
            ):
                if (
                    original_slide.ooxml_slide_id != edited_slide.ooxml_slide_id
                    or original_slide.speaker_notes != edited_slide.speaker_notes
                    or len(original_slide.objects) != len(edited_slide.objects)
                ):
                    raise AcceptanceFailure("EDITED_EXPORT_STRUCTURE_CHANGED")
                for original_object, edited_object in zip(
                    original_slide.objects,
                    edited_slide.objects,
                    strict=True,
                ):
                    expected_object = (
                        replace(original_object, text=replacement_text)
                        if original_object.object_id == target["object_id"]
                        else original_object
                    )
                    if edited_object != expected_object:
                        raise AcceptanceFailure("EDITED_EXPORT_UNRELATED_CONTENT_CHANGED")
            original_parts = _package_part_hashes(source)
            edited_parts = _package_part_hashes(edited_export)
            if len(original_parts) != len(edited_parts):
                raise AcceptanceFailure("EDITED_EXPORT_PACKAGE_PARTS_CHANGED")
            changed_parts = [
                original_part[0]
                for original_part, edited_part in zip(
                    original_parts,
                    edited_parts,
                    strict=True,
                )
                if original_part != edited_part
            ]
            expected_changed_part = original_fidelity.slides[slide_number - 1].part_name
            if changed_parts != [expected_changed_part]:
                raise AcceptanceFailure("EDITED_EXPORT_UNTOUCHED_PART_CHANGED")

            powerpoint_slide_count: int | None = None
            powerpoint_validation = "not_performed"
            visual_validation = "not_performed"
            visual_result: dict[str, Any] | None = None
            if powerpoint is not None:
                office_validation_started = True
                has_external_content = bool(
                    _external_non_hyperlink_relationship_count(source)
                    or _external_non_hyperlink_relationship_count(edited_export)
                )
                if has_external_content:
                    powerpoint_validation = "skipped_external_relationships"
                    if office_visual_requested:
                        visual_validation = "skipped_external_relationships"
                elif office_visual_requested:
                    if (
                        isinstance(slide_width_emu, bool)
                        or not isinstance(slide_width_emu, int)
                        or isinstance(slide_height_emu, bool)
                        or not isinstance(slide_height_emu, int)
                    ):
                        raise AcceptanceFailure("POWERPOINT_SLIDE_DIMENSIONS_INVALID")
                    visual_result = powerpoint.compare_rendered_exports(
                        source,
                        edited_export,
                        len(edited_fidelity.slides),
                        slide_number,
                        target_geometry,
                        slide_width_emu,
                        slide_height_emu,
                    )
                    powerpoint_slide_count = visual_result.get("rendered_slide_count")
                    if not isinstance(powerpoint_slide_count, int):
                        raise AcceptanceFailure("POWERPOINT_RENDER_COUNT_MISSING")
                    powerpoint_validation = "passed"
                    visual_validation = str(visual_result.get("status"))
                else:
                    powerpoint_slide_count = powerpoint.open_read_only(
                        edited_export,
                        len(edited_fidelity.slides),
                    )
                    powerpoint_validation = "passed"

            _call(
                core,
                "source.reindex",
                {"project_id": project_id, "document_id": document_id},
            )
            indexed = _call(
                core,
                "search.lexical",
                {
                    "project_id": project_id,
                    "query": replacement_token,
                    "presentation_revision_id": edited_revision_id,
                },
            )
            indexed_results = indexed.get("results")
            if not isinstance(indexed_results, list) or not any(
                isinstance(result, dict)
                and result.get("source_id") == document_id
                and replacement_token in lexical_normalize(str(result.get("text", ""))).split()
                for result in indexed_results
            ):
                raise AcceptanceFailure("EDITED_TEXT_NOT_REINDEXED")

            restored = _call(
                core,
                "presentation.workspace.restore_revision",
                {
                    "project_id": project_id,
                    "document_id": document_id,
                    "expected_revision_id": edited_revision_id,
                    "revision_id": original_revision_id,
                },
            )
            if restored.get("changed") is not True:
                raise AcceptanceFailure("ORIGINAL_REVISION_NOT_RESTORED")
            _call(
                core,
                "source.reindex",
                {"project_id": project_id, "document_id": document_id},
            )
            stale_search = _call(
                core,
                "search.lexical",
                {
                    "project_id": project_id,
                    "query": replacement_token,
                    "presentation_revision_id": original_revision_id,
                },
            )
            if stale_search.get("results"):
                raise AcceptanceFailure("RESTORED_REVISION_RETAINED_EDITED_TEXT")

            restored_export = root / "restored-export.pptx"
            _call(
                core,
                "presentation.workspace.export_current_copy",
                {
                    "project_id": project_id,
                    "document_id": document_id,
                    "destination_path": str(restored_export),
                },
            )
            restored_hash = _sha256(restored_export)
            if restored_hash != source_hash or _sha256(source) != source_hash:
                raise AcceptanceFailure("ORIGINAL_EXPORT_NOT_BYTE_IDENTICAL")

            result = {
                "record_id": item["record_id"],
                "status": "roundtrip_smoke_passed",
                "source_sha256": source_hash,
                "edited_export_sha256": edited_sha256,
                "restored_sha256": restored_hash,
                "edit_path": (
                    "uniform_runs" if operation_type == "replace_text_shape" else "single_run"
                ),
                "slide_count": len(edited_fidelity.slides),
                "object_count": edited_fidelity.object_count,
                "edited_slide_number": slide_number,
                "edited_export_reopened": True,
                "original_export_byte_identical": True,
            }
            if powerpoint_slide_count is not None:
                result["powerpoint_opened"] = True
                result["powerpoint_slide_count"] = powerpoint_slide_count
            if powerpoint is not None:
                result["powerpoint_open_validation"] = powerpoint_validation
            if office_visual_requested:
                result["visual_validation"] = visual_validation
                if visual_result is not None:
                    result["visual_metrics"] = {
                        key: visual_result[key]
                        for key in (
                            "renderer_nondeterministic_slides",
                            "renderer_unstable_pixel_counts",
                            "untouched_slides_with_pixel_diff",
                            "edited_slide_changed_pixels",
                            "edited_slide_change_visible",
                            "edited_target_geometry_check",
                            "edited_slide_diff_bounds",
                            "edited_target_allowed_diff_bounds_px",
                        )
                    }
            return result
        except AcceptanceFailure as error:
            failure = {
                "record_id": item["record_id"],
                "status": "failed",
                "code": error.code,
            }
            if office_validation_started:
                failure["powerpoint_open_validation"] = "failed"
                if office_visual_requested:
                    failure["visual_validation"] = "failed"
            return failure
        except CoreDomainError as error:
            return {
                "record_id": item["record_id"],
                "status": "failed",
                "code": error.code,
            }
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            return {
                "record_id": item["record_id"],
                "status": "failed",
                "code": "ROUNDTRIP_SMOKE_FAILED",
            }
        finally:
            if opened and opened.get("session_id") and project_id and document_id:
                try:
                    _call(
                        core,
                        "presentation.workspace.close_source",
                        {
                            "project_id": project_id,
                            "document_id": document_id,
                            "session_id": opened["session_id"],
                        },
                    )
                except Exception:
                    pass
            core.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record-id",
        type=int,
        action="append",
        help="Run selected pinned corpus record IDs; repeat to select more than one.",
    )
    args = parser.parse_args()
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        records = manifest["records"]
        supplemental_records = manifest.get("supplemental_records", [])
        if not isinstance(records, list) or not isinstance(supplemental_records, list):
            raise TypeError
        records = [*records, *supplemental_records]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        print(json.dumps({"status": "failed", "code": "CORPUS_MANIFEST_UNAVAILABLE"}))
        return 1

    if args.record_id:
        selected_ids = set(args.record_id)
        records = [
            item
            for item in records
            if isinstance(item, dict) and item.get("record_id") in selected_ids
        ]
        if {item["record_id"] for item in records} != selected_ids:
            print(json.dumps({"status": "failed", "code": "CORPUS_RECORD_NOT_FOUND"}))
            return 1

    office_visual_requested = os.environ.get("PRESENTER_COPILOT_OFFICE_VISUAL") == "1"
    office_open_requested = (
        os.environ.get("PRESENTER_COPILOT_OFFICE_OPEN") == "1" or office_visual_requested
    )
    powerpoint: PowerPointOpenValidator | None = None
    if office_open_requested:
        try:
            powerpoint = PowerPointOpenValidator()
        except AcceptanceFailure as error:
            print(json.dumps({"status": "manual_required", "code": error.code}))
            return 2

    entries: list[dict[str, Any]] = []
    release_failed = False
    for item in records:
        name = item.get("local_name")
        if not isinstance(name, str) or Path(name).name != name:
            entries.append(
                {
                    "record_id": item.get("record_id"),
                    "status": "failed",
                    "code": "CORPUS_MANIFEST_INVALID",
                }
            )
            continue
        source = CORPUS_ROOT / name
        if not source.is_file() or source.is_symlink():
            entries.append(
                {
                    "record_id": item.get("record_id"),
                    "status": "failed",
                    "code": "CORPUS_FILE_MISSING",
                }
            )
            continue
        try:
            if source.stat().st_size != item.get("file_size_bytes"):
                entries.append(
                    {
                        "record_id": item["record_id"],
                        "status": "failed",
                        "code": "CORPUS_SIZE_MISMATCH",
                    }
                )
                continue
            digest = hashlib.md5(source.read_bytes(), usedforsecurity=False).hexdigest()
            if digest != item.get("file_md5"):
                entries.append(
                    {
                        "record_id": item["record_id"],
                        "status": "failed",
                        "code": "CORPUS_MD5_MISMATCH",
                    }
                )
                continue
            if item.get("file_sha1"):
                sha1 = hashlib.sha1(source.read_bytes(), usedforsecurity=False).hexdigest()
                if sha1 != item.get("file_sha1"):
                    entries.append(
                        {
                            "record_id": item["record_id"],
                            "status": "failed",
                            "code": "CORPUS_SHA1_MISMATCH",
                        }
                    )
                    continue
            if item.get("file_sha256"):
                sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
                if sha256 != item.get("file_sha256"):
                    entries.append(
                        {
                            "record_id": item["record_id"],
                            "status": "failed",
                            "code": "CORPUS_SHA256_MISMATCH",
                        }
                    )
                    continue
            if office_open_requested and powerpoint is None:
                powerpoint = PowerPointOpenValidator()
            entries.append(_exercise(item, source, powerpoint, office_visual_requested))
        except AcceptanceFailure as error:
            failure = {
                "record_id": item.get("record_id"),
                "status": "failed",
                "code": error.code,
            }
            if office_open_requested:
                failure["powerpoint_open_validation"] = "failed"
                if office_visual_requested:
                    failure["visual_validation"] = "failed"
            entries.append(failure)
        except OSError:
            entries.append(
                {
                    "record_id": item.get("record_id"),
                    "status": "failed",
                    "code": "CORPUS_FILE_UNREADABLE",
                }
            )
        finally:
            if office_open_requested and powerpoint is not None:
                try:
                    powerpoint.close()
                except AcceptanceFailure:
                    release_failed = True
                powerpoint = None

    if powerpoint is not None:
        try:
            powerpoint.close()
        except AcceptanceFailure:
            release_failed = True

    unsupported = sum(entry.get("status") == "unsupported" for entry in entries)
    text_edit_unsupported = sum(entry.get("status") == "text_edit_unsupported" for entry in entries)
    failures = sum(entry.get("status") == "failed" for entry in entries)
    passed = sum(entry.get("status") == "roundtrip_smoke_passed" for entry in entries)
    powerpoint_statuses = [
        entry["powerpoint_open_validation"]
        for entry in entries
        if "powerpoint_open_validation" in entry
    ]
    if release_failed or "failed" in powerpoint_statuses:
        powerpoint_validation = "failed"
    elif "skipped_external_relationships" in powerpoint_statuses:
        powerpoint_validation = "partial_external_relationships_skipped"
    elif powerpoint_statuses and all(status == "passed" for status in powerpoint_statuses):
        powerpoint_validation = "passed"
    elif not powerpoint_statuses:
        powerpoint_validation = "not_performed"
    else:
        powerpoint_validation = "failed"

    visual_statuses = [
        entry["visual_validation"] for entry in entries if "visual_validation" in entry
    ]
    if not office_visual_requested:
        visual_validation = "not_performed"
    elif "failed" in visual_statuses or failures:
        visual_validation = "failed"
    elif "needs_review" in visual_statuses:
        visual_validation = "needs_review"
    elif "skipped_external_relationships" in visual_statuses:
        visual_validation = "partial_external_relationships_skipped"
    elif "passed_with_dynamic_regions_masked" in visual_statuses:
        visual_validation = "passed_with_dynamic_regions_masked"
    elif visual_statuses and all(status == "passed" for status in visual_statuses):
        visual_validation = "passed"
    else:
        visual_validation = "failed"

    result = {
        "status": "completed" if failures == 0 and not release_failed else "failed",
        "operation": "isolated_real_deck_text_edit_export_restore_smoke",
        "record_count": len(entries),
        "roundtrip_smoke_passed_count": passed,
        "parser_unsupported_count": unsupported,
        "text_edit_unsupported_count": text_edit_unsupported,
        "unsupported_count": unsupported + text_edit_unsupported,
        "failure_count": failures + int(release_failed),
        "powerpoint_application_quit": False,
        "powerpoint_release_failed": release_failed,
        "deck_text_emitted": False,
        "visual_validation": visual_validation,
        "powerpoint_open_validation": powerpoint_validation,
        "powerpoint_opened_count": sum(
            entry.get("powerpoint_open_validation") == "passed" for entry in entries
        ),
        "powerpoint_external_relationships_skipped_count": sum(
            entry.get("powerpoint_open_validation") == "skipped_external_relationships"
            for entry in entries
        ),
        "visual_passed_count": sum(entry.get("visual_validation") == "passed" for entry in entries),
        "visual_dynamic_masked_count": sum(
            entry.get("visual_validation") == "passed_with_dynamic_regions_masked"
            for entry in entries
        ),
        "visual_review_required_count": sum(
            entry.get("visual_validation") == "needs_review" for entry in entries
        ),
        "visual_external_relationships_skipped_count": sum(
            entry.get("visual_validation") == "skipped_external_relationships" for entry in entries
        ),
        "entries": entries,
    }
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 1 if failures or release_failed else 0


if __name__ == "__main__":
    sys.exit(main())
