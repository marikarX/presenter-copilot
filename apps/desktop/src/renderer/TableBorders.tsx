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
  borders?: {
    editable: boolean;
    reason: string | null;
    cell_borders: Record<
      string,
      {
        source: string;
        visible: boolean | null;
        width_pt: number | null;
        color: string | null;
        line_style: string | null;
      }
    >[][];
  };
};
const emptyStyle = {
  border_scope: "outline",
  line_style: "solid",
  width_pt: "1",
  color: "#182132",
};
export function TableBorders({
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
  const [range, setRange] = useState({
    row_start: "1",
    row_end: "1",
    column_start: "1",
    column_end: "1",
  });
  const [style, setStyle] = useState({ ...emptyStyle });
  const selected = items.find((item) => item.object_id === choice);
  const targetEditable = selected?.editable && selected.borders?.editable;
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
  const draft = JSON.stringify({ choice, range, style });
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
        : "The table borders could not be verified.";
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
    setRange({
      row_start: "1",
      row_end: "1",
      column_start: "1",
      column_end: String(item?.cells?.[0]?.length || 1),
    });
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
        result.items.find((item) => item.editable && item.borders?.editable) ||
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
            summary: "Edit reviewed native table borders",
            operations: [
              {
                type: "set_table_borders",
                params: {
                  slide_id: slideId,
                  object_id: choice,
                  expected_fingerprint: selected?.fingerprint,
                  ...Object.fromEntries(
                    Object.entries(range).map(([key, value]) => [
                      key,
                      Number(value) - 1,
                    ]),
                  ),
                  border_scope: style.border_scope,
                  line_style: style.line_style,
                  width_pt:
                    style.line_style === "none" ? null : Number(style.width_pt),
                  color: style.line_style === "none" ? null : style.color,
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The borders preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The borders did not change the presentation.");
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
        Table borders
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-table-borders-title"
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
                <h2 id="pw-table-borders-title">
                  Table borders on slide {slideNumber}
                </h2>
                <p>
                  Apply or remove borders for a native cell range. Review the
                  selected range and shared neighboring edges before saving.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Table
                  <select
                    aria-label="Borders table"
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
                        {item.editable && item.borders?.editable
                          ? ""
                          : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {selected && !targetEditable ? (
                  <p role="status">
                    {selected.reason ||
                      selected.borders?.reason ||
                      "This table cannot be safely formatted."}
                  </p>
                ) : null}
                <fieldset disabled={busy || saved.current || !targetEditable}>
                  <legend>Cell range</legend>
                  <div className="pw-object-clipboard">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => {
                        setRange({
                          row_start: "1",
                          row_end: "1",
                          column_start: "1",
                          column_end: String(selected?.cells?.[0]?.length || 1),
                        });
                        setReviewed(false);
                      }}
                    >
                      Header row
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => {
                        setRange({
                          row_start: "1",
                          row_end: String(selected?.cells?.length || 1),
                          column_start: "1",
                          column_end: String(selected?.cells?.[0]?.length || 1),
                        });
                        setReviewed(false);
                      }}
                    >
                      Entire table
                    </button>
                  </div>
                  <div className="pw-geometry-fields">
                    {(
                      [
                        ["row_start", "First row"],
                        ["row_end", "Last row"],
                        ["column_start", "First column"],
                        ["column_end", "Last column"],
                      ] as const
                    ).map(([key, label]) => (
                      <label key={key}>
                        {label}
                        <input
                          aria-label={`Borders ${label.toLowerCase()}`}
                          type="number"
                          min={1}
                          max={
                            key.startsWith("row")
                              ? selected?.cells?.length
                              : selected?.cells?.[0]?.length
                          }
                          value={range[key]}
                          onChange={(e) => {
                            setRange({ ...range, [key]: e.target.value });
                            setReviewed(false);
                          }}
                        />
                      </label>
                    ))}
                  </div>
                  {selected?.cells ? (
                    <div className="pw-data-review">
                      <table>
                        <caption>Selected cell text is preserved</caption>
                        <tbody>
                          {selected.cells
                            .slice(
                              Number(range.row_start) - 1,
                              Number(range.row_end),
                            )
                            .map((row, index) => (
                              <tr key={index}>
                                {row
                                  .slice(
                                    Number(range.column_start) - 1,
                                    Number(range.column_end),
                                  )
                                  .map((cell, col) => (
                                    <td key={col}>{cell}</td>
                                  ))}
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </fieldset>
                {selected?.borders?.cell_borders ? (
                  <div className="pw-data-review">
                    <table>
                      <caption>Current range borders</caption>
                      <thead>
                        <tr>
                          <th>Cell</th>
                          {["left", "right", "top", "bottom"].map((side) => (
                            <th key={side}>{side}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {selected.borders.cell_borders
                          .slice(
                            Number(range.row_start) - 1,
                            Number(range.row_end),
                          )
                          .flatMap((row, index) =>
                            row
                              .slice(
                                Number(range.column_start) - 1,
                                Number(range.column_end),
                              )
                              .map((cell, col) => (
                                <tr key={`${index}-${col}`}>
                                  <td>
                                    {Number(range.row_start) + index},
                                    {Number(range.column_start) + col}
                                  </td>
                                  {["left", "right", "top", "bottom"].map(
                                    (side) => {
                                      const edge = cell[side];
                                      return (
                                        <td key={side}>
                                          {!edge || edge.source === "inherited"
                                            ? "Inherited"
                                            : edge.visible === false
                                              ? "Removed"
                                              : `${edge.line_style ?? "native"} · ${edge.width_pt ?? "native"} pt · ${edge.color ?? "native color"}`}
                                        </td>
                                      );
                                    },
                                  )}
                                </tr>
                              )),
                          )}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                <fieldset disabled={busy || saved.current || !targetEditable}>
                  <legend>Border changes</legend>
                  <label>
                    Edges
                    <select
                      aria-label="Border edges"
                      value={style.border_scope}
                      onChange={(event) =>
                        change("border_scope", event.target.value)
                      }
                    >
                      {[
                        ["outline", "Outline"],
                        ["all", "All"],
                        ["inside", "Inside"],
                        ["horizontal", "Inside horizontal"],
                        ["vertical", "Inside vertical"],
                        ["top", "Top"],
                        ["bottom", "Bottom"],
                        ["left", "Left"],
                        ["right", "Right"],
                      ].map(([value, text]) => (
                        <option key={value} value={value}>
                          {text}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Line style
                    <select
                      aria-label="Border line style"
                      value={style.line_style}
                      onChange={(event) =>
                        change("line_style", event.target.value)
                      }
                    >
                      {[
                        ["solid", "Solid"],
                        ["dash", "Dash"],
                        ["dot", "Dot"],
                        ["none", "Remove"],
                      ].map(([value, text]) => (
                        <option key={value} value={value}>
                          {text}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Width (points)
                    <input
                      aria-label="Border width"
                      type="number"
                      min={0.25}
                      max={12}
                      step="0.25"
                      value={style.width_pt}
                      disabled={style.line_style === "none"}
                      onChange={(event) =>
                        change("width_pt", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    Color
                    <input
                      aria-label="Border RGB"
                      type="color"
                      value={style.color}
                      disabled={style.line_style === "none"}
                      onChange={(event) =>
                        change("color", event.target.value.toUpperCase())
                      }
                    />
                  </label>
                  <p>
                    Shared edges also update the adjoining side of a neighboring
                    cell, including outside the selected range. Other edges,
                    cell text, fills and geometry stay intact. Remove suppresses
                    inherited borders. These explicit borders replace the
                    selected edges’ prior line styling; Undo restores it.
                  </p>
                  <p className="muted">
                    The preview may differ from PowerPoint. Review the range and
                    shared edges before saving.
                  </p>
                </fieldset>
                {!hasStyle ? <p>Choose border settings to preview.</p> : null}
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy || saved.current || !targetEditable || !hasStyle
                  }
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview table borders"}
                </button>
                {image ? (
                  <section aria-label="Table borders preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review the table borders before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify the table borders."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed table borders"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The borders preview did not load.");
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
                      I reviewed the selected range and shared border edges.
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
                  Save reviewed table borders
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved table borders"
                    : "Discard table borders preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
