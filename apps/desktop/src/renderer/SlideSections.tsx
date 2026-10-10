import { useEffect, useState } from "react";

export type SlideSectionState = {
  revision_id: string;
  slide_ids: string[];
  sections: Array<{ section_id: string; name: string; slide_ids: string[] }>;
  editable: boolean;
  reason: string | null;
  fingerprint: string;
};

export type SlideSectionDraft = {
  section_id: string | null;
  name: string;
  first_slide_id: string;
};

export function isSlideSectionState(
  value: unknown,
): value is SlideSectionState {
  if (!value || typeof value !== "object") return false;
  const state = value as Partial<SlideSectionState>;
  const strings = (items: unknown) =>
    Array.isArray(items) && items.every((item) => typeof item === "string");
  return (
    typeof state.revision_id === "string" &&
    strings(state.slide_ids) &&
    Array.isArray(state.sections) &&
    state.sections.every(
      (section) =>
        !!section &&
        typeof section.section_id === "string" &&
        typeof section.name === "string" &&
        strings(section.slide_ids),
    ) &&
    typeof state.editable === "boolean" &&
    (state.reason === null || typeof state.reason === "string") &&
    typeof state.fingerprint === "string" &&
    /^[0-9a-f]{64}$/.test(state.fingerprint)
  );
}

function initialDraft(state: SlideSectionState): SlideSectionDraft[] {
  return state.sections
    .filter((section) => section.slide_ids.length)
    .map((section) => ({
      section_id: section.section_id,
      name: section.name,
      first_slide_id: section.slide_ids[0] ?? "",
    }));
}

/** Named runs of slides; each section starts at a slide and runs to the next. */
export function SlideSections({
  state,
  disabled,
  onApply,
}: {
  state: SlideSectionState;
  disabled: boolean;
  onApply: (sections: SlideSectionDraft[]) => void;
}) {
  const [draft, setDraft] = useState(() => initialDraft(state));
  const [adding, setAdding] = useState({ name: "", start: "" });
  useEffect(() => {
    setDraft(initialDraft(state));
    setAdding({ name: "", start: "" });
  }, [state]);
  const position = (slideId: string) => state.slide_ids.indexOf(slideId);
  const sorted = [...draft].sort(
    (a, b) => position(a.first_slide_id) - position(b.first_slide_id),
  );
  const used = new Set(sorted.map((section) => section.first_slide_id));
  const valid =
    sorted.every((section) => section.name.trim().length > 0) &&
    (sorted.length === 0 || position(sorted[0]?.first_slide_id ?? "") === 0) &&
    used.size === sorted.length;
  const changed =
    JSON.stringify(sorted) !== JSON.stringify(initialDraft(state)) ||
    state.reason !== null;
  const count = (index: number) => {
    const start = position(sorted[index]?.first_slide_id ?? "");
    const next = sorted[index + 1];
    return (
      (next ? position(next.first_slide_id) : state.slide_ids.length) - start
    );
  };
  if (!state.editable)
    return (
      <fieldset className="pw-picture-crop">
        <legend>Sections</legend>
        <p className="muted">{state.reason ?? "Sections stay read-only."}</p>
      </fieldset>
    );
  return (
    <fieldset className="pw-picture-crop">
      <legend>Sections</legend>
      <p className="muted">
        Group slides into named sections. Each section runs until the next one
        starts.
        {state.reason ? ` ${state.reason}` : ""}
      </p>
      {sorted.length ? (
        <ol className="pw-animation-list">
          {sorted.map((section, index) => (
            <li
              key={`${section.section_id ?? "new"}-${section.first_slide_id}`}
            >
              <input
                type="text"
                maxLength={120}
                aria-label={`Section ${index + 1} name`}
                value={section.name}
                onChange={(event) =>
                  setDraft((current) =>
                    current.map((item) =>
                      item === section
                        ? { ...item, name: event.target.value }
                        : item,
                    ),
                  )
                }
                disabled={disabled}
              />
              <span className="muted">
                Slide {position(section.first_slide_id) + 1} · {count(index)}{" "}
                slide{count(index) === 1 ? "" : "s"}
              </span>
              {index > 0 ? (
                <button
                  type="button"
                  className="secondary-button"
                  aria-label={`Merge section ${section.name} into the previous one`}
                  onClick={() =>
                    setDraft((current) =>
                      current.filter((item) => item !== section),
                    )
                  }
                  disabled={disabled}
                >
                  Merge up
                </button>
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">This presentation has no sections.</p>
      )}
      <div className="pw-animation-add">
        <input
          type="text"
          maxLength={120}
          aria-label="New section name"
          placeholder="Section name"
          value={adding.name}
          onChange={(event) =>
            setAdding((current) => ({ ...current, name: event.target.value }))
          }
          disabled={disabled}
        />
        <select
          aria-label="New section starts at"
          value={adding.start}
          onChange={(event) =>
            setAdding((current) => ({ ...current, start: event.target.value }))
          }
          disabled={disabled}
        >
          <option value="">Starts at slide…</option>
          {state.slide_ids.map((slideId, index) =>
            used.has(slideId) ? null : (
              <option key={slideId} value={slideId}>
                Slide {index + 1}
              </option>
            ),
          )}
        </select>
        <button
          type="button"
          className="secondary-button"
          onClick={() => {
            const firstSlide = state.slide_ids[0];
            if (!adding.start || !adding.name.trim() || !firstSlide) return;
            setDraft((current) => [
              // PowerPoint keeps every slide in a section: start with a default one.
              ...(current.length || adding.start === firstSlide
                ? current
                : [
                    {
                      section_id: null,
                      name: "Default Section",
                      first_slide_id: firstSlide,
                    },
                  ]),
              {
                section_id: null,
                name: adding.name.trim(),
                first_slide_id: adding.start,
              },
            ]);
            setAdding({ name: "", start: "" });
          }}
          disabled={disabled || !adding.start || !adding.name.trim()}
        >
          Add section
        </button>
      </div>
      <div className="pw-animation-add">
        <button
          type="button"
          className="secondary-button"
          onClick={() => onApply(sorted)}
          disabled={disabled || !valid || !changed}
        >
          Apply sections
        </button>
        {state.sections.length ? (
          <button
            type="button"
            className="secondary-button"
            onClick={() => onApply([])}
            disabled={disabled}
          >
            Remove all sections
          </button>
        ) : null}
      </div>
    </fieldset>
  );
}
