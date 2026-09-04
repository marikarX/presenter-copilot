# Decision Log

This file records product and architecture decisions that are important enough to preserve across implementation changes.

## D-001 — Working repository name is not the public brand

**Status:** Accepted

Use `presenter-copilot` as a descriptive internal repository name.

Reason:

Early naming attempts such as CuePilot and CoPres collided with existing products/companies. Public naming should be screened deliberately rather than chosen during architecture work.

## D-002 — Local-first architecture

**Status:** Accepted as core hypothesis

Continuous latency-sensitive processing should run locally where practical.

Includes:

- audio capture;
- VAD;
- ASR;
- retrieval;
- presentation state;
- HUD rendering;
- session history.

Reason:

Local processing simultaneously improves latency, privacy, and marginal economics.

## D-003 — Hybrid rather than cloud-only reasoning

**Status:** Accepted

Remote reasoning is an escalation path, not the default path for every utterance.

Reason:

Many live presentation needs are retrieval or compression tasks. Sending continuous audio/context to a frontier model is unnecessary and creates cost/privacy/latency penalties.

## D-004 — Provider-pluggable reasoning

**Status:** Accepted

The core application must not depend on one model provider or one authentication mechanism.

Target backend classes:

- local model;
- user-supplied API;
- officially supported agent/backend integration.

Reason:

Provider terms, quotas, pricing, and model quality change. Backend portability is strategically important.

## D-005 — Codex integration must use official surfaces only

**Status:** Accepted

If Codex is integrated, use officially documented SDK/app-server authentication and invocation mechanisms.

Do not:

- scrape ChatGPT browser cookies;
- extract OAuth tokens for unrelated use;
- directly call undocumented ChatGPT backend endpoints;
- treat personal ChatGPT capacity as a guaranteed permanent commercial entitlement.

Codex remains optional until provider terms and intended product use are sufficiently clear for the chosen distribution model.

## D-006 — HUD is not a traditional teleprompter

**Status:** Accepted

Default HUD content is concise cueing, not prose.

Preferred output:

- keywords;
- numbers;
- answer structure;
- source/slide pointer;
- reminder of a practiced example.

Reason:

The objective is to support natural speaking and eye contact rather than replace the presenter with generated text.

## D-007 — Webcam-adjacent placement

**Status:** Accepted as UX hypothesis

The default cue surface should appear immediately below/around the top-center laptop webcam.

Reason:

This minimizes visible eye deviation without requiring specialized teleprompter hardware.

Needs validation across different webcam/display geometries.

## D-008 — High-stakes presentations are the initial wedge

**Status:** Accepted

Prioritize presentations where being prepared has material value:

- enterprise sales;
- technical proposals;
- board/executive reviews;
- investor pitches;
- consulting recommendations;
- bid/proposal defenses.

Reason:

Generic public-speaking coaching is crowded and has lower pricing power. High-stakes readiness has stronger willingness to pay and a clearer need for source-grounded Q&A.

## D-009 — Do not position as stealth/undetectable AI

**Status:** Accepted

Position the live interface as an AI-enhanced private presenter view.

Reason:

This is more compatible with enterprise adoption and avoids tying the product identity to cheating/deception use cases.

## D-010 — Rehearsal and live mode share one knowledge system

**Status:** Accepted

The same presentation corpus, audience model, questions, and practiced answers should flow from rehearsal into live mode and back into future rehearsal.

Reason:

This closed loop is a stronger differentiation hypothesis than isolated rehearsal or live-answer features.

## D-011 — Source provenance is required for important answers

**Status:** Accepted

The system should preserve where a surfaced fact or answer came from.

Reason:

High-stakes presentations often involve exact numbers and defensible claims. Generic model output without provenance is not sufficient.

## D-012 — Apache-2.0 for the open-source repository

**Status:** Accepted

The repository is licensed under the Apache License 2.0.

Reason:

Apache-2.0 is permissive, allows commercial use and modification, and includes an explicit contributor patent grant. It is a strong fit for an open-source AI/tooling project while leaving room for future separately developed hosted or enterprise services.

