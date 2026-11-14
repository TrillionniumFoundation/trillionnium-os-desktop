# Runtime and namespace layout v1

This is the construction contract for the Rust `droidloomd`. The supervisor
implements the fail-closed transaction, emits the complete typed Linux
construction/reverse-teardown plan, and provides the executable Android
cell path. `droidloomd` retains the exact namespace child handle while
`droidloomctl` supplies idempotent lifecycle operations. Production user-ID
mapping, cgroup limits, seccomp, and complete packaging hardening remain later
work; the executable path does not claim those unfinished isolation layers.

## Read-only development inspection

`droidloom-supervisor development-inspect --spec <path>` checks the cell
specification, readable image magic, selected GApps hashes, override files,
writable-image metadata and endpoint types without root. It creates no files,
mounts, namespaces, network rules or Android processes. Permission-denied and
missing-input errors are failures; successful inspection does not prove boot,
complete filesystem integrity or isolation. `development-validate`,
`development-run`, and the private namespace entry still require root.

## Intended production identity

The mapping below is a design requirement, not an implemented preview guarantee.

One cell exists for one logged-in host UID. Its stable ID is `u<host-uid>`.
Android UID/GID `0..99999` maps one-to-one onto a dedicated contiguous
subordinate host range of at least 100,000 IDs. Android root is therefore an
unprivileged subordinate host ID, never host root or the interactive host UID.
Ranges must not overlap another allocation or cell.

## Namespaces

The cell receives new user, PID, mount, IPC, UTS, network, and cgroup
namespaces. Android `init` becomes PID 1 only inside the PID namespace. The
supervisor keeps a pidfd and host-side cgroup handle; process names and PID
scans are never lifecycle authority.

## Mount tree

| Cell path | Source/ownership | Required flags |
| --- | --- | --- |
| `/system` | activated package artifact | read-only, nodev |
| `/system/bin/init` | optional package-owned compatibility binary over the activated base | read-only, nosuid, nodev, executable |
| immutable partition file override | optional package-owned compatibility file at its original Android path | read-only, nosuid, nodev, executable mappings allowed |
| `/vendor` | activated package artifact | read-only, nodev |
| `/product` | activated package artifact | read-only, nodev |
| `/data` | per-user `data.img` raw ext4 filesystem | read-write, nodev, nosuid |
| `/metadata` | per-user `metadata.img` raw ext4 filesystem | read-write, nodev, nosuid |
| `/data/media/0/<collection>` | explicitly configured host-user directory | read-write idmapped bind, nodev, nosuid, noexec |
| `/proc` | private procfs | nosuid, nodev, noexec, hide host processes |
| `/sys` | minimal read-only projection/synthetic tree | read-only, nosuid, nodev, noexec |
| `/dev` | private tmpfs | nosuid, strict modes |
| `/dev/pts` | private devpts | nosuid, noexec, newinstance |
| `/dev/binderfs` | private binderfs | three named devices only |

An optional `gapps_dir` in the root-owned cell specification selects a derived
`product`/`system_ext` image pair before Android init starts. `system` and `vendor`
retain their normal sources. The add-on manifest binds all three base partitions
and both derived outputs to exact hashes, Android SDK and native architecture.
Its files and ancestors must be root-owned, without symlinks or group/other write
access. Missing or mismatched selected images fail startup. Omission uses the
base images; installing the optional package does not edit the specification.
Read-only Android image mounts detect raw ext4 or EROFS from the filesystem
magic, including the selected add-on images.

The first GApps activation refuses already initialized Android data. A marker
inside the cell-owned data image records selected packages, signers and manifest
identity. Changing signers/selection or disabling the add-on requires fresh data
or a suitable backup; images alone cannot roll back Google updates in `/data`.
Manifest changes invalidate only the selected Google applications' parser cache.
The runtime never deletes accounts or installed app updates as a side effect.

The supervisor builds the complete tree before exec. Android receives neither
`CAP_SYS_ADMIN` nor a general view of host mounts to finish construction.
Android-controlled system state remains confined to loop-backed filesystems.
Only explicit shared-storage collections may be writable host-directory bind
mounts. They map the host UID to MediaProvider's recorded app UID and the host
GID to Android `media_rw`, and are mounted
`nodev,nosuid,noexec`, and placed behind Android's ordinary emulated-storage
service rather than exposed as Android system state.

