# Pocket4 current inputs and cleanup reference observation

This capsule contains the latest source for the bounded cleanup reference
observer and the current-input verifier. The replacement has **not been
applied to the live cleanup helper**. Source qualification does not authorize
deletion or establish Android/app production readiness.

This isolated revision passed **83 controls in both normal and -O modes on
Cloud Linux (UID 0)**: all 59 existing controls plus 24 focused empty-view and
representative-selection controls. The new proof controls use an explicit
test-only collector model. They do not establish real namespace or child
lifecycle qualification. The **20-case real private fixture also passed normal and -O on
Pocket4**, using kernel 7.0.14-p4cred1 and boot
97d9600f-e081-465c-9e6e-62651e09806b. Both modes bind the exact source before
and after execution and have positive complete H terminal evidence.

The prior published 13ad observer passed 59 Cloud controls and 15 real private
controls in both modes on Pocket4 kernel 7.0.14-p4cred1, boot
97d9600f-e081-465c-9e6e-62651e09806b. Its complete prior qualification, the failed
90a6 fixture attempt and older source evidence remain in
[test-results.json](test-results.json); none is relabelled as this revision's
host qualification.

## Separately retired review copies

Three exact owned Cloud source-copy roots were removed after published source
custody and peer release: 18 files, 289,339 logical bytes, then independent
absence readback. `remaining-roots-readback.json` preserves that narrow receipt
and its explicit `process_coverage_passed=false`. This recoverable review-copy
cleanup is separate from Pocket4 whole-root admission; no Pocket4 runtime,
Android image or application was deleted by this operation.

## Latest real host observation

The exact 50ea source completed a separate read-only scan at 10:44:22 UTC.
It found no process/owner or mount hits, but the result remained **UNKNOWN**:
one task/leader set changed, three processes disappeared, and the process set
changed. These existing vetoes prevented collector creation, leaving the empty
task view and namespace coverage unresolved. All zero created collectors were
closed; no deletion, Android action or CURRENT write occurred. The positive
durable process terminal was exit 0 with complete 2,327-byte output; process
success is not deletion admission. The exact diagnostic source, original
transport and result are appended to `mount-layer-observation.json`.

## Successful empty task mountinfo needs a complete view

The f091 whole-host preflight at 09:32:56 UTC correctly returned UNKNOWN and
deleted nothing. It found no process/owner or mount hits, but retained one
empty mountinfo, two FD-set changes, process-set change, two FileNotFound
errors and incomplete namespace coverage. Existing errors prevented collector
creation; the 26 uncovered namespaces were not individually proved impossible
to observe. The earlier shadow/stack errors did not recur in that run.

A separate 09:42:59 UTC diagnostic read only three named task views. It found
PID 1686 to be a stable ordinary avahi-daemon task with a restricted root and
two successful zero-byte mountinfo reads. The other two sampled threads had
stable FD number sets during that fixed 0.2-second pair. The preflight did not
record their starttimes: these later numeric-PID observations cannot establish
continuity with the original scan, disprove its FD churn, or recover any
missing task terminal. Exact evidence, positive H terminal identities and the
upstream Linux semantic reference are appended to
[mount-layer-observation.json](mount-layer-observation.json).

Only a successful exact empty task view enters the new pending-proof branch.
The first process pass still scans root/cwd/exe/FD/maps/argv, counts descriptors
once, and records the task/root/namespace and FD-number plus per-slot
device/inode baseline. It neither holds traversal FDs across the observer's
own census nor creates collector children early. Existing errors remain vetoes.

After the original process-set check, an owned native-root witness is required,
including when the empty task shares the observer's namespace. The task's root
display path is reopened from that witness root one directory component at a
time with O_PATH and NOFOLLOW. Actual mount IDs, devices, ancestry transitions
and the final device/inode/mount ID must agree with the separately held task
root. Noncanonical, deleted, symlink, missing or otherwise unexplained routes
remain UNKNOWN. A supposedly empty view containing a native mountpoint under
the proved root also remains UNKNOWN.

