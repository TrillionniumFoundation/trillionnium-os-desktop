# Current source and kernel verification

This guide was checked against the product candidate
`d8b2bc6fb715af8ed27dfec09e3dfa8b94fa5bd2` on 2026-10-24. It describes
the source interfaces and commands in that checkout. The accompanying spec
repair changes Python guards and documentation; it does not change production
Rust, source-profile identities or recorded native execution results.

Use the [current module inventory](MODULES.md) for development and technical
entry points. [Current capabilities](../CURRENT_CAPABILITIES.md) distinguishes
implementation from source-specific execution. Dated evidence and the old
sections of [STATUS](../STATUS.md) retain their original identities.

## Fast checks with no kernel build

Run from the repository root with Python 3.11 or newer and the pinned upstream
Git objects available:

```sh
python3 -I -B -m unittest discover -s tests/spec -p 'test_*.py' -v
python3 -I -B -O -m unittest discover -s tests/spec -p 'test_*.py' -v
python3 -I -B support/build/verify-source.py
python3 -I -B tests/golden/generate_hos2.py --check
```

These commands check host-side specifications, the enumerated upstream and
downstream build inputs, and HOS2 golden bytes. They do not compile Rust or
execute a kernel. `verify-source.py` reports the pinned **upstream** identity
in its `commit` and `tree` fields; retain `git rev-parse HEAD` and
`git rev-parse 'HEAD^{tree}'` separately for the actual Desktop revision.

The 2026-10-24 baseline ran 44 spec tests and failed three source assertions:
one still required the former device-local boot-ID storage, and two required
particular Rust line wrapping. The repaired suite runs 53 tests in both normal
and optimized Python. The security checks still require all of the following:

- HOS2 delegates to the same boot-identity owner used by procfs; one locked
  Process image key supplies both the open descriptor and its full-width nonce.
- Every use checks the exact Process allocation and current image epoch/nonce.
- Ordinary builds advertise only QueryAbi; G1-c adds only ReadUsage; G1-d
  separately enables the five bounded HOS2 operations. Disabled operations
  retain `EOPNOTSUPP`, and feature/authority bits remain zero.
- The original Process owner receives the same image key after the session
  check. G2's private launcher requires its own feature and exact session.
- Trusted profiles remain outside ordinary defaults, including transitive
  feature aliases; G1-c cannot select management, and G1-d cannot select G2.

The small [lexical helper](../../tests/spec/rust_source_contract.py) ignores
comments and layout while retaining literals, token boundaries, cfg expressions
and statement order. Negative controls mutate those real source boundaries
and leave the former safe text in comments; the checks must still reject them.
This is a source guard, not a Rust parser, proof of all control-flow paths or
replacement for compiled behavior tests.

## Original behavior tests to retain

| Boundary | Existing executable test owner | Required execution scope |
| --- | --- | --- |
| Process allocation, shared opens, child identity, exec close/commit and epoch/nonce exhaustion | [original Process image tests](../../kernel/asterinas/kernel/core/src/process/process/image.rs) | Full original `aster-core` ktest suite; keep the named tests and all existing inventory gates |
| Stable boot UUID and read-only procfs behavior | [boot identity](../../kernel/asterinas/kernel/core/src/util/boot_identity.rs), [native boot-ID runbook](../../tests/kernel/control/NATIVE_AUTHORITY_BOOT_ID.md) | Full core suite, then the real ordinary-kernel two-boot procfs/HOS2 probe |
| Fork produces a new image identity; inherited and pre-exec descriptors cannot regain authority | [QueryAbi guest](../../tests/kernel/control/queryabi_guest.c) | Fresh ordinary build, boot and QueryAbi candidate runner |
| Trusted image bytes, restricted observation, original control dispatch and disabled profiles | [G1-c runner](../../tests/kernel/control/run_g1c_guest.py), [G1-d runner](../../tests/kernel/control/run_g1d_guest.py) | Each runner's exact image plus modified/truncated-image negative boots |
| CPU ownership, watchdog, physical reserve, page-table and IPC recovery | [complete native gates](../../support/build/ktest/README.md) and their named test inventories | Independent complete core, OSTD, allocator and MLSDisk runs; specialized user-progress/recovery probes remain separate |
| G2 Root/successor/launcher Process state | [G2 checker](../../support/build/ktest/check-g2.py) | Complete original core inventory plus all G2 additions; no userspace-owner qualification |

Use these existing behavior tests when changing the implementation. A harmless
rename or refactor should update the narrow source guard and retain the same
behavioral contract. A changed authority or failure path needs a real negative
case in its original owner or guest probe; a matching comment is insufficient.
This repair adds no duplicate kernel tests because the existing image, UUID
and guest tests already exercise the affected behavior. Their execution is a
separate gate on the final integrated source.

## Kernel profiles and minimal commands

The kernel toolchain remains `nightly-2026-07-21`, independently of the Linux
host UI's Rust 1.96.0. Prepare the disposable native Ubuntu 24.04 x86_64 build
host using [the build guide](../../support/build/README.md). Its `--apt` option
installs system packages and requires root; use the authorized build host.
No remote CI or another device is implied by these commands.

The ordinary kernel smoke and all four complete native suites are:

```sh
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -I -B support/build/ktest/prepare-locks.py
python3 -I -B support/build/ktest/run.py --output /absolute/new/ordinary-ktest
```

