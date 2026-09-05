# Presentation Workspace Product Specification

## Purpose

Presentation Workspace extends Presenter Copilot so imported and newly created decks can be edited inside the same environment used for Teach, Challenge, Run, and Live Assist.

The objective is not to replace every capability of PowerPoint. The objective is to eliminate routine context switching during presentation preparation while preserving reliable PPTX interoperability.

## Product promise

A user should be able to:

1. import a PPTX;
2. inspect and edit it directly;
3. discuss the presentation with the AI by text or voice;
4. apply AI-generated edits to the actual presentation;
5. rehearse the current version;
6. convert rehearsal findings into proposed slide changes;
7. review, accept, reject, or refine those changes;
8. repeat until ready;
9. export or present without losing the accumulated Project Brain.

## Primary user journeys

### Imported-deck workflow

```text
Open PPTX
  -> render + parse
  -> build editable presentation model
  -> connect slide semantics to Project Brain
  -> edit / ask / rehearse
  -> accept changes
  -> export PPTX/PDF
```

### Conversation-to-deck workflow

```text
Voice/text conversation
  -> capture objective, audience, argument, evidence
  -> propose narrative
  -> propose slide structure
  -> materialize editable slides
  -> user edits
  -> rehearse
  -> improve
```

### Rehearsal-to-edit workflow

```text
Run or Challenge
  -> identify weak claim / long explanation / missing evidence
  -> create edit proposal
  -> preview diff
  -> user applies or modifies
  -> new presentation version
```

## Core jobs to be done

### Understand

- See the current presentation as slides, objects, notes, and narrative.
- Understand what each slide is trying to achieve.
- Know which claims have evidence and which do not.
- Know how the slide relates to likely audience concerns.

### Edit

- Make direct visual/textual changes without leaving Presenter Copilot.
- Perform common layout and content operations quickly.
- Preserve imported objects the editor does not fully understand.

### Collaborate with AI

- Ask for changes in natural language.
- Use voice when thinking aloud is faster than typing.
- Reference the selected slide/object, current narrative, sources, audience, and prior rehearsal automatically.
- Review proposed edits before destructive or broad changes.

### Improve through rehearsal

- Capture stronger spoken explanations.
- Identify evidence gaps and likely objections.
- Convert those findings into slide/notes/appendix proposals.
- Keep the user's preferred language rather than replacing it with generic AI prose.

## Workspace modes

The workspace is not a new independent knowledge silo. Existing modes use the same current presentation version.

### Edit

Direct manipulation plus AI side chat.

### Teach

Conversation may update Project Brain and optionally produce slide/notes proposals.

### Challenge

Questions target the current deck version. Findings can become proposed edits.

### Run

Rehearsal tracks the current deck version. Strong explanations and weak spots can become proposals after the run.

### Live Assist

Uses the presentation version explicitly marked ready/presentable. Draft edits must not silently change a live session.

## Presentation lifecycle states

At minimum:

- `draft` — actively being edited;
- `ready` — user-marked version for rehearsal/presentation;
- `archived` — retained prior version/snapshot.

A live or rehearsal session should bind to an immutable presentation revision ID so later editing does not rewrite historical session meaning.

## High-frequency editing scope

Initial workspace editing should prioritize:

- text editing;
- speaker notes;
- image replacement/crop/fit;
- object move/resize/delete/duplicate;
- slide add/delete/duplicate/reorder;
- common font/alignment/color/fill/stroke changes;
- grouping/ungrouping for supported objects;
- simple shape creation;
- simple tables;
- constrained charts;
- simple diagrams;
- theme-aware layout selection;
- source/evidence badges or footnotes;
- appendix generation.

## AI-native capabilities

High-value commands include:

- "Make this slide understandable to a CFO."
- "Split this into problem, decision, and outcome."
- "Use what I just said in rehearsal instead of this paragraph."
- "Find support for the $1.8M number and cite it."
- "Move implementation detail to an appendix."
- "Create a diagram from the architecture source."
- "Shorten the title without changing my wording style."
- "Show me the version for an executive audience."

The system should prefer transforming existing slide content and user-authored language over replacing the entire slide by default.

## User-control principles

- AI edits are attributable and reversible.
- Broad multi-slide edits should be previewable before apply.
- Unsupported imported elements are never silently discarded.
- Rehearsal output does not mutate the presentation automatically.
- Generated claims do not become sourced facts merely because they appear on a slide.
- The user can inspect why an edit was proposed and which evidence/rehearsal event triggered it.

## Non-goals

The first workspace versions are not intended to provide:

- full PowerPoint parity;
- arbitrary macro/add-in execution;
- advanced animation authoring;
- every Office chart and SmartArt edit operation;
- desktop-publishing precision beyond presentation needs;
- enterprise coauthoring parity with Microsoft 365 or Google Workspace;
- automatic slide changes during a live meeting;
- automatic publication/export without user review when unsupported content may change.

## Product success criteria

A workspace release is compelling when users can import real decks and complete most preparation work without opening PowerPoint.

Target qualitative outcome:

> "I only open PowerPoint when someone else requires it, not because Presenter Copilot cannot make the change I need."

Initial quantitative targets are defined in [`VALIDATION.md`](VALIDATION.md).
