import { useEffect, useState } from "react";
import { unwrapInvokeResult } from "../shared/protocol";
import { RehearsalComparison } from "./RehearsalComparison";
import { RehearsalCoverage } from "./RehearsalCoverage";
import { RecurringObjections } from "./RecurringObjections";
import { RehearsalSemanticReview } from "./RehearsalSemanticReview";
import { RehearsalObjectionComparison } from "./RehearsalObjectionComparison";
import { RehearsalObjectionReview } from "./RehearsalObjectionReview";

export type RehearsalFinding = {
  finding_id: string;
  kind:
    | "marked"
    | "long_explanation"
    | "evidence_review"
    | "spoken_explanation"
    | "semantic_coverage"
    | "semantic_objection";
  session_id: string;
  source_revision_id: string;
  source_revision_number: number;
  source_slide_number: number | null;
  slide_id: string | null;
  current_slide_number: number | null;
  quote: string;
  label: string;
  disposition: "unreviewed" | "applied" | "rejected";
  applied_revision_id: string | null;
  object_id?: string;
  current_span_status?: string;
  context_current?: boolean;
};
type FindingsResult = {
  document_id: string;
  revision_id: string;
  findings: RehearsalFinding[];
  sessions: Array<{
    session_id: string;
    revision_number: number;
    started_at: string;
    debrief_available: boolean;
  }>;
  truncated: boolean;
};
const labels = {
  marked: "Your rehearsal marker",
  long_explanation: "Long explanation",
  evidence_review: "Evidence needs review",
  spoken_explanation: "Spoken explanation to review",
  semantic_coverage: "Unverified window coverage hint",
  semantic_objection: "Unverified recorded-window concern",
};

