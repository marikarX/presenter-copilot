from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from presenter_core.tools import presentation_preview_compare
from presenter_core.tools.presentation_preview_compare import (
    _compare_slide,
    _render_preview,
    _renderer_environment,
)


def test_preview_comparison_masks_only_source_render_variation(tmp_path: Path) -> None:
    original_path = tmp_path / "office-original.png"
    repeated_path = tmp_path / "office-repeat.png"
    preview_path = tmp_path / "preview.png"
    original = Image.new("RGB", (4, 4), "black")
    repeated = original.copy()
    repeated.putpixel((0, 0), (255, 255, 255))
    preview = original.copy()
    preview.putpixel((0, 0), (255, 255, 255))
    preview.putpixel((3, 3), (255, 255, 255))
    original.save(original_path)
    repeated.save(repeated_path)
    preview.save(preview_path)

    result = _compare_slide(original_path, repeated_path, preview_path)

    assert result["source_unstable_pixels"] == 1
    assert result["preview_stable_difference_pixels"] == 1
    assert result["preview_stable_difference_bounds"] == [3, 3, 4, 4]


def test_preview_renderer_environment_drops_provider_secrets(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-secret")
    monkeypatch.setenv("PRESENTER_COPILOT_DATA_ROOT", "test-data-path")
    monkeypatch.setenv("PATH", "safe-path")

    environment = _renderer_environment()

    assert "OPENAI_API_KEY" not in environment
    assert "OPENROUTER_API_KEY" not in environment
    assert "PRESENTER_COPILOT_DATA_ROOT" not in environment
    assert environment["PATH"] == "safe-path"


def test_preview_baseline_mode_disables_compatibility_in_isolated_harness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    response = {
        "status": "completed",
        "slide_count": 1,
        "slides": [{"slide_number": 1}],
        "compatibility": {
            "backgroundFillShapesNormalized": 0,
            "themeBackgroundImageFillsResolved": 0,
            "smartArtImageReferencesRepaired": 0,
            "smartArtRelationshipPartsUpdated": 0,
            "smartArtImageShapesPromoted": 0,
            "compatibilityPartsSkipped": 0,
        },
        "compatibility_mode": "baseline",
    }
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(response), stderr="")

    monkeypatch.setattr(presentation_preview_compare.subprocess, "run", fake_run)

    result = _render_preview(
        Path("fixture.pptx"),
        tmp_path,
        compatibility_mode="baseline",
    )

    assert calls == [
        [
            "node",
            str(presentation_preview_compare.RENDERER_SCRIPT),
            "fixture.pptx",
            str(tmp_path),
            "baseline",
        ]
    ]
    assert result["compatibility_mode"] == "baseline"


def test_preview_all_mode_is_explicit_after_smartart_only_becomes_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    response = {
        "status": "completed",
        "slide_count": 1,
        "slides": [{"slide_number": 1}],
        "compatibility": {
            "backgroundFillShapesNormalized": 1,
            "themeBackgroundImageFillsResolved": 0,
            "smartArtImageReferencesRepaired": 0,
            "smartArtRelationshipPartsUpdated": 0,
            "smartArtImageShapesPromoted": 0,
            "compatibilityPartsSkipped": 0,
        },
        "compatibility_mode": "all",
    }
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(response), stderr="")

    monkeypatch.setattr(presentation_preview_compare.subprocess, "run", fake_run)

    result = _render_preview(
        Path("fixture.pptx"),
        tmp_path,
        compatibility_mode="all",
    )

    assert calls == [
        [
            "node",
            str(presentation_preview_compare.RENDERER_SCRIPT),
            "fixture.pptx",
            str(tmp_path),
            "all",
        ]
    ]
    assert result["compatibility_mode"] == "all"
