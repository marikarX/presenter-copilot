# Presentation Workspace

In **New presentation → Plan with Copilot**, use **Save drafting session** to keep
one project-local session with up to ten drafts. After reopening or restarting,
choose **Resume saved drafting session**. Edited drafts, branch baselines, notes,
briefing and unsent refinement are retained. Saving replaces the project's saved
copy. **Reload saved copy** refreshes its record after a conflict while keeping your
current edits; **Remove saved copy** keeps the temporary draft in the dialog.
These actions do not call a provider, restore account settings or create a deck.
Original planning responses remain in local project provenance records. Review the
saved source excerpts and current facts before creating slides.


## Choose a slide's appearance (2026-10-08)

Open a presentation preview and select **PowerPoint appearance** to view the saved
slide rendered by Microsoft PowerPoint. This requires PowerPoint installed on
Windows. **Browser appearance** returns to the experimental browser renderer.
After navigating, saving an edit, or undoing/redoing, select PowerPoint appearance
again to render that saved version. Manual slide-edit and Copilot edit-plan reviews
also offer PowerPoint appearance for proposed bytes before saving. Refinement,
appearance switching and discard invalidate prior frames and review acknowledgment.
Specialized draft previews outside those review dialogs still use Browser appearance.
Supported object selection and editing controls remain available over the native
image. If native rendering fails, continue with Browser appearance or retry.

Both development and the current unsigned unpacked app pass the native GUI checks,
including selection bounds, stale replies, retry, and full-slide containment at the
minimum window size. The full Workspace sweep passes 117 workflows on the corrected
canvas. These are local installed-Office and fixture-based workflow checks; broader
fidelity, live-provider, human workflow and hardware acceptance remain open. See
the [handoff](../SESSION_HANDOFF.md) for current receipts.

Current native corpus validation preserves shared PowerPoint application state:
private byte-checked copies, no global property changes/Quit, independently
balanced COM initialization, and preflight before opening active/external content.
Installed Office unsaved-sentinel/already-open-source preservation passes. Fresh
33-record comparison covers 28 decks / 563 slides; two external-link decks are
skipped and three embedded-OLE decks are blocked. All compared slides retain
stable pixel differences, so broad fidelity acceptance remains open. See the
[handoff](../SESSION_HANDOFF.md) for current receipts and next fidelity targets.


Fast Decisions Settings keeps an unsaved provider/model draft through ChatGPT
sign-in and status refreshes. Account changes revalidate the chosen model; a
catalog failure disables Save while retaining the same account's draft for retry.
Only explicit Save configures a provider. Live ChatGPT acceptance remains open.
The dedicated GUI check is `node apps/desktop/scripts/test-chatgpt-settings.mjs`.


## Restore and compare outline drafts (2026-10-07)

