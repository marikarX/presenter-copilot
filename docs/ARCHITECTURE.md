# Architecture

## Goals

The architecture should optimize for:

- low latency during live presentation use;
- local handling of sensitive presentation data;
- graceful degradation when cloud models are unavailable;
- pluggable model providers;
- source-grounded answers;
- a lightweight desktop experience rather than a cloud-first meeting bot.

## High-level design

```text
                       USER DEVICE

Deck / docs ------------------------------+
                                          |
                                          v
                                  Ingestion pipeline
                                          |
                                          v
                                   Local knowledge index
                                          |
                                          |
Microphone -> VAD -> Local ASR -> Transcript ----+
                                          |       |
Presentation state / current slide -------+       |
                                                  v
                                          Context builder
                                                  |
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
                                         Response composer
                                                 |
                                                 v
                                      Webcam-adjacent HUD
```

## Local-first processing

The following should run locally by default where hardware permits:

- microphone capture;
- voice activity detection;
- streaming ASR;
- slide state tracking;
- document parsing/indexing;
- embeddings/retrieval;
- transcript persistence;
- simple classification and routing;
- HUD rendering;
- session history;
- basic answer compression.

This keeps continuous processing inexpensive and reduces round-trip latency.

## Reasoning router

Not every utterance should invoke an expensive model.

The router should distinguish at least:

1. **No action** — normal narration; no HUD update needed.
2. **Retrieval only** — surface a known number, fact, citation, or slide reference.
3. **Local reasoning** — summarize or structure retrieved context.
4. **Remote reasoning** — complex comparison, synthesis, objection handling, or ambiguous questions.

The router itself should be deterministic or use a lightweight local model where practical.

## ASR

The implementation should abstract transcription behind an interface so multiple engines can be benchmarked.

Candidate classes:

- local NVIDIA/ONNX/TensorRT-compatible ASR;
- faster-whisper/Whisper-compatible local ASR;
- OS-native transcription when quality is sufficient;
- optional cloud streaming ASR.

Metrics to benchmark:

- first partial latency;
- stable partial latency;
- word error rate on business/technical language;
- GPU/CPU utilization;
- coexistence with a local LLM;
- microphone/device robustness.

## Presentation ingestion

Initial file types:

- PDF;
- PPT/PPTX where parsing is reliable;
- plain text / Markdown;
- common office documents used as supporting sources.

Each source should retain provenance so a surfaced answer can point back to:

- document;
- page/slide;
- section;
- optionally exact text span.

The system should never flatten all presentation material into an untraceable text blob.

## Retrieval

Local retrieval should support:

- current-slide bias;
- nearby-slide context;
- audience-role weighting;
- source priority;
- recency/session memory;
- exact-number lookup;
- semantic retrieval across supporting documents.

A simple local vector store is sufficient for the prototype. The interface should remain replaceable.

## Reasoning backends

Use a provider abstraction. Planned classes:

### Local model

For offline/private operation and cheap continuous processing.

### User-supplied API

For users or organizations that want predictable provider-backed capacity.

### Official agent backend

An optional integration may use an officially supported Codex app-server / SDK flow when appropriate. Authentication must be owned by the official client flow; the application must not scrape browser cookies, extract undocumented tokens, or call undocumented ChatGPT endpoints directly.

Because provider terms, quotas, and product scope can change, this backend must remain optional.

## HUD

The HUD is a first-class component, not a generic chat window.

Default behavior:

- top-center placement near the laptop webcam;
- one to three short lines;
- large readable text;
- minimal horizontal eye movement;
- progressive disclosure;
- confidence/provenance indicator when useful;
- optional slide/source reference;
- no full generated paragraph by default.

Example:

```text
             [ webcam ]

       Active/active regions
       RTO: 17 min
       Mention June failover test
```

The presenter should be able to glance at the cue and continue speaking in their own words.

## Live question pipeline

Target flow:

```text
Audience question
      |
      v
Local partial transcript
      |
      +--> early intent detection
      |
      v
Stable question segment
      |
      v
Retrieve likely sources
      |
      +--> immediate fact cue if high confidence
      |
      v
Reasoning / answer scaffold
      |
      v
HUD update
```

The system should prefer an early correct partial cue over waiting several seconds for a polished paragraph.

## Rehearsal mode

Rehearsal adds:

- simulated audience personas;
- interrupt/question policy;
- answer scoring;
- concise-answer coaching;
- repeated practice on weak objections;
- delivery metrics;
- storage of strongest answer versions.

The simulated audience should be grounded in the same local presentation corpus rather than acting as a generic roleplay bot.

## Data storage

Prototype storage should be local and easy to inspect/delete.

Suggested logical stores:

- project metadata;
- source documents/index metadata;
- embeddings/index;
- transcripts;
- rehearsal sessions;
- questions/answers;
- settings/model configuration.

Encryption-at-rest and enterprise key-management requirements can be layered later, but the schema should avoid assumptions that all data is cloud-hosted.

## Desktop shell

The implementation stack is intentionally undecided. Key requirements are more important than framework choice:

- Windows first-class support;
- transparent always-on-top HUD;
- reliable global shortcuts;
- microphone access;
- local process/model management;
- GPU capability detection;
- screen/presentation state integration;
- eventual macOS support.

## Open technical questions

1. Best Windows desktop shell for low-latency overlays and native integration.
2. Best local ASR quality/latency tradeoff on CPU-only laptops vs RTX systems.
3. Whether slide state is best inferred through PowerPoint integration, screen analysis, or both.
4. Minimum local model size that produces useful answer scaffolds.
5. How to robustly segment an audience question from general room speech.
6. How to keep the HUD helpful without creating dependence or visible reading behavior.
7. How to expose provenance without cluttering the HUD.
