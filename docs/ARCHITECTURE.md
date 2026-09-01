# Architecture

This document captures durable architectural principles. The concrete developer contract for the first implementation is [`docs/MVP/ARCHITECTURE.md`](MVP/ARCHITECTURE.md).

## Goals

The architecture should optimize for:

- low latency during live presentation use;
- local handling of sensitive presentation data;
- graceful degradation when cloud models are unavailable;
- pluggable model providers;
- source-grounded answers;
- preservation of the presenter's own communication style;
- audience-specific rehearsal grounded in authorized evidence;
- a lightweight desktop experience rather than a cloud-first meeting bot.

## Context model

The system deliberately separates three context layers:

```text
Speaker Profile
     +
Project Brain
     +
Audience Model
     |
     v
Mode + style policy
     |
     v
Retrieval / reasoning / cueing
```

### Speaker Profile

User-controlled communication/style evidence: preferred wording, analogies, strong explanations, answer-length preference, and accepted/rejected coaching patterns.

### Project Brain

Project-local deck, sources, user explanations, evidence, decisions, rehearsal history, questions, answer versions, and session state.

### Audience Model

Project-local roles, attributed prior questions, observable recurring concerns/question patterns, and user notes. It must not become a biometric or sensitive-trait dossier.

## High-level design

```text
                       USER DEVICE

Deck / docs / transcripts -----------------+
                                            |
                                            v
                                    Ingestion pipeline
                                            |
                                            v
                                     Project Brain/index
                                            |
Mic -> VAD -> Local ASR -> Transcript ------+----+
                                            |    |
Presentation state / current slide ---------+    |
                                                 v
                                          Context builder
                                     +-----------+----------+
                                     |                      |
                              Speaker Profile         Audience Model
                                     |                      |
                                     +-----------+----------+
                                                 v
                                         Reasoning router
                                          /      |      \
                                         /       |       \
                                        v        v        v
                                  Retrieval   Local LLM  Remote backend
                                        \        |        /
                                         \       |       /
                                          +------v------+
                                                 |
                                                 v
                                           Cue composer
                                                 |
                                                 v
                                      Webcam-adjacent HUD
```

## MVP runtime choice

For MVP implementation, the chosen split is:

- Electron + React + TypeScript for desktop UI/window/HUD behavior;
- Python sidecar for ASR, parsing, retrieval, orchestration, and provider adapters;
- newline-delimited JSON over child-process stdio;
- SQLite + project-local embedding data;
- Windows 11 as reference platform.

This is an MVP implementation decision, not a permanent requirement that every future client use Electron/Python.

## Local-first processing

The following should run locally by default where hardware permits:

- microphone capture;
- voice activity detection;
- streaming ASR;
- slide state tracking;
- document/transcript parsing and indexing;
- embeddings/retrieval;
- transcript persistence;
- speaker/project/audience context persistence;
- simple classification/routing;
- HUD rendering;
- session history;
- basic answer/cue compression.

This keeps continuous processing inexpensive and reduces round-trip latency.

## Reasoning router

Not every utterance should invoke a large model.

The router should distinguish at least:

1. **No action** — normal narration; no HUD update needed.
2. **Retrieval only** — surface a known number, fact, citation, practiced explanation, or slide reference.
3. **Local reasoning** — summarize or structure retrieved context.
4. **Remote reasoning** — complex comparison, synthesis, objection handling, or ambiguous questions.

The router also enforces active privacy mode and provider availability.

## ASR

Transcription is behind an adapter interface. The MVP reference adapter is `faster-whisper`; other local/cloud engines may be benchmarked later.

Metrics:

- first partial latency;
- stable final latency;
- word error rate on business/technical language;
- GPU/CPU utilization;
- coexistence with a local LLM;
- microphone/device robustness.

## Presentation and source ingestion

P0 file classes:

- PDF;
- PPTX;
- Markdown/plain text;
- attributed transcript formats such as VTT/SRT/structured text through adapters.

Each source retains provenance to document/page/slide/section/timestamp/speaker where available.

Do not flatten source material into an untraceable text blob.

## Meeting transcript attribution

