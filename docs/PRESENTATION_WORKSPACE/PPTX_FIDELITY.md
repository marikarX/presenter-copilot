# PPTX Fidelity and Compatibility Strategy

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


## Goal

Imported PPTX files should remain usable PowerPoint documents after normal Presenter Copilot editing. The workspace does not need to edit every Office feature, but it must not silently destroy features it does not understand.

The compatibility strategy therefore prioritizes:

1. preserve;
2. render;
3. edit common content;
4. warn before normalization;
5. validate round-trip output.

## Fidelity classes

Every imported object/feature should be classified into a support tier.

### Tier A — native editable

Presenter Copilot understands and can safely round-trip the feature.

Initial targets:

- slide order and dimensions;
- text boxes/placeholders;
- text runs/paragraphs;
- common fonts/alignment;
- common solid fills/strokes;
- common basic shapes;
- images;
- speaker notes;
- hyperlinks;
- object geometry/z-order;
- groups when their children are supported.

### Tier B — constrained editable

Presenter Copilot understands a bounded subset and may restrict operations.

Candidates:

- tables;
- charts;
- connectors;
- theme/layout changes;
- diagrams;
- grouped mixed-content objects.

Example: a chart may allow data/title/legend changes while preserving unsupported styling as opaque package data.

### Tier C — preserve + limited transform

Presenter Copilot can retain/render the object but cannot safely edit its internal semantics.

Possible operations:

- select;
- move;
- resize where safe;
- hide/delete;
- duplicate;
- preserve on export.

Candidates:

- SmartArt not yet modeled;
- uncommon charts;
- equations;
- 3D models;
- media;
- specialized Office drawing extensions.

### Tier D — opaque preserve only

The feature/package part must be retained untouched unless the user explicitly chooses normalization/removal.

Candidates:

- unsupported extension XML;
- embedded OLE content;
- arbitrary custom XML parts;
- unknown vendor extensions;
- non-executed macro payloads in macro-enabled documents if that format is eventually admitted.

Initial workspace support may reject macro-enabled formats rather than preserve them.

## Import behavior

On import:

- snapshot the exact original file;
- validate ZIP/package structure and bounded resource usage;
- build the fidelity model;
- classify unsupported features;
- render previews;
- record a compatibility report;
- do not rewrite/export simply as a side effect of opening the file.

Compatibility report should be concise for the user but detailed in diagnostics/tests.
The current import inventory reports drawing-object counts for shapes,
pictures, graphic frames, connectors, and groups. These are structural counts;
they do not measure whether the preview matches PowerPoint or classify every
feature inside those objects.

Example user summary:

```text
This deck is editable.
42 slides
318 fully editable objects
7 preserved objects with limited editing
0 export blockers
```

## Preservation rule

If Presenter Copilot does not need to change an OOXML part to satisfy an edit, prefer retaining the original part and relationships rather than regenerating it.

This is especially important for:

- masters/layouts/themes;
- embedded charts/workbooks;
- SmartArt;
- custom XML/extensions;
- media;
- notes metadata;
- external relationship metadata.

## Normalization boundary

Some operations may require converting an object from an unsupported representation into a supported native representation.

Normalization must be explicit when it can cause fidelity loss.

Example:

```text
This SmartArt graphic is preserved but not directly editable.
Converting it to Presenter Copilot shapes will make its text/layout editable,
but some PowerPoint SmartArt behavior will be lost.

[Convert a copy] [Keep preserved]
```

Never normalize an entire deck merely because one object is unsupported.

## Export modes

### Standard PPTX export

Default. Preserve untouched unsupported content and write supported edits back into a valid PPTX.

### PDF export

Visual delivery/export when editability is not required.

### Normalized PPTX

Future explicit option. Converts more content into Presenter Copilot-supported structures. Must clearly disclose fidelity tradeoffs.

The original import remains recoverable regardless of export mode.

## Round-trip fidelity definition

Round-trip correctness includes more than "PowerPoint opens the file."

Test dimensions:

- package validity;
- slide count/order;
- object count/type where expected;
- text preservation;
- notes preservation;
- hyperlinks;
- image/media identity;
- geometry;
- z-order;
- fonts/styles;
- theme/layout references;
- unsupported-part preservation;
- visual render similarity;
- edited-object correctness;
- no unintended changes on untouched slides.

## Golden corpus

The locally cached sample is tracked by [`CORPUS.md`](CORPUS.md). It currently
contains 23 Zenodo CC BY 4.0 records plus ten Internet Archive PPT-Eval sources
whose Public Domain Mark 1.0 metadata is rechecked. On 2026-10-01 Core
inventoried all 33 files; all were parser-supported and none failed structural
validation. The six prior structural rejections were false positives caused by mutually exclusive
`mc:Choice` / `mc:Fallback` branches and pictures nested in opaque OLE
graphic-frame payloads. Core now inventories one supported compatibility
branch, leaves all source branches unchanged, and marks alternate-content
objects read-only. Duplicate IDs among effective drawing objects still fail
closed. This is an initial research set, not the permanent golden corpus
described below. Embedded media rights, visual references, and additional
compatibility classes still need review.

