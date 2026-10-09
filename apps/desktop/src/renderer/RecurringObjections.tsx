import { useEffect, useRef, useState } from "react";
import { unwrapInvokeResult } from "../shared/protocol";
import type { RehearsalFinding } from "./RehearsalFindings";

type Group = {
  group_id: string;
  slide_id: string;
  current_slide_number: number | null;
  note: string;
  session_count: number;
  occurrence_count: number;
  dispositions: Record<string, number>;
  occurrences: RehearsalFinding[];
  occurrences_truncated: boolean;
  selected_finding: RehearsalFinding;
};
type Result = {
  document_id: string;
  revision_id: string;
  groups: Group[];
  total_groups: number;
  offset: number;
  limit: number;
  sessions_checked: number;
  truncated: boolean;
  ungrouped_objections: number;
};
export function RecurringObjections({
  projectId,
  documentId,
  revisionId,
  selectedSlide,
  disabled,
  onOpenSlide,
  onPrepare,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  selectedSlide: number;
  disabled: boolean;
  onOpenSlide: (ordinal: number) => void;
  onPrepare: (
    finding: RehearsalFinding,
    destination: "text" | "notes" | "rewrite",
  ) => void;
}) {
  const [result, setResult] = useState<Result | null>(null);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  async function inspect(offset = 0) {
    const request = ++generation.current;
    setBusy(true);
    setError(null);
    setResult(null);
    setSelected({});
    try {
      const next = unwrapInvokeResult(
        await window.presenterCopilot.core.request<Result>(
          "presentation.workspace.recurring_objections",
          {
            project_id: projectId,
            document_id: documentId,
            expected_revision_id: revisionId,
            offset,
            limit: 20,
          },
        ),
      );
      if (request !== generation.current) return;
      if (
        next.document_id !== documentId ||
        next.revision_id !== revisionId ||
        next.offset !== offset ||
        next.limit !== 20 ||
        !Number.isSafeInteger(next.total_groups) ||
        next.total_groups < 0 ||
        !Array.isArray(next.groups) ||
        next.groups.length > 20 ||
        next.groups.some(
          (group) =>
            !group ||
            typeof group.group_id !== "string" ||
            typeof group.note !== "string" ||
            !Number.isSafeInteger(group.session_count) ||
            group.session_count < 2 ||
            !Array.isArray(group.occurrences) ||
            group.occurrences.length > 5 ||
            !group.occurrences.some(
              (finding) =>
                finding.finding_id === group.selected_finding?.finding_id,
            ) ||
            group.occurrences.some(
              (finding) =>
                finding.kind !== "marked" ||
                finding.label !== "objection" ||
                finding.slide_id !== group.slide_id ||
                finding.current_slide_number !== group.current_slide_number,
            ),
        )
      )
        throw new Error("The recurring objections could not be verified.");
      setResult(next);
    } catch (caught) {
      if (request === generation.current)
        setError(
          caught instanceof Error
            ? caught.message
            : "Recurring objections are unavailable.",
        );
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }
  return (
    <section
      aria-label="Recurring rehearsal objections"
      className="pw-recurring-objections"
    >
      <h4>Review recurring objections</h4>
      <p className="muted">
        Mark objections with a note during Run. Matching wording on the same
        slide across distinct rehearsals appears here. Case and punctuation
        remain distinct; extra spaces are ignored. Each original observation
        keeps its own review and edit history.
      </p>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled || busy}
        onClick={() => void inspect()}
      >
        Find recurring objections
      </button>
      {busy ? (
        <p role="status">Checking objections across ended rehearsals…</p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      {result ? (
        <>
          <p>
            {result.total_groups} recurring objections in{" "}
            {result.sessions_checked} rehearsals checked · page{" "}
            {Math.floor(result.offset / 20) + 1} of{" "}
            {Math.max(1, Math.ceil(result.total_groups / 20))}.
          </p>
          <p className="muted">
            Ungrouped marked objections: {result.ungrouped_objections}. No
            matching note/slide was found across distinct rehearsals. Similar
            wording is not automatically combined. The latest ten ended
            rehearsals with available debrief observations are checked.
          </p>
          {result.truncated ? (
            <p>
              Older sessions or bounded observations are excluded. These counts
              do not cover every rehearsal.
            </p>
          ) : null}
          {!result.groups.length ? (
            <p>
              No repeated matching objections were found in these rehearsals.
            </p>
          ) : null}
          {result.groups.map((group) => {
            const finding =
              group.occurrences.find(
                (item) => item.finding_id === selected[group.group_id],
              ) ?? group.selected_finding;
            const editable =
              !disabled &&
              !busy &&
              finding.disposition === "unreviewed" &&
              finding.current_slide_number === selectedSlide;
            return (
              <article
                className="pw-finding-card"
                key={group.group_id}
                data-group-id={group.group_id}
              >
                <strong>
                  {group.current_slide_number === null
                    ? "Original slide removed"
                    : `Current slide ${group.current_slide_number}`}
                </strong>
                <blockquote>{group.note}</blockquote>
                <p>
                  {group.occurrence_count} observations across{" "}
                  {group.session_count} distinct rehearsals ·{" "}
                  {group.dispositions.unreviewed} unreviewed ·{" "}
                  {group.dispositions.applied} applied ·{" "}
                  {group.dispositions.rejected} dismissed.
                </p>
                <label>
                  Observation to review
                  <select
                    aria-label="Objection observation"
                    value={finding.finding_id}
                    disabled={disabled || busy}
                    onChange={(event) =>
                      setSelected((previous) => ({
                        ...previous,
                        [group.group_id]: event.target.value,
                      }))
                    }
                  >
                    {group.occurrences.map((item) => (
                      <option key={item.finding_id} value={item.finding_id}>
                        Rehearsed revision {item.source_revision_number} · slide{" "}
                        {item.source_slide_number} · {item.disposition}
                      </option>
                    ))}
                  </select>
                </label>
                {group.occurrences_truncated ? (
                  <p className="muted">
                    Showing up to five original observations, including the next
                    unreviewed one. Saving an edit applies only to the selected
                    observation.
                  </p>
                ) : null}
                <blockquote>{finding.quote}</blockquote>
                <p className="muted">
                  Original wording from rehearsed revision{" "}
                  {finding.source_revision_number}, slide{" "}
                  {finding.source_slide_number}. Preparing a draft makes no
                  saved change. Review and save it separately; other occurrences
                  keep their status.
                </p>
                {finding.disposition !== "unreviewed" ? (
                  <p>
                    {finding.disposition === "applied"
                      ? "This observation was applied in a saved revision."
                      : "This observation was dismissed."}
                  </p>
                ) : null}
                {group.current_slide_number !== null &&
                group.current_slide_number !== selectedSlide ? (
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={disabled || busy}
                    onClick={() => onOpenSlide(group.current_slide_number!)}
                  >
                    Open objection slide {group.current_slide_number}
                  </button>
                ) : null}
                {group.current_slide_number === null ? (
                  <p>
                    The original slide is absent from this revision. These
                    observations are read-only.
                  </p>
                ) : null}
                <button
                  type="button"
                  className="secondary-button"
                  disabled={!editable}
                  onClick={() => onPrepare(finding, "notes")}
                >
                  Prepare objection notes
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={!editable}
                  onClick={() => onPrepare(finding, "rewrite")}
                >
                  Prepare objection rewrite
                </button>
              </article>
            );
          })}
          <button
            type="button"
            className="secondary-button"
            disabled={disabled || busy || result.offset === 0}
            onClick={() => void inspect(Math.max(0, result.offset - 20))}
          >
            Previous objection groups
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={
              disabled || busy || result.offset + 20 >= result.total_groups
            }
            onClick={() => void inspect(result.offset + 20)}
          >
            Next objection groups
          </button>
        </>
      ) : null}
    </section>
  );
}
