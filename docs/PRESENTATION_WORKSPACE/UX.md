# Presentation Workspace UX

## Workspace layout

Default desktop arrangement:

```text
+--------------------------------------------------------------------------------+
| Project / presentation                                    Ready v12   Rehearse |
+------------------+--------------------------------------+----------------------+
| Slide navigator  | Presentation canvas                  | Copilot              |
|                  |                                      |                      |
| 01 Title         | selected slide                       | text / voice          |
| 02 Problem       |                                      | context-aware chat   |
| 03 Decision      | direct editing handles               | proposed changes      |
| 04 Economics     |                                      | evidence / rationale  |
|                  |                                      |                      |
+------------------+--------------------------------------+----------------------+
| Notes | Sources | Claims | Rehearsal findings | Version history             |
+--------------------------------------------------------------------------------+
```

The exact layout may change, but three concepts should remain visible and tightly connected:

1. presentation structure;
2. current editable slide;
3. conversational/AI assistance.

## Direct editing

Users should not need AI for ordinary edits.

Minimum interactions:

- click/select object;
- double-click or Enter to edit text;
- drag to move;
- handles to resize;
- common keyboard operations: delete, duplicate, copy/paste, undo/redo;
- slide drag/reorder;
- context toolbar/inspector for common formatting;
- image replace/crop;
- notes editor.

The editor should avoid exposing raw OOXML concepts.

## AI side chat

AI conversation is presentation-aware by default.

Context precedence:

1. explicit user selection;
2. current slide;
3. selected slide range;
4. presentation objective/narrative;
5. Project Brain evidence;
6. Audience Model;
7. Speaker Profile;
8. recent rehearsal findings.

The UI should make scope visible, e.g. `Editing: Slide 6` or `Editing: Slides 4-8`, so broad actions are not surprising.

## Voice interaction

Voice is another input modality to the same command/planning system, not a separate feature silo.

Examples:

- "Change this title to emphasize the business impact."
- "Add the point I just made about failover testing."
- "Put these implementation details in an appendix."
- "Create a visual for this architecture."

Voice transcription should appear before or alongside execution so the user can detect recognition errors.

The current dictation control is limited to one supported text target. It pins
the current revision, slide, and object for local capture; the user can review
and edit the transcript before explicitly moving it into the existing rewrite
instruction field. Provider use requires the separate rewrite action. Capture
or transcript review locks workspace navigation, and a changed revision
discards the transcript.

For low-risk, local edits, an optional fast-apply mode may be considered later. Initial behavior should remain reviewable.

## Selection-aware commands

A command should resolve a bounded target set before planning an edit.

Examples:

- selected text -> text operation;
- selected image -> replace/crop/style operation;
- selected slide -> slide-level transformation;
- selected slides -> multi-slide operation;
- no selection -> current slide by default;
- explicit "whole deck" -> presentation-wide operation.

If a command would affect materially more content than its resolved selection implies, require preview rather than silently widening scope.

## Change proposals

### Lightweight changes

For local, easily reversible actions such as changing selected text or moving one supported object, the app may apply immediately while recording a transaction in undo/history.

### Structural or broad changes

Preview before apply when an operation:

- changes multiple slides;
- removes content;
- replaces a slide layout substantially;
- introduces generated facts or claims;
- moves material to/from appendix;
- changes theme/design across the deck;
- would alter or flatten unsupported PPTX objects.

A proposal should show:

- target slides/objects;
- concise rationale;
- before/after preview or structured diff;
- evidence/rehearsal trigger when relevant;
- compatibility warning if export fidelity may change.

Actions: `Apply`, `Apply individually`, `Revise`, `Reject`.

## Rehearsal findings panel

Run and Challenge findings should be actionable objects rather than static feedback prose.

Example:

```text
Slide 8
High-confidence finding

Your spoken explanation of migration risk was clearer and 42% shorter
than the current slide text.

[Preview slide rewrite] [Save to notes] [Ignore]
```

Other finding types:

- unsupported numeric claim;
- recurring audience objection;
- excessive slide density;
- explanation consistently omitted;
- useful user analogy not represented in slide/notes;
- likely appendix candidate;
- current wording conflicts with source evidence.

No finding applies edits automatically.

## Sources and claims

A selected claim/text block should be able to expose its evidence relationships.

Useful actions:

- `Find support`;
- `Attach source`;
- `Show source`;
- `Mark as assertion/opinion`;
- `Add citation`;
- `Move evidence to notes/appendix`.

The UI must distinguish source-backed facts from user statements and AI suggestions.

## Unsupported imported content

Unsupported objects require visible status without making the deck unusable.

Possible presentation:

- object renders normally from imported preview/fidelity path;
- selection indicates `Preserved object - limited editing`;
- supported operations may include move/resize/delete;
- unsupported semantic editing is disabled;
- export retains the original object whenever possible.

The user should not have to learn what XML feature caused the limitation.

## Version history

The workspace needs presentation-level versioning beyond a simple undo stack.

Record meaningful checkpoints such as:

- import baseline;
- before/after broad AI transformation;
- user-named checkpoint;
- marked-ready revision;
- rehearsal-bound revision;
- exported revision.

The UI should allow visual comparison and restore without rewriting historical rehearsal/session bindings.

## Ready/presentation boundary

Draft editing and active presentation state must be separate.

When the user starts Run or Live Assist:

- bind the session to a concrete presentation revision;
- optionally prompt to use current draft or last ready revision;
- do not let background AI proposals silently alter that bound revision.

## Failure behavior

### AI unavailable

Direct editing remains fully usable.

### ASR unavailable

Text chat/direct editing remain usable; voice editing is disabled with a typed actionable status.

### PPTX export compatibility warning

Show which objects/features may not round-trip and offer:

- export with preserved unsupported content where possible;
- PDF export;
- duplicate-and-normalize only after explicit user choice.

### Corrupt/unsupported PPTX

Keep the original file immutable, report the failing slide/object where possible, and avoid destructive repair without a user-created copy.

## Arrange objects together (2026-10-03)

