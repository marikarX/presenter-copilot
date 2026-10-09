import { useEffect, useRef, useState } from "react";
import { unwrapInvokeResult } from "../shared/protocol";

type Session = {
  session_id: string;
  revision_number: number;
  started_at: string;
  debrief_available: boolean;
};
type Metrics = {
  speaking_time_ms: number;
  word_count: number;
  utterance_count: number;
};
type Slide = {
  slide_id: string;
  current_slide_number: number | null;
  source_slide_number: number | null;
  native_text_words: number | null;
  native_text_objects: number | null;
  recorded: Metrics | null;
  recorded_visit: boolean | null;
  status:
    | "recorded_speech"
    | "visited_without_recorded_speech"
    | "no_recorded_visit_or_speech"
    | "not_rehearsed_revision";
};
type Coverage = {
  document_id: string;
  revision_id: string;
  session_id: string;
  source_revision_id: string;
  source_revision_number: number;
  session_word_count: number;
  session_utterance_count: number;
  unmapped: Metrics;
  totals: Record<string, number>;
  offset: number;
  limit: number;
  sort: string;
  filter: string;
  total_filtered: number;
  slides: Slide[];
};
const labels: Record<Slide["status"], string> = {
  recorded_speech: "Recorded speech",
  visited_without_recorded_speech: "Visited, with no recorded speech",
  no_recorded_visit_or_speech: "No recorded visit or speech",
  not_rehearsed_revision: "Added since this rehearsal",
};
const nonnegative = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const metricsValid = (value: Metrics) =>
  value &&
  nonnegative(value.word_count) &&
  nonnegative(value.utterance_count) &&
  nonnegative(value.speaking_time_ms);

