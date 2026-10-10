import { useEffect, useState } from "react";
import type { RendererCoreMethod } from "../shared/protocol";

export type ReuseRequest = {
  source_document_id: string;
  source_revision_id: string;
  source_slide_id: string;
  position: number;
  label: string;
};

type DonorSlide = {
  revision_id: string;
  slide_id: string;
  slide_count: number;
  preview: string[];
};

/** Copy a slide from another deck in the project, taking this deck's design. */
export function ReuseSlides({
  projectId,
  decks,
  slideCount,
  currentSlide,
  disabled,
  request,
  onReuse,
}: {
  projectId: string;
  decks: Array<{ id: string; name: string }>;
  slideCount: number;
  currentSlide: number;
  disabled: boolean;
  request: <T>(
    method: RendererCoreMethod,
    params: Record<string, unknown>,
  ) => Promise<T>;
  onReuse: (request: ReuseRequest) => void;
}) {
  const [deck, setDeck] = useState("");
  const [number, setNumber] = useState(1);
  const [slide, setSlide] = useState<DonorSlide | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [position, setPosition] = useState(currentSlide + 1);

  useEffect(() => {
    setPosition(Math.min(currentSlide + 1, slideCount + 1));
  }, [currentSlide, slideCount]);

  useEffect(() => {
    if (!deck) {
      setSlide(null);
      return;
    }
    let cancelled = false;
    setFailure(null);
    (async () => {
      const history = await request<{ current_revision_id: string }>(
        "presentation.workspace.list_revisions",
        { project_id: projectId, document_id: deck },
      );
      const targets = await request<{
        revision_id: string;
        slide_id: string;
        slide_count: number;
        targets: Array<{ current_text: string | null }>;
      }>("presentation.workspace.list_text_targets", {
        project_id: projectId,
        document_id: deck,
        revision_id: history.current_revision_id,
        slide_number: number,
      });
      if (
        typeof targets.slide_id !== "string" ||
        !Number.isSafeInteger(targets.slide_count) ||
        !Array.isArray(targets.targets)
      )
        throw new Error("The slide to reuse could not be verified.");
      if (!cancelled)
        setSlide({
          revision_id: targets.revision_id,
          slide_id: targets.slide_id,
          slide_count: targets.slide_count,
          preview: targets.targets
            .map((item) => item.current_text?.trim() ?? "")
            .filter(Boolean)
            .slice(0, 3),
        });
    })().catch((caught) => {
      if (!cancelled) {
        setSlide(null);
        setFailure(
          caught instanceof Error
            ? caught.message
            : "That deck's slides could not load.",
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, [deck, number, projectId, request]);

  const name = decks.find((item) => item.id === deck)?.name ?? "";
  return (
    <fieldset className="pw-picture-crop">
      <legend>Reuse slides</legend>
      <p className="muted">
        Copy a slide from another presentation in this project. It takes this
        deck&apos;s design and brings its pictures, charts, diagrams and speaker
        notes.
      </p>
      {decks.length ? (
        <>
          <label>
            From
            <select
              aria-label="Presentation to reuse from"
              value={deck}
              onChange={(event) => {
                setDeck(event.target.value);
                setNumber(1);
              }}
              disabled={disabled}
            >
              <option value="">Choose a presentation…</option>
              {decks.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          {deck && slide ? (
            <>
              <label>
                Slide
                <select
                  aria-label="Slide to reuse"
                  value={number}
                  onChange={(event) => setNumber(Number(event.target.value))}
                  disabled={disabled}
                >
                  {Array.from({ length: slide.slide_count }, (_, index) => (
                    <option key={index} value={index + 1}>
                      Slide {index + 1}
                    </option>
                  ))}
                </select>
              </label>
              <p className="muted" aria-label="Slide to reuse preview">
                {slide.preview.length
                  ? slide.preview.join(" · ")
                  : "This slide has no text."}
              </p>
              <label>
                Insert
                <select
                  aria-label="Insert reused slide"
                  value={position}
                  onChange={(event) => setPosition(Number(event.target.value))}
                  disabled={disabled}
                >
                  <option value={1}>At the beginning</option>
                  {Array.from({ length: slideCount }, (_, index) => (
                    <option key={index} value={index + 2}>
                      After slide {index + 1}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="secondary-button"
                disabled={disabled}
                onClick={() =>
                  onReuse({
                    source_document_id: deck,
                    source_revision_id: slide.revision_id,
                    source_slide_id: slide.slide_id,
                    position,
                    label: `slide ${number} of ${name}`,
                  })
                }
              >
                Reuse slide
              </button>
            </>
          ) : null}
          {failure ? <p className="muted">{failure}</p> : null}
        </>
      ) : (
        <p className="muted">
          Import another presentation into this project to reuse its slides.
        </p>
      )}
    </fieldset>
  );
}
