# Shared-kernel Ubuntu release and fixed maintenance

This component adds a normal host payload and a constrained maintenance entry.
Building or testing it does not install a release, change GRUB, reboot a machine,
qualify Android, or replace the original Ubuntu filesystem.

## Production maintenance

The unchanged Ubuntu sudo-rs binary and existing sudoers/PAM account stack
authenticate the caller. The normal file context selects the sudo role; only
the normally published maintenance ELF may transition from it into maintenance.
No generic privileged shell is granted. In particular, invoking sudo /bin/sh
does not gain executable permission through this component.

The fixed commands are:

~~~sh
sudo /usr/lib/droidloom/production/current/droidloom-maintenance status
sudo /usr/lib/droidloom/production/current/droidloom-maintenance collect
sudo /usr/lib/droidloom/production/current/droidloom-maintenance verify RELEASE_SHA256
sudo /usr/lib/droidloom/production/current/droidloom-maintenance rollback
sudo /usr/lib/droidloom/production/current/droidloom-maintenance reboot
~~~

No command accepts a caller path, program, unit name, systemd property, journal
match, GRUB entry, username, UID, environment assignment, or optional flag.
The verify action accepts exactly one lowercase SHA256 identifying an already
protected release manifest. It reports byte verification, never runtime readiness.

The status action observes the fixed system and UID 1000 user units, original
MainPID and InvocationID, boot ID, kernel release, SELinux enforcement/current
context, and AppArmor state. User-unit observations use a fresh subprocess
irreversibly set to UID/GID 1000, with empty supplementary groups and the fixed
local user-bus address; the maintenance owner stays root. A failed manager
observation is returned as failed evidence, not a running/ready unit.

Maintenance selects one exact systemd tool pair for its actual phase. Under the
shared kernel, the real enforcing maintenance context admits only the normal
259.9-0ubuntu0.1+p4gentmp1 candidate's `systemctl` and `journalctl` bytes. Their
source package and complete installed payload are checked by the normal
systemd admission; a caller cannot supply another hash, version, or path. The
original 7.0.14-p4cred1 cold boot instead reads the protected actual dpkg status
and requires all ten selected systemd packages to be configured at one identical
original or candidate version before choosing that version's exact pair. A mixed
or half-configured family is rejected. The original DB descriptor is retained
through the command. Shared-kernel maintenance needs no new access to dpkg data,
and a binary mismatch never falls back to the other phase's tool.

The collect action retains bounded actual journal records for the fixed units,
including trusted boot/PID/UID/unit/Invocation/cursor and monotonic fields.
The journal reader is a separate zero-capability role. It does not reuse or
broaden the existing journal-flush role. Output is limited to 2,000 records and
8 MiB with a 30-second original-process deadline. Metadata before and after
collection expose a changed boot. Message text does not authenticate the sender
or replace trusted journal fields. Private user files and Android userdata are
not inputs. Missing journal writer permissions remain an independently visible
native-service blocker; this reader does not fabricate missing records.

The rollback action checks the root-protected installation record, exact stock
GRUB configuration, and original Ubuntu entry. It changes only next_entry in the
already existing original /boot/grub/grubenv inode using the pinned stock
grub-editenv. It neither creates a GRUB file nor reboots. The reboot action
repeats the original entry/environment checks and requests only the dedicated
stock reboot.target through the real system manager. A successful reply records
an accepted request, not a completed boot.

The original Ubuntu entry must remain installed and verified until final
qualification and explicit cleanup. The fixed production helper never invokes
dpkg, a shell, package maintainer scripts, arbitrary journal commands, or a live
GRUB configuration generator. Normal package installation and independent GRUB
entry publication belong to a separate cold transaction in the original Ubuntu
maintenance boot or a trusted offline environment. That transaction must
preserve the actual root UUID, account database, passwords, SSH configuration,
and original Android data. A fresh qualification root is not a deployment root.

## Normal host publication

The normal droidloom-update host-stage producer compiles maintenance.c and embeds
the exact SHA256/length of this script and the admitted original Ubuntu Python
3.14 interpreter. The fixed production entry remains:

| Normal payload | Mode |
| --- | --- |
| usr/lib/droidloom/production/current/droidloom-maintenance | 0755 |
| usr/lib/droidloom/production/current/droidloom-maintenance.py | 0444 |

The same normal host manifest also contains eight independent, readonly modules
under /usr/lib/droidloom/production/current/: release.py, cold_publish.py,
cold_transaction.py, cold_apply.py, native_bundle.py, systemd_bundle.py,
native_release.py, and cold_native.py. All have root owner/group, mode 0444,
and one link after normal import. cold_modules.rs is the shared source list
used by the normal publisher, exact fixture source-byte admission, and final
ext4 readback. The normal host Debian archive carries these members unchanged;
no workspace module is copied into an installed system by a separate path.

These modules add no production helper action, executable transition, capability,
or live package writer. The authenticated production C entry still runs only
the exact droidloom-maintenance.py script and the five commands above. The cold
modules are used in the original Ubuntu maintenance boot, where the cold
authority and actual acceptance records must be verified before any deployment.

The C entry opens the original interpreter and script through root-owned,
non-writable, non-symlink directory components, verifies complete SHA256 and
nine-field inode identity, retains the original descriptors, clears the
environment, verifies the actual SELinux role with the explicit native LSM
provider (single ID 101, CURRENT 100, no legacy fallback), sets no-new-privileges,
and enters the pinned interpreter in isolated
mode with bytecode writes disabled. A caller-supplied interpreter, script,
environment, or module search path is not consumed.

Produce a normal Debian host package as an ordinary build user:

~~~sh
python3 packaging/ubuntu/production/release.py pack-host \
  --plan /absolute/HOST-DEB-PLAN.json --output /absolute/fresh-output
~~~

The JSON plan has exactly schema, host_manifest, and host_archive. Its schema is
droidloom-normal-host-deb-plan-v1. Each input pin has exactly path, bytes, sha256.
Inputs are the actual normal HOST-STAGE.json and HOST-STAGE.tar.xz. The producer
verifies all original archive members against the manifest, rejects duplicate
paths, links, unexpected types/modes/owners, and retains its source commit/tree.
The only at-sign path exception is the exact reviewed normal
etc/systemd/system/user-runtime-dir@.service.d/50-droidloom-native-session.conf
member. General relative and absolute path admission still rejects at signs.
The ordinary Debian build uses dpkg-deb --root-owner-group and contains only
control and md5sums in its control archive, with no maintainer scripts. Actual
extraction verifies the complete file inventory, bytes, modes, directories, and
both control files. RESULT.json retains the original input and package pins and
keeps physical_install and runtime_qualified false.

## Verification and remaining qualification

The linked policy is compiled with all nine original Android CIL inputs and
assertions, without -N. verify_native_maintenance.py reads the actual binary AV,
exact capabilities, permitted transition sources, immutable inputs, fixed GRUB
write scope, readonly journal, and service-status versus reboot-start boundary.
The shared original Android matrix remains part of the normal compiler gate.

