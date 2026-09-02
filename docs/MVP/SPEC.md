# MVP Product Specification

## 1. Goal

Build the smallest Windows desktop product that proves the Presenter Copilot thesis:

> The system can learn a presenter's material and natural explanations, rehearse them against a realistic audience, and surface private, source-grounded cues fast enough to help during a live presentation without turning the user into a script reader.

## 2. Primary user

A technically or commercially knowledgeable professional preparing for a high-stakes presentation, for example:

- sales engineer / solution architect;
- consultant;
- founder;
- product/engineering leader;
- executive presenting to a board or review committee.

## 3. Core concepts

### 3.1 Speaker Profile

Persistent, local, user-controlled profile of the presenter's own communication patterns.

MVP stores:

- preferred vocabulary/phrasing explicitly learned from user speech or accepted edits;
- examples/analogies the user naturally uses;
- answer length preference;
- formality/directness preference;
- recurring coaching notes accepted by the user;
- explicit style guidance.

The system must prefer a user's prior strong explanation over newly generated prose when both answer the same question.

### 3.2 Project Brain

Project-local corpus containing:

- presentation/deck;
- supporting documents;
- extracted slide/page text;
- user Teach-mode explanations;
- user-supplied facts/decisions;
- rehearsal sessions;
- questions and answer versions;
- source provenance;
- project-specific audience context.

### 3.3 Audience Model

Project-local model of the intended audience.

MVP may learn from:

- manually entered participant roles/concerns;
- named Teams/Webex/other meeting transcripts imported by the user;
- user notes about expected objections;
- questions actually asked during rehearsal/live sessions.

MVP models observable interaction patterns, not hidden psychological or sensitive traits.

In M4, named transcript labels remain unresolved metadata until the user
explicitly maps them to project-local AudienceProfiles. Deterministic local
extraction creates provisional, evidence-backed candidates for review; it
does not call a remote provider or silently activate observations.

## 4. Supported inputs

P0:

- PDF;
- PPTX;
- Markdown/plain text;
- named transcript text formats that preserve speaker labels where available (VTT/SRT/TXT/structured export through an adapter).

P1/stretch:

- DOCX/XLSX extraction where reliable;
- meeting audio/video import with diarization fallback;
- direct Teams/Webex connector ingestion.

For MVP, native transcript speaker attribution is used before any diarization. Persistent biometric voice identification is out of scope.

## 5. Modes

### Teach

Purpose: enrich the Project Brain using the user's own speech/thought process.

Required behavior:

- voice or text conversation;
- AI asks clarifying questions about claims, decisions, weak assumptions, likely objections, and evidence gaps;
- user explanations are stored with `source_type=user` and session provenance;
- user may mark an explanation as `keep`, `preferred answer`, `private note`, or `do not use live`;
- extracted style evidence can update the Speaker Profile only with visible user control.

### Challenge

Purpose: simulate likely audience Q&A.

Required behavior:

- choose one or more audience profiles;
- generate grounded questions from Project Brain + Audience Model;
- avoid generic questions when project-specific evidence exists;
- let user answer by voice;
- evaluate correctness, directness, completeness, source support, and concision;
- offer retry;
- save best answer versions.

### Run

Purpose: uninterrupted rehearsal.

Required behavior:

- start microphone capture and ASR;
- track current slide manually and, where supported, from PowerPoint;
- do not interrupt unless user requests a question segment;
- save transcript and slide timeline;
- produce a post-run debrief with weak points and likely questions.

### Live Assist

Purpose: private cueing during a mock or real presentation.

Required behavior:

- always-on-top HUD near webcam;
- content protection enabled where supported so HUD is excluded from ordinary capture paths;
- default cue length: 1–3 short lines;
- retrieval-first behavior;
- source/slide pointer available without expanding into a chat window;
- global hotkey to hide/show HUD;
- global hotkey or button to request assistance explicitly;
- automatic question segmentation may be experimental, but explicit push-to-assist is mandatory as a reliable fallback.

## 6. Style policies

### Preserve my voice — default

- prefer prior user wording;
- do not introduce unnecessary corporate/AI phrasing;
- keep answer structure recognizable to the user's prior speech;
- surface cue scaffolds, not polished paragraphs.

### Light polish

- fix ambiguity and grammar;
- tighten excessive repetition;
- preserve vocabulary and tone.

### Executive concise

- compress to decision/reason/evidence structure;
- stronger prioritization and shorter answers;
- may rephrase more aggressively.

### Custom

User enters explicit guidance stored per project or globally.

## 7. Privacy modes

### Local Only

No network call from the reasoning/ASR/data path. Tests must verify this.

### Selected Context Cloud

Raw audio and complete corpus remain local. Only question + selected excerpts + minimum required style/audience context may leave the device.

### Full Context Cloud

Explicit opt-in only. Not required for MVP acceptance beyond configuration plumbing.

## 8. Source/provenance rules

Every fact-bearing cue/answer must be able to point to one or more of:

- slide number;
- document/page/section;
- user Teach-mode statement;
- prior practiced answer;
- imported attributed transcript statement.

AI-only inferences must be labeled as inference/suggestion rather than source fact.

## 9. End-to-end acceptance scenario

A tester on Windows must be able to:

1. create a new project;
2. import a 20–30 slide PPTX/PDF and at least two supporting documents;
3. optionally import a prior named transcript and map its speakers to audience profiles;
4. complete a 5-minute Teach conversation explaining at least two decisions in their own words;
5. see those explanations retained as user-authored project knowledge;
6. enter Challenge mode with two audience profiles;
7. receive at least five project-specific questions with visible source rationale;
8. answer by voice and retry at least one weak answer;
9. run a rehearsal while changing slides;
10. enter Live Assist and ask or receive a question whose answer exists in project sources;
11. receive a useful first cue near the webcam quickly enough to use while speaking;
12. expand the cue to inspect provenance;
13. exit and reopen the app with project state preserved;
14. delete the project and verify its indexed/transcript/source snapshot data is removed.

## 10. Performance targets

Targets are reference-machine goals, not public SLAs.

Reference machine class: modern Windows laptop/desktop; RTX GPU is optional.

- local ASR first partial: p50 <= 500 ms after speech onset;
- stable final after end of utterance: p50 <= 900 ms;
- local retrieval: p95 <= 250 ms for <= 50k chunks;
- end-of-question to first useful retrieval-only cue: p50 <= 1.2 s, p95 <= 2.5 s;
- complex remote-reasoned cue: useful partial target <= 4 s where provider latency permits;
- HUD show/hide hotkey response: <= 100 ms perceived latency;
- idle RAM target for UI/core excluding loaded ML model: <= 500 MB;
- no unbounded transcript/index growth within a session.

## 11. P0 non-goals

- generating/editing presentation decks;
- avatars or synthetic presenter video;
- automatic spoken answers in live mode;
- emotion recognition;
- personality/mental-state inference about audience members;
- persistent voiceprints or face recognition;
- cloud-hosted meeting bot joining calls;
- mobile parity;
- team/enterprise admin plane;
- automatic CRM/LMS integration;
- Teams/Webex-specific transcript connectors, audio/video import, and
  diarization fallback;
- invisible/undetectable-cheating marketing.

## 12. MVP success criteria

The MVP is worth continuing if test users consistently report all three:

1. **Preparation value** — the app discovers non-obvious questions/weaknesses from their actual material.
2. **Personalization value** — suggested answers/cues feel more like their own reasoning than generic LLM prose.
3. **Live value** — the HUD surfaces the right fact/structure fast enough to help without requiring visible reading.
