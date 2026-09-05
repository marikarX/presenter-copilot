import path from "node:path";

import {
  app,
  BrowserWindow,
  dialog,
  globalShortcut,
  ipcMain,
  screen,
} from "electron";
import type { IpcMainInvokeEvent } from "electron";

import { CoreClientError, CoreProcessClient, toCoreError } from "./core-client";
import { invokeResult } from "./invoke-result";
import {
  createSidecarCommand,
  SidecarResolutionError,
} from "./sidecar-command";
import {
  isCoreMetadata,
  isHealthResult,
  isJsonObject,
  isRendererCoreMethod,
  PROTOCOL_VERSION,
  DIAGNOSTIC_SECTIONS,
  type CoreMetadata,
  type DiagnosticSection,
  type RendererCoreMethod,
  type CoreStatus,
  type EventEnvelope,
  type HealthResult,
  type HudDisplay,
  type HudSettings,
  type HudStatus,
  type JsonObject,
} from "../shared/protocol";
import {
  isTrustedHudSender,
  isTrustedRendererSender,
  selectRendererLoadTarget,
  type HudValidationOptions,
  type RendererValidationOptions,
} from "./sender-validation";
import {
  calculateHudBounds,
  DEFAULT_HUD_SETTINGS,
  normalizeHudSettings,
} from "./hud-geometry";
import {
  GlobalShortcutRegistry,
  type ShortcutBinding,
} from "./shortcut-manager";
import { nextCueIndex } from "./cue-navigation";
import { bindHudCueRequest, type HudLiveTarget } from "./hud-cue-request";
import {
  AutomaticRestartController,
  DEFAULT_AUTOMATIC_RESTART_DELAYS_MS,
  DEFAULT_AUTOMATIC_RESTART_MAX_ATTEMPTS,
} from "./restart-controller";

let mainWindow: BrowserWindow | null = null;
let hudWindow: BrowserWindow | null = null;
let coreClient: CoreProcessClient | null = null;
let isQuitting = false;
const PACKAGED_SMOKE_ARGUMENT = "--presenter-copilot-smoke";

export const MANUAL_PREVIOUS_SHORTCUT = "Ctrl+Alt+PageUp";
export const MANUAL_NEXT_SHORTCUT = "Ctrl+Alt+PageDown";

type ManualRunTarget = { projectId: string; sessionId: string };
type LiveTarget = HudLiveTarget;

let manualRunTarget: ManualRunTarget | null = null;
let liveTarget: LiveTarget | null = null;
let liveShortcutsRegistered = false;
let hudExpanded = false;
let hudSettings: HudSettings = normalizeHudSettings(DEFAULT_HUD_SETTINGS);
let hudCoreState: CoreStatus["state"] = "stopped";
let hudCaptureProtection: HudStatus["capture_protection"] = "unsupported";
let hudCaptureProtectionMessage =
  "Capture protection status is not available yet.";
let currentHudCueId: string | null = null;
let currentHudAssistId: string | null = null;
const ignoredHudAssistIds = new Set<string>();
let hudCueOrder: string[] = [];
let hudRegistry: GlobalShortcutRegistry | null = null;
let currentHudPolicy: HudValidationOptions | null = null;

const HUD_EVENT_NAMES = new Set([
  "session.started",
  "session.stopped",
  "asr.partial",
  "assist.started",
  "assist.retrieval_ready",
  "assist.reasoning_started",
  "cue.partial",
  "cue.ready",
  "cue.error",
]);

