# Actual A02 owner head: fixed-nightly validation

Status: **owner_head_validated_pending_main_integration**. Exact owner head `606244b6109b1060b4916baa76e3fdd14dcc5240`, tree `6df770187bd48482c84b1cd22acab25b4ee90648`, was read-only exported from Git into an independent scratch directory. All 47 exported Git blobs were checked before execution and remain unchanged afterward. No owner working tree or branch was edited.

The actual owner entry `tests/abi/run_acceptance.py` ran with its default toolchain pin from the exported `support/upstream-lock.json`: **nightly-2026-07-21**, rustc commit `87e5904f5eb6398af6b22eac2802c78934260c48`. No --toolchain override was supplied. Its resolved absolute compiler/Cargo/rustdoc/rustfmt/Clippy identities and executable hashes are in `acceptance-report.json`. Cargo used two jobs and offline execution. Actual outer tool session **35161 completed exit0**; the controller exit is also0.

All **13/13 checks passed**, with no errors or unexecuted checks:

- Rust: **69 unit/integration + 1 doctest**, 0 failed/ignored/filtered.
- Python: **46 normal + 46 optimized**; separately selected canonical mutation oracle **9**. The latter repeats a subset and is not counted as another nine unique tests.
- Independent golden vectors: **12 + 24 + 1**.
- rustfmt, all-target Clippy with -D warnings, and no_std x86_64-unknown-none target check: exit0 each.
- Compiled mutation baselines: **8 + 12 + 7**; **12/12 mutants killed**, with 17 expected assertion failures. Compiler errors, timeouts and incomplete/filtered suites do not count as kills.
- All **15 baseline/mutant suites** match the reference toolchain before compilation and again before test execution.

The complete Rust discovery total is70 because it includes the doctest. Root README remains0 bytes. These are actual fixed-nightly host/codec tests, independent of stable-CI results. They do not establish native ioctl authority, HOS2 driver execution, scheduling enforcement, or main integration.

`controller.json` records the original command/environment/exit. `console.log`, `acceptance-report.json` and `mutations.json` are retained exactly as produced; individual command stdout/stderr, identities and complete denominators are embedded in the owner's reports. `owner-source.tar.gz` and `source-before.json` bind the exact Git export, including historical owner reports. `executed-snapshot.tar.gz` retains the runner's actual selected execution inputs and generated dependency-free Cargo.lock, without compiled target caches. All archive member hashes and modes are recorded. `source-after.json` independently confirms all original exported files remained unchanged.

Replay the owner's existing entry after exporting the exact commit, with prepared Cargo/Rustup roots:

```sh
CARGO_HOME=/prepared/cargo RUSTUP_HOME=/prepared/rustup CARGO_BUILD_JOBS=2 \
python3 -B /export/tests/abi/run_acceptance.py --repo-root /export \
  --rustup /prepared/cargo/bin/rustup --output-dir /new/outside-output
```

The output must be new and the fixed tools already installed. This validation does not change repository CI or relax compiler/check requirements. A00 still owns integration and subsequent checks against its integrated revision. `SHA256SUMS` covers every retained file except itself.
