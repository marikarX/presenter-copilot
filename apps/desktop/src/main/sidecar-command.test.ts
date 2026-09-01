import { delimiter } from "node:path";

import { describe, expect, it } from "vitest";

import { createSidecarCommand } from "./sidecar-command";

describe("sidecar command configuration", () => {
  it("returns the constructor configuration with no unused nested options", () => {
    const command = createSidecarCommand();

    expect(command.args).toEqual(["-u", "-m", "presenter_core"]);
    expect(command.cwd).toBeTruthy();
    expect(command.env.PYTHONUNBUFFERED).toBe("1");
    expect(command.env.PYTHONPATH?.split(delimiter)).toContain(command.cwd);
    expect("options" in command).toBe(false);
  });
});
