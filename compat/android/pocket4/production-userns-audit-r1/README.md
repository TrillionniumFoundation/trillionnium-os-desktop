# Existing user namespace mapping audit

This source capsule diagnoses UID/GID occupancy in the running Linux kernel. It does not allocate an identity, write a map, change an account, enter Android, or authorize production launch. The production API currently issues no guard: a complete, conflict-free **active** inventory returns `CoverageIncomplete` because Linux `listns` omits inactive objects that may later be resurrected. Existing conflicts remain explicit evidence.

## Integration boundary

`production_namespace_audit.rs` is a private supervisor module that consumes the existing `crate::IdRange` type. Its entry point is:

```rust
audit_existing_user_namespaces(uids, gids, deadline)
    -> Result<NamespaceAuditGuard, AuditError>
```

`AuditError` distinguishes `Conflict`, `Unknown`, and `CoverageIncomplete`. Every error refuses the mapping transaction. The guard has private fields, cannot be deserialized or cloned, and accepts no caller-supplied process, namespace exclusion, proc directory, inventory, or receipt. The retained `revalidate(deadline)` interface must be called before creating a broker's own unmapped user namespace; an empty map is unknown, and there is no arbitrary exclusion for it. With the currently supported coverage, no guard is constructed.

This module is independent of a particular broker implementation. A caller must preserve its NSS/subid checks, dedicated account checks, durable range reservation, and child-custody rules. Those checks do not establish that old, inactive kernel references have released their mappings.

## What the observation proves

The caller must be in the initial host user and PID namespaces, with root credentials and effective `CAP_SYS_ADMIN` and `CAP_SYS_PTRACE`. The code binds typed nsfs descriptors, the initial namespace inode definitions, the actual initial PID 1 view, identity maps, and credentials. Runtime namespace IDs are observed rather than hardcoded.

A bounded global `listns(USER_NS, owner=0)` call enumerates active user namespaces, including the active ownership chain of persistent nsfs, taskless namespace-FD, and other active namespace holders. Every namespace receives a retained, typed export-handle descriptor. The code verifies its ancestry to the proved initial user namespace and repeats the global enumeration before returning. There is no proc-only completeness fallback.

For each noninitial namespace, the scanner creates its own collector with `clone3(CLONE_PIDFD)`. Only that child enters the held user namespace. The parent stays in its initial namespace and reads the child's full `uid_map` and `gid_map`; column two therefore uses host IDs, including for nested namespaces. Actual PID/TID, start time, proc descriptor identity, namespace identity, map bytes, signal mask, and liveness are checked before and after the reads. The initial identity map is excluded only after its separate proof; it is not treated as a conflict with every candidate range.

The parent keeps the exact child pidfd through `waitid(P_PIDFD)`. A missing terminal, an external reaper, a changed identity, unsupported ABI, map truncation, namespace churn, or other incomplete evidence produces `Unknown`. `ECHILD` never means successful retirement. Signaling never falls back to a numeric PID.

## Collector containment and lifetime

Only the calling thread's signal mask is temporarily blocked across clone, including the glibc-reserved signals. The parent restores and verifies its prior mask immediately. The child keeps its mask blocked and runs only stack-based libc/syscall operations followed by `_exit`; inherited asynchronous handlers cannot execute. A non-default `SIGCHLD` disposition or `SA_NOCLDWAIT` is rejected.

The creating thread has its own held `PIDFD_THREAD` descriptor. The child arms `PDEATHSIG=SIGKILL` and checks this descriptor before and after `setns`, because the kernel death signal is tied to the creating thread and credential changes may clear it. It also checks the expected parent process.

The child is non-dumpable before and after joining a foreign user namespace. Host `fs.suid_dumpable=1` is refused; only 0 or 2 is accepted. The child neither shares the parent's VM/thread group nor execs, so its memory retains the initial user namespace as owner. The initial-namespace ptrace capability check protects inherited memory and descriptors from processes privileged only in the foreign namespace. The parent requires `CAP_SYS_PTRACE` to read its non-dumpable collector; failure is not worked around by relaxing dumpability.

Bounds are 256 namespaces, 340 map extents per map, 64 KiB per map, 16 MiB aggregate map bytes, and a caller deadline of at most 45 seconds with a two-second retirement reserve. The deadline is a cooperative observation budget. Required final kill/wait retirement is not a hard real-time guarantee.

## Replay

The small standalone package supplies only the existing `IdRange` shape and a diagnostic CLI. It is not a replacement production supervisor. From this directory, run:

```text
cargo test --locked --offline -j 1 -- --test-threads=1
cargo build --locked --offline -j 1
target/debug/userns-audit observe UID_START GID_START COUNT
```

The unit suite runs as an ordinary UID. Its signal-policy regression creates and positively waits for a private test subprocess. A privileged observation needs the initial host namespaces and capabilities listed above and creates only its own bounded collectors. It does not create namespaces or modify mappings. The diagnostic process returns JSON with the refusal status, observed mappings and conflicts, exact collector terminals, parent identity checks, and a before/after descriptor-retirement check. A zero CLI exit means the diagnostic completed; inspect `status` and `namespace_mapping_authorized`, which remains false.

The historical 200000/100000 candidate used during qualification is a diagnostic input, not a current delegation or account grant. `verification.json` records current-source hashes, actual test counts, authoritative terminal receipts, and earlier failed attempts. `source-provenance.json` records the kernel and project contracts. `FILES.json` enumerates only the final source and evidence files; probe prototypes, binaries, targets, and old source revisions are not deliverables.

## Qualification state

The final source candidate completed independent static review and 11 focused Linux tests: 11 passed, with no failed, ignored, or filtered tests. These include the original map/parser/deadline checks plus actual calling-thread signal-mask restoration and a private subprocess control that refuses automatic child reaping. The earlier compile failure and superseded nine-test result remain separately identified in the receipt.

Two privileged observations on Pocket4 enumerated 12 active user namespaces each, including the initial namespace. Every noninitial namespace received an owned collector: 22 collectors in total, all with exit code 0 and positive `waitid(P_PIDFD)` retirement. Both observations verified unchanged parent identity/user/mount namespaces, matching final inventory, and complete descriptor retirement. Neither observation created a namespace or wrote a UID/GID map.

| Actual diagnostic input, for both UID and GID | Result | Evidence |
| --- | --- | --- |
| Start 200000, count 100000 | `COVERAGE_INCOMPLETE` | No overlap with the 11 observed noninitial maps; inactive references remain unenumerated, so no guard is issued. |
| Start 100000, count 65536 | `CONFLICT` | Two actual namespaces overlap, producing six UID/GID extent hits; this is an occupied-range negative control. |

The observed parent namespace 121 maps host IDs 100000 through 165535 in one 65536-ID extent. Its nested namespace 139 maps the same host range in extents of 1000 and 64536 IDs, with the desktop UID/GID mapped separately. These are runtime observation IDs, not assumed kernel constants. The nested result exercises the parent-opened host map view on a real nested namespace.

The previously timed-out ordinary-UID request was recovered by exact request identity and positively reconciled as succeeded with complete durable output. Its observation correctly refused initial-host privileges and created no collectors. It was not rerun. All execution requests in this capsule have authoritative terminal evidence. PTY close acknowledgements reported `already_exited` with unknown close metadata; subsequent authoritative reads still confirmed exit code 0 and complete output, so the receipt does not claim a successful close acknowledgement as termination proof.

No live supervisor, cleanup helper, account, subid file, or active owner checkout was modified. Production mapping remains refused until the inactive-reference coverage or equivalent historical range provenance is actually established.
