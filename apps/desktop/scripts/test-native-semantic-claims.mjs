/* global window */
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
  path.join(root, ".local", "native-semantic-claims", "gui");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "presentation.pptx");
const route = "claims";
assert.ok(
  !packagedExecutable,
  "This fixture provider acceptance is source-only.",
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
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches
deck=Presentation();deck.slide_width=Inches(10);deck.slide_height=Inches(5.625)
slide=deck.slides.add_slide(deck.slide_layouts[6])
shape=slide.shapes.add_textbox(Inches(.4),Inches(.2),Inches(9),Inches(.8));shape.name='Native title';shape.text='Pilot decision'
data=CategoryChartData();data.categories=['Q1','Q2'];data.add_series('Revenue',[.2,.4])
shape=slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,Inches(.4),Inches(1.3),Inches(5),Inches(3),data);shape.name='Pilot chart'
chart=shape.chart;chart.has_title=True;chart.chart_title.text_frame.text='Pilot rates'
chart.value_axis.tick_labels.number_format='0%'
shape=slide.shapes.add_table(2,2,Inches(6),Inches(1.3),Inches(3),Inches(2));shape.name='Pilot table'
for r,row in enumerate([['Metric','Value'],['Pilot','20%']]):
 for c,value in enumerate(row):shape.table.cell(r,c).text=value
