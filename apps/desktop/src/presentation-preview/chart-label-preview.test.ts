import { buildPresentation, type PptxFiles } from "@aiden0z/pptx-renderer";
import { DOMParser } from "@xmldom/xmldom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  chartLabelSeries,
  formatLabelNumber,
  labelText,
  repairChartLabels,
  nativeAxisOptions,
} from "./chart-label-preview";

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

it.each([
  [0, "0.0", "0.0"],
  [1234.5, "$#,##0.00", "$1,234.50"],
  [-12.5, "$0.00;($0.00)", "($12.50)"],
  [0.268456, "0.0%", "26.8%"],
  [12.25, "0.0", "12.3"],
  [1234, "0.00E+00", "1.23E+03"],
  [1500000, "0.0,,", "1.5"],
  [0, '0.0;[Red](0.0);"None"', null],
  [1, "m/d/yyyy", null],
  [1, "[>=100]0.0;0.0", null],
])(
  "formats native label numbers without altering cached values",
  (value, format, expected) => {
    expect(formatLabelNumber(Number(value), String(format))).toBe(expected);
  },
);
function fixture(
  extra = "",
  kind = "barChart",
  transform = (xml: string) => xml,
) {
  const path = "ppt/charts/chart1.xml";
  const xml = `<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart><c:plotArea><c:${kind}><c:ser><c:order val="0"/><c:tx><c:strRef><c:strCache><c:pt idx="0"><c:v>Revenue</c:v></c:pt></c:strCache></c:strRef></c:tx>${extra}<c:cat><c:strRef><c:strCache><c:pt idx="0"><c:v>Baseline</c:v></c:pt><c:pt idx="1"><c:v>Pilot</c:v></c:pt></c:strCache></c:strRef></c:cat><c:val><c:numRef><c:numCache><c:formatCode>0</c:formatCode><c:pt idx="0"><c:v>0</c:v></c:pt><c:pt idx="1"><c:v>12.25</c:v></c:pt></c:numCache></c:numRef></c:val></c:ser></c:${kind}></c:plotArea></c:chart></c:chartSpace>`;
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
    charts: new Map([[path, transform(xml)]]),
    chartRels: new Map(),
    chartStyles: new Map(),
    chartColors: new Map(),
    diagramDrawings: new Map(),
  };
  return buildPresentation(files);
}

const labels =
  '<c:dLbls><c:numFmt formatCode="$0.00" sourceLinked="0"/><c:dLblPos val="outEnd"/><c:showVal val="1"/><c:showCatName val="1"/><c:showSerName val="1"/><c:separator> | </c:separator></c:dLbls>';
it("composes names and currency including zero, and leaves chart XML intact", () => {
  const presentation = fixture(labels),
    root = presentation.charts.get("ppt/charts/chart1.xml")!;
  const xml = root.element!.toString();
  const data = chartLabelSeries(root)[0]!;
  expect(labelText(data, 0)).toBe("Revenue | Baseline | $0.00");
  expect(labelText(data, 1)).toBe("Revenue | Pilot | $12.25");
  expect(root.element!.toString()).toBe(xml);
});
it("uses point override text and formats, deletion, and linked cache formatting", () => {
  const extra =
    '<c:dLbls><c:dLbl><c:idx val="0"/><c:tx><c:rich><a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:t>Reviewed custom label</a:t></a:r></a:p></c:rich></c:tx></c:dLbl><c:dLbl><c:idx val="1"/><c:delete val="1"/></c:dLbl><c:showVal val="1"/><c:numFmt sourceLinked="1" formatCode="$0.00"/></c:dLbls>';
  const data = chartLabelSeries(
    fixture(extra).charts.get("ppt/charts/chart1.xml")!,
  )[0]!;
  expect(labelText(data, 0)).toBe("Reviewed custom label");
  expect(labelText(data, 1)).toBe("");
});
it("formats pie percentage ratios using the explicit precision", () => {
  const data = chartLabelSeries(
    fixture(
      '<c:dLbls><c:numFmt sourceLinked="0" formatCode="0.0%"/><c:showPercent val="1"/></c:dLbls>',
      "pieChart",
    ).charts.get("ppt/charts/chart1.xml")!,
  )[0]!;
  expect(labelText(data, 0)).toBe("0.0%");
  expect(labelText(data, 1)).toBe("100.0%");
});
it.each([false, true])(
  "repairs and settles charts while retaining axes, tooltips, styles and signed values (%s)",
  (negative) => {
    const presentation = fixture(labels, "barChart", (xml) =>
      negative ? xml.replace("<c:v>12.25</c:v>", "<c:v>-12.25</c:v>") : xml,
    );
    const value = negative ? -12.25 : 12.25;
    const option = {
      yAxis: [{ min: 0, max: 20 }],
      tooltip: { valueFormatter: "original" },
      series: [
        {
          name: "Revenue",
          data: [{ value: 0, label: { color: "red" } }, value],
        },
      ],
    };
    const setOption = vi.fn(),
      flush = vi.fn(),
      resize = vi.fn();
    const chart = {
      getDom: () => ({
        parentElement: {
          style: { left: "10px", top: "20px", width: "300px", height: "200px" },
        },
      }),
      getOption: () => option,
      setOption,
      resize,
      getZr: () => ({ flush }),
    };
    const slide = {
      nodes: [
        {
          nodeType: "chart",
          id: "chart",
          name: "Revenue",
          chartPath: "ppt/charts/chart1.xml",
          position: { x: 10, y: 20 },
          size: { w: 300, h: 200 },
          rotation: 0,
          flipH: false,
          flipV: false,
        },
      ],
    };
    expect(
      repairChartLabels(
        presentation,
        slide as Parameters<typeof repairChartLabels>[1],
        new Set([chart]) as unknown as Parameters<typeof repairChartLabels>[2],
      ),
    ).toBe(1);
    const updated = setOption.mock.calls[0]![0].series[0];
    expect(updated.data[0].label.formatter()).toBe(
      "Revenue | Baseline | $0.00",
    );
    expect(updated.data[0].label.color).toBe("red");
    expect(updated.data[1].label.formatter()).toBe(
      `Revenue | Pilot | ${negative ? "-" : ""}$12.25`,
    );
    expect(updated.data[1].label.position).toBe(negative ? "bottom" : "top");
    expect(updated.data[1].value).toBe(value);
    expect(option.yAxis).toEqual([{ min: 0, max: 20 }]);
    expect(option.tooltip.valueFormatter).toBe("original");
    expect(flush).toHaveBeenCalledOnce();
    expect(resize).toHaveBeenCalledOnce();
  },
);

