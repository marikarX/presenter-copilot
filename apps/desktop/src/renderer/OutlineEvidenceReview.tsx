import { useEffect, useRef, useState } from "react";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import type {
  ClaimReviewEvidence,
  ClaimReviewSelection,
} from "./claim-review-selection";

type Reference = {
  evidence_id: string;
  original_excerpt: string;
  original_excerpt_truncated: boolean;
  original_source_type: string | null;
  excerpt_comparison: string;
  source_status: string;
  can_link: boolean;
  current_evidence: ClaimReviewEvidence | null;
};
type Point = {
  original_slide_number: number;
  point_number: number;
  slide_id: string | null;
  slide_number: number | null;
  object_id: string | null;
  quote: string;
  source_kind: "native_text";
  span_status: string;
  reviewable: boolean;
  references: Reference[];
};
type Page = {
  document_id: string;
  revision_id: string;
  offset: number;
  limit: number;
  has_receipt: boolean;
  has_more: boolean;
  total_points: number;
  requires_user_review: boolean;
  planning_record_available?: boolean;
  items: Point[];
  citation_only_slides: Array<{
    original_slide_number: number;
    reason: string;
  }>;
};
const SHA = /^[0-9a-f]{64}$/;
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const STATUSES = [
  "unchanged",
  "changed",
  "missing",
  "missing_original",
  "ambiguous_original",
];

export function validOutlineEvidencePage(page: Page): boolean {
  return (
    typeof page.has_receipt === "boolean" &&
    typeof page.has_more === "boolean" &&
    page.requires_user_review === true &&
    Number.isInteger(page.total_points) &&
    page.total_points >= 0 &&
    page.total_points <= 320 &&
    Array.isArray(page.items) &&
    page.items.length <= 20 &&
    Array.isArray(page.citation_only_slides) &&
    page.citation_only_slides.length <= 40 &&
    page.citation_only_slides.every(
      (slide) =>
        slide &&
        Number.isInteger(slide.original_slide_number) &&
        slide.original_slide_number >= 1 &&
        slide.original_slide_number <= 40 &&
        slide.reason === "no_native_points",
    ) &&
    page.items.every(
      (point) =>
        point &&
        typeof point.quote === "string" &&
        point.quote.trim().length > 0 &&
        point.quote.length <= 200 &&
        point.source_kind === "native_text" &&
        Number.isInteger(point.original_slide_number) &&
        point.original_slide_number >= 1 &&
        point.original_slide_number <= 40 &&
        Number.isInteger(point.point_number) &&
        point.point_number >= 1 &&
        point.point_number <= 8 &&
        STATUSES.includes(point.span_status) &&
        typeof point.reviewable === "boolean" &&
        point.reviewable === (point.span_status === "unchanged") &&
        (!point.reviewable ||
          (typeof point.object_id === "string" &&
            ID.test(point.object_id) &&
            typeof point.slide_id === "string" &&
            ID.test(point.slide_id) &&
            Number.isInteger(point.slide_number) &&
            (point.slide_number ?? 0) > 0)) &&
        Array.isArray(point.references) &&
        point.references.length <= 8 &&
        new Set(point.references.map((reference) => reference?.evidence_id))
          .size === point.references.length &&
        point.references.every(
          (reference) =>
            reference &&
            typeof reference.evidence_id === "string" &&
            reference.evidence_id.length <= 120 &&
            typeof reference.original_excerpt === "string" &&
            reference.original_excerpt.length <= 800 &&
            typeof reference.original_excerpt_truncated === "boolean" &&
            (reference.original_source_type === null ||
              typeof reference.original_source_type === "string") &&
            ["not_comparable", "excerpt_matches", "excerpt_changed"].includes(
              reference.excerpt_comparison,
            ) &&
            [
              "available",
              "missing",
              "not_linkable",
              "too_long",
              "planning_record_missing",
            ].includes(reference.source_status) &&
            typeof reference.can_link === "boolean" &&
            (reference.can_link
              ? reference.source_status === "available" &&
                !!reference.current_evidence &&
                typeof reference.current_evidence.chunk_id === "string" &&
                ID.test(reference.current_evidence.chunk_id) &&
                typeof reference.current_evidence.text === "string" &&
                reference.current_evidence.text.length > 0 &&
                reference.current_evidence.text.length <= 8000 &&
                typeof reference.current_evidence.name === "string" &&
                typeof reference.current_evidence.sha256 === "string" &&
                SHA.test(reference.current_evidence.sha256) &&
                reference.current_evidence.relation === "context"
              : reference.current_evidence === null),
        ),
    )
  );
}

