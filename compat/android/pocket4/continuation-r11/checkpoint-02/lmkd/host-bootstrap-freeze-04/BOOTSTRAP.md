# Lifecycle broker entry and remaining qualification

This revision adds a real `droidloom-psi-owner --lifecycle-fd 3` executable and the `LifecycleBroker` supervisor ownership adapter. It is an uninstalled candidate. The installed `droidloomd` source-to-binary match, its startup barrier, and its actual caller wiring remain unqualified. These files do not claim an Android enrollment, real PSI delivery, foreground preservation, or production readiness.

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
5. On explicit shutdown or a faulted RETIRED progress record, keep ActiveCell owned and call `retire`. Its success requires both the joined-worker RETIRED record and reaping the exact broker with the matching exit status. Only then stop/reap exact old namespace owner and init and perform namespace/cgroup cleanup. The shared caller slot rejects replacement until the retirement flag and both old pidfds prove exit.
6. On timeout, panic, incomplete bootstrap, channel loss, or missing receipt, retain the owner and report that recovery is incomplete. No success acknowledgement or next-cell creation is permitted. `abort_before_initialize` is valid only before any bootstrap attempt, when no authority was sent. A failed active bootstrap is not retried. Dropping the handle closes control to provoke cleanup but does not fabricate a certificate or reset the slot.

The broker reports HUP/service failure through faulted RETIRED and exits with failure after its PSI worker joins. Native LMKD r6 disables pressure monitors when its lease fails; it cannot reenroll in the same process. The platform must use the above lifecycle recovery flow to regain pressure monitoring. No installed platform recovery hook is claimed here.

## Bounded matching verification

Run in a fresh matching host build directory with one CPU, 512 MiB maximum, nice 5, and inputs hashed before and after:

```sh
cargo build --locked --offline -j 1
cargo test --locked --offline -j 1
./target/debug/owned-ipc-controls
```

Expected tests: previous nine Rust tests, five bootstrap controls, and one permanent retirement-panic control (15 total), and seven ordinary IPC controls. The five bootstrap controls exercise fixed codec rejection, real SCM_RIGHTS/CLOEXEC ownership, rejected extra authority/replay, truncated-packet cleanup proven by pipe EOF, and terminal status delivery with peer HUP. The panic control verifies that a consumed worker JoinHandle cannot turn a repeated failed retirement into success. These unit controls do not launch the new production executable, enter namespaces, register PSI, allocate pressure, or run Android. The existing diagnostic PSI/event modes are not part of this build check.

## First actual Android canary and rollback boundary

Use a single fresh owned fixture with a fixed budget from its creation, initially protocol-only. Feed the real broker entry the fixture's held handles and run the actual matching Android r6 `lmkd-cgroup` binary (SHA-256 `bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde`). Record root/budget/namespace/executable pins, READY/ACTIVE, actual Android accepted grant and FD ownership, zero untriggered kills, explicit retirement, native HUP, broker receipt, and exact old process exits. Use only self-owned registered targets and target cgroups.

This revision contains an executable owned lifecycle caller, `owned-relay-canary`, with `prepare`, `bootstrap`, and `protocol` modes. `owned-relay/CANARY.md` defines its bounded first invocation. `bootstrap` holds the real private init, exercises the real broker executable and returned FD-based identities, projects its socket, obtains actual retirement, proves same-living-cell replacement refusal, and reaps both owned lifecycle processes. It never starts LMKD or registers PSI. The subsequent `protocol` mode uses actual r6 LMKD and verifies authenticated grant, normal framework control, no-pressure targets and native HUP; it is not run by the build checks.

The prior r9 runner cannot be reused by changing its binary hash: it changes `memory.high` after lease creation. The earlier host event fixture used a 70 ms critical trigger, whereas r6 must preserve its property-derived original thresholds (default critical 700 ms) and window. Neither new canary mode allocates pressure or changes the budget. A real-pressure driver is still absent and must configure its final budget before bootstrap without relaxing the trigger to force a passing event.

Rollback for this uninstalled canary is confined to the owned fixture: request broker retirement, require the RETIRED/exit receipt, stop/reap its exact init/owner, and remove only that terminated fixture's private mounts and files. Never change Main's installed ACK binary or current service, and never invoke the old broad cleanup/pressure runner against it. If the broker receipt is missing, preserve handles/evidence and report the blocked lifecycle; do not call cleanup complete.
