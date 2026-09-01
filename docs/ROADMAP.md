# Roadmap

## Phase 0 — Validate the wedge

Goal: prove that the product is more useful than generic rehearsal tools or a normal LLM chat.

Tasks:

- collect 5–10 real high-stakes decks from willing testers;
- define 3–5 representative audience personas;
- test whether generated objections are materially relevant;
- measure whether coached answers become shorter and stronger;
- prototype the top-center HUD geometry on common laptop displays;
- validate whether local ASR latency is fast enough for live use.

Exit criteria:

- users report at least several non-obvious useful questions per deck;
- HUD cues can appear quickly enough to affect an answer without disrupting speech;
- users prefer cue scaffolds to full generated prose.

## Phase 1 — Local rehearsal prototype

Build:

- desktop shell;
- PDF/PPT ingestion;
- local document index;
- local microphone capture and ASR;
- session transcript;
- slide/context tracking;
- simple audience personas;
- Q&A rehearsal;
- basic debrief.

No enterprise features yet.

## Phase 2 — Live HUD prototype

Build:

- always-on-top top-center cue surface;
- question segmentation;
- retrieval-first response path;
- progressive cue updates;
- source/slide references;
- keyboard shortcuts for hide/expand/next;
- latency instrumentation.

Critical metric: question-to-useful-cue latency.

## Phase 3 — Mobile companion

Treat mobile first as a companion to the desktop presentation engine rather than a full replacement.

Build:

- paired phone/tablet connection to the desktop app;
- private cue-card display on a phone placed near or below the presentation display;
- presenter remote controls for next/previous cue, hide, expand, and mark question;
- timer, current slide, next talking point, and source reference view;
- rehearsal recording/capture from the phone when a laptop is inconvenient;
- secure local-network mode so companion traffic does not require a cloud relay;
- optional haptic cues for timing or transitions.

Later mobile expansion, only after the companion workflow proves useful:

- standalone presentation rehearsal from a phone/tablet;
- import/share a deck into the mobile app;
- on-device ASR and lightweight retrieval where hardware permits;
- mobile camera-based delivery coaching;
- Apple Watch/Wear OS cue or timer surfaces if there is demonstrated demand.

Why this matters:

- the phone can act as a second private screen while the laptop is screen-sharing;
- a presenter can keep cues physically closer to the audience/camera sightline;
- mobile rehearsal increases usage frequency outside the desk setup;
- the companion can become a low-friction entry point without weakening the local-first desktop architecture.

Do not make full cross-platform mobile parity an MVP requirement.

## Phase 4 — Hybrid reasoning

Build:

- provider abstraction;
- local model backend;
- user-supplied API backend;
- optional officially supported agent backend such as Codex app-server where appropriate;
- local router deciding when remote reasoning is justified;
- explicit privacy-mode controls.

## Phase 5 — Closed learning loop

Build:

- remember real questions by presentation/project;
- compare predicted vs. actual objections;
- store best answer versions;
- identify recurring weak points;
- prioritize future rehearsal automatically;
- audience/stakeholder history.

This phase is strategically more important than adding broad presentation-authoring features.

## Phase 6 — Integrations

Candidates:

- PowerPoint live slide state;
- Keynote;
- Google Slides;
- Teams/Zoom/Webex meeting context where technically and contractually appropriate;
- file/document sources used by enterprise teams.

Integrations should follow validated user demand, not precede core product quality.

## Phase 7 — Team / enterprise layer

Possible commercial features:

- shared audience persona libraries;
- team presentation knowledge;
- approved messaging/playbooks;
- readiness/certification workflows;
- admin model/provider policy;
- local-only enforcement;
- SSO;
- audit/retention controls;
- analytics on recurring objections and weak answers;
- managed deployment.

## Open-source strategy checkpoint

Before public release, decide:

- core license;
- what remains fully open source;
- whether commercial functionality is hosted, enterprise-only, or open-core;
- contributor model;
- trademark/public product name;
- provider-integration terms and branding requirements.

Do not select the public brand solely because a domain is available. Screen search engines, GitHub, app stores, competitors, domains, and trademarks first.
