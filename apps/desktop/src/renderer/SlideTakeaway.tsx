import { useEffect, useRef, useState } from "react";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";

type Takeaway = {
  revision_id: string;
  slide_id: string;
  record_token: string | null;
  takeaway: string;
  status: "reviewed" | "needs_review" | "missing";
  lineage_truncated: boolean;
};

export function SlideTakeaway({
  projectId,
  documentId,
  revisionId,
  slideId,
  slideNumber,
  disabled,
  suggestion,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  slideId: string;
  slideNumber: number;
  disabled: boolean;
  suggestion?: string;
}) {
  const [saved, setSaved] = useState<Takeaway | null>(null);
  const [draft, setDraft] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const alive = useRef(true);
  const generation = useRef(0);
  const scope = {
    project_id: projectId,
    document_id: documentId,
    revision_id: revisionId,
    slide_id: slideId,
    slide_number: slideNumber,
  };
  function accept(value: Takeaway) {
    if (
      value.revision_id !== revisionId ||
      value.slide_id !== slideId ||
      typeof value.takeaway !== "string" ||
      !["reviewed", "needs_review", "missing"].includes(value.status)
    )
      throw new Error("The takeaway scope could not be verified.");
    setSaved(value);
    setDraft(value.takeaway);
    setReviewed(false);
  }
  async function load() {
    const attempt = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const response = await window.presenterCopilot.core.request<Takeaway>(
        "presentation.workspace.get_slide_takeaway",
        scope,
      );
      if (alive.current && generation.current === attempt)
        accept(unwrapInvokeResult<Takeaway>(response));
    } catch (e) {
      if (alive.current && generation.current === attempt)
        setError(
          isCoreError(e)
            ? e.message
            : e instanceof Error
              ? e.message
              : "Takeaway could not be loaded.",
        );
    } finally {
      if (alive.current && generation.current === attempt) setBusy(false);
    }
  }
  useEffect(() => {
    alive.current = true;
    void load();
    return () => {
      alive.current = false;
      generation.current += 1;
    };
  }, []);
  async function save() {
    if (!saved || !reviewed) return;
    const attempt = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const response = await window.presenterCopilot.core.request<Takeaway>(
        "presentation.workspace.save_slide_takeaway",
        {
          ...scope,
          takeaway: draft,
          reviewed: true,
          expected_record_token: saved.record_token,
        },
      );
      if (alive.current && generation.current === attempt)
        accept(unwrapInvokeResult<Takeaway>(response));
    } catch (e) {
      if (alive.current && generation.current === attempt)
        setError(
          isCoreError(e)
            ? e.message
            : e instanceof Error
              ? e.message
              : "Takeaway could not be saved.",
        );
    } finally {
      if (alive.current && generation.current === attempt) setBusy(false);
    }
  }
  return (
    <section className="pw-slide-takeaway" aria-label="Slide takeaway review">
      <h4>Review this slide’s takeaway</h4>
      <p>
        Record the message the audience should retain. This is author intent;
        saving does not change slide text or claim evidence.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {saved ? (
        <p role="status">
          {saved.status === "reviewed"
            ? "Takeaway reviewed for this revision."
            : saved.status === "needs_review"
              ? "Inherited takeaway needs review for this revision."
              : "No reviewed takeaway yet."}
        </p>
      ) : null}
      {saved?.lineage_truncated ? (
        <p>Earlier takeaway history is incomplete.</p>
      ) : null}
      <fieldset disabled={disabled || busy || !saved}>
        {suggestion ? (
          <div>
            <p>Unconfirmed narrative finding: {suggestion}</p>
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setDraft(suggestion);
                setReviewed(false);
              }}
            >
              Use finding as takeaway draft
            </button>
          </div>
        ) : null}
        <label>
          Slide takeaway
          <textarea
            aria-label="Slide takeaway"
            maxLength={1000}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setReviewed(false);
            }}
          />
        </label>
        <label className="pw-takeaway-ack">
          <input
            type="checkbox"
            checked={reviewed}
            onChange={(e) => setReviewed(e.target.checked)}
          />
          I reviewed this takeaway for the current slide.
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={!reviewed}
          onClick={() => void save()}
        >
          {busy ? "Saving takeaway…" : "Save reviewed takeaway"}
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={() => {
            setDraft("");
            setReviewed(false);
          }}
        >
          Clear takeaway draft
        </button>
      </fieldset>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled || busy}
        onClick={() => void load()}
      >
        Reload saved takeaway
      </button>
      <p>
        A reviewed blank save clears the takeaway and stops earlier text from
        returning. Deck edits carry earlier text forward for review.
      </p>
    </section>
  );
}
