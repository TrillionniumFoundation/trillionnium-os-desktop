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
