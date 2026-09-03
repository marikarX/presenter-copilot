import { DEFAULT_SHORTCUTS, type ShortcutBindings } from "./shortcut-manager";

export type HudDisplay = {
  id: string;
  workArea: { x: number; y: number; width: number; height: number };
  scaleFactor: number;
  primary: boolean;
};

export type HudSettings = {
  display_id: string | null;
  width: number;
  font_size: number;
  top_offset: number;
  shortcuts: ShortcutBindings;
};

export const DEFAULT_HUD_SETTINGS: HudSettings = {
  display_id: null,
  width: 560,
  font_size: 24,
  top_offset: 32,
  shortcuts: { ...DEFAULT_SHORTCUTS },
};

export function normalizeHudSettings(value: unknown): HudSettings {
  if (!isRecord(value)) return cloneDefaults();
  const settings = cloneDefaults();
  if (value.display_id === null || typeof value.display_id === "string") {
    settings.display_id = value.display_id;
  }
  if (typeof value.width === "number" && Number.isFinite(value.width)) {
    settings.width = clamp(Math.round(value.width), 360, 900);
  }
  if (typeof value.font_size === "number" && Number.isFinite(value.font_size)) {
    settings.font_size = clamp(Math.round(value.font_size), 16, 48);
  }
  if (
    typeof value.top_offset === "number" &&
    Number.isFinite(value.top_offset)
  ) {
    settings.top_offset = clamp(Math.round(value.top_offset), 0, 240);
  }
  if (isRecord(value.shortcuts)) {
    for (const key of Object.keys(DEFAULT_SHORTCUTS) as Array<
      keyof ShortcutBindings
    >) {
      if (typeof value.shortcuts[key] === "string") {
        settings.shortcuts[key] = (value.shortcuts[key] as string).trim();
      }
    }
  }
  return settings;
}

export function calculateHudBounds(
  display: HudDisplay,
  settings: Pick<HudSettings, "width" | "font_size" | "top_offset">,
  expanded = false,
): { x: number; y: number; width: number; height: number } {
  const width = clamp(Math.round(settings.width), 360, 900);
  const height = expanded
    ? 420
    : clamp(Math.round(settings.font_size * 7 + 72), 120, 420);
  const x = Math.round(
    display.workArea.x + (display.workArea.width - width) / 2,
  );
  const y = display.workArea.y + clamp(Math.round(settings.top_offset), 0, 240);
  return {
    x: clamp(
      x,
      display.workArea.x,
      display.workArea.x + display.workArea.width - width,
    ),
    y: clamp(
      y,
      display.workArea.y,
      display.workArea.y + Math.max(0, display.workArea.height - height),
    ),
    width: Math.min(width, display.workArea.width),
    height: Math.min(height, display.workArea.height),
  };
}

function cloneDefaults(): HudSettings {
  return {
    ...DEFAULT_HUD_SETTINGS,
    shortcuts: { ...DEFAULT_SHORTCUTS },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}
