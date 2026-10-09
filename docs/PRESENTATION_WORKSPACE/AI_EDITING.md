# AI and Voice Editing Contract

## Reviewed Copilot grouping (2026-10-08)

The planner now exposes group_objects with 2-20 distinct objects and ungroup_object.
Core resolves nested earlier-step object references, reads current staged geometry,
and binds preconditions itself. The provider cannot supply geometry fingerprints.
Supported top-level objects and groups reuse the existing native writers and their
connector, package-dependency, geometry, identity and paint-order restrictions.
Grouping returns a created group ID for later operations, including ungrouping.
Review lists the selected native object names and text; all affected slide preview,
explicit acknowledgment, exact reviewed bytes, re-index and revision undo remain.
Eight focused tests cover staged creation/group/ungroup, duplicate/forward/cross-slide/
unselected/precondition/wrong-kind rejection, review data and exact undo. Current
broad check passes 1326 Core/231 desktop tests, Workspace passes 117 workflows,
and rebuilt real-PowerPoint GUI passes six workflows including group/ungroup
exact native-reviewed Save and both Undo steps. Final review-data additions have
eight focused tests and mypy/lint/types validation after the broad check began.
See handoff for exact receipts and validation windows.
Live model quality and human usefulness remain unverified.


## Measured native text-box fitting (2026-10-04)

Fit text box uses owned direct preview/review/save/discard and Copilot fit_text_shape
(37 strict operation types). A current-revision read-only catalog resolves fonts/geometry
and native dependency fingerprints; Core binds each Copilot step to the actual staged
package and reviews its actual fonts. Historical text-target reads remain unchanged.
Grow increases height and restores authored font sizes; shrink retains geometry and
relative sizes with a 6-96pt minimum and cached-scale ceiling. Both explicitly enable
wrapping, restore authored paragraph spacing and replace automatic scaling with noAutofit.
These effects are disclosed. Unsupported structures/fonts/scripts, linked/grouped targets,
connector/animation dependencies and off-slide/unfittable results reject atomically.
Only managed height/font-size/wrapping/autofit properties may change; exact undo is retained.

A fresh 1224-test Core sweep, 177 desktop unit tests, types/lint/format checks and 18 native
PowerPoint opens / 10 exact undos pass. Native fixtures cover mixed fonts, bullets,
numbering, cached scaling and inherited Calibri/Arial placeholders; broad font/corpus
acceptance remains open. The final stable-build Electron sweep passes 112 workflows with
no renderer exceptions, including direct/Copilot staged fitting, save/reopen, discard and
exact undo. A verified Add text box readiness guard disables its controls until the slide
ID is available; the saved-profile reproduction now creates a revision. The 720x520
window verifies both fitting previews, invalidation and unchanged head after discard.
The fixture exposes existing-content overlap; collision avoidance is not claimed. Initial
failed/diagnostic sweeps remain in the receipts. The broader goal remains active.
See [current handoff](../SESSION_HANDOFF.md) for dependency decisions and exact receipts.

## Native text inheritance for fitting (2026-10-04)

A read-only text_inheritance module resolves internal layout/master/theme relationships,
placeholder categories, presentation/per-level/paragraph/run defaults, major/minor Latin
fonts, detached body/geometry and dependency-bound fingerprints. It preserves original
styles/packages. Native testing established layout sample paragraphs do not supply child
styles; list styles do. Ordinary text boxes prioritize presentation defaults over master
otherStyle; placeholders use master categories, including body defaults for subtitles.
Partial run defaults merge without losing inherited fields. Unsupported/ambiguous/external
inheritance rejects. Existing direct-style inventory and GUI/schema remain unchanged.

Sixteen new tests pass in the 66-test resolver/table-fit/layout run; lint/mypy (161 files)
and formatting pass. Coverage reconciles 1185 unchanged prior serial IDs plus 16 new IDs
with the 1201 current collection. It is not a fresh full sweep. Nine native packages
verify 34 shapes/42 paragraphs, font family/size/bold/italic, geometry and unchanged bytes.
Receipts and earlier failed probes: .local/text-fit/. All 359 prior code/test hashes are
preserved; resolver/test additions bring the source freeze to 361 entries.

