# Post-MVP reasoning providers

## E10: ChatGPT-managed Codex

Settings → Reasoning Providers → Codex offers sign-in, status, sign-out, and
explicit provider selection. Install the official Windows Codex executable
separately: supported versions are exactly **0.153.1 and 0.153.4**, with model
**gpt-5.4-mini**. Other versions/models are rejected pending containment testing.
Core resolves `codex` or the backend-only `PRESENTER_CODEX_EXECUTABLE` absolute
executable path; the renderer cannot supply a binary, filesystem path, token,
environment, tool, or arbitrary App Server RPC.

Authentication uses official App Server `account/login/start` with `type: chatgpt`,
`account/read`, `account/login/cancel`, and `account/logout`. The official browser
flow opens outside the renderer. Presenter never opens, copies, or parses auth
files or tokens. Codex manages its own credentials in a fresh dedicated
`CODEX_HOME`. Sign-in lasts for the app session; logout/shutdown terminates the
owned process and deletes its disposable runtime. A process/OS crash can leave
that temporary directory behind; subsequent sessions never discover or reuse it.
Status exposes only state, safe error code, and runtime version. The existing
OpenAI API-key provider and its credential store remain independent. Selecting
Codex disables other provider selections; errors never trigger remote fallback.

### Containment boundary

The security invariant is containment: model-visible capabilities must not access
user/project files, credentials, inherited instructions, environment data, or
other state outside the approved Selected Context packet and Presenter-owned
runtime state. It is not a guarantee of zero built-in tools.

Core starts `codex app-server --stdio --strict-config` with an empty disposable
working directory and an allowlisted environment pointing home/profile/temp
locations into its own runtime. It passes no Presenter project path. Project
docs, host skill discovery, bundled skills/instructions, MCP, apps/connectors,
plugins, web, shell/execution, dynamic tools, memory, and environment instructions
are disabled through the explicit version-scoped policy. Thread sandbox network
access is disabled; the App Server itself still connects to OpenAI for managed
authentication and inference. This is tested capability containment, not an
OS-wide filesystem jail for the trusted App Server executable.

Before any Selected Context is sent, Core checks its configuration file,
effective config and source layers, empty working directory, empty discovered
skill/MCP catalogs, and the new thread's instruction sources, workspace roots,
model/provider, sandbox and approval policy. Each inference uses a fresh ephemeral
thread with the fixed Presenter policy and canonical task contract. Its sole
user input is the execution-validated serialized Selected Context packet.
`ProviderExecutionService` continues to own privacy acknowledgement, `local_only`,
context manifests before transmission, schema/provenance validation, and exactly
one terminal ProviderRun status. Cancellation/timeout interrupts the Codex turn;
late results cannot become successful runs.

The pinned model/runtime exposes residual internal `skills.list` / `skills.read`.
In the tested runtime they return empty catalogs or reject unavailable packages,
including absolute paths, traversal, URI aliases, credential paths, and planted
host skills. App Server has no exhaustive authenticated-thread tool-catalog RPC;
these internal calls are also opaque to normal item notifications. E10 therefore
uses effective-source inspection, pinned runtime/model regression, adversarial
containment evidence, and rejection of newly observed sensitive item types or
server-initiated RPCs. It does not claim exhaustive pre-send enumeration. The
synthetic capture rejects tool-definition drift; runtime inspection rejects
material config/instruction drift. Any observed containment failure disables the
runtime. An unobservable upstream change remains a limitation of this supported
path and requires renewed acceptance when discovered.

### E10 validation and upgrade gate

- `pnpm check`: deterministic auth/session/error, transport bounds, isolation
  drift, unexpected capability, cancellation, structured-output, manifest and
  provider-selection regressions, alongside existing tests.
- `pnpm test:codex-containment`: installs both exact official npm runtimes in a
  disposable test location and forces 62 adversarial residual tool calls per
  binary through a local synthetic Responses fixture. It checks the exact tool
  definition digest and all outputs, including forbidden skill discovery and
  ancestor instructions. This unauthenticated fixture never shares a process or
  home with account acceptance. Hosted and trusted local CI run this gate.
- `pnpm test:codex-real`: explicitly opt-in; runs the same forced containment
  probe, opens official managed sign-in, then executes eight synthetic packets
  through the real execution service, including all 62 adversarial forms as
  untrusted evidence. It checks structured results and successful manifest-backed
  runs, then logs out. Real-model prompts do not force the model to call tools;
  the unauthenticated deterministic probe provides that forced-call evidence.
- `pnpm test:privacy-network` and `pnpm test:providers-ui`: preserve existing
  network/privacy behavior and verify real Electron typed Codex status/sign-out,
  fixed model selection, credential exclusion, and independent local inference.

Acceptance on 2026-09-04 passed with official managed ChatGPT authentication,
`gpt-5.4-mini`, eight structured responses, 62 adversarial forms, and eight
successful manifest-backed runs. Only synthetic content was used. The session
was signed out after acceptance; no existing Codex/ChatGPT token was reused.
This is point-in-time inference/containment evidence, not a promise of account
entitlement or availability. The same 62 forced calls passed on both pinned
Windows npm runtimes, with binary SHA-256 recorded below:

| Runtime | SHA-256 |
| --- | --- |
| 0.153.1 | `921b3df53973e3ec80e9c27b0fb6f5dfec463be44333007f93e60b20caef4f41` |
| 0.153.4 | `444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b` |

Version acceptance is exact-version based; binary digests record the tested
distribution, rather than claiming every same-version distribution is identical.
Model changes also require regression: `gpt-5.6-luna` exposed an additional
execution wrapper and was rejected by the drift gate. Do not broaden the runtime
or model allowlist without forced probes and synthetic real-account acceptance.
Official interface reference: [Codex App Server](https://learn.chatgpt.com/docs/app-server).

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
