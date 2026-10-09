import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

export function InsertAuthoredSlide({
  projectId,
  documentId,
  revisionId,
  slideId,
  layoutSourceSlideId,
  slideNumber,
  disabled,
  onRestore,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  slideId: string;
  layoutSourceSlideId: string;
  slideNumber: number;
  disabled: boolean;
  onRestore: (applied: boolean) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [points, setPoints] = useState("");
  const [notes, setNotes] = useState("");
  const [template, setTemplate] = useState("classic");
  const [layout, setLayout] = useState("points");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<EditPlanIdentity | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [previewNotes, setPreviewNotes] = useState("");
  const [previewDraft, setPreviewDraft] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const owned = useRef<EditPlanIdentity | null>(null);
  const touched = useRef(false);
  const saved = useRef(false);
  const scope = { project_id: projectId, document_id: documentId };
  const bullets = points
    .split("\n")
    .map((point) => point.trim())
    .filter(Boolean);
  const content = {
    title: title.trim(),
    bullets,
    notes: notes.trim(),
    template,
    layout,
  };
  const signature = JSON.stringify(content);
  const valid =
    !!content.title &&
    bullets.length <= 8 &&
    bullets.every((point) => point.length <= 200) &&
    (layout !== "statement" || bullets.length <= 1);
  const changed = signature !== previewDraft;
  const native = usePowerPointAppearance(
    open && plan && !changed
      ? {
          projectId,
          documentId,
          revisionId,
          sourceSha256: plan.sha256,
          planId: plan.plan_id,
        }
      : null,
    slideNumber + 1,
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
            project_id: projectId,
            document_id: documentId,
            plan_id: owned.current.plan_id,
          })
          .catch(() => undefined);
    },
    [projectId, documentId],
  );

  async function discard() {
    if (!owned.current) return;
    try {
      unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "presentation.workspace.reject_edit_plan",
          { ...scope, plan_id: owned.current.plan_id },
        ),
      );
    } catch (caught) {
      if (
        !isCoreError(caught) ||
        caught.code !== "PRESENTATION_EDIT_PLAN_NOT_FOUND"
      )
        throw caught;
    }
    owned.current = null;
  }

  async function finish() {
    setBusy(true);
    setError(null);
    try {
      await discard();
      if (touched.current || saved.current) {
        await onRestore(saved.current);
        touched.current = false;
      }
      setImage(null);
      setPlan(null);
      setOpen(false);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The presentation could not be restored.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function preview() {
    if (!valid) return;
    setBusy(true);
    setError(null);
    setReviewed(false);
    setImage(null);
    setPlan(null);
    try {
      await discard();
      const proposed = unwrapInvokeResult<
        EditPlanIdentity & { baseline_revision_id: string; changed: boolean }
      >(
        await window.presenterCopilot.core.request(
          "presentation.workspace.prepare_edit_plan",
          {
            ...scope,
            expected_revision_id: revisionId,
            summary: `Insert authored slide after slide ${slideNumber}`,
            operations: [
              {
                type: "create_authored_slide",
                params: {
                  slide_id: slideId,
                  layout_source_slide_id: layoutSourceSlideId,
                  ...content,
                },
              },
            ],
          },
        ),
      );
      owned.current = proposed;
      if (
        proposed.baseline_revision_id !== revisionId ||
        proposed.changed !== true
      )
        throw new Error("The insertion preview could not be verified.");
      touched.current = true;
      const slides = await openEditPlanPreview(scope, proposed);
      if (slides[slideNumber - 1]?.slide_id !== slideId || !slides[slideNumber])
        throw new Error("The insertion position changed. Reload the deck.");
      const bytes = await renderEditPlanSlide(slideNumber + 1);
      const copy = new Uint8Array(bytes);
      setImage(
        URL.createObjectURL(new Blob([copy.buffer], { type: "image/png" })),
      );
      setPlan(proposed);
      setPreviewDraft(signature);
      setPreviewNotes(content.notes);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The authored slide could not be previewed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (
      busy ||
      native.pending ||
      saved.current ||
      !plan ||
      !loaded ||
      !reviewed ||
      changed
    )
      return;
    setBusy(true);
    setError(null);
    try {
      unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "presentation.workspace.apply_edit_plan",
          {
            ...scope,
            plan_id: plan.plan_id,
            reviewed_sha256: plan.sha256,
            confirm: true,
          },
        ),
      );
      owned.current = null;
      saved.current = true;
      setPlan(null);
      await finish();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The reviewed slide could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled}
        onClick={() => {
          saved.current = false;
          setReviewed(false);
          setError(null);
          setOpen(true);
        }}
      >
        Insert authored slide
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review pw-authored-review"
              aria-labelledby="pw-insert-title"
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
                <p className="eyebrow">AUTHOR A SLIDE</p>
                <h2 id="pw-insert-title">Insert after slide {slideNumber}</h2>
                <p>
                  Write a new slide, preview it in this deck, then save one
                  reversible revision.
                </p>
                {image ? (
                  <section aria-label="Authored slide preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed inserted slide appearance comes from PowerPoint. Review this slide and its notes before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify the inserted slide."}
                    </p>
                    <h3>Review the inserted slide</h3>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed authored slide"
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
                    </figure>
                    <details>
                      <summary>Speaker notes in this preview</summary>
                      <p>{previewNotes || "No speaker notes."}</p>
                    </details>
                    <label className="pw-edit-review-ack">
                      <input
                        type="checkbox"
                        checked={reviewed && !changed}
                        disabled={
                          busy ||
                          native.pending ||
                          !loaded ||
                          changed ||
                          saved.current
                        }
                        onChange={(event) => setReviewed(event.target.checked)}
                      />
                      I reviewed this slide and its notes.
                    </label>
                    {changed ? (
                      <p role="status">
                        The draft changed. Preview again before saving.
                      </p>
                    ) : null}
                  </section>
                ) : null}
                <details open={!image}>
                  <summary>Edit authored slide content</summary>
                  <label>
                    Slide title
                    <input
                      aria-label="Inserted slide title"
                      value={title}
                      maxLength={120}
                      required
                      disabled={busy || saved.current}
                      onChange={(event) => setTitle(event.target.value)}
                    />
                  </label>
                  <label>
                    Points · one per line
                    <textarea
                      aria-label="Inserted slide points"
                      value={points}
                      rows={4}
                      maxLength={1700}
                      disabled={busy || saved.current}
                      onChange={(event) => setPoints(event.target.value)}
                    />
                  </label>
                  <label>
                    Speaker notes
                    <textarea
                      aria-label="Inserted slide notes"
                      value={notes}
                      rows={3}
                      maxLength={4000}
                      disabled={busy || saved.current}
                      onChange={(event) => setNotes(event.target.value)}
                    />
                  </label>
                  <label>
                    Template
                    <select
                      aria-label="Inserted slide template"
                      value={template}
                      disabled={busy || saved.current}
                      onChange={(event) => setTemplate(event.target.value)}
                    >
                      <option value="classic">Classic</option>
                      <option value="midnight">Midnight</option>
                      <option value="paper">Paper</option>
                    </select>
                  </label>
                  <label>
                    Content layout
                    <select
                      aria-label="Inserted slide layout"
                      value={layout}
                      disabled={busy || saved.current}
                      onChange={(event) => setLayout(event.target.value)}
                    >
                      <option value="points">Points</option>
                      <option value="columns">Two columns</option>
                      <option value="cards">Cards</option>
                      <option value="statement" disabled={bullets.length > 1}>
                        Statement · one key message
                      </option>
                    </select>
                  </label>
                  {!valid && title.trim() ? (
                    <p role="alert">
                      Use up to 8 points of 200 characters each. Statement
                      accepts one point.
                    </p>
                  ) : null}
                </details>
                {error ? <p role="alert">{error}</p> : null}
                <div className="pw-create-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void finish()}
                  >
                    {saved.current ? "Open saved slide" : "Discard / close"}
                  </button>
                  {!saved.current ? (
                    <>
                      <button type="submit" disabled={busy || !valid}>
                        Preview authored slide
                      </button>
                      <button
                        type="button"
                        className="primary-button"
                        disabled={
                          busy ||
                          native.pending ||
                          saved.current ||
                          !plan ||
                          !loaded ||
                          !reviewed ||
                          changed
                        }
                        onClick={() => void apply()}
                      >
                        Save inserted slide
                      </button>
                    </>
                  ) : null}
                </div>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
