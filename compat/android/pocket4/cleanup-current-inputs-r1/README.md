# Pocket4 current inputs and cleanup reference observation

This capsule provides a current-input verifier and a source replacement for
one cleanup observer function. The observer distinguishes a path alias from
an actual consumer, checks references from every visible task, and obtains
missing namespace views through children it creates and owns.

The replacement has **not been applied to the live helper**. It does not
authorize retirement, change Android packages or images, or bypass the active
coordinator. Test fixtures and collector children are explicitly accounted for
in the qualification receipts. On Pocket4, the exact published candidate passed
**54 ordinary-UID controls, 29 existing-host namespace controls and 10 private
namespace integration controls in both normal and `-O` modes**.

## Historical selected-input readback

At **2026-11-09 04:10:06 UTC**, the real selector's **13 preparations** and
**721 retained records** were verified. Their union was **723 files /
20,619,335 bytes**, because two selected preparation files were outside the
retained list. Full SHA-256, size, single-link regular-file, no-symlink
component traversal, held-descriptor identity and final named-path checks
passed. The compact receipt is in [live_721_readback.json](live_721_readback.json).

This is a historical observation. CURRENT has advanced since that readback;
this capsule does not claim that the new CURRENT generation was reverified.
A new cleanup attempt must reread the actual current generation:

```sh
python3 -I -B verify_current_inputs.py --current /home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json
```

The verifier supports the actual current, selector and retained-manifest
schemas, rejects conflicting generations or bindings, and fails closed on
duplicate keys or paths, changed identities, symlinks, hardlinks, signing
material and bounds. The 723-file union does not cover the executor's additional
22 Camera inputs and is not the 42-app runtime acceptance result.

## Reference and mount semantics

The exact baseline helper is
`cleanup/apps-old-root-retirement-20261108-8b88-r1/executor.py`,
SHA-256 `22e7e85962c52a5cf44759dd99610d16293a0f8573ee68b8b9da4c89b1c7911a`.
Its complete source is bundled only to reproduce scope verification.
**Never execute or import fixtures/executor-baseline.py.**

[reference_observer.patch](reference_observer.patch) replaces only
`live_references(roots)`. All code outside that function, including target
selection, current-input checks, signing release, owner policy and deletion,
remains byte-identical. The original caller's three veto lists remain
`process_or_owner_hits`, `mount_hits` and `coverage_errors`.

| Observation | Result |
| --- | --- |
| Strict ancestor bind exposing another path to a target | A verified path alias; no busy finding by itself |
| FD, cwd, exe, root, mapping or owner argument referring to the target through an alias | Actual-reference veto |
| Mount root or mount point at or below a target, including through a verified alias | Mount veto |
| Unreadable, changing, ambiguous or incomplete evidence | UNKNOWN |

Each alias is resolved from the corresponding task's held root descriptor with
component-by-component O_PATH / O_NOFOLLOW traversal. The final target metadata,
device/inode and mount ID must match the pinned target and mount view; the parent
mount chain must reach that view's root. Temporary descriptors close before
the task FD census. Alias indices and mount classification are cached only
under the same namespace, root identity/mount ID and unchanged mountinfo bytes.
Every task still has its actual identity, root and mountinfo checked.

The observer includes non-leader TIDs and itself. Device/inode matching catches
FD and map aliases; namespace-specific path matching also catches deleted-path
and owner-argument references. FD sets, task/process sets, mount views and
target metadata are rechecked. A narrowly verified empty single-leader zombie
may be treated as having no references; missing namespace links alone do not
qualify. Hardlink observation does not change the caller's hardlink policy.

## Complete namespace views

Only a task in the observer's own namespace with the same pinned root identity
and mount ID can directly establish that view. A foreign task's matching root
inode cannot prove completeness: it might be chrooted into a hostfs alias.

The scanner fixes namespace objects using actual held FDs from host nsfs
mounts, observed task namespace entries or namespace FDs in task descriptor
tables. Namespace type and device/inode are checked. The embedded collector
then forks its own children and calls setns directly; it does not mount,
unmount or change the parent's namespace. Child identity, parentage, PID FD,
namespace, root FD/mount ID, native root and repeated mountinfo are verified
while the child waits on its private control pipe. The scanner checks those
live facts again before using the view.

External JSON, caller-supplied PIDs or dictionaries cannot establish coverage.
Unknown nested namespaces, inaccessible handles, changed witnesses, timeouts
or incomplete child retirement remain UNKNOWN. The result reports exact owned
child terminal records and lifecycle counts. All collector children must be
reaped with exit zero for successful production closure. The host qualification
also deliberately kills children or forces setup errors to prove that nonzero
retirement is rejected; those negative-control exits are recorded separately.

