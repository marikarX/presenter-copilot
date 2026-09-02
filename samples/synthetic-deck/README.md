# Synthetic M1 ingestion fixture

This directory contains only fictional, distributable material for testing
Presenter Copilot's local project vault and ingestion flow. It includes a
22-slide PPTX with speaker notes, a four-page PDF cost model, a Markdown
architecture note, expected lexical/semantic/hybrid retrieval targets, and
bounded security fixtures. The retrieval goldens use top-K expectations rather
than exact floating-point scores.

Regenerate the binary/text assets deterministically from the repository root:

```text
uv run --directory core --project . --locked python ../samples/synthetic-deck/generate_fixture.py
```

The source text containing HTML/script-like content is intentionally data. The
desktop preview must display it as escaped text and must never render it as
HTML. `security/unsafe-member.pptx` contains a ZIP member with `..` traversal
and must be rejected during preflight.
