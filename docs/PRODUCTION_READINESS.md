# Production Readiness Snapshot

## Current continuation - committed; cross-Run comparison, list numbering and bullet markers (2026-10-09)

IN PROGRESS. The previously dirty worktree is now committed on
`codex/production-readiness` (`bc1ab9c`), and work continues as small commits
(not pushed). Earlier handoff entries describing "no staging/commit" and
freeze/preservation verifiers are historical; git history is now the record.

Commits this session:

- `55473c3` ChatGPT-plan model catalog also accepts the standard `{data:[{id}]}`
  list shape (previously only the Codex-style `models[].slug` shape).
- `3401a83` Cross-Run objection comparison Core: schema 23 tables
  (`presentation_rehearsal_objection_comparisons` plus a candidate join table
  that references original `finding_id`s and cascades with either Run or the
  original analysis); `RehearsalObjectionComparison` prepare (fingerprinted,
  verified candidates from two distinct ended Runs with unchanged recordings),
  analyze (routed/audited, both recordings guarded in the storage transaction),
  list and verified read; a `comparison` job kind that owns both Run IDs for
  cancellation and session deletion; four protocol methods across Core,
  desktop allowlists and examples.
- `ff1d9f5` Comparison GUI (`RehearsalObjectionComparison.tsx`, in the
  Rehearsal panel) and `test-rehearsal-objection-comparison.mjs` (7/7 actual
  Electron/Core checks; model adapter is the only fixture). A rejected Start
  clears the stale preparation (bug found in the GUI run).
- `e1bfd65` List numbering `1)`, `a.`, `A.`, `i.`, `I.` across detection,
  apply, text-fit markers and the GUI; fixes Copilot edit plans offering
  `bullet_disc`, which Core rejected (schema now mirrors Core, parity-tested);
  adds opt-in `accept-chatgpt-live.mjs` guided live acceptance.
- `2946282` Editable bullet color (`buClr` sRGB) and size (`buSzPct` 25–400%),
  retained across marker-type changes; PowerPoint-style lists with a plain
  text-font `buFont` are now editable (previously read-only). GUI "Bullet
  marker" group; `test-bullet-marker.mjs` 4/4. A draft bug that would have
  written black bullets unasked was caught by the harness and fixed.

- Next commit: editable numbering start values (`buAutoNum startAt`, 1–9999),
  carried across numbered schemes and reset by choosing 1; imported custom
  starts are now editable while malformed values stay read-only. GUI
  "Numbering starts at" field; bullet harness checks roman numbering from III.

- `9bd3cbb` Blank lines (run-less paragraphs) no longer block text and list
  formatting (the only blocker for 21% of corpus text shapes); corpus
  format-editable objects 1836 -> 2068.

Validation: latest full `pnpm check` green on `9bd3cbb` (1908 Core tests,
desktop 312, lint/types/format) with `test-workspace.mjs` 117/117 and
`test-bullet-marker.mjs` 4/4 on that commit. Earlier: check green on
`2946282` (1888 Core tests) and `2f5ce70` (1894); `test-workspace.mjs` 117/117 after both the numbering
and bullet-marker commits; existing objection review GUI 20/20 with the
comparison panel mounted; `test-bullet-marker.mjs` 4/4 including start values.
- `57c84c4` Real-deck bullet tolerance: follow-text, point-size, theme-color
  and single-glyph symbol bullets are editable; applying a marker drops a
  direct symbol font and writes `buFontTx` when needed, fixing markers that
  would have inherited a Wingdings list-style font.

Corpus: all 1836 format-editable text objects in the 33 cached decks are now
bullet-editable (from 1654). 13 real-deck edits read back exactly, use a
text-font marker and open in PowerPoint; rendered before/after pairs were
reviewed. Two decks are declined by the active/external-content safety policy.
See `docs/PRESENTATION_WORKSPACE/VALIDATION.md`.
Fast Decisions live local acceptance (2026-10-09):

- Model: the installed `Qwen3.8-4B-Q4_K_M.gguf`, served on `127.0.0.1:1234`
  by LM Studio's bundled `llama-server` (the LM Studio app itself would not
  start from the agent environment). Server stopped afterwards.
- `presenter_core.tools.decision_acceptance` (10 self-authored synthetic
  cases, `local_choice` provider):
  - GPU (CUDA 12 build): two complete runs, 9/10 and 8/10 correct; median
    882 / 948 ms, p95 1152 / 1375 ms; no timeouts.
  - CPU (AVX2 build): 8/10 when given a 30 s timeout, but median 8.6 s and
    p95 16.5 s; at the default 10 s timeout most requests time out. CPU-only
    hosts do not meet a "fast" budget with this model.
  - Errors cluster on the "opening" (agenda) case, and results vary between
    runs on the same inputs.
- New opt-in GUI acceptance `accept-fast-decisions-local.mjs` (actual
  Electron/Core, live loopback model): Settings configures the local endpoint
  and model and selects Local for Fast Decisions; the Workspace Purpose panel
  returns live suggestions (581–1737 ms provider latency) that are saved only
  after explicit review. The "We recommend funding the pilot" slide was
  classified correctly in both runs; the Agenda slide came back "unclear" in
  one run and "recommendation" in another.
- Bug found and fixed: saving the local reasoning provider did not refresh
  Fast Decisions status, so the panel kept showing the local model as "not
  configured" and Save stayed disabled until Settings was reopened.

- Calibration tooling: `pnpm calibrate:decisions export --corpus
  .local/presentation-workspace-corpus --out .local/calibration/slide-purpose-sheet.csv`
  wrote an unlabeled 684-slide sheet from the 33 corpus decks. After a person
  fills `label`/`labeler`, `pnpm calibrate:decisions evaluate --sheet ...
  --model-id ... --out ...` reports accuracy, confusion and a confidence
  threshold table, and recommends a minimum confidence only with at least 50
  human labels. It never edits thresholds. A live smoke on the 10 self-authored
  cases (not human labels) ran end to end: 6/10, 4 abstentions, 83% precision
  when decided, about 940 ms. The local provider returned no confidence values,
  so confidence thresholds can only be calibrated for providers that report
  confidence; a local model can be judged on accuracy and abstention only.

This is integration evidence, not calibration: thresholds remain uncalibrated
until a licensing-safe human-labeled set exists.

Human-gated items (cannot be completed by an agent):

- Sign in with ChatGPT live acceptance: run
  `PRESENTER_CHATGPT_LIVE_ACCEPTANCE=1 pnpm accept:chatgpt-live` with an
  eligible account. It automates consent wait, restart persistence, model
  listing, disclosures, one synthetic decision, catalog refresh and sign-out,
  and writes a token-free receipt to `.local/chatgpt-live/`.
- Fast Decisions calibration needs a licensing-safe human-labeled set. Live
  local integration is now exercised (see above); rerun with
  `PRESENTER_DECISION_LIVE_MODEL=<id> node apps/desktop/scripts/accept-fast-decisions-local.mjs`
  after starting a loopback model server.
- An unauthenticated probe of the app's real ChatGPT-plan authorize URL
  (`dynamic_agent_client`, custom scope, `resource`/`ext_agent_host_id`/
  `agent_name_hint`) reached `auth.openai.com`, but both a plain HTTP client
  (403) and headless Chromium ("Just a moment…") stop at Cloudflare's bot
  challenge. Whether OpenAI accepts these parameters therefore can only be
  confirmed in a real user browser, which is the consent step the guided
  script waits for. Probe: `.local/session2/chatgpt_authorize_probe.py`.
- Codex "Sign in with ChatGPT" lasting only for the app session is documented
  in `docs/PROVIDERS.md` as part of the isolation design, not a bug.

Next: remaining direct-edit gaps (picture bullets, symbol-font bullets), held Run/head GUI replies,
fidelity corpus review and human acceptance gates. Signing and clean Windows
validation remain accepted debt.

## Current continuation - identity GUI accepted and comparison foundation started (2026-10-08)

IN PROGRESS. Final actual Electron/Core/native GUI60052 passed20 checks/errors empty:
historical changed recording disables adoption but retains excerpts/IDs and independent
review; restored recording restores eligibility. Actual reviewed native reorder maps
original slide1 to current2 with unchanged candidate IDs/dispositions; actual reviewed
deletion removes current mapping/navigation/adoption while preserving historical
excerpts/independent dismissal and no extra native edit. Two harness interaction/
encoding failures retained and corrected; final identity receipt/log accepted.

New cross-Run comparison provider contract assesses the complete bounded selected
candidate matrix with original left/right IDs and unverified equivalent/related/
distinct/unclear interpretations. Omissions, duplicates, foreign/reversed/same-side
IDs and extra review/speaker/quote authority reject. OpenAI/local/Codex/fake registration
and transport supported; fake only returns unclear. Target153/old adapter regression
and final33 contract cases pass; Core ruff/format310/mypy193 pass. Owned context,
durable comparison store, two-Run lifetime jobs/API and GUI still required; no live
semantic usefulness/account/human acceptance claimed.

Freeze512 preserves506 previous inputs unchanged/four intended provider edits/two
new schema/test files;434 dirty paths/branch/base/16 packages preserved. Full
check62233 RUNNING at .local/rehearsal-semantic-coverage/check-objection-equivalence-contract.log;
source frozen, no GUI/build live. Use comparison contract verifier/freeze.
Remaining: complete cross-Run workflow, held Run/head GUI replies, broader density/
assets/conversation, fidelity/live Fast Decisions/official ChatGPT/human integration.
Rough80% overall/features90%/integration68%; signing/clean Windows accepted debt.
Goal active; no staging/commit/push/reset/package rebuild.

## Current continuation - actionable objection error routes accepted (2026-10-08)

IN PROGRESS. Pending-Cancel broader Workspace81032 passed117 checks/renderer errors
empty. Core unchanged/full1812/mypy192; current desktop312/lint/types/build/format
pass. Objection error display now preserves structured RPC messages/codes and gives
known provider/privacy/context recovery directions. Worker failure uses the same
formatter; privacy, routing, audit and native edit authority are unchanged.

Actual dedicated GUI34920 passed17 checks/errors empty: provider unconfigured,
remote-in-Local-Only and missing remote acknowledgement failures, late recording
mutation before job allocation, and explicit successful retry. Failed attempts
persist no result, acknowledge nothing and leave native revision unchanged.
Fixture policy selection is explicit; provider readiness/locality/model/capture are
fixtures. Earlier117 broad GUI predates only the formatter; final17 is current.
No live-provider/account/human acceptance is claimed.

Receipts/logs: objection-errors-final-gui/result.json, objection-errors-final-gui.log,
objection-errors-desktop.log, objection-errors-build.log in
.local/rehearsal-semantic-coverage. Final errors freeze510 preserves508 prior inputs
unchanged/two intended component/harness edits,432 dirty paths/branch/base/16 package
artifacts. No GUI/build/full-check live. Use final errors verifier/freeze.

Remaining: historical stale-recording/reorder/removal/held Run/head GUI edges,
distinct-Run semantic equivalence with independent provenance/dispositions and
both-Run cancellation ownership, broader density/assets/conversation, fidelity,
live Fast Decisions/official ChatGPT/human integration. Rough80% overall/features90%/
integration68%; signing/clean Windows accepted debt. Goal active; no staging/commit/
push/reset/package rebuild.

## Current continuation - pending Start cancellation implemented (2026-10-08)

IN PROGRESS. Objection Cancel is now available before Start returns its job ID;
the captured owner/generation path retains cancellation intent and sends actual
Cancel when the ID arrives. Desktop312/lint/types/build pass. Core unchanged from
full1812/mypy192 acceptance. Actual GUI85014 passed13 checks/errors empty, including
accepted direct pending Cancel and hidden-panel pending Start, plus independently
verified completed storage/too-late cancellation with saved history preserved.
Native revision and original applied reviews remain unchanged. Fixture model/capture/
picker do not establish live or human acceptance.

Evidence: objection-start-final-gui/result.json and objection-start-final-gui.log in
.local/rehearsal-semantic-coverage. Freeze510 preserves508 prior inputs unchanged/
two intended edits (component/harness),432 dirty paths/branch/base/16 packages.
Broader Workspace GUI81032 RUNNING at objection-start-workspace.log; source frozen,
no build/full-check live. Use final start freeze/verifier and poll the existing handle.

Remaining: stale/reorder/removal/held Run/head GUI edges and actionable structured
provider/privacy error routes; distinct-Run semantic equivalence with independent
candidate provenance/dispositions and both-Run cancellation ownership; broader
density/assets/conversation/fidelity/live Fast Decisions/official ChatGPT/human
integration. Rough80% overall/features90%/integration68%; signing/clean Windows
accepted debt. Goal active; no staging/commit/push/reset/package rebuild.

## Current continuation - objection restart and deferred detail accepted (2026-10-08)

IN PROGRESS. Full check30948 passed1812 Core/312 desktop/format/lint/types/mypy192;
Core429.14sec. Maintained actual Electron/Core/native PPTX harness now passes10
checks/errors empty (44715). Full restart retains original Run,21 saved analyses,
independent applied candidate identities/review state and exact native current
revision; applied candidates cannot prepare edits or reopen. A verified actual Core
detail reply released after panel closure cannot restore old candidate/adoption
controls. Native revision and verified review records remain unchanged.

Only the harness changed; application source matches full-check and broader117-GUI
acceptance. Picker/capture/model are explicit fixtures, not live/human acceptance.
Evidence: objection-restart-gui/result.json and objection-restart-gui.log in
.local/rehearsal-semantic-coverage. Harness format/lint pass; freeze510 preserves509
previous inputs unchanged/one intended harness edit.432 dirty paths/branch/base/16
packages preserved. Use objection-restart-freeze.json and its verifier. No GUI/build/
full-check live now; goal active.

Remaining: held Start/late Cancel/stale recording/reorder/removal/provider/privacy
GUI routes, distinct-Run semantic equivalence with both-Run lifetime ownership and
separate candidate provenance/dispositions, broader density/assets/conversation,
fidelity, live Fast Decisions/official ChatGPT/human integration. Rough80% overall
(features90%,integration68%), not test-count derived. Signing/clean Windows accepted
debt. No staging/commit/push/reset/package rebuild.

## Current continuation - objection GUI workflow validated (2026-10-08)

IN PROGRESS. Adoption full check32677 passed1803 Core/312 desktop/format/lint/types/
mypy192;Core446.87sec. New objection GUI enables debrief-free ended Run/original-slide
paging, complete recorded windows/explicit detection, shared owned cancellation,
empty and multi-candidate history/detail, per-candidate dismiss/reopen, and explicit
current notes/text/rewrite preparation into actual native editing. Concern and possible
answer excerpts remain separate unverified context; no text object is inferred.
Original slide API preserves stable identities through reorder/remove without needing
a debrief or editable native object. Oversize text excerpts are not silently truncated.

Selector/history/jobs/protocol16268 passed55 tests16.85sec; desktop types/lint/Core
mypy192/ruff/build pass. Actual objection GUI39958 terminal0:8 checks/renderer errors
empty, including held-provider Cancel/no persistence, separate candidate dispositions,
native notes Save, separate rewrite review/native text Preview/Save, empty analyses,
21-result paging and707x460/430-wide contained layout. Screenshot inspected. Model,
picker and capture are explicit fixtures; audit/storage/jobs/native edit are actual
application code. Live-model/physical microphone/human acceptance are not established.
Initial harness syntax and premature history-row assertion repaired; accepted evidence
is objection-gui-corrected/result.json and objection-gui-native-corrected.log.

Broader Workspace GUI78328 passed117 checks/renderer errors empty on this build;
receipt retained as objection-gui-workspace-result.json. Native edit/table/chart/
Copilot/rehearsal/minimum-window/general restart/disabled Fast Decisions checked.
Dedicated objection restart, stale/hidden/deferred reply, source reorder/remove and
late-Cancel GUI edges still require acceptance, as do provider/privacy error routes.

GUI freeze510 preserves499 of507 previous inputs unchanged/eight edits/three newfiles;
final harness-only correction freeze510 preserves509 of510 GUI inputs.432 dirty paths,
branch/base/16 packages unchanged. Full check30948 running at
.local/rehearsal-semantic-coverage/check-objection-gui.log; production source frozen,
no GUI/build live. Use final GUI verifier/freeze; do not republish stale drafts.

Remaining: dedicated GUI edges, distinct-Run semantic equivalence with separate
candidate provenance/dispositions and both-Run job lifetime ownership, broader Workspace
density/assets/conversation, fidelity, live Fast Decisions/official ChatGPT/human
integration. Rough estimate80% overall (features90%, integration68%), not derived from
test counts. Signing/clean Windows accepted debt; goal active. No staging/commit/push/
reset/package rebuild; older packages remain isolated from schema22 stores.

## Current continuation - candidate adoption and native Save (2026-10-08)

IN PROGRESS. Shared queue/API full check74753 passed1781 Core/312 desktop/format/
lint/types/mypy191;Core439.16sec. New candidate resolver supplies safe public finding
details and enables existing rehearsal dismiss/reopen and explicit native notes/text
Save APIs. Exact concern excerpts remain separate from unverified concern/reason/
answer metadata; no original text object is inferred. Rewrite preserves this boundary,
audits original Run/candidate provenance and excludes private notes/knowledge.

Native Save atomically checks owned immutable snapshot/candidate hashes/provider
audit/recording/disposition/head/parent/original and edit-baseline snapshots. Late
failures roll back native revision and review; siblings save independently across
successive revisions. No-op saves remain unreviewed; applied candidates cannot reopen.
Historical stale/removed-slide candidates remain dismissible but cannot be adopted.

Focused adoption/coverage/jobs/store43099 passed86 tests46.50sec, including actual
PPTX content and late transaction mutations. Existing debrief/recurring/rewrite/
history/appendix/edit-planning24593 passed83 tests31.03sec. Core mypy192 and ruff pass.
Model/capture fixtures prove contracts, not live-model/human usefulness. Objection
GUI selection/detection/history/detail/preparation/Preview/Save acceptance is pending.

Freeze507/preservation retains502 of505 prior inputs unchanged/three intended edits/
two new files;429 dirty paths, branch/base/16 package artifacts unchanged. Full
check32677 running at .local/rehearsal-semantic-coverage/check-objection-adoption.log;
production source frozen, no build/GUI live. Stale ignored drafts must not overwrite
the corrected implementation.

Next is actual objection GUI and native Preview/Save workflow, then distinct-Run
semantic equivalence and broader Workspace/fidelity/live Fast Decisions/official
ChatGPT/human integration gates. Estimate78% overall (features88%, integration65%)
unchanged. Signing/clean Windows accepted debt; goal active. No staging/commit/push/
reset/package rebuild; older packages remain isolated from schema22 stores.

## Current continuation - audited objection storage and shared jobs (2026-10-08)

IN PROGRESS. Schema22 full check10376 passed1730 Core/312 desktop. Audited objection
store full check26305 terminal0 passed1761 Core/312 desktop/format/lint/types/mypy191;
Core411.29sec. Separate immutable analyses support empty results and0..4 independently
hashed candidates. Original source/window/whole-recording/provider audit/native
snapshot checks reject corruption and stale adoption; changed recordings retain
readable history. Original privacy metadata survives preference changes. Actual
ProviderExecutionService routing/policy/cancellation gates remain in force.

Public prepare/start/list/detail APIs now expose objections through the existing
bounded owned rehearsal analysis queue. Coverage and objections share four live
slots/32 retained records and cancel/deletion/close/model/reset barriers. Terminal
job results contain IDs only; coverage keeps finding_id, objections use finding_ids.
Paged history includes empty analyses and requires verified detail before adoption.
No model label, quoted answer, empty window or recorded actor becomes verified truth.

Store/context/coverage regression80 tests42.86sec; native store cases31 tests13.41sec;
shared queue/IPC/history/protocol regression31409 passed69 tests26.99sec. Core mypy191
and desktop types pass. Tests include mixed capacity, independent candidates, empty
results, cancellation timing, owned cleanup barriers, history after queue eviction,
foreign owners and current-vs-original context. All model inputs/outputs are fixtures;
this is not live-model quality or actual objection GUI/native adoption acceptance.

Freeze505/preservation retains498 of504 prior inputs unchanged/six intended edits/
one new test file,427 dirty paths, branch/base/16 package artifacts unchanged. Full
check74753 running at .local/rehearsal-semantic-coverage/check-objection-jobs.log;
production source frozen, no build/GUI live. Do not republish stale ignored drafts.

Required next: transaction-guarded candidate resolution/dismissal/reopening and exact
concern-quote notes review/Preview/native Save; then actual GUI selection/window/
detection/history/detail workflows and distinct-Run semantic equivalence. Broader
Workspace/fidelity/integration/human/live Fast Decisions and official ChatGPT gates
remain open. Overall estimate78% (features88%, integration acceptance65%) unchanged.
Signing and clean Windows validation remain accepted debt; older packages must stay
isolated from schema22 stores. Goal active; no staging/commit/push/reset.

## Current continuation - objection schema22 and recording identity (2026-10-08)

IN PROGRESS. Prior context/provider full check1041 terminal0:1726 Core/312 desktop/
format/lint/types/mypy189;Core414.20sec. Whole-recording SHA now matches existing
transaction-compatible recording_state and stays stable when only current project
privacy preference changes; policy capture/reread is separately guarded. Original
Run binding and every final utterance retain identity, text, actor, timing and slide.

Schema22 adds separate objection analyses and0..3 unique candidate slots with owned
source/baseline/Run/provider FKs, hashes, bounded JSON and cascade. Empty analyses can
have no candidates. No domain parser/save/read, RPC, jobs, adoption or GUI yet; this
is storage-schema foundation. Populated21->22 migration preserves old coverage/review/
audit/recording/debrief/native files/app DB; collisions roll back both schema versions.
Protocol/version assertions and fixture downgrades updated together.

Targeted83 tests23.20sec + migration/schema selection30 tests6.41sec passed;
ruff format/check301 files and mypy189 passed. Evidence under
.local/rehearsal-semantic-coverage/objection-schema22-*.log.
Freeze501/preservation retains482 of500 prior inputs unchanged/18 intended edits/
1 new migration test;423 dirty paths/branch/base/16 package artifacts preserved.
Full check10376 running at check-objection-schema22.log; source frozen, no GUI/build.
Older binaries/packages stay isolated from schema22 stores.

Next: strict audited immutable save/read/analysis; candidate review and exact concern
notes/native Save guards; bounded jobs/lifetime cancellation; public APIs/actual GUI;
distinct-Run equivalence. Stored window privacy metadata must preserve historical
validation without treating preference changes as changed speech. Broader density/
assets/conversation, remaining semantic GUI edges, fidelity, live Fast Decisions
and official human ChatGPT acceptance remain open. Goal active; signing/clean
Windows accepted debt; no package rebuild/public action.

## Current continuation - objection recorded context and adapters (2026-10-08)

IN PROGRESS. Objection context preserves full actor-labeled recorded speech from an
owned ended Run/original stable slide, without editable-text dependency/private notes.
Source snapshot/head and final whole-recording reread guards reject changed context.
Actual serialized12000-character requests yield complete <=4-utterance windows;
oversize escaped speech fails rather than truncates. Unmapped recordings are counted;
speaker/ASR/interpretations remain unverified. Separate whole-recording SHA captures
changes beyond selected-slide speech. Task schema/instruction/output dispatch and
narrow disclosure classes are shared by OpenAI/local/Codex/fake; fake abstains with
empty observations. No Workspace RPC, storage, job orchestration or GUI yet.

Accepted186 context/contract/adapter + existing provider regressions38.70sec;
ruff format/check300 files and mypy189 passed. Evidence in
.local/rehearsal-semantic-coverage/objection-context-provider-tests.log and lint/type
logs. objection-context-freeze500/preservation retains492 of497 previous inputs
unchanged/5 intended provider/schema edits/3 new files,422 dirty paths, unchanged
branch/base/16 package artifacts. Full check1041 currently running at
check-objection-context.log; source frozen, no GUI/build live. Earlier117 Workspace
GUI checks apply to their accepted earlier build, not new objection functionality.

Next: immutable typed analyses/candidate review/native transaction guards; shared
bounded cancellation/job lifetime integration; public APIs and actual GUI workflow;
distinct-Run equivalence. No completed semantic objection or live-model-quality
claim. Broader density/assets/conversation, remaining semantic GUI edges, fidelity,
Fast Decisions and official human ChatGPT acceptance remain open. Goal active;
signing/clean Windows accepted debt. No package rebuild or public action.

## Current continuation - Workspace regression accepted; objection contract started (2026-10-08)

IN PROGRESS. Broad Workspace GUI6543 terminal0:117 checks/renderer errors empty
against the accepted correction build. Actual Electron/Core/native workflows with
disposable data and fixture capture/provider boundaries. Evidence:
.local/rehearsal-semantic-coverage/regression-workspace-result.json and
regression-workspace.log; prior151-file UI evidence retained separately. This
proves local workflows, not physical capture, live model quality or human benefit.

Semantic objection contract foundation now defines bounded <=4 observations, exact
concern/possible answer quotes separately, one-window answer status and empty result.
Exact unique quote authority and strict output bounds are validated; overlapping
concerns cannot inflate candidate counts. New+existing coverage contract60 tests
passed1.03sec; ruff format/check and mypy188 passed. No task routing, public RPC,
durable objection storage or GUI yet: semantic detection/equivalence remains open.
Coverage's user-only speech, native quote adoption and one-finding typed storage
cannot silently become objection records. Relevant original actors and concern
excerpts need fresh context, audited inference, separate typed durable findings and
reviewed native adoption; distinct Run provenance is required for recurrence.

objection-contract-freeze497 retains all495 prior source inputs unchanged, only2
new contract/test files. Branch/base/419 dirty paths/16 package artifacts preserved.
No live process from this continuation. Next substantial feature work is objection
context/provider integration/storage/GUI, then cross-Run semantic equivalence.
Broader density/assets/conversation, remaining semantic GUI edges, fidelity, live
Fast Decisions and official human ChatGPT acceptance remain open. Goal active;
signing/clean Windows accepted debt; no package rebuild/public action.

## Current continuation - semantic cancellation, viewport and rewrite GUI accepted (2026-10-08)

IN PROGRESS. Full check82382 terminal0:1675 Core/312 desktop/format/lint/types/
mypy187;Core401.73sec. Corrected build terminal0, existing large-chunk advisory.
Actual source Electron GUI13865 terminal0 accepted11 checks; GUI11440 terminal0
accepted12 after adding semantic Suggest rewrite/review/Use suggestion/native
Preview/Save. Evidence: .local/rehearsal-semantic-coverage/gui-notice-correction/
result.json and gui-rewrite/result.json, renderer errors empty. Real held Start/
Cancel receipt matches terminal notice/result count; already committed analysis
survives too-late Cancel; hidden panel cancels captured job and discards stale reply.
Measured actual renderer707x460, semantic scroll/client430/430, document707/707;
screenshots inspected. Old auxiliary-window viewport claim remains historical.

Suggestion request/copy preserves native SHA, revision and unreviewed finding;
explicit user replacement/native Save retains exact semantic finding attribution.
The fixture provider returns unchanged text: this is workflow acceptance, not model
rewrite quality. Speech/session seeding and picker/ASR/provider fixtures do not
prove physical capture, live inference or human usefulness. Current application
source matches passing full check/build; only published harness changed afterward.
gui-rewrite-freeze495 retains494 prior inputs unchanged/one intended harness edit;
branch/base/417 dirty paths/16 old package artifacts preserved. Rehearsal coverage
GUI30219 terminal0:7 checks; native claim GUI48416 terminal0:6 checks/errors empty.
Broad Workspace GUI6543 currently running against the same frozen build. Old
.local/ui-validation evidence copied before launch (151 files/52,319,013 bytes).

Open: affected GUI regressions; substantial Workspace semantic objections/density,
assets/conversation; semantic graphics/reorder/delete/stale context/paging/held-detail
acceptance; dedicated active-job reset; fidelity, live Fast Decisions and official
human ChatGPT authentication/inference. Signing/clean Windows accepted debt.
Goal active, no package rebuild or public action; old schema20 packages isolated
from schema21 stores.

## Current continuation - semantic GUI acceptance and terminal notice correction (2026-10-08)

IN PROGRESS. Initial GUI/application freeze494 passed full check76535 terminal0:
1675 Core/312 desktop/format/lint/types/mypy187;Core331.20sec. Build passed at
gui-build.log (large chunk advisory). New published actual source Electron harness
apps/desktop/scripts/test-rehearsal-semantic-review.mjs uses disposable data, picker/
ASR/provider boundaries as fixtures, actual GUI Run start/stop, actual SQLite final
speech seed9 and25 extra owned ended Runs, real Core semantic RPCs/native Save.

Basic GUI run59898 terminal0 recorded8 checks at gui-initial/result.json. Seven workflow
checks establish no-debrief/no-speech behavior, session paging beyond20, full long native
source with explicit unique span,9 utterances/3 windows/explicit one-window Analyze with
native bytes unchanged, verified separate original message/model hint/dismiss/reopen,
notes draft/no write before explicit native Save/applied attribution, independent retry/
original stable object selection/later native text Preview/Save preserving finding ID,
original source after current edit and message paging28 objects. Renderer errors empty.
Earlier failed harness runs were async target-option/paging waits and exact quote locator
including timing child text; corrected harness only. No GUI semantic rewrite proposal/
Save or graphics/reorder/delete/more-than26-slide workload accepted yet.

Screenshot inspection corrected the viewport claim: basic run requested720x520 but picked
an auxiliary BrowserWindow; actual document width1187. Inspector was contained, but small
viewport acceptance is not established. Expanded harness selects the actual renderer
window, waits and asserts measured680..720 width/420..520 height, then checks overflow.
The old screenshot/result receipts are retained rather than relabeled as small proof.

Expanded real held-Start reply run3642 terminal1 exposed an actual GUI issue: cancellation
could finish cancelled while pending-Start notice remained. It also disproved the test's
assumption that fake inference had committed before Cancel. Corrected source terminal
notice: cancelled explicitly says no saved window; failed clears pending notice; completed
following user Cancel explains that storage began first and durable result remains.
All semantic buttons now use app secondary-button styling. Application change is limited
to RehearsalSemanticReview.tsx. Expanded harness now verifies actual Cancel receipt and
terminal/result count instead of assuming timing, separately waits for actual stored
analysis before too-late Cancel, and tests hidden-panel late Start cancellation/discard
while retaining committed history. Captures verified detail plus measured small viewport.

Current gui-notice-correction-freeze495/gui-notice-correction-preservation.json retains
prior495/493 unchanged/2 intended component+harness edits;417 dirty, branch/base/16 package
artifacts unchanged. Full check82382 running at check-gui-notice-correction.log; production
source frozen. No GUI/build currently live. Current built renderer is the earlier initial
GUI: rebuild after corrected full check terminal before expanded acceptance. Old schema20
packages/stores isolated from schema21. No live-model/physical/human usefulness proof.

Next: poll82382 to terminal, verify current freeze, build once, rerun expanded published
harness (do not overwrite it from older ignored gui-draft/helper). Inspect current screenshots
and actual measured viewport. Then cover real semantic rewrite proposal/Preview/Save,
original source after reorder/deletion, graphics, context stale, result/window paging,
held detail/reply selection changes and affected existing Workspace/rehearsal/claim GUI.
Active-job actual reset still has no new dedicated acceptance case; existing reset
regressions pass and deletion/close/model job barriers are tested. Broader Workspace/assets/
semantic objections/density, fidelity/integration, live Fast Decisions and official ChatGPT
acceptance remain open. Goal active; signing/clean Windows accepted debt. No staging/
commit/push/reset or package rebuild.

## Current continuation - initial semantic rehearsal GUI (2026-10-08)

IN PROGRESS. RehearsalSemanticReview is mounted independently of legacy latest10/
debrief results. Explicit paged ended Run/original message selection preserves full
original source; user chooses whole short message or exact unique <=2000 span. Prepare
shows total utterances/windows/unmapped/other actor counts and selectable paged windows.
No recorded speech disables Analyze without claiming omission. Native chart cache/table
representation limitations and unknown recording/speaker/ASR fidelity stay visible.

Analyze uses bounded start/poll/cancel jobs with captured owner/selection generations.
A late Start after selection/unmount is cancelled with captured owner; cancellation
request is distinct from terminal cancellation/committing/finishing. Poll failures leave
status uncertain and polling active; no implicit inference retries. Successful results
refresh durable history. Verified detail precedes native action and shows original quote,
unverified model reason/status/provider, one window of total, model quote references,
full supplied speech/timing and current context/source/review state. Dismiss/reopen uses
exact durable finding. Missing slide/stale/reviewed result disables native preparation.

RehearsalFinding now includes semantic_coverage/object/context fields. Parent preparation
checks current unreviewed semantic context and exact original object for text/rewrite.
Select original text object is a separate action: changing selectedTargetHandle clears
pending finding in an existing effect, so selecting and preparing simultaneously would
lose attribution. Subsequent Prepare creates draft through existing notes/text/rewrite,
Preview/explicit Save/finding-ID paths. Notes use original native quote, not model reason.
CSS wraps long source/quote/IDs and controls for constrained inspector widths.

Job full check58332 terminal1:1674 passed/1 failed in363.72sec. The failure was existing
Teach session deletion project-failure-after-app-cleanup: added Core _sessions.get read
moved injected second DB access before app cleanup and changed error to INTERNAL_ERROR.
Corrected with optional general SessionService.before_delete after its existing validation
connection closes, before app cleanup/transaction; Core injects job drain and removes
extra read. All71 affected job/Teach/Run-safety/release tests then passed unchanged.
Initial GUI props were placed on canvas checkbox; TypeScript caught it and props moved
precisely onto RehearsalFindings. Corrected desktop typecheck and lint pass.

Current gui-initial-freeze494/gui-initial-preservation.json: prior493/488 unchanged/
5 intended files (2 lifecycle correction,3 renderer/style)/1 new component;416 dirty,
branch/base/16 package artifacts unchanged. Full check76535 is running at
check-gui-initial.log; production source frozen. No build/GUI is live yet. Old schema20
packages/stores remain isolated from schema21; no GUI/live quality acceptance claimed.

Next: poll76535 to terminal and verify current freeze. Then build once, create and run
actual Electron semantic review harness per gui-implementation-notes.md and inspect
screenshots/constrained viewport. Validate actual recorded synthetic Run and provider
fixtures through sessions/messages/span/windows/Analyze/result reopening/dismiss/notes/
rewrite/current-original-object/Preview/Save, changed/deleted/reordered source, held
late reply/cancel/committing states and affected existing Workspace/rehearsal/claims GUI.
Any source repair requires new freeze/check then new build before further GUI acceptance.
Broader Workspace/assets/semantic objections/density, fidelity/integration, live Fast
Decisions and official ChatGPT acceptance remain open. Goal active; signing/clean Windows
accepted debt. No staging/commit/push/reset or package rebuild.

## Current continuation - controlled semantic analysis jobs (2026-10-08)

IN PROGRESS. Core-owned RehearsalAnalysisJobs adds public start/poll/cancel RPCs while
Sidecar transport stays serial. Read-only owned exact-context preparation precedes job
allocation; worker rechecks context and uses normal audited execution/cancellation.
Four live jobs maximum;32 in-memory records maximum with oldest terminal eviction.
Successful polling returns analysis/finding IDs only; full speech/history remain behind
verified detail. No automatic inference retries or native/review/claim creation.

Cancel and the final before_persist callback share a lock: accepted Cancel before the
committing state prevents durable storage, including the race after domain cancellation
check but before the committing callback. Committing/finished jobs report cancellation
not accepted. Only an exited worker is terminal; short finalization interval reports
finishing. Errors keep bounded safe code/generic message, without raw exception contents.
Provider success and failed/cancelled persistence remain separate audit facts.

Lifecycle drains request cancellation and bounded joins without holding job-map or DB
locks. Core close/project/source/session deletion/reset/model release wait before resource
removal. Ended-session deletion gets an explicit validated barrier (the old active-run
cleanup hook does not cover it). Timeout retains resources/job ownership and is retryable;
close timeout leaves Core open. Destructive cleanup/close purge owned terminal memory
only after workers exit, while durable saved history remains subject to normal DB cascades.

23 new job tests pass;81 combined job/analysis/store/protocol/release regressions pass.
Actual IPC start/poll/cancel/detail, provider cancellation and cancelled audit, before/
during/after commit, queued no-provider cancellation, exact callback race, foreign and
extra scope, stale native head cancellation, four-job cap, retention preserving durable
history, close/deletion successful joins, close/deletion timeout keeping original rows/
resources, and model cleanup hook are covered. Reset barrier is wired; existing reset
regressions pass, but active-job actual reset has no new dedicated acceptance case yet.
No GUI/live model/quality/human usefulness acceptance added in this phase.

Current jobs-freeze493/jobs-preservation.json: prior491/486 unchanged/5 intended edits/
2 new module-test files;415 dirty, branch/base/16 retained package artifacts unchanged.
Full check58332 is running at check-jobs.log; production source frozen during validation.
Mypy187/format/lint/types and312 desktop tests passed before Core suite began.
Old schema20 packages/stores remain isolated from schema21. No owned GUI/build is live.

Next: poll58332 to terminal and reverify jobs freeze. Then implement semantic GUI per
analysis-job-dependency-plan.md/gui-implementation-notes.md/gui-selection-plan.md.
Renderer selectedTargetHandle effect clears pending finding: select exact original object
first, then separately Prepare edit so attribution survives. Independent ended Run/message/
exact-span/window selection, controlled job polling/cancel and late Start cancellation,
verified durable detail/review, original-object routing/native Preview/explicit Save and
actual Electron acceptance remain required. Broader Workspace/assets/semantic objections/
density, fidelity/integration, live Fast Decisions and official ChatGPT acceptance stay
open. Goal active; signing/clean Windows accepted debt. No staging/commit/push/reset or
package rebuild.

