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
