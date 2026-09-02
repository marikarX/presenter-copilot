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
```

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
provider candidate is pending.

### ASR

```text
asr.list_devices
asr.configure
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

Voice input arrives through ASR utterances rather than a separate audio upload method.

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
```

### Run

```text
run.mark_event
run.generate_debrief
```

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
  "confidence": 0.93
}
```

Do not assume confidence is available from every ASR adapter.

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
  "classes_sent": ["application_policy", "question", "document_excerpt", "user_knowledge"],
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

## 12. Versioning

- protocol starts at integer version `1`;
- desktop and core perform compatibility handshake;
- unknown fields should be ignored where safe;
- breaking method/schema changes increment protocol version before public releases;
- one supported desktop build should ship with exactly one tested core build.
