# Private Android init relay barrier (implementation in progress)

This new DSO has one private ABI and no compatibility interposition. The existing SELinux compatibility library and its source are unchanged. The supervisor must pin the exact init, existing compatibility library, new barrier library, native LMKD and broker artifacts before enabling this path.

The opt-in constructor is limited to root PID1 with exact argv /init second_stage, DROIDLOOM_CELL=1, required=1, ABI=1, a private nonblocking SOCK_SEQPACKET FD, a nonzero 32-byte nonce and a bounded monotonic timeout. First-stage, partial/bad contracts, foreign credentials, stale/replayed phase, unexpected rights, peer PIDFD death, HUP or timeout fail closed. There is no pressure or PSI threshold operation in the constructor.

The actual current Pocket4 loader chain is independently captured in input-reference-04/report.json outside this source directory: main init d6905d43..., AT_SECURE=0, bootstrap linker b8f4ca47... and the existing preload b4da6c85... verified from real map_files descriptors. That proves the existing second-stage loader path; it is not execution evidence for this new candidate DSO. Android candidate compilation, real constructor execution and the full supervisor/domain/broker integration remain open.

Wire format is fixed 128-byte little-endian P4IBV1!!, ABI=1, kind at offset12, nonce at16. HELLO transfers 12 CLOEXEC FDs: domain root, init PIDFD, and pid/pid_for_children/mnt/cgroup/user/net/ipc/uts/time/time_for_children namespace handles. Its payload at48 is domain device,inode,memory.max,memory.high,memory.swap.max; count12 is at88 and all remaining bytes are reserved zero.

PROJECT carries exactly one O_PATH socket FD, actual device/inode at48/56, UID/GID at64/68 and mode0600 at72. The constructor binds only that exact socket to /dev/socket/droidloom-lmkd-psi and returns PROJECTED with the same identity. COMMIT must repeat that complete frame with kind4 and no FDs. After private environment/capability cleanup, DONE kind5 is the last send; the control descriptor is then closed before init main can start services. The barrier removes itself from subsequent LD_PRELOAD values while preserving the exact existing architecture-specific compatibility preload.

The supervisor must admit COMMIT only after the real broker's READY, finite precreated cgroup budget, exact Android init/executable/namespace identity and projection acknowledgment are all verified. Receipt strings and ordinary protocol controls cannot replace that production ownership proof.

protocol_controls.c uses actual owned children, Unix SCM_RIGHTS, PIDFD liveness, malformed messages, peer death with the control socket still held, timeout and a subsequent exec to check descriptor noninheritance. It has explicit collection and mount seams, performs no Android PID1, cgroup, namespace, mount, network or pressure action, and cannot qualify those missing layers.
