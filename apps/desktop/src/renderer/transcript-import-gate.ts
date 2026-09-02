export type SourceImportKind = "presentation" | "supporting" | "transcript";

/** Keep the transcript authorization disclosure ahead of the native picker. */
export function requiresTranscriptDisclosure(
  kind: SourceImportKind,
  transcriptAuthorized: boolean,
): boolean {
  return kind === "transcript" && !transcriptAuthorized;
}
