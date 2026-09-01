import path from "node:path";
import { pathToFileURL } from "node:url";

import { describe, expect, it } from "vitest";

import {
  DEV_RENDERER_ORIGIN,
  isExpectedDevelopmentUrl,
  isTrustedRendererSender,
  selectRendererLoadTarget,
  type RendererFrameReference,
  type RendererValidationOptions,
} from "./sender-validation";

const bundledRendererPath = path.resolve("dist", "renderer", "index.html");
const policy: RendererValidationOptions = {
  bundledRendererPath,
  allowDevelopmentRenderer: true,
};

function frame(
  url: string,
  processId = 10,
  routingId = 20,
): RendererFrameReference {
  return { url, processId, routingId };
}

describe("renderer sender validation", () => {
  it("accepts only the exact bundled file in the main frame", () => {
    const mainFrame = frame(pathToFileURL(bundledRendererPath).href);

    expect(isTrustedRendererSender(mainFrame, mainFrame, policy)).toBe(true);
    expect(
      isTrustedRendererSender(
        frame(pathToFileURL(bundledRendererPath).href, 10, 21),
        mainFrame,
        policy,
      ),
    ).toBe(false);
    expect(
      isTrustedRendererSender(
        frame(pathToFileURL(path.join("dist", "other.html")).href),
        mainFrame,
        policy,
      ),
    ).toBe(false);
    expect(isTrustedRendererSender(null, mainFrame, policy)).toBe(false);
  });

  it("accepts only the parsed loopback Vite renderer URL in development", () => {
    const mainFrame = frame(`${DEV_RENDERER_ORIGIN}/`);

    expect(isExpectedDevelopmentUrl(`${DEV_RENDERER_ORIGIN}/`)).toBe(true);
    expect(isTrustedRendererSender(mainFrame, mainFrame, policy)).toBe(true);

    for (const rejectedUrl of [
      "http://localhost:5173/",
      "https://127.0.0.1:5173/",
      "http://127.0.0.1:5174/",
      "http://127.0.0.1:5173/other",
      "http://127.0.0.1:5173/?remote=true",
      "https://attacker.example/",
    ]) {
      expect(isExpectedDevelopmentUrl(rejectedUrl)).toBe(false);
      expect(
        isTrustedRendererSender(frame(rejectedUrl), mainFrame, policy),
      ).toBe(false);
    }

    expect(
      isTrustedRendererSender(mainFrame, mainFrame, {
        ...policy,
        allowDevelopmentRenderer: false,
      }),
    ).toBe(false);
  });

  it("uses development content only for an unpackaged explicit dev run", () => {
    expect(
      selectRendererLoadTarget({
        bundledRendererPath,
        developmentUrl: `${DEV_RENDERER_ORIGIN}/`,
        isPackaged: false,
        isDevelopment: true,
      }),
    ).toEqual({ type: "development", url: `${DEV_RENDERER_ORIGIN}/` });

    for (const options of [
      {
        developmentUrl: "https://attacker.example/",
        isPackaged: false,
        isDevelopment: true,
      },
      {
        developmentUrl: `${DEV_RENDERER_ORIGIN}/`,
        isPackaged: true,
        isDevelopment: true,
      },
      {
        developmentUrl: `${DEV_RENDERER_ORIGIN}/`,
        isPackaged: false,
        isDevelopment: false,
      },
    ]) {
      expect(
        selectRendererLoadTarget({ bundledRendererPath, ...options }),
      ).toEqual({ type: "bundled", path: bundledRendererPath });
    }
  });
});
