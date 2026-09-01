# Development Guide

Presenter Copilot is still in the architecture/prototyping stage. This document defines development expectations without pretending the implementation stack has already been selected.

## Current status

No production framework, package manager, desktop runtime, mobile framework, database, ASR engine, or model runtime is yet mandatory.

When implementation begins, this document should become the canonical source for:

- prerequisites;
- local setup;
- build commands;
- test commands;
- lint/format commands;
- packaging;
- platform-specific notes;
- model downloads;
- local services and ports.

## Repository conventions

Until a concrete stack is selected:

- keep product/architecture decisions in `docs/`;
- record durable architectural decisions in `docs/DECISIONS.md` or future ADRs;
- keep secrets and local model artifacts out of Git;
- prefer deterministic, scriptable setup over hand-configured environments;
- keep local and cloud model integrations behind interfaces rather than spreading provider-specific calls through UI code;
- keep the live HUD independent from model/provider logic.

## Expected architecture boundaries

The implementation should preserve separable modules for:

1. presentation/document ingestion;
2. local indexing and retrieval;
3. microphone capture and ASR;
4. presentation/slide state;
5. reasoning/router layer;
6. model-provider adapters;
7. rehearsal engine;
8. live HUD;
9. session storage and deletion;
10. mobile-companion transport;
11. telemetry/diagnostics, if any.

## Testing priorities

The first automated tests should focus on behavior that is easy to regress and hard to notice manually:

- document parsing and chunk provenance;
- retrieval correctness;
- cue compression/length constraints;
- privacy-mode routing;
- provider fallback behavior;
- transcript/session deletion;
- local listener binding and companion authentication;
- HUD visibility/state transitions;
- latency measurement.

## Performance targets

Exact thresholds will be validated experimentally, but the product should measure at minimum:

- microphone-to-partial-transcript latency;
- end-of-question detection latency;
- retrieval latency;
- question-to-first-useful-cue latency;
- question-to-complete-cue latency;
- memory and GPU/CPU usage during presentation mode.

## Sample data

Tests and demos must use synthetic or explicitly distributable sample decks and documents. Never commit customer presentations, private meeting recordings, credentials, or proprietary corpora.

## Logging

Logs should be useful without becoming a privacy leak.

Do not log:

- provider access tokens;
- OAuth refresh tokens;
- raw confidential document content by default;
- full microphone transcripts by default;
- API keys;
- local file contents unrelated to an explicit diagnostic export.

Diagnostic exports should be explicit and reviewable by the user before sharing.
