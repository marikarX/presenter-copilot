import path from "node:path";
import { randomUUID } from "node:crypto";

import {
  BrowserWindow,
  ipcMain,
  session,
  type IpcMainEvent,
  type Session,
} from "electron";

import {
  isTrustedRendererSender,
  type RendererValidationOptions,
} from "./sender-validation";
import { CoreClientError } from "./core-client";
import { invokeResult } from "./invoke-result";
import type { PresentationPreviewHostResponse } from "../shared/presentation-preview-protocol";
import type {
  PresentationPreviewOpenResult,
  PresentationPreviewRenderResult,
} from "../shared/protocol";

const PREVIEW_CHANNEL = "presentation-preview:request";
const PREVIEW_READY_CHANNEL = "presentation-preview:ready";
const PREVIEW_RESPONSE_CHANNEL = "presentation-preview:response";
const PREVIEW_REQUEST_TIMEOUT_MS = 120_000;
const MAX_PREVIEW_BYTES = 50 * 1024 * 1024;
const MAX_PREVIEW_IMAGE_BYTES = 16 * 1024 * 1024;
const MAX_PREVIEW_IMAGE_DIMENSION = 4096;
const PREVIEW_IMAGE_WIDTH = 960;
const MAX_PREVIEW_SLIDE_COUNT = 5000;
const MAX_TEXT_CANDIDATES = 100;
const MAX_TEXT_CANDIDATE_CHARS = 2000;
const MAX_TEXT_CANDIDATE_NAME_CHARS = 200;
const MAX_PREVIEW_FONT_NOTICES = 64;
const MAX_PREVIEW_FONT_NOTICE_CHARS = 256;

interface PresentationPreviewWindowOptions {
  readonly bundledPreviewPath: string;
  readonly allowDevelopmentPreview: boolean;
  readonly rendererPolicy: RendererValidationOptions;
}

interface PendingRequest {
  readonly window: BrowserWindow;
  readonly expectedType: "opened" | "slide" | "released";
  readonly resolve: (response: PresentationPreviewHostResponse) => void;
  readonly reject: (error: Error) => void;
  readonly timeout: ReturnType<typeof setTimeout>;
}

type PreviewChildRequest =
  | { type: "open"; buffer: ArrayBuffer }
  | {
      type: "render";
      slide_number: number;
      mock_text?: { shape_node_id: string; text: string };
    }
  | { type: "release-frame" };

interface ReadyWaiter {
  readonly window: BrowserWindow;
  readonly resolve: () => void;
  readonly reject: (error: Error) => void;
  readonly timeout: ReturnType<typeof setTimeout>;
}

interface PreviewDimensions {
  readonly height: number;
  readonly width: number;
}

let previewOptions: PresentationPreviewWindowOptions | null = null;
let previewSession: Session | null = null;
let previewWindow: BrowserWindow | null = null;
let previewDimensions: PreviewDimensions | null = null;
let readyWaiter: ReadyWaiter | null = null;
const pendingRequests = new Map<string, PendingRequest>();

