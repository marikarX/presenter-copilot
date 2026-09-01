import { randomUUID } from "node:crypto";
import {
  spawn,
  type ChildProcessWithoutNullStreams,
  type SpawnOptions,
} from "node:child_process";

import {
  isCoreMetadata,
  isJsonObject,
  PROTOCOL_VERSION,
  type CoreError,
  type CoreMetadata,
  type CoreMethod,
  type CoreStatus,
  type EventEnvelope,
  type HealthResult,
  type JsonObject,
} from "../shared/protocol";
import { NdjsonLineBuffer } from "./ndjson";

type SpawnSidecar = (
  command: string,
  args: string[],
  options: SpawnOptions,
) => ChildProcessWithoutNullStreams;

type PendingRequest = {
  resolve: (result: unknown) => void;
  reject: (reason: unknown) => void;
  timer: ReturnType<typeof setTimeout>;
};

type EventListener = (event: EventEnvelope) => void;
type StatusListener = (status: CoreStatus) => void;
type ProtocolErrorListener = (error: CoreClientError) => void;

const DEFAULT_REQUEST_TIMEOUT_MS = 3_000;
const DEFAULT_STARTUP_TIMEOUT_MS = 5_000;
const DEFAULT_SHUTDOWN_TIMEOUT_MS = 2_000;

export class CoreClientError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly details: JsonObject;

  constructor(error: CoreError) {
    super(error.message);
    this.name = "CoreClientError";
    this.code = error.code;
    this.retryable = error.retryable;
    this.details = error.details;
  }
}

export class CoreRequestTimeoutError extends Error {
  readonly code = "REQUEST_TIMEOUT";
  readonly requestId: string;

  constructor(requestId: string, timeoutMs: number) {
    super(`Core request ${requestId} timed out after ${timeoutMs} ms.`);
    this.name = "CoreRequestTimeoutError";
    this.requestId = requestId;
  }
}

export function toCoreError(
  error: unknown,
  fallbackCode = "SIDECAR_UNAVAILABLE",
  retryable = true,
): CoreError {
  if (error instanceof CoreClientError) {
    return {
      code: error.code,
      message: error.message,
      retryable: error.retryable,
      details: error.details,
    };
  }
  if (error instanceof CoreRequestTimeoutError) {
    return {
      code: error.code,
      message: error.message,
      retryable: true,
      details: { request_id: error.requestId },
    };
  }
  return {
    code: fallbackCode,
    message: error instanceof Error ? error.message : String(error),
    retryable,
    details: {},
  };
}

export class CoreProcessClient {
  private readonly command: string;
  private readonly args: string[];
  private readonly spawnOptions: SpawnOptions;
  private readonly spawnProcess: SpawnSidecar;
  private readonly requestTimeoutMs: number;
  private readonly startupTimeoutMs: number;
  private readonly shutdownTimeoutMs: number;
  private readonly lineBuffer = new NdjsonLineBuffer();
  private readonly pending = new Map<string, PendingRequest>();
  private readonly eventListeners = new Set<EventListener>();
  private readonly statusListeners = new Set<StatusListener>();
  private readonly protocolErrorListeners = new Set<ProtocolErrorListener>();

  private child: ChildProcessWithoutNullStreams | null = null;
  private metadata: CoreMetadata | null = null;
  private startPromise: Promise<CoreMetadata> | null = null;
  private resolveStart: ((metadata: CoreMetadata) => void) | null = null;
  private rejectStart: ((reason: unknown) => void) | null = null;
  private startupTimer: ReturnType<typeof setTimeout> | null = null;
  private exitPromise: Promise<void> | null = null;
  private resolveExit: (() => void) | null = null;
  private intentionalShutdown = false;
  private shutdownPromise: Promise<void> | null = null;
  private status: CoreStatus = {
    state: "stopped",
    protocolVersion: null,
    coreVersion: null,
    health: null,
    error: null,
  };

  constructor(options: {
    command: string;
    args?: string[];
    cwd?: string;
    env?: NodeJS.ProcessEnv;
    requestTimeoutMs?: number;
    startupTimeoutMs?: number;
    shutdownTimeoutMs?: number;
    spawnProcess?: SpawnSidecar;
  }) {
    this.command = options.command;
    this.args = options.args ?? [];
    this.spawnOptions = {
      cwd: options.cwd,
      env: options.env,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    };
    this.spawnProcess =
      options.spawnProcess ??
      ((command, args, spawnOptions) =>
        spawn(command, args, spawnOptions) as ChildProcessWithoutNullStreams);
    this.requestTimeoutMs =
      options.requestTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
    this.startupTimeoutMs =
      options.startupTimeoutMs ?? DEFAULT_STARTUP_TIMEOUT_MS;
    this.shutdownTimeoutMs =
      options.shutdownTimeoutMs ?? DEFAULT_SHUTDOWN_TIMEOUT_MS;
  }

