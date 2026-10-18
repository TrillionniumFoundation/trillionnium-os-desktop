# A01 owner / CI refresh — 2026-10-17

This packet contains read-only GitHub GET evidence and the explicitly requested host validation of exact current main. It changes no owner implementation, kernel source, PR, issue or comment. It starts no VM.

The snapshot has a bounded collection window, recorded in `report.json` and each `api/*.receipt.json`. Branches can advance after this snapshot. Initial A01 head was `e932e49191db61bb4b95d4dbbb891e4793908219`; the closing observed head is `84f49159b066faa87a135c0662f9eba5be971e10`. Main is `40ca002fac0726b366726d3353916637b29adeae`.

## Findings and evidence boundaries

| Owner / check | A01 verified from this collection | Owner-reported / remaining boundary |
| --- | --- | --- |
| A05 [PR87](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/87) | Open Draft; head `25cbffe6080bdf397f4911f85111cc966ac951d3`. Handler blob `b9b2571b99637744c6d5927ca56971c9f3b92989` advertises only QueryAbi. It has no genuine effect authority or trusted CapSpace. Decode failures still map to EINVAL; disabled operations to ENOTTY. | Historical actual QueryAbi guest receipt binds earlier kernel source `5fc3887d...` and ELF `54c8a7a7...`. The owner has since merged stricter guest reply tests; that does not rebuild the kernel or qualify A00's separate pending errno correction #88. This refresh did not reexecute the guest. |
| A06 [PR18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18), [issue63](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/63) | Open Draft; head `57b23ede7e242711ef142b672f04c896383a264a`. `cpu.rs` remains exact issue-cited blob `45d93fe11506e6f6813142de1012352b958a5897`; `charge_task_cpu` returns when the Process weak reference is dead. Issue remains open with zero comments. | This is the unresolved final-runtime accounting concern. No new quota-bypass QEMU exploit has been demonstrated by this packet. Earlier owner ktests / quota guests retain their original limits. |
| A04 [PR8](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/8) | Open Draft; head `da4107f8bf525b773c8b40899f443c292c3e6dbd`. Owner result JSON and rootfs manifest blobs were independently fetched and Git-hash verified. Current main SCM_RIGHTS receive inserts with `FdFlags::empty()` and retains CLOEXEC TODO; open / FileTable insert has no NOFILE limit check in this inspected path. | Owner reports 11/13 guest cases pass. Focused failures: MSG_CMSG_CLOEXEC leaves the received FD flag clear; soft NOFILE=32 still allows 256 opens. These refine the older timeouts; A01 did not rerun them here. Owner also reports four reconstructed ELF hashes differ from the manifest: exact original bytes remain required. The PR prose has a mistyped Asterinas commit; this packet does not adopt that prose as the pin. |
| A07 | No `agents/A07*` branch among the 71 returned branches; exact A07-title and A07-head PR queries each return zero. Exact main root tree has no `services`; tests tree has no `integration`. Related merged PR11 is organ-backend diagnostics / docs. | A04's fixed-Hepta provider audit reports zero concrete invocation-provider implementations / attachments and no terminal receipt in its previous failed e2e. This is retained as owner-reported evidence. No external authenticated Hepta owner was executed or independently inspected by this packet; absence in this repository is not proof about other repositories. |

## Current main host validation

Exact detached worktree: `/tmp/trillionnium-a01-main40ca002`.

- Commit: `40ca002fac0726b366726d3353916637b29adeae`
- Tree: `3d15019940246eb9a8cef85931dd92dec3c309bf`
- Fixed toolchain: nightly-2026-07-21; rustc 1.99.0-nightly `87e5904f5eb6398af6b22eac2802c78934260c48`
- Actual command: `sh tests/control/run-validation.sh <absolute main-control-current/script-logs>`
- Jobs=2; independent target `/tmp/trillionnium-a01-main40ca002-control-target`.
- std **129/129**, portable-spin **129/129**: each mode 6 + 81 + 6 + 8 + 6 + 12 + 10; zero doctests, failures, ignored or filtered tests.
- fmt, std strict Clippy, spin strict Clippy, x86_64-unknown-none no_std check: all exit 0.
- Overall script exit 0; source bytes before/after identical; worktree clean; root README 0 bytes.

