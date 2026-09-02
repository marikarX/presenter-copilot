# Changelog

All notable changes to Presenter Copilot will be documented in this file.

The project intends to follow [Semantic Versioning](https://semver.org/) once versioned releases begin.

## Unreleased

### Added

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

## 0.0.0

Repository planning baseline. No executable application has been released yet.
