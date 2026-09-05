# OpenAI Codex runtime attribution

Presenter Copilot's Windows installer bundles the unmodified official OpenAI Codex CLI **0.153.4** Windows x64 runtime for the E10 ChatGPT-managed Codex provider.

- Upstream source: https://github.com/openai/codex/tree/rust-v0.153.4
- Upstream release: https://github.com/openai/codex/releases/tag/rust-v0.153.4
- Bundled asset: `codex-x86_64-pc-windows-msvc.exe`
- Expected SHA-256: `444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b`

The binary is fetched from the pinned upstream release during the Presenter Copilot Windows build and is not committed to this repository. The build fails closed if its SHA-256 or reported version differs.

Codex is licensed under the Apache License 2.0. The upstream `LICENSE` and `NOTICE` files are included alongside the installed runtime attribution. Bundling Codex does not imply endorsement of Presenter Copilot by OpenAI.
