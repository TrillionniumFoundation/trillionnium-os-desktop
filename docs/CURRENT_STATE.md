# TrillionniumOS Desktop — current state

**Updated:** 2026-08-28
**Canonical plan:** `2026-08-28-d5`
**Repository mode:** `FULL_PRODUCT_REPOSITORY`
**Implementation stage:** `D0R_D0C02_SOURCE`

## What is implemented in source

1. The canonical Rust 2024 product workspace and D0 contract/session foundation.
2. Layered session, document, semantic-snapshot, and mutation revisions.
3. Deterministic Agent/human arbitration with bounded FIFO admission.
4. Synthetic HTTPS trusted-app origins and an explicit trusted-shell/content
   trust split.
5. Browser, receipt, permit, app-manifest, and error contracts.
6. `hepta-agent-transport`, a connected-stream AF_UNIX carrier source
   implementation with:
   - kernel `SO_PEERCRED` PID/UID/GID extraction;
   - explicit peer policy;
   - fresh 256-bit server nonce;
   - an 88-byte versioned frame header;
   - a 256 KiB pre-allocation payload bound;
   - SHA-256 payload binding;
   - strictly increasing request sequences;
   - one monotonic absolute deadline across each complete frame.
7. An exact Cargo registry dependency allowlist and checksum-bound lock closure.
8. Browserd self-check source that includes the local transport round trip.
9. Fail-closed repository validation for the desktop/mobile graph, transport
   contract/source alignment, dependency closure, claim ceiling, and absence of
   a product listener.

## Validation ceiling

Static JSON/TOML/source consistency checks for this D0C-02 candidate were
performed while constructing the branch. A trusted Rust 1.93 execution
environment was not available, and GitHub hosted jobs previously failed before
runner assignment. Therefore the following remain **UNEXECUTED** for this exact
head:

- `cargo fmt --all --check`;
- `cargo clippy --workspace --all-targets --locked -- -D warnings`;
- `cargo test --workspace --all-targets --locked`;
- `cargo run --locked -p hepta-browserd -- --self-check`.

The D0C-02 candidate is not merge-ready until those checks execute on the exact
head in a trusted environment.

## What is not implemented or claimed

- No filesystem or abstract Unix socket is bound.
- No systemd socket activation or product Agent listener is enabled.
- No Browser API codec is dispatched over the carrier yet.
- No Servo source is linked by the product workspace.
- No `WebView`, rendering context, visible first frame, Wayland surface, or
  native input path exists.
- No resolved Debian package snapshot or bootable QEMU image exists.
- No external interaction, capability, credential use, or web effect is
  authorized.
- No signed app runtime, update chain, Secure Boot chain, beta, or release
  claim exists.

## Active next work

1. Obtain exact-head Rust validation for `D0C-02`; only then promote it from
   source candidate to host-validated carrier core.
2. Complete `D0A-01` against pinned Servo commit
   `670ae8a70801b162e186f81cbb5bdd2d59c39108`.
3. Implement `D0A-02`, the product-owned headed wrapper with one trusted shell
   surface and exactly one untrusted content WebView.
4. Integrate `D0C-03` canonical Browser API decoding and `D0C-04` exactly-one
   request dispatch before any listener activation.
5. Resolve signed Debian inputs before `D1-01`.

A source file, schema, static validator, or failed-before-start CI run is not
runtime evidence.
