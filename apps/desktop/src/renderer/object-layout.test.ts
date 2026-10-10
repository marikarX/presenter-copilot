import { describe, expect, it } from "vitest";
import {
  layoutOperations,
  translationOperations,
  resizeOperations,
  RESIZE_HANDLES,
  type LayoutObject,
  type LayoutAction,
} from "./object-layout";

function object(
  id: string,
  x: number,
  y: number,
  width: number,
  height: number,
): LayoutObject {
  return {
    object_id: id,
    name: id,
    geometry_editable: true,
    geometry: { x_emu: x, y_emu: y, width_emu: width, height_emu: height },
  };
}
const pair = [object("a", 100, 100, 100, 80), object("b", 400, 300, 200, 100)];
function replacements(objects: LayoutObject[], action: LayoutAction) {
  const ops = layoutOperations(
    objects,
    objects.map((o) => o.object_id),
    "slide",
    action,
  );
  return objects.map(
    (o) =>
      ops.find((op) => op.params.object_id === o.object_id)?.params
        .replacement_geometry ?? o.geometry,
  );
}
describe("multi-object native layout", () => {
  it.each([
    ["left", [100, 100], [100, 300]],
    ["center", [300, 250], [100, 300]],
    ["right", [500, 400], [100, 300]],
    ["top", [100, 400], [100, 100]],
    ["middle", [100, 400], [210, 200]],
    ["bottom", [100, 400], [320, 300]],
  ] as const)(
    "aligns unequal objects by %s without resizing",
    (action, xs, ys) => {
      const result = replacements(pair, action);
      expect(result.map((g) => g?.x_emu)).toEqual(xs);
      expect(result.map((g) => g?.y_emu)).toEqual(ys);
      expect(result.map((g) => [g?.width_emu, g?.height_emu])).toEqual([
        [100, 80],
        [200, 100],
      ]);
      expect(pair[1]?.geometry?.x_emu).toBe(400);
    },
  );
  it("distributes unequal widths with fixed outer objects regardless of selection order", () => {
    const objects = [
      object("c", 900, 20, 100, 10),
      object("a", 100, 30, 100, 20),
      object("b", 200, 40, 200, 30),
    ];
    const result = replacements(objects, "horizontal");
    expect(result.map((g) => g?.x_emu)).toEqual([900, 100, 450]);
    expect(result.map((g) => g?.y_emu)).toEqual([20, 30, 40]);
  });
  it("rounds vertical spacing to native integer units and omits unchanged endpoints", () => {
    const objects = [
      object("a", 10, 100, 20, 100),
      object("b", 40, 400, 30, 201),
      object("c", 60, 1000, 40, 50),
    ];
    const ops = layoutOperations(objects, ["a", "b", "c"], "slide", "vertical");
    expect(ops).toHaveLength(1);
    expect(ops[0]?.params.replacement_geometry.y_emu).toBe(500);
    expect(ops[0]?.params.expected_geometry).toEqual(objects[1]?.geometry);
  });
  it("returns no moves for an already aligned selection", () => {
    expect(
      layoutOperations(
        [object("a", 10, 20, 30, 40), object("b", 10, 70, 20, 20)],
        ["a", "b"],
        "slide",
        "left",
      ),
    ).toEqual([]);
  });
  it("rejects unsupported, missing, duplicate, oversized and insufficient selections", () => {
    expect(() => layoutOperations(pair, ["a"], "slide", "left")).toThrow(
      "between 2 and 20",
    );
    expect(() => layoutOperations(pair, ["a", "a"], "slide", "left")).toThrow(
      "only once",
    );
    expect(() =>
      layoutOperations(pair, ["a", "missing"], "slide", "left"),
    ).toThrow("cannot be moved");
    expect(() =>
      layoutOperations(
        [{ ...pair[0]!, geometry_editable: false }, pair[1]!],
        ["a", "b"],
        "slide",
        "left",
      ),
    ).toThrow("cannot be moved");
    expect(() =>
      layoutOperations(
        pair,
        Array.from({ length: 21 }, (_, i) => String(i)),
        "slide",
        "left",
      ),
    ).toThrow("between 2 and 20");
    expect(() =>
      layoutOperations(pair, ["a", "b"], "slide", "horizontal"),
    ).toThrow("at least 3");
  });
  it("rejects distribution when nonoverlapping equal gaps cannot fit", () => {
    expect(() =>
      replacements(
        [
          object("a", 0, 0, 100, 10),
          object("b", 10, 0, 100, 10),
          object("c", 20, 0, 100, 10),
        ],
        "horizontal",
      ),
    ).toThrow("more space");
  });
});