This decision does not determine the eventual commercial boundary. Remaining questions include:

- what stays in the open-source core;
- whether commercial functionality is hosted, enterprise-only, or open-core;
- contributor/CLA/DCO policy if contribution volume grows;
- trademark/public naming;
- third-party model/provider licensing and terms.

## D-013 — Mobile starts as a companion, not full platform parity

**Status:** Accepted as roadmap direction

The first mobile implementation should pair with the desktop app for private cue display, presenter controls, timers, and lightweight rehearsal capture.

Reason:

A second screen is useful while the laptop is screen-sharing and can sit close to the camera/audience sightline. Full standalone mobile parity would add substantial scope before the desktop interaction model is validated.

## D-014 — Product state is Speaker Profile + Project Brain + Audience Model

**Status:** Accepted

The MVP conceptual model has three distinct context layers:

- **Speaker Profile** — the user's own approved communication/style evidence;
- **Project Brain** — deck, sources, user explanations, decisions, rehearsals, questions, and answers for one project;
- **Audience Model** — project-local audience roles, attributed prior questions, observable interaction patterns, and user notes.

Reason:

Keeping these layers distinct gives the system better provenance, deletion semantics, personalization, and privacy than one undifferentiated vector store or chat history.

## D-015 — Preserve the user's voice by default

**Status:** Accepted

`Preserve my voice` is the default style policy. The application should prefer the user's own prior strong wording/explanations over newly generated prose.

Reason:

The product should make the presenter better prepared and clearer without making them sound like a generic LLM. Style learning must be visible, user-controlled, and removable.

## D-016 — Native transcript attribution before diarization; no persistent biometrics in MVP

**Status:** Accepted

When prior meeting transcripts are imported, preserve platform/native speaker names and timestamps first. Let the user map those labels to project-local audience profiles. Diarization is only a future fallback when attribution is missing.

Do not persist voiceprints, facial embeddings, or biometric identity templates in the MVP.

Reason:

Teams/Webex and similar transcripts often already contain useful attribution. Reusing that metadata is more accurate, simpler, and avoids unnecessary biometric/privacy complexity.

## D-017 — MVP desktop stack is Electron + TypeScript UI with a Python core sidecar

**Status:** Accepted for MVP

Use Electron/React/TypeScript for desktop/HUD behavior and a Python sidecar for parsing, ASR, retrieval, orchestration, and provider adapters.

Electron main process communicates with the sidecar over newline-delimited JSON on child-process stdio. Normal desktop operation does not require a localhost network listener.

Reason:

This split optimizes implementation speed while preserving strong boundaries: Electron is effective for Windows overlays/global shortcuts/capture protection, while Python has the strongest ecosystem for local speech/ML/document tooling. Stdio keeps the local attack surface small and is replaceable later.

## D-018 — Push-to-assist is the reliable MVP live trigger

**Status:** Accepted

Automatic audience-question detection may be developed experimentally, but MVP Live Assist must always support an explicit global push-to-assist action using the recent local transcript/current slide.

Reason:

Perfectly segmenting audience questions in arbitrary rooms is a hard reliability problem. The live-value hypothesis can be tested without making automatic detection a release blocker.

## D-019 — Milestone 0 shares protocol through a schema and contract fixtures

**Status:** Accepted for the scaffold

Keep `shared/schemas/protocol-v1.schema.json` as the canonical envelope
description and validate `protocol-v1.examples.json` from both the Python and
TypeScript test suites. Runtime code keeps small, explicit native types instead
of adding a schema-generation tool before the first domain payload exists.

Reason:

Milestone 0 has only three lifecycle methods. A shared schema plus executable
cross-language examples catches envelope drift while preserving the simple
Electron/Python boundary. Future method contracts can extend the schema or
introduce generated types when that becomes materially useful.

## D-020 — Renderer IPC authority is explicit and sender-origin checked

**Status:** Accepted for the scaffold

Privileged renderer-to-main IPC accepts only the exact bundled renderer file or
the exact loopback Vite development renderer in the explicit development run.
The main process also requires the sending frame to be the window's main frame.
Renderer-callable core methods have their own explicit runtime and TypeScript
allowlist; adding an internal core method does not expand renderer authority.

