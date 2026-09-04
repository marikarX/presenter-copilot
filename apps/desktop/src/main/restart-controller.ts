export const DEFAULT_AUTOMATIC_RESTART_DELAYS_MS = [500, 1_500] as const;
export const DEFAULT_AUTOMATIC_RESTART_MAX_ATTEMPTS = 2;
export const DEFAULT_AUTOMATIC_RESTART_STABILITY_WINDOW_MS = 30_000;

export interface AutomaticRestartControllerOptions {
  restart: () => Promise<boolean>;
  isQuitting: () => boolean;
  maxAttempts?: number;
  delaysMs?: readonly number[];
  stabilityWindowMs?: number;
  onExhausted?: () => void;
}

export interface AutomaticRestartSnapshot {
  attempts: number;
  scheduled: boolean;
  inFlight: boolean;
  stabilityPending: boolean;
  exhausted: boolean;
}

/**
 * Restart only after CoreProcessClient has finalized an unexpected close.
 * An exit event is deliberately not a recovery signal: close owns lifecycle
 * finalization and is the only event the main process should forward here.
 */
export class AutomaticRestartController {
  private readonly restart: () => Promise<boolean>;
  private readonly isQuitting: () => boolean;
  private readonly maxAttempts: number;
  private readonly delaysMs: readonly number[];
  private readonly stabilityWindowMs: number;
  private readonly onExhausted?: () => void;

  private restartTimer: ReturnType<typeof setTimeout> | null = null;
  private stabilityTimer: ReturnType<typeof setTimeout> | null = null;
  private attempts = 0;
  private inFlight = false;
  private crashDuringAttempt = false;
  private exhausted = false;
  private cancelled = false;

  constructor(options: AutomaticRestartControllerOptions) {
    this.restart = options.restart;
    this.isQuitting = options.isQuitting;
    this.maxAttempts = Math.max(
      0,
      Math.floor(options.maxAttempts ?? DEFAULT_AUTOMATIC_RESTART_MAX_ATTEMPTS),
    );
    this.delaysMs = options.delaysMs?.length
      ? options.delaysMs.map((delay) => Math.max(0, delay))
      : DEFAULT_AUTOMATIC_RESTART_DELAYS_MS;
    this.stabilityWindowMs = Math.max(
      0,
      options.stabilityWindowMs ??
        DEFAULT_AUTOMATIC_RESTART_STABILITY_WINDOW_MS,
    );
    this.onExhausted = options.onExhausted;
  }

  /** Called only after CoreProcessClient's close finalizer reports an error. */
  onUnexpectedClose(): void {
    if (this.cancelled || this.isQuitting() || this.exhausted) return;
    if (this.inFlight) {
      this.crashDuringAttempt = true;
      return;
    }
    this.clearStabilityTimer();
    this.schedule();
  }

  /** Exit is an intermediate lifecycle signal and never schedules recovery. */
  onExit(): void {
    // Intentionally empty. CoreProcessClient finalizes lifecycle on close.
  }

  cancel(): void {
    this.cancelled = true;
    this.clearRestartTimer();
    this.clearStabilityTimer();
    this.crashDuringAttempt = false;
  }

  snapshot(): AutomaticRestartSnapshot {
    return {
      attempts: this.attempts,
      scheduled: this.restartTimer !== null,
      inFlight: this.inFlight,
      stabilityPending: this.stabilityTimer !== null,
      exhausted: this.exhausted,
    };
  }

  private schedule(): void {
    if (
      this.cancelled ||
      this.isQuitting() ||
      this.restartTimer !== null ||
      this.inFlight ||
      this.exhausted
    )
      return;
    if (this.attempts >= this.maxAttempts) {
      this.exhausted = true;
      try {
        this.onExhausted?.();
      } catch {
        // Exhaustion reporting cannot restart a process or break lifecycle.
      }
      return;
    }
    const delay =
      this.delaysMs[this.attempts] ??
      this.delaysMs[this.delaysMs.length - 1] ??
      0;
    this.attempts += 1;
    this.restartTimer = setTimeout(() => {
      this.restartTimer = null;
      void this.runAttempt();
    }, delay);
  }

  private async runAttempt(): Promise<void> {
    if (this.cancelled || this.isQuitting() || this.inFlight || this.exhausted)
      return;
    this.inFlight = true;
    this.crashDuringAttempt = false;
    let ready: boolean;
    try {
      ready = await this.restart();
    } catch {
      ready = false;
    }
    const crashedDuringAttempt = this.crashDuringAttempt;
    this.inFlight = false;
    this.crashDuringAttempt = false;

    if (this.cancelled || this.isQuitting()) return;
    if (!ready || crashedDuringAttempt) {
      this.schedule();
      return;
    }
    this.armStabilityWindow();
  }

  private armStabilityWindow(): void {
    this.clearStabilityTimer();
    this.stabilityTimer = setTimeout(() => {
      this.stabilityTimer = null;
      if (this.cancelled || this.isQuitting()) return;
      this.attempts = 0;
      this.exhausted = false;
    }, this.stabilityWindowMs);
  }

  private clearRestartTimer(): void {
    if (this.restartTimer !== null) clearTimeout(this.restartTimer);
    this.restartTimer = null;
  }

  private clearStabilityTimer(): void {
    if (this.stabilityTimer !== null) clearTimeout(this.stabilityTimer);
    this.stabilityTimer = null;
  }
}
