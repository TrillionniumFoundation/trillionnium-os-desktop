# os-control development and technical entry

This crate owns the in-memory HOS2 delivery namespace, bounded history window,
resource CAS model and public lock-backend seam. Read the normative
[API contract](API_CONTRACT.md) before changing its state machine. The wire
codec lives in [os-abi](../os-abi/README.md); neither a Rust token nor a host
namespace authenticates a kernel caller.

## State, authority and failure

`ControlCoreWith<B>` owns a boot-local namespace and pins the actual native
resource owner for a reservation. The adapter checks current grant, lease,
ancestor epochs and revision under the real owner's mutation lock. Native
execution must not reconstruct a shadow resource or substitute a new grant.
The original Hepta writer owns durable logical operation identity and outcome.

A pending or indeterminate entry blocks replay and contiguous retirement.
An unknown callback result must be reconciled through the pinned original
owner; rebuilding the table cannot establish that no effect occurred. A saved
terminal result survives only as long as this in-memory namespace. The
experimental `portable-spin` backend requires allocator/atomics and separate
kernel IRQ, preemption and lock-order validation. It is unsuitable as an
implicit production kernel lock adapter.

## Build and change procedure

From the repository root, run:

```sh
cargo test --locked --manifest-path libs/os-control/Cargo.toml
cargo test --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin
sh tests/control/run-validation.sh /tmp/a03-current-validation
```

The full driver also checks public downstream compilation, allocation behavior,
Loom schedules and bare `no_std`; use the prerequisites in
[validation](../../tests/control/VALIDATION.md). Tests under
[tests/control](../../tests/control/) are registered by this crate's manifest.
Add a real refusal/race/recovery scenario when changing reservation identity,
publication or retirement. Keep static model, host execution, kernel execution
and durable Hepta qualification separate in the result record.
