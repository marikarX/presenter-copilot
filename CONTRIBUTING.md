# Contributing

Thanks for your interest in Presenter Copilot.

The project is currently pre-1.0 and architecture is still evolving. Contributions are welcome, but large implementation changes should be discussed before substantial work begins so effort does not get stranded by an architectural change.

## Ways to contribute

- report reproducible bugs;
- improve documentation;
- propose product or UX improvements;
- add tests and benchmarks;
- improve local ASR, retrieval, latency, privacy, or model-provider integrations;
- contribute accessibility improvements;
- validate behavior on additional operating systems and hardware.

## Before opening a pull request

1. Search existing issues and pull requests.
2. For non-trivial changes, open an issue describing the problem, proposed approach, and alternatives considered.
3. Keep changes focused. Avoid combining unrelated refactors with functional changes.
4. Add or update tests when behavior changes.
5. Update relevant documentation when configuration, architecture, privacy behavior, or user-visible behavior changes.
6. Do not commit secrets, credentials, private decks, recordings, transcripts, or proprietary model files.

## Development principles

Contributions should preserve the project's core principles:

- local-first processing where practical;
- cloud use must be explicit and understandable;
- minimal, non-distracting presenter cues rather than generated scripts;
- source-grounded answers for important claims;
- provider-pluggable architecture;
- no stealth-cheating positioning;
- privacy and security treated as product requirements.

## Pull requests

A good pull request should include:

- what problem it solves;
- what changed;
- how it was tested;
- privacy/security implications, if any;
- screenshots or recordings for meaningful UI changes, using non-sensitive sample data only.

## AI-assisted contributions

AI-assisted code and documentation are allowed. Contributors remain responsible for correctness, licensing, security, tests, and reviewability of everything they submit. Do not submit generated code you cannot explain or validate.

## Licensing

By submitting a contribution, you agree that it may be distributed under the repository's Apache License 2.0.

## Conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
