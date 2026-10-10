export type LayoutGeometry = {
  x_emu: number;
  y_emu: number;
  width_emu: number;
  height_emu: number;
};
export type LayoutObject = {
  object_id: string;
  name: string;
  geometry_editable: boolean;
  geometry: LayoutGeometry | null;
  rotation?: { rotation_degrees: number } | null;
};
export const LAYOUT_ACTIONS = [
  ["left", "Align left"],
  ["center", "Align centers"],
  ["right", "Align right"],
  ["top", "Align top"],
  ["middle", "Align middles"],
  ["bottom", "Align bottom"],
  ["horizontal", "Distribute horizontally"],
  ["vertical", "Distribute vertically"],
] as const;
export type LayoutAction = (typeof LAYOUT_ACTIONS)[number][0];
export type ObjectMoveRequest = {
  resize?: boolean;
  operations: ReturnType<typeof translationOperations>;
};

export function translationOperations(
  objects: LayoutObject[],
  ids: string[],
  slideId: string,
  dx: number,
  dy: number,
  size: { width: number; height: number },
  grid = 0,
) {
  if (
    !ids.length ||
    ids.length > 20 ||
    new Set(ids).size !== ids.length ||
    ![dx, dy, size.width, size.height, grid].every(Number.isFinite) ||
    size.width < 1 ||
    size.height < 1 ||
    grid < 0
  )
    throw new Error("Choose a valid selection and slide size for this move.");
  const selected = ids.map((id) => {
    const object = objects.find((o) => o.object_id === id);
    if (!object?.geometry_editable || !object.geometry)
      throw new Error("A selected object cannot be moved. Refresh the slide.");
    const g = object.geometry;
    // Objects may extend past the slide edge; a move brings them fully back onto it.
    if (
      !Object.values(g).every(Number.isSafeInteger) ||
      g.width_emu < 1 ||
      g.height_emu < 1
    )
      throw new Error("A selected object has an invalid size.");
    return { ...object, geometry: g };
  });
  const left = Math.min(...selected.map((o) => o.geometry.x_emu)),
    top = Math.min(...selected.map((o) => o.geometry.y_emu));
  const right = Math.max(
      ...selected.map((o) => o.geometry.x_emu + o.geometry.width_emu),
    ),
    bottom = Math.max(
      ...selected.map((o) => o.geometry.y_emu + o.geometry.height_emu),
    );
  if (right - left > size.width || bottom - top > size.height)
    throw new Error("The selection is larger than the slide.");
  const x = Math.round(
    Math.max(
      -left,
      Math.min(size.width - right, grid ? Math.round(dx / grid) * grid : dx),
    ),
  );
  const y = Math.round(
    Math.max(
      -top,
      Math.min(size.height - bottom, grid ? Math.round(dy / grid) * grid : dy),
    ),
  );
  if (!x && !y) return [];
  return selected.map((o) => ({
    type: "transform_object",
    params: {
      slide_id: slideId,
      object_id: o.object_id,
      expected_geometry: o.geometry,
      replacement_geometry: {
        ...o.geometry,
        x_emu: o.geometry.x_emu + x,
        y_emu: o.geometry.y_emu + y,
      },
    },
  }));
}

/** Keep sizes and paint order; align within the selection's original bounds. */
export function layoutOperations(
  objects: LayoutObject[],
  selectedIds: string[],
  slideId: string,
  action: LayoutAction,
) {
  if (selectedIds.length < 2 || selectedIds.length > 20)
    throw new Error("Select between 2 and 20 editable objects.");
  if (new Set(selectedIds).size !== selectedIds.length)
    throw new Error("Select each object only once.");
  const selected = selectedIds.map((id) => {
    const object = objects.find((candidate) => candidate.object_id === id);
    if (!object?.geometry_editable || !object.geometry)
      throw new Error("A selected object cannot be moved. Refresh the slide.");
    const geometry = object.geometry;
    if (
      !Object.values(geometry).every(Number.isSafeInteger) ||
      geometry.x_emu < 0 ||
      geometry.y_emu < 0 ||
      geometry.width_emu < 1 ||
      geometry.height_emu < 1
    )
      throw new Error("The selected geometry is invalid.");
    return { ...object, geometry, replacement: { ...geometry } };
  });
  const left = Math.min(...selected.map((o) => o.geometry.x_emu));
  const top = Math.min(...selected.map((o) => o.geometry.y_emu));
  const right = Math.max(
    ...selected.map((o) => o.geometry.x_emu + o.geometry.width_emu),
  );
  const bottom = Math.max(
    ...selected.map((o) => o.geometry.y_emu + o.geometry.height_emu),
  );
  if (action === "horizontal" || action === "vertical") {
    if (selected.length < 3)
      throw new Error("Select at least 3 objects to distribute.");
    const axis = action === "horizontal" ? "x_emu" : "y_emu";
    const size = action === "horizontal" ? "width_emu" : "height_emu";
    const sorted = [...selected].sort(
      (a, b) => a.geometry[axis] - b.geometry[axis],
    );
    const first = sorted[0],
      last = sorted[sorted.length - 1];
    if (!first || !last)
      throw new Error("Select at least 3 objects to distribute.");
    const gap =
      (last.geometry[axis] -
        first.geometry[axis] -
        sorted.slice(0, -1).reduce((sum, o) => sum + o.geometry[size], 0)) /
      (sorted.length - 1);
    if (gap < 0)
      throw new Error(
        "The outer objects need more space for equal gaps. Move them apart first.",
      );
    let position = first.geometry[axis];
    for (const object of sorted) {
      object.replacement[axis] =
        object === last ? last.geometry[axis] : Math.round(position);
      position += object.geometry[size] + gap;
    }
  } else {
    for (const object of selected) {
      const g = object.geometry,
        r = object.replacement;
      switch (action) {
        case "left":
          r.x_emu = left;
          break;
        case "center":
          r.x_emu = Math.round((left + right - g.width_emu) / 2);
          break;
        case "right":
          r.x_emu = right - g.width_emu;
          break;
        case "top":
          r.y_emu = top;
          break;
        case "middle":
          r.y_emu = Math.round((top + bottom - g.height_emu) / 2);
          break;
        case "bottom":
          r.y_emu = bottom - g.height_emu;
          break;
        default:
          throw new Error("Choose a supported layout command.");
      }
    }
  }
  return selected
    .filter(
      (o) =>
        o.geometry.x_emu !== o.replacement.x_emu ||
        o.geometry.y_emu !== o.replacement.y_emu,
    )
    .map((o) => ({
      type: "transform_object",
      params: {
        slide_id: slideId,
        object_id: o.object_id,
        expected_geometry: o.geometry,
        replacement_geometry: o.replacement,
      },
    }));
}

