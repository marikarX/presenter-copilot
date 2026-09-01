# MVP Developer Package

This directory is the implementation contract for the first working Presenter Copilot MVP.

If a planning document elsewhere in the repository conflicts with this package, this package controls for MVP implementation until the conflict is resolved in `docs/DECISIONS.md`.

## MVP objective

Prove one end-to-end workflow on Windows:

> A presenter imports a real deck and supporting material, teaches the app context in their own words, rehearses against a realistic audience, and can receive short source-grounded cues near the webcam during a live or mock presentation.

The MVP is not a general meeting bot, deck authoring suite, or full teleprompter.

## Frozen product model

The MVP is built around three persistent local objects:

1. **Speaker Profile** — how the presenter naturally explains things, their preferred wording, habits, and accepted/rejected coaching patterns.
2. **Project Brain** — the deck, supporting sources, user explanations, decisions, evidence, rehearsal history, questions, and practiced answers for one presentation/project.
3. **Audience Model** — roles, prior attributed questions, observed communication patterns, recurring concerns, and user-supplied context about the intended audience.

The AI combines these objects according to a selected rehearsal/live mode and a separate style policy.

## MVP modes

- **Teach** — user talks or types with the AI to enrich project context and preserve their own explanations.
- **Challenge** — simulated audience asks grounded questions/objections.
- **Run** — uninterrupted rehearsal with post-run debrief.
- **Live Assist** — private top-center HUD surfaces concise cues during a mock/real presentation.

`Coach` behavior exists initially as post-answer/post-run feedback rather than a separate always-interrupting mode.

## Style policies

- **Preserve my voice** — default; prefer the user's prior wording and explanation patterns.
- **Light polish** — improve clarity while preserving recognizable voice.
- **Executive concise** — shorten and structure more aggressively.
- **Custom** — user-supplied guidance.

Style policy is independent of mode.

## MVP platform

- Windows 11 is the reference platform.
- Laptop webcam/top-center HUD is the reference form factor.
- Desktop is primary; mobile is post-MVP companion work.
- PowerPoint live slide state is supported where practical; manual slide-state fallback is mandatory.

## Implementation baseline

The MVP implementation should use:

- **Electron + React + TypeScript** for desktop UI, window management, global shortcuts, and HUD;
- a **Python sidecar** for ASR, parsing, retrieval, embeddings, orchestration, and model adapters;
- **SQLite** for local structured state;
- float32 embedding vectors persisted locally and searched in-process for the MVP rather than requiring an external vector database;
- local ASR through a replaceable adapter, with `faster-whisper` as the initial reference implementation;
- newline-delimited JSON messages over child-process stdio between Electron and the Python sidecar; no local network listener is required for the desktop MVP;
- provider adapters for reasoning. At least one working provider plus a deterministic/mock provider is required. Local-model and officially supported Codex integrations remain pluggable and must not be architectural dependencies.

Exact dependency versions are pinned when the executable scaffold is created, not in this planning package.

## Developer reading order

1. [`SPEC.md`](SPEC.md) — frozen MVP scope and acceptance criteria.
2. [`UX_FLOWS.md`](UX_FLOWS.md) — screens, modes, and state transitions.
3. [`ARCHITECTURE.md`](ARCHITECTURE.md) — concrete module/runtime design.
4. [`DATA_MODEL.md`](DATA_MODEL.md) — local persistence model and provenance.
5. [`INTERFACES.md`](INTERFACES.md) — IPC/events/provider contracts.
6. [`PRIVACY_SAFETY.md`](PRIVACY_SAFETY.md) — data boundaries and meeting/audience constraints.
7. [`TEST_PLAN.md`](TEST_PLAN.md) — required automated/performance validation.
8. [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — build sequence.
9. [`BACKLOG.md`](BACKLOG.md) — issue-sized P0/P1 work.

## Definition of MVP complete

MVP is complete only when the end-to-end acceptance scenario in `SPEC.md` runs on a clean Windows machine with no developer intervention and passes the privacy-mode and deletion tests.
