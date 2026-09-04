# MVP Test Plan

## 1. Test strategy

The MVP needs four classes of tests:

1. unit tests for deterministic domain logic;
2. integration tests across desktop/core/storage/provider boundaries;
3. end-to-end tests for user flows;
4. performance/privacy tests on Windows.

Tests use only synthetic or explicitly distributable data.

## 2. Required synthetic fixture

Create one canonical sample project under `samples/synthetic-deck/` containing:

- 20–25 slide PPTX or PDF;
- two supporting documents;
- exact numeric facts intentionally repeated/conflicted in controlled places;
- one named meeting transcript with at least three speakers;
- one unresolved/room speaker label;
- expected audience mappings;
- expected questions;
- expected retrieval targets;
- malicious prompt-injection text in one source for security testing.

The fixture should include at least these facts:

- current solution 3-year cost;
- proposed solution 3-year cost;
- an RTO number;
- an explicit rejected option and rationale;
- one fact that changes between sources so conflict handling can be tested.

## 3. Unit tests

### Parsing/chunking

- PDF page boundaries retained;
- PPTX slide boundaries retained;
- transcript timestamps retained;
- speaker labels retained;
- unsafe filenames normalized;
- duplicate import detected by hash;
- chunks preserve source-unit provenance.

### Retrieval

- exact number query returns correct source;
- deterministic semantic paraphrase ranking and hybrid lexical/semantic fusion;
- exact-number precedence, stable tie-breaking, and source/document filters;
- current-slide boost works;
- adjacent-slide boost is smaller and never applies to supporting PDF pages;
- persisted generation reloads after restart and unchanged chunks reuse vectors;
- D07 User-preferred answer/explanation boost applies only to relevant,
  confirmed KnowledgeItems and exposes `user_knowledge`/
  `preferred_user_explanation` trace reasons;
- D08 `usage = all | rehearsal | live` filters KnowledgeItems without
  excluding document evidence;
- D08 covers rehearsal-disabled public items, private items, rehearsal-enabled
  items, and the `allow_private` boundary while documents remain eligible;
- confirmed KnowledgeItems share the generic embedding generation with document
  chunks; candidates and rejected items are never indexable;
- conflicting facts are detectable;
- repeated rebuilds retain one generation, one mapping set, and one matrix;
- failed activation preserves the prior generation and removes the orphan
  matrix;
- source deletion removes vectors by captured Chunk IDs and project deletion
  removes project embedding files without touching the shared model cache;
- malformed/mismatched matrix state degrades to lexical retrieval without an
  implicit model download.
- an unfiltered semantic query with complete current mappings searches the
  compact matrix without an eligibility join/materialized row mask;
- an orphaned/deleted mapped entity disables that fast path and cannot appear
  in returned evidence;
- mapping-count cache invalidation remains truthful when an indexed
  KnowledgeItem is deleted, rebuild fails, and a replacement KnowledgeItem
  returns the current entity count to its original value;
- lexical retrieval processes document and knowledge candidates in bounded
  batches rather than materializing an unbounded record list.

### Speaker Profile

- only user-approved evidence becomes global SpeakerEvidence;
- Teach candidates and provider output never become SpeakerEvidence
  automatically;
- rejected phrases do not affect prompt context;
- project override wins over global default;
- reset removes learned evidence;
- deleting a project removes its origin-linked global evidence, while unrelated
  evidence survives.

### Audience Model

- imported native labels map to correct profile;
- remapping updates observations/query context;
- observation requires evidence unless user-entered;
- prohibited sensitive categories are rejected;
- deleting profile removes mappings/observations safely.

### Cue composer

- collapsed cue max 3 lines;
- exact fact cue requires fact-safe evidence;
- `Preserve my voice` prefers practiced/user wording;
- inference marker retained;
- low-confidence conflict produces warning instead of false certainty.

### Privacy router

- Local Only cannot select remote provider;
- a local-only Teach submission cannot invoke a remote provider;
- Selected Context Cloud excludes raw audio/full corpus;
- private KnowledgeItems are excluded from remote context;
- remote reasoning requires a project acknowledgement;
- Full Context Cloud requires explicit project setting;
- context manifest matches actual provider payload entity IDs/classes;
- project `privacy_mode` remains authoritative when a session attempts an
  override or the project changes mode while the session is active.

### Teach state and deletion recovery

