# Synthetic deck fixture

This directory is reserved for the canonical, distributable Presenter Copilot
test project. The complete fixture will eventually contain a 20–25 slide deck
or PDF, two supporting documents, a named transcript with three speakers plus
an unresolved room label, expected audience mappings/questions/retrieval
targets, controlled conflicting numeric facts, and a prompt-injection source.

Milestone 0 provides the fixture skeleton only. No real customer material,
recordings, credentials, or proprietary presentation content belongs here.

Planned layout:

```text
deck/          canonical PPTX/PDF
supporting/    two synthetic source documents
transcript/    named synthetic transcript
expected/      mappings, questions, retrieval goldens
security/      malicious-but-safe import fixtures
manifest.json  machine-readable fixture plan
```
