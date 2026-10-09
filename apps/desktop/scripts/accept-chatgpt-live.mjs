/* global window */
// Guided LIVE acceptance for Sign in with ChatGPT (ChatGPT plan Fast Decisions).
//
// Requires a human with an eligible ChatGPT account. The script automates every
// step except the browser consent screen, then writes a token-free receipt:
//   first-time consent, returning sign-in after app restart, model listing,
//   one synthetic finite-choice decision, disclosures, catalog refresh, sign-out.
//
// Run:  pnpm build && PRESENTER_CHATGPT_LIVE_ACCEPTANCE=1 node apps/desktop/scripts/accept-chatgpt-live.mjs
// Data is isolated in a temporary directory; no presentation content is used
// beyond one synthetic slide, and no token, email or account ID is recorded.
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron } from "playwright";

if (process.env.PRESENTER_CHATGPT_LIVE_ACCEPTANCE !== "1") {
  console.error(
    "Live acceptance contacts OpenAI with a real account. Set PRESENTER_CHATGPT_LIVE_ACCEPTANCE=1 to run it.",
  );
  process.exit(2);
}
const require = createRequire(import.meta.url);
const desktop = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const root = path.resolve(desktop, "../..");
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-chatgpt-"));
const output = path.join(root, ".local", "chatgpt-live");
await mkdir(output, { recursive: true });
const consentMinutes = Number(
  process.env.PRESENTER_CHATGPT_CONSENT_MINUTES || 10,
);
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

const receipt = {
  started_at: new Date().toISOString(),
  boundary:
    "Actual Electron/Core, live OpenAI OAuth and Responses; isolated data root; synthetic one-slide deck",
  steps: {},
  disclosures: {},
};
const step = (name, value) => {
  receipt.steps[name] = value;
  console.log(`✓ ${name}`);
};
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
  page = undefined;
  const deadline = Date.now() + 30_000;
  while (!page && Date.now() < deadline) {
    page = app
      .windows()
      .find((candidate) => candidate.url().endsWith("/renderer/index.html"));
    if (!page) await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(page, "The renderer window did not open.");
  page.setDefaultTimeout(30_000);
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
}
const ask = (method, params = {}) =>
  page.evaluate(
    async ({ method, params }) => {
      const r = await window.presenterCopilot.core.request(method, params);
      if (!r.ok)
        throw new Error(`${r.error.code ?? "ERROR"}: ${r.error.message}`);
      return r.result;
    },
    { method, params },
  );
async function openSettings() {
  await page
    .getByRole("button", { name: "Setup & settings", exact: true })
    .click();
  const panel = page.getByRole("region", {
    name: "Fast Decisions",
    exact: true,
  });
  await panel.waitFor();
  return panel;
}

