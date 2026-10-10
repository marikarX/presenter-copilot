"""Bounded OOXML inventory for imported presentations.

This module establishes document-lineage identities and a deliberately modest
fidelity inventory. Revision content is identified separately by its source
hash. It does not rewrite PPTX parts or claim that inventory alone makes a
deck safe to edit or export.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
import uuid
import zipfile
import zlib
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any, BinaryIO, cast

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError
from presenter_core.ingestion.security import (
    MAX_ARCHIVE_ENTRIES,
    MAX_ARCHIVE_EXPANDED_BYTES,
    MAX_EXTRACTED_TEXT_CHARS,
    MAX_SOURCE_BYTES,
)

PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MARKUP_COMPATIBILITY_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
SLIDE_REL_TYPE = f"{REL_NS}/slide"
NOTES_SLIDE_REL_TYPE = f"{REL_NS}/notesSlide"
XML_PART_LIMIT = 8 * 1024 * 1024
SLIDE_LIMIT = 5_000
OBJECT_LIMIT = 100_000
MAX_DECISION_OBJECT_TEXT_CHARS = 8_000
MAX_SPEAKER_NOTES_CHARS = 12_000
MAX_SPEAKER_NOTES_PARAGRAPHS = 128
MAX_SLIDE_DIMENSION_EMU = 100_000_000
EMU_PER_POINT = 12_700
MAX_TEXT_LEFT_INDENT_PT = 144
MAX_TEXT_LEFT_INDENT_EMU = EMU_PER_POINT * MAX_TEXT_LEFT_INDENT_PT
MAX_TEXT_FIRST_LINE_INDENT_PT = 144
MAX_TEXT_FIRST_LINE_INDENT_EMU = EMU_PER_POINT * MAX_TEXT_FIRST_LINE_INDENT_PT
MAX_TEXT_PARAGRAPH_SPACING_PT = 144
MAX_TEXT_PARAGRAPH_SPACING_HUNDREDTHS = MAX_TEXT_PARAGRAPH_SPACING_PT * 100
MAX_TEXT_LINE_SPACING_PT = 144
MAX_TEXT_LINE_SPACING_HUNDREDTHS = MAX_TEXT_LINE_SPACING_PT * 100
MAX_TEXT_FORMAT_PARAGRAPHS = 128
_PARAGRAPH_PROPERTY_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "lnSpc",
            "spcBef",
            "spcAft",
            "buClrTx",
            "buClr",
            "buSzTx",
            "buSzPct",
            "buSzPts",
            "buFontTx",
            "buFont",
            "buNone",
            "buAutoNum",
            "buChar",
            "buBlip",
            "tabLst",
            "defRPr",
            "extLst",
        )
    )
}
_PARAGRAPH_BULLET_PROPERTY_NAMES = frozenset(
    {
        "buClrTx",
        "buClr",
        "buSzTx",
        "buSzPct",
        "buSzPts",
        "buFontTx",
        "buFont",
        "buNone",
        "buAutoNum",
        "buChar",
        "buBlip",
    }
)
PARAGRAPH_BULLET_CHAR_BY_MODE = {
    "bullet": "•",
    "bullet_hollow": "◦",
    "bullet_square": "▪",
    "bullet_dash": "–",
}
_PARAGRAPH_BULLET_MODE_BY_CHAR = {
    character: mode for mode, character in PARAGRAPH_BULLET_CHAR_BY_MODE.items()
}
# Plain automatic numbering schemes; custom start values stay read-only.
PARAGRAPH_AUTONUM_TYPE_BY_MODE = {
    "numbered": "arabicPeriod",
    "numbered_paren": "arabicParenR",
    "numbered_alpha_lower": "alphaLcPeriod",
    "numbered_alpha_upper": "alphaUcPeriod",
    "numbered_roman_lower": "romanLcPeriod",
    "numbered_roman_upper": "romanUcPeriod",
}
_PARAGRAPH_MODE_BY_AUTONUM_TYPE = {
    kind: mode for mode, kind in PARAGRAPH_AUTONUM_TYPE_BY_MODE.items()
}
_PARAGRAPH_BULLET_TYPE_NAMES = frozenset({"buNone", "buAutoNum", "buChar", "buBlip"})
# Unicode text fonts that render the predefined glyphs; symbol fonts stay read-only.
_PLAIN_BULLET_FONTS = frozenset(
    {
        "+mn-lt",
        "+mj-lt",
        "Arial",
        "Calibri",
        "Calibri Light",
        "Helvetica",
        "Segoe UI",
        "Times New Roman",
        "Verdana",
        "Tahoma",
        "Georgia",
        "Aptos",
    }
)
MIN_BULLET_SIZE_PERCENT = 25
MAX_NUMBERING_START = 9999
MAX_BULLET_SIZE_PERCENT = 400
PARAGRAPH_BULLET_MODES = frozenset(
    {"none", *PARAGRAPH_AUTONUM_TYPE_BY_MODE, *PARAGRAPH_BULLET_CHAR_BY_MODE}
)
_XML_DECLARATION_PATTERN = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_IDENTITY_NAMESPACE = uuid.UUID("f3c3c788-716e-4c4c-9081-ff23a23c896f")
_NS = {"p": PRESENTATION_NS, "a": DRAWING_NS, "r": REL_NS, "rel": PACKAGE_REL_NS}
_OBJECT_KINDS = {"sp", "pic", "graphicFrame", "cxnSp", "grpSp"}
_OBJECT_KIND_REPORT_KEYS = {
    "sp": "shapes",
    "pic": "pictures",
    "graphicFrame": "graphic_frames",
    "cxnSp": "connectors",
    "grpSp": "groups",
}
_SUPPORTED_MARKUP_COMPATIBILITY_NAMESPACES = frozenset({PRESENTATION_NS, DRAWING_NS, REL_NS})


@dataclass(frozen=True)
class FidelityGeometry:
    """Slide-space dimensions in English Metric Units."""

    x_emu: int
    y_emu: int
    width_emu: int
    height_emu: int


@dataclass(frozen=True)
class FidelityPictureCrop:
    """Simple source-rectangle crop values in OOXML thousandths of a percent."""

    left: int = 0
    right: int = 0
    top: int = 0
    bottom: int = 0


@dataclass(frozen=True)
class FidelityHyperlink:
    """One click link shared by every text run: a web address, another slide, or none."""

    url: str | None = None
    slide_id: str | None = None


@dataclass(frozen=True)
class FidelityRotation:
    """Direct slide-level rotation (60000ths of a degree, normalized) and flips."""

    rotation: int = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False


@dataclass(frozen=True)
class FidelityPictureAdjustment:
    """Direct picture brightness/contrast (a:lum, whole percents) and grayscale."""

    brightness: int = 0
    contrast: int = 0
    grayscale: bool = False


@dataclass(frozen=True)
class FidelityTextStyle:
    """Direct run and paragraph formatting supported by the constrained formatter."""

    editable: bool
    fingerprint: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strikethrough: bool | None = None
    font_family: str | None = None
    highlight_color: str | None = None
    vertical_anchor: str | None = None
    columns: int | None = None
    font_size_pt: float | None = None
    font_color: str | None = None
    color_editable: bool = False
    alignment: str | None = None
    alignment_editable: bool = False
    bullet_state: str | None = None
    bullet_editable: bool = False
    left_indent_pt: int | None = None
    left_indent_editable: bool = False
    first_line_indent_pt: int | None = None
    first_line_indent_editable: bool = False
    line_spacing_pt: int | None = None
    line_spacing_editable: bool = False
    space_before_pt: int | None = None
    space_before_editable: bool = False
    space_after_pt: int | None = None
    space_after_editable: bool = False
    bullet_color: str | None = None
    bullet_color_editable: bool = False
    bullet_size_percent: int | None = None
    bullet_size_editable: bool = False
    numbering_start: int | None = None
    numbering_start_editable: bool = False


@dataclass(frozen=True)
class FidelityShapeStyle:
    """Direct solid fill and outline colors for a simple top-level shape."""

    editable: bool
    fingerprint: str | None = None
    fill_color: str | None = None
    fill_editable: bool = False
    fill_transparency_percent: int | None = None
    shadow: bool | None = None
    shadow_editable: bool = False
    shape_geometry: str | None = None
    line_color: str | None = None
    line_editable: bool = False
    line_width_pt: float | None = None
    line_dash: str | None = None
    line_format_editable: bool = False


DECORATIVE_EXT_URI = "{C183D7F6-B498-43B3-948B-1728B52AA6E4}"
DECORATIVE_NS = "http://schemas.microsoft.com/office/drawing/2017/decorative"


# Non-visual extensions that carry identity or accessibility only (a16:creationId,
# adec:decorative on cNvPr; p14:modId on nvPr); they move with the object and never
# change its rendering.
BENIGN_NONVISUAL_EXTENSIONS = frozenset(
    {
        "{FF2B5EF4-FFF2-40B4-BE49-F238E27FC236}",
        DECORATIVE_EXT_URI,
        "{D42A27DB-BD31-4B8C-83A1-F6EECF244321}",
    }
)


def has_unsafe_extensions(node: etree._Element) -> bool:
    """Placeholders or extension lists other than benign non-visual metadata."""
    return bool(node.xpath(".//p:ph", namespaces=_NS)) or has_unsafe_extension_lists(node)


def has_unsafe_extension_lists(node: etree._Element) -> bool:
    """Extension lists other than benign non-visual identity/accessibility metadata."""
    for extensions in node.xpath(".//p:extLst | .//a:extLst", namespaces=_NS):
        parent = extensions.getparent()
        if (
            parent is None
            or etree.QName(parent).localname not in {"cNvPr", "nvPr"}
            or any(
                child.tag != f"{{{DRAWING_NS}}}ext"
                or child.get("uri") not in BENIGN_NONVISUAL_EXTENSIONS
                for child in extensions
                if isinstance(child.tag, str)
            )
        ):
            return True
    return False


def refresh_creation_ids(node: etree._Element) -> None:
    """Give a copied object (and its children) new a16:creationId identities, as PowerPoint
    does on copy, so co-authoring never sees two objects with one identity."""
    import uuid

    for identity in node.xpath(".//*[local-name()='creationId'][@id]"):
        identity.set("id", "{" + str(uuid.uuid4()).upper() + "}")


def object_alt_text(nonvisual: etree._Element) -> tuple[str, bool]:
    """An object's alt text (cNvPr@descr) and PowerPoint's "Mark as decorative" flag."""
    flags = nonvisual.xpath(
        "./a:extLst/a:ext[@uri=$uri]/*[local-name()='decorative']/@val",
        namespaces=_NS,
        uri=DECORATIVE_EXT_URI,
    )
    return nonvisual.get("descr", ""), bool(flags) and flags[0] in {"1", "true"}


# Preset shape types offered for "change shape" (a:prstGeom@prst).
SHAPE_GEOMETRIES = frozenset(
    {
        "rect",
        "roundRect",
        "ellipse",
        "triangle",
        "diamond",
        "hexagon",
        "rightArrow",
        "chevron",
        "homePlate",
        "wedgeRoundRectCallout",
    }
)

# Preset outline dash styles exposed for editing (a:prstDash@val).
SHAPE_LINE_DASHES = frozenset(
    {"solid", "dash", "dot", "dashDot", "lgDash", "lgDashDot", "sysDash", "sysDot"}
)
EMU_PER_QUARTER_POINT = 3175
MAX_SHAPE_LINE_WIDTH_PT = 20


def _shape_line_format(line: etree._Element | None) -> tuple[float | None, str | None, bool]:
    """Direct outline width (points) and preset dash, and whether both are editable."""
    if line is None:
        return None, None, True
    width: float | None = None
    raw_width = line.get("w")
    if raw_width is not None:
        if not re.fullmatch(r"[0-9]{1,8}", raw_width):
            return None, None, False
        emu = int(raw_width)
        if emu % EMU_PER_QUARTER_POINT or emu > MAX_SHAPE_LINE_WIDTH_PT * EMU_PER_POINT:
            return None, None, False
        width = emu / EMU_PER_POINT
    if line.find(f"{{{DRAWING_NS}}}custDash") is not None:
        return width, None, False
    dash: str | None = None
    preset = line.find(f"{{{DRAWING_NS}}}prstDash")
    if preset is not None:
        dash = preset.get("val")
        if set(preset.attrib) != {"val"} or len(preset) or dash not in SHAPE_LINE_DASHES:
            return width, None, False
    return width, dash, True


@dataclass(frozen=True)
class FidelityObject:
    """One OOXML drawing object with a stable identity inside its source."""

    object_id: str
    ooxml_id: str
    name: str
    kind: str
    text: str
    text_edit_candidate: bool
    single_run_text_edit_candidate: bool
    uniform_run_text_edit_candidate: bool
    text_format_edit_candidate: bool
    geometry: FidelityGeometry | None = None
    geometry_editable: bool = False
    delete_editable: bool = False
    group_editable: bool = False
    group_reason: str | None = None
    text_style: FidelityTextStyle | None = None
    picture_crop: FidelityPictureCrop | None = None
    picture_adjustment: FidelityPictureAdjustment | None = None
    rotation: FidelityRotation | None = None
    hyperlink: FidelityHyperlink | None = None
    shape_style: FidelityShapeStyle | None = None
    semantic_source_kind: str | None = None
    alt_text: str | None = None
    decorative: bool = False
    geometry_inherited: bool = False
    group_child: bool = False


@dataclass(frozen=True)
class FidelityBackground:
    """A slide's own background: inherited from its layout, a theme style or solid RGB."""

    state: str
    color: str | None = None


