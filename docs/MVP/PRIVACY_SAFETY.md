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

For M8 Teach, Challenge, and Live Assist, a remote provider is impossible in this mode. A configured local
provider may be used locally; otherwise the typed direct-save/retrieval-only
path remains available. E09 permits only an explicitly configured loopback
provider connection in Local Only; content cannot leave the machine. Private-LAN
inference is still a local provider, but its off-machine transport requires the
existing acknowledgement, minimum-context manifest, and private-item exclusion.
Endpoint validation rejects public/DNS destinations and redirects. See
[provider transport policy](../PROVIDERS.md). Update checks/optional external links must be
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

For E10, `remote payload` means the project-derived content supplied by Presenter
Copilot. The supported Codex App Server interface may also expose fixed
Presenter-owned policy/protocol metadata and bounded built-in harness
capabilities. Those capabilities are acceptable only while they cannot access
user files, project files, credentials, inherited instructions, environment
data, or other non-approved state. See the E10 containment boundary below and
[provider evidence](../PROVIDERS.md#e10-chatgpt-managed-codex).

### Full Context Cloud

Explicit opt-in only. M8 deliberately uses the same conservative selected
context packet even when this setting is selected; it does not implement
full-corpus upload. UI must not switch to it automatically on provider error.

## 6. Secrets

- use OS credential storage for provider secrets where possible;
- M9's OpenAI adapter resolves the user-scoped Windows Credential Manager entry
  `Presenter Copilot/OpenAI` inside core first, with `OPENAI_API_KEY` as an
  explicit development/bootstrap fallback; SQLite persists only safe
  `credential_source` metadata;
- never store API keys or OAuth refresh tokens in project DB/logs;
- never expose secrets to renderer context;
- never accept plaintext provider secrets through renderer IPC;
- official provider auth only;
- E10 Codex uses documented App Server ChatGPT-managed authentication; Presenter never reads, copies, logs, or returns Codex/ChatGPT auth files, tokens, OAuth state, or account identifiers to the renderer;
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
its body is not stored in ProviderRun manifests. Presenter Copilot never asks a
provider to reveal chain-of-thought and does not request provider tools. If an
official provider harness exposes unavoidable built-in capabilities, they must
satisfy the same containment boundary as E10: no capability may reach user,
project, credential, environment, or filesystem state outside the approved
packet and Presenter-owned runtime state.

## 10. Provenance and hallucination controls

For live fact cues:

- prefer retrieval-only facts when possible;
- exact numbers require supporting evidence;
- AI inference must not masquerade as a source fact;
- low-confidence or conflicting evidence should produce a warning/ambiguity cue rather than a confident number;
- expanded provenance must be available.

M7 Live Assist keeps microphone capture, continuous ASR processing, and the
recent transcript window in the local core. Live retrieval always uses
`usage=live`. A remote provider receives only the bounded question/context
packet; private Live-enabled KnowledgeItems may be used by a local provider but
are excluded from remote context. Live microphone finals remain
unattributed (`unknown_audience`) and no voice or identity inference is added.
There is no automatic question segmentation.

## 11. Capture protection

HUD uses OS/Electron content-protection features where supported.

Rules:

- never claim invisibility/undetectability;
- show status if capture protection is unavailable;
- user can manually hide HUD before sharing;
- capture protection is defense-in-depth, not a legal/privacy guarantee.

The HUD is a separate isolated Electron window with a minimal preload. The
collapsed surface is click-through and can be hidden through a main-process
shortcut even when the core/provider is unavailable. The HUD displays the
actual Electron content-protection API state and does not claim invisible or
undetectable capture behavior.

## 12. Logging

Default logs may include:

- timestamps;
- event names;
- durations;
- error codes;
- model/provider IDs;
- non-sensitive counts/sizes.

M8 may also record ProviderRun task/provider IDs, bounded latency and token
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

The M8 provider disclosure also states that private KnowledgeItems, raw audio, and
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
- Codex residual harness capability attempts to read user/project/credential state outside Selected Context;
- deleted project remains in embedding cache;
- transcript maps one native speaker to wrong profile and user remaps it;
- remote provider response includes unsupported exact number;
- renderer tries to invoke non-allowlisted IPC method;
- core crashes while HUD is visible;
- content protection unavailable during screen share.

## 16. M8 provider resilience boundary

Teach, Challenge, and Live Assist use one core-owned provider execution
service. It rereads the current project `privacy_mode` and remote
acknowledgement immediately before a remote invocation. A `local_only` project
rejects a remote provider at that final guard without calling the provider;
the session does not silently fall back to another remote provider. Selected
Context Cloud and Full Context Cloud both send only the operation-specific
bounded context packet. Private KnowledgeItems, raw audio, full documents, and
the full corpus never enter remote context.

The service derives the metadata-only privacy manifest from the actual final
serialized payload. It validates manifest/entity parity and fails closed on a
private marker, credential/raw-media field, stale privacy policy, or malformed
packet. The manifest is committed to `ProviderRun` and emitted before the
provider call; the provider call never runs inside a SQLite transaction. It
also enforces a core-owned per-task context-class allowlist at that last-mile
boundary. Teach question generation cannot disclose audience context,
challenge intensity, conflicts, or prior-question context; Teach candidate
generation adds only its current prompt and user explanation. Challenge
question/follow-up/evaluation receive only their operation-specific selected
evidence, accepted audience, conflict, intensity, bounded prior, question, and
typed-answer classes. Live cue generation receives its current question and
selected evidence/conflicts/style context but no audience, challenge, or prior
context. Any non-empty disallowed class is rejected before a `ProviderRun` is
created, even if a caller bypasses the context builder.

Provider health is process-local and renderer-safe. It exposes only
`ready`, `unconfigured`, `auth_failed`, `quota_exhausted`, `rate_limited`, and
`unavailable`, with stable error codes and retry guidance. Secrets remain in
the core environment; configure/status/history APIs expose metadata only.

Timeouts are bounded by the request latency budget. Logical cancellation and
Live Assist supersession discard ineligible output and finalize the run as
`cancelled`; provider-native transport cancellation is advertised only when
the adapter implements it. A provider timeout/auth/quota/unavailability
failure updates safe health state and uses the existing retrieval-only Live
fallback or Teach direct-save path. Challenge reports a stable actionable
unavailable error and creates no partial question/answer version.

`privacy.list_context_manifests` exposes bounded run metadata and sanitized
manifest history for project inspection. It never returns prompt text,
transcript excerpts, provider responses, raw error bodies, or credentials.

## 17. M9 release hardening boundary

Provider secrets are core-owned. On Windows, the OpenAI credential is resolved
from the per-user Windows Credential Manager target `Presenter Copilot/OpenAI`
before the explicitly detected environment fallback. Renderer IPC accepts no
credential value; the save action asks the core to persist its already detected
environment credential, and status/remove operations return metadata only.
Reset removes the app-owned stored credential but cannot erase an environment
variable owned by the launching process.

Core logs are structured JSONL records with an allowlisted event name and
bounded scalar fields. They do not include source text, transcript text, raw
provider errors, filesystem paths, prompts, or secret-like values. Diagnostic
preview and ZIP export use the same safe projection and are initiated through
the native main-process save dialog; the renderer supplies only an optional
bounded section list, never an output path or archive contents.

The packaged desktop application resolves only the bundled frozen sidecar
under Electron resources. Packaged mode does not fall back to system Python or
developer paths. The sidecar uses protocol-only stdout, minimized inherited
environment, hidden Windows process startup, and bounded restart/reconcile
behavior. Model preparation is an explicit user action and model caches are
not included in the installer or removed by app reset unless the user selects
that destructive option.

M9 deletion tests verify that a deleted project cannot be queried through a
warm retrieval mapping or cache, while another project's data and shared model
cache remain intact. Archive validation rejects traversal, absolute/drive
paths, control characters, duplicate normalized names, external links, and
overlong member names before extraction.

## 18. E10 Codex containment boundary

E10 uses a Presenter-owned official Codex App Server as an optional remote
reasoning provider. The security invariant is containment, not zero
model-visible tools. A built-in harness capability is permitted only when the
supported pinned runtime/model combination has evidence that the capability
cannot reach user files, project files, credentials, inherited instructions,
environment data, or any other non-approved state.

Core launches Codex with a fresh disposable `CODEX_HOME`, empty cwd, minimal
environment, no Presenter project path, disabled project-doc/instruction/tool/
web/network/MCP/app/plugin discovery surfaces, fresh ephemeral threads and a
fixed Presenter policy. The actual project-derived input still enters through
`ProviderExecutionService`, so Local Only, remote acknowledgement, Selected
Context manifests, private-item exclusion, task-class allowlists, validation,
timeouts and cancellation remain authoritative.

The tested Codex runtimes expose residual internal `skills.list` /
`skills.read`. E10 does not claim exhaustive pre-send enumeration of every
internal authenticated-thread tool. Instead, support is version/model-scoped;
forced adversarial containment tests exercise the residual surface against
planted user-home, project, credential and inherited-instruction canaries.
Unexpected material config/instruction drift, server-initiated authority or
observable sensitive capabilities fail closed. Any newly discovered ability to
reach outside Presenter-owned state is a containment failure and disables the
provider until revalidated. See [PROVIDERS.md](../PROVIDERS.md#e10-chatgpt-managed-codex) for the exact tested versions, evidence and known opaque-harness limitation.