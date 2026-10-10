import { useEffect, useState } from "react";
import type { RendererCoreMethod } from "../shared/protocol";

export type DeckFont = {
  name: string;
  uses: number;
  theme: boolean;
  equation_uses: number;
};

function isDeckFont(value: unknown): value is DeckFont {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<DeckFont>;
  return (
    typeof item.name === "string" &&
    Number.isSafeInteger(item.uses) &&
    typeof item.theme === "boolean" &&
    Number.isSafeInteger(item.equation_uses)
  );
}

/** Rename one typeface everywhere in the deck, like PowerPoint's Replace Fonts. */
export function ReplaceFonts({
  projectId,
  documentId,
  revisionId,
  disabled,
  request,
  onReplace,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  disabled: boolean;
  request: <T>(
    method: RendererCoreMethod,
    params: Record<string, unknown>,
  ) => Promise<T>;
  onReplace: (font: DeckFont, replacement: string) => void;
}) {
  const [fonts, setFonts] = useState<DeckFont[] | null>(null);
  const [selected, setSelected] = useState("");
  const [replacement, setReplacement] = useState("");
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setFonts(null);
    setFailure(null);
    request<{ fonts: unknown[] }>("presentation.workspace.list_fonts", {
      project_id: projectId,
      document_id: documentId,
      expected_revision_id: revisionId,
    })
      .then((result) => {
        if (cancelled) return;
        if (!Array.isArray(result.fonts) || !result.fonts.every(isDeckFont))
          throw new Error("The deck's fonts could not be verified.");
        setFonts(result.fonts);
        setSelected((current) =>
          result.fonts.some((item) => (item as DeckFont).name === current)
            ? current
            : ((result.fonts[0] as DeckFont | undefined)?.name ?? ""),
        );
      })
      .catch((caught) => {
        if (!cancelled)
          setFailure(
            caught instanceof Error
              ? caught.message
              : "The deck's fonts could not load.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [documentId, projectId, request, revisionId]);

  const font = fonts?.find((item) => item.name === selected);
  const name = replacement.trim();
  return (
    <fieldset className="pw-picture-crop">
      <legend>Replace fonts</legend>
      <p className="muted">
        Every use of a font in slides, layouts, masters, notes, charts and the
        theme changes to the replacement.
      </p>
      {failure ? <p className="muted">{failure}</p> : null}
      {fonts && !fonts.length ? (
        <p className="muted">This presentation names no fonts.</p>
      ) : null}
      {fonts?.length ? (
        <>
          <label>
            Replace
            <select
              aria-label="Font to replace"
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
              disabled={disabled}
            >
              {fonts.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name} · {item.uses} use{item.uses === 1 ? "" : "s"}
                  {item.theme ? " · theme" : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            With
            <input
              type="text"
              list="pw-font-family-suggestions"
              maxLength={31}
              aria-label="Replacement font"
              value={replacement}
              onChange={(event) => setReplacement(event.target.value)}
              disabled={disabled}
            />
          </label>
          {font?.equation_uses ? (
            <p className="muted" role="note">
              {font.equation_uses} of these uses are in equations, which need a
              math font such as Cambria Math to render correctly.
            </p>
          ) : null}
          <button
            type="button"
            className="secondary-button"
            disabled={disabled || !font || !name || name === font.name}
            onClick={() => font && onReplace(font, name)}
          >
            Replace font
          </button>
        </>
      ) : null}
    </fieldset>
  );
}
