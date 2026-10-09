import { createHash, randomUUID } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  statSync,
} from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const artifactDirectory = path.join(repositoryRoot, "artifacts", "installer");
const desktopPackage = JSON.parse(
  readFileSync(
    path.join(repositoryRoot, "apps", "desktop", "package.json"),
    "utf8",
  ),
);
const packageVersion = desktopPackage.version;
if (
  typeof packageVersion !== "string" ||
  !/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(packageVersion)
) {
  throw new Error("The desktop package version is invalid.");
}
const installerName = `Presenter-Copilot-${packageVersion}-x64-setup.exe`;
const configuredInstaller = process.env.PRESENTER_COPILOT_INSTALLER;
const installer = configuredInstaller
  ? path.resolve(configuredInstaller)
  : path.join(artifactDirectory, installerName);
const installSmokeOptIn = process.env.PRESENTER_CI_INSTALL_SMOKE === "1";
const hostedWindowsRunner =
  process.platform === "win32" &&
  process.env.GITHUB_ACTIONS === "true" &&
  process.env.RUNNER_ENVIRONMENT === "github-hosted" &&
  process.env.RUNNER_OS === "Windows";
const packagedSmokeArgument = "--presenter-copilot-smoke";

function report(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

function isChildPath(parent, candidate) {
  const relative = path.relative(path.resolve(parent), path.resolve(candidate));
  return (
    relative !== "" &&
    relative !== "." &&
    relative !== ".." &&
    !relative.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relative)
  );
}

function ensureWithin(parent, candidate, label) {
  if (!isChildPath(parent, candidate)) {
    throw new Error(`${label} is outside its required parent.`);
  }
}

function installerExists() {
  try {
    return statSync(installer).isFile() && statSync(installer).size > 0;
  } catch {
    return false;
  }
}

function assertSafeInstaller() {
  ensureWithin(artifactDirectory, installer, "Installer path");
  if (path.basename(installer).toLowerCase() !== installerName.toLowerCase()) {
    throw new Error("The installer filename does not match this package.");
  }
  if (!installerExists()) throw new Error("The installer artifact is missing.");
}

function cleanChildEnvironment(paths, dataRoot) {
  const systemRoot = process.env.SYSTEMROOT ?? process.env.WINDIR;
  if (!systemRoot) throw new Error("The Windows system root is unavailable.");
  return {
    SYSTEMROOT: systemRoot,
    WINDIR: systemRoot,
    COMSPEC: process.env.COMSPEC,
    USERPROFILE: process.env.USERPROFILE,
    LOCALAPPDATA: paths.localAppData,
    APPDATA: paths.appData,
    TEMP: paths.temp,
    TMP: paths.temp,
    PATH: path.join(systemRoot, "System32"),
    PATHEXT: process.env.PATHEXT ?? ".COM;.EXE;.BAT;.CMD",
    PRESENTER_COPILOT_DATA_ROOT: dataRoot,
  };
}

function runSilent(executable, args, env) {
  execFileSync(executable, args, {
    cwd: repositoryRoot,
    env,
    stdio: "ignore",
    timeout: 180_000,
    windowsHide: true,
  });
}

function terminateSmokeProcessTree(child) {
  if (!child.pid) {
    child.kill();
    return;
  }
  try {
    execFileSync("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      timeout: 15_000,
      windowsHide: true,
    });
  } catch {
    child.kill();
  }
}

function findUninstaller(installDirectory) {
  if (!existsSync(installDirectory)) return null;
  const name = readdirSync(installDirectory).find((entry) =>
    /^(uninstall|unins).*\.exe$/i.test(entry),
  );
  return name ? path.join(installDirectory, name) : null;
}

function presenterCoreCount() {
  try {
    const output = execFileSync(
      "tasklist.exe",
      ["/FI", "IMAGENAME eq presenter-core.exe", "/FO", "CSV", "/NH"],
      { encoding: "utf8", windowsHide: true },
    );
    return output
      .split(/\r?\n/)
      .filter((line) => line.toLowerCase().includes('"presenter-core.exe"'))
      .length;
  } catch {
    return null;
  }
}

