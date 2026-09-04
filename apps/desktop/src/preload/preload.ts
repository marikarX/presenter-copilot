import { contextBridge, ipcRenderer } from "electron";

import type {
  RendererCoreMethod,
  CoreStatus,
  EventEnvelope,
  JsonObject,
  ImportSourceResult,
  InvokeResult,
  ManualShortcutResult,
  HudDisplay,
  HudSettings,
  HudSettingsUpdate,
  HudStatus,
  DiagnosticPreviewResult,
  DiagnosticSaveResult,
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
  diagnostics: {
    preview(
      sections?: string[],
    ): Promise<InvokeResult<DiagnosticPreviewResult>> {
      return ipcRenderer.invoke("diagnostics:preview", sections) as Promise<
        InvokeResult<DiagnosticPreviewResult>
      >;
    },
    save(sections?: string[]): Promise<InvokeResult<DiagnosticSaveResult>> {
      return ipcRenderer.invoke("diagnostics:save", sections) as Promise<
        InvokeResult<DiagnosticSaveResult>
      >;
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
  hud: {
    getStatus(): Promise<InvokeResult<HudStatus>> {
      return ipcRenderer.invoke("hud:get-status") as Promise<
        InvokeResult<HudStatus>
      >;
    },
    getSettings(): Promise<InvokeResult<HudSettings>> {
      return ipcRenderer.invoke("hud:get-settings") as Promise<
        InvokeResult<HudSettings>
      >;
    },
    updateSettings(
      settings: HudSettingsUpdate,
    ): Promise<InvokeResult<HudSettings>> {
      return ipcRenderer.invoke("hud:update-settings", settings) as Promise<
        InvokeResult<HudSettings>
      >;
    },
    getDisplays(): Promise<InvokeResult<{ displays: HudDisplay[] }>> {
      return ipcRenderer.invoke("hud:get-displays") as Promise<
        InvokeResult<{ displays: HudDisplay[] }>
      >;
    },
    show(): Promise<InvokeResult<{ visible: true }>> {
      return ipcRenderer.invoke("hud:show") as Promise<
        InvokeResult<{ visible: true }>
      >;
    },
    hide(): Promise<InvokeResult<{ visible: false }>> {
      return ipcRenderer.invoke("hud:hide") as Promise<
        InvokeResult<{ visible: false }>
      >;
    },
  },
};

contextBridge.exposeInMainWorld("presenterCopilot", api);
