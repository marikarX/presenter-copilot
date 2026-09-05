# Presentation Workspace Roadmap

## Position in the broader roadmap

Presentation Workspace is a **post-MVP expansion**. It should not delay validation of the current rehearsal/live-assist wedge.

Entry gate:

- document ingestion/retrieval is stable;
- Teach/Challenge/Run/Live Assist provide clear user value;
- users demonstrate repeated need to modify decks as a result of preparation/rehearsal;
- the team is willing to own PPTX round-trip compatibility as a product capability.

## Phase PW0 — Validate the editing wedge

Goal: prove that keeping users inside Presenter Copilot for deck changes materially improves the preparation loop.

Build:

- high-fidelity slide viewer for imported PPTX;
- side-by-side Copilot conversation;
- read-only semantic overlays: claims, sources, notes, rehearsal findings;
- manual "apply this finding" prototypes that produce a rendered mock change, not yet full PPTX round-trip;
- instrumentation around edit intent.

Research:

- observe 10-20 real deck-preparation sessions;
- classify edit operations users leave the app to perform;
- measure frequency of PowerPoint context switching;
- collect licensing-safe PPTX compatibility corpus.

Exit criteria:

- a small set of edit operations covers the majority of preparation-related context switches;
- rehearsal findings frequently lead to requested deck changes;
- users prefer an integrated workflow strongly enough to justify fidelity engineering.

## Phase PW1 — Fidelity foundation

Goal: import and render PPTX with stable internal object identity and no-op round-trip safety.

Build:

- immutable original snapshot;
- fidelity document model;
- stable slide/object IDs;
- compatibility classification;
- opaque preservation nodes;
- render pipeline;
- PPTX package writer/export validator;
- version/revision skeleton;
- golden corpus and automated no-op round-trip tests.

No AI mutation yet.

Exit criteria:

- supported corpus opens and renders within defined visual thresholds;
- no-op export preserves unsupported content and produces valid PowerPoint files;
- untouched-slide invariants pass;
- compatibility warnings are accurate enough for dogfooding.

## Phase PW2 — Core direct editing

Goal: make ordinary deck preparation possible without PowerPoint for supported content.

Build:

- text editing;
- notes editing;
- object selection/move/resize/delete/duplicate;
- slide add/delete/duplicate/reorder;
- common text/shape formatting;
- image replacement/crop;
- undo/redo;
- revision checkpoints;
- save/export PPTX/PDF.

Exit criteria:

- real users can complete at least 70% of observed preparation edits without leaving Presenter Copilot;
- export fidelity remains within release thresholds;
- unsupported objects are preserved rather than silently flattened.

## Phase PW3 — Semantic presentation model

Goal: connect the editable document to Project Brain meaning.

Build:

- PresentationNarrative;
- SlideSemantics;
- claim extraction/binding;
- evidence coverage status;
- slide purpose/narrative-role analysis;
- explicit mapping between fidelity object ranges and semantic nodes;
- incremental semantic refresh after edits;
- current revision awareness in retrieval/context builders.

Exit criteria:

- semantic overlays survive normal edits without drift;
- claims/evidence remain traceable to current slide/object spans;
- rehearsal and Challenge always bind to a concrete presentation revision.

## Phase PW4 — AI side-chat editing

Goal: convert natural-language requests into safe typed edit transactions.

Build:

- selection-aware target resolver;
- typed EditPlan schema;
- planner task through existing provider execution boundary;
- deterministic core validation;
- preview/review UI;
- apply/reject/revise;
- stale-plan detection/rebase rules;
- audit/history metadata;
- preserve-my-voice rewrite policy.

Initial command set:

- rewrite/shorten/clarify selected text;
- restructure current slide;
- split/merge simple content;
- notes generation from user-authored explanation;
- source/citation attachment;
- move detail to appendix;
- simple layout transformations.

Exit criteria:

- AI never mutates raw OOXML directly;
- broad/destructive changes always pass review gates;
- stale plans fail safely;
- AI edits are reversible and attributable;
- user acceptance rate demonstrates practical value beyond direct editing alone.

## Phase PW5 — Voice editing

Goal: make spoken thinking a first-class presentation-authoring input.

Build:

- local ASR reuse for edit commands;
- visible transcript/command confirmation;
- selection/current-slide grounding;
- voice-to-EditPlan path;
- ambiguity/low-confidence handling;
- push-to-edit shortcut;
- optional conversational drafting sessions that materialize into slide proposals.

Exit criteria:

- users can perform common edit/refinement tasks reliably by voice;
- ASR errors do not create destructive silent mutations;
- latency supports natural iterative work.

## Phase PW6 — Rehearsal-to-edit closed loop

Goal: make preparation/rehearsal outcomes improve the actual deck.

Build:

- typed rehearsal findings;
- strong-spoken-explanation capture;
- weak/unsupported claim findings;
- repeated-objection findings;
- slide-density/omission findings;
- proposal generation from findings;
- links from applied edits back to Run/Challenge provenance;
- compare improvement across presentation revisions.

Exit criteria:

- users regularly accept rehearsal-derived changes;
- revised decks produce measurably better subsequent rehearsals;
- the loop does not silently promote AI interpretation as user evidence.

This phase is the strategic payoff for the workspace.

## Phase PW7 — Creation from conversation

Goal: allow a new presentation to emerge from voice/text conversation using the same editable model.

Build:

- objective/audience/decision capture;
- narrative planner;
- slide-outline proposal;
- constrained layout/template system;
- materialization into fidelity model;
- evidence-aware content generation;
- user-voice-aware notes/content;
- asset/diagram insertion;
- immediate transition into normal editing/rehearsal.

Boundary:

Do not optimize for generic one-shot "generate a deck" benchmarks. Optimize for iterative authoring grounded in Project Brain and rehearsal.

## Phase PW8 — Richer native objects and design assistance

Only after core loop proves value:

- better tables/charts;
- structured diagrams;
- reusable component/layout library;
- theme operations;
- higher-end design suggestions;
- richer image generation/editing;
- additional native PPTX feature support.

Each feature should be justified by observed context-switch frequency or strategic workflow value.

## Phase PW9 — Integration/export expansion

Candidates:

- Google Slides export/integration;
- Keynote interoperability where practical;
- optional PowerPoint add-in/hand-off surfaces;
- enterprise template libraries;
- team review/approval workflows.

Do not make external-office integrations the source of truth for Presenter Copilot presentation state.

## Explicit deferrals

Unless user demand changes materially, defer:

- VBA/macro support;
- arbitrary Office add-ins;
- exhaustive animation authoring;
- full SmartArt editing;
- full master/theme designer;
- real-time multi-user coauthoring;
- every PowerPoint chart subtype;
- cloud document suite replacement;
- automatic live-session slide rewriting.

## Sequencing rule

PPTX fidelity and direct editing come **before** broad AI authoring. A natural-language editor on top of an unreliable document model would create demos but not a trustworthy product.

Likewise, creation-from-conversation comes after import/edit because real high-stakes users already have decks, templates, and organizational material that the product must respect.
