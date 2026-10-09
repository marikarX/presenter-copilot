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
  formatting?: {
    editable: boolean;
    reason: string | null;
    cell_styles: Record<string, unknown>[][];
  };
};
const emptyStyle = {
  bold: "",
  italic: "",
  underline: "",
  font_size_pt: "",
  font_color: "",
  fill_color: "",
  alignment: "",
  vertical_alignment: "",
};
export function TableFormatting({
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
  const targetEditable = selected?.editable && selected.formatting?.editable;
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
        : "The table formatting could not be verified.";
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
        result.items.find(
          (item) => item.editable && item.formatting?.editable,
        ) || result.items[0],
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
            summary: "Edit reviewed native table formatting",
            operations: [
              {
                type: "format_table_cells",
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
                  style: Object.fromEntries(
                    Object.entries(style).map(([key, value]) => [
                      key,
                      value === ""
                        ? null
                        : key === "bold" ||
                            key === "italic" ||
                            key === "underline"
                          ? value === "true"
                          : key === "font_size_pt"
                            ? Number(value)
                            : value,
                    ]),
                  ),
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The formatting preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The formatting did not change the presentation.");
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
        Table formatting
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-table-format-title"
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
                <h2 id="pw-table-format-title">
                  Table formatting on slide {slideNumber}
                </h2>
                <p>
                  Style a header, the whole table or a cell range. Text,
                  dimensions, borders and margins stay intact. Review the text
                  fit before saving.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Table
                  <select
                    aria-label="Formatting table"
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
                        {item.editable && item.formatting?.editable
                          ? ""
                          : " · read-only"}
                      </option>
                    ))}
                  </select>
                </label>
                {selected && !targetEditable ? (
                  <p role="status">
                    {selected.reason ||
                      selected.formatting?.reason ||
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
                          aria-label={`Formatting ${label.toLowerCase()}`}
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
                <fieldset disabled={busy || saved.current || !targetEditable}>
                  <legend>Formatting changes</legend>
                  <p>
                    Keep current preserves each cell’s native or inherited
                    setting.
                  </p>
                  {(["bold", "italic", "underline"] as const).map((key) => (
                    <label key={key}>
                      {key === "bold"
                        ? "Bold"
                        : key === "italic"
                          ? "Italic"
                          : "Underline"}
                      <select
                        aria-label={`Table ${key}`}
                        value={style[key]}
                        onChange={(e) => change(key, e.target.value)}
                      >
                        <option value="">Keep current</option>
                        <option value="true">On</option>
                        <option value="false">Off</option>
                      </select>
                    </label>
                  ))}
                  <label className="pw-edit-review-ack">
                    <input
                      type="checkbox"
                      aria-label="Apply table font size"
                      checked={style.font_size_pt !== ""}
                      onChange={(e) =>
                        change("font_size_pt", e.target.checked ? "18" : "")
                      }
                    />
                    Apply font size
                  </label>
                  <label>
                    Font size (points)
                    <input
                      aria-label="Table font size"
                      type="number"
                      min={6}
                      max={96}
                      disabled={style.font_size_pt === ""}
                      value={style.font_size_pt || "18"}
                      onChange={(e) => change("font_size_pt", e.target.value)}
                    />
                  </label>
                  {(["font_color", "fill_color"] as const).map((key) => (
                    <div key={key}>
                      <label className="pw-edit-review-ack">
                        <input
                          type="checkbox"
                          aria-label={
                            key === "font_color"
                              ? "Apply table text color"
                              : "Apply table fill color"
                          }
                          checked={style[key] !== ""}
                          onChange={(e) =>
                            change(
                              key,
                              e.target.checked
                                ? key === "font_color"
                                  ? "#182132"
                                  : "#FFFFFF"
                                : "",
                            )
                          }
                        />
                        {key === "font_color"
                          ? "Apply text color"
                          : "Apply cell fill"}
                      </label>
                      <label className="pw-shape-color-control">
                        {key === "font_color" ? "Text RGB" : "Fill RGB"}
                        <input
                          aria-label={
                            key === "font_color"
                              ? "Table text RGB"
                              : "Table fill RGB"
                          }
                          type="color"
                          disabled={style[key] === ""}
                          value={
                            style[key] ||
                            (key === "font_color" ? "#182132" : "#FFFFFF")
                          }
                          onChange={(e) =>
                            change(key, e.target.value.toUpperCase())
                          }
                        />
                      </label>
                      {style[key] ? (
                        <p>
                          {key === "font_color" ? "Text" : "Fill"}: {style[key]}
                        </p>
                      ) : null}
                    </div>
                  ))}
                  <label>
                    Horizontal alignment
                    <select
                      aria-label="Table horizontal alignment"
                      value={style.alignment}
                      onChange={(e) => change("alignment", e.target.value)}
                    >
                      <option value="">Keep current</option>
                      {["left", "center", "right", "justify"].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Vertical alignment
                    <select
                      aria-label="Table vertical alignment"
                      value={style.vertical_alignment}
                      onChange={(e) =>
                        change("vertical_alignment", e.target.value)
                      }
                    >
                      <option value="">Keep current</option>
                      {["top", "center", "bottom"].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </label>
                </fieldset>
                {!hasStyle ? (
                  <p>Choose at least one formatting change to preview.</p>
                ) : null}
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy || saved.current || !targetEditable || !hasStyle
                  }
                  onClick={() => void preview()}
                >
                  {busy ? "Working…" : "Preview table formatting"}
                </button>
                {image ? (
                  <section aria-label="Table formatting preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review the table formatting before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify the table formatting."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed table formatting"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The formatting preview did not load.");
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
                      I reviewed these cell styles and text fit.
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
                  Save reviewed table formatting
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved table formatting"
                    : "Discard table formatting preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
