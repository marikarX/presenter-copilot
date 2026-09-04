import { useCallback, useEffect, useState } from "react";

import type {
  CredentialStatus,
  DiagnosticPreviewResult,
  ModelsStatusResult,
  ModelStatusSummary,
  RendererCoreMethod,
} from "../shared/protocol";
import { unwrapInvokeResult } from "../shared/protocol";

interface ReleaseControlsProps {
  coreReady: boolean;
  runActive: boolean;
  onResetComplete: () => void;
}

function requestCore<T>(
  method: RendererCoreMethod,
  params?: Record<string, unknown>,
): Promise<T> {
  return window.presenterCopilot.core
    .request<T>(method, params)
    .then(unwrapInvokeResult);
}

function errorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null) {
    const value = error as { code?: unknown; message?: unknown };
    if (typeof value.code === "string" && typeof value.message === "string")
      return `${value.code}: ${value.message}`;
    if (typeof value.message === "string") return value.message;
  }
  return "The request could not be completed.";
}

function modelLabel(model: ModelStatusSummary): string {
  return model.kind === "asr" ? "Speech recognition" : "Semantic retrieval";
}

export function ReleaseControls({
  coreReady,
  runActive,
  onResetComplete,
}: ReleaseControlsProps) {
  const [models, setModels] = useState<ModelsStatusResult | null>(null);
  const [credentials, setCredentials] = useState<CredentialStatus | null>(null);
  const [diagnosticPreview, setDiagnosticPreview] =
    useState<DiagnosticPreviewResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [removeModelCache, setRemoveModelCache] = useState(false);

  const loadModels = useCallback(async () => {
    try {
      setModels(await requestCore<ModelsStatusResult>("models.status"));
    } catch (error) {
      setNotice(errorMessage(error));
    }
  }, []);

  const loadCredentials = useCallback(async () => {
    try {
      setCredentials(
        await requestCore<CredentialStatus>("provider.credentials.status"),
      );
    } catch (error) {
      setNotice(errorMessage(error));
    }
  }, []);

  useEffect(() => {
    if (!coreReady) return;
    void loadModels();
    void loadCredentials();
  }, [coreReady, loadCredentials, loadModels]);

  const prepareModel = useCallback(
    async (model: ModelStatusSummary) => {
      if (
        runActive ||
        !window.confirm(
          `Prepare ${modelLabel(model)} model “${model.model_id}” now? This is the only action that may download the approved local model.`,
        )
      )
        return;
      setBusy(`prepare-${model.kind}`);
      setNotice(null);
      try {
        await requestCore("models.prepare", { kind: model.kind });
        await loadModels();
        setNotice(`${modelLabel(model)} model is ready for local use.`);
      } catch (error) {
        setNotice(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadModels, runActive],
  );

  const removeModel = useCallback(
    async (model: ModelStatusSummary) => {
      if (
        runActive ||
        !window.confirm(
          `Remove the ${modelLabel(model).toLowerCase()} model cache? Project data is retained, but this model must be prepared again before use.`,
        )
      )
        return;
      setBusy(`remove-${model.kind}`);
      setNotice(null);
      try {
        await requestCore("models.remove", { kind: model.kind, confirm: true });
        await loadModels();
        setNotice(`${modelLabel(model)} model cache removed.`);
      } catch (error) {
        setNotice(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadModels, runActive],
  );

  const saveDetectedCredential = useCallback(async () => {
    setBusy("save-credential");
    setNotice(null);
    try {
      await requestCore("provider.credentials.save_detected");
      await loadCredentials();
      setNotice(
        "The detected credential was saved to the operating-system store.",
      );
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [loadCredentials]);

  const removeCredential = useCallback(async () => {
    if (
      !window.confirm(
        "Remove the stored provider credential? Environment variables are not changed.",
      )
    )
      return;
    setBusy("remove-credential");
    setNotice(null);
    try {
      await requestCore("provider.credentials.remove");
      await loadCredentials();
      setNotice("The stored provider credential was removed.");
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [loadCredentials]);

  const previewDiagnostics = useCallback(async () => {
    setBusy("diagnostic-preview");
    setNotice(null);
    try {
      const result = await window.presenterCopilot.diagnostics
        .preview(["core", "storage", "models", "provider", "benchmarks"])
        .then(unwrapInvokeResult);
      setDiagnosticPreview(result);
      setNotice("Safe diagnostic metadata is ready to review.");
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, []);

  const saveDiagnostics = useCallback(async () => {
    setBusy("diagnostic-save");
    setNotice(null);
    try {
      const result = await window.presenterCopilot.diagnostics
        .save(["core", "storage", "models", "provider", "logs", "benchmarks"])
        .then(unwrapInvokeResult);
      if (result.cancelled) {
        setNotice("Diagnostic export cancelled.");
      } else {
        setNotice(
          "Safe diagnostic ZIP exported from the selected native save location.",
        );
      }
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, []);

  const resetLocalData = useCallback(async () => {
    const cacheText = removeModelCache
      ? " Project data, settings, logs, credentials, and model caches will be removed."
      : " Project data, settings, logs, and credentials will be removed; model caches will be retained.";
    if (!window.confirm(`Reset all local application data?${cacheText}`))
      return;
    setBusy("reset-local-data");
    setNotice(null);
    try {
      await requestCore("app.reset_local_data", {
        confirm: true,
        remove_model_cache: removeModelCache,
      });
      setDiagnosticPreview(null);
      await Promise.all([loadModels(), loadCredentials()]);
      onResetComplete();
      setNotice(
        "Local application data was reset. Model-cache retention followed your selection.",
      );
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [loadCredentials, loadModels, onResetComplete, removeModelCache]);

  const controlsDisabled = !coreReady || runActive || busy !== null;

  return (
    <section
      className="release-controls"
      aria-labelledby="release-controls-title"
    >
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">M9 · Release controls</p>
          <h2 id="release-controls-title">
            Models, credentials, and diagnostics
          </h2>
        </div>
        <span className="event-label">No silent model downloads</span>
      </div>
      <p className="section-copy release-copy">
        Normal runtime uses local files only. Preparing a model is an explicit
        action; credentials stay in the operating-system store and never enter
        the renderer.
      </p>

      <div className="model-list">
        {(models?.models ?? []).map((model) => (
          <article className="model-card" key={model.kind}>
            <div>
              <p className="model-label">{modelLabel(model)}</p>
              <strong>{model.model_id}</strong>
              <span className="model-meta">
                {model.status} ·{" "}
                {model.local_only ? "local only" : "policy unavailable"} ·{" "}
                {model.cache_location}
              </span>
            </div>
            <div className="model-actions">
              <button
                type="button"
                className="primary-button"
                onClick={() => void prepareModel(model)}
                disabled={controlsDisabled || model.preparing}
              >
                {busy === `prepare-${model.kind}`
                  ? "Preparing…"
                  : "Prepare explicitly"}
              </button>
              <button
                type="button"
                className="text-button danger-text"
                onClick={() => void removeModel(model)}
                disabled={controlsDisabled || model.status === "not_installed"}
              >
                Remove cache
              </button>
            </div>
          </article>
        ))}
      </div>

      <div className="release-grid">
        <section
          className="release-subsection"
          aria-labelledby="credential-title"
        >
          <p className="model-label" id="credential-title">
            Provider credential
          </p>
          <strong>
            {credentials?.configured ? "Configured" : "Not configured"}
          </strong>
          <span className="model-meta">
            Source: {credentials?.credential_source ?? "checking"}
            {credentials?.environment_detected ? " · environment detected" : ""}
          </span>
          <div className="model-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() => void saveDetectedCredential()}
              disabled={
                controlsDisabled ||
                !credentials?.environment_detected ||
                !credentials.secure_store_available
              }
            >
              Save detected credential
            </button>
            <button
              type="button"
              className="text-button danger-text"
              onClick={() => void removeCredential()}
              disabled={controlsDisabled || !credentials?.configured}
            >
              Remove stored credential
            </button>
          </div>
        </section>

        <section
          className="release-subsection"
          aria-labelledby="diagnostics-title"
        >
          <p className="model-label" id="diagnostics-title">
            Diagnostics
          </p>
          <span className="model-meta">
            Metadata-only preview and ZIP export. No source text, secrets, or
            renderer paths.
          </span>
          <div className="model-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() => void previewDiagnostics()}
              disabled={controlsDisabled}
            >
              {busy === "diagnostic-preview"
                ? "Preparing preview…"
                : "Preview safe metadata"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void saveDiagnostics()}
              disabled={controlsDisabled}
            >
              {busy === "diagnostic-save" ? "Exporting…" : "Export ZIP…"}
            </button>
          </div>
          {diagnosticPreview ? (
            <div className="diagnostic-preview" role="status">
              <strong>Previewed sections</strong>
              <span>
                {Object.keys(diagnosticPreview)
                  .filter(
                    (key) => key !== "schema_version" && key !== "timestamp",
                  )
                  .join(" · ") || "none"}
              </span>
              <small>Schema {diagnosticPreview.schema_version}</small>
            </div>
          ) : null}
        </section>
      </div>

      <section className="release-reset" aria-labelledby="reset-title">
        <div>
          <p className="model-label" id="reset-title">
            Reset local data
          </p>
          <span className="model-meta">
            Removes projects, settings, logs, diagnostics, and stored
            credentials. Model caches are retained unless selected.
          </span>
        </div>
        <label className="reset-checkbox">
          <input
            type="checkbox"
            checked={removeModelCache}
            onChange={(event) => setRemoveModelCache(event.target.checked)}
            disabled={controlsDisabled}
          />
          Also remove model caches
        </label>
        <button
          type="button"
          className="danger-button"
          onClick={() => void resetLocalData()}
          disabled={controlsDisabled}
        >
          Reset Local Data…
        </button>
      </section>
      {notice ? (
        <p className="notice-message" role="status">
          {notice}
        </p>
      ) : null}
    </section>
  );
}
