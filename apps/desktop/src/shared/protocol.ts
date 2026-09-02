export const PROTOCOL_VERSION = 1 as const;

export const CORE_METHODS = [
  "core.hello",
  "core.health",
  "core.shutdown",
  "project.create",
  "project.open",
  "project.list",
  "project.update_settings",
  "project.delete",
  "source.import",
  "source.list",
  "source.preview",
  "source.delete",
  "source.reindex",
  "search.lexical",
  "retrieval.health",
  "retrieval.query",
  "retrieval.rebuild",
] as const;

export type CoreMethod = (typeof CORE_METHODS)[number];
export const RENDERER_CORE_METHODS = [
  "core.health",
  "project.create",
  "project.open",
  "project.list",
  "project.update_settings",
  "project.delete",
  "source.list",
  "source.preview",
  "source.delete",
  "source.reindex",
  "retrieval.health",
  "retrieval.query",
  "retrieval.rebuild",
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
  event: string;
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
    source_unit_id: string;
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
      kind?: "presentation" | "supporting",
    ): Promise<InvokeResult<ImportSourceResult>>;
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
  }
}
