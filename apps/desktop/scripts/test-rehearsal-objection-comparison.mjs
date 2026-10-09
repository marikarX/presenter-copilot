/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX; picker, recorded speech and model adapter are fixtures.
const require = createRequire(import.meta.url);
const desktop = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const root = path.resolve(desktop, "../..");
const python = path.join(
  root,
  "core",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const temporary = await mkdtemp(
  path.join(os.tmpdir(), "presenter-objection-compare-"),
);
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "rehearsal-semantic-coverage", "comparison-gui");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "presentation.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
from pptx.util import Inches
presentation=Presentation()
for text in ('Pilot approval plan.','Rollout budget.'):
 slide=presentation.slides.add_slide(presentation.slide_layouts[6])
 slide.shapes.add_textbox(Inches(.5),Inches(.5),Inches(8),Inches(2)).text=text
 slide.notes_slide.notes_text_frame.text='Initial speaker notes.'
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
  PRESENTER_CORE_DIR: path.join(root, "core"),
  PRESENTER_COPILOT_DEV_MODE: "1",
  PRESENTER_COPILOT_TEST_PROVIDER: "deterministic_fake",
  PRESENTER_COPILOT_TEST_DECISION: "deterministic_fake",
  PRESENTER_COPILOT_TEST_ASR: "deterministic_fake",
});
const fixtureRuntime = path.join(temporary, "fixture-provider");
await mkdir(fixtureRuntime);
const controlFile = path.join(fixtureRuntime, "control.json");
const enteredFile = path.join(fixtureRuntime, "entered.txt");
await writeFile(
  path.join(fixtureRuntime, "sitecustomize.py"),
  String.raw`
import json,time
from pathlib import Path
from presenter_core.providers.fake import DeterministicFakeReasoningProvider
from presenter_core.providers.models import ReasoningResult
original=DeterministicFakeReasoningProvider.generate
runtime=Path(__file__).parent
def generate(self,invocation):
 task=invocation.request.task_type
 if task=='presentation_rehearsal_objections':
  result=original(self,invocation)
  speech=json.loads(invocation.request.current_slide_summary)['recorded_speech']
  observations=[{'concern':label,'reason':'Fixture interpretation; unverified.',
   'concern_quotes':[{'utterance_id':speech[i]['utterance_id'],'quote':speech[i]['text']}],
   'answer_status':'not_observed','answer_quotes':[]}
   for i,label in ((0,'Fixture approval concern'),(1,'Fixture cost concern')) if i<len(speech)]
  return ReasoningResult(output={'observations':observations},latency_ms=result.latency_ms)
 if task=='presentation_rehearsal_objection_equivalence':
  control=runtime/'control.json'
  if control.exists() and json.loads(control.read_text()).get('hold'):
   (runtime/'entered.txt').write_text('entered')
   deadline=time.monotonic()+30
   while time.monotonic()<deadline and not json.loads(control.read_text()).get('release'):time.sleep(.05)
  result=original(self,invocation)
  output=json.loads(json.dumps(result.output))
  output['comparisons'][0]['relationship']='equivalent'
  output['comparisons'][0]['reason']='Fixture: both ask who approves the pilot.'
  if len(output['comparisons'])>1:
   output['comparisons'][1]['relationship']='distinct'
   output['comparisons'][1]['reason']='Fixture: approval versus cost.'
  return ReasoningResult(output=output,latency_ms=result.latency_ms)
 return original(self,invocation)
DeterministicFakeReasoningProvider.generate=generate
`,
);
env.PYTHONPATH = [fixtureRuntime, path.join(root, "core")].join(path.delimiter);
const errors = [];
const checks = [];
let app;
let page;
const control = (value) => writeFile(controlFile, JSON.stringify(value));
try {
  await control({ hold: false, release: false });
  app = await electron.launch({
    executablePath: require("electron"),
    args: [desktop, `--user-data-dir=${path.join(temporary, "browser")}`],
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
    .fill("Comparison acceptance");
  await page.keyboard.press("Enter");
  await page
    .getByRole("heading", { name: "Sources", exact: true })
    .first()
    .waitFor();
  await app.evaluate(({ dialog }, file) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [file],
    });
  }, fixture);
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("presentation");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  await page.getByRole("button", { name: /presentation\.pptx/ }).waitFor();
  const workspace = async () => {
    await page
      .getByRole("navigation", { name: "Project navigation", exact: true })
      .getByRole("button", { name: "Workspace", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Open preview", exact: true })
      .click();
    await page.getByText(/^Current · Revision \d+$/).waitFor();
  };
  await workspace();
  const ask = async (method, params) =>
    page.evaluate(
      async ({ method, params }) => {
        const r = await window.presenterCopilot.core.request(method, params);
        if (!r.ok)
          throw new Error(`${r.error.code ?? ""}: ${r.error.message}`.trim());
        return r.result;
      },
      { method, params },
    );
  const project = (await ask("project.list", {})).projects.find(
    (item) => item.name === "Comparison acceptance",
  );
  const source = (
    await ask("source.list", { project_id: project.id })
  ).sources.find((item) => item.original_name === "presentation.pptx");
  const revisions = await ask("presentation.workspace.list_revisions", {
    project_id: project.id,
    document_id: source.id,
  });
  const scope = {
    project_id: project.id,
    document_id: source.id,
    expected_revision_id: revisions.current_revision_id,
  };

  // One actual GUI Run; the second Run clones its ended session row.
  await page.getByRole("button", { name: "Rehearse", exact: true }).click();
  await page
    .getByLabel("Presentation tracking", { exact: true })
    .selectOption("manual");
  await page.getByRole("button", { name: "Start Run", exact: true }).click();
  await page.getByRole("button", { name: "Stop Run", exact: true }).click();
  await page
    .getByRole("heading", { name: "Run debrief", exact: true })
    .waitFor();
  const firstRun = (
    await ask("session.list", { project_id: project.id })
  ).sessions.find((item) => item.mode === "run").id;
  const database = path.join(
    temporary,
    "core",
    "projects",
    project.id,
    "project.db",
  );
  const sql = (code, ...args) =>
    execFileSync(python, ["-c", code, database, ...args], {
      cwd: root,
      windowsHide: true,
      stdio: "pipe",
    })
      .toString()
      .trim();
  const secondRun = sql(
    String.raw`
import sqlite3,sys,uuid
db=sqlite3.connect(sys.argv[1]);db.row_factory=sqlite3.Row
first=sys.argv[2]
db.execute('DELETE FROM run_debriefs WHERE session_id=?',(first,))
db.execute('DELETE FROM utterances WHERE session_id=?',(first,))
row=dict(db.execute('SELECT * FROM sessions WHERE id=?',(first,)).fetchone());fields=list(row)
second=str(uuid.uuid4())
clone=row|{'id':second,'started_at':'2099-10-09T12:00:00Z'}
db.execute(f"INSERT INTO sessions ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",[clone[k] for k in fields])
speech={first:[('unknown_audience','Who approves this pilot before launch?'),('unknown_audience','What will the rollout cost us?')],
 second:[('user','Which team signs off on the pilot?'),('unknown_audience','How long will onboarding take?')]}
for session,items in speech.items():
 for n,(actor,text) in enumerate(items):
  db.execute("INSERT INTO utterances (id,session_id,actor,text,created_at,start_ms,end_ms,asr_confidence,slide_ordinal,is_final) VALUES (?,?,?,?,'2026-10-08T10:00:00Z',?,?,NULL,1,1)",(str(uuid.uuid4()),session,actor,text,n*2000,n*2000+1500))
db.commit();print(second)
`,
    firstRun,
  );

  // Detection was accepted separately; here it runs through the actual job IPC.
  async function detect(session) {
    const slides = await ask(
      "presentation.workspace.list_rehearsal_review_slides",
      { ...scope, session_id: session },
    );
    const slide = slides.slides.find((item) => item.source_slide_number === 1);
    const prepared = await ask(
      "presentation.workspace.prepare_rehearsal_objections_review",
      { ...scope, session_id: session, slide_id: slide.slide_id, limit: 1 },
    );
    let job = await ask(
      "presentation.workspace.start_rehearsal_objections_analysis",
      {
        ...scope,
        session_id: session,
        slide_id: slide.slide_id,
        expected_context_sha256: prepared.context_sha256,
        expected_recording_sha256: prepared.recording_sha256,
        window_index: 0,
      },
    );
    while (!job.terminal) {
      await new Promise((resolve) => setTimeout(resolve, 200));
      job = await ask("presentation.workspace.poll_rehearsal_analysis", {
        ...scope,
        job_id: job.job_id,
      });
    }
    assert.equal(job.state, "completed", JSON.stringify(job));
    assert.equal(job.result.finding_ids.length, 2);
    return job.result;
  }
  const leftAnalysis = await detect(firstRun);
  const rightAnalysis = await detect(secondRun);
  checks.push(
    "Two distinct ended Runs each have a saved, audited two-candidate objection analysis",
  );

  await workspace();
  await page
    .getByRole("group", { name: "Slide studio panels", exact: true })
    .getByRole("button", { name: "Rehearsal", exact: true })
    .click();
  const panel = page.getByRole("region", {
    name: "Cross-Run objection comparison",
    exact: true,
  });
  await panel
    .getByRole("heading", {
      name: "Compare concerns across two Runs",
      exact: true,
    })
    .waitFor();
  await panel.getByText("0 saved comparisons for this deck.").waitFor();
  const first = panel.getByRole("group", { name: "First Run", exact: true });
  const second = panel.getByRole("group", { name: "Second Run", exact: true });
  async function pick(group, label, session, analysis, boxes) {
    const run = group.getByRole("combobox", {
      name: `${label} for comparison`,
      exact: true,
    });
    await run
      .locator(`option[value="${session}"]`)
      .waitFor({ state: "attached" });
    await run.selectOption(session);
    const saved = group.getByRole("combobox", {
      name: `${label} saved analysis`,
      exact: true,
    });
    await saved
      .locator(`option[value="${analysis}"]`)
      .waitFor({ state: "attached" });
    await saved.selectOption(analysis);
    for (const index of boxes)
      await group
        .getByRole("checkbox", {
          name: `${label} candidate ${index}`,
          exact: true,
        })
        .check();
  }
  await pick(first, "First Run", firstRun, leftAnalysis.analysis_id, [1, 2]);
  assert.equal(
    await second
      .getByRole("combobox", { name: "Second Run for comparison", exact: true })
      .locator(`option[value="${firstRun}"]`)
      .evaluate((option) => option.disabled),
    true,
  );
  await pick(second, "Second Run", secondRun, rightAnalysis.analysis_id, [1]);
  const compare = panel.getByRole("button", {
    name: "Compare selected concerns",
    exact: true,
  });
  assert.equal(await compare.isDisabled(), true);
  await panel
    .getByRole("button", { name: "Prepare comparison", exact: true })
    .click();
  await panel.getByText(/Prepared 2 × 1 pairs from/).waitFor();
  checks.push(
    "GUI selects candidates from two distinct Runs (same Run disabled on the other side) and prepares a fingerprinted 2x1 comparison before Start is enabled",
  );

  await compare.click();
  await panel.getByText(/Saved this comparison/).waitFor();
  const detail = panel.getByRole("region", {
    name: "Verified objection comparison",
    exact: true,
  });
  const pair1 = detail.getByRole("article", {
    name: "Compared pair 1",
    exact: true,
  });
  await pair1
    .getByRole("heading", {
      name: "Pair 1: Possibly the same underlying concern",
      exact: true,
    })
    .waitFor();
  await pair1
    .getByText("Unverified reason: Fixture: both ask who approves the pilot.")
    .waitFor();
  await pair1
    .getByText("Who approves this pilot before launch?", { exact: true })
    .waitFor();
  await pair1
    .getByText("Which team signs off on the pilot?", { exact: true })
    .waitFor();
  await detail
    .getByRole("article", { name: "Compared pair 2", exact: true })
    .getByRole("heading", { name: "Pair 2: Different concerns", exact: true })
    .waitFor();
  await panel.getByText("1 saved comparisons for this deck.").waitFor();
  const listed = await ask(
    "presentation.workspace.list_rehearsal_objection_comparisons",
    scope,
  );
  const comparisonId = listed.comparisons[0].comparison_id;
  const verified = await ask(
    "presentation.workspace.get_rehearsal_objection_comparison",
    { ...scope, comparison_id: comparisonId },
  );
  assert.deepEqual(
    verified.left_finding_ids,
    leftAnalysis.finding_ids.slice(0, 2),
  );
  assert.deepEqual(verified.right_finding_ids, [rightAnalysis.finding_ids[0]]);
  assert.equal(verified.interpretation_verified, false);
  assert.equal(verified.establishes_absence, false);
  checks.push(
    "Actual comparison job stores a verified 2x1 matrix referencing original candidate IDs; GUI shows unverified relationships/reasons separately from exact excerpts from both Runs",
  );

  const originals = detail.getByRole("article", {
    name: "Compared original candidate",
    exact: true,
  });
  await originals
    .first()
    .getByRole("button", { name: "Dismiss first run candidate", exact: true })
    .click();
  await originals
    .first()
    .getByText(/Original review state: rejected/)
    .waitFor();
  await originals
    .last()
    .getByText(/Original review state: unreviewed/)
    .waitFor();
  const leftOriginal = await ask(
    "presentation.workspace.get_rehearsal_objections_analysis",
    { ...scope, analysis_id: leftAnalysis.analysis_id },
  );
  const rightOriginal = await ask(
    "presentation.workspace.get_rehearsal_objections_analysis",
    { ...scope, analysis_id: rightAnalysis.analysis_id },
  );
  assert.deepEqual(
    leftOriginal.findings.map((item) => item.disposition),
    ["rejected", "unreviewed"],
  );
  assert.deepEqual(
    rightOriginal.findings.map((item) => item.disposition),
    ["unreviewed", "unreviewed"],
  );
  assert.equal(
    (
      await ask("presentation.workspace.list_revisions", {
        project_id: project.id,
        document_id: source.id,
      })
    ).current_revision_id,
    scope.expected_revision_id,
  );
  checks.push(
    "Dismissing one compared original candidate changes only that candidate's own review record; the equivalent counterpart and native revision stay unchanged",
  );

  // Defer delivery of a real verified comparison reply, then close the panel.
  await app.evaluate(
    (_electron, modulePath) => {
      const { CoreProcessClient } = process.mainModule.require(modulePath);
      const original = CoreProcessClient.prototype.request;
      globalThis.comparisonHold = true;
      globalThis.comparisonHeld = false;
      globalThis.comparisonRelease = false;
      globalThis.comparisonReturned = false;
      CoreProcessClient.prototype.request = async function (...args) {
        const result = await original.apply(this, args);
        if (
          args[0] ===
            "presentation.workspace.get_rehearsal_objection_comparison" &&
          globalThis.comparisonHold
        ) {
          globalThis.comparisonHeld = true;
          const deadline = Date.now() + 30000;
          while (!globalThis.comparisonRelease && Date.now() < deadline)
            await new Promise((resolve) => setTimeout(resolve, 30));
          globalThis.comparisonReturned = true;
        }
        return result;
      };
    },
    path.join(desktop, "dist", "main", "core-client.js"),
  );
  const waitMain = async (name) => {
    const until = Date.now() + 20000;
    while (!(await app.evaluate((_electron, key) => globalThis[key], name))) {
      assert.ok(Date.now() < until, `${name} was not reached`);
      await new Promise((resolve) => setTimeout(resolve, 30));
    }
  };
  await panel
    .getByRole("button", { name: "Review saved comparison", exact: true })
    .click();
  await waitMain("comparisonHeld");
  const studioButton = (name) =>
    page
      .getByRole("group", { name: "Slide studio panels", exact: true })
      .getByRole("button", { name, exact: true });
  await studioButton("Notes").click();
  await app.evaluate(() => {
    globalThis.comparisonHold = false;
    globalThis.comparisonRelease = true;
  });
  await waitMain("comparisonReturned");
  await studioButton("Rehearsal").click();
  await panel.getByText("1 saved comparisons for this deck.").waitFor();
  await page.waitForTimeout(500);
  assert.equal(
    await panel
      .getByRole("region", { name: "Verified objection comparison" })
      .count(),
    0,
    "A reply delivered after the panel closed must not reappear",
  );
  assert.equal(
    await panel.getByText(/Prepared 2 × 1 pairs/).count(),
    0,
    "Reopening starts from a clean selection",
  );
  assert.deepEqual(errors, []);
  checks.push(
    "A real comparison detail reply held past panel closure is discarded; reopening shows saved history without stale detail or selection",
  );

  // Hold a reply again, then change the deck revision through a real GUI edit.
  await app.evaluate(() => {
    globalThis.comparisonHold = true;
    globalThis.comparisonHeld = false;
    globalThis.comparisonRelease = false;
    globalThis.comparisonReturned = false;
  });
  await panel
    .getByRole("button", { name: "Review saved comparison", exact: true })
    .click();
  await waitMain("comparisonHeld");
  await studioButton("Notes").click();
  await page
    .getByRole("textbox", { name: "Speaker notes", exact: true })
    .fill("Revision change while a comparison reply is held.");
  await page
    .getByRole("button", { name: "Save speaker notes", exact: true })
    .click();
  await page
    .locator(".presentation-workspace")
    .getByText("Current · Revision 2", { exact: true })
    .waitFor();
  await app.evaluate(() => {
    globalThis.comparisonHold = false;
    globalThis.comparisonRelease = true;
  });
  await waitMain("comparisonReturned");
  const revisedHead = (
    await ask("presentation.workspace.list_revisions", {
      project_id: project.id,
      document_id: source.id,
    })
  ).current_revision_id;
  assert.notEqual(revisedHead, scope.expected_revision_id);
  scope.expected_revision_id = revisedHead;
  await studioButton("Rehearsal").click();
  await panel.getByText("1 saved comparisons for this deck.").waitFor();
  await page.waitForTimeout(500);
  assert.equal(
    await panel
      .getByRole("region", { name: "Verified objection comparison" })
      .count(),
    0,
    "A reply for the previous revision must not appear on the new revision",
  );
  await panel
    .getByRole("button", { name: "Review saved comparison", exact: true })
    .click();
  await panel
    .getByRole("region", { name: "Verified objection comparison" })
    .getByRole("heading", {
      name: "Pair 1: Possibly the same underlying concern",
      exact: true,
    })
    .waitFor();
  const onNewHead = await ask(
    "presentation.workspace.get_rehearsal_objection_comparison",
    { ...scope, comparison_id: comparisonId },
  );
  assert.equal(onNewHead.revision_id, revisedHead);
  assert.notEqual(onNewHead.baseline_revision_id, revisedHead);
  assert.equal(onNewHead.context_current, true);
  assert.deepEqual(errors, []);
  checks.push(
    "A real comparison reply held across a GUI native revision change is discarded; the saved comparison reopens verified on the new head with its original baseline",
  );
  await pick(first, "First Run", firstRun, leftAnalysis.analysis_id, [1, 2]);
  await pick(second, "Second Run", secondRun, rightAnalysis.analysis_id, [1]);

  // Held provider: Cancel during inference persists nothing.
  await control({ hold: true, release: false });
  await panel
    .getByRole("button", { name: "Prepare comparison", exact: true })
    .click();
  await panel.getByText(/Prepared 2 × 1 pairs from/).waitFor();
  await compare.click();
  const enteredDeadline = Date.now() + 15_000;
  while (Date.now() < enteredDeadline) {
    try {
      await readFile(enteredFile);
      break;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  await panel
    .getByRole("button", { name: "Cancel comparison", exact: true })
    .click();
  await control({ hold: true, release: true });
  await panel
    .getByText("Comparison cancelled. Nothing was saved.", { exact: true })
    .waitFor();
  await control({ hold: false, release: false });
  assert.equal(
    (
      await ask(
        "presentation.workspace.list_rehearsal_objection_comparisons",
        scope,
      )
    ).total,
    1,
  );
  checks.push(
    "Cancel during held comparison inference reports cancellation and stores no comparison",
  );

  // A late recording change on either Run blocks Start with recovery guidance.
  await panel
    .getByRole("button", { name: "Prepare comparison", exact: true })
    .click();
  await panel.getByText(/Prepared 2 × 1 pairs from/).waitFor();
  const lateUtterance = sql(
    String.raw`
import sqlite3,sys,uuid
db=sqlite3.connect(sys.argv[1]);identity=str(uuid.uuid4())
db.execute("INSERT INTO utterances (id,session_id,actor,text,created_at,start_ms,end_ms,asr_confidence,slide_ordinal,is_final) VALUES (?,?,'user','Late appended speech.','2026-10-08T10:00:00Z',9000,9500,NULL,1,1)",(identity,sys.argv[2]))
db.commit();print(identity)
`,
    secondRun,
  );
  await compare.click();
  await panel
    .getByRole("alert")
    .getByText(/REHEARSAL_CONTEXT_CHANGED/)
    .waitFor();
  assert.equal(await panel.getByText(/Prepared 2 × 1 pairs from/).count(), 0);
  assert.equal(await compare.isDisabled(), true);
  sql(
    String.raw`
import sqlite3,sys
db=sqlite3.connect(sys.argv[1]);db.execute('DELETE FROM utterances WHERE id=?',(sys.argv[2],));db.commit()
`,
    lateUtterance,
  );
  assert.equal(
    (
      await ask(
        "presentation.workspace.list_rehearsal_objection_comparisons",
        scope,
      )
    ).total,
    1,
  );
  checks.push(
    "A late recording change on the second Run rejects actual Start with structured REHEARSAL_CONTEXT_CHANGED guidance and stores nothing",
  );
  await page.screenshot({ path: path.join(output, "comparison.png") });

  // Deleting either Run removes comparisons that reference it, not the other Run's analysis.
  await ask("session.delete", {
    project_id: project.id,
    session_id: secondRun,
  });
  await workspace();
  await page
    .getByRole("group", { name: "Slide studio panels", exact: true })
    .getByRole("button", { name: "Rehearsal", exact: true })
    .click();
  await page
    .getByRole("region", {
      name: "Cross-Run objection comparison",
      exact: true,
    })
    .getByText("0 saved comparisons for this deck.")
    .waitFor();
  const kept = await ask(
    "presentation.workspace.get_rehearsal_objections_analysis",
    { ...scope, analysis_id: leftAnalysis.analysis_id },
  );
  assert.deepEqual(
    kept.findings.map((item) => item.disposition),
    ["rejected", "unreviewed"],
  );
  checks.push(
    "Deleting the second Run cascades its comparison while the first Run's original analysis and review state remain",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      {
        checks,
        errors,
        scope,
        firstRun,
        secondRun,
        comparisonId,
        boundary:
          "Actual Electron/Core/native PPTX; picker, recorded speech insertion and explicit fixture model adapter",
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ passed: checks.length, output }, null, 2));
} catch (error) {
  await writeFile(
    path.join(output, "failure-checks.json"),
    JSON.stringify({ checks, errors, error: error.message }, null, 2),
  );
  if (page)
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
  throw error;
} finally {
  await control({ hold: false, release: true }).catch(() => {});
  if (app) await app.close();
}
