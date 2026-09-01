import { contextBridge, ipcRenderer } from "electron";

import type {
  RendererCoreMethod,
  CoreStatus,
  EventEnvelope,
  JsonObject,
  ImportSourceResult,
  PresenterCopilotApi,
} from "../shared/protocol";

const api: PresenterCopilotApi = {
  core: {
    request<T = unknown>(
      method: RendererCoreMethod,
      params?: JsonObject,
    ): Promise<T> {
      return ipcRenderer.invoke("core:request", {
        method,
        params: params ?? {},
      }) as Promise<T>;
    },
    getStatus(): Promise<CoreStatus> {
      return ipcRenderer.invoke("core:get-status") as Promise<CoreStatus>;
    },
    onEvent(listener: (event: EventEnvelope) => void): () => void {
      const handler = (
        _event: Electron.IpcRendererEvent,
        event: EventEnvelope,
      ) => listener(event);
      ipcRenderer.on("core:event", handler);
      return () => ipcRenderer.removeListener("core:event", handler);
    },
    onStatus(listener: (status: CoreStatus) => void): () => void {
      const handler = (_event: Electron.IpcRendererEvent, status: CoreStatus) =>
        listener(status);
      ipcRenderer.on("core:status", handler);
      return () => ipcRenderer.removeListener("core:status", handler);
    },
  },
  source: {
    pickAndImport(
      projectId: string,
      kind: "presentation" | "supporting" = "supporting",
    ): Promise<ImportSourceResult> {
      return ipcRenderer.invoke("source:pick-and-import", {
        project_id: projectId,
        kind,
      }) as Promise<ImportSourceResult>;
    },
  },
};

contextBridge.exposeInMainWorld("presenterCopilot", api);
