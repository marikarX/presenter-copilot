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
teach.submit_text
teach.confirm_knowledge_item
teach.reject_knowledge_item
```

Voice input arrives through ASR utterances rather than a separate audio upload method.

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

Secrets are referenced by an opaque credential key managed by the desktop/OS credential layer; plaintext keys should not cross arbitrary renderer APIs.

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
- generate(request: ReasoningRequest) -> stream[ReasoningEvent]
- cancel(run_id)
```

`ReasoningRequest` contains structured context fields:

```text
task_type
question
current_slide_summary
evidence[]
preferred_user_explanations[]
audience_context[]
style_policy
privacy_mode
output_schema
latency_budget_ms
```

Provider adapters must not query project storage directly. Context assembly happens before provider invocation so privacy behavior is testable.

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

## 11. Privacy manifest

Before every remote call, core emits/stores a manifest:

```json
{
  "provider_id": "...",
  "task_type": "answer_scaffold",
  "privacy_mode": "selected_context_cloud",
  "classes_sent": ["question", "document_excerpt", "user_preferred_answer"],
  "source_ids": ["..."],
  "raw_audio_sent": false,
  "full_document_sent": false
}
```

This is the auditable boundary. It should be inspectable from project history.

## 12. Versioning

- protocol starts at integer version `1`;
- desktop and core perform compatibility handshake;
- unknown fields should be ignored where safe;
- breaking method/schema changes increment protocol version before public releases;
- one supported desktop build should ship with exactly one tested core build.
