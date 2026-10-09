import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { unwrapInvokeResult, type SourceSummary } from "../shared/protocol";
import { OutlinePlanner } from "./OutlinePlanner";

type SlideLayout = "points" | "columns" | "cards" | "statement";
type OutlineSlide = {
  title: string;
  bullets: string[];
  notes: string;
  layout?: SlideLayout;
  pointsDraft?: string;
  evidence_ids?: string[];
};

function readOutline(outline: string): OutlineSlide[] {
  const slides: OutlineSlide[] = [];
  for (const line of outline
    .split("\n")
    .map((value) => value.trim())
    .filter(Boolean)) {
    if (line.startsWith("# ")) {
      slides.push({ title: line.slice(2).trim(), bullets: [], notes: "" });
    } else {
      const slide = slides.at(-1);
      if (!slide)
        throw new Error("Start each slide with # followed by its title.");
      if (line.startsWith("Notes: "))
        slide.notes += `${slide.notes ? "\n" : ""}${line.slice(7)}`;
      else slide.bullets.push(line.replace(/^[-*] /, ""));
    }
  }
  if (!slides.length || slides.length > 40)
    throw new Error("Use between 1 and 40 slide headings.");
  for (const slide of slides) {
    if (!slide.title || slide.title.length > 120)
      throw new Error("Slide titles need 1–120 characters.");
    if (
      slide.bullets.length > 8 ||
      slide.bullets.some((point) => point.length > 200)
    )
      throw new Error(
        "Use up to 8 points per slide, with at most 200 characters each.",
      );
    if (slide.notes.length > 4000)
      throw new Error("Keep notes below 4,000 characters per slide.");
  }
  return slides;
}

