# Presentation Workspace

Status: **post-MVP roadmap direction**.

This package defines how Presenter Copilot can evolve from a presentation-intelligence sidecar into the primary preparation workspace for an imported or newly created presentation while preserving the existing local-first rehearsal/live-assist architecture.

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

The workspace begins only after the initial wedge and closed-loop learning behavior are validated strongly enough to justify a broader preparation surface.

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
- maintain undo/redo and presentation version history;
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
