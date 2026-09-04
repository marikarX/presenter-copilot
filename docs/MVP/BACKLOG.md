# MVP Backlog

This is the initial issue-sized engineering backlog. `P0` blocks the MVP release. `P1` is important but may move after first external usability. `P2` is explicitly post-MVP.

## Epic A — Scaffold and protocol

### P0

- [x] A01 Create Electron/React/TypeScript desktop scaffold.
- [x] A02 Create Python `presenter_core` package and test scaffold.
- [x] A03 Launch/stop Python sidecar from Electron main process.
- [x] A04 Implement protocol v1 NDJSON request/response/event envelopes.
- [x] A05 Implement `core.hello`, `core.health`, `core.shutdown`.
- [x] A06 Generate/share IPC schemas/types between Python and TypeScript or add contract fixtures.
- [x] A07 Configure formatter/linter/typecheck/test commands.
- [x] A08 Add CI for non-hardware tests.
- [x] A09 Create synthetic sample project fixture and fixture documentation.

## Epic B — Local project storage

### P0

- [x] B01 Implement `app.db` initialization/migrations.
- [x] B02 Implement project vault creation and `project.db` migrations.
- [x] B03 Implement ProjectService CRUD.
- [x] B04 Implement source snapshot hashing/path sanitization.
- [x] B05 Implement project delete cascade and filesystem cleanup.
- [x] B06 Implement session delete semantics (detaches confirmed Teach provenance before cascading session data).
- [x] B07 Add migration/version fixture tests.

## Epic C — Ingestion and provenance

### P0

- [x] C01 PDF parser preserving pages.
- [x] C02 PPTX parser preserving slides and notes where available.
- [x] C03 TXT/Markdown parser.
- [x] C04 SourceUnit/chunk pipeline.
- [x] C05 Deduplication by source hash.
- [x] C06 Source preview/list/delete/re-index IPC.
- [x] C07 Canonical `Evidence` / `ProvenanceRef` model.
- [x] C08 Import security tests: zip-slip, unsafe filename, HTML/script preview.

### P1

- [ ] C09 DOCX parser.
- [ ] C10 XLSX structured extraction.

## Epic D — Retrieval

### P0

- [x] D01 Embedding adapter interface.
- [x] D02 Initial local embedding implementation.
- [x] D03 Persist embedding matrix/vector metadata.
- [x] D04 In-process cosine similarity search.
- [x] D05 Lexical/exact-number scoring.
- [x] D06 Current/adjacent slide boosts.
- [x] D07 User-preferred answer/explanation boost for relevant confirmed KnowledgeItems.
- [x] D08 `use_live` / `use_rehearsal` retrieval filters.
- [x] D09 Conflict/ambiguity detection for exact facts.
- [x] D10 Golden retrieval benchmark/tests up to 50k chunks.

## Epic E — Provider and orchestration layer

### P0

- [x] E01 Define ReasoningProvider interface.
- [x] E02 Implement deterministic fake provider.
- [x] E03 Implement one real provider adapter using user-owned credentials.
- [x] E04 Implement structured context builder.
- [x] E05 Implement ReasoningRouter classes: NONE/RETRIEVAL/LOCAL/REMOTE.
- [x] E06 Implement provider cancellation/timeout/auth/quota errors.
- [x] E07 Implement provider health/status UI contract.
- [x] E08 Implement prompt-injection isolation: retrieved text is untrusted data.

### P1

- [ ] E09 Local OpenAI-compatible/local-model adapter.
- [ ] E10 Official Codex adapter behind feature flag if still appropriate.

## Epic F — Speaker Profile and style preservation

### P0

- [x] F01 Implement SpeakerProfile/SpeakerEvidence persistence.
- [x] F02 Speaker Profile settings/review UI.
- [x] F03 Style policy selector: Preserve / Light / Executive / Custom.
- [x] F04 Require user approval before project evidence becomes global speaker evidence.
- [x] F05 Implement preferred phrase/explanation retrieval.
- [x] F06 Implement project style override.
- [x] F07 Reset/remove profile evidence.
- [x] F08 Tests proving Preserve My Voice prefers accepted user wording.

## Epic G — Teach mode

### P0

- [x] G01 Teach session state machine.
- [x] G02 Typed Teach conversation UI.
- [x] G03 Generate one focused clarification at a time.
- [x] G04 Extract KnowledgeItem candidate from user answer.
- [x] G05 Confirm/edit/reject KnowledgeItem UI.
- [x] G06 `preferred`, `private`, `use_live`, `use_rehearsal` controls.
- [x] G07 Store user-authored provenance separately from AI suggestions.
- [x] G08 Make confirmed Teach knowledge retrievable immediately.

### P1

- [ ] G09 Voice-first Teach using ASR.

## Epic H — Transcript import and Audience Model

### P0

- [x] H01 VTT transcript adapter.
- [x] H02 SRT transcript adapter.
- [x] H03 Generic named text/structured transcript adapter.
- [x] H04 Preserve native speaker labels/timestamps.
- [x] H05 Transcript speaker mapping UI.
- [x] H06 AudienceProfile CRUD.
- [x] H07 Extract evidence-backed observable audience observations.
- [x] H08 Observation review/edit/delete UI.
- [x] H09 Prohibited sensitive-observation filter.
- [x] H10 Tests: unresolved speaker, remap, delete profile.

