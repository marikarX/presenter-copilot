import { describe, expect, it } from "vitest";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import {
  runPdfWorker,
  savePresentationPdf,
  stopPdfExports,
  validatePdfDestination,
  validatePdfRequest,
} from "./pdf-export";
import type { SidecarCommand } from "./sidecar-command";

async function fixture(script: string) {
  const root = await mkdtemp(path.join(os.tmpdir(), "presenter-pdf-test-"));
  const file = path.join(root, "worker.cjs");
  await writeFile(file, script);
  const runtime: SidecarCommand = {
    command: process.execPath,
    args: [file],
    cwd: root,
    env: {
      ...process.env,
      OPENAI_API_KEY: "fake-never-use",
      PRIVATE_TOKEN: "fake",
      PRESENTER_COPILOT_DATA_ROOT: root,
    },
    shell: false,
  };
  return { root, runtime };
}
const request = () => ({
  project_id: randomUUID(),
  document_id: randomUUID(),
  expected_revision_id: randomUUID(),
  include_hidden: false,
});

describe("native PDF privileged boundaries", () => {
  it("rejects paths, unknown options and non-boolean hidden options from renderer", () => {
    expect(validatePdfRequest(request()).includeHidden).toBe(false);
    expect(() =>
      validatePdfRequest({ ...request(), snapshot_path: "arbitrary.pptx" }),
    ).toThrow();
    expect(() =>
      validatePdfRequest({ ...request(), include_hidden: 1 }),
    ).toThrow();
    expect(() =>
      validatePdfRequest({ ...request(), expected_revision_id: "stale" }),
    ).toThrow();
  });
  it("requires PDF outside application storage and confirms a regular file", async () => {
    const { root } = await fixture("");
    const data = path.join(root, "vault");
    await mkdir(data);
    await expect(
      validatePdfDestination(path.join(data, "deck.pdf"), data),
    ).rejects.toThrow();
    await expect(
      validatePdfDestination(path.join(root, "deck.pptx"), data),
    ).rejects.toThrow();
    await expect(
      validatePdfDestination("relative.pdf", data),
    ).rejects.toThrow();
    expect(await validatePdfDestination(path.join(root, "deck"), data)).toBe(
      path.join(root, "deck.pdf"),
    );
  });
  it("separate child strips credentials and never echoes stderr", async () => {
    const { runtime } =
      await fixture(`console.error('private path and account data');
      process.stdin.resume(); process.stdin.on('end', () => process.stdout.write(JSON.stringify({ok:true,result:{
      flag:process.argv.at(-1), credential:!!process.env.OPENAI_API_KEY, token:!!process.env.PRIVATE_TOKEN,
      vault:!!process.env.PRESENTER_COPILOT_DATA_ROOT}})));`);
    expect(await runPdfWorker(runtime, {})).toEqual({
      flag: "--native-pdf-export",
      credential: false,
      token: false,
      vault: false,
    });
  });
  it("handles a terminal structured unavailable error", async () => {
    const { runtime } =
      await fixture(`process.stdin.resume();process.stdin.on('end',()=>{
      console.log(JSON.stringify({ok:false,error:{code:'PRESENTATION_PDF_UNAVAILABLE',message:'PowerPoint is unavailable.',retryable:false,details:{}}}));process.exitCode=1;});`);
    await expect(runPdfWorker(runtime, {})).rejects.toMatchObject({
      code: "PRESENTATION_PDF_UNAVAILABLE",
    });
  });
  it("stops only owned worker on timeout or oversized output", async () => {
    const hanging = await fixture("setInterval(()=>{},1000);");
    await expect(runPdfWorker(hanging.runtime, {}, 100)).rejects.toMatchObject({
      code: "PRESENTATION_PDF_TIMEOUT",
    });
    const oversized = await fixture(
      "process.stdin.resume();process.stdin.on('end',()=>{console.log('x'.repeat(17000));setInterval(()=>{},1000);});",
    );
    await expect(runPdfWorker(oversized.runtime, {})).rejects.toMatchObject({
      code: "PRESENTATION_PDF_FAILED",
    });
  });
  it("cancelled picker does not copy or start conversion", async () => {
    const { root, runtime } = await fixture("throw new Error('must not run');");
    expect(
      await savePresentationPdf(request(), {
        dataRoot: root,
        runtime,
        chooseDestination: async () => null,
        copyRevision: async () => {
          throw new Error("must not copy");
        },
      }),
    ).toEqual({ cancelled: true });
  });
  it("stale revision leaves the chosen existing destination intact", async () => {
    const { root, runtime } = await fixture("throw new Error('must not run');");
    const destination = path.join(root, "deck.pdf");
    await writeFile(destination, "keep");
    await expect(
      savePresentationPdf(request(), {
        dataRoot: path.join(root, "vault"),
        runtime,
        chooseDestination: async () => destination,
        copyRevision: async () => {
          throw new Error("revision changed");
        },
      }),
    ).rejects.toThrow("revision changed");
    expect(await readFile(destination, "utf8")).toBe("keep");
  });
  it("rejects corrupt native receipt without replacing the chosen PDF", async () => {
    const { root, runtime } = await fixture(
      `process.stdin.resume();process.stdin.on('end',()=>console.log(JSON.stringify({ok:true,result:{renderer:'experimental_preview'}})));`,
    );
    const destination = path.join(root, "deck.pdf");
    await writeFile(destination, "keep");
    const value = request();
    await expect(
      savePresentationPdf(value, {
        dataRoot: path.join(root, "vault"),
        runtime,
        chooseDestination: async () => destination,
        copyRevision: async () => ({
          saved: true,
          revision_id: value.expected_revision_id,
          copy_kind: "current_revision",
          sha256: "a".repeat(64),
        }),
      }),
    ).rejects.toMatchObject({ code: "PRESENTATION_PDF_FAILED" });
    expect(await readFile(destination, "utf8")).toBe("keep");
  });
  it("atomically saves only verified worker bytes and returns revision receipt without paths", async () => {
    const { root, runtime } =
      await fixture(`let input='';process.stdin.on('data',c=>input+=c);process.stdin.on('end',()=>{
      const fs=require('node:fs'), crypto=require('node:crypto'), job=JSON.parse(input), bytes=Buffer.from('%PDF-test-receipt');
      fs.writeFileSync(job.output_path,bytes);console.log(JSON.stringify({ok:true,result:{source_sha256:job.source_sha256,renderer:'microsoft_powerpoint',include_hidden:job.include_hidden,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),byte_size:bytes.length,page_count:1,slide_count:2}}));});`);
    const destination = path.join(root, "deck.pdf");
    await writeFile(destination, "previous file");
    const value = request();
    let copiedParams: unknown;
    const result = await savePresentationPdf(value, {
      dataRoot: path.join(root, "vault"),
      runtime,
      chooseDestination: async () => destination,
      copyRevision: async (params) => {
        copiedParams = params;
        return {
          saved: true,
          revision_id: value.expected_revision_id,
          copy_kind: "current_revision",
          sha256: "a".repeat(64),
        };
      },
    });
    expect(copiedParams).toMatchObject({
      expected_revision_id: value.expected_revision_id,
    });
    expect(result).toMatchObject({
      saved: true,
      revision_id: value.expected_revision_id,
      file_name: "deck.pdf",
      page_count: 1,
    });
    expect(JSON.stringify(result)).not.toContain(root);
    expect(await readFile(destination, "utf8")).toBe("%PDF-test-receipt");
  });
  it("app shutdown closes the owned worker before accepting more PDF jobs", async () => {
    const { runtime } = await fixture("setInterval(()=>{},1000);");
    const pending = runPdfWorker(runtime, {});
    const rejected = expect(pending).rejects.toMatchObject({
      code: "PRESENTATION_PDF_CANCELLED",
    });
    await stopPdfExports();
    await rejected;
    await expect(runPdfWorker(runtime, {})).rejects.toMatchObject({
      code: "PRESENTATION_PDF_CANCELLED",
    });
  });
});