export function RehearsalFindings({
  projectId,
  documentId,
  revisionId,
  selectedSlide,
  visible,
  disabled,
  onOpenSlide,
  onPrepare,
  selectedTextObjectId,
  selectedTextEditable,
  onSelectTextObject,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  selectedSlide: number;
  visible: boolean;
  disabled: boolean;
  selectedTextObjectId: string | null;
  selectedTextEditable: boolean;
  onSelectTextObject: (finding: RehearsalFinding) => void;
  onOpenSlide: (ordinal: number) => void;
  onPrepare: (
    finding: RehearsalFinding,
    destination: "text" | "notes" | "rewrite",
  ) => void;
}) {
  const [result, setResult] = useState<FindingsResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    setResult(null);
    if (!visible) return;
    let current = true;
    setBusy(true);
    setError(null);
    void window.presenterCopilot.core
      .request<FindingsResult>(
        "presentation.workspace.list_rehearsal_findings",
        {
          project_id: projectId,
          document_id: documentId,
          expected_revision_id: revisionId,
        },
      )
      .then(unwrapInvokeResult)
      .then((next) => {
        if (!current) return;
        if (
          next.document_id !== documentId ||
          next.revision_id !== revisionId ||
          !Array.isArray(next.findings) ||
          !Array.isArray(next.sessions)
        )
          throw new Error("The rehearsal findings could not be verified.");
        setResult(next);
      })
      .catch((caught) => {
        if (current)
          setError(
            caught instanceof Error
              ? caught.message
              : "Findings are unavailable.",
          );
      })
      .finally(() => {
        if (current) setBusy(false);
      });
    return () => {
      current = false;
    };
  }, [projectId, documentId, revisionId, visible, refresh]);
  async function dismiss(finding: RehearsalFinding, reopen = false) {
    setBusy(true);
    setError(null);
    try {
      unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "presentation.workspace.reject_rehearsal_finding",
          {
            project_id: projectId,
            document_id: documentId,
            expected_revision_id: revisionId,
            finding_id: finding.finding_id,
            reopen,
          },
        ),
      );
      setRefresh((value) => value + 1);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The finding could not be dismissed.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="pw-findings" aria-label="Rehearsal findings">
      <h4>Turn rehearsal into your next edit</h4>
      <RehearsalObjectionReview
        projectId={projectId}
        documentId={documentId}
        revisionId={revisionId}
        selectedSlide={selectedSlide}
        visible={visible}
        disabled={disabled}
        selectedTextEditable={selectedTextEditable}
        onPrepare={onPrepare}
        onOpenSlide={onOpenSlide}
      />
      <RehearsalObjectionComparison
        projectId={projectId}
        documentId={documentId}
        revisionId={revisionId}
        visible={visible}
        disabled={disabled}
      />
      <RehearsalSemanticReview
        projectId={projectId}
        documentId={documentId}
        revisionId={revisionId}
        selectedSlide={selectedSlide}
        visible={visible}
        disabled={disabled}
        selectedTextObjectId={selectedTextObjectId}
        selectedTextEditable={selectedTextEditable}
        onSelectTextObject={onSelectTextObject}
        onPrepare={onPrepare}
        onOpenSlide={onOpenSlide}
      />
      <p className="muted">
        Review what you said and marked. Findings retain their rehearsed
        revision and follow the same slide through reordering. Nothing changes
        until you preview and save an edit.
      </p>
      <button
        type="button"
        className="secondary-button"
        disabled={busy || disabled}
        onClick={() => setRefresh((value) => value + 1)}
      >
        Refresh findings
      </button>
      {busy ? <p role="status">Loading rehearsal findings…</p> : null}
      {result ? (
        <RehearsalComparison
          key={`${documentId}:${revisionId}:${refresh}`}
          projectId={projectId}
          documentId={documentId}
          revisionId={revisionId}
          sessions={result.sessions}
          disabled={disabled || busy}
          onOpenSlide={onOpenSlide}
        />
      ) : null}
      {result ? (
        <RehearsalCoverage
          key={`coverage:${documentId}:${revisionId}:${refresh}`}
          projectId={projectId}
          documentId={documentId}
          revisionId={revisionId}
          sessions={result.sessions}
          disabled={disabled || busy}
          onOpenSlide={onOpenSlide}
        />
      ) : null}
      {result ? (
        <RecurringObjections
          key={`objections:${projectId}:${documentId}:${revisionId}:${refresh}`}
          projectId={projectId}
          documentId={documentId}
          revisionId={revisionId}
          selectedSlide={selectedSlide}
          disabled={disabled || busy}
          onOpenSlide={onOpenSlide}
          onPrepare={onPrepare}
        />
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      {result && !result.sessions.length ? (
        <p>
          No completed rehearsals for this deck yet. Choose Rehearse to practice
          this revision.
        </p>
      ) : null}
      {result?.sessions.some((session) => !session.debrief_available) ? (
        <p>
          Some sessions have no debrief yet. Generate their debrief in Run to
          include them here.
        </p>
      ) : null}
      {result && result.sessions.length > 0 && !result.findings.length ? (
        <p>No review candidates were found in the available debriefs.</p>
      ) : null}
      {result?.findings.map((finding) => {
        const onSlide = finding.current_slide_number === selectedSlide;
        const editable =
          finding.disposition === "unreviewed" && onSlide && !disabled && !busy;
        return (
          <article className="pw-finding-card" key={finding.finding_id}>
            <strong>{labels[finding.kind]}</strong>
            <span className="muted">
              Revision {finding.source_revision_number} ·{" "}
              {finding.source_slide_number
                ? `Slide ${finding.source_slide_number}`
                : "No slide recorded"}{" "}
              · {finding.label.replaceAll("_", " ")}
            </span>
            {finding.quote ? (
              <blockquote>{finding.quote}</blockquote>
            ) : (
              <p>You marked this moment without a note.</p>
            )}
            <p className="muted">
              {finding.disposition === "applied"
                ? "Applied in a saved revision. Rehearse again to compare."
                : finding.disposition === "rejected"
                  ? "Dismissed by you."
                  : finding.current_slide_number === null
                    ? "The original slide is unavailable in this revision. This finding is read-only."
                    : !onSlide
                      ? `Open current slide ${finding.current_slide_number} to prepare an edit.`
                      : "Choose the text target in Text before preparing a replacement or rewrite."}
            </p>
            <div className="pw-finding-actions">
              {finding.current_slide_number !== null && !onSlide ? (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={disabled || busy}
                  onClick={() => onOpenSlide(finding.current_slide_number!)}
                >
                  Open slide {finding.current_slide_number}
                </button>
              ) : null}
              {finding.disposition === "rejected" ? (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={disabled || busy}
                  onClick={() => void dismiss(finding, true)}
                >
                  Undo dismissal
                </button>
              ) : null}
              {finding.disposition === "unreviewed" ? (
                <>
                  {finding.quote ? (
                    <>
                      {finding.kind === "spoken_explanation" ? (
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={!editable}
                          onClick={() => onPrepare(finding, "text")}
                        >
                          Use spoken wording
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={!editable}
                        onClick={() => onPrepare(finding, "notes")}
                      >
                        Add to notes draft
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={!editable}
                        onClick={() => onPrepare(finding, "rewrite")}
                      >
                        Prepare rewrite
                      </button>
                    </>
                  ) : null}
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={disabled || busy}
                    onClick={() => void dismiss(finding)}
                  >
                    Dismiss finding
                  </button>
                </>
              ) : null}
            </div>
          </article>
        );
      })}
      {result?.truncated ? (
        <p className="muted">
          Showing up to 300 findings from the ten latest completed sessions.
        </p>
      ) : null}
    </section>
  );
}
