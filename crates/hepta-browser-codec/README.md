# hepta-browser-codec

Product Rust codec for the D5 Browser API wire envelope. It rejects recursive
duplicate JSON members, unknown nested fields, non-canonical encodings, invalid
session/revision bindings, unsafe navigation targets, malformed response shapes
and messages above the transport bound before dispatch.

Every admitted request is converted into the existing engine-neutral
`hepta-browser-contracts::BrowserOperation`; the future BrowserActor therefore
receives one domain contract rather than reinterpreting wire JSON. Rust tests
include all six byte-exact reference golden vectors.

This crate opens no listener, calls no browser engine and grants no effect
authority.
