/* global document, window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";
const require = createRequire(import.meta.url);
const desktop = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const root = path.resolve(desktop, "../..");
const packagedExecutable = process.env.PRESENTER_COPILOT_PACKAGED_EXE;
const temporary = await mkdtemp(
  path.join(os.tmpdir(), "presenter-outline-session-"),
);
const output = path.join(root, ".local", "outline-session");
await mkdir(output, { recursive: true });
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
  PRESENTER_COPILOT_TEST_ASR: "deterministic_fake",
});
let app, page, projectId;
const errors = [],
  checks = [];
async function launch(packaged = false) {
  page = null;
  app = await electron.launch({
    executablePath: packaged
      ? path.resolve(packagedExecutable)
      : require("electron"),
    args: [
      ...(!packaged ? [desktop] : []),
      `--user-data-dir=${path.join(temporary, packaged ? "browser-packaged" : "browser")}`,
    ],
    cwd: root,
    env: packaged
      ? {
          ...Object.fromEntries(
            Object.entries(env).filter(
              ([key]) => !key.startsWith("PRESENTER_"),
            ),
          ),
          PRESENTER_COPILOT_DATA_ROOT: path.join(temporary, "core"),
        }
      : env,
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
}
async function planner() {
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
  return dialog;
}
async function session() {
  return page.evaluate(async (id) => {
    const result = await window.presenterCopilot.core.request(
      "presentation.workspace.get_outline_session",
      { project_id: id },
    );
    if (!result.ok) throw new Error(result.error.message);
    return result.result;
  }, projectId);
}
function counts() {
  const database = path.join(
    temporary,
    "core",
    "projects",
    projectId,
    "project.db",
  );
  const script =
    "import sqlite3,json,sys;from pathlib import Path;c=sqlite3.connect('file:'+Path(sys.argv[1]).as_posix()+'?mode=ro',uri=True);print(json.dumps({'runs':c.execute('SELECT COUNT(*) FROM provider_runs').fetchone()[0],'documents':c.execute('SELECT COUNT(*) FROM documents').fetchone()[0]}));c.close()";
  return JSON.parse(
    execFileSync(
      path.join(root, "core", ".venv", "Scripts", "python.exe"),
      ["-c", script, database],
      { encoding: "utf8", windowsHide: true },
    ),
  );
}
try {
  await launch();
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill("Durable outline acceptance");
  await page.keyboard.press("Enter");
  projectId = await page.evaluate(async () => {
    const result = await window.presenterCopilot.core.request(
      "project.list",
      {},
    );
    if (!result.ok) throw new Error("Could not list owned project");
    return result.result.projects.find(
      (p) => p.name === "Durable outline acceptance",
    ).id;
  });
  let dialog = await planner();
  await dialog
    .getByLabel("Presentation objective", { exact: true })
    .fill("Approve a measured pilot");
  await dialog
    .getByLabel("Audience for this presentation", { exact: true })
    .fill("Leadership team");
  await dialog
    .getByLabel("Your briefing", { exact: true })
    .fill("Keep rollback and ownership explicit.");
  await dialog.getByLabel("Number of slides", { exact: true }).fill("3");
  await dialog
    .getByRole("button", { name: "Propose outline", exact: true })
    .click();
  await dialog
    .getByLabel("Draft presentation title", { exact: true })
    .fill("My edited ancestor");
  await dialog
    .getByLabel("Refine this draft", { exact: true })
    .fill("Put the decision first.");
  await dialog
    .getByRole("button", { name: "Refine outline", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Restore draft 2", exact: true })
    .waitFor();
  await dialog
    .getByRole("button", { name: "Restore draft 1", exact: true })
    .click();
  await dialog
    .getByLabel("Draft presentation title", { exact: true })
    .fill("Another edited ancestor");
  await dialog
    .getByLabel("Refine this draft", { exact: true })
    .fill("Keep the rollback visible.");
  await dialog
    .getByRole("button", { name: "Refine outline", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Restore draft 3", exact: true })
    .waitFor();
  await dialog
    .getByLabel("Draft presentation title", { exact: true })
    .fill("My saved branch");
  await dialog
    .getByText("Speaker notes and source review", { exact: true })
    .first()
    .click();
  await dialog
    .getByLabel("Slide 1 notes", { exact: true })
    .fill("My exact saved notes");
  await dialog
    .getByLabel("Refine this draft", { exact: true })
    .fill("Unsent refinement survives restart");
  assert.equal((await session()).payload, null);
  await app.evaluate(
    (_electron, filename) => {
      const { CoreProcessClient } = process.mainModule.require(filename);
      const original = CoreProcessClient.prototype.request;
      globalThis.outlineSaveHeld = false;
      globalThis.releaseOutlineSave = null;
      CoreProcessClient.prototype.request = async function (...args) {
        const result = await original.apply(this, args);
        if (args[0] === "presentation.workspace.save_outline_session") {
          CoreProcessClient.prototype.request = original;
          globalThis.outlineSaveHeld = true;
          await new Promise((resolve, reject) => {
            const timer = setTimeout(
              () => reject(new Error("Owned saved-session gate expired")),
              30_000,
            );
            globalThis.releaseOutlineSave = () => {
              clearTimeout(timer);
              resolve();
            };
          });
        }
        return result;
      };
    },
    path.join(desktop, "dist", "main", "core-client.js"),
  );
  await dialog
    .getByRole("button", { name: "Save drafting session", exact: true })
    .click();
  const saveDeadline = Date.now() + 30_000;
  while (
    !(await app.evaluate(() => globalThis.outlineSaveHeld)) &&
    Date.now() < saveDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 100));
  assert.equal(await app.evaluate(() => globalThis.outlineSaveHeld), true);
  assert.equal(
    await dialog
      .getByRole("button", { name: "Dictate refinement", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(
    await dialog
      .getByRole("button", {
        name: "Resume saved drafting session",
        exact: true,
      })
      .isDisabled(),
    true,
  );
  await app.evaluate(() => globalThis.releaseOutlineSave());
  checks.push(
    "A held save acknowledgment locks dictation and session actions until the exact saved receipt returns",
  );
  await dialog
    .getByText("A drafting session is saved locally in this project.", {
      exact: true,
    })
    .waitFor();
  const saved = await session();
  assert.equal(saved.payload.conversation.turns.length, 3);
  assert.deepEqual(counts(), { runs: 3, documents: 0 });
  await page.screenshot({ path: path.join(output, "saved.png") });
  await app.close();
  app = null;
  await launch();
  await page
    .getByRole("button", { name: "Durable outline acceptance", exact: true })
    .click();
  dialog = await planner();
  assert.equal(
    await dialog
      .getByRole("button", { name: "Restore draft 3", exact: true })
      .count(),
    0,
  );
  await dialog
    .getByRole("button", { name: "Resume saved drafting session", exact: true })
    .click();
  assert.equal(
    await dialog
      .getByLabel("Draft presentation title", { exact: true })
      .inputValue(),
    "My saved branch",
  );
  assert.equal(
    await dialog.getByLabel("Slide 1 notes", { exact: true }).inputValue(),
    "My exact saved notes",
  );
  assert.equal(
    await dialog.getByLabel("Refine this draft", { exact: true }).inputValue(),
    "Unsent refinement survives restart",
  );
  assert.deepEqual(await session(), saved);
  assert.deepEqual(counts(), { runs: 3, documents: 0 });
  await dialog
    .getByRole("button", { name: "Restore draft 2", exact: true })
    .click();
  await dialog.locator(".pw-outline-changes summary").click();
  assert.match(
    await dialog.locator(".pw-outline-changes").innerText(),
    /My edited ancestor/,
  );
  await dialog
    .getByRole("button", { name: "Restore draft 1", exact: true })
    .click();
  assert.equal(
    await dialog
      .getByLabel("Draft presentation title", { exact: true })
      .inputValue(),
    "Another edited ancestor",
  );
  checks.push(
    "Explicit Save and real Electron restart preserve three branched turns, ancestor edits, exact request baselines, notes and unsent refinement; Resume calls no provider and creates no deck",
  );
  await page.screenshot({ path: path.join(output, "resumed.png") });
  await app.evaluate(({ BrowserWindow }) => {
    const owned = BrowserWindow.getAllWindows().find((candidate) =>
      candidate.webContents.getURL().endsWith("/renderer/index.html"),
    );
    globalThis.outlinePreviousSize = owned.getSize();
    owned.setSize(720, 520);
  });
  await dialog
    .getByRole("region", { name: "Saved drafting session", exact: true })
    .scrollIntoViewIfNeeded();
  assert.equal(
    await dialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
    true,
  );
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
    true,
  );
  await page.screenshot({ path: path.join(output, "minimum-window.png") });
  await app.evaluate(({ BrowserWindow }) => {
    const owned = BrowserWindow.getAllWindows().find((candidate) =>
      candidate.webContents.getURL().endsWith("/renderer/index.html"),
    );
    owned.setSize(...globalThis.outlinePreviousSize);
  });
  checks.push(
    "Saved-session controls wrap without horizontal dialog or workspace overflow at minimum window size",
  );
  const changedElsewhere = await page.evaluate(
    async ({ id, saved }) => {
      const result = await window.presenterCopilot.core.request(
        "presentation.workspace.save_outline_session",
        {
          project_id: id,
          expected_record_token: saved.record_token,
          payload: saved.payload,
        },
      );
      if (!result.ok) throw new Error(result.error.message);
      return result.result;
    },
    { id: projectId, saved },
  );
  await dialog
    .getByLabel("Draft presentation title", { exact: true })
    .fill("Unsaved edits survive a conflict");
  await dialog
    .getByRole("button", { name: "Save drafting session", exact: true })
    .click();
  await dialog
    .getByText(
      "The saved drafting session changed in another view. Reload before saving.",
      { exact: true },
    )
    .waitFor();
  assert.equal(
    await dialog
      .getByLabel("Draft presentation title", { exact: true })
      .inputValue(),
    "Unsaved edits survive a conflict",
  );
  assert.deepEqual(await session(), changedElsewhere);
  await dialog
    .getByRole("button", { name: "Reload saved copy", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Save drafting session", exact: true })
    .click();
  const afterReload = await session();
  assert.notEqual(afterReload.record_token, changedElsewhere.record_token);
  assert.equal(
    afterReload.payload.conversation.turns[0].draft.title,
    "Unsaved edits survive a conflict",
  );
  assert.deepEqual(counts(), { runs: 3, documents: 0 });
  checks.push(
    "Concurrent saved-copy write blocks stale Save without losing edits; Reload refreshes ownership and permits exact current-draft Save with no provider call",
  );
  await dialog
    .getByRole("button", { name: "Remove saved copy", exact: true })
    .click();
  await dialog
    .getByText("No saved drafting session in this project.", { exact: true })
    .waitFor();
  assert.equal((await session()).payload, null);
  assert.equal(
    await dialog
      .getByLabel("Draft presentation title", { exact: true })
      .inputValue(),
    "Unsaved edits survive a conflict",
  );
  assert.deepEqual(counts(), { runs: 3, documents: 0 });
  checks.push(
    "Removing saved copy preserves the current temporary edits and invokes no provider or deck creation",
  );
  if (packagedExecutable) {
    await dialog
      .getByRole("button", { name: "Save drafting session", exact: true })
      .click();
    await dialog
      .getByText("A drafting session is saved locally in this project.", {
        exact: true,
      })
      .waitFor();
    const packagedSeed = await session();
    await app.close();
    app = null;
    await launch(true);
    await page.getByRole("dialog").waitFor();
    await page.keyboard.press("Escape");
    await page
      .getByRole("button", { name: "Durable outline acceptance", exact: true })
      .click();
    dialog = await planner();
    await dialog
      .getByRole("button", {
        name: "Resume saved drafting session",
        exact: true,
      })
      .click();
    assert.equal(
      await dialog
        .getByLabel("Draft presentation title", { exact: true })
        .inputValue(),
      "Unsaved edits survive a conflict",
    );
    assert.deepEqual(await session(), packagedSeed);
    assert.deepEqual(counts(), { runs: 3, documents: 0 });
    await page.screenshot({ path: path.join(output, "packaged-resumed.png") });
    await dialog
      .getByRole("button", { name: "Remove saved copy", exact: true })
      .click();
    await dialog
      .getByText("No saved drafting session in this project.", { exact: true })
      .waitFor();
    assert.equal((await session()).payload, null);
    assert.deepEqual(counts(), { runs: 3, documents: 0 });
    checks.push(
      "Fresh unpacked app resumes/removes developer-seeded local session through bundled schema-18 sidecar, without developer provider flags, provider calls or deck creation",
    );
  }
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, temporary }, null, 2),
  );
  console.log(JSON.stringify({ checks, errors }, null, 2));
} catch (error) {
  if (page)
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
  throw error;
} finally {
  if (app) await app.close();
}