Reason:

The renderer boundary is a security boundary, not only a type boundary. Parsed
URL and frame checks prevent a future navigation, child frame, or environment
mistake from turning a new internal capability into renderer authority.

## D-021 — M1 uses explicit transactional SQLite user-version migrations

**Status:** Accepted for Milestone 1

Both `app.db` and each `project.db` use SQLite's integer `PRAGMA user_version`
with a small, ordered migration table implemented in the core. Migrations run
forward-only inside one transaction; a newer unsupported version is rejected
without mutation.

Reason:

M1 needs inspectable, deterministic persistence without introducing an ORM or
Alembic-scale dependency. The mechanism leaves a clear seam for future schema
versions while keeping the local database authority explicit.

## D-022 — Source snapshots use UUID-prefixed names and project-relative paths

**Status:** Accepted for Milestone 1

Imported files are hashed and copied atomically into `projects/<uuid>/sources/`
as `<document-uuid>-<sanitized-original-name>`. The database stores only the
project-relative snapshot path; source and project deletion resolve paths from
trusted UUIDs through the storage layer.

Reason:

The original display name remains useful to the presenter, while the UUID
prefix prevents same-name collisions. Relative-path validation and one
authoritative delete path make traversal and cross-project cleanup errors
mechanically testable.

## D-023 — M1 parser and chunking choices favor bounded deterministic provenance

**Status:** Accepted for Milestone 1

M1 uses `pypdf` for page-preserving PDF extraction, `python-pptx` for slide
text/title/notes extraction, and the Python standard library for TXT/Markdown
sections. Chunks are created independently within each SourceUnit with a
1,200-character ceiling, and the lexical fallback searches persisted chunks
without embeddings or providers. PPTX visible text remains the display body;
speaker notes are retained in metadata and appended to the same slide's
searchable chunk text without creating a second provenance unit.

Reason:

These adapters are small enough for the Windows sidecar and preserve the
source boundaries required by provenance. The unit-local chunk seam can later
feed embedding retrieval without changing the document model or crossing a
page/slide boundary.

## D-024 — Privileged Electron invokes return serializable result envelopes

**Status:** Accepted for the M1 correction pass

Electron main-process handlers that call the Python core return a plain
`{ok: true, result}` or `{ok: false, error}` envelope. The error branch carries
the canonical `code`, `message`, `retryable`, and `details` fields; sender
validation remains a hard rejection before the handler enters the envelope
helper.

Reason:

Electron IPC does not preserve arbitrary custom properties on rejected Error
objects. Returning structured data keeps core-domain errors reliable in the
renderer without expanding renderer authority or creating a second error
model.

## D-025 — M2 uses a pinned local FastEmbed adapter with offline normal operation

**Status:** Accepted for Milestone 2

Use `fastembed==0.8.0` with `BAAI/bge-small-en-v1.5` through a replaceable
`EmbeddingAdapter`. The normal application, indexing, and query paths use
CPU/ONNX execution with local-files-only loading. Model acquisition is limited
to the explicit developer bootstrap command and is never exposed through
renderer IPC.

Reason:

The M2 retrieval path must remain local, provider-neutral, reproducible, and
usable when the model cache is absent. A deterministic injectable adapter keeps
CI independent of internet/model availability without silently becoming the
production fallback.

## D-026 — Project embeddings use generation-based memory-mapped NumPy matrices

**Status:** Accepted for Milestone 2

Persist normalized float32 vectors in project-local `.npy` matrices under one
active generation record. Rebuilds write and fsync a staging matrix, atomically
activate the completed file through a transactional metadata switch, preserve
compatible vectors by chunk ID/content hash/model identity, retire all inactive
generation rows after activation, and garbage-collect orphaned derived files
best-effort. The previous generation remains the sole usable generation if the
activation transaction fails.

Reason:

The frozen MVP scale is at most 50,000 chunks, where an in-process vectorized
dot product is simpler and more inspectable than a vector database or ANN
service. Generations keep SQLite metadata and the matrix from exposing a
half-written index while preserving a later seam for additional entity types.

