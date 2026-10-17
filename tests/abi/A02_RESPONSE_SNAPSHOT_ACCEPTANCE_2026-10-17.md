# A02 response snapshot / copyout-capacity acceptance — 2026-10-17

## Scope and exact source

- Repository: `TrillionniumFoundation/trillionnium-os-desktop`.
- Base main commit: `40ca002fac0726b366726d3353916637b29adeae`.
- A02 branch: `agents/A02-hos2-wire`; PR [#95](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/95).
- Production/test addition: `f32dad0d14eb2731f2e3d394404ede566a964b91`.
- Regression fix: `08f65da4cd784cb1c13a38a599642673c56d86bc`.
- File ownership: `libs/os-abi/src/lib.rs` and `libs/os-abi/tests/response_snapshot.rs`, plus this A02 evidence record. No edits to the shared HOS2 wire, fixed golden vectors, Cargo dependencies, other agents' directories or the zero-byte root README.

## Motivation and contract

Existing `decode_response_prefix_for` intentionally accepts a larger copied response buffer and ignores the unused capacity. It cannot itself know the actual `Transport.response_capacity`; a caller may accidentally pass a buffer larger than ioctl could have copied. The new no_std `Transport::decode_response_snapshot_for(&self, snapshot: &[u8], request: &Request) -> Result<(Response, usize), Error>` delegates to the same production response decoder after enforcing:

1. Transport descriptor validation, including reserved bytes, request length bounds and checked address arithmetic.
2. The typed request's actual wire length equals `Transport.request_bytes`.
3. `snapshot.len() <= Transport.response_capacity`.
4. Enough response capacity for the opcode's *success* response, even when the returned status is an error.
5. Full existing response format validation and semantic request/response correlation.

This helper does not copy userspace memory and must be used only after a successful ioctl/copyout. A copyout fault makes the output invalid, regardless of response data in the caller's buffer. This is a host byte-codec contract, not kernel CapSpace/ioctl permission or scheduling execution.

Five new Rust tests use the independently Python-generated 12 fixed HOS2 vectors, covering all five operations; both success and failure replies; terminal/retired history; over-capacity snapshots; insufficient *success* capacity for a 64-byte error; malformed/truncated frames; pointer overflow; reserved descriptors; wrong request byte counts and mismatched IDs. The deliberate prefix-only known-bad consumer accepts an over-capacity buffer while the new bounded path rejects it. The pre-existing 12 compiled-source mutants are unchanged.

## Actual negative control and repair

The first CI candidate mistakenly constructed the 64-byte InstallBudget error fixture with 17 extra bytes: **81 bytes** of output capacity. The protocol requires **88 bytes**, even for an error. The production helper correctly returned `InsufficientCapacity`; one newly added test failed. This was **test construction**, not a codec defect.

- [First G0 host failure](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39000265264): four of the five new tests passed, `every_fixed_success_and_error_response_accepts_its_own_transport_bounds` failed as expected from 81 < 88.
- [First pinned-nightly failure](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39000265535): unified acceptance reported `success=false`; this failure is retained, not relabeled as a pass.
- Fix `08f65da4`: reserve `max(actual_frame_len+17, successful_response_frame_len)` and verify all unused copyout bytes are intact. No production parser relaxation.

## Verified code HEAD — successful GitHub Actions

The following two runs explicitly checked the **same** code HEAD `08f65da4cd784cb1c13a38a599642673c56d86bc`:

| Verification | Run and result |
| --- | --- |
| G0 scoped host contracts | [39000337575](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39000337575): **success**. All independent HOS2 generators/spec tests, host Rust ABI, strict fmt/Clippy, A03 Rust host control and A05 host QueryAbi/ENOTTY smoke completed successfully. |
| A02 pinned nightly | [39000337633](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39000337633): **success**, exactly **13/13** required acceptance checks; no omitted checks. Toolchain `nightly-2026-07-21`, `rustc 1.99.0-nightly (87e5904f5)`, bare `x86_64-unknown-none` no_std, fmt/strict Clippy, golden bytes, Rust tests, Python normal and `-O`, compiled-source mutations. |
| Pinned raw report artifact | [a02-fixed-nightly-host-acceptance](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39000337633/artifacts/12088493887). |

Rust codec suite: pre-existing **69** unit/integration tests plus **5** response-snapshot tests = **74**, and **1** doctest. The single fixed-toolchain acceptance also includes the existing **52** Python ABI tests in each of normal and `-O`, 12 original + 24 edge + 1 transport independent generator vectors and the existing **12/12** compiled-source mutants killed. The 17 expected mutant assertions are deliberate negative controls, **not** production test failures. No tests were deliberately skipped or filtered; the 13-check report is successful.

The caller's working container had no local Cargo/Rust compiler; verification uses actual GitHub Actions runners on the stated commits, not fabricated local Cargo output. The first failing runs remain in history; no known A02 code/test blocker remains after the verified repair.

## A03/A05 handoff and project boundary

Use the single `hos2_os_abi` crate and `Request`/`Response`/payload public types. After a successful complete input copy, use `Transport::decode_request_snapshot`. After a **successful** output copy, use `Transport::decode_response_snapshot_for` for the same descriptor/request, returning the exact HOSR frame length; existing `decode_response_prefix_for` remains suitable if its slice is already transport-bounded.

The public ioctl number remains an A00/A05 decision. Actual kernel copyin/copyout, CapSpace authority, A06 CPU scheduling/limiting and A07 original Hepta persistent owner recovery are **not** proved by this host ABI acceptance. No test result here establishes a production HOS2 syscall, user-space privilege enforcement, or native-kernel QEMU behavior. A00 retains merge/integration ownership.
