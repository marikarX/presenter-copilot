# Presentation Asset Model

## Purpose

Images, diagrams, and other media used in the presentation should be first-class project assets rather than anonymous blobs embedded only inside one slide.

## Asset entity

Suggested fields:

- `asset_id`;
- project-local storage reference;
- media type and dimensions;
- original/imported/generated origin;
- source URI or document provenance when applicable;
- generation prompt/model metadata when applicable;
- rights/license/attribution metadata when known;
- content hash;
- variants/derivatives;
- slide/object usages;
- semantic tags/description;
- created/updated timestamps.

## Imported media

When a PPTX is imported, media should be deduplicated by content hash where safe while preserving the original package relationships required for round-trip export.

Replacing an image should create a new asset/version rather than destroying the imported original.

## Generated media

Generated images/diagrams should record enough provenance to answer:

- was this generated or imported;
- what request produced it;
- which model/provider produced it, when known;
- whether it is safe to reuse/export under the active provider terms;
- which earlier asset it derived from.

Prompt metadata is project-private and should follow the same retention/privacy philosophy as other provider context.

## Structured diagrams

Prefer structured editable diagram primitives for architecture/process visuals when practical:

- nodes;
- connectors;
- labels;
- groups;
- layout constraints.

Use raster/vector image assets when structured editing is not practical. The user should know whether a generated visual is editable as a diagram or only as an image.

## Variants

Assets may have variants such as:

- original;
- cropped;
- background-removed;
- compressed;
- alternate aspect ratio;
- generated variation;
- presentation-render derivative.

Variants should reference the parent asset and never overwrite the canonical original silently.

## External content

Do not persist fragile hotlinks as the only durable representation. When the user explicitly imports permitted remote media, snapshot the selected asset locally and retain source metadata.

The application should not automatically fetch arbitrary external relationships found in imported PPTX files.

## Deletion

Deleting an asset from one slide removes that usage, not necessarily the project asset. Explicit project-asset deletion should warn if the asset is referenced by other presentation revisions or slides.

Historical revisions may retain immutable references/snapshots as required for version restoration.

## Export

PPTX export should package the exact asset variant referenced by the exported revision. PDF/export renders should be deterministic for the same revision and asset generation.


## Implemented raster library (2026-10-03)

Schema v14 stores immutable project PNG/JPEG uploads as SQLite BLOBs with opaque
project/content IDs, original file names, SHA-256, MIME type, byte size and creation
time. Identical content keeps the first item's identity and name. Validation uses
native insertion constraints: 4 MiB, one frame, 8192 dimensions and 20 MP. Each
project allows 200 images/64 MiB; bounded thumbnail pages and full reads verify
content integrity. No source URI, provenance/license fields, usage index, tags,
variants or generated-image integration is implemented yet.

Objects selection reuses the ordinary native insertion form. Copilot explicitly
attaches library metadata and binds actual image bytes inside Core staging.
Library removal requires confirmation and the expected hash. Existing revisions
and staged proposals own embedded copies and remain usable after removal. This
is logical library deletion; it is not a secure-erasure guarantee. Pre-deck Core
methods exist; standalone pre-deck GUI management remains open.
