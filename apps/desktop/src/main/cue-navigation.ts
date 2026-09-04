export type CueNavigationDirection = "previous" | "next";

/** Select an index from a newest-first cue list: previous is older, next is newer. */
export function nextCueIndex(
  cueIds: readonly string[],
  currentCueId: string | null,
  direction: CueNavigationDirection,
): number | null {
  if (cueIds.length === 0) return null;
  const currentIndex =
    currentCueId === null ? -1 : cueIds.indexOf(currentCueId);
  if (currentIndex < 0) return direction === "next" ? 0 : cueIds.length - 1;
  const offset = direction === "previous" ? 1 : -1;
  return (currentIndex + offset + cueIds.length) % cueIds.length;
}
