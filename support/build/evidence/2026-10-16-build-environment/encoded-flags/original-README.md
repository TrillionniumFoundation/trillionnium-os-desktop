# Fixed Cargo encoded-flag override: actual reproducer and ktest guard

The public kernel-test entry now rejects any inherited `CARGO_ENCODED_RUSTFLAGS`, including an explicitly empty value, before lock creation, output allocation or any tool/build invocation. It exits 2 and directs the user to unset the variable. Ordinary RUSTFLAGS behavior is unchanged. This protects the mandatory linker script, static relocation, no-redzone and other flags that OSDK supplies through RUSTFLAGS.

The two new host-only CLI regression tests exercise explicit and default output rejection, prove that no fixture tool/target/lock/output was created, then unset the variable and successfully retry the identical explicit command/output path. They failed against a saved pre-fix runner (2 failures, exit 1). The complete final lifecycle suite passed 17/17 both normally and with Python -O (actual tool sessions 57051 and 68174, each exit 0). These are host fixture checks, not kernel or QEMU acceptance.

The separate real tiny Cargo experiment used the exact installed nightly-2026-07-21 Cargo and rustc with one dependency-free binary and three independent target directories. All commands used --locked --offline. With `RUSTFLAGS="--cfg from_rustflags"`, actual program output was:

| CARGO_ENCODED_RUSTFLAGS | Actual output | Cargo exit |
| --- | --- | --- |
| absent | RUSTFLAGS=true;ENCODED=false | 0 |
| present, empty | RUSTFLAGS=false;ENCODED=false | 0 |
| --cfg + unit-separator + from_encoded | RUSTFLAGS=false;ENCODED=true | 0 |

The empty case proves a presence check is necessary. Exact executable hashes/versions, argv, selected environment, output, source and lock are retained in cargo-precedence.json, cargo-*/invocation.json and the corresponding logs. These tiny host programs do not represent a kernel build or boot. `osdk-mandatory-flags-excerpt.txt` and source-bindings.json pin the inspected mandatory-flag injection; no OSDK/core/OSTD source was changed.

The coordinated normal shell guard is owned by another agent. Kernel-debug calls reach that shell guard, but this patch does not add a guard before the debug top-level output allocation. OSDK-integration top-level validation is outside this patch. These scope limits must remain explicit.

Source snapshots preserve the exact new test/runner bytes and the original OSDK builder. The two new tests in baseline-lifecycle/ are intentionally run with the pre-fix copied run.py. Generated __pycache__ and each tiny target cache are scratch only and need not be included in repository evidence; the checksum list excludes them. No VM, mount, namespace, host setup change or large kernel compilation was performed for this task.
