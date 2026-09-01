import path from "node:path";

import { app, BrowserWindow, dialog, ipcMain } from "electron";
import type { IpcMainInvokeEvent } from "electron";

import { CoreProcessClient, toCoreError } from "./core-client";
import { invokeResult } from "./invoke-result";
import { createSidecarCommand } from "./sidecar-command";
import {
  isCoreMetadata,
  isHealthResult,
  isJsonObject,
  isRendererCoreMethod,
  PROTOCOL_VERSION,
  type CoreMetadata,
  type RendererCoreMethod,
  type CoreStatus,
  type EventEnvelope,
  type HealthResult,
  type JsonObject,
} from "../shared/protocol";
import {
  isTrustedRendererSender,
  selectRendererLoadTarget,
  type RendererValidationOptions,
} from "./sender-validation";

let mainWindow: BrowserWindow | null = null;
let coreClient: CoreProcessClient | null = null;
let isQuitting = false;

function createWindow(
  rendererPolicy: RendererValidationOptions,
): BrowserWindow {
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
  kind: "presentation" | "supporting";
} {
  if (!isJsonObject(value) || typeof value.project_id !== "string") {
    throw new Error("A project id is required to import a source.");
  }
  const kind = value.kind ?? "supporting";
  if (kind !== "presentation" && kind !== "supporting") {
    throw new Error("Source kind is invalid.");
  }
  return { projectId: value.project_id, kind };
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

function registerIpc(rendererPolicy: RendererValidationOptions): void {
  ipcMain.handle("core:get-status", (event) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(() => requireClient().getStatus());
  });
  ipcMain.handle("core:request", async (event, value: unknown) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(async () => {
      const request = validateRendererRequest(value);
      const timeoutMs =
        request.method === "source.reindex" ? 60_000 : undefined;
      return timeoutMs === undefined
        ? requireClient().request(request.method, request.params)
        : requireClient().request(request.method, request.params, timeoutMs);
    });
  });
  ipcMain.handle("source:pick-and-import", async (event, value: unknown) => {
    assertTrustedRendererSender(event, rendererPolicy);
    return invokeResult(async () => {
      const request = validateImportPickerRequest(value);
      const selection = await dialog.showOpenDialog({
        title: "Import presentation source",
        properties: ["openFile"],
        filters: [
          {
            name: "Supported sources",
            extensions: ["pdf", "pptx", "txt", "md", "markdown"],
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
}

async function stopCore(): Promise<void> {
  if (!coreClient) return;
  await coreClient.shutdown();
}

void app.whenReady().then(() => {
  const rendererPolicy: RendererValidationOptions = {
    bundledRendererPath: path.join(__dirname, "../renderer/index.html"),
    allowDevelopmentRenderer:
      !app.isPackaged && process.env.PRESENTER_COPILOT_DEV_MODE === "1",
  };
  registerIpc(rendererPolicy);
  const command = createSidecarCommand();
  coreClient = new CoreProcessClient(command);
  coreClient.onStatus(sendStatus);
  coreClient.onEvent(sendEvent);
  coreClient.onProtocolError((error) => {
    // Keep protocol diagnostics in the main process; never expose raw stderr
    // or arbitrary child-process output to the renderer.
    console.error(`[core:${error.code}] ${error.message}`);
  });
  mainWindow = createWindow(rendererPolicy);
  void bootstrapCore();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0)
      mainWindow = createWindow(rendererPolicy);
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
