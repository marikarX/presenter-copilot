import { usePowerPointAppearance } from "./NativeAppearance";
import type { NarrativeContext } from "./PresentationNarrative";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";
import { VoiceEditInstruction } from "./VoiceEditInstruction";
import { DeckPictureAssets, type Asset } from "./DeckPictureAssets";
import {
  openEditPlanPreview,
  renderEditPlanSlide,
  type EditPlanIdentity,
  type PreviewSlide,
} from "./edit-plan-preview";

type Operation = {
  type: string;
  params: Record<string, unknown>;
  rationale: string;
  evidence_ids: string[];
  previous_data?: Record<string, unknown>;
};
type Proposal = EditPlanIdentity & {
  changed: boolean;
  summary: string;
  baseline_revision_id: string;
  provider_id: string;
  model_id: string;
  review_operations: Operation[];
  attached_assets: Array<
    Pick<Asset, "asset_id" | "name" | "width" | "height" | "sha256">
  >;
  slide_takeaways?: {
    revision_id: string;
    incomplete: boolean;
    items: Array<{
      slide_id: string;
      slide_number: number;
      takeaway: string;
      status: "reviewed" | "needs_review";
      shortened: boolean;
    }>;
  } | null;
  presentation_narrative?: NarrativeContext | null;
  reviewed_claim_context?: {
    incomplete: boolean;
    claims: Array<{
      claim_id: string;
      slide_number: number;
      quote_excerpt: string | null;
      quote_truncated: boolean;
      coverage: string;
      span_status: string;
      reviewed_for_revision: boolean;
      links: Array<{
        relation: string;
        status: string;
        grounding_included: boolean;
      }>;
    }>;
  } | null;
  target_slides: PreviewSlide[];
  baseline_slides: PreviewSlide[];
  evidence: Array<{
    evidence_id: string;
    text: string;
    source_locator: unknown;
  }>;
};
const labels: Record<string, string> = {
  replace_text_shape: "Replace text",
  replace_speaker_notes: "Update speaker notes",
  format_text_shape: "Format text",
  format_shape_style: "Change shape colors",
  transform_object: "Move or resize an object",
  group_objects: "Group native objects",
  ungroup_object: "Ungroup native objects",
  change_object_layer: "Change object layer",
  crop_picture: "Crop a picture",
  adjust_picture: "Adjust picture brightness, contrast or grayscale",
  rotate_object: "Rotate or flip an object",
  set_slide_background: "Change the slide background",
  set_slide_hidden: "Hide or show a slide in the slide show",
  set_slide_transition: "Change the slide transition",
  set_slide_animations: "Change the slide animations",
  set_alt_text: "Change the alt text",
  copy_object_format: "Copy one object's format onto others",
  set_theme_fonts: "Change the theme fonts",
  set_theme_colors: "Change the theme colors",
  set_slide_sections: "Change the slide sections",
  set_text_hyperlink: "Set or remove a text link",
  reorder_slides: "Reorder the presentation",
  apply_slide_layout: "Change slide layout",
  create_slide: "Insert a blank slide",
  create_authored_slide: "Insert an authored slide",
  duplicate_slide: "Duplicate a slide",
  delete_slide: "Delete a slide",
  create_text_box: "Add a text box",
  create_shape: "Add a shape",
  create_diagram: "Add a structured diagram",
  replace_diagram: "Edit a structured diagram",
  delete_diagram: "Remove a structured diagram",
  create_table: "Add a native table",
  replace_table_cells: "Update table cells",
  reshape_table: "Change table rows or columns",
  create_chart: "Add a native chart",
  replace_chart_data: "Update chart data",
  fit_text_shape: "Fit native text box",
  fit_table_rows: "Auto-fit native table rows",
  merge_table_cells: "Merge native table cells",
  split_table_cells: "Split native table cells",
  set_table_borders: "Change native table borders",
  format_table_cells: "Format table cells",
  set_chart_color: "Change native chart color",
  set_shape_fill: "Change native shape fill and opacity",
  set_chart_fill: "Change native chart fill and opacity",
  set_chart_marker: "Change native line markers",
  set_chart_axis: "Change native chart axis",
  set_chart_labels: "Change native data labels",
  set_chart_legend: "Place or hide chart legend",
  reshape_chart: "Change chart categories or series",
  create_picture: "Insert an attached picture",
  delete_object: "Delete an object",
  duplicate_object: "Duplicate an object",
};

function GroupTargets({ data }: { data: Record<string, unknown> | undefined }) {
  if (!data) return null;
  if (Array.isArray(data.group_members)) {
    return (
      <div>
        <p>Objects to group:</p>
        <ul>
          {data.group_members.map((item, index) => {
            const target = item as { name: string; text: string };
            return (
              <li key={index}>
                {target.name}
                {target.text ? `: ${target.text}` : ""}
              </li>
            );
          })}
        </ul>
        <p>Child content and placement are preserved.</p>
      </div>
    );
  }
  if (
    typeof data.format_source === "string" &&
    Array.isArray(data.format_targets)
  )
    return (
      <p>
        Copy the format of {data.format_source} onto{" "}
        {data.format_targets.map(String).join(", ")}. Text and placement stay
        the same.
      </p>
    );
  if (typeof data.group_name === "string")
    return (
      <p>
        Ungroup {data.group_name}. Children retain their content and placement.
      </p>
    );
  return null;
}

