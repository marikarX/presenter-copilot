import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type Stop = {
  position_percent: string;
  color: string;
  opacity_percent: string;
};
type Fill = {
  kind: string;
  color?: string;
  opacity_percent?: number;
  angle_degrees?: number;
  stops?: {
    position_percent: number;
    color: string;
    opacity_percent: number;
  }[];
};
type FillsChart = {
  object_id: string;
  name: string;
  editable: boolean;
  reason: string | null;
  fingerprint?: string;
  fills?: {
    editable: boolean;
    reason: string | null;
    property: string;
    series_editable: boolean;
    points_editable: boolean;
    series: {
      name: string;
      fill: Fill;
      points: { category: string; fill: Fill }[];
    }[];
  };
};
export function ChartFills({
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
  const [items, setItems] = useState<FillsChart[]>([]);
  const [choice, setChoice] = useState("");
  const [series, setSeries] = useState(0);
  const [point, setPoint] = useState("");
  const [color, setColor] = useState("#2563EB");
  const [kind, setKind] = useState("solid");
  const [opacity, setOpacity] = useState("100");
  const [angle, setAngle] = useState("0");
  const [stops, setStops] = useState<Stop[]>([
    { position_percent: "0", color: "#2563EB", opacity_percent: "100" },
    { position_percent: "100", color: "#DB2777", opacity_percent: "100" },
  ]);
  const whole = (value: string, min: number, max: number) =>
    /^\d+$/.test(value) && Number(value) >= min && Number(value) <= max;
  const validFill =
    kind === "solid"
      ? whole(opacity, 0, 100)
      : whole(angle, 0, 359) &&
        stops.length >= 2 &&
        stops.length <= 8 &&
        stops.every(
          (stop, index) =>
            whole(stop.position_percent, 0, 100) &&
            whole(stop.opacity_percent, 0, 100) &&
            (index === 0
              ? Number(stop.position_percent) === 0
              : Number(stop.position_percent) >
                Number(stops[index - 1]!.position_percent)),
        ) &&
        Number(stops.at(-1)?.position_percent) === 100;
  const fill =
    kind === "solid"
      ? { kind, color, opacity_percent: Number(opacity) }
      : {
          kind,
          angle_degrees: Number(angle),
          stops: stops.map((stop) => ({
            ...stop,
            position_percent: Number(stop.position_percent),
            opacity_percent: Number(stop.opacity_percent),
          })),
        };
  function prefill(value?: Fill) {
    setKind(value?.kind === "linear_gradient" ? "linear_gradient" : "solid");
    setColor(value?.color || "#2563EB");
    setOpacity(String(value?.opacity_percent ?? 100));
    setAngle(String(value?.angle_degrees ?? 0));
    setStops(
      value?.stops?.map((stop) => ({
        ...stop,
        position_percent: String(stop.position_percent),
        opacity_percent: String(stop.opacity_percent),
      })) ?? [
        { position_percent: "0", color: "#2563EB", opacity_percent: "100" },
        { position_percent: "100", color: "#DB2777", opacity_percent: "100" },
      ],
    );
  }
  const selected = items.find((item) => item.object_id === choice);
  const targetEditable =
    selected?.editable &&
    selected.fills?.editable &&
    (point === ""
      ? selected.fills.series_editable
      : selected.fills.points_editable);
  const seriesInfo = selected?.fills?.series[series];
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
    series,
    point,
    color,
    kind,
    opacity,
    angle,
    stops,
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
        : "The chart fill could not be verified.";
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
  function choose(item?: FillsChart) {
    setChoice(item?.object_id || "");
    setSeries(0);
    const pointValue = item?.fills?.series_editable ? "" : "0";
    setPoint(pointValue);
    prefill(
      pointValue === ""
        ? item?.fills?.series[0]?.fill
        : item?.fills?.series[0]?.points[0]?.fill,
    );
    setReviewed(false);
  }
  function chooseTarget(index: number, pointValue: string) {
    setSeries(index);
    setPoint(pointValue);
    setReviewed(false);
    const item = selected?.fills?.series[index];
    prefill(
      pointValue === "" ? item?.fill : item?.points[Number(pointValue)]?.fill,
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
        items: FillsChart[];
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
        result.items.find((item) => item.editable && item.fills?.editable) ||
          result.items[0],
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    if (busy || saved.current || !targetEditable || !validFill) return;
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
            summary: "Edit reviewed native chart fill",
            operations: [
              {
                type: "set_chart_fill",
                params: {
                  slide_id: slideId,
                  object_id: choice,
                  expected_fingerprint: selected?.fingerprint,
                  series_index: series,
                  point_index: point === "" ? null : Number(point),
                  fill,
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The fill preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The fill did not change the presentation.");
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
        Chart fills & opacity
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-fills-title"
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
                <h2 id="pw-fills-title">Chart fills on slide {slideNumber}</h2>
                <p>
                  Set native solid or linear-gradient fills with opacity. Review
                  the chart before saving.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Chart
                  <select
                    aria-label="Fill chart"
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
                        {item.editable && item.fills?.editable
                          ? ""
                          : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {selected &&
                (!selected.editable || !selected.fills?.editable) ? (
                  <p role="status">
                    {selected.reason ||
                      selected.fills?.reason ||
                      "This chart's fills cannot be safely edited."}
                  </p>
                ) : null}
                <fieldset
                  disabled={
                    busy ||
                    saved.current ||
                    !selected?.editable ||
                    !selected.fills?.editable
                  }
                >
                  <legend>Fill target</legend>
                  <label>
                    Series
                    <select
                      aria-label="Fill series"
                      value={series}
                      onChange={(e) =>
                        chooseTarget(Number(e.target.value), point)
                      }
                    >
                      {selected?.fills?.series.map((item, index) => (
                        <option key={index} value={index}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Apply to
                    <select
                      aria-label="Fill data point"
                      value={point}
                      onChange={(e) => chooseTarget(series, e.target.value)}
                    >
                      {selected?.fills?.series_editable ? (
                        <option value="">Entire series</option>
                      ) : null}
                      {selected?.fills?.points_editable
                        ? seriesInfo?.points.map((item, index) => (
                            <option key={index} value={index}>
                              {item.category}
                            </option>
                          ))
                        : null}
                    </select>
                  </label>
                  <p>
                    Current formatting:{" "}
                    {(point === ""
                      ? seriesInfo?.fill.kind
                      : seriesInfo?.points[Number(point)]?.fill.kind
                    )?.replaceAll("_", " ") ?? "native default"}
                    . Explicit new fill replaces the selected native fill and
                    opacity; outlines, markers and effects remain intact.
                  </p>
                  <label>
                    Fill style
                    <select
                      aria-label="Chart fill style"
                      value={kind}
                      onChange={(e) => {
                        setKind(e.target.value);
                        setReviewed(false);
                      }}
                    >
                      <option value="solid">Solid RGB with opacity</option>
                      <option value="linear_gradient">Linear gradient</option>
                    </select>
                  </label>
                  {kind === "solid" ? (
                    <>
                      <label>
                        Fill fill
                        <input
                          aria-label="Chart fill RGB"
                          type="color"
                          value={color}
                          onChange={(e) => {
                            setColor(e.target.value.toUpperCase());
                            setReviewed(false);
                          }}
                        />
                      </label>
                      <label>
                        Opacity percent
                        <input
                          aria-label="Chart fill opacity"
                          type="number"
                          min="0"
                          max="100"
                          step="1"
                          value={opacity}
                          onChange={(e) => {
                            setOpacity(e.target.value);
                            setReviewed(false);
                          }}
                        />
                      </label>
                    </>
                  ) : (
                    <>
                      <label>
                        Angle in degrees
                        <input
                          aria-label="Gradient angle"
                          type="number"
                          min="0"
                          max="359"
                          step="1"
                          value={angle}
                          onChange={(e) => {
                            setAngle(e.target.value);
                            setReviewed(false);
                          }}
                        />
                      </label>
                      {stops.map((stop, index) => (
                        <fieldset key={index}>
                          <legend>Gradient stop {index + 1}</legend>
                          <label>
                            Position percent
                            <input
                              aria-label={`Gradient stop ${index + 1} position`}
                              type="number"
                              min="0"
                              max="100"
                              step="1"
                              disabled={
                                index === 0 || index === stops.length - 1
                              }
                              value={stop.position_percent}
                              onChange={(e) => {
                                setStops(
                                  stops.map((item, i) =>
                                    i === index
                                      ? {
                                          ...item,
                                          position_percent: e.target.value,
                                        }
                                      : item,
                                  ),
                                );
                                setReviewed(false);
                              }}
                            />
                          </label>
                          <label>
                            Fill
                            <input
                              aria-label={`Gradient stop ${index + 1} color`}
                              type="color"
                              value={stop.color}
                              onChange={(e) => {
                                setStops(
                                  stops.map((item, i) =>
                                    i === index
                                      ? {
                                          ...item,
                                          color: e.target.value.toUpperCase(),
                                        }
                                      : item,
                                  ),
                                );
                                setReviewed(false);
                              }}
                            />
                          </label>
                          <label>
                            Opacity percent
                            <input
                              aria-label={`Gradient stop ${index + 1} opacity`}
                              type="number"
                              min="0"
                              max="100"
                              step="1"
                              value={stop.opacity_percent}
                              onChange={(e) => {
                                setStops(
                                  stops.map((item, i) =>
                                    i === index
                                      ? {
                                          ...item,
                                          opacity_percent: e.target.value,
                                        }
                                      : item,
                                  ),
                                );
                                setReviewed(false);
                              }}
                            />
                          </label>
                          {index > 0 && index < stops.length - 1 ? (
                            <button
                              type="button"
                              className="secondary-button"
                              aria-label={`Remove gradient stop ${index + 1}`}
                              onClick={() => {
                                setStops(stops.filter((_, i) => i !== index));
                                setReviewed(false);
                              }}
                            >
                              Remove stop
                            </button>
                          ) : null}
                        </fieldset>
                      ))}
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={stops.length >= 8 || !validFill}
                        onClick={() => {
                          if (
                            !validFill ||
                            stops.length < 2 ||
                            stops.length >= 8
                          )
                            return;
                          let index = 1;
                          for (let i = 2; i < stops.length; i++)
                            if (
                              Number(stops[i]!.position_percent) -
                                Number(stops[i - 1]!.position_percent) >
                              Number(stops[index]!.position_percent) -
                                Number(stops[index - 1]!.position_percent)
                            )
                              index = i;
                          const position = Math.floor(
                            (Number(stops[index - 1]!.position_percent) +
                              Number(stops[index]!.position_percent)) /
                              2,
                          );
                          setStops([
                            ...stops.slice(0, index),
                            {
                              position_percent: String(position),
                              color: stops[index - 1]!.color,
                              opacity_percent:
                                stops[index - 1]!.opacity_percent,
                            },
                            ...stops.slice(index),
                          ]);
                          setReviewed(false);
                        }}
                      >
                        Add gradient stop
                      </button>
                    </>
                  )}
                  {!validFill ? (
                    <p role="alert">
                      Use whole percentages from 0 to 100, angles from 0 to 359,
                      and strictly increasing gradient stops from 0 to 100.
                    </p>
                  ) : null}
                  <p>
                    Opacity 100% is opaque; 0% is transparent. Bars, columns and
                    pie slices change fill only; lines change stroke fill only.
                    Series edits retain individual point overrides. Use
                    PowerPoint appearance to verify transparency and gradients.
                  </p>
                </fieldset>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy || saved.current || !targetEditable || !validFill
                  }
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview chart fill"}
                </button>
                {image ? (
                  <section aria-label="Chart fill preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review fill and opacity before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify native fills and opacity."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed chart fill"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The native fill preview did not load.");
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
                      I reviewed this fill and the chart legend.
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
                  Save reviewed chart fill
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved chart fill"
                    : "Discard chart fill preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
