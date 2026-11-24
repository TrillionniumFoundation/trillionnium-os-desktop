# GDM filesystem-credential candidate

The selected Ubuntu GDM 50.1-0ubuntu0.1 creates its dynamic greeter home with
UID 60578..60705, GID 65534 and mode 0700. The original manager then writes
.config/environment.d/gdm.conf as host root. With the original Android
DAC_OVERRIDE assertions preserved, that write fails. Moving only the final
directory chown is insufficient because the home is already private.

The normal source package 50.1-0ubuntu0.1+p4fsuser1 scopes only the calling
thread's fsuid/fsgid to the already held dynamic user's IDs, verifies both
changes, performs the complete GIO write and explicit close/atomic rename,
then restores both IDs and verifies the original capability vector. A failed
restoration is fatal; a write error still restores identity. There is no
process-wide credential change, private-home permission relaxation, account
lookup, CAP_SETPCAP or DAC privilege. The exact required GDM capability set is
CHOWN/FOWNER/SETGID/SETUID. Other threads retain their original credentials.

## Maintained normal sources

source.lock binds the exact original Ubuntu .dsc/.orig/.debian archives,
maintained source commit 5a3885a1a5db0d306d57b5161e77865c574017ec, complete normal
Debian build, emitted .deb/.dsc/.buildinfo/.changes, and actual root test ELF
and TAP evidence. The quilt patch and C regression here are byte-identical
to the files in that normal source package. All original Debian source
members other than the new patch, series and changelog must remain unchanged.
The build used dpkg-buildpackage -F -j2 -us -uc and the original Debian rules;
there was no nocheck, altered upstream test runner or physical installation.
The local candidate is unsigned; it is not represented as an Ubuntu-signed
modified package.

The normal unprivileged Meson run reports three root-only skips. Those skips
are not the claimed positive evidence. The same normally built production
writer test ELF was separately copied to a root-protected directory and ran
three real subprocess cases with only the four required capabilities:

- A private 0700 home first rejects the original root write, then the actual
  new function creates and replaces the 0600 configuration. A second thread
  continuously verifies unchanged root filesystem credentials.
- An actual I/O failure returns after restoring both filesystem IDs.
- A real seccomp denial of restoration causes the required fatal exit; the
  parent verifies the real wait status and diagnostic instead of permitting
  execution under unproven credentials.

Those tests ran on the build host's 7.0.14-p4cred1 kernel. They do not certify
GDM on the final 6.18 shared kernel or the final enforcing SELinux/AppArmor.

## Fresh-fixture admission

The BootPlan field is gdm_candidate, containing exactly {artifacts:{...}}
with the fifteen FilePin names fixed by source.lock. Paths may be relocated
only with their original fixed basenames, lengths and complete SHA256 values.
The complete sources, normal build and real test artifacts are copied from
held no-follow descriptors into a private qualification directory and read
back before package analysis. Missing, extra, substituted or truncated inputs
are rejected.

The fixture selects only usr/sbin/gdm3 from the normally built gdm3 .deb.
It does not extract that archive's namespace or follow its three reviewed
unrelated aliases. The actual original and new ELF must both have the same
nine fixed DT_NEEDED entries, original interpreter and nonexecutable stack.
The new ELF must import setfsuid/setfsgid; private RPATH/RUNPATH and text
relocations are refused. The GDM manager does not have a libgdm.so DT_NEEDED
entry. None of the other companion package files is silently substituted.

Only an independent original GDM ELF matching the selected fixture manifest,
full original SHA, root ownership, 0755 mode and one link may be replaced.
The original descriptor remains held through replacement. The candidate
is read back after an atomic same-directory rename and fsync. The normal
package database must be present and retain exactly its previous bytes.
No maintainer script is run and no installed-version claim is rewritten.
Normal physical deployment later must use dpkg and the complete matching
runtime package dependency set; this qualification overlay is not that step.

Full non-calibration prepare-boot requires this candidate. The finished ext4
image must retain the candidate's exact bytes and the normal GDM label and
inode metadata. Calibration may retain the specifically admitted original
ELF. Runtime acceptance still requires real GDM startup and the dynamic
greeter path; a successful autologin desktop alone is insufficient.

The ignored actual_normal_gdm_artifacts_admission test consumes the actual
fifteen pinned artifacts into a new empty qualification directory, runs the
same producer admission, and verifies six real malformed-input rejections.
It neither runs GDM nor modifies a fixture. It uses only these two explicit
inputs: DROIDLOOM_GDM_ADMISSION_INPUTS and DROIDLOOM_GDM_ADMISSION_WORK.
