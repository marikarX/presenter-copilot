import { describe, expect, it } from "vitest";
import { guidedTranslation } from "./canvas-guides";
import { translationOperations, type LayoutObject } from "./object-layout";

const box = (
  id: string,
  x: number,
  y: number,
  width = 100,
  height = 100,
): LayoutObject => ({
  object_id: id,
  name: id,
  geometry_editable: true,
  geometry: { x_emu: x, y_emu: y, width_emu: width, height_emu: height },
});
const size = { width: 1000, height: 1000 };
const pair = [box("a", 100, 100), box("b", 317, 700)];
describe("canvas alignment guides", () => {
  it("retains exact existing grid behavior when guides are disabled", () => {
    const actual = guidedTranslation(pair, ["a"], "slide", 212, 17, size, 100);
    expect(actual.operations).toEqual(
      translationOperations(pair, ["a"], "slide", 212, 17, size, 100),
    );
    expect(actual.guides).toEqual([]);
  });
  it("finds an edge near the raw pointer even when the grid rounds away from it", () => {
    const result = guidedTranslation(pair, ["a"], "slide", 212, 17, size, 100, {
      x: 6,
      y: 6,
    });
    expect(result.operations[0]?.params.replacement_geometry).toEqual({
      x_emu: 317,
      y_emu: 100,
      width_emu: 100,
      height_emu: 100,
    });
    expect(result.guides).toEqual([{ axis: "x", position: 317 }]);
  });
  it("uses selection bounds and preserves every member's spacing and dimensions", () => {
    const objects = [
      box("a", 100, 200),
      box("b", 250, 200),
      box("target", 687, 700),
    ];
    const result = guidedTranslation(
      objects,
      ["a", "b"],
      "slide",
      334,
      0,
      size,
      100,
      { x: 6, y: 6 },
    );
    expect(
      result.operations.map((op) => op.params.replacement_geometry.x_emu),
    ).toEqual([437, 587]);
    expect(
      result.operations.map((op) => op.params.replacement_geometry.width_emu),
    ).toEqual([100, 100]);
    expect(result.guides).toEqual([{ axis: "x", position: 687 }]);
  });
  it("snaps to slide centers on both axes", () => {
    const result = guidedTranslation(
      [box("a", 100, 100)],
      ["a"],
      "slide",
      347,
      347,
      size,
      0,
      { x: 6, y: 6 },
    );
    expect(result.operations[0]?.params.replacement_geometry.x_emu).toBe(450);
    expect(result.operations[0]?.params.replacement_geometry.y_emu).toBe(450);
    expect(result.guides).toEqual([
      { axis: "x", position: 500 },
      { axis: "y", position: 500 },
    ]);
  });
  it("scales the independent horizontal and vertical proximity thresholds", () => {
    const objects = [box("a", 100, 100), box("b", 317, 327)];
    const result = guidedTranslation(
      objects,
      ["a"],
      "slide",
      212,
      212,
      size,
      0,
      { x: 6, y: 2 },
    );
    expect(result.operations[0]?.params.replacement_geometry).toMatchObject({
      x_emu: 317,
      y_emu: 312,
    });
    expect(result.guides).toEqual([{ axis: "x", position: 317 }]);
  });
  it("ignores read-only, invalid and off-slide reference geometry", () => {
    for (const target of [
      { ...pair[1]!, geometry_editable: false },
      box("b", 317, 700, -1),
      box("b", 317, 1001),
    ]) {
      const result = guidedTranslation(
        [pair[0]!, target],
        ["a"],
        "slide",
        212,
        17,
        size,
        100,
        { x: 6, y: 6 },
      );
      expect(result.operations[0]?.params.replacement_geometry.x_emu).toBe(300);
      expect(result.guides).toEqual([]);
    }
  });
  it("keeps the whole selection in bounds when an alignment would cross an edge", () => {
    const objects = [box("a", 100, 100, 900), box("b", 150, 700)];
    const result = guidedTranslation(objects, ["a"], "slide", 48, 0, size, 0, {
      x: 60,
      y: 6,
    });
    expect(result.operations).toEqual([]);
    expect(
      result.guides.every((g) => g.axis !== "x" || g.position !== 150),
    ).toBe(true);
  });
  it("rejects stale selections and nonfinite guide thresholds", () => {
    expect(() =>
      guidedTranslation(pair, ["missing"], "slide", 1, 1, size, 0, {
        x: 6,
        y: 6,
      }),
    ).toThrow(/cannot be moved/);
    expect(() =>
      guidedTranslation(pair, ["a"], "slide", 1, 1, size, 0, { x: NaN, y: 6 }),
    ).toThrow(/finite/);
  });
  it("chooses the nearest eligible target and remains stable on ties", () => {
    const objects = [
      box("a", 100, 100),
      box("b", 317, 700),
      box("c", 314, 800),
    ];
    const result = guidedTranslation(
      objects,
      ["a"],
      "slide",
      212,
      17,
      size,
      0,
      { x: 6, y: 6 },
    );
    expect(result.operations[0]?.params.replacement_geometry.x_emu).toBe(314);
    expect(result.guides).toEqual([{ axis: "x", position: 314 }]);
    expect(
      guidedTranslation(objects, ["a"], "slide", 212, 17, size, 0, {
        x: 6,
        y: 6,
      }),
    ).toEqual(result);
  });
});
