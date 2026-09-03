# MVP UX Flows

## 1. Navigation model

Primary desktop navigation:

```text
Home
  └─ Project
      ├─ Sources
      ├─ Audience
      ├─ Teach
      ├─ Challenge
      ├─ Run
      ├─ Live Assist
      └─ History

Settings
  ├─ Speaker Profile
  ├─ Models & Providers
  ├─ Audio
  ├─ Privacy
  └─ Shortcuts
```

The product should feel project-centric, not chat-centric.

## 2. First-run flow

1. Welcome.
2. Explain local-first architecture in one short screen.
3. Select microphone.
4. Run 10-second ASR check.
5. Configure reasoning backend:
   - local/mock unavailable for production quality but can test plumbing;
   - user-supplied provider;
   - optional provider integrations when implemented.
6. Select default privacy mode; recommend `Selected Context Cloud` only if a remote provider is configured, otherwise `Local Only`.
7. Offer optional `Build my Speaker Profile later`; do not force onboarding speech training.

## 3. Create project

Fields:

- project name;
- presentation file;
- optional supporting files;
- optional audience names/roles;
- privacy mode;
- style policy (default `Preserve my voice`).

After import show processing status per source:

```text
ArchitectureReview.pptx    Ready · 24 slides
CostModel.pdf              Ready · 18 pages
JulyMeeting.vtt            Ready · 4 named speakers
```

Errors must be per-file and retryable.

Selecting Transcript opens the authorization disclosure before the native file
picker. The user must explicitly continue before choosing a VTT, SRT, named
TXT, or structured JSON transcript. The renderer never receives arbitrary
filesystem authority.

## 4. Source review

User can inspect:

- presentation slide list;
- supporting sources;
- transcript speakers;
- extracted text preview;
- indexing status;
- delete/re-index source.

For transcript import:

```text
Native speaker: Jane Smith       [Map to: Jane / CFO]
Native speaker: Robert Chen      [Map to: Robert / CTO]
Native speaker: Conference Room  [Map to: Unresolved]
```

Do not hide unresolved attribution.

Native labels are metadata until the user maps them. Mapping is performed per
transcript document and label; a profile created from a label is still an
explicit user action. Remapping does not move old observations to the new
profile—derived rows become stale and require fresh review.

## 5. Audience setup

Audience page contains cards:

```text
Jane Smith
CFO

Observed from imported meetings:
- asks for status-quo cost comparisons
- recurring concern: downside risk
- prefers short, direct answers

Evidence: 7 attributed questions
[Review evidence] [Edit] [Disable]
```

AI-derived observations must expose evidence and be editable/deletable.

Prohibited sensitive/emotion inference is never presented.

Audience suggestions are visibly provisional and show their exact supporting
transcript segments, including speaker label and cue time. The user can edit
the wording/type, accept, reject, or leave a candidate pending. Only accepted
non-stale observations enter future AudienceContext.

## 6. Teach mode

Layout:

```text
+--------------------------------------------------+
| Current slide/context                            |
|                                                  |
| AI question                                      |
| "Why did you reject option A?"                  |
|                                                  |
| live transcript                                  |
|                                                  |
| [Keep explanation] [Preferred answer] [Private] |
| [Don't use live]                                 |
+--------------------------------------------------+
```

Behavior:

- user answers naturally by voice or typing;
- AI may ask one focused follow-up at a time;
- after a useful user explanation, app offers a compact extracted knowledge item for confirmation;
- app never silently promotes model-generated wording to `user-authored` knowledge;
- user can correct the extracted meaning before saving.

## 7. Speaker Profile review

Settings page shows human-readable learned evidence, not opaque personality scores.

Examples:

```text
Preferred phrase
"There are really three reasons..."
Source: Project Alpha / Teach session
[Keep] [Remove]

Preferred answer length
Short (15–30 seconds)
[Change]
```

No labels such as personality type, confidence score, emotional state, intelligence, etc.

## 8. Challenge mode

Setup:

- choose 1–3 audience profiles;
- choose intensity: Normal / Skeptical / Adversarial;
- choose whether follow-up questions are allowed;
- select current slide range or full deck.

