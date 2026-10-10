/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for Reuse Slides.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-reuse-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "reuse-slides");
await mkdir(output, { recursive: true });
const library = path.join(temporary, "library.pptx");
const talk = path.join(temporary, "talk.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
deck=Presentation()
deck.slides.add_slide(deck.slide_layouts[0]).shapes.title.text='Library'
slide=deck.slides.add_slide(deck.slide_layouts[1])
slide.shapes.title.text='Quarterly results'
slide.placeholders[1].text_frame.text='Revenue grew'
slide.notes_slide.notes_text_frame.text='Mention the pilot.'
deck.save(sys.argv[1])
deck=Presentation()
for t in ('Opening','Closing'):
    deck.slides.add_slide(deck.slide_layouts[5]).shapes.title.text=t
deck.save(sys.argv[2])
`,
    library,
    talk,
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
    .fill("Reuse acceptance");
  await page.keyboard.press("Enter");
  await page
    .getByRole("heading", { name: "Sources", exact: true })
    .first()
    .waitFor();
  for (const file of [library, talk]) {
    await app.evaluate(({ dialog }, chosen) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [chosen],
      });
    }, file);
    await page
      .getByLabel("Import source kind", { exact: true })
      .selectOption("presentation");
    await page
      .getByRole("button", { name: "Import source…", exact: true })
      .click();
    await page
      .getByRole("button", {
        name: new RegExp(path.basename(file).replace(".", "[.]")),
      })
      .waitFor();
  }
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  const chooser = page.getByLabel("Workspace presentation", { exact: true });
  await chooser.selectOption({
    label: (await chooser.locator("option").allTextContents()).find((text) =>
      text.startsWith("talk.pptx"),
    ),
  });
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
    (item) => item.name === "Reuse acceptance",
  ).id;
  const listed = (await ask("source.list", { project_id: project })).sources;
  const document = listed.find((item) => item.original_name === "talk.pptx").id;
  const slideText = async (number) => {
    const revision = (
      await ask("presentation.workspace.list_revisions", {
        project_id: project,
        document_id: document,
      })
    ).current_revision_id;
    return ask("presentation.workspace.list_text_targets", {
      project_id: project,
      document_id: document,
      revision_id: revision,
      slide_number: number,
    });
  };
  await page.getByText("Slide actions & layout", { exact: true }).click();
  await page
    .getByLabel("Presentation to reuse from", { exact: true })
    .selectOption({ label: "library.pptx" });
  await page.getByLabel("Slide to reuse", { exact: true }).selectOption("2");
  await page
    .getByLabel("Slide to reuse preview", { exact: true })
    .getByText("Quarterly results · Revenue grew", { exact: true })
    .waitFor();
  checks.push("GUI previews slide 2 of the library deck before reusing it");
  await page
    .getByLabel("Insert reused slide", { exact: true })
    .selectOption({ label: "After slide 1" });
  await page.getByRole("button", { name: "Reuse slide", exact: true }).click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  await page
    .getByText("with the Title and Content layout and its speaker notes.", {
      exact: false,
    })
    .waitFor();
  const reused = await slideText(2);
  assert.equal(reused.slide_count, 3);
  assert.deepEqual(
    reused.targets.map((item) => item.current_text).filter(Boolean),
    ["Quarterly results", "Revenue grew"],
  );
  assert.equal(reused.speaker_notes.current_text, "Mention the pilot.");
  await page.screenshot({ path: path.join(output, "reuse-slides.png") });
  checks.push(
    "GUI reuses the library slide as slide 2 with the destination layout and its notes, as one revision",
  );
  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 1", { exact: true }).waitFor();
  assert.equal((await slideText(1)).slide_count, 2);
  checks.push("Undo removes the reused slide");
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
