# Changelog

All notable changes to Presenter Copilot will be documented in this file.

The project intends to follow [Semantic Versioning](https://semver.org/) once versioned releases begin.

## Unreleased

### Added

- Milestone 9 release hardening: explicit model status/prepare/remove controls,
  core-owned Windows Credential Manager integration with safe development
  fallback, allowlisted structured logs, previewable metadata-only diagnostic
  ZIPs, full local-data reset, and warm-cache project purge barriers.
- Frozen one-folder Windows Python sidecar packaging, unsigned per-user NSIS
  installer configuration, deterministic packaged smoke, release E2E-01 to
  E2E-08 reporting, and metadata-only aggregate performance benchmarking.
- Malicious archive preflight for unsafe names, duplicate normalized members,
  links, entry counts, and expanded-size bounds, plus renderer/main/preload
  allowlist and packaged-environment regressions.
- Milestone 4 transcript and Audience Model vertical slice: bounded VTT, SRT,
  named-TXT, and structured-JSON adapters; timestamped/native-label
  SourceUnits; explicit unresolved speaker mapping; project-local
  AudienceProfile CRUD; provisional evidence-backed observation candidates;
  review/edit/accept/reject lifecycle; stale attribution invalidation; and
  restart/source/project deletion coverage.
- M4 transcript authorization disclosure, transcript-specific provenance and
  retrieval metadata, deterministic local observable-pattern extraction, and
  sensitive/hidden-trait policy enforcement. Audience extraction makes no
  remote provider call.
- Milestone 3 typed Teach and Speaker Profile vertical slice: project-local
  sessions, durable user-statement provenance, provisional KnowledgeItem
  candidates, explicit confirmation/edit/reject controls, preferred/private/
  live/rehearsal retrieval flags, and explicit global style-evidence approval.
- Generic local retrieval for confirmed KnowledgeItems with deterministic
  preferred-user-explanation boosts, usage filters, immediate lexical access,
  and best-effort semantic-generation synchronization.
- Provider-neutral Teach routing, bounded structured context manifests,
  deterministic fake-provider coverage, and an opt-in official OpenAI Responses
  adapter using `OPENAI_API_KEY`, strict JSON schemas, no tools, `store=false`,
  and bounded timeouts.
- Milestone 2 local FastEmbed/BGE semantic retrieval with a replaceable
  deterministic test adapter, generation-based NumPy matrices, hybrid lexical
  ranking, current-slide boosts, exact-fact conflict detection, and a
  development retrieval inspector.
- Milestone 1 local project vault with transactional app/project SQLite
  migrations and UUID-keyed project lifecycle.
- Project-local SHA-256 source snapshots, bounded PDF/PPTX/TXT/Markdown
  ingestion, slide/page/section provenance, deterministic chunking, and
  lexical exact-text retrieval.
- Source preview, re-index, delete, project delete, restart recovery, native
  Electron import picker, progress events, and the canonical synthetic
  22-slide/four-page ingestion fixture.

- Initial product and architecture documentation.
- Local-first privacy model.
- Competitive analysis and roadmap.
- Apache-2.0 license.
- Community, contribution, security, and support policies.
- Milestone 0 Electron/React/TypeScript desktop scaffold with a Python NDJSON sidecar.
- Versioned core handshake, health, shutdown, request correlation, events, and cross-language contract fixtures.
- Synthetic deck fixture skeleton and Windows CI checks.

### Changed

- Mobile companion added to the product roadmap.

### Fixed

- Hardened Milestone 0 renderer sender/origin validation and sidecar process
  finalization across spawn errors, exits, closes, timeouts, and shutdown.
- Hardened restart recovery so automatic sidecar restart follows final `close`
  finalization, stale process-owned state is reconciled, and unexpected HUD
  state is cleared without creating an endless restart loop.

## 0.0.0

Repository planning baseline. No executable application has been released yet.
