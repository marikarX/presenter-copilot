import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  buildEvidenceFootnotes,
  citationLabel,
  type FootnoteEvidence,
} from "./evidence-footnote-plan";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

export function EvidenceFootnote({
  scope,
  claim,
  size,
  disabled,
  onRestore,
}: {
  scope: {
    project_id: string;
    document_id: string;
    revision_id: string;
    slide_id: string;
    slide_number: number;
  };
  claim: {
    claim_id: string;
    quote: string;
    source_revision_id: string;
    span_status: string;
    evidence: FootnoteEvidence[];
  };
  size: { width: number; height: number } | null;
  disabled: boolean;
  onRestore: (applied: boolean) => Promise<void>;
}) {
  const eligible =
    claim.source_revision_id === scope.revision_id &&
    claim.span_status === "unchanged";
  const sources = claim.evidence.filter((item) => item.status === "current");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>(
    sources.map((item) => item.chunk_id),
  );
  const [labels, setLabels] = useState<Record<string, string>>(
    Object.fromEntries(
      sources.map((item) => [item.chunk_id, citationLabel(item)]),
    ),
  );
  const [position, setPosition] = useState<"top" | "bottom">("bottom");
  const [color, setColor] = useState("333333");
  const [start, setStart] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [plan, setPlan] = useState<EditPlanIdentity | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [previewDraft, setPreviewDraft] = useState("");
  const owned = useRef<EditPlanIdentity | null>(null);
  const touched = useRef(false);
  const saved = useRef(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const chosen = sources.filter((item) => selected.includes(item.chunk_id));
  const draft = JSON.stringify({ selected, labels, position, color, start });
  const matches = draft === previewDraft;
  let operations: ReturnType<typeof buildEvidenceFootnotes> | null = null;
  let validation = "";
  try {
    if (!size || !eligible)
      throw new Error(
        "Review this claim on the current revision before adding footnotes.",
      );
    operations = buildEvidenceFootnotes(
      scope.slide_id,
      size,
      chosen,
      chosen.map((item) => labels[item.chunk_id] ?? ""),
      position,
      color,
      start === "" ? undefined : Math.round(Number(start) * 914400),
    );
  } catch (e) {
    validation = e instanceof Error ? e.message : "Check the citation choices.";
  }
  const identity = {
    project_id: scope.project_id,
    document_id: scope.document_id,
  };
  const native = usePowerPointAppearance(
    open && plan && matches && eligible && !!operations
      ? {
          projectId: scope.project_id,
          documentId: scope.document_id,
          revisionId: scope.revision_id,
          sourceSha256: plan.sha256,
          planId: plan.plan_id,
        }
      : null,
    scope.slide_number,
  );
  const displayedImage = native.image ?? image;
  useEffect(() => {
    setLoaded(false);
    setReviewed(false);
  }, [displayedImage]);
  useEffect(() => {
    if (native.pending) setReviewed(false);
  }, [native.pending]);

  useEffect(() => {
    if (open) dialog.current?.showModal();
  }, [open]);
  useEffect(
    () => () => {
      if (image) URL.revokeObjectURL(image);
    },
    [image],
  );
  useEffect(
    () => () => {
      if (owned.current)
        void window.presenterCopilot.core
          .request("presentation.workspace.reject_edit_plan", {
            project_id: scope.project_id,
            document_id: scope.document_id,
            plan_id: owned.current.plan_id,
          })
          .catch(() => undefined);
    },
    [scope.project_id, scope.document_id],
  );
  function failure(e: unknown) {
    setError(e instanceof Error || isCoreError(e) ? e.message : String(e));
  }
  async function discard() {
    if (!owned.current) return;
    try {
      unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "presentation.workspace.reject_edit_plan",
          { ...identity, plan_id: owned.current.plan_id },
        ),
      );
    } catch (e) {
      if (!isCoreError(e) || e.code !== "PRESENTATION_EDIT_PLAN_NOT_FOUND")
        throw e;
    }
    owned.current = null;
  }
  async function finish() {
    setBusy(true);
    setError("");
    try {
      await discard();
      if (touched.current || saved.current) await onRestore(saved.current);
      touched.current = false;
      setPlan(null);
      setImage(null);
      setOpen(false);
    } catch (e) {
      failure(e);
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    if (!operations) return;
    setBusy(true);
    setError("");
    setReviewed(false);
    setPlan(null);
    setImage(null);
    try {
      await discard();
      const current = unwrapInvokeResult<{ items: (typeof claim)[] }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_claims",
          scope,
        ),
      );
      const fresh = current.items.find(
        (item) => item.claim_id === claim.claim_id,
      );
      if (
        !fresh ||
        fresh.source_revision_id !== scope.revision_id ||
        fresh.span_status !== "unchanged" ||
        fresh.quote !== claim.quote ||
        chosen.some(
          (item) =>
            !fresh.evidence.some(
              (source) =>
                source.chunk_id === item.chunk_id &&
                source.sha256 === item.sha256 &&
                source.status === "current" &&
                source.relation === item.relation &&
                source.name === item.name &&
                source.ordinal === item.ordinal,
            ),
        )
      )
        throw new Error(
          "The reviewed claim or evidence changed. Close and review it again.",
        );
      const proposed = unwrapInvokeResult<
        EditPlanIdentity & { baseline_revision_id: string; changed: boolean }
      >(
        await window.presenterCopilot.core.request(
          "presentation.workspace.prepare_edit_plan",
          {
            ...identity,
            expected_revision_id: scope.revision_id,
            summary: "Add reviewed evidence footnotes",
            operations,
          },
        ),
      );
      owned.current = proposed;
      if (
        proposed.baseline_revision_id !== scope.revision_id ||
        !proposed.changed
      )
        throw new Error("The footnote preview could not be verified.");
      touched.current = true;
      const slides = await openEditPlanPreview(identity, proposed);
      if (slides[scope.slide_number - 1]?.slide_id !== scope.slide_id)
        throw new Error("The selected slide changed. Reload the presentation.");
      const bytes = new Uint8Array(
        await renderEditPlanSlide(scope.slide_number),
      );
      setImage(
        URL.createObjectURL(new Blob([bytes.buffer], { type: "image/png" })),
      );
      setPreviewDraft(draft);
      setPlan(proposed);
    } catch (e) {
      failure(e);
    } finally {
      setBusy(false);
    }
  }
  async function apply() {
    if (
      busy ||
      native.pending ||
      saved.current ||
      !eligible ||
      !operations ||
      !plan ||
      !matches ||
      !loaded ||
      !reviewed
    )
      return;
    setBusy(true);
    setError("");
    try {
      const result = unwrapInvokeResult<{ sha256: string; changed: boolean }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.apply_edit_plan",
          {
            ...identity,
            plan_id: plan.plan_id,
            reviewed_sha256: plan.sha256,
            confirm: true,
          },
        ),
      );
      if (!result.changed || result.sha256 !== plan.sha256)
        throw new Error("The saved footnotes could not be verified.");
      owned.current = null;
      saved.current = true;
      setPlan(null);
      await finish();
    } catch (e) {
      failure(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled || !eligible || !size || !sources.length}
        onClick={() => {
          saved.current = false;
          setError("");
          setReviewed(false);
          setOpen(true);
        }}
      >
        Add evidence footnotes
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review pw-authored-review"
              aria-label="Reviewed evidence footnotes"
              onCancel={(event) => {
                event.preventDefault();
                if (!busy) void finish();
              }}
            >
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void preview();
                }}
              >
                <p className="eyebrow">SOURCE CITATIONS</p>
                <h2>Add evidence footnotes</h2>
                <blockquote>{claim.quote}</blockquote>
                <p>
                  Choose reviewed excerpts and edit their citation labels.
                  Footnotes are editable native text, saved as one revision.
                  Source relations record your judgment. Check legibility and
                  overlap in the preview.
                </p>
                <fieldset disabled={busy || saved.current}>
                  <legend>Reviewed sources</legend>
                  {sources.map((source, index) => (
                    <section key={source.chunk_id}>
                      <label>
                        <input
                          type="checkbox"
                          aria-label={`Include source ${index + 1}`}
                          checked={selected.includes(source.chunk_id)}
                          onChange={(event) => {
                            setSelected((previous) =>
                              event.target.checked
                                ? [...previous, source.chunk_id]
                                : previous.filter(
                                    (id) => id !== source.chunk_id,
                                  ),
                            );
                            setReviewed(false);
                          }}
                        />
                        {citationLabel(source)}
                      </label>
                      <details>
                        <summary>Read source excerpt {index + 1}</summary>
                        <p>{source.text}</p>
                      </details>
                      <label>
                        Citation label {index + 1}
                        <input
                          aria-label={`Citation label ${index + 1}`}
                          value={labels[source.chunk_id] ?? ""}
                          maxLength={140}
                          onChange={(event) => {
                            setLabels((previous) => ({
                              ...previous,
                              [source.chunk_id]: event.target.value,
                            }));
                            setReviewed(false);
                          }}
                        />
                      </label>
                    </section>
                  ))}
                  <label>
                    Footnote position
                    <select
                      aria-label="Footnote position"
                      value={position}
                      onChange={(event) => {
                        setPosition(event.target.value as "top" | "bottom");
                        setStart("");
                        setReviewed(false);
                      }}
                    >
                      <option value="bottom">Bottom</option>
                      <option value="top">Top</option>
                    </select>
                  </label>
                  <label>
                    Citation block starts at (inches)
                    <input
                      type="number"
                      step="0.05"
                      min="0"
                      aria-label="Citation block starts at (inches)"
                      value={
                        start === ""
                          ? (
                              (position === "top"
                                ? 228600
                                : (size?.height ?? 0) -
                                  228600 -
                                  274320 * chosen.length) / 914400
                            ).toFixed(2)
                          : start
                      }
                      onChange={(event) => {
                        setStart(event.target.value);
                        setReviewed(false);
                      }}
                    />
                  </label>
                  <label>
                    Footnote text color
                    <input
                      type="color"
                      aria-label="Footnote text color"
                      value={`#${color}`}
                      onChange={(event) => {
                        setColor(event.target.value.slice(1));
                        setReviewed(false);
                      }}
                    />
                  </label>
                </fieldset>
                {validation ? <p role="alert">{validation}</p> : null}
                {image ? (
                  <section aria-label="Evidence footnote preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review the citation labels and placement before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify citation labels and placement."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed evidence footnotes"
                        onLoad={() => {
                          setLoaded(true);
                        }}
                        onError={() => {
                          setLoaded(false);
                          setReviewed(false);
                          if (native.image) native.rejectImage();
                          setError("The proposed slide image did not load.");
                        }}
                      />
                      <figcaption>
                        Slide {scope.slide_number} · {chosen.length} citations ·{" "}
                        {position}
                      </figcaption>
                    </figure>
                  </section>
                ) : null}
                {image && !matches ? (
                  <p role="status">
                    The draft changed. Preview again before saving.
                  </p>
                ) : null}
                <label className="pw-edit-review-ack">
                  <input
                    type="checkbox"
                    aria-label="I reviewed the citation labels and placement"
                    checked={reviewed}
                    disabled={
                      busy ||
                      native.pending ||
                      saved.current ||
                      !eligible ||
                      !operations ||
                      !loaded ||
                      !plan ||
                      !matches
                    }
                    onChange={(event) => setReviewed(event.target.checked)}
                  />
                  I reviewed the citation labels and placement.
                </label>
                <p className="muted">
                  Citations are a snapshot of this review. Changing the deck
                  creates a new revision and requires fresh claim review;
                  footnote text does not update automatically.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <div className="pw-create-actions">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void finish()}
                  >
                    {saved.current ? "Open saved footnotes" : "Discard / close"}
                  </button>
                  <button
                    type="submit"
                    disabled={busy || !operations || saved.current}
                  >
                    Preview footnotes
                  </button>
                  <button
                    type="button"
                    disabled={
                      busy ||
                      !plan ||
                      native.pending ||
                      !eligible ||
                      !operations ||
                      !loaded ||
                      !reviewed ||
                      !matches ||
                      saved.current
                    }
                    onClick={() => void apply()}
                  >
                    Save reviewed footnotes
                  </button>
                </div>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
