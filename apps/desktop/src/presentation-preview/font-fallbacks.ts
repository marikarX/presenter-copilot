import type {
  FontFaceConfig,
  PresentationData,
  PptxFiles,
} from "@aiden0z/pptx-renderer";

const MAX_FONT_FAMILIES = 64;
const MAX_XML_SCAN_CHARS = 12 * 1024 * 1024;
const MAX_FONT_NAME_CHARS = 128;
const MAX_FONT_PROBES_AT_ONCE = 8;

const TYPEFACE_ATTRIBUTE = /\btypeface\s*=\s*(["'])(.*?)\1/gs;
const LATIN_TYPEFACE_ATTRIBUTE =
  /<(?:[A-Za-z_][\w.-]*:)?latin\b[^>]*\btypeface\s*=\s*(["'])(.*?)\1/gs;
const SAFE_FONT_FAMILY = /^[\p{L}\p{N}][\p{L}\p{N}\p{M} ._()'’,-]{0,127}$/u;
const GENERIC_FONT_FAMILIES = new Set([
  "cursive",
  "fantasy",
  "inherit",
  "initial",
  "math",
  "monospace",
  "sans-serif",
  "serif",
  "system-ui",
  "unset",
]);

type FallbackKind = "sans" | "serif" | "monospace";

interface FallbackFace {
  localName: string;
  descriptors: NonNullable<FontFaceConfig["descriptors"]>;
}

export interface PreviewFontResolution {
  fontFaces: FontFaceConfig[];
  substitutions: string[];
  unresolvedFamilies: string[];
  limited: boolean;
}

export type LocalFontProbe = (family: string) => Promise<boolean>;

interface FontScanResult {
  families: string[];
  limited: boolean;
}

const FALLBACK_FAMILIES: Record<FallbackKind, readonly string[]> = {
  sans: ["Arial", "Calibri", "Liberation Sans", "Noto Sans"],
  serif: [
    "Times New Roman",
    "Georgia",
    "Cambria",
    "Liberation Serif",
    "Noto Serif",
  ],
  monospace: ["Courier New", "Consolas", "Liberation Mono", "Noto Sans Mono"],
};

/**
 * Width-matched fallbacks for Office cloud fonts that browsers cannot load
 * with local(): the local face is scaled with CSS size-adjust so advance widths
 * (and therefore wrapping) match. Ratios were measured from the cached Office
 * font files against the installed fallback at the same size.
 */
interface MetricFallback {
  family: string;
  regular: string;
  bold: string;
}
const METRIC_FALLBACKS: ReadonlyMap<string, readonly MetricFallback[]> =
  new Map([
    ["aptos", [{ family: "Segoe UI", regular: "97.2%", bold: "95.5%" }]],
    [
      "aptos display",
      [{ family: "Segoe UI", regular: "97.2%", bold: "95.5%" }],
    ],
    ["aptos narrow", [{ family: "Calibri", regular: "97%", bold: "97%" }]],
    ["aptos serif", [{ family: "Georgia", regular: "101.8%", bold: "101.8%" }]],
  ]);

const FALLBACK_STYLES = [
  { suffix: "", descriptors: { weight: "400", style: "normal" } },
  { suffix: " Bold", descriptors: { weight: "700", style: "normal" } },
  { suffix: " Italic", descriptors: { weight: "400", style: "italic" } },
  { suffix: " Bold Italic", descriptors: { weight: "700", style: "italic" } },
] as const;

function decodeXmlAttribute(value: string): string {
  return value
    .replace(/&(?:amp|quot|apos|lt|gt);/g, (entity) => {
      switch (entity) {
        case "&amp;":
          return "&";
        case "&quot;":
          return '"';
        case "&apos;":
          return "'";
        case "&lt;":
          return "<";
        case "&gt;":
          return ">";
        default:
          return entity;
      }
    })
    .replace(/&#(x[\da-f]+|\d+);/gi, (entity, code: string) => {
      const number =
        code[0]?.toLowerCase() === "x"
          ? Number.parseInt(code.slice(1), 16)
          : Number.parseInt(code, 10);
      if (!Number.isSafeInteger(number) || number < 1 || number > 0x10ffff) {
        return "";
      }
      try {
        return String.fromCodePoint(number);
      } catch {
        return "";
      }
    });
}

function usableFamily(rawValue: string): string | null {
  const family = decodeXmlAttribute(rawValue).trim();
  if (
    family.length < 1 ||
    family.length > MAX_FONT_NAME_CHARS ||
    family.startsWith("+") ||
    GENERIC_FONT_FAMILIES.has(family.toLowerCase()) ||
    !SAFE_FONT_FAMILY.test(family)
  ) {
    return null;
  }
  return family;
}

function* xmlParts(
  files: PptxFiles,
): Generator<{ xml: string; latinThemeOnly?: boolean }> {
  yield { xml: files.presentation };
  for (const collection of [
    files.slides,
    files.slideLayouts,
    files.slideMasters,
    files.charts,
    files.chartStyles,
    files.chartColors,
    files.diagramDrawings,
  ]) {
    for (const xml of collection.values()) yield { xml };
  }
  if (files.tableStyles) yield { xml: files.tableStyles };
  for (const collection of [files.themes, files.themeOverrides]) {
    if (!collection) continue;
    for (const xml of collection.values()) {
      yield { xml, latinThemeOnly: true };
    }
  }
}

function collectReferencedFamilies(files: PptxFiles): FontScanResult {
  const families = new Map<string, string>();
  let scannedChars = 0;
  let limited = false;

  for (const part of xmlParts(files)) {
    if (families.size >= MAX_FONT_FAMILIES) {
      limited = true;
      break;
    }
    const remainingChars = MAX_XML_SCAN_CHARS - scannedChars;
    if (remainingChars <= 0) {
      limited = true;
      break;
    }
    const boundedXml = part.xml.slice(0, remainingChars);
    if (boundedXml.length < part.xml.length) limited = true;
    scannedChars += boundedXml.length;
    const attributePattern = part.latinThemeOnly
      ? LATIN_TYPEFACE_ATTRIBUTE
      : TYPEFACE_ATTRIBUTE;
    attributePattern.lastIndex = 0;
    for (const match of boundedXml.matchAll(attributePattern)) {
      const family = usableFamily(match[2] ?? "");
      if (!family) continue;
      const key = family.toLowerCase();
      if (families.has(key)) continue;
      if (families.size >= MAX_FONT_FAMILIES) {
        limited = true;
        break;
      }
      families.set(key, family);
    }
    if (limited) break;
  }

  return { families: [...families.values()], limited };
}

function embeddedFontKeys(presentation: PresentationData): Set<string> {
  const families = presentation.embeddedFontFamilies;
  if (!families) return new Set();
  return new Set(
    [...families.keys(), ...families.values()].map((family) =>
      family.toLowerCase(),
    ),
  );
}

function fallbackKind(family: string): FallbackKind {
  if (/mono|courier|consolas|cascadia|terminal|\bcode\b/i.test(family)) {
    return "monospace";
  }
  if (
    /serif|times|garamond|baskerville|palatino|didot|bodoni|cambria|constantia|georgia|rockwell|book\s/i.test(
      family,
    )
  ) {
    return "serif";
  }
  return "sans";
}

function escapeCssString(value: string): string {
  return value.replace(/[\\"\n\r\f]/g, (character) => `\\${character}`);
}

async function runBounded<T>(
  values: readonly T[],
  concurrency: number,
  task: (value: T) => Promise<void>,
): Promise<void> {
  let nextIndex = 0;
  const workerCount = Math.min(concurrency, values.length);
  await Promise.all(
    Array.from({ length: workerCount }, async () => {
      while (nextIndex < values.length) {
        const current = values[nextIndex];
        nextIndex += 1;
        if (current !== undefined) await task(current);
      }
    }),
  );
}

export async function resolvePreviewFonts(
  files: PptxFiles,
  presentation: PresentationData,
  probeLocalFont: LocalFontProbe,
  signal?: AbortSignal,
): Promise<PreviewFontResolution> {
  if (signal?.aborted) throw new Error("Presentation preview was closed.");
  const scan = collectReferencedFamilies(files);
  const embedded = embeddedFontKeys(presentation);
  const familiesToCheck = scan.families.filter(
    (family) => !embedded.has(family.toLowerCase()),
  );
  const availability = new Map<string, boolean>();
  const probeCache = new Map<string, Promise<boolean>>();
  const checkLocalFont = (family: string): Promise<boolean> => {
    if (signal?.aborted) {
      return Promise.reject(new Error("Presentation preview was closed."));
    }
    const key = family.toLowerCase();
    let result = probeCache.get(key);
    if (!result) {
      result = probeLocalFont(family).catch(() => false);
      probeCache.set(key, result);
    }
    return result;
  };

  await runBounded(familiesToCheck, MAX_FONT_PROBES_AT_ONCE, async (family) => {
    availability.set(family.toLowerCase(), await checkLocalFont(family));
  });
  if (signal?.aborted) throw new Error("Presentation preview was closed.");

  const configuredFallbacks = new Map<FallbackKind, Promise<FallbackFace[]>>();
  const getFallbackFaces = (kind: FallbackKind): Promise<FallbackFace[]> => {
    let result = configuredFallbacks.get(kind);
    if (!result) {
      result = (async () => {
        for (const candidate of FALLBACK_FAMILIES[kind]) {
          if (!(await checkLocalFont(candidate))) continue;
          const faces: FallbackFace[] = [];
          for (const style of FALLBACK_STYLES) {
            const localName = `${candidate}${style.suffix}`;
            if (!(await checkLocalFont(localName))) continue;
            faces.push({ localName, descriptors: style.descriptors });
          }
          return faces;
        }
        return [];
      })();
      configuredFallbacks.set(kind, result);
    }
    return result;
  };

  const metricFallbackFaces = async (
    family: string,
  ): Promise<{ faces: FontFaceConfig[]; localFamily: string } | null> => {
    for (const candidate of METRIC_FALLBACKS.get(family.toLowerCase()) ?? []) {
      if (!(await checkLocalFont(candidate.family))) continue;
      const faces: FontFaceConfig[] = [];
      for (const style of FALLBACK_STYLES) {
        const localName = `${candidate.family}${style.suffix}`;
        if (!(await checkLocalFont(localName))) continue;
        // size-adjust is a supported FontFace descriptor missing from lib.dom.
        const descriptors: FontFaceDescriptors & { sizeAdjust: string } = {
          ...style.descriptors,
          sizeAdjust:
            style.descriptors.weight === "700"
              ? candidate.bold
              : candidate.regular,
        };
        faces.push({
          family,
          source: `local("${escapeCssString(localName)}")`,
          descriptors,
        });
      }
      if (faces.length) return { faces, localFamily: candidate.family };
    }
    return null;
  };

  const fontFaces: FontFaceConfig[] = [];
  const substitutions: string[] = [];
  const unresolvedFamilies: string[] = [];
  for (const family of familiesToCheck) {
    if (availability.get(family.toLowerCase())) continue;
    if (signal?.aborted) throw new Error("Presentation preview was closed.");
    const matched = await metricFallbackFaces(family);
    if (matched) {
      fontFaces.push(...matched.faces);
      substitutions.push(`${family} → ${matched.localFamily} (width-matched)`);
      continue;
    }
    const fallbackFaces = await getFallbackFaces(fallbackKind(family));
    if (fallbackFaces.length === 0) {
      unresolvedFamilies.push(family);
      continue;
    }
    for (const face of fallbackFaces) {
      fontFaces.push({
        family,
        source: `local("${escapeCssString(face.localName)}")`,
        descriptors: face.descriptors,
      });
    }
    substitutions.push(
      `${family} → ${fallbackFaces[0]?.localName.replace(/ (?:Bold|Italic).*$/, "") ?? "local font"}`,
    );
  }

  return {
    fontFaces,
    substitutions,
    unresolvedFamilies,
    limited: scan.limited,
  };
}

const browserFontProbeCache = new Map<string, Promise<boolean>>();

export function probeBrowserLocalFont(family: string): Promise<boolean> {
  const key = family.toLowerCase();
  let result = browserFontProbeCache.get(key);
  if (!result) {
    result = (async () => {
      if (typeof FontFace !== "function") return false;
      try {
        await new FontFace(
          "__presenter_copilot_local_font_probe__",
          `local("${escapeCssString(family)}")`,
        ).load();
        return true;
      } catch {
        return false;
      }
    })();
    browserFontProbeCache.set(key, result);
  }
  return result;
}
