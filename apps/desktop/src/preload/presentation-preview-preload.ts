import { contextBridge, ipcRenderer } from "electron";

import type {
  PresentationPreviewHostApi,
  PresentationPreviewHostRequest,
  PresentationPreviewHostResponse,
} from "../shared/presentation-preview-protocol";

const listeners = new Set<(request: PresentationPreviewHostRequest) => void>();

ipcRenderer.on("presentation-preview:request", (_event, value: unknown) => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return;
  for (const listener of listeners) {
    listener(value as PresentationPreviewHostRequest);
  }
});

const api: PresentationPreviewHostApi = {
  ready() {
    ipcRenderer.send("presentation-preview:ready");
  },
  onRequest(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  respond(response: PresentationPreviewHostResponse) {
    ipcRenderer.send("presentation-preview:response", response);
  },
};

contextBridge.exposeInMainWorld("presentationPreviewHost", api);
