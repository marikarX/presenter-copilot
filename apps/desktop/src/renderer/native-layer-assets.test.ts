import { describe, expect, it } from "vitest";
import {
  createNativeLayerUrls,
  isCurrentNativeLayers,
} from "./native-layer-assets";
import type { NativeLayersResult } from "../shared/protocol";
import type { NativeAppearanceTarget } from "./NativeAppearance";
const id = "00000000-0000-4000-8000-000000000001";
const target: NativeAppearanceTarget = {
  projectId: id,
  documentId: id,
  revisionId: id,
  sourceSha256: "a".repeat(64),
};
const asset = () => ({ sha256: "b".repeat(64), image: new Uint8Array(40) });
const frame = (): NativeLayersResult => ({
  revision_id: id,
  document_id: id,
  source_sha256: target.sourceSha256,
  slide_number: 1,
  width: 960,
  height: 540,
  renderer: "microsoft_powerpoint",
  baseline_max_channel_error: 2,
  background: asset(),
  layers: [{ object_id: id, ooxml_shape_id: "2", visible: true, ...asset() }],
});
describe("native layer image ownership", () => {
  it("accepts only the full saved identity and known object catalog", () => {
    const value = frame();
    expect(
      isCurrentNativeLayers(value, target, 1, [
        { object_id: id, name: "A", geometry: null, geometry_editable: false },
      ]),
    ).toBe(true);
    expect(isCurrentNativeLayers(value, { ...target, planId: id }, 1, [])).toBe(
      false,
    );
    expect(isCurrentNativeLayers(value, target, 2, [])).toBe(false);
    expect(
      isCurrentNativeLayers(value, target, 1, [
        {
          object_id: "other",
          name: "A",
          geometry: null,
          geometry_editable: false,
        },
      ]),
    ).toBe(false);
  });
  it.each([
    "revision",
    "source",
    "document",
    "dimensions",
    "baseline",
    "duplicates",
    "bytes",
  ])("rejects invalid %s assets before URL ownership", (issue) => {
    const value = frame();
    if (issue === "revision") value.revision_id = "other";
    if (issue === "source") value.source_sha256 = "c".repeat(64);
    if (issue === "document") value.document_id = "other";
    if (issue === "dimensions") value.width = 5000;
    if (issue === "baseline") value.baseline_max_channel_error = 5;
    if (issue === "duplicates") value.layers.push(value.layers[0]!);
    if (issue === "bytes") value.background.image = new Uint8Array(20);
    expect(isCurrentNativeLayers(value, target, 1, [])).toBe(false);
  });
  it("owns all URLs in source paint order and revokes them exactly once", () => {
    const created: string[] = [],
      revoked: string[] = [];
    const urls = createNativeLayerUrls(frame(), {
      createObjectURL: () => {
        const value = `blob:${created.length}`;
        created.push(value);
        return value;
      },
      revokeObjectURL: (value) => {
        revoked.push(value);
      },
    });
    expect(urls.background).toBe("blob:0");
    expect(urls.layers).toEqual([{ objectId: id, value: "blob:1" }]);
    urls.dispose();
    urls.dispose();
    expect(revoked).toEqual(created);
  });
  it("revokes earlier URLs if allocating a later image fails", () => {
    const revoked: string[] = [];
    let count = 0;
    expect(() =>
      createNativeLayerUrls(frame(), {
        createObjectURL: () => {
          if (count++) throw new Error("allocation failed");
          return "blob:owned";
        },
        revokeObjectURL: (value) => {
          revoked.push(value);
        },
      }),
    ).toThrow(/allocation/);
    expect(revoked).toEqual(["blob:owned"]);
  });
});
