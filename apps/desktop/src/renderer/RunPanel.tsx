import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type ASRStatus,
  type AudioDevice,
  type EventEnvelope,
  type JsonObject,
  type ReadyProjectSummary,
  type RendererCoreMethod,
  type RunDebrief,
  type RunMarkerType,
  type RunState,
  type RunTranscriptResult,
  type Session,
  unwrapInvokeResult,
} from "../shared/protocol";

type RunPanelProps = {
  project: ReadyProjectSummary;
  onActiveChange: (active: boolean) => void;
};

type DeviceListResult = { devices: AudioDevice[] };
type ASRConfigureResult = { config: ASRStatus["config"]; status: ASRStatus };
type SessionListResult = { sessions: Session[] };
type SessionResult = { session: Session };
type PresentationResult = {
  project_id: string;
  session_id: string;
  mode: "manual" | "powerpoint";
  reason: string;
  current_slide: number | null;
  slide_count: number | null;
  tracking: "active" | "stopped";
};
type DebriefResult = {
  debrief: RunDebrief | null;
  reused?: boolean;
};

type PartialUtterance = {
  utterance_id: string;
  text: string;
};

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
    if (typeof value.code === "string" && typeof value.message === "string") {
      return `${value.code}: ${value.message}`;
    }
    if (typeof value.message === "string") return value.message;
  }
  return "The Run request could not be completed.";
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function formatDuration(durationMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1_000));
  const hours = Math.floor(totalSeconds / 3_600);
  const minutes = Math.floor((totalSeconds % 3_600) / 60);
  const seconds = totalSeconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function isRunSession(session: Session | null | undefined): session is Session {
  return session?.mode === "run";
}

function currentElapsedMs(
  session: Session | null,
  state: RunState | null,
  currentTime = Date.now(),
): number {
  if (!session) return state?.duration_ms ?? 0;
  if (session.status !== "active") return state?.duration_ms ?? 0;
  const started = Date.parse(session.started_at);
  if (!Number.isFinite(started)) return state?.duration_ms ?? 0;
  return Math.max(0, currentTime - started);
}

function runEventSessionId(event: EventEnvelope): string | null {
  const value = event.payload.session_id;
  return typeof value === "string" ? value : null;
}

