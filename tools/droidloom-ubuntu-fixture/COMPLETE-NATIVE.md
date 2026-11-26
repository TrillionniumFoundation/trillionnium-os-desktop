# Complete normal Ubuntu source

This path consumes a fresh Ubuntu root created by normal signed debootstrap and
normal apt/dpkg transactions. It does not reuse or broaden the older selection
of public files from a running machine. The complete tree includes the original
package database, package metadata, service accounts, files, symlinks, hardlinks,
ownership, modes, capabilities and POSIX ACLs.

The source root must be a root-owned root directory directly inside a private
/var/lib/droidloom-qualification/WORK directory. The source receipt binds its
device/inode, the signed bootstrap, successful install/audit/query transactions,
the complete configured package roster and the actual dpkg status. All receipt
references use the producer's exact eight-field EvidencePin. Receipt inputs stay
open and are fully hashed again after capture.

The complete reader uses held directory descriptors and openat2 with BENEATH,
NO_SYMLINKS, NO_MAGICLINKS and NO_XDEV. It never follows guest links into the host,
crosses a mounted API filesystem, or opens a device. Only eight ordinary static
/dev character nodes are representable by their exact name and device number.
Sockets, FIFOs, unrelated devices and links outside the whole frozen inode set
are rejected. Every regular file has complete bytes and privilege metadata
checked between identity observations. A second exact inventory checks the
whole source after capture. Copying uses new inodes, then complete readback.

## Material commands

- capture-complete-native --source-receipt PATH --source-receipt-sha256 SHA --target-kernel-release RELEASE --output MANIFEST
- materialize-complete-native --manifest MANIFEST --manifest-sha256 SHA --destination /var/lib/droidloom-qualification/WORK/root --receipt RECEIPT
- verify-complete-native --manifest MANIFEST --manifest-sha256 SHA --destination /var/lib/droidloom-qualification/WORK/root --receipt RECEIPT

The original **baseline** authority remains unchanged. An **installed** source
must instead bind the exact original baseline manifest, its successful complete
materialization to a different root inode, and every subsequent successful
normal apt/dpkg transaction. The original signed bootstrap and baseline records
are preserved. The manifest embeds the complete original baseline JSON once;
recursive installed baselines are rejected.

An installed source receipt adds `baseline_manifest` and
`installed_admission_directory`. Its `baseline_receipt` names the actual complete
materialization, `package_transactions` names only the successful transactions on
the new root, and `native_transaction` is the final transaction in that chain.
The admission directory must be a new private direct child of
`/var/lib/droidloom-qualification`, outside the source root. Baselines have none
of these installed authorities.

Each installed transaction binds the original staged archive and the actual
private APT cache copy, actual binary control fields, exact offline APT command,
complete simulation delta, both complete dpkg-query outputs, empty dpkg audit,
and the database before/after. No baseline package may disappear, and no version
may change without its actual requested archive. The final database and all
changed-package dependencies are checked from actual bytes.

`native_release` pins a JSON document with schema
`droidloom.complete-ubuntu-native-release.v1` and `systemd` and
`native_candidates` FilePins. These identify normal source/package admission
receipts, not booleans. Capture reruns both admissions against the current root,
including all ten systemd and six libselinux/AppArmor/GDM packages. The complete
installed payload, actual controls, input provenance and current database are
embedded and cross-checked against the full captured tree. Normal package
post-install transformations retain their exact package/source evidence.

These checks admit installed material for the subsequent initialization and
shared-kernel boot workflow. They do not qualify a running guest or application;
`guest_qualified` remains false and runtime requirements remain explicit.

No kernel is fabricated from this root: its /boot is empty and it contains no
module release. A later normal boot consumes the separately published shared
kernel, its full modules and matching initrd. No machine/user credentials are
copied from Pocket4, no process is started inside the captured root, and no
physical package or service is changed by these three material commands.

## Initialize the complete clone

The boot consumer calls `boot_native::initialize_complete(root, work, inputs, manifest)` only after full verification and independent materialization of the installed complete manifest. `CompleteNativeInputs` contains `hostname`, distinct `root_filesystem_uuid` and `network_connection_uuid`, and `generate_fixture_ssh`. The destination is exactly the new private qualification `work/root`; the source root and its file inodes are rejected as mutation destinations.

This path retains the distribution's real service accounts and numeric groups. It admits only locked, consistent passwd/group/shadow/gshadow files without existing regular-user state. Normal `systemd-sysusers` adds `alex` 1000:1000 and `droidloom-cell-u1000` 976:976; the cell's established public home is `/nonexistent`. Existing account rows and memberships must survive, apart from the five explicitly added alex device memberships. The actual GDM group is recorded at `accounts.groups.gdm` in schema `droidloom.complete-native-ubuntu-initialization.v1`; consumers must bind it to that receipt, rather than using the historical public-root group number.

