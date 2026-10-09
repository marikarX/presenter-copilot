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
  path.join(root, ".local", "native-live-canvas", "gui");
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
from pptx.dml.color import RGBColor
from pptx.oxml.xmlchemy import OxmlElement
presentation = Presentation()
presentation.slide_width = Inches(10)
presentation.slide_height = Inches(5.625)
slide = presentation.slides.add_slide(presentation.slide_layouts[6])
for name,x,y,w,h in [('Moving A',1,1,1,0.5),('Moving B',2.5,1,1,0.5),('Reference',6.37,3,1,0.5)]:
    shape=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h))
    shape.name=name
    shape.text=name
    if name in ['Moving A','Moving B']:
        shape.fill.solid()
        shape.fill.fore_color.rgb=RGBColor(*( (230,20,20) if name=='Moving A' else (20,160,60) ))
        shape.line.fill.background()
        if name=='Moving A':
            rgb=shape._element.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}solidFill/{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr')
            alpha=OxmlElement('a:alpha');alpha.set('val','65000');rgb.append(alpha)
other=presentation.slides.add_slide(presentation.slide_layouts[6])
other.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(1),Inches(1),Inches(2),Inches(1)).text='Other slide'
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
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .check();
  const overlay = page.getByLabel("Select slide objects", { exact: true });
  const moving = overlay.getByRole("button", {
    name: "Select Moving A on slide",
    exact: true,
  });
  const second = overlay.getByRole("button", {
    name: "Select Moving B on slide",
    exact: true,
  });
  const controls = page.getByRole("group", {
    name: "Live object dragging",
    exact: true,
  });
  async function prepare() {
    await controls
      .getByRole("button", { name: "Prepare live dragging", exact: true })
      .click();
    await controls
      .getByText(
        "Live dragging uses PowerPoint pixels. Drag to review a move; changes are saved only after review.",
        { exact: true },
      )
      .waitFor({ timeout: 125000 });
    await page.waitForFunction(
      () =>
        document.querySelectorAll(".pw-native-layers img").length === 4 &&
        [...document.querySelectorAll(".pw-native-layers img")].every(
          (i) => i.complete && i.naturalWidth === 960,
        ),
    );
    assert.equal(
      await page
        .getByRole("button", { name: "PowerPoint appearance", exact: true })
        .getAttribute("aria-pressed"),
      "true",
    );
    assert.equal(
      await page
        .locator(".pw-canvas > img")
        .evaluate((i) => window.getComputedStyle(i).opacity),
      "0",
    );
  }
  async function begin(dx, dy = 0, { multi = false } = {}) {
    await moving.click();
    if (multi) await second.click({ modifiers: ["Shift"] });
    await overlay.scrollIntoViewIfNeeded();
    const box = await overlay.boundingBox(),
      pick = await moving.boundingBox();
    assert.ok(box && pick);
    const x = pick.x + pick.width / 2,
      y = pick.y + pick.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(
      x + (dx * box.width) / 10,
      y + (dy * box.height) / 5.625,
      { steps: 8 },
    );
    return box;
  }
  const dialog = page.getByRole("dialog", {
    name: "Review dragged objects",
    exact: true,
  });
  async function saveAndUndo(expected, multi = false) {
    await page.mouse.up();
    await dialog.waitFor();
    assert.equal(
      await page
        .locator(".pw-native-layers img[data-object-id]")
        .evaluateAll((images) =>
          images.every((i) => i.style.transform === "translate(0px, 0px)"),
        ),
      true,
    );
    await dialog
      .getByRole("button", { name: "Preview all changes", exact: true })
      .click();
    await nativeReady(dialog);
    const receipt = await app.evaluate(() =>
      globalThis.nativePlanReceipts.at(-1),
    );
    await dialog.getByRole("checkbox").check();
    assert.deepEqual(await head(), baseline);
    await dialog
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .click();
    await dialog.waitFor({ state: "hidden" });
    assert.equal((await head()).sha256, receipt.sha256);
    const objects = (await catalog()).objects,
      a = objects.find((o) => o.name === "Moving A").geometry,
      b = objects.find((o) => o.name === "Moving B").geometry;
    assert.equal(a.x_emu, Math.round(expected * 914400));
    assert.equal(a.width_emu, 914400);
    assert.equal(a.height_emu, 457200);
    if (multi) assert.equal(b.x_emu - a.x_emu, 1.5 * 914400);
    else assert.equal(b.x_emu, 2.5 * 914400);
    assert.equal(await page.locator(".pw-native-layers").count(), 0);
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await page
      .getByText("Current \u00b7 Revision 1", { exact: true })
      .waitFor();
    assert.deepEqual(await head(), baseline);
  }
  async function capturePixels(filename) {
    await overlay.evaluate((element) => {
      element.style.opacity = "0";
    });
    try {
      await page
        .locator(".pw-native-layers")
        .screenshot({ path: path.join(output, filename) });
    } finally {
      await overlay.evaluate((element) => {
        element.style.removeProperty("opacity");
      });
    }
  }
  await prepare();
  await moving.click();
  await overlay.scrollIntoViewIfNeeded();
  await capturePixels("before-pixels.png");
  await begin(1.5);
  await page.screenshot({ path: path.join(output, "live-overlap.png") });
  await capturePixels("during-pixels.png");
  const id = before.objects.find((o) => o.name === "Moving A").object_id;
  assert.notEqual(
    await page
      .locator(`.pw-native-layers [data-object-id="${id}"]`)
      .evaluate((i) => window.getComputedStyle(i).transform),
    "matrix(1, 0, 0, 1, 0, 0)",
  );
  execFileSync(
    path.join(root, "core/.venv/Scripts/python.exe"),
    [
      "-c",
      String.raw`
import sys,json
from PIL import Image
from pathlib import Path
out=Path(sys.argv[1]);a=Image.open(out/'before-pixels.png').convert('RGB');b=Image.open(out/'during-pixels.png').convert('RGB')
assert a.size==b.size
point=lambda x,y:(round(x*a.width/10),round(y*a.height/5.625))
old=point(1.12,1.42);foreground=point(2.62,1.42)
assert min(a.getpixel(old))<240,a.getpixel(old)
assert min(b.getpixel(old))>=250,b.getpixel(old)
assert max(abs(x-y) for x,y in zip(a.getpixel(foreground),b.getpixel(foreground)))<=4
(out/'pixel-proof.json').write_text(json.dumps({'before_old':a.getpixel(old),'during_old':b.getpixel(old),'before_foreground':a.getpixel(foreground),'during_foreground':b.getpixel(foreground)}),encoding='utf-8')
`,
      output,
    ],
    { cwd: root, windowsHide: true, stdio: "pipe" },
  );
  await saveAndUndo(2.5);
  checks.push(
    "Live translucent object pixels leave no original copy and remain behind the foreground object; exact native reviewed Save and one Undo preserve source bytes and dimensions",
  );
  await prepare();
  await begin(1.5);
  await page.keyboard.press("Escape");
  await page.mouse.up();
  assert.equal(await dialog.count(), 0);
  assert.equal(
    await page
      .locator(".pw-native-layers img[data-object-id]")
      .evaluateAll((images) =>
        images.every((i) => i.style.transform === "translate(0px, 0px)"),
      ),
    true,
  );
  assert.deepEqual(await head(), baseline);
  await page
    .getByRole("checkbox", {
      name: "Align dragging and resizing to slide and nearby object edges and centers",
      exact: true,
    })
    .check();
  await page
    .getByRole("checkbox", {
      name: "Snap object dragging and resizing to 0.1 inch increments",
      exact: true,
    })
    .check();
  await begin(2.86, 0, { multi: true });
  assert.ok(await overlay.locator(".pw-alignment-guide").count());
  await page.screenshot({ path: path.join(output, "live-multi-guide.png") });
  await saveAndUndo(3.87, true);
  checks.push(
    "Escape restores the live baseline without a plan; multi-object layer movement shares exact guided review offsets and native Save/Undo preserves spacing",
  );
  await prepare();
  await moving.click();
  await overlay.scrollIntoViewIfNeeded();
  const resizeBox = await overlay.boundingBox();
  const resizeHandle = await overlay
    .getByRole("button", { name: "Resize selection right", exact: true })
    .boundingBox();
  assert.ok(resizeBox && resizeHandle);
  await capturePixels("before-resize-pixels.png");
  const resizeX = resizeHandle.x + resizeHandle.width / 2;
  const resizeY = resizeHandle.y + resizeHandle.height / 2;
  await page.mouse.move(resizeX, resizeY);
  await page.mouse.down();
  await page.mouse.move(resizeX + (0.5 * resizeBox.width) / 10, resizeY, {
    steps: 8,
  });
  await capturePixels("during-resize-pixels.png");
  execFileSync(
    path.join(root, "core/.venv/Scripts/python.exe"),
    [
      "-c",
      String.raw`
from PIL import Image,ImageChops
from pathlib import Path
import sys
out=Path(sys.argv[1])
a=Image.open(out/'before-resize-pixels.png').convert('RGB');b=Image.open(out/'during-resize-pixels.png').convert('RGB')
assert a.size==b.size and ImageChops.difference(a,b).getbbox() is None
`,
      output,
    ],
    { cwd: root, windowsHide: true, stdio: "pipe" },
  );
  await page.mouse.up();
  const resizeDialog = page.getByRole("dialog", {
    name: "Review object layout",
    exact: true,
  });
  await resizeDialog.waitFor();
  await resizeDialog
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await nativeReady(resizeDialog);
  await resizeDialog
    .getByRole("button", { name: "Discard preview", exact: true })
    .click();
  await resizeDialog.waitFor({ state: "hidden" });
  assert.deepEqual(await head(), baseline);
  checks.push(
    "Resizing retains byte-identical saved native pixels while geometric ghosts change; the staged resize renders in PowerPoint and discard preserves source bytes",
  );
  const oldUrls = await page
    .locator(".pw-native-layers img")
    .evaluateAll((images) => images.map((i) => i.src));
  await page
    .getByRole("button", { name: "Browser appearance", exact: true })
    .click();
  assert.equal(await page.locator(".pw-native-layers").count(), 0);
  await page.waitForFunction(
    async (urls) =>
      (
        await Promise.all(
          urls.map(async (url) => {
            try {
              await fetch(url);
              return true;
            } catch {
              return false;
            }
          }),
        )
      ).every((v) => !v),
    oldUrls,
  );
  assert.equal(
    await page
      .locator(".pw-canvas > img")
      .evaluate((i) => window.getComputedStyle(i).opacity),
    "1",
  );
  checks.push(
    "Browser appearance stops live pixels, restores the normal saved image and revokes every prepared blob URL",
  );
  await prepare();
  await page
    .locator(".pw-native-layers img[data-object-id]")
    .first()
    .evaluate((i) => {
      i.src = "blob:owned-invalid-image";
    });
  await controls.getByRole("alert").waitFor();
  assert.equal(await page.locator(".pw-native-layers").count(), 0);
  assert.deepEqual(await head(), baseline);
  await prepare();
  await page.getByRole("button", { name: "Next slide", exact: true }).click();
  await page
    .getByRole("img", { name: "Imported presentation, slide 2", exact: true })
    .waitFor();
  assert.equal(await page.locator(".pw-native-layers").count(), 0);
  await page
    .getByRole("button", { name: "Previous slide", exact: true })
    .click();
  await page
    .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
    .waitFor();
  checks.push(
    "Explicit layer image failure falls back without mutation and retries; slide navigation invalidates prepared pixels",
  );
  await app.evaluate(
    (_electron, filename) => {
      const module = process.mainModule.require(filename),
        original = module.runPdfWorker;
      globalThis.layerHold = true;
      globalThis.layerReady = false;
      module.runPdfWorker = async (...args) => {
        const result = await original(...args);
        if (args[3] === "layers") {
          globalThis.layerReady = true;
          const deadline = Date.now() + 125000;
          while (globalThis.layerHold && Date.now() < deadline)
            await new Promise((resolve) => setTimeout(resolve, 50));
          if (globalThis.layerHold) throw new Error("Owned layer gate expired");
        }
        return result;
      };
    },
    path.join(path.dirname(nativeModulePath), "pdf-export.js"),
  );
  await controls
    .getByRole("button", { name: "Prepare live dragging", exact: true })
    .click();
  const layerDeadline = Date.now() + 125000;
  while (
    !(await app.evaluate(() => globalThis.layerReady)) &&
    Date.now() < layerDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 100));
  assert.equal(await app.evaluate(() => globalThis.layerReady), true);
  await controls
    .getByRole("button", { name: "Cancel preparation", exact: true })
    .click();
  await app.evaluate(() => {
    globalThis.layerHold = false;
  });
  await controls
    .getByRole("button", { name: "Prepare live dragging", exact: true })
    .waitFor({ state: "visible" });
  await page.waitForFunction(() => {
    const b = [...document.querySelectorAll("button")].find(
      (b) => b.textContent === "Prepare live dragging",
    );
    return b && !b.disabled;
  });
  assert.equal(await page.locator(".pw-native-layers").count(), 0);
  assert.deepEqual(await head(), baseline);
  checks.push(
    "Cancel preparation rejects a delayed real native reply without allocating or displaying old source layers",
  );
  await prepare();
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()
      .find((w) => w.webContents.getURL().endsWith("/renderer/index.html"))
      .setSize(720, 520),
  );
  await page.waitForFunction(() => window.innerWidth <= 720);
  await begin(2.86, 0, { multi: true });
  await page.mouse.up();
  await dialog.waitFor();
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
    "Minimum-window live multi-object guide movement remains contained, reviewable and discardable",
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
  if (app) {
    await app
      .evaluate(() => {
        globalThis.layerHold = false;
      })
      .catch(() => {});
    await app.close();
  }
}
