/** Pie and doughnut charts take one series whose points carry the colors. */
export const pieLike = (kind: string | undefined) =>
  kind === "pie" || kind === "doughnut";
