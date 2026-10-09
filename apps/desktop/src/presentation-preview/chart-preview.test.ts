import { buildPresentation, type PptxFiles } from "@aiden0z/pptx-renderer";
import { DOMParser } from "@xmldom/xmldom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { normalizeAuthoredPiePreview } from "./chart-preview";

beforeEach(() =>
  vi.stubGlobal(
    "DOMParser",
    class {
      parseFromString(xml: string) {
        const document = new DOMParser().parseFromString(
          xml,
          "application/xml",
        );
        Object.defineProperty(document, "querySelector", {
          value: (selector: string) =>
            selector === "parsererror"
              ? (document.getElementsByTagName("parsererror")[0] ?? null)
              : null,
        });
        for (const element of Array.from(document.getElementsByTagName("*"))) {
          Object.defineProperty(element, "children", {
            get: () =>
              Array.from(element.childNodes).filter(
                (node) => node.nodeType === 1,
              ),
          });
        }
        return document;
      }
    },
  ),
);
afterEach(() => vi.unstubAllGlobals());
const ownPath = `ppt/charts/copilot-${"a".repeat(32)}.xml`;
const colors = ["2563EB", "D97706", "059669"];
function fixture(path = ownPath, pointColor = colors[1], count = 3) {
  const points = colors
    .map(
      (color, i) =>
        `<c:dPt><c:idx val="${i}"/><c:spPr><a:solidFill><a:srgbClr val="${i === 1 ? pointColor : color}"/></a:solidFill></c:spPr></c:dPt>`,
    )
    .join("");
  const xml = `<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><c:chart><c:plotArea><c:pieChart><c:ser>${points}<c:cat><c:strRef><c:strCache><c:ptCount val="${count}"/></c:strCache></c:strRef></c:cat></c:ser></c:pieChart></c:plotArea></c:chart></c:chartSpace>`;
  const files: PptxFiles = {
    contentTypes: "",
    presentation:
      "<p:presentation xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'/>",
    presentationRels: "",
    slides: new Map(),
    slideRels: new Map(),
    slideLayouts: new Map(),
    slideLayoutRels: new Map(),
    slideMasters: new Map(),
    slideMasterRels: new Map(),
    themes: new Map([
      [
        "ppt/theme/theme1.xml",
        `<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:themeElements><a:clrScheme name="Existing"><a:accent1><a:srgbClr val="FF0000"/></a:accent1></a:clrScheme></a:themeElements></a:theme>`,
      ],
    ]),
    media: new Map(),
    charts: new Map([[path, xml]]),
    chartRels: new Map(),
    chartStyles: new Map(),
    chartColors: new Map(),
    diagramDrawings: new Map(),
  };
  return { presentation: buildPresentation(files), xml };
}
it("repairs authored pie legend palette without changing slide themes or chart XML", () => {
  const { presentation } = fixture();
  const base = presentation.themes.values().next().value!;
  const chart = presentation.charts.get(ownPath)!;
  const original = chart.element!.toString();
  expect(normalizeAuthoredPiePreview(presentation)).toBe(1);
  expect(
    presentation.chartThemes!.get(ownPath)!.colorScheme.get("accent2"),
  ).toBe("D97706");
  expect(base.colorScheme.get("accent1")).toBe("FF0000");
  expect(chart.element!.toString()).toBe(original);
});
it.each([
  ["ppt/charts/chart1.xml", "D97706", 3],
  [ownPath, "FF0000", 3],
  [ownPath, "D97706", 25],
])("keeps imported or unsupported pie data intact", (path, color, count) => {
  const { presentation } = fixture(
    path as string,
    color as string,
    count as number,
  );
  expect(normalizeAuthoredPiePreview(presentation)).toBe(0);
  expect(presentation.chartThemes?.has(path as string) ?? false).toBe(false);
});
