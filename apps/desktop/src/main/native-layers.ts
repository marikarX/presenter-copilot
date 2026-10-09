import { createHash } from "node:crypto";
import { lstat, mkdtemp, open, realpath, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { CoreClientError } from "./core-client";
import { runPdfWorker } from "./pdf-export";
import { reserveNativeRendering } from "./native-render-lease";
import {
  validateNativeAppearanceRequest,
  type NativeAppearanceDependencies,
} from "./native-appearance";
import { isJsonObject, type NativeLayersResult } from "../shared/protocol";
const SHA = /^[0-9a-f]{64}$/;
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const MAX_IMAGE_BYTES = 16 * 1024 * 1024,
  MAX_BYTES = 96 * 1024 * 1024;
function fail(message: string) {
  return new CoreClientError({
    code: "PRESENTATION_NATIVE_LAYERS_FAILED",
    message,
    retryable: false,
    details: {},
  });
}

/** No caller-provided paths cross this privileged image preparation boundary. */
export async function renderNativeLayers(
  value: unknown,
  dependencies: NativeAppearanceDependencies,
): Promise<NativeLayersResult> {
  const request = validateNativeAppearanceRequest(value);
  const release = reserveNativeRendering();
  let directory: string | undefined, temporaryRoot: string | undefined;
  try {
    temporaryRoot = await realpath(os.tmpdir());
    directory = await mkdtemp(
      path.join(temporaryRoot, "presenter-native-layers-"),
    );
    async function copy(filename: string) {
      const receipt = await dependencies.copyRevision({
        project_id: request.projectId,
        document_id: request.documentId,
        expected_revision_id: request.revisionId,
        destination_path: path.join(directory!, filename),
      });
      if (
        !isJsonObject(receipt) ||
        receipt.saved !== true ||
        receipt.copy_kind !== "current_revision" ||
        receipt.revision_id !== request.revisionId ||
        receipt.sha256 !== request.sourceSha256
      )
        throw fail(
          "The saved revision changed while preparing live object movement.",
        );
    }
    await copy("revision.pptx");
    const result = await (
      dependencies.runWorker ??
      ((runtime, job) => runPdfWorker(runtime, job, 120_000, "layers"))
    )(dependencies.runtime, {
      snapshot_path: path.join(directory, "revision.pptx"),
      output_path: path.join(directory, "layers.json"),
      source_sha256: request.sourceSha256,
      document_id: request.documentId,
      slide_number: request.slideNumber,
    });
    if (
      result.source_sha256 !== request.sourceSha256 ||
      result.document_id !== request.documentId ||
      result.slide_number !== request.slideNumber ||
      result.renderer !== "microsoft_powerpoint" ||
      ![result.width, result.height, result.slide_count].every(
        (n) => typeof n === "number" && Number.isInteger(n) && n > 0,
      ) ||
      (result.width as number) > 4096 ||
      (result.height as number) > 4096 ||
      (result.slide_count as number) < request.slideNumber ||
      (result.slide_count as number) > 5000 ||
      typeof result.baseline_max_channel_error !== "number" ||
      !Number.isInteger(result.baseline_max_channel_error) ||
      result.baseline_max_channel_error < 0 ||
      result.baseline_max_channel_error > 4 ||
      !Array.isArray(result.layers) ||
      result.layers.length > 200 ||
      (result.layers.length + 2) *
        (result.width as number) *
        (result.height as number) *
        4 >
        256 * 1024 * 1024
    )
      throw fail(
        "The native layer identity, baseline or dimensions could not be verified.",
      );
    let total = 0;
    async function image(record: unknown, expectedFile: string) {
      if (
        !isJsonObject(record) ||
        record.file !== expectedFile ||
        typeof record.sha256 !== "string" ||
        !SHA.test(record.sha256) ||
        typeof record.byte_size !== "number" ||
        !Number.isInteger(record.byte_size) ||
        record.byte_size < 33 ||
        record.byte_size > MAX_IMAGE_BYTES
      )
        throw fail("The native layer image receipt is invalid.");
      total += record.byte_size;
      if (total > MAX_BYTES)
        throw fail("The native layer images exceed their display budget.");
      const filename = path.join(directory!, expectedFile),
        stat = await lstat(filename);
      if (
        stat.isSymbolicLink() ||
        !stat.isFile() ||
        stat.size !== record.byte_size ||
        (await realpath(filename)) !== filename
      )
        throw fail("The native layer image file is invalid.");
      const handle = await open(filename, "r");
      let bytes: Buffer;
      try {
        const opened = await handle.stat();
        if (!opened.isFile() || opened.size !== stat.size)
          throw fail("The native layer image changed.");
        bytes = await handle.readFile();
      } finally {
        await handle.close();
      }
      if (
        bytes.length !== record.byte_size ||
        !bytes
          .subarray(0, 8)
          .equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) ||
        bytes.subarray(12, 16).toString("ascii") !== "IHDR" ||
        bytes.readUInt32BE(16) !== result.width ||
        bytes.readUInt32BE(20) !== result.height ||
        createHash("sha256").update(bytes).digest("hex") !== record.sha256
      )
        throw fail("The native layer PNG or hash could not be verified.");
      return { sha256: record.sha256, image: new Uint8Array(bytes) };
    }
    const background = await image(result.background, "layers-background.png");
    const layers: NativeLayersResult["layers"] = [],
      ids = new Set<string>(),
      shapeIds = new Set<string>();
    for (let index = 0; index < result.layers.length; index++) {
      const layer = result.layers[index];
      if (
        !isJsonObject(layer) ||
        typeof layer.object_id !== "string" ||
        !UUID.test(layer.object_id) ||
        ids.has(layer.object_id) ||
        typeof layer.ooxml_shape_id !== "string" ||
        !/^[1-9][0-9]{0,9}$/.test(layer.ooxml_shape_id) ||
        shapeIds.has(layer.ooxml_shape_id) ||
        typeof layer.visible !== "boolean"
      )
        throw fail(
          "The native layer object identities or paint order are invalid.",
        );
      ids.add(layer.object_id);
      shapeIds.add(layer.ooxml_shape_id);
      layers.push({
        object_id: layer.object_id,
        ooxml_shape_id: layer.ooxml_shape_id,
        visible: layer.visible,
        ...(await image(layer, `layers-layer-${index}.png`)),
      });
    }
    // Re-copy with the expected current head after slow Office/image work. The Core
    // rejects a concurrently changed head, and both copies remain privately owned.
    await copy("verified-current.pptx");
    await dependencies.validateAfterRender?.();
    return {
      revision_id: request.revisionId,
      source_sha256: request.sourceSha256,
      document_id: request.documentId,
      slide_number: request.slideNumber,
      width: result.width as number,
      height: result.height as number,
      renderer: "microsoft_powerpoint",
      baseline_max_channel_error: result.baseline_max_channel_error,
      background,
      layers,
    };
  } catch (error) {
    if (error instanceof CoreClientError) throw error;
    throw fail(
      "PowerPoint could not prepare verified live object movement. Use the normal slide preview.",
    );
  } finally {
    try {
      if (
        directory &&
        temporaryRoot &&
        path.dirname(path.resolve(directory)) === temporaryRoot
      )
        await rm(directory, {
          recursive: true,
          force: true,
          maxRetries: 2,
          retryDelay: 100,
        }).catch(() => undefined);
    } finally {
      release();
    }
  }
}