Text-box fitting is not yet exposed or accepted. Next: bullet/cached-scaling measurement,
Grow height / proportional Shrink fonts, minimum-size and slide-bound rejection, complete
fingerprint/package preservation, then direct/Copilot preview/review/save/discard/undo and
native/GUI verification. Theme override, complex-script/partial-transform/corpus coverage
remain unverified. Broad fidelity/integration, Fast Decisions calibration/latency and live
ChatGPT sign-in remain open; signing/clean Windows are accepted debt. Goal stays active.

## Reviewed native table row fitting (2026-10-04)

Auto-fit table rows now previews and reviews Grow or Compact before saving. Explicit
native grid/frame heights preserve column widths, position, cells/styles/spans and
other package parts. Exact installed fonts, margins, wrapping and paragraph spacing
constrain rows; merged-span deficits distribute after single-row minima. Unsupported
font inheritance/layout and off-slide results reject before mutation. Changed target/
strategy invalidates review; discard, retrieval refresh and exact undo reuse existing
owned transactions. Copilot fit_table_rows adds the 36th strict operation type, with
fresh staged fingerprints and actual previous row/table heights.

All 1185 Core cases (305/340/234/306), 177 desktop tests, TypeScript/mypy (160 files),
lint/formatting and 110 full Electron workflows pass. Corrected GUI tests wait for
actual row-height metadata; the initial placeholder comparison failure is retained.
Ten native PowerPoint packages across five fit cases match stored heights within
0.2pt, preserve other-slide pixels and verify five exact undos. Actual Electron/native
split import at 720x520 verifies 93.60pt growth, strategy invalidation, save/reopen,
compact discard, staged Copilot fitting and undo to 72pt without exceptions/overflow.
The preview no longer clips that split row; sampled first-row background boundaries
match Office within 0.16% slide height. Paragraph pitch still differs and existing
mixed header colors retain low contrast. This is fixture geometry acceptance, not
broad font/corpus fidelity. Reviewed screenshots and all receipts: .local/table-fit/.
Source freeze: 359 code/test hashes, 346 prior files unchanged, ten changed, three new.

Next: text-box grow/shrink fitting with resolved placeholder/layout/master/theme font
and spacing inheritance, then broader renderer/corpus/real-model/integration acceptance,
Fast Decisions calibration/latency and live Sign in with ChatGPT. Signing and clean
Windows remain accepted debt. Dirty work is preserved; the broader goal stays active.

## Reviewed native table merge/split (2026-10-04)

Merge or split table cells previews and reviews whole inclusive rectangles. Merge retains
paragraph/run formatting and stored cell styling while collecting nonempty text at the
top-left; split restores the existing grid and keeps combined text there. Undo restores
prior bytes. Valid span inventory supports top-left text editing, complete-range formatting
and visible borders; covered cells disable text edits. Partial merged ranges and partially
covered larger neighbor edges reject before mutation. Row/column reshape stays disabled
until merges are split. Unsupported/malformed spans and hidden covered content stay read-only.

Copilot merge_table_cells/split_table_cells bring the strict operation set to 35, with
fresh staged fingerprints and previous span/text review. Core coverage: 1163 serial sweep
IDs plus three late guards, reconciled to 1166 current IDs; final focused run 38 pass.
177 desktop tests, types/lint/formatting, 15 native PowerPoint packages and twelve exact
undos pass. Focused actual Electron/native import at 720x520 covers direct and Copilot
merge/split with no renderer errors or modal overflow. All 108 full GUI workflows pass; the final native-focused rebuild covers the later
row-fit disclosure wording.

