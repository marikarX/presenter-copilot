import { useEffect, useRef, useState, type ReactNode } from "react";
import type { CoreStatus, ProjectSummary } from "../shared/protocol";
import { WorkspaceIcon as Icon } from "./WorkspaceIcon";
import {
  projectViews,
  type WorkspaceView,
  canNavigate,
} from "./workspace-navigation";

interface Props {
  view: WorkspaceView;
  onNavigate: (view: WorkspaceView) => void;
  projects: ProjectSummary[];
  project: ProjectSummary | null;
  status: CoreStatus;
  busy: boolean;
  runActive: boolean;
  liveActive: boolean;
  onCreate: () => void;
  onOpen: (project: ProjectSummary) => void;
  onTour: () => void;
  children: ReactNode;
}

export function WorkspaceChrome({
  view,
  onNavigate,
  projects,
  project,
  status,
  busy,
  runActive,
  liveActive,
  onCreate,
  onOpen,
  onTour,
  children,
}: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [search, setSearch] = useState("");
  const content = useRef<HTMLDivElement>(null);
  const recording = runActive || liveActive;
  const matches = projects.filter((item) =>
    item.name.toLowerCase().includes(search.toLowerCase()),
  );
  useEffect(() => {
    content.current?.scrollTo({ top: 0 });
    content.current?.focus({ preventScroll: true });
  }, [view]);
  return (
    <main className="app-shell">
      <a className="skip-link" href="#workspace-content">
        Skip to workspace
      </a>
      <aside
        className="workspace-sidebar"
        hidden={!sidebarOpen}
        aria-label="Workspace sidebar"
      >
        <div className="brand">
          <span className="brand-mark">
            <Icon name="wave" />
          </span>
          <strong>
            Presenter<span>Copilot</span>
          </strong>
          <button
            className="icon-button"
            aria-label="Hide sidebar"
            onClick={() => setSidebarOpen(false)}
          >
            <Icon name="sidebar" size={18} />
          </button>
        </div>
        <button
          className="new-project-button"
          onClick={onCreate}
          disabled={recording || busy}
        >
          <Icon name="plus" size={18} />
          New project
        </button>
        <nav aria-label="Main navigation">
          {(
            [
              { id: "home", label: "Home", icon: "grid" },
              { id: "setup", label: "Setup & settings", icon: "settings" },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              className={`nav-item ${view === item.id ? "active" : ""}`}
              aria-current={view === item.id ? "page" : undefined}
              onClick={() => onNavigate(item.id)}
              disabled={recording}
            >
              <Icon name={item.icon} />
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-project-heading">
          <span>Projects</span>
          <span>{projects.length}</span>
        </div>
        <label className="project-search">
          <Icon name="search" size={16} />
          <input
            aria-label="Search projects"
            placeholder="Find a project"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <div className="sidebar-projects">
          {matches.map((item) => (
            <div key={item.id}>
              <button
                className={`sidebar-project ${project?.id === item.id ? "selected" : ""}`}
                title={item.name}
                disabled={busy || recording}
                onClick={() => {
                  if (project?.id === item.id) {
                    onNavigate("overview");
                    return;
                  }
                  onOpen(item);
                }}
              >
                <Icon name="folder" size={17} />
                <span>{item.name}</span>
                {item.storage_status !== "ready" ? (
                  <small>Unavailable</small>
                ) : null}
              </button>
              {project?.id === item.id ? (
                <nav
                  className="project-navigation"
                  aria-label="Project navigation"
                >
                  {projectViews.map((entry) => (
                    <button
                      key={entry.id}
                      className={`nav-item ${view === entry.id ? "active" : ""}`}
                      aria-current={view === entry.id ? "page" : undefined}
                      disabled={!canNavigate(entry.id, runActive, liveActive)}
                      onClick={() => onNavigate(entry.id)}
                    >
                      <Icon name={entry.icon} size={16} />
                      {entry.label}
                    </button>
                  ))}
                </nav>
              ) : null}
            </div>
          ))}
          {!matches.length ? (
            <p className="sidebar-empty">
              {projects.length
                ? "No matching projects."
                : "Your presentations will feel at home here."}
            </p>
          ) : null}
        </div>
        <div className="sidebar-footer">
          <button className="nav-item" disabled={recording} onClick={onTour}>
            <Icon name="help" size={18} />
            Restart walkthrough
          </button>
          <div className="local-workspace">
            <span className="workspace-avatar">PC</span>
            <div>
              <strong>Personal workspace</strong>
              <small>Stored on this device</small>
            </div>
            <Icon name="shield" size={17} />
          </div>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="workspace-topbar">
          <div className="breadcrumb">
            {!sidebarOpen ? (
              <button
                className="icon-button"
                aria-label="Show sidebar"
                onClick={() => setSidebarOpen(true)}
              >
                <Icon name="sidebar" />
              </button>
            ) : null}
            <Icon
              name={
                view === "home"
                  ? "grid"
                  : view === "setup"
                    ? "settings"
                    : "folder"
              }
              size={18}
            />
            <span>
              {view === "home"
                ? "Home"
                : view === "setup"
                  ? "Setup & settings"
                  : (project?.name ?? "Project")}
            </span>
            {view !== "home" && view !== "setup" ? (
              <>
                <span className="breadcrumb-divider">/</span>
                <strong>
                  {projectViews.find((item) => item.id === view)?.label}
                </strong>
              </>
            ) : null}
          </div>
          <div
            className={`status-pill status-${status.state}`}
            aria-label={`Core status: ${status.state.toUpperCase()}`}
          >
            <span className="status-dot" aria-hidden="true" />
            {status.state === "ready" ? "Core ready" : `Core ${status.state}`}
          </div>
        </header>
        {recording ? (
          <div className="active-session-banner" role="status">
            <Icon name="wave" size={18} />
            <span>
              {runActive ? "Rehearsal" : "Live Assist"} is active. Finish the
              session before switching workspaces.
            </span>
            <button
              className="text-button"
              onClick={() => onNavigate(runActive ? "run" : "live")}
            >
              Return to session
            </button>
          </div>
        ) : null}
        <div
          id="workspace-content"
          className="workspace-content"
          ref={content}
          tabIndex={-1}
        >
          {children}
          <section
            hidden={view !== "home"}
            className="home-view"
            aria-labelledby="home-title"
          >
            <div className="home-intro">
              <span className="welcome-symbol">
                <Icon name="spark" size={32} />
              </span>
              <p className="eyebrow">YOUR NEXT GREAT PRESENTATION</p>
              <h1 id="home-title">
                Make room for
                <br />
                <span>your best thinking.</span>
              </h1>
              <p>
                Know your material. Find your voice.
                <br />
                Walk into the room a little more prepared.
              </p>
              <button
                className="primary-button hero-action"
                disabled={recording || busy}
                onClick={onCreate}
              >
                <Icon name="plus" size={18} />
                Create a project
              </button>
            </div>
            <div className="home-cards">
              {[
                {
                  icon: "folder",
                  color: "lavender",
                  title: "Bring your material",
                  copy: "A deck, a few notes, the evidence behind your story.",
                  action: "Start with a project",
                  click: onCreate,
                },
                {
                  icon: "message",
                  color: "peach",
                  title: "Meet your copilot",
                  copy: "See how teaching, practice, and live cues fit together.",
                  action: "Take the walkthrough",
                  click: onTour,
                },
                {
                  icon: "settings",
                  color: "mint",
                  title: "Make yourself at home",
                  copy: "Prepare local models and review your setup.",
                  action: "Open setup",
                  click: () => onNavigate("setup"),
                },
              ].map((item) => (
                <button
                  className="home-card"
                  key={item.title}
                  disabled={recording || busy}
                  onClick={item.click}
                >
                  <span className={`card-icon ${item.color}`}>
                    <Icon name={item.icon} />
                  </span>
                  <strong>{item.title}</strong>
                  <span>{item.copy}</span>
                  <small>
                    {item.action}
                    <Icon name="arrow" size={14} />
                  </small>
                </button>
              ))}
            </div>
            <div className="recent-heading">
              <h2>Your projects</h2>
              <span>{projects.length} on this device</span>
            </div>
            <div className="recent-projects">
              {projects.length ? (
                projects.map((item) => (
                  <button
                    className="recent-project"
                    key={item.id}
                    disabled={recording || busy}
                    onClick={() => onOpen(item)}
                  >
                    <Icon name="folder" />
                    <span>
                      <strong>{item.name}</strong>
                      <small>
                        {item.storage_status === "ready"
                          ? `${item.source_count} sources`
                          : "Storage unavailable"}
                      </small>
                    </span>
                    <Icon name="arrow" size={16} />
                  </button>
                ))
              ) : (
                <div className="first-project-note">
                  <Icon name="folder" />
                  <span>
                    No projects yet. Start with a presentation you’re working
                    on.
                  </span>
                </div>
              )}
            </div>
            <p className="home-privacy">
              <Icon name="shield" size={14} />
              New projects start in Local Only. Cloud reasoning is your choice.
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}

export function ProjectOverview({
  sourceCount,
  onNavigate,
}: {
  sourceCount: number;
  onNavigate: (view: WorkspaceView) => void;
}) {
  return (
    <section className="project-overview" aria-label="Project overview">
      <div className="overview-callout">
        <span className="card-icon lavender">
          <Icon name="spark" />
        </span>
        <div>
          <h2>
            {sourceCount
              ? "Your context is coming together."
              : "Every great presentation starts somewhere."}
          </h2>
          <p>
            {sourceCount
              ? "Add your own explanations, prepare for your audience, and try a rehearsal."
              : "Add a deck or supporting document. Keep facts connected to their sources."}
          </p>
        </div>
        <button
          className="primary-button"
          onClick={() => onNavigate(sourceCount ? "teach" : "sources")}
        >
          {sourceCount ? "Start teaching" : "Add sources"}
          <Icon name="arrow" size={16} />
        </button>
      </div>
      <div className="workflow-cards">
        {projectViews
          .filter((item) => !["overview", "project-settings"].includes(item.id))
          .map((item, index) => (
            <button
              className="workflow-card"
              key={item.id}
              onClick={() => onNavigate(item.id)}
            >
              <Icon name={item.icon} />
              <small>0{index + 1}</small>
              <strong>{item.label}</strong>
              <span>{item.description}</span>
              <Icon name="arrow" size={16} />
            </button>
          ))}
      </div>
    </section>
  );
}

export function SetupGuide({
  hasProject,
  onNavigate,
  onCreate,
  onTour,
}: {
  hasProject: boolean;
  onNavigate: (view: WorkspaceView) => void;
  onCreate: () => void;
  onTour: () => void;
}) {
  return (
    <>
      <div className="page-heading">
        <p className="eyebrow">MAKE IT YOURS</p>
        <h1>Ready when you are.</h1>
        <p>Start with the essentials. You can change these choices later.</p>
      </div>
      <div className="setup-guide">
        <article>
          <span>01</span>
          <h3>Prepare your models</h3>
          <p>
            Speech recognition powers Run and Live Assist. Semantic retrieval
            improves source matching. Each download starts only when you choose
            it below.
          </p>
        </article>
        <article>
          <span>02</span>
          <h3>Check your microphone</h3>
          <p>
            Open a project’s Run view, select a microphone, and start a short
            rehearsal. Speak for ten seconds, stop, and review the final
            transcript.
          </p>
          <button
            className="text-button"
            onClick={() => (hasProject ? onNavigate("run") : onCreate())}
          >
            {hasProject ? "Open Run" : "Create a project"}
            <Icon name="arrow" size={14} />
          </button>
        </article>
        <article>
          <span>03</span>
          <h3>Choose your boundaries</h3>
          <p>
            Local Only works without a cloud credential. For optional cloud
            reasoning, configure a provider below and review privacy in Project
            settings.
          </p>
          <button
            className="text-button"
            onClick={() =>
              hasProject ? onNavigate("project-settings") : onTour()
            }
          >
            {hasProject ? "Review project privacy" : "Learn how it works"}
            <Icon name="arrow" size={14} />
          </button>
        </article>
      </div>
    </>
  );
}
