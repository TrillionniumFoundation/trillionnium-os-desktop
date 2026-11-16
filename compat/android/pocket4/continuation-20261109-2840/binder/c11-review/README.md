# C11 private Binder review fixes

This capsule contains two independently applicable fixes to the foreground owner's C11 Binder implementation. Both fixes, and their combination, compiled and passed the named ordinary tests in isolated Pocket4 source trees. No private Binder control, mount operation, Android startup, installation, or production admission was executed by this review.

The exact three preimages and postimages are included. The original C11 source is the frozen `qualification/normal-production-binder-independent-r1/source` under `/home/alex/work/pocket4-production-namespace-broker-20261109-8b88-r1`. Its original normal receipt is 34,902 bytes, SHA256 `0b2d86aa9f3489b9a0f9ca3ae3c04198eeafd5cce111835c395ae666115d0834`. This is distinct from the older live C10 source and the discontinued parallel Binder experiment.

## Fix 1: reject successful observations after their deadline

`deadline.patch` changes only the test-only `production_namespace_binder_ipc_child.rs`. The original C11 source explicitly gives all three context transactions one shared two-second work deadline, followed by bounded reap. Each already-owned client's reap already has a separate 250 ms allowance. The caller retains its existing three-second outer protocol bound.

The original implementation checked time before `BINDER_WRITE_READ`, but accepted an ioctl result without checking time afterward. Its server loop accepted an exited child before checking the work deadline. A successful client report, successful `waitid` reap, and final successful return could likewise be accepted after their respective deadlines. An exit status of zero therefore did not establish the claimed timing bound.

The patch checks the monotonic clock at successful ioctl acceptance, successful client-reply acceptance and final report preparation, the server's child-exit observation, successful reap, and the final test return. It retains the separate 250 ms cleanup budget, including on failure. The complete successful return must occur before the shared work deadline plus that final cleanup allowance, or 2.25 seconds. The change does not reset consumed Binder write state, repeat a completed or uncertain Binder command, or introduce another transaction attempt. An expired successful observation becomes an error and follows the existing ownership and cleanup path.

The two new ordinary tests exercise an already-completed result rejected at an expired deadline without a second invocation, and the separation between an expired work budget and a still-valid cleanup budget. They do not execute Binder IPC.

## Fix 2: require mapped ownership of root and features

`mapped-ownership.patch` changes only `production_namespace_binder_child.rs` and `production_namespace_binder_parent.rs`. It adds exact UID/GID checks to the already-held metadata for the Binder root, the `features` directory, and each feature file, on both sides of the barrier. The child must see UID/GID 0; the initial-user-namespace parent must see the admitted lease's starting UID/GID. Existing control-node and transaction-device checks remain intact.

The prior comment claimed that ordinary Binder inodes use global-root IDs and can legitimately appear as overflow IDs inside the child user namespace. The actual kernel build source contradicts that claim:

- `drivers/android/binderfs.c` creates the root and feature inodes using `new_inode` and does not override their ownership.
- `fs/inode.c:228–250` initializes every new inode with `i_uid_write(inode, 0)` and `i_gid_write(inode, 0)`.
- `include/linux/fs.h:1408–1436` maps those numbers through `inode->i_sb->s_user_ns` using `make_kuid` and `make_kgid`.
- `fs/stat.c` converts the stored IDs through the observer's `current_user_ns()` when returning stat fields.

The checked build tree is `/home/qq/work/pocket4-kernel-binder-cred-20261108-8b88-r1/build-r1/source-parent/linux-source-7.0.0` on ai395. The file hashes and exact excerpts are in the evidence directory. The ownership expectation follows from those actual source bytes and the existing fixed, non-idmapped mount construction. No new mount was performed to infer it, and no overflow-owner fallback is introduced. Actual private-stage behavior remains for the foreground owner's reviewed control.

## Ordinary verification

| Input | Durable job | Actual ordinary results |
| --- | --- | --- |
| Deadline fix alone | `1a1c132e030-e62c-29` | 4 passed, 0 failed, 0 ignored |
| Ownership fix alone; original IPC file retained | `1a1c1371e7e-e62c-34` | 9 passed, 0 failed, 1 private control ignored |
| Both fixes in the same exact C11 source | `1a1c13aec0c-e62c-3c` | IPC group: 4 passed. Original Binder group: 9 passed, 1 private control ignored |

The combined result represents 13 test executions covering 11 distinct ordinary tests: the two old IPC layout/pointer tests run in both groups. The second group explicitly excludes the two new deadline tests already run in the first group, preserving the exact nine-test ownership group. The private Binder test retains its original ignored attribute; no `--ignored` option was used.

Each accepted compilation used a fresh, private Cargo target. The combined log proves actual compilation from the combined source path. Before and after source manifests match exactly: 411 files, 6,193,974 bytes. The original manifest is 66,234 bytes, SHA256 `95d7627c59b7ba8b5115e3e68e8bcffa13fc3db92e37dd00bb116eaf0f990d70`. The compact copy preserves the entire manifest and round-trips to those exact original bytes with the recorded serialization. The test ELF is 42,959,272 bytes, SHA256 `86f22dda389b4dcf88e75b14ae347e9b92f3ab1646ffb0b8098291405c48a1e9`.

The normal units were limited to CPU 2 at 100%, 4 GiB memory, no swap, and a 300-second outer runtime. The combined unit took 26.31 seconds and peaked at 849 MiB. Independent retirement checks observed each unit inactive with MainPID 0, no control-group path, and its cgroup absent. No executable under this review's candidate root remained running at that check.

An initial deadline-only attempt, `1a1c12ea966-e62c-21`, exited zero but ran zero tests after a previously used target reused an old test binary. That attempt is explicitly rejected as qualification evidence. Its original output is retained as `deadline-r1-rejected-normal-tests.log`. The accepted runs use new targets and assert the exact nonzero test summary.

## Replay and adoption

`preimage-pins.json` identifies the exact C11 bytes each patch expects. Apply to that source generation only. The two patches touch disjoint files and can be applied in either order; the capsule includes the expected combined postimages and a local exact replay check. No helper script or additional build dependency is required.

From an isolated, exact C11 workspace, after verifying the preimage hashes:

```sh
git apply --check /absolute/capsule/deadline.patch
git apply --check /absolute/capsule/mapped-ownership.patch
git apply /absolute/capsule/deadline.patch
git apply /absolute/capsule/mapped-ownership.patch
```

Use a new or correctly bound private `CARGO_TARGET_DIR` and the resource wrapper already used for the source generation. The exact two normal commands are recorded in `evidence/combined-result.json` and its raw logs. Compare resulting file bytes to `source/` before using an existing qualification record.

The tested remote combined source is `/home/alex/work/pocket4-production-binder-stage-20261109-2840-r1/c11-combined-review-r1/source`. The foreground owner must still freeze and qualify the adopted input before its private control. This review does not replace its retained PIDFD, nonce/SCM credential, lease, mount-inventory, descriptor barrier, quarantine, or actual child-reap checks. The witness remains a preparation witness, with no Running or Android admission credit.

All private Binder IPC, Android runtime, ABI/cohort, application business-flow and production-ready claims remain false or pending in this capsule. The earlier host Binder smoke does not substitute for those gates.
