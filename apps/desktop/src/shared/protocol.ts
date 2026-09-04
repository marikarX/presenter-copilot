export const PROTOCOL_VERSION = 1 as const;

export const CORE_METHODS = [
  "core.hello",
  "core.health",
  "core.shutdown",
  "project.create",
  "project.open",
  "project.list",
  "project.update_settings",
  "project.acknowledge_remote_reasoning",
  "project.delete",
  "source.import",
  "source.list",
  "source.preview",
  "source.delete",
  "source.reindex",
  "transcript.list_speakers",
  "transcript.map_speaker",
  "transcript.unmap_speaker",
  "audience.create",
  "audience.update",
  "audience.list",
  "audience.delete",
  "audience.extract_observations",
  "audience.list_observations",
  "audience.accept_observation",
  "audience.reject_observation",
  "audience.create_observation",
  "audience.update_observation",
  "audience.delete_observation",
  "audience.build_context",
  "search.lexical",
  "retrieval.health",
  "retrieval.query",
  "retrieval.rebuild",
  "session.start",
  "session.stop",
  "session.get",
  "session.list",
  "session.delete",
  "assist.request",
  "assist.cancel",
  "cue.list",
  "cue.dismiss",
  "cue.expand_sources",
  "hud.settings.get",
  "hud.settings.update",
  "asr.list_devices",
  "asr.configure",
  "asr.prepare_model",
  "asr.start",
  "asr.stop",
  "asr.status",
  "models.status",
  "models.prepare",
  "models.remove",
  "presentation.detect",
  "presentation.set_slide",
  "presentation.next_slide",
  "presentation.previous_slide",
  "presentation.status",
  "run.mark_event",
  "run.generate_debrief",
  "run.get_state",
  "run.list_transcript",
  "run.list_timeline",
  "run.get_debrief",
  "teach.next_prompt",
  "teach.get_state",
  "teach.submit_text",
  "teach.discard_answer",
  "teach.confirm_knowledge_item",
  "teach.reject_knowledge_item",
  "challenge.configure",
  "challenge.next_question",
  "challenge.submit_answer",
  "challenge.retry_question",
  "challenge.save_preferred_answer",
  "challenge.get_state",
  "challenge.list_history",
  "knowledge.list",
  "knowledge.update_flags",
  "knowledge.delete",
  "speaker_profile.get",
  "speaker_profile.list_evidence",
  "speaker_profile.approve_evidence",
  "speaker_profile.remove_evidence",
  "speaker_profile.update_settings",
  "speaker_profile.reset",
  "provider.list",
  "provider.configure",
  "provider.test",
  "provider.status",
  "provider.credentials.status",
  "provider.credentials.save_detected",
  "provider.credentials.remove",
  "diagnostics.preview",
  "diagnostics.export",
  "app.reset_local_data",
  "privacy.list_context_manifests",
] as const;

export type CoreMethod = (typeof CORE_METHODS)[number];

export const CORE_EVENTS = [
  "core.ready",
  "core.error",
  "source.import_progress",
  "source.import_error",
  "project.index_progress",
  "project.index_ready",
  "teach.prompt",
  "teach.knowledge_candidate",
  "challenge.question",
  "challenge.evaluation",
  "session.started",
  "session.stopped",
  "asr.model_loading",
  "asr.ready",
  "asr.partial",
  "asr.final",
  "asr.device_error",
  "presentation.slide_changed",
  "presentation.status_changed",
  "run.debrief_progress",
  "provider.status_changed",
  "privacy.remote_context_manifest",
  "assist.started",
  "assist.retrieval_ready",
  "assist.reasoning_started",
  "cue.partial",
  "cue.ready",
  "cue.error",
  "models.progress",
] as const;

export type CoreEvent = (typeof CORE_EVENTS)[number];
// Keep forward compatibility for additive sidecar events while documenting
// the current milestone event contract above.
export type EventName = CoreEvent | (string & {});