function createWindow(
  rendererPolicy: RendererValidationOptions,
): BrowserWindow {
  const window = new BrowserWindow({
    width: 1200,
    height: 820,
    minWidth: 720,
    minHeight: 520,
    show: false,
    backgroundColor: "#f6f7fa",
    webPreferences: {
      preload: path.join(__dirname, "../preload/preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event) => event.preventDefault());
  window.once("ready-to-show", () => window.show());
  window.on("closed", () => {
    disableManualRunShortcuts();
    if (mainWindow === window) {
      mainWindow = null;
      // The HUD is intentionally hidden and non-closable, so it prevents
      // Electron's window-all-closed event from representing app shutdown.
      if (!isQuitting) app.quit();
    }
  });

  const rendererTarget = selectRendererLoadTarget({
    bundledRendererPath: rendererPolicy.bundledRendererPath,
    developmentUrl: process.env.PRESENTER_COPILOT_DEV_SERVER_URL,
    isPackaged: app.isPackaged,
    isDevelopment: rendererPolicy.allowDevelopmentRenderer,
  });
  if (rendererTarget.type === "development") {
    void window.loadURL(rendererTarget.url);
  } else {
    void window.loadFile(rendererTarget.path);
  }
  return window;
}

function allHudDisplays(): HudDisplay[] {
  const primaryId = String(screen.getPrimaryDisplay().id);
  return screen.getAllDisplays().map((display) => ({
    id: String(display.id),
    workArea: {
      x: display.workArea.x,
      y: display.workArea.y,
      width: display.workArea.width,
      height: display.workArea.height,
    },
    scaleFactor: display.scaleFactor,
    primary: String(display.id) === primaryId,
  }));
}

function selectedHudDisplay(): HudDisplay {
  const displays = allHudDisplays();
  return (
    displays.find((display) => display.id === hudSettings.display_id) ??
    displays.find((display) => display.primary) ??
    displays[0] ?? {
      id: "primary",
      workArea: { x: 0, y: 0, width: 1280, height: 720 },
      scaleFactor: 1,
      primary: true,
    }
  );
}

function currentHudStatus(): HudStatus {
  const visible = Boolean(
    hudWindow && !hudWindow.isDestroyed() && hudWindow.isVisible(),
  );
  return {
    visible,
    expanded: hudExpanded,
    core_state: hudCoreState,
    font_size: hudSettings.font_size,
    capture_protection: hudCaptureProtection,
    capture_protection_message: hudCaptureProtectionMessage,
    shortcuts_registered: liveShortcutsRegistered,
  };
}

function sendHudStatus(): void {
  if (!hudWindow || hudWindow.isDestroyed()) return;
  hudWindow.webContents.send("hud:status", currentHudStatus());
}

function repositionHud(): void {
  if (!hudWindow || hudWindow.isDestroyed()) return;
  const bounds = calculateHudBounds(
    selectedHudDisplay(),
    hudSettings,
    hudExpanded,
  );
  hudWindow.setBounds(bounds, false);
}

function setHudExpanded(expanded: boolean): void {
  hudExpanded = expanded;
  if (hudWindow && !hudWindow.isDestroyed()) {
    hudWindow.setFocusable(expanded);
    hudWindow.setIgnoreMouseEvents(!expanded, { forward: true });
    if (expanded) hudWindow.show();
    repositionHud();
  }
  sendHudStatus();
}

function createHudWindow(policy: HudValidationOptions): BrowserWindow {
  const display = selectedHudDisplay();
  const bounds = calculateHudBounds(display, hudSettings, false);
  const window = new BrowserWindow({
    ...bounds,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    closable: false,
    focusable: false,
    skipTaskbar: true,
    hasShadow: false,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, "../preload/hud-preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });
  window.setAlwaysOnTop(true, "floating");
  window.setIgnoreMouseEvents(true, { forward: true });
  try {
    if (typeof window.setContentProtection !== "function") {
      hudCaptureProtection = "unsupported";
      hudCaptureProtectionMessage =
        "This platform does not expose content-protection support.";
    } else {
      window.setContentProtection(true);
      hudCaptureProtection = "enabled";
      hudCaptureProtectionMessage =
        "Capture protection API enabled; external capture exclusion was not independently verified on this validation environment.";
    }
  } catch {
    hudCaptureProtection = "error";
    hudCaptureProtectionMessage =
      "Capture protection could not be enabled on this platform.";
  }
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event) => event.preventDefault());
  window.on("closed", () => {
    if (hudWindow === window) hudWindow = null;
  });
  const development =
    !app.isPackaged && policy.allowDevelopmentHud
      ? "http://127.0.0.1:5173/hud/index.html"
      : null;
  if (development) void window.loadURL(development);
  else void window.loadFile(policy.bundledHudPath);
  return window;
}

function ensureHudWindow(): BrowserWindow | null {
  if (hudWindow && !hudWindow.isDestroyed()) return hudWindow;
  if (!currentHudPolicy) return null;
  hudWindow = createHudWindow(currentHudPolicy);
  return hudWindow;
}

function showHud(): void {
  const window = ensureHudWindow();
  if (!window || window.isDestroyed()) return;
  repositionHud();
  window.showInactive();
  sendHudStatus();
}

function hideHud(): void {
  if (!hudWindow || hudWindow.isDestroyed()) return;
  hudWindow.hide();
  sendHudStatus();
}

function sendStatus(status: CoreStatus): void {
  hudCoreState = status.state;
  sendHudStatus();
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("core:status", status);
}

function sendEvent(event: EventEnvelope): void {
  if (
    event.event === "presentation.status_changed" &&
    event.payload.mode === "powerpoint"
  ) {
    disableManualRunShortcuts();
  }
  if (
    event.event === "session.stopped" &&
    manualRunTarget &&
    event.payload.id === manualRunTarget.sessionId
  ) {
    disableManualRunShortcuts();
  }
  if (
    event.event === "session.started" &&
    event.payload.mode === "live_assist"
  ) {
    const projectId = event.payload.project_id;
    const sessionId = event.payload.id;
    if (typeof projectId === "string" && typeof sessionId === "string") {
      liveTarget = { projectId, sessionId };
      currentHudAssistId = null;
      ensureHudWindow();
      showHud();
      enableLiveShortcuts(liveTarget);
    }
  }
  if (
    event.event === "session.stopped" &&
    liveTarget &&
    event.payload.id === liveTarget.sessionId
  ) {
    disableLiveShortcuts();
    hideHud();
    currentHudCueId = null;
    currentHudAssistId = null;
    hudCueOrder = [];
  }
  if (event.event === "assist.started") {
    const assistId = event.payload.assist_id;
    if (typeof assistId === "string") currentHudAssistId = assistId;
  }
  if (
    event.event === "cue.ready" ||
    event.event === "cue.partial" ||
    event.event === "cue.error"
  ) {
    const assistId = event.payload.assist_id;
    if (typeof assistId !== "string") return;
    if (ignoredHudAssistIds.has(assistId)) return;
    if (currentHudAssistId !== null && assistId !== currentHudAssistId) {
      return;
    }
    const cueId = event.payload.cue_id;
    if (typeof cueId === "string") {
      currentHudCueId = cueId;
      if (!hudCueOrder.includes(cueId)) hudCueOrder.push(cueId);
    }
  }
  if (hudWindow && !hudWindow.isDestroyed()) {
    const hudEvent = eventForHud(event);
    if (hudEvent) hudWindow.webContents.send("hud:event", hudEvent);
  }
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("core:event", event);
}

function eventForHud(event: EventEnvelope): EventEnvelope | null {
  if (!HUD_EVENT_NAMES.has(event.event)) return null;
  if (
    (event.event === "session.started" || event.event === "session.stopped") &&
    event.payload.mode !== "live_assist"
  ) {
    return null;
  }
  if (event.event !== "asr.partial") return event;
  // The HUD only needs the listening transition. Keep audience speech out of
  // the HUD renderer's event channel even though the main renderer receives
  // the full core event for the existing transcript UI.
  const payload: JsonObject = {};
  for (const key of ["project_id", "session_id"] as const) {
    if (typeof event.payload[key] === "string")
      payload[key] = event.payload[key];
  }
  return { ...event, payload };
}

function requireClient(): CoreProcessClient {
  if (!coreClient) throw new Error("Core client is not initialized.");
  return coreClient;
}

function validateRendererRequest(value: unknown): {
  method: RendererCoreMethod;
  params: JsonObject;
} {
  if (!isJsonObject(value) || !isRendererCoreMethod(value.method)) {
    throw new Error(
      "Only explicitly renderer-allowlisted core methods may be invoked.",
    );
  }
  if (value.params !== undefined && !isJsonObject(value.params)) {
    throw new Error("Core request params must be a JSON object.");
  }
  return { method: value.method, params: value.params ?? {} };
}

function validateImportPickerRequest(value: unknown): {
  projectId: string;
  kind: "presentation" | "supporting" | "transcript";
} {
  if (!isJsonObject(value) || typeof value.project_id !== "string") {
    throw new Error("A project id is required to import a source.");
  }
  const kind = value.kind ?? "supporting";
  if (
    kind !== "presentation" &&
    kind !== "supporting" &&
    kind !== "transcript"
  ) {
    throw new Error("Source kind is invalid.");
  }
  return { projectId: value.project_id, kind };
}

function validateManualShortcutRequest(value: unknown): ManualRunTarget {
  if (!isJsonObject(value)) throw new Error("A Run target is required.");
  const projectId = value.project_id;
  const sessionId = value.session_id;
  if (
    typeof projectId !== "string" ||
    typeof sessionId !== "string" ||
    projectId.length === 0 ||
    sessionId.length === 0 ||
    projectId.length > 80 ||
    sessionId.length > 80
  ) {
    throw new Error("The Run target is invalid.");
  }
  return { projectId, sessionId };
}

function requestTrackedSlide(
  method: "presentation.previous_slide" | "presentation.next_slide",
): void {
  const target = manualRunTarget;
  if (!target || !coreClient) return;
  void coreClient
    .request(method, {
      project_id: target.projectId,
      session_id: target.sessionId,
    })
    .catch((error) => {
      const safe = toCoreError(error);
      console.error(`[run:shortcut:${safe.code}] ${safe.message}`);
    });
}

function requestLiveCore(
  method:
    | "assist.request"
    | "assist.cancel"
    | "presentation.previous_slide"
    | "presentation.next_slide"
    | "cue.dismiss"
    | "cue.list",
  params: JsonObject,
): void {
  if (!liveTarget || !coreClient) return;
  void coreClient.request(method, params).catch((error) => {
    const safe = toCoreError(error);
    console.error(`[live:shortcut:${safe.code}] ${safe.message}`);
  });
}

function requestLiveAssist(): void {
  requestLiveAssistWithTrigger("hotkey");
}

function requestLiveAssistWithTrigger(
  trigger: "hotkey" | "button" | "typed",
  question?: string,
): void {
  const target = liveTarget;
  if (!target) return;
  requestLiveCore("assist.request", {
    project_id: target.projectId,
    session_id: target.sessionId,
    trigger,
    ...(question ? { question } : {}),
  });
}

function requestLiveSlide(
  method: "presentation.previous_slide" | "presentation.next_slide",
): void {
  if (!liveTarget) return;
  requestLiveCore(method, {
    project_id: liveTarget.projectId,
    session_id: liveTarget.sessionId,
  });
}

function navigateHudCue(direction: "previous" | "next"): void {
  const target = liveTarget;
  if (!target || !coreClient) return;
  void coreClient
    .request("cue.list", {
      project_id: target.projectId,
      session_id: target.sessionId,
      limit: 50,
    })
    .then((result: unknown) => {
      if (!isJsonObject(result) || !Array.isArray(result.cues)) return;
      const cues = result.cues.filter(
        (cue): cue is JsonObject & { id: string } =>
          isJsonObject(cue) && typeof cue.id === "string",
      );
      if (cues.length === 0) return;
      const nextIndex = nextCueIndex(
        cues.map((cue) => cue.id),
        currentHudCueId,
        direction,
      );
      if (nextIndex === null) return;
      const cue = cues[nextIndex];
      if (!cue) return;
      currentHudCueId = typeof cue.id === "string" ? cue.id : currentHudCueId;
      if (currentHudCueId && !hudCueOrder.includes(currentHudCueId))
        hudCueOrder.push(currentHudCueId);
      if (hudWindow && !hudWindow.isDestroyed())
        hudWindow.webContents.send("hud:cue", cue);
    })
    .catch((error) => {
      const safe = toCoreError(error);
      console.error(`[live:cue-navigation:${safe.code}] ${safe.message}`);
    });
}

function clearHudCue(): void {
  const assistId = suppressCurrentHudAssist();
  if (assistId && liveTarget) {
    requestLiveCore("assist.cancel", {
      project_id: liveTarget.projectId,
      session_id: liveTarget.sessionId,
      assist_id: assistId,
    });
  }
  if (currentHudCueId && liveTarget) {
    requestLiveCore("cue.dismiss", {
      project_id: liveTarget.projectId,
      session_id: liveTarget.sessionId,
      cue_id: currentHudCueId,
    });
  }
  currentHudCueId = null;
  if (hudWindow && !hudWindow.isDestroyed())
    hudWindow.webContents.send("hud:clear");
}

function suppressCurrentHudAssist(): string | null {
  const assistId = currentHudAssistId;
  if (!assistId) return null;
  ignoredHudAssistIds.add(assistId);
  while (ignoredHudAssistIds.size > 32) {
    const oldest = ignoredHudAssistIds.values().next().value;
    if (typeof oldest !== "string") break;
    ignoredHudAssistIds.delete(oldest);
  }
  currentHudAssistId = null;
  return assistId;
}

function shortcutBindingsForRun(): ShortcutBinding[] {
  return [
    {
      accelerator: hudSettings.shortcuts.previous_slide,
      action: () => requestTrackedSlide("presentation.previous_slide"),
    },
    {
      accelerator: hudSettings.shortcuts.next_slide,
      action: () => requestTrackedSlide("presentation.next_slide"),
    },
  ];
}

function shortcutBindingsForLive(): ShortcutBinding[] {
  const shortcuts = hudSettings.shortcuts;
  return [
    { accelerator: shortcuts.push_to_assist, action: requestLiveAssist },
    {
      accelerator: shortcuts.show_hide,
      action: () => (hudWindow?.isVisible() ? hideHud() : showHud()),
    },
    {
      accelerator: shortcuts.expand_collapse,
      action: () => setHudExpanded(!hudExpanded),
    },
    {
      accelerator: shortcuts.previous_cue,
      action: () => navigateHudCue("previous"),
    },
    { accelerator: shortcuts.next_cue, action: () => navigateHudCue("next") },
    { accelerator: shortcuts.clear, action: clearHudCue },
    {
      accelerator: shortcuts.previous_slide,
      action: () => requestLiveSlide("presentation.previous_slide"),
    },
    {
      accelerator: shortcuts.next_slide,
      action: () => requestLiveSlide("presentation.next_slide"),
    },
  ];
}

function enableLiveShortcuts(target: LiveTarget): {
  registered: boolean;
  error_code?: string;
} {
  liveTarget = target;
  const result = hudRegistry?.activate("live", shortcutBindingsForLive()) ?? {
    registered: false,
    error_code: "SHORTCUT_REGISTRATION_FAILED",
  };
  liveShortcutsRegistered =
    hudRegistry?.isOwnerRegistered("live") ?? result.registered;
  sendHudStatus();
  return result;
}

function disableLiveShortcuts(): void {
  liveTarget = null;
  hudRegistry?.deactivate("live");
  liveShortcutsRegistered = false;
  sendHudStatus();
}

function retainHudEmergencyShortcut(): void {
  hudRegistry?.activate("live", [
    {
      accelerator: hudSettings.shortcuts.show_hide,
      action: () => (hudWindow?.isVisible() ? hideHud() : showHud()),
    },
  ]);
  // The complete Live set is unavailable, but this direct Electron action
  // keeps the HUD hideable without a core request.
  liveShortcutsRegistered = false;
  sendHudStatus();
}

function clearInterruptedLiveState(): void {
  disableLiveShortcuts();
  currentHudCueId = null;
  currentHudAssistId = null;
  hudCueOrder = [];
  ignoredHudAssistIds.clear();
  if (hudWindow && !hudWindow.isDestroyed())
    hudWindow.webContents.send("hud:clear");
  retainHudEmergencyShortcut();
}

export function disableManualRunShortcuts(): void {
  const result = hudRegistry?.deactivate("run");
  manualRunTarget = null;
  if (liveTarget && result?.registered === false)
    liveShortcutsRegistered = false;
}

export function enableManualRunShortcuts(target: ManualRunTarget): {
  registered: boolean;
  previous_shortcut: string;
  next_shortcut: string;
  error_code?: string;
} {
  const previousTarget = manualRunTarget;
  manualRunTarget = target;
  const result = hudRegistry?.activate("run", shortcutBindingsForRun()) ?? {
    registered: false,
    error_code: "SHORTCUT_REGISTRATION_FAILED",
  };
  if (!result.registered) manualRunTarget = previousTarget;
  return {
    registered: result.registered,
    previous_shortcut: hudSettings.shortcuts.previous_slide,
    next_shortcut: hudSettings.shortcuts.next_slide,
    ...(result.error_code ? { error_code: result.error_code } : {}),
  };
}

async function bootstrapCore(): Promise<boolean> {
  const client = requireClient();
  try {
    const readyMetadata = await client.start();
    const hello = await client.request<CoreMetadata>("core.hello");
    if (
      !isCoreMetadata(hello) ||
      hello.protocol_version !== PROTOCOL_VERSION ||
      hello.core_version !== readyMetadata.core_version
    ) {
      throw new Error("Core handshake metadata did not match the ready event.");
    }

    const health = await client.request<HealthResult>("core.health");
    if (!isHealthResult(health))
      throw new Error("Core health response was invalid.");
    client.recordHealth(health);
    return true;
  } catch (error) {
    client.markUnavailable(error);
    // A failed handshake may have already asked CoreProcessClient to kill the
    // child. Wait for its close finalizer before another restart attempt; this
    // preserves the one-child/no-race lifecycle invariant when termination is
    // delayed by the OS.
    await client.shutdown().catch(() => undefined);
    return false;
  }
}

const automaticRestartController = new AutomaticRestartController({
  restart: bootstrapCore,
  isQuitting: () => isQuitting,
  maxAttempts: DEFAULT_AUTOMATIC_RESTART_MAX_ATTEMPTS,
  delaysMs: DEFAULT_AUTOMATIC_RESTART_DELAYS_MS,
  onExhausted: () => {
    clearInterruptedLiveState();
  },
});

function validateDiagnosticSections(
  value: unknown,
): DiagnosticSection[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || value.length > 6)
    throw new Error("Diagnostic sections must be a bounded list.");
  const allowed = new Set<string>(DIAGNOSTIC_SECTIONS);
  const sections: DiagnosticSection[] = [];
  for (const section of value) {
    if (
      typeof section !== "string" ||
      !allowed.has(section) ||
      sections.includes(section as DiagnosticSection)
    ) {
      throw new Error("Diagnostic sections contain an unsupported value.");
    }
    sections.push(section as DiagnosticSection);
  }
  return sections;
}

async function runPackagedSmoke(): Promise<void> {
  const client = requireClient();
  try {
    const project = await client.request<{ project: { id: string } }>(
      "project.create",
      { name: "Packaged smoke disposable project" },
    );
    await client.request("project.delete", {
      project_id: project.project.id,
    });
    await client.shutdown();
    isQuitting = true;
    app.exit(0);
  } catch (error) {
    const safe = toCoreError(error, "PACKAGED_SMOKE_FAILED", false);
    console.error(`[packaged-smoke:${safe.code}] ${safe.message}`);
    isQuitting = true;
    await client.shutdown().catch(() => undefined);
    app.exit(1);
  }
}

function assertTrustedRendererSender(
  event: IpcMainInvokeEvent,
  rendererPolicy: RendererValidationOptions,
): void {
  if (
    !isTrustedRendererSender(
      event.senderFrame,
      event.sender.mainFrame,
      rendererPolicy,
    )
  ) {
    throw new Error("IPC request rejected from an untrusted renderer frame.");
  }
}

function assertTrustedHudFrame(
  event: IpcMainInvokeEvent,
  hudPolicy: HudValidationOptions,
): void {
  if (
    !isTrustedHudSender(event.senderFrame, event.sender.mainFrame, hudPolicy)
  ) {
    throw new Error(
      "HUD IPC request rejected from an untrusted renderer frame.",
    );
  }
}

function validateHudSettingsUpdate(value: unknown): JsonObject {
  if (!isJsonObject(value)) throw new Error("HUD settings must be an object.");
  const result: JsonObject = {};
  if ("display_id" in value) {
    if (value.display_id !== null && typeof value.display_id !== "string") {
      throw new Error("HUD display_id must be a string or null.");
    }
    result.display_id = value.display_id;
  }
  for (const key of ["width", "font_size", "top_offset"] as const) {
    if (key in value) {
      if (typeof value[key] !== "number" || !Number.isFinite(value[key])) {
        throw new Error(`HUD ${key} must be a finite number.`);
      }
      result[key] = value[key];
    }
  }
  if ("shortcuts" in value) {
    if (!isJsonObject(value.shortcuts)) {
      throw new Error("HUD shortcuts must be an object.");
    }
    const shortcuts: JsonObject = {};
    for (const key of [
      "push_to_assist",
      "show_hide",
      "expand_collapse",
      "previous_cue",
      "next_cue",
      "clear",
      "previous_slide",
      "next_slide",
    ] as const) {
      if (key in value.shortcuts) {
        if (typeof value.shortcuts[key] !== "string") {
          throw new Error(`HUD shortcut ${key} must be a string.`);
        }
        shortcuts[key] = value.shortcuts[key];
      }
    }
    result.shortcuts = shortcuts;
  }
  return result;
}

function mergedHudSettings(
  current: HudSettings,
  update: JsonObject,
): HudSettings {
  const shortcuts = isJsonObject(update.shortcuts) ? update.shortcuts : {};
  return normalizeHudSettings({
    ...current,
    ...update,
    shortcuts: { ...current.shortcuts, ...shortcuts },
  });
}

function restoreHudSettings(settings: HudSettings): void {
  hudSettings = settings;
  repositionHud();
  if (liveTarget) {
    if (hudCoreState === "unavailable") retainHudEmergencyShortcut();
    else enableLiveShortcuts(liveTarget);
  }
  if (manualRunTarget) enableManualRunShortcuts(manualRunTarget);
}

function hydrateHudCue(): void {
  const target = liveTarget;
  if (!target || !coreClient) return;
  void coreClient
    .request("cue.list", {
      project_id: target.projectId,
      session_id: target.sessionId,
      limit: 50,
    })
    .then((result: unknown) => {
      if (!isJsonObject(result) || !Array.isArray(result.cues)) return;
      const cues = result.cues.filter(isJsonObject);
      const last = cues[0];
      if (!last) return;
      if (typeof last.id === "string") {
        currentHudCueId = last.id;
        currentHudAssistId =
          typeof last.assist_id === "string" ? last.assist_id : null;
        hudCueOrder = cues
          .map((cue) => (typeof cue.id === "string" ? cue.id : null))
          .filter((id): id is string => id !== null)
          .reverse();
      }
      if (hudWindow && !hudWindow.isDestroyed())
        hudWindow.webContents.send("hud:cue", last);
    })
    .catch(() => undefined);
}

function registerIpc(
  rendererPolicy: RendererValidationOptions,
  hudPolicy: HudValidationOptions,
): void {
  ipcMain.handle("core:get-status", (event) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(() => requireClient().getStatus());
  });
  ipcMain.handle("core:request", async (event, value: unknown) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(async () => {
      const request = validateRendererRequest(value);
      const runCleanupMethods = new Set([
        "asr.stop",
        "teach.voice_stop",
        "teach.voice_cancel",
        "session.stop",
        "session.delete",
        "project.delete",
      ]);
      const timeoutMs =
        request.method === "source.reindex"
          ? 60_000
          : request.method === "retrieval.rebuild"
            ? 10 * 60_000
            : request.method === "asr.prepare_model"
              ? 15 * 60_000
              : request.method === "asr.start" ||
                  request.method === "teach.voice_start" ||
                  request.method === "run.generate_debrief"
                ? 60_000
                : runCleanupMethods.has(request.method)
                  ? 60_000
                  : request.method === "teach.next_prompt" ||
                      request.method === "teach.submit_text" ||
                      request.method === "challenge.next_question" ||
                      request.method === "challenge.submit_answer" ||
                      request.method === "provider.test"
                    ? 30_000
                    : undefined;
      return timeoutMs === undefined
        ? requireClient().request(request.method, request.params)
        : requireClient().request(request.method, request.params, timeoutMs);
    });
  });
  ipcMain.handle("source:pick-and-import", async (event, value: unknown) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(async () => {
      const request = validateImportPickerRequest(value);
      const extensions =
        request.kind === "transcript"
          ? ["vtt", "srt", "txt", "json"]
          : ["pdf", "pptx", "txt", "md", "markdown"];
      const selection = await dialog.showOpenDialog({
        title:
          request.kind === "transcript"
            ? "Import authorized transcript"
            : "Import presentation source",
        properties: ["openFile"],
        filters: [
          {
            name: "Supported sources",
            extensions,
          },
        ],
      });
      if (selection.canceled || selection.filePaths.length === 0)
        return { cancelled: true };

      // The selected absolute path is intentionally consumed in main and is
      // never returned to the renderer or placed in an event payload.
      return requireClient().request(
        "source.import",
        {
          project_id: request.projectId,
          kind: request.kind,
          path: selection.filePaths[0],
        },
        60_000,
      );
    });
  });
  ipcMain.handle("diagnostics:preview", async (event, value: unknown) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(() => {
      const sections = validateDiagnosticSections(value);
      return requireClient().request("diagnostics.preview", {
        ...(sections ? { sections } : {}),
      });
    });
  });
  ipcMain.handle("diagnostics:save", async (event, value: unknown) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(async () => {
      const sections = validateDiagnosticSections(value);
      const selection = await dialog.showSaveDialog({
        title: "Export Presenter Copilot diagnostics",
        defaultPath: "presenter-copilot-diagnostics.zip",
        properties: ["createDirectory", "showOverwriteConfirmation"],
        filters: [{ name: "Diagnostic ZIP", extensions: ["zip"] }],
      });
      if (selection.canceled || !selection.filePath)
        return { cancelled: true as const };
      return requireClient().request("diagnostics.export", {
        output_path: selection.filePath,
        ...(sections ? { sections } : {}),
      });
    });
  });
  ipcMain.handle("run:enable-manual-shortcuts", (event, value: unknown) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(() =>
      enableManualRunShortcuts(validateManualShortcutRequest(value)),
    );
  });
  ipcMain.handle("run:disable-manual-shortcuts", (event) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(() => {
      disableManualRunShortcuts();
      return { disabled: true as const };
    });
  });
  ipcMain.handle("hud:get-settings", (event) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(async () => {
      const result = await requireClient().request<{ settings: HudSettings }>(
        "hud.settings.get",
      );
      hudSettings = normalizeHudSettings(result.settings);
      repositionHud();
      return hudSettings;
    });
  });
  ipcMain.handle("hud:get-status", (event) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(() => currentHudStatus());
  });
  ipcMain.handle("hud:update-settings", (event, value: unknown) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(async () => {
      const previous = hudSettings;
      const update = validateHudSettingsUpdate(value);
      const hasShortcutUpdate = Object.prototype.hasOwnProperty.call(
        update,
        "shortcuts",
      );
      const next = mergedHudSettings(previous, update);

      // OS registration is part of the settings transaction. Preflight the
      // candidate set before persisting it so a conflict cannot leave the
      // app metadata pointing at an unusable shortcut mapping.
      if (hasShortcutUpdate) {
        hudSettings = next;
        const liveResult =
          liveTarget && hudCoreState !== "unavailable"
            ? enableLiveShortcuts(liveTarget)
            : { registered: true };
        const runResult = manualRunTarget
          ? enableManualRunShortcuts(manualRunTarget)
          : { registered: true };
        if (!liveResult.registered || !runResult.registered) {
          restoreHudSettings(previous);
          throw new CoreClientError({
            code: "SHORTCUT_REGISTRATION_FAILED",
            message:
              "The shortcut mapping could not be registered; previous settings were restored.",
            retryable: true,
            details: {},
          });
        }
      }

      try {
        const result = await requireClient().request<{ settings: HudSettings }>(
          "hud.settings.update",
          { settings: update },
        );
        hudSettings = normalizeHudSettings(result.settings);
        repositionHud();
        return hudSettings;
      } catch (error) {
        if (hasShortcutUpdate) restoreHudSettings(previous);
        throw error;
      }
    });
  });
  ipcMain.handle("hud:get-displays", (event) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(() => ({ displays: allHudDisplays() }));
  });
  ipcMain.handle("hud:show", (event) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(() => {
      showHud();
      return { visible: true as const };
    });
  });
  ipcMain.handle("hud:hide", (event) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(() => {
      hideHud();
      return { visible: false as const };
    });
  });
  ipcMain.handle("hud:ready", (event) => {
    assertTrustedHudFrame(event, hudPolicy);
    return invokeResult(() => {
      sendHudStatus();
      hydrateHudCue();
      return { ready: true as const };
    });
  });
  ipcMain.handle("hud:set-expanded", (event, value: unknown) => {
    assertTrustedHudFrame(event, hudPolicy);
    return invokeResult(() => {
      if (!isJsonObject(value) || typeof value.expanded !== "boolean") {
        throw new Error("HUD expanded state is invalid.");
      }
      setHudExpanded(value.expanded);
      return { expanded: value.expanded };
    });
  });
  ipcMain.handle("hud:push-to-assist", (event) => {
    assertTrustedHudFrame(event, hudPolicy);
    return invokeResult(() => {
      requestLiveAssistWithTrigger("button");
      return { requested: true as const };
    });
  });
  ipcMain.handle("hud:cue-expand-sources", (event, value: unknown) => {
    assertTrustedHudFrame(event, hudPolicy);
    return invokeResult(() =>
      requireClient().request(
        "cue.expand_sources",
        bindHudCueRequest(value, liveTarget),
        30_000,
      ),
    );
  });
  ipcMain.handle("hud:cue-dismiss", (event, value: unknown) => {
    assertTrustedHudFrame(event, hudPolicy);
    return invokeResult(async () => {
      const target = liveTarget;
      const request = bindHudCueRequest(value, target);
      const assistId =
        currentHudCueId === request.cue_id ? suppressCurrentHudAssist() : null;
      if (assistId && target) {
        await requireClient()
          .request("assist.cancel", {
            project_id: target.projectId,
            session_id: target.sessionId,
            assist_id: assistId,
          })
          .catch(() => undefined);
      }
      return requireClient().request("cue.dismiss", request, 30_000);
    });
  });
  ipcMain.handle("hud:cue-navigate", (event, value: unknown) => {
    assertTrustedHudFrame(event, hudPolicy);
    return invokeResult(() => {
      if (
        !isJsonObject(value) ||
        (value.direction !== "previous" && value.direction !== "next")
      ) {
        throw new Error("HUD cue direction is invalid.");
      }
      navigateHudCue(value.direction);
      return { requested: true as const };
    });
  });
}

