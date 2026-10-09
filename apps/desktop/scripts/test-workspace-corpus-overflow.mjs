/* global window, document, HTMLButtonElement */
import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
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
const sourcePath = path.join(
  root,
  ".local",
  "presentation-workspace-corpus",
  "02-sdgs-budgeting.pptx",
);
const temporary = await mkdtemp(
  path.join(os.tmpdir(), "presenter-overflow-corpus-"),
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

let app;
let page;

async function findReviewTarget() {
  return page.evaluate(async () => {
    const api = window.presenterCopilot.core;
    const projects = await api.request("project.list", {});
    if (!projects.ok) throw new Error("PROJECT_LIST_FAILED");
    const project = projects.result.projects.find(
      (item) => item.name === "3996727 overflow review",
    );
    if (!project) throw new Error("PROJECT_NOT_FOUND");
    const sources = await api.request("source.list", {
      project_id: project.id,
    });
    if (!sources.ok) throw new Error("SOURCE_LIST_FAILED");
    const source = sources.result.sources.find(
      (item) => item.original_name === "02-sdgs-budgeting.pptx",
    );
    if (!source) throw new Error("IMPORTED_SOURCE_NOT_FOUND");
    const opened = await api.request("presentation.workspace.open_source", {
      project_id: project.id,
      document_id: source.id,
    });
    if (!opened.ok) throw new Error("SOURCE_OPEN_FAILED");

    let chosen = null;
    try {
      const slideCount = opened.result.fidelity_report.slide_count;
      for (let slideNumber = 1; slideNumber <= slideCount; slideNumber += 1) {
        const inventory = await api.request(
          "presentation.workspace.list_text_targets",
          {
            project_id: project.id,
            document_id: source.id,
            revision_id: opened.result.revision_id,
            slide_number: slideNumber,
          },
        );
        if (!inventory.ok) throw new Error("TARGET_INVENTORY_FAILED");
        const target = inventory.result.targets.find(
          (item) =>
            item.single_run_editable === true &&
            typeof item.current_text === "string" &&
            item.current_text.length > 0,
        );
        if (!target) continue;
        const object = inventory.result.objects.find(
          (item) => item.object_id === target.object_id,
        );
        if (!object?.geometry) continue;
        chosen = {
          project_id: project.id,
          document_id: source.id,
          source_sha256: source.sha256,
          revision_id: opened.result.revision_id,
          slide_number: slideNumber,
          object_id: target.object_id,
          shape_id: target.ooxml_shape_id,
          text: target.current_text,
          geometry: object.geometry,
        };
        break;
      }
    } finally {
      await api.request("presentation.workspace.close_source", {
        project_id: project.id,
        document_id: source.id,
        session_id: opened.result.session_id,
      });
    }
    if (!chosen) throw new Error("NO_SINGLE_RUN_REVIEW_TARGET");
    return chosen;
  });
}

try {
  await access(sourcePath);
  app = await electron.launch({
    executablePath: require("electron"),
    args: [desktop, `--user-data-dir=${path.join(temporary, "browser")}`],
    cwd: root,
    env,
    timeout: 30_000,
  });
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    page = app
      .windows()
      .find((candidate) => candidate.url().endsWith("/renderer/index.html"));
    if (page) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(page, "Main workspace window loaded");
  page.setDefaultTimeout(20_000);
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page.getByRole("dialog").waitFor();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill("3996727 overflow review");
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
  await page.getByRole("button", { name: /02-sdgs-budgeting\.pptx/ }).waitFor();
  await page.getByRole("button", { name: /02-sdgs-budgeting\.pptx/ }).click();
  await page.getByRole("navigation", { name: "Project navigation" }).waitFor();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page.waitForFunction(() => {
    const navigation = document.querySelector(
      '[aria-label="Presentation slides"]',
    );
    const openButton = [...document.querySelectorAll("button")].find(
      (button) => button.textContent?.trim() === "Open preview",
    );
    return (
      (navigation?.querySelectorAll("button").length > 0 &&
        openButton instanceof HTMLButtonElement &&
        !openButton.disabled) ||
      document.querySelector(".pw-slide-column [role='alert']") !== null
    );
  });
  const previewError = await page
    .locator(".pw-slide-column [role='alert']")
    .allTextContents();
  if (previewError.length > 0) {
    throw new Error(`PRESENTATION_PREVIEW_FAILED: ${previewError[0]}`);
  }

  const target = await findReviewTarget();
  assert.equal(
    target.slide_number,
    7,
    "Corpus overflow target slide remains stable",
  );
  assert.equal(
    target.shape_id,
    "5",
    "Corpus overflow title shape remains stable",
  );
  const targetMapping = await page.evaluate(async (selectedTarget) => {
    const rendered = await window.presenterCopilot.presentationPreview.render(
      selectedTarget.slide_number,
    );
    const inventory = await window.presenterCopilot.core.request(
      "presentation.workspace.list_text_targets",
      {
        project_id: selectedTarget.project_id,
        document_id: selectedTarget.document_id,
        revision_id: selectedTarget.revision_id,
        slide_number: selectedTarget.slide_number,
      },
    );
    if (!rendered.ok || !inventory.ok) {
      return {
        preview_ok: rendered.ok,
        inventory_ok: inventory.ok,
      };
    }
    const candidates = rendered.result.text_candidates;
    const targets = inventory.result.targets;
    return {
      preview_ok: true,
      inventory_ok: true,
      renderer_candidate_count: candidates.length,
      core_target_count: targets.length,
      shape_id_match_count: candidates.filter((candidate) =>
        targets.some((item) => item.ooxml_shape_id === candidate.shape_node_id),
      ).length,
      exact_text_match_count: candidates.filter((candidate) =>
        targets.some(
          (item) =>
            item.ooxml_shape_id === candidate.shape_node_id &&
            item.current_text === candidate.text,
        ),
      ).length,
    };
  }, target);
  assert.equal(targetMapping.exact_text_match_count, 1);
  const firstWord = target.text.match(/[\p{L}\p{N}]+/u)?.[0];
  assert.ok(
    firstWord && firstWord.length >= 4,
    "Target begins with a mutable word",
  );
  const lastLetter = firstWord.at(-1);
  const alphabet =
    lastLetter === lastLetter?.toUpperCase()
      ? "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
      : "abcdefghijklmnopqrstuvwxyz";
  const letterIndex = alphabet.indexOf(lastLetter ?? "");
  assert.ok(
    letterIndex >= 0,
    "The target word ends in an alphabetic character",
  );
  const changedWord =
    firstWord.slice(0, -1) + alphabet[(letterIndex + 1) % alphabet.length];
  const replacement = changedWord + target.text.slice(firstWord.length);
  assert.equal(replacement.length, target.text.length);

  const slideButton = page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(target.slide_number - 1);
  await slideButton.click();
  const targetPicker = page
    .locator(".pw-mock-edit label")
    .filter({ hasText: "Text on this slide" })
    .locator("select");
  await page.waitForFunction(
    (objectId) =>
      [...document.querySelectorAll(".pw-mock-edit select")].some((select) =>
        [...select.options].some((option) => option.value === objectId),
      ),
    target.object_id,
  );
  await targetPicker.selectOption({ value: target.object_id });
  await page.getByLabel("Replacement text", { exact: true }).fill(replacement);
  await page
    .getByRole("button", { name: "Preview replacement", exact: true })
    .click();
  await page
    .getByRole("img", {
      name: `Text edit preview on slide ${target.slide_number}`,
      exact: true,
    })
    .waitFor();
  const warning = page.locator(".pw-layout-warning");
  await warning.waitFor({ timeout: 30_000 });
  const saveButton = page.getByRole("button", {
    name: "Save revision",
    exact: true,
  });
  assert.equal(await saveButton.isDisabled(), true);
  await warning.getByRole("checkbox").check();
  assert.equal(await saveButton.isDisabled(), false);
  const sourceHashAfterPreview = await page.evaluate(async () => {
    const api = window.presenterCopilot.core;
    const projects = await api.request("project.list", {});
    if (!projects.ok) throw new Error("PROJECT_LIST_FAILED");
    const project = projects.result.projects.find(
      (item) => item.name === "3996727 overflow review",
    );
    if (!project) throw new Error("PROJECT_NOT_FOUND");
    const sources = await api.request("source.list", {
      project_id: project.id,
    });
    if (!sources.ok) throw new Error("SOURCE_LIST_FAILED");
    return sources.result.sources.find(
      (item) => item.original_name === "02-sdgs-budgeting.pptx",
    )?.sha256;
  });
  assert.equal(sourceHashAfterPreview, target.source_sha256);
  const result = {
    status: "passed",
    corpus_record: 3996727,
    slide_number: target.slide_number,
    shape_id: target.shape_id,
    replacement_length: replacement.length,
    overflow_warning: true,
    save_requires_acknowledgement: true,
    source_hash_unchanged: true,
    scope:
      "Local Electron preview only; no revision saved; no slide text or render retained.",
  };
  await mkdir(path.join(root, ".local", "ui-validation"), { recursive: true });
  await writeFile(
    path.join(root, ".local", "ui-validation", "corpus-overflow.json"),
    JSON.stringify(result, null, 2),
  );
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  process.stderr.write(
    `${error instanceof Error ? error.message : "CORPUS_OVERFLOW_TEST_FAILED"}\n`,
  );
  if (page) {
    const state = await page
      .evaluate(() => {
        const navigation = document.querySelector(
          '[aria-label="Presentation slides"]',
        );
        const openButton = [...document.querySelectorAll("button")].find(
          (button) => button.textContent?.trim() === "Open preview",
        );
        return {
          workspaceVisible: navigation !== null,
          slideButtonCount: navigation?.querySelectorAll("button").length ?? 0,
          previewErrorVisible:
            document.querySelector(".pw-slide-column [role='alert']") !== null,
          selectedSlide:
            document
              .querySelector(
                '[aria-label="Presentation slides"] button[aria-current="true"]',
              )
              ?.textContent?.trim() ?? null,
          textTargetOptionCount:
            document
              .querySelector(".pw-mock-edit select")
              ?.querySelectorAll("option").length ?? 0,
          slideImageVisible:
            document.querySelector(
              '.pw-canvas img[alt^="Imported presentation"]',
            ) !== null,
          openPreviewEnabled:
            openButton instanceof HTMLButtonElement && !openButton.disabled,
          progressVisible: document.querySelector(".pw-canvas-empty") !== null,
        };
      })
      .catch(() => null);
    if (state) process.stderr.write(`${JSON.stringify(state)}\n`);
  }
  process.exitCode = 1;
} finally {
  if (app) await app.close();
  await rm(temporary, { recursive: true, force: true });
}
