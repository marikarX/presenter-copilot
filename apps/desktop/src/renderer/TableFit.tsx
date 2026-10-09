import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type Table = {
  object_id: string;
  name: string;
  editable: boolean;
  reason: string | null;
  fingerprint?: string;
  cells?: string[][];
  fit?: {
    editable: boolean;
    reason: string | null;
    row_heights_pt: number[];
    column_widths_pt: number[];
    height_pt: number;
  };
};
const emptyStyle = { strategy: "grow" };
export function TableFit({
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
  const [items, setItems] = useState<Table[]>([]);
  const [choice, setChoice] = useState("");
  const [style, setStyle] = useState({ ...emptyStyle });
  const selected = items.find((item) => item.object_id === choice);
  const targetEditable = selected?.editable && selected.fit?.editable;
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
        : "The table fit could not be verified.";
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
  function choose(item?: Table) {
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
        items: Table[];
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_tables",
          { ...scope, revision_id: revisionId, slide_number: slideNumber },
        ),
      );
      if (result.revision_id !== revisionId || result.slide_id !== slideId)
        throw new Error("The table selection changed.");
      setItems(result.items);
      choose(
        result.items.find((item) => item.editable && item.fit?.editable) ||
          result.items[0],
      );
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
            summary: "Edit reviewed native table fit",
            operations: [
              {
                type: "fit_table_rows",
                params: {
                  slide_id: slideId,
                  object_id: choice,
                  expected_fingerprint: selected?.fingerprint,
                  strategy: style.strategy,
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The fitted rows preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The fitted rows did not change the presentation.");
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
        Auto-fit table rows
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-table-fit-title"
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
                <h2 id="pw-table-fit-title">
                  Auto-fit table rows on slide {slideNumber}
                </h2>
                <p>
                  Measure native cell text and store row heights explicitly.
                  Grow preserves current row minima; compact may shrink rows.
                  Review the resulting table layout before saving.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Table
                  <select
                    aria-label="Fit table"
                    value={choice}
                    disabled={busy || saved.current}
                    onChange={(e) =>
                      choose(
                        items.find((item) => item.object_id === e.target.value),
                      )
                    }
                  >
                    {!items.length ? (
                      <option value="">No native tables on this slide</option>
                    ) : null}
                    {items.map((item) => (
                      <option key={item.object_id} value={item.object_id}>
                        {item.name}
                        {item.editable && item.fit?.editable
                          ? ""
                          : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {selected && !targetEditable ? (
                  <p role="status">
                    {selected.fit?.reason ||
                      selected.reason ||
                      "This table cannot be safely fitted."}
                  </p>
                ) : null}
                <div className="pw-data-review">
                  <table>
                    <caption>Current row heights</caption>
                    <tbody>
                      {selected?.fit?.row_heights_pt?.map((height, index) => (
                        <tr key={index}>
                          <th>Row {index + 1}</th>
                          <td>{height.toFixed(2)} pt</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p>
                    Table height{" "}
                    {selected?.fit?.height_pt?.toFixed(2) ?? "unavailable"} pt.
                    Column widths are preserved.
                  </p>
                </div>
                <fieldset disabled={busy || saved.current || !targetEditable}>
                  <legend>Fitting</legend>
                  <label>
                    Strategy
                    <select
                      aria-label="Table fit strategy"
                      value={style.strategy}
                      onChange={(e) => change("strategy", e.target.value)}
                    >
                      <option value="grow">Grow rows as needed</option>
                      <option value="compact">Compact rows to text</option>
                    </select>
                  </label>
                </fieldset>
                <p className="muted">
                  The table’s position, column widths, text and styling stay
                  unchanged. Row heights and the table’s total height may
                  change. Merged cells constrain every row they span. Fitting
                  requires explicit installed fonts and supported horizontal
                  text; a table that would extend beyond the slide cannot be
                  saved. Font metrics and wrapping may differ from PowerPoint:
                  review text fit and nearby content.
                </p>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy || saved.current || !targetEditable || !hasStyle
                  }
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview table fit"}
                </button>
                {image ? (
                  <section aria-label="Auto-fit table rows preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review the fitted rows before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify the fitted rows."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed table fit"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The fitted rows preview did not load.");
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
                      I reviewed the fitted rows, text fit and nearby content.
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
                  Save reviewed table fit
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved table fit"
                    : "Discard table fit preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