export function OutlineEvidenceReview({
  projectId,
  documentId,
  revisionId,
  visible,
  disabled,
  onReview,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  visible: boolean;
  disabled: boolean;
  onReview: (
    slide: { slide_id: string; slide_number: number },
    candidate: ClaimReviewSelection,
  ) => void;
}) {
  const [page, setPage] = useState<Page | null>(null);
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const context = `${projectId}:${documentId}:${revisionId}:${visible}:${disabled}`;
  const currentContext = useRef(context);
  currentContext.current = context;
  const sequence = useRef(0);
  useEffect(() => {
    sequence.current++;
    setPage(null);
    setSelected({});
    setError("");
    setBusy(false);
    return () => {
      sequence.current++;
    };
  }, [projectId, documentId, revisionId, visible, disabled]);
  async function load(offset: number) {
    if (busy || disabled || !visible) return;
    const token = ++sequence.current;
    const isCurrent = () =>
      token === sequence.current && context === currentContext.current;
    setBusy(true);
    setError("");
    setPage(null);
    setSelected({});
    try {
      const result = unwrapInvokeResult<Page>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_outline_evidence_candidates",
          {
            project_id: projectId,
            document_id: documentId,
            revision_id: revisionId,
            offset,
            limit: 20,
          },
        ),
      );
      if (
        result.document_id !== documentId ||
        result.revision_id !== revisionId ||
        result.offset !== offset ||
        result.limit !== 20 ||
        !validOutlineEvidencePage(result)
      )
        throw new Error(
          "Outline evidence does not match this native revision or page.",
        );
      if (isCurrent()) setPage(result);
    } catch (caught) {
      if (isCurrent())
        setError(isCoreError(caught) ? caught.message : String(caught));
    } finally {
      if (isCurrent()) setBusy(false);
    }
  }
  if (!visible) return null;
  return (
    <section className="pw-card" aria-label="Outline evidence review">
      <h3>Outline evidence review</h3>
      <p className="muted">
        Review retained planning references against the points you created.
        Planning citations do not approve claims. Reads and navigation do not
        call a provider or Save.
      </p>
      <button
        type="button"
        disabled={busy || disabled}
        onClick={() => void load(0)}
      >
        {busy ? "Loading outline evidence…" : "Load outline evidence"}
      </button>
      {error ? <p role="alert">{error}</p> : null}
      {page && !page.has_receipt ? (
        <p>This presentation has no retained outline evidence receipt.</p>
      ) : null}
      {page?.has_receipt ? (
        <>
          <p>
            {page.total_points} cited native point(s). Compare supplied excerpts
            with current sources; excerpt matching does not prove the entire
            source stayed unchanged.
          </p>
          {page.planning_record_available === false ? (
            <p>
              Original planning record unavailable. References cannot be linked.
            </p>
          ) : null}
          {page.citation_only_slides.map((slide) => (
            <p key={slide.original_slide_number}>
              Created slide {slide.original_slide_number} retained citations but
              has no native points to review.
            </p>
          ))}
          {page.items.map((point) => {
            const key = `${point.original_slide_number}:${point.point_number}`;
            const chosen = selected[key] ?? [];
            return (
              <article key={key} className="pw-card">
                <h4>
                  Created slide {point.original_slide_number}, point{" "}
                  {point.point_number}
                  {point.slide_number
                    ? ` · current slide ${point.slide_number}`
                    : ""}
                </h4>
                <blockquote>{point.quote}</blockquote>
                <p>Native point: {point.span_status.replaceAll("_", " ")}.</p>
                {point.references.map((reference) => (
                  <details key={reference.evidence_id}>
                    <summary>
                      {reference.current_evidence?.name ??
                        reference.original_source_type ??
                        "Planning reference"}
                      {` · ${reference.source_status.replaceAll("_", " ")}`}
                    </summary>
                    <p>
                      Originally supplied excerpt
                      {reference.original_excerpt_truncated
                        ? " (preview truncated)"
                        : ""}
                      :
                    </p>
                    <blockquote>
                      {reference.original_excerpt || "Unavailable"}
                    </blockquote>
                    <p>
                      Excerpt comparison:{" "}
                      {reference.excerpt_comparison.replaceAll("_", " ")}.
                    </p>
                    {reference.current_evidence ? (
                      <>
                        <p>
                          Current source excerpt (SHA{" "}
                          {reference.current_evidence.sha256.slice(0, 12)}):
                        </p>
                        <blockquote>
                          {reference.current_evidence.text}
                        </blockquote>
                      </>
                    ) : null}
                    <label>
                      <input
                        type="checkbox"
                        aria-label={`Select reference ${reference.evidence_id} for point ${key}`}
                        checked={chosen.includes(reference.evidence_id)}
                        disabled={
                          busy ||
                          disabled ||
                          !point.reviewable ||
                          !reference.can_link ||
                          (!chosen.includes(reference.evidence_id) &&
                            chosen.length >= 4)
                        }
                        onChange={(event) =>
                          setSelected({
                            ...selected,
                            [key]: event.target.checked
                              ? [...chosen, reference.evidence_id]
                              : chosen.filter(
                                  (id) => id !== reference.evidence_id,
                                ),
                          })
                        }
                      />
                      Use this current excerpt in claim review
                    </label>
                  </details>
                ))}
                <p>
                  Select up to four excerpts. New links start as context; choose
                  relations and confirm separately.
                </p>
                <button
                  type="button"
                  disabled={
                    busy || disabled || !point.reviewable || chosen.length === 0
                  }
                  onClick={() => {
                    if (
                      page.document_id !== documentId ||
                      page.revision_id !== revisionId ||
                      !point.slide_id ||
                      !point.slide_number ||
                      !point.object_id
                    )
                      return;
                    const evidence = point.references
                      .filter((reference) =>
                        chosen.includes(reference.evidence_id),
                      )
                      .flatMap((reference) =>
                        reference.current_evidence
                          ? [reference.current_evidence]
                          : [],
                      );
                    onReview(
                      {
                        slide_id: point.slide_id,
                        slide_number: point.slide_number,
                      },
                      {
                        object_id: point.object_id,
                        quote: point.quote,
                        source_kind: "native_text",
                        initial_evidence: evidence,
                      },
                    );
                  }}
                >
                  Review point {key} on current slide
                </button>
              </article>
            );
          })}
          <button
            type="button"
            disabled={busy || disabled || page.offset === 0}
            onClick={() => void load(Math.max(0, page.offset - 20))}
          >
            Previous outline points
          </button>
          <button
            type="button"
            disabled={busy || disabled || !page.has_more}
            onClick={() => void load(page.offset + 20)}
          >
            Next outline points
          </button>
        </>
      ) : null}
    </section>
  );
}
