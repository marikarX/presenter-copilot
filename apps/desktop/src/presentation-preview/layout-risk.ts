export interface PreviewRect {
  readonly left: number;
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
}

export type MockTextLayoutStatus = "fits" | "overflow" | "unknown" | null;

export function canSaveMockTextRevision(
  hasPreview: boolean,
  layoutStatus: MockTextLayoutStatus,
  riskAcknowledged: boolean,
): boolean {
  return hasPreview && (layoutStatus !== "overflow" || riskAcknowledged);
}

/** Return whether rendered text fragments extend beyond their source text box. */
export function textEscapesShapeBounds(
  shape: PreviewRect,
  textFragments: readonly PreviewRect[],
  tolerance = 1.5,
): boolean | null {
  const values = [shape.left, shape.top, shape.right, shape.bottom, tolerance];
  if (
    values.some((value) => !Number.isFinite(value)) ||
    shape.right <= shape.left ||
    shape.bottom <= shape.top ||
    tolerance < 0 ||
    textFragments.length === 0
  ) {
    return null;
  }

  if (
    textFragments.some(
      (fragment) =>
        ![fragment.left, fragment.top, fragment.right, fragment.bottom].every(
          Number.isFinite,
        ) ||
        fragment.right < fragment.left ||
        fragment.bottom < fragment.top,
    )
  ) {
    return null;
  }

  return textFragments.some(
    (fragment) =>
      fragment.left < shape.left - tolerance ||
      fragment.top < shape.top - tolerance ||
      fragment.right > shape.right + tolerance ||
      fragment.bottom > shape.bottom + tolerance,
  );
}
