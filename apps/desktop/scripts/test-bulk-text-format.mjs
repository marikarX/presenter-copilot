/* global document, window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Windows/PowerPoint acceptance; only picker, ASR and model boundaries are fixtures.
const require = createRequire(import.meta.url);
const desktop = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const root = path.resolve(desktop, "../..");
const packagedExecutable = process.env.PRESENTER_COPILOT_PACKAGED_EXE;
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-native-ui-"));
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "bulk-text-format", "gui");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "presentation.pptx");
execFileSync(
  path.join(
    root,
    "core",
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  ),
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
presentation = Presentation()
slide = presentation.slides.add_slide(presentation.slide_layouts[6])
for index, text in enumerate(['First selected text', 'Second selected text']):
    shape = slide.shapes.add_textbox(Inches(0.7), Inches(1+index*1.5), Inches(7), Inches(1))
    shape.name = ['First text', 'Second text'][index]
    run = shape.text_frame.paragraphs[0].add_run()
    run.text = text
    run.font.size = Pt(20+index*2)
    run.font.name = 'Arial'
    run.font.bold = bool(index)
    run.font.italic = bool(index)
    run.font.color.rgb = RGBColor.from_string(['13579B','8642AB'][index])
shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.7), Inches(4.5), Inches(3), Inches(1))
shape.name = 'Unsupported rectangle'
presentation.save(sys.argv[1])
`,
    fixture,
  ],
  { cwd: root, windowsHide: true, stdio: "pipe" },
);

const env = { ...process.env };
for (const key of Object.keys(env)) {
  if (
    key.startsWith("PRESENTER_") ||
    key.startsWith("OPENAI_") ||
    key === "OPENROUTER_API_KEY" ||
    key === "ELECTRON_RUN_AS_NODE"
  )
    delete env[key];
}
Object.assign(env, {
  PRESENTER_COPILOT_DATA_ROOT: path.join(temporary, "core"),
});
if (!packagedExecutable)
  Object.assign(env, {
    PRESENTER_CORE_DIR: path.join(root, "core"),
    PRESENTER_COPILOT_DEV_MODE: "1",
    PRESENTER_COPILOT_TEST_PROVIDER: "deterministic_fake",
    PRESENTER_COPILOT_TEST_DECISION: "deterministic_fake",
    PRESENTER_COPILOT_TEST_ASR: "deterministic_fake",
  });
const errors = [];
const checks = [];
let app;
let page;
let nativeModulePath;
try {
  app = await electron.launch({
    executablePath: packagedExecutable
      ? path.resolve(packagedExecutable)
      : require("electron"),
    args: [
      ...(packagedExecutable ? [] : [desktop]),
      `--user-data-dir=${path.join(temporary, "browser")}`,
    ],
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
  nativeModulePath = packagedExecutable
    ? await app.evaluate(
        ({ app }) => `${app.getAppPath()}/dist/main/native-edit-appearance.js`,
      )
    : path.join(desktop, "dist", "main", "native-edit-appearance.js");
  page.setDefaultTimeout(30_000);
  page.on("pageerror", (error) => errors.push(error.message));
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill("Native appearance acceptance");
  await page.keyboard.press("Enter");
  await page
    .getByRole("heading", { name: "Sources", exact: true })
    .first()
    .waitFor();
  await app.evaluate(({ dialog }, fixture) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [fixture],
    });
  }, fixture);
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("presentation");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  await page.getByRole("button", { name: /presentation\.pptx/ }).waitFor();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page
    .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
    .waitFor();
  await app.evaluate((_electron, filename) => {
    const module = process.mainModule.require(filename);
    const original = module.renderNativeEditAppearance;
    globalThis.nativePlanPending = false;
    globalThis.nativePlanHold = false;
    globalThis.nativePlanReady = false;
    globalThis.nativePlanReceipts = [];
    module.renderNativeEditAppearance = async (...args) => {
      globalThis.nativePlanPending = true;
      globalThis.nativePlanReady = false;
      try {
        const result = await original(...args);
        globalThis.nativePlanReceipts.push({
          target: args[0],
          sha256: result.source_sha256,
          planId: result.plan_id,
        });
        globalThis.nativePlanReady = true;
        const deadline = Date.now() + 125_000;
        while (globalThis.nativePlanHold && Date.now() < deadline)
          await new Promise((resolve) => setTimeout(resolve, 100));
        if (globalThis.nativePlanHold)
          throw new Error("Owned native-plan reply gate expired");
        return result;
      } finally {
        globalThis.nativePlanPending = false;
      }
    };
  }, nativeModulePath);

  async function head() {
    return page.evaluate(async () => {
      const projects = await window.presenterCopilot.core.request(
        "project.list",
        {},
      );
      if (!projects.ok) throw new Error("Could not list owned projects");
      const project = projects.result.projects.find(
        (item) => item.name === "Native appearance acceptance",
      );
      const sources = await window.presenterCopilot.core.request(
        "source.list",
        { project_id: project.id },
      );
      if (!sources.ok) throw new Error("Could not list owned sources");
      const document = sources.result.sources.find(
        (item) => item.original_name === "presentation.pptx",
      );
      const scope = { project_id: project.id, document_id: document.id };
      const opened = await window.presenterCopilot.core.request(
        "presentation.workspace.open_source",
        scope,
      );
      if (!opened.ok) throw new Error("Could not inspect current head");
      await window.presenterCopilot.core.request(
        "presentation.workspace.close_source",
        { ...scope, session_id: opened.result.session_id },
      );
      return {
        revisionId: opened.result.revision_id,
        revisionNumber: opened.result.revision_number,
        sha256: opened.result.sha256,
      };
    });
  }
  async function waitMain(field, expected) {
    const deadline = Date.now() + 125_000;
    while (Date.now() < deadline) {
      if (
        (await app.evaluate((_electron, key) => globalThis[key], field)) ===
        expected
      )
        return;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error(`Owned native-plan ${field} did not reach ${expected}`);
  }
  async function nativeReady(dialog) {
    await dialog
      .getByRole("button", { name: "PowerPoint appearance", exact: true })
      .click();
    await dialog
      .getByText(
        "Proposed slide appearance from PowerPoint. Changes are not saved.",
        { exact: true },
      )
      .waitFor({ timeout: 125_000 });
    await page.waitForFunction(() => {
      return [
        ...document.querySelectorAll(
          'dialog[open] img:not([alt="Current native layout baseline"])',
        ),
      ].some((image) => image.complete && image.naturalWidth === 960);
    });
    await dialog
      .getByText("The proposed slide appearance comes from PowerPoint.", {
        exact: false,
      })
      .waitFor();
  }

  const baseline = await head();
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .check();
  const first = page.getByRole("button", {
    name: "Select First text on slide",
    exact: true,
  });
  const second = page.getByRole("button", {
    name: "Select Second text on slide",
    exact: true,
  });
  const rectangle = page.getByRole("button", {
    name: "Select Unsupported rectangle on slide",
    exact: true,
  });
  const bulk = page.getByRole("dialog", {
    name: "Format selected text on slide 1",
    exact: true,
  });
  const button = page.getByRole("button", {
    name: "Format selected text",
    exact: true,
  });
  const preview = bulk.getByRole("button", {
    name: "Preview selected text formatting",
    exact: true,
  });
  const save = bulk.getByRole("button", {
    name: "Save reviewed selected formatting",
    exact: true,
  });
  const ack = bulk.getByRole("checkbox", {
    name: "I reviewed every selected text object.",
    exact: true,
  });
  async function selectText() {
    await first.click();
    await second.click({ modifiers: ["Shift"] });
  }
  async function discard() {
    await bulk
      .getByRole("button", {
        name: "Discard selected formatting preview",
        exact: true,
      })
      .click();
    await bulk.waitFor({ state: "hidden" });
  }
  assert.equal(await button.isDisabled(), true);
  await first.click();
  assert.equal(await button.isDisabled(), true);
  await second.click({ modifiers: ["Shift"] });
  await button.click();
  await bulk
    .getByRole("checkbox", {
      name: "Apply font size to selection",
      exact: true,
    })
    .check();
  const size = bulk.getByLabel("Selected text font size", { exact: true });
  await size.fill("97");
  assert.equal(await preview.isDisabled(), true);
  await size.fill("30");
  await preview.click();
  await bulk
    .getByRole("img", {
      name: "Proposed selected text formatting",
      exact: true,
    })
    .waitFor();
  await ack.check();
  await nativeReady(bulk);
  assert.equal(await ack.isChecked(), false);
  await ack.check();
  await size.fill("31");
  assert.equal(await save.isDisabled(), true);
  await size.fill("30");
  assert.equal(await ack.isChecked(), false);
  await preview.click();
  await nativeReady(bulk);
  await ack.check();
  const receipt = await app.evaluate(() =>
    globalThis.nativePlanReceipts.at(-1),
  );
  assert.deepEqual(await head(), baseline);
  await page.screenshot({
    path: path.join(output, "native-selected-format.png"),
  });
  await save.click();
  await bulk.waitFor({ state: "hidden" });
  const savedHead = await head();
  assert.equal(savedHead.sha256, receipt.sha256);
  const styles = await page.evaluate(
    async ({ target, revision }) => {
      const result = await window.presenterCopilot.core.request(
        "presentation.workspace.list_text_targets",
        {
          project_id: target.project_id,
          document_id: target.document_id,
          revision_id: revision,
          slide_number: 1,
        },
      );
      if (!result.ok) throw new Error("Owned inventory unavailable");
      return result.result.targets
        .filter((t) =>
          ["First selected text", "Second selected text"].includes(
            t.current_text,
          ),
        )
        .map((t) => ({ text: t.current_text, style: t.text_style }));
    },
    { target: receipt.target, revision: savedHead.revisionId },
  );
  assert.equal(styles.length, 2);
  for (const [index, t] of styles.entries()) {
    assert.equal(t.style.font_size_pt, 30);
    assert.equal(t.style.font_color, ["#13579B", "#8642AB"][index]);
    assert.equal(t.style.bold, Boolean(index));
    assert.equal(t.style.italic, Boolean(index));
    assert.equal(
      t.text,
      ["First selected text", "Second selected text"][index],
    );
  }
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  assert.deepEqual(await head(), baseline);
  checks.push(
    "Multi-selected font size preserves differing color/bold/italic and text, invalid size is correctable, fresh native approval saves exact bytes and one Undo restores baseline",
  );
  await selectText();
  await button.click();
  for (const property of [
    "bold",
    "italic",
    "font size",
    "font color",
    "alignment",
  ])
    await bulk
      .getByRole("checkbox", {
        name: `Apply ${property} to selection`,
        exact: true,
      })
      .check();
  await bulk
    .getByLabel("Selected text bold", { exact: true })
    .selectOption("false");
  await bulk
    .getByLabel("Selected text italic", { exact: true })
    .selectOption("false");
  await size.fill("28");
  await bulk
    .getByLabel("Selected text font color", { exact: true })
    .fill("#2468ac");
  await bulk
    .getByLabel("Selected text alignment", { exact: true })
    .selectOption("center");
  await preview.click();
  await nativeReady(bulk);
  await ack.check();
  const combinedReceipt = await app.evaluate(() =>
    globalThis.nativePlanReceipts.at(-1),
  );
  await save.click();
  await bulk.waitFor({ state: "hidden" });
  const combinedHead = await head();
  assert.equal(combinedHead.sha256, combinedReceipt.sha256);
  const combinedStyles = await page.evaluate(
    async ({ target, revision }) => {
      const result = await window.presenterCopilot.core.request(
        "presentation.workspace.list_text_targets",
        {
          project_id: target.project_id,
          document_id: target.document_id,
          revision_id: revision,
          slide_number: 1,
        },
      );
      if (!result.ok) throw new Error("Owned combined inventory unavailable");
      return result.result.targets
        .filter((t) =>
          ["First selected text", "Second selected text"].includes(
            t.current_text,
          ),
        )
        .map((t) => t.text_style);
    },
    { target: combinedReceipt.target, revision: combinedHead.revisionId },
  );
  assert.equal(combinedStyles.length, 2);
  for (const style of combinedStyles) {
    assert.equal(style.bold, false);
    assert.equal(style.italic, false);
    assert.equal(style.font_size_pt, 28);
    assert.equal(style.font_color, "#2468AC");
    assert.equal(style.alignment, "center");
  }
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  assert.deepEqual(await head(), baseline);
  checks.push(
    "All five bulk properties save together on both objects with exact native bytes and one Undo",
  );
  await first.click();
  await rectangle.click({ modifiers: ["Shift"] });
  await button.click();
  await bulk
    .getByRole("checkbox", { name: "Apply bold to selection", exact: true })
    .check();
  await bulk
    .getByRole("status")
    .filter({ hasText: "Unsupported rectangle" })
    .waitFor();
  assert.equal(await preview.isDisabled(), true);
  assert.equal(await save.isDisabled(), true);
  await discard();
  assert.deepEqual(await head(), baseline);
  checks.push(
    "Unsupported mixed selection refuses entire formatting plan without skipping or modifying objects",
  );
  await app.evaluate(({ BrowserWindow }) => {
    const owned = BrowserWindow.getAllWindows().find((candidate) =>
      candidate.webContents.getURL().endsWith("/renderer/index.html"),
    );
    owned.setSize(720, 520);
  });
  await page.waitForFunction(() => window.innerWidth <= 720);
  await selectText();
  await button.click();
  assert.equal(
    await bulk.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
    true,
  );
  await page.screenshot({
    path: path.join(output, "minimum-window-format.png"),
  });
  await bulk
    .getByRole("checkbox", { name: "Apply bold to selection", exact: true })
    .check();
  await preview.click();
  await ack.check();
  await app.evaluate(() => {
    globalThis.nativePlanHold = true;
  });
  await bulk
    .getByRole("button", { name: "PowerPoint appearance", exact: true })
    .click();
  await waitMain("nativePlanReady", true);
  assert.equal(await save.isDisabled(), true);
  await discard();
  await app.evaluate(() => {
    globalThis.nativePlanHold = false;
  });
  await waitMain("nativePlanPending", false);
  assert.deepEqual(await head(), baseline);
  assert.equal(
    await page
      .getByText(
        "Proposed slide appearance from PowerPoint. Changes are not saved.",
        { exact: true },
      )
      .count(),
    0,
  );
  checks.push(
    "Discard during held real native bulk-format reply prevents stale pixels and mutation while Save is blocked",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, receipt, styles }, null, 2),
  );
  console.log(JSON.stringify({ checks, errors }));
} catch (error) {
  if (page)
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
  throw error;
} finally {
  if (app) await app.close();
}
