# D0C Rust product materialization request

This branch consolidates the clean D0C-02 transport stack with the executable
D0C-03/D0C-04 references and stages the reviewed Rust product overlay for
exact Rust 1.93 materialization.

The bootstrap payload is SHA-256 pinned. A one-shot workflow must apply the
overlay, generate the exact Cargo lock, create a dependency allowlist
candidate, run formatting, Clippy, all-target tests and the browserd
self-check, commit only a passing candidate, and remove its bootstrap files.

This request is not execution evidence. Until the workflow completes, the
branch remains draft and makes no listener, BrowserActor, Servo, external
navigation, external effect or release claim.
