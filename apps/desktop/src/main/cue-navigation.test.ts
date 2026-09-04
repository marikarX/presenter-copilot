import { describe, expect, it } from "vitest";

import { nextCueIndex } from "./cue-navigation";

describe("newest-first HUD cue navigation", () => {
  const cues = ["newest", "middle", "oldest"];

  it("moves previous toward older cues and next toward newer cues", () => {
    expect(nextCueIndex(cues, "newest", "previous")).toBe(1);
    expect(nextCueIndex(cues, "middle", "previous")).toBe(2);
    expect(nextCueIndex(cues, "oldest", "next")).toBe(1);
    expect(nextCueIndex(cues, "middle", "next")).toBe(0);
  });

  it("starts at the appropriate end when the HUD has no current cue", () => {
    expect(nextCueIndex(cues, null, "next")).toBe(0);
    expect(nextCueIndex(cues, null, "previous")).toBe(2);
    expect(nextCueIndex([], null, "next")).toBeNull();
  });
});
