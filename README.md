# TrillionniumOS Desktop

TrillionniumOS Desktop is the full product repository for a Debian-based,
AI-native desktop appliance. The product direction is one trusted desktop
shell plus one Agent/human-shared Servo content surface in one visible
workspace. System capabilities remain outside the browser process.

## Current implementation status

The repository follows canonical plan revision `2026-08-28-d5`.

Host-validated today:

- Rust 2024 workspace pinned to Rust 1.93.0;
- platform-neutral contracts and layered session/document/snapshot revisions;
- deterministic Agent/human arbitration and bounded queues;
- `hepta-agent-transport`, a connected-stream AF_UNIX carrier with
  `SO_PEERCRED`, per-connection nonce binding, fixed bounded SHA-256 frames,
  strict sequences and absolute monotonic deadlines;
- exact Cargo dependency name/version/checksum closure;
- independent Python reference and golden transport vector;
- repository contract validation, formatting, Clippy with `-D warnings`,
  25 Rust tests and the integrated non-networked browserd self-check.

D0C-02 is a host-validated **carrier core**, not a listener. No filesystem or
abstract socket is bound by this stage.

Not implemented or claimed:

- canonical Browser API decoding over the carrier;
- exactly-one BrowserActor dispatch;
- a product Agent listener or systemd socket custody;
- Servo embedding, a visible window or native input;
- a bootable Debian/Wayland image;
- external interactive effects, credentials, capabilities or release signing.

## Start here

- [`docs/DESKTOP_PLAN.md`](docs/DESKTOP_PLAN.md) — canonical-plan index
- [`docs/DESKTOP_PLAN-2026-08-28-d5.md`](docs/DESKTOP_PLAN-2026-08-28-d5.md) — active plan
- [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — exact demonstrated state
- [`docs/evidence/2026-08-28-d0c02-authenticated-uds.md`](docs/evidence/2026-08-28-d0c02-authenticated-uds.md) — D0C-02 evidence
- [`contracts/`](contracts/) — machine-readable product contracts
- [`manifests/`](manifests/) — source, dependency and product-boundary locks

## Required checks

```bash
python3 tools/validate_repository.py
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo run --locked -p hepta-browserd -- --self-check
```

`hepta-browserd --self-check` starts no browser, listener or network operation.
A check is evidence only when it succeeds against the exact commit under
review.
