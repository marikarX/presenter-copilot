import { useEffect, useRef, useState } from "react";
import {
  unwrapInvokeResult,
  type RendererCoreMethod,
} from "../shared/protocol";
import type { RehearsalFinding } from "./RehearsalFindings";

type Scope = {
  project_id: string;
  document_id: string;
  expected_revision_id: string;
};
type Owned = { document_id: string; revision_id: string; session_id?: string };
type Page = Owned & { offset: number; total: number; has_more: boolean };
type Runs = Page & {
  sessions: {
    session_id: string;
    source_revision_number: number;
    started_at: string;
  }[];
};
type Slides = Page & {
  source_revision_number: number;
  slides: {
    slide_id: string;
    source_slide_number: number;
    current_slide_number: number | null;
  }[];
};
type Speech = {
  utterance_id: string;
  text: string;
  actor: string;
  start_ms: number | null;
  end_ms: number | null;
};
type Prepared = Owned & {
  slide_id: string;
  source_revision_id: string;
  source_slide_number: number;
  current_slide_number: number | null;
  context_sha256: string;
  recording_sha256: string;
  total_windows: number;
  total_utterances: number;
  unmapped_session_utterances: number;
  actor_counts: Record<string, number>;
  offset: number;
  has_more: boolean;
  windows: {
    index: number;
    utterances: Speech[];
    serialized_context_chars: number;
  }[];
};
type Quote = { utterance_id: string; quote: string };
type Candidate = {
  finding_id: string;
  disposition: string;
  can_adopt: boolean;
  finding: RehearsalFinding;
  observation: {
    concern: string;
    reason: string;
    answer_status: string;
    concern_quotes: Quote[];
    answer_quotes: Quote[];
  };
};
type Detail = {
  analysis_id: string;
  revision_id: string;
  context_current: boolean;
  source_revision_number: number;
  findings: Candidate[];
  snapshot: Prepared & {
    window_index: number;
    provider_id: string;
    model_id: string;
  };
};
type History = Page & {
  analyses: {
    analysis_id: string;
    source_slide_number: number;
    window_index: number;
    total_windows: number;
    candidate_count: number;
    created_at: string;
  }[];
};
type Job = Scope & {
  job_id: string;
  session_id: string;
  analysis_kind: string;
  state: string;
  terminal: boolean;
  can_cancel: boolean;
  cancellation_accepted?: boolean;
  result: { analysis_id: string; finding_ids: string[] } | null;
  error: { message: string; code: string } | null;
};
type Active = {
  scope: Scope;
  generation: number;
  sessionId: string;
  id: string | null;
  cancelled: boolean;
};

async function request<T>(
  method: RendererCoreMethod,
  params: Record<string, unknown>,
): Promise<T> {
  return unwrapInvokeResult(
    await window.presenterCopilot.core.request<T>(method, params),
  );
}
function errorText(caught: unknown): string {
  const value =
    caught !== null && typeof caught === "object"
      ? (caught as { message?: unknown; code?: unknown })
      : null;
  const message =
    typeof value?.message === "string" && value.message
      ? value.message
      : "Objection review is unavailable.";
  const code = typeof value?.code === "string" ? value.code : "";
  const recovery: Record<string, string> = {
    PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED:
      "This project is Local Only. Choose a local reasoning provider in Setup & settings, then retry.",
    PRIVACY_REMOTE_ACK_REQUIRED:
      "Review remote reasoning acknowledgement in Project settings before choosing to send recorded context.",
    PROVIDER_UNCONFIGURED:
      "Open Setup & settings and configure a ready reasoning provider that supports objection review, then retry.",
    PROVIDER_UNAVAILABLE:
      "Check the selected reasoning provider in Setup & settings. Restore its readiness or choose another supported provider, then retry.",
    PROVIDER_TASK_UNSUPPORTED:
      "Choose a reasoning provider that supports objection review in Setup & settings, then retry.",
    PRIVACY_POLICY_CHANGED:
      "Review the current Project settings, select the recorded Run, slide and speech window again, then retry.",
    REHEARSAL_CONTEXT_CHANGED:
      "Select the recorded Run, slide and speech window again to prepare the updated recording before retrying.",
  };
  const hint = Object.hasOwn(recovery, code) ? recovery[code] : null;
  return `${message}${code ? ` (${code})` : ""}${hint ? ` ${hint}` : ""}`;
}
const answerLabels: Record<string, string> = {
  addressed: "Possible answer observed",
  partially_addressed: "Possible partial answer observed",
  not_observed: "No answer excerpt returned",
  unclear: "Answer relationship unclear",
};

