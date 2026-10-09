# Presentation Workspace Architecture

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

## Architectural objective

Enable high-fidelity editing of imported presentations without collapsing Presenter Copilot's semantic Project Brain into a lossy slide abstraction.

The core rule is a dual representation:

```text
Imported / created presentation
            |
            v
+---------------------------+
| Fidelity Document Model   |
| shapes, text, media,       |
| geometry, theme, relations|
+-------------+-------------+
              |
              | stable IDs / mappings
              v
+---------------------------+
| Semantic Presentation     |
| slide purpose, claims,     |
| evidence, narrative role,  |
| speaker intent, audience   |
+-------------+-------------+
              |
              v
        Project Brain
```

The fidelity model answers "what is physically in the deck and how should it round-trip?" The semantic model answers "what does it mean and why should it change?"

## Major components

```text
PPTX / generated deck
        |
        v
Presentation Importer
        |
        +----> immutable original snapshot
        |
        v
Fidelity Model Store <------> Renderer / Direct Editor
        |
        +--------------------> PPTX Exporter
        |
        v
Semantic Mapper
        |
        v
Project Brain / Claims / Sources / Narrative
        |
        v
Context Builder -> AI Planner -> Typed Edit Plan
                                |
                                v
                         Edit Transaction Engine
                                |
                                +--> Fidelity Model
                                +--> Semantic updates
                                +--> Version history
```

## Immutable original

Every imported presentation must retain an immutable original snapshot.

Reasons:

- recovery from parser/export bugs;
- fidelity comparison;
- preservation of unsupported content;
- explicit "restore original" semantics;
- deterministic round-trip tests.

Normal editing never mutates this snapshot.

Each imported presentation has a Core-owned lineage. The project database
records immutable revision metadata, the hash and size of each package, its
parent revision, and the current revision head. Revision files use generated
names under the project source vault; IPC returns metadata but never local
paths. Original revision 1 points to the exact imported snapshot. A new edit
revision is committed only after the package writer validates the output and
the file is atomically installed. Source deletion removes derived revision
files before deleting lineage metadata.

Parsed slide units also carry their immutable revision ID. Import associates
the initial units with revision 1; re-index parses the verified current
snapshot and atomically replaces only that revision's units. Other revisions'
units remain available to sessions already bound to them. Default retrieval
selects each presentation's current head, while Run, Teach, Challenge, Live
Assist, and debrief retrieval pass their session's bound revision. A committed
revision with no successfully indexed units yields no slide evidence until
Core re-indexes it; old slide text is never substituted as the current deck.

## Stable identity

Slides and editable objects require stable internal IDs independent of their
current order, OOXML relationship paths, and revision content hashes. The
import inventory currently derives those IDs from the document lineage and
unique OOXML slide/shape IDs. Managed edits must preserve existing anchors and
allocate new IDs without reusing retired ones. A source hash identifies the
revision content separately. Independently imported files receive separate
document lineages; matching OOXML IDs alone do not establish cross-import
identity.

Suggested identities:

- `presentation_id`;
- `revision_id`;
- `slide_id`;
- `object_id`;
- `asset_id`;
- `semantic_node_id`;
- `source_binding_id`.

Imported OOXML identifiers and relationship paths remain source anchors and
metadata, not the internal domain IDs themselves.

## Fidelity model

The fidelity model should represent at least:

- slide dimensions;
- slide ordering;
- master/layout/theme references;
- object z-order;
- geometry/rotation;
- text runs and paragraphs;
- fonts/style references;
- fills/strokes/effects for supported primitives;
- images/media references;
- groups;
- tables/charts for supported tiers;
- speaker notes;
- hyperlinks;
- OOXML passthrough references for unsupported/opaque features.

The model should avoid forcing every OOXML construct into a fully editable semantic shape.

## Opaque preservation

Unsupported imported features should be represented as opaque preservation nodes whenever possible.

An opaque node may expose only:

- position/bounds;
- preview/render surface;
- move/resize/delete where safe;
- original package parts/relationships needed for export;
- compatibility metadata.

This is preferable to flattening or deleting unsupported content.

## Semantic presentation model

The semantic model is intentionally higher level.

Suggested entities:

### PresentationNarrative

- objective;
- target audience;
- desired decision/action;
- thesis;
- narrative arc;
- constraints.

### SlideSemantics