- core rejects submit/confirm/reject actions outside the authoritative state
  transitions with stable `TEACH_STATE_INVALID`, `TEACH_ANSWER_PENDING`, and
  `TEACH_SOURCE_INVALID` errors;
- a direct local answer can be explicitly discarded without creating a
  UserStatement, KnowledgeItem, KnowledgeEvidence, SpeakerEvidence, or vector
  mapping, and the next prompt remains available;
- an unanswered `awaiting_user` prompt can end normally, while a pending answer
  or provider candidate still blocks session stop;
- `teach.get_state` restores bounded prompt, pending-answer, and candidate
  state after a core/app restart, including direct-save pending answers;
- app-cleanup failure and project-delete failure each leave a retryable session
  state with no partial project detachment.

## 4. IPC contract tests

- handshake succeeds at compatible protocol version;
- incompatible protocol fails clearly;
- malformed JSON does not crash core;
- unknown method rejected;
- request/response correlation works under concurrent requests;
- event stream does not block responses;
- large source-import progress events remain bounded;
- sidecar restart restores openable project state.

## 5. Provider contract tests

Every provider adapter runs the same suite:

- health/status;
- successful structured answer;
- bounded structured Teach question/candidate output;
- bounded timeout;
- authentication failure;
- quota/rate-limit failure;
- malformed model output;
- no direct project storage access;
- privacy manifest generated before invocation.

The OpenAI adapter also maps nested `insufficient_quota`/quota codes before a
generic HTTP 429, keeps `output_schema` out of the serialized user payload,
and sends the strict schema only through the adapter request fields.

A deterministic fake provider is required for CI. M8 adds the shared
core-owned execution boundary used by Teach, Challenge, and Live Assist. Its
contract tests cover final privacy re-read, payload/manifest parity, provider
run lifecycle, bounded timeout, logical cancellation, safe health transitions,
task-specific failure mapping, and the explicit per-task context-class
allowlist across all six remote task families. The selected-context integration
test inspects both captured provider payloads and metadata manifests; a
disallowed class must fail before provider invocation or `ProviderRun` creation.
Provider calls must occur outside SQLite transactions; late output after
timeout or cancellation is discarded.

The OpenAI adapter test also verifies that health plus requests with different
latency budgets reuse one SDK client, while each `responses.create` call gets
its own bounded timeout, and that provider shutdown closes the cached client.

## 6. ASR tests

Use recorded synthetic speech fixtures, not a live microphone in CI.

Validate:

- partial/final event order;
- timestamp monotonicity;
- end-of-utterance behavior;
- technical/numeric phrase fixture;
- device/model failure states;
- adapter can be disabled and typed flows still work.

Manual Windows hardware test additionally validates microphone device switching and latency.

## 7. PowerPoint/manual slide state

- PowerPoint adapter detects active slide when supported;
- adapter failure falls back without session failure;
- manual next/previous works globally;
- slide changes attach to transcript timeline;
- current-slide retrieval boost uses latest state.

## 8. End-to-end tests

### E2E-01 Project creation/import

Create project -> import sample deck/docs -> index ready -> inspect source provenance.

### E2E-02 Transcript audience setup

Import named transcript -> map two speakers -> leave one unresolved -> generate evidence-backed audience observations.

M4 acceptance expands this scenario across the four transcript adapters:
VTT, SRT, named TXT with `kind=transcript`, and structured JSON. Assert that
ordinary TXT without that kind remains a supporting source. Preview and
retrieval must retain exact cue timestamps, native labels, transcript
provenance, deterministic unchanged-reindex IDs, and existing M2/M3 behavior.
Audience extraction must be local/deterministic, create only provisional
candidates, and attach exact transcript SourceUnit evidence before acceptance.

The M4 lifecycle suite also asserts: unresolved labels are excluded from
profile context; candidate edits are reviewable; rejected fingerprints are
not immediately regenerated; safe user observations may omit evidence;
remap/unmap and removed re-index evidence stale derived rows without transfer;
profile deletion unresolves speakers without deleting transcript content;
transcript deletion removes mappings/evidence while preserving user-entered
observations; and project deletion removes all project-local M4 rows/files.

### E2E-03 Teach

Start typed Teach -> receive one focused question or retrieval-only fallback ->
submit a user explanation -> inspect the separate provisional candidate -> edit
and confirm it -> mark preferred/use-live -> verify persisted, immediately
retrievable, and still present after session deletion.

