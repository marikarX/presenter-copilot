/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for a slide's entrance animations.
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
  path.join(os.tmpdir(), "presenter-animations-"),
);
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "slide-animations");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "animations.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import io, sys
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches
deck=Presentation()
slide=deck.slides.add_slide(deck.slide_layouts[5])
slide.shapes.title.text='Animated'
box=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(1),Inches(2),Inches(3),Inches(2))
box.name='Box'; box.text='Point'
image=io.BytesIO(); Image.new('RGB',(32,24),(40,120,200)).save(image,'PNG'); image.seek(0)
slide.shapes.add_picture(image,Inches(5),Inches(2),Inches(3),Inches(2)).name='Chart image'
bullets=slide.shapes.add_textbox(Inches(1),Inches(4.5),Inches(4),Inches(2))
bullets.name='Bullets'; bullets.text_frame.text='One'
for t in ('Two','Three'): bullets.text_frame.add_paragraph().text=t
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
    .fill("Animation acceptance");
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
  await page.getByRole("button", { name: /animations\.pptx/ }).waitFor();
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
    (item) => item.name === "Animation acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const state = async () => {
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
    const result = await ask("presentation.workspace.get_slide_animations", {
      project_id: project,
      document_id: document,
      expected_revision_id: revision,
      slide_id: slide,
    });
    return result.effects.map((e) => [e.name, e.effect, e.start]);
  };
  assert.deepEqual(await state(), []);
  await page.getByText("Slide actions & layout", { exact: true }).click();
  await page
    .getByText("No entrance animations on this slide.", { exact: true })
    .waitFor();
  checks.push("A new slide reports no entrance animations");

  const add = async (name, effect) => {
    await page
      .getByLabel("Object to animate", { exact: true })
      .selectOption({ label: name });
    await page
      .getByLabel("New animation effect", { exact: true })
      .selectOption({ label: effect });
    await page
      .getByRole("button", { name: "Add animation", exact: true })
      .click();
  };
  const apply = page.getByRole("button", {
    name: "Apply animations",
    exact: true,
  });
  assert.equal(await apply.isDisabled(), true, "Nothing pending");
  await add("Box", "Fade");
  await add("Chart image", "Fly in");
  await page
    .getByLabel("Animation start for Chart image", { exact: true })
    .selectOption({ label: "After previous" });
  await apply.click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.deepEqual(await state(), [
    ["Box", "fade", "on_click"],
    ["Chart image", "fly_in", "after_previous"],
  ]);
  assert.equal(await apply.isDisabled(), true, "Controls read back the save");
  checks.push(
    "GUI adds Fade on click and Fly in after previous as one native revision",
  );
  await page.screenshot({ path: path.join(output, "slide-animations.png") });

  await page
    .getByRole("button", { name: "Play Chart image earlier", exact: true })
    .click();
  await page
    .getByLabel("Animation effect for Box", { exact: true })
    .selectOption({ label: "Zoom" });
  await apply.click();
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  assert.deepEqual(await state(), [
    ["Chart image", "fly_in", "after_previous"],
    ["Box", "zoom", "on_click"],
  ]);
  checks.push("GUI reorders the sequence and switches Box to Zoom");

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.deepEqual(await state(), [
    ["Box", "fade", "on_click"],
    ["Chart image", "fly_in", "after_previous"],
  ]);
  await page.getByLabel("Animation effect for Box", { exact: true }).waitFor();
  assert.equal(
    await page
      .getByLabel("Animation effect for Box", { exact: true })
      .inputValue(),
    "fade",
  );
  checks.push("Undo restores the previous sequence in the controls");

  await page
    .getByRole("button", { name: "Remove animation from Box", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Remove animation from Chart image",
      exact: true,
    })
    .click();
  await apply.click();
  await workspace.getByText("Current · Revision 4", { exact: true }).waitFor();
  assert.deepEqual(await state(), []);
  checks.push("GUI removes every animation as one native revision");

  await add("Box", "Fade");
  await add("Box", "Fade out");
  await page
    .getByLabel("Exit effect for Box", { exact: true })
    .selectOption({ label: "Fly out" });
  await apply.click();
  await workspace.getByText("Current · Revision 5", { exact: true }).waitFor();
  assert.deepEqual(await state(), [
    ["Box", "fade", "on_click"],
    ["Box", "fly_out", "on_click"],
  ]);
  checks.push(
    "GUI gives Box a Fade entrance and a Fly out exit as one revision",
  );

  await page
    .getByLabel("Object to animate", { exact: true })
    .selectOption({ label: "Bullets" });
  await page
    .getByLabel("New animation effect", { exact: true })
    .selectOption({ label: "Wipe" });
  await page.getByLabel("Animate by paragraph", { exact: true }).check();
  await page
    .getByRole("button", { name: "Add animation", exact: true })
    .click();
  await page
    .getByLabel("Animation start for Bullets paragraph 1", { exact: true })
    .selectOption({ label: "After previous" });
  await apply.click();
  await workspace.getByText("Current · Revision 6", { exact: true }).waitFor();
  const revision = (
    await ask("presentation.workspace.list_revisions", {
      project_id: project,
      document_id: document,
    })
  ).current_revision_id;
  const slideId = (
    await ask("presentation.workspace.list_text_targets", {
      project_id: project,
      document_id: document,
      revision_id: revision,
      slide_number: 1,
    })
  ).slide_id;
  const built = (
    await ask("presentation.workspace.get_slide_animations", {
      project_id: project,
      document_id: document,
      expected_revision_id: revision,
      slide_id: slideId,
    })
  ).effects
    .filter((e) => e.name === "Bullets")
    .map((e) => [e.effect, e.start, e.paragraph]);
  assert.deepEqual(built, [
    ["wipe", "after_previous", 0],
    ["wipe", "on_click", 1],
    ["wipe", "on_click", 2],
  ]);
  checks.push(
    "GUI builds Bullets by paragraph: one Wipe step per paragraph, the first after previous",
  );

  await add("Chart image", "Pulse");
  await page
    .getByLabel("Emphasis start for Chart image", { exact: true })
    .selectOption({ label: "With previous" });
  await apply.click();
  await workspace.getByText("Current · Revision 7", { exact: true }).waitFor();
  assert.deepEqual(
    (await state()).filter(([name]) => name === "Chart image"),
    [["Chart image", "pulse", "with_previous"]],
  );
  checks.push(
    "GUI adds a Pulse emphasis to the chart image with the previous step",
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
