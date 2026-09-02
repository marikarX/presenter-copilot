# MVP Data Model

## 1. Principles

- Project data is local by default.
- Project Brain and Audience Model data are project-scoped unless explicitly promoted.
- Speaker Profile may be global with project overrides.
- Every fact-bearing item must retain provenance.
- AI-generated inference must be distinguishable from source/user facts.
- Imported transcript speaker labels are metadata, not biometric identity.
- Deletion must be mechanically complete and testable.

## 2. Databases

Use two SQLite scopes:

### `app.db`

Global device-level state:

- app settings;
- provider configuration references (never plaintext secrets where OS credential storage is available);
- global Speaker Profile;
- recent project list;
- schema/app version metadata.

### `projects/<project-id>/project.db`

Everything specific to one presentation/project.

## 3. Core entities

### Project

```text
Project
- id UUID PK
- name TEXT
- created_at DATETIME
- updated_at DATETIME
- privacy_mode ENUM(local_only, selected_context_cloud, full_context_cloud)
- default_style_policy ENUM(preserve_voice, light_polish, executive_concise, custom)
- custom_style_guidance TEXT nullable
- current_presentation_id UUID nullable
- schema_version INTEGER
```

### Document

```text
Document
- id UUID PK
- project_id UUID
- kind ENUM(presentation, supporting, transcript, note)
- original_name TEXT
- local_snapshot_path TEXT nullable
- source_uri TEXT nullable
- sha256 TEXT
- mime_type TEXT
- parser_id TEXT
- imported_at DATETIME
- parse_status ENUM(pending, ready, error)
- metadata_json JSON
```

### SourceUnit

Structured unit within a document.

```text
SourceUnit
- id UUID PK
- document_id UUID
- unit_type ENUM(slide, page, section, transcript_segment, user_note)
- ordinal INTEGER nullable
- title TEXT nullable
- start_ms INTEGER nullable
- end_ms INTEGER nullable
- speaker_label TEXT nullable
- text TEXT
- metadata_json JSON
```

For Teams/Webex transcripts, `speaker_label` preserves the platform/user-provided label exactly enough for attribution while allowing a separate normalized audience mapping.

### Chunk

```text
Chunk
- id UUID PK
- source_unit_id UUID
- chunk_index INTEGER
- text TEXT
- token_count INTEGER nullable
- embedding_key TEXT nullable
- lexical_text TEXT
- created_at DATETIME
```

### ProvenanceRef

Logical shape used throughout the application; may be normalized or serialized.

```text
ProvenanceRef
- source_type ENUM(document, user_statement, practiced_answer, transcript, ai_inference)
- source_id UUID
- source_unit_id UUID nullable
- label TEXT
- exact_span TEXT nullable
- confidence REAL nullable
```

`ai_inference` may support reasoning but cannot be presented as a sourced fact.

## 4. Speaker Profile

### SpeakerProfile (`app.db`)

```text
SpeakerProfile
- id UUID PK
- display_name TEXT nullable
- default_style_policy ENUM(...)
- custom_style_guidance TEXT nullable
- preferred_answer_seconds INTEGER nullable
- created_at DATETIME
- updated_at DATETIME
```

### SpeakerEvidence (`app.db`)

Stores user-approved evidence only.

```text
SpeakerEvidence
- id UUID PK
- speaker_profile_id UUID
- evidence_type ENUM(preferred_phrase, analogy, explanation_pattern, vocabulary, coaching_preference, rejected_pattern)
- text TEXT
- origin_project_id UUID nullable
- origin_session_id UUID nullable
- user_approved BOOLEAN
- created_at DATETIME
```

### ProjectStyleOverride (`project.db`)

```text
ProjectStyleOverride
- id UUID PK
- project_id UUID
- style_policy ENUM(...)
- custom_guidance TEXT nullable
- enabled BOOLEAN
```

## 5. User-authored project knowledge

### KnowledgeItem