The Objects inspector opens a shared native review dialog with a checklist of
current-slide objects. Unsupported geometry stays visible but disabled. Select
2-20 editable objects, choose left/center/right/top/middle/bottom alignment or
horizontal/vertical equal-gap distribution, then preview. Alignment uses the
selection's combined bounds. Distribution keeps the first and last objects in
position, sorts by the relevant coordinate, preserves unequal dimensions and
requires at least three objects with room for nonnegative gaps. Rounding uses
integer native geometry units. The dialog reports invalid/no-change selections.

Sizes, styling and stacking order remain unchanged. The preview opens staged
PPTX bytes in the native renderer; save stays disabled until the image loads
and the user acknowledges review. All moves save as one revision, reindex the
source and undo together. Cancellation discards private staging and restores
the current deck after renderer use. This adds selection-based alignment. Canvas geometry selection now feeds the
checklist; snapping, grouping and drag repositioning remain open.

## Canvas object selection (2026-10-03)

Enable Select objects on slide to inspect editable geometry over the native
slide image. Click selects one object and populates the Objects inspector.
Shift/Ctrl/Meta-click adds or removes objects; Enter/Space supports the same
keyboard modifier behavior. Drag from empty slide space to select objects whose
bounds intersect the marquee (up to 20), in either direction. Escape clears
selection. Unsupported geometry is omitted from canvas picking but remains in
the inspector inventory. Overlapping objects follow the package's paint order;
the object dropdown remains available for obscured targets.

Selection outlines use native geometry scaled to the actual displayed image,
including letterboxing and resize. No content is changed by selecting. The
selection seeds Arrange objects together and clears on slide/revision reload.
The overlay is disabled while loading or voice owns the workflow. Canvas picks
represent rectangular object bounds; this does not implement text-character
hit testing, group/rotation editing, snapping or drag repositioning.

## Reuse a deck picture (2026-10-03)

Objects -> Add a picture -> Browse deck pictures lists embedded PNG/JPEG media
from the current verified revision, including unused master/layout images.
Thumbnails show names and original dimensions; Next pictures advances bounded
pages. Skipped unsupported/invalid/oversized entries are counted. Use fills the
insertion form, resets obsolete local file selection and alt text, and preserves
aspect ratio in its default placement. Add picture is a separate revision action.
A local upload can still replace the selection after reading finishes. Competing
picture controls lock during an asset read; scope/revision changes discard stale
choices. Browsing and selection do not mutate the deck or contact providers.

## Reviewed canvas drag moves (2026-10-03)

Drag an editable object to move it or the current selection. Modifier clicks
remain additive selection; movement starts after four screen pixels. Proposed
ghost bounds move together. Snap object dragging to 0.1 inch increments is
optional and enabled by default. Whole-selection clamping keeps every object
inside the slide without altering size, spacing or paint order. Escape or
pointer cancellation abandons the gesture.

Release opens Review dragged objects with named before/after native positions.
Preview all changes renders staged PPTX bytes; acknowledgment and Save reviewed
changes commit one revision. Undo restores the batch. Revision changes clear
selection. The gesture moves outlines; native bitmap changes appear in the
review preview. Advanced alignment guides, object-edge snapping, grouping and
live bitmap dragging remain open.


## Project pictures (2026-10-03)

Objects -> Add a picture -> Project pictures uploads local PNG/JPEG images and
browses reusable project thumbnails. Use fills the insertion form; Add picture
remains a separate revision action. Upload and selection leave the deck head
unchanged. The Copilot request dialog can upload/browse and explicitly attach
the same library images, sharing the eight-image/16 MiB request limit with deck
pictures. Only descriptions/dimensions/hashes enter provider context.

Remove library item opens inline confirmation. Confirm remove drops library
availability; saved decks and staged previews retain copies. Keep picture cancels.
Returning to the panel requires Browse project pictures to reload the library.
Image reads/uploads lock competing picture controls. Invalid uploads and failed
integrity checks surface errors. The library is currently shown inside loaded
deck workflows; a standalone pre-deck management GUI remains open.


## Claim and evidence review (2026-10-03)

Purpose -> Claims and evidence shows reviewed claim counts and coverage. Choose
an object, enter an exact unique quote, and Search evidence in local supporting,
transcript or note sources. Linked excerpts remain visible for review; select
Supports claim, Contradicts claim or Context only. Any quote/link/relation change
clears acknowledgment. Save reviewed claim requires explicit review and stores
semantics without changing PPTX bytes. Up to four excerpts/20 claims per slide.

Existing claims show source snapshots and current/changed/missing evidence state.
Review claim fills the form; changed quotes must be rebound to current text and
stale evidence must be searched/linked again. Every inherited claim needs review
on a new revision. Remove claim records a revision-local tombstone, preserving
prior semantic history for undo. Incomplete history/text inventory has an alert.
Coverage represents the user's evidence relation judgment; no automatic truth
assessment, model claim extraction or semantic search is provided in this flow.


## Claim grounding in Copilot review (2026-10-03)

Copilot edit proposals show Claim grounding used when reviewed bindings exist.
Coverage and source relations reflect the preparation snapshot. Excerpt supplied
means that linked current text survived context budgeting and is available for
citation; excerpt not supplied does not authorize citing its ID. Changed/missing
quotes must be rebound in Purpose and do not appear as historical quote text in
the provider packet. Inherited/stale links require review before current support.
Incomplete context and shortened quote excerpts are labelled. Discarding a plan
leaves the deck revision unchanged. Structured Core failures now show their
actual message, such as routing, stale-context or unavailable-preview errors.

Challenge reads claim context from the session's frozen revision, including
when the Workspace head later changes. Relations remain user judgment. Reviewed
links participate in the usual provider/privacy/context/citation boundaries.


## Claim/excerpt relation suggestions (2026-10-03)

