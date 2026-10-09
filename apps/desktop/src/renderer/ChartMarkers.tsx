import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type MarkersChart = {
  object_id: string;
  name: string;
  editable: boolean;
  reason: string | null;
  fingerprint?: string;
  markers?: {
    editable: boolean;
    reason: string | null;
    symbols: string[];
    series: {
      name: string;
      marker_symbol: string | null;
      marker_size: number | null;
      point_overrides: number;
    }[];
  };
};
export function ChartMarkers({
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
  const [items, setItems] = useState<MarkersChart[]>([]);
  const [choice, setChoice] = useState("");
  const [series, setSeries] = useState(0);
  const [symbol, setSymbol] = useState("circle");
  const [size, setSize] = useState("7");
  const selected = items.find((item) => item.object_id === choice);
  const targetEditable = selected?.editable && selected.markers?.editable;
  const validSize =
    /^\d+$/.test(size) && Number(size) >= 2 && Number(size) <= 72;
  const seriesInfo = selected?.markers?.series[series];
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
  const draft = JSON.stringify({ choice, series, symbol, size });
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
        : "The chart marker could not be verified.";
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
  function choose(item?: MarkersChart) {
    setChoice(item?.object_id || "");
    setSeries(0);
    setSymbol(
      item?.markers?.symbols.includes(
        item.markers.series[0]?.marker_symbol || "",
      )
        ? (item?.markers?.series[0]?.marker_symbol ?? "circle")
        : "circle",
    );
    setSize(String(item?.markers?.series[0]?.marker_size ?? 7));
    setReviewed(false);
  }
  function chooseTarget(index: number) {
    setSeries(index);
    const value = selected?.markers?.series[index];
    setSymbol(
      selected?.markers?.symbols.includes(value?.marker_symbol || "")
        ? value!.marker_symbol!
        : "circle",
    );
    setSize(String(value?.marker_size ?? 7));
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
        items: MarkersChart[];
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
        result.items.find((item) => item.editable && item.markers?.editable) ||
          result.items[0],
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    if (busy || saved.current || !targetEditable || !validSize) return;
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
            summary: "Edit reviewed native chart marker",
            operations: [
              {
                type: "set_chart_marker",
                params: {
                  slide_id: slideId,
                  object_id: choice,
                  expected_fingerprint: selected?.fingerprint,
                  series_index: series,
                  marker_symbol: symbol,
                  marker_size: Number(size),
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The marker preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The marker did not change the presentation.");
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
        Chart markers
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-markers-title"
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
                <h2 id="pw-markers-title">
                  Chart markers on slide {slideNumber}
                </h2>
                <p>
                  Choose a marker shape and size for an ordinary native
                  line-chart series. Review the proposed chart before saving.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Chart
                  <select
                    aria-label="Marker chart"
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
                        {item.editable && item.markers?.editable
                          ? ""
                          : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {selected &&
                (!selected.editable || !selected.markers?.editable) ? (
                  <p role="status">
                    {selected.reason ||
                      selected.markers?.reason ||
                      "This chart's markers cannot be safely edited."}
                  </p>
                ) : null}
                <fieldset disabled={busy || saved.current || !targetEditable}>
                  <legend>Line-series markers</legend>
                  <label>
                    Series
                    <select
                      aria-label="Marker series"
                      value={series}
                      onChange={(e) => chooseTarget(Number(e.target.value))}
                    >
                      {selected?.markers?.series.map((item, index) => (
                        <option key={index} value={index}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p>
                    Current marker:{" "}
                    {seriesInfo?.marker_symbol ?? "native default"} · size{" "}
                    {seriesInfo?.marker_size ?? "native default"}. Individual
                    point overrides: {seriesInfo?.point_overrides ?? 0}.
                  </p>
                  <label>
                    Marker shape
                    <select
                      aria-label="Marker shape"
                      value={symbol}
                      onChange={(e) => {
                        setSymbol(e.target.value);
                        setReviewed(false);
                      }}
                    >
                      {(selected?.markers?.symbols ?? []).map((value) => (
                        <option key={value} value={value}>
                          {value === "none"
                            ? "None (hide series markers)"
                            : value}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Size in points
                    <input
                      aria-label="Marker size in points"
                      type="number"
                      min="2"
                      max="72"
                      step="1"
                      value={size}
                      onChange={(e) => {
                        setSize(e.target.value);
                        setReviewed(false);
                      }}
                    />
                  </label>
                  {!validSize ? (
                    <p role="alert">
                      Choose a whole-number marker size from 2 to 72 points.
                    </p>
                  ) : null}
                  <p>
                    Marker colors and individual point overrides stay intact.
                    Hiding series markers retains point overrides. Line styles,
                    data and labels remain unchanged. Use PowerPoint appearance
                    to inspect the proposed markers.
                  </p>
                </fieldset>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy || saved.current || !targetEditable || !validSize
                  }
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview chart marker"}
                </button>
                {image ? (
                  <section aria-label="Chart marker preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review the markers before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify the native markers."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed chart marker"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The native marker preview did not load.");
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
                      I reviewed these markers and the chart legend.
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
                  Save reviewed chart marker
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved chart marker"
                    : "Discard chart marker preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
