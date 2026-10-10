/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX: double-click a group on the canvas to edit a member.
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
const temporary = await mkdtemp(
  path.join(os.tmpdir(), "presenter-group-canvas-"),
);
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "group-canvas");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "group.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches
deck=Presentation()
slide=deck.slides.add_slide(deck.slide_layouts[6])
group=slide.shapes.add_group_shape()
group.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(1),Inches(1),Inches(2),Inches(1)).name='Inner A'
group.shapes.add_shape(MSO_SHAPE.OVAL,Inches(4),Inches(3),Inches(2),Inches(2)).name='Inner B'
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
    .fill("Group canvas acceptance");
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
  await page.getByRole("button", { name: /group\.pptx/ }).waitFor();
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
    (item) => item.name === "Group canvas acceptance",
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
    return inventory.objects.find((item) => item.name === "Inner A");
  };
  const initial = await target();
  assert.equal(initial.group_child, true);
  await page.getByText("Select objects on slide", { exact: true }).click();
  const overlay = page.getByLabel("Select slide objects", { exact: true });
  const member = overlay.getByRole("button", {
    name: "Select Inner A on slide",
    exact: true,
  });
  assert.equal(
    await member.count(),
    0,
    "Members are hidden until the group is entered",
  );
  await overlay
    .getByRole("button", { name: /^Select Group \d+ on slide$/ })
    .dblclick();
  await member.waitFor();
  await member.click();
  checks.push("Double-clicking a group exposes its members on the canvas");

  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Objects", exact: true })
    .click();
  assert.equal(
    await page
      .getByRole("combobox", { name: "Object to edit", exact: true })
      .inputValue(),
    initial.object_id,
  );
  await page
    .getByRole("spinbutton", { name: "X position (inches)", exact: true })
    .fill("2.000");
  await page
    .getByRole("button", { name: "Save object layout", exact: true })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  const moved = await target();
  assert.equal(moved.geometry.x_emu, 2 * 914400);
  checks.push(
    "The selected member moves inside its group as one native revision",
  );
  await page.screenshot({ path: path.join(output, "group-canvas.png") });

  const revision = (
    await ask("presentation.workspace.list_revisions", {
      project_id: project,
      document_id: document,
    })
  ).current_revision_id;
  const slide = (
    await ask("presentation.workspace.list_text_targets", {
      project_id: project,
      document_id: document,
      revision_id: revision,
      slide_number: 1,
    })
  ).slide_id;
  const outside = await page.evaluate(
    (params) =>
      window.presenterCopilot.core.request(
        "presentation.workspace.transform_object",
        params,
      ),
    {
      project_id: project,
      document_id: document,
      expected_revision_id: revision,
      slide_id: slide,
      object_id: moved.object_id,
      expected_geometry: moved.geometry,
      replacement_geometry: { ...moved.geometry, x_emu: 8 * 914400 },
    },
  );
  assert.equal(outside.ok, false);
  assert.match(outside.error.message, /group/);
  checks.push("Moving a member outside its group frame is refused");
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
