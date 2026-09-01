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

## 4. Speaker Profile boundary

The user may intentionally let the app learn their own speaking style.

P0 rules:

- profile belongs to the user;
- learned evidence is visible/removable;
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

No provider/network request is allowed from the content-processing path. Update checks/optional external links must be separable from session processing and disabled in the network-isolation test environment.

### Selected Context Cloud

Required invariant:

```text
raw audio         -> local only
full corpus       -> local only
retrieval         -> local
remote payload    -> question + minimum selected excerpts/context
```

The app records a context manifest before every remote call.

### Full Context Cloud

Explicit opt-in only. UI must not switch to it automatically on provider error.

## 6. Secrets

- use OS credential storage for provider secrets where possible;
- never store API keys or OAuth refresh tokens in project DB/logs;
- never expose secrets to renderer context;
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

Default logs must not include:

- raw audio;
- full transcript;
- full source excerpts;
- API keys/tokens;
- audience sensitive data;
- complete provider prompts.

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

## 14. UX disclosures

Before transcript/meeting import:

> Only analyze recordings or transcripts you are authorized to use. Local processing does not change your legal or organizational obligations.

Before remote reasoning is first enabled for a project:

> Selected excerpts and the current question may be sent to your configured AI provider. Raw meeting audio remains local in this mode.

Keep disclosures concise and contextual rather than requiring broad legal acceptance for every session.

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
