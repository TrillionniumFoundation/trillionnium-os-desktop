# Native generator private tmpfs

Cal11 reached the original environment generator, then the stock systemd generator
sandbox failed when mounting its private /tmp. The exact retained serial is
296,862 bytes, SHA-256 8d83292d66ef611902c2375938d32ee89891d9b1371d3ad4c75494eabb521d1a.
The original owned VM ended unsuccessfully; this source change is not runtime qualification.

Apply the quilt patch to the exact normally unpacked Ubuntu source in source.lock.json,
with the original Ubuntu quilt series already applied. Add one normal changelog entry
for the locked candidate source version and build through the original Debian packaging.

The actual raw native manager context selects an internal flag before clone. The child
uses only literal labels on a newly created tmpfs. Its original new mount namespace,
slave propagation, nosuid/nodev options, mode, resource limits, generation and wait/error
handling remain. No environment variable, supplied path, capability increase, generic
Android tmpfs mount, or fallback on the failed mount is introduced.

Kernel 6.18's may_context_mount_sb_relabel requires the native manager's exact
tmpfs:filesystem relabelfrom source permission and relabel-to the new native
filesystem type. The following inode context checks also require relabel-from the
new filesystem and association of the one native temporary-inode type. These are
explicit policy boundaries; no original Android inode is relabelled.

The normal source package, binary package dependency closure, full payload readback,
original package rollback, strict original-nine-CIL policy build, and a fresh actual
enforcing boot are mandatory downstream gates. A patch application alone passes none
of those runtime or package gates.

## Normal package and source admission

`droidloom-ubuntu-fixture verify-systemd-candidate --config PLAN.json
--config-sha256 SHA256` checks the complete maintained systemd source family.
It is a read-only admission command: it snapshots pinned inputs into a fresh
private work directory, but never installs packages, extracts a payload into a
source root, runs maintainer scripts, or changes the host's package database.

The plan has schema `droidloom.systemd-candidate-admission-plan.v1` and these
fields. Every `FilePin` is `{ "path": "/absolute/path", "bytes": N,
"sha256": "64 lowercase hex digits" }`:

- `work_directory`: a nonexistent direct child of
  `/var/lib/droidloom-qualification`; admission creates it with mode 0700.
- `artifacts`: a map from exact archive basename to `FilePin`. Include the
  original three source archives from `source.lock.json`, the new `.dsc`,
  Debian source archive, `.changes`, `.buildinfo`, every output listed by their
  SHA256 fields, and the original ten binary package archives.
- `original_status`: the pinned real dpkg status file of the completed normal
  baseline, before the candidate transaction.
- `normal_build`: a pinned `droidloom.systemd-normal-build.v1` producer record.
  It contains the actual `exit_code`, `argv`, `source_lock_sha256`, `outputs`
  (basename to byte count and SHA256), and `source_roundtrip` (every patched
  source path declared in `source.lock.json`, with its byte count and SHA256). Keep the original command and source
  roundtrip receipts with this record. A successful normal `dpkg-source
  --after-build` may unapply the quilt series in the build directory; the
  independently unpacked candidate `.dsc` is the maintained source check.
- `installed_source`: omit it or set it to null for material admission. After
  normal installation and capture, set it to `{ "root": "/var/lib/droidloom-qualification/WORK/root",
  "manifest": FilePin }` to verify the real installed source and its capture.
  The manifest may be omitted while capture is pending; the receipt then keeps
  `capture_manifest_verified` false and the captured-member count null, while
  still checking the actual installed database and complete package payload.

The exact family is `libnss-systemd`, `libpam-systemd`, `libsystemd-shared`,
`libsystemd0`, `libudev1`, `systemd`, `systemd-resolved`, `systemd-sysv`,
`systemd-timesyncd`, and `udev`, all amd64. Admission refuses a missing package,
mixed family versions, missing source/build output, a dependency or reverse
dependency that does not hold, an unreviewed payload path/owner/mode/alias
change, or a duplicate or malformed package control field. It checks every regular payload member,
including the shared libraries and helper executables, rather than selecting
only PID 1.

The existing public supplement parser keeps refusing archive extensions. The
read-only systemd admission additionally accepts bounded GNU long file names,
which the normal systemd package uses for one long unit alias. Each declaration
must bind the next header exactly; traversal, orphan/repeated declarations, PAX
metadata, long link targets, devices and sparse members remain refused.