Each linked excerpt in Purpose offers Suggest relation for an exact quote from
a selected text object. The disclosure says that the selected decision provider
reviews that quote/excerpt when privacy permits. Results show relation or
abstention, provider/model, latency and uncalibrated confidence. Provisional
thresholds do not establish accuracy. Requesting keeps the manual relation;
Use suggested relation changes only the draft and clears review acknowledgment.
The user can override the relation, review the source and Save reviewed claim.
Changed selection/quote/excerpt identity hides an inapplicable prior suggestion.
Stale source/revision/privacy and malformed output fail without semantic writes.


## Presentation narrative editor (2026-10-03)

Narrative in Slide studio holds objective, target audience, desired decision or
action, central thesis, narrative arc and constraints. Switching panels preserves
drafts. A review checkbox enables Save reviewed narrative; text changes clear
acknowledgment. Save binds to the current deck revision without altering slides.
Inherited narrative after an edit requires review; undo selects that revision's
intent. Clear narrative draft affects only the draft; reviewed blank save clears
intent for the revision. Reload saved narrative restores the last saved/inherited
record and rejects overwriting an unseen concurrent save through a record token.

Copilot proposals display Narrative intent used, its captured fields, revision
review state and shortening/history notices. Intent describes the author's goals;
it is never cited as source evidence. Challenge uses its frozen deck revision.


## Deck semantic review (2026-10-03)

Deck review in Slide studio browses 20 native slides per page with title, purpose
review state and recorded claim coverage. Show attention items on this page filters
only that page; Next/Previous review page reaches the rest of the deck. Refresh or
returning to the panel reloads current semantic state. Review slide N opens that
exact slide in Purpose for existing manual/typed purpose and claim/evidence review.
Browsing/filtering/navigation never saves semantic labels or changes the deck.

Counts are explicitly page-scoped and limited to claims the user recorded. Slides
with no recorded claims are labelled neutrally. Missing/inherited/unclear purpose,
stale claims/sources, conflicting evidence and missing supporting links are distinct
attention reasons. Incomplete native text/history coverage stays visible. An edit
marks inherited purpose and claims for review; undo selects that revision's labels.


## Narrative suggestions from the deck (2026-10-03)

Narrative offers an analysis instruction and a contiguous slide range (up to 40).
Suggest narrative from deck sends the draft intent, bounded verified native text/
notes and permitted grounding to the selected reasoning provider. The review shows
proposed intent, slide findings, provider/model, omitted slides and shortened
excerpts; visuals are explicitly not analyzed. Requesting leaves the draft intact.
Discard dismisses the proposal. Use suggested narrative copies fields into the
draft and clears acknowledgment; Save reviewed narrative is a separate action.
Changing draft/range/instruction clears the old review. Panel navigation preserves
the draft and review; revision changes reset them. Finding navigation opens the
exact slide's existing Purpose controls. Suggested roles and takeaways are
unconfirmed and are never saved as slide labels by this flow.


## Slide takeaway review (2026-10-03)

Purpose now includes a takeaway editor for the message the audience should retain.
Manual drafting, Clear draft and Reload saved text are available. A narrative
finding opens the exact slide with an unconfirmed proposal; Use finding as takeaway
draft is separate from navigation, correction, acknowledgment and Save reviewed
takeaway. Saving records author intent without changing slide content, purpose or
evidence. A reviewed blank save stops older text returning. Native edits mark
inherited text for review; undo selects the prior revision's text. Deck review
shows takeaways and inherited attention; missing takeaways are neutrally labelled.
Concurrent saves require reload and never silently overwrite unseen text.


## Captured takeaway intent in Copilot review (2026-10-03)

Copilot review includes Slide takeaways used when the selected revision/range has
reviewed intent. It lists slide numbers and captured text with reviewed or inherited
status. Shortened text and incomplete selection/history are visible. This section
is separate from claim grounding: takeaways do not establish factual support. Later
takeaway saves do not update a prepared proposal. Challenge uses takeaways from its
frozen deck revision for question preparation and answer evaluation.


## Browse and review native layouts (2026-10-03)

Slide actions & layout offers Browse native layouts. The dialog lists this deck's
master/layout names, including unused layouts, with usage and placeholder counts.
Choose a layout and Preview native layout to render the staged deck. Applying does
not add/remove slide objects or remap placeholders; inherited styling/backgrounds
can differ. Review the displayed slide and Save reviewed native layout to commit
exact preview bytes as one revision. Changing selection clears approval and requires
another preview. Discard restores the current deck and retains its revision. Save
refreshes retrieval; Undo restores the earlier native relationship. The existing
source-slide layout picker remains available. An already-used layout is a no-op.
PowerPoint/export verification remains part of wider fidelity acceptance.


## Insert a slide from a native layout (2026-10-03)

Open Slide actions & layout and choose Insert from native layout. Select an existing
layout, including unused layouts, then draft its named text placeholders and notes.
Each line becomes a paragraph with the deck's inherited styling. Layouts with
unsupported or ambiguous text geometry are disabled. Review the rendered new slide
and notes before Save reviewed native slide. Changing layout resets slot drafts;
editing any draft clears approval and requires a fresh preview. Discard restores the
current deck. Saving selects the inserted slide, refreshes retrieval and records one
revision; Undo restores the prior package. The text slots become native editable
objects. This workflow supports text placeholders; other placeholder kinds use
future authoring flows. Template-based insertion and applying a layout to existing
content remain separate available actions.


## Create and edit native tables (2026-10-03)

Choose Native tables in Slide actions & layout. Insert new table exposes row/column
counts, header styling, position/size in inches and an accessible cell grid. Each
cell line is a paragraph. Selecting an existing supported table loads its current
cells; editing keeps its dimensions and native styles. Unsupported tables are
read-only and show a reason. Wider draft grids scroll horizontally. Preview native
table renders the staged result; review cells, placement and text fit before Save
reviewed native table. Changing any draft clears approval. Discard preserves the
current deck. Saving refreshes retrieval and records one revision. Undoing a cell
edit restores the inserted table; undoing insertion restores the original deck.
The current picker includes at most 20 direct tables; merged/complex tables and
structural row/column changes need later workflows. Creation supports 12 rows and
8 columns with 500 characters/10 paragraphs per cell and 10000 total characters.


