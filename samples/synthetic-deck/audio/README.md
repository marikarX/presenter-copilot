# Synthetic ASR fixture

`speech-fixture.wav` is a checked-in, fictional speech recording for local
ASR acceptance and benchmarking. It is 16 kHz mono signed 16-bit PCM and does
not contain personal or customer audio. The acceptance terms are listed in
the root manifest; the benchmark artifact records timings and environment
metadata only, not the recognized transcript.

Run the real checks only after the pinned model has been prepared explicitly:

```text
pnpm model:prepare:asr
pnpm test:asr-real
pnpm benchmark:asr
```
