import { repairChartLabels } from "./chart-label-preview";
import { normalizeAuthoredPiePreview } from "./chart-preview";
import {
  buildPresentation,
  parseZipLazyMedia,
  PptxViewer,
  renderSlide,
  type SlideRendererOptions,
  type FontFaceConfig,
  RECOMMENDED_ZIP_LIMITS,
  type SlideHandle,
} from "@aiden0z/pptx-renderer";

import type {
  PresentationPreviewHostRequest,
  PresentationPreviewHostResponse,
  PresentationPreviewHostTextCandidate,
} from "../shared/presentation-preview-protocol";
import {
  probeBrowserCssFamily,
  probeBrowserLocalFont,
  resolvePreviewFonts,
} from "./font-fallbacks";
import { applyPreviewRendererCompatibility } from "./renderer-compatibility";
import { textEscapesShapeBounds } from "./layout-risk";
import { PREVIEW_PDFJS } from "./pdfjs-assets";
import { applyPowerPointWordWrapping } from "./text-layout";

const PREVIEW_WIDTH = 960;
const MAX_TEXT_CANDIDATES = 100;
const MAX_TEXT_CHARS = 2000;
const MAX_NAME_CHARS = 200;

const stage = document.getElementById("stage");
if (!(stage instanceof HTMLElement)) {
  throw new Error("The isolated preview stage is unavailable.");
}
const previewStage = stage as HTMLElement;

type PreviewSlideResponse = Omit<
  Extract<PresentationPreviewHostResponse, { type: "slide" }>,
  "id"
>;

let viewer: PptxViewer | null = null;
let previewFontFaces: readonly FontFaceConfig[] = [];
let currentHandle: SlideHandle | null = null;
let openController: AbortController | null = null;
let textMutation: { originalText: string; run: { text: string } } | null = null;
let fontSubstitutions: string[] = [];
let unresolvedFontFamilies: string[] = [];
let fontScanLimited = false;
let requestQueue = Promise.resolve();

function respond(response: PresentationPreviewHostResponse): void {
  window.presentationPreviewHost.respond(response);
}

function clearCurrentFrame(): void {
  currentHandle?.dispose();
  currentHandle = null;
  if (textMutation) {
    textMutation.run.text = textMutation.originalText;
    textMutation = null;
  }
  previewStage.replaceChildren();
}

function closeViewer(): void {
  clearCurrentFrame();
  openController?.abort();
  openController = null;
  viewer?.destroy();
  viewer = null;
  previewFontFaces = [];
  fontSubstitutions = [];
  unresolvedFontFamilies = [];
  fontScanLimited = false;
}

async function openPresentation(buffer: ArrayBuffer): Promise<void> {
  closeViewer();
  const controller = new AbortController();
  openController = controller;
  let currentViewer: PptxViewer | null = null;
  const ensureOpen = () => {
    if (controller.signal.aborted || openController !== controller) {
      throw new Error("Presentation preview was closed.");
    }
  };
  try {
    const files = await parseZipLazyMedia(buffer, RECOMMENDED_ZIP_LIMITS);
    ensureOpen();
    await applyPreviewRendererCompatibility(buffer, files, {
      suppressHiddenDrawingObjects: true,
      normalizeBackgroundFills: true,
      normalizeThemeOverrideColors: true,
      normalizeGroupFills: true,
      inheritLayoutPlaceholderFills: true,
      repairSmartArtRelationships: true,
      normalizePictureFillGeometry: true,
      normalizeDuotoneImages: true,
      sizeTiledImageFills: true,
      suppressBrowserOnlyLineBreaks: true,
      followTextColoredHyperlinks: true,
      fillDefaultLineSpacing: true,
    });
    ensureOpen();
    const presentation = buildPresentation(files, { lazySlides: true });
    normalizeAuthoredPiePreview(presentation);
    const fonts = await resolvePreviewFonts(
      files,
      presentation,
      probeBrowserLocalFont,
      controller.signal,
      probeBrowserCssFamily,
    );
    ensureOpen();
    currentViewer = new PptxViewer(previewStage, {
      fitMode: "none",
      pdfjs: PREVIEW_PDFJS,
      lazySlides: true,
      lazyMedia: true,
      fontFaces: fonts.fontFaces,
    });
    previewFontFaces = fonts.fontFaces;
    currentViewer.load(presentation);
    await currentViewer.renderSlide(0);
    applyPowerPointWordWrapping(previewStage);
    ensureOpen();
    fontSubstitutions = fonts.substitutions;
    unresolvedFontFamilies = fonts.unresolvedFamilies;
    fontScanLimited = fonts.limited;
  } catch (error) {
    currentViewer?.destroy();
    throw error;
  }
  if (!currentViewer) throw new Error("The preview failed to open.");
  if (
    !Number.isSafeInteger(currentViewer.slideCount) ||
    currentViewer.slideCount < 1 ||
    currentViewer.slideCount > 5000 ||
    !Number.isFinite(currentViewer.slideWidth) ||
    currentViewer.slideWidth <= 0 ||
    !Number.isFinite(currentViewer.slideHeight) ||
    currentViewer.slideHeight <= 0
  ) {
    currentViewer.destroy();
    throw new Error("The presentation dimensions could not be verified.");
  }
  viewer = currentViewer;
}

