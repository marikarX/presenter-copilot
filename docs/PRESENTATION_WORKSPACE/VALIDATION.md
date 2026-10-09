# Presentation Workspace Validation Plan

## Objective

Validate both product usefulness and document fidelity before treating Presentation Workspace as a core product surface.

### List numbering and bullet markers on the local corpus — 2026-10-09

Read-only inventory of the 33 cached corpus decks
(`.local/presentation-workspace-corpus/`), comparing `e1bfd65` (before
text-font `buFont` tolerance) with `2f5ce70`:

| Measure | Before | After |
| --- | --- | --- |
| Format-editable text objects | 1836 | 1836 |
| Bullet-editable text objects | 1654 | 1683 |
| Objects with a direct bullet marker that are bullet-editable | 0 | 14 (7 decks) |
| Objects with editable bullet color/size | — | 1683 |

Most real lists inherit bullets from layout placeholders and were already
editable. Before this change, no paragraph that carried its own marker was
editable, because PowerPoint writes a `buFont` beside the `buChar`.

Edit acceptance: for each deck, one direct-marker list received a single
reviewed edit through actual Core (`numbered_alpha_upper`, start 2, color
`#1F4E79`, size 120%). Five decks (06, 21, 22, 29, 30) read the values back
exactly from the saved revision, and Microsoft PowerPoint opened each edited
copy read-only with the expected slide count. Two decks (08, 11) were declined
before PowerPoint by the existing safety policy for active or external
content. That decline is unrelated to the edit. The other 26 decks had no
direct-marker list to exercise. Visual comparison of the rendered bullets was
not part of this run. Script: `.local/session2/corpus_bullets.py`; receipts:
`corpus-bullets-{before,head,edit}.json`.

Follow-up tolerance (same day): follow-text markers (`buClrTx`, `buSzTx`,
`buFontTx`), point sizes, theme/transformed bullet colors and single-glyph
symbol bullets are retained and editable instead of read-only. Picture
bullets and preset/system color models stay read-only. With this change all
1836 format-editable text objects in the corpus are bullet-editable (from
1654 originally).

The run also found a real fidelity bug. A paragraph inherited a Wingdings
bullet font from its shape list style, so an applied "•" or number would have
rendered as a symbol. Applying a visible marker now removes a direct symbol
`buFont` and, when no text font remains, writes `buFontTx` so the marker
follows the text font.

Final corpus pass: 13 real decks were edited through actual Core. Seven were
Wingdings lists changed to "•" with a color. Six were recognised lists changed
to lettered numbering from B with color and 120% size. Every edit read back
exactly, every edited paragraph's marker uses a text font, and PowerPoint
opened each copy. PowerPoint rendered original and edited PNGs for all 13.
Two representative pairs (deck 26 slide 2, deck 22 slide 2) were reviewed by
eye: markers changed as intended and text positions did not move.

Blank lines (same day): run-less paragraphs no longer make a text box
read-only for formatting. They were the only blocker for 501 of 2355 corpus
text shapes. A blank line without direct properties neither reports nor
receives paragraph styles, so a trailing blank line cannot make a list look
mixed. Format-editable text objects rose from 1836 to 2068. The corpus
PowerPoint pass then covered 19 edited decks (7 recognised lists, 12 symbol
lists), all reading back exactly with text-font markers and opening in
PowerPoint. Line breaks (`a:br`, 96 shapes) remain read-only because they
interact with single-paragraph text replacement. Renders:
`.local/session2/corpus-renders/`.

### Native templates and draft authoring — 2026-10-03

General voice-plan follow-up: nine Core voice tests exercise rewrite, current
slide and deck capture ownership, synthetic PCM-to-transcript, no durable
transcript/provider rows, stale-head cancellation, cleanup and blank-slide
capture. Fresh full check passed 101 desktop and 516 Core tests. Electron passed
28 workflows, with a silent capture/cancel/corrected-transcript sequence that
locks scope/proposal controls, rejects instructions over 500 characters,
requires explicit Use, then runs the normal generated-plan review/save/undo.
The styled transcript screenshot was inspected. Final GUI terminal-error
handling passed TypeScript/lint/101 desktop tests afterward. Synthetic provider
UI checks passed. Evidence: `.local/voice-plan-*-20261003.log`. Physical
microphone recognition/latency, confidence/ambiguity handling and live providers
remain unverified; no speech recognition claim is made from the silent UI case.

Authored insertion follow-up: eight Core integration variants cover all four
layouts on 4:3 decks with/without existing notes masters, review-only staging,
exact preview-byte commit, native content/notes, later title editing, restoration
and byte-identical existing slide/notes/asset parts. One provider test covers
the strict authored operation and content-free audit. Full checks passed 101
desktop and 511 Core tests; final GUI-only changes passed formatting, lint,
TypeScript/mypy and 101 desktop tests again. Electron passed 27 workflows,
including insertion preview, direct dialog overflow, discard, approval
invalidation, saved notes, undo and current slide counts. Screenshots were
inspected. PowerPoint opened one generated 4:3 candidate without prior notes
masters, confirmed two slides/title/notes, exported the authored slide, and
left the PPTX hash unchanged. Rendering was inspected. Evidence:
`.local/authored-*-20261003.log`, `.local/authored-office/result.json` and
`slide-2.png`. This does not prove wider corpus or live-model acceptance.

Seven Core template tests verify Classic/Midnight/Paper across Points/Columns/
Cards/Statement layouts, maximum-length content preservation, speaker notes,
native shape bounds, and rejection before import for unsupported designs.
The fresh full check passed 101 desktop and 502 Core tests. Following the final
accessible-label adjustment, formatting/lint/TypeScript/mypy and 101 desktop
tests passed again. Electron passed 26 workflows, including editable draft
content, authored slide insertion, reorder/duplicate/remove, invalid-content
blocking, returning to the updated text outline, Midnight cards/statement
creation, preserved notes, and subsequent normal revision editing. Screenshots
of outline review and the created native deck were inspected. Synthetic
provider UI checks also passed. Evidence logs: `.local/continuation-*-20261003.log`.
This does not prove long-text render fit on every slide, PowerPoint fidelity,
human preparation-session usefulness, live ChatGPT sign-in/inference or fast-
decision quality/latency. Creation templates do not transform imported decks.

The feature fails if either side is weak:

- useful AI/editing with unreliable PPTX export is unacceptable;
- perfect round-trip fidelity that does not reduce preparation friction is not strategically justified.

## Current implementation and evidence — 2026-10-02

Core opens a presentation revision only after validating the project, source
type, parse state, size, safe path, package structure, and SHA-256. It builds a
bounded structural inventory from the verified snapshot. Slide and shape IDs
remain stable across managed revisions that preserve their OOXML anchors;
separately imported files use different document lineages. Project schema v13
stores immutable revision history, binds supported rehearsal sessions to their
starting revision, and scopes parsed slide units to a revision. Existing
projects migrate transactionally.

Reviewed multi-operation edits stage an actual native package while retaining
the baseline head. Core tests verify that apply publishes byte-identical preview
content as one revision, preserves unchanged package parts and the imported
original, and commits only content-free operation metadata. Wrong scope, stale
head, modified preview, missing review acknowledgement, and failed audit commits
leave the head unchanged. Expiry, discard, deletion, shutdown, and abandoned
preview reconciliation are covered. The Electron workflow exercises grouped text
and notes editing, rendered review, discard, one-revision save, and whole-plan
undo. Copilot planning checks additionally cover strict operation schemas,
out-of-scope targets, fabricated evidence, sequential text/style preconditions,
reordering, local-only privacy, generation/finalization races, missing provider
provenance, and oversized inventories. Electron exercises generated plans,
request-change approval invalidation, deck-wide review, discard, save and undo.
These use deterministic providers and capture fixtures. Live model quality,
human preparation sessions, physical microphone acceptance and PowerPoint
fidelity are still open.

