# Milestone 9 Release Checklist

This checklist is the evidence contract for Deletion, Security, Packaging,
and Performance. Every result must name the exact commit SHA and distinguish
verified, unavailable, deferred, and manual evidence.

The dated first-MVP merge/release decision is authoritative in
[`RELEASE_BASELINE.md`](RELEASE_BASELINE.md). Historical benchmark and usability
requirements remain useful validation guidance but do not override that release
baseline.

## Automated gates

Run from the repository root on Windows with the pinned toolchain:

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

The release E2E runner covers E2E-01 through E2E-08 with synthetic fixtures,
deterministic adapters, bounded metadata-only output, and disposable storage.
The packaged smoke must start the bundled executable, complete its core
handshake and shutdown, and report no orphaned `presenter-core` process.

For the approved release code baseline `fb8841dca6505004a5ee08970bfbf1d32f396a37`,
Hosted Windows CI and Trusted Local CI passed, as did M9 15/15,
privacy/network 14/14, release E2E 8/8, package build, and packaged sidecar/
shutdown smoke.

## Security/deletion review

- [x] `source.delete`, `session.delete`, `project.delete`, Audience/Speaker
      deletion, and full local reset are covered by the accepted M9 regression
      gate.
- [x] Project vaults, SQLite rows, retrieval mappings, and warm model/cache
      references are covered by the accepted deletion/cache regression gate.
- [x] Full reset confirmation, credential cleanup semantics, and model-cache
      retention choice are covered by the accepted M9 regression gate.
- [x] Secret/log/diagnostic/SQLite safety is covered by the accepted privacy and
      M9 regression gates.
- [x] Archive traversal, unsafe names, duplicate normalized names, external
      links, and overlong names are covered by the accepted security tests.
- [x] Renderer/preload allowlists and native diagnostic save authority are
      covered by the accepted M9 regression gate.

## Packaging/manual gates

- [x] The installer is unsigned by design, per-user, and allows an explicit
      directory.
- [x] Uninstall removes the application but retains user data.
- [x] Reinstall can reopen retained user data without Python, uv, repository,
      or developer environment paths.
- [x] A clean Windows VM/fresh environment passed the M02 clean-machine
      installation lifecycle on 2026-09-04.

M02 is therefore **PASS** for the first MVP release baseline.

## Physical MVP acceptance

- [x] A real Windows microphone was opened through the shipped local capture
      path and produced visible transcription.
- [x] The current MVP HUD physical path was exercised successfully enough for
      first-MVP acceptance, including cue/show-hide behavior.

The HUD physical path must be re-tested after the planned visual/UX redesign.
Independent external screen-capture exclusion remains deferred and must not be
claimed as verified.

## Deferred performance/provider/usability evidence

The following are deliberately non-blocking for the first MVP release under
`RELEASE_BASELINE.md` and remain open technical-debt/validation work:

- [ ] M06 CPU-only real-model reference benchmark.
- [ ] M07 RTX reference benchmark after repairing/validating the Windows CUDA
      12/cuBLAS runtime.
- [ ] Authorized real OpenAI API-provider acceptance when a user-owned
      credential is available.
- [ ] Five-presenter/deck qualitative usability study.
- [ ] Independent external screen-capture exclusion validation.
- [ ] Physical HUD re-test after the sleek UI/UX implementation.

`benchmark:release` metadata-only evidence remains useful and is retained, but
it is not a substitute for M06/M07 real-hardware measurements. Likewise,
deterministic adapters must never be described as real provider, GPU, or
hardware acceptance.
