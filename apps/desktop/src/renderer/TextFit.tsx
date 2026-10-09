import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type TextTarget = {
  object_id: string;
  name: string;
  text: string;
  editable: boolean;
  reason: string | null;
  fingerprint?: string;
  geometry_pt?: { left: number; top: number; width: number; height: number };
  cached_font_scale?: number;
  paragraphs?: {
    runs: { family: string; size_hundredths: string }[];
    end: { family: string; size_hundredths: string };
  }[];
};
const emptyStyle = { strategy: "grow", minimum: "12" };
export function TextFit({
  projectId,
  documentId,
  revisionId,
  slideId,
  slideNumber,
  disabled,
  onRestore,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  slideId: string;
  slideNumber: number;
  disabled: boolean;
  onRestore: (applied: boolean) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<TextTarget[]>([]);
  const [choice, setChoice] = useState("");
  const [style, setStyle] = useState({ ...emptyStyle });
  const selected = items.find((item) => item.object_id === choice);
  const targetEditable = selected?.editable;
  const hasStyle = Object.values(style).some((value) => value !== "");
  const change = (key: keyof typeof emptyStyle, value: string) => {
    setStyle((current) => ({ ...current, [key]: value }));
    setReviewed(false);
  };
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [plan, setPlan] = useState<EditPlanIdentity | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [previewDraft, setPreviewDraft] = useState("");
  const owned = useRef<EditPlanIdentity | null>(null);
  const touched = useRef(false);
  const saved = useRef(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const scope = { project_id: projectId, document_id: documentId };
  const draft = JSON.stringify({ choice, style });
  const matches = draft === previewDraft;
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
    slideNumber,
  );
  const displayedImage = native.image ?? image;
  useEffect(() => {
    setLoaded(false);
    setReviewed(false);
  }, [displayedImage]);
  useEffect(() => {
    if (native.pending) setReviewed(false);
  }, [native.pending]);

  const message = (e: unknown) =>
    isCoreError(e)
      ? e.message
      : e instanceof Error
        ? e.message
        : "The text fit could not be verified.";
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
            ...scope,
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
      if (touched.current || saved.current) await onRestore(saved.current);
      touched.current = false;
      setPlan(null);
      setImage(null);
      setOpen(false);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  function choose(item?: TextTarget) {
    setChoice(item?.object_id || "");
    setStyle({ ...emptyStyle });
    setReviewed(false);
  }
  async function show() {
    setOpen(true);
    setBusy(true);
    setError("");
    setItems([]);
    choose();
    setPlan(null);
    setImage(null);
    setLoaded(false);
    setReviewed(false);
    saved.current = false;
    try {
      const result = unwrapInvokeResult<{
        revision_id: string;
        slide_id: string;
        targets: TextTarget[];
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_text_fit_targets",
          { ...scope, revision_id: revisionId, slide_number: slideNumber },
        ),
      );
      if (result.revision_id !== revisionId || result.slide_id !== slideId)
        throw new Error("The text selection changed.");
      setItems(result.targets);
      choose(result.targets.find((item) => item.editable) || result.targets[0]);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    if (busy || saved.current || !targetEditable) return;
    setBusy(true);
    setError("");
    setReviewed(false);
    setLoaded(false);
    setImage(null);
    setPlan(null);
    try {
      await discard();
      const value = unwrapInvokeResult<
        EditPlanIdentity & { baseline_revision_id: string; changed: boolean }
      >(
        await window.presenterCopilot.core.request(
          "presentation.workspace.prepare_edit_plan",
          {
            ...scope,
            expected_revision_id: revisionId,
            summary: "Edit reviewed native text fit",
            operations: [
              {
                type: "fit_text_shape",
                params: {
                  slide_id: slideId,
                  object_id: choice,
                  expected_fingerprint: selected?.fingerprint,
                  strategy: style.strategy,
                  minimum_size_pt: Number(style.minimum),
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The fitted text preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The fitted text did not change the presentation.");
        return;
      }
      touched.current = true;
      const slides = await openEditPlanPreview(scope, value);
      if (slides[slideNumber - 1]?.slide_id !== slideId)
        throw new Error("The selected slide changed.");
      const bytes = new Uint8Array(await renderEditPlanSlide(slideNumber));
      setImage(
        URL.createObjectURL(new Blob([bytes.buffer], { type: "image/png" })),
      );
      setPlan(value);
      setPreviewDraft(draft);
    } catch (e) {
      setError(message(e));
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
      !matches
    )
      return;
    setBusy(true);
    setError("");
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
      setReviewed(false);
      await finish();
    } catch (e) {
      setError(message(e));
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
        onClick={() => void show()}
      >
        Fit text box
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-text-fit-title"
              onCancel={(e) => {
                e.preventDefault();
                if (!busy) void finish();
              }}
            >
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void preview();
                }}
              >
                <h2 id="pw-text-fit-title">
                  Fit text box on slide {slideNumber}
                </h2>
                <p>
                  Grow the box height or shrink fonts proportionally. Both
                  enable wrapping and replace automatic scaling with explicit
                  fitted values. Review the resulting text and nearby content
                  before saving.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Text box
                  <select
                    aria-label="Fit text box"
                    value={choice}
                    disabled={busy || saved.current}
                    onChange={(e) =>
                      choose(
                        items.find((item) => item.object_id === e.target.value),
                      )
                    }
                  >
                    {!items.length ? (
                      <option value="">
                        No native text shapes on this slide
                      </option>
                    ) : null}
                    {items.map((item) => (
                      <option key={item.object_id} value={item.object_id}>
                        {item.name}
                        {item.editable ? "" : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {selected && !targetEditable ? (
                  <p role="status">
                    {selected.reason ||
                      "This text box cannot be safely fitted."}
                  </p>
                ) : null}
                <div className="pw-data-review">
                  <p>
                    Box width{" "}
                    {selected?.geometry_pt?.width.toFixed(2) ?? "unavailable"}{" "}
                    pt; height{" "}
                    {selected?.geometry_pt?.height.toFixed(2) ?? "unavailable"}{" "}
                    pt.
                  </p>
                  <p>Current text: {selected?.text || "Empty text box"}</p>
                  <table>
                    <caption>Authored fonts</caption>
                    <tbody>
                      {selected?.paragraphs?.flatMap((paragraph, index) =>
                        [...paragraph.runs, paragraph.end].map(
                          (run, runIndex) => (
                            <tr key={`${index}:${runIndex}`}>
                              <th>
                                Paragraph {index + 1},{" "}
                                {runIndex < paragraph.runs.length
                                  ? `run ${runIndex + 1}`
                                  : "end"}
                              </th>
                              <td>
                                {run.family} ·{" "}
                                {(Number(run.size_hundredths) / 100).toFixed(2)}{" "}
                                pt
                              </td>
                            </tr>
                          ),
                        ),
                      )}
                    </tbody>
                  </table>
                  {(selected?.cached_font_scale ?? 1) < 1 ? (
                    <p>
                      PowerPoint previously displayed these fonts at{" "}
                      {((selected?.cached_font_scale ?? 1) * 100).toFixed(1)}%.
                      Grow restores authored sizes. Shrink starts at or below
                      that scale.
                    </p>
                  ) : null}
                </div>
                <fieldset disabled={busy || saved.current || !targetEditable}>
                  <legend>Fitting</legend>
                  <label>
                    Strategy
                    <select
                      aria-label="Text fit strategy"
                      value={style.strategy}
                      onChange={(e) => change("strategy", e.target.value)}
                    >
                      <option value="grow">Grow box height</option>
                      <option value="shrink">
                        Shrink fonts proportionally
                      </option>
                    </select>
                  </label>
                  <label>
                    Minimum font size (pt)
                    <input
                      aria-label="Minimum text fit size"
                      type="number"
                      min={6}
                      max={96}
                      step={1}
                      value={style.minimum}
                      disabled={style.strategy !== "shrink"}
                      onChange={(e) => change("minimum", e.target.value)}
                    />
                  </label>
                </fieldset>
                <p className="muted">
                  Grow retains the width, position and authored fonts. Shrink
                  retains the box geometry and relative font sizes. Both restore
                  authored paragraph spacing and remove cached line-spacing
                  reductions. Text and mixed styles are preserved. Off-slide or
                  unfittable results are rejected. Review wrapping and nearby
                  content in the preview.
                </p>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy ||
                    native.pending ||
                    saved.current ||
                    !targetEditable ||
                    !hasStyle ||
                    !Number.isInteger(Number(style.minimum)) ||
                    Number(style.minimum) < 6 ||
                    Number(style.minimum) > 96
                  }
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview text fit"}
                </button>
                {image ? (
                  <section aria-label="Fit text box preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review text wrapping and nearby content before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify text wrapping and nearby content."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed text fit"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The fitted text preview did not load.");
                        }}
                      />
                    </figure>
                    <label className="pw-edit-review-ack">
                      <input
                        type="checkbox"
                        checked={reviewed && matches}
                        disabled={
                          busy ||
                          native.pending ||
                          !loaded ||
                          !matches ||
                          saved.current
                        }
                        onChange={(e) => setReviewed(e.target.checked)}
                      />
                      I reviewed the fitted text, wrapping and nearby content.
                    </label>
                    {!matches ? (
                      <p>The draft changed. Preview again before saving.</p>
                    ) : null}
                  </section>
                ) : null}
                <button
                  type="button"
                  className="primary-button"
                  disabled={
                    busy ||
                    native.pending ||
                    !plan ||
                    !loaded ||
                    !reviewed ||
                    !matches ||
                    saved.current
                  }
                  onClick={() => void apply()}
                >
                  Save reviewed text fit
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved text fit"
                    : "Discard text fit preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
