# Product Definition

## Problem

High-stakes presenters often know their subject but still fail in predictable ways:

- they do not rehearse against the actual objections their audience will raise;
- their supporting evidence is scattered across decks, notes, spreadsheets, documents, and prior meetings;
- generic speech coaches measure delivery but not whether the argument is defensible;
- generic LLM assistance tends to replace the presenter's natural wording with generic AI prose;
- teleprompters encourage reading instead of speaking naturally;
- live AI assistants often lack presentation context, provenance, or enterprise-appropriate privacy.

## Product

Presenter Copilot is a local-first presentation-intelligence system that helps a user prepare, rehearse, defend, and deliver a specific presentation.

The product should know:

- what is on each slide;
- what supporting material backs each claim;
- how the presenter naturally explains the topic;
- who the audience is;
- what that audience has actually asked or cared about before, when the user provides authorized prior transcripts/context;
- what objections are likely;
- which answers the presenter has already practiced;
- where the presenter historically struggles.

## Core context model

### Speaker Profile

Persistent, user-controlled knowledge about how the presenter communicates:

- preferred phrases and vocabulary;
- strong prior explanations/analogies;
- answer-length and formality preferences;
- accepted coaching patterns;
- explicit style guidance.

The default objective is **the user on a very good day**, not an AI voice replacing the user.

### Project Brain

Project-local knowledge containing:

- deck and supporting sources;
- user Teach-mode explanations;
- decisions and rationale;
- evidence/provenance;
- rehearsals;
- questions and answer versions;
- presentation/session history.

### Audience Model

Project-local audience context containing:

- participant role/name when lawfully supplied;
- native speaker-attributed transcript questions;
- recurring observable concerns/question patterns;
- user notes about expected objections/decision criteria.

The product models observable interaction behavior, not hidden emotions, psychological diagnoses, or sensitive traits.

## Modes

### Teach

User talks or types with the AI so the app learns missing context and the user's
own explanations. Teach voice uses the existing local ASR stack; only the
finalized transcript enters the same candidate, confirmation, provenance, and
privacy path as typed input. Typed answers remain the fallback when a model or
microphone is unavailable.

### Challenge

Simulated audience profiles ask grounded questions and follow-ups. Weak answers can be retried and strong answers retained.

### Run

Uninterrupted presentation rehearsal with slide/transcript tracking and a post-run debrief.

### Live Assist

Private webcam-adjacent HUD surfaces short source-grounded facts, answer structures, and reminders during a mock or real presentation.

### Immersive Rehearsal — post-MVP

A renderer-independent audience simulation layer surrounds a Run/Challenge-style session with visible audience behavior, interruptions, questions, spatial pressure, and scenario-specific debriefing.

The first validation target is a lightweight desktop audience, not XR or photorealism. Synthetic/role-based participants are the default. Higher-fidelity 3D and headset clients are later rendering options over the same simulation contract.

See [`docs/IMMERSIVE/`](IMMERSIVE/README.md).

## Style policies

Mode and style are independent.

- **Preserve my voice** — default.
- **Light polish** — improve clarity without changing identity.
- **Executive concise** — more aggressive compression/structure.
- **Custom** — project/user guidance.

## Primary users

Initial focus should be people for whom a presentation has material economic or professional consequences:

- enterprise account executives;
- sales engineers and solution architects;
- consultants;
- founders raising capital;
- executives and product leaders;
- proposal and bid teams;
- investor-relations and finance teams;
- technical presenters defending designs or recommendations.

## Jobs to be done

### Before the presentation

- Understand the deck and supporting documents.
- Capture important context that exists only in the presenter's head.
- Identify unsupported or weak claims.
- Build realistic audience models from roles, user notes, and authorized attributed transcripts.
- Predict likely questions by actual audience context.
- Prepare concise answer structures with sources while preserving presenter voice.

### During rehearsal

- Track slide position and speech.
- Learn strong natural explanations from the presenter.
- Measure delivery without over-indexing on cosmetic metrics.
- Ask realistic audience questions.
- Challenge vague, incomplete, overlong, or evasive answers.
- Repeat weak questions until the response improves.
- In later immersive scenarios, expose the presenter to visible attention shifts, interruptions, time pressure, and spatial audience dynamics without presenting simulated behavior as a prediction of real people's internal states.

### During the real presentation

- Show minimal private cues close to the webcam.
- Surface exact numbers, facts, slide references, practiced explanations, and answer scaffolds when needed.
- Avoid displaying full prose unless the user explicitly requests it.
- Preserve natural eye contact and normal speaking cadence.
- Prefer local processing and retrieval before remote reasoning.

### After the presentation

- Capture questions that actually occurred.
- Compare rehearsed vs. real objections.
- Identify answer failures and strong responses.
- Feed resulting knowledge into the Project Brain and future rehearsal.

## MVP

The developer-ready MVP contract is frozen in [`docs/MVP/`](MVP/README.md).

Key P0 capabilities:

1. PDF/PPTX plus supporting-document ingestion.
2. Local semantic/exact retrieval with provenance.
3. Speaker Profile and Preserve-My-Voice behavior.
4. Teach mode for conversational project enrichment.
5. Named transcript import and project-local Audience Models.
6. Challenge mode with grounded audience questions.
7. Local ASR and Run rehearsal mode.
8. A top-center webcam-adjacent HUD with short cues and push-to-assist fallback.
9. Pluggable reasoning backends and explicit privacy modes.

## Explicit non-goals for MVP

- full presentation-authoring suite;
- AI-generated decks as a primary feature;
- avatar presenters;
- immersive/photorealistic audience rendering;
- XR rehearsal;
- LMS replacement;
- video editing;
- stealth or undetectability claims;
- automatic spoken answers during the real meeting;
- persistent biometric voice/face identification;
- workplace emotion recognition or hidden personality inference;
- full meeting audio/video diarization pipeline;
- enterprise analytics before the individual workflow is compelling.

## Differentiation hypothesis

The moat is not the model, teleprompter, or filler-word analysis. Those are commoditized or easily copied.

Potential differentiation comes from accumulated context and workflow:

- Speaker Profile that preserves the user's own voice;
- presentation-specific Project Brain;
- audience-specific objection/question history;
- rehearsal-to-live continuity;
- source-grounded preferred-answer memory;
- local-first privacy and latency;
- longitudinal learning from actual questions and prior responses;
- eventually, renderer-independent audience simulation driven by that accumulated context rather than generic animated avatars.

## Success criteria for prototype

A prototype is compelling if a user can:

1. upload a real technical/business deck;
2. teach missing reasoning in their own words;
3. rehearse against audience profiles grounded in actual project context;
4. receive several genuinely relevant questions they had not anticipated;
5. answer those questions more concisely without losing their speaking style;
6. run a mock live session where the HUD surfaces the right fact or answer scaffold quickly enough to be useful without visibly reading.
