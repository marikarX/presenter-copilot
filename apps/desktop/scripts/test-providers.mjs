/* global window, document */
import assert from "node:assert/strict";
import { mkdtemp, mkdir } from "node:fs/promises";
import { createServer } from "node:http";
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
const temporary = await mkdtemp(path.join(os.tmpdir(), "presenter-providers-"));
const output = path.join(root, ".local", "provider-ui-validation");
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
env.PRESENTER_LOCAL_API_KEY = "synthetic-local-credential";
const calls = [];
const server = createServer((request, response) => {
  let body = "";
  request.on("data", (data) => {
    body += data;
  });
  request.on("end", () => {
    calls.push({
      path: request.url,
      authorization: request.headers.authorization,
      body: JSON.parse(body),
    });
    response.setHeader("Content-Type", "application/json");
    response.end(
      JSON.stringify({
        choices: [
          {
            finish_reason: "stop",
            message: {
              content: JSON.stringify({
                question: "Why this decision?",
                focus: "decision_rationale",
              }),
            },
          },
        ],
      }),
    );
  });
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const endpoint = `http://127.0.0.1:${server.address().port}/v1`;
let app;
try {
  app = await electron.launch({
    executablePath: require("electron"),
    args: [desktop, `--user-data-dir=${path.join(temporary, "browser")}`],
    cwd: root,
    env,
    timeout: 30000,
  });
  let page;
  const deadline = Date.now() + 30000;
  while (!page && Date.now() < deadline) {
    page = app
      .windows()
      .find((candidate) => candidate.url().endsWith("/renderer/index.html"));
    if (!page) await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(page);
  page.setDefaultTimeout(15000);
  await page
    .getByLabel("Core status: READY", { exact: true })
    .waitFor({ timeout: 30000 });
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Setup & settings", exact: true })
    .click();
  const decisionPanel = page.getByRole("region", {
    name: "Fast Decisions",
    exact: true,
  });
  const decisionProvider = decisionPanel.getByRole("combobox", {
    name: /decision provider/i,
  });
  await decisionProvider.waitFor();
  assert.equal(await decisionProvider.inputValue(), "disabled");
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
  await decisionProvider.selectOption("openai_ultrafast");
  await decisionPanel
    .getByText(/Uses GPT-6 Astra with OpenAI Responses Ultrafast/)
    .waitFor();
  await decisionProvider.selectOption("disabled");
  await decisionProvider.selectOption("openai_decisions");
  await decisionPanel
    .getByText(
      /Uses GPT-6 Luna through the native OpenAI Decisions beta endpoint/,
    )
    .waitFor();
  await decisionProvider.selectOption("ollama_systemone");
  const ollamaModel = decisionPanel.getByLabel("Ollama decision model");
  await ollamaModel.waitFor();
  assert.equal(await ollamaModel.inputValue(), "tev1:4b");
  const ollamaModelOptions = await ollamaModel.evaluate((element) =>
    Array.from(element.options, (option) => option.value),
  );
  assert.deepEqual(ollamaModelOptions, [
    "nimble:9b",
    "nimble:9b-q4_K_M",
    "nimble:latest",
    "tev1:4b",
    "tev1:4b-q4_K_M",
    "tev1:latest",
    "tev1:0.8b",
  ]);
  await decisionPanel.getByText(/ollama pull tev1:4b/).waitFor();
  await ollamaModel.selectOption("nimble:latest");
  await decisionPanel.getByText(/ollama pull nimble:latest/).waitFor();
  await decisionPanel
    .getByText(/does not launch Ollama or download models/i)
    .waitFor();
  await decisionProvider.selectOption("disabled");
  await decisionProvider.selectOption("openai_chatgpt_plan");
  await decisionPanel
    .getByText(/separate from Codex — ChatGPT sign-in/)
    .waitFor();
  await decisionPanel
    .getByRole("button", { name: "Continue with ChatGPT", exact: true })
    .waitFor();
  await decisionPanel
    .getByRole("button", { name: "Manage ChatGPT usage", exact: true })
    .waitFor();
  assert.equal(
    await decisionPanel
      .getByLabel("ChatGPT model", { exact: true })
      .isDisabled(),
    true,
    "ChatGPT plan inference stays unavailable until account authorization and model discovery",
  );
  await decisionProvider.selectOption("disabled");
  const panel = page.getByRole("region", {
    name: "Reasoning Providers",
    exact: true,
  });
  await panel.getByText("not configured", { exact: false }).first().waitFor();
  await panel
    .getByRole("combobox", { name: "Provider", exact: true })
    .selectOption("codex_chatgpt");
  assert.equal(
    await panel
      .getByRole("textbox", { name: "Model", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(
    await panel
      .getByRole("textbox", { name: "Model", exact: true })
      .inputValue(),
    "gpt-5.4-mini",
  );
  await panel
    .getByRole("button", { name: "Refresh ChatGPT status", exact: true })
    .click();
  await panel.getByText("ChatGPT status updated.", { exact: true }).waitFor();
  const authStatus = await page.evaluate(async () =>
    window.presenterCopilot.core.request("provider.codex.status"),
  );
  assert.equal(authStatus.ok, true);
  assert.deepEqual(Object.keys(authStatus.result).sort(), [
    "error_code",
    "runtime_version",
    "state",
  ]);
  assert.equal(authStatus.result.state, "signed_out");
  await panel
    .getByRole("button", { name: "Sign out of ChatGPT", exact: true })
    .click();
  await panel.getByText("ChatGPT status updated.", { exact: true }).waitFor();
  await panel
    .getByRole("button", { name: "Save and select", exact: true })
    .click();
  await panel.getByText("Provider selected.", { exact: false }).waitFor();
  await panel
    .getByRole("combobox", { name: "Provider", exact: true })
    .selectOption("local_openai");
  await panel
    .getByRole("textbox", { name: "Base URL", exact: true })
    .fill(endpoint);
  await panel
    .getByRole("textbox", { name: "Model", exact: true })
    .fill("synthetic-model");
  await panel
    .getByRole("button", { name: "Save and select", exact: true })
    .click();
  await panel.getByText("Provider selected.", { exact: false }).waitFor();
  assert.equal(
    calls.length,
    0,
    "Saving configuration sends no inference request",
  );
  await panel
    .getByRole("button", {
      name: "Test selected provider (synthetic)",
      exact: true,
    })
    .click();
  await panel.getByText("Reachable: synthetic", { exact: false }).waitFor();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, "/v1/chat/completions");
  assert.equal(calls[0].authorization, "Bearer synthetic-local-credential");
  const exposed = await page.evaluate(async () => ({
    providers: await window.presenterCopilot.core.request("provider.list"),
    planAuth: await window.presenterCopilot.core.request(
      "provider.chatgpt_plan.status",
    ),
    node: typeof window.require,
    text: document.body.innerText,
  }));
  assert.equal(exposed.node, "undefined");
  assert.ok(!JSON.stringify(exposed).includes("synthetic-local-credential"));
  assert.equal(exposed.planAuth.ok, true);
  assert.deepEqual(Object.keys(exposed.planAuth.result).sort(), [
    "accounts",
    "active_account_id",
    "credential_store_available",
    "error_code",
    "state",
  ]);
  assert.equal(exposed.planAuth.result.state, "signed_out");
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, "reasoning-providers.png") });
  await page.reload();
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Setup & settings", exact: true })
    .click();
  await panel.getByRole("textbox", { name: "Model", exact: true }).waitFor();
  await page.waitForFunction(
    () =>
      document.querySelector(
        '[aria-label="Reasoning Providers"] input[maxlength="120"]',
      )?.value === "synthetic-model",
  );
  assert.equal(
    await panel
      .getByRole("textbox", { name: "Model", exact: true })
      .inputValue(),
    "synthetic-model",
  );
  assert.equal(
    await panel
      .getByRole("textbox", { name: "Base URL", exact: true })
      .inputValue(),
    endpoint,
  );
  assert.equal(calls.length, 1, "Reload performs no background inference");
  await decisionProvider.selectOption("openai_decisions");
  assert.equal(
    await decisionPanel
      .getByRole("button", { name: "Save decision provider", exact: true })
      .isDisabled(),
    true,
    "Native Decisions cannot be selected without an API key",
  );
  await decisionPanel
    .getByText("OpenAI Decisions · Beta", { exact: true })
    .waitFor();
  assert.equal(
    calls.length,
    1,
    "Native decision selection invokes no inference",
  );
  await decisionPanel.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: path.join(output, "native-decisions-settings.png"),
  });
  console.log(
    "Provider UI: configuration, synthetic inference, persistence, and credential boundary passed.",
  );
} finally {
  if (app) await app.close();
  await new Promise((resolve) => server.close(resolve));
}
