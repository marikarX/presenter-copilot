import type {
  PresentationData,
  SlideRendererOptions,
  ChartNodeData,
  SlideData,
} from "@aiden0z/pptx-renderer";

type Xml = PresentationData["charts"] extends Map<string, infer T> ? T : never;
type Chart =
  NonNullable<SlideRendererOptions["chartInstances"]> extends Set<infer T>
    ? T
    : never;
type Labels = {
  deleted: boolean;
  value: boolean;
  category: boolean;
  series: boolean;
  percent: boolean;
  position?: string;
  format?: string;
  separator: string;
  custom?: string;
};
const defaults: Labels = {
  deleted: false,
  value: false,
  category: false,
  series: false,
  percent: false,
  separator: ", ",
};

// Preview-only formatting. Unknown native formats retain the renderer's own text;
// this does not claim a complete Excel format engine or mutate workbook caches.
export function formatLabelNumber(value: number, code?: string): string | null {
  if (!Number.isFinite(value) || (code && code.length > 256)) return null;
  if (!code || code === "General") return String(value);
  const sections = code.match(/(?:"[^"]*"|\\.|[^;])+/g);
  if (!sections) return null;
  const sectionIndex =
    value < 0 && sections.length > 1
      ? 1
      : value === 0 && sections.length > 2
        ? 2
        : 0;
  let format = sections[sectionIndex]!.replace(
    /\[(?:Black|Blue|Cyan|Green|Magenta|Red|White|Yellow|Color\d+)\]/gi,
    "",
  );
  if (/[[\]_*/@]/.test(format)) return null;
  const literals: string[] = [];
  format = format.replace(
    /"([^"]*)"|\\(.)/g,
    (_all, quoted: string | undefined, escaped: string | undefined) => {
      literals.push(quoted ?? escaped ?? "");
      return `\uE000${String.fromCharCode(65 + literals.length - 1)}\uE001`;
    },
  );
  const match =
    /^([^#0?]*)([#0,]+(?:\.[#0]+)?[,]*(?:[Ee][+-]0+)?)([^#0?]*)$/.exec(format);
  if (!match) return null;
  const restore = (text: string) =>
    text.replace(
      /\uE000([A-Z])\uE001/g,
      (_all, index: string) => literals[index.charCodeAt(0) - 65] ?? "",
    );
  const prefix = restore(match[1]!),
    suffix = restore(match[3]!);
  const percents = (match[1]! + match[3]!).split("%").length - 1;
  const scale = match[2]!.match(/,+$/)?.[0].length ?? 0;
  const pattern = match[2]!.replace(/,+$/, "");
  const decimals = pattern.match(/\.([#0]+)/)?.[1] ?? "";
  if (decimals.length > 10) return null;
  const amount = (Math.abs(value) * 100 ** percents) / 1000 ** scale;
  let text: string;
  const exponent = pattern.match(/[Ee]([+-])(0+)$/);
  if (exponent) {
    const [mantissa, power] = amount.toExponential(decimals.length).split("e");
    const number = Number(power);
    text =
      mantissa +
      "E" +
      (number < 0 ? "-" : exponent[1]! === "+" ? "+" : "") +
      String(Math.abs(number)).padStart(exponent[2]!.length, "0");
  } else
    text = new Intl.NumberFormat("en-US", {
      useGrouping: pattern.includes(","),
      minimumFractionDigits: (decimals.match(/0/g) ?? []).length,
      maximumFractionDigits: decimals.length,
      minimumIntegerDigits: Math.min(
        21,
        Math.max(1, (pattern.split(".")[0]!.match(/0/g) ?? []).length),
      ),
    }).format(amount);
  return (value < 0 && sectionIndex === 0 ? "-" : "") + prefix + text + suffix;
}

function settings(node: Xml, base: Labels): Labels {
  const result = { ...base };
  for (const [field, tag] of [
    ["deleted", "delete"],
    ["value", "showVal"],
    ["category", "showCatName"],
    ["series", "showSerName"],
    ["percent", "showPercent"],
  ] as const) {
    const child = node.child(tag);
    if (child.exists())
      result[field] = ["1", "true"].includes(child.attr("val") ?? "1");
  }
  const position = node.child("dLblPos");
  if (position.exists()) result.position = position.attr("val");
  const fmt = node.child("numFmt");
  if (fmt.exists())
    result.format = ["1", "true"].includes(fmt.attr("sourceLinked") ?? "0")
      ? undefined
      : fmt.attr("formatCode");
  const separator = node.child("separator");
  if (separator.exists()) result.separator = separator.text();
  const rich = node.child("tx").child("rich");
  if (rich.exists())
    result.custom = rich
      .children("p")
      .map((p) =>
        p
          .children("r")
          .map((r) => r.child("t").text())
          .join(""),
      )
      .join("\n");
  return result;
}
function point(node: Xml, index: number): Xml | undefined {
  return node
    .children("dLbl")
    .find((p) => p.child("idx").numAttr("val") === index);
}
function cache(
  node: Xml,
  field: string,
  reference: string,
  kind: string,
): string[] {
  const points = node
    .child(field)
    .child(reference)
    .child(kind)
    .children("pt")
    .sort((a, b) => (a.numAttr("idx") ?? -1) - (b.numAttr("idx") ?? -1));
  // A compacted sparse cache can associate a label with the wrong plotted point.
  if (points.some((p, index) => p.numAttr("idx") !== index)) return [];
  return points.map((p) => p.child("v").text());
}

export function chartLabelSeries(root: Xml): {
  name: string;
  values: number[];
  labels: Labels[];
  categories: string[];
  kind: string;
  cacheFormat?: string;
}[] {
  const plot = root.child("chart").child("plotArea");
  const plots = plot.allChildren().filter((p) => p.localName.endsWith("Chart"));
  if (
    plots.length !== 1 ||
    !["barChart", "lineChart", "pieChart"].includes(plots[0]!.localName)
  )
    return [];
  const native = plots[0]!,
    global = native.child("dLbls");
  return native
    .children("ser")
    .sort(
      (a, b) =>
        (a.child("order").numAttr("val") ?? 0) -
        (b.child("order").numAttr("val") ?? 0),
    )
    .map((series) => {
      const own = series.child("dLbls");
      const inherited = settings(own, settings(global, defaults));
      const cached = cache(series, "val", "numRef", "numCache");
      const values = cached.every(
        (v) => v.trim() !== "" && Number.isFinite(Number(v)),
      )
        ? cached.map(Number)
        : [];
      const categories = cache(series, "cat", "strRef", "strCache");
      return {
        name:
          cache(series, "tx", "strRef", "strCache")[0] ??
          series.child("tx").child("v").text(),
        values,
        categories,
        kind: native.localName,
        cacheFormat:
          series
            .child("val")
            .child("numRef")
            .child("numCache")
            .child("formatCode")
            .text() || undefined,
        labels: values.map((_v, index) => {
          let state = { ...inherited };
          const globalPoint = point(global, index),
            ownPoint = point(own, index);
          if (globalPoint) state = settings(globalPoint, state);
          if (ownPoint) state = settings(ownPoint, state);
          return state;
        }),
      };
    });
}
export function labelText(
  series: ReturnType<typeof chartLabelSeries>[number],
  index: number,
): string | null {
  const label = series.labels[index];
  if (!label || label.deleted) return "";
  const value = series.values[index];
  if (value === undefined) return null;
  if (label.custom !== undefined) return label.custom;
  const parts: string[] = [];
  if (label.series) {
    if (!series.name) return null;
    parts.push(series.name);
  }
  if (label.category) {
    if (series.categories[index] === undefined) return null;
    parts.push(series.categories[index]!);
  }
  if (label.value) {
    const text = formatLabelNumber(value, label.format ?? series.cacheFormat);
    if (text === null) return null;
    parts.push(text);
  }
  if (label.percent && series.kind === "pieChart") {
    const total = series.values.reduce(
      (sum, value) => sum + Math.abs(value),
      0,
    );
    const ratio = total ? Math.abs(value) / total : 0;
    const code = label.format ?? "0%";
    const text = formatLabelNumber(
      code.includes("%") ? ratio : ratio * 100,
      code,
    );
    if (text === null) return null;
    parts.push(text + (code.includes("%") ? "" : "%"));
  }
  return parts.join(label.separator);
}
// Native axis data is read independently of series cache formats. ECharts cannot
// reproduce every Office tick-label placement; complex scales retain its rendering.
export function nativeAxisOptions(
  root: Xml,
  axisKind: "category" | "value",
  current: Record<string, unknown>,
): Record<string, unknown> | null {
  const plot = root.child("chart").child("plotArea");
  const axes = plot
    .allChildren()
    .filter((node) =>
      ["catAx", "valAx", "dateAx", "serAx"].includes(node.localName),
    );
  if (
    axes.length !== 2 ||
    axes.filter((node) => node.localName === "catAx").length !== 1 ||
    axes.filter((node) => node.localName === "valAx").length !== 1
  )
    return null;
  const axis = axes.find(
    (node) => node.localName === (axisKind === "value" ? "valAx" : "catAx"),
  )!;
  const scaling = axis.child("scaling");
  if (scaling.child("logBase").exists() || axis.child("dispUnits").exists())
    return null;
  const previousLabel =
    typeof current.axisLabel === "object" && current.axisLabel !== null
      ? (current.axisLabel as Record<string, unknown>)
      : {};
  const grid = (field: string) => ({
    ...(typeof current[field] === "object" && current[field] !== null
      ? (current[field] as Record<string, unknown>)
      : {}),
    show: axis
      .child(field === "splitLine" ? "majorGridlines" : "minorGridlines")
      .exists(),
  });
  const fmt = axis.child("numFmt");
  const code =
    fmt.exists() && !["1", "true"].includes(fmt.attr("sourceLinked") ?? "0")
      ? fmt.attr("formatCode")
      : undefined;
  const rich = axis.child("title").child("tx").child("rich");
  const name = rich.exists()
    ? rich
        .children("p")
        .map((p) =>
          p
            .children("r")
            .map((r) => r.child("t").text())
            .join(""),
        )
        .join("\n")
    : undefined;
  const number = (tag: string) => {
    const child = (tag === "min" || tag === "max" ? scaling : axis).child(tag);
    return child.exists() ? (child.numAttr("val") ?? null) : null;
  };
  const major = number("majorUnit"),
    minor = number("minorUnit");
  const split =
    typeof major === "number" && typeof minor === "number" && minor > 0
      ? major / minor
      : null;
  return {
    ...current,
    show: !["1", "true"].includes(axis.child("delete").attr("val") ?? "0"),
    ...(name !== undefined
      ? { name, nameLocation: "middle", nameGap: 40 }
      : {}),
    axisLabel: {
      ...previousLabel,
      show: axis.child("tickLblPos").attr("val") !== "none",
      ...(code
        ? {
            formatter: (value: number) =>
              formatLabelNumber(value, code) ?? String(value),
          }
        : {}),
    },
    splitLine: grid("splitLine"),
    minorSplitLine: grid("minorSplitLine"),
    ...(axisKind === "value"
      ? {
          min: number("min"),
          max: number("max"),
          interval: major,
          ...(split !== null &&
          Number.isInteger(split) &&
          split >= 1 &&
          split <= 100
            ? {
                minorTick: {
                  ...(typeof current.minorTick === "object" &&
                  current.minorTick !== null
                    ? (current.minorTick as Record<string, unknown>)
                    : {}),
                  splitNumber: split,
                },
              }
            : {}),
        }
      : {}),
  };
}

const barPositions: Record<string, string> = {
  ctr: "inside",
  inEnd: "insideTop",
  inBase: "insideBottom",
  outEnd: "top",
};
const linePositions: Record<string, string> = {
  ctr: "inside",
  t: "top",
  b: "bottom",
  l: "left",
  r: "right",
};

// Match by the chart's intrinsic box, not series names or insertion order. Refuse
// ambiguous overlapping boxes so an imported chart cannot receive another's labels.
export function repairChartLabels(
  presentation: PresentationData,
  slide: SlideData,
  charts: Set<Chart>,
): number {
  let count = 0;
  for (const chart of charts) {
    const dom = chart.getDom().parentElement;
    if (!dom) continue;
    const nodes = slide.nodes.filter(
      (node): node is ChartNodeData =>
        node.nodeType === "chart" &&
        Math.abs(node.position.x - parseFloat(dom.style.left)) < 0.1 &&
        Math.abs(node.position.y - parseFloat(dom.style.top)) < 0.1 &&
        Math.abs(node.size.w - parseFloat(dom.style.width)) < 0.1 &&
        Math.abs(node.size.h - parseFloat(dom.style.height)) < 0.1,
    );
    if (nodes.length !== 1) continue;
    const root = presentation.charts.get(nodes[0]!.chartPath);
    if (!root) continue;
    const existingOption = chart.getOption();
    const barHorizontal =
      root
        .child("chart")
        .child("plotArea")
        .child("barChart")
        .child("barDir")
        .attr("val") === "bar";
    const axisUpdate: Record<string, unknown> = {};
    for (const dimension of ["xAxis", "yAxis"] as const) {
      const entries = existingOption[dimension];
      if (!Array.isArray(entries) || entries.length !== 1) continue;
      const kind =
        (dimension === "xAxis") !== barHorizontal ? "category" : "value";
      const value = nativeAxisOptions(
        root,
        kind,
        entries[0] as Record<string, unknown>,
      );
      if (value) axisUpdate[dimension] = [value];
    }
    if (Object.keys(axisUpdate).length) chart.setOption(axisUpdate);
    const source = chartLabelSeries(root);
    if (!source.length) continue;
    const option = chart.getOption();
    const series = Array.isArray(option.series) ? option.series : [];
    if (series.length !== source.length) continue;
    const horizontal =
      root
        .child("chart")
        .child("plotArea")
        .child("barChart")
        .child("barDir")
        .attr("val") === "bar";
    const updated = series.map((existing, index) => {
      const info = source[index];
      if (!info) return existing;
      const current = existing as Record<string, unknown>;
      const data = Array.isArray(current.data) ? current.data : [];
      if (
        data.length !== info.values.length ||
        data.some((entry, pointIndex) => {
          const value =
            typeof entry === "object" && entry !== null
              ? (entry as Record<string, unknown>).value
              : entry;
          return typeof value !== "number" || value !== info.values[pointIndex];
        })
      )
        return existing;
      return {
        ...current,
        animation: false,
        data: data.map((old, pointIndex) => {
          const entry: Record<string, unknown> =
            typeof old === "object" && old !== null
              ? (old as Record<string, unknown>)
              : { value: old };
          const native = info.labels[pointIndex];
          const text = labelText(info, pointIndex);
          if (!native || text === null) return old;
          const previous =
            typeof entry.label === "object" && entry.label !== null
              ? (entry.label as Record<string, unknown>)
              : {};
          const position =
            info.kind === "barChart"
              ? horizontal
                ? (
                    {
                      ctr: "inside",
                      inEnd: "insideRight",
                      inBase: "insideLeft",
                      outEnd: "right",
                    } as Record<string, string>
                  )[native.position ?? ""]
                : barPositions[native.position ?? ""]
              : info.kind === "lineChart"
                ? linePositions[native.position ?? ""]
                : (
                    {
                      ctr: "inside",
                      inEnd: "inside",
                      outEnd: "outside",
                      bestFit: "outside",
                    } as Record<string, string>
                  )[native.position ?? ""];
          const negative = (info.values[pointIndex] ?? 0) < 0;
          const mirrored: Record<string, string> = {
            top: "bottom",
            insideTop: "insideBottom",
            insideBottom: "insideTop",
            right: "left",
            insideRight: "insideLeft",
            insideLeft: "insideRight",
          };
          const barPosition =
            info.kind === "barChart" && negative && position
              ? (mirrored[position] ?? position)
              : position;
          return {
            ...entry,
            label: {
              ...previous,
              show: text !== "",
              formatter: () => text,
              ...(info.kind === "pieChart" ? { overflow: "break" } : {}),
              ...(barPosition ? { position: barPosition } : {}),
            },
          };
        }),
      };
    });
    chart.setOption({
      animation: false,
      animationDuration: 0,
      animationDurationUpdate: 0,
      series: updated,
    });
    count += 1;
  }
  // Every preview chart must settle before capture, including unmodified charts.
  for (const chart of charts) {
    chart.setOption({
      animation: false,
      animationDuration: 0,
      animationDurationUpdate: 0,
    });
    chart.resize();
    chart.getZr().flush();
  }
  return count;
}
