# Presenter Copilot

**Working title. Private repository.**

Presenter Copilot is a local-first AI copilot for high-stakes presentations. It learns a presentation and its supporting material, learns how the presenter naturally explains the topic, rehearses them against realistic audiences, and can surface minimal private cues near the webcam during the real presentation.

The product is intentionally **not** an AI teleprompter. The core loop is:

**Prepare -> Teach -> Rehearse -> Defend -> Present -> Learn**

## Product model

Presenter Copilot combines three distinct context layers:

- **Speaker Profile** — user-approved speaking style, preferred explanations, vocabulary, analogies, and coaching preferences.
- **Project Brain** — deck, supporting sources, user explanations, decisions, evidence, rehearsals, questions, and answers for one presentation/project.
- **Audience Model** — project-local roles, attributed prior questions, recurring observable concerns/question patterns, and user notes.

The default style policy is **Preserve my voice**: prefer the user's own strong explanations over generic generated prose.

## Core modes

- **Teach** — enrich the project through voice/text conversation in the user's own words.
- **Challenge** — rehearse against grounded audience questions and follow-ups.
- **Run** — uninterrupted presentation rehearsal with post-run debrief.
- **Live Assist** — private webcam-adjacent source-grounded cues with an explicit push-to-assist fallback.

## Design principles

- **Local first.** Audio, transcript, retrieval, and presentation state stay on-device whenever practical.
- **Cloud optional.** Remote reasoning is an escalation path, not a requirement for every utterance.
- **Minimal HUD.** Prefer memory cues and answer scaffolds over generated paragraphs.
- **Preserve the presenter.** Improve clarity/preparation without replacing the user's voice.
- **Provider-pluggable.** Support local models, user-supplied APIs, and officially supported agent backends where permitted.
- **Source-grounded.** Important facts remain traceable to slides, documents, user explanations, transcripts, or practiced answers.
- **Audience evidence, not profiling.** Use observed questions/interaction patterns; do not infer hidden emotions, sensitive traits, or persistent biometric identity.
- **No stealth-cheating positioning.** This is a private presenter view, not an undetectable answer machine.

## Initial architecture

```text
Speaker Profile -----------------------+
                                       |
Deck / docs / transcripts -> Project Brain ----+
                                       |        |
Audience Model ------------------------+        |
                                                v
Mic -> Local ASR -> transcript -> Context / retrieval
                                                |
                                        Reasoning router
                                         /           \
                                   local/retrieval   optional remote
                                         \           /
                                          +---------+
                                               |
                                               v
                                      Webcam-adjacent HUD
```

The frozen MVP runtime uses Electron/React/TypeScript plus a local Python core sidecar, communicating over child-process stdio. See the developer package below.

## Developer start here

The implementation contract is [`docs/MVP/README.md`](docs/MVP/README.md).

Read in this order:

1. [MVP specification](docs/MVP/SPEC.md)
2. [MVP UX flows](docs/MVP/UX_FLOWS.md)
3. [MVP architecture](docs/MVP/ARCHITECTURE.md)
4. [MVP data model](docs/MVP/DATA_MODEL.md)
5. [MVP interfaces/contracts](docs/MVP/INTERFACES.md)
6. [MVP privacy & safety](docs/MVP/PRIVACY_SAFETY.md)
7. [MVP test plan](docs/MVP/TEST_PLAN.md)
8. [MVP implementation plan](docs/MVP/IMPLEMENTATION_PLAN.md)
9. [MVP backlog](docs/MVP/BACKLOG.md)

## Run the desktop development build

Prerequisites: Node.js 22.12+, pnpm 11+, Python 3.13+, and uv. From the
repository root:

```text
pnpm setup
pnpm dev
```

The first setup downloads the pinned Electron development runtime and the
locked Python parser dependencies when they are not already present. `pnpm
dev` opens the desktop shell, which starts the Python core sidecar
automatically. The shell should show `CORE READY`, protocol `1`, core version
`0.1.0`, and health `OK`.

Milestones 1 and 2 add the local project vault flow: create/open a project,
import PPTX/PDF/TXT/Markdown sources through the native file picker, inspect
bounded slide/page/section previews with provenance, re-index from the stored
snapshot, delete sources or whole projects, and inspect local hybrid semantic
retrieval. The normal data root is
`%LOCALAPPDATA%\PresenterCopilot` on Windows. Tests use a temporary root; a
controlled run can set `PRESENTER_COPILOT_DATA_ROOT` explicitly.

Useful root commands:

```text
pnpm build          # compile the Electron main/preload and renderer bundles
pnpm start          # open the last built desktop bundle
pnpm test           # TypeScript tests plus Python tests and real sidecar IPC
pnpm lint           # ESLint plus Ruff
pnpm typecheck      # TypeScript plus mypy
pnpm format:check   # Prettier plus Ruff format check
pnpm check          # formatting, lint, typecheck, and all tests
pnpm model:prepare:embeddings  # explicit, network-dependent model bootstrap
pnpm test:embedding-real       # real local FastEmbed acceptance; cache required
pnpm benchmark:retrieval       # reproducible 50k-vector local benchmark
```

Model preparation is the only command above that may use the network. Normal
startup, source indexing, and retrieval use local-files-only model loading and
never download a model implicitly. Milestone 2 intentionally does not include
ASR, model providers, sessions, or the real presentation HUD. See
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the boundary and core-only
commands.

## Broader documentation

### Product and architecture

- [Product definition](docs/PRODUCT.md)
- [Architecture principles](docs/ARCHITECTURE.md)
- [Privacy model](docs/PRIVACY.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Competition](docs/COMPETITION.md)
- [Roadmap](docs/ROADMAP.md)
- [Decision log](docs/DECISIONS.md)
- [Development guide](docs/DEVELOPMENT.md)
- [Release policy](docs/RELEASING.md)

### Project and community

- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Support](SUPPORT.md)
- [Governance](GOVERNANCE.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Licensing notes](docs/LICENSING.md)
- [Changelog](CHANGELOG.md)

## Repository status

Milestone 0 — repository scaffold — is merged into `main`. The current
implementation slice is Milestone 2 — local project vault, ingestion,
embeddings, and hybrid retrieval.

## License

Presenter Copilot is licensed under the [Apache License 2.0](LICENSE). Third-party models, SDKs, APIs, datasets, and dependencies remain subject to their own licenses and terms.

## Working positioning

> A private, local-first AI copilot for high-stakes presentations.

`Presenter Copilot` is a working project title, not a cleared public brand. Public naming should be screened across search engines, GitHub, app stores, domains, competitors, and trademarks before launch.
