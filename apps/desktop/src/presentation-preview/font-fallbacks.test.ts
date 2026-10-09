import { describe, expect, it } from "vitest";

import type { PresentationData, PptxFiles } from "@aiden0z/pptx-renderer";

import { resolvePreviewFonts } from "./font-fallbacks";

function pptxFiles(slideXml: string): PptxFiles {
  return {
    contentTypes: "",
    presentation: "<p:presentation />",
    presentationRels: "",
    slides: new Map([["ppt/slides/slide1.xml", slideXml]]),
    slideRels: new Map(),
    slideLayouts: new Map(),
    slideLayoutRels: new Map(),
    slideMasters: new Map(),
    slideMasterRels: new Map(),
    themes: new Map(),
    media: new Map(),
    charts: new Map(),
    chartStyles: new Map(),
    chartColors: new Map(),
    diagramDrawings: new Map(),
  };
}

function presentationData(
  embeddedFamilies: readonly string[] = [],
): PresentationData {
  return {
    embeddedFontFamilies: new Map(
      embeddedFamilies.map((family) => [family, `embedded:${family}`]),
    ),
  } as unknown as PresentationData;
}

describe("presentation preview font fallback", () => {
  it("maps only missing referenced families to available local fonts", async () => {
    const files = pptxFiles(
      '<a:rPr typeface="Presenter Copilot Missing Font Smoke"/><a:latin typeface="Arial"/><a:ea typeface="+mn-lt"/><a:cs typeface="Embedded Display"/>',
    );
    const locallyAvailable = new Set([
      "arial",
      "arial bold",
      "arial italic",
      "arial bold italic",
    ]);
    const resolution = await resolvePreviewFonts(
      files,
      presentationData(["Embedded Display"]),
      async (family) => locallyAvailable.has(family.toLowerCase()),
    );

    expect(resolution.substitutions).toEqual([
      "Presenter Copilot Missing Font Smoke → Arial",
    ]);
    expect(resolution.unresolvedFamilies).toEqual([]);
    expect(resolution.fontFaces).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          family: "Presenter Copilot Missing Font Smoke",
          source: 'local("Arial")',
          descriptors: { weight: "400", style: "normal" },
        }),
        expect.objectContaining({
          family: "Presenter Copilot Missing Font Smoke",
          source: 'local("Arial Bold")',
          descriptors: { weight: "700", style: "normal" },
        }),
      ]),
    );
    expect(resolution.fontFaces).toHaveLength(4);
    expect(resolution.limited).toBe(false);
  });

  it("rejects unsafe names and reports a bounded scan", async () => {
    const families = Array.from(
      { length: 65 },
      (_, index) =>
        `<a:rPr typeface="Font ${String(index).padStart(2, "0")}"/>`,
    ).join("");
    const files = pptxFiles(
      `<a:rPr typeface="Bad; font-family: url(https://invalid)"/>${families}`,
    );
    const resolution = await resolvePreviewFonts(
      files,
      presentationData(),
      async () => false,
    );

    expect(resolution.limited).toBe(true);
    expect(resolution.unresolvedFamilies).toHaveLength(64);
    expect(resolution.unresolvedFamilies[0]).toBe("Font 00");
    expect(resolution.unresolvedFamilies.at(-1)).toBe("Font 63");
  });

  it("stops immediately for a closed preview", async () => {
    const controller = new AbortController();
    controller.abort();
    let probes = 0;

    await expect(
      resolvePreviewFonts(
        pptxFiles('<a:rPr typeface="Missing Face"/>'),
        presentationData(),
        async () => {
          probes += 1;
          return false;
        },
        controller.signal,
      ),
    ).rejects.toThrow("Presentation preview was closed.");
    expect(probes).toBe(0);
  });
});