All native potential aliases stay in the reference index. Only verified
component-relative projections are added for the task root, and every
reference kind is scanned again with the original FD baseline. FD-set or
per-slot device/inode changes, changed task/root/namespace/raw view, unproved
FD-only or newly discovered namespaces, and collector failure remain UNKNOWN.
All owned children are positively retired before comparison with the original
process set. The collector factory is unchanged byte for byte.

For ordinary views, the first task that completes all existing checks becomes
the representative. Later tasks still undergo all checks and raw-view
comparison. The first representative is revalidated at the original final
points; losing it is UNKNOWN, with no replacement fallback. This removes an
unnecessary dependency on the last task, but does not clear previous errors
or lock out future writers or same-identity ABA changes.

## Why mount-layer selection changed

The earlier observer, SHA-256
311a943a3b3f2845c69ae1750eadb2e72b7058cac86c5c9ae39f18debc107aa5,
correctly refused an actual retirement preflight. Its 43 shadowed-alias and
18 ambiguous-alias errors included two structural cases independently
reproduced by bounded, stable reads:

| Actual view | Evidence | Correct treatment |
| --- | --- | --- |
| An inaccessible tmpfs bound over /home | The held path FD selected mount 196; the next component was ENOENT. The covering mount was a strict ancestor of the target. | Recognize that this particular pathname route is hidden, while retaining the potential alias for reference checks. |
| Two mount records at the same snap hostfs path | The actual held FD selected mount 437, whose parent was lower layer 1133. Traversal reached the exact target device/inode. | Select the kernel-reported layer and validate its parent chain. Mountinfo order and longest path strings are insufficient. |

[mount-layer-observation.json](mount-layer-observation.json) binds the exact
diagnostic, terminal, source pin and prior UNKNOWN preflight. These two views
do not reclassify the other reported processes. Real FD/process churn and
uncovered namespace evidence from that preflight remain unresolved. Those earlier reads did not establish a
whole-host deletion gate; the later f091 preflight above also refused.

## Reference, mount and failure semantics

The target inventory and each component of an alias now bind the actual
O_PATH descriptor's fdinfo mnt_id to one record in the stable mount view.
Device, mountpoint and the complete parent chain must agree. Crossed layers
must correspond to the component actually traversed. The final visible target
must still match its inventoried metadata and filesystem-relative binding.

The narrowly permitted hidden-route case is an actual, recorded overlay at a
strict ancestor, followed by ENOENT under that held directory. Its parent chain
must include the original candidate route and its filesystem translation must
differ from the target route. Missing paths without that proof, EACCES,
unrecognized mount IDs, disconnected chains, different final target inodes and
changing evidence remain UNKNOWN.

**All potential aliases remain in the conservative reference index**, including
hidden routes. The scanner still checks every visible TID's FD, cwd, exe, root,
maps and owner arguments. Device/inode matching remains independent of pathname
reachability. Deleted-path and owner-argument matching retain the hidden alias.
It never skips the rest of a task just because an alias is hidden.

All mount records, including hidden records, remain subject to target source
and mountpoint checks. A mount at or below a target, or a bind whose source is
inside the target, remains a veto. An ancestor alias alone is not a consumer.

The caller's three veto lists remain process_or_owner_hits, mount_hits and
coverage_errors. UNKNOWN is never admission. Alias indices are reused only
for the same namespace, root identity/mount ID and identical mountinfo bytes;
actual task identities, FD sets, mount views and target metadata are rechecked.
Temporary traversal descriptors close before the task FD census. The narrow
stable, empty, single-leader zombie rule is unchanged.

## Namespace coverage and limits

A foreign task's root inode does not establish a complete namespace view: it
may be chrooted into a hostfs alias. The observer pins and types actual
namespace FDs from task entries, nsfs mounts and task FD tables. Its embedded
collector creates its own children, obtains their native namespace view and
verifies PID identity, namespace, root FD/mount ID and repeated mountinfo while
each child waits on a private control pipe. The scanner checks that witness
again and requires positive child retirement.

No caller-provided dictionary, receipt or arbitrary PID supplies coverage.
Unknown or inaccessible namespace handles, unobserved nested namespaces,
changing witnesses, timeouts and incomplete retirement remain UNKNOWN.
The embedded collector factory is byte-identical to the previously qualified
factory. The historical real private controls exercised its FD-only
namespace discovery and retirement. This revision's new real private
cases also passed with the same unmodified factory.