test_release.py exercises original-FD replacement, path alias/link rejection,
fixed input/output bounds, and actual subprocess deadline/output retirement.
The normal C stage has a focused rejection test. These checks do not claim the
actual enforcing login/PAM, fixed helper, original GRUB return, or native desktop
has run successfully. Those gates require the normal assembled candidate under
the real shared kernel and both enforcing MAC systems. Stock interactive PTY or
fingerprint authentication likewise needs a real qualified session. The existing
alex NOPASSWD policy is not modified by this component.

A previous normal public host archive may exercise the Debian packaging
mechanism. Such a result identifies that old commit and is never relabeled a
new production release. No success receipt is rewritten.

## Normal public kernel and Android Debian components

The source-owned cold_publish.py adds two ordinary packaging commands. The kernel
plan is droidloom-normal-kernel-deb-plan-v1 with one publication FilePin. The
Android plan is droidloom-normal-android-deb-plan-v2 with one materials FilePin.
The normal kernel publisher's exact completed manifest binds all 6,797 original
signed modules and 15 indexes; this command verifies every original byte before
packaging. It does not export the signing private key. The Android input is the
exact completed camera source `11bf0fa339d9c52fbf1093d95e1218f1ada40574`,
tree `266e49032d5a68e843dabb49db33595e652e5466`. The fixed MATERIALS,
independent HANDOFF, normal vendor result and actual producer terminal hashes
bind the new four-image/v2-query/device-bank cohort. Packaging rereads the normal
source records, all nine actual Android CIL inputs and all four extracted camera
members. It cross-checks their complete bytes, modes, owners and SELinux labels
against the normal image readback before copying and fully extracting the Debian
payload. The source records remain unchanged and are retained with the package
and later cold release. The old R10 plan is rejected. No userdata or metadata
image is included, and no install-session or runtime activation is claimed.

The camera material pin is 12,961 bytes with SHA256
`84916101e6c7908114e4053bf6fbdfefc2480b902153923152cad64e62c54547`.
Its schema is `p4-normal-camera-android-materials-v1`. Supply the actual original
MATERIALS path: a transported summary with rewritten paths is not the source
record. The fixed public source images may be packaged by the ordinary build
user; a physical source or service is never modified by this command.

~~~sh
python3 packaging/ubuntu/production/cold_publish.py pack-kernel \
  --plan /absolute/KERNEL-DEB-PLAN.json --output /absolute/fresh-kernel-output
python3 packaging/ubuntu/production/cold_publish.py pack-android \
  --plan /absolute/ANDROID-DEB-PLAN.json --output /absolute/fresh-android-output
~~~

Both normal packages have root-owned payloads and only control/md5sums control
members. Complete ordinary extraction checks every payload digest and mode.
The kernel retains xz; the multi-GiB raw Android image package uses stock dpkg
zstd with one compressor thread and the same bounded deadline. SELinux labels
are not claimed to survive Debian data archives: the four query inputs preserve
the original installation requirements and must receive the exact original
labels, ownership, modes, absence of capabilities, and actual readback during
the eventual cold installation.

## Create-only cold transaction preparation

cold_transaction.py preflight is a readonly original-Pocket4 check. It requires
the original 7.0.14-p4cred1 boot, initial user namespace, actual PID1 root, and
the original ext4 root/boot UUID 01c27223-3933-481e-9836-7bd0ef1be8c9. It hashes
only the fixed public boot/tool files. Account databases, SSH configuration,
and the alex home are observed through metadata only; their contents are not
copied. The sole output must be a create-only COLD-PREFLIGHT-*.json inside the
fixed public evidence directory. It does not inspect original Android data.

~~~sh
sudo python3 packaging/ubuntu/production/cold_transaction.py preflight \
  --output /home/alex/work/p4-native-maintenance-cutover-516eec-r1/COLD-PREFLIGHT-r1.json
python3 packaging/ubuntu/production/cold_transaction.py prepare \
  --plan /absolute/COLD-PLAN.json --output /absolute/fresh-candidate
~~~

The cold plan has schema droidloom-cold-release-preparation-v1, exactly three
components (host/kernel/android normal result FilePins), and one target_preflight
FilePin. Preparation checks the source-bound host manifest, completed normal
kernel/Android cohorts, real Debian control archives, and all original package
bytes. The flat release directory is compatible with the fixed maintenance
verify command after a later protected import. RELEASE.json always says
qualified=false; its exact bytes define the release identifier.

The candidate includes a separate stock GRUB menu entry and source generator.
The original Ubuntu entry remains the default, with a visible recovery menu.
No generator is executed or installed by preparation. The new entry explicitly
keeps both SELinux and AppArmor enforcing, selects the published board-init,
and references an independent new initramfs path. That initramfs must later be
built through the actual original host's normal initramfs mechanism, with the
same selected public libraries/host/kernel and complete readback. A qualification
VM's fresh filesystem or initramfs is not silently used as the physical root.

COLD-INTENT.json lists the unresolved acceptance and publication gates. Missing
maintenance payloads in an older, otherwise valid normal host are reported
explicitly. The current activate interface verifies the candidate and then
fails closed: no admitted verifier yet connects the actual owned full-guest
acceptance, original-device private working-copy acceptance, native candidates,
full host labels, selected-data/five-file MAC publication, and actual maintenance
return to the original Ubuntu. There is no caller-supplied pass flag. Future
integration must consume those real records and preserve their identity chain;
it must not edit this list or a receipt to manufacture acceptance.

This component deliberately contains no dpkg installation, physical relabel,
service enable, GRUB update, one-shot boot selection, or reboot action.
The transaction is reviewable preparation. Physical publication remains blocked
by the actual acceptance gates and is not claimed complete by these build tests.

### Original-host normal initramfs preparation

`droidloom-ubuntu-fixture prepare-original-initramfs --config PLAN
--config-sha256 SHA256` runs a separate Rust producer. Its strict plan is:

```json
{
  "schema": "droidloom.original-host-initramfs-plan.v1",
  "work_directory": "/var/lib/droidloom-qualification/original-initramfs-candidate-r1",
  "public_release": {"path": "/protected/release/RELEASE.json", "bytes": 1, "sha256": "..."},
  "native_release": {"path": "/protected/native/NATIVE-RELEASE.json", "bytes": 1, "sha256": "..."},
  "native_release_id": "...",
  "target_preflight": {"path": "/protected/COLD-PREFLIGHT.json", "bytes": 1, "sha256": "..."}
}
```

Replace the example pins with the exact protected normal records. The work name
uses lowercase letters, digits and hyphens, and must be absent. The native source
is the separate `droidloom-original-host-native-package-release-v1` profile with
exactly 22 candidate and 22 rollback packages. A fresh original-host preflight must
match the actual boot ID, original kernel, root UUID, PID1 root and held original
boot/tool inodes. Original tool paths are resolved through the existing protected
alias reader and the exact alias inode chain and final ELF are rechecked after
the package locks and at completion. Each full held-descriptor hash restarts at
offset zero, including repeated readbacks of the same inode. The original uutils
chroot has one fixed
root-owned symlink and a source-pinned multi-call ELF with exactly 116 hard links;
this narrow read-only tool exception does not apply to candidate inputs or outputs.
The producer takes POSIX shared locks on the physical dpkg and
frontend locks. It hashes the actual original passwd/group and dpkg status,
records metadata of preserved account/SSH/home paths, and verifies them again
after preparation. Shadow/gshadow and SSH key contents are never captured.

