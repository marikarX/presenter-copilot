import { useEffect, useRef, useState } from "react";
import { errorText, request } from "./RehearsalObjectionReview";

type Scope = {
  project_id: string;
  document_id: string;
  expected_revision_id: string;
};
type Side = "left" | "right";
type Page = {
  document_id: string;
  revision_id: string;
  offset: number;
  total: number;
  has_more: boolean;
};
type Runs = Page & {
  sessions: {
    session_id: string;
    source_revision_number: number;
    started_at: string;
  }[];
};
type Analyses = Page & {
  session_id: string;
  analyses: {
    analysis_id: string;
    source_slide_number: number;
    window_index: number;
    total_windows: number;
    candidate_count: number;
    created_at: string;
  }[];
};
type Quote = { utterance_id: string; quote: string; recorded_actor?: string };
type Original = {
  analysis_id: string;
  revision_id: string;
  context_current: boolean;
  snapshot: { session_id: string; source_slide_number: number };
  findings: {
    finding_id: string;
    disposition: string;
    observation: { concern: string; concern_quotes: Quote[] };
  }[];
};
type Selected = {
  finding_id: string;
  concern: string;
  source_slide_number: number;
};
type ComparedCandidate = {
  finding_id: string;
  side: Side;
  session_id: string;
  source_slide_number: number;
  window_index: number;
  concern_label: string;
  answer_status: string;
  concern_quotes: Quote[];
  answer_quotes: Quote[];
  disposition: string;
  can_adopt: boolean;
  context_current: boolean;
  current_slide_number: number | null;
};
type Prepared = {
  document_id: string;
  revision_id: string;
  session_id: string;
  right_session_id: string;
  context_sha256: string;
  left: { candidates: ComparedCandidate[] };
  right: { candidates: ComparedCandidate[] };
};
type History = Page & {
  comparisons: {
    comparison_id: string;
    session_id: string;
    right_session_id: string;
    left_candidate_count: number;
    right_candidate_count: number;
    relationship_counts: Record<string, number>;
    model_id: string;
    created_at: string;
  }[];
};
type Detail = {
  comparison_id: string;
  revision_id: string;
  session_id: string;
  right_session_id: string;
  provider_id: string;
  model_id: string;
  context_current: boolean;
  left_finding_ids: string[];
  right_finding_ids: string[];
  candidates: Record<string, ComparedCandidate>;
  comparisons: {
    left_finding_id: string;
    right_finding_id: string;
    relationship: string;
    reason: string;
  }[];
};
type Job = Scope & {
  job_id: string;
  session_id: string;
  right_session_id?: string;
  analysis_kind: string;
  state: string;
  terminal: boolean;
  can_cancel: boolean;
  cancellation_accepted?: boolean;
  result: { comparison_id: string } | null;
  error: { message: string; code: string } | null;
};
type Active = {
  scope: Scope;
  generation: number;
  id: string | null;
  cancelled: boolean;
};

const MAX_PER_RUN = 4;
const relationshipLabels: Record<string, string> = {
  equivalent: "Possibly the same underlying concern",
  related: "Related topic, different concern",
  distinct: "Different concerns",
  unclear: "Relationship unclear",
};
const sideLabels: Record<Side, string> = {
  left: "First Run",
  right: "Second Run",
};