function previewError(
  message: string,
  code = "PRESENTATION_PREVIEW_FAILED",
): CoreClientError {
  return new CoreClientError({
    code,
    message,
    retryable: false,
    details: {},
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasControlCharacter(value: string): boolean {
  return [...value].some((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    return codePoint < 32 || (codePoint >= 127 && codePoint <= 159);
  });
}

function isPreviewFontNoticeList(value: unknown): value is string[] {
  return (
    Array.isArray(value) &&
    value.length <= MAX_PREVIEW_FONT_NOTICES &&
    value.every(
      (item) =>
        typeof item === "string" &&
        item.length > 0 &&
        item.length <= MAX_PREVIEW_FONT_NOTICE_CHARS &&
        !hasControlCharacter(item),
    ) &&
    new Set(value).size === value.length
  );
}

function isTrustedMainRenderer(
  event: Electron.IpcMainInvokeEvent,
  rendererPolicy: RendererValidationOptions,
): boolean {
  return isTrustedRendererSender(
    event.senderFrame,
    event.sender.mainFrame,
    rendererPolicy,
  );
}

function isTrustedPreviewWindowEvent(
  event: IpcMainEvent,
): BrowserWindow | null {
  const activeWindow = previewWindow;
  if (
    !activeWindow ||
    activeWindow.isDestroyed() ||
    event.sender !== activeWindow.webContents ||
    !event.senderFrame ||
    event.senderFrame !== event.sender.mainFrame
  ) {
    return null;
  }
  return activeWindow;
}

function resolveReadyWaiter(window: BrowserWindow): void {
  const waiter = readyWaiter;
  if (!waiter || waiter.window !== window) return;
  clearTimeout(waiter.timeout);
  readyWaiter = null;
  waiter.resolve();
}

function rejectReadyWaiter(window: BrowserWindow, error: Error): void {
  const waiter = readyWaiter;
  if (!waiter || waiter.window !== window) return;
  clearTimeout(waiter.timeout);
  readyWaiter = null;
  waiter.reject(error);
}

function rejectPendingRequests(window: BrowserWindow, error: Error): void {
  for (const [id, pending] of pendingRequests) {
    if (pending.window !== window) continue;
    clearTimeout(pending.timeout);
    pendingRequests.delete(id);
    pending.reject(error);
  }
}

function disposePreviewWindow(
  window: BrowserWindow | null = previewWindow,
  message = "The presentation preview was closed.",
): void {
  if (!window) return;
  if (previewWindow === window) {
    previewWindow = null;
    previewDimensions = null;
  }
  const error = previewError(message);
  rejectReadyWaiter(window, error);
  rejectPendingRequests(window, error);
  if (!window.isDestroyed()) window.destroy();
}

function requestPreviewChild(
  window: BrowserWindow,
  request: PreviewChildRequest,
): Promise<PresentationPreviewHostResponse> {
  if (window.isDestroyed() || previewWindow !== window) {
    return Promise.reject(previewError("The presentation preview is closed."));
  }

  const id = randomUUID();
  const expectedType =
    request.type === "open"
      ? "opened"
      : request.type === "render"
        ? "slide"
        : "released";

  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      pendingRequests.delete(id);
      const error = previewError(
        "The presentation preview exceeded its time limit.",
        "PRESENTATION_PREVIEW_TIMEOUT",
      );
      reject(error);
      disposePreviewWindow(window, error.message);
    }, PREVIEW_REQUEST_TIMEOUT_MS);
    pendingRequests.set(id, {
      window,
      expectedType,
      resolve,
      reject,
      timeout,
    });
    try {
      window.webContents.send(PREVIEW_CHANNEL, { ...request, id });
    } catch {
      clearTimeout(timeout);
      pendingRequests.delete(id);
      reject(previewError("The isolated presentation preview stopped."));
      disposePreviewWindow(window);
    }
  });
}

function isValidTextCandidates(
  value: unknown,
): value is PresentationPreviewRenderResult["text_candidates"] {
  return (
    Array.isArray(value) &&
    value.length <= MAX_TEXT_CANDIDATES &&
    value.every(
      (candidate) =>
        isRecord(candidate) &&
        typeof candidate.shape_node_id === "string" &&
        candidate.shape_node_id.length > 0 &&
        candidate.shape_node_id.length <= 128 &&
        typeof candidate.name === "string" &&
        candidate.name.length <= MAX_TEXT_CANDIDATE_NAME_CHARS &&
        typeof candidate.text === "string" &&
        candidate.text.length > 0 &&
        candidate.text.length <= MAX_TEXT_CANDIDATE_CHARS,
    )
  );
}

function isValidMockTextOverflow(value: unknown): value is boolean | null {
  return value === null || typeof value === "boolean";
}

