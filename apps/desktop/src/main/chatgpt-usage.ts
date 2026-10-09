export const CHATGPT_USAGE_SETTINGS_URL = "https://chatgpt.com/settings/usage";

export async function openChatGPTUsageSettings(
  openExternal: (url: string) => Promise<void>,
): Promise<{ opened: true }> {
  await openExternal(CHATGPT_USAGE_SETTINGS_URL);
  return { opened: true };
}
