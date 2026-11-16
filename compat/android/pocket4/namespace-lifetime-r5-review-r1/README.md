# Pocket4 namespace lifetime source review

This is a source review package for an isolated candidate based on the frozen
production namespace broker **r5**. It is **not a deployment, Android runtime
qualification, application acceptance result, or production-ready release**.
Production admission and runtime readiness remain false.

The coordinator reported a platform safety-check interruption before the
planned private validation. The agent stopped all further remote mutations and
process launches, did not retry the private controls through another entry
point, and completed only read-only inventory and this local export. **No new
private or privileged namespace, loop, mount, or diagnostic-unit control in
this package was executed.** The private runner was not compiled or executed
and is excluded from this package.

## Exact source boundary

The source workspace was exported from upstream commit
`b4dc3b49ce29e706efca0ba5a7c775864d9b54b8` and overlaid with all exact frozen r5
source inputs. The isolated r5 snapshot HEAD is
`8db9faa6bc337844e5bc0093a237824cf2e0b782`. The final two-file change remains
uncommitted in that isolated workspace; publication of this review package does
not apply it to the active owner's source.

The frozen r5 manifest is 82,624 bytes, SHA-256
`b5c2df96128fa79efde357dfa75352e6070aba5eeaccdcd74f0f157976cf6053`.
`qualification.json` pins both preimages and postimages. The patch was checked
and replayed locally against those exact preimages; both resulting hashes
matched the actual tested source. Newer owner changes must be reconciled with
those pins; this package does not justify overwriting a moving owner tree.

The product patch changes only `production_namespace_child.rs` and
`production_namespace_tests.rs`. It preserves the frozen r5 device and tree
implementation. No shared owner source, CURRENT state, original source/build
lock inode, application data, or Android installation was modified.

## What changed

Linux's thread PIDFD can remain unreadable after a thread-group leader exits
while another thread in the same group survives. The old PIDFD-only check
therefore missed an actual creating-thread death window. The candidate also
holds the live creator's read-only proc stat file, verifies its procfs and TID
binding before clone, and reads that same descriptor after PDEATHSIG arming.
Its bounded parser rejects exited/exiting creators, malformed observations and
read failures without reopening a saved numeric TID.

The held stat is retained across credential rearming and the CLONE_PARENT
creation step so that nested PID1 can perform the same check. Source descriptors
are pinned above the fixed child slots before remapping. The intended nested
handoff closes the creator observations before mount/READY and returns to the
FD3-only barrier. This nested behavior has been reviewed in source but its new
privileged runtime qualification remains pending.

## Actual completed validation

The final ordinary-UID job was `1a1bffdc26b-5e21-847` on pocket4. It completed
with exit 0 and durable, complete output. It used one CPU, one Cargo job and a
4 GiB bound.

| Scope | Actual result |
| --- | --- |
| Focused namespace library tests | 17 passed, 0 failed, 4 privileged tests ignored |
| Non-test supervisor library and both binaries | Build succeeded |
| Non-leader initial-arm/rearm controls | Passed; included in the 17 tests |
| Actual group-leader initial-arm/rearm controls | Both exited 125 and were actually reaped; both outer processes exited 0 |
| Earlier PIDFD-only comparison | Both actual leader windows incorrectly reached sentinel exit 127; failure and complete reap evidence retained |
| Local exact-preimage patch replay | Passed; both postimage SHA-256 values matched |

The ordinary leader program deliberately keeps the original TGID alive after
the creating leader exits. Both final controls observed a zombie creator and an
unreadable thread PIDFD before the child rejected the creator. Its helper panic
path explicitly exits nonzero, and its outer check requires an actual, unique
exit125/reaped result record.

The source of that actually run program is included as
`creator_leader_control.rs`. It also contains a compiled nested test entry;
**that nested entry was never invoked**. `leader_fd_probe.rs` is the source of
the separate, actually run read-only PIDFD/stat observation. Both are historical
test source, not installed executables or permission to run private controls.

## Outstanding qualification

The new patch has not run the privileged user-namespace mapping control, PID1
namespace control, empty-base mount controls, or private-device control. The
actual nested leader early-death positive and PIDFD-only negative controls also
remain unexecuted. Their pending/ignored status is not a pass. Older r4, 81-test
or 184-test results are not transferred to this new candidate.

All 18 H jobs recorded for this namespace branch have terminal states; the one
failed job is the retained earlier PIDFD-only negative comparison. Read-only
final service inventory found all five planned new private diagnostic units
not found, inactive and with MainPID 0. No private root stage or fixture was
created by this agent.

The independent review accepts the source for review and explicitly leaves
private qualification incomplete. The kernel review records the inspected
7.0.14-p4cred1 source semantics. The manifest lists every member of this package
and locks its exact bytes and SHA-256. Binaries, APKs, build outputs, large logs,
the unexecuted private runner and unexecuted mutant source copies are excluded.