## Current continuation - semantic rehearsal review inventory (2026-10-08)

IN PROGRESS. Public workspace RPCs now page owned ended Run sessions (independent of
latest10/debrief), original rehearsal-time native messages, saved semantic summaries,
strict verified result detail, and explicit Analyze through the audited domain service.
Python protocol, both desktop allowlists and ready fixture are aligned. Summaries use
the same strict stored-row/audit parser as detail and require verified detail before
review actions. Private adoption/recording guard tokens are stripped from public detail.
Read/list never invokes inference or creates reviews/native edits.

Original messages preserve complete supported native text/chart cache/table cells and
stable original source IDs/SHA/ordinal after current reorder/edit/delete. Current ordinal,
changed/missing state and actual text-editability are separate. Full safe native text
is not truncated; messages longer than2000 require an explicit exact unique quote span.
Unrepresented objects are counted; notes are excluded. Charts retain raw cache values,
not verified formatted/workbook values; table representation is row-major cell text.

19 inventory tests pass (59 earlier combined inventory/adoption/store/protocol checks
passed before3 additional inventory cases). Actual IPC selection, paging26 ended Runs,
no-debrief selection, durable Analyze/list/detail/notes Save, independent retries/review
state, strict scope, final head guard, corrupted stored row, original native tampering,
long full-message/unique explicit span, actual chart/table inventory/Prepare are covered.
No semantic GUI, live inference/model quality or human usefulness acceptance added.

Source freeze491 /inventory-correction-preservation.json retains prior489/483 unchanged/
6 intended edits/2 new files; correction changed only protocol.ts formatting.413 dirty,
branch codex/production-readiness/base657b876 unchanged,16 retained package artifacts
unchanged. Initial full check stopped at desktop protocol formatting; targeted Prettier
fixed it. Full corrected check61839 terminal0:1652 Core/312 desktop/format/lint/types/
mypy186, Core344.23sec at check-inventory-corrected.log. Current source freeze rechecked
with verify-inventory-correction-preservation.py; all16 package artifacts retained.
All owned check/test handles are terminal; no build/GUI/check live. Old schema20 packages/
stores remain isolated from schema21.

Next: analysis-job-dependency-plan.md documents real cancellable jobs before GUI.
Sidecar requests are serial: current synchronous Analyze blocks Cancel RPC handling.
Reuse audited execution cancellation in a bounded Core-owned worker service, with exact
job ownership, safe lifecycle joins before delete/reset/close and a linearized persistence
boundary. Accepted cancellation before storage prevents a saved result; already committing
must report finishing/completed, not fake cancellation. Then implement explicit original
Run/message/quote/window selection, durable detail/review, original-object text routing,
native preview/Save and actual Electron GUI acceptance from gui-selection-plan.md.
Broader semantic objections/density/Workspace/assets, fidelity/integration, Fast Decisions
and official ChatGPT live acceptance remain open. Goal active; signing/clean Windows
accepted debt. No staging/commit/push/reset or package rebuild.

## Current continuation - semantic finding native adoption (2026-10-08)

IN PROGRESS. RehearsalSemanticAdoption resolves exact durable semantic IDs before
legacy latest10/capped/debrief enumeration. Compatibility finding preserves original
native quote/source revision number/stable slide/object identity; separate semantic_review
carries unverified model status/reason/window/provider provenance and exact utterance ID/
quote digests. Rewrite explicitly excludes recorded speech text instead of truncating it;
no claims/evidence/user knowledge/native edits on proposal. Rewrite and text adoption
must target original stable native object; removed point can recover intent through notes.
Stale recording blocks rewrite/Save while its historical hint remains dismissible/reopenable.

Existing notes/text apply_rehearsal_edit now checks immutable analysis digest/own audit,
recording signature, disposition, native snapshot byte sizes/streamed hashes under the
same edit transaction. Callback executes after new head insertion: verify new head and
parent reviewed baseline, not incorrectly old head. No nested DB/migration transaction
while locked. Failure rolls back native revision/head/review and removes generated file.
No-op edits retain previous behavior (no applied disposition without actual native change).
Applied finding cannot reopen; separate explicit retries keep independent review state.

13 new adoption tests pass, plus47 affected store/Run/rewrite/objection regressions.
Actual IPC notes/text Save, dismissed/reopened history, independent retry, precise lookup
beyond12 later sessions/invalid debrief, stale recording/no provider, wrong object/no
provider, proposal native quote/model reason split with safe manifest/no approved knowledge,
recording changes during actual rewrite, late recording/review/analysis mutation inside
native commit with full rollback/file cleanup, reorder Save/current ordinal mapping and
removed object/notes recovery. Test fixture initially used text instead of current_text;
corrected fixture only. Mypy185/lint/format pass. No new GUI/live-model acceptance yet.

Current adoption-freeze489 /adoption-preservation.json, prior487/484 unchanged/3 intended
service edits/2 new module-test files;411 dirty,branch/base/16 package artifacts unchanged.
Schema21 unchanged; old schema20 bundles/stores isolated and preserved. Full check68336 terminal0:1633 Core/312 desktop/format/lint/types/mypy185,
Core349.60sec at check-adoption.log. All owned handles terminal; no check/GUI/build live.
Current freeze rechecked with verify-adoption-preservation.py; earlier freezes retained.
No GUI/live-provider/human acceptance added in this phase.

Next: .local/rehearsal-semantic-coverage/gui-selection-plan.md covers dedicated bounded
ended Run/message/result inventory, original rehearsal-time native selection after
edit/delete, Analyze/read/list protocol, typed semantic finding/original-object guard,
explicit session/point/span/window GUI through native preview/Save and actual synthetic
Run acceptance. Existing renderer preserves finding IDs but its prepareFinding callback
accepts any selected text object: add semantic original-object check before enabling
text/rewrite actions. Semantic omission PW6/human improvement, objections/visual density,
broader Workspace/assets, fidelity/integration/live Fast Decisions and official ChatGPT
remain open. Goal active; signing/clean Windows accepted debt. No staging/commit/push.

## Current continuation - durable semantic rehearsal storage (2026-10-08)

IN PROGRESS. Project schema21 adds presentation_rehearsal_analyses, an immutable,
bounded window result per successful provider run, separate from debriefs/reviews/
claims and content-free provider manifests. Own session/presentation/source/baseline
revision FKs; namespaced SHA256 finding ID; context/window/snapshot digests/bounds.
Internal Analyze now persists only after normal inference/output/current-context guards
and a final BEGIN IMMEDIATE transaction: exact privacy/acknowledgment, native head,
all final speech/Run signature, cancellation, actual managed source/baseline byte sizes
and streamed file SHA checks. No nested database reads while holding the write lock.
Provider success remains separate from failed persistence; rollback leaves no result
or finding review row. Distinct explicit retries keep distinct immutable identities.

New RehearsalAnalysisStore read verifies bounded strict JSON/digest/row identities,
successful task/run/session/native ownership, original verified source/slide/object/exact
message, quote digest and exact supplied speech windows. Reopening Core retains results.
Current reorder/native text editing updates mapping/status without rewriting history;
changed/deleted recording preserves historical hint and disables adoption eligibility.
Stored-window fabrication fails, including rehashed snapshot when actual context is
unchanged. Raw chart/table and recording/speaker/ASR limitations stay explicit.

No public Analyze/read/list protocol or GUI/adoption wiring yet. can_adopt is internal
eligibility only, not a completed native edit path. Existing findings-to-edit requires
exact durable finding resolution and a same-transaction recording guard before Save.
Original-message inventory is needed for source objects changed/deleted since recording;
current-only text target inventory cannot implement that GUI selection correctly.

Store23 focused tests pass, including Core reopen/retry, changed/absent recording,
reorder/current text edit/source tamper, strict snapshot fields, fabricated stored speech,
foreign run/session/document, successful inference plus failed storage rollback, late
privacy/speech/cancel at final storage boundary, populated actual schema20 upgrade with
native/session/utterance/debrief/claim rows retained and app.db bytes unchanged, migration
collision rollback/version/rows. Affected migration tests adjusted latest-version21 and
proper simulated-old table drops; m6 exact new-table expectation includes analyses.
Initial new fixture lacked native edit operation_type; corrected fixture only. No
provider/model semantic quality or artist/human usefulness acceptance is asserted.

Current store-correction-freeze487 /store-correction-preservation.json; previous source
freeze485 preserved469 unchanged/16 intended schema/analysis/version-expectation edits/
2 new module-test files, then2 test-only fixture corrections. Branch/base/16 package
artifacts unchanged;409 dirty paths preserved. Old schema20 package/store snapshots are
isolated and retained. Full check88416 terminal0:1620 Core/312 desktop/format/lint/types/mypy184,
Core336.83sec at check-store.log. All owned handles terminal; no check/GUI/build live.
Current preservation rechecked with verify-store-correction-preservation.py; earlier
freezes retained. No GUI check added this phase.

Next: .local/rehearsal-semantic-coverage/adoption-gui-plan.md traces original Run message
inventory, bounded list/read APIs, precise finding lookup outside legacy latest10/300
limits, dismiss/reopen/notes/rewrite/current target guard/atomic Save, protocol and actual
GUI. Broader Workspace/assets, semantic objections/visual density/human improvement,
fidelity/integration and live Fast Decisions/official ChatGPT remain open. Goal active;
signing/clean Windows accepted debt. No staging/commit/push/public release.

## Current continuation - semantic rehearsal inference foundation (2026-10-08)

IN PROGRESS. Shared providers/rehearsal_coverage_schema.py now owns the existing
coverage instruction/schema and strict shape/exact-window quote validation. Registered
presentation_rehearsal_coverage in trusted context/schema/instruction/output dispatch,
OpenAI schema selection/capabilities, inherited local capabilities/4096-token budget,
Codex derived capabilities and explicit fake abstention. Fake output is unclear/noquotes;
no keyword coverage matcher. Addressed/partially_addressed require actual supplied speech
quotes. Wrong-window IDs/fabricated excerpts/extra fields/statuses/oversized output,
repeated or overlapping ambiguous spans and overlapping duplicate references reject.
Valid exact paraphrase quotes remain unverified semantic hints, not proven entailment.

New internal RehearsalSemanticAnalysis prepares actual owned native/recorded context
again, validates expected full-context SHA/window index, routes configured provider with
privacy/remote acknowledgment, checks actual serialized context budget and delegates
to normal audited execution. Before-provider/output-validation/after-return guards
recheck source snapshot/head/native point/recording/context/privacy. Cancellation is
passed to execution. Provider manifest names original native revision/session supplied.
No native edits/claims/user knowledge/reviews are created. No public Analyze RPC/GUI yet:
durable result storage must precede the requested restart/review/edit workflow.

60 focused checks pass: context19/contract29/analysis12, including actual loopback local
transport, mocked official OpenAI SDK transport, safe fixture abstention, actual provider
execution/audit, stale input/no invocation, native reorder during inference, late speech,
privacy change, false quotes, remote local-only rejection and cancellation/no invocation.
Initial tests used an incorrect fake adapter name and head/privacy fixture fields;
corrected fixtures (actual ordered_slide_ids and privacy enum), guards unchanged.

Current source freeze analysis-freeze.json485 and analysis-preservation.json; chained
provider-contract freeze485 preserves481 prior inputs/476 unchanged/5 intended edits/
4 new files, then one head-test-only correction. Branch/base/16 package artifacts
unchanged;407 dirty paths preserved. Schema remains20. Full check49940 terminal0:1597 Core/312 desktop/format/lint/types/mypy183,
Core337.65sec at .local/rehearsal-semantic-coverage/check-analysis.log. All owned
handles terminal; no GUI/build/check live. No GUI acceptance added in this phase.
Verify current freeze with verify-analysis-preservation.py; earlier context and
provider-contract freezes are preserved historical checkpoints.

Next source chain is .local/rehearsal-semantic-coverage/storage-adoption-plan.md:
additive schema21 immutable analysis/result store, bounded strict provenance/read/restart,
paged result APIs and stable finding IDs; source/recording guards on adoption; existing
dismiss/reopen/notes/rewrite/preview/Save transaction integration; only then expose
Analyze and explicit full-window/session/point GUI. Semantic omission PW6, semantic
objection equivalence/visual density/human improvement, rich Workspace/assets, fidelity/
integration and live Fast Decisions/official ChatGPT sign-in/inference remain open.
Goal active; signing/clean Windows accepted debt. No staging/commit/push/public release.

## Current continuation - semantic rehearsal review context (2026-10-08, in progress)

Verified native message/frozen Run context and complete bounded speech windows are
implemented and exposed through a read-only preflight RPC. Stable identities retain
historical wording after current reorder/edit/delete; explicit exact spans, native
source kinds and full source/context digests preserve provenance. Whole recorded
utterances pack within the actual serialized12000-char request budget, never silently
truncate; max4 per window/pages20. Unmapped/other-actor counts remain separate from
coverage, recording completeness and speaker/ASR accuracy remain unverified. No
provider invocation, inference, review persistence or native edits on preflight.

46 focused tests/lint/types/mypy181 pass. Full check53657 terminal0:1556 Core/312 desktop/
format/lint/types/mypy181 at .local/rehearsal-semantic-coverage/check-context.log.
All owned handles terminal. Freeze481/403 dirty,479 previous/
475 unchanged/4 intended Core/protocol edits/2 new files; branch/base/16 artifacts
preserved. Provider task registration/output authority/privacy guards, durable semantic
findings/adoption and explicit Analyze/review/edit GUI remain required. This foundation
does not complete semantic omissions or PW6/human improvement acceptance. Goal active.

## Accepted continuation - outline evidence review (2026-10-08)

New workflow6 and affected GUI regressions138 pass (144 unique checks total:
Workspace117/text6/deck7/session5/conversation3/new6), no renderer errors. All owned
handles terminal. Full reader check1537 Core/312 desktop/types/mypy180 pass; later
manual-transition UI passes scoped lint/types/build and312 desktop again. Final
harness-only screenshot change passes lint/format and GUI6; claim form inspected with
current source/context/unchecked approval/disabled Save. Read-only citation provenance,
exact native point/current evidence handoff and explicit relation/confirmation/Save
are locally accepted. Fixture model proposal proves workflow, not live quality or
human preparation improvement. Bounded point binding closes that part of PW7 only.

Acceptance freeze479/401 dirty paths; prior478 unchanged/1 harness-only change,
branch/base/16 artifacts preserved. Receipts in .local/outline-evidence-links;
accepted older freezes/packages/images retained. Next: substantial semantic rehearsal
coverage/possible omissions and Workspace gaps, then fidelity/integration acceptance.
Live Fast Decisions/official ChatGPT/human evidence still open. Signing/clean Windows
accepted debt. Goal active.

## Latest continuation - cited outline to native claim review GUI (2026-10-08)

Implemented with6 actual source GUI checks passing: real stored planning citations
survive native creation edits/reorder/duplicate, exact points/current excerpts enter
claim review as unsaved context, separate confirmation/Save creates one claim, existing
links/relations are retained on reopen with approval reset, explicit relation update,
small-window707x460 at2x/no horizontal overflow and stale real reader reply discard.
Whole-outline editing explicitly becomes a manual draft and clears citations/planning
association; structured individual-slide review retains them. GUI provider proposal is
seeded through real Core with a citation fixture before app launch, not live quality.

Full reader1537 Core/312 desktop/format/lint/types/mypy180 pass; later manual UI transition
passes scoped lint/types/build and312 desktop tests again. GUI text6/deck7/session5/
conversation3 regressions pass. Workspace75924 terminal0:117 pass; exact log
.local/outline-evidence-links/gui-workspace-regression.log. Current source freeze479,
401 dirty paths, branch/base/16 package artifacts preserved. Goal remains active.
Broader semantic rehearsal/Workspace, fidelity, human outcomes, live Fast Decisions
and official ChatGPT sign-in/inference remain open; signing/clean Windows accepted debt.

## Current continuation - outline evidence reader/UI chain (2026-10-08, in progress)

Read-only native point/source candidate RPC and explicit review panel are implemented
through the Core/protocol/renderer chain. Creation review retains structured per-slide
planning IDs through final edits/reorder; reader follows original verified Point N
identities into the current revision. Changed/missing native spans are not reviewable.
Original supplied excerpt comparison is separate from full current chunk/SHA; unavailable
planning records/sources, speaker memory and overlong text cannot supply claim links.
New chosen excerpts enter the existing claim form as context with approval reset;
existing exact saved claims retain their links. Relation judgment/confirmation/Save
remain separate. Source reads/navigation never infer, approve or persist claims.

Receipt foundation check terminal0:1516 Core/309 desktop. Reader focused46 Core tests
pass, including actual reorder/edit/delete/undo, four layouts/repeated quotes/reindex,
current sources/corrupt receipts/privacy scope/bounds and no-receipt head check. All312
desktop tests pass; scoped lint/types/mypy180 pass. Broader check89271 terminal0:1537 Core/
312 desktop, recorded in .local/outline-evidence-links/check-reader-second.log (initial
formatting failure retained). See newer GUI entry for workflow acceptance; human/live
model usefulness remains unaccepted.

Reader source freeze478:473 prior/464 unchanged/9 intended edits/5 new files,400 dirty
paths; branch/base and16 artifacts preserved. Evidence at
.local/outline-evidence-links/reader-preservation.json and reader-freeze.json. Older
foundation/package receipts retained. Broad Workspace/fidelity/live Fast Decisions/
official ChatGPT sign-in and inference remain open. Signing/clean Windows accepted debt.

## Current continuation - outline evidence claim handoff (2026-10-08, in progress)

Creation now accepts bounded original planning citations per final edited slide and
records an additive original-revision/SHA/run/point receipt. An internal ingestion
initializer commits receipt with document/original revision; failure rolls back rows
and removes its new snapshot. Legacy creation/source-import authority stays intact;
no schema migration, claims, support judgment, inference or GUI change from this step.
44 focused tests/lint/format/types pass, including four layouts, citation authority,
reindex, atomic failure cleanup/retry. Full compatibility terminal0:1516 Core/309 desktop.
473-input freeze:
470 prior unchanged/2 intended edits/1 new test,395 dirty paths/16 artifacts preserved.
Read-only native object/source candidate service and complete explicit GUI review/Save
workflow are still required. See current handoff/dependency plan. Goal active.

## Current continuation - native graphic semantic claims (2026-10-08)

Native chart/table claim workflow is implemented and locally verified: separate semantic
inventory, exact quote extraction/review/Save/evidence context, typed Fast Decisions
triage, source-kind provenance/budget/cache/freshness and visible raw-cache disclosure.
Existing editing inventory/native text/counts remain unchanged; no schema migration.
Raw cached chart values are not displayed/formatted values or verified workbook data.

Current full check1505 Core/309 desktop/format/lint/types/mypy179 and build pass. Actual
graphic source GUI6 passes including PowerPoint color/data previews/native Save,
revision reapproval, exact raw quote/evidence judgment, selective cache reuse and late
reply discard. Screenshots inspected. Text extraction6/deck scan7/incremental11 GUI
regressions pass. Workspace117 also passes (21172 terminal0):147 actual GUI checks total,
no renderer errors. Provider/typed-decision adapters are synthetic; live quality/human
acceptance remain open. All owned semantic phase handles terminal.

Latest472-input GUI freeze/394 dirty paths:449 unchanged prior inputs/19 intended edits/
4 new files,16 package artifacts/branch/base preserved. Historical foundation/chain
receipts retained. Existing package predates voice/semantic changes. No staging/push.
See current handoff for evidence/handles/next actions. Goal active; broader substantial
semantics/conversation/rehearsal, fidelity/human reliability, live Fast Decisions and
human Sign in with ChatGPT/catalog/inference acceptance remain open. Signing and clean
Windows validation remain accepted debt.

## Latest continuation - voice recognition review (2026-10-08)

Temporary original ASR phrase/optional adapter-score review now reaches both Workspace
dictation paths, with64-phrase preview/count/truncation and unavailable confidence
disclosure. No accuracy threshold/calibration is inferred; cancel purges scores, and
Workspace voice stays outside durable utterance/provider rows. Renderer validates
original quotes/counts/scores against the captured transcript and keeps context/epoch
ownership. Explicit optional clarification counts toward the request limit; Use fills
the request, while provider proposal and native Save remain separate.

18 new Core cases (17 within27 focused +1 separate cancellation),12 desktop cases and
source GUI5 pass, with actual720x520 screenshot inspection. Types/mypy179 pass.
Final check1495 Core/307 desktop, format/lint/types/mypy179 and build pass. Workspace117
and latest voice5 GUI pass without renderer errors:122 checks. Actual720x520 recognition/
Use controls captured and inspected; final capture-only harness change linted/rerun.
All owned handles terminal. Latest handoff lists exact evidence and next actions.
468-input freeze/390 dirty paths,458 prior inputs
unchanged/4 intended edits/6 new files,16 package artifacts preserved. No staging/push.
Current package predates this voice feature. Automatic ambiguity resolution, calibrated
recognition/human reliability and broader production gates remain unaccepted.

## Latest continuation - frozen claims/rehearsal integration (2026-10-08)

Separate unsigned Electron44.1.0/schema20 directory bundle at
.local/workspace-loop-package/app/win-unpacked/Presenter Copilot.exe builds and passes
actual packaged GUI5 combined workflows: disposable project reopen,26-slide claim
preflight/20-row selection without inference, coverage20/6 paging, recurring-note23
groups/20-3 paging across reorder and explicit native notes Save with original finding
provenance/independent review. Synthetic sessions do not establish actual capture or
live provider claim/cache quality. Packaged Settings verifies signed-out ChatGPT,
credential-store availability/account0 and disabled Save for unavailable providers.
Codex0.153.4 pin/license/notice and restricted-PATH startup/no-orphan checks pass.

Frozen handshake confirms schema20/new capability;440 Core resources equal isolated
build hashes,462 source/test inputs and12 prior package artifacts preserved. New4
artifact hashes recorded,16-artifact preservation set; dirty384/branch/base unchanged.
No production code changed during packaging;1477 Core/295 desktop/source GUI129 remain
valid. Screenshots inspected, all owned handles terminal. See latest session handoff
and .local/workspace-loop-package for exact hashes/receipts and corrected attempts.
No staging/commit/push/user-store migration/public release. Old schema19 package stays
historical; never open upgraded stores there. OPENAI_API_KEY absent; live Fast Decisions,
human ChatGPT OAuth/catalog/inference, larger real GUI, broader fidelity and human
ASR/preparation/rehearsal acceptance remain open. Signing/clean Windows debt accepted.

## Latest continuation - explicit recurring objection review (2026-10-08)

Run Mark objection and Rehearsal recurring-note review are implemented. Exact wording
(whitespace collapsed, case/punctuation distinct) and stable slide identity must recur
across distinct ended Runs. Original observations retain independent review and source/
applied revision provenance; explicit notes/rewrite preparation uses existing Save
authority. Inspection never invokes a provider or approves a claim/remaining group.
Bounded ten Runs/1000 markers per Run,20-group pages and5-original previews disclose
truncation; late replies cannot republish across native revisions. Semantic audience
objection detection and measured rehearsal improvement remain open.

Project schema20 transactionally preserves schema19 run_markers rows/FK/index while
adding objection; migration/no-op/cascade/rollback and forward-only rejection tested.
Debrief m6-deterministic-v2 refreshes cache fingerprints. Exact finding review reaches
bounded originals beyond ordinary display caps. Final check1477 Core/295 desktop,
format/lint/types/mypy178 and build pass. Source GUI5 + coverage7 + Workspace117 =129
checks pass; final screenshots inspected.458 prior inputs:438 unchanged/20 intended
edits/4 new files;462 frozen inputs,384 dirty paths and12 package artifacts preserved.
No staging/commit/push; objection-phase handles terminal. See latest session handoff
and .local/repeated-objections for receipts and fixture limits.

Separate schema20 frozen integration builds at .local/workspace-loop-package pass;
packaged workflow acceptance passes in the newer entry above within fixture scope.
Existing schema19 package remains untouched
and predates claims/coverage/objections; do not open upgraded stores in old packages.
Broader Workspace semantics/conversation/voice, fidelity, large-deck/human acceptance,
live Fast Decisions and official human ChatGPT inference remain open. Signing and
clean Windows validation remain accepted debt. Goal active.

## Latest continuation - rehearsal density and recorded coverage (2026-10-08)

The Rehearsal inspector now offers explicit local coverage inspection for an ended
Run with a debrief. It shows native text quantity from that exact rehearsed snapshot,
recorded words/utterances/speaking time, recorded visits, and slides without recorded
speech or visits. Most-native-text/current-order sorting, explicit gap filters and
20-row paging lead to Open current slide actions. Snapshot counts remain original
through subsequent text/notes edits. Stable IDs map reordered slides; newly added
slides have unavailable original observations rather than false zeroes, and removed
slides retain source observations without a navigation action. Unmapped speech stays
separate. This enables density/coverage review; recording gaps do not prove semantic
omissions, and native word count is not a design-quality score.

Dependency reasoning binds queries to project/deck/current head and an ended owned
session/debrief. Source and current snapshots are verified against frozen SHA/size.
Native extraction counts top-level/group-child text once, including extracted native
chart/table text; it excludes speaker notes/images/visual complexity. Word counts
use whitespace-separated tokens. Strict debrief identity/nonnegative integer/ordinal/
duplicate/total validation rejects corrupt data. Current head is checked again after
inspection. Timeline and output pages are bounded. New RPC is synchronized with both
desktop method lists and shared core.ready examples. No provider invocation, database
migration, claim/evidence approval, native save or existing comparison refactor.

Renderer clears visible results on session/filter/order/revision changes and discards
held real replies by generation/remount ownership. Actual source Electron/Core/native
PPTX GUI7 passes: Run/debrief,26-slide density/gap review,20/6 paging and24-slide no-visit
filter, stable navigation, actual reorder/text edit/frozen counts, held filter reply,
held reply across GUI notes revision,720x520 containment, native SHA and claim store.
Screenshots inspected; capture/model/picker fixtures do not establish human microphone,
omission accuracy or rehearsal improvement.20 new Core cases cover read-only metrics,
filters/pages, reorder, added/removed slides, unmapped speech, invalid requests/corrupt
data and actual head mutation during snapshot inspection.28 focused cases pass with
comparison/protocol regressions. Final pnpm check1463 Core/295 desktop, format/lint/
types/mypy177 and final build pass. Full Workspace117 GUI passes without renderer
errors, total124 GUI checks this phase. All owned handles15064/40908/75360/62612/
86574/58710/44709 terminal; failed initial attempts retained. No owned GUI/build remains.

All454 prior inputs verified:448 unchanged/6 intended edits,4 new feature/test files,
458-input source freeze, dirty380 paths; branch/base and all12 prior package artifacts
preserved. No staging/commit/push/unrelated cleanup/public mutation. Receipts/logs at
.local/rehearsal-coverage/gui/result.json, gui-second.log, core-final.log,
check-initial.log, workspace.log, workspace-result.json, build-final.log,
source-freeze.json and preservation.json.
Earlier fixture point-length/footer/word-count expectations, SQL lint/type errors and
explicit reselection after save were corrected; original failures retained. Current
package remains untouched and predates claim features and this coverage workflow.
Grouped fresh integration packaging remains open.

PW6 remains partial: broader semantic omission/density/repeated-objection findings,
voice uncertainty, richer conversation/semantic refresh and demonstrated human
improvement remain open. Larger real native GUI/performance, observed70% preparation,
broader fidelity and live/human acceptance remain open. OPENAI_API_KEY rechecked
absent; live Fast Decisions inference/calibration/latency and official human ChatGPT
OAuth/catalog/model inference remain unaccepted. Physical microphone/ASR/presenter
acceptance remains open. Signing and clean Windows validation are accepted debt.
Goal active.

## Latest continuation - incremental native claim scan refresh (2026-10-08)

Deck review now offers explicit Refresh changed text after native revisions. A bounded
app-session cache matches stable slide IDs, ordered object IDs, full native text SHA
and Python code-point window offsets. Every reused candidate is rechecked against
fresh current native text before display. Original provider revision provenance is
retained; cached suggestions do not become new inference or automatically approve
inherited claims/evidence. Existing Prepare deck claim scan explicitly forces fresh
analysis and separate disclosure. Changed windows alone need provider requests.
Notes-only edits and stable slide reordering reuse unchanged text windows. This is
exact-input claim reuse, not broader incremental semantic analysis.

Dependency reasoning keeps the cache in Presentation Workspace outside revision-keyed
Deck review remounts. Visible results, disclosure and individual approval still reset
on revision changes. Cache is project/document scoped, memory-only and bounded to3
scopes/1000 batches/1M quote characters per scope. Native current-head and generation
checks discard held old replies. Selected-scope results and request counts stay aligned.
Slide selection and candidates paginate20 rows, with bulk selection and current native
slide/window result ordering. Set-based deduplication removes quadratic overlap lookup.
No Core/provider/protocol/config/dependency changes or automatic claim/PPTX saves.

Actual source Electron/Core/native PPTX GUI11 passes on26 slides/28 initial requests:
paged selection/results, explicit disclosure, insertion and reviewed native text change
each send only1 changed request, notes-only edits/reorder send0, original provenance,
existing claim ID/fresh approval/source SHA,720x520 containment and a held actual
preflight reply across a GUI revision are verified. Total30 fixture model calls.
Screenshots inspected. Existing single-claim6 and deck7 GUI regressions pass.
Final pnpm check1443 Core/295 desktop, format/lint/types/mypy176 and final build pass.
Full Workspace117 GUI passes with no renderer errors; total141 GUI checks this phase.
Owned current handles43944/75280/26451/13867/84084/93471 terminal. Earlier failed runs
are terminal; no GUI/build process remains owned by this continuation.
15 helper tests include5000-slide duplicate handling, cache bounds, identity/hash/span
changes, malformed quotes, code-point offsets and fresh/reused result ordering. The
5000-slide helper test does not establish large native-deck GUI performance.

All451 prior inputs verified:448 unchanged/3 intended renderer edits;3 new files,
454-input freeze, dirty376 paths. All12 prior package artifacts, branch/base preserved.
No staging/commit/push/unrelated cleanup/public mutation. Receipts under
.local/incremental-claims: gui/result.json, gui-fourth.log, claim-regression.log,
deck-final.log, workspace-final.log, workspace-result.json, check-fourth.log,
build-accepted.log,
source-freeze.json and preservation.json. Earlier harness missing notes/unused variable,
format/type failures and the discovered result-order issue are retained in logs;
fixes preserve checks. Prior native canvas package remains untouched and predates
all claim discovery/scan/reuse features; grouped fresh package integration remains open.

Next substantial features: broader native/multimodal semantics, semantic refresh beyond
exact text inputs, conversation/voice ambiguity and rehearsal findings. Larger real
GUI performance, observed70% preparation, broader fidelity and live/human acceptance
remain open. OPENAI_API_KEY rechecked absent: Fast Decisions live inference/calibration/
latency remains unaccepted. Official human ChatGPT OAuth/catalog/model inference and
physical microphone/ASR/presenter acceptance remain open. Signing and clean Windows
validation remain accepted debt. Goal active.

## Latest continuation - full-deck native text claim scan (2026-10-08)

Deck review has a local paged all-slide preflight, explicit native text exclusions,
slide selection/request-count disclosure and separately acknowledged serial inference.
Dense available objects use overlapping bounded windows; batch sizing includes the
actual escaped serialized12K context budget. Core window/hash/bounds/current revision/
privacy and unique exact quote validation preserve source-only disclosure and existing
human-confirmed save_claim authority. Quotes/SHA refer to complete native objects.
Renderer rechecks fresh native text, discards late real replies, resumes completed
batches after fresh acknowledgement, deduplicates overlapping quotes and hands each
candidate to individual Purpose review on its exact slide. Repeated selection resets
approval/reuses existing claim/evidence. Actual revision changes clear the whole scan.
Stopped requests may finish/be repeated; UI discloses this. No automatic claim/deck save.

Final full check1443 Core/280 desktop, format/lint/types/mypy176/build passes. New12
scan tests include26-slide paging/single inspection, dense windows, unavailable text,
invalid spans, escaped budgets, undisclosed quote rejection and actual stale revision.
Actual source GUI7 plus existing claims6 and Workspace117 pass, no renderer exceptions;
final screenshots inspected. Model/ASR/picker fixtures establish workflows, not live
model quality. Initial format/loop-binding lint and fixture/harness errors corrected;
logs retained. Receipts at .local/deck-claims/gui/result.json, workspace-result.json,
check-final.log, claim-regression.log, build-final.log and preservation.json.

447 prior inputs:437 unchanged/10 intended changes;4 new files,451-input final freeze.
All12 prior artifact hashes, branch/base and dirty373 paths preserved; owned handles
terminal. No staging/commit/push/unrelated cleanup/public mutation. Accepted package
predates both claim features. Native text unavailable under the safe8000-character
ceiling/inventory limits is reported; notes/images/chart visuals are not analyzed.
Broader semantic/native coverage, large-deck performance, incremental refresh, voice/
rehearsal, fresh package integration, broader fidelity and observed70% preparation
remain open. Live extraction quality, Fast Decisions inference/calibration/latency
and official human ChatGPT OAuth/catalog/inference remain open; OPENAI_API_KEY rechecked
absent. Physical microphone/ASR/presenter gates remain open. Signing/clean Windows are
accepted debt. Goal active.

## Latest continuation - reviewed native text claim discovery (2026-10-08)

Purpose / Claim and evidence review now finds unsaved exact quotes in1-8 explicitly
selected current native text objects, up to6000 total characters. Separate native
decision_text targets cover read-only/multi-run text without changing browser editing
permissions. Selected reasoning provider receives only those object IDs/text through
existing privacy/audit execution; notes, evidence, knowledge and speaker/style context
are excluded. Strict schema and exact unique quote/current revision/privacy binding
reject malformed/stale results. Empty results are allowed. Existing human-confirmed
save_claim owns persistence; candidate selection only prefills review, reuses an
existing exact claim/evidence and resets approval. Renderer rejects late replies
after navigation/revision and validates returned quotes. Main IPC timeout60s covers
the bounded30s provider task. Finite Fast Decisions triage is unchanged.

Final pnpm check1431 Core/280 desktop, all format/lint/types/mypy175 and final build
pass. New15 Core cases include disclosure, invalid output, privacy/revision races
and real loopback strict-schema/empty-result transport. Actual source Electron/Core/
PPTX GUI6 workflows pass; full Workspace regression117 passes without renderer
exceptions. Native read-only dense text, explicit Save/source SHA, existing claim
reuse, actual revision invalidation, held real reply/navigation, tampered quote/
retry and minimum-window review/dismissal are covered; screenshots inspected.
Model/ASR/picker fixtures do not establish live model extraction quality. Initial
full check1430 passed/1 failed on the missing shared core.ready example RPC; example
corrected,7 focused protocol tests and final full check pass. Failure logs retained.
Receipts at .local/claim-extraction/gui/result.json, workspace-result.json,
check-accepted.log, build-accepted.log and preservation.json.

440 prior source/test/config inputs preserved except12 intended changes;428 unchanged.
Five new feature/test files and two preexisting README/icon inputs extend freeze to447.
All12 old package artifact hashes, branch/base and dirty369 paths preserved; no
staging/commit/push/unrelated cleanup/public mutation. Owned handles terminal.
Accepted native-canvas package predates this feature and remains untouched.
Full-deck extraction/semantic coverage, incremental refresh, conversation/voice and
rehearsal findings, fresh grouped integration, broader fidelity and observed70%
preparation remain open. OPENAI_API_KEY rechecked absent; live Fast Decisions and
official human ChatGPT OAuth/catalog/inference remain open, alongside physical
microphone/ASR/presenter acceptance. Signing/clean Windows are accepted debt. Goal active.

## Latest continuation - fresh native canvas package integration (2026-10-08)

Builds a new isolated unsigned unpacked app at
.local/native-canvas-package/app/win-unpacked/Presenter Copilot.exe. Dependency
reasoning requires a fresh frozen Core for the new native-layers CLI, then matched
main/preload/renderer assets and actual package GUI acceptance. Previous packages
remain intact; no shared sidecar/artifact replacement. Full source pnpm check
passes1416 Core/280 desktop tests, all format/lint/types and mypy173 source files.
Fresh PyInstaller Core and Electron44.1.0 app builds complete; schema19 remains.
All440 built Core resources match their bundled copies. Pinned Codex0.153.4 hash,
version and LICENSE/NOTICE checks pass.

Actual packaged Electron/frozen Core/PowerPoint acceptance passes35 GUI workflows:
drag guides4, resize guides5, spacing guides6, live bitmap canvas7, native layer
IPC/revision race3, and saved/staged native appearance10. Geometry, transparency,
paint order, reviewed Save SHA, byte-restoring Undo, multi-selection, grid/Alt/Shift,
cancellation, late real worker replies, mode/navigation/revision invalidation,
image failure/retry/URL cleanup, native resize review/discard and minimum-window
containment pass. No fake native pixels. Packaged live-canvas pixel proof matches
the source result: old position(217,87,87) becomes(255,255,255), foreground remains
(176,223,189). Normal packaged interaction pixels inspected. Picker/unused model
and ASR boundaries remain fixtures where permitted; no live inference claimed.
Receipts at .local/native-canvas-package/gui-summary.json and route result.json/logs;
native appearance result copied into the phase directory.

