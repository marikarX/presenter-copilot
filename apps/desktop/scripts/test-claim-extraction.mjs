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
  path.join(root, ".local", "claim-extraction", "gui");
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
for name,text,y in [('Basic metric','Revenue rose 20% during the pilot.',0.5),('Readonly metrics','Return on investment reached 24%.\n'+'Long supporting explanation for the metric. '*75,1.2)]:
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
  const readonly = baseline.inventory.targets.find((t) =>
    t.decision_text?.startsWith("Return on investment"),
  );
  assert.ok(
    readonly &&
      readonly.current_text === null &&
      readonly.decision_text.length > 2000,
  );
  const studio = async (name) =>
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
  await discovery
    .getByRole("checkbox", {
      name: "Readonly metrics · Native slide text",
      exact: true,
    })
    .check();
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
    .getByRole("button", { name: "Review candidate 2", exact: true })
    .click();
  assert.equal(
    await review.getByLabel("Exact claim quote", { exact: true }).inputValue(),
    "Return on investment reached 24%.",
  );
  const save = review.getByRole("button", {
    name: "Save reviewed claim",
    exact: true,
  });
  assert.equal(await save.isDisabled(), true);
  await review
    .getByRole("checkbox", {
      name: "I reviewed the quote and evidence relations for this revision.",
      exact: true,
    })
    .check();
  await save.click();
  await review
    .getByText("1 claim \u00b7 0 supported \u00b7 0 need review", {
      exact: true,
    })
    .waitFor();
  const saved = (
    await ask("presentation.workspace.list_claims", baseline.scope)
  ).items[0];
  assert.equal(saved.object_id, readonly.object_id);
  assert.equal(saved.coverage, "unlinked");
  assert.equal((await context()).sha256, baseline.sha256);
  await page.screenshot({
    path: path.join(output, "readonly-claim-review.png"),
  });
  checks.push(
    "Selected native text including a noneditable 3000-character object produces unsaved exact quotes; human review saves one unlinked claim without changing PPTX bytes",
  );
  await discovery
    .getByRole("button", { name: "Review candidate 2", exact: true })
    .click();
  assert.equal(await save.isDisabled(), true);
  await review
    .getByRole("checkbox", {
      name: "I reviewed the quote and evidence relations for this revision.",
      exact: true,
    })
    .check();
  await save.click();
  assert.equal(
    (await ask("presentation.workspace.list_claims", baseline.scope)).items
      .length,
    1,
  );
  checks.push(
    "Choosing an existing exact candidate reopens the same reviewed claim and clears approval instead of creating a duplicate",
  );
  await studio("Objects");
  await page
    .getByRole("textbox", { name: "New text box text", exact: true })
    .fill("Reviewed revision fixture.");
  await page.getByRole("button", { name: "Add text box", exact: true }).click();
  await page.getByText("Current \u00b7 Revision 2", { exact: true }).waitFor();
  await studio("Purpose");
  assert.equal(
    await discovery
      .getByRole("button", { name: "Review candidate 2", exact: true })
      .count(),
    0,
  );
  const changed = await context();
  assert.notEqual(changed.sha256, baseline.sha256);
  assert.equal(
    (await ask("presentation.workspace.list_claims", changed.scope)).items[0]
      .coverage,
    "needs_review",
  );
  checks.push(
    "Actual GUI deck edits invalidate candidates and inherited claims require fresh review on the new revision",
  );
  await app.evaluate(
    (_electron, filename) => {
      const { CoreProcessClient: CoreClient } =
        process.mainModule.require(filename);
      const original = CoreClient.prototype.request;
      globalThis.claimHold = true;
      globalThis.claimReady = false;
      globalThis.claimPending = false;
      CoreClient.prototype.request = async function (method, ...args) {
        const result = await original.call(this, method, ...args);
        if (method === "presentation.workspace.extract_claims") {
          if (globalThis.claimCorrupt) {
            globalThis.claimCorrupt = false;
            result.candidates[0].quote = "Unsupplied claim text";
          }

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
    .getByRole("button", { name: "Find candidates", exact: true })
    .click();
  const gateDeadline = Date.now() + 30000;
  while (
    !(await app.evaluate(() => globalThis.claimReady)) &&
    Date.now() < gateDeadline
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
  const finishDeadline = Date.now() + 30000;
  while (
    (await app.evaluate(() => globalThis.claimPending)) &&
    Date.now() < finishDeadline
  )
    await new Promise((r) => setTimeout(r, 100));
  assert.equal(await app.evaluate(() => globalThis.claimPending), false);
  assert.equal(
    await discovery
      .getByRole("button", { name: "Review candidate 1", exact: true })
      .count(),
    0,
  );
  const next = await context(2);
  assert.equal(
    (await ask("presentation.workspace.list_claims", next.scope)).items.length,
    0,
  );
  await discovery
    .getByRole("button", { name: "Find candidates", exact: true })
    .click();
  await discovery
    .getByRole("button", { name: "Review candidate 1", exact: true })
    .waitFor();
  checks.push(
    "A held real extraction reply after slide navigation is discarded; the new slide independently extracts without saving or inheriting old candidates",
  );
  await app.evaluate(() => {
    globalThis.claimCorrupt = true;
  });
  await discovery
    .getByRole("button", { name: "Find candidates", exact: true })
    .click();
  await discovery.getByRole("alert").waitFor();
  assert.equal(
    await discovery
      .getByRole("button", { name: "Review candidate 1", exact: true })
      .count(),
    0,
  );
  assert.equal(
    (await ask("presentation.workspace.list_claims", next.scope)).items.length,
    0,
  );
  await discovery
    .getByRole("button", { name: "Find candidates", exact: true })
    .click();
  await discovery
    .getByRole("button", { name: "Review candidate 1", exact: true })
    .waitFor();
  checks.push(
    "Renderer rejects a tampered unsupplied quote after the real Core reply; retry returns valid unsaved candidates without mutation",
  );
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()
      .find((w) => w.webContents.getURL().endsWith("/renderer/index.html"))
      .setSize(720, 520),
  );
  await page.waitForFunction(() => window.innerWidth <= 720);
  await discovery
    .getByRole("button", { name: "Review candidate 1", exact: true })
    .click();
  assert.equal(
    await review.evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
    true,
  );
  await page.screenshot({
    path: path.join(output, "minimum-claim-review.png"),
  });
  await discovery
    .getByRole("button", { name: "Dismiss candidates", exact: true })
    .click();
  assert.equal(
    (await ask("presentation.workspace.list_claims", next.scope)).items.length,
    0,
  );
  assert.deepEqual(errors, []);
  checks.push(
    "Minimum-window discovery/review is contained, and dismissal leaves the deck and claim store unchanged",
  );
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
