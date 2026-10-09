import { reserveNativeRendering } from "./native-render-lease";
import { createHash } from "node:crypto";
import { lstat, mkdtemp, open, realpath, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { CoreClientError } from "./core-client";
import { runPdfWorker } from "./pdf-export";
import type { SidecarCommand } from "./sidecar-command";
import {
  isJsonObject,
  type JsonObject,
  type NativeAppearanceResult,
} from "../shared/protocol";

const MAX_BYTES = 16 * 1024 * 1024;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SHA = /^[0-9a-f]{64}$/;
function fail(message: string) {
  return new CoreClientError({
    code: "PRESENTATION_NATIVE_PREVIEW_FAILED",
    message,
    retryable: false,
    details: {},
  });
}

export function validateNativeAppearanceRequest(value: unknown) {
  if (
    !isJsonObject(value) ||
    Object.keys(value).some(
      (key) =>
        ![
          "project_id",
          "document_id",
          "expected_revision_id",
          "source_sha256",
          "slide_number",
        ].includes(key),
    ) ||
    ![value.project_id, value.document_id, value.expected_revision_id].every(
      (id) => typeof id === "string" && UUID.test(id),
    ) ||
    typeof value.source_sha256 !== "string" ||
    !SHA.test(value.source_sha256) ||
    typeof value.slide_number !== "number" ||
    !Number.isInteger(value.slide_number) ||
    value.slide_number < 1 ||
    value.slide_number > 5000
  ) {
    throw fail("The saved slide target is invalid.");
  }
  return {
    projectId: value.project_id as string,
    documentId: value.document_id as string,
    revisionId: value.expected_revision_id as string,
    sourceSha256: value.source_sha256,
    slideNumber: value.slide_number,
  };
}

export async function renderNativeAppearance(
  value: unknown,
  dependencies: NativeAppearanceDependencies,
): Promise<NativeAppearanceResult> {
  return renderNativeSnapshot(
    validateNativeAppearanceRequest(value),
    dependencies,
  );
}

export interface NativeAppearanceDependencies {
  runtime: SidecarCommand;
  copyRevision(params: JsonObject): Promise<unknown>;
  runWorker?: (runtime: SidecarCommand, job: JsonObject) => Promise<JsonObject>;
  validateAfterRender?: () => Promise<void>;
}

/** Privileged callers supply an already validated identity and owned-copy producer. */
export async function renderNativeSnapshot(
  request: ReturnType<typeof validateNativeAppearanceRequest>,
  dependencies: NativeAppearanceDependencies,
  planId?: string,
): Promise<NativeAppearanceResult> {
  const release = reserveNativeRendering();
  let directory: string | undefined;
  let temporaryRoot: string | undefined;
  try {
    temporaryRoot = await realpath(os.tmpdir());
    directory = await mkdtemp(
      path.join(temporaryRoot, "presenter-native-appearance-"),
    );
    const snapshot = path.join(directory, "revision.pptx"),
      output = path.join(directory, "slide.png");
    const copied = await dependencies.copyRevision({
      project_id: request.projectId,
      document_id: request.documentId,
      expected_revision_id: request.revisionId,
      destination_path: snapshot,
    });
    if (
      !isJsonObject(copied) ||
      copied.saved !== true ||
      copied.revision_id !== request.revisionId ||
      copied.copy_kind !==
        (planId ? "edit_plan_preview" : "current_revision") ||
      (planId !== undefined && copied.plan_id !== planId) ||
      copied.sha256 !== request.sourceSha256
    ) {
      throw fail(
        "The saved revision changed before its appearance could be rendered.",
      );
    }
    const receipt = await (
      dependencies.runWorker ??
      ((runtime, job) => runPdfWorker(runtime, job, 120_000, "preview"))
    )(dependencies.runtime, {
      snapshot_path: snapshot,
      output_path: output,
      source_sha256: copied.sha256,
      slide_number: request.slideNumber,
    });
    if (
      receipt.source_sha256 !== request.sourceSha256 ||
      receipt.slide_number !== request.slideNumber ||
      receipt.renderer !== "microsoft_powerpoint" ||
      typeof receipt.sha256 !== "string" ||
      !SHA.test(receipt.sha256) ||
      ![
        receipt.width,
        receipt.height,
        receipt.byte_size,
        receipt.slide_count,
      ].every((n) => typeof n === "number" && Number.isInteger(n) && n > 0) ||
      (receipt.byte_size as number) > MAX_BYTES ||
      (receipt.width as number) > 4096 ||
      (receipt.height as number) > 4096 ||
      (receipt.slide_count as number) < request.slideNumber ||
      (receipt.slide_count as number) > 5000
    ) {
      throw fail("The PowerPoint appearance receipt could not be verified.");
    }
    const stat = await lstat(output);
    if (
      stat.isSymbolicLink() ||
      !stat.isFile() ||
      stat.size !== receipt.byte_size ||
      stat.size > MAX_BYTES
    )
      throw fail("The native appearance file is invalid.");
    const file = await open(output, "r");
    let bytes: Buffer;
    try {
      const opened = await file.stat();
      if (!opened.isFile() || opened.size !== stat.size)
        throw fail("The native appearance file changed.");
      bytes = await file.readFile();
    } finally {
      await file.close();
    }
    if (
      bytes.length !== receipt.byte_size ||
      bytes.length < 33 ||
      !bytes
        .subarray(0, 8)
        .equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) ||
      bytes.subarray(12, 16).toString("ascii") !== "IHDR" ||
      bytes.readUInt32BE(16) !== receipt.width ||
      bytes.readUInt32BE(20) !== receipt.height ||
      createHash("sha256").update(bytes).digest("hex") !== receipt.sha256
    ) {
      throw fail("The PowerPoint image changed before it could be displayed.");
    }
    await dependencies.validateAfterRender?.();
    return {
      ...(planId ? { plan_id: planId } : {}),
      revision_id: request.revisionId,
      source_sha256: request.sourceSha256,
      slide_number: request.slideNumber,
      width: receipt.width as number,
      height: receipt.height as number,
      sha256: receipt.sha256,
      renderer: "microsoft_powerpoint",
      image: new Uint8Array(bytes),
    };
  } catch (error) {
    if (
      error instanceof CoreClientError &&
      error.code.startsWith("PRESENTATION_NATIVE_PREVIEW")
    )
      throw error;
    throw fail(
      "PowerPoint could not verify this slide. Use Browser appearance or open a PPTX copy in PowerPoint.",
    );
  } finally {
    try {
      if (
        directory &&
        temporaryRoot &&
        path.dirname(path.resolve(directory)) === temporaryRoot
      ) {
        // A timed-out Office call may still lock our private copy. Never touch other files.
        await rm(directory, {
          recursive: true,
          force: true,
          maxRetries: 2,
          retryDelay: 100,
        }).catch(() => undefined);
      }
    } finally {
      release();
    }
  }
}
