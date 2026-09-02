import { useCallback, useEffect, useState } from "react";

import {
  type JsonObject,
  type KnowledgeItem,
  type ProviderStatus,
  type ReadyProjectSummary,
  type RendererCoreMethod,
  type Session,
  type SpeakerEvidence,
  type SpeakerProfile,
  type TeachCandidate,
  unwrapInvokeResult,
} from "../shared/protocol";

type TeachPanelProps = {
  project: ReadyProjectSummary;
};

type SessionListResult = { sessions: Session[] };
type SessionResult = { session: Session };
type KnowledgeListResult = { knowledge_items: KnowledgeItem[] };
type SpeakerProfileResult = { profile: SpeakerProfile };
type SpeakerEvidenceResult = { evidence: SpeakerEvidence[] };
type ProviderListResult = { providers: ProviderStatus[] };

type TeachPromptResult = {
  session_id: string;
  state: string;
  utterance_id: string;
  question: string;
  focus: string;
  route: string;
  reasoning?: {
    route?: string;
    status?: string;
    provider_id?: string;
    model_id?: string;
    reason?: string;
    provider_error?: { code?: string; retryable?: boolean };
  };
  context_manifest?: {
    provider_id?: string;
    privacy_mode?: string;
    classes_sent?: string[];
    bounded_context_chars?: number;
  };
};

type TeachSubmitResult = {
  session_id: string;
  source_utterance_id: string;
  direct_save_available: boolean;
  route: string;
  local_only: boolean;
  candidate: TeachCandidate | null;
  reasoning?: {
    route?: string;
    status?: string;
    provider_id?: string;
    model_id?: string;
    provider_error?: { code?: string; retryable?: boolean };
  };
};

type TeachDiscardResult = {
  project_id: string;
  session_id: string;
  source_utterance_id: string;
  discarded: boolean;
  state: string;
};

type TeachStateResult = {
  session_id: string;
  state: string;
  prompt: { utterance_id: string; text: string } | null;
  pending_answer: { source_utterance_id: string; text: string } | null;
  candidate: TeachCandidate | null;
};

const EVIDENCE_TYPES = [
  "preferred_phrase",
  "explanation_pattern",
  "analogy",
  "vocabulary",
  "coaching_preference",
  "rejected_pattern",
] as const;

const KNOWLEDGE_KINDS = [
  "fact",
  "decision",
  "rationale",
  "preferred_explanation",
  "analogy",
  "private_note",
  "constraint",
  "objection",
  "answer",
] as const;

function requestCore<T>(
  method: RendererCoreMethod,
  params?: JsonObject,
): Promise<T> {
  return window.presenterCopilot.core
    .request<T>(method, params)
    .then(unwrapInvokeResult);
}

function errorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null) {
    const value = error as { code?: unknown; message?: unknown };
    if (typeof value.code === "string" && typeof value.message === "string")
      return `${value.code}: ${value.message}`;
    if (typeof value.message === "string") return value.message;
  }
  return "The Teach request could not be completed.";
}

function providerLabel(provider: ProviderStatus | null): string {
  if (!provider) return "No reasoning provider";
  return `${provider.provider_id} · ${provider.model_id}`;
}

