import path from "node:path";

import { app, BrowserWindow, ipcMain } from "electron";

import { CoreProcessClient, toCoreError } from "./core-client";
import { createSidecarCommand } from "./sidecar-command";
import {
  isCoreMethod,
  isCoreMetadata,
  isHealthResult,
  isJsonObject,
  PROTOCOL_VERSION,
  type CoreMetadata,
  type RendererCoreMethod,
  type CoreStatus,
  type EventEnvelope,
  type HealthResult,
  type JsonObject,
} from "../shared/protocol";

let mainWindow: BrowserWindow | null = null;
let coreClient: CoreProcessClient | null = null;
let isQuitting = false;

function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 980,
    height: 720,
    minWidth: 720,
    minHeight: 520,
    show: false,
    backgroundColor: "#0b1220",
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
    if (mainWindow === window) mainWindow = null;
  });

  const developmentUrl = process.env.PRESENTER_COPILOT_DEV_SERVER_URL;
  if (developmentUrl) {
    void window.loadURL(developmentUrl);
  } else {
    void window.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
  return window;
}

function sendStatus(status: CoreStatus): void {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("core:status", status);
}

function sendEvent(event: EventEnvelope): void {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("core:event", event);
}

function requireClient(): CoreProcessClient {
  if (!coreClient) throw new Error("Core client is not initialized.");
  return coreClient;
}

function validateRendererRequest(value: unknown): {
  method: RendererCoreMethod;
  params: JsonObject;
} {
  if (
    !isJsonObject(value) ||
    !isCoreMethod(value.method) ||
    value.method === "core.shutdown"
  ) {
    throw new Error("Only allowlisted core methods may be invoked.");
  }
  if (value.params !== undefined && !isJsonObject(value.params)) {
    throw new Error("Core request params must be a JSON object.");
  }
  return { method: value.method, params: value.params ?? {} };
}

async function bootstrapCore(): Promise<void> {
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
  } catch (error) {
    client.markUnavailable(error);
  }
}

function registerIpc(): void {
  ipcMain.handle("core:get-status", () => requireClient().getStatus());
  ipcMain.handle("core:request", async (_event, value: unknown) => {
    const request = validateRendererRequest(value);
    return requireClient().request(request.method, request.params);
  });
}

async function stopCore(): Promise<void> {
  if (!coreClient) return;
  await coreClient.shutdown();
}

void app.whenReady().then(() => {
  registerIpc();
  const command = createSidecarCommand();
  coreClient = new CoreProcessClient(command);
  coreClient.onStatus(sendStatus);
  coreClient.onEvent(sendEvent);
  coreClient.onProtocolError((error) => {
    // Keep protocol diagnostics in the main process; never expose raw stderr
    // or arbitrary child-process output to the renderer.
    console.error(`[core:${error.code}] ${error.message}`);
  });
  mainWindow = createWindow();
  void bootstrapCore();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) mainWindow = createWindow();
  });
});

app.on("before-quit", (event) => {
  if (isQuitting || !coreClient) return;
  event.preventDefault();
  isQuitting = true;
  void stopCore()
    .catch((error) =>
      console.error(`[core:shutdown] ${toCoreError(error).message}`),
    )
    .finally(() => app.quit());
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
