import { contextBridge, ipcRenderer } from "electron";

import type {
  RendererCoreMethod,
  CoreStatus,
  EventEnvelope,
  JsonObject,
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
};

contextBridge.exposeInMainWorld("presenterCopilot", api);
