# Product manifests

These files record selected and locked product inputs and explicit blockers.
A file may intentionally state that a required lock is unresolved; this is a
fail-closed stage gate and not a completed image claim.

- `repository-state.json` — implementation and non-claim status
- `servo.lock.json` — pinned Servo compatibility-spike commit
- `rust-toolchain.lock.json` — Rust compiler/tool components
- `debian-base.selection.json` — selected base and unresolved snapshot fields
- `product-boundary.json` — desktop/mobile dependency firewall
