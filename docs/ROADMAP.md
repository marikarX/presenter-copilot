# Roadmap

## Phase 0 — Validate the wedge

Goal: prove that the product is more useful than generic rehearsal tools or a normal LLM chat.

Tasks:

- collect 5–10 real high-stakes decks from willing testers;
- define 3–5 representative audience personas;
- test whether generated objections are materially relevant;
- measure whether coached answers become shorter and stronger;
- prototype the top-center HUD geometry on common laptop displays;
- validate whether local ASR latency is fast enough for live use.

Exit criteria:

- users report at least several non-obvious useful questions per deck;
- HUD cues can appear quickly enough to affect an answer without disrupting speech;
- users prefer cue scaffolds to full generated prose.

## Phase 1 — Local rehearsal prototype

Build:

- desktop shell;
- PDF/PPT ingestion;
- local document index;
- local microphone capture and ASR;
- session transcript;
- slide/context tracking;
- simple audience personas;
- Q&A rehearsal;
- basic debrief.

No enterprise features yet.

## Phase 2 — Live HUD prototype

Build:

- always-on-top top-center cue surface;
- question segmentation;
- retrieval-first response path;
- progressive cue updates;
- source/slide references;
- keyboard shortcuts for hide/expand/next;
- latency instrumentation.

Critical metric: question-to-useful-cue latency.

## Phase 3 — Mobile companion

Treat mobile first as a companion to the desktop presentation engine rather than a full replacement.

Build:

- paired phone/tablet connection to the desktop app;
- private cue-card display on a phone placed near or below the presentation display;
- presenter remote controls for next/previous cue, hide, expand, and mark question;
- timer, current slide, next talking point, and source reference view;
- rehearsal recording/capture from the phone when a laptop is inconvenient;
- secure local-network mode so companion traffic does not require a cloud relay;
- optional haptic cues for timing or transitions.

Later mobile expansion, only after the companion workflow proves useful:

- standalone presentation rehearsal from a phone/tablet;
- import/share a deck into the mobile app;
- on-device ASR and lightweight retrieval where hardware permits;
- mobile camera-based delivery coaching;
- Apple Watch/Wear OS cue or timer surfaces if there is demonstrated demand.

Why this matters:

- the phone can act as a second private screen while the laptop is screen-sharing;
- a presenter can keep cues physically closer to the audience/camera sightline;
- mobile rehearsal increases usage frequency outside the desk setup;
- the companion can become a low-friction entry point without weakening the local-first desktop architecture.

Do not make full cross-platform mobile parity an MVP requirement.

## Phase 4 — Hybrid reasoning

Build:

- provider abstraction;
- local model backend;
- user-supplied API backend;
- optional officially supported agent backend such as Codex app-server where appropriate;
- local router deciding when remote reasoning is justified;
- explicit privacy-mode controls.

## Phase 5 — Closed learning loop

Build:

- remember real questions by presentation/project;
- compare predicted vs. actual objections;
- store best answer versions;
- identify recurring weak points;
- prioritize future rehearsal automatically;
- audience/stakeholder history.

This phase is strategically more important than adding broad presentation-authoring features.

## Phase 5.5 — Presentation Workspace

Goal: keep users inside Presenter Copilot when preparation/rehearsal identifies changes that should be made to the actual presentation.

Strategic boundary:

- build a focused presentation-preparation editor;
- do not pursue general-purpose PowerPoint feature parity;
- treat PowerPoint as an interoperability/export target rather than the required editing environment;
- preserve the frozen MVP's read-only PowerPoint integration until the workspace fidelity model is independently ready.

Implement in gated stages:

1. **PW0 — validate the editing wedge**
   - high-fidelity viewer and AI side chat;
   - observe real deck-preparation sessions;
   - measure which edits cause users to leave Presenter Copilot;
   - prototype rehearsal-to-edit proposals.
2. **PW1 — fidelity foundation**
   - immutable original PPTX snapshot;
   - editable fidelity document model with stable slide/object IDs;
   - opaque preservation for unsupported Office features;
   - no-op PPTX round-trip corpus and export validation.
3. **PW2 — core direct editing**
   - text/notes editing;
   - move/resize/delete/duplicate common objects;
   - slide add/delete/duplicate/reorder;
   - common formatting and image insert/replace/crop (bounded insertion and
     replacement for simple embedded pictures are implemented in the research
     preview);
   - undo/redo, revision checkpoints, PPTX/PDF export.
4. **PW3 — semantic presentation model**
   - presentation narrative;
   - slide purpose and claim/evidence bindings;
   - a typed decision-provider path for bounded slide-purpose and
     claim/evidence triage, gated by a human-labeled evaluation set;
   - current-revision awareness throughout Project Brain and rehearsal.
