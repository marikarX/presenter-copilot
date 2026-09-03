import { describe, expect, it } from "vitest";

import type { EventEnvelope } from "../shared/protocol";
import { isStaleAssistEvent, parseCue } from "./HudApp";

describe("HUD cue boundary", () => {
  it("keeps cue content as bounded text and never interprets markup", () => {
    const cue = parseCue(
      {
        cue_id: "cue-1",
        session_id: "session-1",
        state: "final",
        lines: [
          '<img src=x onerror="window.compromised=true">',
          "Second line",
          "Third line",
          "Fourth line must be dropped",
        ],
        evidence: Array.from({ length: 10 }, (_, index) => ({
          evidence_id: `evidence-${index}`,
          label: `Source ${index}`,
          rank: index + 1,
        })),
      },
      null,
    );

    expect(cue?.lines).toEqual([
      '<img src=x onerror="window.compromised=true">',
      "Second line",
      "Third line",
    ]);
    expect(cue?.evidence).toHaveLength(8);
  });

  it("suppresses cue updates from an older assist request", () => {
    const stale = {
      event: "cue.ready",
      payload: { assist_id: "assist-old" },
    } as unknown as EventEnvelope;
    const current = {
      event: "cue.ready",
      payload: { assist_id: "assist-new" },
    } as unknown as EventEnvelope;

    expect(isStaleAssistEvent(stale, "assist-new")).toBe(true);
    expect(isStaleAssistEvent(current, "assist-new")).toBe(false);
    expect(isStaleAssistEvent(stale, null)).toBe(false);
  });
});
