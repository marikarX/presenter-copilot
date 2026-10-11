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

type FallbackKind = "sans" | "classified-sans" | "serif" | "monospace";

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
/** Whether CSS `font-family` resolves the name (local() also accepts PostScript names). */
export type CssFamilyProbe = (family: string) => boolean;

interface FontScanResult {
  families: string[];
  /** Lower-case families referenced with a PANOSE classification. */
  classified: Set<string>;
  limited: boolean;
}

const FALLBACK_FAMILIES: Record<FallbackKind, readonly string[]> = {
  // PowerPoint draws an unavailable font of unknown style in Calibri (independent of
  // the theme fonts), so Calibri comes first where it is installed.
  sans: ["Calibri", "Arial", "Liberation Sans", "Noto Sans"],
  // With a PANOSE classification PowerPoint lets Windows map to the closest installed
  // face, which is Arial for a sans-serif font.
  "classified-sans": ["Arial", "Calibri", "Liberation Sans", "Noto Sans"],
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
    [
      "arial nova cond",
      [
        { family: "Arial Narrow", regular: "108.5%", bold: "103.8%" },
        { family: "Calibri", regular: "97.6%", bold: "98.1%" },
      ],
    ],
    // Cloud fonts seen in real decks, matched within their style (humanist sans to
    // Segoe UI, condensed to Arial Narrow, old-style serif to Times New Roman).
    ["abadi", [{ family: "Segoe UI", regular: "97.7%", bold: "96.1%" }]],
    ["lato", [{ family: "Segoe UI", regular: "100.7%", bold: "95.5%" }]],
    ["nunito", [{ family: "Segoe UI", regular: "102.8%", bold: "99.3%" }]],
    ["nunito sans", [{ family: "Segoe UI", regular: "102.6%", bold: "99.3%" }]],
    ["roboto", [{ family: "Segoe UI", regular: "101.1%", bold: "96.1%" }]],
    ["raleway", [{ family: "Segoe UI", regular: "105.5%", bold: "101.8%" }]],
    ["open sans", [{ family: "Segoe UI", regular: "105.3%", bold: "105.1%" }]],
    ["montserrat", [{ family: "Segoe UI", regular: "113.4%", bold: "111.3%" }]],
    ["ubuntu", [{ family: "Segoe UI", regular: "102.5%", bold: "100.9%" }]],
    [
      "source sans pro",
      [{ family: "Calibri", regular: "102.0%", bold: "105.7%" }],
    ],
    ["oswald", [{ family: "Arial Narrow", regular: "98.5%", bold: "91.8%" }]],
    ["bembo", [{ family: "Times New Roman", regular: "99.5%", bold: "94.6%" }]],
    [
      "source code pro",
      [{ family: "Courier New", regular: "100%", bold: "100%" }],
    ],
    ["inconsolata", [{ family: "Consolas", regular: "90.9%", bold: "90.9%" }]],
  ]);

/**
 * Windows ascent and descent (OS/2 winAscent/winDescent, percent of the font size)
 * of the cloud fonts, read from the cached Office font files. PowerPoint places
 * text with these metrics (not the typo metrics Chromium prefers when a font sets
 * USE_TYPO_METRICS), so the width-matched fallback takes them over and a line
 * mixing it with other fonts keeps the height it has in PowerPoint.
 */
const CLOUD_FONT_METRICS: ReadonlyMap<string, readonly [number, number]> =
  new Map([
    ["aptos", [101, 27.5]],
    ["aptos display", [101, 27.5]],
    ["aptos narrow", [101, 27.5]],
    ["aptos serif", [101, 27.5]],
    ["abadi", [88.7, 24.6]],
    ["lato", [111.7, 29.9]],
    ["nunito", [107.7, 30]],
    ["nunito sans", [110.2, 32.7]],
    ["roboto", [95, 25]],
    ["raleway", [115.4, 23.4]],
    ["open sans", [106.9, 29.3]],
    ["montserrat", [110.9, 27]],
    ["ubuntu", [93.2, 18.9]],
    ["source sans pro", [98.4, 27.3]],
    ["oswald", [132.5, 37.7]],
    ["bembo", [89.6, 23.3]],
    ["source code pro", [98.4, 27.3]],
    ["inconsolata", [100.4, 45.4]],
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
  const classified = new Set<string>();
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
      const start = boundedXml.lastIndexOf("<", match.index ?? 0);
      const end = boundedXml.indexOf(">", match.index ?? 0);
      if (
        /\bpanose\s*=/.test(boundedXml.slice(start, end < 0 ? undefined : end))
      )
        classified.add(key);
      if (families.has(key)) continue;
      if (families.size >= MAX_FONT_FAMILIES) {
        limited = true;
        break;
      }
      families.set(key, family);
    }
    if (limited) break;
  }

  return { families: [...families.values()], classified, limited };
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
  probeCssFamily?: CssFamilyProbe,
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
    // A PostScript name such as "ArialMT" loads through local() but is not a CSS
    // family, so the browser would silently use its default font. Treat it as
    // missing so the normal fallback (for example Arial) applies.
    const local = await checkLocalFont(family);
    availability.set(
      family.toLowerCase(),
      local && (probeCssFamily ? probeCssFamily(family) : true),
    );
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
        const sizeAdjust =
          style.descriptors.weight === "700"
            ? candidate.bold
            : candidate.regular;
        // size-adjust is a supported FontFace descriptor missing from lib.dom.
        const descriptors: FontFaceDescriptors & { sizeAdjust: string } = {
          ...style.descriptors,
          sizeAdjust,
        };
        const metrics = CLOUD_FONT_METRICS.get(family.toLowerCase());
        if (metrics) {
          // Chromium scales the metric overrides by size-adjust as well.
          const scale = parseFloat(sizeAdjust) / 100;
          descriptors.ascentOverride = `${(metrics[0] / scale).toFixed(1)}%`;
          descriptors.descentOverride = `${(metrics[1] / scale).toFixed(1)}%`;
          descriptors.lineGapOverride = "0%";
        }
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
    const kind = fallbackKind(family);
    const fallbackFaces = await getFallbackFaces(
      kind === "sans" && scan.classified.has(family.toLowerCase())
        ? "classified-sans"
        : kind,
    );
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

const cssFamilyProbeCache = new Map<string, boolean>();

/** Detect CSS family resolution by comparing canvas widths against generic fonts. */
export function probeBrowserCssFamily(family: string): boolean {
  const key = family.toLowerCase();
  const cached = cssFamilyProbeCache.get(key);
  if (cached !== undefined) return cached;
  let available = true;
  try {
    const context = document.createElement("canvas").getContext("2d");
    if (context) {
      const sample = "mmmmmmmmmmlli1WQ@#0";
      available = ["monospace", "serif", "sans-serif"].some((generic) => {
        context.font = `72px ${generic}`;
        const baseline = context.measureText(sample).width;
        context.font = `72px "${escapeCssString(family)}", ${generic}`;
        return Math.abs(context.measureText(sample).width - baseline) > 0.5;
      });
    }
  } catch {
    available = true;
  }
  cssFamilyProbeCache.set(key, available);
  return available;
}

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