The source-embedded existing cold admission code rereads the complete normal
native archives and the real host/kernel Debian data streams. Twenty-four exact
archives are copied into the private input directory: original native 22, public
host and shared kernel. The Android package is bound to the same release but is
not installed in this initramfs build. No package is installed in the physical
root. The source modules, actual commands and source pins remain in the receipt.

Fixed mount setup first proves a distinct, recursively private mount namespace
and an isolated network while retaining the original user namespace. It makes
a nonrecursive readonly bind of the original root before creating the overlay;
this avoids cloning inherited locked child mounts. The readonly lower, inputs
and hardware binds are verified from actual mountinfo. No package script runs
during this setup.
The fixed original `/tmp` mountpoint may retain its root-owned sticky 1777 mode
until it is covered by the new tmpfs. Only its final directory inode is checked;
none of its contents or descendant paths enter this exception.

Package scripts then enter UID/GID map `0 0 65536` with a second private mount
namespace, locking the inherited readonly binds, and retain the isolated
network, IPC and UTS namespaces. The overlay stores writes in an independent
bounded tmpfs. A nested PID namespace places
the chrooted builder at PID1, preventing `/proc/1/root` from exposing the setup
process's original root. Home, original Android data, maintenance state and the entire previous
qualification tree are hidden; only this build's separate `/build` and `/inputs`
binds remain visible; `/run` and `/dev` are private, and hardware `/sys` is readonly. Each of
the five admitted character devices is checked by actual type and device number.
Before any package script executes, setpriv removes mount, raw-device, MAC,
module, reboot and other global capabilities from the bounding set and enables
no-new-privileges. The child verifies actual effective/permitted/bounding masks
and requires a real permission denial for a harmless readonly-to-readonly `/sys`
remount. The fixed
temporary policy-rc.d returns 101 and normal apt uses only the admitted local
archives with no network or extra package/removal authorization. The source-pinned
archives are copied, create-only, into the private overlay's canonical APT archive
cache with their real package/version/architecture names, preserving `all` and
escaping a version epoch as `%3a`. Both simulation and `--no-download --no-remove`
installation use those absolute cache paths. This follows the complete source
installer's normal offline path; it neither enables downloading nor changes
physical cache files. Every copied archive is read back before APT starts. All original
account bytes and unrelated configured package identities must remain unchanged
inside the private view too. The roster also retains removed-package config-file
and purged records, including their exact prior version, architecture and state;
they cannot stand in for an already installed native candidate dependency.
Original GDM and service numbers are preserved.

The material admission's v3 record includes the entire host/kernel directory
inventory from the actual, fully verified Debian data streams. Original dpkg
preserves existing directory owners: this host's two public namespace roots,
`/usr/lib/droidloom` and `/usr/share/droidloom`, are legacy `1000:1000`, mode
`0755`. After proving private overlay/PID isolation, the producer records a
durable intent and changes only those two held directory descriptors to the
archive's `0:0/0755`. It accepts only their exact original metadata or already
correct ownership, never follows an alias, and never recursively changes a
child. Every directory in the full admitted inventory is read back after normal
installation. The outer process compares both original directory identities and
metadata again, including when the private build fails. This private mechanism
does not authorize physical directory changes; the cold transaction must retain
their original owner/mode/xattrs in its rollback snapshot before its own claim.

The cold public transaction now records those exact two legacy directories in
its v2 snapshot, together with the original inode, metadata and extended
attributes of every selected directory. The complete normal package inventory
must declare both as `0:0/0755`. Snapshot and recovery-pointer durability precede
the held-descriptor, nonrecursive ownership claims; the selected original files
and directory identities are checked again before and after those claims, before
dpkg may run. No other user-owned ancestor is admitted. Existing private parents
retain their original restrictive mode and attributes, while the claimed public
namespaces remain root-owned after installation. Readback covers every selected
directory as well as every normal package file.

Recovery uses that same durable snapshot if interruption occurs between the two
claims or during package installation. It rejects an unknown replacement inode
and reclaims only the saved public namespace roots, then performs normal package
removal and restores selected original files. Newly created empty directories
are removed before the two legacy owners are restored last. Their original
mode, extended attributes and modification time are restored with descriptor
and parent-directory fsync; existing unselected children are never traversed or
recursively chowned. Old v1 snapshots retain their original interpretation and
cannot introduce a legacy-owner exception. This recovery mechanism leaves the
physical qualification and permanent activation gates unchanged.

The producer calls the original normal `mkinitramfs`, with one-thread gzip,
the retained shared-kernel release and the original host configuration. Its
source-owned extra upstream hook uses `copy_exec` for both admitted native LSM
libraries. A fixed private `conf.d` file sets the upstream `FSTYPE=ext4` setting
after the original root UUID and actual mounted ext4 are verified. The upstream
fsck hook can then include the original filesystem checkers without gaining raw
access to the host block device; automatic probing cannot do that in the isolated
`/dev`. The original `fsck`, ext4 checker and `logsave` ELFs and alias chains are
guarded across preparation, and their full bytes and metadata must appear in the
normal output. Normal `unmkinitramfs` then reads back the whole output. The stock
`/init`, early-custody order, both host ELFs, both native libraries, and every
included kernel module must match their actual normal sources. A complete
bounded member inventory retains both raw archive paths and normalized effective
paths. Every normal main/early archive layer rejects private account, SSH, home,
Android-data and qualification-tree contents. The private configured dpkg status and original
command logs are retained. Private package writes disappear with the namespace.

`ORIGINAL-INITRAMFS-PREPARED.json` has phase `candidate_preparation`. It is real
build evidence and grants no boot, package installation, permanent default or
service enable authority. The once-only physical qualification phase still
requires the same candidate's actual owned calibration/runtime mechanism,
original account and independent data-working-copy identities, actual physical
file-context readback, selected-data/five-MAC-file publication, and an atomic
independent Ubuntu recovery entry plus maintenance configuration. Final permanent
activation separately requires all selected 39 complete business/common gates,
private migration acceptance and the actual maintenance return to original
Ubuntu. Physical camera and maintenance-return results are therefore later
qualification observations, rather than prerequisites that prevent the first
controlled qualification boot. A phase name or caller pass flag establishes
none of these observations.

## Isolated cold command invocation

The production C entry uses the held interpreter FD with the exact argument
vector /usr/bin/python3.14, -I, -B, /proc/self/fd/4, --maintenance, the fixed
action, and an optional release digest. It supplies only PATH, LC_ALL, LANG and
PYTHONNOUSERSITE, changes directory to /, and never inserts the production
directory into sys.path. Its pinned script imports no sibling cold module.