## Insert a native chart (2026-10-03)

Choose Insert native chart in Slide actions & layout. Select column, bar, line or
pie; draft title, categories, series names and values; choose placement/size in
inches. The data grid scrolls horizontally. Pie mode keeps one series and requires
nonnegative values with a positive total. Preview native chart renders the staged
package. Review data, labels and placement, then Save reviewed native chart. Any
draft change clears approval; discard preserves the current deck. Saving refreshes
retrieval and records one revision; undo restores the complete prior deck. The
export contains an editable native chart and embedded data workbook. Existing
chart editing and additional chart types need later workflows. Pie plot spacing
still differs between preview and PowerPoint; broad chart fidelity remains open.


## Edit existing native chart data (2026-10-03)

Native charts replaces the insertion-only action in Slide actions & layout.
Chart action offers Insert new chart and current direct charts. Choosing a supported
chart loads its cached title, category labels, series names and values. Type and
category/series counts stay locked; placement fields are hidden because data edits
preserve geometry. Plain uniformly styled titles can change; mixed/complex titles
stay locked. Unsupported charts show a read-only reason. Edits preserve styles,
axes, labels, placement and notes and use a new embedded literal-data workbook;
original chart/workbook parts remain intact. Preview unchanged data reports a no-op.
Review the staged image before Save reviewed native chart. Any draft/selection
change clears approval; discard preserves the deck. Save refreshes retrieval and
records one revision; undo data editing restores the prior chart, and a separate
undo can remove insertion. The current picker includes at most 20 direct charts;
structural/type/placement editing and additional chart types need later workflows.


## Move or resize native charts and tables (2026-10-03)

Supported native charts and tables now appear as editable in Object to edit and
the selection canvas. Use position/size fields, then Review object layout. Preview
all changes renders the staged package; acknowledge review before Save reviewed
changes. Cancel restores the current deck. Saving refreshes retrieval and records
one revision; undo restores the prior geometry. Table resize scales row heights
and column widths together while preserving cells/styles. Charts retain their data
and styles. Canvas drag and shared alignment/distribution use the same reviewed
transform path. Grouped/rotated/extended frames or mismatched table grids remain
read-only. Delete/duplicate/layering need separate frame workflows.


## Native chart/table layers and deletion (2026-10-03)

Supported direct native charts and tables now support object layering and confirmed
object deletion in the Presentation Workspace. Deletion removes only the selected
frame from its slide; chart/workbook parts and relationships remain intact so other
frames can keep using them. Layering changes only the native slide tree order.
Both use existing current-head/stale-target guards, retrieval refresh and undo.
Duplication remains disabled in the GUI and explicitly rejected by both Core API
and writer because the shape/picture identity copier is not a graphicFrame copier.

Dependencies considered before edits: native frame selection already supports
geometry, but delete eligibility is also consumed by layering, duplicate controls
and object response validation. All those consumers were traced and adjusted.
Placeholder, connector and animation dependencies keep deletion/layering read-only.
Connector references inside groups are checked, and all timing spid attributes are
checked, including chart build references without spTgt nodes. Existing narrow
geometry eligibility remains required. No new IPC method, schema or migration.
Package parts are retained deliberately; no orphan cleanup is attempted.

Focused acceptance: 20 tests passed in 7.96 seconds in
`.local/graphic-actions-focused-20261003.log`, including native chart/table
layer/delete/undo, unchanged package parts and contents, shared-chart isolation,
connector/group/placeholder/timing/build guards and duplicate rejection.
PowerPoint opened layered and deleted chart/table fixtures read-only, verified
native data and selected-frame removal, retained the independent chart on slide 2,
and left input hashes unchanged. Evidence: `.local/graphic-actions-office/`
`check.py`, `check.log`, `result.json`, PPTX files and exported PNGs. All four PNGs
were visually inspected. The table-layer fixture deliberately places the table
behind overlapping text; this demonstrates stacking, not final authored layout.
The synthetic shared-chart case has Core package/data proof only; its earlier
Office baseline incompatibility is not presented as Office acceptance.

Electron acceptance passed 60 workflows in
`.local/graphic-actions-ui-final-20261003.log`, including chart/table layer changes,
confirmation cancellation, deletion, duplicate gating and undo. Confirmation
screenshots `workspace-native-table-delete-review.png` and
`workspace-native-chart-delete-review.png` in `.local/ui-validation/` were inspected.
The initial GUI attempts caught test locator/selection errors; after correcting
those test harness errors, the complete rerun passed.

Final `pnpm check` passed formatting, lint, type checking, 121 desktop tests and
747 Core tests in 136.00 seconds: `.local/graphic-actions-check-final-20261003.log`.
Earlier check attempts caught test harness lint/format issues; the final check ran
after the timing-build and shared-chart tests were added. `git diff --check` passed.

Next priorities remain native chart/table duplication and broader structural
editing, then corpus fidelity and live integration acceptance. Fast-decision live
calibration/latency and actual Sign in with ChatGPT acceptance remain open. Signing
and clean Windows validation remain accepted tech debt. Dirty work was preserved;
no account/model calls, downloads, commits, pushes, packaging or releases occurred.


## Independent native chart/table duplication (2026-10-03)

Supported direct native chart/table objects now expose Duplicate object in the
Objects inspector. The existing action creates one immutable revision, selects
the copy, refreshes retrieval and supports exact-byte undo. Copies receive fresh
native object IDs and unique names, retain size/content/formatting, and use the
existing bounded 0.25-inch (18-point) placement offset. Tables copy their own native
frame/grid/cells. Charts copy an independent package graph: chart XML, embedded
workbook bytes, chart styles/colors, internal images and theme overrides, with
rewritten relationships and content types. Source chart/workbook parts, other
slides and notes remain untouched. Workbooks are copied as opaque bytes rather
than opened, evaluated or regenerated. Chart duplication does not require the
narrower chart data editor's category/type bounds.

