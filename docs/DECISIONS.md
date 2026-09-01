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

## D-012 — Apache-2.0 for the open-source repository

**Status:** Accepted

The repository is licensed under the Apache License 2.0.

Reason:

Apache-2.0 is permissive, allows commercial use and modification, and includes an explicit contributor patent grant. It is a strong fit for an open-source AI/tooling project while leaving room for future separately developed hosted or enterprise services.

This decision does not determine the eventual commercial boundary. Remaining questions include:

- what stays in the open-source core;
- whether commercial functionality is hosted, enterprise-only, or open-core;
- contributor/CLA/DCO policy if contribution volume grows;
- trademark/public naming;
- third-party model/provider licensing and terms.

## D-013 — Mobile starts as a companion, not full platform parity

**Status:** Accepted as roadmap direction

The first mobile implementation should pair with the desktop app for private cue display, presenter controls, timers, and lightweight rehearsal capture.

Reason:

A second screen is useful while the laptop is screen-sharing and can sit close to the camera/audience sightline. Full standalone mobile parity would add substantial scope before the desktop interaction model is validated.

## D-014 — Product state is Speaker Profile + Project Brain + Audience Model

**Status:** Accepted

The MVP conceptual model has three distinct context layers:

- **Speaker Profile** — the user's own approved communication/style evidence;
- **Project Brain** — deck, sources, user explanations, decisions, rehearsals, questions, and answers for one project;
- **Audience Model** — project-local audience roles, attributed prior questions, observable interaction patterns, and user notes.

Reason:

Keeping these layers distinct gives the system better provenance, deletion semantics, personalization, and privacy than one undifferentiated vector store or chat history.

## D-015 — Preserve the user's voice by default

**Status:** Accepted

`Preserve my voice` is the default style policy. The application should prefer the user's own prior strong wording/explanations over newly generated prose.

Reason:

The product should make the presenter better prepared and clearer without making them sound like a generic LLM. Style learning must be visible, user-controlled, and removable.

## D-016 — Native transcript attribution before diarization; no persistent biometrics in MVP

**Status:** Accepted

When prior meeting transcripts are imported, preserve platform/native speaker names and timestamps first. Let the user map those labels to project-local audience profiles. Diarization is only a future fallback when attribution is missing.

Do not persist voiceprints, facial embeddings, or biometric identity templates in the MVP.

Reason:

Teams/Webex and similar transcripts often already contain useful attribution. Reusing that metadata is more accurate, simpler, and avoids unnecessary biometric/privacy complexity.

## D-017 — MVP desktop stack is Electron + TypeScript UI with a Python core sidecar

**Status:** Accepted for MVP

Use Electron/React/TypeScript for desktop/HUD behavior and a Python sidecar for parsing, ASR, retrieval, orchestration, and provider adapters.

Electron main process communicates with the sidecar over newline-delimited JSON on child-process stdio. Normal desktop operation does not require a localhost network listener.

Reason:

This split optimizes implementation speed while preserving strong boundaries: Electron is effective for Windows overlays/global shortcuts/capture protection, while Python has the strongest ecosystem for local speech/ML/document tooling. Stdio keeps the local attack surface small and is replaceable later.

## D-018 — Push-to-assist is the reliable MVP live trigger

**Status:** Accepted

Automatic audience-question detection may be developed experimentally, but MVP Live Assist must always support an explicit global push-to-assist action using the recent local transcript/current slide.

Reason:

Perfectly segmenting audience questions in arbitrary rooms is a hard reliability problem. The live-value hypothesis can be tested without making automatic detection a release blocker.

## D-019 — Milestone 0 shares protocol through a schema and contract fixtures

**Status:** Accepted for the scaffold

Keep `shared/schemas/protocol-v1.schema.json` as the canonical envelope
description and validate `protocol-v1.examples.json` from both the Python and
TypeScript test suites. Runtime code keeps small, explicit native types instead
of adding a schema-generation tool before the first domain payload exists.

Reason:

Milestone 0 has only three lifecycle methods. A shared schema plus executable
cross-language examples catches envelope drift while preserving the simple
Electron/Python boundary. Future method contracts can extend the schema or
introduce generated types when that becomes materially useful.

## D-020 — Renderer IPC authority is explicit and sender-origin checked

**Status:** Accepted for the scaffold

Privileged renderer-to-main IPC accepts only the exact bundled renderer file or
the exact loopback Vite development renderer in the explicit development run.
The main process also requires the sending frame to be the window's main frame.
Renderer-callable core methods have their own explicit runtime and TypeScript
allowlist; adding an internal core method does not expand renderer authority.

Reason:

The renderer boundary is a security boundary, not only a type boundary. Parsed
URL and frame checks prevent a future navigation, child frame, or environment
mistake from turning a new internal capability into renderer authority.
