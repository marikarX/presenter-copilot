import { useEffect, useRef, useState } from "react";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";

const FIELDS = [
  ["objective", "Presentation objective", 1000],
  ["target_audience", "Target audience", 1000],
  ["desired_action", "Desired decision or action", 1000],
  ["thesis", "Central thesis", 1000],
  ["narrative_arc", "Narrative arc", 2000],
  ["constraints", "Presentation constraints", 2000],
] as const;
type Field = (typeof FIELDS)[number][0];
type Fields = Record<Field, string>;
export type NarrativeContext = {
  revision_id: string;
  source_revision_id: string | null;
  status: "reviewed" | "needs_review" | "missing";
  fields: Fields;
  shortened_fields: string[];
  lineage_truncated: boolean;
};
type Narrative = Omit<NarrativeContext, "shortened_fields"> & {
  record_token: string | null;
};
type NarrativeProposal = {
  revision_id: string;
  expected_record_token: string | null;
  summary: string;
  fields: Fields;
  provider_id: string;
  model_id: string;
  analysis_scope: {
    start_slide: number;
    end_slide: number;
    total_slides: number;
    covered_slide_count: number;
    omitted_slide_count: number;
    shortened_slide_numbers: number[];
  };
  findings: Array<{
    slide_id: string;
    slide_number: number;
    role: string;
    takeaway: string;
    issue: string;
    action: string;
    evidence_ids: string[];
  }>;
  evidence: Array<{ evidence_id: string; text: string }>;
};
const EMPTY: Fields = {
  objective: "",
  target_audience: "",
  desired_action: "",
  thesis: "",
  narrative_arc: "",
  constraints: "",
};

