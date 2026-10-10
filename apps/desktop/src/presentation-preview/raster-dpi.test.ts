import { describe, expect, it } from "vitest";
import { joinBrowserOnlyBreaks, rasterDpi } from "./renderer-compatibility";

function jfif(unit: number, x: number, y: number): Uint8Array {
  return new Uint8Array([
    0xff,
    0xd8,
    0xff,
    0xe0,
    0x00,
    0x10,
    0x4a,
    0x46,
    0x49,
    0x46,
    0x00,
    0x01,
    0x01,
    unit,
    x >> 8,
    x & 0xff,
    y >> 8,
    y & 0xff,
    0x00,
    0x00,
  ]);
}

function pngWithPhys(pixelsPerMetre: number): Uint8Array {
  const bytes = new Uint8Array(8 + 25 + 21);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const view = new DataView(bytes.buffer);
  view.setUint32(8, 13);
  bytes.set([0x49, 0x48, 0x44, 0x52], 12);
  view.setUint32(33, 9);
  bytes.set([0x70, 0x48, 0x59, 0x73], 37);
  view.setUint32(41, pixelsPerMetre);
  view.setUint32(45, pixelsPerMetre);
  bytes[49] = 1;
  return bytes;
}

describe("rasterDpi", () => {
  it("reads JFIF density in dots per inch and per centimetre", () => {
    expect(rasterDpi(jfif(1, 75, 75), "ppt/media/a.jpeg")).toEqual({
      x: 75,
      y: 75,
    });
    const metric = rasterDpi(jfif(2, 118, 118), "ppt/media/a.jpg");
    expect(metric.x).toBeCloseTo(299.72);
  });

  it("reads PNG pHYs pixels per metre", () => {
    expect(rasterDpi(pngWithPhys(3780), "ppt/media/a.png").x).toBeCloseTo(
      96.01,
      1,
    );
  });

  it("defaults to 96 DPI without density metadata", () => {
    expect(rasterDpi(jfif(0, 1, 1), "ppt/media/a.jpeg")).toEqual({
      x: 96,
      y: 96,
    });
    expect(rasterDpi(new Uint8Array([1, 2, 3]), "ppt/media/a.gif")).toEqual({
      x: 96,
      y: 96,
    });
  });
});

describe("joinBrowserOnlyBreaks", () => {
  it("keeps ? and ! inside words but leaves sentence ends alone", () => {
    expect(joinBrowserOnlyBreaks("images?q=tbn")).toBe("images?⁠q=tbn");
    expect(joinBrowserOnlyBreaks("Really? Yes! Done.")).toBe(
      "Really? Yes! Done.",
    );
    expect(joinBrowserOnlyBreaks("why?!")).toBe("why?!");
  });
});
