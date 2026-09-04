import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import type {
  CueSourceProjection,
  EventEnvelope,
  HudStatus,
  JsonObject,
} from "../shared/protocol";

type HudCue = {
  id: string;
  sessionId: string;
  cueType: string;
  route: string;
  state: "partial" | "final";
  lines: string[];
  evidence: Array<{
    evidenceId: string;
    label: string;
    available: boolean;
    rank: number;
  }>;
};

type HudViewState =
  | "HIDDEN"
  | "IDLE"
  | "LISTENING"
  | "SEARCHING"
  | "CUE_PARTIAL"
  | "CUE_READY"
  | "EXPANDED_SOURCE"
  | "ERROR";

const initialStatus: HudStatus = {
  visible: false,
  expanded: false,
  core_state: "stopped",
  font_size: 24,
  capture_protection: "unsupported",
  capture_protection_message: "Capture protection status is not available yet.",
  shortcuts_registered: false,
};

export function HudApp() {
  const [status, setStatus] = useState(initialStatus);
  const [viewState, setViewState] = useState<HudViewState>("HIDDEN");
  const [cue, setCue] = useState<HudCue | null>(null);
  const [sources, setSources] = useState<CueSourceProjection[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sourceBusy, setSourceBusy] = useState(false);
  const statusRef = useRef(status);
  const sessionIdRef = useRef<string | null>(null);
  const assistIdRef = useRef<string | null>(null);

  useEffect(() => {
    const removeStatus = window.presenterCopilotHud.onStatus((next) => {
      statusRef.current = next;
      setStatus(next);
      setViewState((current) => {
        if (!next.visible) return "HIDDEN";
        if (next.core_state === "unavailable") return "ERROR";
        return current === "HIDDEN" ? "IDLE" : current;
      });
      if (next.core_state === "unavailable") {
        setError(
          "CORE_UNAVAILABLE: Live Assist is unavailable; the HUD can still be hidden.",
        );
      }
    });
    const removeEvent = window.presenterCopilotHud.onEvent((event) => {
      if (
        event.event === "session.started" &&
        event.payload.mode === "live_assist"
      ) {
        assistIdRef.current = null;
      }
      if (event.event === "session.stopped") sessionIdRef.current = null;
      if (event.event === "session.stopped") assistIdRef.current = null;
      if (event.event === "assist.started") {
        const assistId = stringValue(event.payload.assist_id);
        if (assistId) assistIdRef.current = assistId;
      }
      if (
        (event.event === "cue.partial" ||
          event.event === "cue.ready" ||
          event.event === "cue.error") &&
        isStaleAssistEvent(event, assistIdRef.current)
      ) {
        return;
      }
      handleEvent(event, {
        setSessionId: (value) => {
          sessionIdRef.current = value;
        },
        setCue,
        setSources,
        setError,
        setViewState,
      });
    });
    const removeCue = window.presenterCopilotHud.onCue((value) => {
      const next = parseCue(value, sessionIdRef.current);
      if (next) {
        setCue(next);
        setSources([]);
        setError(null);
        setViewState("CUE_READY");
      }
    });
    const removeClear = window.presenterCopilotHud.onClear(() => {
      setCue(null);
      setSources([]);
      setError(null);
      setViewState(statusRef.current.visible ? "IDLE" : "HIDDEN");
    });
    void window.presenterCopilotHud.ready();
    return () => {
      removeStatus();
      removeEvent();
      removeCue();
      removeClear();
    };
  }, []);

  const expanded = status.expanded;
  const routeLabel = cue?.route.replaceAll("_", " ") ?? "local";
  const captureLabel =
    status.capture_protection === "enabled"
      ? "Capture protection: enabled (best effort)"
      : status.capture_protection === "unsupported"
        ? "Capture protection: unavailable"
        : "Capture protection: error";

  const expandSources = async () => {
    if (!cue) return;
    setSourceBusy(true);
    setError(null);
    try {
      const response = await window.presenterCopilotHud.expandSources(cue.id);
      if (!response.ok) throw response.error;
      setSources(response.result.sources);
      setViewState("EXPANDED_SOURCE");
    } catch (nextError) {
      setError(errorMessage(nextError));
      setViewState("ERROR");
    } finally {
      setSourceBusy(false);
    }
  };

  const dismiss = async () => {
    if (cue) await window.presenterCopilotHud.dismiss(cue.id);
    setCue(null);
    setSources([]);
    setViewState(status.visible ? "IDLE" : "HIDDEN");
  };

  const toggleExpanded = () => {
    void window.presenterCopilotHud.setExpanded(!expanded);
  };

  const pushAssist = () => {
    setError(null);
    setViewState("SEARCHING");
    void window.presenterCopilotHud
      .pushToAssist()
      .then((response) => {
        if (!response.ok) {
          setError(errorMessage(response.error));
          setViewState("ERROR");
        }
      })
      .catch((nextError) => {
        setError(errorMessage(nextError));
        setViewState("ERROR");
      });
  };

  const evidenceCount = useMemo(() => cue?.evidence.length ?? 0, [cue]);

  if (!status.visible) return null;

  return (
    <section
      className={`hud-shell ${expanded ? "hud-expanded" : "hud-collapsed"}`}
      aria-label="Presenter Copilot live assist"
      style={{ "--hud-font-size": `${status.font_size}px` } as CSSProperties}
    >
      <div className="hud-card">
        <div className="hud-topline">
          <span className="hud-state">{viewState}</span>
          <span className="hud-route">{routeLabel}</span>
          {expanded ? (
            <button
              type="button"
              className="hud-icon-button"
              onClick={toggleExpanded}
            >
              Collapse
            </button>
          ) : null}
        </div>
        <div className="hud-lines" aria-live="polite">
          {cue?.lines.length ? (
            cue.lines
              .slice(0, 3)
              .map((line, index) => <p key={`${cue.id}-${index}`}>{line}</p>)
          ) : (
            <p className="hud-placeholder">
              Push to assist when the audience asks a question.
            </p>
          )}
        </div>
        {expanded ? (
          <div className="hud-expanded-content">
            <div className="hud-actions">
              <button
                type="button"
                className="hud-primary"
                onClick={pushAssist}
              >
                Push to assist
              </button>
              <button
                type="button"
                className="hud-secondary"
                onClick={() => void expandSources()}
                disabled={!cue || sourceBusy}
              >
                {sourceBusy
                  ? "Loading sources…"
                  : `Expand sources (${evidenceCount})`}
              </button>
              <button
                type="button"
                className="hud-secondary"
                onClick={() => void dismiss()}
                disabled={!cue}
              >
                Clear cue
              </button>
            </div>
            {sources.length > 0 ? (
              <div className="hud-sources" aria-label="Cue sources">
                {sources.map((source) => (
                  <article className="hud-source" key={source.evidence_id}>
                    <div className="hud-source-heading">
                      <strong>{source.label}</strong>
                      <span>
                        {source.available ? "available" : "unavailable"}
                      </span>
                    </div>
                    {source.source_name ? (
                      <small>{source.source_name}</small>
                    ) : null}
                    {source.excerpt ? (
                      <p>{source.excerpt}</p>
                    ) : (
                      <p>Source snapshot is no longer available.</p>
                    )}
                  </article>
                ))}
              </div>
            ) : null}
            <p
              className="hud-protection"
              title={status.capture_protection_message}
            >
              {captureLabel} ·{" "}
              {status.shortcuts_registered
                ? "global controls ready"
                : status.core_state === "unavailable"
                  ? "show / hide remains available"
                  : "global controls unavailable"}
            </p>
            <p className="hud-note">
              Automatic question segmentation is not enabled; use
              push-to-assist.
            </p>
          </div>
        ) : null}
        {error ? (
          <p className="hud-error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}

function handleEvent(
  event: EventEnvelope,
  setters: {
    setSessionId: (value: string | null) => void;
    setCue: (value: HudCue | null) => void;
    setSources: (value: CueSourceProjection[]) => void;
    setError: (value: string | null) => void;
    setViewState: (value: HudViewState) => void;
  },
) {
  const payload = event.payload;
  if (event.event === "session.started" && payload.mode === "live_assist") {
    setters.setSessionId(stringValue(payload.id));
    setters.setCue(null);
    setters.setSources([]);
    setters.setError(null);
    setters.setViewState("IDLE");
    return;
  }
  if (event.event === "session.stopped") {
    setters.setCue(null);
    setters.setSources([]);
    setters.setViewState("HIDDEN");
    return;
  }
  if (event.event === "asr.partial") {
    setters.setViewState("LISTENING");
    return;
  }
  if (
    event.event === "assist.started" ||
    event.event === "assist.retrieval_ready" ||
    event.event === "assist.reasoning_started"
  ) {
    setters.setViewState("SEARCHING");
    return;
  }
  if (event.event === "cue.partial" || event.event === "cue.ready") {
    const next = parseCue(payload, stringValue(payload.session_id));
    if (next) {
      setters.setCue(next);
      setters.setSources([]);
      setters.setError(null);
      setters.setViewState(
        event.event === "cue.partial" ? "CUE_PARTIAL" : "CUE_READY",
      );
    }
    return;
  }
  if (event.event === "cue.error") {
    setters.setError(
      `${stringValue(payload.code) ?? "ASSIST_ERROR"}: ${stringValue(payload.message) ?? "Live Assist failed."}`,
    );
    setters.setViewState("ERROR");
  }
}

export function parseCue(
  value: unknown,
  fallbackSessionId: string | null,
): HudCue | null {
  if (!isRecord(value)) return null;
  const id = stringValue(value.cue_id) ?? stringValue(value.id);
  const sessionId = stringValue(value.session_id) ?? fallbackSessionId;
  const lines = Array.isArray(value.lines)
    ? value.lines
        .filter((line): line is string => typeof line === "string")
        .slice(0, 3)
    : [];
  if (!id || !sessionId || lines.length === 0) return null;
  const evidence = Array.isArray(value.evidence)
    ? value.evidence
        .filter(isRecord)
        .map((item, index) => ({
          evidenceId: stringValue(item.evidence_id) ?? `evidence-${index}`,
          label: stringValue(item.label) ?? "Project source",
          available: item.available !== false,
          rank: typeof item.rank === "number" ? item.rank : index + 1,
        }))
        .slice(0, 8)
    : [];
  return {
    id,
    sessionId,
    cueType: stringValue(value.cue_type) ?? "source_pointer",
    route: stringValue(value.route) ?? "retrieval_only",
    state: value.state === "partial" ? "partial" : "final",
    lines,
    evidence,
  };
}

function isRecord(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export function isStaleAssistEvent(
  event: EventEnvelope,
  currentAssistId: string | null,
): boolean {
  if (!currentAssistId) return false;
  const assistId = stringValue(event.payload.assist_id);
  return assistId !== null && assistId !== currentAssistId;
}

function errorMessage(value: unknown): string {
  if (
    isRecord(value) &&
    typeof value.code === "string" &&
    typeof value.message === "string"
  ) {
    return `${value.code}: ${value.message}`;
  }
  return "The HUD request could not be completed.";
}
