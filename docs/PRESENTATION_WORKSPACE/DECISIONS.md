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
