/* global document, window */
import assert from "node:assert/strict";
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
  path.join(root, ".local", "native-edit-preview", "gui-acceptance");
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
let nativeModulePath;
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
  nativeModulePath = packagedExecutable
    ? await app.evaluate(
        ({ app }) => `${app.getAppPath()}/dist/main/native-edit-appearance.js`,
      )
    : path.join(desktop, "dist", "main", "native-edit-appearance.js");
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
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page
    .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
    .waitFor();
  await app.evaluate((_electron, filename) => {
    const module = process.mainModule.require(filename);
    const original = module.renderNativeEditAppearance;
    globalThis.nativePlanPending = false;
    globalThis.nativePlanHold = false;
    globalThis.nativePlanReady = false;
    globalThis.nativePlanReceipts = [];
    module.renderNativeEditAppearance = async (...args) => {
      globalThis.nativePlanPending = true;
      globalThis.nativePlanReady = false;
      try {
        const result = await original(...args);
        globalThis.nativePlanReceipts.push({
          target: args[0],
          sha256: result.source_sha256,
          planId: result.plan_id,
        });
        globalThis.nativePlanReady = true;
        const deadline = Date.now() + 125_000;
        while (globalThis.nativePlanHold && Date.now() < deadline)
          await new Promise((resolve) => setTimeout(resolve, 100));
        if (globalThis.nativePlanHold)
          throw new Error("Owned native-plan reply gate expired");
        return result;
      } finally {
        globalThis.nativePlanPending = false;
      }
    };
  }, nativeModulePath);

  async function head() {
    return page.evaluate(async () => {
      const projects = await window.presenterCopilot.core.request(
        "project.list",
        {},
      );
      if (!projects.ok) throw new Error("Could not list owned projects");
      const project = projects.result.projects.find(
        (item) => item.name === "Native appearance acceptance",
      );
      const sources = await window.presenterCopilot.core.request(
        "source.list",
        { project_id: project.id },
      );
      if (!sources.ok) throw new Error("Could not list owned sources");
      const document = sources.result.sources.find(
        (item) => item.original_name === "presentation.pptx",
      );
      const scope = { project_id: project.id, document_id: document.id };
      const opened = await window.presenterCopilot.core.request(
        "presentation.workspace.open_source",
        scope,
      );
      if (!opened.ok) throw new Error("Could not inspect current head");
      await window.presenterCopilot.core.request(
        "presentation.workspace.close_source",
        { ...scope, session_id: opened.result.session_id },
      );
      return {
        revisionId: opened.result.revision_id,
        revisionNumber: opened.result.revision_number,
        sha256: opened.result.sha256,
      };
    });
  }
  async function waitMain(field, expected) {
    const deadline = Date.now() + 125_000;
    while (Date.now() < deadline) {
      if (
        (await app.evaluate((_electron, key) => globalThis[key], field)) ===
        expected
      )
        return;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error(`Owned native-plan ${field} did not reach ${expected}`);
  }
  async function nativeReady(dialog) {
    await dialog
      .getByRole("button", { name: "PowerPoint appearance", exact: true })
      .click();
    await dialog
      .getByText(
        "Proposed slide appearance from PowerPoint. Changes are not saved.",
        { exact: true },
      )
      .waitFor({ timeout: 125_000 });
    await page.waitForFunction(() => {
      return [
        ...document.querySelectorAll(
          'dialog[open] img:not([alt="Current native layout baseline"])',
        ),
      ].some((image) => image.complete && image.naturalWidth === 960);
    });
    await dialog
      .getByText("The proposed slide appearance comes from PowerPoint.", {
        exact: false,
      })
      .waitFor();
  }
  async function restored() {
    await page
      .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
      .waitFor();
    await page
      .getByRole("button", { name: "Edit slide together", exact: true })
      .waitFor();
  }
  const baseline = await head();
  async function openSlideActions() {
    const toggle = page.getByText("Slide actions & layout", { exact: true });
    if (!(await toggle.evaluate((element) => element.parentElement.open)))
      await toggle.click();
  }
  await openSlideActions();
  await page
    .getByRole("button", { name: "Insert from native layout", exact: true })
    .click();
  const insertion = page.getByRole("dialog", {
    name: /Insert native slide after slide/,
  });
  const slots = insertion.locator(
    'textarea[aria-label^="Native placeholder:"]',
  );
  await slots.first().waitFor();
  await slots.first().fill("PowerPoint-reviewed native layout insertion");
  await insertion
    .getByRole("textbox", { name: "Native slide speaker notes", exact: true })
    .fill("Owned native insertion acceptance.");
  await insertion
    .getByRole("button", { name: "Preview native slide", exact: true })
    .click();
  await insertion
    .getByRole("img", { name: "Proposed native slide", exact: true })
    .waitFor();
  await insertion.getByRole("checkbox").check();
  await nativeReady(insertion);
  assert.equal(await insertion.getByRole("checkbox").isChecked(), false);
  const insertionSave = insertion.getByRole("button", {
    name: "Save reviewed native slide",
    exact: true,
  });
  assert.equal(await insertionSave.isDisabled(), true);
  await insertion.getByRole("checkbox").check();
  const insertionReceipt = await app.evaluate(() =>
    globalThis.nativePlanReceipts.at(-1),
  );
  assert.equal(insertionReceipt.target.slide_number, 2);
  assert.deepEqual(await head(), baseline);
  await page.screenshot({
    path: path.join(output, "layout-insertion-native.png"),
  });
  await insertionSave.click();
  await insertion.waitFor({ state: "hidden" });
  assert.equal((await head()).sha256, insertionReceipt.sha256);
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  await restored();
  assert.deepEqual(await head(), baseline);
  checks.push(
    "Native layout insertion renders staged slide 2, resets prior approval, saves exact native-reviewed bytes and undoes to baseline",
  );

  await openSlideActions();
  await page
    .getByRole("button", { name: "Browse native layouts", exact: true })
    .click();
  const layouts = page.getByRole("dialog", {
    name: /Native layouts for slide/,
  });
  await layouts
    .getByRole("img", { name: "Current native layout baseline", exact: true })
    .waitFor();
  await layouts
    .getByRole("button", { name: "Preview native layout", exact: true })
    .click();
  await layouts
    .getByRole("img", { name: "Proposed native layout", exact: true })
    .waitFor();
  await nativeReady(layouts);
  await layouts.getByRole("checkbox").check();
  await layouts
    .getByRole("button", { name: "Browser appearance", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelector('dialog[open] input[type="checkbox"]')?.checked ===
      false,
  );
  await nativeReady(layouts);
  await layouts.getByRole("checkbox").check();
  const layoutReceipt = await app.evaluate(() =>
    globalThis.nativePlanReceipts.at(-1),
  );
  await page.screenshot({
    path: path.join(output, "layout-application-native.png"),
  });
  await layouts
    .getByRole("button", { name: "Save reviewed native layout", exact: true })
    .click();
  await layouts.waitFor({ state: "hidden" });
  assert.equal((await head()).sha256, layoutReceipt.sha256);
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  await restored();
  assert.deepEqual(await head(), baseline);
  checks.push(
    "Native layout application requires fresh approval after Browser/PowerPoint switching, saves exact reviewed bytes and undoes to baseline",
  );

  await page
    .getByRole("button", { name: "Edit slide together", exact: true })
    .click();
  const manual = page.getByRole("dialog", {
    name: "Review slide edits",
    exact: true,
  });
  await manual
    .getByRole("textbox", { name: "Slide text 1", exact: true })
    .fill("Native-reviewed exact-byte commit");
  await manual
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await manual.getByRole("img").waitFor();
  await nativeReady(manual);
  assert.deepEqual(await head(), baseline);
  await manual.getByRole("checkbox").check();
  const manualReceipt = await app.evaluate(() =>
    globalThis.nativePlanReceipts.at(-1),
  );
  await page.screenshot({
    path: path.join(output, "manual-native-reviewed.png"),
  });
  await manual
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await manual.waitFor({ state: "hidden" });
  await restored();
  const manualHead = await head();
  assert.equal(manualHead.sha256, manualReceipt.sha256);
  assert.notEqual(manualHead.revisionId, baseline.revisionId);
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  await restored();
  assert.deepEqual(await head(), baseline);
  checks.push(
    "Manual native-reviewed Save commits exactly the rendered package hash; Undo restores the original revision and hash",
  );

  if (!packagedExecutable) {
    let groupedHead;
    for (const instruction of [
      "Group two new pilot callouts.",
      "Ungroup the pilot callouts.",
    ]) {
      await page
        .getByRole("button", { name: "Ask Copilot to edit", exact: true })
        .click();
      const grouping = page.getByRole("dialog", {
        name: "Copilot edit plan",
        exact: true,
      });
      await grouping
        .getByLabel("Copilot edit request", { exact: true })
        .fill(instruction);
      await grouping
        .getByRole("button", { name: "Propose changes", exact: true })
        .click();
      await grouping
        .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
        .waitFor();
      await grouping
        .getByText(
          instruction.startsWith("Group")
            ? "Group native objects"
            : "Ungroup native objects",
          { exact: false },
        )
        .waitFor();
      assert.equal(
        await grouping
          .getByText("Previous table/chart data", { exact: true })
          .count(),
        0,
      );
      await nativeReady(grouping);
      await grouping.getByRole("checkbox").check();
      const receipt = await app.evaluate(() =>
        globalThis.nativePlanReceipts.at(-1),
      );
      await page.screenshot({
        path: path.join(
          output,
          instruction.startsWith("Group")
            ? "copilot-group-native.png"
            : "copilot-ungroup-native.png",
        ),
      });
      await grouping
        .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
        .scrollIntoViewIfNeeded();
      await page.screenshot({
        path: path.join(
          output,
          instruction.startsWith("Group")
            ? "copilot-group-slide-native.png"
            : "copilot-ungroup-slide-native.png",
        ),
      });
      await grouping
        .getByRole("button", { name: "Save Copilot changes", exact: true })
        .click();
      await grouping.waitFor({ state: "hidden" });
      await restored();
      const committed = await head();
      assert.equal(committed.sha256, receipt.sha256);
      if (instruction.startsWith("Group")) groupedHead = committed;
    }
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await page
      .getByText(`Current \u00b7 Revision ${groupedHead.revisionNumber}`, {
        exact: true,
      })
      .waitFor();
    await restored();
    assert.deepEqual(await head(), groupedHead);
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await page
      .getByText("Current \u00b7 Revision 1", { exact: true })
      .waitFor();
    await restored();
    assert.deepEqual(await head(), baseline);
    checks.push(
      "Copilot creates, positions and groups callouts through earlier-step references, ungroups the existing group, saves native-reviewed bytes twice and undoes both revisions",
    );
  }

  if (!packagedExecutable) {
    await page
      .getByRole("button", { name: "Ask Copilot to edit", exact: true })
      .click();
    const copilot = page.getByRole("dialog", {
      name: "Copilot edit plan",
      exact: true,
    });
    await copilot
      .getByLabel("Copilot edit request", { exact: true })
      .fill(
        "Clarify this slide's decision using the reviewed claim grounding.",
      );
    await copilot
      .getByRole("button", { name: "Propose changes", exact: true })
      .click();
    await copilot
      .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
      .waitFor();
    await app.evaluate(() => {
      globalThis.nativePlanHold = true;
    });
    await copilot
      .getByRole("button", { name: "PowerPoint appearance", exact: true })
      .click();
    await waitMain("nativePlanPending", true);
    await waitMain("nativePlanReady", true);
    const previous = await app.evaluate(() =>
      globalThis.nativePlanReceipts.at(-1),
    );
    await copilot
      .getByLabel("Copilot proposal refinement", { exact: true })
      .fill("Keep the title change and make the notes more specific.");
    await copilot
      .getByRole("button", { name: "Refine proposal", exact: true })
      .click();
    await page.waitForFunction(
      () =>
        document.querySelector(
          'textarea[aria-label="Copilot proposal refinement"]',
        )?.value === "",
    );
    await app.evaluate(() => {
      globalThis.nativePlanHold = false;
    });
    await waitMain("nativePlanPending", false);
    await copilot
      .getByRole("button", { name: "PowerPoint appearance", exact: true })
      .waitFor();
    assert.equal(
      await copilot
        .getByText(
          "Proposed slide appearance from PowerPoint. Changes are not saved.",
          { exact: true },
        )
        .count(),
      0,
    );
    assert.equal(await copilot.getByRole("checkbox").isChecked(), false);
    assert.deepEqual(await head(), baseline);
    await nativeReady(copilot);
    const refined = await app.evaluate(() =>
      globalThis.nativePlanReceipts.at(-1),
    );
    assert.notEqual(refined.planId, previous.planId);
    await copilot.getByRole("checkbox").check();
    await page.screenshot({
      path: path.join(output, "refined-native-reviewed.png"),
    });
    await copilot
      .getByRole("button", { name: "Save Copilot changes", exact: true })
      .click();
    await copilot.waitFor({ state: "detached" });
    await restored();
    const copilotHead = await head();
    assert.equal(copilotHead.sha256, refined.sha256);
    assert.notEqual(copilotHead.revisionId, baseline.revisionId);
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await page
      .getByText("Current \u00b7 Revision 1", { exact: true })
      .waitFor();
    await restored();
    assert.deepEqual(await head(), baseline);
    checks.push(
      "Refinement replaces the plan while a real native reply is delayed; stale frame is rejected, refined Save uses exact native-reviewed hash and Undo restores baseline",
    );

    await page
      .getByRole("button", { name: "Ask Copilot to edit", exact: true })
      .click();
    await copilot
      .getByLabel("Copilot edit request", { exact: true })
      .fill(
        "Clarify this slide's decision using the reviewed claim grounding.",
      );
    await copilot
      .getByRole("button", { name: "Propose changes", exact: true })
      .click();
    await copilot
      .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
      .waitFor();
    await app.evaluate(() => {
      globalThis.nativePlanHold = true;
    });
    await copilot
      .getByRole("button", { name: "PowerPoint appearance", exact: true })
      .click();
    await waitMain("nativePlanPending", true);
    await waitMain("nativePlanReady", true);
    const discarded = await app.evaluate(() =>
      globalThis.nativePlanReceipts.at(-1),
    );
    await copilot
      .getByRole("button", { name: "Discard Copilot proposal", exact: true })
      .click();
    await copilot.waitFor({ state: "detached" });
    await restored();
    await app.evaluate(() => {
      globalThis.nativePlanHold = false;
    });
    await waitMain("nativePlanPending", false);
    assert.deepEqual(await head(), baseline);
    const rejected = await page.evaluate(
      async (target) =>
        window.presenterCopilot.presentation.nativeEditPlanAppearance(
          target.project_id,
          target.document_id,
          target.expected_revision_id,
          target.plan_id,
          target.source_sha256,
          target.slide_number,
        ),
      discarded.target,
    );
    assert.equal(rejected.ok, false);
    assert.equal(
      await page
        .getByText(
          "Proposed slide appearance from PowerPoint. Changes are not saved.",
          { exact: true },
        )
        .count(),
      0,
    );
    checks.push(
      "Discard closes the review before a delayed native reply; reply cannot leak into saved view and discarded plan cannot render again",
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
