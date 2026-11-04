# Scoped LMKD pressure notification relay candidate

**Status: host authentication, actual scoped PSI registration and revocation controls pass. Real event/pressure and Android integration qualification are absent. Do not deploy.**

This directory contains a native LMKD notification receiver, a Rust host authority/peer authenticator, and a single independent host worker that owns scoped PSI monitors and revocation. It does not contain an Android enrollment/grant client, a new system service, or a patch to the current LMKD r5 target. The candidate library never chooses or signals a process. The test harness may terminate only its own child on failure. The existing r5 binary, r9 diagnostic fixture, r10 candidate fixture and Main configuration are unchanged. `host-owner` retains the minimal authentication-only revision used by the poison regression; `host-psi-owner` is the separately built and exercised registration extension.

The current Main `droidloom-supervisor` binary has not been bound to an exact source build. The cached Droidloom source is a design reference, not proof of that binary's implementation. That provenance requirement remains open.

## Why a scoped relay is needed

The already-collected Main receipt establishes that its projected `/sys/fs/cgroup` is the service cgroup, that the mount has `nsdelegate`, and that init sees its membership as `0::/` from its own cgroup namespace. Main still runs the ACK-only LMKD compatibility binary.

Linux v7.0 captures a reference to the opener's cgroup namespace in `cgroup_file_open`. `cgroup_file_write` later tests that stored namespace. At a non-initial namespace root under `nsdelegate`, it rejects non-delegatable file writes; `memory.pressure` is not marked delegatable. `psi_trigger_create` independently uses the opening file's saved credentials for the `CAP_SYS_RESOURCE` test. These are open-file-description properties, not a new caller-namespace check performed each time an SCM_RIGHTS recipient uses the descriptor. The Main layout therefore matches the upstream denial condition. No Main trigger-registration write was attempted.

The same sources establish two limitations on directly transferring a pressure descriptor. A registered open description permits one trigger; another registration write returns `EBUSY`. However, closing the host's copy cannot revoke copies held by a recipient. `psi_trigger_poll` also consumes a shared event bit, so polling a descriptor from both host and guest would let them consume each other's notification. The trigger is destroyed by the file-release path, not by closing an arbitrary one of several references.

Primary source pins:

