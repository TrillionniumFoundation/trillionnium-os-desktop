# Droidloom threat model v1

These are security design requirements, not a claim that the preview enforces
every control.

The current preview still needs production isolation hardening. In particular,
requirements below for subordinate UID mapping, seccomp and signed distribution
must not be read as evidence of enforcement.

`droidloom-supervisor identity-inspect --spec <cell.json>` reads the actual
local subordinate-ID grants and checks a dedicated non-login principal against
NSS. It rejects short, overlapping, duplicate, or stale grants. It creates no
accounts, reservations, namespaces, or ID maps. The identity reservation API
keeps a root-owned durable cell/range/cohort/data binding and a separate live
file lock. Lease drop, process death, and expiry never reclaim that binding; a
partial record requires explicit reconciliation. This prerequisite is not yet
wired to an executing production backend. The owned-userns primitive now retains atomic clone3 pidfd/proc/ns custody,
clears inherited groups, preserves setgroups allow and verifies exact map
readback for its own fixed child. Its public production entry remains closed
until complete effective-NSS, active-namespace and host admission exist.
Private syscall controls do not bypass that gate or qualify Android execution.
Full namespace construction, idmapped data mounts, peer identity changes and
seccomp remain required before production activation. The development launch path retains its existing status.

## Security claim

The primary boundary is designed to contain an untrusted Android application
that has not escaped Android's application sandbox. Defense in depth should
also make a framework or cell compromise harder to turn into host compromise,
but version 1 does **not** claim VM-equivalent containment of a fully
compromised Android cell. The host kernel, selected DRM render driver, host compositor,
and `droidloomd` remain trusted computing base.

## Principals and trust

| Principal | Trust | Authority |
| --- | --- | --- |
| Android APK and native libraries | Untrusted | Android app UID, granted Android permissions |
| Android framework/cell | Partially trusted | Private namespaces, Binder contexts, delegated cgroup |
| Per-user presenter and catalog | User-trusted | Lifecycle requests and narrow host portals for that user |
| `droidloomd` | Host-trusted, minimal | Namespace/mount/device/cgroup/network construction only |
| Host compositor | Host-trusted | Display, input, shell, task, capture, and power policy |
| Image/package manager | Host-trusted | Signed immutable system content and explicit activation |
| Linux kernel and selected GPU driver | Trusted computing base | Shared execution and render-node ABI |

## Protected assets

- host filesystem content outside explicit portals;
- host UID identities and credentials;
- host routes, firewall, sockets, and other users' traffic;
- physical display/KMS, input devices, camera, microphone, sensors, USB, modem,
  Bluetooth, and power controls;
- other users' Android cells and `/data`;
- The host compositor's private control channels and compositor-owned buffers;
- package-owned immutable Android system content.

## Mandatory controls

1. Map Android IDs into a dedicated, non-overlapping subordinate range. Never
   map Android root to host root or the interactive user's host UID.
2. Create private PID, mount, IPC, UTS, network, cgroup, and Binder namespaces.
3. Assemble mounts and devices in the supervisor. Android receives no general
   host mount authority and no broad `/dev` bind mount.
4. Expose only the selected DRM render node and the explicitly configured
   graphics backend's bounded auxiliary devices. `kgsl_dma_heap` adds only
   `/dev/kgsl-3d0` and `/dev/dma_heap/system`; their drivers become part of the
   trusted kernel interface. Validate device identities and use private inodes
   so cell permissions cannot alter host nodes. DRM card/KMS and physical input
   nodes are forbidden.
5. Put Android networking behind a private veth and host-owned policy. Android
   `netd` never shares host route/firewall authority.
6. Authenticate the private compositor and lifecycle sockets with filesystem
   ownership plus peer credentials. Treat task/package identity sent by the
   Android side as untrusted until reconciled with the session service.
7. Validate and bound every message, string, object count, dimension, file
   descriptor, DMA-BUF plane, format/modifier, fence, and lifecycle transition.
8. Apply no-new-privileges and seccomp after construction; retain only the
   capabilities proven necessary for Android boot.
9. Keep system/vendor/product immutable and package signed. `/data` is the only
   normal mutable Android state.
10. Make teardown idempotent and host-owned. A dead or hostile cell must not be
    needed to release its cgroup, mounts, veth, Binder instance, or buffers.

## Boundary-specific attacks

- Binder: use a private binderfs instance and three private contexts; never
  expose host Binder devices.
- Denial protocol/DMA-BUF: reject truncated sequenced records, ancillary-data
  truncation, invalid plane counts, descriptor-role mismatches, overflows,
  unsupported format/modifier pairs, foreign devices, impossible dimensions,
  stale timeline points, and ambiguous ownership. Retain buffers until GPU/KMS
  completion.
- Portals: use typed, least-authority requests; pass individual descriptors
  instead of paths or host directory mounts.
- Image activation: validate schema/ABI and artifact hashes before an atomic
  version switch. Never execute hooks from an untrusted image.
- Network: host policy owns NAT/routing. Prevent spoofing outside the assigned
  veth and tear policy down by stable cell identity.