Dependency reasoning preceded edits: shape/picture duplication used nvSpPr/nvPicPr
and spPr transforms; graphicFrame requires nvGraphicFramePr and p:xfrm. A shared
chart relationship would make direct Office edits affect both copies, so charts
must get independent parts before the new frame is written. Graph traversal
retains relationship IDs inside each copied part, rewrites targets, handles shared
nodes/cycles once, limits traversal to 64 parts and avoids collisions. External,
unknown, missing or extended chart dependencies fail before revision commit.
Geometry/deletion eligibility still excludes placeholders, connector/animation
references and unsupported/grouped frames. Existing stale geometry/head, package
limits, staging, native transaction, retrieval refresh and undo paths are reused.
No IPC method, provider operation, database schema or migration was added.

Focused acceptance passed 25 tests in 12.00 seconds:
`.local/graphic-duplication-focused-final-20261003.log`. New cases cover native
chart/table identity, order, size/content, source-part preservation, literal
workbook copy, independent subsequent chart editing, undo, external/extension
rejection and style/image graph target isolation. Final desktop acceptance passed
121 tests using two workers in `.local/graphic-duplication-desktop-final-20261003.log`.
Formatting, lint and type checking passed in separate final format/lint/types logs.

PowerPoint evidence: `.local/graphic-duplication-office/check.py`, `check.log`,
`result.json`, duplicated PPTX fixtures and native exported PNGs. Office opened both
fixtures read-only, found distinct native IDs/names and matching data/formatting,
verified the 18-point placement offset, and independently edited the copy's chart
title/table cell in memory while the original and other slide stayed unchanged.
No save was performed, hashes stayed unchanged, and the owned Office instance was
closed. Both PNGs were inspected; deliberate overlapping copies demonstrate native
independence and offset, not a publication-ready composed slide.

The initial concurrent acceptance attempt failed from host worker/allocation
exhaustion and a GUI narrative timeout before this feature. Its handles were
verified terminal. Validation was rerun with bounded desktop workers and a separate
GUI run; no unrelated process was stopped. The first Office attempt caught a test
expectation of 12 points instead of the existing 18-point offset, then the corrected
fixture check passed.

Full Core acceptance passed 752 tests in 199.10 seconds:
`.local/graphic-duplication-core-final-20261003.log`. The suite exercised duplication before the final imported
chart clone naming refinement, which was added to avoid the authored-chart preview adapter
convention; all 25 focused checks passed again with an explicit naming assertion,
and the changed module passed Ruff and mypy. Office was rerun successfully
after the refinement. Authored charts retain their naming
convention. The naming refinement changes neither native chart bytes nor contents.

Final Electron acceptance passed 62 workflows:
`.local/graphic-duplication-ui-final-20261003.log`. Both native duplication flows
verified creation of a second editable object, selected-copy refresh and exact
revision undo, followed by the prior layer/delete workflows. Screenshots
`workspace-native-chart-duplicated.png` and `workspace-native-table-duplicated.png`
were inspected. Both final acceptance process handles are terminal. Diff checks
passed, and all unrelated dirty work remains preserved.

Remaining priorities: broader structural editing including whole-slide duplication
with chart/table dependencies, corpus fidelity and live integration acceptance.
Current whole-slide duplication rejects chart relationships even when a deleted
frame left an unused relationship; this is the next verified structural gap.
Fast-decision live calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted tech debt.
Dirty work is preserved; no account/model calls, downloads, commits, pushes,
packaging or releases occurred. The production-readiness goal remains active.


## Whole native chart/table slide duplication (2026-10-03)

Whole-slide duplication now accepts native chart relationships and creates
independent chart/workbook/style/image/theme parts for the copied slide. Native
tables already copy as slide XML and are now covered by direct, reviewed-plan and
GUI acceptance. The copied slide retains its exact source XML bytes, native IDs,
geometry, names, content, notes and internal relationship IDs. Existing slides,
chart parts, embedded workbooks and notes remain unchanged. One revision is added,
retrieval refresh and selection use the existing workflow, and undo restores the
original bytes. No new IPC operation, provider schema or database migration.

Dependencies considered before editing: simply accepting /chart relationships
would make the copy share mutable chart/workbook parts with its source. The chart
graph copier now accepts copied slide relationship/content-type roots, preserves
relationship IDs and shares a clone map across charts. Multiple references to one
chart, different relationships to that same chart, and separate charts sharing a
workbook retain their internal sharing inside the copied slide while separating
all active chart dependencies from the original. Graph copying still rejects
external, missing, extended or unknown active chart dependencies before commit;
chart references outside supported native frame structures are rejected. Unused
internal chart relationships left by object deletion are preserved without cloning
inactive charts, so copying a slide after deleting its chart now works. Notes
back-links and content-type overrides are updated together with presentation order.
The archive remains subject to existing source/package/XML/object/slide limits.

Focused acceptance passed 15 tests in 5.59 seconds:
`.local/graphic-slide-copy-focused-20261003.log`. This includes the previous object
duplication tests plus new chart/table direct and staged-review slide copying,
exact slide/notes bytes, source-package preservation, independent subsequent chart
editing and undo, unsupported dependency rejection, duplication after chart
deletion and three intentional chart/workbook sharing patterns. Format/lint/types
passed in `.local/graphic-slide-copy-{format,lint,types}-20261003.log`; desktop
acceptance passed 121 tests with two workers in the corresponding desktop log.
Validation runs are separated to avoid the host allocation exhaustion observed in
the previous continuation; no unrelated processes were stopped.

PowerPoint evidence: `.local/graphic-slide-copy-office/check.py`, `check.log`,
`result.json`, copied PPTX fixtures and exported PNGs. Both decks opened read-only
with three slides; source/copy native geometry, IDs, names, data and speaker notes
matched. Original and copied slide exports were byte-identical native PNGs. Editing
the copied chart title/table cell in memory left the original and remaining chart
slide unchanged. Files were never saved, hashes remained unchanged and the owned
Office instance was closed. Copy and independently edited PNGs were inspected.
The synthetic shared-dependency cases have Core package/data proof; the Office
acceptance above uses independent native fixture decks.

