import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type AxisSettings = {
  axis_kind: "category" | "value";
  visible: boolean;
  tick_labels: string;
  major_gridlines: boolean;
  minor_gridlines: boolean;
  title: string | null;
  number_format: string | null;
  minimum: number | null;
  maximum: number | null;
  major_unit: number | null;
  minor_unit: number | null;
};
type AxisState = AxisSettings & { title_editable: boolean };
type AxisChart = {
  object_id: string;
  name: string;
  editable: boolean;
  reason: string | null;
  fingerprint?: string;
  axes?: { editable: boolean; reason: string | null; axes: AxisState[] };
};
const initial: AxisSettings = {
  axis_kind: "value",
  visible: true,
  tick_labels: "next_to",
  major_gridlines: true,
  minor_gridlines: false,
  title: null,
  number_format: null,
  minimum: null,
  maximum: null,
  major_unit: null,
  minor_unit: null,
};
export function ChartAxes({
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
  const [items, setItems] = useState<AxisChart[]>([]);
  const [choice, setChoice] = useState("");
  const [settings, setSettings] = useState<AxisSettings>(initial);
  const axis = items
    .find((item) => item.object_id === choice)
    ?.axes?.axes.find((item) => item.axis_kind === settings.axis_kind);
  function update(patch: Partial<AxisSettings>) {
    setSettings((value) => ({ ...value, ...patch }));
    setReviewed(false);
  }
  const selected = items.find((item) => item.object_id === choice);
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
  const draft = JSON.stringify({ choice, settings });
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
        : "The chart axes could not be verified.";
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
  function choose(item?: AxisChart) {
    setChoice(item?.object_id || "");
    const value =
      item?.axes?.axes.find((axis) => axis.axis_kind === "value") ??
      item?.axes?.axes[0];
    setSettings(
      value
        ? (Object.fromEntries(
            Object.keys(initial).map((key) => [
              key,
              key === "title" || key === "number_format"
                ? null
                : value[key as keyof AxisSettings],
            ]),
          ) as AxisSettings)
        : initial,
    );
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
        items: AxisChart[];
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_charts",
          {
            ...scope,
            revision_id: revisionId,
            slide_number: slideNumber,
          },
        ),
      );
      if (result.revision_id !== revisionId || result.slide_id !== slideId)
        throw new Error("The chart selection changed.");
      setItems(result.items);
      choose(
        result.items.find((item) => item.editable && item.axes?.editable) ||
          result.items[0],
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    if (
      busy ||
      saved.current ||
      !selected?.editable ||
      !selected.axes?.editable
    )
      return;
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
            summary: "Edit reviewed native chart axes",
            operations: [
              {
                type: "set_chart_axis",
                params: {
                  slide_id: slideId,
                  object_id: choice,
                  expected_fingerprint: selected?.fingerprint,
                  ...settings,
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The axes preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The axes did not change the presentation.");
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
        Chart axes
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-axes-title"
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
                <h2 id="pw-axes-title">Chart axes on slide {slideNumber}</h2>
                <p>
                  Edit category or value axes. Review tick labels, range, titles
                  and gridlines before saving. Fixed bounds can hide data.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Chart
                  <select
                    aria-label="Axis chart"
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
                        {item.editable && item.axes?.editable
                          ? ""
                          : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {selected &&
                (!selected.editable || !selected.axes?.editable) ? (
                  <p role="status">
                    {selected.reason ||
                      selected.axes?.reason ||
                      "This chart axes cannot be safely edited."}
                  </p>
                ) : null}
                <fieldset
                  disabled={
                    busy ||
                    saved.current ||
                    !selected?.editable ||
                    !selected.axes?.editable
                  }
                >
                  <legend>Axis settings</legend>
                  <label>
                    Axis
                    <select
                      aria-label="Axis kind"
                      value={settings.axis_kind}
                      onChange={(event) => {
                        const value = selected?.axes?.axes.find(
                          (axis) => axis.axis_kind === event.target.value,
                        );
                        if (value) {
                          setSettings(
                            Object.fromEntries(
                              Object.keys(initial).map((key) => [
                                key,
                                key === "title" || key === "number_format"
                                  ? null
                                  : value[key as keyof AxisSettings],
                              ]),
                            ) as AxisSettings,
                          );
                          setReviewed(false);
                        }
                      }}
                    >
                      {selected?.axes?.axes.map((axis) => (
                        <option key={axis.axis_kind} value={axis.axis_kind}>
                          {axis.axis_kind === "value"
                            ? "Value axis"
                            : "Category axis"}
                        </option>
                      ))}
                    </select>
                  </label>
                  {(
                    ["visible", "major_gridlines", "minor_gridlines"] as const
                  ).map((field) => (
                    <label className="pw-edit-review-ack" key={field}>
                      <input
                        type="checkbox"
                        aria-label={
                          field === "visible"
                            ? "Show axis"
                            : field === "major_gridlines"
                              ? "Show major gridlines"
                              : "Show minor gridlines"
                        }
                        checked={settings[field]}
                        onChange={(event) =>
                          update({ [field]: event.target.checked })
                        }
                      />
                      {field === "visible"
                        ? "Show axis"
                        : field === "major_gridlines"
                          ? "Major gridlines"
                          : "Minor gridlines"}
                    </label>
                  ))}
                  <label>
                    Tick labels
                    <select
                      aria-label="Axis tick labels"
                      value={settings.tick_labels}
                      onChange={(event) =>
                        update({ tick_labels: event.target.value })
                      }
                    >
                      {[
                        ["next_to", "Next to axis"],
                        ["low", "Low"],
                        ["high", "High"],
                        ["none", "Hidden"],
                      ].map(([value, text]) => (
                        <option key={value} value={value}>
                          {text}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="pw-edit-review-ack">
                    <input
                      type="checkbox"
                      aria-label="Replace axis title"
                      disabled={!axis?.title_editable}
                      checked={settings.title !== null}
                      onChange={(event) =>
                        update({
                          title: event.target.checked
                            ? (axis?.title ?? "")
                            : null,
                        })
                      }
                    />
                    Replace axis title
                  </label>
                  <label>
                    Title
                    <input
                      aria-label="Axis title"
                      maxLength={120}
                      disabled={settings.title === null}
                      value={settings.title ?? axis?.title ?? ""}
                      onChange={(event) =>
                        update({ title: event.target.value })
                      }
                    />
                  </label>
                  {!axis?.title_editable ? (
                    <p>Complex native titles stay intact.</p>
                  ) : (
                    <p className="muted">
                      Leave Replace axis title off to retain it; a blank
                      replacement removes it.
                    </p>
                  )}
                  {settings.axis_kind === "value" ? (
                    <>
                      {(
                        [
                          "minimum",
                          "maximum",
                          "major_unit",
                          "minor_unit",
                        ] as const
                      ).map((field) => (
                        <label key={field}>
                          {field.replaceAll("_", " ")}
                          <input
                            type="number"
                            step="any"
                            aria-label={`Axis ${field.replaceAll("_", " ")}`}
                            value={settings[field] ?? ""}
                            onChange={(event) =>
                              update({
                                [field]:
                                  event.target.value === ""
                                    ? null
                                    : Number(event.target.value),
                              })
                            }
                          />
                        </label>
                      ))}
                      <p className="muted">
                        Blank bounds and units use automatic scaling. Minimum
                        must be less than maximum; minor unit must not exceed
                        major unit.
                      </p>
                      <label className="pw-edit-review-ack">
                        <input
                          type="checkbox"
                          aria-label="Apply axis number format"
                          checked={settings.number_format !== null}
                          onChange={(event) =>
                            update({
                              number_format: event.target.checked
                                ? (axis?.number_format ?? "0.0")
                                : null,
                            })
                          }
                        />
                        Apply number format
                      </label>
                      <label>
                        Number format
                        <input
                          aria-label="Axis number format"
                          maxLength={64}
                          disabled={settings.number_format === null}
                          value={
                            settings.number_format ?? axis?.number_format ?? ""
                          }
                          onChange={(event) =>
                            update({ number_format: event.target.value })
                          }
                        />
                      </label>
                    </>
                  ) : null}
                  <p className="muted">
                    Existing axis styling and data stay intact. Removing
                    gridlines or a title removes their styling; adding them uses
                    native defaults. Undo restores the original. Use PowerPoint
                    appearance to review axes and plot layout before saving.
                  </p>
                </fieldset>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy ||
                    saved.current ||
                    !selected?.editable ||
                    !selected.axes?.editable
                  }
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview chart axes"}
                </button>
                {image ? (
                  <section aria-label="Chart axes preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review the chart axes before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify the chart axes."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed chart axes"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The chart axes preview did not load.");
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
                      I reviewed these axes and the plot area.
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
                  Save reviewed chart axes
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved chart axes"
                    : "Discard chart axes preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