export function RehearsalObjectionReview({
  projectId,
  documentId,
  revisionId,
  visible,
  disabled,
  selectedSlide,
  selectedTextEditable,
  onOpenSlide,
  onPrepare,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  visible: boolean;
  disabled: boolean;
  selectedSlide: number;
  selectedTextEditable: boolean;
  onOpenSlide: (ordinal: number) => void;
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
  const [runs, setRuns] = useState<Runs | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [slides, setSlides] = useState<Slides | null>(null);
  const [slideId, setSlideId] = useState("");
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [windowIndex, setWindowIndex] = useState("");
  const [history, setHistory] = useState<History | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const generation = useRef(0);
  const reviewGeneration = useRef(0);
  const mounted = useRef(false);
  const activeJob = useRef<Active | null>(null);
  const current = (id: number) => mounted.current && generation.current === id;

  function verify<T extends Owned>(next: T, run?: string): T {
    if (
      next.document_id !== documentId ||
      next.revision_id !== revisionId ||
      (run !== undefined && next.session_id !== run)
    )
      throw new Error(
        "This response does not match the selected presentation and Run.",
      );
    return next;
  }
  function cancelCaptured(active: Active) {
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
    setDetail(null);
    setJob(null);
    setBusy(false);
    setReviewBusy(false);
    setError(null);
    setNotice(null);
  }

  useEffect(() => {
    mounted.current = true;
    generation.current++;
    reviewGeneration.current++;
    const id = generation.current;
    setRuns(null);
    setSessionId("");
    setSlides(null);
    setSlideId("");
    setPrepared(null);
    setWindowIndex("");
    setHistory(null);
    setDetail(null);
    setJob(null);
    setError(null);
    setNotice(null);
    setBusy(false);
    setReviewBusy(false);
    if (visible) {
      setBusy(true);
      void request<Runs>(
        "presentation.workspace.list_rehearsal_review_sessions",
        scope,
      )
        .then((next) => {
          verify(next);
          if (current(id)) setRuns(next);
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
    if (disabled && activeJob.current) cancelCaptured(activeJob.current);
  }, [disabled]);

  async function runPage(offset: number) {
    invalidate();
    setSessionId("");
    setSlides(null);
    setSlideId("");
    setHistory(null);
    const id = generation.current;
    setBusy(true);
    try {
      const next = verify(
        await request<Runs>(
          "presentation.workspace.list_rehearsal_review_sessions",
          { ...scope, offset },
        ),
      );
      if (current(id)) setRuns(next);
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function chooseRun(run: string) {
    invalidate();
    setSessionId(run);
    setSlides(null);
    setSlideId("");
    setHistory(null);
    if (!run) return;
    const id = generation.current;
    setBusy(true);
    try {
      const [nextSlides, nextHistory] = await Promise.all([
        request<Slides>("presentation.workspace.list_rehearsal_review_slides", {
          ...scope,
          session_id: run,
        }),
        request<History>(
          "presentation.workspace.list_rehearsal_objections_analyses",
          { ...scope, session_id: run },
        ),
      ]);
      verify(nextSlides, run);
      verify(nextHistory, run);
      if (current(id)) {
        setSlides(nextSlides);
        setHistory(nextHistory);
      }
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function slidePage(offset: number) {
    invalidate();
    setSlideId("");
    const id = generation.current;
    setBusy(true);
    try {
      const next = verify(
        await request<Slides>(
          "presentation.workspace.list_rehearsal_review_slides",
          { ...scope, session_id: sessionId, offset },
        ),
        sessionId,
      );
      if (current(id)) setSlides(next);
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function prepareWindow(selected: string, offset: number) {
    invalidate();
    setSlideId(selected);
    if (!selected) return;
    const id = generation.current;
    setBusy(true);
    try {
      const next = verify(
        await request<Prepared>(
          "presentation.workspace.prepare_rehearsal_objections_review",
          {
            ...scope,
            session_id: sessionId,
            slide_id: selected,
            offset,
            limit: 1,
          },
        ),
        sessionId,
      );
      if (next.slide_id !== selected)
        throw new Error(
          "The prepared window belongs to another original slide.",
        );
      if (current(id)) setPrepared(next);
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function historyPage(offset = 0) {
    const selection = generation.current,
      requestId = ++reviewGeneration.current;
    setReviewBusy(true);
    setError(null);
    try {
      const next = verify(
        await request<History>(
          "presentation.workspace.list_rehearsal_objections_analyses",
          { ...scope, session_id: sessionId, offset },
        ),
        sessionId,
      );
      if (current(selection) && requestId === reviewGeneration.current)
        setHistory(next);
    } catch (caught) {
      if (current(selection) && requestId === reviewGeneration.current)
        setError(errorText(caught));
    } finally {
      if (current(selection) && requestId === reviewGeneration.current)
        setReviewBusy(false);
    }
  }
  async function openDetail(analysisId: string) {
    const selection = generation.current,
      requestId = ++reviewGeneration.current;
    setReviewBusy(true);
    setDetail(null);
    setError(null);
    try {
      const next = await request<Detail>(
        "presentation.workspace.get_rehearsal_objections_analysis",
        { ...scope, analysis_id: analysisId },
      );
      if (
        next.revision_id !== revisionId ||
        next.analysis_id !== analysisId ||
        next.snapshot.session_id !== sessionId ||
        !Array.isArray(next.findings) ||
        next.findings.some(
          (candidate) =>
            candidate.finding.kind !== "semantic_objection" ||
            candidate.finding.finding_id !== candidate.finding_id ||
            candidate.finding.session_id !== sessionId ||
            candidate.finding.slide_id !== next.snapshot.slide_id,
        )
      )
        throw new Error(
          "This saved analysis does not match the selected Run or candidate.",
        );
      if (current(selection) && requestId === reviewGeneration.current)
        setDetail(next);
    } catch (caught) {
      if (current(selection) && requestId === reviewGeneration.current)
        setError(errorText(caught));
    } finally {
      if (current(selection) && requestId === reviewGeneration.current)
        setReviewBusy(false);
    }
  }
  async function analyze() {
    if (
      !prepared ||
      windowIndex === "" ||
      busy ||
      disabled ||
      activeJob.current
    )
      return;
    const active: Active = {
      scope: { ...scope },
      generation: generation.current,
      sessionId,
      id: null,
      cancelled: false,
    };
    activeJob.current = active;
    setBusy(true);
    setError(null);
    setNotice(null);
    setDetail(null);
    setJob(null);
    try {
      let next = await request<Job>(
        "presentation.workspace.start_rehearsal_objections_analysis",
        {
          ...active.scope,
          session_id: sessionId,
          slide_id: prepared.slide_id,
          expected_context_sha256: prepared.context_sha256,
          expected_recording_sha256: prepared.recording_sha256,
          window_index: Number(windowIndex),
        },
      );
      active.id = next.job_id;
      if (!current(active.generation) || active.cancelled)
        cancelCaptured(active);
      while (current(active.generation) && activeJob.current === active) {
        if (
          next.project_id !== active.scope.project_id ||
          next.document_id !== active.scope.document_id ||
          next.expected_revision_id !== active.scope.expected_revision_id ||
          next.session_id !== active.sessionId ||
          next.job_id !== active.id ||
          next.analysis_kind !== "objections"
        )
          throw new Error(
            "Analysis status does not match this objection selection.",
          );
        setJob(next);
        if (next.terminal) {
          activeJob.current = null;
          setBusy(false);
          if (next.state === "completed") {
            setNotice(
              active.cancelled
                ? "Cancellation arrived after storage began. The saved window remains available for review."
                : `Saved this window analysis with ${next.result?.finding_ids.length ?? 0} concern candidates. Review it before preparing an edit.`,
            );
            await historyPage();
          } else if (next.state === "cancelled")
            setNotice("Analysis cancelled. No window result was saved.");
          else if (next.error) setError(errorText(next.error));
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
  async function cancel() {
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
            : "Storage has begun or the worker has finished. Check its final status and saved history.",
        );
      }
    } catch (caught) {
      if (current(active.generation))
        setError(`Cancellation was not confirmed. ${errorText(caught)}`);
    }
  }
  async function review(candidate: Candidate, reopen: boolean) {
    if (!detail) return;
    const selection = generation.current,
      analysisId = detail.analysis_id;
    setReviewBusy(true);
    setError(null);
    try {
      await request("presentation.workspace.reject_rehearsal_finding", {
        ...scope,
        finding_id: candidate.finding_id,
        reopen,
      });
      if (current(selection)) {
        await historyPage();
        if (current(selection)) await openDetail(analysisId);
      }
    } catch (caught) {
      if (current(selection)) setError(errorText(caught));
    } finally {
      if (current(selection)) setReviewBusy(false);
    }
  }

  if (!visible) return null;
  const controlsDisabled = disabled || busy || reviewBusy;
  const selectedWindow = prepared?.windows[0];
  const quotes = (items: Quote[], caption: string) => (
    <div>
      <h6>{caption}</h6>
      {items.map((quote, index) => {
        const utterance = detail?.snapshot.windows[0]?.utterances.find(
          (speech) => speech.utterance_id === quote.utterance_id,
        );
        return (
          <div key={`${quote.utterance_id}:${index}`}>
            <small>
              Recorded label: {utterance?.actor ?? "unknown"} · identity and
              transcription unverified
            </small>
            <blockquote>{quote.quote}</blockquote>
          </div>
        );
      })}
    </div>
  );
  return (
    <section
      className="pw-semantic-review pw-objection-review"
      aria-label="Recorded objection review"
    >
      <h4>Review possible concerns and answers</h4>
      <p className="muted">
        Choose an original slide and one recorded speech window. Concern and
        answer relationships are unverified model interpretations. Recording
        completeness, speaker identity and transcription accuracy are
        unverified.
      </p>
      <button
        type="button"
        className="secondary-button"
        disabled={controlsDisabled}
        onClick={() => void runPage(0)}
      >
        Refresh objection Runs
      </button>
      {runs && (
        <>
          <p>
            {runs.total} ended Runs for this deck. A debrief is not required.
          </p>
          {!runs.total && (
            <p>
              Use Rehearse in the presentation toolbar to record a Run first.
            </p>
          )}
          <label>
            Recorded Run
            <select
              aria-label="Objection recorded Run"
              value={sessionId}
              disabled={controlsDisabled}
              onChange={(event) => void chooseRun(event.target.value)}
            >
              <option value="">Choose a Run</option>
              {runs.sessions.map((run) => (
                <option key={run.session_id} value={run.session_id}>
                  {run.started_at} · Original revision{" "}
                  {run.source_revision_number}
                </option>
              ))}
            </select>
          </label>
          <div className="pw-semantic-actions">
            <button
              className="secondary-button"
              disabled={controlsDisabled || runs.offset === 0}
              onClick={() => void runPage(Math.max(0, runs.offset - 20))}
            >
              Previous objection Runs
            </button>
            <button
              className="secondary-button"
              disabled={controlsDisabled || !runs.has_more}
              onClick={() => void runPage(runs.offset + 20)}
            >
              Next objection Runs
            </button>
          </div>
        </>
      )}
      {slides && (
        <>
          <p>
            {slides.total} original slides in revision{" "}
            {slides.source_revision_number}. A native text object is not
            required.
          </p>
          <label>
            Original slide
            <select
              aria-label="Objection original slide"
              value={slideId}
              disabled={controlsDisabled}
              onChange={(event) => void prepareWindow(event.target.value, 0)}
            >
              <option value="">Choose an original slide</option>
              {slides.slides.map((slide) => (
                <option key={slide.slide_id} value={slide.slide_id}>
                  Original slide {slide.source_slide_number} ·{" "}
                  {slide.current_slide_number === null
                    ? "Removed from current revision"
                    : `Current slide ${slide.current_slide_number}`}
                </option>
              ))}
            </select>
          </label>
          <div className="pw-semantic-actions">
            <button
              className="secondary-button"
              disabled={controlsDisabled || slides.offset === 0}
              onClick={() => void slidePage(Math.max(0, slides.offset - 20))}
            >
              Previous original slides
            </button>
            <button
              className="secondary-button"
              disabled={controlsDisabled || !slides.has_more}
              onClick={() => void slidePage(slides.offset + 20)}
            >
              Next original slides
            </button>
          </div>
        </>
      )}
      {prepared && (
        <>
          <h5>Prepared recorded speech</h5>
          <p>
            {prepared.total_utterances} recorded utterances on original slide{" "}
            {prepared.source_slide_number} across {prepared.total_windows}{" "}
            bounded windows. {prepared.unmapped_session_utterances} Run
            utterances have no original slide mapping.
          </p>
          <p>
            Recorded actor labels:{" "}
            {Object.entries(prepared.actor_counts)
              .map(([actor, count]) => `${actor}: ${count}`)
              .join(" · ") || "none"}
            . These labels do not verify speaker identity.
          </p>
          {!selectedWindow && (
            <p>
              No recorded speech window is available for this original slide.
              This is not evidence that no concern was raised.
            </p>
          )}
          {selectedWindow && (
            <>
              <label>
                Recorded speech window
                <select
                  aria-label="Objection speech window"
                  value={windowIndex}
                  disabled={controlsDisabled}
                  onChange={(event) => setWindowIndex(event.target.value)}
                >
                  <option value="">
                    Choose this window after reviewing its speech
                  </option>
                  <option value={selectedWindow.index}>
                    Window {selectedWindow.index + 1} of{" "}
                    {prepared.total_windows}
                  </option>
                </select>
              </label>
              {selectedWindow.utterances.map((speech) => (
                <div key={speech.utterance_id}>
                  <small>
                    Recorded label: {speech.actor} · {speech.start_ms ?? "?"}–
                    {speech.end_ms ?? "?"} ms · unverified
                  </small>
                  <blockquote>{speech.text}</blockquote>
                </div>
              ))}
              <div className="pw-semantic-actions">
                <button
                  className="secondary-button"
                  disabled={controlsDisabled || prepared.offset === 0}
                  onClick={() =>
                    void prepareWindow(slideId, prepared.offset - 1)
                  }
                >
                  Previous objection window
                </button>
                <button
                  className="secondary-button"
                  disabled={controlsDisabled || !prepared.has_more}
                  onClick={() =>
                    void prepareWindow(slideId, prepared.offset + 1)
                  }
                >
                  Next objection window
                </button>
                <button
                  className="secondary-button"
                  disabled={controlsDisabled || windowIndex === ""}
                  onClick={() => void analyze()}
                >
                  Detect concerns in selected window
                </button>
              </div>
            </>
          )}
        </>
      )}
      {job && (
        <p role="status">
          Objection analysis: {job.state}
          {job.terminal ? " · worker finished" : " · worker active"}
        </p>
      )}
      {busy && (
        <button
          className="secondary-button"
          disabled={job !== null && !job.can_cancel}
          onClick={() => void cancel()}
        >
          Cancel objection analysis
        </button>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
      {busy && !job && (
        <p role="status">Preparing recorded objection context…</p>
      )}
      {sessionId && (
        <>
          <h5>Saved objection window analyses</h5>
          <button
            className="secondary-button"
            disabled={controlsDisabled}
            onClick={() => void historyPage()}
          >
            Refresh saved objection analyses
          </button>
          {history && (
            <>
              <p>
                {history.total} saved analyses. Each covers one recorded window;
                empty results remain in history.
              </p>
              {history.analyses.map((summary) => (
                <div key={summary.analysis_id}>
                  <p>
                    Original slide {summary.source_slide_number} · Window{" "}
                    {summary.window_index + 1}/{summary.total_windows} ·{" "}
                    {summary.candidate_count} concern candidates ·{" "}
                    {summary.created_at}
                  </p>
                  <button
                    className="secondary-button"
                    disabled={controlsDisabled}
                    onClick={() => void openDetail(summary.analysis_id)}
                  >
                    Review saved objection analysis
                  </button>
                </div>
              ))}
              <div className="pw-semantic-actions">
                <button
                  className="secondary-button"
                  disabled={controlsDisabled || history.offset === 0}
                  onClick={() =>
                    void historyPage(Math.max(0, history.offset - 20))
                  }
                >
                  Previous objection analyses
                </button>
                <button
                  className="secondary-button"
                  disabled={controlsDisabled || !history.has_more}
                  onClick={() => void historyPage(history.offset + 20)}
                >
                  Next objection analyses
                </button>
              </div>
            </>
          )}
        </>
      )}
      {reviewBusy && <p role="status">Verifying saved objection candidates…</p>}
      {detail && (
        <section aria-label="Verified objection analysis">
          <h5>
            Original revision {detail.source_revision_number} · Slide{" "}
            {detail.snapshot.source_slide_number} · Window{" "}
            {detail.snapshot.window_index + 1}/{detail.snapshot.total_windows}
          </h5>
          <p>
            Unverified analysis from {detail.snapshot.provider_id} ·{" "}
            {detail.snapshot.model_id}. Applies to this recorded window only.
          </p>
          {!detail.context_current && (
            <p>
              The recording changed. Historical excerpts remain available;
              preparing an edit is disabled.
            </p>
          )}
          {!detail.findings.length && (
            <p>
              No concern candidate was returned for this window. This does not
              establish absence of concerns in the Run.
            </p>
          )}
          {detail.findings.map((candidate, index) => {
            const onSlide =
              candidate.finding.current_slide_number === selectedSlide;
            const editable =
              candidate.can_adopt &&
              candidate.finding.context_current === true &&
              candidate.disposition === "unreviewed" &&
              onSlide &&
              !controlsDisabled;
            const observation = candidate.observation;
            return (
              <article
                key={candidate.finding_id}
                aria-label={`Recorded concern candidate ${index + 1}`}
              >
                <h5>
                  Possible concern {index + 1}: {observation.concern}
                </h5>
                <p>Unverified interpretation: {observation.reason}</p>
                <p>Review state: {candidate.disposition}</p>
                {quotes(observation.concern_quotes, "Exact concern excerpts")}
                <p>
                  {answerLabels[observation.answer_status] ??
                    "Answer relationship unverified"}{" "}
                  · unverified, this window only.
                </p>
                {observation.answer_quotes.length ? (
                  quotes(
                    observation.answer_quotes,
                    "Separate possible answer excerpts",
                  )
                ) : (
                  <p>
                    No possible answer excerpt was returned. Other windows and
                    Runs were not assessed.
                  </p>
                )}
                {candidate.finding.current_slide_number === null ? (
                  <p>The original slide is absent from the current revision.</p>
                ) : (
                  !onSlide && (
                    <button
                      className="secondary-button"
                      disabled={controlsDisabled}
                      onClick={() =>
                        onOpenSlide(candidate.finding.current_slide_number!)
                      }
                    >
                      Open current slide for concern
                    </button>
                  )
                )}
                <div className="pw-semantic-actions">
                  <button
                    className="secondary-button"
                    disabled={!editable}
                    onClick={() => onPrepare(candidate.finding, "notes")}
                  >
                    Prepare concern in notes
                  </button>
                  <button
                    className="secondary-button"
                    disabled={!editable || !selectedTextEditable}
                    onClick={() => onPrepare(candidate.finding, "text")}
                  >
                    Prepare concern in selected text
                  </button>
                  <button
                    className="secondary-button"
                    disabled={!editable || !selectedTextEditable}
                    onClick={() => onPrepare(candidate.finding, "rewrite")}
                  >
                    Suggest selected text from concern
                  </button>
                  {candidate.disposition !== "applied" && (
                    <button
                      className="secondary-button"
                      disabled={controlsDisabled}
                      onClick={() =>
                        void review(
                          candidate,
                          candidate.disposition === "rejected",
                        )
                      }
                    >
                      {candidate.disposition === "rejected"
                        ? "Reopen concern candidate"
                        : "Dismiss concern candidate"}
                    </button>
                  )}
                </div>
                <p className="muted">
                  Choose a current native text target for text edits. Notes
                  preparation appends exact concern excerpts locally. Review the
                  draft, Preview and Save before the presentation changes; model
                  labels and possible answers are kept separate.
                </p>
              </article>
            );
          })}
        </section>
      )}
    </section>
  );
}
