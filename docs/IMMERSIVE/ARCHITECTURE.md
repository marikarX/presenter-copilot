# Immersive Rehearsal Architecture

**Status:** Post-MVP architecture direction. This document does not change the frozen MVP runtime contract.

## Architectural objective

Immersive Rehearsal must add behavioral simulation without coupling Presenter Copilot's core reasoning, evidence, or privacy logic to a specific 3D engine or XR platform.

The architectural boundary is:

> simulation semantics are authoritative; rendering is replaceable.

## Components

```text
                       Existing Presenter Copilot Core

Deck / sources -> Project Brain -> Retrieval -------------------+
Speaker Profile -------------------------------------------------+---+
Audience Model --------------------------------------------------+   |
ASR / transcript / slide state ---------------------------------+   |
                                                                    v
                                                         Rehearsal Orchestrator
                                                                    |
                                      +-----------------------------+------------------+
                                      |                                                |
                                      v                                                v
                           Audience Simulation Engine                         Challenge / reasoning
                                      |                                                |
                                      +-----------------------------+------------------+
                                                                    v
                                                             Simulation Event Bus
                                                                    |
                                              +---------------------+--------------------+
                                              |                     |                    |
                                              v                     v                    v
                                      Desktop Renderer         3D Renderer          XR Renderer
```

## Rehearsal Orchestrator

The orchestrator owns one immersive run. It:

- binds a project/session to a scenario;
- subscribes to final transcript and slide-state updates;
- passes bounded semantic signals to the simulation engine;
- requests grounded questions/follow-ups through existing reasoning/provider boundaries;
- persists simulation events and debrief inputs;
- keeps simulation time and session time aligned;
- degrades to deterministic behavior when optional reasoning is unavailable.

The orchestrator does not draw avatars and does not own renderer-specific assets.

## Audience Simulation Engine

The engine owns canonical simulated participant state.

For each interactive participant it maintains bounded numeric/categorical state, for example:

```text
ParticipantState {
  participant_id
  attention: 0..1
  comprehension: 0..1
  skepticism: 0..1
  support: 0..1
  patience: 0..1
  question_cooldown_ms
  last_reaction_at
  unresolved_topics[]
}
```

The engine accepts typed inputs rather than raw renderer actions:

```text
SimulationInput =
  | TranscriptFinal
  | SlideChanged
  | TopicSignal
  | EvidenceMentioned
  | QuestionAnswered
  | ElapsedTime
  | PresenterSignal
  | ScenarioControl
```

The engine produces typed outputs:

```text
SimulationEvent =
  | ParticipantStateChanged
  | VisualReactionRequested
  | InterruptRequested
  | QuestionRequested
  | FollowUpRequested
  | RoomReactionRequested
  | DebriefMarker
```

## Deterministic state machine first

The first implementation should be predominantly deterministic and seedable.

Example rules:

- if an executive participant has `patience < 0.3` and one topic exceeds the configured duration without an explicit conclusion, request a time-pressure reaction;
- if a participant has an unresolved concern whose topic matches the current slide, increase question probability;
- if a claim is followed by matching evidence, reduce skepticism;
- if a technical participant receives extended non-technical narration, reduce attention gradually;
- enforce cooldowns so the room does not become unrealistically noisy.

This makes behavior testable, inexpensive, and reproducible.

## Model-assisted interpretation

Optional model reasoning may map transcript content into semantic events, such as:

- concern addressed;
- claim unsupported;
- answer evasive;
- topic transition;
- likely follow-up category.

This reasoning must run through the existing core-owned provider execution boundary and privacy rules. Imported source text and audience evidence remain untrusted data, not instructions.

The simulation engine must function without a remote provider. Remote failure may reduce semantic richness, but it must not stop the rehearsal.

## Question generation

Questions should reuse Challenge-mode grounding contracts where practical.

A `QuestionRequested` event contains semantic intent, not generated prose:

```text
QuestionRequest {
  participant_id
  trigger
  topic
  evidence_refs[]
  difficulty
  max_length
}
```

The Challenge/reasoning layer returns a grounded question with provenance. The orchestrator then emits a renderer event identifying the speaker.

This prevents a 3D renderer from calling a model directly or inventing project facts.

## Renderer contract

