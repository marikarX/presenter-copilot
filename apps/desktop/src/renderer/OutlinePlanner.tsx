import { useEffect, useRef, useState } from "react";
import { VoiceEditInstruction } from "./VoiceEditInstruction";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import {
  activeOutlineTurn,
  appendOutlineTurn,
  editOutlineTurn,
  emptyOutlineConversation,
  MAX_OUTLINE_TURNS,
  outlineChanges,
  selectOutlineTurn,
  type OutlineProposal,
  type OutlineRequest,
  type PlannedSlide,
  type OutlineConversation,
} from "./outline-conversation";

type OutlineSession = {
  record_token: string | null;
  updated_at: string | null;
  payload: { conversation: OutlineConversation; fields: OutlineRequest } | null;
};

export function OutlinePlanner({
  projectId,
  onBusyChange,
  onUse,
}: {
  projectId: string;
  onBusyChange: (busy: boolean) => void;
  onUse: (
    title: string,
    outline: string,
    providerRunId: string,
    evidenceIds: string[][],
  ) => void;
}) {
  const [objective, setObjective] = useState("");
  const [audience, setAudience] = useState("");
  const [briefing, setBriefing] = useState("");
  const [slideCount, setSlideCount] = useState(6);
  const [instruction, setInstruction] = useState("");
  const [conversation, setConversation] = useState(emptyOutlineConversation);
  const currentTurn = activeOutlineTurn(conversation);
  const proposal = currentTurn?.draft ?? null;
  const changes =
    proposal && currentTurn?.baseline
      ? outlineChanges(currentTurn.baseline, proposal)
      : [];
  const manuallyEdited =
    proposal && currentTurn
      ? outlineChanges(currentTurn.original, proposal).length > 0
      : false;
  const [busy, setBusy] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [savedSession, setSavedSession] = useState<OutlineSession | null>(null);
  const locked = busy || voiceBusy || sessionBusy;
  useEffect(() => {
    onBusyChange(locked);
  }, [locked, onBusyChange]);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  const requestBusy = useRef(false);
  const generation = useRef(0);
  const draftHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (proposal?.provider_run_id) {
      draftHeading.current?.focus();
      draftHeading.current?.scrollIntoView({ block: "start" });
    }
  }, [proposal?.provider_run_id]);
  useEffect(() => {
    generation.current++;
    mounted.current = true;
    requestBusy.current = false;
    setConversation(emptyOutlineConversation());
    setObjective("");
    setAudience("");
    setBriefing("");
    setSlideCount(6);
    setInstruction("");
    setError(null);
    setBusy(false);
    setSavedSession(null);
    setSessionBusy(true);
    const loadGeneration = generation.current;
    void window.presenterCopilot.core
      .request<OutlineSession>("presentation.workspace.get_outline_session", {
        project_id: projectId,
      })
      .then((result) => {
        if (!mounted.current || generation.current !== loadGeneration) return;
        setSavedSession(unwrapInvokeResult(result));
      })
      .catch((caught) => {
        if (mounted.current && generation.current === loadGeneration)
          setError(
            isCoreError(caught)
              ? caught.message
              : "The saved drafting session could not be loaded.",
          );
      })
      .finally(() => {
        if (mounted.current && generation.current === loadGeneration)
          setSessionBusy(false);
      });
    return () => {
      mounted.current = false;
      generation.current++;
      requestBusy.current = false;
    };
  }, [projectId]);

  async function saveSession(clear = false) {
    if (locked || !savedSession || (!clear && !conversation.turns.length))
      return;
    setSessionBusy(true);
    const requestedGeneration = generation.current;
    setError(null);
    try {
      const result = unwrapInvokeResult(
        await window.presenterCopilot.core.request<OutlineSession>(
          clear
            ? "presentation.workspace.clear_outline_session"
            : "presentation.workspace.save_outline_session",
          {
            project_id: projectId,
            expected_record_token: savedSession.record_token,
            ...(!clear
              ? {
                  payload: {
                    conversation,
                    fields: {
                      objective,
                      audience,
                      briefing,
                      slide_count: slideCount,
                      instruction,
                    },
                  },
                }
              : {}),
          },
        ),
      );
      if (mounted.current && generation.current === requestedGeneration)
        setSavedSession(result);
    } catch (caught) {
      if (mounted.current && generation.current === requestedGeneration)
        setError(
          isCoreError(caught)
            ? caught.message
            : "The drafting session could not be saved.",
        );
    } finally {
      if (mounted.current && generation.current === requestedGeneration)
        setSessionBusy(false);
    }
  }
  function resumeSession() {
    if (locked || !savedSession?.payload) return;
    const { conversation: restored, fields } = structuredClone(
      savedSession.payload,
    );
    setConversation(restored);
    setObjective(fields.objective);
    setAudience(fields.audience);
    setBriefing(fields.briefing);
    setSlideCount(fields.slide_count);
    setInstruction(fields.instruction);
    setError(null);
  }
  async function reloadSession() {
    if (locked) return;
    const requestedGeneration = generation.current;
    setSessionBusy(true);
    setError(null);
    try {
      const result = unwrapInvokeResult(
        await window.presenterCopilot.core.request<OutlineSession>(
          "presentation.workspace.get_outline_session",
          { project_id: projectId },
        ),
      );
      if (mounted.current && generation.current === requestedGeneration)
        setSavedSession(result);
    } catch (caught) {
      if (mounted.current && generation.current === requestedGeneration)
        setError(
          isCoreError(caught)
            ? caught.message
            : "The saved drafting session could not be loaded.",
        );
    } finally {
      if (mounted.current && generation.current === requestedGeneration)
        setSessionBusy(false);
    }
  }

  async function plan() {
    if (
      voiceBusy ||
      requestBusy.current ||
      conversation.turns.length >= MAX_OUTLINE_TURNS
    )
      return;
    if (sessionBusy) return;
    requestBusy.current = true;
    const requestGeneration = generation.current;
    const request: OutlineRequest = {
      objective,
      audience,
      briefing,
      slide_count: slideCount,
      instruction:
        instruction.trim() || "Plan a clear narrative for this presentation.",
    };
    setBusy(true);
    setError(null);
    try {
      const result = unwrapInvokeResult(
        await window.presenterCopilot.core.request<OutlineProposal>(
          "presentation.workspace.propose_outline",
          {
            project_id: projectId,
            ...request,
            ...(proposal
              ? {
                  prior_outline: {
                    title: proposal.title,
                    rationale: proposal.rationale,
                    slides: proposal.slides,
                  },
                }
              : {}),
          },
        ),
      );
      if (!mounted.current || generation.current !== requestGeneration) return;
      if (
        !result ||
        result.requires_user_review !== true ||
        !/^[0-9a-f-]{36}$/i.test(result.provider_run_id) ||
        typeof result.title !== "string" ||
        !result.title.trim() ||
        typeof result.rationale !== "string" ||
        !Array.isArray(result.slides) ||
        result.slides.length !== slideCount ||
        !Array.isArray(result.evidence) ||
        result.slides.some(
          (slide) =>
            typeof slide.title !== "string" ||
            typeof slide.notes !== "string" ||
            !Array.isArray(slide.bullets) ||
            slide.bullets.some((point) => typeof point !== "string") ||
            !Array.isArray(slide.evidence_ids) ||
            slide.evidence_ids.some((id) => typeof id !== "string"),
        ) ||
        result.evidence.some(
          (item) =>
            typeof item.evidence_id !== "string" ||
            typeof item.text !== "string",
        )
      )
        throw new Error("The outline proposal could not be verified.");
      setConversation(appendOutlineTurn(conversation, result, request));
      setInstruction("");
    } catch (caught) {
      if (mounted.current && generation.current === requestGeneration)
        setError(
          isCoreError(caught)
            ? caught.message
            : caught instanceof Error
              ? caught.message
              : "The outline could not be planned.",
        );
    } finally {
      if (mounted.current && generation.current === requestGeneration) {
        requestBusy.current = false;
        setBusy(false);
      }
    }
  }

  function updateSlide(index: number, update: Partial<PlannedSlide>) {
    if (requestBusy.current || voiceBusy) return;
    setConversation((current) => {
      const draft = activeOutlineTurn(current)?.draft;
      return draft
        ? editOutlineTurn(current, {
            slides: draft.slides.map((slide, ordinal) =>
              ordinal === index ? { ...slide, ...update } : slide,
            ),
          })
        : current;
    });
  }

  function restoreDraft(runId: string) {
    if (requestBusy.current || voiceBusy) return;
    const selected = selectOutlineTurn(conversation, runId);
    const turn = activeOutlineTurn(selected)!;
    setConversation(selected);
    setObjective(turn.request.objective);
    setAudience(turn.request.audience);
    setBriefing(turn.request.briefing);
    setSlideCount(turn.request.slide_count);
    setInstruction("");
    setError(null);
  }

  return (
    <section className="pw-outline-planner" aria-label="Plan with Copilot">
      <p className="muted">
        Describe the decision and your audience. Copilot uses relevant project
        sources and approved explanations under your project privacy settings.
        Review every claim before creating slides.
      </p>
      <section aria-label="Saved drafting session">
        <p className="muted">
          Save one drafting session in this project to resume after closing or
          restarting. Saving replaces its saved copy; it does not call a
          provider or create slides. Saved source excerpts reflect planning
          time. Review current facts before creating a presentation.
        </p>
        <div className="button-row">
          <button
            type="button"
            className="secondary-button"
            disabled={locked || !savedSession || !conversation.turns.length}
            onClick={() => void saveSession()}
          >
            Save drafting session
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={locked || !savedSession?.payload}
            onClick={resumeSession}
          >
            Resume saved drafting session
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={locked || !savedSession?.payload}
            onClick={() => void saveSession(true)}
          >
            Remove saved copy
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={locked}
            onClick={() => void reloadSession()}
          >
            Reload saved copy
          </button>
        </div>
        <p role="status">
          {sessionBusy
            ? "Accessing saved drafting session…"
            : !savedSession
              ? "Saved session status is unavailable. Reload the saved copy."
              : savedSession.payload
                ? "A drafting session is saved locally in this project."
                : "No saved drafting session in this project."}
        </p>
      </section>
      {conversation.turns.length ? (
        <details className="pw-outline-conversation" open>
          <summary>
            Draft conversation · {conversation.turns.length} of{" "}
            {MAX_OUTLINE_TURNS}
          </summary>
          <p className="muted">
            Unsaved drafts stay in this dialog until you close it or switch
            modes. Select an earlier draft to restore its edited content,
            briefing and source review; refining it starts a new branch.
            Creating a presentation still requires review.
          </p>
          <ol>
            {conversation.turns.map((turn) => {
              const parent = conversation.turns.find(
                (entry) => entry.original.provider_run_id === turn.parentRunId,
              );
              const selected =
                turn.original.provider_run_id === conversation.activeRunId;
              return (
                <li key={turn.original.provider_run_id}>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={locked || selected}
                    aria-pressed={selected}
                    aria-label={`Restore draft ${turn.ordinal}`}
                    onClick={() => restoreDraft(turn.original.provider_run_id)}
                  >
                    Draft {turn.ordinal}
                    {selected ? " · Current" : ""}: {turn.draft.title}
                  </button>
                  <p>
                    {parent
                      ? `Refined draft ${parent.ordinal}`
                      : "Initial outline"}
                    : {turn.request.instruction}
                  </p>
                </li>
              );
            })}
          </ol>
          {conversation.turns.length >= MAX_OUTLINE_TURNS ? (
            <p role="status">
              Conversation limit reached. Review any saved draft here, or close
              this dialog and start another conversation.
            </p>
          ) : null}
        </details>
      ) : null}
      <details className="pw-planner-brief" open={!proposal}>
        <summary>Your briefing · {slideCount} slides</summary>
        <div className="pw-brief-grid">
          <label>
            Presentation objective
            <input
              value={objective}
              maxLength={500}
              disabled={locked}
              onChange={(event) => setObjective(event.target.value)}
              placeholder="What decision or outcome do you need?"
            />
          </label>
          <label>
            Audience for this presentation
            <input
              value={audience}
              maxLength={300}
              disabled={locked}
              onChange={(event) => setAudience(event.target.value)}
              placeholder="Who needs to understand or decide?"
            />
          </label>
        </div>
        <label>
          Your briefing
          <textarea
            aria-label="Your briefing"
            rows={4}
            value={briefing}
            maxLength={2000}
            disabled={locked}
            onChange={(event) => setBriefing(event.target.value)}
            placeholder="Your reasoning, constraints, and points to include. Add supporting documents to the project for sourced claims."
          />
        </label>
        <label>
          Number of slides
          <input
            type="number"
            min={1}
            max={40}
            value={slideCount}
            disabled={locked}
            onChange={(event) => setSlideCount(Number(event.target.value))}
          />
        </label>
      </details>
      {proposal ? (
        <>
          <div className="pw-plan-summary">
            <h3 ref={draftHeading} tabIndex={-1}>
              Draft for your review
            </h3>
            <p>{proposal.rationale}</p>
            <span className="muted">
              {proposal.model_id} · Draft {currentTurn?.ordinal} · Nothing has
              been created yet
            </span>
            {manuallyEdited ? (
              <p className="muted">
                This draft includes your edits after the provider response.
              </p>
            ) : null}
          </div>
          {currentTurn?.baseline ? (
            <details className="pw-outline-changes">
              <summary>
                Changes from the request baseline · {changes.length}
              </summary>
              <p className="muted">
                Compared with the edited draft sent for this refinement. Slides
                are compared by position; moved slides can appear as several
                changes. Current manual edits are included.
              </p>
              {changes.length ? (
                <dl>
                  {changes.map((change) => (
                    <div key={change.label}>
                      <dt>{change.label}</dt>
                      <dd>
                        <strong>Before</strong>
                        <p>{change.before || "Empty"}</p>
                      </dd>
                      <dd>
                        <strong>Current draft</strong>
                        <p>{change.after || "Empty"}</p>
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p>No content changes from the request baseline.</p>
              )}
            </details>
          ) : null}
          <label>
            Draft presentation title
            <input
              value={proposal.title}
              maxLength={120}
              disabled={locked}
              onChange={(event) => {
                const title = event.target.value;
                setConversation((current) =>
                  editOutlineTurn(current, { title }),
                );
              }}
            />
          </label>
          <ol className="pw-planned-slides">
            {proposal.slides.map((slide, index) => (
              <li key={index}>
                <strong>Slide {index + 1}</strong>
                <label>
                  Slide {index + 1} title
                  <input
                    value={slide.title}
                    maxLength={120}
                    disabled={locked}
                    onChange={(event) =>
                      updateSlide(index, { title: event.target.value })
                    }
                  />
                </label>
                <label>
                  Slide {index + 1} points
                  <textarea
                    rows={3}
                    value={slide.bullets.join("\n")}
                    aria-label={`Slide ${index + 1} points`}
                    maxLength={1608}
                    disabled={locked}
                    onChange={(event) =>
                      updateSlide(index, {
                        bullets: event.target.value.split("\n"),
                      })
                    }
                  />
                </label>
                <details>
                  <summary>Speaker notes and source review</summary>
                  <label>
                    Slide {index + 1} notes
                    <textarea
                      aria-label={`Slide ${index + 1} notes`}
                      rows={3}
                      value={slide.notes}
                      maxLength={4000}
                      disabled={locked}
                      onChange={(event) =>
                        updateSlide(index, { notes: event.target.value })
                      }
                    />
                  </label>
                  {slide.evidence_ids.length ? (
                    slide.evidence_ids.map((id) => (
                      <blockquote key={id}>
                        {proposal.evidence.find(
                          (item) => item.evidence_id === id,
                        )?.text ?? "Source unavailable"}
                        <small>Evidence reference: {id}</small>
                      </blockquote>
                    ))
                  ) : (
                    <p className="muted">
                      No project evidence cited for this slide. Verify factual
                      claims against your briefing and supporting material.
                    </p>
                  )}
                </details>
              </li>
            ))}
          </ol>
          <label>
            Refine this draft
            <textarea
              aria-label="Refine this draft"
              rows={2}
              value={instruction}
              maxLength={500}
              disabled={locked}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder="For example: move the decision first and shorten the explanation."
            />
          </label>
        </>
      ) : null}
      <VoiceEditInstruction
        key={proposal ? "refinement" : "briefing"}
        projectId={projectId}
        outlinePurpose={proposal ? "refinement" : "briefing"}
        scopeChoice="deck"
        disabled={busy || sessionBusy}
        onBusyChange={setVoiceBusy}
        onUse={proposal ? setInstruction : setBriefing}
      />
      {error ? <p role="alert">{error}</p> : null}
      <div className="pw-create-actions">
        <button
          type="button"
          className="secondary-button"
          disabled={
            locked ||
            conversation.turns.length >= MAX_OUTLINE_TURNS ||
            !objective.trim() ||
            !audience.trim() ||
            !Number.isInteger(slideCount) ||
            slideCount < 1 ||
            slideCount > 40 ||
            (proposal !== null && !instruction.trim())
          }
          onClick={() => void plan()}
        >
          {busy
            ? "Planning outline…"
            : proposal
              ? "Refine outline"
              : "Propose outline"}
        </button>
        {proposal ? (
          <button
            type="button"
            className="primary-button"
            disabled={locked}
            onClick={() => {
              const outline = proposal.slides
                .map((slide) => {
                  const references = slide.evidence_ids.length
                    ? `Evidence references to review: ${slide.evidence_ids.join(", ")}`
                    : "";
                  const notes = [slide.notes, references]
                    .filter(Boolean)
                    .join("\n\n");
                  return [
                    `# ${slide.title}`,
                    ...slide.bullets
                      .filter((point) => point.trim())
                      .map((point) => `- ${point}`),
                    ...notes
                      .split("\n")
                      .filter(Boolean)
                      .map((line) => `Notes: ${line}`),
                  ].join("\n");
                })
                .join("\n\n");
              onUse(
                proposal.title,
                outline,
                proposal.provider_run_id,
                proposal.slides.map((slide) => [...slide.evidence_ids]),
              );
            }}
          >
            Review this outline
          </button>
        ) : null}
      </div>
    </section>
  );
}
