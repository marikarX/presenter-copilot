import { describe, expect, it } from "vitest";

import { requiresTranscriptDisclosure } from "./transcript-import-gate";

describe("transcript import disclosure gate", () => {
  it("requires explicit continuation before a transcript picker request", () => {
    expect(requiresTranscriptDisclosure("transcript", false)).toBe(true);
    expect(requiresTranscriptDisclosure("transcript", true)).toBe(false);
  });

  it("does not add a disclosure step to ordinary source imports", () => {
    expect(requiresTranscriptDisclosure("supporting", false)).toBe(false);
    expect(requiresTranscriptDisclosure("presentation", false)).toBe(false);
  });
});