Python isolated mode does not add the script directory to sys.path. A trusted
operator in the original Ubuntu maintenance boot uses an explicit fixed module
directory for the separate cold tool; the selected module is a literal in the
command, never a caller-supplied module name. For example, the readonly bundle
verification entry is:

~~~sh
sudo /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C LANG=C \
  /usr/bin/python3.14 -I -B -c \
  'import sys; sys.path.insert(0, "/usr/lib/droidloom/production/current"); from cold_transaction import main; main()' \
  verify --bundle /var/lib/droidloom-maintenance/releases/RELEASE_SHA256 \
  --release RELEASE_SHA256
~~~

This command belongs to the unchanged original Ubuntu administrator context,
not the constrained production sudo role. It requires the normally installed,
root-owned, non-writable module directory. The actual original interpreter
identity and all eight module origins are covered by the loading audit. The
same interpreter rejects an import without the explicit fixed directory under
-I. No user site, current directory or PYTHONPATH is part of this invocation.
Byte verification alone does not authorize apply or activation.

## Complete normal native package publication

The current combined native release is schema
`droidloom-normal-native-package-release-v3`. It contains the same sixteen normal
packages as the complete installed qualification root: ten systemd packages,
libselinux1, apparmor, libapparmor1, gdm3, libgdm1 and gir1.2-gdm-1.0. The AppArmor
parser package accompanies its library. Its exact original and candidate Debian
archive digests are frozen in the source, and its candidate output is verified
against the same normal AppArmor `.changes` and `.buildinfo` already admitted for
libapparmor. Both complete payloads and every control member are read back.

The two normal AppArmor postinst/postrm files each differ only in two generated
`dh_apparmor` version comments. The verifier permits those exact full comment
lines and requires every executable script byte, conffile declaration, config,
trigger and template to remain identical. It does not rewrite either archive.

~~~sh
python3 packaging/ubuntu/production/native_release.py prepare \
  --core /absolute/native-five --core-release-id NATIVE_FIVE_ID \
  --systemd /absolute/systemd --systemd-release-id SYSTEMD_ID \
  --apparmor-old /absolute/old-apparmor.deb \
  --apparmor-new /absolute/new-apparmor.deb \
  --output /absolute/fresh-native-sixteen
~~~

The physical original host has six more installed source-family packages than
the complete qualification fixture: libselinux-dev, libsystemd-dev, libudev-dev,
systemd-cryptsetup, systemd-dev and systemd-oomd. Its independent original-host
profile includes exactly those six alongside the unchanged sixteen. The original
2391-record dpkg status binds their versions, sources and architectures;
systemd-dev remains architecture `all`. The six candidate archives are bound to
the same admitted normal `.changes` and `.buildinfo`. Their original rollback
archives are verified against complete Ubuntu InRelease and Packages files with
the actual archive-key signature. Both versions' complete control and payload
streams are read back, and executable maintainer/configuration scripts must be
byte-identical. No original package is removed to satisfy a candidate dependency.

~~~sh
python3 packaging/ubuntu/production/native_release.py prepare-original \
  --native-full /absolute/native-sixteen --native-release-id NATIVE_SIXTEEN_ID \
  --extras /absolute/normal-original-six-and-signed-sources \
  --output /absolute/fresh-original-native-22
~~~

Historical five-, fifteen- and sixteen-package releases retain their original
verification and rollback interpretation. New physical native application
requires the exact original-host 22-package profile; the complete fixture's
sixteen-package contract is unchanged. Publication grants no runtime or
application acceptance.

## Recovery of an interrupted native package transaction

Rollback consumes the original protected attempt and snapshot, exact target root
inode and native source closure. It does not require successful application
acceptance or an already repaired dpkg database. The source admits the original
Ubuntu kernel, initial user namespace and actual root/boot filesystem first.
Under the original transaction and dpkg locks it then matches the installed
`systemctl` ELF against exactly one old or new systemd package member from that
same verified release. Only the fixed inactive graphical/Android owner checks
may execute through this recovery path. The selected tool, boot and unit states
are retained in the durable transaction journal before normal downgrade begins.
Unknown binaries, a live owner, another root or another attempt are rejected.
The shared-kernel maintenance command path and ordinary cold application keep
their stricter complete-family admission.


## Independent owned full-guest evidence

The normal fixture tool's `verify-owned-guest` command binds one completed full
native guest to its original preparation, run and collector inputs. The plan
schema is `droidloom.owned-full-guest-evidence-plan.v1`, with `boot_plan`,
`collect_plan` and `collected` FilePins, `expected_boot_phase` (`mac_calibration`
or `android_runtime`), and a fresh `verification_name` of at most 48 ASCII
letters, digits, underscores or hyphens. `collected` points to the actual
`boot/RUN/COLLECTION/COLLECTED.json`; the two plan pins refer to the exact source
bytes used by preparation and collection, including their original hashes.
All inputs and their ancestors must remain root protected.

~~~sh
droidloom-ubuntu-fixture verify-owned-guest \
  --config /var/lib/droidloom-qualification/INPUTS/OWNED-GUEST.json \
  --config-sha256 SOURCE_PLAN_SHA256
~~~

Verification checks the complete installed-source manifest and all sixteen
normally installed native packages, preserved package database, selected normal
host, shared kernel, Android cohort and runtime, actual paused QEMU executable
inode and unprivileged process fields, exact device/descriptor/network command
line, ended independent disk, retained original image and ordinary guest exit.
It then invokes the existing bounded collector on a fresh replay of that ended
disk. The actual journal and PID 1 fields are read again; an asserted successful
collector flag is not evidence. Original files remain unchanged. New evidence
is confined to `boot/RUN/NAME` and `boot/RUN/NAME-journals`.

The output `OWNED-GUEST-VERIFIED.json` proves only the owned normal guest
mechanism. Calibration must occur before ordinary Android runtime and does not
require application business acceptance. Calibration forbids original working
data and public APK imports; ordinary runtime requires the exact five-file MAC
input set. Neither mode authorizes physical publication, application acceptance,
service activation or deletion of recovery inputs.

The cold sequence remains ordered: normal source-bound public and exact original
22-package native publication; original-host initramfs, file-contexts and recovery-entry
readback for a controlled qualification boot; then independent original-data,
complete selected-39 business/common gates and actual maintenance-to-Ubuntu
return evidence before permanent activation. The owned guest record retains
those separate outstanding authorities rather than folding them into a passed
flag or making the first calibration depend on final application acceptance.

## Original data directory custody

The normal fixture tool exposes a metadata-only `inspect-original-data-pair`
entry point. Its protected plan has schema
`droidloom.original-data-inspection-plan.v1`, a create-only `work_directory`
directly below `/var/lib/droidloom-qualification` named
`original-data-inspect-...`, and `cold_clone`, a FilePin for the retained normal
cold-clone proof imported byte-for-byte into a root-protected directory.