- purpose;
- narrative role;
- primary takeaway;
- claims;
- audience relevance;
- evidence coverage;
- complexity/density markers;
- appendix/main status.

### Claim

- normalized claim text;
- claim type: fact / estimate / opinion / recommendation / assumption;
- object/text-span origin;
- evidence bindings;
- support status;
- user/AI provenance.

### SpeakerIntent

- preferred explanation;
- notes;
- practiced variants;
- strong rehearsal excerpts;
- style constraints.

The semantic model can be recomputed or partially refreshed; the fidelity document remains authoritative for physical slide state.

## Edit transaction engine

All mutation paths must converge on typed edit transactions:

- direct manipulation;
- keyboard commands;
- inspector changes;
- AI text commands;
- AI voice commands;
- rehearsal-derived proposals;
- bulk operations.

Example conceptual transaction:

```json
{
  "transaction_id": "...",
  "base_revision_id": "...",
  "operations": [
    {
      "type": "replace_text",
      "object_id": "...",
      "range": { "start": 0, "end": 42 },
      "text": "..."
    }
  ],
  "origin": "ai_proposal",
  "reason": "rehearsal_finding",
  "evidence_refs": ["..."]
}
```

The concrete schema should be versioned and implementation-language neutral.

## Current implementation boundary — 2026-09-30