export const RENDERER_CORE_METHODS = [
  "core.health",
  "project.create",
  "project.open",
  "project.list",
  "project.update_settings",
  "project.acknowledge_remote_reasoning",
  "project.delete",
  "source.list",
  "source.preview",
  "source.delete",
  "source.reindex",
  "transcript.list_speakers",
  "transcript.map_speaker",
  "transcript.unmap_speaker",
  "audience.create",
  "audience.update",
  "audience.list",
  "audience.delete",
  "audience.extract_observations",
  "audience.list_observations",
  "audience.accept_observation",
  "audience.reject_observation",
  "audience.create_observation",
  "audience.update_observation",
  "audience.delete_observation",
  "retrieval.health",
  "retrieval.query",
  "retrieval.rebuild",
  "session.start",
  "session.stop",
  "session.get",
  "session.list",
  "session.delete",
  "assist.request",
  "assist.cancel",
  "cue.list",
  "cue.dismiss",
  "cue.expand_sources",
  "asr.list_devices",
  "asr.configure",
  "asr.prepare_model",
  "asr.start",
  "asr.stop",
  "asr.status",
  "models.status",
  "models.prepare",
  "models.remove",
  "presentation.detect",
  "presentation.set_slide",
  "presentation.next_slide",
  "presentation.previous_slide",
  "presentation.status",
  "run.mark_event",
  "run.generate_debrief",
  "run.get_state",
  "run.list_transcript",
  "run.list_timeline",
  "run.get_debrief",
  "teach.next_prompt",
  "teach.get_state",
  "teach.submit_text",
  "teach.discard_answer",
  "teach.confirm_knowledge_item",
  "teach.reject_knowledge_item",
  "challenge.configure",
  "challenge.next_question",
  "challenge.submit_answer",
  "challenge.retry_question",
  "challenge.save_preferred_answer",
  "challenge.get_state",
  "challenge.list_history",
  "knowledge.list",
  "knowledge.update_flags",
  "knowledge.delete",
  "speaker_profile.get",
  "speaker_profile.list_evidence",
  "speaker_profile.approve_evidence",
  "speaker_profile.remove_evidence",
  "speaker_profile.update_settings",
  "speaker_profile.reset",
  "provider.list",
  "provider.configure",
  "provider.test",
  "provider.status",
  "provider.credentials.status",
  "provider.credentials.save_detected",
  "provider.credentials.remove",
  "app.reset_local_data",
  "privacy.list_context_manifests",
] as const;
export type RendererCoreMethod = (typeof RENDERER_CORE_METHODS)[number];
export type JsonObject = Record<string, unknown>;

export interface RequestEnvelope {
  protocol_version: typeof PROTOCOL_VERSION;
  type: "request";
  request_id: string;
  method: CoreMethod;
  params: JsonObject;
}

export interface CoreError {
  code: string;
  message: string;
  retryable: boolean;
  details: JsonObject;
}

export interface InvokeSuccess<T> {
  ok: true;
  result: T;
}

export interface InvokeFailure {
  ok: false;
  error: CoreError;
}

export type InvokeResult<T = unknown> = InvokeSuccess<T> | InvokeFailure;

export interface SuccessResponse<T = unknown> {
  protocol_version: typeof PROTOCOL_VERSION;
  type: "response";
  request_id: string | null;
  ok: true;
  result: T;
}

export interface ErrorResponse {
  protocol_version: typeof PROTOCOL_VERSION;
  type: "response";
  request_id: string | null;
  ok: false;
  error: CoreError;
}

export type ResponseEnvelope<T = unknown> = SuccessResponse<T> | ErrorResponse;

export interface EventEnvelope {
  protocol_version: typeof PROTOCOL_VERSION;
  type: "event";
  event: EventName;
  payload: JsonObject;
}

export interface CoreCapabilities {
  methods: string[];
  events: string[];
}

export interface CoreMetadata {
  protocol_version: typeof PROTOCOL_VERSION;
  core_version: string;
  capabilities: CoreCapabilities;
  adapters: string[];
  migration_status: string;
  storage?: {
    app_schema_version: number;
    project_schema_version: number;
  };
}

interface ProjectSummaryCommon {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  last_opened_at?: string | null;
}

export interface ReadyProjectSummary extends ProjectSummaryCommon {
  storage_status: "ready";
  privacy_mode: string;
  default_style_policy: string;
  custom_style_guidance: string | null;
  style_override_enabled: boolean;
  remote_reasoning_acknowledged_at: string | null;
  remote_reasoning_acknowledged: boolean;
  source_count: number;
}

export interface UnavailableProjectSummary extends ProjectSummaryCommon {
  storage_status: "unavailable";
  storage_error_code: string;
}