~~~sh
droidloom-ubuntu-fixture inspect-original-data-pair \
  --config /var/lib/droidloom-qualification/INPUTS/DATA-INSPECTION.json \
  --config-sha256 SOURCE_PLAN_SHA256
~~~

Inspection binds the two actual original images through the retained cold clone
to the existing independent working-copy producer. Both sides' complete F9
identities, sizes, roles and independent inodes must still match; each individual
copy record must match the whole-pair record. Image descriptors are opened
read-only for the real backing flock protocol, without reading their bodies.
Kernel process descriptors, mapped-file identities, bind-mount roots and loop
backings are checked for those same inodes; a permission error cannot become an
empty owner set. The original host, proof bytes and pair metadata are read again
before writing `ORIGINAL-DATA-INSPECTED.json`. That record grants no physical
exchange, runtime acceptance or production authority.

The private Rust transaction core keeps both images in their original parent
directory. Its durable intent precedes moving the entire admitted working-copy
directory into the private recovery work, then `RENAME_EXCHANGE` selects it at
the fixed `/var/lib/droidloom/users/1000/data` path. The original directory and
both original image inodes remain together in `data-pair.rollback`. Only after
both parent directories are durable and the new cell pin is revalidated may the
normal `selected.json` be published atomically. No per-image move is used.

Recovery first restores the original selection, then reverses the directory
exchange and returns the whole working-copy directory to its original location.
It identifies every interrupted phase from the actual directory and selection
inodes, not a passed flag or a journal phase alone. Original image F9 identities
remain exact; a working image that has run may retain its changed content clocks,
while its inode, size, mode and owner must remain the same. Its old copy hash is
historical evidence and is never asserted as a new runtime or migration result.
The mutation core has no standalone physical CLI; only the separately verified
qualification controller's sealed authority calls its typed preparation and
exchange adapter. Every move rechecks the exact durable once phase, immutable
data intent, selected cell bytes, four backing OFDs and actual retirement scan.
Exchange returns before labels and final selection publication.

Mount-reference observations bind both the mount namespace and the held
process-root inode. Two chroots in the same namespace cannot share an unchecked
mount result, and a missing process root never completes a namespace scan. The
PID start identity, root and namespace must remain stable through the readback.
Every mutation observation also rereads the held immutable intent's full bytes,
F9 identity and named inode.

The enclosing qualification authority must prove that the owned runtime,
mounts and loops have retired before restoration. The data writer then performs
real `fsync` on both held working-image descriptors and verifies their metadata
again before restoring the selection or directory pair. It never synchronizes
the preserved original images. The recovery receipt records the two actual
working-backend synchronization results separately from directory rename
durability and runtime or migration acceptance.


### Descriptor-bound label recovery

The label mutation core changes only `security.selinux` through the fixed
`/proc/self/fd/<held O_PATH>` bridge. It binds the actual proc filesystem,
current-process inode and held mount, PID and user namespaces before and after
access. A held symlink is treated as that symlink inode, without changing its
target or a replacement at the old pathname. All other extended attributes and
all inode fields other than the expected ctime remain exact.

Before an inode can change, its complete preimage, desired source-plan label
and candidate binding are written and fsynced in a protected create-only
journal. A separate recovery descriptor stays open when a syscall succeeds but
a later identity check or result publication fails. Recovery classifies the
actual full xattrs and inode identity against the two admitted states; an error
is never interpreted as proof that nothing was written. Partial result files
are preserved under their inode/hash names before recovery continues. Replaced
proofs, replaced target inodes and unrelated attribute changes are rejected.

Persistent snapshots include the ext4 inode/generation handle. The small
`droidloom-descriptor-custody` crate wraps only `name_to_handle_at` with a fixed
empty path and `open_by_handle_at` with fixed `O_PATH|O_NOFOLLOW|O_CLOEXEC` flags.
The fixture crate continues to forbid unsafe code. Decoding a handle is not
installation authority: the full label adapter must bind the same original
filesystem UUID, held mount, immutable plan and normally resolved pathname.
An unlinked old inode is rejected even if a remaining descriptor allows the
kernel to decode its handle. The physical label-plan/apply interface remains
closed until that complete source and once-owner binding is present.


### Fresh original initramfs admission

The read-only `verify-original-initramfs` command takes a protected
`droidloom.original-initramfs-readback-plan.v1` JSON with `work_directory`
and `prepared` (the actual `ORIGINAL-INITRAMFS-PREPARED.json` FilePin).
The output work is a new `original-initramfs-...` child of the qualification
directory. The command rereads the original context and public package database
under the existing shared dpkg locks, checks the actual normal producer/import
and complete source inventory, and runs the same source-bound public/native22
archive admission again. It extracts the admitted normal kernel package only
into its private work and unpacks the existing initramfs for full readback.

The five required candidate members, stock upstream init, original filesystem
checkers, every archived member and every retained signed-kernel module are
checked against their actual source pins. Producer staging may change only the
known archive paths to the exact numbered private inputs, never package bytes
or selection. The resulting `ORIGINAL-INITRAMFS-READBACK.json` exposes the full
normal Materials, actual producer and host source commit/tree, source receipts,
image and member pins for the once owner to cross-bind. Old success flags do
not authorize this readback, and a successful readback does not authorize a
qualification boot, physical installation or final application acceptance.

The fresh readback also parses both the still-current original dpkg status and
the normal producer's retained private status. The whole roster must equal the
original roster with exactly the selected 24 package transactions; retained
configuration-only and held states cannot disappear. Both actual status pins
and complete parsed rosters are exposed for the once constructor.

Only this read-only image verifier distinguishes historical and current
/home/alex directory-entry metadata. The complete producer excluded /home
and the full image validator rejects every home payload layer. The same
home inode/type/mode/owner must remain, while its directory length/link count
and clocks may reflect continued use. Every other machine/account/package
field remains exact. Both complete observations are retained; normal physical
preparation and its fresh context gates are unchanged.

### Complete original label source inspection

`inspect-original-labels` takes a protected
`droidloom.original-label-inspection-plan.v1` input with `work_directory`,
`prepared_initramfs`, `cold_clone` and the existing `label_tools` pins. The new
work must be an `original-initramfs-label-...` direct child of the qualification
directory. Admission reruns the complete normal initramfs/package verifier,
extracts only the admitted normal host package into private work, and validates
its file-contexts against its own joint policy with the normal `setfiles -n`.
The actual normal `matchpathcon` and source libsepol resolve every included
inode's context without changing any original label.

The scope is the original UUID's ext4 root, with fixed exclusions for the
historical `/home/alex/work` tree, qualification/evidence/rollback tree and
the fixed data pair (which has its separate exact-member transaction). Exact
retained cold-clone directories are also recorded and reread, even beneath
an already excluded ancestor. Original device/process/system/runtime/tmp mounts,
the actual EFI mount and normal readonly Snap mounts are separately recorded;
an unknown mount cannot become an arbitrary caller exclusion. Normal homes
and service homes remain in scope. The metadata walk never reads their bodies.