Preserved mixed text styles may lower contrast on the origin fill. PowerPoint expands a
split text fixture's first row from 72 to 93.6 points, while the experimental preview
keeps the stored height; final text-fit fidelity is unproven. Next: automatic fitting,
broad fidelity/integration, Fast Decisions calibration and live ChatGPT sign-in acceptance.
Signing and clean Windows remain accepted debt. [SESSION_HANDOFF.md](../SESSION_HANDOFF.md)
records exact receipts and scope. Dirty source freeze: 356 entries, 339 prior preserved,
fourteen intentional changes and three new files.

## Reviewed native table borders (2026-10-04)

Table borders provides reviewed inclusive ranges, nine edge presets, solid/dash/dot,
0.25-12 pt RGB lines and explicit removal. Shared edges update reciprocal neighbors,
including cells outside the selected range; the dialog discloses this and invalidates
review on changes. Only selected line properties are replaced. Canonical preservation
checks protect all remaining cell content, styling and geometry; the transaction
preserves other package parts and supports retrieval refresh and exact undo.

Copilot set_table_borders is the 33rd strict operation type. Core binds fresh fingerprints
and captures actual staged previous edges, including reciprocal sides. Remove requires
null width/color. Merged/complex cells and ambiguous line properties stay read-only;
merge/split requires coordinated inventory and editor support before enabling spans.

Current evidence: 1148 Core tests in four serial batches, 51 new border cases,
177 desktop tests, 106 real Electron/local Core GUI workflows, a focused final-build
720x520 native-import workflow, eight native PowerPoint packages and four exact undos.
Types, lint and formatting pass. The experimental preview shows borders/removal but
dash spacing differs from PowerPoint. Broad corpus, Fast Decisions calibration/latency
and live Sign in with ChatGPT acceptance remain open; signing and clean Windows are
accepted debt. See [SESSION_HANDOFF.md](../SESSION_HANDOFF.md) for dependencies,
final-source validation scope and .local/table-borders/ receipts. The dirty-tree
source freeze preserves 340 prior entries, changes ten and adds three (353 total).

## Reviewed native axes (2026-10-04)

Chart axes offers category/value visibility, tick labels, major/minor gridlines and
simple titles. Value bounds/units can be fixed or restored to automatic; native number
formats are optional. The existing owned review/save/discard/undo lifecycle is reused.
Copilot set_chart_axis binds staged fingerprints and previous settings. The chart-only
clone writer preserves workbook/data, other chart fields, IDs and cross-axis relations.
Pie/date/secondary axes, logarithmic/display-unit scales and ambiguous/extension
settings stay read-only. Complex titles can be retained but not replaced.

Focused Electron review at 720x520 and native PowerPoint column/bar/line acceptance
verify the workflow and packages. Preview fonts, tick placement and minor-grid spacing
remain approximate. Full evidence and next work: [session handoff](../SESSION_HANDOFF.md).


## Chart-label preview acceptance (2026-10-04)

The snapshot host uses the pinned renderer's public renderSlide/chartInstances API,
retaining PDF/font/scale/handle cleanup. Preview-only label formatters support native
names, common numeric formats and pie percentage precision; pie labels wrap. Charts
are settled with animations disabled, resize and flush before capture. Sparse caches,
unsupported/combo charts, ambiguous boxes, mismatched values and unknown formats retain
renderer fallback. Native workbook/chart data and packages remain untouched.

Focused native column/bar/line/pie imports and second-series currency review at 720x520
were visually inspected; common content/format omissions are repaired. Full PowerPoint
layout, legend-key decoration, complex formats and broad-corpus fidelity remain open.
Current evidence and continuation priorities: [session handoff](../SESSION_HANDOFF.md).


## Goal

Natural-language and voice requests should modify the same presentation model as direct manipulation while remaining bounded, reviewable, reversible, and source-aware.

The AI is a planner over typed presentation operations, not an unrestricted document mutator.

## Flow

