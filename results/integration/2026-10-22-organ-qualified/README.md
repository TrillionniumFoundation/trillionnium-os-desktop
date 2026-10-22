# Qualified desktop / original-owner source combination — 2026-10-22

This packet retains the actual combined-source executions and the ordinary
merge of [PR #240](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/240).
It does not turn the limited kernel profiles, a test issuer, or an ABI preflight
into a production release. The next implementation gates are in
[ORGAN_IMPLEMENTATION_NEXT](../../../docs/agents/ORGAN_IMPLEMENTATION_NEXT.md).

## Exact identities

| Role | Commit / tree |
| --- | --- |
| Executed OS source | `85d394f99c73ad3194d57c876712ac01b59d90ca` / `7389c0a3f982983087953f75de7042fc058be088` |
| Executed and published Hepta source | `6d6097da843f5831dfaf9cee3530da512d072a15` / `f722fbe5f24275c324089be720559a40901105f3` |
| Original-owner Notes parent | `eefc858f4c15149f017a60642cf36b58d82d5529` / `f099c88ccfd3fce89bd0bf04787a69c0861a4487` |
| OS #240 ordinary merge | `f85ccae8445f8d753572d41411d98ee28d253af5` / `bad0a3ee66859cfcf7bf1185e4f10d0f953239ad` |
| Actual merge parents | main `7d9966b83ef1210e0c4307f2fd348809debde349`, then tested head `85d394f99c73ad3194d57c876712ac01b59d90ca` |

The two executed commits are the runtime qualification pair. The merge and this
later evidence commit have their own identities. The actual merge delta contains
21 historical evidence paths and one ExFAT host test file, with no additional
runtime-source change. The final ExFAT test file was separately run normally and
under `python -O`: 15/15 in each invocation. `merge-verification.json` records
the exact 22-path comparison and its verified blob identities.

## Actual results

| Gate | Actual result and scope |
| --- | --- |
| Combined UI | Complete `tests/ui/check-host.sh`, UI all-targets 181 passed / 0 failed / 2 existing ignored, all-targets Clippy `-D warnings`, and complete owned Weston gate passed. Counts from repeated host invocations are not added together as unique tests. |
| Complete aster-core | 269 declared / 269 passed / 0 filtered / 0 soft skips; required subset 31. The separate SMP permission profile declares 272 and selects its three actual concurrency cases; it is not 272 additional executed tests. |
| Ordinary kernel | Real boot, QueryAbi and disabled-operation refusal passed. Local ordinary ELF SHA256 `8170402aaa7408eb2c4ab1ade2cd1d9641ef03ccbd37631aaec775528df2ede7`. |
| SQLite | WAL/FULL on a fresh ext2 `filetype` image: committed sudden-QEMU-kill/reopen and omitted-COMMIT negative control passed across four boots. No physical power-loss, volatile-device-cache-loss or original-Hepta-store claim. |
| G1-d | Exact-image, byte-mismatch and truncated-image boots passed. UID/GID 60001, empty capabilities, no-new-privileges, securebits and inherited 256 MiB address-space limit were observed on the real workload. Finite independent recovery and legal zero-cap pause preservation passed. `hepta_durability=false` and `production_ready=false` remain. |
| Original Agentd package | Exact Hepta `6d6097d`: 238 tests run, 238 passed, 7 skipped. The separate real GUI invocation ran one otherwise ignored test successfully; its other 244 discovered tests were filtered. The remaining skipped tests are not claimed as passes. |
| Original owner / actual Notes | Original writer and test issuer drove the actual Session/Notes application, read back revision 0→1, and recorded the original committed terminal. The receipt binds the actual application and Session binaries. Production authority, native kernel and physical pixels remain unqualified. |
| Source profile | Real build and verify on the two clean checkouts passed; the separate tool suite has 19 passing temporary-Git/DAG regressions. Source verification is not runtime or authority verification. |
| Original Agentd ordinary ABI | The exact frozen original ELF dynamically loaded in Asterinas, entered Rust main, and produced the expected missing-fleet configuration refusal: child exit 1, QEMU exit 33. No daemon, original owner or async runtime was started by this gate. |

The final Agentd source stayed unchanged after the package test, explicit GUI
test, scoped `just fix` and `just fmt`; the final build then succeeded.
[Hepta #3072](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3072)
contains the original-owner Notes assembly, and
[#3115](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3115)
adds bounded ReadUsage through the existing `AgentdHos2Device`. Neither PR
introduces a second history owner or outbox.

The frozen dev Agentd is 484,463,504 bytes, SHA256
`228d2e07583d0d27cf5750a6ba169254380fb4d49f1fdc21adcc04001fc3252f`.
It is a dynamically linked PIE, not the small static trusted G1-d image. File
size and PT_LOAD memory are different measures; neither is peak RSS. This dev
artifact does not establish the size or feasibility of a future release build.

## Source-only release profile

The committed [manifest](../../../support/release/profiles/2026-10-22-organ-source.json)
has SHA256 `260139110c06921db6a156c1f072c55d0a3218f4b8da523b509adad4471e5667`.
[Build](source-build-receipt.json) and [verify](source-verify-receipt.json)
receipts bind the executed OS head/tree, one Hepta head/tree, original-history
ancestry, 12 OS roles, 9 Hepta roles and two exact-byte golden pairs.

Production activation is explicitly disabled. Seven deployment inputs remain
unconfigured: original grant provider, protected clock, external frontier,
issuer keyring, revocation feed, authenticated current-cut and recovered writer.
The profile has no command-line switch that enables them. A later source commit
must be verified with its own explicit head/tree; it cannot borrow the runtime
identity above. See the [profile manual](../../../docs/agents/ORGAN_RELEASE_PROFILE.md).

## Retained evidence and independent checks

- `combined-execution.tar.xz` contains 109 selected raw reports, serials, logs,
  source snapshots and invocations from the combined UI/kernel and ABI runs.
  [manifest.json](manifest.json) records every uncompressed member's size and
  SHA256. The archive is 695,376 bytes, SHA256
  `61eff30a413ff3a02d31f2c62c380de8bca7a36be5a12997921fd946c92e3e99`.
  Every member was reopened and checked before transport, then independently
  checked again after transport.
- [hepta-original-owner-qualification.json](hepta-original-owner-qualification.json)
  preserves the exact source identity, unchanged-after-tests check and actual
  original-owner GUI receipt. The separate
  [execution summary](hepta-original-owner-execution-summary.json) records the
  seven actual commands and exit codes, 238/7 package result, explicit GUI 1/244
  result, and the sizes and SHA256 identities of the original logs. Those full
  private-package logs remain at the recorded producer path; they are not
  members of the 109-file public archive. Private source files and provider
  secrets are not part of this public packet.
- [github/metadata.json](github/metadata.json) retains all seven successful
  workflow results, the A06/G1-d step results, empty review-thread list,
  actual main branch identity and merge parents/tree. Complete decoded A06 job
  `119621892212` and G1-d job `119621892292` logs are retained losslessly as gzip;
  [their manifest](github/log-manifest.json) records both raw and compressed
  identities. The workflow artifacts' upload digests in those logs are producer
  claims; their ZIPs were not independently downloaded in this packet.
- The [separate ABI packet](../2026-10-22-agentd-ordinary-abi/README.md) retains the
  complete 7,287,706-byte serial and an independent replay using the exact
  executed oracle. The new host workflow tests the harness only; it does not
  silently run the private binary or grant native qualification.

The seven successful #240 workflows were G0, A01, A06, A07 ARM64, G1-c, G1-d
and A10. A07 still pins historical Hepta `f8c9419`; its success is not evidence
for the new Hepta source pair. CI and local kernel binaries have distinct build
receipts and hashes even where the source tree matches.

## Known issues retained by this qualification

The Agentd ABI guest's read-only ext2 payload produced one failed Write BIO and
two page-writeback I/O diagnostics during shutdown, after the exact child
result. The host read-only backend rejected the write and the payload remained
unchanged. Buffered read, direct read and readdir can dirty automatic atime on
the current read-only filesystem; VFS mutation checks, remount flushing and
virtio RO negotiation need their own review. Do not hide this by skipping all
sync on RO or by making this test's payload writable. The serial also records
25 unsupported `rseq` calls; startup's fallback worked, but rseq is not thereby
implemented. These findings do not invalidate the narrow loader/config oracle
and do not qualify correct read-only storage semantics.

Remaining product gates are the production original-owner assembly, native
post-exec role bootstrap and G2 durable reconciliation, autonomous/public
recovery and total process-tree memory control, native original Agentd/UI, and
fixed physical GPU/VMM/ARM/phone execution. The source-only profile and this
evidence packet keep all of those boundaries explicit.
