import { useCallback, useEffect, useState } from "react";

import {
  isHealthResult,
  type CoreStatus,
  type EventEnvelope,
  type HealthResult,
  type JsonObject,
  type ProjectSummary,
  type ReadyProjectSummary,
  type RetrievalHealthResult,
  type RetrievalQueryResult,
  type RendererCoreMethod,
  type SourcePreviewResult,
  type SourceSummary,
  unwrapInvokeResult,
} from "../shared/protocol";
import { AudiencePanel } from "./AudiencePanel";
import { ChallengePanel } from "./ChallengePanel";
import { LiveAssistPanel } from "./LiveAssistPanel";
import { ReleaseControls } from "./ReleaseControls";
import { RunPanel } from "./RunPanel";
import { TeachPanel } from "./TeachPanel";
import {
  requiresTranscriptDisclosure,
  type SourceImportKind,
} from "./transcript-import-gate";

import {
  WorkspaceChrome,
  ProjectOverview,
  SetupGuide,
} from "./WorkspaceChrome";
import { Modal } from "./Modal";
import { Walkthrough } from "./Walkthrough";
import { WorkspaceIcon } from "./WorkspaceIcon";
import {
  canNavigate,
  projectViews,
  needsWalkthrough,
  rememberWalkthrough,
  walkthroughKey,
  type WorkspaceView,
} from "./workspace-navigation";

const initialStatus: CoreStatus = {
  state: "starting",
  protocolVersion: null,
  coreVersion: null,
  health: null,
  error: null,
};

type ProjectListResult = { projects: ProjectSummary[] };
type ProjectResult = { project: ReadyProjectSummary };
type SourceListResult = { sources: SourceSummary[] };