describe("reviewed canvas translations", () => {
  it("moves a selection together without changing dimensions or spacing", () => {
    const ops = translationOperations(pair, ["a", "b"], "slide", 35.6, -20.2, {
      width: 1000,
      height: 800,
    });
    expect(ops.map((op) => op.params.replacement_geometry.x_emu)).toEqual([
      136, 436,
    ]);
    expect(ops.map((op) => op.params.replacement_geometry.y_emu)).toEqual([
      80, 280,
    ]);
    expect(ops.map((op) => op.params.replacement_geometry.width_emu)).toEqual([
      100, 200,
    ]);
    expect(pair[0]?.geometry?.x_emu).toBe(100);
  });
  it("clamps the whole group at either slide edge", () => {
    const ops = translationOperations(pair, ["a", "b"], "slide", 9999, -9999, {
      width: 1000,
      height: 800,
    });
    expect(ops.map((op) => op.params.replacement_geometry.x_emu)).toEqual([
      500, 800,
    ]);
    expect(ops.map((op) => op.params.replacement_geometry.y_emu)).toEqual([
      0, 200,
    ]);
  });
  it("snaps translation increments then clamps, allowing a fractional-grid boundary", () => {
    const ops = translationOperations(
      pair,
      ["a", "b"],
      "slide",
      48,
      59,
      { width: 625, height: 800 },
      20,
    );
    expect(ops[0]?.params.replacement_geometry.x_emu).toBe(125);
    expect(ops[0]?.params.replacement_geometry.y_emu).toBe(160);
  });
  it("supports a single dragged object and omits a zero or boundary move", () => {
    expect(
      translationOperations(pair, ["a"], "slide", 0, 0, {
        width: 1000,
        height: 800,
      }),
    ).toEqual([]);
    expect(
      translationOperations(
        [object("edge", 0, 0, 100, 100)],
        ["edge"],
        "slide",
        -50,
        -50,
        { width: 100, height: 100 },
      ),
    ).toEqual([]);
    expect(
      translationOperations(pair, ["a"], "slide", 20, 30, {
        width: 1000,
        height: 800,
      }),
    ).toHaveLength(1);
  });
  it("rejects stale/read-only selection, oversized selection and nonfinite movement", () => {
    expect(() =>
      translationOperations(pair, ["missing"], "slide", 1, 2, {
        width: 1000,
        height: 800,
      }),
    ).toThrow("cannot be moved");
    expect(() =>
      translationOperations(
        [{ ...pair[0]!, geometry_editable: false }],
        ["a"],
        "slide",
        1,
        2,
        { width: 1000, height: 800 },
      ),
    ).toThrow("cannot be moved");
    // A selection extending past the slide edge is moved fully back onto it.
    const recovered = translationOperations(pair, ["a", "b"], "slide", 1, 2, {
      width: 500,
      height: 800,
    });
    expect(recovered.map((op) => op.params.replacement_geometry.x_emu)).toEqual(
      [0, 300],
    );
    expect(() =>
      translationOperations(pair, ["a", "b"], "slide", 1, 2, {
        width: 400,
        height: 800,
      }),
    ).toThrow("larger than the slide");
    expect(() =>
      translationOperations(pair, ["a"], "slide", Infinity, 2, {
        width: 1000,
        height: 800,
      }),
    ).toThrow("valid selection");
  });
});

