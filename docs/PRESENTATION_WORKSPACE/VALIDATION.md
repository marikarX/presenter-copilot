# Presentation Workspace Validation Plan

## Objective

Validate both product usefulness and document fidelity before treating Presentation Workspace as a core product surface.

The feature fails if either side is weak:

- useful AI/editing with unreliable PPTX export is unacceptable;
- perfect round-trip fidelity that does not reduce preparation friction is not strategically justified.

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
7. restore a prior revision;
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
