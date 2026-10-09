import { useEffect, useRef, useState } from "react";
import {
  unwrapInvokeResult,
  type RendererCoreMethod,
} from "../shared/protocol";
import type { RehearsalFinding } from "./RehearsalFindings";

type Page = { offset: number; total: number; has_more: boolean };
type Session = {
  session_id: string;
  source_revision_number: number;
  started_at: string;
};
type Message = {
  slide_id: string;
  object_id: string;
  name: string;
  text: string;
  source_kind: "native_text" | "native_chart_cache" | "native_table_cells";
  source_slide_number: number;
  current_slide_number: number | null;
  current_span_status: string;
  current_text_editable: boolean;
  whole_message_selectable: boolean;
};
type Messages = Page & {
  messages: Message[];
  source_revision_number: number;
  excluded_objects: number;
};
type Speech = {
  utterance_id: string;
  text: string;
  start_ms: number | null;
  end_ms: number | null;
};
type Window = { index: number; utterances: Speech[] };
type Prepared = {
  document_id: string;
  revision_id: string;
  session_id: string;
  slide_id: string;
  point: {
    object_id: string;
    quote: string;
    source_kind: Message["source_kind"];
  };
  context_sha256: string;
  total_windows: number;
  total_utterances: number;
  unmapped_session_utterances: number;
  excluded_actor_utterances: number;
  offset: number;
  has_more: boolean;
  windows: Window[];
};
type Summary = {
  finding_id: string;
  source_slide_number: number;
  window_index: number;
  total_windows: number;
  status: string;
  disposition: string;
};
type History = Page & { analyses: Summary[] };
type Detail = {
  revision_id: string;
  can_adopt: boolean;
  context_current: boolean;
  finding: RehearsalFinding;
  snapshot: Prepared & {
    provider_id: string;
    model_id: string;
    window_index: number;
    hint: {
      status: string;
      reason: string;
      quotes: { utterance_id: string; quote: string }[];
    };
  };
};
type Scope = {
  project_id: string;
  document_id: string;
  expected_revision_id: string;
};
type Job = Scope & {
  job_id: string;
  session_id: string;
  state: string;
  terminal: boolean;
  can_cancel: boolean;
  cancellation_requested: boolean;
  cancellation_accepted?: boolean;
  result: { finding_id: string; analysis_id: string } | null;
  error: { code: string; message: string } | null;
};
type ActiveJob = {
  scope: Scope;
  generation: number;
  id: string | null;
  cancelled: boolean;
};
const kinds = {
  native_text: "Native text",
  native_chart_cache: "Cached chart values",
  native_table_cells: "Table cell text",
};

async function request<T>(
  method: RendererCoreMethod,
  params: Record<string, unknown>,
): Promise<T> {
  return unwrapInvokeResult(
    await window.presenterCopilot.core.request<T>(method, params),
  );
}
const errorText = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "The rehearsal review could not be loaded.";

