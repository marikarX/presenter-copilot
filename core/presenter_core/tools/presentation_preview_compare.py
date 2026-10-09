"""Compare in-app PPTX preview renders with local PowerPoint output."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from presenter_core.errors import CoreDomainError
from presenter_core.tools.presentation_corpus_roundtrip import (
    CORPUS_ROOT,
    MANIFEST_PATH,
    REPOSITORY_ROOT,
    AcceptanceFailure,
    PowerPointOpenValidator,
    _binary_pixel_difference,
    _checked_snapshot,
    _external_non_hyperlink_relationship_count,
    _pixel_mask_summary,
    _sha256,
)

LOCAL_ROOT = REPOSITORY_ROOT / ".local"
RENDERER_SCRIPT = REPOSITORY_ROOT / "apps" / "desktop" / "scripts" / "render-workspace-preview.mjs"
DESKTOP_ROOT = REPOSITORY_ROOT / "apps" / "desktop"
MAX_RENDER_SLIDES = 5_000
PREVIEW_COMPATIBILITY_MODES = {
    "all",
    "all-no-image-effects",
    "line-spacing-only",
    "baseline",
    "background-only",
    "theme-background-only",
    "theme-override-only",
    "hidden-only",
    "placeholder-only",
    "smartart-only",
    "picture-geometry-only",
}


def _record_source(item: dict[str, Any]) -> tuple[Path | None, str | None]:
    name = item.get("local_name")
    if not isinstance(name, str) or Path(name).name != name:
        return None, "CORPUS_MANIFEST_INVALID"
    source = CORPUS_ROOT / name
    try:
        if LOCAL_ROOT.is_symlink() or CORPUS_ROOT.is_symlink() or source.is_symlink():
            return None, "CORPUS_PATH_SYMLINK"
        resolved_root = CORPUS_ROOT.resolve(strict=True)
        resolved_source = source.resolve(strict=True)
        if resolved_source.parent != resolved_root or not resolved_source.is_file():
            return None, "CORPUS_PATH_INVALID"
        if resolved_source.stat().st_size != item.get("file_size_bytes"):
            return None, "CORPUS_SIZE_MISMATCH"
        digest = hashlib.md5(resolved_source.read_bytes(), usedforsecurity=False).hexdigest()
        if digest != item.get("file_md5"):
            return None, "CORPUS_MD5_MISMATCH"
        return resolved_source, None
    except FileNotFoundError:
        return None, "CORPUS_FILE_MISSING"
    except OSError:
        return None, "CORPUS_FILE_UNREADABLE"


def _renderer_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in list(environment):
        if (
            key.startswith("PRESENTER_")
            or key.startswith("OPENAI_")
            or key in {"OPENROUTER_API_KEY", "ELECTRON_RUN_AS_NODE"}
        ):
            environment.pop(key, None)
    return environment


def _render_preview(
    source: Path,
    output_directory: Path,
    compatibility_mode: str = "all",
) -> dict[str, Any]:
    if compatibility_mode not in PREVIEW_COMPATIBILITY_MODES:
        raise AcceptanceFailure("PREVIEW_COMPATIBILITY_MODE_INVALID")
    command = ["node", str(RENDERER_SCRIPT), str(source), str(output_directory)]
    command.append(compatibility_mode)
    try:
        completed = subprocess.run(
            command,
            cwd=DESKTOP_ROOT,
            env=_renderer_environment(),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except FileNotFoundError as error:
        raise AcceptanceFailure("PREVIEW_NODE_RUNTIME_UNAVAILABLE") from error
    except subprocess.TimeoutExpired as error:
        raise AcceptanceFailure("PREVIEW_RENDER_TIMEOUT") from error
    if completed.returncode != 0:
        try:
            response = json.loads(completed.stdout)
            code = response.get("code") if isinstance(response, dict) else None
        except json.JSONDecodeError:
            code = None
        raise AcceptanceFailure(code if isinstance(code, str) else "PREVIEW_RENDER_FAILED")
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AcceptanceFailure("PREVIEW_RENDER_RESPONSE_INVALID") from error
    if (
        not isinstance(response, dict)
        or response.get("status") != "completed"
        or response.get("compatibility_mode") != compatibility_mode
        or not isinstance(response.get("slide_count"), int)
        or not isinstance(response.get("slides"), list)
    ):
        raise AcceptanceFailure("PREVIEW_RENDER_RESPONSE_INVALID")
    if response["slide_count"] != len(response["slides"]):
        raise AcceptanceFailure("PREVIEW_RENDER_RESPONSE_INVALID")
    return response


def _slide_metadata(
    response: dict[str, Any],
    slide_count: int,
    output_directory: Path,
) -> tuple[list[tuple[int, int]], list[Path]]:
    rows = response["slides"]
    if len(rows) != slide_count or slide_count < 1 or slide_count > MAX_RENDER_SLIDES:
        raise AcceptanceFailure("PREVIEW_SLIDE_COUNT_MISMATCH")
    dimensions: list[tuple[int, int]] = []
    images: list[Path] = []
    for expected_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or row.get("slide_number") != expected_number:
            raise AcceptanceFailure("PREVIEW_SLIDE_ORDER_INVALID")
        width = row.get("width")
        height = row.get("height")
        image_path = output_directory / f"slide-{expected_number:04}.png"
        if (
            isinstance(width, bool)
            or not isinstance(width, int)
            or isinstance(height, bool)
            or not isinstance(height, int)
            or not image_path.is_file()
            or _sha256(image_path) != row.get("png_sha256")
        ):
            raise AcceptanceFailure("PREVIEW_IMAGE_INVALID")
        try:
            with Image.open(image_path) as image:
                if image.size != (width, height):
                    raise AcceptanceFailure("PREVIEW_IMAGE_DIMENSIONS_INVALID")
                image.verify()
        except OSError as error:
            raise AcceptanceFailure("PREVIEW_IMAGE_INVALID") from error
        dimensions.append((width, height))
        images.append(image_path)
    return dimensions, images


def _compare_slide(
    powerpoint_image: Path,
    repeated_powerpoint_image: Path,
    preview_image: Path,
) -> dict[str, Any]:
    try:
        with Image.open(powerpoint_image) as image:
            original = image.convert("RGB")
        with Image.open(repeated_powerpoint_image) as image:
            repeated = image.convert("RGB")
        with Image.open(preview_image) as image:
            preview = image.convert("RGB")
    except OSError as error:
        raise AcceptanceFailure("VISUAL_COMPARE_IMAGE_INVALID") from error
    if original.size != repeated.size or original.size != preview.size:
        raise AcceptanceFailure("VISUAL_COMPARE_DIMENSIONS_MISMATCH")

    unstable_mask = _binary_pixel_difference(original, repeated)
    preview_difference = _binary_pixel_difference(original, preview)
    stable_difference = ImageChops.subtract(preview_difference, unstable_mask)
    unstable_pixels, _ = _pixel_mask_summary(unstable_mask)
    stable_changed_pixels, stable_bounds = _pixel_mask_summary(stable_difference)
    total_pixels = original.width * original.height
    stable_mask = ImageChops.invert(unstable_mask)
    difference = ImageChops.difference(original, preview)
    red, green, blue = difference.split()
    maximum_channel_difference = ImageChops.lighter(
        ImageChops.lighter(red, green),
        blue,
    )
    stable_magnitude = ImageChops.composite(
        maximum_channel_difference,
        Image.new("L", original.size, 0),
        stable_mask,
    )
    maximum_histogram = stable_magnitude.histogram()
    stable_pixel_count = total_pixels - unstable_pixels
    stable_rgb_histograms = [
        ImageChops.composite(channel, Image.new("L", original.size, 0), stable_mask).histogram()
        for channel in (red, green, blue)
    ]
    absolute_sum = sum(
        value * count
        for histogram in stable_rgb_histograms
        for value, count in enumerate(histogram)
    )
    squared_sum = sum(
        value * value * count
        for histogram in stable_rgb_histograms
        for value, count in enumerate(histogram)
    )
    mse = squared_sum / (stable_pixel_count * 3) if stable_pixel_count else 0
    return {
        "width": original.width,
        "height": original.height,
        "source_unstable_pixels": unstable_pixels,
        "source_unstable_percent": round(100 * unstable_pixels / total_pixels, 4),
        "preview_stable_difference_pixels": stable_changed_pixels,
        "preview_stable_difference_percent": round(
            100 * stable_changed_pixels / total_pixels,
            4,
        ),
        "preview_stable_difference_bounds": list(stable_bounds)
        if stable_bounds is not None
        else None,
        "stable_rgb_mae_percent": round(100 * absolute_sum / (stable_pixel_count * 3 * 255), 4)
        if stable_pixel_count
        else None,
        "stable_rgb_psnr_db": round(10 * math.log10((255 * 255) / mse), 3) if mse > 0 else None,
        "stable_pixels_max_channel_diff_over_8_percent": round(
            100 * sum(maximum_histogram[9:]) / stable_pixel_count,
            4,
        )
        if stable_pixel_count
        else None,
        "stable_pixels_max_channel_diff_over_32_percent": round(
            100 * sum(maximum_histogram[33:]) / stable_pixel_count,
            4,
        )
        if stable_pixel_count
        else None,
        "stable_pixels_max_channel_diff_over_96_percent": round(
            100 * sum(maximum_histogram[97:]) / stable_pixel_count,
            4,
        )
        if stable_pixel_count
        else None,
    }


def _compare_record(
    item: dict[str, Any],
    powerpoint: PowerPointOpenValidator,
    compatibility_mode: str = "all",
) -> dict[str, Any]:
    record_id = item.get("record_id")
    base = {"record_id": record_id}
    source, source_error = _record_source(item)
    if source is None:
        return {**base, "status": "failed", "code": source_error}
    if _external_non_hyperlink_relationship_count(source):
        return {
            **base,
            "status": "skipped_external_relationships",
            "code": "POWERPOINT_EXTERNAL_CONTENT_BLOCKED",
        }
    try:
        fidelity = _checked_snapshot(source, f"preview-compare-{record_id}")
    except CoreDomainError as error:
        return {**base, "status": "unsupported", "code": error.code}

    source_hash = _sha256(source)
    try:
        with tempfile.TemporaryDirectory(prefix="presenter-preview-office-compare-") as value:
            root = Path(value)
            preview_directory = root / "preview"
            rendered = _render_preview(
                source,
                preview_directory,
                compatibility_mode=compatibility_mode,
            )
            if rendered["slide_count"] != len(fidelity.slides):
                raise AcceptanceFailure("PREVIEW_SLIDE_COUNT_MISMATCH")
            dimensions, preview_images = _slide_metadata(
                rendered,
                len(fidelity.slides),
                preview_directory,
            )
            if _sha256(source) != source_hash:
                raise AcceptanceFailure("PREVIEW_SOURCE_CHANGED_DURING_RENDER")

            office_first = powerpoint._render_slides(
                powerpoint._application,
                source,
                root / "office-first",
                len(fidelity.slides),
                dimensions,
            )
            office_repeat = powerpoint._render_slides(
                powerpoint._application,
                source,
                root / "office-repeat",
                len(fidelity.slides),
                dimensions,
            )
            comparisons = [
                {
                    "slide_number": slide_number,
                    **_compare_slide(first, repeated, preview_image),
                }
                for slide_number, (first, repeated, preview_image) in enumerate(
                    zip(office_first, office_repeat, preview_images, strict=True),
                    start=1,
                )
            ]
            if _sha256(source) != source_hash:
                raise AcceptanceFailure("POWERPOINT_CHANGED_READ_ONLY_EXPORT")

            mismatch_count = sum(
                result["preview_stable_difference_pixels"] > 0 for result in comparisons
            )
            unstable_count = sum(result["source_unstable_pixels"] > 0 for result in comparisons)
            return {
                **base,
                "status": "compared",
                "source_sha256": source_hash,
                "slide_count": len(comparisons),
                "preview_compatibility_mode": compatibility_mode,
                "preview_compatibility": rendered.get("compatibility"),
                "slides_with_stable_pixel_differences": mismatch_count,
                "slides_with_unstable_powerpoint_render": unstable_count,
                "slides": comparisons,
            }
    except AcceptanceFailure as error:
        return {**base, "status": "failed", "code": error.code}
    except (OSError, TypeError, ValueError, KeyError):
        return {**base, "status": "failed", "code": "VISUAL_COMPARE_FAILED"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-id", type=int, help="Compare one pinned corpus record.")
    parser.add_argument(
        "--preview-compatibility",
        choices=sorted(PREVIEW_COMPATIBILITY_MODES),
        default="all",
        help="Select the preview-only compatibility pass for paired corpus diagnostics.",
    )
    args = parser.parse_args()
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        records = manifest.get("records")
        supplemental_records = manifest.get("supplemental_records", [])
        if (
            not isinstance(records, list)
            or not records
            or not isinstance(supplemental_records, list)
        ):
            raise ValueError
        records = [*records, *supplemental_records]
    except (OSError, json.JSONDecodeError, ValueError):
        print(json.dumps({"status": "failed", "code": "CORPUS_MANIFEST_UNAVAILABLE"}))
        return 1

    selected = [
        item
        for item in records
        if isinstance(item, dict)
        and (args.record_id is None or item.get("record_id") == args.record_id)
    ]
    if not selected:
        print(json.dumps({"status": "failed", "code": "CORPUS_RECORD_NOT_FOUND"}))
        return 1
    powerpoint: PowerPointOpenValidator | None
    try:
        powerpoint = PowerPointOpenValidator()
    except AcceptanceFailure as error:
        print(json.dumps({"status": "manual_required", "code": error.code}))
        return 2

    entries: list[dict[str, Any]] = []
    powerpoint_release_failed = False
    for item in selected:
        try:
            if powerpoint is None:
                powerpoint = PowerPointOpenValidator()
            entries.append(
                _compare_record(
                    item,
                    powerpoint,
                    compatibility_mode=args.preview_compatibility,
                )
            )
        except AcceptanceFailure as error:
            entries.append(
                {
                    "record_id": item.get("record_id"),
                    "status": "failed",
                    "code": error.code,
                }
            )
        finally:
            if powerpoint is not None:
                try:
                    powerpoint.close()
                except AcceptanceFailure:
                    powerpoint_release_failed = True
                powerpoint = None

    failed = sum(entry.get("status") == "failed" for entry in entries) + int(
        powerpoint_release_failed
    )
    compared = [entry for entry in entries if entry.get("status") == "compared"]
    skipped_external = sum(
        entry.get("status") == "skipped_external_relationships" for entry in entries
    )
    unsupported = sum(entry.get("status") == "unsupported" for entry in entries)
    slides_with_stable_differences = sum(
        entry.get("slides_with_stable_pixel_differences", 0) for entry in compared
    )
    slides_with_unstable_renders = sum(
        entry.get("slides_with_unstable_powerpoint_render", 0) for entry in compared
    )
    print(
        json.dumps(
            {
                "status": "completed" if failed == 0 else "failed",
                "operation": "workspace_candidate_preview_vs_powerpoint_pixel_compare",
                "record_count": len(entries),
                "compared_count": len(compared),
                "unsupported_count": unsupported,
                "external_relationships_skipped_count": skipped_external,
                "failure_count": failed,
                "powerpoint_release_failed": powerpoint_release_failed,
                "powerpoint_quit_failed": False,
                "powerpoint_application_quit": False,
                "slides_with_stable_pixel_differences": slides_with_stable_differences,
                "slides_with_unstable_powerpoint_render": slides_with_unstable_renders,
                "slide_text_emitted": False,
                "rendered_images_retained": False,
                "entries": entries,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
