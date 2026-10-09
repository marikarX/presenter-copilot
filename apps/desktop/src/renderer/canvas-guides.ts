import { spacingCandidates, type SpacingCandidate } from "./spacing-guides";
import {
  translationOperations,
  resizeOperations,
  type ResizeHandle,
  type LayoutObject,
} from "./object-layout";

export type GuideTolerance = { x: number; y: number };
export type AlignmentGuide = {
  axis: "x" | "y";
  position: number;
  gap?: { start: number; end: number; cross: number };
};

function guideTargets(
  objects: LayoutObject[],
  ids: string[],
  size: { width: number; height: number },
) {
  const targets = {
    x: [0, size.width / 2, size.width],
    y: [0, size.height / 2, size.height],
  };
  for (const object of objects) {
    const g = object.geometry;
    if (
      ids.includes(object.object_id) ||
      !object.geometry_editable ||
      !g ||
      !Object.values(g).every(Number.isSafeInteger) ||
      g.x_emu < 0 ||
      g.y_emu < 0 ||
      g.width_emu < 1 ||
      g.height_emu < 1 ||
      g.x_emu + g.width_emu > size.width ||
      g.y_emu + g.height_emu > size.height
    )
      continue;
    targets.x.push(g.x_emu, g.x_emu + g.width_emu / 2, g.x_emu + g.width_emu);
    targets.y.push(g.y_emu, g.y_emu + g.height_emu / 2, g.y_emu + g.height_emu);
  }
  return targets;
}

/** Resolve guide snapping once, preserving atomic selection movement and slide bounds. */
export function guidedTranslation(
  objects: LayoutObject[],
  ids: string[],
  slideId: string,
  dx: number,
  dy: number,
  size: { width: number; height: number },
  grid = 0,
  tolerance?: GuideTolerance,
) {
  const fallback = translationOperations(
    objects,
    ids,
    slideId,
    dx,
    dy,
    size,
    grid,
  );
  const guides: AlignmentGuide[] = [];
  if (!tolerance) return { operations: fallback, guides };
  if (![tolerance.x, tolerance.y].every((v) => Number.isFinite(v) && v >= 0))
    throw new Error("Use a finite alignment guide distance.");
  const selection = ids.map(
    (id) => objects.find((o) => o.object_id === id)!.geometry!,
  );
  const left = Math.min(...selection.map((g) => g.x_emu));
  const top = Math.min(...selection.map((g) => g.y_emu));
  const right = Math.max(...selection.map((g) => g.x_emu + g.width_emu));
  const bottom = Math.max(...selection.map((g) => g.y_emu + g.height_emu));
  const targets = guideTargets(objects, ids, size);
  // Find guides near the pointer's ungridded position: grid rounding must not hide a nearby edge.
  const raw = translationOperations(objects, ids, slideId, dx, dy, size);
  const offset = (operations: typeof fallback, axis: "x" | "y") => {
    const p = operations[0]?.params;
    const field = axis === "x" ? "x_emu" : "y_emu";
    return p ? p.replacement_geometry[field] - p.expected_geometry[field] : 0;
  };
  type Resolved = {
    distance: number;
    delta: number;
    guides: AlignmentGuide[];
    spacing?: SpacingCandidate;
  };
  function aligned(
    axis: "x" | "y",
    anchors: number[],
    min: number,
    max: number,
  ): Resolved {
    const rawOffset = offset(raw, axis);
    let best: Resolved | null = null;
    for (const position of targets[axis])
      for (const anchor of anchors) {
        const delta = Math.round(position - anchor);
        const distance = Math.abs(delta - rawOffset);
        if (delta < min || delta > max || distance > tolerance![axis]) continue;
        if (!best || distance < best.distance)
          best = { distance, delta, guides: [{ axis, position }] };
      }
    return (
      best ?? { distance: Infinity, delta: offset(fallback, axis), guides: [] }
    );
  }
  const alignmentX = aligned(
    "x",
    [left, (left + right) / 2, right],
    -left,
    size.width - right,
  );
  const alignmentY = aligned(
    "y",
    [top, (top + bottom) / 2, bottom],
    -top,
    size.height - bottom,
  );
  function spaced(axis: "x" | "y", baseline: Resolved, otherDelta: number) {
    let best = baseline;
    for (const candidate of spacingCandidates(
      objects,
      ids,
      size,
      { left, top, right, bottom },
      axis,
      offset(raw, axis),
      otherDelta,
      tolerance![axis],
    )) {
      if (
        candidate.distance < best.distance ||
        (candidate.distance === best.distance &&
          candidate.delta === best.delta &&
          !best.spacing)
      ) {
        const gaps = candidate.guidesFor(otherDelta);
        if (gaps)
          best = {
            distance: candidate.distance,
            delta: candidate.delta,
            guides: gaps,
            spacing: candidate,
          };
      }
    }
    return best;
  }
  let x = spaced("x", alignmentX, alignmentY.delta);
  let y = spaced("y", alignmentY, x.delta);
  // An orthogonal snap can change the lane. Revalidate both gap witnesses against
  // the final pair of offsets and fall back to alignment if a witness no longer holds.
  if (x.spacing && !x.spacing.guidesFor(y.delta)) x = alignmentX;
  if (y.spacing && !y.spacing.guidesFor(x.delta)) y = alignmentY;
  if (x.spacing) x.guides = x.spacing.guidesFor(y.delta)!;
  if (y.spacing) y.guides = y.spacing.guidesFor(x.delta)!;
  return {
    operations: translationOperations(
      objects,
      ids,
      slideId,
      x.delta,
      y.delta,
      size,
    ),
    guides: [...x.guides, ...y.guides],
  };
}