```text
User text / voice
      |
      v
Intent + target resolver
      |
      v
Context builder
      |
      v
AI planner
      |
      v
Typed EditPlan
      |
      v
Core validation / compatibility checks
      |
      +--> preview/review when required
      |
      v
Edit Transaction Engine
      |
      v
New presentation revision
```

## Voice path

Voice uses the same planning path after local ASR.

Dictation supports both a selected-text rewrite and a general Copilot edit-plan
request for the current slide or whole deck. General capture does not require
a text object, so it also works on blank slides. Both paths validate the exact
current revision before and after local Core capture and display an editable
transcript for explicit use. The Copilot dialog locks scope and provider actions
during capture/review; using the transcript fills its request and still requires
the separate Propose changes action. Provider privacy, typed-operation review,
exact-byte save, and undo stay unchanged. Captures create no Utterance or
ProviderRun and do not emit durable final transcripts. Unmount, source/project
deletion, reset and shutdown cancel the owned capture.

Transcript review asks users to correct uncertain wording, names, numbers and
target references. No model confidence score or automatic ambiguity resolver
is implemented. Reviewed outline briefings/refinements and Copilot requests now
support local dictation before creation as well as on existing decks.

Hold Ctrl+Shift+Space in the focused selected-text editor, Copilot dialog or
outline planner to dictate locally; release Space, Control or Shift to review.
An early release waits for the owned capture to start. Escape, window blur,
document hiding or editor-context disposal cancels an unfinished gesture;
Escape while final transcription is pending discards that capture's review
after stop completes. Repeated presses do not start another capture. The
shortcut has no system-wide registration and leaves the separate Live Assist
Ctrl+Alt+Space shortcut unchanged. Existing Dictate/Stop/Discard buttons remain.
Reviewed text requires explicit use and a separate provider proposal/save.
Capture IDs and context generations prevent late replies from changing another
editor session. Cancellation failures retain owner controls for retry; this
does not prove hardware microphone release under device failure.
Real microphone quality/latency and automatic ambiguity handling remain open.

Requirements:

- transcription remains visible/reviewable;
- raw audio follows existing local-first rules;
- speech recognition does not itself grant mutation authority;
- low-confidence or ambiguous commands should become proposals rather than destructive actions;
- voice may reference current selection and recent context, but target resolution remains explicit in the resulting plan.

## Planning contract

### Reviewed creation from a briefing

The planner keeps up to ten successful drafts in a temporary conversation, with
submitted instructions and explicit branch parents. Earlier drafts restore their
manual edits, original run/evidence review and captured briefing fields. Pending
refinement text clears on restoration. Refinement sends the current briefing,
selected edited draft and new instruction using the existing privacy/context
contract. The request baseline is immutable, so editing an ancestor later cannot
change a descendant's comparison. Before/current changes include title, rationale,
points, notes, evidence references and positional additions/removals; moved slides
can appear as several changes. Current manual changes are included. Restoration
makes no provider call or deck mutation. Failed proposals retain edits/history.
History locks during capture/provider work; at ten successes, restoration and
final review remain available while further proposals stop. Close/mode switch
clears this temporary session. Explicit outline-session Save/Restore/Clear now provides
durable recovery through the existing project-owned session service. Broader edit
conversations and measured live provider usefulness remain open.

The creation dialog supports objective, audience, user briefing, and slide
count, followed by a structured outline proposal. Users can edit every title,
point, and note, inspect supplied evidence excerpts, and request refinements
before reviewing the final outline and explicitly creating a native PPTX.
The planner uses existing project retrieval, speaker style, provider privacy
routing, execution budgets, and content-free run manifests. An earlier draft
is passed as untrusted context. A cited evidence ID must have been supplied to
that exact provider request. A citation is traceability, not proof of factual
support; users still review claims and unresolved evidence.

The planning task accepts 1–40 slides and has a separate bounded 48,000-character
context allowance so ordinary complete outlines can be refined. Overlarge
drafts fail explicitly. Creation uses the existing native outline writer and
ingestion/revision/indexing path. It retains evidence references in notes and
the originating successful run in PPTX properties. The initial implementation
does not yet provide voice creation, template selection, asset insertion, or
multi-object editing within the creation flow.

