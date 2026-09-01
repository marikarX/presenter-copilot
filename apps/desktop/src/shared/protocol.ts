export const PROTOCOL_VERSION = 1 as const;

export const CORE_METHODS = [
  "core.hello",
  "core.health",
  "core.shutdown",
] as const;

export type CoreMethod = (typeof CORE_METHODS)[number];
export const RENDERER_CORE_METHODS = ["core.health"] as const;
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
    ): Promise<T>;
    getStatus(): Promise<CoreStatus>;
    onEvent(listener: (event: EventEnvelope) => void): () => void;
    onStatus(listener: (status: CoreStatus) => void): () => void;
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