Packaged signed-out Settings exposes OpenAI Decisions and Continue with ChatGPT,
keeps decision provider disabled, and confirms DPAPI available with zero accounts.
This proves UI/credential-store availability, not OAuth/catalog entitlement/inference
or provider-server health. Startup smoke before/after GUI uses restricted PATH and
leaves zero orphaned Core processes. Codex-bundle.json, settings.json, smoke.json
and smoke-final.json retained. Initial receipt aggregation incorrectly expected11
native appearance cases (source count); package runs10 because deterministic Copilot
is deliberately source-only and production disables dev provider fixtures. Corrected
count without modifying any GUI assertion; source Copilot case remains covered by
prior source11, packaged live-provider acceptance remains open. Windows PowerShell5
redirected logs were UTF16; owned logs normalized to UTF8 with raw originals retained.

440 source/test files, bundle-input hashes, all440 frozen Core resource hashes and
all12 prior/new package artifact hashes match after acceptance. Dirty status364 paths,
branchcodex/production-readiness and baseSHA657b876739ff7a1cc5709a7e28e92ec2551b337e
preserved. No source/config/dependency edits, staging/commit/push/unrelated cleanup
or public mutation. Owned handles2032/40153/48469/92342/39779 terminal0. Exact artifact
hashes and preservation receipt at .local/native-canvas-package/artifact-receipts.json
and preservation.json. This package now contains the guides and complete native
layer worker/API/canvas chain; older packages still predate it.

Next: prioritize substantial remaining semantic/conversation/rehearsal Workspace
features and GUI workflows, then broader fidelity/integration and observed preparation
acceptance. PW2 observed70% preparation gate is still open. Process OPENAI_API_KEY
availability rechecked false; live Fast Decisions inference/calibration/latency and
official human ChatGPT OAuth/catalog/inference remain unaccepted. Physical microphone,
ASR quality/latency and human rehearsal gates remain open. Signing and clean Windows
are accepted debt. Goal active.

## Latest continuation - live native bitmap canvas (2026-10-08)

Completes the saved-slide live dragging chain in the renderer. Dependency reasoning
keeps native image identity tied to project/document/revision/SHA/slide, owns prepared
blob URLs by generation, rejects late responses before URL allocation, and disposes
replaced/failed/unmounted assets. All background/object images must load at verified
native dimensions before replacing the saved preview. Ordered full-slide transparent
layers translate only for active move operations, using the same guided geometry
as existing staged review. Transparency and paint order remain intact; resize keeps
saved native pixels static while geometric ghosts change, then renders the actual
resize in PowerPoint review. Existing native saved/proposed appearance defaults
remain intact; mode selection stops live layers and native rendering shares busy
controls. Cancel preparation abandons UI ownership while the worker finishes safely.

Prepare/refresh/stop controls expose truthful saved-pixel status and image failures
fall back to the normal preview. Native-layer identity/image limits and URL cleanup
have ten new focused cases; all280 desktop tests pass. Final types/lint/format/build
pass. No Core/provider/database/writer/dependency changes from the previous1416-case
full check. Real Electron/Core/PowerPoint test-live-canvas.mjs passes7 workflows:
translucent object movement removes the original pixels while foreground overlap
remains unchanged; exact reviewed native Save/Undo preserves source bytes and size;
Escape restores baseline; multi-selection shares guided offsets/internal spacing;
resize pixels remain byte-identical before native preview/discard; Browser revokes
all blob URLs; image failure/retry/navigation invalidation; delayed real native
reply after Cancel is discarded;720x520 multi-object review/discard remains contained.
No fake native pixels or model calls. Picker/unused provider/ASR boundaries are fixtures.
Receipts/pixels at .local/native-live-canvas/gui/result.json, pixel-proof.json and
gui-accepted.log. Pixel proof: old position moves from(217,87,87) to(255,255,255);
foreground remains(176,223,189). Normal interaction/native review pixels inspected.

Sequential native appearance regression passes11 checks with no renderer errors,
including saved/staged manual/Copilot, image readiness, revision/navigation, late
reply, failure/retry and minimum-window workflows. Receipt at
.local/native-appearance/native-live-canvas-source-20261008/result.json. Full source
Workspace integration: 117 workflows pass with no renderer errors; receipt copied to
.local/native-live-canvas/workspace-result.json, workspace-regression.log retained. Initial GUI pixel failure was the selection
SVG overlay: screenshot style did not hide it in Electron. Test now hides/restores
its opacity only for pixel capture, retaining normal interaction screenshots and
strict pixel assertions. Added resize test initially used Cancel after preview;
actual contract is Discard preview, corrected without production changes. Initial
failure logs retained. Final harness formatting changes only line wrapping; worker hook resolves beside
the launched app native module for packaged acceptance. Source path is identical;
packaged branch remains unaccepted.

440 source/test freeze:433 of436 previous entries unchanged, three intended renderer
files modified and four new hook/asset/test/GUI-script files. All8 prior package
artifacts and branch/base preserved. No staging/commit/push/unrelated cleanup or
public mutation. All owned handles terminal0 (49325/42738/1678). Current package still predates all guides and native
layer Core/API/canvas changes; fresh frozen Core and app integration required.

Next: grouped fresh Core/app integration, then remaining substantial Workspace
semantic/conversation/rehearsal workflows and broader fidelity/live/human acceptance.
PW2 observed70% preparation acceptance remains open. Current process OPENAI_API_KEY
availability rechecked false; Fast Decisions inference and official human ChatGPT
OAuth/catalog/inference remain unaccepted. Physical microphone/ASR/rehearsal gates
remain open. Signing and clean Windows are accepted debt. Goal active.

## Latest continuation - privileged native layer desktop boundary (2026-10-08)

Connects the verified native layer worker through main/preload with a typed nativeLayers
API. Dependency reasoning requires a full saved identity, main-owned temporary
copies, validated image assets and a current-head check after slow rendering.
Caller paths/unknown request fields are rejected. The desktop verifies exact
source/document/slide identity, baseline error0..4, layer/dimension/memory budgets,
expected generated basenames, regular nonsymlink files, PNG signature/IHDR/dimensions,
byte counts and SHA for every image, and unique UUID/OOXML identities in returned
paint order. Only verified typed bytes/identity metadata are exposed, never paths.
A second expected-head Core export after asset reading rejects concurrent revisions.
All private files are removed after terminal worker/error handling.

Ordinary saved/staged native appearance and layers now share an idempotent render
lease; existing native preview busy behavior is retained. Worker transport adds
only explicit layers mode, preserving prior PDF/preview flags and16KiB response
bounds while allowing a256KiB bounded layer receipt. Existing owned-worker pool,
credential environment filtering and app-shutdown handling apply. No Office Quit
or shared settings changes. Core/source writer/provider/database/dependencies are
unchanged from the previous1416-case full check.

Thirteen focused desktop boundary cases/all270 desktop tests pass. They cover
verified image return/private cleanup, hostile paths, changed hashes/dimensions,
source/document/baseline mismatch, duplicate/count receipts, initial/final stale
head rejection and shared lease release on failure. Final lint/format/types/build
pass. Real Electron/preload/Core/PowerPoint test-native-layers.mjs passes3 checks:
verified native images and exact catalog IDs/order/source SHA without mutation;
held real worker shares the lease while explicit GUI reviewed Save changes the
head, causing final layer preparation to reject stale revision and remove its
private directory; one Undo restores baseline bytes and a retry succeeds. No fake
native pixels. Picker/unused model/ASR boundaries are fixtures; no model calls.
Receipts at .local/native-live-desktop/gui/result.json and gui-accepted.log.

Sequential source native appearance regression passes11 checks, including saved
native selection/navigation/revision pixels, manual/deterministic Copilot staged
review, delayed replies, failure/retry and minimum window. Receipts at
.local/native-appearance/native-live-desktop-source-20261008/result.json. Owned
handles91384/85183 terminal0. Initial copied GUI harness reused deadline identifier
and failed before launch; renamed with no assertion change, log retained. Lint
removed two unused imports after functional checks; final emitted native-layers.js
hash is byte-identical to the accepted runtime. No repeated GUI run needed for
those nonfunctional removals.

436 source/test freeze:427 of432 prior files unchanged, five intended main/preload/
shared files modified and four new main helper/lease/test/GUI-script files. All8
previous package hashes preserved; branch/base and dirty worktree preserved.
No staging/commit/push/cleanup of unrelated work/public mutation. All owned handles
terminal. Current package predates all guides, native Core worker and desktop API.

Next: full revision/slide/mode URL ownership and cancellation in a renderer layer
hook, ordered canvas layer translation from the existing guided operations, then
actual live-pointer visual/overlap/alpha/cancellation/navigation/late-reply and
exact Save/Undo acceptance. No live bitmap canvas UI yet; the API/native boundary
checks do not substitute for that acceptance. Grouped fresh Core/app integration,
fidelity and human workflows remain open. Current process OPENAI_API_KEY availability
rechecked false; Fast Decisions live inference and official human ChatGPT OAuth/
catalog/inference remain unaccepted. Signing/clean Windows accepted debt. Goal active.

## Latest continuation - verified native layer worker (2026-10-08)

Traces the live bitmap movement dependency chain before GUI edits. Cropping the
saved bitmap would drag background pixels, leave the old object behind and change
paint order. Owned real PowerPoint probe tested transparent shape export grouped
with a slide-sized anchor: exports were970x549 for a960x540 slide, with padding and
unreliable object placement. That approach is not shipped. Full-slide black/white
native mattes retain coordinates and recover transparent RGBA objects over an
actual saved native background rendered with slide objects hidden. Ordered native
compositing handles transparency, text, shadows, rotation and overlapping foreground
objects in the authored fixture. Baseline/moved comparisons have maximum channel
error2; MAE0.0180742/0.00967593 and0% pixels exceeding8 per channel. Fixture bytes
unchanged. Probe receipts/pixels/scripts at .local/native-live-probe; initial padded
export evidence retained. Microsoft Shape.Export documentation inspected.

New standalone --native-layers-export worker reuses validated copied-source archive
security and immutable fidelity identities, verifies native slide dimensions,
shape IDs and paint order, creates same-size transparent PNG layers/background,
then rejects any composition differing from the saved native baseline by more than
4 on any RGB channel. This gate does not substitute a low average for an affected
object. Unknown/invalid jobs and existing/outside outputs rejected. Limits:200 root
objects,256MiB decoded layer/background buffers,16MiB per PNG,96MiB total generated
PNG budget; tall/dense slides can hit the decoded limit earlier. Reads only the
privileged owned source; opens read-only/windowless, changes only that in-memory
presentation, never saves/quits/changes shared Office settings, closes its owned
deck and checks source SHA after closing. Alpha-inconsistent objects reject with a
normal-preview fallback message. Errors omit raw Office exception/path content.
No existing protocol/provider/database/renderer behavior changed; CLI gains only
the explicit worker branch. Desktop GUI is not wired to this worker yet.

Focused layers/preview/PDF56 tests pass before two final budget cases; final module
ruff and focused mypy pass. Final worker process exits0 with5 real native layers,
stable UUID/OOXML IDs and baseline maximum channel error2;4.191s wall time including
Core startup, source unchanged. Receipt .local/native-live-probe/worker-final-run.json.
New worker and process probes are not GUI/live-pointer acceptance. Full pnpm check
passes:257 desktop/1416 Core tests, all format/lint/types and mypy173 source files.
Owned handle37229 exits0; check.log retained. All owned handles terminal. Initial test
collection from repository root lacked presenter_core on the module path; rerun
from core passed, no source/test assertion relaxation. Initial ruff long error
message wrapped; final lint clean.

432 source/test freeze:429 of430 prior files unchanged; only __main__.py modified
plus new native_layers.py/test_native_layers.py. All8 prior package hashes preserved.
Current package predates all guides and this new Core worker; frozen Core needs a
fresh build after the live bitmap integration chain is finished.

Next: privileged desktop IPC/verified asset reads, full saved-revision/slide image
identity and URL ownership, then canvas translation of ordered native layers and
real GUI cancellation/late-reply/navigation/Save/Undo acceptance. Resizing must keep
native review: simply stretching layer pixels changes text/effects and is not an
accurate geometric resize. Live bitmap GUI, substantial remaining workflows,
grouped package/integration/fidelity and live/human acceptance remain open. Fast
Decisions and official human ChatGPT OAuth/catalog/inference unaccepted. Signing
and clean Windows accepted debt. Dirty worktree/branch/base preserved; goal active.

## Latest continuation - equal-spacing canvas guides (2026-10-08)

Adds paired equal-gap markers to the existing optional canvas guide control while
dragging a selection between two nearby objects or continuing their spacing before
or after a row/column. Dependency reasoning keeps geometry in guidedTranslation,
shared by pointer ghosts and staged review, with one whole-selection offset through
existing translationOperations. Dimensions/internal spacing, bounds, revision and
expected-geometry preconditions remain intact; keyboard/disabled/Alt grid behavior
is unchanged. Eligible references must be editable, valid/in-bounds and share a
common cross-axis lane. Candidate placements must fit without reference overlap.
Orthogonal guide changes revalidate both gap witnesses against final offsets;
invalid witnesses fall back to alignment. Nearest proximity wins; an edge/spacing
tie at the same exact offset shows the paired gap witnesses. Gap positions override
grid only on their axis; rounding permits at most1 EMU difference between gaps.
No Core/protocol/database/writer/provider/dependency changes.

Nine new focused tests/all257 desktop cases pass, including horizontal insertion,
before/after continuation, vertical insertion, multi-selection geometry, disabled
behavior, invalid/off-lane/overlap/bounds rejection, final lane invalidation and
edge-gap ties. Final lint/format/types/build pass. Actual Electron/Core/PowerPoint
GUI passes6 checks: five exact native equal-gap Save/reopen/Undo cases (between,
before, after, multi-selection and vertical); Escape/Alt and720x520 contained discard.
Reviewed Save SHA and one exact byte-restoring Undo checked. Guide/native pixels
inspected. Real rendering/bytes; picker/unused model/ASR boundaries are fixtures.
No model calls. Receipts at .local/spacing-guides/gui/result.json and
gui-final-accepted.log under the same phase directory.

Initial GUI fixture failures preserved in gui-initial.log, gui-tie-failure.log and
gui-wide-selection-failure.log plus screenshots: a column object occupied the row
continuation, the separated fixture exposed a real equal-offset edge/gap display
tie (fixed with numerical regression), and a two-object selection exceeded its
reference gap. Final fixture separates the column and provides a valid positive
multi-selection gap; overlap/bounds/geometry/Save/Undo assertions were not relaxed.
Initial typecheck identified gap narrowing lost inside a nested tick callback;
fixed within the outer gap guard, final types pass.

430 source/test freeze:424 of427 prior files unchanged, three intended helper/UI
changes and three new spacing helper/test/script files. Previous8 package artifact
hashes preserved. Existing drag/resize guide GUI regressions pass4/5 checks respectively, with no
renderer errors and exact native geometry/Save/Undo, sequential owned handle62521
exits0. Receipts at .local/spacing-guides/drag-regression/result.json and
.local/spacing-guides/resize-regression/result.json. All owned handles terminal. Prior source Workspace119/native11
passed before these spacing edits; no rerun of those broad suites claimed here.
Current package predates drag/resize/spacing guides.

Next: live bitmap movement dependency chain and substantial remaining workflows;
group source changes for a fresh package/full integration sweep, then broader
fidelity and live/human acceptance. Fast Decisions and official human ChatGPT
OAuth/catalog/inference remain open. Signing/clean Windows accepted debt. Dirty
worktree/branch/base preserved; no staging/commit/push/public mutation. Goal active.

## Latest continuation - resize alignment guides (2026-10-08)

Extends the optional canvas guides to moving resize edges, using one guidedResize
calculation for pointer ghosts and the final staged review. Dependency reasoning
keeps the existing resizeOperations as the authority for opposite anchors, member
minimum sizes, whole-selection bounds and Shift corner proportions. Eligible
slide/object edge/center targets are checked against ungridded pointer geometry;
a candidate must actually reach its guide after constraint and rounding checks.
Guide hits override grid only on an active aligned axis. Shift corners choose one
uniform scale; independently forcing both axes would distort the selection.
Alt bypass, disabled guides and keyboard resizing retain existing grid behavior.
No Core/protocol/database/writer/provider/dependency changes.

Eight focused resize tests and all248 desktop tests pass, including minimum-size
and proportional slide-bound rejection. Lint/format/types/build pass. New actual
Electron/Core/PowerPoint test-resize-guides.mjs passes5 GUI checks: all eight handles
cancel with Escape; single, multi-object and Shift-proportional resizing preserve
exact guided native edges/opposite anchors, reviewed Save SHA and one byte-restoring
Undo; Alt bypass retains grid and720x520 review remains contained/discardable.
Guide and actual native review pixels inspected. Real native rendering and bytes;
picker/unused model/ASR boundaries are fixtures. No model calls.
Receipts at .local/resize-guides/gui/result.json and gui.log.

Full source Workspace119 passes with no renderer errors; sequential native
appearance11 passes (9 saved plus staged manual/deterministic Copilot). Owned
handle74618 exits0. Receipts at .local/resize-guides/workspace/result.json and
.local/native-appearance/resize-guides-source-20261008/result.json. Focused shared
drag-guide regression passes4 native workflows with no renderer errors; owned
handle31944 exits0, receipts at .local/resize-guides/drag-regression/result.json.
427 source/test freeze:421 of425 prior files unchanged, four intended existing
helper/UI/script changes and two new resize test/script files. All8 prior package
artifact hashes match. All owned handles are terminal. Current package predates drag and resize guides.

Equal-spacing guides, live bitmap movement, broader authoring/fidelity integration,
live Fast Decisions, official human ChatGPT OAuth/catalog/inference and human
workflow acceptance remain open. Signing/clean Windows validation accepted debt.
Dirty worktree/branch/base preserved; no staging/commit/push or public mutation.
Goal remains active.

## Latest continuation - canvas alignment guides (2026-10-08)

Adds optional direct canvas drag alignment to slide edges/centers and nearby
supported movable object edges/centers. Current roadmap/source inspection showed
fixed0.1-inch grid snapping but no alignment guides. Dependency reasoning identified
that canvas ghost geometry and final staged move previously calculated grid offsets
separately: applying a second grid round after guide snapping could change the
reviewed position. New shared guidedTranslation is used by both ghost and final
move paths and reuses whole-selection translation validation. Guide hits override
grid only on the aligned axis; other axes keep grid behavior. Matching uses the
ungridded pointer within6 CSS pixels, separately scaled on each axis. The nearest
eligible in-bounds target wins deterministically. Read-only/invalid/off-slide
references are excluded. Selection spacing, dimensions, paint order and existing
Core expected-geometry/revision checks remain unchanged. No protocol/database/
writer/provider/dependency changes.

The new checkbox starts off. Dashed magenta guides show the resolved alignment
while dragging one object or the whole selection. Alt bypasses guides while keeping
grid snapping. Escape, pointer cancellation/lost capture, image/revision/slide,
grid/guides and enabled changes clear guide/ghost state. Final movement still opens
the existing native staged review and requires explicit Save; no mutation during
drag. Existing resize behavior is unchanged. This closes drag edge/center snapping;
resize/equal-spacing guides and live bitmap movement remain separate open work.

Nine focused numerical tests and complete desktop240 tests pass, along with final
lint/format/types/build. Core unchanged from previous1398-case full check; no repeated
Core run claimed. New test-canvas-guides.mjs passes4 real Electron/Core/PowerPoint
GUI workflows: single and multi-object edge alignment despite grid rounding; two-axis
slide centering over actual PowerPoint baseline; Alt bypass/Escape cancellation and
720x520 multi-object discard. Exact saved package SHA, reopened native coordinates,
selection spacing and one exact Undo are checked. Magenta edge/center guide pixels
inspected. Browser/native renderers and bytes are real; picker/unused model/ASR are
fixtures. No model calls. Receipts at .local/canvas-guides/gui/result.json and logs.
Initial harness issues were an incorrect inventory RPC name, treating zero-width
SVG lines as visibly boxed elements, and a bypass distance depending on viewport
scale. Corrected to actual list_text_targets, attached-line plus exact coordinate
checks and an explicit4.31-inch bypass request expected to grid-round4.3 inches.
Assertions retain exact metadata/Save/Undo; no production threshold relaxation.
Unused copied helper removed for lint without changing exercised paths.

Full source Workspace9814 exits0:119 workflows including native footnote checks,
no renderer errors. Saved/native regression45733 exits0:11 checks (9 saved plus
staged manual/deterministic Copilot), including selection bounds, browser switch,
navigation, explicit native failure/retry and delayed replies. Receipts at
.local/canvas-guides/workspace and .local/native-appearance/canvas-guides-source-20261008.
425 source/test hashes match after acceptance:419 of422 prior files unchanged,
three existing UI/style files modified and three new helper/test/script files.
All8 artifact hashes from both previous packages preserved. All owned handles
terminal. Dirty checkout/branch/base SHA preserved; no staging/commit/push, unrelated
cleanup or public mutation. Current package predates this source feature.

Next: remaining substantial canvas/authoring workflows, including resize/equal-gap
guides and the live bitmap interaction dependency chain; integrate grouped source
changes into a fresh package, then broader fidelity and real/human acceptance.
Live Fast Decisions and separate ChatGPT OAuth/catalog/inference remain unaccepted;
credentials/human official browser completion are still required. Signing and clean
Windows validation remain accepted debt. Production goal stays active.


## Latest continuation - packaged native review integration (2026-10-08)

Closes package staleness for the three chart presentation dialogs, five table
dialogs and five remaining staged-review dialogs. Dependency reasoning verified
the422-entry source/test freeze, copied the unchanged validated frozen Core into
isolated staging with all440 resource hashes checked, rebuilt the desktop, then
packaged those exact outputs with pinned Codex. Production source/config untouched.
No new Core build or test run claimed: Core files are unchanged from the prior
fresh1398-case full check; desktop231/types/lint/format and source Workspace119
acceptance from the immediately preceding frozen source remain applicable.

Fresh unsigned unpacked Electron44.1.0/schema19 bundle at:
.local/native-review-package/app/win-unpacked/Presenter Copilot.exe.
Artifact receipts record absolute paths/size/hash. New executable SHA:
e7983ad27ecc6f3014124ea32ab66095b0f1981fc89b7f8ecc65fc224f24d84a;
app.asar3a4a5c5271e0b29c4a1a9f89909685d99e0c015f2cc746107a4f7e30597745fb;
Coreaa66a72e3cc5cb58388a652e50539bea9e639c4e95bd99ae7806386f1ddcb7ca;
Codex444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b.
Core and Codex executable hashes equal the previous package. Reused frozen Core
resources are byte-identical in both staging and packaged resources. Build/package
6250 exits0. Initial builder invocation ran before staging finished writing its
owned config and stopped with ENOENT; log retained as package-initial.log. Rerun
started only after staging20250 exited0; no source or assertion change.

Actual packaged Electron/frozen Core/PowerPoint acceptance passes54 GUI workflows:
14 across text-fit/diagram create-update-delete/authored insertion/appendix move-copy;
16 across table create/data/structure/formatting/borders/fit/merge/split;
12 across column/bar/line/pie colors plus axes/legend;10 native-appearance regression
cases (9 saved plus staged manual; no deterministic Copilot model in the package);
2 direct evidence-footnote workflows. Matrix31697 and footnote15991/16809 exit0.
Exact proposed ordinals, fresh image and changed-and-returned draft approval,
reviewed-byte Save/reopened metadata/Undo,720x520 containment, pending Save/approval
and held native replies after Discard pass. Native worker bytes are real, not mocked;
only picker/unused model/ASR boundaries are fixtures. No model calls.

Owned test-footnotes.mjs creates and imports a synthetic deck plus supporting
Markdown, searches project evidence, manually confirms a supports relation and
saves the reviewed claim through GUI. It then verifies exact native footnote review,
Save, stale claim state, Undo, minimum window and held Discard. No provider required.
Its fixture explicitly enables text wrapping for readable native claim pixels;
initial successful non-wrapping fixture log retained. Assertions unchanged. Final
native screenshot inspected: two-line claim and bottom citation remain readable.
Receipts at .local/native-review-package/gui/*/result.json,gui-summary.json and logs;
saved/staged regression at .local/native-appearance/native-review-package-20261008.

Initial and final packaged startup smoke exit0 with0 sidecars before/after, no
orphan/model download. Final smoke runs after all GUI checks. Codex0.153.4
version/hash/license/notice pass. Packaged signed-out Settings probe confirms DPAPI
store availability,0 accounts, native Decisions and separate ChatGPT plan choices,
Fast Decisions selected disabled and signed-out plan Save disabled. No live OAuth,
catalog entitlement or inference acceptance implied. Credentials still unavailable
for live Decisions; human official browser completion remains needed for ChatGPT.

After acceptance all422 source/test hashes,440 reused Core resource hashes and
all8 new/previous artifact hashes match. All owned handles terminal.346 dirty paths,
branchcodex/production-readiness and baseSHA657b876739ff7a1cc5709a7e28e92ec2551b337e
preserved. No staging/commit/push, unrelated cleanup, installer or public release.
Signing and clean Windows validation remain accepted debt. Goal remains active.

Next: inventory substantial remaining Workspace authoring/GUI against current
source and concrete roadmap requirements, then fidelity and integration/human
acceptance. Nonlinear browser gradients, broader corpus acceptance, physical
microphone/ASR latency, real preparation/rehearsal and live Fast Decisions/ChatGPT
model acceptance remain open. Current package now contains the latest reviewed
source; do not replace this scope with a release-complete claim.


## Latest continuation - remaining staged native review (2026-10-08)

Adds actual proposed PowerPoint appearance to TextFit, NativeDiagrams,
InsertAuthoredSlide, CreateAppendix and EvidenceFootnote. Dependency reasoning
preserves existing Core writers, staged operations, exact reviewed SHA and Undo.
Each hook binds the full project/document/baseline revision/plan/source SHA identity
only for an open matching draft. Text/diagram/footnote review uses the original
ordinal; authored insertion reviews slideNumber+1; appendix browsing reviews the
proposed divider ordinal plus the detail index. Image or draft changes invalidate
approval. Native rendering blocks approval and Save in controls and handlers.
Native display failure explicitly falls back to experimental browser appearance.
Discard/unmount contains delayed native replies without changing the head.

Insertion, appendix and footnote dialogs now require a loaded image before Save,
with busy/saved guards in handlers. Footnotes additionally require current eligible
claim evidence and valid operations. Appendix counts a viewed slide only once its
image has loaded, preserves full-divider/all-details review, and resets approval
on browsing. Diagram caption now describes a proposed slide instead of implying
browser pixels came from a reviewed native package. Core/database/protocol/provider
and dependency files unchanged. Current renderer scan finds no renderEditPlanSlide
consumer without usePowerPointAppearance; that scan is an inventory check, not broad
fidelity or human acceptance.

Desktop231 tests and desktop lint/format/types/build pass. Core unchanged from the
prior fresh1398-case full check; no repeated Core run claimed. New self-contained
scripts/test-native-workflow-review.mjs passes14 acceptance workflows across seven
real Electron/Core/PowerPoint source routes: text fit, diagram create/update/delete,
authored insertion, appendix move/copy. Every route checks actual proposed ordinal,
image switching and changed-and-returned approval, exact reviewed Save/one exact
Undo,720x520 containment, pending Save/approval guards and held-reply Discard.
Diagram update/delete explicitly select the existing native target and verify
reopened catalog metadata. Appendix reviews the divider and both details at their
actual proposed ordinals. Only picker/unused model/ASR boundaries are fixtures;
native bytes and PowerPoint rendering are real. No model calls.

scripts/test-workspace.mjs adds optional PRESENTER_NATIVE_FOOTNOTE_REVIEW=1 checks
using its real current reviewed claim/evidence fixture. Both native checks pass:
actual proposed ordinal, image-approval reset, pending Save/approval blocking,
held-reply Discard with identical baseline head, exact reviewed package Save and
Undo restoring baseline revision/bytes. Existing assertions retained. Complete
source Workspace sweep52857 exits0 with119 workflows (117 existing plus2 native
footnote checks), no renderer errors. Owned copy changes only desktop/runtime/output
paths. Receipts at .local/remaining-native-review/workspace/result.json and
workspace.log. Focused GUI receipts at gui/*/result.json and gui-summary.json.
Native text-fit, inserted-slide, appendix and evidence-footnote screenshots inspected.
Text-fit wraps the owned fixture into two readable lines. Appendix retains the
fixture's pre-existing clipped text; no automatic layout repair claim.

Initial focused harness failures were option visibility, a Windows text-encoding
revision selector, missing Core fixture import path and failure to select an existing
diagram before testing update. Fixed harness synchronization/encoding/import/target
selection; exact Save/Undo/reopened metadata assertions retained. No production
behavior change or threshold relaxation in response to these harness errors.

422 source/test entries frozen:415 of421 previous entries unchanged, six existing
UI/script files modified and one new GUI script. All422 hashes and all four previous
shape-fill package artifacts match after acceptance. All owned handles terminal.
Branch/base SHA and dirty checkout preserved; no staging/commit/push, unrelated
cleanup or public mutation. Previous package predates these and the latest chart/
table dialog changes. Production goal remains active.

Next: group the chart/table/remaining-dialog source changes into fresh isolated
package integration; inventory substantial remaining Workspace authoring/GUI against
current source, then fidelity and real/human acceptance. Process OPENAI_API_KEY
availability rechecked false; live Fast Decisions remains untested. Separate ChatGPT
plan sign-in still requires human official browser completion then catalog/model
inference. Signing and clean Windows validation remain accepted debt.


## Latest continuation - native table workflow review (2026-10-08)

Adds actual proposed PowerPoint appearance to NativeTables, TableFormatting,
TableBorders, TableFit and TableMerge. Dependency reasoning keeps Core table
writers, staged operation contracts and exact reviewed SHA/Undo unchanged. Each
native hook binds project/document/revision/plan/source SHA/slide only for an open,
matching draft. Draft or displayed-image changes clear approval, including changed-
and-returned values. Pending native rendering clears approval and blocks both Save
control and handler. Discard/unmount invalidates target identity and rejects delayed
replies. Display failure rejects native image with explicit browser fallback. Parent
revision scope/retrieval refresh, database, protocol, providers and dependencies are
unchanged. No native row measurement algorithm or table writer changes.

Saved NativeAppearance caption now says Review proposed changes in an edit preview
rather than implying every draft uses Browser appearance. Its seven exact-caption
selectors in test-native-appearance.mjs are updated to the new copy; assertions and
behavioral coverage retained. Proposed-plan disclosure remains unchanged.

Desktop231 tests plus complete desktop lint/format/types/build pass. Core/source/
test entries are unchanged from prior fresh1398-case full check; no new Core run
claimed. New self-contained test-native-table-review.mjs uses real Electron/Core/
PowerPoint and a3x3 native table with explicit Arial18 text. Eight source runs pass
16 workflows across create/cell edit/row insertion/formatting/borders/compact row
fit/merge/split. Every route verifies native pixels, image and changed-and-returned
approval, exact reviewed Save, reopened authoritative metadata and one exact Undo,
actual720x520 containment, pending Save/approval guards and held real native reply
contained after Discard without mutation. Fitted rows preserve text/column width;
merge/split expected regions and explicit style/border values reopen correctly.
Only picker/unused model/ASR are fixtures; native bytes/rendering are real. No model
calls. Compact-fit and merge screenshots inspected for readable text/layout. Creation
uses existing default placement; no automatic non-overlap/layout acceptance claimed.
Receipts at .local/table-native-review/gui/*/result.json and per-route logs.

Native appearance regression additionally passes11 workflows through real PowerPoint
(9 saved-appearance cases plus staged manual and deterministic Copilot previews):
immutable saved pixels, Browser switching/navigation, revision edit/Undo/Redo,
selection bounds, held reply rejection, explicit native failure/retry and minimum
window. Receipts at .local/native-appearance/table-review-20261008; orchestration
74289 exits0. Desktop checks24298 and initial cell-edit30243 exit0. No assertion or
acceptance threshold relaxation. Full source Workspace sweep82281 exits0:117 workflows and renderer-error assertion
pass at .local/table-native-review/workspace.log/output.421 source/test hashes and
all four prior package hashes match after acceptance. All owned handles terminal.

421 source/test entries frozen:413 of420 prior entries unchanged, seven existing
UI/script files modified and one new table GUI script. All four previous shape-fill
package artifacts preserved; that package predates these table and chart-presentation
dialog changes. Dirty checkout preserved; no staging/commit/push, unrelated cleanup
or public mutation. Production goal remains active.

Next: remaining native review for TextFit/NativeDiagrams/InsertAuthoredSlide/
CreateAppendix/EvidenceFootnote (current renderer source inspection shows they still
use renderEditPlanSlide without usePowerPointAppearance), substantial remaining
Workspace authoring/GUI, grouped package integration, fidelity and real/human
acceptance. Live Fast Decisions
needs process credentials outside chat; separate ChatGPT plan sign-in needs human
official browser completion then catalog/model inference. Signing/clean Windows
accepted debt.


## Latest continuation - native chart color/axis/legend review (2026-10-08)

Closes three direct chart-review gaps: ChartColors, ChartAxes and ChartLegend now
show actual proposed PowerPoint appearance through the existing shared native hook.
Dependency reasoning: existing writers already stage immutable plans with exact
reviewed SHA and Undo. Native target binds full project/document/revision/plan/source
SHA/slide identity only while the dialog is open and its draft matches. Draft or
displayed-image changes clear approval, including changed-and-returned values;
pending native rendering clears approval and blocks both Save button and handler.
Discard/unmount invalidates the hook identity and rejects held replies. Failed
native display rejects that image and retains explicit experimental browser fallback.
Existing writer/plan/database/protocol/provider/dependency contracts unchanged.
Caption identifies the actual proposed appearance; axis guidance points to native
review rather than assuming every preview is experimental. Parent revision scope
and retrieval refresh are unchanged.

Desktop231 tests, complete desktop lint/format/types/build pass. Core/source/test
files are unchanged from the prior fresh1398-case full check; no repeat Core run
claimed. New self-contained test-native-chart-presentation.mjs runs real Electron/
Core/PowerPoint with an owned synthetic fixture. Six sequential source runs pass
12 workflows: colors column/bar/line/pie, axes, legend. Each tests image switching
and changed-and-returned draft approval, actual native pixels, exact reviewed Save,
settings reopen/one exact Undo,720x520 containment, pending Save/approval blocking
and held real native reply discarded without head mutation. No model calls.
Axes/legend screenshots inspected: scale0..40 with title Revenue scale and a right
legend. Native bytes/rendering are real; only picker/unused model/ASR are fixtures.
Initial test read approval before React state settled; captured UI was already
unchecked. It now waits for unchecked state and retains the false assertion.
A second test read default color before catalog arrival; now waits for an actual
nonempty chart option, retaining exact reopened color assertion. No production
behavior patch or timeout/assertion relaxation for either test synchronization fix.
Receipts at .local/chart-native-review/gui/*/result.json and logs. Initial column
logs retained separately; final settled column run77393 and other runs30956 exit0.

Full source Workspace sweep86754 exits0:117 workflows and renderer-error assertion
pass at .local/chart-native-review/workspace.log/output. No new source GUI failure
or acceptance-threshold changes.420 source/test hashes and all four prior package
hashes match after acceptance. All owned handles this turn are terminal.420 source/test entries frozen:416 of419 prior entries kept,
three existing dialog files changed and one new native GUI script. All four prior
shape-fill package artifact hashes preserved. That package predates these dialog
changes. Dirty checkout preserved; no staging/commit/push, unrelated cleanup or
public release. Production goal remains active.

Next: substantial remaining Workspace/table authoring
and native review, fidelity/integration and real/human acceptance. Saved-native
caption still says draft edits use Browser appearance; inspect/update that separate
saved-pixel disclosure alongside remaining dialog work. Live Fast Decisions needs
process credentials outside chat; separate ChatGPT plan OAuth/catalog/inference
needs human official browser completion. Signing/clean Windows accepted debt.


## Latest continuation - packaged shape-fill integration (2026-10-08)

Closes package staleness for the separate shape-gradient/opacity workflow. Dependency
chain was reasoned before work: verify419 source/test hashes, build Core in isolated
local outputs, rebuild desktop, package those exact outputs with pinned Codex, then
run actual frozen-sidecar/native GUI acceptance. Production source/config untouched.
Fresh unsigned unpacked Electron44.1.0/frozen schema19 bundle at:
.local/shape-fill-package/app/win-unpacked/Presenter Copilot.exe.
No installer, signing, clean-machine or public-release claim. Previous packages kept.

Fresh pnpm check20088 exits0:1398 Core tests in307.94s,231 desktop tests, whole-repo
format/lint/types and mypy172. Includes the protocol example fix and both new Copilot
shape-fill dependency cases. PyInstaller44999 and builder93433 exit0. Owned local
builder config selects isolated sidecar/app outputs; pinned Codex0.153.4 version,
hash/license/notice check passes. Artifact receipts record absolute paths/size/hash:
exe db08168bd70b77dfe4adef2a28de9b643e01f50b7d14c2e5ee66f59195f474e5;
asar ff9d00194e0a4880806674929a10710e8b569a1c41170f3f7714b5f3f6970aad;
Core aa66a72e3cc5cb58388a652e50539bea9e639c4e95bd99ae7806386f1ddcb7ca;
Codex444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b.

