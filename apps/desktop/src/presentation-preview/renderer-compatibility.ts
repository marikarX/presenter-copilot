import JSZip from "jszip";

import type { PptxFiles } from "@aiden0z/pptx-renderer";

const PRESENTATION_NS =
  "http://schemas.openxmlformats.org/presentationml/2006/main";
const DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main";
const DIAGRAM_NS = "http://schemas.openxmlformats.org/drawingml/2006/diagram";
const DIAGRAM_DRAWING_NS =
  "http://schemas.microsoft.com/office/drawing/2008/diagram";
const PACKAGE_RELATIONSHIP_NS =
  "http://schemas.openxmlformats.org/package/2006/relationships";
const XMLNS_NS = "http://www.w3.org/2000/xmlns/";
const OFFICE_RELATIONSHIP_NS =
  "http://schemas.openxmlformats.org/officeDocument/2006/relationships";

const IMAGE_RELATIONSHIP_TYPE = `${OFFICE_RELATIONSHIP_NS}/image`;
const SLIDE_LAYOUT_RELATIONSHIP_TYPE = `${OFFICE_RELATIONSHIP_NS}/slideLayout`;
const THEME_OVERRIDE_RELATIONSHIP_TYPE = `${OFFICE_RELATIONSHIP_NS}/themeOverride`;
const MAX_XML_DOCUMENT_CHARS = 8 * 1024 * 1024;
const MAX_RELATIONSHIP_XML_CHARS = 1024 * 1024;
const MAX_COMPATIBILITY_XML_CHARS = 32 * 1024 * 1024;
const MAX_GROUP_FILL_DRAWABLES_PER_SLIDE = 20_000;
const MAX_GROUP_FILL_DEPTH = 64;
const MAX_DIAGRAM_PARTS = 256;
const MAX_DIAGRAM_IMAGE_REFERENCES = 2_000;
const MAX_THEME_OVERRIDE_PARTS = 256;
const MAX_THEME_OVERRIDE_REFERENCES = 100_000;
const MAX_THEME_BACKGROUND_FILL_PARTS = 256;
const MAX_PICTURE_GEOMETRY_IMAGES = 2_000;
const MAX_PICTURE_GEOMETRY_SINGLE_MEDIA_BYTES = 32 * 1024 * 1024;
const MAX_PICTURE_GEOMETRY_TOTAL_MEDIA_BYTES = 128 * 1024 * 1024;
const MAX_DUOTONE_IMAGE_REFERENCES = 128;
const MAX_DUOTONE_SOURCE_BYTES = 16 * 1024 * 1024;
const MAX_DUOTONE_OUTPUT_BYTES = 8 * 1024 * 1024;
const MAX_DUOTONE_TOTAL_BYTES = 32 * 1024 * 1024;
const MAX_DUOTONE_TOTAL_PIXELS = 8_000_000;
const MAX_DUOTONE_SINGLE_IMAGE_PIXELS = 4_000_000;
// Re-fit against PowerPoint after a:lum was corrected to PowerPoint's measured
// brightness/contrast behavior (record 90000004 median RGB MAE minimum).
const OBSERVED_CLEAR_MATERIAL_PREVIEW_ALPHA = 0.1;
const PRESENTATION_DRAWABLE_NAMES = new Set([
  "sp",
  "cxnSp",
  "pic",
  "graphicFrame",
  "grpSp",
]);
const PRESENTATION_NON_VISUAL_PROPERTIES = new Map([
  ["sp", "nvSpPr"],
  ["cxnSp", "nvCxnSpPr"],
  ["pic", "nvPicPr"],
  ["graphicFrame", "nvGraphicFramePr"],
  ["grpSp", "nvGrpSpPr"],
]);
const DRAWING_FILL_NAMES = new Set([
  "noFill",
  "solidFill",
  "gradFill",
  "blipFill",
  "pattFill",
  "grpFill",
]);

type XmlPlatform = Pick<DOMParser, "parseFromString"> & {
  serialize(document: Document): string;
};

interface SlideSize {
  width: bigint;
  height: bigint;
}

interface RelationshipRecord {
  id: string;
  type: string;
  target: string;
  targetMode: string | null;
  element: Element;
}

interface RelationshipContext {
  sourcePath: string;
  sourceXml: string;
  relationshipPath: string;
  relationshipMap: Map<string, string>;
  document: Document;
  root: Element;
  records: Map<string, RelationshipRecord>;
  drawingPaths: Set<string>;
  changed: boolean;
}

interface RelationshipCollection {
  parts: Map<string, string>;
  relationships: Map<string, string>;
}

interface RelationshipPartSize {
  uncompressedSize?: number;
}

interface ZipFileWithSize extends JSZip.JSZipObject {
  _data?: RelationshipPartSize;
}

export interface PreviewRendererCompatibilityReport {
  hiddenDrawingObjectsSuppressed: number;
  backgroundFillShapesNormalized: number;
  backgroundStyleFillReferencesRemoved: number;
  themeBackgroundImageFillsResolved: number;
  pictureGeometryImagesPromoted: number;
  pictureGeometryImagesSkipped: number;
  themeOverrideColorsNormalized: number;
  groupFillReferencesInherited: number;
  layoutPlaceholderFillsInherited: number;
  smartArtImageReferencesRepaired: number;
  smartArtRelationshipPartsUpdated: number;
  smartArtImageShapesPromoted: number;
  duotoneImageReferencesNormalized: number;
  tiledImageFillsSized?: number;
  pictureGeometryInherited?: number;
  browserLineBreaksSuppressed?: number;
  textColoredHyperlinks?: number;
  defaultLineSpacingLevelsFilled?: number;
  compatibilityPartsSkipped: number;
}

export interface PreviewRendererCompatibilityOptions {
  suppressHiddenDrawingObjects?: boolean;
  normalizeBackgroundFills?: boolean;
  normalizeThemeBackgroundImageFills?: boolean;
  normalizeThemeBackgroundImageEffects?: boolean;
  normalizePictureFillGeometry?: boolean;
  normalizeThemeOverrideColors?: boolean;
  normalizeGroupFills?: boolean;
  inheritLayoutPlaceholderFills?: boolean;
  repairSmartArtRelationships?: boolean;
  normalizeDuotoneImages?: boolean;
  sizeTiledImageFills?: boolean;
  suppressBrowserOnlyLineBreaks?: boolean;
  followTextColoredHyperlinks?: boolean;
  fillDefaultLineSpacing?: boolean;
}

interface RGBColor {
  r: number;
  g: number;
  b: number;
}

interface DuotoneImageEffect {
  dark: RGBColor;
  light: RGBColor;
  brightness: number;
  contrast: number;
  opacity: number;
}

function browserXmlPlatform(): XmlPlatform | null {
  if (
    typeof DOMParser === "undefined" ||
    typeof XMLSerializer === "undefined"
  ) {
    return null;
  }
  const parser = new DOMParser();
  const serializer = new XMLSerializer();
  return {
    parseFromString: (source, mimeType) =>
      parser.parseFromString(source, mimeType),
    serialize: (document) => serializer.serializeToString(document),
  };
}

function childElements(parent: Element): Element[] {
  return Array.from(parent.childNodes).filter(
    (child): child is Element => child.nodeType === 1,
  );
}

function childElement(
  parent: Element,
  namespace: string,
  localName: string,
): Element | null {
  return (
    childElements(parent).find(
      (child) =>
        child.namespaceURI === namespace && child.localName === localName,
    ) ?? null
  );
}

function hasHiddenDrawingObject(shape: Element): boolean {
  const nonVisualPropertiesName = PRESENTATION_NON_VISUAL_PROPERTIES.get(
    shape.localName,
  );
  if (!nonVisualPropertiesName) return false;
  const nonVisualProperties = childElement(
    shape,
    PRESENTATION_NS,
    nonVisualPropertiesName,
  );
  const properties = nonVisualProperties
    ? childElement(nonVisualProperties, PRESENTATION_NS, "cNvPr")
    : null;
  const hidden = properties?.getAttribute("hidden")?.toLowerCase();
  return hidden === "1" || hidden === "true" || hidden === "on";
}

function suppressHiddenDrawingObjectsInContainer(container: Element): number {
  let suppressed = 0;
  for (const child of childElements(container)) {
    if (
      child.namespaceURI !== PRESENTATION_NS ||
      !PRESENTATION_DRAWABLE_NAMES.has(child.localName)
    ) {
      continue;
    }
    if (hasHiddenDrawingObject(child)) {
      container.removeChild(child);
      suppressed += 1;
    } else if (child.localName === "grpSp") {
      suppressed += suppressHiddenDrawingObjectsInContainer(child);
    }
  }
  return suppressed;
}

function suppressHiddenDrawingObjects(
  files: PptxFiles,
  platform: XmlPlatform,
): { objectsSuppressed: number; partsSkipped: number } {
  const partMaps = [
    { expectedRoot: "sld", parts: files.slides },
    { expectedRoot: "sldLayout", parts: files.slideLayouts },
    { expectedRoot: "sldMaster", parts: files.slideMasters },
  ];
  let objectsSuppressed = 0;
  let partsSkipped = 0;

  for (const { expectedRoot, parts } of partMaps) {
    for (const [path, source] of parts) {
      if (!source.includes("cNvPr") || !source.includes("hidden")) continue;
      const document = parseXml(source, platform, MAX_XML_DOCUMENT_CHARS);
      const root = document?.documentElement;
      if (!document || !root) {
        partsSkipped += 1;
        continue;
      }
      if (
        root.namespaceURI !== PRESENTATION_NS ||
        root.localName !== expectedRoot
      ) {
        continue;
      }

      let suppressedInPart = 0;
      for (const shapeTree of elementsWithLocalName(document, "spTree")) {
        if (shapeTree.namespaceURI === PRESENTATION_NS) {
          suppressedInPart +=
            suppressHiddenDrawingObjectsInContainer(shapeTree);
        }
      }
      if (suppressedInPart === 0) continue;
      try {
        parts.set(path, platform.serialize(document));
        objectsSuppressed += suppressedInPart;
      } catch {
        partsSkipped += 1;
      }
    }
  }

  return { objectsSuppressed, partsSkipped };
}

function elementsWithLocalName(
  document: Document,
  localName: string,
): Element[] {
  return Array.from(document.getElementsByTagName("*")).filter(
    (element): element is Element =>
      element.nodeType === 1 && element.localName === localName,
  );
}

