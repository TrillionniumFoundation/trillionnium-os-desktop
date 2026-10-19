# Actual same-host cross-path kernel equality: passed

Two independent cold source builds at producer `4e8c7083575cec69efabe8d2250dfdd040c8dee8` booted the real derived Asterinas Rust kernel. The completed A4 and B4 guests both reached the small initramfs on one CPU and exited QEMU with raw 33. The **actual comparator then returned 0**, ran two additional live-artifact checks and proved full byte equality of the kernel ELF, initramfs and BIOS.

This accepts **two distinct real source roots on the same actual cloud host under the explicit schema4 path/component/metadata projection profile**. It does not accept cross-host reproducibility, an immutable environment, the unprofiled default build, or project G0/G1/G2. The separately preserved earlier A2/B2 boots still have their original failed cross-path comparison; this phase does not rewrite them.

| Completed case | Actual kernel source root | Outer session / exit | Cold `Compiling` lines | Actual QEMU duration / raw exit |
| --- | --- | --- | ---: | --- |
| A4 | `/tmp/trillionnium-a01-normalized-A4/kernel/asterinas` | 48522 / 0 | 279 | 1.275 s / 33 |
| B4 | `/tmp/trillionnium-a01-normalized-B4/kernel/asterinas` | 20786 / 0 | 279 | 1.279 s / 33 |

Both cases used absent target directories at prelaunch, exact eight successful original controller operations, clean source pre/post checks, three successful postrun profile/source/code custody checks and owned manifest removal. Their source `run_kernel` actions cold-compiled and booted with action/make exit 0; no additional standalone `make kernel` subprocess is invented. Fixed one-job policy was recorded in both policy JSON and each actual child environment. Each case has 369 compiler invocations and 738 ordered start/completion ledger entries; all 332 Cargo units succeeded. The separate 37 query probes include 34 exit-0 and three exit-1 records, preserved as probe results.

Complete producer tree: `d50cc2fd3fac4e8060ff26c324267b267767bca2`. Derived kernel tree: `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. Fixed upstream remains Asterinas v0.19.0 commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, upstream tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e`; fixed toolchain `nightly-2026-07-21`, rustc commit `87e5904f5eb6398af6b22eac2802c78934260c48`.

## Actual comparison execution

The completed launcher retained original argv, working directory, full stdout/stderr, exit status and exact comparator bytes. It ran from `2026-10-17T01:56:19.252535+00:00` to `2026-10-17T01:56:19.781979+00:00` and returned `0`. The original actual command was:

```sh
python3 -I /workspace/scratch/ae1a8cf05419/compare-normalized-cloud-v4.py 4e8c7083575cec69efabe8d2250dfdd040c8dee8
```

Comparator SHA256: `7c1da58aa5b1e3ee2484404349cee31f09e7bf3e5df39e563e72865dcc933a61`. Launcher SHA256: `08f0184771f79cf37f38f448ce441ebc4dd97a57e37945bd5079dfec493a054b`. `readable/normalized-cloud/controller-comparison-v4/command.json` and `output.log` retain the execution evidence. `readable/normalized-cloud/comparison-v4/result.json` is the complete 451,576-byte original result, including both canonical descriptor ledgers, actual paths and input hashes. Both fresh comparison live-check logs are retained in that same readable directory. Their exit-0 argv/returncodes also remain in the original result.

The independent static review is preserved in the raw archive with SHA256SUMS `bd407076082f9b7abf6d1c6400759b52823ab7682aa9e1eb6faa363977b630bf` and its readable receipt. That review did not run the comparator; the actual command above subsequently did. Source-bridge static review is an input-identity review only and implies no new candidate host-test rerun.

## Complete equal boot inputs

| Actual loaded input | Original bytes in each case | SHA256 in both cases |
| --- | ---: | --- |
| Kernel ELF | 8286952 | `8c540288c6af2a1a97121031643c1af4c4db395d7e8b4082d6edc4604449849a` |
| Initramfs | 1107990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| BIOS | 262144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

Comparison uses full reconstructed input bytes, not hash equality alone. Each per-case original QEMU artifact record binds those exact bytes, size and snapshot path. Both complete serial logs, QEMU requested/executed argv, executable version/hash, source/controller records, policy/results, all metadata query inputs/outputs and compiler incoming/effective argv plus producer ledger remain in the archive. The pinned OSDK's ELF64 `EM_386` Multiboot compatibility marker is retained and verified.

Synthetic embedded builder identity is explicit in both policies and serial metadata, separate from the actual cloud host/user. Both actual host records match. Successful producer provenance uses completion plus recorded device/inode/size/mtime; it is not an immutable-content claim. Runtime scope remains the explicit opt-in profile.

## Preservation and offline verification

The standalone package contains 128 original files, 120 deterministic raw archive members and three unique binary payloads shared over eight original logical paths. The kernel gzip is split into chunks no larger than 2 MiB. There are 86 exact producer source controls and 30 Git Merkle tree objects, including lockfiles, fixed source/toolchain controls and upstream license bytes. The original frozen A4/B4 phase checksum identities are recorded in `capture.json` and `report.json`; the comparison remains independently restorable without those sibling directories.

Packaging read the frozen A4/B4 evidence and only the terminated comparison/controller files plus static launcher/review inputs. It did not read ordinary N1 outputs or any original target/worktree, modify profiles, execute a build/guest, rerun the comparator/live checks, or remove original artifacts.

```sh
python3 -I support/build/evidence/2026-10-17-repro-cross-path/verify.py
python3 -I -O support/build/evidence/2026-10-17-repro-cross-path/verify.py
```

The offline verifier checks full checksum coverage, exact tar/gzip members and modes, source commit/tree/blob membership, both case inventories and controller logs, fixed compiler identity and one-job environment, strict compiler argument/ledger bindings, full guest serial acceptance and QEMU records, the actual comparison command/output/static-review identity, and complete kernel/initramfs/BIOS equality. It executes no captured scripts, Cargo, live checks or VM and requires no original source paths, target directories, Git executable or network.

```sh
python3 -I support/build/evidence/2026-10-17-repro-cross-path/verify.py --restore /absolute/new-directory
```

Optional restore creates fresh verified original/source files without executing them. It does not recreate historic inode identities, permissions or target outputs.
