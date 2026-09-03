# MVP Interfaces and Contracts

## 1. IPC transport

Electron main process launches the Python sidecar as a child process.

Transport:

- newline-delimited UTF-8 JSON over stdin/stdout;
- one JSON object per line;
- stderr reserved for developer/diagnostic logs;
- every request has `request_id`;
- long-running operations emit events and a final response;
- protocol version included during handshake.

Do not expose the Python core through localhost HTTP for P0.

## 2. Envelope

### Request

```json
{
  "protocol_version": 1,
  "type": "request",
  "request_id": "uuid",
  "method": "project.create",
  "params": {}
}
```

### Response

```json
{
  "protocol_version": 1,
  "type": "response",
  "request_id": "uuid",
  "ok": true,
  "result": {}
}
```

### Error response

```json
{
  "protocol_version": 1,
  "type": "response",
  "request_id": "uuid",
  "ok": false,
  "error": {
    "code": "ASR_MODEL_UNAVAILABLE",
    "message": "Human-readable summary",
    "retryable": true,
    "details": {}
  }
}
```

### Event

```json
{
  "protocol_version": 1,
  "type": "event",
  "event": "asr.partial",
  "payload": {}
}
```

## 3. Required P0 methods

### Lifecycle

```text
core.hello
core.health
core.shutdown
```

`core.hello` returns protocol version, core version, available adapters/capabilities, and migration status.

`core.shutdown` first runs the canonical cleanup for every active Run with
`status=aborted`. It returns `cleanup_pending=true` and a safe error code when
the bounded ASR cleanup cannot finish; in that case the active session remains
recoverable and no resource is closed underneath a live worker.

### Projects

```text
project.create
project.open
project.list
project.update_settings
project.acknowledge_remote_reasoning
project.delete
```

### Sources

```text
source.import
source.list
source.preview
source.delete
source.reindex
```

`source.import` accepts `kind=transcript` for `.vtt`, `.srt`, `.txt`, and
structured `.json` transcript files. VTT/SRT/JSON default to transcript kind;
ordinary `.txt` remains a supporting source unless the caller explicitly
selects `kind=transcript`. Transcript previews expose bounded cue timestamps,
native speaker labels, and `source_type=transcript` provenance. The named-text
transcript adapter uses the canonical parser ID `transcript.named-text`; native
labels are retained as imported metadata.

### Retrieval

```text
search.lexical                 # M1 compatibility path
retrieval.health
retrieval.query
retrieval.rebuild
```

`retrieval.query` requires `project_id` and a bounded `query`, and accepts
optional `limit`, `document_ids`, `source_types`, `current_slide`, and
`slide_window`, `usage`, and `allow_private` fields. Confirmed Teach
KnowledgeItems use the same Evidence contract as document chunks; candidates
are not indexable. It returns the retrieval mode, latency, semantic health
summary, generic index counts, bounded ranked hits, canonical Evidence,
ranking-trace components, and deterministic conflict metadata. Semantic failure
degrades to lexical fallback; a query never downloads or rebuilds a model/index
implicitly.

`retrieval.rebuild` explicitly creates and activates a project-local semantic
generation. It returns model identity, dimension, coverage, and reuse/embed
counts. Long-running rebuilds reuse `project.index_progress` and
`project.index_ready`; M2 progress stages include `model_load`, `scan`,
`reuse`, `embed`, `persist`, `activate`, and `complete`. These payloads contain
metadata only—no source text, vectors, or filesystem paths.

### Transcript mapping

```text
transcript.list_speakers
transcript.map_speaker
transcript.unmap_speaker
```

`transcript.list_speakers` returns bounded native-label summaries grouped by
transcript document. Every label starts unresolved. `map_speaker` and
`unmap_speaker` are explicit project-local mutations; they never infer a
person from a display name, voice, face, or other biometric signal. Mapping a
label to a different profile revalidates its exact transcript evidence and
marks incompatible derived observations/candidates stale.

### Speaker profile

```text
speaker_profile.get
speaker_profile.list_evidence
speaker_profile.approve_evidence
speaker_profile.remove_evidence
speaker_profile.update_settings
speaker_profile.reset
```

### Audience

```text
audience.create
audience.update
audience.list
audience.delete
audience.list_observations
audience.accept_observation
audience.reject_observation
audience.create_observation
audience.update_observation
audience.delete_observation
audience.build_context
```

