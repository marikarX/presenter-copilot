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
  path.join(root, ".local", "native-chart-fills", "gui");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "presentation.pptx");
const chartKind = process.env.PRESENTER_NATIVE_CHART_KIND || "column";
assert.ok(["column", "bar", "line", "pie"].includes(chartKind));
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
chart_types = {'column': XL_CHART_TYPE.COLUMN_CLUSTERED, 'bar': XL_CHART_TYPE.BAR_CLUSTERED, 'line': XL_CHART_TYPE.LINE, 'pie': XL_CHART_TYPE.PIE}
slide.shapes.add_chart(chart_types[sys.argv[2]], Inches(0.7), Inches(1.5), Inches(8.4), Inches(4.8), data)
presentation.save(sys.argv[1])
`,
    fixture,
    chartKind,
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
  const fills = page.getByRole("dialog", {
    name: "Chart fills on slide 1",
    exact: true,
  });
  async function openFills() {
    await page
      .getByRole("button", { name: "Chart fills & opacity", exact: true })
      .click();
    await fills
      .getByLabel("Fill series", { exact: true })
      .getByRole("option", { name: "Revenue", exact: true })
      .waitFor({ state: "attached" });
  }
  const preview = fills.getByRole("button", {
    name: "Preview chart fill",
    exact: true,
  });
  const save = fills.getByRole("button", {
    name: "Save reviewed chart fill",
    exact: true,
  });
  const ack = fills.getByRole("checkbox", {
    name: "I reviewed this fill and the chart legend.",
    exact: true,
  });
  await openFills();
  await fills
    .getByLabel("Chart fill style", { exact: true })
    .selectOption("linear_gradient");
  await fills.getByLabel("Gradient angle", { exact: true }).fill("45");
  await fills
    .getByRole("button", { name: "Add gradient stop", exact: true })
    .click();
  await fills
    .getByLabel("Gradient stop 2 position", { exact: true })
    .fill("100");
  assert.equal(await preview.isDisabled(), true);
  await fills
    .getByLabel("Gradient stop 2 position", { exact: true })
    .fill("50");
  await fills
    .getByLabel("Gradient stop 2 color", { exact: true })
    .fill("#8642AB");
  await fills.getByLabel("Gradient stop 2 opacity", { exact: true }).fill("65");
  await fills.getByLabel("Gradient stop 3 opacity", { exact: true }).fill("20");
  await preview.click();
  await fills
    .getByRole("img", { name: "Proposed chart fill", exact: true })
    .waitFor();
  await ack.check();
  await nativeReady(fills);
  assert.equal(await ack.isChecked(), false);
  await ack.check();
  await fills.getByLabel("Gradient angle", { exact: true }).fill("90");
  assert.equal(await save.isDisabled(), true);
  assert.equal(
    await fills
      .getByRole("button", { name: "PowerPoint appearance", exact: true })
      .count(),
    0,
  );
  await preview.click();
  await nativeReady(fills);
  await ack.check();
  const gradientReceipt = await app.evaluate(() =>
    globalThis.nativePlanReceipts.at(-1),
  );
  assert.deepEqual(await head(), baseline);
  await page.screenshot({ path: path.join(output, "native-gradient.png") });
  await save.click();
  await fills.waitFor({ state: "hidden" });
  assert.equal((await head()).sha256, gradientReceipt.sha256);
  const gradientHead = await head();
  await openFills();
  assert.equal(
    await fills.getByLabel("Chart fill style", { exact: true }).inputValue(),
    "linear_gradient",
  );
  assert.equal(
    await fills.getByLabel("Gradient angle", { exact: true }).inputValue(),
    "90",
  );
  assert.equal(
    await fills
      .getByLabel("Gradient stop 2 opacity", { exact: true })
      .inputValue(),
    "65",
  );
  await fills
    .getByLabel("Chart fill style", { exact: true })
    .selectOption("solid");
  await fills.getByLabel("Chart fill opacity", { exact: true }).fill("101");
  assert.equal(await preview.isDisabled(), true);
  await fills.getByLabel("Chart fill opacity", { exact: true }).fill("35");
  await fills.getByLabel("Chart fill RGB", { exact: true }).fill("#13579B");
  await preview.click();
  await nativeReady(fills);
  await ack.check();
  const solidReceipt = await app.evaluate(() =>
    globalThis.nativePlanReceipts.at(-1),
  );
  await page.screenshot({ path: path.join(output, "native-opacity.png") });
  await save.click();
  await fills.waitFor({ state: "hidden" });
  assert.equal((await head()).sha256, solidReceipt.sha256);
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page
    .getByText(`Current · Revision ${gradientHead.revisionNumber}`, {
      exact: true,
    })
    .waitFor();
  assert.deepEqual(await head(), gradientHead);
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  assert.deepEqual(await head(), baseline);
  await openFills();
  await fills.getByLabel("Chart fill opacity", { exact: true }).fill("50");
  await preview.click();
  await app.evaluate(() => {
    globalThis.nativePlanHold = true;
  });
  await fills
    .getByRole("button", { name: "PowerPoint appearance", exact: true })
    .click();
  await waitMain("nativePlanReady", true);
  assert.equal(await save.isDisabled(), true);
  await fills
    .getByRole("button", { name: "Discard chart fill preview", exact: true })
    .click();
  await fills.waitFor({ state: "hidden" });
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
    "Three-stop gradient/opacity native review rejects stop order, resets approval after angle change, saves exact bytes and reopens settings",
  );
  checks.push(
    "Solid opacity invalid value is correctable, native-reviewed exact Save and two undos restore gradient then baseline",
  );
  checks.push(
    "Discard during held native fill reply prevents stale display and leaves baseline exact",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, gradientReceipt, solidReceipt }, null, 2),
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
