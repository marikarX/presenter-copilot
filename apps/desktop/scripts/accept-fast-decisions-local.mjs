/* global window */
// LIVE acceptance: Fast Decisions through the real Settings and Workspace GUI
// against a loopback OpenAI-compatible model server that you start separately
// (for example LM Studio or llama-server). Nothing is a fixture except the
// synthetic two-slide deck.
//
// Run: pnpm build && PRESENTER_DECISION_LIVE_MODEL=<model id> \
//      [PRESENTER_DECISION_LIVE_ENDPOINT=http://127.0.0.1:1234/v1] \
//      node apps/desktop/scripts/accept-fast-decisions-local.mjs
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

const model = process.env.PRESENTER_DECISION_LIVE_MODEL;
const endpoint =
  process.env.PRESENTER_DECISION_LIVE_ENDPOINT || "http://127.0.0.1:1234/v1";
if (!model) {
  console.error("Set PRESENTER_DECISION_LIVE_MODEL to the served model id.");
  process.exit(2);
}
assert.match(
  new URL(endpoint).hostname,
  /^(127\.0\.0\.1|localhost|\[::1\])$/,
  "Only a loopback endpoint is accepted.",
);
const require = createRequire(import.meta.url);
const desktop = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const root = path.resolve(desktop, "../..");
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-decisions-"));
const output = path.join(
  root,
  ".local",
  "ui-validation",
  "fast-decisions-local",
);
await mkdir(output, { recursive: true });
const env = { ...process.env };
for (const key of Object.keys(env))
  if (
    key.startsWith("PRESENTER_") ||
    key.startsWith("OPENAI_") ||
    key === "OPENROUTER_API_KEY" ||
    key === "ELECTRON_RUN_AS_NODE"
  )
    delete env[key];
