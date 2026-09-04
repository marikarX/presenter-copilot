import { contextBridge, ipcRenderer } from "electron";

import type {
  CueExpandSourcesResult,
  EventEnvelope,
  InvokeResult,
  JsonObject,
  HudStatus,
  PresenterCopilotHudApi,
} from "../shared/protocol";

const api: PresenterCopilotHudApi = {
  ready(): Promise<InvokeResult<{ ready: true }>> {
    return ipcRenderer.invoke("hud:ready") as Promise<
      InvokeResult<{ ready: true }>
    >;
  },
  onEvent(listener: (event: EventEnvelope) => void): () => void {
    const handler = (_event: Electron.IpcRendererEvent, value: EventEnvelope) =>
      listener(value);
    ipcRenderer.on("hud:event", handler);
    return () => ipcRenderer.removeListener("hud:event", handler);
  },
  onStatus(listener: (status: HudStatus) => void): () => void {
    const handler = (_event: Electron.IpcRendererEvent, value: HudStatus) =>
      listener(value);
    ipcRenderer.on("hud:status", handler);
    return () => ipcRenderer.removeListener("hud:status", handler);
  },
  onCue(listener: (cue: JsonObject) => void): () => void {
    const handler = (_event: Electron.IpcRendererEvent, value: JsonObject) =>
      listener(value);
    ipcRenderer.on("hud:cue", handler);
    return () => ipcRenderer.removeListener("hud:cue", handler);
  },
  onClear(listener: () => void): () => void {
    const handler = () => listener();
    ipcRenderer.on("hud:clear", handler);
    return () => ipcRenderer.removeListener("hud:clear", handler);
  },
  setExpanded(expanded: boolean): Promise<InvokeResult<{ expanded: boolean }>> {
    return ipcRenderer.invoke("hud:set-expanded", { expanded }) as Promise<
      InvokeResult<{ expanded: boolean }>
    >;
  },
  pushToAssist(): Promise<InvokeResult<{ requested: true }>> {
    return ipcRenderer.invoke("hud:push-to-assist") as Promise<
      InvokeResult<{ requested: true }>
    >;
  },
  expandSources(cueId: string): Promise<InvokeResult<CueExpandSourcesResult>> {
    return ipcRenderer.invoke("hud:cue-expand-sources", {
      cue_id: cueId,
    }) as Promise<InvokeResult<CueExpandSourcesResult>>;
  },
  dismiss(cueId: string): Promise<InvokeResult<JsonObject>> {
    return ipcRenderer.invoke("hud:cue-dismiss", { cue_id: cueId }) as Promise<
      InvokeResult<JsonObject>
    >;
  },
  navigate(direction: "previous" | "next"): Promise<InvokeResult<JsonObject>> {
    return ipcRenderer.invoke("hud:cue-navigate", { direction }) as Promise<
      InvokeResult<JsonObject>
    >;
  },
};

contextBridge.exposeInMainWorld("presenterCopilotHud", api);
