import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  buildAppendixPlan,
  type AppendixMode,
  type AppendixSlide,
} from "./appendix-plan";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

export function CreateAppendix({
  projectId,
  documentId,
  revisionId,
  slides,
  currentSlideId,
  disabled,
  onRestore,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  slides: AppendixSlide[];
  currentSlideId: string;
  disabled: boolean;
  onRestore: (applied: boolean, dividerOrdinal: number) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([currentSlideId]);
  const [mode, setMode] = useState<AppendixMode>("move");
  const [title, setTitle] = useState("Appendix");
  const [notes, setNotes] = useState("");
  const [template, setTemplate] = useState("classic");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [plan, setPlan] = useState<EditPlanIdentity | null>(null);
  const [previewDraft, setPreviewDraft] = useState("");
  const [previewIndex, setPreviewIndex] = useState(0);
  const [seen, setSeen] = useState<number[]>([]);
  const [image, setImage] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const owned = useRef<EditPlanIdentity | null>(null);
  const touched = useRef(false);
  const saved = useRef(false);
  const savedOrdinal = useRef(1);
  const scope = { project_id: projectId, document_id: documentId };
  const draft = JSON.stringify({ selected, mode, title, notes, template });
  let composition: ReturnType<typeof buildAppendixPlan> | null = null;
  let validation = "";
  try {
    composition = buildAppendixPlan(
      slides,
      selected,
      mode,
      title,
      notes,
      template,
    );
  } catch (e) {
    validation = e instanceof Error ? e.message : "Check the appendix choices.";
  }
  const matches = draft === previewDraft;
  const complete =
    matches && !!composition && seen.length === composition.selected.length + 1;
  const native = usePowerPointAppearance(
    open && plan && matches
      ? {
          projectId,
          documentId,
          revisionId,
          sourceSha256: plan.sha256,
          planId: plan.plan_id,
        }
      : null,
    composition ? composition.dividerOrdinal + previewIndex : 1,
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
    if (loaded && matches && !busy && !native.pending)
      setSeen((previous) =>
        previous.includes(previewIndex)
          ? previous
          : [...previous, previewIndex],
      );
  }, [loaded, matches, busy, native.pending, previewIndex]);

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
      if (touched.current || saved.current)
        await onRestore(saved.current, savedOrdinal.current);
      touched.current = false;
      setPlan(null);
      setImage(null);
      setOpen(false);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "The current presentation could not be restored.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function showSlide(index: number, ordinal: number) {
    setLoaded(false);
    setReviewed(false);
    setImage(null);
    const bytes = await renderEditPlanSlide(ordinal);
    const copy = new Uint8Array(bytes);
    setImage(
      URL.createObjectURL(new Blob([copy.buffer], { type: "image/png" })),
    );
    setPreviewIndex(index);
  }
  async function preview() {
    if (busy || saved.current || !composition) return;
    setBusy(true);
    setError("");
    setReviewed(false);
    setImage(null);
    setPlan(null);
    setSeen([]);
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
            summary: `${mode === "copy" ? "Copy" : "Move"} ${composition.selected.length} detail slides to an appendix`,
            operations: composition.operations,
          },
        ),
      );
      owned.current = proposed;
      if (proposed.baseline_revision_id !== revisionId || !proposed.changed)
        throw new Error("The appendix preview could not be verified.");
      touched.current = true;
      const proposedSlides = await openEditPlanPreview(scope, proposed);
      const mainIds = composition.main.map((slide) => slide.slide_id);
      if (
        proposedSlides.length !== composition.total ||
        proposedSlides
          .slice(0, mainIds.length)
          .some((slide, i) => slide.slide_id !== mainIds[i])
      )
        throw new Error(
          "The main presentation order changed. Reload the deck.",
        );
      const divider = proposedSlides[composition.dividerOrdinal - 1];
      const details = proposedSlides.slice(composition.dividerOrdinal);
      if (
        !divider ||
        slides.some((slide) => slide.slide_id === divider.slide_id) ||
        details.length !== composition.selected.length ||
        details.some((slide, i) =>
          mode === "move"
            ? slide.slide_id !== composition.selected[i]?.slide_id
            : slides.some((original) => original.slide_id === slide.slide_id),
        )
      )
        throw new Error("The proposed appendix order could not be verified.");
      savedOrdinal.current = composition.dividerOrdinal;
      await showSlide(0, composition.dividerOrdinal);
      setPreviewDraft(draft);
      setPlan(proposed);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The appendix could not be previewed.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function browse(index: number) {
    if (busy || saved.current || !composition || !matches || !plan) return;
    setBusy(true);
    setError("");
    try {
      await showSlide(index, composition.dividerOrdinal + index);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "The appendix slide could not be rendered.",
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
      !complete
    )
      return;
    setBusy(true);
    setError("");
    try {
      const result = unwrapInvokeResult<{ sha256: string; changed: boolean }>(
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
      if (!result.changed || result.sha256 !== plan.sha256)
        throw new Error("The saved appendix could not be verified.");
      owned.current = null;
      saved.current = true;
      setPlan(null);
      await finish();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "The reviewed appendix could not be saved.",
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
        disabled={disabled || slides.length >= 5000}
        onClick={() => {
          saved.current = false;
          setReviewed(false);
          setError("");
          setOpen(true);
        }}
      >
        Create appendix
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review pw-authored-review"
              aria-labelledby="pw-appendix-title"
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
                <p className="eyebrow">SUPPORTING DETAIL</p>
                <h2 id="pw-appendix-title">Create an appendix</h2>
                <p>
                  Keep the main story together and place detail slides after an
                  editable divider. Review the full appendix, then save one
                  reversible revision.
                </p>
                {image && composition ? (
                  <section aria-label="Appendix preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed appendix slide appearance comes from PowerPoint. Review every appendix slide and the order before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify appendix slides."}
                    </p>
                    <h3>
                      Review{" "}
                      {previewIndex === 0
                        ? "the divider"
                        : `detail slide ${composition.selected[previewIndex - 1]?.ordinal}`}{" "}
                      · proposed slide{" "}
                      {composition.dividerOrdinal + previewIndex}
                    </h3>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed appendix slide"
                        onLoad={() => {
                          setLoaded(true);
                          if (matches && !busy && !native.pending)
                            setSeen((previous) =>
                              previous.includes(previewIndex)
                                ? previous
                                : [...previous, previewIndex],
                            );
                        }}
                        onError={() => {
                          setLoaded(false);
                          setReviewed(false);
                          if (native.image) native.rejectImage();
                          setError("The proposed slide image did not load.");
                        }}
                      />
                    </figure>
                    <div className="pw-create-actions">
                      <button
                        type="button"
                        disabled={busy || !matches || previewIndex === 0}
                        onClick={() => void browse(previewIndex - 1)}
                      >
                        Previous appendix preview
                      </button>
                      <button
                        type="button"
                        disabled={
                          busy ||
                          !matches ||
                          previewIndex === composition.selected.length
                        }
                        onClick={() => void browse(previewIndex + 1)}
                      >
                        Next appendix preview
                      </button>
                    </div>
                    <p role="status">
                      Viewed {seen.length} of {composition.selected.length + 1}{" "}
                      appendix slides.
                    </p>
                    <label className="pw-edit-review-ack">
                      <input
                        type="checkbox"
                        checked={reviewed && complete}
                        disabled={
                          busy ||
                          native.pending ||
                          !loaded ||
                          !complete ||
                          saved.current
                        }
                        onChange={(event) => setReviewed(event.target.checked)}
                      />
                      I reviewed the divider, every detail slide and the
                      proposed order.
                    </label>
                    {!matches ? (
                      <p role="status">
                        The draft changed. Preview again before saving.
                      </p>
                    ) : null}
                  </section>
                ) : null}
                <details open={!image}>
                  <summary>Edit appendix choices</summary>
                  <label>
                    Detail slides · choose up to 18
                    <select
                      multiple
                      size={Math.min(8, slides.length)}
                      aria-label="Appendix detail slides"
                      value={selected}
                      disabled={busy || saved.current}
                      onChange={(event) => {
                        setSelected(
                          Array.from(
                            event.target.selectedOptions,
                            (option) => option.value,
                          ),
                        );
                        setReviewed(false);
                      }}
                    >
                      {slides.map((slide) => (
                        <option key={slide.slide_id} value={slide.slide_id}>
                          Slide {slide.ordinal}
                          {slide.slide_id === currentSlideId
                            ? " · current"
                            : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Place detail in appendix
                    <select
                      aria-label="Appendix move or copy"
                      value={mode}
                      disabled={busy || saved.current}
                      onChange={(event) => {
                        setMode(event.target.value as AppendixMode);
                        setReviewed(false);
                      }}
                    >
                      <option value="move">Move selected slides</option>
                      <option value="copy">
                        Copy selected slides · keep originals
                      </option>
                    </select>
                  </label>
                  <label>
                    Divider title
                    <input
                      aria-label="Appendix divider title"
                      value={title}
                      maxLength={120}
                      disabled={busy || saved.current}
                      onChange={(event) => setTitle(event.target.value)}
                    />
                  </label>
                  <label>
                    Divider speaker notes
                    <textarea
                      aria-label="Appendix divider notes"
                      value={notes}
                      maxLength={4000}
                      rows={3}
                      disabled={busy || saved.current}
                      onChange={(event) => setNotes(event.target.value)}
                    />
                  </label>
                  <label>
                    Divider template
                    <select
                      aria-label="Appendix divider template"
                      value={template}
                      disabled={busy || saved.current}
                      onChange={(event) => setTemplate(event.target.value)}
                    >
                      <option value="classic">Classic</option>
                      <option value="midnight">Midnight</option>
                      <option value="paper">Paper</option>
                    </select>
                  </label>
                </details>
                {composition ? (
                  <section aria-label="Proposed appendix order">
                    <h3>Proposed order</h3>
                    <p>
                      Main presentation: {composition.main.length} slides in
                      their original order. Divider: slide{" "}
                      {composition.dividerOrdinal}. Total: {composition.total}{" "}
                      slides.
                    </p>
                    <ol>
                      {composition.selected.map((slide) => (
                        <li key={slide.slide_id}>
                          {mode === "copy" ? "Copy of" : "Move"} slide{" "}
                          {slide.ordinal}
                        </li>
                      ))}
                    </ol>
                    <p>
                      Existing slide content and notes stay intact.{" "}
                      {mode === "copy"
                        ? "Copies receive new slide identities."
                        : "Moved slides keep their identities."}{" "}
                      Undo restores the whole previous presentation.
                    </p>
                  </section>
                ) : (
                  <p role="alert">{validation}</p>
                )}
                {error ? <p role="alert">{error}</p> : null}
                <div className="pw-create-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void finish()}
                  >
                    {saved.current ? "Open saved appendix" : "Discard / close"}
                  </button>
                  {!saved.current ? (
                    <>
                      <button type="submit" disabled={busy || !composition}>
                        Preview appendix
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
                          !complete
                        }
                        onClick={() => void apply()}
                      >
                        Save reviewed appendix
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
