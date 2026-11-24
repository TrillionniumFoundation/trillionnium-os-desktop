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

The supervisor builds the selected private tree before exec. The production
CP3A entry uses the explicitly selected subordinate-user-namespace capability
profile described below. Its `CAP_SYS_ADMIN` is confined to namespaces owned by
that subordinate user namespace; Android receives no initial-user-namespace
authority or general view of host mounts.
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

The fixed owned PID 1 opens its proc fs_context in the actual private PID/user
namespace. The existing private control retains phases 24/30/31 and creates
its context in that child. The Android activation role selects separate
phases 64/65/66 from its already authenticated DEV role; it sends the original,
still uncreated context through one nonce- and SCM_CREDENTIALS-bound FD.
No supplied path, selector, GID or external PID chooses either role.

The initial-userns broker authenticates the original child, held PIDFD, map,
namespace custody and fs_context shape before configuring that same context.
For the Android role it resets `gid` to the original lease's mapped host
readproc GID, sets `lsm_context=selinux`, then issues CMD_CREATE and the fixed
detached fsmount with RO, NOSUID, NODEV and NOEXEC. The kernel retains the PID
namespace selected at fsopen. Its proc creation applies the numeric GID in
the creator's current user namespace, so this initial-userns creator must use
the mapped host value; the child's earlier numeric 3009 would be incorrect.
The complete mount inventory must contain exactly one SELinux selector and
the mapped GID. The separate private control rejects any selector option.

Before returning one mount FD, the broker checks PROC type, all flags, only
PID 1, and PID/user namespace identity against its held objects. The child
attaches it to its private root and repeats full verification. Neither role
retains or binds host proc. A separate fresh devpts instance uses the mapped
tty GID and only a relative private ptmx link. The selector changes this proc
superblock's legacy LSM context view; it does not reorder the host LSM stack
or supply the independent host MAC preflight.

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

## Concurrent production property observation

The original owned init's boot property is read through the held private
property-area file. Bionic publishes new trie nodes after reserving their
storage and publishes mutable values with each property's dirty bit and
serial. Its global update serial belongs to another area; the boot context's
header serial alone cannot prove a consistent copy.

The reader checks the allocation header around the copy and retains a value
parse error until the actual leaf serial and file identity have been rechecked.
A changed snapshot receives at most three immediate reads, then remains
`Updating` under the existing boot deadline. Dirty values never become Ready.
Identical malformed trie snapshots and stable invalid values still fail;
owner, mode, inode, size, ABI and traversal bounds remain mandatory. These
read retries neither start Android nor issue execution admission.

## Fixed application query inputs

A prepared runtime may select the command layout (`cmd` and `toybox`) or the
Contacts layout, which adds both `app_process64` and `content.jar`. Selection
comes from the verified manifest and stays typed through descriptor transfer,
parent projection checks and the child mount consumer. The Contacts transfer
has a distinct fixed protocol phase and requires the same three descriptors as
the command layout; neither a pathname nor a caller-provided role list is sent.
The legacy readonly runtime retains its two-descriptor transfer. The explicit
production activation layout below adds its three fixed writable roots.

The private query root is an owned read-only, nosuid, nodev tmpfs. Both consumers
require the complete selected leaf set, mapped root ownership and bounded
regular files. Executables use mode 0555. The Contacts JAR uses mode 0444 and
its dedicated `droidloom_provider_jar` label; the app process uses the separate
`droidloom_provider_exec` label. Ordinary command labels do not gain Contacts
execution permissions. The child checks exact labels and absent capabilities,
while the parent retains each original inode and verifies the same mount and
complete identities after projection. Partial Contacts inputs, extra leaves,
symlinks, hard-link aliases and an executable JAR are rejected.

These construction checks preserve source-image bytes and resource custody.
They do not qualify Android startup, provider authorization, Contacts results
or upgrades of retained user data; those need acceptance in the final runtime.

## Original activation owner and scoped final capabilities

The production constructor prepares the listener on the original fresh DEV,
before idmapping and descriptor transfer, with the same live MAC and namespace
owner. Its `MountActivationDev`/`ActivationDevReady` protocol is distinct from
the private seven-device probe. Fresh DEV contains exactly the seven devices
and `socket/droidloom-linkerconfig`; the directory is 0755 and the single
listener inode is 0600. The same directory, socket inode, kernel `SO_COOKIE`,
mapped credentials, MAC observation and retained server FD remain required.

The executed stage requires an actual `ExecutedInitWitness`, with the original
PIDFD, nonce, held proc identity and executable. It uses a separate complete
DEV observation: a bounded descriptor-relative traversal records every inode,
mount ID, file type, mapped owner, symlink target and metadata generation.
Device bodies are not opened and symlink targets are not followed. Two complete
observations must agree. Every later listener revalidation compares the full
inventory, and any new or replaced entry invalidates that observation. Only
the original DEV, devpts and Binder filesystem mounts may be traversed. The
complete prepared runtime mount inventory and existing namespace checks remain
in force; this does not accept an init-created mount namespace or a new mount.

The owner coordinator now consumes the original listener and selected runtime
trampoline/original-linkerconfig inputs. It authenticates the actual peer and
runs the existing bounded broker protocol, retaining the real command exit
and retirement evidence on the same tree owner. The command receives at most
30 seconds and cannot extend the original 120-second preparation deadline.
An error retires that same tree; unproven retirement retains its resources in
the existing quarantine. Neither a socket connection nor a zero process exit
alone constructs Android execution admission.

The production activation layout transfers five fixed descriptors, in order:
readonly runtime image, original init, fresh APEX container, fresh linkerconfig
container and a separate fresh bootstrap-APEX container. A selected query
layout adds its sixth descriptor. `MountRuntimeBootstrapActivation` (60) and
`MountRuntimeBootstrapActivationContacts` (61) are distinct protocol phases.
The earlier 58/59 input layouts retain exactly their two activation roots and
four/five descriptors; neither those nor the readonly two/three-descriptor
phases admit the new root. Each receiver rejects a phase/arity mismatch and
verifies the original transferred inodes before reporting `RuntimeReady`.

