/* global window */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

// Actual Electron/Core/native PPTX for the added chart types.
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
  path.join(os.tmpdir(), "presenter-chart-types-"),
);
const output =
  process.env.PRESENTER_NATIVE_OUTPUT ||
  path.join(root, ".local", "ui-validation", "chart-types");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "charts.pptx");
execFileSync(
  python,
  [
    "-c",
    String.raw`
import sys
from pptx import Presentation
deck=Presentation()
for _ in range(2): deck.slides.add_slide(deck.slide_layouts[6])
deck.save(sys.argv[1])
`,
    fixture,
  ],
  { cwd: root, windowsHide: true, stdio: "pipe" },
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
  PRESENTER_COPILOT_TEST_ASR: "deterministic_fake",
});
const checks = [];
const errors = [];
let app;
let page;
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
  page.setDefaultTimeout(30_000);
  page.on("pageerror", (error) => errors.push(error.message));
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill("Chart types acceptance");
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
  await page.getByRole("button", { name: /charts\.pptx/ }).waitFor();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  const workspace = page.locator(".presentation-workspace");
  await workspace.getByText("Current · Revision 1", { exact: true }).waitFor();
  const ask = async (method, params) =>
    page.evaluate(
      async ({ method, params }) => {
        const r = await window.presenterCopilot.core.request(method, params);
        if (!r.ok) throw new Error(`${r.error.code}: ${r.error.message}`);
        return r.result;
      },
      { method, params },
    );
  const project = (await ask("project.list", {})).projects.find(
    (item) => item.name === "Chart types acceptance",
  ).id;
  const document = (await ask("source.list", { project_id: project }))
    .sources[0].id;
  const charts = async (number) =>
    (
      await ask("presentation.workspace.list_charts", {
        project_id: project,
        document_id: document,
        revision_id: (
          await ask("presentation.workspace.list_revisions", {
            project_id: project,
            document_id: document,
          })
        ).current_revision_id,
        slide_number: number,
      })
    ).items;
  const slideButtons = page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button");
  for (const [number, kind, revision] of [
    [1, "doughnut", 2],
    [2, "stacked_column", 3],
  ]) {
    await slideButtons.nth(number - 1).click();
    const actions = page.getByText("Slide actions & layout", { exact: true });
    if (!(await actions.evaluate((element) => element.parentElement.open)))
      await actions.click();
    await page
      .getByRole("button", { name: "Native charts", exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: /Native charts on slide/ });
    await dialog
      .getByRole("textbox", { name: "Chart title", exact: true })
      .fill(`A ${kind} chart`);
    await dialog
      .getByRole("combobox", { name: "Chart type", exact: true })
      .selectOption(kind);
    await dialog
      .getByRole("button", { name: "Preview native chart", exact: true })
      .click();
    await dialog
      .getByRole("img", { name: "Proposed native chart", exact: true })
      .waitFor({ timeout: 30000 });
    await dialog
      .getByRole("checkbox", {
        name: "I reviewed this chart’s data, labels and placement.",
        exact: true,
      })
      .check();
    await page.screenshot({ path: path.join(output, `${kind}.png`) });
    await dialog
      .getByRole("button", { name: "Save reviewed native chart", exact: true })
      .click();
    await dialog.waitFor({ state: "detached" });
    await workspace
      .getByText(`Current · Revision ${revision}`, { exact: true })
      .waitFor();
    const created = await charts(number);
    assert.equal(created.length, 1);
    assert.equal(created[0].data.chart_type, kind);
    checks.push(`GUI creates a native ${kind} chart as one revision`);
  }
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors }, null, 2),
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
  if (app) await app.close();
}
