/* global window */
import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { _electron as electron } from "playwright";

const require = createRequire(import.meta.url);
const desktop = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const root = path.resolve(desktop, "../..");
const defaultSourcePath = path.join(
  root,
  ".local",
  "presentation-workspace-corpus",
  "11-mobile-network-research.pptx",
);
const sourcePath = process.argv[2]
  ? path.resolve(process.argv[2])
  : defaultSourcePath;
const temporary = await mkdtemp(
  path.join(os.tmpdir(), "presenter-preview-profile-"),
);
const outputDirectory = path.join(root, ".local", "ui-validation");
const outputPath = path.join(
  outputDirectory,
  `preview-profile-${new Date().toISOString().replaceAll(":", "-")}.json`,
);
const env = { ...process.env };
for (const key of Object.keys(env)) {
  if (
    key.startsWith("PRESENTER_") ||
    key.startsWith("OPENAI_") ||
    key === "OPENROUTER_API_KEY" ||
    key === "ELECTRON_RUN_AS_NODE"
  ) {
    delete env[key];
  }
}
env.PRESENTER_COPILOT_DATA_ROOT = path.join(temporary, "core");
env.PRESENTER_CORE_DIR = path.join(root, "core");
env.PRESENTER_COPILOT_DEV_MODE = "1";
env.PRESENTER_COPILOT_TEST_PROVIDER = "deterministic_fake";
env.PRESENTER_COPILOT_TEST_ASR = "deterministic_fake";

const runId = randomUUID().slice(0, 8);
const samples = [];
const sampleErrors = [];
let currentStage = "startup";
let sampling = true;
let app;
let page;
let sampleTask;

async function readProcessMetrics() {
  return app.evaluate(({ app: electronApp, BrowserWindow }) => {
    const previewPids = new Set(
      BrowserWindow.getAllWindows()
        .filter((window) =>
          window.webContents
            .getURL()
            .endsWith("/presentation-preview/index.html"),
        )
        .map((window) => window.webContents.getOSProcessId()),
    );
    return electronApp.getAppMetrics().map((metric) => ({
      type: metric.type,
      name: metric.name ?? null,
      pid: metric.pid,
      is_preview_renderer: previewPids.has(metric.pid),
      private_kb: metric.memory.privateBytes ?? null,
      working_set_kb: metric.memory.workingSetSize,
    }));
  });
}

async function sampleMetrics(stage = currentStage) {
  try {
    const processes = await readProcessMetrics();
    samples.push({
      elapsed_ms: Math.round(performance.now()),
      stage,
      total_private_kb: processes.reduce(
        (sum, item) => sum + (item.private_kb ?? 0),
        0,
      ),
      total_working_set_kb: processes.reduce(
        (sum, item) => sum + item.working_set_kb,
        0,
      ),
      preview_private_kb: processes
        .filter((item) => item.is_preview_renderer)
        .reduce((sum, item) => sum + (item.private_kb ?? 0), 0),
      preview_working_set_kb: processes
        .filter((item) => item.is_preview_renderer)
        .reduce((sum, item) => sum + item.working_set_kb, 0),
      processes,
    });
  } catch (error) {
    sampleErrors.push(
      error instanceof Error ? error.name : "ProcessMetricsUnavailable",
    );
  }
}

