# Latest integrated main host validation

Exact actual main **8f3bb49ab161104063a6ebea25428c40aa884ac0** was validated independently after A00 merged the newer A02 PR76 head and A03 PR50. This run does not reuse the earlier 606244 owner result. Source identity and all 80 selected Git blobs are retained in source-before.json; every original byte remains unchanged afterward.

The A03 entry records Git HEAD and a scoped diff, so the validator used a separate local sparse detached checkout sharing read-only Git objects with the project checkout. It contains only ABI/control sources and tests, golden fixtures, README and upstream lock; **no second kernel source copy**. Its HEAD is the exact main SHA, final Git status is clean, and control source-diff.patch is0 bytes. No owner branch/source or project working tree was changed by these tests. Compilation targets and outputs reside outside this checkout.

## Actual A02 entry

Tool session **36713 completed exit0** after sparse setup and the actual latest `tests/abi/run_acceptance.py` invocation. All **13/13 checks passed**, errors and unexecuted lists are empty. The new entry's separate compiled mutation batch budget is **900s**; individual commands retain their60s budget. These are the newer compiler-wrapper/batch fixes rather than the historical owner's entry.

- Python: **52 normal + 52 optimized**; separately selected canonical mutation oracle9 repeats a subset.
- Rust: **69 unit/integration + 1 doctest**, 0 failed/ignored/filtered.
- Golden generators: **12 + 24 + 1**.
- rustfmt, strict all-target Clippy, bare no_std target: exit0 each.
- Compiled mutation baselines and **12/12 killed mutants** pass the owner's complete-suite checks;17 intentional assertion failures are expected mutation evidence, not production test failures.

The actual pin is **nightly-2026-07-21**, rustc commit `87e5904f5eb6398af6b22eac2802c78934260c48`, with no toolchain override. The complete owner reports retain commands, stdout/stderr, executable hashes/versions, wrapper identity and dynamic denominators. Original runner input hashes remain unchanged; the actual execution snapshot and generated dependency-free lock are archived under abi/ without compiled target caches.

## Actual A03 control entry

Tool session **79554 completed exit0** for `/bin/sh tests/control/run-validation.sh`. The unmodified owner shell executes all six checks with set-e: fmt, std tests, std strict all-target Clippy, portable-spin tests, portable-spin strict all-target Clippy, and no_std x86_64-unknown-none library compile. All six returned0; each original log is retained under control/.

Both host backends report **113 passed**, 0 failed/ignored/filtered:6 unit,81 conformance,6 delivery adversarial,8 resource adversarial and12 kernel-handoff host cases; there are0 doctests in this crate. Cargo uses --locked, offline mode and two jobs. A new control target begins absent; std and spin subsequently share that target. Direct absolute Cargo/rustc/rustdoc paths match the fixed executables identified in the ABI report. The owner records source commit exactly8f and a zero-byte diff; source/fixture/lock bytes remain unchanged.

These are host codec/control models and a no_std compile. A test filename containing kernel_handoff does not establish kernel execution. No VM ran, and neither native HOS2 authority/enforcement, SMP nor IRQ-safe spin locking is accepted by this package. Real kernel evidence is maintained separately. A00/A01 still own merges and checks at their resulting revision.

## Evidence

exact-main-source.tar.gz retains all selected exact source files, modes and blob bindings, including historical owner reports. source-after.json verifies unchanged originals. abi/ and control/ preserve exact produced reports and logs; setup/ retains local sparse checkout commands' output. Actual controller argv/environment/exit receipts are included. Root README is0 bytes. Earlier 606244/BIOS/DATA evidence remains frozen and historical. SHA256SUMS covers every retained file except itself.