Audience methods are project-scoped. Extraction creates provisional pending
candidates only from currently mapped transcript SourceUnits. Acceptance
requires the candidate to remain pending and every exact transcript evidence
unit to remain attributed to the same profile; user-entered safe observations
may omit evidence. Rejected fingerprints stay in the project to prevent
immediate recreation, while stale rows remain inspectable but are never active
context.

M4 audience data is bounded by `MAX_PROFILE_COUNT=100`,
`MAX_OBSERVATIONS_PER_PROFILE=100`, `MAX_CANDIDATES_PER_PROFILE=100`, and
`MAX_EVIDENCE_PER_ITEM=20` as storage caps. Extraction reads at most
`MAX_EXTRACTION_SEGMENTS=5000` mapped transcript segments per request and
returns `AUDIENCE_EXTRACTION_TOO_LARGE` when the bound is exceeded; callers
can filter by transcript document IDs. `AudienceContextBuilder` accepts at
most three profiles, eight observations per profile, and three evidence
examples per observation, with 800-character evidence and notes bounds and a
20,000-character serialized packet budget. It fails closed on prohibited
profile notes or observation text and excludes sensitive or currently
unattributed rows.

### Sessions

```text
session.start
session.stop
session.get
session.list
session.delete
```

`session.start` reads the current project `privacy_mode`; a caller-provided
`privacy_mode` is accepted only when it exactly matches the project value and
can never broaden authority. Session deletion first clears app-level
SpeakerEvidence session provenance, then detaches project UserStatement and
KnowledgeItem session provenance and deletes the project session in one
transaction. A failure in either phase is retryable and never deletes a
project session partially.

`session.stop` completes an active Teach session from `ready_for_prompt` or
`awaiting_user`. It remains blocked while a user answer or provisional
provider candidate is pending. For an active Run, the IPC handler delegates to
the Run lifecycle: ASR cleanup must succeed before the presentation watcher,
session row, or completed debrief can change. `session.delete` and
`project.delete` likewise fail closed while the selected Run still owns
unresolved capture/model resources.

### ASR

```text
asr.list_devices
asr.configure
asr.prepare_model
asr.start
asr.stop
asr.status
```

### Presentation state

```text
presentation.detect
presentation.set_slide
presentation.next_slide
presentation.previous_slide
presentation.status
```

### Teach

```text
teach.next_prompt
teach.get_state
teach.submit_text
teach.discard_answer
teach.confirm_knowledge_item
teach.reject_knowledge_item
```

M6 voice input arrives through Run ASR utterances rather than a separate audio
upload method. Teach and Challenge remain typed-first in this milestone.

Core owns the Teach state machine:

```text
ready_for_prompt -> next_prompt -> awaiting_user
awaiting_user -> submit_text -> candidate_ready
awaiting_user -> stop -> completed
candidate_ready -> confirm/reject/discard -> ready_for_prompt
candidate_ready -> stop (blocked)
```

`teach.get_state` returns only bounded active-session recovery data: the current
prompt, pending user answer, and pending provisional candidate when present.
Every Teach operation rereads the current project privacy mode, so changing a
project to `local_only` takes effect for an already-active session.

`teach.discard_answer` is allowed only for the current pending user answer when
no provider candidate is pending. It preserves the ordinary session utterance
history, creates no knowledge or evidence, and returns the session to
`ready_for_prompt`; arbitrary utterance deletion is not exposed.

### Knowledge management

```text
knowledge.list
knowledge.update_flags
knowledge.delete
```

`knowledge.update_flags` changes only the user-controlled `preferred`,
`private`, `use_live`, and `use_rehearsal` fields. Confirmed KnowledgeItems
remain immediately available to lexical retrieval; semantic synchronization is
best-effort when the local embedding model is unavailable.

### Challenge

```text
challenge.configure
challenge.next_question
challenge.submit_answer
challenge.retry_question
challenge.save_preferred_answer
challenge.get_state
challenge.list_history
```

Challenge is a typed-first, project-local rehearsal surface. Core owns the
state machine; the renderer may display `valid_next_actions` but cannot infer
authority from button state.

`challenge.configure` accepts:

```json
{
  "project_id": "uuid",
  "session_id": "uuid",
  "audience_profile_ids": ["uuid", "uuid"],
  "intensity": "normal | skeptical | adversarial",
  "allow_follow_ups": true,
  "scope": "full_deck | slide_range",
  "slide_start": 1,
  "slide_end": 8
}
```

