/* global document, window */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-workspace-"));
const output = path.join(root, ".local", "ui-validation");
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
env.PRESENTER_COPILOT_DATA_ROOT = path.join(temporary, "core");
env.PRESENTER_CORE_DIR = path.join(root, "core");
env.PRESENTER_COPILOT_DEV_MODE = "1";
env.PRESENTER_COPILOT_TEST_PROVIDER = "deterministic_fake";
env.PRESENTER_COPILOT_TEST_DECISION = "deterministic_fake";
env.PRESENTER_COPILOT_TEST_ASR = "deterministic_fake";
const nativeFootnoteReview =
  process.env.PRESENTER_NATIVE_FOOTNOTE_REVIEW === "1";
const errors = [];
const checks = [];
const rendererAssetRequests = new Set();
let app;
let page;
async function launch() {
  app = await electron.launch({
    executablePath: require("electron"),
    args: [desktop, `--user-data-dir=${path.join(temporary, "browser")}`],
    cwd: root,
    env,
    timeout: 30_000,
  });
  // The hidden HUD can register with Playwright before the main renderer.
  page = undefined;
  const deadline = Date.now() + 30_000;
  while (!page && Date.now() < deadline) {
    page = app
      .windows()
      .find((candidate) => candidate.url().endsWith("/renderer/index.html"));
    if (!page) await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(page, "Main workspace window loaded");
  page.setDefaultTimeout(15_000);
  console.log("Main workspace loaded");
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => rendererAssetRequests.add(request.url()));
  await page
    .getByLabel("Core status: READY", { exact: true })
    .waitFor({ timeout: 30_000 });
}
async function shot(name) {
  await page.screenshot({ path: path.join(output, `${name}.png`) });
}
async function navigate(name) {
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name, exact: true })
    .click();
}
async function studioPanel(name) {
  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name, exact: true })
    .click();
}
async function noOverflow(label) {
  const issues = await page.evaluate(() =>
    [...document.querySelectorAll("#workspace-content, .workspace-main, body")]
      .filter((element) => element.scrollWidth > element.clientWidth + 2)
      .map((element) => element.className || element.tagName),
  );
  assert.deepEqual(issues, [], `${label}: no horizontal overflow`);
}
async function rendererAssetLoaded(fragment) {
  return [...rendererAssetRequests].some((url) => url.includes(fragment));
}
async function holdVoice(target) {
  // Playwright normally emulates focus even when the native window loses it.
  const focusSession = await page.context().newCDPSession(page);
  await focusSession.send("Emulation.setFocusEmulationEnabled", {
    enabled: false,
  });
  await focusSession.detach();
  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()
      .find((candidate) =>
        candidate.webContents.getURL().endsWith("/renderer/index.html"),
      )
      ?.focus();
  });
  await target.focus();
  await page.waitForFunction(() => document.hasFocus());
  await page.keyboard.down("Control");
  await page.keyboard.down("Shift");
  await page.keyboard.down("Space");
}
async function releaseVoice() {
  await page.keyboard.up("Space");
  await page.keyboard.up("Shift");
  await page.keyboard.up("Control");
}
try {
  await launch();
  await page.getByRole("dialog").waitFor();
  await shot("01-walkthrough");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  assert.match(await page.getByRole("dialog").innerText(), /Start with what/);
  await page.keyboard.press("Escape");
  assert.equal(await page.getByRole("dialog").count(), 0);
  checks.push("Fresh profile opens walkthrough; next and Escape work");
  await shot("02-home");
  await noOverflow("Home");
  await page.reload();
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  assert.equal(await page.getByRole("dialog").count(), 0);
  await page
    .getByRole("button", { name: "Restart walkthrough", exact: true })
    .click();
  for (let index = 0; index < 4; index++)
    await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Open setup", exact: true }).click();
  await page.getByRole("heading", { name: "Ready when you are." }).waitFor();
  await shot("03-setup");
  checks.push(
    "Dismissal survives reload; restart begins at step one; completion opens setup",
  );
  await page.getByRole("button", { name: "New project", exact: true }).click();
  assert.equal(
    await page
      .getByRole("button", { name: "Create project", exact: true })
      .isDisabled(),
    true,
  );
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill("Quarterly strategy review");
  await page.keyboard.press("Enter");
  await page
    .getByRole("heading", { name: "Sources", exact: true })
    .first()
    .waitFor();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .waitFor();
  await shot("04-sources");
  await navigate("Overview");
  await shot("05-overview");
  await navigate("Sources");
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("transcript");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  await page.getByRole("dialog").waitFor();
  assert.match(
    await page.getByRole("dialog").innerText(),
    /authorized to use this transcript/,
  );
  await page.keyboard.press("Escape");
  checks.push(
    "Project creation uses real core; transcript authorization still precedes picker",
  );
  let fixture = path.join(temporary, "strategy-notes.md");
  // Keep the fixture source-backed but lexical-fallback-ready: Challenge's
  // audience query includes these decision terms when no embedding model is
  // available in offline CI.
  await writeFile(
    fixture,
    "# Strategy review\n\nThe proposed service targets a recovery time of 15 minutes. " +
      "The decision rationale weighs cost, operational risk, and the tradeoff " +
      "between faster recovery and migration complexity; this evidence supports " +
      "the target.\n",
  );
  // Substitute only the native picker result. Main-process import and parsing remain real.
  await app.evaluate(({ dialog }, fixturePath) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [fixturePath],
    });
  }, fixture);
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("supporting");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  await page.getByRole("button", { name: /strategy-notes.md/ }).waitFor();
  await page.getByRole("button", { name: /strategy-notes.md/ }).click();
  await page
    .getByText("The proposed service targets a recovery time of 15 minutes.")
    .waitFor();
  await shot("07-imported-source");
  checks.push(
    "Native-picker test substitution imports and previews a real synthetic Markdown source",
  );
  fixture = path.join(
    root,
    "samples",
    "synthetic-deck",
    "deck",
    "presentation.pptx",
  );
  await app.evaluate(({ dialog }, fixturePath) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [fixturePath],
    });
  }, fixture);
  await page
    .getByLabel("Import source kind", { exact: true })
    .selectOption("presentation");
  await page
    .getByRole("button", { name: "Import source…", exact: true })
    .click();
  await page.getByRole("button", { name: /presentation\.pptx/ }).waitFor();
  const deckHashBeforePreview = await page.evaluate(async () => {
    const projects = await window.presenterCopilot.core.request(
      "project.list",
      {},
    );
    if (!projects.ok) throw new Error("Could not list test projects.");
    const project = projects.result.projects.find(
      (item) => item.name === "Quarterly strategy review",
    );
    if (!project) throw new Error("Could not find test project.");
    const sources = await window.presenterCopilot.core.request("source.list", {
      project_id: project.id,
    });
    if (!sources.ok) throw new Error("Could not list test sources.");
    return sources.result.sources.find(
      (item) => item.original_name === "presentation.pptx",
    )?.sha256;
  });
  assert.ok(deckHashBeforePreview, "Imported PPTX hash is available");
  for (const panelChunk of [
    "AudiencePanel-",
    "ChallengePanel-",
    "LiveAssistPanel-",
    "PresentationWorkspace-",
    "RunPanel-",
    "TeachPanel-",
  ])
    assert.equal(
      await rendererAssetLoaded(panelChunk),
      false,
      `${panelChunk} stays unloaded until its first visit`,
    );
  await navigate("Workspace");
  await page
    .getByRole("button", { name: "Open preview", exact: true })
    .waitFor();
  assert.equal(
    await rendererAssetLoaded("PresentationWorkspace-"),
    true,
    "Presentation Workspace is fetched when its route opens",
  );
  const saveCurrentCopyButton = page.getByRole("button", {
    name: "Save a copy of the current presentation revision",
    exact: true,
  });
  const saveAndOpenCopyButton = page.getByRole("button", {
    name: "Save and open the current presentation in the default presentation app",
    exact: true,
  });
  const saveOriginalCopyButton = page.getByRole("button", {
    name: "Save unchanged copy of the imported presentation",
    exact: true,
  });
  assert.equal(await saveCurrentCopyButton.isDisabled(), true);
  assert.equal(await saveAndOpenCopyButton.isDisabled(), true);
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page
    .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
    .waitFor();
  assert.equal(await saveAndOpenCopyButton.isDisabled(), false);
  assert.equal(
    await page
      .locator(".pw-slide-column .pw-notice")
      .filter({ hasText: "higher-fidelity preview was unavailable" })
      .count(),
    0,
    "The isolated higher-fidelity preview opened instead of the compatibility fallback",
  );
  await page
    .locator(".pw-slide-column .pw-notice")
    .filter({ hasText: "Presenter Copilot Missing Font Smoke" })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .filter({ hasText: "Arial" })
    .waitFor();
  const previewImage = page.getByRole("img", {
    name: "Imported presentation, slide 1",
    exact: true,
  });
  await page.waitForFunction(() => {
    const image = [...document.images].find(
      (item) => item.alt === "Imported presentation, slide 1",
    );
    return image?.complete ?? false;
  });
  const previewImageState = await previewImage.evaluate((image) => ({
    complete: image.complete,
    naturalWidth: image.naturalWidth,
    naturalHeight: image.naturalHeight,
    blobUrl: image.currentSrc.startsWith("blob:"),
  }));
  console.log("Preview image diagnostic", JSON.stringify(previewImageState));
  assert.ok(
    previewImageState.naturalWidth > 0,
    "Slide SVG loads in the image renderer",
  );
  await studioPanel("History");
  await page.locator(".pw-slide-actions > summary").click();
  const fidelitySummary = page.getByRole("region", {
    name: "Presentation structure inventory",
    exact: true,
  });
  await studioPanel("History");
  await fidelitySummary.getByText(/text shape candidates/).waitFor();
  await studioPanel("History");
  await fidelitySummary.getByText(/Object types: .*shapes/).waitFor();
  await studioPanel("History");
  await fidelitySummary
    .getByText(/slide reordering are writable in this preview/)
    .waitFor();
  const revisionHistory = page.locator(".presentation-workspace");
  await revisionHistory
    .getByText("Current · Revision 1", { exact: true })
    .waitFor();
  await studioPanel("Narrative");
  const narrativePanel = page.getByRole("region", {
    name: "Presentation narrative",
    exact: true,
  });
  await narrativePanel
    .getByText("No narrative saved for this revision.", { exact: true })
    .waitFor();
  await narrativePanel
    .getByLabel("Presentation objective", { exact: true })
    .fill("Approve a limited regional migration pilot.");
  await narrativePanel
    .getByLabel("Target audience", { exact: true })
    .fill("Architecture steering committee");
  await narrativePanel
    .getByLabel("Desired decision or action", { exact: true })
    .fill("Fund and assign an owner to a six-week pilot.");
  await narrativePanel
    .getByLabel("Central thesis", { exact: true })
    .fill("Validate recovery risk with a reversible pilot.");
  await narrativePanel
    .getByLabel("Narrative arc", { exact: true })
    .fill(
      "Operational risk → recovery target → pilot evidence → decision and owner.",
    );
  await narrativePanel
    .getByLabel("Presentation constraints", { exact: true })
    .fill("Ten minutes; do not claim the target is already achieved.");
  await studioPanel("Text");
  await studioPanel("Narrative");
  assert.equal(
    await narrativePanel
      .getByLabel("Presentation objective", { exact: true })
      .inputValue(),
    "Approve a limited regional migration pilot.",
  );
  assert.equal(
    await narrativePanel
      .getByRole("button", { name: "Save reviewed narrative", exact: true })
      .isDisabled(),
    true,
  );
  await narrativePanel
    .getByRole("checkbox", {
      name: "I reviewed this narrative for the current deck revision",
      exact: true,
    })
    .check();
  await narrativePanel
    .getByRole("button", { name: "Save reviewed narrative", exact: true })
    .click();
  await narrativePanel
    .getByText("Narrative reviewed for this revision.", { exact: true })
    .waitFor();
  await revisionHistory
    .getByText("Current · Revision 1", { exact: true })
    .waitFor();
  assert.equal(
    await narrativePanel.evaluate(
      (panel) => panel.scrollWidth <= panel.clientWidth + 2,
    ),
    true,
  );
  await shot("workspace-reviewed-narrative-controls");
  await narrativePanel
    .getByRole("heading", { name: "Presentation narrative", exact: true })
    .scrollIntoViewIfNeeded();
  await shot("workspace-reviewed-narrative");
  checks.push(
    "Narrative edits retain drafts across panels, require review and save deck intent without a slide revision",
  );
  const narrativeThesis = narrativePanel.getByLabel("Central thesis", {
    exact: true,
  });
  const thesisBeforeAnalysis = await narrativeThesis.inputValue();
  await narrativePanel
    .getByLabel("Analysis slide count", { exact: true })
    .fill("1");
  await narrativePanel
    .getByRole("button", { name: "Suggest narrative from deck", exact: true })
    .click();
  const narrativeSuggestion = narrativePanel.getByRole("region", {
    name: "Narrative suggestion review",
    exact: true,
  });
  await narrativeSuggestion
    .getByText("Partial deck coverage: 21 slides omitted.", { exact: true })
    .waitFor();
  assert.equal(await narrativeThesis.inputValue(), thesisBeforeAnalysis);
  await narrativeSuggestion
    .getByRole("button", { name: "Discard narrative suggestion", exact: true })
    .click();
  assert.equal(await narrativeSuggestion.count(), 0);
  assert.equal(await narrativeThesis.inputValue(), thesisBeforeAnalysis);
  await narrativePanel
    .getByRole("button", { name: "Suggest narrative from deck", exact: true })
    .click();
  await narrativeSuggestion
    .getByText("Partial deck coverage: 21 slides omitted.", { exact: true })
    .waitFor();
  await narrativeSuggestion
    .getByRole("button", {
      name: "Review narrative finding on slide 1",
      exact: true,
    })
    .click();
  await page
    .getByRole("group", { name: "Slide studio panels", exact: true })
    .getByRole("button", { name: "Purpose", exact: true })
    .waitFor();
  const takeawayReview = page.getByRole("region", {
    name: "Slide takeaway review",
    exact: true,
  });
  await takeawayReview
    .getByText("No reviewed takeaway yet.", { exact: true })
    .waitFor();
  const takeawayDraft = takeawayReview.getByRole("textbox", {
    name: "Slide takeaway",
    exact: true,
  });
  assert.equal(await takeawayDraft.inputValue(), "");
  await takeawayReview
    .getByRole("button", { name: "Use finding as takeaway draft", exact: true })
    .click();
  assert.equal(
    await takeawayDraft.inputValue(),
    "Make the requested decision explicit.",
  );
  assert.equal(
    await takeawayReview
      .getByRole("button", { name: "Save reviewed takeaway", exact: true })
      .isDisabled(),
    true,
  );
  await takeawayDraft.fill("Approve the reversible pilot with a named owner.");
  await takeawayReview
    .getByRole("checkbox", {
      name: "I reviewed this takeaway for the current slide.",
      exact: true,
    })
    .check();
  await takeawayReview
    .getByRole("button", { name: "Save reviewed takeaway", exact: true })
    .click();
  await takeawayReview
    .getByText("Takeaway reviewed for this revision.", { exact: true })
    .waitFor();
  await takeawayReview
    .getByRole("button", { name: "Reload saved takeaway", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelector('[aria-label="Slide takeaway"]')?.value ===
      "Approve the reversible pilot with a named owner.",
  );
  await takeawayReview.scrollIntoViewIfNeeded();
  await shot("workspace-reviewed-slide-takeaway");
  checks.push(
    "Narrative finding takeaway requires explicit use, correction and acknowledgment-gated revision-local save; reload preserves reviewed text without a native revision",
  );
  await studioPanel("Narrative");
  await narrativeSuggestion
    .getByRole("button", { name: "Use suggested narrative", exact: true })
    .click();
  assert.equal(
    await narrativeThesis.inputValue(),
    "Validate the decision through a reviewed, reversible pilot.",
  );
  assert.equal(
    await narrativePanel
      .getByRole("button", { name: "Save reviewed narrative", exact: true })
      .isDisabled(),
    true,
  );
  await narrativePanel
    .getByRole("checkbox", {
      name: "I reviewed this narrative for the current deck revision",
      exact: true,
    })
    .check();
  await narrativePanel
    .getByRole("button", { name: "Save reviewed narrative", exact: true })
    .click();
  await narrativePanel
    .getByText("Narrative reviewed for this revision.", { exact: true })
    .waitFor();
  await page.waitForFunction(
    () =>
      document.querySelector('[aria-label="Narrative suggestion review"]') ===
      null,
  );
  await revisionHistory
    .getByText("Current · Revision 1", { exact: true })
    .waitFor();
  await narrativePanel
    .getByRole("button", { name: "Suggest narrative from deck", exact: true })
    .click();
  await narrativeSuggestion
    .getByText("Partial deck coverage: 21 slides omitted.", { exact: true })
    .waitFor();
  await narrativeSuggestion.scrollIntoViewIfNeeded();
  assert.equal(
    await narrativePanel.evaluate(
      (panel) => panel.scrollWidth <= panel.clientWidth + 2,
    ),
    true,
  );
  await shot("workspace-narrative-suggestion-review");
  await narrativeSuggestion
    .getByRole("button", {
      name: "Review narrative finding on slide 1",
      exact: true,
    })
    .scrollIntoViewIfNeeded();
  await shot("workspace-narrative-suggestion-controls");
  await narrativeSuggestion
    .getByRole("button", { name: "Discard narrative suggestion", exact: true })
    .click();
  checks.push(
    "Narrative analysis discloses partial text/notes scope, leaves drafts unchanged until explicit use, supports discard/finding navigation and requires reviewed save without a deck revision",
  );
  await studioPanel("Purpose");
  const slidePurposePanel = page.locator(".pw-purpose-panel");
  await studioPanel("Purpose");
  const slidePurposeChoice = page.getByRole("combobox", {
    name: "Slide purpose to save",
    exact: true,
  });
  await studioPanel("Purpose");
  await slidePurposeChoice.selectOption("opening");
  await studioPanel("Purpose");
  await page
    .getByRole("button", {
      name: "Save purpose for this revision",
      exact: true,
    })
    .click();
  await studioPanel("Purpose");
  await slidePurposePanel
    .getByText("Saved purpose: opening", { exact: true })
    .waitFor();
  checks.push(
    "Workspace stores a user-confirmed slide purpose on its exact revision",
  );
  const claimReview = page.getByRole("region", {
    name: "Claim and evidence review",
    exact: true,
  });
  const claimObject = claimReview.getByRole("combobox", {
    name: "Claim text object",
    exact: true,
  });
  await claimObject.locator("option").nth(1).waitFor({ state: "attached" });
  await claimObject.selectOption(
    await claimObject.locator("option").nth(1).getAttribute("value"),
  );
  await claimReview
    .getByLabel("Find project evidence", { exact: true })
    .fill("recovery");
  await claimReview
    .getByRole("button", { name: "Search evidence", exact: true })
    .click();
  await claimReview
    .getByRole("button", {
      name: "Link excerpt from strategy-notes.md",
      exact: true,
    })
    .click();
  await claimReview
    .getByLabel("Evidence relation for strategy-notes.md", { exact: true })
    .selectOption("supports");
  await claimReview
    .getByRole("button", {
      name: "Suggest relation for strategy-notes.md",
      exact: true,
    })
    .click();
  await claimReview
    .getByText("Suggested relation: context", { exact: true })
    .waitFor();
  assert.equal(
    await claimReview
      .getByLabel("Evidence relation for strategy-notes.md", { exact: true })
      .inputValue(),
    "supports",
  );
  await claimReview
    .getByRole("button", {
      name: "Use suggested relation for strategy-notes.md",
      exact: true,
    })
    .click();
  assert.equal(
    await claimReview
      .getByLabel("Evidence relation for strategy-notes.md", { exact: true })
      .inputValue(),
    "context",
  );
  await shot("workspace-claim-evidence-triage");
  await claimReview
    .getByLabel("Evidence relation for strategy-notes.md", { exact: true })
    .selectOption("supports");
  checks.push(
    "Finite claim/excerpt triage is explicitly requested, shows uncalibrated confidence, requires separate use and preserves manual relation review before save",
  );
  const saveClaim = claimReview.getByRole("button", {
    name: "Save reviewed claim",
    exact: true,
  });
  assert.equal(await saveClaim.isDisabled(), true);
  await claimReview
    .getByRole("checkbox", {
      name: "I reviewed the quote and evidence relations for this revision.",
      exact: true,
    })
    .check();
  await saveClaim.click();
  await claimReview
    .getByText("1 claim · 1 supported · 0 need review", { exact: true })
    .waitFor();
  await claimReview
    .getByRole("heading", { name: "Claims and evidence", exact: true })
    .scrollIntoViewIfNeeded();
  await noOverflow("Claim evidence review controls");
  await shot("workspace-claim-evidence-review");
  await studioPanel("Deck review");
  const deckReview = page.getByRole("region", {
    name: "Deck semantic review",
    exact: true,
  });
  const firstSemanticSlide = deckReview.getByRole("article", {
    name: "Slide 1 semantics",
    exact: true,
  });
  await firstSemanticSlide
    .getByText("Purpose: opening · reviewed for this revision", { exact: true })
    .waitFor();
  await firstSemanticSlide
    .getByText(/1 recorded claims: 1 supported/)
    .waitFor();
  await deckReview
    .getByRole("checkbox", {
      name: "Show attention items on this page",
      exact: true,
    })
    .check();
  assert.equal(await firstSemanticSlide.count(), 0);
  await deckReview
    .getByRole("checkbox", {
      name: "Show attention items on this page",
      exact: true,
    })
    .uncheck();
  await firstSemanticSlide.waitFor();
  await firstSemanticSlide.scrollIntoViewIfNeeded();
  assert.equal(
    await deckReview.evaluate(
      (panel) => panel.scrollWidth <= panel.clientWidth + 2,
    ),
    true,
  );
  await shot("workspace-deck-review-page");
  await deckReview
    .getByRole("button", { name: "Next review page", exact: true })
    .click();
  const laterSemanticSlide = deckReview.getByRole("article", {
    name: "Slide 21 semantics",
    exact: true,
  });
  await laterSemanticSlide.waitFor();
  await laterSemanticSlide
    .getByRole("button", { name: "Review slide 21", exact: true })
    .click();
  await page.getByText("Slide 21 of 22", { exact: true }).waitFor();
  await studioPanel("Deck review");
  await laterSemanticSlide.waitFor();
  await deckReview
    .getByRole("button", { name: "Previous review page", exact: true })
    .click();
  await firstSemanticSlide.waitFor();
  await firstSemanticSlide
    .getByRole("button", { name: "Review slide 1", exact: true })
    .click();
  await page.getByText("Slide 1 of 22", { exact: true }).waitFor();
  await claimReview
    .getByText("1 claim · 1 supported · 0 need review", { exact: true })
    .waitFor();
  checks.push(
    "Deck review pages purposes and claim coverage, filters attention on the displayed page and opens exact slides for review without a deck revision",
  );

  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  const claimEditPlan = page.getByRole("dialog", {
    name: "Copilot edit plan",
    exact: true,
  });
  await claimEditPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Clarify this slide's decision using the reviewed claim grounding.");
  await claimEditPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  const claimGrounding = claimEditPlan.getByRole("region", {
    name: "Claim grounding used",
    exact: true,
  });
  await claimGrounding
    .getByText("Slide 1 · supported", { exact: true })
    .waitFor();
  await claimGrounding
    .getByText("supports · current · excerpt supplied", { exact: true })
    .waitFor();
  await claimGrounding.scrollIntoViewIfNeeded();
  const takeawayContextUsed = claimEditPlan.getByRole("region", {
    name: "Slide takeaways used",
    exact: true,
  });
  await takeawayContextUsed
    .getByText("Approve the reversible pilot with a named owner.", {
      exact: true,
    })
    .waitFor();
  await takeawayContextUsed
    .getByText("Slide 1 · reviewed for this revision", { exact: true })
    .waitFor();
  await takeawayContextUsed.scrollIntoViewIfNeeded();
  await shot("workspace-copilot-takeaway-context");
  checks.push(
    "Copilot review exposes captured revision-bound slide takeaway intent separately from evidence",
  );
  const narrativeGrounding = page.getByRole("region", {
    name: "Narrative intent used",
    exact: true,
  });
  await narrativeGrounding
    .getByText("Approve a limited regional migration pilot.", { exact: true })
    .waitFor();
  await narrativeGrounding
    .getByText("Reviewed for the preparation revision.", { exact: true })
    .waitFor();
  await shot("workspace-copilot-reviewed-claim-grounding");
  await claimEditPlan
    .getByRole("button", { name: "Discard Copilot proposal", exact: true })
    .click();
  await claimEditPlan.waitFor({ state: "detached" });
  await revisionHistory
    .getByText("Current · Revision 1", { exact: true })
    .waitFor();
  checks.push(
    "Copilot proposal review shows exact captured claim coverage and whether linked grounding excerpts were supplied; discard preserves the revision",
  );

  checks.push(
    "Workspace binds an exact object quote to a reviewed source excerpt and support relation without editing the deck",
  );
  await studioPanel("Text");
  const replacementText = page.getByRole("textbox", {
    name: "Replacement text",
    exact: true,
  });
  await studioPanel("Text");
  const dictateInstruction = page.getByRole("button", {
    name: "Dictate instruction",
    exact: true,
  });
  await studioPanel("Text");
  await dictateInstruction.waitFor();
  await studioPanel("Text");
  assert.equal(await dictateInstruction.isEnabled(), true);
  checks.push(
    "Workspace enables local dictation for the selected supported text target",
  );
  await studioPanel("Text");
  await dictateInstruction.click();
  const voiceDialog = page.getByRole("dialog", {
    name: "Dictate an edit instruction",
    exact: true,
  });
  await voiceDialog.waitFor();
  await voiceDialog
    .getByText("Listening for your edit instruction…", { exact: true })
    .waitFor();
  assert.equal(
    await page
      .locator(".project-navigation")
      .getByRole("button", { name: "Sources", exact: true })
      .isDisabled(),
    true,
  );
  await voiceDialog
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await voiceDialog.waitFor({ state: "detached" });
  await studioPanel("Text");
  assert.equal(await dictateInstruction.isEnabled(), true);
  checks.push(
    "Workspace voice capture uses local Core ownership, locks navigation, and releases cleanly on cancel",
  );
  const rewriteField = page.getByRole("textbox", {
    name: "Rewrite instruction",
    exact: true,
  });
  const instructionBeforeHold = await rewriteField.inputValue();
  await holdVoice(rewriteField);
  await voiceDialog
    .getByText("Listening for your edit instruction…", { exact: true })
    .waitFor();
  await page.keyboard.down("Space");
  await releaseVoice();
  const heldReview = page.getByRole("dialog", {
    name: "Review spoken instruction",
    exact: true,
  });
  await heldReview
    .getByLabel("Review dictated instruction", { exact: true })
    .waitFor();
  assert.equal(await rewriteField.inputValue(), instructionBeforeHold);
  assert.equal(
    await heldReview
      .getByRole("button", { name: "Use reviewed instruction", exact: true })
      .isDisabled(),
    true,
  );
  await heldReview
    .getByLabel("Review dictated instruction", { exact: true })
    .fill("Clarify the recommendation without changing the numbers.");
  await shot("workspace-hold-selected-text-review");
  await heldReview
    .getByRole("button", { name: "Use reviewed instruction", exact: true })
    .click();
  assert.equal(
    await rewriteField.inputValue(),
    "Clarify the recommendation without changing the numbers.",
  );
  assert.equal(await page.locator(".pw-rewrite-proposal").count(), 0);
  await holdVoice(rewriteField);
  await voiceDialog
    .getByText("Listening for your edit instruction…", { exact: true })
    .waitFor();
  await page.keyboard.press("Escape");
  await releaseVoice();
  await voiceDialog.waitFor({ state: "detached" });
  assert.equal(await dictateInstruction.isEnabled(), true);
  checks.push(
    "Selected-text hold gesture reviews only its capture on release, ignores repeat, requires explicit use without a provider proposal, and cancels with Escape",
  );
  await studioPanel("Text");
  const textBeforeSuggestion = await replacementText.inputValue();
  await studioPanel("Text");
  await page
    .getByRole("textbox", { name: "Rewrite instruction", exact: true })
    .fill("Keep the selected wording unchanged for this review-flow check.");
  await studioPanel("Text");
  await page
    .getByRole("button", { name: "Suggest rewrite", exact: true })
    .click();
  await studioPanel("Text");
  const rewriteReview = page.locator(".pw-rewrite-proposal");
  await studioPanel("Text");
  await rewriteReview
    .getByText("Review rewrite suggestion", { exact: true })
    .waitFor();
  await studioPanel("Text");
  await rewriteReview.getByText("not applied", { exact: false }).waitFor();
  await studioPanel("Text");
  await page
    .getByRole("button", { name: "Use suggestion in editor", exact: true })
    .click();
  await studioPanel("Text");
  assert.equal(await replacementText.inputValue(), textBeforeSuggestion);
  await revisionHistory
    .getByText("Current · Revision 1", { exact: true })
    .waitFor();
  checks.push(
    "Rewrite suggestion is review-only and enters the existing preview/save flow",
  );
  await studioPanel("History");
  await revisionHistory
    .getByText("Original import · Revision 1", { exact: true })
    .waitFor();
  await studioPanel("Notes");
  await page
    .getByRole("textbox", { name: "Speaker notes", exact: true })
    .waitFor();
  await studioPanel("History");
  await page
    .getByLabel("What would you ask it to do?", { exact: true })
    .fill("Shorten the opening title and connect it to the recommendation.");
  await studioPanel("History");
  await page
    .getByRole("button", { name: "Record edit intent", exact: true })
    .click();
  await page.getByText(/Intent counted for this open view/).waitFor();
  await studioPanel("Text");
  const previewReplacement = page.getByRole("button", {
    name: "Preview replacement",
    exact: true,
  });
  const editPreviewImage = page.getByRole("img", {
    name: "Text edit preview on slide 1",
    exact: true,
  });
  await studioPanel("Text");
  await replacementText.fill(
    "Layout stress preview: " +
      "This replacement is intentionally long so the editor can check whether the text leaves its source box. ".repeat(
        8,
      ),
  );
  await studioPanel("Text");
  const saveTextRevision = page.getByRole("button", {
    name: "Save revision",
    exact: true,
  });
  await studioPanel("Text");
  assert.equal(
    await saveTextRevision.isDisabled(),
    true,
    "Changing replacement text invalidates its earlier preview",
  );
  await studioPanel("Text");
  await previewReplacement.click();
  await editPreviewImage.waitFor();
  const layoutReview = page.locator(
    ".pw-mock-edit [role=status], .pw-mock-edit .pw-layout-warning",
  );
  await layoutReview.waitFor();
  const layoutWarning = page.locator(".pw-mock-edit .pw-layout-warning");
  let overflowAcknowledgementShown = false;
  await studioPanel("Text");
  if (await layoutWarning.count()) {
    overflowAcknowledgementShown = true;
    await layoutWarning.scrollIntoViewIfNeeded();
    assert.equal(
      await page
        .locator(".pw-copilot-panel")
        .evaluate((panel) => panel.scrollWidth <= panel.clientWidth + 2),
      true,
      "Overflow acknowledgement does not introduce horizontal scrolling",
    );
    await shot("workspace-text-overflow-warning");
    assert.equal(
      await saveTextRevision.isDisabled(),
      true,
      "Detected text overflow needs a separate acknowledgement",
    );
    await layoutWarning.getByRole("checkbox").check();
    assert.equal(await saveTextRevision.isDisabled(), false);
  }
  await studioPanel("Text");
  await replacementText.fill("Edited in Core and saved as revision two");
  await studioPanel("Text");
  assert.equal(
    await saveTextRevision.isDisabled(),
    true,
    "Changing replacement text clears its preview and acknowledgement",
  );
  await studioPanel("Text");
  await previewReplacement.click();
  await editPreviewImage.waitFor();
  await layoutReview.waitFor();
  await studioPanel("Text");
  if (await layoutWarning.count()) {
    overflowAcknowledgementShown = true;
    assert.equal(await saveTextRevision.isDisabled(), true);
    await layoutWarning.getByRole("checkbox").check();
  }
  await studioPanel("Text");
  await saveTextRevision.click();
  await revisionHistory
    .getByText("Current · Revision 2", { exact: true })
    .waitFor();
  await studioPanel("Deck review");
  await firstSemanticSlide
    .getByText("Purpose: opening · inherited; needs review", { exact: true })
    .waitFor();
  await firstSemanticSlide
    .getByText("Claim or source needs review", { exact: true })
    .waitFor();
  await firstSemanticSlide
    .getByText(
      "Takeaway: Approve the reversible pilot with a named owner. · inherited; needs review",
      { exact: true },
    )
    .waitFor();
  await firstSemanticSlide
    .getByText("Inherited takeaway needs review", { exact: true })
    .waitFor();
  await firstSemanticSlide.scrollIntoViewIfNeeded();
  await shot("workspace-deck-review-inherited");
  checks.push(
    "Deck edits mark inherited purpose and changed claim coverage for review in the deck-wide overview",
  );
  await firstSemanticSlide
    .getByRole("button", { name: "Review slide 1", exact: true })
    .click();
  await takeawayReview
    .getByText("Inherited takeaway needs review for this revision.", {
      exact: true,
    })
    .waitFor();
  assert.equal(
    await takeawayDraft.inputValue(),
    "Approve the reversible pilot with a named owner.",
  );
  await takeawayReview
    .getByRole("button", { name: "Clear takeaway draft", exact: true })
    .click();
  assert.equal(await takeawayDraft.inputValue(), "");
  assert.equal(
    await takeawayReview
      .getByRole("button", { name: "Save reviewed takeaway", exact: true })
      .isDisabled(),
    true,
  );
  await takeawayReview
    .getByRole("button", { name: "Reload saved takeaway", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelector('[aria-label="Slide takeaway"]')?.value ===
      "Approve the reversible pilot with a named owner.",
  );
  await takeawayReview.scrollIntoViewIfNeeded();
  await shot("workspace-inherited-slide-takeaway");
  await takeawayReview
    .getByRole("button", { name: "Clear takeaway draft", exact: true })
    .click();
  await takeawayReview
    .getByRole("checkbox", {
      name: "I reviewed this takeaway for the current slide.",
      exact: true,
    })
    .check();
  await takeawayReview
    .getByRole("button", { name: "Save reviewed takeaway", exact: true })
    .click();
  await takeawayReview
    .getByText("Takeaway reviewed for this revision.", { exact: true })
    .waitFor();
  await studioPanel("Deck review");
  await firstSemanticSlide
    .getByText("No recorded takeaway.", { exact: true })
    .waitFor();
  checks.push(
    "Native edits mark inherited takeaways for review; clearing stays draft-only until acknowledgment and reviewed blank save updates deck review",
  );
  await studioPanel("Narrative");
  await narrativePanel
    .getByText(
      "Inherited narrative: review it against this revision before saving.",
      { exact: true },
    )
    .waitFor();
  assert.equal(
    await narrativePanel
      .getByLabel("Presentation objective", { exact: true })
      .inputValue(),
    "Approve a limited regional migration pilot.",
  );
  await narrativePanel
    .getByRole("button", { name: "Clear narrative draft", exact: true })
    .click();
  assert.equal(
    await narrativePanel
      .getByRole("button", { name: "Save reviewed narrative", exact: true })
      .isDisabled(),
    true,
  );
  await narrativePanel
    .getByRole("button", { name: "Reload saved narrative", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelector('textarea[aria-label="Presentation objective"]')
        ?.value === "Approve a limited regional migration pilot.",
  );
  await narrativePanel
    .getByText(
      "Inherited narrative: review it against this revision before saving.",
      { exact: true },
    )
    .waitFor();
  assert.equal(
    await narrativePanel
      .getByLabel("Presentation objective", { exact: true })
      .inputValue(),
    "Approve a limited regional migration pilot.",
  );
  checks.push(
    "Deck edits mark inherited narrative for review; clearing a draft is reversible and captured intent is visible in Copilot review",
  );
  await studioPanel("Text");

  await studioPanel("History");
  await revisionHistory
    .getByText("Edited · Revision 2", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Saved revision 2 and refreshed its slide text for retrieval/)
    .waitFor();
  await studioPanel("Purpose");
  await slidePurposePanel
    .getByText("Saved purpose: opening", { exact: true })
    .waitFor({ state: "detached" });
  await claimReview
    .getByText("1 claim · 0 supported · 1 need review", { exact: true })
    .waitFor();
  await claimReview
    .getByRole("heading", { name: "Claims and evidence", exact: true })
    .scrollIntoViewIfNeeded();
  await noOverflow("Claim evidence review controls");
  await shot("workspace-claim-evidence-needs-review");
  checks.push(
    "A deck edit retains claim evidence snapshots while requiring review of inherited bindings on the new revision",
  );

  await studioPanel("Notes");
  await page
    .getByRole("textbox", { name: "Speaker notes", exact: true })
    .fill("Edited speaker notes from the workspace");
  await studioPanel("Notes");
  await page
    .getByRole("button", { name: "Save speaker notes", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 3", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Saved revision 3 and refreshed its speaker notes for retrieval/)
    .waitFor();
  await studioPanel("Notes");
  assert.equal(
    await page
      .getByRole("textbox", { name: "Speaker notes", exact: true })
      .inputValue(),
    "Edited speaker notes from the workspace",
  );
  await studioPanel("Objects");
  await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .selectOption({
      label: "Workspace transform test shape · sp · editable",
    });
  await page
    .getByRole("spinbutton", { name: "X position (inches)", exact: true })
    .fill("8.250");
  await page
    .getByRole("button", { name: "Save object layout", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 4", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Saved revision 4 and refreshed the slide layout/)
    .waitFor();
  assert.equal(
    await page
      .getByRole("spinbutton", { name: "X position (inches)", exact: true })
      .inputValue(),
    "8.250",
  );
  await page
    .getByRole("button", { name: "Move current slide later", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 5", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Moved the slide to position 2 and refreshed slide retrieval/)
    .waitFor();
  await page
    .getByRole("img", {
      name: "Imported presentation, slide 2",
      exact: true,
    })
    .waitFor();
  await studioPanel("Objects");
  await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .selectOption({
      label: "Workspace transform test shape · sp · editable",
    });
  await page
    .getByRole("button", { name: "Duplicate selected object", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 6", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Duplicated the object and refreshed slide 2/)
    .waitFor();
  assert.equal(
    await page
      .getByRole("spinbutton", { name: "X position (inches)", exact: true })
      .inputValue(),
    "8.500",
    "The new stable object is selected after duplication",
  );
  await studioPanel("Objects");
  await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .selectOption({
      label: "Workspace transform test shape copy · sp · editable",
    });
  await page
    .getByRole("button", { name: "Review object deletion", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Confirm delete selected object",
      exact: true,
    })
    .click();
  await revisionHistory
    .getByText("Current · Revision 7", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Deleted the object and refreshed slide 2/)
    .waitFor();
  await studioPanel("Objects");
  assert.equal(
    await page
      .getByRole("option", {
        name: "Workspace transform test shape copy · sp · editable",
        exact: true,
      })
      .count(),
    0,
    "Deleted copies disappear from the current slide inventory",
  );
  assert.equal(
    await page
      .getByRole("option", {
        name: "Workspace transform test shape · sp · editable",
        exact: true,
      })
      .count(),
    1,
    "Deleting a copy preserves the original shape",
  );
  await page
    .getByRole("button", { name: "Duplicate current slide", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 8", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Duplicated slide 2 and refreshed slide retrieval/)
    .waitFor();
  await page
    .getByRole("img", {
      name: "Imported presentation, slide 3",
      exact: true,
    })
    .waitFor();
  await studioPanel("Notes");
  assert.equal(
    await page
      .getByRole("textbox", { name: "Speaker notes", exact: true })
      .inputValue(),
    "Edited speaker notes from the workspace",
    "Duplicated slides retain their speaker notes",
  );
  await page
    .getByRole("button", {
      name: "Review current slide deletion",
      exact: true,
    })
    .click();
  const slideDeletionConfirmation = page.getByRole("group", {
    name: "Confirm slide deletion",
    exact: true,
  });
  await slideDeletionConfirmation.getByText(/Delete slide 3\?/).waitFor();
  await slideDeletionConfirmation
    .getByRole("button", { name: "Confirm delete current slide", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 9", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Deleted slide 3 and refreshed slide retrieval/)
    .waitFor();
  await page.getByText("Slide 3 of 22", { exact: true }).waitFor();
  await studioPanel("Notes");
  assert.equal(
    await page
      .getByRole("textbox", { name: "Speaker notes", exact: true })
      .inputValue(),
    "Synthetic presenter note for slide 3.",
    "Deleting the duplicate keeps the following original slide in place",
  );
  await studioPanel("Text");
  const boldButton = page.getByRole("button", { name: "Bold", exact: true });
  const boldBefore = await boldButton.getAttribute("aria-pressed");
  await boldButton.click();
  await revisionHistory
    .getByText("Current · Revision 10", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Saved formatting revision 10/)
    .waitFor();
  assert.notEqual(await boldButton.getAttribute("aria-pressed"), boldBefore);
  await studioPanel("Objects");
  await page
    .getByRole("textbox", { name: "New text box text", exact: true })
    .fill("Created in the workspace");
  await studioPanel("Objects");
  await page.getByRole("button", { name: "Add text box", exact: true }).click();
  await revisionHistory
    .getByText("Current · Revision 11", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Added a text box in revision 11/)
    .waitFor();
  await studioPanel("Text");
  assert.equal(
    await page
      .getByRole("textbox", { name: "Replacement text", exact: true })
      .inputValue(),
    "Created in the workspace",
    "The new text box is selected for direct text editing",
  );
  await studioPanel("Objects");
  assert.equal(
    await page
      .getByRole("combobox", { name: "Object to edit", exact: true })
      .locator("option:checked")
      .innerText(),
    "Text Box · sp · editable",
  );
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await studioPanel("Objects");
  await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .selectOption({
      label: "Workspace transform test shape · sp · editable",
    });
  await studioPanel("Objects");
  await page
    .getByLabel("Shape fill color", { exact: true })
    .evaluate((input) => {
      const color = input;
      color.value = "#FF00AA";
      color.dispatchEvent(new Event("input", { bubbles: true }));
      color.dispatchEvent(new Event("change", { bubbles: true }));
    });
  await page
    .getByRole("button", { name: "Apply fill color", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 12", { exact: true })
    .waitFor();
  await studioPanel("Objects");
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Saved revision 12 and refreshed the shape color/)
    .waitFor();
  await studioPanel("Objects");
  assert.equal(
    await page.getByLabel("Shape fill color", { exact: true }).inputValue(),
    "#ff00aa",
  );
  await studioPanel("Objects");
  await page
    .getByLabel("Shape outline color", { exact: true })
    .evaluate((input) => {
      const color = input;
      color.value = "#13579B";
      color.dispatchEvent(new Event("input", { bubbles: true }));
      color.dispatchEvent(new Event("change", { bubbles: true }));
    });
  await page
    .getByRole("button", { name: "Apply outline color", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 13", { exact: true })
    .waitFor();
  await studioPanel("Objects");
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Saved revision 13 and refreshed the shape color/)
    .waitFor();
  await studioPanel("Objects");
  assert.equal(
    await page.getByLabel("Shape outline color", { exact: true }).inputValue(),
    "#13579b",
  );
  await studioPanel("Objects");
  await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .selectOption({
      label: "Workspace duplicate test picture · pic · editable",
    });
  await studioPanel("Objects");
  await page
    .getByRole("spinbutton", { name: "Left crop (%)", exact: true })
    .fill("10.5");
  await studioPanel("Objects");
  await page
    .getByRole("button", { name: "Save picture crop", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 14", { exact: true })
    .waitFor();
  await studioPanel("Objects");
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Saved revision 14 and refreshed the picture crop/)
    .waitFor();
  await studioPanel("Objects");
  assert.equal(
    await page
      .getByRole("spinbutton", { name: "Left crop (%)", exact: true })
      .inputValue(),
    "10.5",
  );
  await studioPanel("Objects");
  await noOverflow("Workspace picture-crop controls");
  await studioPanel("Objects");
  await shot("09-presentation-workspace-picture-crop");
  await studioPanel("Objects");
  await page
    .getByLabel("Replacement picture image", { exact: true })
    .setInputFiles({
      name: "replacement.png",
      mimeType: "image/png",
      buffer: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGMUVDJmYGBgYgADAATQAGoNqSJLAAAAAElFTkSuQmCC",
        "base64",
      ),
    });
  await studioPanel("Objects");
  await page
    .getByRole("button", { name: "Replace picture image", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 15", { exact: true })
    .waitFor();
  await studioPanel("Objects");
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Saved revision 15 and replaced the picture image/)
    .waitFor();
  await studioPanel("Objects");
  await noOverflow("Workspace picture-image replacement controls");
  await shot("10-presentation-workspace-image-replacement");
  await studioPanel("Objects");
  await page.getByLabel("Picture to add", { exact: true }).setInputFiles({
    name: "new-picture.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGMUVDJmYGBgYgADAATQAGoNqSJLAAAAAElFTkSuQmCC",
      "base64",
    ),
  });
  await studioPanel("Objects");
  const addPictureButton = page.getByRole("button", {
    name: "Add picture",
    exact: true,
  });
  await studioPanel("Objects");
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll("button")].find(
      (item) => item.textContent?.trim() === "Add picture",
    );
    return button !== undefined && !button.matches(":disabled");
  });
  await studioPanel("Objects");
  await page
    .getByRole("button", { name: "Browse deck pictures", exact: true })
    .click();
  const reusedAsset = page
    .locator(".pw-deck-asset-grid article")
    .filter({ hasText: "2 × 2" })
    .first();
  await reusedAsset.getByRole("img").waitFor();
  await shot("workspace-deck-picture-assets");
  await reusedAsset.getByRole("button").click();
  await page.getByText(/Selected: .*\.png/).waitFor();
  await revisionHistory
    .getByText("Current · Revision 15", { exact: true })
    .waitFor();
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll("button")].find(
      (item) => item.textContent?.trim() === "Add picture",
    );
    return button && !button.matches(":disabled");
  });
  checks.push(
    "Deck picture thumbnails and verified reuse fill the insertion form without creating a revision; the selected embedded PNG is inserted through ordinary native creation",
  );
  await page
    .getByLabel("Alternative text (optional)", { exact: true })
    .fill("Added workspace picture");
  await studioPanel("Objects");
  await page
    .getByRole("spinbutton", { name: "New picture X position (inches)" })
    .fill("1");
  await studioPanel("Objects");
  await page
    .getByRole("spinbutton", { name: "New picture Y position (inches)" })
    .fill("1");
  await studioPanel("Objects");
  await page
    .getByRole("spinbutton", { name: "New picture Width (inches)" })
    .fill("1.25");
  await studioPanel("Objects");
  await page
    .getByRole("spinbutton", { name: "New picture Height (inches)" })
    .fill("1.25");
  await studioPanel("Objects");
  await addPictureButton.click();
  await revisionHistory
    .getByText("Current · Revision 16", { exact: true })
    .waitFor();
  await studioPanel("Objects");
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Added a picture in revision 16/)
    .waitFor();
  await studioPanel("Objects");
  assert.match(
    await page
      .getByRole("combobox", { name: "Object to edit", exact: true })
      .locator("option:checked")
      .innerText(),
    /^Picture(?: \d+)? · pic · editable$/,
  );
  await studioPanel("Objects");
  await noOverflow("Workspace picture-creation controls");
  await studioPanel("Objects");
  await shot("11-presentation-workspace-picture-creation");
  const projectPictures = page.getByRole("group", {
    name: "Project pictures",
    exact: true,
  });
  await projectPictures
    .getByLabel("Upload project picture", { exact: true })
    .setInputFiles({
      name: "project-visual.png",
      mimeType: "image/png",
      buffer: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGMUVDJmYGBgYgADAATQAGoNqSJLAAAAAElFTkSuQmCC",
        "base64",
      ),
    });
  await projectPictures
    .getByRole("button", { name: "Use project-visual.png", exact: true })
    .waitFor();
  await projectPictures
    .getByRole("button", { name: "Use project-visual.png", exact: true })
    .click();
  await addPictureButton.waitFor();
  await revisionHistory
    .getByText("Current · Revision 16", { exact: true })
    .waitFor();
  await shot("workspace-project-picture-library");
  checks.push(
    "Project picture upload persists in the reusable library and fills insertion controls without changing the deck revision",
  );

  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  const assetEditPlan = page.getByRole("dialog", {
    name: "Copilot edit plan",
    exact: true,
  });
  await assetEditPlan
    .getByRole("button", { name: "Browse project pictures", exact: true })
    .click();
  const planAsset = assetEditPlan
    .locator(".pw-deck-asset-grid article")
    .filter({ hasText: "2 × 2" })
    .first();
  await planAsset
    .getByRole("button", { name: "Attach project-visual.png", exact: true })
    .click();
  await assetEditPlan
    .getByRole("region", { name: "Attached deck pictures", exact: true })
    .waitFor();
  await assetEditPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Insert the attached picture at the lower right.");
  await assetEditPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await assetEditPlan
    .getByRole("img", { name: "Copilot proposed slide 2", exact: true })
    .waitFor({ timeout: 30_000 });
  await assetEditPlan
    .getByText("Viewed 1 of 1 affected slides.", { exact: true })
    .waitFor();
  await assetEditPlan
    .getByText("Insert an attached picture · original slide 2", { exact: true })
    .waitFor();
  await assetEditPlan.getByRole("checkbox").check();
  assert.equal(
    await assetEditPlan
      .getByRole("button", { name: "Save Copilot changes", exact: true })
      .isEnabled(),
    true,
  );
  await shot("workspace-copilot-attached-picture");
  await assetEditPlan.getByText("Edit your request", { exact: true }).click();
  await assetEditPlan
    .getByRole("region", { name: "Attached deck pictures", exact: true })
    .getByRole("button", { name: "Remove project-visual.png", exact: true })
    .click();
  await assetEditPlan
    .getByText(
      "Your request changed. Propose the revised request before saving.",
      { exact: true },
    )
    .waitFor();
  assert.equal(
    await assetEditPlan
      .getByRole("button", { name: "Save Copilot changes", exact: true })
      .isEnabled(),
    false,
  );
  await assetEditPlan
    .getByRole("button", { name: "Discard Copilot proposal", exact: true })
    .click();
  await assetEditPlan.waitFor({ state: "detached" });
  await revisionHistory
    .getByText("Current · Revision 16", { exact: true })
    .waitFor();
  checks.push(
    "Copilot attaches an explicitly selected project picture, previews Core-bound image insertion, requires review, invalidates save after attachment removal and discards without a revision",
  );

  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll("button")].find(
      (item) =>
        item.getAttribute("aria-label") ===
        "Save a copy of the current presentation revision",
    );
    return button !== undefined && !button.matches(":disabled");
  });
  await studioPanel("Objects");
  await projectPictures
    .getByRole("button", { name: "Browse project pictures", exact: true })
    .click();
  await projectPictures
    .getByRole("button", {
      name: "Remove library item project-visual.png",
      exact: true,
    })
    .click();
  await projectPictures
    .getByRole("button", {
      name: "Confirm remove project-visual.png",
      exact: true,
    })
    .click();
  await projectPictures
    .getByText("No reusable PNG or JPEG pictures on this page.", {
      exact: true,
    })
    .waitFor();
  await revisionHistory
    .getByText("Current · Revision 16", { exact: true })
    .waitFor();
  checks.push(
    "Confirmed project-library removal leaves the current deck revision unchanged",
  );
  const exportDirectory = path.join(temporary, "exports");
  await mkdir(exportDirectory, { recursive: true });
  const currentCopyPath = path.join(exportDirectory, "current-revision.pptx");
  const currentOpenCopyPath = path.join(
    exportDirectory,
    "current-revision-open.pptx",
  );
  const originalCopyPath = path.join(exportDirectory, "original-copy.pptx");
  await app.evaluate(
    ({ dialog, shell }, destination) => {
      dialog.showSaveDialog = async (_parent, options) => {
        if (!options?.properties?.includes("showOverwriteConfirmation")) {
          throw new Error(
            "Save dialog must confirm overwriting an existing file.",
          );
        }
        const selected = options.title?.includes("open")
          ? destination.currentOpen
          : options.title?.includes("current")
            ? destination.current
            : destination.original;
        return { canceled: false, filePath: selected };
      };
      globalThis.__presenterWorkspaceTest = {
        originalOpenPath: shell.openPath,
        openedPath: null,
      };
      shell.openPath = async (openedPath) => {
        globalThis.__presenterWorkspaceTest.openedPath = openedPath;
        return "";
      };
    },
    {
      current: currentCopyPath,
      currentOpen: currentOpenCopyPath,
      original: originalCopyPath,
    },
  );
  await saveAndOpenCopyButton.click();
  const saveNotice = page.locator(".pw-slide-column .pw-notice");
  await saveNotice.getByText(/Saved and opened current revision:/).waitFor();
  assert.equal((await saveNotice.innerText()).includes(temporary), false);
  const openedPath = await app.evaluate(
    () => globalThis.__presenterWorkspaceTest.openedPath,
  );
  assert.equal(openedPath, currentOpenCopyPath);
  const currentOpenBytes = await readFile(currentOpenCopyPath);
  assert.ok(currentOpenBytes.length > 0, "Opened revision is a nonempty PPTX");
  await app.evaluate(({ shell }) => {
    const state = globalThis.__presenterWorkspaceTest;
    if (state?.originalOpenPath) shell.openPath = state.originalOpenPath;
    delete globalThis.__presenterWorkspaceTest;
  });
  await saveCurrentCopyButton.click();
  await saveNotice.getByText(/Saved current revision:/).waitFor();
  assert.equal((await saveNotice.innerText()).includes(temporary), false);
  const currentBytes = await readFile(currentCopyPath);
  const fixtureBytes = await readFile(fixture);
  assert.notDeepEqual(currentBytes, fixtureBytes);
  assert.deepEqual(currentOpenBytes, currentBytes);
  assert.ok(currentBytes.length > 0, "Edited revision is a nonempty PPTX copy");

  if (process.env.PRESENTER_TEST_NATIVE_PDF === "1") {
    const pdfButton = page.getByRole("button", {
      name: "Export PDF",
      exact: true,
    });
    const pdfBefore = await page.evaluate(async () => {
      const projects = await window.presenterCopilot.core.request(
        "project.list",
        {},
      );
      if (!projects.ok) throw new Error("Missing projects");
      const project = projects.result.projects.find(
        (item) => item.name === "Quarterly strategy review",
      );
      const sources = await window.presenterCopilot.core.request(
        "source.list",
        { project_id: project.id },
      );
      if (!sources.ok) throw new Error("Missing sources");
      const source = sources.result.sources.find(
        (item) => item.original_name === "presentation.pptx",
      );
      const revisions = await window.presenterCopilot.core.request(
        "presentation.workspace.list_revisions",
        {
          project_id: project.id,
          document_id: source.id,
        },
      );
      if (!revisions.ok) throw new Error("Missing revision");
      return {
        projectId: project.id,
        documentId: source.id,
        revisionId: revisions.result.current_revision_id,
      };
    });
    await pdfButton.click();
    const pdfDialog = page.getByRole("dialog", {
      name: "Export presentation as PDF",
      exact: true,
    });
    await pdfDialog.waitFor();
    assert.equal(
      await pdfDialog.getByLabel("Include hidden slides").isChecked(),
      false,
    );
    await noOverflow("PDF options");
    await shot("workspace-pdf-options");
    await page.keyboard.press("Escape");
    assert.equal(await pdfDialog.count(), 0);
    checks.push(
      "PDF options disclose static slides and omit hidden slides by default; Escape cancels",
    );
    await app.evaluate(({ dialog }) => {
      globalThis.__presenterPdfOriginalSaveDialog = dialog.showSaveDialog;
      dialog.showSaveDialog = async () => ({ canceled: true });
    });
    await pdfButton.click();
    await pdfDialog
      .getByRole("button", { name: "Choose PDF destination", exact: true })
      .click();
    await pdfDialog
      .getByRole("button", { name: "Choose PDF destination", exact: true })
      .waitFor({ state: "visible" });
    await page.waitForFunction(
      () =>
        ![...document.querySelectorAll("dialog button")].find(
          (button) => button.textContent === "Choose PDF destination",
        )?.disabled,
    );
    await pdfDialog
      .getByRole("button", { name: "Cancel", exact: true })
      .click();
    checks.push(
      "Cancelled native PDF destination returns to editable options without creating a revision",
    );
    for (const hidden of [false, true]) {
      const destination = path.join(
        exportDirectory,
        hidden ? "current-including-hidden.pdf" : "current-visible.pdf",
      );
      await app.evaluate(({ dialog }, destination) => {
        dialog.showSaveDialog = async (_parent, options) => {
          if (
            !options.properties.includes("showOverwriteConfirmation") ||
            options.filters[0].extensions[0] !== "pdf"
          )
            throw new Error("PDF picker contract failed");
          return { canceled: false, filePath: destination };
        };
      }, destination);
      await pdfButton.click();
      await pdfDialog.getByLabel("Include hidden slides").setChecked(hidden);
      await pdfDialog
        .getByRole("button", { name: "Choose PDF destination", exact: true })
        .click();
      await saveNotice
        .getByText(
          new RegExp(
            `Exported revision 16 as ${hidden ? "current-including-hidden" : "current-visible"}\\.pdf:`,
          ),
        )
        .waitFor({ timeout: 140_000 });
      assert.equal((await saveNotice.innerText()).includes(temporary), false);
      assert.match(
        await saveNotice.innerText(),
        hidden ? /including hidden slides/ : /hidden slides omitted/,
      );
      const bytes = await readFile(destination);
      assert.equal(bytes.subarray(0, 5).toString(), "%PDF-");
      assert.ok(bytes.length > 1000);
      await writeFile(
        path.join(
          output,
          hidden ? "workspace-including-hidden.pdf" : "workspace-visible.pdf",
        ),
        bytes,
      );
      checks.push(
        `Native PowerPoint PDF export through real privileged IPC, ${hidden ? "including" : "omitting"} hidden slides`,
      );
    }
    const pdfAfter = await page.evaluate(async (target) => {
      const result = await window.presenterCopilot.core.request(
        "presentation.workspace.list_revisions",
        {
          project_id: target.projectId,
          document_id: target.documentId,
        },
      );
      if (!result.ok) throw new Error("Missing revision after export");
      return result.result.current_revision_id;
    }, pdfBefore);
    assert.equal(pdfAfter, pdfBefore.revisionId);
    await shot("workspace-pdf-exported");
    checks.push("PDF exports leave the immutable revision head unchanged");
    await app.evaluate(({ dialog }) => {
      dialog.showSaveDialog = globalThis.__presenterPdfOriginalSaveDialog;
      delete globalThis.__presenterPdfOriginalSaveDialog;
    });
  }

  await saveOriginalCopyButton.click();
  await saveNotice.getByText(/Saved unchanged copy:/).waitFor();
  const originalBytes = await readFile(originalCopyPath);
  assert.deepEqual(originalBytes, fixtureBytes);
  assert.equal(
    createHash("sha256").update(originalBytes).digest("hex"),
    deckHashBeforePreview,
  );
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 15", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(
      /Undid to revision 15 and refreshed its slide text for retrieval/,
    )
    .waitFor();
  await revisionHistory
    .getByRole("button", { name: "Redo presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 16", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(
      /Redid to revision 16 and refreshed its slide text for retrieval/,
    )
    .waitFor();
  await studioPanel("History");
  await revisionHistory
    .getByRole("button", { name: "Restore revision 1", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 1", { exact: true })
    .waitFor();
  await studioPanel("Purpose");
  await slidePurposePanel
    .getByText("Saved purpose: opening", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Restored revision 1 and refreshed its slide text for retrieval/)
    .waitFor();
  await page
    .getByLabel("Layout source slide", { exact: true })
    .selectOption({ label: "Layout from slide 2" });
  await page
    .getByRole("button", {
      name: "Add blank slide after current slide",
      exact: true,
    })
    .click();
  await revisionHistory
    .getByText("Current · Revision 17", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(
      /Added a blank slide after slide \d+ using the layout from slide 2 and refreshed slide retrieval/,
    )
    .waitFor();
  await studioPanel("Notes");
  await page
    .getByText("This slide has no editable speaker-notes body.", {
      exact: true,
    })
    .waitFor();
  await studioPanel("Objects");
  await page
    .getByRole("textbox", { name: "New text box text", exact: true })
    .fill("Created on the new blank slide");
  await studioPanel("Objects");
  await page.getByRole("button", { name: "Add text box", exact: true }).click();
  await revisionHistory
    .getByText("Current · Revision 18", { exact: true })
    .waitFor();
  await studioPanel("Text");
  assert.equal(
    await page
      .getByRole("textbox", { name: "Replacement text", exact: true })
      .inputValue(),
    "Created on the new blank slide",
  );
  const slidePreview = page.locator(".pw-canvas img");
  await studioPanel("Objects");
  const previewUrlBeforeShape = await slidePreview.getAttribute("src");
  await studioPanel("Objects");
  const previewBeforeShape = await slidePreview.screenshot();
  await studioPanel("Objects");
  await page
    .getByRole("combobox", { name: "New shape type", exact: true })
    .selectOption("rect");
  await studioPanel("Objects");
  await page
    .getByLabel("New shape fill color", { exact: true })
    .evaluate((input) => {
      const color = input;
      color.value = "#FFAA00";
      color.dispatchEvent(new Event("input", { bubbles: true }));
      color.dispatchEvent(new Event("change", { bubbles: true }));
    });
  await studioPanel("Objects");
  await page
    .getByLabel("New shape outline color", { exact: true })
    .evaluate((input) => {
      const color = input;
      color.value = "#0044AA";
      color.dispatchEvent(new Event("input", { bubbles: true }));
      color.dispatchEvent(new Event("change", { bubbles: true }));
    });
  await studioPanel("Objects");
  await page
    .getByRole("spinbutton", { name: "New shape X position (inches)" })
    .fill("1");
  await studioPanel("Objects");
  await page
    .getByRole("spinbutton", { name: "New shape Y position (inches)" })
    .fill("1");
  await studioPanel("Objects");
  await page
    .getByRole("spinbutton", { name: "New shape Width (inches)" })
    .fill("2");
  await studioPanel("Objects");
  await page
    .getByRole("spinbutton", { name: "New shape Height (inches)" })
    .fill("1.5");
  await studioPanel("Objects");
  await page.getByRole("button", { name: "Add shape", exact: true }).click();
  await revisionHistory
    .getByText("Current · Revision 19", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Added a rectangle in revision 19/)
    .waitFor();
  await page.waitForFunction((previousUrl) => {
    const image = document.querySelector(".pw-canvas img");
    return (
      image?.tagName === "IMG" &&
      image.complete &&
      image.naturalWidth > 0 &&
      image.src !== previousUrl
    );
  }, previewUrlBeforeShape);
  await studioPanel("Objects");
  const previewAfterShape = await slidePreview.screenshot();
  assert.notDeepEqual(
    previewAfterShape,
    previewBeforeShape,
    "The preview should repaint after creating the rectangle.",
  );
  await studioPanel("Objects");
  assert.equal(
    await page
      .getByRole("combobox", { name: "Object to edit", exact: true })
      .locator("option:checked")
      .innerText(),
    "Rectangle · sp · editable",
  );
  await studioPanel("Objects");
  assert.equal(
    await page.getByLabel("Shape fill color", { exact: true }).inputValue(),
    "#ffaa00",
  );
  await studioPanel("Objects");
  assert.equal(
    await page.getByLabel("Shape outline color", { exact: true }).inputValue(),
    "#0044aa",
  );
  await page
    .getByRole("button", { name: "Previous slide", exact: true })
    .click();
  await page.getByText("Slide 1 of 23", { exact: true }).waitFor();
  await studioPanel("Text");
  const textTargetChoice = page.getByRole("combobox", {
    name: "Text on this slide",
    exact: true,
  });
  await studioPanel("Text");
  const multiParagraphTarget = textTargetChoice.locator("option").nth(1);
  assert.match(
    await multiParagraphTarget.innerText(),
    /Content Placeholder 2/,
    "The isolated preview exposes the fixture's supported multi-paragraph target",
  );
  await studioPanel("Text");
  await textTargetChoice.selectOption({ index: 1 });
  await studioPanel("Text");
  const paragraphAlignment = page.getByRole("combobox", {
    name: /Paragraph alignment/,
  });
  await studioPanel("Text");
  await paragraphAlignment.selectOption("center");
  await studioPanel("Text");
  const paragraphBulletMode = page.getByRole("combobox", {
    name: "Bullet style",
    exact: true,
  });
  await studioPanel("Text");
  await paragraphBulletMode.selectOption("bullet_hollow");
  await studioPanel("Text");
  const paragraphLeftIndent = page.getByRole("spinbutton", {
    name: /Left indent \(points, 0–144\)/,
  });
  await studioPanel("Text");
  await paragraphLeftIndent.fill("24");
  await studioPanel("Text");
  const paragraphFirstLineIndent = page.getByRole("spinbutton", {
    name: /First-line \/ hanging indent \(points, -144–144\)/,
  });
  await studioPanel("Text");
  await paragraphFirstLineIndent.fill("-9");
  await studioPanel("Text");
  const paragraphLineSpacing = page.getByRole("spinbutton", {
    name: /Line spacing \(points, 1–144\)/,
  });
  await studioPanel("Text");
  await paragraphLineSpacing.fill("22");
  await studioPanel("Text");
  const paragraphSpaceBefore = page.getByRole("spinbutton", {
    name: /Space before \(points, 0–144\)/,
  });
  await studioPanel("Text");
  await paragraphSpaceBefore.fill("12");
  await studioPanel("Text");
  const paragraphSpaceAfter = page.getByRole("spinbutton", {
    name: /Space after \(points, 0–144\)/,
  });
  await studioPanel("Text");
  await paragraphSpaceAfter.fill("6");
  await studioPanel("Text");
  await page
    .getByRole("button", { name: "Apply paragraph format", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 20", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Saved formatting revision 20/)
    .waitFor();
  await studioPanel("Text");
  assert.match(
    await textTargetChoice.locator("option:checked").innerText(),
    /Content Placeholder 2/,
    "The formatted target remains selected after saving",
  );
  await studioPanel("Text");
  assert.equal(await paragraphAlignment.inputValue(), "center");
  await studioPanel("Text");
  assert.equal(await paragraphBulletMode.inputValue(), "bullet_hollow");
  await studioPanel("Text");
  assert.equal(await paragraphLeftIndent.inputValue(), "24");
  await studioPanel("Text");
  assert.equal(await paragraphFirstLineIndent.inputValue(), "-9");
  await studioPanel("Text");
  assert.equal(await paragraphLineSpacing.inputValue(), "22");
  await studioPanel("Text");
  assert.equal(await paragraphSpaceBefore.inputValue(), "12");
  await studioPanel("Text");
  assert.equal(await paragraphSpaceAfter.inputValue(), "6");
  await page.getByRole("button", { name: "Next slide", exact: true }).click();
  await page.getByText("Slide 2 of 23", { exact: true }).waitFor();
  const layoutSourceSlide = page.getByLabel("Layout source slide", {
    exact: true,
  });
  await layoutSourceSlide.selectOption({ label: "Layout from slide 1" });
  await page
    .getByRole("button", {
      name: "Apply selected layout to current slide",
      exact: true,
    })
    .click();
  await revisionHistory
    .getByText("Current · Revision 21", { exact: true })
    .waitFor();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(
      /Applied the layout from slide 1 to slide 2 and refreshed slide retrieval/,
    )
    .waitFor();
  await studioPanel("Text");
  assert.equal(
    await page.getByLabel("Replacement text", { exact: true }).inputValue(),
    "Created on the new blank slide",
    "Applying a layout preserves slide text objects.",
  );
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 20", { exact: true })
    .waitFor();
  await revisionHistory
    .getByRole("button", { name: "Redo presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 21", { exact: true })
    .waitFor();
  await noOverflow("Workspace shape-creation controls");
  await studioPanel("Objects");
  checks.push(
    "Core saves and indexes text, direct text and multi-paragraph formatting including predefined bullet glyphs, paragraph alignment, indentation, line and before/after spacing, shape fill/outline formatting, shape and picture creation, picture cropping and replacement, blank-slide creation using another slide's layout, existing-slide layout application with text preservation and undo/redo, text-box creation, speaker-notes, object-layout, object-duplication, slide-order, slide duplication/deletion, and safe object-deletion revisions, exports current and immutable original copies, verifies the save-and-open handoff with OS launching mocked, supports undo/redo, then restores and re-indexes revision 1",
  );
  checks.push(
    overflowAcknowledgementShown
      ? "Text overflow preview requires a separate acknowledgement before saving"
      : "Text layout review appears for the stress edit; no overflow acknowledgement was needed",
  );
  await page
    .getByRole("button", { name: "Insert authored slide", exact: true })
    .click();
  let insertDialog = page.getByRole("dialog", {
    name: "Insert after slide 1",
    exact: true,
  });
  await insertDialog
    .getByLabel("Inserted slide title", { exact: true })
    .fill("A new authored decision");
  await insertDialog
    .getByLabel("Inserted slide points", { exact: true })
    .fill("Approve the measured pilot\nReview the outcome with the team");
  await insertDialog
    .getByLabel("Inserted slide notes", { exact: true })
    .fill("Ask for explicit approval.");
  await insertDialog
    .getByLabel("Inserted slide template", { exact: true })
    .selectOption("paper");
  await insertDialog
    .getByLabel("Inserted slide layout", { exact: true })
    .selectOption("columns");
  await insertDialog
    .getByRole("button", { name: "Preview authored slide", exact: true })
    .click();
  await insertDialog
    .getByRole("img", { name: "Proposed authored slide", exact: true })
    .waitFor();
  assert.equal(
    await insertDialog
      .getByRole("button", { name: "Save inserted slide", exact: true })
      .isDisabled(),
    true,
  );
  await noOverflow("Authored slide insertion preview");
  assert.equal(
    await insertDialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 2,
    ),
    true,
    "Insertion dialog has no horizontal overflow",
  );
  await shot("workspace-authored-slide-preview");
  await insertDialog
    .getByRole("button", { name: "Discard / close", exact: true })
    .click();
  await insertDialog.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 21", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Insert authored slide", exact: true })
    .click();
  insertDialog = page.getByRole("dialog", {
    name: "Insert after slide 1",
    exact: true,
  });
  assert.equal(
    await insertDialog
      .getByLabel("Inserted slide title", { exact: true })
      .inputValue(),
    "",
  );
  await insertDialog
    .getByLabel("Inserted slide title", { exact: true })
    .fill("A new authored decision");
  await insertDialog
    .getByLabel("Inserted slide points", { exact: true })
    .fill("Approve the measured pilot\nReview the outcome with the team");
  await insertDialog
    .getByLabel("Inserted slide notes", { exact: true })
    .fill("Ask for explicit approval.");
  await insertDialog
    .getByLabel("Inserted slide template", { exact: true })
    .selectOption("paper");
  await insertDialog
    .getByLabel("Inserted slide layout", { exact: true })
    .selectOption("columns");
  await insertDialog
    .getByRole("button", { name: "Preview authored slide", exact: true })
    .click();
  await insertDialog
    .getByRole("img", { name: "Proposed authored slide", exact: true })
    .waitFor();
  await insertDialog
    .getByRole("checkbox", {
      name: "I reviewed this slide and its notes.",
      exact: true,
    })
    .check();
  await insertDialog
    .getByText("Edit authored slide content", { exact: true })
    .click();
  await insertDialog
    .getByLabel("Inserted slide notes", { exact: true })
    .fill("Ask for explicit approval and explain the tradeoffs.");
  assert.equal(
    await insertDialog
      .getByRole("button", { name: "Save inserted slide", exact: true })
      .isDisabled(),
    true,
  );
  await insertDialog
    .getByRole("button", { name: "Preview authored slide", exact: true })
    .click();
  await insertDialog
    .getByRole("img", { name: "Proposed authored slide", exact: true })
    .waitFor();
  await insertDialog
    .getByRole("checkbox", {
      name: "I reviewed this slide and its notes.",
      exact: true,
    })
    .check();
  await insertDialog
    .getByRole("button", { name: "Save inserted slide", exact: true })
    .click();
  await insertDialog.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 22", { exact: true }).waitFor();
  await page
    .getByRole("heading", {
      name: "presentation.pptx · 24 slides",
      exact: true,
    })
    .waitFor();
  await studioPanel("Text");
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .selectOption({ label: "Slide title: A new authored decision" });
  await studioPanel("Notes");
  assert.equal(
    await page
      .getByRole("textbox", { name: "Speaker notes", exact: true })
      .inputValue(),
    "Ask for explicit approval and explain the tradeoffs.",
  );
  await shot("workspace-authored-slide-saved");
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 21", { exact: true }).waitFor();
  checks.push(
    "Authored insertion previews native content, discards without a revision, invalidates changed drafts, commits reviewed text/notes as one revision, and undoes the inserted slide",
  );
  const deckHashAfterPreview = await page.evaluate(async () => {
    const projects = await window.presenterCopilot.core.request(
      "project.list",
      {},
    );
    if (!projects.ok) throw new Error("Could not list test projects.");
    const project = projects.result.projects.find(
      (item) => item.name === "Quarterly strategy review",
    );
    if (!project) throw new Error("Could not find test project.");
    const sources = await window.presenterCopilot.core.request("source.list", {
      project_id: project.id,
    });
    if (!sources.ok) throw new Error("Could not list test sources.");
    return sources.result.sources.find(
      (item) => item.original_name === "presentation.pptx",
    )?.sha256;
  });
  assert.equal(deckHashAfterPreview, deckHashBeforePreview);
  await page.waitForFunction(
    () => {
      const emptyState = document.querySelector(".pw-canvas-empty");
      const image = document.querySelector(".pw-canvas > img");
      return !emptyState && image?.complete && image.naturalWidth > 0;
    },
    undefined,
    { timeout: 30_000 },
  );
  await shot("08-presentation-workspace-preview");
  checks.push(
    "Presentation Workspace tracks the original revision, inventories stable PPTX structure, renders a preview, captures transient intent, and keeps mock edits out of the source snapshot",
  );
  await noOverflow("Presentation Workspace");
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill("Other workspace project");
  await page.keyboard.press("Enter");
  await page
    .getByText(
      "Project created. Add your presentation or supporting material to get started.",
      { exact: true },
    )
    .waitFor();
  await page.getByText("LOCAL ONLY · 0 SOURCES", { exact: true }).waitFor();
  await navigate("Workspace");
  await page
    .getByRole("heading", {
      name: "Start your next presentation",
      exact: true,
    })
    .waitFor();
  assert.equal(
    await page
      .getByRole("img", { name: /Imported presentation, slide/ })
      .count(),
    0,
  );
  checks.push(
    "Switching projects clears the previous deck preview and reader state",
  );
  await page
    .getByRole("button", { name: "New presentation", exact: true })
    .click();
  const createDialog = page.getByRole("dialog", {
    name: "Start with your outline",
    exact: true,
  });
  await createDialog
    .getByLabel("Presentation title", { exact: true })
    .fill("A new decision deck");
  await createDialog
    .getByLabel("Slide outline", { exact: true })
    .fill(
      "# Recommendation\n- Approve the pilot\n- Review results in thirty days\nNotes: Ask for a decision\n\n# Evidence\n- Insert verified figures before presenting",
    );
  await createDialog
    .getByRole("button", { name: "Review outline", exact: true })
    .click();
  await createDialog
    .getByText("2 slides ready to create", { exact: true })
    .waitFor();
  await createDialog.getByText("Edit slide 1 content", { exact: true }).click();
  await createDialog
    .getByLabel("Reviewed slide 1 points", { exact: true })
    .fill("Approve a measured pilot\nReview results in thirty days");
  await createDialog
    .getByRole("button", { name: "Add draft slide", exact: true })
    .click();
  await createDialog
    .getByText("3 slides ready to create", { exact: true })
    .waitFor();
  await createDialog.getByText("Edit slide 3 content", { exact: true }).click();
  await createDialog
    .getByLabel("Reviewed slide 3 title", { exact: true })
    .fill("Draft appendix");
  await createDialog
    .getByLabel("Reviewed slide 3 points", { exact: true })
    .fill("A".repeat(201));
  assert.equal(
    await createDialog
      .getByRole("button", { name: "Create presentation", exact: true })
      .isDisabled(),
    true,
  );
  await createDialog
    .getByLabel("Reviewed slide 3 points", { exact: true })
    .fill("Supporting detail\nA second detail");
  await createDialog
    .getByRole("button", { name: "Move slide 3 earlier", exact: true })
    .click();
  await createDialog
    .getByRole("button", { name: "Duplicate draft slide 2", exact: true })
    .click();
  await createDialog
    .getByText("4 slides ready to create", { exact: true })
    .waitFor();
  await createDialog
    .getByRole("button", { name: "Remove draft slide 3", exact: true })
    .click();
  await createDialog
    .getByRole("button", { name: "Remove draft slide 2", exact: true })
    .click();
  await createDialog
    .getByText("2 slides ready to create", { exact: true })
    .waitFor();
  await createDialog
    .getByRole("button", { name: "Edit outline", exact: true })
    .click();
  assert.ok(
    (
      await createDialog
        .getByLabel("Slide outline", { exact: true })
        .inputValue()
    ).includes("Notes: Ask for a decision"),
  );
  await createDialog
    .getByRole("button", { name: "Review outline", exact: true })
    .click();
  checks.push(
    "Outline review supports bounded content editing, authored slides, reordering, duplication, removal, and returning to the updated outline",
  );
  await createDialog
    .getByLabel("Presentation template", { exact: true })
    .selectOption("midnight");
  await createDialog
    .getByLabel("Slide 1 layout", { exact: true })
    .selectOption("cards");
  await createDialog
    .getByLabel("Slide 2 layout", { exact: true })
    .selectOption("statement");
  await noOverflow("Native template review");
  await shot("workspace-create-outline-review");
  await createDialog
    .getByRole("button", { name: "Create presentation", exact: true })
    .click();
  await createDialog.waitFor({ state: "detached" });
  await page
    .getByRole("img", { name: "Imported presentation, slide 1", exact: true })
    .waitFor();
  await page.getByText("Slide 1 of 2", { exact: true }).waitFor();
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  await studioPanel("Text");
  assert.ok(
    (
      await page
        .getByRole("combobox", { name: "Text on this slide", exact: true })
        .innerText()
    ).includes("Approve a measured pilot"),
  );
  await shot("workspace-created-native-deck");
  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Notes", exact: true })
    .click();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Speaker notes", exact: true })
      .inputValue(),
    "Ask for a decision",
  );
  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Text", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .selectOption({ label: "Slide title: Recommendation" });
  await page
    .getByRole("textbox", { name: "Replacement text", exact: true })
    .fill("Approve the pilot");
  await page
    .getByRole("button", { name: "Preview replacement", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Save revision", exact: true })
    .click();
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  checks.push(
    "Reviewed Midnight template with cards and statement layouts creates native slides with notes and supports normal revision editing",
  );
  await page.getByRole("button", { name: "Rehearse", exact: true }).click();
  await page
    .getByText(/Rehearsal target: A new decision deck.*Revision 2/)
    .waitFor();
  await page
    .getByLabel("Presentation tracking", { exact: true })
    .selectOption("manual");
  await page.getByRole("button", { name: "Start Run", exact: true }).click();
  await page
    .getByLabel("Optional marker note", { exact: true })
    .fill("Ask which outcome would justify expanding the pilot.");
  await page
    .getByRole("button", { name: "Mark weak point", exact: true })
    .click();
  await page
    .getByLabel("Optional marker note", { exact: true })
    .fill("Confirm the decision owner before presenting.");
  await page
    .getByRole("button", { name: "Mark question", exact: true })
    .click();
  await page.getByRole("button", { name: "Stop Run", exact: true }).click();
  await page
    .getByRole("heading", { name: "Run debrief", exact: true })
    .waitFor();
  await navigate("Workspace");
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  await studioPanel("Rehearsal");
  const findings = page.getByRole("region", {
    name: "Rehearsal findings",
    exact: true,
  });
  const questionFinding = findings
    .locator("article")
    .filter({ hasText: "Confirm the decision owner before presenting." });
  await questionFinding
    .getByRole("button", { name: "Dismiss finding", exact: true })
    .click();
  await questionFinding
    .getByText("Dismissed by you.", { exact: true })
    .waitFor();
  await questionFinding
    .getByRole("button", { name: "Undo dismissal", exact: true })
    .click();
  await questionFinding
    .getByRole("button", { name: "Dismiss finding", exact: true })
    .waitFor();
  await shot("workspace-rehearsal-findings");
  const weakFinding = findings.locator("article").filter({
    hasText: "Ask which outcome would justify expanding the pilot.",
  });
  await weakFinding
    .getByRole("button", { name: "Add to notes draft", exact: true })
    .click();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Speaker notes", exact: true })
      .inputValue(),
    "Ask for a decision\n\nAsk which outcome would justify expanding the pilot.",
  );
  await shot("workspace-rehearsal-notes-draft");
  await page
    .getByRole("button", { name: "Save speaker notes", exact: true })
    .click();
  await page.getByText("Current · Revision 3", { exact: true }).waitFor();
  await studioPanel("Rehearsal");
  await weakFinding
    .getByText("Applied in a saved revision. Rehearse again to compare.", {
      exact: true,
    })
    .waitFor();
  await shot("workspace-rehearsal-applied");
  await page.getByRole("button", { name: "Rehearse", exact: true }).click();
  await page
    .getByText(/Rehearsal target: A new decision deck.*Revision 3/)
    .waitFor();
  await page
    .getByLabel("Presentation tracking", { exact: true })
    .selectOption("manual");
  await page.getByRole("button", { name: "Start Run", exact: true }).click();
  await page
    .getByLabel("Optional marker note", { exact: true })
    .fill("Second rehearsal observation.");
  await page
    .getByRole("button", { name: "Mark weak point", exact: true })
    .click();
  await page.getByRole("button", { name: "Stop Run", exact: true }).click();
  await page
    .getByRole("heading", { name: "Run debrief", exact: true })
    .waitFor();
  await navigate("Workspace");
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page.getByText("Current · Revision 3", { exact: true }).waitFor();
  await studioPanel("Rehearsal");
  const comparisonPanel = page.getByRole("region", {
    name: "Compare rehearsals",
    exact: true,
  });
  await comparisonPanel
    .getByRole("button", { name: "Compare recorded rehearsals", exact: true })
    .click();
  const totals = comparisonPanel.getByRole("table", {
    name: "Rehearsal totals",
    exact: true,
  });
  await totals.waitFor();
  assert.equal(
    await totals.evaluate((table) => table.scrollWidth > table.clientWidth + 1),
    false,
    "Comparison totals fit the inspector width",
  );
  assert.deepEqual(
    await totals
      .getByRole("row")
      .filter({ hasText: "Your markers" })
      .getByRole("cell")
      .allTextContents(),
    ["2", "1", "-1"],
  );
  await comparisonPanel.locator("summary").first().click();
  await comparisonPanel
    .getByRole("button", { name: "Open current slide 1", exact: true })
    .waitFor();
  await shot("workspace-rehearsal-comparison");
  await comparisonPanel
    .getByRole("button", { name: "Open current slide 1", exact: true })
    .click();
  checks.push(
    "Two GUI rehearsals compare recorded marker deltas across revisions and navigate to the current stable slide without editing the deck",
  );
  checks.push(
    "Workspace rehearses the selected revision and turns a marker into reviewed notes with persistent provenance and reversible dismissal",
  );
  await page
    .getByRole("button", { name: "New presentation", exact: true })
    .click();
  const plannedDialog = page.getByRole("dialog", {
    name: "Start with your outline",
    exact: true,
  });
  await plannedDialog
    .getByRole("button", { name: "Plan with Copilot", exact: true })
    .click();
  await plannedDialog
    .getByLabel("Presentation objective", { exact: true })
    .fill("Approve a measured pilot");
  await plannedDialog
    .getByLabel("Audience for this presentation", { exact: true })
    .fill("Leadership team");
  await plannedDialog.getByLabel("Number of slides", { exact: true }).fill("3");
  await holdVoice(plannedDialog.getByLabel("Your briefing", { exact: true }));
  await plannedDialog
    .getByRole("button", { name: "Stop and review request", exact: true })
    .waitFor();
  await releaseVoice();
  await plannedDialog
    .getByLabel("Reviewed outline transcript", { exact: true })
    .waitFor();
  assert.equal(
    await plannedDialog
      .getByLabel("Your briefing", { exact: true })
      .inputValue(),
    "",
  );
  await plannedDialog
    .getByRole("button", { name: "Discard outline dictation", exact: true })
    .click();
  await plannedDialog
    .getByRole("button", { name: "Dictate briefing", exact: true })
    .waitFor();
  checks.push(
    "Outline briefing holds from its dialog field, reviews on release, leaves the briefing unchanged until explicit use and discards without proposing an outline",
  );
  await plannedDialog
    .getByRole("button", { name: "Dictate briefing", exact: true })
    .click();
  await plannedDialog
    .getByRole("button", { name: "Stop and review request", exact: true })
    .waitFor();
  assert.equal(
    await plannedDialog
      .getByRole("button", { name: "Propose outline", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(
    await plannedDialog
      .getByRole("button", { name: "Write outline", exact: true })
      .isDisabled(),
    true,
  );
  await plannedDialog
    .getByRole("button", { name: "Discard outline dictation", exact: true })
    .click();
  await plannedDialog
    .getByRole("button", { name: "Dictate briefing", exact: true })
    .click();
  await plannedDialog
    .getByRole("button", { name: "Stop and review request", exact: true })
    .click();
  assert.equal(
    await plannedDialog
      .getByLabel("Your briefing", { exact: true })
      .inputValue(),
    "",
  );
  await plannedDialog
    .getByLabel("Reviewed outline transcript", { exact: true })
    .fill("x".repeat(2001));
  assert.equal(
    await plannedDialog
      .getByRole("button", { name: "Use reviewed briefing", exact: true })
      .isDisabled(),
    true,
  );
  await plannedDialog
    .getByLabel("Reviewed outline transcript", { exact: true })
    .fill(
      "Explain the decision, review the available evidence, and leave unresolved figures for review.",
    );
  await shot("workspace-voice-outline-briefing");
  await plannedDialog
    .getByRole("button", { name: "Use reviewed briefing", exact: true })
    .click();
  assert.equal(
    await plannedDialog
      .getByLabel("Your briefing", { exact: true })
      .inputValue(),
    "Explain the decision, review the available evidence, and leave unresolved figures for review.",
  );
  await plannedDialog
    .getByRole("button", { name: "Propose outline", exact: true })
    .click();
  await plannedDialog
    .getByText("Draft for your review", { exact: true })
    .waitFor();
  await shot("workspace-conversation-outline");
  const draftHistory = plannedDialog.locator(".pw-outline-conversation");
  assert.equal(
    await draftHistory
      .getByRole("button", { name: "Restore draft 1", exact: true })
      .getAttribute("aria-pressed"),
    "true",
  );
  const conversationDeckCount = await page
    .getByRole("combobox", { name: "Presentation", exact: true })
    .locator("option")
    .count();
  await plannedDialog
    .getByLabel("Draft presentation title", { exact: true })
    .fill("Reviewed baseline pilot");
  await plannedDialog
    .getByLabel("Slide 1 points", { exact: true })
    .fill("Retain the reviewed baseline wording");
  await plannedDialog
    .getByRole("button", { name: "Dictate refinement", exact: true })
    .click();
  await plannedDialog
    .getByRole("button", { name: "Stop and review request", exact: true })
    .click();
  await plannedDialog
    .getByLabel("Reviewed outline transcript", { exact: true })
    .fill("x".repeat(501));
  assert.equal(
    await plannedDialog
      .getByRole("button", { name: "Use reviewed refinement", exact: true })
      .isDisabled(),
    true,
  );
  await plannedDialog
    .getByLabel("Reviewed outline transcript", { exact: true })
    .fill("Put the decision first and keep the pilot measurable.");
  await plannedDialog
    .getByRole("button", { name: "Use reviewed refinement", exact: true })
    .click();
  assert.equal(
    await plannedDialog
      .getByLabel("Refine this draft", { exact: true })
      .inputValue(),
    "Put the decision first and keep the pilot measurable.",
  );
  checks.push(
    "Outline dictation owns local project capture before a deck exists, cancels cleanly, locks proposal/mode controls, reviews briefing and refinement transcripts, and requires separate provider actions",
  );
  await plannedDialog
    .getByRole("button", { name: "Refine outline", exact: true })
    .click();
  await plannedDialog
    .getByRole("button", { name: "Refine outline", exact: true })
    .waitFor();
  await draftHistory
    .getByRole("button", { name: "Restore draft 2", exact: true })
    .waitFor();
  const outlineChanges = plannedDialog.locator(".pw-outline-changes");
  await outlineChanges.locator("summary").click();
  assert.match(await outlineChanges.innerText(), /Reviewed baseline pilot/);
  assert.match(
    await outlineChanges.innerText(),
    /Retain the reviewed baseline wording/,
  );
  await plannedDialog
    .getByLabel("Draft presentation title", { exact: true })
    .fill("Reviewed refined pilot");
  await plannedDialog
    .getByLabel("Slide 1 points", { exact: true })
    .fill("x".repeat(201));
  await plannedDialog
    .getByLabel("Refine this draft", { exact: true })
    .fill("Refine this invalid point for the failure-retention check.");
  await plannedDialog
    .getByRole("button", { name: "Refine outline", exact: true })
    .click();
  await plannedDialog.locator('.pw-outline-planner [role="alert"]').waitFor();
  assert.equal(await draftHistory.getByRole("button").count(), 2);
  assert.equal(
    await plannedDialog
      .getByLabel("Slide 1 points", { exact: true })
      .inputValue(),
    "x".repeat(201),
  );
  assert.equal(
    await plannedDialog
      .getByLabel("Draft presentation title", { exact: true })
      .inputValue(),
    "Reviewed refined pilot",
  );
  await plannedDialog
    .getByLabel("Slide 1 points", { exact: true })
    .fill("Reviewed refined decision");
  await holdVoice(
    plannedDialog.getByLabel("Refine this draft", { exact: true }),
  );
  await plannedDialog
    .getByRole("button", { name: "Stop and review request", exact: true })
    .waitFor();
  assert.equal(
    await draftHistory
      .getByRole("button", { name: "Restore draft 1", exact: true })
      .isDisabled(),
    true,
  );
  await page.keyboard.press("Escape");
  await releaseVoice();
  await plannedDialog
    .getByRole("button", { name: "Dictate refinement", exact: true })
    .waitFor();
  assert.equal(
    await draftHistory
      .getByRole("button", { name: "Restore draft 1", exact: true })
      .isEnabled(),
    true,
  );
  await draftHistory
    .getByRole("button", { name: "Restore draft 1", exact: true })
    .click();
  assert.equal(
    await plannedDialog
      .getByLabel("Draft presentation title", { exact: true })
      .inputValue(),
    "Reviewed baseline pilot",
  );
  assert.equal(
    await plannedDialog
      .getByLabel("Slide 1 points", { exact: true })
      .inputValue(),
    "Retain the reviewed baseline wording",
  );
  assert.equal(
    await plannedDialog
      .getByLabel("Refine this draft", { exact: true })
      .inputValue(),
    "",
  );
  await plannedDialog.locator(".pw-planner-brief summary").click();
  assert.equal(
    await plannedDialog
      .getByLabel("Your briefing", { exact: true })
      .inputValue(),
    "Explain the decision, review the available evidence, and leave unresolved figures for review.",
  );
  await plannedDialog
    .getByLabel("Audience for this presentation", { exact: true })
    .fill("Branch audience");
  await plannedDialog
    .getByLabel("Refine this draft", { exact: true })
    .fill("Explore another opening from the reviewed baseline.");
  await plannedDialog
    .getByRole("button", { name: "Refine outline", exact: true })
    .click();
  await draftHistory
    .getByRole("button", { name: "Restore draft 3", exact: true })
    .waitFor();
  assert.match(
    await draftHistory.innerText(),
    /Refined draft 1: Explore another opening/,
  );
  if (!(await outlineChanges.evaluate((element) => element.open)))
    await outlineChanges.locator("summary").click();
  assert.match(await outlineChanges.innerText(), /Reviewed baseline pilot/);
  await draftHistory
    .getByRole("button", { name: "Restore draft 2", exact: true })
    .click();
  assert.equal(
    await plannedDialog
      .getByLabel("Draft presentation title", { exact: true })
      .inputValue(),
    "Reviewed refined pilot",
  );
  assert.equal(
    await plannedDialog
      .getByLabel("Audience for this presentation", { exact: true })
      .inputValue(),
    "Leadership team",
  );
  assert.equal(
    await page
      .getByRole("combobox", { name: "Presentation", exact: true })
      .locator("option")
      .count(),
    conversationDeckCount,
  );
  await shot("workspace-outline-conversation-restored");
  checks.push(
    "Outline conversation retains manually edited ancestors and independent branches, compares the exact request baseline, restores briefing context without provider calls, and creates no deck before explicit review",
  );
  await plannedDialog
    .getByLabel("Draft presentation title", { exact: true })
    .fill("Evidence-led pilot proposal");
  await plannedDialog
    .getByLabel("Slide 1 title", { exact: true })
    .fill("The decision we need");
  await plannedDialog
    .getByLabel("Slide 1 points", { exact: true })
    .fill("Approve a measured pilot\nConfirm the decision owner");
  await plannedDialog
    .getByRole("button", { name: "Review this outline", exact: true })
    .click();
  await plannedDialog
    .getByText("3 slides ready to create", { exact: true })
    .waitFor();
  await plannedDialog
    .getByLabel("Presentation title", { exact: true })
    .fill("Reviewed pilot proposal");
  await plannedDialog
    .getByText("3 slides ready to create", { exact: true })
    .waitFor();
  await shot("workspace-conversation-review");
  await plannedDialog
    .getByRole("button", { name: "Create presentation", exact: true })
    .click();
  await plannedDialog.waitFor({ state: "detached" });
  await page.getByText("Slide 1 of 3", { exact: true }).waitFor();
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  await studioPanel("Text");
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .selectOption({ label: "Slide title: The decision we need" });
  assert.equal(
    await page
      .getByRole("textbox", { name: "Replacement text", exact: true })
      .inputValue(),
    "The decision we need",
  );
  await shot("workspace-conversation-native-deck");
  checks.push(
    "Conversational planning proposes and refines a review-only outline, allows user edits, and creates an editable native deck after review",
  );
  await page
    .getByRole("button", { name: "Edit slide together", exact: true })
    .click();
  const groupedReview = page.getByRole("dialog", {
    name: "Review slide edits",
    exact: true,
  });
  await groupedReview
    .getByLabel("Slide text 1", { exact: true })
    .fill("A decision for the team");
  await groupedReview
    .getByLabel("Grouped speaker notes", { exact: true })
    .fill("Explain the tradeoffs and ask for an explicit decision.");
  await groupedReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await groupedReview
    .getByRole("img", {
      name: "Proposed slide with all reviewed text changes",
      exact: true,
    })
    .waitFor();
  assert.equal(
    await groupedReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isDisabled(),
    true,
  );
  await shot("workspace-grouped-edit-preview");
  await groupedReview
    .getByRole("button", { name: "Discard preview", exact: true })
    .click();
  await groupedReview.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Replacement text", exact: true })
      .inputValue(),
    "The decision we need",
  );
  await page
    .getByRole("button", { name: "Edit slide together", exact: true })
    .click();
  await groupedReview
    .getByLabel("Slide text 1", { exact: true })
    .fill("A decision for the team");
  await groupedReview
    .getByLabel("Slide text 2", { exact: true })
    .fill("Review the tradeoffs");
  await groupedReview
    .getByLabel("Grouped speaker notes", { exact: true })
    .fill("Explain the tradeoffs and ask for an explicit decision.");
  await groupedReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await groupedReview
    .getByRole("img", {
      name: "Proposed slide with all reviewed text changes",
      exact: true,
    })
    .waitFor();
  await groupedReview.getByRole("checkbox").check();
  await groupedReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await groupedReview.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 2", { exact: true }).waitFor();
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .selectOption({ label: "Slide title: A decision for the team" });
  assert.equal(
    await page
      .getByRole("textbox", { name: "Replacement text", exact: true })
      .inputValue(),
    "A decision for the team",
  );
  await studioPanel("Notes");
  assert.equal(
    await page
      .getByRole("textbox", { name: "Speaker notes", exact: true })
      .inputValue(),
    "Explain the tradeoffs and ask for an explicit decision.",
  );
  await shot("workspace-grouped-edit-applied");
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Speaker notes", exact: true })
      .inputValue()
      .then((value) =>
        value.includes(
          "Explain the tradeoffs and ask for an explicit decision.",
        ),
      ),
    false,
  );
  await studioPanel("Text");
  checks.push(
    "A real native package previews multiple text and notes edits without mutation, discards safely, saves the exact reviewed package as one revision, and undoes all edits together",
  );
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  const editPlan = page.getByRole("dialog", {
    name: "Copilot edit plan",
    exact: true,
  });
  await editPlan
    .getByLabel("Copilot edit scope", { exact: true })
    .selectOption("deck");
  const voiceWindowBounds = await app.evaluate(({ BrowserWindow }) => {
    const main = BrowserWindow.getAllWindows().find((candidate) =>
      candidate.webContents.getURL().endsWith("/renderer/index.html"),
    );
    const bounds = main.getBounds();
    main.setSize(720, 520);
    return bounds;
  });
  await holdVoice(editPlan.getByLabel("Copilot edit request", { exact: true }));
  await editPlan
    .getByRole("button", { name: "Stop and review request", exact: true })
    .waitFor();
  await page.waitForFunction(() => {
    const status = document.querySelector('.pw-voice-edit [role="status"]');
    const bounds = status?.getBoundingClientRect();
    return bounds && bounds.top >= 0 && bounds.bottom <= window.innerHeight;
  });
  await shot("workspace-hold-small-listening");
  assert.equal(
    await editPlan
      .getByLabel("Copilot edit scope", { exact: true })
      .isDisabled(),
    true,
  );
  await app.evaluate(async ({ BrowserWindow }) => {
    const focusFixture = new BrowserWindow({
      width: 240,
      height: 140,
      title: "Gesture focus fixture",
      webPreferences: { nodeIntegration: false, contextIsolation: true },
    });
    await focusFixture.loadURL("about:blank");
    focusFixture.setTitle("Gesture focus fixture");
    focusFixture.show();
    focusFixture.focus();
  });
  await page.waitForFunction(() => !document.hasFocus());
  assert.equal(
    await app.evaluate(
      ({ BrowserWindow }) =>
        BrowserWindow.getFocusedWindow()?.getTitle() ===
        "Gesture focus fixture",
    ),
    true,
  );
  await editPlan
    .getByRole("button", { name: "Dictate Copilot request", exact: true })
    .waitFor();
  await releaseVoice();
  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()
      .find((candidate) => candidate.getTitle() === "Gesture focus fixture")
      ?.destroy();
  });
  assert.equal(
    await editPlan
      .getByLabel("Reviewed Copilot transcript", { exact: true })
      .count(),
    0,
  );
  await holdVoice(editPlan.getByLabel("Copilot edit request", { exact: true }));
  await editPlan
    .getByRole("button", { name: "Stop and review request", exact: true })
    .waitFor();
  await page.keyboard.up("Shift");
  await editPlan
    .getByLabel("Reviewed Copilot transcript", { exact: true })
    .waitFor();
  await page.keyboard.down("Space");
  assert.equal(
    await editPlan
      .getByLabel("Reviewed Copilot transcript", { exact: true })
      .inputValue(),
    "",
  );
  await releaseVoice();
  await page.waitForFunction(() => {
    const field = document.querySelector(".pw-voice-edit textarea");
    const bounds = field?.getBoundingClientRect();
    return (
      field === document.activeElement &&
      bounds &&
      bounds.top >= 0 &&
      bounds.bottom <= window.innerHeight
    );
  });
  await shot("workspace-hold-small-review");
  await noOverflow("Copilot hold review at minimum window");
  await editPlan
    .getByRole("button", { name: "Discard voice request", exact: true })
    .click();
  await editPlan
    .getByRole("button", { name: "Dictate Copilot request", exact: true })
    .waitFor();
  checks.push(
    "Copilot hold gesture starts from the dialog request field, locks deck scope, cancels on actual Electron window blur and reviews on release without proposing changes",
  );
  await app.evaluate(({ BrowserWindow }, bounds) => {
    BrowserWindow.getAllWindows()
      .find((candidate) =>
        candidate.webContents.getURL().endsWith("/renderer/index.html"),
      )
      ?.setBounds(bounds);
  }, voiceWindowBounds);
  checks.push(
    "At 720x520 the hold gesture brings listening feedback and the focused transcript into view without horizontal overflow",
  );
  await editPlan
    .getByRole("button", { name: "Dictate Copilot request", exact: true })
    .click();
  await editPlan
    .getByRole("button", { name: "Stop and review request", exact: true })
    .waitFor();
  assert.equal(
    await editPlan
      .getByLabel("Copilot edit scope", { exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(
    await editPlan
      .getByRole("button", { name: "Propose changes", exact: true })
      .isDisabled(),
    true,
  );
  await editPlan
    .getByRole("button", { name: "Discard voice request", exact: true })
    .click();
  await editPlan
    .getByRole("button", { name: "Dictate Copilot request", exact: true })
    .waitFor();
  await editPlan
    .getByLabel("Copilot edit scope", { exact: true })
    .selectOption("slide");
  await editPlan
    .getByRole("button", { name: "Dictate Copilot request", exact: true })
    .click();
  await editPlan
    .getByRole("button", { name: "Stop and review request", exact: true })
    .click();
  await editPlan
    .getByLabel("Reviewed Copilot transcript", { exact: true })
    .waitFor();
  assert.equal(
    await editPlan
      .getByRole("button", {
        name: "Use reviewed Copilot request",
        exact: true,
      })
      .isDisabled(),
    true,
  );
  await editPlan
    .getByLabel("Reviewed Copilot transcript", { exact: true })
    .fill("A".repeat(501));
  assert.equal(
    await editPlan
      .getByRole("button", {
        name: "Use reviewed Copilot request",
        exact: true,
      })
      .isDisabled(),
    true,
  );
  await editPlan
    .getByLabel("Reviewed Copilot transcript", { exact: true })
    .fill("Clarify the decision and add a speaking reminder.");
  await shot("workspace-voice-edit-plan-transcript");
  await editPlan
    .getByRole("button", { name: "Use reviewed Copilot request", exact: true })
    .click();
  assert.equal(
    await editPlan
      .getByLabel("Copilot edit request", { exact: true })
      .inputValue(),
    "Clarify the decision and add a speaking reminder.",
  );
  checks.push(
    "General voice edit requests own local capture, lock target scope, cancel cleanly, review/correct an empty fixture transcript, enforce instruction length, and require explicit use before provider proposal",
  );
  await editPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Clarify the decision and add a speaking reminder.");
  await editPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await editPlan
    .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
    .waitFor();
  await editPlan
    .getByText("Viewed 1 of 1 affected slides.", { exact: true })
    .waitFor();
  assert.equal(
    await editPlan
      .getByRole("button", { name: "Save Copilot changes", exact: true })
      .isDisabled(),
    true,
  );
  await shot("workspace-copilot-edit-plan");
  await editPlan.getByText("Edit your request", { exact: true }).click();
  await editPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Clarify the decision and keep a brief speaking reminder.");
  await editPlan
    .getByText(
      "Your request changed. Propose the revised request before saving.",
      { exact: true },
    )
    .waitFor();
  assert.equal(await editPlan.getByRole("checkbox").isDisabled(), true);
  await editPlan
    .getByRole("button", { name: "Propose revised request", exact: true })
    .click();
  await editPlan
    .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
    .waitFor();
  await editPlan.getByRole("checkbox").check();
  await editPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await editPlan.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 3", { exact: true }).waitFor();
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .selectOption({ label: "Slide title: The decision we need — reviewed" });
  await studioPanel("Notes");
  assert.equal(
    (
      await page
        .getByRole("textbox", { name: "Speaker notes", exact: true })
        .inputValue()
    ).includes("Review the decision with the audience."),
    true,
  );
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  await shot("workspace-copilot-edit-undone");
  checks.push(
    "Copilot produces a revision-bound multi-operation proposal, renders the actual native package, requires review, invalidates approval when the request changes, supports reproposal, saves one revision, and undoes the entire plan",
  );
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await editPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Add a concise speaking reminder across the presentation.");
  await editPlan
    .getByLabel("Copilot edit scope", { exact: true })
    .selectOption("deck");
  await editPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await editPlan
    .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
    .waitFor();
  await editPlan
    .getByText("Viewed 1 of 3 affected slides.", { exact: true })
    .waitFor();
  assert.equal(await editPlan.getByRole("checkbox").isDisabled(), true);
  await editPlan
    .getByLabel("Proposed slide to review", { exact: true })
    .selectOption("2");
  await editPlan
    .getByRole("img", { name: "Copilot proposed slide 2", exact: true })
    .waitFor();
  assert.equal(await editPlan.getByRole("checkbox").isDisabled(), true);
  await editPlan
    .getByLabel("Proposed slide to review", { exact: true })
    .selectOption("3");
  await editPlan
    .getByRole("img", { name: "Copilot proposed slide 3", exact: true })
    .waitFor();
  await editPlan
    .getByText("Viewed 3 of 3 affected slides.", { exact: true })
    .waitFor();
  assert.equal(await editPlan.getByRole("checkbox").isEnabled(), true);
  await shot("workspace-copilot-deck-review");
  await editPlan
    .getByRole("button", { name: "Discard Copilot proposal", exact: true })
    .click();
  await editPlan.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  checks.push(
    "A whole-presentation Copilot proposal requires viewing every affected slide before approval and discards without changing the baseline revision",
  );
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await editPlan
    .getByLabel("Copilot edit scope", { exact: true })
    .selectOption("slide");
  await editPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Add a styled callout using a coordinated creation plan.");
  await editPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await editPlan
    .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
    .waitFor();
  await editPlan
    .getByText("Approve the measured pilot", { exact: true })
    .first()
    .waitFor();
  await editPlan.getByText(/^Format text ·/).waitFor();
  await editPlan.getByText(/^Move or resize an object ·/).waitFor();
  await editPlan
    .getByText("Viewed 1 of 1 affected slides.", { exact: true })
    .waitFor();
  await shot("workspace-copilot-created-callout");
  console.log(
    "Callout image layout",
    await editPlan
      .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
      .evaluate((img) => {
        const style = window.getComputedStyle(img);
        return {
          width: img.width,
          height: img.height,
          naturalWidth: img.naturalWidth,
          naturalHeight: img.naturalHeight,
          objectFit: style.objectFit,
          objectPosition: style.objectPosition,
          maxHeight: style.maxHeight,
          rect: img.getBoundingClientRect().toJSON(),
        };
      }),
  );
  const calloutPixels = await editPlan
    .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
    .evaluate((img) => {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.getContext("2d").drawImage(img, 0, 0);
      return canvas.toDataURL("image/png").split(",")[1];
    });
  await writeFile(
    path.join(output, "workspace-copilot-created-callout-native.png"),
    Buffer.from(calloutPixels, "base64"),
  );
  console.log(
    "Callout preview framing",
    await app.evaluate(async ({ BrowserWindow }) => {
      const child = BrowserWindow.getAllWindows().find((candidate) =>
        candidate.webContents.getURL().includes("/presentation-preview/"),
      );
      return child
        ? {
            bounds: child.getContentBounds(),
            zoom: child.webContents.getZoomFactor(),
            renderer: await child.webContents.executeJavaScript(
              "JSON.stringify({width: innerWidth, height: innerHeight, dpr: devicePixelRatio, stage: document.getElementById('stage').getBoundingClientRect().toJSON()})",
            ),
          }
        : null;
    }),
  );
  await editPlan.getByRole("checkbox").check();
  await editPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await editPlan.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await studioPanel("Text");
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .selectOption({ label: "Text Box: Approve the measured pilot" });
  assert.equal(
    await page
      .getByRole("button", { name: "Bold", exact: true })
      .getAttribute("aria-pressed"),
    "true",
  );
  await studioPanel("Objects");
  await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .selectOption({ label: "Text Box · sp · editable" });
  await page.getByRole("button", { name: "Send to back", exact: true }).click();
  await page.getByText("Current · Revision 5", { exact: true }).waitFor();
  await studioPanel("Objects");
  await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .locator("option")
    .filter({ hasText: "Text Box · sp · editable" })
    .waitFor({ state: "attached" });
  await page.waitForFunction(() => {
    const select = document.querySelector(
      'select[aria-label="Object to edit"]',
    );
    return select && !select.matches(":disabled");
  });
  const orderedOptions = await page
    .getByRole("combobox", { name: "Object to edit", exact: true })
    .locator("option")
    .allTextContents();
  assert.equal(
    orderedOptions[1],
    "Text Box · sp · editable",
    "The callout becomes the backmost object",
  );
  await shot("workspace-object-layer-back");
  await page.getByRole("button", { name: "Send to back", exact: true }).click();
  await page
    .getByText("The object is already at this layer boundary.", { exact: true })
    .waitFor();
  await page.getByText("Current · Revision 5", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  checks.push(
    "Direct layering saves a native order-only revision, keeps selection and object content, performs boundary no-ops without new revisions, and undoes independently of creation",
  );
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .check();
  const canvasOverlay = page.getByLabel("Select slide objects", {
    exact: true,
  });
  await canvasOverlay.waitFor();
  const calloutPick = page.getByRole("button", {
    name: "Select Text Box on slide",
    exact: true,
  });
  await calloutPick.click();
  assert.equal(await calloutPick.getAttribute("aria-pressed"), "true");
  assert.ok(
    await page
      .getByRole("combobox", { name: "Object to edit", exact: true })
      .inputValue(),
    "Canvas selection populates the inspector",
  );
  const labelPick = page.getByRole("button", {
    name: "Select Deck label on slide",
    exact: true,
  });
  await labelPick.click({ modifiers: ["Shift"] });
  assert.equal(
    await canvasOverlay.locator('rect[aria-pressed="true"]').count(),
    2,
  );
  await labelPick.click({ modifiers: ["Shift"] });
  assert.equal(
    await canvasOverlay.locator('rect[aria-pressed="true"]').count(),
    1,
  );
  await labelPick.focus();
  await labelPick.press("Shift+Space");
  assert.equal(
    await canvasOverlay.locator('rect[aria-pressed="true"]').count(),
    2,
  );
  await page
    .getByRole("button", { name: "Arrange objects together", exact: true })
    .click();
  const pickedReview = page.getByRole("dialog", {
    name: "Review object layout",
    exact: true,
  });
  assert.equal(
    await pickedReview.getByRole("checkbox", { checked: true }).count(),
    2,
    "Canvas selection seeds the reviewed layout",
  );
  await pickedReview
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await pickedReview.waitFor({ state: "detached" });
  await labelPick.focus();
  await labelPick.press("Escape");
  assert.equal(
    await canvasOverlay.locator('rect[aria-pressed="true"]').count(),
    0,
  );
  await canvasOverlay.scrollIntoViewIfNeeded();
  const canvasBox = await canvasOverlay.boundingBox();
  assert.ok(canvasBox);
  await page.mouse.move(
    canvasBox.x + canvasBox.width * 0.98,
    canvasBox.y + canvasBox.height * 0.98,
  );
  await page.mouse.down();
  await page.mouse.move(
    canvasBox.x + canvasBox.width * 0.02,
    canvasBox.y + canvasBox.height * 0.02,
    { steps: 8 },
  );
  await page.mouse.up();
  await page.waitForFunction(
    () =>
      document.querySelectorAll('.pw-object-overlay rect[aria-pressed="true"]')
        .length >= 3,
  );
  assert.ok(
    (await canvasOverlay.locator('rect[aria-pressed="true"]').count()) >= 3,
    "Reverse marquee selects intersecting editable objects",
  );
  await shot("workspace-canvas-object-selection");
  await calloutPick.click();
  await labelPick.click({ modifiers: ["Shift"] });
  await calloutPick.scrollIntoViewIfNeeded();
  const dragBox = await calloutPick.boundingBox();
  assert.ok(dragBox);
  await page.mouse.move(
    dragBox.x + dragBox.width / 2,
    dragBox.y + dragBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    dragBox.x + dragBox.width / 2 + 20,
    dragBox.y + dragBox.height / 2 + 30,
    { steps: 6 },
  );
  await page.mouse.up();
  const draggedReview = page.getByRole("dialog", {
    name: "Review dragged objects",
    exact: true,
  });
  await draggedReview.waitFor();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await draggedReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await draggedReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor({ timeout: 30_000 });
  await draggedReview
    .getByText(
      "Moved 2 objects together. Undo restores their previous positions.",
      { exact: true },
    )
    .waitFor();
  assert.equal(
    await draggedReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isEnabled(),
    false,
  );
  await draggedReview.getByRole("checkbox").check();
  await shot("workspace-canvas-drag-review");
  await draggedReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await draggedReview.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 6", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await labelPick.waitFor();
  assert.equal(
    await canvasOverlay.locator('rect[aria-pressed="true"]').count(),
    0,
    "Revision changes clear canvas selection",
  );
  checks.push(
    "Dragging two selected native objects previews snapped translation, keeps the revision unchanged until explicit review/save, commits one revision and undoes the batch",
  );

  await calloutPick.click();
  await labelPick.click({ modifiers: ["Shift"] });
  assert.equal(
    await canvasOverlay
      .getByRole("button", { name: /^Resize selection / })
      .count(),
    8,
  );
  const topLeftResize = canvasOverlay.getByRole("button", {
    name: "Resize selection top left",
    exact: true,
  });
  await topLeftResize.scrollIntoViewIfNeeded();
  let resizeBox = await topLeftResize.boundingBox();
  await page.mouse.move(
    resizeBox.x + resizeBox.width / 2,
    resizeBox.y + resizeBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    resizeBox.x + resizeBox.width / 2 + 20,
    resizeBox.y + resizeBox.height / 2 + 15,
    { steps: 5 },
  );
  await shot("workspace-canvas-resize-ghost");
  await page.keyboard.press("Escape");
  await page.mouse.up();
  assert.equal(
    await page
      .getByRole("dialog", { name: "Review object layout", exact: true })
      .count(),
    0,
  );
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await calloutPick.click();
  const rightResize = canvasOverlay.getByRole("button", {
    name: "Resize selection right",
    exact: true,
  });
  await rightResize.focus();
  await rightResize.press("ArrowRight");
  const resizedReview = page.getByRole("dialog", {
    name: "Review object layout",
    exact: true,
  });
  await resizedReview.waitFor();
  await resizedReview
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await resizedReview.waitFor({ state: "detached" });
  await labelPick.click({ modifiers: ["Shift"] });
  await topLeftResize.scrollIntoViewIfNeeded();
  resizeBox = await topLeftResize.boundingBox();
  await page.mouse.move(
    resizeBox.x + resizeBox.width / 2,
    resizeBox.y + resizeBox.height / 2,
  );
  await page.mouse.down();
  await page.keyboard.down("Shift");
  await page.mouse.move(
    resizeBox.x + resizeBox.width / 2 + 20,
    resizeBox.y + resizeBox.height / 2 + 1,
    { steps: 5 },
  );
  await page.mouse.up();
  await page.keyboard.up("Shift");
  await resizedReview.waitFor();
  assert.equal(
    await resizedReview
      .locator("li")
      .filter({ hasText: /; size .* × .* → .* × .* inches/ })
      .count(),
    2,
  );
  await resizedReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await resizedReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor({ timeout: 30000 });
  assert.equal(
    await resizedReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isEnabled(),
    false,
  );
  await resizedReview.getByRole("checkbox").check();
  await shot("workspace-canvas-resize-review");
  await resizedReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await resizedReview.waitFor({ state: "detached" });
  await page
    .getByText("Saved the reviewed object layout as one revision.", {
      exact: true,
    })
    .waitFor();
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  checks.push(
    "Eight canvas resize handles support selected groups, ghosts, Escape cancellation, keyboard drafting, proportional corner review, required acknowledgment, save and undo",
  );
  await labelPick.focus();
  await labelPick.press("Escape");
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .uncheck();
  await canvasOverlay.waitFor({ state: "detached" });
  checks.push(
    "Canvas click, Shift-click, keyboard additive selection, Escape and reverse marquee feed reviewed alignment without editing the deck",
  );
  await studioPanel("Objects");
  await page
    .getByRole("button", { name: "Arrange objects together", exact: true })
    .click();
  let objectLayoutReview = page.getByRole("dialog", {
    name: "Review object layout",
    exact: true,
  });
  await objectLayoutReview.waitFor();
  await objectLayoutReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await objectLayoutReview
    .getByRole("alert")
    .filter({ hasText: "Select between 2 and 20" })
    .waitFor();
  await objectLayoutReview
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await objectLayoutReview.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Arrange objects together", exact: true })
    .click();
  objectLayoutReview = page.getByRole("dialog", {
    name: "Review object layout",
    exact: true,
  });
  const layoutChecks = objectLayoutReview
    .getByRole("group", { name: "Objects to arrange", exact: true })
    .getByRole("checkbox");
  let selectedForLayout = 0;
  for (let i = 0; i < (await layoutChecks.count()); i++) {
    if (await layoutChecks.nth(i).isEnabled()) {
      await layoutChecks.nth(i).check();
      selectedForLayout++;
    }
  }
  assert.ok(
    selectedForLayout >= 3,
    "Native title, body and callout can be arranged together",
  );
  await objectLayoutReview
    .getByRole("combobox", { name: "Layout command", exact: true })
    .selectOption("right");
  await objectLayoutReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await objectLayoutReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor({ timeout: 30_000 });
  const saveLayout = objectLayoutReview.getByRole("button", {
    name: "Save reviewed changes",
    exact: true,
  });
  assert.equal(
    await saveLayout.isEnabled(),
    false,
    "Layout save requires review acknowledgment",
  );
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await objectLayoutReview.getByRole("checkbox").check();
  await shot("workspace-object-layout-review");
  await saveLayout.click();
  await objectLayoutReview.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 8", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  checks.push(
    "Multi-object alignment validates selection, cancels without mutation, previews native geometry, requires review, saves one revision and undoes all moves together",
  );
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .check();
  await calloutPick.click();
  await labelPick.click({ modifiers: ["Shift"] });
  await calloutPick.focus();
  await calloutPick.press("Control+c");
  await page
    .getByText("2 copied · presentation clipboard", { exact: true })
    .waitFor();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Next slide", exact: true }).click();
  await page
    .getByRole("button", { name: "Paste objects", exact: true })
    .click();
  const pasteReview = page.getByRole("dialog", {
    name: "Review pasted objects",
    exact: true,
  });
  await pasteReview.waitFor();
  assert.equal(await pasteReview.locator("li").count(), 2);
  await pasteReview
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await pasteReview.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Paste objects", exact: true })
    .click();
  await pasteReview.waitFor();
  await pasteReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await pasteReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor({ timeout: 30000 });
  assert.equal(
    await pasteReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isEnabled(),
    false,
  );
  await pasteReview.getByRole("checkbox").check();
  await shot("workspace-object-paste-review");
  await pasteReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await pasteReview.waitFor({ state: "detached" });
  await page
    .getByText("Pasted the reviewed objects as one revision.", { exact: true })
    .waitFor();
  await page.getByText("Current · Revision 9", { exact: true }).waitFor();
  assert.equal(
    await canvasOverlay.locator('rect[aria-pressed="true"]').count(),
    2,
    "Pasted group stays selected for the next canvas edit",
  );
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .uncheck();
  checks.push(
    "Presentation clipboard copies a native selection by keyboard, survives slide navigation, cancels without mutation, previews pasted objects, requires acknowledgment, saves one revision and undoes the batch",
  );

  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .check();
  await calloutPick.click();
  await labelPick.click({ modifiers: ["Shift"] });
  const selectionCountBefore = await canvasOverlay
    .locator("rect[aria-pressed]")
    .count();
  await calloutPick.press("Control+d");
  const duplicateReview = page.getByRole("dialog", {
    name: "Review selection duplication",
    exact: true,
  });
  await duplicateReview.waitFor();
  assert.equal(await duplicateReview.locator("li").count(), 2);
  await duplicateReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await duplicateReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor();
  await duplicateReview
    .getByRole("button", { name: "Discard preview", exact: true })
    .click();
  await duplicateReview.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await calloutPick.waitFor();
  assert.equal(
    await canvasOverlay.locator("rect[aria-pressed]").count(),
    selectionCountBefore,
  );
  assert.equal(
    await canvasOverlay.locator('rect[aria-pressed="true"]').count(),
    2,
    "Discard preserves the original selection",
  );
  await page
    .getByRole("button", { name: "Duplicate selection", exact: true })
    .click();
  await duplicateReview.waitFor();
  await duplicateReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await duplicateReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor();
  assert.equal(
    await duplicateReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isEnabled(),
    false,
  );
  await duplicateReview.getByRole("checkbox").check();
  await shot("workspace-selection-duplicate-review");
  await duplicateReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await duplicateReview.waitFor({ state: "detached" });
  await page
    .getByText("Duplicated the reviewed objects as one revision.", {
      exact: true,
    })
    .waitFor();
  const duplicateHead = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await calloutPick.waitFor();
  assert.equal(
    await canvasOverlay.locator("rect[aria-pressed]").count(),
    selectionCountBefore + 2,
  );
  const selectedCopies = canvasOverlay.locator('rect[aria-pressed="true"]');
  assert.equal(
    await selectedCopies.count(),
    2,
    "Saved duplicate identities keep the entire selection",
  );
  await selectedCopies.first().press("Backspace");
  const deleteReview = page.getByRole("dialog", {
    name: "Review selection deletion",
    exact: true,
  });
  await deleteReview.waitFor();
  await deleteReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await deleteReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor();
  await deleteReview
    .getByRole("button", { name: "Discard preview", exact: true })
    .click();
  await deleteReview.waitFor({ state: "detached" });
  await page.getByText(duplicateHead, { exact: true }).waitFor();
  await calloutPick.waitFor();
  assert.equal(await selectedCopies.count(), 2);
  await selectedCopies.first().press("Delete");
  await deleteReview.waitFor();
  assert.equal(await deleteReview.locator("li").count(), 2);
  await deleteReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await deleteReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor();
  assert.equal(
    await deleteReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isEnabled(),
    false,
  );
  await deleteReview.getByRole("checkbox").check();
  await shot("workspace-selection-delete-review");
  await deleteReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await deleteReview.waitFor({ state: "detached" });
  await page
    .getByText("Deleted the reviewed objects as one revision.", { exact: true })
    .waitFor();
  const deletionHead = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await calloutPick.waitFor();
  assert.equal(
    await canvasOverlay.locator("rect[aria-pressed]").count(),
    selectionCountBefore,
  );
  await calloutPick.press("Control+z");
  await page.getByText(duplicateHead, { exact: true }).waitFor();
  await calloutPick.waitFor();
  assert.equal(
    await canvasOverlay.locator("rect[aria-pressed]").count(),
    selectionCountBefore + 2,
  );
  await calloutPick.press("Control+Shift+z");
  await page.getByText(deletionHead, { exact: true }).waitFor();
  await calloutPick.press("Control+z");
  await page.getByText(duplicateHead, { exact: true }).waitFor();
  await calloutPick.press("Control+y");
  await page.getByText(deletionHead, { exact: true }).waitFor();
  await calloutPick.press("Control+z");
  await page.getByText(duplicateHead, { exact: true }).waitFor();
  await calloutPick.press("Control+z");
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .uncheck();

  checks.push(
    "Selection duplication/deletion preview and cancel preserve the deck, acknowledgment saves one revision, copies stay selected, and canvas Ctrl+D, Delete/Backspace and undo/redo traverse the whole batch",
  );
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .check();
  await calloutPick.click();
  await labelPick.click({ modifiers: ["Shift"] });
  const beforeGroupingCount = await canvasOverlay
    .locator("rect[aria-pressed]")
    .count();
  await calloutPick.press("Control+g");
  const nativeGroupingReview = page.getByRole("dialog", {
    name: "Review native grouping",
    exact: true,
  });
  await nativeGroupingReview.waitFor();
  assert.equal(await nativeGroupingReview.locator("li").count(), 2);
  await nativeGroupingReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await nativeGroupingReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor();
  assert.equal(
    await nativeGroupingReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isEnabled(),
    false,
  );
  await nativeGroupingReview
    .getByRole("button", { name: "Discard preview", exact: true })
    .click();
  await nativeGroupingReview.waitFor({ state: "detached" });
  await calloutPick.waitFor();
  assert.equal(
    await canvasOverlay.locator('rect[aria-pressed="true"]').count(),
    2,
  );
  await page
    .getByRole("button", { name: "Group selection", exact: true })
    .click();
  await nativeGroupingReview.waitFor();
  await nativeGroupingReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await nativeGroupingReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor();
  await nativeGroupingReview.getByRole("checkbox").check();
  await shot("workspace-native-group-review");
  await nativeGroupingReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await nativeGroupingReview.waitFor({ state: "detached" });
  await page
    .getByText("Grouped the reviewed objects as one revision.", { exact: true })
    .waitFor();
  const nativeGroupHead = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  const nativeGroupPick = canvasOverlay.getByRole("button", {
    name: /^Select Group \d+ on slide$/,
  });
  await nativeGroupPick.waitFor();
  assert.equal(await nativeGroupPick.getAttribute("aria-pressed"), "true");
  assert.equal(
    await canvasOverlay.locator("rect[aria-pressed]").count(),
    beforeGroupingCount - 1,
  );
  assert.equal(
    await calloutPick.count(),
    0,
    "Children are selected through their containing group",
  );
  async function saveGroupActionReview(title, screenshot) {
    const review = page.getByRole("dialog", { name: title, exact: true });
    await review.waitFor();
    await review
      .getByRole("button", { name: "Preview all changes", exact: true })
      .click();
    await review
      .getByRole("img", {
        name: "Proposed slide with arranged objects",
        exact: true,
      })
      .waitFor();
    assert.equal(
      await review
        .getByRole("button", { name: "Save reviewed changes", exact: true })
        .isEnabled(),
      false,
    );
    await review.getByRole("checkbox").check();
    if (screenshot) await shot(screenshot);
    await review
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .click();
    await review.waitFor({ state: "detached" });
  }
  for (const copyAction of ["duplicate", "paste"]) {
    await nativeGroupPick.waitFor();
    await nativeGroupPick.click();
    if (copyAction === "paste") {
      await nativeGroupPick.press("Control+c");
      await page
        .getByText("1 copied · presentation clipboard", { exact: true })
        .waitFor();
      await nativeGroupPick.press("Control+v");
    } else {
      await nativeGroupPick.press("Control+d");
    }
    await saveGroupActionReview(
      copyAction === "paste"
        ? "Review pasted objects"
        : "Review selection duplication",
      `workspace-group-${copyAction}-review`,
    );
    const selectedGroupCopy = canvasOverlay.locator(
      'rect[aria-pressed="true"]',
    );
    await selectedGroupCopy.waitFor();
    assert.match(
      await selectedGroupCopy.getAttribute("aria-label"),
      /^Select Group \d+ copy.* on slide$/,
    );
    assert.equal(
      await canvasOverlay.locator("rect[aria-pressed]").count(),
      beforeGroupingCount,
    );
    await selectedGroupCopy.press("Delete");
    const groupDeletionReview = page.getByRole("dialog", {
      name: "Review selection deletion",
      exact: true,
    });
    await groupDeletionReview.waitFor();
    await groupDeletionReview
      .getByRole("button", { name: "Preview all changes", exact: true })
      .click();
    await groupDeletionReview
      .getByRole("img", {
        name: "Proposed slide with arranged objects",
        exact: true,
      })
      .waitFor();
    await groupDeletionReview
      .getByRole("button", { name: "Discard preview", exact: true })
      .click();
    await groupDeletionReview.waitFor({ state: "detached" });
    await selectedGroupCopy.waitFor();
    await selectedGroupCopy.press("Delete");
    await saveGroupActionReview(
      "Review selection deletion",
      "workspace-group-delete-review",
    );
    await nativeGroupPick.waitFor();
    assert.equal(
      await canvasOverlay.locator("rect[aria-pressed]").count(),
      beforeGroupingCount - 1,
    );
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await canvasOverlay
      .getByRole("button", { name: /^Select Group \d+ copy.* on slide$/ })
      .waitFor();
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await page.getByText(nativeGroupHead, { exact: true }).waitFor();
    await nativeGroupPick.waitFor();
    await nativeGroupPick.click();
  }
  await studioPanel("Objects");
  const groupObjectSelect = page.getByRole("combobox", {
    name: "Object to edit",
    exact: true,
  });
  const nativeGroupOption = await groupObjectSelect
    .locator("option")
    .filter({ hasText: /^Group \d+ · grpSp · editable$/ })
    .innerText();
  await groupObjectSelect.selectOption({ label: nativeGroupOption });
  await page.getByRole("button", { name: "Send to back", exact: true }).click();
  await page.getByText(/Saved object layer in revision/).waitFor();
  await studioPanel("Objects");
  const groupLayerOrder = await groupObjectSelect
    .locator("option")
    .allTextContents();
  assert.equal(groupLayerOrder[1], nativeGroupOption);
  await shot("workspace-group-layer-back");
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText(nativeGroupHead, { exact: true }).waitFor();
  await nativeGroupPick.waitFor();
  await nativeGroupPick.click();
  checks.push(
    "Native groups duplicate and paste as selected containers, discard and delete as complete subtrees, layer as one unit, and undo without losing original children",
  );
  const nativeGroupWidth = Number(await nativeGroupPick.getAttribute("width"));
  await page
    .getByRole("button", { name: "Resize selection right", exact: true })
    .press("ArrowLeft");
  objectLayoutReview = page.getByRole("dialog", {
    name: "Review object layout",
    exact: true,
  });
  await objectLayoutReview.waitFor();
  await objectLayoutReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await objectLayoutReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor();
  await objectLayoutReview.getByRole("checkbox").check();
  await objectLayoutReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await objectLayoutReview.waitFor({ state: "detached" });
  await page
    .getByText("Saved the reviewed object layout as one revision.", {
      exact: true,
    })
    .waitFor();
  const resizedGroupHead = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await nativeGroupPick.waitFor();
  assert.equal(
    await nativeGroupPick.getAttribute("aria-pressed"),
    "true",
    "Resizing keeps the native group selected",
  );
  assert.ok(
    Number(await nativeGroupPick.getAttribute("width")) < nativeGroupWidth,
  );
  await nativeGroupPick.press("Control+Shift+g");
  const nativeUngroupReview = page.getByRole("dialog", {
    name: "Review native ungrouping",
    exact: true,
  });
  await nativeUngroupReview.waitFor();
  await nativeUngroupReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await nativeUngroupReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor();
  await nativeUngroupReview
    .getByRole("button", { name: "Discard preview", exact: true })
    .click();
  await nativeUngroupReview.waitFor({ state: "detached" });
  await nativeGroupPick.waitFor();
  assert.equal(await nativeGroupPick.getAttribute("aria-pressed"), "true");
  await page
    .getByRole("button", { name: "Ungroup selection", exact: true })
    .click();
  await nativeUngroupReview.waitFor();
  await nativeUngroupReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await nativeUngroupReview
    .getByRole("img", {
      name: "Proposed slide with arranged objects",
      exact: true,
    })
    .waitFor();
  assert.equal(
    await nativeUngroupReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isEnabled(),
    false,
  );
  await nativeUngroupReview.getByRole("checkbox").check();
  await shot("workspace-native-ungroup-review");
  await nativeUngroupReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await nativeUngroupReview.waitFor({ state: "detached" });
  await page
    .getByText("Ungrouped the reviewed objects as one revision.", {
      exact: true,
    })
    .waitFor();
  await calloutPick.waitFor();
  assert.equal(await nativeGroupPick.count(), 0);
  assert.equal(
    await canvasOverlay.locator("rect[aria-pressed]").count(),
    beforeGroupingCount,
  );
  assert.equal(
    await canvasOverlay.locator('rect[aria-pressed="true"]').count(),
    2,
  );
  await calloutPick.press("Control+z");
  await page.getByText(resizedGroupHead, { exact: true }).waitFor();
  await nativeGroupPick.press("Control+z");
  await page.getByText(nativeGroupHead, { exact: true }).waitFor();
  await nativeGroupPick.press("Control+z");
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  await page
    .getByRole("checkbox", { name: "Select objects on slide", exact: true })
    .uncheck();
  checks.push(
    "Native grouping and ungrouping preview, discard, acknowledgment and save preserve selection; groups resize through review; Ctrl+G/Ctrl+Shift+G and undo restore native child identities",
  );
  const appendixActions = page.getByText("Slide actions & layout", {
    exact: true,
  });
  async function openAppendix(mode = "move") {
    if (
      !(await appendixActions.evaluate(
        (element) => element.closest("details").open,
      ))
    )
      await appendixActions.click();
    await page
      .getByRole("button", { name: "Create appendix", exact: true })
      .click();
    const review = page.getByRole("dialog", {
      name: "Create an appendix",
      exact: true,
    });
    await review.waitFor();
    const choices = review.getByRole("listbox", {
      name: "Appendix detail slides",
      exact: true,
    });
    const firstId = await choices
      .locator("option")
      .nth(0)
      .getAttribute("value");
    const lastId = await choices.locator("option").nth(2).getAttribute("value");
    await choices.selectOption([firstId, lastId]);
    await review
      .getByRole("combobox", { name: "Appendix move or copy", exact: true })
      .selectOption(mode);
    await review
      .getByRole("textbox", { name: "Appendix divider notes", exact: true })
      .fill("Preserve native detail and notes.");
    return review;
  }
  async function reviewAppendix(review) {
    await review
      .getByRole("button", { name: "Preview appendix", exact: true })
      .click();
    await review
      .getByRole("img", { name: "Proposed appendix slide", exact: true })
      .waitFor();
    await review
      .getByText("Viewed 1 of 3 appendix slides.", { exact: true })
      .waitFor();
    assert.equal(
      await review.evaluate((dialog) => {
        const image = dialog.querySelector(
          'img[alt="Proposed appendix slide"]',
        );
        const preview = image?.closest("section");
        return (
          dialog.scrollWidth <= dialog.clientWidth + 1 &&
          image.getBoundingClientRect().width <=
            preview.getBoundingClientRect().width + 1
        );
      }),
      true,
      "Appendix preview fits the dialog without horizontal overflow",
    );
    assert.equal(await review.getByRole("checkbox").isEnabled(), false);
    assert.equal(
      await review
        .getByRole("button", { name: "Save reviewed appendix", exact: true })
        .isEnabled(),
      false,
    );
    for (let count = 2; count <= 3; count++) {
      await review
        .getByRole("button", { name: "Next appendix preview", exact: true })
        .click();
      await review
        .getByText(`Viewed ${count} of 3 appendix slides.`, { exact: true })
        .waitFor();
    }
    await review.getByRole("checkbox").check();
  }
  let appendixReview = await openAppendix();
  await reviewAppendix(appendixReview);
  await appendixReview
    .getByText("Edit appendix choices", { exact: true })
    .click();
  await appendixReview
    .getByRole("textbox", { name: "Appendix divider title", exact: true })
    .fill("Supporting detail");
  assert.equal(
    await appendixReview
      .getByRole("button", { name: "Save reviewed appendix", exact: true })
      .isEnabled(),
    false,
  );
  await appendixReview
    .getByText("The draft changed. Preview again before saving.", {
      exact: true,
    })
    .waitFor();
  await appendixReview
    .getByRole("button", { name: "Discard / close", exact: true })
    .click();
  await appendixReview.waitFor({ state: "detached" });
  await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  for (const mode of ["move", "copy"]) {
    appendixReview = await openAppendix(mode);
    await reviewAppendix(appendixReview);
    await shot(`workspace-appendix-${mode}-review`);
    await appendixReview
      .getByRole("button", { name: "Save reviewed appendix", exact: true })
      .click();
    await appendixReview.waitFor({ state: "detached" });
    await page
      .getByText(
        "Saved the reviewed appendix as one revision and refreshed retrieval.",
        { exact: true },
      )
      .waitFor();
    await page
      .getByText(mode === "move" ? "Slide 2 of 4" : "Slide 4 of 6", {
        exact: true,
      })
      .waitFor();
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await page.getByText("Current · Revision 4", { exact: true }).waitFor();
  }
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .first()
    .click();
  await page.getByText("Slide 1 of 3", { exact: true }).waitFor();
  checks.push(
    "Appendix move/copy previews every detail and divider, invalidates changed drafts, discards, saves one native revision, selects the divider, reindexes and undoes the complete appendix",
  );
  await studioPanel("Text");
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await page.getByText("Current · Revision 1", { exact: true }).waitFor();
  assert.equal(
    await page
      .getByRole("combobox", { name: "Text on this slide", exact: true })
      .locator("option")
      .filter({ hasText: "Approve the measured pilot" })
      .count(),
    0,
  );
  checks.push(
    "Copilot creates, formats and positions a new object through earlier-step references, previews the native result, saves one revision, and undoes the whole creation",
  );
  const nativeSlideActions = page.getByText("Slide actions & layout", {
    exact: true,
  });
  if (
    !(await nativeSlideActions.evaluate(
      (element) => element.parentElement.open,
    ))
  )
    await nativeSlideActions.click();
  const beforeNativeLayout = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await page
    .getByRole("button", { name: "Browse native layouts", exact: true })
    .click();
  const nativeLayoutDialog = page.getByRole("dialog", {
    name: /Native layouts for slide/,
  });
  const nativeLayoutChoice = nativeLayoutDialog.getByRole("combobox", {
    name: "Native layout",
    exact: true,
  });
  await page.waitForFunction(
    () =>
      document.querySelector('[aria-label="Native layout"]')?.options.length >
      1,
  );
  const unusedNativeLayouts = await nativeLayoutChoice.evaluate((element) =>
    Array.from(element.options)
      .filter((option) => option.textContent.endsWith("unused"))
      .map((option) => option.value),
  );
  assert.ok(unusedNativeLayouts.length > 1);
  const layoutBaseline = nativeLayoutDialog.getByRole("img", {
    name: "Current native layout baseline",
    exact: true,
  });
  await layoutBaseline.waitFor();
  const baselineUrl = await layoutBaseline.getAttribute("src");
  const compareLayouts = nativeLayoutDialog.getByRole("button", {
    name: "Compare layout thumbnails",
    exact: true,
  });
  await compareLayouts.click();
  await nativeLayoutDialog.getByText(/Layout comparison page 1 of/).waitFor();
  assert.equal(
    await nativeLayoutDialog.locator(".pw-layout-thumbnail img").count(),
    4,
  );
  await nativeLayoutDialog
    .getByRole("button", { name: "Next layout comparisons", exact: true })
    .click();
  await nativeLayoutDialog.getByText(/Layout comparison page 2 of/).waitFor();
  assert.equal(await layoutBaseline.getAttribute("src"), baselineUrl);
  await nativeLayoutDialog
    .getByRole("button", { name: "Previous layout comparisons", exact: true })
    .click();
  await nativeLayoutDialog.getByText(/Layout comparison page 1 of/).waitFor();
  await nativeLayoutDialog.locator(".pw-layout-thumbnail").first().click();
  assert.equal(
    await nativeLayoutDialog
      .getByRole("button", { name: "Save reviewed native layout", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(
    await nativeLayoutDialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
    true,
  );
  await nativeLayoutDialog
    .getByRole("heading", {
      name: "Compare layouts on this slide",
      exact: true,
    })
    .scrollIntoViewIfNeeded();
  await shot("workspace-native-layout-comparisons");
  await nativeLayoutDialog
    .locator(".pw-layout-thumbnails")
    .scrollIntoViewIfNeeded();
  await page.waitForFunction(() => {
    const images = [...document.querySelectorAll(".pw-layout-thumbnail img")];
    return (
      images.length === 4 &&
      images.every((image) => image.complete && image.naturalWidth > 0)
    );
  });
  await shot("workspace-native-layout-thumbnail-gallery");
  await nativeLayoutChoice.selectOption(unusedNativeLayouts[0]);
  await nativeLayoutDialog
    .getByRole("button", { name: "Preview native layout", exact: true })
    .click();
  const nativeLayoutImage = nativeLayoutDialog.getByRole("img", {
    name: "Proposed native layout",
    exact: true,
  });
  await nativeLayoutImage.waitFor();
  await nativeLayoutDialog
    .getByRole("checkbox", {
      name: "I reviewed this layout on the current slide.",
      exact: true,
    })
    .check();
  await compareLayouts.click();
  assert.equal(
    await nativeLayoutDialog
      .getByRole("button", { name: "Save reviewed native layout", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(await layoutBaseline.getAttribute("src"), baselineUrl);
  await nativeLayoutChoice.selectOption(unusedNativeLayouts[1]);
  assert.equal(
    await nativeLayoutDialog
      .getByRole("button", { name: "Save reviewed native layout", exact: true })
      .isDisabled(),
    true,
  );
  await nativeLayoutDialog
    .getByRole("button", { name: "Discard native layout preview", exact: true })
    .click();
  await nativeLayoutDialog.waitFor({ state: "detached" });
  await revisionHistory
    .getByText(beforeNativeLayout, { exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Browse native layouts", exact: true })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelector('[aria-label="Native layout"]')?.options.length >
      1,
  );
  const remappingLayout = await nativeLayoutChoice.evaluate(
    (element) =>
      Array.from(element.options).find((option) =>
        option.textContent.includes(" · Comparison · "),
      )?.value,
  );
  assert.ok(remappingLayout);
  await nativeLayoutChoice.selectOption(remappingLayout);
  const placeholderChoice = nativeLayoutDialog
    .getByRole("combobox", {
      name: /^Remap placeholder /,
    })
    .first();
  await placeholderChoice.waitFor();
  await placeholderChoice.selectOption({ index: 1 });
  await nativeLayoutDialog
    .getByRole("button", { name: "Preview native layout", exact: true })
    .click();
  await nativeLayoutImage.waitFor();
  await nativeLayoutDialog
    .getByRole("checkbox", {
      name: "I reviewed this layout on the current slide.",
      exact: true,
    })
    .check();
  await placeholderChoice.selectOption("");
  assert.equal(
    await nativeLayoutDialog
      .getByRole("button", {
        name: "Save reviewed native layout",
        exact: true,
      })
      .isDisabled(),
    true,
  );
  await placeholderChoice.selectOption({ index: 1 });
  await nativeLayoutDialog
    .getByRole("button", {
      name: "Preview native layout",
      exact: true,
    })
    .click();
  await nativeLayoutImage.waitFor();
  await nativeLayoutDialog
    .getByRole("checkbox", {
      name: "I reviewed this layout on the current slide.",
      exact: true,
    })
    .check();
  await shot("workspace-native-layout-preview");
  await shot("workspace-native-placeholder-remap-review");
  await nativeLayoutDialog
    .getByRole("button", { name: "Save reviewed native layout", exact: true })
    .click();
  await nativeLayoutDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved the reviewed native layout as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText(beforeNativeLayout, { exact: true })
    .waitFor();
  checks.push(
    "Native unused layout discovery, preview, changed-choice approval invalidation, discard, exact reviewed save and undo work in the GUI",
  );
  checks.push(
    "Native placeholder mapping uses a fresh reviewed preview, invalidates approval on reassignment, saves exact reviewed bytes and restores the original revision with undo",
  );
  checks.push(
    "Native layout comparison renders a verified baseline and paged four-candidate thumbnails, preserves the baseline across pages, selects a candidate without approval and invalidates prior previews before comparison",
  );

  if (
    !(await nativeSlideActions.evaluate(
      (element) => element.parentElement.open,
    ))
  )
    await nativeSlideActions.click();
  await page
    .getByRole("button", { name: "Insert from native layout", exact: true })
    .click();
  const nativeInsertDialog = page.getByRole("dialog", {
    name: /Insert native slide after slide/,
  });
  const nativeInsertChoice = nativeInsertDialog.getByRole("combobox", {
    name: "Native layout",
    exact: true,
  });
  await page.waitForFunction(
    () =>
      document.querySelector('[aria-label="Native layout"]')?.options.length >
      1,
  );
  const comparisonOption = await nativeInsertChoice
    .locator("option")
    .filter({ hasText: "Comparison" })
    .getAttribute("value");
  await nativeInsertChoice.selectOption(comparisonOption);
  const nativeSlots = nativeInsertDialog.locator(
    'textarea[aria-label^="Native placeholder:"]',
  );
  assert.equal(await nativeSlots.count(), 5);
  const nativeDraftTexts = [
    "Choose the measured pilot",
    "Option A",
    "Faster learning\nMeasured risk",
    "Option B",
    "Lower cost\nSlower rollout",
  ];
  for (let index = 0; index < nativeDraftTexts.length; index++)
    await nativeSlots.nth(index).fill(nativeDraftTexts[index]);
  await nativeInsertDialog
    .getByRole("textbox", { name: "Native slide speaker notes", exact: true })
    .fill("Explain the tradeoffs and request a decision.");
  await nativeInsertDialog
    .getByRole("button", { name: "Preview native slide", exact: true })
    .click();
  const nativeInsertImage = nativeInsertDialog.getByRole("img", {
    name: "Proposed native slide",
    exact: true,
  });
  await nativeInsertImage.waitFor();
  const nativeInsertAck = nativeInsertDialog.getByRole("checkbox", {
    name: "I reviewed the new native slide and its notes.",
    exact: true,
  });
  await nativeInsertAck.check();
  await nativeSlots.nth(0).fill("Choose the revised pilot");
  assert.equal(
    await nativeInsertDialog
      .getByRole("button", { name: "Save reviewed native slide", exact: true })
      .isDisabled(),
    true,
  );
  await nativeInsertDialog
    .getByRole("button", { name: "Discard native slide preview", exact: true })
    .click();
  await nativeInsertDialog.waitFor({ state: "detached" });
  await revisionHistory
    .getByText(beforeNativeLayout, { exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Insert from native layout", exact: true })
    .click();
  await nativeInsertChoice.selectOption(comparisonOption);
  for (let index = 0; index < nativeDraftTexts.length; index++)
    await nativeSlots.nth(index).fill(nativeDraftTexts[index]);
  await nativeInsertDialog
    .getByRole("textbox", { name: "Native slide speaker notes", exact: true })
    .fill("Explain the tradeoffs and request a decision.");
  await nativeInsertDialog
    .getByRole("button", { name: "Preview native slide", exact: true })
    .click();
  await nativeInsertImage.waitFor();
  await nativeInsertAck.check();
  await shot("workspace-native-slide-preview");
  await nativeInsertDialog
    .getByRole("button", { name: "Save reviewed native slide", exact: true })
    .click();
  await nativeInsertDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Inserted the reviewed native slide as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  await studioPanel("Text");
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .locator("option")
    .filter({ hasText: nativeDraftTexts[0] })
    .waitFor({ state: "attached" });
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText(beforeNativeLayout, { exact: true })
    .waitFor();
  checks.push(
    "Native Comparison creation populates five editable themed slots and notes, invalidates edited drafts, discards, previews, saves one revision, selects the new slide and undoes creation",
  );

  if (
    !(await nativeSlideActions.evaluate(
      (element) => element.parentElement.open,
    ))
  )
    await nativeSlideActions.click();
  const beforeNativeTable = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await page
    .getByRole("button", { name: "Native tables", exact: true })
    .click();
  const nativeTableDialog = page.getByRole("dialog", {
    name: /Native tables on slide/,
  });
  const tablePreview = nativeTableDialog.getByRole("button", {
    name: "Preview native table",
    exact: true,
  });
  const tableSave = nativeTableDialog.getByRole("button", {
    name: "Save reviewed native table",
    exact: true,
  });
  const tableAck = nativeTableDialog.getByRole("checkbox", {
    name: "I reviewed this table’s cells, placement and text fit.",
    exact: true,
  });
  const tableImage = nativeTableDialog.getByRole("img", {
    name: "Proposed native table",
    exact: true,
  });
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 2, column 1", exact: true })
    .fill("Revenue");
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 2, column 2", exact: true })
    .fill("$10M");
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 2, column 3", exact: true })
    .fill("$12M");
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 3, column 1", exact: true })
    .fill("Risk");
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 3, column 2", exact: true })
    .fill("Measured");
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 3, column 3", exact: true })
    .fill("Bounded");
  await tablePreview.click();
  await tableImage.waitFor();
  await tableAck.check();
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 2, column 3", exact: true })
    .fill("$13M");
  assert.equal(await tableSave.isDisabled(), true);
  await nativeTableDialog
    .getByRole("button", { name: "Discard native table preview", exact: true })
    .click();
  await nativeTableDialog.waitFor({ state: "detached" });
  await revisionHistory.getByText(beforeNativeTable, { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Native tables", exact: true })
    .click();
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 2, column 1", exact: true })
    .fill("Revenue");
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 2, column 2", exact: true })
    .fill("$10M");
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 2, column 3", exact: true })
    .fill("$12M");
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 3, column 1", exact: true })
    .fill("Risk");
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 3, column 2", exact: true })
    .fill("Measured");
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 3, column 3", exact: true })
    .fill("Bounded");
  await tablePreview.click();
  await tableImage.waitFor();
  await tableAck.check();
  await shot("workspace-native-table-insert");
  await tableSave.click();
  await nativeTableDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved the reviewed native table as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  await studioPanel("Objects");
  const tableGeometryBaseline = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  const tableGeometryPicker = page.getByRole("combobox", {
    name: "Object to edit",
    exact: true,
  });
  const tableGeometryId = await tableGeometryPicker
    .locator("option")
    .filter({ hasText: "graphicFrame · editable" })
    .first()
    .getAttribute("value");
  assert.ok(tableGeometryId);
  await tableGeometryPicker.selectOption(tableGeometryId);
  await page
    .getByRole("spinbutton", { name: "X position (inches)", exact: true })
    .fill("1.5");
  await page
    .getByRole("spinbutton", { name: "Width (inches)", exact: true })
    .fill("6.5");
  await page
    .getByRole("button", { name: "Review object layout", exact: true })
    .click();
  const tableGeometryReview = page.getByRole("dialog", {
    name: "Review object layout",
    exact: true,
  });
  await tableGeometryReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await tableGeometryReview.getByRole("img").waitFor();
  assert.equal(
    await tableGeometryReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isDisabled(),
    true,
  );
  await tableGeometryReview.getByRole("checkbox").check();
  await shot("workspace-native-table-layout");
  await tableGeometryReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await tableGeometryReview.waitFor({ state: "detached" });
  await page
    .getByText("Saved the reviewed object layout as one revision.", {
      exact: true,
    })
    .waitFor();
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText(tableGeometryBaseline, { exact: true })
    .waitFor();
  await page
    .getByText(
      /Undid to revision \d+ and refreshed its slide text for retrieval\./,
      { exact: true },
    )
    .waitFor();
  checks.push(
    "Native table geometry discovery, position/size draft, staged layout preview, required review, exact save and undo work in the GUI",
  );
  async function checkGraphicLayerDeletion(kind, baseline) {
    const studioPanelObjects = page.locator("#pw-panel-objects");
    await tableGeometryPicker.selectOption(
      await tableGeometryPicker
        .locator("option")
        .filter({ hasText: "graphicFrame · editable" })
        .first()
        .getAttribute("value"),
    );
    const nativeObjectName = (
      await tableGeometryPicker.locator("option:checked").innerText()
    ).split(" · ")[0];
    await page
      .getByRole("checkbox", { name: "Select objects on slide", exact: true })
      .check();
    await page
      .getByRole("button", {
        name: `Select ${nativeObjectName} on slide`,
        exact: true,
      })
      .click();
    await page
      .getByRole("button", { name: "Resize selection right", exact: true })
      .press("ArrowLeft");
    const nativeResizeReview = page.getByRole("dialog", {
      name: "Review object layout",
      exact: true,
    });
    await nativeResizeReview.waitFor();
    assert.equal(
      await nativeResizeReview
        .locator("li")
        .filter({ hasText: /; size .* × .* → .* × .* inches/ })
        .count(),
      1,
    );
    await nativeResizeReview
      .getByRole("button", { name: "Preview all changes", exact: true })
      .click();
    await nativeResizeReview
      .getByRole("img", {
        name: "Proposed slide with arranged objects",
        exact: true,
      })
      .waitFor({ timeout: 30000 });
    await nativeResizeReview.getByRole("checkbox").check();
    await shot(`workspace-native-${kind}-canvas-resize`);
    await nativeResizeReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .click();
    await nativeResizeReview.waitFor({ state: "detached" });
    await page
      .getByText("Saved the reviewed object layout as one revision.", {
        exact: true,
      })
      .waitFor();
    await revisionHistory
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await revisionHistory.getByText(baseline, { exact: true }).waitFor();
    await page
      .getByText(
        /Undid to revision \d+ and refreshed its slide text for retrieval\./,
        { exact: true },
      )
      .waitFor();
    await page
      .getByRole("checkbox", { name: "Select objects on slide", exact: true })
      .uncheck();
    await tableGeometryPicker.selectOption(
      await tableGeometryPicker
        .locator("option")
        .filter({ hasText: "graphicFrame · editable" })
        .first()
        .getAttribute("value"),
    );
    checks.push(
      `Native ${kind} canvas handles preview and save resizing through the reviewed geometry lane, with undo`,
    );
    await page
      .getByRole("checkbox", { name: "Select objects on slide", exact: true })
      .check();
    const copiedNative = page.getByRole("button", {
      name: `Select ${nativeObjectName} on slide`,
      exact: true,
    });
    await copiedNative.click();
    await page
      .getByRole("button", { name: "Copy objects", exact: true })
      .click();
    await copiedNative.focus();
    await copiedNative.press("Control+v");
    const graphicPasteReview = page.getByRole("dialog", {
      name: "Review pasted objects",
      exact: true,
    });
    await graphicPasteReview.waitFor();
    await graphicPasteReview
      .getByRole("button", { name: "Preview all changes", exact: true })
      .click();
    await graphicPasteReview
      .getByRole("img", {
        name: "Proposed slide with arranged objects",
        exact: true,
      })
      .waitFor({ timeout: 30000 });
    await graphicPasteReview.getByRole("checkbox").check();
    await shot(`workspace-native-${kind}-clipboard-review`);
    await graphicPasteReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .click();
    await graphicPasteReview.waitFor({ state: "detached" });
    await page
      .getByText("Pasted the reviewed objects as one revision.", {
        exact: true,
      })
      .waitFor();
    assert.equal(
      await tableGeometryPicker
        .locator("option")
        .filter({ hasText: "graphicFrame · editable" })
        .count(),
      2,
    );
    assert.equal(
      await page
        .locator('.pw-object-overlay rect[aria-pressed="true"]')
        .count(),
      1,
      "Pasted native graphic stays selected",
    );
    await revisionHistory
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await revisionHistory.getByText(baseline, { exact: true }).waitFor();
    await page
      .getByRole("checkbox", { name: "Select objects on slide", exact: true })
      .uncheck();
    await tableGeometryPicker.selectOption(
      await tableGeometryPicker
        .locator("option")
        .filter({ hasText: "graphicFrame · editable" })
        .first()
        .getAttribute("value"),
    );
    checks.push(
      `Native ${kind} clipboard copy and keyboard paste require preview/review, save an independent native object and undo`,
    );
    await studioPanelObjects
      .getByRole("button", { name: "Send to back", exact: true })
      .click();
    await page.getByText(/Saved object layer in revision/).waitFor();
    await revisionHistory
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await revisionHistory.getByText(baseline, { exact: true }).waitFor();
    await page
      .getByText(
        /Undid to revision \d+ and refreshed its slide text for retrieval\./,
        { exact: true },
      )
      .waitFor();
    const graphicOption = await tableGeometryPicker
      .locator("option")
      .filter({ hasText: "graphicFrame · editable" })
      .first()
      .getAttribute("value");
    await tableGeometryPicker.selectOption(graphicOption);
    await studioPanelObjects
      .getByRole("button", { name: "Duplicate selected object", exact: true })
      .click();
    await page.getByText(/Duplicated the object and refreshed slide/).waitFor();
    assert.equal(
      await tableGeometryPicker
        .locator("option")
        .filter({ hasText: "graphicFrame · editable" })
        .count(),
      2,
    );
    await shot(`workspace-native-${kind}-duplicated`);
    await revisionHistory
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await revisionHistory.getByText(baseline, { exact: true }).waitFor();
    await page
      .getByText(
        /Undid to revision \d+ and refreshed its slide text for retrieval\./,
        { exact: true },
      )
      .waitFor();
    await tableGeometryPicker.selectOption(graphicOption);
    checks.push(
      `Native ${kind} duplication creates an independent selected object, refreshes retrieval and undoes in the GUI`,
    );
    await studioPanelObjects
      .getByRole("button", { name: "Review object deletion", exact: true })
      .click();
    await studioPanelObjects
      .getByRole("button", { name: "Cancel object deletion", exact: true })
      .click();
    await studioPanelObjects
      .getByRole("button", { name: "Review object deletion", exact: true })
      .click();
    await shot(`workspace-native-${kind}-delete-review`);
    await studioPanelObjects
      .getByRole("button", {
        name: "Confirm delete selected object",
        exact: true,
      })
      .click();
    await page.getByText(/Deleted the object and refreshed slide/).waitFor();
    assert.equal(
      await tableGeometryPicker
        .locator("option")
        .filter({ hasText: "graphicFrame · editable" })
        .count(),
      0,
    );
    await revisionHistory
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await revisionHistory.getByText(baseline, { exact: true }).waitFor();
    await page
      .getByText(
        /Undid to revision \d+ and refreshed its slide text for retrieval\./,
        { exact: true },
      )
      .waitFor();
    assert.equal(
      await tableGeometryPicker
        .locator("option")
        .filter({ hasText: "graphicFrame · editable" })
        .count(),
      1,
    );
    checks.push(
      `Native ${kind} layering, confirmation cancellation, deletion and undo work in the GUI`,
    );
    await page
      .getByRole("button", { name: "Duplicate current slide", exact: true })
      .click();
    await page
      .locator(".pw-slide-column .pw-notice")
      .getByText(/Duplicated slide 1 and refreshed slide retrieval/)
      .waitFor();
    await page.getByText("Slide 2 of 4", { exact: true }).waitFor();
    assert.equal(
      await tableGeometryPicker
        .locator("option")
        .filter({ hasText: "graphicFrame · editable" })
        .count(),
      1,
    );
    await tableGeometryPicker.selectOption(
      await tableGeometryPicker
        .locator("option")
        .filter({ hasText: "graphicFrame · editable" })
        .first()
        .getAttribute("value"),
    );
    await shot(`workspace-native-${kind}-slide-duplicated`);
    await revisionHistory
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await revisionHistory.getByText(baseline, { exact: true }).waitFor();
    await page
      .getByText(
        /Undid to revision \d+ and refreshed its slide text for retrieval\./,
        { exact: true },
      )
      .waitFor();
    await page.getByText("Slide 1 of 3", { exact: true }).waitFor();
    await tableGeometryPicker.selectOption(graphicOption);
    checks.push(
      `Whole native ${kind} slides duplicate with editable objects, preview, retrieval refresh and undo in the GUI`,
    );
  }
  await checkGraphicLayerDeletion("table", tableGeometryBaseline);
  const afterTableInsertion = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await page
    .getByRole("button", { name: "Native tables", exact: true })
    .click();
  const tablePicker = nativeTableDialog.getByRole("combobox", {
    name: "Native table",
    exact: true,
  });
  await page.waitForFunction(
    () =>
      document.querySelector('[aria-label="Native table"]')?.options.length > 1,
  );
  await tablePicker.selectOption({ index: 1 });
  assert.equal(
    await nativeTableDialog
      .getByRole("textbox", { name: "Row 2, column 3", exact: true })
      .inputValue(),
    "$12M",
  );
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 2, column 3", exact: true })
    .fill("$13M\nPilot target");
  await tablePreview.click();
  await tableImage.waitFor();
  await tableAck.check();
  await shot("workspace-native-table-edit");
  await tableSave.click();
  await nativeTableDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved the reviewed native table as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText(afterTableInsertion, { exact: true })
    .waitFor();
  await page
    .getByText(
      /Undid to revision \d+ and refreshed its slide text for retrieval\./,
      { exact: true },
    )
    .waitFor();
  await page
    .getByRole("button", { name: "Native tables", exact: true })
    .click();
  await tablePicker.selectOption({ index: 1 });
  const rowChoice = nativeTableDialog.getByRole("combobox", {
    name: "Selected table row",
    exact: true,
  });
  const columnChoice = nativeTableDialog.getByRole("combobox", {
    name: "Selected table column",
    exact: true,
  });
  await rowChoice.selectOption({ value: "1" });
  await nativeTableDialog
    .getByRole("button", { name: "Insert row before", exact: true })
    .click();
  await rowChoice.selectOption({ value: "2" });
  await nativeTableDialog
    .getByRole("button", { name: "Remove row", exact: true })
    .click();
  await rowChoice.selectOption({ value: "1" });
  await nativeTableDialog
    .getByRole("button", { name: "Insert row after", exact: true })
    .click();
  await nativeTableDialog
    .getByRole("button", { name: "Remove row", exact: true })
    .click();
  await columnChoice.selectOption({ value: "2" });
  await nativeTableDialog
    .getByRole("button", { name: "Insert column before", exact: true })
    .click();
  await columnChoice.selectOption({ value: "3" });
  await nativeTableDialog
    .getByRole("button", { name: "Remove column", exact: true })
    .click();
  await columnChoice.selectOption({ value: "2" });
  await nativeTableDialog
    .getByRole("button", { name: "Insert column after", exact: true })
    .click();
  await nativeTableDialog
    .getByRole("button", { name: "Remove column", exact: true })
    .click();
  const structuralCell = nativeTableDialog.getByRole("textbox", {
    name: "Row 2, column 3",
    exact: true,
  });
  assert.equal(
    await nativeTableDialog
      .getByRole("textbox", { name: "Row 1, column 1", exact: true })
      .inputValue(),
    "Metric",
  );
  assert.equal(
    await nativeTableDialog
      .getByRole("textbox", { name: "Row 1, column 2", exact: true })
      .inputValue(),
    "Current",
  );
  assert.equal(
    await nativeTableDialog
      .getByRole("textbox", { name: "Row 2, column 1", exact: true })
      .inputValue(),
    "",
  );
  assert.equal(
    await nativeTableDialog
      .getByRole("textbox", { name: "Row 3, column 2", exact: true })
      .inputValue(),
    "Measured",
  );
  await nativeTableDialog
    .getByRole("textbox", { name: "Row 2, column 1", exact: true })
    .fill("Decision owner");
  await structuralCell.fill("New owner");
  assert.equal(
    await nativeTableDialog
      .getByRole("textbox", { name: "Row 3, column 1", exact: true })
      .inputValue(),
    "Risk",
  );
  await tablePreview.click();
  await tableImage.waitFor();
  assert.equal(await tableSave.isEnabled(), false);
  await tableAck.check();
  await rowChoice.selectOption({ value: "1" });
  await nativeTableDialog
    .getByRole("button", { name: "Insert row after", exact: true })
    .click();
  assert.equal(await tableSave.isEnabled(), false);
  await nativeTableDialog
    .getByRole("button", { name: "Remove row", exact: true })
    .click();
  await tablePreview.click();
  await tableImage.waitFor();
  await tableAck.check();
  await shot("workspace-native-table-structure-review");
  await tableSave.click();
  await nativeTableDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved the reviewed native table as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  await page
    .getByRole("button", { name: "Native tables", exact: true })
    .click();
  await tablePicker.selectOption({ index: 1 });
  assert.equal(await structuralCell.inputValue(), "New owner");
  assert.equal(
    await nativeTableDialog
      .getByRole("textbox", { name: "Row 3, column 1", exact: true })
      .inputValue(),
    "Risk",
  );
  assert.equal(await nativeTableDialog.getByRole("textbox").count(), 9);
  await nativeTableDialog
    .getByRole("button", { name: "Discard native table preview", exact: true })
    .click();
  await nativeTableDialog.waitFor({ state: "detached" });
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText(afterTableInsertion, { exact: true })
    .waitFor();
  checks.push(
    "Native table row/column insertion before/after, middle deletion, retained draft text, structural review invalidation, save, persisted cell discovery and undo work in the GUI",
  );
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(beforeNativeTable, { exact: true }).waitFor();
  checks.push(
    "Native table drafting, bounds, preview, edited-draft invalidation, discard, reviewed creation, persisted cell discovery, multiline editing, retrieval refresh and two-step undo work in the GUI",
  );

  if (
    !(await nativeSlideActions.evaluate(
      (element) => element.parentElement.open,
    ))
  )
    await nativeSlideActions.click();
  const beforeNativeChart = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await page
    .getByRole("button", { name: "Native charts", exact: true })
    .click();
  const chartDialog = page.getByRole("dialog", {
    name: /Native charts on slide/,
  });
  const chartPreview = chartDialog.getByRole("button", {
    name: "Preview native chart",
    exact: true,
  });
  const chartSave = chartDialog.getByRole("button", {
    name: "Save reviewed native chart",
    exact: true,
  });
  const chartImage = chartDialog.getByRole("img", {
    name: "Proposed native chart",
    exact: true,
  });
  const chartAck = chartDialog.getByRole("checkbox", {
    name: "I reviewed this chart’s data, labels and placement.",
    exact: true,
  });
  await chartDialog
    .getByRole("textbox", { name: "Chart title", exact: true })
    .fill("Pilot outcomes");
  await chartDialog
    .getByRole("combobox", { name: "Chart type", exact: true })
    .selectOption("line");
  await chartPreview.click();
  await chartImage.waitFor();
  await chartAck.check();
  await chartDialog
    .getByRole("spinbutton", {
      name: "Category 2, series 1 value",
      exact: true,
    })
    .fill("13");
  assert.equal(await chartSave.isDisabled(), true);
  await chartDialog
    .getByRole("button", { name: "Discard native chart preview", exact: true })
    .click();
  await chartDialog.waitFor({ state: "detached" });
  await revisionHistory.getByText(beforeNativeChart, { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Native charts", exact: true })
    .click();
  await chartDialog
    .getByRole("combobox", { name: "Chart type", exact: true })
    .selectOption("column");
  await chartPreview.click();
  await chartImage.waitFor();
  await chartAck.check();
  await shot("workspace-native-chart-column");
  await chartSave.click();
  await chartDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved the reviewed native chart changes as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  await studioPanel("Objects");
  const chartGeometryBaseline = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  const graphicPicker = page.getByRole("combobox", {
    name: "Object to edit",
    exact: true,
  });
  const graphicId = await graphicPicker
    .locator("option")
    .filter({ hasText: "graphicFrame · editable" })
    .first()
    .getAttribute("value");
  assert.ok(graphicId);
  await graphicPicker.selectOption(graphicId);
  await page
    .getByRole("spinbutton", { name: "X position (inches)", exact: true })
    .fill("1.5");
  await page
    .getByRole("spinbutton", { name: "Width (inches)", exact: true })
    .fill("6.5");
  await page
    .getByRole("button", { name: "Review object layout", exact: true })
    .click();
  const graphicReview = page.getByRole("dialog", {
    name: "Review object layout",
    exact: true,
  });
  await graphicReview
    .getByRole("button", { name: "Preview all changes", exact: true })
    .click();
  await graphicReview.getByRole("img").waitFor();
  assert.equal(
    await graphicReview
      .getByRole("button", { name: "Save reviewed changes", exact: true })
      .isDisabled(),
    true,
  );
  await graphicReview.getByRole("checkbox").check();
  await shot("workspace-native-chart-layout");
  await graphicReview
    .getByRole("button", { name: "Save reviewed changes", exact: true })
    .click();
  await graphicReview.waitFor({ state: "detached" });
  await page
    .getByText("Saved the reviewed object layout as one revision.", {
      exact: true,
    })
    .waitFor();
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText(chartGeometryBaseline, { exact: true })
    .waitFor();
  await page
    .getByText(
      /Undid to revision \d+ and refreshed its slide text for retrieval\./,
      { exact: true },
    )
    .waitFor();
  checks.push(
    "Native chart geometry discovery, position/size draft, staged layout preview, required review, exact save and undo work in the GUI",
  );
  await checkGraphicLayerDeletion("chart", chartGeometryBaseline);
  const createdNativeChartRevision = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await page
    .getByRole("button", { name: "Native charts", exact: true })
    .click();
  const chartAction = chartDialog.getByRole("combobox", {
    name: "Native chart action",
    exact: true,
  });
  const savedChartId = await chartAction
    .locator("option")
    .nth(1)
    .getAttribute("value");
  assert.ok(savedChartId);
  await chartAction.selectOption(savedChartId);
  assert.equal(
    await chartDialog
      .getByRole("textbox", { name: "Chart title", exact: true })
      .inputValue(),
    "Pilot outcomes",
  );
  for (const name of [
    "Chart type",
    "Chart category count",
    "Chart series count",
  ]) {
    assert.equal(
      await chartDialog.getByLabel(name, { exact: true }).isDisabled(),
      true,
    );
  }
  await chartPreview.click();
  await chartDialog
    .getByText("The chart did not change the presentation.", { exact: true })
    .waitFor();
  assert.equal(await chartSave.isDisabled(), true);
  await chartDialog
    .getByRole("spinbutton", {
      name: "Category 2, series 1 value",
      exact: true,
    })
    .fill("17.125");
  await chartPreview.click();
  await chartImage.waitFor();
  await chartAck.check();
  await chartDialog
    .getByRole("spinbutton", {
      name: "Category 2, series 1 value",
      exact: true,
    })
    .fill("18.5");
  assert.equal(await chartSave.isDisabled(), true);
  await chartDialog
    .getByRole("button", { name: "Discard native chart preview", exact: true })
    .click();
  await chartDialog.waitFor({ state: "detached" });
  await revisionHistory
    .getByText(createdNativeChartRevision, { exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Native charts", exact: true })
    .click();
  await chartAction.selectOption(savedChartId);
  assert.equal(
    await chartDialog
      .getByRole("spinbutton", {
        name: "Category 2, series 1 value",
        exact: true,
      })
      .inputValue(),
    "12",
  );
  await chartDialog
    .getByRole("spinbutton", {
      name: "Category 2, series 1 value",
      exact: true,
    })
    .fill("17.125");
  await chartDialog
    .getByRole("textbox", { name: "Chart title", exact: true })
    .fill("Reviewed pilot outcomes");
  await chartPreview.click();
  await chartImage.waitFor();
  await chartAck.check();
  await shot("workspace-native-chart-data-edit");
  await chartSave.click();
  await chartDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved the reviewed native chart changes as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  await page
    .getByRole("button", { name: "Native charts", exact: true })
    .click();
  await chartAction.selectOption(savedChartId);
  assert.equal(
    await chartDialog
      .getByRole("textbox", { name: "Chart title", exact: true })
      .inputValue(),
    "Reviewed pilot outcomes",
  );
  assert.equal(
    await chartDialog
      .getByRole("spinbutton", {
        name: "Category 2, series 1 value",
        exact: true,
      })
      .inputValue(),
    "17.125",
  );
  await chartDialog
    .getByRole("button", { name: "Discard native chart preview", exact: true })
    .click();
  await chartDialog.waitFor({ state: "detached" });
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText(createdNativeChartRevision, { exact: true })
    .waitFor();
  await page
    .getByText(
      /Undid to revision \d+ and refreshed its slide text for retrieval\./,
      { exact: true },
    )
    .waitFor();
  checks.push(
    "Existing native chart discovery, fixed structure, no-op, data/title drafts, edited-value approval invalidation, discard, reviewed data save, persisted values, retrieval refresh and two-step undo work in the GUI",
  );
  await page
    .getByRole("button", { name: "Native charts", exact: true })
    .click();
  await chartAction.selectOption(savedChartId);
  const categoryChoice = chartDialog.getByRole("combobox", {
    name: "Selected chart category",
    exact: true,
  });
  const seriesChoice = chartDialog.getByRole("combobox", {
    name: "Selected chart series",
    exact: true,
  });
  await categoryChoice.selectOption({ value: "1" });
  await chartDialog
    .getByRole("button", { name: "Insert category before", exact: true })
    .click();
  await categoryChoice.selectOption({ value: "2" });
  await chartDialog
    .getByRole("button", { name: "Remove category", exact: true })
    .click();
  await categoryChoice.selectOption({ value: "1" });
  await chartDialog
    .getByRole("button", { name: "Insert category after", exact: true })
    .click();
  await chartDialog
    .getByRole("button", { name: "Remove category", exact: true })
    .click();
  await seriesChoice.selectOption({ value: "1" });
  await chartDialog
    .getByRole("button", { name: "Insert series before", exact: true })
    .click();
  await seriesChoice.selectOption({ value: "2" });
  await chartDialog
    .getByRole("button", { name: "Remove series", exact: true })
    .click();
  await seriesChoice.selectOption({ value: "1" });
  await chartDialog
    .getByRole("button", { name: "Insert series after", exact: true })
    .click();
  await chartDialog
    .getByRole("button", { name: "Remove series", exact: true })
    .click();
  assert.equal(
    await chartDialog
      .getByRole("textbox", { name: "Category 1", exact: true })
      .inputValue(),
    "Baseline",
  );
  assert.equal(
    await chartDialog
      .getByRole("textbox", { name: "Category 3", exact: true })
      .inputValue(),
    "Target",
  );
  assert.equal(
    await chartDialog
      .getByRole("spinbutton", {
        name: "Category 3, series 1 value",
        exact: true,
      })
      .inputValue(),
    "15",
  );
  await chartDialog
    .getByRole("textbox", { name: "Category 2", exact: true })
    .fill("Forecast");
  await chartDialog
    .getByRole("textbox", { name: "Series 2 name", exact: true })
    .fill("Margin");
  for (const [r, c, value] of [
    [2, 1, "11"],
    [1, 2, "2"],
    [2, 2, "3"],
    [3, 2, "4"],
  ]) {
    await chartDialog
      .getByRole("spinbutton", {
        name: `Category ${r}, series ${c} value`,
        exact: true,
      })
      .fill(value);
  }
  await chartPreview.click();
  await chartImage.waitFor();
  assert.equal(await chartSave.isEnabled(), false);
  await chartAck.check();
  await categoryChoice.selectOption({ value: "1" });
  await chartDialog
    .getByRole("button", { name: "Insert category after", exact: true })
    .click();
  assert.equal(await chartSave.isEnabled(), false);
  await chartDialog
    .getByRole("button", { name: "Remove category", exact: true })
    .click();
  await chartPreview.click();
  await chartImage.waitFor();
  await chartAck.check();
  await shot("workspace-native-chart-structure-review");
  await chartSave.click();
  await chartDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved the reviewed native chart changes as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  await page
    .getByRole("button", { name: "Native charts", exact: true })
    .click();
  await chartAction.selectOption(savedChartId);
  assert.equal(
    await chartDialog
      .getByRole("textbox", { name: "Category 2", exact: true })
      .inputValue(),
    "Forecast",
  );
  assert.equal(
    await chartDialog
      .getByRole("textbox", { name: "Series 2 name", exact: true })
      .inputValue(),
    "Margin",
  );
  assert.equal(
    await chartDialog
      .getByRole("spinbutton", {
        name: "Category 3, series 2 value",
        exact: true,
      })
      .inputValue(),
    "4",
  );
  await chartDialog
    .getByRole("button", { name: "Discard native chart preview", exact: true })
    .click();
  await chartDialog.waitFor({ state: "detached" });
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText(createdNativeChartRevision, { exact: true })
    .waitFor();
  checks.push(
    "Native chart category/series insertion before/after, middle deletion, retained labels/values, structural review invalidation, reviewed save, persisted discovery and undo work in the GUI",
  );
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(beforeNativeChart, { exact: true }).waitFor();
  await page
    .getByText(
      /Undid to revision \d+ and refreshed its slide text for retrieval\./,
      { exact: true },
    )
    .waitFor();
  await page
    .getByRole("button", { name: "Native charts", exact: true })
    .click();
  await chartDialog
    .getByRole("combobox", { name: "Chart type", exact: true })
    .selectOption("pie");
  assert.equal(
    await chartDialog
      .getByRole("spinbutton", { name: "Chart series count", exact: true })
      .inputValue(),
    "1",
  );
  await chartPreview.click();
  await chartImage.waitFor();
  await chartAck.check();
  await shot("workspace-native-chart-pie");
  await chartDialog
    .getByRole("button", { name: "Discard native chart preview", exact: true })
    .click();
  await chartDialog.waitFor({ state: "detached" });
  await revisionHistory.getByText(beforeNativeChart, { exact: true }).waitFor();
  checks.push(
    "Native chart data/type drafting, line/column/pie rendering, edited-value review invalidation, discard, reviewed save, retrieval refresh and undo work in the GUI",
  );

  if (
    !(await nativeSlideActions.evaluate(
      (element) => element.parentElement.open,
    ))
  )
    await nativeSlideActions.click();
  const beforeNativeDiagram = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  const diagramButton = page.getByRole("button", {
    name: "Native diagrams",
    exact: true,
  });
  await diagramButton.click();
  const diagramDialog = page.getByRole("dialog", {
    name: /Native diagrams on slide/,
  });
  const diagramPreview = diagramDialog.getByRole("button", {
    name: "Preview native diagram",
    exact: true,
  });
  const diagramImage = diagramDialog.getByRole("img", {
    name: "Proposed native diagram",
    exact: true,
  });
  const diagramReview = diagramDialog.getByRole("checkbox", {
    name: "I reviewed this diagram on the current slide.",
    exact: true,
  });
  const diagramSave = diagramDialog.getByRole("button", {
    name: "Save reviewed native diagram",
    exact: true,
  });
  await diagramPreview.click();
  await diagramImage.waitFor();
  await diagramReview.check();
  await diagramDialog
    .getByRole("textbox", { name: "Diagram node 1", exact: true })
    .fill("Prepare the pilot");
  assert.equal(await diagramSave.isDisabled(), true);
  await diagramPreview.click();
  await diagramImage.waitFor();
  await diagramReview.check();
  await shot("workspace-native-diagram-process-review");
  await diagramDialog
    .getByRole("button", {
      name: "Discard native diagram preview",
      exact: true,
    })
    .click();
  await diagramDialog.waitFor({ state: "detached" });
  await revisionHistory
    .getByText(beforeNativeDiagram, { exact: true })
    .waitFor();
  await diagramButton.click();
  await diagramDialog
    .getByRole("combobox", { name: "Diagram structure", exact: true })
    .selectOption("hierarchy");
  await diagramDialog
    .getByRole("button", { name: "Add diagram node", exact: true })
    .click();
  await diagramDialog
    .getByRole("textbox", { name: "Diagram node 4", exact: true })
    .fill("Report the results");
  await diagramDialog
    .getByRole("combobox", { name: "Diagram parent 4", exact: true })
    .selectOption("node2");
  await diagramPreview.click();
  await diagramImage.waitFor();
  await diagramReview.check();
  await shot("workspace-native-diagram-hierarchy-review");
  assert.equal(
    await diagramDialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
    true,
  );
  await diagramSave.click();
  await diagramDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved the reviewed native diagram as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  const hierarchyDiagramHead = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  if (
    !(await nativeSlideActions.evaluate(
      (element) => element.parentElement.open,
    ))
  )
    await nativeSlideActions.click();
  await diagramButton.click();
  const diagramChoice = diagramDialog.getByRole("combobox", {
    name: "Native diagram",
    exact: true,
  });
  await page.waitForFunction(
    () =>
      document.querySelector('[aria-label="Native diagram"]')?.options.length >
      1,
  );
  await diagramChoice.selectOption({ index: 1 });
  assert.equal(
    await diagramDialog
      .getByRole("textbox", { name: "Diagram node 4", exact: true })
      .inputValue(),
    "Report the results",
  );
  await diagramDialog
    .getByRole("combobox", { name: "Diagram structure", exact: true })
    .selectOption("cycle");
  await diagramDialog
    .getByRole("button", { name: "Remove node 4", exact: true })
    .click();
  await diagramDialog
    .getByRole("combobox", { name: "Diagram palette", exact: true })
    .selectOption("midnight");
  await diagramDialog
    .getByRole("textbox", { name: "Diagram node 1", exact: true })
    .fill("Refine the pilot");
  await diagramPreview.click();
  await diagramImage.waitFor();
  await diagramReview.check();
  await shot("workspace-native-diagram-cycle-review");
  await diagramSave.click();
  await diagramDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved the reviewed native diagram as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  const cycleDiagramHead = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();

  if (
    !(await nativeSlideActions.evaluate(
      (element) => element.parentElement.open,
    ))
  )
    await nativeSlideActions.click();
  await diagramButton.click();
  await page.waitForFunction(
    () =>
      document.querySelector('[aria-label="Native diagram"]')?.options.length >
      1,
  );
  await diagramChoice.selectOption({ index: 1 });
  await diagramDialog
    .getByRole("button", { name: "Preview diagram deletion", exact: true })
    .click();
  await diagramImage.waitFor();
  await diagramReview.check();
  await shot("workspace-native-diagram-delete-review");
  await diagramSave.click();
  await diagramDialog.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved the reviewed native diagram as one revision and refreshed retrieval.",
      { exact: true },
    )
    .waitFor();
  for (const head of [
    cycleDiagramHead,
    hierarchyDiagramHead,
    beforeNativeDiagram,
  ]) {
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await revisionHistory.getByText(head, { exact: true }).waitFor();
  }
  checks.push(
    "Structured process diagram preview invalidates changed-label approval and discards without publication",
  );
  checks.push(
    "Structured hierarchy adds nodes and assigns earlier parents, renders native connections and saves one reviewed revision without dialog overflow",
  );
  checks.push(
    "Existing structured diagram reloads, converts to a cycle, removes a node, changes palette, saves, previews whole-diagram deletion and undoes all three complete revisions",
  );

  const beforeCopilotDiagram = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  const diagramPlan = page.getByRole("dialog", {
    name: "Copilot edit plan",
    exact: true,
  });
  await diagramPlan
    .getByRole("button", { name: "Dictate Copilot request", exact: true })
    .click();
  await diagramPlan
    .getByRole("button", { name: "Stop and review request", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Reviewed Copilot transcript", { exact: true })
    .fill("Add a three-step pilot diagram on a new slide.");
  await diagramPlan
    .getByRole("button", { name: "Use reviewed Copilot request", exact: true })
    .click();
  assert.equal(
    await diagramPlan
      .getByLabel("Copilot edit request", { exact: true })
      .inputValue(),
    "Add a three-step pilot diagram on a new slide.",
  );
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan
    .getByRole("img", { name: "Copilot proposed slide 1", exact: true })
    .waitFor();
  await diagramPlan
    .getByLabel("Proposed slide to review", { exact: true })
    .selectOption("2");
  await diagramPlan
    .getByRole("img", { name: "Copilot proposed slide 2", exact: true })
    .waitFor();
  await diagramPlan
    .getByText("Viewed 2 of 2 affected slides.", { exact: true })
    .waitFor();
  await diagramPlan.getByRole("checkbox").check();
  await shot("workspace-copilot-diagram-create-review");
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved Copilot's reviewed edits as one revision and refreshed slide text for retrieval.",
      { exact: true },
    )
    .waitFor();
  const createdCopilotDiagramHead = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  let convertedCopilotDiagramHead;
  for (const [request, shotName] of [
    [
      "Convert the pilot diagram into a cycle.",
      "workspace-copilot-diagram-convert-review",
    ],
    ["Remove the pilot diagram.", "workspace-copilot-diagram-delete-review"],
  ]) {
    await page
      .getByRole("button", { name: "Ask Copilot to edit", exact: true })
      .click();
    await diagramPlan
      .getByLabel("Copilot edit request", { exact: true })
      .fill(request);
    await diagramPlan
      .getByRole("button", { name: "Propose changes", exact: true })
      .click();
    await diagramPlan
      .getByRole("img", { name: "Copilot proposed slide 2", exact: true })
      .waitFor();
    await diagramPlan
      .getByText("Viewed 1 of 1 affected slides.", { exact: true })
      .waitFor();
    await diagramPlan.getByRole("checkbox").check();
    await shot(shotName);
    await diagramPlan
      .getByRole("button", { name: "Save Copilot changes", exact: true })
      .click();
    await diagramPlan.waitFor({ state: "detached" });
    await page
      .getByText(
        "Saved Copilot's reviewed edits as one revision and refreshed slide text for retrieval.",
        { exact: true },
      )
      .waitFor();
    if (request.startsWith("Convert")) {
      convertedCopilotDiagramHead = await revisionHistory
        .getByText(/Current · Revision \d+/, { exact: true })
        .innerText();
    }
  }
  for (const restoredHead of [
    convertedCopilotDiagramHead,
    createdCopilotDiagramHead,
    beforeCopilotDiagram,
  ]) {
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await revisionHistory.getByText(restoredHead, { exact: true }).waitFor();
  }
  checks.push(
    "Reviewed voice request proposes a native diagram on a newly created slide, requires both affected-slide previews, saves once and refreshes retrieval",
  );
  checks.push(
    "Copilot uses verified existing diagram structure to convert and delete a native diagram; reviewed saves and three whole-revision undos preserve the original deck",
  );

  const beforeRefinement = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Clarify this slide and its notes.");
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan.getByRole("img").waitFor();
  await diagramPlan
    .getByText("Viewed 1 of 1 affected slides.", { exact: true })
    .waitFor();
  await diagramPlan.getByRole("checkbox").check();
  const priorTitleProposal = await diagramPlan
    .getByText(/— reviewed$/, { exact: true })
    .first()
    .innerText();
  await diagramPlan
    .getByLabel("Copilot proposal refinement", { exact: true })
    .fill("Try a malformed refinement.");
  await diagramPlan
    .getByRole("button", { name: "Refine proposal", exact: true })
    .click();
  await diagramPlan.getByRole("alert").waitFor();
  await diagramPlan
    .getByText(priorTitleProposal, { exact: true })
    .first()
    .waitFor();
  await diagramPlan
    .getByText("Viewed 1 of 1 affected slides.", { exact: true })
    .waitFor();
  await diagramPlan
    .getByLabel("Copilot proposal refinement", { exact: true })
    .fill("");
  await diagramPlan.getByRole("checkbox").check();
  assert.equal(
    await diagramPlan
      .getByRole("button", { name: "Save Copilot changes", exact: true })
      .isEnabled(),
    true,
  );
  await shot("workspace-copilot-refinement-failed");
  await diagramPlan
    .getByRole("button", { name: "Check reasoning provider", exact: true })
    .click();
  await diagramPlan
    .getByText(
      "Provider check passed. You can retry refinement or review the previous proposal.",
      { exact: true },
    )
    .waitFor();
  await diagramPlan
    .getByLabel("Copilot proposal refinement", { exact: true })
    .fill("Keep the title change and make the notes more specific.");
  assert.equal(
    await diagramPlan
      .getByRole("button", { name: "Save Copilot changes", exact: true })
      .isEnabled(),
    false,
  );
  await diagramPlan
    .getByRole("button", { name: "Refine proposal", exact: true })
    .click();
  await diagramPlan
    .getByText("Review the refined title and specific pilot notes.", {
      exact: true,
    })
    .waitFor();
  await diagramPlan.getByRole("img").waitFor();
  await diagramPlan
    .getByText("Viewed 1 of 1 affected slides.", { exact: true })
    .waitFor();
  await diagramPlan
    .getByText(priorTitleProposal, { exact: true })
    .first()
    .waitFor();
  await diagramPlan
    .getByText("Name the pilot owner and review the outcome.", { exact: true })
    .waitFor();
  assert.equal(await diagramPlan.getByRole("checkbox").isChecked(), false);
  assert.equal(
    await diagramPlan
      .getByRole("button", { name: "Save Copilot changes", exact: true })
      .isEnabled(),
    false,
  );
  await shot("workspace-copilot-refinement-review");
  await diagramPlan.getByRole("checkbox").check();
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await page
    .getByText(
      "Saved Copilot's reviewed edits as one revision and refreshed slide text for retrieval.",
      { exact: true },
    )
    .waitFor();
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(beforeRefinement, { exact: true }).waitFor();
  checks.push(
    "Copilot refinement retains the unsaved title proposal, changes its notes and invalidates previous save approval until the replacement is viewed and acknowledged",
  );
  checks.push(
    "Refined Copilot proposal saves as one revision, refreshes retrieval and whole-revision undo restores the preceding presentation",
  );

  const beforeCopilotData = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(0)
    .click();
  const dataHeads = [];
  for (const [request, stage] of [
    ["Add a pilot metrics slide with a table and chart.", "create"],
    ["Update the pilot metrics values.", "update"],
    ["Expand the pilot table and chart with targets.", "expand"],
  ]) {
    await page
      .getByRole("button", { name: "Ask Copilot to edit", exact: true })
      .click();
    await diagramPlan
      .getByLabel("Copilot edit request", { exact: true })
      .fill(request);
    await diagramPlan
      .getByRole("button", { name: "Propose changes", exact: true })
      .click();
    await diagramPlan.getByRole("img").waitFor();
    if (stage === "create") {
      await diagramPlan
        .getByLabel("Proposed slide to review", { exact: true })
        .selectOption("2");
      await diagramPlan
        .getByRole("img", { name: "Copilot proposed slide 2", exact: true })
        .waitFor();
      await diagramPlan
        .getByText("Viewed 2 of 2 affected slides.", { exact: true })
        .waitFor();
    } else {
      await diagramPlan
        .getByText("Viewed 1 of 1 affected slides.", { exact: true })
        .waitFor();
    }
    const proposedTable = diagramPlan.getByRole("table", {
      name: "Proposed table cells",
      exact: true,
    });
    const proposedChart = diagramPlan.getByRole("table", {
      name: "Proposed chart values",
      exact: true,
    });
    await proposedTable
      .getByRole("cell", {
        name: stage === "create" ? "12.25" : "12.5",
        exact: true,
      })
      .waitFor();
    await proposedChart
      .getByRole("cell", {
        name: stage === "create" ? "12.25" : "12.5",
        exact: true,
      })
      .waitFor();
    if (stage !== "create") {
      const previous = diagramPlan.getByText("Previous table/chart data", {
        exact: true,
      });
      await previous.nth(0).click();
      await previous.nth(1).click();
      await diagramPlan
        .getByRole("table", { name: "Previous chart values", exact: true })
        .getByRole("cell", {
          name: stage === "update" ? "12.25" : "12.5",
          exact: true,
        })
        .waitFor();
      await diagramPlan
        .getByRole("table", { name: "Previous table cells", exact: true })
        .getByRole("cell", {
          name: stage === "update" ? "12.25" : "12.5",
          exact: true,
        })
        .waitFor();
    }
    if (stage === "expand") {
      await proposedChart
        .getByRole("columnheader", { name: "Cost", exact: true })
        .waitFor();
      await proposedChart
        .getByRole("rowheader", { name: "Target", exact: true })
        .waitFor();
      await proposedTable
        .getByRole("cell", { name: "Finance", exact: true })
        .waitFor();
    }
    await diagramPlan.getByRole("checkbox").check();
    await shot(`workspace-copilot-data-${stage}-review`);
    await diagramPlan
      .getByRole("button", { name: "Save Copilot changes", exact: true })
      .click();
    await diagramPlan.waitFor({ state: "detached" });
    await page
      .getByText(
        "Saved Copilot's reviewed edits as one revision and refreshed slide text for retrieval.",
        { exact: true },
      )
      .waitFor();
    dataHeads.push(
      await revisionHistory
        .getByText(/Current · Revision \d+/, { exact: true })
        .innerText(),
    );
    if (stage === "create")
      await page
        .getByRole("navigation", { name: "Presentation slides", exact: true })
        .getByRole("button")
        .nth(1)
        .click();
  }
  const legendDialog = page.getByRole("dialog", {
    name: "Chart legend on slide 2",
    exact: true,
  });
  const legendOpen = page.getByRole("button", {
    name: "Chart legend",
    exact: true,
  });
  const legendPreview = legendDialog.getByRole("button", {
    name: "Preview chart legend",
    exact: true,
  });
  const legendSave = legendDialog.getByRole("button", {
    name: "Save reviewed chart legend",
    exact: true,
  });
  async function openLegend() {
    await legendOpen.click();
    await legendDialog
      .getByText("Series: Revenue, Cost. Pie legends identify categories.", {
        exact: true,
      })
      .waitFor();
  }
  async function waitLegendImage() {
    await legendDialog
      .getByRole("img", { name: "Proposed chart legend", exact: true })
      .waitFor();
    await legendDialog
      .getByRole("checkbox", {
        name: "I reviewed this legend’s placement and the plot area.",
        exact: true,
      })
      .waitFor();
  }
  await openLegend();
  assert.equal(
    await legendDialog
      .getByLabel("Legend placement", { exact: true })
      .inputValue(),
    "hidden",
  );
  await legendDialog
    .getByLabel("Legend placement", { exact: true })
    .selectOption("bottom");
  await legendPreview.click();
  await waitLegendImage();
  await legendDialog
    .getByRole("checkbox", {
      name: "I reviewed this legend’s placement and the plot area.",
      exact: true,
    })
    .check();
  await legendDialog
    .getByLabel("Legend placement", { exact: true })
    .selectOption("right");
  assert.equal(await legendSave.isDisabled(), true);
  await legendPreview.click();
  await waitLegendImage();
  await legendDialog
    .getByRole("checkbox", {
      name: "I reviewed this legend’s placement and the plot area.",
      exact: true,
    })
    .check();
  await shot("workspace-chart-legend-right-review");
  await legendSave.click();
  await legendDialog.waitFor({ state: "detached" });
  await openLegend();
  assert.equal(
    await legendDialog
      .getByLabel("Legend placement", { exact: true })
      .inputValue(),
    "right",
  );
  await legendDialog
    .getByLabel("Legend placement", { exact: true })
    .selectOption("hidden");
  await legendPreview.click();
  await waitLegendImage();
  await legendDialog
    .getByRole("button", { name: "Discard chart legend preview", exact: true })
    .click();
  await legendDialog.waitFor({ state: "detached" });
  await openLegend();
  assert.equal(
    await legendDialog
      .getByLabel("Legend placement", { exact: true })
      .inputValue(),
    "right",
  );
  await legendDialog
    .getByRole("button", { name: "Discard chart legend preview", exact: true })
    .click();
  await legendDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Chart legend editor loads native settings, invalidates save after placement changes, saves the fresh reviewed right legend and undo restores the exact data revision",
  );
  checks.push(
    "Discarding a rendered hide-legend proposal leaves the saved right legend intact",
  );

  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Show a bottom legend for the pilot chart.");
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan.getByRole("img").waitFor();
  await diagramPlan
    .getByText("Proposed legend: bottom · does not overlay plot", {
      exact: true,
    })
    .waitFor();
  await diagramPlan
    .getByText("Previous legend settings", { exact: true })
    .click();
  await diagramPlan
    .getByText("Previous legend: hidden · does not overlay plot", {
      exact: true,
    })
    .waitFor();
  await diagramPlan.getByRole("checkbox").check();
  await shot("workspace-copilot-chart-legend-review");
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await openLegend();
  assert.equal(
    await legendDialog
      .getByLabel("Legend placement", { exact: true })
      .inputValue(),
    "bottom",
  );
  await legendDialog
    .getByRole("button", { name: "Discard chart legend preview", exact: true })
    .click();
  await legendDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Copilot reviews exact previous/proposed legend placement, saves a native bottom legend and undo restores the exact expanded data revision",
  );

  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  const colorDialog = page.getByRole("dialog", {
    name: "Chart colors on slide 2",
    exact: true,
  });
  const colorPreview = colorDialog.getByRole("button", {
    name: "Preview chart color",
    exact: true,
  });
  const colorSave = colorDialog.getByRole("button", {
    name: "Save reviewed chart color",
    exact: true,
  });
  async function openColors() {
    await page
      .getByRole("button", { name: "Chart colors", exact: true })
      .click();
    await colorDialog
      .getByLabel("Color series", { exact: true })
      .getByRole("option", { name: "Revenue", exact: true })
      .waitFor({ state: "attached" });
  }
  async function reviewColor() {
    await colorPreview.click();
    await colorDialog
      .getByRole("img", { name: "Proposed chart color", exact: true })
      .waitFor();
    await colorDialog
      .getByRole("checkbox", {
        name: "I reviewed this color and the chart legend.",
        exact: true,
      })
      .check();
  }
  await openColors();
  await colorDialog
    .getByLabel("Chart RGB color", { exact: true })
    .fill("#13579b");
  await reviewColor();
  await colorDialog
    .getByLabel("Chart RGB color", { exact: true })
    .fill("#6a2eb5");
  assert.equal(await colorSave.isDisabled(), true);
  await reviewColor();
  await shot("workspace-chart-color-series-review");
  await colorSave.click();
  await colorDialog.waitFor({ state: "detached" });
  await openColors();
  await colorDialog
    .getByText("Current fill: #6A2EB5.", { exact: true })
    .waitFor();
  await colorDialog
    .getByLabel("Color series", { exact: true })
    .selectOption("1");
  await colorDialog
    .getByLabel("Color data point", { exact: true })
    .selectOption("1");
  await colorDialog
    .getByLabel("Chart RGB color", { exact: true })
    .fill("#d63621");
  await reviewColor();
  await shot("workspace-chart-color-point-review");
  await colorDialog
    .getByRole("button", { name: "Discard chart color preview", exact: true })
    .click();
  await colorDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Native chart colors target series and individual data points, require fresh preview after RGB changes, retain reviewed series color after reopen and undo the exact saved revision",
  );
  checks.push(
    "A native point-color preview can be rendered and reviewed then discarded without saving",
  );
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Recolor the pilot chart.");
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan.getByRole("img").waitFor();
  await diagramPlan
    .getByText("Proposed chart color: series 1, entire series · #6A2EB5", {
      exact: true,
    })
    .waitFor();
  await diagramPlan
    .getByText("Proposed chart color: series 2, point 2 · #D63621", {
      exact: true,
    })
    .waitFor();
  await diagramPlan
    .getByText("Previous chart color", { exact: true })
    .nth(0)
    .click();
  await diagramPlan
    .getByText("Previous chart color: series 1, entire series · #2563EB", {
      exact: true,
    })
    .waitFor();
  await diagramPlan.getByRole("checkbox").check();
  await shot("workspace-copilot-chart-colors-review");
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await openColors();
  await colorDialog
    .getByText("Current fill: #6A2EB5.", { exact: true })
    .waitFor();
  await colorDialog
    .getByLabel("Color series", { exact: true })
    .selectOption("1");
  await colorDialog
    .getByLabel("Color data point", { exact: true })
    .selectOption("1");
  await colorDialog
    .getByText("Current fill: #D63621.", { exact: true })
    .waitFor();
  await colorDialog
    .getByRole("button", { name: "Discard chart color preview", exact: true })
    .click();
  await colorDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Copilot composes series and point color edits with staged previous RGB review, native preview, whole-revision save and exact undo",
  );

  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  const formatDialog = page.getByRole("dialog", {
    name: "Table formatting on slide 2",
    exact: true,
  });
  async function openTableFormat() {
    await page
      .getByRole("button", { name: "Table formatting", exact: true })
      .click();
    await page.waitForFunction(
      () =>
        document
          .querySelector('select[aria-label="Table bold"]')
          ?.closest("fieldset")?.disabled === false,
    );
  }
  const formatPreview = formatDialog.getByRole("button", {
    name: "Preview table formatting",
    exact: true,
  });
  const formatSave = formatDialog.getByRole("button", {
    name: "Save reviewed table formatting",
    exact: true,
  });
  async function reviewTableFormat() {
    await formatDialog
      .getByRole("img", { name: "Proposed table formatting", exact: true })
      .waitFor();
    await formatDialog
      .getByRole("checkbox", {
        name: "I reviewed these cell styles and text fit.",
        exact: true,
      })
      .check();
  }
  await openTableFormat();
  await formatDialog
    .getByLabel("Table bold", { exact: true })
    .selectOption("true");
  await formatDialog
    .getByLabel("Apply table fill color", { exact: true })
    .check();
  await formatDialog
    .getByLabel("Table fill RGB", { exact: true })
    .fill("#6a2eb5");
  await formatDialog
    .getByLabel("Table horizontal alignment", { exact: true })
    .selectOption("center");
  await formatPreview.click();
  await reviewTableFormat();
  await formatDialog
    .getByLabel("Table fill RGB", { exact: true })
    .fill("#224466");
  assert.equal(await formatSave.isDisabled(), true);
  await formatPreview.click();
  await reviewTableFormat();
  await shot("workspace-table-format-header-review");
  await formatSave.click();
  await formatDialog.waitFor({ state: "detached" });
  const formatHead = await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .innerText();
  await openTableFormat();
  await formatDialog
    .getByRole("button", { name: "Entire table", exact: true })
    .click();
  assert.equal(
    await formatDialog
      .getByLabel("Formatting last row", { exact: true })
      .inputValue(),
    "3",
  );
  await formatDialog
    .getByLabel("Table italic", { exact: true })
    .selectOption("true");
  await formatPreview.click();
  await reviewTableFormat();
  await formatDialog
    .getByRole("button", {
      name: "Discard table formatting preview",
      exact: true,
    })
    .click();
  await formatDialog.waitFor({ state: "detached" });
  await revisionHistory.getByText(formatHead, { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Native table header formatting requires fresh review after style changes, saves as one revision and exact undo preserves expanded data",
  );
  checks.push(
    "Whole-table formatting preview is discardable without changing the saved header or text",
  );
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Style the pilot table header.");
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan.getByRole("img").waitFor();
  await diagramPlan
    .getByText("Previous cell formatting", { exact: true })
    .nth(0)
    .click();
  await diagramPlan
    .getByRole("table")
    .filter({
      has: page.getByText("Previous cell formatting", { exact: true }),
    })
    .first()
    .waitFor();
  await diagramPlan.getByRole("checkbox").check();
  await shot("workspace-copilot-table-format-review");
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Copilot reviews exact prior cell formatting and inclusive ranges, saves header/body alignment together and undo restores the exact data revision",
  );

  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  const labelsDialog = page.getByRole("dialog", {
    name: "Chart labels on slide 2",
    exact: true,
  });
  async function openChartLabels() {
    await page
      .getByRole("button", { name: "Chart labels", exact: true })
      .click();
    await labelsDialog
      .getByLabel("Label series", { exact: true })
      .getByRole("option", { name: "Revenue", exact: true })
      .waitFor({ state: "attached" });
  }
  const labelsPreview = labelsDialog.getByRole("button", {
    name: "Preview chart labels",
    exact: true,
  });
  const labelsSave = labelsDialog.getByRole("button", {
    name: "Save reviewed chart labels",
    exact: true,
  });
  async function reviewChartLabels() {
    await labelsDialog
      .getByRole("img", { name: "Proposed chart labels", exact: true })
      .waitFor();
    await labelsDialog
      .getByRole("checkbox", {
        name: "I reviewed these labels and the plot area.",
        exact: true,
      })
      .check();
  }
  await openChartLabels();
  await labelsDialog
    .getByLabel("Label series", { exact: true })
    .selectOption("all");
  await labelsDialog
    .getByLabel("Label placement", { exact: true })
    .selectOption("outside_end");
  await labelsDialog
    .getByLabel("Apply label number format", { exact: true })
    .check();
  await labelsDialog
    .getByLabel("Label number format", { exact: true })
    .fill("0.0");
  await labelsPreview.click();
  await reviewChartLabels();
  await labelsDialog
    .getByLabel("Label number format", { exact: true })
    .fill("0.00");
  assert.equal(await labelsSave.isDisabled(), true);
  await labelsPreview.click();
  await reviewChartLabels();
  await shot("workspace-chart-labels-review");
  await labelsSave.click();
  await labelsDialog.waitFor({ state: "detached" });
  await openChartLabels();
  await labelsDialog
    .getByText(/Current labels for Revenue: outside end.*format 0.00/)
    .waitFor();
  await labelsDialog
    .getByLabel("Label placement", { exact: true })
    .selectOption("hidden");
  await labelsPreview.click();
  await reviewChartLabels();
  await labelsDialog
    .getByRole("button", { name: "Discard chart labels preview", exact: true })
    .click();
  await labelsDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Native chart labels edit all series, require fresh review after number format changes, reopen saved settings and undo the exact data revision",
  );
  checks.push(
    "A rendered hide-label proposal can be reviewed and discarded without saving",
  );
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Label the pilot chart values.");
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan.getByRole("img").waitFor();
  await diagramPlan
    .getByText("Proposed chart labels: all series · outside end", {
      exact: true,
    })
    .waitFor();
  await diagramPlan
    .locator("summary")
    .filter({ hasText: "Previous chart labels" })
    .nth(1)
    .click();
  await diagramPlan.getByText(/outside end · value on.*format 0.0/).waitFor();
  await diagramPlan.getByRole("checkbox").check();
  await shot("workspace-copilot-chart-labels-review");
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await openChartLabels();
  await labelsDialog
    .getByText(/Current labels for Revenue: inside end.*format 0.0/)
    .waitFor();
  await labelsDialog
    .getByRole("button", { name: "Discard chart labels preview", exact: true })
    .click();
  await labelsDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Copilot reviews actual staged previous labels, composes all-series and single-series placements, saves one revision and undoes the exact data head",
  );

  const axesDialog = page.getByRole("dialog", {
    name: "Chart axes on slide 2",
    exact: true,
  });
  async function openAxes() {
    await page
      .getByRole("navigation", { name: "Presentation slides", exact: true })
      .getByRole("button")
      .nth(1)
      .click();
    await page.getByRole("button", { name: "Chart axes", exact: true }).click();
    await axesDialog.waitFor();
    await axesDialog
      .getByLabel("Axis kind", { exact: true })
      .getByRole("option", { name: "Value axis", exact: true })
      .waitFor({ state: "attached" });
  }
  await openAxes();
  await axesDialog.getByLabel("Replace axis title", { exact: true }).check();
  await axesDialog
    .getByLabel("Axis title", { exact: true })
    .fill("Revenue ($)");
  for (const [field, value] of [
    ["minimum", "0"],
    ["maximum", "30"],
    ["major unit", "5"],
    ["minor unit", "1"],
  ])
    await axesDialog.getByLabel(`Axis ${field}`, { exact: true }).fill(value);
  await axesDialog
    .getByLabel("Apply axis number format", { exact: true })
    .check();
  await axesDialog
    .getByLabel("Axis number format", { exact: true })
    .fill("$0.0");
  await axesDialog
    .getByRole("button", { name: "Preview chart axes", exact: true })
    .click();
  await axesDialog
    .getByRole("img", { name: "Proposed chart axes", exact: true })
    .waitFor();
  await axesDialog
    .getByRole("checkbox", {
      name: "I reviewed these axes and the plot area.",
      exact: true,
    })
    .check();
  await axesDialog.getByLabel("Axis maximum", { exact: true }).fill("35");
  assert.equal(
    await axesDialog
      .getByRole("button", { name: "Save reviewed chart axes", exact: true })
      .isDisabled(),
    true,
  );
  await axesDialog.getByLabel("Axis maximum", { exact: true }).fill("30");
  await axesDialog
    .getByRole("button", { name: "Preview chart axes", exact: true })
    .click();
  await axesDialog
    .getByRole("img", { name: "Proposed chart axes", exact: true })
    .waitFor();
  await axesDialog
    .getByRole("checkbox", {
      name: "I reviewed these axes and the plot area.",
      exact: true,
    })
    .check();
  await shot("workspace-chart-axes-review");
  await axesDialog
    .getByRole("button", { name: "Save reviewed chart axes", exact: true })
    .click();
  await axesDialog.waitFor({ state: "detached" });
  await openAxes();
  assert.equal(
    await axesDialog.getByLabel("Axis maximum", { exact: true }).inputValue(),
    "30",
  );
  assert.equal(
    await axesDialog.getByLabel("Axis title", { exact: true }).inputValue(),
    "Revenue ($)",
  );
  assert.equal(
    await axesDialog
      .getByLabel("Axis number format", { exact: true })
      .inputValue(),
    "$0.0",
  );
  await axesDialog
    .getByLabel("Axis kind", { exact: true })
    .selectOption("category");
  assert.equal(
    await axesDialog.getByLabel("Axis maximum", { exact: true }).count(),
    0,
  );
  await axesDialog.getByLabel("Show axis", { exact: true }).uncheck();
  await axesDialog
    .getByRole("button", { name: "Preview chart axes", exact: true })
    .click();
  await axesDialog
    .getByRole("img", { name: "Proposed chart axes", exact: true })
    .waitFor();
  await axesDialog
    .getByRole("button", { name: "Discard chart axes preview", exact: true })
    .click();
  await axesDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Chart axes preview range, units, title and currency; changing settings invalidates review; save/reopen, category-axis discard and exact undo work",
  );
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Set the pilot chart axes.");
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan.getByRole("img").waitFor();
  await diagramPlan
    .locator("summary")
    .filter({ hasText: "Previous chart axis" })
    .nth(1)
    .click();
  await diagramPlan.getByText(/Previous value axis:.*bounds 0 to 30/).waitFor();
  await diagramPlan.getByRole("checkbox").check();
  await shot("workspace-copilot-chart-axes-review");
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await openAxes();
  assert.equal(
    await axesDialog.getByLabel("Axis maximum", { exact: true }).inputValue(),
    "",
  );
  assert.equal(
    await axesDialog.getByLabel("Axis title", { exact: true }).inputValue(),
    "Revenue ($)",
  );
  assert.equal(
    await axesDialog
      .getByLabel("Axis number format", { exact: true })
      .inputValue(),
    "$0.0",
  );
  await axesDialog
    .getByRole("button", { name: "Discard chart axes preview", exact: true })
    .click();
  await axesDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Copilot axis operations show staged previous bounds, restore automatic scaling while retaining title/format, save one revision and undo the data head",
  );

  const bordersDialog = page.getByRole("dialog", {
    name: "Table borders on slide 2",
    exact: true,
  });
  async function openBorders() {
    await page
      .getByRole("navigation", { name: "Presentation slides", exact: true })
      .getByRole("button")
      .nth(1)
      .click();
    await page
      .getByRole("button", { name: "Table borders", exact: true })
      .click();
    await bordersDialog.waitFor();
    await bordersDialog
      .getByLabel("Borders table", { exact: true })
      .getByRole("option")
      .first()
      .waitFor({ state: "attached" });
  }
  await openBorders();
  await bordersDialog
    .getByRole("button", { name: "Entire table", exact: true })
    .click();
  await bordersDialog
    .getByLabel("Border edges", { exact: true })
    .selectOption("all");
  await bordersDialog
    .getByLabel("Border line style", { exact: true })
    .selectOption("dash");
  await bordersDialog.getByLabel("Border width", { exact: true }).fill("3");
  await bordersDialog.getByLabel("Border RGB", { exact: true }).fill("#A12266");
  await bordersDialog
    .getByRole("button", { name: "Preview table borders", exact: true })
    .click();
  await bordersDialog
    .getByRole("img", { name: "Proposed table borders", exact: true })
    .waitFor();
  await bordersDialog
    .getByRole("checkbox", {
      name: "I reviewed the selected range and shared border edges.",
      exact: true,
    })
    .check();
  await bordersDialog
    .getByLabel("Border edges", { exact: true })
    .selectOption("outline");
  assert.equal(
    await bordersDialog
      .getByRole("button", { name: "Save reviewed table borders", exact: true })
      .isDisabled(),
    true,
  );
  await bordersDialog
    .getByLabel("Border edges", { exact: true })
    .selectOption("all");
  await bordersDialog
    .getByRole("button", { name: "Preview table borders", exact: true })
    .click();
  await bordersDialog.getByRole("img").waitFor();
  await bordersDialog
    .getByRole("checkbox", {
      name: "I reviewed the selected range and shared border edges.",
      exact: true,
    })
    .check();
  await shot("workspace-table-borders-review");
  await bordersDialog
    .getByRole("button", { name: "Save reviewed table borders", exact: true })
    .click();
  await bordersDialog.waitFor({ state: "detached" });
  await openBorders();
  await bordersDialog
    .getByText("dash · 3 pt · #A12266", { exact: true })
    .first()
    .waitFor();
  await bordersDialog
    .getByRole("button", { name: "Entire table", exact: true })
    .click();
  await bordersDialog
    .getByLabel("Border line style", { exact: true })
    .selectOption("none");
  assert.equal(
    await bordersDialog
      .getByLabel("Border width", { exact: true })
      .isDisabled(),
    true,
  );
  await bordersDialog
    .getByRole("button", { name: "Preview table borders", exact: true })
    .click();
  await bordersDialog.getByRole("img").waitFor();
  await bordersDialog
    .getByRole("button", { name: "Discard table borders preview", exact: true })
    .click();
  await bordersDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Range borders review all dashed edges, invalidate stale review, reopen native styles, discard removal and undo the exact data head",
  );
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Style the pilot table borders.");
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan.getByRole("img").waitFor();
  await diagramPlan
    .getByText(/Proposed table borders:.*inside.*remove/)
    .waitFor();
  await diagramPlan
    .locator("summary")
    .filter({ hasText: "Previous border edges" })
    .nth(1)
    .click();
  await diagramPlan.getByText("#A12266", { exact: true }).first().waitFor();
  await diagramPlan.getByRole("checkbox").check();
  await shot("workspace-copilot-table-borders-review");
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await openBorders();
  await bordersDialog.getByText("Removed", { exact: true }).first().waitFor();
  await bordersDialog
    .getByText("solid · 3 pt · #A12266", { exact: true })
    .first()
    .waitFor();
  await bordersDialog
    .getByRole("button", { name: "Discard table borders preview", exact: true })
    .click();
  await bordersDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Copilot border operations review staged reciprocal edges, retain the outline while removing interior lines, save one revision and undo",
  );

  async function openMerge() {
    await page
      .getByRole("navigation", { name: "Presentation slides", exact: true })
      .getByRole("button")
      .nth(1)
      .click();
    await page
      .getByRole("button", { name: "Merge or split table cells", exact: true })
      .click();
    const modal = page.getByRole("dialog", {
      name: "Merge or split table cells on slide 2",
      exact: true,
    });
    await modal.waitFor();
    await modal
      .getByLabel("Merge table", { exact: true })
      .locator("option")
      .first()
      .waitFor({ state: "attached" });
    return modal;
  }
  let mergeDialog = await openMerge();
  await mergeDialog.getByLabel("Merge last column", { exact: true }).fill("2");
  await mergeDialog
    .getByRole("button", { name: "Preview table merge", exact: true })
    .click();
  await mergeDialog.getByRole("img").waitFor();
  await mergeDialog
    .getByRole("checkbox", {
      name: "I reviewed the merged cells, text distribution and layout.",
      exact: true,
    })
    .check();
  await mergeDialog
    .getByLabel("Merge action", { exact: true })
    .selectOption("split");
  assert.equal(
    await mergeDialog
      .getByRole("button", { name: "Save reviewed table merge", exact: true })
      .isDisabled(),
    true,
  );
  await mergeDialog
    .getByLabel("Merge action", { exact: true })
    .selectOption("merge");
  await mergeDialog
    .getByRole("button", { name: "Preview table merge", exact: true })
    .click();
  await mergeDialog.getByRole("img").waitFor();
  await mergeDialog
    .getByRole("checkbox", {
      name: "I reviewed the merged cells, text distribution and layout.",
      exact: true,
    })
    .check();
  await shot("workspace-table-merge-review");
  await mergeDialog
    .getByRole("button", { name: "Save reviewed table merge", exact: true })
    .click();
  await mergeDialog.waitFor({ state: "detached" });
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("button", { name: "Native tables", exact: true })
    .click();
  const cellsDialog = page.getByRole("dialog", {
    name: "Native tables on slide 2",
    exact: true,
  });
  await cellsDialog
    .getByLabel("Native table", { exact: true })
    .locator("option")
    .nth(1)
    .waitFor({ state: "attached" });
  await cellsDialog
    .getByLabel("Native table", { exact: true })
    .selectOption({ index: 1 });
  assert.equal(
    await cellsDialog
      .getByLabel("Row 1, column 2", { exact: true })
      .isDisabled(),
    true,
  );
  await cellsDialog
    .getByLabel("Row 1, column 1", { exact: true })
    .fill("Metric\nCurrent reviewed");
  await cellsDialog
    .getByRole("button", { name: "Preview native table", exact: true })
    .click();
  await cellsDialog.getByRole("img").waitFor();
  await cellsDialog
    .getByRole("button", { name: "Discard native table preview", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Native merge review invalidates changed actions, saves merged spans, keeps top-left text editable and covered cells disabled, discards text changes and undoes exact head",
  );
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Merge then split the pilot table header.");
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan.getByRole("img").waitFor();
  await diagramPlan
    .locator("summary")
    .filter({ hasText: "Previous table/chart data" })
    .nth(1)
    .click();
  await diagramPlan
    .getByText(/Previous merged cells: row 1, column 1: 1 × 2/)
    .waitFor();
  await diagramPlan.getByRole("checkbox").check();
  await shot("workspace-copilot-table-merge-review");
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Copilot merge then split reviews actual staged spans and combined text, saves one revision and restores the exact prior package",
  );

  async function openTableFit() {
    await page
      .getByRole("navigation", { name: "Presentation slides", exact: true })
      .getByRole("button")
      .nth(1)
      .click();
    await page
      .getByRole("button", { name: "Auto-fit table rows", exact: true })
      .click();
    const modal = page.getByRole("dialog", {
      name: "Auto-fit table rows on slide 2",
      exact: true,
    });
    await modal.waitFor();
    await modal
      .getByLabel("Fit table", { exact: true })
      .locator("option")
      .first()
      .waitFor({ state: "attached" });
    await modal.getByRole("table").getByRole("cell").first().waitFor();
    return modal;
  }
  let fitDialog = await openTableFit();
  const originalFitText = await fitDialog.getByRole("table").innerText();
  await fitDialog
    .getByLabel("Table fit strategy", { exact: true })
    .selectOption("compact");
  await fitDialog
    .getByRole("button", { name: "Preview table fit", exact: true })
    .click();
  await fitDialog.getByRole("img").waitFor();
  await fitDialog
    .getByRole("checkbox", {
      name: "I reviewed the fitted rows, text fit and nearby content.",
      exact: true,
    })
    .check();
  await fitDialog
    .getByLabel("Table fit strategy", { exact: true })
    .selectOption("grow");
  assert.equal(
    await fitDialog
      .getByRole("button", { name: "Save reviewed table fit", exact: true })
      .isDisabled(),
    true,
  );
  await fitDialog
    .getByLabel("Table fit strategy", { exact: true })
    .selectOption("compact");
  await fitDialog
    .getByRole("button", { name: "Preview table fit", exact: true })
    .click();
  await fitDialog.getByRole("img").waitFor();
  await fitDialog.getByRole("checkbox").check();
  await shot("workspace-table-fit-review");
  await fitDialog
    .getByRole("button", { name: "Save reviewed table fit", exact: true })
    .click();
  await fitDialog.waitFor({ state: "detached" });
  fitDialog = await openTableFit();
  assert.notEqual(
    await fitDialog.getByRole("table").innerText(),
    originalFitText,
  );
  await fitDialog
    .getByRole("button", { name: "Discard table fit preview", exact: true })
    .click();
  await fitDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Native table fit invalidates changed strategies, previews compact rows, saves and reopens changed heights, discards and restores the exact prior head",
  );
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Fit the pilot table rows.");
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan.getByRole("img").waitFor();
  const fitPrevious = diagramPlan
    .locator("summary")
    .filter({ hasText: "Previous table/chart data" });
  await fitPrevious.nth(0).click();
  await fitPrevious.nth(1).click();
  await diagramPlan.getByRole("checkbox").check();
  await shot("workspace-copilot-table-fit-review");
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Copilot compact then grow reviews staged row heights, previews measured fit, saves one revision and restores the exact prior head",
  );

  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await studioPanel("Objects");
  await page
    .getByRole("textbox", { name: "New text box text", exact: true })
    .fill(
      "A reviewed pilot needs careful measurement before a decision. ".repeat(
        4,
      ),
    );
  await page.getByRole("button", { name: "Add text box", exact: true }).click();
  await page
    .locator(".pw-slide-column .pw-notice")
    .getByText(/Added a text box in revision/)
    .waitFor();
  const textFitHead = await revisionHistory
    .getByText(/Current · Revision/)
    .innerText();
  async function openTextFit() {
    await page
      .getByRole("navigation", { name: "Presentation slides", exact: true })
      .getByRole("button")
      .nth(1)
      .click();

    await page
      .getByRole("button", { name: "Fit text box", exact: true })
      .click();
    const modal = page.getByRole("dialog", {
      name: "Fit text box on slide 2",
      exact: true,
    });
    await modal.waitFor();
    const target = modal.getByLabel("Fit text box", { exact: true });
    await target
      .locator("option")
      .filter({ hasText: /^Text Box/ })
      .last()
      .waitFor({ state: "attached" });
    await target.selectOption(
      await target
        .locator("option")
        .filter({ hasText: /^Text Box/ })
        .last()
        .getAttribute("value"),
    );
    await modal.getByRole("table").getByRole("cell").first().waitFor();
    return modal;
  }
  let textFitDialog = await openTextFit();
  const originalFonts = await textFitDialog.getByRole("table").innerText();
  await textFitDialog
    .getByLabel("Text fit strategy", { exact: true })
    .selectOption("shrink");
  await textFitDialog
    .getByLabel("Minimum text fit size", { exact: true })
    .fill("6");
  await textFitDialog
    .getByRole("button", { name: "Preview text fit", exact: true })
    .click();
  await textFitDialog.getByRole("img").waitFor();
  await textFitDialog.getByRole("checkbox").check();
  await textFitDialog
    .getByLabel("Minimum text fit size", { exact: true })
    .fill("7");
  assert.equal(
    await textFitDialog
      .getByRole("button", { name: "Save reviewed text fit", exact: true })
      .isDisabled(),
    true,
  );
  await textFitDialog
    .getByLabel("Minimum text fit size", { exact: true })
    .fill("6");
  await textFitDialog
    .getByRole("button", { name: "Preview text fit", exact: true })
    .click();
  await textFitDialog.getByRole("img").waitFor();
  await textFitDialog.getByRole("checkbox").check();
  await shot("workspace-text-fit-review");
  await textFitDialog
    .getByRole("button", { name: "Save reviewed text fit", exact: true })
    .click();
  await textFitDialog.waitFor({ state: "detached" });
  textFitDialog = await openTextFit();
  assert.notEqual(
    await textFitDialog.getByRole("table").innerText(),
    originalFonts,
  );
  await textFitDialog
    .getByRole("button", { name: "Discard text fit preview", exact: true })
    .click();
  await textFitDialog.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(textFitHead, { exact: true }).waitFor();
  textFitDialog = await openTextFit();
  await textFitDialog
    .getByRole("button", { name: "Preview text fit", exact: true })
    .click();
  await textFitDialog.getByRole("img").waitFor();
  await textFitDialog
    .getByLabel("Text fit strategy", { exact: true })
    .selectOption("shrink");
  assert.equal(
    await textFitDialog
      .getByRole("button", { name: "Save reviewed text fit", exact: true })
      .isDisabled(),
    true,
  );
  await textFitDialog
    .getByRole("button", { name: "Discard text fit preview", exact: true })
    .click();
  await textFitDialog.waitFor({ state: "detached" });
  await revisionHistory.getByText(textFitHead, { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Direct text fitting previews grow/shrink, invalidates minimum/strategy changes, saves/reopens fitted fonts, discards and restores the exact prior head",
  );
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .nth(1)
    .click();
  await page
    .getByRole("button", { name: "Ask Copilot to edit", exact: true })
    .click();
  await diagramPlan
    .getByLabel("Copilot edit request", { exact: true })
    .fill("Fit the pilot text box.");
  await diagramPlan
    .getByRole("button", { name: "Propose changes", exact: true })
    .click();
  await diagramPlan.getByRole("img").waitFor();
  const textPrevious = diagramPlan
    .locator("summary")
    .filter({ hasText: "Previous text fitting" });
  await textPrevious.nth(0).click();
  await textPrevious.nth(1).click();
  assert.notEqual(
    await textPrevious.nth(0).locator("..").getByRole("table").innerText(),
    await textPrevious.nth(1).locator("..").getByRole("table").innerText(),
  );
  await diagramPlan.getByRole("checkbox").check();
  await shot("workspace-copilot-text-fit-review");
  await diagramPlan
    .getByRole("button", { name: "Save Copilot changes", exact: true })
    .click();
  await diagramPlan.waitFor({ state: "detached" });
  await page
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory.getByText(dataHeads[2], { exact: true }).waitFor();
  checks.push(
    "Copilot creates and constrains a text box then reviews actual staged shrink/grow fonts, saves one revision and restores the exact prior head",
  );

  for (const restored of [dataHeads[1], dataHeads[0], beforeCopilotData]) {
    await page
      .getByRole("button", { name: "Undo last presentation edit", exact: true })
      .click();
    await revisionHistory.getByText(restored, { exact: true }).waitFor();
  }
  checks.push(
    "Copilot creates an authored slide with native table and chart, requires both slide previews and exposes exact proposed cells and numeric series values before reviewed save",
  );
  checks.push(
    "Copilot updates existing table cells and chart values together while showing the exact staged previous data for review",
  );
  checks.push(
    "Copilot adds table rows/columns and chart categories/series using native structural edits; exact expanded data and previous data remain reviewable",
  );
  checks.push(
    "Three native data proposals save and re-index as whole revisions, and three undos restore their exact prior heads",
  );

  await page
    .getByRole("button", { name: "Quarterly strategy review", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Quarterly strategy review", exact: true })
    .first()
    .waitFor();
  await navigate("Workspace");
  const footnoteDeck = page.getByLabel("Workspace presentation", {
    exact: true,
  });
  const originalDeckOption = footnoteDeck
    .locator("option")
    .filter({ hasText: /^presentation\.pptx/ })
    .first();
  await originalDeckOption.waitFor({ state: "attached" });
  await footnoteDeck.selectOption(
    await originalDeckOption.getAttribute("value"),
  );
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await revisionHistory
    .getByText(/Current · Revision \d+/, { exact: true })
    .waitFor();
  await studioPanel("History");
  if (
    !(await revisionHistory
      .getByText("Current · Revision 1", { exact: true })
      .count())
  )
    await revisionHistory
      .getByRole("button", { name: "Restore revision 1", exact: true })
      .click();
  await revisionHistory
    .getByText("Current · Revision 1", { exact: true })
    .waitFor();
  await page
    .getByRole("navigation", { name: "Presentation slides", exact: true })
    .getByRole("button")
    .first()
    .click();
  await studioPanel("Purpose");
  await claimReview
    .getByText("1 claim · 1 supported · 0 need review", { exact: true })
    .waitFor();
  const footnoteDialog = page.getByRole("dialog", {
    name: "Reviewed evidence footnotes",
    exact: true,
  });
  const openFootnotes = claimReview.getByRole("button", {
    name: "Add evidence footnotes",
    exact: true,
  });
  const previewFootnotes = footnoteDialog.getByRole("button", {
    name: "Preview footnotes",
    exact: true,
  });
  const saveFootnotes = footnoteDialog.getByRole("button", {
    name: "Save reviewed footnotes",
    exact: true,
  });
  const footnoteImage = footnoteDialog.getByRole("img", {
    name: "Proposed evidence footnotes",
    exact: true,
  });
  const footnoteAck = footnoteDialog.getByRole("checkbox", {
    name: "I reviewed the citation labels and placement",
    exact: true,
  });
  await openFootnotes.click();
  await previewFootnotes.click();
  await footnoteImage.waitFor();
  let nativeFootnoteBaseline;
  let nativeFootnoteReceipt;
  async function footnoteHead() {
    return page.evaluate(async () => {
      const projects = await window.presenterCopilot.core.request(
        "project.list",
        {},
      );
      const project = projects.result.projects.find(
        (item) => item.name === "Quarterly strategy review",
      );
      const sources = await window.presenterCopilot.core.request(
        "source.list",
        { project_id: project.id },
      );
      const document = sources.result.sources.find(
        (item) => item.original_name === "presentation.pptx",
      );
      const scope = { project_id: project.id, document_id: document.id };
      const opened = await window.presenterCopilot.core.request(
        "presentation.workspace.open_source",
        scope,
      );
      if (!opened.ok) throw new Error("Footnote head unavailable");
      await window.presenterCopilot.core.request(
        "presentation.workspace.close_source",
        { ...scope, session_id: opened.result.session_id },
      );
      return {
        revisionId: opened.result.revision_id,
        sha256: opened.result.sha256,
      };
    });
  }
  async function nativeFootnoteReady() {
    await footnoteDialog
      .getByRole("button", { name: "PowerPoint appearance", exact: true })
      .click();
    await footnoteDialog
      .getByText(
        "Proposed slide appearance from PowerPoint. Changes are not saved.",
        { exact: true },
      )
      .waitFor({ timeout: 125_000 });
    await page.waitForFunction(() => {
      const image = document.querySelector(
        'dialog[open] img[alt="Proposed evidence footnotes"]',
      );
      return image?.complete && image.naturalWidth === 960;
    });
    nativeFootnoteReceipt = await app.evaluate(
      () => globalThis.ownedFootnoteReceipt,
    );
    assert.equal(nativeFootnoteReceipt.target.slide_number, 1);
    assert.equal(await footnoteAck.isChecked(), false);
  }
  if (nativeFootnoteReview) {
    nativeFootnoteBaseline = await footnoteHead();
    await app.evaluate(
      (_electron, filename) => {
        const module = process.mainModule.require(filename);
        const original = module.renderNativeEditAppearance;
        globalThis.ownedFootnoteHold = true;
        globalThis.ownedFootnoteReady = false;
        globalThis.ownedFootnotePending = false;
        module.renderNativeEditAppearance = async (...args) => {
          globalThis.ownedFootnotePending = true;
          try {
            const result = await original(...args);
            globalThis.ownedFootnoteReceipt = {
              target: args[0],
              sha256: result.source_sha256,
            };
            globalThis.ownedFootnoteReady = true;
            const deadline = Date.now() + 125_000;
            while (globalThis.ownedFootnoteHold && Date.now() < deadline)
              await new Promise((resolve) => setTimeout(resolve, 100));
            if (globalThis.ownedFootnoteHold)
              throw new Error("Owned footnote reply gate expired");
            return result;
          } finally {
            globalThis.ownedFootnotePending = false;
          }
        };
      },
      path.join(desktop, "dist/main/native-edit-appearance.js"),
    );
    await footnoteDialog
      .getByRole("button", { name: "PowerPoint appearance", exact: true })
      .click();
    const deadline = Date.now() + 125_000;
    while (
      !(await app.evaluate(() => globalThis.ownedFootnoteReady)) &&
      Date.now() < deadline
    )
      await new Promise((resolve) => setTimeout(resolve, 100));
    assert.equal(await app.evaluate(() => globalThis.ownedFootnoteReady), true);
    assert.equal(await saveFootnotes.isDisabled(), true);
    assert.equal(await footnoteAck.isDisabled(), true);
    await footnoteDialog
      .getByRole("button", { name: "Discard / close", exact: true })
      .click();
    await footnoteDialog.waitFor({ state: "detached" });
    await app.evaluate(() => {
      globalThis.ownedFootnoteHold = false;
    });
    const released = Date.now() + 125_000;
    while (
      (await app.evaluate(() => globalThis.ownedFootnotePending)) &&
      Date.now() < released
    )
      await new Promise((resolve) => setTimeout(resolve, 100));
    assert.equal(
      await app.evaluate(() => globalThis.ownedFootnotePending),
      false,
    );
    assert.deepEqual(await footnoteHead(), nativeFootnoteBaseline);
    assert.equal(
      await page
        .getByText(
          "Proposed slide appearance from PowerPoint. Changes are not saved.",
          { exact: true },
        )
        .count(),
      0,
    );
    await openFootnotes.click();
    await previewFootnotes.click();
    await footnoteImage.waitFor();
    await nativeFootnoteReady();
    await footnoteAck.check();
    await footnoteDialog
      .getByRole("button", { name: "Browser appearance", exact: true })
      .click();
    await page.waitForFunction(
      (element) => !element.checked,
      await footnoteAck.elementHandle(),
    );
    assert.equal(await footnoteAck.isChecked(), false);
    await nativeFootnoteReady();
    checks.push(
      "Native footnotes bind the actual proposed ordinal, reset appearance approval, block pending Save and contain held replies after Discard",
    );
  }

  assert.equal(await saveFootnotes.isDisabled(), true);
  await footnoteAck.check();
  await footnoteDialog
    .getByLabel("Citation label 1", { exact: true })
    .fill("Strategy notes · recovery evidence · supports");
  assert.equal(await saveFootnotes.isDisabled(), true);
  await footnoteDialog
    .getByText("The draft changed. Preview again before saving.", {
      exact: true,
    })
    .waitFor();
  await footnoteDialog
    .getByRole("button", { name: "Discard / close", exact: true })
    .click();
  await footnoteDialog.waitFor({ state: "detached" });
  await revisionHistory
    .getByText("Current · Revision 1", { exact: true })
    .waitFor();
  await openFootnotes.click();
  await footnoteDialog
    .getByLabel("Citation label 1", { exact: true })
    .fill("Strategy notes · recovery evidence · supports");
  await previewFootnotes.click();
  await footnoteImage.waitFor();
  assert.equal(
    await footnoteDialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
    true,
  );
  if (nativeFootnoteReview) await nativeFootnoteReady();
  await footnoteAck.check();
  await shot("workspace-evidence-footnotes-review");
  await saveFootnotes.click();
  await footnoteDialog.waitFor({ state: "detached" });
  if (nativeFootnoteReview)
    assert.equal((await footnoteHead()).sha256, nativeFootnoteReceipt.sha256);
  await page
    .getByText(
      "Saved reviewed evidence footnotes and refreshed retrieval. Review claims on the new revision.",
      { exact: true },
    )
    .waitFor();
  await claimReview
    .getByText("1 claim · 0 supported · 1 need review", { exact: true })
    .waitFor();
  assert.equal(await openFootnotes.isDisabled(), true);
  await studioPanel("Text");
  await page
    .getByRole("combobox", { name: "Text on this slide", exact: true })
    .locator("option")
    .filter({ hasText: /Strategy notes · recovery evidence/ })
    .waitFor({ state: "attached" });
  await revisionHistory
    .getByRole("button", { name: "Undo last presentation edit", exact: true })
    .click();
  await revisionHistory
    .getByText("Current · Revision 1", { exact: true })
    .waitFor();
  await studioPanel("Purpose");
  await claimReview
    .getByText("1 claim · 1 supported · 0 need review", { exact: true })
    .waitFor();
  if (nativeFootnoteReview) {
    assert.deepEqual(await footnoteHead(), nativeFootnoteBaseline);
    checks.push(
      "Native footnotes save the exact reviewed package and one Undo restores its original revision and bytes",
    );
  }
  checks.push(
    "Evidence footnotes preview current reviewed sources, invalidate changed labels, discard, save editable native citations, reindex, require fresh claim review and undo the complete revision",
  );
  if (
    await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .count()
  )
    await page
      .getByRole("button", { name: "Dismiss notification", exact: true })
      .click();
  await navigate("Teach");
  await page.getByRole("button", { name: "Start Teach", exact: true }).click();
  await page
    .getByRole("button", { name: "Ask focused question", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Start speaking", exact: true })
    .waitFor();
  await page
    .getByLabel("Your explanation", { exact: true })
    .fill("Keep this draft while I review my audience.");
  await navigate("Audience");
  await navigate("Teach");
  assert.equal(
    await page.getByLabel("Your explanation", { exact: true }).inputValue(),
    "Keep this draft while I review my audience.",
  );
  checks.push(
    "A real Teach session exposes voice-first controls and its typed fallback survives mode navigation",
  );
  await navigate("Audience");
  await page.getByLabel("Display name", { exact: true }).fill("Test audience");
  await page
    .getByRole("button", { name: "Create profile", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Test audience", exact: true })
    .waitFor();
  await navigate("Challenge");
  const challengeProfile = page.locator(".challenge-profile-option").filter({
    hasText: "Test audience",
  });
  await challengeProfile.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Start Challenge", exact: true })
    .click();
  await page
    .getByLabel("Your typed answer", { exact: true })
    .fill("Keep this Challenge draft while I review the rehearsal flow.");
  await navigate("Run");
  await page.getByRole("button", { name: "Start Run", exact: true }).click();
  await page.getByRole("button", { name: "Stop Run", exact: true }).click();
  await page.getByRole("button", { name: "Start Run", exact: true }).waitFor();
  await navigate("Teach");
  assert.equal(
    await page.getByLabel("Your explanation", { exact: true }).inputValue(),
    "Keep this draft while I review my audience.",
  );
  await navigate("Challenge");
  assert.equal(
    await page.getByLabel("Your typed answer", { exact: true }).inputValue(),
    "Keep this Challenge draft while I review the rehearsal flow.",
  );
  checks.push(
    "Teach and Challenge drafts survive a deterministic Run start and stop",
  );
  for (const name of [
    "Audience",
    "Teach",
    "Challenge",
    "Run",
    "Live Assist",
    "Workspace",
    "Project settings",
  ]) {
    await navigate(name);
    await noOverflow(name);
    await shot(`view-${name.toLowerCase().replaceAll(" ", "-")}`);
  }
  for (const panelChunk of [
    "AudiencePanel-",
    "ChallengePanel-",
    "LiveAssistPanel-",
    "PresentationWorkspace-",
    "RunPanel-",
    "TeachPanel-",
  ])
    assert.equal(
      await rendererAssetLoaded(panelChunk),
      true,
      `${panelChunk} loads on the first visit and remains available`,
    );
  checks.push(
    "Large renderer panels load on first navigation and stay available afterward",
  );
  const settingsGrid = page.locator(".settings-grid");
  const projectNameField = settingsGrid
    .locator("label")
    .filter({ hasText: /^Project name/ })
    .locator("input");
  const privacyModeField = settingsGrid
    .locator("label")
    .filter({ hasText: /^Privacy mode/ })
    .locator("select");
  const stylePolicyField = settingsGrid
    .locator("label")
    .filter({ hasText: /^Style policy/ })
    .locator("select");
  const customGuidanceField = settingsGrid
    .locator("label")
    .filter({ hasText: /^Custom guidance/ })
    .locator("textarea");
  const styleOverrideField = settingsGrid.locator(
    ".settings-checkbox input[type=checkbox]",
  );
  await projectNameField.fill("Draft project name");
  await privacyModeField.selectOption("selected_context_cloud");
  await stylePolicyField.selectOption("custom");
  await customGuidanceField.fill(
    "Keep the explanation grounded in the approved project voice.",
  );
  await styleOverrideField.check();
  await navigate("Sources");
  await navigate("Project settings");
  await page
    .getByRole("button", { name: "Quarterly strategy review", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Quarterly strategy review", exact: true })
    .first()
    .waitFor();
  await navigate("Project settings");
  assert.equal(await projectNameField.inputValue(), "Draft project name");
  assert.equal(await privacyModeField.inputValue(), "selected_context_cloud");
  assert.equal(await stylePolicyField.inputValue(), "custom");
  assert.equal(
    await customGuidanceField.inputValue(),
    "Keep the explanation grounded in the approved project voice.",
  );
  assert.equal(await styleOverrideField.isChecked(), true);
  checks.push(
    "All project views render; unsaved settings survive navigation and current-project clicks",
  );
  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()
      .find((window) => !window.isDestroyed() && window.isVisible())
      ?.setSize(720, 520);
  });
  await noOverflow("Minimum window");
  await navigate("Workspace");
  await noOverflow("Workspace at minimum window");
  await shot("workspace-minimum-window");
  await navigate("Project settings");
  assert.ok(
    (await page
      .locator(".sidebar-projects")
      .evaluate((element) => element.clientHeight)) >= 100,
  );
  await shot("06-minimum-window");
  await page.getByRole("button", { name: "Hide sidebar", exact: true }).click();
  await page
    .getByRole("button", { name: "Show sidebar", exact: true })
    .waitFor();
  await page.getByRole("button", { name: "Show sidebar", exact: true }).click();
  checks.push("Minimum 720x520 window and sidebar collapse work");
  await app.close();
  app = undefined;
  await launch();
  assert.equal(await page.getByRole("dialog").count(), 0);
  assert.equal(
    await page
      .getByRole("button", { name: "Quarterly strategy review", exact: true })
      .count(),
    1,
  );
  checks.push(
    "Project and walkthrough dismissal survive full Electron restart",
  );
  await page
    .getByRole("button", { name: "Setup & settings", exact: true })
    .click();
  const decisionSettings = page.getByRole("region", {
    name: "Fast Decisions",
    exact: true,
  });
  await decisionSettings.waitFor();
  const decisionProvider = decisionSettings.getByLabel(/decision provider/i);
  const decisionOptions = await decisionProvider.evaluate((element) =>
    Array.from(element.options, (option) => option.textContent?.trim() ?? ""),
  );
  assert.deepEqual(decisionOptions, [
    "Disabled",
    "Local model · strict JSON Schema",
    "OpenAI Responses · Fast mode",
    "OpenAI Responses · Ultrafast (GPT-6 Astra)",
    "OpenAI Decisions · Beta (GPT-6 Luna)",
    "Jev · OpenRouter System One",
    "Ollama · Jev-compatible System One",
    "ChatGPT plan usage · Preview",
  ]);
  assert.equal(await decisionProvider.inputValue(), "disabled");
  checks.push(
    "Fast decision providers are explicit in Settings and start disabled",
  );
  assert.deepEqual(errors, [], "No renderer exceptions");
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      {
        checks,
        rendererErrors: errors,
        scope:
          "Real Electron and local core; disposable profile; deterministic fake capture only; no hardware microphone, model downloads, or remote provider calls",
      },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({ passed: checks.length, checks, output }, null, 2),
  );
} catch (error) {
  if (page) {
    await shot("failure").catch(() => {});
    console.error(
      (
        await page
          .locator("body")
          .innerText()
          .catch(() => "")
      ).slice(0, 8000),
    );
  }
  throw error;
} finally {
  if (app) await app.close();
}
