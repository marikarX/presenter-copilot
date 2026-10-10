import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { TableFit } from "./TableFit";
import { TableMerge } from "./TableMerge";
import { TableBorders } from "./TableBorders";
import { TableFormatting } from "./TableFormatting";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type NativeTable = {
  object_id: string;
  name: string;
  editable: boolean;
  reason: string | null;
  fingerprint: string;
  cells?: string[][];
  locked_cells?: number[][];
  structure_editable?: boolean;
  spans?: {
    regions: {
      row: number;
      column: number;
      row_span: number;
      column_span: number;
    }[];
    owners: number[][][];
  };
};
export function NativeTables({
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
  const [items, setItems] = useState<NativeTable[]>([]);
  const [choice, setChoice] = useState("");
  const [cells, setCells] = useState<string[][]>([
    ["Metric", "Current", "Target"],
    ["", "", ""],
    ["", "", ""],
  ]);
  const [header, setHeader] = useState(true);
  const [rowSources, setRowSources] = useState<(number | null)[]>([]);
  const [columnSources, setColumnSources] = useState<(number | null)[]>([]);
  const [activeRow, setActiveRow] = useState(0);
  const [activeColumn, setActiveColumn] = useState(0);
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
    cells,
    geometry,
    header,
    rowSources,
    columnSources,
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

  const selected = items.find((v) => v.object_id === choice);
  const isCovered = (r: number, c: number) =>
    !!selected?.spans?.regions.length &&
    (selected.spans.owners[r]?.[c]?.[0] !== r ||
      selected.spans.owners[r]?.[c]?.[1] !== c);
  const isLocked = (r: number, c: number) =>
    !!selected?.locked_cells?.some(
      ([row, column]) => row === r && column === c,
    );
  const structural =
    !!choice &&
    (rowSources.length !== selected?.cells?.length ||
      columnSources.length !== selected?.cells?.[0]?.length ||
      rowSources.some((source, index) => source !== index) ||
      columnSources.some((source, index) => source !== index));
  const message = (e: unknown) =>
    isCoreError(e)
      ? e.message
      : e instanceof Error
        ? e.message
        : "The native table could not be verified.";
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
    setRowSources([]);
    setColumnSources([]);
    setActiveRow(0);
    setActiveColumn(0);
    setPlan(null);
    setImage(null);
    setReviewed(false);
    saved.current = false;
    setCells([
      ["Metric", "Current", "Target"],
      ["", "", ""],
      ["", "", ""],
    ]);
    setHeader(true);
    try {
      const result = unwrapInvokeResult<{
        revision_id: string;
        slide_id: string;
        slide_width_emu: number;
        slide_height_emu: number;
        items: NativeTable[];
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_tables",
          { ...scope, revision_id: revisionId, slide_number: slideNumber },
        ),
      );
      if (
        result.revision_id !== revisionId ||
        result.slide_id !== slideId ||
        !Array.isArray(result.items)
      )
        throw new Error("The table selection changed.");
      setItems(result.items);
      const inches = (value: number) => (value / 914400).toFixed(3);
      setGeometry({
        x: inches(result.slide_width_emu * 0.1),
        y: inches(result.slide_height_emu * 0.5),
        width: inches(result.slide_width_emu * 0.8),
        height: inches(result.slide_height_emu * 0.4),
      });
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    if (busy || saved.current) return;
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
      const value = unwrapInvokeResult<
        EditPlanIdentity & { baseline_revision_id: string; changed: boolean }
      >(
        await window.presenterCopilot.core.request(
          "presentation.workspace.prepare_edit_plan",
          {
            ...scope,
            expected_revision_id: revisionId,
            summary: choice
              ? structural
                ? "Restructure reviewed native table"
                : "Edit reviewed native table cells"
              : "Insert reviewed native table",
            operations: [
              {
                type: choice
                  ? structural
                    ? "reshape_table"
                    : "replace_table_cells"
                  : "create_table",
                params: {
                  slide_id: slideId,
                  cells,
                  ...(choice
                    ? {
                        object_id: choice,
                        expected_fingerprint: selected?.fingerprint,
                        ...(structural
                          ? {
                              row_sources: rowSources,
                              column_sources: columnSources,
                            }
                          : {}),
                      }
                    : {
                        geometry: {
                          x_emu: emu(geometry.x),
                          y_emu: emu(geometry.y),
                          width_emu: emu(geometry.width),
                          height_emu: emu(geometry.height),
                        },
                        header_row: header,
                      }),
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The table preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The table cells are unchanged.");
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
  function resize(rows: number, columns: number) {
    if (
      !Number.isInteger(rows) ||
      !Number.isInteger(columns) ||
      rows < 1 ||
      rows > 12 ||
      columns < 1 ||
      columns > 8
    )
      return;
    setCells(
      Array.from({ length: rows }, (_, r) =>
        Array.from({ length: columns }, (_, c) => cells[r]?.[c] || ""),
      ),
    );
    setReviewed(false);
  }
  function changeAxis(
    axis: "row" | "column",
    action: "before" | "after" | "remove",
  ) {
    if (busy || saved.current || !selected?.structure_editable) return;
    const sources = axis === "row" ? rowSources : columnSources;
    const active = axis === "row" ? activeRow : activeColumn;
    const limit = axis === "row" ? 12 : 8;
    if (action === "remove" ? sources.length <= 1 : sources.length >= limit)
      return;
    const index = active + (action === "after" ? 1 : 0);
    const updated = [...sources];
    updated.splice(
      index,
      action === "remove" ? 1 : 0,
      ...(action === "remove" ? [] : [null]),
    );
    if (axis === "row") {
      const next = cells.map((row) => [...row]);
      next.splice(
        index,
        action === "remove" ? 1 : 0,
        ...(action === "remove"
          ? []
          : [Array<string>(cells[0]?.length || 1).fill("")]),
      );
      setCells(next);
      setRowSources(updated);
      setActiveRow(Math.min(index, updated.length - 1));
    } else {
      setCells(
        cells.map((row) => {
          const next = [...row];
          next.splice(
            index,
            action === "remove" ? 1 : 0,
            ...(action === "remove" ? [] : [""]),
          );
          return next;
        }),
      );
      setColumnSources(updated);
      setActiveColumn(Math.min(index, updated.length - 1));
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
        Native tables
      </button>
      <TableFormatting
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
      <TableFit
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
      <TableMerge
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
      <TableBorders
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
              aria-labelledby="pw-table-title"
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
                <h2 id="pw-table-title">
                  Native tables on slide {slideNumber}
                </h2>
                <p>
                  Insert an editable PowerPoint table or review changes to an
                  existing table’s cells, rows and columns. Retained cells keep
                  their styling. Structural changes keep the table’s outer size;
                  new cells inherit the nearest retained row/column’s styling.
                  Review placement and text fit in the native preview.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Table
                  <select
                    aria-label="Native table"
                    value={choice}
                    disabled={busy || saved.current}
                    onChange={(e) => {
                      const selected = items.find(
                        (v) => v.object_id === e.target.value,
                      );
                      setChoice(e.target.value);
                      setRowSources(
                        selected?.cells?.map((_, index) => index) || [],
                      );
                      setColumnSources(
                        selected?.cells?.[0]?.map((_, index) => index) || [],
                      );
                      setActiveRow(0);
                      setActiveColumn(0);
                      setCells(
                        selected?.cells || [
                          ["Metric", "Current", "Target"],
                          ["", "", ""],
                          ["", "", ""],
                        ],
                      );
                      setReviewed(false);
                    }}
                  >
                    <option value="">Insert new table</option>
                    {items.map((v) => (
                      <option
                        key={v.object_id}
                        value={v.object_id}
                        disabled={!v.editable}
                      >
                        {v.name}
                        {v.editable ? "" : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {items
                  .filter((v) => !v.editable)
                  .map((v) => (
                    <p key={v.object_id} className="muted">
                      {v.name}: {v.reason}
                    </p>
                  ))}
                {!choice ? (
                  <>
                    <div className="pw-geometry-fields">
                      <label>
                        Rows
                        <input
                          aria-label="Table rows"
                          type="number"
                          min={1}
                          max={12}
                          value={cells.length}
                          disabled={busy || saved.current}
                          onChange={(e) =>
                            resize(
                              Number(e.target.value),
                              cells[0]?.length || 1,
                            )
                          }
                        />
                      </label>
                      <label>
                        Columns
                        <input
                          aria-label="Table columns"
                          type="number"
                          min={1}
                          max={8}
                          value={cells[0]?.length || 1}
                          disabled={busy || saved.current}
                          onChange={(e) =>
                            resize(cells.length, Number(e.target.value))
                          }
                        />
                      </label>
                    </div>
                    <label>
                      <input
                        type="checkbox"
                        checked={header}
                        disabled={busy || saved.current}
                        onChange={(e) => {
                          setHeader(e.target.checked);
                          setReviewed(false);
                        }}
                      />
                      Style first row as a header
                    </label>
                    <div className="pw-geometry-fields">
                      {(["x", "y", "width", "height"] as const).map((field) => (
                        <label key={field}>
                          {field} (inches)
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            aria-label={`Table ${field} (inches)`}
                            value={geometry[field]}
                            disabled={busy || saved.current}
                            onChange={(e) => {
                              setGeometry({
                                ...geometry,
                                [field]: e.target.value,
                              });
                              setReviewed(false);
                            }}
                          />
                        </label>
                      ))}
                    </div>
                  </>
                ) : null}
                {choice ? (
                  <fieldset
                    disabled={
                      busy || saved.current || !selected?.structure_editable
                    }
                  >
                    <legend>Rows and columns</legend>
                    {(["row", "column"] as const).map((axis) => {
                      const count =
                        axis === "row" ? cells.length : cells[0]?.length || 1;
                      return (
                        <div key={axis} className="pw-object-clipboard">
                          <label>
                            {axis === "row"
                              ? "Selected row"
                              : "Selected column"}
                            <select
                              aria-label={`Selected table ${axis}`}
                              value={axis === "row" ? activeRow : activeColumn}
                              onChange={(e) =>
                                axis === "row"
                                  ? setActiveRow(Number(e.target.value))
                                  : setActiveColumn(Number(e.target.value))
                              }
                            >
                              {Array.from({ length: count }, (_, index) => (
                                <option key={index} value={index}>
                                  {index + 1}
                                </option>
                              ))}
                            </select>
                          </label>
                          {(["before", "after", "remove"] as const).map(
                            (action) => (
                              <button
                                key={action}
                                type="button"
                                className="secondary-button"
                                disabled={
                                  action === "remove"
                                    ? count <= 1
                                    : count >= (axis === "row" ? 12 : 8)
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
                      Removing a row or column removes its draft text. The
                      current deck changes only after preview and save. Row
                      heights and column widths are redistributed within the
                      original size.
                    </p>
                  </fieldset>
                ) : null}
                {choice && selected?.locked_cells?.length ? (
                  <p className="muted">
                    Cells with rich text formatting are locked here; edit them
                    in PowerPoint.
                  </p>
                ) : null}
                {choice &&
                selected?.editable &&
                !selected.structure_editable ? (
                  <p className="muted">
                    This table supports cell-text editing; its native row/column
                    structure is read-only.
                  </p>
                ) : null}
                <div className="pw-native-table-grid">
                  <table>
                    <caption>Draft table cells</caption>
                    <tbody>
                      {cells.map((row, r) => (
                        <tr key={r}>
                          {row.map((value, c) => (
                            <td key={c}>
                              {isCovered(r, c) ? (
                                <span className="muted">
                                  Covered by row{" "}
                                  {(selected?.spans?.owners[r]?.[c]?.[0] ?? 0) +
                                    1}
                                  , column{" "}
                                  {(selected?.spans?.owners[r]?.[c]?.[1] ?? 0) +
                                    1}
                                </span>
                              ) : null}
                              <textarea
                                aria-label={`Row ${r + 1}, column ${c + 1}`}
                                rows={2}
                                maxLength={500}
                                value={value}
                                title={
                                  isLocked(r, c)
                                    ? "Rich text formatting: edit in PowerPoint"
                                    : undefined
                                }
                                disabled={
                                  busy ||
                                  saved.current ||
                                  isCovered(r, c) ||
                                  isLocked(r, c)
                                }
                                onFocus={() => {
                                  setActiveRow(r);
                                  setActiveColumn(c);
                                }}
                                onChange={(e) => {
                                  setCells(
                                    cells.map((line, index) =>
                                      index === r
                                        ? line.map((text, col) =>
                                            col === c ? e.target.value : text,
                                          )
                                        : line,
                                    ),
                                  );
                                  setReviewed(false);
                                }}
                              />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="muted">
                  Up to 12 rows, 8 columns, 500 characters per cell and 10,000
                  characters per table. Each line becomes a paragraph.
                </p>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy || saved.current || (!!choice && !selected?.editable)
                  }
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview native table"}
                </button>
                {image ? (
                  <section aria-label="Native table preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review the table before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify the table."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed native table"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The native table preview did not load.");
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
                      I reviewed this table’s cells, placement and text fit.
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
                  Save reviewed native table
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved native table"
                    : "Discard native table preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
