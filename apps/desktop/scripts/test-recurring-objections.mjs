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
  path.join(root, ".local", "repeated-objections", "gui");
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
  const note = "Why should we approve this cost?";
  const groups = page.getByRole("region", {
    name: "Recurring rehearsal objections",
    exact: true,
  });
  const find = () =>
    groups.getByRole("button", {
      name: "Find recurring objections",
      exact: true,
    });
  const cost = () => groups.locator("article").filter({ hasText: note });
  async function workspace() {
    await page
      .getByRole("navigation", { name: "Project navigation", exact: true })
      .getByRole("button", { name: "Workspace", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Open preview", exact: true })
      .click();
    await studio("Rehearsal");
    await find().waitFor();
  }
  async function rehearse(second = false) {
    await page.getByRole("button", { name: "Rehearse", exact: true }).click();
    await page
      .getByLabel("Presentation tracking", { exact: true })
      .selectOption("manual");
    await page.getByRole("button", { name: "Start Run", exact: true }).click();
    if (second)
      await page
        .getByRole("button", { name: "Next slide", exact: true })
        .click();
    const notes = [
      note,
      ...(!second ? [note] : []),
      ...Array.from(
        { length: 22 },
        (_, i) => `Distinct objection ${i + 1}: explain the risk.`,
      ),
      ...(second ? [note.toLowerCase()] : []),
    ];
    for (const text of notes) {
      await page.getByLabel("Optional marker note", { exact: true }).fill(text);
      await page
        .getByRole("button", { name: "Mark objection", exact: true })
        .click();
    }
    await page.getByRole("button", { name: "Stop Run", exact: true }).click();
    await page
      .getByRole("heading", { name: "Run debrief", exact: true })
      .waitFor();
  }
  await rehearse();
  await workspace();
  await find().click();
  await groups
    .getByText(
      "No repeated matching objections were found in these rehearsals.",
      { exact: true },
    )
    .waitFor();
  assert.equal((await context()).sha256, baseline.sha256);
  checks.push(
    "Actual Run captures explicit objection notes; repeated markers inside one rehearsal produce no cross-rehearsal recurrence and inspection does not edit the native deck",
  );
  const actions = page.locator("details.pw-slide-actions");
  if (!(await actions.evaluate((node) => node.open)))
    await actions.locator("summary").click();
  await page
    .getByRole("button", { name: "Move current slide later", exact: true })
    .click();
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  await rehearse(true);
  await workspace();
  await find().click();
  await groups
    .getByText(
      "23 recurring objections in 2 rehearsals checked · page 1 of 2.",
      { exact: true },
    )
    .waitFor();
  assert.equal(await groups.locator("article").count(), 20);
  await cost()
    .getByText(
      /3 observations across 2 distinct rehearsals · 3 unreviewed · 0 applied · 0 dismissed/,
    )
    .waitFor();
  const groupId = await cost().getAttribute("data-group-id");
  const scope2 = (await context(2)).scope;
  const result2 = await ask("presentation.workspace.recurring_objections", {
    project_id: scope2.project_id,
    document_id: scope2.document_id,
    expected_revision_id: scope2.revision_id,
  });
  const original = result2.groups.find((group) => group.group_id === groupId);
  assert.equal(original.current_slide_number, 2);
  assert.deepEqual(
    [
      ...new Set(original.occurrences.map((item) => item.source_slide_number)),
    ].sort(),
    [1, 2],
  );
  assert.equal(result2.ungrouped_objections, 1);
  await page.screenshot({
    path: path.join(output, "recurring-objections.png"),
  });
  checks.push(
    "Two actual GUI Runs across a native reorder yield 23 exact-wording/stable-slide recurring objection groups, keep case variants separate and preserve every original revision/ordinal",
  );
  await groups
    .getByRole("button", { name: "Next objection groups", exact: true })
    .click();
  await groups
    .getByText(
      "23 recurring objections in 2 rehearsals checked · page 2 of 2.",
      { exact: true },
    )
    .waitFor();
  assert.equal(await groups.locator("article").count(), 3);
  await groups
    .getByRole("button", { name: "Previous objection groups", exact: true })
    .click();
  await cost().waitFor();
  const choices = cost().getByRole("combobox", {
    name: "Objection observation",
    exact: true,
  });
  const older = original.occurrences.find(
    (item) => item.source_revision_number === 1,
  );
  await choices.selectOption(older.finding_id);
  await cost()
    .getByRole("button", { name: "Open objection slide 2", exact: true })
    .click();
  await page.getByText("Slide 2 of 26", { exact: true }).waitFor();
  const beforeDraft = await context(2);
  await cost()
    .getByRole("button", { name: "Prepare objection notes", exact: true })
    .click();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Speaker notes", exact: true })
      .inputValue(),
    `Initial private speaking reminder.\n\n${note}`,
  );
  assert.equal((await context(2)).sha256, beforeDraft.sha256);
  await page
    .getByRole("textbox", { name: "Speaker notes", exact: true })
    .fill(
      `Initial private speaking reminder.\n\nReviewed response: explain the cost evidence before asking for approval.`,
    );
  await page
    .getByRole("button", { name: "Save speaker notes", exact: true })
    .click();
  await page.getByText("Current · Revision 3", { exact: true }).waitFor();
  await studio("Rehearsal");
  await find().click();
  await cost()
    .getByText(
      /3 observations across 2 distinct rehearsals · 2 unreviewed · 1 applied · 0 dismissed/,
    )
    .waitFor();
  const scope3 = (await context(2)).scope;
  const result3 = await ask("presentation.workspace.recurring_objections", {
    project_id: scope3.project_id,
    document_id: scope3.document_id,
    expected_revision_id: scope3.revision_id,
  });
  const after = result3.groups.find((group) => group.group_id === groupId);
  assert.equal(after.group_id, groupId);
  const applied = after.occurrences.find(
    (item) => item.finding_id === older.finding_id,
  );
  assert.equal(applied.applied_revision_id, scope3.revision_id);
  assert.equal(applied.source_revision_id, baseline.scope.revision_id);
  assert.equal(after.selected_finding.disposition, "unreviewed");
  checks.push(
    "Group paging shows 20 then 3; selecting an original revision-1 occurrence opens stable current slide 2, prepares a read-only notes draft and explicit user-edited Save records only that occurrence's original/applied provenance",
  );

  await app.evaluate(
    (_electron, modulePath) => {
      const { CoreProcessClient } = process.mainModule.require(modulePath);
      const original = CoreProcessClient.prototype.request;
      globalThis.objectionsHold = false;
      globalThis.objectionsHeld = false;
      globalThis.objectionsRelease = true;
      CoreProcessClient.prototype.request = async function (...args) {
        const result = await original.apply(this, args);
        if (
          args[0] === "presentation.workspace.recurring_objections" &&
          globalThis.objectionsHold
        ) {
          globalThis.objectionsHeld = true;
          const deadline = Date.now() + 30000;
          while (!globalThis.objectionsRelease && Date.now() < deadline)
            await new Promise((resolve) => setTimeout(resolve, 30));
        }
        return result;
      };
    },
    path.join(desktop, "dist", "main", "core-client.js"),
  );
  await cost()
    .getByRole("button", { name: "Open objection slide 2", exact: true })
    .click();
  await app.evaluate(() => {
    globalThis.objectionsHold = true;
    globalThis.objectionsRelease = false;
  });
  await find().click();
  const holdDeadline = Date.now() + 20000;
  while (
    !(await app.evaluate(() => globalThis.objectionsHeld)) &&
    Date.now() < holdDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 40));
  assert.equal(await app.evaluate(() => globalThis.objectionsHeld), true);
  await studio("Notes");
  await page
    .getByRole("textbox", { name: "Speaker notes", exact: true })
    .fill("A new reviewed reminder after the objection response.");
  await page
    .getByRole("button", { name: "Save speaker notes", exact: true })
    .click();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await app.evaluate(() => {
    globalThis.objectionsRelease = true;
    globalThis.objectionsHold = false;
  });
  await studio("Rehearsal");
  await page.waitForTimeout(400);
  assert.equal(await groups.locator("article").count(), 0);
  await find().click();
  await cost()
    .getByText(/2 unreviewed · 1 applied · 0 dismissed/)
    .waitFor();
  checks.push(
    "Held real recurring-objection reply cannot republish after an actual GUI notes revision; fresh inspection keeps independent applied/unreviewed status",
  );
  const finalSource = await context(2);
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()
      .find((window) =>
        window.webContents.getURL().endsWith("/renderer/index.html"),
      )
      ?.setSize(720, 520),
  );
  await groups
    .getByRole("heading", { name: "Review recurring objections", exact: true })
    .scrollIntoViewIfNeeded();
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
    false,
  );
  await page.screenshot({ path: path.join(output, "minimum-objections.png") });
  assert.equal((await context(2)).sha256, finalSource.sha256);
  assert.equal(
    (await ask("presentation.workspace.list_claims", finalSource.scope)).items
      .length,
    0,
  );
  assert.deepEqual(errors, []);
  checks.push(
    "Recurring-objection controls/cards fit at 720x520; inspection and navigation preserve native bytes, create no claims and never approve the remaining occurrences",
  );
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      { checks, errors, baseline, finalSource, original, after },
      null,
      2,
    ),
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
        globalThis.objectionsRelease = true;
      })
      .catch(() => {});
    await app.close();
  }
}
