import { contextBridge, ipcRenderer } from "electron";

import type {
  RendererCoreMethod,
  CoreStatus,
  EventEnvelope,
  JsonObject,
  ImportSourceResult,
  InvokeResult,
  ManualShortcutResult,
  PresenterCopilotApi,
} from "../shared/protocol";

const api: PresenterCopilotApi = {
  core: {
    request<T = unknown>(
      method: RendererCoreMethod,
      params?: JsonObject,
    ): Promise<InvokeResult<T>> {
      return ipcRenderer.invoke("core:request", {
        method,
        params: params ?? {},
      }) as Promise<InvokeResult<T>>;
    },
    getStatus(): Promise<InvokeResult<CoreStatus>> {
      return ipcRenderer.invoke("core:get-status") as Promise<
        InvokeResult<CoreStatus>
      >;
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
      kind: "presentation" | "supporting" | "transcript" = "supporting",
    ): Promise<InvokeResult<ImportSourceResult>> {
      return ipcRenderer.invoke("source:pick-and-import", {
        project_id: projectId,
        kind,
      }) as Promise<InvokeResult<ImportSourceResult>>;
    },
  },
  shortcuts: {
    enableManualRun(
      projectId: string,
      sessionId: string,
    ): Promise<InvokeResult<ManualShortcutResult>> {
      return ipcRenderer.invoke("run:enable-manual-shortcuts", {
        project_id: projectId,
        session_id: sessionId,
      }) as Promise<InvokeResult<ManualShortcutResult>>;
    },
    disableManualRun(): Promise<InvokeResult<{ disabled: true }>> {
      return ipcRenderer.invoke("run:disable-manual-shortcuts") as Promise<
        InvokeResult<{ disabled: true }>
      >;
    },
  },
};

contextBridge.exposeInMainWorld("presenterCopilot", api);
