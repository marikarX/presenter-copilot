import { CoreClientError } from "./core-client";
let rendering = false;
/** Serialize owned PowerPoint slide/layer jobs without touching shared Office processes. */
export function reserveNativeRendering() {
  if (rendering)
    throw new CoreClientError({
      code: "PRESENTATION_NATIVE_PREVIEW_FAILED",
      message:
        "PowerPoint is rendering another slide. Try again when it finishes.",
      retryable: false,
      details: {},
    });
  rendering = true;
  let live = true;
  return () => {
    if (live) {
      live = false;
      rendering = false;
    }
  };
}