## D-027 — Confirmed Teach knowledge uses durable UserStatement provenance

**Status:** Accepted for Milestone 3

When a user confirms a Teach explanation, the core snapshots the user utterance
into a project-level `UserStatement` and links the confirmed KnowledgeItem to
that snapshot. Deleting the originating session cascades session-owned
utterances, provider runs, and pending candidates, but first nulls the
UserStatement's session and utterance references. Confirmed project knowledge
therefore remains attributable without pointing at deleted rows.

Reason:

Session history is disposable while confirmed Project Brain knowledge is not.
Keeping a durable project-scoped user snapshot preserves provenance without
promoting AI questions, candidate wording, or deleted session rows into user
evidence.

## D-028 — M3 uses the official OpenAI Responses adapter with core-owned credentials

**Status:** Accepted for Milestone 3

The first real provider is the official OpenAI Python SDK (`openai==3.6.0`)
through the Responses API. It reads only `OPENAI_API_KEY` from the core process
environment, sends bounded structured context with strict task-specific JSON
schemas, uses no tools, explicitly sets `store=false`, and applies a bounded
timeout. Provider metadata may store the model ID and opaque credential source,
but no secret crosses renderer IPC or is persisted.

Reason:

M3 needs one real, user-owned provider seam without coupling the domain to
browser or ChatGPT credentials. Keeping auth and context assembly in the core
makes the remote boundary testable and leaves full cancellation/resilience and
OS-backed secret storage for later milestones.

## D-029 — Project style override is an explicit switch over global Speaker Profile

**Status:** Accepted for Milestone 3

The existing project style policy and custom guidance remain the project-level
values. A single `project_style_overrides.enabled` row distinguishes whether
those values are active. The effective precedence is explicit project override
> global Speaker Profile > the product default `preserve_voice`.

Reason:

M3 needs project-specific style without creating two mutable copies of the
same policy. One switch plus the existing project fields keeps the source of
truth inspectable and makes global profile behavior reversible per project.

## D-030 — M4 Audience Model state is project-local

**Status:** Accepted for Milestone 4

AudienceProfiles, transcript speaker maps, observation candidates, reviewed
AudienceObservations, and their evidence live only in each project's
`project.db`. There is no global audience table and no automatic promotion
between projects. Project deletion removes the database and all M4 local
artifacts through the existing project lifecycle.

Reason:

Audience expectations and transcript authorization are presentation-specific.
Keeping them in the project vault makes isolation, deletion, and review
inspectable and avoids accidental cross-project personalization.

## D-031 — Native transcript labels require explicit user attribution

**Status:** Accepted for Milestone 4

VTT/SRT/named-TXT/structured-JSON adapters preserve native labels and cue
times as SourceUnit metadata. Every label begins unresolved. Only an explicit
`transcript.map_speaker` action associates a label with an AudienceProfile;
the system does not match names silently and never stores biometric identity.

Reason:

Meeting-provided labels are useful provenance but are not proof of identity.
Separating native metadata from user-controlled mapping prevents accidental
attribution while retaining exact evidence.

## D-032 — M4 extraction is deterministic and review-gated

**Status:** Accepted for Milestone 4

M4 uses bounded local rules over currently mapped transcript segments to
create provisional observation candidates. It does not invoke a remote or
local reasoning provider. Candidates remain outside AudienceContext until the
user reviews and accepts them; acceptance rechecks exact transcript evidence
and the prohibited-category policy.

Reason:

The milestone needs an auditable evidence/review boundary before richer
inference. Deterministic extraction makes privacy and regression behavior
testable without provider credentials or transcript upload.

## D-033 — Attribution changes stale evidence rather than transferring it

**Status:** Accepted for Milestone 4

When a native label is remapped, unmapped, or its transcript evidence is
removed during source deletion/re-index, affected source-derived observations
become stale and pending candidates become stale. They remain inspectable but
are excluded from AudienceContext and are never moved to the new profile.

Reason:

An attribution change invalidates the original interpretation. Requiring
fresh extraction/review is safer than silently rewriting a person's audience
model from evidence gathered under another mapping.

