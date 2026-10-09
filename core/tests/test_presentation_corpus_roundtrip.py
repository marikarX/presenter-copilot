from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from PIL import Image

from presenter_core.tools.presentation_corpus_roundtrip import (
    AcceptanceFailure,
    PowerPointOpenValidator,
    _external_non_hyperlink_relationship_count,
    _pixel_mask_summary,
    _single_character_text_mutation,
    _stable_rendered_difference_mask,
)


def _package_with_relationships(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "relationships.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", body)
    return path


def test_external_hyperlinks_do_not_block_office_open(tmp_path) -> None:
    path = _package_with_relationships(
        tmp_path,
        """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship
        Id="rId1"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
        Target="https://example.invalid"
        TargetMode="External" />
        </Relationships>""",
    )

    assert _external_non_hyperlink_relationship_count(path) == 0


def test_external_media_and_object_links_are_counted(tmp_path) -> None:
    path = _package_with_relationships(
        tmp_path,
        """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship
        Id="rId1"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
        Target="https://example.invalid/image.png"
        TargetMode="External" />
        <Relationship
        Id="rId2"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/video"
        Target="https://example.invalid/video.mp4"
        TargetMode="External" />
        <Relationship
        Id="rId3"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
        Target="../slideLayouts/slideLayout1.xml" />
        </Relationships>""",
    )

    assert _external_non_hyperlink_relationship_count(path) == 2


def test_malformed_relationship_xml_fails_closed(tmp_path) -> None:
    path = _package_with_relationships(tmp_path, "<Relationships><Relationship")

    with pytest.raises(AcceptanceFailure) as error:
        _external_non_hyperlink_relationship_count(path)

    assert error.value.code == "POWERPOINT_RELATIONSHIPS_INVALID"


def test_visual_difference_must_stay_inside_target_shape() -> None:
    geometry = {
        "x_emu": 914_400,
        "y_emu": 514_350,
        "width_emu": 914_400,
        "height_emu": 514_350,
    }
    allowed_bounds = PowerPointOpenValidator._target_diff_allowed_bounds(
        geometry,
        9_144_000,
        5_143_500,
    )

    PowerPointOpenValidator._validate_target_diff_bounds(
        (126, 70, 200, 120),
        allowed_bounds,
    )
    with pytest.raises(AcceptanceFailure) as error:
        PowerPointOpenValidator._validate_target_diff_bounds(
            (100, 70, 200, 120),
            allowed_bounds,
        )

    assert allowed_bounds == (122, 66, 262, 150)
    assert error.value.code == "POWERPOINT_EDIT_VISUAL_ESCAPED_TARGET"


def test_visual_comparison_masks_instability_in_both_rendered_states() -> None:
    original = Image.new("RGB", (4, 4), "black")
    repeated_original = original.copy()
    repeated_original.putpixel((0, 0), (255, 255, 255))
    edited = original.copy()
    repeated_edited = original.copy()
    edited.putpixel((1, 1), (255, 255, 255))
    edited.putpixel((3, 3), (255, 255, 255))
    repeated_edited.putpixel((3, 3), (255, 255, 255))

    stable_changes, source_unstable, edited_unstable, total_unstable = (
        _stable_rendered_difference_mask(original, repeated_original, edited, repeated_edited)
    )

    assert (source_unstable, edited_unstable, total_unstable) == (1, 1, 2)
    assert _pixel_mask_summary(stable_changes) == (1, (3, 3, 4, 4))


def test_corpus_edit_changes_one_character_and_creates_a_novel_token() -> None:
    source = "Project overview"
    replacement, marker = _single_character_text_mutation(source, {"project", "overview"}) or (
        None,
        None,
    )

    assert isinstance(replacement, str)
    assert isinstance(marker, str)
    assert len(replacement) == len(source)
    assert sum(left != right for left, right in zip(source, replacement, strict=True)) == 1
    assert marker not in {"project", "overview"}
    assert marker in replacement.casefold().split()
