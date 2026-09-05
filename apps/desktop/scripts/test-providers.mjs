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
  const panel = page.getByRole("region", {
    name: "Reasoning Providers",
    exact: true,
  });
  await panel.getByText("not configured", { exact: false }).first().waitFor();
  assert.match(
    await panel.innerText(),
    /Selected Context isolation not verified/,
  );
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
    node: typeof window.require,
    text: document.body.innerText,
  }));
  assert.equal(exposed.node, "undefined");
  assert.ok(!JSON.stringify(exposed).includes("synthetic-local-credential"));
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
  console.log(
    "Provider UI: configuration, synthetic inference, persistence, and credential boundary passed.",
  );
} finally {
  if (app) await app.close();
  await new Promise((resolve) => server.close(resolve));
}