For prior meeting context, use attribution in this order:

1. platform/native transcript speaker label;
2. user mapping of that label to a project-local Audience Profile;
3. future diarization only when attribution is missing.

The MVP does not maintain persistent voiceprints or face-recognition identity templates.

## Retrieval

Local retrieval should support:

- exact-number/lexical match;
- current-slide bias;
- nearby-slide context;
- user-authored/preferred explanation boost;
- audience-role relevance;
- source priority;
- semantic retrieval across supporting documents and prior answers;
- `use_live` / privacy filtering;
- conflict detection for exact facts.

The MVP uses an in-process vector search abstraction rather than requiring a standalone vector database.

## Reasoning backends

Use a provider abstraction.

Planned classes:

### Local model

For offline/private operation and cheap continuous processing.

### User-supplied API

For predictable provider-backed capacity using user-owned credentials.

### Official agent backend

An optional integration may use an officially supported Codex app-server/SDK flow where appropriate. Authentication must use official surfaces only. This backend remains optional.

## Style preservation

Style policy is independent from rehearsal/live mode.

Default: `Preserve my voice`.

The context builder should prefer the presenter's own accepted phrases, practiced answers, analogies, and explanations before generating replacement prose.

The system must distinguish:

- user-authored statement;
- user-approved style evidence;
- source fact;
- practiced answer;
- AI inference/suggestion.

## HUD

The HUD is a first-class component, not a generic chat window.

Default behavior:

- top-center placement near laptop webcam;
- one to three short lines;
- large readable text;
- minimal horizontal eye movement;
- progressive disclosure;
- optional confidence/provenance indicator;
- source/slide pointer;
- no full generated paragraph by default;
- global show/hide and push-to-assist controls.

Example:

```text
             [ webcam ]

       Active/active regions
       RTO: 17 min
       Mention June failover test
```

## Live question pipeline

```text
Audience question / recent transcript
      |
      +--> explicit push-to-assist (required MVP fallback)
      |
      +--> automatic segmentation (experimental)
      |
      v
Retrieve likely sources
      |
      +--> immediate fact/practiced-answer cue when high confidence
      |
      v
Reasoning / answer scaffold if needed
      |
      v
HUD update
```

The system should prefer an early correct partial cue over waiting several seconds for polished prose.

## Rehearsal modes

### Teach

Conversationally capture project knowledge and the user's own reasoning/explanations.

### Challenge

Simulate evidence-grounded audience questions and follow-ups; coach/retry weak answers.

### Run

Uninterrupted rehearsal with transcript/slide timeline and post-run debrief.

### Live Assist

Private source-grounded cueing during mock/real presentation.

## Data storage

Prototype storage is local, inspectable, and deletable.

Logical stores include:

- app/global settings and Speaker Profile;
- per-project database/vault;
- source snapshots/extracted units;
- embeddings/index;
- transcripts/sessions;
- Audience Models;
- questions/answers;
- cues/provenance;
- provider context manifests.

Project-local separation is preferred because deletion/export and privacy boundaries become simpler.

## Privacy modes

- **Local Only** — no content-processing network calls.
- **Selected Context Cloud** — raw audio/full corpus local; only question + selected evidence/minimum context may leave the device.
- **Full Context Cloud** — explicit opt-in.

Every remote provider call should have a context manifest recording what source classes/IDs were sent without logging the full confidential prompt by default.

## Mobile direction

Mobile is initially a companion, not an MVP dependency:

- second private cue surface;
- remote controls;
- timer/current/next point;
- optional rehearsal capture;
- secure local-network pairing.

Standalone mobile rehearsal comes only after desktop value is validated.

## Open technical questions after MVP freeze

1. Best embedding model/runtime across CPU-only and RTX Windows hardware.
2. Best PowerPoint current-slide adapter reliability and packaging approach.
3. Minimum useful local model size for answer scaffolding.
4. Robust automatic audience-question segmentation beyond push-to-assist.
5. Best way to quantify style preservation without turning it into an opaque personality score.
6. How much Audience Model context improves rehearsal before it becomes noisy/overfit.
7. When the simple in-process vector index should be replaced for larger projects.