The kernel's observed nsfs `mnt:[positive inode]` roots are treated as opaque
objects. Their mountpoints still veto targets; opaque roots never participate
in filesystem ancestor translation. Other non-absolute formats remain UNKNOWN.
The historical format observation is pinned in
[namespace-format-observation.json](namespace-format-observation.json).

Bounds remain 128 exact targets, 100,000 target entries, 20,000 tasks,
500,000 descriptors, bounded reads/hits and a shared 45-second budget.
The collector additionally bounds children and aggregate mountinfo, reserving
time for their retirement. This is a snapshot, not a future-writer lock.

## Reproduce and distinguish qualification

[test-results.json](test-results.json) separates three groups. Passing source
controls is not deletion admission or app production acceptance.

| Group | Entry | Privilege | Expected controls per mode |
| --- | --- | --- | ---: |
| Input/reference regression | Two unittest modules below | Ordinary Linux UID | 54 |
| Existing Pocket4 namespace qualification | verify_namespace_collector.py | Root / namespace capability | 29 |
| Complete scanner with owned private PID/mount fixtures | verify_isolated_alias_views.py | Root / namespace capability | 10 |

Run ordinary controls from this directory, in both modes:

```sh
python3 -B -m unittest -v test_verify_current_inputs.py test_reference_observer.py
python3 -B -O -m unittest -v test_verify_current_inputs.py test_reference_observer.py
```

A08 uses an isolated Python loader with this directory explicitly on its import
path and requires the exact count, zero failures/errors and zero skips. The
real FD/mmap control must detect its own held references. Unrelated shared-host
visibility failures remain UNKNOWN; the ordinary-UID receipt is not a proof
that every host process is readable.

Scope replay is portable and does not execute the historical helper:

```sh
python3 -I -B verify_reference_patch.py
python3 -I -B -O verify_reference_patch.py
```

The host qualification requires its observed count explicitly:

```sh
sudo -n python3 -I -B verify_namespace_collector.py --expected-persistent-count 6
sudo -n python3 -I -B -O verify_namespace_collector.py --expected-persistent-count 6
```

Those 29 controls inspect the actual Pocket4 namespace objects and are not part
of ordinary CI. Their receipt binds both modes, the exact embedded factory,
six observed views, positive and negative ownership controls and child exits.

The private integration entry has no snap path, namespace-ID or six-namespace
requirement. It creates its own private mount and PID namespaces, installs a
private procfs, and checks alias-only success plus actual FD/mmap/cwd/argv,
target-source mounts, alias mountpoints, a shadowed wrong-inode alias and an
FD-only persistent namespace. It verifies the exact FD-only witness's terminal
record and restores the alias-only control afterward. The existing parent
namespace/mountinfo must remain unchanged and its owned fixture directory must
be absent before success is reported.

Run it with a newly created, empty, owned fixture base, then remove that empty
base after the script has retired its own temporary child directory:

```sh
sudo -n env NAMESPACE_FIXTURE_DIR=/absolute/owned/fixture-base python3 -I -B verify_isolated_alias_views.py /absolute/capsule/reference_observer.py
sudo -n env NAMESPACE_FIXTURE_DIR=/absolute/owned/fixture-base python3 -I -B -O verify_isolated_alias_views.py /absolute/capsule/reference_observer.py
```

A08 may run that explicit privileged private-fixture group after its source
pins are checked. It must not substitute the Pocket4 host group or count an
unsupported namespace operation as a skip.

## The final two historical retained roots

[remaining-roots-readback.json](remaining-roots-readback.json) retains the
independent read-only evidence. The original 661-byte fence remains bound to
its original request; canonical backups and an absent historical job or unit
do not supply positive owner-terminal evidence.

The **2026-11-09 04:37 UTC** original-image registry observation found
`org.droidloom.qa.amazon.r3`, version 1, app ID 10154, still consuming its
signing lineage. It is outside the production cohort. The receipt contains
only the necessary package/certificate/registry and data-count metadata.
Normal PackageManager retirement, exact identity and all-user/data custody
checks, and subsequent absence of every signing consumer must precede a
separate signing-root retirement. The capsule performs none of those actions.

[FILES.json](FILES.json) is the publication whitelist, excluding only itself.
It retains necessary source, exact baseline fixtures and compact evidence;
prototype scanners, app-data bodies, private material and full registries are
excluded.