The planner receives bounded, trust-labeled context:

- current presentation revision ID;
- explicit selection/slide range;
- relevant slide/object summaries;
- semantic narrative context;
- permitted Project Brain evidence;
- Audience Model context when relevant;
- Speaker Profile/style policy;
- relevant rehearsal findings;
- compatibility constraints for targeted objects.

Imported slide text and source material are untrusted data, not application instructions.

## Edit plan principles

### Reviewed native transactions now implemented

The Workspace's **Edit slide together** dialog edits supported text shapes and
plain speaker notes in one proposal. It stages the actual native PPTX, displays
the proposed slide and before/after content, and requires explicit review before
saving all changes as one revision. Discarding restores the current preview;
undo restores the whole preceding revision. Successful saves request re-indexing;
a failed re-index is reported separately from the committed revision.

Core accepts 1–20 allowlisted native operations through
`presentation.workspace.prepare_edit_plan`. Existing edit validators and package
writers compose the changes in private managed snapshots without moving the
revision head. `open_edit_plan_preview` uses the existing bounded, hash-verified
reader; `apply_edit_plan` publishes those exact bytes after a final integrity
check and compare-and-swap against the baseline revision. `reject_edit_plan`
discards the private package. Four previews may be retained for up to 15 minutes,
with cleanup on expiry, discard, source/project deletion, reset, or shutdown.
Project access reconciles abandoned previews and staging packages after a crash,
preserving registered snapshots, live previews, and unrelated files.

Project schema v13 records operation types and stable target IDs in the same
transaction as the revision commit. It does not store source/replacement content
or a user's free-text summary in that audit record. History exposes this optional
transaction metadata. The engine supports text/style/geometry/image, object and
slide operations; the manual dialog exposes grouped text and notes.

**Ask Copilot to edit** uses `presentation.workspace.propose_edit_plan` to
generate a review-only plan through the selected reasoning provider. The task's
strict schema allows 1–20 operations across 31 native types, with rationales and
supplied evidence IDs. Its bounded 48,000-character context contains a selected
baseline inventory and edit capabilities, with source text kept as untrusted
data. Required inventory is never silently truncated. Core validates scope and
evidence, binds native preconditions against the rolling staged package, and
checks the current source around inference. No provider can write a revision.

The dialog renders the native proposal and requires viewing all affected slides
before explicit review and save. Changing the request invalidates approval;
re-proposal starts from the same baseline. **Refine proposal** instead supplies
the owned unsaved draft and its original instruction as untrusted context, plus
the user's new feedback. Core retains validated provider intent only in the
transient review plan, preserving earlier-step creation references. The provider
returns a complete replacement plan from the original baseline, with all scope,
evidence, assets and native preconditions validated again. Refinement requires
the same slide scope and attached pictures and an unexpired proposal owned by
the project/document; ownership and the baseline are rechecked around inference.
An oversized draft fails the existing context bound explicitly. Failed inference
or validation retains the previous available proposal. A valid replacement gets
a new full preview and requires fresh acknowledgment before exact-byte save.
The UI discards the old preview only after a replacement exists; Core callers
retain explicit control over discarding previews. No intermediate revision is
published. Malformed provider output retains the ordinary unavailable-health guard;
the dialog offers an explicit Check reasoning provider action using the existing
synthetic connection test, with no project content. A successful check restores
provider readiness before the user retries. Successful provider-run and evidence
IDs are recorded with the transaction. Earlier-step created-target references and reviewed voice plan requests are
implemented. Raw image ingestion and live model quality remain open. This implementation does not establish PowerPoint renderer fidelity or
complete PW4.