describe("canvas resize geometry", () => {
  const size = { width: 10000000, height: 8000000 };
  const original = object("a", 1000000, 1000000, 2000000, 1000000);
  it.each(RESIZE_HANDLES)(
    "keeps the opposite anchor fixed for %s",
    (handle) => {
      const next = resizeOperations(
        [original],
        ["a"],
        "slide",
        handle,
        400000,
        300000,
        size,
      )[0]!.params.replacement_geometry;
      expect(next.x_emu).toBe(handle.includes("w") ? 1400000 : 1000000);
      expect(next.y_emu).toBe(handle.includes("n") ? 1300000 : 1000000);
      expect(next.x_emu + next.width_emu).toBe(
        handle.includes("e") ? 3400000 : 3000000,
      );
      expect(next.y_emu + next.height_emu).toBe(
        handle.includes("s") ? 2300000 : 2000000,
      );
      expect(original.geometry).toEqual({
        x_emu: 1000000,
        y_emu: 1000000,
        width_emu: 2000000,
        height_emu: 1000000,
      });
    },
  );
  it("scales unequal members and gaps together without depending on selection order", () => {
    const pair = [original, object("b", 4000000, 1000000, 1000000, 1000000)];
    const ops = resizeOperations(
      pair,
      ["b", "a"],
      "slide",
      "se",
      4000000,
      1000000,
      size,
    );
    const a = ops.find((o) => o.params.object_id === "a")!.params
      .replacement_geometry;
    const b = ops.find((o) => o.params.object_id === "b")!.params
      .replacement_geometry;
    expect(a).toEqual({
      x_emu: 1000000,
      y_emu: 1000000,
      width_emu: 4000000,
      height_emu: 2000000,
    });
    expect(b).toEqual({
      x_emu: 7000000,
      y_emu: 1000000,
      width_emu: 2000000,
      height_emu: 2000000,
    });
    expect(ops.every((o) => o.params.slide_id === "slide")).toBe(true);
  });
  it("clamps all edges to the slide and retains positive integer members at minimum size", () => {
    const grown = resizeOperations(
      [original],
      ["a"],
      "slide",
      "nw",
      -1e12,
      -1e12,
      size,
    )[0]!.params.replacement_geometry;
    expect(grown).toEqual({
      x_emu: 0,
      y_emu: 0,
      width_emu: 3000000,
      height_emu: 2000000,
    });
    const shrunk = resizeOperations(
      [original],
      ["a"],
      "slide",
      "se",
      -1e12,
      -1e12,
      size,
    )[0]!.params.replacement_geometry;
    expect(shrunk.width_emu).toBe(12700);
    expect(shrunk.height_emu).toBe(12700);
    expect(Object.values(shrunk).every(Number.isSafeInteger)).toBe(true);
  });
  it("snaps resize displacement and locks corner proportions while respecting bounds", () => {
    const snapped = resizeOperations(
      [original],
      ["a"],
      "slide",
      "e",
      149999,
      0,
      size,
      100000,
    )[0]!.params.replacement_geometry;
    expect(snapped.width_emu).toBe(2100000);
    const locked = resizeOperations(
      [original],
      ["a"],
      "slide",
      "se",
      1000000,
      200000,
      size,
      0,
      true,
    )[0]!.params.replacement_geometry;
    expect(locked.width_emu / locked.height_emu).toBe(2);
    const bounded = resizeOperations(
      [original],
      ["a"],
      "slide",
      "se",
      1e12,
      1e12,
      size,
      0,
      true,
    )[0]!.params.replacement_geometry;
    expect(bounded.width_emu / bounded.height_emu).toBe(2);
    expect(bounded.x_emu + bounded.width_emu).toBeLessThanOrEqual(size.width);
    expect(bounded.y_emu + bounded.height_emu).toBeLessThanOrEqual(size.height);
  });
  it("does not stage no-ops, ignored axes or snapped micro-movements", () => {
    expect(
      resizeOperations([original], ["a"], "slide", "e", 0, 300000, size),
    ).toEqual([]);
    expect(
      resizeOperations([original], ["a"], "slide", "se", 3, 4, size, 100000),
    ).toEqual([]);
  });
  it("rejects stale, read-only, duplicate and invalid pointer selections", () => {
    expect(() =>
      resizeOperations([original], ["missing"], "slide", "e", 1, 1, size),
    ).toThrow();
    expect(() =>
      resizeOperations(
        [{ ...original, geometry_editable: false }],
        ["a"],
        "slide",
        "e",
        1,
        1,
        size,
      ),
    ).toThrow();
    expect(() =>
      resizeOperations([original], ["a", "a"], "slide", "e", 1, 1, size),
    ).toThrow();
    expect(() =>
      resizeOperations([original], ["a"], "slide", "e", Infinity, 1, size),
    ).toThrow();
  });
});
