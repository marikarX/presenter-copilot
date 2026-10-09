# Reasoning and decision providers

## Typed decision providers — limited slide-purpose workflow

Typed decisions are a separate provider path, not a replacement for the
text-generating `ReasoningProvider`. Settings can explicitly select local
structured output, OpenAI Responses Fast or Ultrafast, Jev through OpenRouter,
or Jev-compatible decision models through Ollama's local System One endpoint.
The current workspace action classifies the selected slide's
supported text shapes into a fixed purpose set. Core extracts text from the
selected current revision, checks the project privacy mode, and writes
provider/source/revision metadata to the run manifest. The result requires user
review; it is not saved or applied. Images, diagrams, and the complete PPTX are
not sent. See
[D-059](DECISIONS.md#d-059--typed-decision-models-are-a-separate-bounded-provider-path).

Local Only blocks remote providers. `selected_context_cloud` requires the
project's explicit remote-reasoning acknowledgement. A loopback local model
stays on-device; private-LAN endpoints are treated as off-machine. OpenAI Fast
uses the existing OpenAI credential and active OpenAI model. OpenAI Ultrafast
uses that credential with GPT-6 Astra and does not fall back to another service
tier. Jev uses a
separate OpenRouter credential entry and pinned `typesafe/jev-1.13` model.
Neither credential passes through the renderer.

Ollama 0.35 or later offers a local
[`POST /v1/systemone` API](https://docs.ollama.com/api/systemone), compatible
with Jev's typed request/response shape. The app fixes that transport to
`http://127.0.0.1:11434/v1/systemone` and offers `nimble:9b`, `tev1:4b`, and
`tev1:0.8b`, with the lower-memory `nimble:9b-q4_K_M` and
`tev1:4b-q4_K_M` variants. It also accepts Ollama's published `nimble:latest`
and `tev1:latest` aliases so models installed with the library's default
quick-start names can be selected. Settings shows the exact `ollama pull`
command for the selected tag. The selected exact model tag must already be
installed in Ollama. Presenter Copilot does not start Ollama, download model
files, or send credentials. The adapter enforces Ollama's 64 KiB API maximum,
plus tighter UTF-8 byte limits for the model context: 1 KiB of state and 1.5
KiB for the whole request for Tev1; 5 KiB of state and 6 KiB for the whole
request for Nimble. These conservative byte guards leave room for the prompt
template and scoring positions under Tev1's approximately 2,000-token context
and Nimble's 8,192-token context. They are not tokenizer-accurate guarantees;
Ollama remains authoritative and never truncates an oversized input. The
limits apply equally to quantized variants.
Before and after inference it resolves the selected installed tag through
Ollama's local [List models API](https://docs.ollama.com/api/tags); if its digest
changes during the call, the result is rejected. The verified tag and SHA-256
digest are recorded in the content-free provider-run manifest.
Nimble is listed as a 9B model; Ollama's current catalog does not list a
Nimble 4B variant. The Q4_K_M tags reduce the published download size while
keeping the model family and request contract unchanged. Ollama documents 2 to
26 options for Nimble choice/score questions, so the adapter rejects more than
26 before sending a request even though the shared schema permits 32. Tev1 is
experimental and was trained with 2 to 24 choice options, so the adapter
rejects larger Tev1 questions even though the shared schema supports more.
Ollama's catalog currently reports mean accuracy across 13 public datasets
(3,880 human-labeled decisions) of 75.7% for Nimble 9B, 73.3% for Tev1 4B,
and 63.5% for Tev1 0.8B. These provider-published results are not an evaluation
of slide-purpose suggestions or this app's task distribution, so they do not
close the project's human-labeled decision-quality gate.
Suggestions remain review-only, and a missing model or endpoint error never
falls back to another provider.
See the official [Nimble](https://ollama.com/library/nimble) and
[Tev1](https://ollama.com/library/tev1) model pages for current model and API
details.

OpenRouter documents its [System One API](https://openrouter.ai/docs/guides/community/typesafe-sdk)
at `POST /api/v1/systemone` for Jev-style typed decisions; it accepts a regular
OpenRouter API key and the TypeSafe request/response shape. The app uses that
versioned endpoint and does not request a management key. OpenAI documents
Responses [Fast mode](https://developers.openai.com/api/docs/guides/fast-mode)
and [Ultrafast mode](https://developers.openai.com/api/docs/guides/ultrafast-mode)
service tiers, and [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
can constrain Responses to a schema. These Responses adapters are interim
bridges, not implementations of the OpenAI Decisions API. OpenAI announced that
API as a GPT-6 Luna limited preview on 2026-09-29 for finite-answer decisions
over supplied text or images. Its public [DevDay recap](https://openai.com/index/devday-2026-recap/)
does not publish an endpoint, request/response schema, authentication method,
limits, or data-handling contract, and the public [API reference](https://developers.openai.com/api/reference/overview)
and [changelog](https://developers.openai.com/api/docs/changelog) still do not
document those details. A check on 2026-10-02 found no Decisions API endpoint
contract there, so keep that adapter pending instead of guessing its wire
protocol. The official Ultrafast guide says GPT-6 Astra is broadly available at
low rate limits and GPT-5.6 Sol has preview access, while the Responses
[create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
still describes GPT-5.6 Sol as the supported Ultrafast model. This conflict
leaves account-level eligibility unverified; the app targets GPT-6 Astra and
fails closed if OpenAI does not serve the requested tier.

Typed decision providers handle finite-choice tasks such as slide-purpose
classification. Selected-text rewrite suggestions use the separate
`ReasoningProvider` contract and its existing execution boundary: Core sends
the selected one-paragraph text and the user's instruction, plus an optional
server-resolved rehearsal candidate kept as untrusted context, binds the
proposal to the exact source revision, and requires review before the user
copies it into the ordinary preview/save edit path. The OpenAI Decisions API is
in limited preview, but has no verified request/response contract in this
project yet; Fast and Ultrafast Responses are not that API.

`presentation_outline` uses the same `ReasoningProvider` privacy and execution
boundary for reviewed presentation creation. It sends the objective, audience,
briefing, requested slide count, bounded retrieved project evidence, approved
explanations, and an optional complete prior draft. The prior draft and source
text remain data, not trusted instructions. Private knowledge is excluded.
This task and `presentation_edit_plan` have a 48,000-character context ceiling; other tasks keep
their 12,000-character ceiling. A briefing or draft that cannot fit is rejected
without silently shortening the user input. Core validates the native outline
shape, exact requested slide count, XML-compatible text, and cited evidence
IDs. Proposals never create documents or promote generated text into approved
knowledge. After review, native creation validates the planning run belongs to
the project and records its ID in the PPTX properties.

`presentation_edit_plan` uses the same privacy, readiness and execution boundary
to propose 1–20 operations against a verified current presentation revision.
Its strict schema exposes 15 existing native operation types; source text and
the selected object inventory are untrusted context. Private knowledge is
excluded. Core validates exact baseline scope and supplied evidence IDs, then
resolves text, style and geometry preconditions against each staged step through
the existing native validators. Oversized inventories are rejected explicitly.
Provider output prepares a private native preview; saving requires user review
of the exact bytes and a successful provider run in the same project. Audit
metadata retains the run and evidence IDs without source or replacement text.
Raw image ingestion and later references to newly created targets are excluded.
Deterministic local workflows pass; live-provider editing quality is unverified.

OpenRouter's separate alpha [Decisions endpoint](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)
currently documents a management-key requirement that conflicts with its Jev
tutorial. This app does not call that alpha endpoint or ask users for a
management key. Core maps a 403 from the versioned System One API to a
non-retryable permission error without exposing the provider response body.
Live Jev acceptance still requires an authorized account and credential.

Status checked 2026-10-02: the [OpenAI API reference overview](https://developers.openai.com/api/reference/overview)
documents Responses, Realtime, Administration, and other API surfaces; its
current index does not list a Decisions endpoint. The [OpenAI API changelog](https://developers.openai.com/api/docs/changelog)
also has no Decisions API request or response contract. The separately
announced API stays unimplemented; recheck official documentation before
adding that transport. The current Responses Fast/Ultrafast bridges and
Jev/Ollama/local adapters have synthetic adapter and Core-boundary tests. No
live Ollama decision was run. A direct
local decision-adapter acceptance also ran against LM Studio's loopback server
with `qwen3.8-4b-distill`: 10/10 outputs satisfied the strict schema, 7/10
matched a small hand-written synthetic set (70%), median latency was 1,101 ms,
and p95 was 2,106 ms. This is useful transport evidence, not representative
semantic-accuracy evidence. No OpenAI or OpenRouter live inference was used.
Keep the workflow in review-only preview until a licensing-safe human-labeled
evaluation measures quality, latency, abstention, and costly errors; broader
semantic classification and automation stay gated on those results.

The local smoke is reproducible when a loopback server and model are already
running, using the model identifier returned by that server, for example:
`pnpm benchmark:decision-local -- --model-id presenter-copilot-qwen3.8-4b`.
The Ollama System One adapter can be exercised directly against one of its
already-installed supported decision tags:
`pnpm benchmark:decision-local -- --provider-id ollama_systemone` defaults to
`tev1:4b`; pass `--model-id tev1:0.8b` or another supported tag to select a
different model. It only accepts Ollama's fixed loopback endpoint and refuses
custom endpoints. The command does not start Ollama or download weights; an
inference request may cause the running Ollama service to load the installed
model into its configured runtime. Both modes run the same ten self-authored
synthetic examples, report structured-response success, accuracy, and latency,
and omit prompt/response text. The synthetic accuracy has no release threshold
and must not be read as a quality pass.

## ChatGPT plan usage through Sign in with ChatGPT

Settings → Reasoning Providers offers an optional ChatGPT plan account for the
bounded typed-decision workflow. This follows OpenAI's [Sign in with ChatGPT
flow](https://developers.openai.com/siwc) for [open-source apps using ChatGPT
plan capacity](https://developers.openai.com/siwc/token-sharing-open-source).
It is independent of the OpenAI API-key provider and of E10's ChatGPT-managed
Codex App Server session: it does not use API-key billing or Codex-managed
credentials.

Core owns OAuth, the system-browser sign-in, the exact loopback callback,
PKCE/state/nonce validation, and ID-token signature/issuer/audience/time/nonce
checks. It verifies that the granted scopes include the requested plan-use and
offline-refresh scopes before saving. A stable opaque host ID is kept separate
from account identity, and each ChatGPT account has its own issued client ID
and session. Core stores credentials in a separate Windows user-scoped DPAPI
vault; tokens do not cross renderer IPC or enter the project database/logs.
Refresh-token rotation is saved. Sign-out attempts remote revocation and then
deletes the local account credentials; provider confirmation is best-effort.
See OpenAI's [registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
and [accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)
guides.

Core lists only models marked for public listing and lets the user choose a
model explicitly. A decision request sends the selected slide's supported text
shapes through the streamed Responses API with `store: false`, only after the
project's remote-reasoning acknowledgement and context-manifest checks. It
does not send the PPTX, images, speaker notes, or prior conversation state.
The adapter does not use tools, a system-role input, `previous_response_id`,
or an output-token override. Only a complete, schema-valid finite-choice result
is returned as a review-only suggestion; the app does not apply or save it.
See OpenAI's [models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
and [preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

Settings explains that eligible usage consumes ChatGPT plan capacity, that
limits may be shared with other apps using the account, and that this is
separate from API-key billing. The feature and model eligibility remain subject
to OpenAI's documented preview limitations. A missing account/model, rejected
scope, expired session, request error, or incomplete stream fails closed; it
never falls back to another provider. OAuth, JWKS, refresh, account-isolation,
scope, cancellation, and response-stream tests use local synthetic fixtures.
No real ChatGPT sign-in or plan inference has been run for this candidate, so
account eligibility and live endpoint behavior still need release acceptance.
The selected provider panel links to ChatGPT usage settings, and the Workspace
quota error offers the same action. See OpenAI's [ChatGPT plan usage UI/UX
guidelines](https://developers.openai.com/siwc/ui-ux-guidelines).

## E10: ChatGPT-managed Codex

Settings → Reasoning Providers → Codex offers sign-in, status, sign-out, and
explicit provider selection. Packaged Windows builds are self-contained: the
installer includes the exact official Codex CLI **0.153.4** Windows x64 runtime
used by the E10 acceptance path, with model **gpt-5.4-mini**. The release build
fetches the pinned upstream binary, verifies SHA-256 and `--version`, and places
it under Electron resources together with the upstream Apache-2.0 `LICENSE` and
`NOTICE`. End users do not install Node, npm, or Codex separately, and first run
does not download the reasoning runtime.

Packaged Electron sets `PRESENTER_CODEX_EXECUTABLE` to its own resource path
after minimizing the sidecar environment, so a system Codex binary or caller
`PATH` cannot replace the bundled runtime. Development and explicit acceptance
workflows may still use `PRESENTER_CODEX_EXECUTABLE` or `codex` on `PATH` with
exactly supported versions **0.153.1 or 0.153.4**. Other versions/models are
rejected pending containment testing. The renderer cannot supply a binary,
filesystem path, token, environment, tool, or arbitrary App Server RPC.

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
- `pnpm package:win` prepares only the pinned official 0.153.4 Windows x64 Codex
  binary and fails closed on upstream SHA-256/version mismatch. `pnpm
test:packaged` verifies the exact binary digest/version and bundled upstream
  license/notice inside `win-unpacked`; it also runs the existing packaged
  sidecar smoke with a system-only `PATH`.
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

| Runtime | SHA-256                                                            |
| ------- | ------------------------------------------------------------------ |
| 0.153.1 | `921b3df53973e3ec80e9c27b0fb6f5dfec463be44333007f93e60b20caef4f41` |
| 0.153.4 | `444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b` |

Version acceptance is exact-version based; binary digests record the tested
distribution, rather than claiming every same-version distribution is identical.
Packaged release builds additionally require the exact 0.153.4 digest above.
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
is claimed for the text-generation adapter by the synthetic HTTP tests. The
typed local decision adapter was separately exercised against LM Studio as
described above; that does not establish text-generation compatibility or
decision quality.

An optional `PRESENTER_LOCAL_API_KEY` is read only from the Core environment.
It is not accepted over IPC or stored in SQLite. It is independent of the
existing OpenAI API credential and Windows Credential Manager entry. This
increment does not create another durable secret or require a database migration.

`local_openai` remains a local provider. Its `leaves_machine` property separates
inference locality from transport privacy:

| Endpoint                                                       | Local Only                       | Other project modes                                    |
| -------------------------------------------------------------- | -------------------------------- | ------------------------------------------------------ |
| Literal loopback or `localhost`                                | Allowed when explicitly selected | Allowed                                                |
| RFC1918 IPv4 / IPv6 ULA                                        | Blocked                          | Requires existing remote acknowledgement and manifests |
| Public IP, arbitrary DNS, link-local, unspecified, mapped IPv6 | Rejected                         | Rejected                                               |

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