## D-034 — Challenge history is session-owned until explicit promotion

**Status:** Accepted for Milestone 5

Challenge Questions and AnswerVersions remain ordinary project-local session
history. They are not automatically indexed or treated as reusable user
knowledge. Only the explicit `challenge.save_preferred_answer` operation may
promote a typed user answer through the existing KnowledgeItem pipeline.

Reason:

Rehearsal history must remain inspectable without silently changing the
Project Brain. Explicit promotion gives the user a clear authorship and
retrieval boundary while retaining immutable retry history.

## D-035 — Challenge reuses canonical grounding, audience context, and routing

**Status:** Accepted for Milestone 5

Challenge question and evaluation generation composes the existing
`RetrievalService`, `AudienceContextBuilder`, `ProviderContextBuilder`, and
`ReasoningRouter`. Core owns audience rotation, privacy authority, state
transitions, and provenance validation; providers receive bounded trust-labeled
context and cannot invent Evidence, AudienceProfile identity, or authority.

Reason:

Keeping Challenge on the M2–M4 seams preserves project scoping, stale and
prohibited-observation filtering, prompt-injection isolation, conflict
handling, and the existing Local Only/Selected Context Cloud guarantees.

## D-036 — Preferred Challenge answers use durable user-authored provenance

**Status:** Accepted for Milestone 5

An explicitly preferred Challenge answer is copied as a durable user-authored
snapshot and promoted through the existing `KnowledgeItem` retrieval path with
`kind=answer`, `preferred=true`, `use_rehearsal=true`, and `use_live=true`.
The active promotion is replaced idempotently when another version is chosen;
the session may then be deleted without leaving provenance that points only at
session-owned rows. Evaluation prose is never promoted as user wording.

Reason:

Preferred practiced language should behave like other Project Brain evidence
and survive session cleanup, while remaining distinguishable from document or
transcript evidence.

## D-037 — Deterministic fake reasoning is explicit developer-only smoke support

**Status:** Accepted for Milestone 5

The desktop sidecar keeps the OpenAI reference provider as its normal default.
Deterministic fake reasoning is selected only when both
`PRESENTER_COPILOT_DEV_MODE=1` and
`PRESENTER_COPILOT_TEST_PROVIDER=deterministic_fake` are explicitly present.
It is local-only and cannot silently replace the normal provider or bypass
project privacy routing.

Reason:

Offline deterministic Electron acceptance must be possible without a provider
credential, while missing production credentials must not create a hidden cloud
or fake fallback.

## D-038 — Challenge evaluation preserves the complete accepted answer

**Status:** Accepted for Milestone 5 hardening

Challenge uses a distinct bounded current-user-input limit of 4,000 characters.
The complete validated answer is passed to `challenge_evaluation` and persisted
as the AnswerVersion text. Context fitting may remove lower-priority history,
audience, style, or extra evidence, but it never shortens the current answer;
an irreducible overflow fails with `CHALLENGE_CONTEXT_TOO_LARGE`.

Reason:

Evaluating a prefix while recording the full answer would make the coaching
result non-reproducible and could misrepresent the user's response.

## D-039 — Challenge revalidates current AudienceContext at the commit boundary

**Status:** Accepted for Milestone 5 hardening

After provider generation, Challenge reuses the M4 AudienceContextBuilder from
the caller-owned project connection before inserting a Question. A cited
observation must still belong to the active selected profile, be active and
non-sensitive, and retain valid source attribution. Historical references are
kept but are reported unavailable when those rules no longer hold.

Reason:

Provider calls can outlive a speaker remap, profile change, or source mutation;
storing an observation that was valid only at request start would make the
question's audience rationale untrustworthy.

## D-040 — KnowledgeItem payload and flags are authoritative

**Status:** Accepted for Milestone 5 hardening

Challenge canonical evidence reads the current `KnowledgeItem.text` and
`KnowledgeItem.preferred` values. The linked `UserStatement` supplies durable
user-authored provenance and its ID, but never replaces the curated knowledge
payload or determines preferred status. Explicit re-promotion sets both the
KnowledgeItem and AnswerVersion preferred flags true.

