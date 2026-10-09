import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";

type Match = {
  target: "slide" | "speaker_notes";
  slide_id: string;
  slide_number: number;
  object_id: string | null;
  name: string;
  excerpt: string;
  replaceable_count: number;
  skipped_count: number;
};

type FindResult = {
  query: string;
  match_case: boolean;
  replaceable_matches: number;
  skipped_matches: number;
  objects: Match[];
  objects_truncated: boolean;
};

function isFindResult(value: unknown): value is FindResult {
  if (!value || typeof value !== "object") return false;
  const result = value as Partial<FindResult>;
  return (
    typeof result.query === "string" &&
    typeof result.match_case === "boolean" &&
    Number.isSafeInteger(result.replaceable_matches) &&
    Number.isSafeInteger(result.skipped_matches) &&
    typeof result.objects_truncated === "boolean" &&
    Array.isArray(result.objects) &&
    result.objects.every(
      (item) =>
        (item?.target === "slide" || item?.target === "speaker_notes") &&
        typeof item.slide_id === "string" &&
        (item.target === "slide"
          ? typeof item.object_id === "string"
          : item.object_id === null) &&
        typeof item.name === "string" &&
        typeof item.excerpt === "string" &&
        Number.isSafeInteger(item.slide_number) &&
        Number.isSafeInteger(item.replaceable_count) &&
        Number.isSafeInteger(item.skipped_count),
    )
  );
}

/** Deck-wide find and run-preserving replace as one reviewed revision. */
export function FindReplace({
  projectId,
  documentId,
  revisionId,
  disabled,
  onReplaced,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  disabled: boolean;
  onReplaced: (replaced: number, objects: number) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [replacement, setReplacement] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [result, setResult] = useState<FindResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const generation = useRef(0);
  useEffect(() => {
    if (open) dialog.current?.showModal();
  }, [open]);
  // Results belong to one query, case mode and revision.
  const current =
    result && result.query === query && result.match_case === matchCase
      ? result
      : null;
  const message = (caught: unknown, fallback: string) =>
    isCoreError(caught)
      ? caught.message
      : caught instanceof Error
        ? caught.message
        : fallback;

  async function find() {
    const id = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const found = unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "presentation.workspace.find_text",
          {
            project_id: projectId,
            document_id: documentId,
            expected_revision_id: revisionId,
            query,
            match_case: matchCase,
          },
        ),
      );
      if (!isFindResult(found))
        throw new Error("The search results could not be verified.");
      if (id === generation.current) setResult(found);
    } catch (caught) {
      if (id === generation.current) {
        setResult(null);
        setError(message(caught, "The presentation could not be searched."));
      }
    } finally {
      if (id === generation.current) setBusy(false);
    }
  }

  async function replaceAll() {
    if (!current || current.replaceable_matches < 1) return;
    const id = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const saved = unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "presentation.workspace.replace_text_all",
          {
            project_id: projectId,
            document_id: documentId,
            expected_revision_id: revisionId,
            query: current.query,
            match_case: current.match_case,
            replacement,
            expected_matches: current.objects
              .filter((item) => item.replaceable_count > 0)
              .map((item) => ({
                target: item.target,
                slide_id: item.slide_id,
                object_id: item.object_id,
                replaceable_count: item.replaceable_count,
              })),
          },
        ),
      ) as { replaced_matches?: unknown; objects_changed?: unknown };
      if (
        !Number.isSafeInteger(saved.replaced_matches) ||
        !Number.isSafeInteger(saved.objects_changed)
      )
        throw new Error("The replacement revision could not be verified.");
      if (id !== generation.current) return;
      setResult(null);
      setOpen(false);
      await onReplaced(
        saved.replaced_matches as number,
        saved.objects_changed as number,
      );
    } catch (caught) {
      if (id === generation.current)
        setError(message(caught, "The text could not be replaced."));
    } finally {
      if (id === generation.current) setBusy(false);
    }
  }

  const validQuery = query.trim().length > 0 && query.length <= 200;
  return (
    <>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled}
        onClick={() => {
          setResult(null);
          setError("");
          setOpen(true);
        }}
      >
        Find and replace
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review"
              aria-labelledby="pw-find-replace-title"
              onCancel={(event) => {
                event.preventDefault();
                if (!busy) setOpen(false);
              }}
            >
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  if (validQuery && !busy) void find();
                }}
              >
                <h2 id="pw-find-replace-title">Find and replace</h2>
                <p>
                  Search all slide text and speaker notes. Replacing keeps each
                  run&apos;s formatting and saves one revision you can undo.
                  Matches that span differently formatted text, or sit in fields
                  such as slide numbers, are listed but not replaced.
                </p>
                <label>
                  Find
                  <input
                    type="text"
                    maxLength={200}
                    aria-label="Find text"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    disabled={busy}
                  />
                </label>
                <label>
                  Replace with
                  <input
                    type="text"
                    maxLength={2000}
                    aria-label="Replace with"
                    value={replacement}
                    onChange={(event) => setReplacement(event.target.value)}
                    disabled={busy}
                  />
                </label>
                <label className="pw-edit-review-ack">
                  <input
                    type="checkbox"
                    aria-label="Match case"
                    checked={matchCase}
                    onChange={(event) => setMatchCase(event.target.checked)}
                    disabled={busy}
                  />
                  Match case
                </label>
                {error ? <p role="alert">{error}</p> : null}
                {current ? (
                  <div role="status" aria-label="Search results">
                    <p>
                      {current.replaceable_matches} replaceable{" "}
                      {current.replaceable_matches === 1 ? "match" : "matches"}
                      {current.skipped_matches
                        ? ` · ${current.skipped_matches} not replaceable`
                        : ""}
                    </p>
                    <ul>
                      {current.objects.map((item) => (
                        <li
                          key={`${item.target}:${item.slide_id}:${item.object_id ?? ""}`}
                        >
                          Slide {item.slide_number} · {item.name}:{" "}
                          {item.excerpt} ({item.replaceable_count}
                          {item.skipped_count
                            ? `, ${item.skipped_count} skipped`
                            : ""}
                          )
                        </li>
                      ))}
                    </ul>
                    {current.objects_truncated ? (
                      <p className="muted">
                        Showing the first 200 objects. Narrow the search to
                        review every match.
                      </p>
                    ) : null}
                  </div>
                ) : null}
                <div className="pw-shape-color-control">
                  <button
                    type="submit"
                    className="secondary-button"
                    disabled={busy || !validQuery}
                  >
                    Find
                  </button>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => void replaceAll()}
                    disabled={
                      busy ||
                      !current ||
                      current.replaceable_matches < 1 ||
                      current.objects_truncated
                    }
                  >
                    {current
                      ? `Replace all ${current.replaceable_matches}`
                      : "Replace all"}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setOpen(false)}
                    disabled={busy}
                  >
                    Close
                  </button>
                </div>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
