# Security Policy

Presenter Copilot processes potentially sensitive presentation material, microphone audio, transcripts, local indexes, and optional authentication/model-provider credentials. Security reports are taken seriously.

## Supported versions

The project is pre-1.0. Until the first stable release, security fixes are applied to the current development branch and most recent release only.

## Reporting a vulnerability

Please do not disclose an exploitable vulnerability in a public issue.

Preferred reporting path:

1. Use GitHub Private Vulnerability Reporting / Security Advisories for this repository when available.
2. If private reporting is unavailable, open a minimal public issue stating that you need a private security contact. Do not include exploit details, secrets, private user data, or reproduction steps that would enable abuse.

A useful report should include:

- affected version or commit;
- operating system and environment;
- vulnerability class and impact;
- minimal reproduction steps;
- whether secrets, recordings, transcripts, decks, indexes, or authentication material may be exposed;
- any suggested mitigation.

## Security-sensitive areas

Extra care is required around:

- microphone and screen capture permissions;
- storage of recordings, transcripts, embeddings, and local indexes;
- authentication tokens and provider credentials;
- Codex/app-server or other remote-agent integrations;
- local HTTP/WebSocket listeners and mobile companion pairing;
- document parsing and archive extraction;
- model/plugin execution;
- update mechanisms;
- telemetry and crash reporting;
- screen-sharing/privacy boundaries for the presenter HUD.

## Project security principles

- Keep sensitive content local by default where practical.
- Never log secrets or authentication tokens.
- Minimize the context sent to remote models.
- Require explicit user control over cloud processing.
- Bind local services to loopback by default unless pairing requires otherwise.
- Authenticate and encrypt local-network companion connections.
- Treat imported documents as untrusted input.
- Do not execute embedded document content.
- Make deletion of recordings, transcripts, and indexes straightforward.

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) and [docs/PRIVACY.md](docs/PRIVACY.md).
