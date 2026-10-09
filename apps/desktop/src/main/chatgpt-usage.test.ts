import { describe, expect, it, vi } from "vitest";

import { openChatGPTUsageSettings } from "./chatgpt-usage";

describe("ChatGPT plan usage settings", () => {
  it("opens only the fixed ChatGPT usage settings page", async () => {
    const openExternal = vi.fn(async (url: string) => {
      expect(url).toBe("https://chatgpt.com/settings/usage");
    });

    await expect(openChatGPTUsageSettings(openExternal)).resolves.toEqual({
      opened: true,
    });
    expect(openExternal).toHaveBeenCalledExactlyOnceWith(
      "https://chatgpt.com/settings/usage",
    );
  });

  it("does not report success when the system browser cannot open it", async () => {
    const openExternal = vi.fn(async (url: string) => {
      expect(url).toBe("https://chatgpt.com/settings/usage");
      throw new Error("browser unavailable");
    });

    await expect(openChatGPTUsageSettings(openExternal)).rejects.toThrow(
      "browser unavailable",
    );
  });
});
