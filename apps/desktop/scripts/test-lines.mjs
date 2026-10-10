/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for lines and arrows.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-lines-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "lines");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "lines.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
deck=Presentation()
deck.slides.add_slide(deck.slide_layouts[6])
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
    .fill("Lines acceptance");
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
  await page.getByRole("button", { name: /lines\.pptx/ }).waitFor();
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
    (item) => item.name === "Lines acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const line = async () =>
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
    ).objects.find((item) => item.name.startsWith("Line"));
  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Objects", exact: true })
    .click();
  await page.getByLabel("New shape type", { exact: true }).selectOption("line");
  await page.getByRole("button", { name: "Add shape", exact: true }).click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  let created = await line();
  assert.equal(created.geometry.height_emu, 0);
  assert.equal(created.shape_style.shape_geometry, "line");
  checks.push("GUI adds a horizontal line as one native revision");

  await page
    .getByLabel("End arrowhead", { exact: true })
    .selectOption("triangle");
  await page
    .getByRole("button", { name: "Apply outline style", exact: true })
    .click();
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  created = await line();
  assert.equal(created.shape_style.line_end, "triangle");
  assert.equal(created.shape_style.line_start, "none");
  checks.push("GUI turns the line into an arrow with a triangle end");

  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .check();
  const overlay = page.getByLabel("Select slide objects", { exact: true });
  await overlay
    .getByRole("button", {
      name: `Select ${created.name} on slide`,
      exact: true,
    })
    .click();
  const east = overlay.getByRole("button", {
    name: "Resize selection right",
    exact: true,
  });
  await east.focus();
  await east.press("ArrowRight");
  const review = page.getByRole("dialog", {
    name: "Review object layout",
    exact: true,
  });
  await review.waitFor();
  await review
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await review
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor({ timeout: 30000 });
  await review.getByRole("checkbox").check();
  await review
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await review.waitFor({ state: "detached" });
  await workspace.getByText("Current · Revision 4", { exact: true }).waitFor();
  const resized = await line();
  assert.equal(resized.geometry.height_emu, 0, "The line stays flat");
  assert.ok(resized.geometry.width_emu > created.geometry.width_emu);
  await page
    .getByText(/^Verifying presentation/)
    .waitFor({ state: "detached", timeout: 30000 })
    .catch(() => {});
  await page.waitForTimeout(1500);
  await page
    .locator(".pw-slide-stage, .presentation-workspace canvas")
    .first()
    .screenshot({ path: path.join(output, "lines.png") })
    .catch(() => page.screenshot({ path: path.join(output, "lines.png") }));
  checks.push(
    "Selecting the flat line on the canvas and widening it keeps it horizontal",
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
