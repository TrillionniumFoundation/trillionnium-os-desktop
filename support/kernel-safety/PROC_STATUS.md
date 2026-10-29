# Per-thread credentials in proc status

The first actual original Root/Agentd G2 guest stopped at Agentd's strict
credential readback. The kernel implemented `PR_SET_NO_NEW_PRIVS` and
`PR_GET_NO_NEW_PRIVS`, but `/proc/self/status` omitted `NoNewPrivs`. Root's
independent `/proc/<agent-pid>/status` startup check required the same field.
The earlier plain Agentd large-image preflight did not exercise this boundary.

After that fix, the next original guest passed Agentd's strict credential
readback and completed the original SQLite genesis, then Root rejected startup.
`Groups:` was also missing. Root requires that field to exist and contain no
supplementary groups. The documentation's list of Linux status fields was not
evidence that every field had actually been implemented. The two failed guests
are retained separately; neither qualified the owner.

`procfs/pid/task/status.rs` now prints `NoNewPrivs:\t0` or `NoNewPrivs:\t1`
from the retained target thread credential handle used for UIDs and capabilities.
`/proc/<pid>/status` describes the leader; `/proc/<pid>/task/<tid>/status`
describes that thread. The implementation neither changes privilege state nor
substitutes the reader's credentials. Agentd's checks are unchanged.

The same target handle supplies an immutable group-set snapshot for `Groups:`.
Each actual supplementary group is
printed as an unsigned decimal ID in the credential set's sorted order. An empty
set prints `Groups:\t\n`; a nonempty set must never be replaced with an empty
placeholder. This is read-only reporting, not a new privilege transition. A
status read is not a transaction with later credential changes, and separate
small reads do not promise a single snapshot across arbitrary concurrent
mutations. The tests hold each target state stable during its read.

The original Root `authority_host_runtime::verify_process` contract was checked
in full: a nonzero bounded PID, matching kernel boot UUID, nonzero matching
`/proc/<pid>/stat` field 22 start ticks, four dedicated UID values, all five
capability sets zero, `NoNewPrivs:\t1`, and an existing empty `Groups:` line.
The failing second guest had already passed the boot and start identity checks.
UIDs, capabilities, NNP, boot ID and start ticks use the existing actual kernel
state. This stage fills the remaining groups output; it does not relax Root's
requirements or assert that all possible proc ABI fields are implemented.

`tests/kernel/proc-status/run.py` runs the actual static C probe in an ordinary
Asterinas guest through the existing safety runner. It accepts the same
`--output`, `--smp` and exact-source `--product-evidence` options. The probe reads
status in small chunks, verifies initial zero and irreversible one, retains a
thread with zero while its leader has one, then checks the changed target thread,
new-thread/fork/exec inheritance, and a distinct Root reader observing an owned
child after the original Agentd UID/GID/capability/NNP drop sequence. It touches
only its own process, threads and child. It never executes a probe on the host.

The groups cases set and read a sorted nonempty set (including IDs above 65535),
require that set to fail an empty-groups policy, read the dropped child's actual
empty groups from its distinct Root parent, and prove the parent's groups stay
unchanged. An existing thread retains its original set while the leader changes
its own; that thread then clears only its own groups. Both readers distinguish
the leader status from the target thread status. Group mutation in these thread
cases uses raw `SYS_setgroups`, since libc can coordinate POSIX process-wide
credential updates. New-thread, fork and exec inheritance are checked against
both `getgroups` and the real proc output. The same updated probe runs against
the previous kernel as a real negative control before the fixed kernel runs.

Example after a matching ordinary product build:

```sh
python3 -B tests/kernel/proc-status/run.py --smp 4 \
  --product-evidence /path/to/exact-source-product --output /path/to/new-evidence
```

These fixes address two proc ABI omissions. The first original failed guest's
log-limit termination and the second guest's explicit Root admission failure
remain separate evidence. Passing this probe does not qualify the
original owner, SQLite terminal state, cross-boot recovery, or production.
No Cargo/build-input derivation changes are needed for this Rust-only proc change.