The host kernel must provide FUSE. The packaged `vold` recursively binds its
MediaProvider lower view so configured collection submounts remain visible;
both volume teardown paths detach the whole lower tree. A non-recursive bind
exposes the underlying empty mountpoint instead of the host collection.
The supervisor reads MediaProvider's UID once from the initialized data image's
`/data/system/packages.list`; it never guesses an app UID. The test collection
uses setgid directory inheritance so Android-created files retain the mapped
host group. MediaProvider's primary GID is also mapped to a reserved subordinate
host GID, satisfying Linux's creator-credential checks before setgid inheritance.
The temporary mapping helper exits before Android init starts;
the mounts retain the kernel's mapping reference. Initial Android provisioning
must have installed MediaProvider before shared collections can be enabled.

## Device allowlist

The initial device set is null, zero, full, random, urandom, tty/ptmx/devpts,
the standard FUSE node used by Android's private emulated-storage mount,
ashmem only if an AOSP compatibility audit still requires it, the three private
Binder devices, and exactly one configured DRM render node. No `card*`, KMS,
physical input, framebuffer, camera, media, USB, Bluetooth, modem, block, raw
memory, or host control node is allowed. The synthetic sysfs exposes the
otherwise-empty fusectl mount point but no host FUSE connections.

## Host paths

- package-owned: `/usr/lib/droidloom`, `/usr/bin/droidloom-*`, and
  `/usr/share/droidloom`;
- ephemeral: `/run/droidloom/cells/u<uid>` and the user's mode-0700 runtime
  directory socket endpoint;
- system state: `/var/lib/droidloom/images` and activation metadata;
- per-user Android data: a platform-owned directory containing `data.img` and
  `metadata.img`, retained on normal package removal and deleted only by
  explicit wipe; the containing host filesystem is never exposed to Android.
- per-user shared storage: an explicit allowlist of host-owned directories,
  each mapped to one top-level collection below `/storage/emulated/0`; an
  omitted list exposes no host directory.
- per-user application integration: managed `.desktop` files below
  `$XDG_DATA_HOME/applications` with `droidloom-` names, rendered icons below the user's
  hicolor icon tree, and reconciliation state below `$XDG_STATE_HOME/droidloom`.
  Only the unprivileged user service writes these paths.
- per-user window policy: user-selected initial geometry at
  `$XDG_CONFIG_HOME/droidloom/window-policy-v1.json` and automatically
  remembered stable sizes at
  `$XDG_STATE_HOME/droidloom/window-sizes-v1.json`. Only the unprivileged
  presenter and CLI read or write these bounded, versioned documents.

No source-checkout path may appear in a runtime mount or unit.
When selected, `android_init` must be a normalized absolute path to a regular,
executable package-owned file. The supervisor bind-mounts it read-only over the
immutable base's `/system/bin/init`; omitting it retains the base init.
Each `android_file_overrides` entry names a normalized absolute package-owned
regular file and a unique normalized target below `/system`, `/system_ext`,
`/product`, or `/vendor`. Existing targets must be regular files. A missing
leaf is allowed only when every parent already exists as a real directory in
the mounted partition; new directory hierarchies and symlink parents are
refused. Before applying overrides, the supervisor projects each affected
parent into a cell-private tmpfs, retaining original files and subdirectories
as read-only binds and preserving symlink text, ownership, and parent
permissions. It creates only the declared leaf targets and seals the parent
read-only. Held directory descriptors and disabled mount-path
canonicalization keep sibling binds attached to the original image objects.
The underlying partition is never written, and the projection disappears
with the cell mount namespace. All override files are bind-mounted read-only
with executable mappings allowed. `/system/bin/init` remains reserved for the
separately validated `android_init` field.
Each `android_runtime_directories` entry names a normalized, package-owned host
directory and a unique, non-overlapping target below the cell-private
`/droidloom` tree. The supervisor creates the target before entering Android
and bind-mounts the directory read-only with device and setuid semantics
disabled. These projections may contain executable compatibility helpers, but
they are not Android-writable storage and cannot target `/system`, `/vendor`,
`/data`, or another Android namespace.

## Network

