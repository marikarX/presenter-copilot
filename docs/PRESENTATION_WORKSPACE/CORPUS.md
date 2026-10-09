# Presentation Workspace corpus

The research corpus is a locally cached subset of PPTX files from the
Zenodo10K metadata collection plus ten individually attributed PPT-Eval source
decks hosted by Internet Archive. Its tracked source of truth is
[`corpus-manifest.json`](corpus-manifest.json). The manifest pins source IDs,
title, creator attribution, original filename, declared license, file size,
and source checksums for each selected file.

Run `pnpm workspace:fetch-corpus` to recheck each live source's rights and file
metadata and fetch files into `.local/presentation-workspace-corpus/`. Zenodo
records must declare open CC BY 4.0; supplemental Internet Archive items must
declare Public Domain Mark 1.0 and match Microsoft PPT-Eval's per-file
attribution list plus the creator, original filename, size, MD5, and SHA-1 in
the pinned metadata. Three supplemental sources overlap earlier Zenodo
records; seven add new decks. The unique CC BY and CC0 PPT-Eval files are
excluded from this PDM-only supplemental set. Downloads are bounded by 25 MB
per file and 170 MB in aggregate, require HTTPS, and never overwrite a
mismatching cache entry. The `.local` directory is ignored by Git; do not
commit or package the downloaded files.

