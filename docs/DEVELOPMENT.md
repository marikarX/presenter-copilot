# Development Guide

Presenter Copilot now has a frozen developer-ready MVP contract under [`docs/MVP/`](MVP/README.md). That package controls MVP implementation when older planning text is less specific.

## MVP implementation baseline

For the first executable Windows MVP:

- desktop: Electron + React + TypeScript;
- core/ML sidecar: Python;
- desktop/core IPC: newline-delimited JSON over child-process stdio;
- structured local state: SQLite;
- local embeddings: project-local float32 matrix/in-process search for P0 scale;
- reference ASR adapter: `faster-whisper` behind a replaceable interface;
- provider integrations behind a single reasoning-provider interface;
- Windows 11 is the reference platform;
- no always-required cloud/server backend.

Exact dependency versions and package-manager lockfiles are established by the scaffold commit and then become authoritative.

## Start here

Read in order:

1. [`MVP/SPEC.md`](MVP/SPEC.md)
2. [`MVP/ARCHITECTURE.md`](MVP/ARCHITECTURE.md)
3. [`MVP/DATA_MODEL.md`](MVP/DATA_MODEL.md)
4. [`MVP/INTERFACES.md`](MVP/INTERFACES.md)
5. [`MVP/IMPLEMENTATION_PLAN.md`](MVP/IMPLEMENTATION_PLAN.md)
6. [`MVP/BACKLOG.md`](MVP/BACKLOG.md)
7. [`MVP/TEST_PLAN.md`](MVP/TEST_PLAN.md)

## Target repository structure

```text
apps/
  desktop/
    src/main/
    src/preload/
    src/renderer/
    src/hud/
core/
  presenter_core/
    ipc/
    ingestion/
    asr/
    retrieval/
    models/
    orchestration/
    rehearsal/
    audience/
    speaker/
    storage/
    providers/
  tests/
shared/
  schemas/
samples/
  synthetic-deck/
docs/
  MVP/
```

Do not create these folders merely to match documentation; scaffold them as the corresponding implementation lands.

## Development principles

- preserve module boundaries from `MVP/ARCHITECTURE.md`;
- keep local/cloud model integrations behind interfaces;
- keep HUD independent from model/provider logic;
- renderer must not receive raw filesystem/provider-secret authority;
- use provenance objects end-to-end instead of plain answer strings;
- make privacy routing testable before provider invocation;
- prefer a working vertical slice over speculative abstraction;
- record durable deviations in `docs/DECISIONS.md`.

## First scaffold requirements

The scaffold milestone must establish reproducible commands for:

- dependency install;
- desktop dev run;
- Python core dev run/tests;
- combined desktop + core run;
- lint;
- format;
- type checking;
- unit tests;
- packaging smoke test.

Update this document with the exact commands as soon as the scaffold exists.

## Expected architecture boundaries

Implementation must preserve separable modules for:

1. presentation/document ingestion;
2. local indexing and retrieval;
3. microphone capture and ASR;
4. presentation/slide state;
5. reasoning/router layer;
6. model-provider adapters;
7. Speaker Profile;
8. Audience Model;
9. rehearsal modes;
10. live HUD;
11. session/project storage and deletion;
12. future mobile-companion transport;
13. local diagnostics/benchmarking.

## Testing priorities

Before broad feature work, automate behavior that is easy to regress and expensive to discover manually:

- document parsing and chunk provenance;
- exact-number/retrieval correctness;
- cue <=3-line constraint;
- Preserve-My-Voice preference for accepted user wording;
- native transcript speaker mapping;
- prohibited audience observation filtering;
- privacy-mode routing/context manifests;
- provider fallback behavior;
- transcript/session/project deletion;
- renderer/preload IPC allowlist;
- HUD visibility/state transitions;
- latency measurement.

The release gate is defined in [`MVP/TEST_PLAN.md`](MVP/TEST_PLAN.md).

## Performance measurements

Measure at minimum:

- microphone-to-partial-transcript latency;
- end-of-utterance finalization latency;
- retrieval latency;
- question-to-first-useful-cue latency;
- question-to-complete-cue latency;
- HUD render latency;
- memory and CPU/GPU use during presentation mode.

Benchmarks must include hardware/build metadata but not confidential transcript/source content.

## Sample data

Tests and demos must use synthetic or explicitly distributable sample decks and documents. Never commit customer presentations, private meeting recordings, credentials, or proprietary corpora.

The P0 synthetic fixture requirements are defined in `MVP/TEST_PLAN.md`.

## Logging

Logs should be useful without becoming a privacy leak.

Do not log by default:

- provider access tokens;
- OAuth refresh tokens;
- API keys;
- raw confidential document content;
- complete transcripts;
- complete remote prompts;
- persistent voice/face biometric templates.

Diagnostic exports should be explicit and reviewable by the user before sharing.
