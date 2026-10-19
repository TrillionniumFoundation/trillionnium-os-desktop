# Successful leader cleanup: real RED and GREEN

The fixed old R9 HEAD `5060ac6976b56b32647c728991e489cdee1cce9d`
finished its ARM readonly eight-original/eight-Session gate and five-ELF
packaging. Its overall run `39182491155` failed later with
`[Errno 39] Directory not empty: 'plugins'`. Raw Objective acceptance output
did not complete the outer report, cleanup, final runtime binding or six-ELF
qualification. The actual CI writer PID was not recorded. Connecting that
failure to the success cleanup branch is a source inference; the separate
real-process reproduction below proves the branch defect itself.

`bounded_command` previously reaped an exit-zero leader without cleaning its
owned process group. The change sends every observed completion through the
existing TERM/grace/KILL cleanup while the real leader is still a WNOWAIT
identity anchor, then performs the existing sole reap. The leader's actual
exit-zero business result remains zero. `ChildGroup`, identity-loss rejection,
the signal deadlines and `terminate_group` are unchanged.

## Actual results

| Attempt | Result | Evidence meaning |
| --- | --- | --- |
| `red-01` | Process exit 1; two unittest failures | The no-signal assertion failed as intended, but the writer fixture's AF_UNIX bind was denied by the default sandbox. This is not the complete RED. |
| `red-02` | Process exit 1; two intended assertion failures | With the authorized local socket available, a same-group writer remained alive and performed a real plugin-file write at the unreaped exit-zero leader boundary. |
| `green-01` | Two focused tests passed | The unchanged tests observed real TERM exit of the writer before leader reap, preserving leader exit 0. |
| `related-01` | 47 tests passed; no skips | Seven process guards, six Session receipt validators, twelve Objective receipt validators and twenty-two history receipt/source contracts. |

Every attempt preserves exact source snapshots, before/after file identities,
the execution plan, helper snapshot, patch, unedited stdout/stderr and receipt.
The helper's `expected_result` field means its expected process exit matched;
`review.json` separately checks actual failure reasons and test counts.

The RED production guard is byte-identical to the failed CI Git blob. The test
file is identical across RED and GREEN. Local execution occurred on the dirty
integration worktree with its complete source patch recorded; the base HEAD
alone is not the identity of the changed execution inputs. The only changed
production Python definition is `bounded_command`.

## Process ownership proof

A fresh fixture subprocess owns its own subreaper state, leader and writer.
The unittest parent never changes subreaper state. The writer connects through
a bounded Unix socket handshake; the fixture checks SO_PEERCRED, UID and the
actual leader process group before allowing the leader to exit. There is no
sleep-based readiness condition. Before each real group signal and at the reap
boundary, the fixture reads the leader's actual exit-zero WNOWAIT status.

RED records the writer's actual file write while it is still live at that
boundary. Cleanup then uses its already-open pidfd to stop it and reaps both
owned identities. GREEN records pidfd exit before leader reap and the writer's
actual `CLD_KILLED/SIGTERM` status. Both paths finish with an actual ECHILD from
P_ALL in the isolated fixture. No numeric PID/PGID reuse is induced.

The production fix reuses the existing bounded process-group contract. This
test does not qualify arbitrary daemonized descendants that escape that group.

## Qualification boundary

No original Hepta process, Rust compilation, ARM job, target OS or device was
started by these checks. The five fixed-original manifest tests were not run
locally because their full unchanged original checkout was not restored; they
were not silently skipped. Receipt/history fixtures are validator tests and
do not constitute original-owner execution.

The new integrated HEAD still requires its own actual CI. These local tests do
not change the failed old-head ARM conclusion or transfer readonly, Objective,
ELF or original-owner qualification between different heads.