export function PresentationNarrative({
  projectId,
  documentId,
  revisionId,
  disabled,
  onOpenSlide,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  disabled: boolean;
  onOpenSlide: (ordinal: number, takeaway?: string) => void;
}) {
  const [saved, setSaved] = useState<Narrative | null>(null);
  const [draft, setDraft] = useState<Fields>(EMPTY);
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [proposal, setProposal] = useState<NarrativeProposal | null>(null);
  const [proposalUsed, setProposalUsed] = useState(false);
  const [proposing, setProposing] = useState(false);
  const [instruction, setInstruction] = useState(
    "Analyze the narrative and suggest clearer deck intent.",
  );
  const [startSlide, setStartSlide] = useState(1);
  const [slideCount, setSlideCount] = useState(40);
  const alive = useRef(true);
  const scope = {
    project_id: projectId,
    document_id: documentId,
    revision_id: revisionId,
  };
  const dirty =
    saved !== null && JSON.stringify(draft) !== JSON.stringify(saved.fields);
  function fail(caught: unknown) {
    if (alive.current)
      setError(isCoreError(caught) ? caught.message : String(caught));
  }
  function accept(value: Narrative) {
    if (
      value.revision_id !== revisionId ||
      FIELDS.some(([key]) => typeof value.fields[key] !== "string")
    )
      throw new Error("Narrative response does not match this revision.");
    if (!alive.current) return;
    setProposal(null);
    setSaved(value);
    setDraft(value.fields);
    setReviewed(false);
    setError("");
  }
  async function load() {
    setBusy(true);
    try {
      accept(
        unwrapInvokeResult<Narrative>(
          await window.presenterCopilot.core.request(
            "presentation.workspace.get_narrative",
            scope,
          ),
        ),
      );
    } catch (caught) {
      fail(caught);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  useEffect(() => {
    alive.current = true;
    void load();
    return () => {
      alive.current = false;
    };
    // Parent remounts on project, document and revision changes; panel switches retain drafts.
  }, []);
  async function save() {
    if (!saved || !reviewed || busy || disabled) return;
    setBusy(true);
    try {
      accept(
        unwrapInvokeResult<Narrative>(
          await window.presenterCopilot.core.request(
            "presentation.workspace.save_narrative",
            {
              ...scope,
              fields: draft,
              reviewed: true,
              expected_record_token: saved.record_token,
            },
          ),
        ),
      );
    } catch (caught) {
      fail(caught);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function suggest() {
    if (!saved || busy || disabled) return;
    setBusy(true);
    setProposing(true);
    setError("");
    setProposal(null);
    setReviewed(false);
    try {
      const result = unwrapInvokeResult<NarrativeProposal>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.propose_narrative",
          {
            ...scope,
            fields: draft,
            expected_record_token: saved.record_token,
            instruction,
            start_slide: startSlide,
            slide_count: slideCount,
          },
        ),
      );
      if (
        result.revision_id !== revisionId ||
        result.expected_record_token !== saved.record_token ||
        FIELDS.some(([key]) => typeof result.fields[key] !== "string")
      )
        throw new Error(
          "Narrative suggestion does not match this revision and saved intent.",
        );
      if (alive.current) {
        setProposal(result);
        setProposalUsed(false);
      }
    } catch (caught) {
      fail(caught);
    } finally {
      if (alive.current) {
        setBusy(false);
        setProposing(false);
      }
    }
  }
  return (
    <section className="pw-narrative-panel" aria-label="Presentation narrative">
      <h3>Presentation narrative</h3>
      <p>
        Define the intent of this deck. Copilot and Challenge use saved intent
        alongside the selected slides. These fields describe your intent; they
        are not source evidence.
      </p>
      {saved ? (
        <p role="status">
          {saved.status === "reviewed"
            ? "Narrative reviewed for this revision."
            : saved.status === "needs_review"
              ? "Inherited narrative: review it against this revision before saving."
              : "No narrative saved for this revision."}
        </p>
      ) : null}
      {saved?.lineage_truncated ? (
        <p>Earlier narrative history is incomplete.</p>
      ) : null}
      {dirty ? <p role="status">Unsaved narrative changes.</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      <fieldset disabled={disabled || busy || saved === null}>
        {FIELDS.map(([key, label, limit]) => (
          <label key={key}>
            {label}
            <textarea
              aria-label={label}
              rows={key === "narrative_arc" ? 5 : 3}
              maxLength={limit}
              value={draft[key]}
              onChange={(event) => {
                setDraft((value) => ({ ...value, [key]: event.target.value }));
                setReviewed(false);
                setProposal(null);
              }}
            />
          </label>
        ))}
        <label className="pw-narrative-review">
          <input
            type="checkbox"
            checked={reviewed}
            onChange={(event) => setReviewed(event.target.checked)}
          />
          I reviewed this narrative for the current deck revision
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={!reviewed}
          onClick={() => void save()}
        >
          {busy
            ? proposing
              ? "Working…"
              : "Saving narrative…"
            : "Save reviewed narrative"}
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={() => {
            setDraft(EMPTY);
            setReviewed(false);
            setProposal(null);
          }}
        >
          Clear narrative draft
        </button>
      </fieldset>
      <button
        type="button"
        className="secondary-button"
        disabled={disabled || busy}
        onClick={() => void load()}
      >
        Reload saved narrative
      </button>
      <section
        className="pw-narrative-analysis"
        aria-label="Narrative suggestions"
      >
        <h4>Review narrative with Copilot</h4>
        <p>
          On request, the selected reasoning provider receives this draft
          intent, bounded native slide text and notes, and allowed grounding
          when privacy permits. Suggestions do not change your draft, slide
          content or saved labels.
        </p>
        <fieldset disabled={disabled || busy || !saved}>
          <label>
            Narrative analysis instruction
            <textarea
              aria-label="Narrative analysis instruction"
              value={instruction}
              maxLength={500}
              onChange={(event) => {
                setInstruction(event.target.value);
                setProposal(null);
              }}
            />
          </label>
          <label>
            Analysis start slide
            <input
              type="number"
              aria-label="Analysis start slide"
              min={1}
              max={5000}
              value={startSlide}
              onChange={(event) => {
                setStartSlide(Number(event.target.value));
                setProposal(null);
              }}
            />
          </label>
          <label>
            Analysis slide count
            <input
              type="number"
              aria-label="Analysis slide count"
              min={1}
              max={40}
              value={slideCount}
              onChange={(event) => {
                setSlideCount(Number(event.target.value));
                setProposal(null);
              }}
            />
          </label>
          <button
            type="button"
            className="secondary-button"
            onClick={() => void suggest()}
          >
            {proposing ? "Analyzing narrative…" : "Suggest narrative from deck"}
          </button>
        </fieldset>
        {proposal ? (
          <section aria-label="Narrative suggestion review">
            <p>
              {proposal.provider_id} · {proposal.model_id}
            </p>
            <p>{proposal.summary}</p>
            <p>
              Text and notes from slides {proposal.analysis_scope.start_slide}–
              {proposal.analysis_scope.end_slide} of{" "}
              {proposal.analysis_scope.total_slides}. Visual content was not
              analyzed.
            </p>
            {proposal.analysis_scope.omitted_slide_count ? (
              <p>
                Partial deck coverage:{" "}
                {proposal.analysis_scope.omitted_slide_count} slides omitted.
              </p>
            ) : null}
            {proposal.analysis_scope.shortened_slide_numbers.length ? (
              <p>
                Text or notes shortened on slides{" "}
                {proposal.analysis_scope.shortened_slide_numbers.join(", ")}.
              </p>
            ) : null}
            <dl>
              {FIELDS.map(([key, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{proposal.fields[key] || "Not proposed"}</dd>
                </div>
              ))}
            </dl>
            <button
              type="button"
              className="secondary-button"
              disabled={disabled || busy || proposalUsed}
              onClick={() => {
                setDraft(proposal.fields);
                setReviewed(false);
                setProposalUsed(true);
              }}
            >
              Use suggested narrative
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={disabled || busy}
              onClick={() => setProposal(null)}
            >
              Discard narrative suggestion
            </button>
            {proposalUsed ? (
              <p>
                Suggestion copied into the draft. Review and save it explicitly.
              </p>
            ) : null}
            <p>
              Slide roles and takeaways below are unconfirmed suggestions; no
              slide purpose was saved.
            </p>
            {proposal.findings.map((finding) => (
              <article key={finding.slide_id}>
                <h4>
                  Slide {finding.slide_number} · Suggested role: {finding.role}
                </h4>
                <p>{finding.takeaway}</p>
                <p>{finding.issue}</p>
                <p>{finding.action}</p>
                {finding.evidence_ids.map((id) => (
                  <blockquote key={id}>
                    {
                      proposal.evidence.find((item) => item.evidence_id === id)
                        ?.text
                    }
                  </blockquote>
                ))}
                <button
                  type="button"
                  className="secondary-button"
                  disabled={disabled || busy}
                  onClick={() =>
                    onOpenSlide(finding.slide_number, finding.takeaway)
                  }
                >
                  Review narrative finding on slide {finding.slide_number}
                </button>
              </article>
            ))}
          </section>
        ) : null}
      </section>
      <p>
        Edits to the deck carry earlier intent forward for review. Saving blank
        fields clears intent for this revision. Narrative saves do not change
        slide content.
      </p>
    </section>
  );
}
