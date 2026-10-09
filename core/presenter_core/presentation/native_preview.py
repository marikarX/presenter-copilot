"""One-shot native slide appearance, on a privileged private revision copy."""

from __future__ import annotations

import ctypes
import importlib
import json
import math
import sys
from pathlib import Path
from typing import Any, TextIO

from PIL import Image

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.native_pdf import (
    NATIVE_PAGE_TOLERANCE_PT,
    _digest,
    validate_native_source,
)

MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_DIMENSION = 4096


def _fail(message: str) -> CoreDomainError:
    return CoreDomainError("PRESENTATION_NATIVE_PREVIEW_FAILED", message)


def export_native_preview(job: dict[str, Any], *, application: Any = None) -> dict[str, Any]:
    reject_unknown_fields(job, {"snapshot_path", "output_path", "source_sha256", "slide_number"})
    digest, number = job.get("source_sha256"), job.get("slide_number")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
        or type(number) is not int
        or not 1 <= number <= 5000
    ):
        raise invalid_request("The native appearance target is invalid.")
    for field in ("snapshot_path", "output_path"):
        value = job.get(field)
        if not isinstance(value, str) or not value or len(value) > 32768 or "\x00" in value:
            raise invalid_request("The native appearance path is invalid.")
    source, output = Path(job["snapshot_path"]), Path(job["output_path"])
    if (
        not source.is_absolute()
        or not output.is_absolute()
        or source.is_symlink()
        or output.exists()
        or output.is_symlink()
        or source.suffix.casefold() != ".pptx"
        or output.suffix.casefold() != ".png"
        or source.parent.resolve() != output.parent.resolve()
    ):
        raise invalid_request("Native appearance requires a new image beside its private copy.")
    count, width, height = validate_native_source(source, digest)
    if number > count:
        raise invalid_request("The requested native slide does not exist.")
    scale = min(960 / width, MAX_DIMENSION / height)
    pixel_width, pixel_height = max(1, round(width * scale)), max(1, round(height * scale))
    apartment: Any = None
    presentation: Any = None
    try:
        if application is None:
            if sys.platform != "win32":
                raise _fail("PowerPoint appearance requires Microsoft PowerPoint on Windows.")
            client = importlib.import_module("win32com.client")
            # Own a native reference, even when pywin32 already initialized this thread.
            apartment = ctypes.WinDLL("ole32")
            apartment.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            apartment.CoInitializeEx.restype = ctypes.c_long
            apartment.CoUninitialize.argtypes = []
            apartment.CoUninitialize.restype = None
            if apartment.CoInitializeEx(None, 2) < 0:
                apartment = None
                raise _fail("The native appearance COM apartment is unavailable.")
            application = client.DispatchEx("PowerPoint.Application")
        presentation = application.Presentations.Open(
            str(source), ReadOnly=True, Untitled=False, WithWindow=False
        )
        if int(presentation.Slides.Count) != count or not all(
            math.isclose(float(actual), expected, rel_tol=0, abs_tol=NATIVE_PAGE_TOLERANCE_PT)
            for actual, expected in (
                (presentation.PageSetup.SlideWidth, width),
                (presentation.PageSetup.SlideHeight, height),
            )
        ):
            raise _fail("PowerPoint changed the slide inventory or geometry.")
        # Index addresses hidden slides too, without changing their visibility.
        presentation.Slides.Item(number).Export(str(output), "PNG", pixel_width, pixel_height)
        size = output.stat().st_size
        if not 0 < size <= MAX_IMAGE_BYTES or output.is_symlink():
            raise _fail("The native appearance image exceeds its limits.")
        with Image.open(output) as image:
            if image.format != "PNG" or image.size != (pixel_width, pixel_height):
                raise _fail("The native appearance image dimensions are invalid.")
            image.verify()
        return {
            "source_sha256": digest,
            "slide_number": number,
            "slide_count": count,
            "width": pixel_width,
            "height": pixel_height,
            "byte_size": size,
            "sha256": _digest(output),
            "renderer": "microsoft_powerpoint",
        }
    finally:
        try:
            if presentation is not None:
                presentation.Close()
        finally:
            presentation = None
            application = None
            if apartment is not None:
                apartment.CoUninitialize()
            if _digest(source) != digest:
                raise _fail("PowerPoint changed the private revision copy.")


def run_preview_worker(stdin: TextIO, stdout: TextIO) -> int:
    try:
        raw = stdin.read(8193)
        if len(raw) > 8192:
            raise invalid_request("The native appearance job is too large.")
        job = json.loads(raw)
        if not isinstance(job, dict):
            raise invalid_request("The native appearance job must be an object.")
        result = export_native_preview(job)
        response: dict[str, Any] = {"ok": True, "result": result}
        code = 0
    except CoreDomainError as error:
        response = {
            "ok": False,
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "details": {},
            },
        }
        code = 1
    except Exception:
        response = {
            "ok": False,
            "error": {
                "code": "PRESENTATION_NATIVE_PREVIEW_FAILED",
                "message": (
                    "PowerPoint could not render this slide. "
                    "Use the browser preview or open a PPTX copy."
                ),
                "retryable": True,
                "details": {},
            },
        }
        code = 1
    stdout.write(json.dumps(response) + "\n")
    stdout.flush()
    return code
