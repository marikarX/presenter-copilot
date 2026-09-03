import { describe, expect, it } from "vitest";

import {
  isCoreMethod,
  isProjectSummary,
  isReadyProjectSummary,
  isRendererCoreMethod,
  isUnavailableProjectSummary,
  type ProjectSummary,
} from "./protocol";

describe("renderer core authority", () => {
  it("keeps HUD settings behind Electron's transactional IPC", () => {
    expect(isCoreMethod("hud.settings.get")).toBe(true);
    expect(isCoreMethod("hud.settings.update")).toBe(true);
    expect(isRendererCoreMethod("hud.settings.get")).toBe(false);
    expect(isRendererCoreMethod("hud.settings.update")).toBe(false);
  });
});

describe("ProjectSummary recovery contract", () => {
  it("models a healthy vault with its ready-only fields", () => {
    const project = {
      id: "project-id",
      name: "Healthy vault",
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
      storage_status: "ready",
      privacy_mode: "local_only",
      default_style_policy: "preserve_voice",
      custom_style_guidance: null,
      style_override_enabled: false,
      remote_reasoning_acknowledged_at: null,
      remote_reasoning_acknowledged: false,
      source_count: 0,
    } satisfies ProjectSummary;

    expect(isProjectSummary(project)).toBe(true);
    expect(isReadyProjectSummary(project)).toBe(true);
    expect(isUnavailableProjectSummary(project)).toBe(false);
  });

  it("models an unavailable vault without inventing settings", () => {
    const project = {
      id: "project-id",
      name: "Corrupt vault",
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
      storage_status: "unavailable",
      storage_error_code: "PROJECT_CORRUPT",
    } satisfies ProjectSummary;

    expect(isProjectSummary(project)).toBe(true);
    expect(isReadyProjectSummary(project)).toBe(false);
    expect(isUnavailableProjectSummary(project)).toBe(true);
  });
});
