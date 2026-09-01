# Decision Log

This file records product and architecture decisions that are important enough to preserve across implementation changes.

## D-001 — Working repository name is not the public brand

**Status:** Accepted

Use `presenter-copilot` as a descriptive internal repository name.

Reason:

Early naming attempts such as CuePilot and CoPres collided with existing products/companies. Public naming should be screened deliberately rather than chosen during architecture work.

## D-002 — Local-first architecture

**Status:** Accepted as core hypothesis

Continuous latency-sensitive processing should run locally where practical.

Includes:

- audio capture;
- VAD;
- ASR;
- retrieval;
- presentation state;
- HUD rendering;
- session history.

Reason:

Local processing simultaneously improves latency, privacy, and marginal economics.

## D-003 — Hybrid rather than cloud-only reasoning

**Status:** Accepted

Remote reasoning is an escalation path, not the default path for every utterance.

Reason:

Many live presentation needs are retrieval or compression tasks. Sending continuous audio/context to a frontier model is unnecessary and creates cost/privacy/latency penalties.

## D-004 — Provider-pluggable reasoning

**Status:** Accepted

The core application must not depend on one model provider or one authentication mechanism.

Target backend classes:

- local model;
- user-supplied API;
- officially supported agent/backend integration.

Reason:

Provider terms, quotas, pricing, and model quality change. Backend portability is strategically important.

## D-005 — Codex integration must use official surfaces only

**Status:** Accepted

If Codex is integrated, use officially documented SDK/app-server authentication and invocation mechanisms.

Do not:

- scrape ChatGPT browser cookies;
- extract OAuth tokens for unrelated use;
- directly call undocumented ChatGPT backend endpoints;
- treat personal ChatGPT capacity as a guaranteed permanent commercial entitlement.

Codex remains optional until provider terms and intended product use are sufficiently clear for the chosen distribution model.

## D-006 — HUD is not a traditional teleprompter

**Status:** Accepted

Default HUD content is concise cueing, not prose.

Preferred output:

- keywords;
- numbers;
- answer structure;
- source/slide pointer;
- reminder of a practiced example.

Reason:

The objective is to support natural speaking and eye contact rather than replace the presenter with generated text.

## D-007 — Webcam-adjacent placement

**Status:** Accepted as UX hypothesis

The default cue surface should appear immediately below/around the top-center laptop webcam.

Reason:

This minimizes visible eye deviation without requiring specialized teleprompter hardware.

Needs validation across different webcam/display geometries.

## D-008 — High-stakes presentations are the initial wedge

**Status:** Accepted

Prioritize presentations where being prepared has material value:

- enterprise sales;
- technical proposals;
- board/executive reviews;
- investor pitches;
- consulting recommendations;
- bid/proposal defenses.

Reason:

Generic public-speaking coaching is crowded and has lower pricing power. High-stakes readiness has stronger willingness to pay and a clearer need for source-grounded Q&A.

## D-009 — Do not position as stealth/undetectable AI

**Status:** Accepted

Position the live interface as an AI-enhanced private presenter view.

Reason:

This is more compatible with enterprise adoption and avoids tying the product identity to cheating/deception use cases.

## D-010 — Rehearsal and live mode share one knowledge system

**Status:** Accepted

The same presentation corpus, audience model, questions, and practiced answers should flow from rehearsal into live mode and back into future rehearsal.

Reason:

This closed loop is a stronger differentiation hypothesis than isolated rehearsal or live-answer features.

## D-011 — Source provenance is required for important answers

**Status:** Accepted

The system should preserve where a surfaced fact or answer came from.

Reason:

High-stakes presentations often involve exact numbers and defensible claims. Generic model output without provenance is not sufficient.

## D-012 — Open source is a strategy hypothesis, not yet a licensing decision

**Status:** Open

The project is currently being designed with an open-source core in mind, but the exact license and commercial boundary are undecided.

Before public release evaluate:

- MIT vs Apache-2.0 vs other approaches;
- trademark/public naming;
- enterprise/open-core boundary;
- contributor expectations;
- third-party model/provider licensing and terms.