Opaque nsfs mnt:[positive inode] roots retain their mountpoint veto and are
never used as filesystem ancestor paths. Other non-absolute root formats
remain UNKNOWN. The earlier format evidence remains in
[namespace-format-observation.json](namespace-format-observation.json).

Observation bounds remain 128 exact targets, 100,000 target entries,
20,000 tasks, 500,000 descriptors, bounded reads/hits, and a shared 45-second
budget. Collector child/read bounds and retirement requirements are unchanged.
The current observer source is 76,800 bytes. A caller's prior source-file limit
(66,232 bytes for 13ad; 65,536 in older loaders) must separately admit this
exact source size and SHA;
that adjustment does not enlarge the observer's scan bounds. Source custody
still requires a single-link regular file and stable, verified bytes.

This remains a snapshot, not a lock against future references or writers.

## Reproduce the current qualification

| Group | Entry | Required environment | Current controls per mode |
| --- | --- | --- | ---: |
| Input/reference regression | The three unittest modules below | Linux; no namespace privilege required | 83, passed |
| Complete scanner and owned fixtures | verify_isolated_alias_views.py | Root with private mount/PID namespace capability | 20, passed |
| Exact replacement scope | verify_reference_patch.py | Python; parse/compile only | One scope verification |

Run the source controls from this directory:

~~~sh
python3 -B -m unittest -v test_verify_current_inputs.py test_reference_observer.py test_empty_task_views.py
python3 -B -O -m unittest -v test_verify_current_inputs.py test_reference_observer.py test_empty_task_views.py
~~~

The current recorded runs used Cloud UID 0; they are not a new Pocket4
ordinary-UID observation. Both actual Cloud runs completed 83 tests with zero
failures/errors/skips. The real Linux self-FD/mmap test must find its held
references; unrelated host visibility failures remain UNKNOWN.

The historical 15 private controls retain the original ten cases and add a masked
ancestor route, a kernel-selected samepoint stack, and references held before
masking through an FD, mmap and owner argument. Their specific reference kinds
and process/FD identities must be found. Visible-alias cwd has a real control;
masked cwd has a unit regression and shared code-path review, not a separate
claimed real private control. Wrong final inode remains UNKNOWN. Target-source
and target-mountpoint negatives remain vetoes.

One historical initial private run failed because an argv fixture closed its ready FD
after signaling readiness. The observer correctly reported an FD-set change
and UNKNOWN, while also finding the argument reference. Only the two fixture
handshakes changed: their ready FDs now remain open until controlled exit.
The failed terminal and both subsequent successful modes are preserved
separately; the observer's FD-change gate was not relaxed.

The current fixture retains all 15 cases and adds five real chroot cases:
no references, an FD or mmap held before chroot, cwd outside the jail, and a
task-root-relative argv. Configuration travels over a pipe to avoid embedding
the host target in argv. Each new case first proves actual empty mountinfo and
the jail's exact root device/inode/mount ID, then requires the precise child PID
and reference kind or a clear result. All five passed in both actual Pocket4 modes. The no-reference case
was OBSERVED with no hits; the FD, maps, cwd and argv cases were OBSERVED
with the required specific reference veto. The real wrong-inode case remains
UNKNOWN, as intended.

To reproduce in an authorized private test environment, use an empty owned fixture base:

~~~sh
sudo -n env NAMESPACE_FIXTURE_DIR=/absolute/owned/fixture-base python3 -I -B verify_isolated_alias_views.py /absolute/capsule/reference_observer.py
sudo -n env NAMESPACE_FIXTURE_DIR=/absolute/owned/fixture-base python3 -I -B -O verify_isolated_alias_views.py /absolute/capsule/reference_observer.py
~~~

