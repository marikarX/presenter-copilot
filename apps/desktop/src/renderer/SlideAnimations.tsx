import { useEffect, useState } from "react";

export type SlideAnimationEffect = {
  object_id: string;
  name: string;
  effect: string;
  start: string;
  /** null animates the whole object; otherwise one paragraph of its text. */
  paragraph?: number | null;
};

export type SlideAnimationState = {
  slide_id: string;
  editable: boolean;
  reason: string | null;
  effects: SlideAnimationEffect[];
  candidates: Array<{
    object_id: string;
    name: string;
    paragraphs?: Array<{ index: number; text: string }>;
  }>;
  fingerprint: string;
};

const ENTRANCES: ReadonlyArray<[string, string]> = [
  ["appear", "Appear"],
  ["fade", "Fade"],
  ["fly_in", "Fly in"],
  ["wipe", "Wipe"],
  ["zoom", "Zoom"],
];
const EXITS: ReadonlyArray<[string, string]> = [
  ["disappear", "Disappear"],
  ["fade_out", "Fade out"],
  ["fly_out", "Fly out"],
  ["wipe_out", "Wipe out"],
  ["zoom_out", "Zoom out"],
];
const STARTS: ReadonlyArray<[string, string]> = [
  ["on_click", "On click"],
  ["with_previous", "With previous"],
  ["after_previous", "After previous"],
];

const EMPHASES: ReadonlyArray<[string, string]> = [
  ["pulse", "Pulse"],
  ["grow_shrink", "Grow/Shrink"],
  ["spin", "Spin"],
  ["teeter", "Teeter"],
];
type Kind = "entrance" | "emphasis" | "exit";
const kindOf = (effect: string): Kind =>
  effect === "custom_exit" || EXITS.some(([value]) => value === effect)
    ? "exit"
    : effect === "custom_emphasis" ||
        EMPHASES.some(([value]) => value === effect)
      ? "emphasis"
      : "entrance";
const CHOICES: Record<Kind, ReadonlyArray<[string, string]>> = {
  entrance: ENTRANCES,
  emphasis: EMPHASES,
  exit: EXITS,
};
const CUSTOMS: Record<Kind, string> = {
  entrance: "custom",
  emphasis: "custom_emphasis",
  exit: "custom_exit",
};

export function isSlideAnimationState(
  value: unknown,
): value is SlideAnimationState {
  if (!value || typeof value !== "object") return false;
  const state = value as Partial<SlideAnimationState>;
  const named = (item: unknown) =>
    !!item &&
    typeof item === "object" &&
    typeof (item as { object_id?: unknown }).object_id === "string" &&
    typeof (item as { name?: unknown }).name === "string";
  return (
    typeof state.slide_id === "string" &&
    typeof state.editable === "boolean" &&
    (state.reason === null || typeof state.reason === "string") &&
    Array.isArray(state.effects) &&
    state.effects.every(
      (effect) =>
        named(effect) &&
        typeof effect.effect === "string" &&
        STARTS.some(([value]) => value === effect.start),
    ) &&
    Array.isArray(state.candidates) &&
    state.candidates.every(named) &&
    typeof state.fingerprint === "string" &&
    /^[0-9a-f]{64}$/.test(state.fingerprint)
  );
}

const key = (effects: SlideAnimationEffect[]) =>
  JSON.stringify(
    effects.map((e) => [e.object_id, e.effect, e.start, e.paragraph ?? null]),
  );

/** "Box" for the whole object, "Box paragraph 2" for one of its paragraphs. */
const targetName = (effect: SlideAnimationEffect) =>
  effect.paragraph == null
    ? effect.name
    : `${effect.name} paragraph ${effect.paragraph + 1}`;

