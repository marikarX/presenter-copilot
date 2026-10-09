/* global document, window */
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { _electron as electron } from "playwright";

const require = createRequire(import.meta.url);
const desktop = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const root = path.resolve(desktop, "../..");
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-outline-"));
const output = path.join(root, ".local", "outline-conversation");
await mkdir(output, { recursive: true });
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
  PRESENTER_COPILOT_TEST_ASR: "deterministic_fake",
});
const errors = [],
  checks = [];
let app, page;
async function noOverflow() {
  const issues = await page.evaluate(() =>
    [
      ...document.querySelectorAll(
        'body, [role="dialog"], .pw-outline-conversation, .pw-outline-changes',
      ),
    ]
      .filter(
        (element) =>
          element.getClientRects().length &&
          element.scrollWidth > element.clientWidth + 2,
      )
      .map((element) => element.className || element.tagName),
  );
  assert.deepEqual(issues, [], "No horizontal overflow at minimum window");
}
async function deckCount() {
  return page.evaluate(async () => {
    const projects = await window.presenterCopilot.core.request(
      "project.list",
      {},
    );
    if (!projects.ok || projects.result.projects.length !== 1)
      throw new Error("Expected the owned fixture project");
    const sources = await window.presenterCopilot.core.request("source.list", {
      project_id: projects.result.projects[0].id,
    });
    if (!sources.ok) throw new Error("Could not inspect owned fixture sources");
    return sources.result.sources.filter(
      (source) => source.kind === "presentation",
    ).length;
  });
}
try {
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
  page.setDefaultTimeout(15_000);
  page.on("pageerror", (error) => errors.push(error.message));
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByLabel("New project name", { exact: true })
    .fill("Outline history fixture");
  await page.keyboard.press("Enter");
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
    .getByLabel("Presentation objective", { exact: true })
    .fill("Approve a measured pilot");
  await dialog
    .getByLabel("Audience for this presentation", { exact: true })
    .fill("Small-window leadership");
  await dialog
    .getByLabel("Your briefing", { exact: true })
    .fill("Measure the decision against evidence.");
  await dialog.getByLabel("Number of slides", { exact: true }).fill("2");
  await dialog
    .getByRole("button", { name: "Propose outline", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Restore draft 1", exact: true })
    .waitFor();
  await dialog
    .getByLabel("Draft presentation title", { exact: true })
    .fill("Baseline small-screen draft");
  await dialog
    .getByLabel("Slide 1 points", { exact: true })
    .fill("BaselineWord".repeat(15));
  await dialog
    .getByLabel("Refine this draft", { exact: true })
    .fill("RefinementWord".repeat(30));
  await dialog
    .getByRole("button", { name: "Refine outline", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Restore draft 2", exact: true })
    .waitFor();
  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()
      .find((candidate) =>
        candidate.webContents.getURL().endsWith("/renderer/index.html"),
      )
      ?.setSize(720, 520);
  });
  const changes = dialog.locator(".pw-outline-changes");
  await changes.locator("summary").click();
  assert.match(await changes.innerText(), /Baseline small-screen draft/);
  assert.match(await changes.innerText(), /BaselineWord/);
  await changes.locator("summary").scrollIntoViewIfNeeded();
  await noOverflow();
  await page.screenshot({ path: path.join(output, "small-comparison.png") });
  await dialog
    .getByRole("button", { name: "Restore draft 1", exact: true })
    .click();
  assert.equal(
    await dialog
      .getByLabel("Draft presentation title", { exact: true })
      .inputValue(),
    "Baseline small-screen draft",
  );
  assert.equal(
    await dialog.getByLabel("Slide 1 points", { exact: true }).inputValue(),
    "BaselineWord".repeat(15),
  );
  await dialog
    .locator(".pw-outline-conversation summary")
    .scrollIntoViewIfNeeded();
  await noOverflow();
  await page.screenshot({
    path: path.join(output, "small-restored-history.png"),
  });
  checks.push(
    "720x520 history and before/current comparison wrap long request/point text, restore edited content and have no horizontal overflow",
  );
  for (let ordinal = 3; ordinal <= 10; ordinal++) {
    await dialog
      .getByLabel("Refine this draft", { exact: true })
      .fill(`Review alternative ${ordinal}.`);
    await dialog
      .getByRole("button", { name: "Refine outline", exact: true })
      .click();
    await dialog
      .getByRole("button", { name: `Restore draft ${ordinal}`, exact: true })
      .waitFor();
  }
  assert.equal(
    await dialog
      .getByRole("button", { name: "Refine outline", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(
    await dialog
      .getByRole("button", { name: "Review this outline", exact: true })
      .isEnabled(),
    true,
  );
  await dialog.getByText(/Conversation limit reached/).waitFor();
  await dialog
    .getByRole("button", { name: "Restore draft 1", exact: true })
    .click();
  assert.equal(
    await dialog
      .getByLabel("Draft presentation title", { exact: true })
      .inputValue(),
    "Baseline small-screen draft",
  );
  assert.equal(
    await dialog.locator(".pw-outline-conversation button").count(),
    10,
  );
  assert.equal(await deckCount(), 0);
  checks.push(
    "Ten-draft cap blocks further provider proposals while preserving all earlier drafts, restoration and explicit final review; no deck is created",
  );
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await dialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "New presentation", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Plan with Copilot", exact: true })
    .click();
  assert.equal(await dialog.locator(".pw-outline-conversation").count(), 0);
  assert.equal(
    await dialog
      .getByLabel("Presentation objective", { exact: true })
      .inputValue(),
    "",
  );
  assert.equal(await deckCount(), 0);
  checks.push(
    "Closing the temporary conversation leaves no deck and reopening starts a fresh planner",
  );
  assert.deepEqual(errors, []);
  const result = {
    checks,
    rendererErrors: errors,
    scope:
      "Final built Electron/local Core; disposable profile; deterministic local provider; no account/model or microphone calls",
  };
  await writeFile(
    path.join(output, "small-result.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify({ passed: checks.length, ...result }, null, 2));
} catch (error) {
  if (page) {
    await page
      .screenshot({ path: path.join(output, "small-failure.png") })
      .catch(() => {});
    console.error(
      await page
        .locator("body")
        .innerText()
        .catch(() => ""),
    );
  }
  throw error;
} finally {
  if (app) await app.close();
}
