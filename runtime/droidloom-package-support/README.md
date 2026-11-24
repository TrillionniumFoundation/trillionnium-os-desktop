# Package setup and first Pocket4 activation

The package helper maintains the ordinary package lifecycle and the first
physical shared-kernel activation. First activation is a separate command path:
it preserves the existing Android data and metadata images, admits the normal
release inputs, and prepares one one-shot boot. A staged or installed release is
not a runtime or application qualification result.

## Commands

Run the helper from the exact normal host release being prepared. Its running
ELF must match that release's host manifest. First activation requires the
original host's root credentials and native system manager.

**inspect-first-original** is read-only. It reports the original cell and userdata
identities, their ext4 profile, actual configured identity delegation, and the
native manager, cgroup, user-actor and loop preflight. It neither acquires a
production reservation nor creates the setup lock or a maintenance fence.

**stage-first --plan /protected/first-activation.json** imports and verifies the
normal release in
/var/lib/droidloom/activation-staging/&lt;plan-sha256&gt;/{root,work}.
Both the plan and the staged receipt are private root-owned files. The command
performs native package dependency checks, real label-tool probes and a dry run,
original-data inspection, and a GRUB preview. It leaves live services, installed
files, the boot selection and the original userdata unchanged.

**activate-first --generation &lt;plan-sha256&gt;** rereads the exact private
generation, repeats its preflights, retires the original native owners under the
same exclusive setup-lock description, installs and reads back the release,
applies the normal labels, publishes the selected generation, and arms one
one-shot GRUB entry. The command does not reboot. It keeps the existing default
and recovery kernel until real boot and application acceptance have succeeded.

## Normal input plan

The strict plan schema is **droidloom-pocket4-first-activation-v1**. File pins
contain an absolute path, complete bytes, and lowercase sha256. These pins
select ordinary material bytes; they cannot represent a live owner, loaded
policy, successful resource retirement, namespace authority, or installation
permit.

| Field | Required source |
| --- | --- |
| source_commit, source_tree | The clean source identities in the normal host release. |
| host | The normal producer's release record, host manifest and host archive. |
| platform | The normal complete peer kernel and module manifests, original kernel-source custody, final prepared initramfs, and the two fixed normal native Debian packages. |
| android | The complete four-image cohort; same-generation runtime and four original query inputs; device manifest and bank; source cell template; and the normal five-file calibration MAC release. |
| original | The original member returned by this helper's read-only inspection of the actual fixed Pocket4 userdata. |
| labels | The admitted ordinary setfiles, matchpathcon and producer libsepol inputs. |

The host importer accepts only the compiled normal product inventory. The
platform importer checks the entire module namespace and each complete file,
the normal native package payloads, and the final initramfs rather than treating
its base image as the final boot image. The MAC transport is checked against its
inner declarations, exact normal policy inputs and same-generation image pins.
The target runtime must still establish its own actual loaded-policy witnesses.

## Existing data and the dedicated identity

This first path supports Pocket4's existing user 1000 image pair and the
observed legacy mapping of 100000:100000. The production cell selects the
already configured dedicated account's 200000:100000 UID and GID ranges.
Both transitions are explicit. The real IdentityAuthority::inspect must
accept the dedicated local account and exact grants; the helper never expands
the desktop user's grant or writes the delegation files.

The original ext4 guest owners, UUIDs, feature sets, backing inodes, lengths and
modification times are preserved. The regular image files are never copied,
formatted, replayed, recursively changed, or removed by activation. Applying
their fixed outer SELinux labels is a controlled operation on the same held
readonly descriptors. Only the observed ctime advances after the real xattr
readback; no global identity check is weakened.

The selected persistent-data contract describes the original on-disk guest
owners. During real boot the existing persistent-data consumer verifies those
owners before applying the dedicated namespace's idmapped mount, then verifies
the same filesystem inode and expected mapped ownership. A successful
configured-delegation preflight does not claim that this kernel operation has
already happened.

## Installation and failure behavior

Every live mutation requires the non-deserializable original-owner permit.
Actual original PIDFDs, systemd invocations, cgroups, original data files and
loop ownership are checked. All routine preflight checks happen before the
first failure fence. After that point a failure retains the original fence;
there is no command that recreates a permit from a receipt or discards a stale
fence to resume an uncertain transaction.

Normal native packages are installed through dpkg, including their real
maintainer scripts. Their final status, metadata and complete payload are read
back after labeling. Product files have fixed destinations, original-byte
backups and exact post-install observations. Only the five known legacy
user-owned executables and their two fixed old parent directories have a
narrow first-install ownership transition. The helper does not recursively
change ownership or touch unrelated services.

The production and observer units are enabled without starting them on the
old kernel. Labeling uses the admitted normal setfiles producer and explicit
mount exclusions. Original setup, cell, selection, fence and userdata objects
have separate typed transitions. The four original query inputs receive their
fixed Android labels after the general native labeling pass.

GRUB is reobserved after all ordinary labels are complete. The new script,
generated configuration and environment are individually labeled before their
final observations. The original failure fence is consumed only after the
committed selection, ordinary products, native packages, query inputs and
one-shot boot have all passed their final readbacks.

The activation receipts report runtime_qualified and production_ready as false.
Physical boot, service readiness, original-data continuity, application
business checks and eventual removal of obsolete versions remain separate
real acceptance work.