Two normal packaging differences are scoped explicitly. Eleven documentation
symlinks may become regular 0644 files. NEWS must match the corresponding new
`libsystemd-shared` document byte for byte. Decompressed changelogs must match
except for Debhelper's exact final `apt changelog <binary-package>` hint; any
other text change fails. The systemd package also includes
the original upstream `po/LINGUAS` set of 46 translations: exactly 139 added
read-only catalog/directory members. Catalog magic, table bounds and string
termination are checked. No other added or removed payload path, executable
permission change, owner change, or alias change is admitted.

Source admission allows only the appended maintained patch, appended quilt
series entry, and prepended changelog entry. The producer's private source
archive umask may remove group/other permission bits without changing bytes,
ownership or link targets. Ubuntu's original `Dpkg::Vendor::Ubuntu`
`update-buildprofiles` hook supplies `derivative.ubuntu noudeb`; only that exact
default profile set and `parallel=1`, `parallel=2`, or `parallel=4` are accepted.
Profiles/options such as `nocheck`, `nodoc`, `noinsttest`, and `stage1` fail
admission.

Use a create-only private clone of the completed normal bootstrap for the real
package transaction. Preserve its baseline receipt and status pin. The normal
producer runs dpkg in new user, mount, PID and network namespaces with private
mount propagation, `SYSTEMD_OFFLINE=1`, a create-only `policy-rc.d` returning
101, and no host `/sys` or `/run` bind. It consumes the admitted local packages,
checks the actual dpkg exit/status/audit, and retains the unchanged host and
baseline database evidence. The old public fixture lacks a dpkg database and
cannot stand in for this normal baseline.

After the normal transaction, use the existing `capture`, `materialize`, and
`prepare-native` interfaces with newly pinned public inputs. Re-run admission
in another fresh work directory with `installed_source` populated. This checks
the new source's actual package versions, every selected package payload, and
every captured public payload member against its manifest. The two credential
store directories must have the normal installed 0700 permissions; that exact
change from archive mode 0755 is bound to the candidate
`/usr/lib/tmpfiles.d/credstore.conf` bytes and its two explicit rules. No other
installed metadata exception is accepted. Configuration or
state paths outside the public capture allowlist are reported separately and
remain subject to ordinary native initialization.

`SYSTEMD-CANDIDATE-VERIFIED.json` records material and optional installed-source
verification. It always leaves `guest_qualified` and `production_ready` false.
The enforcing shared-kernel boot and application gates must still pass.

## Complete native package source verification

A complete Ubuntu source installs normal Debian packages before capture. The fixed additional source families are `libselinux1`, `apparmor` with `libapparmor1`, and `gdm3` with its exact-version `libgdm1` and `gir1.2-gdm-1.0` dependencies. Development and debug packages remain build evidence, outside the installed selection. Original and installed dpkg databases must contain exactly these members of their respective source families, all configured at the selected version.

`droidloom-ubuntu-fixture verify-native-candidates --config PLAN --config-sha256 SHA256` accepts schema `droidloom.native-family-candidate-admission-plan.v1`. It binds the six actual normal package hashes and their complete `.changes`/`.buildinfo` output sets. It reuses the maintained libselinux, AppArmor and GDM source, normal build, API/regression and packaged ELF validators, then decodes every selected package member and reads its bytes, type, mode, owner and alias from the private installed root. No package installation or legacy ELF overlay runs during verification.

The plan's `artifacts` map retains each original producer path as its key and pins an independent imported copy as its value. A source receipt is consumed unchanged. An imported artifact must match the original expected basename, size and SHA256; missing imports and conflicting copies fail admission. `libselinux`, `libapparmor` and `gdm` retain the existing candidate input structures. `original_status` pins the original complete dpkg roster. `installed_root` optionally requests current source readback; absent it, neither installed-state nor capture verification is claimed.

Both systemd and the three-family admission receipts preserve the exact input configuration bytes. Installed complete-source capture calls `verify_installed_systemd` and `verify_installed_native` with the actual root, the admitted receipt pin and a new private evidence directory. These helpers repeat source/build/archive and current dpkg/payload validation; an earlier pass flag never substitutes for reading the new root. The report's `input` retains the original admission input identity and `preserved_input` pins this run's private copy.

`installed_source.complete_installed_payload` contains every member actually read back, including any explicitly source-bound normal package transform. Systemd's two credential directory modes are bound to its exact tmpfiles rules. The selected libselinux, AppArmor and GDM packages require exact archive metadata and contents. Complete capture must compare all these members to its manifest and bind the same root identity and final dpkg status. Other normally installed packages and independently admitted family upgrades are checked through the complete current dependency and reverse-dependency closure. These source receipts continue to report guest and production qualification as false.

