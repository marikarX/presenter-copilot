import { describe, expect, it } from "vitest";
import {
  isCurrentNativeAppearance,
  nativeAppearanceKey,
} from "./NativeAppearance";
import type { NativeAppearanceResult } from "../shared/protocol";
const target = {
  projectId: "project",
  documentId: "document",
  revisionId: "revision",
  sourceSha256: "a".repeat(64),
};
const frame: NativeAppearanceResult = {
  revision_id: "revision",
  source_sha256: "a".repeat(64),
  slide_number: 2,
  width: 960,
  height: 540,
  sha256: "b".repeat(64),
  renderer: "microsoft_powerpoint",
  image: new Uint8Array(40),
};
describe("native frame ownership", () => {
  it("distinguishes saved frames and each proposed plan even for identical package hashes", () => {
    const proposed = { ...target, planId: "plan-one" };
    const proposedFrame = { ...frame, plan_id: "plan-one" };
    expect(isCurrentNativeAppearance(proposedFrame, proposed, 2)).toBe(true);
    expect(isCurrentNativeAppearance(frame, proposed, 2)).toBe(false);
    expect(isCurrentNativeAppearance(proposedFrame, target, 2)).toBe(false);
    expect(
      isCurrentNativeAppearance(
        proposedFrame,
        { ...proposed, planId: "plan-two" },
        2,
      ),
    ).toBe(false);
    expect(nativeAppearanceKey(proposed, 2)).not.toBe(
      nativeAppearanceKey(target, 2),
    );
    expect(nativeAppearanceKey(proposed, 2)).not.toBe(
      nativeAppearanceKey({ ...proposed, planId: "plan-two" }, 2),
    );
  });
  it("binds frame and URL identity to all source coordinates", () => {
    expect(isCurrentNativeAppearance(frame, target, 2)).toBe(true);
    expect(nativeAppearanceKey(target, 2)).not.toBe(
      nativeAppearanceKey({ ...target, projectId: "other" }, 2),
    );
    expect(nativeAppearanceKey(target, 2)).not.toBe(
      nativeAppearanceKey({ ...target, documentId: "other" }, 2),
    );
    expect(nativeAppearanceKey(target, 2)).not.toBe(
      nativeAppearanceKey({ ...target, revisionId: "other" }, 2),
    );
    expect(nativeAppearanceKey(target, 2)).not.toBe(
      nativeAppearanceKey(target, 3),
    );
  });
  it("rejects stale revision/hash/slide and malformed images", () => {
    for (const update of [
      { revision_id: "old" },
      { source_sha256: "c".repeat(64) },
      { slide_number: 1 },
      { width: 4097 },
      { height: 0 },
      { image: new Uint8Array(0) },
      { sha256: "invalid" },
    ])
      expect(
        isCurrentNativeAppearance({ ...frame, ...update }, target, 2),
      ).toBe(false);
  });
});