Each record declares its own attribution and license. The manifest's metadata
screen does not clear third-party media, personal data, privacy, publicity, or
moral rights embedded in a deck. Keep the files local; review rights and
content before redistributing any deck, screenshot, excerpt, or derivative.
CC BY 4.0 allows sharing and adaptation with attribution, a license link, and
an indication of changes, subject to rights that the license cannot grant.
The Public Domain Mark is an indicator of public-domain status, not a warranty
about third-party content inside the files.
See the [CC BY 4.0 deed](https://creativecommons.org/licenses/by/4.0/) and the
individual [Zenodo records](https://zenodo.org/records/4709936),
[3996727](https://zenodo.org/records/3996727),
[2651704](https://zenodo.org/records/2651704),
[7488502](https://zenodo.org/records/7488502),
[5789785](https://zenodo.org/records/5789785),
[8376688](https://zenodo.org/records/8376688),
[11397234](https://zenodo.org/records/11397234),
[7761240](https://zenodo.org/records/7761240),
[11196015](https://zenodo.org/records/11196015),
[6447723](https://zenodo.org/records/6447723),
[10648100](https://zenodo.org/records/10648100),
[10679286](https://zenodo.org/records/10679286),
[5606643](https://zenodo.org/records/5606643),
[8376101](https://zenodo.org/records/8376101),
[5524399](https://zenodo.org/records/5524399), and
[13268484](https://zenodo.org/records/13268484),
[1287949](https://zenodo.org/records/1287949),
[2624130](https://zenodo.org/records/2624130),
[3957567](https://zenodo.org/records/3957567),
[8019884](https://zenodo.org/records/8019884),
[8021750](https://zenodo.org/records/8021750),
[13284023](https://zenodo.org/records/13284023), and
[8028476](https://zenodo.org/records/8028476). Microsoft PPTArena's
[attribution list](https://github.com/microsoft/ppteval/blob/main/ATTRIBUTION.md)
identifies ten selected files as Internet Archive items carrying Public Domain
Mark 1.0: [Accounting Equation](https://archive.org/details/accounting-equation),
[Worms](https://archive.org/details/GTAVC2005),
[Aircraft Surface](https://archive.org/details/AircraftSurface),
[Pre-Colonial Filipino Culture](https://archive.org/details/AlmonissahArchives_20171223_1426),
[HSC Careers and Expo](https://archive.org/details/humanexperiences_202105),
[Obesity](https://archive.org/details/Obesity_201504),
[Pediatric Prep](https://archive.org/details/pediatric-prep.),
[Jean-Nicolas-Louis Durand](https://archive.org/details/jeannicolaslouisdurand),
[Classical Social Experiments](https://archive.org/details/revisitingclassicalsocialexperiments),
and [Sea Level Rise](https://archive.org/details/drummondtroilounseenaspectsofsealevelrisefinal). Their live
archive metadata is rechecked by the downloader. The current 33 pinned PPTX
files total 159,057,663 bytes, below the manifest's 170,000,000-byte aggregate
limit.

Run `pnpm workspace:inventory-corpus` after fetching to verify the exact
cached hashes and produce a metadata-only structural inventory using Core's
bounded PPTX parser. It reports import success, slide/object counts, and
single-run text candidates without printing deck text. This inventory is not a
visual comparison, a PowerPoint-open check, a compatibility acceptance, or a
replacement for the planned 10–20 real deck-preparation sessions.

Run `pnpm workspace:roundtrip-corpus` to import each parser-supported deck
into an isolated temporary Core profile, apply one unique single-run text
edit where available, re-index and export the edit, validate the exported
structure, verify that only the edited slide package part changed, restore the
original revision, and check byte-identical original export. The report
contains only record IDs, hashes, counts, and stable error codes; slide text
is not printed. A deck without a supported single-run text target is reported
separately from a parser rejection.
Pass `-- --record-id <id>` to `pnpm workspace:roundtrip-corpus` to limit the
run to one pinned record; repeat the option to select multiple IDs. Use the
same option once with `pnpm workspace:visual-compare` for a focused PowerPoint
comparison.

The original 26-deck set contained 23 Zenodo records and three overlapping
Internet Archive files. Seven new PDM files were added from PPT-Eval on
2026-10-01. The expanded inventory accepted all 33 files; all 33 were parser
supported and none failed structural validation. The expanded edit/export/
restore smoke passed for 29 decks; four had no qualifying text target.
PowerPoint opened 27 of the 29 edited exports with matching slide counts and
unchanged hashes; two were skipped because they contain external non-hyperlink
relationships. The seven added decks passed
edit/export/restore, PowerPoint-open, and visual checks in the per-deck
isolated run. It completed with 21 unmasked passes, five passes with dynamic
regions masked, one review-required case, and two external-relationship skips.
An initial run reused one PowerPoint process for the corpus and reported nine
review cases; restarting Office for each record removed the order-dependent
differences. The remaining review is a text-overflow case on record `3996727`,
described below. The older 26-deck preview comparison below predates the
seven-deck extension; the current 33-deck comparison is documented below.

The earlier six structural rejections came from counting both `mc:Choice` and
`mc:Fallback` as separate shapes, plus pictures nested inside opaque OLE
graphic-frame payloads. The inventory now selects the first compatibility
choice whose required namespaces it supports, otherwise its fallback, and
keeps the original branches untouched. Selected alternate-content objects are
read-only; opaque graphic-frame payloads are not traversed. Duplicate IDs
among effective drawing objects still fail closed.

For each successful edit/export/restore case, the runner changes one character
in an existing word, preserving text length and whitespace; it confirms the
novel token was absent before editing, re-indexes and searches the exact edited
revision, verifies the result belongs to the edited document, reopens the edited
PPTX through Core, checks the target text and structural inventory, restores
the original revision, and exports bytes identical to the source. This does not
measure rendering fidelity.

On Windows with PowerPoint installed, run
`$env:PRESENTER_COPILOT_OFFICE_OPEN = "1"` followed by
`pnpm workspace:roundtrip-corpus` to open generated exports read-only in a
separate minimized COM instance. Before Office opens a deck, the runner scans
all package relationship parts and skips it if any external non-hyperlink
relationship could retrieve linked content. Automation security is disabled;
presentation windows are suppressed, slide counts and export hashes are
checked, and no deck text is emitted. On 2026-10-01, the expanded guarded run
opened 27 of 29 Core round-trip exports; two were skipped because they contain
external non-hyperlink relationships. Four decks without a qualifying text
target had no edited export to open. The runner starts a fresh minimized Office
process for each deck to prevent cross-record rendering state.

For the optional pixel comparison, run
`$env:PRESENTER_COPILOT_OFFICE_VISUAL = "1"` followed by
`pnpm workspace:roundtrip-corpus`. This also enables the guarded Office-open
check. For each safe export, PowerPoint renders source, edited, source, and
edited at 1280x720 into a temporary directory. The comparison masks pixels
that vary within either same-state pair, reports source and edited instability
separately, checks untouched-slide differences, verifies a visible edit, and
requires its changed-pixel bounds to stay inside the selected shape. Target
geometry comes from the complete parsed source snapshot rather than the
bounded UI object list. Rendered images are deleted; the report contains only
counts, slide numbers, hashes, observed difference bounds, and the expected
allowed target bounds in 1280x720 render pixels (including the existing six-
pixel tolerance).

On 2026-10-01, the per-deck isolated run completed with no structural,
round-trip, restore, or PowerPoint-open failures. Of 27 visual comparisons,
21 passed without masking, five passed with dynamic pixels masked, and one
needs review; two exports were skipped because of external non-hyperlink
relationships. All seven added records passed the visual check without masks.
The only review case is record `3996727`, with changed-pixel bounds
`[61, 74, 1231, 187]` and selected-shape bounds `[54, 51, 1240, 162]`; there
were no changed untouched slides. Visual inspection showed that the synthetic
one-character edit made the already-full-width title wrap and overlap the next
bullet. The PPTX export preserves that text edit correctly, but the overflow
means the resulting slide needs correction and the visual gate remains open.
The automated report cannot establish broad compatibility; the app should also
surface the resulting layout risk before a production edit is accepted.

A focused read-only rerun of record `3996727` also passed edit/export/restore
and Office-open validation but remained `needs_review`. Its target-bound escape
reproduced with no untouched-slide differences, confirming that it is the
edited title's overflow rather than a cross-slide change.

## In-app preview compared with PowerPoint

Run `pnpm workspace:visual-compare` on Windows with PowerPoint installed to
compare the actual browser worker used by the desktop app against read-only
PowerPoint renders. The runner uses only the hash-validated local manifest,
blocks external browser requests, masks pixels that vary across repeated
PowerPoint renders, emits counts and pixel metrics without slide text, and
deletes temporary images. It starts a fresh minimized PowerPoint process for
each corpus record to avoid cross-deck rendering state.

The 2026-10-01 comparison ran before the seven-deck corpus extension and
processed the then-current 26 pinned records through the integrated
`@aiden0z/pptx-renderer@1.3.0` primary preview path. Twenty-four decks (386
slides) were renderable by both paths, two were skipped because of external
non-hyperlink relationships, and none failed structural checks. The
in-memory SmartArt cached-image relationship repair fixed 52 image references
across two decks. A broad `useBgFill` rewrite had previously regressed slides
with explicit fills, so the production repair now only handles an exact,
backmost full-canvas `useBgFill` shape when its direct fill is absent or already
`noFill`. In paired `smartart-only` versus `all` runs, 15 shapes were normalized
across the corpus and 14 slides improved; no slide regressed. Median
changed-pixel rate moved from 16.0620% to 15.5916%; median normalized RGB MAE
remained 2.2403% and median PSNR remained 19.025 dB. PowerPoint's repeated
render varied on 148 slides, and all 386 slides still had stable pixel
differences. A human spot-check found remaining text-style, position, and
wrapping differences. This comparison does not establish a release threshold;
visual fidelity remains a release blocker. Open exported decks in PowerPoint
and review their appearance.

After adding the seven new records, the per-deck isolated full comparison ran
against all 33 manifest records on 2026-10-01. Thirty-one decks (613 slides)
were comparable, two were skipped because of external non-hyperlink
relationships, and none failed. all 613 slides had stable pixel differences;
PowerPoint output was unstable on 21 slides. Median changed-pixel rate was
14.4983%, median normalized RGB MAE was 2.9514%, and median PSNR was 17.894 dB
in this initial run.
No slide text or render images were retained. These metrics have no accepted
release threshold and still show a broad renderer mismatch; preview fidelity
remains a release blocker.

The initial all-effects comparison identified two especially weak previews
among the new records. Record `90000004` differed on all 32 slides (median
changed-pixel rate 96.62%, median RGB MAE 14.32%, median PSNR 11.71 dB); record
`90000008` differed on all 24 slides (76.57%, 5.03%, and 21.32 dB). On
`90000004`, bounded preview-only work restored the inherited title band and
approximated three `a:duotone`/`a:lum` raster references. On `90000008`, a
full-canvas `useBgFill` style fallback and themed duotone background were
traced and corrected in preview. A paired 24-slide run left its median
changed-pixel rate unchanged, improved median RGB MAE from 16.75% to 5.03%,
improved PSNR from 10.79 to 21.32 dB, and had no slide-level MAE regressions.
Both decks still have substantial stable visual differences and do not
establish acceptable fidelity. The renderer's generic preview disclosure
remains visible in the UI.

The latest full-corpus run on 2026-10-01 uses the additional narrowly gated
clear-material alpha approximation for two master pictures in `90000004`.
It compared 31 decks / 613 slides, skipped two external-relationship decks,
had zero failures, and saw 21 unstable PowerPoint captures. Corpus medians were
14.4983% changed pixels, 2.9402% normalized RGB MAE, and 18.267 dB PSNR. In the
paired `90000004` rerun, which had no unstable captures, median MAE improved
from 14.3155% to 7.0297% and PSNR from 11.715 to 15.8215 dB; MAE improved on
all 32 slides. Median changed-pixel rate moved from 96.6150% to 96.6146%, with
three slide-level increases no larger than 0.0006 percentage points. 613 of
613 slides in the full corpus still had stable differences against PowerPoint,
so preview fidelity
remains a release blocker.

A focused browser-versus-PowerPoint inspection of record `3996727` traced one
preview mismatch to renderer CSS that allowed horizontal text to break at any
character. The preview now normalizes `overflow-wrap` and, for horizontal
space-delimited text, `line-break` to word-level wrapping; vertical and East
Asian line-break behavior is preserved. On the reproduced one-character title
edit, the browser now moves the whole final word like PowerPoint. Both renders
still show the title overflowing into the following bullet, and the edited PPTX
remains `needs_review` because its changed pixels escape the selected-shape
bounds. This renderer-only correction does not change PPTX text, style, or
geometry, and the full-corpus medians did not materially improve. It resolves
one known wrapping discrepancy, not the broader fidelity release blocker.

The Workspace now measures text fragments in its isolated browser preview for
a uniquely matched, unrotated, top-level single-run target. If those fragments
extend beyond the source shape bounds, the UI displays a warning and disables
Save revision until the user acknowledges the overflow. If the renderer cannot
match the shape or measure its text, the UI asks for manual review. The
`pnpm test:ui:corpus-overflow` exercised the actual record `3996727` in an
isolated Electron profile. On slide 7, shape 5, the same-length one-character
preview produced the overflow warning and required acknowledgement before Save
was enabled. The source hash stayed unchanged, no revision was saved, and the
report retained no slide text or rendered image. This corpus also exposed a
slightly off-slide object on slide 1: Core marks its signed geometry as
non-editable, and the UI now accepts that read-only source geometry so it can
render the slide. This is browser-renderer evidence only; it does not establish
Office export fidelity or clear the exported case's visual `needs_review`
result.

The 2026-10-01 slide-theme follow-up compared the same 31 decks / 613 slides
against PowerPoint, skipped two decks with external relationships, and had no
failures. It normalized 164 explicit colors with no skipped compatibility
parts. Record `1287949` slide 24 improved from 35.1295% to 9.4762% normalized
RGB MAE. Full-corpus medians moved from 14.457% to 14.3864% changed pixels,
2.8487% to 2.8295% normalized RGB MAE, with PSNR unchanged at 18.469 dB.
These cross-run aggregate metrics include PowerPoint capture variation. The
full report remains under ignored
`.local/preview-compare-theme-override-33-all-20261001.json`; all 613
slides with stable differences still leave preview fidelity as a release blocker.
See [`PPTX_FIDELITY.md`](PPTX_FIDELITY.md) for bounds and per-slide evidence.

## Public research sources

The GUIDE benchmark includes 120 novice demonstrations across 10 applications,
with screen recordings and think-aloud narrations, including PowerPoint and
Google Slides. Its dataset card says each application has four task variants,
each completed by three novice users. That implies 12 PowerPoint and 12 Google
Slides demonstrations (24 presentation-editing sessions in total). The card
also says its initial release contains 50 full recordings and annotated
segments for the other 70, without identifying whether all 24 presentation
recordings are among the full videos. The dataset declares CC BY 4.0, but
downloading requires accepting a condition to share account contact
information. We have not accepted that condition or accessed/downloaded the
files. GUIDE is a candidate for supplementary interaction-pattern research
after authorized access and content review; novice benchmark tasks are not
product-user acceptance or high-stakes professional preparation.
See the [GUIDE project](https://guide-bench.github.io/) and its
[dataset card](https://huggingface.co/datasets/saelyne/GuideBench).

Pango's [Hugging Face card](https://huggingface.co/datasets/chakra-labs/pango-office-trajectories)
describes real, compensated work sessions in Google Slides, with video URLs,
timestamped clicks and text input, screenshots, and task context. Its visible
application list does not include PowerPoint, and its card does not state a
data-reuse license. Access to the files is contact-gated; Pango's [public
site](https://pango.so/) directs dataset users to request access, while its
current product page lists Microsoft Office support as future work. We have
not contacted the provider or accessed any files. Pango is a possible source
of interaction-pattern evidence only after terms, participant-data scope, and
privacy review; it does not provide verified PPTX export-fidelity cases.

PPTArena describes 100 paired slide-edit benchmark tasks and declares an MIT
dataset license. It may help evaluate edit operations, but benchmark tasks are
not observed preparation sessions. Check each underlying deck's provenance and
rights before using or redistributing its files. See the
[PPTArena dataset card](https://huggingface.co/datasets/mofengenden/PPTArena).

The SWELL-KW research dataset describes 25 participants doing about three
hours each of general knowledge work, including making presentations, and
contains computer-interaction logs alongside facial, posture, and physiological
data. Its published summary does not establish 10–20 distinct slide-preparation
sessions, the specific presentation tasks, commercial reuse rights, or consent
for this product's research purpose. It is not being used as a substitute.
The DANS record is publicly accessible, but its terms and participant-data
scope need direct review before any reuse. See the
[Radboud dataset description](https://www.cs.ru.nl/~skoldijk/SWELL-KW/Dataset.html)
and [DANS record](https://doi.org/10.17026/dans-x55-69zp).

Two newer edit benchmarks may supplement operation-level validation.
[PPT-Eval](https://arxiv.org/abs/2606.31154) contains 120 PowerPoint tasks
across 12 files. Its paper and [attribution manifest](https://github.com/microsoft/ppteval/blob/main/ATTRIBUTION.md)
identify 11 source decks as Public Domain Mark 1.0 or CC0 and one as CC BY 4.0.
The source PPTX files have not been added to this corpus; review the individual
Internet Archive records and embedded content before reuse. [TSBench](https://arxiv.org/abs/2505.11604)
contains 379 human-verified editing instructions. Neither benchmark is a set
of observed product preparation sessions.

[PPTC](https://github.com/gydpku/PPTC) describes 279 simulated multi-turn
PowerPoint sessions (229 creation and 50 editing tasks). The repository code
is MIT-licensed, but its presentation templates have separate sources and
rights that need review. These task simulations can supplement operation-level
checks after deck review; they are not observed sessions with Presenter Copilot
and do not replace product-user research.

[A11y-CUA](https://huggingface.co/datasets/berkeley-hci/A11y-CUA) declares
CC BY 4.0 and contains human interaction traces from 16 participants (8 blind
and low-vision users and 8 sighted users) completing the same 60 controlled
Windows tasks. Seven tasks involve PowerPoint: Task 27 creates a two-slide
personal introduction; Task 28 changes a deck's theme; Task 33 changes slide
orientation; Task 37 copies Word content into slide notes; Task 41 inserts a
recorded screen demonstration; Task 42 inserts a picture; and Task 43 inserts
an Excel chart. That is 112 participant-task traces across the seven tasks,
including 16 guided two-slide deck-creation attempts. The task traces offer
useful operation-level and accessibility interaction evidence, but do not
represent a diverse sample of natural preparation workflows, Presenter Copilot
user acceptance, or PPTX export-fidelity cases.

The [Reduced-A11y-CUA variant](https://huggingface.co/datasets/berkeley-hci/Reduced-A11y-CUA)
declares CC BY 4.0 and removes audio and video while retaining interaction
events, accessibility trees, session metadata, and web logs; its card reports
3.86 GB total. For a limited behavior review, only the 16 Task 27 PowerPoint
event-log files were fetched in memory and reduced to aggregate event types and
timestamps; no raw files or media were saved. The blind-and-low-vision logs
contain keyboard and hotkey events, while the sighted logs also contain mouse
movement and drag events. This supports accessibility-oriented workflow
checks, not usability or export acceptance. The event format can contain text
and window/focus context, so review participant-data scope before any broader
analysis or redistribution.

The [SlideSpace study](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/07/a16-edge.pdf)
reports eight experienced participants, each completing one approximately
two-hour authoring session with screen capture, audio, and action logging. The
publication describes the study but does not provide a downloadable set of its
raw recordings. It therefore informs task design but does not meet the 10–20
session product-validation gate. GUIDE offers 24 candidate presentation-editing
demonstrations across PowerPoint and Google Slides, but its gated file access
and privacy-review split need resolution before those recordings can be
assessed or used. Neither literature nor benchmark tasks count as observed
Presenter Copilot user acceptance.

## Hidden master objects in the candidate preview

The pinned corpus has `p:cNvPr/@hidden="1"` on one master object in each of
records `5606643` and `11196015`. PowerPoint omits these objects, as required by
the [Open XML hidden-property semantics](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.nonvisualdrawingproperties.hidden?view=openxml-3.0.1),
but the candidate renderer drew the picture in `5606643` over every slide. The
preview-only shape-tree pass now removes the owning hidden object from parsed
slide, layout, and master data while preserving source bytes and exports.

For `5606643`, the stable eight-slide before/after run had no unstable Office
captures. Median normalized RGB MAE fell from 13.03535% to 0.89545%, PSNR rose
from 9.4485 to 25.317 dB, and changed-pixel rate fell from 61.1787% to
33.54585%; all eight slide MAEs improved. For `11196015`, suppressing its
master object produced no per-slide metric changes across 17 slides and no
unstable captures. The full 33-record run compared 31 decks / 613 slides,
skipped two external-relationship decks, failed on none, and saw 21 unstable
PowerPoint captures. Its medians were 14.457% changed pixels, 2.9308% MAE,
and 18.368 dB PSNR. All slides still differed, so the broader preview-fidelity
gate remains open. Machine-readable metrics and visual diagnostics are kept
under ignored `.local/` paths recorded in `PPTX_FIDELITY.md`.

## Earlier integrated preview comparison (2026-10-02)

The latest integrated comparison used the SmartArt image-relationship repair,
the bounded explicit-background fixes, slide-specific theme override colors,
group-fill inheritance, and the new theme-background image-fill resolution.
It completed on all 33 manifest records: 31 decks / 613 slides compared, two
external-relationship records skipped, zero failures, and 21 unstable
PowerPoint captures. Thirty-five SmartArt images were promoted to pictures in
the preview graph and one theme background image fill was resolved. Corpus
medians were 13.8487% changed pixels, 2.7614% normalized RGB MAE, and 18.572
dB PSNR. Stable pixel differences remain on all 613 comparable slides, so
this is diagnostic evidence and does not pass the fidelity gate.

Compared with the previous SmartArt-promoted report, 592 slides had stable
captures in both runs: three had lower MAE, 588 were unchanged, and one had a
small increase. The record `90000008` targeted comparison had no unstable
captures; three slides improved, 21 were unchanged, and none regressed. These
paired reports provide the better evidence for the targeted changes; the
aggregate medians also reflect differences between PowerPoint captures. The
machine-readable report is kept at
`.local/preview-compare-33-current-tree-20261002.json` and retains no slide
text or rendered images.

## Ellipse picture-fill follow-up (2026-10-02 UTC)

The preview compatibility pass now promotes only simple preset ellipses with
stretched internal image fills. The first broader preset-shape experiment
improved ellipse-clipped pictures but regressed a cropped `round2DiagRect` on
record `6447723`, slide 30; the production rule was narrowed so that and other
unsupported geometry remain unchanged. The transform verifies package media
through the lazy resolver, applies 32 MiB per-image and 128 MiB total media
bounds, and edits only the preview's in-memory slide graph.

The 33-record run completed with 31 decks / 613 slides compared, two
external-relationship records skipped, zero failures, and 21 unstable Office
captures. Six ellipse pictures were promoted across three records and 11
unsupported candidates were skipped. On 592 slides stable in both runs, MAE
improved on four, worsened slightly on two (0.1202 and 0.4263 percentage
points), and was unchanged on 586; median paired MAE movement was zero. The
per-slide medians across the 613 comparisons were 13.8487% changed pixels,
2.7285% normalized RGB MAE, and 18.615 dB PSNR. Those aggregate values are
subject to Office capture variation; all 613 comparable slides still show
stable differences.

For record `6447723`, the stable 32-slide run promoted four ellipses and
skipped six unsupported candidates. Slide 3 changed-pixel rate fell from
39.6456% to 35.0411%, normalized RGB MAE from 11.7892% to 9.8695%, and PSNR
rose from 10.468 to 11.167 dB. The machine-readable full report is
`.local/preview-compare-33-ellipse-only-20261002.json`; slide text and rendered
images were not retained. The wider diagnostic report that exposed the
`round2DiagRect` regression remains at
`.local/preview-compare-33-picture-geometry-20261002.json`.
