import { describe, expect, it } from "vitest";

import { canSaveMockTextRevision, textEscapesShapeBounds } from "./layout-risk";

const shape = { left: 10, top: 20, right: 110, bottom: 80 };

describe("textEscapesShapeBounds", () => {
  it("accepts text that stays within a text box", () => {
    expect(
      textEscapesShapeBounds(shape, [
        { left: 14, top: 25, right: 98, bottom: 72 },
      ]),
    ).toBe(false);
  });

  it("reports any text fragment that extends beyond the box", () => {
    expect(
      textEscapesShapeBounds(shape, [
        { left: 14, top: 25, right: 98, bottom: 72 },
        { left: 14, top: 73, right: 105, bottom: 91 },
      ]),
    ).toBe(true);
  });

  it("allows subpixel measurement drift at each edge", () => {
    expect(
      textEscapesShapeBounds(shape, [
        { left: 8.5, top: 18.5, right: 111.5, bottom: 81.5 },
      ]),
    ).toBe(false);
  });

  it("returns unknown when geometry or text measurements are unavailable", () => {
    expect(textEscapesShapeBounds(shape, [])).toBeNull();
    expect(
      textEscapesShapeBounds({ ...shape, right: Number.NaN }, [
        { left: 14, top: 25, right: 98, bottom: 72 },
      ]),
    ).toBeNull();
    expect(
      textEscapesShapeBounds(shape, [
        { left: 14, top: 25, right: Number.POSITIVE_INFINITY, bottom: 72 },
      ]),
    ).toBeNull();
  });
});

describe("canSaveMockTextRevision", () => {
  it("requires a preview before saving", () => {
    expect(canSaveMockTextRevision(false, "fits", false)).toBe(false);
  });

  it("requires acknowledgement when the preview detects overflow", () => {
    expect(canSaveMockTextRevision(true, "overflow", false)).toBe(false);
    expect(canSaveMockTextRevision(true, "overflow", true)).toBe(true);
  });

  it("allows a reviewed preview when layout fits or could not be checked", () => {
    expect(canSaveMockTextRevision(true, "fits", false)).toBe(true);
    expect(canSaveMockTextRevision(true, "unknown", false)).toBe(true);
  });
});
