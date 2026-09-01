# Threat Model

Presenter Copilot may handle confidential decks, supporting documents, live microphone audio, transcripts, embeddings/indexes, presentation history, and optional model-provider authentication. Security and privacy are therefore part of the product architecture, not later hardening work.

## Assets to protect

- presentation files and supporting documents;
- live microphone audio;
- transcripts and rehearsal history;
- embeddings/vector indexes and cached retrieval context;
- audience/stakeholder profiles;
- model/API credentials and OAuth tokens;
- locally generated answer scaffolds;
- session metadata and analytics;
- mobile-companion pairing keys;
- user identity and configuration.

## Trust boundaries

### Local desktop process

Trusted to access files, microphone input, local indexes, and the private HUD. It should minimize privileges and avoid exposing sensitive local services.

### Imported documents

Untrusted input. PDFs, PPT/PPTX archives, images, URLs, and metadata can be malformed or malicious. Parsers must not execute embedded scripts/macros or arbitrary content.

### Local model/runtime

Potentially third-party code or weights. Model runtimes and plugins should be isolated from credentials and unnecessary filesystem access where practical.

### Remote model/provider

Anything sent across this boundary leaves the device and is subject to the provider's terms, retention, security, and data controls. Cloud transmission must match the selected privacy mode.

### Mobile companion

A separate device and network boundary. Pairing must be explicit, authenticated, revocable, and encrypted. The desktop should not expose an unauthenticated LAN endpoint.

### Meeting/screen-share environment

The HUD is intended to remain private, but operating-system capture behavior and meeting software can vary. The product must avoid promising invisibility and should provide a screen-share safety check.

## Primary threats

### 1. Accidental cloud disclosure

Risk: content intended to remain local is sent to a remote provider through a reasoning or telemetry path.

Mitigations:

- explicit privacy modes;
- centralized routing policy;
- selected-context cloud mode by default when remote reasoning is enabled;
- visible indicators when cloud processing is active;
- tests that assert routing behavior;
- no implicit provider fallback from local-only mode.

### 2. Credential theft

Risk: API keys/OAuth tokens are logged, stored insecurely, exposed to plugins, or copied into diagnostics.

Mitigations:

- OS credential/keychain storage where possible;
- provider-managed auth flows rather than manual token extraction;
- redact credentials from logs;
- least-privilege access;
- never persist credentials in project/session files.

### 3. Malicious document ingestion

Risk: crafted presentation/archive exploits parser bugs or causes resource exhaustion.

Mitigations:

- treat all documents as untrusted;
- disable macro/script execution;
- constrain decompression, file counts, dimensions, and parsing time;
- use maintained parsers;
- sandbox high-risk conversions where practical.

### 4. Prompt injection through source material

Risk: imported documents contain instructions designed to influence an LLM or exfiltrate data.

Mitigations:

- separate retrieved source text from system/tool instructions;
- treat document content strictly as data;
- restrict tool permissions;
- do not let retrieved text change privacy mode or provider configuration;
- require explicit user action for external side effects.

### 5. Local service exposure

Risk: HTTP/WebSocket endpoints used for UI/mobile pairing become reachable by other machines.

Mitigations:

- bind to loopback by default;
- authenticated pairing for LAN use;
- short-lived pairing codes/keys;
- encryption in transit;
- no sensitive unauthenticated endpoints;
- clear paired-device revocation.

### 6. Screen-share leakage

Risk: private cues appear in a shared screen or recording.

Mitigations:

- platform-specific capture exclusion where reliably supported;
- explicit pre-flight screen-share test;
- mobile second-screen option;
- fast hide shortcut;
- avoid claims of guaranteed undetectability.

### 7. Persistent sensitive data

Risk: transcripts, recordings, indexes, and caches remain after the user believes a project/session was deleted.

Mitigations:

- documented retention behavior;
- project-level delete action;
- purge derived indexes/caches with source deletion;
- configurable recording/transcript retention;
- avoid hidden cloud copies in local-only mode.

### 8. Hallucinated or misleading live cues

Risk: generated guidance is incorrect during a high-stakes presentation.

Mitigations:

- retrieval-first design;
- source references for factual cues;
- distinguish sourced facts from model suggestions;
- favor short scaffolds over authoritative prose;
- let users disable generative live answers and use retrieval-only mode.

## Out of scope for initial releases

Until explicitly designed and reviewed, do not assume support for:

- regulated clinical decision support;
- autonomous financial/legal decisions;
- covert recording that violates applicable law/policy;
- adversarial multi-user kiosk environments;
- executing arbitrary third-party plugins with unrestricted system access.

## Security review triggers

Revisit this threat model whenever the project adds:

- automatic updates;
- cloud accounts/sync;
- enterprise admin services;
- new OAuth/provider integrations;
- browser extensions;
- meeting-platform integrations;
- mobile pairing over the internet;
- plugin/tool execution;
- telemetry/crash upload;
- public sharing of presentations or sessions.