Object.assign(env, {
  PRESENTER_COPILOT_DATA_ROOT: path.join(temporary, "core"),
  PRESENTER_CORE_DIR: path.join(root, "core"),
  PRESENTER_COPILOT_DEV_MODE: "1",
});
const slides = [
  {
    title: "Agenda",
    bullets: ["Context", "Options", "Recommendation", "Next steps"],
    notes: "",
    expected: "opening",
  },
  {
    title: "We recommend funding the pilot",
    bullets: [
      "Approve a 12-week pilot in two regions",
      "Budget: 180k, reviewed at week 6",
      "Decision needed today",
    ],
    notes: "",
    expected: "recommendation",
  },
];
const results = [];
const checks = [];
const errors = [];
let app;
let page;
try {
  app = await electron.launch({
    executablePath: require("electron"),
    args: [desktop, `--user-data-dir=${path.join(temporary, "browser")}`],
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
  page.setDefaultTimeout(60_000);
  page.on("pageerror", (error) => errors.push(error.message));
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await page
    .getByRole("textbox", { name: "New project name", exact: true })
    .fill("Fast decisions live");
  await page.keyboard.press("Enter");
  await page
    .getByRole("heading", { name: "Sources", exact: true })
    .first()
    .waitFor();
  const ask = async (method, params) =>
    page.evaluate(
      async ({ method, params }) => {
        const r = await window.presenterCopilot.core.request(method, params);
        if (!r.ok) throw new Error(`${r.error.code}: ${r.error.message}`);
        return r.result;
      },
      { method, params },
    );
  const project = (await ask("project.list", {})).projects.find(
    (item) => item.name === "Fast decisions live",
  ).id;
  const document = (
    await ask("presentation.workspace.create_from_outline", {
      project_id: project,
      title: "Pilot decision",
      slides: slides.map(({ title, bullets, notes }) => ({
        title,
        bullets,
        notes,
      })),
    })
  ).document.id;

  // Settings: local reasoning endpoint/model, then the local decision provider.
  await page
    .getByRole("button", { name: "Setup & settings", exact: true })
    .click();
  const providers = page.getByRole("region", {
    name: "Reasoning Providers",
    exact: true,
  });
  await providers
    .getByRole("combobox", { name: "Provider", exact: true })
    .selectOption("local_openai");
  await providers
    .getByRole("textbox", { name: "Base URL", exact: true })
    .fill(endpoint);
  await providers
    .getByRole("textbox", { name: "Model", exact: true })
    .fill(model);
  await providers
    .getByRole("button", { name: "Save and select", exact: true })
    .click();
  const decisions = page.getByRole("region", {
    name: "Fast Decisions",
    exact: true,
  });
  await decisions
    .getByRole("combobox", { name: /^Decision provider/ })
    .selectOption("local_choice");
  await decisions
    .getByRole("button", { name: "Save decision provider", exact: true })
    .click();
  await decisions
    .getByText(/Local structured output: .*· loopback · selected/)
    .waitFor();
  checks.push(
    "Settings GUI configures the loopback local model and selects it for Fast Decisions",
  );

  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  // The deck was created over RPC; reload so the renderer lists it.
  await page.reload();
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Fast decisions live" })
    .first()
    .click();
  await page
    .getByRole("navigation", { name: "Project navigation", exact: true })
    .getByRole("button", { name: "Workspace", exact: true })
    .click();
  const picker = page.getByRole("combobox", {
    name: "Presentation",
    exact: true,
  });
  if (await picker.count())
    await picker
      .selectOption({ value: document })
      .catch(() => picker.selectOption({ index: 0 }));
  await page.getByRole("button", { name: "Open preview", exact: true }).click();
  await page
    .locator(".presentation-workspace")
    .getByText("Current · Revision 1", { exact: true })
    .waitFor();
  await page
    .getByRole("group", { name: "Slide studio panels" })
    .getByRole("button", { name: "Purpose", exact: true })
    .click();
  for (const [index, slide] of slides.entries()) {
    if (index > 0) {
      await page
        .getByRole("button", { name: "Next slide", exact: true })
        .click();
      await page
        .getByText(`Slide ${index + 1} of ${slides.length}`, { exact: true })
        .waitFor();
    }
    const started = Date.now();
    await page
      .getByRole("button", { name: "Suggest slide purpose", exact: true })
      .click();
    const status = page.locator(".pw-purpose-result").first();
    await status.getByText(/^Suggestion:/).waitFor({ timeout: 60_000 });
    const text = await status.innerText();
    const purpose = /Suggestion:\s*([a-z ]+)/i
      .exec(text)[1]
      .trim()
      .toLowerCase()
      .replaceAll(" ", "_");
    results.push({
      slide: index + 1,
      expected: slide.expected,
      suggested: purpose,
      correct: purpose === slide.expected,
      gui_round_trip_ms: Date.now() - started,
      provider_latency_ms: Number(/· (\d+) ms/.exec(text)?.[1] ?? NaN),
      provider: /local_choice/.test(text) ? "local_choice" : "unexpected",
    });
    assert.equal(results.at(-1).provider, "local_choice");
    // Reviewed adoption: the user saves the suggestion explicitly; an
    // suggestion that is not a savable purpose is recorded but left unsaved.
    const choice = page.getByRole("combobox", {
      name: "Slide purpose to save",
      exact: true,
    });
    const savable = await choice.locator(`option[value="${purpose}"]`).count();
    results.at(-1).saved = savable > 0;
    if (savable) {
      await choice.selectOption(purpose);
      await page
        .getByRole("button", {
          name: "Save purpose for this revision",
          exact: true,
        })
        .click();
      await page
        .getByText(`Saved purpose: ${purpose.replaceAll("_", " ")}`)
        .waitFor();
    }
  }
  checks.push(
    "Workspace Purpose panel returns live local-model suggestions; savable ones are saved only after explicit review",
  );
  await page.screenshot({ path: path.join(output, "fast-decisions.png") });
  assert.deepEqual(errors, []);
  const receipt = {
    endpoint_scope: "loopback",
    model,
    checks,
    results,
    accuracy: `${results.filter((r) => r.correct).length}/${results.length}`,
    boundary:
      "Actual Electron/Core/local_choice provider and live loopback model; synthetic deck; not a calibrated quality claim",
  };
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(receipt, null, 2),
  );
  console.log(JSON.stringify(receipt, null, 2));
} catch (error) {
  await writeFile(
    path.join(output, "failure-checks.json"),
    JSON.stringify({ checks, results, errors, error: error.message }, null, 2),
  );
  if (page)
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
  throw error;
} finally {
  if (app) await app.close();
}
