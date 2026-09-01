# Product Definition

## Problem

High-stakes presenters often know their subject but still fail in predictable ways:

- they do not rehearse against the actual objections their audience will raise;
- their supporting evidence is scattered across decks, notes, spreadsheets, documents, and prior meetings;
- generic speech coaches measure delivery but not whether the argument is defensible;
- teleprompters encourage reading instead of speaking naturally;
- live AI assistants often lack presentation context, provenance, or enterprise-appropriate privacy.

## Product

Presenter Copilot is a local-first presentation-intelligence system that helps a user prepare, rehearse, defend, and deliver a specific presentation.

The product should know:

- what is on each slide;
- what supporting material backs each claim;
- who the audience is;
- what objections are likely;
- which answers the presenter has already practiced;
- where the presenter historically struggles.

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
- Identify unsupported or weak claims.
- Predict likely questions by audience role.
- Generate concise answer structures with sources.
- Build a rehearsal plan around weak areas.

### During rehearsal

- Track slide position and speech.
- Measure delivery without over-indexing on cosmetic metrics.
- Ask realistic audience questions.
- Challenge vague, incomplete, overlong, or evasive answers.
- Repeat weak questions until the response improves.

### During the real presentation

- Show minimal private cues close to the webcam.
- Surface exact numbers, facts, slide references, and answer scaffolds when needed.
- Avoid displaying full prose unless the user explicitly requests it.
- Preserve natural eye contact and normal speaking cadence.

### After the presentation

- Capture questions that actually occurred.
- Compare rehearsed vs. real objections.
- Identify answer failures and strong responses.
- Feed the resulting knowledge into the next rehearsal.

## MVP

The first useful version should include:

1. PDF/PPT ingestion plus supporting documents.
2. Local semantic retrieval over presentation material.
3. Local or low-latency transcription during rehearsal.
4. Slide/presentation context tracking.
5. Audience-persona question generation.
6. Rehearsal transcript and answer review.
7. A top-center webcam-adjacent HUD with short cue cards.
8. Pluggable reasoning backends.

## Explicit non-goals for MVP

- full presentation-authoring suite;
- AI-generated decks as a primary feature;
- avatar presenters;
- LMS replacement;
- video editing;
- stealth or undetectability claims;
- automatic spoken answers during the real meeting;
- enterprise analytics before the individual workflow is compelling.

## Differentiation hypothesis

The moat is not the model, teleprompter, or filler-word analysis. Those are commoditized or easily copied.

Potential differentiation comes from the accumulated presentation context and workflow:

- presentation-specific knowledge graph/index;
- audience-specific objection history;
- rehearsal-to-live continuity;
- source-grounded answer memory;
- local-first privacy and latency;
- longitudinal learning from actual questions and prior responses.

## Success criteria for prototype

A prototype is compelling if a user can:

1. upload a real technical/business deck;
2. rehearse it naturally;
3. receive at least several genuinely relevant questions the user had not anticipated;
4. answer those questions more concisely after coaching;
5. run a mock live session where the HUD surfaces the right fact or answer scaffold quickly enough to be useful without visibly reading.
