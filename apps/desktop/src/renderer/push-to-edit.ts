import { useEffect, useRef, type RefObject } from "react";

export type VoiceGestureCapture = {
  stop(): Promise<void>;
  cancel(): Promise<void>;
};
type Operation = {
  ending: "review" | "cancel" | null;
  ended: Promise<void>;
  end(): void;
};

/** Release can precede capture readiness. End actions own a specific capture ID. */
export class VoiceHoldGesture {
  private operation: Operation | null = null;
  completion: Promise<void> = Promise.resolve();
  get active(): boolean {
    return this.operation !== null;
  }
  press(start: () => Promise<VoiceGestureCapture | null>): boolean {
    if (this.operation) return false;
    let resolveEnd!: () => void;
    const ended = new Promise<void>((resolve) => {
      resolveEnd = resolve;
    });
    const operation: Operation = { ending: null, ended, end: resolveEnd };
    this.operation = operation;
    this.completion = this.run(operation, start);
    // Public completion retains errors for callers/tests; events never leave an unhandled rejection.
    void this.completion.catch(() => undefined);
    return true;
  }
  release(): void {
    const operation = this.operation;
    if (!operation || operation.ending) return;
    operation.ending = "review";
    operation.end();
  }
  cancel(): void {
    const operation = this.operation;
    if (!operation) return;
    operation.ending = "cancel";
    operation.end();
  }
  private async run(
    operation: Operation,
    start: () => Promise<VoiceGestureCapture | null>,
  ): Promise<void> {
    let capture: VoiceGestureCapture | null = null;
    try {
      capture = await start();
      if (!capture) return;
      await operation.ended;
      if (operation.ending === "review") await capture.stop();
      // Escape during stop discards only this capture's local review after stop completes.
      if (operation.ending === "cancel") await capture.cancel();
    } catch (error) {
      if (capture) await capture.cancel().catch(() => undefined);
      throw error;
    } finally {
      if (this.operation === operation) this.operation = null;
    }
  }
}

export const PUSH_TO_EDIT_LABEL = "Ctrl+Shift+Space";

/** Focused Workspace/dialog gesture, without claiming any system-wide shortcut. */
export function usePushToEdit({
  root,
  contextKey,
  disabled,
  start,
}: {
  root: RefObject<HTMLElement | null>;
  contextKey: string;
  disabled: boolean;
  start(): Promise<VoiceGestureCapture | null>;
}) {
  const gesture = useRef(new VoiceHoldGesture());
  const current = useRef({ disabled, start });
  current.current = { disabled, start };
  useEffect(() => {
    const controller = gesture.current;
    let spaceHeld = false;
    const down = (event: KeyboardEvent) => {
      // A modifier can end capture before Space is released. Do not type its
      // trailing repeat into the newly focused transcript or activate a button.
      if (spaceHeld && event.code === "Space") {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (event.key === "Escape" && controller.active) {
        event.preventDefault();
        event.stopPropagation();
        controller.cancel();
        return;
      }
      if (
        event.code !== "Space" ||
        !event.ctrlKey ||
        !event.shiftKey ||
        event.altKey ||
        event.metaKey ||
        event.isComposing
      )
        return;
      if (controller.active) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (event.repeat || current.current.disabled || !document.hasFocus())
        return;
      const element = root.current;
      const active = document.activeElement;
      if (
        !element ||
        !(active instanceof HTMLElement) ||
        !element.getClientRects().length ||
        element.closest('[aria-hidden="true"], [inert]')
      )
        return;
      const owner = element.closest('[role="dialog"], dialog');
      const activeOwner = active.closest('[role="dialog"], dialog');
      if (owner !== activeOwner || !(owner ?? element).contains(active)) return;
      if (controller.press(current.current.start)) {
        spaceHeld = true;
        event.preventDefault();
        event.stopPropagation();
      }
    };
    const up = (event: KeyboardEvent) => {
      if (spaceHeld && event.code === "Space") {
        spaceHeld = false;
        event.preventDefault();
        event.stopPropagation();
        controller.release();
        return;
      }
      if (
        !controller.active ||
        ![
          "Space",
          "ControlLeft",
          "ControlRight",
          "ShiftLeft",
          "ShiftRight",
        ].includes(event.code)
      )
        return;
      event.preventDefault();
      event.stopPropagation();
      controller.release();
    };
    const blur = () => {
      spaceHeld = false;
      controller.cancel();
    };
    const hidden = () => {
      if (document.hidden) blur();
    };
    window.addEventListener("keydown", down, true);
    window.addEventListener("keyup", up, true);
    window.addEventListener("blur", blur);
    document.addEventListener("visibilitychange", hidden);
    return () => {
      controller.cancel();
      window.removeEventListener("keydown", down, true);
      window.removeEventListener("keyup", up, true);
      window.removeEventListener("blur", blur);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, [root, contextKey]);
  return gesture.current;
}
