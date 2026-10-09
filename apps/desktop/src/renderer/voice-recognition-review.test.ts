import { describe, expect, it } from "vitest";
import {
  clarifiedVoiceInstruction,
  parseRecognitionReview,
} from "./voice-recognition-review";

const sample = () => ({
  version: 1,
  chunk_count: 2,
  unavailable_count: 1,
  truncated: false,
  chunks: [
    { text: "Do not change the cost.", adapter_score: null },
    { text: "Shorten this title.", adapter_score: 0.2 },
  ],
});
const transcript = "Do not change the cost. Shorten this title.";
describe("original recognition review", () => {
  it("keeps adapter observations without an accuracy threshold", () => {
    expect(parseRecognitionReview(sample(), transcript)).toEqual(sample());
  });
  it.each([
    undefined,
    {},
    { ...sample(), unavailable_count: 0 },
    { ...sample(), truncated: true },
    { ...sample(), chunks: [] },
    { ...sample(), chunk_count: -1 },
    {
      ...sample(),
      chunks: [
        { text: "Do not change the cost.", adapter_score: Number.NaN },
        sample().chunks[1],
      ],
    },
  ])("rejects malformed original review %j", (value) => {
    expect(() => parseRecognitionReview(value, transcript)).toThrow();
  });
  it("rejects quotes that no longer match original transcript", () => {
    expect(() =>
      parseRecognitionReview(sample(), "Change the cost."),
    ).toThrow();
  });
  it("allows bounded previews only when counts and original prefix agree", () => {
    const chunks = Array.from({ length: 64 }, (_, i) => ({
      text: `Phrase ${i}`,
      adapter_score: null,
    }));
    const value = {
      version: 1,
      chunk_count: 65,
      unavailable_count: 65,
      truncated: true,
      chunks,
    };
    expect(
      parseRecognitionReview(
        value,
        chunks.map((c) => c.text).join(" ") + " Phrase 64",
      ),
    ).toEqual(value);
    expect(() =>
      parseRecognitionReview(
        { ...value, unavailable_count: 63 },
        chunks.map((c) => c.text).join(" ") + " Phrase 64",
      ),
    ).toThrow();
  });
  it("accepts honest empty capture instead of manufacturing confidence", () => {
    expect(
      parseRecognitionReview(
        {
          version: 1,
          chunk_count: 0,
          unavailable_count: 0,
          truncated: false,
          chunks: [],
        },
        "",
      ).chunk_count,
    ).toBe(0);
  });
  it("adds only explicit target clarification and still requires an instruction", () => {
    expect(
      clarifiedVoiceInstruction(" Shorten this. ", " The title on slide 2. "),
    ).toBe("Shorten this.\nTarget clarification: The title on slide 2.");
    expect(clarifiedVoiceInstruction(" ", "Any target")).toBe("");
    expect(clarifiedVoiceInstruction("Shorten this.", " ")).toBe(
      "Shorten this.",
    );
  });
});
