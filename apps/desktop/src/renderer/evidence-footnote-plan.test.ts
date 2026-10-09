import { describe, expect, it } from "vitest";
import {
  buildEvidenceFootnotes,
  citationLabel,
  type FootnoteEvidence,
} from "./evidence-footnote-plan";
const evidence: FootnoteEvidence = {
  chunk_id: "chunk",
  sha256: "a".repeat(64),
  name: "Architecture notes.md",
  ordinal: 2,
  relation: "supports",
  status: "current",
  text: "Reviewed excerpt",
};
const size = { width: 12192000, height: 6858000 };
const plan = (
  items = [evidence],
  labels = [citationLabel(evidence)],
  position: "top" | "bottom" = "bottom",
) => buildEvidenceFootnotes("slide", size, items, labels, position, "333333");
describe("reviewed evidence footnote composition", () => {
  it("uses explicit source location and relation without asserting verification", () => {
    expect(citationLabel(evidence)).toBe(
      "Architecture notes.md · unit 2 · supports",
    );
    expect(plan()[0]!.params.text).toBe(
      "[1] Architecture notes.md · unit 2 · supports",
    );
    expect(plan()[0]!.params.geometry.y_emu).toBe(
      size.height - 228600 - 274320,
    );
    expect(plan()[0]!.params.text_style.font_size_pt).toBe(10);
  });
  it("keeps four numbered native text boxes inside the slide in source selection order", () => {
    const items = Array.from({ length: 4 }, (_, i) => ({
      ...evidence,
      chunk_id: `c${i}`,
    }));
    const operations = plan(items, ["One", "Two", "Three", "Four"], "top");
    expect(operations.map((op) => op.params.text)).toEqual([
      "[1] One",
      "[2] Two",
      "[3] Three",
      "[4] Four",
    ]);
    expect(operations[3]!.params.geometry.y_emu).toBe(228600 + 3 * 274320);
  });
  it.each(["changed", "missing"])("rejects %s evidence", (status) => {
    expect(() => plan([{ ...evidence, status }])).toThrow(/evidence changed/);
  });
  it("rejects duplicates, empty selection and mismatched labels", () => {
    expect(() => plan([evidence, evidence], ["A", "B"])).toThrow(/distinct/);
    expect(() => plan([], [])).toThrow(/distinct/);
    expect(() => plan([evidence], [])).toThrow(/distinct/);
  });
  it("rejects oversized or multiline labels and invalid source identity", () => {
    expect(() => plan([evidence], ["x".repeat(141)])).toThrow(/140/);
    expect(() => plan([evidence], ["Source\nOther"])).toThrow(/one line/);
    expect(() => plan([{ ...evidence, sha256: "bad" }])).toThrow(
      /evidence changed/,
    );
  });
  it("rejects unverified or tiny slide dimensions", () => {
    expect(() =>
      buildEvidenceFootnotes(
        "slide",
        { width: 100, height: 100 },
        [evidence],
        ["A"],
        "bottom",
        "333333",
      ),
    ).toThrow(/verified slide/);
  });
  it("accepts reviewed custom placement and rejects an overflowing citation block", () => {
    expect(
      buildEvidenceFootnotes(
        "slide",
        size,
        [evidence],
        ["A"],
        "top",
        "333333",
        1828800,
      )[0]!.params.geometry.y_emu,
    ).toBe(1828800);
    expect(() =>
      buildEvidenceFootnotes(
        "slide",
        size,
        [evidence],
        ["A"],
        "top",
        "333333",
        size.height,
      ),
    ).toThrow(/inside/);
    expect(() =>
      buildEvidenceFootnotes(
        "slide",
        size,
        [evidence],
        ["A"],
        "top",
        "333333",
        NaN,
      ),
    ).toThrow(/inside/);
  });
});
