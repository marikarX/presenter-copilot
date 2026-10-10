/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for the reusable component library.
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
  path.join(os.tmpdir(), "presenter-components-"),
);
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "components");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "components.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
deck=Presentation()
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches
first=deck.slides.add_slide(deck.slide_layouts[6])
badge=first.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,Inches(1),Inches(1),Inches(2),Inches(1))
badge.name='Badge'
badge.text_frame.text='Confidential'
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
    .fill("Component acceptance");
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
  await page.getByRole("button", { name: /components\.pptx/ }).waitFor();
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
    (item) => item.name === "Component acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const objectsOn = async (number) =>
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
        slide_number: number,
      })
    ).objects.map((item) => item.name);
  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Objects", exact: true })
    .click();
  await page.getByText("No saved components yet.", { exact: true }).waitFor();
  const objectPicker = page.getByRole("combobox", {
    name: "Object to edit",
    exact: true,
  });
  const badge = await objectPicker
    .locator("option")
    .filter({ hasText: /^Badge/ })
    .first()
    .getAttribute("value");
  await objectPicker.selectOption(badge);
  await page
    .getByLabel("Component name", { exact: true })
    .fill("Confidential badge");
  await page
    .getByRole("button", { name: "Save selection as component", exact: true })
    .click();
  const library = page.getByRole("list", {
    name: "Saved components",
    exact: true,
  });
  await library.getByText("Confidential badge", { exact: true }).waitFor();
  const saved = (
    await ask("presentation.workspace.list_components", {
      project_id: project,
    })
  ).components;
  assert.equal(saved.length, 1);
  assert.deepEqual(saved[0].names, ["Badge"]);
  checks.push("GUI saves the selected Badge as a named project component");

  // Delete the original so the insert must come from the saved revision.
  await page
    .getByRole("button", { name: "Review object deletion", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Confirm delete selected object",
      exact: true,
    })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.deepEqual(await objectsOn(1), []);

  const slideButtons = page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button");
  await slideButtons.nth(1).click();
  await page
    .getByRole("button", {
      name: "Insert component Confidential badge",
      exact: true,
    })
    .click();
  const review = page.getByRole("dialog", {
    name: "Review pasted objects",
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
  await page.screenshot({
    path: path.join(output, "component-insert-review.png"),
  });
  await review
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await review.waitFor({ state: "detached" });
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  assert.deepEqual(await objectsOn(2), ["Badge copy"]);
  checks.push(
    "Inserting the component on slide 2 goes through paste review and lands as one revision, even after the original was deleted",
  );

  await page
    .getByRole("button", {
      name: "Delete component Confidential badge",
      exact: true,
    })
    .click();
  await page.getByText("No saved components yet.", { exact: true }).waitFor();
  assert.deepEqual(
    (
      await ask("presentation.workspace.list_components", {
        project_id: project,
      })
    ).components,
    [],
  );
  checks.push("GUI deletes the component from the library");
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