5. **PW4 — AI side-chat editing**
   - selection-aware commands;
   - typed EditPlan operations;
   - preview/review gates;
   - stale-plan detection;
   - Preserve-My-Voice and source-grounded rewriting.
6. **PW5 — voice editing**
   - reuse local ASR;
   - visible transcription;
   - voice commands route to the same typed edit-planning system.
7. **PW6 — rehearsal-to-edit closed loop**
   - convert strong explanations, unsupported claims, recurring objections, and slide-density findings into reviewable presentation changes;
   - retain links from applied changes back to the originating rehearsal evidence.
8. **PW7 — creation from conversation**
   - voice/text conversation -> objective/audience/narrative -> editable slides;
   - optimize for iterative grounded authoring, not generic one-shot deck generation.
9. **PW8+ — richer native presentation objects/integrations**
   - improve charts, tables, diagrams, themes, image workflows, and external presentation integrations only when usage justifies them.

Critical architectural rule: imported decks use a dual representation — a fidelity document model for render/edit/PPTX export plus a semantic model connected to Project Brain, Speaker Profile, Audience Model, sources, and rehearsal history. Direct edits, AI edits, voice edits, and rehearsal-derived changes converge on one typed edit-transaction layer.

Critical compatibility rule: unsupported imported PPTX content must be preserved whenever possible rather than silently flattened or discarded. Broad AI authoring does not ship before the PPTX fidelity and direct-editing foundations are trustworthy.

Investment gate: proceed beyond viewer/prototype work only if observed preparation sessions show frequent edit-driven context switching and rehearsal regularly creates useful deck-change intent.

See [`docs/PRESENTATION_WORKSPACE/`](PRESENTATION_WORKSPACE/README.md) for the product, UX, architecture, PPTX fidelity, AI-editing, asset, validation, and detailed staged roadmap specifications.

## Phase 6 — Immersive audience simulation

Goal: extend rehearsal from question generation into a socially realistic presentation simulation without coupling the core product to one rendering stack.

Build in stages:

1. **Behavioral desktop simulation**
   - synthetic/role-based audience;
   - participant attention, comprehension, skepticism, support, and patience state;
   - visible reactions, interruptions, and grounded questions;
   - reproducible scenario seeds;
   - post-run audience-state debrief.
2. **Spatial 3D room**
   - participant seating/positioning;
   - foreground interactive participants plus lower-cost background crowd;
   - local GPU quality scaling;
   - renderer failure isolated from rehearsal/session state.
3. **High-fidelity synthetic audience**
   - improved animation, facial behavior, lighting, and lip sync only if behavioral simulation already proves useful.
4. **XR client**
   - headset rendering using the same renderer-independent simulation contract;
   - optional spatial interaction and gaze coaching after privacy review.

Architectural rule: the Audience Simulation Engine owns canonical participant behavior; desktop/3D/XR renderers only visualize typed simulation events.

Safety rule: synthetic audience identities are the default. Photorealistic cloning, face recognition, voice cloning, emotion recognition, and claims that the system predicts exactly how a named person will react are outside the default roadmap.

Investment gate: do not prioritize photorealism or XR until a lightweight behavioral prototype demonstrates measurable value over normal Challenge/Run rehearsal.

See [`docs/IMMERSIVE/`](IMMERSIVE/README.md) for the specification, architecture, privacy/safety requirements, and validation plan.

## Phase 7 — Integrations

Candidates:

- PowerPoint live slide state;
- Keynote;
- Google Slides;
- Teams/Zoom/Webex meeting context where technically and contractually appropriate;
- file/document sources used by enterprise teams.

Presentation Workspace does not make these integrations the authoritative document state. Interoperability should follow validated demand and retain Presenter Copilot's local project/revision model.

Integrations should follow validated user demand, not precede core product quality.

## Phase 8 — Team / enterprise layer

Possible commercial features:

- shared audience persona libraries;
- team presentation knowledge;
- approved messaging/playbooks;
- readiness/certification workflows;
- admin model/provider policy;
- local-only enforcement;
- SSO;
- audit/retention controls;
- analytics on recurring objections and weak answers;
- managed deployment;
- curated immersive scenario libraries after individual simulation value is proven;
- enterprise presentation templates/review policies after the individual Presentation Workspace proves useful.

## Open-source strategy checkpoint

The repository uses MIT for its own code and documentation. Before broad public release, still decide:

- what remains fully open source;
- whether commercial functionality is hosted, enterprise-only, or open-core;
- whether a CLA or DCO is needed as contribution volume grows;
- trademark/public product name;
- provider-integration terms and branding requirements;
- third-party dependency/model notice process.

Do not select the public brand solely because a domain is available. Screen search engines, GitHub, app stores, competitors, domains, and trademarks first.


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