M3 adds the disposable-project acceptance path for direct answers: explicitly
discard one answer and verify no project knowledge is created, submit another
answer and confirm it, set `use_live=false`, query `usage=live`, and verify the
item is excluded. Promote only the confirmed item to Speaker Profile through
the separate explicit approval action.

### E2E-04 Challenge

Use the canonical synthetic project, deck, supporting documents, and
`PriorMeeting.vtt`. Index the project, map Jane Smith and Robert Chen to two
project-local AudienceProfiles, and create/accept safe observations for both.
Start a Challenge session with both profiles, a non-default intensity, and
follow-ups enabled. Generate a grounded Jane question, inspect its rationale
and canonical sources, submit a weak typed answer, retry the same Question,
submit a stronger typed answer, and verify two immutable AnswerVersions under
one Question. Explicitly save the stronger version and verify it is returned
by normal `usage=rehearsal` retrieval as user/practiced evidence. Generate the
next root question and verify Robert context is used. Restart core/app,
reopen the active session, and verify Question, AnswerVersion, evaluation,
preference, and evidence state is recovered without provider regeneration.
Also run disposable-session deletion and disposable-project cleanup checks.

The canonical flow must keep the unresolved `Conference Room` transcript
label out of AudienceContext, preserve the fixture's prompt-injection text as
untrusted evidence, keep private KnowledgeItems out of remote packets, and
keep source/profile deletion references truthful.

### M5 Challenge regression matrix

The deterministic core suite covers at minimum:

- v4 -> v5, new v5, no-op v5, and future-version-without-mutation migration;
- 1–3 unique active project-local profiles, invalid ranges, profile deletion,
  and stable cross-project/state errors;
- round-robin audience selection, role/observation-specific questions,
  accepted active evidence only, slide-range filtering, prior-question
  de-duplication, intensity framing, and insufficient-context failure;
- strict question/evaluation output bounds, provider-invented evidence
  rejection, conflict status, unavailable style score, and bounded feedback;
- complete answers longer than the document-excerpt bound reach evaluation
  intact, local word-count/speaking-time metrics use the persisted answer,
  and irreducible provider-context overflow returns
  `CHALLENGE_CONTEXT_TOO_LARGE` without an AnswerVersion;
- in-flight AudienceObservation remap/unmap stales the context before
  question persistence, and historical observation references report
  `available=false` without rewriting the old Question;
- KnowledgeItem text and preferred flags remain authoritative over
  UserStatement provenance text, including divergence and explicit
  re-promotion after a preferred flag is cleared;
- trusted task instructions are present for question, follow-up, and
  evaluation requests in structurally separate provider system content, and
  contradictory source-support statuses/evidence IDs are rejected;
- typed answer persistence, one-Question retry history, bounded follow-up
  parentage, and restart recovery without regeneration;
- explicit/idempotent preferred-answer promotion, replacement without duplicate
  active knowledge, immediate lexical retrieval, best-effort semantic sync,
  durable user-authored provenance after session deletion, and knowledge/index
  deletion cleanup;
- Local Only no-remote-call behavior, current privacy reread, selected-context
  manifests, absence of full corpus/raw transcript/private content, inert
  prompt injection, stopped-session read-only recovery actions, and
  renderer-safe serializable errors.

### E2E-05 Run

Create a disposable project, import the synthetic deck/supporting documents,
build or reuse the local retrieval index, start `mode=run`, configure the
deterministic local ASR adapter, feed bounded synthetic PCM, and verify the
partial/final sequence. Move through slides 1 -> 2 -> 3, mark a weak point and
a question, stop through the canonical session lifecycle, and verify final
transcript rows, utterance slide snapshots, slide timeline, markers, and the
deterministic debrief. Restart the core and verify transcript/timeline/debrief
recovery without regeneration, then delete the disposable session/project and
verify no Run rows remain while the shared ASR cache survives.

### M6 Local ASR and Run regression matrix

The deterministic suite covers:

- Python-core microphone ownership with bounded 16 kHz mono frames and no raw
  audio table/event payload;
- device enumeration/invalid-device handling, single-capture ownership,
  busy configuration, model-missing/no-implicit-prepare, and shutdown release;
- energy VAD start confirmation, silence finalization, forced max-duration
  finalization, monotonic timestamps, same-utterance partial/final IDs,
  ephemeral partials, and final persistence before `asr.final`;