Copilot supports native table/chart creation, value edits and structural edits
through the existing writers. Selected-slide context supplies up to twenty
table descriptions and twenty chart descriptions per slide. Tables expose
bounded plain cells; charts expose bounded cached categories/series/values,
never hidden worksheet contents. Merged or complex tables, linked or unsupported
charts and unsupported structural changes remain read-only. Core binds fresh
fingerprints against each staged step, including earlier created targets.
Retained row/column/category/series source indices must be unique and ordered;
null denotes an addition. Chart type is preserved by edits, and complex titles
must retain their existing text. The review dialog shows exact proposed cells
and chart values with expandable previous data from the same staged target.
Native slide previews, evidence review and explicit acknowledgment remain
required. Chart data operations retain prior decoration settings. Explicit legend
editing is available separately; other presentation controls remain open.

A plan must contain typed operations rather than free-form XML/code.

Representative operations:

- `replace_text`;
- `insert_text`;
- `set_text_style`;
- `move_object`;
- `resize_object`;
- `change_object_layer`;
- `delete_object`;
- `duplicate_object`;
- `insert_image`;
- `replace_image`;
- `set_crop`;
- `create_shape`;
- `create_text_box`;
- `reorder_slide`;
- `duplicate_slide`;
- `insert_slide`;
- `delete_slide`;
- `set_notes`;
- `attach_evidence`;
- `create_appendix_slide`;
- `apply_layout`;
- constrained chart/table operations.

Unknown operation types fail closed.

## Preconditions

Every operation should include sufficient preconditions to detect stale or mis-targeted execution.

Examples:

- base revision;
- expected object ID/type;
- expected current text hash/range;
- expected slide membership;
- compatibility tier;
- required asset existence.

Broad edits should carry an explicit resolved target list.

## Review policy

### May apply immediately

Initially limited to reversible, local, narrowly targeted changes such as:

- replace selected text;
- change selected object style;
- move/resize selected supported object;
- update notes on current slide.

Even these create undo/history transactions.

### Must preview

- multi-slide transformations;
- slide deletion;
- large text replacement;
- structural narrative changes;
- generated images/diagrams replacing existing content;
- adding unsupported or weakly supported claims;
- operations requiring PPTX normalization;
- theme-wide changes;
- appendix/main-deck movement across several slides;
- stale/rebased AI plans.

## Claim and evidence behavior

The planner must not treat generated prose as evidence.

When a user asks "find support for this" the operation sequence should be conceptually:

1. identify claim;
2. retrieve candidate evidence;
3. show support/conflict status;
4. propose citation/wording change;
5. attach canonical evidence references only after validation.

If evidence conflicts with the slide, the system should propose correction or qualification rather than silently citing the conflicting source.

## Preserve-my-voice behavior

For content rewriting, source priority should generally be:

1. user-authored wording from current deck;
2. strong user explanations/practiced answers;
3. explicit style guidance;
4. source-backed facts;
5. generated connective language.

The planner should not unnecessarily replace presenter language with generic consultant-style prose.

## Rehearsal-derived edits

A rehearsal finding is input to a proposal, not authority to mutate.

Examples:

- strong spoken explanation -> `replace_text` or `set_notes` proposal;
- repeated objection -> appendix or evidence proposal;
- unsupported exact number -> citation/correction proposal;
- slide consistently skipped -> deletion/merge proposal;
- answer too long -> slide simplification proposal.

Every such proposal retains a reference to the originating run/question/answer/finding where practical.

## Whole-deck transformations

Commands such as "make this executive" should not be implemented as one unconstrained prompt producing a replacement deck.

Preferred sequence:

1. analyze narrative and audience;
2. produce a transformation plan;
3. identify slides to keep/merge/move/remove;
4. show structural preview;
5. apply per-slide typed operations;
6. preserve a revision checkpoint;
7. refresh semantics and evidence bindings;
8. report compatibility impacts.

## Generated images and diagrams

Generated media enters through the asset subsystem and is inserted by reference.

The edit plan should never embed opaque remote URLs as durable presentation state.