other=deck.slides.add_slide(deck.slide_layouts[6]);other.shapes.add_textbox(Inches(.4),Inches(.4),Inches(9),Inches(1)).text='Independent second slide.'
deck.save(sys.argv[1])
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
  const evidence = path.join(temporary, "Pilot evidence.txt");
  await writeFile(evidence, "Pilot Q1 raw rate is 0.2, with Q2 raw rate 0.4.");
  await app.evaluate(({ dialog }, selectedPath) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [selectedPath],
    });
  }, evidence);
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("supporting");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  await page.getByRole("button", { name: /Pilot evidence\.txt/ }).waitFor();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page
    .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
    .waitFor();
  async function context(slideNumber = 1) {
    return page.evaluate(async (number) => {
      const ask = async (method, params) => {
        const r = await window.presenterCopilot.core.request(method, params);
        if (!r.ok) throw new Error(r.error.message);
        return r.result;
      };
      const project = (await ask("project.list", {})).projects.find(
        (p) => p.name === "Native appearance acceptance",
      );
      const document = (
        await ask("source.list", { project_id: project.id })
      ).sources.find((d) => d.original_name === "presentation.pptx");
      const base = { project_id: project.id, document_id: document.id };
      const opened = await ask("presentation.workspace.open_source", base);
      await ask("presentation.workspace.close_source", {
        ...base,
        session_id: opened.session_id,
      });
      const inventory = await ask("presentation.workspace.list_text_targets", {
        ...base,
        revision_id: opened.revision_id,
        slide_number: number,
      });
      return {
        scope: {
          ...base,
          revision_id: opened.revision_id,
          slide_id: inventory.slide_id,
          slide_number: number,
        },
        inventory,
        sha256: opened.sha256,
      };
    }, slideNumber);
  }
  const ask = async (method, params) =>
    page.evaluate(
      async ({ method, params }) => {
        const r = await window.presenterCopilot.core.request(method, params);
        if (!r.ok) throw new Error(r.error.message);
        return r.result;
      },
      { method, params },
    );

  const baseline = await context();
  const chart = baseline.inventory.semantic_targets.find(
    (t) => t.source_kind === "native_chart_cache",
  );
  const table = baseline.inventory.semantic_targets.find(
    (t) => t.source_kind === "native_table_cells",
  );
  assert.ok(chart && table);
  assert.equal(baseline.inventory.targets.length, 1);
  assert.equal(baseline.inventory.semantic_targets.length, 3);
  assert.ok(
    chart.decision_text.includes("Q1: 0.2") &&
      !chart.decision_text.includes("20%"),
  );
  const studio = (name) =>
    page
      .getByRole("group", { name: "Slide studio panels", exact: true })
      .getByRole("button", { name, exact: true })
      .click();
  await studio("Purpose");
  const review = page.getByRole("region", {
    name: "Claim and evidence review",
    exact: true,
  });
  const discovery = review.getByRole("region", {
    name: "Find claim candidates",
    exact: true,
  });
  const save = review.getByRole("button", {
    name: "Save reviewed claim",
    exact: true,
  });
  const confirm = review.getByRole("checkbox", {
    name: "I reviewed the quote and evidence relations for this revision.",
    exact: true,
  });
  await discovery
    .getByRole("checkbox", {
      name: "Native title · Native slide text",
      exact: true,
    })
    .uncheck();
  await discovery
    .getByRole("checkbox", {
      name: "Pilot chart · Raw chart cache",
      exact: true,
    })
    .check();
  await discovery
    .getByRole("checkbox", {
      name: "Pilot table · Native table cells",
      exact: true,
    })
    .check();
  await page.screenshot({
    path: path.join(output, "graphic-source-selection.png"),
  });
  await discovery
    .getByRole("button", { name: "Find candidates", exact: true })
    .click();
  await discovery
    .getByRole("button", { name: "Review candidate 2", exact: true })
    .waitFor();
  assert.equal(
    (await ask("presentation.workspace.list_claims", baseline.scope)).items
      .length,
    0,
  );
  await discovery
    .getByRole("button", { name: "Review candidate 1", exact: true })
    .click();
  assert.equal(
    await review.getByLabel("Claim text object", { exact: true }).inputValue(),
    chart.object_id,
  );
  await review
    .getByLabel("Exact claim quote", { exact: true })
    .fill("Revenue: Q1: 0.2; Q2: 0.4");
  await review
    .getByText("Selected native representation", { exact: true })
    .click();
  await review.getByText(chart.decision_text, { exact: true }).waitFor();
  assert.equal(await save.isDisabled(), true);
  await confirm.check();
  await save.click();
  await review
    .getByText("1 claim · 0 supported · 0 need review", { exact: true })
    .waitFor();
  let claim = (await ask("presentation.workspace.list_claims", baseline.scope))
    .items[0];
  assert.equal(claim.source_kind, "native_chart_cache");
  assert.equal(claim.coverage, "unlinked");
  assert.equal((await context()).sha256, baseline.sha256);
  await page.screenshot({
    path: path.join(output, "raw-cache-claim-review.png"),
  });
  checks.push(
    "Actual native percentage chart supplies raw0.2 rather than displayed20%; chart/table selection and labeled extraction stay unsaved until exact quote review/Save, with native bytes unchanged",
  );
  await discovery
    .getByRole("button", { name: "Review candidate 2", exact: true })
    .click();
  assert.equal(
    await review.getByLabel("Claim text object", { exact: true }).inputValue(),
    table.object_id,
  );
  await review
    .getByLabel("Exact claim quote", { exact: true })
    .fill("Pilot\t20%");
  await confirm.check();
  await save.click();
  await review
    .getByText("2 claims · 0 supported · 0 need review", { exact: true })
    .waitFor();
  const chartCard = review
    .locator("article")
    .filter({ hasText: "Revenue: Q1: 0.2; Q2: 0.4" })
    .filter({
      has: page.getByRole("button", { name: "Review claim", exact: true }),
    });
  await chartCard
    .getByRole("button", { name: "Review claim", exact: true })
    .click();
  await review
    .getByLabel("Find project evidence", { exact: true })
    .fill("pilot");
  await review
    .getByRole("button", { name: "Search evidence", exact: true })
    .click();
  await review
    .getByRole("button", {
      name: "Link excerpt from Pilot evidence.txt",
      exact: true,
    })
    .click();
  await review
    .getByLabel("Evidence relation for Pilot evidence.txt", { exact: true })
    .selectOption("supports");
  await review
    .getByRole("button", {
      name: "Suggest relation for Pilot evidence.txt",
      exact: true,
    })
    .click();
  await review.getByText(/^(Suggested relation:|Abstained:)/).waitFor();
  assert.equal(await save.isDisabled(), true);
  await confirm.check();
  await save.click();
  await review
    .getByText("2 claims · 1 supported · 0 need review", { exact: true })
    .waitFor();
  claim = (
    await ask("presentation.workspace.list_claims", baseline.scope)
  ).items.find((c) => c.source_kind === "native_chart_cache");
  assert.equal(claim.coverage, "supported");
  assert.equal(claim.evidence[0].relation, "supports");
  checks.push(
    "Native table exact row quotes save with table provenance; chart evidence search/link/typed relation suggestion require independent explicit relation review and Save",
  );
  await studio("Deck review");
  const scan = page.getByRole("region", {
    name: "Deck claim discovery",
    exact: true,
  });
  await scan
    .getByRole("button", { name: "Prepare deck claim scan", exact: true })
    .click();
  await scan
    .getByRole("checkbox", { name: "Inspect slide 1", exact: true })
    .waitFor();
  await scan
    .getByText("3 available native representations", { exact: false })
    .waitFor();
  await scan
    .getByRole("checkbox", {
      name: "Send native text, table cells and raw chart cache data from these slides to my configured reasoning provider.",
      exact: true,
    })
    .check();
  await scan
    .getByRole("button", { name: "Start deck claim scan", exact: true })
    .click();
  await scan.getByText(/^Finished /).waitFor();
  await page.screenshot({ path: path.join(output, "graphic-deck-scan.png") });
  const beforeRefresh = (await context()).sha256;
  await scan
    .getByRole("button", { name: "Refresh changed text", exact: true })
    .click();
  await scan.getByText(/^Refreshed native text\./).waitFor();
  assert.equal((await context()).sha256, beforeRefresh);
  checks.push(
    "Actual deck preflight counts native text/chart/table representations, discloses raw data before acknowledgment, runs labeled unsaved suggestions and refreshes exact input without native edits",
  );
  const layoutToggle = page.getByText("Slide actions & layout", {
    exact: true,
  });
  if (!(await layoutToggle.evaluate((element) => element.parentElement.open)))
    await layoutToggle.click();
  async function nativeReady(dialog) {
    await dialog
      .getByRole("button", { name: "PowerPoint appearance", exact: true })
      .click();
    await dialog
      .getByText(
        "Proposed slide appearance from PowerPoint. Changes are not saved.",
        { exact: true },
      )
      .waitFor({ timeout: 125000 });
  }
  await page.getByRole("button", { name: "Chart colors", exact: true }).click();
  const colorDialog = page.getByRole("dialog", {
    name: "Chart colors on slide 1",
    exact: true,
  });
  await colorDialog
    .getByLabel("Color chart", { exact: true })
    .selectOption(chart.object_id);
  await colorDialog
    .getByLabel("Chart RGB color", { exact: true })
    .fill("#13579B");
  await colorDialog
    .getByRole("button", { name: "Preview chart color", exact: true })
    .click();
  await colorDialog
    .getByRole("img", { name: "Proposed chart color", exact: true })
    .waitFor();
  await nativeReady(colorDialog);
  await colorDialog
    .getByRole("checkbox", {
      name: "I reviewed this color and the chart legend.",
      exact: true,
    })
    .check();
  await page.screenshot({
    path: path.join(output, "native-chart-color-preview.png"),
  });
  await colorDialog
    .getByRole("button", { name: "Save reviewed chart color", exact: true })
    .click();
  await colorDialog.waitFor({ state: "hidden" });
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  const formatted = await context();
  assert.notEqual(formatted.sha256, baseline.sha256);
  claim = (
    await ask("presentation.workspace.list_claims", formatted.scope)
  ).items.find((item) => item.source_kind === "native_chart_cache");
  assert.equal(claim.span_status, "unchanged");
  assert.equal(claim.coverage, "needs_review");
  await studio("Purpose");
  await review
    .locator("article")
    .filter({ hasText: "Revenue: Q1: 0.2; Q2: 0.4" })
    .filter({
      has: page.getByRole("button", { name: "Review claim", exact: true }),
    })
    .getByRole("button", { name: "Review claim", exact: true })
    .click();
  assert.equal(await save.isDisabled(), true);
  await confirm.check();
  await save.click();
  claim = (
    await ask("presentation.workspace.list_claims", formatted.scope)
  ).items.find((item) => item.source_kind === "native_chart_cache");
  assert.equal(claim.coverage, "supported");
  await studio("Deck review");
  await scan
    .getByRole("button", { name: "Refresh changed text", exact: true })
    .click();
  await scan
    .getByText(/^Refreshed native text\. 2 unchanged text windows reused/)
    .waitFor();
  checks.push(
    "Actual GUI chart-color preview from PowerPoint and reviewed native Save create a revision with unchanged raw span but needs-review claim; separate reapproval restores support and both exact scan windows reuse without inference",
  );
  await page
    .getByRole("button", { name: "Native charts", exact: true })
    .click();
  const chartDialog = page.getByRole("dialog", {
    name: "Native charts on slide 1",
    exact: true,
  });
  await chartDialog
    .getByLabel("Native chart action", { exact: true })
    .selectOption(chart.object_id);
  await chartDialog
    .getByLabel("Category 1, series 1 value", { exact: true })
    .fill("0.3");
  await chartDialog
    .getByRole("button", { name: "Preview native chart", exact: true })
    .click();
  await chartDialog
    .getByRole("img", { name: "Proposed native chart", exact: true })
    .waitFor();
  await nativeReady(chartDialog);
  await chartDialog
    .getByRole("checkbox", {
      name: "I reviewed this chart’s data, labels and placement.",
      exact: true,
    })
    .check();
  await page.screenshot({
    path: path.join(output, "native-chart-data-preview.png"),
  });
  await chartDialog
    .getByRole("button", { name: "Save reviewed native chart", exact: true })
    .click();
  await chartDialog.waitFor({ state: "hidden" });
  await page.getByText("Current · Revision 3", { exact: true }).waitFor();
  const changed = await context();
  claim = (
    await ask("presentation.workspace.list_claims", changed.scope)
  ).items.find((item) => item.source_kind === "native_chart_cache");
  assert.equal(claim.span_status, "changed");
  assert.equal(claim.coverage, "needs_review");
  await studio("Purpose");
  await review
    .locator("article")
    .filter({ hasText: "Revenue: Q1: 0.2; Q2: 0.4" })
    .filter({
      has: page.getByRole("button", { name: "Review claim", exact: true }),
    })
    .getByRole("button", { name: "Review claim", exact: true })
    .click();
  await review
    .getByLabel("Exact claim quote", { exact: true })
    .fill("Revenue: Q1: 0.3; Q2: 0.4");
  await review
    .getByLabel("Evidence relation for Pilot evidence.txt", { exact: true })
    .selectOption("context");
  await confirm.check();
  await save.click();
  claim = (
    await ask("presentation.workspace.list_claims", changed.scope)
  ).items.find((item) => item.source_kind === "native_chart_cache");
  assert.equal(claim.span_status, "unchanged");
  assert.equal(claim.coverage, "unlinked");
  assert.equal(claim.evidence[0].relation, "context");
  await studio("Deck review");
  await scan
    .getByRole("button", { name: "Refresh changed text", exact: true })
    .click();
  await scan
    .getByText(/^Refreshed native text\. 1 unchanged text windows reused/)
    .waitFor();
  checks.push(
    "Actual GUI chart-data PowerPoint preview/Save changes raw span and requires a new exact quote plus evidence judgment; changed chart scan window is excluded from reuse while unchanged second slide reuses",
  );
  await studio("Purpose");
  await app.evaluate(
    (_electron, modulePath) => {
      const { CoreProcessClient } = process.mainModule.require(modulePath);
      const original = CoreProcessClient.prototype.request;
      globalThis.claimHold = true;
      globalThis.claimReady = false;
      globalThis.claimPending = false;
      CoreProcessClient.prototype.request = async function (method, ...args) {
        const result = await original.call(this, method, ...args);
        if (method === "presentation.workspace.extract_claims") {
          globalThis.claimReady = true;
          globalThis.claimPending = true;
          const deadline = Date.now() + 30000;
          while (globalThis.claimHold && Date.now() < deadline)
            await new Promise((r) => setTimeout(r, 50));
          globalThis.claimPending = false;
          if (globalThis.claimHold) throw new Error("Owned claim gate expired");
        }
        return result;
      };
    },
    path.join(path.dirname(nativeModulePath), "core-client.js"),
  );
  await discovery
    .getByRole("checkbox", {
      name: "Pilot chart · Raw chart cache",
      exact: true,
    })
    .check();
  await discovery
    .getByRole("button", { name: "Find candidates", exact: true })
    .click();
  const extractionDeadline = Date.now() + 30000;
  while (
    !(await app.evaluate(() => globalThis.claimReady)) &&
    Date.now() < extractionDeadline
  )
    await new Promise((r) => setTimeout(r, 100));
  assert.equal(await app.evaluate(() => globalThis.claimReady), true);
  await page.getByRole("button", { name: "Next slide", exact: true }).click();
  await page
    .getByRole("img", { name: "Imported presentation, slide 2", exact: true })
    .waitFor();
  await app.evaluate(() => {
    globalThis.claimHold = false;
  });
  const ended = Date.now() + 30000;
  while (
    (await app.evaluate(() => globalThis.claimPending)) &&
    Date.now() < ended
  )
    await new Promise((r) => setTimeout(r, 100));
  assert.equal(
    await discovery
      .getByRole("button", { name: "Review candidate 1", exact: true })
      .count(),
    0,
  );
  assert.equal(
    (await ask("presentation.workspace.list_claims", (await context(2)).scope))
      .items.length,
    0,
  );
  checks.push(
    "Held actual graphic extraction reply after slide navigation is discarded; source kind does not bypass revision/slide ownership",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, baseline }, null, 2),
  );
  console.log(JSON.stringify({ checks, errors }));
} catch (error) {
  if (page)
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
  throw error;
} finally {
  if (app) {
    await app
      .evaluate(() => {
        globalThis.claimHold = false;
      })
      .catch(() => {});
    await app.close();
  }
}
