# TrillionniumOS Desktop — current state

**Updated:** 2026-08-28
**Canonical plan:** `2026-08-28-d5`
**Repository mode:** `FULL_PRODUCT_REPOSITORY`
**Implementation stage:** `D0R_D0C_FOUNDATION`

## What is implemented

The repository now contains the initial product implementation rather than only
planning documents:

1. A Rust 2024 workspace with `rust-version = 1.93` and four initial packages:
   `trillionnium-contract-core`, `hepta-browser-contracts`,
   `hepta-session-core`, and `hepta-browserd`.
2. Layered revision identity:
   `session_generation`, `document_generation`,
   `semantic_snapshot_revision`, and `mutation_epoch`.
3. A deterministic Agent/human state machine covering Agent observation and
   mutation, human focus leases, IME composition, navigation, modal state,
   capability waits, cancellation, browser crash, recovery, and closure.
4. A bounded FIFO arbiter queue that fails closed on overflow.
5. A trusted-origin decision using distinct synthetic HTTPS hosts under
   `*.apps.hepta.invalid`; path-only custom-scheme origins are not used.
6. Machine-readable schemas for browser requests, operation receipts,
   capability permits, and signed app manifests, plus error codes and golden
   vectors.
7. Product-boundary checks that prevent Android/mobile direct shell, ADB,
   Root-Linux, and privilege-broker packages from entering the desktop default
   graph.
8. A `hepta-browserd --self-check` scaffold that exercises preemption,
   revisions, navigation, crash, and recovery without opening a listener or
   network connection.
9. CI and repository validation definitions.

## What is not implemented or claimed

- No Servo source is linked or built by this repository yet.
- No `WebView`, rendering context, Wayland surface, keyboard/pointer path, or
  IME adapter exists yet.
- No Unix-domain Agent API listener exists; therefore peer-credential and
  channel-binding authentication are not yet product facts.
- No Debian snapshot has been fully resolved to `InRelease` and package-set
  digests, and no bootable QEMU image exists.
- No trusted shell bundle is signed or loaded.
- No network egress proxy, file portal, secret service, update daemon, Secure
  Boot chain, or A/B rollback image exists.
- No external webpage interaction or external effect is authorized.
- No public release, beta image, or hardware-qualification claim exists.

## Active next work packages

1. `D0A-01`: build a pinned Servo compatibility spike at commit
   `670ae8a70801b162e186f81cbb5bdd2d59c39108`.
2. `D0A-02`: prove one visible workspace containing a trusted shell surface and
   exactly one untrusted content WebView, without a hidden second Agent page.
3. `D0C-02`: bind JSON contracts to a bounded authenticated UDS carrier with
   peer credentials, session nonce, deadlines, cancellation, and strict frame
   handling.
4. `D1-01`: resolve the Debian snapshot and build the first reproducible QEMU
   image only after its signed package inputs are locked.

A source file, schema, self-check, or CI definition is not evidence that Servo
or Debian bring-up has completed. Stage promotion requires the exit evidence in
the canonical plan.
