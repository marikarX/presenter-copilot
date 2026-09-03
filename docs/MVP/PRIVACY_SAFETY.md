# MVP Privacy and Safety Requirements

## 1. Product rule

Presenter Copilot processes only material the user is authorized to use. The application does not grant the user rights to recordings, transcripts, documents, or other people's data.

Local processing reduces disclosure risk but does not make unauthorized use lawful.

## 2. Meeting recordings and transcripts

P0 supports transcript import and preserves native speaker attribution when present.

Preferred source order:

1. platform-provided named transcript (Teams/Webex/etc.);
2. structured transcript with speaker labels;
3. user mapping of unknown labels;
4. diarization only as a later fallback.

P0 does not persist voiceprints, facial embeddings, or other biometric identity templates.

If future recording import is added:

- user must affirm they are authorized to process it;
- raw media persistence is opt-in;
- diarization means `same unknown speaker`, not identity recognition;
- user maps diarized speakers to project-local audience profiles.

## 3. Audience Model boundary

Allowed observations are limited to observable presentation/meeting interaction patterns, for example:

- topics frequently questioned;
- recurring objections;
- preference for short vs detailed answers when supported by interaction evidence;
- tendency to ask for comparisons, evidence, failure modes, ownership, cost, schedule, etc.;
- question sequencing/interaction patterns;
- explicit role/decision criteria supplied by the user.

Do not infer/store sensitive or hidden traits such as:

- race/ethnicity;
- religion;
- political beliefs/affiliation;
- sexual orientation or sex life;
- medical/health conditions;
- disability unless explicitly necessary and lawfully provided for accessibility;
- criminal history;
- union membership;
- psychological diagnosis;
- deception/lie detection;
- hidden emotional state;
- intelligence or employability score derived from voice/face.

Do not implement workplace emotion recognition from voice/video.

M4 enforces this boundary with one fail-closed observation policy at every
user-entered, candidate-acceptance, and observation-edit gate. The policy
rejects sensitive identity, health, criminal, political, religious, sexual,
psychological, deception, intelligence, employability, and hidden-emotion
wording. It also prevents source-derived rows from becoming active without
exact transcript evidence. `sensitive_trait` is an explicit stored flag for
the schema contract, but accepted M4 observations must have it false.

## 4. Speaker Profile boundary

The user may intentionally let the app learn their own speaking style.

P0 rules:

- profile belongs to the user;
- learned evidence is visible/removable;
- only a confirmed project KnowledgeItem can be offered for promotion, and
  promotion is a separate explicit user action;
- project-derived evidence is not silently promoted globally;
- AI-generated phrasing is not treated as the user's style unless accepted;
- reset/export/delete is supported;
- do not label the user with opaque personality diagnoses.

## 5. Privacy modes

### Local Only

Required invariant:

```text
raw audio         -> local only
transcript        -> local only
source files      -> local only
embeddings        -> local only
reasoning context -> local only
```

For M3 Teach, a remote provider is impossible in this mode. A configured local
provider may be used locally; otherwise the typed direct-save/retrieval-only
path remains available. No provider/network request is allowed from the
content-processing path. Update checks/optional external links must be
separable from session processing and disabled in the network-isolation test
environment.

The project row is authoritative for this decision. A Teach or Challenge
session cannot select a broader privacy mode, and changing an active project's
mode to `local_only` immediately prevents subsequent remote content calls; the
session's stored mode is not an authority override. Challenge question and
evaluation requests use the same local/remote router and selected-context
manifest path as the rest of the product. Challenge history is local project
state; it is not uploaded as a corpus. M6 Run ASR is local regardless of the
project privacy mode: the Python core owns capture, no provider receives
microphone data, and the deterministic post-run debrief does not call a
provider. The explicit `asr.prepare_model` operation is separate setup and is
the only M6 operation permitted to download approved model assets.

Run debrief is rehearsal retrieval: the core sends `usage=rehearsal` and may
set `allow_private=true`, while retrieval still enforces each KnowledgeItem's
independent `use_rehearsal` flag. Raw PCM and partial text remain transient;
only the final local `Utterance`, slide/timeline state, markers, and bounded
debrief are durable.