function requestCore<T>(
  method: RendererCoreMethod,
  params?: JsonObject,
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

function payloadString(
  payload: Record<string, unknown>,
  key: string,
): string | null {
  return typeof payload[key] === "string" ? payload[key] : null;
}

function optionalInteger(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : undefined;
}

function formatTimestamp(value: number | null): string | null {
  if (value === null) return null;
  const totalSeconds = Math.floor(value / 1000);
  const milliseconds = value % 1000;
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(milliseconds).padStart(3, "0")}`;
}

export function App() {
  const [view, setView] = useState<WorkspaceView>("home");
  const [createOpen, setCreateOpen] = useState(false);
  const [tourOpen, setTourOpen] = useState(() => {
    try {
      return needsWalkthrough(window.localStorage);
    } catch {
      return true;
    }
  });
  const [status, setStatus] = useState<CoreStatus>(initialStatus);
  const [health, setHealth] = useState<HealthResult | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedProject, setSelectedProject] = useState<ProjectSummary | null>(
    null,
  );
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [audienceRefreshToken, setAudienceRefreshToken] = useState(0);
  const refreshAudiencePanels = useCallback(() => {
    setAudienceRefreshToken((value) => value + 1);
  }, []);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [preview, setPreview] = useState<SourcePreviewResult | null>(null);
  const [projectName, setProjectName] = useState("");
  const [privacyMode, setPrivacyMode] = useState("local_only");
  const [stylePolicy, setStylePolicy] = useState("preserve_voice");
  const [customGuidance, setCustomGuidance] = useState("");
  const [styleOverrideEnabled, setStyleOverrideEnabled] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [importKind, setImportKind] = useState<SourceImportKind>("supporting");
  const [transcriptDisclosureOpen, setTranscriptDisclosureOpen] =
    useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastEvent, setLastEvent] = useState("Waiting for core.ready");
  const [progress, setProgress] = useState<string | null>(null);
  const [progressKind, setProgressKind] = useState<"import" | "semantic">(
    "import",
  );
  const [healthState, setHealthState] = useState<"idle" | "checking" | "error">(
    "idle",
  );
  const [retrievalHealth, setRetrievalHealth] =
    useState<RetrievalHealthResult | null>(null);
  const [retrievalQuery, setRetrievalQuery] = useState("What is the RTO?");
  const [retrievalLimit, setRetrievalLimit] = useState("5");
  const [currentSlide, setCurrentSlide] = useState("");
  const [slideWindow, setSlideWindow] = useState("1");
  const [retrievalSourceType, setRetrievalSourceType] = useState("");
  const [retrievalResult, setRetrievalResult] =
    useState<RetrievalQueryResult | null>(null);
  const [runPanelActive, setRunPanelActive] = useState(false);
  const [livePanelActive, setLivePanelActive] = useState(false);
  const [teachVoiceActive, setTeachVoiceActive] = useState(false);
  const runActive = runPanelActive || livePanelActive;
  const workspaceCaptureActive = runActive || teachVoiceActive;

  const navigate = (next: WorkspaceView) => {
    if (canNavigate(next, runPanelActive, livePanelActive, teachVoiceActive))
      setView(next);
  };
  const closeTour = () => {
    try {
      rememberWalkthrough(window.localStorage);
    } catch {
      /* Storage can be unavailable. */
    }
    setTourOpen(false);
  };

  const checkHealth = useCallback(async () => {
    setHealthState("checking");
    try {
      const result = await requestCore<HealthResult>("core.health");
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
      const result = await requestCore<ProjectListResult>("project.list");
      setProjects(result.projects);
      setSelectedProject((current) =>
        current
          ? (() => {
              const project = result.projects.find(
                (candidate) => candidate.id === current.id,
              );
              return project?.storage_status === "ready" ? project : null;
            })()
          : null,
      );
    } catch (error) {
      setNotice(errorMessage(error));
    }
  }, []);

  const loadSources = useCallback(async (projectId: string) => {
    const result = await requestCore<SourceListResult>("source.list", {
      project_id: projectId,
    });
    setSources(result.sources);
  }, []);

  const loadRetrievalHealth = useCallback(async (projectId: string) => {
    if (!import.meta.env.DEV) return;
    try {
      const result = await requestCore<RetrievalHealthResult>(
        "retrieval.health",
        {
          project_id: projectId,
        },
      );
      setRetrievalHealth(result);
    } catch (error) {
      setRetrievalHealth(null);
      setNotice(errorMessage(error));
    }
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
          setProgressKind("import");
          setProgress(`${stage} · ${eventStatus}`);
          if (eventStatus === "complete" && stage === "complete")
            window.setTimeout(() => mounted && setProgress(null), 700);
        }
        if (event.event === "project.index_progress") {
          const stage = payloadString(event.payload, "stage") ?? "working";
          const eventStatus =
            payloadString(event.payload, "status") ?? "working";
          setProgressKind(stage === "lexical" ? "import" : "semantic");
          setProgress(`${stage} · ${eventStatus}`);
          if (eventStatus === "complete" && stage === "complete")
            window.setTimeout(() => mounted && setProgress(null), 700);
        }
        if (event.event === "project.index_ready") {
          setProgress(null);
          const projectId = payloadString(event.payload, "project_id");
          const indexKind = payloadString(event.payload, "index_kind");
          if (
            projectId &&
            (indexKind === "hybrid" || indexKind === "knowledge_item")
          )
            void loadRetrievalHealth(projectId);
        }
      },
    );
    void window.presenterCopilot.core
      .getStatus()
      .then(unwrapInvokeResult)
      .then((currentStatus) => {
        if (!mounted) return;
        setStatus(currentStatus);
        if (currentStatus.health) setHealth(currentStatus.health);
        if (currentStatus.state === "ready") setLastEvent("core.ready");
      })
      .catch((error) => {
        if (mounted) setNotice(errorMessage(error));
      });

    return () => {
      mounted = false;
      removeStatusListener();
      removeEventListener();
    };
  }, [loadRetrievalHealth]);

  useEffect(() => {
    if (status.state === "ready") {
      void checkHealth();
      void loadProjects();
    }
  }, [checkHealth, loadProjects, status.state]);

  const selectProject = useCallback(
    async (project: ProjectSummary) => {
      if (workspaceCaptureActive) return;
      if (selectedProject?.id === project.id) {
        setView("overview");
        return;
      }
      setBusy("open-project");
      setNotice(null);
      try {
        const result = await requestCore<ProjectResult>("project.open", {
          project_id: project.id,
        });
        setSelectedProject(result.project);
        setView("overview");
        setProjectName(result.project.name);
        setPrivacyMode(result.project.privacy_mode);
        setStylePolicy(result.project.default_style_policy);
        setCustomGuidance(result.project.custom_style_guidance ?? "");
        setStyleOverrideEnabled(result.project.style_override_enabled);
        setPreview(null);
        setSelectedSourceId(null);
        setRetrievalResult(null);
        await loadSources(project.id);
        await loadRetrievalHealth(project.id);
      } catch (error) {
        setNotice(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadRetrievalHealth, loadSources, selectedProject, workspaceCaptureActive],
  );

  const createProject = useCallback(async () => {
    if (workspaceCaptureActive || !newProjectName.trim()) return;
    setBusy("create-project");
    setNotice(null);
    try {
      const result = await requestCore<ProjectResult>("project.create", {
        name: newProjectName.trim(),
      });
      setSelectedProject(result.project);
      setProjectName(result.project.name);
      setPrivacyMode(result.project.privacy_mode);
      setStylePolicy(result.project.default_style_policy);
      setCustomGuidance(result.project.custom_style_guidance ?? "");
      setStyleOverrideEnabled(result.project.style_override_enabled);
      setSources([]);
      setPreview(null);
      setRetrievalResult(null);
      await loadProjects();
      await loadRetrievalHealth(result.project.id);
      setCreateOpen(false);
      setNewProjectName("");
      setView("sources");
      setNotice(
        "Project created. Add your presentation or supporting material to get started.",
      );
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [
    loadProjects,
    loadRetrievalHealth,
    newProjectName,
    workspaceCaptureActive,
  ]);

  const saveSettings = useCallback(async () => {
    if (workspaceCaptureActive || !selectedProject || !projectName.trim())
      return;
    setBusy("save-settings");
    setNotice(null);
    try {
      const result = await requestCore<ProjectResult>(
        "project.update_settings",
        {
          project_id: selectedProject.id,
          name: projectName.trim(),
          privacy_mode: privacyMode,
          default_style_policy: stylePolicy,
          custom_style_guidance: customGuidance,
          style_override_enabled: styleOverrideEnabled,
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
    styleOverrideEnabled,
    workspaceCaptureActive,
  ]);

  const importSource = useCallback(
    async (transcriptAuthorized = false) => {
      if (workspaceCaptureActive || !selectedProject) return;
      if (requiresTranscriptDisclosure(importKind, transcriptAuthorized)) {
        setTranscriptDisclosureOpen(true);
        return;
      }
      setBusy("import-source");
      setNotice(null);
      setProgressKind("import");
      setProgress("snapshot · waiting for selection");
      try {
        const result = await window.presenterCopilot.source
          .pickAndImport(selectedProject.id, importKind)
          .then(unwrapInvokeResult);
        if (result.cancelled) {
          setProgress(null);
          return;
        }
        await loadSources(selectedProject.id);
        setAudienceRefreshToken((value) => value + 1);
        await loadProjects();
        await loadRetrievalHealth(selectedProject.id);
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
    },
    [
      importKind,
      loadProjects,
      loadRetrievalHealth,
      loadSources,
      workspaceCaptureActive,
      selectedProject,
    ],
  );

  const continueTranscriptImport = useCallback(() => {
    setTranscriptDisclosureOpen(false);
    void importSource(true);
  }, [importSource]);

  const inspectSource = useCallback(
    async (source: SourceSummary) => {
      if (workspaceCaptureActive || !selectedProject) return;
      setSelectedSourceId(source.id);
      setBusy(`preview-${source.id}`);
      setNotice(null);
      try {
        const result = await requestCore<SourcePreviewResult>(
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
    [selectedProject, workspaceCaptureActive],
  );

  const reindexSource = useCallback(
    async (source: SourceSummary) => {
      if (workspaceCaptureActive || !selectedProject) return;
      setBusy(`reindex-${source.id}`);
      setNotice(null);
      try {
        await requestCore("source.reindex", {
          project_id: selectedProject.id,
          document_id: source.id,
        });
        await loadSources(selectedProject.id);
        setAudienceRefreshToken((value) => value + 1);
        await loadRetrievalHealth(selectedProject.id);
        setNotice(
          `Re-indexed ${source.original_name} from its stored snapshot.`,
        );
      } catch (error) {
        setNotice(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadRetrievalHealth, loadSources, selectedProject, workspaceCaptureActive],
  );

  const deleteSource = useCallback(
    async (source: SourceSummary) => {
      if (
        workspaceCaptureActive ||
        !selectedProject ||
        !window.confirm(`Delete ${source.original_name} from this project?`)
      )
        return;
      setBusy(`delete-${source.id}`);
      setNotice(null);
      try {
        await requestCore("source.delete", {
          project_id: selectedProject.id,
          document_id: source.id,
        });
        setSources((current) =>
          current.filter((item) => item.id !== source.id),
        );
        setAudienceRefreshToken((value) => value + 1);
        await loadProjects();
        await loadRetrievalHealth(selectedProject.id);
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
    [
      loadProjects,
      loadRetrievalHealth,
      workspaceCaptureActive,
      selectedProject,
      selectedSourceId,
    ],
  );

  const deleteProject = useCallback(async () => {
    if (
      workspaceCaptureActive ||
      !selectedProject ||
      !window.confirm(
        `Delete project “${selectedProject.name}” and all vault data?`,
      )
    )
      return;
    setBusy("delete-project");
    setNotice(null);
    try {
      await requestCore("project.delete", {
        project_id: selectedProject.id,
      });
      setSelectedProject(null);
      setSources([]);
      setPreview(null);
      setSelectedSourceId(null);
      setRetrievalHealth(null);
      setRetrievalResult(null);
      await loadProjects();
      setNotice("Project vault and registry entry deleted.");
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [loadProjects, selectedProject, workspaceCaptureActive]);

  const rebuildRetrieval = useCallback(async () => {
    if (!selectedProject) return;
    setBusy("retrieval-rebuild");
    setNotice(null);
    setProgressKind("semantic");
    setProgress("model_load · started");
    try {
      await requestCore("retrieval.rebuild", {
        project_id: selectedProject.id,
      });
      await loadRetrievalHealth(selectedProject.id);
      setNotice("Semantic index rebuilt locally.");
    } catch (error) {
      setProgress(null);
      setNotice(errorMessage(error));
      await loadRetrievalHealth(selectedProject.id);
    } finally {
      setBusy(null);
    }
  }, [loadRetrievalHealth, selectedProject]);

  const runRetrievalQuery = useCallback(async () => {
    if (!selectedProject || !retrievalQuery.trim()) return;
    const limit = optionalInteger(retrievalLimit);
    const slide = optionalInteger(currentSlide);
    const window = optionalInteger(slideWindow);
    if (limit === undefined || limit < 1) {
      setNotice("Result limit must be a positive integer.");
      return;
    }
    if (currentSlide.trim() && (slide === undefined || slide < 1)) {
      setNotice("Current slide must be a positive integer.");
      return;
    }
    if (slideWindow.trim() && (window === undefined || window < 0)) {
      setNotice("Slide window must be a non-negative integer.");
      return;
    }
    setBusy("retrieval-query");
    setNotice(null);
    try {
      const params: JsonObject = {
        project_id: selectedProject.id,
        query: retrievalQuery,
        limit,
      };
      if (slide !== undefined) params.current_slide = slide;
      if (window !== undefined) params.slide_window = window;
      if (retrievalSourceType) params.source_types = [retrievalSourceType];
      setRetrievalResult(
        await requestCore<RetrievalQueryResult>("retrieval.query", params),
      );
    } catch (error) {
      setNotice(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [
    currentSlide,
    retrievalLimit,
    retrievalQuery,
    retrievalSourceType,
    selectedProject,
    slideWindow,
  ]);

  const healthLabel =
    healthState === "checking"
      ? "Checking…"
      : healthState === "error"
        ? "Unavailable"
        : (health?.status.toUpperCase() ?? "Not checked");

  const handleResetComplete = useCallback(() => {
    try {
      window.localStorage.removeItem(walkthroughKey);
    } catch {
      /* Preferences may be unavailable. */
    }
    setTourOpen(true);
    setSelectedProject(null);
    setView("home");
    setSources([]);
    setPreview(null);
    setSelectedSourceId(null);
    setRetrievalHealth(null);
    setRetrievalResult(null);
    void loadProjects();
  }, [loadProjects]);

  return (
    <WorkspaceChrome
      view={view}
      onNavigate={navigate}
      projects={projects}
      project={selectedProject}
      status={status}
      busy={busy !== null}
      runActive={runPanelActive}
      liveActive={livePanelActive}
      teachVoiceActive={teachVoiceActive}
      onCreate={() => {
        setNotice(null);
        setCreateOpen(true);
      }}
      onOpen={(project) => void selectProject(project)}
      onTour={() => setTourOpen(true)}
    >
      {notice ? (
        <div className="workspace-notice" role="status">
          <span>{notice}</span>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setNotice(null)}
          >
            <WorkspaceIcon name="close" size={16} />
          </button>
        </div>
      ) : null}
      {status.error && view !== "setup" ? (
        <p className="error-message" role="alert">
          {status.error.message} Open Setup & settings to check core health.
        </p>
      ) : null}
      <div hidden={view !== "setup"} className="setup-view">
        <SetupGuide
          hasProject={selectedProject !== null}
          onNavigate={navigate}
          onCreate={() => setCreateOpen(true)}
          onTour={() => setTourOpen(true)}
        />
        <ReleaseControls
          visible={view === "setup"}
          coreReady={status.state === "ready"}
          runActive={workspaceCaptureActive}
          onResetComplete={handleResetComplete}
        />
        <details className="core-details">
          <summary>Core health & troubleshooting</summary>
          <section className="status-grid" aria-labelledby="status-title">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Troubleshooting</p>
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
              {healthState === "checking"
                ? "Checking core…"
                : "Check Core Health"}
            </button>
          </section>
        </details>
      </div>
      <section
        hidden={view === "home" || view === "setup"}
        className="panel project-workspace"
        aria-labelledby="project-title"
      >
        {!selectedProject ? (
          <div className="empty-state">
            <p className="eyebrow">Choose a project</p>
            <h2 id="project-title">Choose your next presentation</h2>
            <p className="muted">
              Create a project from the sidebar, or open an existing
              presentation.
            </p>
          </div>
        ) : (
          <>
            <div className="page-heading">
              <p className="eyebrow">
                {selectedProject.storage_status === "ready" &&
                selectedProject.privacy_mode === "local_only"
                  ? "LOCAL ONLY"
                  : "CLOUD CONTEXT ENABLED"}{" "}
                · {sources.length} SOURCES
              </p>
              <h1>
                {view === "overview"
                  ? selectedProject.name
                  : projectViews.find((item) => item.id === view)?.label}
              </h1>
              <p>
                {projectViews.find((item) => item.id === view)?.description}
              </p>
            </div>
            <div hidden={view !== "overview"}>
              <ProjectOverview
                sourceCount={sources.length}
                onNavigate={navigate}
              />
            </div>
            <div hidden={view !== "project-settings"}>
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Presentation preferences</p>
                  <h2 id="project-title">{selectedProject.name}</h2>
                </div>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => void deleteProject()}
                  disabled={busy !== null || workspaceCaptureActive}
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
                <label className="settings-guidance">
                  Custom guidance
                  <textarea
                    value={customGuidance}
                    onChange={(event) => setCustomGuidance(event.target.value)}
                    maxLength={4000}
                    rows={2}
                  />
                </label>
                <label className="settings-checkbox">
                  <input
                    type="checkbox"
                    checked={styleOverrideEnabled}
                    onChange={(event) =>
                      setStyleOverrideEnabled(event.target.checked)
                    }
                  />
                  Use this project style override before the global Speaker
                  Profile
                </label>
              </div>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void saveSettings()}
                disabled={busy !== null || workspaceCaptureActive}
              >
                Save settings
              </button>
            </div>
            <div hidden={view !== "run"}>
              {selectedProject.storage_status === "ready" ? (
                <RunPanel
                  visible={view === "run"}
                  project={selectedProject}
                  blocked={livePanelActive || teachVoiceActive}
                  onActiveChange={setRunPanelActive}
                />
              ) : null}
            </div>
            <div hidden={view !== "live"}>
              {selectedProject.storage_status === "ready" ? (
                <LiveAssistPanel
                  visible={view === "live"}
                  project={selectedProject}
                  blocked={runPanelActive || teachVoiceActive}
                  onActiveChange={setLivePanelActive}
                />
              ) : null}
            </div>
            <div hidden={view !== "teach"}>
              {selectedProject.storage_status === "ready" ? (
                <TeachPanel
                  project={selectedProject}
                  captureActive={runActive}
                  onVoiceActiveChange={setTeachVoiceActive}
                />
              ) : null}
            </div>
            <div hidden={view !== "challenge"}>
              {selectedProject.storage_status === "ready" ? (
                <ChallengePanel
                  project={selectedProject}
                  refreshToken={audienceRefreshToken}
                  captureActive={workspaceCaptureActive}
                />
              ) : null}
            </div>
            <div hidden={view !== "sources"}>
              <div className="source-heading section-heading">
                <div>
                  <p className="eyebrow">Your project library</p>
                  <h2>Sources</h2>
                </div>
                <div className="source-actions">
                  <select
                    aria-label="Import source kind"
                    value={importKind}
                    onChange={(event) =>
                      setImportKind(
                        event.target.value as
                          "presentation" | "supporting" | "transcript",
                      )
                    }
                    disabled={busy !== null || workspaceCaptureActive}
                  >
                    <option value="presentation">Presentation</option>
                    <option value="supporting">Supporting document</option>
                    <option value="transcript">Authorized transcript</option>
                  </select>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => void importSource()}
                    disabled={busy !== null || workspaceCaptureActive}
                  >
                    Import source…
                  </button>
                </div>
              </div>
              {progress ? (
                <p className="progress-message" aria-live="polite">
                  {progressKind === "semantic"
                    ? "Semantic index progress"
                    : "Import progress"}
                  : {progress}
                </p>
              ) : null}
              <div className="source-list">
                {sources.length === 0 ? (
                  <p className="muted">
                    Add a presentation, supporting notes, or an authorized
                    transcript. Choose the source type above, then select Import
                    source.
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
                      disabled={busy !== null || workspaceCaptureActive}
                    >
                      <span className="source-name">
                        {source.original_name}
                      </span>
                      <span className="source-meta">
                        {source.source_type.toUpperCase()} ·{" "}
                        {source.parse_status.replaceAll("_", " ")} ·{" "}
                        {source.source_units_count}{" "}
                        {source.source_type === "pptx"
                          ? "slides"
                          : source.source_type === "pdf"
                            ? "pages"
                            : source.kind === "transcript"
                              ? "segments"
                              : "sections"}
                      </span>
                    </button>
                    <div className="source-item-actions">
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => void reindexSource(source)}
                        disabled={busy !== null || workspaceCaptureActive}
                      >
                        Re-index
                      </button>
                      <button
                        type="button"
                        className="text-button danger-text"
                        onClick={() => void deleteSource(source)}
                        disabled={busy !== null || workspaceCaptureActive}
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
                      <p className="eyebrow">Source preview</p>
                      <h2 id="preview-title">
                        {preview.document.original_name}
                      </h2>
                    </div>
                    <span className="count-badge">{preview.total} units</span>
                  </div>
                  {preview.units.map((unit) => {
                    const transcriptPreview =
                      preview.document.kind === "transcript";
                    const start = formatTimestamp(unit.start_ms);
                    const end = formatTimestamp(unit.end_ms);
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
                          {transcriptPreview ? (
                            <span className="transcript-cue-heading">
                              {start
                                ? `${start}${end ? `–${end}` : ""}`
                                : `Segment ${unit.ordinal ?? "—"}`}
                              <strong>
                                {unit.speaker_label ?? "Unlabeled speaker"}
                              </strong>
                            </span>
                          ) : (
                            <span>{label}</span>
                          )}
                          {unit.title ? <strong>{unit.title}</strong> : null}
                        </div>
                        {transcriptPreview ? (
                          <p className="transcript-provenance-label">{label}</p>
                        ) : null}
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
            </div>
            <div hidden={view !== "audience"}>
              {selectedProject.storage_status === "ready" ? (
                <AudiencePanel
                  project={selectedProject}
                  refreshToken={audienceRefreshToken}
                  onAudienceChange={refreshAudiencePanels}
                />
              ) : null}
            </div>
            {import.meta.env.DEV && view === "project-settings" ? (
              <section
                className="retrieval-inspector"
                aria-labelledby="retrieval-inspector-title"
              >
                <div className="section-heading compact">
                  <div>
                    <p className="eyebrow">
                      Developer diagnostics · local only
                    </p>
                    <h2 id="retrieval-inspector-title">Retrieval inspector</h2>
                  </div>
                  <span className="count-badge">M2 · M3</span>
                </div>
                <p className="inspector-note">
                  Semantic retrieval is derived project data. Queries never
                  download a model or read source files directly.
                </p>
                <div className="retrieval-health-grid">
                  <div>
                    <span>Status</span>
                    <strong>{retrievalHealth?.status ?? "not checked"}</strong>
                  </div>
                  <div>
                    <span>Coverage</span>
                    <strong>
                      {retrievalHealth
                        ? `${Math.round(retrievalHealth.semantic_coverage * 100)}%`
                        : "—"}
                    </strong>
                  </div>
                  <div>
                    <span>Model</span>
                    <strong>
                      {retrievalHealth?.model_available
                        ? "available"
                        : "offline / missing"}
                    </strong>
                  </div>
                  <div>
                    <span>Dimensions</span>
                    <strong>{retrievalHealth?.dimension ?? "—"}</strong>
                  </div>
                  <div>
                    <span>Indexed entities</span>
                    <strong>
                      {retrievalHealth
                        ? `${retrievalHealth.current_indexed_mappings} / ${retrievalHealth.current_indexable_entity_count}`
                        : "—"}
                    </strong>
                  </div>
                  <div>
                    <span>Knowledge items</span>
                    <strong>
                      {retrievalHealth?.current_knowledge_item_count ?? "—"}
                    </strong>
                  </div>
                  <div>
                    <span>Generation</span>
                    <strong>
                      {retrievalHealth?.active_generation_id
                        ? retrievalHealth.active_generation_id.slice(0, 8)
                        : "not built"}
                    </strong>
                  </div>
                </div>
                {retrievalHealth?.stale_reason ? (
                  <p className="inspector-warning" role="status">
                    {retrievalHealth.stale_reason}
                  </p>
                ) : null}
                <div className="retrieval-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => void loadRetrievalHealth(selectedProject.id)}
                    disabled={busy !== null || workspaceCaptureActive}
                  >
                    Refresh health
                  </button>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => void rebuildRetrieval()}
                    disabled={busy !== null || workspaceCaptureActive}
                  >
                    {busy === "retrieval-rebuild"
                      ? "Building index…"
                      : "Build / rebuild index"}
                  </button>
                </div>
                <div className="retrieval-query-form">
                  <label className="retrieval-query-field">
                    Query
                    <textarea
                      value={retrievalQuery}
                      onChange={(event) =>
                        setRetrievalQuery(event.target.value)
                      }
                      rows={2}
                      maxLength={500}
                    />
                  </label>
                  <label>
                    Limit
                    <input
                      inputMode="numeric"
                      value={retrievalLimit}
                      onChange={(event) =>
                        setRetrievalLimit(event.target.value)
                      }
                    />
                  </label>
                  <label>
                    Current slide
                    <input
                      inputMode="numeric"
                      placeholder="optional"
                      value={currentSlide}
                      onChange={(event) => setCurrentSlide(event.target.value)}
                    />
                  </label>
                  <label>
                    Slide window
                    <input
                      inputMode="numeric"
                      value={slideWindow}
                      onChange={(event) => setSlideWindow(event.target.value)}
                    />
                  </label>
                  <label>
                    Source type
                    <select
                      value={retrievalSourceType}
                      onChange={(event) =>
                        setRetrievalSourceType(event.target.value)
                      }
                    >
                      <option value="">all types</option>
                      <option value="pptx">PPTX</option>
                      <option value="pdf">PDF</option>
                      <option value="markdown">Markdown</option>
                      <option value="txt">Text</option>
                    </select>
                  </label>
                  <button
                    type="button"
                    className="secondary-button retrieval-query-button"
                    onClick={() => void runRetrievalQuery()}
                    disabled={busy !== null || workspaceCaptureActive}
                  >
                    {busy === "retrieval-query" ? "Querying…" : "Run query"}
                  </button>
                </div>
                {retrievalResult ? (
                  <div className="retrieval-results">
                    <div className="retrieval-result-summary">
                      <span>
                        Mode <strong>{retrievalResult.mode}</strong>
                      </span>
                      <span>
                        Latency{" "}
                        <strong>
                          {retrievalResult.latency_ms.toFixed(1)} ms
                        </strong>
                      </span>
                      <span>
                        Hits <strong>{retrievalResult.hits.length}</strong>
                      </span>
                    </div>
                    {retrievalResult.hits.map((hit) => (
                      <article
                        className="retrieval-hit"
                        key={hit.evidence.evidence_id}
                      >
                        <div className="retrieval-hit-heading">
                          <strong>{hit.evidence.label}</strong>
                          <span>{hit.scores.final.toFixed(3)}</span>
                        </div>
                        <p>{hit.evidence.text}</p>
                        <div className="retrieval-score-line">
                          <span>semantic {hit.scores.semantic.toFixed(3)}</span>
                          <span>lexical {hit.scores.lexical.toFixed(3)}</span>
                          <span>slide {hit.scores.slide_boost.toFixed(3)}</span>
                          <span>{hit.reasons.join(" · ") || "candidate"}</span>
                        </div>
                      </article>
                    ))}
                    {retrievalResult.conflicts.map((conflict, index) => (
                      <div
                        className="inspector-warning conflict-warning"
                        key={`${conflict.subject}-${index}`}
                        role="alert"
                      >
                        <strong>
                          Potential source conflict: {conflict.subject}
                        </strong>
                        <span>
                          {conflict.values
                            .map((value) => value.normalized_value)
                            .join(" · ")}
                        </span>
                        <small>
                          {conflict.evidence
                            .map((item) => item.label)
                            .join(" · ")}
                        </small>
                      </div>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}
          </>
        )}
      </section>
      {createOpen ? (
        <Modal
          titleId="create-project-title"
          onClose={() => {
            if (busy === null) setCreateOpen(false);
          }}
        >
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void createProject();
            }}
          >
            <div className="dialog-heading">
              <span className="card-icon lavender">
                <WorkspaceIcon name="folder" />
              </span>
              <button
                type="button"
                className="icon-button"
                aria-label="Close new project"
                disabled={busy !== null}
                onClick={() => setCreateOpen(false)}
              >
                <WorkspaceIcon name="close" />
              </button>
            </div>
            <h2 id="create-project-title">What are you presenting?</h2>
            <p>
              Give your project a name. Add your deck and supporting material
              next.
            </p>
            <label className="dialog-label">
              Project name
              <input
                autoFocus
                aria-label="New project name"
                placeholder="e.g. Quarterly strategy review"
                value={newProjectName}
                onChange={(event) => setNewProjectName(event.target.value)}
                maxLength={120}
                disabled={busy !== null}
              />
            </label>
            <p className="privacy-hint">
              <WorkspaceIcon name="shield" size={16} />
              Starts in Local Only, with Preserve my voice.
            </p>
            {notice ? <p role="status">{notice}</p> : null}
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                disabled={busy !== null}
                onClick={() => setCreateOpen(false)}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="primary-button"
                disabled={
                  busy !== null ||
                  workspaceCaptureActive ||
                  status.state !== "ready" ||
                  !newProjectName.trim()
                }
              >
                {busy === "create-project" ? "Creating…" : "Create project"}
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
      {tourOpen ? (
        <Walkthrough
          onClose={closeTour}
          onSetup={() => {
            closeTour();
            navigate("setup");
          }}
        />
      ) : null}
      {transcriptDisclosureOpen ? (
        <Modal
          titleId="transcript-disclosure-title"
          onClose={() => setTranscriptDisclosureOpen(false)}
        >
          <p className="eyebrow">Before transcript import</p>
          <h2 id="transcript-disclosure-title">
            Confirm you are authorized to use this transcript
          </h2>
          <p>
            Only analyze recordings or transcripts you are authorized to use.
            Local processing does not change your legal or organizational
            obligations.
          </p>
          <div className="modal-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() => setTranscriptDisclosureOpen(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={continueTranscriptImport}
            >
              Continue to file picker
            </button>
          </div>
        </Modal>
      ) : null}
    </WorkspaceChrome>
  );
}
