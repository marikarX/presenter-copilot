/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for slide sections.
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-sections-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "slide-sections");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "sections.pptx");
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
    .fill("Section acceptance");
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
  await page.getByRole("button", { name: /sections\.pptx/ }).waitFor();
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
    (item) => item.name === "Section acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const sections = async () => {
    const result = await ask("presentation.workspace.get_slide_sections", {
      project_id: project,
      document_id: document,
      expected_revision_id: (
        await ask("presentation.workspace.list_revisions", {
          project_id: project,
          document_id: document,
        })
      ).current_revision_id,
    });
    return result.sections.map((s) => [
      s.name,
      s.slide_ids.map((id) => result.slide_ids.indexOf(id) + 1),
    ]);
  };
  assert.deepEqual(await sections(), []);
  await page.getByText("Slide actions & layout", { exact: true }).click();
  await page
    .getByText("This presentation has no sections.", { exact: true })
    .waitFor();
  checks.push("A new deck reports no sections");

  const apply = page.getByRole("button", {
    name: "Apply sections",
    exact: true,
  });
  await page
    .getByLabel("New section name", { exact: true })
    .fill("Main points");
  await page
    .getByLabel("New section starts at", { exact: true })
    .selectOption({ label: "Slide 2" });
  await page.getByRole("button", { name: "Add section", exact: true }).click();
  // The first slide gets a default section, as in PowerPoint; rename it.
  await page.getByLabel("Section 1 name", { exact: true }).fill("Opening");
  await apply.click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.deepEqual(await sections(), [
    ["Opening", [1]],
    ["Main points", [2, 3]],
  ]);
  assert.equal(await apply.isDisabled(), true, "Controls read back the save");
  const strip = page.getByRole("navigation", {
    name: "Presentation slides",
    exact: true,
  });
  await strip.getByText("Main points", { exact: true }).waitFor();
  assert.deepEqual(await strip.locator(".pw-slide-section").allTextContents(), [
    "Opening",
    "Main points",
  ]);
  checks.push(
    "GUI splits the deck into Opening and Main points as one native revision, shown in the slide strip",
  );
  await page.screenshot({ path: path.join(output, "slide-sections.png") });

  await page
    .getByRole("button", {
      name: "Merge section Main points into the previous one",
      exact: true,
    })
    .click();
  await apply.click();
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  assert.deepEqual(await sections(), [["Opening", [1, 2, 3]]]);
  checks.push("GUI merges a section into the previous one");

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  await page.getByLabel("Section 2 name", { exact: true }).waitFor();
  assert.equal(
    await page.getByLabel("Section 2 name", { exact: true }).inputValue(),
    "Main points",
  );
  checks.push("Undo restores both sections in the controls");

  await page
    .getByRole("button", { name: "Remove all sections", exact: true })
    .click();
  await workspace.getByText("Current · Revision 4", { exact: true }).waitFor();
  assert.deepEqual(await sections(), []);
  checks.push("GUI removes all sections as one native revision");

  const slideButtons = page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button");
  await slideButtons.nth(2).dragTo(slideButtons.nth(0));
  await workspace.getByText("Current · Revision 5", { exact: true }).waitFor();
  const firstTitle = (
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
  ).targets.find((item) => item.current_text)?.current_text;
  assert.equal(firstTitle, "Details");
  checks.push(
    "Dragging slide 3 onto slide 1 in the slide strip moves it first as one revision",
  );

  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Objects", exact: true })
    .click();
  const objectPicker = page.getByRole("combobox", {
    name: "Object to edit",
    exact: true,
  });
  const titleOption = await objectPicker
    .locator("option")
    .filter({ hasText: /^Title/ })
    .first()
    .getAttribute("value");
  await objectPicker.selectOption(titleOption);
  await page
    .getByLabel("Click action", { exact: true })
    .selectOption({ label: "Go to a slide" });
  await page
    .getByLabel("Click action slide", { exact: true })
    .selectOption({ label: "Slide 3" });
  await page
    .getByRole("button", { name: "Apply click action", exact: true })
    .click();
  await workspace.getByText("Current · Revision 6", { exact: true }).waitFor();
  const linked = await ask("presentation.workspace.list_text_targets", {
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
  const lastSlide = (
    await ask("presentation.workspace.list_text_targets", {
      project_id: project,
      document_id: document,
      revision_id: linked.revision_id,
      slide_number: 3,
    })
  ).slide_id;
  const titleObject = linked.objects.find(
    (item) => item.object_id === titleOption,
  );
  assert.deepEqual(titleObject.click_action, {
    kind: "slide",
    url: null,
    slide_id: lastSlide,
  });
  checks.push(
    "GUI makes slide 1's title jump to slide 3 as one native revision",
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
