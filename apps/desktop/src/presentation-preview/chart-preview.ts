import type { PresentationData } from "@aiden0z/pptx-renderer";

const COLORS = ["2563EB", "D97706", "059669", "9333EA", "DC2626", "0891B2"];

// The renderer builds pie and doughnut legends from the theme palette, ignoring direct dPt
// fills used by the slices. Scope this repair to our bounded authored charts;
// clone a chart-local theme so slides and unrelated imported charts stay intact.
export function normalizeAuthoredPiePreview(
  presentation: PresentationData,
): number {
  let repaired = 0;
  const fallback = presentation.themes.values().next().value;
  if (!fallback) return repaired;
  for (const [path, root] of presentation.charts) {
    if (repaired >= 256) break;
    if (!/^ppt\/charts\/copilot-[a-f0-9]{32}\.xml$/.test(path)) continue;
    const plot = root.child("chart").child("plotArea");
    const charts = plot
      .allChildren()
      .filter((node) => node.localName.endsWith("Chart"));
    const pie = charts[0];
    if (
      charts.length !== 1 ||
      !pie ||
      (pie.localName !== "pieChart" && pie.localName !== "doughnutChart")
    )
      continue;
    const series = pie.children("ser");
    const first = series[0];
    if (series.length !== 1 || !first) continue;
    const count = first
      .child("cat")
      .child("strRef")
      .child("strCache")
      .child("ptCount")
      .numAttr("val");
    const points = first.children("dPt");
    if (!count || count < 1 || count > 24 || points.length !== count) continue;
    if (
      points.some(
        (point, index) =>
          point.child("idx").numAttr("val") !== index ||
          point
            .child("spPr")
            .child("solidFill")
            .child("srgbClr")
            .attr("val") !== COLORS[index % COLORS.length],
      )
    )
      continue;
    const theme = presentation.chartThemes?.get(path) ?? fallback;
    const colorScheme = new Map(theme.colorScheme);
    COLORS.forEach((color, index) =>
      colorScheme.set(`accent${index + 1}`, color),
    );
    presentation.chartThemes ??= new Map();
    presentation.chartThemes.set(path, { ...theme, colorScheme });
    repaired += 1;
  }
  return repaired;
}
