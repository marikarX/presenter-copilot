import { useCallback, useEffect, useState } from "react";

import {
  type AudienceObservation,
  type AudienceObservationCandidate,
  type AudienceObservationType,
  type AudienceProfile,
  type AudienceProfileSummary,
  type JsonObject,
  type ReadyProjectSummary,
  type RendererCoreMethod,
  type TranscriptSpeakerSummary,
  unwrapInvokeResult,
} from "../shared/protocol";

type AudiencePanelProps = {
  project: ReadyProjectSummary;
  refreshToken: number;
};

type ProfileListResult = { profiles: AudienceProfile[] };
type SpeakerListResult = { speakers: TranscriptSpeakerSummary[] };
type ObservationListResult = {
  observations: AudienceObservation[];
  candidates: AudienceObservationCandidate[];
};

type ProfileDraft = {
  display_name: string;
  role: string;
  organization: string;
  user_notes: string;
};

type CandidateDraft = {
  text: string;
  observation_type: AudienceObservationType;
};

const OBSERVATION_TYPES: Array<{
  value: AudienceObservationType;
  label: string;
}> = [
  { value: "topic_interest", label: "Topic interest" },
  { value: "question_pattern", label: "Question pattern" },
  { value: "answer_preference", label: "Answer preference" },
  { value: "recurring_objection", label: "Recurring objection" },
  { value: "interaction_pattern", label: "Interaction pattern" },
  { value: "decision_criterion", label: "Decision criterion" },
];

const EMPTY_PROFILE_DRAFT: ProfileDraft = {
  display_name: "",
  role: "",
  organization: "",
  user_notes: "",
};

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
  return "The Audience Model request could not be completed.";
}

