# AI and Voice Editing Contract

## Goal

Natural-language and voice requests should modify the same presentation model as direct manipulation while remaining bounded, reviewable, reversible, and source-aware.

The AI is a planner over typed presentation operations, not an unrestricted document mutator.

## Flow

```text
User text / voice
      |
      v
Intent + target resolver
      |
      v
Context builder
      |
      v
AI planner
      |
      v
Typed EditPlan
      |
      v
Core validation / compatibility checks
      |
      +--> preview/review when required
      |
      v
Edit Transaction Engine
      |
      v
New presentation revision
```

## Voice path

Voice uses the same planning path after local ASR.

Requirements:

- transcription remains visible/reviewable;
- raw audio follows existing local-first rules;
- speech recognition does not itself grant mutation authority;
- low-confidence or ambiguous commands should become proposals rather than destructive actions;
- voice may reference current selection and recent context, but target resolution remains explicit in the resulting plan.

## Planning contract

The planner receives bounded, trust-labeled context:

- current presentation revision ID;
- explicit selection/slide range;
- relevant slide/object summaries;
- semantic narrative context;
- permitted Project Brain evidence;
- Audience Model context when relevant;
- Speaker Profile/style policy;
- relevant rehearsal findings;
- compatibility constraints for targeted objects.

Imported slide text and source material are untrusted data, not application instructions.

## Edit plan principles

A plan must contain typed operations rather than free-form XML/code.

Representative operations:

- `replace_text`;
- `insert_text`;
- `set_text_style`;
- `move_object`;
- `resize_object`;
- `delete_object`;
- `duplicate_object`;
- `insert_image`;
- `replace_image`;
- `set_crop`;
- `create_shape`;
- `create_text_box`;
- `reorder_slide`;
- `duplicate_slide`;
- `insert_slide`;
- `delete_slide`;
- `set_notes`;
- `attach_evidence`;
- `create_appendix_slide`;
- `apply_layout`;
- constrained chart/table operations.

Unknown operation types fail closed.

## Preconditions

Every operation should include sufficient preconditions to detect stale or mis-targeted execution.

Examples:

- base revision;
- expected object ID/type;
- expected current text hash/range;
- expected slide membership;
- compatibility tier;
- required asset existence.

Broad edits should carry an explicit resolved target list.

## Review policy

### May apply immediately

Initially limited to reversible, local, narrowly targeted changes such as:

- replace selected text;
- change selected object style;
- move/resize selected supported object;
- update notes on current slide.

Even these create undo/history transactions.

### Must preview

- multi-slide transformations;
- slide deletion;
- large text replacement;
- structural narrative changes;
- generated images/diagrams replacing existing content;
- adding unsupported or weakly supported claims;
- operations requiring PPTX normalization;
- theme-wide changes;
- appendix/main-deck movement across several slides;
- stale/rebased AI plans.

## Claim and evidence behavior

The planner must not treat generated prose as evidence.

When a user asks "find support for this" the operation sequence should be conceptually:

1. identify claim;
2. retrieve candidate evidence;
3. show support/conflict status;
4. propose citation/wording change;
5. attach canonical evidence references only after validation.

If evidence conflicts with the slide, the system should propose correction or qualification rather than silently citing the conflicting source.

## Preserve-my-voice behavior

For content rewriting, source priority should generally be:

1. user-authored wording from current deck;
2. strong user explanations/practiced answers;
3. explicit style guidance;
4. source-backed facts;
5. generated connective language.

The planner should not unnecessarily replace presenter language with generic consultant-style prose.

## Rehearsal-derived edits

A rehearsal finding is input to a proposal, not authority to mutate.

Examples:

- strong spoken explanation -> `replace_text` or `set_notes` proposal;
- repeated objection -> appendix or evidence proposal;
- unsupported exact number -> citation/correction proposal;
- slide consistently skipped -> deletion/merge proposal;
- answer too long -> slide simplification proposal.

Every such proposal retains a reference to the originating run/question/answer/finding where practical.

## Whole-deck transformations

Commands such as "make this executive" should not be implemented as one unconstrained prompt producing a replacement deck.

Preferred sequence:

1. analyze narrative and audience;
2. produce a transformation plan;
3. identify slides to keep/merge/move/remove;
4. show structural preview;
5. apply per-slide typed operations;
6. preserve a revision checkpoint;
7. refresh semantics and evidence bindings;
8. report compatibility impacts.

## Generated images and diagrams

Generated media enters through the asset subsystem and is inserted by reference.

The edit plan should never embed opaque remote URLs as durable presentation state.

Generated diagrams should prefer structured editable representations when practical; otherwise store them as image assets with prompt/provenance metadata.

## Safety and security constraints

AI planning cannot:

- execute macros/add-ins;
- emit arbitrary filesystem paths for mutation;
- fetch external PPTX relationships without explicit product support;
- directly modify OOXML package bytes;
- bypass privacy/provider context rules;
- auto-accept normalization/fidelity loss;
- mark generated facts as source-backed without canonical evidence.

## Observability

For debugging and user trust, retain metadata such as:

- origin: direct / AI text / AI voice / rehearsal proposal;
- task type;
- model/provider identity where remote reasoning was used;
- resolved target IDs;
- plan fingerprint;
- applied/rejected/stale status;
- compatibility warnings;
- evidence references;
- resulting revision ID.

Do not persist confidential full prompts by default if existing provider policy avoids them.

## Deterministic validation

Provider output is never trusted solely because it matches a JSON schema.

Core validation must verify:

- referenced slides/objects exist in the base revision;
- operations are permitted for object compatibility tiers;
- geometry/ranges are bounded;
- asset references exist;
- evidence IDs are canonical and eligible;
- operation count/size stays within task limits;
- broad destructive plans trigger review;
- the plan has not become stale.
