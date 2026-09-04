# Presenter Copilot 0.1.0 — M9 release-hardening draft

## Included

- Project, session, source, Audience, Speaker, cache, mapping, and local-state
  deletion paths with explicit reset confirmation.
- Core-owned Windows Credential Manager integration with renderer-safe status,
  save-detected, remove, and reset behavior.
- Structured allowlisted logs and previewable metadata-only diagnostic ZIPs.
- Archive extraction hardening for traversal, malformed names, duplicate
  normalized members, and external links.
- Frozen one-folder Python sidecar packaging, per-user NSIS installer config,
  deterministic packaged smoke, and bounded sidecar restart/reconciliation.
- Explicit model status/prepare/remove controls with no surprise launch
  downloads.
- Deterministic E2E-01 through E2E-08 runner and aggregate metadata-only release
  benchmark reporter.

## Evidence boundaries

This draft does not claim a clean-machine install, real-model CPU/RTX
benchmark, physical microphone recognition quality, external screen-capture
behavior, or live provider acceptance unless those results are attached for
the exact release SHA. The installer is unsigned. The release remains subject
to the manual clean-machine and architecture review gates in the M9 checklist.
