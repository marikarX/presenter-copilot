import { describe, expect, it } from "vitest";
import {
  retainScanCache,
  reusableScanBatches,
  scanBatchKey,
  scanCacheKey,
  uniqueScanCandidates,
  validScanResult,
  type CompletedScanBatch,
  type ClaimScanCache,
  type NativeScanText,
} from "./claim-scan-state";

const quote = "Revenue increased by 20%.";
const sha = "a".repeat(64);
function entry(id = "slide", ordinal = 1): CompletedScanBatch {
  return {
    slide: {
      slide_id: id,
      slide_number: ordinal,
      title: "Metric",
      eligible_objects: 1,
      excluded_objects: 0,
      inventory_truncated: false,
      batches: [
        {
          object_ids: ["object"],
          spans: [
            { object_id: "object", start: 0, end: quote.length, sha256: sha },
          ],
          characters: quote.length,
        },
      ],
    },
    batch: 0,
    verified_revision_id: "old",
    carried: false,
    result: {
      document_id: "document",
      revision_id: "old",
      slide_id: id,
      object_ids: ["object"],
      candidates: [
        {
          object_id: "object",
          quote,
          kind: "factual",
          reason: "Review the metric.",
          confidence: 0.5,
          object_sha256: sha,
        },
      ],
      summary: "Review the assertion.",
      provider_id: "provider",
      model_id: "model",
      inventory_truncated: false,
      requires_user_review: true,
    },
  };
}
const native = (text = quote): NativeScanText => ({
  revision_id: "new",
  slide_id: "slide",
  targets: [{ object_id: "object", decision_text: text }],
});
function valid(row: CompletedScanBatch, text = native()) {
  const batch = row.slide.batches[0];
  if (!batch) throw new Error("Missing fixture batch");
  return validScanResult(
    batch,
    "slide",
    "document",
    row.result,
    "old",
    text,
    "new",
  );
}