Full Core acceptance passed 762 tests in 194.51 seconds:
`.local/graphic-slide-copy-core-20261003.log`. All static and desktop checks used
the final source, after shared-workbook and native frame-reference guards were added.

Final Electron acceptance passed 64 workflows:
`.local/graphic-slide-copy-ui-final-20261003.log`. Whole native chart/table slides
were copied from slide 1 to slide 2, retained editable objects and rendered
previews, refreshed retrieval, and undid back to the original slide/revision.
Screenshots `workspace-native-chart-slide-duplicated.png` and
`workspace-native-table-slide-duplicated.png` were inspected. The initial GUI
attempt caught a test-only extra Previous navigation after undo had already
restored slide 1; removing that unnecessary step yielded a complete passing run.
Final lint and format checks passed again after that test adjustment. All acceptance
process handles are terminal and `git diff --check` passed.

Remaining priorities: canvas resize handles and object copy/paste, substantial
table/chart editing, broader corpus fidelity and live integration acceptance.
The UX minimum interactions explicitly require resize handles and copy/paste;
current SlideObjectCanvas renders translation/selection only, with no resize
callback or clipboard path. These are verified missing workflows for the next
continuation.
Fast-decision live calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted tech debt.
Dirty work remains preserved. No account/model calls, downloads, commits, pushes,
packaging or releases occurred. The production-readiness goal remains active.

## Canvas interaction continuation - reviewed canvas resize handles

The slide canvas now has eight accessible edge/corner resize handles for supported
native objects and selections of up to 20 objects. Pointer dragging shows geometry
ghosts; releasing drafts the existing native geometry review. Shift on corners
preserves group proportions, and optional 0.1-inch snapping applies to displacement.
Arrow keys on a focused handle draft a resize. Escape, canceled/lost pointer capture,
slide/revision changes and leaving selection mode clear the drag without saving.
Review shows before/after position and width/height, requires a rendered preview and
acknowledgment, saves one revision, refreshes retrieval and supports existing undo.
Shapes, pictures, native charts and tables use the same supported geometry guards.

Dependencies considered before editing: canvas pixels must map through the rendered
image into integer slide EMUs, including selection-mode margins and image resize.
Group scaling anchors the opposite edge, scales relative placement and sizes, rounds
endpoints, clamps to slide bounds and keeps each member at least one point unless
already smaller. Existing source geometry is not mutated. Only editable top-level
objects are exposed; native table row/column scaling and chart preservation remain
in the existing reviewed transform writer. No backend, IPC or database change.
Handles sit outside selected bounds with 20 pixels of image margin in selection
mode; the first GUI attempt caught centered handles intercepting thin-label clicks.
That actual interaction defect was fixed before the passing rerun. A later failure
was a test revision-number expectation after the newly added save/undo workflow.

Final acceptance passed 134 desktop tests in 3.51 seconds and all 67 Electron GUI
workflows, including group/corner/keyboard resizing, Escape cancellation, preview,
required acknowledgment, one-revision save and undo, plus native chart/table resize
and existing downstream editing workflows. Evidence:
`.local/canvas-resize-desktop-final-20261003.log` and
`.local/canvas-resize-ui-final-20261003.log`. Focused Core geometry/duplication/
transaction acceptance passed 55 tests in 11.39 seconds:
`.local/canvas-resize-native-core-20261003.log`. Final lint, format and types passed
in `.local/canvas-resize-{lint,format,types}-final-20261003.log`; both TypeScript
projects and 144 Core modules type-check. Group ghost/review and native chart/table
resize screenshots under `.local/ui-validation/` were inspected. The review now
explicitly lists dimensions as well as positions. All check handles are terminal,
and `git diff --check` passes.
The earlier full 762-test Core and native PowerPoint evidence remain historical;
this continuation changes the frontend only and does not claim a new full Core or
PowerPoint acceptance run. Validation is serial with a bounded Node heap because
host allocation exhaustion interrupted earlier attempts; unrelated processes remain
untouched.

Remaining priorities: object copy/paste, substantial table/chart editing, broader
corpus fidelity and live integration acceptance. Fast-decision live calibration and
latency plus actual Sign in with ChatGPT acceptance remain open. Signing and clean
Windows validation remain accepted tech debt. Dirty work is preserved; no account or
model calls, downloads, commits, pushes, packaging or releases occurred. The
production-readiness goal remains active.

## Object clipboard continuation - immutable native object clipboard

Copy objects and Paste objects now expose a presentation clipboard in the slide
canvas. Ctrl/Cmd+C and Ctrl/Cmd+V work from the focused canvas without intercepting
text inputs. Copy records the selected native objects, source presentation, slide
and immutable revision; it performs no edit. The clipboard survives navigation and
presentation changes within the current project, and clears when changing projects.
Pasting drafts a native edit plan into the current destination slide and requires
preview plus acknowledgment before saving one revision. Cancel/discard changes no
revision; save refreshes retrieval and supports existing undo. This is an in-app
presentation clipboard, not OS clipboard interoperability or cut/move.

Dependencies considered before editing: simply invoking Duplicate would read the
latest content instead of the content at Copy, and would not cross slides. The new
manual paste_objects transaction reads the verified pinned source revision in the
same project and rewrites a verified current destination package. It copies 1–20
eligible top-level objects in source layer order with fresh IDs/names, preserving
physical sizes and group spacing with a bounded 0.25-inch offset. Selections larger
than the destination are rejected. Native images get remapped PNG/JPEG dependencies
with sharing retained within a batch; crop and external hyperlinks are preserved
without opening them. Native chart graphs get independent chart/workbook/style/
image/theme parts, preserving internal sharing inside the batch while separating
source dependencies. Tables copy native frames/cells; unavailable custom table
styles are rejected. Text/theme colors use the destination theme as stated in review.
Unsupported or missing dependencies, linked chart workbooks and extended chart
dependencies fail before commit. Package,
XML, expanded-size and object limits remain enforced. Existing slides, objects,
notes and parts are validated after writing. No database migration or new public IPC;
paste uses prepare/open/apply/reject edit plans and the existing transaction writer.
Created-object arrays are returned and recorded in transaction metadata.

