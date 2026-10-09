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
const output = path.join(
  root,
  ".local",
  "native-appearance",
  process.env.PRESENTER_NATIVE_OUTPUT ??
    (packagedExecutable ? "gui-packaged" : "gui"),
);
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
async function appearance(name) {
  await page
    .getByRole("group", { name: "Slide appearance", exact: true })
    .getByRole("button", { name, exact: true })
    .click();
}
async function nativeReady() {
  await page
    .getByText(
      "Saved slide appearance from PowerPoint. Review proposed changes in an edit preview.",
      { exact: true },
    )
    .waitFor({ timeout: 125_000 });
  await page.waitForFunction(() => {
    const image = document.querySelector(".pw-canvas img");
    return image?.complete && image.naturalWidth === 960;
  });
}
async function delayedReplyFinished() {
  const deadline = Date.now() + 125_000;
  while (Date.now() < deadline) {
    if (await app.evaluate(() => globalThis.nativeReplyPending === false))
      return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("Owned delayed native reply did not finish");
}
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
        ({ app }) => `${app.getAppPath()}/dist/main/native-appearance.js`,
      )
    : path.join(desktop, "dist", "main", "native-appearance.js");
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
  await page
    .getByRole("button", { name: "Edit slide together", exact: true })
    .click();
  const review = page.getByRole("dialog");
  await review
    .getByRole("textbox", { name: "Slide text 1", exact: true })
    .fill("Native proposal review fixture");
  await review
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  const proposedImage = review.getByRole("img", {
    name: "Proposed slide with all reviewed text changes",
    exact: true,
  });
  await proposedImage.waitFor();
  await review
    .getByRole("button", { name: "PowerPoint appearance", exact: true })
    .click();
  await review
    .getByText(
      "Proposed slide appearance from PowerPoint. Changes are not saved.",
      { exact: true },
    )
    .waitFor({ timeout: 125_000 });
  await page.waitForFunction(() => {
    const image = document.querySelector("dialog[open] img");
    return image?.complete && image.naturalWidth === 960;
  });
  assert.equal(
    await review
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isEnabled(),
    false,
  );
  await page.screenshot({
    path: path.join(output, "native-proposed-slide.png"),
  });
  await review
    .getByRole("button", { name: "Browser appearance", exact: true })
    .click();
  await review
    .getByRole("button", { name: "Discard preview", exact: true })
    .click();
  await review.waitFor({ state: "hidden" });
  await page
    .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
    .waitFor();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  checks.push(
    "Manual staged edits render through real PowerPoint before commit; browser switching/discard preserve the saved revision",
  );
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
    await copilot
      .getByRole("button", { name: "PowerPoint appearance", exact: true })
      .click();
    await copilot
      .getByText(
        "Proposed slide appearance from PowerPoint. Changes are not saved.",
        { exact: true },
      )
      .waitFor({ timeout: 125_000 });
    await page.waitForFunction(() => {
      const image = document.querySelector("dialog[open] img");
      return image?.complete && image.naturalWidth === 960;
    });
    await copilot.getByRole("checkbox").check();
    assert.equal(
      await copilot
        .getByRole("button", { name: "Save Copilot changes", exact: true })
        .isEnabled(),
      true,
    );
    await page.screenshot({
      path: path.join(output, "native-copilot-proposed-slide.png"),
    });
    await copilot
      .getByRole("button", { name: "Browser appearance", exact: true })
      .click();
    await page.waitForFunction(
      () =>
        document.querySelector('dialog[open] input[type="checkbox"]')
          ?.checked === false,
    );
    assert.equal(await copilot.getByRole("checkbox").isChecked(), false);
    await copilot
      .getByRole("button", { name: "Discard Copilot proposal", exact: true })
      .click();
    await copilot.waitFor({ state: "detached" });
    await page
      .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
      .waitFor();
    checks.push(
      "Deterministic Copilot proposal renders in real PowerPoint; image readiness gates save and Browser switching clears acknowledgment; discard preserves baseline",
    );
  }
  await appearance("PowerPoint appearance");
  await nativeReady();
  checks.push(
    "Real immutable-revision copy, native worker and bounded PNG display for slide 1",
  );
  await page.screenshot({ path: path.join(output, "native-slide-1.png") });
  await appearance("Browser appearance");
  assert.equal(
    await page
      .getByText(
        "Saved slide appearance from PowerPoint. Review proposed changes in an edit preview.",
        { exact: true },
      )
      .count(),
    0,
  );
  checks.push("Explicit browser switch removes native status and image");
  await appearance("PowerPoint appearance");
  await nativeReady();
  await page.getByRole("button", { name: "Next slide", exact: true }).click();
  await page
    .getByRole("img", { name: "Imported presentation, slide 2", exact: true })
    .waitFor();
  assert.equal(
    await page
      .getByText(
        "Saved slide appearance from PowerPoint. Review proposed changes in an edit preview.",
        { exact: true },
      )
      .count(),
    0,
  );
  await appearance("PowerPoint appearance");
  await nativeReady();
  checks.push(
    "Slide navigation invalidates slide 1 appearance; slide 2 renders independently",
  );
  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Objects", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "New text box text", exact: true })
    .fill("Native appearance selection fixture");
  await page.getByRole("button", { name: "Add text box", exact: true }).click();
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  assert.equal(
    await page
      .getByText(
        "Saved slide appearance from PowerPoint. Review proposed changes in an edit preview.",
        { exact: true },
      )
      .count(),
    0,
  );
  await appearance("PowerPoint appearance");
  await nativeReady();
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current \u00b7 Revision 1", { exact: true }).waitFor();
  assert.equal(
    await page
      .getByText(
        "Saved slide appearance from PowerPoint. Review proposed changes in an edit preview.",
        { exact: true },
      )
      .count(),
    0,
  );
  await page
    .getByRole("button", { name: "Redo presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  await appearance("PowerPoint appearance");
  await nativeReady();
  checks.push(
    "GUI text-box edit and undo/redo invalidate native revision images; revised slide renders",
  );
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .check();
  const overlay = page.getByLabel("Select slide objects", { exact: true });
  await overlay.waitFor();
  const pick = overlay.getByRole("button").first();
  await pick.click();
  assert.equal(await pick.getAttribute("aria-pressed"), "true");
  const bounds = await page.evaluate(() => {
    const image = document
      .querySelector(".pw-canvas img")
      .getBoundingClientRect();
    const overlay = document
      .querySelector(".pw-canvas svg")
      .getBoundingClientRect();
    return {
      dx: Math.abs(image.x - overlay.x),
      dy: Math.abs(image.y - overlay.y),
      dw: Math.abs(image.width - overlay.width),
      dh: Math.abs(image.height - overlay.height),
    };
  });
  assert.ok(
    Object.values(bounds).every((n) => n < 1),
    JSON.stringify(bounds),
  );
  checks.push(
    "Native pixels retain object selection and exact overlay/image bounds",
  );
  // Delay only the owned test app's response after the real worker finishes.
  await app.evaluate((_electron, filename) => {
    const module = process.mainModule.require(filename);
    const original = module.renderNativeAppearance;
    module.renderNativeAppearance = async (...args) => {
      globalThis.nativeReplyPending = true;
      try {
        const result = await original(...args);
        await new Promise((resolve) => setTimeout(resolve, 2000));
        return result;
      } finally {
        globalThis.nativeReplyPending = false;
      }
    };
    globalThis.restoreNativeAppearance = () => {
      module.renderNativeAppearance = original;
    };
  }, nativeModulePath);
  await appearance("PowerPoint appearance");
  await appearance("Browser appearance");
  await page
    .getByRole("button", { name: "PowerPoint appearance", exact: true })
    .waitFor({ timeout: 125_000 });
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll("button")].some(
        (button) =>
          button.textContent === "PowerPoint appearance" && !button.disabled,
      ),
    undefined,
    { timeout: 125_000 },
  );
  assert.equal(
    await page
      .getByText(
        "Saved slide appearance from PowerPoint. Review proposed changes in an edit preview.",
        { exact: true },
      )
      .count(),
    0,
  );
  checks.push("Browser switch rejects a delayed real native reply");
  const previousSlide = Number(
    (await page.locator(".pw-canvas img").getAttribute("alt")).match(
      /slide (\d+)$/,
    )[1],
  );
  await appearance("PowerPoint appearance");
  await page.getByRole("button", { name: "Next slide", exact: true }).click();
  await page
    .getByRole("img", {
      name: `Imported presentation, slide ${previousSlide + 1}`,
      exact: true,
    })
    .waitFor();
  await delayedReplyFinished();
  await page.waitForFunction(
    () =>
      !document
        .querySelector(".pw-native-appearance [aria-pressed='true']")
        ?.textContent.includes("PowerPoint"),
  );
  assert.equal(
    await page
      .getByText(
        "Saved slide appearance from PowerPoint. Review proposed changes in an edit preview.",
        { exact: true },
      )
      .count(),
    0,
  );
  checks.push("Navigation rejects a delayed previous-slide reply");
  await app.evaluate(() => globalThis.restoreNativeAppearance());
  await app.evaluate((_electron, filename) => {
    const module = process.mainModule.require(filename);
    const original = module.renderNativeAppearance;
    module.renderNativeAppearance = async () => {
      throw new Error("Owned native appearance failure fixture");
    };
    globalThis.restoreNativeAppearance = () => {
      module.renderNativeAppearance = original;
    };
  }, nativeModulePath);
  await appearance("PowerPoint appearance");
  await page
    .getByRole("group", { name: "Slide appearance", exact: true })
    .getByRole("alert")
    .waitFor();
  await app.evaluate(() => globalThis.restoreNativeAppearance());
  await appearance("PowerPoint appearance");
  await nativeReady();
  checks.push(
    "Explicit native failure keeps browser available; retry renders through real worker",
  );
  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()
      .find((candidate) =>
        candidate.webContents.getURL().endsWith("/renderer/index.html"),
      )
      ?.setSize(720, 520);
  });
  await page
    .getByRole("group", { name: "Slide appearance", exact: true })
    .evaluate((element) => element.scrollIntoView({ block: "start" }));
  await page.screenshot({ path: path.join(output, "native-small-window.png") });
  const overflow = await page.evaluate(
    () =>
      [document.body, document.querySelector(".workspace-main")].filter(
        (element) => element && element.scrollWidth > element.clientWidth + 2,
      ).length,
  );
  assert.equal(overflow, 0);
  const viewport = await page.evaluate(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
    dpr: window.devicePixelRatio,
  }));
  const frameBounds = await page.evaluate(() => {
    const image = document.querySelector(".pw-canvas img");
    const pixels = image.getBoundingClientRect();
    const canvas = image.parentElement.getBoundingClientRect();
    return {
      image: {
        width: pixels.width,
        height: pixels.height,
        x: pixels.x,
        y: pixels.y,
      },
      canvas: {
        width: canvas.width,
        height: canvas.height,
        x: canvas.x,
        y: canvas.y,
      },
      natural: { width: image.naturalWidth, height: image.naturalHeight },
      contained:
        pixels.top >= canvas.top - 1 &&
        pixels.bottom <= canvas.bottom + 1 &&
        pixels.left >= canvas.left - 1 &&
        pixels.right <= canvas.right + 1,
    };
  });
  console.log("Small-window native frame bounds", JSON.stringify(frameBounds));
  assert.ok(
    frameBounds.contained,
    "The full native slide fits the canvas without clipping",
  );
  checks.push(
    `Requested 720x520 window, actual viewport ${JSON.stringify(viewport)}: no horizontal workspace overflow`,
  );
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
