/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for slide background color and visibility.
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
  path.join(os.tmpdir(), "presenter-background-"),
);
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "slide-background");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "background.pptx");
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
    .fill("Background acceptance");
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
  await page.getByRole("button", { name: /background\.pptx/ }).waitFor();
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
    (item) => item.name === "Background acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const background = async () => {
    const revision = (
      await ask("presentation.workspace.list_revisions", {
        project_id: project,
        document_id: document,
      })
    ).current_revision_id;
    return (
      await ask("presentation.workspace.list_text_targets", {
        project_id: project,
        document_id: document,
        revision_id: revision,
        slide_number: 1,
      })
    ).background;
  };
  assert.deepEqual(await background(), {
    state: "inherited",
    color: null,
    editable: true,
  });
  checks.push("A new slide reports an editable inherited layout background");

  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Objects", exact: true })
    .click();
  const reset = page.getByRole("button", {
    name: "Use layout background",
    exact: true,
  });
  assert.equal(await reset.isDisabled(), true, "Already inherited");
  await page
    .getByLabel("Slide background color", { exact: true })
    .fill("#1f3a5f");
  await page
    .getByRole("button", { name: "Apply background color", exact: true })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.deepEqual(await background(), {
    state: "solid",
    color: "#1F3A5F",
    editable: true,
  });
  await page
    .getByText("This slide uses its own color #1F3A5F.", { exact: true })
    .waitFor();
  checks.push("GUI applies a navy slide background as one native revision");
  await page.screenshot({ path: path.join(output, "slide-background.png") });

  await reset.click();
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  assert.equal((await background()).state, "inherited");
  checks.push("Use layout background removes the slide's own background");

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.equal((await background()).color, "#1F3A5F");
  checks.push("Undo restores the navy background");
  await page.getByText("Slide actions & layout", { exact: true }).click();
  await page
    .getByRole("button", { name: "Hide slide in slide show", exact: true })
    .click();
  await workspace.getByText("Current · Revision 4", { exact: true }).waitFor();
  const visibility = await ask("presentation.workspace.list_text_targets", {
    project_id: project,
    document_id: document,
    revision_id: (
      await ask("presentation.workspace.list_revisions", {
        project_id: project,
        document_id: document,
      })
    ).current_revision_id,
    slide_number: 1,
  });
  assert.equal(visibility.hidden, true);
  await page
    .getByRole("button", { name: "Show slide in slide show", exact: true })
    .waitFor();
  checks.push("GUI hides slide 1 from the slide show as one native revision");
  await page
    .getByLabel("Slide transition", { exact: true })
    .selectOption("fade");
  await workspace.getByText("Current · Revision 5", { exact: true }).waitFor();
  const transition = await ask("presentation.workspace.list_text_targets", {
    project_id: project,
    document_id: document,
    revision_id: (
      await ask("presentation.workspace.list_revisions", {
        project_id: project,
        document_id: document,
      })
    ).current_revision_id,
    slide_number: 1,
  });
  assert.deepEqual([transition.transition, transition.hidden], ["fade", true]);
  checks.push("GUI sets a fade transition while keeping the slide hidden");
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
