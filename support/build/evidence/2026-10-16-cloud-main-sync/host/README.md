# Exact current-main G0 host validation

Main `bc294f75bfb8c03d9963f5a12ea23b9589779d96`, tree `39316103c8a1ee881703a38ad5c50a1cc96c055f`, was exported into a new isolated scratch directory. All45 source/config inputs retain their exact Git blobs, bytes and executable modes after execution. This task modified no source file, owner branch, kernel, previous frozen blocker-closure archive or root README. [Source bindings](source-inputs.json), complete [source archive](source.tar.gz), [selected environment](environment.json), [original commands](commands.json) and every full log are retained.

| Actual command group | Result |
| --- | --- |
| ABI cargo test --all-targets |61 passed across seven binaries;0 failed/ignored/filtered |
| ABI separate doctest |1 passed;0 failed/ignored/filtered |
| Control cargo test |1 unit +20 conformance passed;0 doctests;0 failed/ignored/filtered |
| ABI / control cargo fmt -- --check |both0 |
| ABI strict all-target Clippy |101; first reports tests/transport_preflight.rs:28 |
| Additional strict narrow Clippy |--test mutation_kill and --test transport_vectors both101, reporting the other two unchanged helper diagnostics |
| Control strict all-target Clippy |0 |
| Python ABI / spec / archive model |30 /14 /5 each under -I and -I -O:98 passing executions |
| Independent golden checks |12 HOS2 +24 semantic edge frames +1 transport descriptor;3 supported generator invocations passed |
| A05 host smoke |actual sh tests/kernel/control/run-host-smoke.sh exit0; Linux selftest, actual /dev/null ENOTTY vs injected EFAULT |

**181 host-test executions passed**:83 Rust including the one ABI doctest, plus98 Python. Golden vectors, formatting, lint commands and C smoke remain separate metrics. **Overall validation is partial**, not all green: three actual ABI Clippy commands fail. No kernel, QEMU guest, native HOS2 control operation, CPU budget or Hepta runtime acceptance was executed. [Machine report](report.json) records counts and commands.

The original controller tool session60513 completed exit0 after recording all23 initial child-command outcomes, including nonzero results. Its own0 is not an all-pass verdict. One supplementary supported generator and two narrow lint commands bring retained command attempts to26. ABI all-target testing generated a small new Cargo.lock; later ABI commands use --locked. The control's tracked lock remains unchanged. Both [ABI lock](os-abi.Cargo.lock) and [control lock](os-control.Cargo.lock) are retained.

## Retained invocation and observer errors

The extra direct python3 -I tests/golden/generate_hos2_edges.py --check invocation failed because isolated Python excludes the script directory while the unchanged generator imports sibling generate_hos2. The original traceback is retained. The [ordinary-Python supported retry](supplementary-command.json) exits0, matching the existing semantic-edge unittest subprocess. Both ABI Python suites already passed that test. This is an unsupported invocation, not observed golden-byte drift.

The initial observer incorrectly compared full filesystem permissions with0644/0755. Git archive emitted0664/0775 and extraction preserved them; Git tracks executable status. Thus [original source-after](source-after.json) and [original completion](completion.json) say false although every byte was unchanged. Both original records remain intact. The [read-only correction](source-integrity-correction.posthoc.json) verifies original tar permissions, Git modes and bytes; [final integrity](final-integrity.json) checks actual blobs/modes after all26 commands. No chmod or source edit was used to obtain that result.

A Clippy target stopping first cannot prove other helper code fixed. The [two additional narrow command receipts](narrow-clippy-commands.json) retain real101 diagnostics for the other two helpers. All three source files still contain chunks_exact(2). The separate handoff remains pending owner adoption. Initial informal estimates were corrected from actual logs: the separate ABI doctest count is1, not0, and the absent full-target diagnostics did not establish adopted helper fixes. A packaging counter initially matched python-version as a test suite; that assertion stopped packaging before report creation and was corrected without running any tests again.

## Environment and replay

The existing installed nightly-2026-07-21 was used offline with two Cargo jobs; no Rust install/upgrade or rustup component add was attempted. The new owned target began absent; no other target was borrowed. Registry/toolchain caches were reused. Host-only CARGO_PROFILE_DEV_DEBUG=0, CARGO_PROFILE_TEST_DEBUG=0 and CARGO_INCREMENTAL=0 kept final target regular-file bytes to13491345, below200MiB. Nonstandard tool/cache paths and actual cwd/argv are recorded. df reported0 available but all actual writes/builds succeeded without ENOSPC.

Replay by extracting source.tar.gz into another new scratch directory, supplying the recorded already installed toolchain/cache, selecting a new target with the recorded profile, and executing argv from commands.json, supplementary-command.json and narrow-clippy-commands.json. The workflow component-install step was intentionally omitted because components were already installed and this task forbids install/upgrade. Its selected host tests, generators, strict checks and mandatory smoke were executed; this does not mean a GitHub Actions job ran.

SHA256SUMS covers every other file. Packaging checked all45 tar members against input blobs and every command-log SHA. No target or pycache is archived.
