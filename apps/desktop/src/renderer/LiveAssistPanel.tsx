import { useCallback, useEffect, useState } from "react";

import type {
  ASRStatus,
  AudioDevice,
  Cue,
  EventEnvelope,
  HudDisplay,
  HudSettings,
  HudSettingsUpdate,
  HudStatus,
  JsonObject,
  ReadyProjectSummary,
  RendererCoreMethod,
  Session,
} from "../shared/protocol";
import { unwrapInvokeResult } from "../shared/protocol";

type LiveAssistPanelProps = {
  project: ReadyProjectSummary;
  blocked?: boolean;
  onActiveChange: (active: boolean) => void;
};

type SessionListResult = { sessions: Session[] };
type SessionResult = { session: Session };
type DeviceListResult = { devices: AudioDevice[] };
type ConfigureResult = { status: ASRStatus };
type CueListResult = { cues: Cue[] };

const SHORTCUT_FIELDS: Array<{
  key: keyof HudSettings["shortcuts"];
  label: string;
}> = [
  { key: "push_to_assist", label: "Push to assist" },
  { key: "show_hide", label: "Show / hide HUD" },
  { key: "expand_collapse", label: "Expand / collapse" },
  { key: "previous_cue", label: "Previous cue" },
  { key: "next_cue", label: "Next cue" },
  { key: "clear", label: "Clear cue" },
  { key: "previous_slide", label: "Previous slide" },
  { key: "next_slide", label: "Next slide" },
];

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
  return "The Live Assist request could not be completed.";
}

function eventSessionId(event: EventEnvelope): string | null {
  return typeof event.payload.session_id === "string"
    ? event.payload.session_id
    : typeof event.payload.id === "string"
      ? event.payload.id
      : null;
}

