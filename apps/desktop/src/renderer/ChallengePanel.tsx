import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type AudienceObservation,
  type AudienceProfile,
  type ChallengeAnswerVersion,
  type ChallengeEvidenceRef,
  type ChallengeEvaluation,
  type ChallengeHistoryItem,
  type ChallengeHistoryResult,
  type ChallengeIntensity,
  type ChallengeQuestion,
  type ChallengeStateResult,
  type JsonObject,
  type ProviderStatus,
  type ReadyProjectSummary,
  type RendererCoreMethod,
  type Session,
  unwrapInvokeResult,
} from "../shared/protocol";

type ChallengePanelProps = {
  project: ReadyProjectSummary;
  refreshToken: number;
};

type ProfileListResult = { profiles: AudienceProfile[] };
type ObservationListResult = {
  observations: AudienceObservation[];
  candidates: unknown[];
};
type SessionListResult = { sessions: Session[] };
type SessionResult = { session: Session };

const MAX_ANSWER_CHARS = 4_000;
const MAX_HISTORY_PAGE_SIZE = 20;

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
    if (typeof value.code === "string" && typeof value.message === "string") {
      return `${value.code}: ${value.message}`;
    }
    if (typeof value.message === "string") return value.message;
  }
  return "The Challenge request could not be completed.";
}

function displayAudience(audience: ChallengeQuestion["audience"]): string {
  return [audience.display_name, audience.role, audience.organization]
    .filter(Boolean)
    .join(" · ");
}

function formatScore(score: number | null): string {
  return score === null
    ? "Not enough style evidence"
    : `${Math.round(score * 100)}%`;
}

function formatEstimate(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)} sec estimated`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${String(remainder).padStart(2, "0")}s estimated`;
}

function answerVersionLabel(
  answer: ChallengeAnswerVersion,
  index: number,
): string {
  const preferred = answer.preferred ? " · preferred" : "";
  return `Version ${index + 1}${preferred}`;
}

function ScoreCard({
  label,
  score,
  feedback,
}: {
  label: string;
  score: number | null;
  feedback: string;
}) {
  return (
    <div className="challenge-score-card">
      <span>{label}</span>
      <strong>{formatScore(score)}</strong>
      <p>{feedback}</p>
    </div>
  );
}

