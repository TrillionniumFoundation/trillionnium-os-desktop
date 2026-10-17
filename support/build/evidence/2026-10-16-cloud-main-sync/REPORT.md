# Current main integration after cloud closure

While the preceding cloud evidence was being published, main advanced from
`3b2d15bc987e7ca78e64fa54edffb2177b8abde0` to
`bc294f75bfb8c03d9963f5a12ea23b9589779d96`: A02 PR72, A00 PR69 and PR79.
A01 adopted that approved main through published merge
`be86dc41228078b4b941b8a2e4d745fc09453d11`, tree
`2e18b73e5898af2e8b21fa746c9f32a2669b9ec1`, ordered parents
`d80cf2b1f7a9d4de1dc3375bf837bc4b5e7e3fd1` and the exact main above.
The merge imported18 files from main without A01-authored edits to their
owners' code. Kernel, build-support and upstream-lock subtrees did not change
in this merge. The root README remains0 bytes.

## Actual current-main host validation

[Host evidence](host/README.md) exports45 exact Git inputs from main, retains
their source archive and every command/environment/log/exit, and verifies
their unchanged bytes and executable bits after execution. Root additionally
checked every tested input's Git blob, full bytes, SHA256 and Git mode against
the actual merged branch: [merge input check](merged-input-verification.json).
That original receipt records the equivalent local merge commit before API
publication; its tree is identical to the published merge.

| Execution at fixed `nightly-2026-07-21` | Actual result |
| --- | --- |
| ABI all-targets tests | 61 passed |
| ABI doctest | 1 passed |
| Rust control model | 21 passed; zero doctests |
| Python ABI/spec/archive tests, ordinary and optimized isolated modes | (30+14+5)×2 =98 passed |
| Accepted host test executions | **181**, including repetitions across Python modes |
| ABI/control fmt | both exit0 |
| Control strict all-target Clippy | exit0 |
| ABI strict all-target Clippy | exit101; this invocation first reports `transport_preflight.rs:28` |
| Two explicit narrow ABI Clippy checks | both exit101, confirming `mutation_kill.rs:21` and `transport_vectors.rs:14` |
| Supported golden-generator commands and A05 host smoke | exit0; separate checks, not kernel execution |

Overall validation is **partial**, because strict fixed-nightly ABI Clippy is
not closed. All three helpers still use `chunks_exact(2)`. The first whole-crate
diagnostic is not evidence that the other helpers were fixed; the narrow
commands independently confirm them. No lint was suppressed and no owner
source was patched during validation.

The existing [A02 minimal candidate](../../handoffs/a02-nightly-clippy/README.md)
has all14 exact-base input bytes equal to the merged main inputs. Its unified
patch also passes a fresh `git apply --check` against the unmodified main
archive: [applicability receipt](candidate-applicability.json). The check did
not apply it. Its earlier isolated fmt/61-test/no_std/Clippy success remains
bound to that candidate; A00/A02 adoption on their integration revision is
still required.

The26 recorded command attempts have22 exit0 and4 nonzero outcomes. Besides
the three expected Clippy101 outcomes, an additional direct isolated-Python
call to the edge generator failed because `-I` removes its adjacent import
path. Its normal supported Python invocation then passed; the existing ABI
test also calls it normally. Both original and retry logs are retained. The
workflow does not require that extra isolated direct invocation. This failure
is not hidden or recast as a supported-command pass.

An initial metadata comparison incorrectly treated archived0664/0775
permissions as different from Git100644/100755. Its original false report is
preserved. A separate correction checks Git's executable-bit contract and all
original archive modes, bytes and Git blobs; no source change occurred. Root's
independent45-input comparison also passed. The original outer tool60513
completed0; aggregate command success is not inferred from that controller
status. The new private Cargo target is13,491,345 bytes, with debug info disabled
for these host tests and no shared kernel target reuse.

## Kernel acceptance and remaining work

This sync executes **no new kernel or QEMU test**. Its exact kernel subtree is
`6b3cab110aa6d30d5b89f99c4389c9c3e01022da`, identical to the already accepted
cloud debug source. The [preceding cloud report](../2026-10-16-blocker-closure/REPORT.md)
retains full-kernel Rust-entry debug/raw33, TCP OSDK22/22, failures, complete
serial and actual loaded boot/symbol artifacts, each with its own original
source revision. Those frozen185 files and their master manifest are unchanged.
The earlier actual empty-target normal build and kernel-crate regression are
also preserved at their original revisions; nothing here reassigns them to a
new clean build.

The upstream Asterinas commit and fixed kernel nightly remain unchanged.
Historical normal-ELF SHA `e884f5e5...` remains the separate A04 comparison
baseline. A05 process/ioctl and A06 scheduling interfaces are listed in the
preceding report and `support/build/README.md`; this merge does not implement
native HOS2 control, quota debit or Hepta's durable owner. Hardware/default-UNIX,
cross-path/host reproducibility, unknown writer, A04 compatibility and queued
CI limitations remain open. Main integration does not manufacture those results.

`SHA256SUMS` covers this sync packet; `host/SHA256SUMS` independently covers its
original host evidence. Exact-head CI status and the final PR readback are
recorded after publication, so queued checks remain distinct from local tests.
