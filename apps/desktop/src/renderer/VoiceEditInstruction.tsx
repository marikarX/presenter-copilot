import { useEffect, useRef, useState } from "react";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { VoiceRecognitionReview } from "./VoiceRecognitionReview";
import {
  clarifiedVoiceInstruction,
  parseRecognitionReview,
  type RecognitionReview,
} from "./voice-recognition-review";
import {
  usePushToEdit,
  PUSH_TO_EDIT_LABEL,
  type VoiceGestureCapture,
} from "./push-to-edit";

type VoiceInstructionProps = {
  projectId: string;
  scopeChoice: string;
  disabled: boolean;
  onBusyChange: (busy: boolean) => void;
  onUse: (instruction: string) => void;
} & (
  | {
      outlinePurpose: "briefing" | "refinement";
      documentId?: never;
      revisionId?: never;
      slideNumber?: never;
    }
  | {
      outlinePurpose?: never;
      documentId: string;
      revisionId: string;
      slideNumber: number;
    }
);

/** Local capture owns no provider action; only reviewed text leaves this component. */
export function VoiceEditInstruction({
  projectId,
  outlinePurpose,
  documentId,
  revisionId,
  slideNumber,
  scopeChoice,
  disabled,
  onBusyChange,
  onUse,
}: VoiceInstructionProps) {
  const outlining = outlinePurpose !== undefined;
  const limit = outlinePurpose === "briefing" ? 2000 : 500;
  const targetLabel = outlining
    ? outlinePurpose === "briefing"
      ? "briefing"
      : "refinement"
    : "Copilot request";
  type Phase =
    "idle" | "starting" | "listening" | "stopping" | "review" | "cancelling";
  const [phase, setPhaseState] = useState<Phase>("idle");
  const phaseRef = useRef<Phase>("idle");
  const root = useRef<HTMLElement>(null);
  const reviewCapture = useRef<string | null>(null);
  const epoch = useRef(0);
  function setPhase(next: Phase) {
    phaseRef.current = next;
    setPhaseState(next);
    onBusyChange(next !== "idle");
  }
  const [transcript, setTranscript] = useState("");
  const [recognition, setRecognition] = useState<RecognitionReview | null>(
    null,
  );
  const [clarification, setClarification] = useState("");
  const [partial, setPartial] = useState("");
  const [error, setError] = useState<string | null>(null);
  const capture = useRef<string | null>(null);
  const alive = useRef(true);
  const scope = {
    project_id: projectId,
    ...(outlining ? {} : { document_id: documentId }),
  };
  const contextKey = JSON.stringify([
    projectId,
    documentId,
    revisionId,
    slideNumber,
    scopeChoice,
    outlinePurpose,
  ]);
  useEffect(() => {
    const currentEpoch = ++epoch.current;
    alive.current = true;
    phaseRef.current = "idle";
    setPhaseState("idle");
    setTranscript("");
    setRecognition(null);
    setClarification("");
    setPartial("");
    setError(null);
    onBusyChange(false);
    return () => {
      alive.current = false;
      if (epoch.current === currentEpoch) epoch.current++;
      const owned = capture.current;
      capture.current = null;
      reviewCapture.current = null;
      onBusyChange(false);
      if (owned)
        void window.presenterCopilot.core
          .request("presentation.workspace.voice_cancel", {
            project_id: projectId,
            capture_id: owned,
          })
          .catch(() => undefined);
    };
  }, [projectId, contextKey, onBusyChange]);
  useEffect(() => {
    if (phase === "idle") return;
    const element = root.current;
    const target =
      element?.querySelector<HTMLElement>("textarea, button:not(:disabled)") ??
      element;
    // The request field can be above a long asset catalog. Keep capture/review visible.
    target?.focus();
  }, [phase]);
  useEffect(() => {
    if (phase !== "listening") return;
    return window.presenterCopilot.core.onEvent((event) => {
      if (
        event.event === "asr.partial" &&
        event.payload.session_id === capture.current &&
        typeof event.payload.text === "string"
      )
        setPartial(event.payload.text.slice(0, 1000));
    });
  }, [phase]);

  async function start(): Promise<VoiceGestureCapture | null> {
    if (phaseRef.current !== "idle" || disabled) return null;
    const startingEpoch = epoch.current;
    reviewCapture.current = null;
    setPhase("starting");
    setError(null);
    setPartial("");
    setTranscript("");
    setRecognition(null);
    setClarification("");
    try {
      const result = unwrapInvokeResult<{
        capture_id: string;
        document_id: string | null;
        revision_id: string | null;
        capture_state: string;
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.voice_start",
          {
            ...scope,
            ...(outlining
              ? {}
              : { revision_id: revisionId, slide_number: slideNumber }),
            intent: outlining ? "outline" : "edit_plan",
            scope: scopeChoice,
          },
        ),
      );
      if (!alive.current || epoch.current !== startingEpoch) {
        await window.presenterCopilot.core.request(
          "presentation.workspace.voice_cancel",
          { project_id: projectId, capture_id: result.capture_id },
        );
        return null;
      }
      capture.current = result.capture_id;
      if (
        !/^[0-9a-f-]{36}$/.test(result.capture_id) ||
        result.document_id !== (documentId ?? null) ||
        result.revision_id !== (revisionId ?? null) ||
        result.capture_state !== "running"
      )
        throw new Error("Voice capture could not be verified.");
      setPhase("listening");
      return {
        stop: () => stop(result.capture_id),
        cancel: () => cancel(result.capture_id),
      };
    } catch (caught) {
      if (!alive.current || epoch.current !== startingEpoch) return null;
      setError(
        isCoreError(caught)
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "Local capture could not start.",
      );
      setPhase(capture.current ? "listening" : "idle");
      return null;
    }
  }

  async function stop(expectedCaptureId?: string) {
    const captureId = capture.current;
    if (
      !captureId ||
      phaseRef.current !== "listening" ||
      (expectedCaptureId && expectedCaptureId !== captureId)
    )
      return;
    const stoppingEpoch = epoch.current;
    setPhase("stopping");
    setError(null);
    try {
      const result = unwrapInvokeResult<{
        capture_id: string;
        document_id: string | null;
        revision_id: string | null;
        slide_number: number | null;
        intent: string;
        scope: string;
        transcript: string;
        recognition_review: unknown;
        stopped: boolean;
        cancelled: boolean;
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.voice_stop",
          { project_id: projectId, capture_id: captureId },
        ),
      );
      if (
        !alive.current ||
        epoch.current !== stoppingEpoch ||
        capture.current !== captureId
      )
        return;
      capture.current = null;
      if (
        result.capture_id !== captureId ||
        result.document_id !== (documentId ?? null) ||
        result.revision_id !== (revisionId ?? null) ||
        result.slide_number !== (slideNumber ?? null) ||
        result.intent !== (outlining ? "outline" : "edit_plan") ||
        result.scope !== scopeChoice ||
        result.stopped !== true ||
        result.cancelled !== false ||
        typeof result.transcript !== "string" ||
        result.transcript.length > 16000
      )
        throw new Error(
          "The voice instruction no longer matches this request.",
        );
      reviewCapture.current = captureId;
      setRecognition(
        parseRecognitionReview(result.recognition_review, result.transcript),
      );
      setTranscript(result.transcript);
      setPartial("");
      setPhase("review");
    } catch (caught) {
      if (!alive.current || epoch.current !== stoppingEpoch) return;
      setError(
        isCoreError(caught)
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "The transcript could not be reviewed.",
      );
      if (
        isCoreError(caught) &&
        [
          "PRESENTATION_REVISION_CONFLICT",
          "SOURCE_NOT_FOUND",
          "PROJECT_NOT_FOUND",
          "ASR_SESSION_INVALID",
        ].includes(caught.code)
      )
        capture.current = null;
      setPhase(capture.current ? "listening" : "idle");
    }
  }

  async function cancel(expectedCaptureId?: string) {
    if (
      expectedCaptureId &&
      capture.current !== expectedCaptureId &&
      reviewCapture.current !== expectedCaptureId
    )
      return;
    if (
      ["starting", "stopping", "cancelling", "idle"].includes(phaseRef.current)
    )
      return;
    const cancellingEpoch = epoch.current;
    const captureId = capture.current;
    setPhase("cancelling");
    setError(null);
    try {
      if (captureId)
        unwrapInvokeResult(
          await window.presenterCopilot.core.request(
            "presentation.workspace.voice_cancel",
            { project_id: projectId, capture_id: captureId },
          ),
        );
      if (!alive.current || epoch.current !== cancellingEpoch) return;
      capture.current = null;
      reviewCapture.current = null;
      setTranscript("");
      setRecognition(null);
      setClarification("");
      setPartial("");
      setPhase("idle");
    } catch (caught) {
      if (!alive.current || epoch.current !== cancellingEpoch) return;
      setError(
        isCoreError(caught)
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "Capture could not be cancelled. Retry.",
      );
      setPhase(capture.current ? "listening" : "review");
    }
  }

  const hold = usePushToEdit({
    root,
    contextKey,
    disabled: disabled || phase !== "idle",
    start,
  });

  return (
    <section
      ref={root}
      tabIndex={-1}
      className="pw-voice-edit"
      aria-label={
        outlining
          ? `Dictated outline ${targetLabel}`
          : "Dictated Copilot request"
      }
    >
      {phase === "idle" ? (
        <button
          type="button"
          className="secondary-button"
          disabled={disabled}
          onClick={() => void start()}
          aria-keyshortcuts="Control+Shift+Space"
          title={`Hold ${PUSH_TO_EDIT_LABEL} while this editor is focused; release to review. Escape cancels.`}
        >
          {outlining ? `Dictate ${targetLabel}` : "Dictate Copilot request"}
        </button>
      ) : null}
      {phase === "listening" ? (
        <>
          <p role="status">
            Listening locally for your{" "}
            {outlining
              ? `outline ${targetLabel}`
              : `${scopeChoice === "deck" ? "whole-presentation" : "slide"} edit request`}
            …
          </p>
          {partial ? <p>{partial}</p> : null}
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              hold.release();
              void stop();
            }}
          >
            Stop and review request
          </button>
        </>
      ) : null}
      {phase === "starting" ||
      phase === "stopping" ||
      phase === "cancelling" ? (
        <p role="status">
          {phase === "starting"
            ? "Starting local microphone…"
            : phase === "stopping"
              ? "Finishing transcription…"
              : "Cancelling capture…"}
        </p>
      ) : null}
      {phase === "review" ? (
        <>
          <p>
            Intended target:{" "}
            {outlining
              ? `outline ${targetLabel}`
              : scopeChoice === "deck"
                ? "the whole presentation"
                : `current slide ${slideNumber}`}
            . Check this target before using the request.
          </p>
          <VoiceRecognitionReview review={recognition} />
          <label>
            Review your dictated request
            <textarea
              aria-label={
                outlining
                  ? "Reviewed outline transcript"
                  : "Reviewed Copilot transcript"
              }
              value={transcript}
              rows={4}
              onChange={(event) => setTranscript(event.target.value)}
            />
          </label>
          {!outlining ? (
            <label>
              Clarify intended slides or objects (optional)
              <textarea
                aria-label="Dictated target clarification"
                value={clarification}
                maxLength={500}
                rows={2}
                onChange={(event) => setClarification(event.target.value)}
              />
            </label>
          ) : null}
          <p className="muted">
            {outlining
              ? "Check names, numbers, audience and the decision you need."
              : "Check names, numbers and which slides or objects you mean."}{" "}
            Transcript and clarification together must fit within {limit}{" "}
            characters. Correct uncertain wording before using it.
          </p>
          <p className="muted">
            {clarifiedVoiceInstruction(transcript, clarification).length} /{" "}
            {limit} characters including clarification.
          </p>
          <button
            type="button"
            className="primary-button"
            disabled={
              !transcript.trim() ||
              clarifiedVoiceInstruction(transcript, clarification).length >
                limit
            }
            onClick={() => {
              onUse(clarifiedVoiceInstruction(transcript, clarification));
              reviewCapture.current = null;
              setTranscript("");
              setRecognition(null);
              setClarification("");
              setPhase("idle");
            }}
          >
            {outlining
              ? `Use reviewed ${targetLabel}`
              : "Use reviewed Copilot request"}
          </button>
        </>
      ) : null}
      {phase === "listening" || phase === "review" ? (
        <button
          type="button"
          className="secondary-button"
          onClick={() => {
            hold.cancel();
            void cancel();
          }}
        >
          {outlining ? "Discard outline dictation" : "Discard voice request"}
        </button>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      <p className="muted">
        Hold <kbd>{PUSH_TO_EDIT_LABEL}</kbd> in this editor to dictate. Release
        to review; Escape or leaving the window cancels an unfinished gesture.
      </p>
      <p className="muted">
        {outlining
          ? `Dictation stays local. Using it replaces the ${targetLabel} field; propose or refine the outline separately through your selected provider.`
          : "Dictation stays local. Using it fills the request; “Propose changes” sends the reviewed instruction through your selected provider."}
      </p>
    </section>
  );
}