### P1

- [ ] H11 Import adapters tuned to common Teams transcript exports.
- [ ] H12 Import adapters tuned to common Webex transcript exports.

### P2

- [ ] H13 Audio/video import.
- [ ] H14 Diarization fallback without persistent voice identity.
- [ ] H15 Direct conferencing connectors.

H11–H15 remain deferred: M4 supports generic standards and local project
mapping only. No Teams/Webex connector, media/diarization fallback, or direct
conferencing integration is part of this milestone.

## Epic I — Challenge mode

### P0

- [x] I01 Challenge configuration UI.
- [x] I02 Select 1–3 audience profiles.
- [x] I03 Generate source-grounded audience-specific questions.
- [x] I04 Question provenance/rationale display.
- [x] I05 Typed answer submission first.
- [x] I06 Evaluation schema and display.
- [x] I07 Retry same question.
- [x] I08 Save preferred answer.
- [x] I09 Follow-up question support.
- [x] I10 Persist Question/AnswerVersion/Evidence.

## Epic J — ASR and Run mode

### P0

- [x] J01 ASR adapter interface.
- [x] J02 `faster-whisper` reference adapter.
- [x] J03 Microphone enumeration/selection.
- [x] J04 Model download/load/status UX.
- [x] J05 VAD/partial/final event flow.
- [x] J06 ASR latency benchmark harness.
- [x] J07 Run session UI and timer.
- [x] J08 Session transcript persistence.
- [x] J09 Manual slide next/previous global shortcuts.
- [x] J10 SlideStateEvent timeline.
- [x] J11 Windows PowerPoint current-slide adapter with fallback.
- [x] J12 Post-run debrief.

## Epic K — Live HUD

### P0

- [x] K01 Dedicated transparent frameless HUD BrowserWindow.
- [x] K02 Top-center display positioning and calibration.
- [x] K03 Collapsed cue renderer hard-limited to <=3 lines.
- [x] K04 Global show/hide shortcut.
- [x] K05 Global push-to-assist shortcut.
- [x] K06 Click-through collapsed mode.
- [x] K07 Electron/OS content protection and visible status.
- [x] K08 CueService with user-wording preference.
- [x] K09 `cue.partial` progressive updates.
- [x] K10 Expanded provenance view.
- [x] K11 Retrieval-only fast path.
- [x] K12 HUD survives provider/core error and remains hideable.
- [x] K13 Question-to-cue latency instrumentation.

### P1

- [ ] K14 Experimental automatic question segmentation.

## Epic L — Privacy and secret handling

### P0

- [x] L01 Implement Local Only hard routing invariant.
- [x] L02 Implement Selected Context Cloud minimum-context builder.
- [x] L03 Emit/store privacy context manifest before remote call.
- [ ] L04 Implement OS-backed provider secret storage.
- [x] L05 Prevent renderer access to raw secrets.
- [x] L06 Add local-only network isolation test.
- [x] L07 Add fake-provider payload inspection test.
- [ ] L08 Add local legal/authorization disclosure for transcript/recording inputs.
- [ ] L09 Log redaction rules/tests.
- [ ] L10 Verify deleted project is absent from caches/indexes.

## Epic M — Packaging and release readiness

### P0

- [ ] M01 Bundle Python sidecar for Windows release build.
- [ ] M02 Clean-machine installation test.
- [ ] M03 Model bootstrap/download path.
- [ ] M04 Crash/restart recovery flow.
- [ ] M05 Diagnostic export with user preview/redaction.
- [ ] M06 Release benchmark on CPU-only Windows machine.
- [ ] M07 Release benchmark on RTX reference machine when available.
- [ ] M08 Run all E2E acceptance scenarios from `TEST_PLAN.md`.
- [ ] M09 Update README with real setup/run commands after scaffold lands.
- [ ] M10 Produce first pre-1.0 release notes.

## Epic N — Post-MVP mobile companion

### P2

- [ ] N01 Define authenticated LAN companion protocol.
- [ ] N02 Phone/tablet private cue display.
- [ ] N03 Remote next/previous/hide/expand controls.
- [ ] N04 Optional haptic timing cues.
- [ ] N05 Standalone mobile rehearsal feasibility spike.

## Suggested first 10 implementation issues

If development starts now, create/work these in order:

1. A01 Desktop scaffold.
2. A02 Python core scaffold.
3. A03/A04 sidecar + protocol.
4. B01/B02 local DB/project vault.
5. C01/C02 presentation parsing.
6. C04/C07 chunk + provenance model.
7. D01–D04 basic semantic retrieval.
8. E01/E02 provider interface + fake provider.
9. G01/G02 typed Teach vertical slice.
10. K01/K03 minimal standalone HUD spike.

The HUD spike is intentionally early enough to validate Windows overlay/capture behavior before most product logic depends on it.
