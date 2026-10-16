# A01 host tools and OSDK regression evidence

The exact fixed Rust toolchain was retained. GDB 15.1 is executable from a scratch-only dependency root. The original full 14-unit OSDK suite ran without skips: **13 passed, 1 failed**, exit 101. The selected non-VM integration subset passed **13/13**. This directory records a host-tool regression result, not a new kernel boot result.

## Tool acquisition and validation

`apt-get -o APT::Sandbox::User=root download gdb libbabeltrace1 libdebuginfod1t64 libipt2 libpython3.12t64 libsource-highlight4t64 libboost-regex1.83.0 libdw1t64` downloaded eight packages from the standard Ubuntu `20260828T000000Z` snapshot. All eight package sizes and SHA256 values were verified against apt metadata before use; package metadata and dependency lists are in `gdb-package-metadata.json`. Only `dpkg-deb -x` was used, so pending rdma-related post-install scripts were not executed. `pending-package-status-after-download.log` preserves the unchanged half/unconfigured states.

The working dependency root is `/workspace/scratch/ae1a8cf05419/a01-host-tools-next-e5ae/root`. All regular files in this fresh extraction were compared to their package tar entries by size, mode, and SHA256; `gdb-unpacked-files.json` and `gdb-fresh-extract-all.log` record those checks. GDB's package tar entry and extracted executable both have size 8,920,528 and mode 0755. `gdb-fresh-dynamic-libraries.log` has no missing libraries, and `gdb-fresh-version.log` records version execution with exit 0. No permission, account, rdma post-install script, or fixed toolchain change was made.

The version check and upstream `have_gdb_installed` unit only establish executable availability. Ptrace and remote debugging were not tested. No new QEMU VM was started for this work.

Setup failures are retained. The initial gdb download was later found truncated (1,696,935 versus expected 4,082,912 bytes), and its tar validation failed. The first extraction destination also contained an incomplete gdb executable (3,923,456 bytes, mode 0700), which produced SIGSEGV on `--version`; its dynamic-linker check failed. These artifacts were rejected. Their origin is unestablished, and no actor or tool is blamed. A new scratch destination was justified by those mismatches, then fully verified as described above. See `initial-truncated-package.json`, `initial-truncated-package-validation.log`, `gdb-destination-comparison.log`, and the retained first-attempt logs. No truncated package or executable was used for the tests below.

## Exact tool environment and tests

```sh
export CARGO_HOME=/workspace/scratch/ae1a8cf05419/toolchains/cargo
export RUSTUP_HOME=/workspace/scratch/ae1a8cf05419/toolchains/rustup
export CARGO_TARGET_DIR=/workspace/scratch/ae1a8cf05419/osdk-regression-target
export CARGO_BUILD_JOBS=2
export OSDK_LOCAL_DEV=1
export PATH=/workspace/scratch/ae1a8cf05419/a01-host-tools-next-e5ae/root/usr/bin:$CARGO_HOME/bin:$PATH
export LD_LIBRARY_PATH=/workspace/scratch/ae1a8cf05419/a01-host-tools-next-e5ae/root/usr/lib/x86_64-linux-gnu
cd /workspace/scratch/ae1a8cf05419/trillionnium-os-desktop/kernel/asterinas/osdk
cargo +nightly-2026-07-21 test --locked --no-run --bin cargo-osdk --test integration
cargo +nightly-2026-07-21 test --locked --bin cargo-osdk -- --test-threads=1
```

The original unit binary contains 14 tests (`osdk-unit-inventory.log`). Compilation occurred before the parent added further build-lock regression tests; those later tests are outside this evidence. `rustc-version.log` identifies the unchanged compiler, and `test-tools.sha256` identifies the actual binaries.

The unit failure is `daemon::supervisor::tests::stop_all_terminates_daemon_descendants`, at `src/daemon/supervisor.rs:318`, asserting `!process_exists(child_pid)`. The full suite's failure is preserved in `osdk-unit-all14.log` and remains a failure. The GDB availability unit passed.

After reading source, only these integration module filters were run: `cli::` (8), `commands::new::` (3 workspace-creation tests), and `examples_in_book::create_os_projects::` (2). Each ran with `--test-threads=1` from a scratch working directory using the compiled original integration harness. All 13 selected tests passed. The complete suite has 22 tests; 9 cases involving kernel run/test or QEMU, including `work_in_workspace`, were not selected. `osdk-integration-runs.json` records actual commands, working directories, and exits; full logs and inventory are retained.

## Descendant-test diagnosis and open limitation

The failed single test received exactly three diagnostic replays, each passing. Those 3/3 focused passes do not replace or erase the original 13/14 result. The first two narrow probes did not capture descendants; the third collected actual host PID, namespace PID, state, process-group, and parent relationships by reading proc status.

`pid-namespace-probe.json` proves that this execution environment presents an ancestor-namespace proc mount: Python's getpid was 5, while `/proc/self` identified host PID 49419 with `NSpid: 49419 5`. Its own sleep child had namespace PID 6, but `/proc/6/status` described an unrelated `caas-prefix-tra` process, which remained after the child was terminated and reaped. The source helper `process_exists` directly reads `/proc/<pid>/stat` using the namespace-local child PID. That assumption is invalid here and can give both false positives and false negatives.

In diagnostic 3, the real shell had host PID 50914 / namespace PID 9; the sleep child had host PID 50915 / namespace PID 10. Both belonged to host group 50914 / namespace group 9. While sleep was running, `/proc/10/status` already returned ENOENT. The shell was observed becoming a zombie, then both real host paths returned ENOENT by harness exit at about 1.064 seconds. Thus that diagnostic observed actual termination, while the helper's numeric path did not identify the sleep process. Errors and observations are recorded in `daemon-focused-3.json`. The original full-suite failure did not print its child PID, so its individual child state was not observed; attributing that particular failure solely to the namespace mismatch remains an inference.

A separate production-code risk remains open: `stop_all` waits for the direct group leader, and `RunningDaemon::kill/terminate` return early after that leader is reaped. A group descendant that ignores TERM may therefore outlive the leader. These ordinary-sleep diagnostics do not resolve or test that case. No production or test source was modified, no test was skipped to obtain a green result, and no ptrace/permission workaround was attempted.

Only evidence is stored here; no .deb, toolchain, executable, or shared-library binary is copied into the repository.

## Isolated proc-alignment attempt

After the three diagnostic replays, exactly one isolated namespace attempt was authorized and made:

```sh
unshare --user --map-root-user --pid --fork --mount-proc /workspace/scratch/ae1a8cf05419/osdk-regression-target/debug/deps/cargo_osdk-87e58130b1b091d4 --test-threads=1
```

It failed before the harness started, with exit 1 and `unshare: write failed /proc/self/uid_map: Operation not permitted`. No changed-parameter retry or workaround was attempted. The existing proc mount, account permissions, and services were not modified. The overall original-unit result remains 13 passed / 1 failed; aligned-proc execution is blocked by the host restriction.