Each cell owns a network namespace and one veth peer. Host policy assigns its
address, forwarding, DNS broker, anti-spoofing, and NAT/firewall objects under
a stable cell tag. Android `netd` may operate only inside the cell namespace.
Teardown removes every tagged host object even if Android is unresponsive.

## Construction transaction

Construction is fail-closed and rolls back in reverse ownership order:
reserve identity/cgroup, create namespaces, populate UID/GID maps, assemble
mounts and devices, create Binder contexts, create network policy, apply
resource limits, start init, then publish the per-user lifecycle handle. A
handle is published only after every prerequisite succeeds.

Teardown first refuses new launches, terminates the pidfd-owned namespace,
waits with a bound, kills the remaining cgroup if necessary, removes network
policy/veth, unmounts the private tree, removes runtime paths, and finally
releases the cgroup. Repeating teardown must be safe.

## Lifecycle readiness and progress

`running` means the namespace owner is alive. Android readiness additionally
requires `sys.boot_completed=1`, a running `droidloom-input-bridge`, the task
launcher executable, and the task-control socket. Public `droidloomctl start`
and `restart` wait for readiness; `--no-wait` and internal `--cell` orchestration
retain service/cell-only startup. `droidloomctl wait` observes readiness without
starting or restarting the cell. `status` reports the current observed stage.

Legacy lifecycle requests remain bare JSON objects with a single JSON response.
Interactive clients opt into progress with `{"request": <control request>}`.
The daemon sends newline-delimited `{"progress": "..."}` frames followed by the
normal response object. APK file descriptors still accompany the first request
byte and are accepted only for installation. UID authorization is unchanged;
boot observations are emitted only after authorizing the cell owner.

Boot waiting is bounded at 120 seconds, with short timeouts on readiness probes.
Task-launcher retries share a 120-second execution deadline; application catalog
and package-manager commands use 110 seconds. Timed-out subprocess groups receive
a forced kill after a short grace period. Clients enforce a 250-second wall-clock
request deadline, including queue time, even if progress or partial bytes keep
arriving. Socket writes are bounded, and a full accept queue fails promptly.
Client disconnection does not tear down Android. A timed-out client's operation
may still complete, so its error advises checking the result before retrying.

## Linux CPU inventory projection

The minimal synthetic sysfs exposes only the host kernel's `online`, `possible`,
and `present` CPU-list files through read-only, noexec/nosuid/nodev bind mounts.
It does not expose per-core controls, uevents or the complete host sysfs tree.
These lists report Linux topology, not a fabricated mobile model or a fixed CPU
count; cgroup quotas and CPU affinity remain independent and unchanged. Missing
or invalid source lists and failed read-only mounts fail the boot transaction
instead of silently advertising one CPU.

## Explicit system-as-root GSI layout

The cell specification accepts `image_layout: "gsi_system_as_root"` for a
verified GSI with `/system/product` and `/system/system_ext` inside the system
image. Omitting this field retains `split_partitions`: separate system, product
and system_ext images remain mandatory. There is no missing-file fallback.
Both layouts keep `image_dir/images/system.img` and the explicit raw ext4
`vendor_image`; a GSI cannot select the separate GApps image pair.

Metadata inspection, the auditable Linux plan and the actual namespace executor
consume the same explicit layout. Before exposing a GSI root, the executor
requires real internal partition directories and the exact `/product` and
`/system_ext` aliases. It creates equivalent relative aliases only in the
private synthetic root, preventing host-side absolute-symlink resolution before
chroot. File override targets below these aliases are mapped to their real
`/system` paths; duplicate targets through two names are rejected. Other
symlink-parent and read-only leaf-override restrictions remain in force.
Read-only ext4 image mounts include `noload`, keeping journal replay disabled.

This layout support does not qualify a new Android/framework/APEX/native bridge
cohort or a user-data upgrade. The caller must verify the exact image hashes,
platform/shared-UID signing compatibility and all selected overlays, then run
fresh boot, runtime and application acceptance. No image is rewritten by this
layout selection.

## Production user-namespace broker prerequisite