Generated diagrams should prefer structured editable representations when practical; otherwise store them as image assets with prompt/provenance metadata.

## Safety and security constraints

AI planning cannot:

- execute macros/add-ins;
- emit arbitrary filesystem paths for mutation;
- fetch external PPTX relationships without explicit product support;
- directly modify OOXML package bytes;
- bypass privacy/provider context rules;
- auto-accept normalization/fidelity loss;
- mark generated facts as source-backed without canonical evidence.

## Observability

For debugging and user trust, retain metadata such as:

- origin: direct / AI text / AI voice / rehearsal proposal;
- task type;
- model/provider identity where remote reasoning was used;
- resolved target IDs;
- plan fingerprint;
- applied/rejected/stale status;
- compatibility warnings;
- evidence references;
- resulting revision ID.

Do not persist confidential full prompts by default if existing provider policy avoids them.

## Deterministic validation

Provider output is never trusted solely because it matches a JSON schema.

Core validation must verify:

- referenced slides/objects exist in the base revision;
- operations are permitted for object compatibility tiers;
- geometry/ranges are bounded;
- asset references exist;
- evidence IDs are canonical and eligible;
- operation count/size stays within task limits;
- broad destructive plans trigger review;
- the plan has not become stale.

## Earlier-step creation references

Native plans and provider proposals accept `{ "created_by": N }` in a target
ID field, where N is a one-based index of an earlier operation. Object fields
require that operation's `created_object_id`; slide fields require its
`created_slide_id`. This covers new and duplicated targets, layout-source IDs
and entries in slide-reordering lists. References never grant authority outside
the selected deck or overwrite scope. Missing/forward/self references to an
unavailable creation, the wrong target kind, and deleted targets fail before
any plan is published; staging cleanup removes the intermediate packages.

For example: create a slide (step 1), create a text box with
`slide_id: {created_by: 1}` (step 2), then format and transform it using
`slide_id: {created_by: 1}, object_id: {created_by: 2}`. Core resolves native IDs
from actual staged outcomes. Provider preconditions are then derived from the
current staged snapshot, including prior style/text/geometry changes. Baseline
slides and objects outside the user's selection remain forbidden. Operations
returned for review contain resolved IDs and deterministic preconditions.

The final native package is still rendered and explicitly reviewed, saved by
exact digest as one revision, and undone as a unit. Creation IDs join the
content-free transaction audit. No provider-generated paths/XML/media or
automatic application are added.

## Native object layer changes (2026-10-03)

`change_object_layer` is the seventeenth provider operation. It accepts a slide
and supported slide-level shape/picture target with direction `forward`,
`backward`, `front` or `back`. Later XML drawing nodes paint in front. Core binds
the exact staged `expected_object_ids` order; provider input cannot override that
precondition. Created-target references resolve before binding. Unsupported
groups/connectors and other targets excluded by the existing safe-delete
capability remain read-only for layering.

The direct inspector uses the same revision operation. A boundary move is a
no-op. Changed moves preserve object contents and package relationships, become
immutable revisions and use ordinary undo. In plans, moves participate in the
same reviewed staged bytes and atomic save as other operations.

## Explicit deck-image attachments (2026-10-03)

`presentation.workspace.propose_edit_plan` accepts optional `asset_ids`, up to
eight unique deck assets with 16 MiB total original bytes. Core reads them from
the verified baseline before inference. Context exposes IDs, names, hashes,
formats and dimensions; it contains no raw image or thumbnail bytes. Assets are
untrusted metadata, not interpreted visual evidence. Existing project privacy
routing still gates the provider request.

Provider operation `create_picture` accepts `slide_id` (including an earlier
created-slide reference), attached `asset_id`, bounded native `geometry` and
`alt_text`. Core rejects IDs outside the explicit attachment set, injects image
bytes only into the native staging operation and retains ordinary target-scope
and revision/hash checks. Public proposal operations restore the opaque asset
reference and omit injected image bytes. Review identifies the source image
and alt text. Exact staged bytes save atomically and undo through normal history.
New project uploads and model image understanding remain open.

