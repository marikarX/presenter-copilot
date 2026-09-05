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
Teach, Challenge, and Live build packets using `leaves_machine`, not the local
provider label. This removes private context before LAN execution rather than
rejecting a mixed public/private packet at the final guard. Challenge provenance
checks and Live preferred-evidence selection use the same transport authority.

The adapter caps output at 2,048 requested tokens and 65,536 response bytes,
then applies the existing task schemas and provenance checks. HTTP operations
have a total watchdog within the request budget; shutdown closes active sockets.
Logical cancellation uses the existing execution boundary and suppresses late
results; provider-native cancellation is not advertised. Health is initially
configured/unavailable (`PROVIDER_NOT_TESTED`), and a successful request marks
it reachable. Status is the last observed outcome, not a background probe.
The explicit Test button sends only a synthetic packet and can restore readiness.

## Validation

`core/tests/test_local_provider.py` uses a disposable loopback HTTP server for
structured success, endpoint rejection, proxy/redirect denial, auth/error
redaction, bounded output, timeout, logical cancellation, shutdown, health,
selection, LAN privacy/manifests, and retrieval fallback. LAN transport in the
manifest test is redirected to that fixture by the test only.
The privacy-network suite also exercises all six reasoning tasks with mixed
public document evidence and private preferred knowledge against a simulated
LAN provider. It verifies successful invocation, pre-call manifests, and absence
of private text and identifiers from provider payloads.

Run `pnpm check`, `pnpm build`, `pnpm test:privacy-network`, and
`uv run --directory core --project . --locked python -m pytest tests/test_local_provider.py -q`.
`pnpm test:providers-ui` verifies real Electron Settings configuration, synthetic
HTTP inference, renderer credential exclusion, and reload persistence in a
disposable profile; it does not contact a real model or account.
The full check includes the existing provider regressions. No packaging or
runtime dependency changes are required: the transport uses Python's standard
library and the existing provider interfaces.