function runPackagedSmoke(executable, env) {
  return new Promise((resolve, reject) => {
    let finished = false;
    let timedOut = false;
    let timeout;
    let timeoutGrace;
    let stdoutBytes = 0;
    let stderrBytes = 0;
    const child = spawn(executable, [packagedSmokeArgument], {
      cwd: path.dirname(executable),
      env,
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    const finish = (error, result) => {
      if (finished) return;
      finished = true;
      clearTimeout(timeout);
      clearTimeout(timeoutGrace);
      if (error) reject(error);
      else resolve(result);
    };

    child.stdout.on("data", (chunk) => {
      stdoutBytes += Buffer.byteLength(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderrBytes += Buffer.byteLength(chunk);
    });
    child.once("error", () => {
      finish(new Error("The installed application could not be launched."));
    });
    child.once("close", (code, signal) => {
      finish(null, {
        status:
          !timedOut && code === 0 && signal === null ? "verified" : "failed",
        exit_code: code,
        signal: signal ?? null,
        stdout_bytes: stdoutBytes,
        stderr_bytes: stderrBytes,
        timed_out: timedOut,
      });
    });
    timeout = setTimeout(() => {
      timedOut = true;
      terminateSmokeProcessTree(child);
      timeoutGrace = setTimeout(() => {
        finish(
          new Error("The installed application did not exit after timeout."),
        );
      }, 5_000);
    }, 90_000);
  });
}

function waitFor(predicate, label, timeoutMs = 30_000) {
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      if (predicate()) {
        resolve();
      } else if (Date.now() - startedAt >= timeoutMs) {
        reject(new Error(`${label} did not reach the expected state.`));
      } else {
        setTimeout(check, 250);
      }
    };
    check();
  });
}

function sha256File(filePath) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

async function launchAndVerify(executable, env, dataFile) {
  const before = presenterCoreCount();
  const smoke = await runPackagedSmoke(executable, env);
  await waitFor(
    () => presenterCoreCount() === before,
    "sidecar shutdown",
    10_000,
  );
  const after = presenterCoreCount();
  if (
    smoke.status !== "verified" ||
    before === null ||
    after === null ||
    after !== before
  ) {
    throw new Error("The installed package smoke or sidecar cleanup failed.");
  }
  if (!existsSync(dataFile) || statSync(dataFile).size === 0) {
    throw new Error(
      "The installed app did not create its disposable data file.",
    );
  }
  return smoke;
}

function uninstall(installDirectory, env) {
  const uninstaller = findUninstaller(installDirectory);
  if (!uninstaller) throw new Error("The installed uninstaller is missing.");
  runSilent(uninstaller, ["/S"], env);
}

function removeVerifiedRunnerRoot(root, runnerTemp) {
  if (!existsSync(root)) return;
  const resolvedRunnerTemp = realpathSync(runnerTemp);
  const resolvedRoot = realpathSync(root);
  ensureWithin(resolvedRunnerTemp, resolvedRoot, "Temporary cleanup path");
  if (
    !path.basename(resolvedRoot).startsWith("presenter-copilot-install-smoke-")
  ) {
    throw new Error("Temporary cleanup path does not have the expected name.");
  }
  rmSync(resolvedRoot, { recursive: true, force: true });
}

