# MVP Implementation Plan

## 1. Delivery strategy

Build vertical slices that remain runnable. Do not implement every subsystem in isolation before producing a user-visible flow.

The recommended order is:

1. desktop/core scaffold;
2. project/source ingestion;
3. retrieval/provenance;
4. Teach + Speaker Profile;
5. Audience Model + transcript import;
6. Challenge;
7. ASR + Run;
8. HUD + push-to-assist;
9. provider/privacy routing;
10. packaging/performance hardening.

Each milestone has an executable exit criterion.

## Milestone 0 — Repository scaffold

### Build

- Electron + React + TypeScript app;
- Python core package;
- deterministic Python environment tooling;
- Electron launches/stops sidecar;
- NDJSON IPC handshake;
- unit-test runners for TypeScript and Python;
- formatting/linting/type checking;
- CI for non-hardware tests;
- `samples/synthetic-deck/` fixture skeleton.

### Exit

Packaged/dev app opens, core reports health, one request/event round trip is tested, and both language test suites run from documented commands.

## Milestone 1 — Local project vault and ingestion

### Build

- ProjectService;
- app/project SQLite creation/migrations;
- import UI;
- source snapshot directory;
- PDF/PPTX/TXT/Markdown parsers;
- slide/page SourceUnits;
- chunking and provenance;
- source list/preview/delete/re-index;
- exact/lexical search first.

### Exit

User imports the synthetic deck + two documents and can inspect extracted slide/page text with provenance after restart.

## Milestone 2 — Embeddings and retrieval

### Build

- embedding adapter;
- embedding persistence;
- local matrix search;
- metadata filters;
- current-slide boosts;
- exact number/lexical boost;
- evidence object contract;
- retrieval inspection developer panel.

### Exit

Golden retrieval tests return expected facts/pages/slides from synthetic fixture within target latency for <=50k chunks.

## Milestone 3 — Teach and Speaker Profile

### Build

- provider abstraction + deterministic fake provider;
- one real reasoning provider adapter;
- Teach UI;
- typed Teach flow first;
- AI asks targeted context questions;
- KnowledgeItem candidate/confirm/edit/reject;
- `use_live`, `preferred`, and `private` flags;
- Speaker Profile UI;
- explicit approval before global style evidence is stored;
- style context builder.

### Exit

User can teach two rationales, confirm them, reopen project, and retrieval/provider context prefers the user-authored explanation when relevant.

## Milestone 4 — Transcript import and Audience Model

### Build

- VTT/SRT/named-TXT/structured-JSON adapters;
- preserve timestamps/native speaker labels in transcript SourceUnits;
- explicit native-label mapping UI with unresolved defaults;
- project-local AudienceProfile CRUD;
- deterministic, local, evidence-backed observable-pattern candidates;
- provisional candidate edit/accept/reject and accepted observation
  edit/delete;
- prohibited sensitive/hidden-trait category filter;
- bounded AudienceContextBuilder with active profiles and accepted,
  non-stale observations only;
- source re-index/delete and project-delete lifecycle invalidation.

### Exit

The synthetic named transcript imports with three native labels; two labels
map explicitly to project-local AudienceProfiles and one remains unresolved.
Extraction creates reviewable candidates only from currently attributed
transcript segments. Accepted observations retain exact transcript evidence,
remain after restart, become stale after incompatible remapping, and never
enter context after their evidence is removed. The transcript authorization
disclosure appears before the native picker opens.

M4 does not include Teams/Webex-specific connectors, audio/video import,
diarization, remote transcript profiling, or Challenge mode.

## Milestone 5 — Challenge mode

### Build

- Challenge setup UI;
- audience selection;
- question generation schema;
- project/audience-grounded question prompt/context;
- typed answer first;
- evaluation schema: correctness/directness/completeness/concision/style match;
- retry;
- preferred answer storage;
- question/answer history.

### Exit

Challenge produces project-specific questions for two synthetic audience profiles, user retries a weak answer, and preferred answer becomes retrievable evidence.