The strict runner defaults to `ostd`, `aster-core`, `osdk-frame-allocator` and
`aster-mlsdisk`. Each uses its own original derived lock and real QEMU guest.
It fixes q35/TCG, CPU `max`, one vCPU, 512 MiB, packaged SeaBIOS and serial
output. Keep the complete serial bytes, actual QEMU arguments, raw exit 33,
zero failures, zero filters and explicit soft-skip record. TCG VMX/EPT soft
skips do not establish those hardware paths. A focused `--test-name` run is a
diagnostic and does not replace the complete inventory.

The following guest profiles require a **clean committed checkout**, its full
expected commit/tree, and fresh output outside that checkout. Replace each
uppercase identity placeholder with the reviewed value; do not use an old
receipt to qualify a new tree. Each command builds and runs its profile, so
run them sequentially on the authorized build host:

```sh
python3 -I -B tests/kernel/control/run_queryabi_candidate_guest.py \
  --expected-source-head REVIEWED_DESKTOP_COMMIT \
  --expected-source-tree REVIEWED_DESKTOP_TREE \
  --target-dir /absolute/cache/ordinary \
  --output /absolute/new/queryabi

python3 -I -B tests/kernel/control/run_g1c_guest.py \
  --expected-source-head REVIEWED_DESKTOP_COMMIT \
  --expected-source-tree REVIEWED_DESKTOP_TREE \
  --target-dir /absolute/cache/g1c \
  --output /absolute/new/g1c

python3 -I -B tests/kernel/control/run_g1d_guest.py \
  --expected-source-head REVIEWED_DESKTOP_COMMIT \
  --expected-source-tree REVIEWED_DESKTOP_TREE \
  --target-dir /absolute/cache/g1d \
  --output /absolute/new/g1d
```

| Profile | Enabled source interface | Qualification limit |
| --- | --- | --- |
| Ordinary | QueryAbi, request bound 0, response bound 48 | No native grants or resource effects |
| `g1c-trusted-observe` | QueryAbi + ReadUsage, request bound 0, response bound 64 | Trusted initial-image observation only |
| `g1d-trusted-control` | All five HOS2 opcodes, request bound 40, response bound 64; includes G1-c and original physical-reserve prerequisite | Original Process/CPU/in-memory history slice; Hepta disk durability and production isolation remain separate |
| `g2-trusted-daemon` ktest | Includes G1-d and private launcher; full Process-state tests | The embedded ELF is compilation input only; tests do not execute an original Hepta owner |

For the G2 Process gate, supply the actual canonical static x86_64 ELF and its
SHA-256. The runner freezes at most 8 MiB of exact input bytes:

```sh
HEPTA_TRUSTED_INITIAL_ELF=/absolute/pinned/compile-input.elf \
python3 -I -B support/build/ktest/run.py --g2-initial-root \
  --crate aster-core --trusted-initial-sha256 REVIEWED_ELF_SHA256 \
  --output /absolute/new/g2-process-ktest
```

The current checker retains the ordinary minimum of 373 core tests with at
least 134 required names, plus three Root and eleven successor/launcher tests
(minimum 387). It explicitly reports `actual_native_owner_verified: false`
and `g2_complete: false`. These are current checker thresholds, not execution
results from this documentation change. Future inventory updates must retain
the named original tests and record their own full run.

Build OSDK from the same exact checkout path used for the kernel. Its binary
embeds local paths. `--skip-osdk-install` is valid only with that already built
and recorded tool; a matching version from another worktree is insufficient.

## Independent Hepta native runtime line

The product UI/source pair pins Hepta `22e87e0dd6560a7b925e716a33011378ae07a9a2`.
The separate [F1 runtime source review](../../tests/workloads/hepta_agentd_runtime/source-review.json)
currently selects Desktop `0187bd578f6786c40c812c13976e4889a1aba835` and
Hepta `b3d3f2d4b01f123d7ac17575c27fb54d00094f7f` with userspace Rust 1.95.0.
Those are different reviewed profiles. The [F1 runbook](../../tests/workloads/hepta_agentd_runtime/README.md)
requires its original `build_kernel.py --execute`, input preparation and
`run_agentd_runtime.py --execute` stages on those exact clean sources.

To qualify the new product pair natively, first review and freeze the changed
Desktop/Hepta sources and the new toolchain, then build and execute that new
profile. Editing only the review hashes cannot transfer earlier no-turn Agentd
or CognitiveStore receipts. Full model turns, authenticated original owner,
durable CPU control/recovery, and native display/input are additional gates.

## What still needs execution or physical devices

This foundation repair verifies host specifications and documentation only.
Final integrated kernel compilation, all four ordinary suites, the three guest
profiles and the separate G2 Process suite need actual output on the designated
build host. Even successful QEMU N0 results leave these independent conditions:

- Full native original Hepta runtime, owner authority and durable recovery on
  the same Desktop/Hepta source pair and actual binaries.
- Native Asterinas display/input, per-device GPU, storage flush and power-loss
  behavior, SMP and recovery admission; each needs its own target matrix.
- Linux host native windows, input methods and accessibility on the built UI
  profile; headless layout and package tests have narrower scopes.
- Android signed receiver/install/lifecycle and real device permissions;
  an Android application result does not qualify a mobile OS or another BSP.

Record missing prerequisites as blockers for their own profiles. Source tests,
command-help checks and historical receipts cannot close them.
