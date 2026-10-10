import { useEffect, useState } from "react";

/** Alt text and PowerPoint's "Mark as decorative" flag for one object. */
export function AltTextEditor({
  objectId,
  altText,
  decorative,
  disabled,
  onApply,
}: {
  objectId: string;
  altText: string;
  decorative: boolean;
  disabled: boolean;
  onApply: (altText: string, decorative: boolean) => void;
}) {
  const [draft, setDraft] = useState({ text: altText, decorative });
  useEffect(() => {
    setDraft({ text: altText, decorative });
  }, [objectId, altText, decorative]);
  const changed =
    draft.text.trim() !== altText || draft.decorative !== decorative;
  return (
    <fieldset className="pw-picture-crop">
      <legend>Alt text</legend>
      <p className="muted">
        Screen readers read this description. Mark purely visual objects as
        decorative instead.
      </p>
      <textarea
        aria-label="Alt text"
        maxLength={2000}
        rows={3}
        value={draft.text}
        onChange={(event) =>
          setDraft((current) => ({ ...current, text: event.target.value }))
        }
        disabled={disabled || draft.decorative}
      />
      <label className="checkbox-row">
        <input
          type="checkbox"
          aria-label="Mark as decorative"
          checked={draft.decorative}
          onChange={(event) =>
            setDraft((current) => ({
              ...current,
              decorative: event.target.checked,
            }))
          }
          disabled={disabled}
        />
        Mark as decorative
      </label>
      {!draft.decorative && !draft.text.trim() ? (
        <p className="muted">This object has no alt text.</p>
      ) : null}
      <button
        type="button"
        className="secondary-button"
        onClick={() =>
          onApply(draft.decorative ? "" : draft.text.trim(), draft.decorative)
        }
        disabled={disabled || !changed}
      >
        Apply alt text
      </button>
    </fieldset>
  );
}