export const RESIZE_HANDLES = [
  ["nw", "top left"],
  ["n", "top"],
  ["ne", "top right"],
  ["e", "right"],
  ["se", "bottom right"],
  ["s", "bottom"],
  ["sw", "bottom left"],
  ["w", "left"],
] as const;
export type ResizeHandle = (typeof RESIZE_HANDLES)[number][0];

/** Scale the selection about the opposite edge, retaining relative placement. */
export function resizeOperations(
  objects: LayoutObject[],
  ids: string[],
  slideId: string,
  handle: ResizeHandle,
  dx: number,
  dy: number,
  size: { width: number; height: number },
  grid = 0,
  proportional = false,
): ReturnType<typeof translationOperations> {
  // Reuse move validation for selection identity, integer geometry and slide bounds.
  translationOperations(objects, ids, slideId, 0, 0, size, grid);
  if (
    !RESIZE_HANDLES.some(([key]) => key === handle) ||
    ![dx, dy].every(Number.isFinite)
  )
    throw new Error("Choose a valid resize handle and distance.");
  const selected = ids.map((id) => objects.find((o) => o.object_id === id)!);
  const geometry = selected.map((o) => o.geometry!);
  const left = Math.min(...geometry.map((g) => g.x_emu));
  const top = Math.min(...geometry.map((g) => g.y_emu));
  const right = Math.max(...geometry.map((g) => g.x_emu + g.width_emu));
  const bottom = Math.max(...geometry.map((g) => g.y_emu + g.height_emu));
  const width = right - left,
    height = bottom - top;
  // Keep every member at least one point, unless it started smaller.
  const minWidth = Math.ceil(
    Math.max(
      ...geometry.map(
        (g) => (width * Math.min(12700, g.width_emu)) / g.width_emu,
      ),
    ),
  );
  const minHeight = Math.ceil(
    Math.max(
      ...geometry.map(
        (g) => (height * Math.min(12700, g.height_emu)) / g.height_emu,
      ),
    ),
  );
  const west = handle.includes("w"),
    east = handle.includes("e");
  const north = handle.includes("n"),
    south = handle.includes("s");
  const snap = (value: number) =>
    Math.round(grid ? Math.round(value / grid) * grid : value);
  const clamp = (value: number, min: number, max: number) =>
    Math.max(min, Math.min(max, value));
  let l = left,
    t = top,
    r = right,
    b = bottom;
  if (west) l = clamp(left + snap(dx), 0, right - minWidth);
  if (east) r = clamp(right + snap(dx), left + minWidth, size.width);
  if (north) t = clamp(top + snap(dy), 0, bottom - minHeight);
  if (south) b = clamp(bottom + snap(dy), top + minHeight, size.height);
  if (proportional && (west || east) && (north || south)) {
    const sx = 1 + (west ? -snap(dx) : snap(dx)) / width;
    const sy = 1 + (north ? -snap(dy) : snap(dy)) / height;
    const scale = Math.abs(sx - 1) >= Math.abs(sy - 1) ? sx : sy;
    const spaceX = west ? right : size.width - left;
    const spaceY = north ? bottom : size.height - top;
    const bounded = clamp(
      scale,
      Math.max(minWidth / width, minHeight / height),
      Math.min(spaceX / width, spaceY / height),
    );
    const w = Math.min(spaceX, Math.max(minWidth, Math.round(width * bounded)));
    const h = Math.min(
      spaceY,
      Math.max(minHeight, Math.round(height * bounded)),
    );
    l = west ? right - w : left;
    r = l + w;
    t = north ? bottom - h : top;
    b = t + h;
  }
  return selected.flatMap((o) => {
    const g = o.geometry!;
    const x = Math.round(l + ((g.x_emu - left) * (r - l)) / width);
    const y = Math.round(t + ((g.y_emu - top) * (b - t)) / height);
    const replacement = {
      x_emu: x,
      y_emu: y,
      width_emu:
        Math.round(l + ((g.x_emu + g.width_emu - left) * (r - l)) / width) - x,
      height_emu:
        Math.round(t + ((g.y_emu + g.height_emu - top) * (b - t)) / height) - y,
    };
    if (
      Object.values(replacement).some((v) => !Number.isSafeInteger(v)) ||
      replacement.width_emu < 1 ||
      replacement.height_emu < 1
    )
      throw new Error("The selection is too small to resize safely.");
    if (
      Object.entries(replacement).every(
        ([key, value]) => value === g[key as keyof LayoutGeometry],
      )
    )
      return [];
    return [
      {
        type: "transform_object",
        params: {
          slide_id: slideId,
          object_id: o.object_id,
          expected_geometry: g,
          replacement_geometry: replacement,
        },
      },
    ];
  });
}