function parseXml(
  source: string,
  platform: XmlPlatform,
  maxChars: number,
): Document | null {
  if (
    source.length === 0 ||
    source.length > maxChars ||
    /<!DOCTYPE\b/i.test(source)
  ) {
    return null;
  }
  try {
    const parsed = platform.parseFromString(source, "application/xml");
    if (
      parsed.doctype ||
      !parsed.documentElement ||
      elementsWithLocalName(parsed, "parsererror").length > 0
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function boundedPositiveInteger(value: string | null): bigint | null {
  if (!value || !/^\d{1,20}$/.test(value)) return null;
  try {
    const integer = BigInt(value);
    return integer > 0n ? integer : null;
  } catch {
    return null;
  }
}

function readSlideSize(
  presentationXml: string,
  platform: XmlPlatform,
): SlideSize | null {
  const document = parseXml(presentationXml, platform, MAX_XML_DOCUMENT_CHARS);
  const presentation = document?.documentElement;
  if (
    !presentation ||
    presentation.namespaceURI !== PRESENTATION_NS ||
    presentation.localName !== "presentation"
  ) {
    return null;
  }
  const size = childElement(presentation, PRESENTATION_NS, "sldSz");
  if (!size) return null;
  const width = boundedPositiveInteger(size.getAttribute("cx"));
  const height = boundedPositiveInteger(size.getAttribute("cy"));
  return width && height ? { width, height } : null;
}

function isFirstDrawableChild(shape: Element, tree: Element): boolean {
  const drawableNames = new Set([
    "sp",
    "cxnSp",
    "pic",
    "graphicFrame",
    "grpSp",
  ]);
  const firstDrawable = childElements(tree).find(
    (child) =>
      child.namespaceURI === PRESENTATION_NS &&
      drawableNames.has(child.localName),
  );
  return firstDrawable === shape;
}

function explicitSolidSlideBackgroundFill(
  commonSlideData: Element,
): Element | null {
  const backgrounds = childElements(commonSlideData).filter(
    (child) =>
      child.namespaceURI === PRESENTATION_NS && child.localName === "bg",
  );
  if (backgrounds.length !== 1) return null;
  const background = backgrounds[0];
  if (!background) return null;
  const backgroundProperties = childElements(background);
  if (
    backgroundProperties.length !== 1 ||
    backgroundProperties[0]?.namespaceURI !== PRESENTATION_NS ||
    backgroundProperties[0].localName !== "bgPr" ||
    backgroundProperties[0].attributes.length !== 0
  ) {
    return null;
  }
  const properties = backgroundProperties[0];
  const propertyChildren = childElements(properties);
  const fills = propertyChildren.filter(
    (child) =>
      child.namespaceURI === DRAWING_NS &&
      DRAWING_FILL_NAMES.has(child.localName),
  );
  if (fills.length !== 1 || fills[0]?.localName !== "solidFill") return null;
  for (const child of propertyChildren) {
    if (child === fills[0]) continue;
    if (
      child.namespaceURI === DRAWING_NS &&
      child.localName === "effectLst" &&
      childElements(child).length === 0
    ) {
      continue;
    }
    return null;
  }
  return fills[0] ?? null;
}

function isFullCanvasRectangle(
  shape: Element,
  slideTree: Element,
  slideSize: SlideSize,
): boolean {
  if (
    shape.namespaceURI !== PRESENTATION_NS ||
    shape.localName !== "sp" ||
    !isFirstDrawableChild(shape, slideTree)
  ) {
    return false;
  }
  const spProperties = childElement(shape, PRESENTATION_NS, "spPr");
  if (!spProperties) return false;
  const transform = childElement(spProperties, DRAWING_NS, "xfrm");
  const offset = transform ? childElement(transform, DRAWING_NS, "off") : null;
  const extent = transform ? childElement(transform, DRAWING_NS, "ext") : null;
  const presetGeometry = childElement(spProperties, DRAWING_NS, "prstGeom");
  if (
    !offset ||
    !extent ||
    !presetGeometry ||
    presetGeometry.getAttribute("prst") !== "rect"
  ) {
    return false;
  }
  return (
    offset.getAttribute("x") === "0" &&
    offset.getAttribute("y") === "0" &&
    boundedPositiveInteger(extent.getAttribute("cx")) === slideSize.width &&
    boundedPositiveInteger(extent.getAttribute("cy")) === slideSize.height
  );
}

function hasExplicitNoFill(properties: Element): boolean {
  const fills = childElements(properties).filter(
    (child) =>
      child.namespaceURI === DRAWING_NS &&
      DRAWING_FILL_NAMES.has(child.localName),
  );
  return fills.length === 1 && fills[0]?.localName === "noFill";
}

function removeStyleFillReference(shape: Element): boolean {
  const styles = childElements(shape).filter(
    (child) =>
      child.namespaceURI === PRESENTATION_NS && child.localName === "style",
  );
  if (styles.length !== 1) return false;
  const style = styles[0];
  if (!style) return false;
  const fillReferences = childElements(style).filter(
    (child) =>
      child.namespaceURI === DRAWING_NS && child.localName === "fillRef",
  );
  if (fillReferences.length !== 1) return false;
  const fillReference = fillReferences[0];
  if (!fillReference) return false;
  style.removeChild(fillReference);
  return true;
}

function optionalStyleFillReference(shape: Element): {
  valid: boolean;
  fillReference: Element | null;
} {
  const styles = childElements(shape).filter(
    (child) =>
      child.namespaceURI === PRESENTATION_NS && child.localName === "style",
  );
  if (styles.length > 1) return { valid: false, fillReference: null };
  const style = styles[0];
  if (!style) return { valid: true, fillReference: null };
  const fillReferences = childElements(style).filter(
    (child) =>
      child.namespaceURI === DRAWING_NS && child.localName === "fillRef",
  );
  if (fillReferences.length > 1) {
    return { valid: false, fillReference: null };
  }
  return { valid: true, fillReference: fillReferences[0] ?? null };
}

interface BackgroundFillNormalizationResult {
  shapesNormalized: number;
  styleFillReferencesRemoved: number;
}

function hasNoDirectFill(properties: Element): boolean {
  const fills = childElements(properties).filter(
    (child) =>
      child.namespaceURI === DRAWING_NS &&
      DRAWING_FILL_NAMES.has(child.localName),
  );
  return (
    fills.length === 0 ||
    (fills.length === 1 && fills[0]?.localName === "noFill")
  );
}

function replaceDirectFill(properties: Element, fill: Element): boolean {
  const fills = childElements(properties).filter(
    (child) =>
      child.namespaceURI === DRAWING_NS &&
      DRAWING_FILL_NAMES.has(child.localName),
  );
  if (fills.length > 1) return false;
  const clonedFill = fill.cloneNode(true);
  const existingFill = fills[0];
  if (existingFill) {
    properties.replaceChild(clonedFill, existingFill);
    return true;
  }

  const afterFillNames = new Set([
    "ln",
    "effectLst",
    "effectDag",
    "scene3d",
    "sp3d",
    "extLst",
  ]);
  const insertBefore = childElements(properties).find(
    (child) =>
      child.namespaceURI === DRAWING_NS && afterFillNames.has(child.localName),
  );
  properties.insertBefore(clonedFill, insertBefore ?? null);
  return true;
}

function normalizeSlideBackgroundFill(
  files: PptxFiles,
  platform: XmlPlatform,
): BackgroundFillNormalizationResult {
  const slideSize = readSlideSize(files.presentation, platform);
  if (!slideSize) {
    return { shapesNormalized: 0, styleFillReferencesRemoved: 0 };
  }
  let scannedChars = 0;
  let normalizedShapes = 0;
  let styleFillReferencesRemoved = 0;
  const changedSlides = new Map<string, string>();

  for (const [path, source] of files.slides) {
    if (!/^ppt\/slides\/slide\d+\.xml$/.test(path)) continue;
    if (
      source.length > MAX_XML_DOCUMENT_CHARS ||
      scannedChars + source.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      break;
    }
    scannedChars += source.length;
    const document = parseXml(source, platform, MAX_XML_DOCUMENT_CHARS);
    const root = document?.documentElement;
    if (
      !document ||
      !root ||
      root.namespaceURI !== PRESENTATION_NS ||
      root.localName !== "sld"
    ) {
      continue;
    }
    const commonSlideData = childElement(root, PRESENTATION_NS, "cSld");
    const slideTree = commonSlideData
      ? childElement(commonSlideData, PRESENTATION_NS, "spTree")
      : null;
    if (!slideTree || !commonSlideData) continue;
    const slideBackgroundFill =
      explicitSolidSlideBackgroundFill(commonSlideData);

    let changed = false;
    let changedOnSlide = 0;
    let styleFillReferencesRemovedOnSlide = 0;
    for (const shape of childElements(slideTree)) {
      if (shape.namespaceURI !== PRESENTATION_NS || shape.localName !== "sp") {
        continue;
      }
      const properties = childElement(shape, PRESENTATION_NS, "spPr");
      const fullCanvas = isFullCanvasRectangle(shape, slideTree, slideSize);
      const usesBackgroundFill = /^(?:1|true)$/i.test(
        shape.getAttribute("useBgFill") ?? "",
      );
      if (
        !fullCanvas &&
        properties &&
        slideBackgroundFill &&
        usesBackgroundFill &&
        hasNoDirectFill(properties)
      ) {
        const styleReference = optionalStyleFillReference(shape);
        if (
          styleReference.valid &&
          replaceDirectFill(properties, slideBackgroundFill)
        ) {
          if (styleReference.fillReference) {
            styleReference.fillReference.parentNode?.removeChild(
              styleReference.fillReference,
            );
            styleFillReferencesRemovedOnSlide += 1;
          }
          shape.removeAttribute("useBgFill");
          changed = true;
          changedOnSlide += 1;
          continue;
        }
      }
      if (
        fullCanvas &&
        properties &&
        slideBackgroundFill &&
        usesBackgroundFill &&
        hasNoDirectFill(properties)
      ) {
        const styleReference = optionalStyleFillReference(shape);
        if (
          styleReference.valid &&
          replaceDirectFill(properties, slideBackgroundFill)
        ) {
          if (styleReference.fillReference) {
            styleReference.fillReference.parentNode?.removeChild(
              styleReference.fillReference,
            );
            styleFillReferencesRemovedOnSlide += 1;
          }
          shape.removeAttribute("useBgFill");
          changed = true;
          changedOnSlide += 1;
        }
        continue;
      }
      if (!fullCanvas) continue;
      if (
        properties &&
        hasNoDirectFill(properties) &&
        (usesBackgroundFill || hasExplicitNoFill(properties)) &&
        removeStyleFillReference(shape)
      ) {
        changed = true;
        styleFillReferencesRemovedOnSlide += 1;
      }
    }
    if (changed) {
      try {
        changedSlides.set(path, platform.serialize(document));
        normalizedShapes += changedOnSlide;
        styleFillReferencesRemoved += styleFillReferencesRemovedOnSlide;
      } catch {
        // Keep the original parsed slide if preview serialization fails.
      }
    }
  }

  for (const [path, updated] of changedSlides) files.slides.set(path, updated);
  return {
    shapesNormalized: normalizedShapes,
    styleFillReferencesRemoved,
  };
}

interface DirectDrawingFill {
  fill: Element | null;
  ambiguous: boolean;
}

function readDirectDrawingFill(properties: Element | null): DirectDrawingFill {
  if (!properties) return { fill: null, ambiguous: false };
  const fills = childElements(properties).filter(
    (child) =>
      child.namespaceURI === DRAWING_NS &&
      DRAWING_FILL_NAMES.has(child.localName),
  );
  return {
    fill: fills.length === 1 ? (fills[0] ?? null) : null,
    ambiguous: fills.length > 1,
  };
}

interface GroupFillFrame {
  container: Element;
  inheritedFill: Element | null;
  depth: number;
}

interface GroupFillNormalizationResult {
  referencesInherited: number;
  partsSkipped: number;
}

function normalizeGroupFills(
  files: PptxFiles,
  platform: XmlPlatform,
): GroupFillNormalizationResult {
  const result = { referencesInherited: 0, partsSkipped: 0 };
  let scannedChars = 0;
  const changedSlides = new Map<string, string>();

  for (const [path, source] of files.slides) {
    if (!/^ppt\/slides\/slide\d+\.xml$/.test(path)) continue;
    if (
      source.length > MAX_XML_DOCUMENT_CHARS ||
      scannedChars + source.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      result.partsSkipped += 1;
      break;
    }
    scannedChars += source.length;
    const document = parseXml(source, platform, MAX_XML_DOCUMENT_CHARS);
    const root = document?.documentElement;
    if (
      !document ||
      !root ||
      root.namespaceURI !== PRESENTATION_NS ||
      root.localName !== "sld"
    ) {
      result.partsSkipped += 1;
      continue;
    }
    const commonSlideData = childElement(root, PRESENTATION_NS, "cSld");
    const slideTree = commonSlideData
      ? childElement(commonSlideData, PRESENTATION_NS, "spTree")
      : null;
    if (!slideTree) continue;

    const rootGroupPropertiesMatches = childElements(slideTree).filter(
      (child) =>
        child.namespaceURI === PRESENTATION_NS && child.localName === "grpSpPr",
    );
    const rootGroupProperties = rootGroupPropertiesMatches[0] ?? null;
    const rootFill = readDirectDrawingFill(rootGroupProperties);
    const pendingReplacements: { properties: Element; fill: Element }[] = [];
    const stack: GroupFillFrame[] = [
      {
        container: slideTree,
        inheritedFill: rootFill.ambiguous ? null : rootFill.fill,
        depth: 0,
      },
    ];
    let drawableCount = 0;
    let slideSkipped =
      rootFill.ambiguous || rootGroupPropertiesMatches.length > 1;

    while (stack.length > 0 && !slideSkipped) {
      const frame = stack.pop();
      if (!frame) break;
      for (const shape of childElements(frame.container)) {
        if (
          shape.namespaceURI !== PRESENTATION_NS ||
          !PRESENTATION_DRAWABLE_NAMES.has(shape.localName)
        ) {
          continue;
        }
        drawableCount += 1;
        if (drawableCount > MAX_GROUP_FILL_DRAWABLES_PER_SLIDE) {
          slideSkipped = true;
          break;
        }

        if (shape.localName === "grpSp") {
          if (frame.depth >= MAX_GROUP_FILL_DEPTH) {
            slideSkipped = true;
            break;
          }
          const groupPropertiesMatches = childElements(shape).filter(
            (child) =>
              child.namespaceURI === PRESENTATION_NS &&
              child.localName === "grpSpPr",
          );
          if (groupPropertiesMatches.length > 1) {
            slideSkipped = true;
            break;
          }
          const groupProperties = groupPropertiesMatches[0] ?? null;
          const groupFill = readDirectDrawingFill(groupProperties);
          if (groupFill.ambiguous) {
            slideSkipped = true;
            break;
          }
          const inheritedFill =
            groupFill.fill?.localName === "grpFill"
              ? frame.inheritedFill
              : (groupFill.fill ?? frame.inheritedFill);
          stack.push({
            container: shape,
            inheritedFill,
            depth: frame.depth + 1,
          });
          continue;
        }

        const shapePropertiesMatches = childElements(shape).filter(
          (child) =>
            child.namespaceURI === PRESENTATION_NS &&
            child.localName === "spPr",
        );
        if (shapePropertiesMatches.length > 1) {
          slideSkipped = true;
          break;
        }
        const shapeProperties = shapePropertiesMatches[0] ?? null;
        const shapeFill = readDirectDrawingFill(shapeProperties);
        if (shapeFill.ambiguous) {
          slideSkipped = true;
          break;
        }
        if (
          shapeFill.fill?.localName === "grpFill" &&
          frame.inheritedFill &&
          shapeProperties
        ) {
          pendingReplacements.push({
            properties: shapeProperties,
            fill: frame.inheritedFill,
          });
        }
      }
    }

    if (slideSkipped) {
      result.partsSkipped += 1;
      continue;
    }
    if (pendingReplacements.length === 0) continue;

    const validatedReplacements: {
      properties: Element;
      fill: Element;
      existing: Element;
    }[] = [];
    for (const replacement of pendingReplacements) {
      const existing = readDirectDrawingFill(replacement.properties).fill;
      if (!existing || existing.localName !== "grpFill") {
        slideSkipped = true;
        break;
      }
      validatedReplacements.push({ ...replacement, existing });
    }
    if (slideSkipped) {
      result.partsSkipped += 1;
      continue;
    }

    for (const { properties, fill, existing } of validatedReplacements) {
      properties.replaceChild(document.importNode(fill, true), existing);
    }

    try {
      changedSlides.set(path, platform.serialize(document));
      result.referencesInherited += pendingReplacements.length;
    } catch {
      result.partsSkipped += 1;
    }
  }

  for (const [path, updated] of changedSlides) files.slides.set(path, updated);
  return result;
}

interface PlaceholderIdentity {
  index: string | null;
  type: string;
}

function packageRelationshipPartPath(sourcePath: string): string | null {
  const match = sourcePath.match(
    /^ppt\/(slides|slideLayouts|slideMasters)\/([^/]+\.xml)$/,
  );
  return match ? `ppt/${match[1]}/_rels/${match[2]}.rels` : null;
}

function placeholderIdentity(shape: Element): PlaceholderIdentity | null {
  if (shape.namespaceURI !== PRESENTATION_NS || shape.localName !== "sp") {
    return null;
  }
  const nonVisual = childElement(shape, PRESENTATION_NS, "nvSpPr");
  const nonVisualProperties = nonVisual
    ? childElement(nonVisual, PRESENTATION_NS, "nvPr")
    : null;
  const placeholder = nonVisualProperties
    ? childElement(nonVisualProperties, PRESENTATION_NS, "ph")
    : null;
  if (!placeholder) return null;

  const rawIndex = placeholder.hasAttribute("idx")
    ? placeholder.getAttribute("idx")
    : null;
  if (rawIndex !== null && !/^\d{1,8}$/.test(rawIndex)) return null;
  const rawType = placeholder.getAttribute("type") ?? "";
  if (rawType.length > 40 || hasControlCharacters(rawType)) return null;
  return { index: rawIndex, type: rawType || "obj" };
}

function samePlaceholder(
  slidePlaceholder: PlaceholderIdentity,
  layoutPlaceholder: PlaceholderIdentity,
): boolean {
  if (slidePlaceholder.index !== null) {
    return layoutPlaceholder.index === slidePlaceholder.index;
  }
  return (
    layoutPlaceholder.index === null &&
    layoutPlaceholder.type === slidePlaceholder.type
  );
}

function xmlElementSignature(element: Element): string {
  const attributes = Array.from(element.attributes)
    .map((attribute) => [
      attribute.namespaceURI ?? "",
      attribute.localName,
      attribute.value,
    ])
    .sort(([leftNamespace, leftName], [rightNamespace, rightName]) =>
      `${leftNamespace}|${leftName}`.localeCompare(
        `${rightNamespace}|${rightName}`,
      ),
    );
  return JSON.stringify([
    element.namespaceURI,
    element.localName,
    attributes,
    childElements(element).map(xmlElementSignature),
  ]);
}

function sameColorMapOverride(
  slideRoot: Element,
  layoutRoot: Element,
): boolean {
  const slideMap = childElement(slideRoot, PRESENTATION_NS, "clrMapOvr");
  const layoutMap = childElement(layoutRoot, PRESENTATION_NS, "clrMapOvr");
  if (!slideMap || !layoutMap) return slideMap === layoutMap;
  return xmlElementSignature(slideMap) === xmlElementSignature(layoutMap);
}

function hasAnyDirectFill(properties: Element): boolean {
  return childElements(properties).some(
    (child) =>
      child.namespaceURI === DRAWING_NS &&
      DRAWING_FILL_NAMES.has(child.localName),
  );
}

function directSolidFill(shape: Element): Element | null {
  const properties = childElement(shape, PRESENTATION_NS, "spPr");
  if (!properties) return null;
  const fills = childElements(properties).filter(
    (child) =>
      child.namespaceURI === DRAWING_NS &&
      DRAWING_FILL_NAMES.has(child.localName),
  );
  return fills.length === 1 && fills[0]?.localName === "solidFill"
    ? fills[0]
    : null;
}

function ensureShapeProperties(
  shape: Element,
  document: Document,
): Element | null {
  const existing = childElement(shape, PRESENTATION_NS, "spPr");
  if (existing) return existing;
  if (!childElement(shape, PRESENTATION_NS, "nvSpPr")) return null;

  const prefix = shape.lookupPrefix(PRESENTATION_NS);
  const properties = document.createElementNS(
    PRESENTATION_NS,
    prefix ? `${prefix}:spPr` : "spPr",
  );
  const insertBefore = childElements(shape).find(
    (child) =>
      child.namespaceURI === PRESENTATION_NS &&
      (child.localName === "style" || child.localName === "txBody"),
  );
  shape.insertBefore(properties, insertBefore ?? null);
  return properties;
}

function insertInheritedSolidFill(
  properties: Element,
  sourceFill: Element,
  document: Document,
): boolean {
  if (hasAnyDirectFill(properties)) return false;
  const inheritedFill = document.importNode(sourceFill, true);
  const afterFillNames = new Set([
    "ln",
    "effectLst",
    "effectDag",
    "scene3d",
    "sp3d",
    "extLst",
  ]);
  const insertBefore = childElements(properties).find(
    (child) =>
      child.namespaceURI === DRAWING_NS && afterFillNames.has(child.localName),
  );
  properties.insertBefore(inheritedFill, insertBefore ?? null);
  return true;
}

function inheritLayoutPlaceholderSolidFills(
  files: PptxFiles,
  platform: XmlPlatform,
): number {
  let scannedChars = 0;
  let inheritedFills = 0;
  const changedSlides = new Map<string, string>();
  const layoutDocuments = new Map<string, Document | null>();

  for (const [slidePath, slideXml] of files.slides) {
    if (!/^ppt\/slides\/slide\d+\.xml$/.test(slidePath)) continue;
    if (
      slideXml.length > MAX_XML_DOCUMENT_CHARS ||
      scannedChars + slideXml.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      break;
    }
    scannedChars += slideXml.length;

    const relationshipPath = packageRelationshipPartPath(slidePath);
    const relationshipXml = relationshipPath
      ? files.slideRels.get(relationshipPath)
      : undefined;
    if (
      !relationshipXml ||
      relationshipXml.length > MAX_RELATIONSHIP_XML_CHARS ||
      scannedChars + relationshipXml.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      continue;
    }
    scannedChars += relationshipXml.length;
    const relationshipDocument = parseXml(
      relationshipXml,
      platform,
      MAX_RELATIONSHIP_XML_CHARS,
    );
    const parsedRelationships = relationshipDocument
      ? relationshipRecords(relationshipDocument)
      : null;
    if (!parsedRelationships) continue;

    const layoutRelationships = [
      ...parsedRelationships.records.values(),
    ].filter(
      (relationship) =>
        relationship.type === SLIDE_LAYOUT_RELATIONSHIP_TYPE &&
        isInternalTargetMode(relationship.targetMode),
    );
    if (layoutRelationships.length !== 1) continue;
    const layoutPath = resolveInternalPackageTarget(
      slidePath,
      layoutRelationships[0]?.target ?? "",
    );
    if (!layoutPath || !/^ppt\/slideLayouts\/[^/]+\.xml$/.test(layoutPath)) {
      continue;
    }

    const layoutXml = files.slideLayouts.get(layoutPath);
    if (!layoutXml || layoutXml.length > MAX_XML_DOCUMENT_CHARS) continue;
    let layoutDocument = layoutDocuments.get(layoutPath);
    if (layoutDocument === undefined) {
      if (scannedChars + layoutXml.length > MAX_COMPATIBILITY_XML_CHARS) break;
      scannedChars += layoutXml.length;
      layoutDocument = parseXml(layoutXml, platform, MAX_XML_DOCUMENT_CHARS);
      const layoutRoot = layoutDocument?.documentElement;
      if (
        !layoutRoot ||
        layoutRoot.namespaceURI !== PRESENTATION_NS ||
        layoutRoot.localName !== "sldLayout"
      ) {
        layoutDocument = null;
      }
      layoutDocuments.set(layoutPath, layoutDocument);
    }
    const layoutRoot = layoutDocument?.documentElement;
    if (!layoutRoot) continue;

    const slideDocument = parseXml(slideXml, platform, MAX_XML_DOCUMENT_CHARS);
    const slideRoot = slideDocument?.documentElement;
    if (
      !slideDocument ||
      !slideRoot ||
      slideRoot.namespaceURI !== PRESENTATION_NS ||
      slideRoot.localName !== "sld" ||
      // A slide-specific color map can make a copied theme fill resolve
      // differently from the layout's original fill. Skip mismatched maps.
      !sameColorMapOverride(slideRoot, layoutRoot)
    ) {
      continue;
    }

    const slideCommonData = childElement(slideRoot, PRESENTATION_NS, "cSld");
    const layoutCommonData = childElement(layoutRoot, PRESENTATION_NS, "cSld");
    const slideTree = slideCommonData
      ? childElement(slideCommonData, PRESENTATION_NS, "spTree")
      : null;
    const layoutTree = layoutCommonData
      ? childElement(layoutCommonData, PRESENTATION_NS, "spTree")
      : null;
    if (!slideTree || !layoutTree) continue;

    const layoutShapes = childElements(layoutTree).filter(
      (shape) =>
        shape.namespaceURI === PRESENTATION_NS && shape.localName === "sp",
    );
    let changedOnSlide = 0;
    for (const slideShape of childElements(slideTree)) {
      const identity = placeholderIdentity(slideShape);
      if (
        !identity ||
        /^(?:1|true)$/i.test(slideShape.getAttribute("useBgFill") ?? "")
      ) {
        continue;
      }
      const matchingShapes = layoutShapes.filter((layoutShape) => {
        const layoutIdentity = placeholderIdentity(layoutShape);
        return (
          layoutIdentity !== null && samePlaceholder(identity, layoutIdentity)
        );
      });
      if (matchingShapes.length !== 1) continue;
      const layoutShape = matchingShapes[0];
      if (!layoutShape) continue;
      const fill = directSolidFill(layoutShape);
      if (!fill) continue;

      const properties = ensureShapeProperties(slideShape, slideDocument);
      if (
        !properties ||
        !insertInheritedSolidFill(properties, fill, slideDocument)
      ) {
        continue;
      }
      changedOnSlide += 1;
    }

    if (changedOnSlide > 0) {
      try {
        changedSlides.set(slidePath, platform.serialize(slideDocument));
        inheritedFills += changedOnSlide;
      } catch {
        // Keep the parsed slide unchanged if preview serialization fails.
      }
    }
  }

  for (const [path, updated] of changedSlides) files.slides.set(path, updated);
  return inheritedFills;
}

function picturePlaceholderIdentity(
  picture: Element,
): PlaceholderIdentity | null {
  if (picture.namespaceURI !== PRESENTATION_NS) return null;
  const nonVisual = childElement(
    picture,
    PRESENTATION_NS,
    picture.localName === "pic" ? "nvPicPr" : "nvSpPr",
  );
  const properties = nonVisual
    ? childElement(nonVisual, PRESENTATION_NS, "nvPr")
    : null;
  const placeholder = properties
    ? childElement(properties, PRESENTATION_NS, "ph")
    : null;
  if (!placeholder) return null;
  const rawIndex = placeholder.getAttribute("idx");
  if (rawIndex !== null && !/^\d{1,8}$/.test(rawIndex)) return null;
  const rawType = placeholder.getAttribute("type") ?? "";
  if (rawType.length > 40 || hasControlCharacters(rawType)) return null;
  return { index: rawIndex, type: rawType || "obj" };
}

/**
 * A picture placeholder without its own geometry takes the layout
 * placeholder's prstGeom/custGeom (PowerPoint clips the picture to it).
 */
function inheritLayoutPictureGeometry(
  files: PptxFiles,
  platform: XmlPlatform,
): number {
  let inherited = 0;
  let scannedChars = 0;
  const changedSlides = new Map<string, string>();
  for (const [slidePath, slideXml] of files.slides) {
    if (!/^ppt\/slides\/slide\d+\.xml$/.test(slidePath)) continue;
    if (!slideXml.includes(":pic>") || !slideXml.includes(":ph")) continue;
    if (
      slideXml.length > MAX_XML_DOCUMENT_CHARS ||
      scannedChars + slideXml.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      break;
    }
    scannedChars += slideXml.length;
    const relationshipPath = packageRelationshipPartPath(slidePath);
    const relationshipXml = relationshipPath
      ? files.slideRels.get(relationshipPath)
      : undefined;
    if (
      !relationshipXml ||
      relationshipXml.length > MAX_RELATIONSHIP_XML_CHARS
    ) {
      continue;
    }
    const relationshipDocument = parseXml(
      relationshipXml,
      platform,
      MAX_RELATIONSHIP_XML_CHARS,
    );
    const records = relationshipDocument
      ? relationshipRecords(relationshipDocument)
      : null;
    const layouts = records
      ? [...records.records.values()].filter(
          (relationship) =>
            relationship.type === SLIDE_LAYOUT_RELATIONSHIP_TYPE &&
            isInternalTargetMode(relationship.targetMode),
        )
      : [];
    if (layouts.length !== 1) continue;
    const layoutPath = resolveInternalPackageTarget(
      slidePath,
      layouts[0]?.target ?? "",
    );
    const layoutXml = layoutPath
      ? files.slideLayouts.get(layoutPath)
      : undefined;
    if (!layoutXml || layoutXml.length > MAX_XML_DOCUMENT_CHARS) continue;
    const layoutDocument = parseXml(
      layoutXml,
      platform,
      MAX_XML_DOCUMENT_CHARS,
    );
    const slideDocument = parseXml(slideXml, platform, MAX_XML_DOCUMENT_CHARS);
    const layoutTree = layoutDocument
      ? elementsWithLocalName(layoutDocument, "spTree")[0]
      : undefined;
    const slideTree = slideDocument
      ? elementsWithLocalName(slideDocument, "spTree")[0]
      : undefined;
    if (!slideDocument || !layoutTree || !slideTree) continue;
    const layoutPlaceholders = childElements(layoutTree).filter(
      (shape) =>
        shape.namespaceURI === PRESENTATION_NS &&
        (shape.localName === "sp" || shape.localName === "pic"),
    );
    let changed = 0;
    for (const picture of childElements(slideTree)) {
      if (
        picture.namespaceURI !== PRESENTATION_NS ||
        picture.localName !== "pic"
      ) {
        continue;
      }
      const identity = picturePlaceholderIdentity(picture);
      const properties = childElement(picture, PRESENTATION_NS, "spPr");
      if (
        !identity ||
        !properties ||
        childElement(properties, DRAWING_NS, "prstGeom") ||
        childElement(properties, DRAWING_NS, "custGeom")
      ) {
        continue;
      }
      const matches = layoutPlaceholders.filter((shape) => {
        const layoutIdentity = picturePlaceholderIdentity(shape);
        return (
          layoutIdentity !== null && samePlaceholder(identity, layoutIdentity)
        );
      });
      const layoutProperties =
        matches.length === 1 && matches[0]
          ? childElement(matches[0], PRESENTATION_NS, "spPr")
          : null;
      const geometry = layoutProperties
        ? (childElement(layoutProperties, DRAWING_NS, "custGeom") ??
          childElement(layoutProperties, DRAWING_NS, "prstGeom"))
        : null;
      if (
        !geometry ||
        (geometry.localName === "prstGeom" &&
          geometry.getAttribute("prst") === "rect")
      ) {
        continue;
      }
      const copy = slideDocument.importNode(geometry, true) as Element;
      const transform = childElement(properties, DRAWING_NS, "xfrm");
      properties.insertBefore(
        copy,
        transform ? transform.nextSibling : properties.firstChild,
      );
      changed += 1;
    }
    if (!changed) continue;
    try {
      changedSlides.set(slidePath, platform.serialize(slideDocument));
      inherited += changed;
    } catch {
      // Keep the parsed slide unchanged if preview serialization fails.
    }
  }
  for (const [path, updated] of changedSlides) files.slides.set(path, updated);
  return inherited;
}

function relationshipSourcePath(relationshipPath: string): string | null {
  const match = relationshipPath.match(
    /^(ppt\/(?:slides|slideLayouts|slideMasters))\/_rels\/([^/]+\.xml)\.rels$/,
  );
  return match ? `${match[1]}/${match[2]}` : null;
}

function relationshipPathFor(sourcePath: string): string | null {
  const match = sourcePath.match(
    /^(ppt\/(?:slides|slideLayouts|slideMasters|diagrams))\/([^/]+\.xml)$/,
  );
  return match ? `${match[1]}/_rels/${match[2]}.rels` : null;
}

function isInternalTargetMode(targetMode: string | null): boolean {
  return targetMode === null || targetMode.toLowerCase() === "internal";
}

function hasControlCharacters(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code < 0x20 || code === 0x7f) return true;
  }
  return false;
}

function resolveInternalPackageTarget(
  sourcePath: string,
  target: string,
): string | null {
  if (
    !target ||
    target.length > 2048 ||
    target.includes("\\") ||
    target.includes("?") ||
    target.includes("#") ||
    hasControlCharacters(target) ||
    /^[a-z][a-z\d+.-]*:/i.test(target) ||
    target.startsWith("/")
  ) {
    return null;
  }

  const sourceDirectory = sourcePath.split("/").slice(0, -1);
  const parts = sourceDirectory;
  for (const rawSegment of target.split("/")) {
    if (!rawSegment) {
      return null;
    }
    let segment: string;
    try {
      segment = decodeURIComponent(rawSegment);
    } catch {
      return null;
    }
    if (
      segment.includes("/") ||
      segment.includes("\\") ||
      hasControlCharacters(segment)
    ) {
      return null;
    }
    if (segment === ".") continue;
    if (segment === "..") {
      if (parts.length === 0) return null;
      parts.pop();
      continue;
    }
    parts.push(segment);
  }
  return parts.join("/");
}

function isSafeZipPart(zip: JSZip, path: string): ZipFileWithSize | null {
  const file = zip.file(path) as ZipFileWithSize | null;
  if (
    !file ||
    file.dir ||
    file.name !== path ||
    (file.unsafeOriginalName !== undefined && file.unsafeOriginalName !== path)
  ) {
    return null;
  }
  const size = file._data?.uncompressedSize;
  if (!Number.isSafeInteger(size) || size === undefined || size < 0) {
    return null;
  }
  return file;
}

async function readBoundedZipXml(
  zip: JSZip,
  path: string,
  maxChars: number,
): Promise<string | null> {
  const file = isSafeZipPart(zip, path);
  if (!file || file._data?.uncompressedSize === undefined) return null;
  if (file._data.uncompressedSize > maxChars) return null;
  try {
    const xml = await file.async("string");
    return xml.length <= maxChars ? xml : null;
  } catch {
    return null;
  }
}

function relationshipRecords(
  document: Document,
): { root: Element; records: Map<string, RelationshipRecord> } | null {
  const root = document.documentElement;
  if (
    !root ||
    root.namespaceURI !== PACKAGE_RELATIONSHIP_NS ||
    root.localName !== "Relationships"
  ) {
    return null;
  }
  const records = new Map<string, RelationshipRecord>();
  for (const element of childElements(root)) {
    if (
      element.namespaceURI !== PACKAGE_RELATIONSHIP_NS ||
      element.localName !== "Relationship"
    ) {
      return null;
    }
    const id = element.getAttribute("Id");
    const type = element.getAttribute("Type");
    const target = element.getAttribute("Target");
    const targetMode = element.hasAttribute("TargetMode")
      ? element.getAttribute("TargetMode")
      : null;
    if (
      !id ||
      !type ||
      !target ||
      (targetMode !== null &&
        targetMode.toLowerCase() !== "internal" &&
        targetMode.toLowerCase() !== "external") ||
      records.has(id)
    ) {
      return null;
    }
    records.set(id, { id, type, target, targetMode, element });
  }
  return { root, records };
}

function relationshipCollections(files: PptxFiles): RelationshipCollection[] {
  return [
    { parts: files.slides, relationships: files.slideRels },
    { parts: files.slideLayouts, relationships: files.slideLayoutRels },
    { parts: files.slideMasters, relationships: files.slideMasterRels },
  ];
}

function relationshipsForPart(
  files: PptxFiles,
  sourcePath: string,
): Map<string, string> | null {
  if (sourcePath.startsWith("ppt/slides/")) return files.slideRels;
  if (sourcePath.startsWith("ppt/slideLayouts/")) return files.slideLayoutRels;
  if (sourcePath.startsWith("ppt/slideMasters/")) return files.slideMasterRels;
  return null;
}

function relatedInternalPart(
  files: PptxFiles,
  sourcePath: string,
  relationshipType: string,
  platform: XmlPlatform,
): string | null {
  const relationshipPath = relationshipPathFor(sourcePath);
  const relationships = relationshipsForPart(files, sourcePath);
  const source = relationshipPath ? relationships?.get(relationshipPath) : null;
  const document = source
    ? parseXml(source, platform, MAX_RELATIONSHIP_XML_CHARS)
    : null;
  const parsed = document ? relationshipRecords(document) : null;
  if (!parsed) return null;
  const matches = [...parsed.records.values()].filter((record) =>
    record.type.endsWith(`/${relationshipType}`),
  );
  if (
    matches.length !== 1 ||
    !isInternalTargetMode(matches[0]?.targetMode ?? null)
  ) {
    return null;
  }
  const match = matches[0];
  return match ? resolveInternalPackageTarget(sourcePath, match.target) : null;
}

interface ThemeBackgroundImageFillResult {
  fillsResolved: number;
  partsSkipped: number;
}

function masterPathForPart(
  files: PptxFiles,
  sourcePath: string,
  platform: XmlPlatform,
): string | null {
  if (/^ppt\/slideMasters\/[^/]+\.xml$/.test(sourcePath)) return sourcePath;
  if (/^ppt\/slideLayouts\/[^/]+\.xml$/.test(sourcePath)) {
    return relatedInternalPart(files, sourcePath, "slideMaster", platform);
  }
  if (/^ppt\/slides\/[^/]+\.xml$/.test(sourcePath)) {
    const layoutPath = relatedInternalPart(
      files,
      sourcePath,
      "slideLayout",
      platform,
    );
    return layoutPath
      ? relatedInternalPart(files, layoutPath, "slideMaster", platform)
      : null;
  }
  return null;
}

function supportedStretchBlipFill(fill: Element): {
  blip: Element;
  relationshipId: string;
} | null {
  if (
    fill.namespaceURI !== DRAWING_NS ||
    fill.localName !== "blipFill" ||
    !hasExactAttributes(fill, { rotWithShape: "1" })
  ) {
    return null;
  }
  const fillChildren = childElements(fill);
  const blips = fillChildren.filter(
    (child) => child.namespaceURI === DRAWING_NS && child.localName === "blip",
  );
  const stretches = fillChildren.filter(
    (child) =>
      child.namespaceURI === DRAWING_NS && child.localName === "stretch",
  );
  if (
    fillChildren.length !== 2 ||
    blips.length !== 1 ||
    stretches.length !== 1 ||
    fillChildren.some((child) => child.namespaceURI !== DRAWING_NS)
  ) {
    return null;
  }
  const blip = blips[0];
  const stretch = stretches[0];
  if (!blip || !stretch || childElements(stretch).length > 1) return null;
  const stretchChild = childElements(stretch)[0];
  if (
    stretchChild &&
    (stretchChild.namespaceURI !== DRAWING_NS ||
      stretchChild.localName !== "fillRect" ||
      stretchChild.attributes.length > 0 ||
      childElements(stretchChild).length > 0)
  ) {
    return null;
  }
  const relationshipId = blip.getAttributeNS(OFFICE_RELATIONSHIP_NS, "embed");
  const blipAttributes = Array.from(blip.attributes);
  if (
    blipAttributes.filter(
      (attribute) =>
        attribute.namespaceURI === OFFICE_RELATIONSHIP_NS &&
        attribute.localName === "embed",
    ).length !== 1 ||
    blipAttributes.some(
      (attribute) =>
        attribute.namespaceURI !== XMLNS_NS &&
        !(
          attribute.namespaceURI === OFFICE_RELATIONSHIP_NS &&
          attribute.localName === "embed"
        ),
    ) ||
    !relationshipId ||
    childElements(blip).length > 1 ||
    childElements(blip).some(
      (child) =>
        child.namespaceURI !== DRAWING_NS ||
        !["duotone", "lum"].includes(child.localName),
    )
  ) {
    return null;
  }
  return { blip, relationshipId };
}

async function normalizeThemeBackgroundImageFills(
  files: PptxFiles,
  sourceArchive: JSZip,
  platform: XmlPlatform,
  normalizeImageEffects: boolean,
): Promise<ThemeBackgroundImageFillResult> {
  let fillsResolved = 0;
  let partsSkipped = 0;
  let scannedChars = 0;
  let partsScanned = 0;
  let relationshipSequence = 1;
  let totalPixels = 0;
  let totalBytes = 0;
  const variants = new Map<
    string,
    { mediaPath: string; bytes: Uint8Array; pixels: number }
  >();
  const nonce =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const collections = relationshipCollections(files);

  for (const collection of collections) {
    for (const [sourcePath, sourceXml] of collection.parts) {
      const skip = () => {
        partsSkipped += 1;
      };
      if (
        sourceXml.length > MAX_XML_DOCUMENT_CHARS ||
        scannedChars + sourceXml.length > MAX_COMPATIBILITY_XML_CHARS
      ) {
        skip();
        break;
      }
      scannedChars += sourceXml.length;
      if (!sourceXml.includes("bgRef")) continue;
      partsScanned += 1;
      if (partsScanned > MAX_THEME_BACKGROUND_FILL_PARTS) {
        skip();
        break;
      }

      const relationshipPath = relationshipPathFor(sourcePath);
      const sourceRelationshipXml = relationshipPath
        ? collection.relationships.get(relationshipPath)
        : null;
      const document = parseXml(sourceXml, platform, MAX_XML_DOCUMENT_CHARS);
      const relationshipDocument = sourceRelationshipXml
        ? parseXml(sourceRelationshipXml, platform, MAX_RELATIONSHIP_XML_CHARS)
        : null;
      const sourceRelationships = relationshipDocument
        ? relationshipRecords(relationshipDocument)
        : null;
      const root = document?.documentElement;
      if (
        !document ||
        !root ||
        !relationshipPath ||
        !sourceRelationshipXml ||
        !relationshipDocument ||
        !sourceRelationships
      ) {
        skip();
        continue;
      }

      const commonSlideData = childElement(root, PRESENTATION_NS, "cSld");
      const background = commonSlideData
        ? childElement(commonSlideData, PRESENTATION_NS, "bg")
        : null;
      if (!background) continue;
      const backgroundChildren = childElements(background);
      const references = backgroundChildren.filter(
        (child) =>
          child.namespaceURI === PRESENTATION_NS && child.localName === "bgRef",
      );
      const backgroundReference = references[0];
      if (!backgroundReference) continue;
      const rawIndex = backgroundReference.getAttribute("idx");
      const index =
        rawIndex && /^\d{1,5}$/.test(rawIndex) ? Number(rawIndex) : NaN;
      if (
        references.length !== 1 ||
        backgroundChildren.length !== 1 ||
        backgroundReference.attributes.length !== 1 ||
        !Number.isSafeInteger(index) ||
        index < 1001
      ) {
        continue;
      }

      const colors = childElements(backgroundReference);
      if (
        colors.length !== 1 ||
        colors[0]?.namespaceURI !== DRAWING_NS ||
        colors[0]?.localName !== "schemeClr"
      ) {
        skip();
        continue;
      }

      const masterPath = masterPathForPart(files, sourcePath, platform);
      const themePath = masterPath
        ? relatedInternalPart(files, masterPath, "theme", platform)
        : null;
      const themeXml = themePath ? files.themes.get(themePath) : null;
      const themeDocument = themeXml
        ? parseXml(themeXml, platform, MAX_XML_DOCUMENT_CHARS)
        : null;
      const themeRoot = themeDocument?.documentElement;
      const themeElements = themeRoot
        ? childElement(themeRoot, DRAWING_NS, "themeElements")
        : null;
      const formatScheme = themeElements
        ? childElement(themeElements, DRAWING_NS, "fmtScheme")
        : null;
      const backgroundFillStyles = formatScheme
        ? childElement(formatScheme, DRAWING_NS, "bgFillStyleLst")
        : null;
      const fillStyle = backgroundFillStyles
        ? childElements(backgroundFillStyles)[index - 1001]
        : null;
      if (
        !themePath ||
        !themeXml ||
        !themeDocument ||
        !themeRoot ||
        themeRoot.namespaceURI !== DRAWING_NS ||
        themeRoot.localName !== "theme" ||
        !fillStyle
      ) {
        skip();
        continue;
      }
      const supportedFill = supportedStretchBlipFill(fillStyle);
      if (!supportedFill) {
        if (fillStyle.localName === "blipFill") skip();
        continue;
      }

      const themeRelationshipPath = relationshipPathForTheme(themePath);
      const themeRelationshipXml = themeRelationshipPath
        ? await readBoundedZipXml(
            sourceArchive,
            themeRelationshipPath,
            MAX_RELATIONSHIP_XML_CHARS,
          )
        : null;
      const themeRelationshipDocument = themeRelationshipXml
        ? parseXml(themeRelationshipXml, platform, MAX_RELATIONSHIP_XML_CHARS)
        : null;
      const themeRelationships = themeRelationshipDocument
        ? relationshipRecords(themeRelationshipDocument)
        : null;
      const imageRelationship = themeRelationships?.records.get(
        supportedFill.relationshipId,
      );
      const mediaPath = imageRelationship
        ? resolveInternalPackageTarget(themePath, imageRelationship.target)
        : null;
      if (
        !themeRelationshipDocument ||
        !themeRelationships ||
        !imageRelationship ||
        imageRelationship.type !== IMAGE_RELATIONSHIP_TYPE ||
        !isInternalTargetMode(imageRelationship.targetMode) ||
        !mediaPath ||
        !/^ppt\/media\/[^/]+$/i.test(mediaPath)
      ) {
        skip();
        continue;
      }

      let targetMediaPath = mediaPath;
      const imageEffects = childElements(supportedFill.blip);
      if (imageEffects.length > 0 && normalizeImageEffects) {
        const theme = themeContextForPart(
          files,
          sourcePath,
          document,
          platform,
        );
        const placeholderColor = resolveDrawingColor(
          colors[0] as Element,
          theme,
        );
        const effect = placeholderColor
          ? parseDuotoneEffect(supportedFill.blip, theme, placeholderColor)
          : null;
        if (!effect) {
          skip();
          continue;
        }
        const variantKey = JSON.stringify([mediaPath, effectSignature(effect)]);
        let variant = variants.get(variantKey);
        if (!variant) {
          const original = await imageBytesForRelationship(
            files,
            mediaPath,
            imageRelationship.target,
          );
          if (!original) {
            skip();
            continue;
          }
          const transformed = await renderDuotonePng(
            original,
            mediaPath,
            effect,
          );
          if (
            !transformed ||
            totalPixels + transformed.pixels > MAX_DUOTONE_TOTAL_PIXELS ||
            totalBytes + transformed.bytes.byteLength > MAX_DUOTONE_TOTAL_BYTES
          ) {
            skip();
            continue;
          }
          totalPixels += transformed.pixels;
          totalBytes += transformed.bytes.byteLength;
          variant = {
            mediaPath: `ppt/media/_presenter-preview-theme-bg-${nonce}-${variants.size + 1}.png`,
            bytes: transformed.bytes,
            pixels: transformed.pixels,
          };
          variants.set(variantKey, variant);
          files.media.set(variant.mediaPath, variant.bytes);
        }
        targetMediaPath = variant.mediaPath;
      }

      const nextRelationshipId = () => {
        let candidate: string;
        do {
          candidate = `rIdPresenterPreviewBackground${relationshipSequence++}`;
        } while (sourceRelationships.records.has(candidate));
        return candidate;
      };
      const relationshipId = nextRelationshipId();
      const copiedFill = document.importNode(fillStyle, true) as Element;
      const copiedBlip = childElement(copiedFill, DRAWING_NS, "blip");
      if (!copiedBlip) {
        skip();
        continue;
      }
      for (const effectName of ["duotone", "lum"]) {
        const effectNode = childElement(copiedBlip, DRAWING_NS, effectName);
        if (effectNode) copiedBlip.removeChild(effectNode);
      }
      const relationshipPrefix =
        copiedBlip.lookupPrefix(OFFICE_RELATIONSHIP_NS) ?? "r";
      copiedBlip.setAttributeNS(
        OFFICE_RELATIONSHIP_NS,
        `${relationshipPrefix}:embed`,
        relationshipId,
      );
      const directBackground = document.createElementNS(
        PRESENTATION_NS,
        `${root.lookupPrefix(PRESENTATION_NS) ?? "p"}:bgPr`,
      );
      directBackground.appendChild(copiedFill);
      const relationshipNamespacePrefix =
        relationshipDocument.documentElement.lookupPrefix(
          PACKAGE_RELATIONSHIP_NS,
        ) ?? "";
      const relationshipElement = relationshipDocument.createElementNS(
        PACKAGE_RELATIONSHIP_NS,
        relationshipNamespacePrefix
          ? `${relationshipNamespacePrefix}:Relationship`
          : "Relationship",
      );
      relationshipElement.setAttribute("Id", relationshipId);
      relationshipElement.setAttribute("Type", IMAGE_RELATIONSHIP_TYPE);
      relationshipElement.setAttribute(
        "Target",
        relativePackageTarget(sourcePath, targetMediaPath),
      );
      try {
        const relationshipRoot = relationshipDocument.documentElement;
        relationshipRoot.appendChild(relationshipElement);
        background.replaceChild(directBackground, backgroundReference);
        const updatedSource = platform.serialize(document);
        const updatedRelationships = platform.serialize(relationshipDocument);
        collection.parts.set(sourcePath, updatedSource);
        collection.relationships.set(relationshipPath, updatedRelationships);
        fillsResolved += 1;
      } catch {
        partsSkipped += 1;
      }
    }
  }
  return { fillsResolved, partsSkipped };
}

function relationshipPathForTheme(themePath: string): string | null {
  const match = themePath.match(/^(ppt\/theme)\/([^/]+\.xml)$/);
  return match ? `${match[1]}/_rels/${match[2]}.rels` : null;
}

interface DrawingThemeContext {
  document: Document | null;
  colorMap: Map<string, string>;
}

const THEME_COLOR_MAP_KEYS = [
  "bg1",
  "tx1",
  "bg2",
  "tx2",
  "accent1",
  "accent2",
  "accent3",
  "accent4",
  "accent5",
  "accent6",
  "hlink",
  "folHlink",
];

const THEME_COLOR_NAMES = new Set([
  "dk1",
  "lt1",
  "dk2",
  "lt2",
  ...THEME_COLOR_MAP_KEYS.slice(4),
  "hlink",
  "folHlink",
]);

const THEME_COLOR_SLOT_NAMES = [
  "dk1",
  "lt1",
  "dk2",
  "lt2",
  ...THEME_COLOR_MAP_KEYS.slice(4),
];

function colorSchemeForThemeDocument(document: Document): Element | null {
  const root = document.documentElement;
  if (!root || root.namespaceURI !== DRAWING_NS) return null;
  const directColorScheme = childElement(root, DRAWING_NS, "clrScheme");
  if (directColorScheme) return directColorScheme;
  const themeElements = childElement(root, DRAWING_NS, "themeElements");
  return themeElements
    ? childElement(themeElements, DRAWING_NS, "clrScheme")
    : null;
}

function isThemeOverrideDocument(document: Document): boolean {
  const root = document.documentElement;
  if (
    !root ||
    root.namespaceURI !== DRAWING_NS ||
    root.localName !== "themeOverride"
  ) {
    return false;
  }
  const colorSchemes = childElements(root).filter(
    (child) =>
      child.namespaceURI === DRAWING_NS && child.localName === "clrScheme",
  );
  const colorScheme = colorSchemes[0];
  if (!colorScheme || colorSchemes.length !== 1) return false;
  const slots = childElements(colorScheme);
  return (
    slots.length === THEME_COLOR_SLOT_NAMES.length &&
    new Set(slots.map((slot) => slot.localName)).size ===
      THEME_COLOR_SLOT_NAMES.length &&
    THEME_COLOR_SLOT_NAMES.every((name) =>
      slots.some(
        (slot) =>
          slot.namespaceURI === DRAWING_NS &&
          slot.localName === name &&
          childElements(slot).length === 1,
      ),
    )
  );
}

function parseThemeColorMap(element: Element | null): Map<string, string> {
  const result = new Map<string, string>();
  if (!element) return result;
  for (const key of THEME_COLOR_MAP_KEYS) {
    const value = element.getAttribute(key);
    if (!value || !THEME_COLOR_NAMES.has(value)) return new Map();
    result.set(key, value);
  }
  return result;
}

function themeContextForPart(
  files: PptxFiles,
  sourcePath: string,
  sourceDocument: Document,
  platform: XmlPlatform,
  themeOverrideDocument: Document | null = null,
): DrawingThemeContext {
  let masterPath: string | null = null;
  if (sourcePath.startsWith("ppt/slideMasters/")) {
    masterPath = sourcePath;
  } else if (sourcePath.startsWith("ppt/slideLayouts/")) {
    masterPath = relatedInternalPart(
      files,
      sourcePath,
      "slideMaster",
      platform,
    );
  } else if (sourcePath.startsWith("ppt/slides/")) {
    const layoutPath = relatedInternalPart(
      files,
      sourcePath,
      "slideLayout",
      platform,
    );
    masterPath = layoutPath
      ? relatedInternalPart(files, layoutPath, "slideMaster", platform)
      : null;
  }
  const masterXml = masterPath ? files.slideMasters.get(masterPath) : null;
  const masterDocument =
    masterPath === sourcePath
      ? sourceDocument
      : masterXml
        ? parseXml(masterXml, platform, MAX_XML_DOCUMENT_CHARS)
        : null;
  const masterRoot = masterDocument?.documentElement ?? null;
  const masterColorMap = parseThemeColorMap(
    masterRoot ? childElement(masterRoot, PRESENTATION_NS, "clrMap") : null,
  );
  let colorMap = masterColorMap;
  const sourceRoot = sourceDocument.documentElement;
  const colorMapOverride = childElement(
    sourceRoot,
    PRESENTATION_NS,
    "clrMapOvr",
  );
  if (colorMapOverride) {
    const explicitOverride = childElement(
      colorMapOverride,
      DRAWING_NS,
      "overrideClrMapping",
    );
    const masterOverride = childElement(
      colorMapOverride,
      DRAWING_NS,
      "masterClrMapping",
    );
    if (explicitOverride) colorMap = parseThemeColorMap(explicitOverride);
    else if (!masterOverride) colorMap = new Map();
  }

  const themePath = masterPath
    ? relatedInternalPart(files, masterPath, "theme", platform)
    : null;
  const themeXml = themePath ? files.themes.get(themePath) : null;
  return {
    document:
      themeOverrideDocument ??
      (themeXml ? parseXml(themeXml, platform, MAX_XML_DOCUMENT_CHARS) : null),
    colorMap,
  };
}

function clampByte(value: number): number {
  return Math.max(0, Math.min(255, value));
}

function rgbToHsl(color: RGBColor): [number, number, number] {
  const r = color.r / 255;
  const g = color.g / 255;
  const b = color.b / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  const lightness = (max + min) / 2;
  if (delta === 0) return [0, 0, lightness];
  const saturation = delta / (1 - Math.abs(2 * lightness - 1));
  let hue: number;
  if (max === r) hue = ((g - b) / delta) % 6;
  else if (max === g) hue = (b - r) / delta + 2;
  else hue = (r - g) / delta + 4;
  return [(((hue / 6) % 1) + 1) % 1, saturation, lightness];
}

function hslToRgb(
  hue: number,
  saturation: number,
  lightness: number,
): RGBColor {
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
  const scaledHue = hue * 6;
  const secondary = chroma * (1 - Math.abs((scaledHue % 2) - 1));
  const [red, green, blue] =
    scaledHue < 1
      ? [chroma, secondary, 0]
      : scaledHue < 2
        ? [secondary, chroma, 0]
        : scaledHue < 3
          ? [0, chroma, secondary]
          : scaledHue < 4
            ? [0, secondary, chroma]
            : scaledHue < 5
              ? [secondary, 0, chroma]
              : [chroma, 0, secondary];
  const offset = lightness - chroma / 2;
  return {
    r: clampByte((red + offset) * 255),
    g: clampByte((green + offset) * 255),
    b: clampByte((blue + offset) * 255),
  };
}

function srgbToLinear(channel: number): number {
  const value = channel / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function linearToSrgb(value: number): number {
  const clamped = Math.min(1, Math.max(0, value));
  return clampByte(
    255 *
      (clamped <= 0.0031308
        ? clamped * 12.92
        : 1.055 * clamped ** (1 / 2.4) - 0.055),
  );
}

function mapLinear(
  color: RGBColor,
  transform: (value: number) => number,
): RGBColor {
  return {
    r: linearToSrgb(transform(srgbToLinear(color.r))),
    g: linearToSrgb(transform(srgbToLinear(color.g))),
    b: linearToSrgb(transform(srgbToLinear(color.b))),
  };
}

function applyColorTransforms(
  element: Element,
  base: RGBColor,
): RGBColor | null {
  let color = { ...base };
  for (const transform of childElements(element)) {
    if (transform.namespaceURI !== DRAWING_NS) return null;
    const value = transform.getAttribute("val");
    if (!value || !/^-?\d{1,7}$/.test(value)) return null;
    const amount = Number(value) / 100_000;
    if (!Number.isFinite(amount)) return null;
    if (transform.localName === "tint" && amount >= 0 && amount <= 1) {
      // PowerPoint mixes tint and shade in linear light (measured: black at
      // 98% tint renders 39, 50% tint renders 188).
      color = mapLinear(color, (value) => value * amount + (1 - amount));
    } else if (transform.localName === "shade" && amount >= 0 && amount <= 1) {
      color = mapLinear(color, (value) => value * amount);
    } else if (transform.localName === "satMod" && amount >= 0 && amount <= 8) {
      // PowerPoint scales saturation without a cap and clamps the final RGB
      // (measured: FA8D3D at 400% renders 255,97,0).
      const [hue, saturation, lightness] = rgbToHsl(color);
      color = hslToRgb(hue, saturation * amount, lightness);
    } else if (transform.localName === "lumMod" && amount >= 0 && amount <= 8) {
      const [hue, saturation, lightness] = rgbToHsl(color);
      color = hslToRgb(hue, saturation, Math.min(1, lightness * amount));
    } else {
      return null;
    }
  }
  return color;
}

function parseHexColor(value: string | null): RGBColor | null {
  if (!value || !/^[0-9a-f]{6}$/i.test(value)) return null;
  return {
    r: Number.parseInt(value.slice(0, 2), 16),
    g: Number.parseInt(value.slice(2, 4), 16),
    b: Number.parseInt(value.slice(4, 6), 16),
  };
}

function resolveDrawingColor(
  element: Element,
  theme: DrawingThemeContext,
  depth = 0,
  placeholderColor: RGBColor | null = null,
): RGBColor | null {
  if (element.namespaceURI !== DRAWING_NS || depth > 3) {
    return null;
  }
  let base: RGBColor | null = null;
  if (element.localName === "srgbClr") {
    base = parseHexColor(element.getAttribute("val"));
  } else if (element.localName === "sysClr") {
    base = parseHexColor(element.getAttribute("lastClr"));
  } else if (element.localName === "prstClr") {
    const preset = element.getAttribute("val")?.toLowerCase();
    if (preset === "black") base = { r: 0, g: 0, b: 0 };
    else if (preset === "white") base = { r: 255, g: 255, b: 255 };
  } else if (element.localName === "schemeClr") {
    const name = element.getAttribute("val");
    if (name === "phClr") {
      base = placeholderColor ? { ...placeholderColor } : null;
    } else {
      const mappedName = name ? (theme.colorMap.get(name) ?? name) : null;
      const colorScheme = theme.document
        ? colorSchemeForThemeDocument(theme.document)
        : null;
      const themeColor =
        mappedName && colorScheme
          ? childElement(colorScheme, DRAWING_NS, mappedName)
          : null;
      const themeBase = themeColor ? childElements(themeColor)[0] : null;
      base = themeBase
        ? resolveDrawingColor(themeBase, theme, depth + 1, placeholderColor)
        : null;
    }
  }
  return base ? applyColorTransforms(element, base) : null;
}

function relatedThemeOverridePart(
  files: PptxFiles,
  slidePath: string,
  platform: XmlPlatform,
): string | null {
  const relationshipPath = relationshipPathFor(slidePath);
  const relationships = relationshipPath
    ? files.slideRels.get(relationshipPath)
    : null;
  const document = relationships
    ? parseXml(relationships, platform, MAX_RELATIONSHIP_XML_CHARS)
    : null;
  const parsed = document ? relationshipRecords(document) : null;
  if (!parsed) return null;
  const matches = [...parsed.records.values()].filter(
    (relationship) => relationship.type === THEME_OVERRIDE_RELATIONSHIP_TYPE,
  );
  if (
    matches.length !== 1 ||
    !isInternalTargetMode(matches[0]?.targetMode ?? null)
  ) {
    return null;
  }
  return resolveInternalPackageTarget(slidePath, matches[0]?.target ?? "");
}

function isWithinElement(element: Element, ancestor: Element): boolean {
  let current: Node | null = element;
  while (current) {
    if (current === ancestor) return true;
    current = current.parentNode;
  }
  return false;
}

function colorToHex(color: RGBColor): string {
  return [color.r, color.g, color.b]
    .map((channel) => Math.round(channel).toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
}

async function normalizeSlideThemeOverrideColors(
  files: PptxFiles,
  platform: XmlPlatform,
  zip: JSZip,
): Promise<{ referencesNormalized: number; partsSkipped: number }> {
  let referencesNormalized = 0;
  let partsSkipped = 0;
  let scannedChars = 0;
  const themeDocuments = new Map<string, Document | null>();
  const changedSlides = new Map<string, string>();

  for (const [slidePath, source] of files.slides) {
    if (!/^ppt\/slides\/slide\d+\.xml$/i.test(slidePath)) continue;
    const relationshipPath = relationshipPathFor(slidePath);
    const relationshipXml = relationshipPath
      ? files.slideRels.get(relationshipPath)
      : undefined;
    if (!relationshipXml?.includes(THEME_OVERRIDE_RELATIONSHIP_TYPE)) continue;
    if (
      relationshipXml.length > MAX_RELATIONSHIP_XML_CHARS ||
      scannedChars + relationshipXml.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      partsSkipped += 1;
      continue;
    }
    scannedChars += relationshipXml.length;

    const themeOverridePath = relatedThemeOverridePart(
      files,
      slidePath,
      platform,
    );
    if (
      !themeOverridePath ||
      !/^ppt\/theme\/[^/]+\.xml$/i.test(themeOverridePath)
    ) {
      partsSkipped += 1;
      continue;
    }

    let themeOverrideDocument = themeDocuments.get(themeOverridePath);
    if (themeOverrideDocument === undefined) {
      if (themeDocuments.size >= MAX_THEME_OVERRIDE_PARTS) {
        partsSkipped += 1;
        continue;
      }
      const remainingBudget = MAX_COMPATIBILITY_XML_CHARS - scannedChars;
      const themeOverrideXml = await readBoundedZipXml(
        zip,
        themeOverridePath,
        Math.min(MAX_XML_DOCUMENT_CHARS, remainingBudget),
      );
      if (!themeOverrideXml) {
        themeDocuments.set(themeOverridePath, null);
        partsSkipped += 1;
        continue;
      }
      scannedChars += themeOverrideXml.length;
      const parsedThemeOverride = parseXml(
        themeOverrideXml,
        platform,
        MAX_XML_DOCUMENT_CHARS,
      );
      themeOverrideDocument =
        parsedThemeOverride && isThemeOverrideDocument(parsedThemeOverride)
          ? parsedThemeOverride
          : null;
      themeDocuments.set(themeOverridePath, themeOverrideDocument);
    }
    if (!themeOverrideDocument) {
      partsSkipped += 1;
      continue;
    }

    if (
      source.length > MAX_XML_DOCUMENT_CHARS ||
      scannedChars + source.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      partsSkipped += 1;
      continue;
    }
    scannedChars += source.length;
    const document = parseXml(source, platform, MAX_XML_DOCUMENT_CHARS);
    const root = document?.documentElement;
    if (
      !document ||
      !root ||
      root.namespaceURI !== PRESENTATION_NS ||
      root.localName !== "sld"
    ) {
      partsSkipped += 1;
      continue;
    }
    const commonSlideData = childElement(root, PRESENTATION_NS, "cSld");
    if (!commonSlideData) {
      partsSkipped += 1;
      continue;
    }

    const theme = themeContextForPart(
      files,
      slidePath,
      document,
      platform,
      themeOverrideDocument,
    );
    if (theme.colorMap.size !== THEME_COLOR_MAP_KEYS.length) {
      partsSkipped += 1;
      continue;
    }

    const replacements: Array<{ source: Element; replacement: Element }> = [];
    for (const schemeColor of elementsWithLocalName(document, "schemeClr")) {
      if (
        schemeColor.namespaceURI !== DRAWING_NS ||
        !isWithinElement(schemeColor, commonSlideData) ||
        schemeColor.attributes.length !== 1 ||
        !schemeColor.hasAttribute("val")
      ) {
        continue;
      }
      const name = schemeColor.getAttribute("val");
      const mappedName = name ? (theme.colorMap.get(name) ?? name) : null;
      if (!mappedName || !THEME_COLOR_NAMES.has(mappedName)) continue;
      const color = resolveDrawingColor(schemeColor, theme);
      if (!color) continue;

      const prefix = schemeColor.lookupPrefix(DRAWING_NS);
      const replacement = document.createElementNS(
        DRAWING_NS,
        prefix ? `${prefix}:srgbClr` : "srgbClr",
      );
      replacement.setAttribute("val", colorToHex(color));
      replacements.push({ source: schemeColor, replacement });
    }

    if (
      referencesNormalized + replacements.length >
      MAX_THEME_OVERRIDE_REFERENCES
    ) {
      partsSkipped += 1;
      continue;
    }
    if (replacements.length === 0) continue;

    for (const { source: schemeColor, replacement } of replacements) {
      schemeColor.parentNode?.replaceChild(replacement, schemeColor);
    }
    try {
      changedSlides.set(slidePath, platform.serialize(document));
      referencesNormalized += replacements.length;
    } catch {
      partsSkipped += 1;
    }
  }

  for (const [slidePath, source] of changedSlides) {
    files.slides.set(slidePath, source);
  }
  return { referencesNormalized, partsSkipped };
}

function hasExactAttributes(
  element: Element,
  expected: Record<string, string>,
): boolean {
  return (
    element.attributes.length === Object.keys(expected).length &&
    Object.entries(expected).every(
      ([name, value]) => element.getAttribute(name) === value,
    )
  );
}

function observedClearMaterialPreviewOpacity(blip: Element): number {
  let ancestor: Node | null = blip;
  let picture: Element | null = null;
  while (ancestor?.nodeType === 1) {
    const element = ancestor as Element;
    if (
      element.namespaceURI === PRESENTATION_NS &&
      element.localName === "pic"
    ) {
      picture = element;
      break;
    }
    ancestor = ancestor.parentNode;
  }
  if (
    !picture ||
    picture.parentNode?.nodeType !== 1 ||
    (picture.parentNode as Element).namespaceURI !== PRESENTATION_NS ||
    (picture.parentNode as Element).localName !== "spTree"
  ) {
    return 1;
  }
  const pictureFill = childElement(picture, PRESENTATION_NS, "blipFill");
  const properties = childElement(picture, PRESENTATION_NS, "spPr");
  if (!pictureFill || blip.parentNode !== pictureFill || !properties) return 1;
  if (!childElement(properties, DRAWING_NS, "noFill")) return 1;
  const effects = childElement(properties, DRAWING_NS, "effectLst");
  if (effects && childElements(effects).length > 0) return 1;

  const scene = childElement(properties, DRAWING_NS, "scene3d");
  const format = childElement(properties, DRAWING_NS, "sp3d");
  if (
    !scene ||
    !format ||
    !hasExactAttributes(format, { prstMaterial: "clear" })
  ) {
    return 1;
  }
  const sceneChildren = childElements(scene);
  if (sceneChildren.length !== 2) return 1;
  const camera = childElement(scene, DRAWING_NS, "camera");
  const lightRig = childElement(scene, DRAWING_NS, "lightRig");
  if (
    !camera ||
    !lightRig ||
    !hasExactAttributes(camera, { prst: "orthographicFront" }) ||
    !hasExactAttributes(lightRig, { rig: "chilly", dir: "t" })
  ) {
    return 1;
  }
  const cameraRotation = childElement(camera, DRAWING_NS, "rot");
  const lightRotation = childElement(lightRig, DRAWING_NS, "rot");
  const bevel = childElement(format, DRAWING_NS, "bevelT");
  if (
    childElements(camera).length !== 1 ||
    childElements(lightRig).length !== 1 ||
    childElements(format).length !== 1 ||
    !cameraRotation ||
    !lightRotation ||
    !bevel ||
    !hasExactAttributes(cameraRotation, { lat: "0", lon: "0", rev: "0" }) ||
    !hasExactAttributes(lightRotation, {
      lat: "0",
      lon: "0",
      rev: "18480000",
    }) ||
    !hasExactAttributes(bevel, { h: "63500" })
  ) {
    return 1;
  }

  // This exact clear-material profile was compared against native PowerPoint on
  // the licensed corpus. The browser renderer ignores its picture material, so
  // reduce only the preview alias alpha; source bytes and exports stay intact.
  return OBSERVED_CLEAR_MATERIAL_PREVIEW_ALPHA;
}

function parseDuotoneEffect(
  blip: Element,
  theme: DrawingThemeContext,
  placeholderColor: RGBColor | null = null,
): DuotoneImageEffect | null {
  const children = childElements(blip);
  if (
    children.length < 1 ||
    children.length > 2 ||
    children.some((child) => child.namespaceURI !== DRAWING_NS) ||
    children[0]?.localName !== "duotone" ||
    (children.length === 2 && children[1]?.localName !== "lum")
  ) {
    return null;
  }
  const duotone = children[0];
  if (!duotone) return null;
  const colors = childElements(duotone);
  if (colors.length !== 2) return null;
  const dark = resolveDrawingColor(
    colors[0] as Element,
    theme,
    0,
    placeholderColor,
  );
  const light = resolveDrawingColor(
    colors[1] as Element,
    theme,
    0,
    placeholderColor,
  );
  if (!dark || !light) return null;

  let brightness = 0;
  let contrast = 0;
  const luminance = children[1];
  if (luminance) {
    if (childElements(luminance).length > 0) return null;
    for (const [attribute, fallback] of [
      ["bright", 0],
      ["contrast", 0],
    ] as const) {
      const raw = luminance.getAttribute(attribute);
      const parsed =
        raw === null ? fallback : /^-?\d{1,7}$/.test(raw) ? Number(raw) : NaN;
      if (
        !Number.isSafeInteger(parsed) ||
        parsed < -100_000 ||
        parsed > 100_000
      ) {
        return null;
      }
      if (attribute === "bright") brightness = parsed;
      else contrast = parsed;
    }
  }
  return {
    dark,
    light,
    brightness,
    contrast,
    opacity: observedClearMaterialPreviewOpacity(blip),
  };
}

/**
 * DrawingML a:lum as measured in PowerPoint: bright adds bright x 255, and
 * contrast is a percent change around mid-grey with scale 1/(1-c) for c > 0 and
 * 1+c for c < 0. Both default to 0 (no change).
 */
export function luminanceAdjust(
  value: number,
  bright: number,
  contrast: number,
): number {
  const brightened = value + (bright / 100_000) * 255;
  const change = contrast / 100_000;
  const scale = change >= 0 ? 1 / Math.max(1 - change, 0.001) : 1 + change;
  return clampByte(127.5 + (brightened - 127.5) * scale);
}

function applyDuotonePixels(
  pixels: Uint8ClampedArray,
  effect: DuotoneImageEffect,
): void {
  const applyChannel = (source: number, dark: number, light: number) => {
    const luminance = source / 255;
    const value = dark + (light - dark) * luminance;
    return luminanceAdjust(value, effect.brightness, effect.contrast);
  };
  for (let index = 0; index < pixels.length; index += 4) {
    const sourceRed = pixels[index] ?? 0;
    const sourceGreen = pixels[index + 1] ?? 0;
    const sourceBlue = pixels[index + 2] ?? 0;
    const luminance =
      (0.2126 * sourceRed + 0.7152 * sourceGreen + 0.0722 * sourceBlue) / 255;
    pixels[index] = applyChannel(
      luminance * 255,
      effect.dark.r,
      effect.light.r,
    );
    pixels[index + 1] = applyChannel(
      luminance * 255,
      effect.dark.g,
      effect.light.g,
    );
    pixels[index + 2] = applyChannel(
      luminance * 255,
      effect.dark.b,
      effect.light.b,
    );
    pixels[index + 3] = clampByte((pixels[index + 3] ?? 0) * effect.opacity);
  }
}

function boundedRasterDimensions(
  source: Uint8Array,
  mediaPath: string,
): { width: number; height: number } | null {
  if (/\.png$/i.test(mediaPath)) {
    if (
      source.byteLength < 24 ||
      source[0] !== 0x89 ||
      source[1] !== 0x50 ||
      source[2] !== 0x4e ||
      source[3] !== 0x47 ||
      source[4] !== 0x0d ||
      source[5] !== 0x0a ||
      source[6] !== 0x1a ||
      source[7] !== 0x0a ||
      source[12] !== 0x49 ||
      source[13] !== 0x48 ||
      source[14] !== 0x44 ||
      source[15] !== 0x52
    ) {
      return null;
    }
    const view = new DataView(
      source.buffer,
      source.byteOffset,
      source.byteLength,
    );
    return { width: view.getUint32(16), height: view.getUint32(20) };
  }
  if (
    !/\.jpe?g$/i.test(mediaPath) ||
    source[0] !== 0xff ||
    source[1] !== 0xd8
  ) {
    return null;
  }
  const startLimit = Math.min(source.byteLength, 1024 * 1024);
  let offset = 2;
  while (offset + 4 < startLimit) {
    if (source[offset] !== 0xff) {
      offset += 1;
      continue;
    }
    while (source[offset] === 0xff) offset += 1;
    const marker = source[offset];
    offset += 1;
    if (marker === undefined || marker === 0xd9 || marker === 0xda) {
      break;
    }
    if (
      marker === 0xd8 ||
      marker === 0x01 ||
      (marker >= 0xd0 && marker <= 0xd7)
    ) {
      continue;
    }
    const segmentLength =
      ((source[offset] ?? 0) << 8) | (source[offset + 1] ?? 0);
    if (segmentLength < 2 || offset + segmentLength > startLimit) return null;
    if (
      [
        0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce,
        0xcf,
      ].includes(marker)
    ) {
      const height =
        ((source[offset + 3] ?? 0) << 8) | (source[offset + 4] ?? 0);
      const width =
        ((source[offset + 5] ?? 0) << 8) | (source[offset + 6] ?? 0);
      return { width, height };
    }
    offset += segmentLength;
  }
  return null;
}

async function imageBytesForRelationship(
  files: PptxFiles,
  mediaPath: string,
  target: string,
): Promise<Uint8Array | null> {
  const cached = files.media.get(mediaPath);
  if (cached) return cached;
  try {
    const resolved = await files.mediaResolver?.resolve(target);
    return resolved?.mediaPath === mediaPath ? resolved.data : null;
  } catch {
    return null;
  }
}

async function renderDuotonePng(
  source: Uint8Array,
  mediaPath: string,
  effect: DuotoneImageEffect,
): Promise<{ bytes: Uint8Array; pixels: number } | null> {
  if (
    source.byteLength > MAX_DUOTONE_SOURCE_BYTES ||
    !/\.(?:png|jpe?g)$/i.test(mediaPath) ||
    typeof createImageBitmap !== "function" ||
    typeof document === "undefined"
  ) {
    return null;
  }
  const expectedDimensions = boundedRasterDimensions(source, mediaPath);
  const expectedPixels = expectedDimensions
    ? expectedDimensions.width * expectedDimensions.height
    : 0;
  if (
    !expectedDimensions ||
    !Number.isSafeInteger(expectedPixels) ||
    expectedDimensions.width < 1 ||
    expectedDimensions.height < 1 ||
    expectedPixels > MAX_DUOTONE_SINGLE_IMAGE_PIXELS
  ) {
    return null;
  }
  let bitmap: ImageBitmap | null = null;
  try {
    const copy = source.slice().buffer as ArrayBuffer;
    bitmap = await createImageBitmap(new Blob([copy]));
    const pixels = bitmap.width * bitmap.height;
    if (
      !Number.isSafeInteger(pixels) ||
      bitmap.width < 1 ||
      bitmap.height < 1 ||
      pixels > MAX_DUOTONE_SINGLE_IMAGE_PIXELS ||
      bitmap.width !== expectedDimensions.width ||
      bitmap.height !== expectedDimensions.height
    ) {
      return null;
    }
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return null;
    context.drawImage(bitmap, 0, 0);
    const imageData = context.getImageData(0, 0, bitmap.width, bitmap.height);
    applyDuotonePixels(imageData.data, effect);
    context.putImageData(imageData, 0, 0);
    const outputBlob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/png"),
    );
    if (
      !outputBlob ||
      outputBlob.size === 0 ||
      outputBlob.size > MAX_DUOTONE_OUTPUT_BYTES
    ) {
      return null;
    }
    return { bytes: new Uint8Array(await outputBlob.arrayBuffer()), pixels };
  } catch {
    return null;
  } finally {
    bitmap?.close();
  }
}

function effectSignature(effect: DuotoneImageEffect): string {
  return JSON.stringify(effect);
}

async function normalizeDuotoneImages(
  files: PptxFiles,
  platform: XmlPlatform,
): Promise<{ references: number; partsSkipped: number }> {
  let references = 0;
  let partsSkipped = 0;
  let totalPixels = 0;
  let totalBytes = 0;
  let aliasSequence = 1;
  const variants = new Map<
    string,
    { mediaPath: string; bytes: Uint8Array; pixels: number }
  >();
  const nonce =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

  for (const collection of relationshipCollections(files)) {
    for (const [
      relationshipPath,
      relationshipXml,
    ] of collection.relationships) {
      const sourcePath = relationshipSourcePath(relationshipPath);
      if (!sourcePath || !collection.parts.has(sourcePath)) continue;
      const sourceXml = collection.parts.get(sourcePath) ?? "";
      if (!sourceXml.includes("duotone")) continue;
      if (
        sourceXml.length > MAX_XML_DOCUMENT_CHARS ||
        relationshipXml.length > MAX_RELATIONSHIP_XML_CHARS
      ) {
        partsSkipped += 1;
        continue;
      }
      const document = parseXml(sourceXml, platform, MAX_XML_DOCUMENT_CHARS);
      const relationshipDocument = parseXml(
        relationshipXml,
        platform,
        MAX_RELATIONSHIP_XML_CHARS,
      );
      const parsedRelationships = relationshipDocument
        ? relationshipRecords(relationshipDocument)
        : null;
      if (!document || !relationshipDocument || !parsedRelationships) {
        partsSkipped += 1;
        continue;
      }

      const theme = themeContextForPart(files, sourcePath, document, platform);
      const referencesById = new Map<string, Element[]>();
      for (const blip of elementsWithLocalName(document, "blip")) {
        if (blip.namespaceURI !== DRAWING_NS) continue;
        const relationshipId = blip.getAttributeNS(
          OFFICE_RELATIONSHIP_NS,
          "embed",
        );
        if (!relationshipId) continue;
        const group = referencesById.get(relationshipId) ?? [];
        group.push(blip);
        referencesById.set(relationshipId, group);
      }

      const stagedMedia = new Map<string, Uint8Array>();
      let changedReferences = 0;
      for (const [relationshipId, blips] of referencesById) {
        const relationship = parsedRelationships.records.get(relationshipId);
        if (
          !relationship ||
          relationship.type !== IMAGE_RELATIONSHIP_TYPE ||
          !isInternalTargetMode(relationship.targetMode)
        ) {
          continue;
        }
        const effects = blips.map((blip) => parseDuotoneEffect(blip, theme));
        if (effects.every((effect) => effect === null)) continue;
        const firstEffect = effects[0];
        if (
          !firstEffect ||
          effects.some(
            (effect) =>
              !effect ||
              effectSignature(effect) !== effectSignature(firstEffect),
          )
        ) {
          partsSkipped += 1;
          continue;
        }
        if (
          references + changedReferences + blips.length >
          MAX_DUOTONE_IMAGE_REFERENCES
        ) {
          partsSkipped += 1;
          continue;
        }

        const mediaPath = resolveInternalPackageTarget(
          sourcePath,
          relationship.target,
        );
        if (!mediaPath || !/^ppt\/media\/[^/]+$/i.test(mediaPath)) {
          partsSkipped += 1;
          continue;
        }
        const variantKey = JSON.stringify([
          mediaPath,
          effectSignature(firstEffect),
        ]);
        let variant = variants.get(variantKey);
        if (!variant) {
          const original = await imageBytesForRelationship(
            files,
            mediaPath,
            relationship.target,
          );
          if (!original) {
            partsSkipped += 1;
            continue;
          }
          const transformed = await renderDuotonePng(
            original,
            mediaPath,
            firstEffect,
          );
          if (
            !transformed ||
            totalPixels + transformed.pixels > MAX_DUOTONE_TOTAL_PIXELS ||
            totalBytes + transformed.bytes.byteLength > MAX_DUOTONE_TOTAL_BYTES
          ) {
            partsSkipped += 1;
            continue;
          }
          totalPixels += transformed.pixels;
          totalBytes += transformed.bytes.byteLength;
          const aliasPath = `ppt/media/_presenter-preview-duotone-${nonce}-${aliasSequence++}.png`;
          variant = {
            mediaPath: aliasPath,
            bytes: transformed.bytes,
            pixels: transformed.pixels,
          };
          variants.set(variantKey, variant);
        }

        for (const blip of blips) {
          for (const effectName of ["duotone", "lum"]) {
            const effectNode = childElement(blip, DRAWING_NS, effectName);
            if (effectNode) blip.removeChild(effectNode);
          }
        }
        relationship.element.setAttribute(
          "Target",
          relativePackageTarget(sourcePath, variant.mediaPath),
        );
        stagedMedia.set(variant.mediaPath, variant.bytes);
        changedReferences += blips.length;
      }

      if (changedReferences === 0) continue;
      try {
        const updatedSource = platform.serialize(document);
        const updatedRelationships = platform.serialize(relationshipDocument);
        collection.parts.set(sourcePath, updatedSource);
        collection.relationships.set(relationshipPath, updatedRelationships);
        for (const [path, bytes] of stagedMedia) files.media.set(path, bytes);
        references += changedReferences;
      } catch {
        partsSkipped += 1;
      }
    }
  }
  return { references, partsSkipped };
}

const HYPERLINK_COLOR_NS =
  "http://schemas.microsoft.com/office/drawing/2018/hyperlinkcolor";

/**
 * Office's ahyp:hlinkClr val="tx" keeps a link in the run's text color. The
 * renderer always uses the theme hyperlink color, so the preview copy drops the
 * (inert) click link and keeps PowerPoint's underline.
 */
function followTextColoredHyperlinks(
  files: PptxFiles,
  platform: XmlPlatform,
): number {
  let changedLinks = 0;
  for (const [slidePath, slideXml] of files.slides) {
    if (!slideXml.includes(HYPERLINK_COLOR_NS)) continue;
    if (slideXml.length > MAX_XML_DOCUMENT_CHARS) continue;
    const document = parseXml(slideXml, platform, MAX_XML_DOCUMENT_CHARS);
    if (!document) continue;
    let changed = 0;
    for (const colorChoice of [
      ...document.getElementsByTagNameNS(HYPERLINK_COLOR_NS, "hlinkClr"),
    ]) {
      if (colorChoice.getAttribute("val") !== "tx") continue;
      let link: Node | null = colorChoice.parentNode;
      while (link && (link as Element).localName !== "hlinkClick") {
        link = link.parentNode;
      }
      const properties = link?.parentNode as Element | null;
      if (!link || !properties || properties.localName !== "rPr") continue;
      properties.removeChild(link);
      if (!properties.hasAttribute("u")) properties.setAttribute("u", "sng");
      changed += 1;
    }
    if (!changed) continue;
    try {
      files.slides.set(slidePath, platform.serialize(document));
      changedLinks += changed;
    } catch {
      // Keep the parsed slide unchanged if preview serialization fails.
    }
  }
  return changedLinks;
}

const WORD_JOINER = "\u2060";

/**
 * PowerPoint breaks lines only at spaces and hyphens (then mid-word when a
 * segment cannot fit); browsers also break after "?" and "!", splitting URLs
 * such as images?q=. A zero-width word joiner keeps those inside the word.
 */
export function joinBrowserOnlyBreaks(text: string): string {
  return text.replace(/([?!])(?=[^\s?!\u2060])/g, `$1${WORD_JOINER}`);
}

function suppressBrowserOnlyLineBreaks(
  files: PptxFiles,
  platform: XmlPlatform,
): number {
  let joined = 0;
  let scannedChars = 0;
  for (const [slidePath, slideXml] of files.slides) {
    if (!/[?!][^\s<?!]/.test(slideXml)) continue;
    if (
      slideXml.length > MAX_XML_DOCUMENT_CHARS ||
      scannedChars + slideXml.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      break;
    }
    scannedChars += slideXml.length;
    const document = parseXml(slideXml, platform, MAX_XML_DOCUMENT_CHARS);
    if (!document) continue;
    let changed = 0;
    for (const text of elementsWithLocalName(document, "t")) {
      if (text.namespaceURI !== DRAWING_NS) continue;
      const original = text.textContent ?? "";
      const updated = joinBrowserOnlyBreaks(original);
      if (updated !== original) {
        text.textContent = updated;
        changed += 1;
      }
    }
    if (!changed) continue;
    try {
      files.slides.set(slidePath, platform.serialize(document));
      joined += changed;
    } catch {
      // Keep the parsed slide unchanged if preview serialization fails.
    }
  }
  return joined;
}

const EMU_PER_INCH = 914_400;
export const TILE_WIDTH_ATTRIBUTE = "presenterTileWidthEmu";
export const TILE_HEIGHT_ATTRIBUTE = "presenterTileHeightEmu";

/** Horizontal and vertical DPI from PNG pHYs or JPEG JFIF; 96 when absent. */
export function rasterDpi(
  source: Uint8Array,
  mediaPath: string,
): { x: number; y: number } {
  const fallback = { x: 96, y: 96 };
  const view = new DataView(
    source.buffer,
    source.byteOffset,
    source.byteLength,
  );
  if (/\.png$/i.test(mediaPath)) {
    let offset = 8;
    while (offset + 12 <= source.byteLength && offset < 1024 * 1024) {
      const length = view.getUint32(offset);
      const type = String.fromCharCode(
        ...source.subarray(offset + 4, offset + 8),
      );
      if (type === "pHYs" && length === 9 && offset + 17 <= source.byteLength) {
        const x = view.getUint32(offset + 8);
        const y = view.getUint32(offset + 12);
        // Unit 1 is pixels per metre.
        return source[offset + 16] === 1 && x > 0 && y > 0
          ? { x: x * 0.0254, y: y * 0.0254 }
          : fallback;
      }
      if (type === "IDAT" || type === "IEND") break;
      offset += 12 + length;
    }
    return fallback;
  }
  if (
    /\.jpe?g$/i.test(mediaPath) &&
    source.byteLength > 18 &&
    source[2] === 0xff &&
    source[3] === 0xe0 &&
    String.fromCharCode(...source.subarray(6, 11)) === "JFIF\0"
  ) {
    const unit = source[13];
    const x = view.getUint16(14);
    const y = view.getUint16(16);
    if (x > 0 && y > 0 && (unit === 1 || unit === 2)) {
      return unit === 1 ? { x, y } : { x: x * 2.54, y: y * 2.54 };
    }
  }
  return fallback;
}

/** Record each tiled image fill's PowerPoint tile size (EMU) for the renderer. */
async function sizeTiledImageFills(
  files: PptxFiles,
  platform: XmlPlatform,
): Promise<{ fills: number; partsSkipped: number }> {
  let fills = 0;
  let partsSkipped = 0;
  for (const collection of relationshipCollections(files)) {
    for (const [
      relationshipPath,
      relationshipXml,
    ] of collection.relationships) {
      const sourcePath = relationshipSourcePath(relationshipPath);
      if (!sourcePath || !collection.parts.has(sourcePath)) continue;
      const sourceXml = collection.parts.get(sourcePath) ?? "";
      if (!sourceXml.includes(":tile")) continue;
      if (
        sourceXml.length > MAX_XML_DOCUMENT_CHARS ||
        relationshipXml.length > MAX_RELATIONSHIP_XML_CHARS
      ) {
        partsSkipped += 1;
        continue;
      }
      const document = parseXml(sourceXml, platform, MAX_XML_DOCUMENT_CHARS);
      const relationshipDocument = parseXml(
        relationshipXml,
        platform,
        MAX_RELATIONSHIP_XML_CHARS,
      );
      const records = relationshipDocument
        ? relationshipRecords(relationshipDocument)
        : null;
      if (!document || !records) {
        partsSkipped += 1;
        continue;
      }
      let changed = 0;
      for (const tile of elementsWithLocalName(document, "tile")) {
        const fill = tile.parentNode as Element | null;
        if (
          tile.namespaceURI !== DRAWING_NS ||
          !fill ||
          fill.localName !== "blipFill"
        ) {
          continue;
        }
        const blip = childElement(fill, DRAWING_NS, "blip");
        const relationshipId = blip?.getAttributeNS(
          OFFICE_RELATIONSHIP_NS,
          "embed",
        );
        const relationship = relationshipId
          ? records.records.get(relationshipId)
          : undefined;
        if (
          !relationship ||
          relationship.type !== IMAGE_RELATIONSHIP_TYPE ||
          !isInternalTargetMode(relationship.targetMode)
        ) {
          continue;
        }
        const mediaPath = resolveInternalPackageTarget(
          sourcePath,
          relationship.target,
        );
        if (!mediaPath || !/^ppt\/media\/[^/]+$/i.test(mediaPath)) continue;
        const bytes = await imageBytesForRelationship(
          files,
          mediaPath,
          relationship.target,
        );
        const size = bytes ? boundedRasterDimensions(bytes, mediaPath) : null;
        if (!bytes || !size || size.width < 1 || size.height < 1) continue;
        const dpi = rasterDpi(bytes, mediaPath);
        const scale = (name: string) => {
          const value = Number(tile.getAttribute(name) ?? "100000");
          return Number.isFinite(value) && value > 0 && value <= 10_000_000
            ? value / 100_000
            : 1;
        };
        const width = Math.round(
          (size.width / dpi.x) * EMU_PER_INCH * scale("sx"),
        );
        const height = Math.round(
          (size.height / dpi.y) * EMU_PER_INCH * scale("sy"),
        );
        if (width < 1 || height < 1) continue;
        tile.setAttribute(TILE_WIDTH_ATTRIBUTE, String(width));
        tile.setAttribute(TILE_HEIGHT_ATTRIBUTE, String(height));
        changed += 1;
      }
      if (!changed) continue;
      try {
        collection.parts.set(sourcePath, platform.serialize(document));
        fills += changed;
      } catch {
        partsSkipped += 1;
      }
    }
  }
  return { fills, partsSkipped };
}

function referencedDiagramDrawingPaths(
  context: RelationshipContext,
  files: PptxFiles,
  platform: XmlPlatform,
): { paths: Set<string>; sourceChars: number } | null {
  if (
    !context.sourceXml.includes("graphicFrame") ||
    !context.sourceXml.includes(DIAGRAM_NS) ||
    !context.sourceXml.includes("relIds")
  ) {
    return { paths: new Set(), sourceChars: 0 };
  }
  if (context.sourceXml.length > MAX_XML_DOCUMENT_CHARS) return null;
  const document = parseXml(
    context.sourceXml,
    platform,
    MAX_XML_DOCUMENT_CHARS,
  );
  if (!document) return null;

  const candidates = [...context.records.values()].flatMap((relationship) => {
    if (
      !isInternalTargetMode(relationship.targetMode) ||
      (!relationship.type.includes("diagramDrawing") &&
        !relationship.target.toLowerCase().includes("diagrams/drawing"))
    ) {
      return [];
    }
    const path = resolveInternalPackageTarget(
      context.sourcePath,
      relationship.target,
    );
    const number = path?.match(/^ppt\/diagrams\/drawing(\d+)\.xml$/)?.[1];
    if (!path || number === undefined || !files.diagramDrawings.has(path)) {
      return [];
    }
    return [{ path, number: Number.parseInt(number, 10) }];
  });

  const referenced = new Set<string>();
  for (const frame of elementsWithLocalName(document, "graphicFrame")) {
    if (frame.namespaceURI !== PRESENTATION_NS) continue;
    const graphic = childElement(frame, DRAWING_NS, "graphic");
    const graphicData = graphic
      ? childElement(graphic, DRAWING_NS, "graphicData")
      : null;
    if (!graphicData || graphicData.getAttribute("uri") !== DIAGRAM_NS) {
      continue;
    }
    const relationshipIds = childElement(graphicData, DIAGRAM_NS, "relIds");
    const dataId = relationshipIds?.getAttributeNS(
      OFFICE_RELATIONSHIP_NS,
      "dm",
    );
    const dataRelationship = dataId ? context.records.get(dataId) : undefined;
    const dataNumber = dataRelationship?.target.match(/data(\d+)/)?.[1];
    let frameCandidates = candidates;
    if (dataNumber !== undefined) {
      const desiredNumber = Number.parseInt(dataNumber, 10);
      frameCandidates = [...candidates].sort(
        (left, right) =>
          Math.abs(left.number - desiredNumber) -
          Math.abs(right.number - desiredNumber),
      );
    }
    const selected = frameCandidates[0]?.path;
    if (selected) referenced.add(selected);
  }
  return { paths: referenced, sourceChars: context.sourceXml.length };
}

function relativePackageTarget(sourcePath: string, targetPath: string): string {
  const sourceDirectory = sourcePath.split("/").slice(0, -1);
  const targetParts = targetPath.split("/");
  let common = 0;
  while (
    common < sourceDirectory.length &&
    common < targetParts.length &&
    sourceDirectory[common] === targetParts[common]
  ) {
    common += 1;
  }
  const relativeParts = [
    ...sourceDirectory.slice(common).map(() => ".."),
    ...targetParts.slice(common),
  ];
  return relativeParts.map(encodeURIComponent).join("/");
}

function appendImageRelationship(
  context: RelationshipContext,
  id: string,
  type: string,
  target: string,
): void {
  const qualifiedName = context.root.prefix
    ? `${context.root.prefix}:Relationship`
    : "Relationship";
  const relation = context.document.createElementNS(
    PACKAGE_RELATIONSHIP_NS,
    qualifiedName,
  );
  relation.setAttribute("Id", id);
  relation.setAttribute("Type", type);
  relation.setAttribute(
    "Target",
    relativePackageTarget(context.sourcePath, target),
  );
  context.root.appendChild(relation);
  context.changed = true;
}

function imageReferenceAttributes(document: Document): Attr[] {
  const references: Attr[] = [];
  for (const element of Array.from(document.getElementsByTagName("*"))) {
    if (element.nodeType !== 1) continue;
    for (const attribute of Array.from(element.attributes)) {
      if (
        attribute.namespaceURI === OFFICE_RELATIONSHIP_NS &&
        (attribute.localName === "embed" || attribute.localName === "link")
      ) {
        references.push(attribute);
      }
    }
  }
  return references;
}

async function normalizeDiagramImageRelationships(
  sourceBytes: ArrayBuffer,
  files: PptxFiles,
  platform: XmlPlatform,
  sourceArchive?: JSZip | null,
): Promise<{
  referencesRepaired: number;
  relationshipPartsUpdated: number;
  partsSkipped: number;
}> {
  const result = {
    referencesRepaired: 0,
    relationshipPartsUpdated: 0,
    partsSkipped: 0,
  };
  const collections = relationshipCollections(files);
  const contexts: RelationshipContext[] = [];
  let xmlBudget = 0;
  let relationshipScanComplete = true;

  for (const collection of collections) {
    for (const [relationshipPath, source] of collection.relationships) {
      const sourcePath = relationshipSourcePath(relationshipPath);
      if (!sourcePath || !collection.parts.has(sourcePath)) continue;
      if (
        source.length > MAX_RELATIONSHIP_XML_CHARS ||
        xmlBudget + source.length > MAX_COMPATIBILITY_XML_CHARS
      ) {
        result.partsSkipped += 1;
        relationshipScanComplete = false;
        continue;
      }
      xmlBudget += source.length;
      const document = parseXml(source, platform, MAX_RELATIONSHIP_XML_CHARS);
      const parsed = document ? relationshipRecords(document) : null;
      if (!document || !parsed) {
        result.partsSkipped += 1;
        relationshipScanComplete = false;
        continue;
      }
      contexts.push({
        sourcePath,
        sourceXml: collection.parts.get(sourcePath) ?? "",
        relationshipPath,
        relationshipMap: collection.relationships,
        document,
        root: parsed.root,
        records: parsed.records,
        drawingPaths: new Set(),
        changed: false,
      });
    }
  }

  if (!relationshipScanComplete) return result;

  const contextsByDrawing = new Map<string, RelationshipContext[]>();
  const usedIds = new Set<string>();
  for (const context of contexts) {
    for (const relationship of context.records.values()) {
      usedIds.add(relationship.id);
    }
    const selected = referencedDiagramDrawingPaths(context, files, platform);
    if (
      !selected ||
      xmlBudget + selected.sourceChars > MAX_COMPATIBILITY_XML_CHARS
    ) {
      result.partsSkipped += 1;
      relationshipScanComplete = false;
      continue;
    }
    xmlBudget += selected.sourceChars;
    for (const targetPath of selected.paths) {
      context.drawingPaths.add(targetPath);
      const linkedContexts = contextsByDrawing.get(targetPath) ?? [];
      linkedContexts.push(context);
      contextsByDrawing.set(targetPath, linkedContexts);
    }
  }

  if (!relationshipScanComplete) return result;

  const zip =
    sourceArchive ??
    (await JSZip.loadAsync(sourceBytes, { createFolders: false }));
  const changedRelationships = new Set<RelationshipContext>();
  const changedDrawings = new Map<string, string>();
  let nextAlias = 1;
  let diagramPartsSeen = 0;

  for (const [drawingPath, drawingXml] of files.diagramDrawings) {
    if (!/^ppt\/diagrams\/drawing\d+\.xml$/.test(drawingPath)) continue;
    const linkedContexts = contextsByDrawing.get(drawingPath);
    if (!linkedContexts?.length) continue;
    diagramPartsSeen += 1;
    if (diagramPartsSeen > MAX_DIAGRAM_PARTS) {
      result.partsSkipped += 1;
      break;
    }
    if (
      drawingXml.length > MAX_XML_DOCUMENT_CHARS ||
      xmlBudget + drawingXml.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      result.partsSkipped += 1;
      continue;
    }
    xmlBudget += drawingXml.length;
    const drawingDocument = parseXml(
      drawingXml,
      platform,
      MAX_XML_DOCUMENT_CHARS,
    );
    if (!drawingDocument) {
      result.partsSkipped += 1;
      continue;
    }
    const references = imageReferenceAttributes(drawingDocument);
    if (references.length === 0) continue;

    const relationshipPath = relationshipPathFor(drawingPath);
    if (!relationshipPath) {
      result.partsSkipped += 1;
      continue;
    }
    const relationshipXml = await readBoundedZipXml(
      zip,
      relationshipPath,
      MAX_RELATIONSHIP_XML_CHARS,
    );
    if (
      !relationshipXml ||
      xmlBudget + relationshipXml.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      result.partsSkipped += 1;
      continue;
    }
    xmlBudget += relationshipXml.length;
    const relationshipDocument = parseXml(
      relationshipXml,
      platform,
      MAX_RELATIONSHIP_XML_CHARS,
    );
    const parsedRelationships = relationshipDocument
      ? relationshipRecords(relationshipDocument)
      : null;
    if (!parsedRelationships) {
      result.partsSkipped += 1;
      continue;
    }

    const referencesById = new Map<string, Attr[]>();
    for (const reference of references) {
      const group = referencesById.get(reference.value) ?? [];
      group.push(reference);
      referencesById.set(reference.value, group);
    }
    const aliases = new Map<string, string>();
    let plannedReferences = 0;
    for (const [id, referenceGroup] of referencesById) {
      if (
        result.referencesRepaired + plannedReferences + referenceGroup.length >
        MAX_DIAGRAM_IMAGE_REFERENCES
      ) {
        result.partsSkipped += 1;
        continue;
      }
      const imageRelationship = parsedRelationships.records.get(id);
      if (
        !imageRelationship ||
        imageRelationship.type !== IMAGE_RELATIONSHIP_TYPE ||
        !isInternalTargetMode(imageRelationship.targetMode)
      ) {
        continue;
      }
      const mediaPath = resolveInternalPackageTarget(
        drawingPath,
        imageRelationship.target,
      );
      if (!mediaPath || !/^ppt\/media\/[^/]+$/.test(mediaPath)) continue;
      const mediaFile = isSafeZipPart(zip, mediaPath);
      if (!mediaFile) continue;

      let alias: string;
      do {
        alias = `rIdPresenterPreviewImage${nextAlias++}`;
      } while (usedIds.has(alias));
      usedIds.add(alias);
      aliases.set(id, alias);
      plannedReferences += referenceGroup.length;
      for (const reference of referenceGroup) reference.value = alias;
      for (const context of linkedContexts) {
        appendImageRelationship(
          context,
          alias,
          imageRelationship.type,
          mediaPath,
        );
        changedRelationships.add(context);
      }
    }

    if (aliases.size > 0) {
      changedDrawings.set(drawingPath, platform.serialize(drawingDocument));
      result.referencesRepaired += plannedReferences;
    }
  }

  const serializedRelationships = new Map<RelationshipContext, string>();
  let relationshipSerializationFailed = false;
  for (const context of changedRelationships) {
    if (!context.changed) continue;
    try {
      serializedRelationships.set(
        context,
        platform.serialize(context.document),
      );
    } catch {
      result.partsSkipped += 1;
      relationshipSerializationFailed = true;
    }
  }
  if (relationshipSerializationFailed) {
    result.referencesRepaired = 0;
    return result;
  }
  for (const [path, updated] of changedDrawings) {
    files.diagramDrawings.set(path, updated);
  }
  for (const [context, updated] of serializedRelationships) {
    context.relationshipMap.set(context.relationshipPath, updated);
  }
  result.relationshipPartsUpdated = serializedRelationships.size;
  return result;
}

function internalPreviewImageRelationshipIds(
  files: PptxFiles,
  platform: XmlPlatform,
): Set<string> {
  const ids = new Set<string>();
  let scannedChars = 0;
  for (const [relationshipPath, source] of files.slideRels) {
    const sourcePath = relationshipSourcePath(relationshipPath);
    if (
      !sourcePath ||
      !/^ppt\/slides\/slide\d+\.xml$/i.test(sourcePath) ||
      source.length > MAX_RELATIONSHIP_XML_CHARS ||
      scannedChars + source.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      continue;
    }
    scannedChars += source.length;
    const document = parseXml(source, platform, MAX_RELATIONSHIP_XML_CHARS);
    const parsed = document ? relationshipRecords(document) : null;
    if (!parsed) continue;
    for (const relationship of parsed.records.values()) {
      if (
        !relationship.id.startsWith("rIdPresenterPreviewImage") ||
        relationship.type !== IMAGE_RELATIONSHIP_TYPE ||
        !isInternalTargetMode(relationship.targetMode)
      ) {
        continue;
      }
      const mediaPath = resolveInternalPackageTarget(
        sourcePath,
        relationship.target,
      );
      if (mediaPath && /^ppt\/media\/[^/]+$/i.test(mediaPath)) {
        ids.add(relationship.id);
      }
    }
  }
  return ids;
}

function pictureFromSmartArtImageShape(
  shape: Element,
  document: Document,
  validImageRelationshipIds: ReadonlySet<string>,
): Element | null {
  if (
    shape.namespaceURI !== DIAGRAM_DRAWING_NS ||
    shape.localName !== "sp" ||
    childElement(shape, DIAGRAM_DRAWING_NS, "txBody")
  ) {
    return null;
  }
  const nonVisual = childElement(shape, DIAGRAM_DRAWING_NS, "nvSpPr");
  const nonVisualName = nonVisual
    ? childElement(nonVisual, DIAGRAM_DRAWING_NS, "cNvPr")
    : null;
  const shapeProperties = childElement(shape, DIAGRAM_DRAWING_NS, "spPr");
  if (!nonVisual || !nonVisualName || !shapeProperties) return null;

  const shapeChildren = childElements(shape);
  if (
    shapeChildren.some(
      (child) =>
        child.namespaceURI !== DIAGRAM_DRAWING_NS ||
        !["nvSpPr", "spPr", "style"].includes(child.localName),
    )
  ) {
    return null;
  }
  const properties = childElements(shapeProperties);
  if (
    properties.some(
      (child) =>
        child.namespaceURI !== DRAWING_NS ||
        !["xfrm", "prstGeom", "blipFill", "ln", "effectLst"].includes(
          child.localName,
        ),
    )
  ) {
    return null;
  }
  const fills = properties.filter(
    (child) =>
      child.namespaceURI === DRAWING_NS &&
      DRAWING_FILL_NAMES.has(child.localName),
  );
  const imageFill = fills[0];
  const image = imageFill ? childElement(imageFill, DRAWING_NS, "blip") : null;
  const imageRelationshipId = image?.getAttributeNS(
    OFFICE_RELATIONSHIP_NS,
    "embed",
  );
  const geometry = childElement(shapeProperties, DRAWING_NS, "prstGeom");
  const transform = childElement(shapeProperties, DRAWING_NS, "xfrm");
  if (
    fills.length !== 1 ||
    imageFill?.localName !== "blipFill" ||
    !imageRelationshipId ||
    !validImageRelationshipIds.has(imageRelationshipId) ||
    childElement(imageFill, DRAWING_NS, "tile") ||
    !childElement(imageFill, DRAWING_NS, "stretch") ||
    geometry?.getAttribute("prst") !== "rect" ||
    !transform ||
    !childElement(transform, DRAWING_NS, "off") ||
    !childElement(transform, DRAWING_NS, "ext")
  ) {
    return null;
  }

  const prefix = shape.prefix || "dsp";
  const createDiagramElement = (localName: string) =>
    document.createElementNS(DIAGRAM_DRAWING_NS, `${prefix}:${localName}`);
  const picture = createDiagramElement("pic");
  if (shape.hasAttribute("modelId")) {
    picture.setAttribute("modelId", shape.getAttribute("modelId") ?? "");
  }

  const nonVisualPicture = createDiagramElement("nvPicPr");
  nonVisualPicture.appendChild(nonVisualName.cloneNode(true));
  nonVisualPicture.appendChild(createDiagramElement("cNvPicPr"));
  const nonVisualProperties = childElement(
    nonVisual,
    DIAGRAM_DRAWING_NS,
    "nvPr",
  );
  if (nonVisualProperties) {
    nonVisualPicture.appendChild(nonVisualProperties.cloneNode(true));
  }

  const pictureFill = createDiagramElement("blipFill");
  for (const attribute of Array.from(imageFill.attributes)) {
    if (attribute.namespaceURI) {
      pictureFill.setAttributeNS(
        attribute.namespaceURI,
        attribute.name,
        attribute.value,
      );
    } else {
      pictureFill.setAttribute(attribute.name, attribute.value);
    }
  }
  for (const child of childElements(imageFill)) {
    pictureFill.appendChild(child.cloneNode(true));
  }

  const pictureProperties = shapeProperties.cloneNode(true) as Element;
  const clonedImageFill = childElement(
    pictureProperties,
    DRAWING_NS,
    "blipFill",
  );
  if (!clonedImageFill) return null;
  pictureProperties.removeChild(clonedImageFill);

  picture.appendChild(nonVisualPicture);
  picture.appendChild(pictureFill);
  picture.appendChild(pictureProperties);
  return picture;
}

function promoteSmartArtImageFillShapes(
  files: PptxFiles,
  platform: XmlPlatform,
): { shapesPromoted: number; partsSkipped: number } {
  const result = { shapesPromoted: 0, partsSkipped: 0 };
  const validImageRelationshipIds = internalPreviewImageRelationshipIds(
    files,
    platform,
  );
  if (validImageRelationshipIds.size === 0) return result;

  let scannedChars = 0;
  let partsScanned = 0;
  const changedDrawings = new Map<string, string>();
  for (const [path, source] of files.diagramDrawings) {
    if (!/^ppt\/diagrams\/drawing\d+\.xml$/i.test(path)) continue;
    partsScanned += 1;
    if (
      partsScanned > MAX_DIAGRAM_PARTS ||
      source.length > MAX_XML_DOCUMENT_CHARS ||
      scannedChars + source.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      result.partsSkipped += 1;
      continue;
    }
    scannedChars += source.length;
    if (!source.includes("blipFill")) continue;
    const document = parseXml(source, platform, MAX_XML_DOCUMENT_CHARS);
    const root = document?.documentElement;
    if (
      !document ||
      !root ||
      root.namespaceURI !== DIAGRAM_DRAWING_NS ||
      root.localName !== "drawing"
    ) {
      result.partsSkipped += 1;
      continue;
    }

    let changed = false;
    let promotedOnPart = 0;
    for (const shape of elementsWithLocalName(document, "sp")) {
      const picture = pictureFromSmartArtImageShape(
        shape,
        document,
        validImageRelationshipIds,
      );
      if (!picture || !shape.parentNode) continue;
      if (
        result.shapesPromoted + promotedOnPart >=
        MAX_DIAGRAM_IMAGE_REFERENCES
      ) {
        result.partsSkipped += 1;
        break;
      }
      shape.parentNode.insertBefore(picture, shape);
      shape.parentNode.removeChild(shape);
      promotedOnPart += 1;
      changed = true;
    }
    if (!changed) continue;
    try {
      changedDrawings.set(path, platform.serialize(document));
      result.shapesPromoted += promotedOnPart;
    } catch {
      result.partsSkipped += 1;
    }
  }
  for (const [path, drawing] of changedDrawings) {
    files.diagramDrawings.set(path, drawing);
  }
  return result;
}

interface PictureGeometryPromotionResult {
  picturesPromoted: number;
  picturesSkipped: number;
  partsSkipped: number;
}

function drawingImageFillFromPictureFill(
  document: Document,
  pictureFill: Element,
  drawingPrefix: string,
): Element | null {
  const children = childElements(pictureFill);
  const blips = children.filter(
    (child) => child.namespaceURI === DRAWING_NS && child.localName === "blip",
  );
  const modes = children.filter(
    (child) =>
      child.namespaceURI === DRAWING_NS &&
      (child.localName === "stretch" || child.localName === "tile"),
  );
  const allowedChildren = new Set(["blip", "srcRect", "stretch"]);
  if (
    blips.length !== 1 ||
    modes.length !== 1 ||
    modes[0]?.localName !== "stretch" ||
    children.some(
      (child) =>
        child.namespaceURI !== DRAWING_NS ||
        !allowedChildren.has(child.localName),
    )
  ) {
    return null;
  }

  const fill = document.createElementNS(
    DRAWING_NS,
    `${drawingPrefix || "a"}:blipFill`,
  );
  for (let index = 0; index < pictureFill.attributes.length; index += 1) {
    const attribute = pictureFill.attributes.item(index);
    if (!attribute || attribute.namespaceURI === XMLNS_NS) continue;
    fill.setAttributeNS(
      attribute.namespaceURI,
      attribute.name,
      attribute.value,
    );
  }
  for (const child of Array.from(pictureFill.childNodes)) {
    fill.appendChild(child.cloneNode(true));
  }
  return fill;
}

async function promoteNonRectangularPicturesToShapeFills(
  files: PptxFiles,
  platform: XmlPlatform,
): Promise<PictureGeometryPromotionResult> {
  const result: PictureGeometryPromotionResult = {
    picturesPromoted: 0,
    picturesSkipped: 0,
    partsSkipped: 0,
  };
  let scannedChars = 0;
  let validatedMediaBytes = 0;
  const validatedMediaSizes = new Map<string, number>();

  for (const [slidePath, source] of files.slides) {
    if (!/^ppt\/slides\/slide\d+\.xml$/i.test(slidePath)) continue;
    if (
      !/<(?:[A-Za-z_][\w.-]*:)?pic(?:\s|>)/.test(source) ||
      !/(?:prstGeom|custGeom)/.test(source)
    ) {
      continue;
    }
    if (
      source.length > MAX_XML_DOCUMENT_CHARS ||
      scannedChars + source.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      result.partsSkipped += 1;
      continue;
    }
    scannedChars += source.length;

    const document = parseXml(source, platform, MAX_XML_DOCUMENT_CHARS);
    const root = document?.documentElement;
    if (
      !document ||
      !root ||
      root.namespaceURI !== PRESENTATION_NS ||
      root.localName !== "sld"
    ) {
      result.partsSkipped += 1;
      continue;
    }

    const shapeTree = elementsWithLocalName(document, "spTree").find(
      (element) => element.namespaceURI === PRESENTATION_NS,
    );
    if (!shapeTree) {
      result.partsSkipped += 1;
      continue;
    }

    const pictures = elementsWithLocalName(document, "pic").filter(
      (element) =>
        element.namespaceURI === PRESENTATION_NS &&
        isWithinElement(element, shapeTree),
    );
    if (pictures.length > MAX_GROUP_FILL_DRAWABLES_PER_SLIDE) {
      result.partsSkipped += 1;
      continue;
    }

    const candidates = pictures.filter((picture) => {
      const shapeProperties = childElement(picture, PRESENTATION_NS, "spPr");
      return Boolean(
        shapeProperties &&
        childElements(shapeProperties).some(
          (child) =>
            child.namespaceURI === DRAWING_NS &&
            (child.localName === "prstGeom" || child.localName === "custGeom"),
        ),
      );
    });
    const nonRectangularCandidates = candidates.filter((picture) => {
      const shapeProperties = childElement(picture, PRESENTATION_NS, "spPr");
      const geometries = shapeProperties
        ? childElements(shapeProperties).filter(
            (child) =>
              child.namespaceURI === DRAWING_NS &&
              (child.localName === "prstGeom" ||
                child.localName === "custGeom"),
          )
        : [];
      if (geometries.length !== 1) return true;
      const geometry = geometries[0];
      return (
        !geometry ||
        geometry.localName !== "prstGeom" ||
        (geometry.getAttribute("prst") ?? "").toLowerCase() !== "rect"
      );
    });
    if (nonRectangularCandidates.length === 0) continue;

    if (
      result.picturesPromoted + nonRectangularCandidates.length >
      MAX_PICTURE_GEOMETRY_IMAGES
    ) {
      result.picturesSkipped += nonRectangularCandidates.length;
      result.partsSkipped += 1;
      break;
    }

    const relationshipPath = relationshipPathFor(slidePath);
    const relationshipXml = relationshipPath
      ? files.slideRels.get(relationshipPath)
      : undefined;
    if (
      !relationshipPath ||
      !relationshipXml ||
      relationshipXml.length > MAX_RELATIONSHIP_XML_CHARS ||
      scannedChars + relationshipXml.length > MAX_COMPATIBILITY_XML_CHARS
    ) {
      result.picturesSkipped += nonRectangularCandidates.length;
      result.partsSkipped += 1;
      continue;
    }
    scannedChars += relationshipXml.length;
    const relationshipDocument = parseXml(
      relationshipXml,
      platform,
      MAX_RELATIONSHIP_XML_CHARS,
    );
    const parsedRelationships = relationshipDocument
      ? relationshipRecords(relationshipDocument)
      : null;
    if (!parsedRelationships) {
      result.picturesSkipped += nonRectangularCandidates.length;
      result.partsSkipped += 1;
      continue;
    }

    let promotedOnSlide = 0;
    let skippedOnSlide = 0;
    for (const picture of nonRectangularCandidates) {
      const directChildren = childElements(picture);
      const nonVisual = childElement(picture, PRESENTATION_NS, "nvPicPr");
      const pictureFill = childElement(picture, PRESENTATION_NS, "blipFill");
      const shapeProperties = childElement(picture, PRESENTATION_NS, "spPr");
      const geometries = shapeProperties
        ? childElements(shapeProperties).filter(
            (child) =>
              child.namespaceURI === DRAWING_NS &&
              (child.localName === "prstGeom" ||
                child.localName === "custGeom"),
          )
        : [];
      const geometry = geometries[0] ?? null;
      const presetGeometry = geometry?.getAttribute("prst");
      const geometryChildren = geometry ? childElements(geometry) : [];
      const simpleEllipseGeometry = Boolean(
        geometry?.localName === "prstGeom" &&
        presetGeometry?.toLowerCase() === "ellipse" &&
        geometryChildren.length === 1 &&
        geometryChildren[0]?.namespaceURI === DRAWING_NS &&
        geometryChildren[0]?.localName === "avLst" &&
        childElements(geometryChildren[0]).length === 0,
      );
      const parent = picture.parentNode;
      const nonVisualChildren = nonVisual ? childElements(nonVisual) : [];
      const nonVisualName = nonVisualChildren.find(
        (child) =>
          child.namespaceURI === PRESENTATION_NS && child.localName === "cNvPr",
      );
      const nonVisualProperties = nonVisualChildren.find(
        (child) =>
          child.namespaceURI === PRESENTATION_NS && child.localName === "nvPr",
      );
      const blip = pictureFill
        ? childElement(pictureFill, DRAWING_NS, "blip")
        : null;
      const embeddedRelationshipId = blip?.getAttributeNS(
        OFFICE_RELATIONSHIP_NS,
        "embed",
      );
      const relationship = embeddedRelationshipId
        ? parsedRelationships.records.get(embeddedRelationshipId)
        : undefined;
      const targetPath = relationship
        ? resolveInternalPackageTarget(slidePath, relationship.target)
        : null;
      const drawingFill =
        pictureFill && geometry
          ? drawingImageFillFromPictureFill(
              document,
              pictureFill,
              geometry.prefix ?? "a",
            )
          : null;
      const unsupportedShapeFill = Boolean(
        shapeProperties &&
        childElements(shapeProperties).some(
          (child) =>
            child.namespaceURI === DRAWING_NS &&
            DRAWING_FILL_NAMES.has(child.localName),
        ),
      );

      if (
        !nonVisual ||
        !nonVisualName ||
        !nonVisualProperties ||
        !pictureFill ||
        !shapeProperties ||
        geometries.length !== 1 ||
        !simpleEllipseGeometry ||
        !presetGeometry ||
        !/^[A-Za-z0-9]{1,64}$/.test(presetGeometry) ||
        !embeddedRelationshipId ||
        blip?.hasAttributeNS(OFFICE_RELATIONSHIP_NS, "link") ||
        !relationship ||
        relationship.type !== IMAGE_RELATIONSHIP_TYPE ||
        !isInternalTargetMode(relationship.targetMode) ||
        !targetPath ||
        !/^ppt\/media\/[^/]{1,255}$/i.test(targetPath) ||
        !drawingFill ||
        unsupportedShapeFill ||
        !parent ||
        directChildren.length !== 3 ||
        !directChildren.includes(nonVisual) ||
        !directChildren.includes(pictureFill) ||
        !directChildren.includes(shapeProperties)
      ) {
        skippedOnSlide += 1;
        continue;
      }

      let mediaSize = validatedMediaSizes.get(targetPath);
      if (mediaSize === undefined) {
        const indexedMedia = files.media.get(targetPath);
        if (indexedMedia) {
          mediaSize = indexedMedia.byteLength;
        } else if (files.mediaResolver) {
          try {
            const resolvedMedia = await files.mediaResolver.resolve(
              relationship.target,
            );
            if (resolvedMedia?.mediaPath === targetPath) {
              mediaSize = resolvedMedia.data.byteLength;
            }
          } catch {
            // Skip this picture if lazy media validation fails.
          }
        }
        if (
          mediaSize === undefined ||
          mediaSize <= 0 ||
          mediaSize > MAX_PICTURE_GEOMETRY_SINGLE_MEDIA_BYTES ||
          validatedMediaBytes + mediaSize >
            MAX_PICTURE_GEOMETRY_TOTAL_MEDIA_BYTES
        ) {
          skippedOnSlide += 1;
          continue;
        }
        validatedMediaSizes.set(targetPath, mediaSize);
        validatedMediaBytes += mediaSize;
      }

      const prefix = picture.prefix ?? "p";
      const newShape = document.createElementNS(
        PRESENTATION_NS,
        `${prefix}:sp`,
      );
      const newNonVisual = document.createElementNS(
        PRESENTATION_NS,
        `${prefix}:nvSpPr`,
      );
      newNonVisual.appendChild(nonVisualName.cloneNode(true));
      newNonVisual.appendChild(
        document.createElementNS(PRESENTATION_NS, `${prefix}:cNvSpPr`),
      );
      newNonVisual.appendChild(nonVisualProperties.cloneNode(true));
      const newShapeProperties = shapeProperties.cloneNode(true) as Element;
      const shapeGeometry = childElements(newShapeProperties).find(
        (child) =>
          child.namespaceURI === DRAWING_NS && child.localName === "prstGeom",
      );
      if (!shapeGeometry) {
        skippedOnSlide += 1;
        continue;
      }
      newShapeProperties.insertBefore(drawingFill, shapeGeometry.nextSibling);
      newShape.appendChild(newNonVisual);
      newShape.appendChild(newShapeProperties);
      const textBody = document.createElementNS(
        PRESENTATION_NS,
        `${prefix}:txBody`,
      );
      const drawingPrefix = geometry?.prefix ?? "a";
      textBody.appendChild(
        document.createElementNS(DRAWING_NS, `${drawingPrefix}:bodyPr`),
      );
      textBody.appendChild(
        document.createElementNS(DRAWING_NS, `${drawingPrefix}:lstStyle`),
      );
      textBody.appendChild(
        document.createElementNS(DRAWING_NS, `${drawingPrefix}:p`),
      );
      newShape.appendChild(textBody);
      parent.replaceChild(newShape, picture);
      promotedOnSlide += 1;
    }

    result.picturesSkipped += skippedOnSlide;
    if (promotedOnSlide === 0) continue;
    try {
      files.slides.set(slidePath, platform.serialize(document));
      result.picturesPromoted += promotedOnSlide;
    } catch {
      result.picturesSkipped += promotedOnSlide;
      result.partsSkipped += 1;
    }
  }

  return result;
}

const DEFAULT_TEXT_LEVELS = new Set([
  "defPPr",
  ...Array.from({ length: 9 }, (_, index) => `lvl${index + 1}pPr`),
]);

/**
 * PowerPoint's single spacing is 100% of its line height. Without any lnSpc the
 * renderer leaves CSS `normal`, measured about 6% tighter than PowerPoint, while
 * explicit percentages use the PowerPoint-calibrated multiplier. Fill 100% only
 * into the lowest-priority defaults (presentation default text style and master
 * text styles) that declare no spacing, so every explicit or inherited value
 * still wins. Preview-only; source bytes are untouched.
 */
function fillDefaultLineSpacing(
  files: PptxFiles,
  platform: XmlPlatform,
): { levelsFilled: number; partsSkipped: number } {
  let levelsFilled = 0;
  let partsSkipped = 0;
  const fill = (container: Element): number => {
    let filled = 0;
    for (const level of childElements(container)) {
      if (
        level.namespaceURI !== DRAWING_NS ||
        !DEFAULT_TEXT_LEVELS.has(level.localName) ||
        childElement(level, DRAWING_NS, "lnSpc")
      ) {
        continue;
      }
      const document = level.ownerDocument;
      const spacing = document.createElementNS(DRAWING_NS, "a:lnSpc");
      const percent = document.createElementNS(DRAWING_NS, "a:spcPct");
      percent.setAttribute("val", "100000");
      spacing.appendChild(percent);
      level.insertBefore(spacing, level.firstChild);
      filled += 1;
    }
    return filled;
  };
  const presentation = parseXml(
    files.presentation,
    platform,
    MAX_XML_DOCUMENT_CHARS,
  );
  const defaults = presentation?.documentElement
    ? childElement(
        presentation.documentElement,
        PRESENTATION_NS,
        "defaultTextStyle",
      )
    : null;
  if (presentation && defaults) {
    const filled = fill(defaults);
    if (filled) {
      try {
        files.presentation = platform.serialize(presentation);
        levelsFilled += filled;
      } catch {
        partsSkipped += 1;
      }
    }
  } else if (!presentation) {
    partsSkipped += 1;
  }
  for (const [path, source] of files.slideMasters) {
    const document = parseXml(source, platform, MAX_XML_DOCUMENT_CHARS);
    const root = document?.documentElement;
    if (!document || !root) {
      partsSkipped += 1;
      continue;
    }
    const styles = childElement(root, PRESENTATION_NS, "txStyles");
    if (!styles) continue;
    let filled = 0;
    for (const style of childElements(styles)) {
      if (style.namespaceURI === PRESENTATION_NS) filled += fill(style);
    }
    if (!filled) continue;
    try {
      files.slideMasters.set(path, platform.serialize(document));
      levelsFilled += filled;
    } catch {
      partsSkipped += 1;
    }
  }
  return { levelsFilled, partsSkipped };
}

export async function applyPreviewRendererCompatibility(
  sourceBytes: ArrayBuffer,
  files: PptxFiles,
  options: PreviewRendererCompatibilityOptions = {},
): Promise<PreviewRendererCompatibilityReport> {
  const report: PreviewRendererCompatibilityReport = {
    hiddenDrawingObjectsSuppressed: 0,
    backgroundFillShapesNormalized: 0,
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
  };
  const platform = browserXmlPlatform();
  if (!platform) return report;

  if (options.fillDefaultLineSpacing === true) {
    try {
      const spacing = fillDefaultLineSpacing(files, platform);
      report.defaultLineSpacingLevelsFilled = spacing.levelsFilled;
      report.compatibilityPartsSkipped += spacing.partsSkipped;
    } catch {
      report.compatibilityPartsSkipped += 1;
    }
  }

  if (options.suppressHiddenDrawingObjects !== false) {
    const hiddenObjects = suppressHiddenDrawingObjects(files, platform);
    report.hiddenDrawingObjectsSuppressed = hiddenObjects.objectsSuppressed;
    report.compatibilityPartsSkipped += hiddenObjects.partsSkipped;
  }

  let sourceArchive: JSZip | null = null;
  if (
    options.normalizeThemeOverrideColors === true ||
    options.normalizeThemeBackgroundImageFills === true
  ) {
    try {
      sourceArchive = await JSZip.loadAsync(sourceBytes, {
        createFolders: false,
      });
    } catch {
      // A failed preview-only compatibility pass must not make the deck unavailable.
      report.compatibilityPartsSkipped += 1;
    }
  }
  if (options.normalizeThemeOverrideColors === true && sourceArchive) {
    try {
      const themeOverrides = await normalizeSlideThemeOverrideColors(
        files,
        platform,
        sourceArchive,
      );
      report.themeOverrideColorsNormalized =
        themeOverrides.referencesNormalized;
      report.compatibilityPartsSkipped += themeOverrides.partsSkipped;
    } catch {
      // A failed preview-only compatibility pass must not make the deck unavailable.
      report.compatibilityPartsSkipped += 1;
    }
  }

  if (options.normalizeThemeBackgroundImageFills === true && sourceArchive) {
    try {
      const themeBackgrounds = await normalizeThemeBackgroundImageFills(
        files,
        sourceArchive,
        platform,
        options.normalizeThemeBackgroundImageEffects === true,
      );
      report.themeBackgroundImageFillsResolved = themeBackgrounds.fillsResolved;
      report.compatibilityPartsSkipped += themeBackgrounds.partsSkipped;
    } catch {
      // Keep the existing parsed background if the preview-only repair fails.
      report.compatibilityPartsSkipped += 1;
    }
  }

  if (options.normalizeGroupFills === true) {
    const groupFills = normalizeGroupFills(files, platform);
    report.groupFillReferencesInherited = groupFills.referencesInherited;
    report.compatibilityPartsSkipped += groupFills.partsSkipped;
  }

  // Keep the bounded full-canvas fill compatibility lane opt-in for A/B
  // diagnostics; production preview enables it after corpus review.
  if (options.normalizeBackgroundFills === true) {
    const background = normalizeSlideBackgroundFill(files, platform);
    report.backgroundFillShapesNormalized = background.shapesNormalized;
    report.backgroundStyleFillReferencesRemoved =
      background.styleFillReferencesRemoved;
  }
  if (options.inheritLayoutPlaceholderFills === true) {
    report.layoutPlaceholderFillsInherited = inheritLayoutPlaceholderSolidFills(
      files,
      platform,
    );
  }
  if (options.followTextColoredHyperlinks === true) {
    try {
      report.textColoredHyperlinks = followTextColoredHyperlinks(
        files,
        platform,
      );
    } catch {
      report.compatibilityPartsSkipped += 1;
    }
  }
  if (options.suppressBrowserOnlyLineBreaks === true) {
    try {
      report.browserLineBreaksSuppressed = suppressBrowserOnlyLineBreaks(
        files,
        platform,
      );
    } catch {
      report.compatibilityPartsSkipped += 1;
    }
  }
  // Before duotone baking, which re-encodes images without their DPI.
  if (options.sizeTiledImageFills === true) {
    try {
      const tiles = await sizeTiledImageFills(files, platform);
      report.tiledImageFillsSized = tiles.fills;
      report.compatibilityPartsSkipped += tiles.partsSkipped;
    } catch {
      report.compatibilityPartsSkipped += 1;
    }
  }
  if (options.normalizeDuotoneImages === true) {
    try {
      const duotone = await normalizeDuotoneImages(files, platform);
      report.duotoneImageReferencesNormalized = duotone.references;
      report.compatibilityPartsSkipped += duotone.partsSkipped;
    } catch {
      // A failed image transform must not make an otherwise readable deck unavailable.
      report.compatibilityPartsSkipped += 1;
    }
  }
  if (options.normalizePictureFillGeometry === true) {
    try {
      report.pictureGeometryInherited = inheritLayoutPictureGeometry(
        files,
        platform,
      );
    } catch {
      report.compatibilityPartsSkipped += 1;
    }
    try {
      const pictureGeometry = await promoteNonRectangularPicturesToShapeFills(
        files,
        platform,
      );
      report.pictureGeometryImagesPromoted = pictureGeometry.picturesPromoted;
      report.pictureGeometryImagesSkipped = pictureGeometry.picturesSkipped;
      report.compatibilityPartsSkipped += pictureGeometry.partsSkipped;
    } catch {
      // Keep the original parsed slides if a preview-only geometry repair fails.
      report.compatibilityPartsSkipped += 1;
    }
  }
  if (options.repairSmartArtRelationships === false) return report;
  try {
    const diagrams = await normalizeDiagramImageRelationships(
      sourceBytes,
      files,
      platform,
      sourceArchive,
    );
    report.smartArtImageReferencesRepaired = diagrams.referencesRepaired;
    report.smartArtRelationshipPartsUpdated = diagrams.relationshipPartsUpdated;
    report.compatibilityPartsSkipped += diagrams.partsSkipped;
  } catch {
    // Preview compatibility must never make an otherwise readable deck unavailable.
    report.compatibilityPartsSkipped += 1;
  }
  try {
    const promoted = promoteSmartArtImageFillShapes(files, platform);
    report.smartArtImageShapesPromoted = promoted.shapesPromoted;
    report.compatibilityPartsSkipped += promoted.partsSkipped;
  } catch {
    report.compatibilityPartsSkipped += 1;
  }
  return report;
}

export const previewRendererCompatibilityInternals = {
  resolveInternalPackageTarget,
  relativePackageTarget,
};
