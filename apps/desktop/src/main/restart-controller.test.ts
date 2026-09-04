import { afterEach, describe, expect, it, vi } from "vitest";

import { AutomaticRestartController } from "./restart-controller";

afterEach(() => {
  vi.useRealTimers();
});

describe("AutomaticRestartController", () => {
  it("does not restart for an exit lifecycle signal", async () => {
    vi.useFakeTimers();
    const restart = vi.fn<() => Promise<boolean>>().mockResolvedValue(true);
    const controller = new AutomaticRestartController({
      restart,
      isQuitting: () => false,
      delaysMs: [500, 1_500],
      stabilityWindowMs: 100,
    });

    controller.onExit();
    await vi.advanceTimersByTimeAsync(10_000);

    expect(restart).not.toHaveBeenCalled();
    expect(controller.snapshot()).toMatchObject({
      attempts: 0,
      scheduled: false,
      inFlight: false,
    });
  });

  it("schedules one restart only after an unexpected close and uses the first delay", async () => {
    vi.useFakeTimers();
    const restart = vi.fn<() => Promise<boolean>>().mockResolvedValue(true);
    const controller = new AutomaticRestartController({
      restart,
      isQuitting: () => false,
      delaysMs: [500, 1_500],
      stabilityWindowMs: 100,
    });

    controller.onUnexpectedClose();
    await vi.advanceTimersByTimeAsync(499);
    expect(restart).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(restart).toHaveBeenCalledTimes(1);
  });

  it("schedules the second attempt after a failed first attempt and never starts a third", async () => {
    vi.useFakeTimers();
    const exhausted = vi.fn();
    const restart = vi
      .fn<() => Promise<boolean>>()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(false);
    const controller = new AutomaticRestartController({
      restart,
      isQuitting: () => false,
      delaysMs: [500, 1_500],
      stabilityWindowMs: 100,
      onExhausted: exhausted,
    });

    controller.onUnexpectedClose();
    await vi.advanceTimersByTimeAsync(500);
    expect(restart).toHaveBeenCalledTimes(1);
    expect(controller.snapshot()).toMatchObject({
      attempts: 2,
      scheduled: true,
    });

    await vi.advanceTimersByTimeAsync(1_500);
    expect(restart).toHaveBeenCalledTimes(2);
    expect(exhausted).toHaveBeenCalledTimes(1);
    expect(controller.snapshot()).toMatchObject({
      attempts: 2,
      scheduled: false,
      exhausted: true,
    });

    controller.onUnexpectedClose();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(restart).toHaveBeenCalledTimes(2);
  });

  it("does not reset the attempt budget until a successful restart is stable", async () => {
    vi.useFakeTimers();
    const restart = vi.fn<() => Promise<boolean>>().mockResolvedValue(true);
    const exhausted = vi.fn();
    const controller = new AutomaticRestartController({
      restart,
      isQuitting: () => false,
      delaysMs: [500, 1_500],
      stabilityWindowMs: 100,
      onExhausted: exhausted,
    });

    controller.onUnexpectedClose();
    await vi.advanceTimersByTimeAsync(500);
    expect(controller.snapshot()).toMatchObject({
      attempts: 1,
      stabilityPending: true,
    });

    controller.onUnexpectedClose();
    await vi.advanceTimersByTimeAsync(1_500);
    expect(restart).toHaveBeenCalledTimes(2);
    expect(controller.snapshot().attempts).toBe(2);

    controller.onUnexpectedClose();
    expect(exhausted).toHaveBeenCalledTimes(1);
    expect(restart).toHaveBeenCalledTimes(2);
  });

  it("exhausts repeated handshake-then-crash cycles without a third attempt", async () => {
    vi.useFakeTimers();
    const resolvers: Array<(ready: boolean) => void> = [];
    const restart = vi.fn(
      () =>
        new Promise<boolean>((resolve) => {
          resolvers.push(resolve);
        }),
    );
    const exhausted = vi.fn();
    const controller = new AutomaticRestartController({
      restart,
      isQuitting: () => false,
      delaysMs: [0, 0],
      stabilityWindowMs: 100,
      onExhausted: exhausted,
    });

    controller.onUnexpectedClose();
    await vi.advanceTimersByTimeAsync(0);
    expect(restart).toHaveBeenCalledTimes(1);
    controller.onUnexpectedClose();
    const resolveFirst = resolvers.shift();
    if (!resolveFirst) throw new Error("first restart was not started");
    resolveFirst(true);
    await vi.advanceTimersByTimeAsync(0);
    expect(restart).toHaveBeenCalledTimes(2);

    controller.onUnexpectedClose();
    const resolveSecond = resolvers.shift();
    if (!resolveSecond) throw new Error("second restart was not started");
    resolveSecond(true);
    await vi.advanceTimersByTimeAsync(0);
    expect(exhausted).toHaveBeenCalledTimes(1);
    expect(controller.snapshot()).toMatchObject({
      attempts: 2,
      scheduled: false,
      exhausted: true,
    });

    await vi.advanceTimersByTimeAsync(10_000);
    expect(restart).toHaveBeenCalledTimes(2);
  });

  it("resets the episode only after the stability window", async () => {
    vi.useFakeTimers();
    const restart = vi.fn<() => Promise<boolean>>().mockResolvedValue(true);
    const controller = new AutomaticRestartController({
      restart,
      isQuitting: () => false,
      delaysMs: [500, 1_500],
      stabilityWindowMs: 100,
    });

    controller.onUnexpectedClose();
    await vi.advanceTimersByTimeAsync(500);
    await vi.advanceTimersByTimeAsync(99);
    expect(controller.snapshot().attempts).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(controller.snapshot()).toMatchObject({
      attempts: 0,
      exhausted: false,
    });

    controller.onUnexpectedClose();
    await vi.advanceTimersByTimeAsync(500);
    expect(restart).toHaveBeenCalledTimes(2);
  });

  it("cancels scheduled and in-flight recovery when shutdown begins", async () => {
    vi.useFakeTimers();
    let quitting = false;
    let resolveRestart!: (ready: boolean) => void;
    const restart = vi.fn(
      () => new Promise<boolean>((resolve) => (resolveRestart = resolve)),
    );
    const controller = new AutomaticRestartController({
      restart,
      isQuitting: () => quitting,
      delaysMs: [500, 1_500],
      stabilityWindowMs: 100,
    });

    controller.onUnexpectedClose();
    controller.cancel();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(restart).not.toHaveBeenCalled();

    // A second controller proves that a promise already in progress cannot
    // schedule another attempt after the app enters its expected shutdown.
    quitting = false;
    const inFlight = new AutomaticRestartController({
      restart,
      isQuitting: () => quitting,
      delaysMs: [0, 0],
      stabilityWindowMs: 100,
    });
    inFlight.onUnexpectedClose();
    await vi.advanceTimersByTimeAsync(0);
    expect(restart).toHaveBeenCalledTimes(1);
    quitting = true;
    inFlight.cancel();
    resolveRestart(false);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(restart).toHaveBeenCalledTimes(1);
  });

  it("coalesces close notifications while an attempt is in flight", async () => {
    vi.useFakeTimers();
    let resolveRestart!: (ready: boolean) => void;
    const restart = vi.fn(
      () => new Promise<boolean>((resolve) => (resolveRestart = resolve)),
    );
    const controller = new AutomaticRestartController({
      restart,
      isQuitting: () => false,
      delaysMs: [0, 1_500],
      stabilityWindowMs: 100,
    });

    controller.onUnexpectedClose();
    await vi.advanceTimersByTimeAsync(0);
    controller.onUnexpectedClose();
    controller.onUnexpectedClose();
    expect(restart).toHaveBeenCalledTimes(1);
    resolveRestart(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(controller.snapshot()).toMatchObject({
      attempts: 2,
      scheduled: true,
    });
  });
});