- fail-closed final/worker shutdown using synchronization primitives: live
  ownership, non-terminal session, rejected capture/deletion, and a successful
  retry only after release;
- slow optional partial decoding while ingestion continues, one-slot partial
  coalescing, final priority/losslessness, bounded audio queue behavior, and
  `ASR_BACKPRESSURE` on dropped-input status;
- v5 -> v6 populated M0-M5 preservation, new v6, no-op, and
  future-version-without-mutation migrations;
- manual slide state/bounds, duplicate suppression, PowerPoint filename and
  slide-count matching, absent/mismatched/invalid/failing fallback, and
  persistence before `presentation.slide_changed`, including the real COM
  `SlideShowWindow.View.Slide.SlideIndex` contract;
- bounded transcript/timeline reads, marker limits, debrief retrieval/conflict
  review, exact fact-safe numeric support/review/conflict classification,
  `use_rehearsal` filtering, deterministic question recommendations, debrief
  idempotency, restart recovery, session/project cascade deletion, and no
  automatic KnowledgeItem creation;
- serialized asynchronous NDJSON writes so one event/response remains one
  complete line;
- renderer/main/preload allowlists, typed Run projections, and global shortcut
  routing through presentation IPC.

Real local ASR is separate from normal CI and uses only the checked-in
synthetic fixture after explicit `pnpm model:prepare:asr`:

```text
pnpm model:prepare:asr
pnpm test:asr-real
pnpm benchmark:asr
```

The real acceptance reports model identity, local execution, bounded phrase
matching, and unavailable status without fabricating success when the model or
hardware is unavailable. A separate Windows physical-microphone acceptance
must observe live spoken text through `sounddevice`, VAD, faster-whisper,
`asr.partial`, `asr.final`, durable Utterance persistence, slide association,
Run stop/debrief, restart recovery, and handle/process cleanup; opening a
device without observed spoken text is only a partial smoke result. The
benchmark stores metadata/timings only and does not store transcript text.

### E2E-06 Live Assist

Start Live Assist -> push-to-assist known question -> retrieve fact -> HUD receives <=3-line cue -> expand provenance -> clear/hide cue.

M7 deterministic coverage also verifies:

- v6 -> v7 migration preserves prior rows and creates only `cues`/
  `cue_evidence`, while `app.db` remains at version 2;
- Live Assist reuses the local ASR owner, stores final audience speech as
  `unknown_audience`, exposes only an ephemeral latest partial, and performs
  no automatic question segmentation;
- explicit typed/button/hotkey triggers, six-utterance/15-second/1,200-character
  bounds, current-slide retrieval, empty-context rejection, and one-assist/one-cue
  partial-to-final updates;
- retrieval-only exact fact/source-pointer cues, <=3-line bounds, fact-safe
  evidence, conflict warnings, preferred user wording, deletion availability,
  session/project cascade deletion, and restart recovery;
- provider evidence-ID containment, unsupported exact-fact rejection, local-only
  provider bypass, remote private-knowledge exclusion, logical cancellation,
  stale-result suppression, and degraded retrieval fallback;
- isolated HUD sender validation, geometry, shortcut arbitration/rollback,
  click-through/expanded state seams, and renderer-safe cue text handling.

### E2E-07 Restart/recovery

Close app after completed sessions -> reopen -> project/session state intact.

### E2E-08 Delete project

Delete project -> project directory removed -> recent list removed -> no retrieval/index residue -> promoted SpeakerEvidence handled according to delete rule.

## 9. Privacy/network tests

### Network isolation test

Run app in Local Only with outbound networking blocked/monitored.

The M8 automated scope covers Teach, Challenge, and Live Assist. Expected:

- a Local Only project never calls a remote provider, even when a remote
  provider is configured;
- no content-processing network attempt, including socket/connect/sendto;
- selected-context remote payloads contain only operation-specific bounded
  metadata and non-private evidence;
- test fails on an unexpected low-level network call from the core path;
- cancellation/supersession does not emit a stale Live cue or leave a started
  ProviderRun unfinished.

M6 adds the already-prepared-model Run path: `asr.start`, local transcription,
and deterministic debrief must make no download, provider, or content-network
call. Raw PCM must not reach retrieval, renderer, logs, SQLite, or any provider;
the explicit model-prepare command is tested separately as setup.

### Selected Context Cloud inspection

Use fake provider capturing payload.

Assert payload does not contain:

- raw audio bytes;
- full document contents;
- unrelated transcript history;
- secrets.

Assert context manifest precisely identifies sent source IDs/classes.

M3's real-provider acceptance is separate and opt-in. It uses only synthetic
content, `OPENAI_API_KEY`, the official OpenAI Responses adapter, `store=false`,
no tools, and a disposable project; no provider credential is required by
normal CI. M8 additionally verifies that the provider sees the same
metadata-only manifest that core persisted and emitted before invocation.

## 10. Security tests

- zip-slip/path traversal import fixture;
- oversized archive expansion limit;
- HTML/script content sanitized in previews;
- source prompt injection cannot change privacy/tool policy;
- renderer cannot invoke raw filesystem APIs;
- secret values never appear in logs;
- project delete clears caches;
- malformed provider output cannot inject executable HTML into HUD.

## 11. Performance benchmarks

M2/M3 provide separate local retrieval and optional provider acceptance checks:

```text
pnpm model:prepare:embeddings
pnpm benchmark:retrieval
pnpm test:provider-real
```

It uses the actual pinned model dimension with 50,000 seeded float32 vectors,
measures cold model load separately from warm query embedding, matrix cosine
search, and total metadata/rerank retrieval, and records p50/p95/max metadata
without source text or queries. The reference target is warm retrieval p95 <=
250 ms; hosted CI must not treat that manual hardware target as a brittle SLA.

Run on at least:

- CPU-only modern Windows laptop;
- NVIDIA RTX reference machine when available.

Measure separately:

```text
ASR first partial
ASR finalization
retrieval
question segmentation
provider first token/partial
cue composition
end-question -> first cue
end-question -> final cue
HUD render event -> visible
idle RAM
active RAM
CPU/GPU utilization
```

Store benchmark result JSON with build/version/hardware metadata; do not store source transcript content.

The M3 provider path records bounded ProviderRun latency and optional token
counts. M8 applies the request latency budget to every provider invocation and
keeps Live Assist within its bounded cue target. Record provider health state,
stable error code, retry guidance, cancellation outcome, and whether the
retrieval-only fallback was used; never store prompt text or raw provider
errors in benchmark artifacts.

## 12. UX/manual acceptance

Before declaring MVP complete, test with at least five real presenters/decks under explicit permission.

For each session record qualitative answers:

- Did Challenge ask anything non-obvious/useful?
- Did Preserve My Voice feel recognizably closer to the presenter than generic AI wording?
- Did the user trust the shown provenance?
- Was the HUD fast enough to help?
- Did the user visibly read or could they continue speaking naturally?
- What did they want to hide/disable?

## 13. Release gate

### M4 milestone gate

Before opening the M4 review PR, verify the M3 typed Teach/Speaker Profile
flow remains intact, the v3 -> v4 migration preserves existing rows, all four
transcript adapters and ordinary TXT behavior, explicit mapping/remap/stale
semantics, candidate review and sensitive-category rejection, restart and
delete behavior, renderer disclosure/IPC boundaries, `pnpm check`,
`pnpm build`, the real-model acceptance and 50k benchmark (or record their
unavailable status without fabricating results), hosted CI, and trusted Local
CI on the same final SHA. Do not require a provider key for M4.

### M5 milestone gate

Before opening the M5 review PR, verify the v4 -> v5 migration preserves all
M0–M4 project/source/retrieval/Teach/Speaker Profile/transcript/Audience Model
state; E2E-04 and the M5 Challenge regression matrix pass; Challenge config,
questions, evidence, typed answer versions, evaluations, retry/follow-up,
preferred promotion, deletion, and restart semantics are verified; Local Only
and selected-context privacy tests pass; renderer/main/preload allowlists and
serializable error envelopes remain intact; `pnpm setup`, `pnpm check`,
`pnpm build`, the real embedding acceptance, and the 50k retrieval benchmark
are run or their unavailable status is recorded precisely; real provider
acceptance is run only with `OPENAI_API_KEY`; Windows Electron smoke, hosted
CI, and trusted Local CI pass on the same final SHA. Do not require a provider
key for deterministic M5 CI. Do not start Run, ASR, HUD, or any M6 work as
part of this gate.

### M6 milestone gate

