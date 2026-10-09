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
  path.join(root, ".local", "rehearsal-coverage", "gui");
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
from pptx.util import Inches,Pt
presentation=Presentation();presentation.slide_width=Inches(10);presentation.slide_height=Inches(5.625)
slide=presentation.slides.add_slide(presentation.slide_layouts[6])
slide.notes_slide.notes_text_frame.text='Initial private speaking reminder.'
for name,text,y in [('Basic metric','Revenue rose 20% during the pilot.',0.5),('Readonly metrics','Return on investment reached 24%.\n'+' '.join(f'Unique supporting observation {i}.' for i in range(210)),1.2)]:
 shape=slide.shapes.add_textbox(Inches(.5),Inches(y),Inches(9),Inches(3));shape.name=name;shape.text=text
 for p in shape.text_frame.paragraphs:p.font.size=Pt(8)
other=presentation.slides.add_slide(presentation.slide_layouts[6]);other.shapes.add_textbox(Inches(.5),Inches(.5),Inches(9),Inches(2)).text='Other slide statement.'
for number in range(3,27):
 other=presentation.slides.add_slide(presentation.slide_layouts[6]);other.shapes.add_textbox(Inches(.5),Inches(.5),Inches(9),Inches(2)).text=f'Metric increased by {number}% on slide {number}.'
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
  const studio = async (name) =>
    page
      .getByRole("group", { name: "Slide studio panels", exact: true })
      .getByRole("button", { name, exact: true })
      .click();
  const scope = {
    project_id: baseline.scope.project_id,
    document_id: baseline.scope.document_id,
    expected_revision_id: baseline.scope.revision_id,
  };
  await page.getByRole("button", { name: "Rehearse", exact: true }).click();
  await page
    .getByLabel("Presentation tracking", { exact: true })
    .selectOption("manual");
  await page.getByRole("button", { name: "Start Run", exact: true }).click();
  await page.getByRole("button", { name: "Next slide", exact: true }).click();
  await page.getByRole("button", { name: "Stop Run", exact: true }).click();
  await page
    .getByRole("heading", { name: "Run debrief", exact: true })
    .waitFor();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  await studio("Rehearsal");
  const coverage = page.getByRole("region", {
    name: "Rehearsal coverage",
    exact: true,
  });
  const inspect = () =>
    coverage.getByRole("button", {
      name: "Inspect rehearsal coverage",
      exact: true,
    });
  await inspect().waitFor();
  assert.equal(await coverage.locator("article").count(), 0);
  await inspect().click();
  await coverage
    .getByText("26 matching slides · page 1 of 2.", { exact: true })
    .waitFor();
  assert.equal(await coverage.locator("article").count(), 20);
  await coverage
    .getByText(
      /Rehearsed revision 1: 0 of 26 slides have recorded speech; 26 have none/,
    )
    .waitFor();
  const firstCard = coverage.locator("article").first();
  const firstIdentity = await firstCard.getAttribute("data-slide-id");
  assert.equal(firstIdentity, baseline.scope.slide_id);
  const nativeText = await firstCard.getByText(/^Native text:/).innerText();
  assert.equal((await context()).sha256, baseline.sha256);
  const claims = await ask(
    "presentation.workspace.list_claims",
    baseline.scope,
  );
  assert.equal(claims.items.length, 0);
  checks.push(
    "Actual GUI Run/debrief on 26 slides opens local source-revision native density and recorded coverage; no captured speech remains an observation, with native bytes and claims unchanged",
  );
  await coverage
    .getByRole("button", { name: "Next coverage slides", exact: true })
    .click();
  await coverage
    .getByText("26 matching slides · page 2 of 2.", { exact: true })
    .waitFor();
  assert.equal(await coverage.locator("article").count(), 6);
  await coverage
    .getByRole("combobox", { name: "Coverage filter", exact: true })
    .selectOption("no_visit");
  assert.equal(await coverage.locator("article").count(), 0);
  await inspect().click();
  await coverage
    .getByText("24 matching slides · page 1 of 2.", { exact: true })
    .waitFor();
  assert.equal(
    await coverage
      .getByRole("heading", { name: "Slide 1", exact: true })
      .count(),
    0,
  );
  assert.equal(
    await coverage
      .getByRole("heading", { name: "Slide 2", exact: true })
      .count(),
    0,
  );
  await coverage
    .getByRole("combobox", { name: "Coverage filter", exact: true })
    .selectOption("all");
  await inspect().click();
  await firstCard
    .getByRole("button", { name: "Open current slide 1", exact: true })
    .click();
  await page.getByText("Slide 1 of 26", { exact: true }).waitFor();
  await page.screenshot({
    path: path.join(output, "density-and-coverage.png"),
  });
  checks.push(
    "Coverage pagination shows 20 then 6 rows; explicit no-visit filter excludes the two actually visited slides, clears old results, and exact stable-slide navigation works",
  );

  const actions = page.locator("details.pw-slide-actions");
  if (!(await actions.evaluate((node) => node.open)))
    await actions.locator("summary").click();
  await page
    .getByRole("button", { name: "Move current slide later", exact: true })
    .click();
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.equal(await coverage.locator("article").count(), 0);
  await inspect().click();
  await coverage
    .getByText("26 matching slides · page 1 of 2.", { exact: true })
    .waitFor();
  const moved = coverage.locator(`article[data-slide-id="${firstIdentity}"]`);
  assert.equal(await moved.getByText(/^Native text:/).innerText(), nativeText);
  await moved
    .getByRole("button", { name: "Open current slide 2", exact: true })
    .click();
  await page.getByText("Slide 2 of 26", { exact: true }).waitFor();
  checks.push(
    "Actual native slide reorder clears prior results and maps frozen rehearsal slide 1 to current slide 2 without changing its native density or source provenance",
  );

  await studio("Text");
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .selectOption({ index: 0 });
  await page
    .getByRole("textbox", { name: "Replacement text", exact: true })
    .fill(
      "A newly expanded statement with extra words for the current revision only.",
    );
  await page
    .getByRole("button", { name: "Preview replacement", exact: true })
    .click();
  await page
    .getByRole("img", { name: "Text edit preview on slide 2", exact: true })
    .waitFor();
  await page
    .locator(".pw-mock-edit [role=status], .pw-mock-edit .pw-layout-warning")
    .waitFor();
  const warning = page.locator(".pw-mock-edit .pw-layout-warning");
  if (await warning.count()) await warning.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Save revision", exact: true })
    .click();
  await page.getByText("Current · Revision 3", { exact: true }).waitFor();
  await studio("Rehearsal");
  await inspect().click();
  await coverage
    .getByText("26 matching slides · page 1 of 2.", { exact: true })
    .waitFor();
  assert.equal(await moved.getByText(/^Native text:/).innerText(), nativeText);
  await coverage.getByText(/Rehearsed revision 1:/).waitFor();
  await moved
    .getByRole("button", { name: "Open current slide 2", exact: true })
    .click();
  await page.getByText("Slide 2 of 26", { exact: true }).waitFor();
  checks.push(
    "Actual native text replacement creates a new current revision while coverage still reports exact rehearsed native text counts and original recorded observations",
  );

  await app.evaluate(
    (_electron, modulePath) => {
      const { CoreProcessClient } = process.mainModule.require(modulePath);
      const original = CoreProcessClient.prototype.request;
      globalThis.coverageHeld = false;
      globalThis.coverageHold = false;
      globalThis.coverageRelease = true;
      CoreProcessClient.prototype.request = async function (...args) {
        const result = await original.apply(this, args);
        if (
          args[0] === "presentation.workspace.rehearsal_coverage" &&
          globalThis.coverageHold
        ) {
          globalThis.coverageHeld = true;
          const deadline = Date.now() + 30000;
          while (!globalThis.coverageRelease && Date.now() < deadline)
            await new Promise((resolve) => setTimeout(resolve, 30));
        }
        return result;
      };
    },
    path.join(desktop, "dist", "main", "core-client.js"),
  );
  await app.evaluate(() => {
    globalThis.coverageHold = true;
    globalThis.coverageRelease = false;
  });
  await inspect().click();
  const holdDeadline = Date.now() + 20000;
  while (
    !(await app.evaluate(() => globalThis.coverageHeld)) &&
    Date.now() < holdDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 40));
  assert.equal(await app.evaluate(() => globalThis.coverageHeld), true);
  await coverage
    .getByRole("combobox", { name: "Coverage filter", exact: true })
    .selectOption("no_visit");
  await app.evaluate(() => {
    globalThis.coverageRelease = true;
    globalThis.coverageHold = false;
  });
  await page.waitForTimeout(400);
  assert.equal(await coverage.locator("article").count(), 0);
  await inspect().click();
  await coverage
    .getByText("24 matching slides · page 1 of 2.", { exact: true })
    .waitFor();
  checks.push(
    "A held real Core coverage reply is discarded when its filter changes; new inspection binds to the chosen filter without old results reappearing",
  );

  await app.evaluate(() => {
    globalThis.coverageHold = true;
    globalThis.coverageRelease = false;
    globalThis.coverageHeld = false;
  });
  await inspect().click();
  const revisionDeadline = Date.now() + 20000;
  while (
    !(await app.evaluate(() => globalThis.coverageHeld)) &&
    Date.now() < revisionDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 40));
  assert.equal(await app.evaluate(() => globalThis.coverageHeld), true);
  await studio("Notes");
  await page
    .getByRole("textbox", { name: "Speaker notes", exact: true })
    .fill("A revised private speaking reminder.");
  await page
    .getByRole("button", { name: "Save speaker notes", exact: true })
    .click();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await app.evaluate(() => {
    globalThis.coverageRelease = true;
    globalThis.coverageHold = false;
  });
  await studio("Rehearsal");
  await page.waitForTimeout(400);
  assert.equal(await coverage.locator("article").count(), 0);
  await inspect().click();
  await coverage
    .getByText("26 matching slides · page 1 of 2.", { exact: true })
    .waitFor();
  assert.equal(await moved.getByText(/^Native text:/).innerText(), nativeText);
  checks.push(
    "A held old-revision real reply cannot publish after an actual GUI notes save; fresh current inspection retains original rehearsed density and session provenance",
  );
  const finalSource = await context(2);
  assert.equal(
    (await ask("presentation.workspace.list_claims", finalSource.scope)).items
      .length,
    0,
  );
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()
      .find((window) =>
        window.webContents.getURL().endsWith("/renderer/index.html"),
      )
      ?.setSize(720, 520),
  );
  await coverage
    .getByRole("heading", {
      name: "Review slide density and recorded coverage",
      exact: true,
    })
    .scrollIntoViewIfNeeded();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  assert.equal(overflow, false);
  await page.screenshot({ path: path.join(output, "minimum-coverage.png") });
  assert.equal((await context(2)).sha256, finalSource.sha256);
  assert.deepEqual(errors, []);
  checks.push(
    "Coverage controls and paged cards are contained at 720x520; read-only inspection/navigation preserves native SHA and creates no claims, evidence or presentation revisions",
  );
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, baseline, finalSource, scope }, null, 2),
  );
  console.log(JSON.stringify({ passed: checks.length, output }, null, 2));
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
        globalThis.coverageRelease = true;
      })
      .catch(() => {});
    await app.close();
  }
}
