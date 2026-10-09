import { useEffect, useRef, useState } from "react";
import { ClaimDiscovery } from "./ClaimDiscovery";
import { EvidenceFootnote } from "./EvidenceFootnote";
import type {
  ClaimReviewEvidence,
  ClaimReviewSelection,
} from "./claim-review-selection";
import {
  claimSourceLabel,
  NATIVE_CLAIM_DISCLOSURE,
  type NativeClaimSourceKind,
  type NativeClaimTarget,
} from "./claim-source";
import {
  unwrapInvokeResult,
  isCoreError,
  type RendererCoreMethod,
} from "../shared/protocol";

type Evidence = ClaimReviewEvidence;
type Claim = {
  claim_id: string;
  object_id: string;
  quote: string;
  coverage: string;
  span_status: string;
  source_revision_id: string;
  evidence: Evidence[];
  source_kind?: NativeClaimSourceKind;
};
type Triage = {
  suggestion: string;
  abstained: boolean;
  reason: string;
  confidence: number | null;
  provider_id: string;
  model_id: string;
  latency_ms: number;
  revision_id: string;
  object_id: string;
  chunk_id: string;
  excerpt_sha256: string;
  quote: string;
};
type Target = NativeClaimTarget;
export function ClaimEvidenceReview({
  projectId,
  documentId,
  revisionId,
  slideId,
  slideNumber,
  targets,
  disabled,
  slideSize,
  onFootnoteRestore,
  candidateToReview,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  slideId: string;
  slideNumber: number;
  targets: Target[];
  disabled: boolean;
  slideSize: { width: number; height: number } | null;
  onFootnoteRestore: (applied: boolean) => Promise<void>;
  candidateToReview?: ClaimReviewSelection;
}) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [incomplete, setIncomplete] = useState(false);
  const [objectId, setObjectId] = useState(targets[0]?.object_id ?? "");
  const [quote, setQuote] = useState(
    (targets[0]?.text.length ?? 0) <= 2000 ? (targets[0]?.text ?? "") : "",
  );
  const [claimId, setClaimId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Evidence[]>([]);
  const [searched, setSearched] = useState(false);
  const [links, setLinks] = useState<Evidence[]>([]);
  const [triage, setTriage] = useState<Record<string, Triage>>({});
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [claimsLoaded, setClaimsLoaded] = useState(false);
  const consumedCandidate = useRef("");
  const scope = {
    project_id: projectId,
    document_id: documentId,
    revision_id: revisionId,
    slide_id: slideId,
    slide_number: slideNumber,
  };
  async function request<T>(
    method: RendererCoreMethod,
    params: Record<string, unknown>,
  ) {
    return unwrapInvokeResult<T>(
      await window.presenterCopilot.core.request(method, params),
    );
  }
  async function load() {
    const result = await request<{
      items: Claim[];
      lineage_truncated: boolean;
      inventory_truncated: boolean;
    }>("presentation.workspace.list_claims", scope);
    setClaims(result.items);
    setIncomplete(result.lineage_truncated || result.inventory_truncated);
  }
  useEffect(() => {
    let alive = true;
    void request<{
      items: Claim[];
      lineage_truncated: boolean;
      inventory_truncated: boolean;
    }>("presentation.workspace.list_claims", scope)
      .then((result) => {
        if (alive) {
          setClaims(result.items);
          setIncomplete(result.lineage_truncated || result.inventory_truncated);
          setClaimsLoaded(true);
        }
      })
      .catch((caught) => {
        if (alive) setError(String(caught));
      });
    return () => {
      alive = false;
    };
    // The parent remounts this revision/slide-scoped review component.
  }, []);
  function chooseCandidate(candidate: ClaimReviewSelection) {
    const target = targets.find(
      (target) => target.object_id === candidate.object_id,
    );
    const text = target?.text;
    if (
      (candidate.source_kind ?? "native_text") !==
        (target?.source_kind ?? "native_text") ||
      !text ||
      !candidate.quote.trim() ||
      text.indexOf(candidate.quote) < 0 ||
      text.indexOf(candidate.quote, text.indexOf(candidate.quote) + 1) >= 0
    ) {
      setError(
        "The candidate quote no longer matches this current native text object.",
      );
      return;
    }
    const existing = claims.find(
      (claim) =>
        claim.object_id === candidate.object_id &&
        claim.quote === candidate.quote,
    );
    setClaimId(existing?.claim_id ?? null);
    setObjectId(candidate.object_id);
    setQuote(candidate.quote);
    setLinks(
      existing?.evidence ??
        (candidate.initial_evidence ?? []).slice(0, 4).map((evidence) => ({
          ...evidence,
          relation: "context",
        })),
    );
    setTriage({});
    setResults([]);
    setSearched(false);
    setReviewed(false);
    setQuery("");
    setError("");
  }
  useEffect(() => {
    if (!claimsLoaded || !candidateToReview) return;
    const candidateKey = JSON.stringify(candidateToReview);
    if (consumedCandidate.current === candidateKey) return;
    consumedCandidate.current = candidateKey;
    chooseCandidate(candidateToReview);
  }, [claimsLoaded, candidateToReview]);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (caught) {
      setError(
        caught instanceof Error || isCoreError(caught)
          ? caught.message
          : String(caught),
      );
    } finally {
      setBusy(false);
    }
  }
  function reset() {
    setClaimId(null);
    setLinks([]);
    setReviewed(false);
  }
  return (
    <section
      className="pw-purpose-panel pw-claim-review"
      aria-label="Claim and evidence review"
    >
      <h4>Claims and evidence</h4>
      <p className="muted">
        Bind an exact quote to a slide text object, then review source excerpts.
        Coverage records your judgment; it does not verify that a claim is true.
        Deck edits require fresh review.
      </p>
      <p role="status">
        {claims.length} {claims.length === 1 ? "claim" : "claims"} ·{" "}
        {claims.filter((c) => c.coverage === "supported").length} supported ·{" "}
        {claims.filter((c) => c.coverage === "needs_review").length} need review
      </p>
      {incomplete ? (
        <p role="alert">
          This view is incomplete: text inventory or revision history reached
          its limit. Older or unlisted claims may require review.
        </p>
      ) : null}
      <ClaimDiscovery
        scope={scope}
        targets={targets}
        disabled={disabled || busy}
        onChoose={chooseCandidate}
      />
      {claims.map((claim) => (
        <article key={claim.claim_id}>
          <blockquote>{claim.quote}</blockquote>
          <p>{claimSourceLabel(claim.source_kind)}</p>
          <p>
            {claim.coverage.replaceAll("_", " ")} · object {claim.span_status}
          </p>
          {claim.evidence.map((e) => (
            <details key={e.chunk_id}>
              <summary>
                {e.name} · {e.relation} · {e.status}
              </summary>
              <p>{e.text}</p>
            </details>
          ))}
          <EvidenceFootnote
            scope={scope}
            claim={{
              ...claim,
              evidence: claim.evidence.map((e) => ({
                ...e,
                ordinal: e.ordinal ?? null,
                relation: e.relation ?? "",
                status: e.status ?? "missing",
              })),
            }}
            size={slideSize}
            disabled={disabled || busy}
            onRestore={onFootnoteRestore}
          />
          <button
            type="button"
            className="secondary-button"
            disabled={disabled || busy}
            onClick={() => {
              setClaimId(claim.claim_id);
              setObjectId(claim.object_id);
              setQuote(claim.quote);
              setLinks(claim.evidence);
              setReviewed(false);
            }}
          >
            Review claim
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={disabled || busy}
            onClick={() =>
              void run(async () => {
                await request("presentation.workspace.remove_claim", {
                  ...scope,
                  claim_id: claim.claim_id,
                  confirm: true,
                });
                await load();
                reset();
              })
            }
          >
            Remove claim
          </button>
        </article>
      ))}
      <fieldset disabled={disabled || busy}>
        <legend>{claimId ? "Review existing claim" : "New claim"}</legend>
        <p className="muted">{NATIVE_CLAIM_DISCLOSURE}</p>
        <label>
          Claim text object
          <select
            aria-label="Claim text object"
            value={objectId}
            onChange={(event) => {
              setObjectId(event.target.value);
              setQuote(
                (targets.find((t) => t.object_id === event.target.value)?.text
                  .length ?? 0) <= 2000
                  ? (targets.find((t) => t.object_id === event.target.value)
                      ?.text ?? "")
                  : "",
              );
              setReviewed(false);
            }}
          >
            <option value="">Choose text</option>
            {targets.map((target) => (
              <option key={target.object_id} value={target.object_id}>
                {target.label} · {claimSourceLabel(target.source_kind)}
              </option>
            ))}
          </select>
        </label>
        <details>
          <summary>Selected native representation</summary>
          <p>
            {claimSourceLabel(
              targets.find((t) => t.object_id === objectId)?.source_kind,
            )}
          </p>
          <p style={{ whiteSpace: "pre-wrap" }}>
            {targets.find((t) => t.object_id === objectId)?.text ??
              "Choose an available text object."}
          </p>
        </details>
        <label>
          Exact claim quote
          <textarea
            aria-label="Exact claim quote"
            maxLength={2000}
            rows={3}
            value={quote}
            onChange={(event) => {
              setQuote(event.target.value);
              setReviewed(false);
            }}
          />
        </label>
        <label>
          Find project evidence
          <input
            aria-label="Find project evidence"
            value={query}
            maxLength={120}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="secondary-button"
          disabled={query.trim().length < 2}
          onClick={() =>
            void run(async () => {
              const result = await request<{
                items: Evidence[];
                has_more: boolean;
              }>("presentation.workspace.search_claim_evidence", {
                project_id: projectId,
                query,
              });
              setResults(result.items);
              setSearched(true);
              if (result.has_more)
                setError(
                  "Showing 20 excerpts. Refine the search for other results.",
                );
            })
          }
        >
          Search evidence
        </button>
        {searched && !results.length ? (
          <p>
            No matching supporting excerpts. Import a supporting source, or
            refine the search.
          </p>
        ) : null}
        {results.map((e) => (
          <article key={e.chunk_id}>
            <strong>{e.name}</strong>
            <p>{e.text}</p>
            <button
              type="button"
              className="secondary-button"
              disabled={
                links.length >= 4 ||
                links.some((link) => link.chunk_id === e.chunk_id)
              }
              onClick={() => {
                setLinks([...links, { ...e, relation: "context" }]);
                setReviewed(false);
              }}
            >
              Link excerpt from {e.name}
            </button>
          </article>
        ))}
        {links.map((e) => (
          <div key={e.chunk_id}>
            <strong>{e.name}</strong>
            <p>{e.text}</p>
            <p className="muted">
              On request, the selected decision provider receives this exact
              quote and excerpt when privacy permits. Suggestions require your
              review.
            </p>
            <button
              type="button"
              className="secondary-button"
              disabled={!objectId || !quote.trim()}
              onClick={() =>
                void run(async () => {
                  setReviewed(false);
                  const result = await request<Triage>(
                    "presentation.workspace.triage_claim_evidence",
                    {
                      ...scope,
                      object_id: objectId,
                      quote,
                      chunk_id: e.chunk_id,
                      expected_sha256: e.sha256,
                    },
                  );
                  if (
                    result.revision_id !== revisionId ||
                    result.object_id !== objectId ||
                    result.chunk_id !== e.chunk_id ||
                    result.excerpt_sha256 !== e.sha256 ||
                    !["supports", "contradicts", "context", "unclear"].includes(
                      result.suggestion,
                    )
                  )
                    throw new Error(
                      "The evidence suggestion could not be verified.",
                    );
                  setTriage((current) => ({
                    ...current,
                    [e.chunk_id]: { ...result, quote },
                  }));
                })
              }
            >
              Suggest relation for {e.name}
            </button>
            {triage[e.chunk_id]?.quote === quote &&
            triage[e.chunk_id]?.object_id === objectId &&
            triage[e.chunk_id]?.excerpt_sha256 === e.sha256 ? (
              <div role="status">
                <p>
                  {triage[e.chunk_id]!.abstained
                    ? `Abstained: ${triage[e.chunk_id]!.reason.replaceAll("_", " ")}`
                    : `Suggested relation: ${triage[e.chunk_id]!.suggestion}`}
                </p>
                <p>
                  {triage[e.chunk_id]!.provider_id} ·{" "}
                  {triage[e.chunk_id]!.model_id} ·{" "}
                  {triage[e.chunk_id]!.latency_ms} ms
                </p>
                <p className="muted">
                  {triage[e.chunk_id]!.confidence === null
                    ? "No confidence estimate."
                    : `Provider confidence: ${Math.round(triage[e.chunk_id]!.confidence! * 100)}%.`}{" "}
                  Confidence is uncalibrated; the thresholds are provisional.
                  Review the excerpt yourself.
                </p>
                {!triage[e.chunk_id]!.abstained ? (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => {
                      setLinks(
                        links.map((link) =>
                          link.chunk_id === e.chunk_id
                            ? {
                                ...link,
                                relation: triage[e.chunk_id]!.suggestion,
                              }
                            : link,
                        ),
                      );
                      setReviewed(false);
                    }}
                  >
                    Use suggested relation for {e.name}
                  </button>
                ) : null}
              </div>
            ) : null}
            <label>
              Evidence relation
              <select
                aria-label={`Evidence relation for ${e.name}`}
                value={e.relation}
                onChange={(event) => {
                  setLinks(
                    links.map((link) =>
                      link.chunk_id === e.chunk_id
                        ? { ...link, relation: event.target.value }
                        : link,
                    ),
                  );
                  setReviewed(false);
                }}
              >
                <option value="context">Context only</option>
                <option value="supports">Supports claim</option>
                <option value="contradicts">Contradicts claim</option>
              </select>
            </label>
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setLinks(links.filter((link) => link.chunk_id !== e.chunk_id));
                setReviewed(false);
              }}
            >
              Unlink {e.name}
            </button>
          </div>
        ))}
        <label>
          <input
            type="checkbox"
            checked={reviewed}
            onChange={(event) => setReviewed(event.target.checked)}
          />
          I reviewed the quote and evidence relations for this revision.
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={!reviewed || !objectId || !quote.trim()}
          onClick={() =>
            void run(async () => {
              await request("presentation.workspace.save_claim", {
                ...scope,
                object_id: objectId,
                quote,
                ...(claimId ? { claim_id: claimId } : {}),
                evidence: links.map((e) => ({
                  chunk_id: e.chunk_id,
                  sha256: e.sha256,
                  relation: e.relation,
                })),
                confirm: true,
              });
              await load();
              reset();
            })
          }
        >
          Save reviewed claim
        </button>
        {claimId ? (
          <button type="button" className="secondary-button" onClick={reset}>
            Start new claim
          </button>
        ) : null}
      </fieldset>
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
