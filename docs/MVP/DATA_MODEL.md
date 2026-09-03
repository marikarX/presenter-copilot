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
- non-secret provider configuration metadata (`provider_id`, `enabled`, `model_id`,
  `credential_source`, and safe configuration JSON); credentials remain in the
  core environment for M3;
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
- remote_reasoning_acknowledged_at DATETIME nullable
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
- enabled BOOLEAN
- created_at DATETIME
- updated_at DATETIME
```

The project keeps the effective project style policy and custom guidance on its
`Project` row. `ProjectStyleOverride.enabled` is the single switch that selects
those values over the global Speaker Profile; the precedence is explicit
project override > global Speaker Profile > `preserve_voice`.

## 5. User-authored project knowledge

### UserStatement

```text
UserStatement
- id UUID PK
- project_id UUID
- origin_session_id UUID nullable
- source_utterance_id UUID nullable
- text TEXT
- created_at DATETIME
```

Confirmed Teach knowledge links to this durable project-level snapshot rather
than treating an AI question or candidate as user evidence. Session deletion
detaches the two origin identifiers before cascading session utterances.

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
- private BOOLEAN
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

`private = true` keeps a confirmed item project-local and excludes it from
remote provider context. It does not imply `use_live = false`; those controls
remain independent.

### TeachCandidate

```text
TeachCandidate
- id UUID PK
- session_id UUID
- source_utterance_id UUID
- proposed_kind ENUM(...)
- proposed_text TEXT
- provider_run_id UUID nullable
- status ENUM(pending, confirmed, rejected)
- knowledge_item_id UUID nullable
- created_at DATETIME
```

Candidates are provisional, are not retrieval entities, and are never global
SpeakerEvidence until the user confirms the resulting KnowledgeItem and takes
the separate promotion action.

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
- origin ENUM(user_typed, user_spoken, user_edited, ai_suggested)
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
- assist_id UUID-like request identifier, unique within the session
- cue_type ENUM(fact, structure, reminder, source_pointer, warning)
- text TEXT
- state ENUM(partial, final)
- route ENUM(retrieval_only, local_reasoning, remote_reasoning)
- provider_run_id UUID nullable
- created_at DATETIME
- displayed_at DATETIME nullable
- dismissed_at DATETIME nullable
```

### CueEvidence

```text
CueEvidence
- cue_id UUID
- source_type ENUM(document, user_statement, transcript)
- source_id UUID
- source_unit_id UUID nullable
- knowledge_item_id UUID nullable
- label_snapshot TEXT
- rank INTEGER
- available BOOLEAN
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
- status ENUM(started, success, error, cancelled)
- input_token_count INTEGER nullable
- output_token_count INTEGER nullable
- latency_ms INTEGER nullable
- context_manifest_json JSON
- error_code TEXT nullable
```

`context_manifest_json` records which provenance IDs/classes were sent; it should not duplicate full confidential prompt text by default.

## 11. Embedding store

M2 introduced a generation-based local embedding file/index, and M3 extends
the same store rather than creating a second vector database. The active
generation contains ready document chunks plus confirmed KnowledgeItems with
`entity_type=knowledge_item` and `source_class=user_knowledge`. Candidates and
rejected items are never indexable. Private KnowledgeItems may be embedded
locally because remote filtering happens during context assembly.

The active matrix is stored as a normalized float32 NumPy `.npy` file under the
project's `embeddings/` directory and is opened with memory mapping for query
time access. The shared FastEmbed model cache is outside project vaults.
The project retains exactly one active `embedding_generations` row and one
current `embedding_vectors` mapping set. A successful rebuild writes and
fsyncs the new matrix before the activation transaction, then retires the old
rows through the foreign-key cascade. Compatible vectors are reused only when
entity type, entity ID, content hash, model identity, and dimension match. If
activation fails, the prior active row and matrix remain usable and the newly
written matrix is an orphan that cleanup may remove.

The in-process mapping-count cache is valid only for an unchanged generation
mapping set. Source mutations, KnowledgeItem mapping deletion, confirmed
KnowledgeItem mutation, project eviction, and successful generation activation
invalidate the affected project entries; a failed rebuild leaves the active
generation and its cacheable mapping set unchanged.

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
mapping in the active generation; otherwise it is null. Rebuilds compact all
current indexable entities into a new generation, activate the matrix only
after the file has been written and flushed, and synchronize immediately after
KnowledgeItem confirmation/deletion when the local model is available. A
model-unavailable sync leaves the durable KnowledgeItem and lexical retrieval
usable while reporting partial semantic coverage. Deleted chunks and knowledge
items lose their mappings and can never be returned by retrieval.