## Explicit native chart legends (2026-10-04)

`set_chart_legend` accepts a selected slide/chart (including earlier-created targets),
`legend_position` of hidden/left/right/top/bottom/top_right and boolean
`legend_overlay`. Hidden with overlay is invalid. Bounded selected-chart context
includes editable legend position/overlay metadata, never private fingerprints or
workbook contents. Core binds fresh chart fingerprints against every staged step.
Manual layouts/extensions/unknown legend settings remain read-only. Review exposes
exact previous and proposed settings; native preview and acknowledgment are required.

The writer clones the selected chart part and chart relationships while preserving
original workbook bytes and every non-legend chart node. Placement/overlay changes
retain existing legend styles/entries; hiding removes the legend, showing it again
uses default styling, and undo restores the original. The existing native data writer
continues to preserve legend settings. No automatic second-series legend change,
provider XML/path authority or separate save path is introduced.

## Reviewed native chart colors (2026-10-04)

`set_chart_color` accepts selected/earlier-created slide/chart, zero-based
`series_index` (0-5), nullable `point_index` (0-23, null means series) and opaque
#RRGGBB `color`. Supported columns/bars allow series or individual points; pies use
points and lines use series strokes. Chart color metadata reports native explicit
RGB or null for defaults/custom styles; Core supplies fresh staged fingerprints and
previous explicit fill/stroke values. Invalid/foreign/stale/read-only targets fail.

The shared chart-appearance writer clones only the selected chart/relationships and
retains original workbook bytes; data, geometry, IDs, notes and legend remain intact.
Selected color replaces fill/outline color/opacity while preserving widths/dashes/
effects; line series retain their unused area fill. Individual point/marker overrides
remain when changing a series. Native preview, exact-hash save and undo are unchanged.
Review shows target indexes and known previous/proposed RGB; live model quality and
resolved theme/custom color inspection remain separate acceptance requirements.

## Reviewed native table range formatting (2026-10-04)

`format_table_cells` targets a supported selected/earlier-created native table with
inclusive zero-based row_start/row_end (0-11) and column_start/column_end (0-7).
Its strict style object has seven required nullable fields: boolean bold/italic,
integer font_size_pt (6-96), #RRGGBB font_color/fill_color, alignment of
left/center/right/justify, and vertical_alignment of top/center/bottom. At least one
field must be non-null; null preserves each cell's native/inherited setting.
Bounded selected-table metadata reports explicit supported settings or null for
inherited/custom values. Core binds a fresh staged fingerprint and captures only
requested previous settings for every selected cell. Review shows one-based ranges,
proposed fields and previous selected cell settings, then requires native slide
preview and acknowledgment. No provider can supply paths, XML or fingerprints.
Text, dimensions, frame identity, borders, margins and table-style references remain
intact. Merged/linked/complex cells stay read-only; invalid/stale inputs do not publish.
This extends the schema to 30 native operation types without a new public IPC method.

## Reviewed native data labels (2026-10-04)

`set_chart_labels` accepts selected/earlier-created native charts, nullable series_index
(0-5; null means all), position, four required booleans show_value/show_category/
show_series/show_percent and nullable number_format (1-64 characters when supplied).
Position is hidden/default or a supported labels.positions value; visible labels
require a content flag and percentage flags are pie-only. Null formats retain native
formatting. Hiding preserves settings. Requested fields apply to point overrides too;
custom text and decoration remain, and may override displayed content. Context reports
bounded current series/point settings; Core supplies fresh staged fingerprints and
captures previous selected settings. Exact previous/proposed settings are reviewed
before package save. Manual layouts, ambiguous/indexed/linked extension limitations
remain read-only. No new public IPC or database migration is needed.
The native PowerPoint package is verified; experimental label preview formatting/
content and a possible completion race remain open fidelity work, explicitly disclosed.