Reason:

Curated project knowledge may be edited after its provenance snapshot is
created. Retrieval and Challenge context must not resurrect stale wording or
claim that an answer remains preferred after the user clears the flag.

## D-041 — Challenge task contracts are trusted provider instructions

**Status:** Accepted for Milestone 5 hardening

Core supplies separate trusted instructions for Challenge question,
follow-up, and evaluation tasks. The OpenAI adapter places them with the
application policy in system/application content, while project and audience
text remains an untrusted data payload. Source-support status must agree with
supporting evidence IDs, and stopped sessions expose no mutation actions.

Reason:

Strict output schemas alone do not define the task's behavioral contract.
Separating task instructions from imported text preserves the prompt-injection
boundary and makes invalid evaluation claims fail before persistence.

## D-042 — Python core owns microphone capture; raw audio never crosses NDJSON

**Status:** Accepted for Milestone 6

The Python sidecar owns the M6 `AudioInputAdapter`, bounded PCM queue, VAD, and
local ASR worker. Electron/browser microphone APIs are not used for Run, raw
PCM is never transported over stdio NDJSON, and audio is not persisted in
files, SQLite, logs, provider packets, retrieval requests, or renderer state.

Reason:

Keeping capture and recognition in one local process makes the privacy and
lifecycle boundary explicit while preserving the existing stdio transport and
renderer isolation.

## D-043 — Runtime ASR is local-files-only; model bootstrap is explicit

**Status:** Accepted for Milestone 6

The approved `Systran/faster-whisper-base.en` model is acquired only through
the explicit model-preparation operation/command and stored in the shared
app-level ASR cache. `asr.start` uses local-files-only loading and fails with
`ASR_MODEL_UNAVAILABLE` when the model is absent; it never downloads and never
accepts an arbitrary renderer-supplied model path.

Reason:

An explicit setup boundary prevents a Run action from unexpectedly making a
network request or changing model identity during a rehearsal.

## D-044 — ASR partials are ephemeral; final utterances are the durable Run transcript

**Status:** Accepted for Milestone 6

One utterance receives one UUID across bounded partial and final events.
Partial text is renderer-facing transient state only. A final decode is
committed as an existing session `Utterance` with actor/user, timestamps,
optional adapter confidence, and the slide snapshot taken at utterance start;
`asr.final` is emitted only after that commit.

Reason:

This keeps the transcript durable and restartable without creating duplicate
rows or retaining a raw-audio/partial-text history that the user did not ask
to save.

## D-044a — ASR ingestion is decoupled from optional partial decoding

**Status:** Accepted for Milestone 6

The capture callback only performs bounded non-blocking enqueue. A fast
ingestion/VAD worker schedules recognition on a serialized decoder with one
replaceable optional partial request and a bounded queue of lossless final
requests. Final requests have priority and stale partials may be discarded.
Input-overflow status or queue exhaustion is a typed `ASR_BACKPRESSURE` error;
the service never silently produces an incomplete final transcript.

Reason:

Optional latency hints must not back up the real-time audio path or consume the
bounded queue needed for durable final utterances.

## D-044b — Run cleanup is an ownership and terminal-state gate

**Status:** Accepted for Milestone 6

Run cleanup stops capture, resolves final audio, persists before emitting the
final event, terminates both ASR workers, and releases audio/model resources
before stopping presentation or transitioning the session. A failed join,
unresolved final, or release failure retains the Run owner in retryable
stopping state. Session/project deletion and normal core shutdown use the same
gate; shutdown preserves an active session when its bounded budget expires.

Reason:

Terminal rows and released model handles are not safe substitutes for a live
worker that may still write transcript state. Keeping ownership authoritative
makes retry and restart recovery deterministic.

## D-045 — PowerPoint integration is read-only and feature detected

**Status:** Accepted for Milestone 6

The Windows PowerPoint adapter inspects only an already-running slideshow and
trusts it only when bounded filename and slide-count checks match the current
project presentation and the slide ordinal is valid. It never launches,
opens, edits, advances, or controls PowerPoint. Absence, mismatch, invalid
state, or mid-run COM failure switches the Run to persisted manual slide
tracking while preserving the latest known slide and active session.