The list contains 1–3 unique active profiles from the current project. A
slide range is required only for `slide_range`, is bounded, and must be within
the current presentation. Configuration is stored in `project.db` and cannot
change after a question has been generated.

`challenge.next_question` creates one project-grounded Question. Core chooses
the configured audience profile fairly; provider output cannot choose the
profile. An optional `follow_up_to_question_id` creates one bounded follow-up
with the same profile and `parent_question_id`. Follow-ups are rejected with
`CHALLENGE_FOLLOW_UP_DISABLED` when disabled. No autonomous provider loop is
permitted.

`challenge.submit_answer` accepts only the current Question and a non-empty
typed `text` bounded to 4,000 characters. It creates an immutable
`AnswerVersion` with `origin=user_typed`, evaluates it through the existing
ReasoningProvider contract, and transitions the session to `evaluated`.
Evaluation contains bounded correctness, directness, completeness, concision,
and style-match objects, source support, missing points, and validated
canonical evidence IDs. Scores are normalized to 0.0–1.0; style match may be
null when approved style evidence is unavailable.

For `challenge_evaluation`, the complete validated answer is sent to the
provider up to the 4,000-character answer bound. Provider packet fitting may
drop lower-priority prior questions, extra audience observations, style
examples, or extra retrieved evidence, but never shortens the current answer.
If the complete answer, trusted instructions, and minimum grounding cannot
fit the bounded request, core returns `CHALLENGE_CONTEXT_TOO_LARGE` without
creating an AnswerVersion.

`challenge.retry_question` transitions the current evaluated Question back to
`awaiting_answer` without creating another Question. The next submission
creates another AnswerVersion. `challenge.save_preferred_answer` is explicit
and idempotent: it promotes one selected user answer through the existing
durable `UserStatement` and `KnowledgeItem` path. It does not promote provider
evaluation prose.

`challenge.get_state` returns bounded recovery data: configuration, selected
audience summaries, the current Question, the latest AnswerVersion/evaluation,
reasoning availability, and valid next actions. `challenge.list_history`
accepts bounded `limit` and `offset` values and returns paginated Question,
AnswerVersion, evaluation, preference, and evidence summaries. It never
returns a raw database or unbounded session payload.

`challenge.get_state` also returns `session_status`. A stopped session remains
readable for history/recovery, but its `valid_next_actions` is empty and all
Challenge mutations are rejected as inactive.

Challenge mutations reject cross-project IDs and invalid transitions with
stable errors including `CHALLENGE_CONFIG_INVALID`,
`CHALLENGE_AUDIENCE_INVALID`, `CHALLENGE_STATE_INVALID`,
`CHALLENGE_QUESTION_NOT_FOUND`, `CHALLENGE_ANSWER_NOT_FOUND`,
`CHALLENGE_CONTEXT_INSUFFICIENT`, `CHALLENGE_CONTEXT_TOO_LARGE`,
`CHALLENGE_CONTEXT_STALE`, and `CHALLENGE_OUTPUT_INVALID`.

The `challenge.question` and `challenge.evaluation` events contain only
bounded IDs, statuses, and summaries. They contain no filesystem paths,
secrets, complete prompts, or hidden model reasoning.

### Run

```text
run.mark_event
run.generate_debrief
run.get_state
run.list_transcript
run.list_timeline
run.get_debrief
```

Run uses the ordinary `session.start`, `session.stop`, `session.get`,
`session.list`, and `session.delete` lifecycle. `session.start` with
`mode=run` is the only M6 microphone consumer; `live_assist` remains
`MODE_NOT_IMPLEMENTED`.

`asr.list_devices` returns only bounded device metadata. `asr.configure` accepts
the core-approved `adapter_id`, `model_id`, English `language`, and selected
`device_id`; it rejects changes while capture/model preparation is active.
`asr.prepare_model` is an explicit setup operation for the approved local
model. `asr.start` requires an active Run session and never downloads. A second
capture returns `ASR_ALREADY_RUNNING`; a missing model returns
`ASR_MODEL_UNAVAILABLE`. `asr.stop` is idempotent only for the matching active
Run session and performs bounded cleanup. It reports success only after the
ingestion and serialized decoder workers have terminated, any active final has
been persisted or deterministically found empty, and audio/model resources
have been released. A failed join or final remains in retryable `stopping`
state; a later stop retries the retained final without permitting another
capture. `ASR_BACKPRESSURE` reports input overflow or another capture condition
that means microphone audio was dropped.

