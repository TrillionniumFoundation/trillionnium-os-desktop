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
