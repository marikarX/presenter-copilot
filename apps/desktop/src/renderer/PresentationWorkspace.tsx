import { guidedTranslation, guidedResize } from "./canvas-guides";
import { RevisionCheckpoints } from "./RevisionCheckpoints";
import { VoiceRecognitionReview } from "./VoiceRecognitionReview";
import {
  clarifiedVoiceInstruction,
  parseRecognitionReview,
  type RecognitionReview,
} from "./voice-recognition-review";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type FormEvent,
} from "react";
import { createPortal } from "react-dom";
import {
  usePushToEdit,
  PUSH_TO_EDIT_LABEL,
  type VoiceGestureCapture,
} from "./push-to-edit";

import {
  isActiveTypedDecisionProviderId,
  isCoreError,
  type ProjectSummary,
  type ActiveTypedDecisionProviderId,
  type PresentationExportResult,
  type PresentationPreviewRenderResult,
  type RendererCoreMethod,
  type SourcePreviewResult,
  type SourceSummary,
  type TypedDecisionProviderStatus,
  unwrapInvokeResult,
} from "../shared/protocol";
import type { SourceHandle } from "pptx-glimpse";
import { canSaveMockTextRevision } from "../presentation-preview/layout-risk";
import { RehearsalFindings, type RehearsalFinding } from "./RehearsalFindings";
import { CreatePresentation } from "./CreatePresentation";
import {
  SlideEditReview,
  type ObjectPasteRequest,
  type ObjectActionRequest,
} from "./SlideEditReview";
import { SlideObjectCanvas } from "./SlideObjectCanvas";
import { BulkTextFormat } from "./BulkTextFormat";
import { FindReplace } from "./FindReplace";
import { AltTextEditor } from "./AltTextEditor";
import { ReplaceFonts, type DeckFont } from "./ReplaceFonts";
import { ReuseSlides, type ReuseRequest } from "./ReuseSlides";
import {
  ComponentLibrary,
  type ComponentSelection,
  type PresentationComponent,
} from "./ComponentLibrary";
import { ClickActionEditor, type ClickAction } from "./ClickActionEditor";
import {
  AccessibilityCheck,
  isAccessibilityResult,
  type AccessibilityIssue,
  type AccessibilityResult,
} from "./AccessibilityCheck";
import {
  SlideSections,
  isSlideSectionState,
  type SlideSectionDraft,
  type SlideSectionState,
} from "./SlideSections";
import {
  SlideAnimations,
  isSlideAnimationState,
  type SlideAnimationEffect,
  type SlideAnimationState,
} from "./SlideAnimations";
import { DeckSemanticReview } from "./DeckSemanticReview";
import type { ClaimScanCache } from "./claim-scan-state";
import { SlideTakeaway } from "./SlideTakeaway";
import { PresentationNarrative } from "./PresentationNarrative";
import { ClaimEvidenceReview } from "./ClaimEvidenceReview";
import { DeckPictureAssets } from "./DeckPictureAssets";
import { type ObjectMoveRequest } from "./object-layout";
import { CopilotEditPlan } from "./CopilotEditPlan";
import { NativeCharts } from "./NativeCharts";
import { ShapeFills } from "./ShapeFills";
import { NativeTables } from "./NativeTables";
import { TextFit } from "./TextFit";
import { PdfExport } from "./PdfExport";
import { NativeDiagrams } from "./NativeDiagrams";
import { NativeLayouts } from "./NativeLayouts";
import { CreateAppendix } from "./CreateAppendix";
import { InsertAuthoredSlide } from "./InsertAuthoredSlide";
import { WorkspaceIcon as Icon } from "./WorkspaceIcon";

const MAX_PREVIEW_BYTES = 50 * 1024 * 1024;
const MAX_PREVIEW_IMAGE_BYTES = 16 * 1024 * 1024;
const PREVIEW_WORKER_REQUEST_TIMEOUT_MS = 120_000;
const DEFAULT_READ_BYTES = 512 * 1024;
const MAX_MOCK_TEXT_CHARS = 2_000;
const MAX_REWRITE_INSTRUCTION_CHARS = 500;
const MAX_REVIEW_TRANSCRIPT_CHARS = 4_000;
const MAX_SPEAKER_NOTES_CHARS = 12_000;
const MAX_SPEAKER_NOTES_PARAGRAPHS = 128;
const MAX_WORKSPACE_SLIDES = 5_000;
const MAX_REPLACEMENT_IMAGE_BYTES = 4 * 1024 * 1024;
const MAX_TEXT_LEFT_INDENT_PT = 144;
const MAX_TEXT_FIRST_LINE_INDENT_PT = 144;
const MAX_TEXT_PARAGRAPH_SPACING_PT = 144;
const MAX_TEXT_LINE_SPACING_PT = 144;
const EMU_PER_INCH = 914_400;
const MAX_SLIDE_DIMENSION_EMU = 100_000_000;
const TEXT_ALIGNMENTS = ["left", "center", "right", "justify"] as const;
const TEXT_BULLET_STATES = [
  "bullet",
  "bullet_hollow",
  "bullet_square",
  "bullet_dash",
  "none",
  "numbered",
  "numbered_paren",
  "numbered_alpha_lower",
  "numbered_alpha_upper",
  "numbered_roman_lower",
  "numbered_roman_upper",
] as const;
const SLIDE_PURPOSES = [
  "opening",
  "problem",
  "recommendation",
  "evidence",
  "plan",
  "risk",
  "transition",
  "summary",
  "appendix",
  "unclear",
] as const;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

type SlidePurpose = (typeof SLIDE_PURPOSES)[number];

function isSlidePurpose(value: unknown): value is SlidePurpose {
  return (
    typeof value === "string" &&
    (SLIDE_PURPOSES as readonly string[]).includes(value)
  );
}

type FidelityObjectKindCounts = {
  shapes: number;
  pictures: number;
  graphic_frames: number;
  connectors: number;
  groups: number;
};

function hasValidObjectKindCounts(
  value: unknown,
  expectedTotal: number,
): value is FidelityObjectKindCounts {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const counts = value as Record<string, unknown>;
  const keys: Array<keyof FidelityObjectKindCounts> = [
    "shapes",
    "pictures",
    "graphic_frames",
    "connectors",
    "groups",
  ];
  if (Object.keys(counts).length !== keys.length) return false;
  const values = keys.map((key) => counts[key]);
  return (
    values.every(
      (count) =>
        typeof count === "number" && Number.isSafeInteger(count) && count >= 0,
    ) &&
    values.reduce<number>((total, count) => total + Number(count), 0) ===
      expectedTotal
  );
}

function formatObjectKindCounts(counts: FidelityObjectKindCounts): string {
  const entries: Array<[string, number]> = [
    ["shapes", counts.shapes],
    ["pictures", counts.pictures],
    ["graphic frames", counts.graphic_frames],
    ["connectors", counts.connectors],
    ["groups", counts.groups],
  ];
  return (
    entries
      .filter(([, count]) => count > 0)
      .map(([label, count]) => `${count} ${label}`)
      .join(" · ") || "No drawing objects"
  );
}

type ReaderOpenResult = {
  session_id: string;
  revision_id: string;
  revision_kind: "original" | "edited";
  revision_number: number;
  byte_size: number;
  sha256: string;
  chunk_bytes: number;
  fidelity_report: {
    status: "inventory_only";
    slide_count: number;
    object_count: number;
    object_kinds: FidelityObjectKindCounts;
    text_edit_candidates: number;
    nontext_or_unmodeled_objects: number;
    slides: Array<{
      slide_id: string;
      ordinal: number;
      object_count: number;
    }>;
  };
};

type ReaderChunkResult = {
  offset: number;
  bytes_b64: string;
  complete: boolean;
};

type PresentationRevision = {
  revision_id: string;
  parent_revision_id: string | null;
  revision_number: number;
  revision_kind: "original" | "edited";
  sha256: string;
  byte_size: number;
  created_at: string;
  is_current: boolean;
};

type RevisionHistoryResult = {
  presentation_id: string;
  current_revision_id: string;
  has_more: boolean;
  next_before_revision_number: number | null;
  revisions: PresentationRevision[];
};

type TextTarget = {
  key: string;
  slide_id: string;
  object_id: string;
  ooxml_shape_id: string;
  handle?: SourceHandle;
  label: string;
  text: string;
  replaceEditable: boolean;
  uniformRunReplacement: boolean;
  style: TextStyle;
};

type TextStyle = {
  editable: boolean;
  fingerprint: string | null;
  bold: boolean | null;
  italic: boolean | null;
  underline?: boolean | null;
  strikethrough?: boolean | null;
  font_family?: string | null;
  highlight_color?: string | null;
  vertical_anchor?: "top" | "middle" | "bottom" | null;
  columns?: number | null;
  font_size_pt: number | null;
  font_color: string | null;
  color_editable: boolean;
  alignment: (typeof TEXT_ALIGNMENTS)[number] | null;
  alignment_editable: boolean;
  bullet_state: (typeof TEXT_BULLET_STATES)[number] | null;
  bullet_editable: boolean;
  left_indent_pt: number | null;
  left_indent_editable: boolean;
  first_line_indent_pt: number | null;
  first_line_indent_editable: boolean;
  line_spacing_pt: number | null;
  line_spacing_editable: boolean;
  space_before_pt: number | null;
  space_before_editable: boolean;
  space_after_pt: number | null;
  space_after_editable: boolean;
  bullet_color: string | null;
  bullet_color_editable: boolean;
  bullet_size_percent: number | null;
  bullet_size_editable: boolean;
  numbering_start: number | null;
  numbering_start_editable: boolean;
};

type TextStyleChange = Partial<
  Pick<
    TextStyle,
    | "bold"
    | "italic"
    | "underline"
    | "strikethrough"
    | "font_family"
    | "highlight_color"
    | "vertical_anchor"
    | "columns"
    | "font_size_pt"
    | "font_color"
    | "alignment"
    | "left_indent_pt"
    | "first_line_indent_pt"
    | "line_spacing_pt"
    | "space_before_pt"
    | "space_after_pt"
    | "bullet_color"
    | "bullet_size_percent"
    | "numbering_start"
  >
> & {
  bullet_mode?: (typeof TEXT_BULLET_STATES)[number];
};

type WorkerTextTarget = {
  key: string;
  shapeNodeId: string;
  handle?: SourceHandle;
  label: string;
  text: string;
};

type RenderTextTarget = {
  shapeNodeId: string;
  label: string;
  text: string;
  key?: string;
  handle?: SourceHandle;
};

type ObjectGeometry = {
  x_emu: number;
  y_emu: number;
  width_emu: number;
  height_emu: number;
};

type PictureCrop = {
  left_percent: number;
  right_percent: number;
  top_percent: number;
  bottom_percent: number;
};

type SlideBackground = {
  state: "inherited" | "theme_reference" | "solid" | "unsupported";
  color: string | null;
  editable: boolean;
};

function isSlideBackground(value: unknown): value is SlideBackground {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<SlideBackground>;
  return (
    typeof candidate.editable === "boolean" &&
    (candidate.state === "solid"
      ? typeof candidate.color === "string" &&
        /^#[0-9A-F]{6}$/.test(candidate.color)
      : ["inherited", "theme_reference", "unsupported"].includes(
          candidate.state ?? "",
        ) && candidate.color === null)
  );
}

type ObjectRotation = {
  rotation_degrees: number;
  flip_horizontal: boolean;
  flip_vertical: boolean;
};

type ObjectRotationDraft = {
  rotation_degrees: string;
  flip_horizontal: boolean;
  flip_vertical: boolean;
};

type PictureAdjustment = {
  brightness_percent: number;
  contrast_percent: number;
  grayscale: boolean;
};

type PictureAdjustmentDraft = {
  brightness_percent: string;
  contrast_percent: string;
  grayscale: boolean;
};

type ShapeStyle = {
  editable: boolean;
  fingerprint: string | null;
  fill_color: string | null;
  fill_editable: boolean;
  line_color: string | null;
  line_editable: boolean;
  line_width_pt: number | null;
  line_dash: string | null;
  line_format_editable: boolean;
  fill_transparency_percent?: number | null;
  shadow?: boolean | null;
  shadow_editable?: boolean;
  shape_geometry?: string | null;
};

const SHAPE_GEOMETRIES: ReadonlyArray<[string, string]> = [
  ["rect", "Rectangle"],
  ["roundRect", "Rounded rectangle"],
  ["ellipse", "Oval"],
  ["triangle", "Triangle"],
  ["diamond", "Diamond"],
  ["hexagon", "Hexagon"],
  ["rightArrow", "Right arrow"],
  ["chevron", "Chevron"],
  ["homePlate", "Pentagon arrow"],
  ["wedgeRoundRectCallout", "Callout"],
];

type SlideFooterState = {
  slide_numbers: "all" | "some" | "none";
  footers: "all" | "some" | "none";
  footer_text: string | null;
  supported_slides: number;
  slide_count: number;
  fingerprint: string;
};

function isSlideFooterState(value: unknown): value is SlideFooterState {
  if (!value || typeof value !== "object") return false;
  const state = value as Partial<SlideFooterState>;
  const coverage = ["all", "some", "none"];
  return (
    coverage.includes(state.slide_numbers ?? "") &&
    coverage.includes(state.footers ?? "") &&
    (state.footer_text === null || typeof state.footer_text === "string") &&
    Number.isSafeInteger(state.supported_slides) &&
    Number.isSafeInteger(state.slide_count) &&
    typeof state.fingerprint === "string" &&
    /^[0-9a-f]{64}$/.test(state.fingerprint)
  );
}

const THEME_COLOR_SLOTS: ReadonlyArray<[string, string]> = [
  ["accent1", "Accent 1"],
  ["accent2", "Accent 2"],
  ["accent3", "Accent 3"],
  ["accent4", "Accent 4"],
  ["accent5", "Accent 5"],
  ["accent6", "Accent 6"],
  ["dk2", "Dark 2"],
  ["lt2", "Light 2"],
  ["hlink", "Hyperlink"],
  ["folHlink", "Followed hyperlink"],
];

type ThemeColorState = {
  colors: Record<string, string> | null;
  editable: boolean;
};

function isThemeColorState(value: unknown): value is ThemeColorState {
  if (!value || typeof value !== "object") return false;
  const state = value as Partial<ThemeColorState>;
  if (typeof state.editable !== "boolean") return false;
  if (state.colors === null) return !state.editable;
  return (
    !!state.colors &&
    typeof state.colors === "object" &&
    THEME_COLOR_SLOTS.every(([slot]) =>
      /^#[0-9A-F]{6}$/.test(state.colors?.[slot] ?? ""),
    )
  );
}

const SLIDE_TRANSITIONS: ReadonlyArray<[string, string]> = [
  ["none", "No transition"],
  ["fade", "Fade"],
  ["push", "Push"],
  ["wipe", "Wipe"],
  ["split", "Split"],
  ["cut", "Cut"],
];

const SHAPE_LINE_DASHES: ReadonlyArray<[string, string]> = [
  ["solid", "Solid"],
  ["dash", "Dash"],
  ["dot", "Dot"],
  ["dashDot", "Dash dot"],
  ["lgDash", "Long dash"],
  ["lgDashDot", "Long dash dot"],
  ["sysDash", "Square dash"],
  ["sysDot", "Round dot"],
];

type PresentationObject = {
  object_id: string;
  ooxml_shape_id: string;
  name: string;
  kind: "sp" | "pic" | "graphicFrame" | "cxnSp" | "grpSp";
  geometry_editable: boolean;
  delete_editable: boolean;
  group_editable: boolean;
  group_reason: string | null;
  geometry: ObjectGeometry | null;
  picture_crop: PictureCrop | null;
  picture_adjustment?: PictureAdjustment | null;
  rotation?: ObjectRotation | null;
  hyperlink?: { url: string | null; slide_id?: string | null } | null;
  shape_style: ShapeStyle | null;
  alt_text?: string | null;
  decorative?: boolean;
  group_child?: boolean;
  group_id?: string | null;
  click_action?: ClickAction | null;
};

type GeometryDraft = {
  x: string;
  y: string;
  width: string;
  height: string;
};

type PictureCropDraft = {
  left_percent: string;
  right_percent: string;
  top_percent: string;
  bottom_percent: string;
};

type ShapeStyleDraft = {
  fill_transparency_percent: string;
  fill_color: string;
  line_color: string;
  line_width_pt: string;
  line_dash: string;
};

type NewShapeType = "rect" | "ellipse";

const FONT_FAMILY_SUGGESTIONS = [
  "+mn-lt",
  "+mj-lt",
  "Aptos",
  "Arial",
  "Calibri",
  "Cambria",
  "Consolas",
  "Georgia",
  "Segoe UI",
  "Times New Roman",
  "Verdana",
];

function validFontFamily(value: string): boolean {
  return (
    value === "+mn-lt" ||
    value === "+mj-lt" ||
    // eslint-disable-next-line no-control-regex
    (/^[^\u0000-\u001f\u007f<>"&+\s][^\u0000-\u001f\u007f<>"&]{0,30}$/.test(
      value,
    ) &&
      value === value.trim())
  );
}

type TextStyleDraft = {
  highlight_color: string;
  font_family: string;
  font_size_pt: string;
  font_color: string;
  alignment: string;
  bullet_mode: string;
  bullet_color: string;
  bullet_size_percent: string;
  numbering_start: string;
  left_indent_pt: string;
  first_line_indent_pt: string;
  line_spacing_pt: string;
  space_before_pt: string;
  space_after_pt: string;
};

type TextTargetInventory = {
  semantic_targets?: Array<{
    object_id: string;
    name: string;
    source_kind: import("./claim-source").NativeClaimSourceKind;
    decision_text: string;
  }>;
  revision_id: string;
  slide_id: string;
  ordinal: number;
  slide_width_emu: number;
  slide_height_emu: number;
  has_more: boolean;
  objects_have_more: boolean;
  background?: SlideBackground;
  hidden?: boolean;
  transition?: string | null;
  speaker_notes: {
    current_text: string | null;
    text_truncated: boolean;
    editable: boolean;
  };
  targets: Array<{
    object_id: string;
    ooxml_shape_id: string;
    single_run_editable: boolean;
    uniform_run_editable: boolean;
    text_format_editable: boolean;
    current_text: string | null;
    text_style: TextStyle | null;
    decision_text: string | null;
  }>;
  objects: PresentationObject[];
};

type SpeakerNotesTarget = {
  slide_id: string;
  current_text: string | null;
  text_truncated: boolean;
  editable: boolean;
};

type SlidePurposeDecision = {
  provider_run_id: string;
  revision_id: string;
  slide_id: string;
  slide_number: number;
  purpose: SlidePurpose;
  confidence: number | null;
  probabilities: Record<string, number> | null;
  provider_id: ActiveTypedDecisionProviderId;
  model_id: string;
  latency_ms: number;
  requires_user_review: true;
};

type SavedSlidePurpose = {
  revision_id: string;
  slide_id: string;
  purpose: SlidePurpose;
  provenance: "user_confirmed";
  created_at: string;
  updated_at: string;
};

type SlidePurposeListResult = {
  revision_id: string;
  items: SavedSlidePurpose[];
};

type TextEditResult = {
  changed: boolean;
  revision_id: string;
  created_object_id?: string;
  created_slide_id?: string;
  parent_revision_id?: string;
  revision_number: number;
  sha256: string;
  byte_size: number;
  created_at?: string;
};

type TextRewriteProposal = {
  provider_run_id: string;
  document_id: string;
  revision_id: string;
  slide_id: string;
  slide_number: number;
  object_id: string;
  current_text: string;
  replacement_text: string;
  edit_summary: string;
  provider_id: string;
  model_id: string;
  latency_ms: number;
  requires_user_review: true;
};

type WorkerReply = {
  id: number;
  ok: boolean;
  type?: "opened" | "slide" | "mock-text";
  slideCount?: number;
  slideNumber?: number;
  svg?: string;
  textTargets?: WorkerTextTarget[];
  message?: string;
};

type WorkerJob = {
  worker: Worker;
  timeoutId: number;
  resolve: (reply: WorkerReply) => void;
  reject: (error: Error) => void;
};

type IntentKind = "text" | "evidence" | "notes" | "layout" | "other";
type IntentCounts = Record<IntentKind, number>;
type WorkspaceVoiceState =
  "idle" | "starting" | "listening" | "stopping" | "cancelling" | "review";

type WorkspaceVoiceStartResult = {
  capture_id: string;
  document_id: string;
  revision_id: string;
  capture_state: string;
};

type WorkspaceVoiceStopResult = {
  capture_id: string;
  document_id: string;
  revision_id: string;
  slide_number: number;
  object_id: string;
  transcript: string;
  recognition_review: unknown;
  stopped: boolean;
  cancelled: boolean;
};

const emptyIntentCounts: IntentCounts = {
  text: 0,
  evidence: 0,
  notes: 0,
  layout: 0,
  other: 0,
};

function requestCore<T>(
  method: RendererCoreMethod,
  params: Record<string, unknown>,
): Promise<T> {
  return window.presenterCopilot.core
    .request<T>(method, params)
    .then(unwrapInvokeResult);
}

function toBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function geometryDraft(geometry: ObjectGeometry): GeometryDraft {
  const asInches = (value: number) => (value / EMU_PER_INCH).toFixed(3);
  return {
    x: asInches(geometry.x_emu),
    y: asInches(geometry.y_emu),
    width: asInches(geometry.width_emu),
    height: asInches(geometry.height_emu),
  };
}

function fitPictureGeometry(
  imageWidth: number,
  imageHeight: number,
  slideWidthEmu: number,
  slideHeightEmu: number,
): ObjectGeometry {
  const scale = Math.min(
    (slideWidthEmu * 0.5) / imageWidth,
    (slideHeightEmu * 0.5) / imageHeight,
  );
  const width = Math.max(1, Math.round(imageWidth * scale));
  const height = Math.max(1, Math.round(imageHeight * scale));
  return {
    x_emu: Math.round((slideWidthEmu - width) / 2),
    y_emu: Math.round((slideHeightEmu - height) / 2),
    width_emu: width,
    height_emu: height,
  };
}

function centeredShapeGeometry(
  slideWidthEmu: number,
  slideHeightEmu: number,
): ObjectGeometry {
  const width = Math.max(1, Math.min(slideWidthEmu * 0.25, 3 * EMU_PER_INCH));
  const height = Math.max(1, Math.min(slideHeightEmu * 0.25, 2 * EMU_PER_INCH));
  return {
    x_emu: Math.round((slideWidthEmu - width) / 2),
    y_emu: Math.round((slideHeightEmu - height) / 2),
    width_emu: Math.round(width),
    height_emu: Math.round(height),
  };
}

function pictureCropDraft(crop: PictureCrop | null): PictureCropDraft {
  const format = (value: number) => value.toFixed(3).replace(/\.?0+$/, "");
  return {
    left_percent: format(crop?.left_percent ?? 0),
    right_percent: format(crop?.right_percent ?? 0),
    top_percent: format(crop?.top_percent ?? 0),
    bottom_percent: format(crop?.bottom_percent ?? 0),
  };
}

function validHyperlinkUrl(value: string): boolean {
  // eslint-disable-next-line no-control-regex
  if (!value || value.length > 2048 || /[\s\u0000-\u001f\u007f]/.test(value))
    return false;
  try {
    const url = new URL(value);
    return (
      ((url.protocol === "http:" || url.protocol === "https:") &&
        url.host !== "") ||
      (url.protocol === "mailto:" && url.pathname.includes("@"))
    );
  } catch {
    return false;
  }
}

function objectRotationDraft(
  rotation: ObjectRotation | null | undefined,
): ObjectRotationDraft {
  return {
    rotation_degrees: String(
      Math.round((rotation?.rotation_degrees ?? 0) * 100) / 100,
    ),
    flip_horizontal: rotation?.flip_horizontal ?? false,
    flip_vertical: rotation?.flip_vertical ?? false,
  };
}

function objectRotationFromDraft(
  draft: ObjectRotationDraft,
  current: ObjectRotation | null | undefined,
): ObjectRotation | null {
  const degrees = Number(draft.rotation_degrees);
  if (!draft.rotation_degrees.trim() || !Number.isFinite(degrees)) return null;
  // Keep the exact stored angle when the rounded display value is unchanged.
  const unchanged =
    current &&
    draft.rotation_degrees === objectRotationDraft(current).rotation_degrees;
  const normalized = unchanged
    ? current.rotation_degrees
    : Math.round((((degrees % 360) + 360) % 360) * 100) / 100;
  return {
    rotation_degrees: normalized === 360 ? 0 : normalized,
    flip_horizontal: draft.flip_horizontal,
    flip_vertical: draft.flip_vertical,
  };
}

function sameObjectRotation(left: ObjectRotation, right: ObjectRotation) {
  return (
    left.rotation_degrees === right.rotation_degrees &&
    left.flip_horizontal === right.flip_horizontal &&
    left.flip_vertical === right.flip_vertical
  );
}

function pictureAdjustmentDraft(
  adjustment: PictureAdjustment | null | undefined,
): PictureAdjustmentDraft {
  return {
    brightness_percent: String(adjustment?.brightness_percent ?? 0),
    contrast_percent: String(adjustment?.contrast_percent ?? 0),
    grayscale: adjustment?.grayscale ?? false,
  };
}

function pictureAdjustmentFromDraft(
  draft: PictureAdjustmentDraft,
): PictureAdjustment | null {
  const brightness = Number(draft.brightness_percent);
  const contrast = Number(draft.contrast_percent);
  if (
    !draft.brightness_percent.trim() ||
    !draft.contrast_percent.trim() ||
    ![brightness, contrast].every(
      (value) => Number.isInteger(value) && value >= -100 && value <= 100,
    )
  ) {
    return null;
  }
  return {
    brightness_percent: brightness,
    contrast_percent: contrast,
    grayscale: draft.grayscale,
  };
}

function samePictureAdjustment(
  left: PictureAdjustment,
  right: PictureAdjustment,
): boolean {
  return (
    left.brightness_percent === right.brightness_percent &&
    left.contrast_percent === right.contrast_percent &&
    left.grayscale === right.grayscale
  );
}

function draftForShapeStyle(style: ShapeStyle | null): ShapeStyleDraft {
  return {
    fill_color: style?.fill_color ?? "#000000",
    line_color: style?.line_color ?? "#000000",
    line_width_pt: style?.line_width_pt?.toString() ?? "",
    fill_transparency_percent:
      style?.fill_transparency_percent?.toString() ?? "",
    line_dash: style?.line_dash ?? "",
  };
}

function pictureCropFromDraft(draft: PictureCropDraft): PictureCrop | null {
  const values = Object.fromEntries(
    Object.entries(draft).map(([field, value]) => [field, Number(value)]),
  ) as PictureCrop;
  const percentages = [
    values.left_percent,
    values.right_percent,
    values.top_percent,
    values.bottom_percent,
  ];
  if (
    Object.values(draft).some((value) => !value.trim()) ||
    percentages.some(
      (value) =>
        !Number.isFinite(value) ||
        value < 0 ||
        value >= 100 ||
        Math.abs(value * 1_000 - Math.round(value * 1_000)) > 1e-6,
    ) ||
    values.left_percent + values.right_percent >= 100 ||
    values.top_percent + values.bottom_percent >= 100
  ) {
    return null;
  }
  return values;
}

function samePictureCrop(left: PictureCrop, right: PictureCrop): boolean {
  return (
    left.left_percent === right.left_percent &&
    left.right_percent === right.right_percent &&
    left.top_percent === right.top_percent &&
    left.bottom_percent === right.bottom_percent
  );
}

function geometryFromDraft(
  draft: GeometryDraft,
  original: ObjectGeometry,
  slideWidthEmu: number,
  slideHeightEmu: number,
): ObjectGeometry | null {
  const toEmu = (value: string, originalValue: number) => {
    if (value === (originalValue / EMU_PER_INCH).toFixed(3))
      return originalValue;
    if (!value.trim()) return null;
    const inches = Number(value);
    if (!Number.isFinite(inches) || inches < 0) return null;
    return Math.round(inches * EMU_PER_INCH);
  };
  const x = toEmu(draft.x, original.x_emu);
  const y = toEmu(draft.y, original.y_emu);
  const width = toEmu(draft.width, original.width_emu);
  const height = toEmu(draft.height, original.height_emu);
  if (
    x === null ||
    y === null ||
    width === null ||
    height === null ||
    x < 0 ||
    y < 0 ||
    width < 1 ||
    height < 1 ||
    x + width > slideWidthEmu ||
    y + height > slideHeightEmu
  ) {
    return null;
  }
  return {
    x_emu: x,
    y_emu: y,
    width_emu: width,
    height_emu: height,
  };
}

function sameGeometry(left: ObjectGeometry, right: ObjectGeometry): boolean {
  return (
    left.x_emu === right.x_emu &&
    left.y_emu === right.y_emu &&
    left.width_emu === right.width_emu &&
    left.height_emu === right.height_emu
  );
}

