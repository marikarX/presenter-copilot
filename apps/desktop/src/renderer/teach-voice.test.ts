import { describe, expect, it } from "vitest";

import {
  boundedPartialText,
  isTeachVoiceMethod,
  MAX_TEACH_VOICE_PARTIAL_CHARS,
  teachVoiceActive,
} from "./teach-voice";

describe("Teach voice renderer boundary", () => {
  it("allows only the three typed voice lifecycle controls", () => {
    expect(isTeachVoiceMethod("teach.voice_start")).toBe(true);
    expect(isTeachVoiceMethod("teach.voice_stop")).toBe(true);
    expect(isTeachVoiceMethod("teach.voice_cancel")).toBe(true);
    expect(isTeachVoiceMethod("asr.start")).toBe(false);
    expect(isTeachVoiceMethod("audio.raw")).toBe(false);
  });

  it("keeps partials replacement-style, bounded, and text-only", () => {
    expect(boundedPartialText(" first partial ")).toBe("first partial");
    expect(boundedPartialText(new Uint8Array([1, 2]))).toBeNull();
    expect(
      boundedPartialText("x".repeat(MAX_TEACH_VOICE_PARTIAL_CHARS + 20)),
    ).toHaveLength(MAX_TEACH_VOICE_PARTIAL_CHARS);
  });

  it("marks only transient capture states as active", () => {
    expect(teachVoiceActive("idle")).toBe(false);
    expect(teachVoiceActive("starting")).toBe(true);
    expect(teachVoiceActive("listening")).toBe(true);
    expect(teachVoiceActive("transcribing")).toBe(true);
    expect(teachVoiceActive("error")).toBe(true);
  });
});
