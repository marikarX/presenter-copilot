/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for underline and strikethrough.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-emphasis-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "text-emphasis");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "emphasis.pptx");
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
slide=deck.slides.add_slide(deck.slide_layouts[6])
box=slide.shapes.add_textbox(Inches(1),Inches(1),Inches(7),Inches(2))
box.name='Agenda list'
run=box.text_frame.paragraphs[0].add_run();run.text='Retire the legacy plan';run.font.size=Pt(28)
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
    .fill("Emphasis acceptance");
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
  await page.getByRole("button", { name: /emphasis\.pptx/ }).waitFor();
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
    (item) => item.name === "Emphasis acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const style = async () => {
    const revision = (
      await ask("presentation.workspace.list_revisions", {
        project_id: project,
        document_id: document,
      })
    ).current_revision_id;
    const inventory = await ask("presentation.workspace.list_text_targets", {
      project_id: project,
      document_id: document,
      revision_id: revision,
      slide_number: 1,
    });
    const id = inventory.semantic_targets.find(
      (item) => item.name === "Agenda list",
    ).object_id;
    return inventory.targets.find((item) => item.object_id === id).text_style;
  };
  const initial = await style();
  assert.equal(initial.underline, null);
  assert.equal(initial.strikethrough, null);
  checks.push("A plain text box reports unset underline and strikethrough");

  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Text", exact: true })
    .click();
  const targets = page.getByRole("combobox", {
    name: "Text on this slide",
    exact: true,
  });
  const option = targets.locator("option", { hasText: "Agenda list" });
  await option.waitFor({ state: "attached" });
  await targets.selectOption(await option.getAttribute("value"));
  const underline = page.getByRole("button", {
    name: "Underline",
    exact: true,
  });
  const strike = page.getByRole("button", {
    name: "Strikethrough",
    exact: true,
  });
  assert.equal(await underline.getAttribute("aria-pressed"), "false");
  await underline.click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  await strike.click();
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  const both = await style();
  assert.deepEqual([both.underline, both.strikethrough], [true, true]);
  assert.equal(await underline.getAttribute("aria-pressed"), "true");
  assert.equal(await strike.getAttribute("aria-pressed"), "true");
  checks.push(
    "GUI toggles underline then strikethrough on as two native revisions and reflects both as pressed",
  );
  await page.screenshot({ path: path.join(output, "text-emphasis.png") });

  await underline.click();
  await workspace.getByText("Current · Revision 4", { exact: true }).waitFor();
  const cleared = await style();
  assert.deepEqual([cleared.underline, cleared.strikethrough], [false, true]);
  checks.push(
    "Toggling underline off writes an explicit no-underline and keeps the strike",
  );

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  assert.equal((await style()).underline, true);
  checks.push("Undo restores the underlined revision");
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