async function stopCore(): Promise<void> {
  disableManualRunShortcuts();
  disableLiveShortcuts();
  if (hudWindow && !hudWindow.isDestroyed()) hudWindow.close();
  if (!coreClient) return;
  await coreClient.shutdown();
}

void app.whenReady().then(() => {
  if (
    process.argv.includes(PACKAGED_SMOKE_ARGUMENT) &&
    !process.env.PRESENTER_COPILOT_DATA_ROOT
  ) {
    process.env.PRESENTER_COPILOT_DATA_ROOT = path.join(
      app.getPath("temp"),
      `presenter-copilot-smoke-${process.pid}`,
    );
  }
  const rendererPolicy: RendererValidationOptions = {
    bundledRendererPath: path.join(__dirname, "../renderer/index.html"),
    allowDevelopmentRenderer:
      !app.isPackaged && process.env.PRESENTER_COPILOT_DEV_MODE === "1",
  };
  const hudPolicy: HudValidationOptions = {
    ...rendererPolicy,
    bundledHudPath: path.join(__dirname, "../renderer/hud/index.html"),
    allowDevelopmentHud: rendererPolicy.allowDevelopmentRenderer,
  };
  currentHudPolicy = hudPolicy;
  hudRegistry = new GlobalShortcutRegistry(globalShortcut);
  registerIpc(rendererPolicy, hudPolicy);
  try {
    coreClient = new CoreProcessClient(
      createSidecarCommand({
        isPackaged: app.isPackaged,
        resourcesPath: process.resourcesPath,
      }),
    );
  } catch (error) {
    const safe =
      error instanceof SidecarResolutionError
        ? new CoreClientError({
            code: error.code,
            message: error.message,
            retryable: false,
            details: {},
          })
        : new CoreClientError({
            code: "SIDECAR_RESOLUTION_FAILED",
            message: "The Python core sidecar could not be resolved.",
            retryable: false,
            details: {},
          });
    coreClient = new CoreProcessClient({ command: "" });
    coreClient.markUnavailable(safe);
  }
  coreClient.onStatus((nextStatus) => {
    if (nextStatus.state === "stopping" || nextStatus.state === "stopped") {
      disableManualRunShortcuts();
      disableLiveShortcuts();
    } else if (nextStatus.state === "unavailable") {
      disableManualRunShortcuts();
      clearInterruptedLiveState();
    }
    sendStatus(nextStatus);
  });
  coreClient.onUnexpectedTermination(() => {
    clearInterruptedLiveState();
    automaticRestartController.onUnexpectedClose();
  });
  coreClient.onEvent(sendEvent);
  coreClient.onProtocolError((error) => {
    // Keep protocol diagnostics in the main process; never expose raw stderr
    // or arbitrary child-process output to the renderer.
    console.error(`[core:${error.code}] ${error.message}`);
  });
  mainWindow = createWindow(rendererPolicy);
  hudWindow = createHudWindow(hudPolicy);
  const bootstrap = bootstrapCore();
  if (process.argv.includes(PACKAGED_SMOKE_ARGUMENT)) {
    void bootstrap.then((ready) => {
      if (ready) void runPackagedSmoke();
      else {
        isQuitting = true;
        app.exit(1);
      }
    });
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0)
      mainWindow = createWindow(rendererPolicy);
  });
});

app.on("before-quit", (event) => {
  if (isQuitting || !coreClient) return;
  event.preventDefault();
  isQuitting = true;
  automaticRestartController.cancel();
  void stopCore()
    .catch((error) =>
      console.error(`[core:shutdown] ${toCoreError(error).message}`),
    )
    // stopCore has already closed the HUD and sidecar; exit directly so a
    // hidden non-closable HUD cannot keep Electron alive after cleanup.
    .finally(() => app.exit(0));
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
