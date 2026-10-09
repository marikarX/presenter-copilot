import { describe, expect, it } from "vitest";
import { layoutComparisonPage } from "./layout-comparison";
const layouts = Array.from({ length: 12 }, (_, index) => ({
  layout_id: `layout-${index}`,
  used_by_slides: index === 5 ? [1] : index === 7 ? [2] : [],
}));
describe("native layout comparison paging", () => {
  it("compares all other layouts in catalog order, including unused and other-slide layouts", () => {
    const result = layoutComparisonPage(layouts, 1, 0);
    expect(result.current.layout_id).toBe("layout-5");
    expect(result.pages).toBe(3);
    expect(result.total).toBe(11);
    expect(
      [0, 1, 2].flatMap((page) =>
        layoutComparisonPage(layouts, 1, page).candidates.map(
          (item) => item.layout_id,
        ),
      ),
    ).toEqual(
      layouts
        .filter((item) => item.layout_id !== "layout-5")
        .map((item) => item.layout_id),
    );
    expect(layoutComparisonPage(layouts, 1, 2).candidates).toHaveLength(3);
  });
  it("allows a single-layout deck with no alternatives", () => {
    expect(layoutComparisonPage([layouts[5]!], 1, 0).candidates).toEqual([]);
  });
  it.each([-1, 3, 0.5])("rejects unavailable page %s", (page) => {
    expect(() => layoutComparisonPage(layouts, 1, page)).toThrow(
      /page|inventory/,
    );
  });
  it("rejects ambiguous current layout and duplicate native identities", () => {
    expect(() => layoutComparisonPage(layouts, 3, 0)).toThrow(/identified/);
    expect(() => layoutComparisonPage([...layouts, layouts[0]!], 1, 0)).toThrow(
      /inventory/,
    );
    expect(() =>
      layoutComparisonPage(
        layouts.map((item) => ({ ...item, used_by_slides: [1] })),
        1,
        0,
      ),
    ).toThrow(/identified/);
  });
});