export function RunPanel({ project, onActiveChange }: RunPanelProps) {
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [asrStatus, setAsrStatus] = useState<ASRStatus | null>(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [trackingPreference, setTrackingPreference] = useState<
    "auto" | "manual"
  >("auto");
  const [session, setSession] = useState<Session | null>(null);
  const [runState, setRunState] = useState<RunState | null>(null);
  const [transcript, setTranscript] = useState<
    RunTranscriptResult["utterances"]
  >([]);
  const [partial, setPartial] = useState<PartialUtterance | null>(null);
  const [debrief, setDebrief] = useState<RunDebrief | null>(null);
  const [markerNote, setMarkerNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  const refreshRunData = useCallback(
    async (nextSession: Session | null) => {
      if (!isRunSession(nextSession)) {
        setRunState(null);
        setTranscript([]);
        setDebrief(null);
        return;
      }
      const params = {
        project_id: project.id,
        session_id: nextSession.id,
      };
      const [state, transcriptResult, debriefResult] = await Promise.all([
        requestCore<RunState>("run.get_state", params),
        requestCore<RunTranscriptResult>("run.list_transcript", {
          ...params,
          limit: 50,
          offset: 0,
        }),
        requestCore<DebriefResult>("run.get_debrief", params),
      ]);
      setRunState(state);
      setTranscript(transcriptResult.utterances);
      setDebrief(debriefResult.debrief);
    },
    [project.id],
  );

  const loadProjectRun = useCallback(async () => {
    setMessage(null);
    try {
      const [deviceResult, nextASRStatus, sessionResult] = await Promise.all([
        requestCore<DeviceListResult>("asr.list_devices"),
        requestCore<ASRStatus>("asr.status"),
        requestCore<SessionListResult>("session.list", {
          project_id: project.id,
        }),
      ]);
      setDevices(deviceResult.devices);
      setAsrStatus(nextASRStatus);
      setSelectedDeviceId(
        nextASRStatus.config.device_id ??
          deviceResult.devices.find((device) => device.is_default)?.device_id ??
          deviceResult.devices[0]?.device_id ??
          "",
      );
      const runs = sessionResult.sessions.filter((item) => item.mode === "run");
      const recovered =
        runs.find((item) => item.status === "active") ?? runs[0] ?? null;
      setSession(recovered);
      await refreshRunData(recovered);
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }, [project.id, refreshRunData]);

  useEffect(() => {
    setDevices([]);
    setAsrStatus(null);
    setSelectedDeviceId("");
    setTrackingPreference("auto");
    setSession(null);
    setRunState(null);
    setTranscript([]);
    setPartial(null);
    setDebrief(null);
    setMarkerNote("");
    void loadProjectRun();
  }, [loadProjectRun]);

  useEffect(() => {
    onActiveChange(session?.status === "active");
  }, [onActiveChange, session?.status]);

  useEffect(() => {
    if (session?.status !== "active") return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [session?.status]);

  useEffect(() => {
    if (session?.status !== "active") return undefined;
    const refreshSignal = () => {
      void requestCore<ASRStatus>("asr.status")
        .then(setAsrStatus)
        .catch(() => undefined);
    };
    refreshSignal();
    const timer = window.setInterval(refreshSignal, 1_000);
    return () => window.clearInterval(timer);
  }, [session?.status]);

  useEffect(() => {
    const removeListener = window.presenterCopilot.core.onEvent((event) => {
      const eventSessionId = runEventSessionId(event);
      const currentSessionId = session?.id;

      if (
        event.event === "asr.ready" ||
        event.event === "asr.model_loading" ||
        event.event === "asr.device_error"
      ) {
        void requestCore<ASRStatus>("asr.status")
          .then(setAsrStatus)
          .catch(() => undefined);
      }
      if (!currentSessionId || eventSessionId !== currentSessionId) return;

      if (event.event === "asr.partial") {
        const text = stringOrNull(event.payload.text);
        const utteranceId = stringOrNull(event.payload.utterance_id);
        if (text && utteranceId)
          setPartial({ utterance_id: utteranceId, text });
      }
      if (event.event === "asr.final") {
        const utteranceId = stringOrNull(event.payload.utterance_id);
        const text = stringOrNull(event.payload.text);
        if (!utteranceId || !text) return;
        const utterance = {
          utterance_id: utteranceId,
          text,
          start_ms: numberOrNull(event.payload.start_ms),
          end_ms: numberOrNull(event.payload.end_ms),
          confidence: numberOrNull(event.payload.confidence),
          slide_ordinal: numberOrNull(event.payload.slide_ordinal),
        };
        setTranscript((current) =>
          current.some((item) => item.utterance_id === utteranceId)
            ? current
            : [...current, utterance].sort(
                (left, right) =>
                  (left.start_ms ?? Number.MAX_SAFE_INTEGER) -
                  (right.start_ms ?? Number.MAX_SAFE_INTEGER),
              ),
        );
        setPartial((current) =>
          current?.utterance_id === utteranceId ? null : current,
        );
        setRunState((current) =>
          current
            ? { ...current, transcript_count: current.transcript_count + 1 }
            : current,
        );
      }
      if (event.event === "presentation.slide_changed") {
        const slide = numberOrNull(event.payload.slide_ordinal);
        if (slide !== null) {
          setRunState((current) =>
            current ? { ...current, current_slide: slide } : current,
          );
        }
      }
      if (event.event === "presentation.status_changed") {
        const slide = numberOrNull(event.payload.current_slide);
        const mode = event.payload.mode;
        if (mode === "manual" || mode === "powerpoint") {
          setRunState((current) =>
            current
              ? {
                  ...current,
                  current_slide: slide,
                  presentation_mode: mode,
                  presentation_reason:
                    stringOrNull(event.payload.reason) ??
                    current.presentation_reason,
                  tracking: "active",
                }
              : current,
          );
          if (mode === "manual" && currentSessionId) {
            void window.presenterCopilot.shortcuts
              .enableManualRun(project.id, currentSessionId)
              .then(unwrapInvokeResult)
              .then((shortcuts) => {
                if (!shortcuts.registered) {
                  setMessage(
                    "Manual tracking is active, but global slide shortcuts are unavailable. Use the on-screen controls.",
                  );
                }
              })
              .catch(() => {
                setMessage(
                  "Manual tracking is active, but global slide shortcuts are unavailable. Use the on-screen controls.",
                );
              });
          }
        }
      }
      if (event.event === "run.debrief_progress") {
        const phase = stringOrNull(event.payload.phase) ?? "working";
        const completed = numberOrNull(event.payload.completed) ?? 0;
        const total = numberOrNull(event.payload.total) ?? 0;
        setProgress(`${phase} · ${completed}/${total}`);
      }
      if (event.event === "session.stopped") {
        const nextStatus = event.payload.status;
        if (
          nextStatus !== "completed" &&
          nextStatus !== "aborted" &&
          nextStatus !== "error"
        ) {
          return;
        }
        setSession((current) =>
          current && event.payload.id === current.id
            ? { ...current, status: nextStatus }
            : current,
        );
      }
    });
    return removeListener;
  }, [project.id, session?.id]);

  const active = session?.status === "active";
  const inputSignalMissing =
    active &&
    asrStatus?.input_signal_state === "silent" &&
    asrStatus.input_frames_received >= 25;
  const durationMs = currentElapsedMs(session, runState, now);
  const currentSlide = runState?.current_slide ?? session?.current_slide_start;
  const modelReady =
    asrStatus?.model_status === "installed" ||
    asrStatus?.model_status === "ready";
  const selectedDevice = devices.find(
    (device) => device.device_id === selectedDeviceId,
  );
  const recentTranscript = useMemo(
    () => [...transcript].slice(-5).reverse(),
    [transcript],
  );

  const configureDevice = useCallback(async (deviceId: string) => {
    setSelectedDeviceId(deviceId);
    setBusy("configure-device");
    setMessage(null);
    try {
      const result = await requestCore<ASRConfigureResult>("asr.configure", {
        device_id: deviceId || null,
      });
      setAsrStatus(result.status);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, []);

  const prepareModel = useCallback(async () => {
    setBusy("prepare-model");
    setProgress("model · preparing local files");
    setMessage(null);
    try {
      setAsrStatus(await requestCore<ASRStatus>("asr.prepare_model", {}));
      setProgress(null);
      setMessage("The approved ASR model is ready locally.");
    } catch (error) {
      setProgress(null);
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, []);

  const startRun = useCallback(async () => {
    if (!modelReady || devices.length === 0) return;
    setBusy("start-run");
    setMessage(null);
    setProgress("run · starting local capture");
    let startedSession: Session | null = null;
    try {
      // Pin the device currently shown in the selector before opening a Run.
      // Windows/ Bluetooth changes can alter the PortAudio default between
      // panel load and Start; silently following that new default can route
      // capture to a different endpoint than the user selected.
      const configured = await requestCore<ASRConfigureResult>(
        "asr.configure",
        {
          device_id: selectedDeviceId || null,
        },
      );
      setAsrStatus(configured.status);
      const started = await requestCore<SessionResult>("session.start", {
        project_id: project.id,
        mode: "run",
        current_slide_start: 1,
      });
      startedSession = started.session;
      setSession(startedSession);
      const presentation = await requestCore<PresentationResult>(
        trackingPreference === "manual"
          ? "presentation.set_slide"
          : "presentation.detect",
        trackingPreference === "manual"
          ? {
              project_id: project.id,
              session_id: startedSession.id,
              slide_ordinal: 1,
            }
          : { project_id: project.id, session_id: startedSession.id },
      );
      setRunState((current) =>
        current
          ? {
              ...current,
              current_slide: presentation.current_slide,
              slide_count: presentation.slide_count,
              presentation_mode: presentation.mode,
              presentation_reason: presentation.reason,
              tracking: presentation.tracking,
            }
          : current,
      );
      if (presentation.mode === "manual") {
        const shortcuts = await window.presenterCopilot.shortcuts
          .enableManualRun(project.id, startedSession.id)
          .then(unwrapInvokeResult);
        if (!shortcuts.registered) {
          setMessage(
            "Run is listening, but global slide shortcuts are unavailable. Use the on-screen controls.",
          );
        }
      }
      const nextASRStatus = await requestCore<ASRStatus>("asr.start", {
        project_id: project.id,
        session_id: startedSession.id,
      });
      setAsrStatus(nextASRStatus);
      await refreshRunData(startedSession);
      setProgress(null);
    } catch (error) {
      if (startedSession?.status === "active") {
        try {
          const stopped = await requestCore<SessionResult>("session.stop", {
            project_id: project.id,
            session_id: startedSession.id,
            status: "error",
          });
          setSession(stopped.session);
          await refreshRunData(stopped.session);
        } catch {
          // The core retains the active session for an explicit safe retry.
        }
      }
      await window.presenterCopilot.shortcuts
        .disableManualRun()
        .catch(() => undefined);
      setProgress(null);
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [
    devices.length,
    modelReady,
    project.id,
    refreshRunData,
    selectedDeviceId,
    trackingPreference,
  ]);

  const stopRun = useCallback(async () => {
    if (!session) return;
    setBusy("stop-run");
    setMessage(null);
    try {
      const result = await requestCore<
        SessionResult & {
          debrief?: RunDebrief | null;
          cleanup_error_code?: string;
          debrief_error_code?: string;
        }
      >("session.stop", {
        project_id: project.id,
        session_id: session.id,
        status: "completed",
      });
      await window.presenterCopilot.shortcuts
        .disableManualRun()
        .catch(() => undefined);
      setSession(result.session);
      setDebrief(result.debrief ?? null);
      await refreshRunData(result.session);
      setProgress(null);
      if (result.cleanup_error_code || result.debrief_error_code) {
        setMessage(
          `Run stopped with ${result.cleanup_error_code ?? result.debrief_error_code}; retrying cleanup is safe.`,
        );
      } else {
        setMessage(
          "Run stopped. The local transcript and debrief are available below.",
        );
      }
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [project.id, refreshRunData, session]);

  const restartMicrophone = useCallback(async () => {
    if (!session || !active) return;
    setBusy("restart-microphone");
    setMessage(null);
    try {
      await requestCore("asr.stop", {
        project_id: project.id,
        session_id: session.id,
      });
      setAsrStatus(
        await requestCore<ASRStatus>("asr.start", {
          project_id: project.id,
          session_id: session.id,
        }),
      );
      setMessage(
        "The local microphone was restarted; Run state was preserved.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [active, project.id, session]);

  const moveSlide = useCallback(
    async (direction: "next" | "previous") => {
      if (!session || !active) return;
      setBusy(`slide-${direction}`);
      try {
        const method =
          direction === "next"
            ? "presentation.next_slide"
            : "presentation.previous_slide";
        const result = await requestCore<PresentationResult>(method, {
          project_id: project.id,
          session_id: session.id,
        });
        setRunState((current) =>
          current
            ? {
                ...current,
                current_slide: result.current_slide,
                presentation_mode: result.mode,
                presentation_reason: result.reason,
              }
            : current,
        );
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [active, project.id, session],
  );

  const mark = useCallback(
    async (markerType: RunMarkerType) => {
      if (!session || !active) return;
      setBusy(`mark-${markerType}`);
      setMessage(null);
      try {
        await requestCore("run.mark_event", {
          project_id: project.id,
          session_id: session.id,
          marker_type: markerType,
          note: markerNote.trim() || null,
        });
        setMarkerNote("");
        setRunState((current) =>
          current
            ? { ...current, marker_count: current.marker_count + 1 }
            : current,
        );
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [active, markerNote, project.id, session],
  );

  return (
    <section className="run-panel" aria-labelledby="run-title">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">Milestone 6 · local voice</p>
          <h2 id="run-title">Run mode</h2>
        </div>
        <span className={`run-state-badge ${active ? "listening" : ""}`}>
          {active ? "Listening" : session ? session.status : "Ready"}
        </span>
      </div>

      <p className="run-note">
        Microphone audio stays in the local core and is never sent through the
        renderer or a cloud speech provider.
      </p>

      {!active ? (
        <div className="run-setup-grid">
          <label>
            Microphone
            <select
              value={selectedDeviceId}
              onChange={(event) => void configureDevice(event.target.value)}
              disabled={busy !== null || devices.length === 0}
            >
              {devices.length === 0 ? (
                <option value="">No input device available</option>
              ) : null}
              {devices.map((device) => (
                <option key={device.device_id} value={device.device_id}>
                  {device.display_name} · {device.host_api} ·{" "}
                  {device.default_sample_rate} Hz
                  {device.is_default ? " · default" : ""}
                </option>
              ))}
            </select>
          </label>
          <div className="run-check">
            <span className="field-label">ASR model</span>
            <strong>{asrStatus?.model_status ?? "checking…"}</strong>
            <small>{asrStatus?.model_id ?? "local model"}</small>
          </div>
          <div className="run-check">
            <span className="field-label">Presentation</span>
            <select
              aria-label="Presentation tracking"
              value={trackingPreference}
              onChange={(event) => {
                setMessage(null);
                setTrackingPreference(event.target.value as "auto" | "manual");
              }}
              disabled={busy !== null}
            >
              <option value="auto">Detect matching PowerPoint</option>
              <option value="manual">Use manual tracking</option>
            </select>
            <small>
              PowerPoint is read-only; manual fallback remains available.
            </small>
          </div>
        </div>
      ) : null}

      {asrStatus?.last_error_code ? (
        <p className="run-warning" role="status">
          Last ASR status: {asrStatus.last_error_code}
        </p>
      ) : null}
      {message ? (
        <p className="notice-message" role="status">
          {message}
        </p>
      ) : null}
      {progress ? (
        <p className="progress-message" aria-live="polite">
          {progress}
        </p>
      ) : null}

      {!active ? (
        <div className="run-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={() => void prepareModel()}
            disabled={busy !== null || modelReady}
          >
            {busy === "prepare-model"
              ? "Preparing model…"
              : "Prepare local model"}
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => void startRun()}
            disabled={busy !== null || !modelReady || devices.length === 0}
          >
            {busy === "start-run" ? "Starting Run…" : "Start Run"}
          </button>
        </div>
      ) : (
        <>
          <div className="run-facts">
            <div>
              <dt>Timer</dt>
              <dd>{formatDuration(durationMs)}</dd>
            </div>
            <div>
              <dt>Slide</dt>
              <dd>
                {currentSlide ?? "—"}
                {runState?.slide_count ? ` / ${runState.slide_count}` : ""}
              </dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{runState?.presentation_mode ?? "manual"}</dd>
            </div>
            <div>
              <dt>Finals</dt>
              <dd>{transcript.length}</dd>
            </div>
          </div>
          <div className="run-live-row" aria-live="polite">
            <span className="listening-indicator" aria-hidden="true" />
            <strong>
              {inputSignalMissing
                ? "Microphone open · no signal"
                : asrStatus?.capture_state === "running"
                  ? "Listening"
                  : "Starting microphone…"}
            </strong>
            {inputSignalMissing ? (
              <span>
                Audio frames are arriving, but no usable input signal has been
                detected. Check mute/routing or choose another microphone.
              </span>
            ) : partial ? (
              <span>{partial.text}</span>
            ) : (
              <span>Waiting for speech…</span>
            )}
          </div>
          {asrStatus?.last_error_code ? (
            <button
              type="button"
              className="secondary-button run-retry-button"
              onClick={() => void restartMicrophone()}
              disabled={busy !== null}
            >
              {busy === "restart-microphone"
                ? "Restarting microphone…"
                : "Retry microphone"}
            </button>
          ) : null}
          <div className="run-actions run-actions-wrap">
            <button
              type="button"
              className="secondary-button"
              onClick={() => void moveSlide("previous")}
              disabled={busy !== null}
            >
              Previous slide
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void moveSlide("next")}
              disabled={busy !== null}
            >
              Next slide
            </button>
            <input
              aria-label="Optional marker note"
              placeholder="Optional marker note"
              value={markerNote}
              onChange={(event) => setMarkerNote(event.target.value)}
              maxLength={500}
              disabled={busy !== null}
            />
            <button
              type="button"
              className="secondary-button"
              onClick={() => void mark("question")}
              disabled={busy !== null}
            >
              Mark question
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void mark("weak_point")}
              disabled={busy !== null}
            >
              Mark weak point
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void mark("note")}
              disabled={busy !== null}
            >
              Add note
            </button>
            <button
              type="button"
              className="danger-button"
              onClick={() => void stopRun()}
              disabled={busy !== null}
            >
              {busy === "stop-run" ? "Stopping…" : "Stop Run"}
            </button>
          </div>
        </>
      )}

      {recentTranscript.length > 0 ? (
        <section
          className="run-transcript"
          aria-labelledby="run-transcript-title"
        >
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Final text only</p>
              <h3 id="run-transcript-title">Recent transcript</h3>
            </div>
            <span className="count-badge">{transcript.length}</span>
          </div>
          <div className="run-transcript-list">
            {recentTranscript.map((item) => (
              <article className="run-transcript-item" key={item.utterance_id}>
                <span>
                  Slide {item.slide_ordinal ?? "—"}
                  {item.start_ms !== null
                    ? ` · ${formatDuration(item.start_ms)}`
                    : ""}
                </span>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {debrief ? (
        <section className="run-debrief" aria-labelledby="run-debrief-title">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Deterministic local summary</p>
              <h3 id="run-debrief-title">Run debrief</h3>
            </div>
            <span className="count-badge">
              {debrief.session.word_count} words
            </span>
          </div>
          <p className="muted">
            {debrief.session.utterance_count} final utterances ·{" "}
            {debrief.long_segments.length} long segments ·{" "}
            {debrief.evidence_review_candidates.length} evidence reviews
          </p>
          {debrief.recommended_challenge_questions.length > 0 ? (
            <ul className="run-question-list">
              {debrief.recommended_challenge_questions
                .slice(0, 3)
                .map((question) => (
                  <li key={question}>{question}</li>
                ))}
            </ul>
          ) : null}
        </section>
      ) : session && session.status !== "active" ? (
        <p className="muted run-recovery-note">
          This completed Run is retained locally. Its state can be recovered
          after an app restart.
        </p>
      ) : null}

      {selectedDevice ? (
        <p className="boundary-note run-device-note">
          {selectedDevice.display_name} · {selectedDevice.host_api} ·{" "}
          {selectedDevice.default_sample_rate} Hz
        </p>
      ) : null}
    </section>
  );
}
