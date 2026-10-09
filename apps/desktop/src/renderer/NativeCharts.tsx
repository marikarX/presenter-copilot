import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChartColors } from "./ChartColors";
import { ChartFills } from "./ChartFills";
import { ChartMarkers } from "./ChartMarkers";
import { ChartAxes } from "./ChartAxes";
import { ChartLabels } from "./ChartLabels";
import { ChartLegend } from "./ChartLegend";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type NativeChart = {
  object_id: string;
  name: string;
  editable: boolean;
  reason: string | null;
  title_editable?: boolean;
  structure_editable?: boolean;
  structure_reason?: string | null;
  fingerprint?: string;
  data?: {
    title: string;
    chart_type: string;
    categories: string[];
    series: { name: string; values: number[] }[];
  };
};
export function NativeCharts({
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
  const [items, setItems] = useState<NativeChart[]>([]);
  const [choice, setChoice] = useState("");
  const selected = items.find((item) => item.object_id === choice);
  const [title, setTitle] = useState("Pilot outcomes");
  const [kind, setKind] = useState("column");
  const [categorySources, setCategorySources] = useState<(number | null)[]>([]);
  const [seriesSources, setSeriesSources] = useState<(number | null)[]>([]);
  const [activeCategory, setActiveCategory] = useState(0);
  const [activeSeries, setActiveSeries] = useState(0);
  const [cells, setCells] = useState<string[][]>([
    ["Category", "Revenue", "Cost"],
    ["Baseline", "10", "8"],
    ["Pilot", "12", "9"],
    ["Target", "15", "10"],
  ]);
  const [geometry, setGeometry] = useState({
    x: "0",
    y: "0",
    width: "1",
    height: "1",
  });
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
    title,
    kind,
    cells,
    geometry,
    categorySources,
    seriesSources,
  });
  const structural =
    !!choice &&
    (categorySources.length !== selected?.data?.categories.length ||
      seriesSources.length !== selected?.data?.series.length ||
      categorySources.some((source, index) => source !== index) ||
      seriesSources.some((source, index) => source !== index));
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
    setReviewed(false);
  }, [draft]);
  useEffect(() => {
    if (native.pending) setReviewed(false);
  }, [native.pending]);
  const message = (e: unknown) =>
    isCoreError(e)
      ? e.message
      : e instanceof Error
        ? e.message
        : "The native chart could not be verified.";
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
  async function show() {
    setOpen(true);
    setBusy(true);
    setError("");
    setChoice("");
    setItems([]);
    setTitle("Pilot outcomes");
    setKind("column");
    setPlan(null);
    setImage(null);
    setReviewed(false);
    saved.current = false;
    setCells([
      ["Category", "Revenue", "Cost"],
      ["Baseline", "10", "8"],
      ["Pilot", "12", "9"],
      ["Target", "15", "10"],
    ]);
    try {
      const result = unwrapInvokeResult<{
        revision_id: string;
        slide_id: string;
        slide_width_emu: number;
        slide_height_emu: number;
        items: NativeChart[];
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_charts",
          { ...scope, revision_id: revisionId, slide_number: slideNumber },
        ),
      );
      if (result.revision_id !== revisionId || result.slide_id !== slideId)
        throw new Error("The chart selection changed.");
      setItems(result.items);
      const inches = (value: number) => (value / 914400).toFixed(3);
      setGeometry({
        x: inches(result.slide_width_emu * 0.1),
        y: inches(result.slide_height_emu * 0.3),
        width: inches(result.slide_width_emu * 0.8),
        height: inches(result.slide_height_emu * 0.6),
      });
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    if (busy || saved.current || (choice && !selected?.editable)) return;
    setBusy(true);
    setError("");
    setReviewed(false);
    setLoaded(false);
    setImage(null);
    setPlan(null);
    try {
      await discard();
      const emu = (value: string) => {
        const number = Number(value);
        if (!value.trim() || !Number.isFinite(number) || number < 0)
          throw new Error("Enter a valid position and size in inches.");
        return Math.round(number * 914400);
      };
      const categories = cells.slice(1).map((row) => row[0]);
      const series = (cells[0] || []).slice(1).map((name, column) => ({
        name,
        values: cells.slice(1).map((row) => {
          const text = row[column + 1] || "";
          const value = Number(text);
          if (!text.trim() || !Number.isFinite(value))
            throw new Error("Enter a finite number for every chart value.");
          return value;
        }),
      }));
      const value = unwrapInvokeResult<
        EditPlanIdentity & { baseline_revision_id: string; changed: boolean }
      >(
        await window.presenterCopilot.core.request(
          "presentation.workspace.prepare_edit_plan",
          {
            ...scope,
            expected_revision_id: revisionId,
            summary: choice
              ? "Edit reviewed native chart data"
              : "Insert reviewed native chart",
            operations: [
              {
                type: choice
                  ? structural
                    ? "reshape_chart"
                    : "replace_chart_data"
                  : "create_chart",
                params: {
                  slide_id: slideId,
                  title,
                  chart_type: kind,
                  categories,
                  series,
                  ...(structural
                    ? {
                        category_sources: categorySources,
                        series_sources: seriesSources,
                      }
                    : {}),
                  ...(choice
                    ? {
                        object_id: choice,
                        expected_fingerprint: selected?.fingerprint,
                      }
                    : {
                        geometry: {
                          x_emu: emu(geometry.x),
                          y_emu: emu(geometry.y),
                          width_emu: emu(geometry.width),
                          height_emu: emu(geometry.height),
                        },
                      }),
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The chart preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The chart did not change the presentation.");
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
  function resize(categories: number, series: number) {
    if (
      !Number.isInteger(categories) ||
      !Number.isInteger(series) ||
      categories < 1 ||
      categories > 24 ||
      series < 1 ||
      series > (kind === "pie" ? 1 : 6)
    )
      return;
    setCells(
      Array.from({ length: categories + 1 }, (_, r) =>
        Array.from(
          { length: series + 1 },
          (_, c) =>
            cells[r]?.[c] ||
            (r === 0
              ? c === 0
                ? "Category"
                : `Series ${c}`
              : c === 0
                ? `Category ${r}`
                : "0"),
        ),
      ),
    );
    setReviewed(false);
  }
  function changeAxis(
    axis: "category" | "series",
    action: "before" | "after" | "remove",
  ) {
    if (busy || saved.current || !selected?.structure_editable) return;
    const originals = axis === "category" ? categorySources : seriesSources;
    const active = axis === "category" ? activeCategory : activeSeries;
    const limit = axis === "category" ? 24 : kind === "pie" ? 1 : 6;
    if (action === "remove" ? originals.length <= 1 : originals.length >= limit)
      return;
    const index = active + (action === "after" ? 1 : 0);
    const mapping = [...originals];
    mapping.splice(
      index,
      action === "remove" ? 1 : 0,
      ...(action === "remove" ? [] : [null]),
    );
    if (axis === "category") {
      const grid = cells.map((row) => [...row]);
      grid.splice(
        index + 1,
        action === "remove" ? 1 : 0,
        ...(action === "remove" ? [] : [["", ...seriesSources.map(() => "0")]]),
      );
      setCells(grid);
      setCategorySources(mapping);
      setActiveCategory(Math.min(index, mapping.length - 1));
    } else {
      setCells(
        cells.map((row, r) => {
          const next = [...row];
          next.splice(
            index + 1,
            action === "remove" ? 1 : 0,
            ...(action === "remove" ? [] : [r === 0 ? "" : "0"]),
          );
          return next;
        }),
      );
      setSeriesSources(mapping);
      setActiveSeries(Math.min(index, mapping.length - 1));
    }
    setReviewed(false);
  }
  return (
    <>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled}
        onClick={() => void show()}
      >
        Native charts
      </button>
      <ChartColors
        {...{
          projectId,
          documentId,
          revisionId,
          slideId,
          slideNumber,
          disabled,
          onRestore,
        }}
      />
      <ChartMarkers
        {...{
          projectId,
          documentId,
          revisionId,
          slideId,
          slideNumber,
          disabled,
          onRestore,
        }}
      />
      <ChartFills
        {...{
          projectId,
          documentId,
          revisionId,
          slideId,
          slideNumber,
          disabled,
          onRestore,
        }}
      />
      <ChartLegend
        {...{
          projectId,
          documentId,
          revisionId,
          slideId,
          slideNumber,
          disabled,
          onRestore,
        }}
      />
      <ChartLabels
        {...{
          projectId,
          documentId,
          revisionId,
          slideId,
          slideNumber,
          disabled,
          onRestore,
        }}
      />
      <ChartAxes
        {...{
          projectId,
          documentId,
          revisionId,
          slideId,
          slideNumber,
          disabled,
          onRestore,
        }}
      />
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-chart-title"
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
                <h2 id="pw-chart-title">
                  Native charts on slide {slideNumber}
                </h2>
                <p>
                  Create a chart or edit an existing supported chart’s labels
                  and values. Review the proposed chart before saving. Edits
                  preserve type, retained series/point formatting and placement,
                  and use a new embedded data workbook. New series use the app’s
                  chart colors. Structural changes require a new review.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Chart action
                  <select
                    aria-label="Native chart action"
                    value={choice}
                    disabled={busy || saved.current}
                    onChange={(event) => {
                      const value = event.target.value;
                      setChoice(value);
                      setReviewed(false);
                      const data = items.find(
                        (item) => item.object_id === value,
                      )?.data;
                      if (data) {
                        setCategorySources(
                          data.categories.map((_, index) => index),
                        );
                        setSeriesSources(data.series.map((_, index) => index));
                        setActiveCategory(0);
                        setActiveSeries(0);
                        setTitle(data.title);
                        setKind(data.chart_type);
                        setCells([
                          [
                            "Category",
                            ...data.series.map((series) => series.name),
                          ],
                          ...data.categories.map((category, index) => [
                            category,
                            ...data.series.map((series) =>
                              String(series.values[index]),
                            ),
                          ]),
                        ]);
                      }
                    }}
                  >
                    <option value="">Insert new chart</option>
                    {items.map((item) => (
                      <option key={item.object_id} value={item.object_id}>
                        {item.name}
                        {item.editable ? "" : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {choice && !selected?.editable ? (
                  <p role="status">
                    {selected?.reason || "The selected chart is unavailable."}
                  </p>
                ) : null}
                {choice ? (
                  <p>
                    Editing keeps the current chart’s type and placement. The
                    original chart and workbook parts are preserved for other
                    uses. External linked workbooks and extended charts remain
                    read-only.
                  </p>
                ) : null}
                <label>
                  Chart title
                  <input
                    aria-label="Chart title"
                    maxLength={120}
                    value={title}
                    disabled={
                      busy ||
                      saved.current ||
                      (Boolean(choice) && !selected?.title_editable)
                    }
                    onChange={(event) => {
                      setTitle(event.target.value);
                      setReviewed(false);
                    }}
                  />
                </label>
                <label>
                  Chart type
                  <select
                    aria-label="Chart type"
                    value={kind}
                    disabled={busy || saved.current || Boolean(choice)}
                    onChange={(event) => {
                      setKind(event.target.value);
                      if (event.target.value === "pie")
                        setCells(cells.map((row) => row.slice(0, 2)));
                      setReviewed(false);
                    }}
                  >
                    <option value="column">Column</option>
                    <option value="bar">Bar</option>
                    <option value="line">Line</option>
                    <option value="pie">Pie</option>
                  </select>
                </label>
                <div className="pw-geometry-fields">
                  <label>
                    Categories
                    <input
                      aria-label="Chart category count"
                      type="number"
                      min={1}
                      max={24}
                      value={cells.length - 1}
                      disabled={busy || saved.current || Boolean(choice)}
                      onChange={(event) =>
                        resize(
                          Number(event.target.value),
                          (cells[0]?.length || 2) - 1,
                        )
                      }
                    />
                  </label>
                  <label>
                    Series
                    <input
                      aria-label="Chart series count"
                      type="number"
                      min={1}
                      max={kind === "pie" ? 1 : 6}
                      value={(cells[0]?.length || 2) - 1}
                      disabled={busy || saved.current || Boolean(choice)}
                      onChange={(event) =>
                        resize(cells.length - 1, Number(event.target.value))
                      }
                    />
                  </label>
                </div>
                {choice ? (
                  <fieldset
                    disabled={
                      busy || saved.current || !selected?.structure_editable
                    }
                  >
                    <legend>Categories and series</legend>
                    {(["category", "series"] as const).map((axis) => {
                      const count =
                        axis === "category"
                          ? categorySources.length
                          : seriesSources.length;
                      return (
                        <div className="pw-object-clipboard" key={axis}>
                          <label>
                            {axis === "category"
                              ? "Selected category"
                              : "Selected series"}
                            <select
                              aria-label={`Selected chart ${axis}`}
                              value={
                                axis === "category"
                                  ? activeCategory
                                  : activeSeries
                              }
                              onChange={(event) =>
                                axis === "category"
                                  ? setActiveCategory(
                                      Number(event.target.value),
                                    )
                                  : setActiveSeries(Number(event.target.value))
                              }
                            >
                              {Array.from({ length: count }, (_, index) => (
                                <option value={index} key={index}>
                                  {axis === "category"
                                    ? `Category ${index + 1}`
                                    : `Series ${index + 1}`}
                                </option>
                              ))}
                            </select>
                          </label>
                          {(["before", "after", "remove"] as const).map(
                            (action) => (
                              <button
                                type="button"
                                key={action}
                                className="secondary-button"
                                disabled={
                                  action === "remove"
                                    ? count <= 1
                                    : count >=
                                      (axis === "category"
                                        ? 24
                                        : kind === "pie"
                                          ? 1
                                          : 6)
                                }
                                onClick={() => changeAxis(axis, action)}
                              >
                                {action === "remove"
                                  ? `Remove ${axis}`
                                  : `Insert ${axis} ${action}`}
                              </button>
                            ),
                          )}
                        </div>
                      );
                    })}
                    <p className="muted">
                      Removed items lose their draft labels and values. The
                      current deck changes only after preview and save. Name new
                      categories and series before previewing.
                    </p>
                  </fieldset>
                ) : null}
                {choice &&
                selected?.editable &&
                !selected.structure_editable ? (
                  <p className="muted">
                    {selected.structure_reason ||
                      "Structural changes are unavailable for this native chart."}{" "}
                    Labels and values can still be edited.
                  </p>
                ) : null}
                {!choice ? (
                  <div className="pw-geometry-fields">
                    {(["x", "y", "width", "height"] as const).map((field) => (
                      <label key={field}>
                        {field} (inches)
                        <input
                          aria-label={`Chart ${field} (inches)`}
                          type="number"
                          min="0"
                          step="0.01"
                          value={geometry[field]}
                          disabled={busy || saved.current || Boolean(choice)}
                          onChange={(event) => {
                            setGeometry({
                              ...geometry,
                              [field]: event.target.value,
                            });
                            setReviewed(false);
                          }}
                        />
                      </label>
                    ))}
                  </div>
                ) : null}
                <div className="pw-native-table-grid">
                  <table>
                    <caption>Draft chart data</caption>
                    <tbody>
                      {cells.map((row, r) => (
                        <tr key={r}>
                          {row.map((value, c) => (
                            <td key={c}>
                              {r === 0 && c === 0 ? (
                                "Category"
                              ) : (
                                <input
                                  type={r > 0 && c > 0 ? "number" : "text"}
                                  step="any"
                                  maxLength={80}
                                  aria-label={
                                    r === 0
                                      ? `Series ${c} name`
                                      : c === 0
                                        ? `Category ${r}`
                                        : `Category ${r}, series ${c} value`
                                  }
                                  value={value}
                                  onFocus={() => {
                                    if (r > 0) setActiveCategory(r - 1);
                                    if (c > 0) setActiveSeries(c - 1);
                                  }}
                                  disabled={
                                    busy ||
                                    saved.current ||
                                    (Boolean(choice) && !selected?.editable)
                                  }
                                  onChange={(event) => {
                                    setCells(
                                      cells.map((line, index) =>
                                        index === r
                                          ? line.map((text, column) =>
                                              column === c
                                                ? event.target.value
                                                : text,
                                            )
                                          : line,
                                      ),
                                    );
                                    setReviewed(false);
                                  }}
                                />
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="muted">
                  Up to 24 categories and 6 series. Values must be finite and
                  within ±1 trillion. Pie charts use one nonnegative series with
                  a positive total.
                </p>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy ||
                    saved.current ||
                    (Boolean(choice) && !selected?.editable)
                  }
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview native chart"}
                </button>
                {displayedImage ? (
                  <section aria-label="Native chart preview">
                    <p className="muted">
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review chart data, labels and placement before saving."
                        : "Browser appearance is experimental. Select PowerPoint appearance to review the exact proposed chart with Microsoft PowerPoint on Windows."}
                    </p>
                    {native.controls}
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage}
                        alt="Proposed native chart"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The native chart preview did not load.");
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
                      I reviewed this chart’s data, labels and placement.
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
                  Save reviewed native chart
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved native chart"
                    : "Discard native chart preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
