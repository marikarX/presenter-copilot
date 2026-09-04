import { delimiter } from "node:path";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";

import { describe, expect, it } from "vitest";

import {
  createSidecarCommand,
  SidecarResolutionError,
} from "./sidecar-command";

describe("sidecar command configuration", () => {
  it("returns the constructor configuration with no unused nested options", () => {
    const command = createSidecarCommand();

    expect(command.args).toEqual(["-u", "-m", "presenter_core"]);
    expect(command.cwd).toBeTruthy();
    expect(command.env.PYTHONUNBUFFERED).toBe("1");
    expect(command.env.PYTHONPATH?.split(delimiter)).toContain(command.cwd);
    expect("options" in command).toBe(false);
    expect(command.shell).toBe(false);
  });

  it("honors explicit development overrides without changing packaged resolution", () => {
    const command = createSidecarCommand({
      env: {
        PRESENTER_CORE_DIR: "C:\\Program Files\\Presenter Copilot\\core",
        PRESENTER_CORE_PYTHON: "C:\\Program Files\\Python\\python.exe",
        PYTHONPATH: "C:\\workspace",
      },
      platform: "win32",
    });

    expect(command.command).toBe("C:\\Program Files\\Python\\python.exe");
    expect(command.cwd).toBe("C:\\Program Files\\Presenter Copilot\\core");
    expect(command.args).toEqual(["-u", "-m", "presenter_core"]);
  });

  it("resolves the frozen Windows sidecar under resources, including spaces", () => {
    const root = mkdtempSync(`${tmpdir()}\\Presenter Copilot resources-`);
    const sidecarDirectory = `${root}\\sidecar\\presenter-core`;
    mkdirSync(sidecarDirectory, { recursive: true });
    const executable = `${sidecarDirectory}\\presenter-core.exe`;
    writeFileSync(executable, "frozen-sidecar-placeholder");
    try {
      const command = createSidecarCommand({
        isPackaged: true,
        platform: "win32",
        resourcesPath: root,
        env: {
          PATH: "C:\\Windows\\System32",
          OPENAI_API_KEY: "explicit-bootstrap-only",
          NODE_OPTIONS: "--inspect",
          PYTHONPATH: "C:\\untrusted",
        },
      });
      expect(command.command).toBe(executable);
      expect(command.args).toEqual([]);
      expect(command.cwd).toBe(sidecarDirectory);
      expect(command.shell).toBe(false);
      expect(command.env.OPENAI_API_KEY).toBe("explicit-bootstrap-only");
      expect(command.env.NODE_OPTIONS).toBeUndefined();
      expect(command.env.PYTHONPATH).toBeUndefined();
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails deterministically instead of falling back to Python when packaged sidecar is absent", () => {
    const root = mkdtempSync(`${tmpdir()}\\Presenter Copilot missing-`);
    try {
      expect(() =>
        createSidecarCommand({
          isPackaged: true,
          platform: "win32",
          resourcesPath: root,
          env: {},
        }),
      ).toThrowError(SidecarResolutionError);
      try {
        createSidecarCommand({
          isPackaged: true,
          platform: "win32",
          resourcesPath: root,
          env: {},
        });
      } catch (error) {
        expect(error).toMatchObject({ code: "SIDECAR_BUNDLE_MISSING" });
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