```text
KnowledgeItem
- id UUID PK
- project_id UUID
- kind ENUM(fact, decision, rationale, preferred_explanation, analogy, private_note, constraint, objection, answer)
- text TEXT
- use_live BOOLEAN
- use_rehearsal BOOLEAN
- preferred BOOLEAN
- created_by ENUM(user, ai_suggested_user_confirmed)
- origin_session_id UUID nullable
- created_at DATETIME
- updated_at DATETIME
```

### KnowledgeEvidence

```text
KnowledgeEvidence
- knowledge_item_id UUID
- provenance_type ENUM(document, user_statement, transcript, practiced_answer)
- provenance_id UUID
```

A Teach-mode statement can be a valid user-authored source even when it does not appear in imported documents; the UI should show that distinction.

## 6. Audience Model

### AudienceProfile

```text
AudienceProfile
- id UUID PK
- project_id UUID
- display_name TEXT
- role TEXT nullable
- organization TEXT nullable
- user_notes TEXT nullable
- active BOOLEAN
- created_at DATETIME
- updated_at DATETIME
```

### TranscriptSpeakerMap

```text
TranscriptSpeakerMap
- id UUID PK
- document_id UUID
- native_speaker_label TEXT
- audience_profile_id UUID nullable
- mapped_by ENUM(user, import_metadata)
- created_at DATETIME
```

No voice embedding field exists.

### AudienceObservation

```text
AudienceObservation
- id UUID PK
- audience_profile_id UUID
- observation_type ENUM(topic_interest, question_pattern, answer_preference, recurring_objection, interaction_pattern, decision_criterion)
- text TEXT
- derivation ENUM(user_entered, source_derived, ai_inferred)
- confidence REAL nullable
- sensitive_trait BOOLEAN DEFAULT false
- created_at DATETIME
```

### AudienceObservationEvidence

```text
AudienceObservationEvidence
- observation_id UUID
- provenance_type ENUM(transcript, user_note, session_question)
- provenance_id UUID
```

Application logic must reject creation of observations representing prohibited/sensitive inference categories defined in `PRIVACY_SAFETY.md`.

## 7. Sessions and speech

### Session

```text
Session
- id UUID PK
- project_id UUID
- mode ENUM(teach, challenge, run, live_assist)
- started_at DATETIME
- ended_at DATETIME nullable
- style_policy ENUM(...)
- privacy_mode ENUM(...)
- provider_id TEXT nullable
- current_slide_start INTEGER nullable
- status ENUM(active, completed, aborted, error)
```

### Utterance

```text
Utterance
- id UUID PK
- session_id UUID
- actor ENUM(user, audience_profile, ai_coach, unknown_audience)
- audience_profile_id UUID nullable
- text TEXT
- start_ms INTEGER nullable
- end_ms INTEGER nullable
- asr_confidence REAL nullable
- slide_ordinal INTEGER nullable
- is_final BOOLEAN
```

Raw audio is not required to persist for P0.

### Question

```text
Question
- id UUID PK
- session_id UUID
- asked_by_audience_profile_id UUID nullable
- utterance_id UUID nullable
- text TEXT
- origin ENUM(simulated, live, imported, user_entered)
- created_at DATETIME
```

### AnswerVersion

```text
AnswerVersion
- id UUID PK
- question_id UUID
- session_id UUID
- text TEXT
- origin ENUM(user_spoken, user_edited, ai_suggested)
- preferred BOOLEAN
- correctness_score REAL nullable
- directness_score REAL nullable
- completeness_score REAL nullable
- concision_score REAL nullable
- style_match_score REAL nullable
- created_at DATETIME
```

### AnswerEvidence

```text
AnswerEvidence
- answer_version_id UUID
- provenance_type ENUM(document, user_statement, transcript, practiced_answer)
- provenance_id UUID
```

## 8. Presentation state

### Presentation

```text
Presentation
- id UUID PK
- document_id UUID
- slide_count INTEGER
- title TEXT nullable
```

### SlideStateEvent