Before opening the M6 review PR, verify the v5 -> v6 migration preserves all
M0-M5 rows; the E2E-05 deterministic Run flow and M6 regression matrix pass;
Python core owns microphone capture; ingestion never blocks on optional
partials; final requests are lossless and have priority; shutdown is
fail-closed and final-before-event durability holds; model preparation is
explicit and `asr.start` is local-files-only; manual slide state, global
shortcuts, PowerPoint fallback, restart/deletion, bounded rehearsal debrief,
numeric fact safety, renderer boundaries, and Local Only audio isolation remain
intact. Run `pnpm setup`, `pnpm check`, `pnpm build`, the real embedding
acceptance, retrieval benchmark, explicit ASR prepare/acceptance/benchmark,
and exact-head hosted Windows plus Trusted Local CI; record any unavailable
hardware/model/PowerPoint or unobserved physical-speech result precisely. Do
not merge and do not start M7.

### M7 milestone gate

Before opening the M7 review PR, verify the v6 -> v7 migration preserves all
M0-M6 rows; the deterministic Live Assist/E2E-06 path produces a bounded
source-grounded cue and expands/deletes provenance correctly; Live ASR uses the
M6 local capture and shuts down/deletes fail-closed; retrieval-only fast path,
provider routing/privacy, logical supersession, degraded fallback, HUD sender
isolation, shortcut rollback, calibration, click-through behavior, and visible
capture-protection status remain intact. Run `pnpm setup`, `pnpm check`,
`pnpm build`, `pnpm test:embedding-real`, `pnpm benchmark:retrieval`,
`pnpm test:asr-real`, `pnpm benchmark:cue`, and `git diff --check`; record
unavailable model, hardware, compositor, physical-microphone, external-capture,
and CI evidence precisely. Require hosted Windows and Trusted Local CI on the
same exact final SHA. Do not merge and do not start M8. K14, E06, L01-L10, and
all M8 work remain deferred.

### M8 milestone gate

Before opening the M8 review PR, verify the existing M0-M7 migrations and
acceptance flows remain intact; the shared execution service is the only
Teach/Challenge/Live provider boundary; Local Only has a final remote guard
and a low-level socket interception test; Selected Context Cloud and Full
Context Cloud preserve operation-specific, private-free payloads; manifests
are derived from the actual payload, persisted and emitted before invocation,
and exposed only through bounded sanitized history; ProviderRun rows finalize
exactly once; timeout, cancellation, supersession, auth, quota, rate-limit,
unavailable, and malformed-output mappings are covered; and Live retrieval-only,
Teach direct-save, and Challenge stable-unavailable fallbacks are verified.
Run `pnpm setup`, `pnpm check`, `pnpm build`, `pnpm test:privacy-network`,
`pnpm test:embedding-real`, `pnpm benchmark:retrieval`, `pnpm benchmark:cue`,
and `git diff --check`; record unavailable model, hardware, external-provider,
physical-capture, and CI evidence precisely. Require hosted Windows and
Trusted Local CI on the same exact final SHA. Do not merge and do not start
M9.

### M9 milestone gate

Before opening the M9 review PR, verify all M0-M8 migrations and acceptance
flows remain intact; deletion removes project/session/source data from SQLite,
vaults, retrieval mappings, and warm caches; app reset requires explicit
confirmation and has a documented model-cache retention choice; credentials,
logs, diagnostics, renderer IPC, preload exposure, archive extraction, and
packaged sidecar resolution satisfy the M9 security boundary; model downloads
are explicit; unexpected sidecar close reconciles ProviderRun and active
Run/Live state; and the installer is per-user with user-data retention on
uninstall. Run `pnpm setup`, `pnpm check`, `pnpm test:privacy-network`,
`pnpm test:m9`, `pnpm test:e2e:release`, `pnpm benchmark:release`,
`pnpm package:win`, `pnpm test:packaged`, `pnpm test:install-smoke`, and
`git diff --check`. Require hosted Windows and trusted Local CI on the same
exact final SHA. Record clean-machine, real-model, hardware, and external
screen-capture evidence precisely; do not convert a deterministic fake or a
metadata-only benchmark into real ASR/provider/hardware evidence. Do not
merge and do not start post-MVP work.

A pre-1.0 MVP release requires:

- all P0 unit/integration tests passing;
- E2E-01 through E2E-08 passing on Windows;
- Local Only network isolation passing;
- project deletion test passing;
- no open critical security issue;
- no known cue path that fabricates unsupported exact numeric facts;
- documented benchmark result for reference hardware;
- one clean-install smoke test of packaged application.
