import { normalizeAuthoredPiePreview } from "./chart-preview";
import {
  buildPresentation,
  parseZipLazyMedia,
  PptxViewer,
  RECOMMENDED_ZIP_LIMITS,
  type SlideHandle,
} from "@aiden0z/pptx-renderer";

import { probeBrowserLocalFont, resolvePreviewFonts } from "./font-fallbacks";
import {
  applyPreviewRendererCompatibility,
  type PreviewRendererCompatibilityOptions,
  type PreviewRendererCompatibilityReport,
} from "./renderer-compatibility";
import { applyPowerPointWordWrapping } from "./text-layout";
import { PREVIEW_PDFJS } from "./pdfjs-assets";

const SOURCE_ROUTE = "/__workspace_qa__/source.pptx";
const BASE_RENDER_WIDTH = 960;
const MAX_SLIDE_COUNT = 5_000;
const MAX_RENDER_DIMENSION = 2_048;
type PreviewCompatibilityMode =
  | "all"
  | "all-no-image-effects"
  | "baseline"
  | "background-only"
  | "theme-background-only"
  | "theme-override-only"
  | "hidden-only"
  | "placeholder-only"
  | "smartart-only"
  | "picture-geometry-only";

const stage = document.getElementById("stage");
if (!(stage instanceof HTMLElement)) {
  throw new Error("Preview stage is unavailable.");
}

let viewer: PptxViewer | null = null;
let currentHandle: SlideHandle | null = null;
let renderDimensions: { width: number; height: number } | null = null;
let renderScale = 1;

window.openDeck = async (compatibilityMode = "all") => {
  if (
    ![
      "all",
      "all-no-image-effects",
      "baseline",
      "background-only",
      "theme-background-only",
      "theme-override-only",
      "hidden-only",
      "placeholder-only",
      "smartart-only",
      "picture-geometry-only",
    ].includes(compatibilityMode)
  ) {
    throw new Error("PREVIEW_COMPATIBILITY_MODE_INVALID");
  }
  const response = await fetch(SOURCE_ROUTE);
  if (!response.ok) throw new Error("PREVIEW_SOURCE_UNAVAILABLE");
  const buffer = await response.arrayBuffer();
  const files = await parseZipLazyMedia(buffer, RECOMMENDED_ZIP_LIMITS);
  const allCompatibility =
    compatibilityMode === "all" || compatibilityMode === "all-no-image-effects";
  const compatibilityOptions: PreviewRendererCompatibilityOptions = {
    suppressHiddenDrawingObjects:
      allCompatibility || compatibilityMode === "hidden-only",
    normalizeBackgroundFills:
      allCompatibility || compatibilityMode === "background-only",
    normalizeThemeBackgroundImageFills:
      allCompatibility || compatibilityMode === "theme-background-only",
    normalizeThemeBackgroundImageEffects:
      compatibilityMode === "all" ||
      compatibilityMode === "theme-background-only",
    normalizeThemeOverrideColors:
      allCompatibility || compatibilityMode === "theme-override-only",
    normalizeGroupFills: allCompatibility,
    inheritLayoutPlaceholderFills:
      allCompatibility || compatibilityMode === "placeholder-only",
    repairSmartArtRelationships:
      allCompatibility || compatibilityMode === "smartart-only",
    normalizePictureFillGeometry:
      allCompatibility || compatibilityMode === "picture-geometry-only",
    normalizeDuotoneImages: compatibilityMode === "all",
  };
  globalThis.previewCompatibilityReport =
    compatibilityMode === "baseline"
      ? {
          backgroundFillShapesNormalized: 0,
          hiddenDrawingObjectsSuppressed: 0,
          backgroundStyleFillReferencesRemoved: 0,
          themeBackgroundImageFillsResolved: 0,
          pictureGeometryImagesPromoted: 0,
          pictureGeometryImagesSkipped: 0,
          themeOverrideColorsNormalized: 0,
          groupFillReferencesInherited: 0,
          layoutPlaceholderFillsInherited: 0,
          smartArtImageReferencesRepaired: 0,
          smartArtRelationshipPartsUpdated: 0,
          smartArtImageShapesPromoted: 0,
          duotoneImageReferencesNormalized: 0,
          compatibilityPartsSkipped: 0,
        }
      : await applyPreviewRendererCompatibility(
          buffer,
          files,
          compatibilityOptions,
        );
  globalThis.previewCompatibilityMode = compatibilityMode;
  const presentation = buildPresentation(files, { lazySlides: true });
  normalizeAuthoredPiePreview(presentation);
  const fonts = await resolvePreviewFonts(
    files,
    presentation,
    probeBrowserLocalFont,
  );
  viewer?.destroy();
  stage.replaceChildren();
  viewer = new PptxViewer(stage, {
    fitMode: "none",
    pdfjs: PREVIEW_PDFJS,
    lazySlides: true,
    lazyMedia: true,
    fontFaces: fonts.fontFaces,
  });
  viewer.load(presentation);
  await viewer.renderSlide(0);
  if (
    !Number.isSafeInteger(viewer.slideCount) ||
    viewer.slideCount < 1 ||
    viewer.slideCount > MAX_SLIDE_COUNT ||
    !Number.isFinite(viewer.slideWidth) ||
    viewer.slideWidth <= 0 ||
    !Number.isFinite(viewer.slideHeight) ||
    viewer.slideHeight <= 0
  ) {
    throw new Error("PREVIEW_DIMENSIONS_INVALID");
  }
  renderScale = BASE_RENDER_WIDTH / viewer.slideWidth;
  renderDimensions = {
    width: BASE_RENDER_WIDTH,
    height: Math.round(
      (BASE_RENDER_WIDTH * viewer.slideHeight) / viewer.slideWidth,
    ),
  };
  if (
    renderDimensions.height < 1 ||
    renderDimensions.height > MAX_RENDER_DIMENSION
  ) {
    throw new Error("PREVIEW_DIMENSIONS_INVALID");
  }
  stage.style.width = `${renderDimensions.width}px`;
  stage.style.height = `${renderDimensions.height}px`;
  return viewer.slideCount;
};

window.renderSlide = async (slideNumber: number) => {
  const currentViewer = viewer;
  const dimensions = renderDimensions;
  if (
    !currentViewer ||
    !dimensions ||
    !Number.isSafeInteger(slideNumber) ||
    slideNumber < 1 ||
    slideNumber > currentViewer.slideCount
  ) {
    throw new Error("PREVIEW_SLIDE_INVALID");
  }
  currentHandle?.dispose();
  stage.replaceChildren();
  currentHandle = currentViewer.renderSlideToContainer(
    slideNumber - 1,
    stage,
    renderScale,
  );
  if (currentHandle?.ready) await currentHandle.ready;
  applyPowerPointWordWrapping(stage);
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  });
  const bounds = currentHandle?.element.getBoundingClientRect();
  if (
    !bounds ||
    Math.abs(bounds.width - dimensions.width) > 1 ||
    Math.abs(bounds.height - dimensions.height) > 1
  ) {
    throw new Error("PREVIEW_SLIDE_DIMENSIONS_INVALID");
  }
  return { slide_number: slideNumber, ...dimensions };
};

declare global {
  interface Window {
    openDeck: (compatibilityMode?: PreviewCompatibilityMode) => Promise<number>;
    renderSlide: (slideNumber: number) => Promise<{
      slide_number: number;
      width: number;
      height: number;
    }>;
  }

  var previewCompatibilityReport: PreviewRendererCompatibilityReport;
  var previewCompatibilityMode: PreviewCompatibilityMode;
}