it("refuses sparse caches and combo charts instead of shifting point labels", () => {
  const sparse = fixture(labels, "barChart", (xml) =>
    xml.replace('idx="1"><c:v>12.25', 'idx="3"><c:v>12.25'),
  );
  expect(
    chartLabelSeries(sparse.charts.get("ppt/charts/chart1.xml")!)[0]!.values,
  ).toEqual([]);
  const combo = fixture(labels, "barChart", (xml) =>
    xml.replace("</c:plotArea>", "<c:areaChart/></c:plotArea>"),
  );
  expect(chartLabelSeries(combo.charts.get("ppt/charts/chart1.xml")!)).toEqual(
    [],
  );
});
it("retains renderer fallback when category caches are sparse or unsupported", () => {
  const presentation = fixture(labels, "barChart", (xml) =>
    xml.replace('idx="1"><c:v>Pilot', 'idx="3"><c:v>Pilot'),
  );
  expect(
    labelText(
      chartLabelSeries(presentation.charts.get("ppt/charts/chart1.xml")!)[0]!,
      1,
    ),
  ).toBeNull();
});

it("lets linked point formatting replace an inherited explicit format", () => {
  const presentation = fixture(
    labels.replace(
      "<c:dLbls>",
      '<c:dLbls><c:dLbl><c:idx val="1"/><c:numFmt sourceLinked="1" formatCode="$0.00"/></c:dLbl>',
    ),
  );
  const data = chartLabelSeries(
    presentation.charts.get("ppt/charts/chart1.xml")!,
  )[0]!;
  expect(labelText(data, 0)).toBe("Revenue | Baseline | $0.00");
  expect(labelText(data, 1)).toBe("Revenue | Pilot | 12");
});

it("uses native value-axis bounds, units, titles, gridlines and formats without changing caches", () => {
  const presentation = fixture("", "barChart", (xml) =>
    xml.replace(
      "</c:plotArea>",
      '<c:catAx><c:scaling/></c:catAx><c:valAx><c:scaling><c:min val="-5"/><c:max val="30"/></c:scaling><c:majorUnit val="5"/><c:minorUnit val="1"/><c:majorGridlines/><c:minorGridlines/><c:numFmt sourceLinked="0" formatCode="$0.0"/><c:title><c:tx><c:rich xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>Revenue ($)</a:t></a:r></a:p></c:rich></c:tx></c:title></c:valAx></c:plotArea>',
    ),
  );
  const root = presentation.charts.get("ppt/charts/chart1.xml")!;
  const before = root.element!.toString();
  const value = nativeAxisOptions(root, "value", {
    axisLabel: { color: "red" },
    splitLine: { lineStyle: { color: "blue" } },
  })!;
  expect(value.min).toBe(-5);
  expect(value.max).toBe(30);
  expect(value.interval).toBe(5);
  expect(value.name).toBe("Revenue ($)");
  expect(
    (value.axisLabel as { formatter: (n: number) => string }).formatter(0),
  ).toBe("$0.0");
  expect(value.splitLine).toEqual({ show: true, lineStyle: { color: "blue" } });
  expect(value.minorTick).toEqual({ splitNumber: 5 });
  expect(root.element!.toString()).toBe(before);
});
it("retains complex or missing axis rendering", () => {
  const root = fixture().charts.get("ppt/charts/chart1.xml")!;
  expect(nativeAxisOptions(root, "value", {})).toBeNull();
});
