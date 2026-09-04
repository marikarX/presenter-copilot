# Privacy Model

## Principle

Presenter Copilot should minimize the amount of presentation data that leaves the user's device.

The default mental model is:

> continuous data stays local; remote models receive only the minimum context needed for an explicitly permitted reasoning task.

## Data classes

Potentially sensitive data includes:

- presentation files;
- supporting documents;
- microphone audio;
- transcripts;
- audience questions;
- customer names and pricing;
- financial information;
- unreleased product details;
- architecture diagrams;
- prior rehearsal history;
- generated answer suggestions;
- future immersive scenario definitions and participant mappings;
- future camera/XR-derived presenter-coaching signals.

## Privacy modes

### Local only

- no remote model calls;
- local ASR;
- local retrieval;
- local model reasoning;
- local storage.

This is the strongest privacy mode and should remain a first-class supported configuration.

### Selected-context cloud

- raw audio stays local;
- full source corpus stays local;
- local retrieval selects only relevant excerpts;
- the selected context and question may be sent to the configured remote reasoning provider;
- returned output is shown locally.

This should be the recommended hybrid mode.

### Full-context cloud

A user may deliberately permit broader remote context for higher-quality reasoning. The UI must make the boundary explicit and should never silently upgrade from a more restrictive privacy mode.

Full-context permission does not automatically authorize upload of raw camera frames, raw XR telemetry, room scans, or biometric-like sensor streams. Any such future capability requires explicit product design and disclosure.

## Authentication

For any provider integration:

- use official authentication mechanisms only;
- do not scrape browser sessions;
- do not extract or repurpose undocumented tokens;
- do not proxy user credentials through project-controlled servers unless a future enterprise design explicitly requires and secures it;
- keep provider authentication local where supported.

For Codex-style integrations, use the official supported app-server/SDK authentication surface and keep the integration optional.

## Data minimization

Remote prompts should prefer:

- the current question;
- the current slide;
- a small set of retrieved source excerpts;
- relevant audience/persona metadata;
- only the rehearsal history required for the task.

Do not send the entire presentation corpus just because it is available.

## Audio

Raw microphone audio is especially sensitive.

Default behavior should be:

- process audio locally;
- persist audio only if the user enables recording;
- permit transcript-only sessions;
- make retention/deletion controls obvious.

## Immersive rehearsal

Future immersive rehearsal must preserve the same local-first model.

Default rules:

- synthetic or role-based audience identities;
- real-person names, when legitimately present in an Audience Model, remain project-local context and must be labeled as simulated approximations;
- no photorealistic recreation of real people by default;
- no persistent face recognition or voiceprints;
- no emotion recognition or sensitive-trait inference;
- camera/XR signals, if introduced, should be processed locally and ephemerally where practical;
- persist derived coaching events rather than raw high-frequency sensor streams;
- renderer processes receive only bounded scene/reaction/question data required for display;
- cloud rendering, if ever introduced, is a new data boundary requiring separate review.

See [`docs/IMMERSIVE/PRIVACY_SAFETY.md`](IMMERSIVE/PRIVACY_SAFETY.md).

## Session storage

Users should be able to:

- delete one rehearsal/session;
- delete all project history;
- rebuild the local index;
- remove source documents;
- inspect which provider/backend was used;
- delete future immersive scenarios, runs, and derived simulation state.

## Source provenance

Generated answers should retain enough metadata to identify which source excerpts contributed to the answer. This improves both trust and deletion correctness.

Simulated audience behavior should likewise retain enough provenance to distinguish source-backed concerns, user-authored scenario assumptions, deterministic simulation rules, and model-generated interpretations.

## Enterprise direction

Potential future enterprise requirements:

- organization-controlled model policy;
- forced local-only mode;
- approved provider allowlists;
- data-retention policies;
- encryption-at-rest controls;
- managed keys;
- audit logging;
- SSO/device policy;
- disable recording;
- admin-defined document-sharing rules;
- policy controls for immersive scenarios and sensor usage.

These should not be required for the first individual prototype.

## Claims discipline

Do not market the product as "zero data leaves your device" unless the active configuration actually guarantees that.

Preferred language should distinguish clearly between:

- Local Only;
- Selected Context Cloud;
- Full Context Cloud.

The application should make the current mode visible during both rehearsal and live presentation use.

Immersive debriefs must not present simulated audience state as a psychological measurement or a prediction of exactly how a named real person will react.
