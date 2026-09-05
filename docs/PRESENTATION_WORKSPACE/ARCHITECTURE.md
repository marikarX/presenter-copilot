# Presentation Workspace Architecture

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

## Stable identity

Slides and editable objects require stable internal IDs independent of their current order or OOXML relationship IDs.

Suggested identities:

- `presentation_id`;
- `revision_id`;
- `slide_id`;
- `object_id`;
- `asset_id`;
- `semantic_node_id`;
- `source_binding_id`.

Imported OOXML identifiers and relationship paths remain metadata, not domain identity.

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
      "range": {"start": 0, "end": 42},
      "text": "..."
    }
  ],
  "origin": "ai_proposal",
  "reason": "rehearsal_finding",
  "evidence_refs": ["..."]
}
```

The concrete schema should be versioned and implementation-language neutral.

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

Renderer choice remains an implementation question. The architecture requires:

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