export function LiveAssistPanel({
  project,
  blocked = false,
  onActiveChange,
}: LiveAssistPanelProps) {
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [asrStatus, setAsrStatus] = useState<ASRStatus | null>(null);
  const [deviceId, setDeviceId] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [cue, setCue] = useState<Cue | null>(null);
  const [settings, setSettings] = useState<HudSettings | null>(null);
  const [hudStatus, setHudStatus] = useState<HudStatus | null>(null);
  const [shortcutDraft, setShortcutDraft] = useState<
    HudSettings["shortcuts"] | null
  >(null);
  const [displays, setDisplays] = useState<HudDisplay[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [question, setQuestion] = useState("");

  const load = useCallback(async () => {
    setMessage(null);
    try {
      const [
        deviceResult,
        status,
        sessionResult,
        hudStatusResult,
        hud,
        displayResult,
      ] = await Promise.all([
        requestCore<DeviceListResult>("asr.list_devices"),
        requestCore<ASRStatus>("asr.status"),
        requestCore<SessionListResult>("session.list", {
          project_id: project.id,
        }),
        window.presenterCopilot.hud.getStatus().then(unwrapInvokeResult),
        window.presenterCopilot.hud.getSettings().then(unwrapInvokeResult),
        window.presenterCopilot.hud.getDisplays().then(unwrapInvokeResult),
      ]);
      setDevices(deviceResult.devices);
      setAsrStatus(status);
      setDeviceId(
        status.config.device_id ??
          deviceResult.devices.find((device) => device.is_default)?.device_id ??
          deviceResult.devices[0]?.device_id ??
          "",
      );
      setSettings(hud);
      setHudStatus(hudStatusResult);
      setShortcutDraft(hud.shortcuts);
      setDisplays(displayResult.displays);
      const liveSessions = sessionResult.sessions.filter(
        (item) => item.mode === "live_assist",
      );
      const recovered =
        liveSessions.find((item) => item.status === "active") ??
        liveSessions[0] ??
        null;
      setSession(recovered);
      if (recovered) {
        const cues = await requestCore<CueListResult>("cue.list", {
          project_id: project.id,
          session_id: recovered.id,
          limit: 1,
        });
        setCue(cues.cues[0] ?? null);
      } else {
        setCue(null);
      }
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }, [project.id]);

  useEffect(() => {
    setSession(null);
    setCue(null);
    setSettings(null);
    setHudStatus(null);
    setShortcutDraft(null);
    setDisplays([]);
    void load();
  }, [load]);

  const active = session?.status === "active";

  useEffect(() => {
    onActiveChange(active);
  }, [active, onActiveChange]);

  useEffect(() => {
    const remove = window.presenterCopilot.core.onEvent((event) => {
      const currentSessionId = session?.id;
      const eventSession = eventSessionId(event);
      if (event.event === "asr.ready" || event.event === "asr.device_error") {
        void requestCore<ASRStatus>("asr.status")
          .then(setAsrStatus)
          .catch(() => undefined);
      }
      if (!currentSessionId || eventSession !== currentSessionId) return;
      if (event.event === "cue.ready") {
        const cueId =
          typeof event.payload.cue_id === "string"
            ? event.payload.cue_id
            : null;
        const lines = Array.isArray(event.payload.lines)
          ? event.payload.lines.filter(
              (line): line is string => typeof line === "string",
            )
          : [];
        if (cueId && lines.length) {
          setCue((current) => ({
            ...(current ?? {
              id: cueId,
              project_id: project.id,
              session_id: currentSessionId,
              assist_id:
                typeof event.payload.assist_id === "string"
                  ? event.payload.assist_id
                  : cueId,
              cue_type: "source_pointer",
              text: lines.join("\n"),
              lines,
              state: "final",
              route: "retrieval_only",
              provider_run_id: null,
              created_at: new Date().toISOString(),
              displayed_at: null,
              dismissed_at: null,
              evidence: [],
            }),
            id: cueId,
            lines,
            text: lines.join("\n"),
            state: "final",
          }));
        }
      }
      if (event.event === "cue.error") {
        const code =
          typeof event.payload.code === "string"
            ? event.payload.code
            : "ASSIST_ERROR";
        setMessage(
          `${code}: ${typeof event.payload.message === "string" ? event.payload.message : "Live Assist failed."}`,
        );
      }
      if (event.event === "session.stopped") {
        setSession((current) =>
          current && event.payload.id === current.id
            ? { ...current, status: event.payload.status as Session["status"] }
            : current,
        );
      }
    });
    return remove;
  }, [project.id, session?.id]);

  const prepareModel = useCallback(async () => {
    setBusy("prepare-model");
    setMessage(null);
    try {
      setAsrStatus(await requestCore<ASRStatus>("asr.prepare_model", {}));
      setMessage("The approved local ASR model is ready.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, []);

  const startLive = useCallback(async () => {
    if (blocked || active) return;
    setBusy("start-live");
    setMessage(null);
    let started: Session | null = null;
    try {
      const configured = await requestCore<ConfigureResult>("asr.configure", {
        device_id: deviceId || null,
      });
      setAsrStatus(configured.status);
      const created = await requestCore<SessionResult>("session.start", {
        project_id: project.id,
        mode: "live_assist",
        current_slide_start: 1,
      });
      started = created.session;
      setSession(started);
      setAsrStatus(
        await requestCore<ASRStatus>("asr.start", {
          project_id: project.id,
          session_id: started.id,
        }),
      );
      setMessage(
        "Live Assist is listening locally. Push to assist when ready.",
      );
    } catch (error) {
      if (started?.status === "active") {
        await requestCore("session.stop", {
          project_id: project.id,
          session_id: started.id,
          status: "error",
        }).catch(() => undefined);
      }
      setSession(null);
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [active, blocked, deviceId, project.id]);

  const stopLive = useCallback(async () => {
    if (!session) return;
    setBusy("stop-live");
    setMessage(null);
    try {
      const stopped = await requestCore<SessionResult>("session.stop", {
        project_id: project.id,
        session_id: session.id,
        status: "completed",
      });
      setSession(stopped.session);
      setAsrStatus(await requestCore<ASRStatus>("asr.status"));
      setMessage(
        "Live Assist stopped; only final local utterances were retained.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [project.id, session]);

  const pushAssist = useCallback(async () => {
    if (!session || !active) return;
    setBusy("assist");
    setMessage(null);
    try {
      await requestCore("assist.request", {
        project_id: project.id,
        session_id: session.id,
        trigger: question.trim() ? "typed" : "button",
        ...(question.trim() ? { question: question.trim() } : {}),
      });
      setQuestion("");
      await window.presenterCopilot.hud.show().then(unwrapInvokeResult);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [active, project.id, question, session]);

  const saveHudSettings = useCallback(async (next: HudSettingsUpdate) => {
    setBusy("hud-settings");
    try {
      const saved = await window.presenterCopilot.hud
        .updateSettings(next)
        .then(unwrapInvokeResult);
      setSettings(saved);
      setShortcutDraft(saved.shortcuts);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, []);

  const modelReady =
    asrStatus?.model_status === "installed" ||
    asrStatus?.model_status === "ready";

  return (
    <section
      className="run-panel live-assist-panel"
      aria-labelledby="live-assist-title"
    >
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">Milestone 7 · push-to-assist</p>
          <h2 id="live-assist-title">Live Assist HUD</h2>
        </div>
        <span className={`run-state-badge ${active ? "listening" : ""}`}>
          {active ? "Listening" : session ? session.status : "Ready"}
        </span>
      </div>
      <p className="run-note">
        Audio remains in the Python core. Push-to-assist uses the current
        bounded audience question, recent final audience utterances, current
        slide, and live-eligible project evidence. Automatic question
        segmentation is not enabled.
      </p>
      {hudStatus ? (
        <p
          className={`notice-message ${hudStatus.capture_protection === "enabled" ? "" : "warning"}`}
          role={hudStatus.capture_protection === "enabled" ? "status" : "alert"}
        >
          {hudStatus.capture_protection === "enabled"
            ? "Capture protection: enabled (best effort)."
            : `Capture protection: unavailable (${hudStatus.capture_protection}). ${hudStatus.capture_protection_message} You may proceed deliberately.`}
        </p>
      ) : null}
      {!active ? (
        <div className="run-setup-grid">
          <label>
            Microphone
            <select
              value={deviceId}
              onChange={(event) => setDeviceId(event.target.value)}
              disabled={busy !== null || devices.length === 0 || blocked}
            >
              {devices.length === 0 ? (
                <option value="">No input device available</option>
              ) : null}
              {devices.map((device) => (
                <option key={device.device_id} value={device.device_id}>
                  {device.display_name} · {device.host_api}
                </option>
              ))}
            </select>
          </label>
          <div className="run-check">
            <span className="field-label">ASR model</span>
            <strong>{asrStatus?.model_status ?? "checking…"}</strong>
            <small>Local capture only</small>
          </div>
          <div className="run-check">
            <span className="field-label">Privacy</span>
            <strong>{project.privacy_mode.replaceAll("_", " ")}</strong>
            <small>Private items are excluded from remote context.</small>
          </div>
        </div>
      ) : null}
      {message ? (
        <p className="notice-message" role="status">
          {message}
        </p>
      ) : null}
      {active ? (
        <label className="live-question-field">
          Optional typed question override
          <input
            type="text"
            value={question}
            maxLength={1000}
            placeholder="Leave blank to use the bounded live question window"
            onChange={(event) => setQuestion(event.target.value)}
            disabled={busy !== null}
          />
        </label>
      ) : null}
      <div className="run-actions run-actions-wrap">
        {!active ? (
          <>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void prepareModel()}
              disabled={busy !== null || modelReady || blocked}
            >
              {busy === "prepare-model"
                ? "Preparing model…"
                : "Prepare local model"}
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={() => void startLive()}
              disabled={
                busy !== null || blocked || !modelReady || devices.length === 0
              }
            >
              {busy === "start-live"
                ? "Starting Live Assist…"
                : "Start Live Assist"}
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className="primary-button"
              onClick={() => void pushAssist()}
              disabled={busy !== null}
            >
              {busy === "assist" ? "Finding a cue…" : "Push to assist"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                void window.presenterCopilot.hud.show().then(unwrapInvokeResult)
              }
            >
              Show HUD
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                void window.presenterCopilot.hud.hide().then(unwrapInvokeResult)
              }
            >
              Hide HUD
            </button>
            <button
              type="button"
              className="danger-button"
              onClick={() => void stopLive()}
              disabled={busy !== null}
            >
              {busy === "stop-live" ? "Stopping…" : "Stop Live Assist"}
            </button>
          </>
        )}
      </div>
      {settings ? (
        <div className="settings-grid live-hud-settings">
          <label>
            HUD display
            <select
              value={settings.display_id ?? ""}
              onChange={(event) =>
                void saveHudSettings({ display_id: event.target.value || null })
              }
              disabled={busy !== null}
            >
              <option value="">Primary display</option>
              {displays.map((display) => (
                <option key={display.id} value={display.id}>
                  Display {display.id}
                  {display.primary ? " · primary" : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            HUD width
            <input
              type="number"
              min={360}
              max={900}
              value={settings.width}
              onChange={(event) =>
                void saveHudSettings({ width: Number(event.target.value) })
              }
              disabled={busy !== null}
            />
          </label>
          <label>
            HUD font size
            <input
              type="number"
              min={16}
              max={48}
              value={settings.font_size}
              onChange={(event) =>
                void saveHudSettings({ font_size: Number(event.target.value) })
              }
              disabled={busy !== null}
            />
          </label>
          <label>
            Top offset
            <input
              type="number"
              min={0}
              max={240}
              value={settings.top_offset}
              onChange={(event) =>
                void saveHudSettings({ top_offset: Number(event.target.value) })
              }
              disabled={busy !== null}
            />
          </label>
        </div>
      ) : null}
      {settings && shortcutDraft ? (
        <div
          className="shortcut-settings"
          aria-label="Live Assist shortcut settings"
        >
          <span className="field-label">Global shortcut settings</span>
          <div className="shortcut-grid">
            {SHORTCUT_FIELDS.map((field) => (
              <label key={field.key}>
                {field.label}
                <input
                  type="text"
                  value={shortcutDraft[field.key]}
                  maxLength={80}
                  onChange={(event) =>
                    setShortcutDraft((current) =>
                      current
                        ? { ...current, [field.key]: event.target.value }
                        : current,
                    )
                  }
                  onBlur={() => {
                    const value = shortcutDraft[field.key];
                    void saveHudSettings({ shortcuts: { [field.key]: value } });
                  }}
                  disabled={busy !== null}
                />
              </label>
            ))}
          </div>
          <small>
            Use Electron accelerator syntax with at least one modifier, for
            example Ctrl+Alt+Space. Failed registrations restore the previous
            set.
          </small>
        </div>
      ) : null}
      {cue ? (
        <p className="boundary-note">
          Latest cue: {cue.lines.join(" · ")} · {cue.route.replaceAll("_", " ")}
        </p>
      ) : null}
      <p className="boundary-note">
        Global shortcuts: push{" "}
        <code>{settings?.shortcuts.push_to_assist ?? "Ctrl+Alt+Space"}</code> ·
        show/hide <code>{settings?.shortcuts.show_hide ?? "Ctrl+Alt+H"}</code> ·
        expand{" "}
        <code>{settings?.shortcuts.expand_collapse ?? "Ctrl+Alt+Enter"}</code>.
      </p>
    </section>
  );
}