The owned-child primitive now creates its own fixed child with clone3 and an
atomic pidfd, binds its retained proc directory, start time and user-namespace
FD, and uses a nonce-bound ready/go channel. It strips inherited descriptors
and supplementary groups before entering a new user namespace, writes
exact lease-derived UID/GID maps with initial-userns CAP_SETUID/CAP_SETGID,
retains the original setgroups allow state, and checks the complete
readback before permitting its fixed child to adopt mapped credentials.
The child then parks; this primitive has no external PID-adoption or Android
execution interface. Exit is signalled and reaped through the held pidfd.
An unproven exit retains the exclusive lease and descriptor custody until
process death, while the durable reservation is never reclaimed.

The admitted entry now consumes an opaque HostAdmission that holds the actual
identity lease, complete bounded NSS/provider observations and live-namespace
seals. Its fixed owned worker runs with UID/GID 65534 and cannot issue authority.
Local identity grants, JSON diagnostics, plans and synthetic test fixtures
cannot construct HostAdmission. The fixed mapped keeper can create one owned
PID 1 with private PID, mount, IPC, UTS, network and cgroup namespaces.

Two immutable base-mount descriptors have a separate nonce-bound transfer.
The fixed PID 1 constructs an empty tmpfs root, separate fresh /data and
/metadata, validates the GSI layout, pivots away from inherited host mounts and
parks. No original account-data body is read or mounted by this stage.

A following single-FD DEV transfer accepts only the same tree's opaque
PreparedDevices. The fresh ID-mapped tmpfs has a 64 MiB / 16,384-inode bound,
nosuid/noexec, device access enabled, a 0755 root and exactly seven 0666 nodes:
null 1:3, zero 1:5, full 1:7, random 1:8, urandom 1:9, tty 5:0 and fuse 10:229.
The child rechecks the exact node set and guest UID/GID 0, attaches only at its
private /dev and closes all descriptors except its original control socket.
A second transfer, extra rights, a foreign tree or mismatched nonce is rejected.
No host device inode is bound, chowned or chmodded.

Both stages retain their real mount/loop and lease owners after any attempted
transfer. Teardown first proves PID 1's actual PIDFD reap, closes live-only
namespace FDs, then retires DEV and base resources, and finally reaps the keeper.
An unknown lifetime quarantines all remaining resources and the real lease.

These are construction stages, not a running Android lifecycle. Private controls
remain separate from production HostAdmission. Binder, delegated cgroups, complete runtime/APEX inputs, peer IPC credentials,
exec/seccomp and
normal daemon wiring require their own implementation and qualification.
Original-data mount authority remains closed. Existing development execution is
unchanged; a failed production gate never selects a development fallback.

## Private process-filesystem construction

The fixed owned PID 1 creates its proc fs_context in the actual private PID/user
namespace. A nonce- and SCM_CREDENTIALS-bound single-FD phase sends that context
to the initial-userns broker, which performs only a fixed detached fsmount with
RO, NOSUID, NODEV and NOEXEC. Before returning one mount FD, the broker checks
PROC type, all flags, only PID 1, and PID/user namespace identity against its held
objects. The child attaches it to its private root and repeats full verification.
It never retains or binds host proc. A separate fresh devpts instance uses the
mapped tty GID and only a relative private ptmx link.

The context and returned mount stay in the same TreeChild custody until actual
PIDFD reap; unknown exit quarantines the lease and all remaining descriptors.
The kernel does not automatically lock these flags on an SCM_RIGHTS transfer.
Android proc write/remount policy, runtime/APEX, Binder and exec/seccomp remain
separate gates. This preparation cannot report a Running cell.

## Original init security metadata

The runtime broker checks the held original init inode's `security.selinux`
value against the exact CP3A bytes `u:object_r:init_exec:s0` followed by one NUL.
Its `security.capability` attribute must be absent. The checks use bounded
descriptor reads and preserve the complete sealed file identity, including
ctime, before and after both reads. They run before mount preparation and again
when checking the live namespace or transferring the detached init mount.
Missing, truncated, oversized, different or unreadable labels are rejected;
an empty capability attribute is still present and is rejected. An unsupported
attribute operation does not prove absence.

These checks require preserved input metadata; they neither set a label nor
establish the active SELinux/AppArmor policy or the post-exec process domain.
The execution gate still requires independently implemented live MAC,
init/APEX activation, guest cgroup and final capability/seccomp contracts.
Ordinary xattr storage tests cannot construct that execution capability.