export function RehearsalObjectionComparison({
  projectId,
  documentId,
  revisionId,
  visible,
  disabled,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  visible: boolean;
  disabled: boolean;
}) {
  const scope: Scope = {
    project_id: projectId,
    document_id: documentId,
    expected_revision_id: revisionId,
  };
  const [runs, setRuns] = useState<Runs | null>(null);
  const [runIds, setRunIds] = useState<Record<Side, string>>({
    left: "",
    right: "",
  });
  const [analyses, setAnalyses] = useState<Record<Side, Analyses | null>>({
    left: null,
    right: null,
  });
  const [originals, setOriginals] = useState<Record<Side, Original | null>>({
    left: null,
    right: null,
  });
  const [selected, setSelected] = useState<Record<Side, Selected[]>>({
    left: [],
    right: [],
  });
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const generation = useRef(0);
  const mounted = useRef(false);
  const activeJob = useRef<Active | null>(null);
  const current = (id: number) => mounted.current && generation.current === id;

  function owned<T extends { document_id: string; revision_id: string }>(
    next: T,
  ): T {
    if (next.document_id !== documentId || next.revision_id !== revisionId)
      throw new Error(
        "This response does not match the selected presentation.",
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
  function invalidatePrepared() {
    setPrepared(null);
    setError(null);
    setNotice(null);
  }

  useEffect(() => {
    mounted.current = true;
    const id = ++generation.current;
    setRuns(null);
    setRunIds({ left: "", right: "" });
    setAnalyses({ left: null, right: null });
    setOriginals({ left: null, right: null });
    setSelected({ left: [], right: [] });
    setPrepared(null);
    setHistory(null);
    setDetail(null);
    setJob(null);
    setError(null);
    setNotice(null);
    setBusy(false);
    if (visible) {
      setBusy(true);
      void Promise.all([
        request<Runs>(
          "presentation.workspace.list_rehearsal_review_sessions",
          scope,
        ),
        request<History>(
          "presentation.workspace.list_rehearsal_objection_comparisons",
          scope,
        ),
      ])
        .then(([nextRuns, nextHistory]) => {
          if (!current(id)) return;
          setRuns(owned(nextRuns));
          setHistory(owned(nextHistory));
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
      if (activeJob.current) cancelCaptured(activeJob.current);
      activeJob.current = null;
    };
  }, [projectId, documentId, revisionId, visible]);

  useEffect(() => {
    if (disabled && activeJob.current) cancelCaptured(activeJob.current);
  }, [disabled]);

  async function chooseRun(side: Side, run: string) {
    const id = generation.current;
    invalidatePrepared();
    setRunIds((previous) => ({ ...previous, [side]: run }));
    setAnalyses((previous) => ({ ...previous, [side]: null }));
    setOriginals((previous) => ({ ...previous, [side]: null }));
    setSelected((previous) => ({ ...previous, [side]: [] }));
    if (!run) return;
    setBusy(true);
    try {
      const next = owned(
        await request<Analyses>(
          "presentation.workspace.list_rehearsal_objections_analyses",
          { ...scope, session_id: run },
        ),
      );
      if (next.session_id !== run)
        throw new Error("The saved analyses belong to another Run.");
      if (current(id))
        setAnalyses((previous) => ({ ...previous, [side]: next }));
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function analysisPage(side: Side, offset: number) {
    const id = generation.current;
    const run = runIds[side];
    setBusy(true);
    try {
      const next = owned(
        await request<Analyses>(
          "presentation.workspace.list_rehearsal_objections_analyses",
          { ...scope, session_id: run, offset },
        ),
      );
      if (next.session_id !== run)
        throw new Error("The saved analyses belong to another Run.");
      if (current(id))
        setAnalyses((previous) => ({ ...previous, [side]: next }));
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function openOriginal(side: Side, analysisId: string) {
    const id = generation.current;
    setOriginals((previous) => ({ ...previous, [side]: null }));
    if (!analysisId) return;
    setBusy(true);
    try {
      const next = await request<Original>(
        "presentation.workspace.get_rehearsal_objections_analysis",
        { ...scope, analysis_id: analysisId },
      );
      if (
        next.revision_id !== revisionId ||
        next.analysis_id !== analysisId ||
        next.snapshot.session_id !== runIds[side]
      )
        throw new Error("This saved analysis does not match the selected Run.");
      if (current(id))
        setOriginals((previous) => ({ ...previous, [side]: next }));
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  function toggle(side: Side, candidate: Selected, checked: boolean) {
    invalidatePrepared();
    setSelected((previous) => {
      const without = previous[side].filter(
        (item) => item.finding_id !== candidate.finding_id,
      );
      const next = checked ? [...without, candidate] : without;
      return { ...previous, [side]: next.slice(0, MAX_PER_RUN) };
    });
  }
  function selectionParams() {
    return {
      ...scope,
      left_finding_ids: selected.left.map((item) => item.finding_id),
      right_finding_ids: selected.right.map((item) => item.finding_id),
    };
  }
  async function prepare() {
    const id = generation.current;
    setBusy(true);
    setError(null);
    setNotice(null);
    setPrepared(null);
    try {
      const next = owned(
        await request<Prepared>(
          "presentation.workspace.prepare_rehearsal_objection_comparison",
          selectionParams(),
        ),
      );
      if (
        next.session_id !== runIds.left ||
        next.right_session_id !== runIds.right
      )
        throw new Error("The prepared comparison belongs to other Runs.");
      if (current(id)) setPrepared(next);
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function historyPage(offset = 0) {
    const id = generation.current;
    try {
      const next = owned(
        await request<History>(
          "presentation.workspace.list_rehearsal_objection_comparisons",
          { ...scope, offset },
        ),
      );
      if (current(id)) setHistory(next);
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    }
  }
  async function openDetail(comparisonId: string) {
    const id = generation.current;
    setBusy(true);
    setDetail(null);
    setError(null);
    try {
      const next = await request<Detail>(
        "presentation.workspace.get_rehearsal_objection_comparison",
        { ...scope, comparison_id: comparisonId },
      );
      const known = new Set(Object.keys(next.candidates ?? {}));
      if (
        next.revision_id !== revisionId ||
        next.comparison_id !== comparisonId ||
        next.session_id === next.right_session_id ||
        !Array.isArray(next.comparisons) ||
        next.comparisons.some(
          (pair) =>
            !known.has(pair.left_finding_id) ||
            !known.has(pair.right_finding_id) ||
            next.candidates[pair.left_finding_id]?.side !== "left" ||
            next.candidates[pair.right_finding_id]?.side !== "right",
        )
      )
        throw new Error(
          "This saved comparison does not match its original candidates.",
        );
      if (current(id)) setDetail(next);
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }
  async function start() {
    if (!prepared || busy || disabled || activeJob.current) return;
    const active: Active = {
      scope: { ...scope },
      generation: generation.current,
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
        "presentation.workspace.start_rehearsal_objection_comparison",
        {
          ...selectionParams(),
          expected_context_sha256: prepared.context_sha256,
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
          next.session_id !== prepared.session_id ||
          next.right_session_id !== prepared.right_session_id ||
          next.job_id !== active.id ||
          next.analysis_kind !== "comparison"
        )
          throw new Error("Comparison status does not match these Runs.");
        setJob(next);
        if (next.terminal) {
          activeJob.current = null;
          setBusy(false);
          if (next.state === "completed" && next.result) {
            setNotice(
              active.cancelled
                ? "Cancellation arrived after storage began. The saved comparison remains available."
                : "Saved this comparison. Review each pair; it does not change either Run's candidates.",
            );
            setPrepared(null);
            await historyPage();
            if (current(active.generation))
              await openDetail(next.result.comparison_id);
          } else if (next.state === "cancelled")
            setNotice("Comparison cancelled. Nothing was saved.");
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
              `Status check failed; the comparison may still be running. ${errorText(caught)}`,
            );
        }
      }
    } catch (caught) {
      cancelCaptured(active);
      if (current(active.generation)) {
        // A rejected Start means the prepared fingerprint is no longer trustworthy.
        setPrepared(null);
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
        "Cancellation requested. Waiting for the comparison to start so it can be cancelled.",
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
            : "Storage has begun or the worker has finished. Check the saved comparisons.",
        );
      }
    } catch (caught) {
      if (current(active.generation))
        setError(`Cancellation was not confirmed. ${errorText(caught)}`);
    }
  }
  async function review(candidate: ComparedCandidate) {
    if (!detail) return;
    const id = generation.current;
    setBusy(true);
    setError(null);
    try {
      await request("presentation.workspace.reject_rehearsal_finding", {
        ...scope,
        finding_id: candidate.finding_id,
        reopen: candidate.disposition === "rejected",
      });
      if (current(id)) await openDetail(detail.comparison_id);
    } catch (caught) {
      if (current(id)) setError(errorText(caught));
    } finally {
      if (current(id)) setBusy(false);
    }
  }

  if (!visible) return null;
  const controlsDisabled = disabled || busy;
  const runLabel = (session: string) => {
    const run = runs?.sessions.find((item) => item.session_id === session);
    return run
      ? `${run.started_at} · revision ${run.source_revision_number}`
      : "Recorded Run";
  };
  const excerpts = (items: Quote[], caption: string) => (
    <div>
      <h6>{caption}</h6>
      {items.map((quote, index) => (
        <div key={`${quote.utterance_id}:${index}`}>
          <small>
            Recorded label: {quote.recorded_actor ?? "unknown"} · identity and
            transcription unverified
          </small>
          <blockquote>{quote.quote}</blockquote>
        </div>
      ))}
    </div>
  );
  const candidateView = (
    candidate: ComparedCandidate | undefined,
    reviewable: boolean,
  ) =>
    candidate && (
      <div className="pw-comparison-candidate">
        <p>
          <strong>{sideLabels[candidate.side]}</strong> · original slide{" "}
          {candidate.source_slide_number} · window {candidate.window_index + 1}
        </p>
        <p>Unverified concern label: {candidate.concern_label}</p>
        {excerpts(candidate.concern_quotes, "Exact concern excerpts")}
        {candidate.answer_quotes.length > 0 &&
          excerpts(
            candidate.answer_quotes,
            "Separate possible answer excerpts",
          )}
        <p>
          Original review state: {candidate.disposition}
          {!candidate.context_current &&
            " · recording changed; this excerpt is historical"}
          {candidate.current_slide_number === null &&
            " · original slide removed from current revision"}
        </p>
        {reviewable && candidate.disposition !== "applied" && (
          <button
            className="secondary-button"
            disabled={controlsDisabled}
            onClick={() => void review(candidate)}
          >
            {candidate.disposition === "rejected"
              ? `Reopen ${sideLabels[candidate.side].toLowerCase()} candidate`
              : `Dismiss ${sideLabels[candidate.side].toLowerCase()} candidate`}
          </button>
        )}
      </div>
    );
  const sidePicker = (side: Side) => {
    const page = analyses[side];
    const original = originals[side];
    const chosen = selected[side];
    return (
      <fieldset className="pw-comparison-side" aria-label={sideLabels[side]}>
        <legend>{sideLabels[side]}</legend>
        <label>
          Recorded Run
          <select
            aria-label={`${sideLabels[side]} for comparison`}
            value={runIds[side]}
            disabled={controlsDisabled}
            onChange={(event) => void chooseRun(side, event.target.value)}
          >
            <option value="">Choose a Run</option>
            {runs?.sessions.map((run) => (
              <option
                key={run.session_id}
                value={run.session_id}
                disabled={
                  run.session_id === runIds[side === "left" ? "right" : "left"]
                }
              >
                {run.started_at} · Original revision{" "}
                {run.source_revision_number}
              </option>
            ))}
          </select>
        </label>
        {page && !page.total && (
          <p>
            No saved objection analyses for this Run. Detect concerns in a
            recorded window above first.
          </p>
        )}
        {page && page.total > 0 && (
          <>
            <label>
              Saved window analysis
              <select
                aria-label={`${sideLabels[side]} saved analysis`}
                value={original?.analysis_id ?? ""}
                disabled={controlsDisabled}
                onChange={(event) =>
                  void openOriginal(side, event.target.value)
                }
              >
                <option value="">Choose a saved analysis</option>
                {page.analyses.map((item) => (
                  <option key={item.analysis_id} value={item.analysis_id}>
                    Original slide {item.source_slide_number} · window{" "}
                    {item.window_index + 1}/{item.total_windows} ·{" "}
                    {item.candidate_count} candidates · {item.created_at}
                  </option>
                ))}
              </select>
            </label>
            <div className="pw-semantic-actions">
              <button
                className="secondary-button"
                disabled={controlsDisabled || page.offset === 0}
                onClick={() =>
                  void analysisPage(side, Math.max(0, page.offset - 20))
                }
              >
                Previous {sideLabels[side].toLowerCase()} analyses
              </button>
              <button
                className="secondary-button"
                disabled={controlsDisabled || !page.has_more}
                onClick={() => void analysisPage(side, page.offset + 20)}
              >
                Next {sideLabels[side].toLowerCase()} analyses
              </button>
            </div>
          </>
        )}
        {original && !original.context_current && (
          <p>
            This Run's recording changed. Its candidates cannot be compared
            until the original recording is restored.
          </p>
        )}
        {original && original.context_current && !original.findings.length && (
          <p>
            This window returned no concern candidates. That does not establish
            absence of concerns in the Run.
          </p>
        )}
        {original &&
          original.context_current &&
          original.findings.map((finding, index) => {
            const isChosen = chosen.some(
              (item) => item.finding_id === finding.finding_id,
            );
            return (
              <label key={finding.finding_id} className="pw-comparison-check">
                <span>
                  <input
                    type="checkbox"
                    aria-label={`${sideLabels[side]} candidate ${index + 1}`}
                    checked={isChosen}
                    disabled={
                      controlsDisabled ||
                      (!isChosen && chosen.length >= MAX_PER_RUN)
                    }
                    onChange={(event) =>
                      toggle(
                        side,
                        {
                          finding_id: finding.finding_id,
                          concern: finding.observation.concern,
                          source_slide_number:
                            original.snapshot.source_slide_number,
                        },
                        event.target.checked,
                      )
                    }
                  />{" "}
                  {finding.observation.concern} · review state{" "}
                  {finding.disposition}
                </span>
                <small>
                  “{finding.observation.concern_quotes[0]?.quote ?? ""}”
                </small>
              </label>
            );
          })}
        <p className="muted">
          {chosen.length} of {MAX_PER_RUN} selected
          {chosen.length > 0 &&
            `: ${chosen
              .map(
                (item) => `slide ${item.source_slide_number} – ${item.concern}`,
              )
              .join("; ")}`}
        </p>
      </fieldset>
    );
  };

  return (
    <section
      className="pw-semantic-review pw-objection-review pw-objection-comparison"
      aria-label="Cross-Run objection comparison"
    >
      <h4>Compare concerns across two Runs</h4>
      <p className="muted">
        Choose up to {MAX_PER_RUN} saved concern candidates from each of two
        different ended Runs. A model suggests whether each pair is the same
        underlying concern. This is unverified interpretation: it never merges
        candidates, changes their review state or approves edits, and a missing
        match does not mean a concern was absent.
      </p>
      {runs && runs.total < 2 && (
        <p>
          Comparison needs at least two ended Runs for this deck. Record another
          Run with Rehearse first.
        </p>
      )}
      {runs && runs.total >= 2 && (
        <div className="pw-comparison-sides">
          {sidePicker("left")}
          {sidePicker("right")}
        </div>
      )}
      <div className="pw-semantic-actions">
        <button
          className="secondary-button"
          disabled={
            controlsDisabled || !selected.left.length || !selected.right.length
          }
          onClick={() => void prepare()}
        >
          Prepare comparison
        </button>
        <button
          className="secondary-button"
          disabled={controlsDisabled || !prepared}
          onClick={() => void start()}
        >
          Compare selected concerns
        </button>
        {busy && activeJob.current && (
          <button
            className="secondary-button"
            disabled={job !== null && !job.can_cancel}
            onClick={() => void cancel()}
          >
            Cancel comparison
          </button>
        )}
      </div>
      {prepared && (
        <p role="status">
          Prepared {prepared.left.candidates.length} ×{" "}
          {prepared.right.candidates.length} pairs from{" "}
          {runLabel(prepared.session_id)} and{" "}
          {runLabel(prepared.right_session_id)}. Only the selected exact
          excerpts and unverified labels are sent to the reasoning provider.
        </p>
      )}
      {job && (
        <p role="status">
          Comparison: {job.state}
          {job.terminal ? " · worker finished" : " · worker active"}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
      <h5>Saved comparisons</h5>
      {history && (
        <>
          <p>{history.total} saved comparisons for this deck.</p>
          {history.comparisons.map((item) => (
            <div key={item.comparison_id}>
              <p>
                {runLabel(item.session_id)} vs {runLabel(item.right_session_id)}{" "}
                · {item.left_candidate_count}×{item.right_candidate_count} pairs
                · {item.relationship_counts.equivalent ?? 0} possibly same ·{" "}
                {item.created_at}
              </p>
              <button
                className="secondary-button"
                disabled={controlsDisabled}
                onClick={() => void openDetail(item.comparison_id)}
              >
                Review saved comparison
              </button>
            </div>
          ))}
          <div className="pw-semantic-actions">
            <button
              className="secondary-button"
              disabled={controlsDisabled || history.offset === 0}
              onClick={() => void historyPage(Math.max(0, history.offset - 20))}
            >
              Previous comparisons
            </button>
            <button
              className="secondary-button"
              disabled={controlsDisabled || !history.has_more}
              onClick={() => void historyPage(history.offset + 20)}
            >
              Next comparisons
            </button>
          </div>
        </>
      )}
      {detail && (
        <section aria-label="Verified objection comparison">
          <h5>
            {runLabel(detail.session_id)} vs {runLabel(detail.right_session_id)}
          </h5>
          <p>
            Unverified comparison from {detail.provider_id} · {detail.model_id}.
            Each candidate keeps its own review state. Open the original Run
            analysis above to prepare an edit.
          </p>
          {!detail.context_current && (
            <p>
              A compared Run's recording or original analysis changed. These
              pairs are historical.
            </p>
          )}
          {detail.comparisons.map((pair, index) => (
            <article
              key={`${pair.left_finding_id}:${pair.right_finding_id}`}
              aria-label={`Compared pair ${index + 1}`}
            >
              <h5>
                Pair {index + 1}:{" "}
                {relationshipLabels[pair.relationship] ??
                  "Relationship unverified"}
              </h5>
              <p>Unverified reason: {pair.reason}</p>
              <div className="pw-comparison-pair">
                {candidateView(detail.candidates[pair.left_finding_id], false)}
                {candidateView(detail.candidates[pair.right_finding_id], false)}
              </div>
            </article>
          ))}
          <h5>Original candidates in this comparison</h5>
          {[...detail.left_finding_ids, ...detail.right_finding_ids].map(
            (identity) => (
              <article key={identity} aria-label="Compared original candidate">
                {candidateView(detail.candidates[identity], true)}
              </article>
            ),
          )}
        </section>
      )}
    </section>
  );
}
