import { useEffect, useMemo, useRef, useState } from "react";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import type { ClaimCandidate, ClaimExtractionResult } from "./ClaimDiscovery";
import { claimSourceLabel, NATIVE_CLAIM_DISCLOSURE } from "./claim-source";
import {
  retainScanCache,
  reusableScanBatches,
  scanCacheKey,
  uniqueScanCandidates,
  validScanResult,
  type ClaimScanCache,
  type CompletedScanBatch,
  type NativeScanText,
  type ScanSlide,
} from "./claim-scan-state";
type Page = {
  document_id: string;
  revision_id: string;
  total_slides: number;
  offset: number;
  has_more: boolean;
  items: ScanSlide[];
};

export function DeckClaimScan({
  scope,
  visible,
  disabled,
  onReview,
  cache,
}: {
  scope: { project_id: string; document_id: string; revision_id: string };
  visible: boolean;
  disabled: boolean;
  cache: ClaimScanCache;
  onReview: (
    slide: { slide_id: string; slide_number: number },
    candidate: ClaimCandidate,
  ) => void;
}) {
  const key = JSON.stringify(scope);
  const current = useRef(key);
  current.current = key;
  const owner = useRef({ live: true, generation: 0 });
  const cacheKey = scanCacheKey(scope.project_id, scope.document_id);
  const [slides, setSlides] = useState<ScanSlide[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [completed, setCompleted] = useState<CompletedScanBatch[]>([]);
  const [slidePage, setSlidePage] = useState(0);
  const [candidatePage, setCandidatePage] = useState(0);
  const [phase, setPhase] = useState<
    "idle" | "preparing" | "ready" | "running" | "stopping"
  >("idle");
  const [confirmed, setConfirmed] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const working =
    phase === "preparing" || phase === "running" || phase === "stopping";
  const selectedIds = useMemo(() => new Set(selected), [selected]);
  const chosen = slides?.filter((s) => selectedIds.has(s.slide_id)) ?? [];
  const selectedCompleted = useMemo(
    () => completed.filter((entry) => selectedIds.has(entry.slide.slide_id)),
    [completed, selectedIds],
  );
  const reusedCount = selectedCompleted.filter((entry) => entry.carried).length;
  const tasks = chosen.flatMap((slide) =>
    slide.batches.map((batch, index) => ({ slide, batch, index })),
  );
  const unique = useMemo(
    () => uniqueScanCandidates(selectedCompleted),
    [selectedCompleted],
  );
  const remainingCount = tasks.length - selectedCompleted.length;
  const currentCandidatePage = Math.min(
    candidatePage,
    Math.max(0, Math.ceil(unique.length / 20) - 1),
  );

  useEffect(() => {
    owner.current.live = true;
    return () => {
      owner.current.live = false;
      owner.current.generation++;
    };
  }, []);
  useEffect(() => {
    owner.current.generation++;
    setSlides(null);
    setCompleted([]);
    setSelected([]);
    setConfirmed(false);
    setPhase("idle");
    setError("");
    setMessage("");
    setSlidePage(0);
    setCandidatePage(0);
  }, [key]);
  useEffect(() => {
    if (!visible && working) stop();
  }, [visible]);
  function stop() {
    owner.current.generation++;
    setPhase("stopping");
    setConfirmed(false);
    setMessage(
      "Stopping after the current request. Completed candidates remain unsaved.",
    );
  }
  async function prepare(incremental = false) {
    const generation = ++owner.current.generation,
      requested = key;
    const active = () =>
      owner.current.live &&
      owner.current.generation === generation &&
      current.current === requested;
    setPhase("preparing");
    setError("");
    setMessage("Preparing native text inventory; no provider calls.");
    setSlides(null);
    setCompleted([]);
    setConfirmed(false);
    setSlidePage(0);
    setCandidatePage(0);
    const previous = incremental ? (cache.get(cacheKey) ?? []) : [];
    if (!incremental) cache.delete(cacheKey);
    try {
      const all: ScanSlide[] = [];
      const seenSlides = new Set<string>();
      let offset = 0,
        total: number | null = null;
      do {
        const page = unwrapInvokeResult<Page>(
          await window.presenterCopilot.core.request(
            "presentation.workspace.prepare_claim_scan",
            { ...scope, offset, limit: 20 },
          ),
        );
        if (!active()) return;
        if (
          page.document_id !== scope.document_id ||
          page.revision_id !== scope.revision_id ||
          page.offset !== offset ||
          !Array.isArray(page.items) ||
          !Number.isInteger(page.total_slides) ||
          page.total_slides < 0 ||
          page.total_slides > 5000 ||
          (total !== null && total !== page.total_slides) ||
          (page.has_more && !page.items.length)
        )
          throw new Error(
            "The deck scan inventory no longer matches this revision.",
          );
        total = page.total_slides;
        for (const slide of page.items) {
          if (
            seenSlides.has(slide.slide_id) ||
            slide.slide_number !== all.length + 1 ||
            !Array.isArray(slide.batches)
          )
            throw new Error(
              "The deck scan inventory is incomplete or duplicated.",
            );
          all.push(slide);
          seenSlides.add(slide.slide_id);
        }
        offset += page.items.length;
        setMessage(`Prepared ${offset} of ${total} slides; no provider calls.`);
        if (!page.has_more) break;
      } while (offset <= 5000);
      if (all.length !== total)
        throw new Error("The deck scan did not inventory every slide.");
      const reused: CompletedScanBatch[] = [];
      const nativeBySlide = new Map<string, NativeScanText>();
      for (const entry of reusableScanBatches(
        all,
        previous,
        scope.document_id,
      )) {
        if (!active()) return;
        let native = nativeBySlide.get(entry.slide.slide_id);
        if (!native) {
          native = unwrapInvokeResult<NativeScanText>(
            await window.presenterCopilot.core.request(
              "presentation.workspace.list_text_targets",
              { ...scope, slide_number: entry.slide.slide_number },
            ),
          );
          if (!active()) return;
          nativeBySlide.set(entry.slide.slide_id, native);
        }
        const currentBatch = entry.slide.batches[entry.batch];
        if (
          currentBatch &&
          validScanResult(
            currentBatch,
            entry.slide.slide_id,
            scope.document_id,
            entry.result,
            entry.result.revision_id,
            native,
            scope.revision_id,
          )
        )
          reused.push({ ...entry, verified_revision_id: scope.revision_id });
      }
      setCompleted(reused);
      if (incremental) retainScanCache(cache, cacheKey, reused);
      setSlides(all);
      setSelected(all.filter((s) => s.batches.length).map((s) => s.slide_id));
      setMessage(
        incremental
          ? `Refreshed native text. ${reused.length} unchanged text windows reused without provider calls. Review changed text before starting.`
          : "Review the slides and request count before starting.",
      );
    } catch (caught) {
      if (active())
        setError(
          isCoreError(caught) || caught instanceof Error
            ? caught.message
            : String(caught),
        );
    } finally {
      if (owner.current.live && current.current === requested) {
        if (owner.current.generation !== generation)
          setMessage(
            "Scan stopped. Completed candidates remain unsaved. Review before resuming.",
          );
        setPhase("ready");
      }
    }
  }
  async function scan() {
    const generation = ++owner.current.generation,
      requested = key;
    const active = () =>
      owner.current.live &&
      owner.current.generation === generation &&
      current.current === requested;
    setPhase("running");
    setError("");
    const done = [...completed];
    const doneKeys = new Set(
      done.map((entry) => `${entry.slide.slide_id}:${entry.batch}`),
    );
    const visibleDone = () =>
      done.filter((entry) => selectedIds.has(entry.slide.slide_id)).length;
    try {
      for (const task of tasks) {
        if (!active()) return;
        if (doneKeys.has(`${task.slide.slide_id}:${task.index}`)) continue;
        setMessage(
          `Inspecting slide ${task.slide.slide_number}, text window ${task.index + 1}. ${visibleDone()} of ${tasks.length} text windows completed.`,
        );
        const result = unwrapInvokeResult<ClaimExtractionResult>(
          await window.presenterCopilot.core.request(
            "presentation.workspace.extract_claims",
            {
              ...scope,
              slide_id: task.slide.slide_id,
              slide_number: task.slide.slide_number,
              object_ids: task.batch.object_ids,
              spans: task.batch.spans,
            },
          ),
        );
        if (!active()) return;
        const native = unwrapInvokeResult<NativeScanText>(
          await window.presenterCopilot.core.request(
            "presentation.workspace.list_text_targets",
            {
              ...scope,
              slide_number: task.slide.slide_number,
            },
          ),
        );
        if (!active()) return;
        if (
          !validScanResult(
            task.batch,
            task.slide.slide_id,
            scope.document_id,
            result,
            scope.revision_id,
            native,
            scope.revision_id,
          )
        )
          throw new Error(
            "The claim result does not match the prepared slide/text window.",
          );
        done.push({
          slide: task.slide,
          batch: task.index,
          result,
          verified_revision_id: scope.revision_id,
          carried: false,
        });
        doneKeys.add(`${task.slide.slide_id}:${task.index}`);
        retainScanCache(cache, cacheKey, done);
        setCompleted([...done]);
      }
      if (active())
        setMessage(
          reusedCount
            ? `Finished ${visibleDone()} text windows (${reusedCount} reused). Review each candidate for this revision; nothing was saved.`
            : `Finished ${visibleDone()} requests. Review each candidate individually; nothing was saved.`,
        );
    } catch (caught) {
      if (active()) {
        setError(
          isCoreError(caught) || caught instanceof Error
            ? caught.message
            : String(caught),
        );
        setConfirmed(false);
        setMessage(
          `Stopped after ${visibleDone()} completed text windows. Review the error before resuming.`,
        );
        if (
          isCoreError(caught) &&
          (caught.code === "PRESENTATION_REVISION_CONFLICT" ||
            caught.code === "PRIVACY_POLICY_CHANGED")
        ) {
          setSlides(null);
          setCompleted([]);
          setSelected([]);
        }
      }
    } finally {
      if (owner.current.live && current.current === requested) {
        if (owner.current.generation !== generation)
          setMessage(
            "Scan stopped. Completed candidates remain unsaved. Review before resuming.",
          );
        setPhase("ready");
      }
    }
  }
  return (
    <section className="pw-purpose-panel" aria-label="Deck claim discovery">
      <h4>Find claims across the deck</h4>
      <p>
        Prepare a local inventory of every slide, then choose which native
        representations to send to your configured reasoning provider. Notes,
        images and chart visuals are excluded. Candidates remain unsaved and
        require individual quote/evidence review.
      </p>
      <p className="muted">{NATIVE_CLAIM_DISCLOSURE}</p>
      <p>A stopped request may finish and be repeated when you resume.</p>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled || working}
        onClick={() => void prepare()}
      >
        Prepare deck claim scan
      </button>
      {cache.get(cacheKey)?.length ? (
        <button
          type="button"
          className="secondary-button"
          disabled={disabled || working}
          onClick={() => void prepare(true)}
        >
          Refresh changed text
        </button>
      ) : null}
      <p>
        Refresh reuses recent unsaved suggestions only when their input text is
        unchanged and verified again. Reused candidates require review for this
        revision. Reuse is limited to this app session; uncached text may need
        another request. Prepare deck claim scan starts fresh.
      </p>
      {working && phase !== "stopping" ? (
        <button type="button" className="secondary-button" onClick={stop}>
          Stop claim scan
        </button>
      ) : null}
      {message ? <p role="status">{message}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {slides ? (
        <fieldset disabled={disabled || working}>
          <legend>Slides to inspect</legend>
          <p>
            {slides.length} slides inventoried · {chosen.length} selected ·{" "}
            {remainingCount} provider requests needed ·{" "}
            {selectedCompleted.length} completed text windows ({reusedCount}{" "}
            reused). Dense objects use overlapping text windows; duplicate
            quotes are shown once.
          </p>
          <div className="pw-deck-review-pages">
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setSelected(
                  slides
                    .filter((slide) => slide.batches.length)
                    .map((slide) => slide.slide_id),
                );
                setConfirmed(false);
                setCandidatePage(0);
              }}
            >
              Select all available slides
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setSelected([]);
                setConfirmed(false);
                setCandidatePage(0);
              }}
            >
              Clear selected slides
            </button>
          </div>
          <p>
            Slide selection page {slidePage + 1} of{" "}
            {Math.max(1, Math.ceil(slides.length / 20))}.
          </p>
          {slides.slice(slidePage * 20, (slidePage + 1) * 20).map((slide) => (
            <div key={slide.slide_id}>
              <label className="pw-deck-review-filter">
                <input
                  type="checkbox"
                  aria-label={`Inspect slide ${slide.slide_number}`}
                  disabled={!slide.batches.length}
                  checked={selected.includes(slide.slide_id)}
                  onChange={(event) => {
                    setSelected(
                      event.target.checked
                        ? [...selected, slide.slide_id]
                        : selected.filter((id) => id !== slide.slide_id),
                    );
                    setConfirmed(false);
                    setCandidatePage(0);
                  }}
                />
                {slide.slide_number}. {slide.title}
              </label>
              <p>
                {slide.eligible_objects} available native representations ·{" "}
                {slide.batches.length} requests · {slide.excluded_objects} empty
                or unavailable objects.
                {slide.inventory_truncated
                  ? " Native text inventory is truncated; this slide has incomplete coverage."
                  : ""}
              </p>
            </div>
          ))}
          <div className="pw-deck-review-pages">
            <button
              type="button"
              className="secondary-button"
              disabled={slidePage === 0}
              onClick={() => setSlidePage(slidePage - 1)}
            >
              Previous scan slides
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={(slidePage + 1) * 20 >= slides.length}
              onClick={() => setSlidePage(slidePage + 1)}
            >
              Next scan slides
            </button>
          </div>
          <label className="pw-deck-review-filter">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            Send native text, table cells and raw chart cache data from these
            slides to my configured reasoning provider.
          </label>
          <button
            type="button"
            className="secondary-button"
            disabled={!confirmed || !tasks.length || remainingCount === 0}
            onClick={() => void scan()}
          >
            {selectedCompleted.length
              ? "Resume deck claim scan"
              : "Start deck claim scan"}
          </button>
        </fieldset>
      ) : null}
      {selectedCompleted.length ? (
        <div>
          <p>
            {unique.length} unsaved candidates in {selectedCompleted.length}{" "}
            completed text windows. Empty results mean no candidates returned,
            not that a slide has no claims. Provider confidence is uncalibrated.
          </p>
          <p>
            Candidate page {currentCandidatePage + 1} of{" "}
            {Math.max(1, Math.ceil(unique.length / 20))}.
          </p>
          {unique
            .slice(currentCandidatePage * 20, (currentCandidatePage + 1) * 20)
            .map(
              ({ slide, candidate, carried, original_revision_id }, index) => (
                <article
                  key={`${slide.slide_id}:${candidate.object_id}:${index}`}
                  data-original-revision={original_revision_id}
                >
                  <h5>Slide {slide.slide_number}</h5>
                  <blockquote>{candidate.quote}</blockquote>
                  {carried ? (
                    <p>
                      Reused from an earlier scan. Current native text matches;
                      review for this revision.
                    </p>
                  ) : null}
                  <p>
                    {claimSourceLabel(candidate.source_kind)} · {candidate.kind}{" "}
                    · {candidate.reason}
                  </p>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={disabled || working}
                    onClick={() => onReview(slide, candidate)}
                  >
                    Review quote on slide {slide.slide_number}
                  </button>
                </article>
              ),
            )}
          <div className="pw-deck-review-pages">
            <button
              type="button"
              className="secondary-button"
              disabled={disabled || working || currentCandidatePage === 0}
              onClick={() => setCandidatePage(currentCandidatePage - 1)}
            >
              Previous claim candidates
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={
                disabled ||
                working ||
                (currentCandidatePage + 1) * 20 >= unique.length
              }
              onClick={() => setCandidatePage(currentCandidatePage + 1)}
            >
              Next claim candidates
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
