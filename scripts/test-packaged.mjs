import { execFileSync, spawn } from "node:child_process";
import { mkdtempSync, statSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const smokeArgument = "--presenter-copilot-smoke";

function report(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

function packagedExecutable() {
  const configured = process.env.PRESENTER_COPILOT_PACKAGED_EXE;
  const candidates = configured
    ? [path.resolve(configured)]
    : [
        path.join(
          repositoryRoot,
          "artifacts",
          "installer",
          "win-unpacked",
          "Presenter Copilot.exe",
        ),
        path.join(
          repositoryRoot,
          "artifacts",
          "win-unpacked",
          "Presenter Copilot.exe",
        ),
      ];
  for (const candidate of candidates) {
    try {
      if (statSync(candidate).isFile() && statSync(candidate).size > 0)
        return candidate;
    } catch {
      // Continue through the bounded candidate list.
    }
  }
  return null;
}

function presenterCoreCount() {
  if (process.platform !== "win32") return null;
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

function runSmoke(executable, dataRoot) {
  return new Promise((resolve) => {
    let settled = false;
    let timedOut = false;
    let timeout;
    let timeoutGrace;
    const child = spawn(executable, [smokeArgument], {
      cwd: path.dirname(executable),
      // The packaged app resolves the bundled sidecar by absolute path, so a
      // system Python on PATH cannot satisfy this smoke accidentally.
      env: {
        SYSTEMROOT: process.env.SYSTEMROOT,
        WINDIR: process.env.WINDIR,
        COMSPEC: process.env.COMSPEC,
        TEMP: process.env.TEMP,
        TMP: process.env.TMP,
        USERPROFILE: process.env.USERPROFILE,
        LOCALAPPDATA: process.env.LOCALAPPDATA,
        APPDATA: process.env.APPDATA,
        PATH: path.join(
          process.env.SYSTEMROOT ?? process.env.WINDIR ?? "C:\\Windows",
          "System32",
        ),
        PATHEXT: process.env.PATHEXT,
        PRESENTER_COPILOT_DATA_ROOT: dataRoot,
      },
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdoutBytes = 0;
    let stderrBytes = 0;
    child.stdout.on("data", (chunk) => {
      stdoutBytes += Buffer.byteLength(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderrBytes += Buffer.byteLength(chunk);
    });
    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      clearTimeout(timeoutGrace);
      resolve(result);
    };
    timeout = setTimeout(() => {
      timedOut = true;
      child.kill();
      // Require close finalization, but do not wait indefinitely for a broken
      // child process before the caller checks for orphaned sidecars.
      timeoutGrace = setTimeout(() => {
        finish({
          status: "failed",
          code: "PACKAGED_SMOKE_TIMEOUT",
          stdout_bytes: stdoutBytes,
          stderr_bytes: stderrBytes,
        });
      }, 5_000);
    }, 90_000);
    child.once("error", () => {
      finish({
        status: "failed",
        code: "PACKAGED_SMOKE_START_FAILED",
        stdout_bytes: stdoutBytes,
        stderr_bytes: stderrBytes,
      });
    });
    child.once("close", (code, signal) => {
      finish({
        status:
          !timedOut && code === 0 && signal === null ? "verified" : "failed",
        code:
          !timedOut && code === 0 && signal === null
            ? undefined
            : timedOut
              ? "PACKAGED_SMOKE_TIMEOUT"
              : "PACKAGED_SMOKE_FAILED",
        exit_code: code,
        signal: signal ?? null,
        stdout_bytes: stdoutBytes,
        stderr_bytes: stderrBytes,
      });
    });
  });
}

if (process.platform !== "win32") {
  report({
    status: "unavailable",
    code: "WINDOWS_REQUIRED",
    operation: "packaged_smoke",
  });
  process.exitCode = 1;
} else {
  const executable = packagedExecutable();
  if (!executable) {
    report({
      status: "unavailable",
      code: "PACKAGED_ARTIFACT_MISSING",
      operation: "packaged_smoke",
    });
    process.exitCode = 1;
  } else {
    const temporaryRoot = mkdtempSync(
      path.join(os.tmpdir(), "presenter-copilot-packaged-"),
    );
    const before = presenterCoreCount();
    try {
      const result = await runSmoke(
        executable,
        path.join(temporaryRoot, "data"),
      );
      const after = presenterCoreCount();
      const orphaned = before !== null && after !== null && after > before;
      const finalResult = {
        ...result,
        operation: "packaged_smoke",
        executable_name: path.basename(executable),
        sidecar_processes_before: before,
        sidecar_processes_after: after,
        model_downloaded: false,
        renderer_supplied_filesystem_path: false,
        orphaned_sidecar_detected: orphaned,
      };
      if (orphaned && finalResult.status === "verified") {
        finalResult.status = "failed";
        finalResult.code = "PACKAGED_SIDECAR_ORPHANED";
      }
      report(finalResult);
      process.exitCode = finalResult.status === "verified" ? 0 : 1;
    } finally {
      rmSync(temporaryRoot, { recursive: true, force: true });
    }
  }
}