export function TeachPanel({ project }: TeachPanelProps) {
  const [session, setSession] = useState<Session | null>(null);
  const [question, setQuestion] = useState<TeachPromptResult | null>(null);
  const [answer, setAnswer] = useState("");
  const [lastSubmittedText, setLastSubmittedText] = useState("");
  const [keepLocal, setKeepLocal] = useState(false);
  const [candidate, setCandidate] = useState<TeachCandidate | null>(null);
  const [candidateText, setCandidateText] = useState("");
  const [lastSourceUtteranceId, setLastSourceUtteranceId] = useState("");
  const [candidateKind, setCandidateKind] = useState("rationale");
  const [useLive, setUseLive] = useState(true);
  const [useRehearsal, setUseRehearsal] = useState(true);
  const [preferred, setPreferred] = useState(false);
  const [privateItem, setPrivateItem] = useState(false);
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);
  const [speakerEvidence, setSpeakerEvidence] = useState<SpeakerEvidence[]>([]);
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [providerModel, setProviderModel] = useState("");
  const [promotionId, setPromotionId] = useState<string | null>(null);
  const [promotionText, setPromotionText] = useState("");
  const [promotionType, setPromotionType] = useState("explanation_pattern");
  const [profileGuidance, setProfileGuidance] = useState("");
  const [profilePolicy, setProfilePolicy] = useState("preserve_voice");
  const [preferredSeconds, setPreferredSeconds] = useState("");
  const [acknowledgedRemote, setAcknowledgedRemote] = useState(
    project.remote_reasoning_acknowledged,
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setSession(null);
    setQuestion(null);
    setAnswer("");
    setLastSubmittedText("");
    setLastSourceUtteranceId("");
    setCandidate(null);
    setCandidateText("");
    setKeepLocal(false);
    setKnowledgeItems([]);
    setSpeakerEvidence([]);
    setProvider(null);
    setProviderModel("");
    setPromotionId(null);
    setPromotionText("");
    setAcknowledgedRemote(project.remote_reasoning_acknowledged);
  }, [project.id]);

  const loadData = useCallback(async () => {
    setMessage(null);
    try {
      const [sessions, knowledge, profileResult, evidence, providers] =
        await Promise.all([
          requestCore<SessionListResult>("session.list", {
            project_id: project.id,
          }),
          requestCore<KnowledgeListResult>("knowledge.list", {
            project_id: project.id,
          }),
          requestCore<SpeakerProfileResult>("speaker_profile.get"),
          requestCore<SpeakerEvidenceResult>("speaker_profile.list_evidence"),
          requestCore<ProviderListResult>("provider.list"),
        ]);
      const activeSession = sessions.sessions.find(
        (item) => item.mode === "teach" && item.status === "active",
      );
      setSession(activeSession ?? null);
      setQuestion(null);
      setAnswer("");
      setLastSubmittedText("");
      setLastSourceUtteranceId("");
      setCandidate(null);
      setCandidateText("");
      setCandidateKind("rationale");
      setKeepLocal(false);
      if (activeSession) {
        const recovered = await requestCore<TeachStateResult>(
          "teach.get_state",
          {
            project_id: project.id,
            session_id: activeSession.id,
          },
        );
        const pending = recovered.pending_answer;
        const recoveredCandidate = recovered.candidate;
        if (recovered.prompt) {
          setQuestion({
            session_id: recovered.session_id,
            state: recovered.state,
            utterance_id: recovered.prompt.utterance_id,
            question: recovered.prompt.text,
            focus: "decision_rationale",
            route: "recovered",
            reasoning: { status: "recovered" },
          });
        }
        setLastSubmittedText(pending?.text ?? "");
        setLastSourceUtteranceId(pending?.source_utterance_id ?? "");
        setCandidate(recoveredCandidate);
        setCandidateText(
          recoveredCandidate?.proposed_text ?? pending?.text ?? "",
        );
        setCandidateKind(recoveredCandidate?.proposed_kind ?? "rationale");
        setSession((current) =>
          current ? { ...current, teach_state: recovered.state } : current,
        );
      }
      setKnowledgeItems(knowledge.knowledge_items);
      setProfilePolicy(profileResult.profile.default_style_policy);
      setProfileGuidance(profileResult.profile.custom_style_guidance ?? "");
      setPreferredSeconds(
        profileResult.profile.preferred_answer_seconds?.toString() ?? "",
      );
      setSpeakerEvidence(evidence.evidence);
      const currentProvider = providers.providers[0] ?? null;
      setProvider(currentProvider);
      setProviderModel(currentProvider?.model_id ?? "");
      setAcknowledgedRemote(project.remote_reasoning_acknowledged);
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }, [project.id, project.remote_reasoning_acknowledged]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const acknowledgeRemote = useCallback(async () => {
    setBusy("acknowledge-remote");
    try {
      const result = await requestCore<{ project: ReadyProjectSummary }>(
        "project.acknowledge_remote_reasoning",
        { project_id: project.id },
      );
      setAcknowledgedRemote(result.project.remote_reasoning_acknowledged);
      setMessage(
        "Selected-context cloud reasoning is acknowledged for this project.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [project.id]);

  const startTeach = useCallback(async () => {
    setBusy("start-teach");
    setMessage(null);
    try {
      const result = await requestCore<SessionResult>("session.start", {
        project_id: project.id,
        mode: "teach",
      });
      setSession(result.session);
      setQuestion(null);
      setCandidate(null);
      setAnswer("");
      setLastSubmittedText("");
      setLastSourceUtteranceId("");
      setMessage("Teach session started.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [project.id]);

  const nextPrompt = useCallback(async () => {
    if (!session) return;
    setBusy("next-prompt");
    setMessage(null);
    try {
      const result = await requestCore<TeachPromptResult>("teach.next_prompt", {
        project_id: project.id,
        session_id: session.id,
      });
      setQuestion(result);
      setSession((current) =>
        current ? { ...current, teach_state: result.state } : current,
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [project.id, session]);

  const stopTeach = useCallback(async () => {
    if (!session) return;
    setBusy("stop-teach");
    try {
      await requestCore<SessionResult>("session.stop", {
        project_id: project.id,
        session_id: session.id,
        status: "completed",
      });
      setSession(null);
      setQuestion(null);
      setCandidate(null);
      setLastSubmittedText("");
      setLastSourceUtteranceId("");
      setMessage(
        "Teach session completed. Confirmed project knowledge remains in the vault.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [project.id, session]);

  const submitAnswer = useCallback(async () => {
    if (!session || !answer.trim()) return;
    setBusy("submit-answer");
    setMessage(null);
    const submitted = answer.trim();
    try {
      const result = await requestCore<TeachSubmitResult>("teach.submit_text", {
        project_id: project.id,
        session_id: session.id,
        text: submitted,
        local_only: keepLocal,
      });
      setLastSubmittedText(submitted);
      setLastSourceUtteranceId(result.source_utterance_id);
      setAnswer("");
      if (result.candidate) {
        setCandidate(result.candidate);
        setCandidateText(result.candidate.proposed_text);
        setCandidateKind(result.candidate.proposed_kind);
      } else {
        setCandidate(null);
        setCandidateText(submitted);
        setCandidateKind("rationale");
      }
      setSession((current) =>
        current ? { ...current, teach_state: "candidate_ready" } : current,
      );
      setMessage(
        result.candidate
          ? "A provisional candidate is ready for your review."
          : "No provider candidate was used. Your original answer is ready to save directly.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [answer, keepLocal, project.id, session]);

  const discardAnswer = useCallback(async () => {
    if (!session || !lastSourceUtteranceId || candidate) return;
    setBusy("discard-answer");
    setMessage(null);
    try {
      await requestCore<TeachDiscardResult>("teach.discard_answer", {
        project_id: project.id,
        session_id: session.id,
        source_utterance_id: lastSourceUtteranceId,
      });
      setAnswer("");
      setLastSubmittedText("");
      setLastSourceUtteranceId("");
      setCandidate(null);
      setCandidateText("");
      setCandidateKind("rationale");
      setKeepLocal(false);
      setSession((current) =>
        current ? { ...current, teach_state: "ready_for_prompt" } : current,
      );
      setMessage(
        "The answer was discarded and remains only in session history. You can ask another question or end the session.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [candidate, lastSourceUtteranceId, project.id, session]);

  const confirmKnowledge = useCallback(
    async (sourceUtteranceId: string, candidateId?: string) => {
      if (!session || !candidateText.trim()) return;
      setBusy(candidateId ? "confirm-candidate" : "save-answer");
      setMessage(null);
      try {
        await requestCore("teach.confirm_knowledge_item", {
          project_id: project.id,
          session_id: session.id,
          source_utterance_id: sourceUtteranceId,
          ...(candidateId ? { candidate_id: candidateId } : {}),
          text: candidateText.trim(),
          kind: candidateKind,
          use_live: useLive,
          use_rehearsal: useRehearsal,
          preferred,
          private: privateItem,
        });
        setCandidate(null);
        setLastSubmittedText("");
        setLastSourceUtteranceId("");
        setSession((current) =>
          current ? { ...current, teach_state: "ready_for_prompt" } : current,
        );
        await loadData();
        setMessage(
          "Confirmed project knowledge is saved with your original statement as provenance.",
        );
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [
      candidateKind,
      candidateText,
      loadData,
      preferred,
      privateItem,
      project.id,
      session,
      useLive,
      useRehearsal,
    ],
  );

  const rejectCandidate = useCallback(async () => {
    if (!session || !candidate) return;
    setBusy("reject-candidate");
    setMessage(null);
    try {
      await requestCore("teach.reject_knowledge_item", {
        project_id: project.id,
        session_id: session.id,
        candidate_id: candidate.id,
      });
      setCandidate(null);
      setLastSubmittedText("");
      setLastSourceUtteranceId("");
      setSession((current) =>
        current ? { ...current, teach_state: "ready_for_prompt" } : current,
      );
      setMessage(
        "The provisional candidate was rejected and was not saved as knowledge.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [candidate, project.id, session]);

  const updateKnowledge = useCallback(
    async (
      item: KnowledgeItem,
      field: "use_live" | "use_rehearsal" | "preferred" | "private",
    ) => {
      setBusy(`knowledge-${item.id}`);
      try {
        await requestCore("knowledge.update_flags", {
          project_id: project.id,
          knowledge_item_id: item.id,
          [field]: !item[field],
        });
        await loadData();
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadData, project.id],
  );

  const deleteKnowledge = useCallback(
    async (item: KnowledgeItem) => {
      if (!window.confirm("Delete this confirmed project knowledge item?"))
        return;
      setBusy(`delete-knowledge-${item.id}`);
      try {
        await requestCore("knowledge.delete", {
          project_id: project.id,
          knowledge_item_id: item.id,
        });
        await loadData();
        setMessage("Project knowledge and its semantic mapping were removed.");
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadData, project.id],
  );

  const promoteKnowledge = useCallback(async () => {
    if (!promotionId || !promotionText.trim()) return;
    setBusy("promote-profile");
    try {
      await requestCore("speaker_profile.approve_evidence", {
        project_id: project.id,
        knowledge_item_id: promotionId,
        evidence_type: promotionType,
        text: promotionText.trim(),
      });
      setPromotionId(null);
      setPromotionText("");
      await loadData();
      setMessage(
        "The edited wording was explicitly added to the global Speaker Profile.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [loadData, project.id, promotionId, promotionText, promotionType]);

  const saveProfile = useCallback(async () => {
    const secondsText = preferredSeconds.trim();
    const seconds = secondsText ? Number(secondsText) : null;
    if (
      seconds !== null &&
      (!Number.isInteger(seconds) || seconds < 1 || seconds > 3600)
    ) {
      setMessage(
        "Preferred answer length must be a whole number from 1 to 3600.",
      );
      return;
    }
    setBusy("save-profile");
    try {
      await requestCore<SpeakerProfileResult>(
        "speaker_profile.update_settings",
        {
          default_style_policy: profilePolicy,
          custom_style_guidance: profileGuidance,
          preferred_answer_seconds: seconds,
        },
      );
      setMessage("Speaker Profile settings saved globally.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [preferredSeconds, profileGuidance, profilePolicy]);

  const configureProvider = useCallback(async () => {
    if (!providerModel.trim()) return;
    setBusy("configure-provider");
    try {
      const result = await requestCore<{ provider: ProviderStatus }>(
        "provider.configure",
        {
          provider_id: "openai",
          model_id: providerModel.trim(),
          enabled: true,
        },
      );
      setProvider(result.provider);
      setMessage(
        "Safe provider metadata saved. Credentials remain core-environment only.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [providerModel]);

  const removeEvidence = useCallback(
    async (item: SpeakerEvidence) => {
      if (!window.confirm("Remove this approved Speaker Profile evidence?"))
        return;
      setBusy(`remove-evidence-${item.id}`);
      try {
        await requestCore("speaker_profile.remove_evidence", {
          evidence_id: item.id,
        });
        await loadData();
        setMessage("Speaker Profile evidence removed.");
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadData],
  );

  const resetProfile = useCallback(async () => {
    if (!window.confirm("Reset all learned Speaker Profile evidence?")) return;
    setBusy("reset-profile");
    try {
      await requestCore("speaker_profile.reset");
      await loadData();
      setMessage("Learned Speaker Profile evidence was reset.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [loadData]);

  const remoteNeedsAcknowledgement =
    project.privacy_mode !== "local_only" && !acknowledgedRemote;
  const reasoningLabel = question?.reasoning?.provider_id
    ? `${question.reasoning.provider_id} · ${question.reasoning.model_id ?? "model"}`
    : question?.route === "recovered"
      ? "Recovered Teach state"
      : question?.route === "retrieval_only"
        ? "Local retrieval-only"
        : "Not used";

  return (
    <section
      className="m3-grid"
      aria-label="Milestone 3 Teach and Speaker Profile"
    >
      <section className="teach-panel" aria-labelledby="teach-title">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Milestone 3 · typed text path</p>
            <h2 id="teach-title">Teach</h2>
          </div>
          <span className="count-badge">
            {session?.teach_state?.replaceAll("_", " ") ?? "not started"}
          </span>
        </div>
        <p className="inspector-note">
          Teach asks one focused question at a time. Provider suggestions stay
          provisional until you confirm them.
        </p>
        {remoteNeedsAcknowledgement ? (
          <div className="privacy-callout" role="status">
            <strong>Remote reasoning disclosure</strong>
            <span>
              Remote reasoning may receive the current answer and bounded
              selected evidence. It never receives raw audio, a full corpus, or
              private KnowledgeItems.
            </span>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void acknowledgeRemote()}
              disabled={busy !== null}
            >
              Acknowledge for this project
            </button>
          </div>
        ) : null}
        <div className="teach-toolbar">
          {!session ? (
            <button
              type="button"
              className="primary-button"
              onClick={() => void startTeach()}
              disabled={busy !== null}
            >
              Start Teach
            </button>
          ) : (
            <>
              <button
                type="button"
                className="primary-button"
                onClick={() => void nextPrompt()}
                disabled={
                  busy !== null ||
                  candidate !== null ||
                  lastSourceUtteranceId !== "" ||
                  session.teach_state !== "ready_for_prompt"
                }
              >
                {busy === "next-prompt" ? "Thinking…" : "Ask focused question"}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void stopTeach()}
                disabled={
                  busy !== null ||
                  candidate !== null ||
                  lastSourceUtteranceId !== "" ||
                  !["ready_for_prompt", "awaiting_user"].includes(
                    session.teach_state,
                  )
                }
              >
                End session
              </button>
            </>
          )}
          {session ? (
            <span className="teach-session-meta">
              {session.utterances} turns · {session.provider_runs} provider runs
            </span>
          ) : null}
        </div>
        {question ? (
          <article className="teach-question">
            <div className="unit-heading">
              <span>Reasoning · {reasoningLabel}</span>
              <strong>{question.focus.replaceAll("_", " ")}</strong>
            </div>
            <p>{question.question}</p>
            <small>
              Privacy: {project.privacy_mode.replaceAll("_", " ")} · Route:{" "}
              {question.route}
            </small>
          </article>
        ) : (
          <p className="muted">
            Start Teach, then ask for one focused question grounded in this
            project.
          </p>
        )}
        {session ? (
          <div className="teach-answer-form">
            <label>
              Your explanation
              <textarea
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                maxLength={4000}
                rows={5}
                placeholder="Explain the decision, rationale, tradeoff, or preferred wording…"
              />
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={keepLocal}
                onChange={(event) => setKeepLocal(event.target.checked)}
              />
              Keep this answer local
            </label>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void submitAnswer()}
              disabled={
                busy !== null ||
                !answer.trim() ||
                session.teach_state !== "awaiting_user"
              }
            >
              {busy === "submit-answer" ? "Saving answer…" : "Submit answer"}
            </button>
          </div>
        ) : null}
        {candidate ? (
          <article
            className="teach-candidate"
            aria-labelledby="candidate-title"
          >
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Approval boundary</p>
                <h3 id="candidate-title">Provisional candidate</h3>
              </div>
              <span className="provisional-badge">Not confirmed</span>
            </div>
            <div className="candidate-columns">
              <div>
                <span className="field-label">Your original statement</span>
                <p className="original-statement">{lastSubmittedText}</p>
              </div>
              <div>
                <label>
                  AI-proposed compact knowledge
                  <textarea
                    value={candidateText}
                    onChange={(event) => setCandidateText(event.target.value)}
                    maxLength={1500}
                    rows={4}
                  />
                </label>
                <label>
                  Kind
                  <select
                    value={candidateKind}
                    onChange={(event) => setCandidateKind(event.target.value)}
                  >
                    {KNOWLEDGE_KINDS.map((kind) => (
                      <option key={kind} value={kind}>
                        {kind.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
            <div className="checkbox-grid">
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={useRehearsal}
                  onChange={(event) => setUseRehearsal(event.target.checked)}
                />{" "}
                Use in rehearsal
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={useLive}
                  onChange={(event) => setUseLive(event.target.checked)}
                />{" "}
                Use live
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={preferred}
                  onChange={(event) => setPreferred(event.target.checked)}
                />{" "}
                Preferred in this project
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={privateItem}
                  onChange={(event) => setPrivateItem(event.target.checked)}
                />{" "}
                Private · never remote
              </label>
            </div>
            <div className="button-row">
              <button
                type="button"
                className="primary-button"
                onClick={() =>
                  void confirmKnowledge(
                    candidate.source_utterance_id,
                    candidate.id,
                  )
                }
                disabled={busy !== null || !candidateText.trim()}
              >
                Confirm knowledge
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void rejectCandidate()}
                disabled={busy !== null}
              >
                Reject
              </button>
            </div>
          </article>
        ) : lastSubmittedText ? (
          <article className="direct-save-card">
            <div>
              <strong>Keep your original explanation</strong>
              <p>{lastSubmittedText}</p>
            </div>
            <div className="button-row">
              <button
                type="button"
                className="primary-button"
                onClick={() =>
                  void confirmKnowledge(lastSourceUtteranceId, undefined)
                }
                disabled={busy !== null}
              >
                Save original answer
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void discardAnswer()}
                disabled={busy !== null}
              >
                Discard
              </button>
            </div>
          </article>
        ) : null}
        {message ? (
          <p className="notice-message" role="status">
            {message}
          </p>
        ) : null}
      </section>

      <section className="m3-side-stack">
        <section className="knowledge-panel" aria-labelledby="knowledge-title">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Project Brain</p>
              <h2 id="knowledge-title">Confirmed knowledge</h2>
            </div>
            <span className="count-badge">{knowledgeItems.length}</span>
          </div>
          {knowledgeItems.length === 0 ? (
            <p className="muted">
              Confirmed Teach explanations will appear here.
            </p>
          ) : null}
          <div className="knowledge-list">
            {knowledgeItems.map((item) => (
              <article className="knowledge-item" key={item.id}>
                <div className="knowledge-item-heading">
                  <strong>{item.kind.replaceAll("_", " ")}</strong>
                  <span>
                    {item.private
                      ? "private"
                      : item.use_live
                        ? "live"
                        : "rehearsal"}
                  </span>
                </div>
                <p>{item.text}</p>
                <div className="knowledge-flags">
                  {(
                    [
                      "use_live",
                      "use_rehearsal",
                      "preferred",
                      "private",
                    ] as const
                  ).map((field) => (
                    <button
                      type="button"
                      className={`flag-button ${item[field] ? "active" : ""}`}
                      key={field}
                      onClick={() => void updateKnowledge(item, field)}
                      disabled={busy !== null}
                    >
                      {field.replace("use_", "")}: {item[field] ? "on" : "off"}
                    </button>
                  ))}
                </div>
                <div className="button-row">
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => {
                      setPromotionId(item.id);
                      setPromotionText(item.text);
                    }}
                    disabled={busy !== null}
                  >
                    Add to Speaker Profile
                  </button>
                  <button
                    type="button"
                    className="text-button danger-text"
                    onClick={() => void deleteKnowledge(item)}
                    disabled={busy !== null}
                  >
                    Delete
                  </button>
                </div>
                {promotionId === item.id ? (
                  <div className="promotion-form">
                    <label>
                      Profile evidence type
                      <select
                        value={promotionType}
                        onChange={(event) =>
                          setPromotionType(event.target.value)
                        }
                      >
                        {EVIDENCE_TYPES.map((type) => (
                          <option key={type} value={type}>
                            {type.replaceAll("_", " ")}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Edit wording before approval
                      <textarea
                        value={promotionText}
                        onChange={(event) =>
                          setPromotionText(event.target.value)
                        }
                        maxLength={1500}
                        rows={3}
                      />
                    </label>
                    <div className="button-row">
                      <button
                        type="button"
                        className="primary-button"
                        onClick={() => void promoteKnowledge()}
                        disabled={busy !== null}
                      >
                        Approve evidence
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => setPromotionId(null)}
                        disabled={busy !== null}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </section>

        <section className="profile-panel" aria-labelledby="profile-title">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Global style memory</p>
              <h2 id="profile-title">Speaker Profile</h2>
            </div>
            <span className="count-badge">{speakerEvidence.length}</span>
          </div>
          <div className="profile-settings">
            <label>
              Default style policy
              <select
                value={profilePolicy}
                onChange={(event) => setProfilePolicy(event.target.value)}
              >
                <option value="preserve_voice">Preserve my voice</option>
                <option value="light_polish">Light polish</option>
                <option value="executive_concise">Executive concise</option>
                <option value="custom">Custom</option>
              </select>
            </label>
            <label>
              Preferred answer length (seconds)
              <input
                inputMode="numeric"
                value={preferredSeconds}
                onChange={(event) => setPreferredSeconds(event.target.value)}
                placeholder="optional"
              />
            </label>
            <label>
              Custom guidance
              <textarea
                value={profileGuidance}
                onChange={(event) => setProfileGuidance(event.target.value)}
                maxLength={4000}
                rows={2}
              />
            </label>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void saveProfile()}
              disabled={busy !== null}
            >
              Save Profile settings
            </button>
          </div>
          <div className="profile-evidence-list">
            {speakerEvidence.length === 0 ? (
              <p className="muted">No approved style evidence yet.</p>
            ) : null}
            {speakerEvidence.map((item) => (
              <div className="profile-evidence" key={item.id}>
                <div>
                  <strong>{item.evidence_type.replaceAll("_", " ")}</strong>
                  <span>
                    {item.origin_project_name ?? "Project origin"} · Teach
                  </span>
                </div>
                <p>{item.text}</p>
                <button
                  type="button"
                  className="text-button danger-text"
                  onClick={() => void removeEvidence(item)}
                  disabled={busy !== null}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={() => void resetProfile()}
            disabled={busy !== null}
          >
            Reset learned evidence
          </button>
        </section>

        <section className="provider-panel" aria-labelledby="provider-title">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Models &amp; Providers</p>
              <h2 id="provider-title">OpenAI reference adapter</h2>
            </div>
            <span
              className={`provider-status provider-${provider?.health.status ?? "missing"}`}
            >
              {provider?.health.status ?? "missing"}
            </span>
          </div>
          <dl className="provider-facts">
            <div>
              <dt>Provider</dt>
              <dd>{providerLabel(provider)}</dd>
            </div>
            <div>
              <dt>Credential</dt>
              <dd>
                {provider?.health.configured
                  ? "configured in core environment"
                  : "missing"}
              </dd>
            </div>
            <div>
              <dt>Remote packet</dt>
              <dd>selected evidence only · no tools · no raw audio</dd>
            </div>
          </dl>
          <label>
            Safe model id
            <input
              value={providerModel}
              onChange={(event) => setProviderModel(event.target.value)}
              maxLength={120}
            />
          </label>
          <button
            type="button"
            className="secondary-button"
            onClick={() => void configureProvider()}
            disabled={busy !== null || !providerModel.trim()}
          >
            Save model configuration
          </button>
          <p className="muted provider-note">
            The API key is never entered, returned, or stored by the renderer.
          </p>
        </section>
      </section>
    </section>
  );
}
