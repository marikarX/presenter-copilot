import { describe, expect, it } from "vitest";
import { VoiceHoldGesture, type VoiceGestureCapture } from "./push-to-edit";
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function capture(events: string[]): VoiceGestureCapture {
  return {
    stop: async () => {
      events.push("stop owned capture");
    },
    cancel: async () => {
      events.push("cancel owned capture");
    },
  };
}
describe("hold-to-dictate ownership and ordering", () => {
  it("releases after actual readiness, even when the key ends before startup replies", async () => {
    const ready = deferred<VoiceGestureCapture | null>(),
      events: string[] = [],
      gesture = new VoiceHoldGesture();
    expect(gesture.press(() => ready.promise)).toBe(true);
    gesture.release();
    expect(events).toEqual([]);
    ready.resolve(capture(events));
    await gesture.completion;
    expect(events).toEqual(["stop owned capture"]);
    expect(gesture.active).toBe(false);
  });
  it("ignores repeat presses and modifier releases after the first end", async () => {
    const events: string[] = [],
      gesture = new VoiceHoldGesture();
    gesture.press(async () => capture(events));
    expect(
      gesture.press(async () => {
        throw new Error("must not start");
      }),
    ).toBe(false);
    gesture.release();
    gesture.release();
    await gesture.completion;
    expect(events).toEqual(["stop owned capture"]);
  });
  it("focus loss before startup cancels without retaining a transcript", async () => {
    const ready = deferred<VoiceGestureCapture | null>(),
      events: string[] = [],
      gesture = new VoiceHoldGesture();
    gesture.press(() => ready.promise);
    gesture.cancel();
    ready.resolve(capture(events));
    await gesture.completion;
    expect(events).toEqual(["cancel owned capture"]);
  });
  it("Escape overrides a queued quick release while capture is preparing", async () => {
    const ready = deferred<VoiceGestureCapture | null>(),
      events: string[] = [],
      gesture = new VoiceHoldGesture();
    gesture.press(() => ready.promise);
    gesture.release();
    gesture.cancel();
    ready.resolve(capture(events));
    await gesture.completion;
    expect(events).toEqual(["cancel owned capture"]);
  });
  it("Escape during final decoding waits for stop then discards that capture's review", async () => {
    const stopped = deferred<void>(),
      events: string[] = [],
      gesture = new VoiceHoldGesture();
    gesture.press(async () => ({
      stop: async () => {
        events.push("stop");
        await stopped.promise;
      },
      cancel: async () => {
        events.push("discard owned review");
      },
    }));
    gesture.release();
    await Promise.resolve();
    await Promise.resolve();
    expect(events).toEqual(["stop"]);
    gesture.cancel();
    stopped.resolve();
    await gesture.completion;
    expect(events).toEqual(["stop", "discard owned review"]);
  });
  it("does not end a different capture when the original startup was invalidated", async () => {
    const ready = deferred<VoiceGestureCapture | null>(),
      gesture = new VoiceHoldGesture();
    gesture.press(() => ready.promise);
    gesture.cancel();
    ready.resolve(null);
    await gesture.completion;
    expect(gesture.active).toBe(false);
  });
  it("retains a specific handle until cancellation completes and then permits another gesture", async () => {
    const cancelled = deferred<void>(),
      events: string[] = [],
      gesture = new VoiceHoldGesture();
    gesture.press(async () => ({
      stop: async () => {},
      cancel: async () => {
        events.push("cancel first");
        await cancelled.promise;
      },
    }));
    gesture.cancel();
    await Promise.resolve();
    await Promise.resolve();
    expect(gesture.active).toBe(true);
    expect(gesture.press(async () => capture(events))).toBe(false);
    cancelled.resolve();
    await gesture.completion;
    expect(gesture.press(async () => capture(events))).toBe(true);
    gesture.release();
    await gesture.completion;
    expect(events).toEqual(["cancel first", "stop owned capture"]);
  });
  it("releases ownership on startup failure without inventing stop/cancel calls", async () => {
    const gesture = new VoiceHoldGesture();
    gesture.press(async () => {
      throw new Error("ASR unavailable");
    });
    await expect(gesture.completion).rejects.toThrow("ASR unavailable");
    expect(gesture.active).toBe(false);
  });
  it("tries to cancel its own handle if stopping throws", async () => {
    const events: string[] = [],
      gesture = new VoiceHoldGesture();
    gesture.press(async () => ({
      stop: async () => {
        throw new Error("decode failed");
      },
      cancel: async () => {
        events.push("cancel own failed stop");
      },
    }));
    gesture.release();
    await expect(gesture.completion).rejects.toThrow("decode failed");
    expect(events).toEqual(["cancel own failed stop"]);
  });
});