function isPresentationObject(value: unknown): value is PresentationObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const candidate = value as Partial<PresentationObject>;
  const kinds = new Set(["sp", "pic", "graphicFrame", "cxnSp", "grpSp"]);
  const geometry = candidate.geometry;
  const validGeometry =
    geometry === null ||
    (!!geometry &&
      [
        geometry.x_emu,
        geometry.y_emu,
        geometry.width_emu,
        geometry.height_emu,
      ].every((coordinate) => Number.isSafeInteger(coordinate)) &&
      geometry.width_emu > 0 &&
      geometry.height_emu > 0 &&
      (candidate.geometry_editable !== true ||
        (geometry.x_emu >= 0 && geometry.y_emu >= 0)));
  const pictureCrop = candidate.picture_crop;
  const validPictureCrop =
    pictureCrop === null ||
    (!!pictureCrop &&
      [
        pictureCrop.left_percent,
        pictureCrop.right_percent,
        pictureCrop.top_percent,
        pictureCrop.bottom_percent,
      ].every(
        (percentage) =>
          typeof percentage === "number" &&
          Number.isFinite(percentage) &&
          percentage >= 0 &&
          percentage < 100 &&
          Math.abs(percentage * 1_000 - Math.round(percentage * 1_000)) <= 1e-6,
      ) &&
      pictureCrop.left_percent + pictureCrop.right_percent < 100 &&
      pictureCrop.top_percent + pictureCrop.bottom_percent < 100);
  const hyperlink = candidate.hyperlink;
  const validHyperlink =
    hyperlink == null ||
    (typeof hyperlink === "object" &&
      (hyperlink.url === null ||
        (typeof hyperlink.url === "string" && hyperlink.url.length <= 2048)) &&
      (hyperlink.slide_id == null ||
        (typeof hyperlink.slide_id === "string" &&
          UUID_PATTERN.test(hyperlink.slide_id))));
  const rotation = candidate.rotation;
  const validRotation =
    rotation === undefined ||
    rotation === null ||
    (!!rotation &&
      typeof rotation.rotation_degrees === "number" &&
      Number.isFinite(rotation.rotation_degrees) &&
      rotation.rotation_degrees >= 0 &&
      rotation.rotation_degrees < 360 &&
      typeof rotation.flip_horizontal === "boolean" &&
      typeof rotation.flip_vertical === "boolean");
  const pictureAdjustment = candidate.picture_adjustment;
  const validPictureAdjustment =
    pictureAdjustment === undefined ||
    pictureAdjustment === null ||
    (!!pictureAdjustment &&
      [
        pictureAdjustment.brightness_percent,
        pictureAdjustment.contrast_percent,
      ].every(
        (value) =>
          typeof value === "number" &&
          Number.isInteger(value) &&
          value >= -100 &&
          value <= 100,
      ) &&
      typeof pictureAdjustment.grayscale === "boolean");
  const shapeStyle = candidate.shape_style;
  const validShapeStyle =
    shapeStyle === null ||
    (!!shapeStyle &&
      typeof shapeStyle.editable === "boolean" &&
      (shapeStyle.fingerprint === null ||
        (typeof shapeStyle.fingerprint === "string" &&
          /^[0-9a-f]{64}$/.test(shapeStyle.fingerprint))) &&
      (shapeStyle.fill_color === null ||
        (typeof shapeStyle.fill_color === "string" &&
          /^#[0-9A-F]{6}$/.test(shapeStyle.fill_color))) &&
      typeof shapeStyle.fill_editable === "boolean" &&
      (shapeStyle.line_color === null ||
        (typeof shapeStyle.line_color === "string" &&
          /^#[0-9A-F]{6}$/.test(shapeStyle.line_color))) &&
      typeof shapeStyle.line_editable === "boolean" &&
      (shapeStyle.line_width_pt === null ||
        (typeof shapeStyle.line_width_pt === "number" &&
          shapeStyle.line_width_pt > 0 &&
          shapeStyle.line_width_pt <= 20)) &&
      (shapeStyle.line_dash === null ||
        SHAPE_LINE_DASHES.some(([value]) => value === shapeStyle.line_dash)) &&
      typeof shapeStyle.line_format_editable === "boolean" &&
      (shapeStyle.fill_transparency_percent == null ||
        (Number.isInteger(shapeStyle.fill_transparency_percent) &&
          shapeStyle.fill_transparency_percent >= 0 &&
          shapeStyle.fill_transparency_percent <= 100)) &&
      (!shapeStyle.editable ||
        ((candidate.kind === "sp" || candidate.kind === "pic") &&
          shapeStyle.fingerprint !== null &&
          (shapeStyle.fill_editable ||
            shapeStyle.line_editable ||
            shapeStyle.line_format_editable ||
            shapeStyle.shadow_editable === true))));
  return (
    typeof candidate.object_id === "string" &&
    UUID_PATTERN.test(candidate.object_id) &&
    typeof candidate.ooxml_shape_id === "string" &&
    candidate.ooxml_shape_id.length > 0 &&
    typeof candidate.name === "string" &&
    candidate.name.length <= 256 &&
    typeof candidate.kind === "string" &&
    kinds.has(candidate.kind) &&
    typeof candidate.geometry_editable === "boolean" &&
    typeof candidate.delete_editable === "boolean" &&
    typeof candidate.group_editable === "boolean" &&
    (candidate.group_reason === null ||
      typeof candidate.group_reason === "string") &&
    validPictureCrop &&
    validPictureAdjustment &&
    validRotation &&
    validHyperlink &&
    (rotation == null || candidate.kind === "sp" || candidate.kind === "pic") &&
    (pictureAdjustment == null || candidate.kind === "pic") &&
    validShapeStyle &&
    (pictureCrop === null || candidate.kind === "pic") &&
    validGeometry &&
    (!candidate.geometry_editable || geometry !== null) &&
    (!candidate.delete_editable ||
      (candidate.geometry_editable &&
        (candidate.kind === "sp" ||
          candidate.kind === "pic" ||
          candidate.kind === "graphicFrame" ||
          candidate.kind === "grpSp")))
  );
}

function isTextStyle(value: unknown): value is TextStyle {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const candidate = value as Partial<TextStyle>;
  const validNullableBoolean =
    candidate.bold === null || typeof candidate.bold === "boolean";
  const validNullableItalic =
    (candidate.italic === null || typeof candidate.italic === "boolean") &&
    (candidate.underline == null || typeof candidate.underline === "boolean") &&
    (candidate.strikethrough == null ||
      typeof candidate.strikethrough === "boolean") &&
    (candidate.highlight_color == null ||
      (typeof candidate.highlight_color === "string" &&
        /^#[0-9A-F]{6}$/.test(candidate.highlight_color))) &&
    (candidate.font_family == null ||
      (typeof candidate.font_family === "string" &&
        candidate.font_family.length <= 256));
  const validFontSize =
    candidate.font_size_pt === null ||
    (typeof candidate.font_size_pt === "number" &&
      Number.isFinite(candidate.font_size_pt) &&
      candidate.font_size_pt > 0 &&
      candidate.font_size_pt <= 4_000);
  const validFontColor =
    candidate.font_color === null ||
    (typeof candidate.font_color === "string" &&
      /^#[0-9A-F]{6}$/.test(candidate.font_color));
  const validAlignment =
    candidate.alignment === null ||
    (typeof candidate.alignment === "string" &&
      TEXT_ALIGNMENTS.some((alignment) => alignment === candidate.alignment));
  const validBulletDecoration =
    (candidate.bullet_color === null ||
      (typeof candidate.bullet_color === "string" &&
        /^#[0-9A-F]{6}$/.test(candidate.bullet_color))) &&
    (candidate.bullet_size_percent === null ||
      (typeof candidate.bullet_size_percent === "number" &&
        Number.isSafeInteger(candidate.bullet_size_percent) &&
        candidate.bullet_size_percent >= 25 &&
        candidate.bullet_size_percent <= 400)) &&
    typeof candidate.bullet_color_editable === "boolean" &&
    typeof candidate.bullet_size_editable === "boolean" &&
    (candidate.numbering_start === null ||
      (typeof candidate.numbering_start === "number" &&
        Number.isSafeInteger(candidate.numbering_start) &&
        candidate.numbering_start >= 1 &&
        candidate.numbering_start <= 9999)) &&
    typeof candidate.numbering_start_editable === "boolean";
  const validBulletState =
    candidate.bullet_state === null ||
    (typeof candidate.bullet_state === "string" &&
      TEXT_BULLET_STATES.some((state) => state === candidate.bullet_state));
  const validLeftIndent =
    candidate.left_indent_pt === null ||
    (typeof candidate.left_indent_pt === "number" &&
      Number.isSafeInteger(candidate.left_indent_pt) &&
      candidate.left_indent_pt >= 0 &&
      candidate.left_indent_pt <= MAX_TEXT_LEFT_INDENT_PT);
  const validFirstLineIndent =
    candidate.first_line_indent_pt === null ||
    (typeof candidate.first_line_indent_pt === "number" &&
      Number.isSafeInteger(candidate.first_line_indent_pt) &&
      candidate.first_line_indent_pt >= -MAX_TEXT_FIRST_LINE_INDENT_PT &&
      candidate.first_line_indent_pt <= MAX_TEXT_FIRST_LINE_INDENT_PT);
  const validLineSpacing =
    candidate.line_spacing_pt === null ||
    (typeof candidate.line_spacing_pt === "number" &&
      Number.isSafeInteger(candidate.line_spacing_pt) &&
      candidate.line_spacing_pt >= 1 &&
      candidate.line_spacing_pt <= MAX_TEXT_LINE_SPACING_PT);
  const validSpaceBefore =
    candidate.space_before_pt === null ||
    (typeof candidate.space_before_pt === "number" &&
      Number.isSafeInteger(candidate.space_before_pt) &&
      candidate.space_before_pt >= 0 &&
      candidate.space_before_pt <= MAX_TEXT_PARAGRAPH_SPACING_PT);
  const validSpaceAfter =
    candidate.space_after_pt === null ||
    (typeof candidate.space_after_pt === "number" &&
      Number.isSafeInteger(candidate.space_after_pt) &&
      candidate.space_after_pt >= 0 &&
      candidate.space_after_pt <= MAX_TEXT_PARAGRAPH_SPACING_PT);
  return (
    typeof candidate.editable === "boolean" &&
    (candidate.fingerprint === null ||
      (typeof candidate.fingerprint === "string" &&
        /^[0-9a-f]{64}$/.test(candidate.fingerprint))) &&
    validNullableBoolean &&
    validNullableItalic &&
    validFontSize &&
    validFontColor &&
    typeof candidate.color_editable === "boolean" &&
    validAlignment &&
    typeof candidate.alignment_editable === "boolean" &&
    validBulletState &&
    validBulletDecoration &&
    typeof candidate.bullet_editable === "boolean" &&
    validLeftIndent &&
    typeof candidate.left_indent_editable === "boolean" &&
    validFirstLineIndent &&
    typeof candidate.first_line_indent_editable === "boolean" &&
    validLineSpacing &&
    typeof candidate.line_spacing_editable === "boolean" &&
    validSpaceBefore &&
    typeof candidate.space_before_editable === "boolean" &&
    validSpaceAfter &&
    typeof candidate.space_after_editable === "boolean"
  );
}

function useSvgObjectUrl(svg: string | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!svg) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(
      new Blob([svg], { type: "image/svg+xml;charset=utf-8" }),
    );
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [svg]);
  return url;
}

function usePngObjectUrl(image: Uint8Array | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!image) {
      setUrl(null);
      return;
    }
    const copy = new Uint8Array(image.byteLength);
    copy.set(image);
    const objectUrl = URL.createObjectURL(
      new Blob([copy.buffer as ArrayBuffer], { type: "image/png" }),
    );
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [image]);
  return url;
}

function sourceLabel(
  source: SourceSummary,
  currentSlideCount?: number,
): string {
  return `${source.original_name} · ${Math.max(1, currentSlideCount ?? source.source_units_count)} slides`;
}

function readImageAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () =>
      reject(new Error("The selected image could not be read."));
    reader.onabort = () =>
      reject(new Error("Reading the selected image was cancelled."));
    reader.onload = () => {
      const dataUrl = reader.result;
      if (typeof dataUrl !== "string") {
        reject(new Error("The selected image could not be read."));
        return;
      }
      const comma = dataUrl.indexOf(",");
      if (comma < 0 || !dataUrl.slice(0, comma).endsWith(";base64")) {
        reject(new Error("The selected image could not be encoded."));
        return;
      }
      resolve(dataUrl.slice(comma + 1));
    };
    reader.readAsDataURL(file);
  });
}

export function PresentationWorkspace({
  project,
  sources,
  visible,
  onGoToSources,
  onPresentationCreated,
  onGoToRehearsal,
  onVoiceActiveChange,
}: {
  project: ProjectSummary;
  sources: SourceSummary[];
  visible: boolean;
  onGoToSources: () => void;
  onPresentationCreated: () => Promise<void>;
  onGoToRehearsal: (target: {
    projectId: string;
    revisionId: string;
    label: string;
  }) => void;
  onVoiceActiveChange: (active: boolean) => void;
}) {
  const decks = useMemo(
    () =>
      sources.filter(
        (source) =>
          source.kind === "presentation" &&
          source.source_type === "pptx" &&
          source.parse_status === "ready",
      ),
    [sources],
  );
  const [takeawayFinding, setTakeawayFinding] = useState<{
    revision: string;
    document: string;
    ordinal: number;
    text: string;
  } | null>(null);
  const [creatingPresentation, setCreatingPresentation] = useState(false);
  const [pendingCreatedId, setPendingCreatedId] = useState<string | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [loadedSourceId, setLoadedSourceId] = useState<string | null>(null);
  const [slideCount, setSlideCount] = useState(0);
  const [fidelityReport, setFidelityReport] = useState<
    ReaderOpenResult["fidelity_report"] | null
  >(null);
  const [revisionHistory, setRevisionHistory] =
    useState<RevisionHistoryResult | null>(null);
  const [currentRevision, setCurrentRevision] = useState<Pick<
    PresentationRevision,
    "revision_id" | "revision_kind" | "revision_number" | "sha256" | "byte_size"
  > | null>(null);
  const [selectedSlide, setSelectedSlide] = useState(1);
  const [inspectorPanel, setInspectorPanel] = useState("text");
  const [pendingRehearsalEdit, setPendingRehearsalEdit] = useState<{
    finding: RehearsalFinding;
    kind: "text" | "notes";
  } | null>(null);
  const [blankSlideLayoutSourceId, setBlankSlideLayoutSourceId] = useState("");
  const [slideSvg, setSlideSvg] = useState<string | null>(null);
  const [slidePng, setSlidePng] = useState<Uint8Array | null>(null);
  const [mockSvg, setMockSvgState] = useState<string | null>(null);
  const [mockPng, setMockPng] = useState<Uint8Array | null>(null);
  const [mockTextLayoutStatus, setMockTextLayoutStatus] = useState<
    "fits" | "overflow" | "unknown" | null
  >(null);
  const [layoutRiskAcknowledged, setLayoutRiskAcknowledged] = useState(false);
  const setMockSvg = useCallback((svg: string | null) => {
    setMockSvgState(svg);
    if (svg === null) {
      setMockPng(null);
      setMockTextLayoutStatus(null);
      setLayoutRiskAcknowledged(false);
    }
  }, []);
  const [textTargets, setTextTargets] = useState<TextTarget[]>([]);
  const [claimTextTargets, setClaimTextTargets] = useState<
    Array<import("./claim-source").NativeClaimTarget>
  >([]);
  const [deckClaimCandidate, setDeckClaimCandidate] = useState<{
    document: string;
    revision: string;
    slide: string;
    object_id: string;
    quote: string;
    selection_token: number;
    source_kind?: import("./claim-source").NativeClaimSourceKind;
    initial_evidence?: import("./claim-review-selection").ClaimReviewEvidence[];
  } | null>(null);
  const deckClaimSelection = useRef(0);
  const claimScanCache = useRef<ClaimScanCache>(new Map());
  useEffect(() => {
    setDeckClaimCandidate(null);
  }, [currentRevision?.revision_id]);
  const [selectedTargetHandle, setSelectedTargetHandle] = useState("");
  const [mockText, setMockText] = useState("");
  const [rewriteInstruction, setRewriteInstruction] = useState("");
  const [textRewriteProposal, setTextRewriteProposal] =
    useState<TextRewriteProposal | null>(null);
  const [rewriteBusy, setRewriteBusy] = useState(false);
  const [voiceCaptureState, setVoiceCaptureState] =
    useState<WorkspaceVoiceState>("idle");
  const [voiceCaptureId, setVoiceCaptureId] = useState<string | null>(null);
  const [voicePartial, setVoicePartial] = useState("");
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceRecognition, setVoiceRecognition] =
    useState<RecognitionReview | null>(null);
  const [voiceClarification, setVoiceClarification] = useState("");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [textStyleDraft, setTextStyleDraft] = useState<TextStyleDraft>({
    highlight_color: "#FFFF00",
    font_family: "",
    font_size_pt: "",
    font_color: "#000000",
    alignment: "",
    bullet_mode: "",
    bullet_color: "",
    bullet_size_percent: "",
    numbering_start: "",
    left_indent_pt: "",
    first_line_indent_pt: "",
    line_spacing_pt: "",
    space_before_pt: "",
    space_after_pt: "",
  });
  const [speakerNotesTarget, setSpeakerNotesTarget] =
    useState<SpeakerNotesTarget | null>(null);
  const [speakerNotesDraft, setSpeakerNotesDraft] = useState("");
  const [linkDraft, setLinkDraft] = useState({ objectId: "", value: "" });
  const [slideHidden, setSlideHidden] = useState<boolean | null>(null);
  const [footerState, setFooterState] = useState<SlideFooterState | null>(null);
  const [themeFonts, setThemeFonts] = useState<{
    heading_font: string | null;
    body_font: string | null;
    editable: boolean;
  } | null>(null);
  const [slideAnimations, setSlideAnimations] =
    useState<SlideAnimationState | null>(null);
  const [accessibility, setAccessibility] =
    useState<AccessibilityResult | null>(null);
  const [copilotPrefill, setCopilotPrefill] = useState<{
    instruction: string;
    scope: "slide" | "deck";
    nonce: number;
  } | null>(null);
  const [slideSections, setSlideSections] = useState<SlideSectionState | null>(
    null,
  );
  const [themeColors, setThemeColors] = useState<ThemeColorState | null>(null);
  const [themeColorDraft, setThemeColorDraft] = useState<
    Record<string, string>
  >({});
  const [themeFontDraft, setThemeFontDraft] = useState({
    heading: "",
    body: "",
  });
  const [footerDraft, setFooterDraft] = useState({
    numbers: false,
    text: "",
    skipTitle: true,
  });
  const [slideTransition, setSlideTransition] = useState<
    string | null | undefined
  >(undefined);
  const [slideBackground, setSlideBackground] =
    useState<SlideBackground | null>(null);
  const [slideBackgroundDraft, setSlideBackgroundDraft] = useState("#FFFFFF");
  const [newTextBoxDraft, setNewTextBoxDraft] = useState("");
  const [workspaceObjects, setWorkspaceObjects] = useState<
    PresentationObject[]
  >([]);
  const [selectedObjectId, setSelectedObjectId] = useState("");
  const [canvasSelectionEnabled, setCanvasSelectionEnabled] = useState(false);
  const [canvasSelectedIds, setCanvasSelectedIds] = useState<string[]>([]);
  const [canvasSnap, setCanvasSnap] = useState(true);
  const [canvasGuides, setCanvasGuides] = useState(false);
  const [pendingCanvasMove, setPendingCanvasMove] =
    useState<ObjectMoveRequest | null>(null);
  const restoredCanvasSelection = useRef<{
    slideId: string;
    documentId: string;
    revisionId: string;
    ids: string[];
  } | null>(null);
  const [objectClipboard, setObjectClipboard] = useState<Omit<
    ObjectPasteRequest,
    "slide_id"
  > | null>(null);
  const [formatSource, setFormatSource] = useState<{
    document_id: string;
    slide_id: string;
    object_id: string;
    name: string;
  } | null>(null);
  const [pendingObjectPaste, setPendingObjectPaste] =
    useState<ObjectPasteRequest | null>(null);
  const [pendingObjectAction, setPendingObjectAction] =
    useState<ObjectActionRequest | null>(null);
  useEffect(() => {
    setPendingObjectAction(null);
    setObjectClipboard(null);
    setFormatSource(null);
    setPendingObjectPaste(null);
    restoredCanvasSelection.current = null;
  }, [project.id]);
  const [deleteConfirmationObjectId, setDeleteConfirmationObjectId] =
    useState("");
  const [deleteConfirmationSlideId, setDeleteConfirmationSlideId] =
    useState("");
  const [objectInventoryHasMore, setObjectInventoryHasMore] = useState(false);
  const [activeSlideId, setActiveSlideId] = useState("");
  useEffect(() => {
    setCanvasSelectedIds([]);
    setPendingObjectAction(null);
    setPendingCanvasMove(null);
    setPendingObjectPaste(null);
  }, [activeSlideId, currentRevision?.revision_id]);
  useEffect(() => {
    const pending = restoredCanvasSelection.current;
    if (!pending) return;
    if (pending.documentId !== selectedSourceId) {
      restoredCanvasSelection.current = null;
      return;
    }
    if (
      pending.revisionId === currentRevision?.revision_id &&
      pending.slideId === activeSlideId &&
      UUID_PATTERN.test(activeSlideId) &&
      pending.ids.every((id) =>
        workspaceObjects.some((o) => o.object_id === id && o.geometry_editable),
      )
    ) {
      setCanvasSelectedIds(pending.ids);
      restoredCanvasSelection.current = null;
    }
  }, [
    activeSlideId,
    currentRevision?.revision_id,
    workspaceObjects,
    selectedSourceId,
  ]);
  const [objectGeometryDraft, setObjectGeometryDraft] = useState<GeometryDraft>(
    {
      x: "",
      y: "",
      width: "",
      height: "",
    },
  );
  const [objectCropDraft, setObjectCropDraft] = useState<PictureCropDraft>(() =>
    pictureCropDraft(null),
  );
  const [objectRotationDraftState, setObjectRotationDraft] =
    useState<ObjectRotationDraft>(() => objectRotationDraft(null));
  const [objectAdjustmentDraft, setObjectAdjustmentDraft] =
    useState<PictureAdjustmentDraft>(() => pictureAdjustmentDraft(null));
  const [objectStyleDraft, setObjectStyleDraft] = useState<ShapeStyleDraft>(
    () => draftForShapeStyle(null),
  );
  const [replacementPictureFile, setReplacementPictureFile] =
    useState<File | null>(null);
  const [newPictureFile, setNewPictureFile] = useState<File | null>(null);
  const [deckPictureBusy, setDeckPictureBusy] = useState(false);
  const [projectPictureBusy, setProjectPictureBusy] = useState(false);
  const pictureAssetBusy = deckPictureBusy || projectPictureBusy;
  const [newPictureGeometryBase, setNewPictureGeometryBase] =
    useState<ObjectGeometry | null>(null);
  const [newPictureGeometryDraft, setNewPictureGeometryDraft] =
    useState<GeometryDraft>({ x: "", y: "", width: "", height: "" });
  const [newPictureAltText, setNewPictureAltText] = useState("");
  const [newShapeType, setNewShapeType] = useState<NewShapeType>("rect");
  const [newShapeGeometryBase, setNewShapeGeometryBase] =
    useState<ObjectGeometry | null>(null);
  const [newShapeGeometryDraft, setNewShapeGeometryDraft] =
    useState<GeometryDraft>({ x: "", y: "", width: "", height: "" });
  const [newShapeFillColor, setNewShapeFillColor] = useState("#D7E6FF");
  const [newShapeLineColor, setNewShapeLineColor] = useState("#204A87");
  const [slideSizeEmu, setSlideSizeEmu] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [slideContext, setSlideContext] = useState<
    SourcePreviewResult["units"][number] | null
  >(null);
  const [slidePurposeDecision, setSlidePurposeDecision] =
    useState<SlidePurposeDecision | null>(null);
  const [savedSlidePurposes, setSavedSlidePurposes] = useState<
    Record<string, SavedSlidePurpose>
  >({});
  const [slidePurposeDraft, setSlidePurposeDraft] =
    useState<SlidePurpose>("unclear");
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [savingSlidePurpose, setSavingSlidePurpose] = useState(false);
  const [loadProgress, setLoadProgress] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [savingCopy, setSavingCopy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [decisionUsageLimitError, setDecisionUsageLimitError] = useState<
    string | null
  >(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [intentKind, setIntentKind] = useState<IntentKind>("text");
  const [intentText, setIntentText] = useState("");
  const [intentCounts, setIntentCounts] =
    useState<IntentCounts>(emptyIntentCounts);
  const generation = useRef(0);
  const rewriteGeneration = useRef(0);
  const voiceCaptureStateRef = useRef<WorkspaceVoiceState>("idle");
  const voiceCaptureIdRef = useRef<string | null>(null);
  const voiceReviewIdRef = useRef<string | null>(null);
  const voiceEpochRef = useRef(0);
  const voiceEditorRef = useRef<HTMLElement | null>(null);
  const cancelAfterStartRef = useRef(false);
  const workspaceMountedRef = useRef(false);
  const voiceDialogRef = useRef<HTMLDivElement | null>(null);
  const onVoiceActiveChangeRef = useRef(onVoiceActiveChange);
  onVoiceActiveChangeRef.current = onVoiceActiveChange;
  const decisionGeneration = useRef(0);
  const semanticListGeneration = useRef(0);
  const semanticSaveGeneration = useRef(0);
  const replacementPictureInput = useRef<HTMLInputElement | null>(null);
  const newPictureInput = useRef<HTMLInputElement | null>(null);
  const reader = useRef<{
    projectId: string;
    documentId: string;
    sessionId: string;
  } | null>(null);
  const worker = useRef<Worker | null>(null);
  const rendererMode = useRef<"isolated" | "legacy" | null>(null);
  const nextWorkerJob = useRef(0);
  const workerJobs = useRef(new Map<number, WorkerJob>());
  const slidePngUrl = usePngObjectUrl(slidePng);
  const slideSvgUrl = useSvgObjectUrl(slideSvg);
  const mockPngUrl = usePngObjectUrl(mockPng);
  const mockSvgUrl = useSvgObjectUrl(mockSvg);
  const slideUrl = slidePngUrl ?? slideSvgUrl;
  const mockUrl = mockPngUrl ?? mockSvgUrl;
  const hasMockPreview = mockPng !== null || mockSvg !== null;
  const selectedSource =
    decks.find((source) => source.id === selectedSourceId) ?? null;
  const savedCurrentSlidePurpose = savedSlidePurposes[activeSlideId] ?? null;
  const selectedTarget =
    textTargets.find((target) => target.key === selectedTargetHandle) ?? null;
  const voiceWorkflowActive = voiceCaptureState !== "idle";
  const setVoicePhase = useCallback(
    (phase: WorkspaceVoiceState) => {
      voiceCaptureStateRef.current = phase;
      setVoiceCaptureState(phase);
      onVoiceActiveChange(phase !== "idle");
    },
    [onVoiceActiveChange],
  );

  useEffect(() => {
    voiceEpochRef.current++;
    workspaceMountedRef.current = true;
    return () => {
      workspaceMountedRef.current = false;
      voiceEpochRef.current++;
      cancelAfterStartRef.current = true;
      const captureId = voiceCaptureIdRef.current;
      voiceCaptureIdRef.current = null;
      voiceReviewIdRef.current = null;
      if (captureId) {
        void requestCore("presentation.workspace.voice_cancel", {
          project_id: project.id,
          capture_id: captureId,
        }).catch(() => undefined);
      }
      onVoiceActiveChangeRef.current(false);
    };
  }, [project.id]);

  useEffect(() => {
    if (voiceCaptureState !== "listening" || !voiceCaptureId) return;
    return window.presenterCopilot.core.onEvent((event) => {
      if (event.event !== "asr.partial") return;
      if (event.payload.session_id !== voiceCaptureId) return;
      if (typeof event.payload.text === "string")
        setVoicePartial(event.payload.text);
    });
  }, [voiceCaptureId, voiceCaptureState]);

  useEffect(() => {
    if (!voiceWorkflowActive) return;
    const dialog = voiceDialogRef.current;
    const focusTarget =
      voiceCaptureState === "review"
        ? dialog?.querySelector<HTMLTextAreaElement>("textarea")
        : dialog?.querySelector<HTMLButtonElement>("button:not(:disabled)");
    focusTarget?.focus();
  }, [voiceCaptureState, voiceWorkflowActive]);
  const replacementTextFontSize = /^\d+$/.test(textStyleDraft.font_size_pt)
    ? Number(textStyleDraft.font_size_pt)
    : null;
  const parsedTextLeftIndent = /^\d+$/.test(textStyleDraft.left_indent_pt)
    ? Number(textStyleDraft.left_indent_pt)
    : null;
  const replacementTextLeftIndent =
    parsedTextLeftIndent !== null &&
    Number.isSafeInteger(parsedTextLeftIndent) &&
    parsedTextLeftIndent >= 0 &&
    parsedTextLeftIndent <= MAX_TEXT_LEFT_INDENT_PT
      ? parsedTextLeftIndent
      : null;
  const invalidTextLeftIndent =
    textStyleDraft.left_indent_pt !== "" && replacementTextLeftIndent === null;
  const parsedTextFirstLineIndent = /^-?\d+$/.test(
    textStyleDraft.first_line_indent_pt,
  )
    ? Number(textStyleDraft.first_line_indent_pt)
    : null;
  const replacementTextFirstLineIndent =
    parsedTextFirstLineIndent !== null &&
    Number.isSafeInteger(parsedTextFirstLineIndent) &&
    parsedTextFirstLineIndent >= -MAX_TEXT_FIRST_LINE_INDENT_PT &&
    parsedTextFirstLineIndent <= MAX_TEXT_FIRST_LINE_INDENT_PT
      ? parsedTextFirstLineIndent
      : null;
  const invalidTextFirstLineIndent =
    textStyleDraft.first_line_indent_pt !== "" &&
    replacementTextFirstLineIndent === null;
  const parsedTextLineSpacing = /^\d+$/.test(textStyleDraft.line_spacing_pt)
    ? Number(textStyleDraft.line_spacing_pt)
    : null;
  const replacementTextLineSpacing =
    parsedTextLineSpacing !== null &&
    Number.isSafeInteger(parsedTextLineSpacing) &&
    parsedTextLineSpacing >= 1 &&
    parsedTextLineSpacing <= MAX_TEXT_LINE_SPACING_PT
      ? parsedTextLineSpacing
      : null;
  const invalidTextLineSpacing =
    textStyleDraft.line_spacing_pt !== "" &&
    replacementTextLineSpacing === null;
  const parsedTextSpaceBefore = /^\d+$/.test(textStyleDraft.space_before_pt)
    ? Number(textStyleDraft.space_before_pt)
    : null;
  const replacementTextSpaceBefore =
    parsedTextSpaceBefore !== null &&
    Number.isSafeInteger(parsedTextSpaceBefore) &&
    parsedTextSpaceBefore >= 0 &&
    parsedTextSpaceBefore <= MAX_TEXT_PARAGRAPH_SPACING_PT
      ? parsedTextSpaceBefore
      : null;
  const parsedTextSpaceAfter = /^\d+$/.test(textStyleDraft.space_after_pt)
    ? Number(textStyleDraft.space_after_pt)
    : null;
  const replacementTextSpaceAfter =
    parsedTextSpaceAfter !== null &&
    Number.isSafeInteger(parsedTextSpaceAfter) &&
    parsedTextSpaceAfter >= 0 &&
    parsedTextSpaceAfter <= MAX_TEXT_PARAGRAPH_SPACING_PT
      ? parsedTextSpaceAfter
      : null;
  const invalidTextParagraphSpacing =
    invalidTextLineSpacing ||
    (textStyleDraft.space_before_pt !== "" &&
      replacementTextSpaceBefore === null) ||
    (textStyleDraft.space_after_pt !== "" &&
      replacementTextSpaceAfter === null);
  const replacementTextBulletMode = TEXT_BULLET_STATES.find(
    (mode) => mode === textStyleDraft.bullet_mode,
  );
  const invalidTextBulletMode =
    textStyleDraft.bullet_mode !== "" && !replacementTextBulletMode;
  const parsedBulletSize = /^\d+$/.test(textStyleDraft.bullet_size_percent)
    ? Number(textStyleDraft.bullet_size_percent)
    : null;
  const replacementBulletSize =
    parsedBulletSize !== null &&
    parsedBulletSize >= 25 &&
    parsedBulletSize <= 400
      ? parsedBulletSize
      : null;
  const invalidBulletSize =
    textStyleDraft.bullet_size_percent !== "" && replacementBulletSize === null;
  const replacementBulletMarker: TextStyleChange = {};
  if (
    selectedTarget?.style.bullet_color_editable &&
    /^#[0-9A-F]{6}$/.test(textStyleDraft.bullet_color) &&
    textStyleDraft.bullet_color !== selectedTarget.style.bullet_color
  )
    replacementBulletMarker.bullet_color = textStyleDraft.bullet_color;
  if (
    selectedTarget?.style.bullet_size_editable &&
    replacementBulletSize !== null &&
    replacementBulletSize !== selectedTarget.style.bullet_size_percent
  )
    replacementBulletMarker.bullet_size_percent = replacementBulletSize;
  const parsedNumberingStart = /^\d+$/.test(textStyleDraft.numbering_start)
    ? Number(textStyleDraft.numbering_start)
    : null;
  const replacementNumberingStart =
    parsedNumberingStart !== null &&
    parsedNumberingStart >= 1 &&
    parsedNumberingStart <= 9999
      ? parsedNumberingStart
      : null;
  const numberedListSelected = (
    replacementTextBulletMode ??
    selectedTarget?.style.bullet_state ??
    ""
  ).startsWith("numbered");
  const invalidNumberingStart =
    textStyleDraft.numbering_start !== "" &&
    (replacementNumberingStart === null || !numberedListSelected);
  const replacementTextAlignment = TEXT_ALIGNMENTS.find(
    (alignment) => alignment === textStyleDraft.alignment,
  );
  const replacementTextParagraphStyle: TextStyleChange = {};
  if (replacementTextAlignment && selectedTarget?.style.alignment_editable) {
    replacementTextParagraphStyle.alignment = replacementTextAlignment;
  }
  if (
    replacementTextBulletMode &&
    selectedTarget?.style.bullet_editable &&
    replacementTextBulletMode !== selectedTarget.style.bullet_state
  ) {
    replacementTextParagraphStyle.bullet_mode = replacementTextBulletMode;
  }
  if (
    replacementNumberingStart !== null &&
    numberedListSelected &&
    selectedTarget?.style.numbering_start_editable &&
    replacementNumberingStart !== (selectedTarget.style.numbering_start ?? 1)
  ) {
    replacementTextParagraphStyle.numbering_start = replacementNumberingStart;
  }
  if (
    replacementTextLeftIndent !== null &&
    selectedTarget?.style.left_indent_editable &&
    replacementTextLeftIndent !== selectedTarget.style.left_indent_pt
  ) {
    replacementTextParagraphStyle.left_indent_pt = replacementTextLeftIndent;
  }
  if (
    replacementTextFirstLineIndent !== null &&
    selectedTarget?.style.first_line_indent_editable &&
    replacementTextFirstLineIndent !== selectedTarget.style.first_line_indent_pt
  ) {
    replacementTextParagraphStyle.first_line_indent_pt =
      replacementTextFirstLineIndent;
  }
  if (
    replacementTextLineSpacing !== null &&
    selectedTarget?.style.line_spacing_editable &&
    replacementTextLineSpacing !== selectedTarget.style.line_spacing_pt
  ) {
    replacementTextParagraphStyle.line_spacing_pt = replacementTextLineSpacing;
  }
  if (
    replacementTextSpaceBefore !== null &&
    selectedTarget?.style.space_before_editable &&
    replacementTextSpaceBefore !== selectedTarget.style.space_before_pt
  ) {
    replacementTextParagraphStyle.space_before_pt = replacementTextSpaceBefore;
  }
  if (
    replacementTextSpaceAfter !== null &&
    selectedTarget?.style.space_after_editable &&
    replacementTextSpaceAfter !== selectedTarget.style.space_after_pt
  ) {
    replacementTextParagraphStyle.space_after_pt = replacementTextSpaceAfter;
  }
  const selectedObject =
    workspaceObjects.find((object) => object.object_id === selectedObjectId) ??
    null;
  const textRewriteProposalMatchesSelection = Boolean(
    textRewriteProposal &&
    selectedSource &&
    currentRevision &&
    selectedTarget &&
    textRewriteProposal.document_id === selectedSource.id &&
    textRewriteProposal.revision_id === currentRevision.revision_id &&
    textRewriteProposal.slide_id === selectedTarget.slide_id &&
    textRewriteProposal.slide_number === selectedSlide &&
    textRewriteProposal.object_id === selectedTarget.object_id &&
    textRewriteProposal.current_text === selectedTarget.text,
  );
  const replacementObjectGeometry =
    selectedObject?.geometry && slideSizeEmu
      ? geometryFromDraft(
          objectGeometryDraft,
          selectedObject.geometry,
          slideSizeEmu.width,
          slideSizeEmu.height,
        )
      : null;
  const newPictureGeometry =
    newPictureGeometryBase && slideSizeEmu
      ? geometryFromDraft(
          newPictureGeometryDraft,
          newPictureGeometryBase,
          slideSizeEmu.width,
          slideSizeEmu.height,
        )
      : null;
  const newShapeGeometry =
    newShapeGeometryBase && slideSizeEmu
      ? geometryFromDraft(
          newShapeGeometryDraft,
          newShapeGeometryBase,
          slideSizeEmu.width,
          slideSizeEmu.height,
        )
      : null;
  const replacementPictureCrop = pictureCropFromDraft(objectCropDraft);
  const replacementObjectRotation = objectRotationFromDraft(
    objectRotationDraftState,
    selectedObject?.rotation,
  );
  const replacementPictureAdjustment = pictureAdjustmentFromDraft(
    objectAdjustmentDraft,
  );

  useEffect(() => {
    decisionGeneration.current += 1;
    rewriteGeneration.current += 1;
    semanticSaveGeneration.current += 1;
    setSlidePurposeDecision(null);
    setTextRewriteProposal(null);
    setRewriteBusy(false);
    setSavingSlidePurpose(false);
  }, [
    activeSlideId,
    currentRevision?.revision_id,
    selectedSlide,
    selectedSourceId,
  ]);

  useEffect(() => {
    setSlidePurposeDraft(
      savedSlidePurposes[activeSlideId]?.purpose ?? "unclear",
    );
  }, [activeSlideId, savedSlidePurposes]);

  useEffect(() => {
    const attempt = ++semanticListGeneration.current;
    setSavedSlidePurposes({});
    const source = selectedSource;
    const revision = currentRevision;
    if (!source || !revision || loadedSourceId !== source.id || loading) {
      return () => {
        if (semanticListGeneration.current === attempt) {
          semanticListGeneration.current += 1;
        }
      };
    }

    void (async () => {
      try {
        const result = unwrapInvokeResult(
          await window.presenterCopilot.core.request<SlidePurposeListResult>(
            "presentation.workspace.list_slide_purposes",
            {
              project_id: project.id,
              document_id: source.id,
              revision_id: revision.revision_id,
            },
          ),
        );
        if (
          !result ||
          result.revision_id !== revision.revision_id ||
          !Array.isArray(result.items)
        ) {
          throw new Error("Saved slide purposes could not be verified.");
        }
        const next: Record<string, SavedSlidePurpose> = {};
        for (const item of result.items) {
          if (
            !item ||
            !UUID_PATTERN.test(item.slide_id) ||
            item.revision_id !== revision.revision_id ||
            !isSlidePurpose(item.purpose) ||
            item.provenance !== "user_confirmed" ||
            typeof item.created_at !== "string" ||
            typeof item.updated_at !== "string" ||
            next[item.slide_id]
          ) {
            throw new Error("Saved slide purposes could not be verified.");
          }
          next[item.slide_id] = item;
        }
        if (attempt === semanticListGeneration.current) {
          setSavedSlidePurposes(next);
        }
      } catch (caught) {
        if (attempt === semanticListGeneration.current) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Saved slide purposes could not be loaded.",
          );
        }
      }
    })();

    return () => {
      if (semanticListGeneration.current === attempt) {
        semanticListGeneration.current += 1;
      }
    };
  }, [
    currentRevision?.revision_id,
    loadedSourceId,
    loading,
    project.id,
    selectedSourceId,
  ]);

  useEffect(() => {
    setReplacementPictureFile(null);
    setNewPictureFile(null);
    setNewPictureGeometryBase(null);
    setNewPictureGeometryDraft({ x: "", y: "", width: "", height: "" });
    setNewPictureAltText("");
    if (replacementPictureInput.current) {
      replacementPictureInput.current.value = "";
    }
    if (newPictureInput.current) {
      newPictureInput.current.value = "";
    }
  }, [
    activeSlideId,
    currentRevision?.revision_id,
    selectedObjectId,
    selectedSourceId,
  ]);

  async function classifyCurrentSlide() {
    const source = selectedSource;
    const revision = currentRevision;
    if (
      !source ||
      !revision ||
      loadedSourceId !== source.id ||
      loading ||
      decisionBusy
    ) {
      return;
    }
    const attempt = ++decisionGeneration.current;
    setDecisionBusy(true);
    setError(null);
    setDecisionUsageLimitError(null);
    try {
      const result = unwrapInvokeResult(
        await window.presenterCopilot.core.request<SlidePurposeDecision>(
          "presentation.workspace.classify_slide",
          {
            project_id: project.id,
            document_id: source.id,
            revision_id: revision.revision_id,
            slide_number: selectedSlide,
          },
        ),
      );
      const purposes = new Set<string>(SLIDE_PURPOSES);
      const probabilitiesValid =
        result?.probabilities === null ||
        (typeof result?.probabilities === "object" &&
          !Array.isArray(result.probabilities) &&
          Object.entries(result.probabilities).every(
            ([purpose, probability]) =>
              purposes.has(purpose) &&
              typeof probability === "number" &&
              Number.isFinite(probability) &&
              probability >= 0 &&
              probability <= 1,
          ));
      if (
        attempt !== decisionGeneration.current ||
        !result ||
        !UUID_PATTERN.test(result.provider_run_id) ||
        result.revision_id !== revision.revision_id ||
        !UUID_PATTERN.test(result.slide_id) ||
        result.slide_number !== selectedSlide ||
        !purposes.has(result.purpose) ||
        !isActiveTypedDecisionProviderId(result.provider_id) ||
        typeof result.model_id !== "string" ||
        result.model_id.length > 120 ||
        !Number.isSafeInteger(result.latency_ms) ||
        result.latency_ms < 0 ||
        (result.confidence !== null &&
          (!Number.isFinite(result.confidence) ||
            result.confidence < 0 ||
            result.confidence > 1)) ||
        !probabilitiesValid ||
        result.requires_user_review !== true
      ) {
        if (attempt === decisionGeneration.current) {
          throw new Error("The slide-purpose result could not be verified.");
        }
        return;
      }
      setSlidePurposeDecision(result);
      setSlidePurposeDraft(result.purpose);
      setNotice("Slide-purpose suggestion ready. Review it before using it.");
    } catch (caught) {
      if (attempt === decisionGeneration.current) {
        const coreError = isCoreError(caught) ? caught : null;
        const message =
          coreError?.message ??
          (caught instanceof Error
            ? caught.message
            : "The slide-purpose decision could not be completed.");
        let usageLimitError: string | null = null;
        if (coreError?.code === "DECISION_PROVIDER_QUOTA_EXCEEDED") {
          try {
            const status = unwrapInvokeResult(
              await window.presenterCopilot.core.request<TypedDecisionProviderStatus>(
                "provider.decision.status",
              ),
            );
            if (status.selected_provider_id === "openai_chatgpt_plan") {
              usageLimitError = message;
            }
          } catch {
            // Keep the provider error; the optional usage link is unavailable.
          }
        }
        setError(message);
        setDecisionUsageLimitError(usageLimitError);
      }
    } finally {
      if (attempt === decisionGeneration.current) setDecisionBusy(false);
    }
  }

  async function openChatGPTUsageSettings() {
    try {
      const result =
        await window.presenterCopilot.chatgptPlan.openUsageSettings();
      if (result.ok) {
        setNotice("Opened ChatGPT usage settings.");
      } else {
        setError(result.error.message);
      }
    } catch {
      setError("Could not open ChatGPT usage settings.");
    }
  }

  async function saveSlidePurpose() {
    const source = selectedSource;
    const revision = currentRevision;
    const slideId = activeSlideId;
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(slideId) ||
      loadedSourceId !== source.id ||
      loading ||
      savingSlidePurpose
    ) {
      return;
    }

    const attempt = semanticSaveGeneration.current;
    setSavingSlidePurpose(true);
    setError(null);
    setNotice(null);
    try {
      const result = unwrapInvokeResult(
        await window.presenterCopilot.core.request<SavedSlidePurpose>(
          "presentation.workspace.save_slide_purpose",
          {
            project_id: project.id,
            document_id: source.id,
            revision_id: revision.revision_id,
            slide_id: slideId,
            slide_number: selectedSlide,
            purpose: slidePurposeDraft,
          },
        ),
      );
      if (
        !result ||
        result.revision_id !== revision.revision_id ||
        result.slide_id !== slideId ||
        result.purpose !== slidePurposeDraft ||
        result.provenance !== "user_confirmed" ||
        typeof result.created_at !== "string" ||
        typeof result.updated_at !== "string"
      ) {
        throw new Error("The saved slide purpose could not be verified.");
      }
      if (attempt !== semanticSaveGeneration.current) return;
      setSavedSlidePurposes((current) => ({ ...current, [slideId]: result }));
      setNotice(
        `Saved “${result.purpose.replaceAll("_", " ")}” for revision ${revision.revision_number}.`,
      );
    } catch (caught) {
      if (attempt === semanticSaveGeneration.current) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The slide purpose could not be saved.",
        );
      }
    } finally {
      if (attempt === semanticSaveGeneration.current) {
        setSavingSlidePurpose(false);
      }
    }
  }

  const saveUnchangedCopy = useCallback(async () => {
    if (
      !selectedSource ||
      loadedSourceId !== selectedSource.id ||
      loading ||
      savingCopy
    ) {
      return;
    }
    setSavingCopy(true);
    setError(null);
    setNotice(null);
    try {
      const result = unwrapInvokeResult<
        PresentationExportResult | { cancelled: true }
      >(
        await window.presenterCopilot.presentation.saveUnchangedCopy(
          project.id,
          selectedSource.id,
        ),
      );
      if ("cancelled" in result) return;
      if (
        !result.saved ||
        result.file_name.length === 0 ||
        result.byte_size !== selectedSource.byte_size ||
        result.sha256 !== selectedSource.sha256
      ) {
        throw new Error(
          "The saved copy could not be verified against its source.",
        );
      }
      setNotice(
        `Saved unchanged copy: ${result.file_name}. Mock preview edits were not included.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The unchanged presentation copy could not be saved.",
      );
    } finally {
      setSavingCopy(false);
    }
  }, [loadedSourceId, loading, project.id, savingCopy, selectedSource]);

  const closeReader = useCallback(() => {
    const openReader = reader.current;
    reader.current = null;
    if (!openReader) return;
    void requestCore("presentation.workspace.close_source", {
      project_id: openReader.projectId,
      document_id: openReader.documentId,
      session_id: openReader.sessionId,
    }).catch(() => undefined);
  }, []);

  const stopPreviewWorker = useCallback(
    (workerInstance: Worker, message: string) => {
      for (const [id, job] of workerJobs.current) {
        if (job.worker !== workerInstance) continue;
        window.clearTimeout(job.timeoutId);
        workerJobs.current.delete(id);
        job.reject(new Error(message));
      }
      workerInstance.terminate();
      if (worker.current === workerInstance) worker.current = null;
    },
    [],
  );

  const clearWorker = useCallback(() => {
    const activeWorkers = new Set(
      Array.from(workerJobs.current.values(), (job) => job.worker),
    );
    if (worker.current) activeWorkers.add(worker.current);
    for (const activeWorker of activeWorkers) {
      stopPreviewWorker(activeWorker, "Preview was closed.");
    }
  }, [stopPreviewWorker]);

  const clearPreview = useCallback(() => {
    generation.current += 1;
    rewriteGeneration.current += 1;
    closeReader();
    clearWorker();
    rendererMode.current = null;
    void window.presenterCopilot.presentationPreview
      .close()
      .catch(() => undefined);
    setLoadedSourceId(null);
    setSlideCount(0);
    setFidelityReport(null);
    setRevisionHistory(null);
    setCurrentRevision(null);
    setSelectedSlide(1);
    setBlankSlideLayoutSourceId("");
    setSlideSvg(null);
    setSlidePng(null);
    setMockSvg(null);
    setMockPng(null);
    setTextTargets([]);
    setClaimTextTargets([]);
    setDeckClaimCandidate(null);
    setSelectedTargetHandle("");
    setMockText("");
    setRewriteInstruction("");
    setTextRewriteProposal(null);
    setRewriteBusy(false);
    setTextStyleDraft({
      highlight_color: "#FFFF00",
      font_family: "",
      font_size_pt: "",
      font_color: "#000000",
      alignment: "",
      bullet_mode: "",
      bullet_color: "",
      bullet_size_percent: "",
      numbering_start: "",
      left_indent_pt: "",
      first_line_indent_pt: "",
      line_spacing_pt: "",
      space_before_pt: "",
      space_after_pt: "",
    });
    setSpeakerNotesTarget(null);
    setSpeakerNotesDraft("");
    setNewTextBoxDraft("");
    setNewPictureFile(null);
    setNewPictureGeometryBase(null);
    setNewPictureGeometryDraft({ x: "", y: "", width: "", height: "" });
    setNewPictureAltText("");
    setNewShapeGeometryBase(null);
    setNewShapeGeometryDraft({ x: "", y: "", width: "", height: "" });
    setNewShapeType("rect");
    setNewShapeFillColor("#D7E6FF");
    setNewShapeLineColor("#204A87");
    setWorkspaceObjects([]);
    setSelectedObjectId("");
    setDeleteConfirmationObjectId("");
    setObjectInventoryHasMore(false);
    setActiveSlideId("");
    setObjectGeometryDraft({ x: "", y: "", width: "", height: "" });
    setObjectCropDraft(pictureCropDraft(null));
    setObjectAdjustmentDraft(pictureAdjustmentDraft(null));
    setObjectRotationDraft(objectRotationDraft(null));
    setObjectStyleDraft(draftForShapeStyle(null));
    setSlideSizeEmu(null);
    setSlideContext(null);
    setLoadProgress(null);
    setIntentCounts(emptyIntentCounts);
    setError(null);
    setNotice(null);
    setLoading(false);
  }, [clearWorker, closeReader]);

  useEffect(() => {
    if (project.storage_status !== "ready") return;
    if (!decks.some((source) => source.id === selectedSourceId)) {
      setSelectedSourceId(decks[0]?.id ?? "");
    }
  }, [decks, project.storage_status, selectedSourceId]);

  useEffect(() => {
    if (visible) return;
    clearPreview();
  }, [clearPreview, visible]);

  useEffect(
    () => () => {
      generation.current += 1;
      closeReader();
      clearWorker();
      void window.presenterCopilot.presentationPreview
        .close()
        .catch(() => undefined);
    },
    [clearWorker, closeReader],
  );

  const invokeWorker = useCallback(
    (
      workerInstance: Worker,
      message: Record<string, unknown> & { type: string },
      transfers: Transferable[] = [],
    ) =>
      new Promise<WorkerReply>((resolve, reject) => {
        const id = ++nextWorkerJob.current;
        const timeoutId = window.setTimeout(
          () =>
            stopPreviewWorker(
              workerInstance,
              "The presentation preview took too long to respond.",
            ),
          PREVIEW_WORKER_REQUEST_TIMEOUT_MS,
        );
        workerJobs.current.set(id, {
          worker: workerInstance,
          timeoutId,
          resolve,
          reject,
        });
        try {
          workerInstance.postMessage({ ...message, id }, transfers);
        } catch (caught) {
          window.clearTimeout(timeoutId);
          workerJobs.current.delete(id);
          reject(
            caught instanceof Error
              ? caught
              : new Error(
                  "The presentation preview request could not be sent.",
                ),
          );
        }
      }),
    [stopPreviewWorker],
  );

  const loadSlideContext = useCallback(
    async (documentId: string, slideNumber: number, generationId: number) => {
      try {
        const preview = await requestCore<SourcePreviewResult>(
          "source.preview",
          {
            project_id: project.id,
            document_id: documentId,
            offset: slideNumber - 1,
            limit: 1,
          },
        );
        if (generation.current !== generationId) return;
        setSlideContext(
          preview.units.find((unit) => unit.ordinal === slideNumber) ??
            preview.units[0] ??
            null,
        );
      } catch {
        if (generation.current === generationId) setSlideContext(null);
      }
    },
    [project.id],
  );

  const renderSlide = useCallback(
    async (
      slideNumber: number,
      generationId: number,
      revisionId: string,
      preferredObjectId = "",
    ) => {
      const activeWorker = worker.current;
      const activeRendererMode = rendererMode.current;
      const source = selectedSource;
      if (
        !source ||
        !activeRendererMode ||
        (activeRendererMode === "legacy" && !activeWorker) ||
        !UUID_PATTERN.test(revisionId)
      ) {
        return;
      }
      setMockSvg(null);
      setMockPng(null);
      setSpeakerNotesTarget(null);
      setSpeakerNotesDraft("");
      setSlideBackground(null);
      setSlideHidden(null);
      setSlideTransition(undefined);
      setWorkspaceObjects([]);
      setSelectedObjectId("");
      setDeleteConfirmationObjectId("");
      setDeleteConfirmationSlideId("");
      setObjectInventoryHasMore(false);
      setActiveSlideId("");
      setObjectGeometryDraft({ x: "", y: "", width: "", height: "" });
      setNewPictureFile(null);
      setNewPictureGeometryBase(null);
      setNewPictureGeometryDraft({ x: "", y: "", width: "", height: "" });
      setNewPictureAltText("");
      setNewShapeGeometryBase(null);
      setNewShapeGeometryDraft({ x: "", y: "", width: "", height: "" });
      setSlideSizeEmu(null);
      setSlideContext(null);
      setSelectedSlide(slideNumber);
      try {
        const renderRequest = (async () => {
          if (activeRendererMode === "isolated") {
            const result = unwrapInvokeResult<PresentationPreviewRenderResult>(
              await window.presenterCopilot.presentationPreview.render(
                slideNumber,
              ),
            );
            if (
              result.slide_number !== slideNumber ||
              !Number.isSafeInteger(result.width) ||
              result.width < 1 ||
              !Number.isSafeInteger(result.height) ||
              result.height < 1 ||
              result.width > 4096 ||
              result.height > 4096 ||
              !(result.image instanceof Uint8Array) ||
              result.image.byteLength < 8 ||
              result.image.byteLength > MAX_PREVIEW_IMAGE_BYTES ||
              result.image[0] !== 0x89 ||
              result.image[1] !== 0x50 ||
              result.image[2] !== 0x4e ||
              result.image[3] !== 0x47 ||
              result.image[4] !== 0x0d ||
              result.image[5] !== 0x0a ||
              result.image[6] !== 0x1a ||
              result.image[7] !== 0x0a ||
              !Array.isArray(result.text_candidates) ||
              result.text_candidates.length > 100 ||
              result.text_candidates.some(
                (candidate) =>
                  !candidate ||
                  typeof candidate.shape_node_id !== "string" ||
                  candidate.shape_node_id.length < 1 ||
                  candidate.shape_node_id.length > 128 ||
                  typeof candidate.name !== "string" ||
                  candidate.name.length > 200 ||
                  typeof candidate.text !== "string" ||
                  candidate.text.length < 1 ||
                  candidate.text.length > MAX_MOCK_TEXT_CHARS,
              )
            ) {
              throw new Error("The isolated preview could not be verified.");
            }
            const textTargets: RenderTextTarget[] = result.text_candidates.map(
              (candidate) => {
                const excerpt = candidate.text
                  .replace(/\s+/g, " ")
                  .trim()
                  .slice(0, 90);
                return {
                  shapeNodeId: candidate.shape_node_id,
                  label: `${candidate.name || "Text box"}: ${excerpt}`,
                  text: candidate.text,
                };
              },
            );
            return { kind: "isolated" as const, result, textTargets };
          }
          if (!activeWorker) {
            throw new Error("The presentation preview is closed.");
          }
          const result = await invokeWorker(activeWorker, {
            type: "render",
            slideNumber,
          });
          if (
            !result.ok ||
            result.type !== "slide" ||
            typeof result.svg !== "string"
          ) {
            throw new Error(
              result.message ?? "The slide preview is unavailable.",
            );
          }
          return {
            kind: "legacy" as const,
            result: { ...result, svg: result.svg },
            textTargets: result.textTargets ?? [],
          };
        })();
        const [rendered, inventory] = await Promise.all([
          renderRequest,
          requestCore<TextTargetInventory>(
            "presentation.workspace.list_text_targets",
            {
              project_id: project.id,
              document_id: source.id,
              revision_id: revisionId,
              slide_number: slideNumber,
            },
          ),
          loadSlideContext(source.id, slideNumber, generationId),
        ]);
        if (generation.current !== generationId) return;
        if (
          inventory.revision_id !== revisionId ||
          inventory.ordinal !== slideNumber ||
          !UUID_PATTERN.test(inventory.slide_id) ||
          !Number.isSafeInteger(inventory.slide_width_emu) ||
          inventory.slide_width_emu <= 0 ||
          inventory.slide_width_emu > MAX_SLIDE_DIMENSION_EMU ||
          !Number.isSafeInteger(inventory.slide_height_emu) ||
          inventory.slide_height_emu <= 0 ||
          inventory.slide_height_emu > MAX_SLIDE_DIMENSION_EMU ||
          typeof inventory.has_more !== "boolean" ||
          typeof inventory.objects_have_more !== "boolean" ||
          !Array.isArray(inventory.targets) ||
          !Array.isArray(inventory.objects) ||
          inventory.objects.some(
            (object) =>
              !isPresentationObject(object) ||
              (object.geometry_editable &&
                (!object.geometry ||
                  object.geometry.x_emu + object.geometry.width_emu >
                    inventory.slide_width_emu ||
                  object.geometry.y_emu + object.geometry.height_emu >
                    inventory.slide_height_emu)),
          ) ||
          !inventory.speaker_notes ||
          inventory.targets.some(
            (target) =>
              typeof target.single_run_editable !== "boolean" ||
              typeof target.uniform_run_editable !== "boolean" ||
              typeof target.text_format_editable !== "boolean" ||
              (target.single_run_editable &&
                (typeof target.current_text !== "string" ||
                  target.current_text.length > MAX_MOCK_TEXT_CHARS)) ||
              (target.text_format_editable &&
                (typeof target.current_text !== "string" ||
                  target.current_text.length > MAX_MOCK_TEXT_CHARS ||
                  !isTextStyle(target.text_style) ||
                  !target.text_style.editable)),
          ) ||
          (inventory.speaker_notes.current_text !== null &&
            (typeof inventory.speaker_notes.current_text !== "string" ||
              inventory.speaker_notes.current_text.length >
                MAX_SPEAKER_NOTES_CHARS)) ||
          typeof inventory.speaker_notes.text_truncated !== "boolean" ||
          typeof inventory.speaker_notes.editable !== "boolean" ||
          (inventory.speaker_notes.editable &&
            (inventory.speaker_notes.current_text === null ||
              inventory.speaker_notes.text_truncated))
        ) {
          throw new Error("The slide text targets could not be verified.");
        }
        const mappedTargets = rendered.textTargets.flatMap((workerTarget) => {
          const target = inventory.targets.find(
            (candidate) =>
              (candidate.single_run_editable ||
                candidate.uniform_run_editable ||
                candidate.text_format_editable) &&
              candidate.ooxml_shape_id === workerTarget.shapeNodeId &&
              candidate.current_text === workerTarget.text &&
              UUID_PATTERN.test(candidate.object_id),
          );
          if (
            !target ||
            !isTextStyle(target.text_style) ||
            (rendered.kind === "legacy" &&
              (target.single_run_editable || target.uniform_run_editable) &&
              !workerTarget.handle)
          )
            return [];
          const style = target.text_style;
          return [
            {
              key: target.object_id,
              ...(workerTarget.handle ? { handle: workerTarget.handle } : {}),
              label: workerTarget.label,
              text: workerTarget.text,
              slide_id: inventory.slide_id,
              object_id: target.object_id,
              ooxml_shape_id: target.ooxml_shape_id,
              replaceEditable:
                target.single_run_editable || target.uniform_run_editable,
              uniformRunReplacement: target.uniform_run_editable,
              style,
            },
          ];
        });
        if (rendered.kind === "isolated") {
          setSlideSvg(null);
          setSlidePng(rendered.result.image);
        } else {
          setSlidePng(null);
          setSlideSvg(rendered.result.svg);
        }
        setTextTargets(mappedTargets);
        setClaimTextTargets(
          (inventory.semantic_targets ?? inventory.targets).flatMap(
            (target, index) =>
              typeof target.decision_text === "string" &&
              UUID_PATTERN.test(target.object_id)
                ? [
                    {
                      object_id: target.object_id,
                      text: target.decision_text,
                      source_kind:
                        "source_kind" in target
                          ? target.source_kind
                          : "native_text",
                      label:
                        inventory.objects.find(
                          (object) => object.object_id === target.object_id,
                        )?.name || `Text object ${index + 1}`,
                    },
                  ]
                : [],
          ),
        );

        setWorkspaceObjects(inventory.objects);
        setObjectInventoryHasMore(inventory.objects_have_more);
        setActiveSlideId(inventory.slide_id);
        setSlideSizeEmu({
          width: inventory.slide_width_emu,
          height: inventory.slide_height_emu,
        });
        const defaultShapeGeometry = centeredShapeGeometry(
          inventory.slide_width_emu,
          inventory.slide_height_emu,
        );
        setNewShapeGeometryBase(defaultShapeGeometry);
        setNewShapeGeometryDraft(geometryDraft(defaultShapeGeometry));
        const preferredEditableObject = inventory.objects.find(
          (object) =>
            object.object_id === preferredObjectId &&
            object.geometry_editable &&
            object.geometry,
        );
        const firstEditableObject =
          preferredEditableObject ??
          inventory.objects.find(
            (object) => object.geometry_editable && object.geometry,
          );
        setSelectedObjectId(firstEditableObject?.object_id ?? "");
        setObjectGeometryDraft(
          firstEditableObject?.geometry
            ? geometryDraft(firstEditableObject.geometry)
            : { x: "", y: "", width: "", height: "" },
        );
        setObjectCropDraft(
          pictureCropDraft(firstEditableObject?.picture_crop ?? null),
        );
        setObjectAdjustmentDraft(
          pictureAdjustmentDraft(firstEditableObject?.picture_adjustment),
        );
        setObjectRotationDraft(
          objectRotationDraft(firstEditableObject?.rotation),
        );
        setObjectStyleDraft(
          draftForShapeStyle(firstEditableObject?.shape_style ?? null),
        );
        const notesTarget: SpeakerNotesTarget = {
          slide_id: inventory.slide_id,
          ...inventory.speaker_notes,
        };
        setSpeakerNotesTarget(notesTarget);
        setSpeakerNotesDraft(notesTarget.current_text ?? "");
        const background = isSlideBackground(inventory.background)
          ? inventory.background
          : null;
        setSlideBackground(background);
        setSlideHidden(
          typeof inventory.hidden === "boolean" ? inventory.hidden : null,
        );
        setSlideTransition(
          inventory.transition === null ||
            (typeof inventory.transition === "string" &&
              SLIDE_TRANSITIONS.some(
                ([value]) => value === inventory.transition,
              ))
            ? inventory.transition
            : undefined,
        );
        setSlideBackgroundDraft(background?.color ?? "#FFFFFF");
        const firstTarget =
          mappedTargets.find(
            (target) => target.object_id === preferredObjectId,
          ) ?? mappedTargets[0];
        setSelectedTargetHandle(firstTarget?.key ?? "");
        setMockText(firstTarget?.text.slice(0, MAX_MOCK_TEXT_CHARS) ?? "");
        setTextStyleDraft({
          highlight_color: firstTarget?.style.highlight_color ?? "#FFFF00",
          font_family: firstTarget?.style.font_family ?? "",
          font_size_pt: firstTarget?.style.font_size_pt?.toString() ?? "",
          font_color: firstTarget?.style.font_color ?? "#000000",
          alignment: firstTarget?.style.alignment ?? "",
          bullet_mode: firstTarget?.style.bullet_state ?? "",
          bullet_color: firstTarget?.style.bullet_color ?? "",
          bullet_size_percent:
            firstTarget?.style.bullet_size_percent?.toString() ?? "",
          numbering_start: firstTarget?.style.numbering_start?.toString() ?? "",
          left_indent_pt: firstTarget?.style.left_indent_pt?.toString() ?? "",
          first_line_indent_pt:
            firstTarget?.style.first_line_indent_pt?.toString() ?? "",
          line_spacing_pt: firstTarget?.style.line_spacing_pt?.toString() ?? "",
          space_before_pt: firstTarget?.style.space_before_pt?.toString() ?? "",
          space_after_pt: firstTarget?.style.space_after_pt?.toString() ?? "",
        });
      } catch (caught) {
        if (generation.current === generationId) {
          setError(
            caught instanceof Error || isCoreError(caught)
              ? caught.message
              : "The slide preview is unavailable.",
          );
        }
      }
    },
    [invokeWorker, loadSlideContext, project.id, selectedSource],
  );

  const loadPresentation = useCallback(
    async (initialSlideNumber = 1, preferredObjectId = "") => {
      if (!Number.isSafeInteger(initialSlideNumber) || initialSlideNumber < 1) {
        setError("The requested slide number is invalid.");
        return;
      }
      if (!selectedSource || project.storage_status !== "ready" || loading)
        return;
      clearPreview();
      setSelectedSlide(initialSlideNumber);
      const generationId = generation.current;
      setLoading(true);
      setError(null);
      setNotice(null);
      let sessionId: string | null = null;
      try {
        const opened = await requestCore<ReaderOpenResult>(
          "presentation.workspace.open_source",
          { project_id: project.id, document_id: selectedSource.id },
        );
        if (
          !opened.session_id ||
          !UUID_PATTERN.test(opened.revision_id) ||
          (opened.revision_kind !== "original" &&
            opened.revision_kind !== "edited") ||
          !Number.isSafeInteger(opened.revision_number) ||
          opened.revision_number < 1 ||
          !/^[0-9a-f]{64}$/.test(opened.sha256) ||
          !Number.isSafeInteger(opened.byte_size) ||
          opened.byte_size < 1 ||
          opened.byte_size > MAX_PREVIEW_BYTES ||
          !Number.isSafeInteger(opened.chunk_bytes) ||
          opened.chunk_bytes < 1 ||
          opened.chunk_bytes > DEFAULT_READ_BYTES ||
          opened.fidelity_report?.status !== "inventory_only" ||
          !Number.isSafeInteger(opened.fidelity_report.slide_count) ||
          opened.fidelity_report.slide_count < 1 ||
          initialSlideNumber > opened.fidelity_report.slide_count ||
          !Array.isArray(opened.fidelity_report.slides) ||
          opened.fidelity_report.slides.length !==
            opened.fidelity_report.slide_count ||
          opened.fidelity_report.slides.some(
            (slide, index) =>
              !slide ||
              !UUID_PATTERN.test(slide.slide_id) ||
              slide.ordinal !== index + 1 ||
              !Number.isSafeInteger(slide.object_count) ||
              slide.object_count < 0,
          ) ||
          new Set(opened.fidelity_report.slides.map((slide) => slide.slide_id))
            .size !== opened.fidelity_report.slide_count ||
          !Number.isSafeInteger(opened.fidelity_report.object_count) ||
          opened.fidelity_report.object_count < 0 ||
          !hasValidObjectKindCounts(
            opened.fidelity_report.object_kinds,
            opened.fidelity_report.object_count,
          ) ||
          !Number.isSafeInteger(opened.fidelity_report.text_edit_candidates) ||
          opened.fidelity_report.text_edit_candidates < 0 ||
          !Number.isSafeInteger(
            opened.fidelity_report.nontext_or_unmodeled_objects,
          ) ||
          opened.fidelity_report.nontext_or_unmodeled_objects < 0
        ) {
          throw new Error(
            "The presentation size or reader response is invalid.",
          );
        }
        const history = await requestCore<RevisionHistoryResult>(
          "presentation.workspace.list_revisions",
          { project_id: project.id, document_id: selectedSource.id, limit: 50 },
        );
        if (
          history.presentation_id !== selectedSource.id ||
          typeof history.current_revision_id !== "string" ||
          typeof history.has_more !== "boolean" ||
          !Array.isArray(history.revisions) ||
          (history.has_more &&
            (!Number.isSafeInteger(history.next_before_revision_number) ||
              (history.next_before_revision_number ?? 0) < 2)) ||
          (!history.has_more && history.next_before_revision_number !== null)
        ) {
          throw new Error(
            "Presentation revision history could not be verified.",
          );
        }
        if (
          history.current_revision_id !== opened.revision_id ||
          history.revisions.filter((revision) => revision.is_current).length >
            1 ||
          history.revisions.some(
            (revision) =>
              !revision ||
              typeof revision !== "object" ||
              !UUID_PATTERN.test(revision.revision_id) ||
              !Number.isSafeInteger(revision.revision_number) ||
              revision.revision_number < 1 ||
              (revision.revision_kind !== "original" &&
                revision.revision_kind !== "edited") ||
              !/^[0-9a-f]{64}$/.test(revision.sha256) ||
              !Number.isSafeInteger(revision.byte_size) ||
              revision.byte_size < 1 ||
              typeof revision.created_at !== "string" ||
              typeof revision.is_current !== "boolean" ||
              (revision.parent_revision_id !== null &&
                !UUID_PATTERN.test(revision.parent_revision_id)),
          )
        ) {
          throw new Error(
            "Presentation revision history could not be verified.",
          );
        }
        setRevisionHistory(history);
        setCurrentRevision({
          revision_id: opened.revision_id,
          revision_kind: opened.revision_kind,
          revision_number: opened.revision_number,
          sha256: opened.sha256,
          byte_size: opened.byte_size,
        });
        sessionId = opened.session_id;
        setFidelityReport(opened.fidelity_report);
        reader.current = {
          projectId: project.id,
          documentId: selectedSource.id,
          sessionId,
        };
        let bytes = new Uint8Array(opened.byte_size);
        let offset = 0;
        while (offset < opened.byte_size) {
          if (generation.current !== generationId) return;
          const chunk = await requestCore<ReaderChunkResult>(
            "presentation.workspace.read_source",
            {
              project_id: project.id,
              document_id: selectedSource.id,
              session_id: sessionId,
              offset,
              max_bytes: Math.min(opened.chunk_bytes, DEFAULT_READ_BYTES),
            },
          );
          const part = toBytes(chunk.bytes_b64);
          if (
            chunk.offset !== offset ||
            offset + part.byteLength > bytes.byteLength ||
            part.byteLength === 0 ||
            chunk.complete !== (offset + part.byteLength === bytes.byteLength)
          ) {
            throw new Error("The presentation snapshot could not be verified.");
          }
          bytes.set(part, offset);
          offset += part.byteLength;
          setLoadProgress(`${Math.round((offset / opened.byte_size) * 100)}%`);
          if (chunk.complete !== (offset === opened.byte_size)) {
            throw new Error("The presentation snapshot could not be verified.");
          }
        }
        reader.current = null;
        if (generation.current !== generationId) return;

        let previewSlideCount = opened.fidelity_report.slide_count;
        try {
          const isolatedResult = unwrapInvokeResult(
            await window.presenterCopilot.presentationPreview.open(
              bytes.buffer,
            ),
          );
          if (
            isolatedResult.slide_count !== opened.fidelity_report.slide_count ||
            !Number.isFinite(isolatedResult.slide_width) ||
            !Number.isFinite(isolatedResult.slide_height) ||
            !Array.isArray(isolatedResult.font_substitutions) ||
            !Array.isArray(isolatedResult.unresolved_font_families) ||
            typeof isolatedResult.font_check_limited !== "boolean"
          ) {
            throw new Error(
              "The isolated preview dimensions could not be verified.",
            );
          }
          rendererMode.current = "isolated";
          // The isolated preview has parsed its own IPC copy. Later operations
          // read from Core again, so clear this temporary full-deck buffer.
          if (bytes.byteLength > 0) bytes.fill(0);
          bytes = new Uint8Array(0);
          const fontNotes: string[] = [];
          const describeFontList = (items: string[]) => {
            const visible = items.slice(0, 6).join(", ");
            const remaining = items.length - 6;
            return remaining > 0
              ? `${visible}, and ${remaining} more`
              : visible;
          };
          if (isolatedResult.font_substitutions.length > 0) {
            fontNotes.push(
              `Local preview font substitutions: ${describeFontList(isolatedResult.font_substitutions)}. Text wrapping or weight may differ from PowerPoint.`,
            );
          }
          if (isolatedResult.unresolved_font_families.length > 0) {
            fontNotes.push(
              `Fonts unavailable for local substitution: ${describeFontList(isolatedResult.unresolved_font_families)}.`,
            );
          }
          if (isolatedResult.font_check_limited) {
            fontNotes.push("The preview font scan reached its safety limit.");
          }
          if (fontNotes.length > 0) setNotice(fontNotes.join(" "));
        } catch {
          await window.presenterCopilot.presentationPreview
            .close()
            .catch(() => undefined);
          const previewWorker = new Worker(
            new URL("./presentation-preview.worker.ts", import.meta.url),
            { type: "module", name: "presentation-preview" },
          );
          previewWorker.onmessage = (event: MessageEvent<WorkerReply>) => {
            const job = workerJobs.current.get(event.data.id);
            if (!job) return;
            window.clearTimeout(job.timeoutId);
            workerJobs.current.delete(event.data.id);
            job.resolve(event.data);
          };
          previewWorker.onerror = () => {
            stopPreviewWorker(
              previewWorker,
              "The presentation preview worker stopped.",
            );
          };
          previewWorker.onmessageerror = () => {
            stopPreviewWorker(
              previewWorker,
              "The presentation preview worker returned an invalid response.",
            );
          };
          worker.current = previewWorker;
          const openedReply = await invokeWorker(
            previewWorker,
            { type: "open", buffer: bytes.buffer },
            [bytes.buffer],
          );
          if (
            generation.current !== generationId ||
            !openedReply.ok ||
            openedReply.type !== "opened" ||
            !Number.isSafeInteger(openedReply.slideCount) ||
            openedReply.slideCount !== opened.fidelity_report.slide_count
          ) {
            throw new Error(
              openedReply.message ?? "The presentation could not be opened.",
            );
          }
          previewSlideCount = openedReply.slideCount;
          rendererMode.current = "legacy";
          setNotice(
            "The higher-fidelity preview was unavailable. Showing the compatibility preview.",
          );
        }
        if (generation.current !== generationId) return;
        setSlideCount(previewSlideCount);
        setLoadedSourceId(selectedSource.id);
        setLoadProgress(null);
        await renderSlide(
          initialSlideNumber,
          generationId,
          opened.revision_id,
          preferredObjectId,
        );
      } catch (caught) {
        if (generation.current === generationId) {
          setError(
            caught instanceof Error
              ? caught.message
              : "The presentation could not be opened in the preview.",
          );
        }
      } finally {
        if (sessionId && reader.current?.sessionId === sessionId) closeReader();
        if (generation.current === generationId) {
          setLoading(false);
          setLoadProgress(null);
        }
      }
    },
    [
      clearPreview,
      closeReader,
      invokeWorker,
      loading,
      project.id,
      project.storage_status,
      renderSlide,
      selectedSource,
      stopPreviewWorker,
    ],
  );

  const changeSource = (sourceId: string) => {
    clearPreview();
    setSelectedSourceId(sourceId);
    setError(null);
    setNotice(null);
  };

  const recordIntent = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!intentText.trim()) return;
    setIntentCounts((current) => ({
      ...current,
      [intentKind]: current[intentKind] + 1,
    }));
    setIntentText("");
    setNotice(
      "Intent counted for this open view. The text was discarded and nothing was sent or saved.",
    );
  };

  const proposeTextRewrite = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const target = selectedTarget;
    if (
      !source ||
      !revision ||
      !target?.replaceEditable ||
      !UUID_PATTERN.test(activeSlideId) ||
      !rewriteInstruction.trim() ||
      rewriteInstruction.length > MAX_REWRITE_INSTRUCTION_CHARS ||
      loadedSourceId !== source.id ||
      loading ||
      rewriteBusy
    ) {
      return;
    }
    const attempt = ++rewriteGeneration.current;
    setRewriteBusy(true);
    setLoading(true);
    setError(null);
    setNotice(null);
    setTextRewriteProposal(null);
    setMockSvg(null);
    try {
      const result = await requestCore<TextRewriteProposal>(
        "presentation.workspace.propose_text_rewrite",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_number: selectedSlide,
          object_id: target.object_id,
          instruction: rewriteInstruction.trim(),
          ...(pendingRehearsalEdit?.kind === "text"
            ? { rehearsal_finding_id: pendingRehearsalEdit.finding.finding_id }
            : {}),
        },
      );
      const providerAllowed = new Set([
        "openai",
        "local_openai",
        "codex_chatgpt",
        "fake-test",
      ]);
      if (
        attempt !== rewriteGeneration.current ||
        !result ||
        !UUID_PATTERN.test(result.provider_run_id) ||
        result.document_id !== source.id ||
        result.revision_id !== revision.revision_id ||
        result.slide_id !== target.slide_id ||
        result.slide_number !== selectedSlide ||
        result.object_id !== target.object_id ||
        result.current_text !== target.text ||
        typeof result.replacement_text !== "string" ||
        !result.replacement_text.trim() ||
        result.replacement_text.length > MAX_MOCK_TEXT_CHARS ||
        result.replacement_text.includes("\n") ||
        result.replacement_text.includes("\r") ||
        typeof result.edit_summary !== "string" ||
        !result.edit_summary.trim() ||
        result.edit_summary.length > 300 ||
        result.edit_summary.includes("\n") ||
        result.edit_summary.includes("\r") ||
        typeof result.provider_id !== "string" ||
        !providerAllowed.has(result.provider_id) ||
        typeof result.model_id !== "string" ||
        result.model_id.length > 120 ||
        !Number.isSafeInteger(result.latency_ms) ||
        result.latency_ms < 0 ||
        result.requires_user_review !== true
      ) {
        if (attempt === rewriteGeneration.current) {
          throw new Error("The rewrite proposal could not be verified.");
        }
        return;
      }
      setTextRewriteProposal(result);
      setNotice("Rewrite suggestion ready. Review it before using it.");
    } catch (caught) {
      if (attempt === rewriteGeneration.current) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The rewrite suggestion could not be completed.",
        );
      }
    } finally {
      if (attempt === rewriteGeneration.current) {
        setRewriteBusy(false);
        setLoading(false);
      }
    }
  }, [
    pendingRehearsalEdit,
    activeSlideId,
    currentRevision,
    loadedSourceId,
    loading,
    project.id,
    rewriteBusy,
    rewriteInstruction,
    selectedSlide,
    selectedSource,
    selectedTarget,
  ]);

  const previewMockText = async () => {
    const activeWorker = worker.current;
    const activeRendererMode = rendererMode.current;
    const target = selectedTarget;
    const generationId = generation.current;
    if (
      !activeRendererMode ||
      (activeRendererMode === "legacy" && !activeWorker) ||
      !target?.replaceEditable ||
      mockText.length > MAX_MOCK_TEXT_CHARS
    )
      return;
    setLoading(true);
    setError(null);
    setMockSvg(null);
    try {
      const replacementText = mockText.slice(0, MAX_MOCK_TEXT_CHARS);
      if (activeRendererMode === "isolated") {
        const result = unwrapInvokeResult<PresentationPreviewRenderResult>(
          await window.presenterCopilot.presentationPreview.render(
            selectedSlide,
            {
              shapeNodeId: target.ooxml_shape_id,
              text: replacementText,
            },
          ),
        );
        if (
          generation.current !== generationId ||
          result.slide_number !== selectedSlide ||
          !(result.image instanceof Uint8Array) ||
          result.image.byteLength < 8 ||
          result.image.byteLength > MAX_PREVIEW_IMAGE_BYTES ||
          result.image[0] !== 0x89 ||
          result.image[1] !== 0x50 ||
          result.image[2] !== 0x4e ||
          result.image[3] !== 0x47 ||
          result.image[4] !== 0x0d ||
          result.image[5] !== 0x0a ||
          result.image[6] !== 0x1a ||
          result.image[7] !== 0x0a ||
          (result.mock_text_overflows_shape !== null &&
            typeof result.mock_text_overflows_shape !== "boolean")
        ) {
          throw new Error("The mock preview could not be verified.");
        }
        setMockPng(result.image);
        setMockTextLayoutStatus(
          result.mock_text_overflows_shape === true
            ? "overflow"
            : result.mock_text_overflows_shape === false
              ? "fits"
              : "unknown",
        );
      } else {
        if (!activeWorker || !target.handle) {
          throw new Error("The selected text preview target is unavailable.");
        }
        const reply = await invokeWorker(activeWorker, {
          type: "mock-text",
          slideNumber: selectedSlide,
          handle: target.handle,
          text: replacementText,
        });
        if (generation.current !== generationId) return;
        if (
          !reply.ok ||
          reply.type !== "mock-text" ||
          typeof reply.svg !== "string"
        ) {
          throw new Error(
            reply.message ?? "The mock change could not be rendered.",
          );
        }
        setMockSvg(reply.svg);
        setMockTextLayoutStatus("unknown");
      }
      setNotice(
        "Mock preview only. The imported PPTX was not changed or saved.",
      );
    } catch (caught) {
      if (generation.current === generationId) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The mock change could not be rendered.",
        );
      }
    } finally {
      if (generation.current === generationId) setLoading(false);
    }
  };

  const moveSlide = useCallback(
    async (currentIndex: number, nextIndex: number) => {
      const source = selectedSource;
      const revision = currentRevision;
      const slides = fidelityReport?.slides;
      if (
        currentIndex === nextIndex ||
        !source ||
        !revision ||
        loadedSourceId !== source.id ||
        loading ||
        !slides ||
        slides.length !== slideCount ||
        currentIndex < 0 ||
        currentIndex >= slides.length ||
        nextIndex < 0 ||
        nextIndex >= slides.length
      ) {
        return;
      }
      const reorderedSlides = [...slides];
      const [movedSlide] = reorderedSlides.splice(currentIndex, 1);
      if (!movedSlide) return;
      reorderedSlides.splice(nextIndex, 0, movedSlide);
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.reorder_slides",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            ordered_slide_ids: reorderedSlides.map((slide) => slide.slide_id),
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number) ||
          result.revision_number < 1 ||
          !/^[0-9a-f]{64}$/.test(result.sha256) ||
          !Number.isSafeInteger(result.byte_size) ||
          result.byte_size < 1 ||
          (result.changed && result.parent_revision_id !== revision.revision_id)
        ) {
          throw new Error("The slide-order revision could not be verified.");
        }
        if (!result.changed) {
          setNotice("The presentation already has that slide order.");
          return;
        }
        let indexedRevision = false;
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
          indexedRevision = true;
        } catch {
          // Re-indexing can be retried. Session-bound historical units remain intact.
        }
        await loadPresentation(nextIndex + 1);
        setNotice(
          indexedRevision
            ? `Moved the slide to position ${nextIndex + 1} and refreshed slide retrieval.`
            : `Moved the slide to position ${nextIndex + 1}. Re-index this presentation before using it in rehearsal.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The slide could not be moved.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      currentRevision,
      fidelityReport,
      loadPresentation,
      loadedSourceId,
      loading,
      project.id,
      selectedSource,
      slideCount,
    ],
  );
  const reorderSelectedSlide = useCallback(
    (direction: -1 | 1) =>
      moveSlide(selectedSlide - 1, selectedSlide - 1 + direction),
    [moveSlide, selectedSlide],
  );
  // Slide strip drag-and-drop: the dragged slide index and the hovered drop target.
  const [draggedSlide, setDraggedSlide] = useState<number | null>(null);
  const [slideDropTarget, setSlideDropTarget] = useState<number | null>(null);

  const applySlideLayoutRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const layoutSourceSlideId = blankSlideLayoutSourceId;
    const layoutSourceSlide = fidelityReport?.slides.find(
      (slide) => slide.slide_id === layoutSourceSlideId,
    );
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      !layoutSourceSlideId ||
      !UUID_PATTERN.test(layoutSourceSlideId) ||
      !layoutSourceSlide ||
      layoutSourceSlideId === activeSlideId ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<
        TextEditResult & { layout_source_slide_id: string }
      >("presentation.workspace.apply_slide_layout", {
        project_id: project.id,
        document_id: source.id,
        expected_revision_id: revision.revision_id,
        slide_id: activeSlideId,
        layout_source_slide_id: layoutSourceSlideId,
      });
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        (result.changed &&
          result.parent_revision_id !== revision.revision_id) ||
        result.layout_source_slide_id !== layoutSourceSlideId
      ) {
        throw new Error("The slide-layout revision could not be verified.");
      }
      if (!result.changed) {
        setNotice("The current slide already uses that layout.");
        return;
      }
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // The immutable revision remains current and can be re-indexed later.
      }
      await loadPresentation(selectedSlide);
      setNotice(
        indexedRevision
          ? "Applied the layout from slide " +
              layoutSourceSlide.ordinal +
              " to slide " +
              selectedSlide +
              " and refreshed slide retrieval. Review the preview; revision history can restore the previous layout."
          : "Applied the layout from slide " +
              layoutSourceSlide.ordinal +
              " to slide " +
              selectedSlide +
              ". Re-index before using it in rehearsal; revision history can restore the previous layout.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The slide layout could not be applied.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    blankSlideLayoutSourceId,
    currentRevision,
    fidelityReport,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedSlide,
    selectedSource,
  ]);

  const createBlankSlideRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const layoutSourceSlideId = blankSlideLayoutSourceId || activeSlideId;
    const layoutSourceSlide = fidelityReport?.slides.find(
      (slide) => slide.slide_id === layoutSourceSlideId,
    );
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      !UUID_PATTERN.test(layoutSourceSlideId) ||
      !layoutSourceSlide ||
      slideCount >= MAX_WORKSPACE_SLIDES ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<
        TextEditResult & { layout_source_slide_id: string }
      >("presentation.workspace.create_slide", {
        project_id: project.id,
        document_id: source.id,
        expected_revision_id: revision.revision_id,
        slide_id: activeSlideId,
        layout_source_slide_id: layoutSourceSlideId,
      });
      const createdSlideId = result.created_slide_id;
      if (
        !result.changed ||
        !UUID_PATTERN.test(result.revision_id) ||
        typeof createdSlideId !== "string" ||
        !UUID_PATTERN.test(createdSlideId) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        result.parent_revision_id !== revision.revision_id ||
        result.layout_source_slide_id !== layoutSourceSlideId
      ) {
        throw new Error("The blank-slide revision could not be verified.");
      }
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // The immutable revision remains current and can be re-indexed later.
      }
      await loadPresentation(selectedSlide + 1);
      setNotice(
        indexedRevision
          ? "Added a blank slide after slide " +
              selectedSlide +
              " using the layout from slide " +
              layoutSourceSlide.ordinal +
              " and refreshed slide retrieval."
          : "Added a blank slide after slide " +
              selectedSlide +
              " using the layout from slide " +
              layoutSourceSlide.ordinal +
              ". Re-index before using it in rehearsal.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The blank slide could not be created.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    blankSlideLayoutSourceId,
    currentRevision,
    fidelityReport,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedSlide,
    selectedSource,
    slideCount,
  ]);

  const duplicateSelectedSlideRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.duplicate_slide",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
        },
      );
      const createdSlideId = result.created_slide_id;
      if (
        !result.changed ||
        !UUID_PATTERN.test(result.revision_id) ||
        typeof createdSlideId !== "string" ||
        !UUID_PATTERN.test(createdSlideId) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        result.parent_revision_id !== revision.revision_id
      ) {
        throw new Error(
          "The slide-duplication revision could not be verified.",
        );
      }
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // The immutable revision remains current and can be re-indexed later.
      }
      await loadPresentation(selectedSlide + 1);
      setNotice(
        indexedRevision
          ? `Duplicated slide ${selectedSlide} and refreshed slide retrieval.`
          : `Duplicated slide ${selectedSlide}. Re-index before using it in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The slide could not be duplicated.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedSlide,
    selectedSource,
  ]);

  const deleteSelectedSlideRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const targetSlideId = activeSlideId;
    if (
      !source ||
      !revision ||
      slideCount <= 1 ||
      deleteConfirmationSlideId !== targetSlideId ||
      !UUID_PATTERN.test(targetSlideId) ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.delete_slide",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: targetSlideId,
        },
      );
      if (
        !result.changed ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        result.parent_revision_id !== revision.revision_id
      ) {
        throw new Error("The slide-deletion revision could not be verified.");
      }
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // The immutable revision remains current and can be re-indexed later.
      }
      const nextSlideNumber = Math.min(selectedSlide, slideCount - 1);
      await loadPresentation(nextSlideNumber);
      setNotice(
        indexedRevision
          ? `Deleted slide ${selectedSlide} and refreshed slide retrieval.`
          : `Deleted slide ${selectedSlide}. Re-index before using this presentation in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The slide could not be deleted.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    deleteConfirmationSlideId,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedSlide,
    selectedSource,
    slideCount,
  ]);

  async function changeObjectLayer(
    direction: "forward" | "backward" | "front" | "back",
  ) {
    if (
      !selectedSource ||
      !currentRevision ||
      !selectedObject ||
      !activeSlideId ||
      loading ||
      loadedSourceId !== selectedSource.id
    )
      return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.change_object_layer",
        {
          project_id: project.id,
          document_id: selectedSource.id,
          expected_revision_id: currentRevision.revision_id,
          slide_id: activeSlideId,
          object_id: selectedObject.object_id,
          expected_object_ids: workspaceObjects.map(
            (object) => object.object_id,
          ),
          direction,
        },
      );
      if (
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        !/^[0-9a-f]{64}$/.test(result.sha256)
      )
        throw new Error("The layer revision could not be verified.");
      if (!result.changed) {
        setNotice("The object is already at this layer boundary.");
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexed = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: selectedSource.id,
        });
        indexed = true;
      } catch {
        /* The saved revision remains available. */
      }
      await loadPresentation(selectedSlide, selectedObject.object_id);
      setNotice(
        `Saved object layer in revision ${result.revision_number}.${indexed ? "" : " Re-index before rehearsal."}`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The object layer could not be changed.",
      );
    } finally {
      setLoading(false);
    }
  }

  const saveCurrentCopy = useCallback(
    async (openAfterSave = false) => {
      const source = selectedSource;
      const revision = currentRevision;
      if (
        !source ||
        !revision ||
        loadedSourceId !== source.id ||
        loading ||
        savingCopy
      ) {
        return;
      }
      setSavingCopy(true);
      setError(null);
      setNotice(null);
      try {
        const result = unwrapInvokeResult<
          PresentationExportResult | { cancelled: true }
        >(
          await window.presenterCopilot.presentation.saveCurrentCopy(
            project.id,
            source.id,
            openAfterSave,
          ),
        );
        if ("cancelled" in result) return;
        if (
          !result.saved ||
          result.copy_kind !== "current_revision" ||
          !result.file_name ||
          result.byte_size !== revision.byte_size ||
          result.sha256 !== revision.sha256
        ) {
          throw new Error(
            "The saved copy could not be verified against this revision.",
          );
        }
        if (openAfterSave && typeof result.opened !== "boolean") {
          throw new Error(
            "The presentation app handoff could not be verified.",
          );
        }
        setNotice(
          openAfterSave
            ? result.opened
              ? `Saved and opened current revision: ${result.file_name}.`
              : `Saved current revision: ${result.file_name}. The default presentation app could not be opened.`
            : `Saved current revision: ${result.file_name}.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The current presentation copy could not be saved.",
        );
      } finally {
        setSavingCopy(false);
      }
    },
    [
      currentRevision,
      loadedSourceId,
      loading,
      project.id,
      savingCopy,
      selectedSource,
    ],
  );

  const saveTextRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const target = selectedTarget;
    if (
      !source ||
      !revision ||
      !target ||
      !target.replaceEditable ||
      !canSaveMockTextRevision(
        hasMockPreview,
        mockTextLayoutStatus,
        layoutRiskAcknowledged,
      ) ||
      loadedSourceId !== source.id ||
      loading ||
      mockText.length > MAX_MOCK_TEXT_CHARS
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<TextEditResult>(
        pendingRehearsalEdit?.kind === "text"
          ? "presentation.workspace.apply_rehearsal_edit"
          : "presentation.workspace.replace_text_shape",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          ...(pendingRehearsalEdit?.kind === "text"
            ? {
                finding_id: pendingRehearsalEdit.finding.finding_id,
                edit_kind: "text",
              }
            : { operation_type: "replace_text_shape" }),
          slide_id: target.slide_id,
          object_id: target.object_id,
          expected_text: target.text,
          replacement_text: mockText,
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        (result.changed && result.parent_revision_id !== revision.revision_id)
      ) {
        throw new Error("The saved revision response could not be verified.");
      }
      if (!result.changed) {
        setNotice(
          "No text change was needed; the current revision is unchanged.",
        );
        setMockSvg(null);
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // The revision remains saved. Core's revision filter keeps its
        // unindexed text out of retrieval until a later re-index succeeds.
      }
      await loadPresentation();
      setNotice(
        indexedRevision
          ? `Saved revision ${result.revision_number} and refreshed its slide text for retrieval.`
          : `Saved revision ${result.revision_number}. Re-index this presentation before using its edited text in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The text change could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    pendingRehearsalEdit,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    hasMockPreview,
    layoutRiskAcknowledged,
    mockText,
    mockTextLayoutStatus,
    project.id,
    selectedSource,
    selectedTarget,
  ]);

  const saveTextStyleRevision = useCallback(
    async (replacementStyle: TextStyleChange) => {
      const source = selectedSource;
      const revision = currentRevision;
      const target = selectedTarget;
      if (
        !source ||
        !revision ||
        !target?.style.editable ||
        !target.style.fingerprint ||
        loadedSourceId !== source.id ||
        loading ||
        !Object.keys(replacementStyle).length
      ) {
        return;
      }
      setLoading(true);
      setError(null);
      setNotice(null);
      setMockSvg(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.format_text_shape",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            slide_id: target.slide_id,
            object_id: target.object_id,
            expected_text: target.text,
            expected_style_fingerprint: target.style.fingerprint,
            replacement_style: replacementStyle,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number) ||
          result.revision_number < 1 ||
          !/^[0-9a-f]{64}$/.test(result.sha256) ||
          !Number.isSafeInteger(result.byte_size) ||
          result.byte_size < 1 ||
          (result.changed && result.parent_revision_id !== revision.revision_id)
        ) {
          throw new Error("The formatting revision could not be verified.");
        }
        if (!result.changed) {
          setNotice("The selected formatting is already applied.");
          return;
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        let indexedRevision = false;
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
          indexedRevision = true;
        } catch {
          // The immutable revision remains current and can be re-indexed later.
        }
        await loadPresentation(selectedSlide, target.object_id);
        setNotice(
          indexedRevision
            ? `Saved formatting revision ${result.revision_number}.`
            : `Saved formatting revision ${result.revision_number}. Re-index before using it in rehearsal.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The text formatting could not be saved.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      currentRevision,
      loadPresentation,
      loadedSourceId,
      loading,
      project.id,
      selectedSource,
      selectedSlide,
      selectedTarget,
    ],
  );

  const createTextBoxRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const text = newTextBoxDraft;
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      !text.trim() ||
      text.length > MAX_MOCK_TEXT_CHARS ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    setMockSvg(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.create_text_box",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          text,
        },
      );
      const createdObjectId = result.created_object_id;
      if (
        !result.changed ||
        !UUID_PATTERN.test(result.revision_id) ||
        typeof createdObjectId !== "string" ||
        !UUID_PATTERN.test(createdObjectId) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        result.parent_revision_id !== revision.revision_id
      ) {
        throw new Error("The new text-box revision could not be verified.");
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // The immutable revision remains current and can be re-indexed later.
      }
      setNewTextBoxDraft("");
      await loadPresentation(selectedSlide, createdObjectId);
      setNotice(
        indexedRevision
          ? `Added a text box in revision ${result.revision_number}.`
          : `Added a text box in revision ${result.revision_number}. Re-index before using it in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The text box could not be created.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    newTextBoxDraft,
    project.id,
    selectedSlide,
    selectedSource,
  ]);

  const createPictureRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const file = newPictureFile;
    const geometry = newPictureGeometry;
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      !geometry ||
      !file ||
      file.size < 1 ||
      file.size > MAX_REPLACEMENT_IMAGE_BYTES ||
      !["image/png", "image/jpeg"].includes(file.type) ||
      loadedSourceId !== source.id ||
      loading ||
      pictureAssetBusy
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    setMockSvg(null);
    try {
      const imageBase64 = await readImageAsBase64(file);
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.create_picture",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          geometry,
          alt_text: newPictureAltText,
          image_base64: imageBase64,
        },
      );
      const createdObjectId = result.created_object_id;
      if (
        !result.changed ||
        !UUID_PATTERN.test(result.revision_id) ||
        typeof createdObjectId !== "string" ||
        !UUID_PATTERN.test(createdObjectId) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        result.parent_revision_id !== revision.revision_id
      ) {
        throw new Error("The new picture revision could not be verified.");
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // The immutable revision remains current and can be re-indexed later.
      }
      setNewPictureFile(null);
      setNewPictureGeometryBase(null);
      setNewPictureGeometryDraft({ x: "", y: "", width: "", height: "" });
      setNewPictureAltText("");
      if (newPictureInput.current) newPictureInput.current.value = "";
      await loadPresentation(selectedSlide, createdObjectId);
      setNotice(
        indexedRevision
          ? `Added a picture in revision ${result.revision_number}.`
          : `Added a picture in revision ${result.revision_number}. Re-index before using it in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The picture could not be created.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    pictureAssetBusy,
    newPictureAltText,
    newPictureFile,
    newPictureGeometry,
    project.id,
    selectedSlide,
    selectedSource,
  ]);

  const createShapeRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const geometry = newShapeGeometry;
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      !geometry ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    setMockSvg(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.create_shape",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          shape_type: newShapeType,
          geometry,
          fill_color: newShapeFillColor,
          line_color: newShapeLineColor,
        },
      );
      const createdObjectId = result.created_object_id;
      if (
        !result.changed ||
        !UUID_PATTERN.test(result.revision_id) ||
        typeof createdObjectId !== "string" ||
        !UUID_PATTERN.test(createdObjectId) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        result.parent_revision_id !== revision.revision_id
      ) {
        throw new Error("The new shape revision could not be verified.");
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // The immutable revision remains current and can be re-indexed later.
      }
      await loadPresentation(selectedSlide, createdObjectId);
      const shapeLabel = newShapeType === "rect" ? "rectangle" : "ellipse";
      setNotice(
        indexedRevision
          ? "Added a " +
              shapeLabel +
              " in revision " +
              result.revision_number +
              "."
          : "Added a " +
              shapeLabel +
              " in revision " +
              result.revision_number +
              ". Re-index before using it in rehearsal.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The shape could not be created.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    newShapeFillColor,
    newShapeGeometry,
    newShapeLineColor,
    newShapeType,
    project.id,
    selectedSlide,
    selectedSource,
  ]);

  const saveSpeakerNotesRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const target = speakerNotesTarget;
    if (
      !source ||
      !revision ||
      !target ||
      !target.editable ||
      target.current_text === null ||
      target.text_truncated ||
      loadedSourceId !== source.id ||
      loading ||
      speakerNotesDraft.length > MAX_SPEAKER_NOTES_CHARS
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    setMockSvg(null);
    try {
      const result = await requestCore<TextEditResult>(
        pendingRehearsalEdit?.kind === "notes"
          ? "presentation.workspace.apply_rehearsal_edit"
          : "presentation.workspace.replace_speaker_notes",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          ...(pendingRehearsalEdit?.kind === "notes"
            ? {
                finding_id: pendingRehearsalEdit.finding.finding_id,
                edit_kind: "notes",
              }
            : {}),
          slide_id: target.slide_id,
          expected_text: target.current_text,
          replacement_text: speakerNotesDraft,
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        (result.changed && result.parent_revision_id !== revision.revision_id)
      ) {
        throw new Error(
          "The saved speaker-notes revision could not be verified.",
        );
      }
      if (!result.changed) {
        setNotice(
          "No speaker-notes change was needed; the current revision is unchanged.",
        );
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation();
      setNotice(
        indexedRevision
          ? `Saved revision ${result.revision_number} and refreshed its speaker notes for retrieval.`
          : `Saved revision ${result.revision_number}. Re-index this presentation before using its edited notes in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The speaker-notes change could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    pendingRehearsalEdit,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedSource,
    speakerNotesDraft,
    speakerNotesTarget,
  ]);

  const savePictureCropRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const target = selectedObject;
    const replacement = replacementPictureCrop;
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      !target?.geometry_editable ||
      !target.geometry ||
      !target.picture_crop ||
      !replacement ||
      samePictureCrop(target.picture_crop, replacement) ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    setMockSvg(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.crop_picture",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          object_id: target.object_id,
          expected_geometry: target.geometry,
          expected_crop: target.picture_crop,
          replacement_crop: replacement,
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        (result.changed && result.parent_revision_id !== revision.revision_id)
      ) {
        throw new Error("The picture crop revision could not be verified.");
      }
      if (!result.changed) {
        setNotice("The picture crop is unchanged.");
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation(selectedSlide, target.object_id);
      setNotice(
        indexedRevision
          ? `Saved revision ${result.revision_number} and refreshed the picture crop.`
          : `Saved revision ${result.revision_number}. Re-index this presentation before using its content in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The picture crop could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    replacementPictureCrop,
    selectedObject,
    selectedSlide,
    selectedSource,
  ]);

  const selectedTextObject = workspaceObjects.find(
    (object) => object.object_id === selectedTarget?.object_id,
  );
  const selectedTextLink = selectedTextObject?.hyperlink ?? null;
  const linkValue =
    linkDraft.objectId === selectedTarget?.object_id
      ? linkDraft.value
      : (selectedTextLink?.url ?? "");

  const saveTextHyperlinkRevision = useCallback(
    async (url: string | null, linkedSlideId: string | null = null) => {
      const source = selectedSource;
      const revision = currentRevision;
      const target = selectedTarget;
      const current = selectedTextLink;
      if (
        !source ||
        !revision ||
        !UUID_PATTERN.test(activeSlideId) ||
        !target ||
        !current ||
        (url !== null && !validHyperlinkUrl(url)) ||
        (url !== null && linkedSlideId !== null) ||
        (url === current.url && linkedSlideId === (current.slide_id ?? null)) ||
        loadedSourceId !== source.id ||
        loading
      ) {
        return;
      }
      setLoading(true);
      setError(null);
      setNotice(null);
      setMockSvg(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.set_text_hyperlink",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            slide_id: activeSlideId,
            object_id: target.object_id,
            expected_text: target.text,
            expected_url: current.url,
            expected_slide_id: current.slide_id ?? null,
            replacement_url: url,
            replacement_slide_id: linkedSlideId,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number) ||
          result.revision_number < 1 ||
          !/^[0-9a-f]{64}$/.test(result.sha256) ||
          !Number.isSafeInteger(result.byte_size) ||
          result.byte_size < 1 ||
          (result.changed && result.parent_revision_id !== revision.revision_id)
        ) {
          throw new Error("The text link revision could not be verified.");
        }
        if (!result.changed) {
          setNotice("The text link is unchanged.");
          return;
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        let indexedRevision = false;
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
          indexedRevision = true;
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        setLinkDraft({ objectId: "", value: "" });
        await loadPresentation(selectedSlide, target.object_id);
        setNotice(
          indexedRevision
            ? `Saved revision ${result.revision_number} and refreshed the text link.`
            : `Saved revision ${result.revision_number}. Re-index this presentation before using its content in rehearsal.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The text link could not be saved.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      activeSlideId,
      currentRevision,
      loadPresentation,
      loadedSourceId,
      loading,
      project.id,
      selectedSlide,
      selectedSource,
      selectedTarget,
      selectedTextLink,
    ],
  );

  useEffect(() => {
    const source = selectedSource;
    const revision = currentRevision;
    if (!source || !revision || loadedSourceId !== source.id) {
      setFooterState(null);
      return;
    }
    let cancelled = false;
    void requestCore<unknown>("presentation.workspace.get_slide_footers", {
      project_id: project.id,
      document_id: source.id,
      expected_revision_id: revision.revision_id,
    })
      .then((state) => {
        if (cancelled || !isSlideFooterState(state)) return;
        setFooterState(state);
        setFooterDraft((current) => ({
          ...current,
          numbers: state.slide_numbers !== "none",
          text: state.footer_text ?? "",
        }));
      })
      .catch(() => {
        if (!cancelled) setFooterState(null);
      });
    return () => {
      cancelled = true;
    };
  }, [currentRevision, loadedSourceId, project.id, selectedSource]);

  useEffect(() => {
    const source = selectedSource;
    const revision = currentRevision;
    if (!source || !revision || loadedSourceId !== source.id) {
      setThemeFonts(null);
      return;
    }
    let cancelled = false;
    void requestCore<{
      heading_font: string | null;
      body_font: string | null;
      editable: boolean;
    }>("presentation.workspace.get_theme_fonts", {
      project_id: project.id,
      document_id: source.id,
      expected_revision_id: revision.revision_id,
    })
      .then((state) => {
        if (cancelled || typeof state?.editable !== "boolean") return;
        setThemeFonts(state);
        setThemeFontDraft({
          heading: state.heading_font ?? "",
          body: state.body_font ?? "",
        });
      })
      .catch(() => {
        if (!cancelled) setThemeFonts(null);
      });
    return () => {
      cancelled = true;
    };
  }, [currentRevision, loadedSourceId, project.id, selectedSource]);

  useEffect(() => {
    const source = selectedSource;
    const revision = currentRevision;
    if (!source || !revision || loadedSourceId !== source.id) {
      setThemeColors(null);
      return;
    }
    let cancelled = false;
    void requestCore<unknown>("presentation.workspace.get_theme_colors", {
      project_id: project.id,
      document_id: source.id,
      expected_revision_id: revision.revision_id,
    })
      .then((state) => {
        if (cancelled || !isThemeColorState(state)) return;
        setThemeColors(state);
        setThemeColorDraft(state.colors ?? {});
      })
      .catch(() => {
        if (!cancelled) setThemeColors(null);
      });
    return () => {
      cancelled = true;
    };
  }, [currentRevision, loadedSourceId, project.id, selectedSource]);

  useEffect(() => {
    const source = selectedSource;
    const revision = currentRevision;
    if (!source || !revision || loadedSourceId !== source.id) {
      setSlideSections(null);
      return;
    }
    let cancelled = false;
    void requestCore<unknown>("presentation.workspace.get_slide_sections", {
      project_id: project.id,
      document_id: source.id,
      expected_revision_id: revision.revision_id,
    })
      .then((state) => {
        if (!cancelled)
          setSlideSections(isSlideSectionState(state) ? state : null);
      })
      .catch(() => {
        if (!cancelled) setSlideSections(null);
      });
    return () => {
      cancelled = true;
    };
  }, [currentRevision, loadedSourceId, project.id, selectedSource]);

  // Section names shown above the slide that starts each section.
  const sectionStarts = useMemo(() => {
    const starts = new Map<number, string>();
    if (
      !slideSections ||
      slideSections.revision_id !== currentRevision?.revision_id
    )
      return starts;
    for (const section of slideSections.sections) {
      const first = section.slide_ids[0];
      const index = first ? slideSections.slide_ids.indexOf(first) : -1;
      if (index >= 0) starts.set(index + 1, section.name || "Untitled section");
    }
    return starts;
  }, [currentRevision?.revision_id, slideSections]);

  const clearCopilotPrefill = useCallback(() => setCopilotPrefill(null), []);

  const checkAccessibility = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    if (!source || !revision || loadedSourceId !== source.id || loading) return;
    setError(null);
    try {
      const result = await requestCore<unknown>(
        "presentation.workspace.check_accessibility",
        {
          project_id: project.id,
          document_id: source.id,
          revision_id: revision.revision_id,
        },
      );
      if (!isAccessibilityResult(result))
        throw new Error(
          "The accessibility check returned an unexpected result.",
        );
      setAccessibility(result);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The accessibility check could not run.",
      );
    }
  }, [currentRevision, loadedSourceId, loading, project.id, selectedSource]);

  const addSlideTitle = useCallback(
    async (issue: AccessibilityIssue, title: string) => {
      const source = selectedSource;
      const revision = currentRevision;
      if (
        !source ||
        !revision ||
        loadedSourceId !== source.id ||
        loading ||
        !title
      )
        return;
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.set_slide_title",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            slide_id: issue.slide_id,
            title,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number)
        ) {
          throw new Error("The slide title revision could not be verified.");
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation(issue.slide_number);
        const refreshed = await requestCore<unknown>(
          "presentation.workspace.check_accessibility",
          {
            project_id: project.id,
            document_id: source.id,
            revision_id: result.revision_id,
          },
        );
        if (isAccessibilityResult(refreshed)) setAccessibility(refreshed);
        setNotice(
          `Saved revision ${result.revision_number} with a title on slide ${issue.slide_number}.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The slide title could not be added.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      currentRevision,
      loadPresentation,
      loadedSourceId,
      loading,
      project.id,
      selectedSource,
    ],
  );

  const goToAccessibilityIssue = useCallback(
    (issue: AccessibilityIssue) => {
      if (issue.object_id) setInspectorPanel("objects");
      void loadPresentation(issue.slide_number, issue.object_id ?? undefined);
    },
    [loadPresentation],
  );

  const saveClickAction = useCallback(
    async (action: ClickAction) => {
      const source = selectedSource;
      const revision = currentRevision;
      const object = selectedObject;
      if (
        !source ||
        !revision ||
        !object?.click_action ||
        !UUID_PATTERN.test(activeSlideId) ||
        loadedSourceId !== source.id ||
        loading
      )
        return;
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.set_click_action",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            slide_id: activeSlideId,
            object_id: object.object_id,
            expected_click_action: object.click_action,
            click_action: action,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number)
        ) {
          throw new Error("The click action revision could not be verified.");
        }
        if (!result.changed) {
          setNotice("The click action is unchanged.");
          return;
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation(selectedSlide, object.object_id);
        setNotice(
          `Saved revision ${result.revision_number} with the click action for ${object.name}.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The click action could not be saved.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      activeSlideId,
      currentRevision,
      loadPresentation,
      loadedSourceId,
      loading,
      project.id,
      selectedObject,
      selectedSlide,
      selectedSource,
    ],
  );

  const saveAltText = useCallback(
    async (text: string, decorative: boolean) => {
      const source = selectedSource;
      const revision = currentRevision;
      const object = selectedObject;
      if (
        !source ||
        !revision ||
        !object ||
        typeof object.alt_text !== "string" ||
        !UUID_PATTERN.test(activeSlideId) ||
        loadedSourceId !== source.id ||
        loading
      )
        return;
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.set_alt_text",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            slide_id: activeSlideId,
            object_id: object.object_id,
            expected_alt_text: object.alt_text,
            expected_decorative: object.decorative === true,
            alt_text: text,
            decorative,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number)
        ) {
          throw new Error("The alt text revision could not be verified.");
        }
        if (!result.changed) {
          setNotice("The alt text is unchanged.");
          return;
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation(selectedSlide, object.object_id);
        setNotice(
          `Saved revision ${result.revision_number} with the ${decorative ? "decorative flag" : "alt text"} for ${object.name}.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The alt text could not be saved.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      activeSlideId,
      currentRevision,
      loadPresentation,
      loadedSourceId,
      loading,
      project.id,
      selectedObject,
      selectedSlide,
      selectedSource,
    ],
  );

  const saveSlideSections = useCallback(
    async (sections: SlideSectionDraft[]) => {
      const source = selectedSource;
      const revision = currentRevision;
      const state = slideSections;
      if (
        !source ||
        !revision ||
        !state?.editable ||
        state.revision_id !== revision.revision_id ||
        loadedSourceId !== source.id ||
        loading
      )
        return;
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.set_slide_sections",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            expected_fingerprint: state.fingerprint,
            sections: sections.map((section) => ({
              section_id: section.section_id,
              name: section.name.trim(),
              first_slide_id: section.first_slide_id,
            })),
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number)
        ) {
          throw new Error("The slide section revision could not be verified.");
        }
        if (!result.changed) {
          setNotice("The slide sections are unchanged.");
          return;
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation(selectedSlide, selectedObjectId || undefined);
        setNotice(
          sections.length
            ? `Saved revision ${result.revision_number} with ${sections.length} section${sections.length === 1 ? "" : "s"}.`
            : `Saved revision ${result.revision_number} without sections.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The slide sections could not be saved.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      currentRevision,
      loadPresentation,
      loadedSourceId,
      loading,
      project.id,
      selectedObjectId,
      selectedSlide,
      selectedSource,
      slideSections,
    ],
  );

  const saveThemeColors = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const state = themeColors;
    if (!source || !revision || !state?.editable || !state.colors || loading)
      return;
    const before = state.colors;
    const colors = Object.fromEntries(
      Object.entries(themeColorDraft)
        .map(([slot, value]): [string, string] => [slot, value.toUpperCase()])
        .filter(([slot, value]) => before[slot] !== value),
    );
    if (Object.keys(colors).length === 0) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.set_theme_colors",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          expected_colors: before,
          colors,
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id)
      ) {
        throw new Error("The theme color revision could not be verified.");
      }
      if (!result.changed) {
        setNotice("The theme colors are unchanged.");
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation(selectedSlide, selectedObjectId || undefined);
      setNotice(
        `Saved revision ${result.revision_number} with the new theme colors.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The theme colors could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    currentRevision,
    loadPresentation,
    loading,
    project.id,
    selectedObjectId,
    selectedSlide,
    selectedSource,
    themeColorDraft,
    themeColors,
  ]);

  const saveThemeFonts = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const state = themeFonts;
    if (!source || !revision || !state?.editable || loading) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.set_theme_fonts",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          expected_heading_font: state.heading_font,
          expected_body_font: state.body_font,
          heading_font: themeFontDraft.heading.trim(),
          body_font: themeFontDraft.body.trim(),
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id)
      ) {
        throw new Error("The theme font revision could not be verified.");
      }
      if (!result.changed) {
        setNotice("The theme fonts are unchanged.");
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation(selectedSlide, selectedObjectId || undefined);
      setNotice(
        `Saved revision ${result.revision_number} with the new theme fonts.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The theme fonts could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    currentRevision,
    loadPresentation,
    loading,
    project.id,
    selectedObjectId,
    selectedSlide,
    selectedSource,
    themeFontDraft,
    themeFonts,
  ]);

  const insertMedia = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    if (
      !source ||
      !revision ||
      loading ||
      !UUID_PATTERN.test(activeSlideId) ||
      loadedSourceId !== source.id
    )
      return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = unwrapInvokeResult(
        await window.presenterCopilot.presentation.pickAndInsertMedia(
          project.id,
          source.id,
          revision.revision_id,
          activeSlideId,
        ),
      );
      if ("cancelled" in result) return;
      if (
        !UUID_PATTERN.test(result.revision_id) ||
        !UUID_PATTERN.test(result.created_object_id)
      ) {
        throw new Error("The inserted media could not be verified.");
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      await loadPresentation(selectedSlide, result.created_object_id);
      const seconds = Math.round(result.duration_seconds);
      setNotice(
        `Saved revision ${result.revision_number} with ${result.media_kind === "video" ? "a video" : "an audio clip"} (${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}). It plays in PowerPoint's slide show.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The media could not be inserted.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedSlide,
    selectedSource,
  ]);

  const reuseSlide = useCallback(
    async (reuse: ReuseRequest) => {
      const source = selectedSource;
      const revision = currentRevision;
      if (!source || !revision || loading) return;
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<
          TextEditResult & {
            created_slide_id: string;
            layout_name: string;
            notes_copied: boolean;
          }
        >("presentation.workspace.reuse_slide", {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          source_document_id: reuse.source_document_id,
          source_revision_id: reuse.source_revision_id,
          source_slide_id: reuse.source_slide_id,
          position: reuse.position,
        });
        if (
          !UUID_PATTERN.test(result.revision_id) ||
          !UUID_PATTERN.test(result.created_slide_id)
        ) {
          throw new Error("The reused slide could not be verified.");
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation(reuse.position);
        setNotice(
          `Saved revision ${result.revision_number}: reused ${reuse.label} as slide ${reuse.position} with the ${result.layout_name} layout${result.notes_copied ? " and its speaker notes" : ""}.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The slide could not be reused.",
        );
      } finally {
        setLoading(false);
      }
    },
    [currentRevision, loadPresentation, loading, project.id, selectedSource],
  );

  const replaceDeckFont = useCallback(
    async (font: DeckFont, replacement: string) => {
      const source = selectedSource;
      const revision = currentRevision;
      if (!source || !revision || loading) return;
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.replace_fonts",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            font: font.name,
            expected_uses: font.uses,
            replacement_font: replacement,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id)
        ) {
          throw new Error("The font replacement could not be verified.");
        }
        if (!result.changed) {
          setNotice("The fonts are unchanged.");
          return;
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation(selectedSlide, selectedObjectId || undefined);
        setNotice(
          `Saved revision ${result.revision_number}: replaced ${font.name} with ${replacement} in ${font.uses} place${font.uses === 1 ? "" : "s"}.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The font could not be replaced.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      currentRevision,
      loadPresentation,
      loading,
      project.id,
      selectedObjectId,
      selectedSlide,
      selectedSource,
    ],
  );

  const saveSlideFooters = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const state = footerState;
    if (
      !source ||
      !revision ||
      !state ||
      loadedSourceId !== source.id ||
      loading
    )
      return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<
        TextEditResult & { slides_changed?: number }
      >("presentation.workspace.set_slide_footers", {
        project_id: project.id,
        document_id: source.id,
        expected_revision_id: revision.revision_id,
        expected_fingerprint: state.fingerprint,
        slide_numbers: footerDraft.numbers,
        footer_text: footerDraft.text.trim() ? footerDraft.text.trim() : null,
        skip_title_slides: footerDraft.skipTitle,
      });
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number)
      ) {
        throw new Error("The slide footer revision could not be verified.");
      }
      if (!result.changed) {
        setNotice("Slide numbers and footers are unchanged.");
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation(selectedSlide, selectedObjectId || undefined);
      setNotice(
        `Saved revision ${result.revision_number}: updated slide numbers and footers on ${result.slides_changed ?? 0} slides.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Slide numbers and footers could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    currentRevision,
    footerDraft,
    footerState,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedObjectId,
    selectedSlide,
    selectedSource,
  ]);

  useEffect(() => {
    const source = selectedSource;
    const revision = currentRevision;
    if (
      !source ||
      !revision ||
      loadedSourceId !== source.id ||
      !UUID_PATTERN.test(activeSlideId)
    ) {
      setSlideAnimations(null);
      return;
    }
    let cancelled = false;
    void requestCore<unknown>("presentation.workspace.get_slide_animations", {
      project_id: project.id,
      document_id: source.id,
      expected_revision_id: revision.revision_id,
      slide_id: activeSlideId,
    })
      .then((state) => {
        if (!cancelled)
          setSlideAnimations(isSlideAnimationState(state) ? state : null);
      })
      .catch(() => {
        if (!cancelled) setSlideAnimations(null);
      });
    return () => {
      cancelled = true;
    };
  }, [
    activeSlideId,
    currentRevision,
    loadedSourceId,
    project.id,
    selectedSource,
  ]);

  const saveSlideAnimations = useCallback(
    async (effects: SlideAnimationEffect[]) => {
      const source = selectedSource;
      const revision = currentRevision;
      const state = slideAnimations;
      if (
        !source ||
        !revision ||
        !state?.editable ||
        state.slide_id !== activeSlideId ||
        loadedSourceId !== source.id ||
        loading
      )
        return;
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.set_slide_animations",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            slide_id: activeSlideId,
            expected_fingerprint: state.fingerprint,
            effects: effects.map(({ object_id, effect, start }) => ({
              object_id,
              effect,
              start,
            })),
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number)
        ) {
          throw new Error(
            "The slide animation revision could not be verified.",
          );
        }
        if (!result.changed) {
          setNotice("The slide animations are unchanged.");
          return;
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation(selectedSlide, selectedObjectId || undefined);
        setNotice(
          `Saved revision ${result.revision_number} with ${effects.length} entrance animation${effects.length === 1 ? "" : "s"}.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The slide animations could not be saved.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      activeSlideId,
      currentRevision,
      loadPresentation,
      loadedSourceId,
      loading,
      project.id,
      selectedObjectId,
      selectedSlide,
      selectedSource,
      slideAnimations,
    ],
  );

  const saveSlideTransitionRevision = useCallback(
    async (transition: string) => {
      const source = selectedSource;
      const revision = currentRevision;
      const current = slideTransition;
      if (
        !source ||
        !revision ||
        typeof current !== "string" ||
        current === transition ||
        !UUID_PATTERN.test(activeSlideId) ||
        loadedSourceId !== source.id ||
        loading
      ) {
        return;
      }
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.set_slide_transition",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            slide_id: activeSlideId,
            expected_transition: current,
            transition,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number) ||
          result.revision_number < 1 ||
          !/^[0-9a-f]{64}$/.test(result.sha256) ||
          !Number.isSafeInteger(result.byte_size) ||
          result.byte_size < 1 ||
          (result.changed && result.parent_revision_id !== revision.revision_id)
        ) {
          throw new Error(
            "The slide transition revision could not be verified.",
          );
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation(selectedSlide, selectedObjectId || undefined);
        setNotice(
          `Saved revision ${result.revision_number} and refreshed the slide transition.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The slide transition could not be saved.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      activeSlideId,
      currentRevision,
      loadPresentation,
      loadedSourceId,
      loading,
      project.id,
      selectedObjectId,
      selectedSlide,
      selectedSource,
      slideTransition,
    ],
  );

  const saveSlideHiddenRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const hidden = slideHidden;
    if (
      !source ||
      !revision ||
      hidden === null ||
      !UUID_PATTERN.test(activeSlideId) ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.set_slide_hidden",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          expected_hidden: hidden,
          hidden: !hidden,
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        (result.changed && result.parent_revision_id !== revision.revision_id)
      ) {
        throw new Error("The slide visibility revision could not be verified.");
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation(selectedSlide, selectedObjectId || undefined);
      setNotice(
        hidden
          ? `Saved revision ${result.revision_number}. Slide ${selectedSlide} shows in the slide show again.`
          : `Saved revision ${result.revision_number}. Slide ${selectedSlide} is hidden from the slide show.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The slide visibility could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedObjectId,
    selectedSlide,
    selectedSource,
    slideHidden,
  ]);

  const saveSlideBackgroundRevision = useCallback(
    async (color: string | null) => {
      const source = selectedSource;
      const revision = currentRevision;
      const background = slideBackground;
      if (
        !source ||
        !revision ||
        !UUID_PATTERN.test(activeSlideId) ||
        !background?.editable ||
        background.state === "unsupported" ||
        loadedSourceId !== source.id ||
        loading
      ) {
        return;
      }
      setLoading(true);
      setError(null);
      setNotice(null);
      setMockSvg(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.set_slide_background",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            slide_id: activeSlideId,
            expected_background: {
              state: background.state,
              color: background.color,
            },
            replacement_color: color,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number) ||
          result.revision_number < 1 ||
          !/^[0-9a-f]{64}$/.test(result.sha256) ||
          !Number.isSafeInteger(result.byte_size) ||
          result.byte_size < 1 ||
          (result.changed && result.parent_revision_id !== revision.revision_id)
        ) {
          throw new Error(
            "The slide background revision could not be verified.",
          );
        }
        if (!result.changed) {
          setNotice("The slide background is unchanged.");
          return;
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        let indexedRevision = false;
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
          indexedRevision = true;
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation(selectedSlide, selectedObjectId || undefined);
        setNotice(
          indexedRevision
            ? `Saved revision ${result.revision_number} and refreshed the slide background.`
            : `Saved revision ${result.revision_number}. Re-index this presentation before using its content in rehearsal.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The slide background could not be saved.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      activeSlideId,
      currentRevision,
      loadPresentation,
      loadedSourceId,
      loading,
      project.id,
      selectedObjectId,
      selectedSlide,
      selectedSource,
      slideBackground,
    ],
  );

  const saveObjectRotationRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const target = selectedObject;
    const replacement = replacementObjectRotation;
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      !target?.geometry_editable ||
      !target.geometry ||
      !target.rotation ||
      !replacement ||
      sameObjectRotation(target.rotation, replacement) ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    setMockSvg(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.rotate_object",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          object_id: target.object_id,
          expected_geometry: target.geometry,
          expected_rotation: target.rotation,
          replacement_rotation: replacement,
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        (result.changed && result.parent_revision_id !== revision.revision_id)
      ) {
        throw new Error("The rotation revision could not be verified.");
      }
      if (!result.changed) {
        setNotice("The object rotation is unchanged.");
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation(selectedSlide, target.object_id);
      setNotice(
        indexedRevision
          ? `Saved revision ${result.revision_number} and refreshed the object rotation.`
          : `Saved revision ${result.revision_number}. Re-index this presentation before using its content in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The object rotation could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    replacementObjectRotation,
    selectedObject,
    selectedSlide,
    selectedSource,
  ]);

  const savePictureAdjustmentRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const target = selectedObject;
    const replacement = replacementPictureAdjustment;
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      target?.kind !== "pic" ||
      !target.geometry ||
      !target.picture_adjustment ||
      !replacement ||
      samePictureAdjustment(target.picture_adjustment, replacement) ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    setMockSvg(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.adjust_picture",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          object_id: target.object_id,
          expected_geometry: target.geometry,
          expected_adjustment: target.picture_adjustment,
          replacement_adjustment: replacement,
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        (result.changed && result.parent_revision_id !== revision.revision_id)
      ) {
        throw new Error(
          "The picture adjustment revision could not be verified.",
        );
      }
      if (!result.changed) {
        setNotice("The picture adjustments are unchanged.");
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation(selectedSlide, target.object_id);
      setNotice(
        indexedRevision
          ? `Saved revision ${result.revision_number} and refreshed the picture adjustments.`
          : `Saved revision ${result.revision_number}. Re-index this presentation before using its content in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The picture adjustments could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    replacementPictureAdjustment,
    selectedObject,
    selectedSlide,
    selectedSource,
  ]);

  const renderPictureAdjustment = (selectedObject: PresentationObject) =>
    selectedObject.picture_adjustment ? (
      <fieldset className="pw-picture-crop">
        <legend>Picture adjustments</legend>
        <p className="muted">
          Brightness and contrast use PowerPoint&apos;s percentages from -100 to
          100.
        </p>
        <div className="pw-geometry-fields">
          {(
            [
              ["brightness_percent", "Brightness (%)"],
              ["contrast_percent", "Contrast (%)"],
            ] as const
          ).map(([field, label]) => (
            <label key={field}>
              {label}
              <input
                type="number"
                min="-100"
                max="100"
                step="1"
                aria-label={`Picture ${label}`}
                value={objectAdjustmentDraft[field]}
                onChange={(event) =>
                  setObjectAdjustmentDraft((current) => ({
                    ...current,
                    [field]: event.target.value,
                  }))
                }
                disabled={!loadedSourceId || loading}
              />
            </label>
          ))}
        </div>
        <label className="checkbox-row">
          <input
            type="checkbox"
            aria-label="Picture grayscale"
            checked={objectAdjustmentDraft.grayscale}
            onChange={(event) =>
              setObjectAdjustmentDraft((current) => ({
                ...current,
                grayscale: event.target.checked,
              }))
            }
            disabled={!loadedSourceId || loading}
          />
          Grayscale
        </label>
        {replacementPictureAdjustment === null ? (
          <p className="muted" role="alert">
            Use whole percentages from -100 to 100.
          </p>
        ) : null}
        <button
          type="button"
          className="secondary-button"
          onClick={() => void savePictureAdjustmentRevision()}
          disabled={
            !loadedSourceId ||
            loading ||
            !replacementPictureAdjustment ||
            samePictureAdjustment(
              selectedObject.picture_adjustment,
              replacementPictureAdjustment,
            )
          }
        >
          Apply picture adjustments
        </button>
      </fieldset>
    ) : (
      <p className="muted">
        This picture uses image effects that stay read-only.
      </p>
    );

  const replacePictureImageRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const target = selectedObject;
    const file = replacementPictureFile;
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      !target?.geometry_editable ||
      !target.geometry ||
      !target.picture_crop ||
      !file ||
      file.size < 1 ||
      file.size > MAX_REPLACEMENT_IMAGE_BYTES ||
      !["image/png", "image/jpeg"].includes(file.type) ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    setMockSvg(null);
    try {
      const imageBase64 = await readImageAsBase64(file);
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.replace_picture_image",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          object_id: target.object_id,
          expected_geometry: target.geometry,
          expected_crop: target.picture_crop,
          image_base64: imageBase64,
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        (result.changed && result.parent_revision_id !== revision.revision_id)
      ) {
        throw new Error(
          "The replacement image revision could not be verified.",
        );
      }
      if (!result.changed) {
        setNotice("The picture image is unchanged.");
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation(selectedSlide, target.object_id);
      setNotice(
        indexedRevision
          ? `Saved revision ${result.revision_number} and replaced the picture image.`
          : `Saved revision ${result.revision_number}. Re-index this presentation before using its content in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The picture image could not be replaced.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    replacementPictureFile,
    selectedObject,
    selectedSlide,
    selectedSource,
  ]);

  const saveObjectGeometryRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const target = selectedObject;
    const replacement = replacementObjectGeometry;
    if (
      !source ||
      !revision ||
      !UUID_PATTERN.test(activeSlideId) ||
      !target?.geometry_editable ||
      !target.geometry ||
      !replacement ||
      sameGeometry(target.geometry, replacement) ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    if (target.kind === "graphicFrame") {
      setPendingCanvasMove({
        resize: true,
        operations: [
          {
            type: "transform_object",
            params: {
              slide_id: activeSlideId,
              object_id: target.object_id,
              expected_geometry: target.geometry,
              replacement_geometry: replacement,
            },
          },
        ],
      });
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    setMockSvg(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.transform_object",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          object_id: target.object_id,
          expected_geometry: target.geometry,
          replacement_geometry: replacement,
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        (result.changed && result.parent_revision_id !== revision.revision_id)
      ) {
        throw new Error("The saved layout revision could not be verified.");
      }
      if (!result.changed) {
        setNotice("The object position and size are unchanged.");
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation(selectedSlide, target.object_id);
      setNotice(
        indexedRevision
          ? `Saved revision ${result.revision_number} and refreshed the slide layout.`
          : `Saved revision ${result.revision_number}. Re-index this presentation before using its content in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The object position or size could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    replacementObjectGeometry,
    activeSlideId,
    selectedObject,
    selectedSlide,
    selectedSource,
  ]);

  const saveShapeColorRevision = useCallback(
    async (
      property:
        | "fill_color"
        | "line_color"
        | "outline"
        | "transparency"
        | "shadow_on"
        | "shadow_off"
        | `geometry:${string}`,
    ) => {
      const source = selectedSource;
      const revision = currentRevision;
      const target = selectedObject;
      const style = target?.shape_style;
      const editable = property.startsWith("geometry:")
        ? style?.shape_geometry != null
        : property === "shadow_on" || property === "shadow_off"
          ? style?.shadow_editable
          : property === "fill_color" || property === "transparency"
            ? style?.fill_editable
            : property === "line_color"
              ? style?.line_editable
              : style?.line_format_editable;
      const replacement: Record<string, string | number | boolean> = {};
      if (property.startsWith("geometry:")) {
        const geometry = property.slice("geometry:".length);
        if (style?.shape_geometry !== geometry)
          replacement.shape_geometry = geometry;
      } else if (property === "shadow_on" || property === "shadow_off") {
        const enabled = property === "shadow_on";
        if (style?.shadow !== enabled) replacement.shadow = enabled;
      } else if (property === "transparency") {
        const percent = Number(objectStyleDraft.fill_transparency_percent);
        if (
          Number.isInteger(percent) &&
          percent >= 0 &&
          percent <= 100 &&
          percent !== style?.fill_transparency_percent
        )
          replacement.fill_transparency_percent = percent;
      } else if (property === "outline") {
        const width = Number(objectStyleDraft.line_width_pt);
        if (
          objectStyleDraft.line_width_pt !== "" &&
          Number.isFinite(width) &&
          width !== style?.line_width_pt
        )
          replacement.line_width_pt = width;
        if (
          objectStyleDraft.line_dash !== "" &&
          objectStyleDraft.line_dash !== (style?.line_dash ?? "")
        )
          replacement.line_dash = objectStyleDraft.line_dash;
      } else if (
        (property === "fill_color" || property === "line_color") &&
        /^#[0-9A-F]{6}$/.test(objectStyleDraft[property])
      ) {
        replacement[property] = objectStyleDraft[property];
      }
      if (
        !source ||
        !revision ||
        !UUID_PATTERN.test(activeSlideId) ||
        !target ||
        !style?.editable ||
        !style.fingerprint ||
        !editable ||
        loadedSourceId !== source.id ||
        loading
      ) {
        return;
      }
      if (
        Object.keys(replacement).length === 0 ||
        ((property === "fill_color" || property === "line_color") &&
          style[property] === replacement[property])
      ) {
        setNotice("The selected shape style is unchanged.");
        return;
      }
      setLoading(true);
      setError(null);
      setNotice(null);
      setMockSvg(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.format_shape_style",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: revision.revision_id,
            slide_id: activeSlideId,
            object_id: target.object_id,
            expected_style_fingerprint: style.fingerprint,
            replacement_style: replacement,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number) ||
          result.revision_number < 1 ||
          !/^[0-9a-f]{64}$/.test(result.sha256) ||
          !Number.isSafeInteger(result.byte_size) ||
          result.byte_size < 1 ||
          (result.changed && result.parent_revision_id !== revision.revision_id)
        ) {
          throw new Error("The shape style revision could not be verified.");
        }
        if (!result.changed) {
          setNotice("The selected shape style is unchanged.");
          return;
        }
        setCurrentRevision({
          revision_id: result.revision_id,
          revision_kind: "edited",
          revision_number: result.revision_number,
          sha256: result.sha256,
          byte_size: result.byte_size,
        });
        let indexedRevision = false;
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
          indexedRevision = true;
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation(selectedSlide, target.object_id);
        setNotice(
          indexedRevision
            ? `Saved revision ${result.revision_number} and refreshed the shape style.`
            : `Saved revision ${result.revision_number}. Re-index before using this presentation in rehearsal.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The shape color could not be saved.",
        );
      } finally {
        setLoading(false);
      }
    },
    [
      activeSlideId,
      currentRevision,
      loadPresentation,
      loadedSourceId,
      loading,
      objectStyleDraft,
      project.id,
      selectedObject,
      selectedSlide,
      selectedSource,
    ],
  );

  const deleteSelectedObjectRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const target = selectedObject;
    if (
      !source ||
      !revision ||
      !target?.delete_editable ||
      !target.geometry ||
      !UUID_PATTERN.test(activeSlideId) ||
      loadedSourceId !== source.id ||
      loading ||
      deleteConfirmationObjectId !== target.object_id
    ) {
      return;
    }
    setDeleteConfirmationObjectId("");
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.delete_object",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          object_id: target.object_id,
          expected_geometry: target.geometry,
        },
      );
      if (
        !result.changed ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        result.parent_revision_id !== revision.revision_id
      ) {
        throw new Error("The object-deletion revision could not be verified.");
      }
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // Re-indexing can be retried; the edit remains an immutable revision.
      }
      await loadPresentation(selectedSlide);
      setNotice(
        indexedRevision
          ? `Deleted the object and refreshed slide ${selectedSlide}.`
          : `Deleted the object from slide ${selectedSlide}. Re-index before using its content in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The object could not be deleted.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    deleteConfirmationObjectId,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedObject,
    selectedSlide,
    selectedSource,
  ]);

  const reviewSelectionAction = (
    action: "duplicate" | "delete" | "group" | "ungroup",
  ) => {
    if (
      loading ||
      voiceWorkflowActive ||
      !currentRevision ||
      !selectedSource ||
      loadedSourceId !== selectedSource.id ||
      !UUID_PATTERN.test(activeSlideId)
    )
      return;
    const ids =
      canvasSelectionEnabled && canvasSelectedIds.length
        ? canvasSelectedIds
        : selectedObject
          ? [selectedObject.object_id]
          : [];
    const objects = workspaceObjects.filter((o) => ids.includes(o.object_id));
    const grouping = action === "group" || action === "ungroup";
    if (
      !objects.length ||
      objects.length !== ids.length ||
      objects.length > 20 ||
      (action === "group" && objects.length < 2) ||
      (action === "ungroup" &&
        (objects.length !== 1 || objects[0]?.kind !== "grpSp")) ||
      objects.some(
        (o) =>
          !o.geometry_editable ||
          !o.geometry ||
          (grouping ? !o.group_editable : !o.delete_editable),
      )
    ) {
      setError(
        grouping
          ? (objects.find((o) => o.group_reason)?.group_reason ??
              "Select 2–20 supported objects to group, or one native group to ungroup.")
          : "Select 1–20 supported objects without placeholder, connector or animation dependencies.",
      );
      return;
    }
    setError(null);
    setInspectorPanel("objects");
    setPendingObjectAction({
      action,
      names: objects.map((o) => o.name),
      object_ids: objects.map((o) => o.object_id),
      operations:
        action === "group"
          ? [
              {
                type: "group_objects",
                params: {
                  slide_id: activeSlideId,
                  objects: objects.map((o) => ({
                    object_id: o.object_id,
                    expected_geometry: o.geometry,
                  })),
                },
              },
            ]
          : objects.map((o) => ({
              type:
                action === "ungroup" ? "ungroup_object" : `${action}_object`,
              params: {
                slide_id: activeSlideId,
                object_id: o.object_id,
                expected_geometry: o.geometry,
              },
            })),
    });
  };
  const copyWorkspaceObjects = () => {
    if (
      loading ||
      voiceWorkflowActive ||
      !currentRevision ||
      !selectedSource ||
      loadedSourceId !== selectedSource.id
    )
      return;
    const ids =
      canvasSelectionEnabled && canvasSelectedIds.length
        ? canvasSelectedIds
        : selectedObject
          ? [selectedObject.object_id]
          : [];
    const objects = workspaceObjects.filter((o) => ids.includes(o.object_id));
    if (
      !objects.length ||
      objects.length !== ids.length ||
      objects.length > 20 ||
      objects.some(
        (o) => !o.delete_editable || !o.geometry_editable || !o.geometry,
      )
    ) {
      setError(
        "Select 1–20 supported objects without placeholder, connector or animation dependencies to copy.",
      );
      return;
    }
    setObjectClipboard({
      source_document_id: selectedSource.id,
      source_revision_id: currentRevision.revision_id,
      source_slide_id: activeSlideId,
      object_ids: objects.map((o) => o.object_id),
      names: objects.map((o) => o.name),
    });
    setError(null);
    setNotice(
      `Copied ${objects.length} objects from revision ${currentRevision.revision_number}. Navigate to a destination slide and paste.`,
    );
  };
  const componentSelection: ComponentSelection | string = (() => {
    if (
      !currentRevision ||
      !selectedSource ||
      loadedSourceId !== selectedSource.id
    )
      return "Open a presentation to save components.";
    const ids =
      canvasSelectionEnabled && canvasSelectedIds.length
        ? canvasSelectedIds
        : selectedObject
          ? [selectedObject.object_id]
          : [];
    const objects = workspaceObjects.filter((o) => ids.includes(o.object_id));
    if (!objects.length) return "Select objects on the slide to save them.";
    if (
      objects.length !== ids.length ||
      objects.length > 20 ||
      objects.some(
        (o) =>
          o.group_child ||
          !o.delete_editable ||
          !o.geometry_editable ||
          !o.geometry,
      )
    )
      return "Select 1–20 supported objects without placeholder, connector or animation dependencies.";
    return {
      document_id: selectedSource.id,
      revision_id: currentRevision.revision_id,
      slide_id: activeSlideId,
      object_ids: objects.map((o) => o.object_id),
      names: objects.map((o) => o.name),
    };
  })();
  const insertComponent = (component: PresentationComponent) => {
    if (
      loading ||
      voiceWorkflowActive ||
      !currentRevision ||
      !selectedSource ||
      loadedSourceId !== selectedSource.id ||
      !UUID_PATTERN.test(activeSlideId)
    )
      return;
    setInspectorPanel("objects");
    setPendingObjectPaste({
      names: component.names,
      source_document_id: component.document_id,
      source_revision_id: component.revision_id,
      source_slide_id: component.slide_id,
      object_ids: component.object_ids,
      slide_id: activeSlideId,
    });
  };
  const formatTargets = (() => {
    if (
      !formatSource ||
      !selectedSource ||
      formatSource.document_id !== selectedSource.id ||
      formatSource.slide_id !== activeSlideId
    )
      return [];
    const ids =
      canvasSelectionEnabled && canvasSelectedIds.length
        ? canvasSelectedIds
        : selectedObject
          ? [selectedObject.object_id]
          : [];
    const objects = workspaceObjects.filter(
      (o) =>
        ids.includes(o.object_id) &&
        o.object_id !== formatSource.object_id &&
        (o.kind === "sp" || o.kind === "pic"),
    );
    return objects.length === ids.length && objects.length <= 20 ? objects : [];
  })();
  const copyObjectFormat = () => {
    const object =
      canvasSelectionEnabled && canvasSelectedIds.length === 1
        ? workspaceObjects.find((o) => o.object_id === canvasSelectedIds[0])
        : !canvasSelectedIds.length
          ? selectedObject
          : null;
    if (
      !object ||
      !selectedSource ||
      !UUID_PATTERN.test(activeSlideId) ||
      (object.kind !== "sp" && object.kind !== "pic")
    ) {
      setError("Select one shape, text box or picture to copy its format.");
      return;
    }
    setFormatSource({
      document_id: selectedSource.id,
      slide_id: activeSlideId,
      object_id: object.object_id,
      name: object.name,
    });
    setError(null);
    setNotice(
      `Copied the format of ${object.name}. Select objects on this slide and paste the format.`,
    );
  };
  const pasteObjectFormat = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const painter = formatSource;
    const targets = formatTargets;
    if (
      !source ||
      !revision ||
      !painter ||
      !targets.length ||
      loadedSourceId !== source.id ||
      loading
    )
      return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.copy_object_format",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: painter.slide_id,
          source_object_id: painter.object_id,
          target_object_ids: targets.map((o) => o.object_id),
        },
      );
      if (
        typeof result.changed !== "boolean" ||
        !UUID_PATTERN.test(result.revision_id) ||
        !Number.isSafeInteger(result.revision_number)
      ) {
        throw new Error("The format revision could not be verified.");
      }
      if (!result.changed) {
        setNotice("Those objects already have this format.");
        return;
      }
      setCurrentRevision({
        revision_id: result.revision_id,
        revision_kind: "edited",
        revision_number: result.revision_number,
        sha256: result.sha256,
        byte_size: result.byte_size,
      });
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
      } catch {
        // Core excludes an unindexed revision from retrieval until retry.
      }
      await loadPresentation(selectedSlide, targets[0]?.object_id);
      setNotice(
        `Saved revision ${result.revision_number} with the format of ${painter.name} on ${targets.length} object${targets.length === 1 ? "" : "s"}.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The format could not be pasted.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    currentRevision,
    formatSource,
    formatTargets,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedSlide,
    selectedSource,
  ]);
  const pasteWorkspaceObjects = () => {
    if (
      !objectClipboard ||
      loading ||
      voiceWorkflowActive ||
      !currentRevision ||
      !selectedSource ||
      loadedSourceId !== selectedSource.id ||
      !UUID_PATTERN.test(activeSlideId)
    )
      return;
    setInspectorPanel("objects");
    setPendingObjectPaste({ ...objectClipboard, slide_id: activeSlideId });
  };

  const duplicateSelectedObjectRevision = useCallback(async () => {
    const source = selectedSource;
    const revision = currentRevision;
    const target = selectedObject;
    if (
      !source ||
      !revision ||
      !target?.delete_editable ||
      !target.geometry_editable ||
      !target.geometry ||
      !UUID_PATTERN.test(activeSlideId) ||
      loadedSourceId !== source.id ||
      loading
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await requestCore<TextEditResult>(
        "presentation.workspace.duplicate_object",
        {
          project_id: project.id,
          document_id: source.id,
          expected_revision_id: revision.revision_id,
          slide_id: activeSlideId,
          object_id: target.object_id,
          expected_geometry: target.geometry,
        },
      );
      const createdObjectId = result.created_object_id;
      if (
        !result.changed ||
        !UUID_PATTERN.test(result.revision_id) ||
        typeof createdObjectId !== "string" ||
        !UUID_PATTERN.test(createdObjectId) ||
        !Number.isSafeInteger(result.revision_number) ||
        result.revision_number < 1 ||
        !/^[0-9a-f]{64}$/.test(result.sha256) ||
        !Number.isSafeInteger(result.byte_size) ||
        result.byte_size < 1 ||
        result.parent_revision_id !== revision.revision_id
      ) {
        throw new Error(
          "The object-duplication revision could not be verified.",
        );
      }
      let indexedRevision = false;
      try {
        await requestCore("source.reindex", {
          project_id: project.id,
          document_id: source.id,
        });
        indexedRevision = true;
      } catch {
        // The immutable revision remains current and can be re-indexed later.
      }
      await loadPresentation(selectedSlide, createdObjectId);
      setNotice(
        indexedRevision
          ? `Duplicated the object and refreshed slide ${selectedSlide}.`
          : `Duplicated the object on slide ${selectedSlide}. Re-index before using its content in rehearsal.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The object could not be duplicated.",
      );
    } finally {
      setLoading(false);
    }
  }, [
    activeSlideId,
    currentRevision,
    loadPresentation,
    loadedSourceId,
    loading,
    project.id,
    selectedObject,
    selectedSlide,
    selectedSource,
  ]);

  const restoreRevision = useCallback(
    async (revisionId: string) => {
      const source = selectedSource;
      const current = currentRevision;
      if (!source || !current || loading || revisionId === current.revision_id)
        return;
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.restore_revision",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: current.revision_id,
            revision_id: revisionId,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          result.revision_id !== revisionId ||
          !Number.isSafeInteger(result.revision_number) ||
          !/^[0-9a-f]{64}$/.test(result.sha256) ||
          !Number.isSafeInteger(result.byte_size)
        ) {
          throw new Error("The selected revision could not be verified.");
        }
        if (!result.changed) return;
        let indexedRevision = false;
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
          indexedRevision = true;
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation();
        setNotice(
          indexedRevision
            ? `Restored revision ${result.revision_number} and refreshed its slide text for retrieval.`
            : `Restored revision ${result.revision_number}. Re-index this presentation before using its text in rehearsal.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "The selected revision could not be restored.",
        );
      } finally {
        setLoading(false);
      }
    },
    [currentRevision, loadPresentation, loading, project.id, selectedSource],
  );

  const stepRevision = useCallback(
    async (direction: "undo" | "redo") => {
      const source = selectedSource;
      const current = currentRevision;
      if (!source || !current || loading) return;
      setLoading(true);
      setError(null);
      setNotice(null);
      try {
        const result = await requestCore<TextEditResult>(
          "presentation.workspace.step_revision",
          {
            project_id: project.id,
            document_id: source.id,
            expected_revision_id: current.revision_id,
            direction,
          },
        );
        if (
          typeof result.changed !== "boolean" ||
          !UUID_PATTERN.test(result.revision_id) ||
          !Number.isSafeInteger(result.revision_number) ||
          !/^[0-9a-f]{64}$/.test(result.sha256) ||
          !Number.isSafeInteger(result.byte_size)
        ) {
          throw new Error("The presentation revision could not be verified.");
        }
        if (!result.changed) {
          setNotice(
            direction === "undo"
              ? "There is no earlier presentation revision to undo."
              : "There is no later presentation revision to redo.",
          );
          return;
        }
        let indexedRevision = false;
        try {
          await requestCore("source.reindex", {
            project_id: project.id,
            document_id: source.id,
          });
          indexedRevision = true;
        } catch {
          // Core excludes an unindexed revision from retrieval until retry.
        }
        await loadPresentation();
        const action = direction === "undo" ? "Undid to" : "Redid to";
        setNotice(
          indexedRevision
            ? `${action} revision ${result.revision_number} and refreshed its slide text for retrieval.`
            : `${action} revision ${result.revision_number}. Re-index this presentation before using its text in rehearsal.`,
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : `The presentation could not ${direction}.`,
        );
      } finally {
        setLoading(false);
      }
    },
    [currentRevision, loadPresentation, loading, project.id, selectedSource],
  );

  const startVoiceInstruction =
    async (): Promise<VoiceGestureCapture | null> => {
      const source = selectedSource;
      const revision = currentRevision;
      const target = selectedTarget;
      if (
        voiceCaptureStateRef.current !== "idle" ||
        !source ||
        !revision ||
        !target?.replaceEditable ||
        loadedSourceId !== source.id ||
        loading
      ) {
        return null;
      }
      const startingEpoch = voiceEpochRef.current;
      voiceReviewIdRef.current = null;
      cancelAfterStartRef.current = false;
      setVoiceError(null);
      setVoicePartial("");
      setVoiceTranscript("");
      setVoiceRecognition(null);
      setVoiceClarification("");
      setVoicePhase("starting");
      try {
        const result = await requestCore<WorkspaceVoiceStartResult>(
          "presentation.workspace.voice_start",
          {
            project_id: project.id,
            document_id: source.id,
            revision_id: revision.revision_id,
            slide_number: selectedSlide,
            object_id: target.object_id,
          },
        );
        if (
          !UUID_PATTERN.test(result.capture_id) ||
          result.document_id !== source.id ||
          result.revision_id !== revision.revision_id ||
          result.capture_state !== "running"
        ) {
          throw new Error("Workspace voice capture could not be verified.");
        }
        if (
          !workspaceMountedRef.current ||
          voiceEpochRef.current !== startingEpoch ||
          cancelAfterStartRef.current ||
          !visible
        ) {
          try {
            await requestCore("presentation.workspace.voice_cancel", {
              project_id: project.id,
              capture_id: result.capture_id,
            });
          } catch {
            // Core shutdown also cancels any still-owned capture.
          }
          if (
            workspaceMountedRef.current &&
            voiceEpochRef.current === startingEpoch
          ) {
            voiceCaptureIdRef.current = null;
            setVoiceCaptureId(null);
            setVoicePhase("idle");
          }
          return null;
        }
        voiceCaptureIdRef.current = result.capture_id;
        setVoiceCaptureId(result.capture_id);
        setVoicePhase("listening");
        return {
          stop: () => stopVoiceInstruction(result.capture_id),
          cancel: () => cancelVoiceInstruction(result.capture_id),
        };
      } catch (caught) {
        if (
          !workspaceMountedRef.current ||
          voiceEpochRef.current !== startingEpoch
        )
          return null;
        setVoiceError(
          isCoreError(caught)
            ? caught.message
            : caught instanceof Error
              ? caught.message
              : "The local microphone could not start.",
        );
        setVoicePhase("idle");
        return null;
      }
    };

  const stopVoiceInstruction = async (expectedCaptureId?: string) => {
    const captureId = voiceCaptureIdRef.current;
    const source = selectedSource;
    const revision = currentRevision;
    const target = selectedTarget;
    if (
      !captureId ||
      !source ||
      !revision ||
      !target ||
      (expectedCaptureId && captureId !== expectedCaptureId) ||
      voiceCaptureStateRef.current !== "listening"
    ) {
      return;
    }
    const stoppingEpoch = voiceEpochRef.current;
    setVoiceError(null);
    setVoicePhase("stopping");
    try {
      const result = await requestCore<WorkspaceVoiceStopResult>(
        "presentation.workspace.voice_stop",
        { project_id: project.id, capture_id: captureId },
      );
      if (
        result.capture_id !== captureId ||
        result.document_id !== source.id ||
        result.revision_id !== revision.revision_id ||
        result.slide_number !== selectedSlide ||
        result.object_id !== target.object_id ||
        typeof result.transcript !== "string" ||
        result.transcript.length > MAX_REVIEW_TRANSCRIPT_CHARS
      ) {
        throw new Error("The dictated instruction could not be verified.");
      }
      if (
        !workspaceMountedRef.current ||
        voiceEpochRef.current !== stoppingEpoch ||
        voiceCaptureIdRef.current !== captureId
      )
        return;
      voiceCaptureIdRef.current = null;
      voiceReviewIdRef.current = captureId;
      setVoiceCaptureId(null);
      setVoicePartial("");
      setVoiceRecognition(
        parseRecognitionReview(result.recognition_review, result.transcript),
      );
      setVoiceTranscript(result.transcript);
      setVoicePhase("review");
    } catch (caught) {
      let captureReleased = false;
      try {
        await requestCore("presentation.workspace.voice_cancel", {
          project_id: project.id,
          capture_id: captureId,
        });
        captureReleased = true;
      } catch {
        // Keep the owner controls available so the user can retry cleanup.
      }
      if (
        !workspaceMountedRef.current ||
        voiceEpochRef.current !== stoppingEpoch
      )
        return;
      setVoiceError(
        isCoreError(caught)
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "The local transcript could not be finalized.",
      );
      if (captureReleased) {
        voiceCaptureIdRef.current = null;
        setVoiceCaptureId(null);
        setVoicePhase("idle");
      } else {
        setVoicePhase("listening");
      }
    }
  };

  const cancelVoiceInstruction = async (expectedCaptureId?: string) => {
    if (
      expectedCaptureId &&
      voiceCaptureIdRef.current !== expectedCaptureId &&
      voiceReviewIdRef.current !== expectedCaptureId
    )
      return;
    const phase = voiceCaptureStateRef.current;
    if (phase === "stopping" || phase === "cancelling" || phase === "idle")
      return;
    if (phase === "review") {
      voiceReviewIdRef.current = null;
      setVoiceTranscript("");
      setVoiceRecognition(null);
      setVoiceClarification("");
      setVoicePartial("");
      setVoiceError(null);
      setVoicePhase("idle");
      return;
    }
    if (phase === "starting") {
      cancelAfterStartRef.current = true;
      setVoicePhase("cancelling");
      return;
    }
    const captureId = voiceCaptureIdRef.current;
    const cancellingEpoch = voiceEpochRef.current;
    if (!captureId) {
      setVoicePhase("idle");
      return;
    }
    setVoiceError(null);
    setVoicePhase("cancelling");
    try {
      await requestCore("presentation.workspace.voice_cancel", {
        project_id: project.id,
        capture_id: captureId,
      });
      if (
        !workspaceMountedRef.current ||
        voiceEpochRef.current !== cancellingEpoch
      )
        return;
      voiceCaptureIdRef.current = null;
      setVoiceCaptureId(null);
      setVoicePartial("");
      setVoiceTranscript("");
      setVoiceRecognition(null);
      setVoiceClarification("");
      setVoicePhase("idle");
    } catch (caught) {
      if (
        !workspaceMountedRef.current ||
        voiceEpochRef.current !== cancellingEpoch
      )
        return;
      setVoiceError(
        isCoreError(caught)
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "The microphone could not be released. Retry cancel.",
      );
      setVoicePhase("listening");
    }
  };

  const voiceHold = usePushToEdit({
    root: voiceEditorRef,
    contextKey: JSON.stringify([
      project.id,
      selectedSource?.id,
      currentRevision?.revision_id,
      selectedSlide,
      selectedTarget?.object_id,
    ]),
    disabled:
      !visible ||
      !loadedSourceId ||
      !currentRevision ||
      !selectedTarget?.replaceEditable ||
      loading ||
      voiceWorkflowActive,
    start: startVoiceInstruction,
  });

  const useReviewedVoiceInstruction = () => {
    const instruction = clarifiedVoiceInstruction(
      voiceTranscript,
      voiceClarification,
    );
    if (!instruction) {
      setVoiceError("Review or dictate an instruction before using it.");
      return;
    }
    if (instruction.length > MAX_REWRITE_INSTRUCTION_CHARS) {
      setVoiceError(
        `Shorten the instruction to ${MAX_REWRITE_INSTRUCTION_CHARS} characters or fewer.`,
      );
      return;
    }
    rewriteGeneration.current += 1;
    voiceReviewIdRef.current = null;
    setRewriteInstruction(instruction);
    setTextRewriteProposal(null);
    setVoiceTranscript("");
    setVoiceRecognition(null);
    setVoiceClarification("");
    setVoicePartial("");
    setVoiceError(null);
    setVoicePhase("idle");
  };

  const handleVoiceDialogKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      voiceHold.cancel();
      void cancelVoiceInstruction();
      return;
    }
    if (event.key !== "Tab") return;
    const dialog = voiceDialogRef.current;
    if (!dialog) return;
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        "button:not(:disabled), textarea:not(:disabled)",
      ),
    );
    if (!focusable.length) {
      event.preventDefault();
      dialog.focus();
      return;
    }
    const first = focusable[0]!;
    const last = focusable[focusable.length - 1]!;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const available = project.storage_status === "ready";
  const currentRevisionEntry = revisionHistory?.revisions.find(
    (revision) => revision.revision_id === currentRevision?.revision_id,
  );
  const canUndoRevision = Boolean(
    revisionHistory?.has_more || currentRevisionEntry?.parent_revision_id,
  );
  const canRedoRevision = Boolean(
    revisionHistory?.has_more ||
    revisionHistory?.revisions.some(
      (revision) =>
        revision.parent_revision_id === currentRevision?.revision_id,
    ),
  );
  const countsText = (Object.keys(intentCounts) as IntentKind[])
    .filter((kind) => intentCounts[kind] > 0)
    .map((kind) => `${kind} ${intentCounts[kind]}`)
    .join(" · ");

  useEffect(() => {
    if (
      pendingCreatedId &&
      selectedSource?.id === pendingCreatedId &&
      !loading
    ) {
      setPendingCreatedId(null);
      void loadPresentation();
    }
  }, [pendingCreatedId, selectedSource, loading, loadPresentation]);

  useEffect(() => {
    setPendingRehearsalEdit(null);
  }, [
    currentRevision?.revision_id,
    selectedSlide,
    selectedSourceId,
    selectedTargetHandle,
  ]);

  const prepareFinding = (
    finding: RehearsalFinding,
    destination: "text" | "notes" | "rewrite",
  ) => {
    if (
      (finding.kind === "semantic_coverage" ||
        finding.kind === "semantic_objection") &&
      (finding.context_current !== true || finding.disposition !== "unreviewed")
    ) {
      setError(
        "Review a current, unreviewed semantic result before preparing an edit.",
      );
      return;
    }
    if (
      finding.slide_id !== activeSlideId ||
      finding.current_slide_number !== selectedSlide ||
      loading
    )
      return;
    if (destination === "notes") {
      if (
        !speakerNotesTarget?.editable ||
        speakerNotesTarget.current_text === null
      ) {
        setError("This slide's notes are not safely editable.");
        return;
      }
      const next = `${speakerNotesDraft}${speakerNotesDraft ? "\n\n" : ""}${finding.quote}`;
      if (next.length > MAX_SPEAKER_NOTES_CHARS) {
        setError("The combined notes exceed the editor limit.");
        return;
      }
      setSpeakerNotesDraft(next);
      setPendingRehearsalEdit({ finding, kind: "notes" });
      setInspectorPanel("notes");
    } else {
      if (
        finding.kind === "semantic_coverage" &&
        selectedTarget?.object_id !== finding.object_id
      ) {
        setError(
          "Select this finding's original native text object before preparing its edit.",
        );
        return;
      }
      if (!selectedTarget?.replaceEditable) {
        setError("Choose a supported text target before preparing this edit.");
        return;
      }
      if (
        finding.kind === "semantic_objection" &&
        destination === "text" &&
        finding.quote.length > MAX_MOCK_TEXT_CHARS
      ) {
        setError(
          "This concern excerpt exceeds the text replacement limit. Use notes or a reviewed rewrite.",
        );
        return;
      }
      setPendingRehearsalEdit({ finding, kind: "text" });
      setInspectorPanel("text");
      setTextRewriteProposal(null);
      setMockSvg(null);
      if (destination === "text") setMockText(finding.quote);
      else
        setRewriteInstruction(
          "Improve this text using the reviewed rehearsal finding. Preserve substantiated claims and distinguish unresolved evidence.",
        );
    }
    setError(null);
    setNotice(
      "Rehearsal edit prepared. Review the draft before saving; its source will be linked to the saved revision.",
    );
  };

  const rehearseCurrent = async () => {
    if (
      !selectedSource ||
      !currentRevision ||
      loading ||
      loadedSourceId !== selectedSource.id
    )
      return;
    setLoading(true);
    setError(null);
    try {
      await requestCore("presentation.workspace.select_for_rehearsal", {
        project_id: project.id,
        document_id: selectedSource.id,
        expected_revision_id: currentRevision.revision_id,
      });
      onGoToRehearsal({
        projectId: project.id,
        revisionId: currentRevision.revision_id,
        label: `${selectedSource.original_name} · Revision ${currentRevision.revision_number}`,
      });
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Rehearsal could not be prepared.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <section
      className="presentation-workspace"
      aria-label="Presentation Workspace"
    >
      <div className="pw-toolbar">
        <div>
          <p className="eyebrow">PRESENTATION EDITOR</p>
          <h2>
            {selectedSource
              ? sourceLabel(
                  selectedSource,
                  loadedSourceId === selectedSource.id && slideCount > 0
                    ? slideCount
                    : undefined,
                )
              : "Presentation Workspace"}
          </h2>
        </div>
        <div className="pw-source-controls">
          <button
            type="button"
            className="primary-button"
            disabled={
              !currentRevision ||
              loading ||
              voiceWorkflowActive ||
              loadedSourceId !== selectedSource?.id
            }
            onClick={() => void rehearseCurrent()}
          >
            Rehearse
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={!available || loading || voiceWorkflowActive}
            onClick={() => setCreatingPresentation(true)}
          >
            New presentation
          </button>
          <label>
            Presentation
            <select
              aria-label="Workspace presentation"
              value={selectedSourceId}
              onChange={(event) => changeSource(event.target.value)}
              disabled={!available || loading}
            >
              {decks.length ? (
                decks.map((source) => (
                  <option key={source.id} value={source.id}>
                    {sourceLabel(
                      source,
                      loadedSourceId === source.id && slideCount > 0
                        ? slideCount
                        : undefined,
                    )}
                  </option>
                ))
              ) : (
                <option value="">No imported PPTX presentations</option>
              )}
            </select>
          </label>
          <button
            type="button"
            className="primary-button"
            onClick={() => void loadPresentation()}
            disabled={!selectedSource || loading || !available}
          >
            {loading && !loadedSourceId ? "Opening…" : "Open preview"}
          </button>
        </div>
      </div>

      {!available ? (
        <div className="empty-state">
          <h3>Project storage is unavailable</h3>
          <p>Open Setup &amp; settings to review the project storage status.</p>
        </div>
      ) : !decks.length ? (
        <div className="empty-state">
          <h3>Start your next presentation</h3>
          <p>
            Create an editable deck from your outline, or import a PPTX to work
            on an existing presentation.
          </p>
          <button
            type="button"
            className="secondary-button"
            onClick={onGoToSources}
          >
            <Icon name="folder" size={16} /> Go to Sources
          </button>
        </div>
      ) : (
        <div className="pw-layout">
          <nav className="pw-slide-nav" aria-label="Presentation slides">
            <div className="pw-slide-nav-heading">
              <strong>Slides</strong>
              <span>
                {slideCount || selectedSource?.source_units_count || "—"}
              </span>
            </div>
            {slideCount ? (
              <ol>
                {Array.from(
                  { length: slideCount },
                  (_, index) => index + 1,
                ).map((slideNumber) => (
                  <li
                    key={slideNumber}
                    className={
                      slideDropTarget === slideNumber &&
                      draggedSlide !== null &&
                      draggedSlide !== slideNumber
                        ? "pw-slide-drop-target"
                        : undefined
                    }
                    onDragOver={(event) => {
                      if (draggedSlide === null) return;
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                      setSlideDropTarget(slideNumber);
                    }}
                    onDragLeave={() =>
                      setSlideDropTarget((current) =>
                        current === slideNumber ? null : current,
                      )
                    }
                    onDrop={(event) => {
                      event.preventDefault();
                      const from = draggedSlide;
                      setDraggedSlide(null);
                      setSlideDropTarget(null);
                      if (from !== null && from !== slideNumber)
                        void moveSlide(from - 1, slideNumber - 1);
                    }}
                  >
                    {sectionStarts.get(slideNumber) ? (
                      <span className="pw-slide-section">
                        {sectionStarts.get(slideNumber)}
                      </span>
                    ) : null}
                    <button
                      type="button"
                      className={
                        slideNumber === selectedSlide ? "selected" : ""
                      }
                      aria-current={
                        slideNumber === selectedSlide ? "true" : undefined
                      }
                      draggable={
                        !!loadedSourceId &&
                        !!currentRevision &&
                        !loading &&
                        slideCount > 1
                      }
                      onDragStart={(event) => {
                        event.dataTransfer.effectAllowed = "move";
                        event.dataTransfer.setData(
                          "text/plain",
                          String(slideNumber),
                        );
                        setDraggedSlide(slideNumber);
                      }}
                      onDragEnd={() => {
                        setDraggedSlide(null);
                        setSlideDropTarget(null);
                      }}
                      onClick={() => {
                        if (currentRevision) {
                          void renderSlide(
                            slideNumber,
                            generation.current,
                            currentRevision.revision_id,
                          );
                        }
                      }}
                      disabled={!loadedSourceId || !currentRevision || loading}
                    >
                      <span>{slideNumber}</span>
                      <span>
                        {slideContext?.ordinal === slideNumber
                          ? slideContext.title || `Slide ${slideNumber}`
                          : `Slide ${slideNumber}`}
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">
                Open an imported presentation to see slides.
              </p>
            )}
          </nav>

          <div className="pw-slide-column">
            {currentRevision ? (
              <div className="pw-current-revision" role="status">
                <span>
                  Current · Revision {currentRevision.revision_number}
                </span>
                <div>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => void stepRevision("undo")}
                    disabled={loading || !canUndoRevision}
                    aria-label="Undo last presentation edit"
                  >
                    Undo
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => void stepRevision("redo")}
                    disabled={loading || !canRedoRevision}
                    aria-label="Redo presentation edit"
                  >
                    Redo
                  </button>
                </div>
              </div>
            ) : null}
            <div className="pw-slide-controls">
              <span>
                {slideCount && loadedSourceId
                  ? `Slide ${selectedSlide} of ${slideCount}`
                  : "Slide preview"}
              </span>
              <div>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => void saveCurrentCopy()}
                  disabled={
                    !selectedSource ||
                    !currentRevision ||
                    loadedSourceId !== selectedSource.id ||
                    loading ||
                    savingCopy
                  }
                  aria-label="Save a copy of the current presentation revision"
                >
                  {savingCopy ? "Saving…" : "Save current copy"}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void saveCurrentCopy(true)}
                  disabled={
                    !selectedSource ||
                    !currentRevision ||
                    loadedSourceId !== selectedSource.id ||
                    loading ||
                    savingCopy
                  }
                  aria-label="Save and open the current presentation in the default presentation app"
                  title="Exports the current revision, then opens the saved copy with your system default presentation app."
                >
                  {savingCopy ? "Saving…" : "Save & open"}
                </button>
                {selectedSource && currentRevision ? (
                  <PdfExport
                    key={`${selectedSource.id}:${currentRevision.revision_id}`}
                    projectId={project.id}
                    documentId={selectedSource.id}
                    revisionId={currentRevision.revision_id}
                    revisionNumber={currentRevision.revision_number}
                    sourceSha256={currentRevision.sha256}
                    disabled={
                      loadedSourceId !== selectedSource.id ||
                      loading ||
                      savingCopy
                    }
                    onNotice={(message) => {
                      setError(null);
                      setNotice(message);
                    }}
                  />
                ) : null}
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    if (currentRevision) {
                      void renderSlide(
                        selectedSlide - 1,
                        generation.current,
                        currentRevision.revision_id,
                      );
                    }
                  }}
                  disabled={!loadedSourceId || selectedSlide <= 1 || loading}
                  aria-label="Previous slide"
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    if (currentRevision) {
                      void renderSlide(
                        selectedSlide + 1,
                        generation.current,
                        currentRevision.revision_id,
                      );
                    }
                  }}
                  disabled={
                    !loadedSourceId || selectedSlide >= slideCount || loading
                  }
                  aria-label="Next slide"
                >
                  Next
                </button>
              </div>
            </div>
            <label className="pw-canvas-select-toggle">
              <input
                type="checkbox"
                checked={canvasSelectionEnabled}
                disabled={!slideUrl || loading || voiceWorkflowActive}
                onChange={(event) => {
                  setCanvasSelectionEnabled(event.target.checked);
                  if (!event.target.checked) setCanvasSelectedIds([]);
                }}
              />
              Select objects on slide
            </label>
            {canvasSelectionEnabled ? (
              <label className="pw-canvas-select-toggle">
                <input
                  type="checkbox"
                  checked={canvasSnap}
                  disabled={loading || voiceWorkflowActive}
                  onChange={(event) => setCanvasSnap(event.target.checked)}
                />
                Snap object dragging and resizing to 0.1 inch increments
              </label>
            ) : null}
            {canvasSelectionEnabled ? (
              <label className="pw-canvas-select-toggle">
                <input
                  type="checkbox"
                  checked={canvasGuides}
                  disabled={loading || voiceWorkflowActive}
                  onChange={(event) => setCanvasGuides(event.target.checked)}
                />
                Align dragging and resizing to slide and nearby object edges and
                centers
              </label>
            ) : null}
            {canvasSelectionEnabled ? (
              <p className="muted">
                Click to select; Shift-click to add or remove. Drag from an
                empty area to select intersecting objects. Escape clears
                selection. Drag an object to review a move of the selection.
                Drag a handle to review resizing. Hold Shift on a corner to keep
                proportions; arrow keys resize a focused handle. Alignment
                guides override grid snapping on aligned axes; hold Alt to
                bypass guides. Paired gap markers help keep equal spacing while
                dragging along a row or column. {canvasSelectedIds.length}{" "}
                selected (maximum 20). Use Arrange objects together in Objects.
              </p>
            ) : null}
            <div
              className="pw-object-clipboard"
              role="group"
              aria-label="Object actions"
            >
              {selectedSource &&
              currentRevision &&
              loadedSourceId === selectedSource.id ? (
                <FindReplace
                  key={`find-replace:${project.id}:${selectedSource.id}:${currentRevision.revision_id}`}
                  projectId={project.id}
                  documentId={selectedSource.id}
                  revisionId={currentRevision.revision_id}
                  disabled={loading || voiceWorkflowActive}
                  onReplaced={async (replaced, objects) => {
                    let indexed = true;
                    try {
                      await requestCore("source.reindex", {
                        project_id: project.id,
                        document_id: selectedSource.id,
                      });
                    } catch {
                      indexed = false;
                    }
                    await loadPresentation(selectedSlide);
                    setNotice(
                      `Replaced ${replaced} ${replaced === 1 ? "match" : "matches"} in ${objects} ${objects === 1 ? "object" : "objects"} as one revision.` +
                        (indexed
                          ? ""
                          : " Re-index this deck before rehearsal."),
                    );
                  }}
                />
              ) : null}
              {selectedSource &&
              currentRevision &&
              activeSlideId &&
              loadedSourceId === selectedSource.id ? (
                <BulkTextFormat
                  key={`bulk-text:${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                  projectId={project.id}
                  documentId={selectedSource.id}
                  revisionId={currentRevision.revision_id}
                  slideId={activeSlideId}
                  slideNumber={selectedSlide}
                  selection={canvasSelectedIds.map((object_id) => ({
                    object_id,
                    name:
                      workspaceObjects.find(
                        (item) => item.object_id === object_id,
                      )?.name ?? "Unavailable object",
                  }))}
                  disabled={loading || voiceWorkflowActive}
                  onRestore={async (applied) => {
                    let indexed = true;
                    if (applied) {
                      try {
                        await requestCore("source.reindex", {
                          project_id: project.id,
                          document_id: selectedSource.id,
                        });
                      } catch {
                        indexed = false;
                      }
                    }
                    await loadPresentation(selectedSlide);
                    if (applied)
                      setNotice(
                        indexed
                          ? "Saved selected text formatting as one revision and refreshed retrieval."
                          : "Saved selected text formatting. Re-index this deck before rehearsal.",
                      );
                  }}
                />
              ) : null}
              <button
                type="button"
                className="secondary-button"
                disabled={
                  loading ||
                  voiceWorkflowActive ||
                  (!canvasSelectedIds.length && !selectedObject)
                }
                onClick={copyWorkspaceObjects}
              >
                Copy objects
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={
                  !objectClipboard ||
                  loading ||
                  voiceWorkflowActive ||
                  !currentRevision ||
                  !UUID_PATTERN.test(activeSlideId) ||
                  !selectedSource ||
                  loadedSourceId !== selectedSource.id
                }
                onClick={pasteWorkspaceObjects}
              >
                Paste objects
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={
                  loading ||
                  voiceWorkflowActive ||
                  !currentRevision ||
                  (!canvasSelectedIds.length && !selectedObject)
                }
                onClick={() => reviewSelectionAction("duplicate")}
              >
                Duplicate selection
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={
                  loading ||
                  voiceWorkflowActive ||
                  !currentRevision ||
                  (!canvasSelectedIds.length && !selectedObject)
                }
                onClick={() => reviewSelectionAction("delete")}
              >
                Delete selection
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={
                  loading ||
                  voiceWorkflowActive ||
                  !currentRevision ||
                  canvasSelectedIds.length < 2
                }
                onClick={() => reviewSelectionAction("group")}
              >
                Group selection
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={
                  loading ||
                  voiceWorkflowActive ||
                  !currentRevision ||
                  !(canvasSelectedIds.length === 1
                    ? workspaceObjects.some(
                        (o) =>
                          o.object_id === canvasSelectedIds[0] &&
                          o.kind === "grpSp" &&
                          o.group_editable,
                      )
                    : !canvasSelectedIds.length &&
                      selectedObject?.kind === "grpSp" &&
                      selectedObject.group_editable)
                }
                onClick={() => reviewSelectionAction("ungroup")}
              >
                Ungroup selection
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={
                  loading ||
                  voiceWorkflowActive ||
                  (!canvasSelectedIds.length && !selectedObject)
                }
                onClick={copyObjectFormat}
              >
                Copy format
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={
                  loading ||
                  voiceWorkflowActive ||
                  !currentRevision ||
                  !formatTargets.length
                }
                title={
                  formatSource
                    ? `Paste the format of ${formatSource.name}`
                    : "Copy a format first"
                }
                onClick={() => void pasteObjectFormat()}
              >
                Paste format
              </button>
              {objectClipboard ? (
                <span className="muted">
                  {objectClipboard.names.length} copied · presentation clipboard
                </span>
              ) : null}
            </div>
            <div
              onKeyDown={(event) => {
                if (
                  event.defaultPrevented ||
                  event.altKey ||
                  voiceWorkflowActive ||
                  (event.target instanceof Element &&
                    event.target.closest(
                      "input,textarea,select,[contenteditable]",
                    ))
                )
                  return;
                const key = event.key.toLowerCase();
                if (event.ctrlKey || event.metaKey) {
                  if (key === "g") {
                    event.preventDefault();
                    reviewSelectionAction(event.shiftKey ? "ungroup" : "group");
                  } else if (key === "z" || (key === "y" && !event.shiftKey)) {
                    event.preventDefault();
                    void stepRevision(
                      key === "y" || event.shiftKey ? "redo" : "undo",
                    );
                  } else if (!event.shiftKey) {
                    if (key === "c") {
                      event.preventDefault();
                      copyWorkspaceObjects();
                    }
                    if (key === "v") {
                      event.preventDefault();
                      pasteWorkspaceObjects();
                    }
                    if (key === "d") {
                      event.preventDefault();
                      reviewSelectionAction("duplicate");
                    }
                  }
                } else if (
                  !event.shiftKey &&
                  (key === "delete" || key === "backspace")
                ) {
                  event.preventDefault();
                  reviewSelectionAction("delete");
                }
              }}
              className={slideUrl ? "pw-slide-canvas-shell" : "pw-canvas"}
              aria-live="polite"
            >
              {slideUrl ? (
                <SlideObjectCanvas
                  key={`${activeSlideId}:${currentRevision?.revision_id}`}
                  image={slideUrl}
                  nativeTarget={
                    selectedSource &&
                    currentRevision &&
                    loadedSourceId === selectedSource.id &&
                    UUID_PATTERN.test(activeSlideId) &&
                    slideSizeEmu &&
                    !loading &&
                    !hasMockPreview
                      ? {
                          projectId: project.id,
                          documentId: selectedSource.id,
                          revisionId: currentRevision.revision_id,
                          sourceSha256: currentRevision.sha256,
                        }
                      : null
                  }
                  slideNumber={selectedSlide}
                  objects={workspaceObjects}
                  size={slideSizeEmu}
                  selectedIds={canvasSelectedIds}
                  grid={canvasSnap ? 91440 : 0}
                  alignmentGuides={canvasGuides}
                  onMove={(ids, dx, dy, tolerance) => {
                    if (
                      !slideSizeEmu ||
                      !currentRevision ||
                      loading ||
                      voiceWorkflowActive
                    )
                      return;
                    try {
                      const { operations } = guidedTranslation(
                        workspaceObjects,
                        ids,
                        activeSlideId,
                        dx,
                        dy,
                        slideSizeEmu,
                        canvasSnap ? 91440 : 0,
                        canvasGuides ? tolerance : undefined,
                      );
                      if (!operations.length) {
                        setNotice("No object positions changed.");
                        return;
                      }
                      setCanvasSelectedIds(ids);
                      setInspectorPanel("objects");
                      setPendingCanvasMove({ operations });
                    } catch (caught) {
                      setError(
                        caught instanceof Error
                          ? caught.message
                          : "The selection could not be moved.",
                      );
                    }
                  }}
                  onResize={(ids, handle, dx, dy, proportional, tolerance) => {
                    if (
                      !slideSizeEmu ||
                      !currentRevision ||
                      loading ||
                      voiceWorkflowActive
                    )
                      return;
                    try {
                      const { operations } = guidedResize(
                        workspaceObjects,
                        ids,
                        activeSlideId,
                        handle,
                        dx,
                        dy,
                        slideSizeEmu,
                        canvasSnap ? 91440 : 0,
                        proportional,
                        canvasGuides ? tolerance : undefined,
                      );
                      if (!operations.length) {
                        setNotice("No object sizes changed.");
                        return;
                      }
                      setCanvasSelectedIds(ids);
                      setInspectorPanel("objects");
                      setPendingCanvasMove({ resize: true, operations });
                    } catch (caught) {
                      setError(
                        caught instanceof Error
                          ? caught.message
                          : "The selection could not be resized.",
                      );
                    }
                  }}
                  enabled={
                    canvasSelectionEnabled && !loading && !voiceWorkflowActive
                  }
                  onSelect={(ids) => {
                    setCanvasSelectedIds(ids);
                    const object = workspaceObjects.find(
                      (o) => o.object_id === ids[ids.length - 1],
                    );
                    setSelectedObjectId(object?.object_id ?? "");
                    setDeleteConfirmationObjectId("");
                    setObjectGeometryDraft(
                      object?.geometry
                        ? geometryDraft(object.geometry)
                        : { x: "", y: "", width: "", height: "" },
                    );
                    setObjectCropDraft(
                      pictureCropDraft(object?.picture_crop ?? null),
                    );
                    setObjectAdjustmentDraft(
                      pictureAdjustmentDraft(object?.picture_adjustment),
                    );
                    setObjectRotationDraft(
                      objectRotationDraft(object?.rotation),
                    );
                    setObjectStyleDraft(
                      draftForShapeStyle(object?.shape_style ?? null),
                    );
                    setInspectorPanel("objects");
                  }}
                />
              ) : (
                <div className="pw-canvas-empty">
                  {loadProgress
                    ? `Verifying presentation… ${loadProgress}`
                    : "Open a presentation preview to begin."}
                </div>
              )}
            </div>
            <details className="pw-slide-actions">
              <summary>Slide actions &amp; layout</summary>
              <div className="pw-slide-actions-content">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void reorderSelectedSlide(-1)}
                  disabled={
                    !loadedSourceId ||
                    !currentRevision ||
                    selectedSlide <= 1 ||
                    loading
                  }
                  aria-label="Move current slide earlier"
                >
                  Move up
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void reorderSelectedSlide(1)}
                  disabled={
                    !loadedSourceId ||
                    !currentRevision ||
                    selectedSlide >= slideCount ||
                    loading
                  }
                  aria-label="Move current slide later"
                >
                  Move down
                </button>
                <label className="pw-layout-picker">
                  <span>Layout source slide</span>
                  <select
                    aria-label="Layout source slide"
                    value={blankSlideLayoutSourceId}
                    onChange={(event) =>
                      setBlankSlideLayoutSourceId(event.currentTarget.value)
                    }
                    disabled={!loadedSourceId || !fidelityReport || loading}
                    title="Use this slide's layout for a new or current slide."
                  >
                    <option value="">Current slide layout</option>
                    {fidelityReport?.slides.map((slide) => (
                      <option key={slide.slide_id} value={slide.slide_id}>
                        Layout from slide {slide.ordinal}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void createBlankSlideRevision()}
                  disabled={
                    !loadedSourceId ||
                    !currentRevision ||
                    !UUID_PATTERN.test(activeSlideId) ||
                    slideCount >= MAX_WORKSPACE_SLIDES ||
                    loading
                  }
                  aria-label="Add blank slide after current slide"
                >
                  Add blank slide
                </button>
                {selectedSource &&
                currentRevision &&
                fidelityReport &&
                loadedSourceId === selectedSource.id ? (
                  <CreateAppendix
                    key={`appendix:${selectedSource.id}:${currentRevision.revision_id}:${selectedSlide}`}
                    projectId={project.id}
                    documentId={selectedSource.id}
                    revisionId={currentRevision.revision_id}
                    slides={fidelityReport.slides}
                    currentSlideId={activeSlideId}
                    disabled={loading || voiceWorkflowActive}
                    onRestore={async (applied, dividerOrdinal) => {
                      let indexed = true;
                      if (applied) {
                        try {
                          await requestCore("source.reindex", {
                            project_id: project.id,
                            document_id: selectedSource.id,
                          });
                        } catch {
                          indexed = false;
                        }
                      }
                      await loadPresentation(
                        applied ? dividerOrdinal : selectedSlide,
                      );
                      if (applied)
                        setNotice(
                          indexed
                            ? "Saved the reviewed appendix as one revision and refreshed retrieval."
                            : "Saved the reviewed appendix. Re-index this deck before rehearsal.",
                        );
                    }}
                  />
                ) : null}
                {selectedSource &&
                currentRevision &&
                loadedSourceId === selectedSource.id ? (
                  <InsertAuthoredSlide
                    key={`${selectedSource.id}:${currentRevision.revision_id}:${selectedSlide}`}
                    projectId={project.id}
                    documentId={selectedSource.id}
                    revisionId={currentRevision.revision_id}
                    slideId={activeSlideId}
                    layoutSourceSlideId={
                      blankSlideLayoutSourceId || activeSlideId
                    }
                    slideNumber={selectedSlide}
                    disabled={
                      loading ||
                      voiceWorkflowActive ||
                      slideCount >= MAX_WORKSPACE_SLIDES
                    }
                    onRestore={async (applied) => {
                      let indexed = true;
                      if (applied) {
                        try {
                          await requestCore("source.reindex", {
                            project_id: project.id,
                            document_id: selectedSource.id,
                          });
                        } catch {
                          indexed = false;
                        }
                      }
                      await loadPresentation(
                        applied ? selectedSlide + 1 : selectedSlide,
                      );
                      if (applied)
                        setNotice(
                          indexed
                            ? "Inserted the reviewed slide as one revision and refreshed retrieval."
                            : "Inserted the reviewed slide. Re-index this deck before rehearsal.",
                        );
                    }}
                  />
                ) : null}
                {selectedSource &&
                currentRevision &&
                activeSlideId &&
                loadedSourceId === selectedSource.id ? (
                  <>
                    <NativeCharts
                      key={`native-chart:${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                      projectId={project.id}
                      documentId={selectedSource.id}
                      revisionId={currentRevision.revision_id}
                      slideId={activeSlideId}
                      slideNumber={selectedSlide}
                      disabled={loading || voiceWorkflowActive}
                      onRestore={async (applied) => {
                        let indexed = true;
                        if (applied) {
                          try {
                            await requestCore("source.reindex", {
                              project_id: project.id,
                              document_id: selectedSource.id,
                            });
                          } catch {
                            indexed = false;
                          }
                        }
                        await loadPresentation(selectedSlide);
                        if (applied)
                          setNotice(
                            indexed
                              ? "Saved the reviewed native chart changes as one revision and refreshed retrieval."
                              : "Saved the reviewed native chart. Re-index this deck before rehearsal.",
                          );
                      }}
                    />
                    <ShapeFills
                      key={`shape-fill:${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                      projectId={project.id}
                      documentId={selectedSource.id}
                      revisionId={currentRevision.revision_id}
                      slideId={activeSlideId}
                      slideNumber={selectedSlide}
                      disabled={loading || voiceWorkflowActive}
                      onRestore={async (applied) => {
                        let indexed = true;
                        if (applied) {
                          try {
                            await requestCore("source.reindex", {
                              project_id: project.id,
                              document_id: selectedSource.id,
                            });
                          } catch {
                            indexed = false;
                          }
                        }
                        await loadPresentation(selectedSlide);
                        if (applied)
                          setNotice(
                            indexed
                              ? "Saved the reviewed shape fill as one revision and refreshed retrieval."
                              : "Saved the reviewed shape fill. Re-index this deck before rehearsal.",
                          );
                      }}
                    />
                    <TextFit
                      key={`native-text-fit:${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                      projectId={project.id}
                      documentId={selectedSource.id}
                      revisionId={currentRevision.revision_id}
                      slideId={activeSlideId}
                      slideNumber={selectedSlide}
                      disabled={loading || voiceWorkflowActive}
                      onRestore={async (applied) => {
                        let indexed = true;
                        if (applied) {
                          try {
                            await requestCore("source.reindex", {
                              project_id: project.id,
                              document_id: selectedSource.id,
                            });
                          } catch {
                            indexed = false;
                          }
                        }
                        await loadPresentation(selectedSlide);
                        if (applied)
                          setNotice(
                            indexed
                              ? "Saved the reviewed text fit as one revision and refreshed retrieval."
                              : "Saved the reviewed text fit. Re-index this deck before rehearsal.",
                          );
                      }}
                    />
                    <NativeTables
                      key={`native-table:${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                      projectId={project.id}
                      documentId={selectedSource.id}
                      revisionId={currentRevision.revision_id}
                      slideId={activeSlideId}
                      slideNumber={selectedSlide}
                      disabled={loading || voiceWorkflowActive}
                      onRestore={async (applied) => {
                        let indexed = true;
                        if (applied) {
                          try {
                            await requestCore("source.reindex", {
                              project_id: project.id,
                              document_id: selectedSource.id,
                            });
                          } catch {
                            indexed = false;
                          }
                        }
                        await loadPresentation(selectedSlide);
                        if (applied)
                          setNotice(
                            indexed
                              ? "Saved the reviewed native table as one revision and refreshed retrieval."
                              : "Saved the reviewed native table. Re-index this deck before rehearsal.",
                          );
                      }}
                    />
                    <NativeDiagrams
                      key={`native-diagram:${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                      projectId={project.id}
                      documentId={selectedSource.id}
                      revisionId={currentRevision.revision_id}
                      slideId={activeSlideId}
                      slideNumber={selectedSlide}
                      disabled={loading || voiceWorkflowActive}
                      onRestore={async (applied) => {
                        let indexed = true;
                        if (applied) {
                          try {
                            await requestCore("source.reindex", {
                              project_id: project.id,
                              document_id: selectedSource.id,
                            });
                          } catch {
                            indexed = false;
                          }
                        }
                        await loadPresentation(selectedSlide);
                        if (applied)
                          setNotice(
                            indexed
                              ? "Saved the reviewed native diagram as one revision and refreshed retrieval."
                              : "Saved the reviewed native diagram. Re-index this deck before rehearsal.",
                          );
                      }}
                    />
                    <NativeLayouts
                      key={`native-layout:${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                      projectId={project.id}
                      documentId={selectedSource.id}
                      revisionId={currentRevision.revision_id}
                      slideId={activeSlideId}
                      slideNumber={selectedSlide}
                      disabled={loading || voiceWorkflowActive}
                      onRestore={async (applied, created) => {
                        let indexed = true;
                        if (applied) {
                          try {
                            await requestCore("source.reindex", {
                              project_id: project.id,
                              document_id: selectedSource.id,
                            });
                          } catch {
                            indexed = false;
                          }
                        }
                        await loadPresentation(
                          selectedSlide + (applied && created ? 1 : 0),
                        );
                        if (applied)
                          setNotice(
                            created
                              ? indexed
                                ? "Inserted the reviewed native slide as one revision and refreshed retrieval."
                                : "Inserted the reviewed native slide. Re-index this deck before rehearsal."
                              : indexed
                                ? "Saved the reviewed native layout as one revision and refreshed retrieval."
                                : "Saved the reviewed native layout. Re-index this deck before rehearsal.",
                          );
                      }}
                    />
                  </>
                ) : null}
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void applySlideLayoutRevision()}
                  disabled={
                    !loadedSourceId ||
                    !currentRevision ||
                    !UUID_PATTERN.test(activeSlideId) ||
                    !fidelityReport ||
                    !blankSlideLayoutSourceId ||
                    blankSlideLayoutSourceId === activeSlideId ||
                    loading
                  }
                  aria-label="Apply selected layout to current slide"
                  title="Applying a layout can reposition placeholders; use revision history to undo."
                >
                  Apply layout
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void duplicateSelectedSlideRevision()}
                  disabled={
                    !loadedSourceId ||
                    !currentRevision ||
                    !UUID_PATTERN.test(activeSlideId) ||
                    slideCount >= MAX_WORKSPACE_SLIDES ||
                    loading
                  }
                  aria-label="Duplicate current slide"
                >
                  Duplicate slide
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void saveSlideHiddenRevision()}
                  disabled={
                    !loadedSourceId ||
                    !currentRevision ||
                    slideHidden === null ||
                    !UUID_PATTERN.test(activeSlideId) ||
                    loading
                  }
                  aria-pressed={slideHidden === true}
                >
                  {slideHidden
                    ? "Show slide in slide show"
                    : "Hide slide in slide show"}
                </button>
                <AccessibilityCheck
                  result={accessibility}
                  current={
                    accessibility?.revision_id === currentRevision?.revision_id
                  }
                  disabled={loading || !currentRevision || !loadedSourceId}
                  onCheck={() => void checkAccessibility()}
                  onGo={goToAccessibilityIssue}
                  onAddTitle={(issue, title) =>
                    void addSlideTitle(issue, title)
                  }
                  onAskCopilot={() =>
                    setCopilotPrefill({
                      instruction:
                        "Add concise alt text to the charts, diagrams, groups and pictures flagged as missing alt text, using their data and slide text; mark purely decorative objects as decorative.",
                      scope: "deck",
                      nonce: Date.now(),
                    })
                  }
                />
                {slideSections &&
                slideSections.revision_id === currentRevision?.revision_id ? (
                  <SlideSections
                    state={slideSections}
                    disabled={loading}
                    onApply={(sections) => void saveSlideSections(sections)}
                  />
                ) : null}
                {themeColors?.editable && themeColors.colors ? (
                  <fieldset className="pw-picture-crop">
                    <legend>Theme colors</legend>
                    <p className="muted">
                      Shapes and text that use theme colors change across the
                      whole deck; directly chosen colors stay.
                    </p>
                    {THEME_COLOR_SLOTS.map(([slot, label]) => (
                      <label key={slot}>
                        {label}
                        <input
                          type="color"
                          aria-label={`Theme color ${label}`}
                          value={(
                            themeColorDraft[slot] ??
                            themeColors.colors?.[slot] ??
                            "#000000"
                          ).toLowerCase()}
                          onChange={(event) =>
                            setThemeColorDraft((current) => ({
                              ...current,
                              [slot]: event.target.value.toUpperCase(),
                            }))
                          }
                          disabled={loading}
                        />
                      </label>
                    ))}
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void saveThemeColors()}
                      disabled={
                        loading ||
                        THEME_COLOR_SLOTS.every(
                          ([slot]) =>
                            (themeColorDraft[slot] ?? "").toUpperCase() ===
                            themeColors.colors?.[slot],
                        )
                      }
                    >
                      Apply theme colors
                    </button>
                  </fieldset>
                ) : null}
                {themeFonts?.editable ? (
                  <fieldset className="pw-picture-crop">
                    <legend>Theme fonts</legend>
                    <p className="muted">
                      Text that uses the theme fonts changes across the whole
                      deck; text with its own font keeps it.
                    </p>
                    <label>
                      Heading font
                      <input
                        type="text"
                        list="pw-font-family-suggestions"
                        maxLength={31}
                        aria-label="Theme heading font"
                        value={themeFontDraft.heading}
                        onChange={(event) =>
                          setThemeFontDraft((current) => ({
                            ...current,
                            heading: event.target.value,
                          }))
                        }
                        disabled={loading}
                      />
                    </label>
                    <label>
                      Body font
                      <input
                        type="text"
                        list="pw-font-family-suggestions"
                        maxLength={31}
                        aria-label="Theme body font"
                        value={themeFontDraft.body}
                        onChange={(event) =>
                          setThemeFontDraft((current) => ({
                            ...current,
                            body: event.target.value,
                          }))
                        }
                        disabled={loading}
                      />
                    </label>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void saveThemeFonts()}
                      disabled={
                        loading ||
                        !themeFontDraft.heading.trim() ||
                        !themeFontDraft.body.trim() ||
                        (themeFontDraft.heading === themeFonts.heading_font &&
                          themeFontDraft.body === themeFonts.body_font)
                      }
                    >
                      Apply theme fonts
                    </button>
                  </fieldset>
                ) : null}
                {selectedSource &&
                currentRevision &&
                fidelityReport &&
                loadedSourceId === selectedSource.id ? (
                  <ReuseSlides
                    projectId={project.id}
                    decks={decks
                      .filter((item) => item.id !== selectedSource.id)
                      .map((item) => ({
                        id: item.id,
                        name: item.original_name,
                      }))}
                    slideCount={fidelityReport.slide_count}
                    currentSlide={selectedSlide}
                    disabled={loading || voiceWorkflowActive}
                    request={requestCore}
                    onReuse={(reuse) => void reuseSlide(reuse)}
                  />
                ) : null}
                {selectedSource &&
                currentRevision &&
                loadedSourceId === selectedSource.id ? (
                  <ReplaceFonts
                    projectId={project.id}
                    documentId={selectedSource.id}
                    revisionId={currentRevision.revision_id}
                    disabled={loading || voiceWorkflowActive}
                    request={requestCore}
                    onReplace={(font, replacement) =>
                      void replaceDeckFont(font, replacement)
                    }
                  />
                ) : null}
                {footerState ? (
                  <fieldset className="pw-picture-crop">
                    <legend>Slide numbers &amp; footer</legend>
                    <p className="muted">
                      Applies to every slide whose layout has these placeholders
                      ({footerState.supported_slides} of{" "}
                      {footerState.slide_count}). Slide numbers:{" "}
                      {footerState.slide_numbers}; footers:{" "}
                      {footerState.footers}.
                    </p>
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        aria-label="Show slide numbers"
                        checked={footerDraft.numbers}
                        onChange={(event) =>
                          setFooterDraft((current) => ({
                            ...current,
                            numbers: event.target.checked,
                          }))
                        }
                        disabled={loading}
                      />
                      Slide numbers
                    </label>
                    <label>
                      Footer text (empty removes footers)
                      <input
                        type="text"
                        maxLength={200}
                        aria-label="Footer text"
                        value={footerDraft.text}
                        onChange={(event) =>
                          setFooterDraft((current) => ({
                            ...current,
                            text: event.target.value,
                          }))
                        }
                        disabled={loading}
                      />
                    </label>
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        aria-label="Skip title slides"
                        checked={footerDraft.skipTitle}
                        onChange={(event) =>
                          setFooterDraft((current) => ({
                            ...current,
                            skipTitle: event.target.checked,
                          }))
                        }
                        disabled={loading}
                      />
                      Don&apos;t show on title slides
                    </label>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void saveSlideFooters()}
                      disabled={loading || footerState.supported_slides < 1}
                    >
                      Apply to all slides
                    </button>
                  </fieldset>
                ) : null}
                {slideAnimations &&
                slideAnimations.slide_id === activeSlideId ? (
                  <SlideAnimations
                    state={slideAnimations}
                    disabled={loading || !currentRevision}
                    onApply={(effects) => void saveSlideAnimations(effects)}
                  />
                ) : null}
                <label>
                  Slide transition
                  <select
                    aria-label="Slide transition"
                    value={slideTransition ?? ""}
                    onChange={(event) =>
                      void saveSlideTransitionRevision(event.target.value)
                    }
                    disabled={
                      !loadedSourceId ||
                      !currentRevision ||
                      typeof slideTransition !== "string" ||
                      loading
                    }
                  >
                    {slideTransition === null ? (
                      <option value="">Effect kept as is (read-only)</option>
                    ) : null}
                    {SLIDE_TRANSITIONS.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setDeleteConfirmationSlideId(activeSlideId)}
                  disabled={
                    !loadedSourceId ||
                    !currentRevision ||
                    slideCount <= 1 ||
                    !UUID_PATTERN.test(activeSlideId) ||
                    loading
                  }
                  aria-label="Review current slide deletion"
                >
                  Review slide deletion
                </button>
                {deleteConfirmationSlideId === activeSlideId &&
                slideCount > 1 ? (
                  <div
                    className="pw-delete-confirmation"
                    role="group"
                    aria-label="Confirm slide deletion"
                  >
                    <span>
                      Delete slide {selectedSlide}? This saves a revision that
                      you can restore from history.
                    </span>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void deleteSelectedSlideRevision()}
                      disabled={loading}
                      aria-label="Confirm delete current slide"
                    >
                      Confirm delete slide
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setDeleteConfirmationSlideId("")}
                      disabled={loading}
                      aria-label="Cancel slide deletion"
                    >
                      Cancel
                    </button>
                  </div>
                ) : null}
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void saveUnchangedCopy()}
                  disabled={
                    !selectedSource ||
                    loadedSourceId !== selectedSource.id ||
                    loading ||
                    savingCopy
                  }
                  aria-label="Save unchanged copy of the imported presentation"
                >
                  Save original copy
                </button>
              </div>
            </details>
            {error ? (
              <>
                <p className="error-message" role="alert">
                  {error}
                </p>
                {decisionUsageLimitError === error ? (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => void openChatGPTUsageSettings()}
                  >
                    Manage ChatGPT usage
                  </button>
                ) : null}
              </>
            ) : null}
            {notice ? (
              <p className="pw-notice" role="status">
                {notice}
              </p>
            ) : null}
            <p className="pw-preview-disclosure">
              Browser appearance uses an experimental renderer. Text placement,
              wrapping, and unsupported content may differ from PowerPoint. Open
              every exported deck in PowerPoint to verify its layout before use.
            </p>
          </div>

          <aside
            className="pw-copilot-panel"
            aria-label="Copilot preview and slide notes"
          >
            <div className="pw-copilot-heading">
              <h3>Slide studio</h3>
              <p className="muted">
                Edit this slide, review suggestions, and save a revision.
              </p>
              {selectedSource &&
              currentRevision &&
              loadedSourceId === selectedSource.id ? (
                <CopilotEditPlan
                  key={`${project.id}:${selectedSource.id}:${currentRevision.revision_id}`}
                  projectId={project.id}
                  documentId={selectedSource.id}
                  revisionId={currentRevision.revision_id}
                  slideNumber={selectedSlide}
                  disabled={loading || voiceWorkflowActive}
                  prefill={copilotPrefill}
                  onPrefillConsumed={clearCopilotPrefill}
                  onRestore={async (applied) => {
                    let indexed = true;
                    if (applied) {
                      try {
                        await requestCore("source.reindex", {
                          project_id: project.id,
                          document_id: selectedSource.id,
                        });
                      } catch {
                        indexed = false;
                      }
                    }
                    await loadPresentation(selectedSlide);
                    if (applied)
                      setNotice(
                        indexed
                          ? "Saved Copilot's reviewed edits as one revision and refreshed slide text for retrieval."
                          : "Saved Copilot's reviewed edits. Re-index this presentation before using its edited text in rehearsal.",
                      );
                  }}
                />
              ) : null}
            </div>
            <div
              className="pw-panel-switcher"
              role="group"
              aria-label="Slide studio panels"
            >
              {(
                [
                  ["text", "Text"],
                  ["objects", "Objects"],
                  ["notes", "Notes"],
                  ["purpose", "Purpose"],
                  ["narrative", "Narrative"],
                  ["deck-review", "Deck review"],
                  ["history", "History"],
                  ["rehearsal", "Rehearsal"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={inspectorPanel === id}
                  aria-controls={`pw-panel-${id}`}
                  onClick={() => setInspectorPanel(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            {pendingRehearsalEdit ? (
              <div className="pw-finding-draft" role="status">
                <strong>
                  Draft from rehearsal · Revision{" "}
                  {pendingRehearsalEdit.finding.source_revision_number}
                </strong>
                <span>
                  {pendingRehearsalEdit.finding.label.replaceAll("_", " ")}
                </span>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={loading}
                  onClick={() => {
                    if (pendingRehearsalEdit.kind === "notes")
                      setSpeakerNotesDraft(
                        speakerNotesTarget?.current_text ?? "",
                      );
                    else {
                      setMockText(selectedTarget?.text ?? "");
                      setRewriteInstruction("");
                      setTextRewriteProposal(null);
                      setMockSvg(null);
                    }
                    setPendingRehearsalEdit(null);
                  }}
                >
                  Cancel finding edit
                </button>
              </div>
            ) : null}
            <div
              id="pw-panel-deck-review"
              className="pw-studio-panel"
              hidden={inspectorPanel !== "deck-review"}
            >
              {selectedSource &&
              currentRevision &&
              loadedSourceId === selectedSource.id ? (
                <DeckSemanticReview
                  claimScanCache={claimScanCache.current}
                  key={`${project.id}:${selectedSource.id}:${currentRevision.revision_id}`}
                  projectId={project.id}
                  documentId={selectedSource.id}
                  revisionId={currentRevision.revision_id}
                  visible={visible && inspectorPanel === "deck-review"}
                  disabled={loading || voiceWorkflowActive}
                  onOpenSlide={(ordinal) => {
                    setDeckClaimCandidate(null);
                    setInspectorPanel("purpose");
                    void renderSlide(
                      ordinal,
                      generation.current,
                      currentRevision.revision_id,
                    );
                  }}
                  onReviewCandidate={(slide, candidate) => {
                    setDeckClaimCandidate({
                      document: selectedSource.id,
                      revision: currentRevision.revision_id,
                      slide: slide.slide_id,
                      object_id: candidate.object_id,
                      quote: candidate.quote,
                      source_kind: candidate.source_kind,
                      initial_evidence: candidate.initial_evidence,
                      selection_token: ++deckClaimSelection.current,
                    });
                    setInspectorPanel("purpose");
                    void renderSlide(
                      slide.slide_number,
                      generation.current,
                      currentRevision.revision_id,
                    );
                  }}
                />
              ) : null}
            </div>
            <div
              id="pw-panel-narrative"
              className="pw-studio-panel"
              hidden={inspectorPanel !== "narrative"}
            >
              {selectedSource &&
              currentRevision &&
              loadedSourceId === selectedSource.id ? (
                <PresentationNarrative
                  key={`${project.id}:${selectedSource.id}:${currentRevision.revision_id}`}
                  projectId={project.id}
                  documentId={selectedSource.id}
                  revisionId={currentRevision.revision_id}
                  disabled={loading || voiceWorkflowActive}
                  onOpenSlide={(ordinal, takeaway) => {
                    setTakeawayFinding(
                      takeaway
                        ? {
                            revision: currentRevision.revision_id,
                            document: selectedSource.id,
                            ordinal,
                            text: takeaway,
                          }
                        : null,
                    );
                    setInspectorPanel("purpose");
                    void renderSlide(
                      ordinal,
                      generation.current,
                      currentRevision.revision_id,
                    );
                  }}
                />
              ) : null}
            </div>
            <div
              id="pw-panel-rehearsal"
              className="pw-studio-panel"
              hidden={inspectorPanel !== "rehearsal"}
            >
              {selectedSource &&
              currentRevision &&
              loadedSourceId === selectedSource.id ? (
                <RehearsalFindings
                  projectId={project.id}
                  documentId={selectedSource.id}
                  revisionId={currentRevision.revision_id}
                  selectedSlide={selectedSlide}
                  visible={visible && inspectorPanel === "rehearsal"}
                  disabled={loading || voiceWorkflowActive}
                  onOpenSlide={(ordinal) =>
                    void renderSlide(
                      ordinal,
                      generation.current,
                      currentRevision.revision_id,
                    )
                  }
                  selectedTextObjectId={selectedTarget?.object_id ?? null}
                  selectedTextEditable={Boolean(
                    selectedTarget?.replaceEditable,
                  )}
                  onSelectTextObject={(finding) => {
                    if (loading || finding.slide_id !== activeSlideId) return;
                    const target = textTargets.find(
                      (item) =>
                        item.object_id === finding.object_id &&
                        item.replaceEditable,
                    );
                    if (!target) {
                      setError(
                        "The original object is not safely editable in this revision.",
                      );
                      return;
                    }
                    setSelectedTargetHandle(target.key);
                    setNotice(
                      "Original text object selected. Review the semantic result, then prepare its edit.",
                    );
                    setError(null);
                  }}
                  onPrepare={prepareFinding}
                />
              ) : (
                <p>Open a presentation to review its rehearsal findings.</p>
              )}
            </div>
            <div
              id="pw-panel-purpose"
              className="pw-studio-panel"
              hidden={inspectorPanel !== "purpose"}
            >
              <section
                className="pw-purpose-panel"
                aria-labelledby="pw-purpose-title"
              >
                <p className="eyebrow">FAST TYPED DECISION</p>
                <h4 id="pw-purpose-title">Suggest this slide’s purpose</h4>
                <p className="muted">
                  On request, Core sends the selected slide’s text to the chosen
                  decision provider when project privacy permits. Images and
                  diagrams are not analyzed. The suggestion is not saved or
                  applied automatically.
                </p>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void classifyCurrentSlide()}
                  disabled={
                    !selectedSource ||
                    !currentRevision ||
                    loadedSourceId !== selectedSource.id ||
                    loading ||
                    decisionBusy
                  }
                >
                  {decisionBusy ? "Deciding…" : "Suggest slide purpose"}
                </button>
                {slidePurposeDecision ? (
                  <div className="pw-purpose-result" role="status">
                    <strong>
                      Suggestion:{" "}
                      {slidePurposeDecision.purpose.replaceAll("_", " ")}
                    </strong>
                    <span>
                      {slidePurposeDecision.provider_id} ·{" "}
                      {slidePurposeDecision.model_id.replace(
                        /@sha256:[0-9a-f]{64}$/,
                        "",
                      )}{" "}
                      · {slidePurposeDecision.latency_ms} ms
                    </span>
                    <span>
                      {slidePurposeDecision.confidence === null
                        ? "No confidence estimate was returned."
                        : `Provider confidence estimate: ${Math.round(slidePurposeDecision.confidence * 100)}%.`}{" "}
                      Review before using this suggestion.
                    </span>
                  </div>
                ) : null}
                {savedCurrentSlidePurpose ? (
                  <div className="pw-purpose-result" role="status">
                    <strong>
                      Saved purpose:{" "}
                      {savedCurrentSlidePurpose.purpose.replaceAll("_", " ")}
                    </strong>
                    <span>
                      User-confirmed for revision{" "}
                      {currentRevision?.revision_number}.
                    </span>
                  </div>
                ) : null}
                <label className="pw-purpose-choice">
                  <span>Choose or correct this slide’s purpose</span>
                  <select
                    aria-label="Slide purpose to save"
                    value={slidePurposeDraft}
                    onChange={(event) =>
                      setSlidePurposeDraft(
                        event.currentTarget.value as SlidePurpose,
                      )
                    }
                    disabled={!activeSlideId || loading || savingSlidePurpose}
                  >
                    {SLIDE_PURPOSES.map((purpose) => (
                      <option key={purpose} value={purpose}>
                        {purpose.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void saveSlidePurpose()}
                  disabled={
                    !selectedSource ||
                    !currentRevision ||
                    !UUID_PATTERN.test(activeSlideId) ||
                    loadedSourceId !== selectedSource.id ||
                    loading ||
                    savingSlidePurpose
                  }
                >
                  {savingSlidePurpose
                    ? "Saving purpose…"
                    : "Save purpose for this revision"}
                </button>
              </section>
              {selectedSource &&
              currentRevision &&
              activeSlideId &&
              loadedSourceId === selectedSource.id ? (
                <>
                  <SlideTakeaway
                    key={`takeaway:${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                    projectId={project.id}
                    documentId={selectedSource.id}
                    revisionId={currentRevision.revision_id}
                    slideId={activeSlideId}
                    slideNumber={selectedSlide}
                    disabled={loading || voiceWorkflowActive}
                    suggestion={
                      takeawayFinding?.revision ===
                        currentRevision.revision_id &&
                      takeawayFinding.document === selectedSource.id &&
                      takeawayFinding.ordinal === selectedSlide
                        ? takeawayFinding.text
                        : undefined
                    }
                  />
                  <ClaimEvidenceReview
                    key={`claims:${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                    projectId={project.id}
                    documentId={selectedSource.id}
                    revisionId={currentRevision.revision_id}
                    slideId={activeSlideId}
                    slideNumber={selectedSlide}
                    targets={claimTextTargets}
                    candidateToReview={
                      deckClaimCandidate?.document === selectedSource.id &&
                      deckClaimCandidate.revision ===
                        currentRevision.revision_id &&
                      deckClaimCandidate.slide === activeSlideId
                        ? deckClaimCandidate
                        : undefined
                    }
                    disabled={loading || voiceWorkflowActive}
                    slideSize={slideSizeEmu}
                    onFootnoteRestore={async (applied) => {
                      let reindexed = true;
                      if (applied) {
                        try {
                          unwrapInvokeResult(
                            await window.presenterCopilot.core.request(
                              "source.reindex",
                              {
                                project_id: project.id,
                                document_id: selectedSource.id,
                              },
                            ),
                          );
                        } catch {
                          reindexed = false;
                        }
                      }
                      await loadPresentation(selectedSlide);
                      if (applied)
                        setNotice(
                          reindexed
                            ? "Saved reviewed evidence footnotes and refreshed retrieval. Review claims on the new revision."
                            : "Saved reviewed evidence footnotes. Reindex before rehearsal and review claims on the new revision.",
                        );
                    }}
                  />
                </>
              ) : null}
            </div>
            <div
              id="pw-panel-history"
              className="pw-studio-panel"
              hidden={inspectorPanel !== "history"}
            >
              {selectedSource &&
              currentRevision &&
              loadedSourceId === selectedSource.id ? (
                <RevisionCheckpoints
                  key={`checkpoint:${project.id}:${selectedSource.id}:${currentRevision.revision_id}`}
                  projectId={project.id}
                  documentId={selectedSource.id}
                  revisionId={currentRevision.revision_id}
                  disabled={loading || voiceWorkflowActive}
                  onRestore={restoreRevision}
                />
              ) : null}
              {fidelityReport ? (
                <section
                  className="pw-fidelity-summary"
                  aria-label="Presentation structure inventory"
                >
                  <strong>Core structure inventory</strong>
                  <span>
                    {fidelityReport.slide_count} slides ·{" "}
                    {fidelityReport.object_count} objects
                  </span>
                  <span>
                    Object types:{" "}
                    {formatObjectKindCounts(fidelityReport.object_kinds)}
                  </span>
                  <span>
                    {fidelityReport.text_edit_candidates} text shape candidates
                    · {fidelityReport.nontext_or_unmodeled_objects} other
                    modeled objects
                  </span>
                  <p>
                    Single-run text replacement, plain-paragraph all-run
                    formatting and alignment, text-box creation, plain notes,
                    bounded object layout and simple picture cropping, certain
                    object deletion and duplication, supported slide deletion
                    and duplication, and slide reordering are writable in this
                    preview. Corpus comparison found visible differences from
                    PowerPoint; review every exported deck in PowerPoint before
                    relying on its layout.
                  </p>
                </section>
              ) : null}
              {revisionHistory ? (
                <section
                  className="pw-fidelity-summary"
                  aria-label="Presentation revision history"
                >
                  <strong>Revision history</strong>
                  {revisionHistory.revisions.map((revision) => (
                    <div className="pw-revision-row" key={revision.revision_id}>
                      <span>
                        {revision.revision_kind === "original"
                          ? "Original import"
                          : "Edited"}{" "}
                        · Revision {revision.revision_number}
                      </span>
                      {!revision.is_current && loadedSourceId ? (
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() =>
                            void restoreRevision(revision.revision_id)
                          }
                          disabled={loading}
                          aria-label={`Restore revision ${revision.revision_number}`}
                        >
                          Restore
                        </button>
                      ) : null}
                    </div>
                  ))}
                  {revisionHistory.has_more ? (
                    <p>Showing the newest 50 revisions.</p>
                  ) : null}
                </section>
              ) : null}
              {loadedSourceId ? (
                <p className="pw-privacy-copy">
                  Saving the current copy exports the selected revision. The
                  original import remains available in revision history.
                </p>
              ) : null}
              <form className="pw-intent-form" onSubmit={recordIntent}>
                <label>
                  Edit intent
                  <select
                    aria-label="Edit intent category"
                    value={intentKind}
                    onChange={(event) =>
                      setIntentKind(event.target.value as IntentKind)
                    }
                  >
                    <option value="text">Text</option>
                    <option value="evidence">Evidence</option>
                    <option value="notes">Speaker notes</option>
                    <option value="layout">Layout or organization</option>
                    <option value="other">Other</option>
                  </select>
                </label>
                <label>
                  What would you ask it to do?
                  <textarea
                    value={intentText}
                    onChange={(event) => setIntentText(event.target.value)}
                    maxLength={1000}
                    rows={3}
                    placeholder="Describe the change you would want…"
                  />
                </label>
                <button
                  type="submit"
                  className="secondary-button"
                  disabled={!intentText.trim()}
                >
                  Record edit intent
                </button>
              </form>
              <p className="pw-privacy-copy">
                Intent counts stay in memory while this view is open. The text
                is discarded, never persisted, and never sent to a provider.
              </p>
              <p className="pw-intent-counts" aria-live="polite">
                {countsText
                  ? `This view: ${countsText}`
                  : "No edit intent recorded yet."}
              </p>
            </div>
            <div
              id="pw-panel-text"
              className="pw-studio-panel"
              hidden={inspectorPanel !== "text"}
            >
              <section
                ref={voiceEditorRef}
                className="pw-mock-edit"
                aria-labelledby="pw-mock-title"
              >
                <p className="eyebrow">TEXT EDIT</p>
                {selectedSource &&
                currentRevision &&
                loadedSourceId === selectedSource.id ? (
                  <SlideEditReview
                    key={`${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${selectedSlide}`}
                    projectId={project.id}
                    documentId={selectedSource.id}
                    revisionId={currentRevision.revision_id}
                    slideNumber={selectedSlide}
                    targets={textTargets}
                    notes={speakerNotesTarget}
                    disabled={loading || voiceWorkflowActive}
                    onRestore={async (applied) => {
                      let indexed = true;
                      if (applied) {
                        try {
                          await requestCore("source.reindex", {
                            project_id: project.id,
                            document_id: selectedSource.id,
                          });
                        } catch {
                          indexed = false;
                        }
                      }
                      await loadPresentation(selectedSlide);
                      if (applied)
                        setNotice(
                          indexed
                            ? "Saved the reviewed changes as one revision and refreshed its slide text for retrieval."
                            : "Saved the reviewed changes. Re-index this presentation before using its edited text in rehearsal.",
                        );
                    }}
                  />
                ) : null}
                <h4 id="pw-mock-title">Preview a text change</h4>
                {textTargets.length ? (
                  <>
                    <p className="muted">
                      {selectedTarget?.uniformRunReplacement
                        ? "Text replacement supports runs only when every run has identical formatting, up to 2,000 characters. Preview the replacement before saving a revision."
                        : selectedTarget?.replaceEditable
                          ? "Text replacement supports one text run up to 2,000 characters. Preview the replacement before saving a revision."
                          : "Text replacement is unavailable for this structure. Formatting controls can apply a direct style to every run in each supported paragraph."}
                    </p>
                    <label>
                      Text on this slide
                      <select
                        value={selectedTargetHandle}
                        onChange={(event) => {
                          const target = textTargets.find(
                            (item) => item.key === event.target.value,
                          );
                          setSelectedTargetHandle(event.target.value);
                          rewriteGeneration.current += 1;
                          setTextRewriteProposal(null);
                          setMockText(
                            target?.text.slice(0, MAX_MOCK_TEXT_CHARS) ?? "",
                          );
                          setTextStyleDraft({
                            highlight_color:
                              target?.style.highlight_color ?? "#FFFF00",
                            font_family: target?.style.font_family ?? "",
                            font_size_pt:
                              target?.style.font_size_pt?.toString() ?? "",
                            font_color: target?.style.font_color ?? "#000000",
                            alignment: target?.style.alignment ?? "",
                            bullet_mode: target?.style.bullet_state ?? "",
                            bullet_color: target?.style.bullet_color ?? "",
                            bullet_size_percent:
                              target?.style.bullet_size_percent?.toString() ??
                              "",
                            numbering_start:
                              target?.style.numbering_start?.toString() ?? "",
                            left_indent_pt:
                              target?.style.left_indent_pt?.toString() ?? "",
                            first_line_indent_pt:
                              target?.style.first_line_indent_pt?.toString() ??
                              "",
                            line_spacing_pt:
                              target?.style.line_spacing_pt?.toString() ?? "",
                            space_before_pt:
                              target?.style.space_before_pt?.toString() ?? "",
                            space_after_pt:
                              target?.style.space_after_pt?.toString() ?? "",
                          });
                          setMockSvg(null);
                        }}
                        disabled={!loadedSourceId || loading}
                      >
                        {textTargets.map((target) => (
                          <option key={target.key} value={target.key}>
                            {target.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Replacement text
                      <textarea
                        aria-label="Replacement text"
                        value={mockText}
                        onChange={(event) => {
                          setMockText(event.target.value);
                          setMockSvg(null);
                        }}
                        maxLength={MAX_MOCK_TEXT_CHARS}
                        rows={3}
                        disabled={
                          !loadedSourceId ||
                          loading ||
                          !selectedTarget?.replaceEditable
                        }
                      />
                    </label>
                    <label>
                      What should change?
                      <textarea
                        aria-label="Rewrite instruction"
                        value={rewriteInstruction}
                        onChange={(event) => {
                          rewriteGeneration.current += 1;
                          setRewriteInstruction(event.target.value);
                          setTextRewriteProposal(null);
                          setRewriteBusy(false);
                        }}
                        maxLength={MAX_REWRITE_INSTRUCTION_CHARS}
                        rows={2}
                        placeholder="Shorten this while keeping the recommendation and numbers."
                        disabled={!loadedSourceId || loading}
                      />
                    </label>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void startVoiceInstruction()}
                      aria-keyshortcuts="Control+Shift+Space"
                      title={`Hold ${PUSH_TO_EDIT_LABEL} in this editor; release to review. Escape cancels.`}
                      disabled={
                        !loadedSourceId ||
                        !currentRevision ||
                        !selectedTarget?.replaceEditable ||
                        loading ||
                        voiceWorkflowActive
                      }
                    >
                      Dictate instruction
                    </button>
                    <p className="muted">
                      Hold <kbd>{PUSH_TO_EDIT_LABEL}</kbd> to dictate. Release
                      to review; Escape or leaving the window cancels an
                      unfinished gesture.
                    </p>
                    {voiceError && !voiceWorkflowActive ? (
                      <p className="error-message" role="alert">
                        {voiceError}
                      </p>
                    ) : null}
                    <p className="pw-privacy-copy">
                      A rewrite sends only the selected text and this
                      instruction to the configured reasoning provider. Project
                      privacy rules apply. Review the suggestion, preview it,
                      and save it to create a revision.
                    </p>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void proposeTextRewrite()}
                      disabled={
                        !loadedSourceId ||
                        !selectedTarget?.replaceEditable ||
                        !rewriteInstruction.trim() ||
                        rewriteInstruction.length >
                          MAX_REWRITE_INSTRUCTION_CHARS ||
                        loading ||
                        rewriteBusy
                      }
                    >
                      {rewriteBusy
                        ? "Preparing suggestion…"
                        : "Suggest rewrite"}
                    </button>
                    {textRewriteProposalMatchesSelection &&
                    textRewriteProposal ? (
                      <fieldset className="pw-rewrite-proposal">
                        <legend>Review rewrite suggestion</legend>
                        <p className="muted">
                          {textRewriteProposal.edit_summary}
                        </p>
                        <p>
                          <strong>Before</strong>
                        </p>
                        <blockquote>
                          {textRewriteProposal.current_text}
                        </blockquote>
                        <p>
                          <strong>Suggested</strong>
                        </p>
                        <blockquote>
                          {textRewriteProposal.replacement_text}
                        </blockquote>
                        <p className="muted">
                          {textRewriteProposal.provider_id} ·{" "}
                          {textRewriteProposal.model_id} ·{" "}
                          {textRewriteProposal.latency_ms} ms · not applied
                        </p>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => {
                            setMockText(textRewriteProposal.replacement_text);
                            setMockSvg(null);
                            setNotice(
                              "Suggestion copied into the editor. Preview it before saving.",
                            );
                          }}
                          disabled={!selectedTarget?.replaceEditable || loading}
                        >
                          Use suggestion in editor
                        </button>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => setTextRewriteProposal(null)}
                          disabled={loading}
                        >
                          Dismiss suggestion
                        </button>
                      </fieldset>
                    ) : null}
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void previewMockText()}
                      disabled={
                        !loadedSourceId ||
                        !selectedTarget?.replaceEditable ||
                        loading
                      }
                    >
                      {loading && loadedSourceId
                        ? "Rendering…"
                        : "Preview replacement"}
                    </button>
                    <button
                      type="button"
                      className="primary-button"
                      onClick={() => void saveTextRevision()}
                      disabled={
                        !loadedSourceId ||
                        !selectedTarget?.replaceEditable ||
                        !canSaveMockTextRevision(
                          hasMockPreview,
                          mockTextLayoutStatus,
                          layoutRiskAcknowledged,
                        ) ||
                        loading
                      }
                    >
                      Save revision
                    </button>
                    {selectedTarget?.style.editable ? (
                      <fieldset className="pw-text-format">
                        <legend>Text formatting</legend>
                        <p className="muted">
                          Text styles apply across every direct run in the
                          supported plain-text shape. Paragraph formatting
                          applies to each simple paragraph. Mixed or inherited
                          text values appear unset.
                        </p>
                        <div className="pw-format-toggles">
                          <button
                            type="button"
                            className="secondary-button"
                            aria-pressed={selectedTarget.style.bold === true}
                            onClick={() =>
                              void saveTextStyleRevision({
                                bold: selectedTarget.style.bold !== true,
                              })
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.fingerprint
                            }
                          >
                            Bold
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            aria-pressed={selectedTarget.style.italic === true}
                            onClick={() =>
                              void saveTextStyleRevision({
                                italic: selectedTarget.style.italic !== true,
                              })
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.fingerprint
                            }
                          >
                            Italic
                          </button>
                          {(
                            [
                              ["underline", "Underline"],
                              ["strikethrough", "Strikethrough"],
                            ] as const
                          ).map(([property, label]) => (
                            <button
                              key={property}
                              type="button"
                              className="secondary-button"
                              aria-pressed={
                                selectedTarget.style[property] === true
                              }
                              onClick={() =>
                                void saveTextStyleRevision({
                                  [property]:
                                    selectedTarget.style[property] !== true,
                                })
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                !selectedTarget.style.fingerprint
                              }
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                        <label>
                          Paragraph alignment
                          <select
                            value={textStyleDraft.alignment}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                alignment: event.target.value,
                              }))
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.alignment_editable
                            }
                          >
                            <option value="">Choose alignment</option>
                            <option value="left">Left</option>
                            <option value="center">Center</option>
                            <option value="right">Right</option>
                            <option value="justify">Justify</option>
                          </select>
                        </label>
                        <label>
                          Bullet style
                          <select
                            value={textStyleDraft.bullet_mode}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                bullet_mode: event.target.value,
                              }))
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.bullet_editable
                            }
                          >
                            <option value="">Keep imported</option>
                            <option value="bullet">Disc · •</option>
                            <option value="bullet_hollow">
                              Hollow circle · ◦
                            </option>
                            <option value="bullet_square">Square · ▪</option>
                            <option value="bullet_dash">Dash · –</option>
                            <option value="numbered">
                              Automatic number · 1.
                            </option>
                            <option value="numbered_paren">
                              Automatic number · 1)
                            </option>
                            <option value="numbered_alpha_lower">
                              Lowercase letter · a.
                            </option>
                            <option value="numbered_alpha_upper">
                              Uppercase letter · A.
                            </option>
                            <option value="numbered_roman_lower">
                              Lowercase roman · i.
                            </option>
                            <option value="numbered_roman_upper">
                              Uppercase roman · I.
                            </option>
                            <option value="none">No bullet</option>
                          </select>
                        </label>
                        <label>
                          Numbering starts at (1–9999)
                          <input
                            type="number"
                            min="1"
                            max="9999"
                            step="1"
                            placeholder="Keep imported"
                            value={textStyleDraft.numbering_start}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                numbering_start: event.target.value,
                              }))
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.numbering_start_editable
                            }
                          />
                        </label>
                        <fieldset
                          className="pw-bullet-marker"
                          aria-label="Bullet marker"
                        >
                          <legend>Bullet marker</legend>
                          <label>
                            Bullet color
                            <input
                              type="color"
                              value={textStyleDraft.bullet_color || "#000000"}
                              onChange={(event) =>
                                setTextStyleDraft((current) => ({
                                  ...current,
                                  bullet_color:
                                    event.target.value.toUpperCase(),
                                }))
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                !selectedTarget.style.bullet_color_editable
                              }
                            />
                          </label>
                          <label>
                            Bullet size (% of text, 25–400)
                            <input
                              type="number"
                              min="25"
                              max="400"
                              step="5"
                              placeholder="Keep imported"
                              value={textStyleDraft.bullet_size_percent}
                              onChange={(event) =>
                                setTextStyleDraft((current) => ({
                                  ...current,
                                  bullet_size_percent: event.target.value,
                                }))
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                !selectedTarget.style.bullet_size_editable
                              }
                            />
                          </label>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() =>
                              void saveTextStyleRevision(
                                replacementBulletMarker,
                              )
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.fingerprint ||
                              invalidBulletSize ||
                              Object.keys(replacementBulletMarker).length === 0
                            }
                          >
                            Apply bullet marker
                          </button>
                          {!selectedTarget.style.bullet_color_editable ? (
                            <p className="muted">
                              This list uses a bullet font, picture or theme
                              color that stays read-only here.
                            </p>
                          ) : null}
                        </fieldset>
                        <label>
                          Left indent (points, 0–144)
                          <input
                            type="number"
                            min="0"
                            max={MAX_TEXT_LEFT_INDENT_PT}
                            step="1"
                            value={textStyleDraft.left_indent_pt}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                left_indent_pt: event.target.value,
                              }))
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.left_indent_editable
                            }
                          />
                        </label>
                        <label>
                          First-line / hanging indent (points, -144–144)
                          <input
                            type="number"
                            min={-MAX_TEXT_FIRST_LINE_INDENT_PT}
                            max={MAX_TEXT_FIRST_LINE_INDENT_PT}
                            step="1"
                            value={textStyleDraft.first_line_indent_pt}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                first_line_indent_pt: event.target.value,
                              }))
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.first_line_indent_editable
                            }
                          />
                        </label>
                        <label>
                          Line spacing (points, 1–144)
                          <input
                            type="number"
                            min="1"
                            max={MAX_TEXT_LINE_SPACING_PT}
                            step="1"
                            value={textStyleDraft.line_spacing_pt}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                line_spacing_pt: event.target.value,
                              }))
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.line_spacing_editable
                            }
                          />
                        </label>
                        <label>
                          Space before (points, 0–144)
                          <input
                            type="number"
                            min="0"
                            max={MAX_TEXT_PARAGRAPH_SPACING_PT}
                            step="1"
                            value={textStyleDraft.space_before_pt}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                space_before_pt: event.target.value,
                              }))
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.space_before_editable
                            }
                          />
                        </label>
                        <label>
                          Space after (points, 0–144)
                          <input
                            type="number"
                            min="0"
                            max={MAX_TEXT_PARAGRAPH_SPACING_PT}
                            step="1"
                            value={textStyleDraft.space_after_pt}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                space_after_pt: event.target.value,
                              }))
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.space_after_editable
                            }
                          />
                        </label>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() =>
                            void saveTextStyleRevision(
                              replacementTextParagraphStyle,
                            )
                          }
                          disabled={
                            !loadedSourceId ||
                            loading ||
                            !selectedTarget.style.fingerprint ||
                            invalidTextBulletMode ||
                            invalidNumberingStart ||
                            invalidTextLeftIndent ||
                            invalidTextFirstLineIndent ||
                            invalidTextParagraphSpacing ||
                            !Object.keys(replacementTextParagraphStyle).length
                          }
                        >
                          Apply paragraph format
                        </button>
                        {selectedTextLink ? (
                          <div className="pw-shape-color-control">
                            <label>
                              Link (http, https or mailto)
                              <input
                                type="url"
                                maxLength={2048}
                                placeholder="https://example.com"
                                aria-label="Text link"
                                value={linkValue}
                                onChange={(event) =>
                                  setLinkDraft({
                                    objectId: selectedTarget.object_id,
                                    value: event.target.value,
                                  })
                                }
                                disabled={!loadedSourceId || loading}
                              />
                            </label>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                void saveTextHyperlinkRevision(linkValue)
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                !validHyperlinkUrl(linkValue) ||
                                linkValue === selectedTextLink.url
                              }
                            >
                              Apply link
                            </button>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                void saveTextHyperlinkRevision(null)
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                (selectedTextLink.url === null &&
                                  !selectedTextLink.slide_id)
                              }
                            >
                              Remove link
                            </button>
                            <label>
                              Or link to slide
                              <select
                                aria-label="Link to slide"
                                value={selectedTextLink.slide_id ?? ""}
                                onChange={(event) =>
                                  event.target.value &&
                                  void saveTextHyperlinkRevision(
                                    null,
                                    event.target.value,
                                  )
                                }
                                disabled={!loadedSourceId || loading}
                              >
                                <option value="">Choose a slide</option>
                                {fidelityReport?.slides.map((slide) => (
                                  <option
                                    key={slide.slide_id}
                                    value={slide.slide_id}
                                  >
                                    Slide {slide.ordinal}
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>
                        ) : selectedTextObject ? (
                          <p className="muted">
                            This text uses mixed, action or hover links that
                            stay read-only.
                          </p>
                        ) : null}
                        <div className="pw-shape-color-control">
                          <label>
                            Highlight color
                            <input
                              type="color"
                              aria-label="Text highlight color"
                              value={textStyleDraft.highlight_color}
                              onChange={(event) =>
                                setTextStyleDraft((current) => ({
                                  ...current,
                                  highlight_color:
                                    event.target.value.toUpperCase(),
                                }))
                              }
                              disabled={!loadedSourceId || loading}
                            />
                          </label>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() =>
                              void saveTextStyleRevision({
                                highlight_color: textStyleDraft.highlight_color,
                              })
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.fingerprint ||
                              textStyleDraft.highlight_color ===
                                selectedTarget.style.highlight_color
                            }
                          >
                            Apply highlight
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() =>
                              void saveTextStyleRevision({
                                highlight_color: "none",
                              })
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.fingerprint ||
                              !selectedTarget.style.highlight_color
                            }
                          >
                            Remove highlight
                          </button>
                        </div>
                        <div className="pw-shape-color-control">
                          <label>
                            Vertical alignment
                            <select
                              aria-label="Text vertical alignment"
                              value={selectedTarget.style.vertical_anchor ?? ""}
                              onChange={(event) =>
                                event.target.value &&
                                void saveTextStyleRevision({
                                  vertical_anchor: event.target.value as
                                    "top" | "middle" | "bottom",
                                })
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                !selectedTarget.style.fingerprint
                              }
                            >
                              <option value="">Inherited</option>
                              <option value="top">Top</option>
                              <option value="middle">Middle</option>
                              <option value="bottom">Bottom</option>
                            </select>
                          </label>
                          <label>
                            Columns
                            <select
                              aria-label="Text columns"
                              value={String(selectedTarget.style.columns ?? 1)}
                              onChange={(event) =>
                                void saveTextStyleRevision({
                                  columns: Number(event.target.value),
                                })
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                !selectedTarget.style.fingerprint
                              }
                            >
                              <option value="1">1</option>
                              <option value="2">2</option>
                              <option value="3">3</option>
                            </select>
                          </label>
                        </div>
                        <label>
                          Font (theme: +mn-lt body, +mj-lt headings)
                          <input
                            type="text"
                            list="pw-font-family-suggestions"
                            maxLength={31}
                            placeholder="Mixed or inherited"
                            aria-label="Font family"
                            value={textStyleDraft.font_family}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                font_family: event.target.value,
                              }))
                            }
                            disabled={!loadedSourceId || loading}
                          />
                          <datalist id="pw-font-family-suggestions">
                            {FONT_FAMILY_SUGGESTIONS.map((font) => (
                              <option key={font} value={font} />
                            ))}
                          </datalist>
                        </label>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() =>
                            void saveTextStyleRevision({
                              font_family: textStyleDraft.font_family,
                            })
                          }
                          disabled={
                            !loadedSourceId ||
                            loading ||
                            !selectedTarget.style.fingerprint ||
                            !validFontFamily(textStyleDraft.font_family) ||
                            textStyleDraft.font_family ===
                              selectedTarget.style.font_family
                          }
                        >
                          Apply font
                        </button>
                        <label>
                          Font size (points, 6–96)
                          <input
                            type="number"
                            min="6"
                            max="96"
                            step="1"
                            value={textStyleDraft.font_size_pt}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                font_size_pt: event.target.value,
                              }))
                            }
                            disabled={!loadedSourceId || loading}
                          />
                        </label>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() =>
                            replacementTextFontSize !== null &&
                            void saveTextStyleRevision({
                              font_size_pt: replacementTextFontSize,
                            })
                          }
                          disabled={
                            !loadedSourceId ||
                            loading ||
                            !selectedTarget.style.fingerprint ||
                            replacementTextFontSize === null ||
                            replacementTextFontSize < 6 ||
                            replacementTextFontSize > 96
                          }
                        >
                          Apply font size
                        </button>
                        <label>
                          Text color
                          <input
                            type="color"
                            value={textStyleDraft.font_color}
                            onChange={(event) =>
                              setTextStyleDraft((current) => ({
                                ...current,
                                font_color: event.target.value.toUpperCase(),
                              }))
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              !selectedTarget.style.color_editable
                            }
                          />
                        </label>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() =>
                            void saveTextStyleRevision({
                              font_color: textStyleDraft.font_color,
                            })
                          }
                          disabled={
                            !loadedSourceId ||
                            loading ||
                            !selectedTarget.style.fingerprint ||
                            !selectedTarget.style.color_editable
                          }
                        >
                          Apply text color
                        </button>
                        {!selectedTarget.style.color_editable ? (
                          <p className="muted">
                            At least one run has unsupported color fills and
                            stays read-only for color changes.
                          </p>
                        ) : null}
                      </fieldset>
                    ) : null}
                    {mockUrl ? (
                      <figure className="pw-mock-result">
                        <figcaption>Text edit preview · not saved</figcaption>
                        <img
                          src={mockUrl}
                          alt={`Text edit preview on slide ${selectedSlide}`}
                        />
                      </figure>
                    ) : null}
                    {mockUrl && mockTextLayoutStatus === "overflow" ? (
                      <div className="pw-layout-warning" role="alert">
                        <p>
                          The preview renderer shows text extending beyond the
                          selected text box. Check for overlap before saving;
                          PowerPoint may lay out the slide differently.
                        </p>
                        <label>
                          <input
                            type="checkbox"
                            checked={layoutRiskAcknowledged}
                            onChange={(event) =>
                              setLayoutRiskAcknowledged(event.target.checked)
                            }
                          />
                          <span>
                            I reviewed this overflow and want to save the
                            revision.
                          </span>
                        </label>
                      </div>
                    ) : null}
                    {mockUrl && mockTextLayoutStatus === "unknown" ? (
                      <p className="muted" role="status">
                        Text overflow could not be checked reliably for this
                        preview. Inspect the slide closely; PowerPoint may lay
                        it out differently.
                      </p>
                    ) : null}
                    {mockUrl && mockTextLayoutStatus === "fits" ? (
                      <p className="muted" role="status">
                        The preview renderer did not detect text outside the
                        selected box. PowerPoint may still lay it out
                        differently.
                      </p>
                    ) : null}
                  </>
                ) : (
                  <p className="muted">
                    Open a slide with supported text to try a mock change.
                  </p>
                )}
              </section>
            </div>
            <div
              id="pw-panel-objects"
              className="pw-studio-panel"
              hidden={inspectorPanel !== "objects"}
            >
              <section
                className="pw-object-edit"
                aria-labelledby="pw-object-edit-title"
              >
                <p className="eyebrow">OBJECT EDITING</p>
                <h4 id="pw-object-edit-title">Edit an object</h4>
                {selectedSource &&
                currentRevision &&
                loadedSourceId === selectedSource.id ? (
                  <SlideEditReview
                    key={`layout:${project.id}:${selectedSource.id}:${currentRevision.revision_id}:${selectedSlide}`}
                    projectId={project.id}
                    documentId={selectedSource.id}
                    revisionId={currentRevision.revision_id}
                    slideNumber={selectedSlide}
                    slideId={activeSlideId}
                    targets={[]}
                    notes={null}
                    layoutObjects={workspaceObjects}
                    initialSelectedIds={canvasSelectedIds}
                    actionRequest={pendingObjectAction}
                    onActionHandled={() => setPendingObjectAction(null)}
                    pasteRequest={pendingObjectPaste}
                    onPasteHandled={() => setPendingObjectPaste(null)}
                    moveRequest={pendingCanvasMove}
                    onMoveHandled={() => setPendingCanvasMove(null)}
                    disabled={loading || voiceWorkflowActive}
                    onRestore={async (
                      applied,
                      pastedIds,
                      pastedRevisionId,
                      action,
                    ) => {
                      if (
                        applied &&
                        pastedIds?.length &&
                        pastedRevisionId &&
                        UUID_PATTERN.test(pastedRevisionId)
                      ) {
                        restoredCanvasSelection.current = {
                          slideId: activeSlideId,
                          documentId: selectedSource.id,
                          revisionId: pastedRevisionId,
                          ids: pastedIds,
                        };
                      }
                      if (
                        !applied &&
                        canvasSelectionEnabled &&
                        canvasSelectedIds.length
                      ) {
                        restoredCanvasSelection.current = {
                          slideId: activeSlideId,
                          documentId: selectedSource.id,
                          revisionId: currentRevision.revision_id,
                          ids: canvasSelectedIds,
                        };
                      }
                      let indexed = true;
                      if (applied) {
                        try {
                          await requestCore("source.reindex", {
                            project_id: project.id,
                            document_id: selectedSource.id,
                          });
                        } catch {
                          indexed = false;
                        }
                      }
                      await loadPresentation(
                        selectedSlide,
                        pastedIds?.[0] ?? selectedObjectId,
                      );
                      if (applied) {
                        const savedMessage =
                          action === "group"
                            ? "Grouped the reviewed objects"
                            : action === "ungroup"
                              ? "Ungrouped the reviewed objects"
                              : action === "duplicate"
                                ? "Duplicated the reviewed objects"
                                : action === "delete"
                                  ? "Deleted the reviewed objects"
                                  : action === "paste"
                                    ? "Pasted the reviewed objects"
                                    : "Saved the reviewed object layout";
                        setNotice(
                          indexed
                            ? `${savedMessage} as one revision.`
                            : `${savedMessage}. Re-index this presentation before rehearsal.`,
                        );
                      }
                    }}
                  />
                ) : null}
                <p className="muted">
                  Move or resize a supported top-level shape, picture, chart or
                  table, or crop a supported embedded picture inside its current
                  frame. Eligible shapes and pictures can be duplicated or
                  removed when they have no placeholder, connector, or animation
                  dependency. Changes save as a new revision.
                </p>
                <fieldset className="pw-picture-crop">
                  <legend>Add video or audio</legend>
                  <p className="muted">
                    MP4 video or MP3, M4A or WAV audio, embedded in the deck.
                    The preview shows the first frame; it plays in PowerPoint.
                  </p>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={
                      loading ||
                      voiceWorkflowActive ||
                      !currentRevision ||
                      !UUID_PATTERN.test(activeSlideId)
                    }
                    onClick={() => void insertMedia()}
                  >
                    Insert video or audio…
                  </button>
                </fieldset>
                <fieldset className="pw-picture-crop">
                  <legend>Add a picture</legend>
                  {selectedSource && currentRevision && slideSizeEmu ? (
                    <>
                      <DeckPictureAssets
                        key={`assets:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                        onBusyChange={setDeckPictureBusy}
                        projectId={project.id}
                        documentId={selectedSource.id}
                        revisionId={currentRevision.revision_id}
                        disabled={
                          loading || voiceWorkflowActive || projectPictureBusy
                        }
                        onUse={async (file) => {
                          const epoch = generation.current;
                          const size = slideSizeEmu;
                          const bitmap = await createImageBitmap(file);
                          try {
                            if (generation.current !== epoch) return;
                            const geometry = fitPictureGeometry(
                              bitmap.width,
                              bitmap.height,
                              size.width,
                              size.height,
                            );
                            if (newPictureInput.current)
                              newPictureInput.current.value = "";
                            setNewPictureFile(file);
                            setNewPictureGeometryBase(geometry);
                            setNewPictureGeometryDraft(geometryDraft(geometry));
                            setNewPictureAltText("");
                            setError(null);
                          } finally {
                            bitmap.close();
                          }
                        }}
                      />
                      <DeckPictureAssets
                        source="project"
                        key={`project-assets:${selectedSource.id}:${currentRevision.revision_id}:${activeSlideId}`}
                        onBusyChange={setProjectPictureBusy}
                        projectId={project.id}
                        documentId={selectedSource.id}
                        revisionId={currentRevision.revision_id}
                        disabled={
                          loading || voiceWorkflowActive || deckPictureBusy
                        }
                        onUse={async (file) => {
                          const epoch = generation.current;
                          const size = slideSizeEmu;
                          const bitmap = await createImageBitmap(file);
                          try {
                            if (generation.current !== epoch) return;
                            const geometry = fitPictureGeometry(
                              bitmap.width,
                              bitmap.height,
                              size.width,
                              size.height,
                            );
                            if (newPictureInput.current)
                              newPictureInput.current.value = "";
                            setNewPictureFile(file);
                            setNewPictureGeometryBase(geometry);
                            setNewPictureGeometryDraft(geometryDraft(geometry));
                            setNewPictureAltText("");
                            setError(null);
                          } finally {
                            bitmap.close();
                          }
                        }}
                      />
                    </>
                  ) : null}
                  <label>
                    Picture file (PNG or JPEG, up to 4 MiB)
                    <input
                      ref={newPictureInput}
                      type="file"
                      accept="image/png,image/jpeg"
                      aria-label="Picture to add"
                      onChange={(event) => {
                        const input = event.currentTarget;
                        const file = input.files?.[0] ?? null;
                        setNewPictureFile(null);
                        setNewPictureGeometryBase(null);
                        setNewPictureGeometryDraft({
                          x: "",
                          y: "",
                          width: "",
                          height: "",
                        });
                        if (!file) return;
                        if (
                          file.size < 1 ||
                          file.size > MAX_REPLACEMENT_IMAGE_BYTES
                        ) {
                          input.value = "";
                          setError("Choose an image no larger than 4 MiB.");
                          return;
                        }
                        if (!["image/png", "image/jpeg"].includes(file.type)) {
                          input.value = "";
                          setError("Choose a PNG or JPEG image.");
                          return;
                        }
                        if (!slideSizeEmu) {
                          input.value = "";
                          setError("Load a slide before adding a picture.");
                          return;
                        }
                        const slideSize = slideSizeEmu;
                        const selectionGeneration = generation.current;
                        void (async () => {
                          let bitmap: ImageBitmap | null = null;
                          try {
                            bitmap = await createImageBitmap(file);
                            if (generation.current !== selectionGeneration)
                              return;
                            const geometry = fitPictureGeometry(
                              bitmap.width,
                              bitmap.height,
                              slideSize.width,
                              slideSize.height,
                            );
                            setNewPictureFile(file);
                            setNewPictureGeometryBase(geometry);
                            setNewPictureGeometryDraft(geometryDraft(geometry));
                            setError(null);
                          } catch {
                            input.value = "";
                            setNewPictureFile(null);
                            setError(
                              "The selected image could not be decoded.",
                            );
                          } finally {
                            bitmap?.close();
                          }
                        })();
                      }}
                      disabled={!loadedSourceId || loading || pictureAssetBusy}
                    />
                  </label>
                  {newPictureFile ? (
                    <p className="muted">
                      Selected: {newPictureFile.name} ·{" "}
                      {Math.ceil(newPictureFile.size / 1024)} KiB
                    </p>
                  ) : null}
                  <label>
                    Alternative text (optional)
                    <input
                      type="text"
                      value={newPictureAltText}
                      onChange={(event) =>
                        setNewPictureAltText(event.target.value)
                      }
                      maxLength={2_000}
                      disabled={!newPictureFile || loading || pictureAssetBusy}
                    />
                  </label>
                  <p className="muted">
                    Initial placement fits the image within half the slide while
                    keeping its proportions. Adjust the position and size below.
                  </p>
                  <div className="pw-geometry-fields">
                    {(
                      [
                        ["x", "X position (inches)"],
                        ["y", "Y position (inches)"],
                        ["width", "Width (inches)"],
                        ["height", "Height (inches)"],
                      ] as const
                    ).map(([field, label]) => (
                      <label key={field}>
                        {label}
                        <input
                          type="number"
                          min="0"
                          step="0.001"
                          aria-label={`New picture ${label}`}
                          value={newPictureGeometryDraft[field]}
                          onChange={(event) =>
                            setNewPictureGeometryDraft((current) => ({
                              ...current,
                              [field]: event.target.value,
                            }))
                          }
                          disabled={
                            !newPictureFile || loading || pictureAssetBusy
                          }
                        />
                      </label>
                    ))}
                  </div>
                  {newPictureFile && newPictureGeometry === null ? (
                    <p className="muted" role="alert">
                      Enter positive dimensions that keep the whole picture
                      inside the slide.
                    </p>
                  ) : null}
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => void createPictureRevision()}
                    disabled={
                      !loadedSourceId ||
                      loading ||
                      pictureAssetBusy ||
                      !newPictureFile ||
                      !newPictureGeometry
                    }
                  >
                    Add picture
                  </button>
                </fieldset>
                <fieldset className="pw-picture-crop">
                  <legend>Add a shape</legend>
                  <label>
                    Shape type
                    <select
                      aria-label="New shape type"
                      value={newShapeType}
                      onChange={(event) =>
                        setNewShapeType(event.target.value as NewShapeType)
                      }
                      disabled={!loadedSourceId || loading}
                    >
                      <option value="rect">Rectangle</option>
                      <option value="ellipse">Ellipse</option>
                    </select>
                  </label>
                  <div className="pw-shape-color-control">
                    <label>
                      Fill color
                      <input
                        type="color"
                        aria-label="New shape fill color"
                        value={newShapeFillColor}
                        onChange={(event) =>
                          setNewShapeFillColor(event.target.value.toUpperCase())
                        }
                        disabled={!loadedSourceId || loading}
                      />
                    </label>
                    <label>
                      Outline color
                      <input
                        type="color"
                        aria-label="New shape outline color"
                        value={newShapeLineColor}
                        onChange={(event) =>
                          setNewShapeLineColor(event.target.value.toUpperCase())
                        }
                        disabled={!loadedSourceId || loading}
                      />
                    </label>
                  </div>
                  <p className="muted">
                    Initial placement is centered. Set the position and size
                    before adding the shape.
                  </p>
                  <div className="pw-geometry-fields">
                    {(
                      [
                        ["x", "X position (inches)"],
                        ["y", "Y position (inches)"],
                        ["width", "Width (inches)"],
                        ["height", "Height (inches)"],
                      ] as const
                    ).map(([field, label]) => (
                      <label key={field}>
                        {label}
                        <input
                          type="number"
                          min="0"
                          step="0.001"
                          aria-label={"New shape " + label}
                          value={newShapeGeometryDraft[field]}
                          onChange={(event) =>
                            setNewShapeGeometryDraft((current) => ({
                              ...current,
                              [field]: event.target.value,
                            }))
                          }
                          disabled={!loadedSourceId || loading}
                        />
                      </label>
                    ))}
                  </div>
                  {newShapeGeometry === null ? (
                    <p className="muted" role="alert">
                      Enter positive dimensions that keep the whole shape inside
                      the slide.
                    </p>
                  ) : null}
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => void createShapeRevision()}
                    disabled={!loadedSourceId || loading || !newShapeGeometry}
                  >
                    Add shape
                  </button>
                </fieldset>
                <label>
                  New text box text
                  <input
                    type="text"
                    value={newTextBoxDraft}
                    onChange={(event) => setNewTextBoxDraft(event.target.value)}
                    maxLength={MAX_MOCK_TEXT_CHARS}
                    disabled={
                      !loadedSourceId ||
                      loading ||
                      !UUID_PATTERN.test(activeSlideId)
                    }
                  />
                </label>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void createTextBoxRevision()}
                  disabled={
                    !loadedSourceId ||
                    loading ||
                    !UUID_PATTERN.test(activeSlideId) ||
                    !newTextBoxDraft.trim()
                  }
                >
                  Add text box
                </button>
                {slideBackground ? (
                  <fieldset className="pw-picture-crop">
                    <legend>Slide background</legend>
                    {slideBackground.editable ? (
                      <>
                        <p className="muted">
                          {slideBackground.state === "solid"
                            ? `This slide uses its own color ${slideBackground.color}.`
                            : slideBackground.state === "theme_reference"
                              ? "This slide uses a theme background style."
                              : "This slide uses its layout background."}
                        </p>
                        <div className="pw-shape-color-control">
                          <label>
                            Background color
                            <input
                              type="color"
                              aria-label="Slide background color"
                              value={slideBackgroundDraft}
                              onChange={(event) =>
                                setSlideBackgroundDraft(
                                  event.target.value.toUpperCase(),
                                )
                              }
                              disabled={!loadedSourceId || loading}
                            />
                          </label>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() =>
                              void saveSlideBackgroundRevision(
                                slideBackgroundDraft,
                              )
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              slideBackgroundDraft === slideBackground.color
                            }
                          >
                            Apply background color
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() =>
                              void saveSlideBackgroundRevision(null)
                            }
                            disabled={
                              !loadedSourceId ||
                              loading ||
                              slideBackground.state === "inherited"
                            }
                          >
                            Use layout background
                          </button>
                        </div>
                      </>
                    ) : (
                      <p className="muted">
                        This slide uses a picture, gradient or pattern
                        background that stays read-only.
                      </p>
                    )}
                  </fieldset>
                ) : null}
                {workspaceObjects.length ? (
                  <>
                    <label>
                      Object on this slide
                      <select
                        aria-label="Object to edit"
                        value={selectedObjectId}
                        onChange={(event) => {
                          const object = workspaceObjects.find(
                            (candidate) =>
                              candidate.object_id === event.target.value,
                          );
                          setSelectedObjectId(event.target.value);
                          setDeleteConfirmationObjectId("");
                          setObjectGeometryDraft(
                            object?.geometry
                              ? geometryDraft(object.geometry)
                              : { x: "", y: "", width: "", height: "" },
                          );
                          setObjectCropDraft(
                            pictureCropDraft(object?.picture_crop ?? null),
                          );
                          setObjectAdjustmentDraft(
                            pictureAdjustmentDraft(object?.picture_adjustment),
                          );
                          setObjectRotationDraft(
                            objectRotationDraft(object?.rotation),
                          );
                          setObjectStyleDraft(
                            draftForShapeStyle(object?.shape_style ?? null),
                          );
                        }}
                        disabled={!loadedSourceId || loading}
                      >
                        <option value="">Choose an object</option>
                        {workspaceObjects.map((object) => (
                          <option
                            key={object.object_id}
                            value={object.object_id}
                          >
                            {object.name} · {object.kind}
                            {object.geometry_editable
                              ? " · editable"
                              : " · read-only"}
                          </option>
                        ))}
                      </select>
                    </label>
                    {selectedObject?.click_action ? (
                      <ClickActionEditor
                        objectId={selectedObject.object_id}
                        action={selectedObject.click_action}
                        slides={fidelityReport?.slides ?? []}
                        disabled={loading || !currentRevision}
                        onApply={(action) => void saveClickAction(action)}
                      />
                    ) : null}
                    {selectedObject &&
                    typeof selectedObject.alt_text === "string" ? (
                      <AltTextEditor
                        objectId={selectedObject.object_id}
                        altText={selectedObject.alt_text}
                        decorative={selectedObject.decorative === true}
                        disabled={loading || !currentRevision}
                        onApply={(text, decorative) =>
                          void saveAltText(text, decorative)
                        }
                      />
                    ) : null}
                    {selectedObject?.geometry_editable &&
                    selectedObject.geometry ? (
                      <>
                        <fieldset>
                          <legend>Object layer</legend>
                          <p className="muted">
                            Later objects appear in front. Move the selected
                            object without changing its contents.
                          </p>
                          {(
                            [
                              ["forward", "Bring forward"],
                              ["backward", "Send backward"],
                              ["front", "Bring to front"],
                              ["back", "Send to back"],
                            ] as const
                          ).map(([direction, label]) => (
                            <button
                              key={direction}
                              type="button"
                              className="secondary-button"
                              disabled={
                                loading || !selectedObject.delete_editable
                              }
                              onClick={() => void changeObjectLayer(direction)}
                            >
                              {label}
                            </button>
                          ))}
                        </fieldset>
                        <div className="pw-geometry-fields">
                          {(
                            [
                              ["x", "X position (inches)"],
                              ["y", "Y position (inches)"],
                              ["width", "Width (inches)"],
                              ["height", "Height (inches)"],
                            ] as const
                          ).map(([field, label]) => (
                            <label key={field}>
                              {label}
                              <input
                                type="number"
                                min="0"
                                step="0.001"
                                aria-label={label}
                                value={objectGeometryDraft[field]}
                                onChange={(event) =>
                                  setObjectGeometryDraft((current) => ({
                                    ...current,
                                    [field]: event.target.value,
                                  }))
                                }
                                disabled={!loadedSourceId || loading}
                              />
                            </label>
                          ))}
                        </div>
                        {replacementObjectGeometry === null ? (
                          <p className="muted" role="alert">
                            Enter positive dimensions that keep the whole object
                            inside the slide.
                          </p>
                        ) : null}
                        <button
                          type="button"
                          className="primary-button"
                          onClick={() => void saveObjectGeometryRevision()}
                          disabled={
                            !loadedSourceId ||
                            loading ||
                            !replacementObjectGeometry ||
                            sameGeometry(
                              selectedObject.geometry,
                              replacementObjectGeometry,
                            )
                          }
                        >
                          {selectedObject.kind === "graphicFrame"
                            ? "Review object layout"
                            : "Save object layout"}
                        </button>
                        {selectedObject.rotation ? (
                          <fieldset className="pw-picture-crop">
                            <legend>Rotate and flip</legend>
                            <p className="muted">
                              Rotation is clockwise around the object&apos;s
                              center; position and size stay the same.
                            </p>
                            <div className="pw-geometry-fields">
                              <label>
                                Rotation (degrees)
                                <input
                                  type="number"
                                  min="0"
                                  max="359.99"
                                  step="0.01"
                                  aria-label="Object rotation (degrees)"
                                  value={
                                    objectRotationDraftState.rotation_degrees
                                  }
                                  onChange={(event) =>
                                    setObjectRotationDraft((current) => ({
                                      ...current,
                                      rotation_degrees: event.target.value,
                                    }))
                                  }
                                  disabled={!loadedSourceId || loading}
                                />
                              </label>
                            </div>
                            <div className="pw-shape-color-control">
                              {(
                                [
                                  [-90, "Rotate left 90°"],
                                  [90, "Rotate right 90°"],
                                ] as const
                              ).map(([delta, label]) => (
                                <button
                                  key={label}
                                  type="button"
                                  className="secondary-button"
                                  onClick={() =>
                                    setObjectRotationDraft((current) => {
                                      const value =
                                        Number(current.rotation_degrees) || 0;
                                      return {
                                        ...current,
                                        rotation_degrees: String(
                                          Math.round(
                                            ((((value + delta) % 360) + 360) %
                                              360) *
                                              100,
                                          ) / 100,
                                        ),
                                      };
                                    })
                                  }
                                  disabled={!loadedSourceId || loading}
                                >
                                  {label}
                                </button>
                              ))}
                            </div>
                            {(
                              [
                                ["flip_horizontal", "Flip horizontally"],
                                ["flip_vertical", "Flip vertically"],
                              ] as const
                            ).map(([field, label]) => (
                              <label key={field} className="checkbox-row">
                                <input
                                  type="checkbox"
                                  aria-label={label}
                                  checked={objectRotationDraftState[field]}
                                  onChange={(event) =>
                                    setObjectRotationDraft((current) => ({
                                      ...current,
                                      [field]: event.target.checked,
                                    }))
                                  }
                                  disabled={!loadedSourceId || loading}
                                />
                                {label}
                              </label>
                            ))}
                            {replacementObjectRotation === null ? (
                              <p className="muted" role="alert">
                                Enter a rotation in degrees.
                              </p>
                            ) : null}
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() => void saveObjectRotationRevision()}
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                !replacementObjectRotation ||
                                sameObjectRotation(
                                  selectedObject.rotation,
                                  replacementObjectRotation,
                                )
                              }
                            >
                              Apply rotation
                            </button>
                          </fieldset>
                        ) : null}
                        {selectedObject.kind === "pic" ? (
                          selectedObject.picture_crop ? (
                            <>
                              <fieldset className="pw-picture-crop">
                                <legend>Picture crop</legend>
                                <p className="muted">
                                  Crop the image inside its existing frame.
                                  Values are percentages from each edge.
                                </p>
                                <div className="pw-geometry-fields">
                                  {(
                                    [
                                      ["left_percent", "Left crop (%)"],
                                      ["right_percent", "Right crop (%)"],
                                      ["top_percent", "Top crop (%)"],
                                      ["bottom_percent", "Bottom crop (%)"],
                                    ] as const
                                  ).map(([field, label]) => (
                                    <label key={field}>
                                      {label}
                                      <input
                                        type="number"
                                        min="0"
                                        max="99.999"
                                        step="0.001"
                                        aria-label={label}
                                        value={objectCropDraft[field]}
                                        onChange={(event) =>
                                          setObjectCropDraft((current) => ({
                                            ...current,
                                            [field]: event.target.value,
                                          }))
                                        }
                                        disabled={!loadedSourceId || loading}
                                      />
                                    </label>
                                  ))}
                                </div>
                                {replacementPictureCrop === null ? (
                                  <p className="muted" role="alert">
                                    Leave a visible portion of the image in both
                                    directions and use increments of 0.001%.
                                  </p>
                                ) : null}
                                <button
                                  type="button"
                                  className="secondary-button"
                                  onClick={() => void savePictureCropRevision()}
                                  disabled={
                                    !loadedSourceId ||
                                    loading ||
                                    !replacementPictureCrop ||
                                    samePictureCrop(
                                      selectedObject.picture_crop,
                                      replacementPictureCrop ??
                                        selectedObject.picture_crop,
                                    )
                                  }
                                >
                                  Save picture crop
                                </button>
                                <label>
                                  Replace picture image (PNG or JPEG, up to 4
                                  MiB)
                                  <input
                                    ref={replacementPictureInput}
                                    type="file"
                                    accept="image/png,image/jpeg"
                                    aria-label="Replacement picture image"
                                    onChange={(event) => {
                                      const file =
                                        event.currentTarget.files?.[0] ?? null;
                                      setReplacementPictureFile(null);
                                      if (!file) return;
                                      if (
                                        file.size < 1 ||
                                        file.size > MAX_REPLACEMENT_IMAGE_BYTES
                                      ) {
                                        event.currentTarget.value = "";
                                        setError(
                                          "Choose an image no larger than 4 MiB.",
                                        );
                                        return;
                                      }
                                      if (
                                        !["image/png", "image/jpeg"].includes(
                                          file.type,
                                        )
                                      ) {
                                        event.currentTarget.value = "";
                                        setError("Choose a PNG or JPEG image.");
                                        return;
                                      }
                                      setError(null);
                                      setReplacementPictureFile(file);
                                    }}
                                    disabled={!loadedSourceId || loading}
                                  />
                                </label>
                                {replacementPictureFile ? (
                                  <p className="muted">
                                    Selected: {replacementPictureFile.name} ·{" "}
                                    {Math.ceil(
                                      replacementPictureFile.size / 1024,
                                    )}{" "}
                                    KiB
                                  </p>
                                ) : null}
                                <button
                                  type="button"
                                  className="secondary-button"
                                  onClick={() =>
                                    void replacePictureImageRevision()
                                  }
                                  disabled={
                                    !loadedSourceId ||
                                    loading ||
                                    !replacementPictureFile
                                  }
                                >
                                  Replace picture image
                                </button>
                              </fieldset>
                              {renderPictureAdjustment(selectedObject)}
                            </>
                          ) : (
                            <p className="muted">
                              This picture uses a fill or relationship structure
                              that the crop editor cannot safely rewrite.
                            </p>
                          )
                        ) : null}
                      </>
                    ) : selectedObject ? (
                      <>
                        <p className="muted">
                          This object is preserved but does not have a supported
                          slide-level transform.
                        </p>
                        {selectedObject.kind === "pic" &&
                        selectedObject.picture_adjustment
                          ? renderPictureAdjustment(selectedObject)
                          : null}
                      </>
                    ) : (
                      <p className="muted">
                        Select an object with supported geometry to edit it.
                      </p>
                    )}
                    {selectedObject?.shape_style?.editable ? (
                      <fieldset className="pw-picture-crop">
                        <legend>Shape fill and outline</legend>
                        <p className="muted">
                          Set direct RGB colors on supported shapes. Each color
                          saves as its own revision and preserves other shape
                          styling.
                        </p>
                        {selectedObject.shape_style.fill_editable ? (
                          <div className="pw-shape-color-control">
                            <label>
                              Fill color
                              <input
                                type="color"
                                aria-label="Shape fill color"
                                value={objectStyleDraft.fill_color}
                                onChange={(event) =>
                                  setObjectStyleDraft((current) => ({
                                    ...current,
                                    fill_color:
                                      event.target.value.toUpperCase(),
                                  }))
                                }
                                disabled={!loadedSourceId || loading}
                              />
                            </label>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                void saveShapeColorRevision("fill_color")
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                selectedObject.shape_style.fill_color ===
                                  objectStyleDraft.fill_color
                              }
                            >
                              Apply fill color
                            </button>
                            {selectedObject.shape_style
                              .fill_transparency_percent != null ? (
                              <>
                                <label>
                                  Fill transparency (%)
                                  <input
                                    type="number"
                                    min="0"
                                    max="100"
                                    step="1"
                                    aria-label="Shape fill transparency"
                                    value={
                                      objectStyleDraft.fill_transparency_percent
                                    }
                                    onChange={(event) =>
                                      setObjectStyleDraft((current) => ({
                                        ...current,
                                        fill_transparency_percent:
                                          event.target.value,
                                      }))
                                    }
                                    disabled={!loadedSourceId || loading}
                                  />
                                </label>
                                <button
                                  type="button"
                                  className="secondary-button"
                                  onClick={() =>
                                    void saveShapeColorRevision("transparency")
                                  }
                                  disabled={
                                    !loadedSourceId ||
                                    loading ||
                                    !/^\d{1,3}$/.test(
                                      objectStyleDraft.fill_transparency_percent,
                                    ) ||
                                    Number(
                                      objectStyleDraft.fill_transparency_percent,
                                    ) > 100 ||
                                    Number(
                                      objectStyleDraft.fill_transparency_percent,
                                    ) ===
                                      selectedObject.shape_style
                                        .fill_transparency_percent
                                  }
                                >
                                  Apply transparency
                                </button>
                              </>
                            ) : null}
                          </div>
                        ) : selectedObject.kind === "pic" ? null : (
                          <p className="muted">
                            The current fill uses an unsupported effect and
                            stays read-only.
                          </p>
                        )}
                        {selectedObject.shape_style.line_editable ? (
                          <div className="pw-shape-color-control">
                            <label>
                              Outline color
                              <input
                                type="color"
                                aria-label="Shape outline color"
                                value={objectStyleDraft.line_color}
                                onChange={(event) =>
                                  setObjectStyleDraft((current) => ({
                                    ...current,
                                    line_color:
                                      event.target.value.toUpperCase(),
                                  }))
                                }
                                disabled={!loadedSourceId || loading}
                              />
                            </label>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                void saveShapeColorRevision("line_color")
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                selectedObject.shape_style.line_color ===
                                  objectStyleDraft.line_color
                              }
                            >
                              Apply outline color
                            </button>
                          </div>
                        ) : (
                          <p className="muted">
                            The current outline uses an unsupported effect and
                            stays read-only.
                          </p>
                        )}
                        {selectedObject.shape_style.shape_geometry ? (
                          <label>
                            Shape type
                            <select
                              aria-label="Shape type"
                              value={selectedObject.shape_style.shape_geometry}
                              onChange={(event) =>
                                void saveShapeColorRevision(
                                  `geometry:${event.target.value}`,
                                )
                              }
                              disabled={!loadedSourceId || loading}
                            >
                              {SHAPE_GEOMETRIES.map(([value, label]) => (
                                <option key={value} value={value}>
                                  {label}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                        {selectedObject.shape_style.shadow_editable ? (
                          <div className="pw-shape-color-control">
                            <p className="muted">
                              Shadow:{" "}
                              {selectedObject.shape_style.shadow === true
                                ? "on"
                                : selectedObject.shape_style.shadow === false
                                  ? "off"
                                  : "from the theme style"}
                            </p>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                void saveShapeColorRevision("shadow_on")
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                selectedObject.shape_style.shadow === true
                              }
                            >
                              Add shadow
                            </button>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                void saveShapeColorRevision("shadow_off")
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                selectedObject.shape_style.shadow === false
                              }
                            >
                              Remove shadow
                            </button>
                          </div>
                        ) : null}
                        {selectedObject.shape_style.line_format_editable ? (
                          <div className="pw-shape-color-control">
                            <label>
                              Outline width (points, 0.25–20)
                              <input
                                type="number"
                                min="0.25"
                                max="20"
                                step="0.25"
                                placeholder="Keep current"
                                aria-label="Shape outline width"
                                value={objectStyleDraft.line_width_pt}
                                onChange={(event) =>
                                  setObjectStyleDraft((current) => ({
                                    ...current,
                                    line_width_pt: event.target.value,
                                  }))
                                }
                                disabled={!loadedSourceId || loading}
                              />
                            </label>
                            <label>
                              Outline style
                              <select
                                aria-label="Shape outline style"
                                value={objectStyleDraft.line_dash}
                                onChange={(event) =>
                                  setObjectStyleDraft((current) => ({
                                    ...current,
                                    line_dash: event.target.value,
                                  }))
                                }
                                disabled={!loadedSourceId || loading}
                              >
                                <option value="">Keep current</option>
                                {SHAPE_LINE_DASHES.map(([value, label]) => (
                                  <option key={value} value={value}>
                                    {label}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                void saveShapeColorRevision("outline")
                              }
                              disabled={
                                !loadedSourceId ||
                                loading ||
                                ((objectStyleDraft.line_width_pt === "" ||
                                  Number(objectStyleDraft.line_width_pt) ===
                                    selectedObject.shape_style.line_width_pt) &&
                                  (objectStyleDraft.line_dash === "" ||
                                    objectStyleDraft.line_dash ===
                                      selectedObject.shape_style.line_dash))
                              }
                            >
                              Apply outline style
                            </button>
                          </div>
                        ) : null}
                      </fieldset>
                    ) : null}
                    {selectedObject?.delete_editable ? (
                      <div className="pw-object-delete">
                        {deleteConfirmationObjectId !==
                          selectedObject.object_id &&
                        (selectedObject.kind === "sp" ||
                          selectedObject.kind === "pic" ||
                          selectedObject.kind === "graphicFrame" ||
                          selectedObject.kind === "grpSp") ? (
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() =>
                              void duplicateSelectedObjectRevision()
                            }
                            disabled={!loadedSourceId || loading}
                            aria-label="Duplicate selected object"
                          >
                            Duplicate object
                          </button>
                        ) : null}
                        {deleteConfirmationObjectId ===
                        selectedObject.object_id ? (
                          <>
                            <p role="status">
                              Delete “{selectedObject.name}” from this slide?
                              The original revision remains available to
                              restore.
                            </p>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() =>
                                void deleteSelectedObjectRevision()
                              }
                              disabled={loading}
                              aria-label="Confirm delete selected object"
                            >
                              Confirm deletion
                            </button>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={() => setDeleteConfirmationObjectId("")}
                              disabled={loading}
                              aria-label="Cancel object deletion"
                            >
                              Keep object
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() =>
                              setDeleteConfirmationObjectId(
                                selectedObject.object_id,
                              )
                            }
                            disabled={!loadedSourceId || loading}
                            aria-label="Review object deletion"
                          >
                            Delete object
                          </button>
                        )}
                      </div>
                    ) : null}
                    {objectInventoryHasMore ? (
                      <p className="muted">
                        Only the first 100 objects are listed on this slide.
                      </p>
                    ) : null}
                  </>
                ) : (
                  <p className="muted">Open a slide to inspect its objects.</p>
                )}
              </section>
              <ComponentLibrary
                projectId={project.id}
                selection={componentSelection}
                sourceNames={Object.fromEntries(
                  sources.map((item) => [item.id, item.original_name]),
                )}
                canInsert={
                  !!currentRevision &&
                  !!selectedSource &&
                  loadedSourceId === selectedSource.id &&
                  UUID_PATTERN.test(activeSlideId)
                }
                disabled={loading || voiceWorkflowActive}
                request={requestCore}
                onInsert={insertComponent}
              />
            </div>
            <div
              id="pw-panel-notes"
              className="pw-studio-panel"
              hidden={inspectorPanel !== "notes"}
            >
              <section
                className="pw-slide-notes"
                aria-labelledby="pw-notes-title"
              >
                <p className="eyebrow">REVISION EDITING</p>
                <h4 id="pw-notes-title">Speaker notes</h4>
                {!speakerNotesTarget ? (
                  <p className="muted">Open a slide to inspect its notes.</p>
                ) : speakerNotesTarget.editable &&
                  speakerNotesTarget.current_text !== null ? (
                  <>
                    <p className="muted">
                      Plain speaker notes can be saved as a new presentation
                      revision. Richly formatted notes stay read-only.
                    </p>
                    <label>
                      Speaker notes
                      <textarea
                        aria-label="Speaker notes"
                        value={speakerNotesDraft}
                        onChange={(event) =>
                          setSpeakerNotesDraft(event.target.value)
                        }
                        maxLength={MAX_SPEAKER_NOTES_CHARS}
                        rows={6}
                        disabled={!loadedSourceId || loading}
                      />
                    </label>
                    {speakerNotesDraft.split("\n").length >
                    MAX_SPEAKER_NOTES_PARAGRAPHS ? (
                      <p className="muted" role="alert">
                        Notes can contain at most {MAX_SPEAKER_NOTES_PARAGRAPHS}{" "}
                        paragraphs in this editor.
                      </p>
                    ) : null}
                    <button
                      type="button"
                      className="primary-button"
                      onClick={() => void saveSpeakerNotesRevision()}
                      disabled={
                        !loadedSourceId ||
                        loading ||
                        speakerNotesDraft.split("\n").length >
                          MAX_SPEAKER_NOTES_PARAGRAPHS
                      }
                    >
                      Save speaker notes
                    </button>
                  </>
                ) : speakerNotesTarget.current_text === null ? (
                  <p className="muted">
                    This slide has no editable speaker-notes body.
                  </p>
                ) : (
                  <>
                    <p className="pw-notes-readonly">
                      {speakerNotesTarget.current_text}
                      {speakerNotesTarget.text_truncated
                        ? "\n[Notes are truncated at the preview limit.]"
                        : ""}
                    </p>
                    <p className="muted">
                      These notes use formatting the editor cannot safely
                      retain, so they are read-only.
                    </p>
                  </>
                )}
              </section>
            </div>
          </aside>
        </div>
      )}
      {creatingPresentation ? (
        <CreatePresentation
          projectId={project.id}
          onClose={() => setCreatingPresentation(false)}
          onCreated={async (document) => {
            await onPresentationCreated();
            setSelectedSourceId(document.id);
            setPendingCreatedId(document.id);
          }}
        />
      ) : null}
      {visible && voiceWorkflowActive
        ? createPortal(
            <div className="pw-voice-backdrop">
              <div
                ref={voiceDialogRef}
                className="pw-voice-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="pw-voice-dialog-title"
                tabIndex={-1}
                onKeyDown={handleVoiceDialogKeyDown}
              >
                <p className="eyebrow">LOCAL VOICE EDIT</p>
                <h2 id="pw-voice-dialog-title">
                  {voiceCaptureState === "review"
                    ? "Review spoken instruction"
                    : "Dictate an edit instruction"}
                </h2>
                <p className="muted">
                  Slide {selectedSlide} ·{" "}
                  {selectedTarget?.label ?? "selected text"}
                </p>
                <p className="pw-privacy-copy">
                  Audio is captured and transcribed by the local Core. The
                  transcript stays temporary until you review it. It is sent to
                  your configured reasoning provider only after you use it and
                  request a rewrite.
                </p>
                {voiceCaptureState === "starting" ? (
                  <p role="status">Preparing local speech capture…</p>
                ) : null}
                {voiceCaptureState === "listening" ? (
                  <>
                    <p role="status">
                      {voicePartial || "Listening for your edit instruction…"}
                    </p>
                    <div className="pw-voice-actions">
                      <button
                        type="button"
                        className="primary-button"
                        onClick={() => {
                          voiceHold.release();
                          void stopVoiceInstruction();
                        }}
                      >
                        Stop and review
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => {
                          voiceHold.cancel();
                          void cancelVoiceInstruction();
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </>
                ) : null}
                {voiceCaptureState === "stopping" ? (
                  <p role="status">Finishing local transcription…</p>
                ) : null}
                {voiceCaptureState === "cancelling" ? (
                  <p role="status">Releasing the microphone…</p>
                ) : null}
                {voiceCaptureState === "starting" ? (
                  <div className="pw-voice-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => {
                        voiceHold.cancel();
                        void cancelVoiceInstruction();
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : null}
                {voiceCaptureState === "review" ? (
                  <>
                    <p>
                      Intended target: selected text on slide {selectedSlide}.
                      Clarification refines this request; choose another text
                      target separately.
                    </p>
                    <VoiceRecognitionReview review={voiceRecognition} />
                    <label className="pw-voice-transcript-label">
                      Dictated instruction
                      <textarea
                        aria-label="Review dictated instruction"
                        value={voiceTranscript}
                        onChange={(event) => {
                          setVoiceTranscript(event.target.value);
                          setVoiceError(null);
                        }}
                        maxLength={MAX_REVIEW_TRANSCRIPT_CHARS}
                        rows={5}
                      />
                    </label>
                    <label className="pw-voice-transcript-label">
                      Clarify intended wording (optional)
                      <textarea
                        aria-label="Dictated rewrite clarification"
                        value={voiceClarification}
                        maxLength={500}
                        rows={2}
                        onChange={(event) =>
                          setVoiceClarification(event.target.value)
                        }
                      />
                    </label>
                    <p className="muted">
                      {
                        clarifiedVoiceInstruction(
                          voiceTranscript,
                          voiceClarification,
                        ).length
                      }{" "}
                      / {MAX_REVIEW_TRANSCRIPT_CHARS} characters including
                      clarification. Rewrite instructions allow up to{" "}
                      {MAX_REWRITE_INSTRUCTION_CHARS}; edit longer transcripts
                      before using them.
                    </p>
                    <div className="pw-voice-actions">
                      <button
                        type="button"
                        className="primary-button"
                        onClick={useReviewedVoiceInstruction}
                        disabled={
                          !voiceTranscript.trim() ||
                          clarifiedVoiceInstruction(
                            voiceTranscript,
                            voiceClarification,
                          ).length > MAX_REWRITE_INSTRUCTION_CHARS
                        }
                      >
                        Use reviewed instruction
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => {
                          voiceHold.cancel();
                          void cancelVoiceInstruction();
                        }}
                      >
                        Discard transcript
                      </button>
                    </div>
                  </>
                ) : null}
                {voiceError ? (
                  <p className="error-message" role="alert">
                    {voiceError}
                  </p>
                ) : null}
              </div>
            </div>,
            document.body,
          )
        : null}
    </section>
  );
}
