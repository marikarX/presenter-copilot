/* global document, window */
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
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
const output = path.join(root, ".local", "chatgpt-settings");
const temporary = await mkdtemp(
  path.join(os.tmpdir(), "presenter-auth-settings-"),
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
env.PRESENTER_COPILOT_DATA_ROOT = path.join(temporary, "core");
env.PRESENTER_CORE_DIR = path.join(root, "core");
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
    timeout: 30000,
  });
  const deadline = Date.now() + 30000;
  while (!page && Date.now() < deadline) {
    page = app
      .windows()
      .find((candidate) => candidate.url().endsWith("/renderer/index.html"));
    if (!page) await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(page, "Main renderer window appeared");
  page.setDefaultTimeout(15000);
  page.on("pageerror", (error) => errors.push(error.message));
  await page
    .getByLabel("Core status: READY", { exact: true })
    .waitFor({ timeout: 30000 });
  await page.keyboard.press("Escape");
  // Only this disposable process's client prototype is replaced. Normal IPC validation
  // remains active. The selected auth/status calls never reach OAuth or inference.
  await app.evaluate(
    (_electron, clientPath) => {
      const { CoreProcessClient } = process.mainModule.require(clientPath);
      const original = CoreProcessClient.prototype.request;
      const f = (globalThis.__chatgptSettingsFixture = {
        state: "signed_out",
        active: null,
        accounts: [],
        selected: "disabled",
        savedModel: "model-a",
        savedOllama: "tev1:4b",
        calls: [],
        saves: [],
        failCatalog: false,
        holdNext: false,
        held: [],
      });
      const clone = (value) => JSON.parse(JSON.stringify(value));
      const auth = () => ({
        state: f.state,
        error_code: null,
        credential_store_available: true,
        active_account_id: f.active,
        accounts: f.accounts.map((a) => ({
          ...a,
          active: a.account_id === f.active,
        })),
      });
      const status = () => ({
        selected_provider_id: f.selected,
        ollama_model_id: f.savedOllama,
        chatgpt_plan_model_id: f.savedModel,
        providers: [
          {
            provider_id: "ollama_systemone",
            label: "Ollama fixture",
            configured: true,
            model_id: "tev1:4b",
            leaves_machine: false,
            model_options: [
              { model_id: "tev1:4b", label: "Tev1" },
              { model_id: "nimble:latest", label: "Nimble" },
            ],
          },
          {
            provider_id: "openai_chatgpt_plan",
            label: "ChatGPT fixture",
            configured: f.state === "signed_in",
            model_id: f.savedModel,
            leaves_machine: true,
          },
        ],
      });
      CoreProcessClient.prototype.request = function (
        method,
        params = {},
        ...rest
      ) {
        if (method === "provider.decision.configure") {
          f.saves.push(clone(params));
          f.selected = params.provider_id;
          if (params.provider_id === "openai_chatgpt_plan")
            f.savedModel = params.model_id;
          if (params.provider_id === "ollama_systemone")
            f.savedOllama = params.model_id;
          return Promise.resolve(status());
        }
        if (
          method === "provider.decision.status" ||
          method.startsWith("provider.chatgpt_plan.")
        ) {
          f.calls.push(method);
          if (method === "provider.decision.status") {
            const snapshot = clone(status());
            if (f.holdNext) {
              f.holdNext = false;
              return new Promise((resolve) =>
                f.held.push(() => resolve(snapshot)),
              );
            }
            return Promise.resolve(snapshot);
          }
          if (method === "provider.chatgpt_plan.sign_in")
            f.state = "signing_in";
          if (method === "provider.chatgpt_plan.cancel") f.state = "signed_out";
          if (method === "provider.chatgpt_plan.sign_out") {
            f.state = "signed_out";
            f.accounts = f.accounts.map((a) =>
              a.account_id === f.active ? { ...a, connected: false } : a,
            );
          }
          if (method === "provider.chatgpt_plan.select")
            f.active = params.account_id;
          if (method === "provider.chatgpt_plan.models") {
            if (f.failCatalog)
              return Promise.reject(new Error("Synthetic catalog unavailable"));
            return Promise.resolve({
              models: [
                { model_id: "model-a", label: "Model A" },
                { model_id: "model-b", label: "Model B" },
              ],
            });
          }
          return Promise.resolve({
            ...auth(),
            remote_revocation_confirmed: true,
          });
        }
        return original.call(this, method, params, ...rest);
      };
    },
    path.join(desktop, "dist", "main", "core-client.js"),
  );
  await page.reload();
  await page.getByLabel("Core status: READY", { exact: true }).waitFor();
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Setup & settings", exact: true })
    .click();
  const panel = page.getByRole("region", {
    name: "Fast Decisions",
    exact: true,
  });
  await panel.getByText("ChatGPT fixture", { exact: true }).waitFor();
  const provider = panel.getByRole("combobox", { name: /^Decision provider/ });
  const model = panel.getByRole("combobox", { name: /^ChatGPT model/ });
  const cancel = panel.getByRole("button", {
    name: "Cancel sign-in",
    exact: true,
  });
  const refresh = panel.getByRole("button", {
    name: "Refresh ChatGPT plan status",
    exact: true,
  });
  const save = panel.getByRole("button", {
    name: "Save decision provider",
    exact: true,
  });
  const countStatus = () =>
    app.evaluate(
      () =>
        globalThis.__chatgptSettingsFixture.calls.filter(
          (m) => m === "provider.decision.status",
        ).length,
    );
  const waitMain = async (predicate, argument) => {
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      if (await app.evaluate(predicate, argument)) return;
      await page.waitForTimeout(100);
    }
    assert.fail("Synthetic auth fixture did not reach its expected state");
  };
  await provider.selectOption("openai_chatgpt_plan");
  await panel
    .getByRole("button", { name: "Continue with ChatGPT", exact: true })
    .click();
  await cancel.waitFor();
  assert.equal(await provider.inputValue(), "openai_chatgpt_plan");
  checks.push(
    "Sign-in refresh keeps the unsaved provider and Cancel control visible",
  );
  await page.screenshot({ path: path.join(output, "signing-in.png") });
  await provider.selectOption("ollama_systemone");
  const ollama = panel.getByRole("combobox", {
    name: /^Ollama decision model/,
  });
  await ollama.selectOption("nimble:latest");
  const startCount = await countStatus();
  await waitMain(
    (_electron, expected) =>
      globalThis.__chatgptSettingsFixture.calls.filter(
        (m) => m === "provider.decision.status",
      ).length >= expected,
    startCount + 2,
  );
  assert.ok((await countStatus()) > startCount);
  assert.equal(await provider.inputValue(), "ollama_systemone");
  assert.equal(await ollama.inputValue(), "nimble:latest");
  checks.push(
    "Recurring sign-in polling preserves provider and Ollama model edits",
  );
  await provider.selectOption("openai_chatgpt_plan");
  await app.evaluate(() => {
    const f = globalThis.__chatgptSettingsFixture;
    f.state = "signed_in";
    f.active = "account-a";
    f.accounts = [
      {
        account_id: "account-a",
        email: "account-a@example.invalid",
        connected: true,
      },
      {
        account_id: "account-b",
        email: "account-b@example.invalid",
        connected: true,
      },
    ];
  });
  await page.waitForFunction(
    () =>
      document.querySelector("#chatgpt-plan-model-select")?.value === "model-a",
  );
  await model.selectOption("model-b");
  await refresh.click();
  await page
    .getByText("ChatGPT plan account status updated.", { exact: true })
    .waitFor();
  assert.equal(await model.inputValue(), "model-b");
  checks.push(
    "Successful sign-in/catalog refresh preserves the user's model choice",
  );
  await app.evaluate(
    () => (globalThis.__chatgptSettingsFixture.failCatalog = true),
  );
  await refresh.click();
  await panel.getByText(/The model catalog could not be loaded/).waitFor();
  assert.equal(await save.isDisabled(), true);
  await app.evaluate(
    () => (globalThis.__chatgptSettingsFixture.failCatalog = false),
  );
  await refresh.click();
  await page.waitForFunction(
    () =>
      document.querySelector("#chatgpt-plan-model-select")?.value === "model-b",
  );
  checks.push(
    "Catalog failure disables saving and retry restores the retained draft model",
  );
  await panel
    .getByRole("button", { name: /account-b@example.invalid · select/ })
    .click();
  await page.waitForFunction(
    () =>
      document.querySelector("#chatgpt-plan-model-select")?.value === "model-a",
  );
  assert.equal(await provider.inputValue(), "openai_chatgpt_plan");
  assert.deepEqual(
    await app.evaluate(() => globalThis.__chatgptSettingsFixture.saves),
    [],
  );
  await save.click();
  await page
    .getByText("Fast decision provider selection saved.", { exact: true })
    .waitFor();
  assert.deepEqual(
    await app.evaluate(() => globalThis.__chatgptSettingsFixture.saves),
    [{ provider_id: "openai_chatgpt_plan", model_id: "model-a" }],
  );
  checks.push(
    "Account switch revalidates the model; only explicit Save configures a provider",
  );
  await panel
    .getByRole("button", { name: "Sign out of this account", exact: true })
    .click();
  await panel
    .getByRole("button", {
      name: "Continue with selected account",
      exact: true,
    })
    .waitFor();
  assert.equal(await provider.inputValue(), "openai_chatgpt_plan");
  assert.equal(await save.isDisabled(), true);
  await panel
    .getByRole("button", {
      name: "Continue with selected account",
      exact: true,
    })
    .click();
  await cancel.waitFor();
  await app.evaluate(
    () => (globalThis.__chatgptSettingsFixture.holdNext = true),
  );
  await waitMain(() => globalThis.__chatgptSettingsFixture.held.length === 1);
  const heldCount = await countStatus();
  await page.waitForTimeout(3200);
  assert.equal(
    await countStatus(),
    heldCount,
    "No overlapping polls while a request is pending",
  );
  await cancel.click();
  await panel
    .getByRole("button", {
      name: "Continue with selected account",
      exact: true,
    })
    .waitFor();
  await app.evaluate(() =>
    globalThis.__chatgptSettingsFixture.held
      .splice(0)
      .forEach((resolve) => resolve()),
  );
  await page.waitForTimeout(200);
  assert.equal(
    await cancel.count(),
    0,
    "A stale sign-in poll cannot resurrect a cancelled attempt",
  );
  assert.equal(await provider.inputValue(), "openai_chatgpt_plan");
  checks.push(
    "Pending polls are serialized and late replies cannot reverse cancellation",
  );
  await app.evaluate(({ BrowserWindow }) => {
    BrowserWindow.getAllWindows()
      .find((win) => win.webContents.getURL().endsWith("/renderer/index.html"))
      .setSize(720, 520);
  });
  await provider.scrollIntoViewIfNeeded();
  await page.waitForFunction(() => window.innerWidth < 730);
  assert.equal(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth + 1,
    ),
    false,
  );
  await panel
    .getByRole("button", {
      name: "Continue with selected account",
      exact: true,
    })
    .click();
  await cancel.waitFor();
  await cancel.scrollIntoViewIfNeeded();
  const cancelBounds = await cancel.boundingBox();
  const viewport = await page.evaluate(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
  }));
  assert.ok(
    cancelBounds &&
      cancelBounds.x >= 0 &&
      cancelBounds.y >= 0 &&
      cancelBounds.x + cancelBounds.width <= viewport.width + 1 &&
      cancelBounds.y + cancelBounds.height <= viewport.height + 1,
  );
  await page.screenshot({ path: path.join(output, "signing-in-small.png") });
  await cancel.click();
  await panel
    .getByRole("button", {
      name: "Continue with selected account",
      exact: true,
    })
    .waitFor();
  assert.equal(await provider.inputValue(), "openai_chatgpt_plan");
  await page.screenshot({ path: path.join(output, "cancelled-small.png") });
  checks.push(
    "Minimum-window account controls remain reachable without horizontal overflow",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      {
        checks,
        rendererErrors: errors,
        scope:
          "Real Electron/local Core and validated IPC; synthetic auth/status/catalog/configuration replies in the disposable process; no OAuth/browser authorization or model inference",
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ passed: checks.length, checks }, null, 2));
} catch (error) {
  if (page)
    await page
      .screenshot({ path: path.join(output, "failure.png") })
      .catch(() => {});
  throw error;
} finally {
  if (app) await app.close();
}
