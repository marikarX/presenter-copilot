# Release Policy

Presenter Copilot is pre-1.0. Releases should optimize for reproducibility, clear privacy/security changes, and easy rollback rather than a high release cadence.

## Versioning

The project intends to use Semantic Versioning:

- `0.x.y` while major product and architecture changes are expected;
- `1.0.0` only after core storage, provider, privacy, and compatibility contracts are intentionally stabilized.

Before 1.0, breaking changes are allowed but must be called out in release notes and `CHANGELOG.md`.

## Release checklist

Before tagging a release:

1. Ensure automated tests pass on supported platforms.
2. Verify a clean install/build from documented prerequisites.
3. Review dependency and model-license changes.
4. Review any change involving microphone, screen capture, networking, credentials, telemetry, cloud routing, retention, or deletion.
5. Confirm Local Only mode still produces no unintended remote model traffic.
6. Update `CHANGELOG.md`.
7. Document known limitations and migration steps.
8. Build release artifacts from a reproducible CI workflow where practical.
9. Generate checksums/signatures for downloadable binaries once binary distribution begins.
10. Smoke-test install, first-run permissions, rehearsal, HUD, and uninstall/data-removal behavior.

## M9 Windows release gate

The current pre-1.0 Windows release pipeline is intentionally split between
deterministic repository gates and manual environment evidence. From the
repository root, run the pinned setup and the following commands on the exact
candidate commit:

```text
pnpm setup
pnpm check
pnpm test:privacy-network
pnpm test:m9
pnpm test:e2e:release
pnpm benchmark:release
pnpm package:win
pnpm test:packaged
pnpm test:install-smoke
git diff --check
```

`pnpm build:sidecar` creates the one-folder frozen Python sidecar used by
`pnpm package:win`; the resulting installer is unsigned and per-user. The
packaged application must launch the bundled sidecar without system Python,
complete hello/health/shutdown, and leave no sidecar process. The installer
smoke command is read-only and reports `manual_required` until a disposable
Windows profile or VM has actually installed, started, uninstalled, and
reinstalled the artifact. Ordinary uninstall must not silently remove user
data; Reset Local Data is the explicit in-app data-removal operation.

Keep Hosted Windows CI and Trusted Local CI as separate exact-SHA evidence.
They do not substitute for a clean-machine install, real CPU/RTX model
benchmark, physical microphone test, external capture test, or the
five-presenter qualitative study. Record missing hardware/provider/model
evidence as unavailable or pending rather than treating deterministic fakes or
package success as those acceptance results.

## Release notes

Every release note should distinguish:

- user-visible features;
- breaking changes;
- security/privacy changes;
- model/provider changes;
- dependency/runtime changes;
- known issues.

## Security releases

For exploitable vulnerabilities, coordinate disclosure under `SECURITY.md`. Do not publish exploit-enabling details before users have a reasonable opportunity to update.

## Stable release criteria

Do not call a release stable merely because the UI looks complete. A 1.0 candidate should have:

- documented storage and deletion semantics;
- defined local/cloud routing behavior;
- tested provider fallback;
- measurable live-cue latency;
- reliable screen-share/HUD behavior on supported platforms;
- documented upgrade compatibility;
- a reviewed threat model;
- a dependency/update strategy.