async function sampleLoop() {
  while (sampling) {
    await sampleMetrics();
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
}

function peakByStage(metricName) {
  const peaks = new Map();
  for (const sample of samples) {
    if (typeof sample[metricName] !== "number") continue;
    const previous = peaks.get(sample.stage);
    if (!previous || sample[metricName] > previous[metricName]) {
      peaks.set(sample.stage, sample);
    }
  }
  return Object.fromEntries(
    [...peaks].map(([stage, sample]) => [stage, sample[metricName]]),
  );
}

async function waitForMainWindow() {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    page = app
      .windows()
      .find((candidate) => candidate.url().endsWith("/renderer/index.html"));
    if (page) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("MAIN_WINDOW_TIMEOUT");
}

try {
  const sourceInfo = await stat(sourcePath);
  assert.ok(sourceInfo.isFile(), "Source must be a regular file");
  assert.ok(sourceInfo.size > 0, "Source file must not be empty");
  assert.ok(
    sourceInfo.size <= 50 * 1024 * 1024,
    "Source exceeds the preview's 50 MiB limit",
  );

  app = await electron.launch({
    executablePath: require("electron"),
    args: [desktop, `--user-data-dir=${path.join(temporary, "browser")}`],
    cwd: root,
    env,
    timeout: 30_000,
  });
  await waitForMainWindow();
  page.setDefaultTimeout(30_000);
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page.getByRole("dialog").waitFor();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill(`Preview profile ${runId}`);
  await page.keyboard.press("Enter");
  await page
    .getByRole("heading", { name: "Sources", exact: true })
    .first()
    .waitFor();

  await app.evaluate(({ dialog }, selectedPath) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [selectedPath],
    });
  }, sourcePath);
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("presentation");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  const sourceButton = page.getByRole("button", {
    name: new RegExp(
      path.basename(sourcePath).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
    ),
  });
  await sourceButton.waitFor();
  await sourceButton.click();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();

  await page.evaluate(() =>
    performance.mark("workspace-preview-profile-start"),
  );
  await sampleMetrics("before-open");
  sampleTask = sampleLoop();
  currentStage = "open-preview";
  const openStarted = performance.now();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  const slideNavigation = page.getByRole("navigation", {
    name: "Presentation slides",
    exact: true,
  });
  await slideNavigation.getByRole("button").first().waitFor();
  await page
    .getByRole("img", {
      name: "Imported presentation, slide 1",
      exact: true,
    })
    .waitFor();
  const openPreviewMs = Math.round(performance.now() - openStarted);
  const slideCount = await slideNavigation.getByRole("button").count();
  assert.ok(slideCount > 0, "Preview exposes slide navigation");

  const renderTimings = [];
  const sampledSlides = [
    ...new Set([1, Math.ceil(slideCount / 2), slideCount]),
  ];
  for (const slideNumber of sampledSlides) {
    const slideButton = slideNavigation
      .getByRole("button")
      .nth(slideNumber - 1);
    const isSelected = await slideButton.getAttribute("aria-current");
    if (isSelected === "true") continue;
    currentStage = "slide-navigation";
    const renderStarted = performance.now();
    await slideButton.click();
    await page
      .getByRole("img", {
        name: `Imported presentation, slide ${slideNumber}`,
        exact: true,
      })
      .waitFor();
    renderTimings.push({
      slide_number: slideNumber,
      elapsed_ms: Math.round(performance.now() - renderStarted),
    });
  }

  currentStage = "preview-close";
  const closeStarted = performance.now();
  const closeResult = await page.evaluate(() =>
    window.presenterCopilot.presentationPreview.close(),
  );
  assert.equal(closeResult.ok, true, "Preview close request succeeds");
  const closeMs = Math.round(performance.now() - closeStarted);
  await new Promise((resolve) => setTimeout(resolve, 2000));
  sampling = false;
  await sampleTask;
  await sampleMetrics("after-close");

  const result = {
    status:
      sampleErrors.length === 0 ? "profiled" : "profiled_with_metric_errors",
    timestamp_utc: new Date().toISOString(),
    platform: process.platform,
    source_label: process.argv[2]
      ? "user-specified"
      : "largest pinned corpus deck",
    source_bytes: sourceInfo.size,
    slide_count: slideCount,
    sampled_slides: sampledSlides,
    open_preview_ms: openPreviewMs,
    navigation_render_ms: renderTimings,
    close_preview_ms: closeMs,
    samples_every_ms: 250,
    sample_count: samples.length,
    sample_errors: [...new Set(sampleErrors)],
    peak_private_kb_by_stage: peakByStage("total_private_kb"),
    peak_working_set_kb_by_stage: peakByStage("total_working_set_kb"),
    peak_preview_private_kb_by_stage: peakByStage("preview_private_kb"),
    peak_preview_working_set_kb_by_stage: peakByStage("preview_working_set_kb"),
    samples,
    scope:
      "Local Electron process metrics and timings only; no slide text, rendered images, or source copy retained by this profile.",
  };
  await mkdir(outputDirectory, { recursive: true });
  await writeFile(outputPath, JSON.stringify(result, null, 2));
  process.stdout.write(
    `${JSON.stringify({ ...result, samples: undefined })}\n`,
  );
  process.stdout.write(`Report: ${outputPath}\n`);
} catch (error) {
  process.stderr.write(
    `${error instanceof Error ? error.message : "PREVIEW_PROFILE_FAILED"}\n`,
  );
  process.exitCode = 1;
} finally {
  sampling = false;
  if (app) await app.close();
  if (sampleTask) await sampleTask;
  const expectedTempParent = path.resolve(os.tmpdir());
  const resolvedTemporary = path.resolve(temporary);
  if (
    path.dirname(resolvedTemporary) !== expectedTempParent ||
    !path.basename(resolvedTemporary).startsWith("presenter-preview-profile-")
  ) {
    process.stderr.write(
      "Refusing to remove an unexpected profile temp directory.\n",
    );
    process.exitCode = 1;
  } else {
    await rm(resolvedTemporary, { recursive: true, force: true });
  }
}
