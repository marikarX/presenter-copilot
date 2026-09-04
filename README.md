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

The installed Windows application does not require Python, Node.js, pnpm, uv,
Git, or this repository. Development uses the Python sidecar from `core/.venv`;
release packaging freezes that sidecar under the Electron resources directory.

Milestones 1–8 add the local project vault flow: create/open a project, import
PPTX/PDF/TXT/Markdown and explicitly authorized VTT/SRT/named-TXT/structured
JSON transcript sources through the native file picker, inspect bounded
slide/page/section/transcript previews with provenance, re-index from the
stored snapshot, delete sources or whole projects, inspect local hybrid
semantic retrieval, use typed Teach/Speaker Profile, review a project-local
Audience Model, rehearse with Challenge and Run, and use the isolated Live
Assist HUD. M3 supports project-local sessions, confirmed user knowledge,
explicit style-evidence promotion, and an optional bounded OpenAI Responses
call. M4 audience extraction is deterministic and local; it never sends
transcript content to a provider. M8 adds bounded Selected Context Cloud
routing, provider health, cancellation, and retrieval-only fallback. The
normal data root is
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
pnpm test:provider-real        # opt-in synthetic OpenAI acceptance; key required
pnpm test:m9                   # deletion, security, recovery, and secret-boundary tests
pnpm test:privacy-network      # Local Only network-isolation regression
pnpm test:e2e:release          # deterministic E2E-01 through E2E-08 runner
pnpm benchmark:release         # metadata-only aggregate release benchmark
pnpm build:sidecar             # frozen one-folder Windows sidecar
pnpm package:win               # Electron app plus unsigned per-user NSIS installer
pnpm test:packaged             # bundled app/sidecar hello-health-shutdown smoke
pnpm test:install-smoke        # installer artifact/readiness report; manual install remains required
```

Model preparation and the explicitly opt-in real-provider acceptance are the
only commands above that may use the network. Normal startup, source indexing,
retrieval, M4 audience extraction, and fake-provider tests use local-only
behavior and never download a model or call a provider implicitly. M4 does not
include Teams/Webex-specific export connectors, audio/video, diarization, or
Challenge mode. See
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the boundary and core-only
commands.

Provider credentials are resolved inside the core process. On Windows, the
user-scoped Credential Manager entry `Presenter Copilot/OpenAI` is preferred;
`OPENAI_API_KEY` remains a development/bootstrap fallback. The renderer can
ask the core to save a detected environment credential or remove the stored
credential, but it never submits or receives plaintext secrets. SQLite,
ProviderRun manifests, logs, and diagnostics contain metadata only.

`local_only` is a hard no-content-network mode. `selected_context_cloud` may
send only the bounded, core-built context manifest permitted by the existing
privacy policy to an enabled provider; it never grants the renderer provider
or credential authority. Model preparation is a separate explicit action and
is the only normal path allowed to download approved local model artifacts.

The M9 release controls expose explicit model preparation/removal, safe
diagnostic preview/export, and destructive Reset Local Data confirmation.
Reset removes projects, settings, app metadata, logs, diagnostics, and stored
credentials; model caches are retained unless the separate removal option is
selected. Diagnostic ZIPs are metadata-only and are written through the
Electron main-process native save dialog.

To build the Windows release, run `pnpm package:win`. The unsigned installer
is written to `artifacts/installer/Presenter-Copilot-0.1.0-x64-setup.exe` and
the unpacked app is placed under `artifacts/installer/win-unpacked/`.
`pnpm test:packaged` uses a disposable data root and removes Python-related
development overrides. `pnpm test:install-smoke` reports whether the artifact
exists but deliberately does not install, uninstall, or delete data on the
developer machine; use [`docs/MVP/M9_CLEAN_MACHINE_CHECKLIST.md`](docs/MVP/M9_CLEAN_MACHINE_CHECKLIST.md)
for that manual gate.

Known limitations: Windows 11 is the reference platform; local models require
explicit bootstrap; automatic question segmentation, Teams/Webex connectors,
biometric speaker/face recognition, and mobile/cloud accounts are not part of
this MVP. Microphone capture protection is best effort. Real CPU/RTX model
benchmarks, physical microphone recognition quality, clean-machine
install/uninstall, external capture behavior, and the five-presenter
qualitative study require separate evidence and are not implied by
deterministic tests or a successful package build.

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

Milestones 0–8 are based on the merged MVP architecture. The current branch
contains the Milestone 9 release-hardening implementation: deletion/cache
purge, OS-backed credential handling, safe logs/diagnostics, security checks,
frozen-sidecar packaging, explicit model controls, restart recovery, and
metadata-only release gates. M02 clean-machine evidence and the real hardware
and qualitative acceptance gates remain separate review items until run.

## License

Presenter Copilot is licensed under the [Apache License 2.0](LICENSE). Third-party models, SDKs, APIs, datasets, and dependencies remain subject to their own licenses and terms.

## Working positioning

> A private, local-first AI copilot for high-stakes presentations.

`Presenter Copilot` is a working project title, not a cleared public brand. Public naming should be screened across search engines, GitHub, app stores, domains, competitors, and trademarks before launch.
