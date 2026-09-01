# Shared protocol contracts

Milestone 0 keeps the cross-language contract intentionally small. The JSON
Schema describes protocol v1 envelopes, and `protocol-v1.examples.json` is a
fixture consumed by both the Python and TypeScript test suites. Runtime
implementations may add fields, but they must preserve the required envelope
shape and protocol version.
