import { usePowerPointAppearance } from "./NativeAppearance";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  LAYOUT_ACTIONS,
  layoutOperations,
  type LayoutObject,
  type LayoutAction,
  type ObjectMoveRequest,
} from "./object-layout";
import {
  unwrapInvokeResult,
  isCoreError,
  type PresentationPreviewRenderResult,
} from "../shared/protocol";

export type ObjectPasteRequest = {
  names: string[];
  source_document_id: string;
  source_revision_id: string;
  source_slide_id: string;
  object_ids: string[];
  slide_id: string;
};

export type ObjectActionRequest = {
  action: "duplicate" | "delete" | "group" | "ungroup";
  names: string[];
  object_ids: string[];
  operations: { type: string; params: Record<string, unknown> }[];
};

type Target = {
  slide_id: string;
  object_id: string;
  label: string;
  text: string;
  replaceEditable: boolean;
};
type Notes = {
  slide_id: string;
  current_text: string | null;
  editable: boolean;
};
type Plan = {
  plan_id: string;
  sha256: string;
  byte_size: number;
  changed: boolean;
};

/** A modal owns the shared preview renderer until the current deck is restored. */
export function SlideEditReview({
  projectId,
  documentId,
  revisionId,
  slideNumber,
  targets,
  notes,
  disabled,
  onRestore,
  layoutObjects,
  slideId,
  initialSelectedIds,
  moveRequest,
  onMoveHandled,
  pasteRequest,
  onPasteHandled,
  actionRequest,
  onActionHandled,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  slideNumber: number;
  targets: Target[];
  notes: Notes | null;
  disabled: boolean;
  onRestore: (
    applied: boolean,
    pastedIds?: string[],
    pastedRevisionId?: string,
    action?: "paste" | "duplicate" | "delete" | "group" | "ungroup",
  ) => Promise<void>;
  layoutObjects?: LayoutObject[];
  slideId?: string;
  initialSelectedIds?: string[];
  moveRequest?: ObjectMoveRequest | null;
  onMoveHandled?: () => void;
  pasteRequest?: ObjectPasteRequest | null;
  onPasteHandled?: () => void;
  actionRequest?: ObjectActionRequest | null;
  onActionHandled?: () => void;
}) {
  const layoutMode = layoutObjects !== undefined;
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [layoutAction, setLayoutAction] = useState<LayoutAction>("left");
  const [presetMove, setPresetMove] = useState<ObjectMoveRequest | null>(null);
  const [presetPaste, setPresetPaste] = useState<ObjectPasteRequest | null>(
    null,
  );
  const [presetAction, setPresetAction] = useState<ObjectActionRequest | null>(
    null,
  );
  const appliedAction = useRef<
    "paste" | "duplicate" | "delete" | "group" | "ungroup" | undefined
  >(undefined);
  const namedSelection = presetAction ?? presetPaste;
  const actionVerb = presetAction
    ? (
        {
          duplicate: "Duplicate",
          delete: "Remove",
          group: "Group",
          ungroup: "Ungroup",
        } as const
      )[presetAction.action]
    : "";
  const actionPast = presetAction
    ? (
        {
          duplicate: "Duplicated",
          delete: "Removed",
          group: "Grouped",
          ungroup: "Ungrouped",
        } as const
      )[presetAction.action]
    : "";
  const pastedIds = useRef<string[] | undefined>(undefined);
  const pastedRevisionId = useRef<string | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [notesDraft, setNotesDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const native = usePowerPointAppearance(
    plan
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
    setImageLoaded(false);
    setReviewed(false);
  }, [displayedImage]);
  useEffect(() => {
    if (native.pending) setReviewed(false);
  }, [native.pending]);
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const ownedPlan = useRef<Plan | null>(null);
  const touchedRenderer = useRef(false);
  const editable = [
    ...new Map(
      targets
        .filter((target) => target.replaceEditable)
        .map((target) => [target.object_id, target]),
    ).values(),
  ];
  const scope = { project_id: projectId, document_id: documentId };

  useEffect(() => {
    if (open) dialog.current?.showModal();
  }, [open]);
  useEffect(() => {
    if (!moveRequest || disabled) return;
    setPresetAction(null);
    setPresetPaste(null);
    setPresetMove(moveRequest);
    setPlan(null);
    setImage(null);
    setReviewed(false);
    setImageLoaded(false);
    setError(null);
    setOpen(true);
    onMoveHandled?.();
  }, [moveRequest, disabled, onMoveHandled]);
  useEffect(() => {
    if (!pasteRequest || disabled) return;
    setPresetAction(null);
    setPresetPaste(pasteRequest);
    setPresetMove(null);
    setPlan(null);
    setImage(null);
    setReviewed(false);
    setImageLoaded(false);
    setError(null);
    setOpen(true);
    onPasteHandled?.();
  }, [pasteRequest, disabled, onPasteHandled]);
  useEffect(() => {
    if (!actionRequest || disabled) return;
    setPresetAction(actionRequest);
    setPresetPaste(null);
    setPresetMove(null);
    pastedIds.current = undefined;
    pastedRevisionId.current = undefined;
    appliedAction.current = undefined;
    setPlan(null);
    setImage(null);
    setReviewed(false);
    setImageLoaded(false);
    setError(null);
    setOpen(true);
    onActionHandled?.();
  }, [actionRequest, disabled, onActionHandled]);
  useEffect(() => {
    if (image) {
      heading.current?.focus({ preventScroll: true });
      dialog.current?.scrollTo({ top: 0 });
    }
  }, [image]);
  useEffect(
    () => () => {
      const pending = ownedPlan.current;
      if (pending)
        void window.presenterCopilot.core
          .request("presentation.workspace.reject_edit_plan", {
            project_id: projectId,
            document_id: documentId,
            plan_id: pending.plan_id,
          })
          .catch(() => undefined);
    },
    [projectId, documentId],
  );
  useEffect(
    () => () => {
      if (image) URL.revokeObjectURL(image);
    },
    [image],
  );

  function begin() {
    setPresetAction(null);
    appliedAction.current = undefined;
    setPresetPaste(null);
    pastedIds.current = undefined;
    pastedRevisionId.current = undefined;
    setPresetMove(null);
    setSelectedIds(
      (initialSelectedIds ?? [])
        .filter((id) =>
          layoutObjects?.some(
            (o) => o.object_id === id && o.geometry_editable && o.geometry,
          ),
        )
        .slice(0, 20),
    );
    setLayoutAction("left");
    setDrafts(
      Object.fromEntries(
        editable.map((target) => [target.object_id, target.text]),
      ),
    );
    setNotesDraft(notes?.current_text ?? "");
    setPlan(null);
    setImage(null);
    setReviewed(false);
    setImageLoaded(false);
    setError(null);
    setOpen(true);
  }

  async function finish(applied = false) {
    setBusy(true);
    try {
      if (ownedPlan.current && !applied) {
        try {
          unwrapInvokeResult(
            await window.presenterCopilot.core.request(
              "presentation.workspace.reject_edit_plan",
              { ...scope, plan_id: ownedPlan.current.plan_id },
            ),
          );
        } catch (caught) {
          if (
            !isCoreError(caught) ||
            caught.code !== "PRESENTATION_EDIT_PLAN_NOT_FOUND"
          )
            throw caught;
        }
      }
      ownedPlan.current = null;
      if (touchedRenderer.current) {
        touchedRenderer.current = false;
        await onRestore(
          applied,
          pastedIds.current,
          pastedRevisionId.current,
          appliedAction.current,
        );
      }
      setPlan(null);
      setImage(null);
      setOpen(false);
    } catch (caught) {
      setError(
        caught instanceof Error || isCoreError(caught)
          ? caught.message
          : "The review could not be closed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function preview() {
    setBusy(true);
    setError(null);
    let sessionId: string | null = null;
    try {
      let operations: { type: string; params: Record<string, unknown> }[] =
        editable
          .filter((target) => drafts[target.object_id] !== target.text)
          .map((target) => ({
            type: "replace_text_shape",
            params: {
              operation_type: "replace_text_shape",
              slide_id: target.slide_id,
              object_id: target.object_id,
              expected_text: target.text,
              replacement_text: drafts[target.object_id] ?? target.text,
            } as Record<string, string>,
          }));
      if (
        notes?.editable &&
        notes.current_text !== null &&
        notesDraft !== notes.current_text
      )
        operations.push({
          type: "replace_speaker_notes",
          params: {
            slide_id: notes.slide_id,
            expected_text: notes.current_text,
            replacement_text: notesDraft,
          },
        });
      if (layoutMode && !presetPaste && !presetAction) {
        if (!slideId) throw new Error("Refresh the current slide.");
        operations =
          presetMove?.operations ??
          layoutOperations(layoutObjects, selectedIds, slideId, layoutAction);
      }
      if (presetPaste) {
        operations = [
          {
            type: "paste_objects",
            params: {
              source_document_id: presetPaste.source_document_id,
              source_revision_id: presetPaste.source_revision_id,
              source_slide_id: presetPaste.source_slide_id,
              object_ids: presetPaste.object_ids,
              slide_id: presetPaste.slide_id,
            },
          },
        ];
      }
      if (presetAction) operations = presetAction.operations;
      if (!operations.length)
        throw new Error(
          layoutMode
            ? "These objects already have the requested layout."
            : "Change at least one text box or the speaker notes.",
        );
      const proposed = unwrapInvokeResult<Plan>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.prepare_edit_plan",
          {
            ...scope,
            expected_revision_id: revisionId,
            summary: presetAction
              ? `${actionVerb} ${presetAction.names.length} objects on slide ${slideNumber}`
              : presetPaste
                ? `Paste ${presetPaste.names.length} copied objects on slide ${slideNumber}`
                : presetMove
                  ? `${presetMove.resize ? "Move or resize" : "Move"} ${presetMove.operations.length} objects on slide ${slideNumber}`
                  : layoutMode
                    ? `${LAYOUT_ACTIONS.find(([action]) => action === layoutAction)?.[1]} on slide ${slideNumber}`
                    : `Reviewed changes to slide ${slideNumber}`,
            operations,
          },
        ),
      );
      ownedPlan.current = proposed;
      setPlan(proposed);
      const reader = unwrapInvokeResult<{
        session_id: string;
        sha256: string;
        byte_size: number;
        chunk_bytes: number;
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.open_edit_plan_preview",
          {
            ...scope,
            plan_id: proposed.plan_id,
          },
        ),
      );
      sessionId = reader.session_id;
      if (
        reader.sha256 !== proposed.sha256 ||
        reader.byte_size !== proposed.byte_size ||
        !Number.isSafeInteger(reader.byte_size) ||
        reader.byte_size < 1 ||
        reader.byte_size > 50 * 1024 * 1024
      )
        throw new Error("The proposed package could not be verified.");
      const bytes = new Uint8Array(reader.byte_size);
      let offset = 0;
      while (offset < bytes.length) {
        const chunk = unwrapInvokeResult<{
          offset: number;
          bytes_b64: string;
          complete: boolean;
        }>(
          await window.presenterCopilot.core.request(
            "presentation.workspace.read_source",
            {
              ...scope,
              session_id: sessionId,
              offset,
              max_bytes: reader.chunk_bytes,
            },
          ),
        );
        const decoded = Uint8Array.from(atob(chunk.bytes_b64), (character) =>
          character.charCodeAt(0),
        );
        if (
          chunk.offset !== offset ||
          !decoded.length ||
          offset + decoded.length > bytes.length ||
          chunk.complete !== (offset + decoded.length === bytes.length)
        )
          throw new Error("The proposed preview stream changed.");
        bytes.set(decoded, offset);
        offset += decoded.length;
      }
      sessionId = null;
      touchedRenderer.current = true;
      unwrapInvokeResult(
        await window.presenterCopilot.presentationPreview.open(bytes.buffer),
      );
      const rendered = unwrapInvokeResult<PresentationPreviewRenderResult>(
        await window.presenterCopilot.presentationPreview.render(slideNumber),
      );
      if (
        rendered.slide_number !== slideNumber ||
        !(rendered.image instanceof Uint8Array) ||
        rendered.image.byteLength < 8 ||
        rendered.image.byteLength > 32 * 1024 * 1024 ||
        rendered.width < 1 ||
        rendered.height < 1 ||
        rendered.width > 4096 ||
        rendered.height > 4096 ||
        rendered.image[0] !== 0x89 ||
        rendered.image[1] !== 0x50 ||
        rendered.image[2] !== 0x4e ||
        rendered.image[3] !== 0x47
      )
        throw new Error("The proposed slide could not be rendered.");
      const copy = new Uint8Array(rendered.image);
      setImage(
        URL.createObjectURL(new Blob([copy.buffer], { type: "image/png" })),
      );
    } catch (caught) {
      setError(
        caught instanceof Error || isCoreError(caught)
          ? caught.message
          : "The proposed edits could not be previewed.",
      );
    } finally {
      if (sessionId)
        await window.presenterCopilot.core
          .request("presentation.workspace.close_source", {
            ...scope,
            session_id: sessionId,
          })
          .catch(() => undefined);
      setBusy(false);
    }
  }

  async function apply() {
    if (!plan || !image || !imageLoaded || !reviewed || native.pending) return;
    setBusy(true);
    setError(null);
    try {
      const saved = unwrapInvokeResult<{
        revision_id: string;
        operations?: {
          created_object_ids?: string[];
          created_object_id?: string;
          selected_object_ids?: string[];
        }[];
      }>(
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
      pastedIds.current = presetPaste
        ? saved.operations?.[0]?.created_object_ids
        : presetAction?.action === "duplicate"
          ? saved.operations?.flatMap((operation) =>
              operation.created_object_id ? [operation.created_object_id] : [],
            )
          : presetAction?.action === "group" ||
              presetAction?.action === "ungroup"
            ? saved.operations?.flatMap(
                (operation) => operation.selected_object_ids ?? [],
              )
            : presetMove
              ? presetMove.operations.map(
                  (operation) => operation.params.object_id,
                )
              : layoutMode
                ? selectedIds
                : undefined;
      pastedRevisionId.current = saved.revision_id;
      appliedAction.current =
        presetAction?.action ?? (presetPaste ? "paste" : undefined);
      ownedPlan.current = null;
      await finish(true);
    } catch (caught) {
      setError(
        caught instanceof Error || isCoreError(caught)
          ? caught.message
          : "The reviewed edits could not be applied.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="secondary-button"
        disabled={
          disabled ||
          (layoutMode
            ? layoutObjects.filter((o) => o.geometry_editable && o.geometry)
                .length < 2
            : !editable.length && !notes?.editable)
        }
        onClick={begin}
      >
        {layoutMode ? "Arrange objects together" : "Edit slide together"}
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-edit-review-title"
              onCancel={(event) => {
                event.preventDefault();
                if (!busy) void finish();
              }}
            >
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void (plan ? apply() : preview());
                }}
              >
                <h2 ref={heading} tabIndex={-1} id="pw-edit-review-title">
                  {presetAction
                    ? (
                        {
                          delete: "Review selection deletion",
                          duplicate: "Review selection duplication",
                          group: "Review native grouping",
                          ungroup: "Review native ungrouping",
                        } as const
                      )[presetAction.action]
                    : presetPaste
                      ? "Review pasted objects"
                      : presetMove
                        ? presetMove.resize
                          ? "Review object layout"
                          : "Review dragged objects"
                        : layoutMode
                          ? "Review object layout"
                          : "Review slide edits"}
                </h2>
                <p className="muted">
                  {presetAction
                    ? `${actionVerb} ${presetAction.names.length} selected objects together. Review the resulting native slide, then save one revision or cancel. Undo restores the previous revision.${presetAction.action === "group" ? " The group uses the frontmost selected layer; child order stays the same." : presetAction.action === "ungroup" ? " Children keep their native identities and current slide positions." : ""}`
                    : presetPaste
                      ? `Paste ${presetPaste.names.length} objects from the copied revision. Their sizes and relative spacing are preserved; theme colors and inherited text styles use this slide’s theme. Review and save one revision or cancel.`
                      : presetMove
                        ? presetMove.resize
                          ? "Review the proposed position and size in a native slide preview. Table columns and rows scale together; chart data and styling stay intact. Save one revision or cancel."
                          : "Review the dragged positions in a native slide preview, then save all moves as one revision. Sizes and layers stay the same."
                        : layoutMode
                          ? "Select 2–20 editable objects. Align within their combined bounds or distribute with equal gaps between the outer objects. Sizes and layers stay the same. Review and save all moves as one revision."
                          : "Edit text and notes together. Review the proposed slide, then save all changes as one revision."}
                </p>
                {namedSelection ? (
                  <ul>
                    {namedSelection.names.map((name, i) => (
                      <li key={namedSelection.object_ids[i]}>{name}</li>
                    ))}
                  </ul>
                ) : null}
                {presetMove ? (
                  <ul>
                    {presetMove.operations.map((operation) => {
                      const before = operation.params.expected_geometry,
                        after = operation.params.replacement_geometry;
                      return (
                        <li key={operation.params.object_id}>
                          {layoutObjects?.find(
                            (o) => o.object_id === operation.params.object_id,
                          )?.name ?? "Object"}
                          : ({(before.x_emu / 914400).toFixed(3)},{" "}
                          {(before.y_emu / 914400).toFixed(3)}) → (
                          {(after.x_emu / 914400).toFixed(3)},{" "}
                          {(after.y_emu / 914400).toFixed(3)}) inches
                          {presetMove.resize ? (
                            <>
                              {"; size "}
                              {(before.width_emu / 914400).toFixed(3)} ×{" "}
                              {(before.height_emu / 914400).toFixed(3)} →{" "}
                              {(after.width_emu / 914400).toFixed(3)} ×{" "}
                              {(after.height_emu / 914400).toFixed(3)} inches
                            </>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
                {layoutMode &&
                !plan &&
                !presetMove &&
                !presetPaste &&
                !presetAction ? (
                  <fieldset>
                    <legend>Objects to arrange</legend>
                    {layoutObjects.map((object) => (
                      <label key={object.object_id}>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(object.object_id)}
                          disabled={
                            busy ||
                            !object.geometry_editable ||
                            !object.geometry ||
                            (selectedIds.length >= 20 &&
                              !selectedIds.includes(object.object_id))
                          }
                          onChange={(event) =>
                            setSelectedIds(
                              event.target.checked
                                ? [...selectedIds, object.object_id]
                                : selectedIds.filter(
                                    (id) => id !== object.object_id,
                                  ),
                            )
                          }
                        />
                        {object.name}
                        {!object.geometry_editable || !object.geometry
                          ? " (read-only)"
                          : ""}
                      </label>
                    ))}
                    <label>
                      Layout command
                      <select
                        aria-label="Layout command"
                        value={layoutAction}
                        disabled={busy}
                        onChange={(event) =>
                          setLayoutAction(event.target.value as LayoutAction)
                        }
                      >
                        {LAYOUT_ACTIONS.map(([action, label]) => (
                          <option key={action} value={action}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <p className="muted">
                      {selectedIds.length} selected. Distribution requires at
                      least 3 objects and enough space for nonnegative gaps.
                    </p>
                  </fieldset>
                ) : null}
                {!plan && !layoutMode
                  ? editable.map((target, index) => (
                      <label key={target.object_id}>
                        {target.label}
                        <textarea
                          aria-label={`Slide text ${index + 1}`}
                          rows={3}
                          maxLength={2000}
                          value={drafts[target.object_id] ?? target.text}
                          disabled={busy || !!plan}
                          onChange={(event) =>
                            setDrafts({
                              ...drafts,
                              [target.object_id]: event.target.value,
                            })
                          }
                        />
                      </label>
                    ))
                  : null}
                {!plan &&
                !layoutMode &&
                notes?.editable &&
                notes.current_text !== null ? (
                  <label>
                    Speaker notes
                    <textarea
                      aria-label="Grouped speaker notes"
                      rows={4}
                      maxLength={12000}
                      value={notesDraft}
                      disabled={busy || !!plan}
                      onChange={(event) => setNotesDraft(event.target.value)}
                    />
                  </label>
                ) : null}
                {native.controls}
                {image ? (
                  <figure>
                    <img
                      key={displayedImage}
                      src={displayedImage ?? undefined}
                      alt={
                        layoutMode
                          ? "Proposed slide with arranged objects"
                          : "Proposed slide with all reviewed text changes"
                      }
                      onLoad={() => setImageLoaded(true)}
                      onError={() => {
                        setImageLoaded(false);
                        if (native.image) native.rejectImage();
                        setError(
                          "The proposed slide image could not be displayed.",
                        );
                      }}
                    />
                    <figcaption>Proposed slide · {slideNumber}</figcaption>
                  </figure>
                ) : null}
                {plan ? (
                  <section
                    className="pw-edit-review-changes"
                    aria-label="Proposed content changes"
                  >
                    <h3>Proposed changes</h3>
                    {presetAction ? (
                      <p>
                        {actionPast} {presetAction.names.length} native objects
                        in this proposal. Save all changes as one revision.
                      </p>
                    ) : presetPaste ? (
                      <p>
                        Pasted {presetPaste.names.length} native objects. Undo
                        restores the previous slide.
                      </p>
                    ) : presetMove ? (
                      <p>
                        {presetMove.resize ? (
                          "Changed the reviewed object layout. Undo restores its previous position and size."
                        ) : (
                          <>
                            Moved {presetMove.operations.length} objects
                            together. Undo restores their previous positions.
                          </>
                        )}
                      </p>
                    ) : layoutMode ? (
                      <p>
                        {
                          LAYOUT_ACTIONS.find(
                            ([action]) => action === layoutAction,
                          )?.[1]
                        }
                        :{" "}
                        {layoutObjects
                          .filter((o) => selectedIds.includes(o.object_id))
                          .map((o) => o.name)
                          .join(", ")}
                      </p>
                    ) : null}
                    {editable
                      .filter(
                        (target) => drafts[target.object_id] !== target.text,
                      )
                      .map((target) => (
                        <article key={target.object_id}>
                          <strong>{target.label}</strong>
                          <p>{drafts[target.object_id] || "Empty text"}</p>
                          <details>
                            <summary>Previous text</summary>
                            <p>{target.text}</p>
                          </details>
                        </article>
                      ))}
                    {notes?.editable &&
                    notes.current_text !== null &&
                    notesDraft !== notes.current_text ? (
                      <article>
                        <strong>Speaker notes</strong>
                        <p>{notesDraft || "Empty notes"}</p>
                        <details>
                          <summary>Previous notes</summary>
                          <p>{notes.current_text || "Empty notes"}</p>
                        </details>
                      </article>
                    ) : null}
                  </section>
                ) : null}
                {plan ? (
                  <p className="muted">
                    The current deck is unchanged. This preview expires after 15
                    minutes.
                  </p>
                ) : null}
                {image ? (
                  <label className="pw-edit-review-ack">
                    <input
                      type="checkbox"
                      checked={reviewed}
                      onChange={(event) => setReviewed(event.target.checked)}
                      disabled={busy || !imageLoaded || native.pending}
                    />
                    {layoutMode
                      ? "I reviewed the object positions and slide layout. "
                      : "I reviewed the text, notes, and slide layout. "}
                    {native.image
                      ? "The proposed slide appearance comes from PowerPoint."
                      : "The experimental Browser appearance may differ from PowerPoint."}
                  </label>
                ) : null}
                {error ? <p role="alert">{error}</p> : null}
                <div className="pw-create-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void finish()}
                  >
                    {plan ? "Discard preview" : "Cancel"}
                  </button>
                  {!plan ? (
                    <button type="submit" disabled={busy}>
                      {busy ? "Preparing preview…" : "Preview all changes"}
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={
                        busy ||
                        !image ||
                        !imageLoaded ||
                        !reviewed ||
                        native.pending
                      }
                    >
                      {busy ? "Saving…" : "Save reviewed changes"}
                    </button>
                  )}
                </div>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
