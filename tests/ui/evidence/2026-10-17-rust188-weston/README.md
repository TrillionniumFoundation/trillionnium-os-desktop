# Rust 1.88 host and Weston evidence, 2026-10-17

The full Linux host gate and headless Weston gate both passed on source
`d57a1be747c1fe0877334d4676d2ddf93dbcac92`, tree
`dda7f6564be2d301a8f4502e8c53b739c79d2cf4`. This includes actual Rust
Session/Shell processes, real private Unix sockets, bidirectional peer-UID
refusal, packaged ELF replay, and a completed Hepta page layout that consumed
a fresh Session projection from an explicitly scripted Agentd-protocol fixture.

The final source is `5d6fbb9d81330bb9e21f7f3d3e4b4d784e6ceaa9`, tree
`c2950ff1bfb51ee09edb60d921b1879fc4ac8ba9`. Its only difference from the
full-gate source is an equivalent Rust format capture in
`ui/session/tests/ipc_reconnect.rs`. Strict UI Clippy, that real reconnect
test, all four formatter checks, and the locked offline metadata gate passed
on this final source. The full host/packager/Weston matrix was not repeated
after that test-only lint correction. The final check records a Git comparison
proving that every other tracked file remained identical.

A00's publication verification maps the full-gate source to remote commit
[`3afa4683795b14977b44ccb7ac47447980ad5e5b`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/3afa4683795b14977b44ccb7ac47447980ad5e5b)
and the final source to
[`d69f04df16435c86951365aa20a4c9282f7b4428`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/d69f04df16435c86951365aa20a4c9282f7b4428),
with the respective Git trees above unchanged. Raw execution metadata keeps
the local producer commit IDs. This record is local execution evidence; it
does not report a completed GitHub Actions run on the published commits.

## Executed results

| Attempt | Source | Exit | Result |
| --- | --- | ---: | --- |
| `check-host-01` | `a643aba` | 1 | Real Rust build and 136 tests passed; the strict IPC script exposed a child-exit versus Cancel race. |
| `check-host-02` | `d57a1be` | 0 | Full host gate, four Cargo suites, live socket probes, strict formatting, real ELF packaging and replay passed. |
| `weston-01` | `d57a1be` | 0 | Shell/app layouts, Hepta page projection, owned compositor crash/restart and new-client layout passed. |
| `clippy-01` | `d57a1be` | 101 | Strict Clippy rejected an existing positional format argument in a reconnect test. |
| `clippy-02` | `5d6fbb9` | 101 | Offline Cargo stopped before compilation because a standard crate download archive had been removed during cache cleanup. |
| `clippy-03` | `5d6fbb9` | 0 | Standard archives restored with the unchanged lock; UI workspace/all-targets Clippy passed with `-D warnings`. |
| `reconnect-01` | `5d6fbb9` | 0 | The modified real private-socket reconnect integration test passed, 1/1. |
| `cargo-fetch-02` | `5d6fbb9` | 0 | Remaining locked target archives restored for complete offline metadata resolution. |
| `final-check-01` | `5d6fbb9` | 0 | Four manifest formatter checks, committed unchanged lock, 332-package offline metadata, empty root README, source equivalence and clean working tree passed. |

The passing full host run contains **136 Rust tests**: 72 UI workspace tests,
17 A07 observer tests, 39 `support/ui` host boundary tests, and 8 `tests/ui`
contract tests. No tests failed or were ignored. The host gate also exercised
eight forged wire frames against the actual Session, preserved task ID 1 for
the first legitimate launch, observed real owned-child cleanup, and tested
root/nobody peer refusal in both directions while the same-UID owner remained
served. The container emitted sudo audit-message warnings; the actual checked
UID-boundary assertions still completed successfully. Their output is retained.

The runtime was **Rust 1.88.0**, commit
`6b00bc3880198600130e1cf62b8f8a93494488cc`, on Linux
`x86_64-unknown-linux-gnu`, with **Weston 13.0.0**. This is separate from the
repository's nightly kernel development toolchain. The exact environment
wrapper is preserved in [runtime/run-host-rust.py.txt](runtime/run-host-rust.py.txt).

## What the fixes changed

The strict raw-IPC probe previously required a Cancel task acknowledgement
whenever Launch initially reported Running. An actual headless GUI child can
exit and be reaped between those two requests. The corrected probe also accepts
only the precise no-owned-live-child domain error, then requires the same
task ID and PID to appear as Failed with an observed non-successful process
exit. It retains all malformed-frame refusals, the first legitimate ID check,
and the requirement to observe actual child cleanup. It does not infer
successful cancellation from an error or an acknowledgement alone.

