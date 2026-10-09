import { useEffect, useState } from "react";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { DeckClaimScan } from "./DeckClaimScan";
import type { ClaimReviewSelection } from "./claim-review-selection";
import { OutlineEvidenceReview } from "./OutlineEvidenceReview";
import type { ClaimScanCache } from "./claim-scan-state";

type Counts = Record<
  "supported" | "conflicting" | "needs_review" | "unlinked",
  number
>;
type Slide = {
  slide_id: string;
  slide_number: number;
  title: string;
  purpose: string | null;
  purpose_status: "missing" | "reviewed" | "needs_review";
  takeaway: string;
  takeaway_status: "missing" | "reviewed" | "needs_review";
  claim_count: number;
  claim_counts: Counts;
  attention_reasons: string[];
  incomplete: boolean;
};
type Review = {
  revision_id: string;
  total_slides: number;
  offset: number;
  limit: number;
  has_more: boolean;
  items: Slide[];
  page_claim_counts: Counts;
  page_slides_needing_attention: number;
  incomplete: boolean;
};
const REASONS: Record<string, string> = {
  takeaway_inherited: "Inherited takeaway needs review",
  purpose_missing: "Purpose not reviewed",
  purpose_inherited: "Inherited purpose needs review",
  purpose_unclear: "Purpose is unclear",
  claim_needs_review: "Claim or source needs review",
  conflicting_evidence: "Reviewed evidence conflicts",
  claim_unlinked: "Claim has no supporting link",
  incomplete_coverage: "Coverage is incomplete",
};

export function DeckSemanticReview({
  projectId,
  documentId,
  revisionId,
  visible,
  disabled,
  onOpenSlide,
  onReviewCandidate,
  claimScanCache,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  visible: boolean;
  disabled: boolean;
  claimScanCache: ClaimScanCache;
  onOpenSlide: (ordinal: number) => void;
  onReviewCandidate: (
    slide: { slide_id: string; slide_number: number },
    candidate: ClaimReviewSelection,
  ) => void;
}) {
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<Review | null>(null);
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!visible) return;
    let active = true;
    setBusy(true);
    setError("");
    void window.presenterCopilot.core
      .request<Review>("presentation.workspace.review_deck_semantics", {
        project_id: projectId,
        document_id: documentId,
        revision_id: revisionId,
        offset,
        limit: 20,
      })
      .then((response) => {
        const result = unwrapInvokeResult<Review>(response);
        if (
          result.revision_id !== revisionId ||
          result.offset !== offset ||
          !Array.isArray(result.items)
        )
          throw new Error(
            "Deck review does not match the current revision/page.",
          );
        if (active) setData(result);
      })
      .catch((caught) => {
        if (active)
          setError(isCoreError(caught) ? caught.message : String(caught));
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [visible, projectId, documentId, revisionId, offset, refresh]);
  const items =
    data?.items.filter(
      (slide) => !attentionOnly || slide.attention_reasons.length,
    ) ?? [];
  return (
    <section
      className="pw-deck-review"
      aria-label="Deck semantic review"
      aria-busy={busy}
    >
      <h3>Deck review</h3>
      <OutlineEvidenceReview
        projectId={projectId}
        documentId={documentId}
        revisionId={revisionId}
        visible={visible}
        disabled={disabled}
        onReview={onReviewCandidate}
      />
      <DeckClaimScan
        cache={claimScanCache}
        scope={{
          project_id: projectId,
          document_id: documentId,
          revision_id: revisionId,
        }}
        visible={visible}
        disabled={disabled}
        onReview={onReviewCandidate}
      />
      <p>
        Review purposes and the claims you have recorded across this deck. Open
        a slide to review its purpose, exact quotes and linked evidence.
      </p>
      <p>
        Counts describe the displayed page and user-reviewed claims. No recorded
        claims does not mean a slide is unsupported or that all its claims were
        found.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {busy ? <p role="status">Loading deck review…</p> : null}
      <fieldset disabled={disabled || busy}>
        <label className="pw-deck-review-filter">
          <input
            type="checkbox"
            checked={attentionOnly}
            onChange={(event) => setAttentionOnly(event.target.checked)}
          />
          Show attention items on this page
        </label>
        <button
          type="button"
          className="secondary-button"
          onClick={() => setRefresh((value) => value + 1)}
        >
          Refresh deck review
        </button>
        {data && !busy ? (
          <>
            <p role="status">
              Slides {data.items.length ? data.offset + 1 : 0}–
              {data.offset + data.items.length} of {data.total_slides}.{" "}
              {data.page_slides_needing_attention} slides need attention on this
              page.
            </p>
            <p>
              Recorded claim counts on this page:{" "}
              {data.page_claim_counts.supported} supported ·{" "}
              {data.page_claim_counts.conflicting} conflicting ·{" "}
              {data.page_claim_counts.needs_review} need review ·{" "}
              {data.page_claim_counts.unlinked} without a supporting link.
            </p>
            {data.incomplete ? (
              <p>
                Some text inventory or revision history is incomplete. Review
                those slides directly.
              </p>
            ) : null}
            {items.length === 0 ? (
              <p>No matching slides on this page.</p>
            ) : null}
            {items.map((slide) => (
              <article
                key={slide.slide_id}
                aria-label={`Slide ${slide.slide_number} semantics`}
              >
                <h4>
                  {slide.slide_number}. {slide.title}
                </h4>
                <p>
                  Purpose: {slide.purpose ?? "not reviewed"} ·{" "}
                  {slide.purpose_status === "reviewed"
                    ? "reviewed for this revision"
                    : slide.purpose_status === "needs_review"
                      ? "inherited; needs review"
                      : "missing"}
                </p>
                {slide.takeaway ? (
                  <p>
                    Takeaway: {slide.takeaway} ·{" "}
                    {slide.takeaway_status === "reviewed"
                      ? "reviewed for this revision"
                      : "inherited; needs review"}
                  </p>
                ) : (
                  <p>No recorded takeaway.</p>
                )}
                {slide.claim_count ? (
                  <p>
                    {slide.claim_count} recorded claims:{" "}
                    {slide.claim_counts.supported} supported,{" "}
                    {slide.claim_counts.conflicting} conflicting,{" "}
                    {slide.claim_counts.needs_review} need review,{" "}
                    {slide.claim_counts.unlinked} without a supporting link.
                  </p>
                ) : (
                  <p>No recorded claims.</p>
                )}
                {slide.attention_reasons.length ? (
                  <ul>
                    {slide.attention_reasons.map((reason) => (
                      <li key={reason}>{REASONS[reason] ?? reason}</li>
                    ))}
                  </ul>
                ) : null}
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onOpenSlide(slide.slide_number)}
                >
                  Review slide {slide.slide_number}
                </button>
              </article>
            ))}
            <div className="pw-deck-review-pages">
              <button
                type="button"
                className="secondary-button"
                disabled={data.offset === 0}
                onClick={() => setOffset(Math.max(0, data.offset - data.limit))}
              >
                Previous review page
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={!data.has_more}
                onClick={() => setOffset(data.offset + data.limit)}
              >
                Next review page
              </button>
            </div>
          </>
        ) : null}
      </fieldset>
    </section>
  );
}
