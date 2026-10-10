import { useEffect, useState } from "react";

export type SlideAnimationEffect = {
  object_id: string;
  name: string;
  effect: string;
  start: string;
};

export type SlideAnimationState = {
  slide_id: string;
  editable: boolean;
  reason: string | null;
  effects: SlideAnimationEffect[];
  candidates: Array<{ object_id: string; name: string }>;
  fingerprint: string;
};

const EFFECTS: ReadonlyArray<[string, string]> = [
  ["appear", "Appear"],
  ["fade", "Fade"],
  ["fly_in", "Fly in"],
  ["wipe", "Wipe"],
  ["zoom", "Zoom"],
];
const STARTS: ReadonlyArray<[string, string]> = [
  ["on_click", "On click"],
  ["with_previous", "With previous"],
  ["after_previous", "After previous"],
];

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
  JSON.stringify(effects.map((e) => [e.object_id, e.effect, e.start]));

/** Ordered entrance effects for one slide; Apply writes them as one revision. */
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
  const [adding, setAdding] = useState({ objectId: "", effect: "fade" });
  useEffect(() => {
    setDraft(state.effects);
    setAdding({ objectId: "", effect: "fade" });
  }, [state]);
  const available = state.candidates.filter(
    (candidate) => !draft.some((e) => e.object_id === candidate.object_id),
  );
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
        Entrance effects play in this order during the slide show.
      </p>
      {draft.length ? (
        <ol className="pw-animation-list">
          {draft.map((effect, index) => (
            <li key={effect.object_id}>
              <span>
                {index + 1}. {effect.name}
              </span>
              <select
                aria-label={`Animation effect for ${effect.name}`}
                value={effect.effect}
                onChange={(event) =>
                  update(index, { effect: event.target.value })
                }
                disabled={disabled}
              >
                {effect.effect === "custom" ||
                state.effects.some(
                  (e) =>
                    e.object_id === effect.object_id && e.effect === "custom",
                ) ? (
                  <option value="custom">Custom (kept as is)</option>
                ) : null}
                {EFFECTS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <select
                aria-label={`Animation start for ${effect.name}`}
                value={effect.start}
                onChange={(event) =>
                  update(index, { start: event.target.value })
                }
                disabled={disabled}
              >
                {STARTS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="secondary-button"
                aria-label={`Play ${effect.name} earlier`}
                onClick={() => move(index, -1)}
                disabled={disabled || index === 0}
              >
                ↑
              </button>
              <button
                type="button"
                className="secondary-button"
                aria-label={`Play ${effect.name} later`}
                onClick={() => move(index, 1)}
                disabled={disabled || index === draft.length - 1}
              >
                ↓
              </button>
              <button
                type="button"
                className="secondary-button"
                aria-label={`Remove animation from ${effect.name}`}
                onClick={() =>
                  setDraft((current) => current.filter((_, i) => i !== index))
                }
                disabled={disabled}
              >
                Remove
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">No entrance animations on this slide.</p>
      )}
      {available.length ? (
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
            disabled={disabled}
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
            {EFFECTS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              const candidate = available.find(
                (c) => c.object_id === adding.objectId,
              );
              if (!candidate) return;
              setDraft((current) => [
                ...current,
                {
                  object_id: candidate.object_id,
                  name: candidate.name,
                  effect: adding.effect,
                  start: "on_click",
                },
              ]);
              setAdding((current) => ({ ...current, objectId: "" }));
            }}
            disabled={disabled || !adding.objectId}
          >
            Add animation
          </button>
        </div>
      ) : null}
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
