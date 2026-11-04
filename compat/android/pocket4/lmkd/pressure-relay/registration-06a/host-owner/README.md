# Host authority and revocation owner candidate

This independent Rust crate provides a typed host-side authority, accepted-peer authenticator, and revocable notification-capability owner. It is a source-level candidate for the existing trusted Droidloom lifecycle owner. It is **not** a standalone daemon and is **not deployable**.

The design reference is `denialwm/droidloom` base `75c5acf086f25fb8d2a31d159a57cdb4e75f85de`, with the inherited graphics and presentation-timing changes documented by the parent source bundle. That reference contains `ActiveCell` / `DevelopmentCell`, the lifecycle control loop, and process spawning. The currently installed Main supervisor binary has not been mapped to its exact source build. This crate does not resolve that gap.

## Authority boundary

Only trusted lifecycle code constructs `CellAuthority`. It supplies the already held exact cgroup directory, owned process pins for the cell owner and init, role-specific namespace handles, expected UID/GID, and a pinned executable file plus verified SHA-256. It must not derive any of these from an enrollment request, peer-provided path, process name search, or untrusted descriptor.

`HostContext::open` refuses a proc view that disagrees with the host process PID. It records host namespaces and requires creation by the process leader. Accepted peer authentication is available only for the private marker returned by the real `Listener::accept`; a socketpair cannot be passed as a substitute. `SO_PEERPIDFD` retains the kernel's connection generation, and failure has no numeric-PID fallback.

The authenticator pins and rechecks:

- Exact process birth through a pidfd and a held proc directory; scheduler state and counters are not identity fields.
- SO_PEERCRED plus every real/effective/saved/filesystem UID/GID value.
- PID, PID-for-children, mount, cgroup, user, network, IPC, UTS, time and time-for-children namespace handles.
- The expected executable inode, file metadata and SHA-256 at admission, with later metadata/file identity checks.
- Actual unified cgroup membership resolved below the trusted host cgroup mount, and the peer's fixed `root/sys/fs/cgroup` projection. Both must identify the exact held cgroup. `openat2` forbids symlinks, magic-link traversal and escapes in the resolved directory paths.
- The finite coherent memory budget, lifecycle owner/init generations and their retained identities, and the host namespace view.

Neither the cgroup directory nor namespace, executable or pidfds are transferred to the peer. The proposed Android-facing capability is a packet endpoint whose write half was permanently shut down before transfer. The owner retains the sender and creates at most two capabilities.

## Lifecycle behavior

`LeaseOwner` starts one independent revocation worker. It watches the peer/owner/init pidfds, control connection and cancellation eventfd, with periodic identity/budget revalidation. It never reads scores, chooses a victim, writes a cgroup limit, registers PSI or signals a process.

Peer death or unexpected control data revoke all endpoints without a caller refresh. An old cell generation cannot refresh the lease under a replacement authority. Explicit retirement, failed revalidation or an excess monitor request also close every sender. The native receiver must still give HUP precedence over queued data and use a separate atomic lease gate at every actual LMKD kill decision, including the watchdog.

The lifecycle must call `finish_retirement` and require true before replacing its cell. A timeout retains the handle and is a failed transition. `Drop` requests revocation but does not prove that a stalled worker has completed. A kernel operation may stall despite nonblocking descriptors; userspace timeout arguments do not remove that limitation.

## Scope of actual verification

`host-ipc-public-summary.json` freezes the actual Pocket4 host-only result. The ordinary-host negative arm and the explicitly authorized private, read-only mount-projection arm both passed, within one CPU and 512 MiB. The latter creates only a short-lived child's mount namespace, leaves its cgroup membership and limits unchanged, and creates no Android/private cell. It proves full host authentication and owner retirement under that host fixture, including automatic peer-exit revocation.

The normal host arm remains required: a regular host child must fail the projection gate. Do not disable that check to accommodate a mismatched test environment. The earlier r10 cloud proc/PID mismatch remains a failure.

The source includes a `--private-projection` test option because that exact bounded control was explicitly authorized. It requires root for `unshare(CLONE_NEWNS)` and a private read-only bind. It must not be run as an unreviewed default or against an Android cell. The production library performs no mounts.

## Reproduce the source build and ordinary host controls

Use an isolated target directory and an admitted resource-limited job:

```sh
CARGO_TARGET_DIR=/absolute/owned/output CARGO_NET_OFFLINE=true RUSTFLAGS='-Ccodegen-units=1 -Dwarnings' cargo build --locked --offline -j 1 --bin owned-ipc-controls
/absolute/owned/output/debug/owned-ipc-controls
```

An explicit host-only private-projection run must also bind the test's expected cgroup membership to the exact admitted job and preserve the parent mount/projection guards. The recorded harness checks `memory.max` and `cpu.max` before starting; it is not a general-purpose privileged helper.

## Remaining integration

There is no PSI registrar/producer, event-observation timestamp guard, enrollment request/grant codec, Android FD-transfer client, or change to LMKD r5. The host controls do not prove live monitor registration, foreign Android UID/namespace access, pressure semantics or bounded cleanup under pressure. They do not resolve r7's cached-plus-foreground loss or qualify r5 for Main.

Keep this candidate **HOST_AUTH_AND_REVOCATION_CONTROLS_PASS / DO_NOT_DEPLOY** until those independent gates pass.
