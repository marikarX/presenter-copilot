import { useEffect, useState } from "react";

export type ClickAction = {
  kind: "none" | "url" | "slide" | "next" | "previous" | "first" | "last";
  url: string | null;
  slide_id: string | null;
};

const KINDS: ReadonlyArray<[ClickAction["kind"], string]> = [
  ["none", "Nothing"],
  ["url", "Open a web link"],
  ["slide", "Go to a slide"],
  ["next", "Next slide"],
  ["previous", "Previous slide"],
  ["first", "First slide"],
  ["last", "Last slide"],
];

/** What clicking the object does in a slide show. */
export function ClickActionEditor({
  objectId,
  action,
  slides,
  disabled,
  onApply,
}: {
  objectId: string;
  action: ClickAction;
  slides: Array<{ slide_id: string; ordinal: number }>;
  disabled: boolean;
  onApply: (action: ClickAction) => void;
}) {
  const [draft, setDraft] = useState(action);
  useEffect(() => {
    setDraft(action);
  }, [objectId, action]);
  const url = (draft.url ?? "").trim();
  const valid =
    draft.kind === "url"
      ? /^(https?:\/\/\S+|mailto:\S+@\S+)$/i.test(url)
      : draft.kind === "slide"
        ? slides.some((slide) => slide.slide_id === draft.slide_id)
        : true;
  const next: ClickAction = {
    kind: draft.kind,
    url: draft.kind === "url" ? url : null,
    slide_id: draft.kind === "slide" ? draft.slide_id : null,
  };
  const changed = JSON.stringify(next) !== JSON.stringify(action);
  return (
    <fieldset className="pw-picture-crop">
      <legend>Click action</legend>
      <p className="muted">What clicking this object does in a slide show.</p>
      <select
        aria-label="Click action"
        value={draft.kind}
        onChange={(event) =>
          setDraft((current) => ({
            ...current,
            kind: event.target.value as ClickAction["kind"],
          }))
        }
        disabled={disabled}
      >
        {KINDS.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      {draft.kind === "url" ? (
        <input
          type="url"
          aria-label="Click action link"
          placeholder="https://"
          maxLength={2048}
          value={draft.url ?? ""}
          onChange={(event) =>
            setDraft((current) => ({ ...current, url: event.target.value }))
          }
          disabled={disabled}
        />
      ) : null}
      {draft.kind === "slide" ? (
        <select
          aria-label="Click action slide"
          value={draft.slide_id ?? ""}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              slide_id: event.target.value || null,
            }))
          }
          disabled={disabled}
        >
          <option value="">Choose a slide…</option>
          {slides.map((slide) => (
            <option key={slide.slide_id} value={slide.slide_id}>
              Slide {slide.ordinal}
            </option>
          ))}
        </select>
      ) : null}
      <button
        type="button"
        className="secondary-button"
        onClick={() => onApply(next)}
        disabled={disabled || !valid || !changed}
      >
        Apply click action
      </button>
    </fieldset>
  );
}
