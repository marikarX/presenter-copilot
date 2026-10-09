import type { LayoutObject } from "./object-layout";

type Bounds = { left: number; top: number; right: number; bottom: number };
type GapGuide = {
  axis: "x" | "y";
  position: number;
  gap: { start: number; end: number; cross: number };
};
export type SpacingCandidate = {
  delta: number;
  distance: number;
  guidesFor: (otherDelta: number) => GapGuide[] | null;
};

/** Find equal-gap insertion and continuation positions for an atomic selection. */
export function spacingCandidates(
  objects: LayoutObject[],
  ids: string[],
  size: { width: number; height: number },
  selection: Bounds,
  axis: "x" | "y",
  rawDelta: number,
  otherDelta: number,
  tolerance: number,
): SpacingCandidate[] {
  const references = objects
    .filter((o) => {
      const g = o.geometry;
      return (
        !ids.includes(o.object_id) &&
        o.geometry_editable &&
        g &&
        Object.values(g).every(Number.isSafeInteger) &&
        g.x_emu >= 0 &&
        g.y_emu >= 0 &&
        g.width_emu > 0 &&
        g.height_emu > 0 &&
        g.x_emu + g.width_emu <= size.width &&
        g.y_emu + g.height_emu <= size.height
      );
    })
    .map((o) => o.geometry!);
  const begin = axis === "x" ? selection.left : selection.top;
  const end = axis === "x" ? selection.right : selection.bottom;
  const crossBegin = axis === "x" ? selection.top : selection.left;
  const crossEnd = axis === "x" ? selection.bottom : selection.right;
  const limit = axis === "x" ? size.width : size.height;
  const interval = (g: (typeof references)[number]) =>
    axis === "x"
      ? {
          start: g.x_emu,
          end: g.x_emu + g.width_emu,
          lo: g.y_emu,
          hi: g.y_emu + g.height_emu,
        }
      : {
          start: g.y_emu,
          end: g.y_emu + g.height_emu,
          lo: g.x_emu,
          hi: g.x_emu + g.width_emu,
        };
  const lane = references
    .map(interval)
    .filter(
      (g) =>
        Math.min(g.hi, crossEnd + otherDelta) >
        Math.max(g.lo, crossBegin + otherDelta),
    )
    .sort((a, b) => a.start - b.start || a.end - b.end);
  const candidates: SpacingCandidate[] = [];
  for (let i = 1; i < lane.length; i++) {
    const left = lane[i - 1]!,
      right = lane[i]!;
    const gap = right.start - left.end;
    if (gap <= 0 || Math.min(left.hi, right.hi) <= Math.max(left.lo, right.lo))
      continue;
    const width = end - begin;
    for (const target of [
      { start: (left.end + right.start - width) / 2, mode: "between" },
      { start: left.start - gap - width, mode: "before" },
      { start: right.end + gap, mode: "after" },
    ]) {
      const delta = Math.round(target.start - begin);
      const distance = Math.abs(delta - rawDelta);
      const start = begin + delta,
        finish = end + delta;
      if (
        distance > tolerance ||
        start < 0 ||
        finish > limit ||
        (target.mode === "between" && gap < width)
      )
        continue;
      const guidesFor = (crossDelta: number): GapGuide[] | null => {
        const lo = Math.max(left.lo, right.lo, crossBegin + crossDelta);
        const hi = Math.min(left.hi, right.hi, crossEnd + crossDelta);
        if (hi <= lo) return null;
        // Every witness must remain nonoverlapping in the final resolved lane.
        if (
          references
            .map(interval)
            .some(
              (g) =>
                Math.min(finish, g.end) > Math.max(start, g.start) &&
                Math.min(crossEnd + crossDelta, g.hi) >
                  Math.max(crossBegin + crossDelta, g.lo),
            )
        )
          return null;
        const segments =
          target.mode === "between"
            ? [
                [left.end, start],
                [finish, right.start],
              ]
            : target.mode === "before"
              ? [
                  [finish, left.start],
                  [left.end, right.start],
                ]
              : [
                  [left.end, right.start],
                  [right.end, start],
                ];
        if (
          segments.some(([a, b]) => b! <= a!) ||
          Math.abs(
            segments[0]![1]! -
              segments[0]![0]! -
              (segments[1]![1]! - segments[1]![0]!),
          ) > 1
        )
          return null;
        return segments.map(([a, b]) => ({
          axis,
          position: (a! + b!) / 2,
          gap: { start: a!, end: b!, cross: (lo + hi) / 2 },
        }));
      };
      if (guidesFor(otherDelta))
        candidates.push({ delta, distance, guidesFor });
    }
  }
  return candidates;
}