The initial-root broker creates three separate detached tmpfs superblocks and
labels only their fresh root inodes. It requires the original CP3A directory
labels `u:object_r:apex_mnt_dir:s0` and `u:object_r:linkerconfig_file:s0`, with
the original terminating NUL, and absent file-capability attributes. All roots
are 0755 and receive the exact same admitted user-namespace idmap. `/apex` and
`/bootstrap-apex` each use the original `apex_mnt_dir` label and are each
bounded to 64 MiB and 16,384 inodes; `/linkerconfig` is bounded to 16 MiB and
4,096 inodes. These are implementation resource limits, not claims that a boot
has completed within them. All three mounts are writable, nosuid, nodev and noexec;
actual executable APEX payloads need separately verified readonly submounts.
The original runtime-image containers must be empty and remain readonly.
The bootstrap target must also be the empty original image directory before
its projection; it is not a new runtime-image member.

This third root is required by the original CP3A init, SHA-256
`9f69cc83a88db5f8533014cfea5ad9ea8e0454120335329aec27f8d65b2a9537`.
Its actual `.gnu_debugdata` identifies `SetupMountNamespaces`; disassembly of
that original executable shows a recursive bind from `/bootstrap-apex` to
`/apex` at `0xf11e6` after creating the default mount namespace and returning
to the bootstrap namespace. The actual `BindMount` implementation at
`0xf1590` passes source then target to `mount` with flags `0x5000`. Leaving
`/bootstrap-apex` on the readonly image therefore replaces the fresh writable
`/apex` view with a readonly directory. The additional root supplies the
required writable source without changing init, system/APEX bytes or the
original `ro.apex.updatable=true` property. Prepared-runtime observation still
does not admit that subsequent namespace or bind transition; those need their
own exact original-init observation.

The live MAC preflight checks this operation against the same loaded-policy
AV sequence as its other decisions. The broker must have the tmpfs source
directory `relabelfrom` permission and the two original destination directory
`relabelto` permissions, plus the corresponding tmpfs filesystem association.
The check also requires denial of broker writes or relabels to files carrying
either label, denial of relabelling those destination directories away again,
and denial of host-role directory mutation. A policy change between decisions
invalidates the entire check. This does not alter or load a policy.

The historical R9 component source has SHA-256
`3e95142c899c2866ade2435b6984489aa7f26fd9d81010a8a9e7612226eee295`; its compiled
policy has SHA-256
`e30a63f7c4665a3a2a72495de18693cbcc4eca0c0e8c41e1ed1d0da244debf8b`.
That source lacks the broker's two destination-directory grants. The four-rule
`runtime/droidloom-supervisor/policy/activation-roots.cil` is an additive offline
input for those directories and their tmpfs associations. It grants no file,
host-role, process-transition or capability permission. It is not a standalone
policy, a policy installation, or evidence of the currently loaded kernel
policy; the complete composed policy still needs its existing validation and
the actual same-epoch kernel checks.

The child checks empty membership, fixed labels, ownership, distinct tmpfs
instances and exact capacities before and after attachment. The parent verifies
the entire mount transition, including every unchanged preexisting mount, and
retains the actual new root inode/mount custody until original-tree retirement.
Later directory contents may change inside these writable roots; their root
identity, owner, mode, labels, flags and capacity may not. A new bind mount or
init-created mount namespace still needs its own transition provider. This
removes the previous readonly-container obstacle to original init's
`mkdir /linkerconfig/bootstrap`, `mkdir /linkerconfig/default` and initial
`ld.config.txt` writes, without treating those writes as successful activation.

The runtime manifest may explicitly select
`execution.scope = "android_cp3a_scoped_capabilities_v1"`. Production requires
this selection, the actual activation inputs and the native-v2 runtime input
contract. The selection is accepted only for these exact original bytes:

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| Official CP3A system image | 2,294,853,632 | `dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4` |
| Original `/system/bin/init` | 2,934,488 | `9f69cc83a88db5f8533014cfea5ad9ea8e0454120335329aec27f8d65b2a9537` |

The fixed profile in `production_execution_profile.rs` contains the 23 explicit
capabilities requested by the original system and APEX init scripts plus
`SETPCAP` for init's child-service capability transitions. It selects
`CHOWN`, `DAC_OVERRIDE`, `DAC_READ_SEARCH`, `FOWNER`, `FSETID`, `KILL`, `SETGID`,
`SETUID`, `SETPCAP`, `NET_BIND_SERVICE`, `NET_ADMIN`, `NET_RAW`, `IPC_LOCK`,
`SYS_CHROOT`, `SYS_PTRACE`, `SYS_ADMIN`, `SYS_NICE`, `SYS_RESOURCE`, `MKNOD`,
`AUDIT_CONTROL`, `SYSLOG`, `WAKE_ALARM`, `BLOCK_SUSPEND` and `PERFMON`.
No caller-supplied capability mask is accepted. An altered system or init
requires a separately implemented profile; changing a version string cannot
select this one.

The execution selection also requires all 38 original APEX input records in
the fixed sorted order. `production_apex_input_profile.json` binds each module
and version to its exact system container name, whole original APEX and whole
payload byte counts and SHA-256 values. The producer and consumer share this
same profile; omission, reordering, extra modules, substituted versions and
mixing any of the three byte layers are rejected. These records came from the
same complete official image capture, SHA-256
`1c1ff9866f5828990abb71884720c1d3aa6cc35eccf1ff0950c658ce52d2939a`, and all 114
source bodies were independently reread with stable complete file identities.
There are 37 ext4 payloads and one 69,070,848-byte EROFS payload for
`com.android.virt`. The fixed profile retains that distinct filesystem rather
than silently dropping it or routing it through an ext4-only provider. These
byte-lineage checks do not constitute AVB verification, mounted payload
observations, successful original apexd execution or Android admission.

`production_apex_archive.rs` additionally reads each held original archive,
hashes its complete body and the complete stored payload, and checks the ZIP
central and local records. Only its opaque result can supply the loop's
payload offset and length. All selected originals have their stored payload
at byte 16,384; duplicate entries, compression, encryption, data descriptors,
overlap and mismatched sizes are rejected. The original filesystem magic and
the bounded AVB footer, vbmeta and single SHA256 hashtree descriptor are read
from that same window. Parsing these fields does not verify an AVB signature.
The original apexd still owns its cryptographic verification and activation
database; a broker cannot substitute a hand-written `apex-info-list.xml`.