| Source | Tag and Git blob | Relevant behavior |
| --- | --- | --- |
| [Linux cgroup implementation](https://github.com/torvalds/linux/blob/v7.0/kernel/cgroup/cgroup.c) | `v7.0`, `4ca3cb993da299aa10174cc619268840b7984049` | Opening namespace retention, namespace-root write gate, one trigger per open description, poll and release |
| [Linux PSI implementation](https://github.com/torvalds/linux/blob/v7.0/kernel/sched/psi.c) | `v7.0`, `d9c9d9480a45b735a996cc22f5d7a4bef6545a3c` | Saved opening credentials, shared event-bit consumption, trigger destruction |
| [Linux socket implementation](https://github.com/torvalds/linux/blob/v7.0/net/core/sock.c) | `v7.0`, `5976100a9d55a0044608ce9466476e243a84d289` | `SO_PEERPIDFD` obtains the connection's retained `sk_peer_pid`, including a stale generation |
| [Linux socket ABI](https://github.com/torvalds/linux/blob/v7.0/include/uapi/asm-generic/socket.h) | `v7.0`, `53b5a8c002b1eeeaa0485ca09a13c6f5666fb8fc` | `SO_PEERPIDFD = 77` |

## Capability choice

| Mechanism | Finding | Decision |
| --- | --- | --- |
| Transfer registered `memory.pressure` FD | Scope is narrow, but host-only close cannot revoke retained copies; multiple pollers share one event bit | Do not use for a revocable lease |
| Transfer anonymous pipe read end | Actual owned-FD negative control reopened the read end through `/proc/self/fd` as a writer under creator credentials | Do not describe a pipe read end as an unforgeable capability |
| Transfer one endpoint of a Unix packet socketpair | Host first shuts down its read half and the recipient's write half. Recipient writes fail with `EPIPE`, procfd reopen with `ENXIO`, and tested `AF_UNSPEC` reconnect with `EINVAL` | Proposed notification capability |

The host retains the real PSI descriptors. LMKD receives only a packet endpoint plus immutable lease metadata. The host has the only sending endpoint; it never transfers that endpoint, a cgroup directory FD, a namespace FD, or a host pidfd into Android. A duplicate of the recipient endpoint still observes peer closure. Closing the host endpoint produces HUP even when old records remain queued; the receiver rejects HUP before considering those records.

These tests establish the stated descriptor behavior on the local Linux 6.18.57 executor. They are not a substitute for a Pocket4 Linux 7.0 registration and revocation canary.

## Host owner and authentication design

The intended owner is the existing trusted lifecycle owner. Do not add an independently privileged daemon, modify cgroup membership, disable `nsdelegate`, or broaden Android's visible cgroup tree.

The reference `control.rs` owns an `ActiveCell` containing a `DevelopmentCell`. Its `run_loop` handles operations synchronously, including operations that can wait for Android. A pressure relay must not depend on that loop returning promptly. Use one bounded worker owned by the cell lifecycle, at most two active monitor slots, and no thread per client. Teardown explicitly cancels and revokes the worker before releasing or replacing the cell. The worker also watches the retained cell/init and LMKD pidfds so normal cell or peer death does not depend on the CLI loop's polling interval.

The reference lifecycle CLI's `peer_uid` authorizes a host user; it discards the peer PID. Its Android discovery helpers use network-namespace membership. Neither is sufficient authentication for this new endpoint. The new enrollment path must retain stronger kernel-backed identities.

Required enrollment sequence:

1. Obtain the exact cell generation from the trusted lifecycle handle. Pin the namespace owner and Android init generations, the projected cgroup directory's device/inode, its finite budget, and the relevant namespace handles. Do not accept a caller-provided path, PID, cgroup name or file descriptor as authority. Do not discover the target by a process name.
2. Accept a bounded binary enrollment request on a cell-specific, host-owned Unix endpoint. This is a separate protocol from the host-user lifecycle CLI. Obtain `SO_PEERCRED` and **`SO_PEERPIDFD` on that accepted enrollment connection**. A socketpair created by the host records its creator's peer credentials; its peer credentials cannot authenticate the later FD recipient.
3. Reject a dead/stale peer pidfd. Verify the peer's expected Android LMKD UID, executable pin, start identity, PID namespace, cgroup namespace, applicable mount identity, and actual membership under the exact held cell cgroup. Re-read identities around enrollment. Match the projected Reader root's device/inode, not a textual path prefix. Verify the process and host share the relevant time namespace before comparing `CLOCK_MONOTONIC` values. No fallback from `SO_PEERPIDFD` failure to a newly opened numeric PID is allowed.
4. Validate the request's level/window/threshold against the values the genuine LMKD calculated for `init_mp_psi`. The host must copy and echo those exact values; it must not clamp, raise or replace a threshold. Permit only the supported medium/some and critical/full monitor slots, with the existing 500,000–10,000,000 microsecond window constraints and `0 < stall <= window`.
5. From the held cgroup directory, open only the literal `memory.pressure` basename with `openat`, `O_NOFOLLOW`, `O_CLOEXEC`, and `O_NONBLOCK`. Verify cgroup2, the held directory identity, the pressure-file identity, and a coherent unchanged budget before and after registration. Register while still in the trusted host namespace and credentials. Never open a client-supplied filename or host-global `/proc/pressure/memory` as a fallback.
6. Create the packet socketpairs, set bounded send buffers, shut down the prohibited halves, and send only the recipient descriptors using SCM_RIGHTS. The grant echoes a fresh client request nonce and includes a fresh host lease generation, exact scope, and exact monitor parameters. Receive with `MSG_CMSG_CLOEXEC`. Close the host's temporary copies of the recipient descriptors after transfer.
7. Keep the enrollment control connection for lease liveness. After the finite grant handshake, unexpected client data or received descriptors are protocol violations. Peer/control disconnect, peer death, init/cell death, changed namespaces, changed scope/budget, owner replacement, failed identity reads, malformed requests or changed configuration revoke every monitor in the lease.

The Rust `host-owner` candidate now implements the accepted endpoint's kernel peer/proc/namespace authentication and generation owner. It takes the exact held cgroup, process pins, role namespace pins and executable SHA/file pin from trusted lifecycle code. Accepted-client authentication requires `SO_PEERPIDFD`; it has no numeric-PID fallback. All four real/effective/saved/filesystem UID and GID fields, ten namespace identities, process birth, executable identity/content, actual membership, and the peer's projected Reader root must match. The host process/namespace view and both retained lifecycle process identities are rechecked as well. Namespace, executable, proc and cgroup handles remain pinned.

This is not the complete enrollment factory above. There is no request/grant codec or Android grant client. `host-psi-owner` implements real registration and a producer, but its actual event path has not yet been exercised with pressure. `Monitor::Adopt` still assumes an independently authenticated grant. Its expected peer and expected scope must never be derived from an untrusted pressure-event record.

The authentication-only revision polls retained peer, owner, init, control and cancellation descriptors. The registration extension adds at most two real PSI descriptors to that same worker, rather than adding a thread per monitor. Peer death and unexpected control data revoke without a lifecycle CLI operation or a caller `refresh`. The poll interval is at most 100 ms and one quarter of the smallest supplied PSI window. The worker rejects a full-window progress gap or clock rollback, copies the exact original registration thresholds, and closes the lease on queue/send failure.

## Generation and revocation

A lease generation is a fresh 32-byte random value issued only after the kernel-backed enrollment checks. It binds the cell/init generation and one LMKD process birth. A restarted LMKD receives a new lease even if the cell cgroup inode is unchanged. A restarted cell receives a new lease even if an administrative path is reused. There is no reconnect to an old lease and no replay of queued records into a new receiver.

Revocation order is: invalidate the generation; stop accepting monitor events; remove the host's PSI descriptors from its poll set; close every host notification endpoint; close the host-owned PSI descriptors; retire the enrollment connection. All recipient duplicates observe closure. The supervisor must finish retirement before making a replacement cell generation available. A teardown that cannot establish retirement is a failed lifecycle transition, not permission to run two generations concurrently.

The implemented revocation worker owns a cancellation eventfd and uses a bounded poll timeout. Its sender-list mutex is released before socket shutdown/close, so lifecycle work does not hold that mutex across those kernel operations. No resource limits or cgroup memberships change. The worker never reads process scores, computes watermarks, selects victims, calls reaper, or signals a process.

`finish_retirement` requires actual worker completion and joins it; a timeout retains the handle and is not a successful retirement. Reference lifecycle integration must reject replacement until that result is true. `Drop` requests revocation but does not certify completed cleanup. As with all kernel I/O here, a userspace timeout does not prove every shutdown, close or metadata call is immune to a kernel-side stall. Real resource-pressure retirement controls remain required.

This is not a claim of instantaneous cancellation of a decision already in flight. LMKD must check a shared atomic lease-validity gate before every cell decision path, including the watchdog. The native `Monitor` object itself is confined to the main event-loop thread. Integrating the watchdog gate requires a separate review of its existing concurrency and r7 foreground-loss failure; no data race through `Monitor::active()` is acceptable.

## Notification, statistics and loss semantics

The host is the sole poller of each real PSI descriptor. It forwards only an actual `EPOLLPRI` result for the corresponding registered monitor. `EPOLLERR`, HUP, descriptor failure or a stale owner wins over `EPOLLPRI`. Do not issue a second poll as a supposed confirmation: the kernel event bit is consumable.

PSI notifications are coalesced event bits, not a lossless count of every stall. The relay sequence counts notifications the host actually observed. It cannot reconstruct kernel-coalesced events.

The kernel interface does not export the original trigger timestamp. A frame's timestamp is the host's monotonic **observation time**, so it bounds transport/queue delay, not the complete age of the original kernel event. The worker therefore wakes at an interval no longer than one quarter of the smallest configured PSI window. If its monotonic loop progress is interrupted for a whole existing PSI window, it revokes rather than stamping a potentially old `EPOLLPRI` as fresh on recovery. The implementation checks after metadata I/O, after poll and after send. Actual pressure/stall controls remain unqualified.

Each event packet is fixed at 128 bytes. The proposed host send buffer is set to 4096 bytes and its kernel readback must not exceed 8192 bytes; this bounds the configured socket buffer, not a claim that all kernel accounting costs total exactly 8192 bytes. There is no unbounded application queue or retry queue. `EAGAIN`, a short send or any send error revokes the lease. It never silently discards an event and claims healthy monitoring. `MSG_DONTWAIT` avoids waiting for queue space but does **not** prove a kernel operation cannot stall on a memory charge. Queue timestamps and the worker progress guard must detect delayed delivery; real pressure validation remains required.

LMKD drains at most 64 records per invocation, checks sequence continuity, and keeps only a current valid notification. It rejects unknown/malformed/truncated records and any ancillary data, closing unexpected SCM_RIGHTS descriptors. It rejects a future timestamp or clock rollback. A record at least one existing PSI window old is stale and cannot authorize a critical decision. No larger window is invented for the relay.

The original native candidate checked freshness only at entry. A real socket/clock negative control showed that an event could expire during I/O and still be accepted. A subsequent independent review found that the final health check could itself run after the completion clock, and that an event arriving during the call was compared with an obsolete entry timestamp. The current receiver samples after each valid receipt and after all final health I/O. The original source fails four completion-clock cases; the intermediate source fails the late-health and in-call-arrival cases. The current source passes both sets, including actual-future rejection with `Error::Timestamp`. These are real packet sockets with explicitly wrapped clock/I/O timing, not real pressure trials. The future LMKD decision hook must still check freshness after current Reader statistics; no decision hook has been applied to r5.

The notification is not a memory snapshot. On a validated event, LMKD still reads the original fixed-root `Reader`, verifies the current cgroup identity and coherent budget, and applies the unchanged PSI, reclaim, watermark, process-selection and protection policy. A critical event can consume r5's pending high evidence only through the existing real-critical path. The host never supplies replacement statistics or a kill recommendation. Cgroup counters and PSI are not atomically sampled by Linux; source consistency means the same pinned scope and current coherent budget, not a fictitious atomic timestamp.

On HUP, malformed input, scope change or revocation, integration must clear pending high evidence, cancel pressure polling, invalidate the lease gate, and refuse cell kills until a new authenticated lease has been established. This applies to the watchdog too. Do not silently fall back to host-global memory, the ACK compatibility endpoint, or a different cgroup.

## Wire layout

All integers are explicitly little-endian; no C++ struct layout is sent.

| Offset | Bytes | Field |
| --- | ---: | --- |
| 0 | 8 | `P4PSI01!` magic |
| 8 | 4 | Protocol version 1 |
| 12 | 4 | Medium=1 or critical=2 |
| 16 | 32 | Lease generation |
| 48 | 8 | Cgroup device |
| 56 | 8 | Cgroup inode |
| 64 | 32 | Canonical memory budget binding |
| 96 | 8 | Existing PSI window, microseconds |
| 104 | 8 | Existing stall threshold, microseconds |
| 112 | 8 | Strictly consecutive sequence, starting at 1 |
| 120 | 8 | Host observation `CLOCK_MONOTONIC`, nanoseconds |

The 32-byte budget field is a lossless tuple, not a hash: maximum at offset 0, high at 8, swap maximum at 16, 32-bit flags at 24, and encoding version 1 at 28. Flag bit 0 means unlimited high; bit 1 means unlimited swap. Unlimited values use a canonical zero numeric field. It binds the same five budget fields already used by r5 `SameBudget`, without adding a crypto dependency. The existing Reader still validates page-size and physical-memory constraints.

## LMKD integration points

These are proposed hooks, not modifications already applied to r5:

- `Reader::OpenPressureMonitor` remains the direct path for environments where the fixed projected root legitimately supports registration. An explicitly configured `relay-required` cell mode would enroll with the one fixed relay endpoint. An automatic fallback on EPERM is not acceptable.
- `init_mp_psi` supplies its exact existing level/stall/window. A relay endpoint must register `EPOLLIN` plus HUP/error handling with the native receiver, rather than treating a packet socket as a kernel PSI descriptor.
- Only `Status::Event` after validation may call the existing PSI handler with a nonzero event indication. Empty/stale/error records are never critical events. Current statistics still come from the Reader.
- `destroy_mp_psi`, initialization failure, monitor refresh and lifecycle teardown revoke the lease and clear high evidence. Failure after creating only one of two monitors closes every partial resource.
- A separate atomic lease gate is required for the watchdog and regular kill paths. The r7 foreground failure must still be resolved; this transport change does not explain or fix it.

## Local evidence and remaining controls

The normal receiver compiles as C++17 with `-fno-exceptions -fno-rtti`, strict warnings and no test-clock entry point. Its local object has no allocator imports. This proves the native component's userspace path has no heap calls; it does not prove kernel operations cannot stall.

The corrected receiver passes **62 transport/budget/clock/scope/FD assertions, four owned-peer-pidfd assertions, and five completion-clock semantic cases**. These numbers include setup checks. The pidfd controls create a socketpair inside an owned child, transfer an endpoint with SCM_RIGHTS, verify the exact live peer pidfd, then observe that same dead generation after normal exit and reaping. They do not use numeric `/proc/<pid>` identity shortcuts.

The first default C++ suite passed 55 transport assertions and then stopped at `socket(AF_UNIX, SOCK_SEQPACKET)` with local `EPERM`. That failed result is preserved. Its named-listener subtest was not rerun on Pocket4. The later Rust host tests below exercise a real named listener and complete host-side authentication through a different implementation; they do not rewrite that earlier result. The earlier r10 cloud PID/proc-namespace failure is also unchanged.

### Actual bounded Pocket4 authentication controls (stage 05)

The frozen `host-owner` source was built offline with `cargo build --locked --offline -j 1`, `-Ccodegen-units=1 -Dwarnings`, and actual `cpu.max=100000 100000` / `memory.max=536870912`. The build uses the exact `libc` and `sha2` dependency versions in its Cargo.lock, copied from the reference source lock. This is not a hermetic build claim.

Both arms passed:

- An ordinary owned host child is rejected for wrong expected UID, GID or executable, and an exited/reaped connection is rejected through its retained `SO_PEERPIDFD`. A normal host child is also rejected because its global cgroup projection differs from its bounded job membership. That required projection check remains enabled.
- An explicitly authorized short-lived host child first obtains a different mount namespace, makes all mount propagation private, then binds only its existing job cgroup read-only/nosuid/nodev/noexec at its own `/sys/fs/cgroup`. It creates no PID/cgroup namespace, Android process, cell or new cgroup, and never changes membership or limits. Trusted parent-held Child/pidfd/namespace handles supply expectations; no request supplies them. This permits a full authentication positive control and a real namespace-mismatch negative control.
- Authenticated leases prove explicit retirement, automatic peer-exit revocation without caller refresh, automatic unexpected-control-data revocation, third-slot rejection, old-generation refusal, and acceptance of normal scheduler-state changes. Every recipient duplicate observes HUP. Each revocation worker actually completes and joins.
- Owned children are reaped, descriptor count returns to baseline, the socket is removed, parent mount namespace/selected mount records/projected root/membership stay unchanged, and the runner has no remaining children. Owned memory high/max/OOM/socket-throttling events remain zero.

The first private-mount attempt stopped before authentication because the fixture incorrectly demanded exactly one mountinfo entry at an overmounted path. The corrected fixture uses `statx` on the open projection to select the actual visible mount ID. Actual evidence shows two same-path records, one matching visible ID, and a read-only cgroup2 projection. The failed attempt is retained; no read-only or identity gate was removed.

The ordinary arm reports seven PASS lines and the private arm thirteen, including setup/cleanup and shared cases. They are not twenty independent security scenarios. See `host-owner/host-ipc-public-summary.json` for the source/binary pins, actual checks and limitations. No PSI registration, pressure generation, Android integration or Main change occurred.

Run the local native component controls with a normal compiler:

```sh
g++ -std=c++17 -O2 -Wall -Wextra -Werror -Wconversion -Wsign-conversion -DDROIDLOOM_RELAY_TEST=1 pressure_relay.cpp test_pressure_relay.cpp -o test-pressure-relay
./test-pressure-relay --transport-only
./test-pressure-relay --owned-peer-pidfd-only
```

Running without a subset argument additionally requires the named-listener control. None of these commands register pressure triggers or run a cell.

Before any Main proposal, an owned Pocket4 canary must establish all of the following without changing Main limits or moving LMKD outside its pressure domain:

1. Verify the exact supervisor source/binary lineage and integrate the Rust authority/revocation owner and complete enrollment factory into that verified source. The current module is a reference-source candidate, not an installed-source patch.
2. Demonstrate that direct registration at the owned namespace root still fails with EPERM while host registration of only that exact root succeeds; prove parent/sibling scopes, symlinks and changed directory generations are refused.
3. Exercise the actual endpoint's PID/UID/executable/namespace/cgroup/time-namespace checks, peer exit/PID reuse, stale grants, partial registration, unexpected FDs, malicious requests and descriptor cleanup.
4. Generate real owned PSI notifications; independently read current statistics from the same scope. Verify no monitor event becomes a host kill decision and that exactly the configured thresholds are registered.
5. Delay the host worker, saturate the notification queue, retire the generation with queued records, and kill the owned broker/LMKD endpoints. Verify revocation, stale-event refusal, no leaked monitors and bounded cleanup.
6. Run the original cached-only kill gate: real notification/count, exactly one cached victim, live foreground/protected/sentinels, zero OOM, original admission/limits, complete Main framework fence, and empty owned cleanup. Preserve r7/r8 failures and keep r9/b099 distinct from r10/r5 and any later relay target.

### Actual bounded Pocket4 registration controls (stage 06a)

`host-psi-owner/registration-controls-public.json` records the real test on Linux `7.0.0-38-generic`. A new admitted job retained its original one-CPU/512-MiB boundary. The fixture pinned its four existing members before temporarily moving only those members into its own control leaf. It enabled child controllers only after satisfying the no-internal-process condition, created bounded target/sibling leaves, and restored the original controller state and membership afterward.

The target was a genuinely new cgroup namespace root. Opening `memory.pressure` after entering that namespace and writing a trigger failed with `EPERM`, before a read-only bind could turn the failure into `EROFS`. The host registered `some 70000 1000000` and `full 70000 1000000` against the exact same held target directory. Real parent and sibling scopes, old authority generation and changed budget requests were rejected before opening a pressure descriptor.

Four registered leases exercised explicit retirement, automatic peer-death retirement, generation replacement and a sealed monitor set. Each quiet period had zero observed/queued notifications. Worker completion was followed by zero target PSI descriptors, HUP on all recipient aliases, normal peer reaping, and socket removal. All four owned cgroup directories were empty and removed, every original job member was restored or observed naturally exited, parent limits/controllers/namespaces/projection were preserved, and all recorded memory-event counters stayed zero. No Android/private cell, Main change, allocation pressure or victim-selection test occurred.

Independent review also found and fixed a mutex-poison error path that returned without revoking old capabilities. The minimal revision's real poisoned-mutex/socket test passes; reverting only the helper to the old error branch fails precisely because the lease stays active. The complete original stage-05 source was not retroactively claimed to run that new test.

The existing listener still assumes a complete stable private path established by trusted lifecycle code. Its immediate-parent ownership check is not proof that arbitrary ancestor paths are safe. Production integration must retain the full endpoint directory chain and use descriptor-relative lifecycle operations. This scope limitation does not invalidate the owned private-directory tests.

Until the remaining event, integration and pressure gates pass, this directory remains **REAL_SCOPED_REGISTRATION_CONTROLS_PASS / PRESSURE_UNQUALIFIED / DO_NOT_DEPLOY**. The r4/b099 r7 foreground failure, r8 pressure abort and r5's missing real-pressure qualification remain unchanged.
