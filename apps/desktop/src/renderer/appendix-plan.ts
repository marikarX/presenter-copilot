export type AppendixSlide = { slide_id: string; ordinal: number };
export type AppendixMode = "move" | "copy";
export const APPENDIX_SELECTION_LIMIT = 18;
const MAX_SLIDES = 5000;

type Operation = { type: string; params: Record<string, unknown> };
export function buildAppendixPlan(
  slides: AppendixSlide[],
  selectedIds: string[],
  mode: AppendixMode,
  title: string,
  notes: string,
  template: string,
) {
  const ids = slides.map((slide) => slide.slide_id);
  if (
    !ids.length ||
    new Set(ids).size !== ids.length ||
    slides.some((slide, i) => slide.ordinal !== i + 1)
  )
    throw new Error(
      "Reload the current slide order before creating an appendix.",
    );
  if (
    !selectedIds.length ||
    selectedIds.length > APPENDIX_SELECTION_LIMIT ||
    new Set(selectedIds).size !== selectedIds.length ||
    selectedIds.some((id) => !ids.includes(id))
  )
    throw new Error(
      "Choose 1–18 distinct detail slides from this presentation.",
    );
  if (mode !== "move" && mode !== "copy")
    throw new Error("Choose move or copy.");
  if (mode === "move" && selectedIds.length === ids.length)
    throw new Error(
      "Keep at least one slide in the main presentation, or copy the detail slides.",
    );
  const selected = slides.filter((slide) =>
    selectedIds.includes(slide.slide_id),
  );
  const main =
    mode === "move"
      ? slides.filter((slide) => !selectedIds.includes(slide.slide_id))
      : slides;
  const total = slides.length + 1 + (mode === "copy" ? selected.length : 0);
  if (total > MAX_SLIDES)
    throw new Error(
      "The appendix would exceed this presentation's slide limit.",
    );
  if (
    !title.trim() ||
    title.trim().length > 120 ||
    notes.length > 4000 ||
    !["classic", "midnight", "paper"].includes(template)
  )
    throw new Error(
      "Use a divider title of 1–120 characters and notes of at most 4000 characters.",
    );
  const last = ids.at(-1)!;
  const operations: Operation[] = [
    {
      type: "create_authored_slide",
      params: {
        slide_id: last,
        layout_source_slide_id: last,
        title: title.trim(),
        bullets: [],
        notes,
        template,
        layout: "statement",
      },
    },
  ];
  if (mode === "copy")
    selected.forEach((slide) =>
      operations.push({
        type: "duplicate_slide",
        params: { slide_id: slide.slide_id },
      }),
    );
  operations.push({
    type: "reorder_slides",
    params: {
      ordered_slide_ids: [
        ...main.map((slide) => slide.slide_id),
        { created_by: 1 },
        ...selected.map((slide, i) =>
          mode === "copy" ? { created_by: i + 2 } : slide.slide_id,
        ),
      ],
    },
  });
  return { operations, selected, main, total, dividerOrdinal: main.length + 1 };
}