### Selected Context Cloud

Required invariant:

```text
raw audio         -> local only
full corpus       -> local only
retrieval         -> local
remote payload    -> question + minimum selected excerpts/context
```

The app records a metadata-only context manifest before every remote call. It
identifies provider, task, privacy mode, sent provenance classes/IDs, and
explicit false values for raw audio, full documents/corpus, and private items.
The request is bounded selected context; it does not upload files, raw audio,
or the full project history. For Challenge, the selected packet may contain
only the current question or typed answer, canonical selected Evidence,
accepted active AudienceContext, approved style evidence, and bounded prior
preferred wording needed for the operation. Pending, rejected, stale, or
unresolved audience material is excluded.

### Full Context Cloud

Explicit opt-in only. M3 deliberately uses the same conservative selected
context packet even when this setting is selected; it does not implement
full-corpus upload. UI must not switch to it automatically on provider error.

## 6. Secrets

- use OS credential storage for provider secrets where possible;
- M3's OpenAI adapter reads only `OPENAI_API_KEY` from the core process
  environment and persists only `credential_source = environment`;
- never store API keys or OAuth refresh tokens in project DB/logs;
- never expose secrets to renderer context;
- never accept plaintext provider secrets through renderer IPC;
- official provider auth only;
- Codex integration, if added, must use documented app-server/SDK authentication surfaces;
- never scrape ChatGPT cookies or call undocumented backend endpoints.

## 7. Local IPC

Desktop core uses child-process stdio for P0.

Security implications:

- no unauthenticated listening port;
- renderer talks to main/preload allowlisted APIs only;
- validate every IPC method/payload;
- reject filesystem paths outside permitted import/user-selected locations where applicable;
- protect against malicious document filenames/path traversal when snapshotting sources.

## 8. Imported document handling

Treat every imported document as untrusted input.

Requirements:

- parsers run without executing macros/scripts;
- PPTX/DOCX are parsed as data, not opened with macro execution;
- imported HTML/Markdown is rendered safely/no arbitrary script;
- archive extraction prevents zip-slip/path traversal;
- enforce reasonable file/expanded-size limits;
- hash files for reproducibility/deduplication;
- sanitize filenames before local snapshot paths.

## 9. Prompt injection/content injection

Documents and transcripts can contain instructions aimed at the model.

The orchestration layer must distinguish:

- system/application policy;
- user instructions;
- retrieved source content.

Retrieved document text is evidence, not executable instruction. Provider prompts must explicitly mark sources as untrusted data and never permit a document to override privacy, tool, or system policy.

Challenge also supplies a core-owned trusted task instruction for question,
follow-up, and evaluation operations. The application policy and task
instruction are placed in trusted system/application content by the OpenAI
adapter; retrieved evidence, audience notes, transcript excerpts, prior
answers, and other project text remain in a separate untrusted data payload.
The task instruction is included in the bounded request-size calculation but
its body is not stored in ProviderRun manifests. No tools or chain-of-thought
requests are permitted.

## 10. Provenance and hallucination controls

For live fact cues:

- prefer retrieval-only facts when possible;
- exact numbers require supporting evidence;
- AI inference must not masquerade as a source fact;
- low-confidence or conflicting evidence should produce a warning/ambiguity cue rather than a confident number;
- expanded provenance must be available.

## 11. Capture protection

HUD uses OS/Electron content-protection features where supported.

Rules:

- never claim invisibility/undetectability;
- show status if capture protection is unavailable;
- user can manually hide HUD before sharing;
- capture protection is defense-in-depth, not a legal/privacy guarantee.

## 12. Logging

Default logs may include:

- timestamps;
- event names;
- durations;
- error codes;
- model/provider IDs;
- non-sensitive counts/sizes.

M3 may also record ProviderRun task/provider IDs, bounded latency and token
counts, error codes, and the metadata-only context manifest.

Default logs must not include:

