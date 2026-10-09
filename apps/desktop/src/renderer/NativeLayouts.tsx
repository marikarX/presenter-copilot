import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { usePowerPointAppearance } from "./NativeAppearance";
import { layoutComparisonPage } from "./layout-comparison";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
} from "./edit-plan-preview";

type Layout = {
  layout_id: string;
  name: string;
  master_name: string;
  placeholder_count: number;
  used_by_slides: number[];
  creation_supported: boolean;
  creation_placeholders: {
    placeholder_id: string;
    name: string;
    type: string;
  }[];
};
type RemapCandidate = {
  object_id: string;
  name: string;
  type: string;
  text: string;
};

export function NativeLayouts({
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
  onRestore: (applied: boolean, created: boolean) => Promise<void>;
}) {
  const [creating, setCreating] = useState(false);
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");
  const [remapCandidates, setRemapCandidates] = useState<RemapCandidate[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [previewDraft, setPreviewDraft] = useState("");
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Layout[]>([]);
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [plan, setPlan] = useState<EditPlanIdentity | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [baseline, setBaseline] = useState<string | null>(null);
  const [comparisonPage, setComparisonPage] = useState(0);
  const [comparisons, setComparisons] = useState<
    { layout: Layout; image?: string; error?: string }[]
  >([]);
  const [loaded, setLoaded] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const owned = useRef<EditPlanIdentity | null>(null);
  const touched = useRef(false);
  const saved = useRef(false);
  const selected = items.find((item) => item.layout_id === choice);
  const draft = JSON.stringify({ choice, texts, notes, creating, mapping });
  const matchesPreview = draft === previewDraft;
  const native = usePowerPointAppearance(
    open && plan && matchesPreview
      ? {
          projectId,
          documentId,
          revisionId,
          sourceSha256: plan.sha256,
          planId: plan.plan_id,
        }
      : null,
    slideNumber + (creating ? 1 : 0),
  );
  const displayedImage = native.image ?? image;
  useEffect(() => {
    setLoaded(false);
    setReviewed(false);
  }, [displayedImage]);
  useEffect(() => {
    if (native.pending) setReviewed(false);
  }, [native.pending]);
  const scope = { project_id: projectId, document_id: documentId };
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
      if (baseline) URL.revokeObjectURL(baseline);
    },
    [baseline],
  );
  useEffect(
    () => () => {
      for (const item of comparisons)
        if (item.image) URL.revokeObjectURL(item.image);
    },
    [comparisons],
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
      if (touched.current || saved.current)
        await onRestore(saved.current, creating);
      touched.current = false;
      setPlan(null);
      setImage(null);
      setBaseline(null);
      setComparisons([]);
      setOpen(false);
    } catch (e) {
      setError(
        isCoreError(e)
          ? e.message
          : e instanceof Error
            ? e.message
            : "The presentation could not be restored.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function show(create = false) {
    setCreating(create);
    setTexts({});
    setNotes("");
    setMapping({});
    setRemapCandidates([]);
    setOpen(true);
    setBusy(true);
    setError("");
    setReviewed(false);
    setPlan(null);
    setImage(null);
    setBaseline(null);
    setComparisons([]);
    setComparisonPage(0);
    saved.current = false;
    try {
      const value = unwrapInvokeResult<{
        revision_id: string;
        items: Layout[];
        remap_candidates?: RemapCandidate[];
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_native_layouts",
          {
            ...scope,
            revision_id: revisionId,
            ...(!create ? { slide_id: slideId } : {}),
          },
        ),
      );
      if (value.revision_id !== revisionId || !Array.isArray(value.items))
        throw new Error("The native layouts could not be verified.");
      setItems(value.items);
      setRemapCandidates(value.remap_candidates ?? []);
      setChoice(
        value.items.find((v) =>
          create
            ? v.creation_supported && v.creation_placeholders.length > 0
            : !v.used_by_slides.includes(slideNumber),
        )?.layout_id || "",
      );
      if (!create) {
        const current = layoutComparisonPage(
          value.items,
          slideNumber,
          0,
        ).current;
        const baselinePlan = await prepareLayout(current.layout_id);
        owned.current = baselinePlan;
        if (
          baselinePlan.changed ||
          baselinePlan.baseline_revision_id !== revisionId
        )
          throw new Error(
            "The current layout baseline changed. Reload the presentation.",
          );
        touched.current = true;
        const slides = await openEditPlanPreview(scope, baselinePlan);
        if (slides[slideNumber - 1]?.slide_id !== slideId)
          throw new Error("The baseline slide changed.");
        const bytes = new Uint8Array(await renderEditPlanSlide(slideNumber));
        setBaseline(
          URL.createObjectURL(new Blob([bytes.buffer], { type: "image/png" })),
        );
        await discard();
      }
    } catch (e) {
      setError(
        isCoreError(e)
          ? e.message
          : e instanceof Error
            ? e.message
            : "Native layouts could not be loaded.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function prepareLayout(layoutId: string) {
    return unwrapInvokeResult<
      EditPlanIdentity & { baseline_revision_id: string; changed: boolean }
    >(
      await window.presenterCopilot.core.request(
        "presentation.workspace.prepare_edit_plan",
        {
          ...scope,
          expected_revision_id: revisionId,
          summary: "Compare native layout on the current slide",
          operations: [
            {
              type: "apply_slide_layout",
              params: { slide_id: slideId, layout_id: layoutId },
            },
          ],
        },
      ),
    );
  }
  async function compare(page: number) {
    if (busy || creating || !baseline || saved.current) return;
    setBusy(true);
    setError("");
    setReviewed(false);
    setLoaded(false);
    setPlan(null);
    setImage(null);
    const results: { layout: Layout; image?: string; error?: string }[] = [];
    try {
      const choices = layoutComparisonPage(items, slideNumber, page);
      await discard();
      for (const layout of choices.candidates) {
        try {
          const proposed = await prepareLayout(layout.layout_id);
          owned.current = proposed;
          if (!proposed.changed || proposed.baseline_revision_id !== revisionId)
            throw new Error("The proposed layout revision changed.");
          touched.current = true;
          const slides = await openEditPlanPreview(scope, proposed);
          if (slides[slideNumber - 1]?.slide_id !== slideId)
            throw new Error("The proposed slide changed.");
          const bytes = new Uint8Array(await renderEditPlanSlide(slideNumber));
          results.push({
            layout,
            image: URL.createObjectURL(
              new Blob([bytes.buffer], { type: "image/png" }),
            ),
          });
        } catch (e) {
          results.push({
            layout,
            error: isCoreError(e)
              ? e.message
              : e instanceof Error
                ? e.message
                : "This layout could not be compared.",
          });
        }
        await discard();
      }
      setComparisonPage(page);
      setComparisons(results);
    } catch (e) {
      for (const item of results)
        if (item.image) URL.revokeObjectURL(item.image);
      setError(
        isCoreError(e)
          ? e.message
          : e instanceof Error
            ? e.message
            : "The native layouts could not be compared.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    if (
      !choice ||
      busy ||
      saved.current ||
      (creating && !selected?.creation_supported)
    )
      return;
    setBusy(true);
    setError("");
    setReviewed(false);
    setLoaded(false);
    setPlan(null);
    setImage(null);
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
            summary: creating
              ? "Create reviewed native layout slide"
              : "Apply reviewed native layout",
            operations: [
              {
                type: creating ? "create_slide" : "apply_slide_layout",
                params: {
                  slide_id: slideId,
                  layout_id: choice,
                  ...(creating
                    ? {
                        notes,
                        placeholder_text: (
                          selected?.creation_placeholders || []
                        ).map((slot) => ({
                          placeholder_id: slot.placeholder_id,
                          text: texts[slot.placeholder_id] || "",
                        })),
                      }
                    : Object.values(mapping).some(Boolean)
                      ? {
                          placeholder_mapping: Object.entries(mapping)
                            .filter(([, slot]) => slot)
                            .map(([object_id, placeholder_id]) => ({
                              object_id,
                              placeholder_id,
                            })),
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
        throw new Error("The layout preview revision changed.");
      if (!value.changed) {
        await discard();
        setError("This slide already uses the selected layout.");
        return;
      }
      touched.current = true;
      const slides = await openEditPlanPreview(scope, value);
      if (slides[slideNumber - 1]?.slide_id !== slideId)
        throw new Error("The selected slide changed.");
      if (
        creating &&
        (!slides[slideNumber] || slides[slideNumber].slide_id === slideId)
      )
        throw new Error("The new slide could not be verified.");
      const bytes = new Uint8Array(
        await renderEditPlanSlide(slideNumber + (creating ? 1 : 0)),
      );
      setImage(
        URL.createObjectURL(new Blob([bytes.buffer], { type: "image/png" })),
      );
      setPlan(value);
      setPreviewDraft(draft);
    } catch (e) {
      setError(
        isCoreError(e)
          ? e.message
          : e instanceof Error
            ? e.message
            : "The native layout could not be previewed.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function apply() {
    if (
      !plan ||
      !image ||
      !loaded ||
      !reviewed ||
      !matchesPreview ||
      native.pending ||
      busy ||
      saved.current
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
      setError(
        isCoreError(e)
          ? e.message
          : e instanceof Error
            ? e.message
            : "The reviewed layout could not be saved.",
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
        disabled={disabled}
        onClick={() => void show()}
      >
        Browse native layouts
      </button>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled}
        onClick={() => void show(true)}
      >
        Insert from native layout
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-native-layout-title"
              onCancel={(e) => {
                e.preventDefault();
                if (!busy) void finish();
              }}
            >
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void preview();
                }}
              >
                <h2 id="pw-native-layout-title">
                  {creating
                    ? `Insert native slide after slide ${slideNumber}`
                    : `Native layouts for slide ${slideNumber}`}
                </h2>
                <p>
                  {creating
                    ? "Choose this deck’s native layout and fill its text placeholders. Each line becomes a paragraph. Theme styling and backgrounds are inherited. Review the new slide before saving."
                    : "Choose a layout from this deck’s themes, including unused layouts. Existing content stays on the slide; placeholders, fonts and backgrounds may look different. Review the native preview and verify the exported deck in PowerPoint."}
                </p>
                {!creating && baseline ? (
                  <section aria-label="Native layout comparison">
                    <h3>Compare layouts on this slide</h3>
                    <figure className="pw-layout-baseline">
                      <img
                        src={baseline}
                        alt="Current native layout baseline"
                      />
                      <figcaption>
                        Current revision · slide {slideNumber}
                      </figcaption>
                    </figure>
                    <p>
                      Render four alternatives at a time with your current
                      content. Select a thumbnail, then preview and approve that
                      exact layout before saving. Thumbnails compare the layout
                      alone; use the fresh preview to review placeholder
                      assignments.
                    </p>
                    <div className="pw-create-actions">
                      <button
                        type="button"
                        disabled={busy || saved.current || items.length < 2}
                        onClick={() => void compare(comparisonPage)}
                      >
                        Compare layout thumbnails
                      </button>
                      <button
                        type="button"
                        disabled={
                          busy ||
                          saved.current ||
                          !comparisons.length ||
                          comparisonPage === 0
                        }
                        onClick={() => void compare(comparisonPage - 1)}
                      >
                        Previous layout comparisons
                      </button>
                      <button
                        type="button"
                        disabled={
                          busy ||
                          saved.current ||
                          !comparisons.length ||
                          comparisonPage + 1 >=
                            Math.ceil((items.length - 1) / 4)
                        }
                        onClick={() => void compare(comparisonPage + 1)}
                      >
                        Next layout comparisons
                      </button>
                    </div>
                    {comparisons.length ? (
                      <>
                        <p role="status">
                          Layout comparison page {comparisonPage + 1} of{" "}
                          {Math.ceil((items.length - 1) / 4)} ·{" "}
                          {items.length - 1} alternatives
                        </p>
                        <div className="pw-layout-thumbnails">
                          {comparisons.map((item) => (
                            <article key={item.layout.layout_id}>
                              <h4>
                                {item.layout.master_name} · {item.layout.name}
                              </h4>
                              {item.image ? (
                                <button
                                  type="button"
                                  className="pw-layout-thumbnail"
                                  disabled={busy || saved.current}
                                  aria-label={`Select compared layout ${item.layout.name}`}
                                  onClick={() => {
                                    setChoice(item.layout.layout_id);
                                    setMapping({});
                                    setReviewed(false);
                                  }}
                                >
                                  <img
                                    src={item.image}
                                    alt={`Compared native layout ${item.layout.name}`}
                                  />
                                  <span>
                                    {choice === item.layout.layout_id
                                      ? "Selected · preview to review"
                                      : "Select this layout"}
                                  </span>
                                </button>
                              ) : (
                                <p role="alert">{item.error}</p>
                              )}
                            </article>
                          ))}
                        </div>
                      </>
                    ) : null}
                  </section>
                ) : null}
                {error ? <p role="alert">{error}</p> : null}
                <label>
                  Native layout
                  <select
                    aria-label="Native layout"
                    value={choice}
                    disabled={busy || saved.current}
                    onChange={(e) => {
                      setChoice(e.target.value);
                      setMapping({});
                      setReviewed(false);
                      setTexts({});
                    }}
                  >
                    <option value="">Choose a native layout</option>
                    {items.map((v) => (
                      <option
                        key={v.layout_id}
                        value={v.layout_id}
                        disabled={creating && !v.creation_supported}
                      >
                        {v.master_name} · {v.name} ·{" "}
                        {v.used_by_slides.length
                          ? `used on ${v.used_by_slides.length} slides`
                          : "unused"}
                      </option>
                    ))}
                  </select>
                </label>
                {!creating && remapCandidates.length ? (
                  <fieldset disabled={busy || saved.current}>
                    <legend>Map existing text placeholders</legend>
                    <p>
                      Assign existing placeholders to this layout’s text slots
                      to use their native position and size. Rich text and
                      object identities stay intact. Unmapped objects keep their
                      existing shape data; inherited positioning and formatting
                      may change. Review wrapping before saving.
                    </p>
                    {remapCandidates.map((target) => (
                      <label key={target.object_id}>
                        {target.name} · {target.type}
                        <select
                          aria-label={`Remap placeholder ${target.name}`}
                          value={mapping[target.object_id] ?? ""}
                          onChange={(event) => {
                            setMapping((previous) => ({
                              ...previous,
                              [target.object_id]: event.target.value,
                            }));
                            setReviewed(false);
                          }}
                        >
                          <option value="">Keep existing placeholder</option>
                          {selected?.creation_supported
                            ? selected.creation_placeholders.map((slot) => (
                                <option
                                  key={slot.placeholder_id}
                                  value={slot.placeholder_id}
                                >
                                  {slot.name} · {slot.type}
                                </option>
                              ))
                            : null}
                        </select>
                        <span className="muted">{target.text}</span>
                      </label>
                    ))}
                  </fieldset>
                ) : null}
                {items.find((v) => v.layout_id === choice) ? (
                  <p>
                    {
                      items.find((v) => v.layout_id === choice)
                        ?.placeholder_count
                    }{" "}
                    {creating
                      ? "layout placeholders. Supported text slots below become editable native objects."
                      : "layout placeholders. Applying does not add or remove slide objects."}
                  </p>
                ) : null}
                {creating ? (
                  <>
                    {(selected?.creation_placeholders || []).map((slot) => (
                      <label key={slot.placeholder_id}>
                        {slot.name} ({slot.type})
                        <textarea
                          aria-label={`Native placeholder: ${slot.name}`}
                          maxLength={2000}
                          rows={
                            slot.type.includes("Title") || slot.type === "title"
                              ? 2
                              : 3
                          }
                          value={texts[slot.placeholder_id] || ""}
                          disabled={busy || saved.current}
                          onChange={(event) => {
                            setTexts({
                              ...texts,
                              [slot.placeholder_id]: event.target.value,
                            });
                            setReviewed(false);
                          }}
                        />
                      </label>
                    ))}
                    <label>
                      Speaker notes for new slide
                      <textarea
                        aria-label="Native slide speaker notes"
                        maxLength={4000}
                        rows={3}
                        value={notes}
                        disabled={busy || saved.current}
                        onChange={(event) => {
                          setNotes(event.target.value);
                          setReviewed(false);
                        }}
                      />
                    </label>
                  </>
                ) : null}
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy ||
                    !choice ||
                    saved.current ||
                    (creating && !selected?.creation_supported)
                  }
                  onClick={() => void preview()}
                >
                  {busy
                    ? "Working…"
                    : creating
                      ? "Preview native slide"
                      : "Preview native layout"}
                </button>
                {image ? (
                  <section aria-label="Native layout preview">
                    {native.controls}
                    <figure>
                      <img
                        key={displayedImage}
                        src={displayedImage ?? undefined}
                        alt={
                          creating
                            ? "Proposed native slide"
                            : "Proposed native layout"
                        }
                        onLoad={() => setLoaded(true)}
                        onError={() => {
                          setLoaded(false);
                          if (native.image) native.rejectImage();
                          setError("The preview image could not be loaded.");
                        }}
                      />
                    </figure>
                    <label className="pw-edit-review-ack">
                      <input
                        type="checkbox"
                        disabled={
                          busy ||
                          native.pending ||
                          !loaded ||
                          !matchesPreview ||
                          saved.current
                        }
                        checked={reviewed && matchesPreview}
                        onChange={(e) => setReviewed(e.target.checked)}
                      />
                      {creating
                        ? "I reviewed the new native slide and its notes."
                        : "I reviewed this layout on the current slide."}
                    </label>
                    <p>
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint."
                        : "The experimental Browser appearance may differ from PowerPoint."}
                    </p>
                    {!matchesPreview ? (
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
                    !matchesPreview
                  }
                  onClick={() => void apply()}
                >
                  {creating
                    ? "Save reviewed native slide"
                    : "Save reviewed native layout"}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {saved.current
                    ? "Close saved native layout"
                    : creating
                      ? "Discard native slide preview"
                      : "Discard native layout preview"}
                </button>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
