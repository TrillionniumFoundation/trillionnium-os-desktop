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

## Normal native package closure

native_bundle.py retains the five complete normal libselinux, libapparmor and
GDM package archives, their original rollback packages, and exact source/build
receipts. systemd_bundle.py adds the ten actually installed binaries from the
single normal systemd 259.9 source build. native_release.py combines both
unchanged component releases into droidloom-normal-native-package-release-v2.
Its package-role table and complete file inventory bind all 15 new and 15 old
archives; this release is material, not activation authority.

The ordinary cold_native.py engine checks the complete real package database
and payloads, then invokes the stock dpkg commands with retained archive FDs.
For this exact systemd cohort, libsystemd-shared is unpacked and configured
first because the normal systemd control declares it as a Pre-Depends.
Systemd precedes udev on upgrade; udev precedes systemd on downgrade to satisfy
the normal Breaks relationship. No force or auto-deconfigure option is used.
All other installed package rows must remain unchanged and configured.

The source-owned configured-state interpretation is limited to
/etc/credstore and /etc/credstore.encrypted: the unchanged, fully pinned
stock tmpfiles rule and postinst make these root-owned directories mode 0700
after configuration, although the archive placeholders are 0755. No other
payload metadata is exempt. The normal scripts and all public payload bytes
are verified on upgrade and rollback. Account, SSH and home paths are observed
only through their held metadata and are never replaced by qualification data.

Each attempt retains its actual snapshot, normal command arguments, exit status,
stdout/stderr pins and ordered durable events. A failed unpack can be reopened
by a new process and restored with the original normal packages. The complete
Ubuntu qualification root is a separate successful installation, with a real
971-package database and only the admitted 15 version changes. Its source and
transaction receipts establish package installation; they do not establish
a successful boot, application readiness, or original-account continuity.

Physical activation remains blocked until the cold acceptance validator binds
the same public/native release, actual owned runtime results and original-device
private working-copy qualification. Missing evidence is an error, never a
caller-supplied success flag.

### Native package archive and protected import

The complete normal native release now has a separate material transport. The
export contains all 109 source, inventory, new package and rollback package files
in a canonical USTAR archive. Its fixed index and the original native manifest
are separate pinned files. Both ordinary readback and protected import parse
every header, body, padding block and the exact archive end before running the
existing full source/package verifier. They reject aliases, links, special
members, extensions, extra bytes and unlisted entries.

The build operation is:

    python3.14 -I -B -c 'import sys; sys.path.insert(0, "/usr/lib/droidloom/production/current"); import native_release; native_release.main()' export --bundle NATIVE_BUNDLE --release-id NATIVE_ID --output NEW_OUTPUT

Original-Ubuntu root may import the three protected public material files with
native_release import-archive, supplying the exact index SHA256 and native ID.
The only public destination is
/var/lib/droidloom-maintenance/native-releases/NATIVE_ID. The import creates a
private pending directory, fully validates it, and publishes it with
renameat2(RENAME_NOREPLACE). An existing identical release is read back; a foreign
or altered target is preserved and rejected. Import performs no dpkg action,
service change, boot selection, account operation, or runtime qualification.

The same source-bound fifteen-package closure and original rollback archives
remain mandatory after transport. This operation does not satisfy the owned
runtime or original-device private-account acceptance gates.

The v2 cold preparation plan has four pinned components: host, kernel, android,
and native (the NATIVE-ARCHIVE.json file). It performs a separate full native
archive materialization and normal package/source readback before publishing the
flat immutable candidate. The candidate includes the three native transport
files. Its deployment digest includes the native release ID, archive index and
archive content hashes as well as the three public packages and original root
UUID. The public RELEASE.json digest and deployment digest are distinct values.

The native material destination is fixed to the same imported native ID under
/var/lib/droidloom-maintenance/native-releases. Native installation precedes the
public package phase. All eight source modules must be present in the actual
normal host manifest; an older 46-file diagnostic host is recorded as missing
those eight modules and remains an unqualified candidate. Preparing or verifying
these materials still cannot grant runtime or private-account acceptance.