## 12. Delete semantics

### Delete session

Removes:

- the session row;
- utterances;
- provider run manifests;
- pending Teach candidates;
- session-owned files, if present.

Confirmed KnowledgeItems and their UserStatement snapshots survive. Their
`origin_session_id` and `source_utterance_id` are nulled before the session
cascade; approved global SpeakerEvidence keeps its project origin but also
detaches a deleted session ID.

### Delete project

Removes entire project directory including:

- `project.db`;
- imported source snapshots;
- extracted text;
- embedding files;
- transcripts;
- session artifacts;
- diagnostics scoped to project.

Then remove the project from `app.db` recent-project references. Global
SpeakerEvidence whose `origin_project_id` is the deleted project is removed by
the app-database foreign-key cascade. Unrelated global evidence and the shared
embedding model cache survive.

## 13. Schema migration rule

Every DB has an integer schema version. Migrations are forward-only in normal
operation and must be covered by fixture tests from every released pre-1.0
schema once releases begin. M7 uses explicit migration history:
`app.db` 1 -> 2 and `project.db` 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7, preserving
existing registry, source, chunk, generation, mapping, project-setting,
session, Teach, Challenge, provider-run, and style rows. The v3 -> v4
migration adds only project-local transcript attribution and Audience Model
tables. The v4 -> v5 migration adds only project-local Challenge state and
promotion tables. The v5 -> v6 migration adds only Run slide, marker, and
debrief state. The v6 -> v7 migration adds only Live Assist cue and cue-evidence
state. A future schema version is rejected without mutating the
database. `app.db` remains at version 2.

## 14. M4 transcript attribution and Audience Model

Transcript documents continue to use the existing `documents`,
`source_units`, and `chunks` tables. M4 persists `kind=transcript`,
`unit_type=transcript_segment`, bounded `start_ms`/`end_ms`, and the native
`speaker_label`. Transcript chunks use the existing retrieval generations;
there is no second transcript vector store. Public transcript provenance uses
`source_type=transcript` and points to the exact `SourceUnit`.

The v4 project-local tables are:

```text
audience_profiles
- id UUID PK
- project_id UUID FK project ON DELETE CASCADE
- display_name TEXT
- role TEXT nullable
- organization TEXT nullable
- user_notes TEXT nullable
- active BOOLEAN
- created_at / updated_at

transcript_speaker_maps
- document_id UUID FK documents ON DELETE CASCADE
- native_speaker_label TEXT
- audience_profile_id UUID nullable FK audience_profiles ON DELETE SET NULL
- mapped_by ENUM(user, import_metadata)
- created_at
- PK(document_id, native_speaker_label)

audience_observations
- id UUID PK
- audience_profile_id UUID FK audience_profiles ON DELETE CASCADE
- observation_type ENUM(topic_interest, question_pattern, answer_preference,
  recurring_objection, interaction_pattern, decision_criterion)
- text TEXT
- derivation ENUM(user_entered, source_derived, ai_inferred)
- confidence REAL nullable
- sensitive_trait BOOLEAN
- review_status ENUM(active, stale)
- created_at / updated_at

audience_observation_evidence
- observation_id UUID FK audience_observations ON DELETE CASCADE
- provenance_type = transcript
- provenance_id UUID source_units.id
- PK(observation_id, provenance_type, provenance_id)

audience_observation_candidates
- id UUID PK
- audience_profile_id UUID FK audience_profiles ON DELETE CASCADE
- observation_type / proposed_text / confidence
- fingerprint TEXT
- status ENUM(pending, accepted, rejected, stale)
- observation_id UUID nullable FK audience_observations ON DELETE SET NULL
- created_at / updated_at

audience_observation_candidate_evidence
- candidate_id UUID FK audience_observation_candidates ON DELETE CASCADE
- provenance_type = transcript
- provenance_id UUID source_units.id
- PK(candidate_id, provenance_type, provenance_id)
```