function textCandidatesForSlide(
  slideNumber: number,
): PresentationPreviewHostTextCandidate[] {
  const slide = viewer?.presentationData?.slides[slideNumber - 1];
  if (!slide) return [];
  const candidates: PresentationPreviewHostTextCandidate[] = [];
  for (const node of slide.nodes) {
    if (node.nodeType !== "shape" || !node.textBody) continue;
    const paragraphs = node.textBody.paragraphs;
    if (paragraphs.length < 1 || paragraphs.length > 128) continue;
    const text = paragraphs
      .map((paragraph) => paragraph.runs.map((run) => run.text).join(""))
      .join("\n");
    if (
      !text.trim() ||
      text.length > MAX_TEXT_CHARS ||
      !node.id ||
      node.id.length > 128
    ) {
      continue;
    }
    candidates.push({
      shape_node_id: node.id,
      name: node.name.trim().slice(0, MAX_NAME_CHARS) || "Text box",
      text,
    });
    if (candidates.length >= MAX_TEXT_CANDIDATES) break;
  }
  return candidates;
}

function findTextRun(
  slideNumber: number,
  shapeNodeId: string,
): { text: string } | null {
  const slide = viewer?.presentationData?.slides[slideNumber - 1];
  if (!slide) return null;
  const matches = slide.nodes.filter(
    (node) => node.nodeType === "shape" && node.id === shapeNodeId,
  );
  if (matches.length !== 1) return null;
  const node = matches[0];
  if (node?.nodeType !== "shape" || !node.textBody) return null;
  const paragraphs = node.textBody.paragraphs;
  if (paragraphs.length !== 1 || paragraphs[0]?.runs.length !== 1) return null;
  return paragraphs[0]?.runs[0] ?? null;
}

function normalizeRenderedText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function previewTextOverflowsShape(
  slideNumber: number,
  shapeNodeId: string,
): boolean | null {
  const currentViewer = viewer;
  const handle = currentHandle;
  const slide = currentViewer?.presentationData?.slides[slideNumber - 1];
  if (!currentViewer || !handle || !slide) return null;
  const matches = slide.nodes.filter(
    (node) => node.nodeType === "shape" && node.id === shapeNodeId,
  );
  if (matches.length !== 1) return null;
  const node = matches[0];
  if (
    node?.nodeType !== "shape" ||
    node.rotation !== 0 ||
    node.flipH ||
    node.flipV
  ) {
    return null;
  }
  const paragraphs = node.textBody?.paragraphs;
  if (
    !paragraphs ||
    paragraphs.length !== 1 ||
    paragraphs[0]?.runs.length !== 1
  ) {
    return null;
  }
  const expectedText = normalizeRenderedText(paragraphs[0].runs[0]?.text ?? "");
  if (!expectedText) return false;

  const slideBounds = handle.element.getBoundingClientRect();
  const scaleX = slideBounds.width / currentViewer.slideWidth;
  const scaleY = slideBounds.height / currentViewer.slideHeight;
  if (
    !Number.isFinite(scaleX) ||
    !Number.isFinite(scaleY) ||
    scaleX <= 0 ||
    scaleY <= 0 ||
    Math.abs(scaleX - scaleY) > 0.01
  ) {
    return null;
  }
  const expectedBounds = {
    left: slideBounds.left + node.position.x * scaleX,
    top: slideBounds.top + node.position.y * scaleY,
    right: slideBounds.left + (node.position.x + node.size.w) * scaleX,
    bottom: slideBounds.top + (node.position.y + node.size.h) * scaleY,
  };
  const targetElements = Array.from(handle.element.children).filter(
    (element): element is HTMLElement => {
      if (!(element instanceof HTMLElement)) return false;
      const renderedText = normalizeRenderedText(element.textContent ?? "");
      if (renderedText !== expectedText) return false;
      const bounds = element.getBoundingClientRect();
      return (
        Math.abs(bounds.left - expectedBounds.left) <= 2 &&
        Math.abs(bounds.top - expectedBounds.top) <= 2 &&
        Math.abs(bounds.width - node.size.w * scaleX) <= 2
      );
    },
  );
  if (targetElements.length !== 1) return null;

  const range = document.createRange();
  range.selectNodeContents(targetElements[0]!);
  const textFragments = Array.from(range.getClientRects())
    .filter((rect) => rect.width > 0 && rect.height > 0)
    .map((rect) => ({
      left: rect.left,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom,
    }));
  return textEscapesShapeBounds(expectedBounds, textFragments);
}

