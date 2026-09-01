import { useCallback, useEffect, useState } from "react";

import {
  isHealthResult,
  type CoreStatus,
  type EventEnvelope,
  type HealthResult,
} from "../shared/protocol";

const initialStatus: CoreStatus = {
  state: "starting",
  protocolVersion: null,
  coreVersion: null,
  health: null,
  error: null,
};

export function App() {
  const [status, setStatus] = useState<CoreStatus>(initialStatus);
  const [health, setHealth] = useState<HealthResult | null>(null);
  const [lastEvent, setLastEvent] = useState<string>("Waiting for core.ready");
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
        if (mounted) setLastEvent(event.event);
      },
    );
    void window.presenterCopilot.core.getStatus().then((currentStatus) => {
      if (mounted) {
        setStatus(currentStatus);
        if (currentStatus.health) setHealth(currentStatus.health);
        if (currentStatus.state === "ready") setLastEvent("core.ready");
      }
    });

    return () => {
      mounted = false;
      removeStatusListener();
      removeEventListener();
    };
  }, []);

  useEffect(() => {
    if (status.state === "ready") void checkHealth();
  }, [checkHealth, status.state]);

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
          <p className="eyebrow">Milestone 0 · developer shell</p>
          <h1>Presenter Copilot</h1>
          <p className="lede">
            A local-first desktop boundary for presentation preparation.
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

      <section
        className="architecture-card"
        aria-labelledby="architecture-title"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Trusted desktop path</p>
            <h2 id="architecture-title">
              Renderer → preload → main → Python core
            </h2>
          </div>
          <span className="transport-label">NDJSON / stdio</span>
        </div>
        <p className="section-copy">
          This small shell proves the process boundary before product features
          are added. The renderer has no filesystem, secret, provider, or Node
          access.
        </p>
      </section>

      <section className="status-grid" aria-labelledby="status-title">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Live handshake</p>
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
            <dt>Uptime</dt>
            <dd>{health ? `${health.uptime_ms} ms` : "—"}</dd>
          </div>
        </dl>
        {status.error ? (
          <p className="error-message" role="alert">
            {status.error.code}: {status.error.message}
          </p>
        ) : null}
        <button
          type="button"
          className="health-button"
          onClick={() => void checkHealth()}
          disabled={healthState === "checking"}
        >
          {healthState === "checking" ? "Checking core…" : "Check Core Health"}
        </button>
      </section>
    </main>
  );
}
