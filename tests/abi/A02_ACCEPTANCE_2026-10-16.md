# A02 exact-source host acceptance — 2026-10-16

## Baseline and scope

Started from actual main `fb135f845dcbf9026010ebbe060c004fda7f8688`, then
fast-forwarded to the existing A02 owner head
`df7cf370382aa3efac0bea2ee197a885f80da3e4`, which already contains that main.
Existing PR: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/65.
No history rewrite, shared protocol change, duplicate production codec, control
state machine, kernel or Hepta owner modification. Root README remains 0 bytes.

The earlier PR65 execution record preserves its historical pending results.
This record supersedes those pending claims only for the exact source tested
below. Host: Linux x86_64; Rust/Cargo 1.95.0; Python 3.12.14. The isolated Rust
toolchain includes rustfmt, Clippy and the `x86_64-unknown-none` target.

## Framing validation fix

Both decoders now validate the snapshot's complete declared length before
dispatching an opcode/status, following NATIVE_ABI section 3. A 64-byte request
with opcode `0xffff` and payload_len=1 returns `Truncated`, rather than
`UnknownOpcode`. Complete unknown opcodes still return `UnknownOpcode`.
The regression covers request and response truncation, trailing bytes and
oversized lengths combined with unknown opcodes, plus unknown response status.

First actual Rust verification (all commands exit 0 after formatting):

```sh
cargo test --manifest-path libs/os-abi/Cargo.toml --offline
cargo fmt --manifest-path libs/os-abi/Cargo.toml -- --check
cargo clippy --manifest-path libs/os-abi/Cargo.toml --offline --all-targets -- -D warnings
cargo check --manifest-path libs/os-abi/Cargo.toml --offline --no-default-features --target x86_64-unknown-none
git diff --check
```

Rust tests: **39 passed, 0 failed, 0 ignored** (3 library, 8 golden,
7 canonical-mutation, 17 negative, 4 transport). Zero doctests are defined.
The golden sweep includes 49,152 reproducible mutated decoder inputs and all
1,160 strict prefixes of the 12 fixed HOS2/HOSR frames. The independent 32-byte
transport fixture is consumed by Rust as well.

The first fmt check exited 1 for unformatted existing PR65 test additions and
the new regression; `cargo fmt` corrected these files. This was a formatting
failure, not a hidden test skip. A later check must pass before final acceptance.

## Golden time evidence

The existing fixed bytes are preserved: ReadUsage sample=150ms, start=100ms,
consumed=35ms, lowered cap=20ms, so 35<=50ms elapsed and **35>20ms cap**.
InstallBudget and terminal history both record effective=140ms and consumed=33ms,
which is <=40ms elapsed. The original consumed values were not reduced.

## Final independent acceptance

The framing fix is pushed as
`9c311354081c589d4f64498dd19333e4c594f77a`. An isolated copy of its predecessor
`df7cf370382aa3efac0bea2ee197a885f80da3e4` was compiled with the new regression:
**1 test failed as expected**, exit 101, specifically `UnknownOpcode` versus
`Truncated`. The fixed source passes the same test in the complete suite.

The existing Python retry oracle incorrectly used `(sequence,target)` as its
reservation key. Its test-only key is now sequence within one CapSpace;
cross-target/generation changes conflict and preserve the original reservation.
Additional independent fixed-payload checks cover ABI capability declarations,
usage accounting, terminal/error history metadata and retirement frontiers.
No production delivery ledger is added.

Final results on the unchanged production Rust source:

| Executed check | Actual result |
| --- | --- |
| Required `cargo test --manifest-path libs/os-abi/Cargo.toml` | **39/39**, 0 failures/ignored; 0 doctests defined |
| Rustfmt, strict Clippy, bare-target no_std check above | All exit 0 |
| `python3 tests/golden/generate_hos2.py --check` | **12/12** fixed HOS2/HOSR frames |
| `python3 tests/golden/generate_transport32.py --check` | **1/1** independent descriptor |
| `python3 -m unittest discover -s tests/abi -p 'test_*.py' -v` | **28/28**, 0 failures/errors/skips |
| Same Python suite under `python3 -O` | **28/28**, 0 failures/errors/skips |
| `python3 -m unittest discover -s tests/abi -p 'test_mutations.py' -v` | **9/9**, 0 failures/errors/skips |
| Real Rust source mutation runner below | Baseline **7/7**; **2/2 compiled mutants killed** |
| `git diff --check`; root README size | Exit 0; **0 bytes** |

```sh
python3 tests/abi/run_rust_mutations.py --cargo cargo \
  --output /tmp/hos2-rust-source-mutations.json
```

This runner copies the actual production type and the unchanged Rust
`mutation_kill` suite to temporary crates. It substitutes a field-omitting
`PartialEq` implementation for `InstallBudgetRequest`, leaving the decoder and
test inputs intact. Both mutants **compile successfully**, then each executes
all seven tests with **5 passed / 2 expected assertion failures**, exit 101:

- `ignore_cap_ns` fails `same_sequence_and_target_different_cap_is_conflict`
  and `cap_ignoring_mutant_is_killed_by_same_delivery_oracle`.
- `ignore_expected_revision` fails
  `same_sequence_and_target_different_revision_is_conflict` and
  `revision_ignoring_mutant_is_killed_by_same_delivery_oracle`.

Compilation failure, timeout, skipped tests or missing expected assertion
failures do not count as mutation kills. Production has **zero failing tests**;
the four mutant assertion failures and the one pre-fix regression failure are
intentional negative controls, not omitted failures.

Full commands, outputs, input SHA256 and exit codes are retained in
[`results/host-acceptance-2026-10-16.json`](results/host-acceptance-2026-10-16.json)
and [`results/rust-source-mutations-2026-10-16.json`](results/rust-source-mutations-2026-10-16.json).
The Rust report's source hash identifies the exact codec tested, even after
the evidence-only commit. The initial CLI push lacked credentials; the
connected GitHub interface pushed the identical verified Git tree without
forcing or overwriting remote history. GitHub Actions status is separate from
these actually executed local checks and is not assumed to be successful.

## A03/A05 interface and untested boundaries

The single dependency-free `#![no_std]` crate remains `hos2_os_abi`:

- `Transport::{new,decode,encode,ensure_success_response_capacity}`; success
  capacity must be checked before semantic admission, including eventual errors.
- `Request`, `RequestPayload`, `Response`, `ResponsePayload`, `Opcode`, `Status`,
  `Error`, and operation payload value types; all wire access is explicit bytes.
- `decode_request`, `encode_request`, `decode_response`, `encode_response`.
- `decode_response_for` and `decode_response_prefix_for` validate request
  correlation; prefix decoding excludes unused copyout capacity.
- `install_budget_request_id` and `install_budget_sequence` construct/extract
  the little-endian ordered sequence with a zero high half; no sequence allocation.

HOS2 is still experimental major=2/minor=0. Published ioctl numbering and
non-x86_64 transport validation remain open. The A03 main host model does not
depend directly on this crate, and A05 currently has a C probe; this run does
not claim a compiled Rust consumer integration. Capability authorization,
user-pointer access/copy faults, syscall routing, actual scheduler enforcement,
concurrency and original Hepta persistence remain untested by this codec suite.
