# Lifecycle broker entry and remaining qualification

This revision continues the real `droidloom-psi-owner --lifecycle-fd 3` executable and the `LifecycleBroker` supervisor ownership adapter. It is an uninstalled candidate. Parent freeze04 subsequently passed an owned bootstrap and an Android r6 protocol/HUP trial; those actual receipts do not certify changed source in this revision. Installed supervisor wiring/recovery, real pressure and production readiness remain unqualified here. `owned-relay/PRESSURE.md` defines the added bounded pressure/stale continuation.

## Trusted entry

The supervisor creates a nonblocking Unix `SOCK_SEQPACKET` socketpair and executes the exact, hash-verified broker file. `LifecycleBroker::spawn` does this through a retained executable FD; it returns the retained `Child`/control owner before any bootstrap operation that can fail. The child consumes only inherited FD 3. It requires root UID/GID, the kernel peer PID equal to its current parent, and `SO_PEERPIDFD`; it arms parent-death SIGKILL and rechecks the parent. No PID-name search, ordinary numeric peer-pidfd fallback, endpoint-path request, threshold field, or arbitrary command is accepted.

`BootstrapSpec::send` is also available for an existing trusted lifecycle implementation that already owns its subprocess. It is not a public Android admission API. Both the supervisor and the broker must retain the one-shot cell generation across failed starts; starting a second broker from a different process/directory is not an authorized way to retry a living cell.

The 128-byte bootstrap record contains magic `P4BOOT1!`, version 1, nonzero role UID/GID, a fresh 32-byte nonce, and the expected SHA-256 hashes of LMKD and private init. Flags/reserved fields are zero. Exactly 16 SCM_RIGHTS descriptors accompany this record:

| Index | Trusted descriptor |
|---|---|
| 0 | Already configured, bounded owned cell cgroup root |
| 1 | Exact namespace owner pidfd |
| 2 | Exact private init pidfd |
| 3 | Verified LMKD executable file |
| 4 | Verified private init executable file |
| 5 | Root-owned mode-0700 endpoint directory |
| 6–15 | `pid`, `pid_for_children`, `mnt`, `cgroup`, `user`, `net`, `ipc`, `uts`, `time`, `time_for_children` namespace files, in that order |

The broker validates inherited pidfds with kernel signal-0/type checking and kernel fdinfo, pins the process generation, and requires process leaders. Owner must be the trusted parent or its direct child. Private init must be the owner's direct root child and PID 1 in a private PID namespace. Its executable, cgroup membership, and `/sys/fs/cgroup` projection must equal the passed pins. Namespace files must be nsfs objects of the exact expected types; all except the deliberately supplied APEX mount namespace must equal private init's namespaces. The existing peer authenticator subsequently requires the actual LMKD to match all ten supplied namespaces, role credentials, executable, cell membership, projection, and budget.

The passed directory is retained across listener moves and cleanup. The fixed socket basename is `droidloom-lmkd-psi`; only that socket inode is projected to Android's `/dev/socket/droidloom-lmkd-psi`. The broker atomically creates and persists a `droidloom-lmkd-psi.claim` marker with `O_EXCL`. It never removes that marker, so crash/exit cannot reopen the same cell directory. A new directory belongs to a new generation after old cleanup and exact old process exits, never a retry shortcut.

## Caller order and recovery

1. Create the owned cell scope with its final memory budget, and hold private init/LMKD at a trusted startup barrier after namespace/image/root setup is stable. Hold the actual init pidfd and the intended LMKD namespace files through that barrier. The reference DevelopmentCell currently does not publish this barrier or these handles.
2. Build the sixteen-handle array exclusively from that lifecycle's held objects. Derive both executable hashes from the matching image/build manifest. Call `LifecycleBroker::spawn`, immediately store the returned owner inside ActiveCell, then call `initialize` by mutable reference.
3. `initialize` returns READY only after actual listener creation and authority validation. Check the returned socket device/inode against the projected socket. Release the LMKD startup barrier only after the projection matches. Preserve r6's original PSI threshold/window properties and set `DROIDLOOM_CELL=1`, `DROIDLOOM_LMKD_CGROUP=/sys/fs/cgroup`, and `DROIDLOOM_LMKD_PRESSURE=relay-required` for the real candidate.
4. Consume ACTIVE using `receive_progress`. ACTIVE means the request authenticated and grant delivery completed. It does not mean pressure occurred. READY, ACTIVE and RETIRED all echo nonce, generation, socket/root identities and fixed canonical budget.
5. On explicit shutdown or a faulted RETIRED progress record, keep ActiveCell owned and call `retire`. Its success requires the joined-worker pressure audit, matching RETIRED record, and reaping the exact broker with the matching exit status. Only then stop/reap exact old namespace owner and init and perform namespace/cgroup cleanup. The shared caller slot rejects replacement until the retirement flag and both old pidfds prove exit. Consume progress through `LifecycleBroker::receive_progress`; the lower-level `BootstrapSpec::receive_status` reads a single 160-byte status and is only used for initial READY by this adapter.
6. On timeout, panic, incomplete bootstrap, channel loss, or missing receipt, retain the owner and report that recovery is incomplete. No success acknowledgement or next-cell creation is permitted. `abort_before_initialize` is valid only before any bootstrap attempt, when no authority was sent. A failed active bootstrap is not retried. Dropping the handle closes control to provoke cleanup but does not fabricate a certificate or reset the slot.

