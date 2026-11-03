# UI boundary and host integration support

This directory contains the dependency-light `trill-ui-boundary` contract
model and host packaging/verification tools. The executable Rust desktop is the
separate [UI workspace](../../ui/README.md). This model never launches a
process, opens Wayland/SurfaceFlinger, installs a grant or resets a GPU.

## Technical ownership

[src/lib.rs](src/lib.rs) distinguishes process lifetime, Session generation,
compositor links and surfaces. A Shell restart leaves the application's
process intact; a compositor/GPU generation change requires surface recreation.
[android.rs](src/android.rs) models buffer/synchronization/input ownership,
while [permission.rs](src/permission.rs) consumes observations supplied by a
trusted authority. Neither model creates a permission protocol or device
executor. The HOS2 adapter reads through the shared codec and exposes no
budget/revoke/effect entry.

## Development and verification

```sh
cargo test --locked --manifest-path support/ui/Cargo.toml
bash tests/ui/check-host.sh
```

The package test is a pure host contract check. The second command has the
graphical prerequisites and scope in [RUN](RUN.md) and the
[test plan](../../tests/ui/TESTPLAN.md). Real window/compositor behavior,
text input and device operation require their own actual runs.

For product changes read [PRODUCT](PRODUCT.md), for native rendering read
[NATIVE_MAKEPAD](NATIVE_MAKEPAD.md), and for the saved-document and recovery
path read [NOTES_DURABILITY](NOTES_DURABILITY.md). Packaging verifies the
Cargo-resolved original resources and notices. A failed resource check must
stop startup; it must not replace original resources with whatever is cached.

## Failure and recovery boundary

An invalid generation invalidates its surfaces; a stale permission/Hepta
observation remains stale or unknown until its owner produces a fresh one.
Draw and layout markers cannot settle an effect. Transport timeouts after a
possible write require original-owner reconciliation. Application checkpoints
and local draft recovery retain their distinct owners and may not restore
effect authorization. See [BOUNDARIES](BOUNDARIES.md) and
[integration contracts](INTEGRATION_CONTRACTS.md).
