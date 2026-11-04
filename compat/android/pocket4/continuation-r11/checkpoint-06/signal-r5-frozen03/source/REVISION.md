# Isolated signal runtime r5

This source revision addresses the three blockers in the independent r4 review.
It does not authorize an Android run. No a04 input, nonce, image, private cell or
commercial-app action is created by this bundle. R4 remains immutable and BLOCKED.

## Exact cleanup despite failures

R5 retains the original v5 function definitions for comparison and negative
controls. Its active cleanup is cleanup_owned.OwnedCleanup.run. All other retained
functions are unchanged in the actual loader AST.

Cleanup installs an in-memory result before starting. Each evidence-write error
is preserved, including the first error, while later cleanup phases continue.
Resource observation, held-FD release, the private daemon stop, each individual
unit retirement and final preservation readbacks have separate error boundaries.
A failed write or observation cannot turn a failed run into PASS. Failure to
write runtime-result.json also leaves the emitted terminal state failed.

A late launch observation is reconciled only against the fixed private unit name,
nonce-bearing Description, actual InvocationID and exact ControlGroup. An unknown
or changed generation is never stopped. An unobserved launch that currently has
no unit remains an unresolved failure, with no completed-retirement claim.

Every verified unit receives one stop regardless of MainPID. A zero MainPID and
an empty root cgroup.procs do not prove that its child groups are empty. R5 reads
the hierarchical cgroup.events populated field and pids.current, and requires
both zero plus the root process list empty. Final manager identity is checked
independently from cgroup evidence. A failure on one unit does not prevent
retirement attempts on other exactly owned units.

The original cgroup directory is held across stop. Renaming it or substituting
an empty directory cannot prove the original domain empty. The actual Pocket4
cgroup2 control found that an unlinked directory still reports nlink=2 through
its held FD. The production deletion proof therefore verifies cgroup2 filesystem
type and disappearance of its always-present cgroup.events and cgroup.procs via
that original FD, while its original path remains absent. The exact source path
was exercised against a real empty child cgroup and that child was removed.

These observations cover the exact unit cgroup and explicitly tracked original
init/fixture child. They are not a claim about arbitrary escaped descendants.

Kernel reference for hierarchical counters and removal semantics:
https://docs.kernel.org/admin-guide/cgroup-v2.html

## Classpaths from both actual roots

The fixed framework epoch permits legitimate separate zygote and init mount
namespaces. It did not prove that a pathname resolved to the same jar in both.
The historical activation itself records different mount namespaces.

R5 holds the fixed private zygote procdir, pidfd, mount namespace FD and actual
root FD. For every required jar, it simultaneously opens the path through that
root and the command's held init root. Device, inode and size must match. Both
FD metadata records must remain unchanged around the streamed content hash.
Different mount namespaces are allowed; different backing files fail closed,
even when their initial bytes are identical. No Main classpath is substituted.

The existing bounded environment, path-count, per-file, total-byte and deadline
limits are unchanged. The shared namespace helper source/binary qualification
and all original Main/private epoch, package, UID, nonce and mapping checks remain.

## What actually ran

The draft02 receipt records:

- 15 controls invoking the actual frozen r4 and current r5 cleanup functions.
  The systemctl/props/journal transports and regular-file cgroup counters are
  explicitly declared seams. The old evidence-write and MainPID=0/subtree bugs
  are reproduced by the actual old function.
- 6 actual paired-root/file-descriptor controls, including same content on a
  different backing file, actual own procdir/pidfd/mount/root acquisition, and
  an owned child exit/reap.
- The original 35 host controls and 13 admission/loader controls.
- Actual AST comparison of all 18 original definitions; the active cleanup
  override is independently identified.
- The exact production cgroup2 deletion proof on a real empty child of the
  owned host control job, with exact removal.
- Four actual, read-only external preparation qualification gates are supplied
  in the separately pinned finalization receipt.

The real MainPID=0 plus live child-subgroup systemd fixture is prepared in
owned_cleanup_fixture.py and owned_cleanup_fixture_child.py. It has NOT RUN at
source freeze. Default invocation prints a plan and starts nothing. A separate
independent admission is required for --execute-once with the final manifest pin.
OWNED-UNIT-FIXTURE.md gives its exact scope and resource protocol.

Draft01 is preserved. Its regular-filesystem control did not establish cgroupfs
post-rmdir link-count semantics. The first tiny kernel experiment rejected its
incorrect assumed outer-job prefix before making any cgroup mutation. A second
experiment used the observed actual user-manager job scope and established the
real nlink/control-file behavior. None of these records is relabeled as an Android
or commercial-app result.

The a03 original 134 launch failure and exact cleanup remain in the inherited
evidence. No ARM64 probe verdict came from that failed instrumentation launch.
R5 still needs final source review, the separately admitted owned systemd fixture,
and a fresh private Android qualification before any deployment decision.

## Fixture02 correction after the real fixture01 failure

Fixture01 actually created its single service with a 33-hex nonce. The unchanged
production planned() guard correctly refused that identity, so production
cleanup issued zero stops and the original fixture remains FAILED. Root retired
the exact original invocation separately. Its pre-recovery child was already
gone, so that recovery does not prove stopping a live populated child subtree.

The new fixture02 uses fixed nonce 5c53c248004139cd14513e8d88023c18 (32 hex).
Both default PLAN and execute invoke the unchanged actual production planned()
before source-contract checks, claim creation, directories or commands. Worker
identity constants are parsed without importing its effectful entry and must
match. Four actual offline controls reproduce the old default/production mismatch
and prove that the old 33-hex value reaches no follow-on action in either new
entry. All five production files are byte-for-byte unchanged from frozen02.

The original fixture01 source, failed result, separate exact recovery, old peer
review and explicit correction are retained. Fixture02 has NOT RUN at this
source freeze; a separate exact admission and actual result are required.
