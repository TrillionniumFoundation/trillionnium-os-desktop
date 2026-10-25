# Per-thread NoNewPrivs in proc status

The first actual original Root/Agentd G2 guest stopped at Agentd's strict
credential readback. The kernel implemented `PR_SET_NO_NEW_PRIVS` and
`PR_GET_NO_NEW_PRIVS`, but `/proc/self/status` omitted `NoNewPrivs`. Root's
independent `/proc/<agent-pid>/status` startup check required the same field.
The earlier plain Agentd large-image preflight did not exercise this boundary.

`procfs/pid/task/status.rs` now prints `NoNewPrivs:\t0` or `NoNewPrivs:\t1`
from the retained target thread credential snapshot used for UIDs and capabilities.
`/proc/<pid>/status` describes the leader; `/proc/<pid>/task/<tid>/status`
describes that thread. The implementation neither changes privilege state nor
substitutes the reader's credentials. Agentd's checks are unchanged.

`tests/kernel/proc-status/run.py` runs the actual static C probe in an ordinary
Asterinas guest through the existing safety runner. It accepts the same
`--output`, `--smp` and exact-source `--product-evidence` options. The probe reads
status in small chunks, verifies initial zero and irreversible one, retains a
thread with zero while its leader has one, then checks the changed target thread,
new-thread/fork/exec inheritance, and a distinct Root reader observing an owned
child after the original Agentd UID/GID/capability/NNP drop sequence. It touches
only its own process, threads and child. It never executes a probe on the host.

Example after a matching ordinary product build:

```sh
python3 -B tests/kernel/proc-status/run.py --smp 4 \
  --product-evidence /path/to/exact-source-product --output /path/to/new-evidence
```

This fixes one proc ABI omission. The original failed guest and its log-limit
termination remain separate evidence. Passing this probe does not qualify the
original owner, SQLite terminal state, cross-boot recovery, or production.
No Cargo/build-input derivation changes are needed for this Rust-only proc change.
