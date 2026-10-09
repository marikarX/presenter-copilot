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
  path.join(root, ".local", "deck-claims", "gui");
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
for name,text,y in [('Basic metric','Revenue rose 20% during the pilot.',0.5),('Readonly metrics','Return on investment reached 24%.\n'+' '.join(f'Unique supporting observation {i}.' for i in range(210)),1.2)]:
 shape=slide.shapes.add_textbox(Inches(.5),Inches(y),Inches(9),Inches(3));shape.name=name;shape.text=text
 for p in shape.text_frame.paragraphs:p.font.size=Pt(8)
other=presentation.slides.add_slide(presentation.slide_layouts[6]);other.shapes.add_textbox(Inches(.5),Inches(.5),Inches(9),Inches(2)).text='Other slide statement.'
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
  await studio("Deck review");
  await scan
    .getByRole("button", { name: "Prepare deck claim scan", exact: true })
    .click();
  await scan
    .getByRole("checkbox", { name: "Inspect slide 2", exact: true })
    .waitFor();
  const plan = await ask("presentation.workspace.prepare_claim_scan", {
    project_id: baseline.scope.project_id,
    document_id: baseline.scope.document_id,
    revision_id: baseline.scope.revision_id,
  });
  assert.equal(plan.total_slides, 2);
  assert.ok(
    plan.items[0].batches.length >= 3,
    "Dense read-only object is windowed rather than omitted",
  );
  const planned = plan.provider_calls;
  assert.equal(await app.evaluate(() => globalThis.deckExtractCalls), 0);
  assert.equal(await start().isDisabled(), true);
  await page.screenshot({ path: path.join(output, "preflight.png") });
  checks.push(
    "Local full-deck preflight inventories both slides, windows dense native text, exposes exact request count and requires disclosure acknowledgement before inference",
  );

  await app.evaluate(() => {
    globalThis.deckHoldAt = 2;
    globalThis.deckHeld = false;
    globalThis.deckRelease = false;
  });
  await acknowledge().check();
  await start().click();
  const waitHeld = async () => {
    const deadline = Date.now() + 20000;
    while (
      !(await app.evaluate(() => globalThis.deckHeld)) &&
      Date.now() < deadline
    )
      await new Promise((resolve) => setTimeout(resolve, 50));
    assert.equal(await app.evaluate(() => globalThis.deckHeld), true);
  };
  await waitHeld();
  await scan
    .getByRole("button", { name: "Stop claim scan", exact: true })
    .click();
  await app.evaluate(() => {
    globalThis.deckRelease = true;
  });
  await start().waitFor();
  await page.waitForFunction(
    () =>
      ![...document.querySelectorAll("button")].find(
        (b) => b.textContent === "Prepare deck claim scan",
      )?.disabled,
  );
  assert.equal(await app.evaluate(() => globalThis.deckExtractCalls), 2);
  await scan
    .getByText(
      "Scan stopped. Completed candidates remain unsaved. Review before resuming.",
      { exact: true },
    )
    .waitFor();
  assert.equal(
    await scan
      .getByRole("button", { name: "Review quote on slide 1", exact: true })
      .count(),
    1,
  );
  assert.equal(await acknowledge().isChecked(), false);
  await acknowledge().check();
  await start().click();
  await scan.getByText(new RegExp(`Finished ${planned} requests`)).waitFor();
  assert.equal(
    await app.evaluate(() => globalThis.deckExtractCalls),
    planned + 1,
  );
  assert.equal(
    (await ask("presentation.workspace.list_claims", baseline.scope)).items
      .length,
    0,
  );
  const roi = scan
    .locator("article")
    .filter({ hasText: "Return on investment reached 24%." });
  assert.equal(await roi.count(), 1);
  await page.screenshot({ path: path.join(output, "completed.png") });
  checks.push(
    "Stop discards a held real Core reply and prevents future requests; resume retains completed batches, finishes all selected windows and leaves claims/PPTX unsaved",
  );

  await roi
    .getByRole("button", { name: "Review quote on slide 1", exact: true })
    .click();
  const review = page.getByRole("region", {
    name: "Claim and evidence review",
    exact: true,
  });
  await page
    .waitForFunction(
      () =>
        document.querySelector('textarea[aria-label="Exact claim quote"]')
          ?.value === "Return on investment reached 24%.",
    )
    .catch(async () => {
      assert.equal(
        await review
          .getByLabel("Exact claim quote", { exact: true })
          .inputValue(),
        "Return on investment reached 24%.",
      );
    });
  const save = review.getByRole("button", {
    name: "Save reviewed claim",
    exact: true,
  });
  const confirm = review.getByRole("checkbox", {
    name: "I reviewed the quote and evidence relations for this revision.",
    exact: true,
  });
  assert.equal(await save.isDisabled(), true);
  await confirm.check();
  await save.click();
  await page.waitForFunction(async (scope) => {
    const r = await window.presenterCopilot.core.request(
      "presentation.workspace.list_claims",
      scope,
    );
    return r.ok && r.result.items.length === 1;
  }, baseline.scope);
  const saved = (
    await ask("presentation.workspace.list_claims", baseline.scope)
  ).items[0];
  assert.equal(saved.quote, "Return on investment reached 24%.");
  assert.equal(saved.coverage, "unlinked");
  assert.equal((await context()).sha256, baseline.sha256);
  checks.push(
    "Deck candidate opens the exact read-only native quote on its slide, requires individual review, and saves one user-confirmed claim without changing native PPTX bytes",
  );

  await confirm.check();
  await studio("Deck review");
  await roi
    .getByRole("button", { name: "Review quote on slide 1", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      ![...document.querySelectorAll("input[type=checkbox]")].find((i) =>
        i.parentElement?.textContent?.includes(
          "I reviewed the quote and evidence relations",
        ),
      )?.checked,
  );
  assert.equal(await confirm.isChecked(), false);
  await confirm.check();
  await save.click();
  assert.equal(
    (await ask("presentation.workspace.list_claims", baseline.scope)).items[0]
      .claim_id,
    saved.claim_id,
  );
  assert.equal(
    (await ask("presentation.workspace.list_claims", baseline.scope)).items
      .length,
    1,
  );
  checks.push(
    "Repeated deck-candidate selection resets approval and reuses the existing claim/evidence instead of duplicating metadata",
  );

  await studio("Deck review");
  await scan
    .getByRole("button", { name: "Prepare deck claim scan", exact: true })
    .click();
  await scan
    .getByRole("checkbox", { name: "Inspect slide 2", exact: true })
    .waitFor();
  await app.evaluate(() => {
    globalThis.deckCorrupt = true;
  });
  await acknowledge().check();
  await start().click();
  await scan.getByRole("alert").filter({ hasText: "does not match" }).waitFor();
  assert.equal(
    await scan.getByRole("button", { name: /Review quote on slide/ }).count(),
    0,
  );
  assert.equal(await acknowledge().isChecked(), false);
  await acknowledge().check();
  await start().click();
  await scan.getByText(new RegExp(`Finished ${planned} requests`)).waitFor();
  assert.equal(
    (await ask("presentation.workspace.list_claims", baseline.scope)).items
      .length,
    1,
  );
  checks.push(
    "Fresh native-text verification rejects a tampered quote after real Core inference, stops the scan, clears disclosure approval and allows a reviewed retry",
  );

  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()
      .find((w) => w.webContents.getURL().endsWith("/renderer/index.html"))
      ?.setSize(720, 520);
  });
  await scan.scrollIntoViewIfNeeded();
  const bounds = await scan.boundingBox();
  const viewport = await page.evaluate(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
  }));
  assert.ok(bounds.x >= -1 && bounds.x + bounds.width <= viewport.width + 1);
  await page.screenshot({ path: path.join(output, "minimum-deck-scan.png") });
  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()
      .find((w) => w.webContents.getURL().endsWith("/renderer/index.html"))
      ?.setSize(1180, 760);
  });
  checks.push(
    "Full-deck request controls and candidates remain horizontally contained at the minimum 720x520 window",
  );

  await scan
    .getByRole("button", { name: "Prepare deck claim scan", exact: true })
    .click();
  await scan
    .getByRole("checkbox", { name: "Inspect slide 2", exact: true })
    .waitFor();
  await app.evaluate(() => {
    globalThis.deckHoldAt = globalThis.deckExtractCalls + 1;
    globalThis.deckHeld = false;
    globalThis.deckRelease = false;
  });
  await acknowledge().check();
  await start().click();
  await waitHeld();
  await studio("Objects");
  await page
    .getByRole("textbox", { name: "New text box text", exact: true })
    .fill("Revision invalidates the deck scan.");
  await page.getByRole("button", { name: "Add text box", exact: true }).click();
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  await app.evaluate(() => {
    globalThis.deckRelease = true;
  });
  await studio("Deck review");
  await scan
    .getByRole("button", { name: "Prepare deck claim scan", exact: true })
    .waitFor();
  assert.equal(
    await scan
      .getByRole("checkbox", { name: "Inspect slide 1", exact: true })
      .count(),
    0,
  );
  assert.equal(
    await scan.getByRole("button", { name: /Review quote on slide/ }).count(),
    0,
  );
  const current = await context();
  assert.equal(
    (await ask("presentation.workspace.list_claims", current.scope)).items[0]
      .coverage,
    "needs_review",
  );
  checks.push(
    "Actual GUI native revision change clears the entire prepared scan and candidate handoff; a held old-revision reply cannot repopulate it, and inherited claims need fresh review",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, planned, baseline }, null, 2),
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
        globalThis.deckRelease = true;
      })
      .catch(() => {});
    await app.close();
  }
}
