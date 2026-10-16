# A02 saved-status mutation coverage acceptance — 2026-10-16

Actual main base: `3b2d15bc987e7ca78e64fa54edffb2177b8abde0`.
Existing A02 parent: `e7725547c905952140fc9b3b6b93d63b3c169b1b`.
The existing [PR #72](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/72)
continues on `agents/A02-hos2-wire`; no remote history is rewritten.
Only A02-owned paths change. The production no_std codec, Cargo manifest,
protocol versions and all committed golden bytes remain unchanged in this increment.

## Reproduced coverage defect and correction

Changing the production QueryDelivery encoder from
`put_u16(out, 2, v.saved_status.as_u16());` to `put_u16(out, 2, 0);`
corrupts every saved terminal rejection. On the parent, that actual compiled
mutant survived the complete **54 unit/integration tests plus 1 doctest**.
The original golden encoder inputs only represented saved_status=0, while the
24 newer semantic edge fixtures were decoded but never encoded.

Three added semantic edge tests now:

- Compare all 24 fixed edge frames against their encoded bytes, with exact
  capacity and 17 extra bytes, preserving the unused tail.
- Reject all **2,816** strictly insufficient output capacities without writing.
- Construct all **11** saved terminal rejection `Response` values independently
  of the decoder and compare their encoding with the independent Python bytes.

Four added negative tests check self-consistent InstallBudget results against
an incompatible expected_revision, retirement results below the requested
frontier, and all **40** mismatched public request/response opcode-payload pairs.
The correlated response APIs reject the mismatches; encoders leave output intact.
`matches_request` only compares opcode and ID; callers needing the full check
must use `validate_for` or a correlated decoder.

The existing source mutation runner now includes the saved_status encoder
mutation alongside cap and revision equality mutations. Temporary repositories
preserve `libs/os-abi` and `tests/golden` paths for the fixed include_str input.
Both unmodified test-suite baselines must pass before any mutant is judged.
Compilation errors, timeout, ignored/filtered tests, incomplete output or a
failure of an unrelated test cannot substitute for the designated regression.

## Actual final validation

Host: Linux x86_64, Rust/Cargo 1.95.0, Python 3.12.14.
No kernel build or QEMU execution is claimed.

| Command/check | Actual result |
| --- | --- |
| `cargo test --manifest-path libs/os-abi/Cargo.toml` | **61/61** unit/integration + **1/1** doctest; 0 failures, ignored or filtered |
| `cargo fmt --manifest-path libs/os-abi/Cargo.toml -- --check` | Pass |
| `cargo clippy --manifest-path libs/os-abi/Cargo.toml --offline --all-targets -- -D warnings` | Pass |
| `cargo check --manifest-path libs/os-abi/Cargo.toml --offline --no-default-features --target x86_64-unknown-none` | Pass |
| `python3 tests/golden/generate_hos2.py --check` | **12/12** |
| `python3 tests/golden/generate_transport32.py --check` | **1/1** |
| `python3 tests/golden/generate_hos2_edges.py --check` | **24/24** |
| Python ABI discovery, normal and `-O` | **30/30 each**, 0 failures/errors/skips |
| Independent Python mutation suite | **9/9**, 0 failures/errors/skips |
| Rust mutation baselines | Canonical comparison **7/7**; semantic edges **12/12** |
| Compiled Rust source mutants | **3/3 killed**, each with its designated regression failing |
| Mutation evidence-parser controls | **6/6**: complete, ignored, missing, duplicate, filtered and missing-summary output |
| `git diff --check`; root README | Pass; **0 bytes** |

Rust test denominator: 3 unit + 8 golden + 7 canonical mutation + 21 negative +
12 semantic edge + 6 transport preflight + 4 transport golden = 61, plus 1 doctest.
The cap and revision mutants each run 7 tests: 5 pass and 2 intentionally fail.
The saved_status mutant runs 12: 10 pass and 2 intentionally fail. All compile;
none time out, skip or filter tests. These six assertion failures are successful
negative controls, not failures of production. During test development one
capacity-count expectation was mistyped as 2,856; it was corrected to the actual
2,816, and the complete final suite passes. No failure or skip remains unexplained.

Reproduce the actual source mutations with:

```sh
python3 tests/abi/run_rust_mutations.py --cargo cargo --output /tmp/hos2-mutants.json
```

Full logs, command exit codes and source/fixture SHA256 are committed in:

- `results/saved-status-acceptance-2026-10-16.json`
- `results/rust-source-mutations-saved-status-2026-10-16.json`
- `results/saved-status-before-control-2026-10-16.json`

The before/after controls have the **same mutated production source SHA256**;
only the tests differ. The first report hashes all implementation/test inputs.
GitHub Actions status is separate from these actually executed local checks.

## Golden timing and A03/A05 handoff

Original ReadUsage remains sample=150ms, window_start=100ms, consumed=35ms,
cap=20ms: 35<=50 and 35>20. Installation and saved history remain effective=140ms,
consumed=33ms: 33<=40. No consumption value was reduced or fixture regenerated.

The current shared Rust interface is the dependency-free `hos2_os_abi` crate:

- Owned `Request`, `Response`, payload value types, `Opcode`, `Status`, `Error`.
- `decode_request`/`encode_request`, `decode_response`/`encode_response`.
- `Transport::decode`/`validate` before copying input once, then
  `Transport::decode_request_snapshot` before semantic admission.
- `decode_response_for`, `decode_response_prefix_for`, `Response::validate_for`
  for request association; prefix variants consume only the declared frame.
- `install_budget_request_id` and `install_budget_sequence` for canonical
  little-endian ordered IDs with a zero high half.

No new wire contradiction was identified and no protocol decision was changed.
HOS2 **major=2/minor=0 remains experimental**, not a released stable ABI.
Published ioctl numbering and validation outside the x86_64 little-endian profile
remain open. Actual kernel consumer integration, user-copy faults, CapSpace
permissions, CPU enforcement and original Hepta durable-owner effects remain
A03/A05/A06/A07 integration work; codec acceptance does not establish them.