GUI acceptance exposed three concrete defects: Paste was enabled while navigation
had cleared the destination ID, the shared dialog tried alignment validation before
paste preparation, and the normal revision-change effect cleared the new selection.
Paste now waits for the authoritative destination inventory, its review bypasses
alignment selection, and pasted objects are selected only after the exact committed
revision and refreshed inventory arrive. Review displays structured Core errors.
Missing chart relationship roots and dependency collisions now fail with structured
errors before any commit. Tests also verify that two pasted chart frames sharing one
source chart keep a single independent chart/workbook graph inside the pasted batch.

Validation on the frozen source: all 784 collected Core tests passed in four serial
fresh-process batches (238 + 178 + 204 + 164), with the complete collection and batch
manifest in `.local/object-paste-core-batches/`. An earlier single-process run failed
two existing tests with logged MEMORY_ALLOCATION_FAILED; it is not a passing receipt.
The serial run includes every collected test without skips or omissions. Focused
clipboard/duplication/diagnostics coverage passed 37 tests. All 134 desktop tests,
ESLint/Ruff, formatting, both TypeScript projects and mypy (145 source files) passed.
Request-boundary diagnostics emit only fixed memory/I/O/unexpected cause codes,
without exception content or changes to public error responses.

Native PowerPoint acceptance passed for charts and tables pasted between presentations:
editable native content, independent in-memory edits, exact size/bounded offset,
destination notes and unchanged source/destination file hashes. Exports were inspected.
Evidence: `.local/object-paste-office/result.json`, `check.log` and four exported PNGs.
This fixture acceptance does not establish fidelity for every imported presentation.
The final GUI sweep passed all 70 workflows on the frozen source, including grouped
copy/paste across slides, cancellation, rendered review and acknowledgment, exact
revision save, pasted selection, native chart/table keyboard paste and undo.
Evidence: `.local/object-paste-ui-final-20261003.log` and inspected screenshots in
`.local/ui-validation/`: `workspace-object-paste-review.png`,
`workspace-native-table-clipboard-review.png` and
`workspace-native-chart-clipboard-review.png`. An initial final-run attempt timed out
at the first screenshot after fonts loaded, before clipboard tests; the complete
retry passed. Code/test source hashes in `.local/object-paste-source-freeze.json`
were verified unchanged for all 303 files; receipt:
`.local/object-paste-source-freeze-check.json`. Final diff whitespace check passed.
All test/acceptance processes launched for this continuation reached terminal state.
GUI/provider workflow tests use deterministic providers; this is not live account,
model, speech or integration acceptance.

Remaining priorities: deeper table/chart authoring, further clipboard interoperability
and common keyboard workflows, broader corpus fidelity and live integration acceptance.
Fast-decision live calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted tech debt. Dirty
work is preserved; no account/model calls, downloads, commits, pushes, packaging or
releases occurred. The production-readiness goal remains active.

## Native table structure continuation - reviewed native table structure

Native tables now supports inserting rows/columns before or after the selection,
and removing selected rows/columns, in the same editor as cell text. Focusing a
cell selects its row and column; labeled selectors also control the actions.
The draft stays local until rendered preview, acknowledgment and one-revision
save. Structural edits invalidate review; discard and existing undo remain wired.
Limits remain 1–12 rows, 1–8 columns, 500 characters/10 paragraphs per cell and
10000 total characters. The last row/column cannot be removed in the GUI.

Dependencies considered before editing: changing matrix dimensions through the
cell-only operation would either fail or shift text into the wrong native cells.
A manual reshape_table transaction instead carries explicit original row/column
indices, with null for inserted rows/columns. Retained indices must be unique,
in bounds and in original order. The verified native table fingerprint and current
revision guard still apply. Retained native cells are cloned with their cell and
text styles; unchanged text bodies are preserved. New cells inherit the
next retained row/column, or the previous one at the end (body/first-column fallback
when no original rows/columns remain). Rows and columns redistribute the existing
height/width totals proportionally, with deterministic integer rounding and native
dimension limits. Outer transform, object identity, notes, other slides/objects and
unrelated package parts stay unchanged and are validated. The cell-only operation
retains its original fixed-dimension contract. No public IPC, provider schema or
database migration is added; the reviewed plan lane dispatches reshape_table.

Imported structures with unknown row/grid attributes, nonpositive/oversized native
dimensions, merged/linked/mixed-run/extended cells remain locked to the supported
editing scope. Supported plain text cells can still be edited when structural
editing is unavailable. Arbitrary row/column reordering, merge/split, per-cell rich
formatting and table pagination remain open.

Validation: 19 new structural tests passed; all 803 collected Core tests passed in
four serial fresh-process batches (251 + 184 + 204 + 164), without skips/omissions.
All 134 desktop tests passed. Tests cover staged save/retrieval/undo, exact part
preservation, retained/inherited native styles, dimensions, no-op and mapping,
stale-target, foreign-target and malformed-structure rejection. An initial no-op
fixture omitted the required plan summary; it was corrected, and rejection tests
now assert their specific error codes. Full collection/batch receipt:
`.local/table-structure-core-batches/manifest.json`; focused and desktop logs:
`.local/table-structure-core-focused.log`, `.local/table-structure-desktop.log`.

