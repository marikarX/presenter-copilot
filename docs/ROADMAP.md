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

## Phase 3 — Hybrid reasoning

Build:

- provider abstraction;
- local model backend;
- user-supplied API backend;
- optional officially supported agent backend such as Codex app-server where appropriate;
- local router deciding when remote reasoning is justified;
- explicit privacy-mode controls.

## Phase 4 — Closed learning loop

Build:

- remember real questions by presentation/project;
- compare predicted vs. actual objections;
- store best answer versions;
- identify recurring weak points;
- prioritize future rehearsal automatically;
- audience/stakeholder history.

This phase is strategically more important than adding broad presentation-authoring features.

## Phase 5 — Integrations

Candidates:

- PowerPoint live slide state;
- Keynote;
- Google Slides;
- Teams/Zoom/Webex meeting context where technically and contractually appropriate;
- file/document sources used by enterprise teams.

Integrations should follow validated user demand, not precede core product quality.

## Phase 6 — Team / enterprise layer

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
