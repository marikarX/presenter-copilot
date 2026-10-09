# Changelog

All notable changes to Presenter Copilot will be documented in this file.

The project intends to follow [Semantic Versioning](https://semver.org/) once versioned releases begin.

## Unreleased

### Changed

- Change the license for repository-owned code and documentation from
  Apache-2.0 to MIT. Existing Apache-2.0 permissions granted for earlier
  versions remain in effect.

### Added

- Allow text replacement across direct runs only when their complete run
  formatting matches; mixed-style multi-run shapes remain read-only. The new
  Core route preserves the legacy single-run route.
- Presentation Workspace research preview: verified local PPTX preview and
  structural inventory, Core-validated single-run and uniform multi-run text
  edits, plus direct bold,
  italic, font-size, and solid-color formatting across every run in a supported
  plain paragraph, left/center/right/justified paragraph alignment, bounded
  left indentation from 0 to 144 points, signed first-line/hanging indentation
  from -144 to 144 points, whole-point line spacing from 1 to 144 points, and
  disc, hollow-circle, square, or dash bullet styles, no-bullet formatting, or
  Arabic-period numbering for simple paragraphs, plus before/after spacing
  from 0 to 144 points, simple
  text-box creation,
  immutable revision history with restore and branch-aware undo/redo controls,
  and current/original export. User research, representative compatibility,
  visual fidelity, and PowerPoint-open checks remain release gates.
- Presentation Workspace can add a blank slide after the current slide using
  the layout from it or another slide in the current revision, with no
  inherited slide content, notes, or media relationships.
- Presentation Workspace can apply a layout already used by another slide to
  the selected slide. Core changes only the layout relationship, verifies the
  slide content remains intact, and records the change in revision history.
- Presentation Workspace can crop a simple embedded picture inside its
  existing frame, preserving its image and slide relationships in a new
  validated, immutable revision.
- Presentation Workspace can replace a simple picture with a validated PNG or
  JPEG up to 4 MiB, adding private media while preserving shared image parts,
  the picture frame, and crop in a new immutable revision.
- Presentation Workspace can add a validated PNG or JPEG as a new picture with
  user-adjustable, slide-bounded geometry and optional alternative text. Core
  adds one private media part and relationship, validates the new object and
  untouched package parts, then commits a new immutable revision.
- Presentation Workspace can save and open the verified current revision with
  the operating system's default presentation app. This opens the PPTX for
  native review; it does not export PDF.
- Presentation Workspace can create a bounded rectangle or ellipse with
  explicit geometry and solid RGB fill/outline colors. Core assigns a stable
  object identity, rewrites only the selected slide, and validates styles,
  geometry, inventory, and untouched package parts before committing a new
  immutable revision.
- Typed fast decisions for a user-triggered slide-purpose suggestion using
  Jev via OpenRouter, OpenAI Responses Fast or Ultrafast, locally installed
  Nimble/Tev1 through Ollama, a configured local structured-output model, or
  ChatGPT plan usage through Sign in with ChatGPT. The plan route has isolated
  account credentials, shared-limit and usage-settings disclosures, and its
  own sign-in flow. Core applies project privacy, enforces provider choice
  limits, records content-free run manifests, and requires user review;
  semantic evaluation and live account acceptance remain open.
- Presentation Workspace can request a review-only rewrite of one supported
  paragraph using the selected reasoning provider. Core sends only the
  selected text and instruction, binds the proposal to the current revision,
  and returns it to the existing preview/save flow; the provider cannot apply
  an edit directly.
- Generated multi-resolution product icon applied to Windows executable
  resources; release code signing remains open until a production identity is
  configured and verified.
- Routine CI/local Windows packaging stays unsigned. The separate
  `pnpm package:win:release` command enables signing and enforces successful
  Authenticode signing; signing credentials belong only in the protected
  release environment.
- Milestone 9 release hardening: explicit model status/prepare/remove controls,
  core-owned Windows Credential Manager integration with safe development
  fallback, allowlisted structured logs, previewable metadata-only diagnostic
  ZIPs, full local-data reset, and warm-cache project purge barriers.
- Frozen one-folder Windows Python sidecar packaging, separate unsigned
  routine and forced-signed release NSIS build paths, deterministic packaged
  smoke, release E2E-01 to E2E-08 reporting, and metadata-only aggregate
  performance benchmarking.
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