The fixture creates private mount/PID namespaces and a private procfs, verifies
the unchanged parent namespace/mountinfo, waits for its own children, and
removes its temporary directory before success. Each historical f091 mode reaped
three fixture children, one FD-only namespace collector, its private PID 1 and
the outer fixture process with successful terminal evidence. Each current 20-case mode
positively reaped eight fixture children and six collector children, plus
the outer process and private PID 1. Parent namespace and mountinfo were
unchanged and fixture paths were removed. Both runs used one logical CPU,
nice 19 and RLIMIT_AS 3 GiB; the 43-second fixture deadline was unchanged.
This is not a cgroup MemoryMax measurement or a whole-host reference gate. An unsupported
operation must fail; A08 must not silently skip a control.

The historical 54/29/10 qualification belongs to the source at commit
208d2dca4dccb622869916b9a7381decdddc0dce. Its 29 existing-host controls used six
then-observed Pocket4 namespace objects. The retained
verify_namespace_collector.py is that host-specific entry, not ordinary CI
or a newly repeated host qualification. The current factory's unchanged source
pin and historical receipt are recorded without treating those old runs as
new results.

## Single-function integration boundary

The exact historical helper is
cleanup/apps-old-root-retirement-20261108-8b88-r1/executor.py,
SHA-256 22e7e85962c52a5cf44759dd99610d16293a0f8573ee68b8b9da4c89b1c7911a.
Its complete bundled source exists only for scope replay.
**Never execute or import fixtures/executor-baseline.py.**

[reference_observer.patch](reference_observer.patch) replaces only
live_references(roots). Target selection, current dependencies, signing
release, owner policy and deletion outside that function remain byte-identical.
The scope verifier parses and compiles the replacement without executing or
applying the historical executor:

~~~sh
python3 -I -B verify_reference_patch.py
python3 -I -B -O verify_reference_patch.py
~~~

Both current scope runs passed. Against unchanged 13ad, two focused new
controls fail for the expected empty_mountinfo and last-representative
FileNotFound reasons; the same controls pass on this revision. No live helper
patch was applied.

## Historical selected inputs and retained roots

At 2026-11-09 04:10:06 UTC, the real selector's 13 preparations and 721 retained
records were independently verified. Their union was 723 files /
20,619,335 bytes, including two preparation files outside the retained list.
The historical receipt [live_721_readback.json](live_721_readback.json) binds its
actual CURRENT generation. CURRENT has since advanced; that observation is not
a fresh assertion about today's dependencies or the 42-app runtime result.
It also excluded the executor's additional 22 Camera inputs.

A new use must read and bind the actual current generation:

~~~sh
python3 -I -B verify_current_inputs.py --current /home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json
~~~

The unchanged verifier understands the actual current/selector/retained schemas
and rejects conflicting generations, duplicate keys/paths, changed identities,
symlinks, hardlinks, signing material and bounds.

[remaining-roots-readback.json](remaining-roots-readback.json) is also historical.
Canonical fence backups and a missing historical job/unit do not establish the
original owner's positive terminal state. The 04:37 UTC original-image registry
observation found org.droidloom.qa.amazon.r3 outside the production cohort but
still using its signing lineage. Normal consumer retirement and fresh
identity/data/signing checks are separate prerequisites; this capsule performs
no such Android, app or signing-root action.

[FILES.json](FILES.json) is the exact publication whitelist, excluding itself.
It contains necessary source, baseline fixtures and compact evidence. Current
source replaces its prior version in this directory; Git retains the historical
versions. One-off diagnostic scripts, prototype scanners, raw app data and
private signing material are not current deliverables.

## Historical unknown setup source fixture

`remaining-roots-readback.json` now retains the exact 47,639-byte historical CB
setup request as a hash-bound gzip/base64 source fixture, together with its
existing `outcome_unknown` invocation identity. This inert record permits byte
reconstruction after the obsolete Cloud broker workspace is retired; **do not
execute it**. Static inspection of the outer script and all six embedded source
files, including independent peer review, found no runtime secrets or captured
user-data bodies. The synthetic NSS unit fixtures use `x` password placeholders.

The original command could write, chmod and chown its own Pocket4 review stage.
Its positive terminal state has never been established; later stage absence is
not a terminal receipt. This addition preserves that uncertainty, adds no
execution result, and changes neither the observer nor any Pocket4 deletion
gate. The separate ai395 unknown requests also remain unknown; their missing
original programs have not been audited by inference from compact metadata.
