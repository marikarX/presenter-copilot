# Presenter Copilot session handoff

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

Validation: latest full `pnpm check` green on `57c84c4` (1902 Core tests,
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
LM Studio is installed on this host but its daemon would not start headlessly,
so no local-model Fast Decisions run was possible this session.

Human-gated items (cannot be completed by an agent):

- Sign in with ChatGPT live acceptance: run
  `PRESENTER_CHATGPT_LIVE_ACCEPTANCE=1 pnpm accept:chatgpt-live` with an
  eligible account. It automates consent wait, restart persistence, model
  listing, disclosures, one synthetic decision, catalog refresh and sign-out,
  and writes a token-free receipt to `.local/chatgpt-live/`.
- Fast Decisions calibration needs a licensing-safe human-labeled set.
- Codex "Sign in with ChatGPT" lasting only for the app session is documented
  in `docs/PROVIDERS.md` as part of the isolation design, not a bug.

Next: remaining direct-edit gaps (picture bullets, symbol-font bullets), held Run/head GUI replies,
fidelity corpus review and human acceptance gates. Signing and clean Windows
validation remain accepted debt.

## Current continuation - identity GUI accepted and comparison contract started (2026-10-08)

IN PROGRESS. Actual GUI60052 terminal0:20 checks/errors empty at
objection-identity-final-gui/result.json and objection-identity-final-gui.log.
Historical changed recording retains exact original candidate IDs/excerpts, disables
adoption and permits independent dismiss/reopen. Exact recording restoration restores
eligibility. Actual GUI Move Slide creates revision4, preserves original slide1/
candidate identity and dispositions, maps to current slide2 and enables notes on that
current slide. Actual reviewed GUI Delete Slide creates revision5; history/excerpts/
IDs remain, current mapping/navigation disappear, adoption disables and independent
dismissal creates no further native revision. Picker/capture/model remain fixtures.

First identity run28393 proved18 checks, then omitted opening Slide actions & layout.
Second41815 also proved18, then stopped on corrupted revision-label test literals.
Failure screenshots inspected; disclosure interaction and two UTF-8 labels corrected.
Both failed receipts/screenshots retained in objection-identity-gui and
objection-identity-corrected-gui. Final20-check run accepted. Harness lint/format pass;
identity freeze510 retained509 previous inputs unchanged/one harness-only edit.

Substantial distinct-Run semantic equivalence work has begun: new provider task
presentation_rehearsal_objection_equivalence and strict schema assess a complete
1..4 by1..4 selected candidate matrix. Each pair retains original left/right IDs and
unverified equivalent/related/distinct/unclear interpretation; omitted/duplicate/
foreign/reversed/same-side IDs, unsupported review/speaker/quote authority and bounded
result violations reject. Output cannot merge dispositions/adoption or imply whole-Run
absence/transitive equivalence. OpenAI/local/Codex/fake registry/transport use the
contract; fake returns only unclear. Local matrix response budget8192 tokens.

Target64945 terminal0:153 tests15.53sec including old coverage/objection/local/Codex
regression; final33 contract tests1.02sec pass after audit metadata assertions include
both candidate IDs. Manifest sorting assumption and long OpenAI schema-name line
corrected. Core ruff format310/check and mypy193 pass. No live provider/account claim.
This is a provider foundation; owned comparison context, durable store, two-Run
job lifetime/API and GUI ARE NOT IMPLEMENTED YET.

Comparison freeze512 retains506 of510 identity inputs unchanged/four intended provider
edits/two new schema/test files,434 dirty paths/branch/base/16 package hashes.
Use verify-objection-equivalence-contract-preservation.py and its freeze. Full
check62233 RUNNING at check-objection-equivalence-contract.log; poll existing handle,
no restart on timeout. Production source frozen; no GUI/build live. No staging/
commit/push/reset/package rebuild. Older packages stay isolated from schema22 stores.

Next: finish full check, then owned immutable candidate context from two distinct
ended Runs with both full recording/audit/native/privacy guards. Preserve both Run
lifetimes in shared jobs before exposing Start. Add durable comparisons retaining
original candidate identities/dispositions and comparison GUI. Held Run/head GUI
replies, broader density/assets/conversation, fidelity/live Fast Decisions/official
ChatGPT/human acceptance remain required. Rough80% overall/features90%/integration68%;
signing/clean Windows accepted debt; goal active and original scope intact.

## Current continuation - actionable objection error routes accepted (2026-10-08)

IN PROGRESS. Broader Workspace81032 terminal0:117 checks/renderer errors empty on
pending-Cancel build. Receipt retained as objection-start-workspace-result.json.
Full1812 Core/mypy192 remains current (Core unchanged); desktop312/lint/types/build
and targeted format checks pass after error formatter changes.

Dependency inspection confirmed unwrapInvokeResult throws a structured object,
while objection errorText previously accepted only Error instances. The formatter
now preserves plain structured message/code, accepts ordinary Error messages, adds
recovery directions for known provider/privacy/context codes and avoids exposing
error details. Failed worker jobs use the same formatter. Settings/privacy/audit/
native authority is unchanged; no acknowledgement is automated.

GUI32279 terminal0:16 checks; final GUI34920 terminal0:17 checks/errors empty.
Actual Core routes reject fixture-unconfigured and remote-in-Local-Only providers;
disposable cloud policy without acknowledgement rejects remote use with Project
settings guidance. Policy remains explicitly selected/acknowledgement false,
no failed analysis persists and native revision is unchanged. Late recording
mutation rejects actual Start before job allocation; structured RPC message/code
and fresh-preparation guidance remain visible. Exact recording restored, explicit
retry stores a verified analysis without editing native slides. Provider readiness/
locality, model and capture are fixture boundaries; routing/store/jobs/native are
actual code. This does not prove live providers, account or human acceptance.

Evidence: objection-errors-final-gui/result.json, objection-errors-final-gui.log,
objection-errors-desktop.log and objection-errors-build.log in
.local/rehearsal-semantic-coverage. Final errors freeze510 preserves508 previous
inputs unchanged/two intentional component/harness edits,432 dirty paths/branch/
base/16 packages. Use verify-objection-errors-final-preservation.py and
objection-errors-final-freeze.json. No GUI/build/full-check live. Earlier117 broad
GUI predates only the display formatter; final17 dedicated GUI is current. Do not
republish ignored drafts/generators over newer maintained source.

Next: historical stale-recording adoption, source reorder/removal and held Run/head
GUI responses, then distinct-Run semantic equivalence with both-Run lifetime
ownership and independent original candidate provenance/dispositions. Broader
Workspace density/assets/conversation, fidelity, live Fast Decisions, official
ChatGPT/human acceptance remain required. Rough80% overall/features90%/integration68%.
Signing/clean Windows accepted debt; goal active. No stage/commit/push/reset/package
rebuild. Original full scope remains intact.

## Current continuation - pending Start cancellation implemented (2026-10-08)

IN PROGRESS. Dependency inspection found objection Cancel unavailable before Start
returned an ID. RehearsalObjectionReview now exposes Cancel while busy, records intent
without an ID, and explains the wait. Existing captured owner/generation path sends
actual Cancel once the ID arrives and continues observing truthful worker outcome.
Routing, persistence linearization and native edit authority are unchanged.

Desktop lint/types/build/312 tests pass; Core unchanged from full check30948
(1812 tests429.14sec/mypy192). Actual GUI82743 terminal0:12 checks; expanded direct
pending-Cancel GUI85014 terminal0:13 checks/errors empty. Independently completed
storage yields rejected late cancellation and saved history; direct pending Cancel
and panel closure each yield accepted cancellation of held actual workers with no
new analysis. Native revision/original applied review records stay unchanged. The
13-check receipt is objection-start-final-gui/result.json; log has matching name in
.local/rehearsal-semantic-coverage. Picker/capture/model are explicit fixtures.

Final start freeze510 preserves508 previous inputs unchanged/two intended edits
(component and maintained GUI harness),432 dirty paths/branch/base/16 package hashes.
Use verify-objection-start-final-preservation.py and objection-start-final-freeze.json.
Broader Workspace regression81032 IS RUNNING at objection-start-workspace.log;
poll that live handle, do not restart on timeout. Production source frozen while
GUI is live; no build/full-check live. Copy its final receipt from .local/ui-validation
to this phase when terminal. Source inputs reverified during the live run.

Next: finish broader regression, stale recording/source reorder/removal and held
Run/head GUI replies, then provider/privacy error routes. Dependency note
objection-error-route-dependencies.md records structured IPC errors currently lose
details in errorText; no route implementation edits yet. Distinct-Run semantic
equivalence/both-Run lifetime ownership, broader Workspace density/assets/conversation,
fidelity/live Fast Decisions/official ChatGPT/human acceptance remain required.
Rough80% overall/features90%/integration68%; signing/clean Windows accepted debt.
Goal active; no staging/commit/push/reset/package rebuild.

## Current continuation - objection restart and deferred detail accepted (2026-10-08)

IN PROGRESS. Full check30948 terminal0:1812 Core tests429.14sec,312 desktop tests,
format/lint/types/mypy192 pass. Log: check-objection-gui.log. Final GUI freeze510
and branch/base/16 package artifacts reverified before harness-only extension.

Maintained test-rehearsal-objection-review.mjs now closes actual Electron/Core and
reopens the same isolated project/browser data. Actual native current revision and
complete verified candidate details match before/after restart; original Run and
21 saved analyses remain selectable, both independently applied candidates stay
applied with adoption disabled and no Reopen. A real verified Core detail reply is
held at its delivery boundary, panel closed, then released. Reopened panel retains
empty Run selection/no old candidate controls; native revision and review records
remain unchanged. Fixture picker/capture/model boundaries remain explicit.

GUI44715 terminal0:10 checks/errors empty. Receipt and log:
.local/rehearsal-semantic-coverage/objection-restart-gui/result.json and
objection-restart-gui.log. Only the maintained harness changed; application source
remains identical to full-check/broader117-GUI acceptance. Harness formatting/lint
pass. Restart freeze510 retains509 of510 previous inputs unchanged;432 dirty paths,
branch/base/16 packages preserved. Use verify-objection-restart-preservation.py and
objection-restart-freeze.json. No GUI/build/full-check process live now.

Next: held Start across panel/Run/head changes and too-late Cancel, stale recording,
source reorder/removal and actionable provider/privacy configuration GUI routes.
Then distinct-Run semantic equivalence must preserve independent original candidate
provenance/dispositions and own both Runs for deletion/lifetime cancellation. Initial
dependency audit is in ignored objection-equivalence-dependencies.md; inspect actual
provider/schema/audit/deletion/protocol dependencies before implementation edits.
Broader Workspace density/assets/conversation, fidelity, live Fast Decisions,
official ChatGPT and human integration acceptance remain required. Rough80% overall
(features90%,integration68%), not test-count derived. Signing/clean Windows accepted
debt. Goal active; no staging/commit/push/reset/package rebuild.

## Current continuation - objection GUI workflow validated (2026-10-08)

IN PROGRESS. Adoption full check32677 terminal0:1803 Core/312 desktop/format/lint/
types/mypy192;Core446.87sec at check-objection-adoption.log. Freeze507/branch/base/
16 package artifacts reverified before GUI publication.

New RehearsalObjectionReview is mounted in RehearsalFindings. It supports ended Run
paging independent of debrief availability, original stable-slide paging without a
native text object, complete bounded speech-window display and explicit selection,
audited detection through shared jobs, captured-owner cancellation, paged history
including empty results, lazy verified detail, individual dismiss/reopen, and explicit
current-slide notes/text/rewrite preparation into the existing native editor. Concern
and possible-answer excerpts are displayed separately with unverified model/recorded
actor labels. Empty windows/results do not establish whole-Run absence. Historical
stale/removed candidates cannot prepare edits; applied candidates cannot reopen.
Parent current/unreviewed checks cover semantic_objection; coverage keeps its original
native-object requirement. Oversize objection text excerpts are rejected rather than
silently truncated; notes or reviewed rewrite remain available.

New list_rehearsal_review_slides API reads the original Run snapshot and current
stable-slide mapping, pages20 items and validates owned ended Run/head/native source.
No debrief or native text object is required. Core/desktop allowlists and protocol
examples advance together. Selector/history/jobs/protocol16268 terminal0:55 tests
16.85sec. Desktop types/lint, Core mypy192/ruff and pnpm build pass (existing large
bundle advisory remains). New scoped styles wrap long headings/quotes/actions.

Actual Electron/Core/native PPTX harness test-rehearsal-objection-review.mjs uses
disposable data, fixture picker/capture and an explicit sitecustomize fixture model
adapter. Production fake provider still returns empty objection output by default;
IPC/audit/storage/jobs/reviews/native edits are actual application code. Corrected
GUI39958 terminal0:8 checks, renderer errors empty. Covers no-debrief/no-speech and
graphic-only original slide paging, full>2000-character context, explicit window
selection, two candidates with separate answer quotes/independent dismiss/reopen,
notes draft preserving private notes/exact concern followed by native Save, separate
text rewrite review/native Preview/Save of sibling, held-provider accepted Cancel
with no analysis persisted, empty-window history,21-analysis GUI paging, small window.
Original and current revision/candidate dispositions are checked through actual RPC.
This does not prove live-model usefulness, actual ASR accuracy or human acceptance.

First fixture attempt had embedded Python semicolon/compound syntax error; corrected
before app launch. Next attempt proved6 workflow checks but asserted old20-row history
before page rendering. Wait corrected; accepted8-check run is at
.local/rehearsal-semantic-coverage/objection-gui-corrected/result.json/native-corrected
log and objection-small.png. Screenshot inspected: actual707x460 viewport, section
430/430 and document707/707; intro/controls readable and contained. Earlier failed
attempt evidence remains at objection-gui/failure-checks.json and failure.png.

Broader actual Workspace regression78328 terminal0:117 checks/renderer errors empty
on this build, including native table/chart/edit/Copilot/rehearsal routes, minimum
window, restart and explicit disabled Fast Decision settings. Current receipt copied
to .local/rehearsal-semantic-coverage/objection-gui-workspace-result.json. It does not
prove objection-specific restart/stale reply/hidden-panel cancellation acceptance;
those dedicated GUI edges remain required. Do not reuse old result.json while a
new harness is live. No GUI process is currently live; no rebuild/package live.

Freeze510 GUI inputs preserves499 of507 prior inputs unchanged/eight intended
selector/protocol/GUI/style edits and three new component/selector-test/harness files.
Final harness correction/format freeze510 preserves509 of510 initial GUI inputs,
only harness changed;432 dirty paths, branch codex/production-readiness/base657b876/
16 package artifacts unchanged. Use verify-objection-gui-final-preservation.py and
objection-gui-final-freeze/preservation. Stale drafts/helpers already published;
do not republish them over corrected source. Full check30948 running at
.local/rehearsal-semantic-coverage/check-objection-gui.log; production source frozen.

Next: poll30948 to terminal/reverify final freeze. Extend dedicated actual GUI evidence
for restart of objection history/applied states, held Start/detail replies when Run/
head/panel changes, stale recording and reorder/removal, too-late Cancel, and actionable
provider/privacy configuration failures. Then distinct-Run semantic equivalence must
retain each original candidate/Run/disposition; shared jobs must own both Runs for
deletion/lifetime cancellation, not only a primary Run. Broader density/assets/
conversation, fidelity and live/human integration remain open. Fast Decisions and
official Sign in with ChatGPT remain in scope. Current rough completion estimate80%
overall (features90%, integration68%); estimate is not a test-count calculation.
Signing/clean Windows accepted debt. Goal active. No staging/commit/push/reset/package
rebuild; old binaries/packages must not open schema22 stores.

## Current continuation - candidate adoption and native Save (2026-10-08)

IN PROGRESS. Shared objection queue/API full check74753 terminal0:1781 Core/312
desktop/format/lint/types/mypy191; Core439.16sec at check-objection-jobs.log.
Freeze505/branch/base/16 package artifacts reverified before adoption publication.

New RehearsalObjectionAdoption resolves exact owned candidate IDs directly from the
immutable store, independently of debrief availability or latest-Run caps. Public
objection detail now supplies a safe per-candidate finding for GUI preparation;
internal guard tokens are removed. Findings use semantic_objection, retain original
Run/source revision/stable slide/current ordinal, and use only exact concern excerpts
for quote drafts. Concern labels/reasons, answer status and separate answer references
remain unverified metadata. No native text object is implied by an objection.

Existing reject_rehearsal_finding and apply_rehearsal_edit now resolve objection
candidates as well as coverage/debrief findings. Both kinds dispatch their own native
Save guard. Under the edit transaction, the new guard verifies snapshot/candidate
hashes, provider audit/ownership, whole-recording SHA, disposition, current head/child
parent and original analysis/native edit baseline snapshots. Late failures roll back
the new revision and review together. Dismiss/reopen remains possible for stale or
removed-slide historical candidates; stale/removed candidates cannot be adopted,
applied candidates cannot reopen, and no-op Save does not mark a candidate applied.
Sibling candidates retain independent dispositions across successive native revisions.

Explicit notes/text Save is supported by the existing native edit API. Notes drafts
can preserve existing private notes locally and append exact concern excerpts; model
labels/reasons and possible answers are not automatically inserted. Text edits require
the caller's explicit current native target and expected text, not an invented source
object. Rewrite now sends the exact concern quote and separate unverified window
metadata/provenance; it retains Run/candidate audit references and excludes private
notes/knowledge. Context is checked before inference and after output, as for coverage.
No new objection GUI or actual GUI Preview/Save acceptance yet.

Focused objection adoption/prior coverage adoption/jobs/store43099 terminal0:86 tests
46.50sec. Includes public safe detail, independent dismiss/reopen, actual notes/text
PPTX content, sibling native revisions, no-op Save, stale recording/provider-output
rejection, reorder/remove, concern/answer separation, foreign scope, atomic rollback
for late speech/review/analysis/candidate/audit/original and current native mutations.
Existing debrief/recurring/rewrite/history/appendix/edit-planning24593 terminal0:
83 tests31.03sec. Mypy192 and ruff check pass; one import-order issue fixed. Model and
capture boundaries remain deterministic fixtures, not live-model/human acceptance.

Freeze507/preservation retains502 of505 previous inputs unchanged, three intended
Core/rehearsal/rewrite edits and two new adoption/test files;429 dirty paths, branch
codex/production-readiness/base657b876/16 package artifacts unchanged. Full check32677
running at .local/rehearsal-semantic-coverage/check-objection-adoption.log. Production
source frozen; no build/GUI live. Ignored adoption drafts/helpers already published;
do not republish them over corrected source or rerun earlier schema mutators.

Next: poll32677 to terminal/reverify freeze. Implement substantial actual objection
GUI in RehearsalFindings: ended Run paging independent of debrief, original stable
slide selection independent of native text objects, complete bounded speech-window
selection, explicit detection with captured-scope cancellation, empty-result and
multi-candidate history, lazy verified detail, separate concern/answer quotes and
unverified actor/model labels, per-candidate dismiss/reopen, explicit current-slide
notes/text/rewrite preparation, actual native Preview/Save and restart acceptance.
Extend RehearsalFinding union and parent prepareFinding current/unreviewed checks to
semantic_objection; retain coverage's original-object requirement only for coverage.
Use the existing pending rehearsal edit/native Save callback so adopted provenance
is recorded atomically. Validate hidden/stale panels, cancellation races, small-window
overflow and older Workspace routes in actual Electron/Core. Then distinct-Run
semantic equivalence with independent provenance/dispositions, broader Workspace
density/assets/conversation, fidelity and live/human integration gates. Fast Decisions
and official Sign in with ChatGPT remain in scope. Estimate78% overall/88% features/
65% integration acceptance unchanged; signing/clean Windows accepted debt. Goal
active. No staging/commit/push/reset/package rebuild; old packages cannot open22.

## Current continuation - audited objection storage and shared jobs (2026-10-08)

IN PROGRESS. Schema22 full check10376 terminal0:1730 Core/312 desktop/format/lint/
types/mypy189. Audited objection storage full check26305 terminal0:1761 Core/312
desktop/format/lint/types/mypy191; Core411.29sec at check-objection-store.log.
Store freeze504/branch/base/16 package artifacts reverified before queue edits.

RehearsalObjectionStore now saves immutable analyses, including explicit empty
results and independently identified 0..4 candidates. Strict snapshot/candidate
hashes, successful owned provider audit, whole-recording identity, exact original
window, native snapshots and current head are checked. History remains readable
after recording changes, but candidates lose adoption eligibility. Original privacy
metadata reconstructs the original window after a preference-only change. Concern
quotes and possible answer quotes remain separate from unverified interpretations.
RehearsalObjectionAnalysis uses ProviderExecutionService and checks policy/context/
cancellation before provider execution and again inside the storage transaction.
Provider/model fixtures prove contracts, not live-model usefulness or speaker truth.

New public Workspace APIs: prepare_rehearsal_objections_review,
start_rehearsal_objections_analysis, list_rehearsal_objections_analyses and
get_rehearsal_objections_analysis. Starts use the existing shared bounded queue;
poll_rehearsal_analysis/cancel_rehearsal_analysis serve both kinds. Both kinds share
four live slots, 32 retained job records and all existing lifecycle barriers. Job
status declares analysis_kind and returns only result IDs after the worker exits;
objections return finding_ids, coverage retains its existing finding_id contract.
Bounded history includes empty analyses, verifies stored hashes/audit/candidates,
and requires verified detail before adoption. It does not infer whole-Run absence
or publish adoption eligibility from a history listing.

Targeted store/context/prior coverage regressions80 tests42.86sec and latest store
native cases31 tests13.41sec passed. Shared queue/objection IPC/old coverage jobs/
history/protocol regressions31409 terminal0:69 tests26.99sec. Includes independent
candidate completion, empty results, queued cancellation, before/inside-commit
races, shared mixed-kind capacity, retained history after eviction and recording
change, foreign scope rejection, deletion/close/model/reset pending barriers.
Source deletion retains its existing retryable SOURCE_DELETE_FAILED wrapper with
REHEARSAL_ANALYSIS_CLEANUP_PENDING cause. Initial assertion and dispatch signature
type error corrected; Core mypy191 and desktop type checks pass. No GUI acceptance
for objections yet; no actual objection native Save or dismiss/reopen API yet.

Freeze505/preservation retains498 of504 previous inputs unchanged, six intended
queue/Core/protocol/history edits and one new job test file;427 dirty paths, branch
codex/production-readiness/base657b876/16 package artifacts unchanged. Full
check74753 running at .local/rehearsal-semantic-coverage/check-objection-jobs.log;
production source frozen, no build/GUI live. Draft generation/publication helpers
already ran; do not republish stale drafts over corrected production files.

Next: poll74753 to terminal and reverify objection-jobs-freeze/preservation. Add
candidate resolution and native adoption with same-transaction candidate/audit/
recording/disposition/native-source guards. Existing rehearsal adoption resolves
coverage or debrief findings; it cannot yet resolve objection candidates. Objections
have no original native text object: first explicit route is exact concern-quote
notes with review/Preview/Save, preserving existing private notes locally. Text and
appendix proposals need explicit current targets plus source provenance. Then wire
the actual GUI for Run/original-slide/window selection, detection, paged history,
lazy verified detail, per-candidate dismissal/reopening and reviewed native Save.
Cross-Run semantic equivalence remains required and must preserve distinct Run and
candidate identities/dispositions. Broader density/assets/conversation, remaining
semantic GUI edges, fidelity, live Fast Decisions and official human ChatGPT
acceptance remain open. Goal active; estimate78% overall/88% feature implementation/
65% integration acceptance unchanged. Signing/clean Windows accepted debt. No
staging/commit/push/reset/package rebuild; older binaries must not open schema22.

## Current continuation - objection schema22 and recording identity (2026-10-08)

IN PROGRESS. Objection context/provider full check1041 terminal0:1726 Core/312
desktop/format/lint/types/mypy189;Core414.20sec at check-objection-context.log.
Freeze500/branch/base/16 package artifacts reverified before next edits.

Dependency audit found whole-recording SHA included current privacy preference.
Corrected to match existing transaction-compatible recording_state: owning Run ID/
project/source revision/mode/status and every final utterance's original identity,
text/actor/timing/slide. Preference-only change retains recording/context identity;
privacy is separately checked before provider/persistence. Preparation still rereads
owner/privacy/rows to reject changes during its capture. New regression proves SHA
matches existing guard and remains stable after a preference change.

Project schema22 adds presentation_rehearsal_objection_analyses (one immutable
analysis/provider audit, original source/baseline/Run FKs, context and recording SHA,
window/privacy/bounded JSON/SHA) and presentation_rehearsal_objection_findings (0..3
unique candidate slots per analysis with cascade). Separate records permit an empty
analysis with no findings. No domain save/read parser, objection RPC, job orchestration,
candidate adoption or GUI yet; schema presence is not completed durable functionality.
Protocol examples/version expectations advance together. Older migration fixtures
drop new tables before downgrading; schema21 collision recovery restores current22.
New populated21->22 migration preserves prior coverage analysis/review/audit/recording/
debrief/native files/app DB. Bounds/uniqueness/FKs/cascade and rollback tested.

Targeted schema/context/native/storage regressions48258 terminal0:83 tests23.20sec;
all migration/schema selection30 tests6.41sec (1700 deselected), not full suite.
Ruff format/check301 files and mypy189 passed. Freeze501/preservation retains500
prior inputs/482 unchanged/18 intended schema/context/test/protocol changes and1 new
migration test;423 dirty paths, branch/base/16 artifacts unchanged. Full check10376
running at check-objection-schema22.log, source frozen; no build/GUI live. Mutator
advance-objection-schema-tests.py already ran; do not rerun it or duplicate table drops.

Next: poll10376 terminal/reverify freeze; implement strict typed immutable save/read
and analysis service through ProviderExecutionService. Verify candidate hashes/audit/
source/complete original speech and window identity, including explicit empty results.
History must remain readable after recording changes but block adoption; retain the
original privacy/window preparation metadata for truthful historical window validation.
Concern excerpts and possible answers remain separate from labels/reasons. No original
native object belongs to an objection: first native route is explicit concern-notes
review/Save; later text/appendix proposals require explicit target plus provenance.
Integrate shared bounded jobs and lifetime/cancellation guards, then public API and
actual GUI; distinct-Run semantic equivalence remains required. Broader density/assets/
conversation, semantic GUI remaining edges, fidelity, live Fast Decisions and official
human ChatGPT acceptance remain open. Goal active; signing/clean Windows accepted
debt. No staging/commit/push/reset/package rebuild. Older binaries/packages must not
open schema22 stores.

## Current continuation - objection recorded context and adapters (2026-10-08)

IN PROGRESS. New RehearsalObjectionContext prepares complete bounded speech windows
for an owned ended Run and original stable slide, without requiring a native text
object or sending private notes. All four recorded actor labels are preserved and
counted; labels/speaker identity/ASR and model interpretations remain unverified.
Unknown original ordinals are counted separately. Original snapshot verification
uses existing native inventory guards; final current-head and whole-recording reread
reject changes during preparation. Slide context SHA and whole-recording SHA remain
distinct: an unrelated/unmapped recording change still invalidates the latter.
Each <=4-utterance window fits the actual serialized12000-character budget, including
policy/instruction overhead. Oversize escaped speech fails rather than truncates.

New task is dispatched through shared schema/instruction/output validation and narrow
disclosure classes in models.py; OpenAI/local/fake support it, Codex derives it from
the same task registry. OpenAI uses shared schema/tools[]/storefalse; local sends full
packet/shared schema/4096-token bound. Fake returns explicit empty observations,
never manufactures a candidate. No public Workspace objection RPC, durable storage,
job orchestration or GUI yet. This is context/provider foundation, not completed
objection detection/equivalence or live-model usefulness acceptance.

Context/contract/provider + existing coverage/context/local/Codex regression50645
terminal0:186 tests38.70sec at objection-context-provider-tests.log. First command
referenced nonexistent test_m4_provider.py and ran0 tests; corrected path list above
is the accepted scope. Ruff format/check300 files and mypy189 passed. Two SQL line
length issues corrected without behavior changes. All outputs under
.local/rehearsal-semantic-coverage/. Current objection-context-freeze500/preservation
retains497 prior inputs/492 unchanged/5 intended provider/schema edits,3 new context/
test files;422 dirty paths/branch/base/16 package artifacts unchanged. Full check1041
running at check-objection-context.log. Production source frozen; no build/GUI live.

Next: poll1041 to terminal and verify freeze. Implement immutable typed objection
analyses (multiple candidates and explicit empty-result history, original Run/source/
window/recording/native guards/provider audit); candidate dispositions and exact
concern-quote adoption inside native Save transaction. Route through bounded owned
analysis jobs and all existing cancellation/lifetime barriers, then public APIs and
actual GUI context/window/detection/detail/review/preparation/Preview/Save. Cross-Run
equivalence must retain distinct original candidate/Run provenance and individual
dispositions. Do not turn a label/reason into native truth or adopt stale recordings.
Broad Workspace regression117 remains accepted for the earlier frozen build only.
Broader density/assets/conversation, semantic GUI remaining edges, fidelity, live
Fast Decisions and official human ChatGPT acceptance remain open. Goal active;
signing/clean Windows accepted debt. No staging/commit/push/reset/package rebuild.

## Current continuation - Workspace regression accepted; objection contract started (2026-10-08)

IN PROGRESS. Broad Workspace GUI6543 terminal0:117 checks/renderer errors empty,
including native edits, Copilot/refinement, rehearsal, minimum window, full restart
and explicit disabled Fast Decision settings. Actual Electron/local Core with
disposable data and fixture capture/provider boundaries; not hardware or live-model
acceptance. Receipt copied to .local/rehearsal-semantic-coverage/
regression-workspace-result.json; full log regression-workspace.log. Prior151-file
UI evidence remains at prior-ui-validation-before-regression. Source preservation
reverified after terminal, all16 retained package artifacts unchanged. No GUI,
build or test handle remains live from this continuation.

Next substantial feature is semantic objection detection, followed by cross-Run
equivalence and reviewed edit preparation. Dependency audit: existing exact marked
notes are not inferred objections; coverage context filters actor=user and coverage
adoption uses native message quote. Coverage storage enforces its specific task,
one finding/provider run and one original native point. Do not relabel/reuse those
records for objection candidates. New context must retain relevant original actor
labels without certifying speakers; adoption must preserve the exact concern quote,
not substitute its label/reason or the native message. Recurrence requires distinct
ended Runs and original individual provenance, not counts of overlapping excerpts.

Started isolated core/presenter_core/providers/rehearsal_objection_schema.py and
core/tests/test_rehearsal_objection_contract.py. Task has <=4 observations, exact
concern excerpts separate from possible answer excerpts, answer status scoped to
one window and explicit empty result. Exact unique excerpts/UUIDs and bounded text
are validated; overlapping concerns cannot multiply counts; separate concerns may
share an unverified answer. No task routing, RPC, storage or GUI is exposed yet.
This is contract foundation, not a completed objection feature. New plus existing
coverage contract60 tests passed1.03sec; ruff format/check passed; mypy188 passed
at objection-contract-mypy.log. No full-check claim for later feature integration.

objection-contract-freeze497/preservation: all495 prior source inputs unchanged,
only2 new files;419 dirty paths, branch/base/16 retained package artifacts preserved.
Current build is the accepted correction/rewrite build; new contract is not imported
by its runtime. Next: bounded fresh objection context/request and provider routing
through existing privacy/audit/cancellation boundary; immutable typed storage and
review/adoption guards; actual GUI detection/review/native preparation/Save; then
distinct-Run equivalence. Keep failed inference and stale recordings from producing
adoptable findings. Broader density/assets/conversation, semantic-review remaining
GUI edges, fidelity, live Fast Decisions and official ChatGPT remain open. Goal
active; signing/clean Windows accepted debt. No staging/commit/push/reset/package
rebuild; schema20 packages stay isolated from schema21 data.

## Current continuation - semantic cancellation, viewport and rewrite GUI accepted (2026-10-08)

IN PROGRESS. Full check82382 terminal0:1675 Core/312 desktop/format/lint/types/
mypy187;Core401.73sec. Corrected source build terminal0 at
.local/rehearsal-semantic-coverage/gui-notice-correction-build.log, with only the
existing large-chunk advisory. GUI13865 terminal0 accepted11 checks at
gui-notice-correction/result.json: real held Start/Cancel receipt agrees with
terminal notice and durable count; already committed result survives too-late
Cancel; hidden panel cancels captured job and discards stale reply. Actual renderer
viewport707x460, semantic scroll/client430/430 and document707/707. Screenshots
inspected; older auxiliary-window screenshot is retained as historical evidence.

Expanded published harness now exercises Prepare semantic text rewrite, Suggest
rewrite, separate suggestion review and Use suggestion in editor before a user
replacement/native Preview/Save. GUI11440 terminal0 accepted12 checks at
gui-rewrite/result.json, renderer errors empty. Requesting/copying the unchanged
fixture suggestion preserves native SHA, revision and unreviewed finding; explicit
user-edited native Save marks the exact finding applied. This proves workflow and
attribution, not model rewrite quality. Earlier ordinary original-text Save proof
remains retained. Picker/ASR/provider boundaries are fixtures; actual Electron/Core/
SQLite/native PowerPoint Save are used, not physical speech or human usefulness.

Current gui-rewrite-freeze495/preservation retains prior495/494 unchanged/one
intended harness edit. Branch/base/417 dirty paths/16 retained package artifacts
unchanged. Application source matches the passing full check and corrected build;
no rebuild needed for harness-only extension. Existing rehearsal coverage GUI30219
terminal0:7 checks at regression-coverage/result.json; native claim GUI48416
terminal0:6 checks/errors empty at regression-native-claims/result.json. Broad
Workspace GUI6543 running at regression-workspace.log against this frozen build,
disposable data. Prior .local/ui-validation evidence copied to
prior-ui-validation-before-regression (151 files/52,319,013 bytes) before launch.
No production source edits while GUI is live.

Next: finish affected rehearsal/native-claim/Workspace GUI regressions; continue
substantial missing Workspace features, including semantic objections/density and
assets/conversation. Semantic review graphics/reorder/deletion/stale context/
result-window paging/held-detail selection acceptance remain open, as does dedicated
active-job reset acceptance. Fidelity, live Fast Decisions and official human
ChatGPT authentication/inference remain open. Goal active; signing/clean Windows
accepted debt. No staging/commit/push/reset/package rebuild; schema20 packages
remain isolated from schema21 stores.

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

## Current continuation - semantic rehearsal context foundation (2026-10-08)

IN PROGRESS. Dependency plan .local/rehearsal-semantic-coverage/dependency-plan.md
reasons through full semantic review/provider/privacy/persistence/adoption chain.
New RehearsalSemanticContext prepares exact selected native message spans from an
ended Run's verified frozen revision, follows stable slide/object IDs into current
inventory, and discloses changed/deleted points without rewriting historical intent.
It does not use later purpose/takeaway metadata as rehearsal-time authority or infer
that every native object was meant to be spoken. Raw semantic representation labels
retain chart-cache/table limitations; notes stay excluded.

Read-only prepare_rehearsal_coverage_review is wired in Core/Python protocol/both desktop
allowlists/ready-method example. Input project/document/current expected revision,
session/slide/object IDs and optional exact unique quote<=2000; strict page offsets/
limits. Reads actual final user-labeled utterances, preserves IDs/digests/order/timing,
reports unmapped and excluded-actor counts, unknown recording completeness/unverified
speaker identity/ASR accuracy. Whole utterances pack into contiguous max4-item windows
using actual ReasoningRequest serialization +trusted policy/instruction/512 overhead
within12000 chars. Oversized escaped content rejects instead of truncating speech.
Paged windows20 carry complete counts/context fingerprint; no provider call or writes.
Semantic coverage task instruction/output schema are defined for the request builder,
but provider task registration/inference/output validation/storage/GUI are NOT done.
Do not report this foundation as semantic omission analysis or the PW6 exit criterion.

46 focused checks pass (19 new context tests +existing coverage/protocol): actual IPC,
private-note exclusion/no inference/reviews, complete exact paging/serialized budgets,
recording edits invalidate fingerprint, reorder updates current ordinal only, native
edit/delete preserve frozen quote and disclose status, source SHA tampering rejected,
overlapping quote ambiguity, absent speech/no omission status, wrong IDs/quotes/bounds,
foreign project/active session exclusion and final head guard. Types/mypy181/lint/
format pass. Initial tests had missing imported fixture registration/fixture actor
name mismatch; corrected test setup, production authority unchanged.

Full check53657 terminal0:1556 Core/312 desktop/format/lint/types/mypy181, recorded in
.local/rehearsal-semantic-coverage/check-context.log. All owned handles terminal;
no GUI/build live. Current freeze context-freeze.json and
context-preservation.json:479 previous inputs/475 unchanged/4 intended protocol/Core
edits/2 new module-test files,481 inputs/403 dirty paths, branch/base/16 artifacts
unchanged. Verify with verify-context-preservation.py. Earlier accepted outline source
and package freezes retained; no schema migration yet (20).

Next: register the actual semantic coverage provider task (provider-contract.md),
strictly validate supplied utterance IDs/exact quotes/status requirements and test
privacy/current context/fingerprint after inference. Finish durable analysis/finding
identity and explicit adoption design before storing results (generic provider_runs
does not retain output text). Then expose explicit window selection/Analyze/review/
native preview/Save GUI; no automatic omission, trusted knowledge or deck mutation.
Broader semantic objections/visual density/human improvement, Workspace/assets,
fidelity/integration, live Fast Decisions and official ChatGPT sign-in/inference remain
open. Goal active; signing/clean Windows accepted debt. No staging/commit/push.

## Accepted continuation - outline evidence workflow (2026-10-08)

Local feature and affected regressions accepted. All owned handles terminal, including
Workspace75924 (117 pass) and final screenshot/GUI13383 (6 pass). Current phase GUI144:
Workspace117/new outline evidence6/text claims6/deck scan7/outline-session5/conversation3,
no renderer errors. Full Core1537/desktop312/format/lint/types/mypy180 passed at reader
chain; subsequent manual-transition UI passed scoped lint/types/build/all312 desktop
again. Latest harness-only screenshot change passes scoped lint/format and actual GUI6;
production source otherwise unchanged from accepted Workspace run. Builds retain the
existing large-chunk advisory. No public release, live model/human usefulness claim.

Actual new GUI workflow covers successful stored cited proposal, edited/reordered/
duplicated native cards, stable quote/object identity, current source comparison and
default unsaved context, separate confirmation/Save, existing saved link retention/
approval reset, explicit relation update, 707x460 content at2x with no horizontal
overflow, held real reader reply discard and explicit manual whole-outline transition
clearing citations/planning run. Source/model proposal is seeded through actual Core
before launch with CitationProvider fixture. Current GUI result/screenshots at
.local/outline-evidence-links/gui; unsaved-context screenshot now scrolls the claim
form into view and was inspected (source/context/unchecked approval/disabled Save).
Its exact quote is independently verified by the actual GUI assertion. Prior GUI
images retained in gui-prior-manual and hardcoded-output archives in prior-gui-evidence.

Latest freeze acceptance-freeze.json and acceptance-preservation.json:479 prior inputs,
478 unchanged/1 intended harness-only edit,479 frozen inputs/401 dirty paths, same
branch/base and16 artifact hashes. Verify with verify-acceptance-preservation.py.
Earlier foundation/reader/GUI/manual freezes retained. .local/gui-draft equivalent in
this phase is HISTORICAL and must not be copied over the published harness, which has
the main-process reply gate, measured viewport and manual-transition checks.

Next substantial priority: semantic rehearsal coverage/possible omissions. Existing
rehearsal_coverage reports quantities/recording gaps, not semantic coverage; recurring
objections only groups exact whitespace-normalized marked notes. Do not redo these
accepted workflows. Reason through frozen session revision/native identity, actual
utterance provenance, complete bounded windows/provider privacy, uncalibrated ASR,
current-head/late-reply checks and explicit findings-to-edit adoption before edits.
Start from this acceptance freeze and16-artifact receipt. Broad semantic objection
equivalence/visual density/human improvement, rich conversation/assets, corpus fidelity/
integration, live Fast Decisions and official ChatGPT sign-in/inference remain open.
Goal active; signing/clean Windows accepted debt. No staging/commit/push or package
overwrite. Follow the next phase's dependency plan; no next-phase code edits yet.

## Latest continuation - outline evidence creation/review GUI (2026-10-08)

Historical GUI checkpoint; superseded by the accepted continuation above.
Complete stored cited proposal -> edited/reordered/duplicated native cards -> retained
point identities/source review -> explicit context Save -> existing claim reopen/
relation change/reapproval is exercised through actual Electron/Core. Held real reader
reply after leaving deck review is discarded. Whole-outline editing now explicitly
starts a manual draft, discloses citation clearing and clears planning run association;
individual slide fields/layout/reorder/duplicate preserve structured references.

Full reader check89271 terminal0:1537 Core/312 desktop/format/lint/types/mypy180, recorded
in .local/outline-evidence-links/check-reader-second.log. Later manual-transition change
only touches CreatePresentation and the new GUI harness; scoped lint/types/build and
all312 desktop tests pass again. GUI-fifth.log and gui/result.json:6 pass/no renderer
errors. Genuine successful CitationProvider proposal/durable drafting session are
seeded through Core before Electron starts; standard uncited fake output is not used
as citation authority. This proves local GUI/Core workflow, not live model/human quality.
Actual minimum-window content707x460/devicePixelRatio2; no horizontal overflow. Normal
creation/source and small-source screenshots inspected; improve unsaved-context shot
to scroll the claim form itself into view (automation already verifies its quote/link).

GUI text claim6/deck scan7 regressions pass, outline-session5 and conversation3 pass.
Workspace75924 terminal0:117 pass, recorded in
.local/outline-evidence-links/gui-workspace-regression.log. All owned handles terminal.
Earlier GUI images archived under prior-gui-evidence before
hardcoded-output regressions; older package artifacts preserved.

Current source freeze manual-transition-freeze.json/preservation.json:479 previous,
477 unchanged/2 intended edits (creation UI +new harness),479 frozen inputs/401 dirty,
same branch/base and16 artifacts preserved. Chain foundation473 ->reader478 ->GUI479
retained; do not overwrite older freezes. verify-manual-transition-preservation.py
validates current source. Failed GUI first ambiguous project locator and second immutable
preload bridge hold are retained; corrected harness uses exact project locator and
main-process Core client reply gate. Fifth is passing current manual-transition source.

Next: finish Workspace regression; improve claim-form screenshot in harness only after
owned GUI terminal, rerun GUI and write new harness freeze/receipt. Reconcile roadmap
PW7 bounded native-point citation binding as locally implemented, retaining broader
conversation/assets/live quality gaps. Then prioritize substantial remaining semantic
rehearsal/objection-equivalence and Workspace features before fidelity/integration.
Official ChatGPT sign-in/inference and live Fast Decisions remain open. Goal active;
signing/clean Windows accepted debt. No staging/commit/push or package overwrite.

## Historical checkpoint - outline evidence reader and renderer chain (2026-10-08)

IN PROGRESS; complete creation-to-review GUI acceptance remains required. The receipt
foundation full check56052 is terminal0:1516 Core/309 desktop/format/lint/types/mypy179.
Read-only presentation.workspace.list_outline_evidence_candidates is now wired through
Core, Python protocol, both desktop allowlists and ready-method example. It validates
bounded receipt/original planning IDs and verified original revision/SHA, follows native
Point N name+exact text to stable slide/object identities across current reorder, and
discloses changed/deleted points instead of permitting old quote approval. Current
project-owned source chunks carry full text/SHA separately from bounded original
planning excerpts. Excerpt comparison never claims full-source freshness. Missing
planning records/sources, speaker memory and overlong chunks cannot create links.
Both receipt and no-receipt reads recheck current head. No inference or claim writes.

OutlinePlanner passes structured IDs to final creation review; title/point/layout edits,
reorder/duplicate operations retain per-slide references. OutlineEvidenceReview under
deck semantic review explicitly loads pages20, shows original/current excerpts, selects
up to4 current sources and opens the native point in existing ClaimEvidenceReview.
Default new relation=context; exact saved claims keep their previous evidence links.
Approval resets and relation judgment/confirmation/Save remain separate. Late replies
are guarded by scope/visibility/disabled state and request sequence; handoff checks
document/revision again. UI is implemented and typed, NOT yet GUI-accepted.

46 focused Core tests pass (reader21/receipt11/protocol/planning): all four native
layouts, repeated identical points with distinct object IDs, reindex, actual native
reorder/edit/delete/undo, stale heads, changed/missing/overlong sources, corrupt receipt,
missing planning record, speaker-memory exclusion, cross-project scope, bounds and
empty receipt final head check. Desktop312 tests pass, including3 packet rejection
tests; scoped lint and mypy180 pass. Initial broad check stopped at protocol formatting;
formatted the intended protocol file. Second check89271 terminal0:1537 Core/312 desktop,
recorded in .local/outline-evidence-links/check-reader-second.log. See newer GUI entry
above for current source and regression handle.

Reader receipt/freeze at .local/outline-evidence-links/reader-preservation.json and
reader-freeze.json:473 foundation inputs,464 unchanged/9 intended changes,5 new files,
478 frozen inputs/400 dirty paths; branch/base unchanged and16 package artifacts
preserved. verify-reader-preservation.py checks the foundation-to-reader chain; do not
overwrite foundation-freeze.json or use the older foundation verifier against new UI.

Next: complete real source GUI creation with cited planning context, manual draft edits/
reorder and native point handoff; verify no claim before Save, explicit relation/context,
existing claim reuse, current source change and held late replies. Build only after owned
check is terminal; record a new GUI freeze if harness/source changes. Broader Workspace,
fidelity, live Fast Decisions and official ChatGPT sign-in/inference remain open. Goal
active; signing and clean Windows validation accepted debt. No staging/commit/push.

## Historical checkpoint - outline evidence receipt foundation (2026-10-08)

IN PROGRESS. Dependency plan at .local/outline-evidence-links/dependency-plan.md.
Actual gap: OutlinePlanner passes title/string outline/run ID; per-slide evidence IDs
become note strings and do not reach object-bound review after creation. Do not redo
durable outline session recovery: it already exists. Next feature must retain cited
IDs from planning through final edited native points into an explicit evidence/claim
review workflow, preserving source provenance/current revision and separate relation
judgment/confirmation/Save. Citations never imply supports. Original supplied context
can be truncated excerpts; do not claim full-source freshness from excerpt matching.

Foundation implemented: create_from_outline accepts optional evidence_ids per slide,
up to8 distinct IDs and only IDs supplied to its successful project-owned stored outline
proposal. Cited IDs require planning run; legacy/manual inputs unchanged. Final edited
points/cited IDs, original revision/SHA/run ID form bounded outline_evidence_receipt in
documents.metadata_json. Ingestion's internal optional initialize_document callback
executes after original revision registration but before commit. Receipt failure rolls
back native registration and removes the new owned snapshot, avoiding a separately
committed deck without provenance. Callback is not an IPC parameter; source.import's
existing field rejection remains. Reindex preserves other metadata keys. No schema
migration (20), provider call, saved claim/evidence relation or GUI change yet.

44 focused tests pass (new receipt11 +planning/ingestion/draft regressions): four native
layouts/final edited points, original identity, no claim/provider creation on receipt,
reindex preservation, missing/unknown/duplicate/oversized/wrong-type/cross-project
citations reject before creation, and injected failure after receipt write leaves no
presentation/revision rows or added snapshot; subsequent retry succeeds. Scoped
lint/format/types (mypy179) pass. Full check56052 terminal0:1516 Core/309 desktop,
recorded in .local/outline-evidence-links/check-initial.log. See newer reader-chain
entry above for current work and validation handle.

Baseline before.json/prior-preservation.json copied accepted graphic GUI phase. Receipt
preservation.json/.log/foundation-freeze.json:472 prior inputs,470 unchanged/2 intended
edits (creation.py/ingestion/service.py),1 new test,473 frozen inputs,395 dirty paths,
same branch/base and16 artifact hashes. Verify with verify-preservation.py. No staging,
commit/push, package overwrite or public release.

Next after compatibility terminal: implement bounded read-only candidate service/RPC
and protocol/renderer chain. Read verified original OOXML and map generated Point N
name+exact text to stable slide/object IDs, then current verified inventory by those
identities (never current ordinal after reorder). Disclose changed/deleted/ambiguous
points and missing/changed/non-chunk/speaker-memory source refs. Compare original
supplied excerpt separately and present current project-owned supporting chunks/full
SHA for explicit relation review. Creation success/duplicate/reopen/reindex/current-head
and late replies need acceptance. Existing source.import rejects byte-identical duplicates
with SOURCE_DUPLICATE; do not claim it returns a reusable document or silently overwrite
another receipt. GUI should explicitly load exact quote/source suggestions into existing
ClaimEvidenceReview with default context, reset approval, then retain separate relation
choice/confirmation/Save. No automatic links/claims/inference on read. Validate complete
creation->native point->source review workflow and preservation; foundation alone does
not complete PW7/semantic production readiness. Broader Workspace/fidelity/human/live
Fast Decisions and official ChatGPT acceptance remain open. Goal active.

## Latest continuation - native graphic semantic claim chain (2026-10-08)

Implemented; full compatibility and actual GUI regressions pass. Workspace117 plus
graphic6/text6/deck7/incremental11 =147 actual source GUI checks pass, no renderer errors.

Separate semantic_targets/semantic_has_more/semantic_excluded_objects label verified
native text, supported raw chart caches and bounded native table cells. Existing
editing targets/flags/object.text/counts/native parsing text stay unchanged; alternate,
external and unsupported representations have no fabricated semantic text. Claim
extraction/scan/Save/provider context consume the semantic inventory. Saved record_json
stores source_kind; missing historical kinds default native_text; kind mismatch marks
changed/needs_review. No schema migration (schema20). Provider output cannot provide
source-kind authority; Core derives it from verified OOXML. Raw cache values are not
formatted/displayed values, inferred units or independently verified workbook data.
Table text retains row/tab ordering. Native SHA/head/privacy/exact unique quote,
evidence snapshot and explicit review/Save guards remain.

Extraction and typed Fast Decisions evidence triage receive source labels/disclosure;
serialized budgets include them. Scan batches carry source-kind maps; exact-input cache
identity and fresh candidate validation include kinds, including empty results. Renderer
maps semantic targets only for claims and visibly labels/discloses native representations.
Candidate handoff checks source kind as well as exact quote; editing maps stay separate.

Evidence: foundation check76927 terminal0 (1498 Core/307 desktop). Current chain full
check6319 terminal0:1505 Core/309 desktop/format/lint/types/mypy179. build.log terminal0.
Native Core7 plus inventory3 pass within full suite: raw0.2/chart/table extraction,
review-only unsaved provenance/Save/context, scan budget, actual format/data revisions/
reapproval/history, typed triage source metadata/abstention/no Save and legacy missing
text kind versus mismatched graphic-kind freshness. First check stopped on B023 closure
lint; flush now explicitly receives the source-kind map. Earlier fixture mistakes and
failed logs are retained; production authority was not relaxed to accommodate fixtures.

Actual source GUI6 pass (gui-fifth.log/result.json): percentage-chart/table selection,
labeled real Core extraction, exact quotes and review-only Save without PPTX mutation;
supporting-source picker/import/evidence search/link and synthetic typed relation review;
deck preflight/explicit raw-data acknowledgment/scan/refresh; actual PowerPoint native
color preview/Save produces new revision with unchanged raw span but needs_review, with
independent reapproval and both exact scan windows reused; actual native data preview/
Save changes Q1 20% to30%, raw0.2 to0.3, requires new exact quote/evidence judgment and
only unchanged second-slide window reuses; held actual extraction reply after slide
navigation is discarded. Screenshot source-selection/raw-quote/color/data previews were
inspected. Provider and decision adapters are deterministic fixtures: this is GUI/Core/
native-edit acceptance, not live model quality, calibration or human preparation proof.

GUI text extraction6, deck scan7 and incremental claims11 regressions pass, no renderer
errors. Scripts updated only for visible source labels. Broader Workspace regression
21172 terminal0,117 passed in gui-workspace-regression.log. All owned handles terminal.
Latest GUI format/lint passes. Earlier GUI attempts
are retained: duplicate harness deadline/unused variable; unauthorized direct evidence
import corrected to actual picker flow; Save remounts native dialog, so wait hidden rather
than clicking its transient close button. No production fix was needed for these cases.

Preservation: before.json/16 artifact hashes came from accepted voice phase. Historical
469-input foundation and471-input chain freezes/receipts remain. Latest gui-v2-freeze.json,
gui-v2-preservation.json/.log:468 prior inputs,449 unchanged/19 intended changes/4 new
files,472 frozen inputs,394 dirty paths; branch codex/production-readiness/base
657b876739ff7a1cc5709a7e28e92ec2551b337e and16 package artifacts preserved. Verify with
verify-gui-v2-preservation.py. GUI-only script changes followed the full chain check;
scoped format/lint and actual GUI runs validate them. No staging/commit/push or public
release. Do not rerun make-gui.py: it is an earlier generator and would undo harness fixes.

Final source freeze/artifact recheck passes in final-preservation.log. Next: audit
substantial remaining Workspace requirements against current code
and handoff (do not redo already implemented durable outline conversation). Broader
native/multimodal meaning, unsupported graphic coverage, semantic rehearsal omissions/
recurring objections, richer conversation/ambiguity, human preparation/voice reliability,
larger real GUI/performance and corpus fidelity remain open. Live Fast Decisions and
official human ChatGPT OAuth/catalog/inference acceptance remain open; do not import
ambient credentials or call synthetic provider acceptance live quality. Frozen package
predates voice/semantic changes; preserve it. Signing/clean Windows validation are
accepted debt. Full production-readiness goal remains active.

## Latest continuation - recognition review and voice clarification (2026-10-08)

Implemented and locally verified. Workspace ASR now retains original
final-phrase adapter scores alongside its existing bounded temporary transcript. Stop
returns a versioned recognition_review: total/unknown counts, original quotes and
optional scores, at most64 preview phrases with explicit truncation. Invalid/out-of-
range/nonfinite/bool scores become unavailable; no calibration or accuracy threshold
is inferred. Production faster-whisper deliberately returns no calibrated confidence.
Cancel clears both phrase text and score lists before releasing ownership. No new RPC,
schema migration, durable utterance/provider rows or asr.final events for Workspace.
Run/Teach/Live Assist persistence paths retain their existing behavior.

Both selected-text rewrite dictation and general Copilot/outline dictation show missing
recognition or original phrase/score review. Original quotes remain separate from the
editable corrected transcript. Intended scope/target is visible. Optional selected-
wording/slide-object clarification appends only explicit user text to the reviewed
instruction; combined text must fit the existing request limit, with a visible count.
Explicit Use fills the request field; proposing/provider invocation and native Save
remain separate. Target/revision/capture identity and epoch ownership checks remain.
Renderer rejects malformed review counts, scores and quote/transcript mismatches before
publishing usable review. Start/context/discard/Use clear temporary review/clarification.
This is local uncertainty disclosure and human clarification, not automatic semantic
ambiguity resolution or proven real-user voice reliability.

Dependency reasoning covered ASR decoder/stop/cancel ownership, temporary transcript
bounds, voice context revalidation, both independent renderer state paths, request
length and provider/save authority.17 new Core cases plus10 existing voice cases pass
(27 focused), and the added actual-capture cancellation case passes separately:18 new
Core cases total.12 new desktop parser/clarification cases pass. Types/mypy179 pass.
Actual source GUI5 passes empty-capture correction, scored/unavailable original review,
scope/clarification/combined limit, discard/reset, malformed quotes/native SHA and real
720x520 containment. Score metadata is a renderer fixture; actual scored capture is
covered in Core, and physical recognition accuracy remains unaccepted.

The first minimum-window harness did not resize a maximized window; corrected unmaximize
and Windows DPI rounding verify actual viewport720x520 (logged), final gui-fourth.log
and gui/result.json pass. Final product copy/combined count built and GUI5 rerun.
Minimum-window captures now explicitly scroll to recognition review and Use/clarification
controls; actual viewport720x520 logged and screenshots inspected. Final capture-only
harness change passed scoped lint/format and GUI5; production code/tests unchanged.
Earlier SQL/import lint and copied unused harness declarations corrected; logs retained.
Do not rerun .local/voice-review/make-gui.py: it preserves the initial harness version.

Final pnpm check passes1495 Core/307 desktop, format/lint/types/mypy179. Full Workspace
117 GUI and latest focused voice5 pass without renderer errors:122 GUI checks this
phase. Final build passes. Owned handles84241/36973/10514 and all earlier phase handles
47109/36010/2797/56579/3149/93417/54179 terminal; final capture command also terminal0.
No owned GUI/build/check remains. Initial broad check failed only copied unused harness
declarations; corrected and complete check rerun. Failures retained.

Preservation initial verifies462 prior inputs:458 unchanged/4 intended changes,6 new
files,468-input source freeze,390 dirty paths, branch/base unchanged and all16 package
artifacts preserved. Receipts/logs at .local/voice-review/source-freeze.json,
preservation.json, core-initial.log, cancel-final.log, desktop-initial.log,
types-initial.log, gui/result.json, gui-capture-final.log, check-second.log,
workspace-result.json, build-final.log and preservation-final.log.
The initial468-input freeze is retained as source-freeze-before-final-capture.json;
source-freeze.json reverified after the final capture-only harness update.
No staging/commit/push/unrelated cleanup. Current frozen
workspace-loop package remains untouched and predates this voice feature.
Broader voice/conversation/native semantics, fidelity, live Fast Decisions/human
ChatGPT OAuth/inference and physical acceptance remain open. Goal active.

Next substantial feature assessment: native chart/table meaning and claim provenance.
Avoid treating serialized chart-cache values as displayed text or silently changing
word-density/ASR/retrieval behavior. Trace native data/format/source linkage, exact
quote/span authority, renderer fresh verification and review/provider context before
any edit. Outline drafting recovery already exists; do not implement it again merely
because older roadmap bullets still list it.

## Latest continuation - frozen claims/rehearsal integration (2026-10-08)

Separate unsigned directory bundle:
.local/workspace-loop-package/app/win-unpacked/Presenter Copilot.exe.
Fresh PyInstaller Core and Electron44.1.0 directory builds pass. Frozen handshake
directly confirms schema20 and recurring-objection capability. All440 bundled Core
files match the isolated sidecar build;462 source/test inputs match the validated
freeze. Existing12 package artifacts remain byte-identical;4 new artifact receipts
bring the preservation set to16. Branch/base unchanged, dirty384; no staging, commit,
push, user-store migration, old-package overwrite or public release.

Actual packaged Electron/frozen Core GUI5 combined cases pass without renderer errors:
reopen disposable project;26-slide native claim preflight with20-row selection and no
inference; synthetic ended-Run coverage with20/6 paging;23 recurring groups with20/3
paging and original stable-slide navigation across reorder; explicit notes Save to
Revision3 records only the selected original finding/source/applied revision, leaving
the other occurrence unreviewed. Screenshots inspected. The ended rehearsals were
seeded through source Core with fixture capture; this package does not establish real
Run capture, model claim extraction/cache reuse quality or human rehearsal improvement.
The source129 GUI checks and1477 Core/295 desktop full check remain the current code
validation; no production code changed during packaging.

Packaged Settings acceptance confirms signed-out ChatGPT/account0/credential store
available and disabled decision Save for unconfigured OpenAI/ChatGPT choices. Fast
Decisions remains disabled by default. Codex0.153.4 pin/hash/license/notice pass.
Restricted-PATH startup smoke exit0 has0 sidecars before/after, no orphan/download.
OPENAI_API_KEY rechecked absent. Human OAuth/catalog/inference and live Fast Decisions
calibration/latency remain unaccepted; no ambient credentials imported.

Receipts/logs at .local/workspace-loop-package/integration-result.json,
settings.json, smoke.json, codex-bundle.json, source-freeze.json,
core-resource-receipts.json, artifact-receipts.json and preservation.json.
All owned handles66559/36362/23430/15932/15994 terminal; successful settings/smoke
command returned terminal0. Earlier harness module-path/paged-permutation/blocked
renderer method/preview/studio/metadata-key errors retained and corrected. The GUI
receipt contains5 combined checks, correcting the earlier progress-message count6.

New artifact SHA256:
- Electron executable: df79cf41afaa6c69a08a93b0e1fc8085b60ee14e590285121c53a0052e42d96e
- app.asar: 48b9fbab0b16fac9776baa1906c346c0f37d9f005c5258cdbf0712767a1f2f28
- frozen Core: 16f845d9c6d177bdbf659c42b849b3456b7e469e248b58baa1af32352ff4f82b
- Codex: 444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b

Substantial remaining Workspace scope includes richer conversation/voice ambiguity,
broader native/multimodal semantics and semantic rehearsal findings. Broader fidelity,
larger real GUI/performance, observed70% preparation and physical ASR/presenter/live
provider acceptance remain open. Signing/clean Windows validation accepted debt.
Schema19 packages stay historical and must not open upgraded stores. Goal active.

## Latest continuation - explicit recurring objection review (2026-10-08)

Run now offers Mark objection with an original user note. The Rehearsal inspector
groups matching note wording on the same stable slide across at least two distinct
ended rehearsals. Whitespace collapses only; case/punctuation remain distinct.
Repeated markers within one Run do not establish recurrence. Each occurrence keeps
its original quote, source revision/ordinal, independent disposition and applied
revision. Users select an original observation, navigate to its current slide and
prepare notes/rewrite through existing explicit Preview/Save. Saving one occurrence
does not approve or address the rest. This is explicit marked-note recurrence;
semantic similarity and automatically inferred audience objections remain open.

Dependency reasoning follows Run marker validation, database CHECK constraints,
debrief questions/cache fingerprint, stable snapshot mappings, review resolution,
RPC allowlists/examples and renderer ownership. Project schema20 transactionally
rebuilds run_markers, retaining original rows, bounds, FK cascade and index. Actual
schema19 migration/reopen/cascade and forced-failure rollback are tested. App schema2
is unchanged. Debrief algorithm m6-deterministic-v2 invalidates old cache fingerprints.
Current-schema tests/protocol examples are synchronized; forward-version fixtures use
PROJECT_SCHEMA_VERSION+1 to preserve forward-only rejection after the migration.
Old schema19 packages remain untouched; do not reuse them on upgraded project stores.

Inspection checks project/deck/current head, verifies original/current native
snapshots and checks the head again before returning. Latest ten ended Runs are
bounded to1000 objection markers each/10000 candidates, with truncation disclosed.
Groups page20; original previews contain at most5 observations and include the next
unreviewed one. Exact finding resolution reaches bounded original observations beyond
the ordinary300 findings/100-per-category display cap, preserving their review/save
authority. Replies held across revision changes cannot republish stale results.

Actual source Electron/Core/native GUI5 passes across26 slides/two Runs/reorder,
23 groups/20-3 paging, raw case-distinct notes, original selection/current navigation,
read-only draft then explicit notes Save/independent provenance, held real replies,
720x520 containment, unchanged inspection bytes and empty claims. Final screenshots
inspected. Coverage7 and Workspace117 regressions pass:129 GUI checks this phase.
14 new Core cases plus focused comparison/protocol regression22 pass. Final pnpm check
passes1477 Core/295 desktop, format/lint/types/mypy178; final build passes. Fixture
capture/model boundaries do not establish human microphone or model-quality acceptance.
Earlier fixture FK/permutation/version/SQL-lint/harness errors are retained in logs.

Preservation verifies458 prior inputs:438 unchanged/20 intended edits,4 new files,
462-input freeze,384 dirty paths, unchanged branch/base and12 prior package artifacts.
Receipts/logs: .local/repeated-objections/preservation.json, source-freeze.json,
check-final.log, gui/result.json, gui-final.log, coverage-result.json and
workspace-result.json. All objection-phase handles terminal; no staging/commit/push.

Separate fresh frozen integration is accepted in the newer entry above at
.local/workspace-loop-package.
PyInstaller Core and unsigned Electron44.1.0 directory builds pass; packaged workflow
GUI5/Settings/startup acceptance passes within the documented fixture scope.
Disposable synthetic sessions do not prove actual capture.
PW6 remains partial; semantic omissions/objection detection and measured human
improvement remain open. Larger real GUI/performance, broader fidelity, observed70%
preparation, live Fast Decisions and human ChatGPT OAuth/catalog/inference remain open.
Signing and clean Windows validation are accepted debt. Goal active.

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

Deck review now prepares a local paged inventory of every slide before inference,
shows native text availability/exclusions and the exact planned request count,
lets users select slides, and requires explicit disclosure acknowledgement.
prepare_claim_scan reuses one verified native inspection per page, never invokes a
provider or writes claims. Dense available native objects are split into overlapping
windows rather than omitted at the single-request6000-character limit. Greedy batches
contain at most8 distinct objects/6000 characters and fit the actual serialized12K
context budget with reserve; overlap preserves spans up to the existing2000-character
quote limit. Full-object SHA and Python code-point offsets bind each prepared window.

Dependency reasoning extends extract_claims with optional exact prepared spans while
preserving its previous whole-object requests, privacy routing, source-only disclosure
and human-confirmed save authority. Core checks window identity/hash/bounds, unique
quote presence in both supplied window and complete native text, and current revision/
privacy. Global quote offsets/SHA still refer to the complete object. Neither notes,
evidence, knowledge nor speaker/style content is forwarded. Local preflight and
extraction have60s main IPC allowance; provider task remains bounded30s. Native safe
text ceiling8000 and inventory limits remain explicit exclusions, not silent coverage.

Renderer executes prepared requests serially, retains completed batches for reviewed
resume, stops future requests on cancellation/error, discards held real replies and
clears acknowledgement before retry. Stopped requests may finish/be repeated on resume;
the UI discloses this. Fresh current native text verifies every returned quote/window
before display. Overlap duplicates are shown once. Candidate selection opens Purpose
on the exact slide, waits for current claim records, reuses an existing exact claim/
evidence, and resets individual approval on every selection. Revision/source changes
invalidate the prepared scan and handoff. No automatic claim or presentation save.

Final pnpm check1443 Core/280 desktop, format/lint/types/mypy176 and build pass.
34 focused cases include12 new scan cases:26-slide paging/single inspection, reported
unavailable objects, dense full-text coverage/quote binding, malformed prepared windows,
escaped serialized budgets, undisclosed-window rejection and real revision invalidation.
Final actual source Electron/Core/PPTX GUI7 checks pass: local preflight/disclosure,
stop/held reply/resume, read-only exact quote review/explicit Save/source SHA, existing
claim reuse/fresh approval, tampered quote rejection/retry,720x520 containment and actual
native revision invalidation. Model/ASR/picker boundaries are deterministic fixtures.
Screenshots inspected. Existing claim GUI6 and full Workspace117 pass without renderer
exceptions. Receipts/logs at .local/deck-claims/gui/result.json, workspace-result.json,
claim-regression.log, check-final.log, build-final.log and preservation-final.log.
Initial format and explicit loop-binding lint failures corrected without disabling
checks; earlier fixture/harness errors retained, final tests/GUI pass.

All447 previous inputs verified:437 unchanged/10 intended changes,4 new feature/test
files,451-input final source freeze. All12 prior package artifacts and branch/base
657b876739ff7a1cc5709a7e28e92ec2551b337e preserved; dirty373 paths. No staging,
commit/push/unrelated cleanup/public mutation. Owned handles43050/3583/36844/62559/
59708/34379/95667/8730/83860 terminal; final GUI command terminal0. Accepted native
canvas package remains untouched and predates both claim discovery continuations.

Next: incremental semantic refresh, broader native/semantic coverage, large-deck scan
performance/presentation of results, conversation/voice ambiguity and rehearsal finding
workflows, then grouped fresh package integration and broader fidelity/human acceptance.
This scans available native text across chosen slides, not complete multimodal semantics.
Live extraction quality/precision/abstention remains unmeasured. PW2 observed70%
preparation remains open. Process OPENAI_API_KEY rechecked absent; live Fast Decisions
inference/calibration/latency and official human ChatGPT OAuth/catalog/model inference
remain unaccepted. Physical microphone/ASR/presenter gates remain open. Signing and
clean Windows are accepted debt. Goal active.

## Latest continuation - reviewed native text claim discovery (2026-10-08)

Adds Find claim candidates in Purpose / Claim and evidence review. Users explicitly
choose1-8 current native text objects, up to6000 total text characters. A separate
native decision_text inventory includes read-only/multi-run text that ordinary
browser editing cannot edit; the editing target list and writer permissions remain
unchanged. The selected reasoning provider receives only selected object IDs/text,
not notes, project evidence, approved knowledge or speaker/style material. Existing
privacy routing and bounded ProviderExecutionService own disclosure and content-free
audit. This is a reasoning task, not an extension of finite Fast Decisions triage.

Dependency reasoning retains existing unique exact quote binding and explicit
save_claim review as persistence authority. Discovery returns up to12 unsaved
candidates under strict schema; unsupported object IDs, paraphrases, repeated or
ambiguous spans, duplicate pairs and malformed confidence/kinds are rejected.
Empty results are allowed. Core verifies current revision/native text/privacy before
provider use and after inference; no deck or claim write occurs during extraction.
Main grants this bounded30s provider task60s IPC time instead of the default3s.
Renderer ownership rejects delayed replies after navigation/revision/unmount and
validates returned quote identity. Choosing a candidate prefills the existing review;
an existing exact claim reopens its own ID/evidence and clears approval. Confirmation
and Save remain separate. Long text can be inspected in a disclosure without being
mistaken for an editable object or saving an overlong default claim.

Final pnpm check passes1431 Core/280 desktop tests, format/lint/types and mypy175
source files; final build passes. Fifteen new Core cases cover review-only binding,
content-free/source-only context, malformed output, privacy/revision races, remote
local-only rejection and real loopback strict JSON Schema/empty-result transport.
Source Electron/Core/PPTX GUI passes6 new workflows: noneditable dense native text,
explicit save/source SHA, existing claim reuse, actual native revision invalidation,
held real Core reply after navigation, tampered quote rejection/retry and720x520
review/dismissal. Model/ASR/picker boundaries are explicit deterministic fixtures;
no live extraction precision or calibrated confidence claimed. Screenshots inspected.
Full source Workspace regression passes117 workflows with zero renderer exceptions.
Receipts/logs at .local/claim-extraction/gui/result.json, workspace-result.json,
check-accepted.log and build-accepted.log. Initial full run1430 passed/1 failed because
the shared core.ready protocol fixture missed the new RPC; corrected the example,
all7 protocol tests and the complete final check pass. Earlier failure logs retained.

All440 previous source/test/config inputs checked:428 unchanged,12 intended changes,
including the shared protocol example. Five new feature/test files; the447-input
freeze additionally includes two preexisting README/icon inputs. All12 prior package
artifact hashes, branchcodex/production-readiness and baseSHA
657b876739ff7a1cc5709a7e28e92ec2551b337e preserved. Dirty369 paths. No staging,
commit/push/unrelated cleanup or public mutation. Owned handles92266/3170/94542
terminal; failed and successful logs retained. Preservation/source-freeze receipts
at .local/claim-extraction. The accepted native-canvas package remains untouched
and predates these claim changes; grouped fresh package integration remains needed.

Next: substantial full-deck semantic/claim coverage and incremental refresh,
conversation/voice ambiguity and rehearsal finding workflows, then grouped package
integration and broader fidelity/human acceptance. This feature covers explicitly
selected current native text, not notes/images/charts or automatic whole-deck coverage.
PW2 observed70% preparation gate remains open. Process OPENAI_API_KEY rechecked false;
live Fast Decisions inference/calibration/latency and official human ChatGPT
OAuth/catalog/model inference remain unaccepted. Physical microphone, ASR quality/
latency and real presenter preparation/rehearsal remain open. Signing and clean
Windows validation are accepted debt. Goal active.

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


## Latest continuation - fresh schema19 packaged acceptance (2026-10-08)

Previous turn was progress: named revision checkpoints and source GUI validation.
The old package predates layout/grouping and schema19, so a fresh frozen Core and
Electron app were required. Preserve prior packages and repository build config;
use isolated .local/revision-checkpoints/package output/config. The only source/test
change this turn adds optional packaged-exe launch to the existing checkpoint script,
with developer PRESENTER flags removed for packaged launches and separate output.
No new production behavior or dependency change.

Fresh PyInstaller sidecar 53207 exits0 (package-sidecar.log); schema19/checkpoints
and current grouping are included. Electron build/unpacked packaging 67337 exits0
(package-app.log), signing skipped explicitly. Builder fetches the pinned Electron
binary; no model download. Current-source full pnpm check 31090 exits0: 1338 Core
cases in 276.02s, 231 desktop tests, format/lint/types and mypy168 pass. No GUI build
was changed while owned acceptance ran.

Exact new unpacked executable passes packaged checkpoint GUI (76885, exit0,
packaged-checkpoints.log): three workflows cover metadata Save without deck/head
change, concurrent write rejection/reload/rename/remove, actual restart retaining
labels, exact baseline restore and 720x520 max-length containment. Frozen sidecar
imports/edits source and metadata normally; packaged launch has no deterministic
provider/capture flags. Native GUI 17654 exits0 (packaged-native.log): three workflows
cover layout insertion/application with fresh appearance acknowledgment, exact native-
reviewed Save and Undo, and manual native-reviewed Save/Undo. No renderer exceptions.

Additional owned packaged IPC/frozen-Core acceptance 89597 exits0 (packaged-groups.log).
Direct typed plans create two native shapes and group through nested earlier-step
references; native review Save commits exact proposed hashes. Returned created group
ID and geometry are verified from frozen inventory, then an ungroup plan saves exact
reviewed bytes. Grouped/ungrouped PowerPoint PNG hashes are identical
06e0942b020883b5fd9d4d5c07740c914e7bfca3c6160daadd29a8e22df15855;
two undos restore exact group head/hash and baseline. Inspectable script/receipts at
package/test-frozen-groups.mjs and package/frozen-groups/. This is direct typed-plan
integration, not packaged Copilot planning/model quality. Inspected packaged minimum
checkpoint image and grouped native slide; source shapes retain placement/appearance.

Packaged smoke passes; first smoke ran alongside owned checkpoint GUI and counted
one sidecar before/after, with no orphan. After all GUI runs ended, final smoke
(packaged-smoke-final.log) exits0 with 0 sidecars before/after and no orphan/model
download. Every owned handle in this turn is terminal. No installer, clean-machine,
account/model, signing or public-release acceptance; these artifacts are local unsigned
unpacked builds. Signing and clean Windows remain accepted debt.

package/artifact-receipts.json contains exact sizes/hashes and unchanged 401-entry
source/test freeze. All four artifacts unchanged after acceptance. New app.asar SHA
115c5f17e512f7f7cc83b5e02928b02317b14ed2481497fe5729f13718422d23;
sidecar SHA f93c1190a0e5fd7c2989d62198c8d990e9961e5deb0fc5b9af3840d61836fc94;
exe SHA d01ad22cfdf657d3d03320181d6fa5ee0f008cf61509cbf32d45ef8d23f1168d.
Bundled Codex remains exact prior SHA444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b.
Previous 401-entry source freeze differs only in checkpoint GUI launch support;
all 400 other source/test files preserved. Branch/base/325 dirty paths unchanged.
No staging/commit/push or prior artifact removal. Production goal stays active.

Next: remaining substantial authoring inventory and broader fidelity/integration;
prioritize actual live Fast Decisions and Sign in with ChatGPT acceptance when account
access permits, plus physical/human preparation/rehearsal. New package now provides a
current executable for those gates. Native/browser corpus fidelity, other specialized
proposal dialogs and live model quality remain open. Do not infer account/auth, quality,
latency/calibration or human readiness from these fixture/native receipts.


## Latest continuation - named revision checkpoints (2026-10-08)

Previous goal turn was progress: reviewed Copilot grouping/ungrouping. Current
inventory confirmed roadmap revision checkpoints were missing: history restores
immutable revisions but had no durable user labels. This continuation implements
that authoring workflow, preserving the dirty checkout and goal scope.

Dependency reasoning before edits: labels annotate immutable bytes, never create
new revisions or change current head. Schema 19 adds presentation_revision_checkpoints
with composite revision/presentation foreign key and cascade on source deletion.
One name/note per revision, up to 100 active labels per deck; 80-character single-line
name and 500-character note. UUID record tokens and BEGIN IMMEDIATE prevent stale
rename/delete. Removal writes a fresh-token tombstone (name NULL, note empty) to
reject stale null-token/ABA writes. Save requires current revision under the same
transaction; historical labels can be removed and renamed after restoring that
revision. Metadata writes invoke no provider, package writer or retrieval refresh.
Restore uses the existing revision restore/re-index workflow, preserving later
history and labels. Schema migration, protocol allowlists/examples and old-schema
fixtures updated; future-version fixture remains unsupported (20).

Core service and list/save/clear_checkpoints RPCs expose project-owned metadata.
History mounts RevisionCheckpoints keyed by project/document/current revision;
late replies are guarded by lifetime/generation, writes/actions lock during access,
and conflict reload keeps unsaved name/note. Labels are explicitly local; removal
keeps the original revision and its PPTX. Scoped CSS gives long names/notes and
buttons minimum-width/wrapping rules without changing other Workspace controls.

Twelve focused tests pass: exact metadata restart and unchanged package/head/history,
no provider runs, source-delete cascade, rename/token conflicts, clear/ABA rejection,
foreign ownership, invalid fields, changed-head rejection, row-preserving v18->19
migration and 100-active-label limit with removal/rename at capacity. Initial targeted
storage/protocol/historical-fixture run passes 56 cases. First persistence test caught
missing explicit commit: project_database closes without auto-commit; corrected.
A broad schema expectation replacement briefly changed three unrelated 18pt text
assertions; restored before verification. Initial mypy found project-ID input type;
now UUID-normalized before the storage path boundary. Initial full check stopped on
unused copied GUI global document; corrected.

Full pnpm check 28204 exits 0: 1337 collected Core tests pass in 298.51s, 231 desktop,
format/lint/types and mypy168. The additional active-cap test was added after that
collection; final checkpoint suite passes all 12 including it (core-final.log).
Core implementation unchanged during/after the broad run. Final Core lint/mypy pass.
Full Workspace 23169 exits 0 with 117 workflows/no renderer errors, copied
workspace-result.json. Its build predates final scoped checkpoint wrapping; final
build/type/lint/format and dedicated GUI cover that layout repair.

Owned Electron checkpoint GUI exits 0 (gui-final2.log, handle59188): three workflows
cover Save preserving exact package/head, concurrent write rejection without draft
loss, reload/rename/remove/resave, real close/relaunch retaining two labels, restore
of exact baseline revision/hash while keeping labels, and actual 720x520 maximum-
length label containment. Strong final check bounds section and every control to
viewport; minimum-window.png inspected and controls wrap/read correctly. Earlier
restart test reused a closed-window locator; corrected. Earlier resize selected a
hidden preview window; now selects renderer/index.html. Weak overflow-only check
missed clipping of long labels, found by screenshot inspection; fixed scoped layout
and strengthened bounds assertion. Diagnostic logs retained. No renderer exceptions.

All owned handles terminal: focused28178, initialtyping21170, renderer11272,
GUI52241/8079/56436/59188, fullcheck28204, Workspace23169. First GUI/lint failures
are retained, not acceptance. Source freeze .local/revision-checkpoints/source-freeze.json
has 401 entries: 18 existing changed, 379 preserved, four new files; none missing,
unchanged after final build/GUI. Branch/base unchanged: codex/production-readiness /
657b876739ff7a1cc5709a7e28e92ec2551b337e. 325 dirty paths; no staging/commit/push.
No package yet: previous outline-session frozen sidecar/app predates schema19 and
layout/grouping/checkpoint changes. Fresh sidecar and app required before packaged
acceptance. No account/model calls, downloads, signing or public release.

Next: substantial remaining authoring inventory, fresh packaging and fidelity/
integration acceptance. Named checkpoint gap is now locally closed. Broader renderer
corpus, real-model/human preparation/rehearsal, physical ASR/HUD, live Fast Decisions
and Sign in with ChatGPT remain open; signing and clean Windows are accepted debt.
Production goal stays active.


## Latest continuation - reviewed Copilot grouping (2026-10-08)

Previous goal turn was progress: native layout application/insertion acceptance.
This continuation closes a verified missing authoring feature: provider-planned
native grouping/ungrouping. Direct native writers were already implemented; the
planner schema and binding did not expose them.

Dependency reasoning before edits: provider picks only IDs, not preconditions.
Add group_objects (2-20 objects:[{object_id}]) and ungroup_object to the strict
provider schema. Transaction resolution resolves nested earlier-step object IDs;
Core binds each actual staged object's geometry and rejects duplicate/unavailable/
unsupported targets. Slide selection still governs scope; foreign-slide objects
cannot bind. Native writers retain top-level eligibility, connectors/dependencies,
geometry, native identity and package preservation. Group returns created_object_id
alongside selected_object_ids, enabling subsequent {created_by:N} ungrouping.
Existing operation metadata already allows this key. No RPC or migration change.

Core supplies review-only selected object names/text and ungroup target name;
Copilot lists them visibly with operation labels. Review does not grant writer
preconditions to the model. Original intent still retains creation references for
refinement; exact-byte review/save, re-index, discard, expiry and undo remain.
Deterministic fake provider adds two explicit GUI fixtures (create/position/group
callouts and ungroup); no live provider behavior is inferred.

Eight new Core tests pass: staged creation/group/ungroup, exact-byte save/undo,
review names/text, duplicate/forward/cross-slide/unselected/forged-precondition/
wrong-kind rejection and failed-plan cleanup. Initial targeted existing planner,
object-group/group-action suite passes 75 cases. Full pnpm check 5438 exits 0 with
1326 Core tests in 311.95s, 231 desktop tests, format/lint/types and mypy. This run
started before final review-only member data/display; those final Core changes
pass all eight grouping tests, lint/mypy167, and renderer types/lint/231 desktop
checks afterward. Initial check stopped on one fake-fixture long rationale;
shortened it (check.log retained). Full Workspace 62242 exits 0 with 117 workflows
and no renderer errors; workspace-result.json copied from owned run. Its GUI build
predates final member display; final native acceptance covers that display.

Final-rebuilt owned Electron/real-PowerPoint acceptance 47748 exits 0 with six
workflows and no pageerrors: new create/position/group, native-reviewed exact hash
Save; subsequent existing-group ungroup, exact hash Save; Undo restores the actual
grouping head/hash then baseline. Existing two layout, manual commit, held native
refinement and discard boundaries also pass. Earlier grouping GUI locator expected
label without appended slide; corrected. Later Undo test assumed revision2 despite
earlier Save/Undo consuming numbers; now waits actual revision number and verifies
full head identity/hash. Diagnostic logs retained.

Visual inspection found a redundant previous table/chart disclosure on group review;
removed it. Final types/lint/build pass; renewed native GUI 26431 exits 0
(gui-final3.log), six workflows and no pageerrors, with explicit absence assertion
and native slide screenshots. Inspected copilot-group-native.png (member names/text),
copilot-group-slide-native.png and copilot-ungroup-slide-native.png; visible content
and callout placement are preserved. All owned handles are terminal.
Other handles 36015/83794/88337/9690/5438/62242/95176/83096/47748/99944 are terminal.

Freeze .local/copilot-groups/source-freeze.json contains 397 source/test entries:
eight prior files changed, 388 byte-identical, one new Core test, none missing.
321 dirty paths; branch/base unchanged. Existing outline-session package predates
layout and grouping changes; changed Core means a fresh frozen sidecar is required.
No packaging, staging/commit/push/release, dependency or live account/model action.
Next: prioritize remaining substantial authoring gaps,
then fresh packaging/fidelity/integration. Live Fast Decisions/ChatGPT, physical/human
and broader corpus acceptance remain open. Signing/clean Windows are accepted debt.
Goal remains active.


## Latest continuation - PowerPoint layout review (2026-10-08)

Previous percentage-report turn was no progress; current state was revalidated.
Branch/base stay codex/production-readiness /
657b876739ff7a1cc5709a7e28e92ec2551b337e; 320 dirty paths retained.
Current layout inventory already supports unused master layouts, placeholder
remapping, insertion and paged comparisons; historical roadmap gaps are stale.
This continuation adds PowerPoint appearance to final layout-application and
native-layout insertion review, extending manual/Copilot proposed appearance.

Dependency reasoning: reuse the privileged immutable edit-plan snapshot pipeline;
no new Core writer, RPC, migration or provider call. The appearance target includes
project/document/baseline revision, plan ID, exact proposed SHA and slide ordinal.
Insertion renders slideNumber + 1; layout application renders the existing ordinal.
Only an open, matching draft owns that target; changed input removes ownership,
so late replies cannot become current pixels. Display changes reset image readiness
and acknowledgment; pending native rendering blocks review and Save. Native image
failure retains Browser fallback and requires fresh display/review. Existing
reviewed SHA commit, re-index, owned discard and whole-revision undo stay authoritative.
Comparison thumbnails remain Browser appearance; final native review is explicit.

Validation: types, lint, build, format and all 231 desktop tests pass. The extended
owned Electron/real-PowerPoint test exits 0 (gui-final2.log) with five workflows and
no pageerrors: insertion renders staged slide 2 and clears prior approval; layout
application clears approval across Browser/PowerPoint switching; both Save exact
native-reviewed package hashes and Undo restores baseline. Existing manual Save/Undo,
refinement with held real native reply and discard with delayed reply also pass.
Inspected layout-insertion-native.png and layout-application-native.png. Initial
GUI setup omitted the collapsed slide actions; corrected. An immediate checkbox
assertion needed to wait for React state; later Copilot image waiting needed to
allow its different image alt text. Earlier diagnostic logs retained.

Source freeze .local/native-layout-appearance/source-freeze.json retains 396 files:
NativeLayouts.tsx and test-native-edit-appearance.mjs changed, 394 byte-identical,
none missing. Core unchanged; prior full 1318-test Core evidence applies unchanged.
No fresh package yet: outline-session package predates this renderer change.
Full Workspace regression 54206 is terminal exit 0: 117 workflows and no renderer
errors (workspace.log and copied workspace-result.json). All owned handles are
terminal. Native handle 62504 exits 0; earlier native handles 96168/74727/6527
terminal failures.
Production goal remains active. Other specialized proposals/creation and layout
thumbnails still need fidelity/integration coverage; live Fast Decisions and ChatGPT,
physical/human acceptance remain open. Signing/clean Windows remain accepted debt.
No staging/commit/push/release, account/model call or dependency change.


## Latest continuation - durable outline drafting session (2026-10-08)

Previous goal turn was progress: native proposal commit/refinement and fresh package
acceptance completed. This continuation implements a substantial missing authoring
workflow: explicitly saved outline conversation survives closing and restart.
Production goal remains active; signing/clean Windows are accepted debt.

Dependency reasoning before edits: React-only ten-turn history disappears on modal
close; preserving it in project storage requires trustworthy original proposal and
request provenance, immutable branch request baselines, explicit user Save, and
optimistic record ownership. Avoid browser-local project content and provider-setting
restoration. Add schema 18 with presentation_outline_proposals (successful original
response/request bound to provider run) and presentation_outline_sessions (one saved
payload per project with UUID record token). Planning captures original provenance;
new get/save/clear_outline_session RPCs validate exact originals, original request,
parent ordering, exact captured baseline, draft provenance and citation IDs. User
content edits remain unnormalized in saved payload. Save uses BEGIN IMMEDIATE and
expected token; Clear writes a token-bearing tombstone so old/null writers cannot
silently replace a deleted saved copy. No deck/remote/provider action in storage RPCs.

OutlinePlanner offers Save drafting session, explicit Resume, Remove saved copy and
Reload. Project/lifetime generation guards discard late reads/writes, actions lock
during access and dictation/proposal, and Reload updates saved-copy ownership while
keeping temporary edits. Resume restores briefing/notes/branches and unsent refinement;
it does not change provider/account configuration. One saved session, ten turns,
bounded fields/content and 8 MiB payload. Original proposals remain local project
provenance after Remove saved copy; no claim that deletion purges provider history.

Validation completed: focused persistence/planning/storage initially 23 tests pass;
11 new tests including exact restart retention, provenance/request/citation/foreign-
project rejection, historical branch baselines after ancestor edits, clear/ABA conflict
and direct v17 migration preserving existing rows. Dedicated Electron script
apps/desktop/scripts/test-outline-session.mjs passes four GUI workflows using owned
temporary project and deterministic provider. Actual Electron restart restores three
branches, notes and unsent refinement; DB counters stay 3 provider runs/0 documents
through Resume, conflict/reload and Remove. Minimum-window controls wrap with no
horizontal dialog/workspace overflow; inspected saved/resumed/minimum screenshots.
First GUI failure was collapsed notes details; test now opens that user control.

Schema bump exposed historical migration fixtures and hard-coded version assertions.
Updated fixtures to remove v18 tables before constructing old schemas, expected
version 18, expected table inventory and unsupported future version 19, keeping row-
preservation checks. Shared protocol examples updated with new methods/schema.
Initial full pnpm check is terminal with 11 fixture/expectation failures and 1307 pass;
focused corrected migration/protocol checks pass (125-case run had 3 then-fixed
inventory/future/examples failures; follow-up nine pass). v7 workspace-source fixture
passes. Next full check stopped at formatting only; fixed that test formatting.

All owned handles are terminal. Fresh full pnpm check 41281 exits 0:
check-final2.log has 1318 Core tests passed in 291.60s, 231 desktop tests,
format/lint/types and mypy 167 sources pass. Full Workspace sweep 88747 exits 0
with 117 checks. Dependency review then found VoiceEditInstruction still used
busy alone; changed it to busy || sessionBusy so dictation cannot begin during
session access. Held real save reply test verifies dictation/session controls remain
locked until receipt. Types/lint/build/format pass after that one-prop guard; Core
unchanged since the full check. Five development session GUI checks pass.

Fresh schema-18 frozen sidecar build 99668 exits 0 (package-sidecar.log); new module
is statically imported by planning. Isolated unsigned unpacked Electron build 77634
exits 0 (package-app-final.log) after the save-lock guard, preserving earlier packages
and repository packaging config. Initial outline Electron build was superseded before
acceptance. Freeze 396 entries unchanged during/after final packaging. Receipts at
package/artifact-receipts.json: app.asar SHA
34430808858c9e144b9c30e17ccd3e3113df00c3aae667c9c4b8e2c56b625b1c;
sidecar SHA 7e8e8686093c60b74e2099a694d652e034f049a471ff85bd049d2045b5e37613.
Bundled Codex stays pinned to the prior verified byte/hash.

Packaged smoke exits 0 with minimal system PATH, exact new exe and bundled sidecar,
process count 0 before/after, no orphan/model download (packaged-smoke.log). Packaged
session script 90417 exits 0: five development workflows plus actual unpacked app
Resume/Remove through frozen schema-18 sidecar using a developer-seeded local session,
with developer provider flags removed from packaged launch. Stored conversation
matches seed exactly and DB counters remain 3 runs/0 documents. This proves local
storage/GUI integration, not live provider generation. Inspected packaged restored
image. No installer/clean-machine/signing/public-release or live account/model action.

Freeze .local/outline-session/source-freeze.json: 396 entries; previous 393 baseline
at before.json; 18 changed existing entries, 375 preserved, none missing; three new
files (Core outline_drafts.py, test_outline_drafts.py, GUI script). Branch/base
codex/production-readiness / 657b876739ff7a1cc5709a7e28e92ec2551b337e unchanged.
Previous native-preview package retained, predates schema 18; cannot reuse that sidecar
for these APIs. No staging/commit/push/release or live account/provider calls.

Next: inventory substantial remaining Workspace authoring/GUI features, then
fidelity/integration, live Fast Decisions and Sign in with ChatGPT and physical/human
acceptance. Native preview coverage outside manual/Copilot review remains partial;
saved canvas disclosure still needs qualification. Keep intermittent undo finding.


## Latest continuation - proposed-edit commit/refinement and packaged acceptance (2026-10-08)

Previous goal turn was progress: proposed native review was implemented and initial
GUI accepted. This continuation completes local save/refinement/discard and fresh
unpacked-package checks. Full production goal remains active; live Decisions,
ChatGPT sign-in, broad fidelity/integration, physical mic/HUD and human workflow
remain open. Signing and clean Windows are accepted debt.

Reasoned dependencies before edits: immutable plan reader -> native image receipt ->
review acknowledgment -> exact reviewed_sha256 commit. Refinement replaces the plan;
delayed successful replies must fail renderer identity, while discarded plan retries
must fail Core before Office. Saved head hashes and undo must match actual Core
receipts rather than screenshot inference. Added test-native-edit-appearance.mjs
using an owned temporary project, deterministic Copilot provider and real installed
PowerPoint. Main response is gated only after real worker/receipt validation, allowing
GUI refinement/discard while a successful old reply is pending. No provider or Office
implementation patch was required. Review checkbox disclosure now distinguishes
native PowerPoint pixels from experimental Browser appearance in both dialogs.

Terminal development acceptance (gui-acceptance.log): three compound workflows pass
with no page errors. Manual Save commits exactly the rendered SHA; Undo restores
original revision+SHA. Refinement while a real reply is delayed replaces plan ID;
old native frame is rejected, refined Save uses the newly rendered SHA, Undo restores
baseline. Discard closes the dialog before a delayed reply; no frame leaks into saved
view and direct retry of the discarded identity is rejected. Inspected native-reviewed
manual/refined screenshots; development receipts archived in gui-development.

Packaging inputs were traced: all 251 Core/spec source entries match the previous
frozen sidecar build, so reused that byte-identical sidecar rather than rebuilding
unchanged Python. Isolated electron-builder config writes a new unsigned unpacked
app to .local/native-edit-preview/package/app/win-unpacked, preserving previous package
and repository configuration. Build 71665 exits 0. New app.asar SHA:
e3d941283d9e5c7b502b8825c7ca16d2a6cc10adaf2088e30a2b84b0daccff8d.
Sidecar and Codex SHA/byte receipts match the prior artifacts. Freeze has 393 source
entries, none changed during or after build. This turn changes two review-disclosure
source files and adds the new GUI harness; all 390 previous other entries preserved.

Fresh-package terminal receipts under .local/native-edit-preview:
- packaged-smoke.log: exact new exe, bundled sidecar, minimal system PATH, exit 0;
  sidecar processes 0 before/after, no orphan, no model download.
- gui-packaged-commit.log (28114): actual frozen Main/worker native manual Save+Undo
  commits exact rendered package hash and restores baseline; no page errors.
- gui-packaged.log (41360): ten native GUI workflows pass, including proposed manual
  Browser/discard, all nine saved appearance regressions, selection bounds,
  edit/undo/redo invalidation, delayed navigation/Browser replies, failure/retry and
  minimum-window full-frame containment. No developer provider fixtures in package.
- package/artifact-receipts.json: four artifact hashes/sizes, base SHA and source
  freeze. Installer installation, signing, clean-machine and public release untested.

Types/lint/build/format pass after disclosure/harness changes. Last desktop tests
remain 231 passing and full Workspace sweep 117 passing; changes to product this
turn are disclosure only. Core unchanged; last full pnpm check remains 1307 Core
passed. All owned handles terminal. Branch/base unchanged at codex/production-readiness
and 657b876739ff7a1cc5709a7e28e92ec2551b337e. No staging/commit/push/release/live account
or provider calls. Keep previous intermittent undo finding visible.

Next: inventory substantial remaining Workspace workflows against current source
(especially durable outline sessions versus existing temporary conversation), then
broader fidelity/integration and live Decisions/ChatGPT and physical/human acceptance.
Native preview coverage outside manual/Copilot plan-review dialogs remains partial;
saved canvas status still says draft edits use Browser and needs qualification.


## Latest continuation - proposed-edit native appearance (2026-10-08)

Previous percentage-only turn was no progress; revalidated the saved-appearance
boundary and implemented the next substantial review workflow. Dirty worktree
preserved, branch/base unchanged. Goal remains active; no release or live provider
acceptance is claimed. Signing and clean Windows remain accepted debt.

Dependency reasoning: Core already owns immutable review packages and verifies plan
scope, active baseline, expiry and hash in open_edit_plan_preview. Reuse that reader
rather than expose a proposal path or add a Core export method. Main copies bounded
canonical-base64 chunks into its exclusive private file, verifies byte count/hash,
releases only its reader (EOF close is idempotent), then uses the existing isolated
native worker. After PNG validation it reopens/closes the plan reader to reject a
plan discarded, expired or made stale during rendering. Saved and proposed requests
share the Office serialization/owned cleanup boundary; saved receipt checks remain.

Implemented Main edit-plan-snapshot.ts and native-edit-appearance.ts, trusted IPC,
preload/protocol and plan-bound appearance hook. Both SlideEditReview and
CopilotEditPlan offer Browser/PowerPoint appearance for immutable proposed bytes.
Frame identity includes plan ID, baseline revision, package SHA and slide. Native
status explicitly says changes are not saved. Appearance changes clear acknowledgment;
saving waits for rendering and displayed-image readiness. Exact reviewed_sha256
commit gates remain unchanged. No Core implementation or worker changes were needed.

Validation so far: 231 desktop tests pass, including 10 new Main tests for streamed
copy, corruption, reader cleanup, exclusive destination and post-render discard,
and one new renderer identity test. Types/lint pass; latest format check passes including final GUI harness additions.
Real installed-PowerPoint manual proposal
image was inspected. gui-final4.log passes 10 native GUI workflows with no page
errors, including Browser switch/discard and all nine saved-appearance regressions.
Earlier gui.log/gui-retry/gui-final/gui-final2/gui-final3 stopped on harness selector,
UTF-8 encoding or asynchronous dialog-close waits; corrected without product patches
or relaxing rendering checks.

All owned handles are now terminal. Full Workspace sweep 70714 exits 0 with 117
checks (workspace.log). Dedicated native run 9765 exits 0 with 11 checks and no
page errors (gui-copilot-retry.log and native-appearance/gui-proposed/result.json).
Manual and deterministic Copilot proposal images inspected. Both render through
real installed PowerPoint before commit; image readiness gates save, Browser switch
clears acknowledgment, discard preserves baseline. The first Copilot run read the
checkbox before React's image-change effect; retry waited for the specified unchecked
state and passed. No product patch or weaker acknowledgment check was introduced.
No live model, OAuth, mic or packaged proposal acceptance is claimed.

Baseline .local/native-edit-preview/before.json has 389 entries; nine existing source
entries changed, 380 preserved, none missing, three new Main files. Current freeze
392 entries refreshed at source-freeze.json including the latest native harness addition.
Old isolated package remains intact and represents the preceding saved-preview build,
not these new proposal features. Next: complete delayed/replaced-plan/refinement
and native-reviewed commit acceptance, then current-source package proof,
then remaining authoring/fidelity/integration, live Decisions/ChatGPT and physical/
human gates. Keep the previous intermittent undo finding visible. Review checkbox
copy still calls the preview experimental even when native pixels are selected;
qualify that disclosure as Browser appearance in the next copy pass.


## Latest continuation - native appearance acceptance and isolated package (2026-10-08)

Previous goal turn was progress: implemented native saved-revision appearance,
found the navigation readiness race and measured real image clipping, and fixed
custom-page rounding for both native workers. This continuation completes local
native GUI and current-source unpacked-package acceptance. The full goal remains
active: substantial remaining authoring/fidelity/integration, live Decisions and
ChatGPT acceptance, human preparation/rehearsal and physical ASR/HUD gates remain.
Signing and clean Windows validation remain accepted debt.

Polled the exact carried handle 6679 to terminal success: all 117 Workspace workflows
pass with the inventory guard. The prior late undo failure (expected 52, stayed 53)
did not reproduce. Traced Core's expected-head and parent/child compare-and-swap
restore and the renderer refresh lifecycle; no undo patch or test relaxation was
made. Retain `workspace-layout-final.log` as an intermittent acceptance finding;
one subsequent pass does not establish its cause. The next full run on the corrected
grid also passes 117 (`workspace-grid-final.log`), including canvas selection,
dragging/resizing, revision history, authoring and keyboard workflows.

Built the pending minmax(0,1fr) canvas grid fix. Native image bounds now measure
237.328x178 CSS pixels within the 436x220 canvas at actual 707x460/DPR2 viewport;
the entire 960x720 frame is contained. The earlier image was 340.664x255.5 and clipped.
Dedicated native GUI passes nine workflows (`gui-grid-final.log`), including
selection/image bounds, edit/undo/redo invalidation, Browser/navigation late-reply
rejection, failure/retry and minimum-window containment. Inspected the corrected
small-window screenshot. The disclosure now explicitly qualifies Browser appearance
as experimental; it no longer describes native pixels as experimental renderer output.

Reviewed frozen-worker/package dependencies before action: CLI flags branch before
Core instantiation, spec statically discovers the preview module and already includes
pythoncom/win32com.client, Main resolves the bundled sidecar, and native GUI fixtures
must patch the actual app.asar module rather than development dist. The native test
harness now accepts PRESENTER_COPILOT_PACKAGED_EXE, leaves developer provider/ASR
fixtures out of packaged launches, and writes separate gui-packaged receipts.
No provider inference or microphone capture is exercised by this native test.

Built a fresh PyInstaller sidecar and unsigned unpacked Electron app into
`.local/native-appearance/package/`, preserving previous artifacts and repository
packaging configuration. Electron-builder fetched/extracted the pinned Electron
runtime; no model download occurred. Signing was skipped by configured policy and
Authenticode reports NotSigned. This is current-host unpacked-package evidence,
not installer installation, clean-machine, signed-release or public-release evidence.

Current terminal receipts under `.local/native-appearance/`:
- `check-final.log`: full pnpm check exits 0; 1307 Core tests pass in 284.80 seconds
  and 220 desktop tests pass. Formatting/lint/types and mypy (166 sources) pass.
  This supersedes the earlier 1299 run plus separate rounding sweeps.
- `package-sidecar.log` and `package-app.log`: builds exit 0. PyInstaller recorded
  an optional tzdata hidden-import warning; no native startup/import failure occurs.
- Frozen native preview and PDF workers both preserve the owned unsaved sentinel
  and already-open original, including count/save/text/global settings and source
  hashes (`frozen-preview-preservation.log/json`, `frozen-pdf-preservation.log/json`).
  The valid custom page size succeeds with the shared 1/16pt absolute tolerance.
- `packaged-smoke.log`: verified exit 0 using the explicit new unpacked executable,
  minimal system PATH and bundled sidecar; sidecar count 0 before/after, no orphan.
- `gui-packaged.log` and `gui-packaged/result.json`: all nine native GUI workflows
  pass through the packaged app and real frozen worker, with full-slide containment
  and no page errors. Inspected the packaged minimum-window screenshot.
- `package/artifact-receipts.json`: exe, app.asar, frozen sidecar and bundled Codex
  byte/hash receipts. Bundled Codex 0.153.4 matches pinned SHA
  444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b. The 389 source
  entries are unchanged during build; package input files/locks retain pre-build
  timestamps. The package is based on dirty sources, not a new reviewed commit.

All owned tool handles are terminal; none need resuming. Branch/base remain
codex/production-readiness / 657b876739ff7a1cc5709a7e28e92ec2551b337e. Source freeze
remains 389 entries. This continuation changed only the appearance disclosure and
native GUI harness among previously frozen sources; the other 387 are preserved.
README/ROADMAP and readiness/handoff documentation updated separately. No staging,
commit, push, account/model call, installer run, signing or release occurred.

Next: prioritize substantial remaining Workspace authoring/review workflows against
the actual implementation (older historical missing-feature lists are stale), then
broader browser/native fidelity and integrated acceptance. Saved native appearance
does not add native rendering of proposed edits; proposals still use browser preview.
Keep the intermittent undo finding visible. Real Decisions access/calibration/latency,
live ChatGPT sign-in, physical ASR/HUD and human preparation/rehearsal remain open.

## Latest continuation - saved-revision PowerPoint appearance (2026-10-08)

Implemented an explicit Workspace appearance choice: Browser appearance or
PowerPoint appearance for the selected saved revision and slide. The native image
comes from installed Windows PowerPoint, while draft edits continue using browser
preview. Native mode is an additional capability; browser fidelity and broader
platform/integration acceptance remain open. Signing and clean Windows remain debt.

Dependency chain reviewed before edits: current Core revision -> Main-owned private
PPTX copy -> isolated one-shot native worker -> checked PNG receipt -> preload ->
revision/slide-bound renderer image -> existing semantic selection overlay. Main
accepts identity fields only, verifies the immutable copy receipt and bounds image
dimensions/bytes/hash. Python preflights the existing active-content/external URI
guard before opening; it closes only its private presentation, changes no Office
global settings and never calls Quit. Worker timeout/child shutdown reuse the PDF
worker boundary with an explicit preview mode; PDF defaults remain unchanged.
Locked owned temporary files can remain after timeout; other Office files/processes
are not cleaned up or terminated.

The renderer checks project/document/revision/source hash/slide identity, owns and
revokes blob URLs, rejects late results on navigation/unmount or Browser selection,
and displays native status only while an identified native image is shown. Rendering
is explicit, serialized, and retryable through the same choice; image decode failure
restores browser availability. The geometry overlay still uses Core's editable
object inventory rather than deriving objects from pixels.

Current receipts under `.local/native-appearance/`:
- Desktop suite: 220 tests pass, including after the layout correction; Main copy/receipt/PNG cleanup and renderer identity
  cases included. Types, lint, mypy (166 files) and desktop build pass.
- Focused worker/PDF/Office ownership suite: 44 pass. Installed Office exposed
  0.025pt page-size rounding on a valid custom fixture; the new appearance worker
  now permits only 1/16pt absolute error with zero relative tolerance. Four added
  rounding/boundary cases plus the worker cases pass (14 latest focused tests).
  The final combined native/PDF/ownership sweep passes 48 tests.
  A real PDF probe reproduced the same rounding rejection. PDF and preview now
  share NATIVE_PAGE_TOLERANCE_PT (1/16pt, zero relative tolerance). Four PDF boundary
  tests were added; the final focused combined sweep passes 52 tests. The isolated
  real PDF worker succeeds on the custom fixture while preserving the owned unsaved
  sentinel and already-open original (`pdf-custom-rounding-final.log` and separate
  `pdf-session-preservation.json`). Initial rejection log is retained. Source
  hashes/counts and exported PDF validation remain unchanged.
- Full Core run: 1299 pass in 334.82 seconds; it collected before the four additional
  rounding tests and worker tolerance adjustments. The separate final 52-test
  combined sweep validates those final changes; do not describe the full run as
  1307. Final ruff and mypy (166 files) pass for both native modules.
- Actual Electron/Main/Core/native worker GUI passes basic saved slide 1/2 render,
  Browser switch and navigation invalidation (`gui.log`). These use real installed
  PowerPoint, with only picker/model/ASR fixtures. Initial small-window screenshot
  captured the top of the editor; extended checks will scroll to the native controls.
- Isolated real preview worker preserves an owned unsaved sentinel and already-open
  original, including text/save/count/global settings and original/private hashes
  (`session-preservation-final.log/json`). Its initial strict-size failure is retained.

The extended native GUI run passed nine checks (`gui-acceptance.log`), including
GUI-created text-box edit/undo/redo invalidation, native object selection bounds,
delayed real replies after Browser/navigation, and failure/retry. The first full
Workspace regression passes all 117 workflows (`workspace-regression.log`).
Visual inspection then found controls inside the fixed-height dark canvas, crowding
the image and status. They now render above a dedicated inner canvas; outer keyboard
handlers remain and the image/SVG overlay share the same positioned inner parent.
The repeat native test exposed an actual readiness race: renderSlide clears and
asynchronously replaces activeSlideId without setting loading. A quick native click
could precede the inventory and be discarded when its key remounted. The native
target is now gated on a verified activeSlideId and slide dimensions, in addition
to existing source/revision guards. Types pass for this final guard.

Final inventory guard passes all nine native GUI checks (`gui-inventory-final.log`),
with actual 707x460 CSS viewport at DPR2 for the requested 720x520 native window.
The status/controls are now visibly readable above the canvas. Further visual review
found real image clipping: final native image measured 340.664x255.5 CSS pixels
inside a 436x220 canvas (`gui-frame-bounds.log`, assertion fails). An implicit grid
row expanded beyond the fixed canvas; the source now constrains both canvas grid
tracks with minmax(0,1fr). The dedicated GUI test now checks complete image containment,
in addition to overlay equality. This last CSS fix is not built/accepted yet.

The second full Workspace regression is terminal exit 1: a late multi-revision undo
sequence expected revision 52 but stayed on 53 (`workspace-layout-final.log`, script
line 7861). Earlier unchanged workflow run passed 117. No speculative undo patch or
test relaxation was made. A fresh run with the final inventory guard (before the
last CSS fix) is live, handle 6679, `workspace-inventory-final.log`. Poll this exact
handle; do not restart on observation timeout or rebuild while its app is running.
All other handles are terminal. After it finishes, inspect whether the undo failure
recurs, build the current CSS, and rerun native GUI image containment/selection.
Then rerun the full Workspace workflow on that built canvas fix as appropriate.
Do not count the earlier 117 pass as final layout/undo acceptance. Earlier selection
timeout used a slide with no editable geometry; the fixture now creates a text box
through the GUI. Undo/redo changed the active slide; the test derives current ordinal
from the actual image rather than assuming it remained slide 2.

Source freeze checkpoint: 389 entries, 372 preceding entries unchanged, ten
existing files modified and seven files added (`source-freeze-check.json`). Dirty branch/base
preserved; no staging/commit/push, live account/model calls, packaging or release.
Next: finish extended GUI and regression evidence, inspect the native controls at
minimum window size, then continue substantial authoring gaps and fidelity/live
integration, Decisions calibration/latency and actual ChatGPT sign-in acceptance.

## Latest continuation - gradient fidelity experiments and native preview dependency review (2026-10-07)

Previous continuation was progress: Office ownership fixed and a fresh corpus
refresh completed. This continuation produces further native evidence that
changes the next implementation decision; no speculative renderer patch ships.
Source freeze remains 382 entries unchanged (`.local/fidelity-gradient/before.json`
and `source-freeze-check.json`). Dirty branch/base retained. No staging, commit,
push, account/model calls, app build or package/release. All tool handles are
terminal. Only diagnostic fixtures/scripts/images plus these docs changed.

Traced source OOXML -> renderer linear gradient parser -> SVG endpoints -> native
PowerPoint pixels. The current dependency drops `a:lin@scaled`; its shape endpoints
use independently scaled width/height sine/cosine offsets. Source airline slides
2/3/4/21 explicitly use `scaled=0`. A preview-only angle compensation experiment
improves MAE by about 0.608 percentage points on these slides, but does not restore
native extent. A projected-extent DOM experiment improves those slides by about
0.69 points. Changing color interpolation to sRGB further improves the airline
example, but the controlled native red/blue fixtures disprove applying that as
a general fix. No dependency files, package manifests/lockfile or renderer files
were modified; no pnpm patch was started/committed.

Eight controlled native gradient slides cover cardinal, 30/70-degree, scaled and
unscaled, and opposite-quadrant directions; a second package removes theme shape
style references to isolate the direct fill. Both open/render twice in installed
PowerPoint via the guarded private-copy validator. Retained native/browser/DOM
experiment grid inspected (`fixture-native-browser-experiment.png`). Default
browser MAE remains 2.29-7.54% for the first fixture; the no-style fixture gives
similar values. Explicit geometry corrections improve some cases but regress
30/210/340-degree cases: 30 degrees goes 2.4718% -> 4.2177%, for example. This
is why a geometry-only or sRGB-only patch was not shipped.

To isolate geometry from nonlinear native color progression, inverted the native
cardinal red/blue profile and fit a plane on the other native captures. At 960x540,
unscaled 30/70-degree fills measure approximately 29.989/70.004 degrees with
extents 1099.612/834.234 pixels; scaled 30/70 measure 45.732/78.435 degrees with
extents 1054.9/720.354 pixels. Native extents agree closely with corner projection
along the measured direction. Scaled direction on this installed PowerPoint
behaves as inverse aspect scaling, unlike the simple width/height multiplication
in the [SDK description](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.lineargradientfill.scaled).
Treat this as observed installed-Office behavior, not a universal version claim.
The color progression differs even on cardinal gradients; native red/blue center
is 186/186, and intermediate weights differ materially from SVG linearRGB.
No empirical transfer function has been accepted as a general renderer rule.

Receipts in `.local/fidelity-gradient/`: angle-experiment.log, projected-preview,
srgb-preview, fixture-before.log/result.json, fixture-no-style.log/result.json,
fixture-geometry-preview and the inspected comparison grid. The PPTX skill's file
validator passes the original controlled package (`fixture-validation-final.log`).
It initially lacked defusedxml in Core and bundled Python. A pinned defusedxml
0.7.1 uv overlay supplied that validation dependency; repo dependencies and lock
files remain unchanged. This is local diagnostic/package validation, not product
or broad fidelity acceptance. Corpus originals remain unchanged; derivatives
remain local research artifacts.

Next implementation candidate: a user-selected, revision-bound PowerPoint appearance
preview reusing the existing immutable revision-copy boundary and owned native
worker/preflight. Dependency review has located Main savePresentationPdf,
runPdfWorker, trusted renderer sender checks, presentation-preview host messages,
and the isolated screenshot/semantic-candidate path. Native PDF export is already
present; it does not currently supply workspace preview pixels. Any new mode must
verify exact revision/source hash and slide number, bound PNG bytes/dimensions,
fence stale requests after revision/project/slide changes, close only owned native
copies, and keep proposed-edit preview clearly separate from saved-revision native
appearance. Do not silently fall back and label browser pixels native. Preserve
browser availability and keep browser fidelity, supported-platform and integration
acceptance open; native mode is additional product capability, not replacement
acceptance for the original goal. Signing/clean Windows remain accepted debt.

## Latest continuation - Office corpus ownership and fresh fidelity evidence (2026-10-07)

Before further native fidelity acceptance, traced the corpus validator shared by
roundtrip and preview comparison. Its previous DispatchEx path changed global
WindowState/DisplayAlerts/AutomationSecurity, opened original paths directly and
called Quit. DispatchEx is not proof of an isolated Office application. The
validator now opens unique byte-checked private copies, preflights active content
and external/undeclared URI relationships before opening a copy, closes only
that copy, leaves application settings alone and never calls Quit. Source/copy
hashes and native slide counts are checked. Label/rights metadata is preserved;
content or source changes fail closed. Temporary cleanup errors can retain owned
files when Office locks them; no source or other presentation is deleted.

Real installed-PowerPoint validation found an additional lifecycle bug: pywin32
skips nested CoInitialize on its main initializer thread, so CoUninitialize in
validator close disconnected the caller's COM objects. Diagnostic checkpoints
proved original/sentinel state unchanged through open/render and disconnected
only on apartment release. Native ole32 CoInitializeEx now acquires a separate
reference, including S_FALSE success, and close releases that reference exactly
once. Failed DispatchEx releases the owned reference; failed apartment init does
not release someone else's. This is confined to acceptance tools; the isolated
native PDF worker, product IPC and renderer are unchanged. Primary references:
[pywin32 main-thread initialization implementation](https://github.com/mhammond/pywin32/blob/main/com/win32com/src/dllmain.cpp)
and [Microsoft COM reference balancing](https://learn.microsoft.com/en-us/windows/win32/api/objbase/nf-objbase-coinitialize).

Receipts under ignored `.local/office-fidelity/`:
- Forty focused ownership/roundtrip/native PDF tests pass. Cases include native
  initialization success/S_FALSE/failure, DispatchEx failure, release idempotence,
  no global property writes/Quit, unique copies, export/close/hash failures,
  active content and undeclared URI rejection before opening.
- Installed PowerPoint preservation passes (`session-preservation.json` and
  `session-preservation-final.log`): an owned unsaved sentinel and already-open
  original fixture remain open with identical saved flag, text hash, slide count,
  presentation count and global settings after open, PNG rendering and release.
  Original bytes are unchanged. Initial failures are retained in diagnostic logs.
- Fresh 22-slide pinned airline corpus baseline compares browser preview against
  two native captures, with no native instability. All 22 slide MAE values match
  the Oct 2 baseline exactly; differences remain on every slide. Retained local
  native/browser images and inspected `airline-current/worst-six.png` expose
  substantial text/layout and gradient differences. Slide 21 MAE is 12.1435%,
  slide 18 8.6109%, slide 3 8.3503%, slide 19 7.5176%, slide 12 6.621%.
  A fresh baseline/all compatibility A/B also has identical metrics for all 22
  slides (`baseline-preview.log`); current compatibility passes do not explain
  these differences. These are diagnostic measurements, not fidelity acceptance.
  Corpus derivatives
  remain local research evidence, not a redistribution/publication permission.
- A blank-paragraph DOM experiment produced no pixel change; live DOM inspection
  showed existing line boxes. Removed all four experimental source/test edits
  and verified their hashes exactly match the preceding freeze. No speculative
  renderer fix remains. The diagnostic scripts/results stay under ignored .local.
- Final full Core sweep: 1289 tests pass in 409.10 seconds
  (`core-all-final.log`). The earlier pre-COM-fix full run passed 1285; it does
  not substitute for this final sweep.
- Fresh full 33-record preview refresh is terminal (`preview-all-current.json`):
  28 compared decks / 563 slides; two external-relationship skips; three
  POWERPOINT_ACTIVE_CONTENT_BLOCKED failures, so CLI exits 1. The blocked
  records 5789785, 7761240 and 1287949 have embedded OLE content types (35/1/10
  embedded parts), with no VBA/ActiveX content types. They were blocked before
  native opening; the new guard was not weakened. This differs from the older
  31-deck / 613-slide run that did not enforce the same preflight. No COM release
  failures and no application Quit. All 563 compared slides have stable pixel
  differences; 15 also have unstable native regions masked by the existing
  comparator. Completion of captures is not fidelity acceptance.
  `worst-corpus-slides.json` ranks the current gaps: airline slide 21 (12.1435%
  MAE), Philippine precolonial slides 19/2 (11.383%/11.1943%), Durand slide 5
  (11.0296%). No full-corpus images retained; the airline diagnostic images
  remain local. All validation handles launched for this continuation are
  terminal; no live handles need resuming.
- Restored desktop suite: 211 tests pass; renderer source bytes are unchanged.
  Types/lint/format checks pass. Core mypy: 165 source files; ruff checks pass;
  all 248 Python files formatted. No build, GUI sweep or packaging was needed for
  the final tools-only change; earlier 117 GUI and current SIWC evidence stay
  separate.

Source freeze (`source-freeze-check.json`/`source-freeze.json`): 382 entries;
379 preceding entries unchanged, only the two Office tools changed, one ownership
regression test file added. Dirty branch/base retained. No staging/commit/push,
account or model calls, download/install, package/release occurred. The preview
CLI retains legacy powerpoint_quit_failed=false and records the actual release
failure separately. Roundtrip release failures now also return nonzero. Existing
pixel comparison masks, tolerances and metrics were not changed. Native COM calls
still lack a per-call worker timeout in these older acceptance CLIs; a successful
comparison does not prove timeout recovery.

Next: investigate airline slide 21 text/gradient fidelity and the ranked
Philippine/Durand corpus gaps using retained/captured native evidence, then
broad fidelity/integration, real preparation/rehearsal/hardware/ASR/provider,
native Decisions calibration/latency and live SIWC acceptance. Native Decisions
still needs a configured API credential. Signing and clean Windows validation
remain accepted debt. Goal active.

## Latest continuation - ChatGPT sign-in Settings draft ownership (2026-10-07)

Reproduced the actual GUI sequence in a disposable Electron profile: choose
ChatGPT plan usage, click Continue with ChatGPT, then let its status refresh/poll
run. Before the change, the picker returned to Disabled and Cancel sign-in
vanished. The inspected `before.png` and `reproduce.log` retain that failure.
The original sequence now retains the selected provider and Cancel control.

Dependencies were traced before edits: saved Core decision configuration -> first
Settings hydration -> separate unsaved provider/Ollama/ChatGPT model draft ->
authentication status/catalog refresh -> account-scoped model revalidation ->
explicit Save. Status updates keep the user's draft; the first load alone
hydrates saved provider/loopback model fields. A model choice survives catalog
failure on the same account and is restored on retry, but a successful changed
catalog removes unavailable choices. Changing the active account chooses a valid
saved/default model for that account instead of carrying the previous account's
draft. Empty/unavailable catalogs keep Save disabled. Closing/reopening Settings
still loads saved Core settings; this is temporary form state, not durable draft
storage. Authentication does not select a decision provider automatically.

Status loads are fenced by request generation and component lifetime. A stale
status reply is discarded before another catalog request; stale catalog results
are discarded before they can replace account/model availability or fields.
Polling skips an outstanding status load or decision/account action. Actions
invalidate earlier polls and use a synchronous guard against duplicate dispatch.
Cancellation/sign-out refreshes therefore cannot be reversed by an older poll.
Core authentication, tokens/credential storage, provider inference, IPC/schema,
privacy and account registration contracts are unchanged. Only the Settings
component, a small draft merge helper/tests and a dedicated GUI script changed.

Validation under ignored `.local/chatgpt-settings/`:
- 211 desktop tests pass (six new account/catalog/draft merge cases); types,
  lint, formatting and build pass. The build retains its existing bundle-size
  advisory.
- Seven current Core ChatGPT authentication tests pass. All Core bytes match the
  preceding source freeze; the preceding full 1277-test sweep was not rerun for
  these renderer-only changes.
- Original GUI reproduction now passes (`after.log`). Final dedicated GUI:
  seven workflows pass, no renderer exceptions (`gui-final.log`, `result.json`).
  It verifies immediate and recurring refreshes, provider/Ollama edits during
  sign-in, model retention, catalog failure/retry, account-switch revalidation,
  explicit-only Save, serialized pending polls and a late reply after cancel.
  At 720x520 it clicks Continue/Cancel and measures Cancel within the viewport,
  with no horizontal overflow. Full and minimum-window screenshots inspected.
- The existing provider GUI regression passes (`providers-gui.log`), exercising
  real Core local-provider configuration/inference/persistence and the credential
  boundary with its synthetic loopback server. The preceding 117-workflow full
  workspace sweep remains separate; it was not rerun for this localized change.
- The dedicated test uses real Electron/local Core and validated IPC, replacing
  selected auth/status/catalog/configuration replies only inside its disposable
  client process. No browser authorization, real sign-in, account mutation or
  model inference is performed by this fixture. Early harness issues (module
  loading, wrong initial window, first-run walkthrough, exact label matching and
  Electron evaluate's callback argument position) were fixed; logs retain the
  initial product reproduction and final success. Live SIWC remains unverified.

Dirty branch/base remains `codex/production-readiness` /
`657b876739ff7a1cc5709a7e28e92ec2551b337e`. The 381-entry source freeze preserves
377 preceding entries unchanged, changes only ReasoningProviders.tsx and adds
three helper/test/script files. No staging, commit, push, download/install,
packaging or release occurred. No live process handles remain.

Next: guard the older PowerPoint corpus validator's shared-instance assumption
before new Office fidelity acceptance; it still changes application settings and
calls Quit, unlike the newer PDF worker. Native Decisions live access, calibration
and latency need a configured API credential (last read-only probe unavailable).
Richer drafting/voice ambiguity, broad fidelity, real preparation/rehearsal/
hardware/ASR acceptance, live SIWC and exact-source packaging remain open.
Signing and clean Windows validation remain accepted debt. Goal active.

## Latest continuation - native OpenAI Decisions beta (2026-10-07)

The previously pending OpenAI Decisions contract is now published. An opt-in
`openai_decisions` adapter uses GPT-6 Luna at `POST https://api.openai.com/v1/decisions`.
It appears separately from Responses Fast/Ultrafast and ChatGPT plan usage.
The existing OpenAI API credential is resolved on each call; ChatGPT plan tokens
are not reused. No SDK upgrade, install, account call or live model inference
was performed. The fixed HTTP transport does not follow redirects or retry;
it bounds response bytes and closes its owned connection.

Dependencies were traced before edits: existing provider selection -> Core
factory and API credential -> project Local Only/cloud acknowledgement checks ->
immutable bounded selected slide/claim state -> native named choice questions ->
complete validated typed answers -> existing content-free run manifest and
review/abstention workflow. Native arrays are mapped to the shared choice model;
confidence remains separate from the complete probability distribution. Boolean
labels, unexpected/duplicate names, unknown labels, nonfinite/invalid scores,
malformed or oversized responses and duplicate JSON keys are rejected. Any
question refusal rejects the whole proposal. No decision is automatically
persisted and no deck mutation occurs. Existing providers/defaults are retained.
Settings discloses beta/API-key/cloud permission and uncalibrated confidence.
An initial status-loading race was found while checking save/reload; the decision
picker now waits for its first status before accepting user selection.

Validation under ignored `.local/openai-decisions/`:
- Final full Core sweep: 1277 tests pass (`core-all-final.log`); preceding sweep
  1273 passed before the added native privacy and transport cases. Native tests
  use exact documented wire fixtures, not live model responses. Core ruff,
  formatting and mypy pass (165 source files).
- Final desktop sweep: 205 tests pass. Types, lint, formatting and build pass.
- Bounded provider GUI passes (`gui-final.log`), including the new native option,
  explanatory copy and saving disabled without an API key. A separate fresh
  synthetic-key GUI saves and restores the selection after reload, invokes no
  fixture inference and passes (`native-gui-final.log`). Its 720x520 variant
  reports 707px content/document width and selector bounds 249..639px with no
  horizontal overflow (`native-gui-small.log`). Full/small screenshots inspected.
- Final rebuilt full workspace GUI: 117 workflows pass, no renderer exceptions
  (`workspace-gui-final.log`, `workspace-gui-result.json`). This exercises the
  current Electron/local Core with deterministic fake ASR/providers and a
  disposable profile. It does not prove physical microphone or live model/account
  acceptance. The preceding sweep reached the final Settings assertion and
  failed because its expected list omitted the native option; that list is fixed.
- Initial harness failures: oversized pytest fixture ID exceeded Windows'
  environment-variable limit; short fixture IDs fixed it. Existing consent code
  and manifest metadata-key expectations were corrected to verify the actual
  contract and absence of raw text. Early save/reload exposed the initial
  Settings-loading race; the picker now waits for its first status. Logs retained.
- Current read-only credential metadata probe reports no OpenAI API credential.
  No live account/model call, download/install, staging, commit, push, packaging
  or release occurred. Native access, quality/calibration/latency remain open.

The 378-entry source freeze preserves 367 preceding files unchanged, changes nine
intended existing source/test/script files and adds two native adapter/test files.
Branch/base remain `codex/production-readiness` /
`657b876739ff7a1cc5709a7e28e92ec2551b337e`.

Next dependency findings: ChatGPT sign-in status polling currently resets unsaved
provider/model fields; preserve draft Settings selection through that workflow.
Before fresh Office corpus acceptance, address the older corpus validator's
assumption that DispatchEx creates an isolated PowerPoint instance: it still
changes global application settings and calls Quit. The newer PDF worker already
preserves shared Office state. No corpus automation was run in this continuation.

Official contract checked 2026-10-07:
- https://developers.openai.com/api/docs/guides/decisions
- https://developers.openai.com/api/reference/typescript/resources/decisions/methods/create

Dirty branch/base and preceding work remain preserved. Remaining gates include
richer drafting/voice ambiguity, broad PPTX fidelity, real preparation/rehearsal/
hardware and ASR acceptance, native Decisions account access, quality/calibration/
latency, live Sign in with ChatGPT and exact-source packaging. Signing and clean
Windows validation remain accepted debt. Goal active.

## Latest continuation - restorable outline conversation (2026-10-07)

The Copilot outline planner now retains up to ten successful drafts within its
temporary dialog conversation. Each turn shows the submitted instruction and
parent draft. Users can restore an earlier draft with its manual title/points/
notes edits, original provider run/evidence quotes and captured objective,
audience, briefing and requested slide count. Restoration clears the pending
refinement and makes no provider call. Refining an earlier draft appends a branch
without erasing its descendants. Failed requests preserve edits and history.
At the cap, further proposals stop while restoration/final review remain available.
Closing or switching modes clears this temporary history; a durable drafting
session is not claimed. Final native creation still requires explicit outline review.

Dependencies were traced before edits: selected draft + current briefing ->
existing propose_outline -> validated response -> immutable request/baseline and
original-response snapshots -> independently edited draft -> explicit final
review -> existing native creation with the selected originating run ID. The
before/current comparison uses the exact edited draft sent for that request;
later ancestor edits cannot rewrite it. Title, rationale, points, notes, evidence
references and added/removed positions are compared. Position-based comparison
does not infer stable identities for moved planned slides. Current manual edits
are included and disclosed. Provider/Core/IPC/schema/packaging code is unchanged;
each refinement sends the current briefing, selected edited draft and new
instruction under existing privacy/context budgets. Historical provider text
retains its existing untrusted-data status. Restore controls lock during local
dictation and provider work, duplicate submissions are guarded synchronously,
and project generations ignore late replies. Structured Core errors remain visible.

Validation under ignored `.local/outline-conversation/`:
- 205 desktop tests pass, including nine new snapshot/provenance/branch/bounds/
  comparison cases. TypeScript, lint, formatting and build pass. Initial type
  failures were test-fixture unchecked indexes; final types pass after explicit
  non-null assertions for those known one-slide fixtures.
- Seven current Core planning tests pass. Core bytes remain unchanged from the
  preceding 1249-test full sweep; it was not rerun for these renderer edits.
- Final rebuilt Electron/local Core sweep: 117 workflows pass, no renderer errors
  (`gui.log`, `gui-result.json`). The new flow retains manual edits after an
  invalid-prior-outline request, locks restoration during dictation, restores
  original briefing/context, branches from draft 1 while retaining draft 2,
  compares captured baseline wording, then explicitly creates the reviewed
  editable native deck. Deterministic ASR/provider fixtures do not prove live
  inference, physical microphone or human preparation acceptance. Optional native
  PDF checks remain in their separate preceding receipt.
- Fresh minimum-window acceptance: three workflows pass, no renderer errors
  (`small.log`, `small-result.json`). At 720x520, long unbroken request/point text
  wraps in history/comparison without horizontal overflow; ten successful turns
  preserve the first manually edited draft and final review at the cap. Closing/
  reopening resets the planner. Source inventory proves no deck was created by
  these actions. `small-comparison.png`, `small-restored-history.png` inspected;
  `restored-history.png` retains the full-sweep state.

Dirty `codex/production-readiness` / base SHA
`657b876739ff7a1cc5709a7e28e92ec2551b337e` remains preserved. The 376-entry
source freeze/audit covers 370 preceding files unchanged, three intended existing
changes (planner, scoped CSS, full GUI script) and three additions (conversation
state/tests, bounded GUI script). No staging, commit, push, account/model call,
download/install, packaging or release occurred. Durable history is a future
enhancement. Remaining gates include richer drafting and voice ambiguity,
broad PPTX fidelity, live provider and real
preparation/rehearsal/hardware/ASR acceptance, Fast Decisions calibration/latency,
live Sign in with ChatGPT and exact-source packaging. Signing and clean Windows
validation remain accepted debt. Goal active.

## Latest continuation - focused push-to-edit (2026-10-07)

Hold Ctrl+Shift+Space in the selected-text editor, Copilot edit dialog or outline
planner to dictate locally. Release Space, Control or Shift to review. Early
release waits for capture startup. Escape, window blur, document hiding and
editor-context disposal cancel an unfinished gesture; Escape during final
decoding discards the owned review after stop completes. Existing buttons remain.
Capture feedback and the editable transcript move into view. Trailing Space
repeats after a modifier-first release are consumed until Space is released.
The shortcut is focused, with no global registration; Live Assist Ctrl+Alt+Space
is unchanged. Explicit transcript use and provider proposal/save remain separate.

Dependencies were traced before edits: gesture -> asynchronous local capture ->
target/scope lock -> owned stop/cancel -> editable review -> explicit field use ->
existing provider proposal -> native preview/save. A capture-specific handle keeps
late gesture actions from ending another capture. Synchronous phase refs prevent
repeat requests; context generations reject old start/stop/cancel replies before
they can clear a new capture or replace its transcript. Existing Core ephemeral
voice methods, revision/target checks and cancellation ownership are reused.
No Core, IPC privilege, provider/authentication or packaging code changes.
Cancellation failures retain controls for retry; hardware release under device
failure is not claimed.

Validation under ignored `.local/push-to-edit/`:
- Final desktop sweep: 196 tests pass, including nine asynchronous gesture cases
  for early release, repeats, queued cancellation, Escape during decoding, owned
  cleanup and startup/stop failures. TypeScript, lint, formatting and build pass.
- Ten current Core voice tests pass. Core source bytes remain unchanged from the
  preceding 1249-test full sweep; that full sweep was not rerun for renderer edits.
- Final rebuilt Electron/local Core sweep: 116 workflows pass, no renderer errors
  (`gui-final.log`, `gui-result.json`). Selected-text release/repeat/Escape, outline
  release, Copilot deck-scope lock, actual native window-blur cancellation and
  modifier-first release all pass. Reviewed text invokes no automatic proposal.
  ASR/providers are deterministic local fixtures, not physical microphone or live
  account/model acceptance. Native PDF's optional five checks were not enabled;
  their preceding receipt remains separately recorded below.
- At 720x520 outer / 707x460 content, capture status and the focused transcript
  are measured within the viewport with no horizontal overflow. Inspected
  `small-listening.png`, `small-review.png`, `selected-text-review.png`.
- The 115-workflow full sweep before focus/repeat polish is retained separately
  (`gui-before-focus-polish.log`, `gui-before-focus-polish-result.json`). Initial
  failures remain: the review dialog changes its title, requiring a different
  locator; native blur testing initially lacked a verified focus transition.
  Playwright enables Chromium focus emulation by default. The final hold harness
  disables that override and focuses an owned disposable native window, verifying
  both native focused-window identity and renderer focus loss before cancellation.

Dirty `codex/production-readiness` / base SHA
`657b876739ff7a1cc5709a7e28e92ec2551b337e` remains preserved. The 373-entry
`source-freeze.json` and `source-audit.json` cover 368 unchanged preceding files,
three intended existing changes and two new gesture files. No staging, commit,
push, download/install, account/model call, packaging or release occurred.
Voice confidence/ambiguity handling and physical ASR quality/latency remain open,
as do broad PPTX fidelity, real preparation/rehearsal and hardware acceptance,
Fast Decisions calibration/latency, live Sign in with ChatGPT and exact-source
packaging. Signing and clean Windows validation remain accepted debt. Goal active.

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

Prepared: 2026-10-04

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

## Previous continuation - reviewed native table range formatting

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

## Previous continuation - reviewed native chart colors

The Workspace now offers Chart colors beside Native charts/Chart legend. Users can
choose a series and set an opaque RGB fill/outline, or choose an individual bar/column
point or pie slice. Line series edit their visible stroke and retain the unused area
fill; line-point/marker decoration remains outside this control. Series edits retain
existing individual point and marker overrides. The dialog shows a known explicit
current fill/stroke, or honestly reports native default/custom formatting. A proposed
RGB is explicit; changed chart/series/point/color invalidates review and save until
fresh preview and acknowledgment. Save, discard, retrieval refresh and exact undo reuse
the ordinary owned EditPlan lifecycle.

Copilot adds `set_chart_color` (29 operation types), with zero-based series index,
nullable point index and #RRGGBB. It receives bounded color descriptions on supported
selected charts, never native paths/fingerprints or workbook content. Core binds a
fresh fingerprint per staged step and captures the actual previous explicit fill/stroke
RGB (null for inherited/custom values), including successive edits to the same series.
The review shows target indexes and previous/proposed RGB, with native slide preview.

Dependencies reasoned through before edits: chart appearance edits must retain the
original workbook rather than use the data writer's literal-workbook replacement.
Legend and color changes now share the extracted `chart_appearance.py` clone/publish
boundary. Only the selected chart/frame is retargeted; original chart/workbook and other
package parts are retained. The final serialized chart is canonical-XML verified.
Color edits also prove all chart XML outside the selected shape properties unchanged;
only selected fill/outline RGB/opacity is replaced within those properties, preserving
widths, dashes, effects and other attributes. New point styles use native indexed dPt
nodes. Native labels, values, notes, geometry, IDs and legend settings stay intact.
Ambiguous native structural indexes and unsupported chart dependencies remain read-only;
invalid colors/indexes/booleans/stale fingerprints fail before publication. No database
migration or additional public IPC method is needed.

Validation: 23 new Core cases cover column/bar/line series, column/bar/pie points,
shared-chart isolation, original package members, no-op/save/undo, unsupported target
modes, invalid colors/bounds/boolean indexes, stale targets, width/dash/effect preservation,
retained point overrides, and successive staged Copilot RGB/fingerprint diffs. All 104
focused native-chart/legend/planning checks pass. The complete Core sweep passes all
1006 collected tests in four serial batches (249/311/248/198), without omissions/skips.
All 157 desktop tests, formatting, lint, TypeScript and mypy (154 files) pass. Receipts:
`.local/chart-colors/core-batches/manifest.json`, `core-all.log`, `core-native.log`,
`legend-regression.log`, `desktop.log`, `format-final.log`, `lint-final.log`,
`types-final.log`. Initial import-order/instruction-line-length fixture lint errors are
retained in earlier logs.

GUI acceptance: The Electron/local Core sweep passed all 96 checks without renderer exceptions.
Three added checks cover series/point target selection, RGB draft invalidation, fresh
native review/save/reopen/undo, reviewed point-preview discard and Copilot composed
series/point edits with previous RGB review, one-revision save/re-index and exact undo.
All three new review screenshots were inspected. Receipts: `.local/chart-colors/gui.log`,
`gui-result.json`, `workspace-chart-color-{series,point}-review.png` and
`workspace-copilot-chart-colors-review.png`. The first sweep reached a correct rendered
preview but the acknowledgment text had been changed incorrectly during component
extraction; the corrected label and final sweep are verified. The earlier failure is
retained in `gui-fixture-label.log`.

The final chart-color render check reuses the established color-control style so the
RGB picker displays a visible swatch. The complete 96-check behavior sweep preceded
this style-only correction; a fresh disposable Electron check imported an accepted
native chart, opened the color dialog, set purple and verified a 42px-wide, at least
30px-tall picker with 3px padding and the exact RGB. The screenshot was inspected.
Receipts: `.local/chart-colors/swatch.log`, `swatch-result.json`, `swatch-visible.png`.
Formatting/lint and the 339-entry freeze were reverified afterward.

Native PowerPoint opened twelve ordinary packages (baseline and colored for each of
six cases) read-only. COM verifies column/bar fill+outline RGB, line stroke RGB, pie
slice RGB and individual column/bar point RGB. It also verifies native values/categories/
series names/title and notes. Other-chart slide pixels stay identical; original
workbook/chart/other unaffected members remain byte-identical; all six undos restore
exact source packages. The native contact sheet was inspected. The initial audit
incorrectly expected line-chart area fill to render; the corrected writer/inspector
preserve that unused fill and edit/read visible stroke. Receipts:
`.local/chart-colors/office.log`, `office/result.json`, `office/contact.png` and
`office/{column-series,bar-series,line-series,pie-point,column-point,bar-point}/`.
Shared-chart isolation remains package-level evidence; the synthetic shared-chart
baseline was rejected by Office during the preceding legend slice.

Code/test freeze: `.local/chart-colors/source-freeze.json`, 339 entries. Eleven prior
files changed, 324 remain byte-identical and four files were added. Documentation is
outside that code/test freeze. Branch remains `codex/production-readiness`, base SHA
`657b876739ff7a1cc5709a7e28e92ec2551b337e`; dirty work is preserved.

Explicit series/point colors close the prior fixed-palette editing gap. Next substantial
authoring work includes table cell/header formatting; reason through inherited native
styles and cell/run dependencies first. Line markers, opacity/gradient controls,
automatic fitting, broader corpus fidelity and real-model quality remain open.
Fast-decision calibration/latency and live Sign in with ChatGPT acceptance remain open.
Signing and clean Windows validation remain accepted technical debt. No real account/
model call, download, staging, commit, push, packaging or release occurred. Goal is active.

## Previous continuation - explicit native chart legends

The Presentation Workspace now has a Chart legend dialog alongside Native charts.
It can show or hide a supported native legend, choose bottom/right/left/top/top-right
placement and explicitly overlay it on the plot. Changing placement or overlay
invalidates acknowledgment and save until a fresh native preview is reviewed.
Discard restores the saved presentation; save uses the existing exact-hash transaction,
re-index/preview refresh and whole-revision undo. The same `set_chart_legend` operation
is available to Copilot, bringing the strict provider schema to 28 operation types.
Review exposes exact previous and proposed legend settings from the staged target.

Dependencies reasoned through before edits: chart data and legend appearance require
different preservation boundaries. A dedicated writer clones only the selected chart
XML and its relationship part, retargeting only the selected frame. It retains every
original chart/workbook part and copies the original embedded workbook relationship;
no workbook is rewritten. Canonical XML comparison proves all non-legend chart content
unchanged. Native IDs, geometry, labels, cached values, titles and notes remain stable.
Core binds fresh fingerprints from each staged step, including prior legend edits.
Existing legend style/entries survive placement/overlay changes. Explicit hiding removes
the legend; showing it again uses native defaults, and undo restores the original styling.
Manual layouts, extensions and unsupported legend settings remain read-only. Hidden
legends cannot request overlay. No database migration or public IPC method was added.

Validation: eighteen new Core tests cover column/bar/line/pie charts, placements/overlay,
shared-part isolation, exact original package members, hide/no-op/undo, retained legend
styles and entries, malformed/manual/extended legend rejection, invalid booleans/settings,
stale fingerprints, private provider context and successive staged fingerprints/diffs.
The full Core sweep passed all 983 collected tests in four serial batches
(226/311/248/198), with no omissions or skips. A final 38-test legend/data rerun also
covers the added hidden-overlay rejection guard. All 157 desktop tests, formatting,
lint, TypeScript and mypy (152 files) pass. Receipts: `.local/chart-legend/` with
`core-batches/manifest.json`, `core-all.log`, `core-native.log` (81 native/planning
checks), `core-focused-final.log`, `desktop.log`, `format-final.log`, `lint-final.log`
and `types-final.log`. Initial fixture/schema mistakes and lint errors are retained
in their earlier logs.

GUI acceptance: The Electron/local Core sweep passed all 93 checks with no renderer exceptions.
Three added checks cover loading native settings, bottom-to-right draft invalidation,
fresh reviewed save, hide-preview discard, exact undo, and Copilot hidden-to-bottom
previous/proposed settings with native preview/save/re-index/undo. The test explicitly
awaits asynchronous chart discovery and reselects the metrics slide after undo.
Both direct and Copilot review screenshots were inspected. Receipts:
`.local/chart-legend/gui.log`, `gui-result.json`,
`workspace-chart-legend-right-review.png`, and
`workspace-copilot-chart-legend-review.png`. Earlier fixture encoding, loading-wait and
undo-selection failures are retained in `gui-fixture-{encoding,label,loading,slide}.log`.

Native PowerPoint opened a baseline and six saved legend revisions read-only. COM
verified all five visible placements, non-overlay/overlay layout behavior, hiding,
unchanged native series names/categories/values/title and notes. The other chart's
slide export stayed pixel-identical. Original chart/workbook and other package members
remained byte-identical; six successive undos restored the exact prior packages.
All six native exports were visually inspected in `office/contact.png`. Receipts:
`.local/chart-legend/office.log`, `office/result.json`, `office/contact.png` and
`office/{bottom,left,top,top_right,right,hidden}-slide1.png`. PowerPoint rejected the
synthetic shared-chart baseline before legend editing; this is retained in
`office-shared-fixture.log`. Shared-chart isolation is package-level evidence from
Core tests, not native acceptance of that fixture.

Source/test freeze: `.local/chart-legend/source-freeze.json` (335 entries). Ten prior
source/test files changed, 322 remain byte-identical and three files were added.
Documentation updates are separate from this code/test freeze. Branch remains
`codex/production-readiness`, base SHA `657b876739ff7a1cc5709a7e28e92ec2551b337e`;
the dirty worktree is preserved.

The previously observed hidden second-series legend gap is now addressed explicitly.
Verified next authoring gaps: explicit per-series chart colors and table cell/header
formatting controls; the current editors expose data/structure rather than these settings.
Reason through native formatting inheritance and shared-part isolation before implementing
them. Remaining work also includes automatic fit, corpus/renderer fidelity,
real-model integration quality, fast-decision calibration/latency and live Sign in with
ChatGPT acceptance. Signing and clean Windows validation remain accepted technical debt.
These tests use local deterministic providers and synthetic data. No external account/model calls,
downloads, staging, commits, pushes, packaging or releases occurred. Goal remains active.

## Previous continuation - Copilot native table and chart workflows

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

## Previous continuation - refinement of unsaved Copilot edit proposals

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

## Previous continuation - Copilot and reviewed voice diagram planning

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

## Previous continuation - reviewed structured native diagrams

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

## Latest continuation - reviewed existing-placeholder remapping

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

## Latest continuation - native layout thumbnail comparison

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

## Latest continuation - reviewed native evidence footnotes

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

## Latest continuation - reviewed appendix creation

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

## Latest continuation - complete native group actions

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
or reviewed ungrouping. Copilot proposals for grouping/ungrouping remain open.

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

## Latest continuation - reviewed native grouping and ungrouping

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

## Latest continuation - reviewed selection actions and canvas shortcuts

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



## Latest continuation - reviewed native chart structure

Native charts now offers insertion before/after and removal for categories and
series on supported existing column, bar, line and pie charts. Labeled selectors
and focused data cells select the target. New categories/series require names;
new values start at zero. Limits remain 24 categories and 6 series, or one series
for pie; the final item cannot be removed. Structural draft changes invalidate
review. Preview, acknowledgment, one-revision save, retrieval refresh, discard and
undo use the existing reviewed native edit workflow.

Dependencies considered before editing: changing cache counts alone leaves stale
workbook ranges, series identities, point overrides, data-label indexes and legend
entries. The manual reshape_chart transaction carries explicit category/series
source mappings (null means inserted), rejects duplicates/out-of-bounds/reordering,
and retains current revision/fingerprint guards. Retained series keep native IDs,
series formatting and mapped point/data-label overrides. Removed item overrides
are removed; retained cache-point format attributes follow their categories. New
series get new IDs and app chart colors; custom point/label/trendline/error-bar
settings from another series are not copied. Plot-level labels and custom legend
entries are remapped. The native type, axes/layout, outer geometry, identity, title
styles, notes and other slides/objects stay intact. The existing writer clones the
chart/relationships and writes a literal embedded workbook with updated ranges;
original parts remain unchanged for other references. Post-write inventory and
chart/workbook data validation still apply. The fixed-count replace_chart_data
contract remains unchanged. No public IPC, provider schema or database migration.

Linked/extended/unsupported charts remain read-only. Reordered native series,
malformed point/label/legend identities and custom legends combined with trendlines
stay outside structural editing, with explicit reasons; supported labels/values
can still be edited. Arbitrary item reordering, combo/stacked/other chart types,
axes/legend authoring and native workbook editing remain open.

Validation: 18 new structural tests passed across all four types and shared/nonshared
chart dependencies. All 821 collected Core tests passed in four fresh-process serial
batches (173 + 245 + 199 + 204), without skips/omissions; 134 desktop tests passed.
Tests verify reviewed save/reindex/undo, exact unchanged original package parts,
retained series formatting/IDs, independent literal workbooks, point/label/legend
index mapping, cache number-format retention, and specific atomic rejection codes.
Receipts: `.local/chart-structure-core-batches/manifest.json`,
`.local/chart-structure-core-focused.log`, `.local/chart-structure-existing.log`
and `.local/chart-structure-desktop.log`.

Native PowerPoint acceptance passed for ordinary imported column/bar/line/pie
fixtures: four categories, two series (one for pie), exact names/values, unchanged
outer geometry/notes/retained fill and independent native title edits. Other slide
charts and both file hashes remained unchanged. Exports were inspected. Evidence:
`.local/chart-structure-office/result.json`, `check.log` and eight exported PNGs.
The synthetic shared-chart-part source failed PowerPoint open although its edited
result opened. `check-shared-source.log` preserves that evidence; shared-part
isolation is Core proof, not Office compatibility proof. Broad import/pixel fidelity
is not established by these fixtures. Source/test hashes are recorded in
`.local/chart-structure-source-freeze.json` (307 files).
Final ESLint/Ruff, formatting, both TypeScript projects and mypy (147 source files)
passed. The full Electron sweep passed all 72 workflows, including category/series
insertion before/after, middle deletion, retained labels/values, structural review
invalidation, save, persisted discovery and undo. The reviewed screenshot was
inspected for Baseline/Forecast/Target and Revenue/Margin placement. The first run
stopped on a test locator that named Category 1 label instead of the existing
Category 1 field; exact labels were corrected and the full retry passed. Evidence:
`.local/chart-structure-ui-final.log`,
`.local/ui-validation/workspace-native-chart-structure-review.png`,
`.local/chart-structure-lint-final.log`, `.local/chart-structure-format-final.log`
and `.local/chart-structure-types-final.log`. Only GUI-script whitespace was formatted
at the end; application/Core sources stayed unchanged during acceptance. The final
307 source/test hashes match `.local/chart-structure-source-freeze-check.json`.
Final diff whitespace check passed. Every acceptance process launched for this
continuation reached terminal state. GUI/provider checks use deterministic providers;
live model/account/speech/human acceptance remains open.

Next priorities: remaining substantial GUI workflows, richer chart/table authoring,
common keyboard actions, broader corpus fidelity and live integration acceptance.
Live fast-decision calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted debt. Dirty work
is preserved; no account/model calls, downloads, commits, pushes, packaging or
releases occurred. The production-readiness goal remains active.

## Previous continuation - reviewed native table structure

Native tables now supports inserting rows/columns before or after the selection,
and removing selected rows/columns, in the same editor as cell text. Focusing a
cell selects its row and column; labeled selectors also control the actions.
The draft stays local until rendered preview, acknowledgment and one-revision
save. Structural edits invalidate review; discard and existing undo remain wired.
Limits remain 1–12 rows, 1–8 columns, 500 characters/10 paragraphs per cell and
10000 total characters. The last row/column cannot be removed in the GUI.

Dependencies considered before editing: changing matrix dimensions through the
cell-only operation would either fail or shift text into the wrong native cells.
A manual reshape_table transaction instead carries explicit original row/column
indices, with null for inserted rows/columns. Retained indices must be unique,
in bounds and in original order. The verified native table fingerprint and current
revision guard still apply. Retained native cells are cloned with their cell and
text styles; unchanged text bodies are preserved. New cells inherit the
next retained row/column, or the previous one at the end (body/first-column fallback
when no original rows/columns remain). Rows and columns redistribute the existing
height/width totals proportionally, with deterministic integer rounding and native
dimension limits. Outer transform, object identity, notes, other slides/objects and
unrelated package parts stay unchanged and are validated. The cell-only operation
retains its original fixed-dimension contract. No public IPC, provider schema or
database migration is added; the reviewed plan lane dispatches reshape_table.

Imported structures with unknown row/grid attributes, nonpositive/oversized native
dimensions, merged/linked/mixed-run/extended cells remain locked to the supported
editing scope. Supported plain text cells can still be edited when structural
editing is unavailable. Arbitrary row/column reordering, merge/split, per-cell rich
formatting and table pagination remain open.

Validation: 19 new structural tests passed; all 803 collected Core tests passed in
four serial fresh-process batches (251 + 184 + 204 + 164), without skips/omissions.
All 134 desktop tests passed. Tests cover staged save/retrieval/undo, exact part
preservation, retained/inherited native styles, dimensions, no-op and mapping,
stale-target, foreign-target and malformed-structure rejection. An initial no-op
fixture omitted the required plan summary; it was corrected, and rejection tests
now assert their specific error codes. Full collection/batch receipt:
`.local/table-structure-core-batches/manifest.json`; focused and desktop logs:
`.local/table-structure-core-focused.log`, `.local/table-structure-desktop.log`.

Native PowerPoint opened the reviewed 3x4 fixture, verified every cell, original
outer geometry, inherited fills/font colors and independent in-memory editing.
Read-only exports were inspected; both PPTX file hashes stayed unchanged.
Evidence: `.local/table-structure-office/result.json`, `check.log`,
`table-structure.png` and `table-structure-edited.png`. This is fixture acceptance,
not proof for all imported presentations. Source/test hashes are frozen in
`.local/table-structure-source-freeze.json` (305 files).
ESLint/Ruff, formatting, both TypeScript projects and mypy (146 source files)
passed. All 64 focused table/geometry checks passed on the final source. The final
Electron sweep passed all 71 workflows, including insertion before/after, middle
deletion, retained header/body text, rendered review, structural review invalidation,
saved-cell discovery and undo. Screenshot inspection exposed insufficient assertions
in an earlier green sweep: ambiguous numeric Playwright selections matched option
labels instead of intended values. Explicit value selections and intermediate
Metric/Current/Measured preservation assertions now verify the intended sequence.
The initial missing Risk-row fixture was also corrected. Focused GUI traces:
`.local/table-structure-debug/debug-exact.log` and inspected `table-controls.png`.
Final evidence: `.local/table-structure-ui-exact.log`,
`.local/ui-validation/workspace-native-table-structure-review.png`,
`.local/table-structure-core-focused-final.log`, `.local/table-structure-lint-final.log`,
`.local/table-structure-format-final.log` and `.local/table-structure-types-final.log`.
All 305 frozen source/test hashes were verified unchanged after GUI completion;
`.local/table-structure-source-freeze-check.json`. Final diff whitespace check passed.
All acceptance processes from this continuation reached terminal state. GUI/provider
tests use deterministic providers; live account, model, speech and human integration
acceptance remain open.

Next priorities: structural chart categories/series and richer table/chart workflows,
common keyboard operations, broader corpus fidelity and live integration acceptance.
Fast-decision live calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted debt. Dirty work
is preserved; no account/model calls, downloads, commits, pushes, packaging or
releases occurred. The production-readiness goal remains active.

## Previous continuation - immutable native object clipboard

Copy objects and Paste objects now expose a presentation clipboard in the slide
canvas. Ctrl/Cmd+C and Ctrl/Cmd+V work from the focused canvas without intercepting
text inputs. Copy records the selected native objects, source presentation, slide
and immutable revision; it performs no edit. The clipboard survives navigation and
presentation changes within the current project, and clears when changing projects.
Pasting drafts a native edit plan into the current destination slide and requires
preview plus acknowledgment before saving one revision. Cancel/discard changes no
revision; save refreshes retrieval and supports existing undo. This is an in-app
presentation clipboard, not OS clipboard interoperability or cut/move.

Dependencies considered before editing: simply invoking Duplicate would read the
latest content instead of the content at Copy, and would not cross slides. The new
manual paste_objects transaction reads the verified pinned source revision in the
same project and rewrites a verified current destination package. It copies 1–20
eligible top-level objects in source layer order with fresh IDs/names, preserving
physical sizes and group spacing with a bounded 0.25-inch offset. Selections larger
than the destination are rejected. Native images get remapped PNG/JPEG dependencies
with sharing retained within a batch; crop and external hyperlinks are preserved
without opening them. Native chart graphs get independent chart/workbook/style/
image/theme parts, preserving internal sharing inside the batch while separating
source dependencies. Tables copy native frames/cells; unavailable custom table
styles are rejected. Text/theme colors use the destination theme as stated in review.
Unsupported or missing dependencies, linked chart workbooks and extended chart
dependencies fail before commit. Package,
XML, expanded-size and object limits remain enforced. Existing slides, objects,
notes and parts are validated after writing. No database migration or new public IPC;
paste uses prepare/open/apply/reject edit plans and the existing transaction writer.
Created-object arrays are returned and recorded in transaction metadata.

GUI acceptance exposed three concrete defects: Paste was enabled while navigation
had cleared the destination ID, the shared dialog tried alignment validation before
paste preparation, and the normal revision-change effect cleared the new selection.
Paste now waits for the authoritative destination inventory, its review bypasses
alignment selection, and pasted objects are selected only after the exact committed
revision and refreshed inventory arrive. Review displays structured Core errors.
Missing chart relationship roots and dependency collisions now fail with structured
errors before any commit. Tests also verify that two pasted chart frames sharing one
source chart keep a single independent chart/workbook graph inside the pasted batch.

Validation on the frozen source: all 784 collected Core tests passed in four serial
fresh-process batches (238 + 178 + 204 + 164), with the complete collection and batch
manifest in `.local/object-paste-core-batches/`. An earlier single-process run failed
two existing tests with logged MEMORY_ALLOCATION_FAILED; it is not a passing receipt.
The serial run includes every collected test without skips or omissions. Focused
clipboard/duplication/diagnostics coverage passed 37 tests. All 134 desktop tests,
ESLint/Ruff, formatting, both TypeScript projects and mypy (145 source files) passed.
Request-boundary diagnostics emit only fixed memory/I/O/unexpected cause codes,
without exception content or changes to public error responses.

Native PowerPoint acceptance passed for charts and tables pasted between presentations:
editable native content, independent in-memory edits, exact size/bounded offset,
destination notes and unchanged source/destination file hashes. Exports were inspected.
Evidence: `.local/object-paste-office/result.json`, `check.log` and four exported PNGs.
This fixture acceptance does not establish fidelity for every imported presentation.
The final GUI sweep passed all 70 workflows on the frozen source, including grouped
copy/paste across slides, cancellation, rendered review and acknowledgment, exact
revision save, pasted selection, native chart/table keyboard paste and undo.
Evidence: `.local/object-paste-ui-final-20261003.log` and inspected screenshots in
`.local/ui-validation/`: `workspace-object-paste-review.png`,
`workspace-native-table-clipboard-review.png` and
`workspace-native-chart-clipboard-review.png`. An initial final-run attempt timed out
at the first screenshot after fonts loaded, before clipboard tests; the complete
retry passed. Code/test source hashes in `.local/object-paste-source-freeze.json`
were verified unchanged for all 303 files; receipt:
`.local/object-paste-source-freeze-check.json`. Final diff whitespace check passed.
All test/acceptance processes launched for this continuation reached terminal state.
GUI/provider workflow tests use deterministic providers; this is not live account,
model, speech or integration acceptance.

Remaining priorities: deeper table/chart authoring, further clipboard interoperability
and common keyboard workflows, broader corpus fidelity and live integration acceptance.
Fast-decision live calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted tech debt. Dirty
work is preserved; no account/model calls, downloads, commits, pushes, packaging or
releases occurred. The production-readiness goal remains active.

## Previous continuation - reviewed canvas resize handles

The slide canvas now has eight accessible edge/corner resize handles for supported
native objects and selections of up to 20 objects. Pointer dragging shows geometry
ghosts; releasing drafts the existing native geometry review. Shift on corners
preserves group proportions, and optional 0.1-inch snapping applies to displacement.
Arrow keys on a focused handle draft a resize. Escape, canceled/lost pointer capture,
slide/revision changes and leaving selection mode clear the drag without saving.
Review shows before/after position and width/height, requires a rendered preview and
acknowledgment, saves one revision, refreshes retrieval and supports existing undo.
Shapes, pictures, native charts and tables use the same supported geometry guards.

Dependencies considered before editing: canvas pixels must map through the rendered
image into integer slide EMUs, including selection-mode margins and image resize.
Group scaling anchors the opposite edge, scales relative placement and sizes, rounds
endpoints, clamps to slide bounds and keeps each member at least one point unless
already smaller. Existing source geometry is not mutated. Only editable top-level
objects are exposed; native table row/column scaling and chart preservation remain
in the existing reviewed transform writer. No backend, IPC or database change.
Handles sit outside selected bounds with 20 pixels of image margin in selection
mode; the first GUI attempt caught centered handles intercepting thin-label clicks.
That actual interaction defect was fixed before the passing rerun. A later failure
was a test revision-number expectation after the newly added save/undo workflow.

Final acceptance passed 134 desktop tests in 3.51 seconds and all 67 Electron GUI
workflows, including group/corner/keyboard resizing, Escape cancellation, preview,
required acknowledgment, one-revision save and undo, plus native chart/table resize
and existing downstream editing workflows. Evidence:
`.local/canvas-resize-desktop-final-20261003.log` and
`.local/canvas-resize-ui-final-20261003.log`. Focused Core geometry/duplication/
transaction acceptance passed 55 tests in 11.39 seconds:
`.local/canvas-resize-native-core-20261003.log`. Final lint, format and types passed
in `.local/canvas-resize-{lint,format,types}-final-20261003.log`; both TypeScript
projects and 144 Core modules type-check. Group ghost/review and native chart/table
resize screenshots under `.local/ui-validation/` were inspected. The review now
explicitly lists dimensions as well as positions. All check handles are terminal,
and `git diff --check` passes.
The earlier full 762-test Core and native PowerPoint evidence remain historical;
this continuation changes the frontend only and does not claim a new full Core or
PowerPoint acceptance run. Validation is serial with a bounded Node heap because
host allocation exhaustion interrupted earlier attempts; unrelated processes remain
untouched.

Remaining priorities: object copy/paste, substantial table/chart editing, broader
corpus fidelity and live integration acceptance. Fast-decision live calibration and
latency plus actual Sign in with ChatGPT acceptance remain open. Signing and clean
Windows validation remain accepted tech debt. Dirty work is preserved; no account or
model calls, downloads, commits, pushes, packaging or releases occurred. The
production-readiness goal remains active.

## Previous continuation - whole native chart/table slide duplication

Whole-slide duplication now accepts native chart relationships and creates
independent chart/workbook/style/image/theme parts for the copied slide. Native
tables already copy as slide XML and are now covered by direct, reviewed-plan and
GUI acceptance. The copied slide retains its exact source XML bytes, native IDs,
geometry, names, content, notes and internal relationship IDs. Existing slides,
chart parts, embedded workbooks and notes remain unchanged. One revision is added,
retrieval refresh and selection use the existing workflow, and undo restores the
original bytes. No new IPC operation, provider schema or database migration.

Dependencies considered before editing: simply accepting /chart relationships
would make the copy share mutable chart/workbook parts with its source. The chart
graph copier now accepts copied slide relationship/content-type roots, preserves
relationship IDs and shares a clone map across charts. Multiple references to one
chart, different relationships to that same chart, and separate charts sharing a
workbook retain their internal sharing inside the copied slide while separating
all active chart dependencies from the original. Graph copying still rejects
external, missing, extended or unknown active chart dependencies before commit;
chart references outside supported native frame structures are rejected. Unused
internal chart relationships left by object deletion are preserved without cloning
inactive charts, so copying a slide after deleting its chart now works. Notes
back-links and content-type overrides are updated together with presentation order.
The archive remains subject to existing source/package/XML/object/slide limits.

Focused acceptance passed 15 tests in 5.59 seconds:
`.local/graphic-slide-copy-focused-20261003.log`. This includes the previous object
duplication tests plus new chart/table direct and staged-review slide copying,
exact slide/notes bytes, source-package preservation, independent subsequent chart
editing and undo, unsupported dependency rejection, duplication after chart
deletion and three intentional chart/workbook sharing patterns. Format/lint/types
passed in `.local/graphic-slide-copy-{format,lint,types}-20261003.log`; desktop
acceptance passed 121 tests with two workers in the corresponding desktop log.
Validation runs are separated to avoid the host allocation exhaustion observed in
the previous continuation; no unrelated processes were stopped.

PowerPoint evidence: `.local/graphic-slide-copy-office/check.py`, `check.log`,
`result.json`, copied PPTX fixtures and exported PNGs. Both decks opened read-only
with three slides; source/copy native geometry, IDs, names, data and speaker notes
matched. Original and copied slide exports were byte-identical native PNGs. Editing
the copied chart title/table cell in memory left the original and remaining chart
slide unchanged. Files were never saved, hashes remained unchanged and the owned
Office instance was closed. Copy and independently edited PNGs were inspected.
The synthetic shared-dependency cases have Core package/data proof; the Office
acceptance above uses independent native fixture decks.

Full Core acceptance passed 762 tests in 194.51 seconds:
`.local/graphic-slide-copy-core-20261003.log`. All static and desktop checks used
the final source, after shared-workbook and native frame-reference guards were added.

Final Electron acceptance passed 64 workflows:
`.local/graphic-slide-copy-ui-final-20261003.log`. Whole native chart/table slides
were copied from slide 1 to slide 2, retained editable objects and rendered
previews, refreshed retrieval, and undid back to the original slide/revision.
Screenshots `workspace-native-chart-slide-duplicated.png` and
`workspace-native-table-slide-duplicated.png` were inspected. The initial GUI
attempt caught a test-only extra Previous navigation after undo had already
restored slide 1; removing that unnecessary step yielded a complete passing run.
Final lint and format checks passed again after that test adjustment. All acceptance
process handles are terminal and `git diff --check` passed.

Remaining priorities: canvas resize handles and object copy/paste, substantial
table/chart editing, broader corpus fidelity and live integration acceptance.
The UX minimum interactions explicitly require resize handles and copy/paste;
current SlideObjectCanvas renders translation/selection only, with no resize
callback or clipboard path. These are verified missing workflows for the next
continuation.
Fast-decision live calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted tech debt.
Dirty work remains preserved. No external account/model calls, downloads, commits, pushes,
packaging or releases occurred. The production-readiness goal remains active.

## Previous continuation - independent native chart/table duplication

Supported direct native chart/table objects now expose Duplicate object in the
Objects inspector. The existing action creates one immutable revision, selects
the copy, refreshes retrieval and supports exact-byte undo. Copies receive fresh
native object IDs and unique names, retain size/content/formatting, and use the
existing bounded 0.25-inch (18-point) placement offset. Tables copy their own native
frame/grid/cells. Charts copy an independent package graph: chart XML, embedded
workbook bytes, chart styles/colors, internal images and theme overrides, with
rewritten relationships and content types. Source chart/workbook parts, other
slides and notes remain untouched. Workbooks are copied as opaque bytes rather
than opened, evaluated or regenerated. Chart duplication does not require the
narrower chart data editor's category/type bounds.

Dependency reasoning preceded edits: shape/picture duplication used nvSpPr/nvPicPr
and spPr transforms; graphicFrame requires nvGraphicFramePr and p:xfrm. A shared
chart relationship would make direct Office edits affect both copies, so charts
must get independent parts before the new frame is written. Graph traversal
retains relationship IDs inside each copied part, rewrites targets, handles shared
nodes/cycles once, limits traversal to 64 parts and avoids collisions. External,
unknown, missing or extended chart dependencies fail before revision commit.
Geometry/deletion eligibility still excludes placeholders, connector/animation
references and unsupported/grouped frames. Existing stale geometry/head, package
limits, staging, native transaction, retrieval refresh and undo paths are reused.
No IPC method, provider operation, database schema or migration was added.

Focused acceptance passed 25 tests in 12.00 seconds:
`.local/graphic-duplication-focused-final-20261003.log`. New cases cover native
chart/table identity, order, size/content, source-part preservation, literal
workbook copy, independent subsequent chart editing, undo, external/extension
rejection and style/image graph target isolation. Final desktop acceptance passed
121 tests using two workers in `.local/graphic-duplication-desktop-final-20261003.log`.
Formatting, lint and type checking passed in separate final format/lint/types logs.

PowerPoint evidence: `.local/graphic-duplication-office/check.py`, `check.log`,
`result.json`, duplicated PPTX fixtures and native exported PNGs. Office opened both
fixtures read-only, found distinct native IDs/names and matching data/formatting,
verified the 18-point placement offset, and independently edited the copy's chart
title/table cell in memory while the original and other slide stayed unchanged.
No save was performed, hashes stayed unchanged, and the owned Office instance was
closed. Both PNGs were inspected; deliberate overlapping copies demonstrate native
independence and offset, not a publication-ready composed slide.

The initial concurrent acceptance attempt failed from host worker/allocation
exhaustion and a GUI narrative timeout before this feature. Its handles were
verified terminal. Validation was rerun with bounded desktop workers and a separate
GUI run; no unrelated process was stopped. The first Office attempt caught a test
expectation of 12 points instead of the existing 18-point offset, then the corrected
fixture check passed.

Full Core acceptance passed 752 tests in 199.10 seconds:
`.local/graphic-duplication-core-final-20261003.log`. The suite exercised duplication before the final imported
chart clone naming refinement, which was added to avoid the authored-chart preview adapter
convention; all 25 focused checks passed again with an explicit naming assertion,
and the changed module passed Ruff and mypy. Office was rerun successfully
after the refinement. Authored charts retain their naming
convention. The naming refinement changes neither native chart bytes nor contents.

Final Electron acceptance passed 62 workflows:
`.local/graphic-duplication-ui-final-20261003.log`. Both native duplication flows
verified creation of a second editable object, selected-copy refresh and exact
revision undo, followed by the prior layer/delete workflows. Screenshots
`workspace-native-chart-duplicated.png` and `workspace-native-table-duplicated.png`
were inspected. Both final acceptance process handles are terminal. Diff checks
passed, and all unrelated dirty work remains preserved.

Remaining priorities: broader structural editing including whole-slide duplication
with chart/table dependencies, corpus fidelity and live integration acceptance.
Current whole-slide duplication rejects chart relationships even when a deleted
frame left an unused relationship; this is the next verified structural gap.
Fast-decision live calibration/latency and actual Sign in with ChatGPT acceptance
remain open. Signing and clean Windows validation remain accepted tech debt.
Dirty work is preserved; no account/model calls, downloads, commits, pushes,
packaging or releases occurred. The production-readiness goal remains active.

## Previous continuation - native chart/table layers and deletion

Supported direct native charts and tables now support object layering and confirmed
object deletion in the Presentation Workspace. Deletion removes only the selected
frame from its slide; chart/workbook parts and relationships remain intact so other
frames can keep using them. Layering changes only the native slide tree order.
Both use existing current-head/stale-target guards, retrieval refresh and undo.
Duplication remains disabled in the GUI and explicitly rejected by both Core API
and writer because the shape/picture identity copier is not a graphicFrame copier.

Dependencies considered before edits: native frame selection already supports
geometry, but delete eligibility is also consumed by layering, duplicate controls
and object response validation. All those consumers were traced and adjusted.
Placeholder, connector and animation dependencies keep deletion/layering read-only.
Connector references inside groups are checked, and all timing spid attributes are
checked, including chart build references without spTgt nodes. Existing narrow
geometry eligibility remains required. No new IPC method, schema or migration.
Package parts are retained deliberately; no orphan cleanup is attempted.

Focused acceptance: 20 tests passed in 7.96 seconds in
`.local/graphic-actions-focused-20261003.log`, including native chart/table
layer/delete/undo, unchanged package parts and contents, shared-chart isolation,
connector/group/placeholder/timing/build guards and duplicate rejection.
PowerPoint opened layered and deleted chart/table fixtures read-only, verified
native data and selected-frame removal, retained the independent chart on slide 2,
and left input hashes unchanged. Evidence: `.local/graphic-actions-office/`
`check.py`, `check.log`, `result.json`, PPTX files and exported PNGs. All four PNGs
were visually inspected. The table-layer fixture deliberately places the table
behind overlapping text; this demonstrates stacking, not final authored layout.
The synthetic shared-chart case has Core package/data proof only; its earlier
Office baseline incompatibility is not presented as Office acceptance.

Electron acceptance passed 60 workflows in
`.local/graphic-actions-ui-final-20261003.log`, including chart/table layer changes,
confirmation cancellation, deletion, duplicate gating and undo. Confirmation
screenshots `workspace-native-table-delete-review.png` and
`workspace-native-chart-delete-review.png` in `.local/ui-validation/` were inspected.
The initial GUI attempts caught test locator/selection errors; after correcting
those test harness errors, the complete rerun passed.

Final `pnpm check` passed formatting, lint, type checking, 121 desktop tests and
747 Core tests in 136.00 seconds: `.local/graphic-actions-check-final-20261003.log`.
Earlier check attempts caught test harness lint/format issues; the final check ran
after the timing-build and shared-chart tests were added. `git diff --check` passed.

Next priorities remain native chart/table duplication and broader structural
editing, then corpus fidelity and live integration acceptance. Fast-decision live
calibration/latency and actual Sign in with ChatGPT acceptance remain open. Signing
and clean Windows validation remain accepted tech debt. Dirty work was preserved;
no account/model calls, downloads, commits, pushes, packaging or releases occurred.

## Previous continuation - reviewed native chart/table layout

Supported direct native charts and tables now expose verified geometry in the
object inventory and canvas. They participate in selection, drag/align/distribute
workflows and position/size drafting. Numeric layout changes open the staged native
review dialog before saving, with explicit image review, one-revision commit,
retrieval refresh and undo. Existing shape/picture behavior is retained. Charts
change only the native frame transform. Table resizing also scales column widths
and row heights proportionally with exact positive integer totals; translation
keeps the grid unchanged. Cells, formatting, native IDs, chart cache/workbooks,
relationships, other slides and notes stay intact. No new IPC/schema/migration;
existing transform_object and reviewed-plan paths are reused.

Dependencies considered before edits: graphicFrame uses p:xfrm rather than the
shape/picture p:spPr/a:xfrm path; table grid dimensions must match the frame;
proportional rounding must retain nonempty rows/columns and exact totals; native
geometry eligibility must propagate through object parsing, canvas, review plans,
stale geometry/current-head guards, rendering, cleanup and undo. Only direct,
unrotated/unflipped, in-bounds frames with supported chart references or consistent
positive table grids are editable. Table geometry supports at most 128 columns and
256 rows, independently of the narrower cell-data editor. Alternate content,
grouped/inherited/extended/malformed frames and mismatched grids stay read-only.
Delete/duplicate/layer actions remain disabled for these frames because their
identity/relationship dependencies require separate work.

Focused geometry tests passed 10 in 1.93 seconds:
`.local/graphic-geometry-focused-final-20261003.log`. Coverage includes reviewed
chart/table movement and resizing, unchanged package parts/native content/notes,
exact grid totals, proportional unequal widths/heights, no-op, stale geometry,
invalid bounds, empty-grid rejection and undo. The initial full check passed 121
desktop and 736 Core tests before the last proportional-grid case and final GUI
wiring. Final pnpm check passed format/lint/types, 121 desktop and 737 Core tests
in 128.23 seconds: `.local/graphic-geometry-check-final-20261003.log`.
Electron passed 58 workflows: `.local/graphic-geometry-ui-final-20261003.log`.
New cases cover chart and table discovery, position/size drafting, native staged
preview, required review, exact save and undo. Inspected
`.local/ui-validation/workspace-native-chart-layout.png` and
`workspace-native-table-layout.png`. An initial run
failed during Sources navigation before reaching these new workflows. Inspected
Office evidence is `.local/graphic-geometry-office/result.json`, `check.py`,
`check.log`, `chart-resized.png` and `table-resized.png`. PowerPoint opened both
fixtures, reported the requested 1/1.5/6.5/3.5-inch geometry, retained native chart
values/title and table font/counts, matched table row/column totals, exported renders
and left file hashes unchanged. Fixture Office instances closed. This proves native
geometry for these fixtures, not enterprise chart/table fidelity or publication
quality for arbitrary chosen positions.

Dirty worktree preserved; no commits/pushes, packaging, accounts/model calls,
downloads or releases. Next: remaining native chart/table object and structural
workflows, then broader fidelity/integration/human acceptance. Real fast-decision
calibration/latency and live Sign in with ChatGPT remain open. Signing and clean
Windows validation remain accepted debt; full master/theme editing stays deferred.

## Prior continuation - reviewed existing chart data editing

Native charts in Slide actions & layout now inserts charts or selects an existing
supported native chart to edit category labels, series names, values and a plain
styled title. Type, category/series counts, placement, axes, data-point styles,
labels, object identity and notes are preserved. A mixed/complex rich title stays
locked while supported values can still be edited. Native staged preview, explicit
review, draft invalidation, no-op/discard, one-revision save, reindex and whole-edit
undo are supported. The picker currently lists at most 20 direct charts per slide.
New IPC: list_charts/replace_chart_data. Native transactions now support 23 types;
provider schemas remain unchanged. Project schema remains 17; no migration.

Dependencies considered before edits: source/current-head ownership, slide/frame
identity, native relationship resolution, fingerprinted chart/frame/relationships,
embedded workbook/cache consistency, shared parts, chart styles and linked formula
references, title run/paragraph inheritance, literal formula/URL-like labels,
exact staged bytes, reindex/undo, current-head races and dialog lifetime. Each edit
clones the selected chart and its relationships, writes a new literal-data workbook
and adds a new selected-frame relationship. Original chart/workbook/package parts
stay byte-identical for other uses. Category/series counts stay fixed to preserve
point-level styling. The original embedded workbook is never opened; it is retained
alongside the replacement. Charts with linked external workbooks, additional title
or data-label workbook formulas, extension data, unsupported types or missing caches
remain read-only with a reason. Ordinary cached chart text now retains multiline
titles for creation, import, retrieval and reviewed edits.

Final pnpm check passed format/lint/types, 121 desktop and 727 Core tests in
139.84 seconds: `.local/chart-editing-check-final-20261003.log`. Focused chart suites
passed 48 in 10.96 seconds at `.local/chart-editing-focused-final-20261003.log` (25
new edit cases plus 23 creation cases). Covers all four types, imported custom
styles, shared parts on two slides, staged atomic apply/failure cleanup, literal
workbooks, unchanged package/geometry/notes, retrieval, undo, no-op, stale
fingerprint/head/IDs, source corruption, fixed structure, read-only linked/extended
or unsupported data, mixed title preservation and styled multiline title changes.
Initial retrieval assertions used a nonexistent workspace method; corrected to the
actual source.reindex endpoint. The initial full run passed 723 before the final
four linked-title/multiline/atomic-failure/corruption cases were added.

Electron passed 56 workflows: `.local/chart-editing-ui-final-20261003.log`. New case
covers existing discovery, loaded values/title, fixed structure, no-op, preview,
edited-value review invalidation, discard, reviewed save, persisted values,
retrieval refresh and undoing data edits separately from insertion. Inspected
`.local/ui-validation/workspace-native-chart-data-edit.png`. Placement controls are
hidden for data editing rather than showing creation defaults as current placement.

PowerPoint opened and exported four two-slide imported-chart fixtures, verified
native type, new values/title, preserved 23-point bold title, geometry and notes,
other-chart values and unchanged file hashes. Untouched second-slide exports are
byte-identical before/after. All edited renders inspected; Office instances closed.
Evidence: `.local/chart-editing-office/result.json`, `check.py`, `check.log` and
`column|bar|line|pie/edited-chart.png`. The first synthetic shared-chart fixture was
rejected by PowerPoint before editing; final Office fixtures use independent native
charts. Shared-part isolation is Core evidence, not PowerPoint acceptance. Broad
chart/enterprise corpus fidelity and native edit-data workbook UI remain unverified.

Dirty worktree preserved; no commits/pushes, packaging, accounts/model calls,
downloads or releases. Next: chart/table geometry and richer object/structural
editing GUI, then broader fidelity/integration/human acceptance. Real fast-decision
calibration/latency and live Sign in with ChatGPT remain open. Signing and clean
Windows validation remain accepted debt; full master/theme editing stays deferred.

## Prior continuation - reviewed native chart creation

Slide actions & layout now offers Insert native chart. Draft a column, bar, line
or pie chart, title, category/series names, values and placement, then preview the
actual staged PPTX, explicitly review and save one revision. Draft changes clear
approval; discard leaves the baseline unchanged; saving refreshes retrieval; undo
restores the complete prior deck. The chart is a native editable graphic frame
with its own embedded literal-data workbook, not a chart image. Limits: 1–24
categories, 1–6 series, names 80 characters, title 120, finite values within ±1e12.
Pie charts require one nonnegative series with a positive total. New IPC and
transaction operation: create_chart (22 native transaction types). No migration;
project schema remains 17. Provider edit-plan schemas remain unchanged.

Dependencies considered: current-head/source verification, native shape identity,
geometry and object bounds, fresh slide/chart/workbook relationships and content
types, cache/workbook consistency, unrelated package parts/objects/notes, literal
formula/URL-like labels, staged exact-byte commit, draft invalidation, cleanup,
reindex/undo and read-only cached chart text. python-pptx generates only a tiny
owned chart fixture; imported decks stay under verified native XML/archive copy.
The generated XLSX contains literal strings/numbers, no formulas/external links.
Cache text includes supplied labels/values without inferred trends or external
workbook access. Unsupported/stacked/combo/missing-cache charts stay outside this
bounded reader. Existing chart data/geometry editing, other chart types, structural
table changes, broader object workflows and corpus/human acceptance remain open.

Validation evidence: focused 23 Core chart cases passed in 2.81 seconds at
`.local/native-charts-focused-final-20261003.log`. Covers four native chart types,
package preservation, cache/workbook literal labels, staged apply, searchable data,
undo, numeric/pie/name bounds, fractional precision, enormous integer rejection,
unsupported stacked/combo/cache-gap cases and negative line values. Four desktop
adapter tests verify authored-pie palette isolation and unsupported/imported skip.
Final pnpm check passed formatting/lint/types, 121 desktop and 702 Core tests
in 127.29 seconds: `.local/native-charts-check-final-20261003.log`.
Electron passed 55 workflows at `.local/native-charts-ui-final-20261003.log`, including
line/column/pie preview, edited-value approval invalidation, discard, reviewed save,
retrieval refresh and undo. Inspected `workspace-native-chart-column.png` and
`workspace-native-chart-pie.png` in `.local/ui-validation`. Screenshot inspection
caught a pie legend palette mismatch/title overlap; a bounded chart-local preview
adapter now aligns authored-pie legends with direct slice colors and explicit title
placement separates the text. Imported charts/themes remain untouched. Pie plot
spacing still differs from PowerPoint, so this is not pixel-fidelity acceptance.

PowerPoint opened and exported four two-slide fixtures across 4:3/16:9, verified
native charts and exact chart types, series counts/cache values, title, placement
and retained notes, and left file hashes unchanged. All renders inspected; fixture Office instances
closed. Evidence: `.local/native-charts-office/result.json`, `check.log`, and
`column-chart.png`, `bar-chart.png`, `line-chart.png`, `pie-chart.png`. This proves
these fixtures, not arbitrary imported charts or enterprise corpus acceptance.
Dirty worktree preserved; no commits/pushes, packaging, accounts/model calls,
downloads or releases. Next: remaining substantial chart/table/object GUI workflows,
then broader fidelity/integration acceptance. Real fast-decision calibration/latency,
human preparation acceptance and live Sign in with ChatGPT remain open. Signing
and clean Windows validation remain accepted debt; full master/theme editing deferred.

## Prior continuation - reviewed native tables and imported cell editing

Slide actions & layout now offers Native tables. The dialog inserts a native table
with bounded row/column drafts, first-row header styling and explicit placement,
or selects an existing supported table and edits its cells. Both use exact staged
package preview, explicit review and one-revision commit. Draft changes invalidate
approval; discard restores rendering; save reindexes and whole-revision undo works.
Cell editing keeps dimensions, native geometry, cell fills/borders, font/paragraph
styling, object identity and unrelated package parts. Creation writes one direct
editable DrawingML table rather than an image or a grid of text boxes. Imported
packages stay under verified native XML/archive readers; no imported deck rewrite
through python-pptx. No migration; project schema stays 17. New IPC methods are
list_tables/create_table/replace_table_cells. Native transactions support both
operations; existing provider schemas are unchanged.

Dependencies considered before edits: verified native source/revision ownership,
DrawingML table-type URI, row/grid consistency, merged/link/complex-cell detection,
full-frame fingerprints, style-preserving paragraph replacement, fresh shape IDs,
geometry bounds, unrelated slide/notes/package preservation, staged exact bytes,
dialog rendering/cleanup, draft invalidation, reindex, undo, IPC capability fixtures,
semantic text context and current-head races. Existing table styles and widths are
preserved on text edits. Unsupported tables stay read-only with a reason. Limits:
1–12 rows, 1–8 columns, 500 characters/10 paragraphs per cell, 10000 per table;
selection currently lists at most 20 direct native tables on the selected slide.
Merged/grouped/mixed-run/linked/extended tables and structural row/column edits,
existing-table resize/move and generic object delete/duplicate/layering remain open.
Supported cell text now appears in fidelity inventory for semantic/reasoning context;
normal PPTX reindexing makes the edited table searchable and available for rehearsal.

Validation: final pnpm check passed formatting/lint/types, 117 desktop and 679 Core
tests in 114.89 seconds: `.local/native-tables-check-final-20261003.log`. The earlier
run passed 674 cases but failed the protocol ready-event fixture, whose capability
method list needed the new methods; both shared capability examples are now updated.
Focused final table tests passed 24 in 2.75 seconds before one added invalid-XML
character case; all 25 pass in the final full suite. Evidence:
`.local/native-tables-focused-final-20261003.log`. Coverage includes unchanged
existing package parts/styles/dimensions and native IDs, staged creation, multiline
cell edits, retrieval text, no-op, stale fingerprints/head, source corruption,
creation limits/geometry, imported custom font/width preservation, read-only complex
cells and two-step undo. An initial reindex failure exposed an incorrect graphic
URI in new XML; corrected against the installed native parser. No release claim
is made from that initial run.

Electron passed 54 workflows: `.local/native-tables-ui-20261003.log`. New case covers
row/cell drafts, preview, edited-draft invalidation, discard, reviewed creation,
persisted discovery, multiline cell editing, retrieval refresh and undoing edit and
insertion separately. Inspected `.local/ui-validation/workspace-native-table-edit.png`.
The table draft grid scrolls horizontally for wider tables and uses row/column
accessible labels. PowerPoint opened 4:3 and 16:9 native table creation/edit fixtures,
verified genuine 3x3 table cells, multiline edit, header font, placement and preserved
notes, exported renders and retained input hashes. Evidence:
`.local/native-tables-office/result.json`, `standard-table.png`, `wide-table.png` and
`.local/native-tables-office-20261003.log`; both renders inspected. This proves these
two fixtures plus one imported-table Core case, not arbitrary enterprise tables,
merged-cell editing or wider corpus fidelity. All validation processes completed
and fixture Office instances were closed. Dirty worktree preserved; no commits,
pushes, packaging, accounts/model calls, downloads or releases.

Next: remaining substantial native authoring GUI (structured chart creation and
richer table/object workflows), then broader corpus fidelity/integration acceptance.
Human preparation acceptance, real fast-decision calibration/latency and live Sign
in with ChatGPT remain open. Signing/clean Windows validation remain accepted debt.
Full master/theme editing remains explicitly deferred in the roadmap.

## Prior continuation - native layout slide creation with editable placeholders

Slide actions & layout now offers Insert from native layout. Choose a verified
native layout, draft each supported text slot and speaker notes, render the new
slide, acknowledge review, then save exact staged bytes as one revision. Creation
inserts after the selected slide, selects the new slide, reindexes and supports
whole-creation undo. Text/notes/layout changes invalidate approval; discard retains
the original revision. A committed plan cannot be resubmitted after refresh failure.
The native catalog exposes bounded opaque placeholder IDs, names/types and creation
capability. Up to 20 text slots, 2000 characters and 20 paragraphs per slot are
supported. Native title/body/content placeholder identity and inherited theme
styling are retained. Geometry is resolved from the layout or one matching master
placeholder, materialized locally and checked for simple in-bounds editability.
Grouped, ambiguous, rotated, out-of-bounds or malformed text slots disable creation.
Dates/footer/slide-number/image/chart placeholders are not instantiated by this
text creation workflow. Existing blank/source-slide and authored-template callers
retain their behavior; provider schemas are unchanged. No migration; schema 17.

Dependencies considered before edits: verified snapshot/opaque native catalog,
layout/master geometry and style inheritance, placeholder identity/unique shape IDs,
native package insertion/order/relationships, paragraph limits, new notes attachment,
shared authored insertion, staged exact hash review, draft invalidation, restoration,
reindex, undo and later created-target references. Existing package parts stay
byte-identical except insertion metadata. No imported package is rewritten with
python-pptx. Only our tiny generated notes package is copied into the verified deck.

Office acceptance caught a pre-existing authored notes dependency: adding a new
registered notes master while existing slides retain another master makes some
PowerPoint decks fail to open. The shared notes merger now reuses the verified
existing internal notes master without changing its XML/theme/declaration. It adds
a fresh master/theme only when none exists; ambiguous/external/missing or mismatched
notes master metadata rejects creation. This fixes both native and authored insertion.

Validation: full pnpm check passed formatting/lint/types, 117 desktop and 652 Core
tests in 130.96 seconds: `.local/native-create-check-final-20261003.log`. Final
malformed-index/foreign-transform cases and focused layout/authored/transaction
checks passed 59 in 18.85 seconds: `.local/native-create-focused-reviewed-20261003.log`.
Core lint/mypy and git diff --check passed after those final guards. Cases cover
five-slot Comparison content, multiline paragraphs/notes, unchanged existing parts,
atomic exact-hash save/undo, empty slots, later created-target note edits, invalid
IDs/duplicate/foreign slots/bounds, unsupported geometry and notes master reuse/
allocation/ambiguity. The earlier full run passed 648 before the notes-master fix;
the final full run covers that fix. Next full baseline is 654 Core tests.

Electron passed 53 workflows in `.local/native-create-ui-final-20261003.log`, including
native slot discovery, drafting, preview, edited-draft invalidation, discard, save,
new-slide selection and undo. Inspected `.local/ui-validation/workspace-native-slide-preview.png`.
An initial GUI assertion incorrectly waited for an option to be visible; it now
waits for attachment. A later repeat after submit guards timed out in the earlier
alignment undo workflow before native creation. The isolated final rerun passed
all 53 workflows: `.local/native-create-ui-complete-20261003.log`. All validation
processes completed and fixture PowerPoint instances were closed.

PowerPoint opened three native Comparison fixtures (4:3, 16:9 and first notes master),
verified three slides, five text slots, multiline text and notes, exported native
and independently created reference slides, and left package hashes unchanged.
All three native/reference render pairs have zero pixel difference. Existing
authored insertion also opens and retains notes after the shared fix. Evidence:
`.local/native-create-office/result.json`, the `*-native.png` and `*-reference.png`
files and `.local/native-create-office-final-20261003.log`; all native/authoring fixture and GUI renders inspected. This proves these generated fixtures, not arbitrary enterprise
master/notes styling or corpus fidelity. No external account/model calls or releases.

Next: remaining substantial native authoring GUI (for example bounded table creation),
then corpus fidelity and integration acceptance. Full master editing is explicitly
deferred in the roadmap. Existing-object placeholder remapping, layout thumbnails,
human preparation acceptance, triage calibration, measured fast-decision latency and
live Sign in with ChatGPT remain open. Signing/clean Windows validation remain
accepted debt. Dirty worktree preserved; no staging/commits/pushes/packaging/downloads.

## Prior continuation - reviewed native master/layout selection

Slide actions & layout now offers Browse native layouts from referenced presentation
masters, including layouts no slide uses. Catalog shows bounded names, master/theme
labels, placeholder counts and current usage. Opaque document-scoped UUIDs expose no
package path. Existing apply_slide_layout accepts either source-slide ID or native
layout ID, never both. The GUI uses the existing staged-package review: choose,
render native preview, acknowledge, then commit exact reviewed bytes as one revision.
Selection changes invalidate approval; discard restores current rendering; save
reindexes; undo restores the original relationship. No-op application adds no revision.
A committed plan cannot be resubmitted if later refresh fails.

Dependencies considered before edits: managed snapshot ownership/hash/size, catalog
master/layout relationship types and internal targets, reverse master consistency,
stable opaque IDs, layout reuse and existing source-slide callers, native writer
invariants, staged read/hash/commit authority, renderer ownership/restoration,
selection invalidation, reindex and undo, current-head races and package corruption.
Catalog caps at 500 layouts and rejects malformed/duplicate/missing/external or
mismatched links. Writer alters only the target slide layout relationship and
validates unchanged content, IDs/order and notes. It adds no placeholder remapping,
new slide objects or master rewrite. Existing provider layout schema is unchanged.
No migration; project schema remains 17.

Validation: full `pnpm check` passed format/lint/types, 117 desktop and 632 Core
tests in 113.30 seconds: `.local/native-layout-check-complete-20261003.log`. Initial
focused layout/transaction tests passed 29 cases; final additional catalog race/
corruption checks passed 31 in 9.40 seconds:
`.local/native-layout-focused-final-20261003.log`. Cases include unused layouts,
review-only staging, exact preview hash commit, unchanged native parts/content/order,
no-op and undo, invalid IDs/choices, external/mismatched/duplicate references, snapshot
corruption and head changes during catalog read. An early full run collected the
old test's preview-open method name; the corrected focused and full runs pass.
Electron passed 52 workflows (`.local/native-layout-ui-reviewed-20261003.log`). New
case covers discovery, unused choices, preview, changed-choice invalidation, discard,
reviewed save and undo. Test placement was corrected to a loaded deck and expands
the normal Slide actions & layout section. Inspected
`.local/ui-validation/workspace-native-layout-preview.png`. Final GUI rerun after
the post-save guard passed 52 workflows; TypeScript, targeted lint and 117 desktop
tests passed after the guard (`.local/native-layout-desktop-final-20261003.log`).
`git diff --check` passed.

PowerPoint opened a generated two-slide deck after applying unused Comparison,
verified title/points/notes and slide count, exported slide 1 and left the PPTX hash
unchanged. Evidence: `.local/native-layout-office/result.json`, `slide-1.png` and
`.local/native-layout-office-20261003.log`; render inspected. This proves that one
fixture, not master-wide fidelity or the release corpus. No external account/model calls.

Next: native-layout-based slide creation and remaining substantial authoring GUI
workflows, then corpus fidelity/integration acceptance. Master editing, placeholder
remapping and layout thumbnail comparison remain open. Human preparation acceptance,
triage calibration, measured fast-decision latency and live Sign in with ChatGPT
remain open. Signing/clean Windows validation remain accepted debt. Dirty worktree
preserved; no commits, pushes, packaging, model downloads or releases.

## Prior continuation - takeaways in reviewed provider context

Copilot editing, narrative analysis and Challenge question/follow-up/evaluation
now include saved takeaway intent from their concrete verified native revision.
The internal historical reader maps ordinals to stable slide IDs from that revision,
checks project/document ownership and package integrity, and follows parent-only
semantic lineage. Context contains at most five selected slides, 240 characters
per takeaway, and 3200 serialized characters including escaping and metadata.
Omitted selection, shortened text and bounded missing history are explicit. Exact
reviewed versus inherited status and source revision are retained. Reviewed blanks
stop prior text returning; absent takeaways add no intent section.

Dependencies considered before edits: current editing scope versus frozen Challenge
revision, native identity/integrity, claims/narrative packet merging, citation pruning,
privacy and complete-answer budgets, optional context drop order, content-free
audits and captured-proposal review. Takeaways are untrusted author intent, never
evidence, citations or commands. Existing privacy/citation/budget controls remain
in force. Copilot review lists the captured slide text/status and shortening/
incomplete notices separately from evidence. Later semantic saves do not update
an already prepared proposal. No migration or native edit; schema remains 17.

Validation: `pnpm check` passed format/lint/types, 117 desktop and 623 Core tests
(127.70 seconds): `.local/takeaway-context-check-20261003.log`. Focused context/
narrative/claim checks passed 24 tests in 6.79 seconds:
`.local/takeaway-context-focused-20261003.log`. Final mixed claim/intent extension
and context checks passed six tests in 8.84 seconds:
`.local/takeaway-context-mixed-final-20261003.log`; Core lint passed afterward.
Cases cover captured intent surviving later saves and evidence pruning, no intent
citations/audit text, frozen Challenge question/answer context after a real head
edit, inherited/shortened status, explicit clears, foreign/missing revisions, corrupt
packages, local-only provider rejection, six-slide truncation and serialized escape
bounds. Electron passed 51 workflows (`.local/takeaway-context-ui-final-20261003.log`)
including Copilot captured intent assertions. Inspected
`.local/ui-validation/workspace-copilot-takeaway-context.png`; captured takeaway,
narrative and claim sections are readable. Final GUI script format/lint and
`git diff --check` passed. Disposable fixtures establish transport and GUI behavior, not model
quality, account integration or measured preparation usefulness.

Next: substantial remaining native authoring workflows, including unused theme/layout
selection, then corpus fidelity and integration acceptance. Run/debrief use of
takeaways and automatic semantic refresh remain open. Human preparation acceptance,
triage calibration, measured fast-decision latency and live Sign in with ChatGPT
remain open. Signing/clean Windows validation remain accepted debt. Dirty worktree
preserved; no commits, pushes, packaging, model downloads, account calls or releases.

## Prior continuation - persistent reviewed slide takeaways

Purpose now records the audience takeaway per stable native slide and revision,
with manual drafting, clear/reload and explicit review acknowledgment. Narrative
finding navigation opens the exact slide with an unconfirmed candidate; a separate
Use finding as takeaway draft copies it. Correction and reviewed save are separate.
Saved takeaways are author intent, not evidence, purpose labels or native slide text.
Deck review displays retained text and flags inherited takeaways for review. No
provider call or deck revision is created by takeaway save/read.

Dependencies considered before edits: immutable revision ownership, stable native
slide IDs/ordinal binding, managed source verification, current-head races, competing
semantic saves, parent-only inheritance, blank clears and undo/branch semantics,
migration of old intent/claim records, IPC allowlists, proposal-versus-draft behavior,
asynchronous remount scope and existing deck attention filters. Project schema 17
adds revision/slide-keyed takeaway records with a composite ownership foreign key,
unique record token and 1000-character text bound. Reads cap ancestry at 100 and
report missing history. Inherited text is provisional. A reviewed blank save stops
older text returning; concurrent unseen saves reject atomically until reload.
Deck review reuses its verified inventory; takeaway reads add no package inspection.

Validation: focused takeaway/narrative/deck/storage checks passed 39 tests:
`.local/takeaway-focused-20261003.log`. Extended bounded-history and takeaway cases
passed 12 tests (3.41 seconds): `.local/takeaway-history-20261003.log`. They cover
persistence, conflict rejection, current-versus-inherited intent, explicit blank
clear, undo and branch isolation, native scope/invalid inputs, migration and missing
100-parent history. Full `pnpm check` passed format/lint/types, 117 desktop and
617 Core tests (120.69 seconds): `.local/takeaway-check-complete-20261003.log`.
Earlier runs exposed old added-table/future-version fixture expectations; these
were updated and the two migration cases passed independently. After the final
GUI request-generation guard, TypeScript/lint and 117 desktop tests passed again.
The guard rejects late initial/reload/save responses, including development Strict
Mode's repeated initial read. The final GUI run with that guard passed.
Electron passed 50 workflows: `.local/takeaway-ui-complete-20261003.log`. New workflows
exercise finding navigation without copying, explicit draft use/correction/reviewed
save/reload, real-edit inheritance, draft clear/reload, blank reviewed save and deck
review refresh. Inspected `.local/ui-validation/workspace-reviewed-slide-takeaway.png`
and `workspace-inherited-slide-takeaway.png`; controls/text are readable. Final
GUI script formatting/lint and Core lint passed.

Next: use reviewed slide takeaways in bounded provider and rehearsal context, richer
semantic authoring workflows, then corpus fidelity and integration acceptance.
Live narrative quality, human preparation acceptance, triage calibration, measured
fast-decision latency and live Sign in with ChatGPT remain open. Signing/clean
Windows validation remain accepted debt. Dirty worktree preserved; no commits,
pushes, packaging, model downloads, account calls or releases.

## Prior continuation - review-only narrative analysis

Narrative now offers explicit provider analysis of the current verified native
deck and unsaved intent. The user selects an instruction and contiguous range
of 1-40 slides. Core supplies at most 600 text/120 notes characters per slide,
permitted grounding and reviewed claim context under the shared budget/privacy
boundaries. Strict output proposes all six intent fields and at most 12 slide
role/takeaway/issue/action findings. Only supplied slide IDs and evidence IDs are
accepted. Review discloses partial coverage, shortened excerpts and unexamined
visuals. Request leaves the draft unchanged; Use copies fields and clears review
acknowledgment; reviewed save remains separate. Finding navigation opens existing
Purpose controls. No finding labels, native edits or revisions are saved by analysis.

Dependencies considered before edits: verified package/hash/current-head inventory,
unsaved draft versus saved intent, optimistic record tokens, provider capabilities/
strict schemas, bounded context and citation pruning, privacy acknowledgment,
content-free run audits, inference-time state changes and asynchronous GUI draft
life cycle. Core checks head/package/token/privacy before and after inference.
Focused tests exposed that shared execution checks privacy before inference only;
this service adds its own postflight rejection. Existing tasks retain their behavior.
Local structured output gets a 4096-token budget for this task; API and ChatGPT-plan
use existing adapters. No migration; project schema remains 16.

Validation: full `pnpm check` passed format/lint/types, 117 desktop and 606 Core
tests (104.55 seconds): `.local/narrative-analysis-check-final-20261003.log`.
Focused narrative/planning/claim-context checks passed 40 tests:
`.local/narrative-analysis-focused-20261003.log`. Coverage includes draft/save
separation, exact native scope, invalid role/field/slide/citation output, concurrent
head/intent/privacy changes, corrupted packages, range/shortening disclosures and
strict local-provider loopback transport. The loopback fixture validates schema,
4096-token budget and absence of tools; it is not real model inference. Electron
passed 48 workflows: `.local/narrative-analysis-ui-final-20261003.log`, including discard,
explicit use, finding navigation, separate reviewed save and unchanged deck revision.
Inspected `.local/ui-validation/workspace-narrative-suggestion-review.png` and
`workspace-narrative-suggestion-controls.png`; no horizontal overflow. Final GUI
script formatting/targeted lint and `git diff --check` passed. Disposable fixtures
establish GUI and transport behavior, not inference quality.

Next: persistent reviewed slide takeaways and richer semantic authoring workflows,
then corpus fidelity/integration acceptance. Narrative quality, human preparation
acceptance, triage calibration, fast-decision latency and live Sign in with ChatGPT
remain open. Signing/clean Windows validation remain accepted debt. Dirty worktree
preserved; no commits, pushes, packaging, model downloads, account calls or releases.

## Prior continuation - paged deck semantic review

Deck review in Slide studio now presents the verified native slide order, titles,
current or inherited purposes, user-recorded claim coverage and attention reasons.
It pages 20 slides at a time (Core accepts 1-25), filters attention items on the
displayed page, refreshes current semantic state and opens the exact slide in the
existing Purpose/claim/evidence review controls. Returning to the panel refreshes
its current page; revision changes remount the review. Results/controls are scoped
to project/document/revision and stale requests cannot replace a newer page.
No provider request, semantic save or deck revision is created by browsing.

Counts apply to the displayed page and existing user-reviewed claims. No recorded
claims is explicitly separate from unsupported claims or automatic extraction.
A prior purpose is a suggestion for review, never an exact-revision confirmation.
Current conflicting/unlinked links, stale/inherited spans and missing purposes
produce distinct attention reasons. Purpose/claim ancestry is limited to parent
lineage (100 ancestors), and incomplete native text/history coverage stays visible.
Claim removal and undo retain their existing revision-local semantics.

Dependencies considered before edits: snapshot project ownership, managed paths,
preflight/hash/length checks, current-head reads, stable slide/object IDs, bounded
native inventory and ancestry, per-page versus full-deck counts, claim evidence
freshness/tombstones, final-head recheck, asynchronous page lifecycle and opening
existing write controls. The text-target reader now shares an internal verified
revision inventory helper. Each deck page inspects the PPTX once and reuses its
native targets; it does not reread/reinspect the package for each slide. Historical
Challenge reads remain internal and verified. The helper is not an IPC method.
No storage migration was needed; project schema remains 16.

Validation: `pnpm check` passed formatting/lint/types, 117 desktop and 590 Core
tests (105.47 seconds): `.local/deck-review-check-20261003.log`. Focused new page,
workspace-source, claim and provider-context checks passed 68 tests:
`.local/deck-review-focused-20261003.log`. A final existing deep-history case was
extended to assert deck-level incomplete status; it and page/claim checks passed
13 tests: `.local/deck-review-history-20261003.log` (format/lint passed afterward).
Cases cover one inspection per page, counts/pagination, no provider/revision writes,
exact and inherited purposes, changed source/conflicting evidence, tombstones,
undo, scope/offset validation, package corruption and revision change during read.
Electron passed 47 workflows: `.local/deck-review-ui-20261003.log`. The new cases
filter reviewed slide 1 out of attention, page to/open slide 21, return/open slide 1,
retain its reviewed claims and flag inherited purpose/claim after a real text edit.
Inspected `.local/ui-validation/workspace-deck-review-page.png` and
`.local/ui-validation/workspace-deck-review-inherited.png`. Overflow check passed;
`git diff --check` passed. Disposable developer fixtures prove GUI flow, not model
quality, human preparation acceptance or Office fidelity.

Next: automated narrative/authoring analysis and richer slide semantic workflows,
then corpus fidelity and integration acceptance. Human-labeled triage calibration,
fast-decision latency and live Sign in with ChatGPT acceptance remain open. Existing
decision/auth adapters are unchanged. Signing and clean Windows validation remain
accepted debt. Dirty worktree preserved; no commits, pushes, packaging, model
downloads, account calls or releases.

## Prior continuation - reviewed presentation narrative and provider context

The Workspace now has a Narrative editor for objective, target audience, desired
decision/action, thesis, narrative arc and constraints. Panel navigation preserves
unsaved drafts. Saving requires review acknowledgment and uses the current
revision plus a record token to reject concurrent changes. Save does not create
a deck revision or modify native content. Clear narrative draft is reversible
until reviewed save; saving empty fields explicitly clears intent and stops older
parent intent from resurfacing. Reload explicitly restores saved intent.

Project schema 16 adds revision-scoped narrative records with a composite revision/
presentation foreign key. Only parent ancestry is followed, capped at 100; other
branches and later revisions never supply intent. Inherited intent requires
review. Undo restores intent for the selected historical revision, and new edits
from that point follow that branch. Missing history is explicit. New migrations
preserve prior claim/evidence and project rows. No automatic extraction, narrative
analysis, AI narrative generation or full-deck semantic coverage is implied.

Copilot edit planning and Challenge include bounded narrative intent from their
concrete revision. Challenge reads its frozen revision even after the Workspace
head/intent changes. Narrative fields are user-authored intent, never evidence,
citations or application instruction. The packet caps each ordinary field at
240 characters, arc/constraints at 480 and the full serialized narrative at 3200
characters, including escaping/metadata; shortened fields are listed. Shared
context/privacy/budget boundaries and claim grounding/pruning remain in force.
Copilot review displays captured intent and inherited/shortened/incomplete status.
Captured context is the preparation snapshot; later semantic edits do not
automatically invalidate an already prepared plan.

Dependencies considered before edits: schema migrations and old-project fixtures,
project/revision ownership, current-head writes versus historical context reads,
parent lineage and undo branches, save conflict detection, explicit clears,
privacy/context/citation budgeting, typed IPC allowlists, draft and stale response
lifecycle, GUI styling/overflow and captured proposal review. Fast decisions and
Sign in with ChatGPT adapters remain on their existing execution/auth boundaries.
No live account or model-quality acceptance occurred in this increment.

Validation: `pnpm check` passed formatting/lint/types, 117 desktop and 581 Core
tests (123.55 seconds): `.local/narrative-check-final-20261003.log`.
Focused narrative/context/storage/claim
checks passed 31 tests (`.local/narrative-focused-final-20261003.log`), followed
by 91 narrative/history/migration/Challenge checks including the ancestry limit
(`.local/narrative-history-focused-20261003.log`). First GUI run caught an async
reload test reading before its response; it now waits for the restored input.
Screenshot inspection caught default buttons/stretched acknowledgment; final
styling uses existing button classes and compact checkbox. Final Electron run passed 45 workflows:
`.local/narrative-ui-complete-20261003.log`. Both editor and controls screenshots
were inspected: `.local/ui-validation/workspace-reviewed-narrative.png` and
`.local/ui-validation/workspace-reviewed-narrative-controls.png`. Latest screenshot/
overflow test additions passed targeted ESLint, and `git diff --check` passed. New flow checks saving all six
fields, retained drafts, required review, unchanged deck revision, inherited
intent, clear/reload and captured intent alongside claim grounding in Copilot.

Next: substantial deck-wide semantic coverage and narrative/authoring analysis,
then corpus fidelity/integration acceptance. Human-labeled triage calibration,
fast-decision latency and live Sign in with ChatGPT acceptance remain open.
Signing and clean Windows validation remain accepted tech debt. Dirty worktree
preserved; no commits, pushes, packaging, downloads, account calls or releases.

## Prior continuation - finite claim/excerpt triage with explicit review

The Purpose panel can request a finite supports/contradicts/context/unclear
suggestion for one exact current object quote and one linked current source
excerpt. Requesting never changes the draft relation; Use suggested relation is
separate, clears the acknowledgment, and Save reviewed claim still requires
explicit review. Missing confidence and below-threshold answers abstain. UI
labels confidence uncalibrated and thresholds provisional; model confidence is
not evidence quality or calibrated probability. Manual relations remain available.

Dependencies considered before edits: exact quote uniqueness, current immutable
revision and native object identity, source project/readiness/hash, privacy before
and after inference, provider/model identity, typed IPC allowlists, shared
slide-purpose execution, content-free audit completion, and user-owned semantic
writes. The shared decision path now audits each actual task type; regressions
caught and repaired completion filtering that left new triage runs started.
Triage rechecks the quote/object/excerpt before and after inference. It never
creates claims, revisions or support proofs. Local-only routing blocks remote
providers. Existing selected fast decision adapters, including Sign in with
ChatGPT, serve this task without a second authentication/configuration path.
No live account acceptance is implied.

A new `pnpm benchmark:claim-triage-local` diagnostic exercises 20 authored
synthetic cases, including negation, units, time/population scope, estimates,
causality and embedded commands. It reports raw accuracy, selective accepted
precision, coverage, abstention, accepted false-support errors, model identity,
median/p95 latency and metadata-only per-case outcomes. It uses already-running
loopback models and stops on transport failure. This is not an independently
human-labeled corpus or production gate. Fixture tests verify metric accounting,
including wrong high-confidence support; they do not establish model quality.
The host Ollama probe was unavailable, and the diagnostic timed out on its first
case with zero valid responses: `.local/triage-local-acceptance-20261003.log`.
No quality or latency measurement is available from that attempt.

Validation: `pnpm check` passed formatting/lint/types, 117 desktop and 568 Core
tests (114.24 seconds): `.local/triage-check-final-20261003.log`.
Focused shared workflow checks passed
63 tests: `.local/triage-focused-20261003.log`; the final triage/metric set passed
19 tests: `.local/triage-metrics-20261003.log`. Electron passed 43 workflows:
`.local/triage-ui-20261003.log`, using an explicit developer-only finite response
fixture guarded by both DEV_MODE and TEST_DECISION flags. The new flow proves
requesting preserves the manual relation, separate use changes only the draft,
and reviewed save remains explicit. Inspected screenshot:
`.local/ui-validation/workspace-claim-evidence-triage.png`.

Next: substantial narrative/deck-wide semantic and authoring workflows, then
corpus fidelity and integration acceptance. Human-labeled triage calibration,
fast-decision latency and Sign in with ChatGPT live acceptance remain open.
Signing and clean Windows validation remain accepted tech debt. Dirty worktree
preserved; no commits, pushes, package rebuilds, model downloads or account calls.

## Prior continuation - reviewed claim context for Copilot and Challenge

Reviewed claims now inform Copilot edit planning and Challenge question/follow-up/
evaluation context. Linked current excerpts receive priority after canonical
question grounding, inside ordinary document evidence limits. Relations remain
user judgments, never automated proof. Inherited or stale links do not establish
current support. Changed/missing object quotes and stale evidence snapshots are
excluded from the provider packet; current exact quote excerpts are bounded and
shortened explicitly. Citation IDs exist only for excerpts actually supplied
after context pruning. Rehearsal privacy routing and the provider boundary remain
in charge; claim reads do not authorize sending local-only content remotely.

Challenge uses its frozen presentation revision even after Workspace edits.
An internal immutable-revision text-target reader verifies the exact saved PPTX
hash/length. GUI claim writes and ordinary text-target reads retain current-head
checks. Provider context reads exact revision/parent semantics, verifies current
linked chunk hashes, and records the frozen revision in content-free context
manifests. No raw historical/stale excerpt bodies are injected. Copilot proposal
review shows captured claim coverage, stale/unchanged object state and whether
linked excerpts were supplied; review is captured at preparation, not a promise
that later source/semantic changes invalidate a staged proposal automatically.

Dependencies considered before edits: historical versus current-head reads,
verified package identity and source-project scope, parent inheritance, source
reindex/deletion, context budgeting/pruning, canonical question grounding priority,
provider citation validation, privacy routing, provenance manifests, staging and
GUI review ownership. Context inspects at most five selected slides, includes up
to eight claim entries/6000 serialized claim characters and 500-character quote
excerpts, and marks incomplete selection/claim/history coverage. Existing 800-
character excerpts and six-document caps apply. Decks without claims skip native
semantic inspection. Live HUD and typed-decision paths are unchanged.

Validation: `pnpm check` passed format/lint/types, 117 desktop and 549 Core
tests (90.86 seconds): `.local/claim-context-check-20261003.log`. Final Electron
rerun passed 42 workflows: `.local/claim-context-ui-final-20261003.log`. Five new
context cases and related planning/Challenge checks passed 57 focused tests:
`.local/claim-context-focused-20261003.log`. The final shortened-quote GUI label
passed typing: `.local/claim-context-final-types-20261003.log`. New cases cover grounded provider packets/audit source IDs, stale-excerpt exclusion,
actual frozen Challenge generation after an edit, bounded coverage, pruning of
unsupplied citation IDs, revision metadata and local-only remote rejection.
Electron shows captured reviewed support in a native Copilot proposal and discards
without modifying revision 1. One earlier GUI run failed later with a generic
proposal error; a copied-profile Core reproduction succeeded. Core errors now
surface their message in Copilot; the next GUI run passed. Final rerun evidence
is recorded below. No live account/provider acceptance is implied.

Next: typed claim/evidence triage with uncertainty and measured acceptance,
narrative/deck-wide coverage, richer native object/asset GUI workflows. Continue
corpus fidelity and external integration acceptance. Fast decisions and Sign in
with ChatGPT live acceptance remain in scope; signing and clean Windows validation
remain accepted debt. Dirty work preserved; no commits, pushes or packaging.
The full production-readiness goal remains active.

## Latest continuation - reviewed claim spans and evidence coverage

Purpose -> Claims and evidence now binds an exact unique quote to a stable
slide/object ID and code-point range. Local literal-text search finds up to 20
supporting/transcript/note excerpts, excluding the presentation itself. Users
choose up to four links and mark supports, contradicts or context, then explicitly
review before saving. Records snapshot source text/name/hash and whole-object
text hash with user-confirmed provenance; no provider or network request occurs.
Coverage is user judgment, not an automated truth or entailment assessment.

Schema v15 adds revision-scoped claim records and removal tombstones. Claims
inherit through the actual parent chain, never other branches. All inherited
records require fresh review, even if object text is unchanged. Changed/missing
objects and changed/missing source chunks flag needs review. Stale source hashes
or quotes cannot be resaved. Current support and contradiction give supported
and conflicting coverage; context-only/no links remain unlinked. Removal affects
only the current revision; undo restores that revision's own semantic record.
Claim review does not write deck bytes or create a deck revision.

Dependencies considered before edits: immutable PPTX snapshots, stable object
identity, bounded text inventory and ancestry, current-head concurrency guards,
exact span uniqueness, source reindex/deletion, privacy and project isolation,
claim count/evidence budgets, tombstone inheritance, save confirmation, revision
reload and undo, migration preservation and IPC allowlists. Revision ancestry
is bounded to 100 parents; truncated inventory/history explicitly warns the GUI
that the view is incomplete. Limits: 20 claims/slide and four 8000-character
source chunks/claim. This is a reviewed manual model; automatic extraction,
semantic search, entailment triage, narrative analysis, deck-wide coverage and
integration of confirmed bindings into authoring/rehearsal context remain open.

Validation: `pnpm check` passed formatting/lint/types, 117 desktop and 544 Core
tests (86.00 seconds): `.local/claims-check-20261003.log`. Electron passed 41
workflows: `.local/claims-ui-20261003.log`. Final quote-uniqueness hardening and
relation coverage checks passed four focused tests and final static checks:
`.local/claims-focused-20261003.log`, `.local/claims-final-static-20261003.log`. Core checks
persisted records across restart, span/evidence drift, stale revision/hash
rejection, reviewed rebind, removal and undo, invalid inputs, v14 migration with
library preservation, and explicit incomplete status after 102 parent revisions.
Electron saves reviewed support on revision 1 without a deck edit and detects
changed inherited object text after native save to revision 2. Inspected:
`.local/ui-validation/workspace-claim-evidence-needs-review.png`.

Next: integrate reviewed claim/evidence bindings with useful authoring/rehearsal
context and typed decision triage; broader native object and asset GUI workflows
remain open. Then continue corpus fidelity and external integration acceptance.
Fast decisions and Sign in with ChatGPT live acceptance remain in scope. Signing
and clean Windows validation remain accepted debt. Dirty work preserved; no
commits, pushes or packaging. The full production-readiness goal remains active.

## Latest continuation - reusable project picture library

Project pictures now supports local PNG/JPEG upload, paginated thumbnails,
selection into ordinary picture insertion, explicit Copilot attachment and
confirmed library removal. It is available in the Objects panel and Copilot
edit dialog of a loaded presentation. Library data belongs to the project,
independent of deck and revision IDs. The Core API also works before a deck
exists; a standalone pre-deck library management GUI remains open.

Immutable image bytes are content-deduplicated in the project SQLite database.
The additive v14 migration preserves existing project rows. Upload validation
reuses native image insertion limits (4 MiB, one frame, 8192 dimensions/20 MP);
project limits are 200 pictures and 64 MiB. Thumbnails/read bytes undergo hash
and length checks. Lists cap each page at 20 images/16 MiB source input. Duplicate
uploads retain the original name/ID. Removal requires confirmation and the
expected hash. It removes library availability, leaving embedded deck copies
and already-staged native previews intact. Historical decks retain their bytes.

Dependencies considered before edits: project storage migration/rollback,
retention/deletion, immutable content identity, byte validation and thumbnail
budgets, IPC allowlists, project isolation, picker lifecycle/busy coordination,
revision-stale insertion form state, provider context privacy, Core image binding,
exact-preview save and undo. Both deck and project attachments use the existing
18-operation provider contract; only asset metadata reaches the provider. Core
captures uploaded bytes before staging, so a library removal after proposal
preparation does not break review/save. No remote fetching or model download.

Validation: `pnpm check` passed formatting/lint/types, 117 desktop and 540 Core
tests (91.08 seconds): `.local/project-assets-check-20261003.log`. Electron
passed 39 workflows: `.local/project-assets-ui-20261003.log`. New Core cases cover persistence
across restart without a deck, isolation/deduplication, invalid uploads/tampering,
v13 migration preservation/rollback, paginated 200-image capacity, and duplicate
upload at capacity. The planning case deletes its project asset after proposal
preparation, then opens preview, saves the exact hash and undoes. Electron upload,
selection and confirmed removal leave revision 16 unchanged; project attachment
renders a native proposal and attachment removal invalidates approval. Inspected
screenshot: `.local/ui-validation/workspace-project-picture-library.png`.

Next: semantic claim/evidence binding and useful coverage workflows, richer
canvas interaction/grouping and standalone asset management/provenance/usage
metadata. Continue corpus fidelity and external integration acceptance after
substantial Workspace flows. Fast decisions and Sign in with ChatGPT live
acceptance remain in scope. Signing and clean Windows validation remain accepted
debt. Dirty work preserved; no commits, pushes or packaging. Goal remains active.

## Latest continuation - reviewed canvas dragging with grid increments

Canvas object selection now supports dragging one object or the current
multi-selection. A four-pixel threshold separates clicks from movement; modifier
clicks retain additive selection. Ghost outlines follow the proposed group move.
Offsets round to native integer geometry, optionally snap to 0.1-inch increments
(default enabled), and clamp the entire selection inside the slide while
preserving spacing and sizes. Selecting/dragging alone writes no deck bytes.
Only supported in-bounds movable geometry is picked on the canvas.

Release opens Review dragged objects, with named before/after positions in
inches. Preview all changes stages ordinary `transform_object` operations and
renders the native package. Explicit image-loaded review saves all moves as one
revision; normal undo restores them together. Consuming the pending gesture
before revision reload prevents old drags from reopening on a new revision.
Escape, pointer cancel/lost capture and disabled loading/voice state clear the
gesture. Source/revision reload clears selection. Existing click, marquee,
manual geometry, alignment and text/notes review paths remain available.

Dependencies considered before edits: pointer capture/event ordering, click
suppression, image-to-native scaling, source geometry capabilities/bounds,
20-object transaction cap, selection identity, shared preview ownership,
stale preconditions, native save/reindex/undo and pending-dialog lifecycle.
The implementation reuses Core transactions; no new Core method or provider
operation was added. During drag, outlines move; the bitmap changes in the
native review preview. This is reviewed dragging, not live bitmap object motion,
advanced guides/object-edge snapping or serialized grouping.

Five new meaningful desktop tests verify shared translation, size/spacing
preservation, both-edge clamping, grid rounding plus fractional-grid boundaries,
single/zero moves and invalid selections/geometry/nonfinite offsets. Full
`pnpm check` passed format/lint/types, 117 desktop and 535 Core tests (90.70
seconds): `.local/canvas-move-check-20261003.log`. Electron passed 37 workflows:
`.local/canvas-move-ui-20261003.log`. The added case drags two selected objects,
previews snapped native translation with unchanged head, checks acknowledgment,
saves one revision, undoes both moves and verifies revision changes clear
selection. The earlier layering assertion now waits until the refreshed object
inspector is enabled, fixing an old order-read/loading race. Screenshot inspected:
`.local/ui-validation/workspace-canvas-drag-review.png`.

Next substantial gaps include project-wide uploaded assets and semantic/evidence
workflows, with richer canvas interaction/grouping still open. Continue corpus
fidelity and external integration acceptance after those flows. Fast decisions
and Sign in with ChatGPT live acceptance remain in scope. Signing and clean
Windows validation remain accepted debt. Dirty work preserved; no commits,
pushes or packaging. The full production-readiness goal stays active.

## Latest continuation - explicitly attached deck images in Copilot plans

Copilot edit requests now browse deck-picture thumbnails and explicitly attach
up to eight images (16 MiB total). Attached names/dimensions/hashes/formats/IDs
enter the provider context; raw image and thumbnail bytes stay in Core. The
new eighteenth provider operation `create_picture` accepts an attached asset
ID, slide target, geometry and alt text. Core rejects unprovided image IDs,
reads the verified baseline bytes and injects them only into native staging.
Existing slide scope, created-target resolution, exact-preview save and parent
undo apply. Public proposal operations strip injected image data and restore
the opaque asset reference; review displays the source image name and alt text.
Audit/provider context checks confirm no image bytes leak into those records.

Attachment changes invalidate save when the current set differs from the
proposal. Attached items can be removed and a new proposal requested. Browsing
uses the shared deck asset component with an attachment action, leaving direct
image reuse intact. Reading/voice/provider busy states gate proposal controls.
No raw image upload to a provider, model image understanding or new durable
project asset table is implemented here. Metadata is not interpreted visual
evidence; users still review actual native placement.

Dependencies considered before edits: image/source integrity and scope, privacy
routing, context size, strict provider schemas, baseline versus staged image
identities, created-target ordering, Core-only byte binding, public response
sanitization, audit fields, shared asset UI lifetime and review invalidation.
No new IPC methods were required beyond the prior read-only asset browser.

All 29 Core planning cases pass, including four new success/unattached/duplicate/
stale cases. They verify metadata-only provider input, no raw image fields in
public proposal or audit, exact preview/SHA save, inserted picture count, atomic
failure and undo. Full `pnpm check` passed format/lint/types, 112 desktop and
535 Core tests (96.98 seconds): `.local/plan-assets-check-20261003.log`.
A final metadata display addition passed typing and focused planning tests.
Electron passed 36 workflows: `.local/plan-assets-ui-20261003.log`. Its added
case attaches a real embedded PNG, renders the native image proposal, requires
review, enables save, removes the attachment to disable save and discards with
unchanged revision. It deliberately does not click image Save; Core proves that
commit/undo path. Screenshot inspected:
`.local/ui-validation/workspace-copilot-attached-picture.png`.
Deterministic provider fixtures prove transport/staging, not live model quality.

Next major gaps: project-wide uploaded assets, direct canvas repositioning,
snapping/grouping and semantic/evidence workflows, followed by corpus fidelity
and external integration acceptance. Fast decisions and Sign in with ChatGPT
live acceptance remain in scope. Signing and clean Windows validation remain
accepted debt. Dirty work preserved; no commits, pushes or packaging. The full
goal stays active.

## Latest continuation - reuse embedded deck pictures

Objects -> Add a picture now contains Browse deck pictures. It shows thumbnails
and dimensions for embedded PNG/JPEG media in the selected current revision,
including layout/master assets. Use an image to fill the existing insertion
form at an aspect-preserving default size; adding it remains a separate action
through ordinary immutable native picture creation. Selection clears obsolete
local file-input/alt-text state. Browsing/selecting invokes no provider and
publishes no revision. Existing local upload remains available.

New read-only Core methods `list_picture_assets` and `read_picture_asset` use
the same scoped current-head lookup and verified archive as editing. Opaque
asset IDs bind package entry names to the snapshot hash; no filesystem paths or
URLs are accepted. Read validates PNG/JPEG bytes through existing 4 MiB,
single-frame, 8192-dimension/20-megapixel limits. Pages cap 20 assets, 100 scanned
entries and 16 MiB decoded input, with a progressing cursor and explicit skipped
counts. Thumbnails cap 128 pixels. Unsupported/invalid/oversized media are
skipped for browsing and rejected for reads. GUI verifies scope, identity, byte
count and content hash, decodes through the existing placement path, ignores
unmounted/stale choices and locks competing local picture controls while reading.

Dependencies considered before edits: snapshot authenticity, scoped revision
ownership, archive/resource limits, local image validators, IPC allowlists and
capability fixtures, component lifetime, image decode races, insertion geometry,
revision/reindex/undo and privacy. No new durable asset table or provider schema
operation was added. This is a deck-local reusable-image workflow, not a
project-wide uploaded asset library or a model image-analysis capability.

Three new Core tests pass: mixed valid/invalid media inventory, thumbnail bounds,
content SHA, reuse on another slide with immutable external original and
untouched slide bytes, 21-image pagination, bad cursors, stale/cross-project or
unknown IDs/paths and snapshot tampering. Full `pnpm check` passed
format/lint/types, 112 desktop and 531 Core tests (85.74 seconds):
`.local/deck-assets-check-20261003.log`. Electron passed 35 workflows:
`.local/deck-assets-ui-20261003.log`. It browses actual embedded media, selects
the replaced 2x2 PNG without a new revision, then inserts it through the ordinary
picture form. Screenshot inspected:
`.local/ui-validation/workspace-deck-picture-assets.png`.

Next: richer reusable/project assets and reviewed image attachment to authoring
plans, direct canvas repositioning/snapping/grouping, semantic/evidence quality,
then corpus fidelity and external integration acceptance. Fast decisions and
Sign in with ChatGPT live acceptance remain in scope. Signing and clean Windows
validation remain accepted debt. Dirty work preserved; no commits, pushes or
packaging. The full production-readiness goal remains active.

## Latest continuation - native canvas object selection

Select objects on slide now enables click and additive Shift/Ctrl/Meta selection
on editable native geometry. Enter/Space supports the same modifiers. Drag from
empty slide space to select intersecting bounds, in either direction; Escape
clears selection. Up to 20 selections get visible outlines and seed Arrange
objects together. The last pick populates the existing Objects inspector fields.
Selection alone does not write deck bytes or invoke a provider. Unsupported
geometry remains available through inventory but is omitted from canvas picking.

New `renderer/SlideObjectCanvas.tsx` scales geometry to the actual displayed
image and observes both image and parent resize, preserving letterbox offsets.
Picking follows package paint order. Slide/revision identity resets selection;
loading/voice ownership disables the overlay. The existing review component
filters incoming canvas picks against current movable targets before opening.
Dependencies considered: native image sizing, inventory capabilities/paint order,
revision identity, inspector geometry/crop/style drafts, shared plan lifecycle,
20-operation cap and accessibility. There is no new Core/provider operation.

`pnpm check` passed format/lint/types, 112 desktop and 528 Core tests (81.36
seconds): `.local/canvas-selection-check-20261003.log`. Electron passed 34
workflows: `.local/canvas-selection-ui-20261003.log`, covering click, Shift add/
remove, keyboard additive selection, inspector targeting, prefilled reviewed
alignment, cancel, Escape, reverse marquee and mode disable. Screenshot inspected:
`.local/ui-validation/workspace-canvas-object-selection.png`. Inspection found
and fixed inherited checkbox sizing. A subsequent intermittent marquee assertion
led to reading final release coordinates directly and scrolling the test canvas
into view; the corrected product's 34 GUI workflows passed. Final typing and
format checks passed after those changes. The test now also awaits selection
state after pointer release rather than assuming synchronous React painting.
A second corrected-product run with that final wait passed all 34 workflows:
`.local/canvas-selection-ui-final-20261003.log`.

This is rectangle geometry picking, not text-character hit testing or support
for rotated/grouped geometry. Canvas drag repositioning, snapping/grouping,
asset flows and semantic/evidence work remain open. Keep fast decisions and
Sign in with ChatGPT live acceptance in scope, followed by corpus fidelity and
integration. Signing and clean Windows validation remain accepted debt. Dirty
work preserved; no commits, pushes or packaging. The full goal stays active.

## Latest continuation - reviewed multi-object alignment and distribution

Objects -> Arrange objects together now offers a selection checklist, six
alignment commands and horizontal/vertical equal-gap distribution. Alignment
uses the selection's original combined bounds. Distribution sorts by coordinate,
keeps the outer positions, handles unequal sizes and rounds native integer
coordinates. Select 2-20 movable objects; distribution needs at least three and
nonnegative gaps. Unsupported geometry is visible but disabled. Invalid,
stale/missing and already-aligned selections fail without publishing changes.

This extends the existing SlideEditReview lifecycle rather than adding another
commit authority. It proposes bounded `transform_object` operations against the
exact current geometry, streams the staged PPTX into the shared native renderer,
requires an image-load check and explicit review, then saves the exact preview
as one revision. Reindex/restore and parent undo remain shared. Dimensions,
styles and paint order remain unchanged. Existing text/notes review still works.
Dependencies checked before edits: object capability/geometry inventory, the
20-operation transaction limit, staged preconditions and rollback, shared
renderer ownership/restoration, revision reload, reindex and undo. No new Core
method or provider schema operation was needed.

New `renderer/object-layout.ts` has 11 meaningful geometry/selection tests:
six unequal-size alignments, unequal-width distribution, integer vertical
rounding, no-change output, unsupported/missing/duplicate/oversized selection
and insufficient spacing. The 20 Core transaction tests pass, including a new
multi-object case that rejects a stale second operation atomically, verifies
preview SHA matches saved revision, preserves object order and undoes the batch.
Fresh `pnpm check` passed format/lint/types, 112 desktop and 528 Core tests
(89.67 seconds): `.local/object-layout-check-20261003.log`. Electron passed 33
workflows: `.local/object-layout-ui-20261003.log`. It checks selection validation,
cancellation, unchanged head during preview, review acknowledgment, one-revision
save and batch undo. Screenshot inspected:
`.local/ui-validation/workspace-object-layout-review.png`. Its native preview
does not prove external PowerPoint fidelity. An existing layering test race was
fixed by waiting for the refreshed object inventory before reading its order.

Next substantial authoring gaps include useful asset flows, canvas selection,
snapping/grouping and richer evidence/narrative work. Current alignment is a
checklist workflow, not canvas drag multi-selection. Keep fast decisions and
Sign in with ChatGPT live acceptance in scope, then corpus integration/fidelity.
Signing and clean Windows validation remain accepted debt. Dirty work preserved;
no commits, pushes or packaging. The full production-readiness goal stays active.

## Latest continuation - native object layering

Supported slide-level shapes and pictures now have Bring forward, Send backward,
Bring to front and Send to back controls in the object inspector. Core validates
the current revision and exact object order, moves only the selected XML node,
preserves its contents and all other package parts, and commits through the
existing revision/CAS path. Boundary moves create no revision. Selection survives
refresh, retrieval is reindexed, and ordinary undo restores the previous order.
Groups, connectors and targets excluded by the existing safe-delete capability
remain unsupported; opaque neighboring nodes keep their relative order.

The provider schema now exposes 17 operations. `change_object_layer` accepts
`forward`, `backward`, `front` or `back`; Core supplies `expected_object_ids` from
the staged snapshot. Earlier-step created-target references work here too, so
layering shares exact staged preview/save and transaction undo with other edits.
Dependencies considered: XML paint order, stable identities, package
relationships, provider scope/preconditions, renderer inventory, revision CAS,
retrieval invalidation and undo. Existing dirty work was preserved.

Four focused Core direction cases pass, covering node contents, unchanged other
parts, boundary no-ops, stale order/revision rejection and undo. The 25 provider
planning tests pass with an added created-target layering step. Full `pnpm check`
passed formatting/lint/types, 101 desktop and 527 Core tests (100.74 seconds):
`.local/object-layer-check-20261003.log`. The later provider test assertion was
checked separately. Electron passed 32 workflows:
`.local/object-layer-ui-20261003.log`, including direct layering, preserved
selection/order, boundary no-op and undo independent of object creation.
Inspected screenshot: `.local/ui-validation/workspace-object-layer-back.png`.
This screenshot does not establish overlapping opaque-object pixel fidelity,
live provider quality or PowerPoint acceptance. No commits, pushes or packaging.

Continue substantial authoring/GUI gaps (assets and multi-object editing), then
semantic/evidence workflows and corpus fidelity/integration acceptance. Keep
fast decisions and Sign in with ChatGPT in scope; their live acceptance remains
open. Signing and clean Windows validation remain accepted technical debt.
The full production-readiness goal remains active.

## Latest continuation — reviewed voice briefing and refinement

New presentation → Plan with Copilot now offers **Dictate briefing** before
proposal and **Dictate refinement** after a draft exists. Core owns an explicit
`intent=outline`, deck-scope capture for the project, with no presentation,
revision, slide or object attached. Supplying deck-target fields is rejected;
existing rewrite/edit-plan intent still requires the exact revision and slide.
The project is verified around capture, and project deletion discards the owner.
No deck, durable session/utterance or ProviderRun is created by dictation.

The shared voice component reviews/corrects the transcript, requires explicit
Use, and fills the briefing (2000-character limit) or refinement (500-character
limit). Propose/refine/create are separate actions. Draft fields, mode switching,
provider actions and outline acceptance lock while capturing or reviewing.
Cancellation/unmount use the existing owner cleanup, including startup races.
TypeScript keeps outline-only and deck-bound props separate. The briefing field
has a stable accessible name after transcript replacement. Objective/audience
remain explicit typed fields. This is not automatic ambiguity resolution or
confidence scoring, and push-to-edit remains open.

Files: `presentation/voice.py`, `renderer/VoiceEditInstruction.tsx`,
`OutlinePlanner.tsx`, `tests/test_presentation_voice.py`, and the Electron script.
Ten focused Core tests pass, including fed synthetic PCM for outline capture
before any deck exists, cross-project rejection, invalid target fields, zero
persistent capture/provider/deck rows, and actual project-deletion cleanup.
Fresh `pnpm check` passed formatting/lint/typing, 101 desktop tests and 523 Core
tests (76.02 seconds): `.local/voice-outline-check-20261003.log`. Desktop lint
and typing passed again after tightening the component's discriminated props.
Electron passed 31 workflows: `.local/voice-outline-ui-20261003.log`. It uses
silent fake capture plus explicit transcript correction, checks cancellation,
control locking, length limits and no briefing mutation before Use, then
proposes/refines/reviews/creates a native deck. The review screenshot was
inspected: `.local/ui-validation/workspace-voice-outline-briefing.png`.
These fixtures do not prove physical microphone recognition, latency, live
ChatGPT or fast-decision quality. No commits, pushes or release packaging.
The full production-readiness goal remains active.

## Latest continuation — coordinated creation targets in one plan

Copilot/native EditPlans now accept `{created_by: N}` in slide/object target
fields, where N is the one-based index of an earlier creation or duplication.
Core resolves actual native IDs from staged outcomes before binding provider
preconditions against the current staged snapshot. A plan can create a slide,
add a text box on it, format the box and position it. Layout-source IDs and
slide-order lists use the same reference resolution. Baseline targets outside
the selection remain forbidden; missing, forward, wrong-kind, cross-slide and
deleted targets fail without publishing a revision or leaving intermediate
packages. Review returns resolved targets; creation IDs join transaction audit
metadata. Final exact preview bytes still save as one revision and undo as a
unit. Provider schema remains strict and path/code/media-free. Displayed slides
now count as viewed only after image decoding and the paint cycle; detached
images cannot satisfy the current review. Screenshot inspection caught a
transient cropped display; the native PNG contained the complete slide.

Files: `presentation/transactions.py`, `edit_planning.py`, `edit_plans.py`,
`providers/edit_plan_schema.py`, `models.py`, `fake.py`,
`renderer/CopilotEditPlan.tsx`, and `tests/test_presentation_edit_planning.py`.
Five new chain cases and existing scope/evidence/privacy/staging checks pass
(25 focused tests). Fresh `pnpm check` passed formatting/lint/typing, 101 desktop
tests and 522 Core tests (77.91 seconds):
`.local/created-targets-check-20261003.log`. Deterministic provider fixtures
exercise coordinated creation; they do not establish live model quality.
Electron passed 30 workflows, including create/style/position, native preview,
one-revision save and whole-creation undo. Evidence:
`.local/created-targets-ui-20261003.log`,
`.local/ui-validation/workspace-copilot-created-callout.png`, and
`.local/ui-validation/workspace-copilot-created-callout-native.png`.

## Prior continuation — recorded rehearsal comparison

Workspace compares two ended deck-bound sessions with debriefs (latest ten in
the GUI). Duration, words, utterances, markers and review-candidate counts have
explicit deltas. Slide speaking time/counts align through verified frozen
revision snapshots and stable IDs. Reordered slides retain correspondence;
absent/deleted slides have no numeric delta. Unmapped counts, differing analysis
versions and potential storage caps remain visible. The comparison is read-only
and rechecks the current head; it does not infer semantic improvement. Core
checks include actual Run markers/debriefs, stale revisions, unrelated sessions,
reordering/deletion, unmapped observations, caps and corrupt identities. Its
previous check passed 101 desktop / 517 Core tests, and its Electron run passed
29 workflows. Evidence: `.local/rehearsal-compare-check-20261003.log`,
`.local/rehearsal-compare-ui-20261003.log`, and
`.local/ui-validation/workspace-rehearsal-comparison.png`.

The production-readiness goal remains active. Worktree has 170 modified or
untracked paths; no commits, pushes, live provider acceptance or release
packaging occurred in these increments. Fast-decision and Sign in with ChatGPT
live acceptance, human preparation, physical ASR, semantic model and fidelity
remain open. Signing and clean Windows validation remain accepted debt.

## Latest continuation — voice requests for general edit plans

The Copilot edit dialog now provides **Dictate Copilot request** for slide or
deck scope. Local Core capture uses explicit `intent=edit_plan` ownership,
validates the exact revision/slide before and after capture, and does not
require a text object. The old selected-text rewrite path retains its target
validation. Scope/proposal/save controls lock during voice capture and review.
An editable transcript requires explicit Use, then the separate Propose action;
dictation itself never calls a provider or publishes a revision. Oversized
instructions require shortening to 500 characters. Cancellation/unmount clean
owned capture; source/project deletion/reset/shutdown retain existing cleanup.

Files: `presentation/voice.py`, `renderer/VoiceEditInstruction.tsx`,
`renderer/CopilotEditPlan.tsx`, `tests/test_presentation_voice.py`.
Nine focused voice tests cover rewrite/slide-plan/deck-plan ownership and
ephemeral transcripts, stale-head cancellation, cleanup, and a blank slide.
The Electron check uses silent fake capture, explicitly corrects its empty
transcript, verifies scope/proposal locking and length limits, then follows
the reviewed instruction through normal generated-plan preview/save/undo.
It does not prove spoken microphone recognition. Confidence scoring,
automatic ambiguity handling, voice creation and push-to-edit remain open.
Fresh `pnpm check` passed 101 desktop and 516 Core tests (79.02 seconds).
`pnpm test:ui` passed 28 workflows; the styled transcript screen was inspected.
After the final GUI terminal-error handling adjustment, TypeScript, lint and
101 desktop tests passed again. `pnpm test:providers-ui` passed synthetic
configuration/inference/persistence/credential-boundary checks. Evidence:
`.local/voice-plan-check-20261003.log`, `.local/voice-plan-ui-20261003.log`,
`.local/voice-plan-providers-ui-20261003.log`. Core speech tests use fed synthetic
PCM; Electron uses silent fake capture plus transcript correction. Neither
proves physical microphone recognition, latency, live model edit quality,
ChatGPT account sign-in/inference or fast-decision quality. Worktree contains
168 modified/untracked paths; no commits, pushes or release packaging occurred.

## Latest continuation — authored insertion into imported decks

**Insert authored slide** now accepts a reviewed title, up to eight points,
notes, template and content layout. It stages native OOXML at the current deck's
dimensions, renders the inserted slide with review above expandable fields,
invalidates approval after draft changes, and saves exact preview bytes as one
revision. Discard removes the private package; undo removes the whole insertion.
The heading and deck picker now show the loaded revision's slide count.

Core reuses the blank-slide allocation/preservation writer, then fills only
the new slide, adding private notes/master/theme parts with fresh relationships.
Existing imported slide, notes and asset parts remain byte-identical. Imported
packages are not reserialized by python-pptx. Title semantics, normal notes/text
editing, indexing and retrieval remain available. Transaction audits include
baseline/new slide IDs without title, points or notes. Copilot's strict schema
now has 16 operation types, including `create_authored_slide`, with reviewable
content/notes and the same scope, evidence, privacy and exact-byte save boundary.
New targets still cannot be referenced by later operations in a provider plan.

Files: `presentation/authored.py`, `presentation/editing.py`,
`providers/edit_plan_schema.py`, `renderer/InsertAuthoredSlide.tsx`, and
`tests/test_presentation_authored.py` (eight integration variants).
One additional provider-plan test covers authored staging, save and audit.

Fresh full check passed 101 desktop / 511 Core tests (88.80 seconds). After the
last GUI-only changes, formatting/lint/TypeScript/mypy and 101 desktop tests
passed again. Electron passed 27 workflows and its insertion-dialog overflow
check; preview/saved screenshots were inspected. Logs:
`.local/authored-check-20261003.log`, `.local/authored-ui-20261003.log`.
Developer-machine PowerPoint opened a synthetic 4:3 candidate with no prior
notes master, verified the two-slide count, inserted title and notes, exported
slide 2 to PNG, and retained the PPTX SHA-256
`89f5410e890279addc792a74b688eb4765f9fc0226be11809417c4fae2c4df1b`.
The rendering was inspected; `.local/authored-office/result.json` and
`slide-2.png` contain evidence. This is a single Office compatibility check,
not corpus fidelity, human-session or live-model acceptance. No package rebuild,
commit, push, CI, publication or production deployment occurred. Worktree now
contains 167 modified/untracked paths.

## Current continuation — native authoring templates

This continuation preserved the dirty worktree on `codex/production-readiness`.
It added `presentation/templates.py` and template/layout validation to native
outline creation. Review offers Classic/Midnight/Paper plus Points/Columns/Cards/
Statement layouts, ordinary editable shapes/text, and unchanged notes/import/
revision/provenance ownership. Unknown options and multi-point Statements fail
before import. No assets are downloaded and no new provider calls are added.

Outline review now supports title/points/notes editing, adding, duplicating,
removing, and reordering draft slides. Returning to the outline retains current
content/order/notes; layout choices are selected again after that transition.
Core checks cover all three templates/four layouts, content/notes preservation,
native object bounds, and invalid-request rejection without imported documents.
The Electron workflow creates a Midnight cards/statement deck and edits it as
a normal revision.

Verification: fresh `pnpm check` passed (101 desktop / 502 Core tests;
Core 78.83 seconds). After the final accessible-label adjustment, formatting,
lint, TypeScript/mypy and all 101 desktop tests passed again. `pnpm test:ui`
passed 26 workflows, including draft content surviving creation, bounds,
reordering/duplication/removal, updated-outline return, Midnight templates,
notes, normal revision editing, Copilot plans and undo. Review/created-deck
screenshots were inspected. `pnpm test:providers-ui` passed synthetic provider,
fast-decision and ChatGPT configuration flows. Logs are
`.local/continuation-check-20261003.log`,
`.local/continuation-ui-20261003.log`, and
`.local/continuation-providers-ui-20261003.log`. No live account/provider,
PowerPoint fidelity, human-session, package, CI or release acceptance is implied.
Worktree now contains 164 modified/untracked paths; no commits or pushes made.

Voice creation/shortcuts, semantic modeling, fidelity, live provider/account behavior,
human sessions, and release-candidate validation remain open. Applying these
templates to imported decks and selecting unused theme layouts remain open.

## Goal and user decisions

Finish Presenter Copilot to production-ready state, including the full
Presentation Workspace expansion. The goal is still active and incomplete.
The user specifically wants missing major features and GUI quality prioritized;
do not spend the next session primarily on small fixes or repeat the MVP-only
scope question.

- Fast finite-choice decisions are required: Jev/OpenRouter, Ollama Nimble and
  Tev1, local strict-schema models, and OpenAI Decisions when a verified
  first-party integration contract becomes available.
- Sign in with ChatGPT is requested; the supplied first-party SIWC guides informed
  the existing implementation.
- Find licensing-safe corpus/preparation material independently. A 33-deck corpus
  exists, but public material does not establish 10–20 observed human sessions.
- Clean Windows device/VM and production signing identity are accepted technical
  debt. Do not ask again; report their release gates as unverified.
- The user selected GPT Sol 6.1 in the app. Do not claim that an agent tool
  changed the active model.
- Before code edits, reason through dependencies and effects on other functions
  per the user's AGENTS instructions. Do not spawn agents unless explicitly asked.

## Repository state

- Workspace: `D:\Repos\presenter-copilot`
- Branch: `codex/production-readiness`
- Base HEAD: `657b876739ff7a1cc5709a7e28e92ec2551b337e`
- Large uncommitted implementation: 162 modified/untracked paths at handoff.
  Preserve all of it; do not reset, clean, or selectively overwrite from HEAD.
- No new commit, push, PR, hosted CI proof, publication or production deployment
  was performed in this continuation. Existing base CI does not validate this diff.
- Check current Git/process state before starting. All paths above describe this
  checkout; do not create an unrelated replacement project.

## Implemented locally

### Presentation Workspace

- Verified source snapshots; bounded OOXML inventory; stable managed slide/object
  identities; immutable revisions, original preservation, current head,
  parent/child undo and redo; revision-bound retrieval and re-indexing.
- Native bounded editing of text/formatting, notes, object geometry, simple shapes,
  text boxes, pictures, crop/replacement, eligible object duplication/deletion,
  slide insertion/duplication/deletion/order and existing-layout reuse.
- Native current/original PPTX export and user-triggered PowerPoint handoff.
- Reviewed native creation from a manual or Copilot-generated outline, with
  objective/audience/briefing, 1–40 slides, draft refinement, supplied evidence,
  and normal ingestion/revision/indexing. Native Classic/Midnight/Paper templates
  and Points/Columns/Cards/Statement layouts now supplement the original simple
  layout. Asset-driven templates and imported-deck template application remain open.
- Workspace GUI places the preview above expandable actions, groups inspectors
  into Text/Objects/Notes/Purpose/History/Rehearsal, preserves drafts, and exposes
  undo/redo next to revision state. More full-product visual/interaction work remains.
- Rehearsal findings feed reviewed text/notes edits with stable-slide mapping,
  dismissal/reopening and atomic provenance. Runs remain bound to a concrete
  presentation revision. Cross-rehearsal comparison is not implemented.
- Revision-scoped user-confirmed slide-purpose labels and typed decision proposals.
- Local voice dictation for one supported selected-text rewrite instruction.

### Latest major feature: Copilot edit plans

**Ask Copilot to edit** targets the current slide or entire deck. It generates
1–20 typed operations using the selected reasoning provider, stages a native
PPTX, renders the proposal, shows rationales/content changes/evidence, and saves
the exact reviewed bytes as one revision. Users must view every affected slide
and explicitly acknowledge review. Request changes invalidate approval;
discard restores the baseline; undo reverses the entire plan.

The strict schema exposes 15 operation types: text, notes, text/shape formatting,
geometry, crop, text-box/simple-shape creation, eligible object deletion/duplication,
slide order/layout, and slide creation/duplication/deletion. Raw image ingestion
and references to newly created targets later in the same plan are excluded.

Core binds preconditions against the rolling staged package, validates baseline
selection and supplied evidence IDs, checks revision/hash around inference, and
keeps proposals private until review. Schema v13 atomically stores content-free
operation/target/provider-run/evidence IDs with the committed revision. Four
previews may exist for 15 minutes, with expiry/discard/deletion/reset/shutdown
and crash-reconciliation cleanup.

Key implementation files:

- `core/presenter_core/presentation/edit_planning.py`
- `core/presenter_core/providers/edit_plan_schema.py`
- `core/presenter_core/presentation/edit_plans.py`
- `core/presenter_core/presentation/transactions.py`
- `apps/desktop/src/renderer/CopilotEditPlan.tsx`
- `apps/desktop/src/renderer/edit-plan-preview.ts`
- `apps/desktop/src/renderer/SlideEditReview.tsx`
- `core/tests/test_presentation_edit_planning.py` (19 focused checks)
- `apps/desktop/scripts/test-workspace.mjs`

Required selected inventory has a 48,000-character task context allowance and is
never silently truncated. Private knowledge is excluded. Imported text and
earlier drafts are untrusted data. Other ordinary task budgets remain 12,000.
Deterministic provider flows are verified; this is not live-model quality proof.

### Providers and safety

- Existing reasoning-provider routing/privacy/readiness, content-free manifests,
  credential storage, local-only policy and separate remote acknowledgement.
- ChatGPT-plan SIWC registration/OAuth/account/refresh/model/inference plumbing,
  with synthetic tests and Windows DPAPI credential round-trip verification.
  Real account sign-in and inference remain unverified.
- Typed fast-decision adapters and Settings flows for Jev, OpenAI Responses
  Fast/Ultrafast bridges, local strict-schema models, and installed Ollama
  `nimble:9b`, `tev1:4b`, `tev1:0.8b` plus documented aliases/variants.
  No automatic model download/server launch. Live Jev/Ollama acceptance is open.
- OpenAI Decisions adapter remains pending: the last documented search found
  no usable first-party endpoint/request/response/access contract. Recheck
  current official documentation before implementing; do not invent a protocol.
- A local LM Studio decision smoke recorded 10/10 strict-schema outputs, 7/10
  synthetic label matches, median 1,101 ms and p95 2,106 ms. This small fixture
  is transport evidence, not semantic quality acceptance.

## Verification and latest ASR repair

The last fully observed Electron run passed **25 workflows**, including
generated multi-operation review, request-change invalidation, deck-wide
all-affected-slide review, discard, one-revision save and undo. Real Electron,
Core and native PPTX bytes were used, with deterministic provider/audio fixtures.
Screenshots were inspected:

- `.local/ui-validation/workspace-copilot-edit-plan.png`
- `.local/ui-validation/workspace-copilot-deck-review.png`
- `.local/ui-validation/workspace-copilot-edit-undone.png`

Full-check failures exposed an idle ASR worker waiting for a 100 ms audio poll
after stop, while safety fixtures permit only 50 ms. Stop now queues a wake marker
after accepted PCM, preserving drain/flush ordering. Failed device stop retains
resource ownership for retry even when workers have exited. A deterministic
idle-worker regression was added; 30 focused Run/Teach/voice/safety checks passed.
The voice partial fixture now waits while speech is active before feeding
silence, avoiding legitimate coalescing of optional partials into a final.

Final fresh `pnpm check`: **PASS**, exit 0. Formatting, lint, TypeScript and
mypy passed; **101 desktop tests and 495 Core tests passed** (Core: 87.55 seconds).
Recorded log: `.local/handoff-check-20261003.log`.

Previous full checks passed formatting/lint/typing and 101 desktop tests. The
latest unobserved command lost its process handle across the session boundary;
an empty pytest last-failure cache alone was not treated as a confirmed pass.
The fresh handoff check above records an observed exit result.

## Remaining work, in priority order

1. **Complete authoring and GUI workflows.** Native creation templates and draft
   slide authoring/reordering and imported-deck authored insertion now exist.
   Continue with useful asset flows, broader object editing and
   polished interaction/navigation. Plans now resolve earlier-step created slide
   and object references for coordinated authoring. Refine coordinated content, rather than
   merely restyling controls.
2. **General voice creation and editing.** Slide/deck voice-to-EditPlan and
   transcript review and voice outline briefing/refinement now exist. Continue
   with ambiguity/low-confidence handling, push-to-edit shortcuts, and richer
   conversational drafting.
3. **Semantic presentation model.** Claims/object-span binding, evidence coverage,
   narrative analysis, incremental refresh after edits, and decision evaluation
   with explicit abstention and costly-error thresholds. Purpose labels alone
   do not implement this model. Recorded comparison across rehearsals now exists; semantic quality and demonstrated improvement remain open.
4. **PPTX visual fidelity.** The 33-record corpus has 31 compared decks/613 slides,
   two external-relationship skips, zero comparison failures and 21 unstable
   PowerPoint captures. Stable visual differences remain on all 613 slides.
   Investigate text/style/layout differences against explicit thresholds;
   inventory and package validity do not establish render fidelity. One edited
   title-wrapping case also needs review. PDF export is not implemented.
5. **Real preparation and provider acceptance.** 10–20 human preparation sessions
   have not been observed. Public materials and synthetic cases cannot replace
   that gate. Live model edit quality, SIWC account behavior, Jev/Ollama quality
   and latency, and broader corpus/media-rights coverage remain unverified.
6. **ASR and physical integration.** Prior measured partial/final latency was
   939.6/926.2 ms versus 500/900 ms targets. CUDA cuBLAS availability was missing
   in that run. The new shutdown repair does not prove latency or microphone/HUD
   quality; real-device verification remains open.
7. **Release candidate.** Rebuild the Windows package from the completed diff,
   rerun packaged/release/privacy/provider/corpus checks, inspect exact candidate
   identity, and obtain CI evidence. The existing unsigned package predates
   latest Workspace features. Clean install/uninstall/reinstall and signed
   distribution remain accepted infrastructure debt, not passed gates.

## Useful commands and next-session entry points

- `pnpm check`: formatting, lint, TypeScript/mypy, desktop and Core tests.
- `pnpm test:ui`: build plus 42 Electron Workspace workflows.
- `pnpm test:providers-ui`: provider configuration and synthetic UI flows.
- `pnpm test:e2e:release`: local deterministic release flows, with source fingerprint.
- `pnpm workspace:inventory-corpus`, `pnpm workspace:roundtrip-corpus`,
  `pnpm workspace:visual-compare`: inspect documented prerequisites before running
  PowerPoint automation or expensive full-corpus work.
- `pnpm package:win`, `pnpm test:packaged`: unsigned local packaging and smoke.
- `pnpm package:win:release`: requires the unavailable protected signing identity.

Read this handoff, `docs/PRODUCTION_READINESS.md`,
`docs/PRESENTATION_WORKSPACE/ROADMAP.md`, `AI_EDITING.md`, `VALIDATION.md`,
`PPTX_FIDELITY.md`, `CORPUS.md`, and `docs/PROVIDERS.md`. Historical verification
paragraphs describe earlier candidates; do not claim they cover all current code.

Suggested continuation instruction:

> Continue the existing production-readiness goal from docs/SESSION_HANDOFF.md.
> Preserve the dirty worktree. Prioritize substantial missing Presentation
> Workspace features and GUI workflows, then fidelity/integration acceptance.
> Include fast decisions and Sign in with ChatGPT. Signing and clean Windows
> validation are accepted tech debt. Reason through dependencies before edits,
> validate real user flows, and keep implementation evidence separate from
> live-provider, human-session and signed-release proof.