export function RehearsalSemanticReview({
  projectId,
  documentId,
  revisionId,
  visible,
  disabled,
  selectedSlide,
  selectedTextObjectId,
  selectedTextEditable,
  onOpenSlide,
  onSelectTextObject,
  onPrepare,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  visible: boolean;
  disabled: boolean;
  selectedSlide: number;
  selectedTextObjectId: string | null;
  selectedTextEditable: boolean;
  onOpenSlide: (ordinal: number) => void;
  onSelectTextObject: (finding: RehearsalFinding) => void;
  onPrepare: (
    finding: RehearsalFinding,
    destination: "text" | "notes" | "rewrite",
  ) => void;
}) {
  const scope: Scope = {
    project_id: projectId,
    document_id: documentId,
    expected_revision_id: revisionId,
  };
  const [sessions, setSessions] = useState<
    (Page & { sessions: Session[] }) | null
  >(null);
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<Messages | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [quote, setQuote] = useState("");
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [windowIndex, setWindowIndex] = useState("");
  const [history, setHistory] = useState<History | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const generation = useRef(0);
  const reviewGeneration = useRef(0);
  const activeJob = useRef<ActiveJob | null>(null);
  const sourceText = useRef<HTMLTextAreaElement>(null);
  const mounted = useRef(false);

  function cancelCaptured(active: ActiveJob) {
    active.cancelled = true;
    if (active.id)
      void request<Job>("presentation.workspace.cancel_rehearsal_analysis", {
        ...active.scope,
        job_id: active.id,
      }).catch(() => undefined);
  }
  function invalidate() {
    generation.current++;
    reviewGeneration.current++;
    if (activeJob.current) cancelCaptured(activeJob.current);
    activeJob.current = null;
    setPrepared(null);
    setWindowIndex("");
    setJob(null);
    setDetail(null);
    setBusy(false);
    setHistoryBusy(false);
    setError(null);
    setNotice(null);
  }
  const current = (id: number) => mounted.current && generation.current === id;

  useEffect(() => {
    mounted.current = true;
    generation.current++;
    reviewGeneration.current++;
    const id = generation.current;
    setSessions(null);
    setSessionId("");
    setMessages(null);
    setMessage(null);
    setQuote("");
    setPrepared(null);
    setWindowIndex("");
    setHistory(null);
    setDetail(null);
    setJob(null);
    setError(null);
    setNotice(null);
    setBusy(false);
    setHistoryBusy(false);
    if (visible) {
      setBusy(true);
      void request<Page & { sessions: Session[] }>(
        "presentation.workspace.list_rehearsal_review_sessions",
        scope,
      )
        .then((next) => {
          if (current(id)) setSessions(next);
        })
        .catch((caught) => {
          if (current(id)) setError(errorText(caught));
        })
        .finally(() => {
          if (current(id)) setBusy(false);
        });
    }
    return () => {
      mounted.current = false;
      generation.current++;
      reviewGeneration.current++;
      if (activeJob.current) cancelCaptured(activeJob.current);
      activeJob.current = null;
    };
  }, [projectId, documentId, revisionId, visible]);

  useEffect(() => {
    if (disabled && activeJob.current) {
      cancelCaptured(activeJob.current);
      // Keep polling the current job: a cancellation request is not a terminal result.
    }
  }, [disabled]);

  async function sessionPage(offset: number) {
    invalidate();
    setSessionId("");
    setMessages(null);
    setMessage(null);
    setQuote("");
    setHistory(null);
    const id = generation.current;
    setBusy(true);
    try {
      const next = await request<Page & { sessions: Session[] }>(
        "presentation.workspace.list_rehearsal_review_sessions",
        { ...scope, offset },
      );
      if (current(id)) setSessions(next);
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function chooseSession(nextSession: string) {
    invalidate();
    setSessionId(nextSession);
    setMessages(null);
    setMessage(null);
    setQuote("");
    setHistory(null);
    if (!nextSession) return;
    const id = generation.current;
    setBusy(true);
    try {
      const [nextMessages, nextHistory] = await Promise.all([
        request<Messages>(
          "presentation.workspace.list_rehearsal_review_messages",
          { ...scope, session_id: nextSession },
        ),
        request<History>("presentation.workspace.list_rehearsal_analyses", {
          ...scope,
          session_id: nextSession,
        }),
      ]);
      if (current(id)) {
        setMessages(nextMessages);
        setHistory(nextHistory);
      }
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function messagePage(offset: number) {
    invalidate();
    setMessage(null);
    setQuote("");
    const id = generation.current;
    setBusy(true);
    try {
      const next = await request<Messages>(
        "presentation.workspace.list_rehearsal_review_messages",
        { ...scope, session_id: sessionId, offset },
      );
      if (current(id)) setMessages(next);
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  function chooseMessage(object: string) {
    invalidate();
    setQuote("");
    setMessage(
      messages?.messages.find((item) => item.object_id === object) ?? null,
    );
  }
  function chooseQuote(text: string) {
    invalidate();
    setQuote(text);
  }
  async function prepare(offset = 0) {
    if (!message || !quote || disabled || busy) return;
    invalidate();
    const id = generation.current;
    setBusy(true);
    try {
      const next = await request<Prepared>(
        "presentation.workspace.prepare_rehearsal_coverage_review",
        {
          ...scope,
          session_id: sessionId,
          slide_id: message.slide_id,
          object_id: message.object_id,
          quote,
          offset,
        },
      );
      if (
        next.document_id !== documentId ||
        next.revision_id !== revisionId ||
        next.session_id !== sessionId ||
        next.slide_id !== message.slide_id ||
        next.point.object_id !== message.object_id ||
        next.point.quote !== quote ||
        !/^[0-9a-f]{64}$/.test(next.context_sha256)
      )
        throw new Error("Prepared context does not match this selection.");
      if (current(id)) setPrepared(next);
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function historyPage(offset = 0) {
    const selection = generation.current;
    const id = ++reviewGeneration.current;
    setHistoryBusy(true);
    try {
      const next = await request<History>(
        "presentation.workspace.list_rehearsal_analyses",
        { ...scope, session_id: sessionId, offset },
      );
      if (current(selection) && id === reviewGeneration.current)
        setHistory(next);
    } catch (caught) {
      if (current(selection) && id === reviewGeneration.current)
        setError(errorText(caught));
    } finally {
      if (current(selection) && id === reviewGeneration.current)
        setHistoryBusy(false);
    }
  }
  async function openDetail(findingId: string) {
    const selection = generation.current;
    const id = ++reviewGeneration.current;
    setHistoryBusy(true);
    setDetail(null);
    try {
      const next = await request<Detail>(
        "presentation.workspace.get_rehearsal_analysis",
        { ...scope, finding_id: findingId },
      );
      if (
        next.revision_id !== revisionId ||
        next.finding.finding_id !== findingId ||
        next.finding.session_id !== sessionId ||
        next.finding.kind !== "semantic_coverage"
      )
        throw new Error(
          "This saved result does not match the selected rehearsal.",
        );
      if (current(selection) && id === reviewGeneration.current)
        setDetail(next);
    } catch (caught) {
      if (current(selection) && id === reviewGeneration.current)
        setError(errorText(caught));
    } finally {
      if (current(selection) && id === reviewGeneration.current)
        setHistoryBusy(false);
    }
  }
  async function analyze() {
    if (
      !message ||
      !prepared ||
      windowIndex === "" ||
      busy ||
      disabled ||
      activeJob.current
    )
      return;
    const active: ActiveJob = {
      scope: { ...scope },
      generation: generation.current,
      id: null,
      cancelled: false,
    };
    activeJob.current = active;
    setBusy(true);
    setError(null);
    setNotice(null);
    setJob(null);
    try {
      let next = await request<Job>(
        "presentation.workspace.start_rehearsal_analysis",
        {
          ...scope,
          session_id: sessionId,
          slide_id: message.slide_id,
          object_id: message.object_id,
          quote,
          expected_context_sha256: prepared.context_sha256,
          window_index: Number(windowIndex),
        },
      );
      active.id = next.job_id;
      if (!current(active.generation) || active.cancelled)
        cancelCaptured(active);
      while (current(active.generation) && activeJob.current === active) {
        if (
          next.document_id !== active.scope.document_id ||
          next.expected_revision_id !== active.scope.expected_revision_id ||
          next.project_id !== active.scope.project_id ||
          next.session_id !== sessionId ||
          next.job_id !== active.id
        )
          throw new Error("Analysis status does not match this selection.");
        setJob(next);
        if (next.terminal) {
          activeJob.current = null;
          setBusy(false);
          if (next.error && next.state !== "cancelled")
            setError(`${next.error.message} (${next.error.code})`);
          if (next.state === "cancelled") {
            setNotice("Analysis cancelled. No window result was saved.");
          } else if (next.state === "failed") {
            setNotice(null);
          }
          if (next.state === "completed") {
            setNotice(
              active.cancelled
                ? "Cancellation arrived after storage began. The saved window result remains available for review."
                : "Saved one window result. Review it before preparing an edit.",
            );
            void historyPage();
          }
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
        if (!current(active.generation) || activeJob.current !== active) break;
        try {
          next = await request<Job>(
            "presentation.workspace.poll_rehearsal_analysis",
            { ...active.scope, job_id: active.id },
          );
        } catch (caught) {
          if (current(active.generation))
            setError(
              `Status check failed; analysis may still be running. ${errorText(caught)}`,
            );
        }
      }
    } catch (caught) {
      cancelCaptured(active);
      if (current(active.generation)) {
        setError(errorText(caught));
        setBusy(false);
        activeJob.current = null;
      }
    }
  }
  async function cancelAnalysis() {
    const active = activeJob.current;
    if (!active) return;
    active.cancelled = true;
    if (!active.id) {
      setNotice(
        "Cancellation requested. Waiting for analysis to start so it can be cancelled.",
      );
      return;
    }
    try {
      const next = await request<Job>(
        "presentation.workspace.cancel_rehearsal_analysis",
        { ...active.scope, job_id: active.id },
      );
      if (current(active.generation) && activeJob.current === active) {
        setJob(next);
        setNotice(
          next.cancellation_accepted
            ? "Cancellation requested; waiting for the worker to finish."
            : "Storage has begun or the job has finished. Check its final status and saved results.",
        );
      }
    } catch (caught) {
      if (current(active.generation))
        setError(`Cancellation was not confirmed. ${errorText(caught)}`);
    }
  }
  async function review(reopen: boolean) {
    if (!detail) return;
    const selection = generation.current;
    setHistoryBusy(true);
    try {
      await request("presentation.workspace.reject_rehearsal_finding", {
        ...scope,
        finding_id: detail.finding.finding_id,
        reopen,
      });
      if (current(selection)) {
        const id = detail.finding.finding_id;
        await historyPage();
        await openDetail(id);
      }
    } catch (caught) {
      if (current(selection)) setError(errorText(caught));
    } finally {
      if (current(selection)) setHistoryBusy(false);
    }
  }
  if (!visible) return null;
  const finding = detail?.finding;
  const editable = Boolean(
    detail?.can_adopt &&
    finding?.disposition === "unreviewed" &&
    finding.current_slide_number === selectedSlide &&
    !disabled &&
    !busy &&
    !historyBusy,
  );
  const originalText =
    detail?.snapshot.point.source_kind === "native_text" &&
    finding?.current_span_status !== "missing";
  const matchingText =
    originalText &&
    selectedTextEditable &&
    finding?.object_id === selectedTextObjectId;
  const controlsDisabled = disabled || busy;
  return (
    <section
      className="pw-semantic-review"
      aria-label="Semantic rehearsal review"
    >
      <h4>Review a message against recorded speech</h4>
      <p className="muted">
        Choose the original message and one recorded speech window. Results are
        unverified model hints. Recording completeness, speaker identity and
        transcription accuracy are unverified.
      </p>
      <button
        className="secondary-button"
        type="button"

        disabled={controlsDisabled}
        onClick={() => void sessionPage(0)}
      >
        Refresh recorded Runs
      </button>
      {sessions && (
        <>
          <p>
            {sessions.total} ended Runs for this deck. A debrief is not
            required.
          </p>
          <label>
            Recorded Run
            <select
              aria-label="Semantic recorded Run"
              value={sessionId}
              disabled={controlsDisabled}
              onChange={(event) => void chooseSession(event.target.value)}
            >
              <option value="">Choose a Run</option>
              {sessions.sessions.map((item) => (
                <option key={item.session_id} value={item.session_id}>
                  {item.started_at} · Revision {item.source_revision_number}
                </option>
              ))}
            </select>
          </label>
          <div className="pw-semantic-actions">
            <button
              className="secondary-button"
              disabled={controlsDisabled || sessions.offset === 0}
              onClick={() =>
                void sessionPage(Math.max(0, sessions.offset - 20))
              }
            >
              Previous Runs
            </button>
            <button
              className="secondary-button"
              disabled={controlsDisabled || !sessions.has_more}
              onClick={() => void sessionPage(sessions.offset + 20)}
            >
              Next Runs
            </button>
          </div>
        </>
      )}
      {messages && (
        <>
          <p>
            {messages.total} supported original messages · Revision{" "}
            {messages.source_revision_number}. {messages.excluded_objects}{" "}
            objects have no supported text representation.
          </p>
          <label>
            Original message
            <select
              aria-label="Original rehearsal message"
              value={message?.object_id ?? ""}
              disabled={controlsDisabled}
              onChange={(event) => chooseMessage(event.target.value)}
            >
              <option value="">Choose a message</option>
              {messages.messages.map((item) => (
                <option key={item.object_id} value={item.object_id}>
                  Slide {item.source_slide_number} · {item.name} ·{" "}
                  {kinds[item.source_kind]}
                </option>
              ))}
            </select>
          </label>
          <div className="pw-semantic-actions">
            <button
              className="secondary-button"
              disabled={controlsDisabled || messages.offset === 0}
              onClick={() =>
                void messagePage(Math.max(0, messages.offset - 20))
              }
            >
              Previous messages
            </button>
            <button
              className="secondary-button"
              disabled={controlsDisabled || !messages.has_more}
              onClick={() => void messagePage(messages.offset + 20)}
            >
              Next messages
            </button>
          </div>
        </>
      )}
      {message && (
        <>
          <p>
            {kinds[message.source_kind]} · Original slide{" "}
            {message.source_slide_number} · Current{" "}
            {message.current_slide_number === null
              ? "slide removed"
              : `slide ${message.current_slide_number}`}{" "}
            · {message.current_span_status}
          </p>
          {message.source_kind === "native_chart_cache" && (
            <p>
              Raw chart cache values may differ from formatted values. The
              workbook is not verified.
            </p>
          )}
          {message.source_kind === "native_table_cells" && (
            <p>
              Cell text is shown in row order; visual relationships are not
              verified.
            </p>
          )}
          <label>
            Full original source
            <textarea
              ref={sourceText}
              aria-label="Full original rehearsal source"
              readOnly
              rows={5}
              value={message.text}
            />
          </label>
          <div className="pw-semantic-actions">
            <button
              className="secondary-button"
              disabled={controlsDisabled || !message.whole_message_selectable}
              onClick={() => chooseQuote(message.text)}
            >
              Use whole message
            </button>
            <button
              className="secondary-button"
              disabled={controlsDisabled}
              onClick={() => {
                const element = sourceText.current;
                if (element)
                  chooseQuote(
                    element.value.slice(
                      element.selectionStart,
                      element.selectionEnd,
                    ),
                  );
              }}
            >
              Use selected source span
            </button>
          </div>
          {!message.whole_message_selectable && (
            <p>
              This source exceeds 2,000 characters. Select an exact unique span
              of at most 2,000 characters.
            </p>
          )}
          <label>
            Exact message to review
            <textarea
              aria-label="Exact rehearsal message span"
              rows={3}
              value={quote}
              maxLength={2000}
              disabled={controlsDisabled}
              onChange={(event) => chooseQuote(event.target.value)}
            />
          </label>
          <button
            className="secondary-button"
            disabled={controlsDisabled || !quote.trim() || quote.length > 2000}
            onClick={() => void prepare()}
          >
            Prepare recorded speech windows
          </button>
        </>
      )}
      {prepared && (
        <>
          <p>
            {prepared.total_utterances} recorded utterances in{" "}
            {prepared.total_windows} windows for this original slide.{" "}
            {prepared.unmapped_session_utterances} Run utterances were unmapped;{" "}
            {prepared.excluded_actor_utterances} utterances had other actor
            labels.
          </p>
          {!prepared.total_windows ? (
            <p>
              No recorded speech is available for this message. This does not
              establish that it was omitted.
            </p>
          ) : (
            <>
              <label>
                Speech window
                <select
                  aria-label="Semantic speech window"
                  value={windowIndex}
                  disabled={controlsDisabled}
                  onChange={(event) => {
                    generation.current++;
                    reviewGeneration.current++;
                    setWindowIndex(event.target.value);
                    setJob(null);
                    setDetail(null);
                    setHistoryBusy(false);
                    setError(null);
                  }}
                >
                  <option value="">Choose one window</option>
                  {prepared.windows.map((item) => (
                    <option key={item.index} value={String(item.index)}>
                      Window {item.index + 1} of {prepared.total_windows} ·{" "}
                      {item.utterances.length} utterances
                    </option>
                  ))}
                </select>
              </label>
              <div className="pw-semantic-actions">
                <button
                  className="secondary-button"
                  disabled={controlsDisabled || prepared.offset === 0}
                  onClick={() =>
                    void prepare(Math.max(0, prepared.offset - 20))
                  }
                >
                  Previous speech windows
                </button>
                <button
                  className="secondary-button"
                  disabled={controlsDisabled || !prepared.has_more}
                  onClick={() => void prepare(prepared.offset + 20)}
                >
                  Next speech windows
                </button>
              </div>
              {prepared.windows
                .find((item) => String(item.index) === windowIndex)
                ?.utterances.map((item) => (
                  <blockquote key={item.utterance_id}>
                    {item.text}
                    <small>
                      {item.start_ms ?? "?"}–{item.end_ms ?? "?"} ms ·{" "}
                      {item.utterance_id}
                    </small>
                  </blockquote>
                ))}
              <button
                className="secondary-button"
                disabled={controlsDisabled || windowIndex === ""}
                onClick={() => void analyze()}
              >
                Analyze selected speech window
              </button>
            </>
          )}
        </>
      )}
      {busy && (
        <p role="status">
          {activeJob.current
            ? "Analyzing selected speech window…"
            : "Loading rehearsal review…"}
        </p>
      )}
      {job && (
        <p role="status">
          Analysis: {job.state}.{" "}
          {job.state === "committing" || job.state === "finishing"
            ? "Finishing storage; cancellation is no longer available."
            : ""}
        </p>
      )}
      {activeJob.current && (
        <button
          className="secondary-button"
          disabled={job !== null && !job.can_cancel}
          onClick={() => void cancelAnalysis()}
        >
          Cancel semantic analysis
        </button>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
      {sessionId && (
        <>
          <h5>Saved window results</h5>
          <button
            className="secondary-button"
            disabled={disabled || historyBusy}
            onClick={() => void historyPage()}
          >
            Refresh saved coverage results
          </button>
          {history && (
            <>
              <p>
                {history.total} saved results. Each result covers one speech
                window; other windows may still need review.
              </p>
              {history.analyses.map((item) => (
                <article className="pw-finding-card" key={item.finding_id}>
                  <span>
                    Original slide {item.source_slide_number} · Window{" "}
                    {item.window_index + 1} of {item.total_windows} ·{" "}
                    {item.status.replaceAll("_", " ")} · {item.disposition}
                  </span>
                  <button
                    className="secondary-button"
                    disabled={disabled || historyBusy}
                    onClick={() => void openDetail(item.finding_id)}
                  >
                    Review saved window result
                  </button>
                </article>
              ))}
              <div className="pw-semantic-actions">
                <button
                  className="secondary-button"
                  disabled={disabled || historyBusy || history.offset === 0}
                  onClick={() =>
                    void historyPage(Math.max(0, history.offset - 20))
                  }
                >
                  Previous results
                </button>
                <button
                  className="secondary-button"
                  disabled={disabled || historyBusy || !history.has_more}
                  onClick={() => void historyPage(history.offset + 20)}
                >
                  Next results
                </button>
              </div>
            </>
          )}
        </>
      )}
      {historyBusy && <p role="status">Verifying saved rehearsal result…</p>}
      {detail && finding && (
        <article
          aria-label="Verified semantic window result"
          className="pw-finding-card"
        >
          <h5>Unverified window coverage hint</h5>
          <p>
            Revision {finding.source_revision_number} · Original slide{" "}
            {finding.source_slide_number} · Window{" "}
            {detail.snapshot.window_index + 1} of{" "}
            {detail.snapshot.total_windows} · {detail.snapshot.provider_id}/
            {detail.snapshot.model_id}
          </p>
          <strong>Original native message</strong>
          <blockquote>{finding.quote}</blockquote>
          <strong>{detail.snapshot.hint.status.replaceAll("_", " ")}</strong>
          <p>{detail.snapshot.hint.reason}</p>
          <strong>Model-referenced recorded quotes</strong>
          {detail.snapshot.hint.quotes.length ? (
            detail.snapshot.hint.quotes.map((item, index) => (
              <blockquote key={`${item.utterance_id}:${index}`}>
                {item.quote}
                <small>{item.utterance_id}</small>
              </blockquote>
            ))
          ) : (
            <p>The model referenced no quote. This is not proof of omission.</p>
          )}
          <details>
            <summary>All speech supplied for this window</summary>
            {detail.snapshot.windows[0]?.utterances.map((item) => (
              <blockquote key={item.utterance_id}>
                {item.text}
                <small>
                  {item.start_ms ?? "?"}–{item.end_ms ?? "?"} ms ·{" "}
                  {item.utterance_id}
                </small>
              </blockquote>
            ))}
          </details>
          <p>
            Current source: {finding.current_span_status}. Recording context{" "}
            {detail.context_current ? "matches" : "changed"}. Review state:{" "}
            {finding.disposition}.
          </p>
          {!detail.context_current && (
            <p>
              Recording changed. Prepare and analyze the current context before
              adopting an edit.
            </p>
          )}
          {finding.current_slide_number === null ? (
            <p>The original slide was removed. Native edits are unavailable.</p>
          ) : (
            <button
              className="secondary-button"
              disabled={disabled || busy}
              onClick={() => onOpenSlide(finding.current_slide_number!)}
            >
              Open original message's current slide
            </button>
          )}
          <div className="pw-semantic-actions">
            <button
              className="secondary-button"
              disabled={!editable}
              onClick={() => onPrepare(finding, "notes")}
            >
              Prepare notes from original message
            </button>
            <button
              className="secondary-button"
              disabled={!editable || !originalText}
              onClick={() => onSelectTextObject(finding)}
            >
              Select original text object
            </button>
            <button
              className="secondary-button"
              disabled={!editable || !matchingText}
              onClick={() => onPrepare(finding, "text")}
            >
              Prepare original text edit
            </button>
            <button
              className="secondary-button"
              disabled={!editable || !matchingText}
              onClick={() => onPrepare(finding, "rewrite")}
            >
              Prepare semantic text rewrite
            </button>
          </div>
          {originalText && !matchingText && (
            <p>
              Select the original editable text object before preparing text or
              a rewrite.
            </p>
          )}
          {!originalText && (
            <p>
              Only notes can recover this original message; its text object is
              missing or not safely editable.
            </p>
          )}
          <p>
            Preparation creates a draft. Review the native preview and
            explicitly Save to change the presentation.
          </p>
          <button
            className="secondary-button"
            disabled={
              disabled || historyBusy || finding.disposition === "applied"
            }
            onClick={() => void review(finding.disposition === "rejected")}
          >
            {finding.disposition === "rejected"
              ? "Reopen semantic result"
              : "Dismiss semantic result"}
          </button>
        </article>
      )}
    </section>
  );
}
