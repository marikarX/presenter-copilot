/* global window */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
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
  path.join(root, ".local", "native-live-desktop", "gui");
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
  async function prepare() {
    return page.evaluate(async (baseline) => {
      const projects = await window.presenterCopilot.core.request(
        "project.list",
        {},
      );
      const project = projects.result.projects.find(
        (p) => p.name === "Native appearance acceptance",
      );
      const sources = await window.presenterCopilot.core.request(
        "source.list",
        { project_id: project.id },
      );
      const source = sources.result.sources.find(
        (s) => s.original_name === "presentation.pptx",
      );
      const reply = await window.presenterCopilot.presentation.nativeLayers(
        project.id,
        source.id,
        baseline.revisionId,
        baseline.sha256,
        1,
      );
      if (!reply.ok) return reply;
      const r = reply.result;
      return {
        ok: true,
        result: {
          ...r,
          background: {
            sha256: r.background.sha256,
            image: [...r.background.image],
          },
          layers: r.layers.map((l) => ({
            ...l,
            image: [...l.image],
            typed: l.image instanceof Uint8Array,
          })),
          typed: r.background.image instanceof Uint8Array,
        },
      };
    }, baseline);
  }
  const first = await prepare();
  assert.equal(first.ok, true, JSON.stringify(first));
  const frame = first.result;
  assert.equal(frame.typed, true);
  assert.equal(frame.width, 960);
  assert.ok(frame.baseline_max_channel_error <= 4);
  assert.equal(frame.revision_id, baseline.revisionId);
  assert.equal(frame.source_sha256, baseline.sha256);
  assert.deepEqual(
    frame.layers.map((l) => l.object_id),
    before.objects.map((o) => o.object_id),
  );
  assert.equal(
    createHash("sha256")
      .update(Buffer.from(frame.background.image))
      .digest("hex"),
    frame.background.sha256,
  );
  for (const layer of frame.layers) {
    assert.equal(layer.typed, true);
    assert.equal(
      createHash("sha256").update(Buffer.from(layer.image)).digest("hex"),
      layer.sha256,
    );
    assert.equal("file" in layer, false);
  }
  assert.deepEqual(await head(), baseline);
  checks.push(
    "Real preload/main/Core/PowerPoint layers return verified PNG bytes and exact saved-revision/object order, exposing no filesystem paths and changing no source bytes",
  );
  const workerModule = packagedExecutable
    ? await app.evaluate(
        ({ app }) => `${app.getAppPath()}/dist/main/pdf-export.js`,
      )
    : path.join(desktop, "dist/main/pdf-export.js");
  await app.evaluate((_electron, filename) => {
    const module = process.mainModule.require(filename),
      original = module.runPdfWorker;
    globalThis.layerHold = true;
    globalThis.layerReady = false;
    module.runPdfWorker = async (...args) => {
      const result = await original(...args);
      if (args[3] === "layers") {
        globalThis.layerDirectory = process.mainModule
          .require("node:path")
          .dirname(args[1].output_path);
        globalThis.layerReady = true;
        const deadline = Date.now() + 125000;
        while (globalThis.layerHold && Date.now() < deadline)
          await new Promise((resolve) => setTimeout(resolve, 50));
        if (globalThis.layerHold)
          throw new Error("Owned layer reply gate expired");
      }
      return result;
    };
  }, workerModule);
  const pending = prepare();
  const layerDeadline = Date.now() + 125000;
  while (
    !(await app.evaluate(() => globalThis.layerReady)) &&
    Date.now() < layerDeadline
  )
    await new Promise((resolve) => setTimeout(resolve, 100));
  assert.equal(await app.evaluate(() => globalThis.layerReady), true);
  const busy = await page.evaluate(async (baseline) => {
    const projects = await window.presenterCopilot.core.request(
        "project.list",
        {},
      ),
      project = projects.result.projects.find(
        (p) => p.name === "Native appearance acceptance",
      );
    const sources = await window.presenterCopilot.core.request("source.list", {
        project_id: project.id,
      }),
      source = sources.result.sources.find(
        (s) => s.original_name === "presentation.pptx",
      );
    return window.presenterCopilot.presentation.nativeAppearance(
      project.id,
      source.id,
      baseline.revisionId,
      baseline.sha256,
      1,
    );
  }, baseline);
  assert.equal(busy.ok, false);
  assert.match(busy.error.message, /another slide/);
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .check();
  const overlay = page.getByLabel("Select slide objects", { exact: true });
  const moving = overlay.getByRole("button", {
    name: "Select Moving A on slide",
    exact: true,
  });
  await moving.click();
  await overlay.scrollIntoViewIfNeeded();
  const box = await overlay.boundingBox(),
    pick = await moving.boundingBox();
  assert.ok(box && pick);
  await page.mouse.move(pick.x + pick.width / 2, pick.y + pick.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    pick.x + pick.width / 2 + box.width / 10,
    pick.y + pick.height / 2,
    { steps: 6 },
  );
  await page.mouse.up();
  const dialog = page.getByRole("dialog", {
    name: "Review dragged objects",
    exact: true,
  });
  await dialog.waitFor();
  await dialog
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await dialog
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor();
  await dialog.getByRole("checkbox").check();
  await dialog
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await dialog.waitFor({ state: "hidden" });
  assert.equal((await head()).revisionNumber, 2);
  await app.evaluate(() => {
    globalThis.layerHold = false;
  });
  const stale = await pending;
  assert.equal(stale.ok, false);
  assert.equal(
    await app.evaluate(() =>
      process.mainModule
        .require("node:fs")
        .existsSync(globalThis.layerDirectory),
    ),
    false,
  );

  checks.push(
    "A held real layer worker shares the native rendering lease; explicit GUI Save changing the head makes final layer preparation reject the stale revision",
  );
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  assert.deepEqual(await head(), baseline);
  const retry = await prepare();
  assert.equal(retry.ok, true);
  assert.deepEqual(await head(), baseline);
  checks.push(
    "One Undo restores baseline bytes after the concurrent Save; native layer preparation retries successfully after lease release and stale-result cleanup",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      {
        checks,
        errors,
        before,
        frame: {
          width: frame.width,
          height: frame.height,
          baseline_max_channel_error: frame.baseline_max_channel_error,
          layer_count: frame.layers.length,
        },
      },
      null,
      2,
    ),
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
