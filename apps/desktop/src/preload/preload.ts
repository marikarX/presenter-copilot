import { contextBridge, ipcRenderer } from "electron";

import type {
  RendererCoreMethod,
  CoreStatus,
  EventEnvelope,
  JsonObject,
  ImportSourceResult,
  PresentationExportResult,
  PresentationPdfResult,
  NativeAppearanceResult,
  NativeLayersResult,
  PresentationPreviewOpenResult,
  PresentationPreviewRenderResult,
  InvokeResult,
  ManualShortcutResult,
  HudDisplay,
  HudSettings,
  HudSettingsUpdate,
  HudStatus,
  DiagnosticPreviewResult,
  DiagnosticSaveResult,
  DiagnosticSection,
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
  presentation: {
    nativeAppearance(
      projectId,
      documentId,
      expectedRevisionId,
      sourceSha256,
      slideNumber,
    ) {
      return ipcRenderer.invoke("presentation:native-appearance", {
        project_id: projectId,
        document_id: documentId,
        expected_revision_id: expectedRevisionId,
        source_sha256: sourceSha256,
        slide_number: slideNumber,
      }) as Promise<InvokeResult<NativeAppearanceResult>>;
    },
    nativeLayers(
      projectId,
      documentId,
      expectedRevisionId,
      sourceSha256,
      slideNumber,
    ) {
      return ipcRenderer.invoke("presentation:native-layers", {
        project_id: projectId,
        document_id: documentId,
        expected_revision_id: expectedRevisionId,
        source_sha256: sourceSha256,
        slide_number: slideNumber,
      }) as Promise<InvokeResult<NativeLayersResult>>;
    },
    nativeEditPlanAppearance(
      projectId,
      documentId,
      expectedRevisionId,
      planId,
      sourceSha256,
      slideNumber,
    ) {
      return ipcRenderer.invoke("presentation:native-edit-appearance", {
        project_id: projectId,
        document_id: documentId,
        expected_revision_id: expectedRevisionId,
        plan_id: planId,
        source_sha256: sourceSha256,
        slide_number: slideNumber,
      }) as Promise<InvokeResult<NativeAppearanceResult>>;
    },
    savePdf(projectId, documentId, expectedRevisionId, includeHidden) {
      return ipcRenderer.invoke("presentation:save-pdf", {
        project_id: projectId,
        document_id: documentId,
        expected_revision_id: expectedRevisionId,
        include_hidden: includeHidden,
      }) as Promise<InvokeResult<PresentationPdfResult | { cancelled: true }>>;
    },
    saveUnchangedCopy(
      projectId: string,
      documentId: string,
    ): Promise<InvokeResult<PresentationExportResult | { cancelled: true }>> {
      return ipcRenderer.invoke("presentation:save-unchanged-copy", {
        project_id: projectId,
        document_id: documentId,
      }) as Promise<
        InvokeResult<PresentationExportResult | { cancelled: true }>
      >;
    },
    saveCurrentCopy(
      projectId: string,
      documentId: string,
      openAfterSave = false,
    ): Promise<InvokeResult<PresentationExportResult | { cancelled: true }>> {
      return ipcRenderer.invoke("presentation:save-current-copy", {
        project_id: projectId,
        document_id: documentId,
        ...(openAfterSave ? { open_after_save: true } : {}),
      }) as Promise<
        InvokeResult<PresentationExportResult | { cancelled: true }>
      >;
    },
  },
  presentationPreview: {
    open(buffer: ArrayBuffer) {
      return ipcRenderer.invoke("presentation-preview:open", buffer) as Promise<
        InvokeResult<PresentationPreviewOpenResult>
      >;
    },
    render(slideNumber, mockText) {
      return ipcRenderer.invoke("presentation-preview:render", {
        slide_number: slideNumber,
        ...(mockText ? { mock_text: mockText } : {}),
      }) as Promise<InvokeResult<PresentationPreviewRenderResult>>;
    },
    close() {
      return ipcRenderer.invoke("presentation-preview:close") as Promise<
        InvokeResult<{ closed: true }>
      >;
    },
  },
  chatgptPlan: {
    openUsageSettings() {
      return ipcRenderer.invoke("chatgpt-plan:open-usage-settings") as Promise<
        InvokeResult<{ opened: true }>
      >;
    },
  },
  diagnostics: {
    preview(
      sections?: DiagnosticSection[],
    ): Promise<InvokeResult<DiagnosticPreviewResult>> {
      return ipcRenderer.invoke("diagnostics:preview", sections) as Promise<
        InvokeResult<DiagnosticPreviewResult>
      >;
    },
    save(
      sections?: DiagnosticSection[],
    ): Promise<InvokeResult<DiagnosticSaveResult>> {
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