async function waitForRenderedSlide(
  slideNumber: number,
  mockText?: { shape_node_id: string; text: string },
): Promise<PreviewSlideResponse> {
  const currentViewer = viewer;
  if (
    !currentViewer ||
    !Number.isSafeInteger(slideNumber) ||
    slideNumber < 1 ||
    slideNumber > currentViewer.slideCount
  ) {
    throw new Error("The requested presentation slide is unavailable.");
  }

  clearCurrentFrame();
  if (mockText) {
    const run = findTextRun(slideNumber, mockText.shape_node_id);
    if (!run || mockText.text.length > MAX_TEXT_CHARS) {
      throw new Error("The requested mock text target is unavailable.");
    }
    textMutation = { run, originalText: run.text };
    run.text = mockText.text;
  }

  const height = Math.round(
    (PREVIEW_WIDTH * currentViewer.slideHeight) / currentViewer.slideWidth,
  );
  previewStage.style.width = `${PREVIEW_WIDTH}px`;
  previewStage.style.height = `${height}px`;
  previewStage.replaceChildren();
  const presentation = currentViewer.presentationData;
  const slide = presentation?.slides[slideNumber - 1];
  if (!presentation || !slide)
    throw new Error("The slide model is unavailable.");
  const charts: NonNullable<SlideRendererOptions["chartInstances"]> = new Set();
  const handle = renderSlide(presentation, slide, {
    chartInstances: charts,
    pdfjs: PREVIEW_PDFJS,
    fontFaces: previewFontFaces,
  });
  handle.element.style.transform = `scale(${PREVIEW_WIDTH / currentViewer.slideWidth})`;
  handle.element.style.transformOrigin = "top left";
  previewStage.appendChild(handle.element);
  currentHandle = handle;
  if (handle.ready) await handle.ready;
  repairChartLabels(presentation, slide, charts);
  applyPowerPointWordWrapping(previewStage);
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  });
  const bounds = handle.element.getBoundingClientRect();
  if (
    !Number.isFinite(bounds.width) ||
    !Number.isFinite(bounds.height) ||
    Math.abs(bounds.width - PREVIEW_WIDTH) > 1 ||
    Math.abs(bounds.height - height) > 1
  ) {
    throw new Error("The rendered slide dimensions could not be verified.");
  }
  return {
    ok: true,
    type: "slide",
    slide_number: slideNumber,
    text_candidates: textCandidatesForSlide(slideNumber),
    ...(mockText
      ? {
          mock_text_overflows_shape: previewTextOverflowsShape(
            slideNumber,
            mockText.shape_node_id,
          ),
        }
      : {}),
  };
}

async function handleRequest(
  request: PresentationPreviewHostRequest,
): Promise<void> {
  try {
    if (request.type === "open") {
      await openPresentation(request.buffer);
      const currentViewer = viewer;
      if (!currentViewer) throw new Error("The preview failed to open.");
      respond({
        id: request.id,
        ok: true,
        type: "opened",
        slide_count: currentViewer.slideCount,
        slide_width: currentViewer.slideWidth,
        slide_height: currentViewer.slideHeight,
        font_substitutions: fontSubstitutions,
        unresolved_font_families: unresolvedFontFamilies,
        font_check_limited: fontScanLimited,
      });
      return;
    }
    if (request.type === "release-frame") {
      clearCurrentFrame();
      respond({ id: request.id, ok: true, type: "released" });
      return;
    }
    if (request.mock_text) {
      if (
        typeof request.mock_text.shape_node_id !== "string" ||
        request.mock_text.shape_node_id.length < 1 ||
        request.mock_text.shape_node_id.length > 128 ||
        typeof request.mock_text.text !== "string" ||
        request.mock_text.text.length > MAX_TEXT_CHARS
      ) {
        throw new Error("The mock text request is invalid.");
      }
    }
    const response = await waitForRenderedSlide(
      request.slide_number,
      request.mock_text,
    );
    respond({ ...response, id: request.id });
  } catch {
    respond({ id: request.id, ok: false });
  }
}

window.presentationPreviewHost.onRequest((request) => {
  requestQueue = requestQueue
    .then(() => handleRequest(request))
    .catch(() => respond({ id: request.id, ok: false }));
});

window.addEventListener("unload", closeViewer, { once: true });
window.presentationPreviewHost.ready();
