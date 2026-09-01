import { existsSync } from "node:fs";
import path from "node:path";

import type { SpawnOptions } from "node:child_process";

export interface SidecarCommand {
  command: string;
  args: string[];
  cwd: string;
  options: SpawnOptions;
}

export function resolveCoreDirectory(): string {
  if (process.env.PRESENTER_CORE_DIR)
    return path.resolve(process.env.PRESENTER_CORE_DIR);
  const repositoryRoot = process.env.PRESENTER_COPILOT_REPO_ROOT
    ? path.resolve(process.env.PRESENTER_COPILOT_REPO_ROOT)
    : path.resolve(__dirname, "../../../..");
  return path.join(repositoryRoot, "core");
}

export function resolvePythonCommand(coreDirectory: string): string {
  if (process.env.PRESENTER_CORE_PYTHON)
    return process.env.PRESENTER_CORE_PYTHON;

  const virtualEnvironmentCandidates =
    process.platform === "win32"
      ? [path.join(coreDirectory, ".venv", "Scripts", "python.exe")]
      : [path.join(coreDirectory, ".venv", "bin", "python")];
  const virtualEnvironmentPython =
    virtualEnvironmentCandidates.find(existsSync);
  if (virtualEnvironmentPython) return virtualEnvironmentPython;

  return process.platform === "win32" ? "python.exe" : "python3";
}

export function createSidecarCommand(): SidecarCommand {
  const cwd = resolveCoreDirectory();
  const inheritedPythonPath = process.env.PYTHONPATH;
  const pythonPath = [cwd, inheritedPythonPath]
    .filter(Boolean)
    .join(path.delimiter);

  return {
    command: resolvePythonCommand(cwd),
    args: ["-u", "-m", "presenter_core"],
    cwd,
    options: {
      cwd,
      env: {
        ...process.env,
        PYTHONPATH: pythonPath,
        PYTHONUNBUFFERED: "1",
      },
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    },
  };
}
