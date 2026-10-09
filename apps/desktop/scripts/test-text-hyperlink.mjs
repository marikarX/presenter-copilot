/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for text hyperlinks.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-hyperlink-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "text-hyperlink");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "hyperlink.pptx");
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
    .fill("Hyperlink acceptance");
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
  await page.getByRole("button", { name: /hyperlink\.pptx/ }).waitFor();
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
    (item) => item.name === "Hyperlink acceptance",
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
    return inventory.objects.find((item) => item.object_id === id).hyperlink;
  };
  assert.deepEqual(await style(), { url: null });
  checks.push("A plain text box reports an editable, unlinked text target");

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
  const field = page.getByLabel("Text link", { exact: true });
  const apply = page.getByRole("button", { name: "Apply link", exact: true });
  const remove = page.getByRole("button", { name: "Remove link", exact: true });
  assert.equal(await remove.isDisabled(), true, "Nothing to remove yet");
  await field.fill("javascript:alert(1)");
  assert.equal(await apply.isDisabled(), true, "Script links are blocked");
  await field.fill("https://example.com/legacy-plan");
  await apply.click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.deepEqual(await style(), { url: "https://example.com/legacy-plan" });
  assert.equal(await field.inputValue(), "https://example.com/legacy-plan");
  checks.push(
    "GUI blocks a script link and applies an https link to the text as one native revision",
  );
  await page.screenshot({ path: path.join(output, "text-hyperlink.png") });

  await remove.click();
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  assert.deepEqual(await style(), { url: null });
  checks.push("Remove link clears the link");

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.deepEqual(await style(), { url: "https://example.com/legacy-plan" });
  checks.push("Undo restores the link");
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
