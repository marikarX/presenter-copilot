# Presentation Workspace UX

## Workspace layout

Default desktop arrangement:

```text
+--------------------------------------------------------------------------------+
| Project / presentation                                    Ready v12   Rehearse |
+------------------+--------------------------------------+----------------------+
| Slide navigator  | Presentation canvas                  | Copilot              |
|                  |                                      |                      |
| 01 Title         | selected slide                       | text / voice          |
| 02 Problem       |                                      | context-aware chat   |
| 03 Decision      | direct editing handles               | proposed changes      |
| 04 Economics     |                                      | evidence / rationale  |
|                  |                                      |                      |
+------------------+--------------------------------------+----------------------+
| Notes | Sources | Claims | Rehearsal findings | Version history             |
+--------------------------------------------------------------------------------+
```

The exact layout may change, but three concepts should remain visible and tightly connected:

1. presentation structure;
2. current editable slide;
3. conversational/AI assistance.

## Direct editing

Users should not need AI for ordinary edits.

Minimum interactions:

- click/select object;
- double-click or Enter to edit text;
- drag to move;
- handles to resize;
- common keyboard operations: delete, duplicate, copy/paste, undo/redo;
- slide drag/reorder;
- context toolbar/inspector for common formatting;
- image replace/crop;
- notes editor.

The editor should avoid exposing raw OOXML concepts.

## AI side chat

AI conversation is presentation-aware by default.

Context precedence:

1. explicit user selection;
2. current slide;
3. selected slide range;
4. presentation objective/narrative;
5. Project Brain evidence;
6. Audience Model;
7. Speaker Profile;
8. recent rehearsal findings.

The UI should make scope visible, e.g. `Editing: Slide 6` or `Editing: Slides 4-8`, so broad actions are not surprising.

## Voice interaction

Voice is another input modality to the same command/planning system, not a separate feature silo.

Examples:

- "Change this title to emphasize the business impact."
- "Add the point I just made about failover testing."
- "Put these implementation details in an appendix."
- "Create a visual for this architecture."

Voice transcription should appear before or alongside execution so the user can detect recognition errors.

For low-risk, local edits, an optional fast-apply mode may be considered later. Initial behavior should remain reviewable.

## Selection-aware commands

A command should resolve a bounded target set before planning an edit.

Examples:

- selected text -> text operation;
- selected image -> replace/crop/style operation;
- selected slide -> slide-level transformation;
- selected slides -> multi-slide operation;
- no selection -> current slide by default;
- explicit "whole deck" -> presentation-wide operation.

If a command would affect materially more content than its resolved selection implies, require preview rather than silently widening scope.

## Change proposals

### Lightweight changes

For local, easily reversible actions such as changing selected text or moving one supported object, the app may apply immediately while recording a transaction in undo/history.

### Structural or broad changes

Preview before apply when an operation:

- changes multiple slides;
- removes content;
- replaces a slide layout substantially;
- introduces generated facts or claims;
- moves material to/from appendix;
- changes theme/design across the deck;
- would alter or flatten unsupported PPTX objects.

A proposal should show:

- target slides/objects;
- concise rationale;
- before/after preview or structured diff;
- evidence/rehearsal trigger when relevant;
- compatibility warning if export fidelity may change.

Actions: `Apply`, `Apply individually`, `Revise`, `Reject`.

## Rehearsal findings panel

Run and Challenge findings should be actionable objects rather than static feedback prose.

Example:

```text
Slide 8
High-confidence finding

Your spoken explanation of migration risk was clearer and 42% shorter
than the current slide text.

[Preview slide rewrite] [Save to notes] [Ignore]
```

Other finding types:

- unsupported numeric claim;
- recurring audience objection;
- excessive slide density;
- explanation consistently omitted;
- useful user analogy not represented in slide/notes;
- likely appendix candidate;
- current wording conflicts with source evidence.

No finding applies edits automatically.

## Sources and claims

A selected claim/text block should be able to expose its evidence relationships.

Useful actions:

- `Find support`;
- `Attach source`;
- `Show source`;
- `Mark as assertion/opinion`;
- `Add citation`;
- `Move evidence to notes/appendix`.

The UI must distinguish source-backed facts from user statements and AI suggestions.

## Unsupported imported content

Unsupported objects require visible status without making the deck unusable.

Possible presentation:

- object renders normally from imported preview/fidelity path;
- selection indicates `Preserved object - limited editing`;
- supported operations may include move/resize/delete;
- unsupported semantic editing is disabled;
- export retains the original object whenever possible.

The user should not have to learn what XML feature caused the limitation.

## Version history

The workspace needs presentation-level versioning beyond a simple undo stack.

Record meaningful checkpoints such as:

- import baseline;
- before/after broad AI transformation;
- user-named checkpoint;
- marked-ready revision;
- rehearsal-bound revision;
- exported revision.

The UI should allow visual comparison and restore without rewriting historical rehearsal/session bindings.

## Ready/presentation boundary

Draft editing and active presentation state must be separate.

When the user starts Run or Live Assist:

- bind the session to a concrete presentation revision;
- optionally prompt to use current draft or last ready revision;
- do not let background AI proposals silently alter that bound revision.

## Failure behavior

### AI unavailable

Direct editing remains fully usable.

### ASR unavailable

Text chat/direct editing remain usable; voice editing is disabled with a typed actionable status.

### PPTX export compatibility warning

Show which objects/features may not round-trip and offer:

- export with preserved unsupported content where possible;
- PDF export;
- duplicate-and-normalize only after explicit user choice.

### Corrupt/unsupported PPTX

Keep the original file immutable, report the failing slide/object where possible, and avoid destructive repair without a user-created copy.
