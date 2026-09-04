# Immersive Rehearsal

**Status:** Post-MVP roadmap package. Not part of the frozen MVP contract in `docs/MVP/`.

Immersive Rehearsal extends Presenter Copilot from question-and-answer rehearsal into an audience simulation environment. The goal is not photorealism by itself. The goal is to reproduce useful presentation pressure: attention shifts, visible confusion, interruptions, objections, follow-up questions, authority dynamics, and the need to maintain eye contact while continuing the presentation.

The renderer is deliberately separate from the rehearsal intelligence so the same simulation can drive a normal desktop scene, a higher-fidelity 3D room, or an XR client.

## Product hypothesis

A realistic audience should make rehearsal more valuable when it changes presenter behavior and preparation, not merely when it looks realistic.

The primary hypothesis is:

> behavioral fidelity produces measurable rehearsal value before graphical fidelity does.

The program therefore validates audience behavior in a lightweight desktop environment before investing in photorealistic humans or headset-specific rendering.

## Package

Read these documents in order:

1. [Specification](SPEC.md) — product scope, scenarios, requirements, non-goals, and rollout gates.
2. [Architecture](ARCHITECTURE.md) — renderer-independent simulation architecture, state model, event contracts, and compute boundaries.
3. [Privacy & safety](PRIVACY_SAFETY.md) — synthetic-person defaults, real-person likeness restrictions, camera/gaze boundaries, and data handling.
4. [Validation plan](VALIDATION_PLAN.md) — experiments and evidence required before escalating from behavioral simulation to photorealistic/XR rendering.

## Relationship to existing modes

Immersive Rehearsal does not replace `Teach`, `Challenge`, `Run`, or `Live Assist`.

- `Teach` continues to capture project knowledge and presenter wording.
- `Challenge` provides grounded questions and answer coaching.
- `Run` remains the uninterrupted rehearsal session model.
- `Immersive Rehearsal` is a presentation surface and simulation layer around a Run/Challenge-style session.
- `Live Assist` remains a private real-presentation mode and does not render a simulated audience.

## Architectural rule

The Audience Simulation Engine owns scenario behavior. Renderers own presentation of that behavior.

```text
Presentation / speech / slide state
              |
              v
      Rehearsal Orchestrator
              |
              v
   Audience Simulation Engine
       |               |
       v               v
Audience events    Question/objection tasks
       |               |
       +-------+-------+
               v
        Render Adapter
        /      |      \
   Desktop    3D      XR
```

A renderer must never become the source of truth for audience reasoning, project evidence, privacy policy, or session history.

## Default audience identity model

The default product uses synthetic audience members or abstract role-based avatars. Real-person likeness recreation is not required for the feature and is not a default capability.

When a scenario is informed by prior meetings, the system may use authorized project-local evidence such as role, attributed questions, recurring observable concerns, and user-supplied decision criteria. It must not claim to infer a real participant's hidden emotion, diagnosis, personality, or sensitive trait.

## Delivery sequence

1. Behavioral desktop simulation with intentionally simple visuals.
2. Richer 3D room and spatial audience layout.
3. High-fidelity synthetic audience rendering where hardware supports it.
4. XR client after the renderer-independent simulation contract is stable.
5. Organization/team scenario libraries only after individual rehearsal value is demonstrated.

Photorealism and XR are escalation steps, not prerequisites for validating the feature.
