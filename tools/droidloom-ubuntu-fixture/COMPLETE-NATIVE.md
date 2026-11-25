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

This initial contract admits the original configured **baseline**. It explicitly
rejects an installed claim: the final patched native package transaction and
its whole payload need their separate completed admission contract. Baseline
capture/copy is neither a final release nor permission to skip normal package
installation.

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
