/* global document, window */
import assert from "node:assert/strict";
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
  path.join(os.tmpdir(), "presenter-checkpoints-"),
);
const output =
  process.env.PRESENTER_CHECKPOINT_OUTPUT ||
  path.join(root, ".local", "revision-checkpoints");
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

async function call(method, params) {
  return page.evaluate(
    async ({ method, params }) => {
      const response = await window.presenterCopilot.core.request(
        method,
        params,
      );
      if (!response.ok) throw new Error(response.error.message);
      return response.result;
    },
    { method, params },
  );
}
let documentId;
async function catalog() {
  return call("presentation.workspace.list_checkpoints", {
    project_id: projectId,
    document_id: documentId,
  });
}
async function head() {
  const scope = { project_id: projectId, document_id: documentId };
  const opened = await call("presentation.workspace.open_source", scope);
  await call("presentation.workspace.close_source", {
    ...scope,
    session_id: opened.session_id,
  });
  return {
    revision: opened.revision_id,
    number: opened.revision_number,
    sha256: opened.sha256,
  };
}
async function workspace() {
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page
    .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
    .waitFor();
  await history();
}
async function history() {
  await page
    .getByRole("group", { name: "Slide studio panels", exact: true })
    .getByRole("button", { name: "History", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Reload checkpoints", exact: true })
    .waitFor();
}
try {
  await launch(!!packagedExecutable);
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill("Checkpoint acceptance");
  await page.keyboard.press("Enter");
  await page
    .getByRole("heading", { name: "Sources", exact: true })
    .first()
    .waitFor();
  projectId = (await call("project.list", {})).projects.find(
    (item) => item.name === "Checkpoint acceptance",
  ).id;
  await app.evaluate(
    ({ dialog }, fixture) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [fixture],
      });
    },
    path.join(root, "samples", "synthetic-deck", "deck", "presentation.pptx"),
  );
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("presentation");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  await page.getByRole("button", { name: /presentation\.pptx/ }).waitFor();
  documentId = (
    await call("source.list", { project_id: projectId })
  ).sources.find((item) => item.original_name === "presentation.pptx").id;
  await workspace();
  let section = page.getByRole("region", {
    name: "Named revision checkpoints",
    exact: true,
  });
  const baseline = await head();
  await section
    .getByLabel("Checkpoint name", { exact: true })
    .fill("Ready for rehearsal");
  await section
    .getByLabel("Checkpoint note", { exact: true })
    .fill("Keep the reviewed baseline.\nSecond line preserved.");
  await section
    .getByRole("button", { name: "Save current checkpoint", exact: true })
    .click();
  await section.getByRole("heading", { name: /Ready for rehearsal/ }).waitFor();
  assert.deepEqual(await head(), baseline);
  const first = await catalog();
  assert.equal(
    first.items[0].note,
    "Keep the reviewed baseline.\nSecond line preserved.",
  );
  checks.push(
    "Saving a named checkpoint preserves current revision and package hash",
  );

  // Concurrent writer modifies only this owned fixture's metadata.
  await call("presentation.workspace.save_checkpoint", {
    project_id: projectId,
    document_id: documentId,
    expected_revision_id: baseline.revision,
    expected_token: first.current_record_token,
    name: "Concurrent checkpoint",
    note: "",
  });
  await section
    .getByLabel("Checkpoint name", { exact: true })
    .fill("My unsaved label");
  await section
    .getByRole("button", { name: "Save current checkpoint", exact: true })
    .click();
  await section
    .getByRole("alert")
    .getByText(/checkpoint changed/i)
    .waitFor();
  assert.equal(
    await section.getByLabel("Checkpoint name", { exact: true }).inputValue(),
    "My unsaved label",
  );
  await section
    .getByRole("button", { name: "Reload checkpoints", exact: true })
    .click();
  await section
    .getByRole("heading", { name: /Concurrent checkpoint/ })
    .waitFor();
  await section
    .getByRole("button", { name: "Save current checkpoint", exact: true })
    .click();
  await section.getByRole("heading", { name: /My unsaved label/ }).waitFor();
  await section
    .getByRole("button", {
      name: "Remove checkpoint label My unsaved label",
      exact: true,
    })
    .click();
  await section
    .getByText("No named checkpoints yet.", { exact: true })
    .waitFor();
  assert.deepEqual(await head(), baseline);
  await section
    .getByLabel("Checkpoint name", { exact: true })
    .fill("Ready for rehearsal");
  await section
    .getByRole("button", { name: "Save current checkpoint", exact: true })
    .click();
  await section.getByRole("heading", { name: /Ready for rehearsal/ }).waitFor();
  checks.push(
    "Concurrent label writes fail without losing draft text; reload, rename, remove and save preserve deck bytes",
  );

  await page
    .getByRole("group", { name: "Slide studio panels", exact: true })
    .getByRole("button", { name: "Text", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Edit slide together", exact: true })
    .click();
  const review = page.getByRole("dialog", {
    name: "Review slide edits",
    exact: true,
  });
  await review
    .getByRole("textbox", { name: "Slide text 1", exact: true })
    .fill("Checkpoint revision two");
  await review
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await review.getByRole("img").waitFor();
  await review.getByRole("checkbox").check();
  await review
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await review.waitFor({ state: "hidden" });
  await history();
  await section
    .getByLabel("Checkpoint name", { exact: true })
    .fill("Ready for audience");
  await section
    .getByRole("button", { name: "Save current checkpoint", exact: true })
    .click();
  await section.getByRole("heading", { name: /Ready for audience/ }).waitFor();
  const edited = await head();
  assert.notEqual(edited.revision, baseline.revision);
  assert.equal((await catalog()).items.length, 2);
  await page.screenshot({ path: path.join(output, "two-checkpoints.png") });
  await app.close();
  app = null;
  await launch(!!packagedExecutable);
  await page
    .getByRole("button", { name: "Checkpoint acceptance", exact: true })
    .click();
  await workspace();
  section = page.getByRole("region", {
    name: "Named revision checkpoints",
    exact: true,
  });
  await section.getByRole("heading", { name: /Ready for audience/ }).waitFor();
  assert.deepEqual(await head(), edited);
  await section
    .getByRole("button", {
      name: "Restore checkpoint Ready for rehearsal",
      exact: true,
    })
    .click();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  assert.deepEqual(await head(), baseline);
  assert.equal((await catalog()).items.length, 2);
  await page.screenshot({ path: path.join(output, "restored-checkpoint.png") });
  await page
    .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
    .waitFor();
  await page.waitForFunction(() =>
    [...document.querySelectorAll("button")].some(
      (button) =>
        button.textContent === "Reload checkpoints" && !button.disabled,
    ),
  );
  const longName = "A".repeat(80);
  await section.getByLabel("Checkpoint name", { exact: true }).fill(longName);
  await section
    .getByRole("button", { name: "Save current checkpoint", exact: true })
    .click();
  await section.getByRole("heading", { name: new RegExp(longName) }).waitFor();
  await app.evaluate(({ BrowserWindow }) => {
    const owned = BrowserWindow.getAllWindows().find((candidate) =>
      candidate.webContents.getURL().endsWith("/renderer/index.html"),
    );
    owned.setSize(720, 520);
  });
  await page.waitForFunction(() => window.innerWidth <= 720);

  await section.scrollIntoViewIfNeeded();
  assert.equal(
    await section.evaluate(
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
  assert.equal(
    await section.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      return (
        bounds.left >= 0 &&
        bounds.right <= window.innerWidth + 1 &&
        [...element.querySelectorAll("button,input,textarea")].every(
          (control) =>
            control.getBoundingClientRect().right <= window.innerWidth + 1,
        )
      );
    }),
    true,
  );
  await page.screenshot({ path: path.join(output, "minimum-window.png") });
  checks.push(
    "Real Electron restart retains both checkpoint labels; restore selects exact baseline revision/hash and keeps both labels",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, temporary }, null, 2),
  );
  console.log(JSON.stringify({ checks, errors }, null, 2));
} catch (e) {
  if (page) {
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
    console.error(
      (
        await page
          .locator("body")
          .innerText()
          .catch(() => "")
      ).slice(-7000),
    );
  }
  throw e;
} finally {
  if (app) await app.close();
}