M5 implementation status for this branch: typed Challenge setup, bounded
project-local AudienceProfile selection, canonical Project Brain grounding,
advisory evaluation, retry/follow-up history, explicit preferred-answer
promotion, recovery, and the E2E-04 synthetic acceptance gate. Challenge
remains typed-first; M6 intentionally kept ASR out of Teach and Challenge,
with the later G09 slice adding local voice only to Teach.

## Milestone 6 — Local ASR and Run mode

### Build

- microphone selection;
- ASR adapter interface;
- `faster-whisper` reference adapter;
- model download/status path;
- partial/final events;
- VAD/end-of-utterance handling;
- Run session UI;
- slide timeline;
- manual slide controls;
- PowerPoint adapter behind feature detection;
- post-run debrief.

M6 implementation status for this branch: Python-owned local capture with
`sounddevice`, deterministic energy VAD, pinned `faster-whisper` and fixture
adapters, explicit model preparation, bounded partial/final events, durable
Run transcript/timeline/markers, main-owned manual slide shortcuts, read-only
PowerPoint matching/fallback, restart-safe state, deletion cleanup, and a
deterministic retrieval-backed debrief.

### Exit

A user can rehearse a full synthetic deck by voice, change slides, stop, and
view a persisted transcript/debrief after restart. CI uses injected audio/ASR
and presentation fakes; real local ASR uses the explicit model bootstrap and
checked-in synthetic speech fixture.

## Milestone 7 — Live HUD and push-to-assist

### Build

- dedicated HUD BrowserWindow;
- top-center positioning/calibration;
- font/width controls;
- show/hide global shortcut;
- push-to-assist shortcut;
- click-through collapsed mode;
- capture protection where supported;
- CueService enforcing <=3 lines;
- progressive `cue.partial` / `cue.ready` events;
- provenance expansion;
- retrieval-only fast path;
- graceful core/provider failure state.

### Exit

During a mock presentation, push-to-assist on a known question produces a source-grounded cue in the HUD within performance target and can be hidden instantly.

M7 implementation status for this branch: Live Assist is a real session mode
that reuses the M6 local ASR and presentation-state services. The Python core
owns bounded question assembly, live retrieval, cue persistence/provenance,
provider routing, logical supersession, and failure fallback. Electron owns a
dedicated isolated HUD window, main-process global shortcuts, top-center
calibration, click-through collapsed mode, and visible best-effort capture
protection status. Automatic question segmentation is intentionally deferred.

## Milestone 8 — Privacy routing and provider resilience

### Build

- Local Only enforcement;
- Selected Context Cloud builder;
- context manifests;
- provider health/auth/quota states;
- provider cancellation/timeouts;
- retrieval-only fallback;
- optional local-model adapter if practical (deferred in this branch);
- experimental Codex adapter only if official integration remains appropriate and does not block release (deferred in this branch).

### Exit

Local Only passes network-isolation tests; Selected Context Cloud fake-provider capture contains only expected minimum context; provider failure falls back without ending the session.

M8 implementation status for this branch: Teach, Challenge, and Live Assist
share one `ProviderExecutionService`. It rereads the project privacy row and
remote acknowledgement immediately before invocation, rejects remote calls
from Local Only, validates the exact serialized payload, derives a
metadata-only manifest from that payload, and commits the `ProviderRun`
started state before provider I/O. Provider failures update process-local
health with stable actionable states; bounded timeout and logical
supersession/cancellation finalize runs exactly once and discard ineligible
results. `privacy.list_context_manifests` exposes only bounded run metadata
and sanitized manifests. Optional local/Codex adapters remain deferred.

## G09 — Voice-first Teach using the existing local ASR stack

### Build

- mode-aware ownership for the shared Core ASR capture;
- transient `teach.voice_start`, `teach.voice_stop`, and `teach.voice_cancel`
  lifecycle;
- bounded ephemeral partials and final-only voice answer submission through
  `TeachService.submit_text`;
- existing candidate, provenance, confirmation, privacy, and typed fallback
  behavior in the Teach panel;
- deterministic injected audio/ASR, IPC, renderer-boundary, privacy, and
  restart/shutdown coverage.

### Exit

