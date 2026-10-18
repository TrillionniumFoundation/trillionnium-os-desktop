# A01 project-cloud build closure — 2026-10-17

The fixed full Asterinas derivative now has an actual ordinary cold build and
boot, two independently cold distinct-root projected builds with identical
complete inputs, source-root-bound kernel tests and one final complete OSDK
matrix. The remaining host and owner blockers are **not** declared closed.

PR: [#22](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22),
branch `agents/A01-asterinas-boot`, base main
`40ca002fac0726b366726d3353916637b29adeae` (merged into A01 through
`5fffe3394dd562ad88fda7c37edc258cf9b56387`). A00 owns integration into main.
This report names the actual test producer commits; later evidence and
metadata commits are related by the exact consumed-input Git bridge.

| Actual execution | Producer | Result |
| --- | --- | --- |
| Ordinary cold `make kernel`, then same-target `make run_kernel` | `d879a9d2ffae8d0eb0df441370da54f9e3a38431` | Eleven controller steps exit0; 279 cold compilation lines, no new compilation at boot; full kernel/initramfs, raw QEMU33, new live check0; post118 source inputs/clean Git |
| A4 and B4 cold full kernels, distinct actual roots | `4e8c7083575cec69efabe8d2250dfdd040c8dee8` | Both raw33; actual complete ELF, initramfs and BIOS bytes equal; explicit schema4, Cargo jobs1 |
| Correct-root OSTD and aster-core guests | `d895dd73a07788f6fc825fb3ca29cca22d93bb07` | 221+141 reported passes; zero failures; three VMX/EPT soft skips; 359 exercised lower bound; two raw33 |
| One complete final TCP/GDB OSDK matrix | `d879a9d2ffae8d0eb0df441370da54f9e3a38431` | 22/22, zero failed/blocked, eleven raw33 guests, one VMX soft skip; compilation cache reuse |
| Final matrix actual input retention | Same final matrix | 23 private input mappings, 13 unique payloads, all retained losslessly; kernel/BIOS and original EM62 coverage symbol |
| Real GDB coverage export and LLVM merge/show | Same final matrix | 2,096,896 raw bytes, 5,692 functions with counts, all commands0 |

The ordinary complete ELF is **8,258,112 bytes**, SHA256
`c49ad7da1c76c1f559d065ac3f8cbcbad407242dda54f1ed00028f02d5c2413d`.
Its first produced frozen bytes equal the actual later boot snapshot. Serial
is 72,247 bytes, SHA256
`3840526255cff7c53567f3e35e42739a11dba24f3feb03594719e92bec0ab5ca`.
The projected pair ELF is **8,286,952 bytes**, SHA256
`8c540288c6af2a1a97121031643c1af4c4db395d7e8b4082d6edc4604449849a`.
These are separate profiles; their hashes need not equal each other.

The fixed upstream is Asterinas **v0.19.0**,
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`. The sole committed kernel root is
`kernel/asterinas/`, current derived tree
`6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. Rust remains
`nightly-2026-07-21`, rustc commit
`87e5904f5eb6398af6b22eac2802c78934260c48`. Original Cargo locks, upstream
README/documentation, attribution and MPL license remain. This is the full
kernel, not a newly written OSTD-only kernel. The project root README is 0 bytes.

## Replay in this restored cloud

Use a clean worktree of this branch; the source bridge binds its tested inputs.
For an exact earlier producer checkout, source this environment file by its
absolute path in the final checkout. The small initramfs
and upstream developer targets require no full installer ISO, Docker or Nix.
The environment file records the N1 cloud's real private tool paths. It is
specific to this restored host; use the private-toolchain phase to reproduce
its installation on another authorized host.

```sh
. support/build/evidence/2026-10-17-cloud-closure/cloud-replay-env.sh
bash support/build/kernel.sh kernel
bash support/build/kernel.sh run_kernel
python3 -I support/build/ktest/run.py
python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb --output NEW_MATRIX_DIRECTORY
```

`kernel.sh` invokes upstream `make kernel` and `make run_kernel` through
`minimal.mk`. The guest is x86_64, q35/TCG, CPU max, 1 vCPU, 512 MiB, explicit
SeaBIOS, fixed devices, serial capture and isa-debug-exit. The exact expanded
QEMU command, compiler/build logs, environment and full serial bytes are in
[ordinary evidence](../2026-10-17-native-cloud-normal/README.md).
Always create a new output directory. Reinstall the OSDK after changing the
absolute source root: `OSDK_LOCAL_DEV` embeds that root at SDK compile time.
The test and integration outputs have their own locked generated workspaces.

The [private toolchain phase](../2026-10-17-private-toolchain/REPORT.md)
records 57 signed Ubuntu packages, the fixed nightly, actual acquisition and
installation checks and the failed system APT attempt. No `_apt` sandbox,
capability or namespace bypass was used. The freshly fetched nightly manifest
body was not retained; its observed SHA and rustup component verification are
recorded separately. The proof does not claim a complete immutable builder.

For the explicit projected profile, follow
[repro/README](../../repro/README.md). Only source/compiler/producer-bound
metadata and recorded path remaps change; the strict producer gate remains.
The actual [A4/B4 comparison](../2026-10-17-repro-cross-path/README.md)
proves same-host, different-real-root bytes. It is not a cross-host claim or a
statement that the ordinary profile is bit-reproducible.

## Preserved failures and provenance

The [before phase](../2026-10-17-native-cloud-before/README.md) retains the
wrong-root SDK attempt, initial 20/22 matrix, offline missing-crate failures,
exact official-checksum dependency completion and real coverage recovery.
Correct-root ktest's inner runner exited0. Its enclosing tool session36657
later exited1 because the subsequent initial matrix failed; that tool result
is not relabeled as0. The final 22/22 is a separate complete execution.
The initial case14 original kernel bytes were overwritten and are unavailable;
its original SHA/serial remain, and no replacement is reconstructed. The old
wrong-root SDK's original binary was also not frozen. These limits do not
apply to the final matrix's complete private-input archive.

The original component-path panic, A2/B2 unequal ELF result and A3 strict
producer-order failure remain in their own phases. The final recorder freezes
all selected inputs before the QEMU version probe, and the final workspace
runner isolates generated OSDK directories per case. Historical host fake-QEMU
tests are labeled host-only; they are not counted as actual guest boots.
The metadata spelling correction in the unpublished native packages, its
original hashes and the independent auditor's historical partial-manifest
scope correction are retained in this closure's raw receipts. Actual raw
runtime records and payload bytes were not rewritten. See `errata.json` for
one older B2 prose-command typo; its frozen package is unchanged.

`phase-index.json` binds every current 2026-10-17 phase root manifest. Individual
phase checks retain their own exact producer, source tree, commands, failures
and reconstruction rules. Nested historical checksum receipts are ordinary
covered evidence files, not automatically executed subpackages. The aggregate
checker verifies offline inventory/hashes/pins only; it does not execute
archived checks or rerun a build or VM:

```sh
python3 -I support/build/evidence/2026-10-17-cloud-closure/verify.py --repo-root "$PWD"
python3 -I -O support/build/evidence/2026-10-17-cloud-closure/verify.py --repo-root "$PWD"
```

The [handoff](HANDOFF.md) gives A00/A05/A06 exact integration interfaces.
`blockers.json` separates closed A01 build issues from open host, compatibility
and native-control owner work. The final source bridge compares Git bytes,
modes and trees for the listed consumed inputs. ABI/control historical host
checks passed at their stated sources; identical inputs do not mean they were
rerun here and do not establish G1/G2 or CPU enforcement.

Default host AF_UNIX still returns EPERM. KVM/VMX/EPT are unavailable. There is
no validated second-host build or complete immutable environment, and the
workspace writer remains unidentified. A05/A06 owner Drafts and A07's real
persistent-owner chain require further implementation and guest tests; A04's
recorded Linux gaps remain. Final-head CI is read back after publication and
reported on PR22; queued or missing statuses are never called green. A00 owns
main integration and the shared project docs/CI. No A05/A06 core, NATIVE_ABI,
production service, system disk, BIOS or GPU driver was changed by this round.