Included pathnames bind held inodes, complete metadata/xattrs and ext4
generation handles. All hardlink aliases must be inspected and must resolve to
the same label, so a hardlink into an excluded tree cannot silently change a
protected inode. The full inventory is read again after context lookup, and
excluded roots retain their original labels. Output is a read-only
`ORIGINAL-ROOT-LABEL-PLAN.json`; it grants no physical write authority.

Generation recovery requires actual `CAP_DAC_READ_SEARCH`, including for
`O_PATH` handles. The original-kernel root owner records and checks its real
capabilities and namespace custody. A candidate return helper with no effective
capabilities never receives the label/data recovery API or additional capability
authority. Across boots, the original owner reopens the actual UUID-bound root
mount and verifies the saved generation and normal pathname again.

Each durable label attempt now synchronizes the target filesystem through an
ordinary held same-filesystem directory FD before publishing APPLIED or
RESTORED. Complete target metadata and xattrs are read before and after that
`syncfs`; fsync of the evidence journal alone is insufficient. The opaque
`OriginalLabelDerivation` retains the held inode, sealed complete source plan
and actual durable result for the once owner's narrow lock-ctime rebind. It
has no public constructor, deserializer or physical CLI. The complete typed
apply and post-runtime retirement adapter must still admit the candidate and
actual mutable-inode restoration before it can grant physical label mutation.

### Original GRUB target identity

Cold preflight and target admission use the same original-entry verifier as
maintenance return. The original 7.0.14 kernel is the observed leaf inside the
normal advanced submenu, with the complete parent/leaf chain, kernel and initrd
paths, root arguments and original default preserved. The simple entry currently
selects another kernel and cannot stand in for this target. Admission rereads
the complete pinned normal grub.cfg, including the exact original leaf body.
Historical targets retain their recorded simple-entry fact and are not rewritten
to pass a new physical transaction; final candidates need a fresh target.

The typed data adapter now separates durable selection withdrawal from working-image
synchronization. The owner must enter SelectionWithdrawIntent, observe the real
atomic withdrawal, then enter SelectionWithdrawn before retire_working can return
the opaque WorkingDataRetired proof. That proof retains both synchronized read-only
working OFDs and exact current identities, with complete reference scans before
and after synchronization. Later changes invalidate it; it cannot be reconstructed
from serialized success flags. Original images receive no synchronization call.
The once constructor can retain the actual OriginalLabelSources object and use
its source_pin and fresh_initramfs_report accessors, avoiding a second package/image
admission or trusting a later caller-generated label-source assertion.


### Current metadata during original label restoration

The private runtime restoration core records a new, immutable current preimage
only for fixed normal log, cache, temporary, original user/service-home, and
same-candidate runtime-evidence paths after the enclosing owner proves actual
retirement. It preserves their current content identity, metadata, and every
unrelated xattr; only this transaction's SELinux value is restored. Normal
package databases and all other paths retain their strict source snapshots.
Every restoration still requires the same ext4 generation and inode authority,
a durable preimage, complete readback and a real same-filesystem syncfs barrier.

OriginalLabelRestoration is an opaque held-descriptor result, not a serialized
grant. WorkingDataRetired may rebind one synchronized backing's ctime only from
that actual source-plan-bound restoration and revalidates both original OFD
locks. The core has no physical entry point or retirement constructor. Tests
exercise real isolated inode writes; they do not claim a physical boot,
working-copy migration or production acceptance.

### Original initramfs recovery recipe custody

The original-root normal producer accepts an optional pinned `recovery_recipe`. It admits the same normally built producer ELF and exact original materials, keeps all four source descriptors and complete identities across the isolated package/mkinitramfs operation, and stages only the fixed recovery source paths. The private build installs the source-owned normal hook before mkinitramfs. Its existing full archive readback also checks the actual early helper, configuration, signed module, normal init/functions and first/unique init-top ordering. A fresh verification independently repeats these checks. An ordinary image must contain none of the qualification-only recovery entry points.

This interface prepares an image in the existing private overlay. It does not install original-host packages, change labels or data, arm the watchdog, alter GRUB, or grant physical boot authority. Historical images without a recovery recipe retain their ordinary-image scope. Exact final public/native inputs still require a fresh normal build. The archive-only materials verifier is separately usable for restoration: it checks the preserved complete normal package family and source bytes, without claiming the historical original dpkg database is the current returned database.

### Label-source custody after original return

`OriginalLabelRestoreSources` is a separate opaque, read-only source factory. It reopens the original immutable source pin, historical fresh initramfs admission, normal public/native archive family, and exact extracted FC, policy and matcher sources. It preserves their real descriptor identities and complete hashes. It does not rerun initial-host admission against the post-install database, convert historical package status to a current-status assertion, or construct the initial label-apply source type. The once return owner separately proves the actual current package/rollback database and real retirement.

The original `dpkg-deb` descriptor is retained only during normal extraction and policy validation, with its real identity recorded. It is not held as an unchanged empty-xattr source during a later legitimate whole-root labeling pass. Long-lived source guards remain on immutable qualification artifacts. The matcher uses the existing runner's fixed locale and its one allowed library-path input.

### Complete original-root label application and selected-last publication

The sealed once owner creates `labels/LABEL-PLAN.json` only at GrubPublished, after every normal public/configuration input exists. It contains the complete fixed original-root inventory, exact exclusions, normal source pin, pair intent, all actual xattrs/ext4 generations, hardlink coverage, and the normal matcher output. The working pair's fixed nine members and the privately prepared selected inode are separate explicit targets. The original rollback pair and historical clone are not labeled. The old selected inode stays outside the root sweep.

The actual writer consumes `OriginalQualificationAuthority`, its durable LabelsIntent pin and live `OriginalLabelSources`. It persists every preimage and retains an independent recovery descriptor before a syscall. Successful but unreported writes are recognized by actual metadata/xattrs, synchronized through the same filesystem, and returned as opaque derivations; an error never means no side effect. A crash before preimage publication preserves any partial evidence and only retries after the target still exactly matches the complete preimage. Source, namespace, owner, lock and reference checks remain active.

Only `OriginalLabelsApplied` can feed the typed selected-last writer. Publication and withdrawal each persist the actual parent membership, parent generation/xattrs and both configuration inodes before the atomic rename, synchronize both directories, and read back their exact known changes. The selected-parent exception is limited to this owned rename; unrelated files or attributes reject. The arm-side readback checks all labeled targets again and substitutes only these actual parent/selected derivations. No selected file is published from a passed flag.

The code remains source-only until the complete once owner, actual quiescence, qualified normal materials and later typed retirement/restoration are connected and independently reviewed. These isolated tests do not assert a physical label sweep, successful boot, private-data migration, application readiness, or final activation.

### Normal systemd state during label restoration

The source factory extracts three exact normal systemd units from the admitted systemd and systemd-timesyncd archives, checks their complete fixed bytes/hash, and keeps their immutable source pins in the original source record. Restoration reopens those same proofs. Only the declared seed, timesync clock/directory and linger directory/ordinary direct user names receive these additional fixed state contracts. No generic /var/lib, package database, NetworkManager state or nested caller path is admitted.