A renderer consumes a scene snapshot plus ordered simulation events.

Minimal contract:

```text
RendererScene {
  scenario_id
  room_kind
  participants[]
  participant_positions[]
  presentation_surface
}

RendererEvent {
  event_id
  timestamp
  participant_id?
  behavior
  intensity
  duration_ms?
  speech_text?
}
```

Renderers may interpolate animation locally but must not mutate canonical participant semantics.

If a renderer drops frames or disconnects, the orchestrator continues the rehearsal. On reconnect, the renderer receives a current snapshot and resumes from the latest state.

## Renderer implementations

### Desktop lightweight renderer

Recommended first implementation:

- Electron-compatible canvas/WebGL surface or isolated native/web renderer;
- stylized synthetic people;
- fixed set of reusable reaction animations;
- spatial seating layout;
- foreground interactive participants plus low-cost background crowd.

The exact technology should be benchmarked rather than frozen now. Candidates include a browser-based WebGL/WebGPU stack or a separately packaged native renderer.

### High-fidelity local renderer

A future local GPU renderer may use a game engine. The integration should run as a separate process with a narrow IPC contract where practical so renderer crashes or dependency changes do not destabilize the core sidecar.

### Remote/streamed renderer

Not preferred as the default. If explored later, treat it as a new cloud data boundary requiring explicit privacy design and a threat-model update.

### XR client

XR should consume the same scene/event protocol. Head pose, gaze, hand tracking, or spatial mapping must not be required by the core simulation contract.

## Process boundaries

Recommended long-term process model:

```text
Electron main/UI
      |
      +---- Python core sidecar
      |        |
      |        +---- Project / retrieval / ASR / provider execution
      |        +---- Rehearsal orchestrator / simulation engine
      |
      +---- optional renderer process
               |
               +---- local scene/assets/animation only
```

The renderer should not receive:

- provider credentials;
- full project source corpus;
- raw microphone audio;
- unrestricted filesystem access;
- hidden Audience Model history not needed for presentation.

It should receive only bounded display labels, role/visual configuration, reaction events, and spoken question text required for the scene.

## Local compute strategy

Immersive mode should exploit local compute incrementally:

- CPU: deterministic simulation, orchestration, lightweight background behavior;
- NPU/GPU where available: ASR/local models as supported by existing architecture;
- GPU: rendering;
- optional remote model: high-value semantic question/reasoning tasks only.

The rendering workload should be independently quality-scalable so local ASR/reasoning latency remains protected.

Suggested quality governor:

1. reserve latency budget for audio/ASR and core reasoning;
2. cap foreground character count;
3. lower background animation/update rate;
4. reduce materials/lighting/post-processing;
5. reduce render resolution;
6. never sacrifice transcript correctness or project-state persistence for visual fidelity.

## Data persistence

Persist enough for replay and comparison:

- scenario definition and version;
- seed;
- participant profile references;
- canonical simulation events;
- question/follow-up provenance;
- user transcript/session references;
- debrief markers;
- renderer kind and quality metadata for diagnostics.

Do not persist every animation frame or high-frequency headset telemetry by default.

## Versioning

Scenario, simulation-state, and renderer-event schemas should be versioned independently.

A stored run should remain interpretable when the visual renderer changes. Semantic event migrations are more important than preserving exact legacy animation behavior.

## Failure modes

### Renderer crash

- rehearsal continues or pauses based on user setting;
- core session remains valid;
- restart renderer from current scene snapshot.

### Remote provider unavailable

- deterministic simulation continues;
- grounded generated questions may downgrade to local/template questions;
- communicate reduced simulation richness rather than silently changing privacy mode.

### ASR unavailable

- manual/text rehearsal fallback where possible;
- no fake transcript-derived participant reactions.

### Performance contention

- renderer quality degrades before ASR/reasoning budgets are violated.

## Future interfaces

Potential later extensions:

- presentation-room authoring;
- scenario packages shared across teams;
- user-defined role templates;
- spatial audio;
- presenter gaze coaching;
- virtual whiteboard/demo surfaces;
- audience voting/polls;
- multi-presenter rehearsal.

Each must preserve the core rule that the renderer is not the authority for evidence, identity, privacy, or audience reasoning.
