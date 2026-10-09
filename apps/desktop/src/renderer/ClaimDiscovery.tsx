import { useEffect, useRef, useState } from "react";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import {
  claimSourceLabel,
  isNativeClaimSourceKind,
  NATIVE_CLAIM_DISCLOSURE,
  type NativeClaimSourceKind,
  type NativeClaimTarget,
} from "./claim-source";

type Target = NativeClaimTarget;
export type ClaimCandidate = {
  object_id: string;
  quote: string;
  kind: string;
  reason: string;
  confidence: number | null;
  object_sha256: string;
  source_kind?: NativeClaimSourceKind;
};
export type ClaimExtractionResult = {
  document_id: string;
  revision_id: string;
  slide_id: string;
  object_ids: string[];
  candidates: ClaimCandidate[];
  summary: string;
  provider_id: string;
  model_id: string;
  inventory_truncated: boolean;
  requires_user_review: boolean;
};
export function ClaimDiscovery({
  scope,
  targets,
  disabled,
  onChoose,
}: {
  scope: {
    project_id: string;
    document_id: string;
    revision_id: string;
    slide_id: string;
    slide_number: number;
  };
  targets: Target[];
  disabled: boolean;
  onChoose: (candidate: ClaimCandidate) => void;
}) {
  const eligible = targets.filter(
    (t) => t.text.trim() && t.text.length <= 6000,
  );
  const [selected, setSelected] = useState<string[]>(
    eligible.slice(0, 1).map((t) => t.object_id),
  );
  const [prepared, setPrepared] = useState<{
    key: string;
    data: ClaimExtractionResult;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const owner = useRef({ live: true, generation: 0 });
  const key = JSON.stringify([scope, targets]);
  const current = useRef(key);
  current.current = key;
  const result = prepared?.key === key ? prepared.data : null;
  useEffect(() => {
    owner.current.generation++;
    setPrepared(null);
    setBusy(false);
    setError("");
    setSelected(eligible.slice(0, 1).map((t) => t.object_id));
  }, [key]);

  useEffect(() => {
    owner.current.live = true;
    return () => {
      owner.current.live = false;
      owner.current.generation++;
    };
  }, []);
  const total = selected.reduce(
    (n, id) => n + (eligible.find((t) => t.object_id === id)?.text.length ?? 0),
    0,
  );
  async function extract() {
    const generation = ++owner.current.generation,
      requested = key,
      ids = [...selected];
    setBusy(true);
    setError("");
    setPrepared(null);
    try {
      const response = unwrapInvokeResult<ClaimExtractionResult>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.extract_claims",
          { ...scope, object_ids: ids },
        ),
      );
      if (
        !owner.current.live ||
        owner.current.generation !== generation ||
        current.current !== requested
      )
        return;
      if (
        response.document_id !== scope.document_id ||
        response.revision_id !== scope.revision_id ||
        response.slide_id !== scope.slide_id ||
        response.requires_user_review !== true ||
        !Array.isArray(response.object_ids) ||
        response.object_ids.length !== ids.length ||
        new Set(response.object_ids).size !== ids.length ||
        response.object_ids.some((id) => !ids.includes(id)) ||
        !Array.isArray(response.candidates) ||
        response.candidates.length > 12 ||
        response.candidates.some((c) => {
          const target = targets.find((t) => t.object_id === c.object_id);
          const text = target?.text;
          return (
            !isNativeClaimSourceKind(c.source_kind ?? "native_text") ||
            (c.source_kind ?? "native_text") !==
              (target?.source_kind ?? "native_text") ||
            !ids.includes(c.object_id) ||
            typeof c.quote !== "string" ||
            !c.quote.trim() ||
            !text ||
            text.indexOf(c.quote) < 0 ||
            text.indexOf(c.quote, text.indexOf(c.quote) + 1) >= 0 ||
            !/^[0-9a-f]{64}$/.test(c.object_sha256)
          );
        })
      )
        throw new Error(
          "The claim candidates no longer match this selected text.",
        );
      setPrepared({ key: requested, data: response });
    } catch (caught) {
      if (
        owner.current.live &&
        owner.current.generation === generation &&
        current.current === requested
      )
        setError(
          isCoreError(caught) || caught instanceof Error
            ? caught.message
            : "Claim candidates could not be prepared.",
        );
    } finally {
      if (owner.current.live && owner.current.generation === generation)
        setBusy(false);
    }
  }
  return (
    <section aria-label="Find claim candidates" className="pw-purpose-panel">
      <h5>Find claim candidates</h5>
      <p className="muted">
        Choose up to eight native representations and 6,000 characters. Your
        configured reasoning provider receives their text and source labels when
        privacy permits. Candidates are unsaved suggestions; review the exact
        quote and supporting evidence before saving a claim.
      </p>
      <p className="muted">{NATIVE_CLAIM_DISCLOSURE}</p>
      <fieldset disabled={disabled || busy}>
        <legend>Text to inspect</legend>
        {eligible.map((t) => (
          <label key={t.object_id} className="pw-review-ack">
            <input
              type="checkbox"
              checked={selected.includes(t.object_id)}
              onChange={(event) => {
                setSelected(
                  event.target.checked
                    ? [...selected, t.object_id]
                    : selected.filter((id) => id !== t.object_id),
                );
                setPrepared(null);
                setError("");
              }}
            />
            {t.label} · {claimSourceLabel(t.source_kind)}
          </label>
        ))}
        <p>
          {selected.length} objects · {total} characters selected
        </p>
        {eligible.length !== targets.length ? (
          <p>
            Empty objects and objects longer than 6,000 characters are excluded.
          </p>
        ) : null}
        <button
          type="button"
          className="secondary-button"
          disabled={!selected.length || selected.length > 8 || total > 6000}
          onClick={() => void extract()}
        >
          {busy ? "Finding claim candidates…" : "Find candidates"}
        </button>
      </fieldset>
      {busy ? (
        <p role="status">Finding exact claim quotes. Nothing is being saved.</p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      {result ? (
        <div>
          <p role="status">
            {result.summary} · {result.candidates.length} candidates ·{" "}
            {result.provider_id} · {result.model_id}
          </p>
          <p className="muted">
            This covers {result.object_ids.length} selected objects. Other
            objects were not analyzed.{" "}
            {result.inventory_truncated
              ? "The slide text inventory is incomplete."
              : ""}{" "}
            Confidence is uncalibrated; it does not establish that a claim is
            true.
          </p>
          {!result.candidates.length ? (
            <p>
              No claim candidates returned. You can still bind an exact quote
              manually.
            </p>
          ) : null}
          {result.candidates.map((c, index) => (
            <article key={`${c.object_id}:${index}`}>
              <blockquote>{c.quote}</blockquote>
              <p>
                {claimSourceLabel(c.source_kind)} · {c.kind} · {c.reason}
              </p>
              <p>
                {c.confidence === null
                  ? "No confidence estimate."
                  : `Provider confidence: ${Math.round(c.confidence * 100)}%.`}
              </p>
              <button
                type="button"
                className="secondary-button"
                disabled={disabled}
                onClick={() => onChoose(c)}
              >
                Review candidate {index + 1}
              </button>
            </article>
          ))}
          <button
            type="button"
            className="secondary-button"
            onClick={() => setPrepared(null)}
          >
            Dismiss candidates
          </button>
        </div>
      ) : null}
    </section>
  );
}
