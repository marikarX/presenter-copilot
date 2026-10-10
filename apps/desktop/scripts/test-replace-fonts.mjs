/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for Replace Fonts.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-fonts-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "replace-fonts");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "fonts.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
deck=Presentation()
from pptx.util import Inches
for title in ('Intro','Detail'):
    slide=deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text=title
    run=slide.shapes.add_textbox(Inches(1),Inches(2),Inches(5),Inches(1)).text_frame.paragraphs[0].add_run()
    run.text=title+' body'
    run.font.name='Comic Sans MS'
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
    .fill("Fonts acceptance");
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
  await page.getByRole("button", { name: /fonts\.pptx/ }).waitFor();
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
    (item) => item.name === "Fonts acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const fonts = async () =>
    Object.fromEntries(
      (
        await ask("presentation.workspace.list_fonts", {
          project_id: project,
          document_id: document,
          expected_revision_id: (
            await ask("presentation.workspace.list_revisions", {
              project_id: project,
              document_id: document,
            })
          ).current_revision_id,
        })
      ).fonts.map((item) => [item.name, item.uses]),
    );
  assert.equal((await fonts())["Comic Sans MS"], 2);
  await page.getByText("Slide actions & layout", { exact: true }).click();
  const picker = page.getByLabel("Font to replace", { exact: true });
  await picker.waitFor();
  assert.ok(
    (await picker.locator("option").allTextContents()).includes(
      "Comic Sans MS · 2 uses",
    ),
  );
  checks.push("GUI lists the deck's fonts with their use counts");
  await picker.selectOption("Comic Sans MS");
  const replace = page.getByRole("button", {
    name: "Replace font",
    exact: true,
  });
  assert.equal(await replace.isDisabled(), true);
  await page.getByLabel("Replacement font", { exact: true }).fill("Georgia");
  await replace.click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  await page
    .getByText("replaced Comic Sans MS with Georgia in 2 places.", {
      exact: false,
    })
    .waitFor();
  const after = await fonts();
  assert.equal(after["Comic Sans MS"], undefined);
  assert.equal(after.Georgia, 2);
  await picker.locator("option", { hasText: "Georgia · 2 uses" }).waitFor({
    state: "attached",
  });
  await page.screenshot({ path: path.join(output, "replace-fonts.png") });
  checks.push(
    "GUI replaces Comic Sans MS with Georgia across both slides as one native revision",
  );
  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 1", { exact: true }).waitFor();
  await picker
    .locator("option", { hasText: "Comic Sans MS · 2 uses" })
    .waitFor({ state: "attached" });
  checks.push("Undo restores the original font in the list");
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