The final Clippy fix changes the test's positional format argument to an
equivalent captured variable. It does not change the transmitted JSON payload
or production code. Both failures and their subsequent passing runs are kept.

The cache failure is separate: this Cargo invocation required the compressed
crate archive even though the unpacked source and `.cargo-ok` were present.
The failed offline invocation was retained, ordinary registry archives were
restored using the existing lock, and the final offline metadata check passed.
No dependency versions, compiler pin or gate assertions were weakened.

## Hepta page evidence

[weston-01/logs/hepta-layout/evidence.json](weston-01/logs/hepta-layout/evidence.json)
binds the actual Rust Session and Shell binary hashes, fixture source hash and
the completed Hepta page marker. The marker came from Shell PID 512727 after
it consumed Session PID 512724's fresh projection:

| Field | Observed value |
| --- | --- |
| Page / connection | `hepta` / `observed` |
| Agent identity | `11111111-1111-4111-8111-111111111111` |
| Immutable spawn generation | `7` |
| Running current generation | `8` |
| Scripted fixture process | `512723` |
| Sample time, Unix milliseconds | `1792235327235` |

The generic Conversation first-frame marker cannot satisfy this probe.
`--page hepta --hepta-layout-probe` must be explicit; emission requires a
completed Hepta widget update, a connected Session and a fresh Observed
projection. The JSON includes only bounded source metadata. Settings now
shows the shared connection state. The observer still has no authenticated
objective submission adapter, and drafts remain local.

The separate
[Session probe](check-host-02/a10/session-observer-probe.json)
observed the scripted fixture and then stopped it. Session changed to Stale
while retaining the identical last observation; a host action response arrived
in about 100 ms. These are real Rust/Unix-socket observations of a scripted
protocol peer. The fixture is not original Hepta Agentd.

## Qualification limits

- Original upstream Agentd was not started by these UI tests. Source-derived
  lifecycle conformance is separate A07 evidence and does not substitute for
  running the original daemon. Authenticated objective submission and device
  effects remain unverified.
- [weston.log](weston-01/logs/weston.log) explicitly selects the **no-op
  renderer**. The Hepta marker proves completed egui widget layout and fresh
  projection consumption. It does not prove compositor pixel presentation,
  a screenshot, physical GPU output or monitor mapping.
- [Hepta Shell stderr](weston-01/logs/hepta-layout/shell.stderr.log) reports
  **no supported host CJK font**. Chinese glyph appearance and a live IME
  candidate/preedit flow were not accepted in this run.
- The compositor restart test kept the same Session and observed a changed
  socket epoch followed by a newly launched client's layout. The old client
  failed; its prior surface continuity was not verified.
- Target Rust-kernel UI, Android/mobile runtime and WASM runtime were not run.
  The 39 boundary-model tests include Android-shaped contracts, which do not
  qualify Android execution or device display/input.

## Reproduction and raw preservation

Provision the exact Linux dependencies and Rust pin in
`.github/workflows/a10-host.yml`, then run from the repository root with
`RUSTUP_TOOLCHAIN=1.88.0`. A nondefault `CARGO_TARGET_DIR` is supported by all
binary-consuming gates. Use a fresh artifact directory for each attempt.

```sh
bash tests/ui/check-host.sh
bash tests/ui/headless-weston.sh
cargo clippy --manifest-path ui/Cargo.toml --workspace --all-targets --locked --offline -- -D warnings
cargo metadata --manifest-path ui/Cargo.toml --locked --offline --format-version 1
```

The two host scripts need permission to create their own private Unix sockets;
the UID-negative probe additionally uses the CI runner's configured sudo.
They start only their owned test processes. The Hepta page probe uses the
explicit A07 fixture and preserves its output even on failure.

[summary.json](summary.json) records source qualification, individual outcomes,
counts, hashes, failures and unverified capabilities. Each attempt's
`execution.json` retains its exact command, producer commit/tree and exit
status. [raw-artifacts.json](raw-artifacts.json) records original paths, byte
lengths and SHA-256 values for all 42 copied artifacts; [RAW_SHA256SUMS](RAW_SHA256SUMS)
can verify their committed copies. No log whitespace or final blank lines
were normalized. Code/document whitespace checks exclude historical raw
evidence. `final-check-01` preserves the complete metadata stdout as well as
the command result.

The original built binary archive is retained separately at the path recorded
in `summary.json`. Its size is 16,395,572 bytes and SHA-256 is
`3f82a3268f453dbe84b0efb14cd767f32f833721baa0234f9bdda4f6a4e85631`.
The archive was built and replayed at `d57a1be`; its checksum file and complete
replay output are committed here. The 16 MB binary archive itself is not
duplicated in this Git evidence directory.
