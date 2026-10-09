import { useEffect, useRef, useState } from "react";
import {
  isCoreError,
  unwrapInvokeResult,
  type NativeLayersResult,
} from "../shared/protocol";
import {
  nativeAppearanceKey,
  type NativeAppearanceTarget,
} from "./NativeAppearance";
import {
  createNativeLayerUrls,
  isCurrentNativeLayers,
} from "./native-layer-assets";
import type { LayoutObject } from "./object-layout";
type Assets = ReturnType<typeof createNativeLayerUrls>;
type State = {
  key: string;
  generation: number;
  phase: "off" | "running" | "loading" | "ready" | "failed";
  assets?: Assets;
  frame?: NativeLayersResult;
  loaded: Set<number>;
  error?: string;
};
/** Prepared image URLs and late responses belong to exactly one saved source/slide. */
export function useNativeLayers(
  target: NativeAppearanceTarget | null,
  slide: number,
  enabled: boolean,
  objects: LayoutObject[],
) {
  const key = nativeAppearanceKey(target, slide),
    current = useRef(key);
  current.current = key;
  const owner = useRef({ live: true, generation: 0, pending: false });
  const [state, setState] = useState<State>({
    key: "",
    generation: 0,
    phase: "off",
    loaded: new Set(),
  });
  const [workerBusy, setWorkerBusy] = useState(false);
  const objectsRef = useRef(objects);
  objectsRef.current = objects;
  useEffect(() => {
    const scope = owner.current;
    scope.live = true;
    return () => {
      scope.live = false;
      scope.generation++;
    };
  }, []);
  function stop() {
    const generation = ++owner.current.generation;
    setState({
      key: current.current,
      generation,
      phase: "off",
      loaded: new Set(),
    });
  }
  useEffect(() => {
    stop();
  }, [key, enabled]);
  const assets = state.assets;
  useEffect(
    () => () => {
      assets?.dispose();
    },
    [assets],
  );
  const visible = enabled && state.key === key;
  async function prepare() {
    if (!enabled || !target || target.planId || owner.current.pending) return;
    const scope = owner.current,
      generation = ++scope.generation,
      requestedKey = key;
    scope.pending = true;
    setWorkerBusy(true);
    setState({
      key: requestedKey,
      generation,
      phase: "running",
      loaded: new Set(),
    });
    try {
      const frame = unwrapInvokeResult(
        await window.presenterCopilot.presentation.nativeLayers(
          target.projectId,
          target.documentId,
          target.revisionId,
          target.sourceSha256,
          slide,
        ),
      );
      if (
        !scope.live ||
        scope.generation !== generation ||
        current.current !== requestedKey
      )
        return;
      if (!isCurrentNativeLayers(frame, target, slide, objectsRef.current))
        throw new Error(
          "The live dragging images do not match this saved slide.",
        );
      const prepared = createNativeLayerUrls(frame);
      setState({
        key: requestedKey,
        generation,
        phase: "loading",
        assets: prepared,
        frame,
        loaded: new Set(),
      });
    } catch (error) {
      if (
        scope.live &&
        scope.generation === generation &&
        current.current === requestedKey
      )
        setState({
          key: requestedKey,
          generation,
          phase: "failed",
          loaded: new Set(),
          error: isCoreError(error)
            ? error.message
            : error instanceof Error
              ? error.message
              : "Live dragging is unavailable. Use the normal slide preview.",
        });
    } finally {
      scope.pending = false;
      if (scope.live) setWorkerBusy(false);
    }
  }
  function imageLoaded(index: number, width: number, height: number) {
    const generation = state.generation;
    if (!visible || owner.current.generation !== generation) return;
    setState((previous) => {
      if (
        previous.key !== current.current ||
        previous.generation !== generation ||
        !previous.frame ||
        !previous.assets
      )
        return previous;
      if (width !== previous.frame.width || height !== previous.frame.height)
        return {
          key: previous.key,
          generation,
          phase: "failed",
          loaded: new Set(),
          error:
            "Live dragging images could not be displayed. Use the normal slide preview.",
        };
      const loaded = new Set(previous.loaded);
      loaded.add(index);
      return {
        ...previous,
        loaded,
        phase:
          loaded.size === previous.assets.layers.length + 1
            ? "ready"
            : "loading",
      };
    });
  }
  function imageFailed() {
    if (visible && owner.current.generation === state.generation) {
      owner.current.generation++;
      setState({
        key,
        generation: owner.current.generation,
        phase: "failed",
        loaded: new Set(),
        error:
          "Live dragging images could not be displayed. Use the normal slide preview.",
      });
    }
  }
  return {
    prepare,
    stop,
    workerBusy,
    phase: visible ? state.phase : "off",
    ready: visible && state.phase === "ready",
    assets: visible ? state.assets : undefined,
    error: visible ? state.error : undefined,
    imageLoaded,
    imageFailed,
  };
}