Native PowerPoint opened the reviewed 3x4 fixture, verified every cell, original
outer geometry, inherited fills/font colors and independent in-memory editing.
Read-only exports were inspected; both PPTX file hashes stayed unchanged.
Evidence: `.local/table-structure-office/result.json`, `check.log`,
`table-structure.png` and `table-structure-edited.png`. This is fixture acceptance,
not proof for all imported presentations. Source/test hashes are frozen in
`.local/table-structure-source-freeze.json` (305 files).
ESLint/Ruff, formatting, both TypeScript projects and mypy (146 source files)
passed. All 64 focused table/geometry checks passed on the final source. The final
Electron sweep passed all 71 workflows, including insertion before/after, middle
deletion, retained header/body text, rendered review, structural review invalidation,
saved-cell discovery and undo. Screenshot inspection exposed insufficient assertions
in an earlier green sweep: ambiguous numeric Playwright selections matched option
labels instead of intended values. Explicit value selections and intermediate
Metric/Current/Measured preservation assertions now verify the intended sequence.
The initial missing Risk-row fixture was also corrected. Focused GUI traces:
`.local/table-structure-debug/debug-exact.log` and inspected `table-controls.png`.
Final evidence: `.local/table-structure-ui-exact.log`,
`.local/ui-validation/workspace-native-table-structure-review.png`,
`.local/table-structure-core-focused-final.log`, `.local/table-structure-lint-final.log`,
`.local/table-structure-format-final.log` and `.local/table-structure-types-final.log`.
All 305 frozen source/test hashes were verified unchanged after GUI completion;
`.local/table-structure-source-freeze-check.json`. Final diff whitespace check passed.
All acceptance processes from this continuation reached terminal state. GUI/provider
tests use deterministic providers; live account, model, speech and human integration
acceptance remain open.

Next priorities: structural chart categories/series and richer table/chart workflows,
common keyboard operations, broader corpus fidelity and live integration acceptance.
Fast-decision live calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted debt. Dirty work
is preserved; no account/model calls, downloads, commits, pushes, packaging or
releases occurred. The production-readiness goal remains active.

## Native chart structure continuation - reviewed native chart structure

Native charts now offers insertion before/after and removal for categories and
series on supported existing column, bar, line and pie charts. Labeled selectors
and focused data cells select the target. New categories/series require names;
new values start at zero. Limits remain 24 categories and 6 series, or one series
for pie; the final item cannot be removed. Structural draft changes invalidate
review. Preview, acknowledgment, one-revision save, retrieval refresh, discard and
undo use the existing reviewed native edit workflow.

Dependencies considered before editing: changing cache counts alone leaves stale
workbook ranges, series identities, point overrides, data-label indexes and legend
entries. The manual reshape_chart transaction carries explicit category/series
source mappings (null means inserted), rejects duplicates/out-of-bounds/reordering,
and retains current revision/fingerprint guards. Retained series keep native IDs,
series formatting and mapped point/data-label overrides. Removed item overrides
are removed; retained cache-point format attributes follow their categories. New
series get new IDs and app chart colors; custom point/label/trendline/error-bar
settings from another series are not copied. Plot-level labels and custom legend
entries are remapped. The native type, axes/layout, outer geometry, identity, title
styles, notes and other slides/objects stay intact. The existing writer clones the
chart/relationships and writes a literal embedded workbook with updated ranges;
original parts remain unchanged for other references. Post-write inventory and
chart/workbook data validation still apply. The fixed-count replace_chart_data
contract remains unchanged. No public IPC, provider schema or database migration.

Linked/extended/unsupported charts remain read-only. Reordered native series,
malformed point/label/legend identities and custom legends combined with trendlines
stay outside structural editing, with explicit reasons; supported labels/values
can still be edited. Arbitrary item reordering, combo/stacked/other chart types,
axes/legend authoring and native workbook editing remain open.

Validation: 18 new structural tests passed across all four types and shared/nonshared
chart dependencies. All 821 collected Core tests passed in four fresh-process serial
batches (173 + 245 + 199 + 204), without skips/omissions; 134 desktop tests passed.
Tests verify reviewed save/reindex/undo, exact unchanged original package parts,
retained series formatting/IDs, independent literal workbooks, point/label/legend
index mapping, cache number-format retention, and specific atomic rejection codes.
Receipts: `.local/chart-structure-core-batches/manifest.json`,
`.local/chart-structure-core-focused.log`, `.local/chart-structure-existing.log`
and `.local/chart-structure-desktop.log`.

Native PowerPoint acceptance passed for ordinary imported column/bar/line/pie
fixtures: four categories, two series (one for pie), exact names/values, unchanged
outer geometry/notes/retained fill and independent native title edits. Other slide
charts and both file hashes remained unchanged. Exports were inspected. Evidence:
`.local/chart-structure-office/result.json`, `check.log` and eight exported PNGs.
The synthetic shared-chart-part source failed PowerPoint open although its edited
result opened. `check-shared-source.log` preserves that evidence; shared-part
isolation is Core proof, not Office compatibility proof. Broad import/pixel fidelity
is not established by these fixtures. Source/test hashes are recorded in
`.local/chart-structure-source-freeze.json` (307 files).
Final ESLint/Ruff, formatting, both TypeScript projects and mypy (147 source files)
passed. The full Electron sweep passed all 72 workflows, including category/series
insertion before/after, middle deletion, retained labels/values, structural review
invalidation, save, persisted discovery and undo. The reviewed screenshot was
inspected for Baseline/Forecast/Target and Revenue/Margin placement. The first run
stopped on a test locator that named Category 1 label instead of the existing
Category 1 field; exact labels were corrected and the full retry passed. Evidence:
`.local/chart-structure-ui-final.log`,
`.local/ui-validation/workspace-native-chart-structure-review.png`,
`.local/chart-structure-lint-final.log`, `.local/chart-structure-format-final.log`
and `.local/chart-structure-types-final.log`. Only GUI-script whitespace was formatted
at the end; application/Core sources stayed unchanged during acceptance. The final
307 source/test hashes match `.local/chart-structure-source-freeze-check.json`.
Final diff whitespace check passed. Every acceptance process launched for this
continuation reached terminal state. GUI/provider checks use deterministic providers;
live model/account/speech/human acceptance remains open.

Next priorities: remaining substantial GUI workflows, richer chart/table authoring,
common keyboard actions, broader corpus fidelity and live integration acceptance.
Live fast-decision calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted debt. Dirty work
is preserved; no account/model calls, downloads, commits, pushes, packaging or
releases occurred. The production-readiness goal remains active.