The current editor supports replacement and direct formatting of one run in a supported slide shape,
solid RGB fill and outline color changes on supported top-level shapes,
edits to plain speaker notes whose paragraphs have uniform formatting and at
most one run each, movement/resizing of simple unrotated top-level shapes or
pictures, deletion or duplication of eligible top-level shapes or pictures,
bounded source cropping and PNG/JPEG image replacement for simple pictures,
explicitly placed PNG/JPEG picture creation, simple rectangle/ellipse creation,
and slide reordering. Each
operation includes the expected current revision and target text, geometry,
crop, or a complete permutation of stable slide IDs.
Geometry must remain inside the slide bounds. Deletion and duplication exclude
placeholders and objects referenced by slide connectors or animation timing.
Picture cropping is limited to a direct slide-level picture with a simple
stretch fill, one internal image relationship, and a valid crop rectangle.
Core verifies the expected crop and geometry, preserves the image media and
relationship parts, changes only that slide part, and re-inspects the output
before committing the immutable revision.
Image replacement is limited to one decoded single-frame PNG or JPEG up to
4 MiB and 20 megapixels. Core creates a unique media part and slide relationship,
retargets only the selected picture, retains its geometry and crop, and leaves
the old image untouched for other pictures that share it. Every unmodified
package part is checked for byte-identical content.
Picture creation uses the same bounded, fully decoded PNG/JPEG validation.
The renderer proposes a centered size that fits within half the slide while
preserving the source image proportions; users can edit its x, y, width, and
height in inches, and Core independently enforces positive in-bounds geometry.
Core adds a fresh OOXML picture anchor, private media part, and slide image
relationship, records optional alternative text, and verifies the new object,
image bytes, relationship, content type, and unchanged package parts before
committing.
Duplication allocates a unique OOXML shape ID, preserving the existing package
relationships and deriving a new stable object ID from that anchor. Core
modifies only the affected slide/notes XML part or the `p:sldId` ordering in
`ppt/presentation.xml`, validates the generated package, commits a new
immutable revision, and the renderer requests revision-scoped re-indexing.
Slide duplication inserts a new stable slide ID after the selected slide,
retains the source slide's layout, image, and supported hyperlink relationships,
and clones the notes XML and relationship part so later notes edits remain
independent. Unknown slide or notes relationships fail closed. The writer adds
the new slide and optional notes content-type declarations and presentation
relationship; it leaves existing slide and notes parts unchanged.
Slide deletion removes the selected slide, its notes parts, presentation
relationship, and content-type declarations only after confirming that no
custom-show, section, or package relationship points to the slide. It keeps one
slide and preserves media parts because they may be shared. Remaining slide
inventories must pass unchanged validation before the revision commits.
Direct text formatting supports bold, italic, font size from 6 to 96 points,
and solid RGB text color across every direct run in a
structurally simple text shape of up to 128 paragraphs (within the Workspace's 2,000-character target limit). It also supports left, center, right, or justified
paragraph alignment, a bounded 0–144 point left indent, a signed -144–144 point first-line/hanging indent, whole-point line spacing from 1 to 144 points, a disc, hollow-circle, square, or dash bullet styles, no-bullet formatting, or Arabic-period automatic numbering across those paragraphs, and before/after spacing from 0 to 144 points. Each request
supplies the current text, revision, and
fingerprint covering full paragraph properties and every direct run's properties. Core edits only the
requested direct properties, preserves unrelated properties and per-run
style, validates the rewritten slide, and commits an immutable revision. Text
replacement supports multiple direct runs only when their complete run
properties match; Core collapses them into the first run and preserves its
formatting. Mixed-style, linked, and structurally complex multi-run text
remains read-only. Shape color changes require the expected revision and a
fingerprint of the shape properties; they rewrite only the selected slide part
and retain geometry, text, other shape properties, and package relationships.
Gradient, pattern, image, and effect-based fills remain read-only. The current
creator adds one centered, unfilled text box
with a single run and no package relationships. Blank-slide creation inserts a
new slide after the selected slide, with a fresh slide identity and the layout
relationship from the selected slide or another slide in the current revision.
Existing-slide layout application changes only the selected slide's layout
relationship to one already used in the current revision. The writer verifies
the resulting layout target, slide order, object inventory, speaker notes, and
unchanged package parts. A no-op creates no revision; a change enters normal
history and retrieval re-indexing. Applying a layout can reposition
placeholders, so the user reviews the rendered preview and can undo the change.
Mixed-style, linked, or structurally complex
multi-run text replacement, percentage-based or fractional line spacing, picture bullets, custom numbering, arbitrary bullet glyphs, and custom bullet font/color/size styles, and multi-shape bulk formatting,
advanced shape fill or line effects, complex picture fills and image treatment, rich
notes, grouped/rotated/flipped or otherwise
unsupported geometry, additional object types, unused theme-layout
discovery/selection, presentation creation from scratch, and other object/layout
operations remain outside this boundary. The UI's typed
slide-purpose suggestion is review-only and is not an edit transaction. A
separate semantic record may store a category only after explicit user
confirmation or correction; it is keyed by exact revision and stable slide ID,
contains no slide text or provider response, and is never copied to another
revision automatically.

Simple shape creation accepts a rectangle or ellipse, positive slide-bounded
geometry, and direct solid RGB fill and outline colors. Core allocates a fresh
OOXML shape anchor and stable object ID, writes only the selected slide part,
then verifies the shape type, styles, geometry, object inventory, and every
untouched package part before committing the immutable revision.

## Transaction properties

Transactions should be:

- validated before mutation;
- atomic at presentation-revision level;
- reversible;
- attributable to user/direct/AI/rehearsal origin;
- conflict-aware using `base_revision_id`;
- bounded in target scope;
- capable of reporting compatibility impact.

## Revision model

Prefer immutable logical revisions over in-place historical mutation.

A revision should include or reference:

- parent revision;
- transaction sequence;
- current fidelity model generation;
- semantic model generation/fingerprint;
- creation reason;
- timestamp;
- ready/draft status where applicable.

Storage can use snapshots plus deltas internally; the domain contract should not require replaying unbounded history for normal startup.

## Concurrency/conflicts

Initial desktop product may be single-user, but asynchronous AI planning can still conflict with direct edits.

Rule:

> AI plans execute against the revision they were planned from.

If the current revision changed materially before apply:

- revalidate object IDs and preconditions;
- auto-rebase only trivial non-overlapping edits;
- otherwise mark the proposal stale and request regeneration/review.

Never silently apply a broad stale plan to a changed deck.

## Rendering strategy

The desktop research preview currently uses `@aiden0z/pptx-renderer@1.3.0` in
a separate hidden Electron `BrowserWindow`. Core supplies the verified source
snapshot as a bounded `ArrayBuffer`; the preview process receives no
filesystem path. Its preload exposes only the typed open, render, release, and
close protocol. The child window has sandboxing and context isolation enabled,
Node integration disabled, a restrictive content security policy, denied
permissions, blocked network requests in packaged mode, and denied navigation
and window creation. It renders one slide at a time with lazy slide/media
loading and returns a bounded PNG plus supported text candidates. The main
renderer maps those candidates to Core-owned stable identities; Core remains
the edit and export authority.

Preview inputs are limited to 50 MiB. Open and render IPC requests have
120-second deadlines; closing the preview destroys the child and its parsed
document. When the isolated renderer cannot open a file, the UI falls back to
the legacy `pptx-glimpse@5.3.1` worker and displays an experimental-preview
warning. The UI smoke asserts that the candidate path handles its fixture
without taking this fallback. Responsiveness and peak memory at the 50 MiB
limit have not yet been measured, and neither renderer establishes PowerPoint
visual parity.

The architecture still requires:

- deterministic mapping from fidelity nodes to canvas elements;
- object hit testing/selection;
- high-DPI rendering;
- text metrics close enough to detect layout drift;
- fallback previews for unsupported objects;
- comparison against Office/LibreOffice/PDF reference renders in test tooling.

Do not make the semantic model the rendering source of truth for imported decks.

## PPTX package strategy

The exporter should prefer preservation over regeneration where practical:

- retain untouched package parts verbatim when possible;
- rewrite only relationships/parts affected by edits;
- preserve unknown XML/extensions unless the edit requires replacing their parent structure;
- keep content types/relationships consistent;
- validate output package structure before returning it to the user.

A fully regenerated PPTX is acceptable only when the user created the deck natively in Presenter Copilot or explicitly accepts normalization.

## Project Brain synchronization

Edits may invalidate semantic/evidence relationships.

Examples:

- replacing text invalidates claim extraction for that span;
- deleting a slide stales slide-bound claims/notes;
- moving a claim between slides updates slide context but not its evidence source;
- accepting a rehearsal-derived rewrite preserves a link to the originating rehearsal event.

Semantic refresh should be incremental where possible and never reinterpret AI-generated wording as user-authored evidence.

## Local-first boundary

By default, the following stay local:

- original PPTX;
- fidelity model;
- slide renders/previews;
- edit history;
- assets;
- source/evidence bindings;
- direct editing;
- PPTX export.

Remote reasoning receives only bounded context permitted by the existing provider/privacy execution boundary. Binary presentation packages and proprietary media are not uploaded merely because AI editing is enabled.

## Security boundaries

- imported OOXML is untrusted data;
- no macros/add-ins execute;
- external relationships must not trigger arbitrary fetches automatically;
- embedded files are treated as inert attachments unless explicitly supported;
- image/media decoders should be bounded and isolated appropriately;
- AI cannot issue arbitrary filesystem/package operations; it emits typed domain edits only;
- renderer authority remains allowlisted through existing Electron boundaries.

## Migration from current MVP

Do not retrofit editable presentation semantics into the M1 source-ingestion tables.

Instead introduce a separate presentation-document subsystem and link it to existing source/provenance IDs.

Suggested migration path:

1. continue using current PPTX parser for retrieval while workspace prototype is isolated;
2. add fidelity importer/render-only model;
3. establish stable slide mapping between source ingestion and fidelity model;
4. add edit transactions;
5. make semantic extraction consume the current editable revision;
6. retire duplicate PPTX extraction paths only after parity/provenance tests pass.

## Open architecture questions

1. Best OOXML library strategy: extend `python-pptx`, use direct package/XML manipulation, introduce a dedicated service/library, or hybrid.
2. Best canvas/rendering stack for matching PowerPoint text/layout sufficiently well.
3. How much unsupported OOXML can be preserved verbatim after parent-object edits.
4. Whether Office automation should ever be used as an optional validation/export helper; it must never become a required runtime dependency.
5. Snapshot-vs-delta thresholds for revision storage.
6. Best internal representation for native charts and diagrams across PPTX export and HTML/canvas rendering.
7. Whether collaborative editing is ever strategically justified; do not design the initial storage model around it prematurely.


### Reviewed slide takeaways

Project schema 17 adds `presentation_slide_takeaways`, keyed by presentation,
immutable revision and stable native slide ID, with a composite revision ownership
foreign key, unique optimistic record token and 1000-character text bound. Empty
records explicitly clear intent and stop inheritance. Reads follow only parent
lineage (100 ancestors), mark inherited values provisional and report missing bounded
history. Core exposes `get_slide_takeaway` and `save_slide_takeaway`; both verify
the managed native source, selected ordinal/ID and current head. Save requires
review acknowledgment and checks the token in an immediate transaction. Deck review
reuses native inventory and reads takeaways without extra package inspection.
Takeaways are author intent; this increment does not send them to providers or
rehearsal automatically. Narrative finding transfer is a scoped GUI draft proposal.