  getStatus(): CoreStatus {
    return {
      ...this.status,
      error: this.status.error
        ? { ...this.status.error, details: { ...this.status.error.details } }
        : null,
      health: this.status.health ? { ...this.status.health } : null,
    };
  }

  onEvent(listener: EventListener): () => void {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  onProtocolError(listener: ProtocolErrorListener): () => void {
    this.protocolErrorListeners.add(listener);
    return () => this.protocolErrorListeners.delete(listener);
  }

  start(): Promise<CoreMetadata> {
    if (this.status.state === "ready" && this.metadata)
      return Promise.resolve(this.metadata);
    if (this.startPromise) return this.startPromise;
    if (this.child) {
      return Promise.reject(
        new CoreClientError({
          code: "SIDECAR_ALREADY_RUNNING",
          message:
            "The existing Python core sidecar must exit before restarting.",
          retryable: true,
          details: {},
        }),
      );
    }

    this.metadata = null;
    this.intentionalShutdown = false;
    this.setStatus({
      state: "starting",
      protocolVersion: null,
      coreVersion: null,
      health: null,
      error: null,
    });

    const startPromise = new Promise<CoreMetadata>((resolve, reject) => {
      this.resolveStart = resolve;
      this.rejectStart = reject;
    });
    this.startPromise = startPromise;
    this.lineBuffer.reset();

    try {
      this.child = this.spawnProcess(
        this.command,
        this.args,
        this.spawnOptions,
      );
      this.exitPromise = new Promise<void>((resolve) => {
        this.resolveExit = resolve;
      });
      this.attachChild(this.child);
      this.startupTimer = setTimeout(() => {
        const error = new CoreClientError({
          code: "SIDECAR_START_TIMEOUT",
          message: `Core did not become ready within ${this.startupTimeoutMs} ms.`,
          retryable: true,
          details: {},
        });
        this.fail(error);
        this.killChild();
      }, this.startupTimeoutMs);
    } catch (error) {
      this.fail(
        new CoreClientError({
          code: "SIDECAR_START_FAILED",
          message: error instanceof Error ? error.message : String(error),
          retryable: true,
          details: {},
        }),
      );
    }

    return startPromise;
  }

  request<T = unknown>(
    method: CoreMethod,
    params: JsonObject = {},
    timeoutMs = this.requestTimeoutMs,
  ): Promise<T> {
    if (
      !this.child ||
      this.status.state === "stopped" ||
      this.status.state === "unavailable" ||
      this.status.state === "stopping"
    ) {
      return Promise.reject(
        new CoreClientError({
          code: "SIDECAR_UNAVAILABLE",
          message: "The Python core sidecar is not available.",
          retryable: true,
          details: {},
        }),
      );
    }

    const requestId = randomUUID();
    const message = JSON.stringify({
      protocol_version: PROTOCOL_VERSION,
      type: "request",
      request_id: requestId,
      method,
      params,
    });

    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.rejectPending(
          requestId,
          new CoreRequestTimeoutError(requestId, timeoutMs),
        );
      }, timeoutMs);
      this.pending.set(requestId, {
        resolve: (result) => resolve(result as T),
        reject,
        timer,
      });

