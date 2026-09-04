import {
  isCoreError,
  type CoreError,
  type InvokeResult,
} from "../shared/protocol";
import { CoreClientError, toCoreError } from "./core-client";

const GENERIC_INVOKE_ERROR: CoreError = {
  code: "IPC_INTERNAL_ERROR",
  message: "The privileged request could not be completed.",
  retryable: false,
  details: {},
};

/**
 * Convert an Electron-main operation into data that survives invoke IPC.
 * Sender validation intentionally happens before callers enter this helper.
 */
export async function invokeResult<T>(
  operation: () => T | Promise<T>,
): Promise<InvokeResult<T>> {
  try {
    return { ok: true, result: await operation() };
  } catch (error) {
    return { ok: false, error: toInvokeError(error) };
  }
}

export function toInvokeError(error: unknown): CoreError {
  if (error instanceof CoreClientError) {
    return toCoreError(error);
  }
  if (isCoreError(error)) {
    // A structured-looking object can still originate from an untrusted
    // Electron boundary. Re-enter the same sanitizer used for core-client
    // errors instead of copying arbitrary message/details values through IPC.
    return toCoreError(error);
  }
  return { ...GENERIC_INVOKE_ERROR, details: {} };
}