export type ProjectSummary = ReadyProjectSummary | UnavailableProjectSummary;

export function isCoreError(value: unknown): value is CoreError {
  return (
    isJsonObject(value) &&
    typeof value.code === "string" &&
    typeof value.message === "string" &&
    typeof value.retryable === "boolean" &&
    isJsonObject(value.details)
  );
}

export function isReadyProjectSummary(
  value: unknown,
): value is ReadyProjectSummary {
  return (
    isJsonObject(value) &&
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string" &&
    value.storage_status === "ready" &&
    typeof value.privacy_mode === "string" &&
    typeof value.default_style_policy === "string" &&
    (value.custom_style_guidance === null ||
      typeof value.custom_style_guidance === "string") &&
    typeof value.style_override_enabled === "boolean" &&
    (value.remote_reasoning_acknowledged_at === null ||
      typeof value.remote_reasoning_acknowledged_at === "string") &&
    typeof value.remote_reasoning_acknowledged === "boolean" &&
    typeof value.source_count === "number"
  );
}

export function isUnavailableProjectSummary(
  value: unknown,
): value is UnavailableProjectSummary {
  return (
    isJsonObject(value) &&
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string" &&
    value.storage_status === "unavailable" &&
    typeof value.storage_error_code === "string"
  );
}

export function isProjectSummary(value: unknown): value is ProjectSummary {
  return isReadyProjectSummary(value) || isUnavailableProjectSummary(value);
}

export function unwrapInvokeResult<T>(response: InvokeResult<T>): T {
  if (response.ok) return response.result;
  throw response.error;
}

export interface SourceSummary {
  id: string;
  project_id: string;
  kind: string;
  original_name: string;
  source_type: string;
  mime_type: string;
  parser_id: string;
  sha256: string;
  imported_at: string;
  parse_status: "pending" | "ready" | "error";
  parse_error?: { code: string; message: string };
  byte_size: number;
  source_units_count: number;
  chunks_count: number;
  snapshot_name: string | null;
  metadata: JsonObject;
}

export interface RetrievalHealthResult {
  project_id: string;
  status: string;
  model_available: boolean;
  model_loaded: boolean;
  adapter_id: string;
  model_id: string;
  model_fingerprint: string | null;
  dimension: number | null;
  model_load_ms: number | null;
  active_generation_id: string | null;
  matrix_row_count: number;
  current_indexed_mappings: number;
  current_project_chunk_count: number;
  current_knowledge_item_count: number;
  current_indexable_entity_count: number;
  semantic_coverage: number;
  stale_reason: string | null;
  index_model_id: string | null;
  index_model_fingerprint: string | null;
  index_dimension: number | null;
}

export interface RetrievalSemanticStatus {
  status: string;
  coverage: number;
  adapter_id: string;
  model_id: string;
  model_fingerprint: string | null;
  dimension: number | null;
  model_loaded: boolean;
  generation_id: string | null;
  matrix_row_count: number;
  stale_reason: string | null;
}

export interface RetrievalHit {
  evidence: {
    evidence_id: string;
    source_type: string;
    source_id: string;
    source_unit_id: string | null;
    knowledge_item_id?: string | null;
    preferred?: boolean;
    private?: boolean;
    use_live?: boolean;
    use_rehearsal?: boolean;
    label: string;
    text: string;
    rank: number;
    score: number;
    fact_safe: boolean;
  };
  scores: {
    semantic: number;
    lexical: number;
    lexical_raw: number;
    slide_boost: number;
    user_knowledge_boost?: number;
    final: number;
  };
  reasons: string[];
}

export interface RetrievalConflict {
  kind: string;
  subject: string;
  value_type: string;
  values: Array<{
    normalized_value: string;
    value_type: string;
    evidence_ids: string[];
  }>;
  evidence: Array<{ evidence_id: string; label: string }>;
}

export interface RetrievalQueryResult {
  project_id: string;
  query: string;
  mode: string;
  latency_ms: number;
  semantic: RetrievalSemanticStatus;
  hits: RetrievalHit[];
  conflicts: RetrievalConflict[];
}

export interface RetrievalRebuildResult {
  project_id: string;
  status: string;
  generation_id: string;
  model_id: string;
  model_fingerprint: string;
  dimension: number;
  matrix_row_count: number;
  indexed_count: number;
  coverage: number;
  reused_count: number;
  embedded_count: number;
}

