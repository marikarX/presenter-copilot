export type NativeClaimSourceKind =
  "native_text" | "native_chart_cache" | "native_table_cells";

export function isNativeClaimSourceKind(
  value: unknown,
): value is NativeClaimSourceKind {
  return (
    value === "native_text" ||
    value === "native_chart_cache" ||
    value === "native_table_cells"
  );
}

export function claimSourceLabel(kind: NativeClaimSourceKind = "native_text") {
  return kind === "native_chart_cache"
    ? "Raw chart cache"
    : kind === "native_table_cells"
      ? "Native table cells"
      : "Native slide text";
}

export type NativeClaimTarget = {
  object_id: string;
  text: string;
  label: string;
  source_kind?: NativeClaimSourceKind;
};

export const NATIVE_CLAIM_DISCLOSURE =
  "Chart values are raw cached data, not displayed/formatted values or verified workbook data. Table cells retain native row order. Chart visuals, images and notes are not analyzed.";