The runtime guard can prepare an actual readonly loop for each of the ten
uncompressed builtin APEX files. It compares the same init's fixed
`/system/apex/<original name>` inode with the member opened from the already
admitted system mount, rejects a separate mount under that directory, and
checks the original root:root 0644 metadata, complete `system_file` xattr and
readonly/nosuid/nodev filesystem. This retains the actual guest-visible source
path instead of substituting a host copy. The provider requires the same live
init, execution profile, loaded MAC policy and runtime owner; it retains the
source in that owner's existing reservation before `LOOP_CONFIGURE`. No loop
or control descriptor is exported to Android. Retirement checks the held
device, backing inode, exact offset, exact length and readonly/autoclear flags,
then requires kernel `ENXIO` before releasing custody. These APEX consumers
retire before the original base image can be released.

Those ten builtin loops now use a fresh private detached tmpfs and finite
device aliases. The private filesystem is 0700, limited to 64 KiB and 64
inodes, with nosuid/noexec and devices enabled. It is never attached under a
host or guest pathname. Its fixed directory, control node and loop nodes
must receive the separately defined automatic SELinux creation contexts;
an inherited fscreate override, unexpected directory member or missing label
is rejected. Existing host device labels are not changed. Actual sysfs
identifies each bounded free loop device, and only GET_FREE, CONFIGURE,
GET_STATUS64 and CLR_FD are used. Every operation checks the original current
MAC epoch and exact held inode before and after the real ioctl.

The original MAC provider and original production selection are retained as
one immutable, same-thread owner from their first acquisition. Preparation,
execution and runtime cleanup share that exact pair; neither object is
reacquired or rebuilt from a digest. Runtime resources receive the pair before
any private-alias mutation. Whole-image mounts retain their existing separate
source role, while builtin APEX publication accepts only the opaque private
device and its fixed archive index.

The pool records fresh, creating, live, retiring and retired phases. Only the
exact never-mutated state with no pool, rows or retirement records can use
the empty cleanup path. A missing context, interrupted constructor, wrong
thread, changed epoch or unproven device lifetime retains custody. Successful
device retirements remain recorded across a later failure, and the original
pool is borrowed until its complete retirement succeeds. These are resource
ownership and actual syscall rules; they do not qualify original apexd,
provide an AVB signature verdict, or complete Android execution admission.

The builtin publication backend creates the actual ext4 or EROFS filesystem
from that owned loop and applies the same admitted idmap. Its policy is
readonly, nodev, dirsync and noatime, matching the original apexd mount call
at `0x64be4`; nosuid and ext4 noload are explicit container restrictions.
The ten original uncompressed manifests have no true protobuf `noCode` field,
so these particular payload mounts remain executable. The source profile and
opaque archive witness fix the role; callers cannot supply flags, an offset,
a filesystem type, a module name or a target path.

Publication currently requires the original bootstrap namespace. Both the
actual `/bootstrap-apex` and the actual `/apex` must resolve to the third
originally held fresh root inode, through distinct mount IDs. This qualifies
the specific bind performed by the original init without accepting a changed
mount namespace or relaxing the fresh runtime inventory. The only target is
the compiled `/apex/<module>@<version>` directory. It must already exist, be
empty, have the mapped root owner, mode 0755, the original `apex_mnt_dir`
label and no file capabilities, and remain on that exact private tmpfs.

The mount operation runs in a short-lived broker helper created with an
atomic clone3 PIDFD and no shared VM, file table or filesystem state. The
runtime row holds the PIDFD before releasing its private start barrier. Before
clone, the original creator also opens its own `PIDFD_THREAD` and requires the
actual kernel PID/TGID response to match. The child installs parent-death
SIGKILL, retains only the four fixed descriptors, that creator-thread PIDFD
and its private result channel, then sends READY. Only the same original
creator may consume that actual READY and release the child. This ordering
covers death of a creator that is reparented inside a still-live thread group;
PIDFD polling alone would not cover a group leader whose exit remains delayed
by other threads in Linux 6.18. The child additionally polls the held creator
descriptor before its deadline and mount stages. After release it sets NNP,
enters only the pinned guest mount namespace,
sets root and cwd to the held guest root, then invokes `move_mount` with both
empty-path flags. It never enters the guest user namespace or executes guest
code. Normal setns and mount MAC checks continue to apply. Only the helper
retains initial-namespace authority; Android receives none of its descriptors.

A successful syscall result is accepted only with the actual original-parent
PIDFD reap and a matching fixed result packet. The parent then reopens the
fixed guest target and requires the same payload inode, actual mount ID,
filesystem, idmap owner and flags. Timeouts and errors retain the helper and
mount references in the original runtime guard. Retirement kills/reaps only
the held helper PIDFD, closes the retained guest namespace and filesystem
views, then requires the exact loop to become unbound. Ordinary tests actually
create and reap the helper for invalid-input and unreleased-barrier controls,
and observe real SIGKILL/reap when its original creator thread exits while
the rest of the process remains alive;
they do not perform a privileged publication or claim Android execution.
Completion also checks the original absolute deadline before consuming a
queued reply and again after validating the actual child exit. A caller
cannot extend that deadline. A result that has already arrived and been
reaped is still rejected if acceptance occurs too late; the same owner
retains the actual retirement record.

The creator-death control waits for real PIDFD `POLLIN` within its original
short retirement bound: Linux clears `clear_child_tid` and wakes
`pthread_join` before `exit_notify` publishes the state needed by PIDFD poll.
Returning from the userspace join is therefore not treated as a kernel exit
observation, and the exact helper SIGKILL/PIDFD reap remains mandatory.

The normal original-init exec handoff now installs an additional fixed
seccomp notification filter and transfers its single real listener through
phases 62/63. The parent verifies the original nonce, SCM credentials, PIDFD,
proc inode and actual listener file operations, then stores it in the same
tree before acknowledging. The raw child closes its local listener before
the acknowledgement and exec. Neither the fresh runtime inventory nor the
existing global-operation filter is relaxed. The new filter covers classic
mount/unmount, namespace transitions and the loop, block and device-mapper
ioctl families; ordinary file I/O and Binder ioctls retain their native path.
A notification alone supplies no source, executable or mount authority.

Notification receipt runs in a separate fixed broker child because Linux
6.18 `NOTIF_RECV` may block after a cancelled poll wakeup even on a descriptor
marked nonblocking. The parent holds its atomic PIDFD before the same
post-PDEATHSIG READY/release barrier. The child retains only the listener,
creator-thread PIDFD and private channel, then installs a second fixed filter
allowing only that listener's RECV, sending to that channel and exit. The
original parent's absolute deadline and actual kill/reap bound the ioctl.
Result bytes must agree with its actual PIDFD exit, and the original listener
must validate the still-pending kernel notification ID. Only one pending
operation is held. This transport currently exposes a real negative errno
reply. Any unresolved receive or send failure latches retirement-only state;
a new time budget cannot retry past a request whose receipt is uncertain.
The absolute deadline is checked again before a completed result or pending
request is accepted, including a result already queued and actually reaped.
The transport exposes no successful-return or native-CONTINUE shortcut.
Ordinary
tests observe a real trapped ioctl, the exact denial reaching its task,
expired ID rejection, idle-RECV timeout/reap and a real SIGSYS for an unrelated
receiver syscall. Final retirement additionally requires the actual filter's
POLLHUP after the original tree is reaped, proving no task users remain.

