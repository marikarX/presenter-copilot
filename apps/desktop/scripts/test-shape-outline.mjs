/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for list numbering and bullet color/size.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-outline-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "shape-outline");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "outline.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt
deck=Presentation()
slide=deck.slides.add_slide(deck.slide_layouts[6])
shape=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(2),Inches(2),Inches(4),Inches(2))
shape.name='Outline target'
shape.fill.solid();shape.fill.fore_color.rgb=RGBColor(0xE0,0xED,0xFA)
shape.line.color.rgb=RGBColor(0x39,0x6E,0xA7);shape.line.width=Pt(1)
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
    .fill("Outline acceptance");
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
  await page.getByRole("button", { name: /outline\.pptx/ }).waitFor();
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
    (item) => item.name === "Outline acceptance",
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
    return inventory.objects.find((item) => item.name === "Outline target")
      .shape_style;
  };
  const initial = await style();
  assert.equal(initial.line_format_editable, true);
  assert.equal(initial.line_width_pt, 1);
  checks.push("A plain rectangle reports an editable 1 pt outline");

  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Objects", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .selectOption({ label: "Outline target · sp · editable" });
  const apply = page.getByRole("button", {
    name: "Apply outline style",
    exact: true,
  });
  assert.equal(await apply.isDisabled(), true, "No pending outline change");
  await page.getByLabel("Shape outline width", { exact: true }).fill("4.5");
  await page
    .getByLabel("Shape outline style", { exact: true })
    .selectOption("dash");
  await apply.click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  const changed = await style();
  assert.deepEqual(
    [changed.line_width_pt, changed.line_dash, changed.line_color],
    [4.5, "dash", "#396EA7"],
  );
  assert.equal(await apply.isDisabled(), true, "Controls read back the save");
  checks.push(
    "GUI applies a 4.5 pt dashed outline as one native revision while keeping the outline color",
  );
  await page.screenshot({ path: path.join(output, "shape-outline.png") });

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 1", { exact: true }).waitFor();
  const undone = await style();
  assert.deepEqual([undone.line_width_pt, undone.line_dash], [1, null]);
  checks.push("Undo restores the original 1 pt solid outline");
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
