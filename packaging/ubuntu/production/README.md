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
3.14 interpreter. It adds exactly:

| Normal payload | Mode |
| --- | --- |
| usr/lib/droidloom/production/current/droidloom-maintenance | 0755 |
| usr/lib/droidloom/production/current/droidloom-maintenance.py | 0444 |

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
Android plan is droidloom-normal-android-deb-plan-v1 with one handoff FilePin.
The normal kernel publisher's exact completed manifest binds all 6,797 original
signed modules and 15 indexes; this command verifies every original byte before
packaging. It does not export the signing private key. The Android input is the
exact completed normal R10 four-image/v2-query/device-bank handoff. It contains
no userdata or metadata image and has no install-session or activation claim.

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

Historical five- and fifteen-package releases retain their original verification
and rollback interpretation. New physical native application requires the full
sixteen-package release. Package publication still grants no runtime or
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

The cold sequence remains ordered: normal source-bound public and sixteen-package
native publication; original-host initramfs, file-contexts and recovery-entry
readback for a controlled qualification boot; then independent original-data,
complete selected-39 business/common gates and actual maintenance-to-Ubuntu
return evidence before permanent activation. The owned guest record retains
those separate outstanding authorities rather than folding them into a passed
flag or making the first calibration depend on final application acceptance.