```text
SlideStateEvent
- id UUID PK
- session_id UUID
- slide_ordinal INTEGER
- timestamp_ms INTEGER
- source ENUM(powerpoint, manual, inferred)
```

## 9. HUD/cues

### Cue

```text
Cue
- id UUID PK
- session_id UUID
- question_id UUID nullable
- cue_type ENUM(fact, structure, reminder, source_pointer, warning)
- text TEXT
- state ENUM(partial, final)
- confidence REAL nullable
- created_at DATETIME
- displayed_at DATETIME nullable
- dismissed_at DATETIME nullable
```

### CueEvidence

```text
CueEvidence
- cue_id UUID
- provenance_type ENUM(document, user_statement, transcript, practiced_answer)
- provenance_id UUID
- rank INTEGER
```

## 10. Provider calls

### ProviderRun

```text
ProviderRun
- id UUID PK
- session_id UUID nullable
- task_type TEXT
- provider_id TEXT
- privacy_mode ENUM(...)
- started_at DATETIME
- ended_at DATETIME nullable
- status ENUM(success, error, cancelled)
- input_token_count INTEGER nullable
- output_token_count INTEGER nullable
- latency_ms INTEGER nullable
- context_manifest_json JSON
- error_code TEXT nullable
```

`context_manifest_json` records which provenance IDs/classes were sent; it should not duplicate full confidential prompt text by default.

## 11. Embedding store

For M2, each project uses a generation-based local embedding file/index keyed
by `Chunk.id`. The schema leaves `entity_type`/`source_class` generic so later
milestones can add KnowledgeItem, practiced-answer, or transcript evidence
vectors without replacing the store. M2 only writes `entity_type=chunk` and
`source_class=document`.

The active matrix is stored as a normalized float32 NumPy `.npy` file under the
project's `embeddings/` directory and is opened with memory mapping for query
time access. The shared FastEmbed model cache is outside project vaults.
M2 retains exactly one `embedding_generations` row: the active generation and
its current `embedding_vectors` mapping set. A successful rebuild writes and
fsyncs the new matrix before the activation transaction, then retires the old
rows through the foreign-key cascade. If activation fails, the prior active
row and matrix remain usable and the newly written matrix is an orphan that
cleanup may remove.

```text
embedding_generations
- id UUID PK
- adapter_id TEXT
- model_id TEXT
- model_fingerprint TEXT
- dimension INTEGER
- matrix_relative_path TEXT
- matrix_row_count INTEGER
- is_active BOOLEAN
- created_at DATETIME

embedding_vectors
- generation_id UUID
- vector_id TEXT
- entity_type TEXT
- entity_id UUID
- project_id UUID
- source_class TEXT
- row_index INTEGER
- content_sha256 TEXT
```

Required metadata per vector:

```text
vector_id
entity_type
entity_id
project_id
source_class
generation_id
row_index
content_sha256
```

`Chunk.embedding_key` is `generation_id:chunk_id` only when the chunk has a
mapping in the active generation; otherwise it is null. Rebuilds compact the
current parsed chunks into a new generation, reuse a compatible vector when
chunk ID/content hash/model identity match, and activate the matrix only after
the file has been written and flushed. Deleted chunks lose their mappings via
the database relationship/trigger and can never be returned by retrieval.

## 12. Delete semantics

### Delete session

Removes:

- utterances;
- questions/answers owned only by that session unless explicitly promoted;
- cues;
- provider run manifests;
- session files.

### Delete project

Removes entire project directory including:

- `project.db`;
- imported source snapshots;
- extracted text;
- embedding files;
- transcripts;
- session artifacts;
- diagnostics scoped to project.

Then remove the project from `app.db` recent-project references. Global SpeakerEvidence originating from the project must either be removed or have its project-origin link cleared only if the user explicitly promoted it; default behavior is to remove it.

## 13. Schema migration rule

Every DB has an integer schema version. Migrations are forward-only in normal operation and must be covered by fixture tests from every released pre-1.0 schema once releases begin.