export function CreatePresentation({
  projectId,
  onCreated,
  onClose,
}: {
  projectId: string;
  onCreated: (document: SourceSummary) => Promise<void>;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [title, setTitle] = useState("");
  const [outline, setOutline] = useState("");
  const [review, setReview] = useState<OutlineSlide[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<SourceSummary | null>(null);
  const [mode, setMode] = useState<"outline" | "copilot">("outline");
  const [providerRunId, setProviderRunId] = useState<string | null>(null);
  const [template, setTemplate] = useState("classic");
  const invalidSlide =
    review?.findIndex(
      (slide) =>
        !slide.title.trim() ||
        slide.bullets.length > 8 ||
        slide.bullets.some((point) => point.length > 200),
    ) ?? -1;
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  async function create() {
    if ((!review && !created) || invalidSlide >= 0) return;
    setBusy(true);
    setError(null);
    try {
      const document =
        created ??
        unwrapInvokeResult(
          await window.presenterCopilot.core.request<{
            status: string;
            document: SourceSummary;
          }>("presentation.workspace.create_from_outline", {
            project_id: projectId,
            title: title.trim(),
            slides: review?.map(
              ({ title, bullets, notes, layout, evidence_ids }) => ({
                title,
                bullets,
                notes,
                ...(layout ? { layout } : {}),
                ...(evidence_ids?.length ? { evidence_ids } : {}),
              }),
            ),
            template,
            ...(providerRunId ? { provider_run_id: providerRunId } : {}),
          }),
        ).document;
      setCreated(document);
      await onCreated(document);
      onClose();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The presentation could not be created.",
      );
    } finally {
      setBusy(false);
    }
  }
  return createPortal(
    <dialog
      ref={dialog}
      className="pw-create-dialog"
      aria-labelledby="pw-create-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (review || created) void create();
          else if (mode === "outline") {
            try {
              setError(null);
              setReview(readOutline(outline));
            } catch (caught) {
              setError(
                caught instanceof Error
                  ? caught.message
                  : "Review the outline format.",
              );
            }
          }
        }}
      >
        <p className="eyebrow">NEW PRESENTATION</p>
        <h2 id="pw-create-title">Start with your outline</h2>
        <p>
          Your words become editable slides with speaker notes. Review the
          outline before creating a local deck.
        </p>
        {!review && !created ? (
          <div
            className="pw-panel-switcher"
            role="group"
            aria-label="Presentation creation mode"
          >
            <button
              type="button"
              aria-pressed={mode === "outline"}
              disabled={busy}
              onClick={() => setMode("outline")}
            >
              Write outline
            </button>
            <button
              type="button"
              aria-pressed={mode === "copilot"}
              disabled={busy}
              onClick={() => setMode("copilot")}
            >
              Plan with Copilot
            </button>
          </div>
        ) : null}
        {mode === "outline" || review ? (
          <label>
            Presentation title
            <input
              autoFocus
              value={title}
              maxLength={120}
              required
              disabled={busy || created !== null}
              onChange={(event) => {
                setTitle(event.target.value);
              }}
            />
          </label>
        ) : null}
        {review &&
        providerRunId &&
        review.some((slide) => slide.evidence_ids?.length) ? (
          <p className="muted">
            Editing the whole outline starts a manual draft and clears retained
            planning citations. Edit individual slide fields above to keep them.
          </p>
        ) : null}
        {review ? (
          <section className="pw-outline-review" aria-label="Outline review">
            <h3>{review.length} slides ready to create</h3>
            <label>
              Presentation template
              <select
                aria-label="Presentation template"
                value={template}
                disabled={busy || created !== null}
                onChange={(event) => setTemplate(event.target.value)}
              >
                <option value="classic">Classic · cool light</option>
                <option value="midnight">Midnight · dark blue</option>
                <option value="paper">Paper · warm neutral</option>
              </select>
            </label>
            <p className="muted">
              Choose a layout for each slide. Text, panels, and speaker notes
              stay editable in the workspace and PowerPoint.
            </p>
            <ol>
              {review.map((slide, index) => (
                <li key={index}>
                  <strong>{slide.title}</strong>
                  <label>
                    {`Slide ${index + 1} layout`}
                    <select
                      aria-label={`Slide ${index + 1} layout`}
                      value={slide.layout ?? "points"}
                      disabled={busy || created !== null}
                      onChange={(event) => {
                        const layout = event.target.value as SlideLayout;
                        setReview(
                          review.map((item, position) =>
                            position === index ? { ...item, layout } : item,
                          ),
                        );
                      }}
                    >
                      <option value="points">Points · full width</option>
                      <option value="columns">Two columns</option>
                      <option value="cards">Cards · grouped points</option>
                      <option
                        value="statement"
                        disabled={slide.bullets.length > 1}
                      >
                        Statement · one key message
                      </option>
                    </select>
                  </label>
                  <ul>
                    {slide.bullets.map((point, pointIndex) => (
                      <li key={pointIndex}>{point}</li>
                    ))}
                  </ul>
                  {slide.notes ? <p>Notes: {slide.notes}</p> : null}
                  {slide.evidence_ids?.length ? (
                    <p className="muted">
                      {slide.evidence_ids.length} planning reference(s) retained
                      for evidence review after creation. They do not approve or
                      support these points automatically.
                    </p>
                  ) : null}
                  <details>
                    <summary>{`Edit slide ${index + 1} content`}</summary>
                    <label>
                      Slide title
                      <input
                        aria-label={`Reviewed slide ${index + 1} title`}
                        value={slide.title}
                        maxLength={120}
                        required
                        disabled={busy || created !== null}
                        onChange={(event) =>
                          setReview(
                            review.map((item, position) =>
                              position === index
                                ? { ...item, title: event.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                    </label>
                    <label>
                      Points · one per line
                      <textarea
                        aria-label={`Reviewed slide ${index + 1} points`}
                        rows={4}
                        value={slide.pointsDraft ?? slide.bullets.join("\n")}
                        maxLength={1700}
                        disabled={busy || created !== null}
                        onChange={(event) => {
                          const pointsDraft = event.target.value;
                          const bullets = pointsDraft
                            .split("\n")
                            .map((point) => point.trim())
                            .filter(Boolean);
                          setReview(
                            review.map((item, position) =>
                              position === index
                                ? {
                                    ...item,
                                    pointsDraft,
                                    bullets,
                                    layout:
                                      item.layout === "statement" &&
                                      bullets.length > 1
                                        ? "points"
                                        : item.layout,
                                  }
                                : item,
                            ),
                          );
                        }}
                      />
                    </label>
                    <label>
                      Speaker notes
                      <textarea
                        aria-label={`Reviewed slide ${index + 1} notes`}
                        rows={3}
                        value={slide.notes}
                        maxLength={4000}
                        disabled={busy || created !== null}
                        onChange={(event) =>
                          setReview(
                            review.map((item, position) =>
                              position === index
                                ? { ...item, notes: event.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                    </label>
                  </details>
                  <div className="pw-draft-slide-actions">
                    <button
                      type="button"
                      aria-label={`Move slide ${index + 1} earlier`}
                      disabled={busy || created !== null || index === 0}
                      onClick={() => {
                        const next = [...review];
                        [next[index - 1], next[index]] = [
                          next[index]!,
                          next[index - 1]!,
                        ];
                        setReview(next);
                      }}
                    >
                      Move up
                    </button>
                    <button
                      type="button"
                      aria-label={`Move slide ${index + 1} later`}
                      disabled={
                        busy || created !== null || index === review.length - 1
                      }
                      onClick={() => {
                        const next = [...review];
                        [next[index], next[index + 1]] = [
                          next[index + 1]!,
                          next[index]!,
                        ];
                        setReview(next);
                      }}
                    >
                      Move down
                    </button>
                    <button
                      type="button"
                      aria-label={`Duplicate draft slide ${index + 1}`}
                      disabled={busy || created !== null || review.length >= 40}
                      onClick={() =>
                        setReview([
                          ...review.slice(0, index + 1),
                          { ...slide, bullets: [...slide.bullets] },
                          ...review.slice(index + 1),
                        ])
                      }
                    >
                      Duplicate
                    </button>
                    <button
                      type="button"
                      aria-label={`Remove draft slide ${index + 1}`}
                      disabled={busy || created !== null || review.length === 1}
                      onClick={() =>
                        setReview(
                          review.filter((_, position) => position !== index),
                        )
                      }
                    >
                      Remove
                    </button>
                  </div>
                </li>
              ))}
            </ol>
            {invalidSlide >= 0 ? (
              <p role="alert">{`Review slide ${invalidSlide + 1}: use a title and up to 8 points of at most 200 characters each.`}</p>
            ) : null}
            <button
              type="button"
              disabled={busy || created !== null || review.length >= 40}
              onClick={() =>
                setReview([
                  ...review,
                  {
                    title: "New slide",
                    bullets: [],
                    notes: "",
                    layout: "points",
                  },
                ])
              }
            >
              Add draft slide
            </button>
          </section>
        ) : mode === "copilot" ? (
          <OutlinePlanner
            projectId={projectId}
            onBusyChange={setBusy}
            onUse={(plannedTitle, plannedOutline, runId, evidenceIds) => {
              try {
                setError(null);
                const slides = readOutline(plannedOutline);
                if (slides.length !== evidenceIds.length)
                  throw new Error(
                    "The planned slide references do not match this outline.",
                  );
                setTitle(plannedTitle);
                setOutline(plannedOutline);
                setProviderRunId(runId);
                setReview(
                  slides.map((slide, index) => ({
                    ...slide,
                    evidence_ids: [...evidenceIds[index]!],
                  })),
                );
              } catch (caught) {
                setError(
                  caught instanceof Error
                    ? caught.message
                    : "Review the proposed outline.",
                );
              }
            }}
          />
        ) : (
          <label>
            Slide outline
            <textarea
              aria-label="Slide outline"
              rows={10}
              value={outline}
              maxLength={80000}
              required
              disabled={busy}
              onChange={(event) => setOutline(event.target.value)}
              placeholder={
                "# Our recommendation\n- The decision we need\n- The expected outcome\nNotes: What you want to explain aloud\n\n# Why now\n- The problem and supporting evidence"
              }
            />
          </label>
        )}
        {mode === "outline" || review ? (
          <p className="muted">
            Begin each slide with “# Title”. Add one point per line and optional
            “Notes:”. Choose your widescreen template and slide layouts during
            review. Review longer text in the editor before presenting.
          </p>
        ) : null}
        {error ? <p role="alert">{error}</p> : null}
        <div className="pw-create-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={busy}
            onClick={onClose}
          >
            Cancel
          </button>
          {review && !created ? (
            <button
              type="button"
              className="secondary-button"
              disabled={busy}
              onClick={() => {
                setOutline(
                  review
                    .map((slide) =>
                      [
                        `# ${slide.title}`,
                        ...slide.bullets.map((point) => `- ${point}`),
                        ...slide.notes
                          .split("\n")
                          .filter(Boolean)
                          .map((note) => `Notes: ${note}`),
                      ].join("\n"),
                    )
                    .join("\n\n"),
                );
                setMode("outline");
                setProviderRunId(null);
                setReview(null);
              }}
            >
              Edit outline
            </button>
          ) : null}
          {mode === "outline" || review || created ? (
            <button
              type="submit"
              className="primary-button"
              disabled={
                busy ||
                invalidSlide >= 0 ||
                !title.trim() ||
                (!review && !outline.trim() && !created)
              }
            >
              {busy
                ? "Creating…"
                : created
                  ? "Open created presentation"
                  : review
                    ? "Create presentation"
                    : "Review outline"}
            </button>
          ) : null}
        </div>
      </form>
    </dialog>,
    document.body,
  );
}
