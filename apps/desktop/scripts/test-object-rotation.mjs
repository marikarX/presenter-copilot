/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for object rotation and flips.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-rotation-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "object-rotation");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "rotation.pptx");
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
shape.name='Rotation target'
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
    .fill("Rotation acceptance");
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
  await page.getByRole("button", { name: /rotation\.pptx/ }).waitFor();
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
    (item) => item.name === "Rotation acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const target = async () => {
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
    return inventory.objects.find((item) => item.name === "Rotation target");
  };
  const initial = await target();
  assert.deepEqual(initial.rotation, {
    rotation_degrees: 0,
    flip_horizontal: false,
    flip_vertical: false,
  });
  checks.push("A plain rectangle reports an upright, unflipped rotation");

  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Objects", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .selectOption({ label: "Rotation target · sp · editable" });
  const apply = page.getByRole("button", {
    name: "Apply rotation",
    exact: true,
  });
  assert.equal(await apply.isDisabled(), true, "No pending rotation");
  await page
    .getByRole("button", { name: "Rotate left 90°", exact: true })
    .click();
  assert.equal(
    await page
      .getByLabel("Object rotation (degrees)", { exact: true })
      .inputValue(),
    "270",
  );
  await page
    .getByRole("button", { name: "Rotate right 90°", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Rotate right 90°", exact: true })
    .click();
  await page.getByLabel("Flip horizontally", { exact: true }).check();
  await apply.click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  const rotated = await target();
  assert.deepEqual(rotated.rotation, {
    rotation_degrees: 90,
    flip_horizontal: true,
    flip_vertical: false,
  });
  assert.deepEqual(rotated.geometry, initial.geometry);
  assert.equal(rotated.geometry_editable, true);
  assert.equal(await apply.isDisabled(), true, "Controls read back the save");
  checks.push(
    "GUI quick-rotates (left wraps to 270) and applies 90 degrees plus a horizontal flip as one native revision without moving the shape",
  );

  await page
    .getByRole("button", { name: "Save object layout", exact: true })
    .waitFor();
  await page.getByText("Select objects on slide", { exact: true }).click();
  const outline = page.getByRole("button", {
    name: "Select Rotation target on slide",
    exact: true,
  });
  assert.match((await outline.getAttribute("transform")) ?? "", /^rotate\(90 /);
  await outline.click();
  assert.equal(
    await page.getByRole("button", { name: /^Resize selection/ }).count(),
    0,
    "Rotated selections expose no unrotated resize handles",
  );
  checks.push(
    "The rotated shape stays layout-editable; its canvas outline is rotated and offers no unrotated resize handles",
  );
  await page.screenshot({ path: path.join(output, "object-rotation.png") });

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 1", { exact: true }).waitFor();
  assert.deepEqual((await target()).rotation, initial.rotation);
  checks.push("Undo restores the upright shape");
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
