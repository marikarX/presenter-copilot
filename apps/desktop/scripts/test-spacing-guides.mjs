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
  path.join(root, ".local", "spacing-guides", "gui");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "presentation.pptx");
const route = "guides";
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
for name,x,y,w,h in [('Moving A',1,4.5,0.8,0.5),('Moving B',2,4.5,0.8,0.5),('Left',3,1,1,0.5),('Right',6,1,1,0.5),('Top',8,2,1,0.5),('Bottom',8,4,1,0.5)]:
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
    name: "Review dragged objects",
    exact: true,
  });
  const unit = 914400;
  async function drag(
    x,
    y,
    { multi = false, bypass = false, cancel = false, name = "spacing" } = {},
  ) {
    await moving.click();
    if (multi) await second.click({ modifiers: ["Shift"] });
    await overlay.scrollIntoViewIfNeeded();
    const frame = await overlay.boundingBox(),
      pick = await moving.boundingBox();
    assert.ok(frame && pick);
    const px = pick.x + pick.width / 2,
      py = pick.y + pick.height / 2;
    if (bypass) await page.keyboard.down("Alt");
    await page.mouse.move(px, py);
    await page.mouse.down();
    await page.mouse.move(
      px + ((x - 1) * frame.width) / 10,
      py + ((y - 4.5) * frame.height) / 5.625,
      { steps: 8 },
    );
    if (bypass)
      assert.equal(await overlay.locator(".pw-spacing-guide").count(), 0);
    else {
      await overlay
        .locator(".pw-spacing-guide")
        .first()
        .waitFor({ state: "attached" });
      const segments = await overlay
        .locator(".pw-spacing-guide > line:first-child")
        .evaluateAll((lines) =>
          lines.map((line) =>
            Math.hypot(
              Number(line.getAttribute("x2")) - Number(line.getAttribute("x1")),
              Number(line.getAttribute("y2")) - Number(line.getAttribute("y1")),
            ),
          ),
        );
      assert.equal(segments.length, 2);
      assert.ok(Math.abs(segments[0] - segments[1]) <= 1);
      await page.screenshot({ path: path.join(output, `${name}-guides.png`) });
    }
    if (cancel) await page.keyboard.press("Escape");
    await page.mouse.up();
    if (bypass) await page.keyboard.up("Alt");
    if (cancel) {
      assert.equal(await dialog.count(), 0);
      assert.equal(await overlay.locator(".pw-spacing-guide").count(), 0);
      assert.deepEqual(await head(), baseline);
    } else await dialog.waitFor();
  }
  const modes = [
    {
      name: "between",
      x: 4.6,
      y: 1,
      requestX: 4.59,
      multi: false,
      vertical: false,
    },
    {
      name: "before",
      x: 0.2,
      y: 1,
      requestX: 0.21,
      multi: false,
      vertical: false,
    },
    {
      name: "after",
      x: 9,
      y: 1,
      requestX: 8.99,
      multi: false,
      vertical: false,
    },
    {
      name: "multi",
      x: 4.1,
      y: 1,
      requestX: 4.09,
      multi: true,
      vertical: false,
    },
    {
      name: "vertical",
      x: 8,
      y: 3,
      requestX: 8,
      multi: false,
      vertical: true,
    },
  ];
  await drag(4.59, 1, { cancel: true, name: "cancel" });
  for (const mode of modes) {
    await drag(mode.requestX, mode.vertical ? 2.99 : mode.y, {
      multi: mode.multi,
      name: mode.name,
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
      path: path.join(output, `${mode.name}-native-review.png`),
    });
    assert.deepEqual(await head(), baseline);
    await dialog
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .click();
    await dialog.waitFor({ state: "hidden" });
    assert.equal((await head()).sha256, receipt.sha256);
    const objects = (await catalog()).objects;
    const a = objects.find((o) => o.name === "Moving A").geometry,
      b = objects.find((o) => o.name === "Moving B").geometry;
    assert.equal(a.x_emu, Math.round(mode.x * unit));
    assert.equal(a.y_emu, Math.round(mode.y * unit));
    assert.equal(a.width_emu, 0.8 * unit);
    assert.equal(a.height_emu, 0.5 * unit);
    const left = objects.find((o) => o.name === "Left").geometry,
      right = objects.find((o) => o.name === "Right").geometry;
    if (mode.multi) {
      assert.equal(b.x_emu - a.x_emu, unit);
      assert.equal(b.y_emu, a.y_emu);
      assert.equal(b.width_emu, 0.8 * unit);
    } else assert.equal(b.x_emu, 2 * unit);
    let gaps;
    if (mode.vertical) {
      const top = objects.find((o) => o.name === "Top").geometry,
        bottom = objects.find((o) => o.name === "Bottom").geometry;
      gaps = [
        a.y_emu - top.y_emu - top.height_emu,
        bottom.y_emu - a.y_emu - a.height_emu,
      ];
    } else if (mode.name === "before")
      gaps = [
        left.x_emu - a.x_emu - a.width_emu,
        right.x_emu - left.x_emu - left.width_emu,
      ];
    else if (mode.name === "after")
      gaps = [
        right.x_emu - left.x_emu - left.width_emu,
        a.x_emu - right.x_emu - right.width_emu,
      ];
    else
      gaps = [
        a.x_emu - left.x_emu - left.width_emu,
        right.x_emu -
          (mode.multi ? b : a).x_emu -
          (mode.multi ? b : a).width_emu,
      ];
    assert.equal(gaps[0], gaps[1]);
    assert.ok(gaps[0] > 0);
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await page
      .getByText("Current \u00b7 Revision 1", { exact: true })
      .waitFor();
    assert.deepEqual(await head(), baseline);
    checks.push(
      `${mode.name}: paired gap guides match exact native equal spacing, preserved selection geometry, reviewed SHA and one byte-restoring Undo`,
    );
  }
  await drag(4.59, 1, { bypass: true });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await dialog.waitFor({ state: "hidden" });
  assert.deepEqual(await head(), baseline);
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()
      .find((item) =>
        item.webContents.getURL().endsWith("/renderer/index.html"),
      )
      .setSize(720, 520),
  );
  await page.waitForFunction(() => window.innerWidth <= 720);
  await drag(4.09, 1, { multi: true, name: "minimum-window" });
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
    "Escape clears gap guides without changing bytes; Alt bypass omits gap guides; minimum-window multi-object review is contained and discardable",
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
