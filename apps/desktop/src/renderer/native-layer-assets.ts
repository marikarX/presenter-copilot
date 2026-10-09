import type { NativeLayersResult } from "../shared/protocol";
import type { NativeAppearanceTarget } from "./NativeAppearance";
import type { LayoutObject } from "./object-layout";
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export function isCurrentNativeLayers(
  frame: NativeLayersResult,
  target: NativeAppearanceTarget,
  slide: number,
  objects: LayoutObject[],
) {
  const asset = (value: NativeLayersResult["background"]) =>
    !!value &&
    /^[0-9a-f]{64}$/.test(value.sha256) &&
    value.image instanceof Uint8Array &&
    value.image.byteLength >= 33 &&
    value.image.byteLength <= 16 * 1024 * 1024;
  if (
    !frame ||
    target.planId ||
    frame.revision_id !== target.revisionId ||
    frame.source_sha256 !== target.sourceSha256 ||
    frame.document_id !== target.documentId ||
    frame.slide_number !== slide ||
    frame.renderer !== "microsoft_powerpoint" ||
    ![frame.width, frame.height].every(
      (v) => Number.isInteger(v) && v > 0 && v <= 4096,
    ) ||
    !Number.isInteger(frame.baseline_max_channel_error) ||
    frame.baseline_max_channel_error < 0 ||
    frame.baseline_max_channel_error > 4 ||
    !asset(frame.background) ||
    !Array.isArray(frame.layers) ||
    frame.layers.length > 200 ||
    (frame.layers.length + 2) * frame.width * frame.height * 4 >
      256 * 1024 * 1024
  )
    return false;
  const ids = new Set<string>(),
    shapeIds = new Set<string>();
  let total = frame.background.image.byteLength;
  for (const layer of frame.layers) {
    if (
      !layer ||
      !UUID.test(layer.object_id) ||
      ids.has(layer.object_id) ||
      !/^[1-9][0-9]{0,9}$/.test(layer.ooxml_shape_id) ||
      shapeIds.has(layer.ooxml_shape_id) ||
      typeof layer.visible !== "boolean" ||
      !asset(layer)
    )
      return false;
    ids.add(layer.object_id);
    shapeIds.add(layer.ooxml_shape_id);
    total += layer.image.byteLength;
  }
  return (
    total <= 96 * 1024 * 1024 && objects.every((o) => ids.has(o.object_id))
  );
}
export function createNativeLayerUrls(
  frame: NativeLayersResult,
  urls: Pick<typeof URL, "createObjectURL" | "revokeObjectURL"> = URL,
) {
  const created: string[] = [];
  let live = true;
  const dispose = () => {
    if (live) {
      live = false;
      for (const value of created) urls.revokeObjectURL(value);
    }
  };
  const make = (image: Uint8Array) => {
    const value = urls.createObjectURL(
      new Blob([new Uint8Array(image)], { type: "image/png" }),
    );
    created.push(value);
    return value;
  };
  try {
    return {
      background: make(frame.background.image),
      layers: frame.layers.map((l) => ({
        objectId: l.object_id,
        value: make(l.image),
      })),
      dispose,
    };
  } catch (error) {
    dispose();
    throw error;
  }
}
