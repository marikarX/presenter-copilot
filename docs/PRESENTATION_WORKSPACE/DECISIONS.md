# Presentation Workspace Decision Record

These decisions govern the post-MVP Presentation Workspace roadmap. They complement the canonical [`docs/DECISIONS.md`](../DECISIONS.md) without changing frozen MVP decisions such as D-045 (read-only PowerPoint integration for Milestone 6).

## PW-D01 — PowerPoint is an interoperability target, not the required preparation editor

**Status:** Accepted as roadmap direction

After the Presentation Workspace fidelity/editing foundation exists, routine preparation edits should be possible inside Presenter Copilot.

Reason:

Sending a user back to PowerPoint after Presenter Copilot has accumulated presentation context, evidence, speaker style, audience knowledge, and rehearsal history breaks the closed loop and reduces the product to a sidecar.

This does not require PowerPoint feature parity.

## PW-D02 — General-purpose presentation-editor parity is not a goal

**Status:** Accepted

Build enough direct editing to cover high-frequency preparation work. Defer exhaustive Office capabilities such as VBA, arbitrary add-ins, full animation timelines, exhaustive SmartArt editing, every chart subtype, and complete master/theme designer parity.

Reason:

Full parity would consume the product roadmap without strengthening the core presentation-intelligence differentiation.

## PW-D03 — Imported presentations use dual representations

**Status:** Accepted

Maintain:

1. a fidelity document model for render/edit/export/preservation;
2. a semantic presentation model for narrative, claims, evidence, speaker intent, audience relevance, and rehearsal knowledge.

Reason:

A lossy semantic slide abstraction cannot reliably round-trip real PPTX files, while raw OOXML alone cannot support meaningful presentation reasoning.

## PW-D04 — Fidelity model is authoritative for physical slide state

**Status:** Accepted

The semantic model may be refreshed or recomputed, but the fidelity document/revision owns the current slide/object state used for rendering and export.

Reason:

AI interpretation must not silently become the document source of truth.

## PW-D05 — All mutation paths converge on typed edit transactions

**Status:** Accepted

Direct manipulation, keyboard/inspector edits, AI text commands, AI voice commands, and rehearsal-derived proposals must use the same core transaction layer.

AI planners emit typed domain operations; they never edit raw OOXML/package bytes directly.

Reason:

One mutation boundary provides validation, undo, revisioning, stale-plan protection, compatibility checks, and auditable authority.

## PW-D06 — Preserve unsupported PPTX content before normalizing it

**Status:** Accepted

Unknown or unsupported imported features should be retained opaquely when practical. Limited move/resize/delete may be allowed when safe. Conversion to a supported representation is explicit if it can lose native Office behavior.

Reason:

Silent flattening or deletion makes the product unsafe for real enterprise decks.

## PW-D07 — Imported original is immutable

**Status:** Accepted

Every imported deck retains an immutable original snapshot. Editing creates revisions and exports; it never overwrites the only recoverable source.

Reason:

PPTX compatibility work will encounter edge cases. Recovery, comparison, and deterministic debugging require the exact import baseline.

## PW-D08 — Rehearsal findings propose edits; they do not mutate automatically

**Status:** Accepted

Run/Challenge may produce typed findings and edit proposals, but user review remains the authority for presentation mutation.

Reason:

Rehearsal interpretation can be useful without being perfectly reliable, and preserving presenter ownership is consistent with the existing Project Brain model.

## PW-D09 — Presentation sessions bind to immutable revisions

**Status:** Accepted

Run/Challenge/Live sessions reference the concrete presentation revision used when the session starts. Later draft edits do not rewrite historical session meaning or silently alter an active presentation.

Reason:

Reproducible coaching, provenance, and safe live behavior require a stable deck state.

## PW-D10 — AI edits reuse the existing provider/privacy execution boundary

**Status:** Accepted

Remote AI editing receives only bounded, allowed semantic/presentation context through the core-owned provider execution path. PPTX packages, full binary assets, or unrestricted Project Brain content do not leave the machine merely because edit planning is enabled.

Reason:

Presentation editing is not a justification for creating a second weaker remote-data boundary.

## PW-D11 — Voice editing is an input modality over the same planner

**Status:** Accepted

Voice commands use local ASR and then enter the same target-resolution, planning, validation, review, and transaction pipeline as text commands.

Reason:

Separate voice mutation logic would duplicate authority and create inconsistent safety/undo semantics.

## PW-D12 — Broad AI authoring follows fidelity/direct editing

**Status:** Accepted

Do not lead implementation with one-shot deck generation. Establish import/render/no-op round trip, direct editing, revisioning, and semantic mappings first; then add AI/voice editing and creation-from-conversation.

Reason:

A compelling demo that cannot safely preserve/export the user's actual presentation is not a trustworthy high-stakes workflow.

## PW-D13 — Creation-from-conversation optimizes for iterative grounded authoring

**Status:** Accepted as later roadmap direction

When new-deck creation arrives, the primary loop is conversation -> narrative -> editable slides -> rehearsal -> revision, grounded in Project Brain, audience, evidence, and Speaker Profile.

Reason:

Generic one-shot slide generation is commoditized and weaker than the context/rehearsal loop Presenter Copilot can own.

## PW-D14 — Assets are project entities with provenance

**Status:** Accepted

Imported/generated images and diagrams receive project-local identity, source/generation metadata, variants, slide usages, and rights/attribution metadata when known.

Reason:

Assets need reuse, provenance, deterministic revision/export behavior, and safe replacement; anonymous embedded blobs are insufficient.

## PW-D15 — Compatibility is corpus-gated

**Status:** Accepted

PPTX editing claims require a golden corpus, no-op round-trip tests, edited round-trip tests, visual comparison, untouched-content invariants, and real-deck dogfooding.

Reason:

PowerPoint compatibility cannot be established from generated toy files or package validity alone.

## PW-D16 — Bounded semantic decisions use a separate provider contract

**Status:** Partially implemented; evaluation remains a release gate

PW3 uses a fast typed decision model for a review-only slide-purpose
suggestion. Core returns the stable slide ID and current revision; the user
must explicitly confirm or correct a category before it is stored as semantic
metadata. The record is scoped to that exact revision and contains no slide
text or provider response. The model cannot write slide content or bypass the
typed edit-transaction layer. Claim/evidence triage and measured uncertainty
thresholds remain future work.

