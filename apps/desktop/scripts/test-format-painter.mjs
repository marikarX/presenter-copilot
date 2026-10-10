/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for the format painter.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-format-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "format-painter");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "format.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
deck=Presentation()
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt
slide=deck.slides.add_slide(deck.slide_layouts[6])
painter=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,Inches(1),Inches(1),Inches(3),Inches(1))
painter.name='Painter'
painter.fill.solid()
painter.fill.fore_color.rgb=RGBColor(0xC0,0x1F,0x2F)
painter.line.color.rgb=RGBColor(0x1F,0x3F,0xC0)
painter.line.width=Pt(3)
run=painter.text_frame.paragraphs[0].add_run()
run.text='Source'
run.font.bold=True
run.font.name='Georgia'
plain=slide.shapes.add_shape(MSO_SHAPE.OVAL,Inches(5),Inches(1),Inches(2),Inches(1))
plain.name='Plain'
plain.text_frame.text='Target'
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
    .fill("Format acceptance");
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
  await page.getByRole("button", { name: /format\.pptx/ }).waitFor();
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
    (item) => item.name === "Format acceptance",
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
  const objectPicker = page.getByRole("combobox", {
    name: "Object to edit",
    exact: true,
  });
  const pick = async (name) =>
    objectPicker.selectOption(
      await objectPicker
        .locator("option")
        .filter({ hasText: new RegExp(`^${name}`) })
        .first()
        .getAttribute("value"),
    );
  const pasteFormat = page.getByRole("button", {
    name: "Paste format",
    exact: true,
  });
  assert.equal(await pasteFormat.isDisabled(), true);
  await pick("Painter");
  await page.getByRole("button", { name: "Copy format", exact: true }).click();
  await page
    .getByText("Copied the format of Painter.", { exact: false })
    .waitFor();
  assert.equal(
    await pasteFormat.isDisabled(),
    true,
    "The source itself is not a paste target",
  );
  checks.push(
    "GUI copies the Painter's format; the source cannot be its own target",
  );
  await pick("Plain");
  await pasteFormat.click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  await page
    .getByText("with the format of Painter on 1 object.", { exact: false })
    .waitFor();
  const plain = (await objects()).find((item) => item.name === "Plain");
  assert.equal(plain.shape_style.fill_color, "#C01F2F");
  assert.equal(plain.shape_style.line_color, "#1F3FC0");
  assert.equal(plain.shape_style.line_width_pt, 3);
  await page.screenshot({ path: path.join(output, "format-painted.png") });
  checks.push(
    "GUI pastes the fill, outline and text format onto Plain as one native revision",
  );
  await pasteFormat.click();
  await page
    .getByText("Those objects already have this format.", { exact: true })
    .waitFor();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  checks.push("Pasting the same format again saves no revision");
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
