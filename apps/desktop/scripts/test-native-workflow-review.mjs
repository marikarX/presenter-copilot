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
  path.join(root, ".local", "remaining-native-review", "gui");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "presentation.pptx");
const route = process.env.PRESENTER_NATIVE_REVIEW || "text-fit";
assert.ok(
  [
    "text-fit",
    "diagram",
    "diagram-update",
    "diagram-delete",
    "insert",
    "appendix-move",
    "appendix-copy",
  ].includes(route),
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
from pptx.util import Inches, Pt
presentation = Presentation()
for i in range(3):
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    shape = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(6), Inches(0.3))
    shape.name = 'Owned review text'
    shape.text = f'Owned detail {i+1}: measured pilot evidence and review outcomes.'
    for paragraph in shape.text_frame.paragraphs:
        paragraph.font.name = 'Arial'
        paragraph.font.size = Pt(28)
if sys.argv[2] in ('diagram-update', 'diagram-delete'):
    from pathlib import Path
    sys.path.insert(0, str(Path.cwd() / 'core'))
    from presenter_core.presentation.diagrams import generated, keys, validate_data
    from presenter_core.presentation.fidelity import FidelityGeometry
    data = validate_data({'name': 'Owned pilot', 'kind': 'process', 'palette': 'classic', 'nodes': [{'id': 'a', 'label': 'Prepare', 'parent': None}, {'id': 'b', 'label': 'Review', 'parent': None}]})
    native = {key: str(i+10) for i,key in enumerate(keys(data))}
    group = generated(data, FidelityGeometry(500000, 1500000, 7000000, 2200000), native)
    slide = presentation.slides[0]
    slide.shapes._spTree.insert_element_before(group, 'p:extLst')
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
  }

  const baseline = await head();
  const config =
    route === "text-fit"
      ? {
          opener: "Fit text box",
          preview: "Preview text fit",
          save: "Save reviewed text fit",
          discard: "Discard text fit preview",
          alt: "Proposed text fit",
          ack: "I reviewed the fitted text, wrapping and nearby content.",
          ordinal: 1,
        }
      : route.startsWith("diagram")
        ? {
            opener: "Native diagrams",
            preview: "Preview native diagram",
            save: "Save reviewed native diagram",
            discard: "Discard native diagram preview",
            alt: "Proposed native diagram",
            ack: "I reviewed this diagram on the current slide.",
            ordinal: 1,
          }
        : route === "insert"
          ? {
              opener: "Insert authored slide",
              preview: "Preview authored slide",
              save: "Save inserted slide",
              discard: "Discard / close",
              alt: "Proposed authored slide",
              ack: "I reviewed this slide and its notes.",
              ordinal: 2,
            }
          : {
              opener: "Create appendix",
              preview: "Preview appendix",
              save: "Save reviewed appendix",
              discard: "Discard / close",
              alt: "Proposed appendix slide",
              ack: "I reviewed the divider, every detail slide and the proposed order.",
              ordinal: route === "appendix-copy" ? 4 : 2,
            };
  const dialog = page.locator("dialog[open]");
  const ack = dialog.getByRole("checkbox", { name: config.ack, exact: true });
  const save = dialog.getByRole("button", { name: config.save, exact: true });
  async function openReview() {
    const actions = page.getByText("Slide actions & layout", { exact: true });
    if (
      (await actions.count()) &&
      !(await actions.evaluate((element) => element.parentElement.open))
    )
      await actions.click();
    await page
      .getByRole("button", { name: config.opener, exact: true })
      .click();
    await dialog.waitFor();
    if (route === "diagram-update" || route === "diagram-delete") {
      const choice = dialog.getByLabel("Native diagram", { exact: true });
      const option = choice.locator("option[value]:not([value=''])").first();
      await option.waitFor({ state: "attached" });
      await choice.selectOption(await option.getAttribute("value"));
    }
  }
  async function draft(changed = false) {
    if (route === "text-fit") {
      await dialog
        .getByLabel("Fit text box", { exact: true })
        .locator("option[value]:not([value=''])")
        .first()
        .waitFor({ state: "attached" });
      await dialog
        .getByLabel("Text fit strategy", { exact: true })
        .selectOption(changed ? "shrink" : "grow");
    } else if (route.startsWith("diagram")) {
      await dialog
        .getByLabel("Diagram name", { exact: true })
        .fill(changed ? "Revised pilot" : "Native pilot");
    } else if (route === "insert") {
      await dialog
        .getByLabel("Inserted slide title", { exact: true })
        .fill(changed ? "Revised native insertion" : "Native insertion review");
      await dialog
        .getByLabel("Inserted slide points", { exact: true })
        .fill("Measure outcomes\nApprove next step");
      await dialog
        .getByLabel("Inserted slide notes", { exact: true })
        .fill("Ask for explicit approval.");
    } else {
      const choices = dialog.getByLabel("Appendix detail slides", {
        exact: true,
      });
      const values = await choices
        .locator("option")
        .evaluateAll((options) => [options[0].value, options[2].value]);
      await choices.selectOption(values);
      await dialog
        .getByLabel("Appendix move or copy", { exact: true })
        .selectOption(route === "appendix-copy" ? "copy" : "move");
      await dialog
        .getByLabel("Appendix divider title", { exact: true })
        .fill(changed ? "Revised appendix" : "Native appendix");
    }
  }
  async function stage() {
    await dialog
      .getByRole("button", {
        name:
          route === "diagram-delete"
            ? "Preview diagram deletion"
            : config.preview,
        exact: true,
      })
      .click();
    await dialog.getByRole("img", { name: config.alt, exact: true }).waitFor();
    await page.waitForFunction((alt) => {
      const image = document.querySelector(`dialog[open] img[alt="${alt}"]`);
      return image?.complete && image.naturalWidth > 0;
    }, config.alt);
  }
  async function fullReview() {
    await nativeReady(dialog);
    const receipt = await app.evaluate(() =>
      globalThis.nativePlanReceipts.at(-1),
    );
    assert.equal(receipt.target.slide_number, config.ordinal);
    if (route.startsWith("appendix")) {
      assert.equal(await ack.isDisabled(), true);
      for (let i = 1; i <= 2; i++) {
        await dialog
          .getByRole("button", { name: "Next appendix preview", exact: true })
          .click();
        await nativeReady(dialog);
        await dialog
          .getByText(`Viewed ${i + 1} of 3 appendix slides.`, { exact: true })
          .waitFor();
        assert.equal(
          (await app.evaluate(() => globalThis.nativePlanReceipts.at(-1)))
            .target.slide_number,
          config.ordinal + i,
        );
      }
    }
    return receipt;
  }
  await openReview();
  await draft();
  await stage();
  const receipt = await fullReview();
  await ack.check();
  await dialog
    .getByRole("button", { name: "Browser appearance", exact: true })
    .click();
  await page.waitForFunction(
    (element) => !element.checked,
    await ack.elementHandle(),
  );
  assert.equal(await ack.isChecked(), false);
  await nativeReady(dialog);
  await ack.check();
  if (route === "insert")
    await dialog
      .getByText("Edit authored slide content", { exact: true })
      .click();
  if (route.startsWith("appendix"))
    await dialog.getByText("Edit appendix choices", { exact: true }).click();
  await draft(true);
  assert.equal(await save.isDisabled(), true);
  await draft();
  assert.equal(await ack.isChecked(), false);
  await stage();
  await fullReview();
  await ack.check();
  const savedReceipt = await app.evaluate(() =>
    globalThis.nativePlanReceipts.at(-1),
  );
  assert.deepEqual(await head(), baseline);
  await page.screenshot({ path: path.join(output, "native-review.png") });
  await save.click();
  await dialog.waitFor({ state: "hidden" });
  assert.equal((await head()).sha256, savedReceipt.sha256);
  if (route.startsWith("diagram")) {
    const reopened = await page.evaluate(
      async (revisionId) => {
        const projects = await window.presenterCopilot.core.request(
          "project.list",
          {},
        );
        const project = projects.result.projects.find(
          (item) => item.name === "Native appearance acceptance",
        );
        const sources = await window.presenterCopilot.core.request(
          "source.list",
          { project_id: project.id },
        );
        const document = sources.result.sources.find(
          (item) => item.original_name === "presentation.pptx",
        );
        const catalog = await window.presenterCopilot.core.request(
          "presentation.workspace.list_diagrams",
          {
            project_id: project.id,
            document_id: document.id,
            revision_id: revisionId,
            slide_number: 1,
          },
        );
        if (!catalog.ok)
          throw new Error("Reopened diagram metadata unavailable");
        return catalog.result.items;
      },
      (await head()).revisionId,
    );
    if (route === "diagram-delete") assert.equal(reopened.length, 0);
    else assert.equal(reopened[0].data.name, "Native pilot");
  }

  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  assert.deepEqual(await head(), baseline);
  // Restore the original current slide after insertion/appendix Save navigation.
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .first()
    .click();
  await app.evaluate(({ BrowserWindow }) => {
    const owned = BrowserWindow.getAllWindows().find((item) =>
      item.webContents.getURL().endsWith("/renderer/index.html"),
    );
    owned.setSize(720, 520);
  });
  await page.waitForFunction(() => window.innerWidth <= 720);
  await openReview();
  await draft();
  await stage();
  assert.equal(
    await dialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
    true,
  );
  await page.screenshot({ path: path.join(output, "minimum-window.png") });
  await app.evaluate(() => {
    globalThis.nativePlanHold = true;
  });
  await dialog
    .getByRole("button", { name: "PowerPoint appearance", exact: true })
    .click();
  await waitMain("nativePlanReady", true);
  assert.equal(await save.isDisabled(), true);
  assert.equal(await ack.isDisabled(), true);
  await dialog
    .getByRole("button", { name: config.discard, exact: true })
    .click();
  await dialog.waitFor({ state: "hidden" });
  await app.evaluate(() => {
    globalThis.nativePlanHold = false;
  });
  await waitMain("nativePlanPending", false);
  assert.deepEqual(await head(), baseline);
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
    `${route}: exact proposed native ordinal, fresh image/draft approval, exact Save and Undo`,
  );
  checks.push(
    `${route}: minimum-window containment, pending Save/approval guards and held reply Discard`,
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, receipt, savedReceipt }, null, 2),
  );
  console.log(JSON.stringify({ checks, errors }));
} catch (error) {
  if (page)
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
  throw error;
} finally {
  if (app) await app.close();
}