Every identity/configuration replacement is checked against the complete manifest and preserved in the private `work/complete-native-preimages` directory before a new file is created. Only the explicit identity/GDM/SSH allowlist can use this operation. Account files are updated by normal sysusers; the package database is never rebuilt. Fresh machine ID and SSH keys come from the cloned normal distribution programs. The normal aliases and eight unmodified public configurations are rechecked, and the dpkg status must remain unchanged.

Exactly seven nonempty public Snap archives must be present in the manifest and root, with no extra archive or existing Snap state. Their pinned contents supply the existing read-only mount template and revision aliases. No Snap assertions, account tokens or runtime acceptance are manufactured. System and user units are enabled offline. The receipt keeps `guest_started=false` and `guest_qualified=false`; actual boot, enforcing policy, GDM, network, Snap registration and Android/application tests remain separate gates.

Focused tests cover account/UID conflicts, unlocked state, old homes, symlink confinement, full preimages, create-only retirement and exact Snap rosters. An explicitly root-only test exercises real normal `systemd-sysusers`, `systemd-firstboot`, preimage retention and independent replacement in a newly created temporary root; unprivileged runs report it as ignored rather than passing it.

The ended-VM GDM collector reads the boot receipt's exact private `NATIVE-PREPARED.json` pin and preserves its full identity and digest through collection. For this complete schema, the expected GDM primary group comes from the initialized normal account summary; historical public fixtures still require 121. The collector extracts the ended image's root-owned mode-0644 `/etc/group` by inode and checks it against the preparation before considering journal proof. Both the trusted journald `_GID` and the proof payload GID must match. The existing greeter proof reads the fixed `gdm` NSS group and checks its actual credential triple and dynamic account at entry and completion. This changes no journal or desktop acceptance requirement.

## First enforcing calibration, then Android runtime

A complete normally installed root supports two explicit boot phases. First use
`android.calibrate=true`, `android.mac_release=null`, `android.persistent_data=null`
and no `public_apks`. The full installed manifest, native package admission,
normal shared kernel, host archive, labels and initrd are still verified. All
three legacy native ELF overlay fields must remain absent in either phase.

This first phase boots the independent owned guest with enforcing policy and
runs the original `droidloom-mac-calibration.service`. Its
`droidloom-host-mac export-kernel-first-release` producer observes the actual
kernel, original PID 1 and confined loader and exports the five MAC release
members. The collector must verify the actual capture and original systemd
invocation. A preparation receipt only reports `boot_phase="mac_calibration"`;
it does not claim successful calibration, guest qualification or application
acceptance.

After that real capture is verified, prepare another fresh complete root with
`android.calibrate=false` and all five exact pinned `mac_release` files. The
normal release binds the same Android cohort/runtime, kernel policy, complete
systemd ELF and host MAC loader ELF. A changed host, systemd, policy or final
camera cohort needs a compatible real capture; filenames or edited hashes
cannot transfer that authority. This second preparation reports
`boot_phase="android_runtime"`, still with `guest_qualified=false` and
`production_ready=false`. The fresh second root can import the complete pinned
65-APK payload and then run real installation, launch and required business
gates for the selected 39 apps. Preserved original data stays separate from
both the initial calibration and fresh public-APK testing.

## Normal console package closure

The complete initializer checks the compiled board-policy/native-console-setup.json
before modifying the cloned root. This binds the selected normal console-setup,
keyboard-configuration, kbd, shell, coreutils and library packages, all consumed
file bytes and modes, the complete hardlink groups, and command/library symlink
targets. The 116 normal uutils names remain one inode; GNU cp is the actual
selected /usr/bin/cp implementation. No executable replaces a package file and
no normal hardlink group is split.

The normal system service scripts and udev font/terminal cache scripts enter a
dedicated console role. It has no general native command or runtime-library
execution permission. Exact helper and library inodes have narrower labels.
The strict linker derives and checks the old actors' effective access, MLS
constraint membership, ioctl filters and existing transitions for each changed
object family. Original Android assertions and existing native verifiers remain
enabled. The real libselinux matcher checks every regular-file alias and
wrong-kind or unselected-path cases.

The selected configuration uses the US pc105 keyboard, UTF-8 and Uni2 Fixed16
font. Cache regeneration can write only selected cache names and its private
temporary type. The script's first /run/tmpkbd.XXXXXX attempt stays denied;
its existing /tmp fallback creates a non-executable private temporary file.
/run/console-setup has a named directory transition and non-executable marker storage.
No home, password, account key, network socket, arbitrary program, mount or
MAC-management authority is added. VT operations use the actual selected
kernel/kbd ioctl closure and console configuration capability. Normal glibc 2.43
isatty/tcgetattr and the selected normal stty issue TCGETS2 (0x802c542a);
the SELinux filter uses its low 16 bits, 0x542a, and does not grant the obsolete
TCGETS assumption. All 14 requests are checked in the actual linked policy for
exactly the four existing VT object types and the fixed Linux VT type described
below. Null-device isatty probes permit only TCGETS2. Every other character-device
class vector is checked separately.