function validatePng(image: Electron.NativeImage): Uint8Array {
  const size = image.getSize();
  const png = image.toPNG();
  if (
    size.width < 1 ||
    size.height < 1 ||
    size.width > MAX_PREVIEW_IMAGE_DIMENSION ||
    size.height > MAX_PREVIEW_IMAGE_DIMENSION ||
    png.length < 8 ||
    png.length > MAX_PREVIEW_IMAGE_BYTES ||
    png[0] !== 0x89 ||
    png[1] !== 0x50 ||
    png[2] !== 0x4e ||
    png[3] !== 0x47 ||
    png[4] !== 0x0d ||
    png[5] !== 0x0a ||
    png[6] !== 0x1a ||
    png[7] !== 0x0a
  ) {
    throw previewError("The isolated preview image could not be verified.");
  }
  return Uint8Array.from(png);
}

function initializePreviewSession(
  options: PresentationPreviewWindowOptions,
): Session {
  if (previewSession) return previewSession;
  const isolatedSession = session.fromPartition(
    "presenter-copilot-presentation-preview",
  );
  isolatedSession.setPermissionRequestHandler(
    (_webContents, _permission, callback) => callback(false),
  );
  isolatedSession.setPermissionCheckHandler(() => false);
  isolatedSession.webRequest.onBeforeRequest(
    { urls: ["http://*/*", "https://*/*", "ws://*/*", "wss://*/*"] },
    (details, callback) => {
      let allowed = false;
      if (options.allowDevelopmentPreview) {
        try {
          const requestUrl = new URL(details.url);
          allowed =
            requestUrl.hostname === "127.0.0.1" &&
            requestUrl.port === "5173" &&
            (requestUrl.protocol === "http:" ||
              requestUrl.protocol === "ws:") &&
            requestUrl.username === "" &&
            requestUrl.password === "";
        } catch {
          allowed = false;
        }
      }
      callback({ cancel: !allowed });
    },
  );
  previewSession = isolatedSession;
  return isolatedSession;
}

function waitForPreviewReady(window: BrowserWindow): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      rejectReadyWaiter(
        window,
        previewError("The isolated presentation preview did not start."),
      );
      disposePreviewWindow(
        window,
        "The isolated presentation preview did not start.",
      );
    }, PREVIEW_REQUEST_TIMEOUT_MS);
    readyWaiter = { window, resolve, reject, timeout };
    window.webContents.once("render-process-gone", () =>
      onPreviewRendererGone(window),
    );
    window.webContents.once(
      "did-fail-load",
      (_event, errorCode, _description, _validatedUrl, isMainFrame) => {
        if (isMainFrame) {
          rejectReadyWaiter(
            window,
            previewError(`The isolated preview failed to load (${errorCode}).`),
          );
        }
      },
    );
  });
}

function onPreviewRendererGone(window: BrowserWindow): void {
  disposePreviewWindow(window, "The isolated presentation preview stopped.");
}

