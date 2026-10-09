/* global document, window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
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
  path.join(root, ".local", "rehearsal-semantic-coverage", "objection-gui");
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
for name,text,y in [('Other editable','Customer renewals remained stable.',4.5),('Basic metric','Revenue rose 20% during the pilot.',0.5),('Readonly metrics','Return on investment reached 24%.\n'+' '.join(f'Unique supporting observation {i}.' for i in range(210)),1.2)]:
 shape=slide.shapes.add_textbox(Inches(.5),Inches(y),Inches(9),Inches(3));shape.name=name;shape.text=text
 for p in shape.text_frame.paragraphs:p.font.size=Pt(8)
other=presentation.slides.add_slide(presentation.slide_layouts[6]);other.shapes.add_textbox(Inches(.5),Inches(.5),Inches(9),Inches(2)).text='Other slide statement.'
for number in range(3,27):
 other=presentation.slides.add_slide(presentation.slide_layouts[6])
 if number==26:other.shapes.add_shape(1,Inches(1),Inches(1),Inches(2),Inches(2))
 else:other.shapes.add_textbox(Inches(.5),Inches(.5),Inches(9),Inches(2)).text=f'Metric increased by {number}% on slide {number}.'
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
// Only the model adapter is replaced; IPC, audit, storage, jobs and native edits are actual Core.
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
from presenter_core.providers.models import ProviderHealth
original_health=DeterministicFakeReasoningProvider.health
def health(self):
 control=Path(__file__).parent/'control.json'
 mode=json.loads(control.read_text()).get('mode') if control.exists() else None
 self.locality='remote' if mode=='remote' else 'local'
 if mode=='unconfigured':
  return ProviderHealth(provider_id=self.id,locality=self.locality,model_id=self.model_id,status='unconfigured',configured=False,error_code='PROVIDER_UNCONFIGURED')
 return original_health(self)
DeterministicFakeReasoningProvider.health=health
original=DeterministicFakeReasoningProvider.generate
runtime=Path(__file__).parent
def generate(self,invocation):
 if invocation.request.task_type!='presentation_rehearsal_objections':return original(self,invocation)
 control=runtime/'control.json'
 if control.exists() and json.loads(control.read_text()).get('hold'):
  (runtime/'entered.txt').write_text('entered')
  deadline=time.monotonic()+30
  while time.monotonic()<deadline and not json.loads(control.read_text()).get('release'):time.sleep(.05)
 result=original(self,invocation)
 speech=json.loads(invocation.request.current_slide_summary)['recorded_speech']
 observations=[]
 if speech and not speech[0]['text'].startswith('Fixture plain narration'):
  for i,label in ((0,'Fixture approval concern'),(2,'Fixture budget concern')):
   if i>=len(speech):continue
   quote=speech[i]['text'].split(' Complete recorded context.')[0]
   answer=[{'utterance_id':speech[i+1]['utterance_id'],'quote':speech[i+1]['text']}] if i+1<len(speech) else []
   observations.append({'concern':label,'reason':'Fixture interpretation of this recorded window; unverified.',
    'concern_quotes':[{'utterance_id':speech[i]['utterance_id'],'quote':quote}],
    'answer_status':'addressed' if answer else 'not_observed','answer_quotes':answer})
 return ReasoningResult(output={'observations':observations},latency_ms=result.latency_ms)
DeterministicFakeReasoningProvider.generate=generate
`,
);
env.PYTHONPATH = [fixtureRuntime, path.join(root, "core")].join(path.delimiter);
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
  let scope = {
    project_id: baseline.scope.project_id,
    document_id: baseline.scope.document_id,
    expected_revision_id: baseline.scope.revision_id,
  };
  const studio = async (name) =>
    page
      .getByRole("group", { name: "Slide studio panels", exact: true })
      .getByRole("button", { name, exact: true })
      .click();
  await page.getByRole("button", { name: "Rehearse", exact: true }).click();
  await page
    .getByLabel("Presentation tracking", { exact: true })
    .selectOption("manual");
  await page.getByRole("button", { name: "Start Run", exact: true }).click();
  await page.getByRole("button", { name: "Stop Run", exact: true }).click();
  await page
    .getByRole("heading", { name: "Run debrief", exact: true })
    .waitFor();
  const originalSession = (
    await ask("session.list", { project_id: scope.project_id })
  ).sessions.find((item) => item.mode === "run").id;
  const database = path.join(
    temporary,
    "core",
    "projects",
    scope.project_id,
    "project.db",
  );
  execFileSync(
    path.join(root, "core", ".venv", "Scripts", "python.exe"),
    [
      "-c",
      String.raw`
import sqlite3,sys,uuid
connection=sqlite3.connect(sys.argv[1]);connection.row_factory=sqlite3.Row
session=sys.argv[2]
connection.execute('DELETE FROM run_debriefs WHERE session_id=?',(session,))
connection.execute('DELETE FROM utterances WHERE session_id=?',(session,))
speech=[
 ('unknown_audience','Why should we approve the pilot? '+('Complete recorded context. '*110)),
 ('user','We will review pilot outcomes before making the decision.'),
 ('audience_profile','What will the pilot cost?'),
 ('ai_coach','A possible recorded answer says we have a budget.'),
 *[('user',f'Fixture plain narration {i}.') for i in range(5)]
]
for number,(actor,text) in enumerate(speech):
 connection.execute("INSERT INTO utterances (id,session_id,actor,text,created_at,start_ms,end_ms,asr_confidence,slide_ordinal,is_final) VALUES (?,?,?,?,'2026-10-08T10:00:00Z',?,?,NULL,1,1)",(str(uuid.uuid4()),session,actor,text,number*2000,number*2000+1800))
row=dict(connection.execute('SELECT * FROM sessions WHERE id=?',(session,)).fetchone());fields=list(row)
for number in range(25):
 clone=row|{'id':str(uuid.uuid4()),'started_at':f'2099-10-09T12:{number:02d}:00Z'}
 connection.execute(f"INSERT INTO sessions ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",[clone[key] for key in fields])
connection.commit();connection.close()
`,
      database,
      originalSession,
    ],
    { cwd: root, windowsHide: true, stdio: "pipe" },
  );
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  await studio("Text");
  const targets = page.getByRole("combobox", {
    name: "Text on this slide",
    exact: true,
  });
  await targets
    .getByRole("option", { name: /Customer renewals/ })
    .waitFor({ state: "attached" });
  const unrelated = await targets.locator("option").allTextContents();
  const unrelatedIndex = unrelated.findIndex((text) =>
    text.includes("Customer renewals"),
  );
  assert.ok(unrelatedIndex >= 0, JSON.stringify(unrelated));
  await targets.selectOption({ index: unrelatedIndex });
  await studio("Rehearsal");
  const objection = page.getByRole("region", {
    name: "Recorded objection review",
    exact: true,
  });
  const selectRun = objection.getByRole("combobox", {
    name: "Objection recorded Run",
    exact: true,
  });
  const selectSlide = objection.getByRole("combobox", {
    name: "Objection original slide",
    exact: true,
  });
  const selectWindow = objection.getByRole("combobox", {
    name: "Objection speech window",
    exact: true,
  });
  const detail = objection.getByRole("region", {
    name: "Verified objection analysis",
    exact: true,
  });
  const detect = objection.getByRole("button", {
    name: "Detect concerns in selected window",
    exact: true,
  });
  await objection
    .getByText("26 ended Runs for this deck. A debrief is not required.", {
      exact: true,
    })
    .waitFor();
  const emptyRun = await selectRun
    .locator("option")
    .nth(1)
    .getAttribute("value");
  await selectRun.selectOption(emptyRun);
  const originalSlides = await ask(
    "presentation.workspace.list_rehearsal_review_slides",
    { ...scope, session_id: originalSession },
  );
  const firstSlide = originalSlides.slides[0].slide_id;
  await selectSlide.selectOption(firstSlide);
  await objection.getByText(/No recorded speech window is available/).waitFor();
  assert.equal(await detect.count(), 0);
  await objection
    .getByRole("button", { name: "Next original slides", exact: true })
    .click();
  const lastSlides = await ask(
    "presentation.workspace.list_rehearsal_review_slides",
    { ...scope, session_id: originalSession, offset: 20 },
  );
  const graphic = lastSlides.slides.find(
    (slide) => slide.source_slide_number === 26,
  );
  assert.ok(graphic);
  await selectSlide.selectOption(graphic.slide_id);
  await objection.getByText(/No recorded speech window is available/).waitFor();
  checks.push(
    "Ended Runs without debriefs and original slide paging work without an editable text object; empty speech does not enable detection",
  );

  async function chooseOriginalRun() {
    await objection
      .getByRole("button", { name: "Next objection Runs", exact: true })
      .click();
    await selectRun
      .locator(`option[value="${originalSession}"]`)
      .waitFor({ state: "attached" });
    await selectRun.selectOption(originalSession);
  }
  await chooseOriginalRun();
  await selectSlide.selectOption(firstSlide);
  await objection
    .getByText(
      /9 recorded utterances on original slide 1 across 3 bounded windows/,
    )
    .waitFor();
  const fullSpeech = await objection
    .locator("blockquote")
    .first()
    .textContent();
  assert.ok(
    fullSpeech.length > 2000 &&
      fullSpeech.endsWith("Complete recorded context. "),
  );
  assert.equal(await selectWindow.inputValue(), "");
  assert.equal(await detect.isDisabled(), true);
  await selectWindow.selectOption("0");
  await detect.click();
  await objection
    .getByText(/Saved this window analysis with 2 concern candidates/)
    .waitFor();
  const saved = (
    await ask("presentation.workspace.list_rehearsal_objections_analyses", {
      ...scope,
      session_id: originalSession,
    })
  ).analyses[0];
  await objection
    .getByRole("button", {
      name: "Review saved objection analysis",
      exact: true,
    })
    .click();
  const candidate = detail.getByRole("article", {
    name: "Recorded concern candidate 1",
    exact: true,
  });
  const sibling = detail.getByRole("article", {
    name: "Recorded concern candidate 2",
    exact: true,
  });
  await candidate
    .getByText("Why should we approve the pilot?", { exact: true })
    .waitFor();
  await candidate
    .getByText("We will review pilot outcomes before making the decision.", {
      exact: true,
    })
    .waitFor();
  await candidate
    .getByRole("button", { name: "Dismiss concern candidate", exact: true })
    .click();
  await candidate
    .getByText("Review state: rejected", { exact: true })
    .waitFor();
  await sibling
    .getByText("Review state: unreviewed", { exact: true })
    .waitFor();
  await candidate
    .getByRole("button", { name: "Reopen concern candidate", exact: true })
    .click();
  await candidate
    .getByText("Review state: unreviewed", { exact: true })
    .waitFor();
  checks.push(
    "Complete speech is displayed before explicit window selection; actual audited detection produces two independently reviewed candidates with separate concern and answer excerpts",
  );

  await candidate
    .getByRole("button", { name: "Prepare concern in notes", exact: true })
    .click();
  const notes = page.getByRole("textbox", {
    name: "Speaker notes",
    exact: true,
  });
  assert.equal(
    await notes.inputValue(),
    "Initial private speaking reminder.\n\nWhy should we approve the pilot?",
  );
  assert.equal((await context()).sha256, baseline.sha256);
  await page
    .getByRole("button", { name: "Save speaker notes", exact: true })
    .click();
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  scope = {
    ...scope,
    expected_revision_id: (await context()).scope.revision_id,
  };
  let verified = await ask(
    "presentation.workspace.get_rehearsal_objections_analysis",
    { ...scope, analysis_id: saved.analysis_id },
  );
  assert.deepEqual(
    verified.findings.map((item) => item.disposition),
    ["applied", "unreviewed"],
  );
  checks.push(
    "GUI notes preparation preserves private notes and appends only the exact concern; explicit native Save creates a revision and applies only that candidate",
  );

  await studio("Rehearsal");
  await chooseOriginalRun();
  await objection
    .getByRole("button", {
      name: "Review saved objection analysis",
      exact: true,
    })
    .click();
  await sibling
    .getByRole("button", {
      name: "Suggest selected text from concern",
      exact: true,
    })
    .click();
  const beforeRewrite = await context();
  await page
    .getByRole("button", { name: "Suggest rewrite", exact: true })
    .click();
  const suggestion = page.getByRole("group", {
    name: "Review rewrite suggestion",
    exact: true,
  });
  await suggestion.waitFor();
  assert.equal((await context()).sha256, beforeRewrite.sha256);
  await suggestion
    .getByRole("button", { name: "Use suggestion in editor", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Replacement text", exact: true })
    .fill("User reviewed pilot budget before approval.");
  await page
    .getByRole("button", { name: "Preview replacement", exact: true })
    .click();
  await page
    .getByRole("img", { name: "Text edit preview on slide 1", exact: true })
    .waitFor();
  const warning = page.locator(".pw-mock-edit .pw-layout-warning");
  if (await warning.count()) await warning.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Save revision", exact: true })
    .click();
  await page.getByText("Current · Revision 3", { exact: true }).waitFor();
  scope = {
    ...scope,
    expected_revision_id: (await context()).scope.revision_id,
  };
  verified = await ask(
    "presentation.workspace.get_rehearsal_objections_analysis",
    { ...scope, analysis_id: saved.analysis_id },
  );
  assert.deepEqual(
    verified.findings.map((item) => item.disposition),
    ["applied", "applied"],
  );
  checks.push(
    "Explicit current text target supports separate rewrite review, actual native Preview and Save; sibling candidates retain separate applied revisions",
  );

  await studio("Rehearsal");
  await chooseOriginalRun();
  await selectSlide.selectOption(firstSlide);
  await selectWindow.selectOption("0");
  await writeFile(controlFile, JSON.stringify({ hold: true, release: false }));
  await detect.click();
  const heldDeadline = Date.now() + 15000;
  while (Date.now() < heldDeadline) {
    try {
      if ((await readFile(enteredFile, "utf8")) === "entered") break;
    } catch {
      /* Adapter has not entered yet. */
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.equal(await readFile(enteredFile, "utf8"), "entered");
  await objection
    .getByRole("button", { name: "Cancel objection analysis", exact: true })
    .click();
  await objection
    .getByText("Cancellation requested; waiting for the worker to finish.", {
      exact: true,
    })
    .waitFor();
  await writeFile(controlFile, JSON.stringify({ hold: false, release: true }));
  await objection
    .getByText("Analysis cancelled. No window result was saved.", {
      exact: true,
    })
    .waitFor();
  assert.equal(
    (
      await ask("presentation.workspace.list_rehearsal_objections_analyses", {
        ...scope,
        session_id: originalSession,
      })
    ).total,
    1,
  );
  checks.push(
    "GUI cancellation is accepted while an actual provider worker is held; terminal cancellation persists no analysis or candidate",
  );

  await objection
    .getByRole("button", { name: "Next objection window", exact: true })
    .click();
  assert.equal(await selectWindow.inputValue(), "");
  await selectWindow.selectOption("1");
  await detect.click();
  await objection
    .getByText(/Saved this window analysis with 0 concern candidates/)
    .waitFor();
  await objection
    .getByRole("button", {
      name: "Review saved objection analysis",
      exact: true,
    })
    .first()
    .click();
  await detail
    .getByText(/No concern candidate was returned for this window/)
    .waitFor();
  assert.equal(
    await detail
      .getByRole("button", { name: "Prepare concern in notes", exact: true })
      .count(),
    0,
  );
  checks.push(
    "Window paging requires fresh explicit selection and empty analyses stay durable without whole-Run absence claims or adoption controls",
  );

  const prepared = await ask(
    "presentation.workspace.prepare_rehearsal_objections_review",
    {
      ...scope,
      session_id: originalSession,
      slide_id: firstSlide,
      offset: 1,
      limit: 1,
    },
  );
  for (let index = 0; index < 19; index++) {
    let status = await ask(
      "presentation.workspace.start_rehearsal_objections_analysis",
      {
        ...scope,
        session_id: originalSession,
        slide_id: firstSlide,
        expected_context_sha256: prepared.context_sha256,
        expected_recording_sha256: prepared.recording_sha256,
        window_index: 1,
      },
    );
    while (!status.terminal) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      status = await ask("presentation.workspace.poll_rehearsal_analysis", {
        ...scope,
        job_id: status.job_id,
      });
    }
    assert.equal(status.state, "completed");
  }
  await objection
    .getByRole("button", {
      name: "Refresh saved objection analyses",
      exact: true,
    })
    .click();
  await objection.getByText(/21 saved analyses/).waitFor();
  await objection
    .getByRole("button", { name: "Next objection analyses", exact: true })
    .click();
  await objection
    .getByRole("button", {
      name: "Review saved objection analysis",
      exact: true,
    })
    .nth(1)
    .waitFor({ state: "detached" });
  assert.equal(
    await objection
      .getByRole("button", {
        name: "Review saved objection analysis",
        exact: true,
      })
      .count(),
    1,
  );
  await objection
    .getByRole("button", {
      name: "Review saved objection analysis",
      exact: true,
    })
    .click();
  await candidate.getByText("Review state: applied", { exact: true }).waitFor();
  checks.push(
    "GUI history pages beyond twenty retain empty analyses and independently applied original candidates",
  );

  await app.evaluate(({ BrowserWindow }) => {
    const main = BrowserWindow.getAllWindows().find((window) =>
      window.webContents.getURL().endsWith("/renderer/index.html"),
    );
    main.setSize(720, 520);
  });
  await page.waitForFunction(
    () => window.innerWidth <= 720 && window.innerHeight <= 520,
  );
  await objection
    .getByRole("heading", {
      name: "Review possible concerns and answers",
      exact: true,
    })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, "objection-small.png") });
  const overflow = await objection.evaluate((element) => ({
    scroll: element.scrollWidth,
    width: element.clientWidth,
    page: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
    height: window.innerHeight,
  }));
  assert.ok(
    overflow.scroll <= overflow.width + 2 &&
      overflow.page <= overflow.viewport + 2,
    JSON.stringify(overflow),
  );
  assert.deepEqual(errors, []);
  checks.push(
    "Actual constrained-window objection controls and full speech remain contained with no renderer errors",
  );

  // Close both actual processes; retain the same isolated project and browser data.
  const beforeRestart = await context();
  const beforeRestartDetail = await ask(
    "presentation.workspace.get_rehearsal_objections_analysis",
    { ...scope, analysis_id: saved.analysis_id },
  );
  await app.close();
  app = undefined;
  page = undefined;
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
  const restartDeadline = Date.now() + 30_000;
  while (!page && Date.now() < restartDeadline) {
    page = app
      .windows()
      .find((candidate) => candidate.url().endsWith("/renderer/index.html"));
    if (!page) await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(page);
  page.setDefaultTimeout(30_000);
  page.on("pageerror", (error) => errors.push(error.message));
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  assert.equal(await page.getByRole("dialog").count(), 0);
  await page
    .getByRole("button", {
      name: "Native appearance acceptance",
      exact: true,
    })
    .click();
  await page
    .getByRole("navigation", {
      name: "Project navigation",
      exact: true,
    })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page.getByText("Current · Revision 3", { exact: true }).waitFor();
  assert.deepEqual(await context(), beforeRestart);
  await studio("Rehearsal");
  const restarted = page.getByRole("region", {
    name: "Recorded objection review",
    exact: true,
  });
  const restartedRun = restarted.getByRole("combobox", {
    name: "Objection recorded Run",
    exact: true,
  });
  async function selectRestartedRun() {
    await restarted
      .getByText("26 ended Runs for this deck. A debrief is not required.", {
        exact: true,
      })
      .waitFor();
    await restarted
      .getByRole("button", {
        name: "Next objection Runs",
        exact: true,
      })
      .click();
    await restartedRun
      .locator(`option[value="${originalSession}"]`)
      .waitFor({ state: "attached" });
    await restartedRun.selectOption(originalSession);
    await restarted.getByText(/21 saved analyses/).waitFor();
    await restarted
      .getByRole("button", {
        name: "Next objection analyses",
        exact: true,
      })
      .click();
    await restarted
      .getByRole("button", {
        name: "Review saved objection analysis",
        exact: true,
      })
      .nth(1)
      .waitFor({ state: "detached" });
  }
  await selectRestartedRun();
  const restartedReview = restarted.getByRole("button", {
    name: "Review saved objection analysis",
    exact: true,
  });
  await restartedReview.click();
  const restartedDetail = restarted.getByRole("region", {
    name: "Verified objection analysis",
    exact: true,
  });
  for (let index = 1; index <= 2; index++) {
    const item = restartedDetail.getByRole("article", {
      name: `Recorded concern candidate ${index}`,
      exact: true,
    });
    await item.getByText("Review state: applied", { exact: true }).waitFor();
    assert.equal(
      await item
        .getByRole("button", {
          name: "Prepare concern in notes",
          exact: true,
        })
        .isDisabled(),
      true,
    );
    assert.equal(
      await item
        .getByRole("button", {
          name: "Reopen concern candidate",
          exact: true,
        })
        .count(),
      0,
    );
  }
  assert.deepEqual(
    await ask("presentation.workspace.get_rehearsal_objections_analysis", {
      ...scope,
      analysis_id: saved.analysis_id,
    }),
    beforeRestartDetail,
  );
  checks.push(
    "Full Electron/Core restart retains original Run, 21 saved analyses, both independently applied candidate identities and native revision without replaying adoption",
  );

  // Defer delivery of a verified real Core response, not its contents or storage.
  await app.evaluate(
    (_electron, modulePath) => {
      const { CoreProcessClient } = process.mainModule.require(modulePath);
      const original = CoreProcessClient.prototype.request;
      globalThis.objectionDetailHold = true;
      globalThis.objectionDetailHeld = false;
      globalThis.objectionDetailRelease = false;
      globalThis.objectionDetailReturned = false;
      globalThis.objectionStartHold = false;
      globalThis.objectionStartHeld = false;
      globalThis.objectionStartRelease = true;
      globalThis.objectionStartJob = null;
      globalThis.objectionCancelReplies = [];
      CoreProcessClient.prototype.request = async function (...args) {
        const result = await original.apply(this, args);
        if (
          args[0] ===
            "presentation.workspace.get_rehearsal_objections_analysis" &&
          globalThis.objectionDetailHold
        ) {
          globalThis.objectionDetailHeld = true;
          const deadline = Date.now() + 30000;
          while (!globalThis.objectionDetailRelease && Date.now() < deadline)
            await new Promise((resolve) => setTimeout(resolve, 30));
          globalThis.objectionDetailReturned = true;
        }
        if (args[0] === "presentation.workspace.cancel_rehearsal_analysis")
          globalThis.objectionCancelReplies.push(result);
        if (
          args[0] ===
            "presentation.workspace.start_rehearsal_objections_analysis" &&
          globalThis.objectionStartHold
        ) {
          globalThis.objectionStartJob = result;
          globalThis.objectionStartHeld = true;
          const deadline = Date.now() + 30000;
          while (!globalThis.objectionStartRelease && Date.now() < deadline)
            await new Promise((resolve) => setTimeout(resolve, 30));
        }
        return result;
      };
    },
    path.join(desktop, "dist", "main", "core-client.js"),
  );
  await restartedReview.click();
  const detailDeadline = Date.now() + 20000;
  while (
    !(await app.evaluate(() => globalThis.objectionDetailHeld)) &&
    Date.now() < detailDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(await app.evaluate(() => globalThis.objectionDetailHeld), true);
  await studio("Notes");
  await app.evaluate(() => {
    globalThis.objectionDetailHold = false;
    globalThis.objectionDetailRelease = true;
  });
  const returnedDeadline = Date.now() + 20000;
  while (
    !(await app.evaluate(() => globalThis.objectionDetailReturned)) &&
    Date.now() < returnedDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(
    await app.evaluate(() => globalThis.objectionDetailReturned),
    true,
  );
  await studio("Rehearsal");
  await restarted
    .getByText("26 ended Runs for this deck. A debrief is not required.", {
      exact: true,
    })
    .waitFor();
  assert.equal(await restartedDetail.count(), 0);
  assert.equal(await restartedRun.inputValue(), "");
  assert.deepEqual(await context(), beforeRestart);
  assert.deepEqual(
    await ask("presentation.workspace.get_rehearsal_objections_analysis", {
      ...scope,
      analysis_id: saved.analysis_id,
    }),
    beforeRestartDetail,
  );
  checks.push(
    "A held actual detail reply released after panel closure cannot restore old candidates or adoption controls; native revision and review records remain unchanged",
  );
  assert.deepEqual(errors, []);

  await selectRestartedRun();
  await restarted
    .getByRole("combobox", { name: "Objection original slide", exact: true })
    .selectOption(firstSlide);
  await restarted
    .getByRole("combobox", { name: "Objection speech window", exact: true })
    .selectOption("0");
  const savedTotal = async () =>
    (
      await ask("presentation.workspace.list_rehearsal_objections_analyses", {
        ...scope,
        session_id: originalSession,
      })
    ).total;
  async function holdStart() {
    await app.evaluate(() => {
      globalThis.objectionStartHold = true;
      globalThis.objectionStartHeld = false;
      globalThis.objectionStartRelease = false;
    });
    await restarted
      .getByRole("button", {
        name: "Detect concerns in selected window",
        exact: true,
      })
      .click();
    const deadline = Date.now() + 20000;
    while (
      !(await app.evaluate(() => globalThis.objectionStartHeld)) &&
      Date.now() < deadline
    )
      await new Promise((resolve) => setTimeout(resolve, 30));
    assert.equal(await app.evaluate(() => globalThis.objectionStartHeld), true);
  }
  const releaseStart = () =>
    app.evaluate(() => {
      globalThis.objectionStartHold = false;
      globalThis.objectionStartRelease = true;
    });
  async function waitCancellation(count) {
    const deadline = Date.now() + 20000;
    while (
      (await app.evaluate(() => globalThis.objectionCancelReplies.length)) <
        count &&
      Date.now() < deadline
    )
      await new Promise((resolve) => setTimeout(resolve, 30));
    const replies = await app.evaluate(() => globalThis.objectionCancelReplies);
    assert.equal(replies.length, count);
    return replies[count - 1];
  }
  async function waitTerminal() {
    const job = await app.evaluate(() => globalThis.objectionStartJob);
    assert.ok(job?.job_id);
    let status;
    const deadline = Date.now() + 20000;
    do {
      status = await ask("presentation.workspace.poll_rehearsal_analysis", {
        ...scope,
        job_id: job.job_id,
      });
      if (!status.terminal)
        await new Promise((resolve) => setTimeout(resolve, 50));
    } while (!status.terminal && Date.now() < deadline);
    assert.equal(status.terminal, true);
    return status;
  }
  // Prove completion independently before clicking pending Cancel: it must be too late.
  await holdStart();
  assert.equal((await waitTerminal()).state, "completed");
  assert.equal(await savedTotal(), 22);
  await restarted
    .getByRole("button", { name: "Cancel objection analysis", exact: true })
    .click();
  await restarted
    .getByText(
      "Cancellation requested. Waiting for analysis to start so it can be cancelled.",
      { exact: true },
    )
    .waitFor();
  await releaseStart();
  assert.equal((await waitCancellation(1)).cancellation_accepted, false);
  await restarted
    .getByText(
      "Cancellation arrived after storage began. The saved window remains available for review.",
      { exact: true },
    )
    .waitFor();
  await restarted.getByText(/22 saved analyses/).waitFor();
  assert.deepEqual(await context(), beforeRestart);
  checks.push(
    "Pending Start offers Cancel; independently completed storage makes cancellation truthfully too late and preserves the saved analysis without native edits",
  );

  // Direct pending Cancel must also win before the actual persistence boundary.
  await writeFile(enteredFile, "");
  await writeFile(controlFile, JSON.stringify({ hold: true, release: false }));
  await holdStart();
  const pendingEnteredDeadline = Date.now() + 15000;
  while (
    (await readFile(enteredFile, "utf8")) !== "entered" &&
    Date.now() < pendingEnteredDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(await readFile(enteredFile, "utf8"), "entered");
  await restarted
    .getByRole("button", { name: "Cancel objection analysis", exact: true })
    .click();
  await restarted
    .getByText(
      "Cancellation requested. Waiting for analysis to start so it can be cancelled.",
      { exact: true },
    )
    .waitFor();
  await releaseStart();
  assert.equal((await waitCancellation(2)).cancellation_accepted, true);
  await writeFile(controlFile, JSON.stringify({ hold: false, release: true }));
  assert.equal((await waitTerminal()).state, "cancelled");
  await restarted
    .getByText("Analysis cancelled. No window result was saved.", {
      exact: true,
    })
    .waitFor();
  assert.equal(await savedTotal(), 22);
  assert.deepEqual(await context(), beforeRestart);
  checks.push(
    "Direct Cancel during held Start records intent, cancels the actual owned worker after ID delivery and reports terminal cancellation without persisting an analysis",
  );

  // A hidden panel must cancel its captured pending Start after the ID is delivered.
  await writeFile(enteredFile, "");
  await writeFile(controlFile, JSON.stringify({ hold: true, release: false }));
  await holdStart();
  const enteredDeadline = Date.now() + 15000;
  while (
    (await readFile(enteredFile, "utf8")) !== "entered" &&
    Date.now() < enteredDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(await readFile(enteredFile, "utf8"), "entered");
  await studio("Notes");
  await releaseStart();
  assert.equal((await waitCancellation(3)).cancellation_accepted, true);
  await writeFile(controlFile, JSON.stringify({ hold: false, release: true }));
  assert.equal((await waitTerminal()).state, "cancelled");
  assert.equal(await savedTotal(), 22);
  await studio("Rehearsal");
  await restarted
    .getByText("26 ended Runs for this deck. A debrief is not required.", {
      exact: true,
    })
    .waitFor();
  assert.equal(await restartedRun.inputValue(), "");
  assert.equal(await restartedDetail.count(), 0);
  assert.equal(await restarted.getByText(/Objection analysis:/).count(), 0);
  assert.deepEqual(await context(), beforeRestart);
  assert.deepEqual(
    await ask("presentation.workspace.get_rehearsal_objections_analysis", {
      ...scope,
      analysis_id: saved.analysis_id,
    }),
    beforeRestartDetail,
  );
  checks.push(
    "Panel closure during held Start cancels the original owned job after ID delivery; actual worker cancels with no new analysis and no stale UI/native review mutation",
  );
  assert.deepEqual(errors, []);

  // Only provider readiness/locality are fixtures; actual policy rejects the jobs.
  const projectPolicy = async () => {
    const project = (await ask("project.list", {})).projects.find(
      (item) => item.id === scope.project_id,
    );
    return {
      privacy: project.privacy_mode,
      acknowledged: project.remote_reasoning_acknowledged,
    };
  };
  const beforeFailurePolicy = await projectPolicy();
  assert.deepEqual(beforeFailurePolicy, {
    privacy: "local_only",
    acknowledged: false,
  });
  await restarted
    .getByRole("button", { name: "Next objection Runs", exact: true })
    .click();
  await restartedRun
    .locator(`option[value="${originalSession}"]`)
    .waitFor({ state: "attached" });
  await restartedRun.selectOption(originalSession);
  await restarted.getByText(/22 saved analyses/).waitFor();
  await restarted
    .getByRole("combobox", { name: "Objection original slide", exact: true })
    .selectOption(firstSlide);
  await restarted
    .getByRole("combobox", { name: "Objection speech window", exact: true })
    .selectOption("0");
  const restartedDetect = restarted.getByRole("button", {
    name: "Detect concerns in selected window",
    exact: true,
  });
  await writeFile(controlFile, JSON.stringify({ mode: "unconfigured" }));
  await restartedDetect.click();
  await restarted
    .getByRole("alert")
    .filter({ hasText: "PROVIDER_UNCONFIGURED" })
    .waitFor();
  assert.match(
    await restarted.getByRole("alert").innerText(),
    /Open Setup & settings and configure a ready reasoning provider/,
  );
  assert.equal(await savedTotal(), 22);
  await writeFile(controlFile, JSON.stringify({ mode: "remote" }));
  await restartedDetect.click();
  await restarted
    .getByRole("alert")
    .filter({ hasText: "PRIVACY_LOCAL_ONLY_REMOTE_BLOCKED" })
    .waitFor();
  assert.match(
    await restarted.getByRole("alert").innerText(),
    /This project is Local Only. Choose a local reasoning provider/,
  );
  assert.equal(await savedTotal(), 22);
  assert.deepEqual(await context(), beforeRestart);
  assert.deepEqual(await projectPolicy(), beforeFailurePolicy);
  checks.push(
    "Actual failed jobs expose readiness and Local Only recovery guidance without changing privacy, persisting analyses or modifying native slides",
  );

  async function resetFailureSelection() {
    await studio("Notes");
    await studio("Rehearsal");
    await restarted
      .getByText("26 ended Runs for this deck. A debrief is not required.", {
        exact: true,
      })
      .waitFor();
    await restarted
      .getByRole("button", { name: "Next objection Runs", exact: true })
      .click();
    await restartedRun
      .locator(`option[value="${originalSession}"]`)
      .waitFor({ state: "attached" });
    await restartedRun.selectOption(originalSession);
    await restarted.getByText(/22 saved analyses/).waitFor();
    await restarted
      .getByRole("combobox", { name: "Objection original slide", exact: true })
      .selectOption(firstSlide);
    await restarted
      .getByRole("combobox", { name: "Objection speech window", exact: true })
      .selectOption("0");
  }
  // Explicit disposable-project policy change, without acknowledging remote use.
  await ask("project.update_settings", {
    project_id: scope.project_id,
    privacy_mode: "selected_context_cloud",
  });
  try {
    await resetFailureSelection();
    await restartedDetect.click();
    await restarted
      .getByRole("alert")
      .filter({ hasText: "PRIVACY_REMOTE_ACK_REQUIRED" })
      .waitFor();
    assert.match(
      await restarted.getByRole("alert").innerText(),
      /Review remote reasoning acknowledgement in Project settings/,
    );
    assert.deepEqual(await projectPolicy(), {
      privacy: "selected_context_cloud",
      acknowledged: false,
    });
    assert.equal(await savedTotal(), 22);
    assert.deepEqual(await context(), beforeRestart);
  } finally {
    await ask("project.update_settings", {
      project_id: scope.project_id,
      privacy_mode: "local_only",
    });
  }
  await resetFailureSelection();
  assert.deepEqual(await projectPolicy(), beforeFailurePolicy);
  checks.push(
    "Actual missing remote acknowledgement blocks analysis with Project settings guidance; explicit fixture privacy selection does not acknowledge remote use or persist a result",
  );

  await writeFile(controlFile, JSON.stringify({ mode: "local" }));
  const python = path.join(root, "core", ".venv", "Scripts", "python.exe");
  const changedUtterance = JSON.parse(
    execFileSync(
      python,
      [
        "-c",
        String.raw`
import json,sqlite3,sys
c=sqlite3.connect(sys.argv[1])
row=c.execute('SELECT id,text FROM utterances WHERE session_id=? AND start_ms=0',(sys.argv[2],)).fetchone()
assert row
c.execute('UPDATE utterances SET text=? WHERE id=?',(row[1]+' Late fixture recording change.',row[0]));c.commit();c.close()
print(json.dumps({'id':row[0],'text':row[1]}))
`,
        database,
        originalSession,
      ],
      { cwd: root, windowsHide: true, encoding: "utf8" },
    ),
  );
  try {
    await restartedDetect.click();
    await restarted
      .getByRole("alert")
      .filter({ hasText: "REHEARSAL_CONTEXT_CHANGED" })
      .waitFor();
    assert.match(
      await restarted.getByRole("alert").innerText(),
      /prepare the updated recording before retrying/,
    );
    assert.equal(await savedTotal(), 22);
    assert.equal(
      await restarted
        .getByRole("button", { name: "Cancel objection analysis", exact: true })
        .count(),
      0,
    );
  } finally {
    execFileSync(
      python,
      [
        "-c",
        String.raw`
import sqlite3,sys
c=sqlite3.connect(sys.argv[1]);c.execute('UPDATE utterances SET text=? WHERE id=?',(sys.argv[3],sys.argv[2]));c.commit();c.close()
`,
        database,
        changedUtterance.id,
        changedUtterance.text,
      ],
      { cwd: root, windowsHide: true, stdio: "pipe" },
    );
  }
  assert.deepEqual(await context(), beforeRestart);
  assert.deepEqual(
    await ask("presentation.workspace.get_rehearsal_objections_analysis", {
      ...scope,
      analysis_id: saved.analysis_id,
    }),
    beforeRestartDetail,
  );
  checks.push(
    "Late recording mutation rejects real Start before allocating a job; structured RPC error retains code and fresh-preparation guidance without native edits or persistence",
  );
  await restartedDetect.click();
  await restarted
    .getByText(/Saved this window analysis with 2 concern candidates/)
    .waitFor();
  await restarted.getByText(/23 saved analyses/).waitFor();
  assert.equal(await savedTotal(), 23);
  assert.deepEqual(await context(), beforeRestart);
  assert.deepEqual(await projectPolicy(), beforeFailurePolicy);
  assert.equal(await restarted.getByRole("alert").count(), 0);
  checks.push(
    "Explicit retry after fixture provider/recording recovery succeeds through actual audited detection without automatically editing the deck",
  );
  assert.deepEqual(errors, []);

  const recent = (
    await ask("presentation.workspace.list_rehearsal_objections_analyses", {
      ...scope,
      session_id: originalSession,
    })
  ).analyses[0];
  const recentDetail = () =>
    ask("presentation.workspace.get_rehearsal_objections_analysis", {
      ...scope,
      analysis_id: recent.analysis_id,
    });
  const initialRecent = await recentDetail();
  const recentCandidate = restartedDetail.getByRole("article", {
    name: "Recorded concern candidate 1",
    exact: true,
  });
  const recentSibling = restartedDetail.getByRole("article", {
    name: "Recorded concern candidate 2",
    exact: true,
  });
  const firstHistoryReview = restarted
    .getByRole("button", {
      name: "Review saved objection analysis",
      exact: true,
    })
    .first();
  await firstHistoryReview.click();
  await recentCandidate
    .getByText("Review state: unreviewed", { exact: true })
    .waitFor();
  assert.equal(
    await recentCandidate
      .getByRole("button", {
        name: "Prepare concern in notes",
        exact: true,
      })
      .isDisabled(),
    false,
  );
  execFileSync(
    python,
    [
      "-c",
      String.raw`
import sqlite3,sys
c=sqlite3.connect(sys.argv[1]);c.execute('UPDATE utterances SET text=? WHERE id=?',(sys.argv[3]+' Historical fixture recording change.',sys.argv[2]));c.commit();c.close()
`,
      database,
      changedUtterance.id,
      changedUtterance.text,
    ],
    { cwd: root, windowsHide: true, stdio: "pipe" },
  );
  try {
    await firstHistoryReview.click();
    await restartedDetail
      .getByText(
        "The recording changed. Historical excerpts remain available; preparing an edit is disabled.",
        { exact: true },
      )
      .waitFor();
    assert.equal(
      await recentCandidate
        .getByRole("button", { name: "Prepare concern in notes", exact: true })
        .isDisabled(),
      true,
    );
    assert.equal(
      await recentSibling
        .getByRole("button", { name: "Prepare concern in notes", exact: true })
        .isDisabled(),
      true,
    );
    const stale = await recentDetail();
    assert.equal(stale.context_current, false);
    assert.ok(stale.findings.every((item) => !item.can_adopt));
    assert.deepEqual(
      stale.findings.map((item) => item.finding_id),
      initialRecent.findings.map((item) => item.finding_id),
    );
    await recentCandidate
      .getByRole("button", { name: "Dismiss concern candidate", exact: true })
      .click();
    await recentCandidate
      .getByText("Review state: rejected", { exact: true })
      .waitFor();
    await recentSibling
      .getByText("Review state: unreviewed", { exact: true })
      .waitFor();
    assert.deepEqual(await context(), beforeRestart);
  } finally {
    execFileSync(
      python,
      [
        "-c",
        String.raw`
import sqlite3,sys
c=sqlite3.connect(sys.argv[1]);c.execute('UPDATE utterances SET text=? WHERE id=?',(sys.argv[3],sys.argv[2]));c.commit();c.close()
`,
        database,
        changedUtterance.id,
        changedUtterance.text,
      ],
      { cwd: root, windowsHide: true, stdio: "pipe" },
    );
  }
  await recentCandidate
    .getByRole("button", { name: "Reopen concern candidate", exact: true })
    .click();
  await recentCandidate
    .getByText("Review state: unreviewed", { exact: true })
    .waitFor();
  assert.equal(
    await recentCandidate
      .getByRole("button", { name: "Prepare concern in notes", exact: true })
      .isDisabled(),
    false,
  );
  assert.equal((await recentDetail()).context_current, true);
  checks.push(
    "Historical changed recording retains original candidate IDs and exact excerpts, disables adoption, permits independent dismiss/reopen, and restores eligibility only after exact recording restoration",
  );

  async function reviewRecentOnCurrentHead() {
    await restarted
      .getByText("26 ended Runs for this deck. A debrief is not required.", {
        exact: true,
      })
      .waitFor();
    await restarted
      .getByRole("button", { name: "Next objection Runs", exact: true })
      .click();
    await restartedRun
      .locator(`option[value="${originalSession}"]`)
      .waitFor({ state: "attached" });
    await restartedRun.selectOption(originalSession);
    await restarted.getByText(/23 saved analyses/).waitFor();
    await firstHistoryReview.click();
    await recentCandidate
      .getByText("Review state: unreviewed", { exact: true })
      .waitFor();
  }
  async function openSlideActions() {
    const actions = page.locator(".pw-slide-actions");
    if (!(await actions.evaluate((element) => element.open)))
      await actions.locator("summary").click();
  }
  await openSlideActions();
  await page
    .getByRole("button", { name: "Move current slide later", exact: true })
    .click();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await page
    .getByRole("img", { name: "Imported presentation, slide 2", exact: true })
    .waitFor();
  const reordered = await context(2);
  assert.equal(reordered.scope.slide_id, firstSlide);
  scope = { ...scope, expected_revision_id: reordered.scope.revision_id };
  await reviewRecentOnCurrentHead();
  await restarted
    .getByRole("combobox", { name: "Objection original slide", exact: true })
    .locator(`option[value="${firstSlide}"]`)
    .waitFor({ state: "attached" });
  assert.match(
    await restarted
      .getByRole("combobox", { name: "Objection original slide", exact: true })
      .locator(`option[value="${firstSlide}"]`)
      .textContent(),
    /Original slide 1.*Current slide 2/,
  );
  const movedDetail = await recentDetail();
  assert.deepEqual(
    movedDetail.findings.map((item) => item.finding_id),
    initialRecent.findings.map((item) => item.finding_id),
  );
  assert.ok(
    movedDetail.findings.every(
      (item) =>
        item.finding.source_slide_number === 1 &&
        item.finding.current_slide_number === 2,
    ),
  );
  assert.equal(
    await recentCandidate
      .getByRole("button", { name: "Prepare concern in notes", exact: true })
      .isDisabled(),
    false,
  );
  assert.deepEqual(
    movedDetail.findings.map((item) => item.disposition),
    ["unreviewed", "unreviewed"],
  );
  checks.push(
    "Actual GUI slide reorder preserves original Run/slide/candidate identity and independent review state while enabling adoption on the correctly mapped current slide 2",
  );

  await openSlideActions();
  await page
    .getByRole("button", { name: "Review current slide deletion", exact: true })
    .click();
  const confirmDeletion = page.getByRole("group", {
    name: "Confirm slide deletion",
    exact: true,
  });
  await confirmDeletion.getByText(/Delete slide 2\?/).waitFor();
  await confirmDeletion
    .getByRole("button", { name: "Confirm delete current slide", exact: true })
    .click();
  await page.getByText("Current · Revision 5", { exact: true }).waitFor();
  const removed = await context(2);
  assert.notEqual(removed.scope.slide_id, firstSlide);
  scope = { ...scope, expected_revision_id: removed.scope.revision_id };
  await reviewRecentOnCurrentHead();
  await recentCandidate
    .getByText("The original slide is absent from the current revision.", {
      exact: true,
    })
    .waitFor();
  await recentSibling
    .getByText("The original slide is absent from the current revision.", {
      exact: true,
    })
    .waitFor();
  assert.equal(
    await recentCandidate
      .getByRole("button", { name: "Prepare concern in notes", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(
    await recentSibling
      .getByRole("button", { name: "Prepare concern in notes", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(
    await restartedDetail
      .getByRole("button", {
        name: "Open current slide for concern",
        exact: true,
      })
      .count(),
    0,
  );
  await recentSibling
    .getByRole("button", { name: "Dismiss concern candidate", exact: true })
    .click();
  await recentSibling
    .getByText("Review state: rejected", { exact: true })
    .waitFor();
  await recentCandidate
    .getByText("Review state: unreviewed", { exact: true })
    .waitFor();
  const removedDetail = await recentDetail();
  assert.deepEqual(
    removedDetail.findings.map((item) => item.finding_id),
    initialRecent.findings.map((item) => item.finding_id),
  );
  assert.ok(
    removedDetail.findings.every(
      (item) =>
        item.finding.source_slide_number === 1 &&
        item.finding.current_slide_number === null &&
        !item.can_adopt,
    ),
  );
  assert.deepEqual(await context(2), removed);
  checks.push(
    "Actual reviewed GUI slide deletion retains original excerpts/candidate IDs and independent dismissal while removing current navigation and disabling adoption without additional native revisions",
  );
  assert.deepEqual(errors, []);

  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      {
        checks,
        errors,
        scope,
        originalSession,
        saved,
        overflow,
        boundary:
          "Actual Electron/Core/native PPTX; picker, capture and explicit fixture model adapter",
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
  await writeFile(
    controlFile,
    JSON.stringify({ hold: false, release: true }),
  ).catch(() => {});
  if (app) {
    await app
      .evaluate(() => {
        globalThis.objectionDetailHold = false;
        globalThis.objectionDetailRelease = true;
        globalThis.objectionStartHold = false;
        globalThis.objectionStartRelease = true;
      })
      .catch(() => {});
    await app.close();
  }
}