The actual gentmp2 random-seed source performs in-place write/truncate/fsync. It normally removes and sets only user.random-seed-creditable (absent or exactly one byte 1). This one source-owned attribute may therefore differ across the runtime window on the same generation and root-owned0600 regular file. The restoration preimage records its complete current value, and the label syscall must preserve that and every other current attribute and inode field. This is not an exception for replaced generations or unrelated attributes, and never reads seed contents. The normal gentmp2 archive readback independently matched all three declared unit hashes.

The initial data intent now retains each original and working directory/member's complete descriptor-bound xattrs and ext4 generation alongside F9. This reads no image bodies. Every retirement/layout observation preserves the original rollback attributes and generation exactly. Working observations permit only the separately admitted SELinux label attribute to differ; all unrelated xattrs and the generation remain exact, and this observation alone never authorizes a label or data mutation. Old incomplete data intents cannot substitute for these mandatory snapshots.


### Complete original label restoration

The data adapter first consumes the real `OriginalRetirement` and durably
returns the entire independent working directory to its private location.
`OriginalLabelRestorationTransaction` then reopens the original immutable label
plan and exact normal archive sources. Every target is matched both by its
named inode and its persistent ext4 generation; the logical working-data paths
map to the returned private copy, never the restored original images.

Every restoration writes a current preimage under its actual retirement
epoch, retains a recovery descriptor, changes only the recorded SELinux
attribute, and performs the target filesystem metadata barrier before recording
completion. Original accounts/package inputs remain strict. Only the fixed,
source-defined log/cache/home/service state contracts may preserve current
runtime metadata; the two working images additionally require their actual
two-FD fsync and retirement proof. The single GRUB environment and owned
directory renames use their exact transaction observations, not generic mutable
paths. Unknown generations, aliases, attributes or source states remain errors.

A mutable path category describes admissible metadata evolution; it does not
reject an unchanged symlink such as `/var/log/README`. Exact applied/current
equality is admitted only after the existing complete handle, xattr and any
specialized service-state checks. Changed symlinks and special objects still
have no mutable metadata allowance, and a replacement generation is rejected.

An interrupted successful xattr operation is recognized from its real inode
before the held owner's ctime is rebound. A new real retirement may finish
restoration after permitted mutable growth without editing an older preimage.
The opaque `OriginalLabelsRestored` exists only after complete current target
and retained-exclusion readback. Its account/SSH/home metadata derivations bind
the original source prelabel snapshot, current snapshot, restored snapshot and
actual evidence pins for the normal package rollback bridge. No caller Boolean,
phase name, request to return, or failed-return record proves normal shutdown
or final application readiness.

These are source and isolated filesystem tests. They do not assert that labels
have been applied to the original device or that a physical boot is authorized.
The initial and returned owner windows must still retain actual quiescence,
deadlines and complete source/reference checks at their boundaries.

### Bounded normal context matching

Normal context lookup groups the complete inventory by its actual inode type, then runs the same source-pinned matcher on at most 512 paths and 160 KiB of complete argument bytes per process. Every returned context remains paired with its original path/type and passes the same strict parser; no missing or additional output is accepted. The per-command output bound follows the maximum complete context row count, and the normal runner retains its timeout and total-log limit. This removes repeated process-poll overhead from root-scale preparation without changing file contexts or relaxing any target identity gate.

An actual original-host read-only comparison covered 1,548 recorded normal targets across directories, regular files, symlinks and character devices. All per-path results matched between the former 32-path and new 512-path batches, with every tool/context/source pin unchanged before and after. This checks matcher equivalence; it is not a full-tree frozen-window timing result or a physical label-write acceptance.

### Complete label windows and rollback metadata custody

Both full-tree writers now require the corresponding opaque borrowed window: OriginalLabelWindow for forward LabelsIntent, and OriginalRestoreLabelWindow for the actually returned PairRestored owner. Those windows retain the independently guarded real freezer and deadline. Per-inode checks preserve held/named complete identities, xattrs, generation, normal-source custody, owner/namespaces/locks and exact immutable intent/plan identities. Complete source hashing and system-wide reference observation still occur at phase boundaries; the full target and exclusion readback is unchanged. No generic fast flag or caller callback replaces these gates.

The returned path-metadata query is read-only and accepts a bounded, unique set of paths already present in the exact label plan. It first verifies complete actual restoration and then returns every requested prelabel/current/restored snapshot and original proof pins. The closed configuration rollback producer must collect its full finite target/parent set before its first later write; it cannot demand unchanged whole-tree state after it has legitimately restored a configuration. The fixed account/SSH/home helper remains a restricted view of the same proof.

Missing preimages or applications can be reconciled only during a verified unbooted abort or a separately proved preparation-interrupted return. The exact inode generation, current label result and complete other metadata still decide whether that specific unfinished syscall is recognizable. Normal or failed candidate runtime cannot manufacture missing pre-boot application records. These source and isolated tests do not prove that a complete original-root window fits the deadline, and do not authorize a physical label sweep or final activation.

### Bounded durable label batches

The original-root label writer retains the complete source plan, individual
persistent inode handles, full metadata/xattr preimages and independent recovery
descriptors. Ordinary targets are grouped in at most 64 records and 8 MiB of
serialized pending bodies. Each group writes create-only pending records, issues
a real same-filesystem syncfs, publishes the complete record names with
RENAME_NOREPLACE, then issues a second syncfs before any target xattr syscall
is permitted. A crash during publication can therefore reveal a subset of
complete durable originals; uncommitted targets remain unchanged.

After applying a group, every target is checked again across one same-filesystem
metadata barrier. The group then publishes its ordinary per-inode APPLIED.json
records with the same two-barrier protocol. No complete opaque label derivation
is exposed until these records and target metadata have passed readback.
CURRENT-PREIMAGE.json and RESTORED.json use the identical bounded protocol
after actual runtime retirement. Their schemas, original source pins, current
metadata admission and retained history remain the same. Missing success
records are reconciled from actual generation, complete metadata and xattrs;
they never imply that a potentially successful syscall did nothing.

The actual once windows provide their held synchronous paths. The three fixed
locks, current cell, returned GRUB environment and every actually held runtime
evidence member are singleton operations. The label adapter additionally keeps
the original root, whole working pair with its nine members and pending selection
as singletons. They receive their durable opaque ctime derivation before another
owner fence. Caller-provided names cannot expand either window or label scope.

The real frozen-window source/custody/namespace checks and per-target alias,
generation, metadata and attribute checks remain in both loops. Full source
hashes, process/reference retirement and complete target readbacks remain at
the phase boundaries. A partial batch retains all recovery descriptors in its
transaction; existing interrupted/historical return paths keep their exact
per-inode reconciliation.

Focused tests exercise 64 real regular/directory inodes through ten actual
same-filesystem barriers for complete apply and restore, with unchanged bodies
and all target readbacks. They also interrupt preimage publication and target
syscalls and reject foreign xattrs or replaced evidence. These tests are not a
full-root timing or physical activation claim. The complete shadow-root run
must still satisfy the fixed 600-second window without increasing its budget.