The user-facing editor supports bounded mutations: replace text in a
single-run shape or multiple direct runs with identical complete formatting;
apply bold, italic, font-size, or solid RGB color to
every direct run in a structurally simple text shape of up to 128 paragraphs (within the Workspace's 2,000-character target limit); set left, center,
right, or justified alignment, a bounded 0–144 point left indent, a signed -144–144 point first-line/hanging indent, whole-point line spacing from 1 to 144 points, a disc, hollow-circle, square, or dash bullet styles, no-bullet formatting, or Arabic-period automatic numbering across those paragraphs, and bounded before/after spacing from 0 to 144 points on each paragraph; set direct solid RGB fill and outline colors on supported
top-level shapes; create a bounded rectangle or ellipse with direct solid RGB
fill and outline colors; crop a simple embedded picture within its existing frame; replace that picture with a bounded, decoded single-frame PNG or JPEG; create
a simple text box; edit plain speaker notes represented by uniformly
styled paragraphs with at most one run each, move or resize an unrotated,
unflipped top-level shape or picture, delete or duplicate a top-level shape or
picture with no placeholder, connector, or animation dependency, reorder
slides, insert a blank slide using the selected slide's layout or the layout
already used by another slide in the current revision, duplicate a
supported slide, apply another slide's existing layout to the selected slide,
or delete a supported slide. Image replacement accepts one
decoded PNG or JPEG up to 4 MiB and 20 megapixels. It creates a new media part
and slide relationship, changes only the selected picture embed, retains the
existing geometry and crop, and leaves the original media available to any
picture that shares it. Object
duplication keeps existing package relationships, assigns a new stable object
identity, and applies a small in-bounds offset. Slide duplication inserts a
stable new slide after the selected slide, shares its existing layout and media
relationships, and clones speaker notes with a new relationship to the
duplicated slide. Blank-slide creation adds a new slide part and relationship
to a layout already used in the current revision without copying slide
objects, notes, or media. It
inserts after the selected slide and validates the package before commit.
Applying a layout already used by another slide changes only the selected
slide's layout relationship. Core verifies that slide order, slide objects,
speaker notes, and every other package part remain unchanged. Requesting the
layout already in use creates no revision; a real change is revisioned,
re-indexed, previewed, and undoable.
Slide duplication fails closed when a slide or notes part uses an unhandled
package relationship. Geometry must remain within slide bounds. Core checks the
current revision and expected target text, geometry, style fingerprint, or slide identity, or
validates that submitted slide IDs form an exact permutation of the current
slides. It rewrites the selected slide/notes part or slide-list, presentation
relationships, and content-type parts, validates the output and existing slide
inventories, and commits a new immutable revision. Simple picture cropping
requires a direct slide-level picture with a standard stretch fill and one
internal image relationship. Core validates the expected crop and geometry,
changes only `a:srcRect` in the selected slide part, and preserves the media and
relationship parts. Image replacement writes the new media part, selected
slide, and slide relationship; it updates `[Content_Types].xml` only when the
replacement extension has no matching declaration. Other package parts are
checked for unchanged content before commit. Slide deletion removes the
target slide and its notes parts only after checking for custom-show, section,
and package links; it keeps at least one slide and retains possibly shared
media parts. Grouped, rotated, flipped, unsupported, and out-of-bounds objects
remain read-only. Richly formatted and oversized notes remain read-only.
Picture creation uses an explicit positive geometry bounded by the selected
slide, adds private image media and one slide relationship, stores optional
alternative text, and checks that the media bytes, content type, and all
unmodified package parts remain valid before commit.
Shape creation accepts only rectangles and ellipses with positive geometry
inside the selected slide and direct solid RGB fill/outline colors. It allocates
a stable object identity, rewrites only the selected slide XML, verifies the
new object and all unaffected package parts, and commits an immutable revision.
The UI can restore a prior revision, undo to its parent, redo through a unique
child, and export the current or original PPTX through the native save dialog.
Redo stops safely on a branch and requires an explicit revision choice. Simple
shape-color edits retain geometry, text, and other shape properties, and
rewrite only the selected slide part. Gradient, pattern, image, and
effect-based fills stay read-only. Mixed-style, linked, and structurally
complex multi-run text remains read-only. This does not establish paragraph
percentage-based or fractional line spacing,
custom numbering styles, picture bullets, arbitrary bullet glyphs and custom bullet font/color/size styles, or multi-shape bulk
formatting, advanced shape fill/line effects, complex
picture-fill or diagram editing, additional
object types, unused theme-layout discovery/selection, arbitrary presentation
templates,
broad Office-feature compatibility, or visual
parity with PowerPoint.

Native creation is separately implemented through a reviewed manual outline
or a provider-planned briefing. The latter is verified with deterministic
local providers for review-only behavior, iterative refinement, complete
40-slide draft context, fabricated-citation rejection, exact slide count,
Local Only blocking, project-scoped planning lineage, and native creation.
These checks do not establish live model quality, factual entailment of cited
sources, or template and layout acceptance by real presenters.

After a text, formatting, notes, geometry, picture creation, crop or image replacement, safe object or slide
creation/deletion/duplication, slide reorder, restore, undo, or redo, the UI requests a
Core re-index of the current package.
Core verifies the package hash and revision head, then replaces parsed units
for that revision while retaining older revisions' units. Retrieval defaults
to the current head, while session-driven retrieval uses the immutable session
revision. If re-indexing fails, the saved revision has no retrieval units and
the UI directs the user to re-index; the previous revision's text is not
presented as current.

The workspace also exposes an explicit slide-purpose suggestion. Core reads
only supported text from the selected slide and current revision. A selected
remote provider is blocked by Local Only; Selected Context Cloud requires the
project's remote-reasoning acknowledgement. The provider run records provider,
source, revision, privacy, and context-boundary metadata but not the slide
text. Provider responses require user review and are not persisted or applied
to the deck. After the user confirms or corrects a category, Core can store
only that purpose label with `user_confirmed` provenance, keyed to the exact
revision and stable slide ID. It stores no slide text or provider response;
labels do not automatically carry across revisions. Images and diagrams are
outside this workflow. Jev/OpenRouter, OpenAI Responses Fast/Ultrafast,
Ollama System One (Nimble/Tev1), and local strict-schema adapters have synthetic
coverage; no Ollama model call or semantic-accuracy evaluation was run. Ollama
selection requires an already installed model and stays fixed to loopback.
Tev1 is experimental. No provider automatically falls back to another provider.

Core and Electron tests use the checked-in 22-slide synthetic deck to cover
repeatable identities, content-only revisions, cross-lineage identities,
DTD rejection, revision migration, one-run, text-box, picture, rectangle, and
ellipse creation, speaker-notes,
object geometry, single-run and uniform-style multi-run replacement, all-run single- and multi-paragraph formatting, predefined bullet-glyph and no-bullet writes, Arabic-period automatic numbering across simple paragraphs, and rejection of unsupported numbering schemes and arbitrary bullet characters,
left and first-line-indent range and source-value validation, stale-style rejection,
preservation of left margin, first-line indent and unrelated bullet XML, and
per-run style preservation, solid shape
fill/outline color edits and stale-style rejection;
picture crop bounds and stale-target rejection; image replacement validation, shared-media preservation, retained geometry/crop, picture-creation bounds and alternative text, private media and relationship creation, and package-part invariants;
shape/picture and slide
duplication; safe slide/object deletion and slide-order
validation, preservation of the original and untouched package parts, stable
slide/object IDs, stale-edit/permutation and slide-bound rejection,
placeholder/connector/animation deletion and duplication guards,
current/original export, restore, source-deletion cleanup, and privacy-safe
decision manifests. Slide-mutation checks cover cloned notes and their
independent slide relationship, retained image references, untouched existing
parts, notes cleanup, and rejection of unsupported relationships or references.
Core also verifies purpose-label lifecycle behavior: only allowed categories
can be saved, slide and revision identities must match the current head, labels
survive restart, become unavailable on another revision, and reappear when
that revision is restored.
The UI flow checks text and shape color controls, rectangle/ellipse creation
and preview repaint after the committed revision is re-indexed,
picture cropping, PNG/JPEG replacement and insertion with editable geometry,
and text-box creation alongside
the direct-edit operations, revisions, and export path. It also verifies that
a user-confirmed purpose label is saved on one revision, hidden after editing,
and visible again when that revision is restored.
A separate `pptx-glimpse@5.3.1`
spike found that a no-op save changed 60 XML parts that were equal after XML
canonicalization; this was one-deck evidence only and the user-facing export
does not use that serializer. None of this is a representative compatibility
corpus result or a real-user study. A
33-deck public corpus is now pinned and inventoried locally: 23
Zenodo CC BY 4.0 records and ten Internet Archive items attributed by the
Microsoft PPT-Eval project as Public Domain Mark 1.0. On 2026-10-01, Core
accepted all 33 files. The six earlier structural rejections
were false positives from counting mutually exclusive `mc:Choice` and
`mc:Fallback` branches and from traversing pictures nested in opaque OLE
graphic-frame payloads. Core now inventories one supported branch without
rewriting either branch, treats those alternate-content objects as read-only,
and still rejects duplicate IDs among effective drawing objects. The isolated
text-edit/re-index/export/restore smoke passed on 29 decks; four had no text
target meeting the editability, geometry, and novel-token requirements. A
guarded Windows check opened 27 edited exports read-only in PowerPoint,
verified slide counts and unchanged hashes, and skipped two decks with external
non-hyperlink relationships. The check emitted no deck text and retained no
images. The optional Office pixel check rendered source, edited, source, and
edited at 1280x720; its masks include pixels unstable within either same-state
pair. The initial full 33-deck run reused one PowerPoint process and produced
9 review-required cases. The runner now starts a fresh process per deck; the
isolated run produced 21 passes, 5 passes with dynamic regions masked, 1 review-
required case, and 2 skips. All seven added decks passed the isolated run
without masking. The remaining case is a one-character edit that wraps an
already-full-width title beyond its shape and overlaps the next bullet; no
untouched slide changed. The visual acceptance gate remains open until this
layout risk is addressed.
These results do not establish visual fidelity, Office editing behavior beyond
opening, or compatibility across the full corpus. The full result and affected
record IDs are in [`CORPUS.md`](CORPUS.md).

The corpus comparisons are separate from the Electron UI smoke. The original
`pptx-glimpse@5.3.1` path, before the corpus extension, rendered 24 of its then-
current 26 decks (386 slides); two decks with external non-hyperlink
relationships were skipped. Its median changed-pixel rate was 16.2330%, median
normalized RGB MAE was 3.0356%, and median PSNR was 17.404 dB. Repeated
PowerPoint output varied on 148 slides.

The integrated `@aiden0z/pptx-renderer@1.3.0` candidate rendered the same 24
decks and 386 slides in that 26-deck comparison and skipped the same two. On
2026-10-01, paired
`smartart-only` and `all` comparisons found that the in-memory SmartArt repair
fixed 52 image references across two decks. A restricted full-canvas
`useBgFill` repair normalized 15 shapes whose direct fill is absent or already
`noFill`; 14 slides improved and none regressed. Median changed-pixel rate
fell from 16.0620% to 15.5916%, while median normalized RGB MAE remained
2.2403% and median PSNR remained 19.025 dB. PowerPoint rerenders varied on 148
slides, and all 386 slides still had stable pixel differences. Human review
still found visible text-style and position differences. These metrics do not
establish a release threshold or PowerPoint equivalence; visual fidelity
remains a release blocker. No slide text or rendered images were retained.

The per-deck isolated 33-record comparison completed on 2026-10-01: 31 decks
(613 slides) were compared, two were skipped for external non-hyperlink
relationships, and none failed. Stable differences remained on all 613 slides;
PowerPoint was unstable on 21 slides. Median changed-pixel rate was 14.4983%,
median normalized RGB MAE was 2.9514%, and median PSNR was 17.894 dB. This is
full-corpus evidence, not a passing fidelity threshold; the 33-deck in-app
preview remains a release blocker. The runner created a fresh PowerPoint
process for each deck, and retained or emitted neither slide text nor renders.
Records `90000004` and `90000008` were large outliers, with median changed-
pixel rates of 96.50% and 76.57%; visual review of `90000004` confirmed missing
translucent/effect styling in the app preview. Details are in [`CORPUS.md`](CORPUS.md).

The Electron UI smoke exercises the bundled candidate inside its hidden,
sandboxed preview window and asserts that the compatibility fallback notice is
absent. All 15 workspace/application flows passed with no renderer exceptions.
That run uses the synthetic fixture and proves normal preview/open/render and
edit flows; it does not measure memory or input responsiveness near the 50 MiB
file limit, or replace Office visual review. Corpus metrics retained no
render images and emitted no slide text; temporary visual spot-checks are
described in [`PPTX_FIDELITY.md`](PPTX_FIDELITY.md).

Gate 1 remains **pending** until 10–20 real deck-preparation sessions establish
repeated demand for integrated editing. The 33-deck public corpus is pinned,
but its embedded media and compatibility classes still need review; the Office
visual `needs_review` results and measured preview mismatches remain unresolved.
Repeat Office-open checks on the exact release candidate and create a
human-labeled decision evaluation. Public GUI benchmarks do not replace those
product sessions.

## Product metrics

### Context-switch reduction

Measure how often users leave Presenter Copilot for PowerPoint/Slides during preparation.

Target for early editing release:

- at least 70% of observed preparation edits completed inside Presenter Copilot;
- target 90%+ before positioning it as the primary preparation workspace.

### Time-to-change

Compare representative operations:

- edit title/body text;
- replace image;
- move detail to appendix;
- add evidence/citation;
- restructure a dense slide;
- turn a rehearsal explanation into notes/slide content.

Measure direct-edit and AI-assisted flows separately.

### AI proposal acceptance

Track:

- applied as-is;
- applied after revision;
- rejected;
- stale/invalid;
- reverted later.

High acceptance is useful only if reversions and fidelity regressions remain low.

### Rehearsal-to-edit value

Measure:

- percentage of Run/Challenge sessions producing at least one useful edit proposal;
- proposal acceptance rate;
- subsequent rehearsal improvement;
- whether users identify proposals as non-obvious/useful versus generic advice.

### Voice editing value

Measure:

- successful commands without correction;
- correction rate due to ASR;
- destructive-command prevention rate;
- latency from final utterance to reviewable proposal;
- repeat usage after novelty wears off.

## Fidelity metrics

### Import success

- percentage of corpus decks imported without fatal error;
- feature-class warning accuracy;
- slide/object inventory parity.

### No-op round trip

- valid PPTX open in PowerPoint;
- no missing slides/objects;
- notes preserved;
- unsupported package parts preserved;
- visual similarity above threshold;
- no unexpected changes to untouched slides.

### Edited round trip

For each supported edit operation:

- intended object changed correctly;
- unrelated objects unchanged;
- unsupported neighboring content preserved;
- PowerPoint remains able to edit the changed object as expected where claimed.

### Visual drift

Track slide-level render differences with thresholds and human review buckets:

- pass;
- minor acceptable drift;
- material drift;
- blocker.

Text overflow, font substitution, image loss, layout shifts, and z-order mistakes should be treated as high-severity even when aggregate pixel similarity looks acceptable.

## Golden corpus requirements

Maintain at least three corpus classes:

### Synthetic deterministic fixtures

Small files designed to isolate one feature/edge case.

### Licensing-safe representative decks

Realistic business/technical presentations covering themes, charts, diagrams, notes, and mixed content.

### Private dogfood corpus

Real internal/tester decks used only under appropriate permissions. Results/feature inventories may be retained without publishing deck content.

## UX validation tasks

Test users should complete scenarios without coaching:

1. import a real deck and identify any compatibility limitations;
2. change text and image content;
3. move/reorder slides;
4. ask AI to revise the selected slide;
5. reject or revise an AI proposal;
6. rehearse and apply a rehearsal-derived suggestion;
7. undo and redo a direct edit, then restore a prior revision;
8. export and open the result in PowerPoint.

## Security/adversarial tests

Include:

- malicious/oversized ZIP structures;
- external relationships;
- embedded files;
- prompt injection text inside slides/notes;
- malformed XML;
- duplicate relationship IDs;
- extreme coordinates/font sizes;
- stale AI plans after direct edits;
- AI references to nonexistent object IDs;
- generated plans attempting unsupported operations;
- remote provider unavailable during edit planning.

## Go/no-go gates

### Gate 1 — invest in fidelity engine

Proceed from PW0 only if integrated editing is a frequent user need and rehearsal regularly creates edit intent.

### Gate 2 — ship direct editing dogfood

Require:

- no-op corpus round trip is reliable;
- unsupported content preservation works;
- immutable original recovery works;
- direct editing operations are reversible;
- export validation catches corrupt output.

### Gate 3 — enable AI mutation

Require:

- typed transaction layer is stable;
- direct editing and export are already trustworthy;
- stale-plan protection works;
- review policy is enforced by core, not only UI;
- provider privacy boundary is reused.

### Gate 4 — claim primary preparation workspace

Require evidence that users can stay inside Presenter Copilot for the large majority of preparation work and exported decks remain dependable in PowerPoint workflows.

## Release-blocking defects

Examples:

- silent loss of unsupported imported content;
- valid import followed by corrupt export;
- editing one slide materially changes untouched slides;
- AI changes wrong slide/object due to stale selection;
- generated claim displayed as source-backed without evidence;
- revision restore cannot reproduce a prior deck;
- Live/Run session silently changes revision after start.

## Earlier integrated preview comparison refresh (2026-10-02)

The integrated preview was rerun after adding bounded theme background
image-fill resolution. The 33-record run compared 31 decks / 613 slides,
skipped two external-relationship records, failed on none, and recorded 21
unstable PowerPoint captures. Thirty-five SmartArt images were promoted and
one theme background image fill was resolved. Corpus medians were 13.8487%
changed pixels, 2.7614% normalized RGB MAE, and 18.572 dB PSNR; all 613
comparable slides still had stable differences. The latest targeted and
aggregate evidence is in [`CORPUS.md`](CORPUS.md) and
[`PPTX_FIDELITY.md`](PPTX_FIDELITY.md). This rerun does not satisfy the visual
acceptance gate.

## Focused theme-background follow-up (2026-10-02)

The compare harness initially rejected `theme-background-only` even though
the preview entry point and Core comparison CLI supported that mode. The
renderer harness allowlist is now aligned, and a focused comparison of record
`90000008` completed for all 24 slides with no unstable PowerPoint captures.
The slide-5 Office reference was independently regenerated in a new read-only
PowerPoint COM session and matched the prior PNG SHA-256
(`e04fcd0262d4c0f3a8ba85f473ba76edcdc107c1bb1f0fae666a56c3d67754c3`). The
master relationship and image now load, but the rasterized preview fill is
still visibly too dark: on slide 5 the top-left background pixel is RGB
`(4, 4, 4)` in the preview and `(34, 34, 34)` in the Office capture. This
confirms a reproducible appearance mismatch without isolating whether theme
color resolution, effect math, color management, or another rendering detail
is the cause. No empirical brightness adjustment has been accepted. The
compatibility counter alone does not prove visual correction, and the
conversion remains a fidelity blocker until supported rendering matches
PowerPoint and the broader corpus shows no material regressions.

A follow-up inspection of the original 1920x1080 JPEG and dimension-matched
960x540 captures confirms the mismatch at corresponding background pixels:
source `(0, 0)` is `(218, 218, 218)`, while PowerPoint renders `(34, 34, 34)`
and the candidate rasterizer renders `(4, 4, 4)`; at `(900, 500)`, the source
pixel at the corresponding doubled coordinate is `(59, 59, 59)`, PowerPoint
renders `(9, 9, 9)`, and the candidate renders `(1, 1, 1)`. Saved read-only
PowerPoint probes varying the `p:bgRef` grayscale from 0 through 255 also
produce a non-linear output response: the slide's top-left pixel progresses
from 34 at grayscale 0 to 246 at grayscale 255, with intermediate values
34, 34, 36, 37, 40, 48, 71, and 127 for grayscale 1, 2, 4, 8, 16, 32, 64,
and 128. The source and Office captures are dimension-aligned, and the original
reference SHA remains stable. This narrows the issue to PowerPoint's handling
of the placeholder color in this theme effect, but does not identify a
portable transform. Theme-background image-effect normalization remains
enabled only in the comparison harness and focused renderer tests; the live
Workspace renderer does not opt into it. No runtime change is justified by
these probes.

## Ellipse picture-fill follow-up (2026-10-02 UTC)

The preview now normalizes only simple ellipse-clipped pictures with bounded,
internal stretched image media. Non-ellipse preset geometry, custom paths,
ambiguous picture structures, and invalid or oversized media stay unchanged.
Compatibility tests, TypeScript typecheck, and the production renderer build
passed. The paired 33-record comparison completed with 31 decks / 613 slides,
two external-relationship skips, zero failures, and 21 unstable Office
captures. Across the 592 slides stable in both reports, MAE improved on four,
had small increases on two, and was unchanged on 586. Stable differences
remain on every comparable slide, so visual acceptance is still open. Detailed
evidence and the report path are in [`CORPUS.md`](CORPUS.md).

## Auto-fit font-size rounding experiment (2026-10-02 UTC)

A preview-only experiment rounded run and paragraph font sizes to whole points
for text bodies with reduced `a:normAutofit` scales. It compared 31 decks / 613
slides against the same 33-record corpus run, with 21 unstable PowerPoint
captures in each run. Of the 592 slides stable in both runs, MAE improved on
69, regressed on 60, and was unchanged on 463; 11 regressions exceeded 0.1
percentage points and two exceeded 0.5 points. The largest was record
`90000004`, slide 26 (6.6218% to 8.9218%). Record `2651704`, slide 21 improved
from 12.1435% to 10.2082%, but this isolated win did not generalize. A
dimension-matched 960×720 PowerPoint export reproduced the reported slide-26
metrics. The broad rounding rule was removed; the accepted preview continues
to apply only its existing word-wrapping adjustment. No PPTX source or export
bytes were changed by the experiment. Reports remain in ignored
`.local/preview-compare-33-current-tree-20261002.json` and
`.local/preview-compare-autofit-20261002.json`.

## Recorded rehearsal comparison (2026-10-03)

The Rehearsal inspector compares two deck-bound ended sessions through their
verified frozen revision snapshots, matching stable slide identities across
reordering. It presents recorded metrics and signed deltas, absent/deleted
slides, unmapped counts, differing analysis versions and potential storage caps.
It does not measure semantic improvement. Core coverage includes actual Run
markers/debriefs plus synthetic stored observations for boundaries, missing or
unrelated sessions, stale revisions and malformed debrief identities. The API
is read-only and verifies the current head again before returning.

Fresh `pnpm check` passed formatting/lint/typing, 101 desktop tests and 517 Core
tests (80.89 seconds): `.local/rehearsal-compare-check-20261003.log`. Electron
exercises two GUI rehearsals on successive revisions, compares two versus one
marker and a −1 change, and navigates to the matching current slide. This does
not prove physical speech capture, live provider performance, human preparation
improvement or release readiness. No new package was built.

Final `pnpm test:ui` passed 29 workflows, with the comparison screenshot
inspected and totals checked for inspector-width overflow. Desktop lint and
TypeScript passed after the final comparison-only layout adjustment. Evidence:
`.local/rehearsal-compare-ui-20261003.log` and
`.local/ui-validation/workspace-rehearsal-comparison.png`.

## Coordinated created targets (2026-10-03)

Plans can refer to native slide/object IDs created by earlier steps, including
creating a slide, inserting a text box and styling/positioning it. Scope,
wrong-kind, forward, deleted and cross-slide target checks retain cleanup and
revision safety. Provider preconditions bind to each actual staged snapshot.
Creation IDs enter transaction audit; exact preview/save and whole-plan undo
remain required. Five new chain cases join existing planning checks.

Fresh `pnpm check` passed formatting/lint/typing, 101 desktop tests and 522 Core
tests (77.91 seconds): `.local/created-targets-check-20261003.log`. Electron
passed 30 workflows, including coordinated callout creation, native preview,
style inspection after save and complete removal on undo. Its initially cropped
screenshot was transient; native PNG inspection showed a complete slide. Review
now counts a slide as viewed after image decoding and the paint cycle.
The full dialog and native PNG were inspected:
`.local/ui-validation/workspace-copilot-created-callout.png` and
`.local/ui-validation/workspace-copilot-created-callout-native.png`.
The final workflow log is `.local/created-targets-ui-20261003.log`.
Deterministic fixtures do not establish live-provider edit quality or production
fidelity thresholds; no package was rebuilt.

## Reviewed voice outline briefing/refinement (2026-10-03)

New-deck planning now owns project-scoped local capture before a deck exists.
Core rejects deck-target fields for outline intent, verifies the project around
capture, and retains revision/selection checks for existing editing intents.
Synthetic PCM coverage proves ephemeral output, cross-project ownership,
invalid-field rejection, no durable capture/provider/deck rows, and actual
project-deletion cleanup. Ten focused voice tests pass.

Fresh `pnpm check` passed formatting/lint/typing, 101 desktop tests and 523 Core
tests (76.02 seconds): `.local/voice-outline-check-20261003.log`. Desktop lint
and typing passed again after tightening outline/edit prop types. Electron
passed 31 workflows: `.local/voice-outline-ui-20261003.log`, including silent
fixture capture, cancellation, proposal/mode locking, briefing/refinement length
limits, unchanged briefing until explicit Use, then separate provider proposal,
refinement, review and native creation. Screenshot inspected:
`.local/ui-validation/workspace-voice-outline-briefing.png`.

The GUI corrects an empty synthetic transcript; it does not prove microphone
recognition or natural speech latency. Objective and audience stay typed;
automatic confidence/ambiguity handling, shortcuts, live-provider quality,
semantic improvement and release/fidelity gates remain open. No package rebuilt.

## Native object layering (2026-10-03)

Four focused Core cases exercise forward, backward, front and back on three
native text boxes. They verify exact order, unchanged object XML contents and
other package bytes, stale order/revision rejection, boundary no-ops, undo and
unchanged external input. All 25 provider planning cases pass after adding a
layer operation targeting an earlier created object and checking Core-bound
staged order. The direct cases establish actual multi-object reorder behavior;
the created-target case establishes binding through the plan chain.

Fresh full check passed formatting/lint/types, 101 desktop and 527 Core tests
(100.74 seconds): `.local/object-layer-check-20261003.log`. The added provider
test step was run separately afterward. Electron passed 32 workflows:
`.local/object-layer-ui-20261003.log`. The added GUI case sends a created text box
to the back, keeps selection, checks the inventory order, verifies a boundary
move creates no revision, and undoes layering independently from creation.
The inspected `.local/ui-validation/workspace-object-layer-back.png` shows the
four controls fit the inspector. Opaque overlap rendering, unsupported object
editing and external PowerPoint acceptance are not established by this fixture.

## Reviewed multi-object layout (2026-10-03)

The 11 new desktop cases verify unequal-size alignment in six directions,
unequal-width spacing with fixed outer positions, integer rounding, unchanged
output and rejection of invalid selections or negative gaps. Twenty Core
transaction cases pass, including multi-object stale-second-operation rollback,
staged-preview/saved-revision SHA identity, preserved object order and batch undo.
Full `pnpm check` passed formatting/lint/types, 112 desktop and 528 Core tests
(89.67 seconds): `.local/object-layout-check-20261003.log`. Electron passed 33
workflows: `.local/object-layout-ui-20261003.log`, including the new checklist,
invalid selection, cancel, native preview without head mutation, image-load and
acknowledgment gates, single-revision save and whole-batch undo. Screenshot:
`.local/ui-validation/workspace-object-layout-review.png` was inspected.

The existing layering GUI assertion now waits for the refreshed inventory
rather than assuming the new revision label means object loading finished.
No external PowerPoint rendering, canvas multi-selection, grouping/snapping,
physical voice or live model quality is established by these fixtures.

## Native canvas selection (2026-10-03)

Full check passed format/lint/types, 112 desktop and 528 Core tests (81.36
seconds): `.local/canvas-selection-check-20261003.log`. Electron's 34 workflows
pass with click, modifier add/remove, keyboard additive selection, inspector
population, selection prefill in reviewed alignment, cancel, Escape, reverse
marquee and overlay disable. Evidence: `.local/canvas-selection-ui-20261003.log`.
The inspected `.local/ui-validation/workspace-canvas-object-selection.png` shows
five native objects outlined on the letterboxed slide and a compact toggle.

Screenshot inspection corrected inherited checkbox width. A later marquee
failure prompted direct release-coordinate calculation and a test scroll into
view; corrected GUI coverage passes, with final type/format checks afterward.
The fixture uses flat native shapes. It does not prove rotated/grouped object
picking, arbitrary corpus hit accuracy, drag repositioning, real touch-device
acceptance or external PowerPoint fidelity. Selection only changes GUI state;
reviewed transforms retain the earlier Core atomicity/stale-target guarantees.

The corrected product also passed a second complete 34-workflow run with the
final asynchronous selection wait: `.local/canvas-selection-ui-final-20261003.log`.

## Embedded deck picture reuse (2026-10-03)

Three new Core cases verify thumbnail bounds, mixed valid/invalid media skips,
asset content hashes, reuse on another slide, unchanged original/untouched slide,
21-image pagination, invalid cursors, stale and cross-project requests, unknown
IDs/path fields and snapshot tampering. The existing native image validator is
reused for format, single-frame, dimension/pixel and 4 MiB limits. Pages bound
20 accepted images, 100 scanned entries and 16 MiB input; no external fetch occurs.

Full `pnpm check` passed format/lint/types, 112 desktop and 531 Core tests
(85.74 seconds): `.local/deck-assets-check-20261003.log`. Electron passed 35
workflows: `.local/deck-assets-ui-20261003.log`, including browse, displayed
thumbnail, selection with unchanged revision and native insertion of the reused
PNG. Inspected screenshot: `.local/ui-validation/workspace-deck-picture-assets.png`.
This fixture does not establish project-wide asset ingestion, provider image
understanding/attachment or external PowerPoint visual acceptance.

## Attached deck images in provider plans (2026-10-03)

Twenty-nine focused planning cases pass. Four new cases verify a Core-bound
attached image saves as the exact preview hash and undoes; unattached provider
IDs, duplicate input attachments and stale revisions reject without mutation.
Provider context and public proposal omit image/thumbnail bytes. Audit excludes
raw image fields. Full check passed format/lint/types, 112 desktop and 535 Core
tests (96.98 seconds): `.local/plan-assets-check-20261003.log`. Final metadata
review display changes passed typing and focused planning checks afterward.

Electron passed 36 workflows: `.local/plan-assets-ui-20261003.log`. The added
image case browses/attaches, renders the native proposal, reviews, confirms save
is enabled, removes the attachment to invalidate approval and discards without
revision. Core tests establish image commit/undo; GUI exercises discard for this
image case and continues ordinary plan save coverage. Inspected screenshot:
`.local/ui-validation/workspace-copilot-attached-picture.png`. These deterministic
fixtures do not establish live provider image-placement quality or external
PowerPoint rendering. Providers receive metadata only, not visual image input.

## Reviewed canvas translations (2026-10-03)

Five new desktop cases verify group translation with preserved spacing/sizes,
both-edge clamping, integer/grid rounding with boundary exceptions, single/zero
moves and invalid selections/geometry/nonfinite values. Full check passed
format/lint/types, 117 desktop and 535 Core tests (90.70 seconds):
`.local/canvas-move-check-20261003.log`. Electron passed 37 workflows:
`.local/canvas-move-ui-20261003.log`, including a real two-object pointer drag,
reviewed native preview without head mutation, acknowledgment gate, one-revision
save, batch undo and cleared selection after revision reload. Existing Core
multi-object transaction cases cover stale-second-operation rejection and exact
preview-byte commit. Screenshot inspected:
`.local/ui-validation/workspace-canvas-drag-review.png`.

An old layering order assertion now waits for the object inspector to finish
loading. These fixtures do not prove real touch-device behavior, grouped/rotated
object editing, advanced guide snapping, live bitmap movement or external
PowerPoint fidelity. Dragging moves outlines and opens native staged review.


## Reusable project uploads (2026-10-03)

Full `pnpm check` passed format/lint/types, 117 desktop and 540 Core tests
(91.08 seconds): `.local/project-assets-check-20261003.log`. Four new Core cases
verify project isolation/content deduplication, persistence across restart before
any deck exists, invalid-upload rejection/stored-byte integrity, v13 preservation
and failed-migration rollback, 200-image pagination/count rejection and deduplication
at capacity. Existing native image tests cover the shared image validator.
Legacy migration fixtures now include the v14 table, latest schema assertions
and rejection of future v15.

A fifth planning variant binds a project-library image while excluding bytes from
provider/public/audit payloads, deletes the library item after preparation, opens
native preview, commits its exact hash and undoes. This verifies staged copies
survive removal. Electron passed 39 workflows:
`.local/project-assets-ui-20261003.log`. Upload, selection and confirmed removal
leave the deck revision unchanged. Copilot attaches the project image, renders
the native proposal, requires acknowledgment, invalidates save on attachment
removal and discards without a revision. Inspected screenshot:
`.local/ui-validation/workspace-project-picture-library.png`.

These deterministic fixtures do not establish live model image-placement quality,
visual image understanding, cross-application rendering or standalone pre-deck
library GUI acceptance. No provider/network/account acceptance, signing, clean
Windows validation, commits, pushes or packaging occurred in this increment.


## Reviewed claim spans and evidence coverage (2026-10-03)

Full `pnpm check` passed formatting/lint/types, 117 desktop and 544 Core tests
(86.00 seconds): `.local/claims-check-20261003.log`. Four new Core cases cover
restart persistence, exact object/span and evidence snapshots, text/source drift,
stale revision/hash rejection, reviewed rebind, removal/undo, invalid claims and
foreign links, v14-to-v15 preservation, and explicit incomplete status after 102
parent revisions. Final focused checks also verify context-only/contradictory/
supporting coverage and rejection of overlapping ambiguous quotes:
`.local/claims-focused-20261003.log` (four passed). Final static checks passed:
`.local/claims-final-static-20261003.log`.

Electron passed 41 workflows: `.local/claims-ui-20261003.log`. New cases save a
reviewed exact object quote and source excerpt/relation without changing revision
1, then native title replacement creates revision 2 and inherited coverage needs
review with the changed object marked. Checkbox gating and layout overflow checks
passed. Screenshots inspected:
`.local/ui-validation/workspace-claim-evidence-review.png` and
`.local/ui-validation/workspace-claim-evidence-needs-review.png`.

Coverage reflects user judgment, not measured entailment/decision accuracy.
Automatic claim extraction, semantic evidence search, narrative/deck-wide coverage
and integration into provider authoring/rehearsal context remain open. Existing
fast decision and Sign in with ChatGPT deterministic checks run in the full suite;
live account/model/latency acceptance remains unverified. No commits, pushes,
packaging, external account calls, signing or clean Windows validation occurred.


## Reviewed claim grounding in provider workflows (2026-10-03)

Full `pnpm check` passed format/lint/types, 117 desktop and 549 Core tests
(90.86 seconds): `.local/claim-context-check-20261003.log`. Five new Core cases
verify reviewed source text/hash injection, content-free manifest source IDs,
stale snapshot exclusion, actual Challenge question generation using its frozen
revision after a Workspace title edit, current-head GUI rejection, bounded
context/incomplete status, local-only remote blocking and removal of citation
IDs for links excluded by grounding caps. Linked transcript metadata retains
its source class/unit identity. Frozen revision IDs enter context manifests.
Focused context/planning/Challenge checks passed 57 tests:
`.local/claim-context-focused-20261003.log`.

The first GUI attempt passed grounding review but failed a later voice-edit plan
with a generic error. A copied disposable-profile Core reproduction succeeded;
no root cause was established. Copilot now exposes structured Core messages.
The next and final reruns passed all 42 workflows. Final evidence:
`.local/claim-context-ui-final-20261003.log`. The new case shows reviewed claim
coverage and supplied excerpt status in a native proposal, then discards without
a deck revision. Inspected screenshot:
`.local/ui-validation/workspace-copilot-reviewed-claim-grounding.png`. Final
shortened-quote review label passed typing afterward:
`.local/claim-context-final-types-20261003.log`.

Context is bounded to five slides, eight claims/6000 claim characters, 500-character
quote excerpts and normal excerpt/document budgets. Incomplete and shortened
context is explicit. Provider quality, entailment accuracy, frozen-session real
human behavior, live fast-decision latency and Sign in with ChatGPT account
acceptance remain unverified. No commits, pushes, packaging, external account
calls, signing or clean Windows validation occurred in this increment.


## Finite claim/excerpt triage (2026-10-03)

Focused shared decision/purpose checks passed 63 tests, and final triage/metric
checks passed 19 tests. Coverage includes threshold edges, missing confidence,
exact text packets, no automatic semantic/revision writes, stale/foreign source,
privacy rejection/change, malformed output, success/error audit completion and
double-flag developer fixture gating. Synthetic metrics count costly accepted
false supports and report absent selective precision at zero coverage.

Electron passed 43 workflows (`.local/triage-ui-20261003.log`). Its explicit
fixture proves request/use/review separation and preserves existing save flows;
it provides no model-quality evidence. Inspected
`.local/ui-validation/workspace-claim-evidence-triage.png`.

`benchmark:claim-triage-local --provider-id ollama_systemone --timeout-seconds 0.5`
failed its first case with DECISION_PROVIDER_TIMEOUT and zero valid responses
(`.local/triage-local-acceptance-20261003.log`). No real accuracy or latency was
measured. The 20 self-authored synthetic cases are diagnostic only. Production
quality requires human-labeled evidence, calibration and measured selective
precision/coverage/costly error/latency. Live ChatGPT account and corpus integration
acceptance remain open; signing and clean Windows validation are accepted debt.

Full final check passed formatting/lint/types, 117 desktop and 568 Core tests
(114.24 seconds): `.local/triage-check-final-20261003.log`. `git diff --check`
also passed. Dirty worktree preserved without commits or release changes.


## Reviewed presentation narrative (2026-10-03)

Narrative/context/storage/claims focused checks passed 31 tests, then 91 focused
narrative/history/migration/Challenge checks passed. They cover restart persistence,
no slide revision on semantic save, exact-revision review, token conflicts, invalid
fields/limits/NUL/review/scope, stale head, explicit clears, undo/branch isolation,
bounded history, serialized escaping limits, coexistence with reviewed claims,
content-free provenance, actual frozen Challenge generation and local-only remote
blocking. Schema 16 migration preserves existing claims and project rows; future
schemas remain rejected without mutation.

Initial UI failure was an async reload assertion reading the still-cleared draft;
the test now waits for restored text. Screenshot review caught default button
styling and a stretched checkbox; existing classes and a compact checkbox correct
these. Final full check passed formatting/lint/types, 117 desktop and 581 Core tests
(123.55 seconds): `.local/narrative-check-final-20261003.log`. Final Electron run
passed 45 workflows: `.local/narrative-ui-complete-20261003.log`. Editor and
controls screenshots were inspected:
`.local/ui-validation/workspace-reviewed-narrative.png`,
`.local/ui-validation/workspace-reviewed-narrative-controls.png`. The final
screenshot/overflow additions passed targeted ESLint; `git diff --check` passed.
Synthetic/provider fixtures establish transport and UI behavior only. Automated
narrative analysis, human-session quality, corpus integration, fast-decision
latency and live ChatGPT account acceptance remain open. Signing/clean Windows
validation remain accepted tech debt.


## Paged deck semantic review (2026-10-03)

Full check passed format/lint/types, 117 desktop and 590 Core tests (105.47 seconds):
`.local/deck-review-check-20261003.log`. Focused page/source/claim/context checks
passed 68 tests (`.local/deck-review-focused-20261003.log`). Final extended history
and page/claim cases passed 13 tests (`.local/deck-review-history-20261003.log`),
with final format/lint and `git diff --check` passing. One inspection per page,
pagination/count scope, no revisions on read, inherited/exact purpose states,
changed evidence/conflict/removal/undo, unknown fields/scope/limits, changed snapshot,
revision mutation during page read and incomplete history are covered.

Electron passed 47 workflows (`.local/deck-review-ui-20261003.log`). New cases
exercise attention filtering, second-page slide 21 review, return to slide 1,
retained claim state, and inherited purpose/changed claim coverage after a native
text edit. Panel overflow check passed. Inspected
`.local/ui-validation/workspace-deck-review-page.png` and
`.local/ui-validation/workspace-deck-review-inherited.png`.

Counts are page-scoped reviewed records, not automatic discovery or accuracy.
Corpus/Office fidelity, human-session acceptance, model calibration, live fast
latency and ChatGPT account integration remain open. Signing and clean Windows
validation remain accepted debt. No commits, pushes, packaging or account calls.


## Review-only narrative analysis (2026-10-03)

Full check passed format/lint/types, 117 desktop and 606 Core tests (104.55 seconds):
`.local/narrative-analysis-check-final-20261003.log`. Focused existing/new narrative,
planning and claim-context cases passed 40 tests:
`.local/narrative-analysis-focused-20261003.log`. New cases cover native text/notes
scope, 40-slide/range bounds, shortening, strict schema/role limits, supplied
slide/citation IDs, no semantic/revision writes, preserved unsaved intent and
pre/postflight head, record-token, snapshot and privacy rejection. Local loopback
transport validates strict schema, 4096-token task budget and no tools. It does
not establish real model quality or latency.

Electron passed 48 workflows (`.local/narrative-analysis-ui-final-20261003.log`): partial
coverage disclosure, unchanged draft on request/discard, explicit use, finding
navigation, acknowledgment-gated save and unchanged native revision. Proposal
fields and lower-control screenshots inspected:
`.local/ui-validation/workspace-narrative-suggestion-review.png` and
`workspace-narrative-suggestion-controls.png`. No horizontal overflow; final GUI
script formatting/targeted lint and `git diff --check` passed. Human
preparation usefulness, live ChatGPT account/inference, real fast-decision quality/
latency and corpus fidelity/integration remain open. Signing and clean Windows
validation remain accepted debt.


## Reviewed slide takeaways (2026-10-03)

Focused takeaway/narrative/deck/storage checks passed 39 tests:
`.local/takeaway-focused-20261003.log`. Extended bounded-history and takeaway cases
passed 12 tests in 3.41 seconds: `.local/takeaway-history-20261003.log`. Scope covers
restart persistence, conflict tokens, explicit blank clears, inherited review, undo/
branch selection, native identity/input rejection, schema-16 migration retaining
intent, older-project upgrades and the 100-parent missing-history limit.

Electron passed 50 workflows (`.local/takeaway-ui-complete-20261003.log`). Finding
navigation leaves the takeaway blank until explicit Use; corrected drafting requires
acknowledgment and separate save/reload. A real edit marks retained text inherited;
draft clear/reload is reversible and reviewed blank save refreshes deck review.
Inspected `.local/ui-validation/workspace-reviewed-slide-takeaway.png` and
`workspace-inherited-slide-takeaway.png`. Final GUI script format/lint and Core lint
passed. Full `pnpm check` passed format/lint/types, 117 desktop and 617 Core tests
(120.69 seconds): `.local/takeaway-check-complete-20261003.log`. Older migration
fixtures were updated for the new table and supported schema; the two cases passed
independently (`.local/takeaway-migration-final-20261003.log`). Final GUI generation
guard rejects late read/reload/save responses during repeated effects/unmount.
TypeScript/lint and 117 desktop tests passed after that guard
(`.local/takeaway-desktop-final-20261003.log`); final GUI rerun passed 50 workflows. This proves fixture GUI/transport behavior rather than human
usefulness or model quality. Provider/rehearsal integration, corpus fidelity, real
fast-decision quality/latency and live ChatGPT account acceptance remain open.


## Reviewed takeaway provider context (2026-10-03)

Full check passed format/lint/types, 117 desktop and 623 Core tests in 127.70 seconds:
`.local/takeaway-context-check-20261003.log`. Focused context/narrative/claim checks
passed 24 tests in 6.79 seconds (`.local/takeaway-context-focused-20261003.log`).
Final mixed claim/intent case and context checks passed six tests in 8.84 seconds
(`.local/takeaway-context-mixed-final-20261003.log`); Core lint passed afterward.
Coverage includes proposal capture versus later intent saves, claim-pruning merge
preservation, intent excluded from evidence/audit content, frozen Challenge
question/evaluation after head edits, inherited status, shortened text, clear records,
project/revision/package verification, local-only remote rejection, five-slide scope
and escaping-aware 3200-character section limits. Existing complete-answer and
shared total-context limits remain enforced; excessive combined required context
rejects rather than silently shortening the current answer.

Electron passed 51 workflows (`.local/takeaway-context-ui-final-20261003.log`), including
reviewed takeaway text/status in Copilot's captured intent section. Inspected
`.local/ui-validation/workspace-copilot-takeaway-context.png`; takeaway, narrative
and claim sections are readable. Final GUI script format/lint and
`git diff --check` passed. Synthetic provider tests prove workflow/transport only.
Human/model quality, live ChatGPT account acceptance, measured fast-decision latency,
Run/debrief intent integration and corpus fidelity remain open.


## Native master/layout catalog and reviewed application (2026-10-03)

Full check passed format/lint/types, 117 desktop and 632 Core tests in 113.30 seconds:
`.local/native-layout-check-complete-20261003.log`. Final focused native-layout/
transaction checks passed 31 tests in 9.40 seconds:
`.local/native-layout-focused-final-20261003.log`. The final set adds catalog-read
head/snapshot races after the full check. Coverage includes all 11 standard native
layouts, unused Comparison application, review-only staging, preview-hash commit,
byte-identical untouched parts (only target slide relationships differ), no-op,
undo, malformed/foreign IDs, ambiguous selection, external/mismatched/duplicate
master references and unchanged slide objects/notes/order.

Electron passed 52 workflows (`.local/native-layout-ui-reviewed-20261003.log`),
including unused discovery, review preview, choice-change approval invalidation,
discard/restore, exact reviewed save/reindex and undo. Inspected
`.local/ui-validation/workspace-native-layout-preview.png`. Final GUI rerun after
a post-save resubmission guard passed 52 workflows; TypeScript/targeted lint and
117 desktop tests passed afterward (`.local/native-layout-desktop-final-20261003.log`).
`git diff --check` passed.
PowerPoint opened the generated unused-Comparison two-slide candidate, verified
content/notes/count, exported slide 1 and left the file hash unchanged. Inspected
`.local/native-layout-office/slide-1.png`; evidence is `result.json` and
`.local/native-layout-office-20261003.log`. Wider multi-master, placeholder styling,
corpus fidelity, human usefulness, live ChatGPT integration and fast-decision quality/
latency remain open. Signing/clean Windows validation remain accepted debt.


## Native layout creation and notes master consistency (2026-10-03)

Full check passed 117 desktop and 652 Core tests (130.96 seconds), including the
shared notes-master correction: `.local/native-create-check-final-20261003.log`.
Final focused layout/authored/transaction suite passed 59 (18.85 seconds):
`.local/native-create-focused-reviewed-20261003.log`. The additional malformed-index/
foreign-transform checks bring the next full Core baseline to 654. Core lint/mypy
and git diff --check passed after final guards. Coverage includes editable five-slot
Comparison creation/notes, empty slots and subsequent created-target edits, unchanged
existing native parts, exact staged commit/undo, invalid slot/layout IDs, bounds,
unsupported transforms and notes-master allocation/reuse/ambiguity rejection.

Electron passed 53 workflows: `.local/native-create-ui-final-20261003.log`. New case
covers discovery/drafts, rendered native creation, edited-draft invalidation,
discard, reviewed save, new-slide selection and undo. Inspected
`.local/ui-validation/workspace-native-slide-preview.png`. An early assertion waited
for a hidden dropdown option to be visible; corrected to attachment. A later repeat
after submit guards timed out in an earlier alignment undo workflow. The isolated
final repeat passed all 53 workflows: `.local/native-create-ui-complete-20261003.log`.
All native fixture and authored regression renders were inspected.

PowerPoint opened native Comparison creation for 4:3, 16:9 and a deck without prior
notes master, verified text/paragraphs/notes and slide count, and exported renders
without modifying package hashes. Each native slide has zero pixel difference
against an independently created native reference slide. Authored insertion with
an existing master also opens/retains notes after the shared correction. Evidence:
`.local/native-create-office/result.json`, `*-native.png`, `*-reference.png` and
`.local/native-create-office-final-20261003.log`. The initial Office failure isolated
the shared notes helper registering a new master inconsistent with existing notes;
reuse fixes it, with final full regression coverage. Only those fixtures are proven.
Enterprise master/notes styling, wider corpus fidelity, human preparation acceptance,
real fast decision quality/latency and live ChatGPT authentication remain open.


## Native table creation, imported cell editing and retrieval (2026-10-03)

Final full pnpm check passed formatting/lint/types, 117 desktop and 679 Core tests
in 114.89 seconds: `.local/native-tables-check-final-20261003.log`. Earlier full
run passed 674 and failed the shared capability ready-event fixture; synchronized
both method lists to the three new IPC endpoints. Final focused table suite passed
24 in 2.75 seconds (`.local/native-tables-focused-final-20261003.log`) before one
additional invalid XML character case; the final full suite passes all 25. Coverage
includes staged creation/atomic commit, native cell content/paragraph editing,
unchanged package members/old objects/styles/dimensions/notes, retrieval refresh,
no-op, undo, stale fingerprints, corrupt source/head race, bounds/content limits,
unsupported merged/linked/mixed-run/extended cells and an imported table with custom
fonts and unequal column widths. An incorrect table graphic URI initially prevented
reindexing; corrected against the installed parser and covered by retrieval checks.

Electron passed 54 workflows (`.local/native-tables-ui-20261003.log`), including
creation/draft edits, native preview, review invalidation, discard, persisted table
selection, multiline editing, retrieval refresh and undoing both edit and insertion.
Inspected `.local/ui-validation/workspace-native-table-edit.png`. PowerPoint opened
4:3 and 16:9 two-slide fixtures, verified true 3x3 native table cells, multiline
edited value, header font, placement and preserved notes, exported native renders
and left input hashes unchanged. Evidence: `.local/native-tables-office/result.json`,
`standard-table.png`, `wide-table.png` and `.local/native-tables-office-20261003.log`;
both renders inspected. Arbitrary complex tables and corpus fidelity are unproven.
No accounts/model calls, packaging or releases occurred; signing and clean Windows
validation remain accepted debt. Real fast decisions and live ChatGPT sign-in
acceptance remain open.


## Native chart creation acceptance (2026-10-03)

Slide actions & layout now offers Insert native chart. Draft a column, bar, line
or pie chart, title, category/series names, values and placement, then preview the
actual staged PPTX, explicitly review and save one revision. Draft changes clear
approval; discard leaves the baseline unchanged; saving refreshes retrieval; undo
restores the complete prior deck. The chart is a native editable graphic frame
with its own embedded literal-data workbook, not a chart image. Limits: 1–24
categories, 1–6 series, names 80 characters, title 120, finite values within ±1e12.
Pie charts require one nonnegative series with a positive total. New IPC and
transaction operation: create_chart (22 native transaction types). No migration;
project schema remains 17. Provider edit-plan schemas remain unchanged.

Dependencies considered: current-head/source verification, native shape identity,
geometry and object bounds, fresh slide/chart/workbook relationships and content
types, cache/workbook consistency, unrelated package parts/objects/notes, literal
formula/URL-like labels, staged exact-byte commit, draft invalidation, cleanup,
reindex/undo and read-only cached chart text. python-pptx generates only a tiny
owned chart fixture; imported decks stay under verified native XML/archive copy.
The generated XLSX contains literal strings/numbers, no formulas/external links.
Cache text includes supplied labels/values without inferred trends or external
workbook access. Unsupported/stacked/combo/missing-cache charts stay outside this
bounded reader. Existing chart data/geometry editing, other chart types, structural
table changes, broader object workflows and corpus/human acceptance remain open.

Validation evidence: focused 23 Core chart cases passed in 2.81 seconds at
`.local/native-charts-focused-final-20261003.log`. Covers four native chart types,
package preservation, cache/workbook literal labels, staged apply, searchable data,
undo, numeric/pie/name bounds, fractional precision, enormous integer rejection,
unsupported stacked/combo/cache-gap cases and negative line values. Four desktop
adapter tests verify authored-pie palette isolation and unsupported/imported skip.
Final pnpm check passed formatting/lint/types, 121 desktop and 702 Core tests
in 127.29 seconds: `.local/native-charts-check-final-20261003.log`.
Electron passed 55 workflows at `.local/native-charts-ui-final-20261003.log`, including
line/column/pie preview, edited-value approval invalidation, discard, reviewed save,
retrieval refresh and undo. Inspected `workspace-native-chart-column.png` and
`workspace-native-chart-pie.png` in `.local/ui-validation`. Screenshot inspection
caught a pie legend palette mismatch/title overlap; a bounded chart-local preview
adapter now aligns authored-pie legends with direct slice colors and explicit title
placement separates the text. Imported charts/themes remain untouched. Pie plot
spacing still differs from PowerPoint, so this is not pixel-fidelity acceptance.

PowerPoint opened and exported four two-slide fixtures across 4:3/16:9, verified
native charts and exact chart types, series counts/cache values, title, placement
and retained notes,
and left file hashes unchanged. All renders inspected; fixture Office instances
closed. Evidence: `.local/native-charts-office/result.json`, `check.log`, and
`column-chart.png`, `bar-chart.png`, `line-chart.png`, `pie-chart.png`. This proves
these fixtures, not arbitrary imported charts or enterprise corpus acceptance.
Dirty worktree preserved; no commits/pushes, packaging, accounts/model calls,
downloads or releases. Next: remaining substantial chart/table/object GUI workflows,
then broader fidelity/integration acceptance. Real fast-decision calibration/latency,
human preparation acceptance and live Sign in with ChatGPT remain open. Signing
and clean Windows validation remain accepted debt; full master/theme editing deferred.

## Existing native chart data editing acceptance (2026-10-03)

Native charts in Slide actions & layout now inserts charts or selects an existing
supported native chart to edit category labels, series names, values and a plain
styled title. Type, category/series counts, placement, axes, data-point styles,
labels, object identity and notes are preserved. A mixed/complex rich title stays
locked while supported values can still be edited. Native staged preview, explicit
review, draft invalidation, no-op/discard, one-revision save, reindex and whole-edit
undo are supported. The picker currently lists at most 20 direct charts per slide.
New IPC: list_charts/replace_chart_data. Native transactions now support 23 types;
provider schemas remain unchanged. Project schema remains 17; no migration.

Dependencies considered before edits: source/current-head ownership, slide/frame
identity, native relationship resolution, fingerprinted chart/frame/relationships,
embedded workbook/cache consistency, shared parts, chart styles and linked formula
references, title run/paragraph inheritance, literal formula/URL-like labels,
exact staged bytes, reindex/undo, current-head races and dialog lifetime. Each edit
clones the selected chart and its relationships, writes a new literal-data workbook
and adds a new selected-frame relationship. Original chart/workbook/package parts
stay byte-identical for other uses. Category/series counts stay fixed to preserve
point-level styling. The original embedded workbook is never opened; it is retained
alongside the replacement. Charts with linked external workbooks, additional title
or data-label workbook formulas, extension data, unsupported types or missing caches
remain read-only with a reason. Ordinary cached chart text now retains multiline
titles for creation, import, retrieval and reviewed edits.

Final pnpm check passed format/lint/types, 121 desktop and 727 Core tests in
139.84 seconds: `.local/chart-editing-check-final-20261003.log`. Focused chart suites
passed 48 in 10.96 seconds at `.local/chart-editing-focused-final-20261003.log` (25
new edit cases plus 23 creation cases). Covers all four types, imported custom
styles, shared parts on two slides, staged atomic apply/failure cleanup, literal
workbooks, unchanged package/geometry/notes, retrieval, undo, no-op, stale
fingerprint/head/IDs, source corruption, fixed structure, read-only linked/extended
or unsupported data, mixed title preservation and styled multiline title changes.
Initial retrieval assertions used a nonexistent workspace method; corrected to the
actual source.reindex endpoint. The initial full run passed 723 before the final
four linked-title/multiline/atomic-failure/corruption cases were added.

Electron passed 56 workflows: `.local/chart-editing-ui-final-20261003.log`. New case
covers existing discovery, loaded values/title, fixed structure, no-op, preview,
edited-value review invalidation, discard, reviewed save, persisted values,
retrieval refresh and undoing data edits separately from insertion. Inspected
`.local/ui-validation/workspace-native-chart-data-edit.png`. Placement controls are
hidden for data editing rather than showing creation defaults as current placement.

PowerPoint opened and exported four two-slide imported-chart fixtures, verified
native type, new values/title, preserved 23-point bold title, geometry and notes,
other-chart values and unchanged file hashes. Untouched second-slide exports are
byte-identical before/after. All edited renders inspected; Office instances closed.
Evidence: `.local/chart-editing-office/result.json`, `check.py`, `check.log` and
`column|bar|line|pie/edited-chart.png`. The first synthetic shared-chart fixture was
rejected by PowerPoint before editing; final Office fixtures use independent native
charts. Shared-part isolation is Core evidence, not PowerPoint acceptance. Broad
chart/enterprise corpus fidelity and native edit-data workbook UI remain unverified.

Dirty worktree preserved; no commits/pushes, packaging, accounts/model calls,
downloads or releases. Next: chart/table geometry and richer object/structural
editing GUI, then broader fidelity/integration/human acceptance. Real fast-decision
calibration/latency and live Sign in with ChatGPT remain open. Signing and clean
Windows validation remain accepted debt; full master/theme editing stays deferred.

## Native chart/table geometry acceptance (2026-10-03)

Supported direct native charts and tables now expose verified geometry in the
object inventory and canvas. They participate in selection, drag/align/distribute
workflows and position/size drafting. Numeric layout changes open the staged native
review dialog before saving, with explicit image review, one-revision commit,
retrieval refresh and undo. Existing shape/picture behavior is retained. Charts
change only the native frame transform. Table resizing also scales column widths
and row heights proportionally with exact positive integer totals; translation
keeps the grid unchanged. Cells, formatting, native IDs, chart cache/workbooks,
relationships, other slides and notes stay intact. No new IPC/schema/migration;
existing transform_object and reviewed-plan paths are reused.

Dependencies considered before edits: graphicFrame uses p:xfrm rather than the
shape/picture p:spPr/a:xfrm path; table grid dimensions must match the frame;
proportional rounding must retain nonempty rows/columns and exact totals; native
geometry eligibility must propagate through object parsing, canvas, review plans,
stale geometry/current-head guards, rendering, cleanup and undo. Only direct,
unrotated/unflipped, in-bounds frames with supported chart references or consistent
positive table grids are editable. Table geometry supports at most 128 columns and
256 rows, independently of the narrower cell-data editor. Alternate content,
grouped/inherited/extended/malformed frames and mismatched grids stay read-only.
Delete/duplicate/layer actions remain disabled for these frames because their
identity/relationship dependencies require separate work.

Focused geometry tests passed 10 in 1.93 seconds:
`.local/graphic-geometry-focused-final-20261003.log`. Coverage includes reviewed
chart/table movement and resizing, unchanged package parts/native content/notes,
exact grid totals, proportional unequal widths/heights, no-op, stale geometry,
invalid bounds, empty-grid rejection and undo. The initial full check passed 121
desktop and 736 Core tests before the last proportional-grid case and final GUI
wiring. Final pnpm check passed format/lint/types, 121 desktop and 737 Core tests
in 128.23 seconds: `.local/graphic-geometry-check-final-20261003.log`.
Electron passed 58 workflows: `.local/graphic-geometry-ui-final-20261003.log`.
New cases cover chart and table discovery, position/size drafting, native staged
preview, required review, exact save and undo. Inspected
`.local/ui-validation/workspace-native-chart-layout.png` and
`workspace-native-table-layout.png`. An initial run
failed during Sources navigation before reaching these new workflows. Inspected
Office evidence is `.local/graphic-geometry-office/result.json`, `check.py`,
`check.log`, `chart-resized.png` and `table-resized.png`. PowerPoint opened both
fixtures, reported the requested 1/1.5/6.5/3.5-inch geometry, retained native chart
values/title and table font/counts, matched table row/column totals, exported renders
and left file hashes unchanged. Fixture Office instances closed. This proves native
geometry for these fixtures, not enterprise chart/table fidelity or publication
quality for arbitrary chosen positions.

Dirty worktree preserved; no commits/pushes, packaging, accounts/model calls,
downloads or releases. Next: remaining native chart/table object and structural
workflows, then broader fidelity/integration/human acceptance. Real fast-decision
calibration/latency and live Sign in with ChatGPT remain open. Signing and clean
Windows validation remain accepted debt; full master/theme editing stays deferred.


## Native chart/table layers and deletion acceptance (2026-10-03)

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

Eighteen new Core cases verify four supported chart types, shared chart/workbook
preservation, styles/entries, manual/extended/malformed read-only behavior, stale
fingerprints, staged Copilot previous/proposed legend diffs, no-op/hide and exact undo.
Full sweep: 983 Core (226/311/248/198), 157 desktop; final focused guard/data run: 38.
The Electron/local Core sweep passed all 93 checks with no renderer exceptions.
Three added checks cover loading native settings, bottom-to-right draft invalidation,
fresh reviewed save, hide-preview discard, exact undo, and Copilot hidden-to-bottom
previous/proposed settings with native preview/save/re-index/undo. The test explicitly
awaits asynchronous chart discovery and reselects the metrics slide after undo.
Both direct and Copilot review screenshots were inspected. Receipts:
`.local/chart-legend/gui.log`, `gui-result.json`,
`workspace-chart-legend-right-review.png`, and
`workspace-copilot-chart-legend-review.png`. Earlier fixture encoding, loading-wait and
undo-selection failures are retained in `gui-fixture-{encoding,label,loading,slide}.log`.
Native PowerPoint verifies all five visible placements, overlay layout, hiding,
unchanged native data/title/notes, unaffected other-chart pixels and six exact undos.
Original workbook/chart parts remain byte-identical. A synthetic shared-chart baseline
was rejected by Office; shared-part acceptance remains package-level Core evidence.
Receipts and native contact sheet: `.local/chart-legend/`. Broad corpus fidelity and
live-model/account/hardware acceptance are not established by these synthetic checks.

## Reviewed native chart colors - 2026-10-04

23 new Core cases and 104 focused chart/legend/planner tests cover series/point RGB,
no-op/stale/invalid drafts, styles/effects/dashes, shared parts and staged provider diffs.
Fresh full sweep: 1006 Core (249/311/248/198), 157 desktop; formatting/lint/types pass.
The Electron/local Core sweep passed all 96 checks without renderer exceptions.
Three added checks cover series/point target selection, RGB draft invalidation, fresh
native review/save/reopen/undo, reviewed point-preview discard and Copilot composed
series/point edits with previous RGB review, one-revision save/re-index and exact undo.
All three new review screenshots were inspected. Receipts: `.local/chart-colors/gui.log`,
`gui-result.json`, `workspace-chart-color-{series,point}-review.png` and
`workspace-copilot-chart-colors-review.png`. The first sweep reached a correct rendered
preview but the acknowledgment text had been changed incorrectly during component
extraction; the corrected label and final sweep are verified. The earlier failure is
retained in `gui-fixture-label.log`.
PowerPoint opens 12 baseline/colored packages, verifies actual native fill/outline or
line stroke RGB, values/title/notes, unaffected other-chart pixels and six exact undos.
Native contact sheet inspected; shared-chart isolation remains package-level evidence.
Receipts under `.local/chart-colors/`; live providers/accounts are not exercised.

The final chart-color render check reuses the established color-control style so the
RGB picker displays a visible swatch. The complete 96-check behavior sweep preceded
this style-only correction; a fresh disposable Electron check imported an accepted
native chart, opened the color dialog, set purple and verified a 42px-wide, at least
30px-tall picker with 3px padding and the exact RGB. The screenshot was inspected.
Receipts: `.local/chart-colors/swatch.log`, `swatch-result.json`, `swatch-visible.png`.
Formatting/lint and the 339-entry freeze were reverified afterward.

## Reviewed native table range formatting - 2026-10-04

25 new Core cases and all 1031 collected Core tests pass in four serial batches
(249/311/248/223), with no omitted IDs. All 157 desktop tests, formatting, lint,
TypeScript and mypy (155 files) pass. Header/whole/selected-cell styles preserve
text, geometry, IDs, borders, margins, native style references, other cells and
other package parts. Null fields retain inheritance; no-op, stale/invalid input,
empty/multi-paragraph text and staged Copilot previous-style binding are covered.
The complete Electron/local Core sweep passes all 99 checks with no renderer errors,
including fresh-review enforcement, exact revision undo, preview discard and Copilot
range/previous-style review. Both review screenshots inspected. A focused Electron
check verifies visible RGB swatch and a selected-range preview/review/discard at
720x520 without horizontal dialog overflow; its two screenshots were inspected.
Native PowerPoint opens six header/whole/body-column packages and verifies all seven
style settings, native text/margins/untouched cells, identical other-slide pixels,
only slide1.xml changing and three exact undos. Full-resolution exports inspected.
Receipts are under `.local/table-format/`: core-batches/manifest.json, core-all.log,
core-focused.log, desktop.log, format-final.log, lint-final.log, types-final.log,
gui-final.log, gui-result.json, window-result.json, office/result.json and exports.
The 342-entry source freeze preserves 329 prior files, changes ten and adds three.
An earlier GUI failure was an incorrect automation label; the full corrected sweep
passes. Broad imported-table/corpus fidelity and live provider/account acceptance
remain unproven. Signing and clean Windows validation remain accepted debt.

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
