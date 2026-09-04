import { describe, expect, it } from "vitest";

import {
  calculateHudBounds,
  DEFAULT_HUD_SETTINGS,
  normalizeHudSettings,
} from "./hud-geometry";

describe("HUD geometry", () => {
  const display = {
    id: "display-2",
    workArea: { x: 100, y: 20, width: 1920, height: 1080 },
    scaleFactor: 1.25,
    primary: false,
  };

  it("centers the collapsed HUD at the configured top offset", () => {
    expect(calculateHudBounds(display, DEFAULT_HUD_SETTINGS)).toEqual({
      x: 780,
      y: 52,
      width: 560,
      height: 240,
    });
  });

  it("uses a bounded expanded height and clamps oversized offsets", () => {
    const settings = normalizeHudSettings({
      width: 1200,
      font_size: 80,
      top_offset: 1000,
    });
    expect(settings.width).toBe(900);
    expect(settings.font_size).toBe(48);
    expect(settings.top_offset).toBe(240);
    const bounds = calculateHudBounds(display, settings, true);
    expect(bounds).toEqual({
      x: 610,
      y: 260,
      width: 900,
      height: 420,
    });
  });
});
