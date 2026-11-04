# Owned prefix stand-in transport

This is an independent host probe protocol. It is not the Android init-barrier protocol.

## Native HELLO

The packet is exactly 128 bytes, little endian. Reserved bytes must be zero.

| Offset | Bytes | Meaning |
|---|---:|---|
| 0 | 8 | `P4PX01!!` |
| 8 | 8 | Phase 1 |
| 16 | 32 | Nonzero 256-bit attempt nonce |
| 48 | 8 | FD 199 fixture-directory device |
| 56 | 8 | FD 199 fixture-directory inode |
| 64 | 8 | FD 201 probe ELF device |
| 72 | 8 | FD 201 probe ELF inode |
| 80 | 8 | Actual PR_GET_PDEATHSIG, required SIGKILL |
| 88 | 8 | Actual private PID, required 1 |
| 96 | 8 | Actual private PPid, required 0 |
| 104 | 8 | Probe CLOCK_MONOTONIC start, milliseconds |
| 112 | 8 | Independent native lifetime, 15000 milliseconds |
| 120 | 8 | Reserved zero |

Exactly twelve SCM_RIGHTS descriptors accompany HELLO: the target's own pidfd; ten namespace descriptors in the order pid, pid_for_children, mnt, cgroup, user, net, ipc, uts, time, time_for_children; and a duplicate of the actual inherited FD 200 owner pidfd. The receiving host compares the final descriptor to the exact retained Child, not merely to an arbitrary live outside-namespace process. The socket supplies real root SCM_CREDENTIALS; all received rights are atomically CLOEXEC and owned before any rejection. An unexpected SCM_PIDFD is also owned and closed before rejection.

The fixed inherited contract is control=198, fixture directory=199, exact unshare owner pidfd=200, probe ELF=201. The probe verifies its executable identity against FD 201 and seals all four descriptors CLOEXEC. It requires private root PID 1 and an outside-namespace live pidfd before sending HELLO. Every namespace descriptor is compared to the original live procdir view. New namespaces and preserved clock/user/cgroup namespaces are checked explicitly.

Command `E` is one byte and is accepted once. It forks an owned child which execs the same ELF through FD 201 in `--fd-check` mode with an empty environment. Success requires all four fixed descriptors to be EBADF in that child, exact wait status zero, and a phase-2 packet retaining the magic and nonce with bytes 48–127 zero. Command `Q` terminates normally. Malformed/unknown/replayed commands, channel fault and finite timeout fail.

## Inner-controller to outer-actor handoff

A separate private seqpacket carries the observed root-process identities, complete actual argv and namespace identities. It transfers exactly four capabilities: the inner controller pidfd, original unshare owner pidfd, original private PID 1 pidfd and a duplicate of the probe-control peer endpoint. The outer actor compares the kernel sender credentials with its exact retained Child, checks all live pidfd identities and keeps the fourth capability open throughout death observation. It never uses a process-name search or numeric unowned process signal.

The native HELLO must be less than two seconds old when each host layer accepts it. Death modes must finish their observation before ten seconds from that same start, with the actual clock namespace preserved. No post-HELLO owner poll or control-HUP fallback in the native loop may substitute for the kernel parent-death chain.