      try {
        this.child?.stdin.write(
          `${message}\n`,
          "utf8",
          (error?: Error | null) => {
            if (error) {
              this.rejectPending(
                requestId,
                new CoreClientError({
                  code: "SIDECAR_WRITE_FAILED",
                  message: error.message,
                  retryable: true,
                  details: {},
                }),
              );
            }
          },
        );
      } catch (error) {
        this.rejectPending(
          requestId,
          new CoreClientError({
            code: "SIDECAR_WRITE_FAILED",
            message: error instanceof Error ? error.message : String(error),
            retryable: true,
            details: {},
          }),
        );
      }
    });
  }

  recordHealth(health: HealthResult): void {
    this.setStatus({ health: { ...health } });
  }

  markUnavailable(error: unknown): void {
    this.fail(new CoreClientError(toCoreError(error)));
  }

  shutdown(): Promise<void> {
    if (this.shutdownPromise) return this.shutdownPromise;
    const operation = this.shutdownInternal();
    this.shutdownPromise = operation;
    void operation
      .finally(() => {
        if (this.shutdownPromise === operation) this.shutdownPromise = null;
      })
      .catch(() => undefined);
    return operation;
  }

  private async shutdownInternal(): Promise<void> {
    if (!this.child) {
      this.setStatus({ state: "stopped" });
      return;
    }

    this.intentionalShutdown = true;
    try {
      if (this.metadata) {
        await this.request("core.shutdown", {}, this.shutdownTimeoutMs);
      }
    } catch {
      // The process may already be unavailable. The exit wait and kill below
      // still enforce the no-orphan lifecycle guarantee.
    }

    this.setStatus({ state: "stopping" });
    await this.waitForExit(this.shutdownTimeoutMs);
    if (this.child) {
      this.killChild();
      await this.waitForExit(Math.min(1_000, this.shutdownTimeoutMs));
    }
    this.setStatus({ state: "stopped" });
  }

  private attachChild(child: ChildProcessWithoutNullStreams): void {
    child.stdout.on("data", (chunk: Buffer) => this.handleStdout(chunk));
    child.stdout.on("error", (error) =>
      this.fail(
        new CoreClientError(toCoreError(error, "SIDECAR_STDOUT_ERROR")),
      ),
    );
    child.stderr.on("data", () => {
      // Consume stderr so a verbose diagnostic stream cannot block the sidecar.
    });
    child.on("error", (error) =>
      this.fail(
        new CoreClientError(toCoreError(error, "SIDECAR_PROCESS_ERROR")),
      ),
    );
    child.on("exit", (code, signal) => this.handleExit(code, signal));
  }

  private handleStdout(chunk: Buffer): void {
    for (const line of this.lineBuffer.push(chunk)) {
      try {
        const message: unknown = JSON.parse(line);
        this.handleMessage(message);
      } catch (error) {
        this.notifyProtocolError(
          new CoreClientError({
            code: "MALFORMED_JSON",
            message:
              error instanceof Error
                ? error.message
                : "Sidecar emitted malformed JSON.",
            retryable: false,
            details: { line_preview: line.slice(0, 120) },
          }),
        );
      }
    }
  }

  private handleMessage(message: unknown): void {
    if (!isJsonObject(message)) {
      this.notifyProtocolError(
        this.invalidProtocolError("Sidecar message must be an object."),
      );
      return;
    }

    const requestId =
      typeof message.request_id === "string" ? message.request_id : null;
    if (message.protocol_version !== PROTOCOL_VERSION) {
      const error = new CoreClientError({
        code: "PROTOCOL_VERSION_UNSUPPORTED",
        message: `Sidecar protocol version ${String(message.protocol_version)} is not supported.`,
        retryable: false,
        details: { supported_versions: [PROTOCOL_VERSION] },
      });
      if (requestId) this.rejectPending(requestId, error);
      else this.notifyProtocolError(error);
      return;
    }

    if (message.type === "event") {
      this.handleEvent(message);
      return;
    }
    if (message.type === "response") {
      this.handleResponse(message);
      return;
    }

    this.notifyProtocolError(
      this.invalidProtocolError("Sidecar message type is not supported."),
    );
  }

  private handleEvent(message: JsonObject): void {
    if (typeof message.event !== "string" || !isJsonObject(message.payload)) {
      this.notifyProtocolError(
        this.invalidProtocolError("Event envelope is invalid."),
      );
      return;
    }

    const event: EventEnvelope = {
      protocol_version: PROTOCOL_VERSION,
      type: "event",
      event: message.event,
      payload: message.payload,
    };
    if (event.event === "core.ready") {
      if (!isCoreMetadata(event.payload)) {
        this.fail(this.invalidProtocolError("core.ready payload is invalid."));
        return;
      }
      this.metadata = event.payload;
      this.setStatus({
        state: "ready",
        protocolVersion: event.payload.protocol_version,
        coreVersion: event.payload.core_version,
        error: null,
      });
      this.resolveStartPromise(event.payload);
    }
    for (const listener of this.eventListeners) {
      try {
        listener(event);
      } catch {
        // A renderer listener must not destabilize the trusted transport.
      }
    }
  }

  private handleResponse(message: JsonObject): void {
    if (typeof message.request_id !== "string") {
      this.notifyProtocolError(
        this.invalidProtocolError("Response request_id is invalid."),
      );
      return;
    }
    const pending = this.pending.get(message.request_id);
    if (!pending) return;

    if (message.ok === true && "result" in message && !("error" in message)) {
      this.resolvePending(message.request_id, message.result);
    } else if (
      message.ok === false &&
      !("result" in message) &&
      isCoreError(message.error)
    ) {
      this.rejectPending(
        message.request_id,
        new CoreClientError(message.error),
      );
    } else {
      this.rejectPending(
        message.request_id,
        this.invalidProtocolError("Response error is invalid."),
      );
    }
  }

  private handleExit(code: number | null, signal: NodeJS.Signals | null): void {
    this.child = null;
    this.resolveExit?.();
    this.resolveExit = null;
    this.exitPromise = null;

    const expected =
      this.intentionalShutdown || this.status.state === "stopping";
    const exitMessage = expected
      ? "Core sidecar exited."
      : `Core sidecar exited unexpectedly${signal ? ` with ${signal}` : ` with code ${String(code)}`}.`;
    const error = new CoreClientError({
      code: expected ? "SIDECAR_EXITED" : "SIDECAR_EXITED_UNEXPECTEDLY",
      message: exitMessage,
      retryable: !expected,
      details: { code, signal },
    });

    this.rejectAllPending(error);
    if (this.startPromise) this.rejectStartPromise(error);
    if (expected) {
      this.setStatus({ state: "stopped" });
    } else {
      this.setStatus({ state: "unavailable", error: toCoreError(error) });
    }
  }

  private fail(error: CoreClientError): void {
    this.setStatus({ state: "unavailable", error: toCoreError(error) });
    this.rejectAllPending(error);
    if (this.startPromise) this.rejectStartPromise(error);
  }

  private resolveStartPromise(metadata: CoreMetadata): void {
    if (!this.resolveStart) return;
    this.clearStartupTimer();
    const resolve = this.resolveStart;
    this.resolveStart = null;
    this.rejectStart = null;
    this.startPromise = null;
    resolve(metadata);
  }

  private rejectStartPromise(error: CoreClientError): void {
    if (!this.rejectStart) return;
    this.clearStartupTimer();
    const reject = this.rejectStart;
    this.resolveStart = null;
    this.rejectStart = null;
    this.startPromise = null;
    reject(error);
  }

  private clearStartupTimer(): void {
    if (this.startupTimer) clearTimeout(this.startupTimer);
    this.startupTimer = null;
  }

  private resolvePending(requestId: string, result: unknown): void {
    const pending = this.pending.get(requestId);
    if (!pending) return;
    this.pending.delete(requestId);
    clearTimeout(pending.timer);
    pending.resolve(result);
  }

  private rejectPending(requestId: string, error: unknown): void {
    const pending = this.pending.get(requestId);
    if (!pending) return;
    this.pending.delete(requestId);
    clearTimeout(pending.timer);
    pending.reject(error);
  }

  private rejectAllPending(error: unknown): void {
    for (const requestId of this.pending.keys())
      this.rejectPending(requestId, error);
  }

  private waitForExit(timeoutMs: number): Promise<void> {
    if (!this.child || !this.exitPromise) return Promise.resolve();
    const exitPromise = this.exitPromise;
    return new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, timeoutMs);
      void exitPromise.then(() => {
        clearTimeout(timer);
        resolve();
      });
    });
  }

  private killChild(): void {
    try {
      this.child?.kill();
    } catch {
      // The process may have exited between the wait and the kill attempt.
    }
  }

  private invalidProtocolError(message: string): CoreClientError {
    return new CoreClientError({
      code: "INVALID_PROTOCOL_MESSAGE",
      message,
      retryable: false,
      details: {},
    });
  }

  private notifyProtocolError(error: CoreClientError): void {
    for (const listener of this.protocolErrorListeners) {
      try {
        listener(error);
      } catch {
        // Diagnostics are advisory and cannot be allowed to break transport.
      }
    }
  }

  private setStatus(update: Partial<CoreStatus>): void {
    this.status = { ...this.status, ...update };
    const snapshot = this.getStatus();
    for (const listener of this.statusListeners) {
      try {
        listener(snapshot);
      } catch {
        // UI status consumers are isolated from the sidecar lifecycle.
      }
    }
  }
}

function isCoreError(value: unknown): value is CoreError {
  return (
    isJsonObject(value) &&
    typeof value.code === "string" &&
    typeof value.message === "string" &&
    typeof value.retryable === "boolean" &&
    isJsonObject(value.details)
  );
}
