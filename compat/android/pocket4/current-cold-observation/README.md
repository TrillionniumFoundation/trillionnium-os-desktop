# Cold VM observation candidate

This directory adds read-only diagnostics and rejects FIFO replacements without blocking in the reviewed R8 cold VM controller's regular-input and log opens. It is a source candidate for a newly admitted generation. The R8 soft lockup and long clocksource interval remain failed acceptance gates; this change has not run a VM or qualified Android, applications, or production readiness.

## Required generation binding

The complete controller deliberately retains the original sealed bundle digest checks, original control lock, create-only paths, resource limits, and R8 generation constants. Do not execute it with the existing R8 bundle or reuse the R8 output namespace.

The current execution owner must incorporate the reviewed changes into a fresh generation, rebind the controller, native carrier and sealed input identities together, and complete the existing owner admission and create-only sealing workflow. The existing workflow supplies the fresh nonce. This source snapshot does not grant a new execution admission or bypass the original control lock.

An expected kernel export must match its exact reviewed compiler input and target kernel. A newly changed policy, including a browser policy change, needs its own complete export qualification. This diagnostic candidate does not select an expected export.

## Observations added

Each existing CPU sample now brackets its work with metadata observations of three held output files: the kernel console, QEMU stderr, and the COM2 component log. File descriptors are opened read-only with `O_NONBLOCK`, `O_NOFOLLOW`, and `O_CLOEXEC`. Each must identify the original regular, single-link inode. Samples retain the inode and ownership fields, size, mtime, ctime, and monotonic and wall-clock boundaries. Inode replacement, new hard links, truncation after an observed extent, and an extent above the existing serial limit fail the observer. A FIFO replacement is rejected without waiting for a writer or reading its content.

The existing one-second minimum CPU sampling interval, 160-sample limit, and 64-task limit are unchanged. The observer reads metadata during execution; the existing final full-file collection and validation remain in place. No extra QMP command, transport change, output throttling, watchdog change, or scheduling/resource change is introduced.

Task samples also expose the already captured `/proc/<tid>/stat` counters as `utime_ticks`, `stime_ticks`, and `guest_time_ticks`, with the actual host `SC_CLK_TCK`. Guest time is included in `utime`; adding it to `utime + stime` would double count. Adjusted task counters and guest accounting may temporarily differ, so raw values are preserved without clamping. Short-interval derived differences should be treated as accounting estimates, not precise execution traces.

The controller records monotonic/wall-clock pairs around its existing QMP start call. The qualified QMP helper, its peer/owned-process checks, and its single `cont` operation are unchanged. These controller boundaries can be joined to the existing QMP `RESUME` event; they are not guest clock synchronization measurements.

## Interpretation limits

Output extents can bracket when complete final log records first became observable. Cross-file metadata reads are not atomic, and sizes do not prove that a file's earlier bytes were unchanged between samples. Metadata does not replace the existing final complete-log hashes or any acceptance check. A sample remains bound to the original process and invocation; it is not authority over a newly discovered process.

The additions do not capture KVM exit reasons or UART port counters. A correlation between COM2 growth and host CPU time is diagnostic evidence, not proof that UART I/O caused the kernel soft lockup. The original byte equality, security decisions, namespace, original systemd, lifecycle, resource, and critical-console gates remain unchanged. No runtime or production qualification follows from the local tests.

## Regular-input and final-log failure handling

The original `pin()` was reproduced blocking on a real FIFO with no writer. The independent reproduction child entered `pin()`, exceeded its outer two-second timeout, and was terminated and reaped. The updated read-only open adds `O_NONBLOCK`; the original regular-file, size, link, complete-byte, identity, and hash checks remain in place.

The three final-log synchronization call sites use a small `sync_regular_log()` helper. It opens read-only with `O_NONBLOCK`, `O_NOFOLLOW`, and `O_CLOEXEC`, checks the actual opened descriptor is a regular file before calling `fsync`, and always closes it in `finally`, including when `fsync` raises. The existing complete log and identity checks still follow the synchronization. A nonregular file or a synchronization error propagates as failure; it cannot qualify the observation.

The reviewed native outer carrier still sets `RuntimeMaxSec=600`, `TimeoutStopSec=120`, and `KillMode=control-group`. These service-level limits do not make a blocking operation obey the controller's 15-second or 150-second Python deadlines. `O_NONBLOCK` prevents the demonstrated FIFO-open wait; it does not guarantee that regular-file storage I/O or `fsync` will never block. This directory does not claim that every existing I/O operation is nonblocking.

## Verification

Run the self-contained local suite from the repository root:

```sh
python3 -I -B compat/android/pocket4/current-cold-observation/test_observation.py
```

The 17 tests import the controller without calling its execution entry point. They exercise real temporary regular files, inode replacement, hard links, symlinks, truncation, output limits, and descriptor cleanup. The serial observer, `pin()`, and final-log helper each have a real FIFO-without-writer regression in an independent child process with an outer two-second timeout. Additional tests check complete regular-file contents and identity, rejection before any FIFO read or `fsync`, and actual descriptor closure after an injected `fsync` error. Accounting tests cover field positions, complex process names, and preservation of unadjusted counters. AST baseline checks verify preservation of all original `need()` guards, the fixed VM argument/resource settings, and the existing QMP start call.

The minimal AST baseline was derived from the exact 98,797-byte original controller with SHA-256 `93f70fe04854339fad0740f64d2aa6bc3546e7eb64286edc4a20cef28a0953e5`. It permits the tests to run without shipping an old controller or private runtime evidence. `manifest.json` pins the complete current source, tests, baseline, and this document. The manifest itself is identified by the containing repository commit.
