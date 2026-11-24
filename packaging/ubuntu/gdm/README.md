# GDM dynamic filesystem lifecycle candidate

The selected Ubuntu GDM 50.1-0ubuntu0.1 creates private dynamic greeter homes
owned by UID 60578..60705 and filesystem GID 65534, with mode 0700. The
session's primary GDM group is separately the selected `gdm` group, GID 121.
The original root manager cannot write, enumerate or retire those private
objects while the original Android DAC_OVERRIDE assertions remain enforced.
The first local candidate corrected the environment-file writer. The third normal candidate replaces persistent in-place ownership transfer
with copying into new inodes. It also keeps the existing creation, failure,
cleanup and exclusive-home-reuse checks.

## Maintained normal source

Version `50.1-0ubuntu0.1+p4fsuser3` is normal source commit
`762ea3ef217af34eb31a1f8ea773c2d543e6653a`, tree
`a355eda626ec5a0f78faa51e7078aeb522608433`.
`source.lock` binds the unchanged original Ubuntu source archives, the three
exact quilt patches, all 15 maintained source files, normal Debian build,
emitted `.deb/.dsc/.buildinfo/.changes`, and both normally produced root-test
ELFs with their complete TAP logs. All original Debian archive members
except the three appended patches, series and changelog retain their exact bytes.
The normal `dpkg-buildpackage -F -j2 -us -uc` uses the original Debian rules
and test runner. No test is disabled and no physical package is installed.
These local modified packages are unsigned, not Ubuntu-signed releases.

Normal `dpkg-source --after-build` unapplies quilt. Independent extraction of the new normal `.dsc` reproduced all 15
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

Persistent `config` and `state` handovers first acquire the fixed root-owned
seat parent. Each source inode is held through a no-follow descriptor; source
body reads run under its actual old filesystem UID. All source entries must
have that same owner/group, ordinary kinds, no privilege bits, and one link
for nondirectories. Every regular file is copied into an exclusive new inode,
then fully reread and compared by SHA256. Symlinks are copied as link text;
the copier never follows them. Source ownership, permissions and bytes are
never changed to make copying succeed. Unreadable mode-000 data is refused.

The fixed `.config-handoff` or `.state-handoff` root is initially root:root
0700. Its children are new inodes and receive their final UID while the root
remains inaccessible to that UID. The held source inode/name/metadata checks
run after copying, before publication and again after the atomic exchange.
Publication uses `RENAME_EXCHANGE` within the same root-owned seat directory.
This avoids the moved-directory write check needed to update `..` across
parents, which the deliberately unprivileged root manager cannot bypass.
Only after verification does the manager hand the newly created top inode
to the next UID. There is no privileged chown or chmod of any old settings
inode, so an old owner's late hardlink or rename cannot transfer authority
to a new user. An old writable FD still refers exclusively to the old inode.

On a detected source change after exchange, rollback is attempted only when
both paths still name the exact two held roots; neither root is guessed or
deleted. The failed handoff remains visible to the operator and is refused
on a later attempt. Before any exchange, cleanup can adjust only new,
unpublished inodes under its still-private root. Old-snapshot retirement
uses only the old filesystem owner's normal unlink permissions. A refusal
preserves the incomplete handoff and causes launch failure. It never adds
permissions to an old mode-000 directory. Copying is bounded by 64 levels,
32768 entries, 16 MiB per file, 64 MiB total and a 30-second monotonic deadline.

Home creation remains exclusive. Home cleanup removes children as their
owner and unlinks the top directory through its held root-owned parent.
Failed cleanup retains the dynamic-user indexes and UID. Environment
preparation failure now stops the actual session conversation; a later
session-opened callback cannot start a greeter without a successfully
prepared environment. It no longer silently falls back to ephemeral state.
The stock migration of the fixed pre-dynamic GDM state remains distinct;
a migration error is propagated rather than ignored.

The normal test ELFs must pass seventeen real root subprocess cases with
only CHOWN/FOWNER/SETGID/SETUID. The original three cover private writer
replacement and credential restoration. Fourteen lifecycle cases include
real synchronized old-UID hardlink, rename and write attempts; failure must
occur at the source-validation gate and retain original ownership. A live
old writable FD must be unable to modify the new inode, and the old UID must
fail to traverse the private staging root. Test-only linker wrappers cover
the normal Ubuntu large-file/FORTIFY entry points without disabling FORTIFY,
LTO, the original rules, or the production code. Normal unprivileged test
skips are not counted as positive evidence. These tests run on host
7.0.14-p4cred1; they do not qualify the final enforcing 6.18 desktop session.

The original GDM close path waits for its direct worker. That is not evidence
that every descendant or old writable FD is gone. This copy design therefore
does not depend on whole-session quiescence, and does not claim that a worker
wait proved it. Metadata bookends describe the observed copy interval;
subsequent writes through retained old FDs belong to the retired inode and
cannot modify the published snapshot.

## Fresh fixture admission and actual replacement

BootPlan's `gdm_candidate` keeps the exact `{artifacts:{...}}` structure.
There are eighteen source-owned FilePin entries. Input paths may relocate
only while preserving each fixed basename, size and complete SHA256.
Admission uses held no-follow descriptors, copies to a private root, and
checks full bytes. Missing, extra, substituted, truncated and alias inputs
fail. Both source packages, exact archive membership, three quilt patches,
normal rules, source round-trip, build outputs and seventeen root cases are
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
