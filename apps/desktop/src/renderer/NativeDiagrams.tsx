import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type Node = { id: string; label: string; parent: string | null };
type Data = { name: string; kind: string; palette: string; nodes: Node[] };
type Geometry = {
  x_emu: number;
  y_emu: number;
  width_emu: number;
  height_emu: number;
};
type Diagram = {
  object_id: string;
  name: string;
  editable: boolean;
  reason: string | null;
  fingerprint: string;
  data?: Data;
  geometry?: Geometry;
};
const initial = (): Data => ({
  name: "Pilot workflow",
  kind: "process",
  palette: "classic",
  nodes: ["Prepare", "Run pilot", "Review outcomes"].map((label, i) => ({
    id: `node${i + 1}`,
    label,
    parent: null,
  })),
});
export function NativeDiagrams({
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
  const [items, setItems] = useState<Diagram[]>([]);
  const [choice, setChoice] = useState("");
  const [data, setData] = useState<Data>(initial);
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
  const [deleting, setDeleting] = useState(false);
  const [previewDraft, setPreviewDraft] = useState("");
  const owned = useRef<EditPlanIdentity | null>(null);
  const touched = useRef(false);
  const saved = useRef(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const scope = { project_id: projectId, document_id: documentId };
  const selected = items.find((v) => v.object_id === choice);
  const draft = JSON.stringify({ choice, data, geometry });
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
        : "The diagram could not be verified.";
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
            project_id: projectId,
            document_id: documentId,
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
  const fromNative = (g: Geometry) => ({
    x: (g.x_emu / 914400).toFixed(3),
    y: (g.y_emu / 914400).toFixed(3),
    width: (g.width_emu / 914400).toFixed(3),
    height: (g.height_emu / 914400).toFixed(3),
  });
  async function show() {
    setOpen(true);
    setBusy(true);
    setError("");
    setChoice("");
    setItems([]);
    setData(initial());
    setPlan(null);
    setImage(null);
    setReviewed(false);
    saved.current = false;
    try {
      const result = unwrapInvokeResult<{
        revision_id: string;
        slide_id: string;
        slide_width_emu: number;
        slide_height_emu: number;
        items: Diagram[];
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_diagrams",
          { ...scope, revision_id: revisionId, slide_number: slideNumber },
        ),
      );
      if (result.revision_id !== revisionId || result.slide_id !== slideId)
        throw new Error("The diagram selection changed.");
      setItems(result.items);
      setGeometry(
        fromNative({
          x_emu: result.slide_width_emu * 0.1,
          y_emu: result.slide_height_emu * 0.3,
          width_emu: result.slide_width_emu * 0.8,
          height_emu: result.slide_height_emu * 0.6,
        }),
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function preview(remove = false) {
    if (busy || saved.current || (choice && !selected?.editable)) return;
    setBusy(true);
    setError("");
    setDeleting(remove);
    setReviewed(false);
    setLoaded(false);
    setPlan(null);
    setImage(null);
    try {
      await discard();
      const nativeGeometry = Object.fromEntries(
        Object.entries(geometry).map(([key, value]) => {
          const number = Number(value);
          if (
            !value.trim() ||
            !Number.isFinite(number) ||
            number < 0 ||
            ((key === "width" || key === "height") && number === 0)
          )
            throw new Error("Use finite placement values and a positive size.");
          return [`${key}_emu`, Math.round(number * 914400)];
        }),
      );
      const value = unwrapInvokeResult<
        EditPlanIdentity & { baseline_revision_id: string; changed: boolean }
      >(
        await window.presenterCopilot.core.request(
          "presentation.workspace.prepare_edit_plan",
          {
            ...scope,
            expected_revision_id: revisionId,
            summary: choice
              ? "Edit reviewed structured diagram"
              : "Insert reviewed structured diagram",
            operations: [
              {
                type: remove
                  ? "delete_diagram"
                  : choice
                    ? "replace_diagram"
                    : "create_diagram",
                params: {
                  slide_id: slideId,
                  ...(remove ? {} : { data, geometry: nativeGeometry }),
                  ...(choice
                    ? {
                        object_id: choice,
                        expected_fingerprint: selected?.fingerprint,
                      }
                    : {}),
                },
              },
            ],
          },
        ),
      );
      owned.current = value;
      if (value.baseline_revision_id !== revisionId)
        throw new Error("The diagram preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("The diagram is unchanged.");
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
  function change(next: Data) {
    setData(next);
    setReviewed(false);
  }
  function kind(next: string) {
    change({
      ...data,
      kind: next,
      nodes: data.nodes.map((node, i) => ({
        ...node,
        parent:
          next === "hierarchy" && i > 0
            ? data.kind === "hierarchy"
              ? node.parent
              : data.nodes[0]!.id
            : null,
      })),
    });
  }
  function remove(index: number) {
    if (data.nodes.length <= 2) return;
    const deleted = data.nodes[index];
    if (!deleted) return;
    const nodes = data.nodes
      .filter((_, i) => i !== index)
      .map((node, i) => ({
        ...node,
        parent:
          data.kind === "hierarchy"
            ? i === 0
              ? null
              : node.parent === deleted.id
                ? deleted.parent ||
                  data.nodes.find((v) => v.id !== deleted.id)!.id
                : node.parent
            : null,
      }));
    change({ ...data, nodes });
  }
  return (
    <>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled}
        onClick={() => void show()}
      >
        Native diagrams
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review pw-native-diagrams"
              aria-labelledby="pw-diagram-title"
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
                <h2 id="pw-diagram-title">
                  Native diagrams on slide {slideNumber}
                </h2>
                <p>
                  Create or edit a process, hierarchy or cycle using native
                  PowerPoint shapes and attached arrows. Review labels,
                  connections, wrapping and placement on the full slide before
                  saving.
                </p>
                {error ? <p role="alert">{error}</p> : null}
                <fieldset disabled={busy || saved.current}>
                  <label>
                    Diagram
                    <select
                      aria-label="Native diagram"
                      value={choice}
                      onChange={(e) => {
                        const item = items.find(
                          (v) => v.object_id === e.target.value,
                        );
                        setChoice(e.target.value);
                        change(item?.data || initial());
                        if (item?.geometry)
                          setGeometry(fromNative(item.geometry));
                      }}
                    >
                      <option value="">Insert new diagram</option>
                      {items.map((item) => (
                        <option
                          key={item.object_id}
                          value={item.object_id}
                          disabled={!item.editable}
                        >
                          {item.name}
                          {item.editable ? "" : " · manual changes preserved"}
                        </option>
                      ))}
                    </select>
                  </label>
                  {items.some((item) => !item.editable) ? (
                    <p>
                      Diagrams with manual native edits or external dependencies
                      are preserved. Continue editing those in PowerPoint, or
                      insert a new diagram.
                    </p>
                  ) : null}
                  <label>
                    Diagram name
                    <input
                      aria-label="Diagram name"
                      maxLength={120}
                      value={data.name}
                      onChange={(e) =>
                        change({ ...data, name: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Structure
                    <select
                      aria-label="Diagram structure"
                      value={data.kind}
                      onChange={(e) => kind(e.target.value)}
                    >
                      <option value="process">Process</option>
                      <option value="hierarchy">Hierarchy</option>
                      <option value="cycle">Cycle</option>
                    </select>
                  </label>
                  <label>
                    Palette
                    <select
                      aria-label="Diagram palette"
                      value={data.palette}
                      onChange={(e) =>
                        change({ ...data, palette: e.target.value })
                      }
                    >
                      <option value="classic">Classic</option>
                      <option value="midnight">Midnight</option>
                      <option value="paper">Paper</option>
                    </select>
                  </label>
                  <p>
                    Use 2–8 concise labels. Process follows the listed order;
                    cycle connects the last node back to the first. Hierarchies
                    use an earlier parent and at most four levels.
                  </p>
                  {data.nodes.map((node, i) => (
                    <fieldset key={node.id}>
                      <legend>Node {i + 1}</legend>
                      <label>
                        Label
                        <textarea
                          aria-label={`Diagram node ${i + 1}`}
                          maxLength={80}
                          rows={2}
                          value={node.label}
                          onChange={(e) =>
                            change({
                              ...data,
                              nodes: data.nodes.map((v, j) =>
                                j === i ? { ...v, label: e.target.value } : v,
                              ),
                            })
                          }
                        />
                      </label>
                      {data.kind === "hierarchy" && i > 0 ? (
                        <label>
                          Parent
                          <select
                            aria-label={`Diagram parent ${i + 1}`}
                            value={node.parent || ""}
                            onChange={(e) =>
                              change({
                                ...data,
                                nodes: data.nodes.map((v, j) =>
                                  j === i
                                    ? { ...v, parent: e.target.value }
                                    : v,
                                ),
                              })
                            }
                          >
                            {data.nodes.slice(0, i).map((v, j) => (
                              <option key={v.id} value={v.id}>
                                {j + 1} · {v.label}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : null}
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={data.nodes.length <= 2}
                        onClick={() => remove(i)}
                      >
                        Remove node {i + 1}
                      </button>
                    </fieldset>
                  ))}
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={data.nodes.length >= 8}
                    onClick={() =>
                      change({
                        ...data,
                        nodes: [
                          ...data.nodes,
                          {
                            id: crypto.randomUUID(),
                            label: "New step",
                            parent:
                              data.kind === "hierarchy"
                                ? data.nodes[0]!.id
                                : null,
                          },
                        ],
                      })
                    }
                  >
                    Add diagram node
                  </button>
                  <fieldset>
                    <legend>Placement in inches</legend>
                    {Object.entries(geometry).map(([key, value]) => (
                      <label key={key}>
                        {key}
                        <input
                          aria-label={`Diagram ${key}`}
                          type="number"
                          step="0.01"
                          value={value}
                          onChange={(e) => {
                            setGeometry({ ...geometry, [key]: e.target.value });
                            setReviewed(false);
                          }}
                        />
                      </label>
                    ))}
                  </fieldset>
                </fieldset>
                <button
                  type="submit"
                  className="secondary-button"
                  disabled={busy || saved.current}
                >
                  Preview native diagram
                </button>
                {choice ? (
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy || saved.current || !selected?.editable}
                    onClick={() => void preview(true)}
                  >
                    Preview diagram deletion
                  </button>
                ) : null}
                {image && deleting ? (
                  <p>
                    This preview removes the entire selected diagram, including
                    its nodes and connections.
                  </p>
                ) : null}
                {image ? (
                  <section aria-label="Native diagram preview">
                    {native.controls}
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint. Review the diagram before saving."
                        : "Browser appearance is experimental. Use PowerPoint appearance to verify the diagram."}
                    </p>
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt="Proposed native diagram"
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError(
                            "The diagram preview image could not be loaded.",
                          );
                        }}
                      />
                      <figcaption>Proposed slide {slideNumber}</figcaption>
                    </figure>
                    <label className="pw-edit-review-ack">
                      <input
                        type="checkbox"
                        disabled={
                          busy ||
                          native.pending ||
                          !loaded ||
                          !matches ||
                          saved.current
                        }
                        checked={reviewed}
                        onChange={(e) => setReviewed(e.target.checked)}
                      />
                      I reviewed this diagram on the current slide.
                    </label>
                  </section>
                ) : null}
                {busy ? <p role="status">Working…</p> : null}
                <button
                  type="button"
                  className="primary-button"
                  disabled={
                    busy ||
                    native.pending ||
                    saved.current ||
                    !plan ||
                    !loaded ||
                    !reviewed ||
                    !matches
                  }
                  onClick={() => void apply()}
                >
                  Save reviewed native diagram
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  Discard native diagram preview
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