The callback-to-decode path is bounded and lossless for finals: ingestion/VAD
does not call the ASR adapter, one optional partial request is replaceable, and
final requests have priority over partial work. Raw PCM remains internal to
the core.

`asr.status` returns `adapter_id`, `model_id`, `model_status`, safe device
metadata, `capture_state`, nullable `session_id`, `language`, configuration,
`input_signal_state`, bounded `input_frames_received`, capabilities, and a
nullable safe error code. `input_signal_state` is only `unknown`, `silent`, or
`detected`; it is a coarse capture diagnostic, not a speech/transcript result.
It never returns raw PCM, model paths, COM objects, stack traces, or secrets.

`run.list_transcript` returns final utterances only, ordered by start time and
bounded by `limit`/`offset`. `run.list_timeline` returns bounded slide events
and manual markers. `run.get_state` is a bounded recovery projection, and
`run.get_debrief` returns the persisted local debrief without regenerating it.
Run debrief retrieval uses `usage=rehearsal` and may use `allow_private=true`;
the independent `use_rehearsal` flag still excludes disabled KnowledgeItems.
For exact numeric/factual claims, only eligible `fact_safe` evidence with the
same canonical normalized value is supporting evidence. Missing support yields
`needs_evidence_review`, conflicting eligible evidence yields
`conflict_review`, and non-fact-safe or mismatched hits are retained only as
non-supporting review context; the user statement is never labeled false by
absence of support.

### Retrieval / assist

```text
assist.request
assist.cancel
cue.expand_sources
```

### Providers

```text
provider.list
provider.configure
provider.test
provider.status
```

M3's OpenAI reference adapter reads only `OPENAI_API_KEY` from the core
process environment. `provider.configure` accepts safe metadata such as
`enabled` and `model_id`; it rejects API keys, tokens, cookies, and other
secret fields. The renderer never receives or submits a provider secret.

## 4. Required P0 events

```text
core.ready
core.error
project.index_progress
project.index_ready
source.import_progress
source.import_error
asr.model_loading
asr.ready
asr.partial
asr.final
asr.device_error
presentation.slide_changed
session.started
session.stopped
teach.prompt
teach.knowledge_candidate
challenge.question
challenge.evaluation
run.debrief_progress
assist.started
assist.retrieval_ready
assist.reasoning_started
cue.partial
cue.ready
cue.error
provider.status_changed
privacy.remote_context_manifest
```

## 5. ASR event contract

### `asr.partial`

```json
{
  "session_id": "uuid",
  "utterance_id": "uuid",
  "text": "Why don't we just",
  "start_ms": 12340,
  "end_ms": 13210,
  "is_final": false
}
```

### `asr.final`

```json
{
  "session_id": "uuid",
  "utterance_id": "uuid",
  "text": "Why don't we just renew the existing platform?",
  "start_ms": 12340,
  "end_ms": 14820,
  "is_final": true,
  "slide_ordinal": 12
}
```

`confidence` may be included only when an adapter supplies a defensible value;
the M6 faster-whisper adapter leaves it absent. Partial payloads are
ephemeral. Final persistence commits the `Utterance` before `asr.final` is
emitted, and the same `utterance_id` is used for all partial/final updates.
Timestamps are monotonic and session-relative. No raw audio appears in any
event.

`asr.final` is emitted only after the durable `Utterance` commit. The
`slide_ordinal` is the start-slide snapshot, not a PowerPoint custom-show
position. The read-only PowerPoint facade obtains it from
`SlideShowWindow.View.Slide.SlideIndex` and uses `SlideShowWindow.Presentation`
for basename and slide-count matching; unavailable or mismatched COM state
falls back to manual tracking.

## 6. Evidence contract

All retrieval/provider/cue paths use one canonical evidence shape:

```json
{
  "evidence_id": "uuid-or-derived-id",
  "source_type": "document",
  "source_id": "uuid",
  "source_unit_id": "uuid",
  "label": "CostModel.pdf p.4",
  "text": "Relevant excerpt",
  "rank": 1,
  "score": 0.91,
  "fact_safe": true
}
```

`fact_safe=false` for AI inference or unverified generated content.

Transcript evidence uses `source_type=transcript`, `source_id` equal to the
transcript Document ID, and `source_unit_id` equal to the exact timestamped
transcript segment. The canonical label includes the native speaker label and
bounded cue time when present.

## 7. Assist request