This capability follows the shared privacy, context-manifest, credential, and
request-budget rules in [D-059](../DECISIONS.md#d-059--typed-decision-models-are-a-separate-bounded-provider-path).
Broader decisions or user-facing automation must pass a human-labeled
evaluation first.

Reason:

Slide classification is a bounded semantic judgment, while AI editing and
rehearsal feedback still require generative reasoning. Keeping those contracts
separate makes the faster path measurable and prevents a decision model from
becoming document-mutation authority.

## PW-D17 — The current slide renderer is experimental, not PowerPoint parity

**Status:** Accepted as a temporary product boundary; release gate remains open

The workspace currently prefers `@aiden0z/pptx-renderer@1.3.0` inside a
separate hidden, sandboxed Electron window; `pptx-glimpse@5.3.1` remains the
compatibility fallback. In a same-corpus comparison on 2026-09-30, the
candidate rendered the 24 decks (386 slides) renderable by both it and
PowerPoint. Median changed-pixel rate was 16.0512%, median normalized RGB MAE
was 2.2455%, and median PSNR was 19.076 dB. A human spot-check still found
visible text-style differences. The previous renderer's same-corpus medians
were 16.2330% changed pixels and 3.0356% RGB MAE. These results do not
establish a release threshold or PowerPoint parity.
Users must verify exported decks in PowerPoint before relying on their visual
layout. This result is about preview output; it does not by itself prove that
the export path has the same visual differences. The separate Office export
comparison is reported in the [corpus results](CORPUS.md).

Do not use hidden PowerPoint COM automation as the shipped renderer. Microsoft's
[guidance on unattended Office automation](https://learn.microsoft.com/en-us/office/client-developer/integration/considerations-unattended-automation-office-microsoft-365-for-unattended-rpa)
does not recommend or support non-interactive use because it can deadlock or
behave unstably. Keep Office automation in the guarded local validation path.
A renderer replacement must be evaluated against the pinned corpus, supported
feature classes, licensing, packaging, and privacy before this boundary can be
removed. The current candidate is integrated behind isolation, but its
responsiveness and memory use at the supported 50 MiB input limit, the Office
visual review backlog, and real preparation-session evidence remain open.

Aspose.Slides for .NET is one on-premises evaluation candidate, not an approved
dependency. Its purchase page listed Developer OEM at US$2,997 for one
developer and unlimited deployment locations on 2026-09-30; that license type
allows external distribution. The evaluation build adds a watermark and
truncates text read from presentations, so it cannot establish clean visual
fidelity. A temporary license request requires a valid business email. No
license request or purchase has been made. Recheck the [current license
terms](https://purchase.aspose.com/pricing/slides/net) and
[evaluation limits](https://docs.aspose.com/slides/net/licensing/) before
considering this path.

The browser renderer `@office-kit/pptx-preview@0.12.0` was also screened. It
rendered 14 of the 16 Core-comparable decks; on those same 218 slides its
median changed-pixel rate and median normalized RGB MAE were worse than the
current worker's. It is not approved as a replacement. The detailed comparison
and limitations are recorded in [PPTX fidelity](PPTX_FIDELITY.md).

Reason:

A warning does not make a materially inaccurate preview suitable for approving
high-stakes slide layout. The product needs a renderer decision supported by
repeatable visual evidence and an appropriate deployment license.

## PW-D18 — Alternate-content objects remain read-only and source-preserved

**Status:** Accepted

Core inventories the first `mc:Choice` whose `Requires` prefixes resolve only
to namespaces it supports (`p`, `a`, and `r`), otherwise the `mc:Fallback`.
Malformed or unresolvable requirements fail closed. The unselected branch is
never removed or rewritten as a side effect of inventory. Objects selected
from an alternate-content block are read-only, and Core does not descend into
opaque `graphicFrame` payloads such as embedded OLE fallbacks. Shape-ID
allocation scans every raw `cNvPr` ID, including hidden branches and opaque
payloads, so newly written objects remain unique across the preserved source.

Reason:

`Choice` and `Fallback` branches are mutually exclusive representations of
one logical drawing object, while nested OLE pictures are payload data rather
than slide-level objects. Counting them as independent shapes creates false
identity conflicts. Preserving unknown branches and making their visible
objects read-only avoids changing Office-specific behavior without weakening
duplicate-ID checks on effective drawing objects.

## PW-D19 — AI rewrite proposals use the existing revisioned edit path

**Status:** Accepted; one selected-text proposal is implemented

The initial Workspace rewrite feature accepts one supported paragraph and a
bounded user instruction. Core sends only those inputs through the selected
reasoning provider, binds the result to the current source and exact revision,
and returns it for review. The renderer can copy the replacement into the
existing editor, where the user must preview and save through the ordinary
Core edit transaction. Provider output is never applied or written to OOXML
directly. Core rejects a proposal when the selected revision or text changes.

Reason:

This establishes a narrow, testable AI-editing path while keeping provider
inference, edit authority, revision history, and user approval at their
existing boundaries. Multi-operation EditPlans remain a later PW4 step.

## Reviewed selection actions and canvas shortcuts (2026-10-03)

The canvas now offers Duplicate selection and Delete selection for 1–20 supported
native objects. Ctrl+D opens duplication review; Delete and Backspace open deletion
review. Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y traverse presentation history when focus is
on the canvas. Existing copy/paste shortcuts remain available. Shortcuts respect
handled events, editable text fields and voice-workflow ownership. These actions
use native preview, explicit acknowledgment, exact reviewed-byte save, one-revision
undo/redo, retrieval refresh and discard through the existing transaction lane.
Supported shapes, pictures, charts and tables keep their existing dependency guards.

Dependencies considered before editing: batch actions must target the same immutable
revision and expected geometry; sequential staging must publish nothing if a later
object fails. Native chart/workbook relationships and table geometry continue through
the existing writers. The transaction save response now includes created_object_id,
already allowed in audit metadata, so all saved copies can stay selected. Discard
previously lost selection while restoring the shared preview cleared the inventory;
selection now survives that refresh only for the exact document, slide, revision and
verified native object IDs. No new public IPC, provider schema or database migration.

Validation: seven new Core tests cover shapes, charts and tables, new identities,
exact reviewed-byte publication, whole-selection deletion, undo/redo, discard and
late-operation failure with unchanged head/history and cleaned staging files.
All 828 collected Core tests passed in four fresh-process serial batches
(168 + 232 + 218 + 210), without skips/omissions; all 134 desktop tests passed.
Receipts: `.local/selection-actions-core-focused.log`,
`.local/selection-actions-core-batches/manifest.json` and
`.local/selection-actions-desktop-final.log`. Final lint, formatting, both
TypeScript projects and mypy (147 source files) passed. Final receipts:
`.local/selection-actions-lint-verified.log`,
`.local/selection-actions-format-verified.log` and
`.local/selection-actions-types-final.log`.

The complete Electron sweep passed 73 workflows. The new workflow exercises
keyboard duplication, reviewed discard with selection retention, acknowledged
save with both copies selected, Backspace/Delete review and discard, batch deletion
and Ctrl+Z/Ctrl+Shift+Z/Ctrl+Y history traversal. It counts actual selectable objects
rather than the eight resize handles. Early runs corrected a slide-navigation
assumption, the existing Discard preview label and that handle-counting assertion;
they also exposed and verified the selection-restoration repair. Evidence:
`.local/selection-actions-ui-verified.log` and the inspected
`.local/ui-validation/workspace-selection-duplicate-review.png` and
`workspace-selection-delete-review.png`.

PowerPoint opened ordinary native shape/chart/table fixtures after duplicating two
objects and deleting those copies. It verified shape counts, preserved sizes and
independent in-memory native edits; the three file hashes per fixture stayed
unchanged. All six exported PNGs were inspected. Repeated duplication of one native
chart/table intentionally overlaps copies in these dependency tests; this is native
editability proof, not broad pixel-fidelity acceptance. Evidence:
`.local/selection-actions-office/result.json` and `check-final.log`.
The final 308 source/test hashes are recorded in
`.local/selection-actions-source-freeze.json` and verified in
`.local/selection-actions-source-freeze-check.json`. Core sources/tests remained
unchanged after the full Core run; final renderer checks include the discard fix.
Diff whitespace checks passed. All acceptance processes launched here terminated.

Next priorities: substantial remaining GUI workflows, native grouping/ungrouping,
richer chart/table authoring, then broader corpus fidelity and live integration.
Live fast-decision calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted debt. Dirty work
is preserved; no account/model calls, downloads, commits, pushes, packaging or releases
occurred. The production-readiness goal remains active.

## 2026-10-04 continuation - reviewed native grouping and ungrouping

The Presentation Workspace now groups 2–20 eligible native objects through review,
acknowledgment and exact reviewed-byte save. Group selection and Ungroup selection
are available in Object actions, with Ctrl+G and Ctrl+Shift+G on the focused canvas.
Saved groups, moved/resized groups and promoted children remain selected. Supported
native groups can move and resize through the existing reviewed geometry workflow.
Nested groups are supported within a bounded eight-level hierarchy. Discard,
retrieval refresh and whole-revision undo/redo use the existing transaction lane.

Dependencies considered before editing: grouping changes native coordinate
hierarchies, layer order and retrieval traversal, while child identities and picture,
chart and workbook relationships must survive. Selected objects retain source order
inside the new group at the frontmost selected layer. Ungrouping maps child geometry
through parent offsets and scales; nested child coordinates remain coherent. Native
group moves/resizes edit only the outer frame. Retrieval now traverses nested groups
for text, tables and chart summaries. New capability flags and selected-object save
metadata are additive; no database migration or new public IPC endpoint was needed.

Eligible objects include supported shapes, embedded PNG/JPEG pictures and unlocked
native charts. App-authored charts now allow grouping; imported grouping locks remain
respected. Native PowerPoint directly refused grouping a locked imported chart,
confirming that restriction. Tables and placeholders follow
[PowerPoint grouping limits](https://support.microsoft.com/en-gb/office/graphics-visuals/group-or-ungroup-shapes-pictures-or-other-objects).
Rotated/flipped or malformed groups, inherited fills/effects, hidden/click actions,
locks, connector/animation dependencies and children outside group coordinate bounds
remain read-only with explicit reasons. Child geometry edits use the containing group.
Native group copy, duplicate, delete and layer actions, plus Copilot grouping
proposals, remain open; this slice provides manual reviewed grouping and geometry.

Validation: 23 new Core tests cover PNG/JPEG pictures, native charts, nested groups,
layer/identity preservation, retrieval, nonuniform scaling, promoted geometry,
undo/redo, stale targets, discard and atomic late failure. All 851 collected Core
tests passed in four fresh-process serial batches (249 + 186 + 239 + 177), without
skips or omissions. All 134 desktop tests and all 74 Electron workflows passed.
The new GUI workflow covers keyboard/toolbar grouping, acknowledgment, discard,
save, selected-group resizing, ungrouping and history traversal. Both new review
screenshots were inspected. Lint, formatting, both TypeScript projects and mypy
(149 source files) passed on the final source. Receipts:
`.local/groups/core-focused-final.log`, `.local/groups/core-batches/manifest.json`,
`.local/groups/desktop.log`, `.local/groups/ui-final.log`,
`.local/groups/lint-final.log`, `.local/groups/format-final.log` and
`.local/groups/types-final.log`.

Native PowerPoint opened four mixed text/picture/chart fixtures (PNG/JPEG, flat and
nested) before and after reviewed ungrouping following translation and nonuniform
resizing. Native chart values/categories and independent text/series edits remained
available; other slides and notes were preserved, and all file hashes stayed
unchanged. All eight exported PNGs were inspected. Each before/after pair had zero
mean pixel difference at 1280×960. This is bounded fixture fidelity acceptance,
not broad corpus or experimental-renderer acceptance. Evidence:
`.local/groups-office/result.json` and `.local/groups-office/check.log`.
The final 311 source/test hashes in `.local/groups/source-freeze.json` were verified
unchanged in `.local/groups/source-freeze-check.json`. Diff whitespace checks passed,
and all acceptance processes launched here terminated.

Next priorities: remaining native group actions and substantial authoring/GUI gaps,
then broader corpus fidelity and live integration. Fast-decision calibration/latency
and actual Sign in with ChatGPT acceptance remain open. Signing and clean Windows
validation remain accepted debt. The dirty worktree is preserved; no account/model
calls, downloads, commits, pushes, packaging or releases occurred. The
production-readiness goal remains active.

## 2026-10-04 continuation - complete native group actions

Eligible native groups now support copy/paste, duplication, complete deletion and
all four layer actions in the Presentation Workspace. The canvas uses the existing
Ctrl+C/Ctrl+V, Ctrl+D and Delete/Backspace review workflows; the Objects inspector
also exposes duplication/deletion and layering for groups. Saved copies select the
new container. Copy/paste accepts an immutable source revision and preserves group
geometry and relative child coordinates across slides or presentations in the same
project. Preview, acknowledgment, exact reviewed-byte save, discard, retrieval
refresh and whole-revision undo/redo remain in the existing transaction lane.

Dependencies considered before editing: a group container has slide-wide IDs for
all descendants, and its charts depend on native chart/workbook package graphs.
The paste writer now assigns every nested object a fresh native ID, counts all
children against resource limits, remaps picture dependencies and clones each
nested chart graph independently of the source. Canonical copied-subtree XML,
child identities, geometry, content and semantic style fields are validated after
writing. Fingerprints may change with namespace context, native offsets and
relationship remapping; they are recomputed rather than mistaken for content loss.
Group duplication reuses this writer. Complete deletion validates removal of the
container and every child ID while preserving package parts that may be shared.
Layer changes move the whole container and validate unchanged object contents.
The renderer inventory validator accepts eligible group deletion capabilities.
No database migration, provider schema or public IPC endpoint was added.

Unsupported groups keep the existing native dependency restrictions. Groups with
unknown or alternate-content child nodes are now explicitly read-only instead of
silently ignoring those children. Direct child edits still use the containing group
or reviewed ungrouping. Copilot proposals for grouping/ungrouping remain open.

Validation: 21 new group-action tests cover PNG/JPEG pictures, flat/nested groups,
same-slide duplication, cross-slide and same-project cross-document paste,
independent chart/workbook parts, complete subtree deletion, layer boundaries,
undo/redo, discard, stale targets, resource limits and atomic late failure. One new
unsupported-child regression test extends grouping coverage. All 71 focused checks
passed in `.local/group-actions-focused-final3.log`. All 873 collected Core tests
passed in four fresh-process serial batches (185 + 301 + 172 + 215), without skips
or omissions; evidence is `.local/group-actions/core-batches/manifest.json`.
All 134 desktop tests passed in `.local/group-actions/desktop.log`.

The complete Electron sweep passed 75 workflows with no renderer errors. The new
workflow covers reviewed group duplication and clipboard paste, selected copies,
deletion discard/save, complete subtree deletion, layer order and whole-action undo,
then continues the earlier resize/ungroup workflow. A first run corrected the new
test's timing: wait for the restored canvas after deletion before counting objects.
Final evidence: `.local/group-actions-ui-final.log`, `.local/ui-validation/result.json`
and four inspected `workspace-group-*-review.png` / `workspace-group-layer-back.png`
screenshots. Final lint, formatting, both TypeScript projects and mypy (149 source
files) passed; receipts are `.local/group-actions/lint.log`, `format.log`, `types.log`
and the final GUI script `ui-script-lint.log` / `ui-script-format.log`.

Native PowerPoint opened four mixed text/picture/chart group fixtures (PNG/JPEG,
flat/nested) before duplication, after duplication and after deleting the copy.
Copied chart values could be edited in memory without changing the original chart.
Other slides and notes remained intact; all file hashes stayed unchanged. All 12
exported PNGs were inspected. Deleting each copy restored a zero mean pixel
difference at 1280×960. Copy views intentionally overlap and show the independently
edited chart; these are native dependency/editability checks, not layout quality
or broad corpus/experimental-renderer fidelity acceptance. Evidence:
`.local/group-actions-office/result.json` and `.local/group-actions-office.log`.
All final 312 source/test hashes in `.local/group-actions/source-freeze.json` were
verified in `source-freeze-check.json`. All acceptance processes launched here
terminated; diff whitespace checks passed.

Next priorities: substantial remaining authoring/GUI workflows, including native
theme/master-layout discovery and application, then broader corpus fidelity and
live integration. Fast-decision calibration/latency and actual Sign in with ChatGPT
acceptance remain open. Signing and clean Windows validation remain accepted debt.
The dirty worktree is preserved; no account/model calls, downloads, commits, pushes,
packaging or releases occurred. The production-readiness goal remains active.

## 2026-10-04 continuation - reviewed appendix creation

Create appendix is now available in Slide actions & layout. Choose 1–18 existing
detail slides, move them out of the main story or copy them while keeping originals,
and add an editable Appendix divider with notes and Classic/Midnight/Paper styling.
Main slides and selected detail slides retain their original relative order. Moving
requires at least one main slide; copying can include all slides. The resulting deck
must stay within the existing 5,000-slide limit and twenty-operation transaction bound.

The user reviews the proposed order, divider and each detail slide before the review
checkbox and save can activate. Changes to choices/content invalidate approval and
require another preview. Saving publishes exact reviewed bytes as one revision,
selects the divider and refreshes retrieval; discard restores the baseline preview,
and undo/redo traverse the entire appendix as one edit. The dialog uses explicit
source slide numbers and a sequential native preview for content review.

Dependencies considered before editing: slide ordering uses immutable slide IDs,
while divider/copy IDs are generated during staging. Existing earlier-step creation
references allow native authored creation, optional native slide duplication and one
final permutation to compose safely in the same transaction. Native slide writers
preserve notes, picture/chart/workbook relationships and existing objects; no package
round-trip through python-pptx is introduced. Copy mode assigns new slide identities;
move mode preserves identities. A pure renderer planner rejects duplicate/unknown
selection, stale order, empty main story and capacity overflow. Proposed native
inventory is checked against expected main/appendix order before rendering. All
existing Core validators, review ownership, exact-byte save, history and audit paths
remain authoritative. No production Core writer, public IPC, provider schema or
database migration was changed.

Validation: nine new desktop planner tests cover noncontiguous/source-order selection,
copy references, invalid selections, empty-main rejection, all-slide copying, the
20-operation bound and capacity/stale inventory checks. All 143 desktop tests passed.
Ten new Core composition tests cover all three divider templates in move/copy modes,
original native parts/objects/notes, independent chart parts, exact reviewed-byte save,
order and undo/redo; discard, missing targets, stale heads and late-reference failures
publish no partial divider or copies. All 30 focused Core checks passed in
`.local/appendix-core-focused-final.log`. All 883 collected Core tests passed without
skips/omissions in four fresh-process serial batches (225 + 185 + 301 + 172), recorded
in `.local/appendix/core-batches/manifest.json`. Final lint, formatting, both TypeScript
projects and mypy (149 source files) passed; receipts are `.local/appendix/lint.log`,
`format.log`, `types.log` and `desktop.log`. The final GUI-script adjustment passed
`ui-script-lint.log` / `ui-script-format.log`.

GUI acceptance: all 76 checks passed with no renderer exceptions in real Electron
and local Core using a disposable profile. Appendix move/copy previews every detail
and divider, gates acknowledgment/save, invalidates changed drafts, discards, saves,
selects the divider, reindexes and undoes the complete revision. Screenshot review
caught horizontal preview overflow; the existing bounded figure styles now constrain
the image, and a GUI assertion verifies both dialog and preview width. Final move/copy
screenshots were inspected. Receipt: `.local/appendix-ui-layout-retry.log` and
`.local/ui-validation/result.json`. The initial test navigation assumption was fixed
by explicitly selecting slide 1 after undo. A later sweep timed out opening History
after redo before reaching appendix checks; the unchanged retry passed that step and
the full sweep. That transient is retained in `.local/appendix-ui-layout-final.log`.
Desktop lint, formatting, both TypeScript projects and all 143 desktop tests passed
again after the layout correction in `.local/appendix/layout-{lint,format,types,desktop}.log`.

Native PowerPoint opened all six move/copy × divider-template fixtures. Native order,
divider text, notes and charts remained valid; copied chart values could be edited
without changing the retained original. Detail-slide exports had zero mean pixel
difference from their source at 1280×960, and file hashes stayed unchanged. All 18
native exports were inspected in three visual QA sheets. This is bounded fixture
acceptance, not broad corpus, experimental-renderer or human design acceptance.
Evidence: `.local/appendix-office/result.json`, `.local/appendix-office.log` and
`.local/appendix-office/contact-{classic,midnight,paper}.png`.

The final source/test freeze is `.local/appendix/source-freeze.json` (316 files).
All hashes were verified in `.local/appendix/source-freeze-check.json`; the final
layout correction changed only the renderer preview wrapper and GUI assertion, so
Core and native PowerPoint evidence remains applicable. All owned test/Office
processes reached terminal states, and `git diff --check` passed.
Native master/layout discovery and application were already implemented; the previous
handoff's suggestion to implement them next was incorrect. Remaining authoring gaps
include structured diagrams, source/evidence footnotes, existing-placeholder remapping
and layout thumbnail comparison, followed by broader fidelity/integration acceptance.
Automatic semantic appendix labels and model-assisted appendix selection are not
proven by this manual flow. Fast-decision calibration/latency and actual Sign in with
ChatGPT acceptance remain open. Signing and clean Windows validation remain accepted
debt. Dirty work is preserved; no account/model calls, downloads, commits, pushes,
packaging or releases occurred. The production-readiness goal remains active.

## 2026-10-04 continuation - reviewed native evidence footnotes

Claim and evidence review now offers Add evidence footnotes for an unchanged claim
reviewed on the current revision with current source excerpts. Choose 1–4 sources,
review their excerpt text and source unit/relation, edit citation labels, choose
light/dark text, and set top/bottom or explicit vertical placement. Each numbered
citation is an editable native text box. The proposed slide must render, and the
user must acknowledge labels and placement before saving exact reviewed bytes as
one revision. Changes invalidate approval; discard restores the current slide.
Save refreshes retrieval. Undo/redo traverses the entire citation block. The new
revision requires fresh claim review; citations are static review snapshots and do
not automatically update when sources or deck contents change.

Dependencies considered before editing: claim records already contain reviewed
source names, ordinals, excerpt hashes and relations. The modal rechecks claim
revision, object span, quote, excerpt identity/hash, relation and source location
before staging. Native text-box creation now accepts optional bounded geometry and
font size/color/emphasis/alignment through existing validators, while existing
callers retain centered placement and 18-point defaults. The writer verifies the
new object's text/style/geometry and identity and preserves all prior objects,
notes, other slides and package parts. One transaction owns the preview and save;
no database migration, provider call or new public method was introduced. Color
and placement are user-reviewed; no automated collision or font-fit claim is made.

Validation: eight new desktop planner checks cover source locations/relations,
numbered order, four-source geometry, stale/missing/duplicate evidence, invalid
labels/identity/dimensions and custom placement/bounds. All 151 desktop tests passed.
Ten new Core checks cover one/four citations with light/dark font colors, native
style/geometry, unchanged package parts, exact preview-byte save, whole-revision
undo/redo and invalid input/late-stage rejection without partial publication.
All 893 collected Core tests passed in four fresh-process serial batches
(145 + 229 + 222 + 297), without skips or omissions. Final formatting, lint, both
TypeScript projects and mypy (149 files) passed. Receipts are in `.local/footnotes/`:
`core-batches/manifest.json`, `core-full.log`, `desktop-final.log`, `format-final.log`,
`lint-final.log` and `types-final.log`.

GUI acceptance: all 77 checks passed in real Electron and local Core with a
disposable profile and no renderer exceptions. Footnotes preview current reviewed
sources, invalidate changed labels, discard, save native editable citations, refresh
retrieval, require fresh claim review on the new revision and undo the complete
block. The dialog overflow assertion passed and its final screenshot was inspected.
Receipt: `.local/footnotes/gui-final.log`, `.local/ui-validation/result.json` and
`.local/ui-validation/workspace-evidence-footnotes-review.png`. The initial new test
failed because selecting the original deck did not open its preview; it now opens
that deck and waits for the current revision before history restoration. The earlier
failed receipt is retained in `.local/footnotes/gui.log`.

PowerPoint opened four Classic/Midnight × upper/lower-placement fixtures. All sixteen
native citations retained exact text, ten-point fonts and in-bounds positions; native
text bounds fit their shapes, notes stayed intact and file hashes did not change.
All four exported PNGs were visually inspected. Initial top placement intersected
an authored title; explicit vertical placement was added to the dialog, and the
upper fixtures were verified at two inches below the slide top. This is fixture
acceptance, not arbitrary-label collision/fit, broad corpus or renderer equivalence
acceptance. Evidence: `.local/footnotes/office-final/result.json`, `office-final.log`
and `office-final/{classic,midnight}-{top,bottom}.png`.

Source/test freeze: `.local/footnotes/source-freeze.json` (320 files), verified in
`.local/footnotes/source-freeze-check.json`. All owned test and Office processes
reached terminal states; `git diff --check` passed. This slice
modified only four previously frozen files and added four new files; the other
312 frozen source/test files stayed unchanged. Dirty work is preserved on
`codex/production-readiness` at base `657b876739ff7a1cc5709a7e28e92ec2551b337e`.
No account/model calls, downloads, commits, pushes, packaging or releases occurred.
Remaining substantial authoring gaps include structured diagrams, existing-placeholder
remapping and layout thumbnail comparison; broader fidelity/integration, fast-decision
calibration/latency and live Sign in with ChatGPT acceptance remain open. Signing and
clean Windows validation remain accepted debt. The full goal remains active.

## 2026-10-04 continuation - native layout thumbnail comparison

Browse native layouts now shows a verified current-revision baseline and a paged
gallery of four alternatives applied to the current slide's content. Previous/Next
covers every other native layout in catalog order, including unused layouts and
layouts used elsewhere in the deck. Select a thumbnail, then generate and approve
a fresh exact-byte preview before saving. Comparing or changing candidates invalidates
prior approval. Candidate plans are rejected after their images are captured; comparing
alone publishes no revision. The baseline stays fixed across pages. Discard restores
the original slide; a final reviewed save retains existing retrieval refresh and undo.
Native-layout insertion remains in its existing separate review flow.

Dependencies considered before editing: the catalog identifies the current layout by
its used-by slide list, and every candidate is scoped to the immutable document,
revision and slide. A no-op application of the current layout supplies the baseline
through the existing hash-verified package reader. One staged plan at a time supplies
candidate images, verifies the slide identity and is discarded before another is
prepared. The shared renderer stays owned by the modal until restoration. Only four
candidate images are retained for a page, with URL cleanup on replacement/close.
Selecting an image does not authorize its temporary plan. Final save requires the
ordinary new plan, PNG load and acknowledgment. No production Core code, IPC method,
provider schema or database migration changed. The planner rejects duplicate IDs,
ambiguous current layouts, oversized catalogs and invalid pages. The baseline image
height was reduced after screenshot review so the candidate gallery is easier to see.

Validation: six new desktop planner checks cover complete stable catalog order,
other-slide/unused choices, bounded paging, a single-layout deck, invalid pages and
ambiguous/duplicate identities. All 157 desktop tests passed. Two new Core checks
stream the byte-identical baseline, stage/read/reject all ten alternatives without
publishing, save only a freshly reviewed final candidate as revision 2, undo it and
reject a stale comparison after another revision wins. All 53 focused native-layout,
transaction and comparison Core tests passed. Receipts: `.local/layout-comparison/`
`core-focused.log`, `desktop-final.log`, `format.log`, `lint.log`, `types.log`, and
final desktop `format-final.log`, `lint-final.log`, `types-final.log`. The previous
893-test full Core result remains applicable to unchanged production Core and prior
Core test files; this is not a fresh full 895-test suite claim.

GUI acceptance: the final full Electron/local Core sweep passed all 78 checks
with no renderer exceptions using a disposable profile. Tests cover verified baseline
rendering, four-candidate paging, stable baseline URL, thumbnail selection without save
approval, comparison invalidation, loaded thumbnail images, no dialog overflow, discard,
fresh final review/save and whole-revision undo. Both the baseline/comparison and full
four-thumbnail screenshots were inspected after reducing baseline height. Receipts:
`.local/layout-comparison/gui-final.log`, `.local/ui-validation/result.json`,
`.local/ui-validation/workspace-native-layout-comparisons.png` and
`.local/ui-validation/workspace-native-layout-thumbnail-gallery.png`. The first full
sweep also passed before the baseline-height adjustment in `gui.log`.

Native PowerPoint opened and exported the baseline and all ten candidate packages;
text, notes and slide order survived, file hashes and the authoritative head remained
unchanged. All eleven exports were inspected in three contact sheets. The exports
showed real inherited title position/font/orientation differences. Vertical Title and
Text wraps/clips the existing title in its inherited narrow vertical region; layout
comparison does not resolve that remapping/fit gap. No renderer equivalence, automatic
placeholder remapping or broad corpus acceptance is claimed. Evidence:
`.local/layout-comparison/office/result.json`, `office.log` and
`office/contact-{1,2,3}.png`.

Source/test freeze: `.local/layout-comparison/source-freeze.json` (323 files),
verified in `.local/layout-comparison/source-freeze-check.json`. All owned test/Office
processes reached terminal states and `git diff --check` passed.
Three existing source/test files were modified and three added; the other 317 files
from the previous freeze stayed unchanged, including all production Core files.
Dirty work is preserved on `codex/production-readiness` at base
`657b876739ff7a1cc5709a7e28e92ec2551b337e`. No account/model calls, downloads,
commits, pushes, packaging or releases occurred. Next substantial authoring work
includes structured diagrams and existing-placeholder remapping, with the observed
native vertical-title fit issue as concrete fidelity evidence. Broader fidelity and
integration, fast-decision calibration/latency and live Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted debt. Goal active.

## 2026-10-04 continuation - reviewed existing-placeholder remapping

Browse native layouts now offers explicit assignments from eligible existing text
placeholders to the chosen layout's supported text slots. Assignments apply the native
placeholder identity, position and size while preserving each existing object identity
and complete rich-text XML. A fresh preview and acknowledgment authorize exact reviewed
bytes. Changing any assignment invalidates approval. Layout comparison thumbnails show
layout changes alone; final preview includes the assignments. Whole-revision undo/redo
retains the existing history and retrieval-refresh workflow.

Dependencies reasoned through before edits: applying a native layout previously changed
only the slide relationship. Optional `placeholder_mapping` now extends that existing
operation; no new IPC method, provider schema or migration was added. Catalog discovery
accepts an optional verified slide identity and returns eligible source placeholders.
The writer changes only selected placeholder metadata/transforms and the layout
relationship when necessary. Mapped shapes retain IDs, names, styles and full text XML;
unmapped objects, other slides, notes, media and relationships remain preserved.
Native slot transforms must be supported and in bounds. One-to-one object/slot assignment
and distinct final placeholder indices are enforced before publication. Animated or
connector-referenced source placeholders and unsupported 3D/grouped shapes are excluded.
Failed later operations leave the authoritative head unchanged. Existing layout-only
callers keep their previous behavior. Same-layout assignments work and repeated identical
assignments become no-ops.

Validation: eleven new Core cases cover three supported layouts, rich runs, object and
package preservation, unchanged slides/notes/pictures, reviewed hashes, no-ops, atomic
undo/redo, duplicate object/slot assignments, occupied unmapped indices, unknown targets,
empty mappings, late staged failures and exclusion of animation targets. A fresh complete
Core run passed all 906 collected tests in four serial batches (223/235/208/240), with
no omissions or skipped acceptance substituted. All 157 desktop tests passed; formatting,
lint, TypeScript and mypy (150 files) passed. Receipts: `.local/placeholder-remapping/`
`core-batches/manifest.json`, `core-all.log`, `desktop.log`, `format-final.log`,
`lint-final.log` and `types-final.log`.

GUI acceptance: the corrected full Electron/local Core sweep passed all 79 checks
with no renderer exceptions using a disposable profile. The remapping flow selects a
native title slot, previews and acknowledges it, changes the assignment to invalidate
approval, generates a fresh review, saves and undoes the complete revision. Existing
layout comparison, insertion, tables, charts, evidence and project flows also passed.
The review screenshot was inspected and copied to a stable receipt. The initial sweep
stopped because the test queried the reopened asynchronous catalog before it loaded;
adding a catalog-ready wait corrected the test without changing application behavior.
Receipts: `.local/placeholder-remapping/gui-final.log`, `gui-result.json`,
`placeholder-remap-review.png`; the initial failure is retained in `gui.log`.

Native PowerPoint opened and exported three before/after fixtures: Title and Content,
Comparison and Title Slide. COM checks verified rich-text bold/color, native shape IDs,
assigned geometry and preserved notes. Every unchanged second-slide export was
pixel-identical, input/output files remained unchanged by read-only Office opening, and
undo restored the original package bytes. Six first-slide exports were inspected in
`office/contact.png`; Comparison wraps body content into its narrower native content
slot, while Title Slide inherits subtitle styling and moves the title/body. These are
expected theme/layout changes. Receipts: `.local/placeholder-remapping/office-final.log`,
`office/result.json`, and `office/{0,1,2}/{before,after}.png`.

Scope remains explicit existing text placeholders with supported native slots. Freeform
text is not converted, unsupported/dependency-bound placeholders are excluded, and no
automatic fitting, collision avoidance, broad corpus fidelity or renderer equivalence is
claimed. Unmapped shapes keep existing XML but layout inheritance can alter their visible
position or formatting. Users must review wrapping and other content before saving.

Source/test freeze: `.local/placeholder-remapping/source-freeze.json` (325 files),
verified after all checks in `source-freeze-check.json`. All owned test/Office
processes reached terminal states; `git diff --check` passed.
Four prior files were modified and two added; all other 319 prior source/test files were
preserved. Dirty work remains on `codex/production-readiness` at base
`657b876739ff7a1cc5709a7e28e92ec2551b337e`. Next work includes structured diagrams,
broader fidelity/integration acceptance, fast-decision calibration/latency and live
Sign in with ChatGPT acceptance. Signing and clean Windows validation remain accepted
technical debt. Goal active.

## 2026-10-04 continuation - reviewed structured native diagrams

Native diagrams now creates and edits process, hierarchy and cycle diagrams on the
current slide using native grouped PowerPoint shapes and attached arrows. The dialog
supports 2–8 labeled nodes, hierarchy parents from earlier nodes (at most four levels),
three palettes, placement in inches, adding/removing nodes and converting structures.
It reloads existing supported diagrams and previews whole-diagram deletion. Every
change requires a fresh full-slide image and acknowledgment before exact reviewed bytes
save as one revision. Save refreshes retrieval; discard restores the authoritative
preview, and whole-revision undo/redo retains the ordinary history behavior.

Dependencies reasoned through before edits: ordinary grouping/deletion rejects attached
connectors, so diagrams use their own verified semantic writer without weakening those
rules. A diagram's native group description records its bounded structure and native
identity map. Discovery regenerates and compares the complete group XML before offering
an edit. Retained node identities and retained connections keep their OOXML IDs across
regeneration; new nodes/connections get unique IDs. Manual native changes are read-only,
and outside animation/connector references block regeneration/deletion. The writer
changes only the selected slide XML, leaves package entries/relationships/media/notes
intact and validates the entire resulting package. Late failures publish nothing.
Same-data edits become no-ops. Four IPC methods (list/create/replace/delete diagrams),
the desktop allowlists and shared capability examples were added; create/replace/delete
use the existing transaction/review pipeline. No database migration, provider schema,
renderer compatibility rule or generic group eligibility rule changed.

Validation: nineteen new Core cases cover small/eight-node processes and cycles, a branched
hierarchy, native connections, reviewed hashes, preserved original objects/other slides/
notes, complete undo/redo, retained identities across structural changes, stale
fingerprints, manual changes, external dependencies, malformed/duplicate node data,
invalid parents/palettes/text/geometry, late staged failures, whole-diagram deletion and
undo. Twenty-six focused diagram/protocol checks passed. After final routing changes,
a fresh complete Core run passed all 925 collected tests in four serial batches
(249/206/281/189), without omissions or skips. All 157 desktop tests and formatting,
lint, TypeScript and mypy (151 files) passed. Receipts: `.local/diagrams/`
`core-batches/manifest.json`, `core-all-routing-final.log`, `core-routing.log`,
`core-focused-final.log`, `desktop-final.log`, `format-style-final.log`,
`lint-routing-final.log` and `types-routing-final.log`. The initial protocol fixture
mismatch is retained in `core-initial-failure.log` and `core-all.log`.

GUI acceptance: the full Electron/local Core sweep passed all 82 checks with no
renderer exceptions, then passed all 82 again after aligning the save button with the
existing primary-button style. The disposable-profile workflow previews a process,
invalidates approval after a label change, discards without publication, creates a
four-node hierarchy with an assigned parent, saves, reloads it, converts to a cycle,
removes a node, changes palette, saves, previews/saves deletion and undoes all three
complete revisions. Dialog overflow and all existing authoring/project workflows passed.
Final hierarchy, cycle and deletion screenshots were inspected; the hierarchy screenshot
was inspected again after primary-button styling. The initial GUI run caught an oversized
image lacking the established figure wrapper; the next run reached deletion but used
an incorrect Undo accessible name. Both failures are retained. Final receipts:
`.local/diagrams/gui-style-final.log`, `gui-routing-final.log`, `gui-result.json` and
`workspace-native-diagram-{process,hierarchy,cycle,delete}-review.png`.

Native PowerPoint acceptance used five fixtures: three/eight-node processes, a branched
five-node hierarchy and two/eight-node cycles. Each fixture opened read-only at baseline,
inserted, edited and deleted stages. COM verified node IDs/text, group membership,
attached begin/end shapes, directional arrowheads and preserved notes. Unchanged second
slides stayed pixel-identical at every stage; deleting the diagram restored baseline
first-slide pixels, and undo restored exact edited-package bytes. Read-only Office
opening changed no package hashes. All ten inserted/edited exports were inspected in
two contact sheets. Visual inspection caught diagonal routing entering nodes from an
incorrect side; final hierarchy arrows leave parent bottoms and enter child tops, and
process/cycle arrows use separated node edges. Regenerated exports passed all checks.
Receipts: `.local/diagrams/office-final.log`, `office/result.json`,
`office/contact-{1,2}.png` and `office/{0,1,2,3,4}/{inserted,edited}.png`.

The existing PPTX ingestion parser walks grouped children. A separate extraction check
against all five native fixtures verified every inserted label, updated first labels,
absence of deleted labels and identical unchanged-slide units. Receipt:
`.local/diagrams/ingestion-check.json`. No ingestion writer change was needed.

Scope: app-authored process/hierarchy/cycle diagrams with native editable text/shapes,
not full SmartArt authoring or arbitrary graph layouts. Native manual changes and
external dependencies are preserved rather than regenerated. The workflow does not
provide automatic text fitting or collision avoidance; users review labels, connections
and placement. Copilot/voice diagram planning and broader corpus/renderer equivalence
acceptance remain open. Source retrieval refresh is part of reviewed saves; native
PowerPoint evidence and local GUI checks do not prove live-provider quality.

Source/test freeze: `.local/diagrams/source-freeze.json` (329 entries), verified after
all checks in `source-freeze-check.json`. All owned test/Office processes reached
terminal states and `git diff --check` passed. Eight prior
frozen files were modified and all other 317 prior source/test files stayed unchanged.
Three source/test files were added; the existing shared capability example was updated
and added to this freeze. Dirty work remains on `codex/production-readiness` at base
`657b876739ff7a1cc5709a7e28e92ec2551b337e`. Broader fidelity/integration acceptance,
fast-decision calibration/latency and live Sign in with ChatGPT acceptance remain open.
Signing and clean Windows validation remain accepted debt. Goal active.

## 2026-10-04 continuation - Copilot and reviewed voice diagram planning

Copilot edit proposals now create, replace and delete structured native process,
hierarchy and cycle diagrams. Reviewed voice instructions use the same proposal flow.
A proposal can first create an authored slide and then place its diagram through a
staged created-by reference. Existing supported diagrams expose bounded semantic data
and geometry from selected slides, so subsequent requests can convert or remove them.

Dependencies reasoned through before edits: the provider describes intent but does not
supply fingerprints or native identities. Core binds each replacement/deletion to the
current staged package, including targets created earlier in the same plan. The strict
provider schema rejects unknown preconditions, invalid evidence and out-of-scope targets;
the native writer still owns structure, package preservation and external-dependency
checks. At most twenty diagram descriptions per selected slide reach the provider.
Manually changed or externally referenced diagrams remain read-only. Generic group
eligibility, privacy gates, review acknowledgment, exact reviewed hashes, transaction
rollback, retrieval refresh and revision undo retain their existing authority. No new
IPC method or migration was needed.

Validation: eight new Core tests cover staged creation/replacement/deletion, forward
references, unselected targets, invalid evidence, provider-supplied fingerprints,
invalid parents, snapshot data and existing diagram binding. The complete Core sweep
passed all 933 collected cases in four serial batches (160/246/214/313), with no
omissions or skips. All 157 desktop tests, formatting, lint, TypeScript and mypy
(151 files) passed. The final focused planner suite includes 38 cases. Receipts:
`.local/copilot-diagrams/core-batches/manifest.json`, `core-all.log`,
`core-focused-final.log`, `desktop.log`, `format-final.log`, `lint.log` and `types.log`.

GUI acceptance: the complete Electron/local Core sweep passed all 84 checks. A
reviewed voice fixture adds an authored slide plus process diagram, requires both
affected-slide previews, then converts/deletes the diagram and restores all three
revision heads through undo. The creation, conversion and deletion review screenshots
were inspected. No renderer exceptions occurred. The initial run used a slide-title
locator unavailable until selection; the corrected test selects the inserted second
slide and waits for each exact restored revision. Receipts: `gui-final.log`,
`gui-result.json` and `workspace-copilot-diagram-{create,convert,delete}-review.png` in
`.local/copilot-diagrams/`. Voice and provider data are deterministic local fixtures.

Native PowerPoint acceptance used the deterministic local provider to propose/save
an authored slide plus process diagram, convert it to a cycle and delete it. Four
read-only opens verified native node text, attached directional-arrow endpoints,
preserved notes and unchanged package bytes. Both original slides stayed pixel-identical
through all stages. Three successive undos restored exact prior packages and the
baseline. Creation, conversion and deletion exports were inspected. Receipts:
`.local/copilot-diagrams/office-final.log`, `office/result.json` and `office/contact.png`.
The first acceptance script reused a stale revision ID during undo; that script error
and initial log are retained, and the corrected final run passed.

Source/test freeze: `.local/copilot-diagrams/source-freeze.json` (330 entries). Six
previously frozen source/test files changed, 323 remain byte-identical and one test
module was added. Branch remains `codex/production-readiness`, base SHA
`657b876739ff7a1cc5709a7e28e92ec2551b337e`. Dirty work was preserved.

Scope: diagram support is app-authored native shapes, with reviewed placement and text;
full SmartArt editing, automatic text fitting and arbitrary graph layouts remain outside
this slice. Deterministic provider/voice fixtures do not prove microphone recognition,
real model planning, account authentication or cross-renderer equivalence. Broader
fidelity/integration acceptance, fast-decision calibration/latency and live Sign in with
ChatGPT acceptance remain open. Signing and clean Windows validation remain accepted
technical debt. No model/account call, download, staging, commit, push, packaging or
release was performed.

## 2026-10-04 continuation - refinement of unsaved Copilot edit proposals

Copilot now offers a separate Refine proposal field after proposing changes. Feedback
keeps the original request, slide scope and attached pictures, and produces a complete
replacement proposal from the same baseline. A valid replacement must be viewed and
acknowledged again before saving one exact reviewed revision. Failed inference or
validation preserves the prior available proposal; users can clear feedback, acknowledge
it again and save it, or retry refinement. Changing the original request still starts a
fresh proposal. Earlier-step created-target references remain usable across refinements.

Dependencies reasoned through before edits: resolved native target IDs from a preview
cannot become baseline authority. The transient Core review plan therefore retains the
validated provider intent with its original creation references, original/latest
instructions, slide numbers and attached asset IDs. This data is untrusted context,
not approved source material or executable commands. Refinement requires the same
project/document, baseline, slide scope and assets; ownership/expiry and the current
source are checked around inference. The provider returns a full replacement plan,
whose evidence, scope, assets, target preconditions and native operations are checked
again against the baseline and rolling staged package. No previous fingerprint is
supplied by the provider. The existing context bound rejects oversized drafts. Nothing
is published until normal reviewed save. The existing provider-health guard is retained; an explicit
synthetic connection check in the dialog can recover provider readiness before retry.
Failed staging leaves the earlier preview
intact; the GUI discards it only after a valid replacement exists. This adds no IPC
method, database migration or durable draft/conversation storage. Expiry, rejection,
source/project deletion and shutdown remove retained intent with its preview.

Validation: twelve new Core cases cover successful refinement, original title retention,
updated notes, unchanged baseline, exact-byte save/undo, synthetic provider-health
recovery without project content, scope/asset changes, missing or
foreign drafts, stale/expired/non-planner previews, expiry during inference, invalid
evidence, late target failures and two rounds of creation-reference refinement. The
final focused planner suite passed 50 cases. Complete Core validation covers all 945
collected tests in four serial batches (284/161/254/246), with no omissions or skips.
The recovery repeat initially caught an edit-plan-only test hook left enabled during
the synthetic connection check. After correcting that fixture, the entire affected
161-case batch was rerun successfully; the other three batches passed unchanged.
All 157 desktop tests, formatting, lint, TypeScript and mypy (151 files) passed. Receipts:
`.local/copilot-refinement/core-batches/manifest-recovery-final.json`,
`core-all-recovery.log`, `core-retry.log`, `core-focused-recovery-final.log`,
`desktop-recovery.log`, `format-recovery-final.log`, `lint-recovery-final.log` and
`types-recovery.log`. Earlier complete 945-case and 86-check runs remain in
`core-all.log` and `gui.log`; all intermediate failures are retained.

GUI acceptance: the final Electron/local Core sweep passed all 86 checks with no
renderer exceptions. The workflow reviews an initial title/notes proposal, fills
feedback, rejects malformed evidence while retaining that proposal and its viewed
state, clears feedback and re-acknowledges the original, explicitly checks the provider,
then refines successfully. It verifies the original title change is retained, notes
are revised, old acknowledgment is cleared, save stays disabled until fresh review,
and the result saves/re-indexes as one revision followed by whole-revision undo. Failed
and refined review screenshots were inspected. The first recovery run showed that
malformed output correctly marks the provider unavailable, preventing retry; the dialog
now exposes the existing synthetic Check reasoning provider action without weakening
that guard or sending project content. Receipts: `.local/copilot-refinement/`
`gui-recovery.log`, `gui-result.json` and `workspace-copilot-refinement-{failed,review}.png`.
`gui-final.log` preserves the provider-readiness failure that drove this recovery work.

Native PowerPoint opened baseline, initial unsaved draft and refined packages read-only.
The title change appeared exactly once; refined notes matched the reviewed replacement;
initial/refined first-slide pixels were identical because only notes changed. The
unchanged second slide remained pixel-identical. Office changed no package bytes, save
published the reviewed package and undo restored baseline bytes. The refined slide export
was inspected. Receipts: `.local/copilot-refinement/office.log`, `office/result.json` and
`office/{baseline,initial,refined}-{1,2}.png`.

Source/test freeze: `.local/copilot-refinement/source-freeze.json` (331 entries). Six
previously frozen source/test files changed, 324 remain byte-identical and one test
module was added. Branch remains `codex/production-readiness`, base SHA
`657b876739ff7a1cc5709a7e28e92ec2551b337e`; dirty work was preserved. The AI editing
contract now documents refinement and the current 21-type provider schema.

Scope: this verifies deterministic local provider planning and GUI review mechanics;
real model refinement quality, microphone recognition, cross-renderer equivalence and
account authentication remain unproven. Broader substantial authoring/GUI work and
fidelity/integration acceptance remain, including fast-decision calibration/latency
and live Sign in with ChatGPT acceptance. Signing and clean Windows validation remain
accepted technical debt. No model/account call, download, staging, commit, push,
packaging or release occurred. Goal remains active.

## 2026-10-04 continuation - Copilot native table and chart workflows

Copilot now proposes native table/chart creation, value edits and structural changes.
It can create an authored slide and populate it through earlier-step references, edit
existing cells/series, add or remove rows/columns/categories/series, and compose these
operations as one reviewed revision. The dialog exposes exact proposed cells and chart
numbers, with expandable previous data from the actual staged target; slide images alone
would hide exact values. Existing refinement, evidence review, affected-slide viewing,
acknowledgment, exact-byte save, retrieval refresh and whole-revision undo remain intact.

Dependencies reasoned through before edits: the direct writers already own supported
native structures and their package-preservation rules. The provider schema now adds
six operations (27 total) without granting fingerprints or workbook authority. Numeric
schema validation accepts bounded finite integers/floats and rejects booleans/NaN;
domain writers validate rectangular data, category/series lengths, pie constraints,
source-index maps and native compatibility. Core inspects only selected slides and
supplies at most twenty table descriptions and twenty chart descriptions per slide,
with ordinary context-size enforcement. It supplies cached chart data rather than
embedded worksheet content and strips fingerprints/native part references. Replacement
and structural operations bind current fingerprints from each staged package, so prior
steps can create or update their targets. Retained source indices remain unique and in
original order; null creates an item. Tables with merged/complex cells, linked/unsupported
charts and unsupported structures remain read-only. Existing writers preserve or clone
native relationships/workbooks appropriately, protecting shared charts and hidden original
workbook parts. No native writer, IPC method, database migration or revision authority
was changed. Previous-data diffs are review response data, not durable audit content.

Validation: twenty new Core cases cover composition of all six operations, ordered
creation references, successive fingerprints/diffs, exact reviewed save and undo,
forward/unselected/wrong-kind targets, malformed evidence/preconditions, boolean/NaN
values, ragged tables, mismatched series lengths, invalid source maps, shared imported
chart isolation, linked/extension/stacked/missing-cache charts, ordinary table context,
merged/mixed-run table preservation and a real hidden embedded worksheet. The hidden
worksheet's sentinel never enters provider input; its original workbook member survives
the selected chart edit. All 50 existing planner/refinement/diagram tests passed before
the new module. The fresh complete Core sweep passed all 965 collected tests in four
serial batches (229/281/169/286), with no omissions or skips. All 157 desktop tests,
formatting, lint, TypeScript and mypy (151 files) passed. Receipts under
`.local/copilot-data/`: `core-batches/manifest.json`, `core-all.log`,
`core-focused-more.log`, `core-existing.log`, `desktop.log`, `format-final.log`,
`lint-final.log` and `types-final.log`. The initial lint-only fixture line-length error
is retained in `lint.log`.

GUI acceptance: the Electron/local Core sweep passed all 90 checks with no renderer
exceptions. It creates an authored slide plus table/chart, reviews both affected slides
and exact numeric data, saves, selects the new slide, updates both values together,
compares previous/proposed data, expands table rows/columns and chart categories/series,
saves each as one revision/re-index, and undoes all three exact revision heads. Creation,
update and expansion review screenshots were inspected. Receipts:
`.local/copilot-data/gui.log`, `gui-result.json` and
`workspace-copilot-data-{create,update,expand}-review.png`.

Native PowerPoint opened the baseline and all three saved stages read-only. COM verified
native table dimensions/every cell, chart title/category/series names/values and notes.
Independent embedded-worksheet inspection verified matching literal cells and no formulas.
Both original slides remained pixel-identical, native table/chart identities remained
stable, Office changed no package bytes and three successive undos restored exact prior
packages and baseline. All three native slide exports were inspected in a contact sheet.
Receipts: `.local/copilot-data/office.log`, `office/result.json`, `office/contact.png`
and `office/{created,updated,expanded}.png`.

Source/test freeze: `.local/copilot-data/source-freeze.json` (332 entries). Seven prior
source/test/style files changed, 324 remain byte-identical and one test module was added.
Branch remains `codex/production-readiness`, base SHA
`657b876739ff7a1cc5709a7e28e92ec2551b337e`; dirty work was preserved.

Remaining substantial chart presentation gap observed in the native exports: adding a
second series preserves an existing hidden legend, so the user still needs explicit
legend controls. This slice adds data planning/review, not chart decoration controls or
automatic fitting. Broad corpus/renderer fidelity, real-model integration quality,
fast-decision calibration/latency and live Sign in with ChatGPT acceptance remain open.
Signing and clean Windows validation remain accepted technical debt. These tests used
local deterministic providers and synthetic data; no account/model call, download,
staging, commit, push, packaging or release occurred. Goal remains active.

## Explicit native chart legends - 2026-10-04

Keep legend appearance separate from chart-data replacement and structural edits.
A dedicated chart-only clone retains original workbook bytes/relationships and all
non-legend chart XML; only the selected frame points to the new chart. Preserve
existing legend style and entries on placement/overlay changes. Hiding is explicit;
showing again uses defaults, while undo restores the original styled legend.
Manual layouts/extensions/unsupported settings remain read-only. Hidden overlay is
invalid. Reuse the owned-preview, fresh acknowledgment, exact-hash save and ordinary
revision restoration lifecycle. Copilot receives bounded legend metadata, cannot
supply fingerprints, and reviews previous settings from the actual staged target.
No migration or additional public IPC surface is necessary.

## Reviewed native chart colors - 2026-10-04

Extract the existing legend chart-only clone/publish boundary for both legend and
color operations; do not replace chart data/workbooks when changing appearance.
Set opaque RGB on only a selected series/point fill/outline; line series edit stroke
and retain non-rendered area fill. Keep widths, dashes, effects and point/marker overrides.
Pie colors target slices; line point/marker decorations need a separate native contract.
Report null current colors as inherited/custom, rather than invent a resolved theme RGB.
Require fresh native preview after target/RGB changes. Core supplies color metadata,
binds staged fingerprints and captures previous explicit RGB for Copilot review.
No database or public IPC extension is needed. Shared chart references isolate through
chart-only clones, and original chart/workbook bytes remain intact.

## Reviewed native table range formatting - 2026-10-04

Reuse the existing table writer with a distinct formatting branch, retaining the
plain-cell eligibility gate and owned transaction review/save path. Select an
inclusive native cell rectangle, with header/whole-table presets. Treat nullable
style fields as Keep current; do not invent theme resolution or normalize untouched
cells. Set only requested bold/italic/font size/text RGB/fill RGB/horizontal/vertical
alignment, consistently across runs, paragraph defaults and paragraph endings.
Preserve table text, native style references, frame IDs/geometry, borders and margins.
Prove XML outside selected cells unchanged and validate final native text. Keep
merged/linked/complex cells read-only, reject ambiguous paragraph properties and
invalid/reversed/boolean/stale inputs. Font changes require text-fit review; this is
explicit formatting rather than automatic fitting. Capture selected prior settings
from every staged target for Copilot; providers receive no fingerprints or XML/path
authority. No database migration or public IPC extension is needed.

## Reviewed native data labels - 2026-10-04

Direct and Copilot label settings now target one/all series, compatible placements,
value/category/series names, pie percentages and nullable native number formats.
Owned package review/save/discard, exact staged previous-settings review and undo
reuse existing transactions. Chart-only clones preserve workbook/data, title/notes,
IDs/geometry, legend/colors and native custom text/decoration. Inherited global point
decoration is copied into selected-series overrides; untouched series remain intact.
All 1071 Core tests, 157 desktop tests, formatting/lint/types and 102 Electron workflow
checks pass. Native PowerPoint verifies all series on 12 packages and eight exact
undos. The current copy/minimum-window check is separate from the full GUI sweep.
Receipts: .local/chart-labels/, including 345-entry source-freeze.json.

Known fidelity gap: the app preview ignores label numFmt and omits some column/bar
label content; one full-GUI image had an empty plot (possible settling race, unproven).
The native PPTX is correct in PowerPoint. Workflow checks do not prove visual label
acceptance. The direct dialog discloses the limitation; repair renderer label/content/
format/completion handling next, before adding axes or more chart controls. Source
cache mutation would change axes/tooltips and is not an acceptable preview repair.
Broad corpus/model/integration, fast-decision calibration/latency and live ChatGPT
sign-in remain open. Signing/clean Windows remain accepted technical debt.
