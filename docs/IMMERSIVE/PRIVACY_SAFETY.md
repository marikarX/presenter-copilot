# Immersive Rehearsal Privacy & Safety

**Status:** Post-MVP privacy/safety requirements.

Immersive Rehearsal adds new risks because it may combine audience context, camera-derived presenter signals, simulated human behavior, 3D assets, and potentially XR telemetry. These risks must be addressed before implementation rather than after visual prototypes become entrenched.

## Core rule

The product simulates rehearsal scenarios. It does not claim to read, diagnose, or faithfully reproduce real people.

## Synthetic identity by default

Default audience members should be synthetic or role-based.

Recommended labels:

- CFO;
- VP Engineering;
- Security Reviewer;
- Customer Architect;
- Investor;
- Procurement Lead.

Synthetic participants may have generated appearance, voice, and behavior as long as they are not intentionally presented as a real person's likeness.

## Real-person names

A scenario may reference a real participant's name when the existing project-local Audience Model legitimately contains that identity from user-supplied or native attributed data.

When a real name is used:

- behavior must be described as simulated/approximate;
- the UI must not imply psychological certainty;
- the system may use observable evidence such as prior attributed questions, role, stated criteria, and user notes;
- the system must not infer sensitive traits, diagnosis, hidden emotion, political/religious beliefs, or other protected/sensitive attributes;
- absence of evidence must not be filled with invented personal claims.

Preferred wording: `Simulated from project evidence`.

Avoid wording such as `This is how Alex will react`.

## Likeness recreation

Photorealistic recreation of a real coworker, customer, executive, or other identifiable person is not required for Immersive Rehearsal and is excluded from the default roadmap.

Before any future real-person likeness feature is considered, require a separate design and legal/privacy review covering at least:

- explicit user rights/authorization to provide source media;
- consent and applicable publicity/privacy law;
- biometric-data implications;
- organizational policy;
- retention/deletion;
- generated-media labeling;
- abuse prevention;
- voice cloning implications;
- jurisdiction-specific restrictions.

Do not infer consent from the fact that a user possesses a recording or photograph.

## Meeting recordings and transcripts

Existing Presenter Copilot rules remain authoritative.

Prefer:

1. native speaker-attributed transcript labels;
2. explicit user mapping into project-local Audience Profiles;
3. user-authored notes.

Do not add face or voice recognition merely to make immersive scenes look more personalized.

Audio/video import for identity extraction remains out of scope unless separately specified and reviewed.

## Presenter camera signals

A future immersive mode may benefit from coaching signals such as whether the presenter is generally facing the display/camera or distributing gaze across simulated room regions.

Permitted direction after explicit implementation review:

- local-only coarse head orientation;
- local-only gaze-region approximation;
- posture/movement features used only for presenter coaching;
- ephemeral processing by default.

Not permitted as a side effect:

- persistent face embeddings;
- identity recognition;
- emotion recognition;
- mental-state inference;
- demographic inference;
- using camera signals to identify or profile people in imported real meetings.

## XR telemetry

XR devices may expose head pose, gaze, hand/controller input, room geometry, and other sensitive sensor data.

Default requirements:

- collect only signals necessary for rehearsal interaction;
- keep raw high-frequency telemetry local and ephemeral where practical;
- persist derived coaching events rather than raw sensor streams;
- never use room mapping to infer private environmental information unrelated to rehearsal;
- do not send raw telemetry to remote models unless an explicit future feature requires it and the user opts in;
- document device/platform telemetry behavior separately.

## Remote reasoning

The existing privacy modes remain in force:

### Local Only

No immersive project/audience content is sent to remote providers.

### Selected Context Cloud

Only bounded semantic context needed for a question, follow-up, or interpretation task may leave the device. Raw camera frames, raw XR telemetry, full room captures, and raw microphone audio remain local.

### Full Context Cloud

Any future use must still identify what immersive-specific context leaves the device. Full Context Cloud is not permission to upload camera/XR sensor streams by default.

## Renderer isolation

Renderers should receive only what is required to display the simulation.

Allowed examples:

- synthetic display name;
- role;
- avatar/asset ID;
- seat/position;
- current reaction event;
- generated question text;
- bounded visual intensity.

Do not provide renderer processes with:

- API/provider credentials;
- unrestricted Project Brain data;
- full imported meeting transcripts;
- raw microphone audio;
- private evidence not needed for the displayed question;
- persistent biometric templates.

## Generated behavior labeling

A user should be able to distinguish:

- source-backed audience concern;
- user-authored scenario assumption;
- deterministic simulation behavior;
- model-generated interpretation/question;
- renderer animation.

Debriefs should not collapse those classes into a single authoritative statement.

## Psychological and emotion claims

The simulation may use internal variables called `attention`, `skepticism`, `support`, or `comprehension` as game/simulation state.

Those variables are not measurements of real humans.

When a scenario is based on a real Audience Model, debrief language should remain counterfactual/simulation-specific. Examples:

- acceptable: `In this run, the simulated Security Reviewer remained skeptical after the threat-model slide.`
- acceptable: `The scenario generated a follow-up because the configured security concern was not addressed.`
- avoid: `Your Security Reviewer felt threatened.`
- avoid: `The CFO was bored.`

## Asset sourcing

Photorealistic avatar, voice, room, and motion assets introduce licensing and provenance risks.

Before distribution:

- track asset licenses and redistribution terms;
- avoid datasets/assets with unclear consent or provenance;
- store third-party notices where required;
- distinguish generated assets from licensed real-person scans;
- ensure avatar/voice packs do not accidentally imply endorsement by real people.

## Abuse cases

Design should explicitly consider:

- using the product to create humiliating or deceptive simulations of coworkers;
- generating a photorealistic executive/customer clone without authorization;
- using rehearsal data for employee surveillance/scoring;
- secretly processing real meetings for identity/emotion recognition;
- presenting simulated predictions as actual personnel assessments;
- retaining sensitive sensor data longer than needed.

Organization/team features must not silently turn individual rehearsal telemetry into manager-facing employee ranking.

## Deletion and export

Users should be able to delete:

- a scenario;
- one immersive run;
- generated participant definitions;
- rendered/generated local assets where the app owns them;
- derived coaching events;
- imported source material according to the existing project deletion model.

Exports should identify simulated/generated content clearly.

## Review triggers

Revisit this document before adding any of:

- real-person avatar generation;
- voice cloning;
- face recognition;
- speaker recognition from audio/video;
- emotion recognition;
- demographic inference;
- persistent eye tracking;
- cloud rendering;
- raw XR telemetry upload;
- shared employee performance dashboards;
- automatic ingestion of meeting recordings;
- remote multiplayer rehearsal.
