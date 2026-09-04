const paths: Record<string, string> = {
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  folder:
    "M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7h18",
  people:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M16 3a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-3.87 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3z",
  message:
    "M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-3 2V11.5A8.5 8.5 0 0 1 9.5 3h3A8.5 8.5 0 0 1 21 11.5z M7 9h8 M7 13h5",
  play: "m8 4 12 8-12 8V4z",
  wave: "M3 10v4 M7 6v12 M12 3v18 M17 6v12 M21 10v4",
  settings: "M4 7h16 M4 17h16 M8 4v6 M16 14v6",
  plus: "M12 5v14 M5 12h14",
  arrow: "M5 12h14 m-6-6 6 6-6 6",
  check: "m5 12 4 4L19 6",
  close: "m6 6 12 12 M6 18 18 6",
  sidebar: "M3 4h18v16H3z M9 4v16",
  shield: "m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6l9-4z m-4 10 3 3 5-6",
  help: "M9 8a3 3 0 1 1 5 2c-2 1-2 2-2 3 M12 17h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  search: "M10 3a7 7 0 1 1 0 14 7 7 0 0 1 0-14 M15 15l6 6",
};

export function WorkspaceIcon({
  name,
  size = 20,
}: {
  name: string;
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] ?? paths.spark} />
    </svg>
  );
}
