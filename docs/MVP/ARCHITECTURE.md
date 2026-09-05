# MVP Architecture

## 1. Runtime shape

The MVP is a Windows desktop application with two always-on local processes. When the user selects the E10 Codex provider, Core also owns a third, short-lived official Codex App Server child process:

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

The diagram shows the always-on baseline. E10 launches `codex app-server --stdio` only for the selected ChatGPT-managed Codex provider; the Python core owns its lifecycle and communicates with it over bounded stdio. The renderer never receives general App Server RPC, filesystem, environment, or credential authority.

No localhost HTTP server is required for normal desktop operation. The Electron main process owns sidecar lifecycle and communicates through stdin/stdout. This reduces local attack surface and port conflicts.

### M6 Run pipeline

```text
Windows microphone
       |
       v
Python AudioInputAdapter -> bounded in-memory PCM queue
       |
       v
fast ingestion/VAD worker -> serialized local ASR decode worker
       |                         |                    |
       |                         |                    +--> ephemeral asr.partial
       |                         +--> bounded final queue (finals first)
       v
RunService: persist final Utterance + slide snapshot -> asr.final
       |
       +--> SlideStateService timeline / manual markers / local debrief
```

The Python core owns microphone capture. Raw PCM never enters the renderer or
NDJSON stdio transport, is not written to SQLite/files, and is discarded after
the active utterance is decoded. The Electron main process owns only the
minimum `{ project_id, session_id }` target required to route manual Run slide
shortcuts back through canonical presentation IPC.

The sounddevice adapter exposes an opaque endpoint identity rather than a raw
PortAudio enumeration index; this keeps a selected microphone from silently
changing when Windows adds or removes a Bluetooth endpoint. Run start pins the
device shown by the renderer before opening capture. The adapter opens that
selected device at its native default rate and bounded channel count, normalizes
each block to the core's 16 kHz mono PCM, and then performs only a bounded copy
and non-blocking enqueue at the service boundary. The ingestion/VAD worker never waits for a full-prefix partial
decode. The serialized decoder has one replaceable partial request and a
bounded queue for durable finals; a final request always runs before an
optional partial, and final audio is never dropped to preserve a partial
update. Input overflow or another status indicating dropped microphone data
stops acceptance and reports `ASR_BACKPRESSURE`.

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
- `sounddevice` for the Windows microphone reference input;
- `pywin32` for optional read-only PowerPoint feature detection on Windows;
- parsers behind file-type adapters;
- provider adapters behind one reasoning interface.

### Packaging

Development may use the locked `core/.venv` Python environment, but release
builds cannot assume Python is preinstalled. The Windows release uses a
reproducible PyInstaller one-folder sidecar under Electron resources and an
unsigned per-user NSIS installer. Electron launches the bundled executable
with hidden-window, `shell=false` stdio; packaged resolution never falls back
to `python.exe`. Model artifacts remain in the per-user app-data cache and are
prepared only through an explicit user action.

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

- VTT/SRT/named-TXT/structured-JSON transcript import;
- preservation of native speaker labels and timestamps;
- deterministic SourceUnit identity and transcript provenance;
- explicit mapping to project-local Audience Profiles;
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

M6 uses `Systran/faster-whisper-base.en` through a local-files-only runtime.
The approved model is prepared explicitly into the app-level `models/asr`
cache; `asr.start` never downloads. The service owns one bounded frame queue,
one fast ingestion/VAD worker, one serialized decode worker, one active
microphone capture, and deterministic stop/shutdown cleanup. Optional partial
recognition is coalesced to one pending snapshot; final requests have a
bounded lossless queue and priority over partials. Teach and Challenge do not
consume this microphone path in M6.

Run shutdown is fail-closed. It stops accepting frames and physical capture,
drains/finalizes the active segment, persists the final `Utterance`, emits
`asr.final`, terminates both workers, and only then releases audio/model
resources. The presentation watcher and session transition follow that
boundary; a failed join, unresolved final, or release failure leaves the Run
owner in retryable `stopping` state and prevents a new capture or deletion.
Normal core shutdown uses the same Run cleanup path with `aborted` status and
preserves an active session when the bounded cleanup budget cannot complete.

### SlideStateService

Priority order:

1. PowerPoint live state adapter on Windows when available;
2. manual current-slide state via UI/global shortcuts;
3. future screen inference adapter.

The application must remain functional if PowerPoint integration fails.

`RunService` composes session lifecycle, final-transcript persistence, bounded
pagination, manual markers, and the deterministic retrieval-backed debrief.
Its debrief is local and provider-free; unchanged completed state is reused by
an algorithm/timeline/transcript fingerprint.

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
- provisional, deterministic observable-pattern candidates;
- reviewed observations and exact transcript evidence links;
- stale lifecycle after attribution/source changes;
- project-local lifecycle.

Audience extraction is deliberately not a provider adapter. It reads only
currently mapped transcript SourceUnits, applies bounded deterministic rules,
and writes provisional candidates. Acceptance is the review boundary; a
source-derived observation cannot become active without transcript evidence.
`AudienceContextBuilder` returns active profiles and active, evidence-valid
observations only, with user notes explicitly labeled as user-supplied.

### RehearsalService

Owns modes:

- Teach;
- Challenge;
- Run;
- post-answer/post-run coaching.