Core's isolated text-edit/re-index/export/reopen/restore smoke passed on 29
decks. It verified that the edited slide is the only package part whose
uncompressed bytes changed and that the restored PPTX is byte-identical to its
source. Four inventoried decks had no text target meeting the editability,
geometry, and novel-token requirements. A guarded Windows run opened 27 of 29
edited exports in PowerPoint with matching slide counts and unchanged hashes;
two decks with external non-hyperlink relationships were skipped. The optional
pixel check renders source, edited, source, and edited; it masks variation
within either same-state pair. An initial full 33-deck run reused one PowerPoint
process and returned 9 review cases. The runner now starts a fresh process per
deck; the isolated run returned 21 unmasked passes, 5 masked passes, 1 review
case, and 2 external-relationship skips. All seven new records passed without
masking. The only remaining case is record `3996727`: the synthetic text edit
wraps the already-full-width title outside its shape and overlaps the next
bullet, with no untouched-slide differences. Its export is structurally
correct, but the resulting layout needs correction before the visual gate can
close. See [`CORPUS.md`](CORPUS.md) for current run evidence.

The renderer comparisons above this heading were run against the then-current
26-deck subset before the corpus grew to 33. The full 33-record in-app preview
comparison completed on 2026-10-01; its isolated metrics and limitations are
recorded below.

Create a permanent PPTX compatibility corpus with licensing-safe fixtures covering:

- simple corporate deck;
- theme/master-heavy deck;
- many fonts/text styles;
- image-heavy deck;
- charts/tables;
- groups/connectors;
- SmartArt;
- notes/hyperlinks;
- unusual aspect ratios;
- hidden slides;
- section metadata if supported;
- embedded media/objects;
- malformed-but-openable edge cases;
- large deck near product limits.

Each fixture should have:

- original file hash;
- expected feature inventory;
- reference renders;
- import expectations;
- no-op round-trip expectations;
- specific edit scenarios;
- expected warnings.

## No-op round-trip gate

Before broad editing ships, opening and exporting a supported deck without edits should produce no material visible differences and no loss of preserved unsupported features.

Byte equality is not required because ZIP/package metadata may change; semantic and visual equality is the requirement.

## Visual comparison

Automated render comparison should use multiple signals rather than raw pixel equality alone:

- per-slide rendered-image similarity;
- text bounding-box comparison;
- object geometry comparison;
- missing/extra region detection;
- font substitution detection;
- human review for threshold failures.

Reference rendering should preferably include PowerPoint on Windows in CI/lab infrastructure where licensing and automation allow, with a second renderer such as LibreOffice only as a supplemental signal, not the source of truth for PowerPoint compatibility.

On 2026-09-30, after the compatibility traversal change and corpus expansion,
the desktop app's `pptx-glimpse@5.3.1` browser worker was compared against
PowerPoint on the 26-deck corpus. Twenty-four decks were renderable in both
paths; two were skipped for external relationships. All 386 compared slides
had stable pixel differences after masking repeated PowerPoint-render
instability. The median changed-pixel rate was 16.2330%, median normalized RGB
MAE was 3.0356%, and median PSNR was 17.404 dB. A human spot-check confirmed
text placement and wrapping differences. This is a release blocker, not an
accepted similarity threshold. See the [corpus validation](CORPUS.md) for
scope and limitations.

