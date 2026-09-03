import { isJsonObject, type JsonObject } from "../shared/protocol";

export type HudLiveTarget = {
  readonly projectId: string;
  readonly sessionId: string;
};

export type HudCueRequest = {
  readonly cue_id: string;
};

/** Bind the HUD's cue-only request to the authoritative live session. */
export function bindHudCueRequest(
  value: unknown,
  target: HudLiveTarget | null,
): JsonObject {
  const request = validateHudCueRequest(value);
  if (!target) throw new Error("No active Live Assist session is available.");
  return {
    project_id: target.projectId,
    session_id: target.sessionId,
    cue_id: request.cue_id,
  };
}

export function validateHudCueRequest(value: unknown): HudCueRequest {
  if (
    !isJsonObject(value) ||
    Object.keys(value).some((key) => key !== "cue_id")
  ) {
    throw new Error("The HUD cue request must contain only cue_id.");
  }
  if (
    typeof value.cue_id !== "string" ||
    value.cue_id.length === 0 ||
    value.cue_id.length > 80
  ) {
    throw new Error("The HUD cue request is invalid.");
  }
  return { cue_id: value.cue_id };
}
