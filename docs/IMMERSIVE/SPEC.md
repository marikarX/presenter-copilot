# Immersive Rehearsal Specification

**Status:** Post-MVP roadmap specification.

## Objective

Immersive Rehearsal should make a rehearsal feel socially and cognitively closer to the target presentation by simulating audience behavior, room context, interruptions, and questions while preserving the existing local-first and evidence-grounded product model.

The feature is successful when it changes what the presenter practices, notices, or improves. Visual realism is secondary to behavioral realism.

## User outcomes

A user should be able to:

- choose or generate a presentation scenario;
- rehearse against a synthetic audience with role, expertise, authority, attitude, and likely concerns;
- see audience state change as the presentation progresses;
- receive interruptions and questions at plausible moments;
- practice maintaining pace and eye contact under distraction;
- review which audience members became confused, skeptical, disengaged, or convinced and why;
- compare repeated runs against the same scenario;
- increase scenario difficulty without changing the source material;
- use the same scenario in desktop 2D/3D and future XR renderers.

## Scenario model

A scenario contains:

- room type;
- audience size;
- key interactive participants;
- background audience population;
- presentation objective;
- expected duration;
- interruption policy;
- question density;
- difficulty;
- audience profiles;
- scenario seed for reproducibility;
- rendering hints that are not semantically authoritative.

Examples:

- executive board review;
- architecture review;
- enterprise sales pitch;
- investor pitch;
- conference talk;
- hostile Q&A;
- friendly internal rehearsal;
- procurement/bid defense.

## Audience member model

Interactive audience members should be represented by bounded, inspectable state rather than opaque character prompts.

Suggested logical fields:

```text
AudienceMember {
  id
  display_label
  role
  expertise_level
  authority_level
  baseline_attitude
  patience
  attention
  comprehension
  skepticism
  support
  interruption_propensity
  question_topics[]
  evidence_refs[]
  synthetic_identity
}
```

`display_label` may be a role such as `CFO`, `Principal Architect`, or `Security Reviewer`. A real person's name may be used only when the existing Audience Model legitimately contains it and the UI makes clear that the simulated behavior is an approximation, not a prediction of that person's internal state.

## Behavioral events

The simulation engine may emit bounded events such as:

- `attention_up`;
- `attention_down`;
- `confusion_visible`;
- `skepticism_up`;
- `support_up`;
- `side_glance`;
- `note_taking`;
- `laptop_attention`;
- `interrupt_request`;
- `question_request`;
- `follow_up_request`;
- `time_pressure`;
- `room_reaction`.

These events are simulation outputs. They must not be presented as psychological measurements of real humans.

## Inputs to audience state

The simulation may use:

- current slide;
- recent transcript;
- elapsed time;
- speaking pace;
- pauses;
- whether expected evidence was mentioned;
- whether an audience concern was addressed;
- prior simulated questions in the current run;
- scenario difficulty;
- user-selected behavior settings;
- authorized Audience Model evidence.

Future gaze/posture inputs may be used only after explicit privacy review. They must remain presenter-coaching signals and not be repurposed for identity recognition or emotion inference.

## State updates

The engine should combine deterministic rules with optional model reasoning.

Deterministic rules are preferred for:

- timing thresholds;
- question cooldowns;
- interruption frequency;
- scenario reproducibility;
- obvious slide/topic triggers;
- bounds and rate limits.

Model reasoning may be used for:

- deciding whether a claim addresses a participant concern;
- generating a grounded question;
- selecting a plausible follow-up;
- summarizing why a participant state changed.

All model-generated questions must remain grounded in the same project/audience evidence rules as Challenge mode.

## Difficulty

Recommended presets:

- `friendly` — low interruption, forgiving attention, supportive reactions;
- `normal` — plausible attention changes and ordinary questions;
- `skeptical` — higher evidence demands and follow-up probability;
- `executive` — low patience, concise questions, stronger time pressure;
- `adversarial` — aggressive challenge frequency without abusive content.

Difficulty controls interaction pressure, not factual dishonesty. The engine must not invent false evidence or pretend a source contradicts the presenter when it does not.

## Rendering requirements

### Desktop behavioral mode

P0 for this roadmap feature.

- normal desktop window;
- synthetic audience arranged spatially;
- visible attention/reaction changes;
- clear indication of the active questioner;
- no headset required;
- acceptable on commodity hardware;
- intentionally tolerant of stylized/non-photorealistic characters.

### High-fidelity 3D mode

Later.

- renderer may use local GPU acceleration;
- key interactive participants may have higher detail than background participants;
- background crowd behavior can be batched/procedural;
- visual fidelity must degrade gracefully without changing semantic audience state.

### XR mode

Later and optional.

- renderer consumes the same simulation event contract;
- presentation surfaces and audience positions are spatialized;
- no XR-only audience reasoning logic;
- headset telemetry requires separate privacy review.

## Debrief

The post-run debrief should distinguish observed presenter behavior from simulated audience response.

Possible output:

- audience concerns addressed / not addressed;
- participant-specific unresolved questions;
- time periods where simulated attention fell;
- interruptions handled well/poorly;
- repeated weak answer areas;
- strongest evidence-backed moments;
- likely questions that were not preempted;
- comparison with previous runs of the same scenario.

Avoid deceptive aggregate claims such as `74% of your real audience would be convinced`. Prefer `In this simulation, 6 of 8 modeled participants ended in a supportive state`.

## Reproducibility

A user should be able to rerun the same scenario with the same seed and participant definitions. Model-backed behavior may still vary, but the system should persist enough scenario inputs and generated events to replay and compare the run.

## Performance targets

Targets for the first behavioral prototype:

- audience visual reaction latency: under 250 ms for deterministic events;
- question trigger decision: under 500 ms when deterministic;
- generated question latency: use existing Challenge/provider budgets;
- stable 30 FPS minimum on reference desktop hardware for the audience scene;
- simulation behavior continues if remote reasoning is unavailable;
- renderer failure must not corrupt rehearsal/session state.

## Non-goals

The first immersive release does not include:

- photorealistic clones of coworkers;
- face replacement or deepfake generation;
- persistent face recognition;
- voice cloning of audience members;
- hidden emotion detection;
- psychological/personality diagnosis;
- autonomous recording of real meetings;
- claims that the simulation predicts exactly how a named person will react;
- cloud-only rendering as a hard dependency;
- mandatory XR hardware.

## Product gates

Do not fund high-fidelity rendering until a lightweight prototype demonstrates at least one of:

- increased rehearsal frequency;
- improved answer quality under interruption;
- better recall of weak/unsupported sections;
- stronger user-reported preparedness;
- meaningful preference over normal Challenge/Run mode for target scenarios.

Do not fund XR until the renderer-independent simulation contract is stable and users demonstrate a clear preference for spatial rehearsal over desktop 3D.
