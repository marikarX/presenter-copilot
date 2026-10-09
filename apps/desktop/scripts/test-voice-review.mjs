/* global window */
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
  path.join(root, ".local", "voice-review", "gui");
await mkdir(output, { recursive: true });
const fixture = path.join(temporary, "presentation.pptx");
const route = "claims";
assert.ok(
  !packagedExecutable,
  "This fixture provider acceptance is source-only.",
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
from pptx.util import Inches,Pt
presentation=Presentation();presentation.slide_width=Inches(10);presentation.slide_height=Inches(5.625)
slide=presentation.slides.add_slide(presentation.slide_layouts[6])
slide.notes_slide.notes_text_frame.text='Initial private speaking reminder.'
for name,text,y in [('Basic metric','Revenue rose 20% during the pilot.',0.5),('Readonly metrics','Return on investment reached 24%.\n'+' '.join(f'Unique supporting observation {i}.' for i in range(210)),1.2)]:
 shape=slide.shapes.add_textbox(Inches(.5),Inches(y),Inches(9),Inches(3));shape.name=name;shape.text=text
 for p in shape.text_frame.paragraphs:p.font.size=Pt(8)
other=presentation.slides.add_slide(presentation.slide_layouts[6]);other.shapes.add_textbox(Inches(.5),Inches(.5),Inches(9),Inches(2)).text='Other slide statement.'
for number in range(3,27):
 other=presentation.slides.add_slide(presentation.slide_layouts[6]);other.shapes.add_textbox(Inches(.5),Inches(.5),Inches(9),Inches(2)).text=f'Metric increased by {number}% on slide {number}.'
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
  async function context(slideNumber = 1) {
    return page.evaluate(async (number) => {
      const ask = async (method, params) => {
        const r = await window.presenterCopilot.core.request(method, params);
        if (!r.ok) throw new Error(r.error.message);
        return r.result;
      };
      const project = (await ask("project.list", {})).projects.find(
        (p) => p.name === "Native appearance acceptance",
      );
      const document = (
        await ask("source.list", { project_id: project.id })
      ).sources.find((d) => d.original_name === "presentation.pptx");
      const base = { project_id: project.id, document_id: document.id };
      const opened = await ask("presentation.workspace.open_source", base);
      await ask("presentation.workspace.close_source", {
        ...base,
        session_id: opened.session_id,
      });
      const inventory = await ask("presentation.workspace.list_text_targets", {
        ...base,
        revision_id: opened.revision_id,
        slide_number: number,
      });
      return {
        scope: {
          ...base,
          revision_id: opened.revision_id,
          slide_id: inventory.slide_id,
          slide_number: number,
        },
        inventory,
        sha256: opened.sha256,
      };
    }, slideNumber);
  }
  const baseline = await context();
  const studio = (name) =>
    page
      .getByRole("group", { name: "Slide studio panels", exact: true })
      .getByRole("button", { name, exact: true })
      .click();
  await app.evaluate(
    (_electron, modulePath) => {
      const { CoreProcessClient } = process.mainModule.require(modulePath);
      const original = CoreProcessClient.prototype.request;
      globalThis.voiceReviewFixture = "empty";
      CoreProcessClient.prototype.request = async function (...args) {
        const result = await original.apply(this, args);
        if (
          args[0] === "presentation.workspace.voice_stop" &&
          globalThis.voiceReviewFixture !== "empty"
        ) {
          const bad = globalThis.voiceReviewFixture === "mismatch";
          return {
            ...result,
            transcript: "Do not change the cost. Shorten this title.",
            recognition_review: {
              version: 1,
              chunk_count: 2,
              unavailable_count: 1,
              truncated: false,
              chunks: [
                {
                  text: bad ? "Change the cost." : "Do not change the cost.",
                  adapter_score: null,
                },
                { text: "Shorten this title.", adapter_score: 0.2 },
              ],
            },
          };
        }
        return result;
      };
    },
    path.join(desktop, "dist/main/core-client.js"),
  );
  await studio("Text");
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .selectOption({ index: 0 });
  const rewrite = page.getByRole("textbox", {
    name: "Rewrite instruction",
    exact: true,
  });
  const previous = await rewrite.inputValue();
  await page
    .getByRole("button", { name: "Dictate instruction", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Stop and review", exact: true })
    .click();
  let review = page.getByRole("dialog", {
    name: "Review spoken instruction",
    exact: true,
  });
  await review
    .getByText(
      "No final speech was recognized. Type your intended instruction or dictate again.",
      { exact: true },
    )
    .waitFor();
  assert.equal(
    await review
      .getByRole("button", { name: "Use reviewed instruction", exact: true })
      .isDisabled(),
    true,
  );
  await review
    .getByLabel("Review dictated instruction", { exact: true })
    .fill("Shorten the wording.");
  await review
    .getByLabel("Dictated rewrite clarification", { exact: true })
    .fill("Keep the cost and negation unchanged.");
  await page.screenshot({
    path: path.join(output, "empty-recognition-correction.png"),
  });
  await review
    .getByRole("button", { name: "Use reviewed instruction", exact: true })
    .click();
  assert.equal(
    await rewrite.inputValue(),
    "Shorten the wording.\nTarget clarification: Keep the cost and negation unchanged.".replaceAll(
      "\\n",
      "\n",
    ),
  );
  assert.equal((await context()).sha256, baseline.sha256);
  checks.push(
    "Actual empty capture discloses missing recognition, requires typed/corrected instruction, appends explicit wording clarification and creates no proposal or native save",
  );
  await app.evaluate(() => {
    globalThis.voiceReviewFixture = "scores";
  });
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  const plan = page.getByRole("dialog", {
    name: "Copilot edit plan",
    exact: true,
  });
  await plan
    .getByLabel("Copilot edit scope", { exact: true })
    .selectOption("deck");
  await plan
    .getByRole("button", { name: "Dictate Copilot request", exact: true })
    .click();
  await plan
    .getByRole("button", { name: "Stop and review request", exact: true })
    .click();
  await plan.getByText(/Intended target: the whole presentation/).waitFor();
  await plan
    .getByText(/Recognition confidence unavailable for 1 of 2 phrases/)
    .waitFor();
  await plan
    .locator("summary")
    .filter({ hasText: "Review original recognized phrases" })
    .click();
  await plan.getByText("Adapter score: 0.20", { exact: true }).waitFor();
  await plan.getByText("Do not change the cost.", { exact: true }).waitFor();
  const transcript = plan.getByLabel("Reviewed Copilot transcript", {
    exact: true,
  });
  const clarification = plan.getByLabel("Dictated target clarification", {
    exact: true,
  });
  await clarification.fill("A".repeat(480));
  assert.equal(
    await plan
      .getByRole("button", {
        name: "Use reviewed Copilot request",
        exact: true,
      })
      .isDisabled(),
    true,
  );
  await clarification.fill("The title and cost statement on slide 1 only.");
  await transcript.fill("Do not change the cost. Shorten the title.");
  await page.screenshot({
    path: path.join(output, "scored-original-review.png"),
  });
  await plan
    .getByRole("button", { name: "Use reviewed Copilot request", exact: true })
    .click();
  assert.equal(
    await plan.getByLabel("Copilot edit request", { exact: true }).inputValue(),
    "Do not change the cost. Shorten the title.\nTarget clarification: The title and cost statement on slide 1 only.".replaceAll(
      "\\n",
      "\n",
    ),
  );
  assert.equal((await context()).sha256, baseline.sha256);
  checks.push(
    "Recognition fixture exposes original unavailable/provided scores without accuracy claims; deck target is explicit, clarification counts toward request limit and explicit Use alone invokes no provider/save",
  );
  await plan
    .getByRole("button", { name: "Dictate Copilot request", exact: true })
    .click();
  await plan
    .getByRole("button", { name: "Stop and review request", exact: true })
    .click();
  assert.equal(
    await plan
      .getByLabel("Dictated target clarification", { exact: true })
      .inputValue(),
    "",
  );
  await plan
    .getByRole("button", { name: "Discard voice request", exact: true })
    .click();
  assert.equal(await plan.locator(".pw-voice-recognition-review").count(), 0);
  checks.push(
    "New dictation clears prior clarification and discard removes original recognition metadata while releasing capture ownership",
  );
  await app.evaluate(() => {
    globalThis.voiceReviewFixture = "mismatch";
  });
  await plan
    .getByRole("button", { name: "Dictate Copilot request", exact: true })
    .click();
  await plan
    .getByRole("button", { name: "Stop and review request", exact: true })
    .click();
  await plan
    .getByText("Recognition phrases no longer match the original transcript.", {
      exact: true,
    })
    .waitFor();
  assert.equal(
    await plan
      .getByLabel("Reviewed Copilot transcript", { exact: true })
      .count(),
    0,
  );
  assert.equal((await context()).sha256, baseline.sha256);
  checks.push(
    "Malformed original-recognition quotes fail before a review or usable instruction is published, preserving the native deck",
  );
  await app.evaluate(() => {
    globalThis.voiceReviewFixture = "scores";
  });
  await plan
    .getByRole("button", { name: "Dictate Copilot request", exact: true })
    .click();
  await plan
    .getByRole("button", { name: "Stop and review request", exact: true })
    .click();
  await plan
    .getByLabel("Reviewed Copilot transcript", { exact: true })
    .waitFor();
  const minimumBounds = await app.evaluate(({ BrowserWindow }) => {
    const owned = BrowserWindow.getAllWindows().find((w) =>
      w.webContents.getURL().endsWith("/renderer/index.html"),
    );
    owned.unmaximize();
    owned.setMinimumSize(720, 520);
    // Windows DPI rounding adds one CSS pixel to these requested dimensions.
    owned.setContentSize(719, 519);
    return {
      content: owned.getContentBounds(),
      bounds: owned.getBounds(),
      zoom: owned.webContents.getZoomFactor(),
    };
  });
  console.log(
    JSON.stringify({
      minimumBounds,
      viewport: await page.evaluate(() => ({
        width: window.innerWidth,
        height: window.innerHeight,
        ratio: window.devicePixelRatio,
      })),
    }),
  );
  await page.waitForFunction(
    () => window.innerWidth <= 720 && window.innerHeight <= 520,
  );
  await plan.locator(".pw-voice-recognition-review").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: path.join(output, "minimum-voice-review.png"),
  });
  await plan
    .getByRole("button", { name: "Use reviewed Copilot request", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: path.join(output, "minimum-voice-actions.png"),
  });
  const fits = await plan.evaluate((node) => {
    const rect = node.getBoundingClientRect();
    return (
      rect.width <= window.innerWidth &&
      rect.left >= 0 &&
      rect.right <= window.innerWidth + 1
    );
  });
  assert.equal(fits, true);
  await plan
    .getByRole("button", { name: "Discard voice request", exact: true })
    .click();
  assert.equal(errors.length, 0, JSON.stringify(errors));
  checks.push(
    "Recognition/clarification workflow fits at 720x520 without renderer errors; score fixtures are UI contract evidence, not physical ASR accuracy",
  );
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify({ checks, errors, baseline, previous }, null, 2) + "\n",
  );
  console.log(JSON.stringify({ passed: checks.length, output }));
} catch (error) {
  if (page) {
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
    console.log((await page.locator("body").innerText()).slice(-12000));
  }
  throw error;
} finally {
  if (app) await app.close();
}
