# Shared protocol contracts

The JSON Schema describes protocol v1 envelopes, and
`protocol-v1.examples.json` is a fixture consumed by both the Python and
TypeScript test suites. The fixture now covers the M1 capability/event surface
in addition to the lifecycle handshake. Runtime implementations may add
fields, but they must preserve the required envelope shape and protocol
version; renderer authority remains a separate explicit allowlist.
