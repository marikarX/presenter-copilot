import { describe, expect, it } from "vitest";
import { guidedTranslation } from "./canvas-guides";
import { spacingCandidates } from "./spacing-guides";
import { translationOperations, type LayoutObject } from "./object-layout";
const box = (
  id: string,
  x: number,
  y: number,
  w = 80,
  h = 50,
): LayoutObject => ({
  object_id: id,
  name: id,
  geometry_editable: true,
  geometry: { x_emu: x, y_emu: y, width_emu: w, height_emu: h },
});
const size = { width: 1000, height: 1000 },
  tolerance = { x: 6, y: 6 };
const row = [
  box("a", 100, 700),
  box("left", 200, 100, 100, 100),
  box("right", 600, 100, 100, 100),
];
describe("equal-spacing drag guides", () => {
  it("shows gap witnesses when an edge guide resolves to the same exact offset", () => {
    const objects = [
      box("a", 100, 700),
      box("left", 320, 100, 100, 50),
      box("right", 570, 100, 100, 50),
      box("top", 800, 200, 100, 50),
    ];
    const r = guidedTranslation(
      objects,
      ["a"],
      "slide",
      719,
      -600,
      size,
      10,
      tolerance,
    );
    expect(r.operations[0]!.params.replacement_geometry.x_emu).toBe(820);
    expect(
      r.guides.filter((g) => g.gap).map((g) => g.gap!.end - g.gap!.start),
    ).toEqual([150, 150]);
  });

  it("inserts a selection between references with two exact equal gaps despite grid rounding", () => {
    const r = guidedTranslation(
      row,
      ["a"],
      "slide",
      307,
      -600,
      size,
      100,
      tolerance,
    );
    expect(r.operations[0]!.params.replacement_geometry.x_emu).toBe(410);
    const gaps = r.guides.filter((g) => g.gap).map((g) => g.gap!);
    expect(gaps).toEqual([
      { start: 300, end: 410, cross: 125 },
      { start: 490, end: 600, cross: 125 },
    ]);
  });
  it("continues the existing gap before and after a row", () => {
    const objects = [
      row[0]!,
      box("left", 300, 100, 100, 100),
      box("right", 600, 100, 100, 100),
    ];
    for (const [dx, x] of [
      [-77, 20],
      [797, 900],
    ]) {
      const r = guidedTranslation(
        objects,
        ["a"],
        "slide",
        dx!,
        -600,
        size,
        100,
        tolerance,
      );
      expect(r.operations[0]!.params.replacement_geometry.x_emu).toBe(x);
      expect(
        r.guides.filter((g) => g.gap).map((g) => g.gap!.end - g.gap!.start),
      ).toEqual([200, 200]);
    }
  });
  it("handles vertical insertion with independently scaled distances", () => {
    const objects = [
      box("a", 700, 100, 50, 80),
      box("top", 100, 200, 100, 100),
      box("bottom", 100, 600, 100, 100),
    ];
    const r = guidedTranslation(
      objects,
      ["a"],
      "slide",
      -600,
      307,
      size,
      100,
      tolerance,
    );
    expect(r.operations[0]!.params.replacement_geometry.y_emu).toBe(410);
    expect(r.guides.filter((g) => g.gap).map((g) => g.gap)).toEqual([
      { start: 300, end: 410, cross: 125 },
      { start: 490, end: 600, cross: 125 },
    ]);
  });
  it("preserves every member dimension and internal offset in a multi-selection", () => {
    const objects = [...row, box("b", 200, 700)];
    const r = guidedTranslation(
      objects,
      ["a", "b"],
      "slide",
      257,
      -600,
      size,
      100,
      tolerance,
    );
    const a = r.operations[0]!.params.replacement_geometry,
      b = r.operations[1]!.params.replacement_geometry;
    expect(a.x_emu).toBe(360);
    expect(b.x_emu - a.x_emu).toBe(100);
    expect(a.width_emu).toBe(80);
    expect(b.width_emu).toBe(80);
    expect(
      r.guides.filter((g) => g.gap).map((g) => g.gap!.end - g.gap!.start),
    ).toEqual([60, 60]);
  });
  it("retains the old transaction when guides are disabled", () => {
    const r = guidedTranslation(row, ["a"], "slide", 307, -600, size, 100);
    expect(r.operations).toEqual(
      translationOperations(row, ["a"], "slide", 307, -600, size, 100),
    );
    expect(r.guides).toEqual([]);
  });
  it("rejects invalid, read-only and different-lane witnesses", () => {
    for (const ref of [
      { ...row[2]!, geometry_editable: false },
      box("right", 600, 300, 100, 100),
      box("right", 1100, 100, 100, 100),
    ]) {
      const r = guidedTranslation(
        [row[0]!, row[1]!, ref],
        ["a"],
        "slide",
        307,
        -600,
        size,
        100,
        tolerance,
      );
      expect(r.guides.some((g) => g.gap)).toBe(false);
    }
  });
  it("rejects out-of-bounds, overlapping and crowded placement candidates", () => {
    const selection = { left: 100, top: 700, right: 180, bottom: 750 };
    expect(
      spacingCandidates(row, ["a"], size, selection, "x", -500, -600, 6),
    ).toEqual([]);
    const crowded = [...row, box("obstacle", 400, 100, 100, 100)];
    expect(
      spacingCandidates(crowded, ["a"], size, selection, "x", 307, -600, 6),
    ).toEqual([]);
    const wide = [box("a", 100, 700, 400), row[1]!, row[2]!];
    expect(
      spacingCandidates(
        wide,
        ["a"],
        size,
        { ...selection, right: 500 },
        "x",
        150,
        -600,
        6,
      ),
    ).toEqual([]);
  });
  it("invalidates the witnesses if orthogonal snapping leaves their common lane", () => {
    const candidates = spacingCandidates(
      row,
      ["a"],
      size,
      { left: 100, top: 700, right: 180, bottom: 750 },
      "x",
      307,
      -600,
      6,
    );
    expect(candidates).toHaveLength(1);
    expect(candidates[0]!.guidesFor(-600)).not.toBeNull();
    expect(candidates[0]!.guidesFor(-400)).toBeNull();
  });
});
