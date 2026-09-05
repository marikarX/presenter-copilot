# Post-MVP reasoning providers

## E09: local OpenAI-compatible inference

Settings → Reasoning Providers accepts an endpoint/base URL and model name.
Use the server's API base, for example `http://127.0.0.1:11434/v1` or
`http://127.0.0.1:1234/v1`. Start and provision the server yourself. Presenter
Copilot does not install, download, or launch reasoning models. Compatibility
requires non-streaming `/chat/completions` with `response_format.json_schema`;
unsupported schemas, truncation, and tool calls fail closed. Ollama, LM Studio,
and vLLM installations must be checked individually; no real-backend acceptance
is claimed by the synthetic HTTP tests.

An optional `PRESENTER_LOCAL_API_KEY` is read only from the Core environment.
It is not accepted over IPC or stored in SQLite. It is independent of the
existing OpenAI API credential and Windows Credential Manager entry. This
increment does not create another durable secret or require a database migration.

`local_openai` remains a local provider. Its `leaves_machine` property separates
inference locality from transport privacy:

| Endpoint | Local Only | Other project modes |
| --- | --- | --- |
| Literal loopback or `localhost` | Allowed when explicitly selected | Allowed |
| RFC1918 IPv4 / IPv6 ULA | Blocked | Requires existing remote acknowledgement and manifests |
| Public IP, arbitrary DNS, link-local, unspecified, mapped IPv6 | Rejected | Rejected |

`localhost` is pinned to `127.0.0.1`; use `[::1]` for IPv6. Only HTTP and HTTPS
are accepted. Userinfo, query, fragment, control characters, escaped addresses,
scope IDs, and traversal segments are rejected. Core connects directly to the
validated numeric address, does not consult environment proxies, never follows
redirects, and uses normal certificate verification for HTTPS. The user must
configure a server that actually performs inference locally; the client cannot
detect whether a separately operated server forwards requests elsewhere.

`ProviderExecutionService` remains the content authority. It rereads project
privacy, validates the context-class allowlist, rejects private items for any
off-machine transport, records the manifest before transmission, validates the
result, and finalizes the run. Selection enables one provider at a time. Failure
never selects another provider, including when an OpenAI API key is available.
Existing task-specific retrieval/direct-save/unavailable behavior is retained.

The adapter caps output at 2,048 requested tokens and 65,536 response bytes,
then applies the existing task schemas and provenance checks. HTTP operations
have a total watchdog within the request budget; shutdown closes active sockets.
Logical cancellation uses the existing execution boundary and suppresses late
results; provider-native cancellation is not advertised. Health is initially
configured/unavailable (`PROVIDER_NOT_TESTED`), and a successful request marks
it reachable. Status is the last observed outcome, not a background probe.
The explicit Test button sends only a synthetic packet and can restore readiness.

## E10 investigation: supported auth, execution suitability unresolved

Investigated 2026-09-04. **E10 remains unchecked.** This is not a finding that
OpenAI prohibits third-party App Server clients or lacks ChatGPT authentication.

The official [App Server documentation](https://learn.chatgpt.com/docs/app-server)
explicitly describes integration into another product. It documents stdio
JSON-RPC initialization, thread/turn operations, `outputSchema`, and managed
ChatGPT authentication: `account/login/start`, account status, and logout. Codex
owns OAuth persistence and refresh. That is the appropriate candidate, rather
than extracting tokens or treating a ChatGPT login as an API key.

The official [authentication guide](https://learn.chatgpt.com/docs/auth) documents
OS credential storage with `cli_auth_credentials_store = "keyring"` and separate
API-key authentication. A future adapter should use a dedicated app-owned Codex
home and the official managed lifecycle, and never inspect credential files.

**Exact current integration blocker:** no verified public contract was established
in this spike that constrains *all* model-visible input and tool authority to
Presenter Copilot's pre-approved Selected Context packet. The public
[ThreadStartParams schema](https://github.com/openai/codex/blob/459a79eb85400af759e9220c7bafb4429ae07516/codex-rs/app-server-protocol/schema/json/v2/ThreadStartParams.json)
has configuration and instruction overrides, but no explicit per-thread
exhaustive empty tool allowlist. The
[tool assembly source](https://github.com/openai/codex/blob/459a79eb85400af759e9220c7bafb4429ae07516/codex-rs/core/src/tools/spec_plan.rs)
assembles core, extension, hosted, and dynamic tools; adding no dynamic tools
does not remove the others. Built-in utility tools depend on the environment
and model catalog, including an apply-patch tool. Merely declining approval
requests is not a proof of zero additional reads or context.

The [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
provides individual shell, web, app, and memory controls. Those are useful
building blocks, but this spike has not validated their combination against
all harness-added context and tools. This is an integration-suitability finding,
not a claim that such isolation is impossible or that the official API itself
is unsupported. A future implementation must pin a supported runtime, verify
effective isolation (including instructions, environment context, tools, logs,
and model-catalog changes), and fail closed when it cannot establish it.

The `codex` adapter is deliberately inert: safe unavailable status, remote
locality, no sign-in or process launch, no token discovery, no inference. It is
not selectable. Settings names the isolation blocker. Existing API-key billing
remains separately available. No real ChatGPT/Codex or OpenAI account acceptance
was exercised; no entitlement-usage or billing claim is made.

## Validation

`core/tests/test_local_provider.py` uses a disposable loopback HTTP server for
structured success, endpoint rejection, proxy/redirect denial, auth/error
redaction, bounded output, timeout, logical cancellation, shutdown, health,
selection, LAN privacy/manifests, and retrieval fallback. LAN transport in the
manifest test is redirected to that fixture by the test only.

Run `pnpm check`, `pnpm build`, `pnpm test:privacy-network`, and
`uv run --directory core --project . --locked python -m pytest tests/test_local_provider.py -q`.
`pnpm test:providers-ui` verifies real Electron Settings configuration, synthetic
HTTP inference, renderer credential exclusion, and reload persistence in a
disposable profile; it does not contact a real model or account.
The full check includes the existing provider regressions. No packaging or
runtime dependency changes are required: the transport uses Python's standard
library and the existing provider interfaces.
