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
  path.join(root, ".local", "native-table-review", "gui");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "presentation.pptx");
const route = process.env.PRESENTER_NATIVE_TABLE_REVIEW || "data";
assert.ok(
  [
    "create",
    "data",
    "structure",
    "formatting",
    "borders",
    "fit",
    "merge",
    "split",
  ].includes(route),
);
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
presentation = Presentation()
slide = presentation.slides.add_slide(presentation.slide_layouts[6])
shape = slide.shapes.add_table(3, 3, Inches(0.6), Inches(1.1), Inches(8.4), Inches(3.5))
shape.name = 'Owned review table'
table = shape.table
values = [['Metric', 'Current', 'Target'], ['Revenue', '12.25', '15'], ['Capacity', '', '']]
for r, row in enumerate(values):
    for c, text in enumerate(row):
        cell = table.cell(r,c)
        cell.text = text
        for paragraph in cell.text_frame.paragraphs:
            paragraph.font.name = 'Arial'
            paragraph.font.size = Pt(18)
            for run in paragraph.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(18)
if sys.argv[2] == 'split':
    table.cell(2,0).merge(table.cell(2,1))
presentation.save(sys.argv[1])
`,
    fixture,
    route,
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
  async function catalog() {
    const current = await head();
    return page.evaluate(async (revisionId) => {
      const projects = await window.presenterCopilot.core.request(
        "project.list",
        {},
      );
      const project = projects.result.projects.find(
        (item) => item.name === "Native appearance acceptance",
      );
      const sources = await window.presenterCopilot.core.request(
        "source.list",
        { project_id: project.id },
      );
      const document = sources.result.sources.find(
        (item) => item.original_name === "presentation.pptx",
      );
      const result = await window.presenterCopilot.core.request(
        "presentation.workspace.list_tables",
        {
          project_id: project.id,
          document_id: document.id,
          revision_id: revisionId,
          slide_number: 1,
        },
      );
      if (!result.ok) throw new Error("Owned table catalog unavailable");
      return result.result;
    }, current.revisionId);
  }
  const before = await catalog();
  const config =
    route === "formatting"
      ? [
          "Table formatting",
          "Formatting table",
          "table formatting",
          "I reviewed these cell styles and text fit.",
        ]
      : route === "borders"
        ? [
            "Table borders",
            "Borders table",
            "table borders",
            "I reviewed the selected range and shared border edges.",
          ]
        : route === "fit"
          ? [
              "Auto-fit table rows",
              "Fit table",
              "table fit",
              "I reviewed the fitted rows, text fit and nearby content.",
            ]
          : ["merge", "split"].includes(route)
            ? [
                "Merge or split table cells",
                "Merge table",
                "table merge",
                "I reviewed the merged cells, text distribution and layout.",
              ]
            : [
                "Native tables",
                "Native table",
                "native table",
                "I reviewed this table\u2019s cells, placement and text fit.",
              ];
  const [title, picker, noun, approval] = config;
  const toggle = page.getByText("Slide actions & layout", { exact: true });
  if (!(await toggle.evaluate((el) => el.parentElement.open)))
    await toggle.click();
  const dialog = page.getByRole("dialog", {
    name: `${title} on slide 1`,
    exact: true,
  });
  const preview = dialog.getByRole("button", {
    name: `Preview ${noun}`,
    exact: true,
  });
  const save = dialog.getByRole("button", {
    name: `Save reviewed ${noun}`,
    exact: true,
  });
  const ack = dialog.getByRole("checkbox", { name: approval, exact: true });
  async function openReview(existingId = before.items[0].object_id) {
    await page.getByRole("button", { name: title, exact: true }).click();
    await dialog
      .getByLabel(picker, { exact: true })
      .locator('option[value]:not([value=""])')
      .first()
      .waitFor({ state: "attached" });
    if (["data", "structure"].includes(route))
      await dialog.getByLabel(picker, { exact: true }).selectOption(existingId);
  }
  async function setDraft(changed) {
    if (route === "create")
      await dialog
        .getByLabel("Row 1, column 1", { exact: true })
        .fill(changed ? "New revised metrics" : "New metrics");
    else if (route === "data")
      await dialog
        .getByLabel("Row 2, column 2", { exact: true })
        .fill(changed ? "25" : "22.5");
    else if (route === "structure") {
      if (
        !(await dialog.getByLabel("Row 4, column 1", { exact: true }).count())
      )
        await dialog
          .getByRole("button", { name: "Insert row after", exact: true })
          .click();
      await dialog
        .getByLabel("Row 2, column 1", { exact: true })
        .fill(changed ? "Expansion revised" : "Expansion");
    } else if (route === "formatting") {
      await dialog
        .getByLabel("Table bold", { exact: true })
        .selectOption("true");
      await dialog.getByLabel("Apply table font size", { exact: true }).check();
      await dialog
        .getByLabel("Table font size", { exact: true })
        .fill(changed ? "22" : "18");
      await dialog
        .getByLabel("Apply table fill color", { exact: true })
        .check();
      await dialog
        .getByLabel("Table fill RGB", { exact: true })
        .fill("#13579B");
    } else if (route === "borders") {
      await dialog
        .getByLabel("Border width", { exact: true })
        .fill(changed ? "3" : "2");
      await dialog.getByLabel("Border RGB", { exact: true }).fill("#13579B");
    } else if (route === "fit")
      await dialog
        .getByLabel("Table fit strategy", { exact: true })
        .selectOption(changed ? "grow" : "compact");
    else {
      await dialog.getByLabel("Merge first row", { exact: true }).fill("3");
      await dialog.getByLabel("Merge last row", { exact: true }).fill("3");
      await dialog.getByLabel("Merge first column", { exact: true }).fill("1");
      await dialog
        .getByLabel("Merge last column", { exact: true })
        .fill(route === "merge" && changed ? "3" : "2");
      await dialog
        .getByLabel("Merge action", { exact: true })
        .selectOption(
          route === "split" ? (changed ? "merge" : "split") : "merge",
        );
    }
  }
  await openReview();
  await setDraft(false);
  await preview.click();
  await dialog
    .getByRole("img", { name: `Proposed ${noun}`, exact: true })
    .waitFor();
  await ack.check();
  await nativeReady(dialog);
  assert.equal(await ack.isChecked(), false);
  await ack.check();
  await dialog
    .getByRole("button", { name: "Browser appearance", exact: true })
    .click();
  await page.waitForFunction(
    (checkbox) => !checkbox.checked,
    await ack.elementHandle(),
  );
  assert.equal(await ack.isChecked(), false);
  await nativeReady(dialog);
  await ack.check();
  await setDraft(true);
  assert.equal(await save.isDisabled(), true);
  await setDraft(false);
  assert.equal(await ack.isChecked(), false);
  await preview.click();
  await nativeReady(dialog);
  await ack.check();
  const receipt = await app.evaluate(() =>
    globalThis.nativePlanReceipts.at(-1),
  );
  assert.deepEqual(await head(), baseline);
  await page.screenshot({ path: path.join(output, "native-review.png") });
  await save.click();
  await dialog.waitFor({ state: "hidden" });
  assert.equal((await head()).sha256, receipt.sha256);
  const after = await catalog();
  const target = after.items[0];
  if (route === "create")
    assert.equal(
      after.items.filter((item) => item.cells[0][0] === "New metrics").length,
      1,
    );
  else if (route === "data") assert.equal(target.cells[1][1], "22.5");
  else if (route === "structure") {
    assert.equal(target.cells.length, 4);
    assert.equal(target.cells[1][0], "Expansion");
    assert.deepEqual(target.cells[2], before.items[0].cells[1]);
  } else if (route === "formatting") {
    assert.equal(target.formatting.cell_styles[0][0].bold, true);
    assert.equal(target.formatting.cell_styles[0][0].fill_color, "#13579B");
  } else if (route === "borders") {
    assert.equal(target.borders.cell_borders[0][0].top.width_pt, 2);
    assert.equal(target.borders.cell_borders[0][0].top.color, "#13579B");
  } else if (route === "fit") {
    assert.ok(target.fit.height_pt < before.items[0].fit.height_pt);
    assert.deepEqual(target.cells, before.items[0].cells);
  } else if (route === "merge")
    assert.deepEqual(target.spans.regions, [
      { row: 2, column: 0, row_span: 1, column_span: 2 },
    ]);
  else assert.deepEqual(target.spans.regions, []);
  await openReview();
  await dialog
    .getByRole("button", { name: `Discard ${noun} preview`, exact: true })
    .click();
  await dialog.waitFor({ state: "hidden" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  assert.deepEqual(await head(), baseline);
  await app.evaluate(({ BrowserWindow }) => {
    const owned = BrowserWindow.getAllWindows().find((candidate) =>
      candidate.webContents.getURL().endsWith("/renderer/index.html"),
    );
    owned.setSize(720, 520);
  });
  await page.waitForFunction(() => window.innerWidth <= 720);
  await openReview();
  assert.equal(
    await dialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
    true,
  );
  await page.screenshot({ path: path.join(output, "minimum-window.png") });
  await setDraft(false);
  await preview.click();
  await app.evaluate(() => {
    globalThis.nativePlanHold = true;
  });
  await dialog
    .getByRole("button", { name: "PowerPoint appearance", exact: true })
    .click();
  await waitMain("nativePlanReady", true);
  assert.equal(await save.isDisabled(), true);
  assert.equal(await ack.isDisabled(), true);
  await dialog
    .getByRole("button", { name: `Discard ${noun} preview`, exact: true })
    .click();
  await dialog.waitFor({ state: "hidden" });
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
    `Native ${route} review resets appearance/draft approval, saves exact reviewed bytes, reopens authoritative settings and Undo restores baseline`,
  );
  checks.push(
    `Minimum-window ${route} blocks Save/approval while pending and contains held native reply after Discard without mutation`,
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, receipt, before, after }, null, 2),
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
