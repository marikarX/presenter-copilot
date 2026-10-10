/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for inserting video and audio.
const require = createRequire(import.meta.url);
const desktop = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const root = path.resolve(desktop, "../..");
const python = path.join(
  root,
  "core",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-media-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "media");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "media.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
deck=Presentation()
deck.slides.add_slide(deck.slide_layouts[6])
import av, numpy as np, wave, struct, math, pathlib
folder=pathlib.Path(sys.argv[1]).parent
with av.open(str(folder/'clip.mp4'),'w') as c:
    s=c.add_stream('libx264',rate=10); s.width,s.height,s.pix_fmt=64,48,'yuv420p'
    for n in range(20):
        px=np.zeros((48,64,3),dtype=np.uint8); px[:,:,2]=200; px[:,:3*(n+1),0]=255
        for p in s.encode(av.VideoFrame.from_ndarray(px,format='rgb24')): c.mux(p)
    for p in s.encode(): c.mux(p)
with wave.open(str(folder/'tone.wav'),'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
    w.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(2*math.pi*440*k/8000))) for k in range(16000)))
deck.save(sys.argv[1])
`,
    fixture,
  ],
  { cwd: root, windowsHide: true, stdio: "pipe" },
);

const env = { ...process.env };
for (const key of Object.keys(env))
  if (
    key.startsWith("PRESENTER_") ||
    key.startsWith("OPENAI_") ||
    key === "OPENROUTER_API_KEY" ||
    key === "ELECTRON_RUN_AS_NODE"
  )
    delete env[key];
Object.assign(env, {
  PRESENTER_COPILOT_DATA_ROOT: path.join(temporary, "core"),
  PRESENTER_CORE_DIR: path.join(root, "core"),
  PRESENTER_COPILOT_DEV_MODE: "1",
  PRESENTER_COPILOT_TEST_PROVIDER: "deterministic_fake",
  PRESENTER_COPILOT_TEST_DECISION: "deterministic_fake",
  PRESENTER_COPILOT_TEST_ASR: "deterministic_fake",
});
const checks = [];
const errors = [];
let app;
let page;
try {
  app = await electron.launch({
    executablePath: require("electron"),
    args: [desktop, `--user-data-dir=${path.join(temporary, "browser")}`],
    cwd: root,
    env,
    timeout: 30_000,
  });
  const deadline = Date.now() + 30_000;
  while (!page && Date.now() < deadline) {
    page = app
      .windows()
      .find((candidate) => candidate.url().endsWith("/renderer/index.html"));
    if (!page) await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(page);
  page.setDefaultTimeout(30_000);
  page.on("pageerror", (error) => errors.push(error.message));
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill("Media acceptance");
  await page.keyboard.press("Enter");
  await page
    .getByRole("heading", { name: "Sources", exact: true })
    .first()
    .waitFor();
  await app.evaluate(({ dialog }, file) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [file],
    });
  }, fixture);
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("presentation");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  await page.getByRole("button", { name: /media\.pptx/ }).waitFor();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  const workspace = page.locator(".presentation-workspace");
  await workspace.getByText("Current · Revision 1", { exact: true }).waitFor();
  const ask = async (method, params) =>
    page.evaluate(
      async ({ method, params }) => {
        const r = await window.presenterCopilot.core.request(method, params);
        if (!r.ok) throw new Error(`${r.error.code}: ${r.error.message}`);
        return r.result;
      },
      { method, params },
    );
  const project = (await ask("project.list", {})).projects.find(
    (item) => item.name === "Media acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const objects = async () =>
    (
      await ask("presentation.workspace.list_text_targets", {
        project_id: project,
        document_id: document,
        revision_id: (
          await ask("presentation.workspace.list_revisions", {
            project_id: project,
            document_id: document,
          })
        ).current_revision_id,
        slide_number: 1,
      })
    ).objects;
  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Objects", exact: true })
    .click();
  const insert = page.getByRole("button", {
    name: "Insert video or audio…",
    exact: true,
  });
  for (const [file, revision, label, name] of [
    ["clip.mp4", 2, "a video (0:02)", "Video 1"],
    ["tone.wav", 3, "an audio clip (0:02)", "Audio 1"],
  ]) {
    await app.evaluate(
      ({ dialog }, chosen) => {
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [chosen],
        });
      },
      path.join(temporary, file),
    );
    await insert.click();
    await workspace
      .getByText(`Current · Revision ${revision}`, { exact: true })
      .waitFor();
    await page.getByText(`with ${label}`, { exact: false }).waitFor();
    const created = (await objects()).find((item) => item.name === name);
    assert.ok(created, name);
    assert.equal(created.geometry_editable, true);
    checks.push(
      `GUI inserts ${file} as ${name}, movable, as one native revision`,
    );
  }
  await page.screenshot({ path: path.join(output, "media.png") });
  await app.evaluate(({ dialog }) => {
    dialog.showOpenDialog = async () => ({ canceled: true, filePaths: [] });
  });
  await insert.click();
  await new Promise((resolve) => setTimeout(resolve, 500));
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  checks.push("Cancelling the file dialog saves nothing");
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors }, null, 2),
  );
  console.log(JSON.stringify({ passed: checks.length, output }, null, 2));
} catch (error) {
  await writeFile(
    path.join(output, "failure-checks.json"),
    JSON.stringify({ checks, errors, error: error.message }, null, 2),
  );
  if (page)
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
  throw error;
} finally {
  if (app) await app.close();
}
