/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for deck-wide slide numbers and footers.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-footers-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "slide-footers");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "footers.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
deck=Presentation()
deck.slides.add_slide(deck.slide_layouts[0]).shapes.title.text='Title'
for t in ('Agenda','Details'):
    deck.slides.add_slide(deck.slide_layouts[1]).shapes.title.text=t
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
    .fill("Footer acceptance");
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
  await page.getByRole("button", { name: /footers\.pptx/ }).waitFor();
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
    (item) => item.name === "Footer acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const footers = async () =>
    ask("presentation.workspace.get_slide_footers", {
      project_id: project,
      document_id: document,
      expected_revision_id: (
        await ask("presentation.workspace.list_revisions", {
          project_id: project,
          document_id: document,
        })
      ).current_revision_id,
    });
  const initial = await footers();
  assert.deepEqual([initial.slide_numbers, initial.footers], ["none", "none"]);
  checks.push("A new deck reports no slide numbers or footers");

  await page.getByText("Slide actions & layout", { exact: true }).click();
  await page.getByLabel("Show slide numbers", { exact: true }).check();
  await page.getByLabel("Footer text", { exact: true }).fill("Confidential");
  await page
    .getByRole("button", { name: "Apply to all slides", exact: true })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  const applied = await footers();
  assert.deepEqual(
    [applied.slide_numbers, applied.footers, applied.footer_text],
    ["some", "some", "Confidential"],
  );
  checks.push(
    "GUI applies slide numbers and a footer to all non-title slides as one native revision",
  );
  await page.screenshot({ path: path.join(output, "slide-footers.png") });

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 1", { exact: true }).waitFor();
  assert.equal((await footers()).slide_numbers, "none");
  checks.push("Undo removes the slide numbers and footers");
  await page.getByLabel("Theme heading font", { exact: true }).fill("Georgia");
  await page.getByLabel("Theme body font", { exact: true }).fill("Segoe UI");
  await page
    .getByRole("button", { name: "Apply theme fonts", exact: true })
    .click();
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  const fonts = await ask("presentation.workspace.get_theme_fonts", {
    project_id: project,
    document_id: document,
    expected_revision_id: (
      await ask("presentation.workspace.list_revisions", {
        project_id: project,
        document_id: document,
      })
    ).current_revision_id,
  });
  assert.deepEqual(
    [fonts.heading_font, fonts.body_font],
    ["Georgia", "Segoe UI"],
  );
  checks.push(
    "GUI changes the theme heading and body fonts as one native revision",
  );
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
