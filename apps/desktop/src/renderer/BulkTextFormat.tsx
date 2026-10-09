import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type Target = {
  object_id: string;
  current_text: string | null;
  text_format_editable: boolean;
  text_style: {
    editable: boolean;
    fingerprint: string | null;
    color_editable: boolean;
    alignment_editable: boolean;
  } | null;
};
type Property = "bold" | "italic" | "font_size_pt" | "font_color" | "alignment";
const properties: Property[] = [
  "bold",
  "italic",
  "font_size_pt",
  "font_color",
  "alignment",
];
const labels: Record<Property, string> = {
  bold: "Bold",
  italic: "Italic",
  font_size_pt: "Font size",
  font_color: "Font color",
  alignment: "Alignment",
};

export function BulkTextFormat({
  projectId,
  documentId,
  revisionId,
  slideId,
  slideNumber,
  selection,
  disabled,
  onRestore,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  slideId: string;
  slideNumber: number;
  selection: { object_id: string; name: string }[];
  disabled: boolean;
  onRestore: (applied: boolean) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [targets, setTargets] = useState<Target[]>([]);
  const [chosen, setChosen] = useState<Partial<Record<Property, boolean>>>({});
  const [bold, setBold] = useState(true);
  const [italic, setItalic] = useState(true);
  const [size, setSize] = useState("24");
  const [color, setColor] = useState("#2563EB");
  const [alignment, setAlignment] = useState("left");
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
  const values = {
    bold,
    italic,
    font_size_pt: Number(size),
    font_color: color,
    alignment,
  };
  const replacement = Object.fromEntries(
    properties
      .filter((property) => chosen[property])
      .map((property) => [property, values[property]]),
  );
  const draft = JSON.stringify({
    selection,
    chosen,
    bold,
    italic,
    size,
    color,
    alignment,
  });
  const matches = draft === previewDraft;
  const valid =
    Object.keys(replacement).length > 0 &&
    (!chosen.font_size_pt ||
      (/^\d+$/.test(size) && Number(size) >= 6 && Number(size) <= 96)) &&
    (!chosen.font_color || /^#[0-9A-Fa-f]{6}$/.test(color));
  const unsupported = selection.filter((item) => {
    const target = targets.find((t) => t.object_id === item.object_id);
    return (
      !target?.text_format_editable ||
      !target.text_style?.editable ||
      !target.text_style.fingerprint ||
      target.current_text === null ||
      (chosen.font_color && !target.text_style.color_editable) ||
      (chosen.alignment && !target.text_style.alignment_editable)
    );
  });
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
    if (open) dialog.current?.showModal();
  }, [open]);
  useEffect(() => {
    setReviewed(false);
  }, [draft]);
  useEffect(() => {
    setLoaded(false);
    setReviewed(false);
  }, [displayedImage]);
  useEffect(() => {
    if (native.pending) setReviewed(false);
  }, [native.pending]);
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
            project_id: projectId,
            document_id: documentId,
            plan_id: owned.current.plan_id,
          })
          .catch(() => undefined);
    },
    [projectId, documentId],
  );
  const message = (e: unknown) =>
    isCoreError(e)
      ? e.message
      : e instanceof Error
        ? e.message
        : "The selected text could not be formatted.";
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
    if (disabled || selection.length < 2 || selection.length > 20) return;
    setOpen(true);
    setBusy(true);
    setError("");
    setTargets([]);
    setChosen({});
    setPlan(null);
    setImage(null);
    setReviewed(false);
    saved.current = false;
    try {
      const inventory = unwrapInvokeResult<{
        revision_id: string;
        slide_id: string;
        targets: Target[];
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_text_targets",
          { ...scope, revision_id: revisionId, slide_number: slideNumber },
        ),
      );
      if (
        inventory.revision_id !== revisionId ||
        inventory.slide_id !== slideId
      )
        throw new Error(
          "The selected slide changed. Refresh before formatting.",
        );
      setTargets(inventory.targets);
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
      !valid ||
      unsupported.length ||
      selection.length < 2 ||
      selection.length > 20
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
      const next = unwrapInvokeResult<
        EditPlanIdentity & { changed: boolean; baseline_revision_id: string }
      >(
        await window.presenterCopilot.core.request(
          "presentation.workspace.prepare_edit_plan",
          {
            ...scope,
            expected_revision_id: revisionId,
            summary: `Format ${selection.length} selected text objects`,
            operations: selection.map((item) => {
              const target = targets.find(
                (t) => t.object_id === item.object_id,
              )!;
              return {
                type: "format_text_shape",
                params: {
                  slide_id: slideId,
                  object_id: item.object_id,
                  expected_text: target.current_text,
                  expected_style_fingerprint: target.text_style!.fingerprint,
                  replacement_style: replacement,
                },
              };
            }),
          },
        ),
      );
      owned.current = next;
      if (next.baseline_revision_id !== revisionId)
        throw new Error("The formatting preview revision changed.");
      if (!next.changed) {
        await discard();
        setError("The selected text already uses these settings.");
        return;
      }
      touched.current = true;
      const slides = await openEditPlanPreview(scope, next);
      if (slides[slideNumber - 1]?.slide_id !== slideId)
        throw new Error("The selected slide changed.");
      const bytes = new Uint8Array(await renderEditPlanSlide(slideNumber));
      setImage(
        URL.createObjectURL(new Blob([bytes.buffer], { type: "image/png" })),
      );
      setPlan(next);
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
      !matches ||
      !valid ||
      unsupported.length
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
        disabled={disabled || selection.length < 2 || selection.length > 20}
        onClick={() => void show()}
      >
        Format selected text
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-bulk-format-title"
              onCancel={(event) => {
                event.preventDefault();
                if (!busy) void finish();
              }}
            >
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void preview();
                }}
              >
                <h2 id="pw-bulk-format-title">
                  Format selected text on slide {slideNumber}
                </h2>
                <p>
                  Choose the properties to apply to all {selection.length}{" "}
                  selected objects. Other formatting and text stay unchanged.
                  Review the whole slide before saving one revision.
                </p>
                <ul>
                  {selection.map((item) => (
                    <li key={item.object_id}>{item.name}</li>
                  ))}
                </ul>
                {error ? <p role="alert">{error}</p> : null}
                {!busy && unsupported.length ? (
                  <p role="status">
                    These objects cannot accept all chosen properties:{" "}
                    {unsupported.map((item) => item.name).join(", ")}. Close
                    this dialog and adjust the selection or choose different
                    properties. No objects will be skipped.
                  </p>
                ) : null}
                <fieldset disabled={busy || saved.current}>
                  <legend>Properties to change</legend>
                  {properties.map((property) => (
                    <div key={property}>
                      <label className="pw-edit-review-ack">
                        <input
                          type="checkbox"
                          aria-label={`Apply ${labels[property].toLowerCase()} to selection`}
                          checked={Boolean(chosen[property])}
                          onChange={(event) =>
                            setChosen({
                              ...chosen,
                              [property]: event.target.checked,
                            })
                          }
                        />
                        {labels[property]}
                      </label>
                      {property === "bold" || property === "italic" ? (
                        <select
                          aria-label={`Selected text ${property}`}
                          value={String(property === "bold" ? bold : italic)}
                          disabled={!chosen[property]}
                          onChange={(event) =>
                            property === "bold"
                              ? setBold(event.target.value === "true")
                              : setItalic(event.target.value === "true")
                          }
                        >
                          <option value="true">On</option>
                          <option value="false">Off</option>
                        </select>
                      ) : null}
                      {property === "font_size_pt" ? (
                        <input
                          aria-label="Selected text font size"
                          type="number"
                          min={6}
                          max={96}
                          value={size}
                          disabled={!chosen[property]}
                          onChange={(event) => setSize(event.target.value)}
                        />
                      ) : null}
                      {property === "font_color" ? (
                        <input
                          aria-label="Selected text font color"
                          type="color"
                          value={color}
                          disabled={!chosen[property]}
                          onChange={(event) => setColor(event.target.value)}
                        />
                      ) : null}
                      {property === "alignment" ? (
                        <select
                          aria-label="Selected text alignment"
                          value={alignment}
                          disabled={!chosen[property]}
                          onChange={(event) => setAlignment(event.target.value)}
                        >
                          {["left", "center", "right", "justify"].map(
                            (value) => (
                              <option key={value} value={value}>
                                {value}
                              </option>
                            ),
                          )}
                        </select>
                      ) : null}
                    </div>
                  ))}
                </fieldset>
                <p className="muted">
                  Font sizes are whole points from 6 to 96. Unsupported or stale
                  targets reject the entire edit.
                </p>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy || saved.current || !valid || unsupported.length > 0
                  }
                  onClick={() => void preview()}
                >
                  Preview selected text formatting
                </button>
                {displayedImage ? (
                  <section aria-label="Selected text formatting preview">
                    <p className="muted">
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review all selected text before saving."
                        : "Browser appearance is experimental. Select PowerPoint appearance to review all proposed formatting."}
                    </p>
                    {native.controls}
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage}
                        alt="Proposed selected text formatting"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError(
                            "The selected text formatting preview did not load.",
                          );
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
                        onChange={(event) => setReviewed(event.target.checked)}
                      />
                      I reviewed every selected text object.
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
                    !valid ||
                    unsupported.length > 0 ||
                    saved.current
                  }
                  onClick={() => void apply()}
                >
                  Save reviewed selected formatting
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  Discard selected formatting preview
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
