import { describe, expect, it } from "vitest";

import { unwrapInvokeResult } from "../shared/protocol";
import { CoreClientError } from "./core-client";
import { invokeResult } from "./invoke-result";

describe("privileged invoke result envelope", () => {
  it("preserves core error metadata for the renderer abstraction", async () => {
    const transport = await invokeResult(() => {
      throw new CoreClientError({
        code: "SOURCE_DUPLICATE",
        message: "This source is already imported in the project.",
        retryable: false,
        details: {
          duplicate: true,
          existing_document_id: "document-123",
        },
      });
    });

    expect(transport).toEqual({
      ok: false,
      error: {
        code: "SOURCE_DUPLICATE",
        message: "This source is already imported in the project.",
        retryable: false,
        details: {
          duplicate: true,
          existing_document_id: "document-123",
        },
      },
    });

    let rendererError: unknown;
    try {
      unwrapInvokeResult(transport);
    } catch (error) {
      rendererError = error;
    }
    if (transport.ok) throw new Error("Expected an invoke failure.");
    expect(rendererError).toEqual(transport.error);
  });

  it("converts unexpected main-process errors to a safe generic error", async () => {
    const transport = await invokeResult(() => {
      throw new Error("private path and stack must not cross the boundary");
    });

    expect(transport).toEqual({
      ok: false,
      error: {
        code: "IPC_INTERNAL_ERROR",
        message: "The privileged request could not be completed.",
        retryable: false,
        details: {},
      },
    });
  });
});