Reason:

Read-only feature detection avoids arbitrary Office automation and ensures
manual tracking remains a reliable fallback on machines without PowerPoint or
when the active deck cannot be matched.

## D-046 — M6 debrief is deterministic, local, and retrieval-backed

**Status:** Accepted for Milestone 6

`RunService` produces a bounded debrief from final local utterances, persisted
slide state, markers, and current canonical retrieval evidence. It reports
evidence-review candidates rather than unsupported certainty, preserves
canonical evidence references, creates no KnowledgeItem automatically, and
uses a versioned fingerprint for idempotent persistence. Run retrieval uses
`usage=rehearsal` with private access independent from each KnowledgeItem's
`use_rehearsal` flag. Exact numeric/factual claims require matching normalized
values in eligible `fact_safe` evidence; mismatches and non-fact-safe hits are
not support, while conflicts produce review rather than a false user claim.
It does not invoke a remote reasoning provider.

Reason:

The first voice rehearsal must remain useful and repeatable without a provider
key, cloud transcript upload, or hidden promotion of rehearsal text into the
Project Brain.

## D-047 — Live Assist reuses the M6 local ASR and presentation services

**Status:** Accepted for Milestone 7

Live Assist uses the existing Python-owned ASR, VAD, utterance persistence, and
presentation-state services. Live microphone speech is stored only as
unattributed `unknown_audience` final utterances; no speaker identity or voice
inference is added.

Reason:

Reusing the established local capture boundary avoids a second microphone path
and keeps raw audio out of the renderer, NDJSON, and providers.

## D-048 — Explicit push-to-assist owns live question assembly

**Status:** Accepted for Milestone 7

An explicit typed question takes precedence. Otherwise core combines a bounded
recent window of final `unknown_audience` utterances, the latest ephemeral ASR
partial, and the canonical current slide. Automatic question segmentation is
deferred.

Reason:

An explicit action is predictable during a presentation and avoids silently
turning continuous speech into assistance requests.

## D-049 — One Assist owns one Cue row

**Status:** Accepted for Milestone 7

Retrieval creates the progressive `partial` cue and safe final output updates
the same persisted row. Cue evidence is bounded and retains canonical source
identifiers and label snapshots.

Reason:

Stable cue identity lets the HUD update in place without creating duplicate
history or losing the provenance of the displayed result.

## D-050 — The HUD is a dedicated main-owned window

**Status:** Accepted for Milestone 7

The HUD is a dedicated isolated Electron `BrowserWindow` with a minimal
allowlisted preload, click-through collapsed mode, interactive expanded mode,
and best-effort OS/Electron content protection.

Reason:

Separating the HUD from the main renderer keeps its control surface narrow and
allows show/hide to remain available when the core or provider is unavailable.

## D-051 — M7 cancellation is logical cancellation

**Status:** Accepted for Milestone 7

Assist supersession marks older work cancelled and suppresses stale results.
Provider-native cancellation and a broader provider-resilience redesign remain
deferred to M8.

Reason:

Logical cancellation is sufficient to protect cue identity and presentation
state without expanding this milestone into adapter-specific cancellation APIs.

## D-052 — Live retrieval uses live eligibility and remote exclusion

**Status:** Accepted for Milestone 7

Live retrieval always requests `usage=live`. Private live-enabled knowledge may
participate in local reasoning, but it is excluded from remote provider
context. Provider output must cite only the bounded evidence supplied by core.

Reason:

One usage flag and a core-owned privacy filter prevent rehearsal-only or
private project material from crossing the remote context boundary.

## D-053 — HUD preferences are app-scoped metadata

**Status:** Accepted for Milestone 7

Display selection, width, font size, top offset, and the eight remappable
shortcut accelerators are stored in bounded `app_metadata` under a versioned
HUD key. The project schema is not changed for device-specific UI preferences.

Reason:

HUD placement and keyboard choices follow the user's desktop setup rather than
one presentation, while the bounded metadata path avoids a new migration.
