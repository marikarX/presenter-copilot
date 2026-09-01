# MVP Architecture

## 1. Runtime shape

The MVP is a Windows desktop application with two local processes:

```text
+----------------------------------------------------------+
| Electron desktop process                                |
|                                                          |
| React UI   Project UI   Rehearsal UI   Live HUD          |
|    |            |            |            |              |
|    +------------+------------+------------+              |
|                         |                                |
|                    IPC client                           |
+-------------------------|--------------------------------+
                          | child-process stdio
                          | newline-delimited JSON
+-------------------------v--------------------------------+
| Python core sidecar                                      |
|                                                          |
| ingestion  ASR  retrieval  orchestration  providers      |
|     |       |       |          |             |            |
|     +-------+-------+----------+-------------+            |
|                         |                                |
|                 SQLite + local files                    |
+----------------------------------------------------------+
```

No localhost HTTP server is required for normal desktop operation. The Electron main process owns sidecar lifecycle and communicates through stdin/stdout. This reduces local attack surface and port conflicts.

## 2. Technology baseline

### Desktop

- Electron;
- React;
- TypeScript;
- a state store appropriate for small desktop applications;
- Electron main/preload/renderer isolation;
- context isolation enabled;
- no Node integration in renderer;
- global shortcuts owned by main process;
- separate transparent frameless HUD window.

### Core sidecar

- Python;
- typed data models for IPC payloads;
- SQLite for metadata/state;
- NumPy/in-process vector search for MVP corpus sizes;
- replaceable embedding adapter;
- `faster-whisper` as initial local ASR reference adapter;
- parsers behind file-type adapters;
- provider adapters behind one reasoning interface.

### Packaging

The desktop installer must bundle or bootstrap the Python core reproducibly. Development may use an external Python environment, but release builds cannot assume Python is preinstalled.

## 3. Repository layout target

```text
/
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
    schemas/          # generated/shared protocol schemas if used
  samples/
    synthetic-deck/
  docs/
    MVP/
```

The exact monorepo tooling may change during scaffold creation, but these module boundaries should remain.

## 4. Core domain services

### ProjectService

Owns:

- project creation/open/delete;
- project settings/privacy mode;
- project paths;
- source snapshot metadata;
- project lifecycle events.

### IngestionService

Owns:

- type detection;
- parsing;
- slide/page structure;
- text normalization;
- chunking;
- hashing/deduplication;
- provenance;
- embedding/index creation.

### TranscriptImportService

Owns:

- VTT/SRT/text/structured transcript import;
- preservation of native speaker labels and timestamps;
- speaker normalization;
- explicit mapping to Audience Profiles;
- no biometric identity inference.

### ASRService

Owns:

- microphone device selection;
- audio stream lifecycle;
- VAD;
- partial/final transcription;
- timestamps;
- model loading/status;
- adapter abstraction.

### SlideStateService

Priority order:

1. PowerPoint live state adapter on Windows when available;
2. manual current-slide state via UI/global shortcuts;
3. future screen inference adapter.

The application must remain functional if PowerPoint integration fails.

### RetrievalService

Inputs:

- query;
- current slide;
- requested source classes;
- audience/profile context;
- project/session scope.

Outputs ranked evidence objects with provenance. Retrieval must remain usable without an LLM.

### SpeakerProfileService

Owns:

- explicit style settings;
- accepted user phrases/explanations;
- user-approved style evidence;
- global vs project overrides;
- reset/export/delete.

No hidden personality diagnosis.

### AudienceModelService

Owns:

- audience profiles;
- attributed prior questions;
- user-entered role/concern notes;
- derived observable patterns;
- evidence links for each derived observation;
- project-local lifecycle.

### RehearsalService

Owns modes:

- Teach;
- Challenge;
- Run;
- post-answer/post-run coaching.

It records mode/session events but delegates ASR, retrieval, provider reasoning, and persistence to other services.

### CueService

Turns evidence/answer structures into HUD-sized cues.

Rules:

- default <= 3 lines;
- prefer user-authored/practiced wording;
- preserve fact provenance;
- progressive updates allowed;
- no fabricated exact number if evidence is absent.

### ReasoningRouter

Decision classes:

```text
NONE
RETRIEVAL_ONLY
LOCAL_REASONING
REMOTE_REASONING
```

Inputs include privacy mode, provider availability, confidence, latency budget, and task type.

