import { describe, expect, it } from "vitest";
import { guidedResize } from "./canvas-guides";
import {
  resizeOperations,
  RESIZE_HANDLES,
  type LayoutObject,
} from "./object-layout";

const box = (
  id: string,
  x: number,
  y: number,
  width = 200000,
  height = 100000,
): LayoutObject => ({
  object_id: id,
  name: id,
  geometry_editable: true,
  geometry: { x_emu: x, y_emu: y, width_emu: width, height_emu: height },
});
const size = { width: 1000000, height: 1000000 };
const tolerance = { x: 6000, y: 6000 };
const objects = [box("a", 100000, 100000), box("target", 417000, 700000)];
describe("resize alignment guides", () => {
  it("retains grid and proportional behavior for all eight handles when disabled", () => {
    for (const [handle] of RESIZE_HANDLES)
      for (const proportional of [false, true]) {
        const actual = guidedResize(
          objects,
          ["a"],
          "slide",
          handle,
          112000,
          17000,
          size,
          100000,
          proportional,
        );
        expect(actual.operations).toEqual(
          resizeOperations(
            objects,
            ["a"],
            "slide",
            handle,
            112000,
            17000,
            size,
            100000,
            proportional,
          ),
        );
        expect(actual.guides).toEqual([]);
      }
  });
  it("overrides grid at the moving east edge while retaining the opposite edge", () => {
    const result = guidedResize(
      objects,
      ["a"],
      "slide",
      "e",
      112000,
      0,
      size,
      100000,
      false,
      tolerance,
    );
    expect(result.operations[0]?.params.replacement_geometry).toEqual({
      x_emu: 100000,
      y_emu: 100000,
      width_emu: 317000,
      height_emu: 100000,
    });
    expect(result.guides).toEqual([{ axis: "x", position: 417000 }]);
  });
  it("guides west and north edges while keeping their opposite edges fixed", () => {
    const targets = [
      box("a", 300000, 300000),
      box("ref", 100000, 100000, 117000, 117000),
    ];
    const result = guidedResize(
      targets,
      ["a"],
      "slide",
      "nw",
      -80000,
      -80000,
      size,
      0,
      false,
      tolerance,
    );
    expect(result.operations[0]?.params.replacement_geometry).toEqual({
      x_emu: 217000,
      y_emu: 217000,
      width_emu: 283000,
      height_emu: 183000,
    });
    expect(result.guides).toEqual([
      { axis: "x", position: 217000 },
      { axis: "y", position: 217000 },
    ]);
  });
  it("uses the selection edge and scales all members without moving the opposite anchor", () => {
    const selected = [
      box("a", 100000, 100000, 100000),
      box("b", 250000, 100000, 100000),
      box("ref", 417000, 700000),
    ];
    const result = guidedResize(
      selected,
      ["a", "b"],
      "slide",
      "e",
      64000,
      0,
      size,
      100000,
      false,
      tolerance,
    );
    const a = result.operations[0]!.params.replacement_geometry,
      b = result.operations[1]!.params.replacement_geometry;
    expect(a.x_emu).toBe(100000);
    expect(b.x_emu + b.width_emu).toBe(417000);
    expect(a.width_emu).toBe(b.width_emu);
    expect(a.y_emu).toBe(100000);
  });
  it("keeps Shift proportions when one edge reaches a guide", () => {
    const result = guidedResize(
      objects,
      ["a"],
      "slide",
      "se",
      112000,
      50000,
      size,
      100000,
      true,
      tolerance,
    );
    const g = result.operations[0]!.params.replacement_geometry;
    expect(g.x_emu + g.width_emu).toBe(417000);
    expect(g.width_emu / g.height_emu).toBe(2);
    expect(g.x_emu).toBe(100000);
    expect(g.y_emu).toBe(100000);
    expect(result.guides).toEqual([{ axis: "x", position: 417000 }]);
  });
  it("rejects guides that conflict with minimum size or proportional slide bounds", () => {
    const tiny = [box("a", 100000, 100000), box("ref", 106000, 700000)];
    const small = guidedResize(
      tiny,
      ["a"],
      "slide",
      "e",
      -300000,
      0,
      size,
      0,
      false,
      { x: 10000, y: 10000 },
    );
    expect(small.operations[0]?.params.replacement_geometry.width_emu).toBe(
      12700,
    );
    expect(small.guides).toEqual([]);
    const tall = [
      box("a", 100000, 850000, 200000, 100000),
      box("ref", 417000, 100000),
    ];
    const bounded = guidedResize(
      tall,
      ["a"],
      "slide",
      "se",
      112000,
      50000,
      size,
      0,
      true,
      { x: 20000, y: 6000 },
    );
    const g = bounded.operations[0]!.params.replacement_geometry;
    expect(g.y_emu + g.height_emu).toBe(size.height);
    expect(
      bounded.guides.some(
        (guide) => guide.axis === "x" && guide.position === 417000,
      ),
    ).toBe(false);
    expect(g.width_emu / g.height_emu).toBe(2);
  });
  it("ignores read-only references and validates guide distances and target identity", () => {
    const readonly = [
      objects[0]!,
      { ...objects[1]!, geometry_editable: false },
    ];
    const result = guidedResize(
      readonly,
      ["a"],
      "slide",
      "e",
      112000,
      0,
      size,
      100000,
      false,
      tolerance,
    );
    expect(result.operations[0]?.params.replacement_geometry.width_emu).toBe(
      300000,
    );
    expect(result.guides).toEqual([]);
    expect(() =>
      guidedResize(
        objects,
        ["missing"],
        "slide",
        "e",
        1,
        0,
        size,
        0,
        false,
        tolerance,
      ),
    ).toThrow(/cannot be moved/);
    expect(() =>
      guidedResize(objects, ["a"], "slide", "e", 1, 0, size, 0, false, {
        x: Infinity,
        y: 6,
      }),
    ).toThrow(/finite/);
  });
  it("guides only the axes controlled by an edge handle", () => {
    const result = guidedResize(
      objects,
      ["a"],
      "slide",
      "e",
      112000,
      600000,
      size,
      0,
      false,
      tolerance,
    );
    expect(result.operations[0]?.params.replacement_geometry.y_emu).toBe(
      100000,
    );
    expect(result.guides.every((g) => g.axis === "x")).toBe(true);
  });
});