Plan with Copilot retains ten successful drafts in the open creation dialog.
Restore an earlier draft with its manual edits, source review and briefing;
refining it creates a branch while retaining later alternatives. Before/current
comparison shows changes from the exact draft sent with a refinement. Review the
chosen outline before creating a native presentation. Closing or switching modes
clears this temporary conversation. See [the planning contract](AI_EDITING.md#planning-contract).

## Hold to dictate an edit (2026-10-07)

Hold Ctrl+Shift+Space in the selected-text editor, Copilot edit dialog or outline
planner. Release to review a local transcript; correct it and explicitly use it
before separately requesting a provider proposal. Escape or leaving the window
cancels an unfinished gesture. Capture/review feedback moves into view. Existing
Dictate/Stop/Discard buttons remain available. This focused shortcut leaves the
system-wide Live Assist shortcut unchanged. Physical microphone quality/latency
and automatic ambiguity handling remain open; see [the voice contract](AI_EDITING.md#voice-path).

## Native PowerPoint PDF export (2026-10-04)

Export PDF saves the selected immutable revision as print-quality static slides using
installed Microsoft PowerPoint on Windows, with hidden slides omitted unless requested.
The owned modal/picker supports cancellation and discloses that notes/animations are not
included. Core copies a revision-bound snapshot; privileged Main launches a separate
one-job worker, verifies its PDF and atomically saves the approved destination. The worker
closes only its read-only copied deck, never quits PowerPoint or changes shared settings.
Active/embedded OLE and external non-hyperlink dependencies require manual export;
protected PDFs retain their protection and need manual review. Timeouts kill only the
worker; hung Office can retain the owned hidden deck/private files. Packaging acceptance
is still open for the updated one-job flag/COM hidden imports.

The 117-workflow real Electron sweep, 187 desktop tests, final rebuilt 707x460 content
window, 21-visible/22-all native PDFs and unsaved PowerPoint sentinel pass. All 22 native
PDF pages were rendered/compared and the contact sheet inspected; none of the 22 exact
speaker-note paragraphs appear. This is bounded fixture acceptance, not broad corpus
compatibility. See [current handoff](../SESSION_HANDOFF.md) for exact receipts, failures,
dependency decisions and remaining Fast Decisions/Sign in with ChatGPT acceptance.


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


Status: **Limited research preview: verified PPTX preview and inventory, single-run or uniformly formatted multi-run text replacement, all-run and paragraph formatting on simple shapes of up to 128 paragraphs within the 2,000-character Workspace limit, horizontal alignment, bounded left indentation, signed first-line/hanging indentation, whole-point line spacing, disc, hollow-circle, square, or dash bullet styles, no-bullet formatting, and Arabic-period automatic numbering, and before/after spacing, rectangle/ellipse creation, plain speaker-notes, bounded move/resize, simple embedded-picture creation, cropping, and PNG/JPEG replacement, eligible object deletion and duplication, blank-slide creation using the current or another slide's existing layout, applying an existing layout to a slide, supported slide deletion, slide duplication and reordering with immutable revisions, current/original export and restore, branch-aware undo/redo, review-only slide-purpose decisions and selected-text rewrite proposals, and explicit user-confirmed purpose labels scoped to a revision. Full fidelity, broader editing, real-user validation, and the decision evaluation remain pending.**

This package defines how Presenter Copilot can evolve from a presentation-intelligence sidecar into the primary preparation workspace for an imported or newly created presentation while preserving the existing local-first rehearsal/live-assist architecture.

The current creation workflow accepts a manual outline or a review-only
Copilot plan from an objective, audience, briefing, and requested slide count.
Users can refine the plan, edit its content, inspect cited excerpts, and review
the final outline before native PPTX creation. Generated decks use the normal
ingestion, original revision, editing, retrieval, rehearsal, and export paths.
The Rehearsal inspector links completed Run candidates to their source
revision and current stable slide, and supports explicitly reviewed text and
notes edits with atomic applied provenance. These workflows pass local
synthetic Core and Electron checks; real-provider quality, presenter acceptance,
template/asset authoring, broader edit plans, and preview fidelity remain open.

The central product decision is:

> PowerPoint is an interoperability target, not the required editing environment for the Presenter Copilot preparation loop.

A user who imports a PPTX should normally be able to inspect, edit, reorganize, enrich, rehearse, challenge, and export that presentation without leaving Presenter Copilot. The product does **not** attempt full feature parity with PowerPoint, Keynote, or Google Slides.

## Why this exists

The current MVP correctly treats PDF/PPTX as source material and keeps PowerPoint integration read-only. That is appropriate for validating retrieval, rehearsal, ASR, Challenge, and Live Assist. After those wedges are proven, forcing users back into PowerPoint for routine changes would break the strongest product loop:

```text
Import / create
      |
      v
Understand + edit
      |
      v
Teach / enrich
      |
      v
Rehearse / Challenge
      |
      v
Find weak claims, better explanations, missing evidence
      |
      v
Apply changes to the presentation
      |
      +-------------------------> rehearse again
```

The workspace therefore adds **editing** to the same Project Brain, Speaker Profile, Audience Model, evidence, and rehearsal history already used elsewhere in the product.

## Package map

- [`PRODUCT.md`](PRODUCT.md) — product boundaries, jobs-to-be-done, user journeys, and non-goals.
- [`UX.md`](UX.md) — workspace interaction model, direct editing, AI side chat, voice input, review/undo, and failure behavior.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — dual-representation architecture, document identity, edit transactions, synchronization, local-first boundaries, and extensibility.
- [`PPTX_FIDELITY.md`](PPTX_FIDELITY.md) — imported-PPTX compatibility strategy, object support tiers, opaque preservation, round-trip testing, and export contract.
- [`AI_EDITING.md`](AI_EDITING.md) — typed AI/voice editing model, planning/apply boundary, selection/context rules, provenance, and safety constraints.
- [`ASSETS.md`](ASSETS.md) — images, diagrams, generated media, provenance, rights metadata, variants, and project-local storage.
- [`ROADMAP.md`](ROADMAP.md) — staged implementation sequence, dependency gates, exit criteria, and deferrals.
- [`VALIDATION.md`](VALIDATION.md) — product/fidelity metrics, corpus design, test matrix, and go/no-go criteria.
- [`DECISIONS.md`](DECISIONS.md) — durable product/architecture decisions specific to the Presentation Workspace roadmap.

## Relationship to the frozen MVP

This package does **not** change the frozen MVP contract under [`docs/MVP/`](../MVP/README.md).

In particular:

- MVP PPTX ingestion remains a source-extraction path rather than an editable OOXML model;
- MVP PowerPoint integration remains read-only and feature-detected;
- no presentation editor is required to validate the initial rehearsal/live-assist wedge;
- no existing privacy/provider guarantees are weakened.

The user-authorized workspace extends rather than changes the frozen MVP contract. Core can replace text in a supported single-run shape or multiple direct runs whose complete formatting matches and set bold, italic, font size, or solid text color across every run in a structurally simple text shape of up to 128 paragraphs (within the Workspace's 2,000-character target limit); set left, center, right, or justified alignment, a direct left indent from 0 to 144 points, a direct first-line/hanging indent from -144 to 144 whole points, direct line spacing from 1 to 144 whole points, a disc, hollow-circle, square, or dash bullet styles, no-bullet formatting, or Arabic-period automatic numbering across those paragraphs, and direct spacing before or after from 0 to 144 whole points on each paragraph; set direct solid RGB fill or outline colors on supported top-level shapes; create a simple centered text box; edit plain speaker notes with uniform paragraph/run formatting; move or resize a simple unrotated top-level shape or picture within slide bounds; crop a simple picture that has one internal embedded-image relationship and a standard stretch fill; replace that image with a validated single-frame PNG or JPEG up to 4 MiB; delete an eligible top-level shape or picture; duplicate supported top-level shapes and pictures; create a blank slide after the selected slide using the layout from the selected slide or another slide in the current revision; apply a layout already used by another slide in the current revision to the selected slide; duplicate or delete a supported slide; and reorder existing slides. Picture cropping changes only the crop rectangle in the selected slide part, keeps the picture frame and media relationship, and requires the expected crop, geometry, and revision. Image replacement adds a unique media part and relationship, updates only the selected picture reference, keeps its frame and crop, and leaves shared media unchanged. Core validates image bytes and dimensions before committing a new revision. Text-formatting edits preserve per-run properties, apply selected text values to all runs and selected paragraph values to each paragraph, preserve unmodified paragraph properties including left margin, line spacing, and bullets, and require the expected revision and full paragraph/run-style fingerprint; shape-color edits preserve geometry, text, and other shape properties. Both rewrite one slide part and create a new immutable revision. Gradient, pattern, image, and effect-based fills remain read-only. Text-box creation writes a bounded, unfilled rectangle with one text run, allocates a stable object identity, preserves every existing object, and changes only the selected slide part. Blank-slide creation allocates a new OOXML slide identity and part, links only a layout already used in the current revision, and validates that existing slides and package parts remain unchanged. Object deletion and duplication are disabled for placeholders and objects referenced by slide connectors or animation timing. Object duplicates retain package relationships, receive a new stable identity, and stay within slide bounds. Slide duplication retains supported layout, image, hyperlink, and notes relationships; it clones notes for independent editing and fails closed on unhandled dependencies. Slide deletion keeps at least one slide, removes its notes parts, and fails closed when custom-show, section, or package relationships would become stale. Each change is validated and stored as a new immutable revision; users can restore a prior revision, undo to its parent, redo through a unique child, and export the current or original package. Redo stops safely when history branches, leaving the user to choose a revision. Richly formatted or oversized notes, mixed-style, linked, or structurally complex multi-run text replacement, percentage-based or fractional line spacing, custom numbering styles, picture bullets, arbitrary bullet glyphs and custom bullet font/color/size styles, and multi-shape bulk formatting, advanced shape effects, complex picture fills and image treatment, unsupported geometry, additional object types, unused theme-layout discovery or selection, and presentation creation from scratch remain unsupported. Line spacing must use whole-point absolute values from 1 to 144; percentage-based, fractional-point, and malformed line-spacing values remain read-only. Before/after spacing outside the bounded range, percentage-based, fractional-point, and malformed values remain read-only; indent values outside the bounded point range or represented at unsupported precision remain read-only. These narrow operations do not establish general PPTX fidelity or PowerPoint compatibility. Preview, editing, and export remain a research preview pending the user-research, demand, and compatibility evidence in [`ROADMAP.md`](ROADMAP.md) and [`VALIDATION.md`](VALIDATION.md).

The slide-purpose suggestion is never saved as provider output. After review,
the user can correct or confirm one purpose label for a stable slide ID on the
exact current revision. Core stores only that user-confirmed category and
provenance; it stores no slide text or model response. Labels for older
revisions remain available with those revisions and do not carry forward
automatically after edits.

The editor also creates rectangles and ellipses with explicit in-bounds
geometry and direct RGB fill/outline colors. Core assigns a stable identity and
validates the shape, style, slide inventory, and unchanged package parts before
committing its immutable revision.

Settings exposes local structured output, OpenAI Responses Fast or Ultrafast,
Jev via OpenRouter, and installed Nimble/Tev1 models through Ollama's
loopback-only System One endpoint as explicit typed-decision providers. The
Ollama models are not downloaded or launched by the app. The current workspace action
classifies supported text from one selected slide, checks project privacy,
records a content-free run manifest, and returns a suggestion that requires
user review. It does not classify images/diagrams, persist provider results,
or change a deck. A purpose category is stored only after the user explicitly
confirms or corrects it. Semantic accuracy evaluation is still required before broader use or
automation. The separately announced OpenAI Decisions API remains pending its
exact official contract; OpenAI Responses Fast and Ultrafast are interim
transports, not that API.

## Product boundary

### In scope

A focused presentation-preparation editor that supports the high-frequency operations required to stay inside Presenter Copilot:

- view imported slides with high visual fidelity;
- edit text and speaker notes;
- select, move, resize, reorder, duplicate, add, and delete common slide objects;
- add/replace/crop images and diagrams;
- edit common shape and text formatting;
- add simple tables/charts/diagrams through constrained models;
- add/reorder/delete/duplicate slides;
- preserve theme/layout intent where practical;
- perform semantic AI edits through text or voice;
- convert rehearsal discoveries into reviewable presentation changes;
- show source/evidence relationships;
- extend undo/redo to additional edit workflows and presentation-history cases;
- export a usable PPTX and PDF.

### Explicitly not the initial goal

- general-purpose PowerPoint feature parity;
- VBA/macros;
- arbitrary Office add-in execution;
- advanced animation-authoring timelines;
- exhaustive SmartArt authoring;
- full master/theme designer parity;
- every chart subtype and Office-specific editing feature;
- collaborative cloud-office replacement;
- silent destructive normalization of unsupported imported objects.

## Design principle

The presentation is not just a rendered deck and not just an AI-generated outline. It has two linked representations:

1. **Fidelity representation** — enough document structure to render, directly edit, preserve, and export an imported presentation.
2. **Semantic representation** — slide purpose, claims, evidence, narrative role, audience relevance, speaker intent, and rehearsal knowledge.

Direct manipulation, AI editing, and voice editing must converge on the same typed edit-transaction layer. This avoids separate "AI state" and "real document state" drifting apart.

## Strategic hypothesis

The defensible capability is not "generate attractive slides." It is:

> continuously improve the actual presentation using what the system learns from the presenter's own explanations, supporting evidence, audience context, and rehearsal outcomes.

That creates a loop generic slide generators and generic speech coaches do not naturally own.

### Named revision checkpoints

Open History and enter a checkpoint name (up to 80 characters) and optional note
(up to 500 characters), then Save current checkpoint. Each immutable revision has
one label; saving again renames it. Up to 100 active labels are available per deck.
Labels are stored in the project and survive restart. Saving a label leaves the
current revision and PPTX bytes unchanged.

Restore checkpoint selects its exact saved revision through the normal restoration
and retrieval refresh workflow. Remove checkpoint label removes its name and note;
the revision and deck file remain available in history. If another window changes a
label, Reload checkpoints updates its record ownership while keeping your unsaved
name and note. A changed deck requires reloading the presentation before saving a
label for the current revision. Restoring an older checkpoint keeps later revisions
and labels, so subsequent edits can form a branch.
