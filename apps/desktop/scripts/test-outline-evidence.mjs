/* global document, window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";

// Actual Core proposal provenance/native creation/claim Save; model output is a fixture.
const root = path.resolve(process.cwd());
const desktop = path.join(root, "apps", "desktop");
const require = createRequire(path.join(desktop, "package.json"));
const { _electron: electron } = require("playwright");
const temporary = await mkdtemp(
  path.join(os.tmpdir(), "presenter-outline-evidence-"),
);
const output = path.join(root, ".local", "outline-evidence-links", "gui");
await mkdir(output, { recursive: true });
const supporting = path.join(temporary, "Pilot.md");
await writeFile(
  supporting,
  "# Pilot rationale\nThe pilot measures decision quality after thirty days.\n",
);
const python = path.join(root, "core", ".venv", "Scripts", "python.exe");
const seeded = JSON.parse(
  execFileSync(
    python,
    [
      "-c",
      String.raw`
import copy,json,sys
from pathlib import Path
sys.path[:0]=[str(Path.cwd()/'core'),str(Path.cwd()/'core/tests')]
from test_presentation_planning import CitationProvider,call,context
from presenter_core.ipc.core import CoreService
from presenter_core.retrieval.embeddings import DeterministicEmbeddingAdapter
core=CoreService(data_root=Path(sys.argv[1]),reasoning_provider=CitationProvider(locality='local'),embedding_adapter=DeterministicEmbeddingAdapter(dimension=2))
try:
 project,params=context(core)
 call(core,'source.import',{'project_id':project,'kind':'supporting','path':sys.argv[2]})
 proposal=call(core,'presentation.workspace.propose_outline',params)
 fields={k:params[k] for k in ('objective','audience','briefing','slide_count')}
 fields['instruction']='Plan a clear narrative for this presentation.'
 turn={'ordinal':1,'request':copy.deepcopy(fields),'parentRunId':None,'baseline':None,'original':proposal,'draft':copy.deepcopy(proposal)}
 call(core,'presentation.workspace.save_outline_session',{'project_id':project,'expected_record_token':None,'payload':{'fields':fields,'conversation':{'turns':[turn],'activeRunId':proposal['provider_run_id']}}})
 print(json.dumps({'project':project,'run':proposal['provider_run_id'],'evidence':proposal['slides'][0]['evidence_ids'][0]}))
finally: core.close()
`,
      path.join(temporary, "core"),
      supporting,
    ],
    { cwd: root, encoding: "utf8", windowsHide: true },
  ),
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
});
let app, page;
const errors = [],
  checks = [];
async function ask(method, params) {
  return page.evaluate(
    async ({ method, params }) => {
      const r = await window.presenterCopilot.core.request(method, params);
      if (!r.ok) throw new Error(r.error.message);
      return r.result;
    },
    { method, params },
  );
}
function counts() {
  return JSON.parse(
    execFileSync(
      python,
      [
        "-c",
        String.raw`
import sqlite3,json,sys
from pathlib import Path
c=sqlite3.connect('file:'+Path(sys.argv[1]).as_posix()+'?mode=ro',uri=True)
print(json.dumps({'claims':c.execute('SELECT COUNT(*) FROM presentation_claims').fetchone()[0],'runs':c.execute('SELECT COUNT(*) FROM provider_runs').fetchone()[0]}));c.close()
`,
        path.join(temporary, "core", "projects", seeded.project, "project.db"),
      ],
      { encoding: "utf8", windowsHide: true },
    ),
  );
}
try {
  app = await electron.launch({
    executablePath: require("electron"),
    args: [desktop, `--user-data-dir=${path.join(temporary, "browser")}`],
    cwd: root,
    env,
    timeout: 30000,
  });
  const deadline = Date.now() + 30000;
  while (!page && Date.now() < deadline) {
    page = app
      .windows()
      .find((candidate) => candidate.url().endsWith("/renderer/index.html"));
    if (!page) await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(page);
  page.setDefaultTimeout(30000);
  page.on("pageerror", (error) => errors.push(error.message));
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Narrative plan", exact: true })
    .click();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page
    .getByRole("button", { name: "New presentation", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Start with your outline",
    exact: true,
  });
  await dialog
    .getByRole("button", { name: "Plan with Copilot", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Reload saved copy", exact: true })
    .waitFor();
  await page.waitForFunction(
    () =>
      !document
        .querySelector('.pw-outline-planner [role="status"]')
        ?.textContent.includes("Accessing"),
  );
  await dialog
    .getByRole("button", { name: "Resume saved drafting session", exact: true })
    .click();
  await dialog
    .getByLabel("Slide 1 points", { exact: true })
    .fill(
      "The author reviewed this pilot point.\nReview the decision quality after thirty days.",
    );
  await dialog
    .getByRole("button", { name: "Review this outline", exact: true })
    .click();
  await dialog
    .getByLabel("Slide 1 layout", { exact: true })
    .selectOption("cards");
  await dialog
    .getByRole("button", { name: "Move slide 1 later", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Duplicate draft slide 2", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Remove draft slide 4", exact: true })
    .click();
  assert.equal(
    await dialog.getByText(/planning reference\(s\) retained/).count(),
    2,
  );
  await page.screenshot({ path: path.join(output, "creation-review.png") });
  await dialog
    .getByRole("button", { name: "Create presentation", exact: true })
    .click();
  await dialog.waitFor({ state: "hidden" });
  const documentSource = (
    await ask("source.list", { project_id: seeded.project })
  ).sources.find((source) => source.kind === "presentation");
  assert.ok(documentSource);
  const opened = await ask("presentation.workspace.open_source", {
    project_id: seeded.project,
    document_id: documentSource.id,
  });
  const scope = {
    project_id: seeded.project,
    document_id: documentSource.id,
    revision_id: opened.revision_id,
  };
  const packet = await ask(
    "presentation.workspace.list_outline_evidence_candidates",
    scope,
  );
  assert.equal(packet.total_points, 4);
  assert.equal(packet.items[0].original_slide_number, 2);
  assert.equal(packet.items[0].quote, "The author reviewed this pilot point.");
  assert.equal(packet.items[0].references[0].evidence_id, seeded.evidence);
  assert.notEqual(packet.items[0].object_id, packet.items[2].object_id);
  assert.deepEqual(counts(), { claims: 0, runs: 1 });
  checks.push(
    "Real stored cited plan reaches edited/reordered/duplicated native cards, with distinct point IDs and no inferred claim",
  );
  const studio = async (name) =>
    page
      .getByRole("group", { name: "Slide studio panels", exact: true })
      .getByRole("button", { name, exact: true })
      .click();
  await studio("Deck review");
  const panel = page.getByRole("region", {
    name: "Outline evidence review",
    exact: true,
  });
  await panel
    .getByRole("button", { name: "Load outline evidence", exact: true })
    .click();
  const point = panel.locator("article").first();
  await point.locator("summary").first().click();
  await point
    .getByRole("checkbox", {
      name: `Select reference ${seeded.evidence} for point 2:1`,
      exact: true,
    })
    .check();
  await page.screenshot({ path: path.join(output, "source-comparison.png") });
  await point
    .getByRole("button", {
      name: "Review point 2:1 on current slide",
      exact: true,
    })
    .click();
  const review = page.getByRole("region", {
    name: "Claim and evidence review",
    exact: true,
  });
  await page.waitForFunction(
    () =>
      document.querySelector('textarea[aria-label="Exact claim quote"]')
        ?.value === "The author reviewed this pilot point.",
  );
  const relation = review.getByLabel("Evidence relation for Pilot.md", {
    exact: true,
  });
  assert.equal(await relation.inputValue(), "context");
  const save = review.getByRole("button", {
    name: "Save reviewed claim",
    exact: true,
  });
  assert.equal(await save.isDisabled(), true);
  assert.deepEqual(counts(), { claims: 0, runs: 1 });
  await save.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, "unsaved-context.png") });
  await review
    .getByRole("checkbox", {
      name: "I reviewed the quote and evidence relations for this revision.",
      exact: true,
    })
    .check();
  await save.click();
  const claimScope = {
    ...scope,
    slide_id: packet.items[0].slide_id,
    slide_number: 2,
  };
  await page.waitForTimeout(300);
  let saved = await ask("presentation.workspace.list_claims", claimScope);
  assert.equal(saved.items.length, 1);
  assert.equal(saved.items[0].evidence[0].relation, "context");
  checks.push(
    "Selecting a retained citation loads the current excerpt as unsaved context; only separate review confirmation and Save persist a claim",
  );
  await studio("Deck review");
  await panel
    .getByRole("button", { name: "Load outline evidence", exact: true })
    .click();
  await point.locator("summary").first().click();
  await point
    .getByRole("checkbox", {
      name: `Select reference ${seeded.evidence} for point 2:1`,
      exact: true,
    })
    .check();
  await point
    .getByRole("button", {
      name: "Review point 2:1 on current slide",
      exact: true,
    })
    .click();
  await relation.waitFor();
  await relation.selectOption("supports");
  await review
    .getByRole("checkbox", {
      name: "I reviewed the quote and evidence relations for this revision.",
      exact: true,
    })
    .check();
  await save.click();
  await page.waitForTimeout(300);
  saved = await ask("presentation.workspace.list_claims", claimScope);
  assert.equal(saved.items.length, 1);
  assert.equal(saved.items[0].evidence[0].relation, "supports");
  assert.deepEqual(counts(), { claims: 1, runs: 1 });
  await studio("Deck review");
  await panel
    .getByRole("button", { name: "Load outline evidence", exact: true })
    .click();
  await point.locator("summary").first().click();
  await point
    .getByRole("checkbox", {
      name: `Select reference ${seeded.evidence} for point 2:1`,
      exact: true,
    })
    .check();
  await point
    .getByRole("button", {
      name: "Review point 2:1 on current slide",
      exact: true,
    })
    .click();
  await relation.waitFor();
  assert.equal(await relation.inputValue(), "supports");
  assert.equal(await save.isDisabled(), true);
  checks.push(
    "Reopening an exact saved claim preserves its judged links and resets approval; explicit relation change updates the existing claim",
  );
  await studio("Deck review");
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()
      .find((w) => w.webContents.getURL().endsWith("/renderer/index.html"))
      ?.setSize(720, 520),
  );
  await panel
    .getByRole("button", { name: "Load outline evidence", exact: true })
    .click();
  await point.locator("summary").first().click();
  await panel.scrollIntoViewIfNeeded();
  const viewport = await page.evaluate(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio,
  }));
  assert.ok(viewport.width > 0 && viewport.width <= 720);
  assert.ok(viewport.height > 0 && viewport.height <= 520);
  assert.ok(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth + 1,
    ),
  );
  await page.screenshot({ path: path.join(output, "small-source-review.png") });
  checks.push("720x520 source comparison has no horizontal overflow");
  await app.evaluate(
    (_electron, filename) => {
      const { CoreProcessClient } = process.mainModule.require(filename);
      const original = CoreProcessClient.prototype.request;
      globalThis.outlineHold = true;
      globalThis.outlineReady = false;
      globalThis.outlinePending = false;
      CoreProcessClient.prototype.request = async function (method, ...args) {
        const result = await original.call(this, method, ...args);
        if (
          method === "presentation.workspace.list_outline_evidence_candidates"
        ) {
          globalThis.outlineReady = true;
          globalThis.outlinePending = true;
          const deadline = Date.now() + 30000;
          while (globalThis.outlineHold && Date.now() < deadline)
            await new Promise((resolve) => setTimeout(resolve, 50));
          globalThis.outlinePending = false;
          if (globalThis.outlineHold)
            throw new Error("Owned outline reply gate expired");
        }
        return result;
      };
    },
    path.join(desktop, "dist", "main", "core-client.js"),
  );
  await panel
    .getByRole("button", { name: "Load outline evidence", exact: true })
    .click();
  const holdDeadline = Date.now() + 30000;
  while (
    !(await app.evaluate(() => globalThis.outlineReady)) &&
    Date.now() < holdDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 100));
  assert.equal(await app.evaluate(() => globalThis.outlineReady), true);
  await studio("Purpose");
  await app.evaluate(() => {
    globalThis.outlineHold = false;
  });
  const releaseDeadline = Date.now() + 30000;
  while (
    (await app.evaluate(() => globalThis.outlinePending)) &&
    Date.now() < releaseDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 100));
  assert.equal(await app.evaluate(() => globalThis.outlinePending), false);
  await studio("Deck review");
  assert.equal(await panel.locator("article").count(), 0);
  assert.deepEqual(counts(), { claims: 1, runs: 1 });
  checks.push(
    "Held actual Core reader reply after leaving deck review is discarded and cannot hand off or persist",
  );
  await page
    .getByRole("button", { name: "New presentation", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Plan with Copilot", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Resume saved drafting session", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Review this outline", exact: true })
    .click();
  await dialog
    .getByText(/Editing the whole outline starts a manual draft/)
    .waitFor();
  await dialog
    .getByRole("button", { name: "Edit outline", exact: true })
    .click();
  await dialog
    .getByLabel("Presentation title", { exact: true })
    .fill("Manual draft after raw edit");
  await dialog
    .getByRole("button", { name: "Review outline", exact: true })
    .click();
  assert.equal(
    await dialog.getByText(/planning reference\(s\) retained/).count(),
    0,
  );
  await dialog
    .getByRole("button", { name: "Create presentation", exact: true })
    .click();
  await dialog.waitFor({ state: "hidden" });
  const manual = (
    await ask("source.list", { project_id: seeded.project })
  ).sources.find(
    (source) =>
      source.kind === "presentation" && source.id !== documentSource.id,
  );
  assert.ok(manual);
  const manualOpened = await ask("presentation.workspace.open_source", {
    project_id: seeded.project,
    document_id: manual.id,
  });
  const manualReferences = await ask(
    "presentation.workspace.list_outline_evidence_candidates",
    {
      project_id: seeded.project,
      document_id: manual.id,
      revision_id: manualOpened.revision_id,
    },
  );
  assert.equal(manualReferences.has_receipt, false);
  assert.deepEqual(counts(), { claims: 1, runs: 1 });
  checks.push(
    "Whole-outline editing explicitly becomes a manual draft and clears structured citation/planning authority without inference or claims",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      {
        checks,
        errors,
        seeded,
        scope,
        viewport,
        temporary,
        limitation:
          "Seeded actual Core citation proposal with fixture model; source GUI acceptance, not live model or human usefulness.",
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ output, checks, errors }, null, 2));
} finally {
  if (page)
    await page
      .screenshot({ path: path.join(output, "final.png") })
      .catch(() => {});
  if (app) {
    await app
      .evaluate(() => {
        globalThis.outlineHold = false;
      })
      .catch(() => {});
    await app.close();
  }
}