- raw audio;
- full transcript;
- full source excerpts;
- API keys/tokens;
- audience sensitive data;
- complete provider prompts.

M4 transcript import, speaker mapping, extraction, and review logs contain
only event names, bounded counts, IDs, statuses, and error codes. They never
log full transcript text or raw transcript payloads. The same prohibited
sensitive/hidden-trait policy applies to profile notes and observation text at
write time and again at context assembly. AudienceContextBuilder labels
profile notes as user-supplied content and includes only active profiles and
active, evidence-valid observations; pending, rejected, stale, unresolved, and
evidence-less source-derived rows are excluded.

M6 ASR/Run logs and events contain only safe device/model metadata, bounded
transcript text where the Run event contract requires it, timestamps, IDs,
statuses, and error codes. Raw PCM, PortAudio objects, model objects, COM
objects, complete prompts, and filesystem paths are excluded. Partial text is
ephemeral; only final utterances, slide state, markers, and the bounded local
debrief are stored.

The ASR capture callback never blocks on transcription. A dropped-input status
or full bounded frame queue is surfaced as `ASR_BACKPRESSURE`; the Run does not
continue with an implicitly incomplete final. During shutdown, an outstanding
worker or final retains capture ownership in retryable stopping state. The core
does not close a live model, mark the session terminal, generate a debrief, or
delete the session/project until that owner has been safely released. If the
application budget expires, the sidecar may exit under the no-orphan policy,
but the active session remains recoverable on restart.

User-requested diagnostic export must be previewable/redactable before sharing.

## 13. Deletion

Deletion is a feature, not a support procedure.

P0 must support:

- delete session;
- delete imported source;
- delete Audience Profile/observations;
- remove Speaker Profile evidence;
- delete entire project;
- reset entire local app state.

Automated tests verify filesystem and DB removal.

Deleting an individual session cascades its session, final Run utterances,
slide state events, Run markers, Run debrief, provider runs, and pending Teach
candidates. Confirmed project KnowledgeItems survive through
durable UserStatement snapshots; their old session and utterance IDs are
detached. Approved global SpeakerEvidence also detaches a deleted session ID.
Because app and project SQLite databases cannot share a transaction, deletion
validates the project session, clears app-level session provenance first, then
performs project detachment and session deletion transactionally. App cleanup
failure leaves all project rows unchanged. A project-side failure after app
cleanup leaves the session and project rows intact and returns a retryable
error; retrying is safe.

Run-owned ASR cleanup is an earlier deletion gate. `session.delete` and
`project.delete` first require successful bounded capture/final/worker cleanup,
including a stale or prematurely terminal Run row whose live ASR owner still
matches. A blocked final therefore cannot be hidden by a terminal status or
cause model/audio handles to be released underneath a live worker.

## 14. UX disclosures

Before transcript/meeting import:

> Only analyze recordings or transcripts you are authorized to use. Local processing does not change your legal or organizational obligations.

Before remote reasoning is first enabled for a project:

> Selected excerpts and the current question may be sent to your configured AI provider. Raw meeting audio remains local in this mode.

The M3 Teach disclosure also states that private KnowledgeItems, raw audio, and
the full corpus are excluded. A project must record an explicit acknowledgement
before a remote reasoning call; configuring provider metadata alone is not
consent.

Keep disclosures concise and contextual rather than requiring broad legal acceptance for every session.

M4 implements this disclosure as a renderer gate: selecting Transcript shows
the authorization message first, and the native file picker is not opened
until the user explicitly continues. The selected path is handled by Electron
main/preload authority and is not supplied by renderer code as arbitrary core
filesystem authority.

## 15. P0 threat scenarios to test

- malicious PPTX filename attempts path traversal;
- prompt injection inside a source says to exfiltrate the corpus;
- provider adapter attempts network call in Local Only;
- deleted project remains in embedding cache;
- transcript maps one native speaker to wrong profile and user remaps it;
- remote provider response includes unsupported exact number;
- renderer tries to invoke non-allowlisted IPC method;
- core crashes while HUD is visible;
- content protection unavailable during screen share.
