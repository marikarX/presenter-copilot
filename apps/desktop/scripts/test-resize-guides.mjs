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
  path.join(root, ".local", "resize-guides", "gui");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "presentation.pptx");
const route = "resize-guides";
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
from pptx.util import Inches
from pptx.enum.shapes import MSO_SHAPE
presentation = Presentation()
presentation.slide_width = Inches(10)
presentation.slide_height = Inches(5.625)
slide = presentation.slides.add_slide(presentation.slide_layouts[6])
for name,x,y,w,h in [('Moving A',1,1,1,0.5),('Moving B',2.5,1,1,0.5),('Reference',6.37,3,1,0.5)]:
    shape=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h))
    shape.name=name
    shape.text=name
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

  const baseline = await head();
  async function catalog() {
    return page.evaluate(
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
        const source = sources.result.sources.find(
          (item) => item.original_name === "presentation.pptx",
        );
        const reply = await window.presenterCopilot.core.request(
          "presentation.workspace.list_text_targets",
          {
            project_id: project.id,
            document_id: source.id,
            revision_id: revisionId,
            slide_number: 1,
          },
        );
        if (!reply.ok) throw new Error("Owned geometry catalog unavailable");
        return reply.result;
      },
      (await head()).revisionId,
    );
  }
  const before = await catalog();
  const overlay = page.getByLabel("Select slide objects", { exact: true });
  const guidesToggle = page.getByRole("checkbox", {
    name: "Align dragging and resizing to slide and nearby object edges and centers",
    exact: true,
  });
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .check();
  assert.equal(await guidesToggle.isChecked(), false);
  await guidesToggle.check();
  await page
    .getByRole("checkbox", {
      name: "Snap object dragging and resizing to 0.1 inch increments",
      exact: true,
    })
    .check();
  const moving = overlay.getByRole("button", {
    name: "Select Moving A on slide",
    exact: true,
  });
  const second = overlay.getByRole("button", {
    name: "Select Moving B on slide",
    exact: true,
  });

  const dialog = page.getByRole("dialog", {
    name: "Review object layout",
    exact: true,
  });
  const unit = 914400;
  async function resize({
    multi = false,
    proportional = false,
    bypass = false,
    cancel = false,
    label = "right",
    dx,
    dy = 0,
  } = {}) {
    await moving.click();
    if (multi) await second.click({ modifiers: ["Shift"] });
    await overlay.scrollIntoViewIfNeeded();
    const frame = await overlay.boundingBox();
    const handle = await overlay
      .getByRole("button", { name: `Resize selection ${label}`, exact: true })
      .boundingBox();
    assert.ok(frame && handle);
    if (proportional) await page.keyboard.down("Shift");
    if (bypass) await page.keyboard.down("Alt");
    const x = handle.x + handle.width / 2,
      y = handle.y + handle.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(
      x + (dx * frame.width) / 10,
      y + (dy * frame.height) / 5.625,
      { steps: 8 },
    );
    if (bypass)
      assert.equal(await overlay.locator(".pw-alignment-guide").count(), 0);
    else if (!cancel) {
      const positions = await overlay
        .locator(".pw-alignment-guide")
        .evaluateAll((lines) =>
          lines
            .filter(
              (line) => line.getAttribute("x1") === line.getAttribute("x2"),
            )
            .map((line) => Number(line.getAttribute("x1"))),
        );
      assert.ok(
        positions.some((value) => Math.abs(value - 6.37 * 914400) < 1),
        JSON.stringify(positions),
      );
      await page.screenshot({
        path: path.join(
          output,
          `${multi ? "multi" : proportional ? "shift" : "single"}-resize-guide.png`,
        ),
      });
    }
    if (cancel) await page.keyboard.press("Escape");
    await page.mouse.up();
    if (proportional) await page.keyboard.up("Shift");
    if (bypass) await page.keyboard.up("Alt");
    if (cancel) {
      assert.equal(await dialog.count(), 0);
      assert.equal(await overlay.locator(".pw-alignment-guide").count(), 0);
    } else await dialog.waitFor();
  }
  // Exercise every actual pointer handle without committing a plan.
  for (const label of [
    "top left",
    "top",
    "top right",
    "right",
    "bottom right",
    "bottom",
    "bottom left",
    "left",
  ]) {
    await resize({ label, dx: 0.2, dy: 0.2, cancel: true });
    assert.deepEqual(await head(), baseline);
  }
  checks.push(
    "All eight resize handles cancel with Escape, clearing guides and preserving exact revision bytes",
  );
  for (const mode of [
    { multi: false, proportional: false },
    { multi: true, proportional: false },
    { multi: false, proportional: true },
  ]) {
    await resize({
      ...mode,
      label: mode.proportional ? "bottom right" : "right",
      dx: mode.multi ? 2.86 : 4.36,
    });
    await dialog
      .getByRole("button", { name: "Preview all changes", exact: true })
      .click();
    await nativeReady(dialog);
    const receipt = await app.evaluate(() =>
      globalThis.nativePlanReceipts.at(-1),
    );
    await dialog.getByRole("checkbox").check();
    await page.screenshot({
      path: path.join(
        output,
        `${mode.multi ? "multi" : mode.proportional ? "shift" : "single"}-native-review.png`,
      ),
    });
    assert.deepEqual(await head(), baseline);
    await dialog
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .click();
    await dialog.waitFor({ state: "hidden" });
    assert.equal((await head()).sha256, receipt.sha256);
    const after = await catalog();
    const a = after.objects.find((item) => item.name === "Moving A").geometry;
    const b = after.objects.find((item) => item.name === "Moving B").geometry;
    const reference = after.objects.find(
      (item) => item.name === "Reference",
    ).geometry;
    assert.equal(a.x_emu, unit);
    assert.equal(a.y_emu, unit);
    const right = mode.multi ? b : a;
    assert.equal(right.x_emu + right.width_emu, reference.x_emu);
    if (mode.proportional)
      assert.ok(Math.abs(a.width_emu - 2 * a.height_emu) <= 1);
    else assert.equal(a.height_emu, 0.5 * unit);
    if (mode.multi) {
      assert.equal(b.y_emu, unit);
      assert.equal(b.height_emu, 0.5 * unit);
      assert.ok(Math.abs((b.x_emu - a.x_emu) / a.width_emu - 1.5) < 0.00001);
    } else assert.equal(b.x_emu, 2.5 * unit);
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await page
      .getByText("Current \u00b7 Revision 1", { exact: true })
      .waitFor();
    assert.deepEqual(await head(), baseline);
    checks.push(
      `${mode.multi ? "Multi-object" : mode.proportional ? "Shift proportional" : "Single-object"} guided resize saves exact native edge and opposite anchor, with exact reviewed SHA and one byte-restoring Undo`,
    );
  }
  await resize({ bypass: true, dx: 4.31 });
  await dialog
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await nativeReady(dialog);
  const bypassReceipt = await app.evaluate(() =>
    globalThis.nativePlanReceipts.at(-1),
  );
  await dialog.getByRole("checkbox").check();
  await dialog
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await dialog.waitFor({ state: "hidden" });
  assert.equal((await head()).sha256, bypassReceipt.sha256);
  const bypassed = (await catalog()).objects.find(
    (item) => item.name === "Moving A",
  ).geometry;
  assert.equal(bypassed.width_emu, 5.3 * unit);
  assert.equal(bypassed.x_emu, unit);
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  assert.deepEqual(await head(), baseline);
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()
      .find((item) =>
        item.webContents.getURL().endsWith("/renderer/index.html"),
      )
      .setSize(720, 520),
  );
  await page.waitForFunction(() => window.innerWidth <= 720);
  await resize({ multi: true, dx: 2.86 });
  assert.equal(
    await dialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
    true,
  );
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await dialog.waitFor({ state: "hidden" });
  assert.deepEqual(await head(), baseline);
  checks.push(
    "Alt bypass retains resize grid; minimum-window multi-object resize review remains contained and discardable",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, before }, null, 2),
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