The backend still needs the original apexd request dispatcher and a
default-namespace transition witness. It must serve the real apexd mount
request with the real backend result. The original executable remains responsible for AVB
verification, its active database and its generated `apex-info-list.xml`.
The historical R9 MAC component additionally lacks required broker capability,
filesystem mount, target-directory mounton and device operations. A private
libsepol query of the exact historical bytes observes those denials; it is not
evidence of a loaded host policy. The actual fixed device labels and finite
ioctl permissions must be part of the reviewed current policy composition.

The other 28 inputs are compressed CAPEX containers. Their writable
`/data/apex/decompressed` outputs cannot enter this builtin provider, even if a
hash or pathname matches. They require a separate immutable-output and
same-path provider. Original apexd syscall mediation, actual readonly
device-mapper ownership, mount publication, and the exact namespace transition
observation are still required before this block provider can become a real
APEX activation. Premounting payloads alone cannot complete the original
bootstrap: the selected original `--bootstrap` code does not populate its
activation database from an existing mount inventory.

Before changing capabilities the raw child requires PID 1, parent PID 0,
root UID/GID inside the selected namespace, no supplementary groups, NNP=1,
securebits=0 and the original SIGKILL parent-death signal. Complete actual
procfs UID/GID maps must each contain one subordinate extent and must not map
namespace root to initial-namespace root. Kernel `NS_GET_USERNS` observations
must show that the mount, PID, network, IPC, UTS and cgroup namespaces are all
owned by this same subordinate user namespace. Existing parent lease and
original held-namespace checks still apply.

The child rejects unavailable selected bounding bits and an unknown capability
ABI, clears ambient capabilities, removes every unselected bounding bit and
sets permitted/effective/bounding to `0000005c49ac75ff`, with inheritable and
ambient both zero. It reads all five sets back and rechecks NNP, securebits,
parent-death signal and namespace ownership before arming the existing MAC
stack and seccomp filter. Securebits remain zero so original init's ordinary
setuid and ambient-capability child-service transitions are possible. The
post-exec observer must also retain the opaque exact-image runtime profile and
observe the same five masks, NNP=1 and filtering mode 2 on the original held
proc descriptor.

These checks do not grant initial-user-namespace operations. A capability
whose requested operation is checked in the initial user namespace still
cannot authorize that operation here, and the independent MAC/seccomp layers
remain mandatory. Root services without explicit capability declarations are
bounded by this profile as well. Successful boot and their required behavior
must be established by actual runtime acceptance.

Remaining execution contracts include the actual original-init APEX payload
and linkerconfig bind-mount transitions, the original trampoline projection,
default-mount-namespace transition, and guest cgroup/task-profile acceptance.
The complete `VerifiedExecutionContracts` type remains uninhabited until those
providers exist. Input declarations never construct execution admission.

## Fixed original-linkerconfig input production

The runtime-inputs adapter can select
`activation.scope = "cp3a_original_linkerconfig_inputs_v1"` with complete held
`FileRef` records for `original`, `trampoline` and `build_provenance`. The
explicit CP3A execution selection is also required. The producer emits the
consumer's `activation` declaration only after checking the exact original
runtime APEX payload and reading `/bin/linkerconfig` from that filesystem with
the fixed verified debugfs tool. That whole body must equal the separately
held original ELF. Original label bytes are extracted and its entire xattr
inventory must show the exact linkerconfig label and no file capabilities.

The original linkerconfig input is 512,120 bytes, SHA-256
`40105456e35de393c382d5ec9794a2cd30370291a0502e58bb24d6ae2b417ede`, with actual
interpreter `/system/bin/linker64`. Its source is the 11,452,416-byte runtime
APEX payload, SHA-256
`f97a0b03fb4b5dc91ddc71b02fc1f9831749d4a2e3f7cd6db47e3378f31a6345`.

The fixed freestanding trampoline is 24,384 bytes, SHA-256
`71ea5a2f70f4674ff2028dcdfe2ca6ee0d5ab1968ec21c5a3b0ee7be4d555e70`.
It was built in two distinct directories with identical output, Rust 1.93.0
and that toolchain's own `rust-lld`. The Rust channel manifest SHA-256 is
`beb6ba4e41c84e9c11c80e6804a007497d0c8ba0810cd403fabc8f4a9c45b1f8`.
The exact sources are `linkerconfig_trampoline.rs`, SHA-256
`d9368ae085d216091e2228a01206309b4e58022087115001a3744fb2f0a51e15`, and
`production_activation_protocol.rs`, SHA-256
`75a6c01c9e7f482df64931f23c0219251312fa2afe15fd2e055a72ac196f9db3`.
An ordinary test hashes those actual current source files, so a source change
requires an explicit new build and pin. The pinned ELF has no interpreter,
dynamic segment or writable/executable load segment; actual invocation with
invalid arguments exits 126. This refusal is not a successful activation test.

The reproducible compiler settings are edition 2024, target
`x86_64-unknown-linux-gnu`, crate name `droidloom_linkerconfig_trampoline`,
panic=abort, opt-level=2, codegen-units=1, debuginfo=0, strip=symbols and
relocation-model=static. Select the pinned toolchain's `rust-lld` with
linker-flavor=ld.lld and link arguments `--build-id=none`, `-static`, `-nostdlib`
and `-znoexecstack`; remap the source directory to
`/droidloom/trampoline-source`. The actual build record retains both commands
and complete output hashes. A build record alone cannot replace the separately
verified ELF pin or provide runtime credit.

The producer creates `linkerconfig-original` and `linkerconfig-trampoline` with
mode 0555 and records explicit installation requirements for initial-root
ownership, the complete `linkerconfig_exec` label and absent capability xattrs.
It does not relabel source image inodes, install the output, load a host policy,
or run the original linkerconfig. Production rechecks those exact code pins
alongside the actual sealed files and same-owner executable mounts. The input
production record continues to report installation, activation and runtime
qualification as pending.