Native labels are metadata only. They begin unresolved, and only an explicit
user mapping can associate a label with an AudienceProfile. A profile delete
sets mappings to NULL and cascades that profile's observations/candidates;
the transcript document and its chunks survive. Transcript deletion removes
maps/evidence and marks retained source-derived observations/candidates stale
before the source rows cascade. User-entered observations without transcript
evidence survive.

Source-derived observations require at least one currently attributed
transcript evidence row at acceptance. Attribution changes never transfer an
old observation to another profile: incompatible observations become stale,
pending candidates become stale, and stale rows are excluded from context.

## 15. M5 Challenge mode

Challenge state is project-local and session-owned. `app.db` remains at schema
version 2; `project.db` is schema version 7. The explicit v4 -> v5 migration
creates these tables:

```text
challenge_configurations
- session_id UUID PK/FK sessions ON DELETE CASCADE
- intensity ENUM(normal, skeptical, adversarial)
- allow_follow_ups BOOLEAN
- scope ENUM(full_deck, slide_range)
- slide_start INTEGER nullable
- slide_end INTEGER nullable
- state ENUM(ready_for_question, awaiting_answer, evaluated)
- created_at / updated_at

challenge_audiences
- id UUID PK
- session_id UUID FK sessions ON DELETE CASCADE
- audience_profile_id UUID nullable FK audience_profiles ON DELETE SET NULL
- selection_order INTEGER (0..2)
- display_name_snapshot / role_snapshot / organization_snapshot
- selected_at

questions
- id UUID PK
- session_id UUID FK sessions ON DELETE CASCADE
- asked_by_audience_profile_id UUID nullable FK audience_profiles ON DELETE SET NULL
- parent_question_id UUID nullable FK questions ON DELETE SET NULL
- provider_run_id UUID nullable FK provider_runs ON DELETE SET NULL
- audience_display_name_snapshot / audience_role_snapshot
- text TEXT
- origin = simulated
- rationale TEXT
- created_at

question_evidence
- question_id UUID FK questions ON DELETE CASCADE
- evidence_id UUID
- source_type / source_id / source_unit_id / label
- available BOOLEAN

question_audience_observations
- question_id UUID FK questions ON DELETE CASCADE
- observation_id UUID
- available BOOLEAN

answer_versions
- id UUID PK
- question_id UUID FK questions ON DELETE CASCADE
- session_id UUID FK sessions ON DELETE CASCADE
- provider_run_id UUID nullable FK provider_runs ON DELETE SET NULL
- text TEXT
- origin ENUM(user_typed, user_spoken, user_edited, ai_suggested)
- preferred BOOLEAN (at most one per question)
- correctness_score / directness_score / completeness_score /
  concision_score / style_match_score REAL nullable, normalized 0.0..1.0
- source_support_status / source_support_feedback
- bounded evaluation_json
- created_at

answer_evidence
- answer_version_id UUID FK answer_versions ON DELETE CASCADE
- evidence_id UUID
- source_type / source_id / source_unit_id / label
- available BOOLEAN

challenge_answer_promotions
- question_id UUID PK/FK questions ON DELETE CASCADE
- answer_version_id UUID UNIQUE/FK answer_versions ON DELETE CASCADE
- knowledge_item_id UUID UNIQUE/FK knowledge_items ON DELETE CASCADE
- promoted_at / updated_at
```

Question and answer evidence store canonical IDs and labels, never copied source
excerpts. Source deletion marks those references unavailable before the source
cascade. Profile deletion sets historical question links to NULL while the
question's display snapshots remain. Pending, rejected, stale, unresolved, or
prohibited Audience Model data is never copied into Challenge context.

Challenge uses `origin=user_typed` for M5 answers. A retry keeps one Question
row and creates another immutable AnswerVersion. Normal and follow-up questions
are separate Question rows; a follow-up records `parent_question_id` and uses
the same audience profile.

The complete validated typed answer up to 4,000 characters is the text sent to
the Challenge evaluation provider and the text persisted in AnswerVersion;
provider context fitting never substitutes a document-excerpt prefix. Word
count and estimated speaking time are calculated from that same complete
validated answer. If the complete answer plus trusted instructions and minimum
grounding cannot fit the bounded request, evaluation fails with
`CHALLENGE_CONTEXT_TOO_LARGE` and no AnswerVersion is created.

