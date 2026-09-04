import { describe, expect, it } from "vitest";

import {
  GlobalShortcutRegistry,
  type ShortcutRegistrar,
} from "./shortcut-manager";

class FakeRegistrar implements ShortcutRegistrar {
  readonly active = new Map<string, () => void>();
  failAccelerator: string | null = null;

  register(accelerator: string, callback: () => void): boolean {
    if (accelerator === this.failAccelerator || this.active.has(accelerator)) {
      return false;
    }
    this.active.set(accelerator, callback);
    return true;
  }

  unregister(accelerator: string): void {
    this.active.delete(accelerator);
  }
}

const binding = (accelerator: string) => ({
  accelerator,
  action: () => undefined,
});

describe("global shortcut registry", () => {
  it("gives Live Assist ownership of overlapping slide shortcuts", () => {
    const registrar = new FakeRegistrar();
    const registry = new GlobalShortcutRegistry(registrar);
    expect(
      registry.activate("run", [
        binding("Ctrl+Alt+PageUp"),
        binding("Ctrl+Alt+PageDown"),
      ]),
    ).toEqual({ registered: true });

    expect(
      registry.activate("live", [
        binding("Ctrl+Alt+Space"),
        binding("Ctrl+Alt+PageUp"),
        binding("Ctrl+Alt+PageDown"),
      ]),
    ).toEqual({ registered: true });
    expect(registry.getRegisteredAccelerators()).toEqual([
      "Ctrl+Alt+Space",
      "Ctrl+Alt+PageUp",
      "Ctrl+Alt+PageDown",
    ]);
    expect(registry.isOwnerRegistered("live")).toBe(true);
    expect(registry.isOwnerRegistered("run")).toBe(false);

    expect(registry.deactivate("live")).toEqual({ registered: true });
    expect(registry.getRegisteredAccelerators()).toEqual([
      "Ctrl+Alt+PageUp",
      "Ctrl+Alt+PageDown",
    ]);
    expect(registry.isOwnerRegistered("run")).toBe(true);
  });

  it("restores the previous binding set when registration fails", () => {
    const registrar = new FakeRegistrar();
    const registry = new GlobalShortcutRegistry(registrar);
    registry.activate("run", [binding("Ctrl+Alt+PageUp")]);
    registrar.failAccelerator = "Ctrl+Alt+Space";

    expect(
      registry.activate("live", [
        binding("Ctrl+Alt+Space"),
        binding("Ctrl+Alt+H"),
      ]),
    ).toEqual({
      registered: false,
      error_code: "SHORTCUT_REGISTRATION_FAILED",
    });
    expect(registry.getRegisteredAccelerators()).toEqual(["Ctrl+Alt+PageUp"]);
    expect([...registrar.active.keys()]).toEqual(["Ctrl+Alt+PageUp"]);
  });

  it("rejects duplicate and modifier-free bindings before touching the OS", () => {
    const registrar = new FakeRegistrar();
    const registry = new GlobalShortcutRegistry(registrar);
    expect(
      registry.activate("live", [
        binding("Ctrl+Alt+Space"),
        binding("Ctrl+Alt+Space"),
      ]),
    ).toEqual({ registered: false, error_code: "SHORTCUT_INVALID" });
    expect(registry.activate("live", [binding("Space")])).toEqual({
      registered: false,
      error_code: "SHORTCUT_INVALID",
    });
    expect(registrar.active.size).toBe(0);
  });
});
