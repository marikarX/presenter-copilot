import type { ClaimCandidate, ClaimExtractionResult } from "./ClaimDiscovery";
import {
  isNativeClaimSourceKind,
  type NativeClaimSourceKind,
} from "./claim-source";

export type ScanBatch = {
  object_ids: string[];
  spans: { object_id: string; start: number; end: number; sha256: string }[];
  characters: number;
  source_kinds?: Record<string, NativeClaimSourceKind>;
};
export type ScanSlide = {
  slide_id: string;
  slide_number: number;
  title: string;
  batches: ScanBatch[];
  eligible_objects: number;
  excluded_objects: number;
  inventory_truncated: boolean;
};
export type CompletedScanBatch = {
  slide: ScanSlide;
  batch: number;
  result: ClaimExtractionResult;
  verified_revision_id: string;
  carried: boolean;
};
export type ClaimScanCache = Map<string, CompletedScanBatch[]>;
export type NativeScanText = {
  revision_id: string;
  slide_id: string;
  targets: { object_id: string; decision_text: string | null }[];
  semantic_targets?: {
    object_id: string;
    decision_text: string | null;
    source_kind: NativeClaimSourceKind;
  }[];
};
export function scanCacheKey(project: string, document: string) {
  return JSON.stringify([project, document]);
}
export function scanBatchKey(slide: string, batch: ScanBatch) {
  return JSON.stringify([
    slide,
    batch.object_ids,
    batch.spans,
    batch.object_ids.map((id) => batch.source_kinds?.[id] ?? "native_text"),
  ]);
}
export function retainScanCache(
  cache: ClaimScanCache,
  key: string,
  completed: CompletedScanBatch[],
) {
  const kept: CompletedScanBatch[] = [];
  let characters = 0;
  for (
    let index = completed.length - 1;
    index >= 0 && kept.length < 1000;
    index--
  ) {
    const item = completed[index];
    if (!item) continue;
    const size = item.result.candidates.reduce(
      (total, candidate) => total + candidate.quote.length,
      0,
    );
    if (characters + size > 1_000_000) continue;
    characters += size;
    kept.push(item);
  }
  cache.delete(key);
  cache.set(key, kept.reverse());
  while (cache.size > 3) {
    const first = cache.keys().next().value;
    if (first === undefined) break;
    cache.delete(first);
  }
}
export function reusableScanBatches(
  slides: ScanSlide[],
  cached: CompletedScanBatch[],
  document: string,
): CompletedScanBatch[] {
  const byInput = new Map<string, CompletedScanBatch>();
  for (const entry of cached) {
    const batch = entry.slide.batches[entry.batch];
    if (
      batch &&
      entry.result.document_id === document &&
      entry.result.slide_id === entry.slide.slide_id
    )
      byInput.set(scanBatchKey(entry.slide.slide_id, batch), entry);
  }
  return slides.flatMap((slide) =>
    slide.batches.flatMap((batch, index) => {
      const previous = byInput.get(scanBatchKey(slide.slide_id, batch));
      return previous
        ? [{ ...previous, slide, batch: index, carried: true }]
        : [];
    }),
  );
}
export function validScanResult(
  batch: ScanBatch,
  slide: string,
  document: string,
  result: ClaimExtractionResult,
  originalRevision: string,
  native: NativeScanText,
  currentRevision: string,
): boolean {
  if (
    result.document_id !== document ||
    result.revision_id !== originalRevision ||
    result.slide_id !== slide ||
    result.requires_user_review !== true ||
    !Array.isArray(result.object_ids) ||
    result.object_ids.length !== batch.object_ids.length ||
    new Set(result.object_ids).size !== batch.object_ids.length ||
    result.object_ids.some((id) => !batch.object_ids.includes(id)) ||
    !Array.isArray(result.candidates) ||
    result.candidates.length > 12 ||
    native.revision_id !== currentRevision ||
    native.slide_id !== slide ||
    !Array.isArray(native.semantic_targets ?? native.targets)
  )
    return false;
  const targets =
    native.semantic_targets ??
    native.targets.map((target) => ({
      ...target,
      source_kind: "native_text" as const,
    }));
  if (
    !batch.object_ids.every((id) => {
      const kind = batch.source_kinds?.[id] ?? "native_text";
      const target = targets.find((item) => item.object_id === id);
      return isNativeClaimSourceKind(kind) && target?.source_kind === kind;
    })
  )
    return false;
  return result.candidates.every((candidate) => {
    const target = targets.find(
      (target) => target.object_id === candidate.object_id,
    );
    const text = target?.decision_text;
    const span = batch.spans.find(
      (window) => window.object_id === candidate.object_id,
    );
    const window =
      text && span ? [...text].slice(span.start, span.end).join("") : "";
    return (
      isNativeClaimSourceKind(candidate.source_kind ?? "native_text") &&
      (candidate.source_kind ?? "native_text") === target?.source_kind &&
      batch.object_ids.includes(candidate.object_id) &&
      typeof candidate.quote === "string" &&
      Boolean(candidate.quote.trim()) &&
      [...candidate.quote].length <= 2000 &&
      typeof candidate.reason === "string" &&
      candidate.reason.length <= 300 &&
      ["factual", "forecast", "interpretation", "recommendation"].includes(
        candidate.kind,
      ) &&
      (candidate.confidence === null ||
        (typeof candidate.confidence === "number" &&
          Number.isFinite(candidate.confidence) &&
          candidate.confidence >= 0 &&
          candidate.confidence <= 1)) &&
      candidate.object_sha256 === span?.sha256 &&
      /^[0-9a-f]{64}$/.test(candidate.object_sha256) &&
      Boolean(
        text &&
        window.includes(candidate.quote) &&
        text.indexOf(candidate.quote, text.indexOf(candidate.quote) + 1) < 0,
      )
    );
  });
}
export function uniqueScanCandidates(completed: CompletedScanBatch[]) {
  const ordered = [...completed].sort(
    (a, b) => a.slide.slide_number - b.slide.slide_number || a.batch - b.batch,
  );
  const seen = new Set<string>();
  const items: {
    slide: ScanSlide;
    candidate: ClaimCandidate;
    carried: boolean;
    original_revision_id: string;
  }[] = [];
  for (const entry of ordered)
    for (const candidate of entry.result.candidates) {
      const key = JSON.stringify([
        entry.slide.slide_id,
        candidate.object_id,
        candidate.quote,
      ]);
      if (seen.has(key)) continue;
      seen.add(key);
      items.push({
        slide: entry.slide,
        candidate,
        carried: entry.carried,
        original_revision_id: entry.result.revision_id,
      });
    }
  return items;
}