### ProviderService

One interface; adapters may include:

- mock/deterministic provider for tests;
- user-supplied cloud API provider;
- local OpenAI-compatible endpoint / local model adapter;
- optional officially supported Codex adapter later.

The product UI must not contain provider-specific orchestration logic.

## 5. Live Assist pipeline

```text
Mic audio
  |
  v
ASR partial/final ---------------------------+
  |                                          |
  |                                  current slide
  |                                          |
  +--------------------+---------------------+
                       v
               Question/assist trigger
                /                  \
        push-to-assist          auto detect
          (required)           (experimental)
                \                  /
                 +--------+-------+
                          v
                    RetrievalService
                          |
               +----------+----------+
               |                     |
       high-confidence fact       synthesis needed
               |                     |
               v                     v
          CueService          ReasoningRouter
               |                     |
               +----------+----------+
                          v
                      HUD event
```

Push-to-assist captures the recent transcript window plus current question/selection and is the reliability fallback.

## 6. HUD architecture

Use a dedicated Electron `BrowserWindow`:

- transparent;
- frameless;
- always on top;
- top-center anchored relative to selected display;
- draggable/repositionable;
- keyboard-interactive only when expanded/configuring;
- click-through option in presentation mode;
- content protection enabled where supported;
- independent from main window lifecycle.

HUD states:

```text
HIDDEN
IDLE
LISTENING
SEARCHING
CUE_PARTIAL
CUE_READY
EXPANDED_SOURCE
ERROR
```

The HUD must never block the main presentation if the core sidecar crashes. It should fail closed to `IDLE/ERROR` and remain hideable.

## 7. Storage

Per-user app root, for example under Windows Local AppData:

```text
PresenterCopilot/
  app.db
  projects/
    <project-id>/
      project.db
      sources/
      extracted/
      embeddings/
      sessions/
      diagnostics/
```

Project-local databases/files make deletion/export easier and reduce accidental cross-project retrieval.

### Source snapshots

For reproducibility, imported presentation/supporting files are copied into the project vault by default. Large meeting recordings are not copied/persisted unless the user explicitly opts in; attributed transcript text is sufficient for the P0 audience-model workflow.

## 8. Embeddings and retrieval

MVP avoids an external vector database.

Persist:

- chunk metadata in SQLite;
- embeddings as float32 blobs or a project-local matrix file keyed by chunk ID.

At query time:

- load/index memory-mapped matrix;
- cosine similarity in process;
- apply metadata filters and boosts;
- return top evidence.

Expected P0 project scale: <= 50,000 chunks. If benchmarks fail, replace the index behind `RetrievalIndex` without changing domain services.

Ranking boosts:

1. exact lexical/number match;
2. current slide;
3. adjacent slides;
4. user-authored knowledge;
5. preferred practiced answer;
6. audience-relevant source;
7. semantic similarity.

## 9. Model/context policy

A reasoning request is assembled from structured fields rather than dumping the entire project transcript.

Minimum packet:

```text
Task
Current question
Current slide summary
Top evidence excerpts
Relevant preferred user explanation(s)
Style policy
Audience profile/observations required for this task
Output schema + cue length constraint
```

Under Selected Context Cloud, only this packet may be sent remotely.

## 10. Failure/degradation behavior

- ASR unavailable -> typed input remains usable; live voice assist disabled with clear status.
- PowerPoint adapter fails -> manual slide control.
- embedding model unavailable -> lexical retrieval fallback where possible.
- remote provider unavailable/quota -> retrieval-only/local path.
- sidecar crash -> main UI offers restart; HUD does not freeze over presentation.
- project corruption -> never silently overwrite; create diagnostic/recovery path.

## 11. Observability

Local structured metrics only by default:

- ASR partial/final latency;
- retrieval latency;
- provider latency;
- cue latency;
- model load time;
- memory/CPU/GPU utilization sampled coarsely;
- error codes.

Do not include full source text or transcript in telemetry. No remote telemetry is required for P0.

## 12. Architecture gates before merge

No implementation PR should bypass these boundaries without recording a decision:

- renderer cannot access filesystem/secrets directly;
- provider code cannot live in HUD/UI components;
- audience model cannot store biometric voiceprints;
- remote provider cannot receive raw microphone audio in Local Only or Selected Context Cloud;
- fact-bearing cue must retain provenance IDs;
- project delete must have one authoritative cascade path.
