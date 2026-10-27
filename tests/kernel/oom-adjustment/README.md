# Owned OOM adjustment qualification

This guest fixture remains uncompiled and unexecuted on Linux or a guest.
The first `07bff624` host source suite actually ran 84 Python tests with one
aggregate-profile import error. The QA-only `post-1138-oom-adjustment-v2` source
revision fixes that integration error, preserves the failed evidence, and awaits
new host qualification. No native or ordinary guest result is claimed. This
hardens a prerequisite; `memory.max` remains unsupported and its existing
refusal oracle stays unchanged.

The C binary has a required private marker and argument. The runner injects the
marker into a disposable, networkless ordinary guest and never executes the
binary on the host. Each stage has its own owned process group, three-second
alarm, real credential state and children. The parent acts as a subreaper,
kills only that stage's remaining process group and reaps its descendants.
Leaving a descendant makes even a nominally successful stage fail. The whole
fixture has a 35-second alarm; the inherited QEMU timeout stays 120 seconds.

The fixed initial guest has no created user namespace. Its actual initial
writer must be UID zero with effective `CAP_SYS_RESOURCE`. `capget`, `capset`,
`setresuid`, `setresgid` and `PR_SET_DUMPABLE` change real kernel credentials
and ordinary proc DAC. No test-only permission flag or production helper call
exists in the C binary.

The eleven isolated stages verify:

| Stage | Required public behavior |
| --- | --- |
| uid_floor | UID 60001 with no capabilities: 0 → 500 → 0 succeeds, −1 fails `EACCES`; out of range fails `EINVAL` without mutation |
| privileged_floor | A writer with only effective SYS_RESOURCE replaces floor to 200 and then −100; UID zero without that capability, including SYS_PTRACE alone, cannot cross either floor |
| fork | Actual fork inherits raised current and original floor; later parent changes stay independent |
| clone_vm_exit | A separate CLONE_VM process receives current/floor propagation; after its real exit/reap the retained proc FD returns `ESRCH` |
| vfork | Actual separate-process CLONE_VM\|CLONE_VFORK handshake with a separate C stack; child writes do not propagate to the blocked parent |
| threads | Actual pthread/CLONE_THREAD writers share one Process pair while `capset` changes only each writer's authority |
| exec | Actual nonprivileged exec preserves raised current and the inherited floor; both inherited FD and newly opened proc FD enforce it |
| clone_vm_exec | Actual exec of a separate CLONE_VM peer detaches it before an old-VM parent's privileged write; the replacement retains its own floor |
| fd_credential | A privileged open followed by a real UID/capability drop does not retain the opener's floor-changing authority |
| fd_transfer | SCM_RIGHTS transfers an already-open root-target proc FD; the unprivileged receiver can raise and return to floor, cannot cross it; its fresh open fails DAC |
| owned_dac | A same-UID owned-process writer can open but cannot lower the floor; a different UID cannot open |

The C stages emit both verdicts and actual syscall return/errno facts. The
Python checker requires exactly twelve cases and the exact ordered write
inventory per stage, with matching byte counts and errno. Missing output,
duplicates, early termination, timeout or a failed base guest remain failures.
No failure is converted to a skip because an ABI was expected to work. An
unsupported ABI found during execution must retain its real failure and be
resolved or explicitly split into an unqualified later stage.

The native eight regressions additionally exercise the actual Process VM
publication primitive and the pre-zombie unbind cut. The C post-reap check does
not claim to synchronize the earlier exit/unbind interval. The current exec
case verifies actual replacement and pair preservation in an ordinary fork;
the additional synchronized shared-VM exec stage verifies real syscall
detachment from an old peer. Arbitrary exec/write race qualification remains
distinct. New user namespaces,
setuid-exec variants, and combined CLONE_THREAD\|CLONE_VFORK remain unqualified.

Use only an exact clean source product receipt:

```sh
python3 -I -B tests/kernel/oom-adjustment/run.py --smp 2 \
  --product-evidence /absolute/exact-product --output /absolute/new-evidence
```

The ordinary product must be freshly built from the new QA head, not reused
from e7ed or cd40 under a different source identity. Native filtered runs are
diagnostic; only the complete 420-test core plus complete retained OSTD suite
and the ordinary guest can qualify the new head. Preserve original before
failures and all source, binary, ELF, serial and runner hashes.
