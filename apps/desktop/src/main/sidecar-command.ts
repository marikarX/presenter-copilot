import { existsSync, statSync } from "node:fs";
import path from "node:path";

export interface SidecarCommand {
  command: string;
  args: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
  shell?: false;
}

export class SidecarResolutionError extends Error {
  readonly code = "SIDECAR_BUNDLE_MISSING";
  readonly sidecarPath: string;

  constructor(sidecarPath: string) {
    super("The packaged Python core sidecar is missing or not a usable file.");
    this.name = "SidecarResolutionError";
    this.sidecarPath = sidecarPath;
  }
}

export interface SidecarCommandOptions {
  isPackaged?: boolean;
  platform?: NodeJS.Platform;
  resourcesPath?: string;
  env?: NodeJS.ProcessEnv;
}

const PACKAGED_ENV_KEYS = [
  "APPDATA",
  "COMSPEC",
  "HOMEDRIVE",
  "HOMEPATH",
  "LOCALAPPDATA",
  "OPENAI_API_KEY",
  "PATH",
  "PATHEXT",
  "PROGRAMDATA",
  "PRESENTER_COPILOT_DATA_ROOT",
  "TEMP",
  "TMP",
  "USERPROFILE",
  "WINDIR",
  "SYSTEMROOT",
] as const;

export function resolveCoreDirectory(
  env: NodeJS.ProcessEnv = process.env,
): string {
  if (env.PRESENTER_CORE_DIR) return path.resolve(env.PRESENTER_CORE_DIR);
  const repositoryRoot = env.PRESENTER_COPILOT_REPO_ROOT
    ? path.resolve(env.PRESENTER_COPILOT_REPO_ROOT)
    : path.resolve(__dirname, "../../../..");
  return path.join(repositoryRoot, "core");
}

export function resolvePythonCommand(
  coreDirectory: string,
  options: { env?: NodeJS.ProcessEnv; platform?: NodeJS.Platform } = {},
): string {
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  if (env.PRESENTER_CORE_PYTHON) return env.PRESENTER_CORE_PYTHON;

  const virtualEnvironmentCandidates =
    platform === "win32"
      ? [path.join(coreDirectory, ".venv", "Scripts", "python.exe")]
      : [path.join(coreDirectory, ".venv", "bin", "python")];
  const virtualEnvironmentPython =
    virtualEnvironmentCandidates.find(existsSync);
  if (virtualEnvironmentPython) return virtualEnvironmentPython;

  return platform === "win32" ? "python.exe" : "python3";
}

export function resolvePackagedSidecarPath(
  resourcesPath: string,
  platform: NodeJS.Platform = process.platform,
): string {
  const executableName =
    platform === "win32" ? "presenter-core.exe" : "presenter-core";
  return path.join(resourcesPath, "sidecar", "presenter-core", executableName);
}

export function resolvePackagedCodexPath(
  resourcesPath: string,
  platform: NodeJS.Platform = process.platform,
): string {
  const executableName = platform === "win32" ? "codex.exe" : "codex";
  return path.join(resourcesPath, "codex", executableName);
}

function minimizedPackagedEnvironment(
  source: NodeJS.ProcessEnv,
): NodeJS.ProcessEnv {
  const result: NodeJS.ProcessEnv = {};
  for (const key of PACKAGED_ENV_KEYS) {
    const value = source[key];
    if (typeof value === "string") result[key] = value;
  }
  return result;
}

function isUsableExecutable(filePath: string): boolean {
  try {
    const stats = statSync(filePath);
    return stats.isFile() && stats.size > 0;
  } catch {
    return false;
  }
}

export function createSidecarCommand(
  options: SidecarCommandOptions = {},
): SidecarCommand {
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  const isPackaged = options.isPackaged ?? false;

  if (isPackaged) {
    const resourcesPath = path.resolve(
      options.resourcesPath ?? process.resourcesPath,
    );
    const command = resolvePackagedSidecarPath(resourcesPath, platform);
    if (!isUsableExecutable(command)) throw new SidecarResolutionError(command);
    const packagedEnv = minimizedPackagedEnvironment(env);
    packagedEnv.PRESENTER_CODEX_EXECUTABLE = resolvePackagedCodexPath(
      resourcesPath,
      platform,
    );
    packagedEnv.PRESENTER_CODEX_BUNDLED = "1";
    return {
      command,
      args: [],
      cwd: path.dirname(command),
      env: packagedEnv,
      shell: false,
    };
  }

  const cwd = resolveCoreDirectory(env);
  const inheritedPythonPath = env.PYTHONPATH;
  const pythonPath = [cwd, inheritedPythonPath]
    .filter(Boolean)
    .join(path.delimiter);

  return {
    command: resolvePythonCommand(cwd, { env, platform }),
    args: ["-u", "-m", "presenter_core"],
    cwd,
    env: {
      ...env,
      PYTHONPATH: pythonPath,
      PYTHONUNBUFFERED: "1",
    },
    shell: false,
  };
}