- Resource exhaustion: cap processes, memory, CPU, file descriptors, Binder
  allocations, surfaces, buffers, and queued messages at the host cgroup and
  protocol layers.

## Residual risks and escalation

Kernel, Binder, GPU, and shared-filesystem vulnerabilities can cross the cell
boundary. Android SELinux cannot install a private policy into a conventional
shared host kernel. Protected media, hardware attestation, and Play Integrity
are not supported claims. Workloads requiring containment after total cell
compromise must use a separately designed hardened VM mode.

Any new device service, host portal, privileged capability, shared namespace,
or protected-buffer path changes this threat model and requires a new version.

## Production construction descriptors

The namespace broker owns every child from atomic clone3/PIDFD creation and
never adopts a caller-supplied PID. The immutable-base pair and the private DEV
descriptor use separate fixed phases over the original nonce-bound control
socket. Raw child code accepts the exact descriptor count and rejects ancillary
truncation, foreign phases, wrong nonce and substitutes. After each private
mount step it drops every descriptor except its control socket.

The initial DEV stage contains only newly created null, zero, full, random,
urandom, tty and fuse inodes on a bounded ID-mapped tmpfs. It exposes no host
device inode, Binder context, KMS/input node, kmsg, console or loop device.
Additional device and runtime roles require independent trusted inputs and
qualification. A parked constructor cannot publish Android Running status.

Actual PID 1 reap and closure of live mount-namespace references precede device
and base-mount retirement. Ambiguous exit or transfer retains the entire owned
tree, remaining mount descriptors and identity reservation. Test-only fixtures
are absent from normal binaries and cannot construct production admission.

## Native terminal-probe audit boundary

The selected normal glibc isatty() issues TCGETS2 (0x802c542a).
Systemd 259.9 calls it while reading configuration lines. Its isatty_safe()
returns false for both EACCES and ENOTTY; retaining the SELinux denial
does not change the normal non-terminal result. R13 captured 4,373 such
file denials across 28 concrete source/target pairs. Audit loss means this
is a count of retained events, not every attempted operation.

ubuntu-native-manager-lifecycle.cil suppresses only the 0x542a extended
audit bit for those 28 pairs. It adds no access. Each pair has no raw base
file ioctl permission and no pre-existing extended-permission rule in the
admitted baseline. This matters because introducing an xperm table on a pair
that previously had generic ioctl access could restrict unrelated commands.
Character devices, sockets, inherited descriptor use, and other ioctl audit
bits retain their existing rules. SELinux's ioctl table matches the low
16 bits; it cannot distinguish alternate high direction/size encodings of
0x542a. Those operations remain denied.

The selected kernel's security/selinux/ss/services.c (SHA-256
a3dc132fceec9f42a8d1728cef1b45685d5d2e0f3b5dcb812bec4049c5c19f67)
indexes extended DONTAUDIT entries independently of base access.
security/selinux/avc.c (SHA-256
88c0e2ebcdcb071db42357e5baf753e87fa44c7d81c5abff2ae5d37b696de813)
keeps the base denial and then applies the extended audit decision.
Normal systemd source pins are src/basic/fileio.c
691d77b7655f522473d2c0baba78f285bfe5ff344e3ebd4357b63a7b87402d86
and src/basic/terminal-util.c
29d7fcb01a7dfcd1cb03b69772a4bedd98021881f1d3e46378f0abb4529767d1.
The actual normal glibc 2.43-2ubuntu2.7 libc.so.6 is 2,190,608 bytes with
SHA-256 9941dc28e68bc5fd788d9cd024c69e68c791d63799e7538a97b6040dd9f50fb6;
its isatty syscall loads the full command above and returns zero on error.

The normal strict compiler verifies the final binary export against fixed
commitments from the actual R13 binary (1,378,147 bytes,
334f85991aa8b821efbd8ee793083d0031ff1ffbb9bddac7e928c5fa2092d42c)
and its retained export (11,026,119 bytes,
87199686510833e1f2424e12faa9510b900646adf3ad89628ebc68899be50e39).
The proof rejects duplicate, non-concrete, missing, or expanded audit rules.
It also checks all 28 raw base/xperm tables.

The same comparison explicitly accounts for two separately reviewed normal
startup fixes: the policy loader's access to PID 1's proc directory
getattr/search, file getattr/open/read, and link read, plus the service
executor's ioctl bit and sole FS_IOC_FSGETXATTR (0x581f) operation on
p4_linux_logind_state_t directories. Their seven raw bits are zero in the
baseline and must be present in the final concrete rows. Only those seven
bits and that one directory xperm are subtracted for comparison.

Base allow rows are merged by literal source, target, and class with sorted
permission tokens, so libsepol's merging of an existing row cannot change the
meaning of the comparison. Every other non-audit AST, including complete
conditionals, constraints, transitions, and type/attribute membership, remains
bound to the old baseline. Original audit rules remain exact after removing
the 28 additions. The expected hashes are source constants derived from the
old actual artifact; candidate output cannot create an expectation. A later
independent policy change needs an explicitly reviewed composition.

This is a source and policy-structure boundary. Successful compilation does
not prove that the selected kernel has loaded the new policy or that a later
boot retains complete audit evidence.