describe("incremental native text claim scan", () => {
  it("does not reuse identical text from a different native representation", () => {
    const row = entry();
    const batch = row.slide.batches[0]!;
    const graphic = {
      ...row.slide,
      batches: [
        { ...batch, source_kinds: { object: "native_chart_cache" as const } },
      ],
    };
    expect(scanBatchKey("slide", batch)).not.toBe(
      scanBatchKey("slide", graphic.batches[0]!),
    );
    expect(reusableScanBatches([graphic], [row], "document")).toHaveLength(0);
  });

  it("requires trusted graphic source kinds for candidates and empty results", () => {
    const row = entry();
    row.slide.batches[0]!.source_kinds = { object: "native_chart_cache" };
    const graphic: NativeScanText = {
      ...native(),
      semantic_targets: [
        {
          object_id: "object",
          decision_text: quote,
          source_kind: "native_chart_cache",
        },
      ],
    };
    expect(valid(row, graphic)).toBe(false);
    row.result.candidates[0]!.source_kind = "native_chart_cache";
    expect(valid(row, graphic)).toBe(true);
    row.result.candidates = [];
    expect(valid(row, graphic)).toBe(true);
    graphic.semantic_targets![0]!.source_kind = "native_table_cells";
    expect(valid(row, graphic)).toBe(false);
  });
  it("reuses exact input on reorder while preserving original provider revision and current ordinal", () => {
    const row = entry();
    const reordered = {
      ...row.slide,
      slide_number: 7,
      title: "Retitled display",
    };
    const reused = reusableScanBatches([reordered], [row], "document");
    expect(reused).toHaveLength(1);
    expect(reused[0]?.slide.slide_number).toBe(7);
    expect(reused[0]?.result).toBe(row.result);
    expect(reused[0]?.result.revision_id).toBe("old");
    expect(reused[0]?.carried).toBe(true);
    expect(valid(row)).toBe(true);
  });
  it.each(["hash", "span", "object", "slide", "document"])(
    "requires new analysis when %s identity changes",
    (kind) => {
      const row = entry();
      const slide = structuredClone(row.slide);
      const batch = slide.batches[0];
      if (!batch?.spans[0]) throw new Error("Missing fixture span");
      if (kind === "hash") batch.spans[0].sha256 = "b".repeat(64);
      if (kind === "span") batch.spans[0].end--;
      if (kind === "object") batch.object_ids = ["other"];
      if (kind === "slide") slide.slide_id = "other";
      expect(
        reusableScanBatches(
          [slide],
          [row],
          kind === "document" ? "other" : "document",
        ),
      ).toEqual([]);
    },
  );
  it("drops removed slides and never matches by ordinal/title alone", () => {
    const row = entry();
    expect(reusableScanBatches([], [row], "document")).toEqual([]);
    expect(
      reusableScanBatches(
        [{ ...row.slide, slide_id: "new-native-id" }],
        [row],
        "document",
      ),
    ).toEqual([]);
  });
  it("isolates projects even when document identity is the same", () => {
    const cache: ClaimScanCache = new Map();
    retainScanCache(cache, scanCacheKey("project-a", "document"), [entry()]);
    expect(cache.get(scanCacheKey("project-b", "document"))).toBeUndefined();
    expect(scanCacheKey("a,b", "c")).not.toBe(scanCacheKey("a", "b,c"));
  });
  it("requires fresh native revision and quote binding even for unchanged prepared hashes", () => {
    const row = entry();
    expect(valid(row, { ...native(), revision_id: "old" })).toBe(false);
    expect(valid(row, native("The assertion was removed."))).toBe(false);
    expect(valid(row, native(`${quote} ${quote}`))).toBe(false);
    expect(
      valid({ ...row, result: { ...row.result, requires_user_review: false } }),
    ).toBe(false);
  });
  it("rejects invalid cached confidence and quote metadata", () => {
    const row = entry();
    const candidate = row.result.candidates[0];
    if (!candidate) throw new Error("Missing fixture candidate");
    for (const confidence of [NaN, Infinity, -0.1, 1.1])
      expect(
        valid({
          ...row,
          result: { ...row.result, candidates: [{ ...candidate, confidence }] },
        }),
      ).toBe(false);
    expect(
      valid({
        ...row,
        result: {
          ...row.result,
          candidates: [{ ...candidate, object_sha256: "b".repeat(64) }],
        },
      }),
    ).toBe(false);
  });
  it("uses Core code-point window offsets with non-BMP native text", () => {
    const row = entry();
    const batch = row.slide.batches[0];
    if (!batch?.spans[0]) throw new Error("Missing fixture span");
    batch.spans[0].start = 2;
    batch.spans[0].end = 2 + quote.length;
    expect(valid(row, native(`🧠 ${quote}`))).toBe(true);
  });
  it("preserves order-sensitive input identity rather than silently reordering model inputs", () => {
    const batch = entry().slide.batches[0];
    if (!batch) throw new Error("Missing fixture batch");
    expect(
      scanBatchKey("slide", { ...batch, object_ids: ["a", "b"] }),
    ).not.toBe(scanBatchKey("slide", { ...batch, object_ids: ["b", "a"] }));
  });
  it("deduplicates overlapping quotes across 5000 slides without merging different slides", () => {
    const rows = Array.from({ length: 5000 }, (_, index) =>
      entry(`slide-${index}`, index + 1),
    );
    const output = uniqueScanCandidates([...rows, ...rows]);
    expect(output).toHaveLength(5000);
    expect(output[0]?.slide.slide_number).toBe(1);
    expect(output[4999]?.slide.slide_number).toBe(5000);
  });
  it("shows fresh and reused batches in current slide order without mutating completion order", () => {
    const fresh = entry("first", 1);
    const reused = entry("second", 2);
    reused.carried = true;
    const completionOrder = [reused, fresh];
    expect(
      uniqueScanCandidates(completionOrder).map(
        (item) => item.slide.slide_number,
      ),
    ).toEqual([1, 2]);
    expect(completionOrder).toEqual([reused, fresh]);
  });
  it("bounds retained projects, batches and quote content while keeping newest entries", () => {
    const cache: ClaimScanCache = new Map();
    for (let index = 0; index < 5; index++)
      retainScanCache(cache, `document-${index}`, [entry()]);
    expect([...cache.keys()]).toEqual([
      "document-2",
      "document-3",
      "document-4",
    ]);
    const empty = Array.from({ length: 1200 }, (_, index) => {
      const row = entry(`slide-${index}`, index + 1);
      row.result.candidates = [];
      return row;
    });
    retainScanCache(cache, "empty", empty);
    expect(cache.get("empty")).toHaveLength(1000);
    expect(cache.get("empty")?.[0]?.slide.slide_number).toBe(201);
    const large = Array.from({ length: 100 }, () => {
      const row = entry();
      const candidate = row.result.candidates[0];
      if (!candidate) throw new Error("Missing fixture candidate");
      row.result.candidates = Array.from({ length: 12 }, () => ({
        ...candidate,
        quote: "x".repeat(2000),
      }));
      return row;
    });
    retainScanCache(cache, "large", large);
    expect(
      cache
        .get("large")
        ?.reduce(
          (sum, row) =>
            sum + row.result.candidates.reduce((n, c) => n + c.quote.length, 0),
          0,
        ),
    ).toBeLessThanOrEqual(1_000_000);
  });
});
