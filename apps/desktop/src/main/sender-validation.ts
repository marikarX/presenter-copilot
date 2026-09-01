import path from "node:path";
import { fileURLToPath } from "node:url";

export const DEV_RENDERER_ORIGIN = "http://127.0.0.1:5173";

export interface RendererFrameReference {
  readonly url: string;
  readonly processId: number;
  readonly routingId: number;
}

export interface RendererValidationOptions {
  readonly bundledRendererPath: string;
  readonly allowDevelopmentRenderer: boolean;
}

export interface RendererLoadOptions {
  readonly bundledRendererPath: string;
  readonly developmentUrl?: string;
  readonly isPackaged: boolean;
  readonly isDevelopment: boolean;
}

export type RendererLoadTarget =
  { type: "bundled"; path: string } | { type: "development"; url: string };

export function isExpectedDevelopmentUrl(value: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return false;
  }

  return (
    parsed.origin === DEV_RENDERER_ORIGIN &&
    parsed.pathname === "/" &&
    parsed.search === "" &&
    parsed.hash === "" &&
    parsed.username === "" &&
    parsed.password === ""
  );
}

export function selectRendererLoadTarget(
  options: RendererLoadOptions,
): RendererLoadTarget {
  if (
    !options.isPackaged &&
    options.isDevelopment &&
    options.developmentUrl &&
    isExpectedDevelopmentUrl(options.developmentUrl)
  ) {
    return { type: "development", url: options.developmentUrl };
  }
  return { type: "bundled", path: options.bundledRendererPath };
}

export function isTrustedRendererUrl(
  value: string,
  options: RendererValidationOptions,
): boolean {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return false;
  }

  if (parsed.protocol === "file:") {
    if (parsed.hostname !== "" || parsed.search !== "" || parsed.hash !== "")
      return false;
    try {
      return samePath(fileURLToPath(parsed), options.bundledRendererPath);
    } catch {
      return false;
    }
  }

  return options.allowDevelopmentRenderer && isExpectedDevelopmentUrl(value);
}

export function isTrustedRendererSender(
  senderFrame: RendererFrameReference | null,
  mainFrame: RendererFrameReference,
  options: RendererValidationOptions,
): boolean {
  if (!senderFrame || !sameFrame(senderFrame, mainFrame)) return false;
  return isTrustedRendererUrl(senderFrame.url, options);
}

function sameFrame(
  first: RendererFrameReference,
  second: RendererFrameReference,
): boolean {
  return (
    first === second ||
    (first.processId === second.processId &&
      first.routingId === second.routingId)
  );
}

function samePath(first: string, second: string): boolean {
  const normalizedFirst = path.normalize(path.resolve(first));
  const normalizedSecond = path.normalize(path.resolve(second));
  return process.platform === "win32"
    ? normalizedFirst.toLowerCase() === normalizedSecond.toLowerCase()
    : normalizedFirst === normalizedSecond;
}