export interface SourceUnitPreview {
  id: string;
  unit_type: string;
  ordinal: number | null;
  start_ms: number | null;
  end_ms: number | null;
  speaker_label: string | null;
  title: string | null;
  title_truncated: boolean;
  text: string;
  text_truncated: boolean;
  metadata: JsonObject;
  provenance: JsonObject;
}

export interface SourcePreviewResult {
  document: SourceSummary;
  units: SourceUnitPreview[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface ImportSourceResult {
  cancelled?: boolean;
  duplicate?: boolean;
  document?: SourceSummary;
  source_units_count?: number;
  chunks_count?: number;
  status?: string;
}

export interface AudienceProfileSummary {
  id: string;
  display_name: string;
  role: string | null;
  organization: string | null;
  active: boolean;
}

export interface TranscriptSpeakerSummary {
  document_id: string;
  document_name: string;
  native_speaker_label: string;
  segment_count: number;
  first_start_ms: number | null;
  last_end_ms: number | null;
  audience_profile: AudienceProfileSummary | null;
}

export interface AudienceProfile extends AudienceProfileSummary {
  project_id: string;
  user_notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface AudienceEvidence {
  provenance_type: "transcript";
  provenance_id: string;
  source_type: "transcript";
  source_id: string;
  source_unit_id: string;
  label: string;
  text: string;
}

export type AudienceObservationType =
  | "topic_interest"
  | "question_pattern"
  | "answer_preference"
  | "recurring_objection"
  | "interaction_pattern"
  | "decision_criterion";

export interface AudienceObservation {
  id: string;
  audience_profile_id: string;
  observation_type: AudienceObservationType;
  text: string;
  derivation: "user_entered" | "source_derived" | "ai_inferred";
  confidence: number | null;
  sensitive_trait: boolean;
  review_status: "active" | "stale";
  created_at: string;
  updated_at: string;
  evidence: AudienceEvidence[];
}

export interface AudienceObservationCandidate {
  id: string;
  audience_profile_id: string;
  observation_type: AudienceObservationType;
  proposed_text: string;
  confidence: number | null;
  fingerprint: string;
  status: "pending" | "accepted" | "rejected" | "stale";
  observation_id: string | null;
  created_at: string;
  updated_at: string;
  evidence: AudienceEvidence[];
  provisional: boolean;
}

export type ChallengeIntensity = "normal" | "skeptical" | "adversarial";
export type ChallengeScope = "full_deck" | "slide_range";

export interface ChallengeConfig {
  session_id: string;
  intensity: ChallengeIntensity;
  allow_follow_ups: boolean;
  scope: ChallengeScope;
  slide_start: number | null;
  slide_end: number | null;
  state: "ready_for_question" | "awaiting_answer" | "evaluated";
  created_at: string;
  updated_at: string;
}

export interface ChallengeAudienceSummary {
  id: string | null;
  display_name: string;
  role: string | null;
  organization: string | null;
  active: boolean;
  available: boolean;
  selection_order: number;
}

export interface ChallengeEvidenceRef {
  evidence_id: string;
  source_type: string;
  source_id: string;
  source_unit_id: string | null;
  label: string;
  available: boolean;
}

export interface ChallengeQuestion {
  id: string;
  session_id: string;
  audience_profile_id: string | null;
  audience: {
    id: string | null;
    display_name: string;
    role: string | null;
    organization: string | null;
    available: boolean;
    historical: boolean;
  };
  parent_question_id: string | null;
  text: string;
  origin: "simulated";
  rationale: string;
  evidence: ChallengeEvidenceRef[];
  audience_observations: Array<{ observation_id: string; available: boolean }>;
  created_at: string;
}

export interface ChallengeScore {
  score: number | null;
  feedback: string;
}

export interface ChallengeEvaluation {
  correctness: ChallengeScore;
  directness: ChallengeScore;
  completeness: ChallengeScore;
  concision: ChallengeScore;
  style_match: ChallengeScore;
  source_support: {
    status: "supported" | "partially_supported" | "unsupported" | "conflicted";
    feedback: string;
  };
  missing_points: string[];
  supported_evidence_ids: string[];
  strongest_prior_phrasing?: string;
  word_count?: number;
  estimated_speaking_seconds?: number;
  preferred_answer_seconds?: number | null;
}

export interface ChallengeAnswerVersion {
  id: string;
  question_id: string;
  session_id: string;
  text: string;
  origin: "user_typed" | "user_spoken" | "user_edited" | "ai_suggested";
  preferred: boolean;
  evaluation: ChallengeEvaluation | null;
  evidence: ChallengeEvidenceRef[];
  created_at: string;
}

export interface ChallengeReasoningStatus {
  route: string;
  reason: string;
  provider_id: string | null;
  provider_status: string;
  privacy_mode: string;
}

export interface ChallengeStateResult {
  project_id: string;
  session_id: string;
  session_status: Session["status"];
  state: "unconfigured" | ChallengeConfig["state"];
  config: ChallengeConfig | null;
  audiences: ChallengeAudienceSummary[];
  current_question: ChallengeQuestion | null;
  latest_answer_version: ChallengeAnswerVersion | null;
  valid_next_actions: string[];
  reasoning: ChallengeReasoningStatus;
}

export interface ChallengeHistoryItem extends ChallengeQuestion {
  answer_versions: ChallengeAnswerVersion[];
}

export interface ChallengeHistoryResult {
  project_id: string;
  session_id: string;
  items: ChallengeHistoryItem[];
  limit: number;
  offset: number;
  has_more: boolean;
  total: number;
}

export interface Session {
  id: string;
  project_id: string;
  mode: "teach" | "challenge" | "run" | "live_assist";
  started_at: string;
  ended_at: string | null;
  style_policy: string;
  privacy_mode: string;
  provider_id: string | null;
  current_slide_start: number | null;
  status: "active" | "completed" | "aborted" | "error";
  teach_state: string;
  utterances: number;
  pending_candidates: number;
  provider_runs: number;
  cues: number;
}

export type CueType =
  "fact" | "structure" | "reminder" | "source_pointer" | "warning";
export type CueRoute =
  "retrieval_only" | "local_reasoning" | "remote_reasoning";

export interface CueEvidenceRef {
  evidence_id: string;
  source_type: string;
  source_id: string;
  source_unit_id: string | null;
  knowledge_item_id: string | null;
  label: string;
  rank: number;
  available: boolean;
}

export interface Cue {
  id: string;
  project_id: string;
  session_id: string;
  assist_id: string;
  cue_type: CueType;
  text: string;
  lines: string[];
  state: "partial" | "final";
  route: CueRoute;
  provider_run_id: string | null;
  created_at: string;
  displayed_at: string | null;
  dismissed_at: string | null;
  evidence: CueEvidenceRef[];
}

export interface CueSourceProjection {
  evidence_id: string;
  label: string;
  source_name: string | null;
  pointer: {
    source_type: string;
    source_id: string;
    source_unit_id: string | null;
    knowledge_item_id: string | null;
  };
  excerpt: string | null;
  available: boolean;
  rank: number;
}

export interface AssistRequestResult {
  assist_id: string;
  project_id: string;
  session_id: string;
  status: "started";
  question_origin: "typed" | "live_partial" | "live_window" | "live_final";
}

export type HudSettingsUpdate = Partial<
  Pick<HudSettings, "display_id" | "width" | "font_size" | "top_offset">
> & {
  shortcuts?: Partial<HudSettings["shortcuts"]>;
};

export interface CueListResult {
  project_id: string;
  session_id: string;
  cues: Cue[];
  limit: number;
  offset: number;
  total: number;
  has_more: boolean;
}

export interface CueExpandSourcesResult {
  project_id: string;
  session_id: string;
  cue: Cue;
  sources: CueSourceProjection[];
}

export interface HudDisplay {
  id: string;
  workArea: { x: number; y: number; width: number; height: number };
  scaleFactor: number;
  primary: boolean;
}

export interface HudSettings {
  display_id: string | null;
  width: number;
  font_size: number;
  top_offset: number;
  shortcuts: {
    push_to_assist: string;
    show_hide: string;
    expand_collapse: string;
    previous_cue: string;
    next_cue: string;
    clear: string;
    previous_slide: string;
    next_slide: string;
  };
}

export interface HudStatus {
  visible: boolean;
  expanded: boolean;
  core_state: CoreClientState;
  font_size: number;
  capture_protection: "enabled" | "unsupported" | "error";
  capture_protection_message: string;
  shortcuts_registered: boolean;
}

export interface PresenterCopilotHudApi {
  ready(): Promise<InvokeResult<{ ready: true }>>;
  onEvent(listener: (event: EventEnvelope) => void): () => void;
  onStatus(listener: (status: HudStatus) => void): () => void;
  onCue(listener: (cue: JsonObject) => void): () => void;
  onClear(listener: () => void): () => void;
  setExpanded(expanded: boolean): Promise<InvokeResult<{ expanded: boolean }>>;
  pushToAssist(): Promise<InvokeResult<{ requested: true }>>;
  expandSources(cueId: string): Promise<InvokeResult<CueExpandSourcesResult>>;
  dismiss(cueId: string): Promise<InvokeResult<JsonObject>>;
  navigate(direction: "previous" | "next"): Promise<InvokeResult<JsonObject>>;
}

export interface AudioDevice {
  device_id: string;
  display_name: string;
  host_api: string;
  max_input_channels: number;
  default_sample_rate: number;
  is_default: boolean;
}

export interface ASRStatus {
  adapter_id: string;
  model_id: string;
  model_status: string;
  device: AudioDevice | null;
  capture_state: "stopped" | "running" | "stopping";
  session_id: string | null;
  language: string;
  input_signal_state: "unknown" | "silent" | "detected";
  input_frames_received: number;
  last_error_code: string | null;
  config: {
    adapter_id: string;
    model_id: string;
    language: string;
    device_id: string | null;
  };
  capabilities: JsonObject;
}

export interface PresentationStatus {
  project_id: string;
  session_id: string;
  mode: "manual" | "powerpoint";
  reason: string;
  current_slide: number | null;
  slide_count: number | null;
  tracking: "active" | "stopped";
}

export type RunMarkerType = "question" | "weak_point" | "note";

export interface RunMarker {
  id: string;
  session_id: string;
  marker_type: RunMarkerType;
  timestamp_ms: number;
  slide_ordinal: number | null;
  note: string | null;
  created_at?: string | null;
}

export interface RunSlideStateEvent {
  id: string;
  session_id: string;
  slide_ordinal: number;
  timestamp_ms: number;
  source: "powerpoint" | "manual" | "inferred";
  created_at: string | null;
}

export interface RunUtterance {
  utterance_id: string;
  text: string;
  start_ms: number | null;
  end_ms: number | null;
  confidence: number | null;
  slide_ordinal: number | null;
}

export interface RunState {
  project_id: string;
  session_id: string;
  mode: "run";
  status: Session["status"];
  started_at: string;
  ended_at: string | null;
  duration_ms: number;
  current_slide: number | null;
  slide_count: number | null;
  presentation_mode: "manual" | "powerpoint";
  presentation_reason: string;
  tracking: "active" | "stopped";
  transcript_count: number;
  timeline_count: number;
  marker_count: number;
  debrief_available: boolean;
}

export interface RunTranscriptResult {
  project_id: string;
  session_id: string;
  utterances: RunUtterance[];
  limit: number;
  offset: number;
  total: number;
  has_more: boolean;
}

export interface RunTimelineResult {
  project_id: string;
  session_id: string;
  slide_events: RunSlideStateEvent[];
  markers: RunMarker[];
  timeline: Array<
    ({ kind: "slide" } & RunSlideStateEvent) | ({ kind: "marker" } & RunMarker)
  >;
  limit: number;
  offset: number;
  total: number;
  has_more: boolean;
}

export interface RunDebrief {
  algorithm_version: string;
  session: {
    session_id: string;
    duration_ms: number;
    word_count: number;
    utterance_count: number;
  };
  per_slide: Array<{
    slide_ordinal: number | null;
    speaking_time_ms: number;
    word_count: number;
    utterance_count: number;
  }>;
  markers: RunMarker[];
  long_segments: Array<{
    utterance_id: string;
    slide_ordinal: number | null;
    duration_ms: number;
    word_count: number;
    excerpt: string;
  }>;
  evidence_review_candidates: Array<{
    utterance_id: string;
    slide_ordinal: number | null;
    excerpt: string;
    status: "needs_evidence_review" | "conflict_review";
    evidence: Array<JsonObject>;
    conflicts: Array<JsonObject>;
  }>;
  best_explanation_candidates: Array<{
    utterance_id: string;
    slide_ordinal: number | null;
    excerpt: string;
    evidence: Array<JsonObject>;
  }>;
  recommended_challenge_questions: string[];
}

export interface RunDebriefResult {
  project_id: string;
  session_id: string;
  debrief: RunDebrief | null;
  algorithm_version?: string;
  transcript_fingerprint?: string;
  created_at?: string;
  updated_at?: string;
  reused?: boolean;
}

export interface ManualShortcutResult {
  registered: boolean;
  previous_shortcut: string;
  next_shortcut: string;
  error_code?: string;
}

export interface TeachCandidate {
  id: string;
  source_utterance_id: string;
  proposed_kind: string;
  proposed_text: string;
  follow_up_question?: string | null;
  provisional: boolean;
  created_by: string;
}

export interface KnowledgeItem {
  id: string;
  project_id: string;
  kind: string;
  text: string;
  use_live: boolean;
  use_rehearsal: boolean;
  preferred: boolean;
  private: boolean;
  created_by: string;
  origin_session_id: string | null;
  created_at: string;
  updated_at: string;
  evidence: Array<{ provenance_type: string; provenance_id: string }>;
}

export interface SpeakerProfile {
  id: string;
  display_name: string | null;
  default_style_policy: string;
  custom_style_guidance: string | null;
  preferred_answer_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export interface SpeakerEvidence {
  id: string;
  evidence_type: string;
  text: string;
  origin_project_id: string | null;
  origin_session_id: string | null;
  user_approved: boolean;
  created_at: string;
  origin_project_name?: string | null;
}

export interface ProviderStatus {
  provider_id: string;
  enabled: boolean;
  model_id: string;
  credential_source: string;
  safe_config: JsonObject;
  health: {
    provider_id: string;
    locality: string;
    model_id: string;
    status: ProviderHealthStatus;
    configured: boolean;
    error_code: string | null;
    retryable: boolean;
  };
  capabilities: {
    structured_outputs: boolean;
    streaming: boolean;
    cancellation: boolean;
    task_types: string[];
  };
}

export interface ModelStatusSummary {
  kind: "asr" | "embeddings";
  adapter_id: string;
  model_id: string;
  status: string;
  local_only: boolean;
  cache_location: string;
  disk_requirement_mb: number | null;
  preparing: boolean;
  error_code: string | null;
}

export interface ModelsStatusResult {
  network_policy: {
    runtime: "local_files_only";
    prepare: "explicit_user_action_only";
  };
  models: ModelStatusSummary[];
}

export interface CredentialStatus {
  provider_id: string;
  credential_source: string;
  configured: boolean;
  secure_store_available: boolean;
  environment_detected: boolean;
}

export const DIAGNOSTIC_SECTIONS = [
  "core",
  "storage",
  "models",
  "provider",
  "logs",
  "benchmarks",
] as const;
export type DiagnosticSection = (typeof DIAGNOSTIC_SECTIONS)[number];

export interface DiagnosticPreviewResult {
  schema_version: number;
  timestamp: string;
  [section: string]: unknown;
}

export interface DiagnosticSaveResult {
  cancelled?: boolean;
  exported?: boolean;
  format?: "zip";
  file_name?: string;
  size_bytes?: number;
  included_sections?: DiagnosticSection[];
}

export interface ResetLocalDataResult {
  reset: true;
  projects_removed: number;
  project_directories_removed: number;
  model_cache_retained: boolean;
  credentials_removed: boolean;
  stored_credential_present: boolean;
  credential_cleanup_established: boolean;
  environment_credential_detected: boolean;
  environment_credential_retained: true;
}

export type ProviderHealthStatus =
  | "ready"
  | "unconfigured"
  | "auth_failed"
  | "quota_exhausted"
  | "rate_limited"
  | "unavailable";

export interface ContextManifest {
  provider_content_boundary?: string;
  provider_id?: string;
  task_type?: string;
  privacy_mode?: string;
  classes_sent?: string[];
  source_ids?: string[];
  knowledge_item_ids?: string[];
  speaker_evidence_ids?: string[];
  audience_profile_ids?: string[];
  audience_observation_ids?: string[];
  prior_question_count?: number;
  raw_audio_sent?: boolean;
  full_document_sent?: boolean;
  full_corpus_sent?: boolean;
  private_items_sent?: boolean;
  bounded_context_chars?: number;
}

export interface ContextManifestHistoryItem {
  provider_run_id: string;
  session_id: string | null;
  task_type: string;
  provider_id: string;
  privacy_mode: string;
  started_at: string;
  ended_at: string | null;
  status: "started" | "success" | "error" | "cancelled";
  input_token_count: number | null;
  output_token_count: number | null;
  latency_ms: number | null;
  error_code: string | null;
  context_manifest: ContextManifest;
}

export interface PrivacyContextManifestResult {
  project_id: string;
  session_id: string | null;
  manifests: ContextManifestHistoryItem[];
  limit: number;
  offset: number;
  total: number;
  has_more: boolean;
}

export interface HealthResult {
  status: "ok";
  ready: true;
  protocol_version: typeof PROTOCOL_VERSION;
  core_version: string;
  uptime_ms: number;
}

export type CoreClientState =
  "stopped" | "starting" | "ready" | "stopping" | "unavailable";

export interface CoreStatus {
  state: CoreClientState;
  protocolVersion: number | null;
  coreVersion: string | null;
  health: HealthResult | null;
  error: CoreError | null;
}

export interface PresenterCopilotApi {
  core: {
    request<T = unknown>(
      method: RendererCoreMethod,
      params?: JsonObject,
    ): Promise<InvokeResult<T>>;
    getStatus(): Promise<InvokeResult<CoreStatus>>;
    onEvent(listener: (event: EventEnvelope) => void): () => void;
    onStatus(listener: (status: CoreStatus) => void): () => void;
  };
  source: {
    pickAndImport(
      projectId: string,
      kind?: "presentation" | "supporting" | "transcript",
    ): Promise<InvokeResult<ImportSourceResult>>;
  };
  diagnostics: {
    preview(
      sections?: DiagnosticSection[],
    ): Promise<InvokeResult<DiagnosticPreviewResult>>;
    save(
      sections?: DiagnosticSection[],
    ): Promise<InvokeResult<DiagnosticSaveResult>>;
  };
  shortcuts: {
    enableManualRun(
      projectId: string,
      sessionId: string,
    ): Promise<InvokeResult<ManualShortcutResult>>;
    disableManualRun(): Promise<InvokeResult<{ disabled: true }>>;
  };
  hud: {
    getStatus(): Promise<InvokeResult<HudStatus>>;
    getSettings(): Promise<InvokeResult<HudSettings>>;
    updateSettings(
      settings: HudSettingsUpdate,
    ): Promise<InvokeResult<HudSettings>>;
    getDisplays(): Promise<InvokeResult<{ displays: HudDisplay[] }>>;
    show(): Promise<InvokeResult<{ visible: true }>>;
    hide(): Promise<InvokeResult<{ visible: false }>>;
  };
}

export function isCoreMethod(value: unknown): value is CoreMethod {
  return (
    typeof value === "string" &&
    (CORE_METHODS as readonly string[]).includes(value)
  );
}

export function isRendererCoreMethod(
  value: unknown,
): value is RendererCoreMethod {
  return (
    typeof value === "string" &&
    (RENDERER_CORE_METHODS as readonly string[]).includes(value)
  );
}

export function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isCoreMetadata(value: unknown): value is CoreMetadata {
  if (!isJsonObject(value)) return false;
  const capabilities = value.capabilities;
  return (
    value.protocol_version === PROTOCOL_VERSION &&
    typeof value.core_version === "string" &&
    isJsonObject(capabilities) &&
    Array.isArray(capabilities.methods) &&
    capabilities.methods.every((method) => typeof method === "string") &&
    Array.isArray(capabilities.events) &&
    capabilities.events.every((event) => typeof event === "string") &&
    Array.isArray(value.adapters) &&
    value.adapters.every((adapter) => typeof adapter === "string") &&
    typeof value.migration_status === "string"
  );
}

export function isHealthResult(value: unknown): value is HealthResult {
  return (
    isJsonObject(value) &&
    value.status === "ok" &&
    value.ready === true &&
    value.protocol_version === PROTOCOL_VERSION &&
    typeof value.core_version === "string" &&
    typeof value.uptime_ms === "number"
  );
}

declare global {
  interface Window {
    presenterCopilot: PresenterCopilotApi;
    presenterCopilotHud: PresenterCopilotHudApi;
  }
}
