# Milestone 9 Release Checklist

This checklist is the evidence contract for Deletion, Security, Packaging,
and Performance. Every result must name the exact commit SHA and distinguish
verified, unavailable, and manual evidence.

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

## Security/deletion review

- [ ] `source.delete`, `session.delete`, `project.delete`, Audience/Speaker
      deletion, and full local reset were tested with confirmation gates.
- [ ] Project vaults, SQLite rows, retrieval mappings, and warm model/cache
      references are absent after project deletion.
- [ ] Full reset removes app-owned state and stored credentials; model caches
      are retained unless the explicit destructive option is selected.
- [ ] No credential, raw content, filesystem path, prompt, raw provider error,
      or raw child-process output appears in logs, diagnostics, SQLite,
      renderer payloads, manifests, or packaged metadata.
- [ ] Archive traversal, absolute/drive names, control characters, duplicate
      normalized names, external links, and overlong names are rejected before
      extraction.
- [ ] Renderer/preload allowlists expose only the intended bounded methods;
      native file and diagnostic save paths stay in Electron main.

## Packaging/manual gates

- [ ] The installer is unsigned, per-user, and allows an explicit directory.
- [ ] Uninstall removes the application but retains user data.
- [ ] Reinstall can reopen retained user data without Python, uv, repository,
      or developer environment paths.
- [ ] A clean Windows VM or fresh standard-user profile passes
      [`M9_CLEAN_MACHINE_CHECKLIST.md`](M9_CLEAN_MACHINE_CHECKLIST.md).

The repository scripts do not install, uninstall, or delete data on the
developer machine. A missing installer or an unrun clean profile is
`unavailable`/`manual_required`, not a pass.

## Performance evidence

- [ ] `benchmark:release` report is attached or retained for the exact SHA.
- [ ] CPU-only real-model benchmark is run, or marked unavailable with the
      missing model/tool evidence.
- [ ] RTX reference benchmark is run, or marked unavailable with the missing
      model/driver/tool evidence.
- [ ] Cold model load, warm retrieval, ASR partial/final, cue latency, and
      idle/active resource observations are reported without source content.

Do not claim real ASR, provider, GPU, clean-machine, or external screen-share
acceptance from deterministic adapters, metadata-only reports, or local build
success.
