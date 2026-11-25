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
  (basename to byte count and SHA256), and `source_roundtrip` (the three patched
  source paths to byte count and SHA256). Keep the original command and source
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
