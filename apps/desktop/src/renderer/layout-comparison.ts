export type LayoutChoice = { layout_id: string; used_by_slides: number[] };
export const LAYOUT_COMPARISON_PAGE_SIZE = 4;

export function layoutComparisonPage<T extends LayoutChoice>(
  items: T[],
  slideNumber: number,
  page: number,
) {
  if (
    !Number.isSafeInteger(slideNumber) ||
    slideNumber < 1 ||
    !Number.isSafeInteger(page) ||
    page < 0 ||
    items.length > 500 ||
    new Set(items.map((item) => item.layout_id)).size !== items.length
  )
    throw new Error("The native layout comparison inventory is invalid.");
  const current = items.filter((item) =>
    item.used_by_slides.includes(slideNumber),
  );
  if (current.length !== 1)
    throw new Error("The current slide layout could not be identified.");
  const candidates = items.filter(
    (item) => item.layout_id !== current[0]!.layout_id,
  );
  const pages = Math.ceil(candidates.length / LAYOUT_COMPARISON_PAGE_SIZE);
  if (page >= Math.max(1, pages))
    throw new Error("This layout comparison page is unavailable.");
  return {
    current: current[0]!,
    pages,
    total: candidates.length,
    candidates: candidates.slice(
      page * LAYOUT_COMPARISON_PAGE_SIZE,
      (page + 1) * LAYOUT_COMPARISON_PAGE_SIZE,
    ),
  };
}
