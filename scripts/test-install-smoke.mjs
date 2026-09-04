import { statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const configuredInstaller = process.env.PRESENTER_COPILOT_INSTALLER;
const defaultInstaller = path.join(
  repositoryRoot,
  "artifacts",
  "installer",
  "Presenter-Copilot-0.1.0-x64-setup.exe",
);
const installer = configuredInstaller
  ? path.resolve(configuredInstaller)
  : defaultInstaller;

function write(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

let exists = false;
try {
  exists = statSync(installer).isFile() && statSync(installer).size > 0;
} catch {
  exists = false;
}

write({
  status: exists ? "manual_required" : "unavailable",
  code: exists
    ? "CLEAN_MACHINE_INSTALL_REQUIRED"
    : "INSTALLER_ARTIFACT_MISSING",
  operation: "clean_machine_install_smoke",
  installer_name: path.basename(installer),
  mutates_machine: false,
  instructions:
    "Use the clean-machine checklist on a fresh Windows profile or VM.",
});

// Installation is deliberately manual: this helper never installs, uninstalls,
// or deletes user data on the developer machine.
process.exitCode = exists ? 0 : 1;
