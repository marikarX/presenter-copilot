import { describe, expect, it } from "vitest";
import { buildAppendixPlan } from "./appendix-plan";

const slides = Array.from({ length: 4 }, (_, i) => ({
  slide_id: `slide-${i + 1}`,
  ordinal: i + 1,
}));
const build = (ids: string[], mode: "move" | "copy" = "move") =>
  buildAppendixPlan(slides, ids, mode, "Appendix", "Divider notes", "classic");
describe("reviewed appendix composition", () => {
  it("moves noncontiguous detail slides in source order and retains the main order", () => {
    const result = build(["slide-4", "slide-2"]);
    expect(result.operations.at(-1)?.params.ordered_slide_ids).toEqual([
      "slide-1",
      "slide-3",
      { created_by: 1 },
      "slide-2",
      "slide-4",
    ]);
    expect(result.dividerOrdinal).toBe(3);
    expect(result.total).toBe(5);
  });
  it("copies retain every original and reference separately created slide identities", () => {
    const result = build(["slide-4", "slide-2"], "copy");
    expect(
      result.operations.slice(1, -1).map((op) => op.params.slide_id),
    ).toEqual(["slide-2", "slide-4"]);
    expect(result.operations.at(-1)?.params.ordered_slide_ids).toEqual([
      "slide-1",
      "slide-2",
      "slide-3",
      "slide-4",
      { created_by: 1 },
      { created_by: 2 },
      { created_by: 3 },
    ]);
    expect(result.total).toBe(7);
  });
  it.each(
    [
      [],
      ["slide-9"],
      ["slide-1", "slide-1"],
      slides.map((slide) => slide.slide_id),
    ].map((ids) => ({ ids })),
  )("rejects invalid move selection $ids", ({ ids }) =>
    expect(() => build(ids)).toThrow(),
  );
  it("accepts copying every slide without emptying the main presentation", () =>
    expect(
      build(
        slides.map((s) => s.slide_id),
        "copy",
      ).main,
    ).toEqual(slides));
  it("bounds a batch to the existing twenty-operation transaction limit", () => {
    const deck = Array.from({ length: 19 }, (_, i) => ({
      slide_id: `s${i}`,
      ordinal: i + 1,
    }));
    expect(
      buildAppendixPlan(
        deck,
        deck.slice(0, 18).map((s) => s.slide_id),
        "copy",
        "Appendix",
        "",
        "paper",
      ).operations,
    ).toHaveLength(20);
    expect(() =>
      buildAppendixPlan(
        deck,
        deck.map((s) => s.slide_id),
        "copy",
        "Appendix",
        "",
        "paper",
      ),
    ).toThrow();
  });
  it("rejects stale/duplicate inventory and capacity overflow", () => {
    expect(() =>
      buildAppendixPlan(
        [...slides].reverse(),
        ["slide-1"],
        "copy",
        "Appendix",
        "",
        "classic",
      ),
    ).toThrow();
    const full = Array.from({ length: 5000 }, (_, i) => ({
      slide_id: `s${i}`,
      ordinal: i + 1,
    }));
    expect(() =>
      buildAppendixPlan(full, ["s1"], "move", "Appendix", "", "classic"),
    ).toThrow();
  });
});