@dataclass(frozen=True)
class FidelitySlide:
    """Slide ordering and stable objects derived from the immutable import."""

    slide_id: str
    ooxml_slide_id: str
    ordinal: int
    part_name: str
    objects: tuple[FidelityObject, ...]
    speaker_notes: str | None = None
    speaker_notes_editable: bool = False
    background: FidelityBackground | None = None
    hidden: bool = False
    transition: str | None = "none"


@dataclass(frozen=True)
class FidelityDocument:
    """A structural view of one verified original PPTX snapshot."""

    source_sha256: str
    slides: tuple[FidelitySlide, ...]
    slide_width_emu: int
    slide_height_emu: int

    @property
    def text_edit_candidate_count(self) -> int:
        return sum(obj.text_edit_candidate for slide in self.slides for obj in slide.objects)

    @property
    def object_count(self) -> int:
        return sum(len(slide.objects) for slide in self.slides)

    @property
    def object_kind_counts(self) -> dict[str, int]:
        counts = {key: 0 for key in _OBJECT_KIND_REPORT_KEYS.values()}
        for slide in self.slides:
            for obj in slide.objects:
                counts[_OBJECT_KIND_REPORT_KEYS[obj.kind]] += 1
        return counts

    @property
    def nontext_or_unmodeled_count(self) -> int:
        return self.object_count - self.text_edit_candidate_count

    def summary(self) -> dict[str, object]:
        """Return metadata only; slide content and package paths stay in Core."""
        return {
            "status": "inventory_only",
            "slide_count": len(self.slides),
            "object_count": self.object_count,
            "object_kinds": self.object_kind_counts,
            "text_edit_candidates": self.text_edit_candidate_count,
            "nontext_or_unmodeled_objects": self.nontext_or_unmodeled_count,
            "slides": [
                {
                    "slide_id": slide.slide_id,
                    "ordinal": slide.ordinal,
                    "object_count": len(slide.objects),
                }
                for slide in self.slides
            ],
        }

    def text_targets(self, ordinal: int, *, limit: int = 100) -> dict[str, object]:
        """Return bounded stable targets for one slide without exposing its XML path."""
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
            raise ValueError("slide ordinal must be positive")
        slide = next((item for item in self.slides if item.ordinal == ordinal), None)
        if slide is None:
            raise ValueError("slide ordinal is unavailable")
        targets = [obj for obj in slide.objects if obj.text_edit_candidate]
        objects = slide.objects[:limit]
        semantic = [
            obj
            for obj in slide.objects
            if obj.semantic_source_kind is not None
            and obj.text.strip()
            and _is_safe_decision_text(obj.text)
        ]
        return {
            "slide_id": slide.slide_id,
            "ordinal": slide.ordinal,
            "slide_width_emu": self.slide_width_emu,
            "slide_height_emu": self.slide_height_emu,
            "has_more": len(targets) > limit,
            "objects_have_more": len(slide.objects) > limit,
            "semantic_has_more": len(semantic) > limit,
            "semantic_excluded_objects": len(slide.objects) - len(semantic),
            "semantic_targets": [
                {
                    "object_id": obj.object_id,
                    "ooxml_shape_id": obj.ooxml_id,
                    "name": obj.name,
                    "source_kind": obj.semantic_source_kind,
                    "decision_text": obj.text,
                }
                for obj in semantic[:limit]
            ],
            "hidden": slide.hidden,
            "transition": slide.transition,
            "background": (
                {
                    "state": slide.background.state,
                    "color": slide.background.color,
                    "editable": True,
                }
                if slide.background is not None
                else {"state": "unsupported", "color": None, "editable": False}
            ),
            "speaker_notes": {
                "current_text": (
                    slide.speaker_notes[:MAX_SPEAKER_NOTES_CHARS]
                    if slide.speaker_notes is not None
                    else None
                ),
                "text_truncated": (
                    slide.speaker_notes is not None
                    and len(slide.speaker_notes) > MAX_SPEAKER_NOTES_CHARS
                ),
                "editable": (
                    slide.speaker_notes_editable
                    and slide.speaker_notes is not None
                    and len(slide.speaker_notes) <= MAX_SPEAKER_NOTES_CHARS
                ),
            },
            "targets": [
                {
                    "object_id": obj.object_id,
                    "ooxml_shape_id": obj.ooxml_id,
                    "single_run_editable": obj.single_run_text_edit_candidate,
                    "uniform_run_editable": obj.uniform_run_text_edit_candidate,
                    "text_format_editable": obj.text_format_edit_candidate,
                    "current_text": (
                        obj.text
                        if obj.single_run_text_edit_candidate
                        or obj.uniform_run_text_edit_candidate
                        or obj.text_format_edit_candidate
                        else None
                    ),
                    "text_style": (
                        {
                            "editable": obj.text_style.editable,
                            "fingerprint": obj.text_style.fingerprint,
                            "bold": obj.text_style.bold,
                            "italic": obj.text_style.italic,
                            "underline": obj.text_style.underline,
                            "strikethrough": obj.text_style.strikethrough,
                            "font_family": obj.text_style.font_family,
                            "highlight_color": obj.text_style.highlight_color,
                            "vertical_anchor": obj.text_style.vertical_anchor,
                            "columns": obj.text_style.columns,
                            "font_size_pt": obj.text_style.font_size_pt,
                            "font_color": obj.text_style.font_color,
                            "color_editable": obj.text_style.color_editable,
                            "alignment": obj.text_style.alignment,
                            "alignment_editable": obj.text_style.alignment_editable,
                            "bullet_state": obj.text_style.bullet_state,
                            "bullet_editable": obj.text_style.bullet_editable,
                            "left_indent_pt": obj.text_style.left_indent_pt,
                            "left_indent_editable": obj.text_style.left_indent_editable,
                            "first_line_indent_pt": obj.text_style.first_line_indent_pt,
                            "first_line_indent_editable": obj.text_style.first_line_indent_editable,
                            "line_spacing_pt": obj.text_style.line_spacing_pt,
                            "line_spacing_editable": obj.text_style.line_spacing_editable,
                            "space_before_pt": obj.text_style.space_before_pt,
                            "space_before_editable": obj.text_style.space_before_editable,
                            "space_after_pt": obj.text_style.space_after_pt,
                            "space_after_editable": obj.text_style.space_after_editable,
                            "bullet_color": obj.text_style.bullet_color,
                            "bullet_color_editable": obj.text_style.bullet_color_editable,
                            "bullet_size_percent": obj.text_style.bullet_size_percent,
                            "bullet_size_editable": obj.text_style.bullet_size_editable,
                            "numbering_start": obj.text_style.numbering_start,
                            "numbering_start_editable": (obj.text_style.numbering_start_editable),
                        }
                        if obj.text_style is not None
                        else None
                    ),
                    "decision_text": obj.text if _is_safe_decision_text(obj.text) else None,
                }
                for obj in targets[:limit]
            ],
            "objects": [
                {
                    "object_id": obj.object_id,
                    "ooxml_shape_id": obj.ooxml_id,
                    "name": obj.name,
                    "kind": obj.kind,
                    "geometry_editable": obj.geometry_editable,
                    "delete_editable": obj.delete_editable,
                    "group_editable": obj.group_editable,
                    "group_reason": obj.group_reason,
                    "alt_text": obj.alt_text,
                    "decorative": obj.decorative,
                    "geometry_inherited": obj.geometry_inherited,
                    "group_child": obj.group_child,
                    "shape_style": (
                        {
                            "editable": obj.shape_style.editable,
                            "fingerprint": obj.shape_style.fingerprint,
                            "fill_color": obj.shape_style.fill_color,
                            "fill_editable": obj.shape_style.fill_editable,
                            "fill_transparency_percent": (
                                obj.shape_style.fill_transparency_percent
                            ),
                            "shadow": obj.shape_style.shadow,
                            "shape_geometry": obj.shape_style.shape_geometry,
                            "shadow_editable": obj.shape_style.shadow_editable,
                            "line_color": obj.shape_style.line_color,
                            "line_editable": obj.shape_style.line_editable,
                            "line_width_pt": obj.shape_style.line_width_pt,
                            "line_dash": obj.shape_style.line_dash,
                            "line_format_editable": obj.shape_style.line_format_editable,
                        }
                        if obj.shape_style is not None
                        else None
                    ),
                    "picture_crop": (
                        {
                            "left_percent": obj.picture_crop.left / 1_000,
                            "right_percent": obj.picture_crop.right / 1_000,
                            "top_percent": obj.picture_crop.top / 1_000,
                            "bottom_percent": obj.picture_crop.bottom / 1_000,
                        }
                        if obj.picture_crop is not None
                        else None
                    ),
                    "hyperlink": (
                        {"url": obj.hyperlink.url, "slide_id": obj.hyperlink.slide_id}
                        if obj.hyperlink is not None
                        else None
                    ),
                    "rotation": (
                        {
                            "rotation_degrees": obj.rotation.rotation / 60_000,
                            "flip_horizontal": obj.rotation.flip_horizontal,
                            "flip_vertical": obj.rotation.flip_vertical,
                        }
                        if obj.rotation is not None
                        else None
                    ),
                    "picture_adjustment": (
                        {
                            "brightness_percent": obj.picture_adjustment.brightness,
                            "contrast_percent": obj.picture_adjustment.contrast,
                            "grayscale": obj.picture_adjustment.grayscale,
                        }
                        if obj.picture_adjustment is not None
                        else None
                    ),
                    "geometry": (
                        {
                            "x_emu": obj.geometry.x_emu,
                            "y_emu": obj.geometry.y_emu,
                            "width_emu": obj.geometry.width_emu,
                            "height_emu": obj.geometry.height_emu,
                        }
                        if obj.geometry is not None
                        else None
                    ),
                }
                for obj in objects
            ],
        }


