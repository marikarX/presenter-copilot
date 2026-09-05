# PPTX Fidelity and Compatibility Strategy

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

## Release philosophy

Do not claim broad PPTX editing based on a handful of generated fixtures. Real enterprise decks are adversarial compatibility inputs. The feature graduates only through corpus-based round-trip evidence and dogfooding on real user decks.
