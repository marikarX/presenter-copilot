import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type ColorsChart = {
  object_id: string;
  name: string;
  editable: boolean;
  reason: string | null;
  fingerprint?: string;
  colors?: {
    editable: boolean;
    reason: string | null;
    series_color_property: string;
    series_editable: boolean;
    points_editable: boolean;
    series: {
      name: string;
      color: string | null;
      points: { category: string; color: string | null }[];
    }[];
  };
};
export function ChartColors({
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
  const [items, setItems] = useState<ColorsChart[]>([]);
  const [choice, setChoice] = useState("");
  const [series, setSeries] = useState(0);
  const [point, setPoint] = useState("");
  const [color, setColor] = useState("#2563EB");
  const selected = items.find((item) => item.object_id === choice);
  const targetEditable =
    selected?.editable &&
    selected.colors?.editable &&
    (point === ""
      ? selected.colors.series_editable
      : selected.colors.points_editable);
  const seriesInfo = selected?.colors?.series[series];
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
  const draft = JSON.stringify({ choice, series, point, color });
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
        : "The chart color could not be verified.";
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
  function choose(item?: ColorsChart) {
    setChoice(item?.object_id || "");
    setSeries(0);
    const pointValue = item?.colors?.series_editable ? "" : "0";
    setPoint(pointValue);
    setColor(
      (pointValue === ""
        ? item?.colors?.series[0]?.color
        : item?.colors?.series[0]?.points[0]?.color) || "#2563EB",
    );
    setReviewed(false);
  }
  function chooseTarget(index: number, pointValue: string) {
    setSeries(index);
    setPoint(pointValue);
    setReviewed(false);
    const item = selected?.colors?.series[index];
    setColor(
      (pointValue === ""
        ? item?.color
        : item?.points[Number(pointValue)]?.color) || "#2563EB",
    );
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
        items: ColorsChart[];
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_charts",
          { ...scope, revision_id: revisionId, slide_number: slideNumber },
        ),
      );
      if (result.revision_id !== revisionId || result.slide_id !== slideId)
        throw new Error("The chart selection changed.");
      setItems(result.items);
      choose(
        result.items.find((item) => item.editable && item.colors?.editable) ||
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
            summary: "Edit reviewed native chart color",
            operations: [
              {
                type: "set_chart_color",
                params: {
                  slide_id: slideId,
                  object_id: choice,
                  expected_fingerprint: selected?.fingerprint,
                  series_index: series,
                  point_index: point === "" ? null : Number(point),
                  color,
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The color preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The color did not change the presentation.");
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
        Chart colors
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-colors-title"
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
                <h2 id="pw-colors-title">
                  Chart colors on slide {slideNumber}
                </h2>
                <p>
                  Set an opaque RGB fill and outline for a series or data point.
                  Line series change their stroke color. Review the native chart
                  and its legend before saving.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Chart
                  <select
                    aria-label="Color chart"
                    value={choice}
                    disabled={busy || saved.current}
                    onChange={(e) =>
                      choose(
                        items.find((item) => item.object_id === e.target.value),
                      )
                    }
                  >
                    {!items.length ? (
                      <option value="">No native charts on this slide</option>
                    ) : null}
                    {items.map((item) => (
                      <option key={item.object_id} value={item.object_id}>
                        {item.name}
                        {item.editable && item.colors?.editable
                          ? ""
                          : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {selected &&
                (!selected.editable || !selected.colors?.editable) ? (
                  <p role="status">
                    {selected.reason ||
                      selected.colors?.reason ||
                      "This chart's colors cannot be safely edited."}
                  </p>
                ) : null}
                <fieldset
                  disabled={
                    busy ||
                    saved.current ||
                    !selected?.editable ||
                    !selected.colors?.editable
                  }
                >
                  <legend>Color target</legend>
                  <label>
                    Series
                    <select
                      aria-label="Color series"
                      value={series}
                      onChange={(e) =>
                        chooseTarget(Number(e.target.value), point)
                      }
                    >
                      {selected?.colors?.series.map((item, index) => (
                        <option key={index} value={index}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Apply to
                    <select
                      aria-label="Color data point"
                      value={point}
                      onChange={(e) => chooseTarget(series, e.target.value)}
                    >
                      {selected?.colors?.series_editable ? (
                        <option value="">Entire series</option>
                      ) : null}
                      {selected?.colors?.points_editable
                        ? seriesInfo?.points.map((item, index) => (
                            <option key={index} value={index}>
                              {item.category}
                            </option>
                          ))
                        : null}
                    </select>
                  </label>
                  <p>
                    {selected?.colors?.series_color_property === "outline"
                      ? "Current line color:"
                      : "Current fill:"}{" "}
                    {(point === ""
                      ? seriesInfo?.color
                      : seriesInfo?.points[Number(point)]?.color) ||
                      "native default or custom formatting"}
                    .
                  </p>
                  <label className="pw-shape-color-control">
                    New color
                    <input
                      aria-label="Chart RGB color"
                      type="color"
                      value={color}
                      onChange={(e) => {
                        setColor(e.target.value.toUpperCase());
                        setReviewed(false);
                      }}
                    />
                  </label>
                  <p>Proposed RGB: {color}</p>
                  <p className="muted">
                    Series edits retain individual point and marker overrides.
                    Pie charts edit individual slices; line charts edit series.
                    Widths, dashes, effects, labels and data remain intact.
                    Explicit color replaces the selected fill/outline color and
                    opacity.
                  </p>
                </fieldset>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy || saved.current || !targetEditable}
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview chart color"}
                </button>
                {image ? (
                  <section aria-label="Chart color preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review the chart color before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify the chart color."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed chart color"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The native color preview did not load.");
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
                      I reviewed this color and the chart legend.
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
                  Save reviewed chart color
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved chart color"
                    : "Discard chart color preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