function formatTimestamp(value: number | null): string | null {
  if (value === null) return null;
  const totalSeconds = Math.floor(value / 1000);
  const milliseconds = value % 1000;
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(milliseconds).padStart(3, "0")}`;
}

function profileLabel(profile: AudienceProfileSummary): string {
  return [profile.display_name, profile.role].filter(Boolean).join(" · ");
}

function speakerKey(speaker: TranscriptSpeakerSummary): string {
  return `${speaker.document_id}:${speaker.native_speaker_label}`;
}

function evidenceHeading(count: number): string {
  return `${count} transcript segment${count === 1 ? "" : "s"}`;
}

function EvidenceList({
  evidence,
}: {
  evidence: AudienceObservation["evidence"];
}) {
  return (
    <details className="audience-evidence">
      <summary>Review evidence · {evidenceHeading(evidence.length)}</summary>
      {evidence.length === 0 ? (
        <p className="muted">No transcript evidence is attached.</p>
      ) : (
        <ul>
          {evidence.map((item) => (
            <li key={`${item.provenance_type}:${item.provenance_id}`}>
              <strong>{item.label}</strong>
              <span>{item.text}</span>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

function ObservationTypeSelect({
  value,
  onChange,
  disabled = false,
  label,
}: {
  value: AudienceObservationType;
  onChange: (value: AudienceObservationType) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(event) =>
        onChange(event.target.value as AudienceObservationType)
      }
      disabled={disabled}
    >
      {OBSERVATION_TYPES.map((item) => (
        <option value={item.value} key={item.value}>
          {item.label}
        </option>
      ))}
    </select>
  );
}

export function AudiencePanel({ project, refreshToken }: AudiencePanelProps) {
  const [profiles, setProfiles] = useState<AudienceProfile[]>([]);
  const [speakers, setSpeakers] = useState<TranscriptSpeakerSummary[]>([]);
  const [observations, setObservations] = useState<AudienceObservation[]>([]);
  const [candidates, setCandidates] = useState<AudienceObservationCandidate[]>(
    [],
  );
  const [profileDraft, setProfileDraft] =
    useState<ProfileDraft>(EMPTY_PROFILE_DRAFT);
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [candidateDrafts, setCandidateDrafts] = useState<
    Record<string, CandidateDraft>
  >({});
  const [observationDrafts, setObservationDrafts] = useState<
    Record<string, CandidateDraft>
  >({});
  const [userObservationProfileId, setUserObservationProfileId] = useState("");
  const [userObservationType, setUserObservationType] =
    useState<AudienceObservationType>("question_pattern");
  const [userObservationText, setUserObservationText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [profileResult, speakerResult, observationResult] =
        await Promise.all([
          requestCore<ProfileListResult>("audience.list", {
            project_id: project.id,
          }),
          requestCore<SpeakerListResult>("transcript.list_speakers", {
            project_id: project.id,
          }),
          requestCore<ObservationListResult>("audience.list_observations", {
            project_id: project.id,
          }),
        ]);
      setProfiles(profileResult.profiles);
      setSpeakers(speakerResult.speakers);
      setObservations(observationResult.observations);
      setCandidates(observationResult.candidates);
      setUserObservationProfileId((current) => {
        if (
          current &&
          profileResult.profiles.some((profile) => profile.id === current)
        )
          return current;
        return (
          profileResult.profiles.find((profile) => profile.active)?.id ?? ""
        );
      });
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }, [project.id]);

  useEffect(() => {
    setMessage(null);
    setEditingProfileId(null);
    setProfileDraft(EMPTY_PROFILE_DRAFT);
    void loadData();
  }, [loadData, refreshToken]);

  const createProfile = useCallback(async () => {
    if (!profileDraft.display_name.trim()) return;
    setBusy("create-profile");
    setMessage(null);
    try {
      await requestCore("audience.create", {
        project_id: project.id,
        display_name: profileDraft.display_name.trim(),
        role: profileDraft.role.trim() || null,
        organization: profileDraft.organization.trim() || null,
        user_notes: profileDraft.user_notes.trim() || null,
        active: true,
      });
      setProfileDraft(EMPTY_PROFILE_DRAFT);
      await loadData();
      setMessage("Audience profile created locally.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [loadData, profileDraft, project.id]);

  const beginProfileEdit = useCallback((profile: AudienceProfile) => {
    setEditingProfileId(profile.id);
    setProfileDraft({
      display_name: profile.display_name,
      role: profile.role ?? "",
      organization: profile.organization ?? "",
      user_notes: profile.user_notes ?? "",
    });
  }, []);

  const saveProfile = useCallback(
    async (profile: AudienceProfile) => {
      if (!profileDraft.display_name.trim()) return;
      setBusy(`save-profile-${profile.id}`);
      setMessage(null);
      try {
        await requestCore("audience.update", {
          project_id: project.id,
          audience_profile_id: profile.id,
          display_name: profileDraft.display_name.trim(),
          role: profileDraft.role.trim() || null,
          organization: profileDraft.organization.trim() || null,
          user_notes: profileDraft.user_notes.trim() || null,
        });
        setEditingProfileId(null);
        setProfileDraft(EMPTY_PROFILE_DRAFT);
        await loadData();
        setMessage("Audience profile updated locally.");
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadData, profileDraft, project.id],
  );

  const toggleProfile = useCallback(
    async (profile: AudienceProfile) => {
      setBusy(`toggle-profile-${profile.id}`);
      setMessage(null);
      try {
        await requestCore("audience.update", {
          project_id: project.id,
          audience_profile_id: profile.id,
          active: !profile.active,
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

  const deleteProfile = useCallback(
    async (profile: AudienceProfile) => {
      if (
        !window.confirm(
          `Delete ${profile.display_name}? Its transcript mappings will become unresolved.`,
        )
      )
        return;
      setBusy(`delete-profile-${profile.id}`);
      setMessage(null);
      try {
        await requestCore("audience.delete", {
          project_id: project.id,
          audience_profile_id: profile.id,
        });
        await loadData();
        setMessage("Audience profile deleted; transcript evidence remains.");
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadData, project.id],
  );

  const setSpeakerMapping = useCallback(
    async (speaker: TranscriptSpeakerSummary, profileId: string) => {
      setBusy(`map-${speakerKey(speaker)}`);
      setMessage(null);
      try {
        if (profileId) {
          await requestCore("transcript.map_speaker", {
            project_id: project.id,
            document_id: speaker.document_id,
            native_speaker_label: speaker.native_speaker_label,
            audience_profile_id: profileId,
          });
        } else {
          await requestCore("transcript.unmap_speaker", {
            project_id: project.id,
            document_id: speaker.document_id,
            native_speaker_label: speaker.native_speaker_label,
          });
        }
        await loadData();
        setMessage(
          profileId
            ? "Speaker mapping saved. Derived observations were revalidated."
            : "Speaker is unresolved again; derived observations need review.",
        );
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadData, project.id],
  );

  const createFromSpeaker = useCallback((speaker: TranscriptSpeakerSummary) => {
    setEditingProfileId(null);
    setProfileDraft({
      ...EMPTY_PROFILE_DRAFT,
      display_name: speaker.native_speaker_label,
    });
    setMessage(
      "The profile form is ready; confirm the fields before creating it.",
    );
  }, []);

  const extractForProfile = useCallback(
    async (profile: AudienceProfile) => {
      setBusy(`extract-${profile.id}`);
      setMessage(null);
      try {
        const result = await requestCore<{
          created_candidate_count: number;
          skipped_duplicate_count: number;
          matched_segment_count: number;
          evidence_segment_count: number;
        }>("audience.extract_observations", {
          project_id: project.id,
          audience_profile_id: profile.id,
        });
        await loadData();
        setMessage(
          `Created ${result.created_candidate_count} provisional candidate(s) from ${result.matched_segment_count} matched transcript segment(s); retained ${result.evidence_segment_count} evidence example(s); skipped ${result.skipped_duplicate_count} duplicate(s).`,
        );
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadData, project.id],
  );

  const acceptCandidate = useCallback(
    async (candidate: AudienceObservationCandidate) => {
      const draft =
        candidateDrafts[candidate.id] ??
        ({
          text: candidate.proposed_text,
          observation_type: candidate.observation_type,
        } satisfies CandidateDraft);
      setBusy(`accept-candidate-${candidate.id}`);
      setMessage(null);
      try {
        await requestCore("audience.accept_observation", {
          project_id: project.id,
          candidate_id: candidate.id,
          text: draft.text.trim(),
          observation_type: draft.observation_type,
        });
        await loadData();
        setMessage("Observation accepted into the active Audience Model.");
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [candidateDrafts, loadData, project.id],
  );

  const rejectCandidate = useCallback(
    async (candidate: AudienceObservationCandidate) => {
      setBusy(`reject-candidate-${candidate.id}`);
      setMessage(null);
      try {
        await requestCore("audience.reject_observation", {
          project_id: project.id,
          candidate_id: candidate.id,
        });
        await loadData();
        setMessage(
          "Provisional candidate rejected and retained as project-local review history.",
        );
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadData, project.id],
  );

  const updateObservation = useCallback(
    async (observation: AudienceObservation) => {
      const draft =
        observationDrafts[observation.id] ??
        ({
          text: observation.text,
          observation_type: observation.observation_type,
        } satisfies CandidateDraft);
      setBusy(`update-observation-${observation.id}`);
      setMessage(null);
      try {
        await requestCore("audience.update_observation", {
          project_id: project.id,
          observation_id: observation.id,
          text: draft.text.trim(),
          observation_type: draft.observation_type,
        });
        await loadData();
        setMessage("Observation updated and safety policy rechecked.");
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadData, observationDrafts, project.id],
  );

  const deleteObservation = useCallback(
    async (observation: AudienceObservation) => {
      setBusy(`delete-observation-${observation.id}`);
      setMessage(null);
      try {
        await requestCore("audience.delete_observation", {
          project_id: project.id,
          observation_id: observation.id,
        });
        await loadData();
        setMessage("Observation deleted from the project Audience Model.");
      } catch (error) {
        setMessage(errorMessage(error));
      } finally {
        setBusy(null);
      }
    },
    [loadData, project.id],
  );

  const createUserObservation = useCallback(async () => {
    if (!userObservationProfileId || !userObservationText.trim()) return;
    setBusy("create-user-observation");
    setMessage(null);
    try {
      await requestCore("audience.create_observation", {
        project_id: project.id,
        audience_profile_id: userObservationProfileId,
        observation_type: userObservationType,
        text: userObservationText.trim(),
      });
      setUserObservationText("");
      await loadData();
      setMessage(
        "User-entered observation saved locally without transcript evidence.",
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, [
    loadData,
    project.id,
    userObservationProfileId,
    userObservationText,
    userObservationType,
  ]);

  const profileObservations = (profileId: string) =>
    observations.filter(
      (observation) => observation.audience_profile_id === profileId,
    );
  const profileCandidates = (profileId: string) =>
    candidates.filter(
      (candidate) => candidate.audience_profile_id === profileId,
    );

  return (
    <section className="audience-panel" aria-labelledby="audience-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Project-local · explicit mapping</p>
          <h2 id="audience-title">Audience</h2>
        </div>
        <span className="count-badge">{profiles.length} profiles</span>
      </div>
      <p className="inspector-note">
        Native transcript labels stay as evidence. Only an explicit user mapping
        can connect a label to a project Audience Profile.
      </p>
      {message ? (
        <p className="notice-message" role="status">
          {message}
        </p>
      ) : null}

      <section className="audience-subsection" aria-labelledby="speakers-title">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Transcript attribution</p>
            <h3 id="speakers-title">Transcript speakers</h3>
          </div>
          <span className="count-badge">{speakers.length} named</span>
        </div>
        {speakers.length === 0 ? (
          <p className="muted">
            Import an authorized VTT, SRT, named TXT, or structured JSON
            transcript to enumerate native speaker labels.
          </p>
        ) : (
          <div className="audience-speaker-list">
            {speakers.map((speaker) => {
              const start = formatTimestamp(speaker.first_start_ms);
              const end = formatTimestamp(speaker.last_end_ms);
              return (
                <article className="audience-speaker" key={speakerKey(speaker)}>
                  <div>
                    <strong>{speaker.native_speaker_label}</strong>
                    <span>
                      {speaker.document_name} · {speaker.segment_count} segments
                      {start ? ` · ${start}${end ? `–${end}` : ""}` : ""}
                    </span>
                  </div>
                  <div className="audience-speaker-actions">
                    <select
                      aria-label={`Map ${speaker.native_speaker_label} from ${speaker.document_name}`}
                      value={speaker.audience_profile?.id ?? ""}
                      onChange={(event) =>
                        void setSpeakerMapping(speaker, event.target.value)
                      }
                      disabled={busy !== null}
                    >
                      <option value="">Unresolved</option>
                      {profiles.map((profile) => (
                        <option value={profile.id} key={profile.id}>
                          {profileLabel(profile)}
                          {!profile.active ? " · disabled" : ""}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => createFromSpeaker(speaker)}
                      disabled={busy !== null}
                    >
                      Create profile
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="audience-subsection" aria-labelledby="profiles-title">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Explicit audience state</p>
            <h3 id="profiles-title">Audience Profiles</h3>
          </div>
        </div>
        <div className="audience-profile-form">
          <label>
            Display name
            <input
              value={profileDraft.display_name}
              onChange={(event) =>
                setProfileDraft((current) => ({
                  ...current,
                  display_name: event.target.value,
                }))
              }
              maxLength={120}
            />
          </label>
          <label>
            Role
            <input
              value={profileDraft.role}
              onChange={(event) =>
                setProfileDraft((current) => ({
                  ...current,
                  role: event.target.value,
                }))
              }
              maxLength={200}
            />
          </label>
          <label>
            Organization
            <input
              value={profileDraft.organization}
              onChange={(event) =>
                setProfileDraft((current) => ({
                  ...current,
                  organization: event.target.value,
                }))
              }
              maxLength={200}
            />
          </label>
          <label className="audience-notes-field">
            User-supplied notes
            <textarea
              value={profileDraft.user_notes}
              onChange={(event) =>
                setProfileDraft((current) => ({
                  ...current,
                  user_notes: event.target.value,
                }))
              }
              maxLength={4000}
              rows={2}
            />
          </label>
          <div className="audience-form-actions">
            <button
              type="button"
              className="primary-button"
              onClick={() => {
                if (!editingProfileId) {
                  void createProfile();
                  return;
                }
                const profile = profiles.find(
                  (candidate) => candidate.id === editingProfileId,
                );
                if (profile) void saveProfile(profile);
              }}
              disabled={busy !== null || !profileDraft.display_name.trim()}
            >
              {editingProfileId ? "Save profile" : "Create profile"}
            </button>
            {editingProfileId ? (
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setEditingProfileId(null);
                  setProfileDraft(EMPTY_PROFILE_DRAFT);
                }}
                disabled={busy !== null}
              >
                Cancel edit
              </button>
            ) : null}
          </div>
        </div>

        {profiles.length === 0 ? (
          <p className="muted">No project-local Audience Profiles yet.</p>
        ) : (
          <div className="audience-profile-list">
            {profiles.map((profile) => {
              const profileObservationItems = profileObservations(profile.id);
              const profileCandidateItems = profileCandidates(profile.id);
              return (
                <article className="audience-profile-card" key={profile.id}>
                  <div className="audience-profile-heading">
                    <div>
                      <h4>{profile.display_name}</h4>
                      <p className="muted">
                        {[profile.role, profile.organization]
                          .filter(Boolean)
                          .join(" · ") || "No role or organization"}
                        {!profile.active ? " · disabled" : ""}
                      </p>
                    </div>
                    <div className="source-item-actions">
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => beginProfileEdit(profile)}
                        disabled={busy !== null}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => void toggleProfile(profile)}
                        disabled={busy !== null}
                      >
                        {profile.active ? "Disable" : "Enable"}
                      </button>
                      <button
                        type="button"
                        className="text-button danger-text"
                        onClick={() => void deleteProfile(profile)}
                        disabled={busy !== null}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  {profile.user_notes ? (
                    <p className="audience-user-notes">
                      <strong>User-supplied notes</strong> {profile.user_notes}
                    </p>
                  ) : null}
                  <div className="audience-observation-block">
                    <div className="audience-block-heading">
                      <strong>Observations</strong>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => void extractForProfile(profile)}
                        disabled={busy !== null || !profile.active}
                      >
                        {busy === `extract-${profile.id}`
                          ? "Extracting…"
                          : "Extract observations"}
                      </button>
                    </div>
                    {profileObservationItems.length === 0 ? (
                      <p className="muted">No accepted observations.</p>
                    ) : (
                      <div className="audience-observation-list">
                        {profileObservationItems.map((observation) => {
                          const draft = observationDrafts[observation.id] ?? {
                            text: observation.text,
                            observation_type: observation.observation_type,
                          };
                          return (
                            <article
                              className={`audience-observation ${observation.review_status === "stale" ? "stale" : ""}`}
                              key={observation.id}
                            >
                              <div className="audience-observation-heading">
                                <span>
                                  {observation.review_status === "stale"
                                    ? "Needs review — speaker mapping changed"
                                    : observation.derivation === "user_entered"
                                      ? "User-entered observation"
                                      : "Accepted from transcript"}
                                </span>
                                <small>{observation.derivation}</small>
                              </div>
                              <ObservationTypeSelect
                                label="Observation type"
                                value={draft.observation_type}
                                onChange={(value) =>
                                  setObservationDrafts((current) => ({
                                    ...current,
                                    [observation.id]: {
                                      ...draft,
                                      observation_type: value,
                                    },
                                  }))
                                }
                                disabled={busy !== null}
                              />
                              <textarea
                                aria-label="Observation text"
                                value={draft.text}
                                onChange={(event) =>
                                  setObservationDrafts((current) => ({
                                    ...current,
                                    [observation.id]: {
                                      ...draft,
                                      text: event.target.value,
                                    },
                                  }))
                                }
                                maxLength={1500}
                                rows={2}
                                disabled={busy !== null}
                              />
                              <div className="audience-observation-actions">
                                <button
                                  type="button"
                                  className="secondary-button"
                                  onClick={() =>
                                    void updateObservation(observation)
                                  }
                                  disabled={busy !== null || !draft.text.trim()}
                                >
                                  Save edit
                                </button>
                                <button
                                  type="button"
                                  className="text-button danger-text"
                                  onClick={() =>
                                    void deleteObservation(observation)
                                  }
                                  disabled={busy !== null}
                                >
                                  Delete
                                </button>
                              </div>
                              <EvidenceList evidence={observation.evidence} />
                            </article>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {profileCandidateItems.length > 0 ? (
                    <div className="audience-observation-block audience-pending-block">
                      <strong>Pending suggestions</strong>
                      <p className="muted">
                        Suggested from transcript · provisional until accepted
                      </p>
                      <div className="audience-observation-list">
                        {profileCandidateItems.map((candidate) => {
                          const draft = candidateDrafts[candidate.id] ?? {
                            text: candidate.proposed_text,
                            observation_type: candidate.observation_type,
                          };
                          const canAccept = candidate.status === "pending";
                          return (
                            <article
                              className={`audience-observation candidate ${candidate.status === "stale" ? "stale" : ""}`}
                              key={candidate.id}
                            >
                              <div className="audience-observation-heading">
                                <span>
                                  {candidate.status === "stale"
                                    ? "Needs review — speaker mapping changed"
                                    : candidate.status === "pending"
                                      ? "Suggested from transcript"
                                      : `Candidate ${candidate.status}`}
                                </span>
                                <small>
                                  {candidate.confidence === null
                                    ? "confidence unavailable"
                                    : `confidence ${candidate.confidence.toFixed(2)}`}
                                </small>
                              </div>
                              <ObservationTypeSelect
                                label="Candidate observation type"
                                value={draft.observation_type}
                                onChange={(value) =>
                                  setCandidateDrafts((current) => ({
                                    ...current,
                                    [candidate.id]: {
                                      ...draft,
                                      observation_type: value,
                                    },
                                  }))
                                }
                                disabled={busy !== null || !canAccept}
                              />
                              <textarea
                                aria-label="Candidate observation text"
                                value={draft.text}
                                onChange={(event) =>
                                  setCandidateDrafts((current) => ({
                                    ...current,
                                    [candidate.id]: {
                                      ...draft,
                                      text: event.target.value,
                                    },
                                  }))
                                }
                                maxLength={1500}
                                rows={2}
                                disabled={busy !== null || !canAccept}
                              />
                              <div className="audience-observation-actions">
                                <button
                                  type="button"
                                  className="primary-button"
                                  onClick={() =>
                                    void acceptCandidate(candidate)
                                  }
                                  disabled={
                                    busy !== null ||
                                    !canAccept ||
                                    !draft.text.trim()
                                  }
                                >
                                  Edit &amp; accept
                                </button>
                                <button
                                  type="button"
                                  className="secondary-button"
                                  onClick={() =>
                                    void rejectCandidate(candidate)
                                  }
                                  disabled={busy !== null || !canAccept}
                                >
                                  Reject
                                </button>
                              </div>
                              <EvidenceList evidence={candidate.evidence} />
                            </article>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section
        className="audience-subsection"
        aria-labelledby="user-observation-title"
      >
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Manual project knowledge</p>
            <h3 id="user-observation-title">Add user-entered observation</h3>
          </div>
        </div>
        <div className="audience-user-observation-form">
          <label>
            Profile
            <select
              value={userObservationProfileId}
              onChange={(event) =>
                setUserObservationProfileId(event.target.value)
              }
              disabled={busy !== null || profiles.length === 0}
            >
              <option value="">Choose a profile</option>
              {profiles.map((profile) => (
                <option value={profile.id} key={profile.id}>
                  {profileLabel(profile)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Type
            <ObservationTypeSelect
              label="User observation type"
              value={userObservationType}
              onChange={setUserObservationType}
              disabled={busy !== null}
            />
          </label>
          <label className="audience-user-observation-text">
            Text
            <textarea
              value={userObservationText}
              onChange={(event) => setUserObservationText(event.target.value)}
              maxLength={1500}
              rows={2}
            />
          </label>
          <button
            type="button"
            className="secondary-button"
            onClick={() => void createUserObservation()}
            disabled={
              busy !== null ||
              !userObservationProfileId ||
              !userObservationText.trim()
            }
          >
            Save observation
          </button>
        </div>
      </section>
    </section>
  );
}
