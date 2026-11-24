# GDM dynamic filesystem lifecycle candidate

The selected Ubuntu GDM 50.1-0ubuntu0.1 creates private dynamic greeter homes
owned by UID 60578..60705 and filesystem GID 65534, with mode 0700. The
session's primary GDM group is separately the selected `gdm` group, GID 121.
The original root manager cannot write, enumerate or retire those private
objects while the original Android DAC_OVERRIDE assertions remain enforced.
The first local candidate corrected the environment-file writer. This second
normal candidate also closes creation, persistent-data handover, failure
handling, cleanup and exclusive reuse of the dynamic home.

## Maintained normal source

Version `50.1-0ubuntu0.1+p4fsuser2` is normal source commit
`783240ad9e96283364278e7594d4be986fddbf17`, tree
`5d97a87b0ec2e5d12bfc547b22af23fb30d3109e`.
`source.lock` binds the unchanged original Ubuntu source archives, the two
exact quilt patches, all 14 maintained source files, normal Debian build,
emitted `.deb/.dsc/.buildinfo/.changes`, and both normally produced root-test
ELFs with their complete TAP logs. All original Debian archive members
except the appended patches, series and changelog retain their exact bytes.
The normal `dpkg-buildpackage -F -j2 -us -uc` uses the original Debian rules
and test runner. No test is disabled and no physical package is installed.
These local modified packages are unsigned, not Ubuntu-signed releases.

Normal `dpkg-source --after-build` unapplies quilt. The initial controller
recorded that expected build-directory change; that record is retained.
Independent extraction of the new normal `.dsc` then reproduced all 14
maintained source files byte for byte, and the canonical Git source stayed
unchanged. Admission requires that complete round-trip table, not just a
successful build status.

## Filesystem identity and lifecycle

The existing per-thread fsuid/fsgid guard covers the complete synchronous
GIO environment-file replacement, including stream close and atomic rename.
It verifies both transitions and restoration, including the original
capability vector. Failure to restore is fatal. No process-wide credentials
change, directory permission relaxation for other users, DAC capability or
CAP_SETPCAP is introduced. The GDM process retains only its required
CHOWN/FOWNER/SETGID/SETUID capability set.

The new internal lifecycle helper opens fixed parent directories and holds
no-follow inode descriptors. `openat2` rejects aliases and mount crossings.
Private child traversal occurs under that object's actual filesystem owner;
root only performs permitted CHOWN/FOWNER metadata work on held inodes.
Mode-000 directories temporarily gain owner traversal only, then recover
their exact original mode on every return path. Symlink contents are never
followed. Metadata handover rejects hard-linked regular files, devices,
privilege bits and unrelated account owners. Only root, the reserved dynamic
UID range and the fixed original Ubuntu `gdm` account may supply previous
GDM settings. The account name is source-owned, not caller supplied.

Home creation is exclusive and refuses existing entries. Cleanup removes
children as their owner and restores root filesystem identity before
unlinking the top-level home from the root-owned anchor. Traversal is bounded
by depth, entry count and a 30-second monotonic deadline. A failed cleanup
retains both dynamic-user indexes and does not report successful retirement
or release the UID. Persistent config/state handover remains incremental as
in the original recursive metadata operation; failure does not claim a full
rollback. Directory modes and calling-thread credentials are restored.

The normally produced test ELFs pass ten real root subprocess cases with
only the required four capabilities. The original three cases exercise
private writer replacement, I/O-error restoration and fatal denied
restoration. Seven new cases exercise mode-000 trees, write/retire/recreate,
foreign-owner rejection, hard-link rejection, root aliases, original GDM
settings handover and failure without DAC bypass. Another thread checks that
its credentials remain unchanged. The normal unprivileged test skips are
not counted as positive evidence. These tests run on host 7.0.14-p4cred1;
they do not qualify the final 6.18 kernel or enforcing desktop session.

## Fresh fixture admission and actual replacement

BootPlan's `gdm_candidate` keeps the exact `{artifacts:{...}}` structure.
There are eighteen source-owned FilePin entries. Input paths may relocate
only while preserving each fixed basename, size and complete SHA256.
Admission uses held no-follow descriptors, copies to a private root, and
checks full bytes. Missing, extra, substituted, truncated and alias inputs
fail. Both source packages, exact archive membership, two quilt patches,
normal rules, source round-trip, build outputs and ten root cases are
required.

Only `usr/sbin/gdm3` is selected from the normal package. Both original and
candidate ELF must retain the same nine DT_NEEDED entries, original
interpreter and nonexecutable stack. The candidate imports setfsuid/setfsgid;
RPATH/RUNPATH/text relocations fail. No companion package is silently
substituted. Original dependency bytes remain bound to the selected native
fixture manifest.

Only the independent original GDM ELF with the fixed SHA, root ownership,
0755 mode and one link can be replaced. Its original inode remains held
through atomic same-directory replacement and fsync. A second whole-file
hash explicitly rewinds that original descriptor. Dpkg state is optional:
absence remains absence, and an existing status file keeps its identity and
complete bytes. No database or installed-version claim is fabricated and no
maintainer script runs. Physical deployment still requires normal dpkg.

The actual material-admission test runs the production reader on all
18 original artifacts plus six real malformed-input cases. The actual apply
regression uses the fixed original R91 public manifest and ten original
ELF/library files in private test roots. It invokes the complete real apply
function with absent and present dpkg status, verifies both original/candidate
custody, and rejects a changed original ELF before replacement. This is a
small apply fixture, not a claim of a full native-system or greeter boot.

The ignored tests have explicit inputs:

- `DROIDLOOM_GDM_ADMISSION_INPUTS`: root-protected new INPUTS.json.
- `DROIDLOOM_GDM_ADMISSION_WORK`: new protected admission work.
- `DROIDLOOM_GDM_APPLY_SOURCE_ROOT` and `DROIDLOOM_GDM_APPLY_MANIFEST`: the
  independent original selected public source and exact manifest.
- `DROIDLOOM_GDM_APPLY_WORK`: new protected apply work; sibling names are
  created for status-absent, status-present and changed-original cases.

Full normal preparation must subsequently verify the actual final ext4
candidate bytes and labels. Runtime acceptance still requires the real
GDM dynamic greeter, same-user environment proof, orderly exit/reentry and
normal desktop. Timed-login proof and dedicated greeter-home MAC are separate
source components. An autologin desktop or package admission alone does not
prove those runtime conditions.
