import { execFileSync, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const appDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const require = createRequire(import.meta.url);
const viteCli = path.join(
  appDirectory,
  "node_modules",
  "vite",
  "bin",
  "vite.js",
);
const typeScriptCli = path.join(
  appDirectory,
  "node_modules",
  "typescript",
  "bin",
  "tsc",
);
let electronBinary;
try {
  // Electron's package entry downloads the matching development binary if a
  // package manager did not run its optional install hook.
  electronBinary = require("electron");
} catch {
  electronBinary = null;
}
const mainEntry = path.join(appDirectory, "dist", "main", "main.js");
const devServerUrl = "http://127.0.0.1:5173";

if (
  !existsSync(viteCli) ||
  !existsSync(typeScriptCli) ||
  !electronBinary ||
  !existsSync(electronBinary)
) {
  throw new Error(
    "Desktop dependencies are missing. Run `pnpm setup` from the repository root.",
  );
}

execFileSync(
  process.execPath,
  [typeScriptCli, "-p", path.join(appDirectory, "tsconfig.main.json")],
  {
    cwd: appDirectory,
    stdio: "inherit",
    windowsHide: true,
  },
);

const vite = spawn(
  process.execPath,
  [viteCli, "--host", "127.0.0.1", "--strictPort"],
  {
    cwd: appDirectory,
    stdio: "inherit",
    windowsHide: true,
  },
);

async function waitForDevServer() {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const response = await fetch(`${devServerUrl}/`);
      if (response.ok) return;
    } catch {
      // Vite is still starting.
    }
    await delay(100);
  }
  throw new Error("Vite dev server did not become ready.");
}

await waitForDevServer();

const electron = spawn(electronBinary, [mainEntry], {
  cwd: appDirectory,
  env: {
    ...process.env,
    PRESENTER_COPILOT_DEV_SERVER_URL: devServerUrl,
    PRESENTER_COPILOT_DEV_MODE: "1",
    PRESENTER_COPILOT_REPO_ROOT: path.resolve(appDirectory, "..", ".."),
  },
  stdio: "inherit",
  windowsHide: false,
});

function stopChildren() {
  if (!vite.killed) vite.kill();
  if (!electron.killed) electron.kill();
}

process.on("SIGINT", stopChildren);
process.on("SIGTERM", stopChildren);
vite.on("exit", (code) => {
  if (code !== 0 && electron.exitCode === null) electron.kill();
});
electron.on("exit", (code, signal) => {
  if (!vite.killed) vite.kill();
  process.exitCode = code ?? (signal ? 1 : 0);
});
