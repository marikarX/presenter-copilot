"""Verified native transparent layers from a privileged private saved-revision copy.

Only the opened read-only deck belongs to us. Never alter shared Office settings,
quit the application, save, or accept paths chosen by the presentation renderer.
"""

from __future__ import annotations

import ctypes
import importlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, TextIO

import numpy as np
from PIL import Image

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import inspect_pptx_snapshot
from presenter_core.presentation.native_pdf import (
    NATIVE_PAGE_TOLERANCE_PT,
    _digest,
    validate_native_source,
)
from presenter_core.presentation.native_preview import MAX_DIMENSION, MAX_IMAGE_BYTES

MAX_LAYERS = 200
MAX_TOTAL_BYTES = 96 * 1024 * 1024
MAX_DECODED_BYTES = 256 * 1024 * 1024
# Bound every reconstructed channel, rather than accepting a low average hiding a bad object.
MAX_BASELINE_CHANNEL_ERROR = 4
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z", re.I)


def _fail(message: str) -> CoreDomainError:
    return CoreDomainError("PRESENTATION_NATIVE_LAYERS_FAILED", message)


def recover_native_alpha(black: Image.Image, white: Image.Image) -> Image.Image:
    """Recover straight RGBA from same-coordinate black/white native mattes."""
    if black.size != white.size or min(black.size) < 1 or max(black.size) > MAX_DIMENSION:
        raise _fail("Native layer matte dimensions do not match.")
    dark = np.asarray(black.convert("RGB"), dtype=np.float64)
    light = np.asarray(white.convert("RGB"), dtype=np.float64)
    delta = light - dark
    if np.any(delta < -1) or np.any(np.max(delta, axis=2) - np.min(delta, axis=2) > 4):
        raise _fail("This object does not have a consistent transparent native appearance.")
    alpha = 255 - np.mean(np.clip(delta, 0, 255), axis=2)
    rgb = np.divide(
        dark * 255, alpha[:, :, None], out=np.zeros_like(dark), where=alpha[:, :, None] > 0
    )
    pixels = np.concatenate(
        [np.clip(np.rint(rgb), 0, 255), np.rint(alpha[:, :, None])], axis=2
    ).astype(np.uint8)
    return Image.fromarray(pixels)


def verify_native_composition(
    baseline: Image.Image, background: Image.Image, layers: list[Image.Image]
) -> int:
    if baseline.size != background.size or any(layer.size != baseline.size for layer in layers):
        raise _fail("The native layers do not share the saved slide coordinates.")
    composite = background.convert("RGBA")
    for layer in layers:
        composite = Image.alpha_composite(composite, layer.convert("RGBA"))
    difference = np.abs(
        np.asarray(baseline.convert("RGB"), dtype=np.int16)
        - np.asarray(composite.convert("RGB"), dtype=np.int16)
    )
    maximum = int(difference.max())
    if maximum > MAX_BASELINE_CHANNEL_ERROR:
        raise _fail("Native layers do not reproduce the saved slide. Use the normal slide preview.")
    return maximum


def _read_png(path: Path, size: tuple[int, int]) -> Image.Image:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_IMAGE_BYTES:
        raise _fail("A native layer image exceeds its limits.")
    with Image.open(path) as image:
        if image.format != "PNG" or image.size != size:
            raise _fail("A native layer image has invalid dimensions.")
        image.load()
        return image.convert("RGBA")


