import { pieLike } from "./chart-kinds";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type LabelState = {
  name: string;
  position: string;
  show_value: boolean;
  show_category: boolean;
  show_series: boolean;
  show_percent: boolean;
  number_format: string | null;
  points: { index: number; custom_text: boolean }[];
};
type LabelChart = {
  object_id: string;
  name: string;
  editable: boolean;
  reason: string | null;
  fingerprint?: string;
  labels?: {
    editable: boolean;
    reason: string | null;
    positions: string[];
    series: LabelState[];
  };
  data?: { chart_type: string; series: { name: string }[] };
};
export function ChartLabels({
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
  const [items, setItems] = useState<LabelChart[]>([]);
  const [choice, setChoice] = useState("");
  const [position, setPosition] = useState("hidden");
  const [seriesIndex, setSeriesIndex] = useState("0");
  const [flags, setFlags] = useState({
    show_value: true,
    show_category: false,
    show_series: false,
    show_percent: false,
  });
  const [applyFormat, setApplyFormat] = useState(false);
  const [numberFormat, setNumberFormat] = useState("0.0");
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
  const draft = JSON.stringify({
    choice,
    seriesIndex,
    position,
    flags,
    applyFormat,
    numberFormat,
  });
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
        : "The chart labels could not be verified.";
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
  function chooseState(item?: LabelChart, index = "0") {
    setSeriesIndex(index);
    const state = item?.labels?.series[index === "all" ? 0 : Number(index)];
    setPosition(index === "all" ? "default" : state?.position || "hidden");
    setFlags({
      show_value:
        index === "all" || state?.position === "hidden"
          ? true
          : state?.show_value || false,
      show_category: index === "all" ? false : state?.show_category || false,
      show_series: index === "all" ? false : state?.show_series || false,
      show_percent:
        pieLike(item?.data?.chart_type) &&
        index !== "all" &&
        (state?.show_percent || false),
    });
    setApplyFormat(false);
    setNumberFormat(state?.number_format || "0.0");
    setReviewed(false);
  }
  function choose(item?: LabelChart) {
    setChoice(item?.object_id || "");
    chooseState(item);
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
        items: LabelChart[];
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
        result.items.find((item) => item.editable && item.labels?.editable) ||
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
      !selected.labels?.editable
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
            summary: "Edit reviewed native chart labels",
            operations: [
              {
                type: "set_chart_labels",
                params: {
                  slide_id: slideId,
                  object_id: choice,
                  expected_fingerprint: selected?.fingerprint,
                  series_index:
                    seriesIndex === "all" ? null : Number(seriesIndex),
                  position,
                  ...flags,
                  number_format: applyFormat ? numberFormat : null,
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The labels preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The labels did not change the presentation.");
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
        Chart labels
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-labels-title"
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
                <h2 id="pw-labels-title">
                  Chart labels on slide {slideNumber}
                </h2>
                <p>
                  Show values, names or pie percentages on chart data. Review
                  the settings and layout before saving.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Chart
                  <select
                    aria-label="Labels chart"
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
                        {item.editable && item.labels?.editable
                          ? ""
                          : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {selected &&
                (!selected.editable || !selected.labels?.editable) ? (
                  <p role="status">
                    {selected.reason ||
                      selected.labels?.reason ||
                      "This chart labels cannot be safely edited."}
                  </p>
                ) : null}
                <fieldset
                  disabled={
                    busy ||
                    saved.current ||
                    !selected?.editable ||
                    !selected.labels?.editable
                  }
                >
                  <legend>Data label settings</legend>
                  <label>
                    Series
                    <select
                      aria-label="Label series"
                      value={seriesIndex}
                      onChange={(e) => chooseState(selected, e.target.value)}
                    >
                      <option value="all">All series</option>
                      {selected?.labels?.series.map((state, index) => (
                        <option key={index} value={String(index)}>
                          {state.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {selected?.labels?.series.map((state, index) =>
                    seriesIndex === "all" || Number(seriesIndex) === index ? (
                      <p key={index}>
                        Current labels for {state.name}:{" "}
                        {state.position.replaceAll("_", " ")} ·{" "}
                        {state.show_value ? "values" : "no values"} ·{" "}
                        {state.show_category ? "categories" : "no categories"} ·{" "}
                        {state.show_series ? "series names" : "no series names"}{" "}
                        ·{" "}
                        {state.show_percent ? "percentages" : "no percentages"}{" "}
                        · format {state.number_format || "native source"}.{" "}
                        {state.points.length} point overrides.
                      </p>
                    ) : null,
                  )}
                  <label>
                    Placement
                    <select
                      aria-label="Label placement"
                      value={position}
                      onChange={(e) => {
                        setPosition(e.target.value);
                        setReviewed(false);
                      }}
                    >
                      {[
                        "hidden",
                        ...(selected?.labels?.positions || ["default"]),
                      ].map((value) => (
                        <option key={value} value={value}>
                          {value === "default"
                            ? "Native default"
                            : value.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                  </label>
                  {(
                    [
                      ["show_value", "Show values"],
                      ["show_category", "Show category names"],
                      ["show_series", "Show series names"],
                      ["show_percent", "Show percentages"],
                    ] as const
                  ).map(([key, label]) => (
                    <label className="pw-edit-review-ack" key={key}>
                      <input
                        type="checkbox"
                        aria-label={label}
                        checked={flags[key]}
                        disabled={
                          position === "hidden" ||
                          (key === "show_percent" &&
                            !pieLike(selected?.data?.chart_type))
                        }
                        onChange={(e) => {
                          setFlags({ ...flags, [key]: e.target.checked });
                          setReviewed(false);
                        }}
                      />
                      {label}
                    </label>
                  ))}
                  <label className="pw-edit-review-ack">
                    <input
                      type="checkbox"
                      aria-label="Apply label number format"
                      checked={applyFormat}
                      disabled={position === "hidden"}
                      onChange={(e) => {
                        setApplyFormat(e.target.checked);
                        setReviewed(false);
                      }}
                    />
                    Apply number format
                  </label>
                  <label>
                    Number format
                    <input
                      aria-label="Label number format"
                      value={numberFormat}
                      maxLength={64}
                      disabled={!applyFormat || position === "hidden"}
                      onChange={(e) => {
                        setNumberFormat(e.target.value);
                        setReviewed(false);
                      }}
                    />
                  </label>
                  <p>
                    Examples: 0.0 for one decimal, $0.00 for currency, or 0% for
                    pie percentages. Keep the current format by leaving Apply
                    number format off.
                  </p>
                  <p>
                    Existing custom text and decoration stay intact; custom text
                    may override displayed content. Requested settings apply to
                    point overrides too. Hiding retains labels for later use.
                    Review crowding and contrast before saving.
                  </p>
                </fieldset>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy ||
                    saved.current ||
                    !selected?.editable ||
                    !selected.labels?.editable
                  }
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview chart labels"}
                </button>
                {image ? (
                  <section aria-label="Chart labels preview">
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review label content, formatting and crowding before saving."
                        : "Browser appearance is experimental and may omit names, percentages or number formatting. Select PowerPoint appearance to review the exact proposed deck with Microsoft PowerPoint on Windows."}
                    </p>
                    {native.controls}
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed chart labels"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The chart labels preview did not load.");
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
                      I reviewed these labels and the plot area.
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
                  Save reviewed chart labels
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved chart labels"
                    : "Discard chart labels preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
