import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { lstat, mkdtemp, open, realpath, rename, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { CoreClientError } from "./core-client";
import type { SidecarCommand } from "./sidecar-command";
import {
  isCoreError,
  isJsonObject,
  type JsonObject,
  type PresentationPdfResult,
} from "../shared/protocol";

const MAX_PDF_BYTES = 100 * 1024 * 1024;
let exporting = false;
let stopping = false;
const workers = new Set<ChildProcessWithoutNullStreams>();

export async function stopPdfExports(): Promise<void> {
  stopping = true;
  await Promise.all(
    [...workers].map(
      (child) =>
        new Promise<void>((resolve) => {
          child.once("close", () => resolve());
          child.kill(); // Never terminate an Office process on app shutdown.
        }),
    ),
  );
}

function fail(code: string, message: string): CoreClientError {
  return new CoreClientError({ code, message, retryable: false, details: {} });
}

export function validatePdfRequest(value: unknown) {
  const uuid =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (
    !isJsonObject(value) ||
    Object.keys(value).some(
      (key) =>
        ![
          "project_id",
          "document_id",
          "expected_revision_id",
          "include_hidden",
        ].includes(key),
    ) ||
    ![value.project_id, value.document_id, value.expected_revision_id].every(
      (id) => typeof id === "string" && uuid.test(id),
    ) ||
    typeof value.include_hidden !== "boolean"
  ) {
    throw fail(
      "INVALID_REQUEST",
      "The PDF export target or options are invalid.",
    );
  }
  return {
    projectId: value.project_id as string,
    documentId: value.document_id as string,
    revisionId: (value.expected_revision_id as string).toLowerCase(),
    includeHidden: value.include_hidden,
  };
}

export async function validatePdfDestination(
  value: string,
  dataRoot: string,
): Promise<string> {
  let destination = value;
  if (!path.extname(destination)) destination += ".pdf";
  if (
    !path.isAbsolute(destination) ||
    path.extname(destination).toLowerCase() !== ".pdf"
  )
    throw fail(
      "PRESENTATION_PDF_DESTINATION_INVALID",
      "Choose an absolute file name ending in .pdf.",
    );
  const parent = await realpath(path.dirname(destination));
  const root = await realpath(dataRoot).catch(() => path.resolve(dataRoot));
  const result = path.join(parent, path.basename(destination));
  const relative = path.relative(root, result);
  if (
    !relative ||
    (!relative.startsWith(`..${path.sep}`) &&
      relative !== ".." &&
      !path.isAbsolute(relative))
  )
    throw fail(
      "PRESENTATION_PDF_DESTINATION_INVALID",
      "Save the PDF outside Presenter Copilot storage.",
    );
  const existing = await lstat(result).catch((error: NodeJS.ErrnoException) => {
    if (error.code === "ENOENT") return null;
    throw error;
  });
  if (existing && (!existing.isFile() || existing.isSymbolicLink()))
    throw fail(
      "PRESENTATION_PDF_DESTINATION_INVALID",
      "Choose a regular PDF file destination.",
    );
  return result;
}

export async function runPdfWorker(
  runtime: SidecarCommand,
  job: JsonObject,
  timeoutMs = 120_000,
  mode: "pdf" | "preview" | "layers" = "pdf",
): Promise<JsonObject> {
  if (stopping)
    throw fail(
      "PRESENTATION_PDF_CANCELLED",
      "PDF export was cancelled because the app is closing.",
    );
  return new Promise((resolve, reject) => {
    const env = { ...runtime.env };
    // The conversion process has no provider, account or project-vault work.
    for (const key of Object.keys(env)) {
      if (
        /OPENAI|OPENROUTER|API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|PRESENTER_COPILOT_DATA_ROOT|PRESENTER_COPILOT_TEST/i.test(
          key,
        )
      )
        delete env[key];
    }
    const child = spawn(
      runtime.command,
      [
        ...runtime.args,
        mode === "layers"
          ? "--native-layers-export"
          : mode === "preview"
            ? "--native-preview-export"
            : "--native-pdf-export",
      ],
      {
        cwd: runtime.cwd,
        env,
        shell: false,
        windowsHide: true,
        stdio: "pipe",
      },
    );
    workers.add(child);
    let output = "";
    let failure: unknown = null;
    const stop = (error: unknown) => {
      failure ??= error;
      child.kill(); // Only this owned worker, never PowerPoint.
    };
    const timer = setTimeout(
      () =>
        stop(
          fail(
            "PRESENTATION_PDF_TIMEOUT",
            "PowerPoint PDF export timed out. Check PowerPoint before trying again.",
          ),
        ),
      timeoutMs,
    );
    child.on("error", () => {
      failure ??= fail(
        "PRESENTATION_PDF_UNAVAILABLE",
        "The native PDF worker could not start.",
      );
    });
    child.stdin.on("error", () =>
      stop(
        fail(
          "PRESENTATION_PDF_FAILED",
          "The native PDF job could not be sent.",
        ),
      ),
    );
    child.stderr.on("data", () => {
      /* Do not retain raw Office diagnostics. */
    });
    child.stdout.on("data", (chunk: Buffer) => {
      if (failure) return;
      output += chunk.toString("utf8");
      if (Buffer.byteLength(output) > (mode === "layers" ? 256 * 1024 : 16_384))
        stop(
          fail(
            "PRESENTATION_PDF_FAILED",
            "The PDF worker returned an invalid response.",
          ),
        );
    });
    // Resolve only after the owned worker is terminal, before deleting its files.
    child.on("close", (code) => {
      workers.delete(child);
      clearTimeout(timer);
      if (stopping)
        return reject(
          fail(
            "PRESENTATION_PDF_CANCELLED",
            "PDF export was cancelled because the app is closing.",
          ),
        );
      if (failure) return reject(failure);
      try {
        const response: unknown = JSON.parse(output);
        if (
          isJsonObject(response) &&
          response.ok === false &&
          isCoreError(response.error)
        )
          return reject(new CoreClientError(response.error));
        if (
          code !== 0 ||
          !isJsonObject(response) ||
          response.ok !== true ||
          !isJsonObject(response.result)
        )
          throw new Error("Invalid worker receipt");
        resolve(response.result);
      } catch {
        reject(
          fail(
            "PRESENTATION_PDF_FAILED",
            "PowerPoint could not produce a verified PDF.",
          ),
        );
      }
    });
    child.stdin.end(JSON.stringify(job));
  });
}

export async function savePresentationPdf(
  value: unknown,
  dependencies: {
    dataRoot: string;
    runtime: SidecarCommand;
    chooseDestination(): Promise<string | null>;
    copyRevision(params: JsonObject): Promise<unknown>;
  },
): Promise<PresentationPdfResult | { cancelled: true }> {
  const request = validatePdfRequest(value);
  if (exporting)
    throw fail("PRESENTATION_PDF_BUSY", "A PDF export is already running.");
  exporting = true;
  let directory: string | undefined;
  let temporaryRoot: string | undefined;
  let pending: string | undefined;
  try {
    const selection = await dependencies.chooseDestination();
    if (!selection) return { cancelled: true };
    const destination = await validatePdfDestination(
      selection,
      dependencies.dataRoot,
    );
    temporaryRoot = await realpath(os.tmpdir());
    directory = await mkdtemp(path.join(temporaryRoot, "presenter-pdf-"));
    const snapshot = path.join(directory, "revision.pptx");
    const output = path.join(directory, "revision.pdf");
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
      copied.copy_kind !== "current_revision" ||
      typeof copied.sha256 !== "string" ||
      !/^[0-9a-f]{64}$/.test(copied.sha256)
    )
      throw fail(
        "PRESENTATION_PDF_FAILED",
        "The presentation revision could not be verified for PDF export.",
      );
    const receipt = await runPdfWorker(dependencies.runtime, {
      snapshot_path: snapshot,
      output_path: output,
      source_sha256: copied.sha256,
      include_hidden: request.includeHidden,
    });
    if (
      receipt.source_sha256 !== copied.sha256 ||
      receipt.renderer !== "microsoft_powerpoint" ||
      receipt.include_hidden !== request.includeHidden ||
      typeof receipt.byte_size !== "number" ||
      !Number.isInteger(receipt.byte_size) ||
      receipt.byte_size <= 0 ||
      receipt.byte_size > MAX_PDF_BYTES ||
      typeof receipt.sha256 !== "string" ||
      !/^[0-9a-f]{64}$/.test(receipt.sha256) ||
      typeof receipt.page_count !== "number" ||
      !Number.isInteger(receipt.page_count) ||
      receipt.page_count < 1 ||
      typeof receipt.slide_count !== "number" ||
      !Number.isInteger(receipt.slide_count) ||
      receipt.slide_count < receipt.page_count ||
      receipt.slide_count > 5000
    )
      throw fail(
        "PRESENTATION_PDF_FAILED",
        "The native PDF receipt could not be verified.",
      );
    const input = await open(output, "r");
    let bytes: Buffer;
    try {
      if ((await input.stat()).size !== receipt.byte_size)
        throw new Error("PDF size mismatch");
      bytes = await input.readFile();
    } finally {
      await input.close();
    }
    if (
      bytes.length !== receipt.byte_size ||
      bytes.subarray(0, 5).toString("ascii") !== "%PDF-" ||
      createHash("sha256").update(bytes).digest("hex") !== receipt.sha256
    )
      throw fail(
        "PRESENTATION_PDF_FAILED",
        "The exported PDF changed before it could be saved.",
      );
    // Create and flush beside the chosen destination, then atomically replace it.
    pending = path.join(
      path.dirname(destination),
      `.presenter-pdf-${randomUUID()}.tmp`,
    );
    const file = await open(pending, "wx", 0o600);
    try {
      await file.writeFile(bytes);
      await file.sync();
    } finally {
      await file.close();
    }
    await validatePdfDestination(destination, dependencies.dataRoot);
    await rename(pending, destination);
    pending = undefined;
    return {
      saved: true,
      file_name: path.basename(destination),
      revision_id: request.revisionId,
      source_sha256: copied.sha256,
      sha256: receipt.sha256,
      byte_size: receipt.byte_size,
      page_count: receipt.page_count,
      include_hidden: request.includeHidden,
      renderer: "microsoft_powerpoint",
    };
  } finally {
    if (pending) await rm(pending, { force: true }).catch(() => undefined);
    if (directory) {
      // Exact private mkdtemp path only; never traverse a replaced symlink.
      const actual = await realpath(directory).catch(() => null);
      if (actual === directory && path.dirname(actual) === temporaryRoot)
        await rm(directory, {
          recursive: true,
          force: true,
          maxRetries: 3,
          retryDelay: 100,
        }).catch(() => undefined);
    }
    exporting = false;
  }
}
