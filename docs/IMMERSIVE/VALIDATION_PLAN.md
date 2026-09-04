# Immersive Rehearsal Validation Plan

**Status:** Post-MVP validation plan.

The purpose of this plan is to prevent the project from spending heavily on photorealistic rendering or XR before proving that simulated audience behavior materially improves rehearsal.

## Primary question

Does audience simulation improve preparation or delivery compared with existing Challenge and Run modes?

## Validation sequence

### V0 — Behavioral prototype

Build the cheapest credible simulation:

- desktop-only;
- 6–10 visible synthetic audience members;
- 3–5 interactive participant roles;
- simple spatial seating;
- deterministic attention/reaction state;
- grounded questions and interruptions;
- post-run audience-state debrief;
- repeatable seeded scenarios.

Graphics may be stylized. Do not require photorealistic humans, advanced lighting, lip sync, spatial audio, or headset hardware.

Pass if users report that the simulation changes rehearsal behavior and at least one quantitative measure improves relative to Run/Challenge baseline.

### V1 — Behavioral richness

Add only features that test social pressure:

- interruption timing;
- participant-specific follow-ups;
- background distraction;
- time pressure;
- visible confusion/skepticism/support;
- difficulty presets;
- scenario replay/comparison.

Pass if richer behavior improves value without producing implausibly noisy or distracting sessions.

### V2 — Spatial 3D

Add a real 3D room and spatial participant layout while keeping character fidelity moderate.

Test whether spatial presence improves:

- gaze distribution;
- presenter movement;
- perceived pressure;
- recall of audience roles;
- realism relative to V1.

Pass only if the benefit is material enough to justify GPU/rendering complexity.

### V3 — High-fidelity synthetic humans

Evaluate higher-quality avatars, facial animation, lighting, and lip sync.

Pass only if users prefer it meaningfully over V2 and the additional fidelity does not materially degrade ASR/reasoning latency on reference hardware.

### V4 — XR

Evaluate headset rehearsal only after the simulation/renderer contract is stable.

Test:

- willingness to use headset repeatedly;
- setup friction;
- comfort for 10–30 minute sessions;
- incremental improvement over desktop 3D;
- hardware availability among target users;
- enterprise deployment constraints.

Do not infer that greater presence automatically means greater product value.

## Target cohorts

Prioritize users already aligned with the product wedge:

- enterprise sales engineers;
- solution architects;
- executives/product leaders;
- founders pitching investors;
- consultants;
- technical reviewers/presenters.

Use high-stakes scenarios where audience pressure is plausible.

## Baselines

Compare immersive variants against:

1. normal Run mode;
2. Challenge mode;
3. Run + timed manual questions;
4. previous immersive fidelity level.

This is necessary to distinguish audience-simulation value from generic novelty.

## Quantitative measures

Candidate metrics:

- rehearsal completion rate;
- repeat-run rate within 7 days;
- number of weak answers improved on retry;
- answer concision under interruption;
- factual/provenance error rate;
- time-to-recover after interruption;
- omitted critical point rate;
- number of scenario concerns preemptively addressed;
- variance in gaze distribution if an explicitly approved local camera experiment exists;
- ASR latency under rendering load;
- question-generation latency;
- frame rate and dropped-frame rate;
- crash/restart rate.

## Qualitative measures

Ask users:

- Did the audience feel meaningfully different from a normal rehearsal?
- Which reactions changed what you did?
- Which reactions felt fake or distracting?
- Did you prepare differently for the real presentation afterward?
- Would you choose this mode again for a high-stakes presentation?
- Did the simulation increase useful pressure or merely add visual noise?
- Did any participant behavior feel unfairly personalized or invasive?

## Core success metrics

A behavioral prototype should meet at least two before 3D investment:

- >= 25% increase in voluntary repeat rehearsals compared with baseline;
- >= 20% improvement in rubric-scored interrupted-answer quality after repeated runs;
- >= 20% reduction in omitted scenario-critical points;
- >= 60% of target testers prefer behavioral simulation for at least one high-stakes use case;
- >= 50% report discovering a presentation weakness they did not notice in normal Run mode.

These are initial research thresholds, not launch promises. Adjust them after pilot variance is understood.

## Realism evaluation

Separate realism into two dimensions:

### Behavioral realism

- question relevance;
- interruption plausibility;
- reaction timing;
- participant consistency;
- scenario coherence.

### Visual realism

- character appearance;
- animation quality;
- lip sync;
- room quality;
- spatial audio/presence.

Do not combine these into one score. The project specifically needs to know whether visual realism adds value after behavioral realism is good enough.

## Reproducibility tests

For seedable deterministic scenarios:

- same scenario + seed + transcript/slide inputs should produce the same deterministic event sequence;
- provider-generated language may vary, but semantic question intent should remain bounded;
- renderer differences must not change canonical participant state;
- replaying a stored event stream should reproduce the semantic debrief.

## Performance acceptance

For desktop behavioral mode on reference hardware:

- maintain >= 30 FPS under normal rehearsal load;
- deterministic reactions visible within 250 ms;
- no measurable loss of finalized ASR transcript correctness due to rendering contention;
- renderer crash cannot corrupt the session;
- remote provider failure does not terminate simulation;
- local-only mode remains fully functional with reduced semantic richness where necessary.

## Safety acceptance

Before user testing:

- all default participants are synthetic/role-based;
- real-person names, if present from an Audience Model, are labeled as simulated approximations;
- no face recognition or voiceprint creation;
- no emotion-recognition claims;
- no raw camera/XR telemetry persistence by default;
- deletion removes derived immersive-run state;
- remote context obeys existing privacy-mode enforcement;
- renderer has no provider credential access.

## Kill criteria

Pause or narrow the feature if:

- users consistently describe it as distracting rather than useful;
- behavioral simulation does not outperform normal Challenge/Run workflows;
- meaningful value requires unauthorized real-person cloning;
- rendering degrades the core low-latency rehearsal experience materially;
- headset setup friction overwhelms repeat usage;
- users treat simulated reactions as predictions about real people despite labeling and UX safeguards.

## Recommended first experiment

Implement one `Executive Review` scenario with:

- 6 synthetic attendees;
- CEO/GM, CFO, VP Engineering, Security, Product, and Operations roles;
- 3 interactive participants selected per run;
- simple seated avatar states;
- normal/skeptical/executive difficulty;
- deterministic patience/attention rules;
- Challenge-grounded questions;
- debrief showing trigger -> simulated reaction -> unresolved concern.

Run the same deck in normal Run mode and immersive behavioral mode. Compare repeated-use intent, weak-answer remediation, omitted critical points, and perceived usefulness.
