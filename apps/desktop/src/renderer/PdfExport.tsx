import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { Modal } from "./Modal";

export function PdfExport({
  projectId,
  documentId,
  revisionId,
  revisionNumber,
  sourceSha256,
  disabled,
  onNotice,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  revisionNumber: number;
  sourceSha256: string;
  disabled: boolean;
  onNotice(message: string): void;
}) {
  const [open, setOpen] = useState(false);
  const [includeHidden, setIncludeHidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const failureRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (failure) failureRef.current?.focus();
  }, [failure]);
  async function save() {
    if (busy || disabled) return;
    setBusy(true);
    setFailure(null);
    try {
      const result = unwrapInvokeResult(
        await window.presenterCopilot.presentation.savePdf(
          projectId,
          documentId,
          revisionId,
          includeHidden,
        ),
      );
      if ("cancelled" in result) return;
      if (
        !result.saved ||
        result.revision_id !== revisionId ||
        result.source_sha256 !== sourceSha256 ||
        result.renderer !== "microsoft_powerpoint" ||
        result.include_hidden !== includeHidden ||
        !Number.isInteger(result.page_count) ||
        result.page_count < 1 ||
        !result.file_name
      )
        throw new Error(
          "The PDF could not be verified against this presentation revision.",
        );
      setOpen(false);
      onNotice(
        `Exported revision ${revisionNumber} as ${result.file_name}: ${result.page_count} PDF page${result.page_count === 1 ? "" : "s"}${includeHidden ? ", including hidden slides" : ", hidden slides omitted"}.`,
      );
    } catch (caught) {
      setFailure(
        isCoreError(caught)
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "The presentation PDF could not be exported.",
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
        disabled={disabled || busy}
        onClick={() => {
          setFailure(null);
          setOpen(true);
        }}
        title="Export this revision using Microsoft PowerPoint on Windows."
      >
        {busy ? "Exporting PDF…" : "Export PDF"}
      </button>
      {open
        ? createPortal(
            <Modal
              titleId="pw-pdf-title"
              onClose={() => {
                if (!busy) setOpen(false);
              }}
            >
              <h2 id="pw-pdf-title">Export presentation as PDF</h2>
              <p>
                Save revision {revisionNumber} as print-quality slides using
                Microsoft PowerPoint installed on Windows.
              </p>
              <p className="muted">
                The PDF contains static slides. Speaker notes, animations and
                transitions are not included. Keep the PPTX copy for further
                editing.
              </p>
              {failure ? (
                <>
                  <p role="alert" tabIndex={-1} ref={failureRef}>
                    {failure}
                  </p>
                  <p className="muted">
                    Cancel returns to the workspace. Save &amp; open can open a
                    PPTX copy for manual export.
                  </p>
                </>
              ) : null}
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={includeHidden}
                  disabled={busy}
                  onChange={(event) => setIncludeHidden(event.target.checked)}
                />{" "}
                Include hidden slides
              </label>
              {busy ? (
                <p role="status">
                  PowerPoint is exporting and verifying the PDF. This can take
                  up to two minutes.
                </p>
              ) : null}
              <div className="button-row">
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => setOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="primary-button"
                  disabled={disabled || busy}
                  onClick={() => void save()}
                >
                  {busy ? "Exporting…" : "Choose PDF destination"}
                </button>
              </div>
            </Modal>,
            document.body,
          )
        : null}
    </>
  );
}
