export type FootnoteEvidence = {
  chunk_id: string;
  sha256: string;
  name: string;
  ordinal: number | null;
  relation: string;
  status: string;
  text: string;
};

export function citationLabel(evidence: FootnoteEvidence) {
  return `${evidence.name}${evidence.ordinal === null ? "" : ` · unit ${evidence.ordinal}`} · ${evidence.relation}`;
}

export function buildEvidenceFootnotes(
  slideId: string,
  size: { width: number; height: number },
  evidence: FootnoteEvidence[],
  labels: string[],
  position: "top" | "bottom",
  color: string,
  startY?: number,
) {
  if (
    !slideId ||
    ![size.width, size.height].every(Number.isSafeInteger) ||
    size.width < 3 * 914400 ||
    size.height < 2 * 914400
  )
    throw new Error(
      "Footnotes require a verified slide at least 3 × 2 inches.",
    );
  if (
    evidence.length < 1 ||
    evidence.length > 4 ||
    labels.length !== evidence.length ||
    new Set(evidence.map((item) => item.chunk_id)).size !== evidence.length
  )
    throw new Error("Choose 1–4 distinct reviewed source excerpts.");
  if (
    evidence.some(
      (item) =>
        item.status !== "current" ||
        !item.chunk_id ||
        !/^[a-f0-9]{64}$/.test(item.sha256) ||
        !["supports", "contradicts", "context"].includes(item.relation),
    )
  )
    throw new Error(
      "The evidence changed or is unavailable. Review the claim again.",
    );
  if (!["top", "bottom"].includes(position) || !/^[A-Fa-f0-9]{6}$/.test(color))
    throw new Error("Choose a valid footnote position and text color.");
  if (
    labels.some(
      (label) =>
        !label.trim() ||
        label.trim().length > 140 ||
        [...label].some((character) => character.charCodeAt(0) < 32),
    )
  )
    throw new Error("Each citation label needs 1–140 characters on one line.");
  const margin = 228600;
  const row = 274320;
  const firstY =
    startY ??
    (position === "top"
      ? margin
      : size.height - margin - row * evidence.length);
  if (
    !Number.isSafeInteger(firstY) ||
    firstY < 0 ||
    firstY + row * evidence.length > size.height
  )
    throw new Error("The citation block must stay inside the slide.");
  return evidence.map((_, index) => ({
    type: "create_text_box",
    params: {
      slide_id: slideId,
      text: `[${index + 1}] ${labels[index]!.trim()}`,
      geometry: {
        x_emu: margin,
        y_emu: firstY + index * row,
        width_emu: size.width - margin * 2,
        height_emu: row,
      },
      text_style: {
        font_size_pt: 10,
        font_color: `#${color.toUpperCase()}`,
        alignment: "left",
      },
    },
  }));
}
