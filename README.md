# Presenter Copilot

**Working title. Private repository.**

Presenter Copilot is a local-first AI copilot for high-stakes presentations. It learns a presentation and its supporting material, helps the presenter rehearse against realistic audiences, and can surface minimal private cues near the webcam during the real presentation.

The product is intentionally **not** an AI teleprompter. The core idea is a presentation-intelligence loop:

**Prepare -> Rehearse -> Defend -> Present -> Learn**

## Product thesis

Existing tools tend to solve only one part of the problem:

- speech coaching;
- teleprompting;
- deck generation;
- simulated roleplay;
- generic live AI assistance.

Presenter Copilot is intended to connect those pieces around one presentation and one audience while keeping latency and sensitive data under control through local processing.

## Core workflow

1. Import a deck and supporting documents.
2. Build a local knowledge index for the presentation.
3. Analyze likely weak points, objections, missing evidence, and audience-specific questions.
4. Rehearse the actual presentation while the system tracks delivery and slide context.
5. Simulate audience personas such as a CFO, CTO, customer, reviewer, or skeptical executive.
6. During the real presentation, show only small cue cards near the webcam rather than a full script.
7. Capture real questions and weak answers so the next rehearsal improves.

## Design principles

- **Local first.** Audio, transcript, retrieval, and presentation state should stay on-device whenever practical.
- **Cloud optional.** Strong remote reasoning should be an escalation path, not a requirement for every utterance.
- **Minimal HUD.** Prefer memory cues and answer scaffolds over generated paragraphs.
- **Provider-pluggable.** Support local models, user-supplied API credentials, and officially supported agent backends where permitted.
- **No stealth-cheating positioning.** The product is a private presenter view, not an undetectable answer machine.
- **Source-grounded answers.** Important claims should be traceable to the deck or supporting material.

## Initial architecture

```text
Microphone / presentation state
            |
            v
       Local VAD + ASR
            |
            v
      Local transcript
            |
     +------+------+
     |             |
     v             v
Slide context   Local RAG
     |             |
     +------+------+
            v
       Reasoning router
        /          \
       v            v
 Local model   Optional remote
       \            /
        +----------+
             v
       Webcam-adjacent HUD
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Repository status

This repository currently contains product and architecture planning only. No implementation stack has been locked yet.

## Documentation

- [Product definition](docs/PRODUCT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Privacy model](docs/PRIVACY.md)
- [Competition](docs/COMPETITION.md)
- [Roadmap](docs/ROADMAP.md)
- [Decision log](docs/DECISIONS.md)

## Working positioning

> A private, local-first AI copilot for high-stakes presentations.

Public naming and licensing are intentionally undecided until competitor, trademark, domain, and open-source strategy reviews are complete.
