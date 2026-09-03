export const DEFAULT_SHORTCUTS = {
  push_to_assist: "Ctrl+Alt+Space",
  show_hide: "Ctrl+Alt+H",
  expand_collapse: "Ctrl+Alt+Enter",
  previous_cue: "Ctrl+Alt+Left",
  next_cue: "Ctrl+Alt+Right",
  clear: "Ctrl+Alt+Backspace",
  previous_slide: "Ctrl+Alt+PageUp",
  next_slide: "Ctrl+Alt+PageDown",
} as const;

export type ShortcutName = keyof typeof DEFAULT_SHORTCUTS;
export type ShortcutBindings = Record<ShortcutName, string>;

export type ShortcutBinding = {
  accelerator: string;
  action: () => void;
};

export type ShortcutRegistrar = {
  register: (accelerator: string, callback: () => void) => boolean;
  unregister: (accelerator: string) => void;
};

export type ShortcutOwner = "run" | "live";

export type ShortcutRegistrationResult = {
  registered: boolean;
  error_code?: "SHORTCUT_REGISTRATION_FAILED" | "SHORTCUT_INVALID";
};

export function isValidGlobalShortcut(value: string): boolean {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 80 &&
    /(?:CommandOrControl|Ctrl|Alt|Shift|Command|Super)\+/i.test(value) &&
    !/[\r\n]/.test(value)
  );
}

export function validateShortcutBindings(
  bindings: Iterable<ShortcutBinding>,
): boolean {
  const seen = new Set<string>();
  for (const binding of bindings) {
    if (
      !isValidGlobalShortcut(binding.accelerator) ||
      typeof binding.action !== "function" ||
      seen.has(binding.accelerator)
    ) {
      return false;
    }
    seen.add(binding.accelerator);
  }
  return true;
}

/**
 * Own all app global shortcuts in one transactional registry. Electron
 * unregisters existing accelerators before a replacement can be attempted;
 * this class restores the previous set if any new registration is rejected.
 */
export class GlobalShortcutRegistry {
  private readonly registrar: ShortcutRegistrar;
  private readonly owners = new Map<ShortcutOwner, ShortcutBinding[]>();
  private registered = new Map<string, ShortcutBinding>();

  constructor(registrar: ShortcutRegistrar) {
    this.registrar = registrar;
  }

  activate(
    owner: ShortcutOwner,
    bindings: ShortcutBinding[],
  ): ShortcutRegistrationResult {
    if (!validateShortcutBindings(bindings)) {
      return { registered: false, error_code: "SHORTCUT_INVALID" };
    }
    const previous = this.owners.get(owner);
    this.owners.set(owner, [...bindings]);
    const result = this.reconcile();
    if (!result.registered && previous) this.owners.set(owner, previous);
    else if (!result.registered) this.owners.delete(owner);
    return result;
  }

  deactivate(owner: ShortcutOwner): ShortcutRegistrationResult {
    const previous = this.owners.get(owner);
    if (!previous) return { registered: true };
    this.owners.delete(owner);
    const result = this.reconcile();
    if (!result.registered) this.owners.set(owner, previous);
    return result;
  }

  clear(): void {
    for (const accelerator of this.registered.keys()) {
      this.registrar.unregister(accelerator);
    }
    this.registered.clear();
    this.owners.clear();
  }

  getRegisteredAccelerators(): string[] {
    return [...this.registered.keys()];
  }

  isOwnerRegistered(owner: ShortcutOwner): boolean {
    const bindings = this.owners.get(owner);
    return (
      bindings !== undefined &&
      bindings.every(
        (binding) => this.registered.get(binding.accelerator) === binding,
      )
    );
  }

  private reconcile(): ShortcutRegistrationResult {
    const desired = new Map<string, ShortcutBinding>();
    // Live owns the overlapping slide accelerators while a Live session is
    // active; Run bindings are restored when Live deactivates.
    for (const owner of ["live", "run"] as const) {
      for (const binding of this.owners.get(owner) ?? []) {
        if (desired.has(binding.accelerator)) {
          if (owner === "run") continue;
          return this.rollback(
            new Map(this.registered),
            "SHORTCUT_REGISTRATION_FAILED",
          );
        }
        desired.set(binding.accelerator, binding);
      }
    }
    const previous = new Map(this.registered);
    for (const accelerator of previous.keys())
      this.registrar.unregister(accelerator);
    this.registered.clear();
    const added: string[] = [];
    try {
      for (const [accelerator, binding] of desired) {
        if (!this.registrar.register(accelerator, binding.action)) {
          for (const registered of added) this.registrar.unregister(registered);
          this.registered.clear();
          return this.rollback(previous, "SHORTCUT_REGISTRATION_FAILED");
        }
        added.push(accelerator);
        this.registered.set(accelerator, binding);
      }
      return { registered: true };
    } catch {
      for (const registered of added) this.registrar.unregister(registered);
      this.registered.clear();
      return this.rollback(previous, "SHORTCUT_REGISTRATION_FAILED");
    }
  }

  private rollback(
    previous: Map<string, ShortcutBinding>,
    errorCode: "SHORTCUT_REGISTRATION_FAILED",
  ): ShortcutRegistrationResult {
    for (const accelerator of this.registered.keys())
      this.registrar.unregister(accelerator);
    this.registered.clear();
    try {
      for (const [accelerator, binding] of previous) {
        if (!this.registrar.register(accelerator, binding.action)) {
          for (const restored of this.registered.keys())
            this.registrar.unregister(restored);
          this.registered.clear();
          return { registered: false, error_code: errorCode };
        }
        this.registered.set(accelerator, binding);
      }
    } catch {
      for (const restored of this.registered.keys())
        this.registrar.unregister(restored);
      this.registered.clear();
      return { registered: false, error_code: errorCode };
    }
    return { registered: false, error_code: errorCode };
  }
}