async function runHostedInstallSmoke() {
  const runnerTemp = process.env.RUNNER_TEMP;
  if (!runnerTemp || !existsSync(runnerTemp)) {
    throw new Error("The hosted runner temporary directory is unavailable.");
  }
  assertSafeInstaller();

  const root = path.join(
    path.resolve(runnerTemp),
    `presenter-copilot-install-smoke-${randomUUID()}`,
  );
  ensureWithin(runnerTemp, root, "Test workspace");
  if (existsSync(root))
    throw new Error("The unique test workspace already exists.");

  const paths = {
    installDirectory: path.join(root, "install"),
    localAppData: path.join(root, "local-app-data"),
    appData: path.join(root, "roaming-app-data"),
    temp: path.join(root, "temp"),
  };
  const dataRoot = path.join(paths.localAppData, "PresenterCopilot");
  const dataFile = path.join(dataRoot, "app.db");
  const executable = path.join(paths.installDirectory, "Presenter Copilot.exe");
  const childEnv = cleanChildEnvironment(paths, dataRoot);
  let stage = "preflight";

  try {
    mkdirSync(root, { recursive: false });
    mkdirSync(paths.localAppData, { recursive: true });
    mkdirSync(paths.appData, { recursive: true });
    mkdirSync(paths.temp, { recursive: true });
    if (/\s/.test(paths.installDirectory)) {
      throw new Error("The isolated install directory contains whitespace.");
    }
    if (presenterCoreCount() !== 0) {
      throw new Error(
        "The hosted runner already has a Presenter Core process.",
      );
    }

    stage = "first_install";
    runSilent(installer, ["/S", `/D=${paths.installDirectory}`], childEnv);
    await waitFor(
      () => existsSync(executable) && findUninstaller(paths.installDirectory),
      "first installation",
    );

    stage = "first_launch";
    await launchAndVerify(executable, childEnv, dataFile);
    const retainedHash = sha256File(dataFile);

    stage = "first_uninstall";
    uninstall(paths.installDirectory, childEnv);
    await waitFor(() => !existsSync(executable), "first uninstall");
    if (!existsSync(dataFile) || sha256File(dataFile) !== retainedHash) {
      throw new Error("Uninstall changed or removed the disposable app data.");
    }

    stage = "reinstall";
    runSilent(installer, ["/S", `/D=${paths.installDirectory}`], childEnv);
    await waitFor(
      () => existsSync(executable) && findUninstaller(paths.installDirectory),
      "reinstallation",
    );

    stage = "relaunch";
    await launchAndVerify(executable, childEnv, dataFile);
    const reinstalledHash = sha256File(dataFile);

    stage = "second_uninstall";
    uninstall(paths.installDirectory, childEnv);
    await waitFor(() => !existsSync(executable), "second uninstall");
    if (!existsSync(dataFile) || sha256File(dataFile) !== reinstalledHash) {
      throw new Error("The reinstalled app data did not survive uninstall.");
    }

    report({
      status: "verified",
      operation: "clean_machine_install_smoke",
      installer_name: path.basename(installer),
      runner_environment: "github-hosted-ephemeral-windows",
      install_cycles: 2,
      packaged_launches: 2,
      uninstall_cycles: 2,
      user_data_retained: true,
      data_root_isolated_under_runner_temp: true,
      sidecar_processes_after_launches: presenterCoreCount(),
      machine_mutated: true,
    });
  } catch (error) {
    report({
      status: "failed",
      operation: "clean_machine_install_smoke",
      installer_name: path.basename(installer),
      stage,
      error_code:
        error && typeof error === "object" && "code" in error
          ? String(error.code)
          : "INSTALL_SMOKE_FAILED",
      machine_mutated: true,
    });
    process.exitCode = 1;
  } finally {
    try {
      if (existsSync(executable) && findUninstaller(paths.installDirectory)) {
        uninstall(paths.installDirectory, childEnv);
      }
    } catch {
      // The hosted runner is discarded with the job if installer cleanup fails.
      process.exitCode = 1;
    }
    try {
      removeVerifiedRunnerRoot(root, runnerTemp);
    } catch {
      process.exitCode = 1;
    }
  }
}

if (installSmokeOptIn && !hostedWindowsRunner) {
  report({
    status: "refused",
    code: "EPHEMERAL_HOSTED_WINDOWS_RUNNER_REQUIRED",
    operation: "clean_machine_install_smoke",
    machine_mutated: false,
  });
  process.exitCode = 1;
} else if (installSmokeOptIn) {
  await runHostedInstallSmoke();
} else {
  const exists = installerExists();
  report({
    status: exists ? "manual_required" : "unavailable",
    code: exists
      ? "CLEAN_MACHINE_INSTALL_REQUIRED"
      : "INSTALLER_ARTIFACT_MISSING",
    operation: "clean_machine_install_smoke",
    installer_name: path.basename(installer),
    machine_mutated: false,
    instructions:
      "Local runs are read-only. GitHub-hosted Windows CI performs the disposable install cycle.",
  });
  process.exitCode = exists ? 0 : 1;
}