export function RehearsalCoverage({
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
  const [sessionId, setSessionId] = useState(available[0]?.session_id ?? "");
  const [sort, setSort] = useState("native_words");
  const [filter, setFilter] = useState("all");
  const [result, setResult] = useState<Coverage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  function reset() {
    generation.current++;
    setResult(null);
    setBusy(false);
    setError(null);
  }
  async function inspect(offset = 0) {
    const request = ++generation.current;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const next = unwrapInvokeResult(
        await window.presenterCopilot.core.request<Coverage>(
          "presentation.workspace.rehearsal_coverage",
          {
            project_id: projectId,
            document_id: documentId,
            expected_revision_id: revisionId,
            session_id: sessionId,
            sort,
            filter,
            offset,
            limit: 20,
          },
        ),
      );
      if (request !== generation.current) return;
      if (
        next.document_id !== documentId ||
        next.revision_id !== revisionId ||
        next.session_id !== sessionId ||
        next.offset !== offset ||
        next.limit !== 20 ||
        next.sort !== sort ||
        next.filter !== filter ||
        !nonnegative(next.total_filtered) ||
        !Array.isArray(next.slides) ||
        next.slides.length > 20 ||
        !metricsValid(next.unmapped) ||
        !nonnegative(next.session_word_count) ||
        !nonnegative(next.session_utterance_count) ||
        !next.totals ||
        Object.values(next.totals).some((value) => !nonnegative(value)) ||
        next.slides.some(
          (slide) =>
            !slide ||
            typeof slide.slide_id !== "string" ||
            !Object.hasOwn(labels, slide.status) ||
            (slide.current_slide_number !== null &&
              (!nonnegative(slide.current_slide_number) ||
                slide.current_slide_number < 1)) ||
            (slide.source_slide_number !== null &&
              (!nonnegative(slide.source_slide_number) ||
                slide.source_slide_number < 1)) ||
            (slide.native_text_words !== null &&
              !nonnegative(slide.native_text_words)) ||
            (slide.native_text_objects !== null &&
              !nonnegative(slide.native_text_objects)) ||
            (slide.recorded !== null && !metricsValid(slide.recorded)),
        )
      )
        throw new Error("The rehearsal coverage could not be verified.");
      setResult(next);
    } catch (caught) {
      if (request === generation.current)
        setError(
          caught instanceof Error ? caught.message : "Coverage is unavailable.",
        );
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }
  if (!available.length) return null;
  return (
    <section className="pw-rehearsal-coverage" aria-label="Rehearsal coverage">
      <h4>Review slide density and recorded coverage</h4>
      <p className="muted">
        Native text counts come from the rehearsed revision. Recorded visits and
        speech show what this session captured. Missing speech can reflect
        microphone or slide-tracking gaps; it does not prove you skipped a
        topic. Images, visual complexity and speaker notes are excluded from
        text counts.
      </p>
      <label>
        Rehearsal to inspect
        <select
          aria-label="Coverage rehearsal"
          value={sessionId}
          disabled={disabled}
          onChange={(event) => {
            reset();
            setSessionId(event.target.value);
          }}
        >
          {available.map((session) => (
            <option key={session.session_id} value={session.session_id}>
              Revision {session.revision_number} ·{" "}
              {new Date(session.started_at).toLocaleString()}
            </option>
          ))}
        </select>
      </label>
      <label>
        Order slides
        <select
          aria-label="Coverage order"
          value={sort}
          disabled={disabled}
          onChange={(event) => {
            reset();
            setSort(event.target.value);
          }}
        >
          <option value="native_words">Most native text first</option>
          <option value="slide">Current slide order</option>
        </select>
      </label>
      <label>
        Show slides
        <select
          aria-label="Coverage filter"
          value={filter}
          disabled={disabled}
          onChange={(event) => {
            reset();
            setFilter(event.target.value);
          }}
        >
          <option value="all">All slides</option>
          <option value="no_speech">No recorded speech</option>
          <option value="no_visit">No recorded visit or speech</option>
        </select>
      </label>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled || busy || !sessionId}
        onClick={() => void inspect()}
      >
        Inspect rehearsal coverage
      </button>
      {busy ? (
        <p role="status">
          Inspecting the rehearsed snapshot and recorded coverage…
        </p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      {result ? (
        <>
          <p>
            Rehearsed revision {result.source_revision_number}:{" "}
            {result.totals.slides_with_recorded_speech} of{" "}
            {result.totals.source_slides} slides have recorded speech;{" "}
            {result.totals.slides_without_recorded_speech} have none.{" "}
            {result.session_word_count} recorded words in{" "}
            {result.session_utterance_count} utterances.
          </p>
          <p className="muted">
            {result.totals.slides_added_since_rehearsal} slides added and{" "}
            {result.totals.slides_removed_since_rehearsal} removed since this
            rehearsal. Text quantity is an observation for review, not a
            design-quality score. Speaking time sums recorded utterances and can
            include overlap.
          </p>
          {result.unmapped.utterance_count > 0 ? (
            <p>
              {result.unmapped.utterance_count} utterances (
              {result.unmapped.word_count} words) have no matching rehearsed
              slide. They are excluded from slide counts.
            </p>
          ) : null}
          <p>
            {result.total_filtered} matching slides · page{" "}
            {Math.floor(result.offset / 20) + 1} of{" "}
            {Math.max(1, Math.ceil(result.total_filtered / 20))}.
          </p>
          {!result.slides.length ? (
            <p>No slides match this coverage filter.</p>
          ) : null}
          {result.slides.map((slide) => (
            <article
              className="pw-finding"
              key={slide.slide_id}
              data-slide-id={slide.slide_id}
            >
              <h5>
                {slide.current_slide_number === null
                  ? `Removed slide (rehearsed slide ${slide.source_slide_number})`
                  : `Slide ${slide.current_slide_number}`}
              </h5>
              <p>
                {labels[slide.status]}
                {slide.source_slide_number !== null
                  ? ` · rehearsed slide ${slide.source_slide_number}`
                  : ""}
              </p>
              <p>
                Native text:{" "}
                {slide.native_text_words === null
                  ? "Unavailable in the rehearsed revision"
                  : `${slide.native_text_words} words in ${slide.native_text_objects} objects`}
                .
              </p>
              {slide.recorded ? (
                <p>
                  Recorded speech: {slide.recorded.word_count} words ·{" "}
                  {slide.recorded.utterance_count} utterances ·{" "}
                  {(slide.recorded.speaking_time_ms / 1000).toFixed(1)} s.
                </p>
              ) : null}
              {slide.current_slide_number !== null ? (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={disabled || busy}
                  onClick={() => onOpenSlide(slide.current_slide_number!)}
                >
                  Open current slide {slide.current_slide_number}
                </button>
              ) : (
                <p className="muted">
                  This slide is absent from the current revision.
                </p>
              )}
            </article>
          ))}
          <button
            type="button"
            className="secondary-button"
            disabled={busy || disabled || result.offset === 0}
            onClick={() => void inspect(Math.max(0, result.offset - 20))}
          >
            Previous coverage slides
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={
              busy || disabled || result.offset + 20 >= result.total_filtered
            }
            onClick={() => void inspect(result.offset + 20)}
          >
            Next coverage slides
          </button>
        </>
      ) : null}
    </section>
  );
}
