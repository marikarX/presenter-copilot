import { describe, expect, it } from "vitest";
import { createHash, randomUUID } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { copyEditPlanSnapshot, withEditPlanReader } from "./edit-plan-snapshot";
import type { CoreMethod, JsonObject } from "../shared/protocol";
import { renderNativeEditAppearance } from "./native-edit-appearance";
import { writeFile } from "node:fs/promises";

const bytes = Buffer.from("immutable proposed presentation");
function fixture(issue = "") {
  const target = {
    projectId: randomUUID(),
    documentId: randomUUID(),
    revisionId: randomUUID(),
    planId: randomUUID(),
    sourceSha256: createHash("sha256").update(bytes).digest("hex"),
  };
  let closed = 0,
    reads = 0;
  const request = async (
    method: CoreMethod,
    params: JsonObject,
  ): Promise<unknown> => {
    expect(params.project_id).toBe(target.projectId);
    expect(params.document_id).toBe(target.documentId);
    if (method === "presentation.workspace.close_source") {
      closed++;
      return { closed: true };
    }
    if (method === "presentation.workspace.open_edit_plan_preview") {
      expect(params.plan_id).toBe(target.planId);
      return {
        session_id: "owned-reader",
        plan_id: target.planId,
        revision_id: issue === "baseline" ? randomUUID() : target.revisionId,
        revision_kind:
          issue === "kind" ? "current_revision" : "edit_plan_preview",
        is_edit_plan_preview: true,
        sha256: target.sourceSha256,
        byte_size: bytes.length,
        chunk_bytes: 7,
      };
    }
    expect(method).toBe("presentation.workspace.read_source");
    reads++;
    const offset = params.offset as number;
    const chunk = bytes.subarray(offset, offset + 7);
    return {
      offset: issue === "offset" ? offset + 1 : offset,
      bytes_b64:
        issue === "encoding"
          ? chunk.toString("base64") + "\n"
          : issue === "hash"
            ? Buffer.alloc(chunk.length).toString("base64")
            : chunk.toString("base64"),
      complete:
        issue === "complete" ? true : offset + chunk.length === bytes.length,
    };
  };
  return { target, request, counters: () => ({ closed, reads }) };
}
describe("Main-owned proposed package snapshot", () => {
  it.each([false, true])(
    "revalidates the proposal after rendering (discarded=%s)",
    async (discarded) => {
      const f = fixture();
      let opens = 0;
      const result = renderNativeEditAppearance(
        {
          project_id: f.target.projectId,
          document_id: f.target.documentId,
          expected_revision_id: f.target.revisionId,
          plan_id: f.target.planId,
          source_sha256: f.target.sourceSha256,
          slide_number: 1,
        },
        {
          runtime: {
            command: process.execPath,
            args: [],
            cwd: process.cwd(),
            env: {},
            shell: false,
          },
          request: async (method, params) => {
            if (
              method === "presentation.workspace.open_edit_plan_preview" &&
              ++opens === 2 &&
              discarded
            )
              throw new Error("Plan discarded while rendering");
            return f.request(method, params);
          },
          runWorker: async (_runtime, job) => {
            expect(await readFile(job.snapshot_path as string)).toEqual(bytes);
            const png = Buffer.from(
              "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jVq0AAAAASUVORK5CYII=",
              "base64",
            );
            await writeFile(job.output_path as string, png);
            return {
              source_sha256: f.target.sourceSha256,
              slide_number: 1,
              slide_count: 1,
              width: 1,
              height: 1,
              byte_size: png.length,
              sha256: createHash("sha256").update(png).digest("hex"),
              renderer: "microsoft_powerpoint",
            };
          },
        },
      );
      if (discarded) await expect(result).rejects.toThrow();
      else expect((await result).plan_id).toBe(f.target.planId);
      expect(opens).toBe(2);
      expect(f.counters().closed).toBe(discarded ? 1 : 2);
    },
  );
  it("copies exact multi-chunk bytes and closes its reader", async () => {
    const f = fixture();
    const directory = await mkdtemp(
      path.join(os.tmpdir(), "presenter-plan-test-"),
    );
    try {
      const destination = path.join(directory, "revision.pptx");
      const receipt = await copyEditPlanSnapshot(
        f.target,
        destination,
        f.request,
      );
      expect(await readFile(destination)).toEqual(bytes);
      expect(receipt.copy_kind).toBe("edit_plan_preview");
      expect(receipt.plan_id).toBe(f.target.planId);
      expect(f.counters()).toEqual({ closed: 1, reads: 5 });
      await expect(
        copyEditPlanSnapshot(f.target, destination, f.request),
      ).rejects.toThrow();
      expect(await readFile(destination)).toEqual(bytes);
      expect(f.counters().closed).toBe(2);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
  it.each(["baseline", "kind", "offset", "encoding", "hash", "complete"])(
    "rejects %s corruption and releases the reader",
    async (issue) => {
      const f = fixture(issue);
      const directory = await mkdtemp(
        path.join(os.tmpdir(), "presenter-plan-test-"),
      );
      try {
        await expect(
          copyEditPlanSnapshot(
            f.target,
            path.join(directory, "revision.pptx"),
            f.request,
          ),
        ).rejects.toThrow();
        expect(f.counters().closed).toBe(1);
        if (["baseline", "kind"].includes(issue))
          expect(f.counters().reads).toBe(0);
      } finally {
        await rm(directory, { recursive: true, force: true });
      }
    },
  );
  it("closes a revalidation reader when its consumer rejects", async () => {
    const f = fixture();
    await expect(
      withEditPlanReader(f.target, f.request, async () => {
        throw new Error("discarded");
      }),
    ).rejects.toThrow("discarded");
    expect(f.counters()).toEqual({ closed: 1, reads: 0 });
  });
});
