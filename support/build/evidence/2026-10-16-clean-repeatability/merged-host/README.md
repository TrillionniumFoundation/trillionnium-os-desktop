# Merged-tree host validation

The exact committed merge `81d3080908292a0dc206f047de36b9e27bf68a73` passed the following actual host checks. Its tree `48d1c43cb77706870cd431a7cc4cecb0f73f3254` maps to published commit [`81bd3f21`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/81bd3f21804221dcc5de73f3e59b2f953282506a) with the same ordered parents; see [source binding](source-binding.json) and the publisher's [actual Git API receipt](publication-receipt.json), first entry in `publications`. This binding was added after execution; original runtime receipts retain the local tested commit.

| Actual check | Result |
| --- | --- |
| ABI Python (`-I -B`) | 19/19, exit 0 |
| Golden generator `--check` | 12 vectors, exit 0 |
| Rust ABI | 25/25, exit 0 |
| Rust os-control | 21/21, exit 0 |
| Archive CI tests (`-I -B`) | 20/20, exit 0 |
| Archive CI tests (`-I -O -B`) | 20/20, exit 0 |

These are **105 host test executions**, plus the golden-vector check. No tests failed or were ignored/filtered. The os-control suite is an independent host model, not an integrated ABI/kernel consumer. This evidence makes no kernel-build or VM claim.

[Report](report.json), [original summary](readable/overall.json), [full validation receipts](readable/validation.json) and [archive receipts](readable/archive-validation.json) describe the checks. [Environment](readable/environment.json) binds tool paths and executable hashes; full version output, command arguments, environment, actual exits and complete raw logs are retained in [raw.tar.gz](raw.tar.gz), indexed by [member names, sizes and SHA256](members.json). Paths inside original command records are historical execution paths; stable archive-relative locations are provided by that index and [readable index](readable-index.json).

The 34 selected inputs were extracted solely from the committed Git tree, matched to Git blob IDs and SHA256, and checked unchanged after all suites completed. The 95,033-byte original source snapshot is raw member `host/source.tar.gz`; [input hashes](readable/source-inputs.json) bind its contents. Rust used fixed `nightly-2026-07-21`, offline mode, two jobs and separate fresh Cargo targets. Both locks contain only their own package: [generated ABI lock](readable/locks/libs/os-abi/Cargo.lock), [unchanged control lock](readable/locks/libs/os-control/Cargo.lock), and [package details](readable/lock-packages.json). The source snapshot predates the generated ABI lock.

For replay, extract `raw.tar.gz` into a fresh owned scratch directory, extract `host/source.tar.gz` into another fresh directory, and use the commands in the retained `host/*.command.json` and `host/archive-validation.json` with the new source/target locations. The committed input crate paths, test selection and fixed toolchain remain as recorded. No compiler target or tool binary is included. The source/test CI pair was regular and non-symlinked, so its normal two-suite branch ran; absence/bootstrap/event-base branches were not exercised by this tree.

Packaging only read the frozen scratch records and wrote this evidence subdirectory. It ran no Cargo, VM, kernel build, install, Git mutation or production source change. The raw bundle was written to a temporary file, atomically installed, reopened and checked member by member. [SHA256SUMS](SHA256SUMS) covers every other evidence file.
