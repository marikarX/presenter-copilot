import { describe, expect, it } from "vitest";
import { createHash, randomUUID } from "node:crypto";
import { access, readFile, writeFile } from "node:fs/promises";
import {
  renderNativeAppearance,
  validateNativeAppearanceRequest,
} from "./native-appearance";
import type { JsonObject } from "../shared/protocol";
import type { SidecarCommand } from "./sidecar-command";

const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jVq0AAAAASUVORK5CYII=",
  "base64",
);
const runtime: SidecarCommand = {
  command: process.execPath,
  args: [],
  cwd: process.cwd(),
  env: {},
  shell: false,
};
function request() {
  return {
    project_id: randomUUID(),
    document_id: randomUUID(),
    expected_revision_id: randomUUID(),
    source_sha256: "a".repeat(64),
    slide_number: 1,
  };
}

describe("privileged native appearance", () => {
  it("rejects renderer paths, unknown fields and unbounded indices", () => {
    for (const update of [
      { snapshot_path: "C:/other.pptx" },
      { slide_number: 0 },
      { slide_number: 5001 },
      { slide_number: true },
      { source_sha256: "unknown" },
    ]) {
      expect(() =>
        validateNativeAppearanceRequest({ ...request(), ...update }),
      ).toThrow();
    }
  });
  it("copies only the exact revision and verifies PNG before deleting private files", async () => {
    const target = request();
    let input = "",
      output = "";
    const result = await renderNativeAppearance(target, {
      runtime,
      copyRevision: async (params) => {
        expect(params.expected_revision_id).toBe(target.expected_revision_id);
        expect(params.project_id).toBe(target.project_id);
        input = params.destination_path as string;
        await writeFile(input, "owned revision");
        return {
          saved: true,
          revision_id: target.expected_revision_id,
          copy_kind: "current_revision",
          sha256: target.source_sha256,
        };
      },
      runWorker: async (_runtime, job) => {
        expect(await readFile(job.snapshot_path as string, "utf8")).toBe(
          "owned revision",
        );
        output = job.output_path as string;
        await writeFile(output, png);
        return {
          source_sha256: target.source_sha256,
          slide_number: 1,
          slide_count: 2,
          width: 1,
          height: 1,
          byte_size: png.length,
          sha256: createHash("sha256").update(png).digest("hex"),
          renderer: "microsoft_powerpoint",
        };
      },
    });
    expect(Buffer.from(result.image)).toEqual(png);
    expect(result.revision_id).toBe(target.expected_revision_id);
    await expect(access(input)).rejects.toThrow();
    await expect(access(output)).rejects.toThrow();
  });
  it("never launches Office for a stale copied revision", async () => {
    let called = false;
    await expect(
      renderNativeAppearance(request(), {
        runtime,
        copyRevision: async () => ({ saved: true, revision_id: randomUUID() }),
        runWorker: async () => {
          called = true;
          return {};
        },
      }),
    ).rejects.toThrow();
    expect(called).toBe(false);
  });
  it.each(["hash", "slide", "size", "bytes"])(
    "rejects a mismatched %s receipt",
    async (issue) => {
      const target = request();
      let output = "";
      await expect(
        renderNativeAppearance(target, {
          runtime,
          copyRevision: async (params) => {
            await writeFile(params.destination_path as string, "owned");
            return {
              saved: true,
              revision_id: target.expected_revision_id,
              copy_kind: "current_revision",
              sha256: target.source_sha256,
            };
          },
          runWorker: async (_runtime, job) => {
            output = job.output_path as string;
            await writeFile(
              output,
              issue === "bytes"
                ? Buffer.concat([png, Buffer.from("changed")])
                : png,
            );
            const receipt: JsonObject = {
              source_sha256: target.source_sha256,
              slide_number: 1,
              slide_count: 2,
              width: 1,
              height: 1,
              byte_size: png.length,
              sha256: createHash("sha256").update(png).digest("hex"),
              renderer: "microsoft_powerpoint",
            };
            if (issue === "hash") receipt.source_sha256 = "b".repeat(64);
            if (issue === "slide") receipt.slide_number = 2;
            if (issue === "size") receipt.width = 2;
            return receipt;
          },
        }),
      ).rejects.toThrow();
      await expect(access(output)).rejects.toThrow();
    },
  );
});