The batch recovery test also interrupts restoration after only three of eight
kernel writes, with all CURRENT-PREIMAGE records durable and no RESTORED records.
It drops the live objects, reopens actual original/current records and inode
handles, classifies the mixed outcomes, and restores every member. The explicit
ignored complete shadow-root benchmark uses only its fixed independent r2 root,
checks each target is not the original source inode, restores a full group before
checking the unchanged 600-second deadline, then rereads every completed target.
It reports complete coverage and fitting the fixed window separately, including
final readback time; it never constructs physical qualification authority.

### Normal native package configuration-parent provenance

The once configuration producer observes the normal native22 package operation
through `cold_original_once_package_parents.rs`, nested in the existing
configuration module. It never executes a package script, grants physical
qualification, or substitutes directory metadata for complete DPKG verification.

Before each create-only `dispatch-NNNN-native-apply` or
`dispatch-NNNN-native-rollback`, `capture` binds the actual native snapshot and
attempt, the immutable once intent, admitted normal materials, and the selected
original-host native release. It verifies the complete old/new GDM and systemd
archive digests whose normal maintainer scripts define the allowed effects.
The actual snapshot is copied byte-for-byte into private qualification custody;
its original pathname and digest remain the normal command input. Later label
changes to the original transaction file cannot redefine this retained source.
Normal published sources retain root-owned readonly mode 0444 or 0400 with
complete held/named F9, bytes and empty attributes; private attempt evidence
continues to require the existing 0400 `SealedInput` contract.

`BEFORE.json` is durable before the package command can start. It records every
direct member's full identity and ext4 generation in `/etc/systemd/system` and,
when present, `local-fs.target.wants`, together with complete parent attributes.
The selected normal scripts permit only these observed changes:

- With the actual unchanged GDM default selection and normal service file,
  GDM's configure postinst may replace `display-manager.service` with a fresh
  symlink to the same `/lib/systemd/system/gdm3.service`. An existing `/dev/null`
  mask stays exactly unchanged. An absent alias on a later attempt requires the
  exact earlier sealed interrupted-removal observation for this same native
  attempt; an arbitrary originally absent alias is not admitted.
- The normal systemd preinst may remove `tmp.mount` only when it is the obsolete
  `/usr/share/systemd/tmp.mount` symlink. That exact predicate also permits its
  captured non-directory wants entry to be removed. Independently, the wants
  symlink to that same obsolete example may be removed. No other unit or helper
  alias is whitelisted.

Every unrelated member, parent generation, owner, mode, link count and xattr
remains exact. Parent size/clocks can evolve only with an actually explained
change to its direct member. A nested directory's changed metadata updates its
ancestor's member record without exempting that ancestor's own clocks. Merely
returning exit zero cannot admit another member, inode replacement, or
parent-only clock drift.

`finish` reopens the exact `INPUTS.json`, actual normal stdout and source-owned
terminal `RESULT.json` for this command and then verifies current named/held
parents. `reconcile_interrupted` takes that same completed path when a real
result exists; otherwise it records only interrupted parent metadata. Missing
input is admissible only before any command activity, with an absent/empty
command directory and a completely unchanged namespace. These records never
claim the native database has finished installation or rollback.

Opaque `Changes::reopen` verifies historical sealed sources and full recorded
deltas without requiring today's directory to equal an earlier checkpoint.
`apply_to` composes only an exact historical before-to-after step. The once
owner replays owner/masks, the native install delta, then runtime configuration;
return replays runtime configuration restoration, the separate native rollback
delta, then masks/owner restoration. Each later mutation still checks the full
actual current parent against that composed checkpoint.

Focused tests cover exact command/source/attempt bindings and terminal-event
requirements. Separate root tests create only independent qualification test
inodes: real same-target `ln -sf`, retained/reopened interrupted preimages, both
obsolete tmp predicates, and rejection of unrelated children, replaced directory
generations and unexplained parent clocks. The selected normal native22 archives
are also read back completely. These are source and isolated filesystem proofs;
they do not constitute an original-device package operation or runtime pass.

### Callable original-once dispatcher and interrupted preparation

`droidloom-ubuntu-fixture run-original-once --config PLAN --config-sha256 SHA`
is the single entry to the original-machine transaction. It obtains the private
material/owner authority from real normal-source, ended owned-guest, MAC,
original-host and recovery admission. It has no installation-success or
qualification Boolean argument. The normal owner unit retains the four original
locks through every action and remains installed until the final public rollback.
The public packages, native22 packages, cell and recovery configurations, independent
working pair, label transaction, selected publication and GRUB one-shot arm all
use their existing source-bound writers and durable observed events.

On restart, the dispatcher retires an interrupted preparation instead of silently
resuming forward actions. ArmIntent with an already modified next_entry is
reconciled by the normal GRUB reader/disarmer before unbooted retirement. A
preparation that never published its first Admitted event only preserves its
private directory under a new name after real original-owner checks; it cannot
invent a pair intent, label plan or public rollback. Later no-pair/no-label paths
use their actual zero-effect observations. Original cell restoration, native
rollback, public rollback, writer masks and owner-unit withdrawal remain ordered.

Each package operation captures its exact configuration-parent preimage before
the command. Normal completion, actual interrupted metadata and a durable result
whose phase acknowledgement was interrupted follow separate verified paths.
Source-derived parent changes compose between the corresponding configuration
groups. Full parent metadata must be unchanged before a rename that has not
happened; a parent-only touch or foreign create/delete cannot masquerade as the
intended atomic exchange. Actual already-completed rename recovery retains its
finite two-inode classification.

Complete label restoration seals the configuration and normal-package metadata
inputs under the actual label-result hash before publishing LabelsRestored. That
event binds both seals, so a crash before CellRestoreIntent reopens the exact
completed checkpoint. Earlier incomplete restoration generations remain intact;
a new real retirement writes a new seal rather than overwriting prior records.
Runtime-born evidence is archived only after actual label restoration, with its
own inode/parent evolution and no synthetic label preimage. The original
normal-package snapshots are never rewritten.

The CLI wiring and isolated tests do not declare the full original-device
lifecycle qualified. Normal helper/policy/AppArmor packaging, exact current
cohort admission, the measured complete frozen windows and selected-kernel
runtime return proof remain mandatory before physical arm. Permanent enablement
still requires its separate real application, private-data and maintenance gates.

A native parent capture interrupted before BEFORE.json has a separate private-
only recovery path. It retains the original capture directory and any exact
prefix of the same normally produced snapshot, verifies that the corresponding
command directory does not exist, and seals the observation outside that
untouched directory. Source binding reopens the actual native-snapshot input,
stdout, result, original snapshot and selected native package sources. An
existing input, command directory, result, foreign member, changed generation
or non-source prefix is rejected. The preservation record is never a native
package completion or parent-change event; the normal public/native rollback
still uses its original durable snapshots.
