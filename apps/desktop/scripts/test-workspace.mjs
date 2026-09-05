/* global document */
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-workspace-"));
const output = path.join(root, ".local", "ui-validation");
await mkdir(output, { recursive: true });
const env = { ...process.env };
for (const key of Object.keys(env)) {
  if (
    key.startsWith("PRESENTER_") ||
    key.startsWith("OPENAI_") ||
    key === "ELECTRON_RUN_AS_NODE"
  )
    delete env[key];
}
env.PRESENTER_COPILOT_DATA_ROOT = path.join(temporary, "core");
env.PRESENTER_CORE_DIR = path.join(root, "core");
env.PRESENTER_COPILOT_DEV_MODE = "1";
env.PRESENTER_COPILOT_TEST_PROVIDER = "deterministic_fake";
env.PRESENTER_COPILOT_TEST_ASR = "deterministic_fake";
const errors = [];
const checks = [];
let app;
let page;
async function launch() {
  app = await electron.launch({
    executablePath: require("electron"),
    args: [desktop, `--user-data-dir=${path.join(temporary, "browser")}`],
    cwd: root,
    env,
    timeout: 30_000,
  });
  // The hidden HUD can register with Playwright before the main renderer.
  page = undefined;
  const deadline = Date.now() + 30_000;
  while (!page && Date.now() < deadline) {
    page = app
      .windows()
      .find((candidate) => candidate.url().endsWith("/renderer/index.html"));
    if (!page) await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(page, "Main workspace window loaded");
  page.setDefaultTimeout(15_000);
  console.log("Main workspace loaded");
  page.on("pageerror", (error) => errors.push(error.message));
  await page
    .getByLabel("Core status: READY", { exact: true })
    .waitFor({ timeout: 30_000 });
}
async function shot(name) {
  await page.screenshot({ path: path.join(output, `${name}.png`) });
}
async function navigate(name) {
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name, exact: true })
    .click();
}
async function noOverflow(label) {
  const issues = await page.evaluate(() =>
    [...document.querySelectorAll("#workspace-content, .workspace-main, body")]
      .filter((element) => element.scrollWidth > element.clientWidth + 2)
      .map((element) => element.className || element.tagName),
  );
  assert.deepEqual(issues, [], `${label}: no horizontal overflow`);
}
try {
  await launch();
  await page.getByRole("dialog").waitFor();
  await shot("01-walkthrough");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  assert.match(await page.getByRole("dialog").innerText(), /Start with what/);
  await page.keyboard.press("Escape");
  assert.equal(await page.getByRole("dialog").count(), 0);
  checks.push("Fresh profile opens walkthrough; next and Escape work");
  await shot("02-home");
  await noOverflow("Home");
  await page.reload();
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  assert.equal(await page.getByRole("dialog").count(), 0);
  await page
    .getByRole("button", { name: "Restart walkthrough", exact: true })
    .click();
  for (let index = 0; index < 4; index++)
    await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Open setup", exact: true }).click();
  await page.getByRole("heading", { name: "Ready when you are." }).waitFor();
  await shot("03-setup");
  checks.push(
    "Dismissal survives reload; restart begins at step one; completion opens setup",
  );
  await page.getByRole("button", { name: "New project", exact: true }).click();
  assert.equal(
    await page
      .getByRole("button", { name: "Create project", exact: true })
      .isDisabled(),
    true,
  );
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill("Quarterly strategy review");
  await page.keyboard.press("Enter");
  await page
    .getByRole("heading", { name: "Sources", exact: true })
    .first()
    .waitFor();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .waitFor();
  await shot("04-sources");
  await navigate("Overview");
  await shot("05-overview");
  await navigate("Sources");
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("transcript");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  await page.getByRole("dialog").waitFor();
  assert.match(
    await page.getByRole("dialog").innerText(),
    /authorized to use this transcript/,
  );
  await page.keyboard.press("Escape");
  checks.push(
    "Project creation uses real core; transcript authorization still precedes picker",
  );
  const fixture = path.join(temporary, "strategy-notes.md");
  await writeFile(
    fixture,
    "# Strategy review\n\nThe proposed service targets a recovery time of 15 minutes.\n",
  );
  // Substitute only the native picker result. Main-process import and parsing remain real.
  await app.evaluate(({ dialog }, fixturePath) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [fixturePath],
    });
  }, fixture);
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("supporting");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  await page.getByRole("button", { name: /strategy-notes.md/ }).waitFor();
  await page.getByRole("button", { name: /strategy-notes.md/ }).click();
  await page
    .getByText("The proposed service targets a recovery time of 15 minutes.")
    .waitFor();
  await shot("07-imported-source");
  checks.push(
    "Native-picker test substitution imports and previews a real synthetic Markdown source",
  );
  if (
    await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .count()
  )
    await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .click();
  await navigate("Teach");
  await page.getByRole("button", { name: "Start Teach", exact: true }).click();
  await page
    .getByLabel("Your explanation", { exact: true })
    .fill("Keep this draft while I review my audience.");
  await navigate("Audience");
  await navigate("Teach");
  assert.equal(
    await page.getByLabel("Your explanation", { exact: true }).inputValue(),
    "Keep this draft while I review my audience.",
  );
  checks.push(
    "A real Teach session and its unsaved answer survive mode navigation",
  );
  await navigate("Audience");
  await page.getByLabel("Display name", { exact: true }).fill("Test audience");
  await page
    .getByRole("button", { name: "Create profile", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Test audience", exact: true })
    .waitFor();
  await navigate("Challenge");
  const challengeProfile = page.locator(".challenge-profile-option").filter({
    hasText: "Test audience",
  });
  await challengeProfile.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Start Challenge", exact: true })
    .click();
  await page
    .getByLabel("Your typed answer", { exact: true })
    .fill("Keep this Challenge draft while I review the rehearsal flow.");
  await navigate("Run");
  await page.getByRole("button", { name: "Start Run", exact: true }).click();
  await page.getByRole("button", { name: "Stop Run", exact: true }).click();
  await page.getByRole("button", { name: "Start Run", exact: true }).waitFor();
  await navigate("Teach");
  assert.equal(
    await page.getByLabel("Your explanation", { exact: true }).inputValue(),
    "Keep this draft while I review my audience.",
  );
  await navigate("Challenge");
  assert.equal(
    await page.getByLabel("Your typed answer", { exact: true }).inputValue(),
    "Keep this Challenge draft while I review the rehearsal flow.",
  );
  checks.push(
    "Teach and Challenge drafts survive a deterministic Run start and stop",
  );
  for (const name of [
    "Audience",
    "Teach",
    "Challenge",
    "Run",
    "Live Assist",
    "Project settings",
  ]) {
    await navigate(name);
    await noOverflow(name);
    await shot(`view-${name.toLowerCase().replaceAll(" ", "-")}`);
  }
  await page
    .getByLabel("Project name", { exact: true })
    .fill("Draft project name");
  await page
    .getByLabel("Privacy mode", { exact: true })
    .selectOption("selected_context_cloud");
  await page.getByLabel("Style policy", { exact: true }).selectOption("custom");
  await page
    .getByLabel("Custom guidance", { exact: true })
    .fill("Keep the explanation grounded in the approved project voice.");
  await page
    .getByLabel(/Use this project style override/, { exact: false })
    .check();
  await navigate("Sources");
  await navigate("Project settings");
  await page
    .getByRole("button", { name: "Quarterly strategy review", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Quarterly strategy review", exact: true })
    .first()
    .waitFor();
  await navigate("Project settings");
  assert.equal(
    await page.getByLabel("Project name", { exact: true }).inputValue(),
    "Draft project name",
  );
  assert.equal(
    await page.getByLabel("Privacy mode", { exact: true }).inputValue(),
    "selected_context_cloud",
  );
  assert.equal(
    await page.getByLabel("Style policy", { exact: true }).inputValue(),
    "custom",
  );
  assert.equal(
    await page.getByLabel("Custom guidance", { exact: true }).inputValue(),
    "Keep the explanation grounded in the approved project voice.",
  );
  assert.equal(
    await page
      .getByLabel(/Use this project style override/, { exact: false })
      .isChecked(),
    true,
  );
  checks.push(
    "All project views render; unsaved settings survive navigation and current-project clicks",
  );
  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()
      .find((window) => !window.isDestroyed() && window.isVisible())
      ?.setSize(720, 520);
  });
  await noOverflow("Minimum window");
  assert.ok(
    (await page
      .locator(".sidebar-projects")
      .evaluate((element) => element.clientHeight)) >= 100,
  );
  await shot("06-minimum-window");
  await page.getByRole("button", { name: "Hide sidebar", exact: true }).click();
  await page
    .getByRole("button", { name: "Show sidebar", exact: true })
    .waitFor();
  await page.getByRole("button", { name: "Show sidebar", exact: true }).click();
  checks.push("Minimum 720x520 window and sidebar collapse work");
  await app.close();
  app = undefined;
  await launch();
  assert.equal(await page.getByRole("dialog").count(), 0);
  assert.equal(
    await page
      .getByRole("button", { name: "Quarterly strategy review", exact: true })
      .count(),
    1,
  );
  checks.push(
    "Project and walkthrough dismissal survive full Electron restart",
  );
  assert.deepEqual(errors, [], "No renderer exceptions");
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      {
        checks,
        rendererErrors: errors,
        scope:
          "Real Electron and local core; disposable profile; deterministic fake capture only; no hardware microphone, model downloads, or remote provider calls",
      },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({ passed: checks.length, checks, output }, null, 2),
  );
} catch (error) {
  if (page) {
    await shot("failure").catch(() => {});
    console.error(
      (
        await page
          .locator("body")
          .innerText()
          .catch(() => "")
      ).slice(0, 8000),
    );
  }
  throw error;
} finally {
  if (app) await app.close();
}
