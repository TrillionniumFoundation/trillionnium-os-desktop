# A02 configured-cloud blocker closure — 2026-10-16

Configured project cloud node: `29609d47ba8e` (verified from the executing host).
A02 source parent: `00061b6bd0886e393e5ea4113ff999e15ed47bfd`.
Latest main incorporated as a merge parent:
`bc294f75bfb8c03d9963f5a12ea23b9589779d96`.
The A00 workflow/status/Hepta documentation changes are preserved byte-for-byte
from main; they are not independently edited by A02. Changes against main stay
within `libs/os-abi/**`, `tests/abi/**` and the existing predecessor A02 work.
Root README remains 0 bytes. No production codec, Wire ABI or dependency changes.

## Finite A02 blocker inventory

| A02 blocker | Reproduced problem | Closure evidence |
| --- | --- | --- |
| Fixed nightly strict Clippy | On exact 00061b6, test/fmt/no_std passed but Clippy exited 101 with chunks_exact_to_as_chunks | Four test fixture readers use as_chunks; final pinned Clippy exits 0 |
| Mutation toolchain selection in temporary crates | An absolute rustup-proxy Cargo path alone does not preserve a repository's selected toolchain | Explicit --toolchain/frozen env; actual Cargo/rustc identity is checked before every compile and test, all 15 baseline/mutant suites match |
| Single reproducible full host acceptance | Earlier evidence needed separately assembled commands and did not bind all temporary builds to one fixed compiler | run_acceptance.py snapshots actual inputs, resolves/hashes fixed tools, runs all 13 checks, verifies dynamic test names/counts and original input hashes |

All three identified A02 code/host-execution blockers are closed by actual runs
on this configured cloud node. No new production codec correctness defect was
found in this increment. The 1.95.0 evidence remains historical evidence for
that compiler; it did not establish compatibility with the newer fixed nightly.

## Fixed compiler and final execution

The default toolchain comes from the existing
`support/upstream-lock.json` kernel.toolchain: `nightly-2026-07-21`.
Actual resolved tools:

- rustc `1.99.0-nightly (87e5904f5 2026-07-20)`.
- Cargo `1.99.0-nightly (3efb1f477 2026-07-17)`.
- Clippy `0.1.99`; bare target `x86_64-unknown-none`.
- Installed cloud tool roots:
  `/workspace/scratch/ae1a8cf05419/toolchains/{cargo,rustup}`.

Actual command from the A02 checkout:

```sh
CARGO_HOME=/workspace/scratch/ae1a8cf05419/toolchains/cargo \
RUSTUP_HOME=/workspace/scratch/ae1a8cf05419/toolchains/rustup \
python3 -B tests/abi/run_acceptance.py \
  --rustup /workspace/scratch/ae1a8cf05419/toolchains/cargo/bin/rustup \
  --output-dir /tmp/a02-cloud-final-20261016-1
```

The output directory must be new. The entry point never installs a toolchain or
falls back to another compiler. It copies executable inputs and fixed fixtures
into an isolated snapshot; historical reports are excluded. README and upstream
lock copies are read-only. All recorded build/test commands execute inside that
snapshot, with exact RUSTC/RUSTDOC paths and RUSTUP_TOOLCHAIN. Compiler executable
hashes and versions are recorded. Source before/after hashes match.

| Final check | Actual result |
| --- | --- |
| Single entry point | **13/13**, success=true, no unexecuted checks |
| Rust codec tests | **69/69** unit/integration + **1/1** doctest, 0 failed/ignored/filtered |
| Python discovery and execution | **46/46**, both normal and -O, 0 failures/errors/skips |
| Independent Python canonical mutation oracle | **9/9** |
| Independent golden generators | **12/12 + 24/24 + 1/1** |
| rustfmt, strict all-target Clippy, bare-target no_std | All pass |
| Compiled-source mutation baselines | **8/8 + 12/12 + 7/7** |
| Compiled-source mutants | **12/12 killed**, all compile and run complete designated suites |
| Temporary toolchain identity | All 15 baseline/mutant suites match the reference before compile and before test |
| Source/fixture hashes; README | All match; **0 bytes** |

Python's 46 includes 6 new acceptance-runner tests and 7 mutation-toolchain
negative/control tests; these 13 are not added again to the denominator.
The latter cover fixed env propagation, missing compiler, timeout, identity drift
before compile or before test, honest default selection and an invalid reference.
Failure scenarios exercise the production runner's report and cannot earn a kill.
The acceptance tests reject missing/ignored/filtered cases, symlink input escapes,
evidence overwrite and unavailable tools. Their assertions also run under -O.

The 12 intentional mutants produce **17 expected assertion failures**, not
production failures. No compiler error, timeout, filtered or ignored test counts
as a mutation kill. The original nightly Clippy failure is retained as a before
control, and its corrected final command passes. A later checkout-cleanliness
check found an untracked Cargo.lock residue; it was removed and is not committed.
It is excluded from execution inputs; all recorded acceptance commands used the
snapshot and all executable source/fixture hashes still match.

## Committed evidence and long-term handoff

- `results/cloud-pinned-before-2026-10-16.json`: original pinned failure and logs.
- `results/cloud-pinned-acceptance-2026-10-16.json`: all final commands, outputs,
  dynamic denominators, resolved executable hashes and before/after input hashes.
- `results/cloud-pinned-mutations-2026-10-16.json`: compiler identity, all baselines,
  compile/test output and designated assertion failures for the 12 mutants.

The single acceptance entry uses existing golden generators and the existing
source mutation runner. It introduces no second protocol implementation or
control state machine. A03/A05 keep the same Rust interfaces, and all original
consumed values and fixed golden bytes remain unchanged.

A00 can invoke this existing entry from its owned CI workflow after provisioning
the fixed nightly with rustfmt, Clippy and the bare target, for example:

```sh
rustup toolchain install nightly-2026-07-21 --profile minimal \
  --component rustfmt --component clippy --target x86_64-unknown-none
python3 -B tests/abi/run_acceptance.py \
  --output-dir "$RUNNER_TEMP/a02-$GITHUB_SHA"
```

This is a concrete handoff, not a change to A00's workflow or repository settings.
The latest main already requires ABI fmt/Clippy and the transport fixture; the
single entry additionally binds compiled mutations and bare no_std acceptance.

## Project-level work still open

GitHub Actions run `38930013313`, job `117071289244`, remained queued with
conclusion=null at the read-only audit; [issue #33](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/33)
tracks dispatch. This is not recorded as a passed check, and repository security
or required checks were not weakened. Actual workflow dispatch is outside this
A02 code/host-execution closure.

Published ioctl numbering remains an A00/A05 shared decision. Real user copies,
CapSpace authority and CPU enforcement are A05/A06 work; original Hepta durable
owner effects/recovery are A07 work. Other architectures and 32-bit compat are
outside the documented first x86_64 little-endian N0 profile. These are not
marked closed by codec testing. HOS2 remains experimental major=2/minor=0.
