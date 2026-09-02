# Synthetic M4 transcript and ingestion fixture

This directory contains only fictional, distributable material for testing
Presenter Copilot's local project vault, transcript ingestion, retrieval, and
project-local Audience Model. It includes a 22-slide PPTX with speaker notes,
a four-page PDF cost model, a Markdown architecture note, a canonical WebVTT
transcript with Jane Smith, Robert Chen, and an unresolved Conference Room
label, equivalent small SRT/TXT/JSON fixtures, expected retrieval/audience
goldens, and bounded security fixtures.

The canonical transcript is intentionally safe synthetic evidence. Its final
segment contains prompt-injection-shaped text; it must remain inert source
text. The audience goldens use ordinal evidence references rather than
wall-clock UUIDs.

Regenerate the binary/text assets deterministically from the repository root:

```text
uv run --directory core --project . --locked python ../samples/synthetic-deck/generate_fixture.py
```

The source text containing HTML/script-like content is intentionally data. The
desktop preview must display it as escaped text and must never render it as
HTML. `security/unsafe-member.pptx` contains a ZIP member with `..` traversal
and must be rejected during preflight. Transcript labels are metadata only;
they never automatically identify or map a person.
