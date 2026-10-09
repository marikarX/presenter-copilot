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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-bullets-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "bullet-marker");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "bullets.pptx");
// PowerPoint-style list paragraphs: a text-font buFont plus a buChar marker.
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from lxml import etree
from pptx import Presentation
from pptx.util import Inches, Pt
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
deck=Presentation()
slide=deck.slides.add_slide(deck.slide_layouts[6])
box=slide.shapes.add_textbox(Inches(1),Inches(1),Inches(7),Inches(3))
box.name='Agenda list'
frame=box.text_frame
for index,text in enumerate(['Context','Options','Recommendation']):
 paragraph=frame.paragraphs[0] if index==0 else frame.add_paragraph()
 run=paragraph.add_run();run.text=text;run.font.size=Pt(24)
 props=paragraph._p.get_or_add_pPr();props.set('marL','342900');props.set('indent','-342900')
 etree.SubElement(props,A+'buFont',typeface='Arial')
 etree.SubElement(props,A+'buChar',char='•')
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
    .fill("Bullet acceptance");
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
  await page.getByRole("button", { name: /bullets\.pptx/ }).waitFor();
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
    (item) => item.name === "Bullet acceptance",
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
    const id = inventory.semantic_targets.find(
      (item) => item.name === "Agenda list",
    ).object_id;
    return inventory.targets.find((item) => item.object_id === id).text_style;
  };
  const initial = await style();
  assert.equal(initial.bullet_state, "bullet");
  assert.equal(initial.bullet_editable, true);
  assert.equal(initial.bullet_color_editable, true);
  checks.push(
    "A PowerPoint-style list with a text-font buFont is editable for bullets, color and size",
  );

  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Text", exact: true })
    .click();
  const targets = page.getByRole("combobox", {
    name: "Text on this slide",
    exact: true,
  });
  const option = targets.locator("option", { hasText: "Agenda list" });
  await option.waitFor({ state: "attached" });
  await targets.selectOption(await option.getAttribute("value"));
  const bulletStyle = page.getByRole("combobox", {
    name: "Bullet style",
    exact: true,
  });
  await bulletStyle.selectOption("numbered_roman_upper");
  await page
    .getByRole("button", { name: "Apply paragraph format", exact: true })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.equal((await style()).bullet_state, "numbered_roman_upper");
  assert.equal(await bulletStyle.inputValue(), "numbered_roman_upper");
  checks.push("GUI applies uppercase roman numbering as a native revision");

  const marker = page.getByRole("group", {
    name: "Bullet marker",
    exact: true,
  });
  const apply = marker.getByRole("button", {
    name: "Apply bullet marker",
    exact: true,
  });
  assert.equal(await apply.isDisabled(), true);
  await marker.getByLabel("Bullet color", { exact: true }).fill("#c00000");
  await marker
    .getByLabel("Bullet size (% of text, 25–400)", { exact: true })
    .fill("20");
  assert.equal(await apply.isDisabled(), true, "Out-of-range size is blocked");
  await marker
    .getByLabel("Bullet size (% of text, 25–400)", { exact: true })
    .fill("150");
  await apply.click();
  await workspace.getByText("Current · Revision 3", { exact: true }).waitFor();
  const decorated = await style();
  assert.deepEqual(
    [
      decorated.bullet_state,
      decorated.bullet_color,
      decorated.bullet_size_percent,
    ],
    ["numbered_roman_upper", "#C00000", 150],
  );
  assert.equal(
    await marker.getByLabel("Bullet color", { exact: true }).inputValue(),
    "#c00000",
  );
  assert.equal(await apply.isDisabled(), true, "No pending change after save");
  checks.push(
    "GUI applies bullet color and size as one reviewed native revision; numbering type is retained and controls read back",
  );
  await marker.scrollIntoViewIfNeeded();
  await marker.screenshot({
    path: path.join(output, "bullet-marker-controls.png"),
  });
  await page.screenshot({ path: path.join(output, "bullet-marker.png") });

  await workspace
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await workspace.getByText("Current · Revision 2", { exact: true }).waitFor();
  const undone = await style();
  assert.deepEqual(
    [undone.bullet_state, undone.bullet_color, undone.bullet_size_percent],
    ["numbered_roman_upper", null, null],
  );
  checks.push("Undo restores the previous marker without color or size");
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
