import { useCallback, useEffect, useState } from "react";

import {
  isHealthResult,
  type CoreStatus,
  type EventEnvelope,
  type HealthResult,
  type ImportSourceResult,
  type ProjectSummary,
  type SourcePreviewResult,
  type SourceSummary,
} from "../shared/protocol";

const initialStatus: CoreStatus = {
  state: "starting",
  protocolVersion: null,
  coreVersion: null,
  health: null,
  error: null,
};

type ProjectListResult = { projects: ProjectSummary[] };
type ProjectResult = { project: ProjectSummary };
type SourceListResult = { sources: SourceSummary[] };

function errorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null) {
    const value = error as { code?: unknown; message?: unknown };
    if (typeof value.code === "string" && typeof value.message === "string")
      return `${value.code}: ${value.message}`;
    if (typeof value.message === "string") return value.message;
  }
  return "The request could not be completed.";
}

function payloadString(
  payload: Record<string, unknown>,
  key: string,
): string | null {
  return typeof payload[key] === "string" ? payload[key] : null;
}

export function App() {
  const [status, setStatus] = useState<CoreStatus>(initialStatus);
  const [health, setHealth] = useState<HealthResult | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedProject, setSelectedProject] = useState<ProjectSummary | null>(
    null,
  );
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [preview, setPreview] = useState<SourcePreviewResult | null>(null);
  const [projectName, setProjectName] = useState("");
  const [privacyMode, setPrivacyMode] = useState("local_only");
  const [stylePolicy, setStylePolicy] = useState("preserve_voice");
  const [customGuidance, setCustomGuidance] = useState("");
  const [newProjectName, setNewProjectName] = useState("Board proposal");
  const [importKind, setImportKind] = useState<"presentation" | "supporting">(
    "supporting",
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastEvent, setLastEvent] = useState("Waiting for core.ready");
  const [progress, setProgress] = useState<string | null>(null);
  const [healthState, setHealthState] = useState<"idle" | "checking" | "error">(
    "idle",
  );

  const checkHealth = useCallback(async () => {
    setHealthState("checking");
    try {
      const result =
        await window.presenterCopilot.core.request<HealthResult>("core.health");
      if (!isHealthResult(result))
        throw new Error("Core returned an invalid health payload.");
      setHealth(result);
      setHealthState("idle");
    } catch {
      setHealthState("error");
    }
  }, []);

  const loadProjects = useCallback(async () => {
    try {
      const result =
        await window.presenterCopilot.core.request<ProjectListResult>(
          "project.list",
        );
      setProjects(result.projects);
      setSelectedProject((current) =>
        current
          ? (result.projects.find((project) => project.id === current.id) ??
            null)
          : null,
      );
    } catch (error) {
      setNotice(errorMessage(error));
    }
  }, []);

  const loadSources = useCallback(async (projectId: string) => {
    const result = await window.presenterCopilot.core.request<SourceListResult>(
      "source.list",
      { project_id: projectId },
    );
    setSources(result.sources);
  }, []);

  useEffect(() => {
    let mounted = true;
    const removeStatusListener = window.presenterCopilot.core.onStatus(
      (nextStatus) => {
        if (!mounted) return;
        setStatus(nextStatus);
        if (nextStatus.health) setHealth(nextStatus.health);
        if (nextStatus.state === "ready") {
          setLastEvent((current) =>
            current === "Waiting for core.ready" ? "core.ready" : current,
          );
        }
      },
    );
    const removeEventListener = window.presenterCopilot.core.onEvent(
      (event: EventEnvelope) => {
        if (!mounted) return;
        setLastEvent(event.event);
        if (event.event === "source.import_progress") {
          const stage = payloadString(event.payload, "stage") ?? "working";
          const eventStatus =
            payloadString(event.payload, "status") ?? "working";
          setProgress(`${stage} · ${eventStatus}`);
          if (eventStatus === "complete" && stage === "complete")
            window.setTimeout(() => mounted && setProgress(null), 700);
        }
        if (event.event === "project.index_ready") setProgress(null);
      },
    );
    void window.presenterCopilot.core.getStatus().then((currentStatus) => {
      if (!mounted) return;
      setStatus(currentStatus);
      if (currentStatus.health) setHealth(currentStatus.health);
      if (currentStatus.state === "ready") setLastEvent("core.ready");
    });

    return () => {
      mounted = false;
      removeStatusListener();
      removeEventListener();
    };
  }, []);

  useEffect(() => {
    if (status.state === "ready") {
      void checkHealth();
      void loadProjects();
    }
  }, [checkHealth, loadProjects, status.state]);

  const selectProject = useCallback(
    async (project: ProjectSummary) => {
      setBusy("open-project");
      setNotice(null);
      try {
        const result =
          await window.presenterCopilot.core.request<ProjectResult>(
            "project.open",
            { project_id: project.id },
          );
        setSelectedProject(result.project);
        setProjectName(result.project.name);
        setPrivacyMode(result.project.privacy_mode);
        setStylePolicy(result.project.default_style_policy);
        setCustomGuidance(result.project.custom_style_guidance ?? "");
        setPreview(null);
        setSelectedSourceId(null);
        await loadSources(project.id);
      } catch (error) {
        setNotice(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadSources],
  );

  const createProject = useCallback(async () => {
    if (!newProjectName.trim()) return;
    setBusy("create-project");
    setNotice(null);
    try {
      const result = await window.presenterCopilot.core.request<ProjectResult>(
        "project.create",
        { name: newProjectName.trim() },
      );
      setSelectedProject(result.project);
      setProjectName(result.project.name);
      setPrivacyMode(result.project.privacy_mode);
      setStylePolicy(result.project.default_style_policy);
      setCustomGuidance(result.project.custom_style_guidance ?? "");
      setSources([]);
      setPreview(null);
      await loadProjects();
      setNotice("Project created in the local vault.");
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [loadProjects, newProjectName]);

  const saveSettings = useCallback(async () => {
    if (!selectedProject || !projectName.trim()) return;
    setBusy("save-settings");
    setNotice(null);
    try {
      const result = await window.presenterCopilot.core.request<ProjectResult>(
        "project.update_settings",
        {
          project_id: selectedProject.id,
          name: projectName.trim(),
          privacy_mode: privacyMode,
          default_style_policy: stylePolicy,
          custom_style_guidance: customGuidance,
        },
      );
      setSelectedProject(result.project);
      setProjectName(result.project.name);
      await loadProjects();
      setNotice("Project settings saved locally.");
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [
    customGuidance,
    loadProjects,
    privacyMode,
    projectName,
    selectedProject,
    stylePolicy,
  ]);

  const importSource = useCallback(async () => {
    if (!selectedProject) return;
    setBusy("import-source");
    setNotice(null);
    setProgress("snapshot · waiting for selection");
    try {
      const result: ImportSourceResult =
        await window.presenterCopilot.source.pickAndImport(
          selectedProject.id,
          importKind,
        );
      if (result.cancelled) {
        setProgress(null);
        return;
      }
      await loadSources(selectedProject.id);
      await loadProjects();
      if (result.document) {
        setNotice(
          `Imported ${result.document.original_name} · ${result.source_units_count ?? 0} units`,
        );
      }
    } catch (error) {
      setProgress(null);
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [importKind, loadProjects, loadSources, selectedProject]);

  const inspectSource = useCallback(
    async (source: SourceSummary) => {
      if (!selectedProject) return;
      setSelectedSourceId(source.id);
      setBusy(`preview-${source.id}`);
      setNotice(null);
      try {
        const result =
          await window.presenterCopilot.core.request<SourcePreviewResult>(
            "source.preview",
            {
              project_id: selectedProject.id,
              document_id: source.id,
              offset: 0,
              limit: 25,
            },
          );
        setPreview(result);
      } catch (error) {
        setNotice(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [selectedProject],
  );

  const reindexSource = useCallback(
    async (source: SourceSummary) => {
      if (!selectedProject) return;
      setBusy(`reindex-${source.id}`);
      setNotice(null);
      try {
        await window.presenterCopilot.core.request("source.reindex", {
          project_id: selectedProject.id,
          document_id: source.id,
        });
        await loadSources(selectedProject.id);
        setNotice(
          `Re-indexed ${source.original_name} from its stored snapshot.`,
        );
      } catch (error) {
        setNotice(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadSources, selectedProject],
  );

  const deleteSource = useCallback(
    async (source: SourceSummary) => {
      if (
        !selectedProject ||
        !window.confirm(`Delete ${source.original_name} from this project?`)
      )
        return;
      setBusy(`delete-${source.id}`);
      setNotice(null);
      try {
        await window.presenterCopilot.core.request("source.delete", {
          project_id: selectedProject.id,
          document_id: source.id,
        });
        setSources((current) =>
          current.filter((item) => item.id !== source.id),
        );
        await loadProjects();
        if (selectedSourceId === source.id) {
          setSelectedSourceId(null);
          setPreview(null);
        }
        setNotice(`Deleted ${source.original_name}.`);
      } catch (error) {
        setNotice(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadProjects, selectedProject, selectedSourceId],
  );

  const deleteProject = useCallback(async () => {
    if (
      !selectedProject ||
      !window.confirm(
        `Delete project “${selectedProject.name}” and all vault data?`,
      )
    )
      return;
    setBusy("delete-project");
    setNotice(null);
    try {
      await window.presenterCopilot.core.request("project.delete", {
        project_id: selectedProject.id,
      });
      setSelectedProject(null);
      setSources([]);
      setPreview(null);
      setSelectedSourceId(null);
      await loadProjects();
      setNotice("Project vault and registry entry deleted.");
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [loadProjects, selectedProject]);

  const statusLabel = status.state.toUpperCase();
  const healthLabel =
    healthState === "checking"
      ? "Checking…"
      : healthState === "error"
        ? "Unavailable"
        : (health?.status.toUpperCase() ?? "Not checked");

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Milestone 1 · local project vault</p>
          <h1>Presenter Copilot</h1>
          <p className="lede">
            Import presentation material, preserve its boundaries, and inspect
            every fact with its source.
          </p>
        </div>
        <div
          className={`status-pill status-${status.state}`}
          aria-label={`Core status: ${statusLabel}`}
        >
          <span aria-hidden="true" className="status-dot" />
          <span>CORE {statusLabel}</span>
        </div>
      </header>

      <section className="status-grid" aria-labelledby="status-title">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Local handshake</p>
            <h2 id="status-title">Core status</h2>
          </div>
          <span className="event-label" aria-live="polite">
            Last event: {lastEvent}
          </span>
        </div>
        <dl className="facts">
          <div>
            <dt>Protocol</dt>
            <dd>{status.protocolVersion ?? "—"}</dd>
          </div>
          <div>
            <dt>Core version</dt>
            <dd>{status.coreVersion ?? "—"}</dd>
          </div>
          <div>
            <dt>Health</dt>
            <dd>{healthLabel}</dd>
          </div>
          <div>
            <dt>Migration</dt>
            <dd>{status.state === "ready" ? "Ready" : "—"}</dd>
          </div>
        </dl>
        {status.error ? (
          <p className="error-message" role="alert">
            {status.error.code}: {status.error.message}
          </p>
        ) : null}
        <button
          type="button"
          className="secondary-button"
          onClick={() => void checkHealth()}
          disabled={healthState === "checking"}
        >
          {healthState === "checking" ? "Checking core…" : "Check Core Health"}
        </button>
      </section>

      <div className="workspace-grid">
        <aside className="panel project-panel" aria-labelledby="projects-title">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Vault registry</p>
              <h2 id="projects-title">Projects</h2>
            </div>
            <span className="count-badge">{projects.length}</span>
          </div>
          <div className="create-row">
            <input
              aria-label="New project name"
              value={newProjectName}
              onChange={(event) => setNewProjectName(event.target.value)}
              maxLength={120}
            />
            <button
              type="button"
              className="primary-button"
              onClick={() => void createProject()}
              disabled={busy !== null || status.state !== "ready"}
            >
              Create
            </button>
          </div>
          <div className="project-list">
            {projects.length === 0 ? (
              <p className="muted">No local projects yet.</p>
            ) : null}
            {projects.map((project) => (
              <button
                key={project.id}
                type="button"
                className={`project-item ${selectedProject?.id === project.id ? "selected" : ""}`}
                onClick={() => void selectProject(project)}
                disabled={busy !== null}
              >
                <span className="project-item-name">{project.name}</span>
                <span className="project-item-meta">
                  {project.source_count ?? 0} sources · {project.storage_status}
                </span>
              </button>
            ))}
          </div>
          <p className="boundary-note">
            The renderer never receives a filesystem path. Imports open a native
            main-process picker.
          </p>
        </aside>

        <section
          className="panel project-workspace"
          aria-labelledby="project-title"
        >
          {!selectedProject ? (
            <div className="empty-state">
              <p className="eyebrow">Choose a project</p>
              <h2 id="project-title">Create or open a local vault</h2>
              <p className="muted">
                Your project database and copied source snapshots stay under the
                application data root.
              </p>
            </div>
          ) : (
            <>
              <div className="section-heading">
                <div>
                  <p className="eyebrow">
                    Project Brain · local only by default
                  </p>
                  <h2 id="project-title">{selectedProject.name}</h2>
                </div>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => void deleteProject()}
                  disabled={busy !== null}
                >
                  Delete project
                </button>
              </div>

              <div className="settings-grid">
                <label>
                  Project name
                  <input
                    value={projectName}
                    onChange={(event) => setProjectName(event.target.value)}
                    maxLength={120}
                  />
                </label>
                <label>
                  Privacy mode
                  <select
                    value={privacyMode}
                    onChange={(event) => setPrivacyMode(event.target.value)}
                  >
                    <option value="local_only">Local only</option>
                    <option value="selected_context_cloud">
                      Selected context cloud
                    </option>
                    <option value="full_context_cloud">
                      Full context cloud
                    </option>
                  </select>
                </label>
                <label>
                  Style policy
                  <select
                    value={stylePolicy}
                    onChange={(event) => setStylePolicy(event.target.value)}
                  >
                    <option value="preserve_voice">Preserve my voice</option>
                    <option value="light_polish">Light polish</option>
                    <option value="executive_concise">Executive concise</option>
                    <option value="custom">Custom</option>
                  </select>
                </label>
                <label>
                  Custom guidance
                  <textarea
                    value={customGuidance}
                    onChange={(event) => setCustomGuidance(event.target.value)}
                    maxLength={4000}
                    rows={2}
                  />
                </label>
              </div>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void saveSettings()}
                disabled={busy !== null}
              >
                Save settings
              </button>

              <div className="source-heading section-heading">
                <div>
                  <p className="eyebrow">Snapshot → parse → chunk</p>
                  <h2>Sources</h2>
                </div>
                <div className="source-actions">
                  <select
                    aria-label="Import source kind"
                    value={importKind}
                    onChange={(event) =>
                      setImportKind(
                        event.target.value as "presentation" | "supporting",
                      )
                    }
                  >
                    <option value="presentation">Presentation</option>
                    <option value="supporting">Supporting document</option>
                  </select>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => void importSource()}
                    disabled={busy !== null}
                  >
                    Import source…
                  </button>
                </div>
              </div>
              {progress ? (
                <p className="progress-message" aria-live="polite">
                  Import progress: {progress}
                </p>
              ) : null}
              {notice ? (
                <p className="notice-message" role="status">
                  {notice}
                </p>
              ) : null}
              <div className="source-list">
                {sources.length === 0 ? (
                  <p className="muted">
                    No sources imported. Add the canonical PPTX, PDF, and
                    Markdown fixtures to inspect provenance.
                  </p>
                ) : null}
                {sources.map((source) => (
                  <div
                    key={source.id}
                    className={`source-item ${selectedSourceId === source.id ? "selected" : ""}`}
                  >
                    <button
                      type="button"
                      className="source-main"
                      onClick={() => void inspectSource(source)}
                      disabled={busy !== null}
                    >
                      <span className="source-name">
                        {source.original_name}
                      </span>
                      <span className="source-meta">
                        {source.source_type.toUpperCase()} ·{" "}
                        {source.parse_status} · {source.source_units_count}{" "}
                        units · {source.chunks_count} chunks
                      </span>
                    </button>
                    <div className="source-item-actions">
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => void reindexSource(source)}
                        disabled={busy !== null}
                      >
                        Re-index
                      </button>
                      <button
                        type="button"
                        className="text-button danger-text"
                        onClick={() => void deleteSource(source)}
                        disabled={busy !== null}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {preview ? (
                <section className="preview" aria-labelledby="preview-title">
                  <div className="section-heading compact">
                    <div>
                      <p className="eyebrow">Bounded source preview</p>
                      <h2 id="preview-title">
                        {preview.document.original_name}
                      </h2>
                    </div>
                    <span className="count-badge">{preview.total} units</span>
                  </div>
                  {preview.units.map((unit) => {
                    const label =
                      typeof unit.provenance.label === "string"
                        ? unit.provenance.label
                        : "Source unit";
                    const notes =
                      typeof unit.metadata.notes === "string"
                        ? unit.metadata.notes
                        : null;
                    return (
                      <article className="unit-card" key={unit.id}>
                        <div className="unit-heading">
                          <span>{label}</span>
                          {unit.title ? <strong>{unit.title}</strong> : null}
                        </div>
                        <pre>
                          {unit.text || "(No extractable text on this unit)"}
                        </pre>
                        {notes ? (
                          <div className="notes">
                            <span>Speaker notes</span>
                            <p>{notes}</p>
                          </div>
                        ) : null}
                      </article>
                    );
                  })}
                </section>
              ) : null}
            </>
          )}
        </section>
      </div>
    </main>
  );
}
