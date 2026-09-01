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