## Original fixed application query input production

An adapter with the explicit CP3A execution selection can also select
`query.scope = "cp3a_fixed_application_query_inputs_v1"`. This closed object
accepts no executable paths or replacement files. The producer reads the four
fixed members directly from the same held, fully verified system image with
the pinned filesystem tool. It verifies each whole body, ELF interpreter or
JAR format, original inode mode and ownership, complete SELinux label bytes,
and absence of other xattrs. The output selects the existing fixed command
and Contacts query roles; it adds no query command or application authority.

| Original member | Bytes | Original owner/mode | SHA-256 |
| --- | ---: | --- | --- |
| `/system/bin/cmd` | 52,160 | 0:2000 / 0755 | `237410b6f4bfb9586a9a1135feaa4e75c189288483575890447aa5d492c56984` |
| `/system/bin/toybox` | 611,248 | 0:2000 / 0755 | `5c2b46686560564967fb5c1cb4ec633c42f658c347831c1d8c788ecf66e1774b` |
| `/system/bin/app_process64` | 51,616 | 0:2000 / 0755 | `bcc150b9c7e2abcc9aef312ea04f5bbcba631dbb2e23cb1b240b7219df1229a2` |
| `/system/framework/content.jar` | 20,158 | 0:0 / 0644 | `c0ee6290243eda4a6dd95292c28274dd199b82b57466e00a83e1bb1a50eae8b3` |

All three ELF interpreters are `/system/bin/linker64`. The original labels
are respectively `system_file`, `toolbox_exec`, `zygote_exec` and
`system_file`, each with the actual complete Android context and trailing
NUL. Production checks the same exact source pins. The original-image
verifier preserves the three executables' mapped Android shell group 2000;
it does not confuse those inodes with the root-owned sealed input copies.
The content JAR remains a distinct nonexecutable role with its original
root group and exact mode. No source inode is relabelled or chowned.

The producer creates the three sealed input candidates with mode 0555 and
the JAR with mode 0444. `QUERY-INSTALL-REQUIREMENTS.json` records the actual
source metadata and explicit root ownership/label requirements for later
installation. The consumer still requires the original labels before
constructing separately labelled read-only private query projections.
Extraction, copies and metadata checks provide no successful query,
Contacts response, application admission or runtime qualification.

## Original init cleanup and scoped host context providers

The first two CP3A cleanup requests are accepted only from the original init's
held seccomp listener. The actual pinned init has branches that call
`umount("/debug_ramdisk")` and `umount("/second_stage_resources")` in either
order. Its original bootstrap libc calls `umount2` with flags zero. The
dispatcher accepts each fixed target once, from the original main PID and
execution generation, and reads only the bounded target plus its terminator
through that init's held proc memory descriptor. It rechecks the kernel
notification ID, pending request, memory inode, original executable and
capability contract before and after observation.

Both directories are original system-image directories with mode 0755, owner
0:0, link count two and only `security.selinux = u:object_r:tmpfs:s0\0`.
They must remain empty, on the original read-only root mount and absent from
the mountpoint inventory. The same original runtime owner stores a short
helper before releasing it. The helper joins only the held mount namespace,
uses the held guest root, verifies the fixed target inode and mount, and
performs the real operation. Only a stage-nine result that agrees with the
actual original PIDFD exit can produce a response. Setup failure, timeout,
lost identity or changed mount inventory cannot issue a successful result.
The response forwards the actual errno; it never uses seccomp CONTINUE.
The complete mount inventory must remain unchanged across this cleanup.

The host MAC declaration has an explicit additional route:
`schema = 4`, `scope = "droidloom_linux_android_mac_v4"`,
`context_routing = "selinux_typed_host_scoped_android_v1"`. It requires the
actual AppArmor-first host LSM order. Missing routing is valid only for the
existing version-three SELinux-first contract; explicit null, an unknown
route, a mixed schema or an implicit upgrade is rejected.

Under version four, typed SELinux CURRENT identifies the original broker or
loader. A separately held host proc superblock selects
`lsm_context=selinux` before CREATE, while retaining the original host PID
namespace. Foreign init and linkerconfig observations derive only from the
original opaque owner PIDFD and proc directory, with original start ticks,
thread/process IDs, namespace identity and live policy epoch checks. They
cannot accept a caller-supplied PID or replace a foreign label with the
broker's own CURRENT. Explicit AppArmor proc attributes remain independently
checked. The host self-socket pair observes actual AppArmor SO_PEERSEC and
actual peer PIDFD/credentials; it does not claim an Android SELinux peer.

An Android activation listener under this route must be created in the
original subordinate-userns-owned network namespace after its immutable
SELinux provider is selected and before any socket has marked it used.
Selection checks the actual namespace owner, original held namespace ID,
fixed control-device identity and label, and actual SET/GET results. A new
short helper joins only that held network namespace, creates the listener
and an actual connected probe pair, and transfers all three sockets into
the original DeviceResources owner before acknowledgment. The probes'
SO_PEERSEC values must be SELinux broker contexts and both peer PIDFDs must
identify that same live helper. The helper must then acknowledge completion
and be actually reaped before the listener can be used.

The helper's original creator thread PIDFD and post-PDEATHSIG READY/release
handshake remain mandatory. Creation uses one absolute ten-second deadline,
including its final namespace/provider recheck. Failed preparation retains
the helper and transferred descriptors for explicit original-PIDFD retirement.
DeviceResources holds the same non-serializable, thread-bound MAC/selection
Rc that authorized preparation; no later provider reacquisition substitutes
for it.

The selected control node's actual label and narrow policy permissions,
foreign-process ptrace mediation, both MAC implementations, and a privileged
positive run remain required. These providers do not qualify original init's
three subsequent tmpfs mounts, its mount-namespace transitions, apexd's
loop/verity operations, linkerconfig completion or boot. The existing final
execution and readiness gates remain closed until those actual providers
and observations complete.

The two cleanup operations additionally require an actual single-thread and
zero-child observation of that original process. The listener was installed
with NEW_LISTENER and WAIT_KILLABLE_RECV, and the parent has actually received
this same request. Final 6.18 switches that request to a killable wait: an
ordinary signal cannot resume the original task. Proc reports Threads under
the sighand lock; a departing thread reparents its children before its thread
count is removed. The observer reads the sole main task's children only after
Threads equals one, then repeats the original identity and notification checks.
Thus the only guest thread remains blocked and cannot create a new actor.

