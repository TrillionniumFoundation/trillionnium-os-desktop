# A02 generation and N0 profile mutation acceptance — 2026-10-16

Actual final main base and increment parent: `0709ab5d4a1892b5dd0a69fb9af1f313ea3e9c7c`.
The prior [PR #72](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/72)
was merged while this work ran. Its final source commit
`eef96afd4c3fcdc5bcdc2b8ba00260e1fb116b91` is the before-control baseline.
The owner branch `agents/A02-hos2-wire` was fast-forwarded onto the new main;
only the A00-owned STATUS record differed, and that exact main content is retained.
This increment receives a new PR; the merged PR is not reopened.
All changes remain within A02 ownership. This increment changes tests and their
existing mutation runner; the production codec, manifest, dependencies, wire
layout and golden bytes remain unchanged. Root README stays 0 bytes.

## Confirmed gaps and regression coverage

Nine new deliberate production-source variants survived the parent's complete
61 unit/integration tests plus its doctest. No corresponding production bug was
found: this work closes demonstrated test gaps against the current written ABI.

| Surviving wrong variant | Minimal distinguishing case | Required result |
| --- | --- | --- |
| Request equality ignores target_generation | Same sequence and slot, generation 9 -> 10 | Different canonical request / conflict |
| InstallBudget advertisement ignores history dependencies | QueryAbi supported_ops=0x0e | InvalidField |
| RetireThrough advertisement accepts ReadUsage instead of QueryDelivery | supported_ops=0x26 | InvalidField |
| No minimum advertised request capacity | Full profile, max_request_payload=39 | InvalidField |
| ReadUsage advertised response minimum lowered to 48 | supported_ops=0x06, request=0, response=48 | InvalidField |
| Zero active CPU cap rejected | cap=0, real consumed CPU remains positive | Accept |
| cap equal to the fixed period rejected | cap=100000000 | Accept |
| Consumption equal to elapsed time rejected | sample=150ms, start=100ms, consumed=50ms | Accept |
| Earlier misaligned window accepted | window_start=99999999, sample=150ms | InvalidField |

The generation test changes offset 48 of independent InstallBudget bytes and
requires full Request inequality and the existing canonical retry classifier's
conflict result. It introduces no second delivery state machine.

Seven new Rust profile tests independently construct public typed responses and
patch the existing Python-generated fixed bytes at documented offsets. Every
case checks both decode and encode. Invalid typed input must leave all output
unchanged; successful encoding preserves extra capacity.

QueryAbi coverage includes all supported masks 0..127, every high unknown bit,
the seven legal profiles, **19,404 request/response capacity pairs**, exact
65536 bounds, 65537/u32::MAX rejection, all 32 nonzero u32 power-of-two page sizes
and their invalid neighbors. The legal profile table is enumerated independently
of production bit checks:

| supported_ops | Minimum request payload | Minimum response payload |
| --- | ---: | ---: |
| 0x02 | 0 | 48 |
| 0x06 | 0 | 64 |
| 0x12, 0x16, 0x32, 0x36, 0x3e | 40 | 64 |

ReadUsage coverage includes cap=0/period, consumed=0/elapsed, equal event/drop
counters, boot/window boundary samples and u64::MAX, misaligned/future starts,
one-nanosecond excess consumption and inconsistent statistics. Three independent
Python tests reuse the existing Python byte oracle for the profile table, the
same 19,404 capacity pairs and CPU-window endpoints; no extra production parser
or dependency was added.

## Actually executed

Environment: Linux x86_64, Rust/Cargo 1.95.0, Python 3.12.14.

| Command/check | Actual result |
| --- | --- |
| `cargo test --manifest-path libs/os-abi/Cargo.toml` | **69/69** unit/integration + **1/1** doctest; 0 failed/ignored/filtered |
| `cargo fmt --manifest-path libs/os-abi/Cargo.toml -- --check` | Pass |
| `cargo clippy --manifest-path libs/os-abi/Cargo.toml --offline --all-targets -- -D warnings` | Pass |
| `cargo check --manifest-path libs/os-abi/Cargo.toml --offline --no-default-features --target x86_64-unknown-none` | Pass |
| Independent golden generators | HOS2 **12/12**, semantic edges **24/24**, transport **1/1** |
| Python ABI discovery, normal and `-O` | **33/33 each**, 0 failures/errors/skips |
| Independent Python mutation suite | **9/9**, 0 failures/errors/skips |
| Compiled-source mutation baselines | Canonical **8/8**, semantic **12/12**, profiles **7/7** |
| Compiled-source mutants | **12/12 killed**, 0 compiler failures/timeouts/skips/filtered tests |
| Old-suite survival controls | **9/9 survived all 61+1 old tests**, each source SHA256 matches its new-suite killed counterpart |
| `git diff --check`; root README | Pass; **0 bytes** |

Rust denominator: 3 unit + 8 golden + 8 canonical mutation + 21 negative +
7 profile + 12 semantic edge + 6 transport preflight + 4 transport golden = 69,
plus 1 doctest. Production has zero unexpected failures and no skipped item.
The 12 deliberately wrong compiled variants produce **17 expected assertion
failures** across their complete suites. Each named designated regression must
fail with Rust test exit 101; compilation errors, timeout and incomplete or
filtered execution never count as a kill. All three production baselines must
pass before mutants run. Schema v2 records expected counts separately per suite
and requires exactly 12 mutants.

Reproduce source mutations:

```sh
python3 tests/abi/run_rust_mutations.py --cargo cargo --output /tmp/hos2-mutants.json
```

Full commands/logs and source/fixture SHA256:

- `results/profile-boundary-acceptance-2026-10-16.json`
- `results/rust-source-mutations-profile-2026-10-16.json`
- `results/profile-before-controls-2026-10-16.json`

The before/after controls use identical mutated source bytes; the tests differ.
The production source hash and all input hashes match the final tested files.
GitHub Actions results are separate from these executed local checks.

## Protocol and consumer boundary

No new protocol contradiction or wire decision was introduced. HOS2 remains
experimental major=2/minor=0. Original ReadUsage consumed=35ms in 50ms elapsed
with cap=20ms, and installation/history consumed=33ms in 40ms elapsed remain
unchanged. New test variants do not rewrite the committed consumption fixtures.

A03/A05 continue consuming the same dependency-free no_std `hos2_os_abi` API:
owned Request/Response and payload types, explicit encode/decode,
Transport::validate/decode_request_snapshot, correlated/prefix response decoders,
Response::validate_for and canonical ordered sequence ID helpers. QueryAbi
advertisement describes format support and grants no authority. Changed
capability generations remain canonical request content, even for the same slot.

Published ioctl numbering, other architecture transport validation and actual
kernel consumer integration remain open. These host checks do not implement or
verify kernel syscall routing, user copies, CapSpace authorization, CPU throttling
or the original Hepta owner's durable effects.
