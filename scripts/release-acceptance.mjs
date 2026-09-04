import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const uv = process.platform === "win32" ? "uv.exe" : "uv";
const environment = { ...process.env };
delete environment.OPENAI_API_KEY;
delete environment.PRESENTER_COPILOT_DEV_MODE;
delete environment.PRESENTER_COPILOT_TEST_PROVIDER;
delete environment.PRESENTER_CORE_DIR;
delete environment.PRESENTER_CORE_PYTHON;
delete environment.PRESENTER_COPILOT_REPO_ROOT;
delete environment.PYTHONPATH;
delete environment.PYTHONUNBUFFERED;

function run(command, args) {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: repositoryRoot,
      env: environment,
      shell: false,
      windowsHide: true,
      stdio: "inherit",
    });
    child.once("error", () => resolve(1));
    child.once("close", (code, signal) =>
      resolve(code === 0 && signal === null ? 0 : 1),
    );
  });
}

const e2eExit = await run(uv, [
  "run",
  "--directory",
  "core",
  "--project",
  ".",
  "--locked",
  "python",
  "-m",
  "presenter_core.tools.release_e2e",
]);
if (e2eExit !== 0) process.exitCode = e2eExit;

if (process.env.PRESENTER_COPILOT_RUN_PACKAGED_SMOKE === "1") {
  const packagedExit = await run(process.execPath, [
    path.join(repositoryRoot, "scripts", "test-packaged.mjs"),
  ]);
  if (packagedExit !== 0) process.exitCode = packagedExit;
}