/** Ordered entrance and exit effects for one slide; Apply writes them as one revision. */
export function SlideAnimations({
  state,
  disabled,
  onApply,
}: {
  state: SlideAnimationState;
  disabled: boolean;
  onApply: (effects: SlideAnimationEffect[]) => void;
}) {
  const [draft, setDraft] = useState(state.effects);
  const [adding, setAdding] = useState({
    objectId: "",
    effect: "fade",
    byParagraph: false,
  });
  useEffect(() => {
    setDraft(state.effects);
    setAdding({ objectId: "", effect: "fade", byParagraph: false });
  }, [state]);
  // Each object, or paragraph, can have one effect of each kind.
  const taken = (objectId: string, paragraph: number | null, kind: Kind) =>
    draft.some(
      (e) =>
        e.object_id === objectId &&
        (e.paragraph ?? null) === paragraph &&
        kindOf(e.effect) === kind,
    );
  const available = state.candidates;
  const chosen = available.find((c) => c.object_id === adding.objectId);
  const paragraphs = chosen?.paragraphs ?? [];
  const steps: Array<number | null> =
    adding.byParagraph && paragraphs.length > 1
      ? paragraphs.map((p) => p.index)
      : [null];
  const conflict =
    !!chosen &&
    steps.some((step) => taken(adding.objectId, step, kindOf(adding.effect)));
  const update = (index: number, change: Partial<SlideAnimationEffect>) =>
    setDraft((current) =>
      current.map((effect, i) =>
        i === index ? { ...effect, ...change } : effect,
      ),
    );
  const move = (index: number, offset: number) =>
    setDraft((current) => {
      const next = [...current];
      const [item] = next.splice(index, 1);
      if (item) next.splice(index + offset, 0, item);
      return next;
    });
  if (!state.editable)
    return (
      <fieldset className="pw-picture-crop">
        <legend>Animations</legend>
        <p className="muted">{state.reason ?? "Animations stay read-only."}</p>
      </fieldset>
    );
  return (
    <fieldset className="pw-picture-crop">
      <legend>Animations</legend>
      <p className="muted">
        Entrance and exit effects play in this order during the slide show.
      </p>
      {draft.length ? (
        <ol className="pw-animation-list">
          {draft.map((effect, index) => {
            const kind = kindOf(effect.effect);
            const custom = CUSTOMS[kind];
            const target = targetName(effect);
            // Entrance rows keep their established labels; others name their kind.
            const label = (entrance: string, leaving: string) =>
              kind === "exit"
                ? leaving
                : kind === "emphasis"
                  ? leaving
                      .replace("Exit", "Emphasis")
                      .replace("exit", "emphasis")
                  : entrance;
            return (
              <li
                key={`${effect.object_id}:${effect.paragraph ?? "all"}:${kind}`}
              >
                <span>
                  {index + 1}. {target}
                  {kind === "entrance" ? "" : ` (${kind})`}
                </span>
                <select
                  aria-label={label(
                    `Animation effect for ${target}`,
                    `Exit effect for ${target}`,
                  )}
                  value={effect.effect}
                  onChange={(event) =>
                    update(index, { effect: event.target.value })
                  }
                  disabled={disabled}
                >
                  {effect.effect === custom ||
                  state.effects.some(
                    (e) =>
                      e.object_id === effect.object_id && e.effect === custom,
                  ) ? (
                    <option value={custom}>Custom (kept as is)</option>
                  ) : null}
                  {CHOICES[kind].map(([value, name]) => (
                    <option key={value} value={value}>
                      {name}
                    </option>
                  ))}
                </select>
                <select
                  aria-label={label(
                    `Animation start for ${target}`,
                    `Exit start for ${target}`,
                  )}
                  value={effect.start}
                  onChange={(event) =>
                    update(index, { start: event.target.value })
                  }
                  disabled={disabled}
                >
                  {STARTS.map(([value, name]) => (
                    <option key={value} value={value}>
                      {name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="secondary-button"
                  aria-label={label(
                    `Play ${target} earlier`,
                    `Play ${target} exit earlier`,
                  )}
                  onClick={() => move(index, -1)}
                  disabled={disabled || index === 0}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  aria-label={label(
                    `Play ${target} later`,
                    `Play ${target} exit later`,
                  )}
                  onClick={() => move(index, 1)}
                  disabled={disabled || index === draft.length - 1}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  aria-label={label(
                    `Remove animation from ${target}`,
                    `Remove exit from ${target}`,
                  )}
                  onClick={() =>
                    setDraft((current) => current.filter((_, i) => i !== index))
                  }
                  disabled={disabled}
                >
                  Remove
                </button>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="muted">No entrance animations on this slide.</p>
      )}
      <div className="pw-animation-add">
        <select
          aria-label="Object to animate"
          value={adding.objectId}
          onChange={(event) =>
            setAdding((current) => ({
              ...current,
              objectId: event.target.value,
            }))
          }
          disabled={disabled || !available.length}
        >
          <option value="">Choose an object…</option>
          {available.map((candidate) => (
            <option key={candidate.object_id} value={candidate.object_id}>
              {candidate.name}
            </option>
          ))}
        </select>
        <select
          aria-label="New animation effect"
          value={adding.effect}
          onChange={(event) =>
            setAdding((current) => ({
              ...current,
              effect: event.target.value,
            }))
          }
          disabled={disabled}
        >
          <optgroup label="Entrance">
            {ENTRANCES.map(([value, name]) => (
              <option key={value} value={value}>
                {name}
              </option>
            ))}
          </optgroup>
          <optgroup label="Emphasis">
            {EMPHASES.map(([value, name]) => (
              <option key={value} value={value}>
                {name}
              </option>
            ))}
          </optgroup>
          <optgroup label="Exit">
            {EXITS.map(([value, name]) => (
              <option key={value} value={value}>
                {name}
              </option>
            ))}
          </optgroup>
        </select>
        {paragraphs.length > 1 ? (
          <label className="checkbox-row">
            <input
              type="checkbox"
              aria-label="Animate by paragraph"
              checked={adding.byParagraph}
              onChange={(event) =>
                setAdding((current) => ({
                  ...current,
                  byParagraph: event.target.checked,
                }))
              }
              disabled={disabled}
            />
            By paragraph ({paragraphs.length} steps)
          </label>
        ) : null}
        <button
          type="button"
          className="secondary-button"
          onClick={() => {
            if (!chosen || conflict) return;
            // A by-paragraph build is one on-click step per paragraph, as in PowerPoint.
            setDraft((current) => [
              ...current,
              ...steps.map((paragraph) => ({
                object_id: chosen.object_id,
                name: chosen.name,
                effect: adding.effect,
                start: "on_click",
                paragraph,
              })),
            ]);
            setAdding((current) => ({ ...current, objectId: "" }));
          }}
          disabled={disabled || !chosen || conflict}
          title={
            conflict
              ? "This object already has an effect of that kind."
              : undefined
          }
        >
          Add animation
        </button>
      </div>
      <button
        type="button"
        className="secondary-button"
        onClick={() => onApply(draft)}
        disabled={disabled || key(draft) === key(state.effects)}
      >
        Apply animations
      </button>
    </fieldset>
  );
}