Normal source-archive modes may remain unchanged or lose exactly the bits
selected by the producer's normal 0022 or private 0077 umask. R6 removes group
write from the original 0775/0664 members to produce 0755/0644. No added access,
owner, type, alias, packaging-rule or unrelated source-content change is admitted.

## Existing sysusers account lock under the shared kernel

The normally packaged `systemd-sysusers` first opens the existing
`/etc/.pwd.lock` with `O_WRONLY|O_CREAT|O_NOFOLLOW` and takes an exclusive OFD
lock with `F_OFD_SETLKW`. This happens before loading passwd/group and also
happens when the initialized normal root needs no account changes. The
selected normal lock is an empty, single-link, root-owned 0600 regular file.
The producer must preserve that inode; this policy does not create it.

`native-sysusers-source.json` binds the unchanged gentmp2 executable/unit and
the exact normal source call chain. The linker gives only the `/etc` directory
and the regular `/etc/.pwd.lock` file narrower labels. It preserves every old
actor's complete AV, constraint, transition and ioctl view, then adds only
setup's directory `write` and existing lock `write`/`lock`. Directory
`add_name`/`remove_name`, lock creation/replacement and account/password
database writes remain forbidden. `/etc/selinux` keeps the original directory
type and its original neverallow. Missing lock or requested account updates
therefore remain visible failures, rather than gaining generic `/etc` writes.

The source-owned verifier compares the setup role's full file/directory vectors
for every concrete object and the real class-aware file-context matches for the
two selected paths, neighboring names, the policy subtree and account files.
Setup is checked separately at raw TE and every sampled source/target MLS
combination: its s0 startup write remains subject to the original category
constraints. The unchanged hardware/uevent relabel guards stay unreachable
for both old and new lock objects; their exact full statements are checked.
The remount role's complete object matrix follows the same preserved source
vectors for both aliases. These static proofs do not imply sysusers runtime
success; a fresh enforcing normal boot must supply that evidence.

### Fixed normal Netplan configure branch

The complete Ubuntu source admission now binds the normal
`netplan-generator`/`libnetplan1` 1.2-1ubuntu5.1 payload and the complete 18-ELF
dependency graph. The selected public input is exactly the 49-byte
`/usr/lib/netplan/00-network-manager-all.yaml` shipped by ubuntu-settings; it
selects NetworkManager globally and contains no interface definitions.
The two other input directories must contain no files. An added, changed,
symlinked or separately linked input is rejected before native initialization.
Other YAML profiles, including the original physical host's configuration,
require a separate actual source selection and are not marked qualified.

The original unit and package ELF remain byte-identical. Its new execution
role can read the selected YAML, load the twelve newly typed dependency
inodes, and reuse the existing nine-inode console shared-library type (four
are actual dependencies; all nine members remain explicitly pinned).
The role does not inherit the generic native service attribute or executable
permission for the entire runtime library type. The normal libselinux
constructor requires only traversal and statfs/statvfs of the already mounted
selinuxfs; its missing-mount /proc scans are not admitted, and its F_OK check
does not authorize reading the SELinux configuration body.

For the captured input, configure only creates NetworkManager's runtime
parent and conf.d, writes an empty temporary file, and renames it to
`/run/NetworkManager/conf.d/10-globally-managed-devices.conf`. Re-entry removes
that prior typed output. This was observed twice with the same normal ELF and
all dependencies copied into a fresh private chroot in isolated network and
mount namespaces. That observation proves the package's file operations,
not SELinux enforcement or production readiness.

SELinux confines file mutation to the new output type in the existing
NetworkManager runtime family; the fixed source and unit bind the basename
and command line. Other pre-existing NetworkManager file types, systemd
units, account data, interfaces, sockets and child execution remain
inaccessible to this role.
The two unit ExecStartPost udevadm commands are separately started by PID 1
and continue to use the udev execution role.

The normal producer derives Netplan aliases after remount, derives sysusers
aliases last, then verifies every component against the final linked binary.
All original actor vectors, transitions and extended ioctl masks are
preserved. The explicit Netplan matrix covers file, directory, device,
filesystem, capability and socket classes. Read-only fixture admission reports
`runtime_qualified=false`; successful source checking never counts as a
running network service or an application business gate.

The output filename is selected by the pinned normal configure ELF. The file
type transition covers newly created regular files under the existing
NetworkManager runtime directory type; it is not a basename access-control
rule. Other pre-existing NetworkManager file types remain inaccessible to
this role. The file-context matcher records the expected fixed output and its
six-character temporary names, but does not constrain creation by filename.
