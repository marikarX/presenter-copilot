import { describe, expect, it } from "vitest";
import {
  canNavigate,
  needsWalkthrough,
  rememberWalkthrough,
  walkthroughKey,
  projectViews,
} from "./workspace-navigation";

describe("workspace navigation during microphone ownership", () => {
  it("keeps the owning recording controls reachable while blocking other workspaces", () => {
    for (const view of [
      "home",
      "setup",
      ...projectViews.map((item) => item.id),
    ] as const) {
      expect(canNavigate(view, false, false)).toBe(true);
      expect(canNavigate(view, true, false)).toBe(view === "run");
      expect(canNavigate(view, false, true)).toBe(view === "live");
    }
  });
});

describe("local walkthrough preference", () => {
  it("opens for a fresh profile and remembers dismissal across visits", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
    };
    expect(needsWalkthrough(storage)).toBe(true);
    expect(rememberWalkthrough(storage)).toBe(true);
    expect(needsWalkthrough(storage)).toBe(false);
    expect([...values]).toEqual([[walkthroughKey, "seen"]]);
  });
  it("does not break launch when preferences are unavailable or unrecognized", () => {
    expect(needsWalkthrough({ getItem: () => "unexpected" })).toBe(true);
    expect(
      needsWalkthrough({
        getItem: () => {
          throw new Error("disabled");
        },
      }),
    ).toBe(true);
    expect(
      rememberWalkthrough({
        setItem: () => {
          throw new Error("full");
        },
      }),
    ).toBe(false);
  });
});
