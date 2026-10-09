import { createHash } from "node:crypto";
import { open } from "node:fs/promises";
import {
  isJsonObject,
  type CoreMethod,
  type JsonObject,
} from "../shared/protocol";

export interface EditPlanSnapshotTarget {
  projectId: string;
  documentId: string;
  revisionId: string;
  planId: string;
  sourceSha256: string;
}
type Request = (method: CoreMethod, params: JsonObject) => Promise<unknown>;

/** Main supplies the destination in its owned directory; renderer paths never enter here. */
export async function withEditPlanReader<T>(
  target: EditPlanSnapshotTarget,
  request: Request,
  consume: (reader: JsonObject) => Promise<T>,
): Promise<T> {
  const scope = {
    project_id: target.projectId,
    document_id: target.documentId,
  };
  const reader = await request(
    "presentation.workspace.open_edit_plan_preview",
    {
      ...scope,
      plan_id: target.planId,
    },
  );
  if (!isJsonObject(reader))
    throw new Error("Invalid proposed package reader.");
  const sessionId = reader.session_id;
  if (typeof sessionId !== "string" || !sessionId || sessionId.length > 64)
    throw new Error("Invalid proposed package session.");
  try {
    if (
      reader.plan_id !== target.planId ||
      reader.revision_id !== target.revisionId ||
      reader.revision_kind !== "edit_plan_preview" ||
      reader.is_edit_plan_preview !== true ||
      reader.sha256 !== target.sourceSha256 ||
      typeof reader.byte_size !== "number" ||
      !Number.isSafeInteger(reader.byte_size) ||
      reader.byte_size < 1 ||
      reader.byte_size > 50 * 1024 * 1024 ||
      typeof reader.chunk_bytes !== "number" ||
      !Number.isSafeInteger(reader.chunk_bytes) ||
      reader.chunk_bytes < 1 ||
      reader.chunk_bytes > 512 * 1024
    )
      throw new Error("The proposed package identity changed.");
    return await consume(reader);
  } finally {
    // EOF also closes the reader; Core close_source is deliberately idempotent.
    await request("presentation.workspace.close_source", {
      ...scope,
      session_id: sessionId,
    }).catch(() => undefined);
  }
}

export async function copyEditPlanSnapshot(
  target: EditPlanSnapshotTarget,
  destination: string,
  request: Request,
): Promise<JsonObject> {
  return withEditPlanReader(target, request, async (reader) => {
    const file = await open(destination, "wx");
    try {
      const digest = createHash("sha256");
      let offset = 0;
      const size = reader.byte_size as number;
      const chunkSize = reader.chunk_bytes as number;
      while (offset < size) {
        const chunk = await request("presentation.workspace.read_source", {
          project_id: target.projectId,
          document_id: target.documentId,
          session_id: reader.session_id,
          offset,
          max_bytes: chunkSize,
        });
        if (
          !isJsonObject(chunk) ||
          typeof chunk.bytes_b64 !== "string" ||
          chunk.bytes_b64.length > Math.ceil(chunkSize / 3) * 4
        )
          throw new Error("Invalid proposed package chunk.");
        const bytes = Buffer.from(chunk.bytes_b64, "base64");
        if (
          bytes.toString("base64") !== chunk.bytes_b64 ||
          chunk.offset !== offset ||
          bytes.length !== Math.min(chunkSize, size - offset) ||
          chunk.complete !== (offset + bytes.length === size)
        )
          throw new Error("The proposed package stream changed.");
        await file.writeFile(bytes);
        digest.update(bytes);
        offset += bytes.length;
      }
      if (digest.digest("hex") !== target.sourceSha256)
        throw new Error("The proposed package hash changed.");
      await file.sync();
      return {
        saved: true,
        revision_id: target.revisionId,
        copy_kind: "edit_plan_preview",
        plan_id: target.planId,
        sha256: target.sourceSha256,
        byte_size: size,
      };
    } finally {
      await file.close();
    }
  });
}