It records mode/session events but delegates ASR, retrieval, provider reasoning, and persistence to other services.

Challenge mode is a typed-first vertical slice owned by the Python core. Its
`ChallengeService` owns the project-local session state machine, selected
AudienceProfile joins, question/evaluation history, retry and bounded
follow-up relationships, and explicit preferred-answer promotion. It composes
`AudienceContextBuilder`, `RetrievalService`, `ProviderContextBuilder`, and
`ReasoningRouter`; it does not introduce a second retrieval store, persona
builder, provider abstraction, or database. Question and evaluation provider
calls are made outside SQLite write transactions and are committed only after
core revalidates the session, reapplies the current M4 AudienceContext rules
inside the persistence connection, and validates every returned provenance ID.
Challenge evaluation preserves the complete validated typed answer; lower
priority context is dropped before the current answer can be shortened, and
an irreducible packet overflow fails closed.

The renderer receives only bounded Challenge state/history projections through
explicit IPC methods. It never reconstructs Challenge authority from button
state and never receives source excerpts outside the existing bounded,
trust-labeled provider context path. Ordinary Challenge history remains
session-owned until the user explicitly promotes an answer through the
existing KnowledgeItem and durable user-statement pipeline.

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
- ChatGPT-managed Codex App Server provider (E10).

The product UI must not contain provider-specific orchestration logic.

E09 implements `local_openai` with Core-owned Chat Completions HTTP transport.
`ReasoningProvider.leaves_machine` distinguishes loopback from private-LAN
transport without changing the local provider identity or privacy-mode enum.
The router and execution boundary enforce off-machine permission and manifests
using that property. Provider selection reuses `provider_configurations` and
its safe JSON column; no migration is needed.
See [local provider architecture](../PROVIDERS.md).

E10 implements `codex_chatgpt` through a Presenter-owned official Codex App
Server using documented ChatGPT-managed authentication. Core launches a pinned,
version-scoped runtime with a dedicated disposable `CODEX_HOME`, empty cwd and
minimal environment; it never exposes general App Server authority or auth
material to the renderer. The E10 invariant is containment rather than a
zero-tool claim: tested residual built-in `skills.list` / `skills.read`
capabilities may remain only while they cannot access user, project, credential,
environment or filesystem state outside the approved Selected Context packet
and Presenter-owned runtime. Material config/instruction/capability drift fails
closed. `ProviderExecutionService` remains the authority for privacy mode,
acknowledgement, manifests, bounded serialization, validation and cancellation.
See [Codex containment and validation](../PROVIDERS.md#e10-chatgpt-managed-codex).

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
                Explicit assist trigger
                           |
                    push-to-assist
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

M7 push-to-assist is the only live trigger. It captures an optional explicit
question or a bounded recent transcript window plus the current slide; core
does not segment audience questions automatically.

## 6. HUD architecture

Use a dedicated Electron `BrowserWindow`:

- transparent;
- frameless;
- always on top;
- top-center anchored relative to selected display;
- calibrated through bounded display, width, font-size, and top-offset settings;
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

The HUD must never block the main presentation if the core sidecar crashes. It
should fail closed to `IDLE/ERROR` and remain hideable. The collapsed window is
click-through; expanded mode is keyboard/mouse interactive. Content protection
is best-effort and its API state is visible in the HUD.

## 7. Storage

Per-user app root, for example under Windows Local AppData:

```text
PresenterCopilot/
  app.db
  models/
    asr/              # shared approved local ASR model cache
  projects/
    <project-id>/
      project.db
      sources/
      extracted/
      embeddings/
      sessions/
      diagnostics/
```

Project-local databases/files make deletion/export easier and reduce accidental cross-project retrieval. M4
adds its AudienceProfile, transcript mapping, candidate, observation, and
evidence tables to `project.db` only; there is no global Audience Model table.
The shared ASR model cache is app-level and survives project/session deletion.

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

Under Selected Context Cloud, only this bounded project-derived packet may be sent remotely. A provider may additionally receive fixed Presenter-owned policy and protocol/harness metadata required by its supported interface. For E10, any residual built-in harness capability must remain contained to Presenter-owned runtime state and must not create access to user/project state outside the approved packet.

## 10. Failure/degradation behavior

- ASR unavailable -> typed input remains usable; live voice assist disabled with clear status.
- ASR input loss, backpressure, blocked final decode, or failed worker join ->
  retain the Run owner in retryable stopping state; do not close a live model,
  mark the session terminal, or delete its project/session rows.
- PowerPoint adapter fails -> manual slide control.
- embedding model unavailable -> lexical retrieval fallback where possible.
- remote provider unavailable/quota -> retrieval-only/local path.
- sidecar crash -> main UI offers restart; HUD does not freeze over presentation.
- project corruption -> never silently overwrite; create diagnostic/recovery path.
- transcript re-index -> preserve unchanged SourceUnit IDs, reconcile native
  labels, and mark removed-evidence observations/candidates stale.
- incompatible speaker remap/unmap -> keep transcript text, mark derived rows
  stale, and never transfer them to the new profile.

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
- an agent/provider harness cannot access user, project, credential or environment state outside the approved remote context boundary; unavoidable residual capabilities must be bounded and regression-tested;
- fact-bearing cue must retain provenance IDs;
- project delete must have one authoritative cascade path.