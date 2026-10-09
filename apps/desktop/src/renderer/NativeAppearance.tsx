import { useEffect, useRef, useState } from "react";
import {
  isCoreError,
  unwrapInvokeResult,
  type NativeAppearanceResult,
} from "../shared/protocol";

export interface NativeAppearanceTarget {
  projectId: string;
  documentId: string;
  revisionId: string;
  sourceSha256: string;
  planId?: string;
}
export function nativeAppearanceKey(
  target: NativeAppearanceTarget | null,
  slideNumber: number,
): string {
  return target
    ? `${target.projectId}:${target.documentId}:${target.revisionId}:${target.sourceSha256}:${target.planId ?? "saved"}:${slideNumber}`
    : "";
}
export function isCurrentNativeAppearance(
  result: NativeAppearanceResult,
  target: NativeAppearanceTarget,
  slideNumber: number,
): boolean {
  return (
    !!result &&
    result.plan_id === target.planId &&
    result.revision_id === target.revisionId &&
    result.source_sha256 === target.sourceSha256 &&
    result.slide_number === slideNumber &&
    result.renderer === "microsoft_powerpoint" &&
    /^[0-9a-f]{64}$/.test(result.sha256) &&
    [result.width, result.height].every(
      (n) => Number.isInteger(n) && n > 0 && n <= 4096,
    ) &&
    result.image instanceof Uint8Array &&
    result.image.byteLength > 32 &&
    result.image.byteLength <= 16 * 1024 * 1024
  );
}

/** Frames and URLs are owned by a full saved-revision/slide identity. */
export function usePowerPointAppearance(
  target: NativeAppearanceTarget | null,
  slideNumber: number,
  onSelectionChange?: () => void,
  externalBusy = false,
  externalNative = false,
) {
  const key = nativeAppearanceKey(target, slideNumber);
  const current = useRef(key);
  current.current = key;
  const owner = useRef({ live: true, generation: 0, pending: false });
  const [state, setState] = useState<{
    key: string;
    phase: "browser" | "running" | "ready" | "failed";
    frame?: NativeAppearanceResult;
    error?: string;
  }>({ key: "", phase: "browser" });
  const [workerBusy, setWorkerBusy] = useState(false);
  const [url, setUrl] = useState<{ key: string; value: string } | null>(null);
  useEffect(() => {
    const scope = owner.current;
    scope.live = true;
    return () => {
      scope.live = false;
      scope.generation++;
    };
  }, []);
  const frame =
    state.key === key && state.phase === "ready" ? state.frame : undefined;
  useEffect(() => {
    if (!frame) {
      setUrl(null);
      return;
    }
    const value = URL.createObjectURL(
      new Blob([new Uint8Array(frame.image)], { type: "image/png" }),
    );
    setUrl({ key, value });
    return () => URL.revokeObjectURL(value);
  }, [frame, key]);
  const image = frame && url?.key === key ? url.value : null;
  const pending = state.key === key && state.phase === "running";
  async function render() {
    if (!target || owner.current.pending || externalBusy) return;
    onSelectionChange?.();
    const scope = owner.current,
      generation = ++scope.generation,
      requestedKey = key;
    scope.pending = true;
    setWorkerBusy(true);
    setState({ key: requestedKey, phase: "running" });
    try {
      const result = unwrapInvokeResult(
        target.planId
          ? await window.presenterCopilot.presentation.nativeEditPlanAppearance(
              target.projectId,
              target.documentId,
              target.revisionId,
              target.planId,
              target.sourceSha256,
              slideNumber,
            )
          : await window.presenterCopilot.presentation.nativeAppearance(
              target.projectId,
              target.documentId,
              target.revisionId,
              target.sourceSha256,
              slideNumber,
            ),
      );
      if (
        !scope.live ||
        scope.generation !== generation ||
        current.current !== requestedKey
      )
        return;
      if (!isCurrentNativeAppearance(result, target, slideNumber))
        throw new Error(
          "The PowerPoint appearance does not match this saved slide.",
        );
      setState({ key: requestedKey, phase: "ready", frame: result });
    } catch (error) {
      if (
        scope.live &&
        scope.generation === generation &&
        current.current === requestedKey
      ) {
        setState({
          key: requestedKey,
          phase: "failed",
          error: isCoreError(error)
            ? error.message
            : error instanceof Error
              ? error.message
              : "PowerPoint appearance is unavailable.",
        });
      }
    } finally {
      scope.pending = false;
      if (scope.live) setWorkerBusy(false);
    }
  }
  function browser() {
    onSelectionChange?.();
    owner.current.generation++;
    setState({ key, phase: "browser" });
  }
  const controls = target ? (
    <div
      className="pw-native-appearance"
      role="group"
      aria-label="Slide appearance"
    >
      <div className="button-row">
        <button
          type="button"
          className="secondary-button"
          aria-pressed={!image && !externalNative}
          onClick={browser}
        >
          Browser appearance
        </button>
        <button
          type="button"
          className="secondary-button"
          aria-pressed={!!image || externalNative}
          disabled={workerBusy || externalBusy}
          onClick={() => void render()}
        >
          {workerBusy ? "Rendering in PowerPoint…" : "PowerPoint appearance"}
        </button>
      </div>
      <p role="status">
        {image || externalNative
          ? target.planId
            ? "Proposed slide appearance from PowerPoint. Changes are not saved."
            : externalNative
              ? "Saved slide appearance from PowerPoint with live dragging. Review proposed changes in an edit preview."
              : "Saved slide appearance from PowerPoint. Review proposed changes in an edit preview."
          : pending
            ? target.planId
              ? "Rendering proposed slide in PowerPoint. Changes are not saved."
              : "Rendering saved slide in PowerPoint. Browser appearance is shown while waiting."
            : "Browser appearance. PowerPoint appearance requires Microsoft PowerPoint on Windows."}
      </p>
      {state.key === key && state.error ? (
        <p role="alert">
          {state.error} Select Browser appearance to continue, or retry
          PowerPoint appearance.
        </p>
      ) : null}
    </div>
  ) : null;
  return {
    image,
    pending,
    controls,
    rejectImage: () => {
      onSelectionChange?.();
      setState({
        key,
        phase: "failed",
        error:
          "The PowerPoint image could not be displayed. Retry or use Browser appearance.",
      });
    },
    status: `${state.key}:${state.phase}`,
  };
}
