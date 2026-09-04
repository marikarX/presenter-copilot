# Immersive Rehearsal Decision Record

**Status:** Accepted roadmap architecture direction. These decisions apply only to post-MVP immersive work.

## I-001 — Behavioral fidelity precedes graphical fidelity

Validate useful audience behavior with a lightweight desktop prototype before investing in photorealistic characters or XR.

Reason: the product hypothesis is improved rehearsal, not rendering quality. Behavioral value can be tested much more cheaply and isolates the actual user benefit.

## I-002 — Simulation semantics are renderer-independent

The Audience Simulation Engine owns canonical participant state and emits typed events. Desktop, high-fidelity 3D, and XR renderers consume those events.

Reason: core project evidence, audience reasoning, and privacy policy must not become coupled to one graphics engine or device ecosystem.

## I-003 — Synthetic audience identities are the default

Use synthetic or role-based audience members by default. Real-person visual/voice cloning is not required for the roadmap feature.

Reason: role and observable interaction history provide most of the rehearsal utility while avoiding unnecessary likeness, biometric, consent, and workplace-surveillance risk.

## I-004 — Real-person Audience Models remain evidence models, not personality models

When a scenario uses a named Audience Model, it may use attributed questions, role, observable recurring concerns, stated criteria, and user notes. It must not claim hidden emotion, diagnosis, sensitive traits, or certain prediction of future behavior.

Reason: the existing Audience Model is designed around authorized observable evidence. Immersive presentation must not silently broaden that boundary.

## I-005 — Deterministic seeded behavior is the baseline

The first Audience Simulation Engine should be predominantly deterministic, bounded, and seedable. Optional model reasoning enriches semantic interpretation and grounded question generation.

Reason: deterministic behavior is testable, reproducible, cheap, local, and resilient when providers are unavailable.

## I-006 — Existing provider/privacy boundaries remain authoritative

Immersive reasoning must use the same core-owned provider execution boundary and privacy modes as Teach, Challenge, and Live Assist. Renderers do not invoke providers directly.

Reason: adding a renderer must not create a second, weaker path for project data to leave the device.

## I-007 — Rendering quality degrades before core latency

When GPU/CPU contention occurs, reduce crowd complexity, animation rate, materials, effects, or render resolution before sacrificing ASR correctness or reasoning/session-state reliability.

Reason: Presenter Copilot remains a rehearsal intelligence product. Visual fidelity must not compromise its core low-latency functions.

## I-008 — XR is a client, not a fork

Future XR support consumes the same scenario and simulation-event protocol as desktop rendering. XR-only telemetry is optional and subject to separate privacy review.

Reason: headset availability and platform APIs will change. Product logic should remain portable.

## I-009 — Store semantic run state, not raw immersive telemetry

Persist scenario definitions, seeds, semantic simulation events, question provenance, and debrief markers. Do not persist animation frames, raw camera frames, or high-frequency XR telemetry by default.

Reason: semantic state is sufficient for comparison/replay while minimizing storage and privacy exposure.

## I-010 — Photorealistic real-person cloning requires a separate decision gate

Any future proposal to recreate identifiable real people visually or vocally requires a separate legal/privacy/safety design review and must not be introduced as an incremental renderer improvement.

Reason: likeness recreation creates qualitatively different consent, biometric, abuse, policy, and jurisdictional risks from synthetic audience simulation.