function EvaluationView({
  evaluation,
  evidence,
  preferredAnswerSeconds,
  onSavePreferred,
  answerVersionId,
  saved,
}: {
  evaluation: ChallengeEvaluation;
  evidence: ChallengeEvidenceRef[];
  preferredAnswerSeconds: number | null;
  onSavePreferred: () => void;
  answerVersionId: string;
  saved: boolean;
}) {
  const supportedEvidence = useMemo(
    () =>
      Array.from(
        new Map(
          evidence
            .filter((item) =>
              evaluation.supported_evidence_ids.includes(item.evidence_id),
            )
            .map((item) => [item.evidence_id, item]),
        ).values(),
      ),
    [evidence, evaluation.supported_evidence_ids],
  );

  return (
    <div className="challenge-evaluation" aria-label="Challenge evaluation">
      <div className="challenge-score-grid">
        <ScoreCard
          label="Correctness"
          score={evaluation.correctness.score}
          feedback={evaluation.correctness.feedback}
        />
        <ScoreCard
          label="Directness"
          score={evaluation.directness.score}
          feedback={evaluation.directness.feedback}
        />
        <ScoreCard
          label="Completeness"
          score={evaluation.completeness.score}
          feedback={evaluation.completeness.feedback}
        />
        <ScoreCard
          label="Concision"
          score={evaluation.concision.score}
          feedback={evaluation.concision.feedback}
        />
        <ScoreCard
          label="Style match"
          score={evaluation.style_match.score}
          feedback={evaluation.style_match.feedback}
        />
      </div>
      <div className="challenge-support-card">
        <div className="challenge-support-heading">
          <strong>Source support</strong>
          <span
            className={`challenge-support-${evaluation.source_support.status}`}
          >
            {evaluation.source_support.status.replaceAll("_", " ")}
          </span>
        </div>
        <p>{evaluation.source_support.feedback}</p>
        {supportedEvidence.length > 0 ? (
          <ul className="challenge-source-list">
            {supportedEvidence.map((item) => (
              <li key={item.evidence_id}>
                <strong>{item.label}</strong>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No supporting source was cited.</p>
        )}
      </div>
      {evaluation.missing_points.length > 0 ? (
        <div className="challenge-support-card challenge-missing-card">
          <strong>Missing or weak points</strong>
          <ul className="challenge-source-list">
            {evaluation.missing_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {evaluation.strongest_prior_phrasing ? (
        <div className="challenge-prior-phrasing">
          <span>Your strongest prior phrasing</span>
          <p>“{evaluation.strongest_prior_phrasing}”</p>
        </div>
      ) : null}
      <div className="challenge-answer-metrics">
        {typeof evaluation.word_count === "number" ? (
          <span>{evaluation.word_count} words</span>
        ) : null}
        {typeof evaluation.estimated_speaking_seconds === "number" ? (
          <span>{formatEstimate(evaluation.estimated_speaking_seconds)}</span>
        ) : null}
        {preferredAnswerSeconds !== null ? (
          <span>Target: {preferredAnswerSeconds} sec</span>
        ) : null}
      </div>
      <button
        type="button"
        className={saved ? "secondary-button" : "primary-button"}
        onClick={onSavePreferred}
        disabled={saved}
        data-answer-version-id={answerVersionId}
      >
        {saved ? "Saved as preferred" : "Save as preferred"}
      </button>
      <p className="challenge-advisory-note">
        Coaching judgment only. These scores are not scientific measurements,
        personality scores, emotion inference, intelligence scores, or deception
        detection.
      </p>
    </div>
  );
}

function HistoryView({
  history,
  onSavePreferred,
}: {
  history: ChallengeHistoryResult;
  onSavePreferred: (
    item: ChallengeHistoryItem,
    answer: ChallengeAnswerVersion,
  ) => void;
}) {
  return (
    <div className="challenge-history-list">
      {history.items.length === 0 ? (
        <p className="muted">No Challenge questions have been recorded yet.</p>
      ) : null}
      {history.items.map((item, questionIndex) => (
        <article className="challenge-history-item" key={item.id}>
          <div className="challenge-history-heading">
            <span>Question {history.offset + questionIndex + 1}</span>
            <strong>{displayAudience(item.audience)}</strong>
          </div>
          <p className="challenge-history-question">{item.text}</p>
          {item.parent_question_id ? (
            <p className="muted">Bounded follow-up to an earlier question.</p>
          ) : null}
          {item.answer_versions.length === 0 ? (
            <p className="muted">No answer submitted.</p>
          ) : (
            <div className="challenge-answer-history">
              {item.answer_versions.map((answer, answerIndex) => (
                <div className="challenge-answer-history-item" key={answer.id}>
                  <div className="challenge-history-heading">
                    <span>{answerVersionLabel(answer, answerIndex)}</span>
                    <span>{answer.origin.replaceAll("_", " ")}</span>
                  </div>
                  <p>{answer.text}</p>
                  {answer.evaluation ? (
                    <div className="challenge-history-evaluation">
                      <span>
                        Correctness{" "}
                        {formatScore(answer.evaluation.correctness.score)}
                      </span>
                      <span>
                        Source support{" "}
                        {answer.evaluation.source_support.status.replaceAll(
                          "_",
                          " ",
                        )}
                      </span>
                      {!answer.preferred ? (
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => onSavePreferred(item, answer)}
                        >
                          Save this version
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </article>
      ))}
      {history.has_more ? (
        <p className="muted">
          History is bounded to the first {MAX_HISTORY_PAGE_SIZE} questions in
          this view.
        </p>
      ) : null}
    </div>
  );
}

export function ChallengePanel({ project, refreshToken }: ChallengePanelProps) {
  const [profiles, setProfiles] = useState<AudienceProfile[]>([]);
  const [observations, setObservations] = useState<AudienceObservation[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [challengeState, setChallengeState] =
    useState<ChallengeStateResult | null>(null);
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [history, setHistory] = useState<ChallengeHistoryResult | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [selectedProfileIds, setSelectedProfileIds] = useState<string[]>([]);
  const [intensity, setIntensity] = useState<ChallengeIntensity>("normal");
  const [allowFollowUps, setAllowFollowUps] = useState(true);
  const [scope, setScope] = useState<"full_deck" | "slide_range">("full_deck");
  const [slideStart, setSlideStart] = useState("1");
  const [slideEnd, setSlideEnd] = useState("1");
  const [answer, setAnswer] = useState("");
  const [savedAnswerIds, setSavedAnswerIds] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const activeProfiles = useMemo(
    () => profiles.filter((profile) => profile.active),
    [profiles],
  );
  const activeSession = session?.status === "active" ? session : null;
  const config = challengeState?.config;
  const question = challengeState?.current_question ?? null;
  const latestAnswer = challengeState?.latest_answer_version ?? null;
  const evaluated =
    challengeState?.state === "evaluated" && latestAnswer?.evaluation;
  // A project with no Challenge session needs the setup form too; the first
  // submit creates the session through the main/core boundary.
  const setupVisible = config == null;
  const canStartSetup =
    selectedProfileIds.length >= 1 &&
    selectedProfileIds.length <= 3 &&
    (scope === "full_deck" ||
      (Number.isSafeInteger(Number(slideStart)) &&
        Number.isSafeInteger(Number(slideEnd)) &&
        Number(slideStart) >= 1 &&
        Number(slideEnd) >= Number(slideStart)));
  const preferredAnswerSeconds =
    latestAnswer?.evaluation?.preferred_answer_seconds ?? null;

  const loadState = useCallback(
    async (sessionId: string) => {
      const result = await requestCore<ChallengeStateResult>(
        "challenge.get_state",
        {
          project_id: project.id,
          session_id: sessionId,
        },
      );
      setChallengeState(result);
      if (result.config) {
        setIntensity(result.config.intensity);
        setAllowFollowUps(result.config.allow_follow_ups);
        setScope(result.config.scope);
        setSlideStart(String(result.config.slide_start ?? 1));
        setSlideEnd(
          String(result.config.slide_end ?? result.config.slide_start ?? 1),
        );
      }
      return result;
    },
    [project.id],
  );

  const loadHistory = useCallback(
    async (sessionId: string) => {
      const result = await requestCore<ChallengeHistoryResult>(
        "challenge.list_history",
        {
          project_id: project.id,
          session_id: sessionId,
          limit: MAX_HISTORY_PAGE_SIZE,
          offset: 0,
        },
      );
      setHistory(result);
      return result;
    },
    [project.id],
  );

  const loadData = useCallback(async () => {
    setMessage(null);
    try {
      const [profileResult, observationResult, sessionResult, providerResult] =
        await Promise.all([
          requestCore<ProfileListResult>("audience.list", {
            project_id: project.id,
          }),
          requestCore<ObservationListResult>("audience.list_observations", {
            project_id: project.id,
          }),
          requestCore<SessionListResult>("session.list", {
            project_id: project.id,
          }),
          requestCore<{ provider: ProviderStatus }>("provider.status"),
        ]);
      setProfiles(profileResult.profiles);
      setObservations(observationResult.observations);
      setProvider(providerResult.provider);
      const challengeSessions = sessionResult.sessions.filter(
        (item) => item.mode === "challenge",
      );
      const selected =
        challengeSessions.find((item) => item.status === "active") ??
        challengeSessions[0] ??
        null;
      setSession(selected);
      setHistory(null);
      setHistoryOpen(false);
      setAnswer("");
      setSavedAnswerIds(new Set());
      if (selected) {
        const result = await loadState(selected.id);
        if (result.config) {
          setSelectedProfileIds(
            result.audiences
              .filter((item) => item.id !== null)
              .map((item) => item.id as string),
          );
        } else {
          setSelectedProfileIds([]);
        }
      } else {
        setChallengeState(null);
        setSelectedProfileIds([]);
      }
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }, [loadState, project.id]);

  useEffect(() => {
    setProfiles([]);
    setObservations([]);
    setSession(null);
    setChallengeState(null);
    setProvider(null);
    setHistory(null);
    setHistoryOpen(false);
    setSelectedProfileIds([]);
    setIntensity("normal");
    setAllowFollowUps(true);
    setScope("full_deck");
    setSlideStart("1");
    setSlideEnd("1");
    setAnswer("");
    setSavedAnswerIds(new Set());
    void loadData();
  }, [loadData, refreshToken]);

  const ensureActiveSession = useCallback(async (): Promise<Session> => {
    if (activeSession) return activeSession;
    const result = await requestCore<SessionResult>("session.start", {
      project_id: project.id,
      mode: "challenge",
    });
    setSession(result.session);
    return result.session;
  }, [activeSession, project.id]);

  const startChallenge = useCallback(async () => {
    if (!canStartSetup) {
      setMessage(
        "Select 1–3 active audience profiles and a valid scope first.",
      );
      return;
    }
    setBusy("start-challenge");
    setMessage(null);
    try {
      const challengeSession = await ensureActiveSession();
      await requestCore<ChallengeStateResult>("challenge.configure", {
        project_id: project.id,
        session_id: challengeSession.id,
        audience_profile_ids: selectedProfileIds,
        intensity,
        allow_follow_ups: allowFollowUps,
        scope,
        ...(scope === "slide_range"
          ? { slide_start: Number(slideStart), slide_end: Number(slideEnd) }
          : {}),
      });
      await loadState(challengeSession.id);
      const next = await requestCore<{ question: ChallengeQuestion }>(
        "challenge.next_question",
        {
          project_id: project.id,
          session_id: challengeSession.id,
        },
      );
      await loadState(challengeSession.id);
      setAnswer("");
      setMessage(
        `Question ready for ${displayAudience(next.question.audience)}.`,
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [
    allowFollowUps,
    canStartSetup,
    ensureActiveSession,
    intensity,
    loadState,
    project.id,
    scope,
    selectedProfileIds,
    slideEnd,
    slideStart,
  ]);

  const askNextQuestion = useCallback(
    async (followUpToQuestionId?: string) => {
      if (!activeSession) return;
      setBusy(followUpToQuestionId ? "follow-up" : "next-question");
      setMessage(null);
      try {
        await requestCore<{ question: ChallengeQuestion }>(
          "challenge.next_question",
          {
            project_id: project.id,
            session_id: activeSession.id,
            ...(followUpToQuestionId
              ? { follow_up_to_question_id: followUpToQuestionId }
              : {}),
          },
        );
        await loadState(activeSession.id);
        setAnswer("");
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [activeSession, loadState, project.id],
  );

  const submitAnswer = useCallback(async () => {
    if (!activeSession || !question || !answer.trim()) return;
    setBusy("submit-answer");
    setMessage(null);
    try {
      await requestCore<{ answer_version: ChallengeAnswerVersion }>(
        "challenge.submit_answer",
        {
          project_id: project.id,
          session_id: activeSession.id,
          question_id: question.id,
          text: answer,
        },
      );
      await loadState(activeSession.id);
      setMessage("Advisory evaluation ready.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [activeSession, answer, loadState, project.id, question]);

  const retryQuestion = useCallback(async () => {
    if (!activeSession || !question) return;
    setBusy("retry-question");
    setMessage(null);
    try {
      await requestCore<ChallengeStateResult>("challenge.retry_question", {
        project_id: project.id,
        session_id: activeSession.id,
        question_id: question.id,
      });
      await loadState(activeSession.id);
      setAnswer("");
      setMessage(
        "Same question reopened. Your next answer will be a new version.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [activeSession, loadState, project.id, question]);

  const savePreferred = useCallback(
    async (answerVersion: ChallengeAnswerVersion) => {
      if (!activeSession || !question) return;
      setBusy(`save-preferred-${answerVersion.id}`);
      setMessage(null);
      try {
        await requestCore("challenge.save_preferred_answer", {
          project_id: project.id,
          session_id: activeSession.id,
          question_id: question.id,
          answer_version_id: answerVersion.id,
        });
        setSavedAnswerIds((current) => new Set(current).add(answerVersion.id));
        await loadState(activeSession.id);
        if (historyOpen) await loadHistory(activeSession.id);
        setMessage(
          "This user-authored answer is now preferred Project Brain evidence.",
        );
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [activeSession, historyOpen, loadHistory, loadState, project.id, question],
  );

  const toggleHistory = useCallback(async () => {
    if (!session) return;
    if (historyOpen) {
      setHistoryOpen(false);
      return;
    }
    setBusy("history");
    setMessage(null);
    try {
      await loadHistory(session.id);
      setHistoryOpen(true);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [historyOpen, loadHistory, session]);

  const beginNewChallenge = useCallback(() => {
    setSession(null);
    setChallengeState(null);
    setHistory(null);
    setHistoryOpen(false);
    setSelectedProfileIds([]);
    setIntensity("normal");
    setAllowFollowUps(true);
    setScope("full_deck");
    setSlideStart("1");
    setSlideEnd("1");
    setAnswer("");
    setMessage(null);
  }, []);

  const deleteChallengeSession = useCallback(async () => {
    if (!session) return;
    if (
      !window.confirm(
        "Delete this Challenge session and its unsaved history? Explicitly saved preferred answers remain in Project Brain.",
      )
    ) {
      return;
    }
    setBusy("delete-session");
    setMessage(null);
    try {
      await requestCore("session.delete", {
        project_id: project.id,
        session_id: session.id,
      });
      beginNewChallenge();
      setMessage(
        "Challenge session deleted. Saved preferred answers remain available.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [beginNewChallenge, project.id, session]);

  const observationById = useMemo(
    () => new Map(observations.map((item) => [item.id, item])),
    [observations],
  );
  const providerStatus = challengeState?.reasoning ?? null;
  const profileSelectionError =
    selectedProfileIds.length === 0
      ? "Select at least one active profile."
      : selectedProfileIds.length > 3
        ? "Select no more than three profiles."
        : null;

  return (
    <section
      className="challenge-panel"
      aria-label="Milestone 5 Challenge mode"
    >
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">PRACTICE WITH PURPOSE</p>
          <h2>Challenge mode</h2>
        </div>
        <span className="count-badge">
          {challengeState?.state?.replaceAll("_", " ") ?? "not started"}
        </span>
      </div>
      <p className="inspector-note">
        Practice against bounded, project-grounded questions from selected
        audience profiles. Answers are advisory until you explicitly save one.
      </p>
      {message ? (
        <p className="error-message challenge-message" role="status">
          {message}
        </p>
      ) : null}

      <div className="challenge-status-row">
        <span>
          Privacy: <strong>{project.privacy_mode.replaceAll("_", " ")}</strong>
        </span>
        <span>
          Provider: <strong>{provider?.provider_id ?? "unavailable"}</strong>
          {provider?.model_id ? ` · ${provider.model_id}` : ""}
        </span>
        <span>
          Availability:{" "}
          <strong>
            {providerStatus?.reason ?? provider?.health.status ?? "not checked"}
          </strong>
        </span>
      </div>

      {session && session.status !== "active" ? (
        <div className="challenge-closed-card" role="status">
          <strong>This Challenge session is {session.status}.</strong>
          <span>
            Its questions, answer versions, and evaluations remain available
            below.
          </span>
          <button
            type="button"
            className="secondary-button"
            onClick={beginNewChallenge}
          >
            Start a new Challenge
          </button>
        </div>
      ) : null}

      {setupVisible ? (
        <div className="challenge-setup">
          <div className="challenge-setup-heading">
            <div>
              <h3>Set up the challenge</h3>
              <p className="muted">
                Choose one to three active project-local profiles.
              </p>
            </div>
            <span className="challenge-selection-count">
              {selectedProfileIds.length}/3 selected
            </span>
          </div>
          <div className="challenge-profile-grid">
            {activeProfiles.length === 0 ? (
              <p className="muted">
                No active Audience Profiles are available. Create or enable one
                in the Audience Model below before starting.
              </p>
            ) : null}
            {activeProfiles.map((profile) => {
              const selected = selectedProfileIds.includes(profile.id);
              return (
                <label
                  className={`challenge-profile-option ${selected ? "selected" : ""}`}
                  key={profile.id}
                >
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() =>
                      setSelectedProfileIds((current) =>
                        selected
                          ? current.filter((id) => id !== profile.id)
                          : current.length < 3
                            ? [...current, profile.id]
                            : current,
                      )
                    }
                  />
                  <span>
                    <strong>{profile.display_name}</strong>
                    <small>
                      {[profile.role, profile.organization]
                        .filter(Boolean)
                        .join(" · ") || "No role or organization"}
                    </small>
                  </span>
                </label>
              );
            })}
          </div>
          {profileSelectionError ? (
            <p className="muted">{profileSelectionError}</p>
          ) : null}
          <div className="challenge-settings-grid">
            <label>
              Intensity
              <select
                value={intensity}
                onChange={(event) =>
                  setIntensity(event.target.value as ChallengeIntensity)
                }
              >
                <option value="normal">Normal · realistic clarification</option>
                <option value="skeptical">
                  Skeptical · probe assumptions and trade-offs
                </option>
                <option value="adversarial">
                  Adversarial · professional stress test
                </option>
              </select>
            </label>
            <label className="checkbox-row challenge-follow-up-toggle">
              <input
                type="checkbox"
                checked={allowFollowUps}
                onChange={(event) => setAllowFollowUps(event.target.checked)}
              />
              Allow explicit follow-up questions
            </label>
            <label>
              Presentation scope
              <select
                value={scope}
                onChange={(event) =>
                  setScope(event.target.value as "full_deck" | "slide_range")
                }
              >
                <option value="full_deck">Full deck</option>
                <option value="slide_range">Bounded slide range</option>
              </select>
            </label>
            {scope === "slide_range" ? (
              <>
                <label>
                  First slide
                  <input
                    inputMode="numeric"
                    value={slideStart}
                    onChange={(event) => setSlideStart(event.target.value)}
                    min={1}
                    max={10_000}
                  />
                </label>
                <label>
                  Last slide
                  <input
                    inputMode="numeric"
                    value={slideEnd}
                    onChange={(event) => setSlideEnd(event.target.value)}
                    min={1}
                    max={10_000}
                  />
                </label>
              </>
            ) : null}
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={() => void startChallenge()}
            disabled={
              busy !== null || !canStartSetup || activeProfiles.length === 0
            }
          >
            {busy === "start-challenge" ? "Starting…" : "Start Challenge"}
          </button>
        </div>
      ) : null}

      {config && session ? (
        <div className="challenge-config-summary">
          <span>{config.intensity} intensity</span>
          <span>
            {config.scope === "full_deck"
              ? "Full deck"
              : `Slides ${config.slide_start}–${config.slide_end}`}
          </span>
          <span>
            {config.allow_follow_ups ? "Follow-ups on" : "Follow-ups off"}
          </span>
          <span>
            {challengeState?.audiences.filter((item) => item.available)
              .length ?? 0}{" "}
            active profiles available
          </span>
        </div>
      ) : null}

      {question && session ? (
        <div className="challenge-question-card">
          <div className="challenge-question-audience">
            <span>Simulated audience</span>
            <strong>{displayAudience(question.audience)}</strong>
          </div>
          <p className="challenge-question-text">{question.text}</p>
          <details className="challenge-grounding">
            <summary>Why this question / Sources</summary>
            <p>{question.rationale}</p>
            {question.audience_observations.length > 0 ? (
              <div>
                <strong>Audience observation basis</strong>
                <ul className="challenge-source-list">
                  {question.audience_observations.map((item) => {
                    const observation = observationById.get(
                      item.observation_id,
                    );
                    return (
                      <li key={item.observation_id}>
                        {observation
                          ? observation.text
                          : item.available
                            ? "Accepted observation"
                            : "Observation unavailable"}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}
            <div>
              <strong>Project sources</strong>
              {question.evidence.length > 0 ? (
                <ul className="challenge-source-list">
                  {question.evidence.map((item) => (
                    <li key={item.evidence_id}>
                      <span
                        className={
                          item.available ? "" : "challenge-source-unavailable"
                        }
                      >
                        {item.label}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No source is currently available.</p>
              )}
            </div>
          </details>
        </div>
      ) : null}

      {activeSession &&
      question &&
      challengeState?.state === "awaiting_answer" ? (
        <form
          className="challenge-answer-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submitAnswer();
          }}
        >
          <label htmlFor="challenge-answer">Your typed answer</label>
          <textarea
            id="challenge-answer"
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            maxLength={MAX_ANSWER_CHARS}
            rows={7}
            placeholder="Answer in your own words. Keep exact facts tied to the project evidence."
          />
          <div className="challenge-answer-form-footer">
            <span className="muted">
              {answer.length}/{MAX_ANSWER_CHARS} characters
            </span>
            <button
              type="submit"
              className="primary-button"
              disabled={busy !== null || !answer.trim()}
            >
              {busy === "submit-answer" ? "Evaluating…" : "Submit typed answer"}
            </button>
          </div>
        </form>
      ) : null}

      {evaluated && question && latestAnswer?.evaluation ? (
        <EvaluationView
          evaluation={latestAnswer.evaluation}
          evidence={[...question.evidence, ...latestAnswer.evidence]}
          preferredAnswerSeconds={preferredAnswerSeconds}
          onSavePreferred={() => void savePreferred(latestAnswer)}
          answerVersionId={latestAnswer.id}
          saved={latestAnswer.preferred || savedAnswerIds.has(latestAnswer.id)}
        />
      ) : null}

      {activeSession && challengeState?.state === "evaluated" ? (
        <div className="button-row challenge-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={() => void retryQuestion()}
            disabled={busy !== null || !question}
          >
            {busy === "retry-question" ? "Reopening…" : "Retry"}
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => void askNextQuestion()}
            disabled={busy !== null}
          >
            {busy === "next-question" ? "Asking…" : "Next question"}
          </button>
          {config?.allow_follow_ups && question ? (
            <button
              type="button"
              className="secondary-button"
              onClick={() => void askNextQuestion(question.id)}
              disabled={busy !== null}
            >
              {busy === "follow-up" ? "Asking…" : "Follow-up"}
            </button>
          ) : null}
        </div>
      ) : null}

      {activeSession && challengeState?.state === "ready_for_question" ? (
        <button
          type="button"
          className="primary-button"
          onClick={() => void askNextQuestion()}
          disabled={busy !== null}
        >
          {busy === "next-question" ? "Asking…" : "Ask first question"}
        </button>
      ) : null}

      {session ? (
        <div className="challenge-history-heading challenge-history-toolbar">
          <div>
            <strong>Challenge history</strong>
            <span className="muted">
              Questions and answer versions stay session-local.
            </span>
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={() => void toggleHistory()}
            disabled={busy !== null}
          >
            {busy === "history"
              ? "Loading…"
              : historyOpen
                ? "Hide history"
                : "Inspect history"}
          </button>
          <button
            type="button"
            className="text-button danger-text"
            onClick={() => void deleteChallengeSession()}
            disabled={busy !== null}
          >
            {busy === "delete-session" ? "Deleting…" : "Delete session"}
          </button>
        </div>
      ) : null}
      {historyOpen && history ? (
        <HistoryView
          history={history}
          onSavePreferred={(item, answerVersion) => {
            if (item.id === question?.id) void savePreferred(answerVersion);
            else
              setMessage(
                "Save a preferred answer from the current evaluated question.",
              );
          }}
        />
      ) : null}
    </section>
  );
}