Audience observation references are checked against the current M4
AudienceContext rules before a generated Question is inserted. Historical
references remain in Challenge history, but `available` is false when the
profile is inactive/deleted, the observation is stale/sensitive/deleted, or a
source-derived observation no longer has current transcript attribution.

For KnowledgeItem-backed Challenge evidence, `KnowledgeItem.text` is the
authoritative current evidence payload and `UserStatement.text` is provenance
only. The canonical reference returns the KnowledgeItem ID and UserStatement
ID separately, and `preferred` is read from the KnowledgeItem flag rather than
inferred from `kind=answer`. An explicit re-save of an already promoted answer
sets both linked preferred flags true again.

An ordinary Challenge answer is not Project Brain knowledge. Only explicit
`challenge.save_preferred_answer` creates a `kind=answer`, `preferred=true`,
`use_rehearsal=true`, `use_live=true`, `created_by=user` KnowledgeItem through
the existing durable `UserStatement` provenance path. Session deletion detaches
the durable snapshot from the deleted session before cascading ordinary
Challenge rows. Replacing a promotion removes the prior active promotion and
its semantic mapping while retaining answer history. Knowledge deletion uses
the normal KnowledgeItem/index deletion path.

## 16. M6 Run mode

Run state remains project-local and reuses the existing `sessions` and
`utterances` tables. Only final ASR output creates an `Utterance` row:

```text
actor = user for Run and `unknown_audience` for Live Assist
is_final = 1
start_ms / end_ms = monotonic session-relative timestamps
asr_confidence = nullable adapter value
slide_ordinal = slide snapshot from utterance start, or latest valid slide
```

Partial ASR text is ephemeral and creates no row. No audio table exists and
raw PCM is never persisted.

The v5 -> v6 migration adds:

```text
slide_state_events
- id UUID PK
- session_id UUID FK sessions ON DELETE CASCADE
- slide_ordinal INTEGER NOT NULL CHECK >= 1
- timestamp_ms INTEGER NOT NULL CHECK >= 0
- source ENUM(powerpoint, manual, inferred)
- created_at DATETIME

run_markers
- id UUID PK
- session_id UUID FK sessions ON DELETE CASCADE
- marker_type ENUM(question, weak_point, note)
- timestamp_ms INTEGER NOT NULL CHECK >= 0
- slide_ordinal INTEGER nullable
- note TEXT nullable, bounded to 1,000 characters
- created_at DATETIME

run_debriefs
- session_id UUID PK/FK sessions ON DELETE CASCADE
- algorithm_version TEXT
- transcript_fingerprint TEXT
- debrief_json JSON
- created_at DATETIME
- updated_at DATETIME
```

`slide_state_events` persist only actual state changes, and
`presentation.slide_changed` is emitted after the insert commits. PowerPoint
state is read-only and `inferred` is reserved for a later milestone. Run
transcript/timeline/debrief reads are bounded and paginated. Session and
project deletion cascade all M6/M7 rows; the app-level ASR model cache is not
project data and survives deletion.

## 17. M7 Live Assist cues

Live Assist reuses the existing `sessions`, `utterances`, `slide_state_events`,
and embedding/retrieval tables. Live microphone finals are persisted as
unattributed `unknown_audience` utterances; partial text remains ephemeral.
There is no audio table and no question-segmentation table.

The v6 -> v7 migration adds:

```text
cues
- id UUID PK
- session_id UUID FK sessions ON DELETE CASCADE
- assist_id TEXT, UNIQUE(session_id, assist_id)
- cue_type ENUM(fact, structure, reminder, source_pointer, warning)
- text TEXT
- state ENUM(partial, final)
- route ENUM(retrieval_only, local_reasoning, remote_reasoning)
- provider_run_id UUID nullable FK provider_runs ON DELETE SET NULL
- created_at / displayed_at / dismissed_at

cue_evidence
- cue_id UUID FK cues ON DELETE CASCADE
- evidence_id TEXT
- source_type / source_id / source_unit_id
- knowledge_item_id nullable
- label_snapshot TEXT
- rank INTEGER
- available BOOLEAN
- PRIMARY KEY(cue_id, evidence_id)
```

CueService writes one row per Assist request, updates that row from `partial`
to `final`, caps evidence at eight items, and revalidates source/knowledge
availability before a cue is displayed. Source deletion/re-indexing preserves
the historical pointer but marks it unavailable. Cues and cue evidence cascade
with their session or project.
