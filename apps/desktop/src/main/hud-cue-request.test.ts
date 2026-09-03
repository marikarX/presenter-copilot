import { describe, expect, it } from "vitest";

import { bindHudCueRequest, validateHudCueRequest } from "./hud-cue-request";

const liveTarget = {
  projectId: "authoritative-project",
  sessionId: "authoritative-session",
} as const;

describe("HUD cue request binding", () => {
  it("derives project and session from the authoritative live target", () => {
    expect(bindHudCueRequest({ cue_id: "cue-1" }, liveTarget)).toEqual({
      project_id: liveTarget.projectId,
      session_id: liveTarget.sessionId,
      cue_id: "cue-1",
    });
  });

  it("rejects renderer-supplied project or session authority", () => {
    expect(() =>
      bindHudCueRequest(
        {
          project_id: "other-project",
          session_id: "other-session",
          cue_id: "cue-1",
        },
        liveTarget,
      ),
    ).toThrow(/only cue_id/i);
    expect(() => bindHudCueRequest({ cue_id: "cue-1" }, null)).toThrow(
      /active Live Assist session/i,
    );
  });

  it("accepts only a bounded cue identifier", () => {
    expect(validateHudCueRequest({ cue_id: "cue-1" })).toEqual({
      cue_id: "cue-1",
    });
    expect(() =>
      validateHudCueRequest({ cue_id: "cue-1", extra: true }),
    ).toThrow();
    expect(() => validateHudCueRequest({ cue_id: "" })).toThrow();
  });
});