def inspect_pptx_snapshot(
    handle: BinaryIO,
    *,
    document_id: str,
    expected_sha256: str,
    byte_size: int,
) -> FidelityDocument:
    """Inventory a previously verified open handle without modifying the file."""
    if (
        not isinstance(document_id, str)
        or not document_id
        or len(document_id) > 80
        or not isinstance(expected_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
        or isinstance(byte_size, bool)
        or not isinstance(byte_size, int)
        or not 0 < byte_size <= MAX_SOURCE_BYTES
    ):
        raise CoreDomainError(
            "PRESENTATION_FIDELITY_SOURCE_INVALID",
            "The stored presentation metadata is invalid.",
        )

    try:
        handle.seek(0)
        digest = hashlib.sha256()
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            raise CoreDomainError(
                "SOURCE_SNAPSHOT_CHANGED",
                "The stored presentation no longer matches its imported record.",
            )
        handle.seek(0)
        with zipfile.ZipFile(handle, "r") as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise _invalid_package()
            expanded_size = sum(max(0, info.file_size) for info in infos)
            if expanded_size > MAX_ARCHIVE_EXPANDED_BYTES:
                raise _invalid_package()
            members = {info.filename: info for info in infos}
            presentation_info = members.get("ppt/presentation.xml")
            rels_info = members.get("ppt/_rels/presentation.xml.rels")
            if presentation_info is None or rels_info is None:
                raise _invalid_package()
            presentation_root = _parse_xml_part(archive, presentation_info)
            relationships_root = _parse_xml_part(archive, rels_info)
            slide_sizes = presentation_root.xpath("./p:sldSz", namespaces=_NS)
            if len(slide_sizes) != 1:
                raise _invalid_package()
            try:
                slide_width_emu = int(slide_sizes[0].get("cx", ""))
                slide_height_emu = int(slide_sizes[0].get("cy", ""))
            except ValueError as error:
                raise _invalid_package() from error
            if not (
                0 < slide_width_emu <= MAX_SLIDE_DIMENSION_EMU
                and 0 < slide_height_emu <= MAX_SLIDE_DIMENSION_EMU
            ):
                raise _invalid_package()
            relationships = _relationships(relationships_root)
            slide_ids = presentation_root.xpath("./p:sldIdLst/p:sldId", namespaces=_NS)
            if not slide_ids or len(slide_ids) > SLIDE_LIMIT:
                raise _invalid_package()

            slides: list[FidelitySlide] = []
            seen_slide_ids: set[str] = set()
            total_objects = 0
            total_text_chars = 0
            # Slide part -> stable slide id, so slide-jump links resolve to identities.
            slide_part_ids: dict[str, str] = {}
            for slide_ref in slide_ids:
                relation = relationships.get(slide_ref.get(f"{{{REL_NS}}}id") or "")
                if relation is not None and relation[0] == SLIDE_REL_TYPE:
                    slide_part_ids[_resolve_internal_part("ppt", relation[1])] = _stable_id(
                        f"{document_id}\0identity-v1\0slide\0{slide_ref.get('id')}"
                    )
            layout_geometry: dict[str, dict[str, dict[str, FidelityGeometry]]] = {}
            for ordinal, slide_ref in enumerate(slide_ids, start=1):
                ooxml_slide_id = slide_ref.get("id")
                relationship_id = slide_ref.get(f"{{{REL_NS}}}id")
                if not ooxml_slide_id or ooxml_slide_id in seen_slide_ids or not relationship_id:
                    raise _invalid_package()
                seen_slide_ids.add(ooxml_slide_id)
                relationship = relationships.get(relationship_id)
                if relationship is None:
                    raise _invalid_package()
                relationship_type, target, target_mode = relationship
                if relationship_type != SLIDE_REL_TYPE or target_mode.casefold() != "internal":
                    raise _invalid_package()
                part_name = _resolve_internal_part("ppt", target)
                slide_info = members.get(part_name)
                if slide_info is None:
                    raise _invalid_package()
                slide_root = _parse_xml_part(archive, slide_info)
                from presenter_core.presentation.charts import chart_texts
                from presenter_core.presentation.group_geometry import grouping_picture_ids

                objects = _objects_for_slide(
                    slide_root,
                    document_id=document_id,
                    ooxml_slide_id=ooxml_slide_id,
                    slide_width_emu=slide_width_emu,
                    slide_height_emu=slide_height_emu,
                    chart_text=chart_texts(archive, members, slide_root, part_name),
                    group_picture_ids=grouping_picture_ids(archive, members, slide_root, part_name),
                    hyperlink_targets=slide_hyperlink_targets(
                        archive, members, part_name, slide_part_ids
                    ),
                    inherited_geometry=placeholder_geometry_map(
                        archive, members, part_name, layout_geometry
                    ),
                )
                speaker_notes, notes_editable = _speaker_notes_for_slide(
                    archive,
                    members,
                    slide_part_name=part_name,
                )
                total_objects += len(objects)
                total_text_chars += sum(len(obj.text) for obj in objects) + len(speaker_notes or "")
                if total_objects > OBJECT_LIMIT or total_text_chars > MAX_EXTRACTED_TEXT_CHARS:
                    raise CoreDomainError(
                        "PRESENTATION_FIDELITY_RESOURCE_LIMIT",
                        "The presentation contains more editable content than the workspace limit.",
                    )
                slide_identity = _stable_id(f"{document_id}\0identity-v1\0slide\0{ooxml_slide_id}")
                slides.append(
                    FidelitySlide(
                        slide_id=slide_identity,
                        ooxml_slide_id=ooxml_slide_id,
                        ordinal=ordinal,
                        part_name=part_name,
                        objects=objects,
                        speaker_notes=speaker_notes,
                        speaker_notes_editable=notes_editable,
                        background=slide_background(slide_root),
                        hidden=slide_hidden(slide_root),
                        transition=slide_transition(slide_root),
                    )
                )
            result = FidelityDocument(
                source_sha256=expected_sha256,
                slides=tuple(slides),
                slide_width_emu=slide_width_emu,
                slide_height_emu=slide_height_emu,
            )
            handle.seek(0)
            verified_digest = hashlib.sha256()
            while chunk := handle.read(1024 * 1024):
                verified_digest.update(chunk)
            if verified_digest.hexdigest() != expected_sha256:
                raise CoreDomainError(
                    "SOURCE_SNAPSHOT_CHANGED",
                    "The stored presentation no longer matches its imported record.",
                )
            handle.seek(0)
            return result
    except CoreDomainError:
        raise
    except (
        OSError,
        EOFError,
        ValueError,
        KeyError,
        RuntimeError,
        zlib.error,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ) as error:
        raise _invalid_package() from error


def _parse_xml_part(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> etree._Element:
    if info.file_size <= 0 or info.file_size > XML_PART_LIMIT:
        raise _invalid_package()
    payload = archive.read(info)
    if _XML_DECLARATION_PATTERN.search(payload):
        raise _invalid_package()
    try:
        parser = etree.XMLParser(
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            huge_tree=False,
            remove_comments=False,
            recover=False,
        )
        root = etree.fromstring(payload, parser)
    except (etree.XMLSyntaxError, ValueError) as error:
        raise _invalid_package() from error
    if root.getroottree().docinfo.doctype:
        raise _invalid_package()
    return root


def _relationships(root: etree._Element) -> dict[str, tuple[str, str, str]]:
    result: dict[str, tuple[str, str, str]] = {}
    for relationship in root.xpath("./rel:Relationship", namespaces=_NS):
        relationship_id = relationship.get("Id")
        relationship_type = relationship.get("Type")
        target = relationship.get("Target")
        target_mode = relationship.get("TargetMode", "Internal")
        if not relationship_id or not relationship_type or not target or relationship_id in result:
            raise _invalid_package()
        result[relationship_id] = (relationship_type, target, target_mode)
    return result


def _resolve_internal_part(base_directory: str, target: str) -> str:
    if (
        not target
        or len(target) > 512
        or "\\" in target
        or "%" in target
        or "?" in target
        or "#" in target
        or ":" in target
        or any(ord(character) < 32 for character in target)
    ):
        raise _invalid_package()
    candidate = (
        target.lstrip("/") if target.startswith("/") else posixpath.join(base_directory, target)
    )
    normalized = posixpath.normpath(candidate)
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or normalized in {"", "."}
        or normalized == ".."
        or normalized.startswith("../")
    ):
        raise _invalid_package()
    return normalized


def _speaker_notes_for_slide(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    *,
    slide_part_name: str,
) -> tuple[str | None, bool]:
    """Read a slide's body-placeholder notes and classify plain-text editability."""
    slide_path = PurePosixPath(slide_part_name)
    rels_part = f"{slide_path.parent.as_posix()}/_rels/{slide_path.name}.rels"
    rels_info = members.get(rels_part)
    if rels_info is None:
        return None, False
    rels_root = _parse_xml_part(archive, rels_info)
    relationships = _relationships(rels_root)
    notes_relationships = [
        relation for relation in relationships.values() if relation[0] == NOTES_SLIDE_REL_TYPE
    ]
    if not notes_relationships:
        return None, False
    if len(notes_relationships) != 1:
        raise _invalid_package()
    _, target, target_mode = notes_relationships[0]
    if target_mode.casefold() != "internal":
        return None, False
    notes_part = _resolve_internal_part(slide_path.parent.as_posix(), target)
    notes_info = members.get(notes_part)
    if notes_info is None:
        raise _invalid_package()
    notes_root = _parse_xml_part(archive, notes_info)
    if notes_root.tag != f"{{{PRESENTATION_NS}}}notes":
        raise _invalid_package()
    placeholders = notes_root.xpath(
        "./p:cSld/p:spTree/p:sp[p:nvSpPr/p:nvPr/p:ph[@type='body']]",
        namespaces=_NS,
    )
    if not placeholders:
        return None, False
    if len(placeholders) != 1:
        raise _invalid_package()
    text_bodies = placeholders[0].xpath("./p:txBody", namespaces=_NS)
    if len(text_bodies) != 1:
        return None, False
    paragraphs = text_bodies[0].xpath("./a:p", namespaces=_NS)
    if not paragraphs or len(paragraphs) > MAX_SPEAKER_NOTES_PARAGRAPHS:
        return None, False
    text = "\n".join(_paragraph_text(paragraph) for paragraph in paragraphs)
    return text, _notes_body_is_plain_editable(paragraphs)


def _paragraph_text(paragraph: etree._Element) -> str:
    return "".join(part.text or "" for part in paragraph.xpath(".//a:t", namespaces=_NS))


def _notes_body_is_plain_editable(paragraphs: list[etree._Element]) -> bool:
    """Only declare notes editable when paragraph and run formatting is uniform."""
    signatures: set[tuple[bytes, bytes, bytes]] = set()
    for paragraph in paragraphs:
        if paragraph.xpath(".//a:br | .//a:fld", namespaces=_NS):
            return False
        if any(
            child.tag
            not in {
                f"{{{DRAWING_NS}}}pPr",
                f"{{{DRAWING_NS}}}r",
                f"{{{DRAWING_NS}}}endParaRPr",
            }
            for child in paragraph
        ):
            return False
        runs = paragraph.xpath("./a:r", namespaces=_NS)
        if len(runs) > 1:
            return False
        run_properties: etree._Element | None = None
        if runs:
            text_nodes = runs[0].xpath("./a:t", namespaces=_NS)
            if len(text_nodes) != 1 or any(
                child.tag not in {f"{{{DRAWING_NS}}}rPr", f"{{{DRAWING_NS}}}t"} for child in runs[0]
            ):
                return False
            run_properties_list = runs[0].xpath("./a:rPr", namespaces=_NS)
            if len(run_properties_list) > 1:
                return False
            run_properties = run_properties_list[0] if run_properties_list else None
            if run_properties is not None and run_properties.xpath(
                ".//a:hlinkClick | .//a:hlinkMouseOver", namespaces=_NS
            ):
                return False
        paragraph_properties = paragraph.find(f"{{{DRAWING_NS}}}pPr")
        end_properties = paragraph.find(f"{{{DRAWING_NS}}}endParaRPr")
        signatures.add(
            (
                _xml_signature(paragraph_properties),
                _xml_signature(run_properties),
                _xml_signature(end_properties),
            )
        )
    return len(signatures) == 1


def _xml_signature(element: etree._Element | None) -> bytes:
    return etree.tostring(element, method="c14n") if element is not None else b""


def _objects_for_slide(
    root: etree._Element,
    *,
    document_id: str,
    ooxml_slide_id: str,
    slide_width_emu: int,
    slide_height_emu: int,
    chart_text: dict[str, str] | None = None,
    group_picture_ids: set[str] | None = None,
    hyperlink_targets: dict[str, tuple[str, str]] | None = None,
    inherited_geometry: dict[str, dict[str, FidelityGeometry]] | None = None,
) -> tuple[FidelityObject, ...]:
    shape_tree = root.find(f".//{{{PRESENTATION_NS}}}spTree")
    if shape_tree is None:
        raise _invalid_package()
    result: list[FidelityObject] = []
    seen_ooxml_ids: set[str] = set()
    for candidate, alternate_content in _iter_slide_objects(shape_tree):
        kind = etree.QName(candidate).localname
        nonvisual = candidate.xpath(
            "./p:nvSpPr/p:cNvPr | ./p:nvPicPr/p:cNvPr | "
            "./p:nvGraphicFramePr/p:cNvPr | ./p:nvCxnSpPr/p:cNvPr | "
            "./p:nvGrpSpPr/p:cNvPr",
            namespaces=_NS,
        )
        if len(nonvisual) != 1:
            raise _invalid_package()
        ooxml_id = nonvisual[0].get("id")
        if not ooxml_id or ooxml_id in seen_ooxml_ids:
            raise _invalid_package()
        seen_ooxml_ids.add(ooxml_id)
        name = nonvisual[0].get("name") or f"{kind} {ooxml_id}"
        alt_text, decorative = object_alt_text(nonvisual[0])
        paragraphs = candidate.xpath("./p:txBody/a:p", namespaces=_NS)
        text = "\n".join(
            "".join(part.text or "" for part in paragraph.xpath(".//a:t", namespaces=_NS))
            for paragraph in paragraphs
        )
        semantic_kind = None
        if kind == "graphicFrame" and not alternate_content:
            text = (chart_text or {}).get(ooxml_id, "")
            if text:
                semantic_kind = "native_chart_cache"
            from presenter_core.presentation.tables import inspect_table

            table = inspect_table(candidate)
            if table and table["editable"]:
                text = "\n".join("\t".join(row) for row in table["cells"])
                semantic_kind = "native_table_cells"
        has_text_body = bool(candidate.xpath("./p:txBody", namespaces=_NS))
        text_edit_candidate = kind == "sp" and has_text_body
        single_run_text_edit_candidate = _is_single_run_text_shape(candidate, kind) and (
            len(text) <= 2_000
            and not any(
                (ord(character) < 32 and character != "\t") or 0xD800 <= ord(character) <= 0xDFFF
                for character in text
            )
        )
        text_style = _text_style_for_shape(candidate, kind)
        uniform_run_text_edit_candidate = _is_uniform_run_text_shape(candidate, kind) and (
            len(text) <= 2_000
            and text_style.editable
            and not any(
                (ord(character) < 32 and character != "\t") or 0xD800 <= ord(character) <= 0xDFFF
                for character in text
            )
        )
        text_format_edit_candidate = _is_formatable_text_shape(candidate, kind) and (
            len(text) <= 2_000
            and text_style.editable
            and not any(
                (ord(character) < 32 and character not in "\t\n")
                or 0xD800 <= ord(character) <= 0xDFFF
                for character in text
            )
        )
        shape_style = _shape_style(candidate, kind, shape_tree=shape_tree)
        if alternate_content:
            text_style = replace(
                text_style,
                editable=False,
                color_editable=False,
                alignment_editable=False,
            )
            if shape_style is not None:
                shape_style = replace(
                    shape_style,
                    editable=False,
                    fill_editable=False,
                    line_editable=False,
                )
        from presenter_core.presentation.group_geometry import group_reason, read_geometry

        grouping_reason = group_reason(candidate, root, group_picture_ids or set())
        geometry, geometry_editable = _geometry_for_object(
            candidate,
            kind=kind,
            shape_tree=shape_tree,
            slide_width_emu=slide_width_emu,
            slide_height_emu=slide_height_emu,
        )
        geometry_inherited = False
        if geometry is None and kind in {"sp", "pic"} and not alternate_content:
            geometry = _inherited_placeholder_geometry(candidate, inherited_geometry or {})
            geometry_inherited = geometry is not None
            geometry_editable = bool(
                geometry is not None
                and candidate.getparent() is shape_tree
                and candidate.xpath("./p:spPr", namespaces=_NS)
                and not candidate.xpath("./p:spPr/a:xfrm", namespaces=_NS)
                and geometry.x_emu >= 0
                and geometry.y_emu >= 0
                and geometry.width_emu > 0
                and geometry.height_emu > 0
                and geometry.x_emu + geometry.width_emu <= slide_width_emu
                and geometry.y_emu + geometry.height_emu <= slide_height_emu
            )
        group_child = False
        parent = candidate.getparent()
        if (
            kind in {"sp", "pic"}
            and not alternate_content
            and parent is not None
            and parent.tag == f"{{{PRESENTATION_NS}}}grpSp"
            and parent.getparent() is shape_tree
        ):
            from presenter_core.presentation.group_geometry import (
                box_transform,
                promoted_geometry,
                simple_transform,
            )

            # The group must be unrotated; a rotated or flipped child keeps its rotation.
            if simple_transform(parent) and box_transform(candidate):
                # Report slide coordinates; edits stay inside the group's frame.
                outer, _ = read_geometry(parent)
                geometry = promoted_geometry(parent, candidate)
                group_child = True
                geometry_editable = bool(
                    outer is not None
                    and geometry.width_emu > 0
                    and geometry.height_emu > 0
                    and outer.x_emu <= geometry.x_emu
                    and outer.y_emu <= geometry.y_emu
                    and geometry.x_emu + geometry.width_emu <= outer.x_emu + outer.width_emu
                    and geometry.y_emu + geometry.height_emu <= outer.y_emu + outer.height_emu
                )
        if kind == "grpSp":
            geometry, _ = read_geometry(candidate)
            geometry_editable = bool(
                candidate.getparent() is shape_tree
                and grouping_reason is None
                and geometry
                and geometry.x_emu >= 0
                and geometry.y_emu >= 0
                and geometry.x_emu + geometry.width_emu <= slide_width_emu
                and geometry.y_emu + geometry.height_emu <= slide_height_emu
            )
        if not geometry_editable and grouping_reason is None:
            grouping_reason = (
                "This object does not have supported geometry within the slide bounds."
            )
        if candidate.getparent() is not shape_tree:
            grouping_reason = "Select the containing group to change its membership."
        delete_editable = _delete_geometry_candidate(
            root,
            candidate,
            kind=kind,
            ooxml_id=ooxml_id,
            geometry_editable=geometry_editable,
        )
        if kind == "grpSp":
            # Group eligibility recursively checks every descendant's native dependencies.
            delete_editable = geometry_editable and grouping_reason is None
        object_id = _stable_id(
            f"{document_id}\0identity-v1\0slide\0{ooxml_slide_id}\0object\0{ooxml_id}"
        )
        result.append(
            FidelityObject(
                object_id=object_id,
                ooxml_id=ooxml_id,
                name=name[:256],
                kind=kind,
                text=text,
                text_edit_candidate=text_edit_candidate and not alternate_content,
                single_run_text_edit_candidate=(
                    single_run_text_edit_candidate and not alternate_content
                ),
                uniform_run_text_edit_candidate=(
                    uniform_run_text_edit_candidate and not alternate_content
                ),
                text_format_edit_candidate=text_format_edit_candidate and not alternate_content,
                geometry=geometry,
                geometry_editable=geometry_editable and not alternate_content,
                delete_editable=delete_editable and not alternate_content and not group_child,
                group_editable=geometry_editable
                and grouping_reason is None
                and not alternate_content
                and not group_child,
                group_reason=grouping_reason
                if not alternate_content
                else "Alternate-content objects are read-only.",
                text_style=text_style,
                picture_crop=None if alternate_content else _picture_crop(candidate, kind),
                picture_adjustment=(
                    None if alternate_content else _picture_adjustment(candidate, kind)
                ),
                rotation=(
                    None
                    if alternate_content or group_child
                    else object_rotation(candidate, kind, shape_tree)
                ),
                hyperlink=(
                    shape_hyperlink(candidate, hyperlink_targets or {})
                    if not alternate_content
                    and kind == "sp"
                    and text_style is not None
                    and text_style.editable
                    else None
                ),
                shape_style=shape_style,
                alt_text=None if alternate_content else alt_text,
                decorative=decorative,
                geometry_inherited=geometry_inherited,
                group_child=group_child,
                semantic_source_kind="native_text"
                if text_edit_candidate and not alternate_content
                else semantic_kind,
            )
        )
    return tuple(result)


def _iter_slide_objects(
    shape_tree: etree._Element,
) -> tuple[tuple[etree._Element, bool], ...]:
    """Walk effective slide-tree shapes without entering opaque object payloads.

    Markup-compatibility alternatives represent one logical drawing object. The
    inventory selects the first Choice whose required namespaces it supports,
    otherwise the Fallback, and marks that representation read-only because
    edit writers preserve the unselected branch without rewriting it.
    """
    result: list[tuple[etree._Element, bool]] = []
    pending: list[tuple[etree._Element, bool]] = [(child, False) for child in reversed(shape_tree)]
    while pending:
        node, alternate_content = pending.pop()
        qualified_name = etree.QName(node)
        if qualified_name.namespace == MARKUP_COMPATIBILITY_NS:
            if qualified_name.localname != "AlternateContent":
                raise _invalid_package()
            branch = _selected_alternate_content_branch(node)
            if branch is None:
                raise _invalid_package()
            pending.extend((child, True) for child in reversed(branch))
            continue
        if qualified_name.namespace != PRESENTATION_NS:
            continue
        if qualified_name.localname in _OBJECT_KINDS:
            result.append((node, alternate_content))
            if qualified_name.localname == "grpSp":
                pending.extend((child, alternate_content) for child in reversed(node))
    return tuple(result)


def _selected_alternate_content_branch(
    alternate_content: etree._Element,
) -> etree._Element | None:
    choices: list[etree._Element] = []
    fallback: etree._Element | None = None
    fallback_seen = False
    for child in alternate_content:
        qualified_name = etree.QName(child)
        if qualified_name.namespace != MARKUP_COMPATIBILITY_NS:
            raise _invalid_package()
        if qualified_name.localname == "Choice":
            if fallback_seen:
                raise _invalid_package()
            choices.append(child)
        elif qualified_name.localname == "Fallback":
            if fallback is not None:
                raise _invalid_package()
            fallback = child
            fallback_seen = True
        else:
            raise _invalid_package()
    if not choices:
        raise _invalid_package()

    for choice in choices:
        required_prefixes = choice.get("Requires", "").split()
        if not required_prefixes:
            raise _invalid_package()
        required_namespaces = [choice.nsmap.get(prefix) for prefix in required_prefixes]
        if any(namespace is None for namespace in required_namespaces):
            raise _invalid_package()
        if all(
            namespace in _SUPPORTED_MARKUP_COMPATIBILITY_NAMESPACES
            for namespace in required_namespaces
        ):
            return choice
    return fallback


def _picture_crop(candidate: etree._Element, kind: str) -> FidelityPictureCrop | None:
    """Describe only a simple embedded picture fill that supports source cropping."""
    if kind != "pic":
        return None
    fills = candidate.xpath("./p:blipFill", namespaces=_NS)
    if len(fills) != 1:
        return None
    fill = fills[0]
    blips = fill.xpath("./a:blip", namespaces=_NS)
    source_rectangles = fill.xpath("./a:srcRect", namespaces=_NS)
    stretches = fill.xpath("./a:stretch", namespaces=_NS)
    if (
        len(blips) != 1
        or len(source_rectangles) > 1
        or len(stretches) != 1
        or [child.tag for child in fill]
        != [
            f"{{{DRAWING_NS}}}blip",
            *([f"{{{DRAWING_NS}}}srcRect"] if source_rectangles else []),
            f"{{{DRAWING_NS}}}stretch",
        ]
        or len(stretches[0]) != 1
        or stretches[0][0].tag != f"{{{DRAWING_NS}}}fillRect"
    ):
        return None
    blip = blips[0]
    if (
        not blip.get(f"{{{REL_NS}}}embed")
        or blip.get(f"{{{REL_NS}}}link") is not None
        or blip.xpath("./a:extLst", namespaces=_NS)
    ):
        return None

    values: dict[str, int] = {"l": 0, "r": 0, "t": 0, "b": 0}
    if source_rectangles:
        rectangle = source_rectangles[0]
        if set(rectangle.attrib) - values.keys():
            return None
        try:
            values.update({name: int(rectangle.get(name, "0")) for name in values})
        except ValueError:
            return None
    left, right, top, bottom = (
        values["l"],
        values["r"],
        values["t"],
        values["b"],
    )
    if (
        any(value < 0 or value >= 100_000 for value in values.values())
        or left + right >= 100_000
        or top + bottom >= 100_000
    ):
        return None
    return FidelityPictureCrop(left=left, right=right, top=top, bottom=bottom)


def _picture_adjustment(candidate: etree._Element, kind: str) -> FidelityPictureAdjustment | None:
    """Editable only for a simple embedded picture with at most grayscl and lum."""
    if _picture_crop(candidate, kind) is None:
        return None
    blip = candidate.find(f"{{{PRESENTATION_NS}}}blipFill/{{{DRAWING_NS}}}blip")
    if blip is None:
        return None
    names = [child.tag.removeprefix(f"{{{DRAWING_NS}}}") for child in blip]
    if any(name not in {"grayscl", "lum"} for name in names) or len(set(names)) != len(names):
        return None
    grayscale = blip.find(f"{{{DRAWING_NS}}}grayscl")
    if grayscale is not None and (grayscale.attrib or len(grayscale)):
        return None
    brightness = contrast = 0
    luminance = blip.find(f"{{{DRAWING_NS}}}lum")
    if luminance is not None:
        if len(luminance) or not set(luminance.attrib) <= {"bright", "contrast"}:
            return None
        for attribute in ("bright", "contrast"):
            raw = luminance.get(attribute, "0")
            if not re.fullmatch(r"-?[0-9]{1,6}", raw):
                return None
            value = int(raw)
            if value % 1000 or not -100_000 <= value <= 100_000:
                return None
            if attribute == "bright":
                brightness = value // 1000
            else:
                contrast = value // 1000
    return FidelityPictureAdjustment(
        brightness=brightness, contrast=contrast, grayscale=grayscale is not None
    )


def _shape_style(
    candidate: etree._Element,
    kind: str,
    *,
    shape_tree: etree._Element,
) -> FidelityShapeStyle:
    """Expose only direct RGB colors that can be replaced without flattening effects."""
    if (
        kind not in {"sp", "pic"}
        or candidate.getparent() is not shape_tree
        or candidate.xpath("./p:nvSpPr/p:nvPr/p:ph | ./p:nvPicPr/p:nvPr/p:ph", namespaces=_NS)
    ):
        return FidelityShapeStyle(editable=False)
    properties = candidate.xpath("./p:spPr", namespaces=_NS)
    if len(properties) != 1:
        return FidelityShapeStyle(editable=False)
    shape_properties = properties[0]
    shape_property_order = {
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
    fingerprint = hashlib.sha256(etree.tostring(shape_properties, method="c14n")).hexdigest()
    if not _ordered_property_children_supported(
        shape_properties, shape_property_order, repeatable_ranks={2}
    ):
        return FidelityShapeStyle(editable=False, fingerprint=fingerprint)
    shape_fill_tags = {
        f"{{{DRAWING_NS}}}noFill",
        f"{{{DRAWING_NS}}}solidFill",
        f"{{{DRAWING_NS}}}gradFill",
        f"{{{DRAWING_NS}}}blipFill",
        f"{{{DRAWING_NS}}}pattFill",
        f"{{{DRAWING_NS}}}grpFill",
    }
    fill_editable, fill_color = _solid_rgb_color(
        shape_properties, shape_fill_tags, allow_alpha=True
    )
    fill_transparency = _solid_fill_transparency(shape_properties) if fill_editable else None
    lines = shape_properties.findall(f"{{{DRAWING_NS}}}ln")
    if len(lines) > 1:
        line_editable, line_color = False, None
    elif not lines:
        line_editable, line_color = True, None
    else:
        line_property_order = {
            "noFill": 0,
            "solidFill": 0,
            "gradFill": 0,
            "blipFill": 0,
            "pattFill": 0,
            "grpFill": 0,
            "prstDash": 1,
            "custDash": 2,
            "round": 3,
            "bevel": 4,
            "miter": 5,
            "headEnd": 6,
            "tailEnd": 7,
            "extLst": 8,
        }
        line_editable = _ordered_property_children_supported(
            lines[0], line_property_order, repeatable_ranks={0}
        )
        if line_editable:
            line_editable, line_color = _solid_rgb_color(lines[0], shape_fill_tags)
        else:
            line_color = None
    structure_ok = len(lines) <= 1 and (
        not lines
        or _ordered_property_children_supported(lines[0], line_property_order, repeatable_ranks={0})
    )
    line_width_pt, line_dash, line_format_editable = (
        _shape_line_format(lines[0] if lines else None) if structure_ok else (None, None, False)
    )
    shadow_editable, shadow = _shape_shadow(shape_properties)
    if kind == "pic":
        # A picture's fill is its image: only the border and shadow are styled here.
        fill_editable, fill_color, fill_transparency = False, None, None
    geometry = shape_properties.find(f"{{{DRAWING_NS}}}prstGeom")
    shape_geometry = (
        geometry.get("prst")
        if kind == "sp" and geometry is not None and geometry.get("prst") in SHAPE_GEOMETRIES
        else None
    )
    return FidelityShapeStyle(
        shape_geometry=shape_geometry,
        editable=fill_editable or line_editable or line_format_editable or shadow_editable,
        fingerprint=fingerprint,
        shadow=shadow,
        shadow_editable=shadow_editable,
        fill_color=fill_color,
        fill_editable=fill_editable,
        fill_transparency_percent=fill_transparency,
        line_color=line_color,
        line_editable=line_editable,
        line_width_pt=line_width_pt,
        line_dash=line_dash,
        line_format_editable=line_format_editable,
    )


def _shape_shadow(shape_properties: etree._Element) -> tuple[bool, bool | None]:
    """(editable, shadow): theme-driven (None), explicit none (False) or one outer shadow."""
    effects = shape_properties.findall(f"{{{DRAWING_NS}}}effectLst")
    if shape_properties.find(f"{{{DRAWING_NS}}}effectDag") is not None or len(effects) > 1:
        return False, None
    if not effects:
        return True, None
    children = list(effects[0])
    if effects[0].attrib:
        return False, None
    if not children:
        return True, False
    if len(children) == 1 and children[0].tag == f"{{{DRAWING_NS}}}outerShdw":
        return True, True
    return False, None


def _ordered_property_children_supported(
    parent: etree._Element,
    order: dict[str, int],
    *,
    repeatable_ranks: set[int],
) -> bool:
    ranks: list[int] = []
    seen: set[int] = set()
    for child in parent:
        rank = order.get(etree.QName(child).localname)
        if rank is None or (rank in seen and rank not in repeatable_ranks):
            return False
        ranks.append(rank)
        seen.add(rank)
    return ranks == sorted(ranks)


def _alpha_value(color: etree._Element) -> int | None:
    """Whole-percent opacity of a color's only a:alpha child, or None when unsupported."""
    if len(color) != 1 or color[0].tag != f"{{{DRAWING_NS}}}alpha":
        return None
    alpha = color[0]
    raw = alpha.get("val", "")
    if set(alpha.attrib) != {"val"} or len(alpha) or not re.fullmatch(r"[0-9]{1,6}", raw):
        return None
    value = int(raw)
    return value // 1000 if value % 1000 == 0 and value <= 100_000 else None


def _solid_fill_transparency(container: etree._Element) -> int | None:
    """0-100 transparency of a direct solid fill; None without a solid fill."""
    fill = container.find(f"{{{DRAWING_NS}}}solidFill")
    if fill is None or len(fill) != 1:
        return None
    if not len(fill[0]):
        return 0
    opacity = _alpha_value(fill[0])
    return None if opacity is None else 100 - opacity


def _solid_rgb_color(
    container: etree._Element, fill_tags: set[str], *, allow_alpha: bool = False
) -> tuple[bool, str | None]:
    """Accept an absent fill, noFill, or one unmodified solid RGB/theme color."""
    fills = [child for child in container if child.tag in fill_tags]
    if not fills:
        return True, None
    if len(fills) != 1:
        return False, None
    fill = fills[0]
    if fill.tag == f"{{{DRAWING_NS}}}noFill":
        return not len(fill) and not fill.attrib, None
    if fill.tag != f"{{{DRAWING_NS}}}solidFill" or fill.attrib or len(fill) != 1:
        return False, None
    color = fill[0]
    if (
        color.tag
        not in {
            f"{{{DRAWING_NS}}}srgbClr",
            f"{{{DRAWING_NS}}}schemeClr",
        }
        or set(color.attrib) != {"val"}
        or (len(color) and not (allow_alpha and _alpha_value(color) is not None))
    ):
        return False, None
    if color.tag == f"{{{DRAWING_NS}}}srgbClr":
        value = color.get("val", "")
        if re.fullmatch(r"[0-9A-Fa-f]{6}", value):
            return True, f"#{value.upper()}"
        return False, None
    return True, None


_BACKGROUND_FILLS = frozenset(
    f"{{{DRAWING_NS}}}{name}"
    for name in ("noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill")
)


SLIDE_TRANSITIONS = frozenset({"none", "fade", "push", "wipe", "split", "cut"})


def slide_transition(slide_root: etree._Element) -> str | None:
    """Basic transition name; None for alternate-content or unsupported effects."""
    if any(etree.QName(child).localname == "AlternateContent" for child in slide_root):
        return None
    transitions = slide_root.findall(f"{{{PRESENTATION_NS}}}transition")
    if not transitions:
        return "none"
    effects = list(transitions[0])
    if len(transitions) != 1 or len(effects) > 1:
        return None
    if not effects:
        return "none"
    effect = effects[0]
    name = str(etree.QName(effect).localname)
    if effect.tag != f"{{{PRESENTATION_NS}}}{name}" or name not in SLIDE_TRANSITIONS:
        return None
    return name


def slide_hidden(slide_root: etree._Element) -> bool:
    """Whether the slide is excluded from the slide show (p:sld show="0")."""
    return slide_root.get("show") in {"0", "false"}


def slide_background(slide_root: etree._Element) -> FidelityBackground | None:
    """Editable background states; picture, gradient and pattern fills return None."""
    common = slide_root.find(f"{{{PRESENTATION_NS}}}cSld")
    if common is None:
        return None
    backgrounds = common.findall(f"{{{PRESENTATION_NS}}}bg")
    if not backgrounds:
        return FidelityBackground(state="inherited")
    if len(backgrounds) != 1 or backgrounds[0].attrib or len(backgrounds[0]) != 1:
        return None
    child = backgrounds[0][0]
    if child.tag == f"{{{PRESENTATION_NS}}}bgRef":
        return FidelityBackground(state="theme_reference")
    if child.tag != f"{{{PRESENTATION_NS}}}bgPr" or set(child.attrib) - {"shadeToTitle"}:
        return None
    fills = [item for item in child if item.tag in _BACKGROUND_FILLS]
    others = [item for item in child if item.tag not in _BACKGROUND_FILLS]
    if len(fills) != 1 or any(
        item.tag != f"{{{DRAWING_NS}}}effectLst" or len(item) for item in others
    ):
        return None
    fill = fills[0]
    if fill.tag != f"{{{DRAWING_NS}}}solidFill" or len(fill) != 1:
        return None
    color = fill[0]
    value = color.get("val", "")
    if (
        color.tag != f"{{{DRAWING_NS}}}srgbClr"
        or len(color)
        or set(color.attrib) != {"val"}
        or not re.fullmatch(r"[0-9A-Fa-f]{6}", value)
    ):
        return None
    return FidelityBackground(state="solid", color=f"#{value.upper()}")


HYPERLINK_REL_TYPE = f"{REL_NS}/hyperlink"
_HYPERLINK_ATTRIBUTES = {
    f"{{{REL_NS}}}id",
    "action",
    "tooltip",
    "history",
    "highlightClick",
    "endSnd",
}
SLIDE_JUMP_ACTION = "ppaction://hlinksldjump"


def slide_hyperlink_targets(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    part_name: str,
    slide_part_ids: dict[str, str] | None = None,
) -> dict[str, tuple[str, str]]:
    """Link relationships of one slide: ("url", address) or ("slide", slide id)."""
    directory, name = posixpath.split(part_name)
    info = members.get(f"{directory}/_rels/{name}.rels")
    if info is None:
        return {}
    result: dict[str, tuple[str, str]] = {}
    for relationship_id, (relationship_type, target, mode) in _relationships(
        _parse_xml_part(archive, info)
    ).items():
        if relationship_type == HYPERLINK_REL_TYPE and mode == "External":
            result[relationship_id] = ("url", target)
        elif relationship_type == SLIDE_REL_TYPE and mode == "Internal" and slide_part_ids:
            try:
                part = _resolve_internal_part(directory, target)
            except CoreDomainError:
                continue
            if part in slide_part_ids:
                result[relationship_id] = ("slide", slide_part_ids[part])
    return result


def shape_hyperlink(
    candidate: etree._Element, targets: dict[str, tuple[str, str]]
) -> FidelityHyperlink | None:
    """The uniform external click link of a text shape; None when mixed or unsupported."""
    runs = candidate.xpath("./p:txBody/a:p/a:r | ./p:txBody/a:p/a:fld", namespaces=_NS)
    if not runs:
        return None
    urls: set[tuple[str, str] | None] = set()
    for run in runs:
        properties = run.find(f"{{{DRAWING_NS}}}rPr")
        links = [] if properties is None else properties.findall(f"{{{DRAWING_NS}}}hlinkClick")
        if (
            properties is not None
            and properties.find(f"{{{DRAWING_NS}}}hlinkMouseOver") is not None
        ):
            return None
        if not links:
            urls.add(None)
            continue
        link = links[0]
        relationship_id = link.get(f"{{{REL_NS}}}id")
        if (
            len(links) != 1
            or len(link)
            or not set(link.attrib) <= _HYPERLINK_ATTRIBUTES
            or relationship_id not in targets
        ):
            return None
        kind = targets[relationship_id][0]
        if link.get("action") != (SLIDE_JUMP_ACTION if kind == "slide" else None):
            return None
        urls.add(targets[relationship_id])
    if len(urls) != 1:
        return None
    value = urls.pop()
    if value is None:
        return FidelityHyperlink()
    return (
        FidelityHyperlink(slide_id=value[1])
        if value[0] == "slide"
        else FidelityHyperlink(url=value[1])
    )


_FLIP_VALUES = {"0": False, "false": False, "1": True, "true": True}


def object_rotation(
    candidate: etree._Element, kind: str, shape_tree: etree._Element | None
) -> FidelityRotation | None:
    """Rotation/flip of a direct-child shape or picture with a simple transform."""
    if kind not in {"sp", "pic"} or (
        shape_tree is not None and candidate.getparent() is not shape_tree
    ):
        return None
    transforms = candidate.xpath("./p:spPr/a:xfrm", namespaces=_NS)
    if len(transforms) != 1:
        return None
    transform = transforms[0]
    if [child.tag for child in transform] != [
        f"{{{DRAWING_NS}}}off",
        f"{{{DRAWING_NS}}}ext",
    ] or not set(transform.attrib) <= {"rot", "flipH", "flipV"}:
        return None
    raw = transform.get("rot", "0")
    flip_horizontal = transform.get("flipH", "0")
    flip_vertical = transform.get("flipV", "0")
    if (
        not re.fullmatch(r"-?[0-9]{1,10}", raw)
        or flip_horizontal not in _FLIP_VALUES
        or flip_vertical not in _FLIP_VALUES
    ):
        return None
    return FidelityRotation(
        rotation=int(raw) % 21_600_000,
        flip_horizontal=_FLIP_VALUES[flip_horizontal],
        flip_vertical=_FLIP_VALUES[flip_vertical],
    )


_MASTER_PLACEHOLDER_KINDS = {
    "ctrTitle": "title",
    "subTitle": "body",
    "obj": "body",
    "body": "body",
    "chart": "body",
    "tbl": "body",
    "clipArt": "body",
    "dgm": "body",
    "media": "body",
    "pic": "body",
}


def _placeholder_identity(node: etree._Element) -> tuple[str, str] | None:
    placeholder = node.xpath("./*/p:nvPr/p:ph", namespaces=_NS)
    if len(placeholder) != 1:
        return None
    return placeholder[0].get("idx", "0"), placeholder[0].get("type", "obj")


def _explicit_geometry(node: etree._Element) -> FidelityGeometry | None:
    transform = node.xpath("./p:spPr/a:xfrm", namespaces=_NS)
    if len(transform) != 1 or transform[0].get("rot") not in {None, "0"}:
        return None
    offset, extent = transform[0].find("a:off", _NS), transform[0].find("a:ext", _NS)
    if offset is None or extent is None:
        return None
    try:
        return FidelityGeometry(
            int(offset.get("x", "")),
            int(offset.get("y", "")),
            int(extent.get("cx", "")),
            int(extent.get("cy", "")),
        )
    except ValueError:
        return None


def placeholder_geometry_map(
    archive: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    slide_part: str,
    cache: dict[str, dict[str, dict[str, FidelityGeometry]]] | None = None,
) -> dict[str, dict[str, FidelityGeometry]]:
    """Explicit layout placeholder geometry by idx and type, then master geometry by type."""
    result: dict[str, dict[str, FidelityGeometry]] = {"idx": {}, "type": {}, "master": {}}

    def related(part: str, kind: str) -> str | None:
        directory, name = posixpath.split(part)
        rels = members.get(f"{directory}/_rels/{name}.rels")
        if rels is None:
            return None
        matches = [
            target
            for relation_type, target, mode in _relationships(
                _parse_xml_part(archive, rels)
            ).values()
            if relation_type == f"{REL_NS}/{kind}" and mode.casefold() == "internal"
        ]
        if len(matches) != 1:
            return None
        resolved = _resolve_internal_part(directory, matches[0])
        return resolved if resolved in members else None

    layout = related(slide_part, "slideLayout")
    if layout is None:
        return result
    if cache is not None and layout in cache:
        return cache[layout]
    if cache is not None:
        cache[layout] = result
    master = related(layout, "slideMaster")
    for part, bucket in ((layout, "layout"), (master, "master")):
        if part is None:
            continue
        tree = _parse_xml_part(archive, members[part]).find(
            f"{{{PRESENTATION_NS}}}cSld/{{{PRESENTATION_NS}}}spTree"
        )
        if tree is None:
            continue
        for node in tree:
            identity = _placeholder_identity(node)
            geometry = _explicit_geometry(node)
            if identity is None or geometry is None:
                continue
            idx, kind = identity
            if bucket == "layout":
                result["idx"].setdefault(idx, geometry)
                result["type"].setdefault(kind, geometry)
            else:
                result["master"].setdefault(_MASTER_PLACEHOLDER_KINDS.get(kind, kind), geometry)
    return result


def _inherited_placeholder_geometry(
    candidate: etree._Element, inherited: dict[str, dict[str, FidelityGeometry]]
) -> FidelityGeometry | None:
    """The layout (or master) position a slide placeholder without its own transform uses."""
    identity = _placeholder_identity(candidate)
    if identity is None or not inherited:
        return None
    idx, kind = identity
    return (
        inherited.get("idx", {}).get(idx)
        or inherited.get("type", {}).get(kind)
        or inherited.get("master", {}).get(_MASTER_PLACEHOLDER_KINDS.get(kind, kind))
    )


def _geometry_for_object(
    candidate: etree._Element,
    *,
    kind: str,
    shape_tree: etree._Element,
    slide_width_emu: int,
    slide_height_emu: int,
) -> tuple[FidelityGeometry | None, bool]:
    if kind not in {"sp", "pic", "graphicFrame"}:
        return None, False
    transforms = candidate.xpath(
        "./p:xfrm" if kind == "graphicFrame" else "./p:spPr/a:xfrm", namespaces=_NS
    )
    if len(transforms) != 1:
        return None, False
    transform = transforms[0]
    offsets = transform.xpath("./a:off", namespaces=_NS)
    extents = transform.xpath("./a:ext", namespaces=_NS)
    if len(offsets) != 1 or len(extents) != 1:
        return None, False
    try:
        geometry = FidelityGeometry(
            x_emu=int(offsets[0].get("x", "")),
            y_emu=int(offsets[0].get("y", "")),
            width_emu=int(extents[0].get("cx", "")),
            height_emu=int(extents[0].get("cy", "")),
        )
    except ValueError:
        return None, False

    rotation = transform.get("rot")
    try:
        rotation_is_zero = rotation is None or int(rotation) == 0
    except ValueError:
        rotation_is_zero = False
    no_flip = all(transform.get(name) in {None, "0", "false"} for name in ("flipH", "flipV"))
    # Shapes and pictures keep their rotation/flip through moves and resizes.
    supported_orientation = (rotation_is_zero and no_flip) or (
        object_rotation(candidate, kind, shape_tree) is not None
    )
    direct_child = candidate.getparent() is shape_tree
    simple_transform = [child.tag for child in transform] == [
        f"{{{DRAWING_NS}}}off",
        f"{{{DRAWING_NS}}}ext",
    ]
    # Objects may extend past the slide edge (bleeds, parked objects): they can still be
    # moved back, resized or deleted; every edit's replacement must lie on the slide.
    in_slide_bounds = (
        geometry.width_emu > 0
        and geometry.height_emu > 0
        and abs(geometry.x_emu) <= 4 * slide_width_emu
        and abs(geometry.y_emu) <= 4 * slide_height_emu
        and geometry.width_emu <= 8 * slide_width_emu
        and geometry.height_emu <= 8 * slide_height_emu
    )
    return (
        geometry,
        direct_child
        and simple_transform
        and supported_orientation
        and in_slide_bounds
        and (kind != "graphicFrame" or _graphic_frame_geometry_supported(candidate, geometry)),
    )


def _graphic_frame_geometry_supported(
    candidate: etree._Element, geometry: FidelityGeometry
) -> bool:
    data = candidate.findall("a:graphic/a:graphicData", _NS)
    if len(data) != 1 or len(data[0]) != 1:
        return False
    chart_ns = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    if data[0].get("uri") == chart_ns:
        if has_unsafe_extensions(candidate):
            return False
        chart = data[0][0]
        return (
            chart.tag == f"{{{chart_ns}}}chart"
            and set(chart.attrib) == {f"{{{REL_NS}}}id"}
            and bool(chart.get(f"{{{REL_NS}}}id"))
            and not len(chart)
        )
    if (
        data[0].get("uri") != "http://schemas.openxmlformats.org/drawingml/2006/table"
        or data[0][0].tag != f"{{{DRAWING_NS}}}tbl"
    ):
        return False
    from presenter_core.presentation.table_structure import table_extensions_supported

    # Tables may sit in a content placeholder and carry row/column identities; their
    # frame keeps an explicit transform either way.
    if candidate.xpath(".//p:ph[not(parent::p:nvPr)]", namespaces=_NS) or not (
        table_extensions_supported(candidate)
    ):
        return False
    table = data[0][0]
    columns = table.findall("a:tblGrid/a:gridCol", _NS)
    rows = table.findall("a:tr", _NS)
    if not 1 <= len(columns) <= 128 or not 1 <= len(rows) <= 256:
        return False
    try:
        widths = [int(column.get("w", "")) for column in columns]
        heights = [int(row.get("h", "")) for row in rows]
    except ValueError:
        return False
    return (
        all(value > 0 for value in widths + heights)
        and sum(widths) == geometry.width_emu
        # Row heights are minimums: rows grow to fit their text, so the frame can be taller.
        and sum(heights) <= geometry.height_emu
    )


def _delete_geometry_candidate(
    root: etree._Element,
    candidate: etree._Element,
    *,
    kind: str,
    ooxml_id: str,
    geometry_editable: bool,
) -> bool:
    """Exclude placeholders and objects referenced by connectors or animations."""
    if not geometry_editable or kind not in {"sp", "pic", "graphicFrame"}:
        return False
    if candidate.xpath(
        "./p:nvSpPr/p:nvPr/p:ph | ./p:nvPicPr/p:nvPr/p:ph | ./p:nvGraphicFramePr/p:nvPr/p:ph",
        namespaces=_NS,
    ):
        return False
    connector_targets = root.xpath(
        "./p:cSld/p:spTree//p:cxnSp/p:nvCxnSpPr/p:cNvCxnSpPr/"
        "a:stCxn/@id | ./p:cSld/p:spTree//p:cxnSp/p:nvCxnSpPr/p:cNvCxnSpPr/"
        "a:endCxn/@id",
        namespaces=_NS,
    )
    animation_targets = root.xpath("./p:timing//@spid", namespaces=_NS)
    return ooxml_id not in connector_targets and ooxml_id not in animation_targets


def _is_single_run_text_shape(candidate: etree._Element, kind: str) -> bool:
    """Return true only for the deliberately narrow first text-write target."""
    paragraphs = _formatable_text_paragraphs(candidate, kind)
    runs = _formatable_text_runs(candidate, kind)
    return (
        paragraphs is not None
        and len(paragraphs) == 1
        and runs is not None
        and len(runs) == 1
        and not _has_line_break(paragraphs)
    )


def _has_line_break(paragraphs: list[etree._Element]) -> bool:
    """Text replacement rewrites runs, so shapes with breaks or fields stay format-only."""
    return any(
        paragraph.find(f"{{{DRAWING_NS}}}br") is not None
        or paragraph.find(f"{{{DRAWING_NS}}}fld") is not None
        for paragraph in paragraphs
    )


def _is_plain_field(field: etree._Element) -> bool:
    """A field with cached text whose run properties can be styled safely."""
    tags = [child.tag.removeprefix(f"{{{DRAWING_NS}}}") for child in field]
    return (
        set(field.attrib) <= {"id", "type"}
        and tags in (["t"], ["rPr", "t"], ["pPr", "t"], ["rPr", "pPr", "t"])
        and not any(len(child) for child in field if child.tag == f"{{{DRAWING_NS}}}t")
    )


def _is_uniform_run_text_shape(candidate: etree._Element, kind: str) -> bool:
    """Return true only when every direct run has identical complete run properties."""
    paragraphs = _formatable_text_paragraphs(candidate, kind)
    runs = _formatable_text_runs(candidate, kind)
    if (
        paragraphs is None
        or len(paragraphs) != 1
        or runs is None
        or len(runs) < 2
        or _has_line_break(paragraphs)
    ):
        return False
    if any(
        run.attrib or run.xpath(".//a:hlinkClick | .//a:hlinkMouseOver", namespaces=_NS)
        for run in runs
    ):
        return False
    signatures = {_xml_signature(run.find(f"{{{DRAWING_NS}}}rPr")) for run in runs}
    return len(signatures) == 1


def _is_formatable_text_shape(candidate: etree._Element, kind: str) -> bool:
    """Return true for plain text whose direct runs and paragraphs can be styled safely."""
    return _formatable_text_runs(candidate, kind) is not None


def _formatable_text_runs(candidate: etree._Element, kind: str) -> list[etree._Element] | None:
    """Return direct text runs only for simple, independently formatted paragraphs."""
    paragraphs = _formatable_text_paragraphs(candidate, kind)
    if paragraphs is None:
        return None
    # Fields (slide numbers, dates) are styled like runs but never replaced.
    return [
        run
        for paragraph in paragraphs
        for run in paragraph.xpath("./a:r | ./a:fld", namespaces=_NS)
    ]


def _formatable_text_paragraphs(
    candidate: etree._Element,
    kind: str,
) -> list[etree._Element] | None:
    """Return paragraphs whose direct runs can be styled without rewriting structure."""
    if kind != "sp":
        return None
    text_bodies = candidate.xpath("./p:txBody", namespaces=_NS)
    if len(text_bodies) != 1:
        return None
    paragraphs = text_bodies[0].xpath("./a:p", namespaces=_NS)
    if not paragraphs or len(paragraphs) > MAX_TEXT_FORMAT_PARAGRAPHS:
        return None
    allowed_paragraph_children = {
        f"{{{DRAWING_NS}}}pPr",
        f"{{{DRAWING_NS}}}r",
        f"{{{DRAWING_NS}}}br",
        f"{{{DRAWING_NS}}}fld",
        f"{{{DRAWING_NS}}}endParaRPr",
    }
    paragraph_property = f"{{{DRAWING_NS}}}pPr"
    end_paragraph_property = f"{{{DRAWING_NS}}}endParaRPr"
    total_runs = 0
    for paragraph in paragraphs:
        runs = paragraph.xpath("./a:r", namespaces=_NS)
        fields = paragraph.xpath("./a:fld", namespaces=_NS)
        total_runs += len(runs) + len(fields)
        if (
            any(not _is_plain_field(field) for field in fields)
            or any(child.tag not in allowed_paragraph_children for child in paragraph)
            # Line breaks may carry only their own run properties.
            or any(
                br.attrib or [child.tag for child in br] not in ([], [f"{{{DRAWING_NS}}}rPr"])
                for br in paragraph.xpath("./a:br", namespaces=_NS)
            )
            or sum(child.tag == paragraph_property for child in paragraph) > 1
            or sum(child.tag == end_paragraph_property for child in paragraph) > 1
            or any(child.tag == paragraph_property for child in paragraph[1:])
            or any(child.tag == end_paragraph_property for child in paragraph[:-1])
        ):
            return None
        for run in runs:
            child_tags = [child.tag for child in run]
            allowed_run_children = [
                [f"{{{DRAWING_NS}}}t"],
                [f"{{{DRAWING_NS}}}rPr", f"{{{DRAWING_NS}}}t"],
            ]
            if child_tags not in allowed_run_children:
                return None
            text_nodes = run.xpath("./a:t", namespaces=_NS)
            if len(text_nodes) != 1:
                return None
    # Blank lines (run-less paragraphs) are allowed alongside styled text.
    if not total_runs:
        return None
    return cast(list[etree._Element], paragraphs)


def _styled_paragraphs(paragraphs: list[etree._Element]) -> list[etree._Element]:
    """Paragraphs that carry text or their own properties.

    A blank line without direct properties neither reports nor receives paragraph
    styles, so a trailing empty paragraph cannot make a list look mixed.
    """
    return [
        paragraph
        for paragraph in paragraphs
        if paragraph.find(f"{{{DRAWING_NS}}}r") is not None
        or paragraph.find(f"{{{DRAWING_NS}}}pPr") is not None
    ]


TEXT_ANCHORS = {"t": "top", "ctr": "middle", "b": "bottom"}


def _body_anchor(candidate: etree._Element) -> str | None:
    """Direct vertical text alignment of the shape's text body (None when inherited)."""
    body = candidate.find(f"{{{PRESENTATION_NS}}}txBody/{{{DRAWING_NS}}}bodyPr")
    return TEXT_ANCHORS.get(body.get("anchor", "")) if body is not None else None


def _body_columns(candidate: etree._Element) -> int | None:
    body = candidate.find(f"{{{PRESENTATION_NS}}}txBody/{{{DRAWING_NS}}}bodyPr")
    raw = body.get("numCol") if body is not None else None
    return int(raw) if raw is not None and raw.isdigit() and 1 <= int(raw) <= 16 else None


def _text_style_for_shape(candidate: etree._Element, kind: str) -> FidelityTextStyle:
    """Describe direct formatting shared by safe text runs and paragraphs."""
    paragraphs = _formatable_text_paragraphs(candidate, kind)
    runs = _formatable_text_runs(candidate, kind)
    if paragraphs is None or runs is None:
        return FidelityTextStyle(editable=False)
    styles = [_text_style_for_run(run) for run in runs]
    if any(not style.editable for style in styles):
        return FidelityTextStyle(editable=False)

    fingerprints = [style.fingerprint for style in styles]
    if any(fingerprint is None for fingerprint in fingerprints):
        return FidelityTextStyle(editable=False)
    paragraph_properties = [paragraph.find(f"{{{DRAWING_NS}}}pPr") for paragraph in paragraphs]
    paragraph_bytes = [
        etree.tostring(properties, method="c14n") if properties is not None else b""
        for properties in paragraph_properties
    ]
    fingerprint_parts = paragraph_bytes + [
        fingerprint.encode("ascii") for fingerprint in fingerprints if fingerprint is not None
    ]
    combined = b"".join(len(part).to_bytes(8, "big") + part for part in fingerprint_parts)
    fingerprint = hashlib.sha256(combined).hexdigest()
    # The fingerprint covers every paragraph; reported values skip plain blank lines.
    paragraph_properties = [
        paragraph.find(f"{{{DRAWING_NS}}}pPr") for paragraph in _styled_paragraphs(paragraphs)
    ]

    alignment_codes = {"l": "left", "ctr": "center", "r": "right", "just": "justify"}
    alignment_values = [
        alignment_codes.get(properties.get("algn")) if properties is not None else None
        for properties in paragraph_properties
    ]
    alignment = _uniform_style_value(alignment_values)
    bullet_state_values = [
        _paragraph_bullet_mode_for_shape(properties) for properties in paragraph_properties
    ]
    bullet_state = _uniform_style_value([state for state, _editable in bullet_state_values])
    bullet_editable = all(editable for _state, editable in bullet_state_values)
    decorations = [
        _paragraph_bullet_decoration_for_shape(properties) for properties in paragraph_properties
    ]
    decoration_editable = bullet_editable and all(item[2] for item in decorations)

    left_indent_values: list[int | None] = []
    left_indent_editable = True
    for properties in paragraph_properties:
        raw_left_indent = properties.get("marL") if properties is not None else None
        left_indent: int | None = None
        if raw_left_indent is not None:
            if not re.fullmatch(r"[0-9]{1,7}", raw_left_indent):
                left_indent_editable = False
            else:
                left_indent_emu = int(raw_left_indent)
                if (
                    left_indent_emu > MAX_TEXT_LEFT_INDENT_EMU
                    or left_indent_emu % EMU_PER_POINT != 0
                ):
                    left_indent_editable = False
                else:
                    left_indent = left_indent_emu // EMU_PER_POINT
        left_indent_values.append(left_indent)
    left_indent_pt = _uniform_style_value(left_indent_values)

    first_line_indent_values: list[int | None] = []
    first_line_indent_editable = True
    for properties in paragraph_properties:
        raw_first_line_indent = properties.get("indent") if properties is not None else None
        first_line_indent: int | None = None
        if raw_first_line_indent is not None:
            if not re.fullmatch(r"-?[0-9]{1,8}", raw_first_line_indent):
                first_line_indent_editable = False
            else:
                first_line_indent_emu = int(raw_first_line_indent)
                if (
                    abs(first_line_indent_emu) > MAX_TEXT_FIRST_LINE_INDENT_EMU
                    or first_line_indent_emu % EMU_PER_POINT != 0
                ):
                    first_line_indent_editable = False
                else:
                    first_line_indent = first_line_indent_emu // EMU_PER_POINT
        first_line_indent_values.append(first_line_indent)
    first_line_indent_pt = _uniform_style_value(first_line_indent_values)

    line_spacing_values = [
        _paragraph_spacing_for_shape(properties, "lnSpc") for properties in paragraph_properties
    ]
    line_spacing_pt = _uniform_style_value([value for value, _editable in line_spacing_values])
    line_spacing_editable = all(editable for _value, editable in line_spacing_values)
    space_before_values = [
        _paragraph_spacing_for_shape(properties, "spcBef") for properties in paragraph_properties
    ]
    space_before_pt = _uniform_style_value([value for value, _editable in space_before_values])
    space_before_editable = all(editable for _value, editable in space_before_values)
    space_after_values = [
        _paragraph_spacing_for_shape(properties, "spcAft") for properties in paragraph_properties
    ]
    space_after_pt = _uniform_style_value([value for value, _editable in space_after_values])
    space_after_editable = all(editable for _value, editable in space_after_values)

    def uniform(name: str) -> Any:
        return _uniform_style_value([getattr(style, name) for style in styles])

    return FidelityTextStyle(
        editable=True,
        fingerprint=fingerprint,
        bold=uniform("bold"),
        italic=uniform("italic"),
        underline=uniform("underline"),
        strikethrough=uniform("strikethrough"),
        font_family=uniform("font_family"),
        highlight_color=uniform("highlight_color"),
        vertical_anchor=_body_anchor(candidate),
        columns=_body_columns(candidate),
        font_size_pt=uniform("font_size_pt"),
        font_color=uniform("font_color"),
        color_editable=all(style.color_editable for style in styles),
        alignment=alignment,
        alignment_editable=True,
        bullet_state=bullet_state,
        bullet_editable=bullet_editable,
        left_indent_pt=left_indent_pt,
        left_indent_editable=left_indent_editable,
        first_line_indent_pt=first_line_indent_pt,
        first_line_indent_editable=first_line_indent_editable,
        line_spacing_pt=line_spacing_pt,
        line_spacing_editable=line_spacing_editable,
        space_before_pt=space_before_pt,
        space_before_editable=space_before_editable,
        space_after_pt=space_after_pt,
        space_after_editable=space_after_editable,
        bullet_color=_uniform_style_value([item[0] for item in decorations]),
        bullet_color_editable=decoration_editable,
        bullet_size_percent=_uniform_style_value([item[1] for item in decorations]),
        bullet_size_editable=decoration_editable,
        numbering_start=_uniform_style_value(
            [
                _paragraph_numbering_start_for_shape(properties)
                for properties in paragraph_properties
            ]
        ),
        numbering_start_editable=bullet_editable,
    )


def _uniform_style_value(values: list[Any]) -> Any:
    """Return one repeated direct style value, or None for mixed values."""
    if not values:
        return None
    return values[0] if all(value == values[0] for value in values[1:]) else None


def _paragraph_spacing_for_shape(
    paragraph_properties: etree._Element | None, property_name: str
) -> tuple[int | None, bool]:
    """Read bounded point-based line or paragraph spacing without guessing unsupported forms."""
    if property_name not in {"lnSpc", "spcBef", "spcAft"}:
        return None, False
    spacing_tag = f"{{{DRAWING_NS}}}{property_name}"
    elements = paragraph_properties.findall(spacing_tag) if paragraph_properties is not None else []
    if not elements:
        return None, _paragraph_property_insert_index(
            paragraph_properties, property_name
        ) is not None
    if len(elements) != 1:
        return None, False

    spacing = elements[0]
    points_nodes = list(spacing)
    if spacing.attrib or len(points_nodes) != 1:
        return None, False
    points_node = points_nodes[0]
    if (
        points_node.tag != f"{{{DRAWING_NS}}}spcPts"
        or set(points_node.attrib) != {"val"}
        or len(points_node)
        or (spacing.text and spacing.text.strip())
        or (points_node.text and points_node.text.strip())
    ):
        return None, False

    raw_value = points_node.get("val", "")
    if not re.fullmatch(r"[0-9]{1,8}", raw_value):
        return None, False
    hundredths = int(raw_value)
    max_hundredths = (
        MAX_TEXT_LINE_SPACING_HUNDREDTHS
        if property_name == "lnSpc"
        else MAX_TEXT_PARAGRAPH_SPACING_HUNDREDTHS
    )
    if (
        hundredths > max_hundredths
        or hundredths % 100 != 0
        or (property_name == "lnSpc" and hundredths < 100)
    ):
        return None, False
    return hundredths // 100, True


def _paragraph_property_insert_index(
    paragraph_properties: etree._Element | None, property_name: str
) -> int | None:
    """Return a schema-ordered insertion point only for a fully recognized pPr sequence."""
    target_order = _PARAGRAPH_PROPERTY_ORDER.get(property_name)
    if target_order is None:
        return None
    if paragraph_properties is None:
        return 0

    previous_order = -1
    insertion_index = len(paragraph_properties)
    children = list(paragraph_properties)
    for index, child in enumerate(children):
        if not isinstance(child.tag, str) or not child.tag.startswith(f"{{{DRAWING_NS}}}"):
            return None
        order = _PARAGRAPH_PROPERTY_ORDER.get(child.tag.removeprefix(f"{{{DRAWING_NS}}}"))
        if order is None or order <= previous_order:
            return None
        if order > target_order and insertion_index == len(children):
            insertion_index = index
        previous_order = order
    return insertion_index


def _bullet_nodes(paragraph_properties: etree._Element | None) -> list[etree._Element]:
    return (
        [
            child
            for child in paragraph_properties
            if isinstance(child.tag, str)
            and child.tag.startswith(f"{{{DRAWING_NS}}}")
            and child.tag.removeprefix(f"{{{DRAWING_NS}}}") in _PARAGRAPH_BULLET_PROPERTY_NAMES
        ]
        if paragraph_properties is not None
        else []
    )


def _bullet_decoration(
    node: etree._Element,
) -> tuple[str, str | int | None] | None:
    """Classify one supported color/size/font decoration, or None when unsupported.

    A None value means the decoration is retained but has no exact direct value to
    report (follow-text, theme or transformed colors, point sizes); replacing it
    only happens when the user explicitly sets that property.
    """
    name = node.tag.removeprefix(f"{{{DRAWING_NS}}}")
    if node.text and node.text.strip():
        return None
    if name in {"buClrTx", "buSzTx", "buFontTx"}:
        if node.attrib or len(node):
            return None
        return {"buClrTx": "color", "buSzTx": "size", "buFontTx": "font"}[name], None
    if name == "buClr":
        if node.attrib or len(node) != 1:
            return None
        color = node[0]
        value = color.get("val", "")
        if color.tag not in {f"{{{DRAWING_NS}}}srgbClr", f"{{{DRAWING_NS}}}schemeClr"}:
            return None
        if (
            color.tag == f"{{{DRAWING_NS}}}srgbClr"
            and set(color.attrib) == {"val"}
            and not len(color)
            and re.fullmatch(r"[0-9A-Fa-f]{6}", value)
        ):
            return "color", f"#{value.upper()}"
        return "color", None
    if name == "buSzPts":
        raw = node.get("val", "")
        if set(node.attrib) != {"val"} or len(node) or not re.fullmatch(r"[0-9]{3,6}", raw):
            return None
        return "size", None
    if name == "buSzPct":
        raw = node.get("val", "")
        if set(node.attrib) != {"val"} or len(node) or not re.fullmatch(r"[0-9]{4,6}", raw):
            return None
        value = int(raw)
        if (
            value % 1000
            or not MIN_BULLET_SIZE_PERCENT * 1000 <= value <= MAX_BULLET_SIZE_PERCENT * 1000
        ):
            return None
        return "size", value // 1000
    if name == "buFont":
        typeface = node.get("typeface")
        if (
            len(node)
            or not set(node.attrib) <= {"typeface", "panose", "pitchFamily", "charset"}
            or not isinstance(typeface, str)
            or not 0 < len(typeface) <= 64
        ):
            return None
        # Symbol fonts are retained for the imported glyph and dropped when the
        # marker type changes; see PresentationEditService._apply_paragraph_bullet.
        return "font", typeface
    return None


def plain_bullet_font(typeface: str | None) -> bool:
    return typeface in _PLAIN_BULLET_FONTS


def _paragraph_bullet_decoration_for_shape(
    paragraph_properties: etree._Element | None,
) -> tuple[str | None, int | None, bool]:
    """Return direct bullet color, size percent and whether both can be edited."""
    color: str | None = None
    size: int | None = None
    for node in _bullet_nodes(paragraph_properties):
        if node.tag.removeprefix(f"{{{DRAWING_NS}}}") in _PARAGRAPH_BULLET_TYPE_NAMES:
            continue
        decoration = _bullet_decoration(node)
        if decoration is None:
            return None, None, False
        kind, value = decoration
        if kind == "color":
            color = value if isinstance(value, str) else None
        elif kind == "size":
            size = value if isinstance(value, int) else None
    return color, size, True


def _numbering_start_value(node: etree._Element) -> int | None:
    raw = node.get("startAt", "1")
    if not re.fullmatch(r"[1-9][0-9]{0,3}", raw):
        return None
    return int(raw)


def _paragraph_numbering_start_for_shape(
    paragraph_properties: etree._Element | None,
) -> int | None:
    """Return the first number of a plain numbered paragraph, otherwise None."""
    mode, editable = _paragraph_bullet_mode_for_shape(paragraph_properties)
    if not editable or mode not in PARAGRAPH_AUTONUM_TYPE_BY_MODE:
        return None
    assert paragraph_properties is not None
    node = paragraph_properties.find(f"{{{DRAWING_NS}}}buAutoNum")
    return _numbering_start_value(node) if node is not None else None


def _paragraph_bullet_mode_for_shape(
    paragraph_properties: etree._Element | None,
) -> tuple[str | None, bool]:
    """Expose only plain bullet/list markers or safely insertable states."""
    nodes = _bullet_nodes(paragraph_properties)
    if any(
        node.tag.removeprefix(f"{{{DRAWING_NS}}}") not in _PARAGRAPH_BULLET_TYPE_NAMES
        and _bullet_decoration(node) is None
        for node in nodes
    ):
        return None, False
    bullet_nodes = [
        node
        for node in nodes
        if node.tag.removeprefix(f"{{{DRAWING_NS}}}") in _PARAGRAPH_BULLET_TYPE_NAMES
    ]
    if not bullet_nodes:
        return None, _paragraph_property_insert_index(paragraph_properties, "buChar") is not None
    if len(bullet_nodes) != 1:
        return None, False

    bullet_node = bullet_nodes[0]
    if (
        bullet_node.tag == f"{{{DRAWING_NS}}}buChar"
        and set(bullet_node.attrib) == {"char"}
        and not len(bullet_node)
        and not (bullet_node.text and bullet_node.text.strip())
    ):
        char = bullet_node.get("char", "")
        mode = _PARAGRAPH_BULLET_MODE_BY_CHAR.get(char)
        # A single custom glyph (for example a Wingdings square) is kept as an
        # imported marker that can be replaced, but is not reported as a mode.
        return (mode, True) if mode is not None else (None, len(char) == 1)
    if (
        bullet_node.tag == f"{{{DRAWING_NS}}}buNone"
        and not bullet_node.attrib
        and not len(bullet_node)
        and not (bullet_node.text and bullet_node.text.strip())
    ):
        return "none", True
    if (
        bullet_node.tag == f"{{{DRAWING_NS}}}buAutoNum"
        and "type" in bullet_node.attrib
        and set(bullet_node.attrib) <= {"type", "startAt"}
        and _numbering_start_value(bullet_node) is not None
        and bullet_node.get("type") in _PARAGRAPH_MODE_BY_AUTONUM_TYPE
        and not len(bullet_node)
        and not (bullet_node.text and bullet_node.text.strip())
    ):
        return _PARAGRAPH_MODE_BY_AUTONUM_TYPE[bullet_node.get("type", "")], True
    if bullet_node.tag == f"{{{DRAWING_NS}}}buBlip" and _is_plain_picture_bullet(bullet_node):
        # An embedded picture marker is kept as an imported marker that can be
        # replaced; replacing it removes only the buBlip, never the image part.
        return None, True
    return None, False


def _is_plain_picture_bullet(node: etree._Element) -> bool:
    blips = list(node)
    if node.attrib or len(blips) != 1 or blips[0].tag != f"{{{DRAWING_NS}}}blip":
        return False
    blip = blips[0]
    embed = blip.get(f"{{{REL_NS}}}embed")
    return (
        isinstance(embed, str)
        and bool(embed)
        and set(blip.attrib) == {f"{{{REL_NS}}}embed"}
        and not len(blip)
    )


# ST_TextUnderlineType; "none" is the only non-underlined value.
TEXT_UNDERLINE_TYPES = frozenset(
    {
        "none",
        "words",
        "sng",
        "dbl",
        "heavy",
        "dotted",
        "dottedHeavy",
        "dash",
        "dashHeavy",
        "dashLong",
        "dashLongHeavy",
        "dotDash",
        "dotDashHeavy",
        "dotDotDash",
        "dotDotDashHeavy",
        "wavy",
        "wavyHeavy",
        "wavyDbl",
    }
)


def _text_style_for_run(run: etree._Element) -> FidelityTextStyle:
    """Describe one direct run without resolving theme or inherited formatting."""
    properties = run.find(f"{{{DRAWING_NS}}}rPr")
    if properties is None:
        properties_bytes = b""
        attributes: dict[str, str] = {}
        children: list[etree._Element] = []
    else:
        properties_bytes = etree.tostring(properties, method="c14n")
        attributes = properties.attrib
        children = list(properties)
    fingerprint = hashlib.sha256(properties_bytes).hexdigest()

    bold = _text_boolean_attribute(attributes.get("b"))
    italic = _text_boolean_attribute(attributes.get("i"))
    raw_size = attributes.get("sz")
    font_size_pt: float | None = None
    if raw_size is not None:
        try:
            parsed_size = int(raw_size)
        except ValueError:
            return FidelityTextStyle(editable=False, fingerprint=fingerprint)
        if not 1 <= parsed_size <= 400_000:
            return FidelityTextStyle(editable=False, fingerprint=fingerprint)
        font_size_pt = parsed_size / 100

    if ("b" in attributes and bold is None) or ("i" in attributes and italic is None):
        return FidelityTextStyle(editable=False, fingerprint=fingerprint)
    raw_underline = attributes.get("u")
    raw_strike = attributes.get("strike")
    if (raw_underline is not None and raw_underline not in TEXT_UNDERLINE_TYPES) or (
        raw_strike is not None and raw_strike not in {"noStrike", "sngStrike", "dblStrike"}
    ):
        return FidelityTextStyle(editable=False, fingerprint=fingerprint)
    underline = None if raw_underline is None else raw_underline != "none"
    latin = [child for child in children if child.tag == f"{{{DRAWING_NS}}}latin"]
    if len(latin) > 1:
        return FidelityTextStyle(editable=False, fingerprint=fingerprint)
    font_family = latin[0].get("typeface") or None if latin else None
    highlights = [child for child in children if child.tag == f"{{{DRAWING_NS}}}highlight"]
    highlight_color: str | None = None
    if highlights:
        colors = list(highlights[0])
        value = colors[0].get("val", "") if len(colors) == 1 else ""
        if (
            len(highlights) != 1
            or highlights[0].attrib
            or len(colors) != 1
            or colors[0].tag != f"{{{DRAWING_NS}}}srgbClr"
            or len(colors[0])
            or not re.fullmatch(r"[0-9A-Fa-f]{6}", value)
        ):
            return FidelityTextStyle(editable=False, fingerprint=fingerprint)
        highlight_color = f"#{value.upper()}"
    strikethrough = None if raw_strike is None else raw_strike != "noStrike"

    fill_tags = {
        f"{{{DRAWING_NS}}}noFill",
        f"{{{DRAWING_NS}}}solidFill",
        f"{{{DRAWING_NS}}}gradFill",
        f"{{{DRAWING_NS}}}blipFill",
        f"{{{DRAWING_NS}}}pattFill",
        f"{{{DRAWING_NS}}}grpFill",
    }
    fills = [child for child in children if child.tag in fill_tags]
    color_editable = len(fills) <= 1
    font_color: str | None = None
    if len(fills) == 1 and fills[0].tag == f"{{{DRAWING_NS}}}solidFill":
        colors = list(fills[0])
        if len(colors) == 1 and colors[0].tag == f"{{{DRAWING_NS}}}srgbClr":
            value = colors[0].get("val", "")
            if re.fullmatch(r"[0-9A-Fa-f]{6}", value):
                if not any(
                    etree.QName(child).localname
                    in {"alpha", "alphaMod", "alphaOff", "lumMod", "lumOff", "tint", "shade"}
                    for child in colors[0]
                ):
                    font_color = f"#{value.upper()}"

    return FidelityTextStyle(
        editable=True,
        fingerprint=fingerprint,
        bold=bold,
        italic=italic,
        underline=underline,
        strikethrough=strikethrough,
        font_family=font_family,
        highlight_color=highlight_color,
        font_size_pt=font_size_pt,
        font_color=font_color,
        color_editable=color_editable,
    )


def _text_boolean_attribute(value: str | None) -> bool | None:
    if value is None:
        return None
    if value in {"1", "true"}:
        return True
    if value in {"0", "false"}:
        return False
    return None


def _is_safe_decision_text(value: str) -> bool:
    return len(value) <= MAX_DECISION_OBJECT_TEXT_CHARS and not any(
        (ord(character) < 32 and character not in "\t\n\r") or 0xD800 <= ord(character) <= 0xDFFF
        for character in value
    )


def _stable_id(value: str) -> str:
    return str(uuid.uuid5(_IDENTITY_NAMESPACE, value))


def _invalid_package() -> CoreDomainError:
    return CoreDomainError(
        "PRESENTATION_FIDELITY_STRUCTURE_INVALID",
        "This presentation contains an unsupported or invalid package structure.",
    )