Question view:

```text
Jane · CFO
"Why wouldn't we extend the existing platform for one more year?"

[Type your answer]
[Submit answer]
```

After answer:

```text
Correctness      Good
Directness       Good
Completeness     Missing status-quo risk
Concision        Could be tighter
Style match      Not enough style evidence
Source support   Partially supported
Length           28 words · estimated 13 sec · target 25 sec

Your strongest prior phrasing:
"..."

[Retry] [Next question] [Follow-up] [Save as preferred]
```

Scoring must be advisory and explainable, not presented as scientific truth.
Challenge remains typed-first through M6. M6 microphone capture is a Run-only
path; it does not change Teach/Challenge answer semantics or add live meeting
capture. Retry keeps the same Question and creates another immutable
AnswerVersion; Save as preferred is an explicit promotion into Project Brain
knowledge. The expandable “Why this question / Sources” view shows only the
concise rationale, accepted audience basis, and canonical source labels—not
hidden model reasoning.

## 9. Run mode

Pre-run checklist:

- microphone status;
- local ASR model status and explicit prepare action;
- presentation detected/manual mode;
- recording/transcript status;
- privacy mode;
- HUD disabled/enabled for mock run.

During Run:

- minimal controls;
- current slide indicator;
- timer;
- ephemeral partial speech and recent final transcript text;
- explicit `Mark question`, `Mark weak point`, and bounded note actions;
- on-screen previous/next slide controls plus manual global shortcuts;
- no coaching popups by default;
- PowerPoint tracking is read-only and falls back to manual tracking without
  ending Run.

Post-run debrief:

- timeline by slide;
- long/unclear segments;
- claims without evidence;
- unanswered likely objections;
- best explanations captured;
- recommended Challenge questions.

Only final utterances are shown in recovered transcript history. A completed
Run's transcript, slide timeline, markers, and debrief remain available after
core/app restart; raw microphone audio and partial text do not.

## 10. Live Assist mode

Before activation show explicit status:

```text
Privacy: Selected Context Cloud
Audio: processed locally
Remote context: question + selected excerpts only
HUD capture protection: ON
```

HUD default:

```text
            ● CAMERA

     3-year TCO ↓ 18%
     HA removes region SPOF
     Source: Cost model p.4
```

### Live Assist controls

Global shortcuts, user-configurable:

- show/hide HUD;
- push-to-assist;
- expand/collapse source;
- previous/next cue;
- clear cue;
- manual previous/next slide fallback.

### Progressive cue behavior

Example:

1. `Cost comparison`
2. `3-year TCO ↓ 18%`
3. `3-year TCO ↓ 18% · includes licenses + ops`

A correct useful partial is preferred to waiting for polished prose.

## 11. Provenance expansion

Expanded cue shows:

```text
Cue
3-year TCO ↓ 18%

Sources
1. CostModel.pdf · p.4
2. Slide 12 · Financial comparison

Preferred explanation
"We're paying more upfront, but over three years..."
Source: your Challenge rehearsal · Aug 31
```

This view can be larger because it is not intended for constant eye contact.

## 12. Privacy and deletion UX

Every project has:

- `Delete session`;
- `Delete source`;
- `Delete project and local data`;
- privacy mode selector;
- provider context manifest/history.

Deletion confirmation must state what will be removed. Avoid dark patterns and cloud-style vague retention wording for local files.

## 13. Error states

Errors are actionable:

- microphone disconnected -> select another device;
- ASR model missing -> explicitly prepare the approved local model;
- microphone failure -> show the stable error and offer device selection/retry;
- PowerPoint state unavailable -> switch to manual slide control;
- provider quota/auth failure -> retrieval-only fallback;
- unsupported source -> preserve file, show parser error, let user remove/retry;
- HUD capture protection unsupported -> visibly warn user before live use.

## 14. Accessibility

P0 requirements:

- keyboard operable main flows;
- configurable HUD font size/width;
- high-contrast-compatible rendering;
- no critical status communicated by color only;
- transcript usable without audio persistence;
- shortcuts remappable to avoid conflicts.
