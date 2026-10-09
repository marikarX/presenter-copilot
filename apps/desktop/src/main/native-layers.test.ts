import { describe, expect, it } from "vitest";
import { createHash, randomUUID } from "node:crypto";
import { access, writeFile } from "node:fs/promises";
import path from "node:path";
import { renderNativeLayers } from "./native-layers";
import { renderNativeAppearance } from "./native-appearance";
import type { NativeAppearanceDependencies } from "./native-appearance";
import type { JsonObject } from "../shared/protocol";
import type { SidecarCommand } from "./sidecar-command";
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jVq0AAAAASUVORK5CYII=",
  "base64",
);
const sha = createHash("sha256").update(png).digest("hex");
const runtime: SidecarCommand = {
  command: process.execPath,
  args: [],
  cwd: process.cwd(),
  env: {},
  shell: false,
};
const target = () => ({
  project_id: randomUUID(),
  document_id: randomUUID(),
  expected_revision_id: randomUUID(),
  source_sha256: "a".repeat(64),
  slide_number: 1,
});
function harness(
  request: ReturnType<typeof target>,
  change?: (receipt: JsonObject) => void,
) {
  const files: string[] = [];
  let copies = 0;
  const dependencies: NativeAppearanceDependencies = {
    runtime,
    copyRevision: async (params) => {
      const filename = params.destination_path as string;
      files.push(filename);
      await writeFile(filename, "owned");
      copies++;
      return {
        saved: true,
        copy_kind: "current_revision",
        revision_id: request.expected_revision_id,
        sha256: request.source_sha256,
      };
    },
    runWorker: async (_runtime, job) => {
      const dir = path.dirname(job.output_path as string);
      for (const name of ["layers-background.png", "layers-layer-0.png"]) {
        const file = path.join(dir, name);
        files.push(file);
        await writeFile(file, png);
      }
      const receipt: JsonObject = {
        source_sha256: request.source_sha256,
        document_id: request.document_id,
        slide_number: 1,
        slide_count: 1,
        width: 1,
        height: 1,
        renderer: "microsoft_powerpoint",
        baseline_max_channel_error: 0,
        background: {
          file: "layers-background.png",
          byte_size: png.length,
          sha256: sha,
        },
        layers: [
          {
            object_id: randomUUID(),
            ooxml_shape_id: "2",
            visible: true,
            file: "layers-layer-0.png",
            byte_size: png.length,
            sha256: sha,
          },
        ],
      };
      change?.(receipt);
      return receipt;
    },
  };
  return { dependencies, files, copies: () => copies };
}
describe("privileged native layer assets", () => {
  it("returns verified bytes in order, rechecks the current head and removes all owned files", async () => {
    const request = target(),
      h = harness(request),
      result = await renderNativeLayers(request, h.dependencies);
    expect(h.copies()).toBe(2);
    expect(result.revision_id).toBe(request.expected_revision_id);
    expect(Buffer.from(result.background.image)).toEqual(png);
    expect(Buffer.from(result.layers[0]!.image)).toEqual(png);
    expect(result.layers[0]!.ooxml_shape_id).toBe("2");
    expect(result).not.toHaveProperty("file");
    for (const file of h.files) await expect(access(file)).rejects.toThrow();
  });
  it.each([
    "path",
    "hash",
    "png dimensions",
    "document",
    "source",
    "baseline",
    "duplicates",
    "count",
  ])("rejects %s receipts and removes owned files", async (issue) => {
    const request = target(),
      h = harness(request, (r) => {
        if (issue === "path")
          (r.background as JsonObject).file = "../private.png";
        if (issue === "hash")
          (r.background as JsonObject).sha256 = "b".repeat(64);
        if (issue === "png dimensions") r.width = 2;
        if (issue === "document") r.document_id = randomUUID();
        if (issue === "source") r.source_sha256 = "b".repeat(64);
        if (issue === "baseline") r.baseline_max_channel_error = 5;
        if (issue === "duplicates")
          r.layers = [
            (r.layers as JsonObject[])[0]!,
            (r.layers as JsonObject[])[0]!,
          ];
        if (issue === "count")
          r.layers = Array.from({ length: 201 }, () => ({}));
      });
    await expect(renderNativeLayers(request, h.dependencies)).rejects.toThrow();
    for (const file of h.files) await expect(access(file)).rejects.toThrow();
  });
  it("rejects stale initial copies before launching a worker", async () => {
    let launched = false;
    await expect(
      renderNativeLayers(target(), {
        runtime,
        copyRevision: async () => ({
          saved: true,
          copy_kind: "current_revision",
          revision_id: randomUUID(),
          sha256: "a".repeat(64),
        }),
        runWorker: async () => {
          launched = true;
          return {};
        },
      }),
    ).rejects.toThrow(/changed/);
    expect(launched).toBe(false);
  });
  it("rejects a changed head after native rendering and cleans all private files", async () => {
    const request = target(),
      h = harness(request);
    const original = h.dependencies.copyRevision;
    h.dependencies.copyRevision = async (params) => {
      const receipt = (await original(params)) as JsonObject;
      if (h.copies() === 2) receipt.revision_id = randomUUID();
      return receipt;
    };
    await expect(renderNativeLayers(request, h.dependencies)).rejects.toThrow(
      /changed/,
    );
    for (const file of h.files) await expect(access(file)).rejects.toThrow();
  });
  it("rejects renderer-controlled paths before allocating or copying", async () => {
    let copied = false;
    await expect(
      renderNativeLayers(
        { ...target(), output_path: "C:/private.png" },
        {
          runtime,
          copyRevision: async () => {
            copied = true;
            return {};
          },
        },
      ),
    ).rejects.toThrow();
    expect(copied).toBe(false);
  });
  it("holds the same rendering lease as ordinary native appearance and releases on failure", async () => {
    const request = target(),
      h = harness(request);
    let entered!: () => void, unblock!: () => void;
    const pending = new Promise<void>((resolve) => {
      entered = resolve;
    });
    const gate = new Promise<void>((resolve) => {
      unblock = resolve;
    });
    h.dependencies.runWorker = async () => {
      entered();
      await gate;
      throw new Error("private path must not leak");
    };
    const first = renderNativeLayers(request, h.dependencies);
    const observed = expect(first).rejects.toThrow(
      "PowerPoint could not prepare verified live object movement",
    );
    await pending;
    await expect(
      renderNativeAppearance(request, {
        runtime,
        copyRevision: async () => ({}),
      }),
    ).rejects.toThrow(/another slide/);
    unblock();
    await observed;
    const next = harness(request);
    expect(
      (await renderNativeLayers(request, next.dependencies)).layers,
    ).toHaveLength(1);
  });
});
