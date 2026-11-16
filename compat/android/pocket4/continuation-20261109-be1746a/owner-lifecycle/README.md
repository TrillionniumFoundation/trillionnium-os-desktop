# Latest owner lifecycle reconciliation (r2)

This capsule applies the previously reviewed creator-thread lifecycle fixes to an exact, independently frozen copy of the owner's **normal-production-private-dev-r1** source. It preserves the newer SSSD admission code, mounts, statfs correction, nested PID1 tree, empty-base consumer and private device interfaces. It changes only three namespace source files.

**This patch is not based on bare b4dc or the earlier broker-r2 source capsule.** Check the three preimage hashes before using it. The full 408-file freeze manifest binds the qualification context; the independent before/copy/after snapshots were identical and all source hashes pinned by the owner's passing r2 run matched. The ordinary verification then confirmed the other 405 files were unchanged.

## Change and compatibility

- Pin the live creating thread with `PIDFD_THREAD` before clone. The fixed child arms parent-death handling and checks that exact descriptor both before its first barrier and after credential changes. A surviving thread-group leader cannot hide the creator's exit.
- Explicitly restore the creating thread's signal mask on every parent return. If restoration fails after clone, transfer the acquired child handles to `Owner` before surfacing the error, so pidfd-bound cleanup retains custody.
- Carry the reviewed procfs calling-thread and PID-namespace checks together with those lifecycle fixes.
- Preserve the owner's test modes `TreeWrongReady=6`, `EmptyRootControl=7` and `DeviceRootControl=8`; assign the three lifecycle test-only modes 9, 10 and 11. Retain `DeviceResource`, the `private_dev` module and phases 20–23 unchanged. This was the only three-way merge conflict.
- Retain FD 4 for the initial keeper's creator-thread witness. The later tree request replaces it with the separately validated witness for the same creating thread. The nested PID1 path arms and checks parent death, closes FD 4, and still reaches its fd3-only barrier. The actual private PID1 control verifies this compatibility.
- Preserve the creator-exit regression barrier: bind the creator while alive, join it, then poll its held thread pidfd within a deadline before releasing the child. `pthread_join` alone does not establish that the kernel pidfd exit notification has completed. The child must still exit 125, never the failure sentinel 127.

## Actual qualification

| Check | Actual result | Boundary |
| --- | --- | --- |
| Production ordinary library tests | 92 passed, 0 failed, 0 ignored, 151 filtered | Owner-declared privileged tests and the lifecycle proc namespace control explicitly excluded |
| Normal binaries | `droidloom-supervisor` and `droidloomd` built | Build is not runtime admission |
| Creator exit barriers | Both passed; rearm case saw the thread pidfd not yet readable immediately after join | Exact bounded kernel-exit barrier then rejection |
| Fixed private userns fixture | 1 passed, 0 failed, 242 filtered | Exact maps, supplementary groups and owned retirement; no HostAdmission |
| Fixed private PID1 fixture | 1 passed, 0 failed, 242 filtered | Direct-parent pidfd/proc, six namespace owners, fd3-only barrier, wrong nonce, init/keeper retirement |
| Temporary privileged binary copy | Single exact copy removed after owned units/cgroups were terminal | Original independently built binary retained in helper target |

The ordinary run had CPU affinity 0, one CPU quota, a 4 GiB memory limit and no OOM events. Each private run used the existing fixed-fixture capability and systemd isolation contract, including private tmp/devices/network, a read-only host view, no-new-privileges and bounded runtime. Both units were collected with MainPID 0 and no remaining control group. Public account/grant file hashes, original-data metadata and the observer's namespace identities were unchanged.

The previous r1 capsule remains sealed and unchanged. This r2 capsule has fresh execution evidence tied to its different owner generation; its counts are not added to r1.

No private device or mounts/empty-root fixture was run by this integration. No account or grant was created, original data bodies were not opened, no Android was started, and no app was installed. `production_admission`, `runtime_qualified` and `production_ready` remain false. Later owner edits are not covered automatically.

## Files and replay

`minimal.patch` changes exactly the three files in `source-manifest.json`. `preimages/` contains their exact complete before images. The source manifest records all before and after byte counts and SHA256 values. `freeze-manifest.json` contains the full 408-file snapshot. `normal/` and `private-r1/` preserve the actual result files and unedited stdout/stderr. `private-stage-retirement.json` records the exact cleanup.

The Rust verifier checks patch and source hashes, rejects symlinked input components, and creates a fresh output directory before applying the patch. Its replay checks only the three declared file transformations; it does not claim to rebuild or qualify the other files.

Use an existing owned directory on a filesystem that permits execution for the verifier binary; the Pocket4 temporary filesystem was previously observed to be mounted noexec.

```sh
rustc --edition=2024 verify-source.rs -o /path/to/owned-executable-directory/pocket4-owner-lifecycle-verify
/path/to/owned-executable-directory/pocket4-owner-lifecycle-verify /path/to/capsule check-before /path/to/frozen-owner-source
/path/to/owned-executable-directory/pocket4-owner-lifecycle-verify /path/to/capsule replay /path/to/capsule/preimages /new/output/directory
/path/to/owned-executable-directory/pocket4-owner-lifecycle-verify /path/to/capsule check-after /path/to/qualified-helper/source
```

The actual Rust 1.93 verifier run passed `check-before`, an independent three-file replay, and `check-after` against the compiled helper source. `source-replay/` contains those outputs and the durable execution status. A separate read-only review reconstructed the same postimages and compared the r2 additions with the already reviewed r1. Its final report is retained as `independent-review.json`. Neither check reran or added to the 92 + 2 test count.

The parent directory of the replay output must already exist, and the output itself must not exist. Applying to the live concurrently edited owner tree is outside this verifier's remit. Reconcile against a fresh frozen generation if any preimage hash differs.
