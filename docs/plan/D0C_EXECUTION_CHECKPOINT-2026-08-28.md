# D0C execution checkpoint — 2026-08-28

This checkpoint records the real repository state after rebuilding the local
AgentPort path from the merged D5 product foundation. It is an execution
handoff, not a release or runtime claim.

## Canonical base

`main` contains the merged D5 full-product-repository foundation. The former
planning-only repository state is superseded. Code, contracts, manifests,
tests, packaging and evidence belong in this repository.

## Active stacked development line

```text
main
  -> PR #7  D0C-02 authenticated bounded transport v2
  -> PR #8  D0C-03 canonical Browser codec executable reference
  -> PR #9  D0C-04 connected exactly-one AgentPort reference
```

All three pull requests are intentionally draft/non-merge-ready.

### PR #7 — transport

Implemented in Rust source and independently exercised through a Python
standard-library wire reference. The independent corpus passes 15/15 checks on
AF_UNIX framing, SO_PEERCRED, nonce, digest, sequence, size and deadline
behavior. The Rust 1.93 format, Clippy, tests and browserd self-check remain
unexecuted.

### PR #8 — codec

Regenerated from the current D5 Browser API contract after rejecting the stale
old codec branch. The executable reference passes 26/26 checks for canonical
JSON, duplicate rejection, strict fields, session/generation binding, semantic
references, URLs, response shape and effect classification. The Rust product
codec remains unimplemented.

### PR #9 — bridge

Composes the connected transport and codec references over real AF_UNIX
socketpairs. The 13/13 corpus proves exactly-one reference dispatch, request and
response digest binding, peer/sequence/effect context, navigation default
denial, request-derived response identity, duplicate rejection before handler,
and non-commit of late or invalid handler results. No Rust bridge or listener
exists.

## Superseded pull requests

- PR #2: closed; replaced by PR #7.
- PR #3: closed; contract-drifted codec replaced by PR #8.
- PR #5: closed; old connected bridge replaced by the clean stack and PR #9.
- PR #6: closed; socket custody must be rebuilt after the corrected Rust bridge.

PR #4 remains a separate D0A-01 Servo compile-qualification track. Its workflow
failed before runner assignment (`runner_id=0`, no steps), so it has no compile
PASS evidence.

## Hard merge gates

No D0C draft becomes merge-ready until an exact Rust 1.93 environment executes
against the exact candidate stack:

```text
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
```

The Rust product codec and bridge must then be implemented and tested with the
checked-in golden vectors. Reference PASS is additional cross-implementation
evidence, never a substitute for compiling product code.

## Next implementation order

1. Restore a trusted Rust 1.93 execution lane or a correctly provisioned
   self-hosted/hosted runner.
2. Execute and repair PR #7 until exact-head Rust gates pass.
3. Implement the Rust D0C-03 codec from `browser-codec.v1.json`, not from the
   superseded branch.
4. Implement the Rust D0C-04 bridge and prove parity with the reference corpus.
5. Rebuild systemd socket custody as D0C-05 with default-disabled activation.
6. In parallel, complete D0A-01 Servo compile qualification and proceed to the
   product-owned headed D0A-02 wrapper.

## Claim ceiling

No product listener, BrowserActor, Servo runtime, visible window, navigation,
native input, external effect, Debian image, Secure Boot, update or release
claim is established by this checkpoint.