```json
{
  "project_id": "uuid",
  "session_id": "uuid",
  "trigger": "push_to_assist",
  "question_text": "Why not wait a year?",
  "recent_transcript": "...",
  "current_slide": 12,
  "style_policy": "preserve_voice",
  "privacy_mode": "selected_context_cloud",
  "max_lines": 3
}
```

The sidecar owns routing. Renderer must not decide to call a cloud provider directly.

## 8. Cue contract

```json
{
  "cue_id": "uuid",
  "state": "final",
  "lines": [
    "3-year TCO ↓ 18%",
    "Waiting preserves region SPOF",
    "Mention June outage"
  ],
  "evidence": [
    {"evidence_id": "...", "label": "CostModel.pdf p.4"},
    {"evidence_id": "...", "label": "Your Teach explanation"}
  ],
  "confidence": "high",
  "contains_ai_inference": false
}
```

Hard UI constraint: P0 HUD renderer accepts at most 3 cue lines in collapsed mode.

## 9. Reasoning provider interface

Conceptual Python interface:

```text
ReasoningProvider
- id: str
- capabilities() -> ProviderCapabilities
- health() -> ProviderHealth
- generate(request: ReasoningRequest) -> ReasoningResult
- close()
```

`ReasoningRequest` contains structured context fields:

```text
task_type
task_instruction (core-owned trusted Challenge contract)
question
user_input
current_slide_summary
evidence[]
preferred_user_explanations[]
approved_speaker_style_evidence[]
conflict_metadata[]
style_policy
privacy_mode
output_schema
latency_budget_ms
```

Provider adapters must not query project storage directly. Context assembly happens before provider invocation so privacy behavior is testable.

For `challenge_question`, `challenge_follow_up`, and `challenge_evaluation`,
core supplies a bounded trusted task instruction. The OpenAI adapter places
the application policy and task instruction in trusted system/application
content, structurally separate from user content containing untrusted project
evidence, audience text, transcript excerpts, and prior answers. The task
instruction is included in request-size budgeting but its body is never
persisted in a ProviderRun manifest. Providers receive no tools and do not
receive a request to reveal chain-of-thought.

M3 implements the `NONE`, `RETRIEVAL_ONLY`, `LOCAL_REASONING`, and
`REMOTE_REASONING` route vocabulary for Teach. The deterministic fake provider
is injectable for tests; the OpenAI adapter is remote-only and uses the official
Responses API with strict task-specific JSON schemas, no tools, `store=false`,
and a bounded timeout. Full cancellation/resilience remains deferred.

## 10. Retrieval interface

```text
RetrievalIndex
- index(items)
- delete(entity_ids)
- query(query_text, filters, limit) -> Evidence[]
- rebuild()
- health()
```

Filters include:

```text
project_id
source_types
current_slide
slide_window
speaker/audience profile
allow_user_private_notes
allow_live_use_only
```

M3 adds `usage = all | rehearsal | live`; the usage filter applies only to
KnowledgeItems, never document chunks. `allow_private=false` excludes private
KnowledgeItems from a provider-context retrieval request.

## 11. Privacy manifest

Before every remote call, core emits/stores a manifest:

```json
{
  "provider_id": "...",
  "task_type": "teach_candidate",
  "privacy_mode": "selected_context_cloud",
  "classes_sent": ["application_policy", "task_instruction", "question", "document_excerpt", "user_knowledge"],
  "source_ids": ["..."],
  "knowledge_item_ids": ["..."],
  "speaker_evidence_ids": [],
  "raw_audio_sent": false,
  "full_document_sent": false,
  "full_corpus_sent": false,
  "private_items_sent": false
}
```

For M3, the manifest is persisted in `ProviderRun` before the remote request
and emitted as `privacy.remote_context_manifest` before invocation. It contains
metadata and IDs only, not the prompt, source excerpts, response, or secrets.
`full_context_cloud` still uses the same conservative selected-context packet
in M3; full-corpus upload is deferred.

M4 audience observation extraction does not invoke the reasoning router or
any provider under any project privacy mode. Transcript text stays local;
only a future, separately authorized M5 reasoning request may consume the
reviewed AudienceContext.

## 12. Versioning

- protocol starts at integer version `1`;
- desktop and core perform compatibility handshake;
- unknown fields should be ignored where safe;
- breaking method/schema changes increment protocol version before public releases;
- one supported desktop build should ship with exactly one tested core build.
