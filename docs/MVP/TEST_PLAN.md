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
- D07 User-preferred answer/explanation boost is deferred until
  KnowledgeItem/practiced-answer entities arrive;
- D08 `use_live` filter is deferred until the later live-context entities
  arrive;
- conflicting facts are detectable;
- repeated rebuilds retain one generation, one mapping set, and one matrix;
- failed activation preserves the prior generation and removes the orphan
  matrix;
- source deletion removes vectors by captured Chunk IDs and project deletion
  removes project embedding files without touching the shared model cache;
- malformed/mismatched matrix state degrades to lexical retrieval without an
  implicit model download.

### Speaker Profile

- only user-approved evidence becomes global SpeakerEvidence;
- rejected phrases do not affect prompt context;
- project override wins over global default;
- reset removes learned evidence.

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
- Selected Context Cloud excludes raw audio/full corpus;
- Full Context Cloud requires explicit project setting;
- context manifest matches actual provider payload entity IDs/classes.

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
- streaming partials where supported;
- cancellation;
- timeout;
- authentication failure;
- quota/rate-limit failure;
- malformed model output;
- no direct project storage access;
- privacy manifest generated before invocation.

A deterministic fake provider is required for CI.

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

### E2E-03 Teach

Start Teach -> submit user explanation -> confirm extracted KnowledgeItem -> mark preferred/use-live -> verify persisted and retrievable.

### E2E-04 Challenge

Select two audience profiles -> generate grounded question -> answer -> evaluation -> retry -> save preferred answer -> verify preferred answer retrieval.

### E2E-05 Run

Start Run -> feed ASR fixture -> change slides -> stop -> generate debrief -> verify timeline and weak-point outputs.

### E2E-06 Live Assist

Start Live Assist -> push-to-assist known question -> retrieve fact -> HUD receives <=3-line cue -> expand provenance -> clear/hide cue.

### E2E-07 Restart/recovery

Close app after completed sessions -> reopen -> project/session state intact.

### E2E-08 Delete project

Delete project -> project directory removed -> recent list removed -> no retrieval/index residue -> promoted SpeakerEvidence handled according to delete rule.

## 9. Privacy/network tests

### Network isolation test

Run app in Local Only with outbound networking blocked/monitored.

Expected:

- all core acceptance flows supported by configured local/mock adapters;
- no content-processing network attempt;
- test fails on unexpected socket/connect call from core path.

### Selected Context Cloud inspection

Use fake provider capturing payload.

Assert payload does not contain:

- raw audio bytes;
- full document contents;
- unrelated transcript history;
- secrets.

Assert context manifest precisely identifies sent source IDs/classes.

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

M2 also provides a separate local retrieval benchmark:

```text
pnpm model:prepare:embeddings
pnpm benchmark:retrieval
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

A pre-1.0 MVP release requires:

- all P0 unit/integration tests passing;
- E2E-01 through E2E-08 passing on Windows;
- Local Only network isolation passing;
- project deletion test passing;
- no open critical security issue;
- no known cue path that fabricates unsupported exact numeric facts;
- documented benchmark result for reference hardware;
- one clean-install smoke test of packaged application.
