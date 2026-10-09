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
  path.join(root, ".local", "native-chart-review", "gui");
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
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches
presentation = Presentation()
slide = presentation.slides.add_slide(presentation.slide_layouts[5])
slide.shapes.title.text = 'Synthetic quarterly revenue'
data = CategoryChartData()
data.categories = ['Baseline', 'Pilot', 'Target']
data.add_series('Revenue', [10, 12.25, 15])
slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.7), Inches(1.5), Inches(8.4), Inches(4.8), data)
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
  const toggle = page.getByText("Slide actions & layout", { exact: true });
  if (!(await toggle.evaluate((el) => el.parentElement.open)))
    await toggle.click();
  const chart = page.getByRole("dialog", {
    name: "Native charts on slide 1",
    exact: true,
  });
  const action = chart.getByLabel("Native chart action", { exact: true });
  const preview = chart.getByRole("button", {
    name: "Preview native chart",
    exact: true,
  });
  const save = chart.getByRole("button", {
    name: "Save reviewed native chart",
    exact: true,
  });
  const ack = chart.getByRole("checkbox", {
    name: "I reviewed this chart’s data, labels and placement.",
    exact: true,
  });
  async function openChart(existing = false) {
    await page
      .getByRole("button", { name: "Native charts", exact: true })
      .click();
    await action.getByRole("option").nth(1).waitFor({ state: "attached" });
    if (existing)
      await action.selectOption(
        await action.getByRole("option").nth(1).getAttribute("value"),
      );
  }
  async function undo(expected) {
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await page
      .getByText(`Current \u00b7 Revision ${expected.revisionNumber}`, {
        exact: true,
      })
      .waitFor();
    assert.deepEqual(await head(), expected);
  }
  async function receipt() {
    return app.evaluate(() => globalThis.nativePlanReceipts.at(-1));
  }
  await openChart(true);
  const value = chart.getByLabel("Category 2, series 1 value", { exact: true });
  await value.fill("22.5");
  await preview.click();
  await chart
    .getByRole("img", { name: "Proposed native chart", exact: true })
    .waitFor();
  await ack.check();
  await nativeReady(chart);
  assert.equal(await ack.isChecked(), false);
  assert.equal(await save.isDisabled(), true);
  await ack.check();
  await value.fill("23.5");
  assert.equal(await save.isDisabled(), true);
  await value.fill("22.5");
  assert.equal(await ack.isChecked(), false);
  assert.equal(await save.isDisabled(), true);
  await nativeReady(chart);
  await ack.check();
  const editReceipt = await receipt();
  assert.deepEqual(await head(), baseline);
  await page.screenshot({ path: path.join(output, "native-chart-data.png") });
  await save.click();
  await chart.waitFor({ state: "hidden" });
  const edited = await head();
  assert.equal(edited.sha256, editReceipt.sha256);
  await openChart(true);
  assert.equal(
    await chart
      .getByLabel("Category 2, series 1 value", { exact: true })
      .inputValue(),
    "22.5",
  );
  await chart
    .getByRole("button", { name: "Insert category after", exact: true })
    .click();
  await chart.getByLabel("Category 2", { exact: true }).fill("Expansion");
  await chart
    .getByLabel("Category 2, series 1 value", { exact: true })
    .fill("18");
  await preview.click();
  await nativeReady(chart);
  await ack.check();
  const structureReceipt = await receipt();
  await page.screenshot({
    path: path.join(output, "native-chart-structure.png"),
  });
  await save.click();
  await chart.waitFor({ state: "hidden" });
  assert.equal((await head()).sha256, structureReceipt.sha256);
  await openChart(true);
  assert.equal(
    await chart.getByLabel("Category 2", { exact: true }).inputValue(),
    "Expansion",
  );
  assert.equal(
    await chart
      .getByLabel("Chart category count", { exact: true })
      .inputValue(),
    "4",
  );
  await chart
    .getByRole("button", { name: "Discard native chart preview", exact: true })
    .click();
  await chart.waitFor({ state: "hidden" });
  await undo(edited);
  await undo(baseline);
  checks.push(
    "Existing data and structural edits use fresh native approval, save both reviewed hashes, reopen exact settings and undo both revisions",
  );

  await openChart();
  await chart
    .getByLabel("Chart title", { exact: true })
    .fill("Native created bar");
  await chart.getByLabel("Chart type", { exact: true }).selectOption("bar");
  await preview.click();
  await nativeReady(chart);
  await ack.check();
  await chart
    .getByRole("button", { name: "Browser appearance", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      !document.querySelector("dialog[open] .pw-edit-review-ack input")
        ?.checked,
  );
  assert.equal(await ack.isChecked(), false);
  assert.equal(await save.isDisabled(), true);
  await nativeReady(chart);
  await ack.check();
  const createReceipt = await receipt();
  await page.screenshot({
    path: path.join(output, "native-chart-created.png"),
  });
  await save.click();
  await chart.waitFor({ state: "hidden" });
  assert.equal((await head()).sha256, createReceipt.sha256);
  await undo(baseline);
  checks.push(
    "Chart creation renders real PowerPoint pixels, switching appearance clears approval, exact Save and Undo pass",
  );

  await openChart();
  await chart
    .getByLabel("Chart title", { exact: true })
    .fill("Discard owned draft");
  await preview.click();
  await ack.check();
  await app.evaluate(() => {
    globalThis.nativePlanHold = true;
  });
  await chart
    .getByRole("button", { name: "PowerPoint appearance", exact: true })
    .click();
  await waitMain("nativePlanReady", true);
  assert.equal(await save.isDisabled(), true);
  assert.equal(await ack.isChecked(), false);
  await chart
    .getByRole("button", { name: "Discard native chart preview", exact: true })
    .click();
  await chart.waitFor({ state: "hidden" });
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
    "Discard during held real native chart reply prevents stale pixels and head mutation while pending Save is blocked",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      { checks, errors, editReceipt, structureReceipt, createReceipt },
      null,
      2,
    ),
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