An exploratory evaluation also checked the browser entry of
`@office-kit/pptx-preview@0.12.0`. On the same 14 decks (218 slides) that it
successfully rendered and the current worker rendered, the candidate's median
changed-pixel rate was 26.9837% and median normalized RGB MAE was 3.4716%; the
current worker measured 25.5726% and 2.8869% on that subset. The candidate
failed to render two other Core-comparable decks. The harness removed hyperlink
targets from SVG anchors before placing each slide in a non-interactive image
and blocked network requests; no source PPTX was changed and no slide text or
render images were retained. This experimental package did not improve the
same-subset median results and is not an approved replacement. Its declared
Node.js minimum is 22.18, above this evaluation host's 22.16 runtime. See the
[package documentation](https://github.com/office-kit/pptx#readme) for its
experimental status and scope.

On 2026-09-30, `@aiden0z/pptx-renderer@1.3.0` (Apache-2.0) was compared with
`pptx-glimpse@5.3.1` using the original 23-deck manifest and guarded PowerPoint
reference-render procedure. Both rendered 21 decks (353 slides) and skipped
the same two decks with external non-hyperlink relationships. The candidate's
median changed-pixel rate was 16.9803%, median normalized RGB MAE was 2.3327%,
and median PSNR was 18.878 dB; the current renderer measured 17.1965%, 3.1689%,
and 17.242 dB. The candidate had lower per-deck median changed-pixel rates on
15 of 21 decks. The first capture attempt used the outer container size instead
of the rendered slide size; those results were discarded. Reported figures
use corrected intrinsic slide scaling. The evaluation blocked external
browser requests, retained no corpus-wide images, emitted no slide text, and
left source files unchanged. A separate one-deck visual spot-check saved
temporary PNGs under ignored `.local` for review.

On the expanded 26-deck corpus, the candidate rendered the same 24 decks and
386 slides as the current renderer; both skipped two decks with external
non-hyperlink relationships. The candidate's median changed-pixel rate was
16.0512%, median normalized RGB MAE was 2.2455%, and median PSNR was 19.076 dB.
The baseline renderer measured 16.2330%, 3.0356%, and 17.404 dB on that set.
Human review still found visible text-style differences, so these results do
not pass a release threshold.

On 2026-09-30, the integrated hidden-window preview path was compared against
PowerPoint again after bounded local-font detection and substitution were
added. The harness now uses the same `parseZipLazyMedia` / `buildPresentation`,
`PptxViewer`, and font resolver as the primary preview, with the preview CSP
and external requests blocked. It rendered 24 of 26 decks (386 slides), skipped
the same two external-relationship cases, and had no structure/render failures.
PowerPoint rerenders were unstable on 148 slides. Median changed-pixel rate
was 16.0620%, median normalized RGB MAE 2.2456%, and median PSNR 18.971 dB.
These metrics are effectively unchanged from the candidate run without local
font substitutions; font fallback improves transparency and missing-font
handling, but does not resolve visual fidelity. No slide text or rendered
images were retained. This remains a release blocker.

On 2026-10-01, the production preview enabled the in-memory SmartArt cached-
image relationship repair and a restricted full-canvas `useBgFill` repair.
SmartArt repair fixed 52 image references across two decks. Paired
`smartart-only` and `all` corpus runs normalized 15 full-canvas shapes that had
no direct fill or an explicit `noFill`; 14 slides improved and none regressed.
The median changed-pixel rate moved from 16.0620% to 15.5916%; median
normalized RGB MAE remained 2.2403% and PSNR remained 19.025 dB. The broad
rewrite remains unsafe because shapes with explicit solid fills must be left
untouched. Across 24 of 26 decks (386 slides), two were skipped for external
relationships and no render or structure failures occurred. PowerPoint
rerenders were unstable on 148 slides, and all 386 slides still had stable
pixel differences. No slide text or rendered images were retained. The repair
is preview-only and does not change the source PPTX; this result does not clear
the visual-fidelity release gate.

After expanding the corpus, the per-deck isolated comparison ran on all 33
records on 2026-10-01. It compared 31 decks (613 slides), skipped two external-
relationship decks, and had no import or render failures. Every compared slide
still had stable pixel differences; 21 PowerPoint slides varied across the
repeat renders. Median changed-pixel rate was 14.4983%, median normalized RGB
MAE was 2.9514%, and median PSNR was 17.894 dB. A prior shared-process run
reported 180 unstable slides; fresh PowerPoint instances per record reduced
that render-order noise, but did not remove the stable preview mismatch. No
slide text or renders were retained. There is no accepted fidelity threshold;
this remains a release blocker.

A targeted follow-up fixed one reproduced preview mismatch on record `3996727`:
the renderer's `overflow-wrap:anywhere` and inherited `line-break:anywhere`
could split a horizontal title inside its final word, unlike PowerPoint. The
preview now uses word-level wrapping for horizontal text with whitespace
between words and preserves the prior line-break behavior for vertical and
East Asian text. The full corpus medians remain effectively unchanged, and
the source title still overflows into the following bullet. This is a narrow
renderer correction; it does not clear the edited-export review failures or
establish broad PowerPoint fidelity.

A second targeted follow-up addressed the missing translucent title band on
record `90000004`. The slide's centered-title placeholder has no direct fill;
its linked layout placeholder has a direct `solidFill` with `bg1` at 72%
alpha. The preview-only compatibility pass now copies a direct solid fill from
one unambiguous matching layout placeholder when the slide placeholder has no
explicit fill. It matches by exact placeholder index, or by type when neither
placeholder has an index, and requires compatible slide/layout color-map
overrides. Explicit slide `noFill`, unmatched or ambiguous placeholders,
external or invalid layout relationships, and non-solid layout fills are left
unchanged. Layout XML and source PPTX bytes are not modified.

The full 33-record comparison ran after this change: 31 decks / 613 slides
compared, two external-relationship decks skipped, zero failures, and 21
unstable PowerPoint renders. Four decks received seven inherited fills. Paired
baseline/current runs on those four decks showed no median changed-pixel
regressions; median RGB MAE and PSNR were level or improved on each deck. On
record `90000004` slide 1, RGB MAE fell from 19.3056% to 15.6562%, while the
changed-pixel rate moved only from 98.7653% to 98.7473%. Its deck-wide median
changed-pixel rate remains 96.5028%; the record `90000008` outlier also
remains unresolved. This bounded repair improves a specific inherited fill,
but does not clear the visual-fidelity release gate.

A retained one-slide visual spot-check of record `90000004` confirms that the
inherited title band is visible after the fill repair. It also isolates a
separate remaining mismatch: PowerPoint applies `a:duotone` and `a:lum` image
effects to the master symbol-strip pictures, while the candidate preview leaves
them black on white; the layout artwork also has an `a:duotone` effect. The
source deck is public-domain; one-slide QA renders are local-only under the
ignored `.local/preview-debug/90000004` directory.

The first bounded preprocessing prototype was inert: it processed two master
pictures but produced identical slide hashes. Inspection confirmed that the
product uses `parseZipLazyMedia` and that the renderer resolves images lazily by
relationship target. The prototype changed the eager media map, which this
preview path does not use for those images; it was removed.

On 2026-10-01, a second, preview-only compatibility pass was verified against
the lazy media path. It supports direct `a:duotone` effects followed by optional
`a:lum` for bounded embedded PNG/JPEG images when both colors and their
supported theme modifiers can be resolved. It creates a private in-memory PNG
alias, updates only the parsed preview relationship, and removes the baked
effects from that in-memory XML copy so the renderer can consider its bounded
picture-plane 3D path. Original PPTX bytes and exports remain unchanged.
Ambiguous shared relationships, unsupported modifiers, non-raster media, and
images above the decode or pixel budgets are left unchanged. The pixel
transforms follow the documented DrawingML meanings for tint, saturation, and
luminance ([tint](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.tint?view=openxml-3.0.1),
[saturation modulation](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.saturationmodulation?view=openxml-3.0.1),
[luminance](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.luminanceeffect?view=openxml-3.0.1));
browser rasterization remains an approximation of PowerPoint.

The pass transformed three references on record `90000004` and skipped none.
Paired isolated runs used the same PowerPoint capture: with effects disabled,
the deck medians were 96.5028% changed pixels, 18.8637% normalized RGB MAE,
and 9.2885 dB PSNR; with effects enabled they were 96.6150%, 14.3155%, and
11.715 dB. Slide 1 MAE improved from 15.6562% to 11.0732% and PSNR from
11.683 to 14.991 dB, while the changed-pixel rate moved from 98.7473% to
98.7422%. Visual review found the large artwork substantially closer in tone;
the symbol strip remains more opaque than PowerPoint and the image bevel is
still not matched.

The full 33-record corpus was rerun in `all` mode: 31 decks / 613 slides
compared, two external-relationship decks skipped, no failures, and 21 unstable
PowerPoint renders. Only record `90000004` used this effect lane; all other
records were unchanged. Full-corpus medians remained 14.4983% changed pixels,
2.9514% normalized RGB MAE, and 17.894 dB PSNR. all 613 comparable slides
still had stable differences. This bounded improvement does not clear the
visual-fidelity release gate.

A focused inspection of record `8376688` (`06-git-systems.pptx`, SHA-256
`AA873C7C9D67ED4635CFB4AAA107F1894130C3E1ADF3F7DD43DB9D0DEDE7EE85`), slide
17, traced its narrow blue separator to inherited image-fill handling. OOXML
shapes 55 and 56 use `a:grpFill` inside group 54, whose fill is a tiled
`image2.jpeg` relationship at 100% scale and 57% alpha. In
`@aiden0z/pptx-renderer@1.3.0`, an inherited `blipFill` resolves to an empty
shape-fill value; the shape then falls back to its theme fill reference, which
renders as accent blue. This confirms the cause on this slide, not all grouped
image fills. The renderer DOM does not expose stable OOXML shape IDs. A
temporary pattern overlay restored the torn outline on a source-mutated
diagnostic deck, but it stretched the image and did not verify the original
tile alignment or opacity; source-fill mutations also changed a neighboring
group. No product fix was accepted or shipped, and the source PPTX remains
unchanged.

On 2026-10-01, a second targeted follow-up traced record `90000008`'s olive
background fallback to a backmost, full-canvas rectangle with `useBgFill="1"`
and a theme `fillRef`; PowerPoint uses the slide's textured background image.
The preview now removes only the style fill reference when that exact full-canvas
shape has no direct fill, keeping the `useBgFill` semantics and all other style
references. It also resolves `bg1`/`tx1` aliases through the effective master
color map and supports bounded `lumMod` transforms when baking compatible
duotone raster media into private preview-only aliases. Open XML documents the
[color mapping](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.colormap?view=openxml-3.0.1)
and [luminance modulation](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.luminancemodulation?view=openxml-3.0.1)
semantics. Original PPTX bytes and exported files are not modified.

On record `90000008`, the compatibility report removed eight background style
fill references and transformed 18 duotone image references. Paired runs over
all 24 slides show the median changed-pixel rate unchanged at 76.5688%, while
median normalized RGB MAE improved from 16.7522% to 5.0290% and PSNR from
10.79 to 21.32 dB. Twelve slide MAEs improved, twelve were unchanged, and none
regressed. The remaining changed pixels show that color similarity alone does
not establish correct texture, layout, or text rendering.

The full 33-record corpus was rerun with this compatibility pass enabled: 31
decks / 613 slides compared, two external-relationship decks skipped, zero
failures, and 21 unstable PowerPoint renders. The only deck whose median MAE
changed was `90000008`; full-corpus medians were 14.4983% changed pixels,
2.9514% normalized RGB MAE, and 18.061 dB PSNR. all 613 slides still had
stable differences, so preview fidelity remains a release blocker. A one-deck visual
inspection remains under ignored `.local/preview-debug/90000008`; no corpus-wide
images or slide text were retained.

A later inspection of record `90000004` found that PowerPoint renders two
master symbol-strip pictures with an exact orthographic-front, `chilly` light,
`clear` material and bevel profile. For only that explicit profile, the
preview-only raster compatibility pass now multiplies picture alpha by 20%
after applying the already-supported duotone/luminance color transforms. It
requires direct top-level pictures, explicit no-fill and empty effects, exact
zero rotation, and matching material/light properties. If a shared image
relationship has a different per-picture profile, it is skipped. This creates
only a private preview alias; the source PPTX and exported files remain intact.

The paired 32-slide `90000004` run had no unstable PowerPoint captures. Median
RGB MAE improved from 14.3155% to 7.0297% and PSNR from 11.715 to 15.8215 dB;
MAE improved on all 32 slides and regressed on none. Median changed-pixel rate
moved from 96.6150% to 96.6146%; three individual slides increased by at most
0.0006 percentage points. A new 33-record corpus run still compared 31 decks /
613 slides, skipped two external-relationship decks, failed on none, and had
21 unstable PowerPoint captures. Corpus medians were 14.4983% changed pixels,
2.9402% normalized RGB MAE, and 18.267 dB PSNR. all 613 slides still had
stable differences, and the cross-run corpus comparison includes renderer/PowerPoint
variation; the targeted stable 32-slide comparison is the clearer evidence
for this narrow compatibility rule. The fidelity release gate remains open.

The candidate is now integrated as the primary research preview in a hidden
Electron `BrowserWindow` with context isolation and sandboxing enabled, Node
integration disabled, restrictive CSP, denied permissions, blocked external
requests in packaged mode, and no renderer-supplied file paths. The parent
accepts at most 50 MiB of verified snapshot bytes, applies 120-second request
deadlines, captures bounded PNG output, and destroys the child on close or
failure. Lazy slide and media loading are enabled. The 15-flow Electron UI
smoke asserts that the bundled candidate handles its fixture without using
the legacy `pptx-glimpse` fallback.

A 4.9 MB, 32-slide headless probe opened in 143 ms and took 2.797 seconds to
render and screenshot all slides sequentially (16 ms median, 26 ms p95 per
slide); this did not measure Electron input responsiveness. The new
`pnpm profile:workspace-preview` harness measures timings and Electron process
memory for the packaged preview path without retaining slide text or rendered
images. On this Windows host, a 21,747,152-byte, 48-slide corpus deck opened
with its first preview in 1,726 ms; slide 24 and slide 48 rendered in 39 ms and
34 ms. The isolated preview renderer peaked at 105,940 KiB private bytes and
209,792 KiB working set. Total Electron private bytes peaked at 791,848 KiB.

A valid 52,412,416-byte fixture (16 KiB below the 50 MiB limit) based on the
same deck opened in 2,160 ms; slide 24 and slide 48 rendered in 33 ms and
35 ms. Its preview renderer peaked at 185,680 KiB private bytes and 285,512
KiB working set; total Electron private bytes peaked at 901,308 KiB (about
880 MiB) and total working set at 1,056,440 KiB (about 1,032 MiB). The fixture
adds an unreferenced inert package part, so it exercises the input-size limit
without modeling large-media expansion. In both runs, the preview renderer
process was absent after close. The renderer clears its temporary source-byte
buffer after the isolated preview accepts the deck, while the main process
clears its IPC copy when opening succeeds or fails. These are sampled results
from one developer host; they do not establish a general memory ceiling or
input responsiveness, and timeout/cancellation paths remain unforced release
gates. See the [project source](https://github.com/aiden0z/pptx-renderer) and
[package license/version](https://www.npmjs.com/package/@aiden0z/pptx-renderer).

A local-only font-buffer probe on 2026-09-30 used the installed Windows Arial
and Calibri fonts for record 4709936 (18 slides). Per-slide median normalized
RGB MAE changed from 2.42645% without font buffers to 2.5859% with them; median
changed-pixel rate moved from 6.48455% to 6.4345%. This one-deck result does not
show a material improvement. The temporary harness was removed, the source deck
was not changed, and no Windows font files were added to the product.

A separate `pptx-glimpse@5.3.1` probe on the same record compared the current
path-based SVG text output with native SVG text output. All 18 slides had
identical changed-pixel, normalized RGB MAE, and PSNR metrics between the two
modes. The experiment changed only the temporary renderer setting; the product
remains on path-based text output. No slide text or rendered images were
retained.

An isolated `@slideglance/core@0.4.2` Node-API comparison on that same 18-slide
record measured 6.0891% median changed pixels and 2.2829% median normalized RGB
MAE, versus 6.48455% and 2.42645% for the current preview. This small one-deck
median improvement is not enough to select a replacement. The Node API used its
non-canvas text measurement path, so it does not establish browser-viewer
fidelity. The browser worker failed in the isolated harness; a separate direct
Vite bundler probe failed during WASM initialization because the expected memory
export was undefined. The [package documentation](https://www.npmjs.com/package/@slideglance/core)
describes it as pre-release. No browser integration or product dependency was
added. The temporary renderer and images were removed; the source deck was not
changed.

## Untouched-content invariant

An edit to slide 7 should not cause unrelated normalization on slides 1-6 or 8-N.

Tests should compare package parts and visual output outside the touched dependency graph to detect accidental rewrites.

## Error and warning taxonomy

Suggested stable categories:

- `PPTX_IMPORT_UNSUPPORTED_FEATURE`;
- `PPTX_IMPORT_CORRUPT`;
- `PPTX_IMPORT_RESOURCE_LIMIT`;
- `PPTX_RENDER_FIDELITY_WARNING`;
- `PPTX_EDIT_REQUIRES_NORMALIZATION`;
- `PPTX_EXPORT_PRESERVATION_RISK`;
- `PPTX_EXPORT_VALIDATION_FAILED`;
- `PPTX_EXPORT_VISUAL_DRIFT`.

User-facing wording should remain simple; detailed diagnostics belong in logs/test reports.

## Hidden objects in the candidate preview

The renderer does not consistently honor the DrawingML
`p:cNvPr/@hidden="1"` flag on pictures inherited from slide masters. PowerPoint
does honor it: the Open XML definition says a hidden non-visual drawing
property means the object is not displayed
([Microsoft Open XML reference](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.nonvisualdrawingproperties.hidden?view=openxml-3.0.1)).
The preview compatibility pass now removes only the owning hidden drawable
from the parsed slide, layout, or master shape tree. It leaves visible sibling
objects, relationship maps, the original PPTX bytes, Core, and exported files
untouched. The transformation runs only in the preview graph.

The pinned corpus contains this flag on two master objects: record `5606643`
and record `11196015`. The all-compatibility run suppressed one object in each.
The targeted, stable eight-slide `5606643` pair improved median normalized RGB
MAE from 13.03535% to 0.89545%, median PSNR from 9.4485 to 25.317 dB, and
median changed-pixel rate from 61.1787% to 33.54585%; MAE improved on all eight
slides with no regressions. Visual review of slide 2 confirmed the extra
master image disappeared and the candidate matched the PowerPoint layout.
Record `11196015` had zero unstable captures and no per-slide metric changes
after its hidden object was suppressed.

The following full-corpus run compared 31 of 33 records / 613 slides, skipped
two external-relationship decks, failed on none, and had 21 unstable
PowerPoint captures. Corpus medians were 14.457% changed pixels, 2.9308%
normalized RGB MAE, and 18.368 dB PSNR, compared with 14.4983%, 2.9402%, and
18.267 dB in the preceding run. all 613 slides still had stable pixel
differences, so this targeted correction does not clear the preview fidelity
gate. The machine-readable report is under ignored
`.local/preview-compare-hidden-all-20261001.json`; visual diagnostics for
`5606643` are under ignored
`.local/preview-debug/5606643-analysis-20261001/`.

Record `90000006` has a slide-layout `p:bgRef idx="1003"` that selects a theme
background `a:blipFill` with a tiled JPEG and duotone effects. An isolated,
bounded preview-only rasterization prototype was evaluated in QA. It resolved
internal theme image relationships and supported, unrotated layout shapes,
respected image DPI and tile scale, capped input/output size, and left source
PPTX bytes unchanged. The prototype was removed from application code after
the paired comparison regressed.

On 2026-10-01, paired Office comparisons of the stable 17-slide record had no
unstable PowerPoint captures. The candidate changed only slide 1; slides 2–17
were pixel-identical to the baseline. Slide 1 stable RGB MAE regressed from
6.5497% to 8.0112%, PSNR from 13.271 to 13.226 dB, and stable changed-pixel
rate from 34.3440% to 52.2555%. The prototype did not improve the preview and
was removed from application code. The theme relationship and fill fidelity
problem remains unresolved for production, and the current corpus still has
stable differences on all 613 comparable slides.

On 2026-10-01, the preview added a bounded `a:grpFill` compatibility pass.
It resolves fills through nested group ancestry and substitutes only a child
shape's direct `p:spPr` group-fill reference in the renderer's parsed preview
map. It leaves group properties, slide relationships, source PPTX bytes, and
exported files unchanged. Each slide is limited to 20,000 drawables and 64
group levels; ambiguous fills or property trees leave that entire slide
unchanged.

The pinned corpus contains 32 resolvable child references on seven slides:
four each on slides 6, 10, 12, 15, 17, and 18 of record `8376688`, and eight on
slide 4 of record `8021750`. Both records completed with no compatibility
parts skipped. On `8376688` slide 17, the same stable PowerPoint capture showed
changed pixels improve from 12.2865% to 12.2515%, normalized RGB MAE from
6.2934% to 5.2171%, and PSNR from 13.806 to 14.526 dB. On `8021750` slide 4,
the previous stable baseline and latest candidate captures showed changed
pixels move from 44.8991% to 43.9325%, MAE from 6.0322% to 4.6139%, and PSNR
from 14.675 to 15.747 dB; neither capture was marked unstable.

The full 33-record run compared 31 decks / 613 slides, skipped the two decks
with external relationships, failed on none, and recorded 21 unstable Office
captures. Corpus medians were 14.457% changed pixels, 2.8839% normalized RGB
MAE, and 18.426 dB PSNR. Cross-run aggregate movement includes Office capture
variation; the targeted comparisons are the stronger evidence for this
correction. all 613 slides still have stable differences, so presentation
fidelity remains a release blocker. No slide text or rendered images were
retained.

## Explicit solid backgrounds for shapes with useBgFill

The Open XML definition says useBgFill assigns the slide background fill to
the shape; it is not a transparency flag
([Microsoft Open XML Shape reference](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.shape?view=openxml-3.0.1)).
The candidate renderer treated a theme style fillRef as the shape's fill and
missed this background behavior on inset rectangles.

The preview compatibility pass now handles only an unambiguous direct
p:bg/p:bgPr/a:solidFill. It copies that fill to a p:spPr whose fill is
absent or a:noFill, then removes the style fillRef and useBgFill attribute
from the parsed preview map. The background properties must have no
attributes and may contain only that solid fill plus an empty a:effectLst.
Textured, gradient, pattern, inherited, theme-reference, or otherwise
ambiguous backgrounds remain unchanged. The source PPTX and exported files are
untouched; tests verify the source-byte invariant and unsupported cases.

The full corpus run resolved 24 background-fill shapes and removed 32 style
fill references. Nine shapes were newly eligible under the inset-fill rule:
four in record 2651704, one in record 90000007, and four in record 90000008. The other shape counts include the existing restricted full-canvas
normalization.

A fresh paired Office comparison of all 24 slides in record 90000008 had no
unstable captures. For slides 2, 10, 12, and 13, the same-capture stable
normalized RGB MAE fell respectively from 41.1192%, 41.6434%, 41.9813%, and
41.9540% to 2.3391%, 1.9651%, 1.6694%, and 1.7591%. Changed-pixel rates fell
from 99.5089-99.8200% to 17.6970-21.3650%. The deck-wide 24-slide median MAE
fell from 5.0290% to 3.4474%, and median PSNR rose from 21.3185 to 21.8025 dB.
The fix removes the olive panel, but text metrics and overall slide layout
still differ.

The full run for this change compared 31 of 33 records / 613 slides, skipped
the two external-relationship decks, failed on none, and recorded 21 unstable
Office captures. Corpus medians were 14.457% changed pixels, 2.8487%
normalized RGB MAE, and 18.469 dB PSNR. all 613 slides still had stable
differences, so presentation fidelity remains a release blocker. The
machine-readable report is under ignored
.local/preview-compare-background-fix-20261001.json. The 24 preview renders
for the targeted deck remain under ignored
.local/preview-debug/90000008-solid-background-20261001/; no slide text was
emitted.

## Slide-specific theme overrides in the preview

PresentationML slides can relate to a Theme Override part, which overrides a
slide's theme colors, fonts, and effects ([Microsoft's PresentationML
structure reference](https://learn.microsoft.com/en-us/office/open-xml/presentation/structure-of-a-presentationml-document)).
The preview renderer used the layout/master theme for explicit `a:schemeClr`
values even when the slide had its own theme override. In record `1287949`,
that rendered several lavender shapes in green.

The preview compatibility pass now follows only one exact, internal
`themeOverride` relationship per slide to a bounded `ppt/theme/*.xml` part. It
requires a valid DrawingML `themeOverride` with all twelve simple color slots,
uses the slide's existing color-map override, and resolves supported color
choices and transforms. Resolvable `a:schemeClr` values inside that slide's
explicit `p:cSld` are replaced with `a:srgbClr` in the renderer's parsed map.
It does not rewrite master or layout objects, guess unsupported color
transforms, or modify the source PPTX, revision, or exported file. The pass is
bounded to 256 override parts, 100,000 color references, 32 MiB of scanned
XML, and the existing 8 MiB per-part XML limit; unsupported and ambiguous
parts remain unchanged.

The stable paired PowerPoint comparison of record `1287949` normalized 164
explicit colors with no skipped compatibility parts or unstable captures. On
slide 24, normalized RGB MAE fell from 35.1295% to 9.4762%, PSNR rose from
5.455 to 12.008 dB, and changed-pixel rate fell from 70.0809% to 30.3532%.
Slides 6, 8, 9, and 10 also improved materially; a few other slides had small
MAE increases, and the deck still has substantial layout and content
differences.

The full 33-record run compared 31 decks / 613 slides, skipped the two
external-relationship decks, and had zero failures. The preview normalized
164 colors and skipped no compatibility parts. Across runs, median changed
pixels moved from 14.457% to 14.3864%, normalized RGB MAE from 2.8487% to
2.8295%, and median PSNR remained 18.469 dB; cross-run aggregate movement also
includes PowerPoint capture variation. There were 21 unstable captures and
613 slides with stable pixel differences. The result does not clear the
preview-fidelity gate. Machine-readable report:
`.local/preview-compare-theme-override-33-all-20261001.json`. The focused
render of record `1287949` remains under ignored
`.local/preview-debug/1287949-theme-override-after-20261001/`; no slide text
was retained.

## Release philosophy

Do not claim broad PPTX editing based on a handful of generated fixtures. Real enterprise decks are adversarial compatibility inputs. The feature graduates only through corpus-based round-trip evidence and dogfooding on real user decks.

## Theme background image fills in the isolated preview

Record `90000008`, slide 5 uses a master `p:bgRef` with style index `1003`.
That index selects an image fill from the theme's `a:bgFillStyleLst`, linked
through an internal theme relationship and tinted through `phClr` and a
duotone effect. The preview renderer previously fell back to the theme's first
background color, so it showed dark text on a black field.

The isolated preview now resolves only this bounded shape: a valid master
background reference, an internally related theme part, and a stretch image
fill with an internal media target. It applies the master theme's placeholder
color mapping and the supported duotone transform through the existing bounded
rasterizer. The renderer receives a direct background fill and a preview-only
media alias. Unsupported or external relationship structures fail closed.
Only the renderer's parsed in-memory graph and preview relationship map change;
source PPTX bytes, revisions, and exported files remain unchanged. A focused
test verifies the source-byte invariant and another confirms external theme
image relationships are not rewritten.

The focused 24-slide Office comparison for record `90000008` had no unstable
captures: three slides improved, 21 were unchanged, and none regressed. Slide 5
normalized RGB MAE moved from 11.93% to 11.03%, and slide 14 moved from 5.74%
to 5.34%. The relationship now resolves and the image is present, but that is
not yet an appearance match: the current preview remains visibly darker than
PowerPoint. A fresh `theme-background-only` run reproduced the result with no
unstable captures; on slide 5, the Office capture's top-left background pixel
was RGB `(34, 34, 34)` while the preview was `(4, 4, 4)`. The converted
preview-only raster had mean RGB `2.65`. This confirms a reproducible
appearance mismatch, but does not establish whether the cause is theme-color
resolution, duotone math, color management, or another PowerPoint rendering
detail. No empirical brightness adjustment has been accepted. This is a
fidelity defect, not an accepted correction. The targeted images are retained
under ignored `.local/preview-debug/90000008-current-match/` and
`.local/preview-debug/90000008-theme-background-only-20261002/` paths. A new
read-only PowerPoint COM render of the original source produced the same
slide-5 PNG SHA-256 as the earlier reference
(`e04fcd0262d4c0f3a8ba85f473ba76edcdc107c1bb1f0fae666a56c3d67754c3`). The
discrepancy is reproducible and not a stale reference image.

Controlled read-only PowerPoint COM probes on 2026-10-02 narrowed the
background mismatch. Removing the theme image's `a:duotone` effect renders a
bright source texture; replacing its two effect colors with red and green
recolors the rendered background. Explicitly changing the master's `p:bgRef`
color to `#808080`, white, or red also changes the result, so the style
reference color participates in Office's effect resolution. Explicit black
and the original `bg1` reference produce the same Office render. In that black
case, however, the current rasterizer resolves the `shade`/`lumMod` endpoint to
black and the 98% tint endpoint to near-black, producing a raster with mean RGB
2.65. Office retains a luminance-scaled texture instead: the fresh slide-5
capture has RGB `(34, 34, 34)` at `(0, 0)` and `(9, 9, 9)` at `(900, 500)`.
Thus the remaining discrepancy is specifically the black-reference behavior
of this theme-background effect in PowerPoint, not a missing image relation or
an inactive `duotone` node. No generic transform has been accepted, and the
experimental background conversion is not enabled in the integrated preview.
The original source deck was opened read-only; probe copies and images are kept
under ignored `.local/preview-debug/90000008-bgref-probes/` and
`.local/preview-debug/90000008-duotone-probes/` directories.

On 2026-10-02, the existing grayscale `p:bgRef` probe captures were compared
against the source JPEG at corresponding coordinates. At the top-left, source
RGB `(218, 218, 218)` becomes `(34, 34, 34)` in Office and `(4, 4, 4)` in the
candidate. At slide coordinate `(900, 500)`, the corresponding source sample
is `(59, 59, 59)`; Office renders `(9, 9, 9)` and the candidate `(1, 1, 1)`.
Varying the reference color from grayscale 0 to 255 moves Office's top-left
pixel from 34 to 246, with intermediate outputs 34, 34, 36, 37, 40, 48, 71,
and 127 for grayscale 1, 2, 4, 8, 16, 32, 64, and 128. This proves the
placeholder color affects the effect, but the observed response still cannot
be explained by the bounded rasterizer's resolved endpoints alone. The
effect-normalization option is set only by A/B comparison modes and tests, not
by the live Workspace preview. These probes do not justify a general
brightness correction or a runtime change.

The current 33-record integrated run resolved one theme background image fill,
and all 613 comparable slides still had stable pixel differences. The latest
corpus evidence is recorded in [`CORPUS.md`](CORPUS.md); broad preview fidelity
remains a release blocker.

## Ellipse-clipped pictures in the preview

Record `6447723` contains pictures whose embedded image is clipped to a preset
ellipse. The candidate renderer treated these `p:pic` elements as rectangular
images. The preview now promotes only pictures with a simple, unadjusted
`ellipse` preset and a bounded internal stretched-image relationship into
shape fills. It resolves media through the lazy package reader with 32 MiB per
image and 128 MiB total limits. Custom geometries, other presets, tiled fills,
external or missing media, and ambiguous structures remain unchanged. The
conversion preserves source package bytes, relationship parts, alt text,
geometry, outline, and supported effects; it changes only the renderer's
in-memory slide graph. Focused tests cover conversion, lazy media resolution,
unsupported geometry, missing and external media, and source-byte identity.

The paired 32-slide comparison for record `6447723` had no unstable Office
captures. On slide 3, changed-pixel rate fell from 39.6456% to 35.0411%,
normalized RGB MAE from 11.7892% to 9.8695%, and PSNR rose from 10.468 to
11.167 dB. Three other ellipse slides in the same record also improved. In the
full comparison, six pictures were promoted across three records. Of 592
slides stable in both full runs, four improved, two had small MAE increases
(0.1202 and 0.4263 percentage points), and 586 were unchanged. The previous
broader preset-shape experiment produced a large regression on a cropped
`round2DiagRect`; that geometry is now explicitly left unchanged. The full run
had per-slide medians of 13.8487% changed pixels, 2.7285% normalized RGB MAE,
and 18.615 dB PSNR, subject to Office capture variation. It still found stable
differences on all 613 comparable slides, so the preview fidelity gate remains
open. See [`CORPUS.md`](CORPUS.md) for run totals and the ignored machine-readable
reports.