The original namespace keeper cloned this PID1 with CLONE_NEWNS and remains
outside that mount namespace. After returning its initial descriptors it
closes them and accepts only the existing Stop message. The selected-network
socket helper has already been reaped. The same original broker thread and
exclusive notification borrow serialize the one mount helper before reply.
A cwd descriptor or UMOUNT_NOFOLLOW is not used as a substitute for this actor
proof: final 6.18 still traverses mountpoints when umount resolves its target.


### Original network selector private control custody

The scoped host route creates the context-control alias only on a new detached
64 KiB, eight-inode tmpfs with nosuid/noexec and devices enabled. The fixed
directory and character node acquire their reviewed labels through named kernel
transitions. The device number comes from the original built-in driver's sysfs
publication. No existing host device inode is opened or relabeled.

Read-only preparation enters the original DEV owner before filesystem creation
or the immutable netns SET. The guard records entry and the actual SET result
before any later check; failure cannot retry or import a selection. Completed
selected sockets stay in an owned pending slot through listener binding, and a
failed bind returns their original custody to that slot. Retirement reaps the
original socket helper before closing private control and netns descriptors.
Closing those descriptors does not reverse SET or prove the original namespace
tree has retired. Both enforcing MAC policies and the actual fixed-provider
positive run remain required.



### Original init three-mount phase

After both actual first-stage cleanup responses, the original CP3A init issues
its fixed tmpfs mounts in the order /apex, /bootstrap-apex, /linkerconfig.
Each request must come from the original main task under the received
WAIT_KILLABLE_RECV notification, with one actual thread and no children.
The source and filesystem strings are exactly tmpfs, flags are 0x0e, and the
original data string is mode=0755,uid=0,gid=0. All strings are read with finite
bounds from the original held proc memory descriptor.

Each operation creates a distinct new bounded tmpfs, sets the fixed source
name before CREATE, applies the same owned idmap, and executes the real
move_mount through the retained helper. The prepared placeholder is never
reported as that new operation. The original syscall response comes only from
the helper's stage-nine native result and matching original PIDFD exit.

A distinct post-mount projection preserves every lower mount record and
admits exactly one new filesystem at the original visible target per step.
Every unaffected role, held source, inode, label, limit and visible mount
remains checked. The initial RuntimeObservation verifier remains unchanged.
Later APEX publication takes the original root from this completed phase
and still requires its own actual bootstrap bind and payload observations.

Retirement first reaps the actual helpers and closes these extra owned views.
Closing them neither unmounts the guest tree nor claims namespace retirement;
the existing original tree owner subsequently performs actual tree and loop
retirement. No completed runtime contract, namespace transition, APEX
acceptance, boot or application readiness follows from these three mounts.


### Original init propagation phase

The original CP3A init's SetupMountNamespaces sequence first requests a
recursive SHARED transition on /, then nonrecursive PRIVATE transitions on
/apex and /linkerconfig. The original mount arguments have null source,
filesystem and data pointers, with flags 0x104000 or 0x40000 respectively.
These finite requests are read from the original pending main task's held
proc memory, with the original PIDFD, generation, MAC pair and deadline.

The new propagation owner stores each helper before its READY release. The
helper enters only the held guest mount namespace, chroots to its original
root, rechecks the fixed target inode and mount ID, and executes the actual
mount syscall. SELinux sb_mount and AppArmor mount mediation still execute;
no mount_setattr replacement bypasses those hooks. Only the actual syscall
errno and matching original PIDFD exit can produce a response.

The private preparation parser remains strict. A separate propagation view
retains each original record plus its actual shared group. Starting from the
proved private graph, recursive SHARED gives each mount in the original
visible-root subtree a distinct new group. Covered lower child mounts remain
in that subtree; any lower ancestor of the visible root is outside this
operation. Each following PRIVATE call removes only the statx-selected visible
target's group, preserving all covered layers and every other field.

The single-thread/no-child actor requirement and received WAIT_KILLABLE_RECV
barrier remain mandatory. The original ELF has conditional boot-timeout and
USB-controller threads before this sequence, so this source does not infer
their absence from an ordinary test or a property default. Missing actual
actor proof still refuses helper release. The later writable /mnt setup,
bind/slave/shared calls, original namespace transitions and apexd execution
remain separate required providers. This phase grants no boot or production
readiness.


### Original first-stage storage preparation

The GSI /mnt directory is an empty readonly image inode, owned by Android
0:1000 with mode 0755 and the original tmpfs SELinux type. The assembled guest
root itself is a different child-created 16 MiB tmpfs. Storage preparation
checks that actual held root's filesystem, size, flags, owner and SELinux EA;
an image-root label cannot substitute for this observation.

While the original first RootShared notification remains received and held,
the original owner creates a new 16 MiB, 4096-inode tmpfs for /mnt. Its only
purpose is storage mount metadata; app data remains outside this filesystem.
The source is nosuid, nodev and noexec, preserves 0:1000/0755/tmpfs semantics,
and receives the same original owner idmap. No source image inode is changed
or relabelled, and no host control descriptor is exported.

The actual source and helper enter the original guard before READY release.
The helper performs real move_mount onto the held /mnt target. The complete
post-operation inventory must retain every prior row, add exactly this held
source, and change only /mnt's visible top. Any failure retains the original
resource custody until actual helper and guest-tree retirement. Closing an
extra mount descriptor never claims the attached guest mount was destroyed.

This preparation does not answer the pending RootShared syscall. Its separate
helper must still execute the original mount operation and supply the actual
errno, followed by the exact PRIVATE transitions. The distinct propagation
view retains the new /mnt row plus its covered original lower layer and checks
the earlier phase only through this explicitly proved one-mount overlay.

The existing single-thread/no-child and received WAIT_KILLABLE_RECV barrier
remain required. The later original bind/slave/shared requests, namespace
creation/switching, apexd activation and privileged positive/boot observations
remain separate required work; no production qualification follows from the
ordinary controls in this increment.


### Original storage bind and propagation phase

The exact CP3A init sequence creates /mnt/user, /mnt/installer and
/mnt/androidwritable, then performs two recursive binds from /mnt/user to
the other directories, two nonrecursive SLAVE changes, and two nonrecursive
SHARED changes. The fixed flags are 0x5000, 0x80000 and 0x100000. Source,
target, null filesystem/data pointers, original main task, generation,
received notification and deadline are checked before each real helper.

