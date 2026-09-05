export const MAX_TEACH_VOICE_PARTIAL_CHARS = 1_200;

export const TEACH_VOICE_METHODS = [
  "teach.voice_start",
  "teach.voice_stop",
  "teach.voice_cancel",
] as const;

export type TeachVoiceMethod = (typeof TEACH_VOICE_METHODS)[number];
export type TeachVoiceCaptureState =
  "idle" | "starting" | "listening" | "transcribing" | "error";

export function boundedPartialText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  return text ? text.slice(0, MAX_TEACH_VOICE_PARTIAL_CHARS) : null;
}

export function isTeachVoiceMethod(value: string): value is TeachVoiceMethod {
  return (TEACH_VOICE_METHODS as readonly string[]).includes(value);
}

export function teachVoiceActive(state: TeachVoiceCaptureState): boolean {
  return state !== "idle";
}
