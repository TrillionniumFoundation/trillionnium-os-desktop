# hos2-os-abi

The shared no_std HOS2 wire codec. This crate parses and encodes bounded data;
it does not allocate process authority, perform device I/O or publish durable
Hepta outcomes.

## Technical contract

[NATIVE_ABI](../../docs/NATIVE_ABI.md) is the normative wire/semantic contract.
[src/lib.rs](src/lib.rs) contains the implementation; [tests](tests/) cover
golden vectors, malformed data, mutation controls and transport boundaries.
Use the independent [golden generator](../../tests/golden/generate_hos2.py)
when changing wire representations, rather than regenerating expected bytes
with the same codec under test.

QueryAbi, ReadUsage, InstallBudget, QueryDelivery and RetireThrough share the
codec. Their availability is controlled by the kernel profile: ordinary
exposes QueryAbi, G1-c adds trusted observation and G1-d exposes the fixed
trusted-control experiment. Codec acceptance does not establish permission
or native execution.

## Development and verification

From the repository root:

```sh
cargo test --manifest-path libs/os-abi/Cargo.toml
python3 tests/golden/generate_hos2.py --check
```

These are development checks. The pinned acceptance procedure, source-derived
negative controls and toolchain scope are in
[A02 review closure](../../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md) and
[run_acceptance.py](../../tests/abi/run_acceptance.py). Coordinate wire changes
with kernel and Hepta consumers; never infer production qualification from
codec or model tests. Current profile evidence is linked in
[ARCHITECTURE](../../docs/ARCHITECTURE.md) and [STATUS](../../docs/STATUS.md).