Nine sequential actual packaged Electron/Core/PowerPoint GUI runs5878 exit0:
26 workflows total:shape fills3;chart fills column/bar/line/pie3 each;markers2;
labels2;chart creation/data/structure3;bulk text4. Exact reviewed hashes save,
settings reopen, Undo restores exact heads, draft/image changes require fresh
approval, pending rendering blocks Save and delayed native replies remain contained
on Discard. Shape/bulk workflows verify actual720x520 horizontal containment.
Packaged shape-gradient and minimum-window screenshots inspected. Picker/input
fixtures are owned; actual frozen Core and PowerPoint pixels are real. Packaged
runs remove dev/test model flags; no model calls or downloads. No full117-workflow
packaged/model-driven sweep claim. Prior source117 passes on retry with the first
chart slide-duplication timeout retained as unproven; no code/assertion workaround.
Receipts at gui/*/result.json, gui-summary.json and per-run logs.

Signed-out packaged Settings probe passes in a disposable profile: Continue with
ChatGPT visible, DPAPI credential store availabletrue/account_count0, stored decision
providerdisabled, native Decisions/ChatGPT plan providers present. Provider metadata
is not server health or entitlement acceptance. No OAuth/catalog/inference call or
account/token values logged. Process OPENAI_API_KEY still unavailable. Settings
receipts/screenshots and settings.log retained. Live services remain open.

Initial/final bundled startup smoke pass with0 sidecars before/after, no orphan or
model download, sanitized PATH excludes Python fallback.419 source/test hashes,
all four new artifacts and all four prior native-authoring artifacts match after
acceptance. Source freeze/artifact receipts/preservation.json retained.343 dirty
paths preserved, branch codex/production-readiness/base657b876739ff7a1cc5709a7e28e92ec2551b337e
unchanged. No staging/commit/push, unrelated cleanup or public mutation. All owned
handles terminal. Production goal remains active.

Next: substantial remaining Workspace authoring/GUI and specialized native review
(e.g. chart colors/axes/legend and table workflows), broader fidelity and real/human
acceptance. Live native Decisions access/latency/calibration needs process credentials
outside chat; separate ChatGPT plan sign-in needs human official browser completion,
then catalog/model inference. Signing/clean Windows validation are accepted debt.


## Latest continuation - reviewed native shape gradients and opacity (2026-10-08)

Adds a separate shape-fill inventory/writer contract and direct Shape fills & opacity
GUI. Dependency reasoning keeps FidelityShapeStyle and the existing solid-color
writer unchanged. New readonly list_shape_fills RPC verifies the current ready PPTX
revision and exact source hash/size. Native top-level shapes/text boxes expose a
whole-shape fingerprint; placeholders, grouped children and picture/pattern/group
fills stay read-only. Solid RGB supports whole opacity0..100; linear gradients use
2..8 strictly increasing whole-percent stops0..100 with per-stop opacity and
angle0..359. Imported unsupported fill representations are disclosed as native_custom,
not approximated. Explicit replacement changes only the selected fill XML.

Writer removes/replaces that fill in native schema order and proves canonical whole
slide equality after restoring the previous fill. All other ZIP parts are retained;
serialized selected XML and post-edit fidelity identities/content are verified.
Existing staged plans, exact reviewed SHA, atomic Save and Undo remain authoritative.
Typed provider schema/prompt/catalog/binding and before/after review include this
operation. Fingerprints and previous fill are bound from each staged revision,
including a text box created earlier in the same plan. No database/dependency change.

Direct GUI supports correctable malformed percentages/angles/stop order, fresh
approval after draft or displayed-image changes, full native plan/source identity,
Save blocked while native rendering is pending and late-reply containment on Discard.
Parent keys revision/slide scope and reindexes after Save. Source real Electron/Core/
PowerPoint acceptance passes three workflows: actual gradient and opacity pixels,
exact Save/reopen, two exact Undo steps, changed-angle approval reset and held real
native reply discarded without head mutation. Final run also proves720x520 horizontal
containment. Gradient/minimum-window screenshots inspected. Receipts/logs at
.local/shape-fills/gui, gui-final.log. Fixtures replace picker/unused model/ASR only;
PowerPoint pixels and staged bytes are real. No live model calls or packaged claim.

Focused initial suite54 passes (shape fills/chart fills/Copilot data); final shape
suite8 passes, including staged previous values and earlier-created target binding.
Full pnpm check passes format/lint/types/mypy172 and231 desktop tests, then reports
1395 Core passes and one shared-ready-event example mismatch in313.04s. The two
advertised method lists in protocol-v1.examples.json now include the new RPC;
protocol+final shape suite15 passes and desktop231 passes afterward. Broad Core
collection predates the two final Copilot tests; those pass in the targeted run.
No entirely green final full pnpm check is claimed. Source Workspace sweep stopped
at an existing chart slide-duplication notice wait (15s); captured UI retains3 slides
and reports Saved slide purposes could not be loaded. Cause unproven. Sequential
retry68507 with renderer diagnostics and unchanged assertions exits0:117 workflows,
including chart slide duplication and renderer-error assertion. Receipts at
workspace-retry.log/output. First run26850 remains terminal1; failure cause unproven,
not erased by the retry. No timeout/assertion relaxation or speculative source fix.
All owned handles this turn are terminal.
419 source/test entries frozen:404 of415 previous entries preserved,11 existing
wiring/example files changed and4 new files. All four native-authoring package hashes are
preserved. That package predates shape fills.343 dirty paths retained; no staging,
commit/push, unrelated cleanup or public release. Production goal remains active.

Next: package integration and substantial remaining GUI/
authoring and fidelity acceptance. Live Fast Decisions and separate ChatGPT plan
OAuth/catalog/inference remain open. Signing/clean Windows accepted debt.


## Latest continuation - current packaged native-authoring integration (2026-10-08)

Previous turn added reviewed multi-selected text formatting. This continuation
closes package staleness for chart labels/markers, native gradients/opacity,
chart creation/data review and bulk text formatting. Dependency chain was checked
before work: freeze415 source/test entries, build Core in an isolated local output,
rebuild desktop, package those outputs with the pinned Codex runtime, then validate
the actual bundle. No production source or packaging configuration was edited.
Preserve the dirty checkout and all previous packages.

Fresh unsigned unpacked Electron44.1.0 app and frozen schema19 sidecar build
successfully under .local/native-authoring-package. Owned electron-builder config
points to its own sidecar/app outputs; no existing artifact is overwritten. No
installer/signing/clean-machine/public release claim. Executable:
.local/native-authoring-package/app/win-unpacked/Presenter Copilot.exe.
New artifact-receipts.json records four absolute artifact paths, sizes and hashes:
exe22e00e7be070049078c49832e48baed0e15e26df5d0197c2bf31a95fb99db68a;
app.asar698e6bc062f3160692ac369fb929a121734a94bd5e5196145d6f1ff9f5eeb896;
Corecdbffcc8013df85b11d77bf1c9d0a5d107f23874c877121b701a42d7911c163b;
Codex444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b.
Codex bundle check verifies pinned0.153.4 version/hash/license/notice, using an owned
copy changing only the selected resource path and retaining all assertions.

Fresh pnpm check2058 exits0:1390 Core tests in293.50s,231 desktop tests, whole-repo
format/lint/types and mypy171 source files. Source frozen during build/acceptance;
no stale validation window for this build. Core tests are source acceptance, while
actual frozen-sidecar behavior is verified separately below.

Eight sequential real packaged Electron/Core/PowerPoint GUI runs62067 exit0 with
23 workflows total: solid/gradient opacity on column/bar/line/pie (three each),
line markers (two), native chart labels (two), chart creation/data/category edits
(three) and bulk text formatting (four). Exact reviewed hashes save, settings
reopen correctly, Undo restores exact heads, draft/image changes require fresh
approval and held actual native replies are contained after Discard. Bulk tests
preserve differing color/bold/italic/text for size-only edits, save all five
properties together, block unsupported mixed selections and verify actual minimum
window containment. Only picker/owned input fixture setup is substituted; packaged
app uses its real bundled sidecar and native PowerPoint pixels, without dev/test
provider flags or model calls. Line-gradient and minimum-window images inspected.
Receipts/logs/images are at .local/native-authoring-package/gui and gui-summary.json.
No packaged full117-workflow/model-driven sweep is claimed; the latest source GUI
sweep117 passes at .local/bulk-text-format/workspace with its documented label delta.

A new owned packaged settings probe passes in a disposable profile: native OpenAI
Decisions and separate ChatGPT plan usage are present, Continue with ChatGPT is
available, DPAPI store availabletrue, signed_out/account_count0 and stored decision
providerdisabled. Selecting options for inspection did not enable a provider.
No OAuth/inference calls, account/token values or model downloads. settings.json,
settings-decisions.png/settings-chatgpt.png. This is UI/transport availability;
real browser OAuth/catalog/model inference and native Decisions access/latency/
calibration remain open. Previous real OAuth attempt was cancelled after its human
browser wait; current process still requires credential provisioning outside chat.

Both initial and final bundled startup smoke pass with0 sidecars before/after,
no orphan/model download and sanitized PATH proving system Python cannot satisfy
startup. Final smoke-final.json exits0.415 source/test hashes match after all
acceptance; all four new artifact hashes and all four previous package hashes
match. Source freeze, artifact receipts and preservation.json retained.339 dirty
paths, branch codex/production-readiness, base657b876739ff7a1cc5709a7e28e92ec2551b337e
unchanged. No staging/commit/push, unrelated cleanup, public mutation or release.
All owned handles this turn are terminal. Production goal remains active.

Next: substantial remaining Workspace authoring/GUI and specialized native review,
including a separate shape-fill contract for gradients/opacity; broader fidelity
and real/human acceptance. Fast Decisions live access needs process credentials
outside chat; separate ChatGPT plan sign-in needs human official browser completion,
then catalog selection and actual inference. Signing/clean Windows are accepted debt.


## Latest continuation - reviewed multi-object text formatting (2026-10-08)

Previous turn closed native chart creation/data review. This turn examined native
shape gradients and confirmed they require a separate fill inventory/writer contract;
no shape-fill metadata or writer was changed. A substantial direct authoring gap,
multi-selected text formatting, is implemented through the existing atomic plan
service rather than altering single-object formatting behavior.

Dependency reasoning: canvas selection supplies2-20 stable selected object IDs and
names. BulkTextFormat reads the current verified text-target inventory and binds
exact text/style fingerprints for every selected object. Only explicitly enabled
bold/italic/size/color/alignment properties enter the plan. Each target uses the
existing format_text_shape writer, with up to20 operations staged and saved as one
revision. Unsupported/missing targets or selected property restrictions reject the
whole selection; no object is silently skipped. Existing transaction validation,
exact reviewed SHA, Undo and retrieval re-indexing remain authoritative. No Core,
protocol, provider, schema/database or dependency changes. Other styles, text,
geometry and objects are retained by existing writer invariants.

New Format selected text action beside canvas object actions opens a named-target
review dialog. Property opt-ins avoid overwriting differing styles accidentally.
Invalid size remains editable while Preview/Save are blocked. Proposed PowerPoint
appearance uses full plan/scope/slide identity. Draft/image changes reset approval,
including changed-and-returned values; native rendering blocks Save. Discard and
unmount retain staged-plan/renderer ownership and reject delayed native replies.
Parent keys the dialog by project/document/revision/slide and refreshes retrieval
and selection inventory after one saved revision.

Final desktop231/typecheck/lint/format/build pass. Initial type annotations omitted
prepare-plan changed/baseline fields; corrected response intersection types before
final acceptance. Core/source/test entries are unchanged from the prior1390-case
full run; no fresh full Core run is claimed. New owned test-bulk-text-format.mjs uses
real Electron/Core/PowerPoint, two differently formatted text boxes and an empty
rectangle. Actual staged bytes/native pixels are not mocked. Four workflows pass:
size-only editing preserves differing colors/bold/italic and text, correctable size
bounds and fresh approval, exact Save/one Undo; all five properties saved together
on both objects with exact native bytes/one Undo; unsupported mixed selection is
blocked as a whole; held real native reply is contained after Discard with unchanged
head and blocked Save. Minimum720x520 window passes horizontal containment and
pending-render discard. No model calls. Native screenshot visually inspected;
property checkboxes were aligned beside labels using the existing review-label class.
Initial scripts omitted enabling canvas selection and checked the unselected empty
rectangle's size; corrected fixture setup/assertion scope, keeping selected-object
preservation checks. Final GUI74075 exits0. Receipts at
.local/bulk-text-format/gui/result.json and gui-minimum.log.

415 source/test entries frozen;412 of413 prior entries preserved, one existing parent
Workspace file modified and two new component/script files.339 dirty paths retained.
Full Workspace sweep39681 exits0:117 workflows and its renderer-error assertion
passes. This run predates the one-class checkbox alignment. Final rebuilt GUI63400
passes all four workflows and minimum-window containment after that adjustment;
final types/lint/build pass. A final indentation-only Prettier repair passes whole
desktop format check and does not change rendered behavior. Both original and
final415-entry source freezes are retained. All four prior artifact hashes match.
Every owned handle this turn is terminal. Prior packages predate this workflow. No staging/commit/push,
unrelated cleanup or public release. Goal remains active.

Next: substantial remaining Workspace authoring/GUI and specialized native review,
current package integration,
broad fidelity and real/human acceptance. Shape gradients/opacity remain separate
future work. Live Decisions needs process credentials outside chat; separate
ChatGPT plan OAuth needs human browser completion. Signing/clean Windows accepted debt.


## Latest continuation - native chart creation/data review (2026-10-08)

Previous turn implemented chart gradients/opacity and passed1390 Core/231 desktop,
12 native GUI workflows and117 Workspace workflows. Current source inspection
confirmed NativeCharts creation/data/structural review still only displayed browser
pixels. This continuation adds explicit actual proposed PowerPoint appearance to
that dialog. Preserve the dirty checkout.

Dependency reasoning: existing chart creation, value and structural edits already
stage immutable plans using exact reviewed hashes and existing transaction/Undo
boundaries. The dialog now binds the shared native hook to open/matching draft,
project/document/revision/plan/source SHA and slide. Draft and displayed-image
changes clear approval, including change-and-return. Pending native rendering
clears approval and blocks both Save control and handler. Discard closes the hook
identity and late real replies cannot populate another/saved view. Failed native
image display rejects that image and returns to experimental browser appearance.
No Core writer, workbook, geometry, protocol, provider, schema or dependency changes.
Copy identifies the actual selected appearance rather than calling browser pixels
native. Microsoft PowerPoint on Windows is required for explicit native rendering.

231 desktop tests, full desktop lint/types/format/build pass. The final test-script
wait adjustment has additional Prettier/ESLint acceptance. Core source/test entries
are unchanged from the1390-case previous broad run; no new full Core run is claimed.
New self-contained test-native-charts.mjs uses real Electron/Core/PowerPoint and an
owned synthetic column fixture; picker/unused provider and ASR are fixtures. Actual
pixels and exact package hashes are not mocked. Three GUI workflows pass: existing
value and category insertion edits, fresh native approval and exact saved/reopened
settings, two exact Undo steps; native bar-chart creation, switching appearance
clears approval, exact Save/Undo; held real native reply blocks Save and Discard
contains stale pixels without head mutation. Initial immediate post-click approval
assertion raced the existing asynchronous image effect. The test now waits for
unchecked approval before asserting; production was unchanged and final25629 exits0.
Images were visually inspected. Data/structural values and controls are readable;
creation shows the new chart overlapping the original at default supplied geometry,
which native review makes visible. This does not prove automatic placement/layout.
Receipts at .local/native-chart-review/gui/result.json and gui-final.log.

413 source/test entries frozen;411 of412 prior entries unchanged, only NativeCharts
modified and one new owned GUI script added. All prior package hashes unchanged;
that bundle predates these dialogs.337 dirty paths retained. No staging/commit/push,
unrelated cleanup or public release. Full Workspace sweep76608 exits0:117 workflows
and the renderer-error assertion passes before result publication. Its owned local
copy changes only import/launch/output paths, preserving repository assertions.
Receipts are at .local/native-chart-review/workspace/result.json and workspace.log.
Final413-entry source freeze still matches. All owned handles this turn are terminal.
No live-model, human/physical, package or broader corpus acceptance is implied.
Production goal remains active.

Next: substantial remaining Workspace authoring/GUI gaps and specialized native
review, current package integration, broader fidelity and real/human acceptance.
Live Decisions needs process credentials outside chat; separate ChatGPT plan OAuth
needs human browser completion. Signing/clean Windows remain accepted debt.


## Latest continuation - native chart gradients and opacity (2026-10-08)

The substantial chart-fill gap is implemented in direct Workspace editing and
Copilot typed set_chart_fill plans. Dependency reasoning preserved the existing
set_chart_color contract (opaque RGB plus outline/stroke); the new operation
changes only selected area fill for columns/bars/pie, or stroke fill for lines.
Existing outlines, widths/dashes, markers, point overrides, labels, data, workbook
and shared chart parts retain their existing values. Canonical chart preservation
proof checks everything outside the selected fill. Shared appearance transactions
clone the selected chart, bind fingerprints, stage exact bytes, apply/re-index as
one reversible revision and retain exact Undo. No schema/database migration,
provider endpoint or dependency was added.

Solid RGB supports whole opacity percentages0-100. Linear gradients support2-8
strictly increasing stops from0 to100, explicit RGB/per-stop opacity and integer
angle0-359. Supported targets are ordinary native column/bar series or points,
line series and pie points. Imported fills outside the representable subset are
reported as native_custom; absent explicit fills as native_default. No imported
complex fill is approximated. Copilot binding reports exact staged previous fill
and fingerprint, including after an earlier operation.

Chart fills & opacity dialog supports stop insertion/removal, correctable invalid
values, exact settings on reopen and explicit proposed PowerPoint appearance.
Draft/image changes invalidate approval; pending native rendering blocks Save.
Exact reviewed SHA applies. Discard rejects delayed native replies. Browser
appearance remains experimental; native appearance is explicit and uses actual
PowerPoint in an isolated owned worker.

28 focused Core cases pass: solid/gradient round trips across six target kinds,
shared-chart/workbook/package isolation, no-op/exact Undo, invalid nested values,
incompatible targets, retained outlines/line styles and staged Copilot previous
values. Full pnpm check71628 exits0:1390 Core tests in305.02s,231 desktop tests,
format/lint/types and mypy171 files. The later fixture-kind test-script addition
has separate passing Prettier/ESLint checks; production source did not change.

Real Electron/Core/PowerPoint GUI runs pass three workflows each for column,
bar, line and pie (12 total): invalid stop/opacity correction, fresh approval after
angle changes, exact gradient/solid Save, settings reopen, two exact Undo steps,
and held native reply containment after Discard. Screenshots visually inspected:
gradients/transparency render on bars/columns, line stroke and selected pie slice;
other pie slices and chart data remain intact. Receipts/logs/images are under
.local/native-chart-fills/{gui,line,bar,pie}; no model calls were made.

412 source/test entries are frozen;400 of408 prior entries are preserved,8 existing
wiring/review files changed and4 new module/test/component/script files added.
All four prior package hashes remain unchanged; that bundle predates this feature.
336 dirty paths are retained. No staging/commit/push, unrelated cleanup or release.
Full Workspace GUI99644 exits0:117 workflows, with the renderer-error assertion
passing before result publication. An initial owned script copy used default
Windows decoding and corrupted its ellipsis selector; that run8286 exited1 before
importing. Recreated the copy with explicit UTF-8 and reran after terminal
confirmation. Production source and repository assertions were unchanged.
Receipts are under .local/native-chart-fills/workspace and workspace-final.log.
The412-entry freeze still matches after all acceptance. Every owned process this
turn is terminal. This is deterministic-provider local GUI acceptance, not
live/human proof.

Next: native review for chart creation/data edits, substantial remaining authoring/GUI
workflows and specialized native review,
current package integration, broad fidelity and real/human acceptance. Live native
Decisions still needs process credentials outside chat; separate ChatGPT plan OAuth
needs human browser completion. Signing/clean Windows are accepted debt. The
production-readiness goal remains active.


## Latest continuation - reviewed native line markers (2026-10-08)

Previous turn progressed native chart-label review. Current roadmap/editor/schema
inspection verified native line marker shape/size controls were missing. This
continuation implements direct and typed Copilot set_chart_marker plans rather
than adding only another appearance toggle. Preserve the dirty checkout.

Dependency reasoning: chart inventory supplies editable marker state, shape options,
series names, explicit/native-default symbol/size and point-override count. The
writer changes only the selected ordinary line-series c:marker symbol/size, with
canonical whole-chart proof that all other XML is unchanged. Existing marker spPr,
point overrides, line color/width/dash, labels/data/workbook/shared chart parts are
retained. Shared appearance transactions clone the selected chart, use fingerprint
preconditions, stage exact bytes and apply/re-index as one reversible revision.
Malformed targets and non-line charts stay read-only. Bounds are integer series0-5,
size2-72 points and ten symbols (none/circle/square/diamond/triangle/x/plus/star/dot/dash).
None hides series markers while retaining point overrides; picture/auto source
markers are reported but are not offered as new symbols. No protocol/schema/db
migration or new provider/endpoint/dependency required.

Operation added to transaction/editor dispatch, provider JSON schema and prompt.
Copilot binding supplies current fingerprint and exact staged previous marker
settings, including after earlier operations. Review names the operation and
shows previous/proposed series/symbol/size. Live planning quality remains open.
New Chart markers direct dialog offers series/shape/size, honest native defaults
and point-override disclosure. Explicit staged PowerPoint appearance reuses the
shared full-identity/lifetime hook. Draft/image changes clear approval; pending
render and invalid draft block Preview/Save as appropriate, exact SHA applies,
Discard/Undo retain existing ownership boundaries.

Focused21 new tests (17 original plus4 parser boundary cases) cover every symbol,
shared chart/workbook/package isolation, no-op, exact Undo, invalid/bool sizes,
non-line/picture targets, retained marker properties/point overrides, staged
Copilot previous values, and malformed/native 5000-digit size read-only handling.
Initial detached XML-copy assertion compared different namespace contexts; fixed
the test to compare attached-node bytes before/after. Canonical writer preservation
proof unchanged. Final focused marker/color/label/Copilot data suite104 passes in29.97s.

Actual local Electron/Core/PowerPoint GUI initially exposed a correction-path bug:
invalid size disabled its fieldset. Fixed inputs to remain editable while Preview
and Save reject invalid state. Final marker GUI4897 exits0, two workflows: invalid
size can be corrected; appearance/draft changes require fresh review; native square
markers render on line and legend; Save matches reviewed SHA; reopened settings
are square/12pt; Undo restores exact baseline. Held real native reply followed by
Discard cannot leak into saved view or change head. Screenshot visually inspected,
readable controls/chart/title. .local/native-chart-markers/gui/result.json and
native-markers.png, gui-final.log. Script creates its own owned synthetic native
line fixture; picker/unused provider/ASR flags are deterministic. No model call.

Broad pnpm check46774 exits0:1358 Core cases in287.03s,231 desktop tests, lint,
format/types and mypy. This run predates the bounded malformed-size parser repair
and its4 additional tests; final104 focused cases and full Core lint/mypy170 cover
that delta. Final desktop231/typecheck/lint/format/build separately pass after
fieldset repair. Final whole-repo format check passes after all edits. No claim of
a fresh1362-case full Core run.

Full existing Workspace GUI54595 exits0,117 workflows with its renderer-error
assertion passing. Used an owned .local copy changing only launch/import paths and
output location; repository script/assertions are unchanged. Evidence at
.local/native-chart-markers/workspace/result.json and workspace.log. Prior
.local/ui-validation receipts preserved. This broad GUI is deterministic-provider
local acceptance; it does not establish live model or physical/human acceptance.

408-entry source freeze stays unchanged during final acceptance;396 of404 prior
source/test entries preserved,8 bounded existing wiring/review files modified,
4 new marker module/test/component/script files.332 dirty paths preserved. All
prior packaged artifact hashes unchanged; bundle predates marker/label UI changes.
No staging/commit/push, unrelated cleanup, model download or public release.
Every owned handle this turn is terminal. Production goal remains active.

Next: substantial remaining authoring gaps (gradient/opacity), specialized native
review coverage, current package integration, broad fidelity and real/human
acceptance. Live native Decisions needs process credential provisioning outside
chat; separate ChatGPT plan OAuth needs human browser completion. Signing and
clean Windows remain accepted debt.


## Latest continuation - native chart-label review (2026-10-08)

Previous turn progressed real packaged plan OAuth to a bounded browser wait,
then cancelled without a callback. No live account was authenticated. Current
Workspace inspection found chart labels still limited to experimental Browser
appearance. This is a material review gap when names/percentages/formats differ
from PowerPoint, so this continuation adds explicit proposed PowerPoint appearance
in ChartLabels using the existing shared native rendering boundary.

Dependency reasoning: the native target is available only for open review with
a plan matching the current draft; project/document/baseline revision/plan/SHA/
slide identity are preserved. Changing displayed image clears loaded/approval;
pending rendering clears approval and blocks Save in both handler and button.
Draft changes withdraw the native target and require new preview/review. Image
failure rejects native display and retains Browser fallback. Existing prepared-
plan writer, exact reviewed hash, apply/re-index and undo paths are unchanged.
No Core/protocol/database/provider dependency changed. The dialog accurately
labels native proposed pixels and experimental Browser limitations.

New self-contained script apps/desktop/scripts/test-native-chart-labels.mjs
creates an owned synthetic one-slide native column chart via installed Python
PPTX dependencies. Actual local Electron/Core and Microsoft PowerPoint verify
Browser-to-native and native-to-Browser approval reset, changed-format invalidation,
fresh native review, exact source SHA Save, saved 0.00 settings and exact baseline
Undo. A second workflow holds a real native reply after rendering: Save is blocked,
Discard closes review, the late reply cannot leak and saved head stays exact.
Picker/unused provider/ASR configuration are deterministic; no model/account call.
Final script includes its own fixture generation and no unused copied helper.

GUI71988 and final62889 both exit0, two workflows, no renderer errors. Native
screenshot inspected: requested outside-end 10.00/12.25/15.00 labels and chart/title
are clearly visible; native review controls/ack/save/discard are readable. Receipts:
.local/native-chart-labels/gui/result.json, native-labels.png, gui-final.log.
All231 desktop tests pass; typecheck/build, final lint and format check pass.
Initial lint found an unused copied test helper; removed and final lint passes.
No Core implementation changed; no fresh full-Core or full117-workflow claim.

Freeze .local/native-chart-labels/source-freeze.json has404 source/test entries.
Of401 prior package-frozen entries, only ChartLabels.tsx changed;400 remain exact.
Two prior Decisions diagnostic files preserved and one new GUI script added.
Prior packaged artifacts remain unchanged and predate this source UI addition;
new native-label packaged acceptance is still open. No staging/commit/push,
model download, release or unrelated cleanup. Goal stays active.

Next: other specialized proposal dialogs, substantial remaining authoring gaps,
broad fidelity/integration; live Decisions credentials and human ChatGPT browser
completion, microphone/rehearsal acceptance remain open. Signing and clean Windows
validation remain accepted debt.


## Latest continuation - packaged ChatGPT plan OAuth attempt (2026-10-08)

Previous turn was progress: dedicated native Decisions diagnostic. Current trace
confirmed the ChatGPT plan route is separate from Codex reasoning. No production
edit was needed to attempt real authorization. An owned Playwright script at
.local/live-chatgpt-plan.mjs launched the current unsigned unpacked executable,
using a new disposable browser profile and protected Core vault. It selected
ChatGPT plan in Fast Decisions and clicked the actual Continue with ChatGPT
button. No fixture substitution or model/provider override was used.

Initial real status: signed_out, credential_store_available true, zero accounts.
Official browser sign-in started; handle45733 remained live while polled. A user
completion question was presented. No browser callback arrived within the
three-minute bounded acceptance window. Final observed status remained signing_in,
zero accounts, no error code. The test clicked Cancel sign-in and closed the
owned app; handle45733 then exited0. This is a terminal diagnostic with
awaiting_user_timeout, not successful authentication. No OAuth code/token/email
was printed, no account authenticated, and no inference or model discovery was
attempted. Existing application accounts were untouched. Only a disposable host
registration/vault and browser launch occurred; no production account mutation.

Focused test_chatgpt_plan.py: all seven cases pass in13.48s, covering fixture
account separation/refresh/sign-out, plan permission, callback state/cancellation,
protected Windows store and streamed choices/quota mapping. These are synthetic
transport tests, not live account acceptance. Evidence in .local/live-chatgpt-plan/
result.json and preservation.json. All401 prior source/test entries and four
package artifact hashes remain unchanged;327 dirty paths retained. No staging,
commit/push, rebuild, model download or public release. Goal stays active.

Next: resume the real GUI OAuth attempt when the user can finish browser sign-in;
then validate discovered model selection and synthetic completed inference. Live
native Decisions still needs process OPENAI_API_KEY provisioned outside chat.
Continue substantial authoring/fidelity work while these human/account gates are
unavailable. Signing and clean Windows remain accepted debt.


## Latest continuation - native Decisions diagnostic (2026-10-08)

Previous goal turn was a status-only report (no progress). Current inspection
confirmed the live Codex containment command does not cover the separate
ChatGPTPlanAuthService OAuth path. Existing decision diagnostics reject remote
providers. The process has no OPENAI_API_KEY; no credential values were read or
emitted, and no inference/OAuth call was made in this turn.

Added presenter_core.tools.openai_decisions_acceptance: explicit --live,
environment credential only, production fixed-endpoint/model native adapter,
10 purpose and 20 claim/excerpt synthetic cases. One attempt per case, stop on
first failure, no project/vault/OAuth/endpoint override/retry/fallback. Reports
finite choices, separate confidence/distribution, triage review/abstention and
median/p95 latency. Completed means transport/schema diagnostic only; authored
labels and provisional confidence thresholds do not establish calibration or
production model quality. No application/provider behavior changed.

Focused checks: 30 tests pass (new diagnostic and existing native adapter),
ruff lint/format and focused mypy pass. Tests use synthetic transport fixtures;
these are not live access evidence. Actual --live command returns exit2 and
not_executed / OPENAI_API_KEY unavailable, receipt .local/live-decisions/availability.json.
All 401 prior frozen source/test entries remain byte-identical; two new files
bring dirty paths to327. Existing package remains unchanged and lacks this
source-only diagnostic. No staging/commit/push, model downloads or public action.

To run after provisioning OPENAI_API_KEY outside chat:
`uv run --directory core --project . --locked python -m presenter_core.tools.openai_decisions_acceptance --live`
The command prints metadata JSON; redirect to a fresh .local receipt if desired.
Next: actual ChatGPT plan GUI/OAuth acceptance (distinct from Codex reasoning),
then live Decisions when process credentials permit, continuing broader fidelity
and human integration gates. Signing/clean Windows remain accepted debt.


Current package status (2026-10-08): fresh schema19 frozen sidecar and unsigned
unpacked app build successfully. Current pnpm check passes 1338 Core/231 desktop
tests and format/lint/types/mypy. Packaged checkpoint GUI (three workflows), native
layout/manual GUI (three workflows) and direct frozen-Core group/ungroup integration
pass, including exact-byte saves, both undo heads and identical grouped/ungrouped
PowerPoint pixels. Final bundled smoke has 0 sidecars before/after and no orphan/model
download. All 401 source/test entries and four artifact hashes stay unchanged after
acceptance; receipts are in .local/revision-checkpoints/package. No packaged Copilot
model, live Decisions/ChatGPT, physical/human, installer/clean-machine or signing
acceptance is implied. Production goal remains active; see handoff for exact scope.


Current checkpoint status (2026-10-08): History supports project-local revision
names and notes, rename/remove/reload with record-token conflicts, restart retention,
and restoring exact immutable revisions through existing re-indexing. Label edits
leave PPTX bytes/current head unchanged; removal keeps the revision. Schema19 uses
cascade-bound metadata and token-bearing tombstones. Twelve focused tests pass;
broad check passes 1337 collected Core/231 desktop tests (additional cap test passes
separately), and 117 Workspace workflows pass. Three dedicated Electron workflows
prove persistence/conflict/restore and actual minimum-window maximum-label containment.
Final scoped wrapping repair has rebuilt GUI/type/lint/format acceptance after the
broad GUI run. Fresh schema19 package acceptance remains pending. Live Decisions/
ChatGPT, physical/human and broader fidelity/integration gates remain open.


Current Copilot authoring status (2026-10-08): reviewed native grouping/ungrouping
supports distinct supported objects, nested earlier-step creation references and
Core-owned staged geometry preconditions. Visible review lists group targets. Eight
new Core tests pass; broad pnpm check passes 1326 Core/231 desktop tests and Workspace
passes 117 workflows. Final review-data additions have focused tests, lint/types/mypy
and native GUI evidence separately; broad runs predate those display additions.
Six real-PowerPoint workflows pass, including exact group/ungroup Save hashes and
both exact Undo steps. Final rebuilt GUI verification passes all six workflows; native slides and member
review were visually inspected.
Existing packaged app predates these changes. Live Decisions/ChatGPT, physical/human,
broader authoring/fidelity/integration remain open. See handoff for exact receipts.


Current layout-review status (2026-10-08): final native-layout application and
insertion review now offer explicit PowerPoint appearance for exact staged bytes.
Changing the draft or displayed image invalidates approval; Save waits for image
readiness and native rendering. Five real-PowerPoint GUI workflows pass, including
both exact-byte layout Save/Undo and existing manual/refinement/discard boundaries.
231 desktop tests, lint/types/format/build pass. Layout comparison thumbnails remain
Browser appearance. Previous packaged app predates this change; current full Workspace
sweep passes 117 workflows with no renderer errors. Live Decisions/ChatGPT, physical/human and broader fidelity/
integration acceptance remain open. See handoff for receipts and source freeze.


Current authoring work adds explicitly saved project-local outline sessions. Schema
18 stores original proposal/request provenance separately from the saved conversation;
exact branch baselines and record tokens protect restoration and concurrent writes.
Save/Resume/Reload/Remove do not call a provider, restore account settings or create
slides. Five dedicated development GUI checks pass, including a held Save locking dictation,
real restart with three branches, notes/unsent refinement, conflict recovery and
minimum-window containment. Eleven new
Core tests cover persistence/provenance/ownership and v17 row-preserving migration.
Full pnpm check passes 1318 Core and 231 desktop tests; full Workspace GUI passes
117 workflows. Fresh schema-18 frozen sidecar and unsigned unpacked app builds,
packaged smoke and Resume/Remove acceptance pass. Packaged session data is developer-
seeded; packaged launches have no developer provider flags and make no model/deck
calls. Artifact receipts cover unchanged 396-source freeze. Live model/ChatGPT,
physical/human and broader fidelity/integration gates remain open.

Previous native-preview phase:


Latest source also supports native PowerPoint appearance in manual and Copilot
proposed-edit review, before saving. Main copies the existing verified plan reader
into a private snapshot and revalidates the plan after rendering. Plan identity and
image readiness extend saved-frame ownership checks; exact-byte commit checks remain.
Current desktop validation passes 231 tests, types/lint/format, 117 Workspace GUI
workflows and 11 real-PowerPoint native GUI workflows. A separate development run
proves exact native-reviewed manual/refined Copilot commit hashes, undo restoration,
and rejection of delayed replies after refinement/discard. Copilot output is
deterministic test data; no live model acceptance is implied.

Fresh unsigned unpacked package passes bundled-sidecar smoke, native-reviewed manual
Save/Undo, and ten native saved/proposed GUI workflows through the frozen sidecar.
All 393 source entries stay unchanged during/after packaging; unchanged Core/spec
inputs allow reuse of the exact previous frozen sidecar. No live account/model,
installer, clean-machine, signing or public release was exercised. Core unchanged;
last full Core run remains 1307 passing tests. Specialized proposal dialogs outside
manual/Copilot review still use browser appearance; broader authoring/fidelity and
integration, live Decisions/ChatGPT, physical/human gates remain open.

Workspace now implements explicit saved-revision PowerPoint appearance alongside
Browser appearance. Main owns the immutable copy and verifies revision/hash/slide,
PNG dimensions/bytes/hash; a standalone worker preflights the shared source guard,
closes only its private presentation and leaves Office settings and other documents
alone. Renderer frames and URLs are identity-bound and late replies are discarded.
Installed Office preservation passes with an owned unsaved sentinel and already-open
original. The native worker accepts observed custom-page rounding within a strict
1/16pt absolute tolerance, now shared with PDF export after a real custom-size PDF
failure confirmed the same defect. Both isolated native workers preserve the owned
unsaved sentinel and already-open original; source hashes/counts stay exact.
This adds native Windows/PowerPoint capability; browser fidelity and full integration
acceptance remain open. No renderer gradient approximation or locked dependency patch
was shipped. Signing and clean Windows validation remain accepted debt.

Previous saved-preview package validation: full pnpm check passes with 1307 Core tests, 220 desktop tests,
format/lint/types and mypy. The corrected grid contains the entire native slide at
actual 707x460 CSS viewport, with image-relative selection bounds preserved. Nine
native GUI workflows pass in development and the freshly built unsigned unpacked
application. Two subsequent full Workspace sweeps pass 117 workflows; an earlier
late undo failure remains recorded as an intermittent finding, with no speculative
undo patch or test relaxation. No live handles remain.

Current-source PyInstaller sidecar and unpacked Electron app build successfully in
an isolated local output folder. Frozen native preview/PDF workers preserve the
owned unsaved Office sentinel and already-open original. Packaged smoke verifies
the bundled sidecar with no orphan; packaged native GUI passes nine workflows and
full-slide containment. Executable/app.asar/sidecar/Codex hashes and the unchanged
389-entry build source freeze are recorded. Signing is disabled and NotSigned is
confirmed. This is one-host unpacked-package evidence; no installer, clean-machine,
signed-release or public-release acceptance is claimed. Broader fidelity, live
Decisions/ChatGPT, physical ASR/HUD and human preparation/rehearsal remain open.
See the latest [handoff](SESSION_HANDOFF.md) for receipts and exact scope.


Office corpus validation now uses private byte-checked copies and leaves shared
PowerPoint settings/presentations alone. Installed Office preservation passes
with an unsaved sentinel and already-open source; the discovered pywin32 nested
initialization bug is fixed through an independently balanced native COM
reference. Forty focused checks and 211 restored desktop tests pass. A fresh
22-slide native/browser diagnostic reproduces the prior material fidelity gaps;
no renderer fix or broad fidelity acceptance is claimed. Final full Core validation passes
1289 tests. The full 33-record corpus refresh compares 28 decks / 563 slides,
skips two external-link decks and blocks three embedded-OLE decks before native
opening (CLI exit 1). All compared slides retain stable pixel differences; no
COM release fails. Broad fidelity acceptance remains open. See the latest
[handoff](SESSION_HANDOFF.md) for ownership, scopes and remaining gates.


ChatGPT sign-in Settings now preserves unsaved provider/model choices during
status polling, revalidates models on account/catalog changes and discards stale
replies. Seven dedicated GUI workflows and 211 desktop tests pass; the auth
workflow uses synthetic replies, so live SIWC acceptance remains open. See the
[latest handoff](SESSION_HANDOFF.md) for dependencies, source preservation and
validation scope.

Native OpenAI Decisions beta is now implemented as an opt-in GPT-6 Luna provider.
The first-party contract supersedes the October 2 pending-adapter note.
Existing API-key/privacy/review boundaries are reused. Live access, quality,
calibration and latency remain unverified. See the latest
[handoff](SESSION_HANDOFF.md) for validation receipts and remaining gates.

## Latest continuation - restorable outline conversation (2026-10-07)

The outline planner retains ten temporary successful drafts with their submitted
requests, branch parents, original provider/evidence provenance and independent
manual edits. Selecting an earlier draft restores its briefing and edited content;
refining it appends a branch. A position-based comparison uses the exact draft sent
with each request and includes current manual changes. Failures preserve edits;
the cap preserves restoration/final review. Capture/provider work locks history.
Closing or switching modes clears the temporary conversation. Explicit outline
review and native creation keep the selected originating provider run ID.
Provider/Core/IPC/schema/packaging contracts and privacy budgets are unchanged.

Validation: 205 desktop tests (nine new conversation cases), seven Core planning
tests, types/lint/format/build pass. Final rebuilt full GUI sweep passes 117
workflows with no renderer errors; fresh 720x520 acceptance passes three workflows
for wrapping/comparison/restoration, ten-turn bounds and close/reopen. Both small
screenshots were inspected; source inventory confirms zero created decks before
explicit creation. Full GUI additionally verifies failed-request retention,
dictation locking, independent branches and reviewed native materialization.
ASR/providers are deterministic local fixtures. Initial type failures were fixture
indexes; final checks pass. Receipts: `.local/outline-conversation/`.

A 376-entry source freeze confirms 370 preceding files unchanged, three intended
existing changes and three additions. Core/provider/authentication/packaging bytes
remain unchanged; the preceding 1249-test full Core sweep was not rerun. Dirty work
is preserved. No staging, commit, push, account/model call, download/install or
release occurred. Durable history is a future enhancement. Goal remains active:
richer drafting, voice ambiguity,
broad fidelity, real preparation/rehearsal/hardware/ASR/live model acceptance,
Fast Decisions calibration/latency, live Sign in with ChatGPT and exact-source
packaging remain. Signing and clean Windows validation remain accepted debt.
See [handoff](SESSION_HANDOFF.md) and [planning contract](PRESENTATION_WORKSPACE/AI_EDITING.md).

## Latest continuation - focused push-to-edit (2026-10-07)

Focused Ctrl+Shift+Space now supports selected-text rewriting, Copilot slide/deck
requests and outline briefing/refinement. Release reviews local transcription;
Escape or window focus loss cancels an unfinished gesture. Startup queues release
and cancellation; capture-specific handles and context generations protect newer
sessions from late responses. Modifier-first release consumes trailing Space
repeats. Capture/review feedback moves into view. Explicit transcript use,
provider proposal and native save remain separate; no global shortcut or new
Core/provider/authentication authority is added.

Final validation: 196 desktop tests (nine new asynchronous gesture cases), ten
Core voice tests, TypeScript, lint, formatting and build pass. Final rebuilt
Electron/local Core sweep passes 116 workflows with no renderer errors, including
selected-text release/Escape/repeat, outline release, Copilot scope locking,
native window-blur cancellation and modifier-first release. At 720x520 outer /
707x460 content, listening status and focused transcript remain in view without
horizontal overflow; both screenshots were inspected. The native focus test
disables Playwright's default Chromium focus emulation, focuses an owned
disposable window and verifies native and renderer focus state. ASR/providers are
deterministic local fixtures. Physical microphone, live model/account, broad
fidelity and packaging acceptance are not proved by this sweep. Optional native
PDF checks were not rerun; their separate preceding receipt remains below.

Evidence: `.local/push-to-edit/gui-final.log`, `gui-result.json`, final desktop/
types/lint/format/build logs, `core-voice.log`, `small-listening.png`,
`small-review.png`, `selected-text-review.png`. The earlier 115-check full sweep
and initial locator/focus-harness failures remain separately recorded. A 373-entry
source freeze confirms 368 preceding files unchanged, three intended existing
changes and two additions. Core/provider/authentication/packaging bytes remain
unchanged; the preceding 1249-test full Core sweep was not rerun for renderer-only
changes. See [handoff](SESSION_HANDOFF.md) and the
[voice contract](PRESENTATION_WORKSPACE/AI_EDITING.md#voice-path).

Goal remains active: voice confidence/ambiguity and physical ASR quality/latency,
broad PPTX fidelity, real preparation/rehearsal/hardware, Fast Decisions
calibration/latency, live Sign in with ChatGPT and exact-source packaging remain.
Signing and clean Windows validation remain accepted debt. Dirty worktree preserved;
no staging, commit, push, download/install, account/model call or release occurred.

## Latest continuation - native PowerPoint PDF delivery (2026-10-04)

PDF export is implemented in the Presentation Workspace. This supersedes earlier
missing-PDF statements below. Export PDF opens a native modal with revision number,
static-slide scope, and an explicit Include hidden slides checkbox (off by default).
Cancel and Escape precede the system PDF picker; picker cancellation returns to the
options. The destination picker confirms overwrite. Success reports filename, captured
revision and page count without exposing private paths. Editing still uses the PPTX.

Dependencies were traced before edits: Core verifies and copies the selected immutable
revision, including an optional expected_revision_id guard that keeps legacy PPTX
export callers compatible. Main alone selects/validates paths; no new renderer Core
method or arbitrary renderer filesystem authority was added. Native conversion runs as
one separate --native-pdf-export Python/packaged-sidecar job, not on the Core request
loop, so Office delays do not monopolize Fast Decisions or ASR request processing.
The child does not instantiate CoreService, inherit account/provider credentials, or
use the experimental preview as PDF rendering. Packaging now explicitly collects
pythoncom/win32com.client; the current packaged executable still needs rebuilding and
acceptance against this exact source.

PowerPoint can attach to the user's application instance. The worker never calls Quit
or changes application alerts/security/window state. It opens only its private verified
PPTX read-only without a window and closes that deck in finally. Preflight rejects active
macros/ActiveX, embedded OLE, malformed link inventories and external non-hyperlink
content, including URI targets missing External mode. Such decks require manual export.
PDF output preserves Office labels/IRM and accessibility tags; encrypted output requires
manual review rather than stripping protection. Unsupported platforms/missing Office
return a clear unavailable result. A two-minute timeout/app shutdown terminates only the
owned Python worker, never Office, and waits for that worker to close before cleanup.
An Office hang can leave its owned hidden deck/private files behind; cleanup is best
effort and the timeout asks the user to check PowerPoint. No hung-Office recovery claim.

Native export uses print-quality static slides, no notes pages or slide effects. It checks
native slide inventory/geometry against the copied OOXML, expected visible/all page count,
PDF signature/size/page geometry and the unchanged PPTX hash. Main verifies the PDF receipt
and bytes, flushes a temporary file beside the selected destination, then atomically
replaces it. Failed conversion/revision conflicts leave an existing destination intact.
Office PDF metadata timestamps may change bytes between equivalent exports; no binary
reproducibility claim. This host requires msoCTrue=1 for hidden-slide export: msoTrue=-1
silently omitted the hidden slide, caught by actual page-count validation.

Validation currently recorded under ignored .local/pdf-export/:
- Core final full sweep: 1249 tests pass; 22 native PDF cases and three new
  revision-guard cases. The earlier 1244-test sweep and 72 focused integration checks
  are retained; the final sweep includes subsequent inventory/active-content guards.
- Desktop: 187 unit tests, TypeScript, mypy (164 source files), Core lint/format (245
  files) and desktop formatting pass. Ten worker-boundary cases exercise cancellation,
  unavailable/malformed receipts, credentials, timeout, shutdown and atomic destination.
- Stable-build full Electron/local Core sweep: 117 workflows pass, no renderer errors.
  Only native picker choices are substituted for PDF flows; copied revision, separate
  worker, PowerPoint conversion, validation and atomic save are real. Both modes,
  Escape/picker cancellation and unchanged revision head pass. Receipt gui-final.log;
  gui-result.json is its saved result, not a future overwritten global UI receipt.
- Final rebuilt 720x520 outer / 707x460 content window passes both native export modes,
  unchanged head, no dialog horizontal overflow and a 13px checkbox. window.log,
  window-result.json; inspected window-{visible,including-hidden}-options.png.
- Final rebuilt native rejection GUI passes: an imported deck with an external image
  dependency returns actionable manual-export guidance and leaves an existing PDF
  destination byte-identical. Both export modes still pass in the same 707x460 window,
  with unchanged prior head and no renderer errors (window-rejection-visible-error.log,
  window-rejection-result.json); inspected window-native-rejected.png. The error remains
  in the native modal, focused and measured within the viewport (y=244.55-266.64 / 460),
  and Cancel returns to the workspace. This avoids losing the guidance below a scroll.
- Native hidden-slide fixture exports 21 visible / 22 all-slide PDF pages at 720x540pt;
  page count/size and unchanged source hash pass. All 22 PDF pages were rendered and
  compared with 1280x960 PowerPoint images (max mean channel difference 2.0254/255,
  not pixel equality); contact sheet plus first two full-size pages were inspected.
  All 22 exact speaker-note paragraphs are absent (notes-scope.json).
- A separate live unsaved sentinel deck remains open with identical text, unsaved state,
  presentation count and alerts/security/window settings after child export
  (session-preservation.json). Only our sentinel/fixture decks are closed afterward.

Initial failures remain in receipts: import-path test invocation (fixed with python -m
pytest), lint/type/format issues, hidden-slide -1 mismatch, and a deliberately retained
existing-output rejection when rerunning a scratch export. The first GUI sweep wrongly
matched the first export's success notice during the second export; exact-filename waiting
fixes the test. The initial checkbox stretched under generic input styling; the existing
checkbox-row class corrects it, verified in the rebuilt small-window flow. An additional
real GUI rejection exposed structured Core errors falling through the JavaScript Error-only
catch to a generic message. PdfExport now recognizes isCoreError and presents the safe
manual-export/unavailable guidance within the dialog; the initial exact/regex rejection sweeps are retained
in window-rejection*.log. Final rebuilt rejection acceptance is recorded separately below.

Dirty codex/production-readiness tree/base SHA 657b876739ff7a1cc5709a7e28e92ec2551b337e
is preserved. The source audit covers 366 preceding entries: 358 unchanged, eight intended
existing changes and five additions; packaging adds only the two COM hidden imports.
Source freeze pdf-source-freeze.json covers 371 entries including the packaging spec:
357 of the preceding 365 code/schema entries are byte-identical, eight changed, five code
files are added, and the packaging spec is explicitly included. No staging, commit, push,
download/install, remote model/account call or release occurred.
The full goal remains active: broader corpus/renderer fidelity, real preparation/rehearsal,
provider/ASR/hardware acceptance, Fast Decisions calibration/latency, live Sign in with
ChatGPT and exact-source packaging remain open. Signing and clean Windows remain accepted
debt. Official SIWC sign-in/session docs were refreshed during dependency review; existing
auth was not changed and current live OAuth/account acceptance is not claimed.

Native Office contracts: https://learn.microsoft.com/en-us/office/vba/api/powerpoint.presentation.exportasfixedformat
and https://learn.microsoft.com/en-us/previous-versions/office/troubleshoot/office-developer/use-visual-c-automate-run-program-instance.
SIWC contracts: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
and https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions.


## Latest continuation - measured native text-box fitting (2026-10-04)

This supersedes the unfinished fitting status in the preceding inheritance entry.
Fit text box now has direct owned preview/review/save/discard integration and a strict
Copilot fit_text_shape operation (37 operation types). The read-only, current-revision
list_text_fit_targets catalog exposes resolved authored fonts, geometry, cached scale,
capability reasons and a fingerprint bound to all native inheritance dependencies.
The existing historical text-target reader remains unchanged. Copilot receives fitting
capabilities without fingerprints; Core binds each operation to its actual staged package
and reviews the corresponding staged fonts/geometry rather than reusing the original.

Dependency/policy decisions: Grow preserves width/position, restores authored font sizes
and only increases height. Shrink preserves geometry and relative run sizes, respects an
integer 6-96pt minimum, and starts at or below any cached font scale. Both explicitly
turn wrapping on, restore authored paragraph spacing and replace automatic scaling with
noAutofit. The dialog and Copilot review disclose these effects. Installed exact fonts,
Latin kerning thresholds, mixed styles, paragraph/line spacing, hanging bullets, Arabic
numbering and cached reductions inform measurement. Unresolved/unsupported fonts,
complex scripts, fields, rotated/columned/warped text, groups and connector/animation
dependencies reject. Off-slide/unfittable changes reject atomically. Only managed height,
font sizes and wrapping/autofit XML may change; other content/package parts are preserved.
BASIC Pillow cannot apply optional kerning flags: below the native threshold the reader
uses cached individual Latin glyph advances, without requiring a shaping-library install.

Core validation: a fresh full sweep passes 1224 tests, including 23 new fitting cases;
116 focused inheritance/fitting/protocol/Copilot/transaction checks pass. The 177 desktop
unit tests, TypeScript, mypy (163 source files), lint and formatting pass. Receipts:
.local/text-fit/core-full-fitting.log, core-integrated-final.log, desktop-tests-final-fitting.log,
desktop-types-final-fitting.log, types-final-fitting.log, lint-final-verified.log,
format-verified-fitting.log and desktop-format-final-fitting.log. Initial protocol example,
integration insertion, rounding/type/kerning and formatting failures remain in earlier logs.

Native PowerPoint validation opens 16 baseline/fitted packages across mixed, bulleted,
numbered and cached-scaling cases, matching stored heights and actual per-run fonts,
keeping text within the available box, unchanged other-slide pixels and eight exact undos.
Two additional fitted title-placeholder packages retain inherited Calibri and explicit
Arial families/sizes in grow/shrink, preserve every other package part and pass exact undo.
The 36pt inherited-title fixture correctly rejected shrink at the 6pt minimum; the accepted
43.2pt fixture opens and fits. Native exports were inspected. Receipts: native-fitting-
kerning-fixed.log, fitting-office/result.json, native-inherited-fitting-final.log and
inherited-fitting-office/result.json. Earlier native script API/path errors are retained.
This is bounded native acceptance, not broad font/corpus/renderer equivalence.

The final stable-build Electron/local Core sweep passes all 112 workflows with no renderer
exceptions (gui-final-fitting.log, gui-result.json). Direct fitting verifies shrink
preview/review, changed-minimum invalidation, save/reopen of fitted fonts, grow preview,
changed-strategy invalidation, discard and exact prior-head undo. Copilot creates and
constrains a box, then shrink/grow reviews actual staged fonts (18pt then 7.87pt),
saves one revision, reindexes and restores the exact prior head. Screenshots
workspace-{text-fit,copilot-text-fit}-review.png were inspected. The fixture callout
intentionally overlaps existing content; the review exposes that overlap and fitting
does not claim collision avoidance. The 720x520 outer window (707x459 content) verifies
both previews, changed-minimum invalidation, no dialog horizontal overflow and unchanged
current head after discard (window-fitting-fixed.log, window-result.json); inspected
window-{grow,shrink}-review.png. Opening its collapsed Slide actions disclosure is part
of the small-window workflow.

Earlier failure evidence: Initial test selection
assumed slide 2 after undo selected slide 1; the test now explicitly selects slide 2.
A concurrent sweep stopped earlier in the existing duplicate-slide workflow. The isolated
sweep then exposed an actual Add text box readiness defect: the input/button enabled
before activeSlideId was ready, while the handler correctly rejected the click. A saved
profile reproduction logged a missing slide ID with all other guards satisfied. The input
and button now share that existing UUID guard; the exact saved-profile transition creates
a revision successfully (resume-slide-ready-fixed.log). Temporary diagnostic logging was
removed. A diagnostic sweep overlapped rebuilding and is not accepted as evidence.
These initial/diagnostic sweeps are retained; the final stable run is the accepted
GUI receipt. Native and GUI evidence remains bounded to the described fixtures.
Dirty worktree and codex/production-readiness base SHA are preserved. The fitting source
freeze covers 365 code/test/schema entries: 348 preceding entries unchanged, 13 intended
existing files changed and four additions. No staging, commit, push, account/model call,
download, packaging or release occurred. Broader production-readiness remains active,
including broad fidelity/provider/rehearsal/hardware integration, Fast Decisions
calibration/latency and live Sign in with ChatGPT. Signing and clean Windows remain debt.

## Latest continuation - native text inheritance for fitting

Text-box fitting remains unfinished. Its read-only dependency is now implemented in
core/presenter_core/presentation/text_inheritance.py: internal slide/layout/master/theme
relationships, placeholder matching, master text categories, presentation defaults,
per-level list styles, paragraph defaults and per-run overrides. It returns detached
resolved body/geometry, font metadata and a fingerprint bound to the shape and dependency
parts; it never flattens original styles or mutates a package. Partial default run
properties merge field-wise, so a bold/color override does not erase inherited size.
Exclusive bullet/autofit/fill property groups replace the corresponding inherited choice.
Empty paragraph end properties resolve independently. Theme Latin major/minor fonts and
font references resolve to explicit family names. Missing/ambiguous/external relationships,
unknown outline levels and unsupported theme/script font references reject.

Dependency/native findings: layout placeholder sample paragraphs do not act as child
style defaults; layout list-level properties do. Ordinary text boxes use presentation
defaults ahead of master otherStyle, whereas placeholders use their master category.
Subtitles map to the body master/category. These distinctions were established with
actual PowerPoint probes after initial draft mismatches, not inferred from direct style
inventory. The installed python-pptx placeholder implementation also confirms subtitle/
object/media/picture/table placeholders inherit from the body master. Existing direct
style inventory remains unchanged; it intentionally does not resolve inheritance.
The generic python-pptx fit_text helper is inappropriate for preserving mixed original
font sizes/families/runs: its documented constraints flatten those values and line breaks
(https://python-pptx.readthedocs.io/en/latest/dev/analysis/txt-fit-text.html).

Validation: sixteen new resolver cases cover native defaults, outline levels, empty
paragraphs, partial defaults/run precedence, presentation/master precedence, theme changes
and dependency fingerprints, layout sample-versus-list semantics, subtitle geometry,
read-only detached copies and failure guards. All 66 resolver/table-fit/native-layout
regressions pass (core-final.log). Core lint, mypy (161 source files) and formatting pass
(lint-final.log, types-final.log, format-final.log). Current collection is 1201 IDs:
coverage.json reconciles the preserved 1185 serial-sweep IDs with all 16 new passing IDs.
This is reconciled coverage, not a fresh full 1201-test sweep. Desktop/GUI remain at the
preceding verified 177/110 baseline; no GUI code or provider schema changed this turn.

Native acceptance: eight final inheritance variants plus a subtitle package open
read-only in PowerPoint and match family/size/bold/italic per paragraph, and resolved
left/top/width/height within 0.02pt. They cover presentation/fallback defaults, master
body/other styles, layout sample/list properties, minor theme changes, major font
references and subtitle inheritance: 34 shapes / 42 paragraphs total. All package bytes
remain unchanged. Receipts: .local/text-fit/matrix-verified.log, matrix-result.json,
*-office.json, subtitle-current.log and native PNGs. Subtitle export inspected. Initial
probe/import-path errors, failing inheritance assumptions and corrected matrix logs are
retained. Baseline title/body/explicit/default probes also remain in office-inheritance.json.
The module implements nearest theme font overrides, but native override, complex-script,
partial-transform and broad corpus coverage are not yet accepted.

Source freeze: 361 code/test hashes; all preceding 359 entries are unchanged and only
the resolver/test files were added (.local/text-fit/source-freeze.json). Dirty tree and
branch/base SHA are preserved. No staging, commit, push, account/model call, download,
packaging or release occurred. Broader production-readiness remains active.

Next dependency chain: use resolved paragraphs/body properties to measure text, including
bullets/hanging indents and cached normAutofit scaling. Provide Grow box height (retains
width/font sizes) and Shrink fonts proportionally (retains box geometry and relative
font sizes), with explicit minimum size and atomic off-slide/unfittable rejection.
Bind complete resolved dependencies/geometry/text to preview, commit only managed XML,
verify unchanged surrounding objects/package parts, then integrate owned direct/Copilot
review/save/discard/undo workflows and actual native/GUI acceptance. Do not expose the
read-only resolver as a completed fitting feature. Broad renderer/font/corpus/model/
rehearsal/provider/hardware integration, Fast Decisions calibration/latency and live
Sign in with ChatGPT remain open. Signing and clean Windows remain accepted debt.

## Latest continuation - reviewed native table row fitting

The Workspace now offers Auto-fit table rows. Grow retains current row minima and
increases rows when text needs more room; Compact computes smaller row heights where
possible. Both store explicit native grid/frame heights, preserve column widths,
position, cell text/styles, merge regions and all other package parts, and require
preview/review before saving. A changed target or strategy invalidates review. Discard,
retrieval refresh and exact undo reuse the existing owned-plan transaction lifecycle.

Dependency analysis: setting a native autofit policy alone would leave the experimental
preview's stored-grid discrepancy unresolved. The new table_fit module measures exact
installed font faces, wrapping, character spacing, margins and explicit paragraph/line
spacing. Single-row constraints are satisfied before distributing deficits across merged
spans. Grow keeps existing row minima; Compact starts with minimal rows. Only row h and
frame cy may change, checked canonically; the existing package writer validates final
slide bounds and object geometry. Unsupported/missing fonts, theme font references,
rotated/vertical text, bullets, tabs, cached native scaling and malformed geometry are
rejected before mutation. No font substitution, migration or new IPC is introduced.
The font index skips unreadable unrelated files instead of failing an exact-font lookup.
Measurement is an estimate; unfamiliar fonts/scripts and native wrapping remain subject
to broader fidelity acceptance. The dialog requires review of text fit and nearby content.

Copilot adds fit_table_rows with grow/compact strategies (36 strict operation types).
Fresh fingerprints and previous row/table heights bind to each actual staged package;
compact then grow reviews the fitted intermediate heights and saves one final revision.
Native text-box fitting is still separate unfinished work.

Validation: all 1185 collected Core IDs pass in four serial batches (305/340/234/306),
including 19 new table-fit cases for growth/compact, wrapping/spacing, merged constraints,
unsupported inputs, bounds/atomic rejection, preservation, no-op, staged review and undo.
All 177 desktop tests, TypeScript, mypy (160 source files), lint and formatting pass.
Receipts under .local/table-fit/: core-batches/manifest.json, core-all.log, desktop.log,
types-verified.log, lint-verified.log and format-verified.log. Earlier focused test/type/
lint failures and their corrections remain in the initial logs. One spacing-test fixture
initially extended off-slide; its test geometry was corrected while retaining the separate
atomic bounds-rejection case. The first native wrap fixture also exceeded the slide; the
accepted fixture uses less text, while production code retains the bounds check.

The corrected full Electron/local Core sweep passes all 110 workflows with no renderer
exceptions (gui-final.log, gui-result.json), including direct compact preview/review,
changed-strategy invalidation, save/reopen of actual heights, discard and exact prior-head
undo, plus Copilot compact/grow review/save/undo. Inspected screenshots:
workspace-{table-fit,copilot-table-fit}-review.png. The first full GUI attempt compared
loading placeholder text before row metadata arrived (gui-current.log); the final test
waits for a real row-height cell and compares table data. Copilot shows the fixture's
actual staged heights changing from 94.49pt rows to 28.80pt rows, rather than reusing
original metadata.

Native PowerPoint opens ten baseline/fitted packages across compact, split-grow,
merged-compact, wrapped-grow and explicit-spacing cases. All stored row heights match
native COM heights within 0.2pt; unchanged slide pixels and package parts are preserved,
and five undos restore exact bytes. The split row stores 93.6pt, matching PowerPoint's
previously observed auto-growth from the stored 72pt. Its baseline/fitted native slide
pixels are identical. Native exports were inspected (office/result.json, office-current.log).
The actual Electron/local Core split import at 720x520 verifies grow preview, changed-
strategy invalidation, save/reopen at 93.60pt, compact preview/discard, undo to 72pt,
staged Copilot compact/grow heights and save/undo, without renderer exceptions or modal
horizontal overflow (window-current.log, window-result.json). Its preview now shows all
four combined paragraphs inside the expanded row. A pixel scan of the first row solid
background at 40% slide width compares normalized native/preview boundaries within
0.16% of slide height (preview-grid-comparison.json); this proves that fixture geometry,
not general font layout. Paragraph pitch still differs from
PowerPoint, and original mixed text colors retain low contrast on the header fill.
The first focused UI run failed a scoped test locator; the corrected locator passes.
Inspected screenshots: preview-slide.png, minimum-reviewed.png, copilot-minimum.png.

Source freeze records 359 code/test files: 346 preceding entries preserved, ten
intentionally changed and three added (.local/table-fit/source-freeze.json). Branch is
codex/production-readiness at 657b876739ff7a1cc5709a7e28e92ec2551b337e; the dirty tree
is preserved. No staging, commit, push, download, account/model call, packaging or release.
The goal stays active. Next: general text-box fitting and broader font/corpus/renderer
fidelity, real-model/rehearsal/provider/hardware integration, Fast Decisions calibration/
latency and live Sign in with ChatGPT acceptance. Signing and clean Windows validation
remain accepted technical debt. These fixtures do not establish broad production readiness.

Next fitting dependency: plain text shapes can inherit font family, size, emphasis and
paragraph spacing through paragraph defaults, placeholder/layout/master and theme.
Existing style inventory records direct values and must not be mistaken for resolved
rendering values. Decide explicit grow-box versus shrink-font behavior and bind the
complete text/body/geometry fingerprint before mutation. Fit must preserve surrounding
objects and validate slide bounds; preview rendering of native cached font scaling also
needs acceptance. Reusing the table calculator without resolving these inputs is unsafe.

## Latest continuation - reviewed native table merge/split

The Workspace now offers Merge or split table cells. Select an inclusive rectangle,
preview the native result, review text/layout and save once. Merge moves nonempty
paragraphs in reading order into the top-left cell while retaining their paragraph/run
formatting and every cell's stored styling. Split restores the existing grid (not an
arbitrary new row/column subdivision), retaining combined text in the top-left cell;
Undo restores the original distribution exactly. Changed target/range/action invalidates
review. Native cells remain editable at merge origins; covered cells identify their
owner and disable text input. Row/column reshape is disabled while any merges remain,
and becomes available again after splitting all merges.

Dependency analysis: the old plain-cell inventory rejected every span and text replacement
copied the first paragraph's style. A validated owner matrix now checks rectangular span
coverage, flags, bounds, overlap and consistency; the table writer uses it before mutation.
Paragraph-wise replacement preserves each donor's formatting and skips unchanged cells.
Native merge attributes and text bodies are the only managed fields; canonical checks
preserve other cells, cell properties, stored geometry/grid/style and every other package
part. No migration or additional IPC is needed. Full merged cells can be formatted and
have visible borders changed. Border changes update the visible origin and reciprocal
neighbors; covered cells retain their latent borders for later split. Partial merged
ranges and an edge that only covers part of a larger neighboring merge are rejected,
rather than silently changing that whole neighbor. Malformed/unsupported spans, hidden
covered-cell content, links, multiple runs per paragraph and unsupported extensions
remain read-only. Combined text must still fit the 500-character/10-paragraph cell limit;
otherwise merge cannot publish a revision.

Copilot adds merge_table_cells and split_table_cells (35 strict provider operation types),
using explicit inclusive zero-based ranges. Core binds fresh fingerprints and captures
actual staged cells/merge regions. Review shows proposed ranges, text-distribution
semantics, previous spans and previous text; successive merge then split operates on the
real intermediate package and publishes one final revision. Native spans follow the
[DrawingML table model](https://python-pptx.readthedocs.io/en/stable/dev/analysis/tbl-merge.html).

Validation: a full serial Core sweep passes all 1163 then-collected IDs in four batches
(305/321/249/288). Three further guards pass in the final 38-test merge/Copilot-data run;
final-coverage.json reconciles the union with all 1166 current IDs. Eighteen new merge
cases cover horizontal/vertical/rectangular merges, span errors, style/part preservation,
no-op, dependent text/format/border edits, partial-range rejection, covered text, oversized
text, latent content, neighbor-border atomic rejection, staged review and exact undo.
The existing valid imported merge test now expects editable cells, while mixed-run cells
remain read-only. All 177 desktop tests, TypeScript, mypy (159 source files), lint and
formatting pass. Initial failures included test-helper misuse of the response wrapper,
an old valid-merge read-only expectation and a temporarily misplaced test expectation;
corrected tests preserve the unrelated chart rejection cases. Late guard tests initially
missed an import removed when unused; the final focused run passes.

Receipts under .local/table-merge/: core-batches/manifest.json, core-all.log,
core-focused-final.log, final-coverage.json, desktop.log, types-final.log, lint-final.log
and format-final.log. The first full GUI run stopped at an undefined variable in the new
navigation helper (gui.log); the corrected helper selects the exact table slide and uses
the existing dialog labels. All 108 corrected full GUI workflows pass without renderer
exceptions (gui-current.log, gui-result.json), including the new direct/Copilot merge
checks. workspace-{table-merge,copilot-table-merge}-review.png were inspected. The full
run precedes only the final row-fit disclosure wording; a final rebuild/focused native
workflow verifies that wording with the same direct and Copilot operations.
The focused actual Electron/local Core native import at 720x520 passes merge preview,
review invalidation, save/reopen, disabled covered cells, text-preview discard, split
preview/save/reopen, both undo states and staged Copilot merge/split review/save/undo,
with no renderer exceptions or horizontal modal overflow. Screenshots inspected:
preview-slide.png, split-preview.png, minimum-reviewed.png and copilot-minimum.png.
Receipts: window-final.log and window-result.json.

Native PowerPoint opens 15 unique baseline/merged/formatted/bordered/split packages
across horizontal, vertical and rectangular spans. COM verifies native combined text,
span geometry, preserved grid, subsequent fill/bold/outline properties and split text
semantics. Only slide1 XML changes; other-slide pixels match; twelve undos restore exact
prior bytes. Receipts: office.log, office/result.json and per-case PNG/PPTX exports.
Native/preview screenshots inspected. Preserving mixed header/body text styles can
reduce contrast on the top-left fill; users must review and may change cell formatting.
These fixtures do not prove broad-corpus fidelity. PowerPoint automatically expands a
split fixture's first row from 72 to 93.6 points for combined text, whereas the experimental
renderer uses the stored 72-point grid and clips more text. Stored package bytes are
unchanged by inspection. This concrete fit discrepancy remains open; see
office/native-fit-observation.json. Automatic fitting and broader fidelity remain next.

Dirty work remains on codex/production-readiness at
657b876739ff7a1cc5709a7e28e92ec2551b337e. source-freeze.json records 356 code/test
hashes: 339 preceding entries preserved, fourteen intentionally changed and three added.
No reset, staging, commit, push, packaging or release occurred. The broader goal stays
active. Automatic fitting, broader fidelity/integration, Fast Decisions calibration/latency
and live Sign in with ChatGPT acceptance remain open. Signing and clean Windows remain
accepted technical debt.

## Latest continuation - reviewed native table borders

Table borders now offers a bounded row/column range, nine edge presets (all,
outline, inside, horizontal, vertical and four sides), solid/dash/dot lines,
0.25-12 point widths and opaque RGB color. Remove writes explicit native noFill,
which suppresses inherited borders. Shared edges update both adjacent cells,
including neighbors outside the selected range. The dialog discloses this effect,
shows current native/inherited edge metadata and requires preview acknowledgment.
Changing the table, range or style invalidates review. Save publishes one owned
revision, refreshes retrieval, and exact Undo restores the prior package.

Dependency analysis: reuse the existing native table transaction and plain-cell
inventory; do not route border edits through cell text replacement or table reshape.
Only selected line nodes and reciprocal neighbor line nodes are replaced. Canonical
XML validation excludes exactly those nodes and proves that text/runs, fills, other
edges/diagonals, geometry and table styling remain intact. Every other package part
is preserved. Selected line styling is deliberately replaced, rather than merged with
unknown prior styling. Duplicated native line properties stay read-only. Merged/complex
cells remain read-only: merge/split needs coordinated inventory, span validation,
text handling and editor support so the new result remains editable. No migration or
additional IPC is needed.

Copilot adds set_table_borders (33 strict provider operation types), using explicit
inclusive zero-based ranges and edge/style/width/color fields. Remove requires null
width/color. Core binds fresh fingerprints and reviews actual prior edge metadata
from each staged package, including reciprocal neighbors. Two successive operations
can set the whole grid then remove its interior while retaining the outline.

Validation: all 1148 collected Core tests pass in four serial batches
(305/321/249/273), with no omitted IDs; 51 new border cases cover all preset/style
combinations, reciprocity, preservation, no-op, invalid requests, ambiguous edges,
exact undo and successive Copilot staging. The sweep preceded the last fake-provider
fixture/rationale wording; a final focused border/planner/data run covers the final
source (101 focused tests pass). All 177 desktop tests, TypeScript, mypy (158 source files), lint and formatting
pass. Receipts under .local/table-borders/: core-batches/manifest.json, core-all.log,
core-focused-final.log, desktop.log, types-final.log, lint-final.log and format-final.log.
The initial focused test failed on namespace serialization in its preservation
assertion; exclusive canonical comparison fixes that test-only comparison.

All 106 full Electron/local Core GUI workflows pass, including direct range-border
preview/review invalidation/save/reopen/removal discard/undo and successive Copilot
border review/save/undo, with no renderer exceptions. A focused fresh-build native
import at 720x520 verifies the same direct workflow without horizontal modal overflow.
Receipts: gui.log, gui-result.json, workspace-{table-borders,copilot-table-borders}-review.png,
window-final.log, window-result.json, preview-slide.png, remove-preview.png and
minimum-reviewed.png. Screenshots were inspected. The final rebuild includes the
last fake-provider rationale wording; that wording does not change the tested operations.

Native PowerPoint opens eight baseline/edited packages across outline, dashed grid,
dotted single-cell reciprocal edges and interior removal. COM verifies selected and
neighbor edge visibility, width, RGB and dash style; original cell text and other
package parts remain unchanged, other-slide pixels are identical, and four undos
restore exact prior bytes. Receipts: office.log, office/result.json and per-case native
PNG/PPTX exports. Border identities and line styles use PowerPoint's
[native border API](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.ppbordertype)
and [native dash enumeration](https://learn.microsoft.com/en-us/dotnet/api/microsoft.office.core.msolinedashstyle?view=office-pia).
These are bounded fixtures, not broad-corpus acceptance. The experimental renderer
shows explicit borders/removal but draws denser dashes than PowerPoint; exact line
spacing and inherited-theme fidelity remain open.

Dirty work is preserved on codex/production-readiness at
657b876739ff7a1cc5709a7e28e92ec2551b337e. source-freeze.json records 353 code/test
hashes: 340 preceding entries preserved, ten intentionally changed and three added.
No reset, staging, commit, push, packaging or release occurred.

The broader goal remains active. Next prioritize coordinated native table merge/split
and automatic fitting, then broader fidelity/integration acceptance. Fast-decision
calibration/latency and live Sign in with ChatGPT acceptance remain open. Signing and
clean Windows validation remain accepted technical debt.

## Latest continuation - reviewed native chart axes

The Workspace now offers Chart axes beside the other native chart controls. Users
can choose category/value axis visibility, tick-label position, major/minor gridlines
and a simple native title. Value axes also expose minimum/maximum and major/minor
units (blank restores automatic), plus optional native number formatting. Title/format
null retains existing settings; an empty title removes it. Bounds are finite within
±1 trillion, units 1e-9 to 1e12, minimum < maximum and minor <= major. Gridline/title
removal intentionally removes their styling; adding them uses native defaults. Existing
axis and retained title/gridline styling stays intact. Complex titles can be retained
while other settings change; replacement is disabled. Pie/date/secondary axes,
log/display-unit scales, ambiguous IDs/properties and unsupported extensions remain
read-only. Axis IDs, cross-axis relationships and orientation are preserved.

Dependencies reasoned through before edits: use the existing chart-only clone writer,
not the data/workbook writer. It isolates a shared chart, preserves all original
packages/workbooks, and validates canonical XML outside the selected managed axis
fields, plus slide content/identities. No migration or additional public IPC is needed.
The owned edit-plan preview/review/save/discard/retrieval-refresh/undo lifecycle is
reused, and changed chart/axis/settings invalidate review. The preview uses public
ECharts options for bounds, units, visibility, titles, gridlines and common formats;
series data/caches remain untouched. Tick placement, minor-grid spacing and title
fonts/layout still differ from native PowerPoint in some cases; preview remains
experimental and broader fidelity acceptance is not achieved.

Copilot adds set_chart_axis (32 strict provider operation types), with explicit flags,
nullable title/format and nullable numeric bounds/units. Core binds fresh fingerprints
and captures the exact previous axis settings from each staged package. The review
shows previous/proposed visibility, ticks, grids, title, bounds, units and format;
successive operations can restore automatic scaling while retaining title/format.
Provider context contains axis metadata, not native XML/paths/IDs.

Core evidence: 26 new cases cover both axes on column/bar/line, shared chart isolation,
other-part/workbook/data/legend/labels/colors preservation, no-op and exact undo,
invalid inputs, unsupported native axes, retained styled/complex titles, automatic
reset and staged Copilot binding. All 1097 collected tests pass in four serial batches
(303/307/264/223), with no omitted IDs. This sweep preceded the final fake-provider
GUI fixture/wording additions; a final focused chart/planner/data run covers the
current source (76 focused tests pass). All 177 desktop tests (two new axis-preview cases), formatting, lint,
TypeScript and mypy (157 files) pass. Receipts: .local/chart-axes/core-batches/manifest.json,
core-all.log, core-focused-final.log, desktop-final.log, types-current.log,
lint-current.log and format-current.log. Initial validator rejected signed IDs used by
existing fixtures; these are now validated/preserved. Initial test errors included
an extra revision_id in undo parameters and inherited-namespace serialization comparison;
corrected fixtures use the actual undo contract and exclusive canonical style checks.

GUI evidence: all 104 final-build Electron/local Core workflows pass without renderer
exceptions, including two new direct/Copilot axis checks. Receipts: gui-current.log,
gui-result.json and workspace-{chart-axes,copilot-chart-axes}-review.png. A focused
fresh-build Electron/native import
at 720x520 passes value-axis range/units/title/currency preview, draft invalidation,
save/reopen, category controls, discard and undo without horizontal modal overflow or
renderer errors. Preview and minimum-window screenshots inspected. Receipts:
window.log, window-result.json, preview-slide.png and minimum-reviewed.png. The first
full sweep stopped at an unrelated screenshot capture timeout after fonts loaded;
gui.log preserves the terminal failure. The next full sweep initially assumed slide 2 stayed selected after undo; the test now
explicitly selects its target before opening the dialog or asking Copilot. The current
repeat also checks Copilot staged
axis review, automatic reset, retained title/format, one-revision save and exact undo.

Native PowerPoint evidence: nine baseline/edited/reset packages open across column,
bar and line. COM verifies value bounds -5..30, major/minor units 5/1, both axis titles,
category high tick placement, gridlines, currency number format with linking off,
automatic reset and title/gridline removal. PowerPoint normalizes $0.0 to \$0.0;
this is equivalent formatting, not a source-package mutation. Original series values
remain; other-slide pixels are identical; nine undos restore exact prior bytes.
Native exports inspected. Receipts: office-final.log, office/result.json and per-case
PNG/PPTX exports. The shared synthetic baseline was rejected by PowerPoint before
editing; native acceptance uses ordinary two-chart fixtures. Shared-part preservation
is proven by Core tests, not native acceptance of that synthetic baseline. Earlier
Office logs preserve this and an overly literal format-string comparison failure.

Code/test freeze: .local/chart-axes/source-freeze.json (350 entries); 12 prior files
intentionally changed, 335 preserved byte-identically, three new files. Documentation
is outside it. Branch remains codex/production-readiness at base SHA
657b876739ff7a1cc5709a7e28e92ec2551b337e. Dirty work is preserved.

The broader goal remains active. Next prioritize native table borders/merge workflows
and automatic fitting, then corpus fidelity and real-model integration acceptance.
Advanced chart scales remain open. Fast-decision calibration/latency and live Sign in
with ChatGPT acceptance remain open; signing and clean Windows validation remain
accepted debt. No external account/model calls, downloads, staging, commits, push or release.

## Latest continuation - chart-label preview fidelity and settled snapshots

The experimental chart preview now composes native category/series names and values,
uses explicit label number formats before cache formats, and shows pie percentages
with requested precision. Common decimal, grouped/currency, percent, scientific and
scaled formats are supported. Zero values, negative bar placement, per-point deletion
and custom text, linked-format overrides and separators are handled. Unknown formats
keep the renderer fallback. Sparse caches, unsupported chart families/combinations,
ambiguous chart boxes and mismatched rendered values also keep the existing rendering
instead of risking labels on the wrong points. Pie labels wrap rather than silently
truncating percentages. This resolves the preceding known content/format gap for the
verified fixtures; it does not establish full PowerPoint layout fidelity.

Dependencies reasoned through before edits: the pinned renderer's public renderSlide
API exposes chartInstances, unlike the viewer's convenience snapshot method. The
snapshot uses that API with the existing model, PDF configuration, embedded font faces,
scale and disposable SlideHandle lifecycle. After ready, preview-only ECharts label
options are updated; animations are disabled and charts resized/flushed before capture.
No fixed delay, private renderer API, bundle patch, dependency update, workbook/cache
mutation, Core/PPTX writer or public IPC change is involved. Axes, tooltips, data and
point styles remain intact. The ordinary two-frame layout wait remains for slide text.

Current verification: all 175 desktop tests (18 added), formatting, lint, TypeScript
and mypy (156 files) pass. Core source/tests are byte-identical to the prior slice;
its 1071-test result remains the prior baseline, not a fresh full Core execution.
Both real Electron/local Core sweeps pass all 102 GUI workflows without renderer
exceptions, including the final-build repeat.
Fresh Electron imports of the four native PowerPoint labeled fixtures show decimal
category/value text for column/bar/line and full 26.8%/32.9%/40.3% pie labels. The native
packages are unchanged; prior PowerPoint exports are the comparison reference. A fresh
720x520 second-series review/discard preview visibly shows $8.00/$9.00/$10.00, with bars
present and no modal horizontal overflow. Screenshots inspected. This is focused visual
acceptance, not a corpus-wide pixel-match result or proof of the earlier race's cause.

Receipts: .local/label-preview/{desktop-current.log,types-current.log,lint-current.log,
format-current.log,build-current.log,gui-full.log,gui-first-result.json,gui-current.log,gui-current-result.json,
native-current.log,native-result.json,window-current.log,window-result.json}, four
*-slide.png images and minimum-reviewed.png. Initial scaled-comma unit failure,
lint failures and an attempted blob-fetch diagnostic failure remain in earlier logs;
image-element screenshots replaced that diagnostic extraction. Code/test freeze:
.local/label-preview/source-freeze.json (347 entries); one prior preview-host file
changed, 344 preserved byte-identically, two new files. Documentation is outside it.

The goal remains active. Next prioritize substantial Workspace gaps (native chart axes,
table border/merge workflows and automatic fitting), followed by broader corpus fidelity
and real-model integration. Fast-decision calibration/latency and live Sign in with
ChatGPT acceptance remain open; signing and clean Windows validation remain accepted
debt. No external account/model calls, downloads, staging, commits, push or release.

## Latest continuation - reviewed native chart data labels

Chart labels is now available beside Native charts, Chart legend and Chart colors.
Users can target one series or all series, show/hide labels, choose chart-compatible
placement, show values/category names/series names or pie percentages, and optionally
set a bounded native number format. Null number_format retains existing native
formats. Hiding retains settings and decoration. The owned preview/save/discard/
retrieval refresh/exact undo lifecycle is reused; changed target/settings invalidate
review and save. Existing custom text stays intact and may override displayed content.

Copilot adds `set_chart_labels` (31 native operation types), nullable series_index
(null means all), position, four explicit content flags and nullable number_format.
Visible labels need a content flag; percentages are pie-only. Core binds fresh
fingerprints and captures staged previous series/point settings, including successive
all-series and single-series operations. The review shows exact previous and proposed
settings before package review/save. No provider receives XML, paths or fingerprints.

Dependencies reasoned through before edits: use the existing chart-only clone writer,
not the data writer, so original workbook/chart parts, native data, IDs, geometry,
title, notes, legend and colors remain intact. The selected series label settings and
point overrides receive only requested managed fields; text, fills, fonts, separators,
leader lines and other decoration remain. Global point decoration is copied into
selected-series overrides when needed, preserving other series' global inheritance.
Canonical XML checks normalize inherited point decoration and prove everything outside
selected managed settings unchanged. Unsupported indexes, ambiguous properties, manual
label layouts and existing linked/extension restrictions stay read-only. No database
migration or additional public IPC surface is introduced. Microsoft native label model:
[DataLabels](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.datalabels?view=openxml-3.0.1).

Core evidence: 40 new cases cover every supported placement across column/bar/line/pie,
shared-chart isolation, workbook/other-part preservation, exact data/legend/color
retention, no-op/save/undo, invalid input and stale targets, custom text/decoration/
format retention and reversible hiding, global point inheritance, single-series
isolation and staged Copilot settings. All 1071 collected Core tests pass in four
serial batches (279/321/248/223), with no omitted IDs. All 157 desktop tests,
formatting, lint, TypeScript and mypy (156 files) pass. Receipts under
`.local/chart-labels/`: core-batches/manifest.json, core-all.log,
core-focused-final.log, desktop.log, format-final.log, lint-final.log, types-final.log.
An initial multi-series test incorrectly added a duplicate native series ID;
core-initial.log and batch-1-initial.log preserve that fixture failure.

GUI evidence: all 102 real Electron/local Core checks pass without renderer exceptions.
Three added checks verify all-series draft invalidation/format review/save/reopen/
exact undo, reviewed hide-preview discard, and composed Copilot all/single-series
operations with actual staged previous settings and one-revision save/undo. Receipts:
gui-final.log, gui-result.json, workspace-chart-labels-review.png and
workspace-copilot-chart-labels-review.png. The initial GUI run clicked a hidden
caption instead of its disclosure control; gui.log retains that failure. A separate
fresh build and disposable Electron check exercises second-series currency labels,
pie-only control disabling and preview/review/discard at 720x520 without horizontal
modal overflow. It verifies the final preview limitation notice. Receipts:
window-final.log, window-result.json, controls-visible.png, minimum-reviewed.png.
The full 102-check sweep preceded the final explanatory-copy change; the focused
check and final formatting/lint/types verify the current copy. Screenshots inspected.

Native PowerPoint evidence: 12 baseline/labeled/hidden packages open across all four
chart types. Every native series has the requested label content, position and number
format, actual category/percentage text is checked, hiding removes displayed labels,
original values/title/notes remain, other-slide pixels are identical and eight undos
restore exact prior bytes. Native contact sheet inspected. Receipts: office-final.log,
office/result.json, office/contact.png and per-case PNG/PPTX exports.

NEW KNOWN FIDELITY GAP: saved native labels are correct in PowerPoint, but the app's
experimental renderer ignores c:dLbls/c:dLbl numFmt in favor of series cache formats.
Its column/bar formatter omits category/series label content. A focused $0.00
second-series preview showed plain integers; the full GUI review screenshot also
had an empty plot, while the focused imported-chart preview showed bars. A render-
settling race is possible but unproven. Do not count GUI workflow checks as label
visual-fidelity acceptance. The direct dialog now states the formatting/content
limitation and asks users to verify label appearance in PowerPoint; Copilot already
marks its preview experimental. Repair chart-label preview fidelity before adding
more chart controls. Inspect chart option/formatter integration and render completion
rather than changing caches or source packages just to improve a screenshot.

Code/test freeze: .local/chart-labels/source-freeze.json (345 entries): ten prior
files intentionally changed, 332 remain byte-identical, three added. Documentation
is outside this freeze. Branch remains codex/production-readiness at base SHA
657b876739ff7a1cc5709a7e28e92ec2551b337e; dirty work was preserved.

The broader goal remains active. Next is the observed label-preview fidelity repair;
chart axes, table-border/merge workflows, automatic fitting, broad corpus fidelity
and real-model integration remain open. Fast-decision calibration/latency and live
Sign in with ChatGPT acceptance remain open. Signing and clean Windows validation
remain accepted debt. No real account/model call, download, staging, commit, push,
packaging or release occurred.

## Latest continuation - reviewed native table range formatting

The Workspace now offers Table formatting beside Native tables. Users can style a
header row, the whole table or an inclusive cell rectangle. The bounded controls
cover bold/italic, integer font size (6-96pt), opaque text/fill RGB, horizontal
left/center/right/justify and vertical top/center/bottom alignment. Every setting
starts at Keep current; null preserves each cell's native or inherited setting.
The dialog shows selected text, requires a native preview and text-fit review,
and invalidates save when target/range/styles change. Save/discard/retrieval refresh
and exact undo use the existing owned EditPlan lifecycle.

Copilot adds `format_table_cells` (30 operation types), zero-based inclusive row/
column bounds and seven required nullable style fields. It receives bounded native
style metadata, with null for inherited/custom values. Core binds each staged
fingerprint and captures actual previous selected settings per cell; successive
operations review the already-staged values. The review exposes exact ranges,
requested styles and previous cell formatting before native preview and save.

Dependencies reasoned through before edits: reuse the table writer's isolated
formatting branch without replacing data or structure, and keep the existing
plain-cell restrictions. Empty and uniformly styled multi-paragraph cells receive
consistent run/default/end-paragraph properties. Merged, linked and complex text
stays read-only. Only requested native properties change. Table text, geometry,
IDs, table-style references, borders, margins and other cells/package parts remain
intact. No database migration or additional public IPC method is needed. Invalid
style types, colors, bounds, reversed/boolean ranges and stale fingerprints fail
before publication. Font size can change text fit; preview/review is required.

Core verification: 25 new cases cover all three range choices, actual style metadata,
content/dimensions/borders/margins/other-part preservation, no-op and exact undo,
invalid styles/ranges/stale targets, empty/multi-paragraph text, retained native
style references and partial-style inheritance, plus successive staged Copilot
fingerprint/previous-value binding. The complete Core sweep passes all 1031
collected tests in four serial batches (249/311/248/223), without omitted IDs.
All 157 desktop tests, formatting, lint, TypeScript and mypy (155 files) pass.
Receipts: `.local/table-format/core-batches/manifest.json`, `core-all.log`,
`core-focused.log`, `desktop.log`, `format-final.log`, `lint-final.log`,
`types-final.log`. Initial fixture unpacking/namespace-comparison errors and the
test-provider inference-only typing fix are retained in earlier logs.

GUI verification: the full real Electron/local Core sweep passes all 99 checks,
without renderer exceptions. Three added checks cover header formatting and draft
invalidation/fresh preview/save/exact undo, whole-table preview discard without
changing the saved revision, and composed Copilot header/body formatting with exact
previous native styles and inclusive range review. Both review screenshots inspected.
Receipts: `.local/table-format/gui-final.log`, `gui-result.json`,
`workspace-table-format-header-review.png`, `workspace-copilot-table-format-review.png`.
The earlier sweep failed on an incorrect automation checkbox label; its log is retained
in `gui.log`, and the corrected complete sweep passes. A focused disposable Electron
check verifies the visible RGB swatch (42x31.5px, 3px padding), selected-range native
preview/review/discard at 720x520 and zero horizontal dialog overflow. Control/minimum
window screenshots inspected; `window.log`, `window-result.json`,
`controls-visible.png`, `minimum-reviewed.png` record this separate check.

Native PowerPoint verification: six baseline/formatted packages open across header,
whole-table and selected body-column cases. Actual COM font bold/italic/size/RGB,
cell fill, horizontal/vertical alignment match all requested values. Native text,
margins and untouched cells are equal, other-slide pixels are identical, only
slide1.xml changes, and three undos restore exact baseline bytes. Full-resolution
exports and contact sheet inspected. Receipts: `.local/table-format/office.log`,
`office/result.json`, `office/contact.png` and per-case PNG/PPTX files. These are
ordinary synthetic native tables; broad imported-table/corpus fitting is unproven.

Code/test freeze: `.local/table-format/source-freeze.json` (342 entries). Ten prior
files intentionally changed, 329 remain byte-identical and three files were added.
Documentation is outside this freeze. Branch remains `codex/production-readiness`,
base SHA `657b876739ff7a1cc5709a7e28e92ec2551b337e`; the dirty worktree is preserved.

Table cell/header formatting closes the prior direct/Copilot appearance gap. Richer
native chart axes/data labels and table borders/merge controls, automatic fitting,
broader corpus fidelity and real-model integration quality remain open. Fast-decision
calibration/latency and live Sign in with ChatGPT acceptance remain open. Signing and
clean Windows validation remain accepted technical debt. No real account/model call,
download, staging, commit, push, packaging or release occurred. Goal remains active.

Date: 2026-10-03

## Result

The updated Electron UI suite passed 25 workflows, including Copilot-generated
multi-operation plans, grouped text/notes preview, discard, one-revision save,
whole-plan undo, and review of every affected slide in a deck-wide proposal.
The final review layout was inspected in screenshots. A fresh sequential
`pnpm check` passed formatting, lint, typing, 101 desktop tests and 495 Core
tests. Earlier ASR failures led to an idle-worker wakeup repair that preserves
queued audio and keeps ownership after device-stop failure, plus deterministic
shutdown and speech-active partial verification. The check log is
`.local/handoff-check-20261003.log`; the continuation handoff is
[`SESSION_HANDOFF.md`](SESSION_HANDOFF.md).
The unsigned Windows package and
packaged smoke results predate these changes and require rebuilding. The
installer remains unsigned and has not been installed through its setup flow.
This is not a production release sign-off. The changes remain uncommitted.
Release E2E output now includes both the base Git SHA and a SHA-256 fingerprint
of tracked and non-ignored untracked source files captured before the run;
hosted CI, product, real-device, clean-install, and signing gates remain open.
The frozen first-MVP contract remains
[`docs/MVP/RELEASE_BASELINE.md`](MVP/RELEASE_BASELINE.md); the user has also
authorized continuing the broader Presentation Workspace roadmap.

## Workspace authoring and GUI refresh (2026-10-02)

The release priority now follows complete product workflows: native creation,
editing and Copilot review, rehearsal findings into reviewed edits, then
integration and release gates. Major Workspace capabilities remain incomplete.

- New presentation creation reviews a manual or Copilot-planned outline before producing
  native editable PPTX slides and notes. Generated documents pass through the
  existing ingestion pipeline, original-revision recording, retrieval and
  source refresh. Copilot planning captures objective, audience, briefing, and
  requested slide count, retrieves bounded project evidence and approved
  explanations, and supports refinement of the complete draft. Users can edit
  titles, points, and notes and inspect cited excerpts before final review.
  Core rejects fabricated evidence IDs and cross-project planning lineage.
  No deck is created until the user chooses Create presentation. Reviewed
  evidence references are retained in notes, and PPTX properties record the
  successful planning run. Live model quality remains unverified.
- The editor now puts the slide above expandable slide/layout actions, groups
  the inspector into Text, Objects, Notes, Purpose, History and Rehearsal, preserves
  drafts across panel changes, and exposes undo/redo next to revision status.
  The duplicate page heading is removed to give the canvas more room.
- **Edit slide together** stages supported text-shape and plain speaker-notes
  changes in an actual native PPTX, displays the proposed slide and content
  changes, and saves the exact reviewed bytes as one revision after explicit
  review. Discard restores the current preview; undo restores the whole prior
  revision. Successful saves request re-indexing and report indexing failure
  separately. The underlying transaction engine composes 1–20 allowlisted
  existing native operations. Schema v13 records content-free operation/target
  metadata atomically with the revision. Core verifies stale/scope/integrity
  rejection, audit rollback, reader cleanup, expiry, deletion, and safe abandoned
  preview reconciliation.
- **Ask Copilot to edit** proposes 1–20 typed operations for the current slide
  or whole presentation through the selected reasoning provider. Fifteen native
  operation types support text, notes, formatting, geometry, crop, objects,
  layouts and slide structure. Core resolves target preconditions against the
  rolling staged package, rejects targets outside the selected baseline scope
  and fabricated evidence IDs, and rechecks the source before and after inference.
  The dialog renders the actual proposed PPTX, shows rationales, text changes
  and supplied evidence, and requires viewing every affected slide and explicit
  acknowledgement before saving one revision. Changing the request invalidates
  approval. Audit metadata retains successful provider-run and evidence IDs.
  Raw image ingestion and references to newly created objects within the same
  plan are unsupported. Local deterministic workflows are verified; live model
  quality and general voice planning remain open.
- A disposable real Electron profile validated panel switching, draft
  retention, text preview/save, notes save, undo/redo, restoration, and native
  outline creation followed by normal revision editing. Screenshots were
  inspected. This is local workflow evidence, not user-session acceptance.
- Local PDF.js assets now restore PDF-containing EMF charts in the isolated
  preview. Both the Chromium harness and built Electron `file://` path were
  exercised. The 33-record PowerPoint comparison completed with 31 decks /
  613 slides, two external-relationship skips, zero failures, and 21 slides
  with unstable PowerPoint captures. All 613 comparable slides still contain
  stable visual differences; the fidelity gate remains open. The report is
  `.local/preview-compare-33-pdfjs-20261002.json` (ignored local evidence).
- The candidate connects Workspace to Run with an expected revision,
  keeps slide tracking bound to the rehearsed revision, and presents markers,
  long explanations, evidence-review candidates, and spoken explanations in
  a Rehearsal inspector. Findings map stable slide identities through
  reordering. Users can prepare notes, spoken wording, or a provider rewrite,
  dismiss a finding, and undo dismissal. Saving a reviewed text or notes edit
  commits the finding's provenance with the new revision in one transaction.
  Candidate quotes remain separate from trusted instructions and approved
  knowledge. Core checks cover frozen revision binding, reordered slide
  mapping, stale/cross-deck edit rejection, atomic provenance rollback,
  reopening dismissed findings, and dismissal during provider generation.
  Electron exercised rehearse, mark, stop, prepare notes, save, and applied
  status, plus dismissal/reopening. Screenshots were inspected. These are
  local synthetic checks, not real presenter acceptance.
- General voice edit plans, voice creation, native templates,
  comparison across rehearsals, and the broader semantic model remain open.

## Earlier release-gate verification (2026-10-02 UTC)

- `pnpm check` passed after the ASR zero-onset, ChatGPT sign-in cancellation,
  and Windows DPAPI corrections: Prettier, Ruff, ESLint, TypeScript, mypy, 101
  desktop tests, and 447 Core tests. The SIWC commit re-check prevents a
  cancelled sign-in from saving credentials when cancellation wins the account
  lock; the Windows DPAPI encrypt/read/delete round-trip also passed locally.
- Python security remediation: `pypdf` is pinned to 6.19.0, `urllib3` is
  locked to 2.8.0 through FastEmbed's Requests dependency, and dev-only pytest
  is pinned to 9.1.1. Both `uv audit --locked` and `uv audit --locked
  --no-dev` report no known vulnerabilities; the Core suite first passed with
  443 tests after the dependency update and now passes with 445 tests after the
  ASR regressions were added. Hosted and trusted-local workflows now audit the
  Python lock as well as JavaScript dependencies.
- `pnpm test:providers-ui` passed provider configuration, synthetic inference,
  persistence, credential-boundary, Ollama alias, selected-tag install-hint,
  ChatGPT plan signed-out/model-gating, and usage-settings link flows. SIWC
  OAuth and inference use local synthetic fixtures; no account was signed in
  and no live inference ran.
- `pnpm test:codex-containment` passed for bundled Codex runtimes 0.153.1 and
  0.153.4, with 62 adversarial calls per runtime. This validates the local
  containment probe, not account-backed live Codex behavior.
- `pnpm test:ui` passed all 19 Electron flows. The separate
  `pnpm test:ui:corpus-overflow` check passed on record `3996727`, slide 7,
  shape 5: Save required overflow acknowledgement, the imported source hash
  stayed unchanged, and no revision was saved.
- `pnpm test:install-smoke` returned `manual_required` with
  `machine_mutated: false`, as intended for a local machine. It does not prove
  install, uninstall, or reinstall behavior.
- `pnpm package:win` rebuilt the unsigned installer after the Windows DPAPI
  vault fix;
  `pnpm test:packaged` passed with exit code 0, no orphaned sidecar, and no
  model download. The current installer is 268,483,958 bytes with SHA-256
  `D8335576636245B14E1469E5F046723CB9E0FC44E7BAB623F3C8F73A790FABFE`;
  its blockmap is 281,293 bytes with SHA-256
  `2E3369ED6FA48ADD503D0753B4BF5EAF929F2065EA5D6FFC620B8EB2BE9A3C11`.
  Authenticode reports `NotSigned` for both installer and app executable.
- A production Vite module report on the current working tree maps the main
  window's initial JS and CSS to 233.59 KB minified (73.83 KB gzip): a 40.25 KB
  entry, preloaded React/runtime chunks, and 1.91 KB of CSS. The 1,276.73 KB
  chunk previously labeled as the main entry is the separate Presentation
  Preview window's renderer bundle (390.91 KB gzip). The Workspace preview
  worker is another on-demand asset at 951.93 KB. These are build sizes, not
  user-facing startup or first-navigation timings; no latency threshold has
  been set or validated yet.
- `pnpm test:e2e:release` passed E2E-01 through E2E-08 with no content output.
  The runner used base SHA `657b876739ff7a1cc5709a7e28e92ec2551b337e` and
  captured working-tree SHA-256
  `52e0e03533966cab69b5bfefd5741583d2e2c65e1fb8a2ab2567a4cf9509a649` at
  runner start (`2026-10-02T12:18:23.500809+00:00`). This is local
  deterministic E2E evidence, not hosted CI or a signed install.
- The optional Sign in with ChatGPT path follows OpenAI's current [open-source
  app token-sharing guide](https://developers.openai.com/siwc/token-sharing-open-source),
  its [registration and sign-in contract](https://developers.openai.com/siwc/token-sharing-open-source/sign-in),
  [model listing and inference requirements](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference),
  [UI/UX guidance](https://developers.openai.com/siwc/ui-ux-guidelines), and
  [preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).
  The implementation uses first-time dynamic client registration, persists the
  issued client ID per account and a stable `urn:uuid:` host ID, exposes the
  documented “Continue with ChatGPT” action, and sends bounded streamed
  Responses API requests with storage disabled.
  Local tests cover OAuth callback/state/PKCE/JWKS/scope validation, account
  isolation, refresh rotation, sign-out cleanup, model visibility, bounded
  streamed responses, failure handling, and fixed-url ChatGPT usage-settings
  routing. Workspace quota errors offer a Manage ChatGPT usage action. Real
  account eligibility, browser sign-in, and live plan inference are unverified.
- The existing Jev-compatible Ollama System One adapter supports installed
  `nimble:9b`, `tev1:4b`, and `tev1:0.8b` tags plus the supported quantized
  variants and the `nimble:latest` / `tev1:latest` quick-start aliases. Settings
  displays the exact selected-tag install command. It stays on Ollama loopback
  and does not launch the server or download weights. No live Ollama runtime or
  model was available, so decision quality and latency remain unverified. The
  adapter now rejects Tev1 inputs above 1 KiB of state / 1.5 KiB total request
  and Nimble inputs above 5 KiB of state / 6 KiB total request before model
  lookup. These UTF-8 byte guards reserve context headroom but are not exact
  token counts. All 38 focused decision-provider tests pass, including the
  model-specific preflight limits. The
  OpenAI Decisions API is confirmed as a GPT-6 Luna limited preview for
  finite-answer decisions by the official [DevDay recap](https://openai.com/index/devday-2026-recap/).
  The 2026-10-02 documentation gap was superseded on 2026-10-07:
  the [Decisions guide](https://developers.openai.com/api/docs/guides/decisions)
  and [create reference](https://developers.openai.com/api/reference/resources/decisions/methods/create)
  now document the beta contract. The native adapter is implemented; live API
  access, quality, calibration and latency remain acceptance gates.
- The latest integrated 33-record preview comparison completed with 31 decks /
  613 slides compared, two external-relationship skips, zero failures, and 21
  unstable captures. The bounded ellipse pass promoted six pictures; stable
  differences remain on all 613 comparable slides, so visual fidelity is
  still a release blocker. See the latest
  [corpus](PRESENTATION_WORKSPACE/CORPUS.md) and
  [fidelity report](PRESENTATION_WORKSPACE/PPTX_FIDELITY.md).

The owner classifies the unavailable clean Windows machine/device and
production signing identity as operational tech debt. Neither is configured in
this environment. That classification does not change the evidence: clean-
machine install, physical microphone/HUD behavior, and signed-distribution
checks remain unverified and are still required before claiming a signed
Windows release.

The worktree is based on `657b876739ff7a1cc5709a7e28e92ec2551b337e` on
`codex/production-readiness`. Hosted Windows and Trusted Local CI results for
that base do not cover this uncommitted diff. GitHub currently shows the
latest successful `CI` and `Local CI` runs on `main` for that SHA at
2026-09-29 18:10 UTC; this branch has no associated PR or hosted run.

## Verified locally

| Gate                                                                                                  | Result                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| pnpm check                                                                                            | Pass on 2026-10-02: Prettier, Ruff, ESLint, TypeScript, mypy, 101 desktop tests, and 447 Core tests, including a local Windows DPAPI vault integration check.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `pnpm test:ui`                                                                                        | Pass on 2026-10-02: all 19 Electron UI flows passed. See the latest verification refresh above for the bounded local evidence and limits.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `pnpm test:ui:corpus-overflow`                                                                        | Pass on 2026-10-02 against cached record `3996727`, slide 7/shape 5: Save required explicit overflow acknowledgement; the imported source hash stayed unchanged and no revision was saved.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Workspace text-layout preflight                                                                       | Pass locally: the isolated renderer reports when measured text fragments escape a uniquely matched, unrotated target's shape bounds. The UI blocks save until acknowledgement for detected overflow and marks unmeasurable cases for manual review. The browser warning is now validated on the Office-reviewed source case `3996727`; the separate exported-PPTX visual `needs_review` remains open.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Isolated preview lifecycle                                                                            | Pass for normal UI flow: candidate renderer runs in a hidden sandboxed/context-isolated window with no Node integration, restrictive CSP, denied permissions, and packaged network access blocked. Input is capped at 50 MiB; open/render requests have 120-second deadlines and close destroys the child. Font detection scans at most 12 MiB of PPTX XML and 64 families; fallback sources use installed local fonts only. The main-window HTML preloads a 39.72 kB app chunk and 189.60 kB React chunk (71.34 kB gzip combined); audience, rehearsal, settings, and Workspace panels load on first visit and stay mounted afterward. The isolated preview route builds a 1,276.72 kB chunk (390.92 kB gzip) and a 951.92 kB worker; the Vite size warning and cold preview cost remain optimization work. A 48-slide corpus deck opened in 1,726 ms; a 52,412,416-byte fixture 16 KiB below the cap opened in 2,160 ms. The latter's preview renderer peaked at 181 MiB private bytes and 279 MiB working set; all Electron processes peaked at 880 MiB private bytes and 1,032 MiB working set. The fixture adds unreferenced inert data, so large-media expansion is unmeasured. The preview process exited after close and temporary source-byte copies are cleared. This is one-host sampled profiling, not a general memory ceiling; responsiveness and timeout/cancellation paths remain unverified. Details and corpus-deck timings are in the [fidelity evaluation](PRESENTATION_WORKSPACE/PPTX_FIDELITY.md). |
| `pnpm test:providers-ui`                                                                              | Pass on 2026-10-02: provider settings and synthetic inference, credential boundaries, Jev, OpenAI Responses Fast/Ultrafast, ChatGPT plan signed-out/model gates, and Ollama Nimble 9B / Tev1 4B and 0.8B options. OAuth and inference used synthetic fixtures; a separate local Windows DPAPI vault encrypt/read/delete check passed. No account was signed in and no live provider inference ran.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Windows x64 package                                                                                   | Built on 2026-10-02 from the current working tree as an unsigned x64 NSIS installer. The top verification refresh records the current installer and blockmap sizes and hashes. Electron Builder skipped signing; no installer install cycle was run.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| pnpm test:packaged                                                                                    | Pass on the 2026-10-02 package: Codex runtime 0.153.4 and SHA-256 `444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b`, license and notices verified; packaged sidecar smoke passed with zero orphan sidecars, model downloads, or renderer-supplied paths. This does not validate installer installation.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| pnpm test:e2e:release                                                                                 | Pass on 2026-10-02: E2E-01 through E2E-08 with no content output. Base SHA `657b876739ff7a1cc5709a7e28e92ec2551b337e`; current-run tracked and non-ignored untracked working-tree fingerprint `a8d2a293d1c501fc0bffaee9636a86012f92b9c144585deac76c94a12b566ad3`. This local run is not hosted CI for a committed candidate.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `pnpm test:codex-containment`                                                                         | Pass: 62 adversarial calls against each pinned runtime; the 0.153.4 bundle hash matches.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `pnpm test:privacy-network` / `pnpm test:m9`                                                          | Pass: 15 privacy-network tests and 16 M9 release tests.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `pnpm audit`                                                                                          | Pass after patch-only overrides for `undici`, `brace-expansion`, and `fast-uri`; full development and production dependency graph reports 0 known advisories. Both Hosted Windows and Trusted Local CI run the audit after frozen-lockfile installation. The initial findings were limited to build/download/lint tooling.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Ollama loopback runtime                                                                               | Not available on this validation host: no `ollama` command and no API at `127.0.0.1:11434`. No model was downloaded; no live Nimble/Tev1 inference was run.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| pnpm benchmark:release | Deterministic smoke passed; this command performed no model inference or network access. The refreshed aggregate `.local/m9-release-asr-absolute-20261002.json` includes the corrected ASR event-path failure above; its retrieval report is stale (SHA `0109376c4b483c6e50b7067ec7fdf82f97691268`). RTX 4080 detection is metadata only; CUDA ASR remains unavailable. The report records base HEAD while this working tree is uncommitted. |
| pnpm test:embedding-real                                                                              | Pass with explicit task-local cache .local/production-model-validation: pinned BAAI/bge-small-en-v1.5, 384 dimensions, fingerprint c8f43b02f96515510ebdb317ffa70fb15f84819470691bd5bde738c697b71d86, model build 2.197 s; indexed 29 chunks and passed all seven semantic/hybrid golden queries. The fixture generator preserves those seven cases, and acceptance errors with RETRIEVAL_ACCEPTANCE_NO_GOLDENS instead of passing 0/0.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| pnpm benchmark:retrieval                                                                              | Pass on 50,000 vectors and 20 queries using the same explicit local cache: hybrid p95 71.966 ms against the 250 ms target; query embedding p95 32.429 ms; matrix-search p95 1.781 ms. Peak-process-memory measurement was unavailable.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| pnpm test:asr-real                                                                                    | Pass using task-local Systran/faster-whisper-base.en on CPU/int8: the local-only synthetic 7.135-second fixture matched all four expected phrases. No provider was called.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| pnpm benchmark:asr | Corrected absolute-time synthetic run failed its latency targets (three CPU/int8 iterations): first partial p50 939.602 ms / p95 947.088 ms versus 500 ms; final event p50 926.203 ms from last speech-active frame / 326.203 ms after VAD completion versus 900 ms; final decode p50 376.752 ms. The full-fixture ASR acceptance passed all four expected terms. Absolute-time pacing removes cumulative Windows timer drift from the superseded service-v2 report. See `.local/asr-baseline-onset-fixed-20261002.json` (corrected zero-onset timing). The report records base HEAD while the working tree is uncommitted. |
| CUDA ASR probe                                                                                        | CTranslate2 sees one CUDA device on the RTX 4080, but model inference fails because cublas64_12.dll is missing. The application remains on its supported CPU/int8 path; no CUDA libraries were installed.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `pnpm test:install-smoke`                                                                             | Local invocation reports `manual_required` and `machine_mutated: false`; Hosted Windows CI is configured for an isolated install/launch/uninstall/data-retention/reinstall cycle, but its latest successful run covers base SHA `657b876739ff7a1cc5709a7e28e92ec2551b337e`, not this uncommitted candidate.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `pnpm workspace:fetch-corpus` / `pnpm workspace:inventory-corpus` / `pnpm workspace:roundtrip-corpus` | Live metadata and hashes verified for all 33 pinned decks: 23 Zenodo CC BY 4.0 and ten Internet Archive items attributed by Microsoft PPT-Eval as Public Domain Mark 1.0. Core parser-supported all 33 with no structural failures. Text-edit/export/restore smoke passed on 29; four had no qualifying text target. PowerPoint opened 27 of 29 edited exports with matching slide counts and unchanged hashes; two external-relationship records were skipped. The runner now starts a fresh PowerPoint process per deck. The isolated visual run had 21 passes, 5 masked passes, 1 review-required case, and 2 skips; all seven new records passed unmasked. Record 3996727 needs review because the stress edit wraps a title beyond its shape, but leaves all other slides unchanged. No slide text or renders were retained.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `pnpm workspace:visual-compare`                                                                       | Latest 2026-10-02 corpus comparison covered 31 of 33 decks and 613 slides, skipped two external-relationship decks, had zero failures and 21 unstable Office captures, and still found stable pixel differences on all 613 comparable slides. Preview fidelity remains a release blocker; the current evidence and focused theme-background investigation are in `docs/PRESENTATION_WORKSPACE/CORPUS.md` and `PPTX_FIDELITY.md`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Authenticode inspection                                                                               | The current local installer reports `NotSigned`; no production identity is configured. Routine CI/local packaging is explicitly unsigned. `pnpm package:win:release` overrides that setting and requires signing to succeed; it has not been run because the identity is unavailable.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Windows installer artifact | Rebuilt from this working tree on 2026-10-02 after DPAPI vault hardening: `artifacts/installer/Presenter-Copilot-0.1.0-x64-setup.exe`, 268,483,958 bytes; SHA-256 `D8335576636245B14E1469E5F046723CB9E0FC44E7BAB623F3C8F73A790FABFE`; blockmap 281,293 bytes, SHA-256 `2E3369ED6FA48ADD503D0753B4BF5EAF929F2065EA5D6FFC620B8EB2BE9A3C11`. Packaged smoke passed; installer and app executable are `NotSigned`. Installer remains uninstalled and unpublished. |

## Current Presentation Workspace scope

The import panel now reports shape, picture, graphic-frame, connector, and
group counts from Core's bounded OOXML inventory. These structural counts help
show what the deck contains but do not indicate visual fidelity or complete
feature support.

The limited research preview can render an imported PPTX, show a structural
inventory, request a review-only rewrite for selected text in a supported one-paragraph shape, replace text in a supported single-run or uniformly formatted
multi-run shape, and set bold, italic,
font size, or solid RGB color across every run in a structurally simple text shape of up to 128 paragraphs (within the Workspace's 2,000-character target limit) plus left/center/right/justified alignment, bounded left indentation from 0 to 144 points, signed first-line/hanging indentation from -144 to 144 points, whole-point line spacing from 1 to 144 points, disc, hollow-circle, square, or dash bullet styles, no-bullet formatting, or Arabic-period automatic numbering across simple paragraphs, and before/after spacing from 0 to 144 points; set direct solid RGB fill or outline colors on
supported top-level shapes, create a simple centered text box or a rectangle or
ellipse with explicit slide-bounded geometry and direct RGB fill/outline, add a PNG or
JPEG picture with editable in-bounds position and size plus optional
alternative text, edit plain
speaker notes with uniform formatting and at most one run per paragraph, move
or resize a simple unrotated top-level shape or picture within slide bounds,
crop a simple embedded picture within its existing frame, replace its image
with a validated single-frame PNG or JPEG up to 4 MiB, and delete or
duplicate an eligible top-level shape or picture. It can reorder,
duplicate, and delete supported slides. A blank slide can be inserted after the
selected slide using its layout; it starts with no objects or notes and does
not copy slide-local media or animation relationships.

Rewrite proposals send only the selected paragraph and the user's instruction
through the configured reasoning provider. They are bound to the current
document revision and fail closed if the selected revision changes during
inference. Core returns model text for review; users must copy it to the
replacement editor, preview it, and save through the existing revisioned edit
transaction. The newer **Ask Copilot to edit** workflow supports reviewed
multi-operation plans as described above. Voice remains limited to selected-text
dictation; general voice planning and unreviewed application are unsupported.

For a mock text replacement, the isolated preview measures rendered text
fragments against the source bounds only when it can uniquely match a
top-level, unrotated, single-run shape. Detected overflow shows a warning and
requires explicit acknowledgement before saving. A missing or ambiguous
measurement is surfaced as manual review; a measured fit is not proof of
PowerPoint or export fidelity.

Object deletion and duplication are disabled for placeholders and objects
referenced by slide connectors or animation timing. Slide duplication
preserves supported layout, image, and hyperlink relationships and clones
notes. Slide deletion preserves media, fails closed for custom-show, section,
or package references, and keeps at least one slide. Each saved change commits
an immutable revision; the UI can restore a prior revision, undo to its parent,
redo through a unique child, and export the current or original PPTX package.
Redo stops safely when a revision has multiple children, and the user can
select a branch from history. Rich or oversized speaker notes and unsupported
geometry remain read-only.

After blank-slide creation, edits, shape/picture creation, cropping, image replacement, deletion, reordering, restore, undo, or redo,
the UI asks Core to re-index the verified current revision. Revision-scoped
retrieval excludes stale source text and retains prior revision units for
sessions already bound to those revisions. A user-triggered slide-purpose
suggestion can use Jev via OpenRouter, OpenAI Responses Fast or Ultrafast with
strict Structured Outputs, a configured local structured-output model, or an
already installed Nimble/Tev1 model through Ollama's loopback-only System One
endpoint. Core limits
the input to supported text on the selected slide, enforces project privacy,
records content-free run metadata, and requires user review. Decision output
does not edit the deck or persist; only an explicitly confirmed or corrected
purpose category is saved as user-confirmed semantic metadata against the exact
revision and stable slide ID.

These gates establish bounded local behavior, not general PPTX compatibility.
The preview renderer can omit unsupported content. Editing remains limited to
single-run or uniform-style multi-run text replacement, all-run formatting in
structurally simple text shapes of up to 128 paragraphs,
horizontal paragraph alignment, bounded left indentation, signed first-line/hanging indentation, bounded line spacing, disc, hollow-circle, square, or dash bullet styles, no-bullet formatting, or Arabic-period automatic numbering across simple paragraphs, and before/after spacing, simple direct
shape colors,
bounded rectangle/ellipse creation, plain speaker notes, bounded
geometry changes for simple top-level shapes and pictures, simple picture
creation, cropping, and PNG/JPEG replacement, eligible object
deletion/duplication, blank-slide creation using the selected slide's layout or another slide's existing layout, applying an existing layout to the selected slide, supported
slide deletion/duplication, and slide reordering. Percentage-based or fractional line spacing, custom numbering schemes, picture bullets, arbitrary bullet glyphs and custom bullet font/color/size styles, multi-shape bulk formatting, advanced shape effects and advanced image treatment, diagrams,
additional object types, unused theme-layout discovery or selection, PDF export, and
presentation creation from scratch are not implemented.

An isolated theme-image tile rasterization prototype was evaluated in QA and
removed from application code after it regressed the cover slide's stable RGB
MAE on `90000006` from 6.5497% to 8.0112%. Full theme-background fidelity
remains a release gate; the paired metrics are in
`PRESENTATION_WORKSPACE/PPTX_FIDELITY.md`.

The synthetic 22-slide fixture does not establish behavior across real-world
presentation files or PowerPoint versions. Local regression coverage verifies
stale revision/target/geometry/crop rejection, exact slide-order permutation
validation, single-member package rewrite, slide-bound rejection, placeholder
deletion rejection, custom-show deletion rejection, last-slide protection,
slide/notes relationship preservation, read-only rejection of rich notes,
untouched package-part preservation, edited slide text and speaker notes
becoming searchable after a verified re-index, historical revision text
remaining available by ID, branch-aware undo/redo with ambiguous redo
rejection, blank-slide creation using another slide's layout while
excluding source slide content, picture creation with bounds and alt-text
validation plus a private media part and relationship, picture cropping that
changes only the selected slide crop rectangle, rectangle/ellipse creation
with bounds, style, identity and package-part validation, and picture
replacement that adds a private media part,
retains shared images and picture geometry, and preserves unrelated package parts.

## Open product and release gates

- Run Hosted Windows and Trusted Local CI against a reviewed candidate commit
  SHA. Current CI evidence belongs to the base SHA only.
- Run and review the updated Hosted Windows CI install cycle on the exact
  candidate SHA. It exercises install, packaged launch, uninstall, retained
  app data, and reinstall on that job's disposable runner; real-device and
  ordinary user-profile acceptance still need physical checks.
- Reduce the remaining CPU ASR service-path latency. The benchmark now paces
  synthetic 20 ms frames against absolute capture-time deadlines, avoiding the
  cumulative Windows timer drift in the earlier
  `.local/asr-benchmark-service-v2-20261002.json` run. In three CPU/int8
  iterations, Core's first `asr.partial` p50 was 939.602 ms (p95 947.088 ms)
  against 500 ms. The first `asr.final` p50 was 926.203 ms after the last
  speech-active frame against 900 ms, or 326.203 ms after VAD completion with
  its 600 ms end-silence window. Adapter-only final decode p50 was 376.752 ms.
  The updated report is `.local/asr-baseline-onset-fixed-20261002.json`; it
  records the base HEAD SHA while the measured working tree is uncommitted.
  Earlier partial-latency thread diagnostics predated the zero-onset fix and
  are not comparable. A 250 ms initial / 300 ms repeat partial schedule was
  rejected after only one of three iterations emitted before finalization and
  final-event p50 rose to 1,106.771 ms. The shipped 500 ms cadence remains.
  A separate in-memory partial decode probe with timestamps disabled and
  `max_new_tokens=8` produced a 600.406 ms first-partial p50 (930.895 ms,
  598.753 ms, and 600.406 ms) and a 915.032 ms final-event p50. Its partial
  text was unstable and included unrelated words, so this setting was not
  adopted. This three-run synthetic probe does not validate real-speaker
  quality.
  These synthetic probes do not establish real-speaker quality. CUDA inference
  also remains unavailable because `cublas64_12.dll` is missing.
- Validate the physical microphone, shipped local ASR, and physical HUD on supported Windows hardware.
- Obtain and configure the production code-signing identity, rebuild the
  candidate with
  `pnpm package:win:release`, and verify the signed installer and executable's
  publisher identity.
- Complete Presentation Workspace research with 10–20 real preparation
  sessions. Review the expanded 33-deck corpus's embedded media and provenance,
  investigate the full 33-deck preview mismatches and the app-preview
  text/layout mismatches, and resolve the Office
  visual `needs_review` results before treating edited PPTX export as
  production-ready. Repeat the guarded PowerPoint-open check against the exact
  release candidate; local corpus results are not release-build evidence.
  A11y-CUA supplies 16 human runs of a guided two-slide introduction task and
  96 more task traces for six specific PowerPoint operations. A limited
  aggregate of the 16 creation-task PowerPoint event logs showed keyboard and
  hotkey interaction in blind-and-low-vision sessions, and keyboard plus mouse
  movement/drag interaction in sighted sessions. These task-scoped traces add
  accessibility and operation-pattern evidence, but do not close the broader
  preparation-workflow or Presenter Copilot acceptance gate. Only event types
  and timestamps were analyzed in memory; no raw traces or media were saved.
  GUIDE's dataset card reports four tasks and three novice demonstrations per
  application, giving 12 each for PowerPoint and Google Slides (24 candidate
  presentation-editing sessions). The initial release has 50 full recordings
  and annotated segments for the remaining 70; the public card does not say
  whether all 24 presentation sessions are full recordings. The card declares
  CC BY 4.0, but downloading requires accepting a condition to share account
  contact information. We have not accepted it or accessed the files. GUIDE is
  not Presenter Copilot product-user acceptance.
  Pango's public card describes real Google Slides work sessions with screen
  video and timestamped interaction data, but its dataset files require
  provider contact, the public card states no reuse license, and the public
  product page lists Microsoft Office as future support. We have not contacted
  the provider or accessed the files; it is a possible interaction-pattern
  source only after terms and participant-data review, not an export-fidelity
  corpus. PPTC offers 279 simulated multi-turn tasks, but its templates need
  separate rights review and its simulations are not observed product
  sessions. SlideSpace reports eight recorded authoring sessions, but its
  publication does not provide the raw recordings. See the
  [corpus research notes](PRESENTATION_WORKSPACE/CORPUS.md).
  An exploratory evaluation of `@office-kit/pptx-preview@0.12.0` did not
  improve same-corpus median fidelity and failed on two Core-comparable decks;
  it is not an approved replacement. See the
  [fidelity evaluation](PRESENTATION_WORKSPACE/PPTX_FIDELITY.md).
  On the 24 comparable decks (386 slides) in the earlier 26-deck corpus, the
  integrated `@aiden0z/pptx-renderer@1.3.0` candidate improved on the prior
  in-app browser: median normalized RGB MAE fell from 3.0356% to 2.2403% and
  PSNR rose from 17.404 to 19.025 dB. The production preview now
  applies in-memory SmartArt image-relationship repair and narrowly normalizes
  exact backmost full-canvas `useBgFill` shapes only when their direct fill is
  absent or already `noFill`; paired corpus validation improved 14 slides with
  no regressions. The preview also handles bounded direct `a:duotone` and
  optional following `a:lum` effects for resolvable embedded PNG/JPEG media by
  creating preview-only in-memory raster aliases. On record `90000004`, the
  effect lane reduced deck median RGB MAE from 18.8637% to 14.3155%, while the
  changed-pixel rate moved from 96.5028% to 96.6150%; full-corpus medians were
  unchanged and visual fidelity remains a release blocker. These preview-only
  changes do not modify exported PPTX files. It runs in
  a hidden sandboxed Electron window and is the preferred research preview,
  with the old worker retained as a compatibility fallback. Visible text-style
  differences remain. One-host sampled profiling recorded an 880 MiB total
  Electron private-byte peak on an inert-padding fixture near the 50 MiB input
  cap; it does not model large-media expansion or set a general memory ceiling.
  Input responsiveness, timeout/cancel behavior near the cap, plus Office
  review, remain open gates. Details
  are in the [fidelity evaluation](PRESENTATION_WORKSPACE/PPTX_FIDELITY.md).
  A one-deck `@slideglance/core@0.4.2` Node-API probe showed a small median
  improvement, but used non-canvas text measurement; its browser worker failed
  during WASM initialization in the isolated harness. It is not an approved
  replacement either.
- Continue Workspace editing beyond single-run and uniform-style multi-run
  text replacement, direct text
  formatting in structurally simple text shapes of up to 128 paragraphs, horizontal paragraph alignment and
  bounded left indentation, signed first-line/hanging indentation, bounded line spacing, disc, hollow-circle, square, or dash bullet styles, no-bullet formatting, or Arabic-period automatic numbering across simple paragraphs, and before/after spacing, direct
  solid shape colors, simple text-box
  creation, plain speaker notes, basic object geometry, and simple picture
  crop/replacement. Remaining direct-edit work includes custom numbering schemes, picture bullets, arbitrary bullet glyphs, and custom bullet font/color/size styles, multi-shape bulk formatting, advanced shape formatting, advanced image treatment,
  additional object types, broader slide-layout
  selection/creation, and PDF
  export.
  Rehearsal and Challenge must stay bound to an immutable presentation
  revision.
- Evaluate decision suggestions on a licensing-safe, human-labeled set for
  accuracy, latency, abstention, and costly errors before using them beyond
  review-only proposals. OpenAI announced its GPT-6 Luna Decisions API limited
  preview in the [DevDay recap](https://openai.com/index/devday-2026-recap/),
  and now publishes the beta contract in the
  [Decisions guide](https://developers.openai.com/api/docs/guides/decisions).
  The native adapter uses GPT-6 Luna with the existing API-key credential;
  account access and model acceptance remain unverified. The documented
  OpenAI Responses API Fast and Ultrafast service tiers are distinct from that
  API. This project exposes both; Ultrafast is fixed to GPT-6 Astra and account
  rate limits apply. The current Ultrafast guide says GPT-6 Astra is broadly
  available at low rate limits and GPT-5.6 Sol has preview access; the Responses
  create reference still describes GPT-5.6 Sol as the supported Ultrafast model.
  This official-docs conflict leaves account-level Astra eligibility unverified,
  and no live OpenAI inference ran. See
  OpenAI's [Fast mode](https://developers.openai.com/api/docs/guides/fast-mode),
  [Ultrafast mode](https://developers.openai.com/api/docs/guides/ultrafast-mode),
  [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
  and the Responses [create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).
- The app now uses OpenRouter's documented versioned System One endpoint
  (`POST /api/v1/systemone`) with a regular OpenRouter API key. The separate
  alpha `/api/alpha/decisions` reference still lists a management-key
  requirement that conflicts with the Jev tutorial; the app does not use that
  endpoint or request management credentials. Run live Jev acceptance with an
  explicitly authorized account before release. Core maps 403 to a permission
  error and keeps provider response bodies private. See the
  [System One SDK guide](https://openrouter.ai/docs/guides/community/typesafe-sdk)
  and [alpha Decisions reference](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request).
- Ollama System One is implemented for fixed-loopback `nimble:9b`,
  `nimble:9b-q4_K_M`, `nimble:latest`, `tev1:4b`, `tev1:4b-q4_K_M`,
  `tev1:latest`, and `tev1:0.8b` model
  identifiers. It never launches Ollama, downloads a
  model, sends credentials, or falls back to a remote provider. It verifies the
  installed model digest before and after inference and records that digest in
  content-free run provenance. Adapter checks use synthetic responses only;
  real-model human-labeled accuracy and latency evaluation remains an open
  release gate. See the official [Nimble](https://ollama.com/library/nimble),
  [Tev1](https://ollama.com/library/tev1),
  [System One API](https://docs.ollama.com/api/systemone), and
  [List models API](https://docs.ollama.com/api/tags).
- Run live provider acceptance only with an explicitly authorized account and
  credential. No live OpenAI, OpenRouter, or Ollama inference was used in these
  local checks.
- Run Sign in with ChatGPT acceptance with an eligible account before release:
  verify first-time consent, returning sign-in, available model listing,
  one synthetic finite-choice inference, shared-limit/preview disclosures,
  refresh and sign-out. Automated OAuth/JWKS/Responses fixtures do not validate
  live account eligibility or service behavior.
- `pnpm benchmark:decision-local -- --model-id presenter-copilot-qwen3.8-4b`
  used LM Studio's loopback-only server
  and the already-installed `qwen3.8-4b-distill` model. All 10 synthetic
  requests returned schema-valid choices; 7 matched the hand-written labels
  (70%). The reproducible command reported a 1,101 ms median and 2,106 ms p95.
  It refuses a private-LAN endpoint before sending any examples. This is a
  small, self-authored smoke set, not representative quality evidence or a
  release pass. The installed 27B model was not loaded: its estimated 13.25 GiB
  total memory exceeded the 3.8 GiB of free system memory observed on this host. The temporary model
  load and loopback server were stopped after the run. No presentation text or
  provider credentials were used.
- The same benchmark command can exercise Ollama's Jev-compatible System One
  adapter directly: `pnpm benchmark:decision-local -- --provider-id
ollama_systemone --model-id tev1:0.8b`. It accepts only the project's
  supported tags, uses the fixed loopback URL, and verifies the installed model
  digest before and after inference. The command and endpoint guard are covered
  by local tests, but no Ollama service or supported model is installed on this
  validation host, so live Nimble/Tev1 quality and latency remain unverified.

The Windows package generated here is a local verification artifact. It was not
installed on a clean machine or published.

## ASR decoder diagnostics (2026-10-02 UTC)

The first-partial values in the following earlier diagnostics predate the
zero-onset fix documented below; the synthetic fixture begins speech at 0 ms,
which the prior benchmark treated as missing and shifted by 100 ms. Use the
corrected report in the following section for current latency status.

- Re-ran the corrected absolute-time Core-event benchmark with partial
  scheduling disabled only inside the diagnostic process. Final-event p50 was
  924.387 ms after speech end, slightly slower than the unchanged baseline's
  919.682 ms. Optional partial decoding is not the cause of the final-latency
  miss.
- A separate diagnostic forced final decoding to beam size 1 while leaving
  partial decoding unchanged. The checked-in speech fixture still matched all
  four required phrases; final-event p50 improved to 895.934 ms, but
  first-partial p50 remained 921.139 ms against the 500 ms target. This
  diagnostic was not promoted: one synthetic recording cannot establish
  real-speech decoder quality, and first-partial latency still fails.
- Prefix probes explain why emitting the first completed decode is unsafe:
  120 ms of this fixture produced `Hope.`, 300 ms produced `post. //`, and
  600 ms produced `Post 3`; only one of two 800 ms attempts contained the
  expected `three year` phrase. Live Assist uses the latest partial as input
  to its question, so relaxing the ASR generation check would expose these
  unstable snippets to the decision path. The check stays in place.
- Reports are
  `.local/asr-benchmark-no-partials-absolute-20261002.json` and
  `.local/asr-benchmark-beam1-absolute-20261002.json`. The installed runtime
  continues to use beam size 5 for final decoding.

## ASR zero-onset timing correction (2026-10-02 UTC)

When VAD confirmed speech beginning at session time 0 ms, truthiness fallbacks
treated that valid timestamp as missing and substituted the 100 ms frame where
the 120 ms confirmation completed. This shifted the captured utterance start
and caused the benchmark to subtract 100 ms from first-partial latency. The
service and benchmark now distinguish `None` from a zero timestamp. Regression
tests cover starts at 0 ms and after leading silence, and the callback path
confirms the durable final preserves its 0 ms start.

With correct onset accounting, the default CPU/int8 run delivered all three
partial events at p50 939.602 ms / p95 947.088 ms; final-event p50 was 926.203
ms from speech end and 326.203 ms after VAD completion. Both configured targets
remain unmet. The 250 ms initial / 300 ms repeat schedule experiment produced
one timely partial in three runs and delayed final events, so it was reverted.
No model or decoder settings changed. The report is
`.local/asr-baseline-onset-fixed-20261002.json`; real microphone quality and
latency still need physical-device validation.

## Preview-fidelity follow-up (2026-10-02 UTC)

- Added bounded preview-only support for simple ellipse-clipped pictures. The
  32-slide target run for record `6447723` had no unstable PowerPoint captures;
  slide 3 changed-pixel rate fell from 39.6456% to 35.0411%, normalized RGB
  MAE from 11.7892% to 9.8695%, and PSNR rose from 10.468 to 11.167 dB.
- Full comparison completed on 31 decks / 613 slides, with two external
  relationship skips, zero failures, and 21 unstable captures. Six ellipses
  were promoted. Among 592 slides stable in both runs, four improved, two had
  small regressions (0.1202 and 0.4263 percentage points MAE), and 586 were
  unchanged. Stable differences remain on all 613 comparable slides, so the
  Workspace preview is still not fidelity-accepted.
- The broader geometry experiment caused a large regression on a cropped
  `round2DiagRect` and was narrowed to simple ellipses. The final rule leaves
  other presets and custom geometry unchanged, and validates lazy image media
  under per-image and aggregate byte limits.
- A focused `theme-background-only` run exercised the previously rejected
  comparison mode on all 24 slides of record `90000008`, with no unstable
  captures. A fresh read-only PowerPoint render of slide 5 matched the prior
  reference PNG SHA-256, but its top-left background pixel is `(34, 34, 34)`;
  the preview pixel is `(4, 4, 4)`. The mismatch is reproducible, while its
  cause is not isolated. No guessed brightness adjustment has been accepted,
  and the theme background remains a fidelity blocker. See the detailed
  [validation record](PRESENTATION_WORKSPACE/VALIDATION.md#focused-theme-background-follow-up-2026-10-02)
  and [fidelity notes](PRESENTATION_WORKSPACE/PPTX_FIDELITY.md).
- The earlier ellipse-only verification snapshot (before the later provider
  authentication work) passed `pnpm check` (98 desktop and 414 Core tests),
  all 17 `pnpm test:ui` flows, the corpus overflow case, E2E-01 through E2E-08,
  `pnpm package:win`, and `pnpm test:packaged`. Its unsigned installer SHA-256 was
  `7303BCE3C67BF914739233AD0C49E04FC55667F7259879BDA73C1AA799FE7275` and
  Authenticode is `NotSigned`. The package has not been installed on a clean
  machine or published; see the latest verification refresh above for the
  current package and test counts.
- Evidence: `.local/preview-compare-33-ellipse-only-20261002.json`. Hosted CI,
  clean-machine install, physical microphone/HUD validation, human-labeled
  Nimble/Tev1 decision quality and latency, and a signed release remain open.

## Reviewed selection actions and canvas shortcuts (2026-10-03)

The canvas now offers Duplicate selection and Delete selection for 1–20 supported
native objects. Ctrl+D opens duplication review; Delete and Backspace open deletion
review. Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y traverse presentation history when focus is
on the canvas. Existing copy/paste shortcuts remain available. Shortcuts respect
handled events, editable text fields and voice-workflow ownership. These actions
use native preview, explicit acknowledgment, exact reviewed-byte save, one-revision
undo/redo, retrieval refresh and discard through the existing transaction lane.
Supported shapes, pictures, charts and tables keep their existing dependency guards.

Dependencies considered before editing: batch actions must target the same immutable
revision and expected geometry; sequential staging must publish nothing if a later
object fails. Native chart/workbook relationships and table geometry continue through
the existing writers. The transaction save response now includes created_object_id,
already allowed in audit metadata, so all saved copies can stay selected. Discard
previously lost selection while restoring the shared preview cleared the inventory;
selection now survives that refresh only for the exact document, slide, revision and
verified native object IDs. No new public IPC, provider schema or database migration.

Validation: seven new Core tests cover shapes, charts and tables, new identities,
exact reviewed-byte publication, whole-selection deletion, undo/redo, discard and
late-operation failure with unchanged head/history and cleaned staging files.
All 828 collected Core tests passed in four fresh-process serial batches
(168 + 232 + 218 + 210), without skips/omissions; all 134 desktop tests passed.
Receipts: `.local/selection-actions-core-focused.log`,
`.local/selection-actions-core-batches/manifest.json` and
`.local/selection-actions-desktop-final.log`. Final lint, formatting, both
TypeScript projects and mypy (147 source files) passed. Final receipts:
`.local/selection-actions-lint-verified.log`,
`.local/selection-actions-format-verified.log` and
`.local/selection-actions-types-final.log`.

The complete Electron sweep passed 73 workflows. The new workflow exercises
keyboard duplication, reviewed discard with selection retention, acknowledged
save with both copies selected, Backspace/Delete review and discard, batch deletion
and Ctrl+Z/Ctrl+Shift+Z/Ctrl+Y history traversal. It counts actual selectable objects
rather than the eight resize handles. Early runs corrected a slide-navigation
assumption, the existing Discard preview label and that handle-counting assertion;
they also exposed and verified the selection-restoration repair. Evidence:
`.local/selection-actions-ui-verified.log` and the inspected
`.local/ui-validation/workspace-selection-duplicate-review.png` and
`workspace-selection-delete-review.png`.

PowerPoint opened ordinary native shape/chart/table fixtures after duplicating two
objects and deleting those copies. It verified shape counts, preserved sizes and
independent in-memory native edits; the three file hashes per fixture stayed
unchanged. All six exported PNGs were inspected. Repeated duplication of one native
chart/table intentionally overlaps copies in these dependency tests; this is native
editability proof, not broad pixel-fidelity acceptance. Evidence:
`.local/selection-actions-office/result.json` and `check-final.log`.
The final 308 source/test hashes are recorded in
`.local/selection-actions-source-freeze.json` and verified in
`.local/selection-actions-source-freeze-check.json`. Core sources/tests remained
unchanged after the full Core run; final renderer checks include the discard fix.
Diff whitespace checks passed. All acceptance processes launched here terminated.

Next priorities: substantial remaining GUI workflows, native grouping/ungrouping,
richer chart/table authoring, then broader corpus fidelity and live integration.
Live fast-decision calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted debt. Dirty work
is preserved; no account/model calls, downloads, commits, pushes, packaging or releases
occurred. The production-readiness goal remains active.

## 2026-10-04 continuation - reviewed native grouping and ungrouping

The Presentation Workspace now groups 2–20 eligible native objects through review,
acknowledgment and exact reviewed-byte save. Group selection and Ungroup selection
are available in Object actions, with Ctrl+G and Ctrl+Shift+G on the focused canvas.
Saved groups, moved/resized groups and promoted children remain selected. Supported
native groups can move and resize through the existing reviewed geometry workflow.
Nested groups are supported within a bounded eight-level hierarchy. Discard,
retrieval refresh and whole-revision undo/redo use the existing transaction lane.

Dependencies considered before editing: grouping changes native coordinate
hierarchies, layer order and retrieval traversal, while child identities and picture,
chart and workbook relationships must survive. Selected objects retain source order
inside the new group at the frontmost selected layer. Ungrouping maps child geometry
through parent offsets and scales; nested child coordinates remain coherent. Native
group moves/resizes edit only the outer frame. Retrieval now traverses nested groups
for text, tables and chart summaries. New capability flags and selected-object save
metadata are additive; no database migration or new public IPC endpoint was needed.

Eligible objects include supported shapes, embedded PNG/JPEG pictures and unlocked
native charts. App-authored charts now allow grouping; imported grouping locks remain
respected. Native PowerPoint directly refused grouping a locked imported chart,
confirming that restriction. Tables and placeholders follow
[PowerPoint grouping limits](https://support.microsoft.com/en-gb/office/graphics-visuals/group-or-ungroup-shapes-pictures-or-other-objects).
Rotated/flipped or malformed groups, inherited fills/effects, hidden/click actions,
locks, connector/animation dependencies and children outside group coordinate bounds
remain read-only with explicit reasons. Child geometry edits use the containing group.
Native group copy, duplicate, delete and layer actions, plus Copilot grouping
proposals, remain open; this slice provides manual reviewed grouping and geometry.

Validation: 23 new Core tests cover PNG/JPEG pictures, native charts, nested groups,
layer/identity preservation, retrieval, nonuniform scaling, promoted geometry,
undo/redo, stale targets, discard and atomic late failure. All 851 collected Core
tests passed in four fresh-process serial batches (249 + 186 + 239 + 177), without
skips or omissions. All 134 desktop tests and all 74 Electron workflows passed.
The new GUI workflow covers keyboard/toolbar grouping, acknowledgment, discard,
save, selected-group resizing, ungrouping and history traversal. Both new review
screenshots were inspected. Lint, formatting, both TypeScript projects and mypy
(149 source files) passed on the final source. Receipts:
`.local/groups/core-focused-final.log`, `.local/groups/core-batches/manifest.json`,
`.local/groups/desktop.log`, `.local/groups/ui-final.log`,
`.local/groups/lint-final.log`, `.local/groups/format-final.log` and
`.local/groups/types-final.log`.

Native PowerPoint opened four mixed text/picture/chart fixtures (PNG/JPEG, flat and
nested) before and after reviewed ungrouping following translation and nonuniform
resizing. Native chart values/categories and independent text/series edits remained
available; other slides and notes were preserved, and all file hashes stayed
unchanged. All eight exported PNGs were inspected. Each before/after pair had zero
mean pixel difference at 1280×960. This is bounded fixture fidelity acceptance,
not broad corpus or experimental-renderer acceptance. Evidence:
`.local/groups-office/result.json` and `.local/groups-office/check.log`.
The final 311 source/test hashes in `.local/groups/source-freeze.json` were verified
unchanged in `.local/groups/source-freeze-check.json`. Diff whitespace checks passed,
and all acceptance processes launched here terminated.

Next priorities: remaining native group actions and substantial authoring/GUI gaps,
then broader corpus fidelity and live integration. Fast-decision calibration/latency
and actual Sign in with ChatGPT acceptance remain open. Signing and clean Windows
validation remain accepted debt. The dirty worktree is preserved; no account/model
calls, downloads, commits, pushes, packaging or releases occurred. The
production-readiness goal remains active.

## 2026-10-04 continuation - complete native group actions

Eligible native groups now support copy/paste, duplication, complete deletion and
all four layer actions in the Presentation Workspace. The canvas uses the existing
Ctrl+C/Ctrl+V, Ctrl+D and Delete/Backspace review workflows; the Objects inspector
also exposes duplication/deletion and layering for groups. Saved copies select the
new container. Copy/paste accepts an immutable source revision and preserves group
geometry and relative child coordinates across slides or presentations in the same
project. Preview, acknowledgment, exact reviewed-byte save, discard, retrieval
refresh and whole-revision undo/redo remain in the existing transaction lane.

Dependencies considered before editing: a group container has slide-wide IDs for
all descendants, and its charts depend on native chart/workbook package graphs.
The paste writer now assigns every nested object a fresh native ID, counts all
children against resource limits, remaps picture dependencies and clones each
nested chart graph independently of the source. Canonical copied-subtree XML,
child identities, geometry, content and semantic style fields are validated after
writing. Fingerprints may change with namespace context, native offsets and
relationship remapping; they are recomputed rather than mistaken for content loss.
Group duplication reuses this writer. Complete deletion validates removal of the
container and every child ID while preserving package parts that may be shared.
Layer changes move the whole container and validate unchanged object contents.
The renderer inventory validator accepts eligible group deletion capabilities.
No database migration, provider schema or public IPC endpoint was added.

Unsupported groups keep the existing native dependency restrictions. Groups with
unknown or alternate-content child nodes are now explicitly read-only instead of
silently ignoring those children. Direct child edits still use the containing group
or reviewed ungrouping. Copilot proposals for grouping/ungrouping are now implemented and locally verified
(2026-10-08; see current status above).

Validation: 21 new group-action tests cover PNG/JPEG pictures, flat/nested groups,
same-slide duplication, cross-slide and same-project cross-document paste,
independent chart/workbook parts, complete subtree deletion, layer boundaries,
undo/redo, discard, stale targets, resource limits and atomic late failure. One new
unsupported-child regression test extends grouping coverage. All 71 focused checks
passed in `.local/group-actions-focused-final3.log`. All 873 collected Core tests
passed in four fresh-process serial batches (185 + 301 + 172 + 215), without skips
or omissions; evidence is `.local/group-actions/core-batches/manifest.json`.
All 134 desktop tests passed in `.local/group-actions/desktop.log`.

The complete Electron sweep passed 75 workflows with no renderer errors. The new
workflow covers reviewed group duplication and clipboard paste, selected copies,
deletion discard/save, complete subtree deletion, layer order and whole-action undo,
then continues the earlier resize/ungroup workflow. A first run corrected the new
test's timing: wait for the restored canvas after deletion before counting objects.
Final evidence: `.local/group-actions-ui-final.log`, `.local/ui-validation/result.json`
and four inspected `workspace-group-*-review.png` / `workspace-group-layer-back.png`
screenshots. Final lint, formatting, both TypeScript projects and mypy (149 source
files) passed; receipts are `.local/group-actions/lint.log`, `format.log`, `types.log`
and the final GUI script `ui-script-lint.log` / `ui-script-format.log`.

Native PowerPoint opened four mixed text/picture/chart group fixtures (PNG/JPEG,
flat/nested) before duplication, after duplication and after deleting the copy.
Copied chart values could be edited in memory without changing the original chart.
Other slides and notes remained intact; all file hashes stayed unchanged. All 12
exported PNGs were inspected. Deleting each copy restored a zero mean pixel
difference at 1280×960. Copy views intentionally overlap and show the independently
edited chart; these are native dependency/editability checks, not layout quality
or broad corpus/experimental-renderer fidelity acceptance. Evidence:
`.local/group-actions-office/result.json` and `.local/group-actions-office.log`.
All final 312 source/test hashes in `.local/group-actions/source-freeze.json` were
verified in `source-freeze-check.json`. All acceptance processes launched here
terminated; diff whitespace checks passed.

Next priorities: substantial remaining authoring/GUI workflows, including native
theme/master-layout discovery and application, then broader corpus fidelity and
live integration. Fast-decision calibration/latency and actual Sign in with ChatGPT
acceptance remain open. Signing and clean Windows validation remain accepted debt.
The dirty worktree is preserved; no account/model calls, downloads, commits, pushes,
packaging or releases occurred. The production-readiness goal remains active.

## 2026-10-04 continuation - reviewed appendix creation

Create appendix is now available in Slide actions & layout. Choose 1–18 existing
detail slides, move them out of the main story or copy them while keeping originals,
and add an editable Appendix divider with notes and Classic/Midnight/Paper styling.
Main slides and selected detail slides retain their original relative order. Moving
requires at least one main slide; copying can include all slides. The resulting deck
must stay within the existing 5,000-slide limit and twenty-operation transaction bound.

The user reviews the proposed order, divider and each detail slide before the review
checkbox and save can activate. Changes to choices/content invalidate approval and
require another preview. Saving publishes exact reviewed bytes as one revision,
selects the divider and refreshes retrieval; discard restores the baseline preview,
and undo/redo traverse the entire appendix as one edit. The dialog uses explicit
source slide numbers and a sequential native preview for content review.

Dependencies considered before editing: slide ordering uses immutable slide IDs,
while divider/copy IDs are generated during staging. Existing earlier-step creation
references allow native authored creation, optional native slide duplication and one
final permutation to compose safely in the same transaction. Native slide writers
preserve notes, picture/chart/workbook relationships and existing objects; no package
round-trip through python-pptx is introduced. Copy mode assigns new slide identities;
move mode preserves identities. A pure renderer planner rejects duplicate/unknown
selection, stale order, empty main story and capacity overflow. Proposed native
inventory is checked against expected main/appendix order before rendering. All
existing Core validators, review ownership, exact-byte save, history and audit paths
remain authoritative. No production Core writer, public IPC, provider schema or
database migration was changed.

Validation: nine new desktop planner tests cover noncontiguous/source-order selection,
copy references, invalid selections, empty-main rejection, all-slide copying, the
20-operation bound and capacity/stale inventory checks. All 143 desktop tests passed.
Ten new Core composition tests cover all three divider templates in move/copy modes,
original native parts/objects/notes, independent chart parts, exact reviewed-byte save,
order and undo/redo; discard, missing targets, stale heads and late-reference failures
publish no partial divider or copies. All 30 focused Core checks passed in
`.local/appendix-core-focused-final.log`. All 883 collected Core tests passed without
skips/omissions in four fresh-process serial batches (225 + 185 + 301 + 172), recorded
in `.local/appendix/core-batches/manifest.json`. Final lint, formatting, both TypeScript
projects and mypy (149 source files) passed; receipts are `.local/appendix/lint.log`,
`format.log`, `types.log` and `desktop.log`. The final GUI-script adjustment passed
`ui-script-lint.log` / `ui-script-format.log`.

GUI acceptance: all 76 checks passed with no renderer exceptions in real Electron
and local Core using a disposable profile. Appendix move/copy previews every detail
and divider, gates acknowledgment/save, invalidates changed drafts, discards, saves,
selects the divider, reindexes and undoes the complete revision. Screenshot review
caught horizontal preview overflow; the existing bounded figure styles now constrain
the image, and a GUI assertion verifies both dialog and preview width. Final move/copy
screenshots were inspected. Receipt: `.local/appendix-ui-layout-retry.log` and
`.local/ui-validation/result.json`. The initial test navigation assumption was fixed
by explicitly selecting slide 1 after undo. A later sweep timed out opening History
after redo before reaching appendix checks; the unchanged retry passed that step and
the full sweep. That transient is retained in `.local/appendix-ui-layout-final.log`.
Desktop lint, formatting, both TypeScript projects and all 143 desktop tests passed
again after the layout correction in `.local/appendix/layout-{lint,format,types,desktop}.log`.

Native PowerPoint opened all six move/copy × divider-template fixtures. Native order,
divider text, notes and charts remained valid; copied chart values could be edited
without changing the retained original. Detail-slide exports had zero mean pixel
difference from their source at 1280×960, and file hashes stayed unchanged. All 18
native exports were inspected in three visual QA sheets. This is bounded fixture
acceptance, not broad corpus, experimental-renderer or human design acceptance.
Evidence: `.local/appendix-office/result.json`, `.local/appendix-office.log` and
`.local/appendix-office/contact-{classic,midnight,paper}.png`.

The final source/test freeze is `.local/appendix/source-freeze.json` (316 files).
All hashes were verified in `.local/appendix/source-freeze-check.json`; the final
layout correction changed only the renderer preview wrapper and GUI assertion, so
Core and native PowerPoint evidence remains applicable. All owned test/Office
processes reached terminal states, and `git diff --check` passed.
Native master/layout discovery and application were already implemented; the previous
handoff's suggestion to implement them next was incorrect. Remaining authoring gaps
include structured diagrams, source/evidence footnotes, existing-placeholder remapping
and layout thumbnail comparison, followed by broader fidelity/integration acceptance.
Automatic semantic appendix labels and model-assisted appendix selection are not
proven by this manual flow. Fast-decision calibration/latency and actual Sign in with
ChatGPT acceptance remain open. Signing and clean Windows validation remain accepted
debt. Dirty work is preserved; no account/model calls, downloads, commits, pushes,
packaging or releases occurred. The production-readiness goal remains active.

## 2026-10-04 continuation - reviewed native evidence footnotes

Claim and evidence review now offers Add evidence footnotes for an unchanged claim
reviewed on the current revision with current source excerpts. Choose 1–4 sources,
review their excerpt text and source unit/relation, edit citation labels, choose
light/dark text, and set top/bottom or explicit vertical placement. Each numbered
citation is an editable native text box. The proposed slide must render, and the
user must acknowledge labels and placement before saving exact reviewed bytes as
one revision. Changes invalidate approval; discard restores the current slide.
Save refreshes retrieval. Undo/redo traverses the entire citation block. The new
revision requires fresh claim review; citations are static review snapshots and do
not automatically update when sources or deck contents change.

Dependencies considered before editing: claim records already contain reviewed
source names, ordinals, excerpt hashes and relations. The modal rechecks claim
revision, object span, quote, excerpt identity/hash, relation and source location
before staging. Native text-box creation now accepts optional bounded geometry and
font size/color/emphasis/alignment through existing validators, while existing
callers retain centered placement and 18-point defaults. The writer verifies the
new object's text/style/geometry and identity and preserves all prior objects,
notes, other slides and package parts. One transaction owns the preview and save;
no database migration, provider call or new public method was introduced. Color
and placement are user-reviewed; no automated collision or font-fit claim is made.

Validation: eight new desktop planner checks cover source locations/relations,
numbered order, four-source geometry, stale/missing/duplicate evidence, invalid
labels/identity/dimensions and custom placement/bounds. All 151 desktop tests passed.
Ten new Core checks cover one/four citations with light/dark font colors, native
style/geometry, unchanged package parts, exact preview-byte save, whole-revision
undo/redo and invalid input/late-stage rejection without partial publication.
All 893 collected Core tests passed in four fresh-process serial batches
(145 + 229 + 222 + 297), without skips or omissions. Final formatting, lint, both
TypeScript projects and mypy (149 files) passed. Receipts are in `.local/footnotes/`:
`core-batches/manifest.json`, `core-full.log`, `desktop-final.log`, `format-final.log`,
`lint-final.log` and `types-final.log`.

GUI acceptance: all 77 checks passed in real Electron and local Core with a
disposable profile and no renderer exceptions. Footnotes preview current reviewed
sources, invalidate changed labels, discard, save native editable citations, refresh
retrieval, require fresh claim review on the new revision and undo the complete
block. The dialog overflow assertion passed and its final screenshot was inspected.
Receipt: `.local/footnotes/gui-final.log`, `.local/ui-validation/result.json` and
`.local/ui-validation/workspace-evidence-footnotes-review.png`. The initial new test
failed because selecting the original deck did not open its preview; it now opens
that deck and waits for the current revision before history restoration. The earlier
failed receipt is retained in `.local/footnotes/gui.log`.

PowerPoint opened four Classic/Midnight × upper/lower-placement fixtures. All sixteen
native citations retained exact text, ten-point fonts and in-bounds positions; native
text bounds fit their shapes, notes stayed intact and file hashes did not change.
All four exported PNGs were visually inspected. Initial top placement intersected
an authored title; explicit vertical placement was added to the dialog, and the
upper fixtures were verified at two inches below the slide top. This is fixture
acceptance, not arbitrary-label collision/fit, broad corpus or renderer equivalence
acceptance. Evidence: `.local/footnotes/office-final/result.json`, `office-final.log`
and `office-final/{classic,midnight}-{top,bottom}.png`.

Source/test freeze: `.local/footnotes/source-freeze.json` (320 files), verified in
`.local/footnotes/source-freeze-check.json`. All owned test and Office processes
reached terminal states; `git diff --check` passed. This slice
modified only four previously frozen files and added four new files; the other
312 frozen source/test files stayed unchanged. Dirty work is preserved on
`codex/production-readiness` at base `657b876739ff7a1cc5709a7e28e92ec2551b337e`.
No external account/model calls, downloads, commits, pushes, packaging or releases occurred.
Remaining substantial authoring gaps include structured diagrams, existing-placeholder
remapping and layout thumbnail comparison; broader fidelity/integration, fast-decision
calibration/latency and live Sign in with ChatGPT acceptance remain open. Signing and
clean Windows validation remain accepted debt. The full goal remains active.

## 2026-10-04 continuation - native layout thumbnail comparison

Browse native layouts now shows a verified current-revision baseline and a paged
gallery of four alternatives applied to the current slide's content. Previous/Next
covers every other native layout in catalog order, including unused layouts and
layouts used elsewhere in the deck. Select a thumbnail, then generate and approve
a fresh exact-byte preview before saving. Comparing or changing candidates invalidates
prior approval. Candidate plans are rejected after their images are captured; comparing
alone publishes no revision. The baseline stays fixed across pages. Discard restores
the original slide; a final reviewed save retains existing retrieval refresh and undo.
Native-layout insertion remains in its existing separate review flow.

Dependencies considered before editing: the catalog identifies the current layout by
its used-by slide list, and every candidate is scoped to the immutable document,
revision and slide. A no-op application of the current layout supplies the baseline
through the existing hash-verified package reader. One staged plan at a time supplies
candidate images, verifies the slide identity and is discarded before another is
prepared. The shared renderer stays owned by the modal until restoration. Only four
candidate images are retained for a page, with URL cleanup on replacement/close.
Selecting an image does not authorize its temporary plan. Final save requires the
ordinary new plan, PNG load and acknowledgment. No production Core code, IPC method,
provider schema or database migration changed. The planner rejects duplicate IDs,
ambiguous current layouts, oversized catalogs and invalid pages. The baseline image
height was reduced after screenshot review so the candidate gallery is easier to see.

Validation: six new desktop planner checks cover complete stable catalog order,
other-slide/unused choices, bounded paging, a single-layout deck, invalid pages and
ambiguous/duplicate identities. All 157 desktop tests passed. Two new Core checks
stream the byte-identical baseline, stage/read/reject all ten alternatives without
publishing, save only a freshly reviewed final candidate as revision 2, undo it and
reject a stale comparison after another revision wins. All 53 focused native-layout,
transaction and comparison Core tests passed. Receipts: `.local/layout-comparison/`
`core-focused.log`, `desktop-final.log`, `format.log`, `lint.log`, `types.log`, and
final desktop `format-final.log`, `lint-final.log`, `types-final.log`. The previous
893-test full Core result remains applicable to unchanged production Core and prior
Core test files; this is not a fresh full 895-test suite claim.

GUI acceptance: the final full Electron/local Core sweep passed all 78 checks
with no renderer exceptions using a disposable profile. Tests cover verified baseline
rendering, four-candidate paging, stable baseline URL, thumbnail selection without save
approval, comparison invalidation, loaded thumbnail images, no dialog overflow, discard,
fresh final review/save and whole-revision undo. Both the baseline/comparison and full
four-thumbnail screenshots were inspected after reducing baseline height. Receipts:
`.local/layout-comparison/gui-final.log`, `.local/ui-validation/result.json`,
`.local/ui-validation/workspace-native-layout-comparisons.png` and
`.local/ui-validation/workspace-native-layout-thumbnail-gallery.png`. The first full
sweep also passed before the baseline-height adjustment in `gui.log`.

Native PowerPoint opened and exported the baseline and all ten candidate packages;
text, notes and slide order survived, file hashes and the authoritative head remained
unchanged. All eleven exports were inspected in three contact sheets. The exports
showed real inherited title position/font/orientation differences. Vertical Title and
Text wraps/clips the existing title in its inherited narrow vertical region; layout
comparison does not resolve that remapping/fit gap. No renderer equivalence, automatic
placeholder remapping or broad corpus acceptance is claimed. Evidence:
`.local/layout-comparison/office/result.json`, `office.log` and
`office/contact-{1,2,3}.png`.

Source/test freeze: `.local/layout-comparison/source-freeze.json` (323 files),
verified in `.local/layout-comparison/source-freeze-check.json`. All owned test/Office
processes reached terminal states and `git diff --check` passed.
Three existing source/test files were modified and three added; the other 317 files
from the previous freeze stayed unchanged, including all production Core files.
Dirty work is preserved on `codex/production-readiness` at base
`657b876739ff7a1cc5709a7e28e92ec2551b337e`. No external account/model calls, downloads,
commits, pushes, packaging or releases occurred. Next substantial authoring work
includes structured diagrams and existing-placeholder remapping, with the observed
native vertical-title fit issue as concrete fidelity evidence. Broader fidelity and
integration, fast-decision calibration/latency and live Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted debt. Goal active.

## 2026-10-04 continuation - reviewed existing-placeholder remapping

Browse native layouts now offers explicit assignments from eligible existing text
placeholders to the chosen layout's supported text slots. Assignments apply the native
placeholder identity, position and size while preserving each existing object identity
and complete rich-text XML. A fresh preview and acknowledgment authorize exact reviewed
bytes. Changing any assignment invalidates approval. Layout comparison thumbnails show
layout changes alone; final preview includes the assignments. Whole-revision undo/redo
retains the existing history and retrieval-refresh workflow.

Dependencies reasoned through before edits: applying a native layout previously changed
only the slide relationship. Optional `placeholder_mapping` now extends that existing
operation; no new IPC method, provider schema or migration was added. Catalog discovery
accepts an optional verified slide identity and returns eligible source placeholders.
The writer changes only selected placeholder metadata/transforms and the layout
relationship when necessary. Mapped shapes retain IDs, names, styles and full text XML;
unmapped objects, other slides, notes, media and relationships remain preserved.
Native slot transforms must be supported and in bounds. One-to-one object/slot assignment
and distinct final placeholder indices are enforced before publication. Animated or
connector-referenced source placeholders and unsupported 3D/grouped shapes are excluded.
Failed later operations leave the authoritative head unchanged. Existing layout-only
callers keep their previous behavior. Same-layout assignments work and repeated identical
assignments become no-ops.

Validation: eleven new Core cases cover three supported layouts, rich runs, object and
package preservation, unchanged slides/notes/pictures, reviewed hashes, no-ops, atomic
undo/redo, duplicate object/slot assignments, occupied unmapped indices, unknown targets,
empty mappings, late staged failures and exclusion of animation targets. A fresh complete
Core run passed all 906 collected tests in four serial batches (223/235/208/240), with
no omissions or skipped acceptance substituted. All 157 desktop tests passed; formatting,
lint, TypeScript and mypy (150 files) passed. Receipts: `.local/placeholder-remapping/`
`core-batches/manifest.json`, `core-all.log`, `desktop.log`, `format-final.log`,
`lint-final.log` and `types-final.log`.

GUI acceptance: the corrected full Electron/local Core sweep passed all 79 checks
with no renderer exceptions using a disposable profile. The remapping flow selects a
native title slot, previews and acknowledges it, changes the assignment to invalidate
approval, generates a fresh review, saves and undoes the complete revision. Existing
layout comparison, insertion, tables, charts, evidence and project flows also passed.
The review screenshot was inspected and copied to a stable receipt. The initial sweep
stopped because the test queried the reopened asynchronous catalog before it loaded;
adding a catalog-ready wait corrected the test without changing application behavior.
Receipts: `.local/placeholder-remapping/gui-final.log`, `gui-result.json`,
`placeholder-remap-review.png`; the initial failure is retained in `gui.log`.

Native PowerPoint opened and exported three before/after fixtures: Title and Content,
Comparison and Title Slide. COM checks verified rich-text bold/color, native shape IDs,
assigned geometry and preserved notes. Every unchanged second-slide export was
pixel-identical, input/output files remained unchanged by read-only Office opening, and
undo restored the original package bytes. Six first-slide exports were inspected in
`office/contact.png`; Comparison wraps body content into its narrower native content
slot, while Title Slide inherits subtitle styling and moves the title/body. These are
expected theme/layout changes. Receipts: `.local/placeholder-remapping/office-final.log`,
`office/result.json`, and `office/{0,1,2}/{before,after}.png`.

Scope remains explicit existing text placeholders with supported native slots. Freeform
text is not converted, unsupported/dependency-bound placeholders are excluded, and no
automatic fitting, collision avoidance, broad corpus fidelity or renderer equivalence is
claimed. Unmapped shapes keep existing XML but layout inheritance can alter their visible
position or formatting. Users must review wrapping and other content before saving.

Source/test freeze: `.local/placeholder-remapping/source-freeze.json` (325 files),
verified after all checks in `source-freeze-check.json`. All owned test/Office
processes reached terminal states; `git diff --check` passed.
Four prior files were modified and two added; all other 319 prior source/test files were
preserved. Dirty work remains on `codex/production-readiness` at base
`657b876739ff7a1cc5709a7e28e92ec2551b337e`. Next work includes structured diagrams,
broader fidelity/integration acceptance, fast-decision calibration/latency and live
Sign in with ChatGPT acceptance. Signing and clean Windows validation remain accepted
technical debt. Goal active.

## 2026-10-04 continuation - reviewed structured native diagrams

Native diagrams now creates and edits process, hierarchy and cycle diagrams on the
current slide using native grouped PowerPoint shapes and attached arrows. The dialog
supports 2–8 labeled nodes, hierarchy parents from earlier nodes (at most four levels),
three palettes, placement in inches, adding/removing nodes and converting structures.
It reloads existing supported diagrams and previews whole-diagram deletion. Every
change requires a fresh full-slide image and acknowledgment before exact reviewed bytes
save as one revision. Save refreshes retrieval; discard restores the authoritative
preview, and whole-revision undo/redo retains the ordinary history behavior.

Dependencies reasoned through before edits: ordinary grouping/deletion rejects attached
connectors, so diagrams use their own verified semantic writer without weakening those
rules. A diagram's native group description records its bounded structure and native
identity map. Discovery regenerates and compares the complete group XML before offering
an edit. Retained node identities and retained connections keep their OOXML IDs across
regeneration; new nodes/connections get unique IDs. Manual native changes are read-only,
and outside animation/connector references block regeneration/deletion. The writer
changes only the selected slide XML, leaves package entries/relationships/media/notes
intact and validates the entire resulting package. Late failures publish nothing.
Same-data edits become no-ops. Four IPC methods (list/create/replace/delete diagrams),
the desktop allowlists and shared capability examples were added; create/replace/delete
use the existing transaction/review pipeline. No database migration, provider schema,
renderer compatibility rule or generic group eligibility rule changed.

Validation: nineteen new Core cases cover small/eight-node processes and cycles, a branched
hierarchy, native connections, reviewed hashes, preserved original objects/other slides/
notes, complete undo/redo, retained identities across structural changes, stale
fingerprints, manual changes, external dependencies, malformed/duplicate node data,
invalid parents/palettes/text/geometry, late staged failures, whole-diagram deletion and
undo. Twenty-six focused diagram/protocol checks passed. After final routing changes,
a fresh complete Core run passed all 925 collected tests in four serial batches
(249/206/281/189), without omissions or skips. All 157 desktop tests and formatting,
lint, TypeScript and mypy (151 files) passed. Receipts: `.local/diagrams/`
`core-batches/manifest.json`, `core-all-routing-final.log`, `core-routing.log`,
`core-focused-final.log`, `desktop-final.log`, `format-style-final.log`,
`lint-routing-final.log` and `types-routing-final.log`. The initial protocol fixture
mismatch is retained in `core-initial-failure.log` and `core-all.log`.

GUI acceptance: the full Electron/local Core sweep passed all 82 checks with no
renderer exceptions, then passed all 82 again after aligning the save button with the
existing primary-button style. The disposable-profile workflow previews a process,
invalidates approval after a label change, discards without publication, creates a
four-node hierarchy with an assigned parent, saves, reloads it, converts to a cycle,
removes a node, changes palette, saves, previews/saves deletion and undoes all three
complete revisions. Dialog overflow and all existing authoring/project workflows passed.
Final hierarchy, cycle and deletion screenshots were inspected; the hierarchy screenshot
was inspected again after primary-button styling. The initial GUI run caught an oversized
image lacking the established figure wrapper; the next run reached deletion but used
an incorrect Undo accessible name. Both failures are retained. Final receipts:
`.local/diagrams/gui-style-final.log`, `gui-routing-final.log`, `gui-result.json` and
`workspace-native-diagram-{process,hierarchy,cycle,delete}-review.png`.

Native PowerPoint acceptance used five fixtures: three/eight-node processes, a branched
five-node hierarchy and two/eight-node cycles. Each fixture opened read-only at baseline,
inserted, edited and deleted stages. COM verified node IDs/text, group membership,
attached begin/end shapes, directional arrowheads and preserved notes. Unchanged second
slides stayed pixel-identical at every stage; deleting the diagram restored baseline
first-slide pixels, and undo restored exact edited-package bytes. Read-only Office
opening changed no package hashes. All ten inserted/edited exports were inspected in
two contact sheets. Visual inspection caught diagonal routing entering nodes from an
incorrect side; final hierarchy arrows leave parent bottoms and enter child tops, and
process/cycle arrows use separated node edges. Regenerated exports passed all checks.
Receipts: `.local/diagrams/office-final.log`, `office/result.json`,
`office/contact-{1,2}.png` and `office/{0,1,2,3,4}/{inserted,edited}.png`.

The existing PPTX ingestion parser walks grouped children. A separate extraction check
against all five native fixtures verified every inserted label, updated first labels,
absence of deleted labels and identical unchanged-slide units. Receipt:
`.local/diagrams/ingestion-check.json`. No ingestion writer change was needed.

Scope: app-authored process/hierarchy/cycle diagrams with native editable text/shapes,
not full SmartArt authoring or arbitrary graph layouts. Native manual changes and
external dependencies are preserved rather than regenerated. The workflow does not
provide automatic text fitting or collision avoidance; users review labels, connections
and placement. Copilot/voice diagram planning and broader corpus/renderer equivalence
acceptance remain open. Source retrieval refresh is part of reviewed saves; native
PowerPoint evidence and local GUI checks do not prove live-provider quality.

Source/test freeze: `.local/diagrams/source-freeze.json` (329 entries), verified after
all checks in `source-freeze-check.json`. All owned test/Office processes reached
terminal states and `git diff --check` passed. Eight prior
frozen files were modified and all other 317 prior source/test files stayed unchanged.
Three source/test files were added; the existing shared capability example was updated
and added to this freeze. Dirty work remains on `codex/production-readiness` at base
`657b876739ff7a1cc5709a7e28e92ec2551b337e`. Broader fidelity/integration acceptance,
fast-decision calibration/latency and live Sign in with ChatGPT acceptance remain open.
Signing and clean Windows validation remain accepted debt. Goal active.

## 2026-10-04 continuation - Copilot and reviewed voice diagram planning

Copilot edit proposals now create, replace and delete structured native process,
hierarchy and cycle diagrams. Reviewed voice instructions use the same proposal flow.
A proposal can first create an authored slide and then place its diagram through a
staged created-by reference. Existing supported diagrams expose bounded semantic data
and geometry from selected slides, so subsequent requests can convert or remove them.

Dependencies reasoned through before edits: the provider describes intent but does not
supply fingerprints or native identities. Core binds each replacement/deletion to the
current staged package, including targets created earlier in the same plan. The strict
provider schema rejects unknown preconditions, invalid evidence and out-of-scope targets;
the native writer still owns structure, package preservation and external-dependency
checks. At most twenty diagram descriptions per selected slide reach the provider.
Manually changed or externally referenced diagrams remain read-only. Generic group
eligibility, privacy gates, review acknowledgment, exact reviewed hashes, transaction
rollback, retrieval refresh and revision undo retain their existing authority. No new
IPC method or migration was needed.

Validation: eight new Core tests cover staged creation/replacement/deletion, forward
references, unselected targets, invalid evidence, provider-supplied fingerprints,
invalid parents, snapshot data and existing diagram binding. The complete Core sweep
passed all 933 collected cases in four serial batches (160/246/214/313), with no
omissions or skips. All 157 desktop tests, formatting, lint, TypeScript and mypy
(151 files) passed. The final focused planner suite includes 38 cases. Receipts:
`.local/copilot-diagrams/core-batches/manifest.json`, `core-all.log`,
`core-focused-final.log`, `desktop.log`, `format-final.log`, `lint.log` and `types.log`.

GUI acceptance: the complete Electron/local Core sweep passed all 84 checks. A
reviewed voice fixture adds an authored slide plus process diagram, requires both
affected-slide previews, then converts/deletes the diagram and restores all three
revision heads through undo. The creation, conversion and deletion review screenshots
were inspected. No renderer exceptions occurred. The initial run used a slide-title
locator unavailable until selection; the corrected test selects the inserted second
slide and waits for each exact restored revision. Receipts: `gui-final.log`,
`gui-result.json` and `workspace-copilot-diagram-{create,convert,delete}-review.png` in
`.local/copilot-diagrams/`. Voice and provider data are deterministic local fixtures.

Native PowerPoint acceptance used the deterministic local provider to propose/save
an authored slide plus process diagram, convert it to a cycle and delete it. Four
read-only opens verified native node text, attached directional-arrow endpoints,
preserved notes and unchanged package bytes. Both original slides stayed pixel-identical
through all stages. Three successive undos restored exact prior packages and the
baseline. Creation, conversion and deletion exports were inspected. Receipts:
`.local/copilot-diagrams/office-final.log`, `office/result.json` and `office/contact.png`.
The first acceptance script reused a stale revision ID during undo; that script error
and initial log are retained, and the corrected final run passed.

Source/test freeze: `.local/copilot-diagrams/source-freeze.json` (330 entries). Six
previously frozen source/test files changed, 323 remain byte-identical and one test
module was added. Branch remains `codex/production-readiness`, base SHA
`657b876739ff7a1cc5709a7e28e92ec2551b337e`. Dirty work was preserved.

Scope: diagram support is app-authored native shapes, with reviewed placement and text;
full SmartArt editing, automatic text fitting and arbitrary graph layouts remain outside
this slice. Deterministic provider/voice fixtures do not prove microphone recognition,
real model planning, account authentication or cross-renderer equivalence. Broader
fidelity/integration acceptance, fast-decision calibration/latency and live Sign in with
ChatGPT acceptance remain open. Signing and clean Windows validation remain accepted
technical debt. No model/account call, download, staging, commit, push, packaging or
release was performed.

## 2026-10-04 continuation - refinement of unsaved Copilot edit proposals

Copilot now offers a separate Refine proposal field after proposing changes. Feedback
keeps the original request, slide scope and attached pictures, and produces a complete
replacement proposal from the same baseline. A valid replacement must be viewed and
acknowledged again before saving one exact reviewed revision. Failed inference or
validation preserves the prior available proposal; users can clear feedback, acknowledge
it again and save it, or retry refinement. Changing the original request still starts a
fresh proposal. Earlier-step created-target references remain usable across refinements.

Dependencies reasoned through before edits: resolved native target IDs from a preview
cannot become baseline authority. The transient Core review plan therefore retains the
validated provider intent with its original creation references, original/latest
instructions, slide numbers and attached asset IDs. This data is untrusted context,
not approved source material or executable commands. Refinement requires the same
project/document, baseline, slide scope and assets; ownership/expiry and the current
source are checked around inference. The provider returns a full replacement plan,
whose evidence, scope, assets, target preconditions and native operations are checked
again against the baseline and rolling staged package. No previous fingerprint is
supplied by the provider. The existing context bound rejects oversized drafts. Nothing
is published until normal reviewed save. The existing provider-health guard is retained; an explicit
synthetic connection check in the dialog can recover provider readiness before retry.
Failed staging leaves the earlier preview
intact; the GUI discards it only after a valid replacement exists. This adds no IPC
method, database migration or durable draft/conversation storage. Expiry, rejection,
source/project deletion and shutdown remove retained intent with its preview.

Validation: twelve new Core cases cover successful refinement, original title retention,
updated notes, unchanged baseline, exact-byte save/undo, synthetic provider-health
recovery without project content, scope/asset changes, missing or
foreign drafts, stale/expired/non-planner previews, expiry during inference, invalid
evidence, late target failures and two rounds of creation-reference refinement. The
final focused planner suite passed 50 cases. Complete Core validation covers all 945
collected tests in four serial batches (284/161/254/246), with no omissions or skips.
The recovery repeat initially caught an edit-plan-only test hook left enabled during
the synthetic connection check. After correcting that fixture, the entire affected
161-case batch was rerun successfully; the other three batches passed unchanged.
All 157 desktop tests, formatting, lint, TypeScript and mypy (151 files) passed. Receipts:
`.local/copilot-refinement/core-batches/manifest-recovery-final.json`,
`core-all-recovery.log`, `core-retry.log`, `core-focused-recovery-final.log`,
`desktop-recovery.log`, `format-recovery-final.log`, `lint-recovery-final.log` and
`types-recovery.log`. Earlier complete 945-case and 86-check runs remain in
`core-all.log` and `gui.log`; all intermediate failures are retained.

GUI acceptance: the final Electron/local Core sweep passed all 86 checks with no
renderer exceptions. The workflow reviews an initial title/notes proposal, fills
feedback, rejects malformed evidence while retaining that proposal and its viewed
state, clears feedback and re-acknowledges the original, explicitly checks the provider,
then refines successfully. It verifies the original title change is retained, notes
are revised, old acknowledgment is cleared, save stays disabled until fresh review,
and the result saves/re-indexes as one revision followed by whole-revision undo. Failed
and refined review screenshots were inspected. The first recovery run showed that
malformed output correctly marks the provider unavailable, preventing retry; the dialog
now exposes the existing synthetic Check reasoning provider action without weakening
that guard or sending project content. Receipts: `.local/copilot-refinement/`
`gui-recovery.log`, `gui-result.json` and `workspace-copilot-refinement-{failed,review}.png`.
`gui-final.log` preserves the provider-readiness failure that drove this recovery work.

Native PowerPoint opened baseline, initial unsaved draft and refined packages read-only.
The title change appeared exactly once; refined notes matched the reviewed replacement;
initial/refined first-slide pixels were identical because only notes changed. The
unchanged second slide remained pixel-identical. Office changed no package bytes, save
published the reviewed package and undo restored baseline bytes. The refined slide export
was inspected. Receipts: `.local/copilot-refinement/office.log`, `office/result.json` and
`office/{baseline,initial,refined}-{1,2}.png`.

Source/test freeze: `.local/copilot-refinement/source-freeze.json` (331 entries). Six
previously frozen source/test files changed, 324 remain byte-identical and one test
module was added. Branch remains `codex/production-readiness`, base SHA
`657b876739ff7a1cc5709a7e28e92ec2551b337e`; dirty work was preserved. The AI editing
contract now documents refinement and the current 21-type provider schema.

Scope: this verifies deterministic local provider planning and GUI review mechanics;
real model refinement quality, microphone recognition, cross-renderer equivalence and
account authentication remain unproven. Broader substantial authoring/GUI work and
fidelity/integration acceptance remain, including fast-decision calibration/latency
and live Sign in with ChatGPT acceptance. Signing and clean Windows validation remain
accepted technical debt. No model/account call, download, staging, commit, push,
packaging or release occurred. Goal remains active.

## 2026-10-04 continuation - Copilot native table and chart workflows

Copilot now proposes native table/chart creation, value edits and structural changes.
It can create an authored slide and populate it through earlier-step references, edit
existing cells/series, add or remove rows/columns/categories/series, and compose these
operations as one reviewed revision. The dialog exposes exact proposed cells and chart
numbers, with expandable previous data from the actual staged target; slide images alone
would hide exact values. Existing refinement, evidence review, affected-slide viewing,
acknowledgment, exact-byte save, retrieval refresh and whole-revision undo remain intact.

Dependencies reasoned through before edits: the direct writers already own supported
native structures and their package-preservation rules. The provider schema now adds
six operations (27 total) without granting fingerprints or workbook authority. Numeric
schema validation accepts bounded finite integers/floats and rejects booleans/NaN;
domain writers validate rectangular data, category/series lengths, pie constraints,
source-index maps and native compatibility. Core inspects only selected slides and
supplies at most twenty table descriptions and twenty chart descriptions per slide,
with ordinary context-size enforcement. It supplies cached chart data rather than
embedded worksheet content and strips fingerprints/native part references. Replacement
and structural operations bind current fingerprints from each staged package, so prior
steps can create or update their targets. Retained source indices remain unique and in
original order; null creates an item. Tables with merged/complex cells, linked/unsupported
charts and unsupported structures remain read-only. Existing writers preserve or clone
native relationships/workbooks appropriately, protecting shared charts and hidden original
workbook parts. No native writer, IPC method, database migration or revision authority
was changed. Previous-data diffs are review response data, not durable audit content.

Validation: twenty new Core cases cover composition of all six operations, ordered
creation references, successive fingerprints/diffs, exact reviewed save and undo,
forward/unselected/wrong-kind targets, malformed evidence/preconditions, boolean/NaN
values, ragged tables, mismatched series lengths, invalid source maps, shared imported
chart isolation, linked/extension/stacked/missing-cache charts, ordinary table context,
merged/mixed-run table preservation and a real hidden embedded worksheet. The hidden
worksheet's sentinel never enters provider input; its original workbook member survives
the selected chart edit. All 50 existing planner/refinement/diagram tests passed before
the new module. The fresh complete Core sweep passed all 965 collected tests in four
serial batches (229/281/169/286), with no omissions or skips. All 157 desktop tests,
formatting, lint, TypeScript and mypy (151 files) passed. Receipts under
`.local/copilot-data/`: `core-batches/manifest.json`, `core-all.log`,
`core-focused-more.log`, `core-existing.log`, `desktop.log`, `format-final.log`,
`lint-final.log` and `types-final.log`. The initial lint-only fixture line-length error
is retained in `lint.log`.

GUI acceptance: the Electron/local Core sweep passed all 90 checks with no renderer
exceptions. It creates an authored slide plus table/chart, reviews both affected slides
and exact numeric data, saves, selects the new slide, updates both values together,
compares previous/proposed data, expands table rows/columns and chart categories/series,
saves each as one revision/re-index, and undoes all three exact revision heads. Creation,
update and expansion review screenshots were inspected. Receipts:
`.local/copilot-data/gui.log`, `gui-result.json` and
`workspace-copilot-data-{create,update,expand}-review.png`.

Native PowerPoint opened the baseline and all three saved stages read-only. COM verified
native table dimensions/every cell, chart title/category/series names/values and notes.
Independent embedded-worksheet inspection verified matching literal cells and no formulas.
Both original slides remained pixel-identical, native table/chart identities remained
stable, Office changed no package bytes and three successive undos restored exact prior
packages and baseline. All three native slide exports were inspected in a contact sheet.
Receipts: `.local/copilot-data/office.log`, `office/result.json`, `office/contact.png`
and `office/{created,updated,expanded}.png`.

Source/test freeze: `.local/copilot-data/source-freeze.json` (332 entries). Seven prior
source/test/style files changed, 324 remain byte-identical and one test module was added.
Branch remains `codex/production-readiness`, base SHA
`657b876739ff7a1cc5709a7e28e92ec2551b337e`; dirty work was preserved.

Remaining substantial chart presentation gap observed in the native exports: adding a
second series preserves an existing hidden legend, so the user still needs explicit
legend controls. This slice adds data planning/review, not chart decoration controls or
automatic fitting. Broad corpus/renderer fidelity, real-model integration quality,
fast-decision calibration/latency and live Sign in with ChatGPT acceptance remain open.
Signing and clean Windows validation remain accepted technical debt. These tests used
local deterministic providers and synthetic data; no account/model call, download,
staging, commit, push, packaging or release occurred. Goal remains active.

## Explicit native chart legends - 2026-10-04

Explicit native chart legends are implemented in the GUI and Copilot as reviewed
transactions. All 983 Core tests and 157 desktop tests passed; formatting/lint/types
pass, and PowerPoint verifies all placements/overlay/hide plus six byte-exact undos.
The Electron/local Core sweep passed all 93 checks with no renderer exceptions.
Three added checks cover loading native settings, bottom-to-right draft invalidation,
fresh reviewed save, hide-preview discard, exact undo, and Copilot hidden-to-bottom
previous/proposed settings with native preview/save/re-index/undo. The test explicitly
awaits asynchronous chart discovery and reselects the metrics slide after undo.
Both direct and Copilot review screenshots were inspected. Receipts:
`.local/chart-legend/gui.log`, `gui-result.json`,
`workspace-chart-legend-right-review.png`, and
`workspace-copilot-chart-legend-review.png`. Earlier fixture encoding, loading-wait and
undo-selection failures are retained in `gui-fixture-{encoding,label,loading,slide}.log`.
Broader fidelity, real-model, fast-decision and live ChatGPT sign-in acceptance remain
open. Signing and clean Windows validation remain accepted debt. See the latest
SESSION_HANDOFF.md section and `.local/chart-legend/` receipts for exact scope.

## Reviewed native chart colors - 2026-10-04

Native chart RGB editing is implemented directly and through Copilot, including
series and individual bar/column points/pie slices; line series use stroke only.
1006 Core tests, 157 desktop tests and formatting/lint/types pass. PowerPoint verifies
all six supported target cases, unchanged other-slide pixels/original dependency
parts and exact undo. The Electron/local Core sweep passed all 96 checks without renderer exceptions.
Three added checks cover series/point target selection, RGB draft invalidation, fresh
native review/save/reopen/undo, reviewed point-preview discard and Copilot composed
series/point edits with previous RGB review, one-revision save/re-index and exact undo.
All three new review screenshots were inspected. Receipts: `.local/chart-colors/gui.log`,
`gui-result.json`, `workspace-chart-color-{series,point}-review.png` and
`workspace-copilot-chart-colors-review.png`. The first sweep reached a correct rendered
preview but the acknowledgment text had been changed incorrectly during component
extraction; the corrected label and final sweep are verified. The earlier failure is
retained in `gui-fixture-label.log`.
Broad corpus/model/fast-decision/live ChatGPT sign-in acceptance remains open.
Signing/clean Windows validation remain accepted debt. See SESSION_HANDOFF.md and
`.local/chart-colors/` receipts for scope; shared-chart preservation is package-level.

The final chart-color render check reuses the established color-control style so the
RGB picker displays a visible swatch. The complete 96-check behavior sweep preceded
this style-only correction; a fresh disposable Electron check imported an accepted
native chart, opened the color dialog, set purple and verified a 42px-wide, at least
30px-tall picker with 3px padding and the exact RGB. The screenshot was inspected.
Receipts: `.local/chart-colors/swatch.log`, `swatch-result.json`, `swatch-visible.png`.
Formatting/lint and the 339-entry freeze were reverified afterward.
