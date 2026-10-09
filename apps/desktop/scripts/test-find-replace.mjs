/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for deck-wide find and replace.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-find-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "find-replace");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "find.pptx");
// PowerPoint-style list paragraphs: a text-font buFont plus a buChar marker.
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
from pptx.util import Inches, Pt
deck=Presentation()
first=deck.slides.add_slide(deck.slide_layouts[6])
box=first.shapes.add_textbox(Inches(1),Inches(1),Inches(7),Inches(1)); box.name='Mixed runs'
p=box.text_frame.paragraphs[0]
p.add_run().text='Retire the Legacy plan and the '
bold=p.add_run(); bold.text='legacy tools'; bold.font.bold=True
split=first.shapes.add_textbox(Inches(1),Inches(3),Inches(7),Inches(1)); split.name='Split word'
q=split.text_frame.paragraphs[0]; q.add_run().text='Leg'; q.add_run().text='acy budget'
second=deck.slides.add_slide(deck.slide_layouts[6])
other=second.shapes.add_textbox(Inches(1),Inches(1),Inches(7),Inches(1)); other.name='Second slide'
other.text_frame.text='LEGACY in capitals'
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
    .fill("Find acceptance");
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
  await page.getByRole("button", { name: /find\.pptx/ }).waitFor();
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
    (item) => item.name === "Find acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const search = async (query) => {
    const revision = (
      await ask("presentation.workspace.list_revisions", {
        project_id: project,
        document_id: document,
      })
    ).current_revision_id;
    return ask("presentation.workspace.find_text", {
      project_id: project,
      document_id: document,
      expected_revision_id: revision,
      query,
      match_case: false,
    });
  };
  await page
    .getByRole("button", { name: "Find and replace", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Find and replace" });
  await dialog.getByLabel("Find text", { exact: true }).fill("legacy");
  await dialog.getByRole("button", { name: "Find", exact: true }).click();
  const results = dialog.getByRole("status", { name: "Search results" });
  await results
    .getByText("3 replaceable matches · 1 not replaceable")
    .waitFor();
  assert.equal(await results.getByRole("listitem").count(), 3);
  checks.push(
    "GUI finds 3 replaceable matches across two slides and reports the run-spanning match as not replaceable",
  );
  await dialog.getByLabel("Match case", { exact: true }).check();
  assert.equal(
    await dialog
      .getByRole("button", { name: "Replace all", exact: true })
      .isDisabled(),
    true,
    "Changing case mode invalidates reviewed results",
  );
  await dialog.getByLabel("Match case", { exact: true }).uncheck();
  await dialog.getByRole("button", { name: "Find", exact: true }).click();
  await dialog.getByLabel("Replace with", { exact: true }).fill("current");
  await page.screenshot({ path: path.join(output, "find-replace.png") });
  await dialog
    .getByRole("button", { name: "Replace all 3", exact: true })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  const after = await search("legacy");
  assert.deepEqual([after.replaceable_matches, after.skipped_matches], [0, 1]);
  assert.equal((await search("current")).replaceable_matches, 3);
  checks.push(
    "Replace all saves one native revision and keeps the split match untouched",
  );

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 1", { exact: true }).waitFor();
  assert.equal((await search("legacy")).replaceable_matches, 3);
  checks.push("Undo restores every replaced match");
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