One original directory owner holds all three distinct pre-bind inodes and
the actual bounded mapped /mnt filesystem. The directories must still be
empty with their original 0755 mapped ownership. Their complete directory
inventory, source mount and inode metadata stay held through the six calls;
covered target directory descriptors are retained after the actual binds.

The original platform file_contexts entry fixes /mnt/user to mnt_user_file.
There is no installer or androidwritable platform entry. Their expected
labels are obtained from actual same-epoch INIT/tmpfs/dir named-create
queries for those two fixed basenames, then compared to the actual held
inode EAs. This does not assert that init had no fscreate override: a
mismatched actual label is rejected. No directory is relabelled, no type
name is supplied by a caller, and no policy is loaded by this phase.

The helper verifies both absolute names against the original held source
and target before the real mount syscall. It keeps the existing atomic
PIDFD, creator-thread READY barrier, original absolute deadline and actual
reap requirements. An earlier setup failure cannot become a completed
syscall result. Every successful response requires the actual errno and
the complete mount view to agree; CONTINUE and declared success are absent.

A separate parser retains shared and master fields without broadening the
earlier private/shared-only parsers. Each bind must add exactly its observed
new mount of the original /user subdirectory, inherit the original parent
peer group, and preserve every old row and visible layer. Each SLAVE call
removes only that target peer and retains the original parent as master.
Each following SHARED call adds a distinct new peer group while retaining
that master. Unknown, duplicate, reordered or foreign propagation fields
and unrelated mount changes are rejected.

This phase remains conditional on the actual received single-actor barrier.
Original namespace unshare/setns, later directory mutations and apexd/verity
activation need their own subsequent actual phase proofs. Ordinary controls
do not qualify these privileged operations or establish Android boot.


## Kernel-lineage instance factory and ordinary service lifecycle

The kernel-first entry prepares boot-wide delivery directories and the selected
joint policy independently of any Android generation. Original Linux PID 1 starts
the same published droidloomd with --serve-early-instances before the initial
SELinux policy load. That process acknowledges only preparation and blocks on its
inherited pipe. PID 1 then activates the complete original policy, releases the
fixed gate, and waits for the factory to enter the enforced
droidloom-instance-factory AppArmor profile through the native LSM API. The
factory retains the original u:r:kernel:s0 SELinux lineage; it performs no
post-policy host-ELF execute-no-transition, installs no seccomp notification
proxy, and rejects inherited seccomp confinement. PID 1 proceeds to the original
Ubuntu systemd only after the actual factory endpoint is ready.

The ordinary droidloom-instance-launcher.service keeps NoNewPrivileges=yes.
Its separate non-Android role authenticates the factory using the original
native peer PIDFD, actual MAC pair and published executable. The factory
independently authenticates the launcher's native peer PIDFD, actual role, fixed
original systemd MainPID, InvocationID and exact ExecStart. The root-owned
mode-0600 instance-factory.sock accepts the fixed START packet while idle. During
a live generation it also accepts the closed query protocol from that exact
original production owner. A caller cannot select a program, UID range, external
PID or namespace.

For each generation the factory creates original Android PID 1 with atomic
clone3/PIDFD custody. The child opens its own original namespace descriptors and
returns them on its inherited private socketpair; the factory does not request
SYS_PTRACE across the Android user namespace. Existing immutable handoff schemas
and the resource owner's cgroup/release gates remain in use. Each generation
gets a fresh device bank. Its loop-control and transient loop nodes live on a
private bounded tmpfs and receive original Android types at creation; no host
/dev/loop inode is relabeled. The stock kernel-to-init transition is unchanged.

The normal resource owner still performs Android's actual orderly shutdown,
observes original init PIDFD death and retires its exact writable mounts and
other resources. The factory requires that same original owner's normal exit
zero, the original owner PIDFD's death, normal observer retirement, the original
shutdown request, and withdrawn readiness before unmounting its original handle
pins. It resets the same shutdown inode only after retirement and reaps its
direct original child with waitid(P_PIDFD). Its authenticated DONE response
releases the normal launcher. A forced kill, different invocation, timeout or
lost original handle never releases the next generation.

Native descriptor and policy tests establish source-level gates. Full enforcing
boot, complete Android/application readiness, repeated start/orderly-stop/start,
final normal policy/profile pins and CLI restart integration require their own
observed acceptance before production activation.

### Original factory query ownership

For the kernel-first application path, only the current original production
resource owner can send a closed query operation to the active factory
generation. The factory checks the original init and broker PIDFDs, the original
Android USER/PID namespaces, the final observed seven-namespace scope and the
fixed empty application-read cgroup. It reopens the held root, namespace and
immutable copied executable descriptions itself. Duplication does not convert
broker or metadata file-description provenance into kernel provenance. Query
stdin and output pipes retain the independent query-I/O creator's provenance.

The factory creates the actual direct child with atomic clone3 PIDFD and
CLONE_INTO_CGROUP. Its fixed native child code closes all unrelated descriptors
before changing only its SELinux CURRENT to droidloom_query_birth. The child is
still in the original host user namespace with root credentials and a fixed
gate. Only then can the real parent legally PTRACE_SEIZE it; the unchanged
Android neverallow against tracing kernel itself remains in force.

After that attach, the fixed child enters the held namespaces, adopts the
original guest shell credentials and drops capabilities. It changes AppArmor
CURRENT to droidloom-production-android while NNP is still zero, verifies the
actual label, then installs NNP and the existing query seccomp filter. The fixed
copied stock ELF makes the strict birth-to-query transition. There is no
caller-selected program, label, UID or namespace, and no notification proxy.

The actual factory thread consumes TRACEEXEC with waitid and GETEVENTMSG. It
sends the original PIDFS device/inode and closed stop event through the
authenticated nonce protocol. The broker creates its own observation PIDFD,
checks the same kernel object and parent, and asks the fixed metadata observer
to verify actual executable, root, namespaces, credentials, MAC, seccomp and
application-read membership. It never ptraces, signals or reaps the query.
Only a verified release request lets the actual factory execute PTRACE_CONT.
Only its true waitid terminal and same-cgroup retirement can finish the read.

Read receipt schema 2 names its actual lifecycle owner. Legacy receipts keep
their original join-worker terminal. Factory receipts keep the original factory
identity, query PIDFS identity, actual release acknowledgement, query terminal,
and a separate typed stdio-creator terminal. A killed query, nonzero exit,
unacknowledged release, mixed owner fields or unproved retirement cannot become
a successful read. Query cancellation does not kill an otherwise healthy boot
factory after that query has genuinely been reaped.

