import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { CoreProcessClient } from "./core-client";
import { resolvePythonCommand } from "./sidecar-command";
import { isHealthResult, type CoreMetadata } from "../shared/protocol";

function findRepositoryRoot(): string {
  let directory = path.dirname(__filename);
  while (directory !== path.dirname(directory)) {
    if (
      existsSync(path.join(directory, "core", "presenter_core", "__main__.py"))
    )
      return directory;
    directory = path.dirname(directory);
  }
  throw new Error(
    "Could not locate the repository root for the sidecar integration test.",
  );
}

describe("Python sidecar integration", () => {
  it("completes the real ready/hello/health/shutdown lifecycle", async () => {
    const repositoryRoot = findRepositoryRoot();
    const coreDirectory = path.join(repositoryRoot, "core");
    const pythonCommand = resolvePythonCommand(coreDirectory);
    const dataRoot = mkdtempSync(
      path.join(tmpdir(), "presenter-copilot-core-"),
    );
    const client = new CoreProcessClient({
      command: pythonCommand,
      args: ["-u", "-m", "presenter_core"],
      cwd: coreDirectory,
      env: {
        ...process.env,
        PYTHONPATH: [coreDirectory, process.env.PYTHONPATH]
          .filter(Boolean)
          .join(path.delimiter),
        PYTHONUNBUFFERED: "1",
        PRESENTER_COPILOT_DATA_ROOT: dataRoot,
      },
      startupTimeoutMs: 5_000,
      requestTimeoutMs: 3_000,
      shutdownTimeoutMs: 3_000,
    });

    try {
      const ready = await client.start();
      expect(ready.protocol_version).toBe(1);
      expect(ready.core_version).toBe("0.1.0");

      const hello = await client.request<CoreMetadata>("core.hello");
      expect(hello).toEqual(ready);

      const health = await client.request("core.health");
      expect(isHealthResult(health)).toBe(true);

      await client.shutdown();
      expect(client.getStatus().state).toBe("stopped");
    } finally {
      await client.shutdown();
      rmSync(dataRoot, { recursive: true, force: true });
    }
  }, 15_000);
});
