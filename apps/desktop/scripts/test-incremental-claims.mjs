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
  path.join(root, ".local", "incremental-claims", "gui");
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
  await app.evaluate(
    (_electron, modulePath) => {
      const { CoreProcessClient } = process.mainModule.require(modulePath);
      const original = CoreProcessClient.prototype.request;
      globalThis.deckExtractCalls = 0;
      globalThis.deckHoldAt = 0;
      globalThis.deckHeld = false;
      globalThis.deckRelease = true;
      globalThis.deckCorrupt = false;
      CoreProcessClient.prototype.request = async function (...args) {
        const result = await original.apply(this, args);
        if (args[0] === "presentation.workspace.extract_claims") {
          globalThis.deckExtractCalls++;
          if (globalThis.deckHoldAt === globalThis.deckExtractCalls) {
            globalThis.deckHeld = true;
            const deadline = Date.now() + 30000;
            while (!globalThis.deckRelease && Date.now() < deadline)
              await new Promise((resolve) => setTimeout(resolve, 30));
          }
          if (globalThis.deckCorrupt && result?.candidates?.length) {
            globalThis.deckCorrupt = false;
            return {
              ...result,
              candidates: [
                {
                  ...result.candidates[0],
                  quote: "Unsupplied deck claim text",
                },
              ],
            };
          }
        }
        return result;
      };
    },
    path.join(path.dirname(nativeModulePath), "core-client.js"),
  );
  const scan = page.getByRole("region", {
    name: "Deck claim discovery",
    exact: true,
  });
  const start = () =>
    scan.getByRole("button", {
      name: /^(Start|Resume) deck claim scan$/,
      exact: true,
    });
  const acknowledge = () =>
    scan.getByRole("checkbox", {
      name: "Send native text, table cells and raw chart cache data from these slides to my configured reasoning provider.",
      exact: true,
    });

  const calls = () => app.evaluate(() => globalThis.deckExtractCalls);
  const prepare = () =>
    scan.getByRole("button", { name: "Prepare deck claim scan", exact: true });
  const refresh = () =>
    scan.getByRole("button", { name: "Refresh changed text", exact: true });
  const waitRefreshed = () =>
    scan.getByText(/^Refreshed native text\./).waitFor();
  const roi = () =>
    scan
      .locator("article")
      .filter({ hasText: "Return on investment reached 24%." });
  const review = page.getByRole("region", {
    name: "Claim and evidence review",
    exact: true,
  });
  const confirm = () =>
    review.getByRole("checkbox", {
      name: "I reviewed the quote and evidence relations for this revision.",
      exact: true,
    });
  const save = () =>
    review.getByRole("button", { name: "Save reviewed claim", exact: true });
  await studio("Deck review");
  await prepare().click();
  await scan
    .getByRole("checkbox", { name: "Inspect slide 1", exact: true })
    .waitFor();
  assert.equal(
    await scan.getByRole("checkbox", { name: /^Inspect slide / }).count(),
    20,
  );
  await scan
    .getByRole("button", { name: "Next scan slides", exact: true })
    .click();
  assert.equal(
    await scan.getByRole("checkbox", { name: /^Inspect slide / }).count(),
    6,
  );
  await scan
    .getByRole("checkbox", { name: "Inspect slide 26", exact: true })
    .uncheck();
  await scan
    .getByRole("button", { name: "Previous scan slides", exact: true })
    .click();
  await scan
    .getByRole("button", { name: "Clear selected slides", exact: true })
    .click();
  assert.equal(await start().isDisabled(), true);
  await scan
    .getByRole("button", { name: "Select all available slides", exact: true })
    .click();
  const base = {
    project_id: baseline.scope.project_id,
    document_id: baseline.scope.document_id,
    revision_id: baseline.scope.revision_id,
  };
  const first = await ask("presentation.workspace.prepare_claim_scan", {
    ...base,
    limit: 20,
  });
  const last = await ask("presentation.workspace.prepare_claim_scan", {
    ...base,
    offset: 20,
    limit: 20,
  });
  assert.equal(first.total_slides, 26);
  const planned = first.provider_calls + last.provider_calls;
  assert.equal(planned, 28);
  assert.equal(await calls(), 0);
  assert.equal(await start().isDisabled(), true);
  await page.screenshot({ path: path.join(output, "paged-preflight.png") });
  checks.push(
    "Actual 26-slide deck preflight renders 20 then 6 selection rows, preserves cross-page choices and bulk selection, and requires disclosure before all 28 planned requests",
  );

  await acknowledge().check();
  await start().click();
  await scan
    .getByText(new RegExp(`Finished ${planned} requests`))
    .waitFor({ timeout: 120000 });
  assert.equal(await calls(), planned);
  assert.equal(await scan.locator("article").count(), 20);
  await scan
    .getByRole("button", { name: "Next claim candidates", exact: true })
    .click();
  assert.equal(await scan.locator("article").count(), 8);
  await scan
    .getByRole("button", { name: "Review quote on slide 26", exact: true })
    .waitFor();
  await scan
    .getByRole("button", { name: "Previous claim candidates", exact: true })
    .click();
  assert.equal(
    (await ask("presentation.workspace.list_claims", baseline.scope)).items
      .length,
    0,
  );
  assert.equal((await context()).sha256, baseline.sha256);
  checks.push(
    "Full 28-request scan paginates candidates as 20 then 8 while leaving native bytes and claim metadata unchanged",
  );

  await roi()
    .getByRole("button", { name: "Review quote on slide 1", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelector('textarea[aria-label="Exact claim quote"]')
        ?.value === "Return on investment reached 24%.",
  );
  assert.equal(await save().isDisabled(), true);
  await confirm().check();
  await save().click();
  await page.waitForFunction(async (scope) => {
    const r = await window.presenterCopilot.core.request(
      "presentation.workspace.list_claims",
      scope,
    );
    return r.ok && r.result.items.length === 1;
  }, baseline.scope);
  const originalClaim = (
    await ask("presentation.workspace.list_claims", baseline.scope)
  ).items[0];
  checks.push(
    "First candidate requires explicit quote/evidence confirmation and produces one user-confirmed claim",
  );

  await studio("Objects");
  await page
    .getByRole("textbox", { name: "New text box text", exact: true })
    .fill("Conversion is forecast to increase by 8%.");
  await page.getByRole("button", { name: "Add text box", exact: true }).click();
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  const revision2 = await context();
  await studio("Deck review");
  assert.equal(
    await scan.getByRole("checkbox", { name: /^Inspect slide / }).count(),
    0,
  );
  assert.equal(await scan.locator("article").count(), 0);
  await refresh().click();
  await waitRefreshed();
  await scan.getByText(/1 provider requests needed/).waitFor();
  assert.equal(await calls(), planned);
  assert.equal(
    await roi().getAttribute("data-original-revision"),
    baseline.scope.revision_id,
  );
  await roi()
    .getByText(/Reused from an earlier scan/)
    .waitFor();
  assert.equal(
    (await ask("presentation.workspace.list_claims", revision2.scope)).items[0]
      .coverage,
    "needs_review",
  );
  await acknowledge().check();
  await start().click();
  await scan.getByText(/Finished 28 text windows \(27 reused\)/).waitFor();
  assert.equal(await calls(), planned + 1);
  await page.screenshot({
    path: path.join(output, "incremental-add-object.png"),
  });
  checks.push(
    "Real native object insertion invalidates visible results; fresh local verification reuses 27 unchanged windows with original provider revision and sends only the one changed batch",
  );

  await roi()
    .getByRole("button", { name: "Review quote on slide 1", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelector('textarea[aria-label="Exact claim quote"]')
        ?.value === "Return on investment reached 24%.",
  );
  assert.equal(await confirm().isChecked(), false);
  assert.equal(await save().isDisabled(), true);
  await confirm().check();
  await save().click();
  const reviewed2 = (
    await ask("presentation.workspace.list_claims", revision2.scope)
  ).items;
  assert.equal(reviewed2.length, 1);
  assert.equal(reviewed2[0].claim_id, originalClaim.claim_id);
  assert.equal((await context()).sha256, revision2.sha256);
  checks.push(
    "Reused suggestion remains unapproved on the new revision; explicit review reuses its existing claim ID and preserves the current PPTX bytes",
  );

  await studio("Text");
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .selectOption({ index: 0 });
  await page
    .getByRole("textbox", { name: "Replacement text", exact: true })
    .fill("Revenue rose 31% during the pilot.");
  await page
    .getByRole("button", { name: "Preview replacement", exact: true })
    .click();
  await page
    .getByRole("img", { name: "Text edit preview on slide 1", exact: true })
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
  await studio("Deck review");
  await refresh().click();
  await waitRefreshed();
  await scan.getByText(/1 provider requests needed/).waitFor();
  assert.equal(await calls(), planned + 1);
  assert.equal(
    await scan
      .getByText("Revenue rose 20% during the pilot.", { exact: true })
      .count(),
    0,
  );
  await acknowledge().check();
  await start().click();
  await scan.getByText(/Finished 28 text windows \(27 reused\)/).waitFor();
  assert.equal(await calls(), planned + 2);
  await scan
    .getByText("Revenue rose 31% during the pilot.", { exact: true })
    .waitFor();
  checks.push(
    "Actual reviewed native text replacement removes its old quote from reuse and reanalyzes exactly one changed input while retaining all other verified windows",
  );

  await studio("Notes");
  await page
    .getByRole("textbox", { name: "Speaker notes", exact: true })
    .fill("A private speaking reminder; excluded from claim extraction.");
  await page
    .getByRole("button", { name: "Save speaker notes", exact: true })
    .click();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await studio("Deck review");
  await refresh().click();
  await waitRefreshed();
  await scan.getByText(/0 provider requests needed/).waitFor();
  assert.equal(await calls(), planned + 2);
  assert.equal(await start().isDisabled(), true);
  assert.equal(
    await roi().getAttribute("data-original-revision"),
    baseline.scope.revision_id,
  );
  assert.equal(
    (await ask("presentation.workspace.list_claims", (await context()).scope))
      .items[0].coverage,
    "needs_review",
  );
  checks.push(
    "Notes-only native revision revalidates/reuses all text windows without any model calls or disclosure, preserves original provenance and does not approve inherited claims",
  );

  const actions = page.locator("details.pw-slide-actions");
  if (!(await actions.evaluate((node) => node.open)))
    await actions.locator("summary").click();
  await page
    .getByRole("button", { name: "Move current slide later", exact: true })
    .click();
  await page.getByText("Current · Revision 5", { exact: true }).waitFor();
  await studio("Deck review");
  await refresh().click();
  await waitRefreshed();
  await scan.getByText(/0 provider requests needed/).waitFor();
  assert.equal(await calls(), planned + 2);
  await roi()
    .getByRole("button", { name: "Review quote on slide 2", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelector('textarea[aria-label="Exact claim quote"]')
        ?.value === "Return on investment reached 24%.",
  );
  assert.equal(await confirm().isChecked(), false);
  assert.equal((await context(2)).scope.slide_id, baseline.scope.slide_id);
  checks.push(
    "Actual native slide reorder retains exact-input cache lineage, updates the displayed ordinal and opens the reused quote on its stable slide identity with fresh approval required",
  );

  await studio("Deck review");
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()
      .find((w) => w.webContents.getURL().endsWith("/renderer/index.html"))
      ?.setSize(720, 520),
  );
  await scan.scrollIntoViewIfNeeded();
  const bounds = await scan.boundingBox();
  const width = await page.evaluate(() => window.innerWidth);
  assert.ok(bounds.x >= -1 && bounds.x + bounds.width <= width + 1);
  await page.screenshot({
    path: path.join(output, "minimum-incremental-review.png"),
  });
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()
      .find((w) => w.webContents.getURL().endsWith("/renderer/index.html"))
      ?.setSize(1180, 760),
  );
  checks.push(
    "Paged 26-slide selection and reused-candidate review remain horizontally contained at 720x520",
  );

  await app.evaluate(
    (_electron, filename) => {
      const { CoreProcessClient } = process.mainModule.require(filename);
      const original = CoreProcessClient.prototype.request;
      globalThis.incrementalHold = true;
      globalThis.incrementalHeld = false;
      globalThis.incrementalRelease = false;
      CoreProcessClient.prototype.request = async function (method, ...args) {
        const result = await original.call(this, method, ...args);
        if (
          method === "presentation.workspace.prepare_claim_scan" &&
          globalThis.incrementalHold
        ) {
          globalThis.incrementalHeld = true;
          const deadline = Date.now() + 30000;
          while (!globalThis.incrementalRelease && Date.now() < deadline)
            await new Promise((resolve) => setTimeout(resolve, 30));
        }
        return result;
      };
    },
    path.join(path.dirname(nativeModulePath), "core-client.js"),
  );
  await refresh().click();
  const holdDeadline = Date.now() + 20000;
  while (
    !(await app.evaluate(() => globalThis.incrementalHeld)) &&
    Date.now() < holdDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 50));
  assert.equal(await app.evaluate(() => globalThis.incrementalHeld), true);
  await studio("Notes");
  await page
    .getByRole("textbox", { name: "Speaker notes", exact: true })
    .fill("Another excluded reminder while an old preflight reply is held.");
  await page
    .getByRole("button", { name: "Save speaker notes", exact: true })
    .click();
  await page.getByText("Current · Revision 6", { exact: true }).waitFor();
  await app.evaluate(() => {
    globalThis.incrementalHold = false;
    globalThis.incrementalRelease = true;
  });
  await studio("Deck review");
  assert.equal(await scan.locator("article").count(), 0);
  assert.equal(
    await scan.getByRole("checkbox", { name: /^Inspect slide / }).count(),
    0,
  );
  await refresh().click();
  await waitRefreshed();
  await scan.getByText(/0 provider requests needed/).waitFor();
  assert.equal(await calls(), planned + 2);
  checks.push(
    "Held real old-revision preflight cannot publish or rebase cached results after an actual GUI revision change; a new explicit refresh verifies current text without model calls",
  );

  const headBeforeFresh = (await context(2)).sha256;
  await prepare().click();
  await scan
    .getByRole("checkbox", { name: "Inspect slide 1", exact: true })
    .waitFor();
  await scan.getByText(/28 provider requests needed/).waitFor();
  assert.equal(await scan.locator("article").count(), 0);
  assert.equal(await acknowledge().isChecked(), false);
  assert.equal(await calls(), planned + 2);
  assert.equal((await context(2)).sha256, headBeforeFresh);
  checks.push(
    "Explicit fresh scan clears unsaved cache reuse, plans all input anew, requires disclosure and leaves native bytes and saved claims unchanged",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      { checks, errors, planned, model_calls: await calls(), baseline },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify(
      { passed: checks.length, planned, model_calls: await calls(), output },
      null,
      2,
    ),
  );
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
        globalThis.deckRelease = true;
        globalThis.incrementalRelease = true;
      })
      .catch(() => {});
    await app.close();
  }
}