function PlanData({
  params,
  label,
}: {
  params: Record<string, unknown>;
  label: string;
}) {
  if (typeof params.minimum_size_pt === "number")
    return (
      <p>
        {label}:{" "}
        {params.strategy === "grow"
          ? "Grow box height and restore authored font sizes"
          : "Shrink fonts proportionally and retain box geometry"}
        . Minimum size {String(params.minimum_size_pt)} pt. Enable wrapping,
        restore authored paragraph spacing and replace cached automatic scaling.
      </p>
    );
  if (Array.isArray(params.paragraphs) && params.geometry_pt) {
    const geometry = params.geometry_pt as { width: number; height: number };
    return (
      <div className="pw-data-review">
        <p>
          {label}: box {geometry.width.toFixed(2)} ×{" "}
          {geometry.height.toFixed(2)} pt; cached font scale{" "}
          {(Number(params.cached_font_scale ?? 1) * 100).toFixed(1)}%.
        </p>
        <table>
          <caption>{label} authored fonts</caption>
          <tbody>
            {params.paragraphs.flatMap((value, index) => {
              const p = value as {
                runs: { family: string; size_hundredths: string }[];
                end: { family: string; size_hundredths: string };
              };
              return [...p.runs, p.end].map((run, i) => (
                <tr key={`${index}:${i}`}>
                  <th>
                    Paragraph {index + 1},{" "}
                    {i < p.runs.length ? `run ${i + 1}` : "end"}
                  </th>
                  <td>
                    {run.family} ·{" "}
                    {(Number(run.size_hundredths) / 100).toFixed(2)} pt
                  </td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    );
  }
  if (Array.isArray(params.border_edges))
    return (
      <div className="pw-data-review">
        <table>
          <caption>{label} shared border edges</caption>
          <thead>
            <tr>
              <th>Cell</th>
              <th>Side</th>
              <th>Source</th>
              <th>Line</th>
              <th>Width</th>
              <th>Color</th>
            </tr>
          </thead>
          <tbody>
            {params.border_edges.map((value, index) => {
              const edge = value as Record<string, unknown>;
              return (
                <tr key={index}>
                  <td>
                    {Number(edge.row) + 1},{Number(edge.column) + 1}
                  </td>
                  <td>{String(edge.side)}</td>
                  <td>{String(edge.source)}</td>
                  <td>
                    {edge.visible === false
                      ? "removed"
                      : edge.line_style === null
                        ? "inherited"
                        : String(edge.line_style)}
                  </td>
                  <td>
                    {edge.width_pt === null
                      ? "inherited"
                      : String(edge.width_pt)}
                  </td>
                  <td>
                    {edge.color === null
                      ? "native or inherited"
                      : String(edge.color)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  if (typeof params.border_scope === "string")
    return (
      <p>
        {label} table borders: rows {Number(params.row_start) + 1}–
        {Number(params.row_end) + 1}, columns {Number(params.column_start) + 1}–
        {Number(params.column_end) + 1} · {params.border_scope} ·{" "}
        {params.line_style === "none"
          ? "remove"
          : `${String(params.line_style)} ${String(params.width_pt)} pt ${String(params.color)}`}{" "}
        · shared neighboring edges included.
      </p>
    );
  if (typeof params.axis_kind === "string")
    return (
      <p>
        {label} {params.axis_kind} axis: {params.visible ? "shown" : "hidden"} ·
        tick labels {String(params.tick_labels)} · major/minor gridlines{" "}
        {params.major_gridlines ? "on" : "off"}/
        {params.minor_gridlines ? "on" : "off"} · title{" "}
        {params.title === null ? "keep" : JSON.stringify(params.title)} · bounds{" "}
        {params.minimum === null ? "auto" : String(params.minimum)} to{" "}
        {params.maximum === null ? "auto" : String(params.maximum)} · units{" "}
        {params.major_unit === null ? "auto" : String(params.major_unit)}/
        {params.minor_unit === null ? "auto" : String(params.minor_unit)} ·
        number format{" "}
        {params.number_format === null ? "keep" : String(params.number_format)}
      </p>
    );
  if (Array.isArray(params.label_series)) {
    return (
      <div className="pw-data-review">
        <table>
          <caption>{label} chart labels</caption>
          <tbody>
            {params.label_series.map((state, index) => (
              <tr key={index}>
                <th>
                  Series {Number(state.series_index) + 1}: {String(state.name)}
                </th>
                <td>
                  {String(state.position).replaceAll("_", " ")} · value{" "}
                  {state.show_value ? "on" : "off"} · category{" "}
                  {state.show_category ? "on" : "off"} · series{" "}
                  {state.show_series ? "on" : "off"} · percent{" "}
                  {state.show_percent ? "on" : "off"} · format{" "}
                  {state.number_format === null
                    ? "native source"
                    : String(state.number_format)}
                  {Array.isArray(state.points) && state.points.length ? (
                    <details>
                      <summary>Point overrides</summary>
                      {state.points.map(
                        (point: Record<string, unknown>, index: number) => (
                          <p key={index}>
                            Point {Number(point.index) + 1}:{" "}
                            {String(point.position)} · value{" "}
                            {point.show_value ? "on" : "off"} · category{" "}
                            {point.show_category ? "on" : "off"} · series{" "}
                            {point.show_series ? "on" : "off"} · percent{" "}
                            {point.show_percent ? "on" : "off"} · format{" "}
                            {point.number_format === null
                              ? "native source"
                              : String(point.number_format)}
                            {point.custom_text ? " · custom text retained" : ""}
                          </p>
                        ),
                      )}
                    </details>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (
    typeof params.position === "string" &&
    typeof params.show_value === "boolean"
  ) {
    return (
      <div>
        <p>
          {label} chart labels:{" "}
          {params.series_index === null
            ? "all series"
            : `series ${Number(params.series_index) + 1}`}{" "}
          · {params.position.replaceAll("_", " ")}
        </p>
        <p>
          Values {params.show_value ? "on" : "off"} · categories{" "}
          {params.show_category ? "on" : "off"} · series names{" "}
          {params.show_series ? "on" : "off"} · percentages{" "}
          {params.show_percent ? "on" : "off"} · format{" "}
          {params.number_format === null
            ? "keep current"
            : String(params.number_format)}
          .
        </p>
      </div>
    );
  }
  if (typeof params.strategy === "string")
    return (
      <p>
        {label} table fitting:{" "}
        {params.strategy === "grow"
          ? "grow rows as needed"
          : "compact rows to measured text"}
        . Row heights and total table height may change; columns, text and
        styling stay unchanged. Review fit and nearby content.
      </p>
    );
  if (Array.isArray(params.row_heights_pt))
    return (
      <div>
        <p>
          {label} table height: {Number(params.height_pt).toFixed(2)} pt
        </p>
        <ul>
          {params.row_heights_pt.map((v, i) => (
            <li key={i}>
              Row {i + 1}: {Number(v).toFixed(2)} pt
            </li>
          ))}
        </ul>
      </div>
    );
  if (typeof params.merge_action === "string") {
    return (
      <p>
        {label}: {params.merge_action} rows {Number(params.row_start) + 1}–
        {Number(params.row_end) + 1}, columns {Number(params.column_start) + 1}–
        {Number(params.column_end) + 1}. Merge collects paragraphs in the
        top-left cell; split keeps combined text there and restores the existing
        grid. Undo restores the original distribution.
      </p>
    );
  }
  if (Array.isArray(params.merge_regions)) {
    return (
      <div>
        <p>
          {label} merged cells:{" "}
          {params.merge_regions.length
            ? params.merge_regions
                .map(
                  (v) =>
                    `row ${v.row + 1}, column ${v.column + 1}: ${v.row_span} × ${v.column_span}`,
                )
                .join("; ")
            : "none"}
        </p>
        <PlanData params={{ cells: params.cells }} label={label} />
      </div>
    );
  }
  if (
    typeof params.row_start === "number" &&
    params.style &&
    typeof params.style === "object"
  ) {
    return (
      <div>
        <p>
          {label} table formatting: rows {params.row_start + 1}–
          {Number(params.row_end) + 1}, columns{" "}
          {Number(params.column_start) + 1}–{Number(params.column_end) + 1}
        </p>
        <ul>
          {Object.entries(params.style)
            .filter(([, value]) => value !== null)
            .map(([key, value]) => (
              <li key={key}>
                {key.replaceAll("_", " ")}:{" "}
                {typeof value === "boolean"
                  ? value
                    ? "on"
                    : "off"
                  : String(value)}
              </li>
            ))}
        </ul>
      </div>
    );
  }
  if (Array.isArray(params.cell_styles)) {
    return (
      <div className="pw-data-review">
        <table>
          <caption>{label} cell formatting</caption>
          <tbody>
            {params.cell_styles.map((item, index) => (
              <tr key={index}>
                <th>
                  Row {Number(item.row) + 1}, column {Number(item.column) + 1}
                </th>
                <td>
                  {Object.entries(item.style)
                    .map(
                      ([key, value]) =>
                        `${key.replaceAll("_", " ")}: ${value === null ? "inherited or custom" : typeof value === "boolean" ? (value ? "on" : "off") : String(value)}`,
                    )
                    .join(" · ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (params.fill && typeof params.fill === "object") {
    const fill = params.fill as Record<string, unknown>;
    return (
      <div>
        <p>
          {label}{" "}
          {typeof params.series_index === "number"
            ? `chart fill: series ${params.series_index + 1} · ${params.point_index === null ? "entire series" : `point ${Number(params.point_index) + 1}`}`
            : "shape fill"}{" "}
          · {String(fill.kind).replaceAll("_", " ")}.
        </p>
        {fill.kind === "solid" ? (
          <p>
            {String(fill.color)} · opacity {String(fill.opacity_percent)}%
          </p>
        ) : null}
        {fill.kind === "linear_gradient" && Array.isArray(fill.stops) ? (
          <>
            <p>Angle: {String(fill.angle_degrees)} degrees</p>
            <ul>
              {fill.stops.map((value, index) => {
                const stop = value as Record<string, unknown>;
                return (
                  <li key={index}>
                    {String(stop.position_percent)}%: {String(stop.color)} ·
                    opacity {String(stop.opacity_percent)}%
                  </li>
                );
              })}
            </ul>
          </>
        ) : null}
      </div>
    );
  }
  if ("marker_symbol" in params && "marker_size" in params) {
    return (
      <p>
        {label} chart markers: series {Number(params.series_index) + 1} ·
        {String(params.marker_symbol ?? "native default")} ·{" "}
        {String(params.marker_size ?? "native default")} pt. Individual point
        overrides and marker colors are retained.
      </p>
    );
  }
  if (
    typeof params.series_index === "number" &&
    "point_index" in params &&
    "color" in params
  ) {
    return (
      <p>
        {label} chart color: series {params.series_index + 1},{" "}
        {params.point_index === null
          ? "entire series"
          : `point ${Number(params.point_index) + 1}`}{" "}
        ·{" "}
        {typeof params.color === "string"
          ? params.color
          : "native default or custom formatting"}
      </p>
    );
  }
  if (
    typeof params.legend_position === "string" &&
    typeof params.legend_overlay === "boolean"
  ) {
    return (
      <p>
        {label} legend: {params.legend_position.replaceAll("_", " ")} ·{" "}
        {params.legend_overlay ? "overlays plot" : "does not overlay plot"}
      </p>
    );
  }
  if (
    Array.isArray(params.cells) &&
    params.cells.every(
      (row) =>
        Array.isArray(row) && row.every((cell) => typeof cell === "string"),
    )
  ) {
    const rows = params.cells as string[][];
    return (
      <div className="pw-data-review">
        <table>
          <caption>{label} table cells</caption>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {row.map((cell, column) => (
                  <td key={column}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (
    !Array.isArray(params.categories) ||
    !params.categories.every((value) => typeof value === "string") ||
    !Array.isArray(params.series)
  )
    return null;
  const categories = params.categories as string[];
  const series = params.series.filter(
    (value): value is { name: string; values: number[] } =>
      value &&
      typeof value === "object" &&
      typeof value.name === "string" &&
      Array.isArray(value.values) &&
      value.values.length === categories.length &&
      value.values.every(
        (number: unknown) =>
          typeof number === "number" && Number.isFinite(number),
      ),
  );
  if (!series.length || series.length !== params.series.length) return null;
  return (
    <div className="pw-data-review">
      <p>
        {String(params.title)} · {String(params.chart_type)}
      </p>
      <table>
        <caption>{label} chart values</caption>
        <thead>
          <tr>
            <th>Category</th>
            {series.map((row, index) => (
              <th key={index}>{row.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((category, index) => (
            <tr key={index}>
              <th>{category}</th>
              {series.map((row, column) => (
                <td key={column}>{String(row.values[index])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CopilotEditPlan({
  projectId,
  documentId,
  revisionId,
  slideNumber,
  disabled,
  onRestore,
  prefill,
  onPrefillConsumed,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  slideNumber: number;
  disabled: boolean;
  onRestore: (applied: boolean) => Promise<void>;
  /** Opens the request with a suggested instruction; nothing is sent until submitted. */
  prefill?: {
    instruction: string;
    scope: "slide" | "deck";
    nonce: number;
  } | null;
  onPrefillConsumed?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [refinement, setRefinement] = useState("");
  const [scopeChoice, setScopeChoice] = useState("slide");
  useEffect(() => {
    if (!prefill) return;
    setOpen(true);
    setInstruction(prefill.instruction);
    setScopeChoice(prefill.scope);
    // The panel remounts per revision: consume the prefill so it opens only once.
    onPrefillConsumed?.();
  }, [onPrefillConsumed, prefill]);
  const [attachments, setAttachments] = useState<Asset[]>([]);
  const [deckAssetBusy, setDeckAssetBusy] = useState(false);
  const [projectAssetBusy, setProjectAssetBusy] = useState(false);
  const assetBusy = deckAssetBusy || projectAssetBusy;
  const [proposedRequest, setProposedRequest] = useState<{
    instruction: string;
    scope: string;
    assets: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providerCheck, setProviderCheck] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [slides, setSlides] = useState<PreviewSlide[]>([]);
  const [ordinal, setOrdinal] = useState(1);
  const [image, setImage] = useState<string | null>(null);
  const [seen, setSeen] = useState<number[]>([]);
  const [reviewed, setReviewed] = useState(false);
  const native = usePowerPointAppearance(
    proposal
      ? {
          projectId,
          documentId,
          revisionId: proposal.baseline_revision_id,
          sourceSha256: proposal.sha256,
          planId: proposal.plan_id,
        }
      : null,
    ordinal,
  );
  const displayedImage = native.image ?? image;
  const [displayReady, setDisplayReady] = useState(false);
  useEffect(() => {
    setDisplayReady(false);
    setReviewed(false);
  }, [displayedImage]);
  useEffect(() => {
    if (native.pending) setReviewed(false);
  }, [native.pending]);
  const owned = useRef<Proposal | null>(null);
  const touchedRenderer = useRef(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const reviewHeading = useRef<HTMLHeadingElement>(null);
  const scope = { project_id: projectId, document_id: documentId };
  const reordered = proposal?.review_operations.some(
    (operation) => operation.type === "reorder_slides",
  );
  const changedIds = new Set(
    proposal?.review_operations
      .map((operation) => operation.params.slide_id)
      .filter((value): value is string => typeof value === "string"),
  );
  const originalIds = new Set(
    proposal?.baseline_slides.map((slide) => slide.slide_id),
  );
  const affected = slides.filter(
    (slide) =>
      reordered ||
      changedIds.has(slide.slide_id) ||
      !originalIds.has(slide.slide_id),
  );
  const required = affected.length ? affected : slides.slice(0, 1);
  const allSeen =
    required.length > 0 &&
    required.every((slide) => seen.includes(slide.ordinal));
  const requestChanged =
    proposedRequest?.instruction !== instruction ||
    proposedRequest?.scope !== scopeChoice ||
    proposedRequest?.assets !== attachments.map((a) => a.asset_id).join(",");

  useEffect(() => {
    if (open) dialog.current?.showModal();
  }, [open]);
  useEffect(
    () => () => {
      if (owned.current)
        void window.presenterCopilot.core
          .request("presentation.workspace.reject_edit_plan", {
            project_id: projectId,
            document_id: documentId,
            plan_id: owned.current.plan_id,
          })
          .catch(() => undefined);
    },
    [projectId, documentId],
  );
  useEffect(
    () => () => {
      if (image) URL.revokeObjectURL(image);
    },
    [image],
  );

  async function discardOwned() {
    if (!owned.current) return;
    try {
      unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "presentation.workspace.reject_edit_plan",
          { ...scope, plan_id: owned.current.plan_id },
        ),
      );
    } catch (caught) {
      if (
        !isCoreError(caught) ||
        caught.code !== "PRESENTATION_EDIT_PLAN_NOT_FOUND"
      )
        throw caught;
    }
    owned.current = null;
  }

  async function close(applied = false) {
    setBusy(true);
    try {
      await discardOwned();
      if (touchedRenderer.current) {
        touchedRenderer.current = false;
        await onRestore(applied);
      }
      setProposal(null);
      setImage(null);
      setOpen(false);
      setRefinement("");
      setProviderCheck(null);
    } catch (caught) {
      setError(
        caught instanceof Error || isCoreError(caught)
          ? caught.message
          : "The proposal could not be closed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function showSlide(number: number) {
    const bytes = await renderEditPlanSlide(number);
    const copy = new Uint8Array(bytes);
    setImage(
      URL.createObjectURL(new Blob([copy.buffer], { type: "image/png" })),
    );
    setOrdinal(number);
  }

  async function propose(refine = false) {
    if (voiceBusy) return;
    if (refine && (!owned.current || requestChanged || !refinement.trim()))
      return;
    setBusy(true);
    setError(null);
    setProviderCheck(null);
    setReviewed(false);
    if (!refine) {
      setSeen([]);
      setImage(null);
      setSlides([]);
    }
    let candidate: Proposal | null = null;
    try {
      if (!refine) {
        await discardOwned();
        setProposal(null);
      }
      const result = unwrapInvokeResult<Proposal>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.propose_edit_plan",
          {
            ...scope,
            expected_revision_id: revisionId,
            instruction: refine ? refinement : instruction,
            ...(refine ? { previous_plan_id: owned.current?.plan_id } : {}),
            asset_ids: attachments.map((asset) => asset.asset_id),
            ...(scopeChoice === "slide"
              ? { slide_numbers: [slideNumber] }
              : {}),
          },
        ),
      );
      candidate = result;
      if (
        result.baseline_revision_id !== revisionId ||
        !Array.isArray(result.review_operations) ||
        !result.review_operations.length ||
        result.review_operations.length > 20
      )
        throw new Error("The proposed edit response could not be verified.");
      if (refine) await discardOwned();
      owned.current = result;
      candidate = null;
      setProposal(result);
      setRefinement("");
      setSeen([]);
      setProposedRequest({
        instruction,
        scope: scopeChoice,
        assets: attachments.map((a) => a.asset_id).join(","),
      });
      touchedRenderer.current = true;
      const previewSlides = await openEditPlanPreview(scope, result);
      setSlides(previewSlides);
      const initial =
        previewSlides.find((slide) =>
          result.review_operations.some(
            (operation) => operation.params.slide_id === slide.slide_id,
          ),
        ) ?? previewSlides[0];
      if (!initial)
        throw new Error("The proposed presentation has no previewable slides.");
      await showSlide(initial.ordinal);
      reviewHeading.current?.focus({ preventScroll: true });
      dialog.current?.scrollTo({ top: 0 });
    } catch (caught) {
      if (candidate) {
        await window.presenterCopilot.core
          .request("presentation.workspace.reject_edit_plan", {
            ...scope,
            plan_id: candidate.plan_id,
          })
          .catch(() => undefined);
      }
      setError(
        caught instanceof Error || isCoreError(caught)
          ? caught.message
          : "The edit proposal is unavailable.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function changeSlide(number: number) {
    setBusy(true);
    setError(null);
    try {
      await showSlide(number);
    } catch (caught) {
      setError(
        caught instanceof Error || isCoreError(caught)
          ? caught.message
          : "The slide could not be previewed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (
      voiceBusy ||
      !proposal ||
      !reviewed ||
      !allSeen ||
      !displayReady ||
      native.pending ||
      !image ||
      !proposal.changed ||
      requestChanged ||
      !!refinement.trim()
    )
      return;
    setBusy(true);
    setError(null);
    try {
      const saved = unwrapInvokeResult<{ sha256: string }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.apply_edit_plan",
          {
            ...scope,
            plan_id: proposal.plan_id,
            reviewed_sha256: proposal.sha256,
            confirm: true,
          },
        ),
      );
      owned.current = null;
      if (saved.sha256 !== proposal.sha256)
        throw new Error(
          "The saved revision does not match the reviewed proposal. Refresh this deck.",
        );
      await close(true);
    } catch (caught) {
      setError(
        caught instanceof Error || isCoreError(caught)
          ? caught.message
          : "The proposed edits could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="primary-button"
        disabled={disabled}
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
      >
        Ask Copilot to edit
      </button>
      {open
        ? createPortal(
            <dialog
              ref={dialog}
              className="pw-create-dialog pw-edit-review pw-copilot-edit"
              aria-labelledby="pw-copilot-edit-title"
              onCancel={(event) => {
                event.preventDefault();
                if (!busy) void close();
              }}
            >
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void propose();
                }}
              >
                <h2
                  ref={reviewHeading}
                  tabIndex={-1}
                  id="pw-copilot-edit-title"
                >
                  Copilot edit plan
                </h2>
                <p className="muted">
                  Describe the changes you want. Review the proposed slides and
                  content before saving one reversible revision.
                </p>
                <details
                  className="pw-edit-request"
                  open={!proposal || requestChanged}
                >
                  <summary>Edit your request</summary>
                  <div className="pw-edit-request-fields">
                    <label>
                      What should change?
                      <textarea
                        aria-label="Copilot edit request"
                        value={instruction}
                        maxLength={500}
                        rows={3}
                        disabled={busy || voiceBusy}
                        required
                        onChange={(event) => setInstruction(event.target.value)}
                        placeholder="Shorten the slide text, move the detailed explanation into notes, and make the decision stand out."
                      />
                    </label>
                    <label>
                      Apply this request to
                      <select
                        aria-label="Copilot edit scope"
                        value={scopeChoice}
                        disabled={busy || voiceBusy}
                        onChange={(event) => setScopeChoice(event.target.value)}
                      >
                        <option value="slide">Current slide</option>
                        <option value="deck">Whole presentation</option>
                      </select>
                    </label>
                    <DeckPictureAssets
                      projectId={projectId}
                      documentId={documentId}
                      revisionId={revisionId}
                      disabled={
                        busy ||
                        voiceBusy ||
                        projectAssetBusy ||
                        attachments.length >= 8
                      }
                      onBusyChange={setDeckAssetBusy}
                      onAttach={(asset) =>
                        setAttachments((current) =>
                          current.some((a) => a.asset_id === asset.asset_id) ||
                          current.length >= 8
                            ? current
                            : [...current, asset],
                        )
                      }
                    />
                    <DeckPictureAssets
                      source="project"
                      projectId={projectId}
                      documentId={documentId}
                      revisionId={revisionId}
                      disabled={
                        busy ||
                        voiceBusy ||
                        deckAssetBusy ||
                        attachments.length >= 8
                      }
                      onBusyChange={setProjectAssetBusy}
                      onAttach={(asset) =>
                        setAttachments((current) =>
                          current.some((a) => a.asset_id === asset.asset_id) ||
                          current.length >= 8
                            ? current
                            : [...current, asset],
                        )
                      }
                    />
                    {attachments.length ? (
                      <section aria-label="Attached deck pictures">
                        <p>
                          {attachments.length} of 8 pictures attached.
                          Descriptions and dimensions are sent with the request.
                        </p>
                        {attachments.map((asset) => (
                          <button
                            key={asset.asset_id}
                            type="button"
                            className="secondary-button"
                            disabled={busy || voiceBusy || assetBusy}
                            onClick={() =>
                              setAttachments(
                                attachments.filter(
                                  (a) => a.asset_id !== asset.asset_id,
                                ),
                              )
                            }
                          >
                            Remove {asset.name}
                          </button>
                        ))}
                      </section>
                    ) : null}
                    <VoiceEditInstruction
                      projectId={projectId}
                      documentId={documentId}
                      revisionId={revisionId}
                      slideNumber={slideNumber}
                      scopeChoice={scopeChoice}
                      disabled={busy || assetBusy}
                      onBusyChange={setVoiceBusy}
                      onUse={(text) => {
                        setInstruction(text);
                        setReviewed(false);
                      }}
                    />
                    <button
                      type="submit"
                      className="primary-button"
                      disabled={
                        busy || voiceBusy || assetBusy || !instruction.trim()
                      }
                    >
                      {busy
                        ? "Preparing…"
                        : proposal
                          ? "Propose revised request"
                          : "Propose changes"}
                    </button>
                  </div>
                </details>
                {proposal ? (
                  <>
                    <h3>{proposal.summary}</h3>
                    <section aria-label="Refine Copilot proposal">
                      <label>
                        What should change in this proposal?
                        <textarea
                          aria-label="Copilot proposal refinement"
                          value={refinement}
                          maxLength={500}
                          rows={2}
                          disabled={
                            busy || voiceBusy || assetBusy || requestChanged
                          }
                          onChange={(event) => {
                            setRefinement(event.target.value);
                            setReviewed(false);
                          }}
                          placeholder="Keep the shorter title, but move the supporting detail into notes."
                        />
                      </label>
                      <p className="muted">
                        Refine this unsaved draft while keeping its slide scope
                        and attached pictures. Review the replacement before
                        saving.
                      </p>
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={
                          busy ||
                          voiceBusy ||
                          assetBusy ||
                          requestChanged ||
                          !refinement.trim()
                        }
                        onClick={() => void propose(true)}
                      >
                        Refine proposal
                      </button>
                    </section>
                    <p className="muted">
                      {proposal.provider_id} · {proposal.model_id} · The current
                      deck is unchanged.
                    </p>
                    {native.controls}
                    {image ? (
                      <figure>
                        <img
                          key={displayedImage}
                          src={displayedImage ?? undefined}
                          alt={`Copilot proposed slide ${ordinal}`}
                          onLoad={(event) => {
                            const displayed = event.currentTarget;
                            void displayed
                              .decode()
                              .then(() => {
                                requestAnimationFrame(() =>
                                  requestAnimationFrame(() => {
                                    if (displayed.isConnected) {
                                      setDisplayReady(true);
                                      setSeen((previous) => [
                                        ...new Set([...previous, ordinal]),
                                      ]);
                                    }
                                  }),
                                );
                              })
                              .catch(() =>
                                setError(
                                  "The proposed slide image could not be decoded.",
                                ),
                              );
                          }}
                          onError={() => {
                            setDisplayReady(false);
                            if (native.image) native.rejectImage();
                            setError(
                              "The proposed slide image could not be loaded.",
                            );
                          }}
                        />
                        <figcaption>
                          Proposed slide {ordinal} of {slides.length}
                        </figcaption>
                      </figure>
                    ) : null}
                    {slides.length ? (
                      <label>
                        Review proposed slides
                        <select
                          aria-label="Proposed slide to review"
                          disabled={busy}
                          value={ordinal}
                          onChange={(event) =>
                            void changeSlide(Number(event.target.value))
                          }
                        >
                          {slides.map((slide) => (
                            <option key={slide.slide_id} value={slide.ordinal}>
                              Slide {slide.ordinal}
                              {required.some(
                                (item) => item.ordinal === slide.ordinal,
                              )
                                ? " · affected"
                                : ""}
                              {seen.includes(slide.ordinal) ? " · viewed" : ""}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                    <p className="muted">
                      Viewed{" "}
                      {
                        required.filter((slide) => seen.includes(slide.ordinal))
                          .length
                      }{" "}
                      of {required.length} affected slides.
                    </p>
                    {proposal.slide_takeaways ? (
                      <section aria-label="Slide takeaways used">
                        <h3>Slide takeaways used</h3>
                        <p>
                          Captured author intent, not source evidence. Later
                          takeaway changes do not update this proposal.
                        </p>
                        {proposal.slide_takeaways.incomplete ? (
                          <p>
                            Takeaway coverage is incomplete for this selection.
                          </p>
                        ) : null}
                        {proposal.slide_takeaways.items.map((item) => (
                          <article key={item.slide_id}>
                            <h4>
                              Slide {item.slide_number} ·{" "}
                              {item.status === "reviewed"
                                ? "reviewed for this revision"
                                : "inherited; needs review"}
                            </h4>
                            <p>{item.takeaway}</p>
                            {item.shortened ? (
                              <p>Takeaway text was shortened.</p>
                            ) : null}
                          </article>
                        ))}
                      </section>
                    ) : null}
                    {proposal.presentation_narrative ? (
                      <section aria-label="Narrative intent used">
                        <h3>Narrative intent used</h3>
                        <p>
                          {proposal.presentation_narrative.status === "reviewed"
                            ? "Reviewed for the preparation revision."
                            : "Inherited intent needs review."}
                        </p>
                        <dl>
                          {Object.entries(
                            proposal.presentation_narrative.fields,
                          )
                            .filter(([, text]) => text)
                            .map(([field, text]) => (
                              <div key={field}>
                                <dt>{field.replaceAll("_", " ")}</dt>
                                <dd>{text}</dd>
                              </div>
                            ))}
                        </dl>
                        {proposal.presentation_narrative.shortened_fields
                          .length ? (
                          <p>
                            Some narrative fields were shortened in the provider
                            context.
                          </p>
                        ) : null}
                        {proposal.presentation_narrative.lineage_truncated ? (
                          <p>Narrative history is incomplete.</p>
                        ) : null}
                        <p>
                          Intent captured at preparation; this is not source
                          evidence.
                        </p>
                      </section>
                    ) : null}
                    {proposal.reviewed_claim_context ? (
                      <section
                        className="pw-edit-review-changes"
                        aria-label="Claim grounding used"
                      >
                        <h3>Claim grounding used</h3>
                        <p className="muted">
                          Captured when this proposal was prepared. Relations
                          are your reviewed judgments; they do not verify claim
                          truth.
                        </p>
                        {proposal.reviewed_claim_context.incomplete ? (
                          <p>
                            Claim context is incomplete. Review omitted bindings
                            in Purpose.
                          </p>
                        ) : null}
                        {proposal.reviewed_claim_context.claims.map((claim) => (
                          <article key={claim.claim_id}>
                            <strong>
                              Slide {claim.slide_number} ·{" "}
                              {claim.coverage.replaceAll("_", " ")}
                            </strong>
                            <p>
                              {claim.quote_excerpt ??
                                "Quote changed or missing; rebind it in Purpose."}
                            </p>
                            {claim.quote_truncated && claim.quote_excerpt ? (
                              <p className="muted">
                                Quote excerpt shortened; review the full claim
                                in Purpose.
                              </p>
                            ) : null}
                            {claim.links.map((link, index) => (
                              <p key={index}>
                                {link.relation} · {link.status} ·{" "}
                                {link.grounding_included
                                  ? "excerpt supplied"
                                  : "excerpt not supplied"}
                              </p>
                            ))}
                          </article>
                        ))}
                      </section>
                    ) : null}
                    <section
                      className="pw-edit-review-changes"
                      aria-label="Copilot proposed changes"
                    >
                      <h3>Proposed changes</h3>
                      {proposal.review_operations.map((operation, index) => {
                        const beforeSlide = proposal.target_slides.find(
                          (slide) =>
                            slide.slide_id === operation.params.slide_id,
                        );
                        const replacement =
                          operation.params.replacement_text ??
                          operation.params.text;
                        return (
                          <article key={index}>
                            <strong>
                              {labels[operation.type] ?? "Proposed change"}
                              {beforeSlide
                                ? ` · original slide ${beforeSlide.ordinal}`
                                : ""}
                            </strong>
                            <p>{operation.rationale}</p>
                            <GroupTargets data={operation.previous_data} />
                            <PlanData
                              params={{
                                ...operation.params,
                                ...(operation.type === "merge_table_cells" ||
                                operation.type === "split_table_cells"
                                  ? {
                                      merge_action:
                                        operation.type === "merge_table_cells"
                                          ? "Merge"
                                          : "Split",
                                    }
                                  : {}),
                              }}
                              label="Proposed"
                            />
                            {operation.previous_data &&
                            operation.type !== "group_objects" &&
                            operation.type !== "ungroup_object" &&
                            operation.type !== "copy_object_format" ? (
                              <details>
                                <summary>
                                  {[
                                    "set_chart_fill",
                                    "set_shape_fill",
                                  ].includes(operation.type)
                                    ? "Previous native fill"
                                    : operation.type === "set_chart_marker"
                                      ? "Previous chart markers"
                                      : operation.type === "fit_text_shape"
                                        ? "Previous text fitting"
                                        : operation.type === "set_table_borders"
                                          ? "Previous border edges"
                                          : operation.type ===
                                              "format_table_cells"
                                            ? "Previous cell formatting"
                                            : operation.type ===
                                                "set_chart_axis"
                                              ? "Previous chart axis"
                                              : operation.type ===
                                                  "set_chart_labels"
                                                ? "Previous chart labels"
                                                : operation.type ===
                                                    "set_chart_color"
                                                  ? "Previous chart color"
                                                  : operation.type ===
                                                      "set_chart_legend"
                                                    ? "Previous legend settings"
                                                    : "Previous table/chart data"}
                                </summary>
                                <PlanData
                                  params={operation.previous_data}
                                  label="Previous"
                                />
                              </details>
                            ) : null}
                            {operation.type === "create_authored_slide" ? (
                              <div>
                                <p>{String(operation.params.title ?? "")}</p>
                                <ul>
                                  {Array.isArray(operation.params.bullets)
                                    ? operation.params.bullets
                                        .filter(
                                          (point): point is string =>
                                            typeof point === "string",
                                        )
                                        .map((point, pointIndex) => (
                                          <li key={pointIndex}>{point}</li>
                                        ))
                                    : null}
                                </ul>
                                <p className="muted">{`Template: ${String(operation.params.template)} · Layout: ${String(operation.params.layout)}`}</p>
                                <details>
                                  <summary>New slide speaker notes</summary>
                                  <p>
                                    {String(
                                      operation.params.notes ||
                                        "No speaker notes.",
                                    )}
                                  </p>
                                </details>
                              </div>
                            ) : null}
                            {operation.type === "create_picture" ? (
                              <p>
                                Picture:{" "}
                                {proposal.attached_assets.find(
                                  (a) =>
                                    a.asset_id === operation.params.asset_id,
                                )?.name ?? "Attached picture"}
                                . Alternative text:{" "}
                                {String(operation.params.alt_text || "None")}
                              </p>
                            ) : null}
                            {typeof replacement === "string" ? (
                              <p>{replacement || "Empty text"}</p>
                            ) : (
                              <p className="muted">
                                Review this structural or visual change in the
                                proposed presentation.
                              </p>
                            )}
                            {typeof operation.params.expected_text ===
                            "string" ? (
                              <details>
                                <summary>Previous text</summary>
                                <p>
                                  {operation.params.expected_text ||
                                    "Empty text"}
                                </p>
                              </details>
                            ) : null}
                            {operation.evidence_ids.length ? (
                              <details>
                                <summary>Referenced evidence</summary>
                                {operation.evidence_ids.map((id) => (
                                  <p key={id}>
                                    {proposal.evidence.find(
                                      (item) => item.evidence_id === id,
                                    )?.text ?? "Evidence excerpt unavailable"}
                                  </p>
                                ))}
                              </details>
                            ) : null}
                          </article>
                        );
                      })}
                    </section>
                    {!proposal.changed ? (
                      <p role="status">
                        This proposal makes no changes. Revise your request or
                        discard it.
                      </p>
                    ) : null}
                    {requestChanged ? (
                      <p role="status">
                        Your request changed. Propose the revised request before
                        saving.
                      </p>
                    ) : null}
                    <label className="pw-edit-review-ack">
                      <input
                        type="checkbox"
                        checked={reviewed}
                        disabled={
                          busy ||
                          !allSeen ||
                          !displayReady ||
                          native.pending ||
                          !proposal.changed ||
                          requestChanged ||
                          !!refinement.trim()
                        }
                        onChange={(event) => setReviewed(event.target.checked)}
                      />
                      I reviewed all proposed edits, sources, and affected
                      slides.{" "}
                      {native.image
                        ? "The proposed slide appearance comes from PowerPoint."
                        : "The experimental Browser appearance may differ from PowerPoint."}
                    </label>
                  </>
                ) : null}
                {error ? (
                  <section>
                    <p role="alert">{error}</p>
                    {proposal ? (
                      <>
                        <p className="muted">
                          The proposal remains available. If the provider is
                          unavailable, check it before retrying. The check sends
                          a synthetic request with no project content.
                        </p>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={busy || voiceBusy || assetBusy}
                          onClick={() => {
                            setBusy(true);
                            setProviderCheck(null);
                            void window.presenterCopilot.core
                              .request("provider.test", {})
                              .then((result) => {
                                unwrapInvokeResult(result);
                                setError(null);
                                setProviderCheck(
                                  "Provider check passed. You can retry refinement or review the previous proposal.",
                                );
                              })
                              .catch((caught: unknown) => {
                                setError(
                                  caught instanceof Error || isCoreError(caught)
                                    ? caught.message
                                    : "The provider check failed.",
                                );
                              })
                              .finally(() => setBusy(false));
                          }}
                        >
                          Check reasoning provider
                        </button>
                      </>
                    ) : null}
                  </section>
                ) : null}
                {providerCheck ? <p role="status">{providerCheck}</p> : null}
                <div className="pw-create-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void close()}
                  >
                    {proposal ? "Discard Copilot proposal" : "Cancel"}
                  </button>
                  {proposal ? (
                    <button
                      type="button"
                      className="primary-button"
                      disabled={
                        busy ||
                        voiceBusy ||
                        !reviewed ||
                        !allSeen ||
                        !displayReady ||
                        native.pending ||
                        !image ||
                        !proposal.changed ||
                        requestChanged ||
                        !!refinement.trim()
                      }
                      onClick={() => void apply()}
                    >
                      Save Copilot changes
                    </button>
                  ) : null}
                </div>
              </form>
            </dialog>,
            document.body,
          )
        : null}
    </>
  );
}