Voice and typed Teach answers share one state machine and one submission path;
only finalized voice text can create the ordinary user utterance/candidate;
cancelled or failed captures create no Teach answer; and confirmed voice
knowledge is immediately retrievable. The local ASR model remains explicit and
never downloads because Teach microphone capture was requested.

G09 implementation status for this branch: complete. The shared ASR service
supports Run, Live Assist, and Teach with one capture slot; Core-side capture
identity and serialized stop/finalization prevent duplicate Teach submissions;
and renderer voice controls expose only bounded text/status projections.

## Milestone 9 — Deletion, security, packaging, performance

### Build

- complete project/session/source deletion;
- cache/index purge;
- secret storage integration;
- log redaction;
- malicious import fixtures;
- renderer/preload API hardening;
- packaged Python sidecar;
- model bootstrap UX;
- clean Windows installer/uninstaller;
- crash/recovery behavior;
- benchmark harness;
- diagnostic export.

### Exit

All MVP release gates in `TEST_PLAN.md` pass on packaged Windows build.

M9 implementation status for this branch: project/session/source and
Audience/Speaker deletion paths purge SQLite, vault, retrieval mappings, and
warm model references; app reset has explicit confirmation and retains model
caches unless selected. Provider credentials use a core-owned Windows
Credential Manager seam, logs and diagnostic exports are allowlisted and
content-free, and renderer IPC never accepts a credential or diagnostic output
path. Unsafe archive names, duplicate normalized members, external links, and
bounded-name violations are rejected before extraction. A pinned PyInstaller
one-folder sidecar is required in packaged mode, the NSIS installer is
per-user and retains user data on uninstall, model preparation is explicit,
and sidecar restart/reconciliation is bounded after unexpected close.

The deterministic M9 E2E runner, deletion/security tests, privacy gate, and
metadata-only benchmark are automated. A clean-machine install and real
CPU/RTX model benchmarks remain separately labeled manual or unavailable until
their evidence is captured on the named machine and exact release SHA.

## 2. Parallelizable work

After Milestone 0, these streams can run partly in parallel if interfaces are respected:

### Desktop stream

- project UI;
- source review;
- Teach/Challenge/Run screens;
- HUD;
- shortcuts;
- privacy/status UI.

### Core ML/data stream

- parsers;
- storage/migrations;
- embeddings/retrieval;
- ASR;
- context builders;
- provider adapters.

### Quality/security stream

- synthetic fixtures;
- golden retrieval tests;
- IPC fuzz/error tests;
- privacy manifest tests;
- benchmark harness;
- import security fixtures.

## 3. Things not to build early

Do not spend P0 time on:

- mobile client;
- cloud account system;
- custom model training/fine-tuning;
- face/voice identity recognition;
- meeting bot joining Teams/Webex;
- complex vector database;
- Kubernetes/server backend;
- presentation deck generation;
- advanced analytics dashboards;
- cross-platform abstraction before Windows flow works;
- automatic question detection before push-to-assist is useful.

## 4. Architecture review triggers

Stop and record/update a decision if implementation proposes:

- replacing stdio IPC with a network service;
- storing raw audio by default;
- sending full corpus to cloud under Selected Context mode;
- adding biometric speaker identity;
- bypassing canonical evidence/provenance structures;
- letting renderer talk directly to model providers/filesystem;
- introducing a server dependency for an individual local project;
- changing from project-local Audience Models to a global dossier by default.

## 5. First external usability build

The first build given to real testers should include only:

- import;
- Teach;
- Challenge;
- Run;
- HUD push-to-assist;
- visible provenance;
- delete project;
- explicit privacy/provider status.

Hide unfinished experimental features behind developer flags rather than showing nonfunctional controls.

## 6. Product instrumentation for MVP validation

Prefer local session summaries and opt-in feedback rather than automatic telemetry.

Capture locally:

- questions generated;
- whether user retried;
- answer duration;
- whether answer was saved as preferred;
- cue latency;
- cue expanded/dismissed;
- source used;
- user rating/comment when explicitly provided.

These metrics support product validation without requiring a cloud analytics pipeline.