Before acknowledging boot readiness the factory publishes factory.json once
with renameat2(RENAME_NOREPLACE). The actual root-owned mode-0400, single-link
tmpfs inode must carry p4_linux_instance_record_t; only kernel lineage has
mutation permissions on that object type. The record contains the actual kernel
boot ID, original factory PIDFS device/inode, original PID and actual published
executable device/inode/size. It contains no readiness or wait-success fields.
The factory keeps its original self PIDFD for its entire lifetime.

A broker query client checks native SO_PEERCRED, SO_PEERPIDFD, PIDFD_GET_INFO and
SELinux SO_PEERSEC against that protected original record and its own admitted
published ELF. The actual factory must remain a live root process whose parent
is Linux PID 1. Record inode, actual EA, body, boot identity and original PIDFD
are checked repeatedly. No broker read of a kernel task's proc entry or
kernel-origin transferred file is required. The actual factory checks its
native current MAC pair again during query phases. Per-generation retirement
does not delete or replace the boot-wide record.

Both fixed fresh-image Linux helpers inherit the same broker-created anonymous
read-only EOF pipe on descriptors 0, 1 and 2. Each entry checks the actual FIFO
identity, access flags, POLLHUP and read()==0. A live writer, queued byte, control
socket or host character device is rejected. These valid inherited descriptions
prevent Rust's pre-main startup from opening host /dev/null. The Android query
still receives only the separate query-I/O creator's guest streams.

Ordinary-host PIDFD, TRACEEXEC, fresh-helper and wire tests are not enforcing
Android acceptance. The combined strict policy/profile producer, original
managed cgroup placement, enforcing boot and live fixed Android queries remain
separate runtime gates before this path can qualify any application.


### Permanent original factory service

The boot-born kernel-lineage factory must enter the fixed
`droidloom-instance-factory.service` before creating any Android generation.
The ordinary `--adopt-early-factory` service entry remains in the existing
launcher MAC role and keeps `NoNewPrivileges=yes`; it cannot create or replace
the boot kernel role. The unit is independent of the per-generation production,
launcher, and observer services. Restart is disabled, and a forced exit never
releases a replacement factory or a successful Android retirement.

The normal service executor opens only the fixed factory unit's `cgroup.procs`
as standard output. The adopter checks and relays that original write-only
FileDescription, then removes the migration descriptor from standard output.
The factory independently opens the named control read-only, checks the same
cgroup2 inode, and writes the literal `0` through the executor-origin handle.
Initial and final cgroup membership, unchanged original namespace and process
identity, and the fixed original systemd invocation are mandatory.

The adopter uses the actual systemd `GetUnitByPIDFD` result (object path, unit
name, and invocation ID). After real self-placement it sends one notification
containing `MAINPIDFD=1` and `READY=1` with exactly the original factory PIDFD.
It stays alive until systemd reports the same invocation active with that
original factory as MainPID. The factory separately checks those live manager
properties before acknowledging adoption. A packet acknowledgement or a sent
notification alone is not successful service custody. The source unit's exact
bytes, fragment path, absence of drop-ins, current loaded state, fixed ExecStart,
and enforced adopter roles are checked; no nonexistent output-path D-Bus
property or caller-selected unit/path is used.


### Original init placement from the permanent factory

Each original init is born inside the permanent factory unit. The production
owner prepares its normal empty payload budget, validates the init's original
metadata and namespace custody, and requests only `MoveOriginalInit` on the
authenticated factory channel. The request binds the already-held original
PIDFD and PID-namespace inodes plus the already-owned payload directory. It
contains no caller-selected PID, unit name, pathname, program, or arguments.

The actual retained factory parent opens the one fixed payload `cgroup.procs`
itself and verifies its empty, root-owned original cgroup2 directory. A direct
`clone3(CLONE_PIDFD)` helper enters only the original PID namespace, retains the
initial user namespace and kernel MAC role, closes every descriptor except the
fixed membership file, and writes literal `1`. A fixed native filter admits
only that descriptor's write and process exit. The original namespace's PID 1
cannot be recycled; no host numeric PID is used to authorize a move.

Before cloning, native `capget` proves that the factory's permitted set contains
the complete current kernel capability set. Neither cloning nor the raw helper
changes user namespace or permitted credentials. This preserves the commoncap
subset condition if cpuset migration checks the target scheduler permission;
SELinux's separate process permission remains enforced. The factory's original
PID-for-children namespace and signal mask are restored and checked.

Only the original factory consumes the helper's actual PIDFD wait event. A
normal zero exit, unchanged original init liveness, exact payload member
readback, removal from the permanent factory's member list, and the same live
production owner are required before a nonce-bound response. The broker then
independently rechecks init metadata and cgroup membership before continuing
normal payload delegation. Its later payload-to-init-leaf operation stays
within the already-owned production subtree. Timeout, signal death, lost
custody, context restoration failure, or a failed membership readback cannot
be reported as successful placement or successful Android shutdown.


### Original host namespace authority

After confirming the real Ubuntu root, original Linux PID 1 publishes three
permanent NSFS bindings: `host-pidns`, `host-userns`, and `host-cgroupns`. Each
binding is independently read-only, nosuid, nodev and noexec. Factory and launcher
native admission compare the actual current namespaces to these original
objects; no later `/proc/1/ns` read or initial-userns ptrace capability is needed.
These boot objects are outside every per-generation cleanup inventory.

The original host mount namespace cannot be bound into its own namespace:
Linux rejects that reference cycle. PID 1 instead opens the actual MNT object
and passes it as fixed fd 3 into the original factory exec. Before its boot gate,
the factory validates NSFS, namespace kind and actual self identity, consumes
fd 3 into one private descriptor at or above 64 with CLOEXEC, and retains it
until the factory exits. Every subsequent native factory-role validation checks
this same held object against its actual current mount namespace.

Before either ADOPT or START, the ordinary fixed adopter/launcher performs the
mandatory `DLHOST01` exchange over its authenticated original-factory channel.
The response contains exactly one reference to this original held MNT file
description. The consumer verifies the real object and its own actual mount
namespace, repeats its UID/MAC/NNP and three-pin native gates, and retains the
object for the whole invocation. No caller supplies a namespace, no namespace
is recreated, and no ordinary file or JSON inode declaration substitutes for
this mount-namespace authority. Android-generation and query child paths keep
this private host descriptor CLOEXEC or close it before their fixed MAC/exec
transition.
