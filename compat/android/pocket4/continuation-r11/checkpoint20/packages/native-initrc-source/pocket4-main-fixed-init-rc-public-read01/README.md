# Fixed Main init source projection — read01

**SOURCE_ONLY. Not dispatched; Python compilation and 14 controls have not run.**

The request reads only the two originally proposed files under the held root of Main init PID 3588093, birth 80797014. It preserves their full size and SHA-256 and projects a closed catalog of 16 literal public declarations/actions copied from the locked AOSP system/core commit. It does not export complete rc text or unknown commands.

## Scope

- /proc/3588093/root/system/etc/init/hw/init.rc — at most 131072 bytes.
- /proc/3588093/root/system/etc/init/hw/init.zygote64.rc — at most 16384 bytes.

Boot, init birth, parent, UID tuple, namespace PID, three namespace identities, cgroup and root device/inode must equal the existing current-role authority before and after. A pidfd is retained throughout. The root is held; every subsequent fixed directory and leaf uses nofollow. Both leaf FDs remain held through final directory, name and identity checks. Missing paths, symlinks, changed identities, bounds, read and close errors fail without fallback or retry.

## Public projection

Matches are restricted by exact file and section. The catalog comprises the zygote service header, nine known onrestart directives, the public property-selected import, the zygote-start trigger and four known commands inside that trigger. Duplicate occurrences retain their line numbers. Comments, continuation lines, altered headers and text with extra suffixes do not match. Unknown lines in selected sections expose only line number, byte length and SHA-256; other unknown lines are counted. The complete original file remains represented by its size and SHA-256.

Exact equality to the public upstream file is a separate boolean. It is not proof that this file was loaded, an action ran, the current ro.zygote value resolves this import, or a particular process sent SIGKILL. Sender/OOM/runtime authorization remain false. This reader neither qualifies a QA epoch nor restarts anything.

## Execution boundary

The existing direct sudo Python transport is reused with a new key, 25% CPU, 128 MiB, nice 15 and 20-second outer timeout. The single Python process starts no child. It installs a self-only 15-second watchdog before data FD acquisition, limits observations to 12 seconds and qualifies FD retirement within 14 seconds. Initial interpreter/source setup and the signal/time imports precede the self timer and remain under the outer timeout. The source sets only its own core-dump/dumpable/timer state.

All acquired FDs are accounted, including the Main pidfd and held root. Close failures are retained separately from the first error and cannot qualify success; a failed close is not retried against a possibly reused numeric descriptor. Output is bounded plain JSON. A timeout has no successful completion; Root must read the actual terminal and output.

## Verification status

V8 verified the exact authority subset, every catalog literal against the pinned upstream originals, source/request hashes and request reproducer. The source invokes 14 production projection cases before reading Main. They remain **UNRUN** until Root executes the reviewed request. No device, local process, Git ref or PR action was taken by this task.
