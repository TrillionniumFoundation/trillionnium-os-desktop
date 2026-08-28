# TrillionniumOS Desktop — current state

**Updated:** 2026-08-28  
**Canonical plan:** `2026-08-28-d5`  
**Repository mode:** `FULL_PRODUCT_REPOSITORY`  
**Implementation stage:** `D0R_D0C04_SOURCE`

## What is implemented in source

1. The canonical Rust 2024 product workspace and D0 contract/session foundation.
2. Layered session, document, semantic-snapshot, and mutation revisions.
3. Deterministic Agent/human arbitration with bounded FIFO admission.
4. Synthetic HTTPS trusted-app origins and an explicit trusted-shell/content
   trust split.
5. Browser, receipt, permit, app-manifest, and error contracts.
6. `hepta-agent-transport`, a connected-stream AF_UNIX carrier source with:
   - kernel `SO_PEERCRED` PID/UID/GID extraction;
   - explicit peer policy;
   - fresh 256-bit server nonce;
   - fixed 88-byte versioned frames;
   - 256 KiB pre-allocation payload bound;
   - SHA-256 payload binding;
   - strictly increasing request sequence;
   - one monotonic absolute deadline per complete frame.
7. `hepta-browser-codec`, a product-owned canonical Browser API codec with:
   - recursive duplicate-member rejection;
   - strict unknown-field and session/generation binding;
   - signed-64-bit integer-only canonical JSON;
   - 256 KiB/depth/container bounds;
   - typed navigation and semantic references;
   - request/response canonical SHA-256;
   - navigation and mutating gestures classified as potential external effects.
8. `hepta-agent-port`, a connected-stream D0C-04 source candidate with:
   - one request and at most one typed handler invocation per connection;
   - immutable peer/sequence/digest/effect/deadline dispatch context;
   - response identity copied from the validated request;
   - canonical response hashing before transport commit;
   - earlier-of server/request monotonic deadline;
   - late-result discard without response commit;
   - bounded handler output;
   - a mechanism-only fixture that denies potential external effects and never
     simulates BrowserActor/Servo success.
9. Exact Cargo dependency pins and checksum-bound registry allowlist. D0C-04
   adds no new registry package.
10. Browserd self-check source now composes transport, codec, AgentPort and the
    session state machine.

## Executed source/reference evidence

The independent standard-library references recorded for this stacked
candidate report:

```text
D0C-02 authenticated transport reference   15/15 PASS
D0C-03 canonical Browser codec reference    27/27 PASS
D0C-04 connected AgentPort reference        13/13 PASS
```

Source/contract audits report:

```text
D0C-03 Rust codec static audit              96 checks PASS
D0C-04 Rust AgentPort static audit         172 checks PASS
```

These are source/reference results. They do not prove Rust compilation or
product runtime behavior.

## Exact-head Rust gate remains open

No trusted Rust 1.93.0 execution result is recorded for the exact D0C-04 head.
The following commands remain required:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo test --locked -p hepta-browser-codec
cargo test --locked -p hepta-agent-port
cargo run --locked -p hepta-browserd -- --self-check
```

The candidate remains Draft/non-merge-ready until these pass and evidence is
updated atomically.

## What is not implemented or claimed

- No filesystem, abstract Unix, TCP or WebDriver listener is bound.
- No systemd socket activation or product Agent listener is enabled.
- No TaskFlow principal-to-service identity mapping exists.
- No BrowserActor is implemented or dispatched.
- No Servo source is linked by the product workspace.
- No `WebView`, rendering context, visible first frame, Wayland surface or
  native input/IME path exists.
- No resolved Debian package snapshot or bootable QEMU image exists.
- No external interaction, capability, credential use or web effect is
  authorized.
- No signed app runtime, update chain, Secure Boot chain, beta or release claim
  exists.

## Active next work

1. Execute and repair the exact Rust 1.93.0 gate for the stacked D0C-02 through
   D0C-04 candidate.
2. Complete `D0A-01` against pinned Servo commit
   `670ae8a70801b162e186f81cbb5bdd2d59c39108`.
3. Implement `D0A-02`, the product-owned headed wrapper with trusted system
   chrome and exactly one untrusted content WebView.
4. Rebuild the default-disabled D0C-05 socket-custody layer only after the
   connected product path is exact-head validated.
5. Resolve signed Debian inputs before `D1-01`.

A source file, schema, reference implementation or failed-before-start CI run
is not runtime evidence.