def export_native_layers(job: dict[str, Any], *, application: Any = None) -> dict[str, Any]:
    reject_unknown_fields(
        job, {"snapshot_path", "output_path", "source_sha256", "slide_number", "document_id"}
    )
    digest, number, document_id = (
        job.get("source_sha256"),
        job.get("slide_number"),
        job.get("document_id"),
    )
    if (
        not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or type(number) is not int
        or not 1 <= number <= 5000
        or not isinstance(document_id, str)
        or not _UUID.fullmatch(document_id)
    ):
        raise invalid_request("The native layer target is invalid.")
    for field in ("snapshot_path", "output_path"):
        value = job.get(field)
        if not isinstance(value, str) or not value or len(value) > 32768 or "\x00" in value:
            raise invalid_request("The native layer path is invalid.")
    source, output = Path(job["snapshot_path"]), Path(job["output_path"])
    if (
        not source.is_absolute()
        or not output.is_absolute()
        or source.is_symlink()
        or output.exists()
        or output.is_symlink()
        or source.suffix.casefold() != ".pptx"
        or output.suffix.casefold() != ".json"
        or source.parent.resolve() != output.parent.resolve()
    ):
        raise invalid_request("Native layers require a new receipt beside the private copy.")
    count, width, height = validate_native_source(source, digest)
    if number > count:
        raise invalid_request("The requested native slide does not exist.")
    with source.open("rb") as handle:
        inventory = inspect_pptx_snapshot(
            handle, document_id=document_id, expected_sha256=digest, byte_size=source.stat().st_size
        )
    objects = inventory.slides[number - 1].objects
    if len(objects) > MAX_LAYERS:
        raise _fail("This slide exceeds the live native layer limit.")
    scale = min(960 / width, MAX_DIMENSION / height)
    size = max(1, round(width * scale)), max(1, round(height * scale))
    if (len(objects) + 2) * size[0] * size[1] * 4 > MAX_DECODED_BYTES:
        raise _fail("This slide exceeds the decoded native layer memory budget.")
    prefix = output.stem

    def filename(label: str) -> Path:
        result = output.with_name(f"{prefix}-{label}.png")
        if result.exists() or result.is_symlink():
            raise invalid_request("Native layer outputs must be new private files.")
        return result

    apartment: Any = None
    presentation: Any = None
    try:
        if application is None:
            if sys.platform != "win32":
                raise _fail("Live native layers require Microsoft PowerPoint on Windows.")
            client = importlib.import_module("win32com.client")
            apartment = ctypes.WinDLL("ole32")
            apartment.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            apartment.CoInitializeEx.restype = ctypes.c_long
            apartment.CoUninitialize.argtypes = []
            apartment.CoUninitialize.restype = None
            if apartment.CoInitializeEx(None, 2) < 0:
                apartment = None
                raise _fail("The native layer COM apartment is unavailable.")
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
            raise _fail("PowerPoint changed the native layer slide inventory or geometry.")
        slide = presentation.Slides.Item(number)
        shapes = [slide.Shapes.Item(i) for i in range(1, int(slide.Shapes.Count) + 1)]
        if [str(shape.Id) for shape in shapes] != [obj.ooxml_id for obj in objects]:
            raise _fail("PowerPoint changed the native object identities or paint order.")
        baseline_path = filename("baseline")
        slide.Export(str(baseline_path), "PNG", *size)
        baseline = _read_png(baseline_path, size)
        visible = [int(shape.Visible) for shape in shapes]
        for shape in shapes:
            shape.Visible = 0
        background_path = filename("background")
        slide.Export(str(background_path), "PNG", *size)
        background = _read_png(background_path, size)
        slide.DisplayMasterShapes = 0
        slide.FollowMasterBackground = 0
        slide.Background.Fill.Solid()
        layers: list[Image.Image] = []
        receipts: list[dict[str, Any]] = []
        total = background_path.stat().st_size + baseline_path.stat().st_size
        for index, (shape, obj, original_visibility) in enumerate(
            zip(shapes, objects, visible, strict=True)
        ):
            layer_path = filename(f"layer-{index}")
            if original_visibility == 0:
                layer = Image.new("RGBA", size)
            else:
                shape.Visible = original_visibility
                black_path, white_path = filename(f"black-{index}"), filename(f"white-{index}")
                slide.Background.Fill.ForeColor.RGB = 0
                slide.Export(str(black_path), "PNG", *size)
                black = _read_png(black_path, size)
                slide.Background.Fill.ForeColor.RGB = 16777215
                slide.Export(str(white_path), "PNG", *size)
                white = _read_png(white_path, size)
                shape.Visible = 0
                total += black_path.stat().st_size + white_path.stat().st_size
                layer = recover_native_alpha(black, white)
            layer.save(layer_path)
            if not 0 < layer_path.stat().st_size <= MAX_IMAGE_BYTES:
                raise _fail("A transparent native layer image exceeds its limits.")
            total += layer_path.stat().st_size
            if total > MAX_TOTAL_BYTES:
                raise _fail("This slide exceeds the native layer image budget.")
            layers.append(layer)
            receipts.append(
                {
                    "object_id": obj.object_id,
                    "ooxml_shape_id": obj.ooxml_id,
                    "visible": original_visibility != 0,
                    "file": layer_path.name,
                    "byte_size": layer_path.stat().st_size,
                    "sha256": _digest(layer_path),
                }
            )
        maximum = verify_native_composition(baseline, background, layers)
        result = {
            "source_sha256": digest,
            "document_id": document_id,
            "slide_number": number,
            "slide_count": count,
            "width": size[0],
            "height": size[1],
            "renderer": "microsoft_powerpoint",
            "baseline_max_channel_error": maximum,
            "background": {
                "file": background_path.name,
                "byte_size": background_path.stat().st_size,
                "sha256": _digest(background_path),
            },
            "layers": receipts,
        }
        output.write_text(json.dumps(result), encoding="utf-8")
        return result
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
                raise _fail("PowerPoint changed the private native layer revision copy.")


def run_layers_worker(stdin: TextIO, stdout: TextIO) -> int:
    try:
        raw = stdin.read(8193)
        if len(raw) > 8192:
            raise invalid_request("The native layer job is too large.")
        job = json.loads(raw)
        if not isinstance(job, dict):
            raise invalid_request("The native layer job must be an object.")
        result = export_native_layers(job)
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
                "code": "PRESENTATION_NATIVE_LAYERS_FAILED",
                "message": (
                    "PowerPoint could not prepare live native layers. Use the normal slide preview."
                ),
                "retryable": True,
                "details": {},
            },
        }
        code = 1
    stdout.write(json.dumps(response) + "\n")
    stdout.flush()
    return code
