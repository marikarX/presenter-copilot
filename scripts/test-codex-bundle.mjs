import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const expectedVersion = "codex-cli 0.153.4";
const expectedSha256 =
  "444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b";

function isFile(filePath) {
  try {
    return statSync(filePath).isFile() && statSync(filePath).size > 0;
  } catch {
    return false;
  }
}

function packagedResources() {
  const candidates = [
    path.join(
      repositoryRoot,
      "artifacts",
      "installer",
      "win-unpacked",
      "resources",
    ),
    path.join(repositoryRoot, "artifacts", "win-unpacked", "resources"),
  ];
  return candidates.find((candidate) =>
    isFile(path.join(candidate, "codex", "codex.exe")),
  );
}

function sha256(filePath) {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(filePath);
    stream.on("error", reject);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

if (process.platform !== "win32") {
  process.stdout.write(
    `${JSON.stringify(
      {
        status: "unavailable",
        code: "WINDOWS_REQUIRED",
        operation: "codex_bundle",
      },
      null,
      2,
    )}\n`,
  );
  process.exitCode = 1;
} else {
  const resources = packagedResources();
  if (!resources) {
    process.stdout.write(
      `${JSON.stringify(
        {
          status: "failed",
          code: "CODEX_BUNDLE_MISSING",
          operation: "codex_bundle",
        },
        null,
        2,
      )}\n`,
    );
    process.exitCode = 1;
  } else {
    const executable = path.join(resources, "codex", "codex.exe");
    const license = path.join(resources, "licenses", "codex", "LICENSE");
    const notice = path.join(resources, "licenses", "codex", "NOTICE");
    const digest = await sha256(executable);
    const version = execFileSync(executable, ["--version"], {
      encoding: "utf8",
      windowsHide: true,
    }).trim();
    const verified =
      digest === expectedSha256 &&
      version === expectedVersion &&
      isFile(license) &&
      isFile(notice);
    process.stdout.write(
      `${JSON.stringify(
        {
          status: verified ? "verified" : "failed",
          code: verified ? undefined : "CODEX_BUNDLE_INVALID",
          operation: "codex_bundle",
          version,
          sha256: digest,
          license_present: isFile(license),
          notice_present: isFile(notice),
        },
        null,
        2,
      )}\n`,
    );
    process.exitCode = verified ? 0 : 1;
  }
}
