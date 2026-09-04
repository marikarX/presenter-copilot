# MVP Release Baseline

Date: 2026-09-04

This document is the authoritative release-closure baseline for the first
pre-1.0 Presenter Copilot MVP. It records an explicit product-owner scope
decision made after the M9 implementation and acceptance campaign.

Where this document conflicts with older release-gate wording in
`TEST_PLAN.md`, `IMPLEMENTATION_PLAN.md`, `M9_RELEASE_CHECKLIST.md`, or
`BACKLOG.md`, this release baseline controls. Historical milestone test
requirements remain useful validation guidance; this document changes which
items block the first MVP merge/release.

## Approved release code baseline

The reviewed release code baseline is:

`fb8841dca6505004a5ee08970bfbf1d32f396a37`

That SHA contains the final packaged-shutdown correction. Hosted Windows CI and
Trusted Local CI passed on that exact code SHA. Subsequent documentation-only
commits that implement this release rebaseline do not change the approved code
surface.

## Required MVP merge gates

The first MVP may merge when all of the following are true:

- deterministic P0 unit/integration and E2E-01 through E2E-08 coverage passes;
- Local Only network isolation passes;
- project deletion/security gates pass with no open critical security issue;
- no known cue path fabricates unsupported exact numeric facts;
- Windows package build and packaged sidecar/shutdown smoke pass;
- one clean-machine/fresh-profile install, launch, close, uninstall, reinstall,
  and retained-data smoke passes;
- a real Windows microphone produces visible local transcription through the
  shipped ASR path;
- the current MVP physical HUD path is usable for push-to-assist/show-hide and
  grounded cue display;
- the reviewed code surface has no unresolved architecture blocker.

## Accepted evidence for this release

- M02 clean-machine installation: **PASS**.
- Physical microphone/local ASR: **PASS**; microphone capture produced visible
  transcription.
- Physical HUD: **PASS for the current MVP UI**; the interaction will be
  re-tested after the planned visual/UX redesign.
- Security/deletion: **PASS** on the approved release code baseline.
- Hosted Windows CI: **PASS** on the approved release code baseline.
- Trusted Local CI: **PASS** on the approved release code baseline.
- Package and packaged sidecar/shutdown smoke: **PASS** on the approved release
  code baseline.

## Deferred non-blocking validation / technical debt

The following items remain valuable, but they do not block the first MVP merge
or release:

- M06 CPU-only reference-hardware benchmark;
- M07 RTX reference benchmark and Windows CUDA/cuBLAS runtime repair;
- authorized real OpenAI API-provider acceptance when a user-owned credential
  is available;
- five-presenter/deck qualitative usability study;
- independent external screen-capture exclusion testing;
- physical HUD re-test after the planned sleek UI/UX implementation.

These items must not be represented as completed. They remain open post-MVP
validation/technical-debt work.

## ChatGPT-authenticated inference

A high-priority post-MVP provider investigation is **ChatGPT-authenticated
inference**, not identity-only sign-in.

Goal:

- allow a user to authenticate through an officially supported OpenAI/ChatGPT
  or Codex mechanism and, where OpenAI explicitly supports it, use that
  authenticated entitlement for Presenter Copilot reasoning/inference;
- preserve the existing `ReasoningProvider` / `ProviderExecutionService`
  privacy boundary and Selected Context manifest rules;
- keep Local Only behavior unchanged;
- do not scrape, copy, or reuse private ChatGPT/Codex tokens through an
  undocumented mechanism;
- retain the current user-owned API-key provider as a fallback unless and until
  an officially supported ChatGPT-authenticated inference path is validated.

This is a provider-integration/product-distribution feature and is not required
for the first MVP merge.

## Change rule

If any remaining acceptance or post-MVP validation uncovers a genuine code
defect before merge, the release code baseline changes and requires a focused
review plus exact-head CI on the new code SHA. Documentation-only release
rebaseline commits do not invalidate the approved `fb8841d...` code review.