The original units retain their ordering. console-setup.service is ordered
before the display manager; that ordering and Wants edges do not constitute a
hard GDM Requires dependency. Console functionality is a separate normal-host
requirement. Source admission retains runtime_qualified=false. Actual unit
completion, keyboard mode/keymap, font/terminal readback and normal udev execution
require a real owned boot; package hashes or a service exit cannot claim them.

Focused tests reject missing/extra hardlink aliases, substituted symlinks or
independent copies, altered bytes, duplicate package identities, wrong
architectures, versions and unconfigured dpkg-query states. The existing normal
package canonicalizer accepts the real amd64-qualified names and the ii status.
The explicitly ignored test
boot_native::console::tests::admitted_normal_source_readback validates an existing
normal source using DROIDLOOM_CONSOLE_SOURCE_ROOT, DROIDLOOM_CONSOLE_SOURCE_MANIFEST
and its exact DROIDLOOM_CONSOLE_SOURCE_SHA256. It starts no service and writes no
source file; it does not qualify a running console.

### First-load Linux VT and loader boundaries

The script's initial binfmt handoff opens the fixed normal /usr/bin/dash while
the old executor still owns the credentials. That one interpreter has its own
type: the executor and udev may open it for the script transition, but cannot
execute a shell while remaining in their old role. noatsecure is not granted;
normal secure-exec environment handling remains in effect.

The exact /etc/ld.so.cache inode and the normal locale archive/C.utf8 files
have separate mapped-data types. Console can read/map those bytes without any
execute permission. The fixed old actors which already use the admitted native
ELF interpreter gain only missing cache read/map access. All their existing
alias access/constraints/transitions continue to be derived from the actual
pre-alias policy; the new role receives no generic runtime-library execution.

Before the first policy load, the board holds exactly /dev/tty (5:0, 0666)
and /dev/tty0 through /dev/tty63 (4:0–63, 0600). The selected 6.18 kernel
creates these root:root; the normal 50-udev-default rule sets group tty (5).
Only those two exact metadata states are admitted. All 65 are checked before
the first label write. They stay the same writable devtmpfs inodes, with their
original mode, ownership and ACLs; the four standard-device projections remain
separate. No terminal body is read or written by this label preparation.

O_PATH descriptors, no-symlink resolution, unique mount IDs, full node metadata
and pathname readback bind the operation. Raw xattrs go through only this
process's generated numeric FD links under a held, verified procfs directory.
Its st_size alone is dynamic: selected fs/proc/fd.c:proc_fd_getattr reports the
current open-FD count. This exception is not used for device metadata. After
initial policy load, the same handles must read the exact valid Linux VT label
and unchanged node identities; every handle is closed before PID 1 handoff.
No active-policy generic device relabel or body permission is added.

The new Linux VT type permits the fixed console closure, normal udev label/DAC
maintenance and logind's session VT lifecycle. The verifier reads every concrete
actor and every character-device permission from the real binary; unselected
actors retain at most existing getattr observation. It also checks the exact
extended ioctl sets below, not merely the presence of ioctl permission.

| Actor and target | Fixed requests | Normal source |
| --- | --- | --- |
| PID 1, private console/VT | TCGETS2 0x542a, TCSETS2 0x542b, TIOCGWINSZ 0x5413, TIOCNXCL 0x540d, KDSKBMODE 0x4b45, TCFLSH 0x540b | systemd terminal_reset_ioctl, vt_reset_keyboard, fd_columns/fd_lines, save_console_winsize_in_environment; glibc tcgetattr/tcsetattr/tcflush |
| Executor, private console/VT | TCGETS2 0x542a | systemd isatty_safe and inherited terminal validation |
| logind, Linux VT | TCGETS2 0x542a, KDSETMODE 0x4b3a, KDSKBMODE 0x4b45, VT_SETMODE 0x5602, VT_GETSTATE 0x5603, VT_RELDISP 0x5605, VT_ACTIVATE 0x5606 | session_prepare_vt, vt_restore, vt_release, vt_is_busy and positive chvt |
| Console helper, standardio/null | TCGETS2 0x542a | glibc isatty/tcgetattr, with the null driver's normal ENOTTY |

PID 1's private-console file lock is the existing normal lock_dev_console
operation. These source checks and inode tests do not substitute for actual
unit completion, VT mode/keymap/font readback, logind ownership restoration or
GDM operation in an owned enforcing boot.

The fresh init.scope must use the exact genfs rules for its directory and
control files, like system.slice. The C consumer verifies its scope/procs labels
instead of storing a parent xattr which would make future kernfs controls
inherit a different label. This change must be integrated with the matching
fixed init.scope genfs policy; root membership handling and all descriptor
retirement remain unchanged.