The broker reports HUP/service failure through faulted RETIRED and exits with failure after its PSI worker joins. Native LMKD r6 disables pressure monitors when its lease fails; it cannot reenroll in the same process. The platform must use the above lifecycle recovery flow to regain pressure monitoring. No installed platform recovery hook is claimed here.

## Terminal observation record

After admission and PSI worker join, the broker sends one fixed 2560-byte `P4AUD01!` record and then the existing 160-byte RETIRED status on the same private inherited channel. No SCM_RIGHTS are allowed on either progress packet. The caller binds the audit to READY's nonce, authority generation, cgroup and immutable budget; a duplicate audit or later nonterminal status is rejected. Audit retrieval is unavailable until terminal status and exact child reap complete.

The record retains the raw successful registration write bytes/counts, pressure device/inode, monotonic write interval, and lease generation. Its fixed 64-event array records actual POLLPRI observation and successful notification send completion. Overflow, a consumed but unqueued observation, a queued packet missing its audit row, or a fault marks the record incomplete. Event observations are host poll-return timestamps, not a claim to know the kernel's internal trigger-creation timestamp. These observations do not alter any original threshold, freshness gate, effect path or ownership decision.

## Bounded matching verification

Run in a fresh matching host build directory with one CPU, 512 MiB maximum, nice 5, and inputs hashed before and after:

```sh
cargo build --locked --offline -j 1
cargo test --locked --offline -j 1
./target/debug/owned-ipc-controls
```

Expected tests: the parent 15 Rust controls plus two audit codec/completeness controls, two real socketpair terminal-audit/framing/FD-cleanup controls, and one cancellation-tail batch-observation control (20 total), and seven ordinary IPC controls. The existing panic control verifies that a consumed worker JoinHandle cannot turn a repeated failed retirement into success. The added socket tests drain the full audit followed by RETIRED after peer close and prove rejection closes every transferred pipe writer by observing EOF. These unit controls do not launch the production executable, enter namespaces, register PSI, allocate pressure, or run Android. The existing diagnostic PSI/event modes are not part of this build check.

## First actual Android canary and rollback boundary

Use a single fresh owned fixture with a fixed budget from its creation, initially protocol-only. Feed the real broker entry the fixture's held handles and run the actual matching Android r6 `lmkd-cgroup` binary (SHA-256 `bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde`). Record root/budget/namespace/executable pins, READY/ACTIVE, actual Android accepted grant and FD ownership, zero untriggered kills, explicit retirement, native HUP, broker receipt, and exact old process exits. Use only self-owned registered targets and target cgroups.

The owned lifecycle caller now has `prepare`, `bootstrap`, `protocol`, `pressure`, and `stale` modes. `owned-relay/CANARY.md` retains the bootstrap/protocol procedure. `bootstrap` never starts LMKD or registers PSI. The other three use matching Android r6 LMKD, authenticated enrollment, normal framework control and native HUP. Only the two explicit new modes induce bounded pressure; none are invoked by the build checks.

The prior r9 runner cannot be reused by changing its binary hash: it changes `memory.high` after lease creation. The earlier host event fixture used a 70 ms critical trigger, whereas r6 preserves its property-derived original thresholds (default critical 700 ms) and window. The new pressure/stale actor sets its final 512/384 MiB hard/high values before authority construction and never changes them. Native and driver completion alone retain `real_pressure_verified:false`; the separate externally pinned evidence qualifier requires actual registration/event/effect correlation. Medium-only pressure evidence is partial and never upgraded by further pressure after the cached victim exits.

Rollback for this uninstalled canary is confined to the owned fixture: request broker retirement, require the RETIRED/exit receipt, stop/reap its exact init/owner, and remove only that terminated fixture's private mounts and files. Never change Main's installed ACK binary or current service, and never invoke the old broad cleanup/pressure runner against it. If the broker receipt is missing, preserve handles/evidence and report the blocked lifecycle; do not call cleanup complete.
