/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for picture brightness/contrast/grayscale.
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
  path.join(os.tmpdir(), "presenter-picture-adjust-"),
);
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "picture-adjust");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "adjust.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import io, sys
from PIL import Image
from pptx import Presentation
from pptx.util import Inches
image=io.BytesIO()
Image.new('RGB',(64,48),(200,80,40)).save(image,'PNG');image.seek(0)
deck=Presentation()
slide=deck.slides.add_slide(deck.slide_layouts[6])
picture=slide.shapes.add_picture(image,Inches(2),Inches(2),Inches(4),Inches(3))
picture.name='Adjust target'
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
    .fill("Picture adjust acceptance");
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
  await page.getByRole("button", { name: /adjust\.pptx/ }).waitFor();
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
    (item) => item.name === "Picture adjust acceptance",
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
    return inventory.objects.find((item) => item.name === "Adjust target");
  };
  const initial = await target();
  assert.deepEqual(initial.picture_adjustment, {
    brightness_percent: 0,
    contrast_percent: 0,
    grayscale: false,
  });
  checks.push("A plain embedded picture reports neutral editable adjustments");

  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Objects", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .selectOption({ label: "Adjust target · pic · editable" });
  const apply = page.getByRole("button", {
    name: "Apply picture adjustments",
    exact: true,
  });
  assert.equal(await apply.isDisabled(), true, "No pending adjustment");
  await page.getByLabel("Picture Brightness (%)", { exact: true }).fill("150");
  await page
    .getByRole("alert")
    .filter({ hasText: "whole percentages" })
    .waitFor();
  assert.equal(
    await apply.isDisabled(),
    true,
    "Out-of-range value blocks save",
  );
  await page.getByLabel("Picture Brightness (%)", { exact: true }).fill("20");
  await page.getByLabel("Picture Contrast (%)", { exact: true }).fill("-30");
  await page.getByLabel("Picture grayscale", { exact: true }).check();
  await apply.click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  const changed = await target();
  assert.deepEqual(changed.picture_adjustment, {
    brightness_percent: 20,
    contrast_percent: -30,
    grayscale: true,
  });
  assert.deepEqual(changed.picture_crop, initial.picture_crop);
  assert.equal(await apply.isDisabled(), true, "Controls read back the save");
  checks.push(
    "GUI rejects 150% and applies +20% brightness, -30% contrast and grayscale as one native revision",
  );
  await page.screenshot({ path: path.join(output, "picture-adjust.png") });

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 1", { exact: true }).waitFor();
  assert.deepEqual(
    (await target()).picture_adjustment,
    initial.picture_adjustment,
  );
  checks.push("Undo restores the unadjusted picture");
  await page.getByLabel("Shape outline color", { exact: true }).fill("#1f3a5f");
  await page
    .getByRole("button", { name: "Apply outline color", exact: true })
    .click();
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  assert.equal((await target()).shape_style.line_color, "#1F3A5F");
  checks.push("GUI adds a navy picture border as one native revision");
  const altApply = page.getByRole("button", {
    name: "Apply alt text",
    exact: true,
  });
  await page
    .getByLabel("Alt text", { exact: true })
    .fill("Orange block standing in for the pilot chart");
  await altApply.click();
  await workspace.getByText("Current · Revision 4", { exact: true }).waitFor();
  assert.deepEqual(
    [(await target()).alt_text, (await target()).decorative],
    ["Orange block standing in for the pilot chart", false],
  );
  assert.equal(await altApply.isDisabled(), true, "Alt text reads back");
  await page.getByLabel("Mark as decorative", { exact: true }).check();
  await altApply.click();
  await workspace.getByText("Current · Revision 5", { exact: true }).waitFor();
  assert.deepEqual(
    [(await target()).alt_text, (await target()).decorative],
    ["", true],
  );
  checks.push(
    "GUI writes alt text, then marks the picture decorative, as native revisions",
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
