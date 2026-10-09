import { useEffect, useRef, useState } from "react";
import { unwrapInvokeResult } from "../shared/protocol";

type Session = {
  session_id: string;
  revision_number: number;
  started_at: string;
  debrief_available: boolean;
};
type Metrics = Record<string, number>;
type Comparison = {
  document_id: string;
  revision_id: string;
  baseline: { session_id: string; totals: Metrics; unmapped: Metrics };
  comparison: { session_id: string; totals: Metrics; unmapped: Metrics };
  delta: Metrics;
  slides: Array<{
    slide_id: string;
    current_slide_number: number | null;
    baseline_slide_number: number | null;
    comparison_slide_number: number | null;
    baseline: Metrics | null;
    comparison: Metrics | null;
    delta: Metrics | null;
  }>;
  truncated: boolean;
  candidate_counts_may_be_capped: boolean;
  algorithm_versions_match: boolean;
};
const metrics = [
  ["duration_ms", "Session duration"],
  ["word_count", "Words"],
  ["utterance_count", "Utterances"],
  ["markers", "Your markers"],
  ["long_segments", "Long explanations"],
  ["evidence_review_candidates", "Evidence-review candidates"],
  ["best_explanation_candidates", "Explanation candidates"],
] as const;
function display(field: string, value: number | undefined, signed = false) {
  if (value === undefined) return "Unavailable";
  const amount = field.endsWith("_ms")
    ? `${(value / 1000).toFixed(1)} s`
    : String(value);
  return signed && value > 0 ? `+${amount}` : amount;
}
export function RehearsalComparison({
  projectId,
  documentId,
  revisionId,
  sessions,
  disabled,
  onOpenSlide,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  sessions: Session[];
  disabled: boolean;
  onOpenSlide: (ordinal: number) => void;
}) {
  const available = sessions.filter((session) => session.debrief_available);
  const [baseline, setBaseline] = useState(available.at(-1)?.session_id ?? "");
  const [comparison, setComparison] = useState(available[0]?.session_id ?? "");
  const [result, setResult] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(
    () => () => {
      generation.current += 1;
    },
    [],
  );
  if (available.length < 2)
    return (
      <p className="muted">
        Complete two rehearsals with debriefs to compare recorded observations.
      </p>
    );
  async function compare() {
    const request = ++generation.current;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const next = unwrapInvokeResult(
        await window.presenterCopilot.core.request<Comparison>(
          "presentation.workspace.compare_rehearsals",
          {
            project_id: projectId,
            document_id: documentId,
            expected_revision_id: revisionId,
            baseline_session_id: baseline,
            comparison_session_id: comparison,
          },
        ),
      );
      if (request !== generation.current) return;
      if (
        next.document_id !== documentId ||
        next.revision_id !== revisionId ||
        next.baseline.session_id !== baseline ||
        next.comparison.session_id !== comparison
      )
        throw new Error("The rehearsal comparison could not be verified.");
      setResult(next);
    } catch (caught) {
      if (request === generation.current)
        setError(
          caught instanceof Error
            ? caught.message
            : "Comparison is unavailable.",
        );
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }
  return (
    <section className="pw-comparison" aria-label="Compare rehearsals">
      <h4>Compare rehearsals</h4>
      <p className="muted">
        Recorded observations, with change measured as comparison minus
        baseline. Counts are review cues; they do not score presentation
        quality. Choose from the latest ten rehearsals.
      </p>
      {(
        [
          ["Baseline rehearsal", baseline, setBaseline],
          ["Comparison rehearsal", comparison, setComparison],
        ] as const
      ).map(([label, value, setter]) => (
        <label key={label}>
          {label}
          <select
            aria-label={label}
            value={value}
            disabled={disabled || busy}
            onChange={(event) => {
              setter(event.target.value);
              setResult(null);
              setError(null);
            }}
          >
            {available.map((session) => (
              <option key={session.session_id} value={session.session_id}>
                Revision {session.revision_number} ·{" "}
                {new Date(session.started_at).toLocaleString()} ·{" "}
                {session.session_id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
      ))}
      <button
        type="button"
        className="secondary-button"
        disabled={disabled || busy || baseline === comparison}
        onClick={() => void compare()}
      >
        {busy ? "Comparing…" : "Compare recorded rehearsals"}
      </button>
      {error ? <p role="alert">{error}</p> : null}
      {result ? (
        <>
          {!result.algorithm_versions_match ? (
            <p>
              These debriefs use different analysis versions. Candidate-count
              changes may reflect that difference.
            </p>
          ) : null}
          {result.candidate_counts_may_be_capped ? (
            <p>
              Some candidate or marker lists reached their storage limit. Counts
              may omit further observations.
            </p>
          ) : null}
          <div className="pw-comparison-table">
            <table aria-label="Rehearsal totals">
              <thead>
                <tr>
                  <th>Observation</th>
                  <th>Baseline</th>
                  <th title="Comparison rehearsal">Compare</th>
                  <th>Change</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map(([field, label]) => (
                  <tr key={field}>
                    <th scope="row">{label}</th>
                    <td>{display(field, result.baseline.totals[field])}</td>
                    <td>{display(field, result.comparison.totals[field])}</td>
                    <td>{display(field, result.delta[field], true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {Object.values(result.baseline.unmapped).some((value) => value > 0) ||
          Object.values(result.comparison.unmapped).some(
            (value) => value > 0,
          ) ? (
            <details>
              <summary>Observations without a matching slide</summary>
              <p>
                Some observations have no matching slide. They remain included
                in session totals and are excluded from slide deltas.
              </p>
              <div className="pw-comparison-table">
                <table aria-label="Unmapped rehearsal observations">
                  <thead>
                    <tr>
                      <th>Observation</th>
                      <th>Baseline</th>
                      <th title="Comparison rehearsal">Compare</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ["speaking_time_ms", "Speaking time"],
                      ...metrics.slice(1),
                    ].map(([field, label]) => (
                      <tr key={field}>
                        <th scope="row">{label}</th>
                        <td>
                          {display(field, result.baseline.unmapped[field])}
                        </td>
                        <td>
                          {display(field, result.comparison.unmapped[field])}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ) : null}
          {result.slides.map((slide) => (
            <details key={slide.slide_id}>
              <summary>
                {slide.current_slide_number !== null
                  ? `Current slide ${slide.current_slide_number}`
                  : "Slide removed from current deck"}{" "}
                · rehearsed as {slide.baseline_slide_number ?? "absent"} →{" "}
                {slide.comparison_slide_number ?? "absent"}
              </summary>
              {slide.current_slide_number !== null ? (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={disabled}
                  onClick={() => onOpenSlide(slide.current_slide_number!)}
                >
                  Open current slide {slide.current_slide_number}
                </button>
              ) : null}
              <div className="pw-comparison-table">
                <table aria-label={`Slide comparison ${slide.slide_id}`}>
                  <thead>
                    <tr>
                      <th>Observation</th>
                      <th>Baseline</th>
                      <th title="Comparison rehearsal">Compare</th>
                      <th>Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ["speaking_time_ms", "Speaking time"],
                      ...metrics.slice(1),
                    ].map(([field, label]) => (
                      <tr key={field}>
                        <th scope="row">{label}</th>
                        <td>
                          {slide.baseline
                            ? display(field, slide.baseline[field])
                            : "Absent"}
                        </td>
                        <td>
                          {slide.comparison
                            ? display(field, slide.comparison[field])
                            : "Absent"}
                        </td>
                        <td>
                          {slide.delta
                            ? display(field, slide.delta[field], true)
                            : "Unavailable"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ))}
          {result.truncated ? (
            <p>Only the first 200 matching slides are shown.</p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