try {
  await launch();
  await page
    .getByRole("dialog")
    .waitFor({ timeout: 5000 })
    .then(() => page.keyboard.press("Escape"))
    .catch(() => {});
  let panel = await openSettings();
  const before = await ask("provider.chatgpt_plan.status");
  assert.equal(
    before.credential_store_available,
    true,
    "The protected credential store is unavailable on this machine.",
  );
  assert.equal(before.state, "signed_out");
  const providerSelect = panel.getByRole("combobox", {
    name: /^Decision provider/,
  });
  await providerSelect.selectOption("openai_chatgpt_plan");
  await panel
    .getByRole("button", { name: "Continue with ChatGPT", exact: true })
    .click();
  console.log(
    `\nComplete ChatGPT sign-in and consent in your browser (waiting up to ${consentMinutes} min)…\n`,
  );
  const consentStarted = Date.now();
  let status = await ask("provider.chatgpt_plan.status");
  while (
    status.state === "signing_in" &&
    Date.now() - consentStarted < consentMinutes * 60_000
  ) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    status = await ask("provider.chatgpt_plan.status");
  }
  assert.equal(status.state, "signed_in", `Sign-in ended as ${status.state}.`);
  step("first_time_consent", {
    state: status.state,
    accounts: status.accounts.length,
    seconds_to_consent: Math.round((Date.now() - consentStarted) / 1000),
  });

  // Returning sign-in: the protected vault restores the session after restart.
  await app.close();
  await launch();
  const returning = await ask("provider.chatgpt_plan.status");
  assert.equal(returning.state, "signed_in");
  step("returning_sign_in_after_restart", { state: returning.state });

  const catalog = await ask("provider.chatgpt_plan.models", {});
  assert.ok(catalog.models.length > 0, "No ChatGPT plan models were listed.");
  step("model_listing", {
    count: catalog.models.length,
    model_ids: catalog.models.map((item) => item.model_id),
  });
  const chosen =
    process.env.PRESENTER_CHATGPT_MODEL &&
    catalog.models.some(
      (item) => item.model_id === process.env.PRESENTER_CHATGPT_MODEL,
    )
      ? process.env.PRESENTER_CHATGPT_MODEL
      : catalog.models[0].model_id;
  panel = await openSettings();
  await panel
    .getByRole("combobox", { name: /^Decision provider/ })
    .selectOption("openai_chatgpt_plan");
  await panel
    .getByRole("combobox", { name: /^ChatGPT model/ })
    .selectOption(chosen);
  await panel
    .getByRole("button", { name: "Save decision provider", exact: true })
    .click();
  const text = await panel.innerText();
  receipt.disclosures = {
    preview_and_limits: /Preview access and usage limits/.test(text),
    shared_limits: /share limits with other ChatGPT apps/.test(text),
    storage_disabled: /storage disabled/.test(text),
  };
  assert.ok(
    Object.values(receipt.disclosures).every(Boolean),
    JSON.stringify(receipt.disclosures),
  );
  step("disclosures_visible", receipt.disclosures);

  const project = (await ask("project.create", { name: "ChatGPT live" }))
    .project.id;
  const document = (
    await ask("presentation.workspace.create_from_outline", {
      project_id: project,
      title: "Synthetic acceptance",
      slides: [
        {
          title: "Agenda",
          bullets: ["Context", "Options", "Recommendation", "Next steps"],
          notes: "",
        },
      ],
    })
  ).document.id;
  const revision = (
    await ask("presentation.workspace.list_revisions", {
      project_id: project,
      document_id: document,
    })
  ).current_revision_id;
  const started = Date.now();
  const decision = await ask("presentation.workspace.classify_slide", {
    project_id: project,
    document_id: document,
    revision_id: revision,
    slide_number: 1,
  });
  step("synthetic_finite_choice_decision", {
    model_id: chosen,
    round_trip_ms: Date.now() - started,
    provider_latency_ms: decision.latency_ms ?? null,
    choice: decision.purpose,
    confidence: decision.confidence,
    requires_user_review: decision.requires_user_review,
  });

  const refreshed = await ask("provider.chatgpt_plan.models", {
    refresh: true,
  });
  step("catalog_refresh", { count: refreshed.models.length });

  panel = await openSettings();
  await panel
    .getByRole("button", { name: "Sign out of this account", exact: true })
    .click();
  let signedOut = await ask("provider.chatgpt_plan.status");
  const outDeadline = Date.now() + 30_000;
  while (signedOut.state === "signed_in" && Date.now() < outDeadline) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    signedOut = await ask("provider.chatgpt_plan.status");
  }
  assert.notEqual(signedOut.state, "signed_in");
  const revocationNotice = await page
    .getByText(/could not confirm remote token revocation/)
    .count();
  step("sign_out", {
    state: signedOut.state,
    remote_revocation_confirmed: revocationNotice === 0,
  });
  receipt.passed = true;
} catch (error) {
  receipt.passed = false;
  receipt.error = String(error.message).slice(0, 500);
  if (page)
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
  process.exitCode = 1;
} finally {
  receipt.finished_at = new Date().toISOString();
  const file = path.join(
    output,
    `receipt-${receipt.started_at.replaceAll(":", "-")}.json`,
  );
  await writeFile(file, JSON.stringify(receipt, null, 2));
  console.log(`\nReceipt: ${file}`);
  if (app) await app.close().catch(() => {});
}