function createPreviewWindow(
  options: PresentationPreviewWindowOptions,
): BrowserWindow {
  const window = new BrowserWindow({
    width: PREVIEW_IMAGE_WIDTH,
    height: 540,
    paintWhenInitiallyHidden: true,
    show: false,
    frame: false,
    resizable: false,
    skipTaskbar: true,
    backgroundColor: "#ffffff",
    webPreferences: {
      preload: path.join(
        __dirname,
        "../preload/presentation-preview-preload.js",
      ),
      session: initializePreviewSession(options),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      backgroundThrottling: false,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event) => event.preventDefault());
  window.webContents.on("will-redirect", (event) => event.preventDefault());
  window.webContents.on("render-process-gone", () =>
    onPreviewRendererGone(window),
  );
  window.on("closed", () => {
    if (previewWindow === window) {
      previewWindow = null;
      previewDimensions = null;
    }
    rejectReadyWaiter(window, previewError("The isolated preview was closed."));
    rejectPendingRequests(
      window,
      previewError("The isolated preview was closed."),
    );
  });
  return window;
}

function loadPreviewWindow(
  window: BrowserWindow,
  options: PresentationPreviewWindowOptions,
): Promise<void> {
  const ready = waitForPreviewReady(window);
  const load = options.allowDevelopmentPreview
    ? window.loadURL("http://127.0.0.1:5173/presentation-preview/index.html")
    : window.loadFile(options.bundledPreviewPath);
  void load.catch(() => {
    rejectReadyWaiter(
      window,
      previewError("The isolated presentation preview could not be loaded."),
    );
  });
  return ready;
}

async function openPresentationPreview(
  value: unknown,
): Promise<PresentationPreviewOpenResult> {
  const options = previewOptions;
  if (!options) {
    throw previewError("The presentation preview is not configured.");
  }
  if (
    !(value instanceof ArrayBuffer) ||
    value.byteLength < 1 ||
    value.byteLength > MAX_PREVIEW_BYTES
  ) {
    throw previewError("The presentation file exceeds the preview limit.");
  }

  disposePreviewWindow();
  let window: BrowserWindow | null = null;
  try {
    const currentWindow = createPreviewWindow(options);
    window = currentWindow;
    previewWindow = currentWindow;
    await loadPreviewWindow(currentWindow, options);
    const response = await requestPreviewChild(currentWindow, {
      type: "open",
      buffer: value,
    });
    if (
      !response.ok ||
      response.type !== "opened" ||
      !Number.isSafeInteger(response.slide_count) ||
      response.slide_count < 1 ||
      response.slide_count > MAX_PREVIEW_SLIDE_COUNT ||
      !Number.isFinite(response.slide_width) ||
      response.slide_width <= 0 ||
      response.slide_width > 100_000 ||
      !Number.isFinite(response.slide_height) ||
      response.slide_height <= 0 ||
      response.slide_height > 100_000 ||
      !isPreviewFontNoticeList(response.font_substitutions) ||
      !isPreviewFontNoticeList(response.unresolved_font_families) ||
      typeof response.font_check_limited !== "boolean"
    ) {
      throw previewError(
        "This presentation could not be opened in the isolated preview.",
      );
    }
    const height = Math.round(
      (PREVIEW_IMAGE_WIDTH * response.slide_height) / response.slide_width,
    );
    if (height < 1 || height > MAX_PREVIEW_IMAGE_DIMENSION) {
      throw previewError(
        "The presentation slide dimensions exceed the preview limit.",
      );
    }
    previewDimensions = { width: PREVIEW_IMAGE_WIDTH, height };
    currentWindow.setContentSize(PREVIEW_IMAGE_WIDTH, height);
    return {
      slide_count: response.slide_count,
      slide_width: response.slide_width,
      slide_height: response.slide_height,
      font_substitutions: response.font_substitutions,
      unresolved_font_families: response.unresolved_font_families,
      font_check_limited: response.font_check_limited,
    };
  } catch (error) {
    if (window) disposePreviewWindow(window);
    throw error;
  } finally {
    // The preview child owns its IPC copy; the main process no longer needs the
    // input after open completes, including on timeout or validation failure.
    new Uint8Array(value).fill(0);
  }
}

async function renderPresentationPreview(
  value: unknown,
): Promise<PresentationPreviewRenderResult> {
  const window = previewWindow;
  const dimensions = previewDimensions;
  if (!window || !dimensions || window.isDestroyed()) {
    throw previewError(
      "Open a presentation before requesting a slide preview.",
    );
  }
  if (!isRecord(value) || !Number.isSafeInteger(value.slide_number)) {
    throw previewError("The requested preview slide is invalid.");
  }
  const slideNumber = value.slide_number as number;
  let mockText: { shape_node_id: string; text: string } | undefined;
  if (value.mock_text !== undefined) {
    if (
      !isRecord(value.mock_text) ||
      typeof value.mock_text.shapeNodeId !== "string" ||
      value.mock_text.shapeNodeId.length < 1 ||
      value.mock_text.shapeNodeId.length > 128 ||
      typeof value.mock_text.text !== "string" ||
      value.mock_text.text.length > MAX_TEXT_CANDIDATE_CHARS
    ) {
      throw previewError("The requested mock text is invalid.");
    }
    mockText = {
      shape_node_id: value.mock_text.shapeNodeId,
      text: value.mock_text.text,
    };
  }

  const response = await requestPreviewChild(window, {
    type: "render",
    slide_number: slideNumber,
    ...(mockText ? { mock_text: mockText } : {}),
  });
  try {
    if (
      !response.ok ||
      response.type !== "slide" ||
      response.slide_number !== slideNumber ||
      !isValidTextCandidates(response.text_candidates) ||
      (mockText !== undefined &&
        !isValidMockTextOverflow(response.mock_text_overflows_shape)) ||
      (response.mock_text_overflows_shape !== undefined &&
        !isValidMockTextOverflow(response.mock_text_overflows_shape))
    ) {
      throw previewError("The requested preview slide could not be rendered.");
    }
    let captureTimeout: ReturnType<typeof setTimeout> | null = null;
    const image = await Promise.race([
      window.webContents.capturePage({
        x: 0,
        y: 0,
        width: dimensions.width,
        height: dimensions.height,
      }),
      new Promise<never>((_resolve, reject) => {
        captureTimeout = setTimeout(() => {
          const error = previewError(
            "The isolated preview image exceeded its time limit.",
            "PRESENTATION_PREVIEW_TIMEOUT",
          );
          disposePreviewWindow(window, error.message);
          reject(error);
        }, PREVIEW_REQUEST_TIMEOUT_MS);
      }),
    ]).finally(() => {
      if (captureTimeout) clearTimeout(captureTimeout);
    });
    return {
      slide_number: slideNumber,
      width: image.getSize().width,
      height: image.getSize().height,
      image: validatePng(image),
      text_candidates: response.text_candidates,
      ...(response.mock_text_overflows_shape !== undefined
        ? { mock_text_overflows_shape: response.mock_text_overflows_shape }
        : {}),
    };
  } finally {
    try {
      const released = await requestPreviewChild(window, {
        type: "release-frame",
      });
      if (!released.ok || released.type !== "released") {
        disposePreviewWindow(window);
      }
    } catch {
      disposePreviewWindow(window);
    }
  }
}

function onPreviewReady(event: IpcMainEvent): void {
  const window = isTrustedPreviewWindowEvent(event);
  if (window) resolveReadyWaiter(window);
}

function onPreviewResponse(event: IpcMainEvent, value: unknown): void {
  const window = isTrustedPreviewWindowEvent(event);
  if (!window || !isRecord(value) || typeof value.id !== "string") return;
  const pending = pendingRequests.get(value.id);
  if (!pending || pending.window !== window) return;
  const isFailure = value.ok === false;
  const expectedType = pending.expectedType;
  const isExpectedSuccess = value.ok === true && value.type === expectedType;
  if (!isFailure && !isExpectedSuccess) return;
  clearTimeout(pending.timeout);
  pendingRequests.delete(value.id);
  if (isFailure) {
    pending.reject(previewError("The isolated presentation preview failed."));
    return;
  }
  pending.resolve(value as PresentationPreviewHostResponse);
}

export function registerPresentationPreviewIpc(
  rendererPolicy: RendererValidationOptions,
  options: PresentationPreviewWindowOptions,
): void {
  previewOptions = options;
  ipcMain.on(PREVIEW_READY_CHANNEL, onPreviewReady);
  ipcMain.on(PREVIEW_RESPONSE_CHANNEL, onPreviewResponse);
  ipcMain.handle("presentation-preview:open", (event, value: unknown) => {
    if (!isTrustedMainRenderer(event, rendererPolicy)) {
      throw previewError("The presentation preview request was rejected.");
    }
    return invokeResult(() => openPresentationPreview(value));
  });
  ipcMain.handle("presentation-preview:render", (event, value: unknown) => {
    if (!isTrustedMainRenderer(event, rendererPolicy)) {
      throw previewError("The presentation preview request was rejected.");
    }
    return invokeResult(() => renderPresentationPreview(value));
  });
  ipcMain.handle("presentation-preview:close", (event) => {
    if (!isTrustedMainRenderer(event, rendererPolicy)) {
      throw previewError("The presentation preview request was rejected.");
    }
    closePresentationPreview();
    return invokeResult(() => ({ closed: true as const }));
  });
}

export function closePresentationPreview(): void {
  disposePreviewWindow();
}
