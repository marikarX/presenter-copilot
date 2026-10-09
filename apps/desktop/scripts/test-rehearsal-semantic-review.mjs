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
  path.join(root, ".local", "rehearsal-semantic-coverage", "gui-initial");
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
for number in range(9):
 connection.execute("INSERT INTO utterances (id,session_id,actor,text,created_at,start_ms,end_ms,asr_confidence,slide_ordinal,is_final) VALUES (?,?,'user',?,'2026-10-08T10:00:00Z',?,?,NULL,1,1)",(str(uuid.uuid4()),session,f'Recorded pilot explanation {number}: revenue rose twenty percent.',number*2000,number*2000+1800))
row=dict(connection.execute('SELECT * FROM sessions WHERE id=?',(session,)).fetchone());fields=list(row)
for number in range(25):
 clone=row|{'id':str(uuid.uuid4()),'started_at':f'2026-10-09T12:{number:02d}:00Z'}
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
  const semantic = page.getByRole("region", {
    name: "Semantic rehearsal review",
    exact: true,
  });
  await semantic
    .getByText("26 ended Runs for this deck. A debrief is not required.", {
      exact: true,
    })
    .waitFor();
  const selectRun = semantic.getByRole("combobox", {
    name: "Semantic recorded Run",
    exact: true,
  });
  const emptySession = await selectRun
    .locator("option")
    .nth(1)
    .getAttribute("value");
  await selectRun.selectOption(emptySession);
  await semantic
    .getByRole("combobox", { name: "Original rehearsal message", exact: true })
    .waitFor();
  const originalMessages = await ask(
    "presentation.workspace.list_rehearsal_review_messages",
    { ...scope, session_id: originalSession },
  );
  const short = originalMessages.messages.find(
    (item) => item.name === "Basic metric",
  );
  const long = originalMessages.messages.find(
    (item) => item.name === "Readonly metrics",
  );
  assert.ok(short && long);
  const choosePoint = async (id) =>
    semantic
      .getByRole("combobox", {
        name: "Original rehearsal message",
        exact: true,
      })
      .selectOption(id);
  await choosePoint(short.object_id);
  await semantic
    .getByRole("button", { name: "Use whole message", exact: true })
    .click();
  await semantic
    .getByRole("button", {
      name: "Prepare recorded speech windows",
      exact: true,
    })
    .click();
  await semantic
    .getByText(
      "No recorded speech is available for this message. This does not establish that it was omitted.",
      { exact: true },
    )
    .waitFor();
  assert.equal(
    await semantic
      .getByRole("button", {
        name: "Analyze selected speech window",
        exact: true,
      })
      .count(),
    0,
  );
  checks.push(
    "Ended Run without a debrief is selectable; no recorded speech does not enable inference or establish omission",
  );
  await semantic
    .getByRole("button", { name: "Next Runs", exact: true })
    .click();
  await selectRun
    .locator(`option[value="${originalSession}"]`)
    .waitFor({ state: "attached" });
  await selectRun.selectOption(originalSession);
  await choosePoint(long.object_id);
  assert.equal(
    await semantic
      .getByRole("textbox", {
        name: "Full original rehearsal source",
        exact: true,
      })
      .inputValue(),
    long.text,
  );
  assert.equal(
    await semantic
      .getByRole("button", { name: "Use whole message", exact: true })
      .isDisabled(),
    true,
  );
  await semantic
    .getByRole("textbox", { name: "Exact rehearsal message span", exact: true })
    .fill("Return on investment reached 24%.");
  await semantic
    .getByRole("button", {
      name: "Prepare recorded speech windows",
      exact: true,
    })
    .click();
  await semantic
    .getByRole("combobox", { name: "Semantic speech window", exact: true })
    .waitFor();
  checks.push(
    "Session paging beyond twenty retains explicit original Run selection; complete long native message requires an explicit exact span",
  );
  await choosePoint(short.object_id);
  await semantic
    .getByRole("button", { name: "Use whole message", exact: true })
    .click();
  await semantic
    .getByRole("button", {
      name: "Prepare recorded speech windows",
      exact: true,
    })
    .click();
  await semantic.getByText(/9 recorded utterances in 3 windows/).waitFor();
  const speechWindow = semantic.getByRole("combobox", {
    name: "Semantic speech window",
    exact: true,
  });
  assert.equal(await speechWindow.inputValue(), "");
  assert.equal(
    await semantic
      .getByRole("button", {
        name: "Analyze selected speech window",
        exact: true,
      })
      .isDisabled(),
    true,
  );
  await speechWindow.selectOption("0");
  await semantic
    .getByText(/^Recorded pilot explanation 0: revenue rose twenty percent\./)
    .waitFor();
  await semantic
    .getByRole("button", {
      name: "Analyze selected speech window",
      exact: true,
    })
    .click();
  await semantic
    .getByText("Saved one window result. Review it before preparing an edit.", {
      exact: true,
    })
    .waitFor();
  const saved = (
    await ask("presentation.workspace.list_rehearsal_analyses", {
      ...scope,
      session_id: originalSession,
    })
  ).analyses;
  assert.equal(saved.length, 1);
  assert.equal((await context()).sha256, baseline.sha256);
  checks.push(
    "Explicit one-of-three window Analyze persists one audited result and leaves native bytes unchanged; full speech is visible before inference",
  );
  await semantic
    .getByRole("button", { name: "Review saved window result", exact: true })
    .click();
  const detail = semantic.getByRole("article", {
    name: "Verified semantic window result",
    exact: true,
  });
  await detail
    .getByRole("heading", {
      name: "Unverified window coverage hint",
      exact: true,
    })
    .waitFor();
  await detail.getByText(short.text, { exact: true }).waitFor();
  await detail
    .getByRole("heading", {
      name: "Unverified window coverage hint",
      exact: true,
    })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: path.join(output, "semantic-verified-detail.png"),
  });
  assert.equal(
    await detail
      .getByRole("button", {
        name: "Prepare semantic text rewrite",
        exact: true,
      })
      .isDisabled(),
    true,
  );
  await detail
    .getByRole("button", { name: "Dismiss semantic result", exact: true })
    .click();
  await detail
    .getByRole("button", { name: "Reopen semantic result", exact: true })
    .waitFor();
  assert.equal(
    await detail
      .getByRole("button", {
        name: "Prepare notes from original message",
        exact: true,
      })
      .isDisabled(),
    true,
  );
  await detail
    .getByRole("button", { name: "Reopen semantic result", exact: true })
    .click();
  await detail
    .getByRole("button", { name: "Dismiss semantic result", exact: true })
    .waitFor();
  checks.push(
    "Verified durable result shows separate native message/model hint; dismiss/reopen is durable and gates preparation without approving a model hint",
  );
  await detail
    .getByRole("button", {
      name: "Prepare notes from original message",
      exact: true,
    })
    .click();
  const notes = page.getByRole("textbox", {
    name: "Speaker notes",
    exact: true,
  });
  assert.equal(
    await notes.inputValue(),
    `Initial private speaking reminder.\n\n${short.text}`,
  );
  assert.equal((await context()).sha256, baseline.sha256);
  await notes.fill("User reviewed pilot revenue before adoption.");
  await page
    .getByRole("button", { name: "Save speaker notes", exact: true })
    .click();
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  scope = {
    ...scope,
    expected_revision_id: (await context()).scope.revision_id,
  };
  const verified = await ask("presentation.workspace.get_rehearsal_analysis", {
    ...scope,
    finding_id: saved[0].finding_id,
  });
  assert.equal(verified.finding.disposition, "applied");
  checks.push(
    "Notes preparation drafts original native message without saving; explicit GUI native Save creates revision and applied finding attribution",
  );
  await studio("Rehearsal");
  await semantic
    .getByRole("button", { name: "Next Runs", exact: true })
    .click();
  await selectRun
    .locator(`option[value="${originalSession}"]`)
    .waitFor({ state: "attached" });
  await selectRun.selectOption(originalSession);
  await semantic
    .getByRole("button", { name: "Review saved window result", exact: true })
    .click();
  await detail
    .getByRole("button", { name: "Dismiss semantic result", exact: true })
    .waitFor();
  assert.equal(
    await detail
      .getByRole("button", { name: "Dismiss semantic result", exact: true })
      .isDisabled(),
    true,
  );
  await choosePoint(short.object_id);
  await semantic
    .getByRole("button", { name: "Use whole message", exact: true })
    .click();
  await semantic
    .getByRole("button", {
      name: "Prepare recorded speech windows",
      exact: true,
    })
    .click();
  await speechWindow.selectOption("1");
  await semantic
    .getByRole("button", {
      name: "Analyze selected speech window",
      exact: true,
    })
    .click();
  await semantic
    .getByText("Saved one window result. Review it before preparing an edit.", {
      exact: true,
    })
    .waitFor();
  const retry = (
    await ask("presentation.workspace.list_rehearsal_analyses", {
      ...scope,
      session_id: originalSession,
    })
  ).analyses.find((item) => item.finding_id !== saved[0].finding_id);
  assert.ok(retry);
  await semantic
    .getByRole("button", { name: "Review saved window result", exact: true })
    .first()
    .click();
  await detail
    .getByRole("button", { name: "Select original text object", exact: true })
    .click();
  await detail
    .getByRole("button", { name: "Prepare semantic text rewrite", exact: true })
    .waitFor();
  assert.equal(
    await detail
      .getByRole("button", {
        name: "Prepare semantic text rewrite",
        exact: true,
      })
      .isEnabled(),
    true,
  );
  await detail
    .getByRole("button", { name: "Prepare semantic text rewrite", exact: true })
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
  assert.equal((await context()).scope.revision_id, scope.expected_revision_id);
  assert.equal(
    (
      await ask("presentation.workspace.get_rehearsal_analysis", {
        ...scope,
        finding_id: retry.finding_id,
      })
    ).finding.disposition,
    "unreviewed",
  );
  await suggestion
    .getByRole("button", { name: "Use suggestion in editor", exact: true })
    .click();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Replacement text", exact: true })
      .inputValue(),
    short.text,
  );
  assert.equal((await context()).sha256, beforeRewrite.sha256);
  checks.push(
    "Semantic rewrite suggestion is reviewed separately; requesting and copying a fixture suggestion leave native bytes, revision and finding disposition unchanged",
  );
  await page
    .getByRole("textbox", { name: "Replacement text", exact: true })
    .fill("Revenue rose 20% during the reviewed pilot.");
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
  const adopted = await ask("presentation.workspace.get_rehearsal_analysis", {
    ...scope,
    finding_id: retry.finding_id,
  });
  assert.equal(adopted.finding.disposition, "applied");
  checks.push(
    "Independent retry preserves prior applied history; original-object selection, semantic Suggest rewrite and user-reviewed replacement Preview/Save retain finding attribution",
  );
  await studio("Rehearsal");
  await semantic
    .getByRole("button", { name: "Next Runs", exact: true })
    .click();
  await selectRun
    .locator(`option[value="${originalSession}"]`)
    .waitFor({ state: "attached" });
  await selectRun.selectOption(originalSession);
  await choosePoint(short.object_id);
  await semantic.getByText(/Current slide 1 · changed/).waitFor();
  assert.equal(
    await semantic
      .getByRole("textbox", {
        name: "Full original rehearsal source",
        exact: true,
      })
      .inputValue(),
    short.text,
  );
  await app.evaluate(
    (_electron, modulePath) => {
      const { CoreProcessClient } = process.mainModule.require(modulePath);
      const original = CoreProcessClient.prototype.request;
      globalThis.semanticHold = false;
      globalThis.semanticHeld = false;
      globalThis.semanticRelease = true;
      globalThis.semanticCancelReplies = [];
      CoreProcessClient.prototype.request = async function (...args) {
        const result = await original.apply(this, args);
        if (args[0] === "presentation.workspace.cancel_rehearsal_analysis")
          globalThis.semanticCancelReplies.push({
            state: result.state,
            accepted: result.cancellation_accepted,
          });
        if (
          args[0] === "presentation.workspace.start_rehearsal_analysis" &&
          globalThis.semanticHold
        ) {
          globalThis.semanticHeld = true;
          const deadline = Date.now() + 30000;
          while (!globalThis.semanticRelease && Date.now() < deadline)
            await new Promise((resolve) => setTimeout(resolve, 30));
        }
        return result;
      };
    },
    path.join(desktop, "dist", "main", "core-client.js"),
  );
  async function heldStart() {
    await semantic
      .getByRole("button", { name: "Use whole message", exact: true })
      .click();
    await semantic
      .getByRole("button", {
        name: "Prepare recorded speech windows",
        exact: true,
      })
      .click();
    await speechWindow.selectOption("0");
    await app.evaluate(() => {
      globalThis.semanticHold = true;
      globalThis.semanticHeld = false;
      globalThis.semanticRelease = false;
    });
    await semantic
      .getByRole("button", {
        name: "Analyze selected speech window",
        exact: true,
      })
      .click();
    const deadline = Date.now() + 20000;
    while (
      !(await app.evaluate(() => globalThis.semanticHeld)) &&
      Date.now() < deadline
    )
      await new Promise((resolve) => setTimeout(resolve, 30));
    assert.equal(await app.evaluate(() => globalThis.semanticHeld), true);
  }
  const savedCount = async () =>
    (
      await ask("presentation.workspace.list_rehearsal_analyses", {
        ...scope,
        session_id: originalSession,
      })
    ).total;
  async function waitSaved(expected) {
    const deadline = Date.now() + 20000;
    while ((await savedCount()) !== expected && Date.now() < deadline)
      await new Promise((resolve) => setTimeout(resolve, 30));
    assert.equal(await savedCount(), expected);
  }
  const releaseStart = () =>
    app.evaluate(() => {
      globalThis.semanticRelease = true;
      globalThis.semanticHold = false;
    });
  const cancelPending = async () => {
    await semantic
      .getByRole("button", { name: "Cancel semantic analysis", exact: true })
      .click();
    await semantic
      .getByText(
        "Cancellation requested. Waiting for analysis to start so it can be cancelled.",
        { exact: true },
      )
      .waitFor();
  };
  let durableCount = await savedCount();
  await heldStart();
  await cancelPending();
  await releaseStart();
  await semantic.getByText(/^Analysis: (completed|cancelled)\./).waitFor();
  const cancellation = (
    await app.evaluate(() => globalThis.semanticCancelReplies)
  )[0];
  assert.ok(cancellation);
  if (cancellation.accepted) {
    await semantic
      .getByText("Analysis cancelled. No window result was saved.", {
        exact: true,
      })
      .waitFor();
    await semantic.getByText(/^Analysis: cancelled\./).waitFor();
    assert.equal(await savedCount(), durableCount);
  } else {
    durableCount++;
    await semantic
      .getByText(
        "Cancellation arrived after storage began. The saved window result remains available for review.",
        { exact: true },
      )
      .waitFor();
    await semantic.getByText(/^Analysis: completed\./).waitFor();
    assert.equal(await savedCount(), durableCount);
  }
  assert.equal((await context()).scope.revision_id, scope.expected_revision_id);
  checks.push(
    "Cancel with a held real Start reply invokes owned Cancel; final notice/state and durable result count match actual acceptance without assuming provider timing",
  );
  await heldStart();
  durableCount++;
  await waitSaved(durableCount);
  await cancelPending();
  await releaseStart();
  await semantic
    .getByText(
      "Cancellation arrived after storage began. The saved window result remains available for review.",
      { exact: true },
    )
    .waitFor();
  await semantic.getByText(/^Analysis: completed\./).waitFor();
  assert.equal(
    (await app.evaluate(() => globalThis.semanticCancelReplies))[1].accepted,
    false,
  );
  checks.push(
    "Already persisted analysis is verified before Cancel; GUI truthfully explains too-late cancellation and preserves the saved window result",
  );
  await heldStart();
  durableCount++;
  await waitSaved(durableCount);
  await studio("Notes");
  await releaseStart();
  const cancelDeadline = Date.now() + 20000;
  while (
    (await app.evaluate(() => globalThis.semanticCancelReplies.length)) < 3 &&
    Date.now() < cancelDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(
    await app.evaluate(() => globalThis.semanticCancelReplies.length),
    3,
  );
  await studio("Rehearsal");
  await semantic
    .getByText("26 ended Runs for this deck. A debrief is not required.", {
      exact: true,
    })
    .waitFor();
  assert.equal(
    await semantic
      .getByText(
        "Saved one window result. Review it before preparing an edit.",
        { exact: true },
      )
      .count(),
    0,
  );
  assert.equal(await semantic.getByText(/Analysis: completed/).count(), 0);
  assert.equal(await savedCount(), durableCount);
  await semantic
    .getByRole("button", { name: "Next Runs", exact: true })
    .click();
  await selectRun
    .locator(`option[value="${originalSession}"]`)
    .waitFor({ state: "attached" });
  await selectRun.selectOption(originalSession);
  checks.push(
    "Hidden panel cancels a late real Start using captured ownership; stale reply/status is discarded and already committed history remains discoverable",
  );
  await semantic
    .getByRole("button", { name: "Next messages", exact: true })
    .click();
  await semantic
    .getByRole("combobox", { name: "Original rehearsal message", exact: true })
    .locator(`option[value="${originalMessages.messages[0].object_id}"]`)
    .waitFor({ state: "detached" });
  assert.equal(
    await semantic
      .getByRole("combobox", {
        name: "Original rehearsal message",
        exact: true,
      })
      .locator("option")
      .count(),
    9,
  );
  checks.push(
    "Later current text edits preserve original native message; original message paging retains full inventory beyond twenty",
  );
  await app.evaluate(({ BrowserWindow }) => {
    const main = BrowserWindow.getAllWindows().find(
      (w) =>
        !w.isDestroyed() &&
        w.webContents.getURL().endsWith("/renderer/index.html"),
    );
    if (!main) throw new Error("Main renderer window unavailable");
    main.setSize(720, 520);
  });
  await page.waitForFunction(
    () => window.innerWidth <= 720 && window.innerHeight <= 520,
  );
  await semantic
    .getByRole("heading", {
      name: "Review a message against recorded speech",
      exact: true,
    })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, "semantic-small.png") });
  const overflow = await semantic.evaluate((element) => ({
    scroll: element.scrollWidth,
    width: element.clientWidth,
    viewport: document.documentElement.clientWidth,
    height: window.innerHeight,
    page: document.documentElement.scrollWidth,
  }));
  assert.ok(overflow.scroll <= overflow.width + 2, JSON.stringify(overflow));
  assert.ok(overflow.page <= overflow.viewport + 2, JSON.stringify(overflow));
  assert.ok(
    overflow.viewport >= 680 &&
      overflow.viewport <= 720 &&
      overflow.height >= 420 &&
      overflow.height <= 520,
    JSON.stringify(overflow),
  );
  assert.deepEqual(errors, []);
  checks.push(
    "Actual semantic controls remain contained at constrained viewport with no renderer errors",
  );
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      { checks, errors, baseline, scope, originalSession, overflow },
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
  if (app) {
    await app
      .evaluate(() => {
        globalThis.semanticRelease = true;
        globalThis.semanticHold = false;
      })
      .catch(() => {});
    await app.close();
  }
}
