# Product manifests

These files record selected and locked product inputs and explicit blockers.
An input lock does not prove a built or booted product; claim ceilings remain
explicit and fail closed.

- `repository-state.json` — implementation, validation and non-claim status
- `servo.lock.json` — pinned Servo compatibility-spike commit
- `rust-toolchain.lock.json` — Rust compiler/tool components
- `debian-base.selection.json` — selected Debian base and canonical lock pointer
- `debian-snapshot.requirements.v1.json` — signed snapshot and resolver policy
- `debian-snapshot.lock.v1.json` — exact signed InRelease and package closure
- `product-boundary.json` — desktop/mobile dependency firewall