The exact invocation, relevant environment with unset values represented as null, source Git blobs and SHA256, full console and each script log are in `main-control-current/`. `sources.tar.gz` retains the full bound Rust/Cargo/validation source bytes. `run-main-control.py` is the actual controller used. This is **258 host Rust model executions**, zero kernel builds, zero VM runs, zero Hepta effects. Older main's count is not extrapolated.

The independent remote compare of main `8f3bb49...` to `40ca002...` has 12 commits / 28 paths: g0 workflow, status, control library and control tests / evidence. No kernel, support/build or wire ABI source paths changed. The control source and Cargo config did change, so newer main is not called the old full tree.

## GitHub Actions source binding

- Closing observed A01 head `84f49159...`: run [38989892349](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38989892349), job `117269712771`, **queued**, conclusion null.
- Current observed synthetic PR22 merge `3074a5bd5f505da67a114093fd0964bcac4dfbb0` has actual API parents `40ca002...` + `84f49159...`. No execution of that merge is inferred.
- Earlier actual green run [38987804080](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38987804080), job `117263227470`, binds head `1e81ef45250dc16e903b05d0386e4f95f332aee9`.
- Its decoded checkout log records actual checkout `154d4a62b18e3126a9dacd9e62df94f8e0536045`; immutable Git commit API verifies parents `82ef86a9...` + `1e81ef45...`.
- That job actually reports 27 + 27 boot-evidence, 30 + 30 kernel-runner, 28 + 28 archive tests = **170 host fixture executions**. It is not the older 146 count and does not qualify current queued source.
- GitHub run `pull_requests[].head` may reflect the PR's later head; this packet uses job checkout logs + immutable merge parents for the historical checkout.

CI is host-only. It does not qualify QEMU, default AF_UNIX, KVM/VMX, G1 or G2. Original decoded logs, run/job/check metadata and merge commits are retained.

## Authorized host entry review

`host-entry-review/` preserves an independent read-only scan, scripts, actual stdout/stderr, references and its own checksum file. In the inspected repo docs/config, no already-authorized available KVM or second dedicated host endpoint was found. Six jobs use ubuntu-24.04; no self-hosted label was found. The lab profile is candidate/unverified with physical host fields null. Repro documentation explicitly disallows treating embedded host identity as second-host evidence.

No credential search, login, cloud resource creation, runtime socket/KVM reprobe or host change occurred. This limited repo review does not establish whether resources exist elsewhere. Previously established AF_UNIX EPERM / no-KVM facts retain their earlier runtime evidence; they were not rerun here.

## Storage, replay and limits

- `api/*.json`: original connector-returned JSON bodies, with an ending line terminator added by patch transport; each receipt records URL and start/end time. Blob/contents endpoints are auto-unwrapped by the connector, and are labeled accordingly.
- `blobs/*.capture.json`: exact returned UTF-8 source strings plus requested immutable Git blob. `verify-blobs.py` reconstructs the byte-identical `.source` files and verifies **18/18 full Git blob hashes**, then records SHA256 and sizes.
- `capture-adaptation.json` records the initial text-vs-JSON handling adaptation and incorrect openat path lookup; no owner source was changed.
- `analyze-refresh.py` is the actual offline assertions/report controller. It consumes only saved responses and logs; all its claims remain bounded by the collection window.
- `report.json` contains machine-readable findings, exact source excerpts/lines, test groups, API receipt paths/times, source identities and limitations.
- `SHA256SUMS` covers every frozen ordinary file except itself. No old evidence is rewritten.

Do not promote source inspection, owner-reported historical runs, host fixture tests or queued jobs into current kernel / G1 / G2 acceptance.