/** Guide a moving resize edge through the same constrained resize transaction used for review. */
export function guidedResize(
  objects: LayoutObject[],
  ids: string[],
  slideId: string,
  handle: ResizeHandle,
  dx: number,
  dy: number,
  size: { width: number; height: number },
  grid = 0,
  proportional = false,
  tolerance?: GuideTolerance,
) {
  const fallback = resizeOperations(
    objects,
    ids,
    slideId,
    handle,
    dx,
    dy,
    size,
    grid,
    proportional,
  );
  const guides: AlignmentGuide[] = [];
  if (!tolerance) return { operations: fallback, guides };
  if (![tolerance.x, tolerance.y].every((v) => Number.isFinite(v) && v >= 0))
    throw new Error("Use a finite alignment guide distance.");
  const selected = ids.map((id) => objects.find((o) => o.object_id === id)!);
  function bounds(operations: typeof fallback) {
    const geometry = selected.map(
      (o) =>
        operations.find((op) => op.params.object_id === o.object_id)?.params
          .replacement_geometry ?? o.geometry!,
    );
    return {
      left: Math.min(...geometry.map((g) => g.x_emu)),
      top: Math.min(...geometry.map((g) => g.y_emu)),
      right: Math.max(...geometry.map((g) => g.x_emu + g.width_emu)),
      bottom: Math.max(...geometry.map((g) => g.y_emu + g.height_emu)),
    };
  }
  const origin = bounds([]),
    base = bounds(fallback);
  const raw = bounds(
    resizeOperations(
      objects,
      ids,
      slideId,
      handle,
      dx,
      dy,
      size,
      0,
      proportional,
    ),
  );
  const west = handle.includes("w"),
    east = handle.includes("e"),
    north = handle.includes("n"),
    south = handle.includes("s");
  const edge = {
    x: west ? "left" : "right",
    y: north ? "top" : "bottom",
  } as const;
  const active = { x: west || east, y: north || south };
  const targets = guideTargets(objects, ids, size);
  const axes = ["x", "y"] as const;
  const baseDX = active.x ? base[edge.x] - origin[edge.x] : 0;
  const baseDY = active.y ? base[edge.y] - origin[edge.y] : 0;
  function build(x: number, y: number) {
    return resizeOperations(
      objects,
      ids,
      slideId,
      handle,
      x,
      y,
      size,
      0,
      proportional,
    );
  }
  if (proportional && active.x && active.y) {
    let best: { score: number; operations: typeof fallback } | null = null;
    for (const axis of axes)
      for (const target of targets[axis]) {
        const distance = Math.abs(target - raw[edge[axis]]);
        if (distance > tolerance[axis]) continue;
        const width = origin.right - origin.left,
          height = origin.bottom - origin.top;
        const scale =
          axis === "x"
            ? (west ? origin.right - target : target - origin.left) / width
            : (north ? origin.bottom - target : target - origin.top) / height;
        if (scale <= 0) continue;
        const operations = build(
          (scale - 1) * width * (west ? -1 : 1),
          (scale - 1) * height * (north ? -1 : 1),
        );
        const resolved = bounds(operations);
        // Clamp/rounding must reach the target before we draw a guide. Never force an independent axis and distort Shift proportions.
        if (Math.abs(resolved[edge[axis]] - target) > 1) continue;
        const score = tolerance[axis] === 0 ? 0 : distance / tolerance[axis];
        if (!best || score < best.score) best = { score, operations };
      }
    if (!best) return { operations: fallback, guides };
    const resolved = bounds(best.operations);
    for (const axis of axes)
      if (
        targets[axis].some(
          (target) => Math.abs(target - resolved[edge[axis]]) <= 1,
        )
      )
        guides.push({ axis, position: resolved[edge[axis]] });
    return { operations: best.operations, guides };
  }
  let x = baseDX,
    y = baseDY;
  for (const axis of axes) {
    if (!active[axis]) continue;
    let best: { distance: number; delta: number; position: number } | null =
      null;
    for (const target of targets[axis]) {
      const distance = Math.abs(target - raw[edge[axis]]);
      if (distance > tolerance[axis]) continue;
      const delta = target - origin[edge[axis]];
      const operations = build(
        axis === "x" ? delta : x,
        axis === "y" ? delta : y,
      );
      const position = bounds(operations)[edge[axis]];
      if (Math.abs(position - target) > 1) continue;
      if (!best || distance < best.distance)
        best = { distance, delta, position };
    }
    if (best) {
      if (axis === "x") x = best.delta;
      else y = best.delta;
      guides.push({ axis, position: best.position });
    }
  }
  return { operations: build(x, y), guides };
}
