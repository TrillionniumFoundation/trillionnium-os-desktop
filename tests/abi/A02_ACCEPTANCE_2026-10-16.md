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
